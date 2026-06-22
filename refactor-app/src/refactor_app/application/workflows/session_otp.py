from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Condition
from time import monotonic
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import ensure_account_proxy_url
from refactor_app.infrastructure.db.models import (
    AccountSessionOtpSnapshotModel,
    JobStepModel,
    MembershipModel,
    UserAccountAuthModel,
    UserAccountModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.session_login import (
    prepare_chatgpt_session_otp,
    submit_prepared_chatgpt_session_otp,
)


class SessionOtpWorkflowError(RuntimeError):
    pass


SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class SessionOtpAccountContext:
    user_account_id: str
    email: str
    password: str
    membership_id: str


@dataclass(frozen=True)
class SessionOtpSnapshotContext:
    user_account_id: str
    membership_id: str
    snapshot_json: dict


_SUBMIT_GATES: dict[tuple[str, str], "_SubmitGate"] = {}


class PrepareSessionOtpWorkflow:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, *, membership_id: str, run_id: str = "") -> str:
        event_writer = _event_writer(self._session_factory, run_id)
        step_id = _start_step(self._session_factory, run_id, "session_otp_prepare")
        try:
            ctx = _load_account_context(self._session_factory, membership_id)
            proxy_url = ensure_account_proxy_url(
                self._session_factory,
                ctx.user_account_id,
                bind_reason="session_otp.prepare",
                event_writer=event_writer,
            )
            result = prepare_chatgpt_session_otp(
                email=ctx.email,
                password=ctx.password,
                proxy=proxy_url,
                mail_provider=self._mail_provider,
            )
            status = _snapshot_status(result.snapshot, default="otp_pending")
            _upsert_snapshot(
                self._session_factory,
                user_account_id=ctx.user_account_id,
                membership_id=ctx.membership_id,
                snapshot=result.snapshot,
                status=status,
            )
            _finish_step(self._session_factory, step_id, "succeeded", {"status": status})
            return ctx.user_account_id
        except Exception as exc:
            _mark_snapshot_failed(self._session_factory, membership_id, type(exc).__name__, str(exc))
            _finish_step(
                self._session_factory,
                step_id,
                "failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            raise


class SubmitSessionOtpWorkflow:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(
        self,
        *,
        membership_id: str,
        barrier_key: str = "",
        barrier_group: str = "",
        barrier_expected: int = 0,
        barrier_timeout_s: float = 120,
        run_id: str = "",
    ) -> str:
        step_id = _start_step(self._session_factory, run_id, "session_otp_submit")
        try:
            ctx = _load_snapshot_context(self._session_factory, membership_id)
            proxy_url = ensure_account_proxy_url(
                self._session_factory,
                ctx.user_account_id,
                bind_reason="session_otp.submit",
            )

            def before_validate(_email: str = "") -> None:
                if barrier_key and barrier_group and barrier_expected > 1:
                    stats = _wait_on_submit_barrier(
                        barrier_key=barrier_key,
                        barrier_group=barrier_group,
                        expected=barrier_expected,
                        timeout_s=barrier_timeout_s,
                    )
                    if run_id:
                        with self._session_factory() as session:
                            EventWriter(session).write(
                                run_id=run_id,
                                event_type="session_otp.submit_barrier_released",
                                message="session otp submit barrier released before validate request",
                                data_json=stats,
                            )
                            session.commit()

            result = submit_prepared_chatgpt_session_otp(
                snapshot=ctx.snapshot_json,
                proxy=proxy_url,
                mail_provider=self._mail_provider,
                before_validate=before_validate,
            )
            status = _snapshot_status(result.snapshot, default="submitted")
            _upsert_snapshot(
                self._session_factory,
                user_account_id=ctx.user_account_id,
                membership_id=ctx.membership_id,
                snapshot=result.snapshot,
                status=status,
                submitted=True,
            )
            _finish_step(self._session_factory, step_id, "succeeded", {"status": status})
            return ctx.user_account_id
        except Exception as exc:
            _record_submit_barrier_failure(barrier_key, barrier_group)
            _mark_snapshot_failed(self._session_factory, membership_id, type(exc).__name__, str(exc))
            _finish_step(
                self._session_factory,
                step_id,
                "failed",
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            raise


def _load_account_context(session_factory: SessionFactory, membership_id: str) -> SessionOtpAccountContext:
    with session_factory() as session:
        membership = session.get(MembershipModel, membership_id)
        if membership is None:
            raise SessionOtpWorkflowError(f"membership not found: {membership_id}")
        account = session.get(UserAccountModel, membership.user_account_id)
        if account is None:
            raise SessionOtpWorkflowError(f"user account not found: {membership.user_account_id}")
        auth = session.get(UserAccountAuthModel, membership.user_account_id)
        if auth is None:
            raise SessionOtpWorkflowError("missing_auth_row")
        if not auth.password:
            raise SessionOtpWorkflowError("missing_password")
        return SessionOtpAccountContext(
            user_account_id=account.id,
            email=account.email,
            password=auth.password,
            membership_id=membership.id,
        )


def _load_snapshot_context(session_factory: SessionFactory, membership_id: str) -> SessionOtpSnapshotContext:
    with session_factory() as session:
        membership = session.get(MembershipModel, membership_id)
        if membership is None:
            raise SessionOtpWorkflowError(f"membership not found: {membership_id}")
        snapshot = (
            session.query(AccountSessionOtpSnapshotModel)
            .filter_by(user_account_id=membership.user_account_id)
            .one_or_none()
        )
        if snapshot is None:
            raise SessionOtpWorkflowError("missing_otp_snapshot")
        return SessionOtpSnapshotContext(
            user_account_id=membership.user_account_id,
            membership_id=membership.id,
            snapshot_json=dict(snapshot.snapshot_json),
        )


def _upsert_snapshot(
    session_factory: SessionFactory,
    *,
    user_account_id: str,
    membership_id: str,
    snapshot: dict,
    status: str,
    submitted: bool = False,
) -> None:
    now = datetime.now(UTC)
    otp_code = str(snapshot.get("otp_code") or snapshot.get("otp") or "").strip()
    with session_factory() as session:
        row = (
            session.query(AccountSessionOtpSnapshotModel)
            .filter_by(user_account_id=user_account_id)
            .one_or_none()
        )
        if row is None:
            row = AccountSessionOtpSnapshotModel(
                id=f"session-otp-snapshot-{uuid4()}",
                user_account_id=user_account_id,
                source_membership_id=membership_id,
                snapshot_status=status,
                snapshot_json=snapshot,
                otp_code_len=len(otp_code),
                prepared_at=now,
                submitted_at=now if submitted else None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.source_membership_id = membership_id
            row.snapshot_status = status
            row.snapshot_json = snapshot
            row.otp_code_len = len(otp_code)
            row.last_error_code = ""
            row.last_error_message = ""
            if row.prepared_at is None:
                row.prepared_at = now
            if submitted:
                row.submitted_at = now
            row.updated_at = now
        session.commit()


def _mark_snapshot_failed(
    session_factory: SessionFactory,
    membership_id: str,
    code: str,
    message: str,
) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        membership = session.get(MembershipModel, membership_id)
        if membership is None:
            return
        row = (
            session.query(AccountSessionOtpSnapshotModel)
            .filter_by(user_account_id=membership.user_account_id)
            .one_or_none()
        )
        if row is None:
            row = AccountSessionOtpSnapshotModel(
                id=f"session-otp-snapshot-{uuid4()}",
                user_account_id=membership.user_account_id,
                source_membership_id=membership.id,
                snapshot_status="failed",
                snapshot_json={},
                otp_code_len=0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        row.snapshot_status = "failed"
        row.last_error_code = code[:200]
        row.last_error_message = message[:1000]
        row.updated_at = now
        session.commit()


def _snapshot_status(snapshot: dict, *, default: str) -> str:
    phase = str(snapshot.get("phase") or "").strip()
    if phase in {"otp_collected", "otp_pending", "otp_validated", "otp_missing", "failed"}:
        return phase
    if default == "submitted":
        return "otp_validated" if bool(snapshot.get("ok")) else "otp_missing"
    return "otp_collected" if bool(snapshot.get("otp_code") or snapshot.get("otp")) else "otp_pending"


class _SubmitGate:
    def __init__(self, expected: int) -> None:
        self.expected = max(1, expected)
        self.arrived = 0
        self.failed_before_arrival = 0
        self.released = False
        self.condition = Condition()

    def wait(self, timeout_s: float) -> dict:
        deadline = monotonic() + timeout_s
        with self.condition:
            self.arrived += 1
            if self.arrived + self.failed_before_arrival >= self.expected:
                self.released = True
                self.condition.notify_all()
            while not self.released:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f"session otp submit barrier timeout: "
                        f"arrived={self.arrived} expected={self.expected}"
                    )
                self.condition.wait(timeout=remaining)
            return {
                "arrived": self.arrived,
                "failed_before_arrival": self.failed_before_arrival,
                "expected": self.expected,
            }

    def record_failure(self) -> None:
        with self.condition:
            self.failed_before_arrival += 1
            if self.arrived + self.failed_before_arrival >= self.expected:
                self.released = True
                self.condition.notify_all()


def _wait_on_submit_barrier(
    *,
    barrier_key: str,
    barrier_group: str,
    expected: int,
    timeout_s: float,
) -> dict:
    key = (barrier_key, barrier_group)
    gate = _SUBMIT_GATES.get(key)
    if gate is None:
        gate = _SubmitGate(expected)
        _SUBMIT_GATES[key] = gate
    try:
        return gate.wait(timeout_s)
    finally:
        if gate.released:
            _SUBMIT_GATES.pop(key, None)


def _record_submit_barrier_failure(barrier_key: str, barrier_group: str) -> None:
    if not barrier_key or not barrier_group:
        return
    gate = _SUBMIT_GATES.get((barrier_key, barrier_group))
    if gate is not None:
        gate.record_failure()


def _event_writer(session_factory: SessionFactory, run_id: str):
    if not run_id:
        return None

    def write(event_type: str, message: str, data_json: dict, level: str = "INFO") -> None:
        with session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=event_type,
                message=message,
                level=level,
                data_json=data_json,
            )
            session.commit()

    return write


def _start_step(session_factory: SessionFactory, run_id: str, name: str) -> str:
    if not run_id:
        return ""
    now = datetime.now(UTC)
    step_id = str(uuid4())
    with session_factory() as session:
        session.add(
            JobStepModel(
                id=step_id,
                run_id=run_id,
                name=name,
                step_status="running",
                attempt=1,
                started_at=now,
                input_json={},
                output_json={},
            )
        )
        session.commit()
    return step_id


def _finish_step(
    session_factory: SessionFactory,
    step_id: str,
    status: str,
    output_json: dict | None = None,
    error_code: str = "",
    error_message: str = "",
) -> None:
    if not step_id:
        return
    with session_factory() as session:
        step = session.get(JobStepModel, step_id)
        if step is None:
            return
        step.step_status = status
        step.finished_at = datetime.now(UTC)
        step.output_json = output_json or {}
        step.error_code = error_code[:200]
        step.error_message = error_message[:1000]
        session.commit()
