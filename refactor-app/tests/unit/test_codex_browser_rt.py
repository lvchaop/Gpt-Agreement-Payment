from __future__ import annotations

from types import SimpleNamespace

import pytest
from curl_cffi import requests as curl_requests

from refactor_app.application.jobs.handlers import _personal_codex_hero_phone_provider
from refactor_app.config.browser_fingerprint import BROWSER_IMPERSONATE
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    HERO_ADD_PHONE_INVALID_STATE,
    HERO_ADD_PHONE_OTP_TIMEOUT,
    RetainedBrowserPhoneOtpProvider,
    _account_deactivated_result,
    _click_first_visible,
    _complete_add_phone_with_provider,
    _exchange_callback,
    _extract_callback_url,
    _fill_otp,
    _has_otp_input,
    _has_password_input,
    _install_callback_capture,
    _is_add_phone_url,
    _is_mfa_challenge_url,
    _is_otp_page,
    _is_password_page,
    _phone_verification_failure,
    _select_existing_account_if_visible,
    _start_passwordless_email_login,
    _submit_email_if_visible,
    _submit_password_if_visible,
    _wait_after_callback_capture,
)


class _CallbackContext:
    def __init__(self) -> None:
        self.routes: list[tuple[str, object]] = []
        self.listeners: dict[str, object] = {}

    def route(self, pattern: str, callback) -> None:
        self.routes.append((pattern, callback))

    def on(self, event: str, callback) -> None:
        self.listeners[event] = callback


class _CallbackPage:
    def __init__(self) -> None:
        self.listeners: dict[str, object] = {}

    def on(self, event: str, callback) -> None:
        self.listeners[event] = callback


def test_callback_capture_is_installed_on_context_and_new_pages() -> None:
    context = _CallbackContext()
    page = _CallbackPage()
    captured: list[str] = []

    _install_callback_capture(context, page, lambda value: not captured.append(value))

    assert context.routes[0][0] == "http://localhost:1455/**"
    assert set(page.listeners) == {"request", "framenavigated"}
    popup = _CallbackPage()
    context.listeners["page"](popup)
    assert set(popup.listeners) == {"request", "framenavigated"}

    popup.listeners["request"](SimpleNamespace(url="http://localhost:1455/auth/callback"))
    assert captured == ["http://localhost:1455/auth/callback"]


def test_callback_capture_waits_before_browser_context_closes() -> None:
    page = SimpleNamespace(wait_for_timeout=lambda timeout_ms: setattr(page, "waited", timeout_ms))

    _wait_after_callback_capture(page)

    assert page.waited == 5_000


def test_account_chooser_is_selected_from_form_when_spa_url_does_not_change() -> None:
    class AccountButton:
        def __init__(self) -> None:
            self.clicked = False

        def inner_text(self) -> str:
            return "Lucas Jones\nTeresaRogers968817@outlook.com"

        def click(self, **kwargs) -> None:
            assert kwargs == {"timeout": 5_000, "no_wait_after": True}
            self.clicked = True

    class AccountChooserPage:
        url = "https://auth.openai.com/oauth/authorize"

        def __init__(self) -> None:
            self.button = AccountButton()
            self.selectors: list[str] = []

        def query_selector_all(self, selector: str):
            self.selectors.append(selector)
            return [self.button] if 'button[name="session_id"]' in selector else []

    page = AccountChooserPage()

    assert (
        _select_existing_account_if_visible(
            page,
            "TeresaRogers968817@outlook.com",
        )
        is True
    )
    assert page.button.clicked is True
    assert page.selectors == ['form[action*="/choose-an-account"] button[name="session_id"]']


def test_extract_callback_url_from_playwright_navigation_exception() -> None:
    callback_url = "http://localhost:1455/auth/callback?code=oauth-code&state=expected-state"
    error_text = f"Page.goto: NS_ERROR_CONNECTION_REFUSED at {callback_url}"

    assert _extract_callback_url(error_text, expected_state="expected-state") == callback_url


