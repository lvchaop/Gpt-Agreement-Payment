from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import ensure_account_proxy_url
from refactor_app.application.workflows.space_usage import (
    quota_window_kind_from_seconds,
    usage_status_from_percent,
)
from refactor_app.infrastructure.db.models import (
    DownstreamChannelCredentialTypeBalanceModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceModel,
    SpacePushBindingModel,
    SpaceRecycleRuleModel,
    SpaceUsageCheckModel,
)
from refactor_app.plugins.contracts import OpenAIChatGPTProvider


class SpaceRecycleWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpaceRecycleSweepInput:
    limit: int = 100


@dataclass(frozen=True)
class SpaceRecycleSweepResult:
    checked_count: int
    active_count: int
    used_count: int
    skipped_count: int
    failed_count: int


@dataclass(frozen=True)
class SpaceRecycleBindingResult:
    space_credential_id: str
    status: str


@dataclass(frozen=True)
class ManualSettlePushBindingResult:
    space_credential_id: str
    push_status: str
    reason: str
    usage_percent: int = 0


class SpaceRecycleSweepWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider

    def run(
        self,
        input_: SpaceRecycleSweepInput = SpaceRecycleSweepInput(),
    ) -> SpaceRecycleSweepResult:
        checked_count = 0
        active_count = 0
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
                    SpaceModel.auto_replenish_enabled.is_(False),
                )
                .order_by(SpacePushBindingModel.updated_at.asc())
                .limit(max(1, int(input_.limit or 100)))
            ).all()

            for binding_id in binding_ids:
                checked_count += 1
                try:
                    status = _process_binding(
                        session_factory=self._session_factory,
                        session=session,
                        openai_provider=self._openai_provider,
                        space_credential_id=str(binding_id),
                    )
                except Exception:
                    failed_count += 1
                    continue
                if status == "used":
                    used_count += 1
                elif status == "skipped":
                    skipped_count += 1
                elif status == "active":
                    active_count += 1
                elif status == "failed":
                    failed_count += 1
            session.commit()
        return SpaceRecycleSweepResult(
            checked_count=checked_count,
            active_count=active_count,
            used_count=used_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
        )

    def select_binding_ids(
        self,
        input_: SpaceRecycleSweepInput = SpaceRecycleSweepInput(),
    ) -> list[str]:
        with self._session_factory() as session:
            return [
                str(item)
                for item in session.scalars(
                    select(SpacePushBindingModel.space_credential_id)
                    .join(
                        SpaceCredentialModel,
                        SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id,
                    )
                    .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
                    .where(
                        SpacePushBindingModel.push_status == "pushed",
                        SpaceModel.space_status == "active",
                        SpaceModel.auto_replenish_enabled.is_(False),
                    )
                    .order_by(SpacePushBindingModel.updated_at.asc())
                    .limit(max(1, int(input_.limit or 100)))
                ).all()
            ]

    def run_binding(self, *, space_credential_id: str) -> SpaceRecycleBindingResult:
        with self._session_factory() as session:
            status = _process_binding(
                session_factory=self._session_factory,
                session=session,
                openai_provider=self._openai_provider,
                space_credential_id=space_credential_id,
            )
            session.commit()
            return SpaceRecycleBindingResult(
                space_credential_id=space_credential_id,
                status=status,
            )

    def refresh_binding_usage(self, *, space_credential_id: str) -> SpaceRecycleBindingResult:
        with self._session_factory() as session:
            status = _process_binding(
                session_factory=self._session_factory,
                session=session,
                openai_provider=self._openai_provider,
                space_credential_id=space_credential_id,
                allow_settlement=False,
            )
            session.commit()
            return SpaceRecycleBindingResult(
                space_credential_id=space_credential_id,
                status=status,
            )


