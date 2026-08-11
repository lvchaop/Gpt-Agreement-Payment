from __future__ import annotations

from hashlib import sha256
from urllib.parse import unquote, urlparse

import pytest

from refactor_app.application.jobs import handlers
from refactor_app.application.workflows import registration_proxy
from refactor_app.application.workflows.registration_proxy import (
    CliproxyProxyConfig,
    CliproxyProxyError,
    build_cliproxy_proxy,
    cliproxy_stable_sid,
    cliproxy_username_for_email,
    detect_machine_egress_country,
    detect_proxy_egress_country,
    probe_cliproxy_proxy,
    resolve_cliproxy_proxy,
    select_cliproxy_gateway_host,
)
from refactor_app.config.settings import Settings


def _config(**overrides) -> CliproxyProxyConfig:
    values = {
        "host": "us.cliproxy.io",
        "port": 1234,
        "username": "base-user",
        "password": "password/with:special",
        "gateway_mode": "fixed",
    }
    values.update(overrides)
    return CliproxyProxyConfig(**values)


def test_registration_proxy_hash_is_stable_for_normalized_email() -> None:
    first = cliproxy_stable_sid(" Target.User@example.com ")
    second = cliproxy_stable_sid("target.user@EXAMPLE.COM")

    assert first == second
    assert len(first) == 64
    assert first == sha256(b"target.user@example.com").hexdigest()


def test_registration_proxy_hash_is_stable_and_isolated_by_country() -> None:
    us_sid = cliproxy_stable_sid(" Target.User@example.com ", "us")
    normalized_us_sid = cliproxy_stable_sid("target.user@EXAMPLE.COM", "US")
    jp_sid = cliproxy_stable_sid("target.user@example.com", "JP")

    assert us_sid == normalized_us_sid
    assert us_sid == sha256(b"target.user@example.com|US").hexdigest()
    assert jp_sid == sha256(b"target.user@example.com|JP").hexdigest()
    assert us_sid != jp_sid


def test_cliproxy_username_contains_documented_routing_fields() -> None:
    sid = "a" * 64
    username = cliproxy_username_for_email(
        base_username="base-user",
        country_code="us",
        sid=sid,
        state="Louisiana",
        session_duration_minutes=15,
    )

    assert username == f"base-user-region-US-st-Louisiana-sid-{sid}-t-15"


def test_registration_proxy_builds_authenticated_cliproxy_url_without_secret_repr() -> None:
    sid = "b" * 64
    proxy = build_cliproxy_proxy(
        email="Target.User@example.com",
        country_code="jp",
        sid=sid,
        host="us.cliproxy.io",
        port=1234,
        scheme="http",
        username="base-user",
        password="password/with:special",
        state="Louisiana",
        session_duration_minutes=15,
    )

    parsed = urlparse(proxy.proxy_url)
    assert unquote(parsed.username or "") == (
        f"base-user-region-JP-st-Louisiana-sid-{sid}-t-15"
    )
    assert unquote(parsed.password or "") == "password/with:special"
    assert parsed.hostname == "us.cliproxy.io"
    assert parsed.port == 1234
    assert proxy.provider == "cliproxy"
    assert proxy.sid == sid
    assert "password/with:special" not in repr(proxy)


def test_registration_proxy_probes_stable_sid_before_random_sid() -> None:
    seen_urls: list[str] = []

    def probe(proxy_url: str) -> bool:
        seen_urls.append(proxy_url)
        return len(seen_urls) == 2

    proxy = resolve_cliproxy_proxy(
        email=" Target.User@example.com ",
        country_code="US",
        config=_config(max_sid_attempts=3),
        probe=probe,
    )

    stable_sid = cliproxy_stable_sid("target.user@example.com", "US")
    assert len(seen_urls) == 2
    assert stable_sid in seen_urls[0]
    assert stable_sid not in seen_urls[1]
    assert proxy.sid_source == "random_uuid"
    assert proxy.probe_attempts == 2


def test_registration_proxy_returns_stable_sid_when_probe_succeeds() -> None:
    proxy = resolve_cliproxy_proxy(
        email="target@example.com",
        country_code="US",
        config=_config(max_sid_attempts=4),
        probe=lambda _proxy_url: True,
    )

    assert proxy.sid == cliproxy_stable_sid("target@example.com", "US")
    assert proxy.sid_source == "email_sha256"
    assert proxy.probe_attempts == 1


