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
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthResult


def test_camoufox_proxy_preserves_authenticated_http_proxy() -> None:
    assert _camoufox_proxy("http://user:password@proxy.example:8080") == {
        "server": "http://proxy.example:8080",
        "username": "user",
        "password": "password",
    }


def test_camoufox_proxy_rejects_authenticated_socks() -> None:
    with pytest.raises(BrowserEmailRegistrationError, match="authenticated SOCKS"):
        _camoufox_proxy("socks5://user:password@proxy.example:1080")


def test_totp_challenge_waits_for_input_before_fetching_and_filling_code(monkeypatch) -> None:
    events: list[str] = []

    class Input:
        value = ""

        @staticmethod
        def is_visible() -> bool:
            return True

        @staticmethod
        def click(**_kwargs) -> None:
            return None

        def fill(self, value: str) -> None:
            events.append("fill")
            self.value = value

    class Button:
        @staticmethod
        def is_visible() -> bool:
            return True

        def evaluate(self, _script: str) -> bool:
            events.append("submit")
            page.url = "https://chatgpt.com/"
            return True

    class Page:
        url = "https://auth.openai.com/mfa-challenge/totp-factor"
        input_poll_count = 0
        field = Input()
        button = Button()

        def query_selector(self, selector: str):
            if selector == 'input[autocomplete="one-time-code"]':
                self.input_poll_count += 1
                events.append(f"poll:{self.input_poll_count}")
                return self.field if self.input_poll_count >= 2 else None
            if selector in browser_registration.CONTINUE_SELECTORS:
                return self.button
            return None

        def query_selector_all(self, selector: str):
            return [self.button] if selector in browser_registration.CONTINUE_SELECTORS else []

    page = Page()
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(capture_artifacts=False)
    )
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)

    runner._complete_totp_challenge(
        page,
        totp_code_provider=lambda: events.append("fetch") or "654321",
    )

    assert page.field.value == "654321"
    assert events[:3] == ["poll:1", "poll:2", "fetch"]
    assert events.index("fill") > events.index("fetch")
    assert events[-1] == "submit"


def test_managed_camoufox_cleans_up_when_browser_launch_fails() -> None:
    calls: list[str] = []

    class Manager:
        def __init__(self, **_launch_options) -> None:
            calls.append("init")

        def __enter__(self):
            calls.append("enter")
            raise RuntimeError("proxy launch failed")

        def __exit__(self, *_args) -> None:
            calls.append("exit")

    with pytest.raises(RuntimeError, match="proxy launch failed"):
        with browser_registration._managed_camoufox(Manager, headless=True):
            pytest.fail("launch failure must not enter the browser body")

    assert calls == ["init", "enter", "exit"]


def test_managed_camoufox_cleanup_does_not_replace_original_error() -> None:
    class Manager:
        def __init__(self, **_launch_options) -> None:
            pass

        def __enter__(self):
            return object()

        def __exit__(self, *_args) -> None:
            raise RuntimeError("cleanup failed")

    with pytest.raises(ValueError, match="workflow failed"):
        with browser_registration._managed_camoufox(Manager):
            raise ValueError("workflow failed")


def test_managed_camoufox_skips_close_after_driver_disconnect() -> None:
    calls: list[str] = []

    class Future:
        @staticmethod
        def done() -> bool:
            return True

    class Manager:
        def __init__(self, **_launch_options) -> None:
            self.browser = type(
                "Browser",
                (),
                {
                    "_impl_obj": type(
                        "Impl",
                        (),
                        {
                            "_connection": type(
                                "Connection",
                                (),
                                {
                                    "_transport": type(
                                        "Transport",
                                        (),
                                        {"on_error_future": Future()},
                                    )()
                                },
                            )()
                        },
                    )()
                },
            )()

        def __enter__(self):
            calls.append("enter")
            return self.browser

        def __exit__(self, *_args) -> None:
            calls.append("exit")

    with browser_registration._managed_camoufox(Manager, headless=True):
        calls.append("body")

    assert calls == ["enter", "body"]


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


def test_open_email_registration_retries_login_when_first_click_has_no_effect(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    calls = {"login": 0, "email_entry": 0}
    email_field = object()

    def visible(_page, selectors):
        if selectors is browser_registration.LOGIN_SELECTORS:
            return object()
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return email_field if calls["email_entry"] else None
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            return object() if calls["login"] >= 2 else None
        return None

    def click_registration_control(_page, selectors, **_kwargs):
        if selectors is browser_registration.LOGIN_SELECTORS:
            calls["login"] += 1
            return True
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            calls["email_entry"] += 1
            return True
        return False

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(
        browser_registration,
        "_click_registration_control",
        click_registration_control,
    )
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda _page, _stage: None)
    monkeypatch.setattr(runner, "_remove_google_one_tap", lambda _page: None)

    runner._open_email_registration(page)

    assert calls == {"login": 2, "email_entry": 1}


def test_open_email_registration_requeries_login_during_home_dom_replacement(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    state = {"click_attempts": 0, "email_ready": False}
    email_field = object()

    def visible(_page, selectors):
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return email_field if state["email_ready"] else None
        if selectors is browser_registration.LOGIN_SELECTORS:
            return object() if not state["email_ready"] else None
        return None

    def click_registration_control(_page, selectors, **_kwargs):
        if selectors is not browser_registration.LOGIN_SELECTORS:
            return False
        state["click_attempts"] += 1
        if state["click_attempts"] == 1:
            return False
        state["email_ready"] = True
        return True

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(
        browser_registration,
        "_click_registration_control",
        click_registration_control,
    )
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda *_args: None)
    monkeypatch.setattr(runner, "_remove_google_one_tap", lambda *_args: None)

    runner._open_email_registration(page)

    assert state == {"click_attempts": 2, "email_ready": True}


