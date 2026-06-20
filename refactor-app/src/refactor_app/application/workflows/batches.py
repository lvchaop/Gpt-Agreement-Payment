from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from refactor_app.application.jobs.queue import WorkQueue
from refactor_app.application.workflows.codex_credentials import (
    BuildCodexCredentialInput,
    BuildCodexCredentialWorkflow,
)
from refactor_app.domain.enums import (
    ActivationStatus,
    BatchItemStatus,
    BatchStatus,
    CredentialStatus,
    MembershipStatus,
    PushStatus,
    TokenStatus,
)
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    MembershipModel,
    WorkspaceJoinBatchItemModel,
    WorkspaceJoinBatchModel,
)
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin


class BatchWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class JoinWorkspaceBatchInput:
    team_workspace_id: str
    user_account_ids: list[str]
    codex_client_id: str
    batch_name: str = ""
    created_by: str = ""
    _job_id: str = ""


@dataclass(frozen=True)
class ProcessWorkspaceJoinBatchItemInput:
    batch_id: str
    batch_item_id: str
    user_account_id: str
    team_workspace_id: str
    codex_client_id: str


@dataclass(frozen=True)
class CreateWorkspaceBatchFromCredentialsInput:
    team_workspace_id: str
    codex_credential_ids: list[str]
    batch_name: str = ""
    created_by: str = ""


class JoinWorkspaceBatchWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider
        self._credential_workflow = BuildCodexCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=openai_provider,
            mail_provider=mail_provider,
        )

    def run(self, input_: JoinWorkspaceBatchInput) -> str:
        if not input_.team_workspace_id:
            raise BatchWorkflowError("team_workspace_id is required")
        if not input_.user_account_ids:
            raise BatchWorkflowError("user_account_ids is required")
        if not input_.codex_client_id:
            raise BatchWorkflowError("codex_client_id is required")

        now = datetime.now(UTC)
        batch_id = f"workspace-join-batch-{uuid4()}"
        source_job_id = input_._job_id
        with UnitOfWork(self._session_factory) as uow:
            if uow.workspace_join_batches is None:
                raise BatchWorkflowError("batch repository is not initialized")
            if uow.workspace_join_batch_items is None:
                raise BatchWorkflowError("batch item repository is not initialized")
            if uow.team_workspaces is None:
                raise BatchWorkflowError("team workspace repository is not initialized")
            if uow.team_workspaces.get(input_.team_workspace_id) is None:
                raise BatchWorkflowError("team workspace not found")

            uow.workspace_join_batches.add(
                WorkspaceJoinBatchModel(
                    id=batch_id,
                    team_workspace_id=input_.team_workspace_id,
                    batch_name=input_.batch_name,
                    batch_status=BatchStatus.RUNNING.value,
                    activation_status=ActivationStatus.INACTIVE.value,
                    source_type="job",
                    source_job_id=source_job_id,
                    created_by=input_.created_by,
                    started_at=now,
                    total_count=len(input_.user_account_ids),
                    created_at=now,
                    updated_at=now,
                )
            )
            if uow.session is None:
                raise BatchWorkflowError("session is not initialized")
            uow.session.flush()
            for user_account_id in input_.user_account_ids:
                batch_item_id = f"workspace-join-batch-item-{uuid4()}"
                uow.workspace_join_batch_items.add(
                    WorkspaceJoinBatchItemModel(
                        id=batch_item_id,
                        batch_id=batch_id,
                        user_account_id=user_account_id,
                        team_workspace_id=input_.team_workspace_id,
                        item_status=BatchItemStatus.PENDING.value,
                        push_status=PushStatus.PENDING.value,
                        created_at=now,
                        updated_at=now,
                    )
                )
                if source_job_id:
                    WorkQueue(uow.session).enqueue(
                        job_id=source_job_id,
                        work_type="workspace_join_batch.item",
                        input_json={
                            "batch_id": batch_id,
                            "batch_item_id": batch_item_id,
                            "user_account_id": user_account_id,
                            "team_workspace_id": input_.team_workspace_id,
                            "codex_client_id": input_.codex_client_id,
                        },
                    )

        return batch_id


class CreateWorkspaceBatchFromCredentialsWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, input_: CreateWorkspaceBatchFromCredentialsInput) -> str:
        credential_ids = [item.strip() for item in input_.codex_credential_ids if item.strip()]
        if not input_.team_workspace_id:
            raise BatchWorkflowError("team_workspace_id is required")
        if not credential_ids:
            raise BatchWorkflowError("codex_credential_ids is required")

        now = datetime.now(UTC)
        batch_id = f"workspace-join-batch-{uuid4()}"
        with UnitOfWork(self._session_factory) as uow:
            if uow.session is None:
                raise BatchWorkflowError("session is not initialized")
            if uow.workspace_join_batches is None:
                raise BatchWorkflowError("batch repository is not initialized")
            if uow.workspace_join_batch_items is None:
                raise BatchWorkflowError("batch item repository is not initialized")
            if uow.team_workspaces is None:
                raise BatchWorkflowError("team workspace repository is not initialized")

            workspace = uow.team_workspaces.get(input_.team_workspace_id)
            if workspace is None:
                raise BatchWorkflowError("team workspace not found")

            credentials = (
                uow.session.query(CodexOAuthCredentialModel)
                .filter(CodexOAuthCredentialModel.id.in_(credential_ids))
                .with_for_update()
                .all()
            )
            by_id = {credential.id: credential for credential in credentials}
            missing_ids = [
                credential_id for credential_id in credential_ids if credential_id not in by_id
            ]
            if missing_ids:
                raise BatchWorkflowError(f"codex credentials not found: {','.join(missing_ids)}")

            for credential_id in credential_ids:
                credential = by_id[credential_id]
                _validate_credential_for_batch(
                    credential=credential,
                    team_workspace_id=input_.team_workspace_id,
                    external_workspace_id=workspace.external_workspace_id,
                    now=now,
                )

            uow.workspace_join_batches.add(
                WorkspaceJoinBatchModel(
                    id=batch_id,
                    team_workspace_id=input_.team_workspace_id,
                    batch_name=input_.batch_name,
                    batch_status=BatchStatus.SUCCESS.value,
                    activation_status=ActivationStatus.INACTIVE.value,
                    source_type="codex_credentials",
                    created_by=input_.created_by,
                    started_at=now,
                    finished_at=now,
                    total_count=len(credential_ids),
                    success_count=len(credential_ids),
                    failed_count=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            uow.session.flush()

            for credential_id in credential_ids:
                credential = by_id[credential_id]
                membership = None
                if uow.memberships is not None:
                    membership = uow.memberships.get_by_user_and_workspace(
                        user_account_id=credential.user_account_id,
                        team_workspace_id=credential.team_workspace_id,
                    )
                uow.workspace_join_batch_items.add(
                    WorkspaceJoinBatchItemModel(
                        id=f"workspace-join-batch-item-{uuid4()}",
                        batch_id=batch_id,
                        user_account_id=credential.user_account_id,
                        team_workspace_id=credential.team_workspace_id,
                        membership_id=membership.id if membership is not None else None,
                        codex_credential_id=credential.id,
                        item_status=BatchItemStatus.TOKEN_GENERATED.value,
                        batch_binding_status="active",
                        join_status="authorized",
                        token_status=TokenStatus.ACTIVE.value,
                        push_status=PushStatus.PENDING.value,
                        generated_chatgpt_web_backend_access_token=credential.access_token,
                        generated_chatgpt_web_backend_id_token=credential.id_token,
                        generated_chatgpt_web_backend_token_expires_at=credential.expires_at,
                        created_at=now,
                        updated_at=now,
                    )
                )

        return batch_id


class ProcessWorkspaceJoinBatchItemWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider
        self._credential_workflow = BuildCodexCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=openai_provider,
            mail_provider=mail_provider,
        )

    def run(self, input_: ProcessWorkspaceJoinBatchItemInput) -> str:
        try:
            credential_id = self._credential_workflow.run(
                BuildCodexCredentialInput(
                    user_account_id=input_.user_account_id,
                    team_workspace_id=input_.team_workspace_id,
                    codex_client_id=input_.codex_client_id,
                )
            )
        except Exception as exc:
            self._mark_batch_item_failed(
                input_.batch_item_id,
                failure_code="credential_build_failed",
                message=str(exc),
            )
            self._finish_batch_if_complete(input_.batch_id)
            raise

        self._mark_batch_item_token_generated(input_.batch_item_id, credential_id=credential_id)
        self._finish_batch_if_complete(input_.batch_id)
        return input_.batch_item_id

    def _mark_batch_item_token_generated(
        self,
        batch_item_id: str,
        *,
        credential_id: str,
    ) -> None:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.session is None:
                raise BatchWorkflowError("session is not initialized")
            item = _get_batch_item_by_id(uow, batch_item_id=batch_item_id)
            item.item_status = BatchItemStatus.TOKEN_GENERATED.value
            item.token_status = "active"
            item.failure_code = ""
            item.failure_message = ""
            item.updated_at = now
            credential = uow.codex_oauth_credentials.get(credential_id)
            if credential is not None:
                workspace = uow.team_workspaces.get(credential.team_workspace_id)
                if workspace is None:
                    raise BatchWorkflowError("team workspace not found")
                self._openai_provider.accept_invite(
                    access_token=credential.access_token,
                    team_id=workspace.external_workspace_id,
                )
                membership = _upsert_active_membership(
                    uow,
                    user_account_id=credential.user_account_id,
                    team_workspace_id=credential.team_workspace_id,
                    access_token=credential.access_token,
                    id_token=credential.id_token,
                    expires_at=credential.expires_at,
                    now=now,
                )
                item.membership_id = membership.id
                item.generated_chatgpt_web_backend_access_token = credential.access_token
                item.generated_chatgpt_web_backend_id_token = credential.id_token
                item.generated_chatgpt_web_backend_token_expires_at = credential.expires_at
                item.join_status = "accepted"

    def _mark_batch_item_failed(
        self,
        batch_item_id: str,
        *,
        failure_code: str,
        message: str,
    ) -> None:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            item = _get_batch_item_by_id(uow, batch_item_id=batch_item_id)
            item.item_status = BatchItemStatus.FAILED.value
            item.token_status = "error"
            item.failure_code = failure_code
            item.failure_message = message[:500]
            item.updated_at = now

    def _finish_batch_if_complete(self, batch_id: str) -> None:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.workspace_join_batches is None:
                raise BatchWorkflowError("batch repository is not initialized")
            if uow.session is None:
                raise BatchWorkflowError("session is not initialized")
            batch = uow.workspace_join_batches.get(batch_id)
            if batch is None:
                raise BatchWorkflowError(f"batch not found: {batch_id}")
            items = (
                uow.session.query(WorkspaceJoinBatchItemModel)
                .filter_by(batch_id=batch_id)
                .all()
            )
            terminal_statuses = {
                BatchItemStatus.TOKEN_GENERATED.value,
                BatchItemStatus.JOINED.value,
                BatchItemStatus.PUSHED.value,
                BatchItemStatus.FAILED.value,
                BatchItemStatus.SKIPPED.value,
            }
            if any(item.item_status not in terminal_statuses for item in items):
                batch.updated_at = now
                return
            success_count = sum(
                1
                for item in items
                if item.item_status
                in {
                    BatchItemStatus.TOKEN_GENERATED.value,
                    BatchItemStatus.JOINED.value,
                    BatchItemStatus.PUSHED.value,
                }
            )
            failed_count = sum(
                1 for item in items if item.item_status == BatchItemStatus.FAILED.value
            )
            batch.success_count = success_count
            batch.failed_count = failed_count
            batch.finished_at = now
            if failed_count == 0:
                batch.batch_status = BatchStatus.SUCCESS.value
            elif success_count > 0:
                batch.batch_status = BatchStatus.PARTIAL_SUCCESS.value
            else:
                batch.batch_status = BatchStatus.FAILED.value
            batch.updated_at = now


class ActivateWorkspaceJoinBatchWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, *, batch_id: str) -> str:
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.workspace_join_batches is None:
                raise BatchWorkflowError("batch repository is not initialized")

            batch = uow.workspace_join_batches.get(batch_id)
            if batch is None:
                raise BatchWorkflowError(f"batch not found: {batch_id}")
            if batch.batch_status not in {
                BatchStatus.SUCCESS.value,
                BatchStatus.PARTIAL_SUCCESS.value,
            }:
                raise BatchWorkflowError("batch_status does not allow activation")

            old_active_batches = uow.workspace_join_batches.active_for_workspace(
                batch.team_workspace_id
            )
            for old_batch in old_active_batches:
                if old_batch.id != batch.id:
                    old_batch.activation_status = ActivationStatus.SUPERSEDED.value
                    old_batch.deactivated_at = now
                    old_batch.updated_at = now
                    _release_batch_items(uow, batch_id=old_batch.id, now=now)

            if uow.session is None:
                raise BatchWorkflowError("session is not initialized")
            uow.session.flush()

            batch.activation_status = ActivationStatus.ACTIVE.value
            batch.activated_at = now
            batch.updated_at = now
            return batch.id