def test_registration_proxy_default_probe_rotates_country_mismatch(monkeypatch) -> None:
    seen_urls: list[str] = []
    observed_countries = iter(("ID", "US"))

    monkeypatch.setattr(
        registration_proxy,
        "probe_cliproxy_proxy",
        lambda proxy_url, **_kwargs: seen_urls.append(proxy_url) or True,
    )
    monkeypatch.setattr(
        registration_proxy,
        "detect_proxy_egress_country",
        lambda _proxy_url, **_kwargs: next(observed_countries),
    )

    proxy = resolve_cliproxy_proxy(
        email="target@example.com",
        country_code="US",
        config=_config(max_sid_attempts=3),
    )

    assert len(seen_urls) == 2
    assert cliproxy_stable_sid("target@example.com", "US") in seen_urls[0]
    assert proxy.country_code == "US"
    assert proxy.sid_source == "random_uuid"
    assert proxy.probe_attempts == 2


def test_registration_proxy_applies_country_specific_state() -> None:
    seen_urls: list[str] = []

    proxy = resolve_cliproxy_proxy(
        email="target@example.com",
        country_code="JP",
        config=_config(state="California", jp_state="Tokyo"),
        probe=lambda proxy_url: seen_urls.append(proxy_url) or True,
    )

    username = unquote(urlparse(seen_urls[0]).username or "")
    assert "-region-JP-" in username
    assert "-st-California-" not in username
    assert "-st-Tokyo-" in username
    assert proxy.country_code == "JP"


def test_registration_proxy_uses_local_trojan_pool_without_remote_credentials(
    monkeypatch,
) -> None:
    seen: dict[str, object] = {"probes": []}

    class Node:
        def __init__(self, port: int) -> None:
            self.local_http_url = f"http://127.0.0.1:{port}"
            self.country_code = "US"

    class Manager:
        @staticmethod
        def ensure_started() -> None:
            seen["started"] = True

        @staticmethod
        def candidate_nodes(*, email: str, country_code: str):
            seen["selection"] = (email, country_code)
            return [Node(18081), Node(18082)]

    monkeypatch.setattr(
        registration_proxy,
        "get_trojan_proxy_pool_manager",
        lambda *_args: Manager(),
    )

    def probe(proxy_url: str) -> bool:
        seen["probes"].append(proxy_url)
        return proxy_url.endswith(":18082")

    proxy = resolve_cliproxy_proxy(
        email=" Target@example.com ",
        country_code="us",
        config=CliproxyProxyConfig(
            host="",
            port=0,
            mode="trojan_pool",
            trojan_pool_file="runtime/proxy/trojan-pool.yaml",
            max_sid_attempts=4,
        ),
        probe=probe,
    )

    assert seen == {
        "started": True,
        "selection": ("target@example.com", "US"),
        "probes": ["http://127.0.0.1:18081", "http://127.0.0.1:18082"],
    }
    assert proxy.proxy_url == "http://127.0.0.1:18082"
    assert proxy.country_code == "US"
    assert proxy.provider == "local_trojan_pool"
    assert proxy.proxy_mode == "trojan_pool_sticky"
    assert proxy.proxy_source == "target_email_country_hash"
    assert proxy.sid_source == "email_sha256_failover"
    assert proxy.probe_attempts == 2


def test_registration_proxy_trojan_pool_does_not_fall_back_to_remote(monkeypatch) -> None:
    class Manager:
        @staticmethod
        def ensure_started() -> None:
            return None

        @staticmethod
        def candidate_nodes(**_kwargs):
            return [
                type(
                    "Node",
                    (),
                    {"local_http_url": "http://127.0.0.1:18081", "country_code": "JP"},
                )()
            ]

    monkeypatch.setattr(
        registration_proxy,
        "get_trojan_proxy_pool_manager",
        lambda *_args: Manager(),
    )
    with pytest.raises(CliproxyProxyError, match="Trojan pool probe failed") as exc_info:
        resolve_cliproxy_proxy(
            email="target@example.com",
            country_code="JP",
            config=CliproxyProxyConfig(
                host="remote.example.test",
                port=443,
                username="remote-user",
                password="remote-password",
                mode="trojan_pool",
                trojan_pool_file="runtime/proxy/trojan-pool.yaml",
            ),
            probe=lambda _proxy_url: False,
        )

    assert "remote.example.test" not in str(exc_info.value)
    assert "remote-password" not in str(exc_info.value)


@pytest.mark.parametrize("country_code", ["JP", "SG", "AU"])
def test_cliproxy_auto_gateway_uses_sg_for_asia_pacific(
    monkeypatch,
    country_code: str,
) -> None:
    monkeypatch.setattr(
        registration_proxy,
        "detect_machine_egress_country",
        lambda *_args: country_code,
    )

    host = select_cliproxy_gateway_host(
        _config(gateway_mode="auto", us_host="us.arxlabs.io", sg_host="sg.arxlabs.io")
    )

    assert host == "sg.arxlabs.io"