def test_open_email_registration_uses_signup_entry_for_registration(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    state = {"signup_opened": False, "email_ready": False}
    clicked: list[tuple[str, ...]] = []

    def visible(_page, selectors):
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return object() if state["email_ready"] else None
        if selectors is browser_registration.SIGNUP_SELECTORS:
            return object() if not state["signup_opened"] else None
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            return object() if state["signup_opened"] and not state["email_ready"] else None
        return None

    def click_registration_control(_page, selectors, **_kwargs):
        clicked.append(selectors)
        if selectors is browser_registration.SIGNUP_SELECTORS:
            state["signup_opened"] = True
            return True
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            state["email_ready"] = True
            return True
        return False

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(
        browser_registration,
        "_click_registration_control",
        click_registration_control,
    )
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda *_args: None)
    monkeypatch.setattr(runner, "_remove_google_one_tap", lambda *_args: None)

    runner._open_email_registration(page, entry_mode="signup")

    assert state == {"signup_opened": True, "email_ready": True}
    assert clicked == [
        browser_registration.SIGNUP_SELECTORS,
        browser_registration.EMAIL_ENTRY_SELECTORS,
    ]
    assert browser_registration.LOGIN_SELECTORS not in clicked


def test_open_email_registration_accepts_delayed_compatibility_email_form(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    state = {"compat_ready": False, "login_clicks": 0}
    email_field = object()

    def visible(_page, selectors):
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return email_field if state["compat_ready"] else None
        return None

    def wait_for_page_state(_page, predicate, **_kwargs):
        state["compat_ready"] = True
        return bool(predicate())

    def click_first(*_args, **_kwargs):
        state["login_clicks"] += 1
        return True

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(browser_registration, "_click_first", click_first)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda _page, _stage: None)
    monkeypatch.setattr(runner, "_accept_cookie_consent", lambda _page: None)
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)

    runner._open_email_registration(page)

    assert state == {"compat_ready": True, "login_clicks": 0}


def test_open_email_registration_starts_at_auth_login(monkeypatch, tmp_path) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    email_field = object()
    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            email_field if selectors is browser_registration.EMAIL_INPUT_SELECTORS else None
        ),
    )
    monkeypatch.setattr(runner, "_accept_cookie_consent", lambda _page: None)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda _page, _stage: None)
    monkeypatch.setattr(runner, "_raise_for_external_idp", lambda _page, _stage: None)

    runner._open_email_registration(page, entry_mode="signup")

    assert page.url == "https://chatgpt.com/auth/login"


def test_restart_email_otp_flow_reenters_email_and_password_branch(
    monkeypatch,
    tmp_path,
) -> None:
    calls: list[str] = []
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    monkeypatch.setattr(
        runner,
        "_open_email_registration",
        lambda _page, *, entry_mode: calls.append(f"open:{entry_mode}"),
    )
    monkeypatch.setattr(
        runner,
        "_submit_email",
        lambda _page, email: calls.append(f"email:{email}"),
    )
    monkeypatch.setattr(
        runner,
        "_submit_password_if_requested",
        lambda *_args, **_kwargs: calls.append("password") or False,
    )
    monkeypatch.setattr(
        runner,
        "_submit_preferred_password_flow",
        lambda *_args, **_kwargs: calls.append("preferred-password") or True,
    )

    runner._restart_email_otp_flow(
        page,
        object(),
        email="user@example.com",
        password="generated-password",
        prefer_password_flow=True,
    )

    assert calls == [
        "open:signup",
        "email:user@example.com",
        "password",
        "preferred-password",
    ]


def test_email_otp_wait_failure_restarts_registration_flow(monkeypatch, tmp_path) -> None:
    restarts: list[dict[str, object]] = []
    waits = {"count": 0}
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()

    class Mailbox:
        def wait_for_otp(self, *_args, **_kwargs) -> str:
            waits["count"] += 1
            if waits["count"] == 1:
                raise TimeoutError("mailbox timeout")
            return "123456"

    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        runner,
        "_restart_email_otp_flow",
        lambda *_args, **kwargs: restarts.append(kwargs),
    )
    monkeypatch.setattr(browser_registration, "_otp_inputs", lambda _page: [object()])
    monkeypatch.setattr(browser_registration, "_type_email_otp", lambda *_args: True)
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: None)

    runner._complete_email_otp(
        page,
        Mailbox(),
        email="user@example.com",
        issued_after=0,
        password="generated-password",
    )

    assert waits["count"] == 2
    assert restarts == [
        {
            "email": "user@example.com",
            "password": "generated-password",
            "prefer_password_flow": False,
        }
    ]


def test_open_email_registration_uses_commit_before_polling_controls(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    email_field = object()

    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: email_field
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS
        else None,
    )
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda *_args: None)

    runner._open_email_registration(page)

    assert page.goto_options["wait_until"] == "commit"


def test_open_email_registration_waits_for_delayed_email_form_after_entry_click(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    state = {"login_opened": False, "email_entry_clicks": 0, "email_ready": False}

    def visible(_page, selectors):
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return object() if state["email_ready"] else None
        if selectors is browser_registration.LOGIN_SELECTORS:
            return object() if not state["login_opened"] else None
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            return object() if state["login_opened"] else None
        return None

    def click_registration_control(_page, selectors, **_kwargs):
        if selectors is browser_registration.LOGIN_SELECTORS:
            state["login_opened"] = True
            return True
        if selectors is browser_registration.EMAIL_ENTRY_SELECTORS:
            state["email_entry_clicks"] += 1
            return True
        return False

    def wait_for_page_state(_page, predicate, *, stage, **_kwargs):
        if stage == "wait-email-form":
            state["email_ready"] = True
        return bool(predicate())

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(
        browser_registration,
        "_click_registration_control",
        click_registration_control,
    )
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)
    monkeypatch.setattr(runner, "_raise_for_challenge", lambda *_args: None)
    monkeypatch.setattr(runner, "_remove_google_one_tap", lambda *_args: None)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)

    runner._open_email_registration(page)

    assert state["email_entry_clicks"] == 1
    assert state["email_ready"] is True


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
    fields = iter((detached, detached, attached, attached, attached))

    monkeypatch.setattr(browser_registration, "_visible", lambda _page, _selectors: next(fields))
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_email(page, "MixedCase@outlook.com")

    assert attached.filled == "MixedCase@outlook.com"


