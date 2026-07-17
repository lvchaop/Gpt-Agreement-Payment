from __future__ import annotations

from datetime import UTC, datetime

from refactor_app.application.workflows.space_payloads import (
    BusinessAccessTokenPayloadInput,
    build_team_5h_weekly_cpa_payload,
    build_team_5h_weekly_sub2api_payload,
    build_team_monthly_sub2api_payload,
)
from refactor_app.application.workflows.space_usage import parse_wham_usage_windows


def test_build_team_5h_weekly_business_access_token_payload() -> None:
    usage_windows = tuple(
        parse_wham_usage_windows(
            {
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 100,
                        "limit_window_seconds": 18_000,
                        "reset_after_seconds": 239,
                        "reset_at": 1_783_282_065,
                    },
                    "secondary_window": {
                        "used_percent": 46,
                        "limit_window_seconds": 604_800,
                        "reset_after_seconds": 503_154,
                        "reset_at": 1_783_389_439,
                    },
                }
            }
        )
    )
    input_ = BusinessAccessTokenPayloadInput(
        access_token="at-1",
        chatgpt_account_id="workspace-1",
        chatgpt_user_id="user-1",
        email="child@example.test",
        credential_type="team_5h_weekly",
        usage_windows=usage_windows,
        exported_at=datetime(2026, 7, 4, 5, 48, 27, tzinfo=UTC),
    )

    sub2api = build_team_5h_weekly_sub2api_payload(input_)
    cpa = build_team_5h_weekly_cpa_payload(input_)

    account = sub2api["accounts"][0]
    assert cpa == sub2api
    assert sub2api["exported_at"] == "2026-07-04T05:48:27Z"
    assert account["name"] == "codex-child@example.test"
    assert account["credentials"]["access_token"] == "at-1"
    assert account["credentials"]["auth_mode"] == "personalAccessToken"
    assert account["credentials"]["chatgpt_account_id"] == "workspace-1"
    assert account["credentials"]["chatgpt_user_id"] == "user-1"
    assert account["credentials"]["openai_auth_mode"] == "personal_access_token"
    assert account["credentials"]["token_type"] == "Bearer"
    assert account["credentials"]["model_mapping"]["gpt-5.3-codex"] == "gpt-5.3-codex"
    assert account["credentials"]["model_mapping"]["gpt-5.6-luna"] == "gpt-5.6-luna"
    assert account["credentials"]["model_mapping"]["gpt-5.6-sol"] == "gpt-5.6-sol"
    assert account["credentials"]["model_mapping"]["gpt-5.6-terra"] == "gpt-5.6-terra"
    assert account["extra"]["auth_provider"] == "codex_personal_access_token"
    assert account["extra"]["codex_5h_used_percent"] == 100
    assert account["extra"]["codex_7d_used_percent"] == 46


def test_build_team_monthly_business_access_token_payload_without_weekly_window() -> None:
    usage_windows = tuple(
        parse_wham_usage_windows(
            {
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 95,
                        "limit_window_seconds": 2_592_000,
                        "reset_after_seconds": 2_592_000,
                        "reset_at": 1_785_856_144,
                    },
                    "secondary_window": None,
                }
            }
        )
    )
    body = build_team_monthly_sub2api_payload(
        BusinessAccessTokenPayloadInput(
            access_token="at-1",
            chatgpt_account_id="workspace-1",
            chatgpt_user_id="user-1",
            email="child@example.test",
            credential_type="team_monthly",
            usage_windows=usage_windows,
            exported_at=datetime(2026, 7, 4, 5, 48, 27, tzinfo=UTC),
        )
    )

    extra = body["accounts"][0]["extra"]
    assert extra["codex_primary_used_percent"] == 95
    assert extra["codex_primary_window_minutes"] == 43_200
    assert extra["codex_secondary_used_percent"] == 0
    assert extra["codex_secondary_window_minutes"] == 0
