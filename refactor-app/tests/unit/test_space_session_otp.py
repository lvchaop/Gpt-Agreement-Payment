from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, cast

import pytest

from refactor_app.api.routes import resources
from refactor_app.application.jobs import handlers
from refactor_app.application.workflows import space_session_otp
from refactor_app.application.workflows.space_session_otp import (
    SpaceSessionOtpCandidate,
    SpaceSessionOtpWorkflow,
    SpaceSessionOtpWorkflowError,
)
from refactor_app.application.workflows.space_session_otp_remote import (
    RemoteSessionOtpCandidate,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow


class _FakeSession:
    def commit(self) -> None:
        return None


class _FakeWorkQueue:
    enqueued: list[dict[str, Any]] = []

    def __init__(self, _session: Any) -> None:
        pass

    def enqueue(self, **kwargs: Any) -> None:
        self.enqueued.append(kwargs)


def _job_result(**kwargs: Any) -> dict:
    return {
        "job_id": kwargs["job_id"],
        "job_status": "running",
        "run_id": kwargs["run_id"],
        "work_count": kwargs["work_count"],
        "selected_count": kwargs["selected_count"],
        "queued": kwargs["selected_count"],
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }


def test_prepare_job_uses_configured_work_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    candidates = [
        SpaceSessionOtpCandidate(
            space_membership_id=f"membership-{index}",
            user_account_id=f"account-{index}",
        )
        for index in range(3)
    ]
    _FakeWorkQueue.enqueued = []

    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(worker_capacity=1000))
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)
    monkeypatch.setattr(
        resources,
        "select_space_session_otp_prepare_candidates",
        lambda **_: candidates,
    )

    def fake_start_work_job(**kwargs: Any):
        captured.update(kwargs)
        return SimpleNamespace(id="prepare-job"), SimpleNamespace(id="prepare-run")

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", _FakeWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", _job_result)

    result = resources.create_space_session_otp_prepare_job(
        "space-1",
        resources.SpaceSessionOtpPrepareJobRequest(created_by="test", work_count=73),
        cast(Any, _FakeSession()),
    )

    assert captured["job_type"] == "account.session_otp.prepare.bulk"
    assert captured["input_json"] == {
        "space_id": "space-1",
        "space_ids": ["space-1"],
        "work_count": 73,
        "selected_count": 3,
        "user_account_ids": ["account-0", "account-1", "account-2"],
    }
    assert result["work_count"] == 73
    assert len(_FakeWorkQueue.enqueued) == 3


def test_prepare_job_uses_optional_account_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    candidates = [
        SpaceSessionOtpCandidate(
            space_membership_id=f"membership-{index}",
            user_account_id=f"account-{index}",
        )
        for index in range(5)
    ]
    _FakeWorkQueue.enqueued = []

    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(worker_capacity=1000))
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)
    monkeypatch.setattr(
        resources,
        "select_space_session_otp_prepare_candidates",
        lambda **_: candidates,
    )

    def fake_start_work_job(**kwargs: Any):
        captured.update(kwargs)
        return SimpleNamespace(id="prepare-job"), SimpleNamespace(id="prepare-run")

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", _FakeWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", _job_result)

    result = resources.create_space_session_otp_prepare_job(
        "space-1",
        resources.SpaceSessionOtpPrepareJobRequest(
            created_by="test",
            work_count=2,
            account_count=3,
        ),
        cast(Any, _FakeSession()),
    )

    assert captured["input_json"] == {
        "space_id": "space-1",
        "space_ids": ["space-1"],
        "work_count": 2,
        "selected_count": 3,
        "account_count": 3,
        "user_account_ids": ["account-0", "account-1", "account-2"],
    }
    assert result["selected_count"] == 3
    assert [item["input_json"]["user_account_id"] for item in _FakeWorkQueue.enqueued] == [
        "account-0",
        "account-1",
        "account-2",
    ]