@pytest.mark.parametrize("country_code", ["US", "DE", "BR"])
def test_cliproxy_auto_gateway_uses_us_for_europe_and_americas(
    monkeypatch,
    country_code: str,
) -> None:
    monkeypatch.setattr(
        registration_proxy,
        "detect_machine_egress_country",
        lambda *_args: country_code,
    )

    host = select_cliproxy_gateway_host(
        _config(gateway_mode="auto", us_host="us.arxlabs.io", sg_host="sg.arxlabs.io")
    )

    assert host == "us.arxlabs.io"


def test_cliproxy_auto_gateway_falls_back_to_fixed_host_when_trace_fails(monkeypatch) -> None:
    def fail_trace(*_args) -> str:
        raise TimeoutError("trace timed out")

    monkeypatch.setattr(registration_proxy, "detect_machine_egress_country", fail_trace)

    host = select_cliproxy_gateway_host(
        _config(gateway_mode="auto", host="fallback.arxlabs.io")
    )

    assert host == "fallback.arxlabs.io"


def test_cliproxy_fixed_gateway_does_not_probe_machine_egress(monkeypatch) -> None:
    def unexpected_trace(*_args) -> str:
        raise AssertionError("fixed mode must not probe")

    monkeypatch.setattr(registration_proxy, "detect_machine_egress_country", unexpected_trace)

    assert select_cliproxy_gateway_host(_config(host="fixed.arxlabs.io")) == (
        "fixed.arxlabs.io"
    )


def test_machine_egress_probe_bypasses_environment_proxy_and_is_cached(monkeypatch) -> None:
    captured: dict[str, object] = {"open_calls": 0}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return b"ip=203.0.113.8\nloc=JP\ncolo=NRT\n"

    class Opener:
        def open(self, request, *, timeout):
            captured["open_calls"] = int(captured["open_calls"]) + 1
            captured["request_url"] = request.full_url
            captured["timeout"] = timeout
            return Response()

    def fake_build_opener(proxy_handler):
        captured["proxies"] = proxy_handler.proxies
        return Opener()

    detect_machine_egress_country.cache_clear()
    monkeypatch.setattr(registration_proxy, "build_opener", fake_build_opener)

    assert detect_machine_egress_country("https://trace.example.test", 3.5) == "JP"
    assert detect_machine_egress_country("https://trace.example.test", 3.5) == "JP"
    assert captured == {
        "open_calls": 1,
        "request_url": "https://trace.example.test",
        "timeout": 3.5,
        "proxies": {},
    }
    detect_machine_egress_country.cache_clear()


def test_proxy_egress_probe_uses_selected_proxy_and_reads_country(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 200
        text = "ip=198.51.100.9\nloc=US\ncolo=FAT\n"

    class Client:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, url, **kwargs):
            captured["trust_env"] = self.trust_env
            captured["url"] = url
            captured["get_kwargs"] = kwargs
            return Response()

    def session_factory(**kwargs):
        captured["session_kwargs"] = kwargs
        return Client()

    monkeypatch.setattr(registration_proxy.curl_requests, "Session", session_factory)

    proxy_url = "http://proxy-user:proxy-password@us.example.test:443"
    assert (
        detect_proxy_egress_country(
            proxy_url,
            trace_url="https://trace.example.test",
            timeout_s=4.0,
        )
        == "US"
    )
    assert captured["session_kwargs"] == {
        "impersonate": registration_proxy.BROWSER_IMPERSONATE,
        "proxies": {"http": proxy_url, "https": proxy_url},
    }
    assert captured["trust_env"] is False
    assert captured["url"] == "https://trace.example.test"
    assert captured["get_kwargs"]["timeout"] == 4.0


@pytest.mark.parametrize(
    ("status_code", "payload"),
    [
        (502, "ip=198.51.100.9\nloc=US\n"),
        (200, "loc=US\n"),
        (200, "ip=198.51.100.9\nloc=XX\n"),
        (200, "ip=198.51.100.9\nloc=USA\n"),
    ],
)
def test_proxy_egress_probe_rejects_unusable_trace(
    monkeypatch,
    status_code: int,
    payload: str,
) -> None:
    class Response:
        pass

    response = Response()
    response.status_code = status_code
    response.text = payload

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, *_args, **_kwargs):
            return response

    monkeypatch.setattr(
        registration_proxy.curl_requests,
        "Session",
        lambda **_kwargs: Client(),
    )

    with pytest.raises(CliproxyProxyError):
        detect_proxy_egress_country(
            "http://secret-user:secret-password@proxy.example.test:443",
            trace_url="https://trace.example.test",
        )


