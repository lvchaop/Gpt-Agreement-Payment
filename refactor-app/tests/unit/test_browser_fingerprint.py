from __future__ import annotations

import pytest

from refactor_app.config.browser_fingerprint import (
    BROWSER_SEC_CH_UA,
    BROWSER_USER_AGENT,
    browser_fingerprint_for,
)
from refactor_app.config.settings import Settings
from refactor_app.plugins.openai_auth_protocol import http_client, sentinel, sentinel_quickjs
from refactor_app.plugins.openai_chatgpt.client import (
    _accept_headers,
    _codex_responses_headers,
    _team_headers,
    _wham_headers,
)


def test_chrome142_fingerprint_fields_are_consistent() -> None:
    fingerprint = browser_fingerprint_for("chrome142")

    assert fingerprint.impersonate == "chrome142"
    assert fingerprint.major_version == 142
    assert "Chrome/142.0.0.0" in fingerprint.user_agent
    assert fingerprint.sec_ch_ua == (
        '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"'
    )
    assert fingerprint.sec_ch_ua_full_version == '"142.0.0.0"'
    assert '"Google Chrome";v="142.0.0.0"' in fingerprint.sec_ch_ua_full_version_list
    assert fingerprint.sec_ch_ua_platform == '"macOS"'
    assert fingerprint.navigator_platform == "MacIntel"


def test_browser_impersonate_can_be_set_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_BROWSER_IMPERSONATE", "chrome136")

    assert Settings(_env_file=None).browser_impersonate == "chrome136"


def test_browser_fingerprint_rejects_non_chrome_value() -> None:
    with pytest.raises(ValueError, match="unsupported browser impersonate value"):
        browser_fingerprint_for("safari260")


def test_manual_http_fingerprint_consumers_share_central_values() -> None:
    assert http_client.USER_AGENT == BROWSER_USER_AGENT
    assert sentinel.DEFAULT_UA == BROWSER_USER_AGENT
    assert sentinel.DEFAULT_SEC_CH_UA == BROWSER_SEC_CH_UA
    assert sentinel_quickjs.DEFAULT_UA == BROWSER_USER_AGENT
    assert sentinel_quickjs.DEFAULT_SEC_CH_UA == BROWSER_SEC_CH_UA

    headers = [
        _team_headers(access_token="token", team_id="space-id"),
        _accept_headers(access_token="token"),
        _codex_responses_headers(access_token="token", team_id="space-id"),
        _wham_headers(access_token="token"),
    ]
    assert all(item["user-agent"] == BROWSER_USER_AGENT for item in headers)