def test_extract_callback_url_rejects_exception_with_wrong_state() -> None:
    error_text = (
        "Page.goto: NS_ERROR_CONNECTION_REFUSED at "
        "http://localhost:1455/auth/callback?code=oauth-code&state=wrong-state"
    )

    assert _extract_callback_url(error_text, expected_state="expected-state") == ""


class _NavigationExceptionButton:
    def __init__(self, message: str) -> None:
        self.message = message
        self.fallback_clicked = False

    def is_visible(self) -> bool:
        return True

    def evaluate(self, _script: str) -> None:
        raise RuntimeError(self.message)

    def click(self, **_kwargs) -> None:
        self.fallback_clicked = True


def test_consent_click_recovers_callback_from_navigation_exception() -> None:
    expected_state = "expected-state"
    callback_url = "http://localhost:1455/auth/callback?code=oauth-code&state=expected-state"
    button = _NavigationExceptionButton(
        f"Element.evaluate: NS_ERROR_CONNECTION_REFUSED at {callback_url}"
    )
    page = SimpleNamespace(query_selector=lambda _selector: button)
    captured: list[str] = []

    def capture(value: str) -> bool:
        url = _extract_callback_url(value, expected_state=expected_state)
        if not url:
            return False
        captured.append(url)
        return True

    assert (
        _click_first_visible(
            page,
            ['button:has-text("Authorize")'],
            capture_exception=capture,
        )
        is True
    )
    assert captured == [callback_url]
    assert button.fallback_clicked is False


def test_consent_click_preserves_generic_exception_behavior() -> None:
    class FailingButton(_NavigationExceptionButton):
        def click(self, **_kwargs) -> None:
            raise RuntimeError("fallback click failed")

    button = FailingButton("evaluate failed")
    page = SimpleNamespace(query_selector=lambda _selector: button)

    with pytest.raises(RuntimeError, match="fallback click failed"):
        _click_first_visible(
            page,
            ['button:has-text("Authorize")'],
            capture_exception=lambda _value: False,
        )


def test_oauth_callback_exchange_uses_configured_browser_fingerprint(monkeypatch) -> None:
    created: list[dict] = []

    class FakeSession:
        def __init__(self, **kwargs) -> None:
            created.append(dict(kwargs))
            self.proxies = {}

        def post(self, *_args, **_kwargs):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "id_token": "id-token",
                    "token_type": "Bearer",
                    "scope": "openid",
                },
            )

    monkeypatch.setattr(curl_requests, "Session", FakeSession)

    result = _exchange_callback(
        callback_url="http://localhost:1455/auth/callback?code=oauth-code",
        verifier="verifier",
        client_id="client-id",
        proxy="",
    )

    assert result.ok is True
    assert created == [{"impersonate": BROWSER_IMPERSONATE}]


class _Button:
    def __init__(self) -> None:
        self.clicked = False

    def is_visible(self) -> bool:
        return True

    def evaluate(self, _script: str) -> None:
        self.clicked = True


class _Page:
    def __init__(self, button: _Button | None = None) -> None:
        self.button = button
        self.queries: list[str] = []

    def query_selector(self, selector: str):
        self.queries.append(selector)
        return self.button


def test_select_channel_returns_permanent_account_marker_code_without_clicking() -> None:
    page = _Page(_Button())

    failure = _phone_verification_failure(
        page,
        "https://auth.openai.com/phone-otp/select-channel",
    )

    assert failure == "phone_otp_select_channel"
    assert page.queries == []


def test_add_phone_continues_when_skip_control_is_available() -> None:
    button = _Button()
    page = _Page(button)

    failure = _phone_verification_failure(
        page,
        "https://auth.openai.com/add-phone",
    )

    assert failure == ""
    assert button.clicked is True


def test_add_phone_returns_separate_failure_when_it_cannot_be_skipped() -> None:
    page = _Page()

    failure = _phone_verification_failure(
        page,
        "https://auth.openai.com/add-phone",
    )

    assert failure == "add_phone_blocked"