def test_cliproxy_auto_gateway_is_used_to_build_proxy(monkeypatch) -> None:
    seen_urls: list[str] = []
    monkeypatch.setattr(
        registration_proxy,
        "detect_machine_egress_country",
        lambda *_args: "JP",
    )

    resolve_cliproxy_proxy(
        email="target@example.com",
        country_code="US",
        config=_config(
            gateway_mode="auto",
            us_host="us.arxlabs.io",
            sg_host="sg.arxlabs.io",
        ),
        probe=lambda proxy_url: seen_urls.append(proxy_url) or True,
    )

    assert urlparse(seen_urls[0]).hostname == "sg.arxlabs.io"


def test_registration_proxy_rejects_all_unhealthy_candidates_without_secret_in_error() -> None:
    with pytest.raises(CliproxyProxyError, match="after 3 attempts") as exc_info:
        resolve_cliproxy_proxy(
            email="target@example.com",
            country_code="US",
            config=_config(password="do-not-leak", max_sid_attempts=3),
            probe=lambda _proxy_url: False,
        )

    assert "do-not-leak" not in str(exc_info.value)
    assert "us.cliproxy.io" not in str(exc_info.value)


def test_registration_proxy_rejects_invalid_configuration() -> None:
    with pytest.raises(CliproxyProxyError, match="port"):
        resolve_cliproxy_proxy(
            email="target@example.com",
            country_code="US",
            config=_config(port=0),
            probe=lambda _proxy_url: True,
        )

    with pytest.raises(CliproxyProxyError, match="two-letter country code"):
        build_cliproxy_proxy(
            email="target@example.com",
            country_code="USA",
            sid="c" * 64,
            host="us.cliproxy.io",
            port=1234,
            scheme="http",
            username="base-user",
            password="password",
        )


def test_cliproxy_probe_uses_proxy_and_requires_chatgpt_csrf_token(monkeypatch) -> None:
    captured: dict = {}

    class Response:
        status_code = 200

        @staticmethod
        def json() -> dict[str, str]:
            return {"csrfToken": "csrf-token"}

    class Session:
        def __init__(self, **kwargs) -> None:
            captured["session"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, url, **kwargs):
            captured["get"] = {"url": url, **kwargs}
            return Response()

    monkeypatch.setattr(registration_proxy.curl_requests, "Session", Session)

    assert probe_cliproxy_proxy(
        "http://clip-user:clip-pass@us.cliproxy.io:1234",
        probe_url="https://chatgpt.com/api/auth/csrf",
        timeout_s=7.5,
    )
    assert captured["session"]["proxies"] == {
        "http": "http://clip-user:clip-pass@us.cliproxy.io:1234",
        "https": "http://clip-user:clip-pass@us.cliproxy.io:1234",
    }
    assert captured["session"]["impersonate"]
    assert captured["get"]["url"] == "https://chatgpt.com/api/auth/csrf"
    assert captured["get"]["timeout"] == 7.5


def test_cliproxy_settings_accept_prefixed_environment(monkeypatch) -> None:
    names = (
        "REFACTOR_APP_CLIPROXY_MODE",
        "REFACTOR_APP_CLIPROXY_TROJAN_POOL_FILE",
        "REFACTOR_APP_CLIPROXY_HOST",
        "REFACTOR_APP_CLIPROXY_PORT",
        "REFACTOR_APP_CLIPROXY_USERNAME",
        "REFACTOR_APP_CLIPROXY_PASSWORD",
        "REFACTOR_APP_CLIPROXY_GATEWAY_MODE",
        "REFACTOR_APP_CLIPROXY_US_HOST",
        "REFACTOR_APP_CLIPROXY_SG_HOST",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_MODE", "trojan_pool")
    monkeypatch.setenv(
        "REFACTOR_APP_CLIPROXY_TROJAN_POOL_FILE",
        "runtime/proxy/trojan-pool.yaml",
    )
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_HOST", "sg.cliproxy.io")
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_PORT", "2345")
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_USERNAME", "clip-user")
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_PASSWORD", "clip-pass")
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_GATEWAY_MODE", "auto")
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_US_HOST", "us.arxlabs.io")
    monkeypatch.setenv("REFACTOR_APP_CLIPROXY_SG_HOST", "sg.arxlabs.io")

    settings = Settings(_env_file=None)
    assert settings.cliproxy_mode == "trojan_pool"
    assert settings.cliproxy_trojan_pool_file == "runtime/proxy/trojan-pool.yaml"
    assert settings.cliproxy_host == "sg.cliproxy.io"
    assert settings.cliproxy_port == 2345
    assert settings.cliproxy_username == "clip-user"
    assert settings.cliproxy_password == "clip-pass"
    assert settings.cliproxy_gateway_mode == "auto"
    assert settings.cliproxy_us_host == "us.arxlabs.io"
    assert settings.cliproxy_sg_host == "sg.arxlabs.io"
    assert "clip-pass" not in repr(settings)


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
