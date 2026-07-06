from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from refactor_app.application.workflows.space_usage import WhamUsageWindow


BUSINESS_PAT_MODEL_MAPPING = {
    "codex-auto-review": "codex-auto-review",
    "gpt-4o-audio-preview": "gpt-4o-audio-preview",
    "gpt-4o-realtime-preview": "gpt-4o-realtime-preview",
    "gpt-5.2": "gpt-5.2",
    "gpt-5.2-2025-12-11": "gpt-5.2-2025-12-11",
    "gpt-5.2-chat-latest": "gpt-5.2-chat-latest",
    "gpt-5.2-pro": "gpt-5.2-pro",
    "gpt-5.2-pro-2025-12-11": "gpt-5.2-pro-2025-12-11",
    "gpt-5.3-codex": "gpt-5.3-codex",
    "gpt-5.3-codex-spark": "gpt-5.3-codex-spark",
    "gpt-5.4": "gpt-5.4",
    "gpt-5.4-2026-03-05": "gpt-5.4-2026-03-05",
    "gpt-5.4-mini": "gpt-5.4-mini",
    "gpt-5.5": "gpt-5.5",
    "gpt-image-1": "gpt-image-1",
    "gpt-image-1.5": "gpt-image-1.5",
    "gpt-image-2": "gpt-image-2",
}


class SpacePayloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class BusinessAccessTokenPayloadInput:
    access_token: str
    chatgpt_account_id: str
    chatgpt_user_id: str
    email: str
    owner_email: str
    credential_type: str
    usage_windows: tuple[WhamUsageWindow, ...] = ()
    exported_at: datetime | None = None
    imported_at: datetime | None = None
    concurrency: int = 10
    priority: int = 1
    rate_multiplier: int = 1


def build_team_5h_weekly_sub2api_payload(input_: BusinessAccessTokenPayloadInput) -> dict:
    _assert_credential_type(input_, expected="team_5h_weekly")
    return _business_access_token_export_body(input_)


def build_team_5h_weekly_cpa_payload(input_: BusinessAccessTokenPayloadInput) -> dict:
    return build_team_5h_weekly_sub2api_payload(input_)


def build_team_monthly_sub2api_payload(input_: BusinessAccessTokenPayloadInput) -> dict:
    _assert_credential_type(input_, expected="team_monthly")
    return _business_access_token_export_body(input_)


def build_team_monthly_cpa_payload(input_: BusinessAccessTokenPayloadInput) -> dict:
    return build_team_monthly_sub2api_payload(input_)


def _business_access_token_export_body(input_: BusinessAccessTokenPayloadInput) -> dict:
    _validate_business_input(input_)
    exported_at = input_.exported_at or datetime.now(UTC)
    imported_at = input_.imported_at or exported_at
    usage = _usage_extra(input_.usage_windows, updated_at=exported_at)
    return {
        "exported_at": _utc_iso(exported_at),
        "proxies": [],
        "accounts": [
            {
                "name": f"母-{input_.owner_email}-子-{input_.email}",
                "platform": "openai",
                "type": "oauth",
                "credentials": {
                    "access_token": input_.access_token,
                    "auth_mode": "personalAccessToken",
                    "chatgpt_account_id": input_.chatgpt_account_id,
                    "chatgpt_account_is_fedramp": False,
                    "chatgpt_user_id": input_.chatgpt_user_id,
                    "email": input_.email,
                    "model_mapping": dict(BUSINESS_PAT_MODEL_MAPPING),
                    "openai_auth_mode": "personal_access_token",
                    "plan_type": "team",
                    "token_type": "Bearer",
                },
                "extra": {
                    "access_token_sha256": hashlib.sha256(
                        input_.access_token.encode("utf-8")
                    ).hexdigest(),
                    "auth_provider": "codex_personal_access_token",
                    **usage,
                    "import_source": "codex_personal_access_token",
                    "imported_at": _utc_iso(imported_at),
                    "openai_oauth_responses_websockets_v2_enabled": False,
                    "openai_oauth_responses_websockets_v2_mode": "off",
                    "privacy_mode": "training_set_failed",
                },
                "concurrency": int(input_.concurrency),
                "priority": int(input_.priority),
                "rate_multiplier": int(input_.rate_multiplier),
                "auto_pause_on_expired": True,
            }
        ],
    }


def _usage_extra(
    usage_windows: tuple[WhamUsageWindow, ...],
    *,
    updated_at: datetime,
) -> dict:
    by_kind = {item.quota_window_kind: item for item in usage_windows}
    primary = by_kind.get("five_hour") or by_kind.get("monthly")
    secondary = by_kind.get("weekly")
    primary_minutes = int((primary.limit_window_seconds if primary else 0) // 60)
    secondary_minutes = int((secondary.limit_window_seconds if secondary else 0) // 60)
    return {
        "codex_5h_reset_after_seconds": _window_reset_after(by_kind.get("five_hour")),
        "codex_5h_reset_at": _window_reset_at(by_kind.get("five_hour")),
        "codex_5h_used_percent": _window_used_percent(by_kind.get("five_hour")),
        "codex_5h_window_minutes": 300,
        "codex_7d_reset_after_seconds": _window_reset_after(secondary),
        "codex_7d_reset_at": _window_reset_at(secondary),
        "codex_7d_used_percent": _window_used_percent(secondary),
        "codex_7d_window_minutes": 10_080,
        "codex_primary_over_secondary_percent": 0,
        "codex_primary_reset_after_seconds": _window_reset_after(primary),
        "codex_primary_used_percent": _window_used_percent(primary),
        "codex_primary_window_minutes": primary_minutes,
        "codex_secondary_reset_after_seconds": _window_reset_after(secondary),
        "codex_secondary_used_percent": _window_used_percent(secondary),
        "codex_secondary_window_minutes": secondary_minutes,
        "codex_usage_updated_at": _utc_iso(updated_at),
    }


def _window_used_percent(window: WhamUsageWindow | None) -> int:
    return int(window.used_percent) if window is not None else 0


def _window_reset_after(window: WhamUsageWindow | None) -> int:
    return int(window.reset_after_seconds) if window is not None else 0


def _window_reset_at(window: WhamUsageWindow | None) -> str:
    if window is None or window.reset_at is None:
        return ""
    return _utc_iso(window.reset_at)


def _validate_business_input(input_: BusinessAccessTokenPayloadInput) -> None:
    if input_.credential_type not in {"team_5h_weekly", "team_monthly"}:
        raise SpacePayloadError(
            "business payload credential_type must be team_5h_weekly or team_monthly"
        )
    for field_name in ("access_token", "chatgpt_account_id", "chatgpt_user_id", "email"):
        if not str(getattr(input_, field_name) or "").strip():
            raise SpacePayloadError(f"{field_name} is required")


def _assert_credential_type(input_: BusinessAccessTokenPayloadInput, *, expected: str) -> None:
    if input_.credential_type != expected:
        raise SpacePayloadError(
            f"credential_type mismatch: expected={expected} actual={input_.credential_type}"
        )


def _utc_iso(value: datetime) -> str:
    normalized = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.isoformat().replace("+00:00", "Z")