def test_multi_space_prepare_job_uses_deduplicated_account_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    selector_input: dict[str, Any] = {}
    candidates = [
        SpaceSessionOtpCandidate(
            space_id="space-2",
            space_membership_id="membership-2",
            user_account_id="account-shared",
        ),
        SpaceSessionOtpCandidate(
            space_id="space-1",
            space_membership_id="membership-1",
            user_account_id="account-unique",
        ),
    ]
    _FakeWorkQueue.enqueued = []
    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(worker_capacity=1000))
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)

    def fake_select(**kwargs: Any):
        selector_input.update(kwargs)
        return candidates

    monkeypatch.setattr(resources, "select_space_session_otp_prepare_candidates", fake_select)

    def fake_start_work_job(**kwargs: Any):
        captured.update(kwargs)
        return SimpleNamespace(id="prepare-job"), SimpleNamespace(id="prepare-run")

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", _FakeWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", _job_result)

    result = resources.create_multi_space_session_otp_prepare_job(
        resources.MultiSpaceSessionOtpPrepareJobRequest(
            space_ids=["space-2", "space-1", "space-2"],
            created_by="test",
            work_count=2,
        ),
        cast(Any, _FakeSession()),
    )

    assert selector_input["space_ids"] == ["space-2", "space-1"]
    assert captured["input_json"]["space_ids"] == ["space-2", "space-1"]
    assert captured["input_json"]["user_account_ids"] == [
        "account-shared",
        "account-unique",
    ]
    assert result["selected_count"] == 2
    assert [item["input_json"]["space_id"] for item in _FakeWorkQueue.enqueued] == [
        "space-2",
        "space-1",
    ]


def test_multi_space_summary_uses_one_deduplicated_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_summary(**kwargs: Any) -> dict:
        captured.update(kwargs)
        return {
            "space_ids": kwargs["space_ids"],
            "space_names": ["Space 2", "Space 1"],
            "prepare_candidate_count": 7,
            "remote_submit_snapshot_count": 3,
        }

    monkeypatch.setattr(resources, "space_session_otp_summary", fake_summary)
    monkeypatch.setattr(resources, "_space_session_otp_active_job_dict", lambda **_: {})
    monkeypatch.setattr(
        resources,
        "get_settings",
        lambda: SimpleNamespace(worker_capacity=2000),
    )

    result = resources.get_multi_space_session_otp_summary(
        resources.MultiSpaceSessionOtpScopeRequest(
            space_ids=["space-2", "space-1", "space-2"],
        ),
        cast(Any, _FakeSession()),
    )

    assert captured["space_ids"] == ["space-2", "space-1"]
    assert result["prepare_candidate_count"] == 7
    assert result["remote_submit_snapshot_count"] == 3
    assert result["worker_capacity"] == 2000


def test_prepare_job_rejects_account_count_above_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [
        SpaceSessionOtpCandidate(
            space_membership_id="membership-1",
            user_account_id="account-1",
        )
    ]
    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(worker_capacity=1000))
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)
    monkeypatch.setattr(
        resources,
        "select_space_session_otp_prepare_candidates",
        lambda **_: candidates,
    )

    with pytest.raises(resources.HTTPException) as exc_info:
        resources.create_space_session_otp_prepare_job(
            "space-1",
            resources.SpaceSessionOtpPrepareJobRequest(work_count=2, account_count=2),
            cast(Any, _FakeSession()),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "message": "prepare account_count exceeds active member count",
        "account_count": 2,
        "active_member_count": 1,
    }


def test_prepare_job_uses_selected_user_account_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    candidates = [
        SpaceSessionOtpCandidate(
            space_membership_id=f"membership-{index}",
            user_account_id=f"account-{index}",
        )
        for index in range(5)
    ]
    _FakeWorkQueue.enqueued = []
    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(worker_capacity=1000))
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)
    monkeypatch.setattr(
        resources,
        "select_space_session_otp_prepare_candidates",
        lambda **_: candidates,
    )

    def fake_start_work_job(**kwargs: Any):
        captured.update(kwargs)
        return SimpleNamespace(id="prepare-job"), SimpleNamespace(id="prepare-run")

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", _FakeWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", _job_result)

    result = resources.create_space_session_otp_prepare_job(
        "space-1",
        resources.SpaceSessionOtpPrepareJobRequest(
            created_by="test",
            work_count=2,
            user_account_ids=["account-3", "account-1", "account-3"],
        ),
        cast(Any, _FakeSession()),
    )

    assert captured["input_json"] == {
        "space_id": "space-1",
        "space_ids": ["space-1"],
        "work_count": 2,
        "selected_count": 2,
        "user_account_ids": ["account-3", "account-1"],
    }
    assert result["selected_count"] == 2
    assert [item["input_json"]["user_account_id"] for item in _FakeWorkQueue.enqueued] == [
        "account-3",
        "account-1",
    ]


