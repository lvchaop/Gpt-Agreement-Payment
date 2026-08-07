from __future__ import annotations

import json
import re

import pytest

from refactor_app.plugins.openai_auth_browser import personal_payment_method as payment_module
from refactor_app.plugins.openai_auth_browser.personal_payment_method import (
    PAYMENT_METHOD_BOOTSTRAP_SCRIPT,
    PAYMENT_METHOD_CHECKOUT_SCRIPT,
    PAYMENT_METHOD_CONFIRM_SCRIPT,
    BrowserBillingDetails,
    BrowserPaymentCard,
    BrowserPaymentMethodConfirmError,
    BrowserPersonalPaymentMethodError,
    bind_personal_payment_card,
)


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
    assert "entry_point: 'all_plans_pricing_modal'" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "plan_name: 'chatgptplusplan'" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "country: 'US'" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "currency: 'USD'" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "checkout_ui_mode: 'hosted'" in PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert "'x-openai-target-path': '/backend-api/payments/checkout'" in (
        PAYMENT_METHOD_CHECKOUT_SCRIPT
    )
    assert "/api/auth/session" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/accounts/check/v4-2023-04-27" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/payments/stripe_client_bootstrap" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/payments/payment_method'" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "JSON.stringify({account_id: personalAccountId})" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "'x-openai-target-path': '/backend-api/payments/payment_method'" in (
        PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    )
    assert "'x-openai-target-route': '/backend-api/payments/payment_method'" in (
        PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    )
    assert "/backend-api/payments/payment_methods?account_id=" in PAYMENT_METHOD_CONFIRM_SCRIPT
    assert "/backend-api/payments/payment_method/default" in PAYMENT_METHOD_CONFIRM_SCRIPT
    assert "'x-openai-target-path': '/backend-api/payments/payment_methods'" in (
        PAYMENT_METHOD_CONFIRM_SCRIPT
    )
    assert "'x-openai-target-route': '/backend-api/payments/payment_method/default'" in (
        PAYMENT_METHOD_CONFIRM_SCRIPT
    )
    assert "set_as_default_payment_method: true" in PAYMENT_METHOD_CONFIRM_SCRIPT
    assert "pk_live_" not in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "js.stripe.com/basil" not in PAYMENT_METHOD_BOOTSTRAP_SCRIPT


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
    assert page.evaluate_args == [
        {"expectedPersonalAccountId": "personal-account-1"}
    ]
    bootstrap_evaluations = [
        script for script in page.evaluate_scripts if PAYMENT_METHOD_BOOTSTRAP_SCRIPT in script
    ]
    confirm_evaluations = [
        script for script in page.evaluate_scripts if PAYMENT_METHOD_CONFIRM_SCRIPT in script
    ]
    assert len(bootstrap_evaluations) == 1
    assert len(confirm_evaluations) == 1
    assert bootstrap_evaluations[0].startswith("mw:")
    assert confirm_evaluations[0].startswith("mw:")
    assert '"expectedPersonalAccountId":"personal-account-1"' in (
        bootstrap_evaluations[0]
    )
    assert '"country":"US"' in confirm_evaluations[0]
    assert any(
        script.startswith("mw:")
        and "__refactorPersonalPaymentMethod?.ready" in script
        for script in page.evaluate_scripts
    )
    assert any(
        script.startswith("mw:")
        and "__refactorPersonalPaymentMethod?.complete" in script
        for script in page.evaluate_scripts
    )


def test_bind_personal_payment_card_surfaces_stripe_error_without_card_data() -> None:
    page = _Page(
        confirmation={
            "ok": False,
            "failure_stage": "confirm",
            "error_code": "card_declined",
            "error_message": "The card was declined.",
            "stripe_diagnostics": {
                "error_type": "card_error",
                "decline_code": "do_not_honor",
                "setup_intent_id": "seti_test_1",
                "setup_intent_status": "requires_payment_method",
                "payment_method_id": "pm_test_declined",
                "request_log_url": "https://dashboard.stripe.test/logs/req_test_1",
                "unexpected_secret": "must-not-be-logged",
            },
        }
    )

    with pytest.raises(BrowserPaymentMethodConfirmError, match="card_declined") as error:
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert "4242424242424242" not in str(error.value)
    assert "123" not in str(error.value)
    assert error.value.diagnostics == {
        "error_type": "card_error",
        "decline_code": "do_not_honor",
        "request_log_url": "https://dashboard.stripe.test/logs/req_test_1",
        "setup_intent_id": "seti_test_1",
        "setup_intent_status": "requires_payment_method",
        "payment_method_id": "pm_test_declined",
    }
    assert "unexpected_secret" not in error.value.diagnostics


def test_bind_personal_payment_card_keeps_post_confirm_failure_separate() -> None:
    page = _Page(
        confirmation={
            "ok": False,
            "failure_stage": "post_confirm",
            "error_code": "payment_method_default_not_verified",
            "error_message": "",
        }
    )

    with pytest.raises(BrowserPersonalPaymentMethodError) as error:
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert not isinstance(error.value, BrowserPaymentMethodConfirmError)


