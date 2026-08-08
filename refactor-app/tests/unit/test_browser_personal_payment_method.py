from __future__ import annotations

import json

import pytest

from refactor_app.plugins.openai_auth_browser import personal_payment_method as payment_module
from refactor_app.plugins.openai_auth_browser.personal_payment_method import (
    PAYMENT_METHOD_CHECKOUT_SCRIPT,
    PAYMENT_METHOD_FORM_SCRIPT,
    BrowserBillingDetails,
    BrowserPaymentCard,
    BrowserPaymentMethodConfirmError,
    BrowserPersonalPaymentMethodError,
    bind_personal_payment_card,
    bind_personal_payment_cards,
)


@pytest.fixture(autouse=True)
def _stub_shared_checkout_creator(monkeypatch):
    def create(page, *, expected_account_id):
        page.goto("https://chatgpt.com/", wait_until="load", timeout=120_000)
        return page.evaluate(
            PAYMENT_METHOD_CHECKOUT_SCRIPT,
            {"expectedPersonalAccountId": expected_account_id},
        )

    monkeypatch.setattr(payment_module, "create_plus_checkout_with_script", create)


def _card() -> BrowserPaymentCard:
    return BrowserPaymentCard(
        number="4242424242424242",
        cvc="123",
        exp_month=12,
        exp_year=2030,
    )


def _billing() -> BrowserBillingDetails:
    return BrowserBillingDetails(
        name="Ada Lovelace",
        email="ada@example.test",
        phone="+12025550123",
        line1="123 Test Street",
        line2="Suite 4",
        city="New York",
        state="NY",
        postal_code="10001",
        country="US",
    )


def test_payment_method_browser_scripts_match_confirmed_backend_contract() -> None:
    assert "/backend-api/payments/checkout" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert 'entry_point: "all_plans_pricing_modal"' in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert 'plan_name: "chatgptplusplan"' in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert 'country: "US"' in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert 'currency: "USD"' in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "promo_campaign" not in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert 'checkout_ui_mode: "hosted"' in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert 'const ResultKey = "__plusPhOaicsCreateResult"' in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "window[ResultKey] = result" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "/api/auth/session" in PAYMENT_METHOD_FORM_SCRIPT
    assert "id=\"__card_submit__\"" in PAYMENT_METHOD_FORM_SCRIPT
    assert "submitButton.onclick = async () =>" in PAYMENT_METHOD_FORM_SCRIPT
    assert "stripe.confirmCardSetup(" in PAYMENT_METHOD_FORM_SCRIPT
    assert "/backend-api/payments/stripe_client_bootstrap" not in PAYMENT_METHOD_FORM_SCRIPT
    assert "/backend-api/payments/payment_method'" in PAYMENT_METHOD_FORM_SCRIPT
    assert "JSON.stringify({ account_id: accountId })" in PAYMENT_METHOD_FORM_SCRIPT
    assert "'x-openai-target-path': '/backend-api/payments/payment_method'" in (
        PAYMENT_METHOD_FORM_SCRIPT
    )
    assert "'x-openai-target-route': '/backend-api/payments/payment_method'" in (
        PAYMENT_METHOD_FORM_SCRIPT
    )
    assert "/backend-api/payments/payment_methods?account_id=" in PAYMENT_METHOD_FORM_SCRIPT
    assert "/backend-api/payments/payment_method/default" in PAYMENT_METHOD_FORM_SCRIPT
    assert "'x-openai-target-path': '/backend-api/payments/payment_methods'" in (
        PAYMENT_METHOD_FORM_SCRIPT
    )
    assert "'x-openai-target-route': '/backend-api/payments/payment_method/default'" in (
        PAYMENT_METHOD_FORM_SCRIPT
    )
    assert "set_as_default_payment_method: true" in PAYMENT_METHOD_FORM_SCRIPT
    assert "window.__personalPaymentMethodBind = result" in PAYMENT_METHOD_FORM_SCRIPT


def test_payment_http_trace_target_only_matches_requested_post_endpoints() -> None:
    assert payment_module._payment_http_trace_target(
        method="POST",
        url="https://api.stripe.com/v1/setup_intents/seti_test_123/confirm",
    ) == {
        "method": "POST",
        "operation": "stripe_confirm",
        "endpoint": "https://api.stripe.com/v1/setup_intents/{SETUP_INTENT_ID}/confirm",
        "setup_intent_id": "seti_test_123",
    }
    assert payment_module._payment_http_trace_target(
        method="POST",
        url="https://chatgpt.com/backend-api/payments/payment_method/default",
    ) == {
        "method": "POST",
        "operation": "payment_method_default",
        "endpoint": "/backend-api/payments/payment_method/default",
    }
    assert (
        payment_module._payment_http_trace_target(
            method="GET",
            url="https://chatgpt.com/backend-api/payments/payment_method/default",
        )
        is None
    )