def manually_settle_pushed_binding_from_usage_state(
    *,
    session: Session,
    space_credential_id: str,
) -> ManualSettlePushBindingResult:
    now = datetime.now(UTC)
    binding = session.get(SpacePushBindingModel, space_credential_id)
    if binding is None:
        return ManualSettlePushBindingResult(
            space_credential_id=space_credential_id,
            push_status="ignored",
            reason="missing_push_binding",
        )
    if binding.push_status != "pushed":
        return ManualSettlePushBindingResult(
            space_credential_id=space_credential_id,
            push_status="ignored",
            reason=f"push_status_{binding.push_status}",
        )
    credential = session.get(SpaceCredentialModel, space_credential_id)
    if credential is None:
        return ManualSettlePushBindingResult(
            space_credential_id=space_credential_id,
            push_status="ignored",
            reason="missing_space_credential",
        )
    space = session.get(SpaceModel, credential.space_id)
    if space is None:
        return ManualSettlePushBindingResult(
            space_credential_id=space_credential_id,
            push_status="ignored",
            reason="missing_space",
        )
    usage_state = _highest_usage_state(session=session, credential=credential)
    if usage_state is None:
        return ManualSettlePushBindingResult(
            space_credential_id=space_credential_id,
            push_status="ignored",
            reason="missing_usage_state",
        )
    usage_percent = _max_usage_percent(session=session, credential=credential, windows=[])
    push_status = _settle_binding_locally(
        session=session,
        binding=binding,
        credential=credential,
        space=space,
        usage_state=usage_state,
        usage_percent=usage_percent,
        now=now,
        reason=f"manual_settle.usage_percent={usage_percent}",
        error_message=(
            "manual settle pushed binding from existing usage state; "
            "remote member is not removed"
        ),
    )
    return ManualSettlePushBindingResult(
        space_credential_id=space_credential_id,
        push_status=push_status,
        reason=f"usage_percent={usage_percent}",
        usage_percent=usage_percent,
    )


def _process_binding(
    *,
    session_factory: Callable[[], Session],
    session: Session,
    openai_provider: OpenAIChatGPTProvider,
    space_credential_id: str,
    allow_settlement: bool = True,
) -> str:
    now = datetime.now(UTC)
    binding = session.get(SpacePushBindingModel, space_credential_id)
    credential = session.get(SpaceCredentialModel, space_credential_id)
    if binding is None or credential is None or binding.push_status != "pushed":
        return "ignored"
    space = session.get(SpaceModel, credential.space_id)
    if space is None or space.space_status != "active":
        return "ignored"
    if allow_settlement and space.auto_replenish_enabled:
        return "ignored"
    try:
        proxy_url = ensure_account_proxy_url(
            session_factory,
            credential.user_account_id,
            bind_reason="space_recycle_usage_probe",
        )
        probe = openai_provider.probe_codex_responses_usage(
            access_token=credential.access_token,
            team_id=space.external_space_id if space.space_type == "business" else "",
            proxy_url=proxy_url,
        )
    except Exception as exc:
        _record_failed_usage_check(
            session=session,
            credential=credential,
            space=space,
            error=exc,
            now=now,
        )
        _mark_binding_recycle_failed(binding=binding, error=exc, now=now)
        return "failed"
    windows = _parse_codex_usage_headers(probe.get("headers") or {})
    if str(probe.get("status") or "ok") != "ok":
        if windows:
            for window in windows:
                _record_usage_window(
                    session=session,
                    credential=credential,
                    space=space,
                    window=window,
                    raw_usage_json=probe,
                    now=now,
                )
        if _is_terminal_unusable_probe(probe):
            if not windows:
                _record_failed_usage_check(
                    session=session,
                    credential=credential,
                    space=space,
                    error=SpaceRecycleWorkflowError(
                        str(probe.get("error_code") or "terminal_unusable")
                    ),
                    now=now,
                    raw_usage_json=probe,
                    usage_percent=_max_usage_percent(
                        session=session, credential=credential, windows=windows
                    ),
                )
            usage_state = _highest_usage_state(session=session, credential=credential)
            usage_percent = _max_usage_percent(session=session, credential=credential, windows=windows)
            if not allow_settlement:
                return "unusable"
            return _settle_binding_locally(
                session=session,
                binding=binding,
                credential=credential,
                space=space,
                usage_state=usage_state,
                usage_percent=usage_percent,
                now=now,
                reason=str(probe.get("error_code") or "terminal_unusable"),
                error_message=(
                    "terminal unusable probe result; settled by usage_percent "
                    f"{usage_percent}"
                ),
            )
        error = SpaceRecycleWorkflowError(str(probe.get("error_code") or "codex_probe_failed"))
        _record_failed_usage_check(
            session=session,
            credential=credential,
            space=space,
            error=error,
            now=now,
            raw_usage_json=probe,
            usage_percent=_max_usage_percent(session=session, credential=credential, windows=windows),
        )
        _mark_binding_recycle_failed(binding=binding, error=error, now=now)
        return "failed"
    if not windows:
        error = SpaceRecycleWorkflowError("codex_usage_headers_missing")
        _record_failed_usage_check(
            session=session,
            credential=credential,
            space=space,
            error=error,
            now=now,
            raw_usage_json=probe,
            usage_percent=_max_usage_percent(session=session, credential=credential, windows=[]),
        )
        _mark_binding_recycle_failed(binding=binding, error=error, now=now)
        return "failed"
    for window in windows:
        _record_usage_window(
            session=session,
            credential=credential,
            space=space,
            window=window,
            raw_usage_json=probe,
            now=now,
        )
    if not allow_settlement:
        binding.recycle_status = "none"
        binding.error_code = ""
        binding.error_message = ""
        binding.updated_at = now
        return "active"
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
            return _settle_binding_locally(
                session=session,
                binding=binding,
                credential=credential,
                space=space,
                usage_state=usage_state,
                usage_percent=int(usage_state.usage_percent or 0),
                now=now,
                reason=(
                    f"{space.credential_type}.{usage_state.quota_window_kind}"
                    f">={rule.threshold_percent}"
                ),
                error_message=(
                    "recycle threshold reached; settled locally; "
                    "remote member is not removed"
                ),
            )
    binding.recycle_status = "none"
    binding.error_code = ""
    binding.error_message = ""
    binding.updated_at = now
    return "active"