def test_empty_password_is_not_submitted() -> None:
    page = _Page(_Button())

    assert _submit_password_if_visible(page, "") is False
    assert page.queries == []


def test_password_input_detection() -> None:
    page = _Page(_Button())

    assert _has_password_input(page) is True
    assert page.queries == ['input[type="password"]:visible']


def test_mfa_challenge_is_not_treated_as_mailbox_otp_page() -> None:
    page = _Page(_Button())
    url = "https://auth.openai.com/mfa-challenge/totp-factor"

    assert _is_mfa_challenge_url(url) is True
    assert _is_otp_page(page, url) is False
    assert page.queries == []


def test_password_route_is_not_treated_as_mailbox_otp_page() -> None:
    page = _Page(_Button())
    url = "https://auth.openai.com/log-in/password"

    assert _is_password_page(page, url) is True
    assert _is_otp_page(page, url) is False


def test_generic_retry_control_does_not_make_unrelated_page_an_otp_page() -> None:
    class RetryOnlyPage:
        retry = _Button()

        def query_selector(self, selector: str):
            return self.retry if "Try again" in selector else None

        def query_selector_all(self, _selector: str):
            return []

    page = RetryOnlyPage()

    assert _is_otp_page(page, "https://auth.openai.com/log-in") is False


def test_fill_otp_accepts_visible_text_input_with_authenticator_label() -> None:
    class Input:
        def __init__(self) -> None:
            self.value = ""

        @staticmethod
        def is_visible() -> bool:
            return True

        def click(self, **_kwargs) -> None:
            return None

        def fill(self, value: str) -> None:
            self.value = value

    field = Input()

    class Page:
        url = "https://auth.openai.com/mfa-challenge/totp-factor"

        @staticmethod
        def query_selector(selector: str):
            return field if selector == 'input[type="text"]' else None

        @staticmethod
        def query_selector_all(_selector: str):
            return []

    assert _fill_otp(Page(), "654321") is True
    assert field.value == "654321"


def test_totp_detection_and_fill_use_standard_selectors_across_frames() -> None:
    class Input:
        def __init__(self) -> None:
            self.value = ""

        @staticmethod
        def is_visible() -> bool:
            return True

        @staticmethod
        def click(**_kwargs) -> None:
            return None

        def fill(self, value: str) -> None:
            self.value = value

    field = Input()

    class Frame:
        @staticmethod
        def query_selector_all(selector: str):
            if selector == 'input[autocomplete="one-time-code"]':
                return [field]
            return []

    class Page:
        url = "https://auth.openai.com/mfa-challenge/totp-factor"
        frames = [Frame()]

        @staticmethod
        def query_selector_all(_selector: str):
            return []

    page = Page()

    assert _has_otp_input(page) is True
    assert _fill_otp(page, "654321") is True
    assert field.value == "654321"


def test_totp_fill_uses_react_controlled_input_fallback() -> None:
    class Input:
        value = ""
        fallback_script = ""

        @staticmethod
        def is_visible() -> bool:
            return True

        @staticmethod
        def click(**_kwargs) -> None:
            return None

        @staticmethod
        def fill(_value: str) -> None:
            raise RuntimeError("controlled input rejected native fill")

        def evaluate(self, script: str, value: str) -> None:
            self.fallback_script = script
            self.value = value

    field = Input()

    class Page:
        url = "https://auth.openai.com/mfa-challenge/totp-factor"

        @staticmethod
        def query_selector_all(selector: str):
            if selector == 'input[autocomplete="one-time-code"]':
                return [field]
            return []

    assert _fill_otp(Page(), "654321") is True
    assert field.value == "654321"
    assert "HTMLInputElement.prototype" in field.fallback_script
    assert "new Event('input'" in field.fallback_script


