from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Barrier, BrokenBarrierError, Lock
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import ensure_account_proxy_url
from refactor_app.infrastructure.db.models import (
    AccountSessionOtpSnapshotModel,
    ProxyInventoryModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
)
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.session_login import (
    prepare_chatgpt_session_otp,
    submit_prepared_chatgpt_session_otp,
)

DEFAULT_SESSION_OTP_PREPARE_WORK_COUNT = 50
SESSION_OTP_SUBMIT_BARRIER_TIMEOUT_S = 120.0
SESSION_OTP_SUBMIT_READY_STATUSES = ("otp_collected", "otp_pending")


class SpaceSessionOtpWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceSessionOtpCandidate:
    space_membership_id: str
    user_account_id: str
    snapshot_id: str = ""


@dataclass
class _SubmitBarrierState:
    barrier: Barrier
    lock: Lock
    ready_count: int = 0
    skipped_count: int = 0


_SUBMIT_BARRIERS_LOCK = Lock()
_SUBMIT_BARRIERS: dict[str, _SubmitBarrierState] = {}


class _SubmitBarrierParticipant:
    def __init__(
        self,
        *,
        barrier_key: str,
        expected: int,
        timeout_s: float,
    ) -> None:
        self.barrier_key = barrier_key
        self.expected = expected
        self.timeout_s = timeout_s
        self.arrived = False

    def wait_ready(self, _email: str = "") -> None:
        self._wait(ready=True)

    def wait_skipped(self, _email: str = "") -> None:
        self._wait(ready=False)

    def _wait(self, *, ready: bool) -> None:
        if self.arrived:
            return
        self.arrived = True
        _wait_for_submit_barrier(
            barrier_key=self.barrier_key,
            expected=self.expected,
            timeout_s=self.timeout_s,
            ready=ready,
        )


def select_space_session_otp_prepare_candidates(
    *,
    session: Session,
    space_id: str,
) -> list[SpaceSessionOtpCandidate]:
    _active_space(session=session, space_id=space_id)
    rows = session.execute(
        select(SpaceMembershipModel, UserAccountModel)
        .join(
            UserAccountModel,
            UserAccountModel.id == SpaceMembershipModel.user_account_id,
        )
        .where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.membership_status == "active",
            UserAccountModel.account_status == "active",
            func.length(func.trim(UserAccountModel.email)) > 0,
        )
        .order_by(SpaceMembershipModel.created_at.asc(), SpaceMembershipModel.id.asc())
    ).all()
    return [
        SpaceSessionOtpCandidate(
            space_membership_id=membership.id,
            user_account_id=account.id,
        )
        for membership, account in rows
    ]


def select_space_session_otp_submit_candidates(
    *,
    session: Session,
    space_id: str,
) -> list[SpaceSessionOtpCandidate]:
    _active_space(session=session, space_id=space_id)
    rows = session.execute(
        select(
            SpaceMembershipModel,
            UserAccountModel,
            AccountSessionOtpSnapshotModel,
        )
        .join(
            UserAccountModel,
            UserAccountModel.id == SpaceMembershipModel.user_account_id,
        )
        .join(
            AccountSessionOtpSnapshotModel,
            AccountSessionOtpSnapshotModel.user_account_id == UserAccountModel.id,
        )
        .where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.membership_status == "active",
            UserAccountModel.account_status == "active",
            func.length(func.trim(UserAccountModel.email)) > 0,
            AccountSessionOtpSnapshotModel.snapshot_status.in_(SESSION_OTP_SUBMIT_READY_STATUSES),
        )
        .order_by(SpaceMembershipModel.created_at.asc(), SpaceMembershipModel.id.asc())
    ).all()
    return [
        SpaceSessionOtpCandidate(
            space_membership_id=membership.id,
            user_account_id=account.id,
            snapshot_id=snapshot.id,
        )
        for membership, account, snapshot in rows
    ]


def space_session_otp_summary(*, session: Session, space_id: str) -> dict:
    space = _active_space(session=session, space_id=space_id)
    prepare_count = len(
        select_space_session_otp_prepare_candidates(session=session, space_id=space_id)
    )
    status_rows = session.execute(
        select(AccountSessionOtpSnapshotModel.snapshot_status, func.count())
        .select_from(SpaceMembershipModel)
        .join(
            UserAccountModel,
            UserAccountModel.id == SpaceMembershipModel.user_account_id,
        )
        .join(
            AccountSessionOtpSnapshotModel,
            AccountSessionOtpSnapshotModel.user_account_id == UserAccountModel.id,
        )
        .where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.membership_status == "active",
            UserAccountModel.account_status == "active",
            func.length(func.trim(UserAccountModel.email)) > 0,
        )
        .group_by(AccountSessionOtpSnapshotModel.snapshot_status)
    ).all()
    snapshot_status_counts = {status: int(count or 0) for status, count in status_rows}
    submit_count = sum(
        snapshot_status_counts.get(status, 0) for status in SESSION_OTP_SUBMIT_READY_STATUSES
    )
    return {
        "space_id": space.id,
        "space_name": space.name,
        "prepare_candidate_count": prepare_count,
        "submit_snapshot_count": submit_count,
        "snapshot_status_counts": snapshot_status_counts,
    }


class SpaceSessionOtpWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run_prepare_work(
        self,
        *,
        space_id: str,
        space_membership_id: str,
        user_account_id: str,
        work_id: str = "",
        job_id: str = "",
    ) -> dict:
        try:
            with self._session_factory() as session:
                membership, account = _active_member_account(
                    session=session,
                    space_id=space_id,
                    space_membership_id=space_membership_id,
                    user_account_id=user_account_id,
                )
                email = account.email
                password = account.password

            proxy_url = ensure_account_proxy_url(
                self._session_factory,
                user_account_id,
                bind_reason="space_session_otp_prepare",
            )
            proxy_id = _active_account_proxy_id(
                session_factory=self._session_factory,
                user_account_id=user_account_id,
            )
            result = prepare_chatgpt_session_otp(
                email=email,
                password=password,
                proxy=proxy_url,
                mail_provider=self._mail_provider,
            )
            status = str(result.snapshot.get("phase") or "")
            if not result.ok or status not in SESSION_OTP_SUBMIT_READY_STATUSES:
                raise SpaceSessionOtpWorkflowError(
                    f"session OTP prepare returned unsupported status: {status or '(empty)'}"
                )
            snapshot_json = {
                **dict(result.snapshot),
                "_space_id": space_id,
                "_space_membership_id": membership.id,
                "_prepare_job_id": job_id,
                "_prepare_work_id": work_id,
                "_proxy_id": proxy_id,
            }
            snapshot_id = self._write_snapshot(
                user_account_id=user_account_id,
                source_membership_id=membership.id,
                snapshot_status=status,
                snapshot_json=snapshot_json,
                prepared=True,
            )
            return {
                "space_id": space_id,
                "space_membership_id": membership.id,
                "user_account_id": user_account_id,
                "snapshot_id": snapshot_id,
                "snapshot_status": status,
                "otp_code_len": len(str(snapshot_json.get("otp_code") or "")),
            }
        except Exception as exc:
            self._write_snapshot_failure(
                user_account_id=user_account_id,
                source_membership_id=space_membership_id,
                space_id=space_id,
                job_id=job_id,
                work_id=work_id,
                exc=exc,
            )
            raise

    def run_submit_work(
        self,
        *,
        space_id: str,
        space_membership_id: str,
        user_account_id: str,
        snapshot_id: str,
        barrier_key: str,
        barrier_expected: int,
        barrier_timeout_s: float = SESSION_OTP_SUBMIT_BARRIER_TIMEOUT_S,
    ) -> dict:
        participant = _SubmitBarrierParticipant(
            barrier_key=barrier_key,
            expected=barrier_expected,
            timeout_s=barrier_timeout_s,
        )
        try:
            snapshot_json, proxy_url = self._load_submit_input(
                space_id=space_id,
                space_membership_id=space_membership_id,
                user_account_id=user_account_id,
                snapshot_id=snapshot_id,
            )
        except Exception as exc:
            participant.wait_skipped()
            self._record_submit_failure(snapshot_id=snapshot_id, exc=exc)
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "space_membership_id": space_membership_id,
                "user_account_id": user_account_id,
                "snapshot_id": snapshot_id,
                "submit_status": "skipped",
                "skip_reason": f"{type(exc).__name__}: {exc}"[:500],
            }

        try:
            result = submit_prepared_chatgpt_session_otp(
                snapshot=snapshot_json,
                proxy=proxy_url,
                mail_provider=self._mail_provider,
                before_validate=participant.wait_ready,
                before_skip=participant.wait_skipped,
            )
        except Exception as exc:
            if not participant.arrived:
                participant.wait_skipped()
                self._record_submit_failure(snapshot_id=snapshot_id, exc=exc)
                return {
                    "_work_outcome": "skipped",
                    "space_id": space_id,
                    "space_membership_id": space_membership_id,
                    "user_account_id": user_account_id,
                    "snapshot_id": snapshot_id,
                    "submit_status": "skipped",
                    "skip_reason": f"{type(exc).__name__}: {exc}"[:500],
                }
            self._record_submit_failure(snapshot_id=snapshot_id, exc=exc)
            raise

        status = str(result.snapshot.get("phase") or "")
        if status not in {"otp_validated", "otp_missing"}:
            error = SpaceSessionOtpWorkflowError(
                f"session OTP submit returned unsupported status: {status or '(empty)'}"
            )
            self._record_submit_failure(snapshot_id=snapshot_id, exc=error)
            raise error
        if status == "otp_missing" and not participant.arrived:
            participant.wait_skipped()
        self._write_submitted_snapshot(
            snapshot_id=snapshot_id,
            snapshot_status=status,
            snapshot_json=dict(result.snapshot),
        )
        output = {
            "space_id": space_id,
            "space_membership_id": space_membership_id,
            "user_account_id": user_account_id,
            "snapshot_id": snapshot_id,
            "submit_status": status,
        }
        if status == "otp_missing":
            output["_work_outcome"] = "skipped"
            output["skip_reason"] = str(result.snapshot.get("otp_error") or "OTP missing")[:500]
        return output

    def _load_submit_input(
        self,
        *,
        space_id: str,
        space_membership_id: str,
        user_account_id: str,
        snapshot_id: str,
    ) -> tuple[dict, str]:
        with self._session_factory() as session:
            _active_member_account(
                session=session,
                space_id=space_id,
                space_membership_id=space_membership_id,
                user_account_id=user_account_id,
            )
            snapshot = session.get(AccountSessionOtpSnapshotModel, snapshot_id)
            if snapshot is None or snapshot.user_account_id != user_account_id:
                raise SpaceSessionOtpWorkflowError(f"session OTP snapshot not found: {snapshot_id}")
            if snapshot.snapshot_status not in SESSION_OTP_SUBMIT_READY_STATUSES:
                raise SpaceSessionOtpWorkflowError(
                    f"session OTP snapshot is not submit-ready: {snapshot.snapshot_status}"
                )
            snapshot_json = dict(snapshot.snapshot_json or {})
            if not snapshot_json:
                raise SpaceSessionOtpWorkflowError("session OTP snapshot payload is empty")
            proxy_url = str(snapshot_json.get("proxy") or "").strip()
            if not proxy_url:
                raise SpaceSessionOtpWorkflowError("session OTP snapshot has no original proxy")
            return snapshot_json, proxy_url

    def _write_snapshot(
        self,
        *,
        user_account_id: str,
        source_membership_id: str,
        snapshot_status: str,
        snapshot_json: dict,
        prepared: bool,
    ) -> str:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalars(
                select(AccountSessionOtpSnapshotModel).where(
                    AccountSessionOtpSnapshotModel.user_account_id == user_account_id
                )
            ).first()
            if row is None:
                row = AccountSessionOtpSnapshotModel(
                    id=f"session-otp-snapshot-{uuid4()}",
                    user_account_id=user_account_id,
                    source_membership_id=source_membership_id,
                    snapshot_status=snapshot_status,
                    snapshot_json=snapshot_json,
                    otp_code_len=len(str(snapshot_json.get("otp_code") or "")),
                    last_error_code="",
                    last_error_message="",
                    prepared_at=now if prepared else None,
                    submitted_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.source_membership_id = source_membership_id
                row.snapshot_status = snapshot_status
                row.snapshot_json = snapshot_json
                row.otp_code_len = len(str(snapshot_json.get("otp_code") or ""))
                row.last_error_code = ""
                row.last_error_message = ""
                if prepared:
                    row.prepared_at = now
                    row.submitted_at = None
                row.updated_at = now
            session.commit()
            return row.id

    def _write_snapshot_failure(
        self,
        *,
        user_account_id: str,
        source_membership_id: str,
        space_id: str,
        job_id: str,
        work_id: str,
        exc: Exception,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            if session.get(UserAccountModel, user_account_id) is None:
                return
            row = session.scalars(
                select(AccountSessionOtpSnapshotModel).where(
                    AccountSessionOtpSnapshotModel.user_account_id == user_account_id
                )
            ).first()
            error_code = type(exc).__name__[:200]
            error_message = str(exc)[:1000]
            if row is None:
                row = AccountSessionOtpSnapshotModel(
                    id=f"session-otp-snapshot-{uuid4()}",
                    user_account_id=user_account_id,
                    source_membership_id=source_membership_id,
                    snapshot_status="failed",
                    snapshot_json={
                        "_space_id": space_id,
                        "_prepare_job_id": job_id,
                        "_prepare_work_id": work_id,
                    },
                    otp_code_len=0,
                    last_error_code=error_code,
                    last_error_message=error_message,
                    prepared_at=now,
                    submitted_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.source_membership_id = source_membership_id
                row.snapshot_status = "failed"
                row.snapshot_json = {
                    "_space_id": space_id,
                    "_prepare_job_id": job_id,
                    "_prepare_work_id": work_id,
                }
                row.otp_code_len = 0
                row.last_error_code = error_code
                row.last_error_message = error_message
                row.prepared_at = now
                row.submitted_at = None
                row.updated_at = now
            session.commit()

    def _record_submit_failure(self, *, snapshot_id: str, exc: Exception) -> None:
        with self._session_factory() as session:
            row = session.get(AccountSessionOtpSnapshotModel, snapshot_id)
            if row is None:
                return
            row.snapshot_status = "failed"
            row.last_error_code = type(exc).__name__[:200]
            row.last_error_message = str(exc)[:1000]
            row.updated_at = datetime.now(UTC)
            session.commit()

    def _write_submitted_snapshot(
        self,
        *,
        snapshot_id: str,
        snapshot_status: str,
        snapshot_json: dict,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.get(AccountSessionOtpSnapshotModel, snapshot_id)
            if row is None:
                raise SpaceSessionOtpWorkflowError(f"session OTP snapshot not found: {snapshot_id}")
            row.snapshot_status = snapshot_status
            row.snapshot_json = snapshot_json
            row.otp_code_len = len(str(snapshot_json.get("otp_code") or ""))
            row.last_error_code = ""
            row.last_error_message = ""
            row.submitted_at = now
            row.updated_at = now
            session.commit()


def _active_space(*, session: Session, space_id: str) -> SpaceModel:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise SpaceSessionOtpWorkflowError(f"space not found: {space_id}")
    if space.space_status != "active":
        raise SpaceSessionOtpWorkflowError(f"space is not active: {space_id}")
    return space


def _active_member_account(
    *,
    session: Session,
    space_id: str,
    space_membership_id: str,
    user_account_id: str,
) -> tuple[SpaceMembershipModel, UserAccountModel]:
    _active_space(session=session, space_id=space_id)
    membership = session.get(SpaceMembershipModel, space_membership_id)
    if (
        membership is None
        or membership.space_id != space_id
        or membership.user_account_id != user_account_id
        or membership.membership_status != "active"
    ):
        raise SpaceSessionOtpWorkflowError(f"space membership is not active: {space_membership_id}")
    account = session.get(UserAccountModel, user_account_id)
    if account is None or account.account_status != "active" or not account.email.strip():
        raise SpaceSessionOtpWorkflowError(f"user account is not active: {user_account_id}")
    return membership, account


def _active_account_proxy_id(
    *,
    session_factory: Callable[[], Session],
    user_account_id: str,
) -> str:
    with session_factory() as session:
        row = session.execute(
            select(UserAccountProxyBindingModel, ProxyInventoryModel)
            .join(
                ProxyInventoryModel,
                ProxyInventoryModel.id == UserAccountProxyBindingModel.proxy_id,
            )
            .where(
                UserAccountProxyBindingModel.user_account_id == user_account_id,
                UserAccountProxyBindingModel.bind_status == "active",
            )
            .limit(1)
        ).first()
        if row is None:
            return ""
        _, proxy = row
        return proxy.id


def _wait_for_submit_barrier(
    *,
    barrier_key: str,
    expected: int,
    timeout_s: float,
    ready: bool,
) -> None:
    if not barrier_key or expected <= 1:
        return
    with _SUBMIT_BARRIERS_LOCK:
        state = _SUBMIT_BARRIERS.get(barrier_key)
        if state is None or state.barrier.parties != expected or state.barrier.broken:
            state = _SubmitBarrierState(barrier=Barrier(expected), lock=Lock())
            _SUBMIT_BARRIERS[barrier_key] = state
    with state.lock:
        if ready:
            state.ready_count += 1
        else:
            state.skipped_count += 1
    try:
        state.barrier.wait(timeout=max(1.0, float(timeout_s or 0)))
    except BrokenBarrierError as exc:
        with _SUBMIT_BARRIERS_LOCK:
            if _SUBMIT_BARRIERS.get(barrier_key) is state:
                _SUBMIT_BARRIERS.pop(barrier_key, None)
        raise TimeoutError(
            "session OTP submit memory barrier timeout: "
            f"key={barrier_key} expected={expected} "
            f"ready={state.ready_count} skipped={state.skipped_count}"
        ) from exc
    finally:
        with _SUBMIT_BARRIERS_LOCK:
            if _SUBMIT_BARRIERS.get(barrier_key) is state and (
                state.barrier.broken or state.barrier.n_waiting == 0
            ):
                _SUBMIT_BARRIERS.pop(barrier_key, None)
