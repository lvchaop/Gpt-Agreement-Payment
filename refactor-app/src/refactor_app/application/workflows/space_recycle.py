from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import (
    DownstreamChannelCredentialTypeBalanceModel,
    SpaceAccountCooldownModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceModel,
    SpacePushBindingModel,
    SpaceRecycleRuleModel,
)


class SpaceRecycleWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceRecycleSweepInput:
    limit: int = 100


@dataclass(frozen=True)
class SpaceRecycleSweepResult:
    checked_count: int
    used_count: int
    skipped_count: int
    failed_count: int


class SpaceRecycleSweepWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(
        self,
        input_: SpaceRecycleSweepInput = SpaceRecycleSweepInput(),
    ) -> SpaceRecycleSweepResult:
        checked_count = 0
        used_count = 0
        skipped_count = 0
        failed_count = 0
        with self._session_factory() as session:
            binding_ids = session.scalars(
                select(SpacePushBindingModel.space_credential_id)
                .join(
                    SpaceCredentialModel,
                    SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id,
                )
                .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
                .where(
                    SpacePushBindingModel.push_status == "pushed",
                    SpaceModel.space_status == "active",
                )
                .order_by(SpacePushBindingModel.updated_at.asc())
                .limit(max(1, int(input_.limit or 100)))
            ).all()

            for binding_id in binding_ids:
                checked_count += 1
                try:
                    status = _process_binding(
                        session=session,
                        space_credential_id=str(binding_id),
                    )
                except Exception:
                    failed_count += 1
                    continue
                if status == "used":
                    used_count += 1
                elif status == "skipped":
                    skipped_count += 1
            session.commit()
        return SpaceRecycleSweepResult(
            checked_count=checked_count,
            used_count=used_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )


def _process_binding(
    *,
    session: Session,
    space_credential_id: str,
) -> str:
    now = datetime.now(UTC)
    binding = session.get(SpacePushBindingModel, space_credential_id)
    credential = session.get(SpaceCredentialModel, space_credential_id)
    if binding is None or credential is None or binding.push_status != "pushed":
        return "skipped"
    space = session.get(SpaceModel, credential.space_id)
    if space is None or space.space_status != "active":
        return "skipped"
    usage_states = session.scalars(
        select(SpaceCredentialUsageStateModel).where(
            SpaceCredentialUsageStateModel.space_credential_id == credential.id
        )
    ).all()
    for usage_state in usage_states:
        rule = session.scalars(
            select(SpaceRecycleRuleModel).where(
                SpaceRecycleRuleModel.credential_type == space.credential_type,
                SpaceRecycleRuleModel.quota_window_kind == usage_state.quota_window_kind,
            )
        ).first()
        if rule is None or not rule.enabled:
            continue
        if int(usage_state.usage_percent or 0) < int(rule.threshold_percent or 95):
            continue
        if rule.action == "mark_used":
            _mark_binding_used_locally(
                session=session,
                binding=binding,
                credential=credential,
                space=space,
                usage_state=usage_state,
                now=now,
                reason=(
                    f"{space.credential_type}.{usage_state.quota_window_kind}"
                    f">={rule.threshold_percent}"
                ),
            )
            return "used"
    return "skipped"


def _mark_binding_used_locally(
    *,
    session: Session,
    binding: SpacePushBindingModel,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    usage_state: SpaceCredentialUsageStateModel,
    now: datetime,
    reason: str,
) -> None:
    binding.push_status = "used"
    binding.recycle_status = "done"
    binding.recycled_at = now
    binding.used_count += 1
    binding.error_code = reason[:200]
    binding.error_message = "marked used locally; remote member is not removed"
    binding.updated_at = now
    usage_state.usage_status = "used"
    usage_state.updated_at = now
    if binding.downstream_channel_id:
        balance = session.get(
            DownstreamChannelCredentialTypeBalanceModel,
            {
                "downstream_channel_id": binding.downstream_channel_id,
                "credential_type": space.credential_type,
            },
        )
        if balance is not None:
            balance.used_count += 1
            balance.updated_at = now
    _ensure_cooldown(
        session=session,
        user_account_id=credential.user_account_id,
        space_id=space.id,
        source_space_push_binding_id=binding.space_credential_id,
        reason=reason,
        now=now,
    )


def _ensure_cooldown(
    *,
    session: Session,
    user_account_id: str,
    space_id: str,
    source_space_push_binding_id: str,
    reason: str,
    now: datetime,
) -> None:
    cooldown_until = now + timedelta(hours=72)
    existing = session.scalars(
        select(SpaceAccountCooldownModel).where(
            SpaceAccountCooldownModel.user_account_id == user_account_id,
            SpaceAccountCooldownModel.space_id == space_id,
            SpaceAccountCooldownModel.cooldown_type == "post_usage_remove",
        )
    ).first()
    if existing is None:
        session.add(
            SpaceAccountCooldownModel(
                id=f"space-account-cooldown-{user_account_id}-{space_id}",
                user_account_id=user_account_id,
                space_id=space_id,
                cooldown_type="post_usage_remove",
                cooldown_until=cooldown_until,
                reason=reason,
                source_space_push_binding_id=source_space_push_binding_id,
                created_at=now,
                updated_at=now,
            )
        )
        return
    existing.cooldown_until = cooldown_until
    existing.reason = reason
    existing.source_space_push_binding_id = source_space_push_binding_id
    existing.updated_at = now