def test_payment_http_trace_records_requests_responses_and_summary() -> None:
    page = _TracePage()
    events: list[tuple[str, dict, str]] = []
    remove = payment_module._install_payment_http_trace(
        page,
        emitter=lambda event_type, data, level: events.append((event_type, data, level)),
    )

    page.emit_response(
        "POST",
        "https://api.stripe.com/v1/setup_intents/seti_test_123/confirm",
        402,
    )
    page.emit_response(
        "POST",
        "https://chatgpt.com/backend-api/payments/payment_method/default",
        200,
    )
    remove()

    assert [event[0] for event in events] == [
        "payment_method.http.request",
        "payment_method.http.response",
        "payment_method.http.request",
        "payment_method.http.response",
        "payment_method.http.summary",
    ]
    assert events[0][1]["request_body"] == "payment_method_data[type]=card"
    assert events[1][1]["status"] == 402
    assert events[1][1]["response_body"] == '{"error":{"code":"card_declined"}}'
    assert events[1][2] == "WARN"
    assert events[-1][1] == {
        "stripe_confirm_request_count": 1,
        "stripe_confirm_response_statuses": [402],
        "payment_method_default_request_count": 1,
        "payment_method_default_response_statuses": [200],
    }


def test_bind_personal_payment_card_fills_stripe_frame_and_verifies_result() -> None:
    page = _Page()

    result = bind_personal_payment_card(
        page,
        expected_personal_account_id="personal-account-1",
        card=_card(),
        billing=_billing(),
    )

    assert result.personal_account_id == "personal-account-1"
    assert result.payment_method_id == "pm_test_1"
    assert result.last4 == "4242"
    assert page.goto_urls == [
        "https://chatgpt.com/",
        "https://chatgpt.com/checkout/openai_llc/cs_test_checkout_1",
    ]
    assert page.frame.values == {
        'input[name="cardnumber"]': "4242424242424242",
        'input[name="exp-date"]': "1230",
        'input[name="cvc"]': "123",
    }
    assert page.values == {
        "#__card_name__": "Ada Lovelace",
        "#__billing_email__": "ada@example.test",
        "#__billing_phone__": "+12025550123",
        "#__billing_line1__": "123 Test Street",
        "#__billing_line2__": "Suite 4",
        "#__billing_city__": "New York",
        "#__billing_state__": "NY",
        "#__billing_postal_code__": "10001",
        "#__billing_country__": "US",
    }
    assert page.clicked == ["#__card_submit__"]
    assert page.evaluate_args == [{"expectedPersonalAccountId": "personal-account-1"}]
    form_evaluations = [
        script
        for script in page.evaluate_scripts
        if "document.getElementById('__personal_card_stripe_modal__')" in script
    ]
    assert len(form_evaluations) == 1
    assert form_evaluations[0].startswith("mw:")


def test_bind_personal_payment_card_surfaces_stripe_error_without_card_data() -> None:
    page = _Page(
        confirmation={
            "ok": False,
            "button_disabled": False,
            "button_text": "确认绑定",
            "message": "The card was declined.",
        }
    )

    with pytest.raises(
        BrowserPaymentMethodConfirmError,
        match="payment_method_confirm_failed",
    ) as error:
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert "4242424242424242" not in str(error.value)
    assert "123" not in str(error.value)
    assert error.value.error_message == "The card was declined."
    assert error.value.diagnostics == {}


def test_bind_personal_payment_card_surfaces_form_validation_failure() -> None:
    page = _Page(
        confirmation={
            "ok": False,
            "button_disabled": False,
            "button_text": "确认绑定",
            "message": "请填写完整账单地址：postal_code",
        }
    )

    with pytest.raises(BrowserPersonalPaymentMethodError) as error:
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert isinstance(error.value, BrowserPaymentMethodConfirmError)


def test_bind_personal_payment_card_accepts_opaque_checkout_session_id() -> None:
    page = _Page(
        checkout={
            "personal_account_id": "personal-account-1",
            "checkout_session_id": "oaics_test_checkout_1",
            "processor_entity": "openai_llc",
            "checkout_url": "https://chatgpt.com/checkout/openai_llc/oaics_test_checkout_1",
        }
    )

    result = bind_personal_payment_card(
        page,
        expected_personal_account_id="personal-account-1",
        card=_card(),
        billing=_billing(),
    )

    assert result.payment_method_id == "pm_test_1"
    assert page.goto_urls[-1].endswith("/oaics_test_checkout_1")