def test_account_deactivated_page_returns_terminal_failure() -> None:
    class DeactivatedPage:
        marker = _Button()

        def query_selector(self, selector: str):
            return self.marker if "deleted or deactivated" in selector else None

    result = _account_deactivated_result(
        DeactivatedPage(),
        "https://auth.openai.com/log-in/password",
    )

    assert result is not None
    assert result.ok is False
    assert result.failure_code == "account_deactivated"
    assert "deleted or deactivated" in result.failure_message
    assert result.final_url == "https://auth.openai.com/log-in/password"


class _EmailInput:
    def __init__(self) -> None:
        self.value = ""

    def click(self, **_kwargs) -> None:
        return None

    def fill(self, value: str) -> None:
        self.value = value


class _EmailPage:
    def __init__(self) -> None:
        self.email_input = _EmailInput()
        self.submit = _Button()

    def query_selector(self, selector: str):
        if selector.startswith('input[type="email"]'):
            return self.email_input
        if selector.startswith("button"):
            return self.submit
        return None


def test_email_submission_preserves_original_case() -> None:
    page = _EmailPage()

    assert _submit_email_if_visible(page, "AshleyJackson500604@hotmail.com") is True
    assert page.email_input.value == "AshleyJackson500604@hotmail.com"


class _PasswordlessPage:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []
        self.navigations: list[str] = []

    def evaluate(self, script: str, path: str):
        self.requests.append((script, path))
        return {"ok": True, "status": 200, "body_head": ""}

    def goto(self, url: str, **_kwargs) -> None:
        self.navigations.append(url)


def test_passwordless_login_sends_empty_post_then_opens_email_verification() -> None:
    page = _PasswordlessPage()

    _start_passwordless_email_login(page)

    assert len(page.requests) == 1
    script, path = page.requests[0]
    assert path == "/api/accounts/passwordless/send-otp"
    assert "JSON.stringify" not in script
    assert '"x-access-flow-invocation-id": crypto.randomUUID()' in script
    assert "oai-device-id" not in script
    assert page.navigations == ["https://auth.openai.com/email-verification"]


class _PhonePage:
    def __init__(self, *, send_continue: str = "/phone-verification") -> None:
        self.url = "https://auth.openai.com/add-phone"
        self.send_continue = send_continue
        self.navigations: list[str] = []
        self.context_waits: list[tuple] = []
        self.phone_value = ""
        self.otp_value = ""
        self.sms_clicked = 0
        self.continue_clicked = 0
        self.invalid_state_visible = False
        self.account_deactivated_visible = False
        self.phone_values: list[str] = []
        self.virtual_phone_error_visible = False

    def wait_for_load_state(self, state: str, **kwargs) -> None:
        self.context_waits.append(("load", state, kwargs["timeout"]))

    def wait_for_selector(self, selector: str, **kwargs) -> None:
        self.context_waits.append(("selector", selector, kwargs["state"], kwargs["timeout"]))

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.context_waits.append(("settle", timeout_ms))

    def query_selector(self, selector: str):
        if any(
            value in selector
            for value in ("deleted or deactivated", "account_deactivated")
        ):
            return _PhoneControl(self, "error") if self.account_deactivated_visible else None
        if "sign-in session is no longer valid" in selector:
            return _PhoneControl(self, "error") if self.invalid_state_visible else None
        if "Please start over to continue" in selector:
            return _PhoneControl(self, "error") if self.invalid_state_visible else None
        if any(
            value in selector
            for value in ("virtual phone number", "non-virtual phone number", "VoIP")
        ):
            return _PhoneControl(self, "error") if self.virtual_phone_error_visible else None
        if self.url.endswith("/add-phone"):
            if "input" in selector and ("tel" in selector or "phone" in selector):
                return _PhoneControl(self, "phone")
            if "Text Message" in selector:
                return _PhoneControl(self, "sms")
            if "button" in selector:
                return _PhoneControl(self, "continue")
        if "phone-verification" in self.url:
            if "input" in selector:
                return _PhoneControl(self, "otp")
            if "button" in selector:
                return _PhoneControl(self, "continue")
        return None

    def query_selector_all(self, _selector: str):
        return []

    def goto(self, url: str, **_kwargs) -> None:
        self.url = url
        self.navigations.append(url)


