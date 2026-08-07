from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from pytest import MonkeyPatch
from sqlalchemy import delete

from refactor_app.api.routes import resources
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
)


def test_selected_personal_memberships_create_manual_authorize_job(
    monkeypatch: MonkeyPatch,
) -> None:
    prefix = f"test-personal-authorize-{uuid4()}"
    eligible_account_id = f"{prefix}-eligible-account"
    blocked_account_id = f"{prefix}-blocked-account"
    eligible_space_id = f"{prefix}-eligible-space"
    blocked_space_id = f"{prefix}-blocked-space"
    eligible_membership_id = f"{prefix}-eligible-membership"
    blocked_membership_id = f"{prefix}-blocked-membership"
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))

    with session_factory() as session:
        session.add_all(
            [
                UserAccountModel(
                    id=eligible_account_id,
                    email=f"{eligible_account_id}@example.test",
                    openai_user_id=f"user-{eligible_account_id}",
                    cookie_header="session=eligible",
                    account_status="active",
                    session_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                UserAccountModel(
                    id=blocked_account_id,
                    email=f"{blocked_account_id}@example.test",
                    openai_user_id=f"user-{blocked_account_id}",
                    cookie_header="session=blocked",
                    auth_cookie_header="auth=blocked",
                    codex_select_channel_required=True,
                    codex_select_channel_detected_at=now,
                    account_status="active",
                    session_status="active",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                SpaceModel(
                    id=eligible_space_id,
                    external_space_id=f"{prefix}-eligible-external",
                    owner_user_account_id=eligible_account_id,
                    name="Eligible personal",
                    space_type="personal",
                    auth_mode="codex_oauth",
                    credential_type="personal_account",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                ),
                SpaceModel(
                    id=blocked_space_id,
                    external_space_id=f"{prefix}-blocked-external",
                    owner_user_account_id=blocked_account_id,
                    name="Blocked personal",
                    space_type="personal",
                    auth_mode="codex_oauth",
                    credential_type="personal_account",
                    space_status="active",
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                SpaceMembershipModel(
                    id=eligible_membership_id,
                    space_id=eligible_space_id,
                    user_account_id=eligible_account_id,
                    membership_status="active",
                    session_account_detected=True,
                    created_at=now,
                    updated_at=now,
                ),
                SpaceMembershipModel(
                    id=blocked_membership_id,
                    space_id=blocked_space_id,
                    user_account_id=blocked_account_id,
                    membership_status="active",
                    session_account_detected=True,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()

    captured: dict = {"works": []}

    def fake_start_work_job(**kwargs):
        captured["job"] = kwargs
        return SimpleNamespace(id="manual-personal-job"), SimpleNamespace(id="manual-personal-run")

    class CapturingWorkQueue:
        def __init__(self, _session) -> None:
            pass

        def enqueue(self, **kwargs) -> None:
            captured["works"].append(kwargs)

    def fake_summary_response(**kwargs):
        return {
            "job_id": kwargs["job_id"],
            "job_status": "running",
            "run_id": kwargs["run_id"],
            "work_count": kwargs["work_count"],
            "selected_count": kwargs["selected_count"],
            "queued": kwargs["selected_count"],
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        }

    monkeypatch.setattr(resources, "_start_work_job", fake_start_work_job)
    monkeypatch.setattr(resources, "WorkQueue", CapturingWorkQueue)
    monkeypatch.setattr(resources, "_work_job_summary_response", fake_summary_response)

    try:
        with session_factory() as session:
            result = resources._create_personal_codex_authorization_work_job(
                req=resources.PersonalCodexAuthorizationJobRequest(
                    space_membership_ids=[
                        eligible_membership_id,
                        eligible_membership_id,
                        blocked_membership_id,
                    ],
                    created_by="test",
                    work_count=2,
                    use_hero_sms_for_add_phone=True,
                    hero_sms_country="73",
                    hero_sms_max_price="0.25",
                    force_clean_browser_login=True,
                ),
                session=session,
            )

        assert captured["job"]["job_type"] == "automation.space_authorize"
        assert captured["job"]["input_json"]["authorization_mode"] == (
            "manual_personal_memberships"
        )
        assert captured["job"]["input_json"]["space_membership_ids"] == [eligible_membership_id]
        assert captured["job"]["input_json"]["use_hero_sms_for_add_phone"] is True
        assert captured["job"]["input_json"]["hero_sms_country"] == "73"
        assert captured["job"]["input_json"]["hero_sms_max_price"] == "0.25"
        assert captured["job"]["input_json"]["force_clean_browser_login"] is True
        assert "cookie" not in str(captured["job"]["input_json"]).lower()
        assert "token" not in str(captured["job"]["input_json"]).lower()
        assert len(captured["works"]) == 1
        assert captured["works"][0]["work_type"] == ("space.personal_codex.authorize.account")
        assert captured["works"][0]["input_json"] == {
            "space_membership_id": eligible_membership_id,
            "space_id": eligible_space_id,
            "user_account_id": eligible_account_id,
            "external_space_id": f"{prefix}-eligible-external",
            "force_clean_browser_login": True,
            "use_hero_sms_for_add_phone": True,
            "hero_sms_country": "73",
            "hero_sms_max_price": "0.25",
            "_run_id": "manual-personal-run",
        }
        assert result["requested_count"] == 2
        assert result["selected_count"] == 1
        assert result["selection_skipped_count"] == 1
        assert result["selection_skipped"] == [
            {
                "space_membership_id": blocked_membership_id,
                "reason": "phone_otp_select_channel_permanent_skip",
            }
        ]
    finally:
        with session_factory() as session:
            session.execute(
                delete(SpaceModel).where(SpaceModel.id.in_([eligible_space_id, blocked_space_id]))
            )
            session.execute(
                delete(UserAccountModel).where(
                    UserAccountModel.id.in_([eligible_account_id, blocked_account_id])
                )
            )
            session.commit()


def test_personal_codex_hero_options_accept_price_above_default() -> None:
    options = resources._validated_personal_codex_hero_options(
        resources.PersonalCodexAuthorizationJobRequest(
            space_membership_ids=["membership-1"],
            use_hero_sms_for_add_phone=True,
            hero_sms_country="151",
            hero_sms_max_price="1.25",
        )
    )

    assert options == {
        "use_hero_sms_for_add_phone": True,
        "hero_sms_country": "151",
        "hero_sms_max_price": "1.25",
    }


def test_personal_codex_hero_options_accept_numeric_price_from_browser() -> None:
    options = resources._validated_personal_codex_hero_options(
        resources.PersonalCodexAuthorizationJobRequest(
            space_membership_ids=["membership-1"],
            use_hero_sms_for_add_phone=True,
            hero_sms_country="16",
            hero_sms_max_price=0.05,
        )
    )

    assert options == {
        "use_hero_sms_for_add_phone": True,
        "hero_sms_country": "16",
        "hero_sms_max_price": "0.05",
    }


def test_personal_codex_without_hero_does_not_store_phone_options() -> None:
    options = resources._validated_personal_codex_hero_options(
        resources.PersonalCodexAuthorizationJobRequest(
            space_membership_ids=["membership-1"],
            use_hero_sms_for_add_phone=False,
            hero_sms_country="not-used",
            hero_sms_max_price="not-used",
        )
    )

    assert options == {"use_hero_sms_for_add_phone": False}
