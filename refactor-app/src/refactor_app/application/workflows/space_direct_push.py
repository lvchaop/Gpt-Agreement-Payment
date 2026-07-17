from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.space_credential_payload import (
    build_space_credential_payload,
)
from refactor_app.infrastructure.db.models import (
    DownstreamChannelCredentialTypeBalanceModel,
    DownstreamChannelModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceModel,
    SpacePushAttemptModel,
    SpacePushBindingModel,
    UserAccountModel,
)
from refactor_app.plugins.contracts import (
    DownstreamCodexPayload,
    DownstreamProvider,
    DownstreamPushResult,
)


class SpaceDirectPushWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceDirectPushInput:
    space_credential_id: str
    downstream_channel_id: str
    is_retry: bool = False


class SpaceDirectPushWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        downstream_provider: DownstreamProvider,
    ) -> None:
        self._session_factory = session_factory
        self._downstream_provider = downstream_provider

    def run(self, input_: SpaceDirectPushInput) -> str:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            credential = session.get(SpaceCredentialModel, input_.space_credential_id)
            channel = session.get(DownstreamChannelModel, input_.downstream_channel_id)
            if credential is None:
                raise SpaceDirectPushWorkflowError("missing_space_credential")
            if channel is None:
                raise SpaceDirectPushWorkflowError("missing_downstream_channel")
            space = session.get(SpaceModel, credential.space_id)
            user = session.get(UserAccountModel, credential.user_account_id)
            if space is None:
                raise SpaceDirectPushWorkflowError("missing_space")
            if user is None:
                raise SpaceDirectPushWorkflowError("missing_user_account")

            balance = session.get(
                DownstreamChannelCredentialTypeBalanceModel,
                {
                    "downstream_channel_id": channel.id,
                    "credential_type": space.credential_type,
                },
            )
            if balance is None:
                raise SpaceDirectPushWorkflowError("missing_channel_credential_type_balance")
            _validate_pushable(
                session=session,
                credential=credential,
                space=space,
                channel=channel,
                balance=balance,
                require_balance=not input_.is_retry,
            )

            binding = session.get(SpacePushBindingModel, credential.id)
            if binding is not None:
                if binding.downstream_channel_id and binding.downstream_channel_id != channel.id:
                    raise SpaceDirectPushWorkflowError(
                        "credential_already_allocated_to_other_channel"
                    )
                if binding.push_status in {"pushing", "pushed", "used"}:
                    raise SpaceDirectPushWorkflowError(
                        f"credential_push_status_{binding.push_status}"
                    )
            if not input_.is_retry:
                active_slots = _active_space_slot_count(
                    session=session,
                    downstream_channel_id=channel.id,
                    credential_type=space.credential_type,
                )
                allowed_slots = _allowed_space_active_slots(
                    session=session,
                    balance=balance,
                )
                if active_slots >= allowed_slots:
                    raise SpaceDirectPushWorkflowError(
                        "downstream_channel_active_slots_exhausted"
                    )
                balance.push_balance -= 1
                balance.claimed_push_count += 1
                balance.updated_at = now

            if binding is None:
                binding = SpacePushBindingModel(
                    space_credential_id=credential.id,
                    space_id=space.id,
                    downstream_channel_id=channel.id,
                    push_status="pushing",
                    created_at=now,
                    updated_at=now,
                )
                session.add(binding)
            else:
                binding.downstream_channel_id = channel.id
                binding.push_status = "pushing"
                binding.error_code = ""
                binding.error_message = ""
                binding.updated_at = now

            payload, payload_type = build_space_credential_payload(
                session=session,
                user=user,
                space=space,
                credential=credential,
                provider_type=channel.provider_type,
            )
            attempt = SpacePushAttemptModel(
                id=f"space-push-attempt-{uuid4()}",
                space_credential_id=credential.id,
                space_id=space.id,
                downstream_channel_id=channel.id,
                payload_type=payload_type,
                request_endpoint=_request_endpoint(channel),
                request_body_json=_attempt_request_body(payload),
                response_json={},
                attempt_status="running",
                started_at=now,
                created_at=now,
            )
            session.add(attempt)
            attempt_id = attempt.id
            session.commit()

        result = _push_payload(
            provider=self._downstream_provider,
            payload=payload,
            payload_type=payload_type,
        )
        finished_at = datetime.now(UTC)
        with self._session_factory() as session:
            binding = session.get(SpacePushBindingModel, input_.space_credential_id)
            attempt = session.get(SpacePushAttemptModel, attempt_id)
            balance = session.get(
                DownstreamChannelCredentialTypeBalanceModel,
                {
                    "downstream_channel_id": input_.downstream_channel_id,
                    "credential_type": payload_type,
                },
            )
            if binding is None or attempt is None:
                raise SpaceDirectPushWorkflowError("push_state_missing_after_provider_call")
            attempt.response_json = result.raw
            attempt.finished_at = finished_at
            if result.pushed:
                attempt.attempt_status = "pushed"
                binding.push_status = "pushed"
                binding.downstream_external_id = result.downstream_external_id
                binding.pushed_count += 1
                binding.error_code = ""
                binding.error_message = ""
                if balance is not None:
                    balance.pushed_count += 1
                    balance.updated_at = finished_at
            else:
                attempt.attempt_status = "failed"
                attempt.error_code = result.error_code or "downstream_push_failed"
                attempt.error_message = result.error_message
                binding.push_status = "failed"
                binding.failed_push_count += 1
                binding.error_code = attempt.error_code
                binding.error_message = attempt.error_message
                if balance is not None:
                    balance.failed_push_count += 1
                    balance.updated_at = finished_at
            binding.updated_at = finished_at
            session.commit()
            if not result.pushed:
                raise SpaceDirectPushWorkflowError(result.error_code or "downstream_push_failed")
            return binding.space_credential_id


