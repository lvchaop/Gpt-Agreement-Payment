from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from refactor_app.config.settings import Settings
from refactor_app.plugins.openai_auth_browser.browser_logging import (
    BrowserLogRecorder,
    redact_browser_value,
)
from refactor_app.plugins.openai_auth_browser.email_registration import (
    BrowserEmailRegistrationConfig,
    CamoufoxEmailRegistration,
)


class _EventTarget:
    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}

    def on(self, event: str, callback) -> None:
        self.handlers.setdefault(event, []).append(callback)

    def remove_listener(self, event: str, callback) -> None:
        self.handlers.get(event, []).remove(callback)

    def emit(self, event: str, *args) -> None:
        for callback in list(self.handlers.get(event, [])):
            callback(*args)


class _Page(_EventTarget):
    def __init__(self) -> None:
        super().__init__()
        self.url = "https://chatgpt.com/"


class _Request:
    method = "POST"
    url = "https://chatgpt.com/backend-api/submit?access_token=URL_SECRET&visible=yes"
    resource_type = "xhr"
    post_data = '{"password":"pw-secret","card_number":"4242424242424242","ok":true}'
    failure = ""

    def __init__(self, page: _Page) -> None:
        self.frame = SimpleNamespace(page=page)

    def all_headers(self) -> dict[str, str]:
        return {
            "authorization": "Bearer access-secret",
            "cookie": "session=secret-cookie",
            "content-type": "application/json",
        }


class _Response:
    status = 402
    status_text = "Payment Required"

    def __init__(self, request: _Request) -> None:
        self.request = request
        self.url = request.url

    def all_headers(self) -> dict[str, str]:
        return {"set-cookie": "session=another-secret", "content-type": "application/json"}

    def text(self) -> str:
        return '{"error":{"code":"card_declined","decline_code":"generic_decline"}}'


def test_browser_log_recorder_captures_events_and_redacts_sensitive_values(tmp_path) -> None:
    page = _Page()
    context = _EventTarget()
    context.pages = [page]
    emitted: list[tuple[str, dict, str]] = []
    path = tmp_path / "browser.log.jsonl"
    recorder = BrowserLogRecorder(
        path=path,
        emitter=lambda event, data, level: emitted.append((event, data, level)),
        capture_bodies=True,
        max_body_chars=20_000,
    )
    recorder.install(context)

    request = _Request(page)
    context.emit("request", request)
    context.emit("response", _Response(request))
    request.failure = "net::ERR_PROXY_CONNECTION_FAILED"
    context.emit("requestfailed", request)
    context.emit("requestfinished", request)
    page.emit(
        "console",
        SimpleNamespace(
            type="error",
            text="Bearer console-secret",
            location={"url": "https://chatgpt.com/app?token=console-token"},
        ),
    )
    page.emit("pageerror", RuntimeError("page crashed"))
    page.emit("framenavigated", SimpleNamespace(url="https://chatgpt.com/checkout"))
    recorder.close()

    entries = [json.loads(line) for line in path.read_text().splitlines()]
    event_names = {entry["event"] for entry in entries}
    assert {
        "browser.log.enabled",
        "browser.request",
        "browser.response",
        "browser.requestfailed",
        "browser.requestfinished",
        "browser.console",
        "browser.pageerror",
        "browser.framenavigated",
        "browser.log.closed",
    } <= event_names
    serialized = path.read_text()
    for secret in (
        "URL_SECRET",
        "access-secret",
        "secret-cookie",
        "pw-secret",
        "4242424242424242",
        "console-secret",
        "console-token",
    ):
        assert secret not in serialized
    assert "generic_decline" in serialized
    assert any(event == "browser.response" and level == "WARN" for event, _, level in emitted)


def test_browser_log_redacts_identity_values_at_every_nested_level() -> None:
    raw = {
        "email": "customer.alpha@example.com",
        "first_name": "FirstnameSecret",
        "lastName": "LastnameSecret",
        "profile": {
            "full_name": "Fullname Secret",
            "network": [
                "public=8.8.8.8",
                "private=192.168.10.24",
                "loopback=127.0.0.1",
                "ipv6=2001:db8:85a3::8a2e:370:7334",
                "link_local=fe80::1%en0",
                "mapped=::ffff:10.0.0.7",
                b"backup-email@example.net from 172.16.0.9",
            ],
        },
        "owner@example.org": "key contains an email",
        "event_name": "registration_finished",
    }

    safe = redact_browser_value(raw)
    serialized = json.dumps(safe, ensure_ascii=False)

    for private_value in (
        "customer.alpha@example.com",
        "FirstnameSecret",
        "LastnameSecret",
        "Fullname Secret",
        "8.8.8.8",
        "192.168.10.24",
        "127.0.0.1",
        "2001:db8:85a3::8a2e:370:7334",
        "fe80::1%en0",
        "::ffff:10.0.0.7",
        "backup-email@example.net",
        "172.16.0.9",
        "owner@example.org",
    ):
        assert private_value not in serialized
    assert safe["first_name"] == "<redacted>"
    assert safe["lastName"] == "<redacted>"
    assert safe["profile"]["full_name"] == "<redacted>"
    assert safe["event_name"] == "registration_finished"
    assert "<redacted-email>" in serialized
    assert "<redacted-ip>" in serialized