def _get_batch_item(
    uow: UnitOfWork,
    *,
    batch_id: str,
    user_account_id: str,
) -> WorkspaceJoinBatchItemModel:
    if uow.session is None:
        raise BatchWorkflowError("session is not initialized")
    item = uow.session.query(WorkspaceJoinBatchItemModel).filter_by(
        batch_id=batch_id,
        user_account_id=user_account_id,
    ).one_or_none()
    if item is None:
        raise BatchWorkflowError("batch item not found")
    return item


def _get_batch_item_by_id(
    uow: UnitOfWork,
    *,
    batch_item_id: str,
) -> WorkspaceJoinBatchItemModel:
    if uow.session is None:
        raise BatchWorkflowError("session is not initialized")
    item = uow.session.get(WorkspaceJoinBatchItemModel, batch_item_id)
    if item is None:
        raise BatchWorkflowError("batch item not found")
    return item


def _upsert_active_membership(
    uow: UnitOfWork,
    *,
    user_account_id: str,
    team_workspace_id: str,
    access_token: str,
    id_token: str,
    expires_at: datetime | None,
    now: datetime,
) -> MembershipModel:
    if uow.memberships is None:
        raise BatchWorkflowError("membership repository is not initialized")
    membership = uow.memberships.get_by_user_and_workspace(
        user_account_id=user_account_id,
        team_workspace_id=team_workspace_id,
    )
    if membership is None:
        membership = MembershipModel(
            id=f"membership-{uuid4()}",
            user_account_id=user_account_id,
            team_workspace_id=team_workspace_id,
            membership_status=MembershipStatus.ACTIVE.value,
            chatgpt_web_backend_access_token=access_token,
            chatgpt_web_backend_id_token=id_token,
            chatgpt_web_backend_access_token_expires_at=expires_at,
            chatgpt_web_backend_access_token_status=TokenStatus.ACTIVE.value,
            last_chatgpt_web_backend_token_refresh_at=now,
            created_at=now,
            updated_at=now,
        )
        uow.memberships.add(membership)
    else:
        membership.membership_status = MembershipStatus.ACTIVE.value
        membership.chatgpt_web_backend_access_token = access_token
        membership.chatgpt_web_backend_id_token = id_token
        membership.chatgpt_web_backend_access_token_expires_at = expires_at
        membership.chatgpt_web_backend_access_token_status = TokenStatus.ACTIVE.value
        membership.last_chatgpt_web_backend_token_refresh_at = now
        membership.failure_code = ""
        membership.failure_message = ""
        membership.updated_at = now
    return membership


def _validate_credential_for_batch(
    *,
    credential: CodexOAuthCredentialModel,
    team_workspace_id: str,
    external_workspace_id: str,
    now: datetime,
) -> None:
    if credential.team_workspace_id != team_workspace_id:
        raise BatchWorkflowError(f"credential workspace mismatch: {credential.id}")
    if credential.credential_status != CredentialStatus.ACTIVE.value:
        raise BatchWorkflowError(f"credential is not active: {credential.id}")
    if credential.expires_at is None or credential.expires_at <= now:
        raise BatchWorkflowError(f"credential expired: {credential.id}")
    if credential.token_chatgpt_account_id != external_workspace_id:
        raise BatchWorkflowError(f"credential token workspace mismatch: {credential.id}")
    if not credential.access_token:
        raise BatchWorkflowError(f"credential missing access_token: {credential.id}")


def _release_batch_items(uow: UnitOfWork, *, batch_id: str, now: datetime) -> None:
    if uow.session is None:
        raise BatchWorkflowError("session is not initialized")
    items = (
        uow.session.query(WorkspaceJoinBatchItemModel)
        .filter_by(batch_id=batch_id, batch_binding_status="active")
        .all()
    )
    for item in items:
        item.batch_binding_status = "released"
        item.updated_at = now
