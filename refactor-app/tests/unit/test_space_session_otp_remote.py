from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import httpx

from refactor_app.application.workflows.space_session_otp_remote import (
    RemoteSessionOtpCandidate,
    SessionOtpExecutorClient,
    _prepare_remote_batch,
    _write_terminal_results,
)
from refactor_app.infrastructure.db.models import AccountSessionOtpSnapshotModel


class _SnapshotSession:
    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows = rows
        self.commits = 0

    def __enter__(self) -> _SnapshotSession:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None

    def get(self, model: type, row_id: str):
        assert model is AccountSessionOtpSnapshotModel
        return self.rows.get(row_id)

    def commit(self) -> None:
        self.commits += 1


def _candidate(
    snapshot_id: str,
    email: str,
    updated_at: datetime,
    *,
    proxy: str = "http://user:pass@proxy.example:8080",
) -> RemoteSessionOtpCandidate:
    return RemoteSessionOtpCandidate(
        snapshot_id=snapshot_id,
        user_account_id=f"account-{snapshot_id}",
        email=email,
        snapshot_json={
            "phase": "otp_collected",
            "email": email,
            "otp_code": "123456",
            "proxy": proxy,
        },
        snapshot_updated_at=updated_at,
    )


def _row(candidate: RemoteSessionOtpCandidate) -> SimpleNamespace:
    return SimpleNamespace(
        id=candidate.snapshot_id,
        user_account_id=candidate.user_account_id,
        snapshot_status="otp_collected",
        snapshot_json=dict(candidate.snapshot_json),
        otp_code_len=6,
        last_error_code="",
        last_error_message="",
        submitted_at=None,
        updated_at=candidate.snapshot_updated_at,
    )


def test_executor_client_submits_polls_and_keeps_exact_request_contract() -> None:
    requests: list[httpx.Request] = []
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-key"
        if request.method == "POST":
            payload = json.loads(request.content)
            assert payload == {
                "items": [
                    {
                        "item_id": "snapshot-1",
                        "email": "one@example.test",
                        "proxy_url": "http://proxy.example:8080",
                        "snapshot": {"otp_code": "123456"},
                    }
                ],
                "barrier_timeout_s": 120.0,
            }
            return httpx.Response(202, json={"batch_id": "batch-1", "status": "queued"})
        poll_count += 1
        if poll_count == 1:
            return httpx.Response(200, json={"batch_id": "batch-1", "status": "running"})
        return httpx.Response(
            200,
            json={
                "batch_id": "batch-1",
                "status": "succeeded",
                "results": [],
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = SessionOtpExecutorClient(
        base_url="http://executor.example",
        api_key="test-key",
        http_client=http_client,
    )
    submitted = client.create_batch(
        items=[
            {
                "item_id": "snapshot-1",
                "email": "one@example.test",
                "proxy_url": "http://proxy.example:8080",
                "snapshot": {"otp_code": "123456"},
            }
        ]
    )
    terminal = client.wait_for_terminal(
        batch_id=submitted["batch_id"],
        poll_interval_s=0.001,
        poll_timeout_s=1,
    )

    assert terminal["status"] == "succeeded"
    assert [request.method for request in requests] == ["POST", "GET", "GET"]


def test_prepare_remote_batch_rejects_duplicate_email_and_missing_proxy_per_item() -> None:
    now = datetime.now(UTC)
    valid = _candidate("snapshot-valid", "Same@example.test", now)
    duplicate = _candidate("snapshot-duplicate", "same@example.test", now)
    missing_proxy = _candidate("snapshot-no-proxy", "other@example.test", now, proxy="")

    prepared = _prepare_remote_batch([valid, duplicate, missing_proxy])

    assert [item["item_id"] for item in prepared.items] == ["snapshot-valid"]
    assert [failure.error_code for failure in prepared.local_failures] == [
        "DuplicateEmail",
        "InvalidSnapshotProxy",
    ]


def test_prepare_remote_batch_skips_missing_otp_without_local_failure() -> None:
    now = datetime.now(UTC)
    missing_otp = _candidate("snapshot-no-otp", "missing@example.test", now)
    missing_otp.snapshot_json["otp_code"] = ""

    prepared = _prepare_remote_batch([missing_otp])

    assert prepared.items == ()
    assert prepared.local_failures == ()
    assert [candidate.snapshot_id for candidate in prepared.local_skips] == [
        "snapshot-no-otp"
    ]


def test_terminal_results_update_success_failure_and_local_rejection() -> None:
    now = datetime.now(UTC)
    succeeded = _candidate("snapshot-success", "success@example.test", now)
    failed = _candidate("snapshot-failed", "failed@example.test", now)
    invalid = _candidate("snapshot-invalid", "invalid@example.test", now, proxy="")
    prepared = _prepare_remote_batch([succeeded, failed, invalid])
    rows = {
        candidate.snapshot_id: _row(candidate)
        for candidate in (succeeded, failed, invalid)
    }
    session = _SnapshotSession(rows)

    summary = _write_terminal_results(
        session_factory=cast(Any, lambda: session),
        prepared=prepared,
        batch_id="batch-1",
        remote_results=(
            {
                "item_id": succeeded.snapshot_id,
                "status": "succeeded",
                "snapshot_patch": {
                    "phase": "otp_validated",
                    "otp_code": "",
                    "continue_url": "https://auth.openai.com/authorize/continue",
                },
            },
            {
                "item_id": failed.snapshot_id,
                "status": "failed",
                "stage": "request",
                "http_status": 403,
                "error_type": "SessionOtpValidateError",
                "error_message": "OTP validate failed",
            },
        ),
    )

    assert summary == {
        "succeeded_count": 1,
        "failed_count": 2,
        "remote_skipped_count": 0,
        "stale_count": 0,
    }
    assert rows[succeeded.snapshot_id].snapshot_status == "otp_validated"
    assert rows[succeeded.snapshot_id].snapshot_json["otp_code"] == ""
    assert rows[succeeded.snapshot_id].submitted_at is not None
    assert rows[failed.snapshot_id].snapshot_status == "failed"
    assert rows[failed.snapshot_id].last_error_code == "SessionOtpValidateError"
    assert "http_status=403" in rows[failed.snapshot_id].last_error_message
    assert rows[invalid.snapshot_id].snapshot_status == "failed"
    assert rows[invalid.snapshot_id].last_error_code == "InvalidSnapshotProxy"
    assert session.commits == 1


def test_writeback_does_not_overwrite_snapshot_updated_while_remote_batch_runs() -> None:
    captured_at = datetime.now(UTC)
    candidate = _candidate("snapshot-stale", "stale@example.test", captured_at)
    prepared = _prepare_remote_batch([candidate])
    row = _row(candidate)
    row.updated_at = captured_at + timedelta(seconds=1)
    session = _SnapshotSession({candidate.snapshot_id: row})

    summary = _write_terminal_results(
        session_factory=cast(Any, lambda: session),
        prepared=prepared,
        batch_id="batch-stale",
        remote_results=(
            {
                "item_id": candidate.snapshot_id,
                "status": "succeeded",
                "snapshot_patch": {"phase": "otp_validated", "otp_code": ""},
            },
        ),
    )

    assert summary["stale_count"] == 1
    assert summary["succeeded_count"] == 0
    assert row.snapshot_status == "otp_collected"
    assert row.snapshot_json["otp_code"] == "123456"
