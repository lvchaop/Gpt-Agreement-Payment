from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete

from refactor_app.application.workflows.membership import (
    InviteWorkspaceMemberWorkflow,
    MembershipProbeWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import MembershipModel, TeamWorkspaceModel, UserAccountModel
from refactor_app.plugins.contracts import HealthcheckResult


class StaticOpenAIProvider:
    name = "static-openai-test"

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok")

    def capabilities(self) -> list[str]:
        return ["openai_chatgpt.team_workspace.probe_membership"]

    def refresh_workspace_token(self, **_kwargs):
        raise NotImplementedError

    def decode_access_token(self, _access_token: str):
        raise NotImplementedError

    def invite_member(self, **_kwargs):
        self.calls.append({"invite_member": _kwargs})
        return {"account_invites": [{"id": "invite-1"}]}

    def accept_invite(self, **_kwargs):
        raise NotImplementedError

    def probe_membership(self, *, access_token: str, team_id: str) -> dict:
        self.calls.append({"access_token": access_token, "team_id": team_id})
        return self.payload


def test_membership_probe_updates_invite_permission_seat_status_and_can_invite() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-membership-probe-account"
    workspace_id = "test-membership-probe-workspace"
    membership_id = "test-membership-probe-membership"

    with session_factory() as session:
        session.execute(delete(MembershipModel).where(MembershipModel.id == membership_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(
            delete(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == "workspace-probe-ext"
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="membership-probe@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-probe-ext",
                name="Workspace 1",
                seat_limit=3,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            MembershipModel(
                id=membership_id,
                user_account_id=account_id,
                team_workspace_id=workspace_id,
                membership_status="unknown",
                chatgpt_web_backend_access_token="access-1",
                chatgpt_web_backend_access_token_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticOpenAIProvider(
        {
            "membership_status": "active",
            "invite_permission": "ok",
            "user_count": 1,
            "invite_count": 1,
        }
    )
    result = MembershipProbeWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(membership_id=membership_id)

    with session_factory() as session:
        membership = session.get(MembershipModel, membership_id)

        assert result.can_invite is True
        assert membership is not None
        assert membership.membership_status == "active"
        assert membership.invite_permission == "ok"
        assert membership.seat_status == "available"
        assert membership.can_invite is True
        assert membership.last_probe_status == "ok"
        assert provider.calls == [{"access_token": "access-1", "team_id": "workspace-probe-ext"}]

        session.execute(delete(MembershipModel).where(MembershipModel.id == membership_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_invite_workspace_member_uses_inviter_membership_token_and_workspace() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-membership-invite-account"
    workspace_id = "test-membership-invite-workspace"
    membership_id = "test-membership-invite-membership"

    with session_factory() as session:
        session.execute(delete(MembershipModel).where(MembershipModel.id == membership_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.add(
            UserAccountModel(
                id=account_id,
                email="membership-invite@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-invite-ext",
                name="Workspace Invite",
                seat_limit=3,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            MembershipModel(
                id=membership_id,
                user_account_id=account_id,
                team_workspace_id=workspace_id,
                membership_status="active",
                chatgpt_web_backend_access_token="access-inviter",
                chatgpt_web_backend_access_token_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticOpenAIProvider({})
    result = InviteWorkspaceMemberWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(inviter_membership_id=membership_id, email="member@example.test")

    assert result["account_invites"][0]["id"] == "invite-1"
    assert provider.calls == [
        {
            "invite_member": {
                "access_token": "access-inviter",
                "team_id": "workspace-invite-ext",
                "email": "member@example.test",
            }
        }
    ]

    with session_factory() as session:
        session.execute(delete(MembershipModel).where(MembershipModel.id == membership_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()