class _InvalidStatePhonePage(_PhonePage):
    pass


class _VirtualPhoneRejectedOncePage(_PhonePage):
    def __init__(self) -> None:
        super().__init__()
        self.rejections_remaining = 1


class _DeactivatedAfterPhoneSubmitPage(_PhonePage):
    pass


class _PhoneControl:
    def __init__(self, page: _PhonePage, kind: str) -> None:
        self.page = page
        self.kind = kind

    def is_visible(self) -> bool:
        return True

    def click(self, **_kwargs) -> None:
        self._activate()

    def evaluate(self, _script: str) -> None:
        self._activate()

    def fill(self, value: str) -> None:
        if self.kind == "phone":
            self.page.phone_value = value
            self.page.phone_values.append(value)
            self.page.virtual_phone_error_visible = False
        elif self.kind == "otp":
            self.page.otp_value = value

    def _activate(self) -> None:
        if self.kind == "sms":
            self.page.sms_clicked += 1
            return
        if self.kind != "continue":
            return
        self.page.continue_clicked += 1
        if isinstance(self.page, _InvalidStatePhonePage):
            self.page.invalid_state_visible = True
        elif isinstance(self.page, _DeactivatedAfterPhoneSubmitPage):
            self.page.account_deactivated_visible = True
        elif (
            isinstance(self.page, _VirtualPhoneRejectedOncePage)
            and self.page.url.endswith("/add-phone")
            and self.page.rejections_remaining > 0
        ):
            self.page.rejections_remaining -= 1
            self.page.virtual_phone_error_visible = True
        elif self.page.url.endswith("/add-phone"):
            self.page.url = "https://auth.openai.com" + self.page.send_continue
        else:
            self.page.url = "https://auth.openai.com/sign-in-with-chatgpt/codex/consent"


class _PhoneProvider:
    def __init__(self) -> None:
        self.allocated = 0
        self.polled: list[str] = []
        self.verified: list[str] = []
        self.failed: list[tuple[str, str]] = []

    def allocate(self):
        self.allocated += 1
        values = [
            ("activation-1", "+15551234567"),
            ("activation-2", "+15557654321"),
        ]
        lease_id, phone_e164 = values[min(self.allocated - 1, len(values) - 1)]
        return SimpleNamespace(lease_id=lease_id, phone_e164=phone_e164)

    def poll_otp(self, lease_id: str) -> str:
        self.polled.append(lease_id)
        return "654321"

    def mark_verified(self, lease_id: str) -> None:
        self.verified.append(lease_id)

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        self.failed.append((lease_id, reason))


class _PhoneTimeoutProvider(_PhoneProvider):
    def poll_otp(self, lease_id: str) -> str:
        self.polled.append(lease_id)
        raise TimeoutError("SMS OTP timeout")


def test_add_phone_uses_hero_and_continues_codex_authorization() -> None:
    page = _PhonePage()
    provider = _PhoneProvider()

    result = _complete_add_phone_with_provider(page, provider)

    assert result is None
    assert provider.allocated == 1
    assert provider.polled == ["activation-1"]
    assert provider.verified == ["activation-1"]
    assert provider.failed == []
    assert page.context_waits == [
        ("load", "domcontentloaded", 10_000),
        (
            "selector",
            'input[type="tel"], input[name="phone_number"], input[autocomplete="tel"]',
            "visible",
            10_000,
        ),
        ("settle", 3_000),
        ("settle", 500),
        ("settle", 500),
    ]
    assert page.phone_value == "+15551234567"
    assert page.otp_value == "654321"
    assert page.sms_clicked == 1
    assert page.continue_clicked == 2
    assert page.url.endswith("/sign-in-with-chatgpt/codex/consent")