def _validate_pushable(
    *,
    session: Session,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    channel: DownstreamChannelModel,
    balance: DownstreamChannelCredentialTypeBalanceModel,
    require_balance: bool,
) -> None:
    if not channel.enabled:
        raise SpaceDirectPushWorkflowError("downstream_channel_disabled")
    if balance.balance_status != "active":
        raise SpaceDirectPushWorkflowError("downstream_channel_balance_disabled")
    if balance.max_active_slots <= 0:
        raise SpaceDirectPushWorkflowError("downstream_channel_active_slots_exhausted")
    if require_balance and balance.push_balance <= 0:
        raise SpaceDirectPushWorkflowError("downstream_channel_balance_exhausted")
    if credential.credential_status != "active":
        raise SpaceDirectPushWorkflowError("credential_not_active")
    if not credential.access_token:
        raise SpaceDirectPushWorkflowError("credential_access_token_missing")
    if space.space_status != "active":
        raise SpaceDirectPushWorkflowError("space_not_active")
    if space.credential_type == "personal_account" and not credential.refresh_token:
        raise SpaceDirectPushWorkflowError("personal_credential_refresh_token_missing")
    if _active_space_slot_count(
        session=session,
        downstream_channel_id=channel.id,
        credential_type=space.credential_type,
    ) > _allowed_space_active_slots(session=session, balance=balance):
        raise SpaceDirectPushWorkflowError("downstream_channel_active_slots_exhausted")


def _push_payload(
    *,
    provider: DownstreamProvider,
    payload: DownstreamCodexPayload | dict,
    payload_type: str,
) -> DownstreamPushResult:
    if payload_type == "personal_account":
        if not isinstance(payload, DownstreamCodexPayload):
            raise SpaceDirectPushWorkflowError("personal_payload_type_mismatch")
        return provider.push_codex_credential(payload)
    if not isinstance(payload, dict):
        raise SpaceDirectPushWorkflowError("business_payload_type_mismatch")
    return provider.push_business_access_token(payload)


def _active_space_slot_count(
    *,
    session: Session,
    downstream_channel_id: str,
    credential_type: str,
) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(SpacePushBindingModel)
            .join(
                SpaceCredentialModel,
                SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id,
            )
            .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
            .where(
                SpacePushBindingModel.downstream_channel_id == downstream_channel_id,
                SpacePushBindingModel.push_status.in_(("pushing", "pushed", "failed")),
                SpaceModel.credential_type == credential_type,
            )
        )
        or 0
    )


def _allowed_space_active_slots(
    *,
    session: Session,
    balance: DownstreamChannelCredentialTypeBalanceModel,
) -> int:
    max_slots = max(0, int(balance.max_active_slots or 0))
    if max_slots <= 0:
        return 0
    base_slots = max(1, max_slots // 2)
    high_usage_count = int(
        session.scalar(
            select(func.count(func.distinct(SpacePushBindingModel.space_credential_id)))
            .select_from(SpacePushBindingModel)
            .join(
                SpaceCredentialModel,
                SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id,
            )
            .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
            .join(
                SpaceCredentialUsageStateModel,
                SpaceCredentialUsageStateModel.space_credential_id
                == SpacePushBindingModel.space_credential_id,
            )
            .where(
                SpacePushBindingModel.downstream_channel_id == balance.downstream_channel_id,
                SpacePushBindingModel.push_status.in_(("pushing", "pushed", "failed")),
                SpaceModel.credential_type == balance.credential_type,
                SpaceCredentialUsageStateModel.usage_percent >= 70,
            )
        )
        or 0
    )
    return min(max_slots, base_slots + high_usage_count)


def _request_endpoint(channel: DownstreamChannelModel) -> str:
    if channel.provider_type == "cpa":
        return "/v0/management/auth-files"
    if channel.provider_type in {"sub2api", "local_sub2api"}:
        return "/api/v1/admin/accounts/import/codex-session"
    if channel.provider_type == "custom_http":
        return channel.base_url
    return ""


def _attempt_request_body(payload: DownstreamCodexPayload | dict) -> dict:
    if isinstance(payload, dict):
        return payload
    return {
        "access_token": "<redacted>",
        "id_token": "<redacted>" if payload.id_token else "",
        "refresh_token": "<redacted>" if payload.refresh_token else "",
        "email": payload.email,
        "account_id": payload.account_id,
        "chatgpt_account_id": payload.downstream_chatgpt_account_id,
        "token_chatgpt_account_id": payload.token_chatgpt_account_id,
        "client_id": payload.client_id,
        "plan_type": payload.plan_type,
    }