def test_browser_log_redacts_identity_values_from_all_url_components() -> None:
    raw = {
        "url": (
            "https://customer%40example.com:password@192.168.1.15/"
            "accounts/other%40example.net/2001%3Adb8%3A%3A5"
            "?email=query%40example.org&ip=10.20.30.40&first_name=UrlName"
        ),
        "href": "https://[2001:db8::8]/callback?next=https%3A%2F%2F8.8.4.4%2Fu",
        "message": (
            "open https://example.com/users/embedded%40example.dev/"
            "172.20.1.4?display_name=EmbeddedName"
        ),
    }

    serialized = json.dumps(redact_browser_value(raw), ensure_ascii=False)

    for private_value in (
        "customer%40example.com",
        "customer@example.com",
        "password",
        "192.168.1.15",
        "other%40example.net",
        "other@example.net",
        "2001%3Adb8%3A%3A5",
        "2001:db8::5",
        "query%40example.org",
        "query@example.org",
        "10.20.30.40",
        "UrlName",
        "2001:db8::8",
        "8.8.4.4",
        "embedded%40example.dev",
        "embedded@example.dev",
        "172.20.1.4",
        "EmbeddedName",
    ):
        assert private_value not in serialized
    assert "<redacted>@" in serialized


def test_browser_log_recorder_swallows_cancelled_response_body_reads(tmp_path) -> None:
    page = _Page()
    context = _EventTarget()
    context.pages = [page]
    path = tmp_path / "browser.log.jsonl"
    recorder = BrowserLogRecorder(
        path=path,
        emitter=None,
        capture_bodies=True,
        max_body_chars=20_000,
    )
    recorder.install(context)

    class _CancelledResponse(_Response):
        def text(self) -> str:
            raise asyncio.CancelledError()

    request = _Request(page)
    context.emit("response", _CancelledResponse(request))
    recorder.close()

    serialized = path.read_text()
    assert "CancelledError" in serialized


def test_browser_log_recorder_does_not_read_static_script_bodies(tmp_path) -> None:
    page = _Page()
    context = _EventTarget()
    context.pages = [page]
    path = tmp_path / "browser.log.jsonl"
    recorder = BrowserLogRecorder(
        path=path,
        emitter=None,
        capture_bodies=True,
        max_body_chars=20_000,
    )
    recorder.install(context)

    class _ScriptRequest(_Request):
        resource_type = "script"

    class _UnexpectedBodyResponse(_Response):
        def text(self) -> str:
            raise AssertionError("static script body must not be read")

    request = _ScriptRequest(page)
    context.emit("response", _UnexpectedBodyResponse(request))
    recorder.close()

    serialized = path.read_text()
    assert "static script body must not be read" not in serialized


def test_browser_log_recorder_ignores_queued_response_after_close(tmp_path) -> None:
    page = _Page()
    context = _EventTarget()
    context.pages = [page]
    path = tmp_path / "browser.log.jsonl"
    recorder = BrowserLogRecorder(
        path=path,
        emitter=None,
        capture_bodies=True,
        max_body_chars=20_000,
    )
    recorder.install(context)
    queued_callback = context.handlers["response"][0]

    class _LateResponse(_Response):
        def text(self) -> str:
            raise AssertionError("closed recorder must not read response body")

    recorder.close()
    queued_callback(_LateResponse(_Request(page)))

    serialized = path.read_text()
    assert "closed recorder must not read response body" not in serialized
    assert serialized.count('"event":"browser.log.closed"') == 1


def test_browser_logging_disabled_does_not_install_or_create_log(tmp_path) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(
            artifact_root=str(tmp_path),
            browser_log_enabled=False,
        )
    )
    context = _EventTarget()

    assert runner._install_browser_log(context) is None
    assert not list(tmp_path.rglob("browser.log.jsonl"))


def test_browser_log_body_capture_is_explicit() -> None:
    assert BrowserEmailRegistrationConfig().browser_log_enabled is False
    assert BrowserEmailRegistrationConfig().browser_log_capture_bodies is False


def test_browser_log_settings_default_to_disabled(monkeypatch) -> None:
    for name in (
        "BROWSER_LOG_ENABLED",
        "REFACTOR_APP_BROWSER_LOG_ENABLED",
        "BROWSER_LOG_CAPTURE_BODIES",
        "REFACTOR_APP_BROWSER_LOG_CAPTURE_BODIES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.browser_log_enabled is False
    assert settings.browser_log_capture_bodies is False


def test_browser_log_settings_can_be_enabled_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_BROWSER_LOG_ENABLED", "true")
    monkeypatch.setenv("REFACTOR_APP_BROWSER_LOG_CAPTURE_BODIES", "1")
    monkeypatch.setenv("REFACTOR_APP_BROWSER_LOG_MAX_BODY_CHARS", "4000")

    settings = Settings(_env_file=None)

    assert settings.browser_log_enabled is True
    assert settings.browser_log_capture_bodies is True
    assert settings.browser_log_max_body_chars == 4_000