def test_preferred_password_submission_marks_auth_result_configured(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    result = AuthResult()
    result.email = "member@example.com"
    result.password = "registered-password"

    monkeypatch.setattr(runner, "_submit_email", lambda *_args: None)
    monkeypatch.setattr(runner, "_submit_password_if_requested", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(runner, "_complete_email_otp", lambda *_args, **_kwargs: True)

    runner._complete_email_authentication(
        page,
        object(),
        result=result,
        email=result.email,
        passwordless_for_existing_login=False,
        prefer_password_flow=True,
    )

    assert result.password_configured is True


def test_registration_rejects_existing_login_before_totp_challenge(monkeypatch) -> None:
    runner = CamoufoxEmailRegistration(BrowserEmailRegistrationConfig())
    page = _FakePage()
    page.url = "https://auth.openai.com/log-in/password"
    password_field = _FakeInput()

    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: password_field
        if selectors is browser_registration.PASSWORD_INPUT_SELECTORS
        else None,
    )
    monkeypatch.setattr(runner, "_raise_for_terminal_account_error", lambda *_args: None)
    monkeypatch.setattr(runner, "_screenshot", lambda *_args: None)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)

    with pytest.raises(BrowserEmailRegistrationError, match="registration email already exists"):
        runner._submit_password_if_requested(
            page,
            "registered-password",
            email="member@example.com",
            passwordless_for_existing_login=True,
            reject_existing_login=True,
        )


def test_submit_email_uses_scoped_email_continue_button(monkeypatch, tmp_path) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput()
    clicked: list[tuple[tuple[str, ...], int]] = []

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: field)
    monkeypatch.setattr(
        browser_registration,
        "_click_first",
        lambda _page, selectors, **kwargs: clicked.append(
            (selectors, kwargs["timeout_ms"])
        )
        or True,
    )
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_email(page, "member@example.com")

    assert clicked == [(browser_registration.EMAIL_CONTINUE_SELECTORS, 5_000)]
    assert field.filled == "member@example.com"
    assert field.clicks == 1


def test_submit_email_falls_back_to_enter_when_click_has_no_effect(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput()
    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: field)
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)

    def wait_for_page_state(_page, predicate, *, stage, **_kwargs):
        if stage in {"wait-email-submit", "wait-email-retry-submit"}:
            return False
        return bool(predicate())

    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_email(page, "member@example.com")

    assert page.keyboard.pressed == ["Enter"]


def test_submit_email_accepts_navigation_when_button_handle_detaches(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput()

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: field)

    def click_and_navigate(_page, _selectors, **_kwargs):
        page.url = "https://auth.openai.com/email-verification"
        return False

    monkeypatch.setattr(browser_registration, "_click_first", click_and_navigate)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_email(page, "member@example.com")

    assert page.keyboard.pressed == []
    assert page.url == "https://auth.openai.com/email-verification"


