from __future__ import annotations

import pytest

import refactor_app.plugins.openai_auth_browser.email_registration as browser_registration
from refactor_app.plugins.openai_auth_browser.email_registration import (
    BrowserEmailRegistrationConfig,
    BrowserEmailRegistrationError,
    CamoufoxEmailRegistration,
    _camoufox_proxy,
    _cookie_header,
    _has_authenticated_session,
    _session_token,
)


def test_camoufox_proxy_preserves_authenticated_http_proxy() -> None:
    assert _camoufox_proxy("http://user:password@proxy.example:8080") == {
        "server": "http://proxy.example:8080",
        "username": "user",
        "password": "password",
    }


def test_camoufox_proxy_rejects_authenticated_socks() -> None:
    with pytest.raises(BrowserEmailRegistrationError, match="authenticated SOCKS"):
        _camoufox_proxy("socks5://user:password@proxy.example:1080")


def test_browser_cookie_export_separates_domains_and_reassembles_session_chunks() -> None:
    cookies = [
        {
            "name": "__Secure-next-auth.session-token.1",
            "value": "second",
            "domain": ".chatgpt.com",
        },
        {
            "name": "__Secure-next-auth.session-token.0",
            "value": "first",
            "domain": ".chatgpt.com",
        },
        {"name": "oai-did", "value": "device", "domain": ".chatgpt.com"},
        {"name": "login_session", "value": "auth", "domain": "auth.openai.com"},
    ]

    assert _session_token(cookies) == "firstsecond"
    assert _cookie_header(cookies, "chatgpt.com") == (
        "__Secure-next-auth.session-token.1=second; "
        "__Secure-next-auth.session-token.0=first; oai-did=device"
    )
    assert _cookie_header(cookies, "openai.com") == "login_session=auth"


def test_open_email_registration_retries_signup_when_first_click_has_no_effect(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    calls = {"signup": 0, "email_entry": 0}
    email_field = object()

    def visible(_page, selectors):
        if selectors is browser_registration.SIGNUP_SELECTORS:
            return object()
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return email_field if calls["email_entry"] else None
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            return object()
        return None

    def click_first(_page, selectors, *, timeout_ms):
        del timeout_ms
        if selectors is browser_registration.SIGNUP_SELECTORS:
            calls["signup"] += 1
            return True
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            calls["email_entry"] += 1
            return True
        return False

    def wait_for_page_state(_page, predicate, *, stage, timeout_s):
        del predicate, timeout_s
        return stage not in {"wait-signup-result-1"}

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(browser_registration, "_click_first", click_first)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda _page, _stage: None)
    monkeypatch.setattr(runner, "_remove_google_one_tap", lambda _page: None)
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)

    runner._open_email_registration(page)

    assert calls == {"signup": 2, "email_entry": 1}


def test_anonymous_chatgpt_home_is_not_an_authenticated_session() -> None:
    page = _FakePage(session_payload={})

    assert _has_authenticated_session(page) is False

    page.session_payload = {"accessToken": "session-access-token"}
    assert _has_authenticated_session(page) is True


def test_submit_email_retries_when_react_replaces_the_input(monkeypatch, tmp_path) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    detached = _FakeInput(fill_error=RuntimeError("Element is not attached to the DOM"))
    attached = _FakeInput()
    fields = iter((detached, detached, attached, attached))

    monkeypatch.setattr(browser_registration, "_visible", lambda _page, _selectors: next(fields))
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_email(page, "MixedCase@outlook.com")

    assert attached.filled == "MixedCase@outlook.com"


def test_complete_about_you_supports_legacy_name_and_age_form(
    monkeypatch,
    tmp_path,
) -> None:
    events: list[tuple[str, dict, str]] = []
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path)),
        event_callback=lambda stage, data, level: events.append((stage, data, level)),
    )
    page = _FakePage(inputs=[_FakeInput(), _FakeInput()])
    metadata = [
        {
            "index": 0,
            "type": "text",
            "name": "name",
            "placeholder": "Full name",
            "ariaLabel": "",
            "label": "",
            "visible": True,
        },
        {
            "index": 1,
            "type": "number",
            "name": "age",
            "placeholder": "Age",
            "ariaLabel": "",
            "label": "",
            "visible": True,
        },
    ]

    monkeypatch.setattr(browser_registration, "_has_authenticated_session", lambda _page: False)
    monkeypatch.setattr(browser_registration, "_visible_input_metadata", lambda _page: metadata)
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._complete_about_you(page, first_name="Jane", last_name="Doe")

    assert page.keyboard.typed[0] == "Jane Doe"
    assert 26 <= int(page.keyboard.typed[1]) <= 40
    assert ("browser.about_you.submitted", {"legacy_age": True}, "INFO") in events


class _FakeInput:
    def __init__(self, *, fill_error: Exception | None = None) -> None:
        self.fill_error = fill_error
        self.filled = ""

    def click(self, **_kwargs) -> None:
        return None

    def focus(self) -> None:
        return None

    def fill(self, value: str) -> None:
        if self.fill_error is not None:
            raise self.fill_error
        self.filled = value


class _FakeKeyboard:
    def __init__(self) -> None:
        self.typed: list[str] = []

    def type(self, value: str, **_kwargs) -> None:
        self.typed.append(value)

    def press(self, _key: str) -> None:
        return None


class _FakePage:
    def __init__(
        self,
        *,
        session_payload: dict | None = None,
        inputs: list[_FakeInput] | None = None,
    ) -> None:
        self.url = "https://chatgpt.com/"
        self.session_payload = session_payload or {}
        self.inputs = inputs or []
        self.keyboard = _FakeKeyboard()

    def goto(self, url: str, **_kwargs) -> None:
        self.url = url

    def evaluate(self, _script: str):
        return self.session_payload

    def query_selector_all(self, selector: str):
        return self.inputs if selector == "input" else []