def test_submit_job_starts_all_snapshots_with_one_barrier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    candidates = [
        SpaceSessionOtpCandidate(
            space_membership_id=f"membership-{index}",
            user_account_id=f"account-{index}",
            snapshot_id=f"snapshot-{index}",
        )
        for index in range(57)
    ]
    _FakeWorkQueue.enqueued = []

    monkeypatch.setattr(resources, "get_settings", lambda: SimpleNamespace(worker_capacity=1000))
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)
    monkeypatch.setattr(
        resources,
        "select_space_session_otp_submit_candidates",
        lambda **_: candidates,
    )

    def fake_start_work_job(**kwargs: Any):
        captured.update(kwargs)
        return SimpleNamespace(id="submit-job"), SimpleNamespace(id="submit-run")

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", _FakeWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", _job_result)

    result = resources.create_space_session_otp_submit_job(
        "space-1",
        resources.SpaceSessionOtpSubmitJobRequest(created_by="test"),
        cast(Any, _FakeSession()),
    )

    assert captured["job_type"] == "account.session_otp.submit.bulk"
    assert captured["input_json"]["work_count"] == 57
    assert captured["input_json"]["dispatch_mode"] == "all_at_once"
    assert captured["input_json"]["required_slots"] == 57
    assert captured["input_json"]["barrier_expected"] == 57
    assert result["work_count"] == 57
    assert len(_FakeWorkQueue.enqueued) == 57
    inputs = [item["input_json"] for item in _FakeWorkQueue.enqueued]
    assert {item["barrier_key"] for item in inputs} == {"session-otp-submit:submit-job"}
    assert {item["barrier_expected"] for item in inputs} == {57}


def test_multi_space_remote_submit_job_creates_one_bridge_work_for_up_to_1000_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    now = SimpleNamespace()
    candidates = tuple(
        RemoteSessionOtpCandidate(
            snapshot_id=f"snapshot-{index}",
            user_account_id=f"account-{index}",
            email=f"account-{index}@example.test",
            snapshot_json={"otp_code": "123456", "proxy": "http://proxy.test:80"},
            snapshot_updated_at=cast(Any, now),
        )
        for index in range(1000)
    )
    _FakeWorkQueue.enqueued = []
    monkeypatch.setattr(
        resources,
        "get_settings",
        lambda: SimpleNamespace(
            session_otp_executor_base_url="http://executor.test",
            session_otp_executor_api_key="key",
        ),
    )
    monkeypatch.setattr(resources, "_reject_active_space_session_otp_job", lambda **_: None)
    monkeypatch.setattr(
        resources,
        "select_remote_session_otp_candidates",
        lambda **_: SimpleNamespace(
            eligible_count=1200,
            remaining_count=200,
            candidates=candidates,
        ),
    )

    def fake_start_work_job(**kwargs: Any):
        captured.update(kwargs)
        return SimpleNamespace(id="remote-job"), SimpleNamespace(id="remote-run")

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", _FakeWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", _job_result)

    result = resources.create_multi_space_session_otp_remote_submit_job(
        resources.MultiSpaceSessionOtpSubmitJobRequest(
            space_ids=["space-1", "space-2"],
            created_by="test",
        ),
        cast(Any, _FakeSession()),
    )

    assert captured["job_type"] == "account.session_otp.remote_submit.bulk"
    assert captured["input_json"]["selected_count"] == 1000
    assert captured["input_json"]["eligible_count"] == 1200
    assert captured["input_json"]["remaining_count"] == 200
    assert captured["input_json"]["work_count"] == 1
    assert captured["input_json"]["space_ids"] == ["space-1", "space-2"]
    assert captured["input_json"]["user_account_ids"] == [
        f"account-{index}" for index in range(1000)
    ]
    assert result["selected_count"] == 1000
    assert result["work_count"] == 1
    assert len(_FakeWorkQueue.enqueued) == 1
    assert _FakeWorkQueue.enqueued[0]["work_type"] == "account.session_otp.remote_submit"
    assert _FakeWorkQueue.enqueued[0]["input_json"]["space_id"] == "space-1"
    assert _FakeWorkQueue.enqueued[0]["input_json"]["space_ids"] == [
        "space-1",
        "space-2",
    ]