def test_submit_email_does_not_refill_while_password_page_is_arriving(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    page.url = "https://chatgpt.com/auth/login"
    state = {"pending": False, "password_ready": False, "submit_clicks": 0}

    class EmailInput(_FakeInput):
        def __init__(self) -> None:
            super().__init__()
            self.fill_calls = 0

        def fill(self, value: str, **_kwargs) -> None:
            self.fill_calls += 1
            if self.fill_calls > 1:
                raise RuntimeError("element is not editable")
            super().fill(value)

        def is_editable(self) -> bool:
            return not state["pending"] and not state["password_ready"]

    email_field = EmailInput()
    password_field = _FakeInput()

    def visible(_page, selectors):
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            # The password page keeps the submitted email visible as a
            # read-only input, matching the real auth page.
            return email_field
        if selectors is browser_registration.PASSWORD_INPUT_SELECTORS:
            return password_field if state["password_ready"] else None
        if selectors is browser_registration.EMAIL_CONTINUE_SELECTORS:
            return email_field if not state["password_ready"] else None
        return None

    def click_and_eventually_navigate(_page, _selectors, **_kwargs):
        state["submit_clicks"] += 1
        if state["submit_clicks"] == 1:
            state["pending"] = True
        else:
            raise AssertionError("pending email submit must not be clicked twice")
        return True

    def wait_for_page_state(_page, predicate, *, stage, **_kwargs):
        if stage == "wait-email-submit":
            return False
        if stage == "wait-email-retry-ready":
            state["password_ready"] = True
            state["pending"] = False
            page.url = "https://auth.openai.com/log-in/password"
        return bool(predicate())

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(browser_registration, "_click_first", click_and_eventually_navigate)
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_email(page, "member@example.com")

    assert email_field.fill_calls == 1
    assert state == {"pending": False, "password_ready": True, "submit_clicks": 1}
    assert page.keyboard.pressed == []


def test_submit_email_waits_for_document_load_before_next_stage_poll(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput()
    load_states: list[str] = []
    wait_calls: list[tuple[str, float, float]] = []

    def wait_for_page_state(
        _page,
        predicate,
        *,
        stage,
        timeout_s,
        transient_challenge_timeout_s,
    ):
        wait_calls.append((stage, timeout_s, transient_challenge_timeout_s))
        return bool(predicate())

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: field)
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    def wait_for_load_state(state: str, *, timeout: int) -> None:
        load_states.append(state)
        assert timeout > 0

    page.wait_for_load_state = wait_for_load_state
    runner._submit_email(page, "member@example.com")

    assert load_states == ["domcontentloaded", "load"]
    assert wait_calls == [("wait-email-submit", 16.0, 60.0)]


def test_page_state_wait_resumes_after_transient_challenge(monkeypatch) -> None:
    events: list[tuple[str, dict[str, object], str]] = []
    clock = {"now": 0.0}
    challenge_states = iter(
        (
            "Cloudflare challenge",
            "Cloudflare challenge",
            "",
            "",
        )
    )
    predicate_calls = {"count": 0}
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(capture_artifacts=False),
        event_callback=lambda stage, data, level: events.append((stage, data, level)),
    )
    page = _FakePage()

    def predicate() -> bool:
        predicate_calls["count"] += 1
        return predicate_calls["count"] >= 2

    monkeypatch.setattr(
        browser_registration.time,
        "monotonic",
        lambda: clock["now"],
    )
    monkeypatch.setattr(
        browser_registration.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    monkeypatch.setattr(
        browser_registration,
        "_challenge_reason",
        lambda _page: next(challenge_states),
    )

    assert runner._wait_for_page_state(
        page,
        predicate,
        stage="wait-email-submit",
        timeout_s=1.0,
        transient_challenge_timeout_s=2.0,
    )
    assert predicate_calls["count"] == 2
    assert [event[0] for event in events] == [
        "browser.challenge.waiting",
        "browser.challenge.cleared",
    ]


def test_page_state_wait_fails_after_transient_challenge_timeout(
    monkeypatch,
    tmp_path,
) -> None:
    events: list[tuple[str, dict[str, object], str]] = []
    screenshots: list[str] = []
    clock = {"now": 0.0}
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path)),
        event_callback=lambda stage, data, level: events.append((stage, data, level)),
    )
    page = _FakePage()

    monkeypatch.setattr(
        browser_registration.time,
        "monotonic",
        lambda: clock["now"],
    )
    monkeypatch.setattr(
        browser_registration.time,
        "sleep",
        lambda seconds: clock.__setitem__("now", clock["now"] + seconds),
    )
    monkeypatch.setattr(
        browser_registration,
        "_challenge_reason",
        lambda _page: "Cloudflare challenge",
    )
    monkeypatch.setattr(runner, "_screenshot", lambda _page, name: screenshots.append(name))

    with pytest.raises(
        BrowserEmailRegistrationError,
        match=(
            r"Cloudflare challenge timed out after 1\.0s "
            r"during wait-email-submit"
        ),
    ):
        runner._wait_for_page_state(
            page,
            lambda: False,
            stage="wait-email-submit",
            timeout_s=1.0,
            transient_challenge_timeout_s=1.0,
        )

    assert screenshots == ["challenge-wait-email-submit.png"]
    assert [event[0] for event in events] == [
        "browser.challenge.waiting",
        "browser.challenge.timeout",
    ]


def test_page_state_wait_keeps_immediate_challenge_failure_by_default(
    monkeypatch,
    tmp_path,
) -> None:
    clock = {"now": 0.0}
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    screenshots: list[str] = []

    monkeypatch.setattr(
        browser_registration.time,
        "monotonic",
        lambda: clock["now"],
    )
    monkeypatch.setattr(
        browser_registration,
        "_challenge_reason",
        lambda _page: "Cloudflare challenge",
    )
    monkeypatch.setattr(runner, "_screenshot", lambda _page, name: screenshots.append(name))

    with pytest.raises(
        BrowserEmailRegistrationError,
        match=r"Cloudflare challenge during wait-email-otp",
    ):
        runner._wait_for_page_state(
            page,
            lambda: False,
            stage="wait-email-otp",
            timeout_s=1.0,
        )

    assert screenshots == ["challenge-wait-email-otp.png"]


def test_page_state_wait_does_not_tolerate_interactive_challenge(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    screenshots: list[str] = []

    monkeypatch.setattr(
        browser_registration,
        "_challenge_reason",
        lambda _page: "Turnstile challenge",
    )
    monkeypatch.setattr(runner, "_screenshot", lambda _page, name: screenshots.append(name))

    with pytest.raises(
        BrowserEmailRegistrationError,
        match=r"Turnstile challenge during wait-email-submit",
    ):
        runner._wait_for_page_state(
            page,
            lambda: False,
            stage="wait-email-submit",
            timeout_s=1.0,
            transient_challenge_timeout_s=60.0,
        )

    assert screenshots == ["challenge-wait-email-submit.png"]


def test_page_state_wait_returns_immediately_on_normal_ready_page(monkeypatch) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(capture_artifacts=False)
    )
    page = _FakePage()
    challenge_checks: list[bool] = []
    monkeypatch.setattr(
        browser_registration,
        "_challenge_reason",
        lambda _page: challenge_checks.append(True) or "",
    )

    assert runner._wait_for_page_state(
        page,
        lambda: True,
        stage="wait-email-submit",
        timeout_s=1.0,
        transient_challenge_timeout_s=2.0,
    )
    assert challenge_checks == []


def test_email_submit_does_not_treat_a_closed_email_modal_as_advance(monkeypatch) -> None:
    page = _FakePage()

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: None)

    assert browser_registration._email_submit_advanced(
        page,
        initial_url="https://chatgpt.com/",
    ) is False


def test_email_submit_does_not_treat_home_redirect_as_advance(monkeypatch) -> None:
    page = _FakePage()
    page.url = "https://chatgpt.com/"

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: None)

    assert browser_registration._email_submit_advanced(
        page,
        initial_url="https://auth.openai.com/log-in",
    ) is False