def test_bind_personal_payment_card_delegates_stripe_loading_to_form_script() -> None:
    page = _Page()

    result = bind_personal_payment_card(
        page,
        expected_personal_account_id="personal-account-1",
        card=_card(),
        billing=_billing(),
    )

    assert result.payment_method_id == "pm_test_1"
    assert not any("typeof window.Stripe" in script for script in page.evaluate_scripts)
    assert any(
        "document.getElementById('__personal_card_stripe_modal__')" in script
        for script in page.evaluate_scripts
    )


class _Locator:
    def __init__(self, frame: _Frame, selector: str) -> None:
        self.frame = frame
        self.selector = selector

    @property
    def first(self) -> _Locator:
        return self

    def count(self) -> int:
        return int(self.selector == 'input[name="cardnumber"]')

    def wait_for(self, **_kwargs) -> None:
        return None

    def fill(self, value: str) -> None:
        self.frame.values[self.selector] = value


class _PageLocator:
    def __init__(self, page: _Page, selector: str) -> None:
        self.page = page
        self.selector = selector

    def wait_for(self, **_kwargs) -> None:
        return None

    def fill(self, value: str) -> None:
        self.page.values[self.selector] = value

    def click(self, **_kwargs) -> None:
        self.page.clicked.append(self.selector)
        if self.page.confirmations:
            self.page.confirmation = self.page.confirmations.pop(0)


class _Frame:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def locator(self, selector: str) -> _Locator:
        return _Locator(self, selector)


class _TraceRequest:
    def __init__(self, method: str, url: str, body: str = "") -> None:
        self.method = method
        self.url = url
        self.post_data = body


class _TraceResponse:
    def __init__(self, request: _TraceRequest, status: int, body: str) -> None:
        self.request = request
        self.url = request.url
        self.status = status
        self.body = body

    def text(self) -> str:
        return self.body


class _TracePage:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {"request": [], "response": []}

    def on(self, event: str, callback) -> None:
        self.listeners[event].append(callback)

    def remove_listener(self, event: str, callback) -> None:
        self.listeners[event].remove(callback)

    def emit_response(self, method: str, url: str, status: int) -> None:
        request = _TraceRequest(method, url, "payment_method_data[type]=card")
        for callback in list(self.listeners["request"]):
            callback(request)
        response = _TraceResponse(request, status, '{"error":{"code":"card_declined"}}')
        for callback in list(self.listeners["response"]):
            callback(response)


_NO_ARGUMENT = object()


class _Page:
    def __init__(
        self,
        *,
        checkout: dict | None = None,
        confirmation: dict | None = None,
        confirmations: list[dict] | None = None,
    ) -> None:
        self.frame = _Frame()
        self.frames = [self.frame]
        self.values: dict[str, str] = {}
        self.clicked: list[str] = []
        self.goto_urls: list[str] = []
        self.evaluate_scripts: list[str] = []
        self.evaluate_args: list[dict] = []
        self.main_world_tasks: dict[str, dict] = {}
        self.checkout = checkout or {
            "personal_account_id": "personal-account-1",
            "checkout_session_id": "cs_test_checkout_1",
            "processor_entity": "openai_llc",
            "publishable_key": "pk_test_checkout_1",
            "checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_test_checkout_1",
        }
        self.confirmation = confirmation or {
            "ok": True,
            "personal_account_id": "personal-account-1",
            "payment_method_id": "pm_test_1",
            "last4": "4242",
            "brand": "visa",
        }
        self.confirmations = list(confirmations or [])

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_urls.append(url)

    def locator(self, selector: str) -> _PageLocator:
        return _PageLocator(self, selector)

    def evaluate(self, script: str, argument: object = _NO_ARGUMENT):
        self.evaluate_scripts.append(script)
        if argument is not _NO_ARGUMENT:
            assert isinstance(argument, dict)
            self.evaluate_args.append(argument)
        if script == PAYMENT_METHOD_CHECKOUT_SCRIPT:
            return self.checkout
        if (
            script.startswith("mw:")
            and "document.getElementById('__personal_card_stripe_modal__')" in script
        ):
            return None
        if script.startswith("mw:") and "button.disabled === false" in script:
            return True
        if script.startswith("mw:") and "window.__personalPaymentMethodBind" in script:
            return json.dumps(self.confirmation)
        if script.startswith("mw:") and "button.click()" in script:
            self.clicked.append("#__card_submit__")
            if self.confirmations:
                self.confirmation = self.confirmations.pop(0)
            return True
        raise AssertionError(f"unexpected evaluate script: {script[:120]}")


