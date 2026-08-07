import base64
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from refactor_app.application.workflows import account_auth
from refactor_app.application.workflows.account_auth import BackfillSessionWorkflow
from refactor_app.application.workflows.space_authorization import (
    CreateBusinessAccessTokenCredentialInput,
    CreateBusinessAccessTokenCredentialWorkflow,
    SpaceAuthorizationWorkflowError,
    UpsertPersonalCodexSpaceCredentialInput,
    UpsertPersonalCodexSpaceCredentialWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
)

ACCOUNT_ID = "test-space-identity-owner-account"
BUSINESS_SPACE_ID = "test-space-identity-business"
BUSINESS_EXTERNAL_ID = "test-space-identity-business-external"
PERSONAL_EXTERNAL_ID = "test-space-identity-personal-external"


def _workspace_access_token(chatgpt_account_id: str) -> str:
    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return ".".join(
        (
            encode({"alg": "none", "typ": "JWT"}),
            encode(
                {
                    "https://api.openai.com/auth": {
                        "chatgpt_account_id": chatgpt_account_id,
                        "chatgpt_user_id": "user-owner",
                    }
                }
            ),
            "",
        )
    )


def test_v4_owns_account_identity_and_authorization_does_not_rewrite_it(monkeypatch) -> None:
    session_factory = make_session_factory(make_engine(Settings()))
    now = datetime.now(UTC)
    _cleanup(session_factory)

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=ACCOUNT_ID,
                email="space-identity@example.test",
                openai_user_id="user-stale__stale-space",
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=BUSINESS_SPACE_ID,
                provider="openai_chatgpt",
                external_space_id=BUSINESS_EXTERNAL_ID,
                owner_user_account_id="",
                name="Identity business",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_5h_weekly",
                plan_type="team",
                seat_limit=0,
                seats_in_use=0,
                seats_entitled=0,
                space_status="active",
                source_admin_session_id="",
                raw_space_json={},
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(
        account_auth,
        "_fetch_accounts_check_v4",
        lambda **_kwargs: _accounts_check_payload(),
    )
    personal_session_access_token = _workspace_access_token(PERSONAL_EXTERNAL_ID)
    result = BackfillSessionWorkflow(
        session_factory=session_factory,
        mail_provider=object(),
    ).detect_account_spaces_from_session(
        user_account_id=ACCOUNT_ID,
        access_token=personal_session_access_token,
        cookie_header="session-cookie=value",
        proxy_url="",
        session_chatgpt_account_id=PERSONAL_EXTERNAL_ID,
        session_chatgpt_account_structure="personal",
        session_chatgpt_account_plan_type="plus",
    )

    assert result["accounts_check_succeeded"] is True
    with session_factory() as session:
        account = session.get(UserAccountModel, ACCOUNT_ID)
        personal_space = session.scalars(
            select(SpaceModel).where(SpaceModel.external_space_id == PERSONAL_EXTERNAL_ID)
        ).one()
        memberships = {
            row.space_id: row
            for row in session.scalars(
                select(SpaceMembershipModel).where(
                    SpaceMembershipModel.user_account_id == ACCOUNT_ID
                )
            ).all()
        }
        assert account is not None
        assert account.openai_user_id == "user-owner"
        assert account.access_token == personal_session_access_token
        assert personal_space.plan_type == "plus"
        assert memberships[BUSINESS_SPACE_ID].remote_user_id == "user-owner"
        assert (
            memberships[BUSINESS_SPACE_ID].remote_account_user_id
            == f"user-owner__{BUSINESS_EXTERNAL_ID}"
        )
        assert memberships[personal_space.id].remote_user_id == "user-owner"
        assert (
            memberships[personal_space.id].remote_account_user_id
            == f"user-owner__{PERSONAL_EXTERNAL_ID}"
        )

    BackfillSessionWorkflow(
        session_factory=session_factory,
        mail_provider=object(),
    ).detect_account_spaces_from_session(
        user_account_id=ACCOUNT_ID,
        access_token=personal_session_access_token,
        cookie_header="session-cookie=value",
        proxy_url="",
        session_chatgpt_account_id=PERSONAL_EXTERNAL_ID,
        session_chatgpt_account_structure="personal",
        session_chatgpt_account_plan_type="pro",
    )
    with session_factory() as session:
        personal_space = session.scalars(
            select(SpaceModel).where(SpaceModel.external_space_id == PERSONAL_EXTERNAL_ID)
        ).one()
        assert personal_space.plan_type == "pro"
        business_membership = session.scalars(
            select(SpaceMembershipModel).where(
                SpaceMembershipModel.space_id == BUSINESS_SPACE_ID,
                SpaceMembershipModel.user_account_id == ACCOUNT_ID,
            )
        ).one()
        business_membership.remote_user_id = "user-business-member"
        session.commit()

    provider = _BusinessCredentialProvider()
    CreateBusinessAccessTokenCredentialWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(
        CreateBusinessAccessTokenCredentialInput(
            user_account_id=ACCOUNT_ID,
            external_space_id=BUSINESS_EXTERNAL_ID,
            session_access_token="",
            credential_name="identity-test",
            cookie_header="session-cookie=value",
        )
    )
    UpsertPersonalCodexSpaceCredentialWorkflow(session_factory=session_factory).run(
        UpsertPersonalCodexSpaceCredentialInput(
            user_account_id=ACCOUNT_ID,
            external_space_id=PERSONAL_EXTERNAL_ID,
            access_token="personal-access-token",
            id_token="personal-id-token",
            refresh_token="personal-refresh-token",
            codex_client_id="personal-client-id",
            token_chatgpt_account_id=PERSONAL_EXTERNAL_ID,
            expires_at=None,
        )
    )

    with session_factory() as session:
        account = session.get(UserAccountModel, ACCOUNT_ID)
        personal_space = session.scalars(
            select(SpaceModel).where(SpaceModel.external_space_id == PERSONAL_EXTERNAL_ID)
        ).one()
        credentials = session.scalars(
            select(SpaceCredentialModel).where(SpaceCredentialModel.user_account_id == ACCOUNT_ID)
        ).all()
        account_ids = {row.account_id for row in credentials}
        assert account is not None
        assert account.openai_user_id == "user-owner"
        assert personal_space.plan_type == "pro"
        assert account_ids == {"user-owner", "user-business-member"}

    _cleanup(session_factory)