def test_password_stage_resubmits_chatgpt_compatibility_email_login(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    page.url = "https://chatgpt.com/auth/login?email=member%40example.com"
    email_field = _FakeInput()
    password_field = _FakeInput()
    submitted: list[str] = []
    passwordless_started: list[str] = []

    def visible(_page, selectors):
        if selectors is browser_registration.EMAIL_INPUT_SELECTORS:
            return email_field if "chatgpt.com/auth/login" in page.url else None
        if selectors is browser_registration.PASSWORD_INPUT_SELECTORS:
            return password_field if "/log-in/password" in page.url else None
        return None

    def submit_email(_page, email: str) -> None:
        submitted.append(email)
        page.url = "https://auth.openai.com/log-in/password"

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(runner, "_submit_email", submit_email)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        browser_registration,
        "_codex_start_passwordless_email_login",
        lambda _page: passwordless_started.append("started"),
    )

    runner._submit_password_if_requested(
        page,
        "generated-password",
        email="member@example.com",
        passwordless_for_existing_login=True,
    )

    assert submitted == ["member@example.com"]
    assert passwordless_started == ["started"]
    assert password_field.filled == ""


def test_chatgpt_compatibility_email_selectors_match_visible_page_contract() -> None:
    assert 'button:has-text("Log in")' in browser_registration.LOGIN_SELECTORS
    assert 'input[placeholder="Email address"]' in browser_registration.EMAIL_INPUT_SELECTORS
    assert (
        'form:has(input[placeholder="Email address"]) button:has-text("Continue")'
        in browser_registration.EMAIL_CONTINUE_SELECTORS
    )


def test_browser_click_uses_codex_dom_click_before_native_fallback(monkeypatch) -> None:
    calls: list[str] = []

    class Element:
        def scroll_into_view_if_needed(self, **_kwargs) -> None:
            calls.append("scroll")

        def click(self, **_kwargs) -> None:
            calls.append("click")

        def evaluate(self, _script: str) -> None:
            calls.append("evaluate")

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: Element())

    assert browser_registration._click_first(
        _FakePage(), browser_registration.CONTINUE_SELECTORS, timeout_ms=5_000
    )
    assert calls == ["scroll", "evaluate"]


def test_continue_with_password_prefers_native_navigation_click(monkeypatch) -> None:
    calls: list[str] = []

    class Element:
        def click(self, **_kwargs) -> None:
            calls.append("native")

        def evaluate(self, _script: str) -> None:
            calls.append("dom")

    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: Element())

    assert browser_registration._click_continue_with_password_if_present(_FakePage())
    assert calls == ["native"]


def test_registration_email_input_falls_back_to_dom_click_after_native_timeout() -> None:
    calls: list[str] = []

    class Input:
        def click(self, **_kwargs) -> None:
            calls.append("native")
            raise TimeoutError("input click timed out")

        def evaluate(self, _script: str) -> None:
            calls.append("dom")

    browser_registration._click_registration_input(Input(), timeout_ms=5_000)

    assert calls == ["native", "dom"]


def test_registration_control_uses_exact_dom_click_without_mouse_motion() -> None:
    calls: list[str] = []

    class Button:
        def is_visible(self) -> bool:
            return True

        def inner_text(self) -> str:
            return "Log in"

        def scroll_into_view_if_needed(self, **_kwargs) -> None:
            calls.append("scroll")

        def click(self, **_kwargs) -> None:
            calls.append("native")

        def evaluate(self, _script: str) -> None:
            calls.append("dom")

    class Page:
        def query_selector_all(self, _selector: str) -> list[Button]:
            return [Button()]

    assert browser_registration._click_registration_control(
        Page(),
        browser_registration.LOGIN_SELECTORS,
        required_text="log in",
        timeout_ms=5_000,
    )
    assert calls == ["dom"]


def test_registration_control_prefers_login_testid_when_labels_are_duplicated() -> None:
    calls: list[str] = []

    class Button:
        def __init__(self, name: str) -> None:
            self.name = name

        def is_visible(self) -> bool:
            return True

        def inner_text(self) -> str:
            return "Log in"

        def evaluate(self, _script: str) -> None:
            calls.append(self.name)

    class Page:
        def query_selector_all(self, selector: str) -> list[Button]:
            if selector == 'button[data-testid="login-button"]':
                return [Button("testid")]
            if ':has-text("Log in")' in selector:
                return [Button("top-label"), Button("bottom-label")]
            return []

    assert browser_registration._click_registration_control(
        Page(),
        browser_registration.LOGIN_SELECTORS,
        required_text="log in",
        timeout_ms=5_000,
    )
    assert calls == ["testid"]


def test_run_enables_passwordless_existing_account_branch(monkeypatch, tmp_path) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    captured: dict[str, object] = {}

    def run_authenticated(_mail_provider, **kwargs):
        captured.update(kwargs)
        return "authenticated"

    monkeypatch.setattr(runner, "_run_authenticated", run_authenticated)

    assert runner.run(object()) == "authenticated"
    assert captured["passwordless_for_existing_login"] is True
    assert captured["prefer_password_flow"] is True


