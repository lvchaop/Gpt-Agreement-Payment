from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.downstream import (
    downstream_import_chatgpt_account_id,
    downstream_payload,
)
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    DownstreamChannelModel,
    DownstreamCodexPushRecordModel,
    TeamWorkspaceModel,
    UserAccountModel,
    WorkspaceAutomationStateModel,
)
from refactor_app.plugins.downstream_cpa.client import CpaClientConfig
from refactor_app.plugins.downstream_cpa.plugin import CpaDownstreamPlugin
from refactor_app.plugins.downstream_custom_http.client import CustomHttpClientConfig
from refactor_app.plugins.downstream_custom_http.plugin import CustomHttpDownstreamPlugin
from refactor_app.plugins.downstream_local_sub2api.client import LocalSub2ApiClientConfig
from refactor_app.plugins.downstream_local_sub2api.plugin import LocalSub2ApiDownstreamPlugin
from refactor_app.plugins.downstream_sub2api.client import Sub2ApiClientConfig
from refactor_app.plugins.downstream_sub2api.plugin import Sub2ApiDownstreamPlugin

MAX_DOWNSTREAM_PUSH_ATTEMPTS = 3


class DirectPushWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class PushCodexCredentialDirectInput:
    codex_credential_id: str
    downstream_channel_id: str
    request_endpoint: str = ""


class PushCodexCredentialDirectWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, input_: PushCodexCredentialDirectInput) -> str:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            credential = session.get(CodexOAuthCredentialModel, input_.codex_credential_id)
            channel = session.scalars(
                select(DownstreamChannelModel)
                .where(DownstreamChannelModel.id == input_.downstream_channel_id)
                .with_for_update()
            ).first()
            if credential is None:
                raise DirectPushWorkflowError("missing_codex_credential")
            if channel is None:
                raise DirectPushWorkflowError("missing_downstream_channel")
            record = session.scalars(
                select(DownstreamCodexPushRecordModel)
                .where(DownstreamCodexPushRecordModel.codex_credential_id == credential.id)
                .with_for_update()
            ).first()
            is_retry = (
                record is not None
                and record.push_status == "failed"
                and record.downstream_channel_id == channel.id
            )
            _validate_pushable(
                session=session,
                credential=credential,
                channel=channel,
                require_balance=not is_retry,
            )
            if record is not None:
                if record.downstream_channel_id and record.downstream_channel_id != channel.id:
                    raise DirectPushWorkflowError("credential_already_allocated_to_other_channel")
                if record.push_status in {"pushing", "pushed", "used"}:
                    raise DirectPushWorkflowError(f"credential_push_status_{record.push_status}")
                record.push_attempt_count = (
                    int(record.push_attempt_count or 0) + 1 if is_retry else 1
                )
            if not is_retry and channel.push_balance <= 0:
                raise DirectPushWorkflowError("downstream_channel_balance_exhausted")
            active_slots = _active_downstream_slot_count(session, channel.id)
            allowed_slots = _allowed_downstream_active_slots(session, channel)
            if (not is_retry) and active_slots >= allowed_slots:
                raise DirectPushWorkflowError("downstream_channel_active_slots_exhausted")

            user = session.get(UserAccountModel, credential.user_account_id)
            workspace = session.get(TeamWorkspaceModel, credential.team_workspace_id)
            if user is None:
                raise DirectPushWorkflowError("missing_user_account")
            if workspace is None:
                raise DirectPushWorkflowError("missing_workspace")
            payload = downstream_payload(
                user=user,
                workspace=workspace,
                credential=credential,
                batch_item=None,
            )

            if not is_retry:
                channel.push_balance -= 1
                channel.claimed_push_count += 1
                channel.updated_at = now
            credential.push_lifecycle_status = "pushing"
            credential.updated_at = now
            if record is None:
                record = DownstreamCodexPushRecordModel(
                    id=f"downstream-push-{uuid4()}",
                    batch_item_id=None,
                    codex_credential_id=credential.id,
                    downstream_channel_id=channel.id,
                    user_account_id=credential.user_account_id,
                    team_workspace_id=credential.team_workspace_id,
                    membership_id=None,
                    downstream_provider=channel.provider_type,
                    downstream_external_id="",
                    push_status="pushing",
                    codex_client_id=credential.codex_client_id,
                    codex_account_id=credential.account_id,
                    codex_email=user.email,
                    downstream_chatgpt_account_id=downstream_import_chatgpt_account_id(
                        user_account_id=user.id,
                        workspace_id=workspace.id,
                    ),
                    token_chatgpt_account_id=credential.token_chatgpt_account_id,
                    codex_token_expires_at=credential.expires_at,
                    request_endpoint=input_.request_endpoint,
                    push_attempt_count=1,
                    usage_percent=0,
                    usage_status="unknown",
                    error_code="",
                    error_message="",
                    created_at=now,
                    updated_at=now,
                )
                session.add(record)
            else:
                record.downstream_channel_id = channel.id
                record.downstream_provider = channel.provider_type
                record.push_status = "pushing"
                record.error_code = ""
                record.error_message = ""
                record.request_endpoint = input_.request_endpoint
                record.updated_at = now
            session.commit()

        try:
            provider = _provider_from_channel(channel)
            result = provider.push_codex_credential(payload)
        except Exception as exc:
            _mark_push_failed(
                session_factory=self._session_factory,
                codex_credential_id=input_.codex_credential_id,
                downstream_channel_id=input_.downstream_channel_id,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        with self._session_factory() as session:
            record = session.scalars(
                select(DownstreamCodexPushRecordModel)
                .where(DownstreamCodexPushRecordModel.codex_credential_id == input_.codex_credential_id)
                .with_for_update()
            ).one()
            credential = session.get(CodexOAuthCredentialModel, input_.codex_credential_id)
            channel = session.get(DownstreamChannelModel, input_.downstream_channel_id)
            finished_at = datetime.now(UTC)
            record.downstream_external_id = result.downstream_external_id
            record.updated_at = finished_at
            if result.pushed:
                record.push_status = "pushed"
                record.usage_status = "active"
                record.error_code = ""
                record.error_message = ""
                if credential is not None:
                    credential.push_lifecycle_status = "pushed"
                    credential.failure_code = ""
                    credential.failure_message = ""
                    credential.updated_at = finished_at
                if channel is not None:
                    channel.pushed_count += 1
                    channel.updated_at = finished_at
                state = (
                    session.get(WorkspaceAutomationStateModel, record.team_workspace_id)
                    if record.team_workspace_id
                    else None
                )
                if state is not None:
                    state.last_push_at = finished_at
                    state.updated_at = finished_at
            else:
                _apply_push_failure(
                    record=record,
                    credential=credential,
                    channel=channel,
                    error_code=result.error_code,
                    error_message=result.error_message,
                    finished_at=finished_at,
                )
            session.commit()
            if not result.pushed:
                raise DirectPushWorkflowError(result.error_code or "downstream_push_failed")
            return record.id


def _mark_push_failed(
    *,
    session_factory: Callable[[], Session],
    codex_credential_id: str,
    downstream_channel_id: str,
    error_code: str,
    error_message: str,
) -> None:
    with session_factory() as session:
        record = session.scalars(
            select(DownstreamCodexPushRecordModel)
            .where(DownstreamCodexPushRecordModel.codex_credential_id == codex_credential_id)
            .with_for_update()
        ).first()
        credential = session.get(CodexOAuthCredentialModel, codex_credential_id)
        channel = session.get(DownstreamChannelModel, downstream_channel_id)
        finished_at = datetime.now(UTC)
        if record is not None:
            _apply_push_failure(
                record=record,
                credential=credential,
                channel=channel,
                error_code=error_code,
                error_message=error_message,
                finished_at=finished_at,
            )
        session.commit()


def _apply_push_failure(
    *,
    record: DownstreamCodexPushRecordModel,
    credential: CodexOAuthCredentialModel | None,
    channel: DownstreamChannelModel | None,
    error_code: str,
    error_message: str,
    finished_at: datetime,
) -> None:
    code = (error_code or "downstream_push_failed")[:200]
    message = (error_message or "")[:1000]
    attempts = int(record.push_attempt_count or 0)
    if attempts >= MAX_DOWNSTREAM_PUSH_ATTEMPTS:
        _refund_skipped_push_quota(record=record, channel=channel, finished_at=finished_at)
        record.downstream_channel_id = None
        record.push_status = "skipped"
        record.error_code = "push_retry_exhausted_released"
        record.error_message = (
            f"released after {attempts} failed push attempts; "
            f"last_error={code}: {message}"
        )[:1000]
        if credential is not None:
            credential.push_lifecycle_status = "pending_push"
            credential.failure_code = record.error_code
            credential.failure_message = record.error_message
            credential.updated_at = finished_at
    else:
        record.push_status = "failed"
        record.error_code = code
        record.error_message = message
        if credential is not None:
            credential.push_lifecycle_status = "failed"
            credential.failure_code = code
            credential.failure_message = message
            credential.updated_at = finished_at
    record.updated_at = finished_at
    if channel is not None:
        channel.failed_push_count += 1
        channel.updated_at = finished_at


def _refund_skipped_push_quota(
    *,
    record: DownstreamCodexPushRecordModel,
    channel: DownstreamChannelModel | None,
    finished_at: datetime,
) -> None:
    if channel is None:
        return
    if record.downstream_channel_id != channel.id:
        return
    if record.push_status not in {"pushing", "pushed", "failed"}:
        return
    channel.push_balance = max(0, int(channel.push_balance or 0)) + 1
    channel.claimed_push_count = max(0, int(channel.claimed_push_count or 0) - 1)
    channel.updated_at = finished_at


def _validate_pushable(
    *,
    session: Session,
    credential: CodexOAuthCredentialModel,
    channel: DownstreamChannelModel,
    require_balance: bool = True,
) -> None:
    if not channel.enabled:
        raise DirectPushWorkflowError("downstream_channel_disabled")
    if channel.max_active_slots <= 0:
        raise DirectPushWorkflowError("downstream_channel_active_slots_exhausted")
    if require_balance and channel.push_balance <= 0:
        raise DirectPushWorkflowError("downstream_channel_balance_exhausted")
    if credential.credential_status != "active":
        raise DirectPushWorkflowError("credential_not_active")
    if credential.last_heartbeat_status != "ok":
        raise DirectPushWorkflowError("credential_heartbeat_not_ok")
    if not credential.access_token or not credential.refresh_token:
        raise DirectPushWorkflowError("credential_token_missing")
    workspace = session.get(TeamWorkspaceModel, credential.team_workspace_id)
    if workspace is None:
        raise DirectPushWorkflowError("missing_workspace")
    if workspace.workspace_status != "active":
        raise DirectPushWorkflowError("workspace_not_active")
    if credential.token_chatgpt_account_id != workspace.external_workspace_id:
        raise DirectPushWorkflowError("workspace_mismatch")


def _active_downstream_slot_count(session: Session, downstream_channel_id: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(DownstreamCodexPushRecordModel)
            .where(
                DownstreamCodexPushRecordModel.downstream_channel_id == downstream_channel_id,
                DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
            )
        )
        or 0
    )