def _settle_binding_locally(
    *,
    session: Session,
    binding: SpacePushBindingModel,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    usage_state: SpaceCredentialUsageStateModel | None,
    usage_percent: int,
    now: datetime,
    reason: str,
    error_message: str,
) -> str:
    if int(usage_percent or 0) >= 60:
        _mark_binding_used_locally(
            session=session,
            binding=binding,
            credential=credential,
            space=space,
            usage_state=usage_state,
            now=now,
            reason=reason,
            error_message=error_message,
        )
        return "used"
    _mark_binding_skipped_and_refund(
        session=session,
        binding=binding,
        credential=credential,
        space=space,
        usage_state=usage_state,
        now=now,
        reason=reason,
        usage_percent=int(usage_percent or 0),
    )
    return "skipped"


def _mark_binding_used_locally(
    *,
    session: Session,
    binding: SpacePushBindingModel,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    usage_state: SpaceCredentialUsageStateModel | None,
    now: datetime,
    reason: str,
    error_message: str = "marked used locally; remote member is not removed",
) -> None:
    binding.push_status = "used"
    binding.recycle_status = "done"
    binding.recycled_at = now
    binding.used_count += 1
    binding.error_code = reason[:200]
    binding.error_message = error_message[:1000]
    binding.updated_at = now
    if usage_state is not None:
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


def _mark_binding_skipped_and_refund(
    *,
    session: Session,
    binding: SpacePushBindingModel,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    usage_state: SpaceCredentialUsageStateModel | None,
    now: datetime,
    reason: str,
    usage_percent: int,
) -> None:
    binding.push_status = "skipped"
    binding.recycle_status = "done"
    binding.recycled_at = now
    binding.error_code = reason[:200]
    binding.error_message = (
        f"settled skipped because usage_percent={usage_percent}<60; refunded push balance"
    )[:1000]
    binding.updated_at = now
    credential.credential_status = "invalid"
    credential.failure_code = reason[:200]
    credential.failure_message = (
        f"terminal unusable credential skipped because usage_percent={usage_percent}<60"
    )[:1000]
    credential.updated_at = now
    if usage_state is not None:
        usage_state.usage_status = "check_failed"
        usage_state.updated_at = now
    if not binding.downstream_channel_id:
        return
    balance = session.get(
        DownstreamChannelCredentialTypeBalanceModel,
        {
            "downstream_channel_id": binding.downstream_channel_id,
            "credential_type": space.credential_type,
        },
    )
    if balance is None:
        return
    balance.push_balance = max(0, int(balance.push_balance or 0)) + 1
    balance.claimed_push_count = max(0, int(balance.claimed_push_count or 0) - 1)
    balance.updated_at = now


def _mark_binding_recycle_failed(
    *,
    binding: SpacePushBindingModel,
    error: Exception,
    now: datetime,
) -> None:
    binding.recycle_status = "failed"
    binding.error_code = _error_code(error)
    binding.error_message = str(error)[:1000]
    binding.updated_at = now


def _record_failed_usage_check(
    *,
    session: Session,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    error: Exception,
    now: datetime,
    raw_usage_json: dict | None = None,
    usage_percent: int = 0,
) -> None:
    session.add(
        SpaceUsageCheckModel(
            id=f"space-usage-check-{uuid4()}",
            space_credential_id=credential.id,
            space_id=space.id,
            quota_window_kind=_default_quota_window_kind(space.credential_type),
            usage_percent=max(0, min(int(usage_percent or 0), 100)),
            limit_window_seconds=0,
            reset_after_seconds=0,
            reset_at=None,
            allowed=False,
            limit_reached=False,
            raw_usage_json=raw_usage_json or {},
            check_status="failed",
            error_code=_error_code(error),
            error_message=str(error)[:1000],
            checked_at=now,
            created_at=now,
        )
    )