def test_run_waits_before_closing_browser_after_success(monkeypatch, tmp_path) -> None:
    sleeps: list[float] = []
    events: list[str] = []
    state: dict[str, bool] = {"exited": False}

    class Context:
        pages: list[object] = []

        def new_page(self):
            page = type("Page", (), {"set_default_timeout": lambda *_args: None})()
            self.pages.append(page)
            return page

    context = Context()

    class Managed:
        def __enter__(self):
            return context

        def __exit__(self, *_args) -> None:
            state["exited"] = True

    class Mailbox:
        def create_mailbox(self) -> str:
            return "user@example.com"

    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(
            artifact_root=str(tmp_path),
            success_close_delay_s=10.0,
        ),
        event_callback=lambda stage, _data, _level: events.append(stage),
    )
    monkeypatch.setattr(
        browser_registration,
        "prepare_domain_mailbox",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        browser_registration,
        "_managed_camoufox",
        lambda *_args, **_kwargs: Managed(),
    )
    monkeypatch.setattr(runner, "_run_in_context", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(browser_registration.time, "sleep", sleeps.append)

    result = runner._run_authenticated(
        Mailbox(),
        password_for_email=lambda _email: "password",
        register_method="email_browser",
        entry_mode="signup",
        passwordless_for_existing_login=False,
        after_session=lambda _context, _page, authenticated: authenticated,
    )

    assert result is not None
    assert sleeps == [10.0]
    assert state["exited"] is True
    assert events[-2:] == [
        "browser.success_close_delay.started",
        "browser.success_close_delay.completed",
    ]


def test_registration_otp_flow_clicks_continue_with_password(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []
    events: list[str] = []
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path)),
        event_callback=lambda stage, _data, _level: events.append(stage),
    )
    page = _FakePage()
    monkeypatch.setattr(
        browser_registration,
        "_click_continue_with_password_if_present",
        lambda _page: True,
    )
    monkeypatch.setattr(
        runner,
        "_submit_password_if_requested",
        lambda *_args, **kwargs: calls.append(kwargs) or True,
    )
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration, "_otp_inputs", lambda _page: [])
    monkeypatch.setattr(browser_registration, "_about_you_visible", lambda _page: True)

    runner._complete_email_otp(
        page,
        object(),
        email="user@example.com",
        issued_after=0,
        password="generated-password",
        prefer_password_flow=True,
    )

    assert calls == [
        {
            "email": "user@example.com",
            "passwordless_for_existing_login": False,
            "require_password": True,
        }
    ]
    assert events[:2] == [
        "browser.password_flow.selected",
        "browser.password_flow.submitted",
    ]


def test_preferred_password_flow_retries_when_otp_page_stays_mounted(monkeypatch, tmp_path) -> None:
    clicks = 0
    waits = 0
    calls: list[dict[str, object]] = []
    events: list[str] = []
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path)),
        event_callback=lambda stage, _data, _level: events.append(stage),
    )

    def click_continue(_page) -> bool:
        nonlocal clicks
        clicks += 1
        return True

    def wait_for_password(*_args, **_kwargs) -> bool:
        nonlocal waits
        waits += 1
        return waits == 2

    monkeypatch.setattr(
        browser_registration,
        "_click_continue_with_password_if_present",
        click_continue,
    )
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_password)
    monkeypatch.setattr(
        runner,
        "_submit_password_if_requested",
        lambda *_args, **kwargs: calls.append(kwargs) or True,
    )

    assert runner._submit_preferred_password_flow(
        _FakePage(), email="user@example.com", password="generated-password"
    )
    assert clicks == 2
    assert waits == 2
    assert calls == [
        {
            "email": "user@example.com",
            "passwordless_for_existing_login": False,
            "require_password": True,
        }
    ]
    assert "browser.password_flow.retrying" in events


def test_email_otp_is_typed_with_browser_keyboard() -> None:
    page = _FakePage()
    field = _FakeInput(maxlength="6")

    assert browser_registration._type_email_otp(page, [field], "123456")
    assert field.filled == ""
    assert page.keyboard.typed == ["123456"]


def test_complete_email_otp_submits_through_page_continue(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput(maxlength="6")
    clicks: list[tuple[str, ...]] = []

    class Mailbox:
        @staticmethod
        def wait_for_otp(*_args, **_kwargs) -> str:
            return "123456"

    def click_first(_page, selectors, **_kwargs):
        clicks.append(selectors)
        page.url = "https://auth.openai.com/about-you"
        return True

    monkeypatch.setattr(browser_registration, "_otp_inputs", lambda _page: [field])
    monkeypatch.setattr(browser_registration, "_visible", lambda *_args: None)
    monkeypatch.setattr(browser_registration, "_click_first", click_first)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)

    runner._complete_email_otp(
        page,
        Mailbox(),
        email="user@example.com",
        issued_after=0,
    )

    assert page.keyboard.typed == ["123456"]
    assert clicks == [browser_registration.CONTINUE_SELECTORS]
    assert page.url == "https://auth.openai.com/about-you"


def test_complete_email_otp_surfaces_chatgpt_account_missing(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput(maxlength="6")
    account_missing = object()

    class Mailbox:
        @staticmethod
        def wait_for_otp(*_args, **_kwargs) -> str:
            return "123456"

    def visible(_page, selectors):
        if selectors is browser_registration.ACCOUNT_MISSING_SELECTORS:
            return account_missing
        return None

    monkeypatch.setattr(browser_registration, "_otp_inputs", lambda _page: [field])
    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)

    with pytest.raises(
        browser_registration.BrowserEmailRegistrationError,
        match="chatgpt_account_missing",
    ):
        runner._complete_email_otp(
            page,
            Mailbox(),
            email="user@example.com",
            issued_after=0,
        )


def test_complete_email_otp_surfaces_account_deactivated_page(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    field = _FakeInput(maxlength="6")

    class Mailbox:
        @staticmethod
        def wait_for_otp(*_args, **_kwargs) -> str:
            return "123456"

    def visible(_page, selectors):
        if selectors is browser_registration.ACCOUNT_DEACTIVATED_SELECTORS:
            return object()
        return None

    monkeypatch.setattr(browser_registration, "_otp_inputs", lambda _page: [field])
    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)

    with pytest.raises(
        browser_registration.BrowserAccountDeactivatedError,
        match="account_deactivated",
    ):
        runner._complete_email_otp(
            page,
            Mailbox(),
            email="user@example.com",
            issued_after=0,
        )


