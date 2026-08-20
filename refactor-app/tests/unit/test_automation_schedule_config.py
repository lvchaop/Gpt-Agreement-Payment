from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from refactor_app.api.routes import resources
from refactor_app.application.jobs import handlers
from refactor_app.infrastructure.db.models import AutomationScheduleModel


def _schedule(schedule_type: str, config_json: dict[str, Any]) -> AutomationScheduleModel:
    now = datetime.now(UTC)
    return AutomationScheduleModel(
        id=f"schedule-{schedule_type}",
        schedule_type=schedule_type,
        schedule_status="active",
        enabled=False,
        interval_seconds=60,
        config_json=config_json,
        last_run_at=None,
        next_run_at=now,
        last_job_id="",
        last_run_status="",
        locked_by="",
        locked_until=None,
        last_error_code="",
        last_error_message="",
        created_by="test",
        created_at=now,
        updated_at=now,
    )


def test_manual_override_is_merged_without_mutating_saved_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.space_authorize",
        {"space_id": "space-business-1", "work_count": 1, "credential_name_prefix": "codex"},
    )
    original_next_run_at = schedule.next_run_at
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"job_id": "job-1", "job_status": "queued"}

    monkeypatch.setattr(resources, "_create_space_authorization_work_job", fake_create)

    result = resources._execute_space_automation_schedule(
        session=cast(Session, object()),
        schedule=schedule,
        config_json={
            "space_id": "space-business-2",
            "work_count": 2,
            "credential_name_prefix": "manual",
        },
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {"job_id": "job-1", "job_status": "queued"}
    assert captured["work_count"] == 2
    assert captured["space_id"] == "space-business-2"
    assert captured["credential_name_prefix"] == "manual"
    assert captured["created_by"] == "ops:test"
    assert schedule.config_json == {
        "space_id": "space-business-1",
        "work_count": 1,
        "credential_name_prefix": "codex",
    }
    assert schedule.next_run_at == original_next_run_at


def test_schedule_config_rejects_unknown_and_out_of_range_fields() -> None:
    with pytest.raises(HTTPException) as unknown:
        resources._effective_space_schedule_config(
            schedule_type="automation.space_recycle_sweep",
            saved_config={"limit": 100, "work_count": 5},
            overrides={"unknown": 1},
        )
    assert unknown.value.status_code == 400

    with pytest.raises(HTTPException) as out_of_range:
        resources._effective_space_schedule_config(
            schedule_type="automation.space_membership_invite_sync",
            saved_config={},
            overrides={"work_count": 999},
        )
    assert out_of_range.value.status_code == 400


def test_space_authorize_schedule_without_space_id_targets_all_spaces() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.space_authorize",
        saved_config={"work_count": 1},
    )

    assert config["space_id"] == ""
    assert config["use_hero_sms_for_add_phone"] is True


def test_space_authorize_without_space_id_enqueues_business_and_personal_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    business_space = SimpleNamespace(id="space-business", external_space_id="ext-business")
    personal_space = SimpleNamespace(id="space-personal", external_space_id="ext-personal")
    captured: dict[str, Any] = {"works": []}

    monkeypatch.setattr(
        resources,
        "_select_space_authorization_target_spaces",
        lambda **_kwargs: [(business_space, "business"), (personal_space, "personal")],
    )
    monkeypatch.setattr(resources, "_active_work_job_for_type", lambda **_kwargs: None)
    monkeypatch.setattr(
        resources,
        "_select_pending_business_access_token_items",
        lambda **_kwargs: [
            {
                "space_membership_id": "membership-business",
                "space_id": "space-business",
                "user_account_id": "account-business",
                "external_space_id": "ext-business",
                "cookie_header": "session=business",
                "space_name": "Business",
                "owner_user_account_id": "owner-business",
                "source_admin_session_id": "admin-session-business",
            }
        ],
    )
    monkeypatch.setattr(
        resources,
        "_select_pending_personal_codex_items",
        lambda **_kwargs: [
            {
                "space_membership_id": "membership-personal",
                "space_id": "space-personal",
                "user_account_id": "account-personal",
                "external_space_id": "ext-personal",
            }
        ],
    )

    class FakeJobQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> Any:
            captured["job"] = kwargs
            return SimpleNamespace(id="authorize-all-job", job_status="queued")

    class FakeWorkQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> None:
            captured["works"].append(kwargs)

    class FakeSession:
        def commit(self) -> None:
            pass

    monkeypatch.setattr(resources, "JobQueue", FakeJobQueue)
    monkeypatch.setattr(resources, "WorkQueue", FakeWorkQueue)

    result = resources._create_space_authorization_work_job(
        session=cast(Session, FakeSession()),
        space_id="",
        work_count=2,
        created_by="test",
        credential_name_prefix="codex",
        use_hero_sms_for_add_phone=True,
        hero_sms_country="187",
        hero_sms_max_price="0.18",
    )

    assert result["selected_count"] == 2
    assert captured["job"]["input_json"]["space_id"] == ""
    assert captured["job"]["input_json"]["space_ids"] == [
        "space-business",
        "space-personal",
    ]
    assert captured["job"]["input_json"]["authorization_mode"] == (
        "mixed_business_and_personal_codex_oauth"
    )
    assert [work["work_type"] for work in captured["works"]] == [
        "space.business_codex.authorize.account",
        "space.personal_codex.authorize.account",
    ]
    assert captured["works"][1]["input_json"]["use_hero_sms_for_add_phone"] is True


