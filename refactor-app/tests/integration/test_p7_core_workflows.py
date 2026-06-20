from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy import or_

from refactor_app.application.workflows.batches import ActivateWorkspaceJoinBatchWorkflow
from refactor_app.application.workflows.batches import JoinWorkspaceBatchInput, JoinWorkspaceBatchWorkflow
from refactor_app.application.workflows.codex_credentials import (
    BuildCodexCredentialInput,
    BuildCodexCredentialWorkflow,
)
from refactor_app.application.workflows.heartbeat import HeartbeatCodexCredentialWorkflow
from refactor_app.application.workflows.workspace import (
    ImportTeamWorkspaceInput,
    ImportTeamWorkspaceWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    MembershipModel,
    TeamWorkspaceModel,
    UserAccountAuthModel,
    UserAccountModel,
    WorkspaceJoinBatchItemModel,
    WorkspaceJoinBatchModel,
)
from refactor_app.plugins.contracts import HealthcheckResult, OAuthTokenSet, TokenClaims


class StaticOpenAIProvider:
    name = "static-openai-token-test"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok")

    def capabilities(self) -> list[str]:
        return ["openai_chatgpt.oauth.refresh_workspace_token"]

    def refresh_workspace_token(
        self,
        *,
        refresh_token: str,
        external_workspace_id: str,
        client_id: str,
    ) -> OAuthTokenSet:
        self.calls.append(
            {
                "refresh_token": refresh_token,
                "external_workspace_id": external_workspace_id,
                "client_id": client_id,
            }
        )
        return OAuthTokenSet(
            access_token="access-1",
            id_token="id-1",
            refresh_token="rt-2",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            claims=TokenClaims(
                account_id="chatgpt-user-1",
                token_chatgpt_account_id=external_workspace_id,
            ),
        )

    def decode_access_token(self, _access_token: str):
        raise NotImplementedError

    def invite_member(self, **_kwargs):
        raise NotImplementedError

    def accept_invite(self, **_kwargs):
        self.calls.append({"accept_invite": _kwargs})
        return {"ok": True}

    def probe_membership(self, **_kwargs):
        raise NotImplementedError

    def heartbeat_codex_credential(self, *, access_token: str, team_id: str) -> dict:
        self.calls.append({"heartbeat_access_token": access_token, "team_id": team_id})
        return {"status": "ok"}


def test_import_team_workspace_upserts_known_workspace() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    external_workspace_id = "workspace-import-ext"

    with session_factory() as session:
        session.execute(
            delete(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == external_workspace_id
            )
        )
        session.commit()

    workflow = ImportTeamWorkspaceWorkflow(session_factory=session_factory)
    first_id = workflow.run(
        ImportTeamWorkspaceInput(
            external_workspace_id=external_workspace_id,
            name="Workspace Old",
            seat_limit=5,
            workspace_status="active",
        )
    )
    second_id = workflow.run(
        ImportTeamWorkspaceInput(
            external_workspace_id=external_workspace_id,
            name="Workspace New",
            seat_limit=9,
            workspace_status="active",
        )
    )

    with session_factory() as session:
        rows = session.scalars(
            select(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == external_workspace_id
            )
        ).all()

        assert first_id == second_id
        assert len(rows) == 1
        assert rows[0].name == "Workspace New"
        assert rows[0].seat_limit == 9

        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == first_id))
        session.commit()