def test_remote_submit_work_calls_bridge_and_returns_terminal_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    def fake_run(**kwargs: Any) -> dict:
        captured["run"] = kwargs
        return {
            "status": "succeeded",
            "batch_id": "batch-1",
            "succeeded_count": 12,
            "failed_count": 0,
            "stale_count": 0,
        }

    monkeypatch.setattr(handlers, "SessionOtpExecutorClient", FakeClient)
    monkeypatch.setattr(handlers, "run_remote_space_session_otp_submit", fake_run)
    settings = SimpleNamespace(
        session_otp_executor_base_url="http://executor.test",
        session_otp_executor_api_key="key",
    )

    result = handlers._run_remote_session_otp_submit_work(
        session_factory=cast(Any, object()),
        settings=cast(Any, settings),
        input_json={
            "space_id": "space-1",
            "space_ids": ["space-1", "space-2"],
            "user_account_ids": ["account-1", "account-2"],
        },
    )

    assert result["batch_id"] == "batch-1"
    assert result["succeeded_count"] == 12
    assert captured["client"] == {
        "base_url": "http://executor.test",
        "api_key": "key",
    }
    assert captured["run"]["space_id"] == "space-1"
    assert captured["run"]["space_ids"] == ["space-1", "space-2"]
    assert captured["run"]["user_account_ids"] == ["account-1", "account-2"]