def test_complete_email_otp_surfaces_account_deactivated_before_otp_form(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    page.url = "https://auth.openai.com/log-in/password"
    wait_stages: list[str] = []

    class Mailbox:
        @staticmethod
        def wait_for_otp(*_args, **_kwargs) -> str:
            raise AssertionError("mailbox must not be polled for a deactivated account")

    def visible(_page, selectors):
        if selectors is browser_registration.ACCOUNT_DEACTIVATED_SELECTORS:
            return object()
        return None

    def wait_for_page_state(_page, predicate, *, stage, timeout_s):
        del timeout_s
        wait_stages.append(stage)
        assert predicate() is True
        return True

    monkeypatch.setattr(browser_registration, "_otp_inputs", lambda _page: [])
    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(runner, "_wait_for_page_state", wait_for_page_state)

    with pytest.raises(
        browser_registration.BrowserAccountDeactivatedError,
        match="account_deactivated",
    ):
        runner._complete_email_otp(
            page,
            Mailbox(),
            email="user@example.com",
            issued_after=0,
        )

    assert wait_stages == ["wait-email-otp"]


def test_email_otp_browser_validation_navigates_existing_account_continue_url() -> None:
    page = _FakeOtpValidationPage(
        {
            "status": 200,
            "payload": {"continue_url": "/api/auth/callback/openai?code=test"},
            "body": "",
        }
    )

    payload = browser_registration._validate_email_otp_in_browser(
        page,
        "123456",
        navigation_timeout_ms=60_000,
    )

    assert payload == {"continue_url": "/api/auth/callback/openai?code=test"}
    assert page.navigations == [
        "https://auth.openai.com/api/auth/callback/openai?code=test"
    ]


def test_email_otp_browser_validation_navigates_new_account_about_you() -> None:
    page = _FakeOtpValidationPage(
        {
            "status": 200,
            "payload": {"page": {"type": "about_you"}},
            "body": "",
        }
    )

    browser_registration._validate_email_otp_in_browser(
        page,
        "123456",
        navigation_timeout_ms=60_000,
    )

    assert page.navigations == ["https://auth.openai.com/about-you"]


def test_email_otp_browser_validation_surfaces_account_deactivated() -> None:
    page = _FakeOtpValidationPage(
        {
            "status": 403,
            "payload": {
                "error": {
                    "code": "account_deactivated",
                    "message": "account deactivated",
                }
            },
            "body": "",
        }
    )

    with pytest.raises(
        browser_registration.BrowserAccountDeactivatedError,
        match="account_deactivated",
    ):
        browser_registration._validate_email_otp_in_browser(
            page,
            "123456",
            navigation_timeout_ms=60_000,
        )


def test_existing_account_password_page_reuses_passwordless_browser_login(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    page.url = "https://auth.openai.com/log-in/password"
    password_field = _FakeInput()
    started: list[str] = []

    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            password_field
            if selectors is browser_registration.PASSWORD_INPUT_SELECTORS
            else None
        ),
    )
    monkeypatch.setattr(
        browser_registration,
        "_codex_start_passwordless_email_login",
        lambda _page: started.append("passwordless"),
    )

    runner._submit_password_if_requested(
        page,
        "generated-password",
        passwordless_for_existing_login=True,
    )

    assert started == ["passwordless"]
    assert password_field.filled == ""


def test_new_account_password_page_keeps_existing_registration_branch(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()
    page.url = "https://auth.openai.com/create-account/password"
    password_field = _FakeInput()

    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            password_field
            if selectors is browser_registration.PASSWORD_INPUT_SELECTORS
            else None
        ),
    )
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._submit_password_if_requested(
        page,
        "generated-password",
        passwordless_for_existing_login=True,
    )

    assert password_field.filled == "generated-password"


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
    assert (
        "browser.about_you.submitted",
        {"legacy_age": True, "segmented_birthday": False},
        "INFO",
    ) in events


def test_complete_about_you_supports_react_aria_segmented_birthday(
    monkeypatch,
    tmp_path,
) -> None:
    events: list[tuple[str, dict, str]] = []
    name_field = _FakeInput()
    segments = [_FakeInput(), _FakeInput(), _FakeInput()]
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path)),
        event_callback=lambda stage, data, level: events.append((stage, data, level)),
    )
    page = _FakePage(inputs=[name_field], date_segments=segments)
    name_metadata = [
        {
            "index": 0,
            "type": "text",
            "name": "name",
            "placeholder": "Full name",
            "ariaLabel": "",
            "label": "Full name",
            "visible": True,
        }
    ]
    segment_metadata = [
        {"index": 0, "ariaLabel": "month", "valueMax": "12", "visible": True},
        {"index": 1, "ariaLabel": "day", "valueMax": "31", "visible": True},
        {"index": 2, "ariaLabel": "year", "valueMax": "9999", "visible": True},
    ]

    monkeypatch.setattr(browser_registration, "_has_authenticated_session", lambda _page: False)
    monkeypatch.setattr(
        browser_registration,
        "_visible_input_metadata",
        lambda _page: name_metadata,
    )
    monkeypatch.setattr(
        browser_registration,
        "_visible_date_segment_metadata",
        lambda _page: segment_metadata,
    )
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(browser_registration.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(browser_registration.random, "uniform", lambda _start, _end: 0)

    runner._complete_about_you(page, first_name="Jane", last_name="Doe")

    assert page.keyboard.typed[0] == "Jane Doe"
    assert page.keyboard.typed[1:3] == ["1", "15"]
    assert len(page.keyboard.typed[3]) == 4
    assert (
        "browser.about_you.submitted",
        {"legacy_age": False, "segmented_birthday": True},
        "INFO",
    ) in events


def test_complete_about_you_surfaces_chatgpt_account_missing(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path))
    )
    page = _FakePage()

    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            object()
            if selectors is browser_registration.ACCOUNT_MISSING_SELECTORS
            else None
        ),
    )

    with pytest.raises(
        browser_registration.BrowserChatGPTAccountMissingError,
        match="chatgpt_account_missing",
    ):
        runner._complete_about_you(page, first_name="Jane", last_name="Doe")


def test_wait_for_chatgpt_session_surfaces_chatgpt_account_missing(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(
            artifact_root=str(tmp_path),
            completion_timeout_s=1,
        )
    )
    page = _FakePage()

    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            object()
            if selectors is browser_registration.ACCOUNT_MISSING_SELECTORS
            else None
        ),
    )

    with pytest.raises(
        browser_registration.BrowserChatGPTAccountMissingError,
        match="chatgpt_account_missing",
    ):
        runner._wait_for_chatgpt_session(page)