def test_space_invite_schedule_has_fixed_1000_work_direct_network_shape() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.space_membership_invite_sync",
        saved_config={},
    )

    assert config == {
        "space_id": "",
        "space_limit": 1,
        "invite_limit_per_space": 1000,
        "work_count": 1000,
        "barrier_timeout_s": 30.0,
    }


def test_space_seat_expand_config_has_fixed_business_parameters() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.space_seat_expand",
        saved_config={"space_id": "space-1", "work_count": 2},
    )

    assert config == {"space_id": "space-1", "work_count": 2}
    assert resources.TARGET_SEATS == 999
    assert resources.MAX_NO_PROGRESS_COUNT == 10
    assert resources.MAX_HTTP_FAILURE_COUNT == 10


def test_space_auto_replenish_schedule_defaults_and_job_mapping() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.space_auto_replenish",
        saved_config={},
    )

    assert config == {"space_id": "", "work_count": 20}
    assert (
        resources._fixed_automation_schedule_id("automation.space_auto_replenish")
        == "automation-schedule-space-auto-replenish"
    )
    assert (
        resources._job_type_for_schedule_type("automation.space_auto_replenish")
        == "space.auto_replenish.tick"
    )


def test_personal_payment_method_schedule_defaults_and_job_mapping() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.personal_payment_method_bind",
        saved_config={},
    )

    assert config == {
        "space_id": "",
        "limit": 10,
        "work_count": 1,
        "proxy_country": "US",
        "auto_start_plus_checkout": True,
    }
    assert resources._fixed_automation_schedule_id(
        "automation.personal_payment_method_bind"
    ) == "automation-schedule-personal-payment-method-bind"
    assert resources._job_type_for_schedule_type(
        "automation.personal_payment_method_bind"
    ) == "space.personal_payment_method_bind.tick"


def test_personal_payment_method_schedule_rejects_excess_browser_concurrency() -> None:
    with pytest.raises(HTTPException) as error:
        resources._effective_space_schedule_config(
            schedule_type="automation.personal_payment_method_bind",
            saved_config={"work_count": 11},
        )

    assert error.value.status_code == 400


def test_personal_payment_method_schedule_propagates_plus_checkout_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.personal_payment_method_bind",
        {
            "space_id": "",
            "limit": 10,
            "work_count": 1,
            "proxy_country": "US",
            "auto_start_plus_checkout": True,
        },
    )
    captured: dict[str, Any] = {}

    class FakeJobQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(id="payment-bind-job-1", job_status="queued")

    monkeypatch.setattr(resources, "JobQueue", FakeJobQueue)
    monkeypatch.setattr(resources, "_active_work_job_for_type", lambda **_kwargs: None)

    result = resources._execute_space_automation_schedule(
        session=cast(Session, object()),
        schedule=schedule,
        config_json={
            "space_id": "space-personal-1",
            "limit": 5,
            "work_count": 2,
            "proxy_country": "de",
            "auto_start_plus_checkout": False,
            "checkout_ui_mode": "custom",
        },
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {"job_id": "payment-bind-job-1", "job_status": "queued"}
    assert captured == {
        "job_type": "space.personal_payment_method_bind.tick",
        "input_json": {
            "space_id": "space-personal-1",
            "limit": 5,
            "work_count": 2,
            "proxy_country": "DE",
            "auto_start_plus_checkout": False,
            "checkout_ui_mode": "custom",
        },
        "created_by": "ops:test",
    }


def test_personal_payment_method_schedule_rejects_unknown_checkout_ui_mode() -> None:
    with pytest.raises(HTTPException) as error:
        resources._effective_space_schedule_config(
            schedule_type="automation.personal_payment_method_bind",
            saved_config={"checkout_ui_mode": "automatic"},
        )

    assert error.value.status_code == 400


def test_personal_codex_credential_heartbeat_schedule_defaults_and_mapping() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.personal_codex_credential_heartbeat",
        saved_config={},
    )

    assert config == {
        "space_id": "",
        "limit": 100,
        "work_count": 10,
        "use_hero_sms_for_add_phone": True,
        "hero_sms_country": "187",
        "hero_sms_max_price": "0.18",
        "force_clean_browser_login": False,
        "proxy_mode": "cliproxy",
        "proxy_country": "US",
    }
    assert resources._fixed_automation_schedule_id(
        "automation.personal_codex_credential_heartbeat"
    ) == "automation-schedule-personal-codex-credential-heartbeat"
    assert resources._job_type_for_schedule_type(
        "automation.personal_codex_credential_heartbeat"
    ) == "space.personal_codex_credential_heartbeat.tick"


