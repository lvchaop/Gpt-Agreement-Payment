from __future__ import annotations

import pytest

from refactor_app.config.browser_fingerprint import (
    BROWSER_SEC_CH_UA,
    BROWSER_USER_AGENT,
    browser_fingerprint_for,
    browser_fingerprint_for_email,
)
from refactor_app.config.settings import Settings
from refactor_app.plugins.openai_auth_protocol import http_client, sentinel, sentinel_quickjs
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow
from refactor_app.plugins.openai_auth_protocol.config import Config
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


@pytest.mark.parametrize(
    ("impersonate", "expected_sec_ch_ua"),
    [
        (
            "chrome136",
            '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        ),
        (
            "chrome142",
            '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        ),
        (
            "chrome145",
            '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        ),
        (
            "chrome146",
            '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
        ),
    ],
)
def test_supported_chrome_brand_order_matches_curl_profile(
    impersonate: str,
    expected_sec_ch_ua: str,
) -> None:
    fingerprint = browser_fingerprint_for(impersonate)

    assert fingerprint.sec_ch_ua == expected_sec_ch_ua
    assert [
        part.split('";v=')[0] for part in fingerprint.sec_ch_ua_full_version_list.split(", ")
    ] == [part.split('";v=')[0] for part in expected_sec_ch_ua.split(", ")]


def test_browser_impersonate_can_be_set_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_BROWSER_IMPERSONATE", "chrome136")

    assert Settings(_env_file=None).browser_impersonate == "chrome136"


def test_browser_fingerprint_rejects_non_chrome_value() -> None:
    with pytest.raises(ValueError, match="unsupported browser impersonate value"):
        browser_fingerprint_for("safari260")


def test_email_fingerprint_is_normalized_and_stable() -> None:
    first = browser_fingerprint_for_email("  User.Name@Example.COM ")
    second = browser_fingerprint_for_email("user.name@example.com")

    assert first == second
    assert f"Chrome/{first.major_version}.0.0.0" in first.user_agent
    assert f'"Google Chrome";v="{first.major_version}"' in first.sec_ch_ua


def test_email_fingerprint_generates_varied_coherent_device_profiles() -> None:
    fingerprints = [
        browser_fingerprint_for_email(f"user-{index}@example.com") for index in range(512)
    ]

    assert len({item.impersonate for item in fingerprints}) == 4
    assert {item.sec_ch_ua_platform for item in fingerprints} == {
        '"Windows"',
        '"macOS"',
        '"Linux"',
    }
    assert len(set(fingerprints)) >= 250
    assert (
        len(
            {
                (
                    item.sec_ch_ua_platform,
                    item.screen_width,
                    item.screen_height,
                    item.device_pixel_ratio,
                )
                for item in fingerprints
            }
        )
        >= 18
    )
    for item in fingerprints:
        if item.sec_ch_ua_platform == '"Windows"':
            assert item.navigator_platform == "Win32"
            assert item.device_pixel_ratio in {1, 1.25, 1.5}
            assert item.hardware_concurrency in {4, 6, 8, 12, 16, 20}
        elif item.sec_ch_ua_platform == '"macOS"':
            assert item.navigator_platform == "MacIntel"
            assert item.device_pixel_ratio == 2
            if item.sec_ch_ua_arch == '"arm"':
                assert item.hardware_concurrency in {8, 10, 12, 14}
            else:
                assert item.hardware_concurrency in {4, 8, 12}
        else:
            assert item.sec_ch_ua_platform == '"Linux"'
            assert item.navigator_platform == "Linux x86_64"
            assert item.device_pixel_ratio in {1, 1.25}
            assert item.hardware_concurrency in {4, 8, 12, 16}
        assert item.device_memory in {4, 8}


def test_email_fingerprint_requires_mailbox_identity() -> None:
    with pytest.raises(ValueError, match="email is required"):
        browser_fingerprint_for_email("")


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        (
            "alpha@example.com",
            ("chrome142", '"Linux"', '"x86"', 2560, 1440, 16, 4, 1),
        ),
        (
            "beta@example.com",
            ("chrome142", '"macOS"', '"arm"', 1440, 900, 8, 8, 2),
        ),
        (
            "gamma@example.com",
            ("chrome146", '"macOS"', '"x86"', 1680, 1050, 8, 8, 2),
        ),
    ],
)
def test_email_fingerprint_catalog_is_versioned_and_stable(
    email: str,
    expected: tuple[object, ...],
) -> None:
    fingerprint = browser_fingerprint_for_email(email)

    assert (
        fingerprint.impersonate,
        fingerprint.sec_ch_ua_platform,
        fingerprint.sec_ch_ua_arch,
        fingerprint.screen_width,
        fingerprint.screen_height,
        fingerprint.hardware_concurrency,
        fingerprint.device_memory,
        fingerprint.device_pixel_ratio,
    ) == expected


def test_auth_flow_uses_one_email_fingerprint_for_http_and_runtime() -> None:
    fingerprint = browser_fingerprint_for_email("stable-flow@example.com")
    config = Config()
    config.proxy_meta = {"register": {"country_code": "US"}}
    config.browser_fingerprint = fingerprint
    flow = AuthFlow(config)
    try:
        headers = flow._common_headers("https://auth.openai.com/log-in")
        profile = flow._sentinel_runtime_context.browser_profile

        assert flow._impersonate_candidates == [fingerprint.impersonate]
        assert headers["User-Agent"] == fingerprint.user_agent
        assert headers["sec-ch-ua"] == fingerprint.sec_ch_ua
        assert headers["sec-ch-ua-platform"] == fingerprint.sec_ch_ua_platform
        raw_headers = flow._raw_http_session().headers
        assert raw_headers["User-Agent"] == fingerprint.user_agent
        assert raw_headers["sec-ch-ua"] == fingerprint.sec_ch_ua
        assert raw_headers["sec-ch-ua-mobile"] == "?0"
        assert raw_headers["sec-ch-ua-platform"] == fingerprint.sec_ch_ua_platform
        assert profile["user_agent"] == fingerprint.user_agent
        assert profile["navigator_platform"] == fingerprint.navigator_platform
        assert flow.result.browser_user_agent == fingerprint.user_agent
        assert flow.result.browser_impersonate == fingerprint.impersonate
    finally:
        flow.close()


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