def _error_code(error: Exception) -> str:
    message = str(error).strip()
    if isinstance(error, SpaceRecycleWorkflowError) and message:
        return message[:200]
    return type(error).__name__[:200]


def _is_terminal_unusable_probe(probe: dict) -> bool:
    http_status = int(probe.get("http_status") or 0)
    return bool(probe.get("payment_required")) or bool(probe.get("unauthorized")) or http_status in {
        401,
        402,
    }


def _highest_usage_state(
    *,
    session: Session,
    credential: SpaceCredentialModel,
) -> SpaceCredentialUsageStateModel | None:
    return session.scalars(
        select(SpaceCredentialUsageStateModel)
        .where(SpaceCredentialUsageStateModel.space_credential_id == credential.id)
        .order_by(SpaceCredentialUsageStateModel.usage_percent.desc())
    ).first()


def _max_usage_percent(
    *,
    session: Session,
    credential: SpaceCredentialModel,
    windows: list[dict],
) -> int:
    usage_values = [int(window.get("usage_percent") or 0) for window in windows]
    usage_values.extend(
        int(state.usage_percent or 0)
        for state in session.scalars(
            select(SpaceCredentialUsageStateModel).where(
                SpaceCredentialUsageStateModel.space_credential_id == credential.id
            )
        ).all()
    )
    if not usage_values:
        return 0
    return max(0, min(max(usage_values), 100))


def _record_usage_window(
    *,
    session: Session,
    credential: SpaceCredentialModel,
    space: SpaceModel,
    window: dict,
    raw_usage_json: dict,
    now: datetime,
) -> None:
    quota_window_kind = str(window["quota_window_kind"])
    usage_percent = max(0, min(int(window["usage_percent"]), 100))
    limit_window_seconds = int(window["limit_window_seconds"])
    reset_after_seconds = max(0, int(window.get("reset_after_seconds") or 0))
    state = session.get(
        SpaceCredentialUsageStateModel,
        {
            "space_credential_id": credential.id,
            "quota_window_kind": quota_window_kind,
        },
    )
    status = usage_status_from_percent(usage_percent)
    if state is None:
        state = SpaceCredentialUsageStateModel(
            space_credential_id=credential.id,
            quota_window_kind=quota_window_kind,
            space_id=space.id,
            usage_percent=usage_percent,
            usage_status=status,
            limit_window_seconds=limit_window_seconds,
            reset_after_seconds=reset_after_seconds,
            reset_at=None,
            last_checked_at=now,
            raw_usage_json=raw_usage_json,
            created_at=now,
            updated_at=now,
        )
        session.add(state)
    else:
        state.space_id = space.id
        state.usage_percent = usage_percent
        state.usage_status = status
        state.limit_window_seconds = limit_window_seconds
        state.reset_after_seconds = reset_after_seconds
        state.reset_at = None
        state.last_checked_at = now
        state.raw_usage_json = raw_usage_json
        state.error_code = ""
        state.error_message = ""
        state.updated_at = now
    session.add(
        SpaceUsageCheckModel(
            id=f"space-usage-check-{uuid4()}",
            space_credential_id=credential.id,
            space_id=space.id,
            quota_window_kind=quota_window_kind,
            usage_percent=usage_percent,
            limit_window_seconds=limit_window_seconds,
            reset_after_seconds=reset_after_seconds,
            reset_at=None,
            allowed=True,
            limit_reached=usage_percent >= 100,
            raw_usage_json=raw_usage_json,
            check_status="ok",
            checked_at=now,
            created_at=now,
        )
    )


def _parse_codex_usage_headers(headers: dict) -> list[dict]:
    result: list[dict] = []
    for prefix in ("primary", "secondary"):
        used_percent = _header_int(headers, f"x-codex-{prefix}-used-percent")
        window_minutes = _header_int(headers, f"x-codex-{prefix}-window-minutes")
        if used_percent is None or window_minutes is None:
            continue
        quota_window_kind = _quota_window_kind_from_minutes(window_minutes)
        if not quota_window_kind:
            continue
        result.append(
            {
                "quota_window_kind": quota_window_kind,
                "usage_percent": used_percent,
                "limit_window_seconds": window_minutes * 60,
                "reset_after_seconds": _header_int(
                    headers, f"x-codex-{prefix}-reset-after-seconds"
                )
                or 0,
            }
        )
    return result


def _quota_window_kind_from_minutes(window_minutes: int) -> str:
    return quota_window_kind_from_seconds(int(window_minutes) * 60) or ""


def _default_quota_window_kind(credential_type: str) -> str:
    if credential_type == "team_5h_weekly":
        return "weekly"
    return "monthly"


def _header_int(headers: dict, key: str) -> int | None:
    value = headers.get(key.lower()) or headers.get(key)
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
