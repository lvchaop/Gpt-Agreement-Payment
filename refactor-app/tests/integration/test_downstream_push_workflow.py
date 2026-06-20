from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from refactor_app.application.workflows.downstream import (
    PushCodexCredentialInput,
    PushCodexCredentialWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    DownstreamCodexPushRecordModel,
    MembershipModel,
    TeamWorkspaceModel,
    UserAccountModel,
    WorkspaceJoinBatchItemModel,
    WorkspaceJoinBatchModel,
)
from refactor_app.plugins.contracts import (
    DownstreamCodexPayload,
    DownstreamPushResult,
    HealthcheckResult,
)


class StaticDownstreamProvider:
    name = "static-downstream-test"

    def __init__(self) -> None:
        self.calls: list[DownstreamCodexPayload] = []

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok")

    def capabilities(self) -> list[str]:
        return ["downstream.cpa.push_codex_credential"]

    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult:
        self.calls.append(payload)
        return DownstreamPushResult(pushed=True, downstream_external_id=f"pushed-{len(self.calls)}")


def test_push_codex_credential_upserts_one_record_per_batch_item_and_provider() -> None:
    settings = Settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    now = datetime.now(UTC)
    account_id = "test-downstream-account"
    workspace_id = "test-downstream-workspace"
    membership_id = "test-downstream-membership"
    batch_id = "test-downstream-batch"
    batch_item_id = "test-downstream-batch-item"
    credential_id = "test-downstream-credential"

    with session_factory() as session:
        session.execute(
            delete(DownstreamCodexPushRecordModel).where(
                DownstreamCodexPushRecordModel.batch_item_id == batch_item_id
            )
        )
        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.id == credential_id
        ))
        session.execute(delete(WorkspaceJoinBatchItemModel).where(
            WorkspaceJoinBatchItemModel.id == batch_item_id
        ))
        session.execute(delete(WorkspaceJoinBatchModel).where(WorkspaceJoinBatchModel.id == batch_id))
        session.execute(delete(MembershipModel).where(MembershipModel.id == membership_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(
            delete(TeamWorkspaceModel).where(
                TeamWorkspaceModel.external_workspace_id == "workspace-downstream-ext"
            )
        )
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()

    with session_factory() as session:
        session.add(
            UserAccountModel(
                id=account_id,
                email="downstream@example.test",
                account_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            TeamWorkspaceModel(
                id=workspace_id,
                provider="openai_chatgpt",
                external_workspace_id="workspace-downstream-ext",
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
            MembershipModel(
                id=membership_id,
                user_account_id=account_id,
                team_workspace_id=workspace_id,
                membership_status="active",
                chatgpt_web_backend_access_token_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            WorkspaceJoinBatchModel(
                id=batch_id,
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

    with session_factory() as session:
        session.add(
            WorkspaceJoinBatchItemModel(
                id=batch_item_id,
                batch_id=batch_id,
                user_account_id=account_id,
                team_workspace_id=workspace_id,
                membership_id=membership_id,
                item_status="token_generated",
                push_status="pending",
                plan_tag="team",
                plan_type="team",
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CodexOAuthCredentialModel(
                id=credential_id,
                user_account_id=account_id,
                team_workspace_id=workspace_id,
                codex_client_id="client-1",
                credential_status="active",
                account_id="chatgpt-user-1",
                token_chatgpt_account_id="workspace-downstream-ext",
                access_token="access-1",
                id_token="id-1",
                refresh_token="rt-1",
                expires_at=now + timedelta(hours=1),
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    provider = StaticDownstreamProvider()
    workflow = PushCodexCredentialWorkflow(
        session_factory=session_factory,
        downstream_provider=provider,
    )
    input_ = PushCodexCredentialInput(
        batch_item_id=batch_item_id,
        user_account_id=account_id,
        team_workspace_id=workspace_id,
        membership_id=membership_id,
        downstream_provider="cpa",
        codex_client_id="client-1",
        request_endpoint="/v0/management/auth-files",
    )

    first_record_id = workflow.run(input_)
    second_record_id = workflow.run(input_)

    with session_factory() as session:
        records = session.scalars(
            select(DownstreamCodexPushRecordModel).where(
                DownstreamCodexPushRecordModel.batch_item_id == batch_item_id,
                DownstreamCodexPushRecordModel.downstream_provider == "cpa",
            )
        ).all()
        batch_item = session.get(WorkspaceJoinBatchItemModel, batch_item_id)

        assert first_record_id == second_record_id
        assert len(records) == 1
        assert records[0].push_status == "pushed"
        assert records[0].downstream_external_id == "pushed-2"
        assert records[0].downstream_chatgpt_account_id == "workspace-downstream-ext"
        assert records[0].token_chatgpt_account_id == "workspace-downstream-ext"
        assert batch_item is not None
        assert batch_item.push_status == "pushed"
        assert batch_item.downstream_external_id == "pushed-2"
        assert provider.calls[0].downstream_chatgpt_account_id == "workspace-downstream-ext"
        assert provider.calls[0].token_chatgpt_account_id == "workspace-downstream-ext"

        session.execute(
            delete(DownstreamCodexPushRecordModel).where(
                DownstreamCodexPushRecordModel.batch_item_id == batch_item_id
            )
        )
        session.execute(delete(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.id == credential_id
        ))
        session.execute(delete(WorkspaceJoinBatchItemModel).where(
            WorkspaceJoinBatchItemModel.id == batch_item_id
        ))
        session.execute(delete(WorkspaceJoinBatchModel).where(WorkspaceJoinBatchModel.id == batch_id))
        session.execute(delete(MembershipModel).where(MembershipModel.id == membership_id))
        session.execute(delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id == workspace_id))
        session.execute(delete(UserAccountModel).where(UserAccountModel.id == account_id))
        session.commit()
