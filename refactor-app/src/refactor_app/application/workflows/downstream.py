from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.domain.enums import BatchItemStatus, PushStatus
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    TeamWorkspaceModel,
    UserAccountModel,
    WorkspaceJoinBatchItemModel,
)
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamProvider


class DownstreamWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class PushCodexCredentialInput:
    batch_item_id: str
    user_account_id: str
    team_workspace_id: str
    membership_id: str | None
    downstream_provider: str
    codex_client_id: str
    request_endpoint: str = ""


class PushCodexCredentialWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        downstream_provider: DownstreamProvider,
    ) -> None:
        self._session_factory = session_factory
        self._downstream_provider = downstream_provider

    def run(self, input_: PushCodexCredentialInput) -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            repos = _required_repositories(uow)
            user = repos["user_accounts"].get(input_.user_account_id)
            workspace = repos["team_workspaces"].get(input_.team_workspace_id)
            batch_item = repos["workspace_join_batch_items"].get(input_.batch_item_id)
            credential = None
            if batch_item is not None and batch_item.codex_credential_id:
                credential = repos["codex_oauth_credentials"].get(batch_item.codex_credential_id)
            if credential is None:
                credential = repos["codex_oauth_credentials"].get_current(
                    user_account_id=input_.user_account_id,
                    team_workspace_id=input_.team_workspace_id,
                    codex_client_id=input_.codex_client_id,
                )
            _validate_loaded(
                user=user,
                workspace=workspace,
                batch_item=batch_item,
                credential=credential,
                input_=input_,
            )
            assert user is not None
            assert workspace is not None
            assert batch_item is not None
            assert credential is not None

            payload = downstream_payload(
                user=user,
                workspace=workspace,
                credential=credential,
                batch_item=batch_item,
            )
            result = self._downstream_provider.push_codex_credential(payload)
            push_status = PushStatus.PUSHED.value if result.pushed else PushStatus.FAILED.value
            error_code = result.error_code if not result.pushed else ""
            error_message = result.error_message if not result.pushed else ""

            record = repos["downstream_codex_push_records"].upsert_from_values(
                {
                    "id": f"downstream-push-{uuid4()}",
                    "batch_item_id": input_.batch_item_id,
                    "codex_credential_id": credential.id,
                    "user_account_id": input_.user_account_id,
                    "team_workspace_id": input_.team_workspace_id,
                    "membership_id": input_.membership_id,
                    "downstream_provider": input_.downstream_provider,
                    "downstream_external_id": result.downstream_external_id,
                    "push_status": push_status,
                    "codex_client_id": credential.codex_client_id,
                    "codex_account_id": credential.account_id,
                    "codex_email": user.email,
                    "downstream_chatgpt_account_id": workspace.external_workspace_id,
                    "token_chatgpt_account_id": credential.token_chatgpt_account_id,
                    "codex_token_expires_at": credential.expires_at,
                    "request_endpoint": input_.request_endpoint,
                    "error_code": error_code,
                    "error_message": error_message,
                    "created_at": now,
                    "updated_at": now,
                }
            )

            batch_item.push_status = push_status
            batch_item.downstream_provider = input_.downstream_provider
            batch_item.downstream_external_id = result.downstream_external_id
            batch_item.failure_code = error_code
            batch_item.failure_message = error_message
            if result.pushed:
                batch_item.item_status = BatchItemStatus.PUSHED.value
            else:
                batch_item.item_status = BatchItemStatus.FAILED.value
            batch_item.updated_at = now

            return record.id


def downstream_payload(
    *,
    user: UserAccountModel,
    workspace: TeamWorkspaceModel,
    credential: CodexOAuthCredentialModel,
    batch_item: WorkspaceJoinBatchItemModel | None,
) -> DownstreamCodexPayload:
    if credential.token_chatgpt_account_id != workspace.external_workspace_id:
        raise DownstreamWorkflowError("workspace_mismatch")
    return DownstreamCodexPayload(
        access_token=credential.access_token,
        id_token=credential.id_token,
        refresh_token=credential.refresh_token,
        email=user.email,
        account_id=credential.account_id,
        downstream_chatgpt_account_id=workspace.external_workspace_id,
        token_chatgpt_account_id=credential.token_chatgpt_account_id,
        client_id=credential.codex_client_id,
        expires_at=credential.expires_at,
        plan_tag=batch_item.plan_tag if batch_item is not None else workspace.plan_type,
        plan_type=batch_item.plan_type if batch_item is not None else workspace.plan_type,
    )


def _required_repositories(uow: UnitOfWork) -> dict:
    names = {
        "user_accounts": uow.user_accounts,
        "team_workspaces": uow.team_workspaces,
        "workspace_join_batch_items": uow.workspace_join_batch_items,
        "codex_oauth_credentials": uow.codex_oauth_credentials,
        "downstream_codex_push_records": uow.downstream_codex_push_records,
    }
    missing = [name for name, repo in names.items() if repo is None]
    if missing:
        raise DownstreamWorkflowError(f"repositories not initialized: {','.join(missing)}")
    return names


def _validate_loaded(
    *,
    user: UserAccountModel | None,
    workspace: TeamWorkspaceModel | None,
    batch_item: WorkspaceJoinBatchItemModel | None,
    credential: CodexOAuthCredentialModel | None,
    input_: PushCodexCredentialInput,
) -> None:
    if user is None:
        raise DownstreamWorkflowError("missing_user_account")
    if workspace is None:
        raise DownstreamWorkflowError("missing_workspace")
    if batch_item is None:
        raise DownstreamWorkflowError("missing_batch_item")
    if batch_item.user_account_id != input_.user_account_id:
        raise DownstreamWorkflowError("batch_item_user_mismatch")
    if batch_item.team_workspace_id != input_.team_workspace_id:
        raise DownstreamWorkflowError("batch_item_workspace_mismatch")
    if credential is None:
        raise DownstreamWorkflowError("missing_codex_credential")
