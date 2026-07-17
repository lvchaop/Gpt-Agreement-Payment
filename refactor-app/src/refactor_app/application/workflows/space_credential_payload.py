from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.space_payloads import (
    BusinessAccessTokenPayloadInput,
    build_team_5h_weekly_cpa_payload,
    build_team_5h_weekly_sub2api_payload,
    build_team_monthly_cpa_payload,
    build_team_monthly_sub2api_payload,
)
from refactor_app.application.workflows.space_usage import WhamUsageWindow
from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceModel,
    UserAccountModel,
)
from refactor_app.plugins.contracts import DownstreamCodexPayload


class SpaceCredentialPayloadError(RuntimeError):
    pass


def build_space_credential_payload(
    *,
    session: Session,
    user: UserAccountModel,
    space: SpaceModel,
    credential: SpaceCredentialModel,
    provider_type: str,
    exported_at: datetime | None = None,
) -> tuple[DownstreamCodexPayload | dict, str]:
    if space.credential_type == "personal_account":
        return (
            DownstreamCodexPayload(
                access_token=credential.access_token,
                id_token=credential.id_token,
                refresh_token=credential.refresh_token,
                email=user.email,
                account_id=credential.account_id,
                downstream_chatgpt_account_id=f"{user.id}_{space.id}",
                token_chatgpt_account_id=credential.token_chatgpt_account_id
                or space.external_space_id,
                client_id=credential.codex_client_id,
                expires_at=credential.expires_at,
                plan_tag=space.plan_type,
                plan_type=space.plan_type,
            ),
            "personal_account",
        )

    payload_input = BusinessAccessTokenPayloadInput(
        access_token=credential.access_token,
        chatgpt_account_id=f"{user.id}_{space.id}",
        chatgpt_user_id=credential.account_id or user.openai_user_id,
        email=user.email,
        credential_type=space.credential_type,
        usage_windows=tuple(
            _usage_windows_for_credential(session=session, credential_id=credential.id)
        ),
        exported_at=exported_at,
    )
    if space.credential_type == "team_5h_weekly":
        if provider_type == "cpa":
            return build_team_5h_weekly_cpa_payload(payload_input), space.credential_type
        return build_team_5h_weekly_sub2api_payload(payload_input), space.credential_type
    if space.credential_type == "team_monthly":
        if provider_type == "cpa":
            return build_team_monthly_cpa_payload(payload_input), space.credential_type
        return build_team_monthly_sub2api_payload(payload_input), space.credential_type
    raise SpaceCredentialPayloadError(f"unsupported_credential_type:{space.credential_type}")


def _usage_windows_for_credential(
    *,
    session: Session,
    credential_id: str,
) -> list[WhamUsageWindow]:
    states = session.scalars(
        select(SpaceCredentialUsageStateModel).where(
            SpaceCredentialUsageStateModel.space_credential_id == credential_id
        )
    ).all()
    return [
        WhamUsageWindow(
            quota_window_kind=state.quota_window_kind,
            used_percent=state.usage_percent,
            limit_window_seconds=state.limit_window_seconds,
            reset_after_seconds=state.reset_after_seconds,
            reset_at=state.reset_at,
            raw_window={},
        )
        for state in states
    ]
