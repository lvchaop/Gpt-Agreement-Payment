from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from refactor_app.infrastructure.db.models import (
    AccountSessionOtpSnapshotModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
)

MAX_REMOTE_SESSION_OTP_BATCH_SIZE = 1000
_TERMINAL_BATCH_STATUSES = {"succeeded", "partial", "failed"}
_ALLOWED_PROXY_SCHEMES = {"http", "https", "socks4", "socks5", "socks5h"}


class RemoteSessionOtpBridgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteSessionOtpCandidate:
    snapshot_id: str
    user_account_id: str
    email: str
    snapshot_json: dict[str, Any]
    snapshot_updated_at: datetime


@dataclass(frozen=True)
class RemoteSessionOtpSelection:
    space_ids: tuple[str, ...]
    eligible_count: int
    candidates: tuple[RemoteSessionOtpCandidate, ...]

    @property
    def space_id(self) -> str:
        return self.space_ids[0]

    @property
    def remaining_count(self) -> int:
        return max(0, self.eligible_count - len(self.candidates))


@dataclass(frozen=True)
class _LocalCandidateFailure:
    candidate: RemoteSessionOtpCandidate
    error_code: str
    error_message: str


@dataclass(frozen=True)
class _PreparedRemoteBatch:
    candidates: tuple[RemoteSessionOtpCandidate, ...]
    items: tuple[dict[str, Any], ...]
    local_failures: tuple[_LocalCandidateFailure, ...]
    local_skips: tuple[RemoteSessionOtpCandidate, ...]


class SessionOtpExecutorClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        request_timeout_s: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        normalized_base_url = str(base_url or "").strip().rstrip("/")
        normalized_api_key = str(api_key or "").strip()
        if not normalized_base_url:
            raise RemoteSessionOtpBridgeError("session OTP executor base URL is not configured")
        if not normalized_api_key:
            raise RemoteSessionOtpBridgeError("INVITE_EXECUTOR_API_KEY is not configured")
        if request_timeout_s <= 0:
            raise ValueError("request_timeout_s must be greater than zero")

        self._base_url = normalized_base_url
        self._authorization = f"Bearer {normalized_api_key}"
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(
            base_url=normalized_base_url,
            timeout=httpx.Timeout(request_timeout_s),
            trust_env=False,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> SessionOtpExecutorClient:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()

    def create_batch(
        self,
        *,
        items: Sequence[dict[str, Any]],
        barrier_timeout_s: float = 120.0,
    ) -> dict[str, Any]:
        if not 1 <= len(items) <= MAX_REMOTE_SESSION_OTP_BATCH_SIZE:
            raise ValueError(
                "session OTP remote batch size must be between 1 and "
                f"{MAX_REMOTE_SESSION_OTP_BATCH_SIZE}"
            )
        response = self._request(
            "POST",
            "/v1/session-otp-submit-batches",
            json={"items": list(items), "barrier_timeout_s": barrier_timeout_s},
        )
        return self._decode_batch(response)

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        normalized_batch_id = str(batch_id or "").strip()
        if not normalized_batch_id:
            raise ValueError("batch_id is required")
        response = self._request(
            "GET",
            f"/v1/session-otp-submit-batches/{normalized_batch_id}",
        )
        batch = self._decode_batch(response)
        if batch["batch_id"] != normalized_batch_id:
            raise RemoteSessionOtpBridgeError("remote executor returned a different batch_id")
        return batch

    def wait_for_terminal(
        self,
        *,
        batch_id: str,
        poll_interval_s: float = 0.5,
        poll_timeout_s: float = 900.0,
    ) -> dict[str, Any]:
        if poll_interval_s <= 0:
            raise ValueError("poll_interval_s must be greater than zero")
        if poll_timeout_s <= 0:
            raise ValueError("poll_timeout_s must be greater than zero")

        deadline = time.monotonic() + poll_timeout_s
        while True:
            batch = self.get_batch(batch_id)
            if batch["status"] in _TERMINAL_BATCH_STATUSES:
                return batch
            if time.monotonic() >= deadline:
                raise RemoteSessionOtpBridgeError(
                    f"remote session OTP batch polling timed out: batch_id={batch_id}"
                )
            time.sleep(min(poll_interval_s, max(0.0, deadline - time.monotonic())))

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("Authorization", self._authorization)
        try:
            response = self._client.request(
                method,
                f"{self._base_url}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise RemoteSessionOtpBridgeError(
                f"remote executor request failed: {type(exc).__name__}: {exc}"
            ) from exc
        if response.is_error:
            detail = _safe_error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise RemoteSessionOtpBridgeError(
                f"remote executor returned HTTP {response.status_code}{suffix}"
            )
        return response

    @staticmethod
    def _decode_batch(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RemoteSessionOtpBridgeError("remote executor returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteSessionOtpBridgeError("remote executor returned a non-object payload")
        batch_id = str(payload.get("batch_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not batch_id:
            raise RemoteSessionOtpBridgeError("remote executor response has no batch_id")
        if status not in {"queued", "running", *_TERMINAL_BATCH_STATUSES}:
            raise RemoteSessionOtpBridgeError(
                f"remote executor returned unsupported batch status: {status or '(empty)'}"
            )
        return payload


def select_remote_session_otp_candidates(
    *,
    session: Session,
    space_id: str = "",
    space_ids: Sequence[str] = (),
    user_account_ids: Sequence[str] = (),
    limit: int = MAX_REMOTE_SESSION_OTP_BATCH_SIZE,
) -> RemoteSessionOtpSelection:
    normalized_space_ids = _active_space_ids(
        session=session,
        space_id=space_id,
        space_ids=space_ids,
    )
    normalized_user_account_ids = tuple(
        dict.fromkeys(
            item
            for item in (str(candidate or "").strip() for candidate in user_account_ids)
            if item
        )
    )
    if not 1 <= limit <= MAX_REMOTE_SESSION_OTP_BATCH_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_REMOTE_SESSION_OTP_BATCH_SIZE}")

    conditions: list[ColumnElement[bool]] = [
        SpaceMembershipModel.space_id.in_(normalized_space_ids),
        SpaceMembershipModel.membership_status == "active",
        UserAccountModel.account_status == "active",
        func.length(func.trim(UserAccountModel.email)) > 0,
        AccountSessionOtpSnapshotModel.snapshot_status == "otp_collected",
        remote_session_otp_code_available_condition(),
    ]
    if normalized_user_account_ids:
        conditions.append(UserAccountModel.id.in_(normalized_user_account_ids))
    rows = session.execute(
        select(
            SpaceMembershipModel,
            UserAccountModel,
            AccountSessionOtpSnapshotModel,
        )
        .select_from(SpaceMembershipModel)
        .join(
            UserAccountModel,
            UserAccountModel.id == SpaceMembershipModel.user_account_id,
        )
        .join(
            AccountSessionOtpSnapshotModel,
            AccountSessionOtpSnapshotModel.user_account_id == UserAccountModel.id,
        )
        .where(*conditions)
    ).all()
    space_rank = {item: index for index, item in enumerate(normalized_space_ids)}
    account_rank = {
        item: index for index, item in enumerate(normalized_user_account_ids)
    }
    ordered_rows = sorted(
        rows,
        key=lambda row: (
            account_rank.get(row[1].id, len(account_rank))
            if account_rank
            else space_rank[row[0].space_id],
            space_rank[row[0].space_id],
            row[0].created_at,
            row[0].id,
        ),
    )
    unique_rows: list[
        tuple[SpaceMembershipModel, UserAccountModel, AccountSessionOtpSnapshotModel]
    ] = []
    seen_account_ids: set[str] = set()
    for membership, account, snapshot in ordered_rows:
        if account.id in seen_account_ids:
            continue
        seen_account_ids.add(account.id)
        unique_rows.append((membership, account, snapshot))
    return RemoteSessionOtpSelection(
        space_ids=normalized_space_ids,
        eligible_count=len(unique_rows),
        candidates=tuple(
            RemoteSessionOtpCandidate(
                snapshot_id=snapshot.id,
                user_account_id=account.id,
                email=account.email.strip(),
                snapshot_json=dict(snapshot.snapshot_json or {}),
                snapshot_updated_at=snapshot.updated_at,
            )
            for _, account, snapshot in unique_rows[:limit]
        ),
    )


def run_remote_space_session_otp_submit(
    *,
    session_factory: Callable[[], Session],
    space_id: str = "",
    space_ids: Sequence[str] = (),
    user_account_ids: Sequence[str] = (),
    client: SessionOtpExecutorClient | None,
    dry_run: bool = False,
    poll_interval_s: float = 0.5,
    poll_timeout_s: float = 900.0,
    barrier_timeout_s: float = 120.0,
    on_submitted: Callable[[str, int], None] | None = None,
) -> dict[str, Any]:
    with session_factory() as session:
        selection = select_remote_session_otp_candidates(
            session=session,
            space_id=space_id,
            space_ids=space_ids,
            user_account_ids=user_account_ids,
        )
    prepared = _prepare_remote_batch(selection.candidates)
    base_summary: dict[str, Any] = {
        "space_id": selection.space_id,
        "space_ids": list(selection.space_ids),
        "eligible_count": selection.eligible_count,
        "selected_count": len(selection.candidates),
        "remaining_count": selection.remaining_count,
        "submitted_count": len(prepared.items),
        "local_rejected_count": len(prepared.local_failures),
        "local_skipped_count": len(prepared.local_skips),
    }
    if dry_run:
        return {**base_summary, "status": "dry_run", "batch_id": ""}
    if not selection.candidates:
        return {**base_summary, "status": "no_candidates", "batch_id": ""}
    if client is None:
        raise RemoteSessionOtpBridgeError("remote executor client is required")

    if not prepared.items:
        writeback = _write_terminal_results(
            session_factory=session_factory,
            prepared=prepared,
            batch_id="",
            remote_results=(),
        )
        return {
            **base_summary,
            "status": "failed" if prepared.local_failures else "no_candidates",
            "batch_id": "",
            **writeback,
        }

    submitted = client.create_batch(
        items=prepared.items,
        barrier_timeout_s=barrier_timeout_s,
    )
    batch_id = str(submitted["batch_id"])
    if on_submitted is not None:
        on_submitted(batch_id, len(prepared.items))
    terminal = (
        submitted
        if submitted["status"] in _TERMINAL_BATCH_STATUSES
        else client.wait_for_terminal(
            batch_id=batch_id,
            poll_interval_s=poll_interval_s,
            poll_timeout_s=poll_timeout_s,
        )
    )
    remote_results = _validated_terminal_results(
        terminal=terminal,
        batch_id=batch_id,
        candidates=prepared.candidates,
    )
    writeback = _write_terminal_results(
        session_factory=session_factory,
        prepared=prepared,
        batch_id=batch_id,
        remote_results=remote_results,
    )
    overall_status = str(terminal["status"])
    if writeback["failed_count"] or writeback["stale_count"]:
        overall_status = "partial" if writeback["succeeded_count"] else "failed"
    return {
        **base_summary,
        "status": overall_status,
        "remote_status": str(terminal["status"]),
        "batch_id": batch_id,
        **writeback,
    }


def _active_space_ids(
    *,
    session: Session,
    space_id: str = "",
    space_ids: Sequence[str] = (),
) -> tuple[str, ...]:
    normalized_space_ids = tuple(
        dict.fromkeys(
            item
            for item in (
                str(candidate or "").strip()
                for candidate in (*space_ids, space_id)
            )
            if item
        )
    )
    if not normalized_space_ids:
        raise RemoteSessionOtpBridgeError("at least one space_id is required")
    spaces_by_id = {
        space.id: space
        for space in session.scalars(
            select(SpaceModel).where(SpaceModel.id.in_(normalized_space_ids))
        ).all()
    }
    for normalized_space_id in normalized_space_ids:
        space = spaces_by_id.get(normalized_space_id)
        if space is None:
            raise RemoteSessionOtpBridgeError(f"space not found: {normalized_space_id}")
        if space.space_status != "active":
            raise RemoteSessionOtpBridgeError(f"space is not active: {normalized_space_id}")
    return normalized_space_ids


def _prepare_remote_batch(
    candidates: Sequence[RemoteSessionOtpCandidate],
) -> _PreparedRemoteBatch:
    valid_candidates: list[RemoteSessionOtpCandidate] = []
    items: list[dict[str, Any]] = []
    failures: list[_LocalCandidateFailure] = []
    skips: list[RemoteSessionOtpCandidate] = []
    seen_emails: set[str] = set()
    for candidate in candidates:
        snapshot = dict(candidate.snapshot_json)
        if not snapshot:
            failures.append(
                _LocalCandidateFailure(
                    candidate=candidate,
                    error_code="EmptySnapshot",
                    error_message="session OTP snapshot payload is empty",
                )
            )
            continue
        otp_code = str(snapshot.get("otp_code") or "").strip()
        if not otp_code:
            skips.append(candidate)
            continue
        snapshot["otp_code"] = otp_code

        email_key = candidate.email.casefold()
        if email_key in seen_emails:
            failures.append(
                _LocalCandidateFailure(
                    candidate=candidate,
                    error_code="DuplicateEmail",
                    error_message="another selected account has the same email",
                )
            )
            continue
        seen_emails.add(email_key)

        proxy_url = str(snapshot.get("proxy") or "").strip()
        proxy_error = _proxy_validation_error(proxy_url)
        if proxy_error:
            failures.append(
                _LocalCandidateFailure(
                    candidate=candidate,
                    error_code="InvalidSnapshotProxy",
                    error_message=proxy_error,
                )
            )
            continue
        valid_candidates.append(candidate)
        items.append(
            {
                "item_id": candidate.snapshot_id,
                "email": candidate.email,
                "proxy_url": proxy_url,
                "snapshot": snapshot,
            }
        )
    return _PreparedRemoteBatch(
        candidates=tuple(valid_candidates),
        items=tuple(items),
        local_failures=tuple(failures),
        local_skips=tuple(skips),
    )


def remote_session_otp_code_available_condition() -> ColumnElement[bool]:
    otp_code = func.coalesce(
        AccountSessionOtpSnapshotModel.snapshot_json["otp_code"].astext,
        "",
    )
    return and_(
        AccountSessionOtpSnapshotModel.otp_code_len > 0,
        func.length(func.trim(otp_code)) > 0,
    )


def _validated_terminal_results(
    *,
    terminal: dict[str, Any],
    batch_id: str,
    candidates: Sequence[RemoteSessionOtpCandidate],
) -> tuple[dict[str, Any], ...]:
    if terminal.get("batch_id") != batch_id:
        raise RemoteSessionOtpBridgeError("terminal response batch_id does not match submission")
    if terminal.get("status") not in _TERMINAL_BATCH_STATUSES:
        raise RemoteSessionOtpBridgeError("remote session OTP batch is not terminal")
    raw_results = terminal.get("results")
    if not isinstance(raw_results, list):
        raise RemoteSessionOtpBridgeError("terminal response has no results list")

    expected_ids = {candidate.snapshot_id for candidate in candidates}
    results_by_id: dict[str, dict[str, Any]] = {}
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            raise RemoteSessionOtpBridgeError("terminal response contains a non-object result")
        item_id = str(raw_result.get("item_id") or "").strip()
        if not item_id or item_id in results_by_id:
            raise RemoteSessionOtpBridgeError(
                "terminal response contains a missing/duplicate item_id"
            )
        if item_id not in expected_ids:
            raise RemoteSessionOtpBridgeError(
                f"terminal response contains unknown item_id: {item_id}"
            )
        status = str(raw_result.get("status") or "")
        if status not in {"succeeded", "failed", "skipped"}:
            raise RemoteSessionOtpBridgeError(
                f"terminal response contains unsupported item status: {status or '(empty)'}"
            )
        if status == "succeeded":
            patch = raw_result.get("snapshot_patch")
            if not isinstance(patch, dict) or patch.get("phase") != "otp_validated":
                raise RemoteSessionOtpBridgeError(
                    f"successful result has invalid snapshot_patch: {item_id}"
                )
        results_by_id[item_id] = raw_result
    if set(results_by_id) != expected_ids:
        missing = sorted(expected_ids - set(results_by_id))
        raise RemoteSessionOtpBridgeError(
            f"terminal response is missing {len(missing)} result(s)"
        )
    return tuple(results_by_id[candidate.snapshot_id] for candidate in candidates)


def _write_terminal_results(
    *,
    session_factory: Callable[[], Session],
    prepared: _PreparedRemoteBatch,
    batch_id: str,
    remote_results: Sequence[dict[str, Any]],
) -> dict[str, int]:
    succeeded_count = 0
    failed_count = 0
    remote_skipped_count = 0
    stale_count = 0
    now = datetime.now(UTC)
    with session_factory() as session:
        for failure in prepared.local_failures:
            row = _current_snapshot(session, failure.candidate)
            if row is None:
                stale_count += 1
                continue
            row.snapshot_status = "failed"
            row.last_error_code = failure.error_code[:200]
            row.last_error_message = failure.error_message[:1000]
            row.updated_at = now
            failed_count += 1

        for candidate, result in zip(prepared.candidates, remote_results, strict=True):
            row = _current_snapshot(session, candidate)
            if row is None:
                stale_count += 1
                continue
            result_status = str(result.get("status") or "")
            if result_status == "succeeded":
                merged_snapshot = dict(row.snapshot_json or {})
                merged_snapshot.update(dict(result.get("snapshot_patch") or {}))
                row.snapshot_status = "otp_validated"
                row.snapshot_json = merged_snapshot
                row.otp_code_len = len(str(merged_snapshot.get("otp_code") or ""))
                row.last_error_code = ""
                row.last_error_message = ""
                row.submitted_at = now
                row.updated_at = now
                succeeded_count += 1
                continue

            error_code = str(result.get("error_type") or "RemoteSessionOtpSubmitFailed")
            error_message = str(result.get("error_message") or "remote OTP submit failed")
            stage = str(result.get("stage") or "")
            http_status = int(result.get("http_status") or 0)
            context = " ".join(
                part
                for part in (
                    f"batch_id={batch_id}" if batch_id else "",
                    f"stage={stage}" if stage else "",
                    f"http_status={http_status}" if http_status else "",
                )
                if part
            )
            row.snapshot_status = "failed"
            row.last_error_code = error_code[:200]
            row.last_error_message = f"{context} {error_message}".strip()[:1000]
            row.updated_at = now
            failed_count += 1
            if result_status == "skipped":
                remote_skipped_count += 1
        session.commit()
    return {
        "succeeded_count": succeeded_count,
        "failed_count": failed_count,
        "remote_skipped_count": remote_skipped_count,
        "stale_count": stale_count,
    }


def _current_snapshot(
    session: Session,
    candidate: RemoteSessionOtpCandidate,
) -> AccountSessionOtpSnapshotModel | None:
    row = session.get(AccountSessionOtpSnapshotModel, candidate.snapshot_id)
    if (
        row is None
        or row.user_account_id != candidate.user_account_id
        or row.snapshot_status != "otp_collected"
        or row.updated_at != candidate.snapshot_updated_at
    ):
        return None
    return row


def _proxy_validation_error(proxy_url: str) -> str:
    if not proxy_url:
        return "session OTP snapshot has no original proxy"
    try:
        parsed = urlsplit(proxy_url)
        port = parsed.port
    except ValueError:
        return "session OTP snapshot proxy URL is invalid"
    if parsed.scheme.lower() not in _ALLOWED_PROXY_SCHEMES:
        return "session OTP snapshot proxy scheme is unsupported"
    if not parsed.hostname or port is None:
        return "session OTP snapshot proxy must include host and port"
    return ""


def _safe_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail[:300]
    if isinstance(detail, dict):
        message = detail.get("message")
        active_type = detail.get("active_batch_type")
        active_id = detail.get("active_batch_id")
        return " ".join(
            str(value).strip()
            for value in (message, active_type, active_id)
            if str(value or "").strip()
        )[:300]
    return ""