def test_build_codex_credential_uses_known_workspace_context() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-build-codex-account"
    workspace_id = "test-build-codex-workspace"

    with session_factory() as session:
        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.user_account_id == account_id
        ))
        session.execute(delete(UserAccountAuthModel).where(
            UserAccountAuthModel.user_account_id == account_id
        ))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(
            delete(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == "workspace-ext-1"
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email="build-codex@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-ext-1",
                name="Workspace 1",
                seat_limit=10,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountAuthModel(
                user_account_id=account_id,
                refresh_token="rt-1",
                refresh_token_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticOpenAIProvider()
    credential_id = BuildCodexCredentialWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(
        BuildCodexCredentialInput(
            user_account_id=account_id,
            team_workspace_id=workspace_id,
            codex_client_id="client-1",
        )
    )

    with session_factory() as session:
        credential = session.get(CodexOAuthCredentialModel, credential_id)

        assert provider.calls == [
            {
                "refresh_token": "rt-1",
                "external_workspace_id": "workspace-ext-1",
                "client_id": "client-1",
            }
        ]
        assert credential is not None
        assert credential.token_chatgpt_account_id == "workspace-ext-1"
        assert credential.account_id == "chatgpt-user-1"
        assert credential.access_token == "access-1"
        assert credential.refresh_token == "rt-2"

        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.id == credential_id
        ))
        session.execute(delete(UserAccountAuthModel).where(
            UserAccountAuthModel.user_account_id == account_id
        ))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_join_workspace_batch_accepts_invite_and_upserts_membership() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-join-batch-account"
    workspace_id = "test-join-batch-workspace"

    with session_factory() as session:
        session.execute(
            delete(WorkspaceJoinBatchItemModel).where(
                WorkspaceJoinBatchItemModel.user_account_id == account_id
            )
        )
        session.execute(
            delete(WorkspaceJoinBatchModel).where(
                WorkspaceJoinBatchModel.team_workspace_id == workspace_id
            )
        )
        session.execute(
            delete(MembershipModel).where(MembershipModel.user_account_id == account_id)
        )
        session.execute(
            delete(CodexOAuthCredentialModel).where(
                CodexOAuthCredentialModel.user_account_id == account_id
            )
        )
        session.execute(
            delete(UserAccountAuthModel).where(UserAccountAuthModel.user_account_id == account_id)
        )
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email="join-batch@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-join-ext",
                name="Workspace Join",
                seat_limit=10,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountAuthModel(
                user_account_id=account_id,
                refresh_token="rt-join",
                refresh_token_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticOpenAIProvider()
    batch_id = JoinWorkspaceBatchWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(
        JoinWorkspaceBatchInput(
            team_workspace_id=workspace_id,
            user_account_ids=[account_id],
            codex_client_id="client-join",
            batch_name="join batch",
            created_by="test",
        )
    )

    with session_factory() as session:
        batch = session.get(WorkspaceJoinBatchModel, batch_id)
        item = session.scalars(
            select(WorkspaceJoinBatchItemModel).where(
                WorkspaceJoinBatchItemModel.batch_id == batch_id
            )
        ).one()
        membership = session.scalars(
            select(MembershipModel).where(
                MembershipModel.user_account_id == account_id,
                MembershipModel.team_workspace_id == workspace_id,
            )
        ).one()

        assert batch is not None
        assert batch.batch_status == "success"
        assert batch.success_count == 1
        assert item.item_status == "token_generated"
        assert item.join_status == "accepted"
        assert item.membership_id == membership.id
        assert membership.membership_status == "active"
        assert membership.chatgpt_web_backend_access_token == "access-1"
        assert membership.chatgpt_web_backend_access_token_status == "active"
        assert {"accept_invite": {"access_token": "access-1", "team_id": "workspace-join-ext"}} in (
            provider.calls
        )

        session.execute(
            delete(WorkspaceJoinBatchItemModel).where(
                WorkspaceJoinBatchItemModel.batch_id == batch_id
            )
        )
        session.execute(delete(WorkspaceJoinBatchModel).where(WorkspaceJoinBatchModel.id == batch_id))
        session.execute(delete(MembershipModel).where(MembershipModel.id == membership.id))
        session.execute(
            delete(CodexOAuthCredentialModel).where(
                CodexOAuthCredentialModel.user_account_id == account_id
            )
        )
        session.execute(
            delete(UserAccountAuthModel).where(UserAccountAuthModel.user_account_id == account_id)
        )
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_activate_workspace_join_batch_supersedes_old_active_batch() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    workspace_id = "test-activate-batch-workspace"
    old_batch_id = "test-activate-batch-old"
    new_batch_id = "test-activate-batch-new"

    with session_factory() as session:
        session.execute(delete(WorkspaceJoinBatchModel).where(
            WorkspaceJoinBatchModel.team_workspace_id == workspace_id
        ))
        session.execute(
            delete(TeamWorkspaceModel).where(
                or_(
                    TeamWorkspaceModel.id == workspace_id,
                    TeamWorkspaceModel.external_workspace_id == "workspace-activate-ext",
                )
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-activate-ext",
                name="Workspace Activate",
                seat_limit=10,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            WorkspaceJoinBatchModel(
                id=old_batch_id,
                team_workspace_id=workspace_id,
                batch_status="success",
                activation_status="active",
                total_count=1,
                success_count=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            WorkspaceJoinBatchModel(
                id=new_batch_id,
                team_workspace_id=workspace_id,
                batch_status="success",
                activation_status="inactive",
                total_count=1,
                success_count=1,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    activated_id = ActivateWorkspaceJoinBatchWorkflow(session_factory=session_factory).run(
        batch_id=new_batch_id
    )

    with session_factory() as session:
        old_batch = session.get(WorkspaceJoinBatchModel, old_batch_id)
        new_batch = session.get(WorkspaceJoinBatchModel, new_batch_id)

        assert activated_id == new_batch_id
        assert old_batch is not None
        assert new_batch is not None
        assert old_batch.activation_status == "superseded"
        assert new_batch.activation_status == "active"

        session.execute(delete(WorkspaceJoinBatchModel).where(
            WorkspaceJoinBatchModel.team_workspace_id == workspace_id
        ))
        session.execute(
            delete(TeamWorkspaceModel).where(
                or_(
                    TeamWorkspaceModel.id == workspace_id,
                    TeamWorkspaceModel.external_workspace_id == "workspace-activate-ext",
                )
            )
        )
        session.commit()


def test_heartbeat_codex_credential_updates_status() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-heartbeat-account"
    workspace_id = "test-heartbeat-workspace"
    credential_id = "test-heartbeat-credential"

    with session_factory() as session:
        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.id == credential_id
        ))
        session.execute(
            delete(TeamWorkspaceModel).where(
                or_(
                    TeamWorkspaceModel.id == workspace_id,
                    TeamWorkspaceModel.external_workspace_id == "workspace-heartbeat-ext",
                )
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email="heartbeat@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-heartbeat-ext",
                name="Workspace Heartbeat",
                seat_limit=10,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            CodexOAuthCredentialModel(
                id=credential_id,
                user_account_id=account_id,
                team_workspace_id=workspace_id,
                codex_client_id="client-1",
                credential_status="active",
                account_id="chatgpt-user-1",
                token_chatgpt_account_id="workspace-heartbeat-ext",
                access_token="access-1",
                id_token="id-1",
                refresh_token="rt-1",
                expires_at=now + timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticOpenAIProvider()
    result_id = HeartbeatCodexCredentialWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(codex_credential_id=credential_id)

    with session_factory() as session:
        credential = session.get(CodexOAuthCredentialModel, credential_id)

        assert result_id == credential_id
        assert credential is not None
        assert credential.last_heartbeat_status == "ok"
        assert credential.last_heartbeat_error_code == ""
        assert provider.calls[-1] == {
            "heartbeat_access_token": "access-1",
            "team_id": "workspace-heartbeat-ext",
        }

        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.id == credential_id
        ))
        session.execute(
            delete(TeamWorkspaceModel).where(
                or_(
                    TeamWorkspaceModel.id == workspace_id,
                    TeamWorkspaceModel.external_workspace_id == "workspace-heartbeat-ext",
                )
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()


def test_join_workspace_batch_builds_credentials_and_updates_items() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-join-batch-account"
    workspace_id = "test-join-batch-workspace"

    with session_factory() as session:
        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.user_account_id == account_id
        ))
        session.execute(delete(WorkspaceJoinBatchModel).where(
            WorkspaceJoinBatchModel.team_workspace_id == workspace_id
        ))
        session.execute(delete(UserAccountAuthModel).where(
            UserAccountAuthModel.user_account_id == account_id
        ))
        session.execute(
            delete(TeamWorkspaceModel).where(
                or_(
                    TeamWorkspaceModel.id == workspace_id,
                    TeamWorkspaceModel.external_workspace_id == "workspace-join-ext",
                )
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email="join-batch@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-join-ext",
                name="Workspace Join",
                seat_limit=10,
                workspace_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountAuthModel(
                user_account_id=account_id,
                refresh_token="rt-1",
                refresh_token_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticOpenAIProvider()
    batch_id = JoinWorkspaceBatchWorkflow(
        session_factory=session_factory,
        openai_provider=provider,
    ).run(
        JoinWorkspaceBatchInput(
            team_workspace_id=workspace_id,
            user_account_ids=[account_id],
            codex_client_id="client-1",
            batch_name="batch 1",
            created_by="test",
        )
    )

    with session_factory() as session:
        batch = session.get(WorkspaceJoinBatchModel, batch_id)
        items = session.scalars(
            select(WorkspaceJoinBatchItemModel).where(
                WorkspaceJoinBatchItemModel.batch_id == batch_id
            )
        ).all()
        credentials = session.scalars(
            select(CodexOAuthCredentialModel).where(
                CodexOAuthCredentialModel.user_account_id == account_id,
                CodexOAuthCredentialModel.team_workspace_id == workspace_id,
            )
        ).all()

        assert batch is not None
        assert batch.batch_status == "success"
        assert batch.success_count == 1
        assert batch.failed_count == 0
        assert len(items) == 1
        assert items[0].item_status == "token_generated"
        assert items[0].token_status == "active"
        assert items[0].generated_chatgpt_web_backend_access_token == "access-1"
        assert len(credentials) == 1
        assert credentials[0].token_chatgpt_account_id == "workspace-join-ext"

        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.user_account_id == account_id
        ))
        session.execute(delete(WorkspaceJoinBatchItemModel).where(
            WorkspaceJoinBatchItemModel.batch_id == batch_id
        ))
        session.execute(delete(WorkspaceJoinBatchModel).where(WorkspaceJoinBatchModel.id == batch_id))
        session.execute(delete(UserAccountAuthModel).where(
            UserAccountAuthModel.user_account_id == account_id
        ))
        session.execute(
            delete(TeamWorkspaceModel).where(
                or_(
                    TeamWorkspaceModel.id == workspace_id,
                    TeamWorkspaceModel.external_workspace_id == "workspace-join-ext",
                )
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()