def test_personal_codex_credential_heartbeat_schedule_creates_personal_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.personal_codex_credential_heartbeat",
        {"space_id": "", "limit": 100, "work_count": 10},
    )
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"job_id": "heartbeat-job-1", "job_status": "running"}

    monkeypatch.setattr(
        resources,
        "_create_personal_codex_credential_heartbeat_work_job",
        fake_create,
    )
    fake_session = cast(Session, object())

    result = resources._execute_space_automation_schedule(
        session=fake_session,
        schedule=schedule,
        config_json={
            "space_id": "space-personal-1",
            "limit": 25,
            "work_count": 4,
            "use_hero_sms_for_add_phone": False,
            "hero_sms_country": "187",
            "hero_sms_max_price": "0.18",
            "force_clean_browser_login": True,
            "proxy_mode": "cliproxy",
            "proxy_country": "US",
        },
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {"job_id": "heartbeat-job-1", "job_status": "running"}
    assert captured == {
        "session": fake_session,
        "space_id": "space-personal-1",
        "limit": 25,
        "work_count": 4,
        "created_by": "ops:test",
        "use_hero_sms_for_add_phone": False,
        "hero_sms_country": "187",
        "hero_sms_max_price": "0.18",
        "force_clean_browser_login": True,
        "proxy_mode": "cliproxy",
        "proxy_country": "US",
    }
    assert schedule.last_job_id == "heartbeat-job-1"
    assert schedule.last_run_status == "running"


def test_space_auto_replenish_schedule_enqueues_one_tick_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.space_auto_replenish",
        {"space_id": "", "work_count": 20},
    )
    captured: dict[str, Any] = {}

    class FakeJobQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(id="auto-replenish-job-1", job_status="queued")

    monkeypatch.setattr(resources, "JobQueue", FakeJobQueue)
    monkeypatch.setattr(resources, "_active_work_job_for_type", lambda **_kwargs: None)

    result = resources._execute_space_automation_schedule(
        session=cast(Session, object()),
        schedule=schedule,
        config_json={"space_id": "space-1", "work_count": 8},
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {"job_id": "auto-replenish-job-1", "job_status": "queued"}
    assert captured == {
        "job_type": "space.auto_replenish.tick",
        "input_json": {"space_id": "space-1", "work_count": 8},
        "created_by": "ops:test",
    }


def test_dynamic_invite_schedule_is_one_batch_for_one_space() -> None:
    config = resources._effective_space_schedule_config(
        schedule_type="automation.space_membership_invite_dynamic",
        saved_config={"space_id": "space-1"},
    )

    assert config == {"space_id": "space-1"}
    assert (
        resources._fixed_automation_schedule_id(
            "automation.space_membership_invite_dynamic"
        )
        == "automation-schedule-space-membership-invite-dynamic"
    )
    assert (
        resources._job_type_for_schedule_type(
            "automation.space_membership_invite_dynamic"
        )
        == "space.membership_invite_dynamic"
    )


def test_dynamic_invite_schedule_enqueues_fixed_single_work_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.space_membership_invite_dynamic",
        {"space_id": "space-1"},
    )
    captured: dict[str, Any] = {}

    class FakeJobQueue:
        def __init__(self, _session: Any) -> None:
            pass

        def enqueue(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return SimpleNamespace(id="dynamic-job-1", job_status="queued")

    monkeypatch.setattr(resources, "JobQueue", FakeJobQueue)
    monkeypatch.setattr(resources, "_active_work_job_for_type", lambda **_kwargs: None)

    result = resources._execute_space_automation_schedule(
        session=cast(Session, object()),
        schedule=schedule,
        config_json={"space_id": "space-1"},
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {
        "job_id": "dynamic-job-1",
        "job_status": "queued",
        "work_count": 1,
    }
    assert captured == {
        "job_type": "space.membership_invite_dynamic",
        "input_json": {"space_id": "space-1", "work_count": 1},
        "created_by": "ops:test",
    }


def test_membership_growth_schedule_creates_one_round_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.space_membership_growth_round",
        {"space_id": "space-1", "work_count": 16, "session_wait_timeout_s": 900},
    )
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"job_id": "growth-job-1", "job_status": "queued"}

    monkeypatch.setattr(resources, "_create_space_membership_growth_work_job", fake_create)
    fake_session = cast(Session, object())

    result = resources._execute_space_automation_schedule(
        session=fake_session,
        schedule=schedule,
        config_json={
            "space_id": "space-1",
            "work_count": 8,
            "session_wait_timeout_s": 600,
        },
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {"job_id": "growth-job-1", "job_status": "queued"}
    assert captured == {
        "session": fake_session,
        "space_id": "space-1",
        "work_count": 8,
        "session_wait_timeout_s": 600,
        "created_by": "ops:test",
    }
    assert resources._fixed_automation_schedule_id(
        "automation.space_membership_growth_round"
    ) == "automation-schedule-space-membership-growth-round"
    assert resources._job_type_for_schedule_type(
        "automation.space_membership_growth_round"
    ) == "space.membership_growth_round"


def test_space_seat_expand_schedule_creates_space_work_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schedule = _schedule(
        "automation.space_seat_expand",
        {"space_id": "", "work_count": 1},
    )
    captured: dict[str, Any] = {}

    def fake_create(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"job_id": "seat-job-1", "job_status": "queued"}

    monkeypatch.setattr(resources, "_create_space_seat_expand_work_job", fake_create)

    result = resources._execute_space_automation_schedule(
        session=cast(Session, object()),
        schedule=schedule,
        config_json={"space_id": "space-1", "work_count": 3},
        advance_next_run=False,
        created_by="ops:test",
    )

    assert result == {"job_id": "seat-job-1", "job_status": "queued"}
    assert captured["space_id"] == "space-1"
    assert captured["work_count"] == 3
    assert captured["created_by"] == "ops:test"
    assert schedule.last_job_id == "seat-job-1"


def test_schedule_switch_recalculates_and_clears_next_run_at() -> None:
    schedule = _schedule(
        "automation.space_recycle_sweep",
        {"limit": 100, "work_count": 5},
    )

    class FakeSession:
        def get(self, _model: Any, _id: str) -> AutomationScheduleModel:
            return schedule

        def commit(self) -> None:
            pass

    session = cast(Session, FakeSession())
    resources.patch_automation_schedule(
        schedule.id,
        resources.PatchAutomationScheduleRequest(enabled=True, interval_seconds=120),
        session,
    )
    assert schedule.enabled is True
    assert schedule.next_run_at is not None
    delay = (schedule.next_run_at - datetime.now(UTC)).total_seconds()
    assert 115 <= delay <= 120

    resources.patch_automation_schedule(
        schedule.id,
        resources.PatchAutomationScheduleRequest(enabled=False),
        session,
    )
    assert schedule.enabled is False
    assert schedule.next_run_at is None


def test_invite_handler_uses_job_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeWorkflow:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def run(self, input_: Any, **_kwargs: Any) -> Any:
            captured["input"] = input_
            return SimpleNamespace(queued_invite_count=0)

    monkeypatch.setattr(handlers, "SpaceMembershipInviteSyncWorkflow", FakeWorkflow)
    monkeypatch.setattr(handlers, "_openai_plugin", lambda _settings: object())
    monkeypatch.setattr(
        handlers,
        "_work_summary",
        lambda **_kwargs: {
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    output = handlers._run_space_membership_invite_sync_job(
        session_factory=cast(Any, object()),
        settings=cast(Any, object()),
        input_json={
            "space_id": "space-1",
            "space_limit": 1,
            "invite_limit_per_space": 1000,
            "work_count": 1000,
            "barrier_timeout_s": 12,
            "_job_id": "job-1",
            "_run_id": "run-1",
        },
    )

    input_ = captured["input"]
    assert input_.space_id == "space-1"
    assert input_.space_limit == 1
    assert input_.invite_limit_per_space == 1000
    assert input_.work_count == 1000
    assert input_.barrier_timeout_s == 12
    assert output["space_limit"] == 1
    assert output["space_id"] == "space-1"
    assert output["work_count"] == 1000