def test_bind_personal_payment_card_rejects_non_stripe_checkout_before_card_fill() -> None:
    page = _Page(
        checkout={
            "personal_account_id": "personal-account-1",
            "checkout_session_id": "oaics_test_checkout_1",
            "processor_entity": "openai_llc",
            "checkout_url": "https://chatgpt.com/checkout/openai_llc/oaics_test_checkout_1",
        }
    )

    with pytest.raises(
        BrowserPersonalPaymentMethodError,
        match="hosted checkout session is invalid",
    ):
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert page.frame.values == {}
    assert page.goto_urls == ["https://chatgpt.com/"]


def test_bind_personal_payment_card_reloads_checkout_when_constructor_is_late(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FastClock()
    monkeypatch.setattr(payment_module.time, "monotonic", clock.monotonic)
    page = _Page(
        stripe_constructor_ready=False,
        stripe_constructor_ready_after_reload=True,
    )

    result = bind_personal_payment_card(
        page,
        expected_personal_account_id="personal-account-1",
        card=_card(),
        billing=_billing(),
    )

    assert result.payment_method_id == "pm_test_1"
    assert page.reload_count == 1


def test_bind_personal_payment_card_stops_before_setup_intent_when_stripe_never_loads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FastClock()
    monkeypatch.setattr(payment_module.time, "monotonic", clock.monotonic)
    page = _Page(stripe_constructor_ready=False)

    with pytest.raises(
        BrowserPersonalPaymentMethodError,
        match="payment_method_stripe_constructor_missing",
    ):
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert page.evaluate_scripts[0] == PAYMENT_METHOD_CHECKOUT_SCRIPT
    assert all(
        PAYMENT_METHOD_BOOTSTRAP_SCRIPT not in script for script in page.evaluate_scripts
    )
    assert page.frame.values == {}
    assert page.reload_count == 1


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


class _Frame:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def locator(self, selector: str) -> _Locator:
        return _Locator(self, selector)


class _FastClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        self.value += 16.0
        return self.value


_NO_ARGUMENT = object()


class _Page:
    def __init__(
        self,
        *,
        checkout: dict | None = None,
        confirmation: dict | None = None,
        stripe_constructor_ready: bool = True,
        stripe_constructor_ready_after_reload: bool = False,
    ) -> None:
        self.frame = _Frame()
        self.frames = [self.frame]
        self.goto_urls: list[str] = []
        self.evaluate_scripts: list[str] = []
        self.evaluate_args: list[dict] = []
        self.main_world_tasks: dict[str, dict] = {}
        self.reload_count = 0
        self.stripe_constructor_ready = stripe_constructor_ready
        self.stripe_constructor_ready_after_reload = (
            stripe_constructor_ready_after_reload
        )
        self.checkout = checkout or {
            "personal_account_id": "personal-account-1",
            "checkout_session_id": "cs_test_checkout_1",
            "processor_entity": "openai_llc",
            "checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_test_checkout_1",
        }
        self.confirmation = confirmation or {
            "ok": True,
            "personal_account_id": "personal-account-1",
            "payment_method_id": "pm_test_1",
            "last4": "4242",
            "brand": "visa",
        }

    def goto(self, url: str, **_kwargs) -> None:
        self.goto_urls.append(url)

    def reload(self, **_kwargs) -> None:
        self.reload_count += 1
        if self.stripe_constructor_ready_after_reload:
            self.stripe_constructor_ready = True

    def evaluate(self, script: str, argument: object = _NO_ARGUMENT):
        self.evaluate_scripts.append(script)
        if argument is not _NO_ARGUMENT:
            assert isinstance(argument, dict)
            self.evaluate_args.append(argument)
        if script == PAYMENT_METHOD_CHECKOUT_SCRIPT:
            return self.checkout
        if script.startswith("mw:") and "Promise.resolve((" in script:
            task_id = self._task_id(script)
            if PAYMENT_METHOD_BOOTSTRAP_SCRIPT in script:
                value = {"personal_account_id": "personal-account-1"}
            else:
                assert PAYMENT_METHOD_CONFIRM_SCRIPT in script
                value = self.confirmation
            self.main_world_tasks[task_id] = {
                "status": "fulfilled",
                "value": value,
            }
            return task_id
        if script.startswith("mw:") and "const task = tasks?.[taskId]" in script:
            task_id = self._task_id(script)
            return json.dumps(self.main_world_tasks.pop(task_id))
        if script.startswith("mw:") and "typeof window.Stripe" in script:
            return self.stripe_constructor_ready
        if script.startswith("mw:") and (
            "__refactorPersonalPaymentMethod?.ready" in script
            or "__refactorPersonalPaymentMethod?.complete" in script
        ):
            return True
        raise AssertionError(f"unexpected evaluate script: {script[:120]}")

    @staticmethod
    def _task_id(script: str) -> str:
        match = re.search(r'const taskId = "([^"]+)";', script)
        assert match is not None
        return match.group(1)