def test_payment_method_batch_reuses_checkout_form_and_setup_intent_for_three_cards() -> None:
    page = _Page(
        confirmations=[
            {
                "ok": False,
                "button_disabled": False,
                "message": "card declined 1",
            },
            {
                "ok": False,
                "button_disabled": False,
                "message": "card declined 2",
            },
            {
                "ok": True,
                "payment_method_id": "pm_test_3",
                "last4": "0003",
                "brand": "visa",
            },
        ]
    )
    failures: list[int] = []
    successes: list[int] = []
    cards = [
        (
            BrowserPaymentCard(
                number=f"424242424242{index:04d}",
                cvc="123",
                exp_month=12,
                exp_year=2030,
            ),
            _billing(),
        )
        for index in (1, 2, 3)
    ]

    results = bind_personal_payment_cards(
        page,
        expected_personal_account_id="personal-account-1",
        cards=cards,
        max_attempts=3,
        on_success=lambda _page, index, _result: successes.append(index),
        on_failure=lambda _page, index, _error: failures.append(index),
    )

    assert [result.payment_method_id for result in results] == ["pm_test_3"]
    assert failures == [1, 2]
    assert successes == [3]
    assert page.goto_urls == [
        "https://chatgpt.com/",
        "https://chatgpt.com/checkout/openai_llc/cs_test_checkout_1",
    ]
    assert page.clicked == ["#__card_submit__"] * 3
    assert page.evaluate_scripts.count(PAYMENT_METHOD_CHECKOUT_SCRIPT) == 1
    form_evaluations = [
        script
        for script in page.evaluate_scripts
        if "document.getElementById('__personal_card_stripe_modal__')" in script
    ]
    assert len(form_evaluations) == 1


def test_payment_method_batch_waits_three_seconds_between_cards(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(payment_module.time, "sleep", sleeps.append)
    page = _Page(
        confirmations=[
            {
                "ok": False,
                "button_disabled": False,
                "message": "card declined 1",
            },
            {
                "ok": False,
                "button_disabled": False,
                "message": "card declined 2",
            },
            {
                "ok": True,
                "payment_method_id": "pm_test_3",
                "last4": "0003",
                "brand": "visa",
            },
        ]
    )
    cards = [
        (
            BrowserPaymentCard(
                number=f"424242424242{index:04d}",
                cvc="123",
                exp_month=12,
                exp_year=2030,
            ),
            _billing(),
        )
        for index in (1, 2, 3)
    ]

    bind_personal_payment_cards(
        page,
        expected_personal_account_id="personal-account-1",
        cards=cards,
        max_attempts=3,
    )

    assert sleeps == [3.0, 3.0]


def test_payment_method_checkout_retries_concurrency_limit(monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(payment_module.time, "sleep", sleeps.append)

    class Page(_Page):
        checkout_attempts = 0

        def evaluate(self, script: str, argument: object = _NO_ARGUMENT):
            if script == PAYMENT_METHOD_CHECKOUT_SCRIPT:
                self.checkout_attempts += 1
                if self.checkout_attempts < 3:
                    raise RuntimeError(
                        "POST /backend-api/payments/checkout -> 503: "
                        "reached concurrency limit"
                    )
            return super().evaluate(script, argument)

    page = Page()
    result = bind_personal_payment_card(
        page,
        expected_personal_account_id="personal-account-1",
        card=_card(),
        billing=_billing(),
    )

    assert result.payment_method_id == "pm_test_1"
    assert page.checkout_attempts == 3
    assert sleeps == [5.0, 10.0]


def test_payment_method_batch_stops_after_three_declined_cards() -> None:
    page = _Page(
        confirmations=[
            {
                "ok": False,
                "button_disabled": False,
                "message": f"card declined {index}",
            }
            for index in range(1, 4)
        ]
    )
    cards = [(_card(), _billing()) for _index in range(3)]

    with pytest.raises(BrowserPaymentMethodConfirmError, match="card declined 3"):
        bind_personal_payment_cards(
            page,
            expected_personal_account_id="personal-account-1",
            cards=cards,
            max_attempts=3,
        )

    assert page.clicked == ["#__card_submit__"] * 3
    assert page.evaluate_scripts.count(PAYMENT_METHOD_CHECKOUT_SCRIPT) == 1


def test_payment_method_batch_stops_immediately_after_first_success() -> None:
    page = _Page(
        confirmations=[
            {
                "ok": True,
                "payment_method_id": "pm_test_1",
                "last4": "0001",
                "brand": "visa",
            }
        ]
    )
    requested_indexes: list[int] = []

    def card_provider(index: int):
        requested_indexes.append(index)
        return (
            BrowserPaymentCard(
                number=f"424242424242{index:04d}",
                cvc="123",
                exp_month=12,
                exp_year=2030,
            ),
            _billing(),
        )

    results = bind_personal_payment_cards(
        page,
        expected_personal_account_id="personal-account-1",
        card_provider=card_provider,
        max_attempts=3,
    )

    assert [result.payment_method_id for result in results] == ["pm_test_1"]
    assert requested_indexes == [1]
    assert page.clicked == ["#__card_submit__"]
    assert page.evaluate_scripts.count(PAYMENT_METHOD_CHECKOUT_SCRIPT) == 1
