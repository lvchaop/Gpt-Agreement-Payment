from __future__ import annotations

from refactor_app.application.workflows.space_recycle import _parse_codex_usage_headers
from refactor_app.application.workflows.space_usage import (
    infer_credential_type,
    parse_wham_usage_windows,
    usage_status_from_percent,
)


def test_parse_team_five_hour_weekly_usage_windows() -> None:
    payload = {
        "plan_type": "team",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {
                "used_percent": 1,
                "limit_window_seconds": 18_000,
                "reset_after_seconds": 18_000,
                "reset_at": 1_783_282_065,
            },
            "secondary_window": {
                "used_percent": 100,
                "limit_window_seconds": 604_800,
                "reset_after_seconds": 125_375,
                "reset_at": 1_783_389_439,
            },
        },
    }

    windows = parse_wham_usage_windows(payload)

    assert [item.quota_window_kind for item in windows] == ["five_hour", "weekly"]
    assert infer_credential_type(space_type="business", usage_payload=payload) == "team_5h_weekly"
    assert usage_status_from_percent(windows[1].used_percent) == "used"


def test_infer_business_five_hour_weekly_from_weekly_window_only() -> None:
    payload = {
        "plan_type": "team",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 0,
                "limit_window_seconds": 604_800,
                "reset_after_seconds": 604_800,
                "reset_at": 1_783_389_439,
            },
            "secondary_window": None,
        },
    }

    windows = parse_wham_usage_windows(payload)

    assert [item.quota_window_kind for item in windows] == ["weekly"]
    assert infer_credential_type(
        space_type="business",
        usage_payload=payload,
    ) == "team_5h_weekly"


def test_parse_personal_monthly_usage_window() -> None:
    payload = {
        "plan_type": "free",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 5,
                "limit_window_seconds": 2_592_000,
                "reset_after_seconds": 2_592_000,
                "reset_at": 1_785_856_144,
            },
            "secondary_window": None,
        },
    }

    windows = parse_wham_usage_windows(payload)

    assert [item.quota_window_kind for item in windows] == ["monthly"]
    assert infer_credential_type(space_type="personal", usage_payload=payload) == "personal_account"
    assert usage_status_from_percent(windows[0].used_percent) == "active"


def test_infer_business_monthly_from_monthly_window() -> None:
    payload = {
        "plan_type": "team",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 95,
                "limit_window_seconds": 2_592_000,
                "reset_after_seconds": 2_592_000,
                "reset_at": 1_785_856_144,
            },
            "secondary_window": None,
        },
    }

    assert infer_credential_type(space_type="business", usage_payload=payload) == "team_monthly"
    assert usage_status_from_percent(95) == "used"


def test_infer_business_monthly_from_variable_calendar_month_window() -> None:
    payload = {
        "plan_type": "team",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 0,
                "limit_window_seconds": 2_628_000,
                "reset_after_seconds": 2_628_000,
                "reset_at": 1_786_465_776,
            },
            "secondary_window": None,
        },
    }

    windows = parse_wham_usage_windows(payload)

    assert [item.quota_window_kind for item in windows] == ["monthly"]
    assert windows[0].limit_window_seconds == 2_628_000
    assert infer_credential_type(space_type="business", usage_payload=payload) == "team_monthly"


def test_parse_codex_monthly_usage_headers_accepts_variable_calendar_window() -> None:
    windows = _parse_codex_usage_headers(
        {
            "x-codex-primary-used-percent": "70",
            "x-codex-primary-window-minutes": "43800",
            "x-codex-primary-reset-after-seconds": "12345",
        }
    )

    assert windows == [
        {
            "quota_window_kind": "monthly",
            "usage_percent": 70,
            "limit_window_seconds": 2_628_000,
            "reset_after_seconds": 12_345,
        }
    ]
