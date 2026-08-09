from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from refactor_app.api.routes import resources
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    JobModel,
    SpaceCredentialModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)


def test_heartbeat_job_selects_only_recoverable_personal_codex_credentials() -> None:
    suffix = uuid4().hex
    account_id = f"test-heartbeat-account-{suffix}"
    personal_space_id = f"test-heartbeat-personal-space-{suffix}"
    free_space_id = f"test-heartbeat-free-space-{suffix}"
    invalid_space_id = f"test-heartbeat-invalid-space-{suffix}"
    revoked_space_id = f"test-heartbeat-revoked-space-{suffix}"
    business_space_id = f"test-heartbeat-business-space-{suffix}"
    credential_ids = {
        "active": f"test-heartbeat-active-{suffix}",
        "free": f"test-heartbeat-free-{suffix}",
        "invalid": f"test-heartbeat-invalid-{suffix}",
        "revoked": f"test-heartbeat-revoked-{suffix}",
        "business": f"test-heartbeat-business-{suffix}",
    }
    job_id = ""
    now = datetime.now(UTC)
    session_factory = make_session_factory(make_engine(Settings()))

    try:
        with session_factory() as session:
            session.add(
                UserAccountModel(
                    id=account_id,
                    email=f"heartbeat-{suffix}@example.test",
                    openai_user_id=f"user-{suffix}",
                    account_status="active",
                    session_status="active",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add_all(
                [
                    SpaceModel(
                        id=personal_space_id,
                        external_space_id=f"personal-{suffix}",
                        owner_user_account_id=account_id,
                        name="Personal heartbeat",
                        space_type="personal",
                        auth_mode="codex_oauth",
                        credential_type="personal_account",
                        plan_type="plus",
                        space_status="active",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceModel(
                        id=free_space_id,
                        external_space_id=f"personal-free-{suffix}",
                        owner_user_account_id=account_id,
                        name="Free Personal heartbeat exclusion",
                        space_type="personal",
                        auth_mode="codex_oauth",
                        credential_type="personal_account",
                        plan_type="free",
                        space_status="active",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceModel(
                        id=business_space_id,
                        external_space_id=f"business-{suffix}",
                        owner_user_account_id=account_id,
                        name="Business heartbeat exclusion",
                        space_type="business",
                        auth_mode="codex_oauth",
                        credential_type="team_monthly",
                        space_status="active",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceModel(
                        id=invalid_space_id,
                        external_space_id=f"personal-invalid-{suffix}",
                        owner_user_account_id=account_id,
                        name="Invalid Personal heartbeat",
                        space_type="personal",
                        auth_mode="codex_oauth",
                        credential_type="personal_account",
                        plan_type="plus",
                        space_status="active",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceModel(
                        id=revoked_space_id,
                        external_space_id=f"personal-revoked-{suffix}",
                        owner_user_account_id=account_id,
                        name="Revoked Personal heartbeat",
                        space_type="personal",
                        auth_mode="codex_oauth",
                        credential_type="personal_account",
                        plan_type="plus",
                        space_status="active",
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    SpaceCredentialModel(
                        id=credential_ids["active"],
                        space_id=personal_space_id,
                        user_account_id=account_id,
                        auth_mode="codex_oauth",
                        credential_status="active",
                        access_token="active-token",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceCredentialModel(
                        id=credential_ids["free"],
                        space_id=free_space_id,
                        user_account_id=account_id,
                        auth_mode="codex_oauth",
                        credential_status="active",
                        access_token="free-token",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceCredentialModel(
                        id=credential_ids["invalid"],
                        space_id=invalid_space_id,
                        user_account_id=account_id,
                        auth_mode="codex_oauth",
                        credential_status="invalid",
                        access_token="invalid-token",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceCredentialModel(
                        id=credential_ids["revoked"],
                        space_id=revoked_space_id,
                        user_account_id=account_id,
                        auth_mode="codex_oauth",
                        credential_status="revoked",
                        access_token="revoked-token",
                        created_at=now,
                        updated_at=now,
                    ),
                    SpaceCredentialModel(
                        id=credential_ids["business"],
                        space_id=business_space_id,
                        user_account_id=account_id,
                        auth_mode="codex_oauth",
                        credential_status="active",
                        access_token="business-token",
                        created_at=now,
                        updated_at=now,
                    ),
                ]
            )
            session.commit()

        with session_factory() as session:
            business_result = resources._create_personal_codex_credential_heartbeat_work_job(
                session=session,
                space_id=business_space_id,
                limit=100,
                work_count=10,
                created_by="test",
                use_hero_sms_for_add_phone=True,
                hero_sms_country="187",
                hero_sms_max_price="0.18",
                force_clean_browser_login=False,
            )
            revoked_result = resources._create_personal_codex_credential_heartbeat_work_job(
                session=session,
                space_id=revoked_space_id,
                limit=100,
                work_count=10,
                created_by="test",
                use_hero_sms_for_add_phone=True,
                hero_sms_country="187",
                hero_sms_max_price="0.18",
                force_clean_browser_login=False,
            )
            free_result = resources._create_personal_codex_credential_heartbeat_work_job(
                session=session,
                space_id=free_space_id,
                limit=100,
                work_count=10,
                created_by="test",
                use_hero_sms_for_add_phone=True,
                hero_sms_country="187",
                hero_sms_max_price="0.18",
                force_clean_browser_login=False,
            )
            result = resources._create_personal_codex_credential_heartbeat_work_job(
                session=session,
                space_id=invalid_space_id,
                limit=100,
                work_count=10,
                created_by="test",
                use_hero_sms_for_add_phone=True,
                hero_sms_country="187",
                hero_sms_max_price="0.18",
                force_clean_browser_login=False,
            )
            job_id = str(result["job_id"])

        assert business_result["job_status"] == "skipped"
        assert business_result["selected_count"] == 0
        assert revoked_result["job_status"] == "skipped"
        assert revoked_result["selected_count"] == 0
        assert free_result["job_status"] == "skipped"
        assert free_result["selected_count"] == 0
        assert result["selected_count"] == 1
        with session_factory() as session:
            job = session.get(JobModel, job_id)
            works = session.scalars(
                select(WorkItemModel).where(WorkItemModel.job_id == job_id)
            ).all()
            assert job is not None
            assert job.type == "space.personal_codex_credential_heartbeat.tick"
            assert job.input_json["space_credential_ids"] == [credential_ids["invalid"]]
            assert [work.work_type for work in works] == [
                "space.personal_codex_credential_heartbeat.account",
            ]
            assert works[0].input_json["space_credential_id"] == credential_ids["invalid"]
    finally:
        with session_factory() as session:
            if job_id:
                session.execute(delete(JobModel).where(JobModel.id == job_id))
            session.execute(
                delete(SpaceModel).where(
                    SpaceModel.id.in_(
                        [
                            personal_space_id,
                            free_space_id,
                            invalid_space_id,
                            revoked_space_id,
                            business_space_id,
                        ]
                    )
                )
            )
            session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
            session.commit()