def test_skipped_submit_work_reaches_barrier_without_blocking_ready_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = SpaceSessionOtpWorkflow(
        session_factory=cast(Any, object()),
        mail_provider=cast(Any, object()),
    )
    submitted: list[str] = []
    failures: list[str] = []
    written: list[str] = []

    def fake_load_submit_input(**kwargs: Any):
        if kwargs["user_account_id"] == "account-skipped":
            raise SpaceSessionOtpWorkflowError("snapshot is unusable")
        return {"phase": "otp_collected", "proxy": "http://proxy.test:80"}, "http://proxy.test:80"

    def fake_submit(**kwargs: Any):
        kwargs["before_validate"]("ready@example.test")
        submitted.append("ready")
        return SimpleNamespace(snapshot={"phase": "otp_validated", "otp_code": "123456"})

    monkeypatch.setattr(workflow, "_load_submit_input", fake_load_submit_input)
    monkeypatch.setattr(
        workflow,
        "_record_submit_failure",
        lambda **kwargs: failures.append(kwargs["snapshot_id"]),
    )
    monkeypatch.setattr(
        workflow,
        "_write_submitted_snapshot",
        lambda **kwargs: written.append(kwargs["snapshot_id"]),
    )
    monkeypatch.setattr(space_session_otp, "submit_prepared_chatgpt_session_otp", fake_submit)

    def run(user_account_id: str, snapshot_id: str) -> dict:
        return workflow.run_submit_work(
            space_id="space-1",
            space_membership_id=f"membership-{user_account_id}",
            user_account_id=user_account_id,
            snapshot_id=snapshot_id,
            barrier_key="submit-job-1",
            barrier_expected=2,
            barrier_timeout_s=2,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        skipped_future = executor.submit(run, "account-skipped", "snapshot-skipped")
        ready_future = executor.submit(run, "account-ready", "snapshot-ready")
        skipped_result = skipped_future.result(timeout=3)
        ready_result = ready_future.result(timeout=3)

    assert skipped_result["submit_status"] == "skipped"
    assert skipped_result["_work_outcome"] == "skipped"
    assert ready_result["submit_status"] == "otp_validated"
    assert submitted == ["ready"]
    assert failures == ["snapshot-skipped"]
    assert written == ["snapshot-ready"]
    assert "submit-job-1" not in space_session_otp._SUBMIT_BARRIERS


def test_pending_otp_is_collected_before_ready_barrier() -> None:
    events: list[str] = []
    wait_kwargs: dict[str, Any] = {}

    class FakeFlow:
        result = SimpleNamespace(email="pending@example.test")
        config = SimpleNamespace(proxy="http://proxy.test:80", proxy_meta={})
        _last_otp_sent_at = 0.0

        def restore_protocol_snapshot(self, _snapshot: dict) -> None:
            events.append("restore")

        def kickoff_otp_delivery(self, _reason: str) -> bool:
            events.append("send")
            return True

        def send_otp(self) -> None:
            events.append("fallback_send")

        def verify_otp(self, code: str, before_post=None, sync_email: str = "") -> dict:
            assert code == "123456"
            before_post(sync_email)
            events.append("validate")
            return {}

        def _extract_continue_url_from_step(self, _response: dict) -> str:
            return ""

        def _normalize_continue_url(self, value: str) -> str:
            return value

        def _extract_page_type(self, _response: dict) -> str:
            return "email_otp_verification"

        def export_protocol_snapshot(self, **extra: Any) -> dict:
            return dict(extra)

    class FakeMailProvider:
        def wait_for_otp(self, *_args: Any, **kwargs: Any) -> str:
            events.append("mail")
            wait_kwargs.update(kwargs)
            return "123456"

    result = AuthFlow.run_protocol_login_submit_prepared_otp(
        cast(Any, FakeFlow()),
        {"email": "pending@example.test", "otp_code": "", "otp_sent_at": 123.0},
        before_validate=lambda _email: events.append("ready"),
        before_skip=lambda _email: events.append("skipped"),
        mail_provider=cast(Any, FakeMailProvider()),
    )

    assert result["phase"] == "otp_validated"
    assert events == ["restore", "mail", "ready", "validate"]
    assert wait_kwargs["max_polls"] == 1
    assert wait_kwargs["issued_after"] == 123.0


def test_missing_pending_otp_reports_skip_before_return() -> None:
    events: list[str] = []
    wait_kwargs: dict[str, Any] = {}

    class FakeFlow:
        result = SimpleNamespace(email="missing@example.test")
        config = SimpleNamespace(proxy="http://proxy.test:80", proxy_meta={})
        _last_otp_sent_at = 0.0

        def restore_protocol_snapshot(self, _snapshot: dict) -> None:
            events.append("restore")

        def kickoff_otp_delivery(self, _reason: str) -> bool:
            events.append("send")
            return True

        def send_otp(self) -> None:
            events.append("fallback_send")

        def export_protocol_snapshot(self, **extra: Any) -> dict:
            return dict(extra)

    class FakeMailProvider:
        def wait_for_otp(self, *_args: Any, **kwargs: Any) -> str:
            events.append("mail")
            wait_kwargs.update(kwargs)
            raise TimeoutError("OTP missing")

    result = AuthFlow.run_protocol_login_submit_prepared_otp(
        cast(Any, FakeFlow()),
        {"email": "missing@example.test", "otp_code": "", "otp_sent_at": 456.0},
        before_validate=lambda _email: events.append("ready"),
        before_skip=lambda _email: events.append("skipped"),
        mail_provider=cast(Any, FakeMailProvider()),
    )

    assert result["phase"] == "otp_missing"
    assert events == ["restore", "mail", "skipped"]
    assert wait_kwargs["max_polls"] == 1
    assert wait_kwargs["issued_after"] == 456.0


def test_prepare_otp_queries_mail_at_most_twice() -> None:
    wait_kwargs: dict[str, Any] = {}

    class FakeFlow:
        result = SimpleNamespace(email="", password="")
        config = SimpleNamespace(proxy="http://proxy.test:80", proxy_meta={})
        _last_otp_sent_at = 123.0

        def check_proxy(self) -> bool:
            return True

        def get_csrf_token(self) -> str:
            return "csrf"

        def get_auth_url(self, _csrf_token: str, **_kwargs: Any) -> str:
            return "https://auth.openai.com/authorize"

        def auth_oauth_init(self, _auth_url: str) -> str:
            return "device"

        def get_sentinel_token(self, _device_id: str) -> str:
            return "sentinel"

        def authorize_continue(self, **_kwargs: Any) -> dict:
            return {
                "page": {
                    "type": "email_otp_verification",
                    "payload": {"email_verification_mode": "passwordless_login"},
                },
                "continue_url": "https://auth.openai.com/email-verification",
            }

        def _extract_page_type(self, response: dict) -> str:
            return str(response["page"]["type"])

        def _extract_continue_url_from_step(self, response: dict) -> str:
            return str(response["continue_url"])

        def _normalize_continue_url(self, value: str) -> str:
            return value

        def kickoff_otp_delivery(self, _reason: str) -> bool:
            return True

        def export_protocol_snapshot(self, **extra: Any) -> dict:
            return dict(extra)

    class FakeMailProvider:
        def wait_for_otp(self, *_args: Any, **kwargs: Any) -> str:
            wait_kwargs.update(kwargs)
            raise TimeoutError("OTP missing")

    result = AuthFlow.run_protocol_login_prepare_otp(
        cast(Any, FakeFlow()),
        cast(Any, FakeMailProvider()),
        "prepare@example.test",
        "password",
    )

    assert result["phase"] == "otp_pending"
    assert wait_kwargs["max_polls"] == 2
    assert wait_kwargs["issued_after"] == 123.0