def test_disabled_business_space_blocks_authorization_upstream_call() -> None:
    session_factory = make_session_factory(make_engine(Settings()))
    now = datetime.now(UTC)
    _cleanup(session_factory)

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=ACCOUNT_ID,
                email="space-disabled@example.test",
                openai_user_id="user-disabled",
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=BUSINESS_SPACE_ID,
                provider="openai_chatgpt",
                external_space_id=BUSINESS_EXTERNAL_ID,
                owner_user_account_id="",
                name="Disabled business",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_monthly",
                plan_type="team",
                seat_limit=0,
                seats_in_use=0,
                seats_entitled=0,
                space_status="disabled",
                source_admin_session_id="",
                raw_space_json={},
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        session.add(
            SpaceMembershipModel(
                id="test-space-disabled-membership",
                space_id=BUSINESS_SPACE_ID,
                user_account_id=ACCOUNT_ID,
                membership_status="active",
                remote_user_id="user-disabled",
                session_account_detected=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = _BusinessCredentialProvider()
    with pytest.raises(SpaceAuthorizationWorkflowError, match="space_not_active"):
        CreateBusinessAccessTokenCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=provider,
        ).run(
            CreateBusinessAccessTokenCredentialInput(
                user_account_id=ACCOUNT_ID,
                external_space_id=BUSINESS_EXTERNAL_ID,
                session_access_token="",
                credential_name="disabled-test",
                cookie_header="session-cookie=value",
            )
        )

    assert provider.call_count == 0
    _cleanup(session_factory)


def test_business_access_token_uses_account_user_id_when_membership_remote_id_is_empty() -> None:
    session_factory = make_session_factory(make_engine(Settings()))
    now = datetime.now(UTC)
    _cleanup(session_factory)

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=ACCOUNT_ID,
                email="business-at-fallback@example.test",
                openai_user_id="user-business-at-fallback",
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=BUSINESS_SPACE_ID,
                provider="openai_chatgpt",
                external_space_id=BUSINESS_EXTERNAL_ID,
                owner_user_account_id="",
                name="Business AT fallback",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_monthly",
                plan_type="team",
                seat_limit=0,
                seats_in_use=0,
                seats_entitled=0,
                space_status="active",
                source_admin_session_id="",
                raw_space_json={},
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        session.add(
            SpaceMembershipModel(
                id="test-business-at-fallback-membership",
                space_id=BUSINESS_SPACE_ID,
                user_account_id=ACCOUNT_ID,
                membership_status="active",
                remote_user_id="",
                remote_account_user_id="",
                session_account_detected=True,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    CreateBusinessAccessTokenCredentialWorkflow(
        session_factory=session_factory,
        openai_provider=_BusinessCredentialProvider(),
    ).run(
        CreateBusinessAccessTokenCredentialInput(
            user_account_id=ACCOUNT_ID,
            external_space_id=BUSINESS_EXTERNAL_ID,
            session_access_token="",
            credential_name="fallback-test",
            cookie_header="session-cookie=value",
        )
    )

    with session_factory() as session:
        credential = session.scalars(
            select(SpaceCredentialModel).where(
                SpaceCredentialModel.user_account_id == ACCOUNT_ID,
                SpaceCredentialModel.space_id == BUSINESS_SPACE_ID,
            )
        ).one()
        membership = session.get(
            SpaceMembershipModel,
            "test-business-at-fallback-membership",
        )
        assert credential.account_id == "user-business-at-fallback"
        assert membership is not None
        assert membership.remote_user_id == ""
        assert membership.remote_account_user_id == ""

    _cleanup(session_factory)


def test_detection_flag_only_preserves_account_and_membership_fields(monkeypatch) -> None:
    session_factory = make_session_factory(make_engine(Settings()))
    now = datetime.now(UTC)
    _cleanup(session_factory)

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=ACCOUNT_ID,
                email="space-detection-only@example.test",
                openai_user_id="user-original",
                access_token="personal-access-token-original",
                cookie_header="session-cookie=value",
                account_status="active",
                session_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            SpaceModel(
                id=BUSINESS_SPACE_ID,
                provider="openai_chatgpt",
                external_space_id=BUSINESS_EXTERNAL_ID,
                owner_user_account_id="",
                name="Detection-only business",
                space_type="business",
                auth_mode="backend_access_token",
                credential_type="team_5h_weekly",
                plan_type="team",
                seat_limit=0,
                seats_in_use=0,
                seats_entitled=0,
                space_status="active",
                source_admin_session_id="",
                raw_space_json={},
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        session.add(
            SpaceMembershipModel(
                id="test-space-detection-only-membership",
                space_id=BUSINESS_SPACE_ID,
                user_account_id=ACCOUNT_ID,
                membership_status="invited",
                session_account_detected=False,
                remote_user_id="user-original-remote",
                remote_account_user_id=f"user-original-remote__{BUSINESS_EXTERNAL_ID}",
                failure_code="existing-failure",
                failure_message="existing failure must be preserved",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(
        account_auth,
        "_fetch_accounts_check_v4",
        lambda **_kwargs: _accounts_check_payload(),
    )
    BackfillSessionWorkflow(
        session_factory=session_factory,
        mail_provider=object(),
    )._mark_detected_space_memberships(
        user_account_id=ACCOUNT_ID,
        access_token="current-session-access-token",
        cookie_header="session-cookie=value",
        proxy_url="",
        run_id="",
        parent_step_id="",
        raise_on_error=True,
        detection_flag_only=True,
    )

    with session_factory() as session:
        account = session.get(UserAccountModel, ACCOUNT_ID)
        membership = session.get(
            SpaceMembershipModel,
            "test-space-detection-only-membership",
        )
        memberships = session.scalars(
            select(SpaceMembershipModel).where(
                SpaceMembershipModel.user_account_id == ACCOUNT_ID
            )
        ).all()
        spaces = session.scalars(
            select(SpaceModel).where(
                SpaceModel.external_space_id.in_([BUSINESS_EXTERNAL_ID, PERSONAL_EXTERNAL_ID])
            )
        ).all()

        assert account is not None
        assert account.access_token == "personal-access-token-original"
        assert account.openai_user_id == "user-original"
        assert membership is not None
        assert membership.session_account_detected is True
        assert membership.membership_status == "invited"
        assert membership.remote_user_id == "user-original-remote"
        assert (
            membership.remote_account_user_id
            == f"user-original-remote__{BUSINESS_EXTERNAL_ID}"
        )
        assert membership.failure_code == "existing-failure"
        assert membership.failure_message == "existing failure must be preserved"
        assert len(memberships) == 1
        assert [space.external_space_id for space in spaces] == [BUSINESS_EXTERNAL_ID]

    _cleanup(session_factory)


def _accounts_check_payload() -> dict:
    personal = {
        "account": {
            "account_id": PERSONAL_EXTERNAL_ID,
            "account_owner_id": "user-owner",
            "account_user_id": f"user-owner__{PERSONAL_EXTERNAL_ID}",
            "structure": "personal",
        }
    }
    return {
        "accounts": {
            BUSINESS_EXTERNAL_ID: {
                "account": {
                    "account_id": BUSINESS_EXTERNAL_ID,
                    "account_owner_id": "user-workspace-owner",
                    "account_user_id": f"user-owner__{BUSINESS_EXTERNAL_ID}",
                    "structure": "workspace",
                }
            },
            PERSONAL_EXTERNAL_ID: personal,
            "default": personal,
        }
    }


class _BusinessCredentialProvider:
    def __init__(self) -> None:
        self.call_count = 0

    def create_wham_auth_credential(self, **kwargs) -> dict:
        self.call_count += 1
        return {
            "workspace_id": kwargs["chatgpt_account_id"],
            "credential_id": "identity-test-credential",
            "access_token": "business-access-token",
            "expires_at": 0,
        }


def _cleanup(session_factory) -> None:
    with session_factory() as session:
        session.execute(
            delete(SpaceCredentialModel).where(SpaceCredentialModel.user_account_id == ACCOUNT_ID)
        )
        session.execute(
            delete(SpaceMembershipModel).where(SpaceMembershipModel.user_account_id == ACCOUNT_ID)
        )
        session.execute(
            delete(SpaceModel).where(
                SpaceModel.external_space_id.in_([BUSINESS_EXTERNAL_ID, PERSONAL_EXTERNAL_ID])
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == ACCOUNT_ID))
        session.commit()