def test_add_phone_replaces_virtual_number_in_same_browser_page() -> None:
    page = _VirtualPhoneRejectedOncePage()
    delegate = _PhoneProvider()
    provider = RetainedBrowserPhoneOtpProvider(delegate)

    result = _complete_add_phone_with_provider(page, provider)

    assert result is None
    assert delegate.allocated == 2
    assert delegate.failed == [("activation-1", "phone_number_rejected_virtual")]
    assert delegate.polled == ["activation-2"]
    assert delegate.verified == ["activation-2"]
    assert page.phone_values == ["+15551234567", "+15557654321"]
    assert page.continue_clicked == 3
    assert [event for event in page.context_waits if event[0] == "load"] == [
        ("load", "domcontentloaded", 10_000)
    ]
    assert page.url.endswith("/sign-in-with-chatgpt/codex/consent")
    assert provider.has_retained_lease is False


def test_add_phone_does_not_handle_select_channel() -> None:
    page = _PhonePage(send_continue="/phone-otp/select-channel")
    provider = _PhoneProvider()

    result = _complete_add_phone_with_provider(page, provider)

    assert result is not None
    assert result.failure_code == "phone_otp_select_channel"
    assert provider.polled == []
    assert provider.verified == []
    assert provider.failed == [("activation-1", "phone_otp_select_channel")]
    assert _is_add_phone_url("https://auth.openai.com/phone-otp/select-channel") is False


def test_add_phone_timeout_releases_number_for_authorization_retry() -> None:
    page = _PhonePage()
    delegate = _PhoneTimeoutProvider()
    provider = RetainedBrowserPhoneOtpProvider(delegate)

    result = _complete_add_phone_with_provider(page, provider)

    assert result is not None
    assert result.failure_code == HERO_ADD_PHONE_OTP_TIMEOUT
    assert delegate.failed == [("activation-1", "phone_otp_timeout")]
    assert provider.has_retained_lease is False


def test_add_phone_surfaces_account_deactivated_before_transition_timeout() -> None:
    page = _DeactivatedAfterPhoneSubmitPage()
    provider = _PhoneProvider()

    result = _complete_add_phone_with_provider(page, provider)

    assert result is not None
    assert result.failure_code == "account_deactivated"
    assert "deleted or deactivated" in result.failure_message
    assert result.final_url == "https://auth.openai.com/add-phone"
    assert provider.allocated == 1
    assert provider.polled == []
    assert provider.verified == []
    assert provider.failed == [("activation-1", "account_deactivated")]


def test_add_phone_invalid_state_reuses_same_hero_number_after_auth_restart() -> None:
    delegate = _PhoneProvider()
    provider = RetainedBrowserPhoneOtpProvider(delegate)

    first_result = _complete_add_phone_with_provider(_InvalidStatePhonePage(), provider)

    assert first_result is not None
    assert first_result.failure_code == HERO_ADD_PHONE_INVALID_STATE
    assert delegate.allocated == 1
    assert delegate.failed == []
    assert provider.has_retained_lease is True

    second_result = _complete_add_phone_with_provider(_PhonePage(), provider)

    assert second_result is None
    assert delegate.allocated == 1
    assert delegate.polled == ["activation-1"]
    assert delegate.verified == ["activation-1"]
    assert delegate.failed == []
    assert provider.has_retained_lease is False


def test_personal_codex_grizzly_provider_uses_dr_and_requested_country_price() -> None:
    provider = _personal_codex_hero_phone_provider(
        session_factory=lambda: None,
        settings=SimpleNamespace(
            grizzly_sms_api_key="grizzly-key",
            grizzly_sms_base_url="https://api.grizzlysms.com/stubs/handler_api.php",
        ),
        input_json={
            "use_hero_sms_for_add_phone": True,
            "hero_sms_country": "16",
            "hero_sms_max_price": "0.75",
        },
        run_id="",
    )

    assert provider is not None
    assert provider.base_url == "https://api.grizzlysms.com/stubs/handler_api.php"
    assert provider.api_key == "grizzly-key"
    assert provider.cfg.service == "dr"
    assert provider.cfg.countries == ["16"]
    assert provider.cfg.maxPrice == "0.75"
