from __future__ import annotations

from urllib.parse import unquote, urlparse

import pytest

from refactor_app.application.jobs import handlers
from refactor_app.application.workflows.registration_proxy import (
    RegistrationProxyError,
    backbone_username_for_country,
    build_registration_backbone_proxy,
    registration_backbone_endpoint_number,
)
from refactor_app.config.settings import Settings


def test_registration_proxy_hash_is_stable_for_normalized_email() -> None:
    first = registration_backbone_endpoint_number(" Target.User@example.com ", 20_000)
    second = registration_backbone_endpoint_number("target.user@EXAMPLE.COM", 20_000)

    assert first == second == 15_716
    assert registration_backbone_endpoint_number("other@example.com", 20_000) == 4_473


def test_registration_proxy_builds_country_scoped_backbone_endpoint() -> None:
    proxy = build_registration_backbone_proxy(
        email="Target.User@example.com",
        country_code="jp",
        endpoint_count=20_000,
        source_scheme="http",
        source_host="p.webshare.io",
        source_port=80,
        source_username="base-3632",
        source_password="password/with:special",
        gateway_resolver=lambda _host, _port: ["192.0.2.10", "192.0.2.11"],
    )

    parsed = urlparse(proxy.proxy_url)
    assert unquote(parsed.username or "") == "base-JP-15716"
    assert unquote(parsed.password or "") == "password/with:special"
    assert parsed.hostname == "192.0.2.11"
    assert parsed.port == 80
    assert proxy.endpoint_id == "backbone-15716"
    assert proxy.country_code == "JP"
    assert "password/with:special" not in repr(proxy)


def test_backbone_country_replaces_existing_country() -> None:
    assert backbone_username_for_country("base-CA-3632", "US") == "base-US-3632"


def test_registration_proxy_rejects_invalid_configuration() -> None:
    with pytest.raises(RegistrationProxyError, match="count must be positive"):
        registration_backbone_endpoint_number("target@example.com", 0)

    with pytest.raises(RegistrationProxyError, match="two-letter country code"):
        build_registration_backbone_proxy(
            email="target@example.com",
            country_code="USA",
            endpoint_count=20_000,
            source_scheme="http",
            source_host="p.webshare.io",
            source_port=80,
            source_username="base-1",
            source_password="password",
            gateway_resolver=lambda _host, _port: ["192.0.2.10"],
        )

    with pytest.raises(RegistrationProxyError, match="no IPv4 address"):
        build_registration_backbone_proxy(
            email="target@example.com",
            country_code="US",
            endpoint_count=20_000,
            source_scheme="http",
            source_host="p.webshare.io",
            source_port=80,
            source_username="base-1",
            source_password="password",
            gateway_resolver=lambda _host, _port: [],
        )


def test_registration_proxy_country_setting_defaults_to_us_and_is_configurable(
    monkeypatch,
) -> None:
    monkeypatch.delenv("REFACTOR_APP_PROTOCOL_REGISTER_PROXY_COUNTRY", raising=False)
    assert Settings(_env_file=None).protocol_register_proxy_country == "US"

    monkeypatch.setenv("REFACTOR_APP_PROTOCOL_REGISTER_PROXY_COUNTRY", "JP")
    assert Settings(_env_file=None).protocol_register_proxy_country == "JP"


def test_registration_job_input_uses_configured_country_and_allows_explicit_override() -> None:
    configured = handlers._protocol_registration_input(
        {"mode": "email_protocol_no_phone"},
        default_proxy_country="JP",
    )
    overridden = handlers._protocol_registration_input(
        {"mode": "email_protocol_no_phone", "proxy_country": "CA"},
        default_proxy_country="JP",
    )

    assert configured.proxy_country == "JP"
    assert overridden.proxy_country == "CA"
