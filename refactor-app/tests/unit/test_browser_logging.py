from __future__ import annotations

import json
from types import SimpleNamespace

from refactor_app.config.settings import Settings
from refactor_app.plugins.openai_auth_browser.browser_logging import BrowserLogRecorder
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


def test_browser_log_settings_can_be_enabled_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("REFACTOR_APP_BROWSER_LOG_ENABLED", "true")
    monkeypatch.setenv("REFACTOR_APP_BROWSER_LOG_CAPTURE_BODIES", "1")
    monkeypatch.setenv("REFACTOR_APP_BROWSER_LOG_MAX_BODY_CHARS", "4000")

    settings = Settings(_env_file=None)

    assert settings.browser_log_enabled is True
    assert settings.browser_log_capture_bodies is True
    assert settings.browser_log_max_body_chars == 4_000