def _allowed_downstream_active_slots(session: Session, channel: DownstreamChannelModel) -> int:
    max_slots = max(0, int(channel.max_active_slots or 0))
    if max_slots <= 0:
        return 0
    high_usage_count = int(
        session.scalar(
            select(func.count())
            .select_from(DownstreamCodexPushRecordModel)
            .where(
                DownstreamCodexPushRecordModel.downstream_channel_id == channel.id,
                DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
                DownstreamCodexPushRecordModel.usage_percent >= 70,
            )
        )
        or 0
    )
    return min(max_slots, 1 + high_usage_count)


def _provider_from_channel(channel: DownstreamChannelModel):
    if channel.provider_type == "sub2api":
        return Sub2ApiDownstreamPlugin.from_config(
            Sub2ApiClientConfig(
                base_url=channel.base_url,
                admin_key=channel.admin_key,
                timeout_s=channel.timeout_s,
                update_existing=channel.update_existing,
                concurrency=channel.sub2api_concurrency,
                group_ids=_parse_downstream_group_ids(channel.sub2api_group_ids),
            )
        )
    if channel.provider_type == "cpa":
        return CpaDownstreamPlugin.from_config(
            CpaClientConfig(
                base_url=channel.base_url,
                admin_key=channel.admin_key,
                timeout_s=channel.timeout_s,
            )
        )
    if channel.provider_type == "local_sub2api":
        return LocalSub2ApiDownstreamPlugin.from_config(
            LocalSub2ApiClientConfig(
                output_dir=channel.base_url,
                update_existing=channel.update_existing,
                concurrency=channel.sub2api_concurrency,
                group_ids=_parse_downstream_group_ids(channel.sub2api_group_ids),
            )
        )
    if channel.provider_type == "custom_http":
        return CustomHttpDownstreamPlugin.from_config(
            CustomHttpClientConfig(
                url=channel.base_url,
                auth_header_name=channel.custom_auth_header_name,
                auth_header_value=channel.custom_auth_header_value,
                payload_type=channel.custom_payload_type,
                timeout_s=channel.timeout_s,
                sub2api_concurrency=channel.sub2api_concurrency,
                sub2api_group_ids=_parse_downstream_group_ids(channel.sub2api_group_ids),
            )
        )
    raise DirectPushWorkflowError(f"unsupported_downstream_provider: {channel.provider_type}")


def _parse_downstream_group_ids(value: str) -> tuple[int, ...]:
    group_ids: list[int] = []
    for part in str(value or "").split(","):
        item = part.strip()
        if not item:
            continue
        group_id = int(item)
        if group_id > 0:
            group_ids.append(group_id)
    return tuple(group_ids)