def test_wait_for_chatgpt_session_retries_user_already_exists_page(
    monkeypatch,
    tmp_path,
) -> None:
    events: list[tuple[str, dict, str]] = []
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(
            artifact_root=str(tmp_path),
            completion_timeout_s=1,
        ),
        event_callback=lambda stage, data, level: events.append((stage, data, level)),
    )
    page = _FakePage()
    page.url = "https://auth.openai.com/about-you"
    state = {"error_visible": True}
    resumed: list[str] = []

    def visible(_page, selectors):
        if selectors is browser_registration.USER_ALREADY_EXISTS_SELECTORS:
            return object() if state["error_visible"] else None
        return None

    def click_first(_page, selectors, **_kwargs):
        if selectors is browser_registration.TRY_AGAIN_SELECTORS:
            state["error_visible"] = False
            page.url = "https://chatgpt.com/"
            return True
        return False

    monkeypatch.setattr(browser_registration, "_visible", visible)
    monkeypatch.setattr(browser_registration, "_click_first", click_first)
    monkeypatch.setattr(
        browser_registration,
        "_chatgpt_session_payload",
        lambda _page: {"accessToken": "access-token"} if not state["error_visible"] else {},
    )

    payload = runner._wait_for_chatgpt_session(
        page,
        on_user_already_exists_retry=lambda: resumed.append("login"),
    )

    assert payload == {"accessToken": "access-token"}
    assert resumed == ["login"]
    assert (
        "browser.user_already_exists.retry.clicked",
        {"url": "https://chatgpt.com/", "attempt": 1},
        "WARN",
    ) in events


def test_wait_for_chatgpt_session_fails_when_user_already_exists_retry_has_no_effect(
    monkeypatch,
    tmp_path,
) -> None:
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(
            artifact_root=str(tmp_path),
            completion_timeout_s=1,
        )
    )
    page = _FakePage()
    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            object()
            if selectors is browser_registration.USER_ALREADY_EXISTS_SELECTORS
            else None
        ),
    )
    monkeypatch.setattr(browser_registration, "_click_first", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(runner, "_wait_for_page_state", lambda *_args, **_kwargs: False)

    with pytest.raises(BrowserEmailRegistrationError, match="Try again click had no effect"):
        runner._wait_for_chatgpt_session(page)


def test_resume_existing_login_after_retry_reuses_passwordless_otp_flow(
    monkeypatch,
    tmp_path,
) -> None:
    events: list[tuple[str, dict, str]] = []
    calls: list[dict] = []
    runner = CamoufoxEmailRegistration(
        BrowserEmailRegistrationConfig(artifact_root=str(tmp_path)),
        event_callback=lambda stage, data, level: events.append((stage, data, level)),
    )
    page = _FakePage()
    page.url = "https://auth.openai.com/log-in"
    result = browser_registration.AuthResult()
    result.email = "member@icloud.com"
    result.password = "generated-password"
    monkeypatch.setattr(
        browser_registration,
        "_visible",
        lambda _page, selectors: (
            object() if selectors is browser_registration.EMAIL_INPUT_SELECTORS else None
        ),
    )

    def complete(_page, _mail_provider, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(runner, "_complete_email_authentication", complete)

    runner._resume_existing_login_after_retry(
        page,
        object(),
        result=result,
    )

    assert calls == [
            {
                "result": result,
                "email": "member@icloud.com",
                "passwordless_for_existing_login": True,
                "totp_code_provider": None,
            }
    ]
    assert events[0][0] == "browser.user_already_exists.login.started"
    assert events[-1][0] == "browser.user_already_exists.login.completed"


class _FakeInput:
    def __init__(
        self,
        *,
        fill_error: Exception | None = None,
        maxlength: str = "",
    ) -> None:
        self.fill_error = fill_error
        self.filled = ""
        self.maxlength = maxlength
        self.clicks = 0

    def click(self, **_kwargs) -> None:
        self.clicks += 1

    def focus(self) -> None:
        return None

    def fill(self, value: str, **_kwargs) -> None:
        if self.fill_error is not None:
            raise self.fill_error
        self.filled = value

    def get_attribute(self, name: str) -> str:
        return self.maxlength if name == "maxlength" else ""

    def input_value(self) -> str:
        return self.filled


class _FakeKeyboard:
    def __init__(self) -> None:
        self.typed: list[str] = []
        self.pressed: list[str] = []

    def type(self, value: str, **_kwargs) -> None:
        self.typed.append(value)

    def press(self, key: str) -> None:
        self.pressed.append(key)


class _FakePage:
    def __init__(
        self,
        *,
        session_payload: dict | None = None,
        inputs: list[_FakeInput] | None = None,
        date_segments: list[_FakeInput] | None = None,
    ) -> None:
        self.url = "https://chatgpt.com/"
        self.session_payload = session_payload or {}
        self.inputs = inputs or []
        self.date_segments = date_segments or []
        self.keyboard = _FakeKeyboard()
        self.goto_options: dict = {}

    def wait_for_load_state(self, _state: str, **_kwargs) -> None:
        return None

    def goto(self, url: str, **_kwargs) -> None:
        self.url = url
        self.goto_options = dict(_kwargs)

    def evaluate(self, _script: str):
        return self.session_payload

    def query_selector_all(self, selector: str):
        if selector == "input":
            return self.inputs
        if selector == '[role="spinbutton"]':
            return self.date_segments
        return []


class _FakeOtpValidationPage:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.navigations: list[str] = []

    def evaluate(self, _script: str, _code: str) -> dict:
        return self.result

    def goto(self, url: str, **_kwargs) -> None:
        self.navigations.append(url)
