from __future__ import annotations

import pytest

from refactor_app.plugins.openai_auth_browser.personal_payment_method import (
    PAYMENT_METHOD_BOOTSTRAP_SCRIPT,
    PAYMENT_METHOD_CONFIRM_SCRIPT,
    BrowserBillingDetails,
    BrowserPaymentCard,
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
    assert "/api/auth/session" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/accounts/check/v4-2023-04-27" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/payments/stripe_client_bootstrap" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/payments/payment_method'" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "JSON.stringify({account_id: personalAccountId})" in PAYMENT_METHOD_BOOTSTRAP_SCRIPT
    assert "/backend-api/payments/payment_methods?account_id=" in PAYMENT_METHOD_CONFIRM_SCRIPT
    assert "/backend-api/payments/payment_method/default" in PAYMENT_METHOD_CONFIRM_SCRIPT
    assert "set_as_default_payment_method: true" in PAYMENT_METHOD_CONFIRM_SCRIPT
    assert "pk_live_" not in PAYMENT_METHOD_BOOTSTRAP_SCRIPT


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
    assert page.frame.values == {
        'input[name="cardnumber"]': "4242424242424242",
        'input[name="exp-date"]': "1230",
        'input[name="cvc"]': "123",
    }
    assert page.evaluate_args[0] == {"expectedPersonalAccountId": "personal-account-1"}
    assert page.evaluate_args[1]["billingDetails"]["address"]["country"] == "US"


def test_bind_personal_payment_card_surfaces_stripe_error_without_card_data() -> None:
    page = _Page(
        confirmation={
            "ok": False,
            "error_code": "card_declined",
            "error_message": "The card was declined.",
        }
    )

    with pytest.raises(BrowserPersonalPaymentMethodError, match="card_declined") as error:
        bind_personal_payment_card(
            page,
            expected_personal_account_id="personal-account-1",
            card=_card(),
            billing=_billing(),
        )

    assert "4242424242424242" not in str(error.value)
    assert "123" not in str(error.value)


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


class _Page:
    def __init__(self, *, confirmation: dict | None = None) -> None:
        self.frame = _Frame()
        self.frames = [self.frame]
        self.evaluate_args: list[dict] = []
        self.confirmation = confirmation or {
            "ok": True,
            "personal_account_id": "personal-account-1",
            "payment_method_id": "pm_test_1",
            "last4": "4242",
            "brand": "visa",
        }

    def goto(self, *_args, **_kwargs) -> None:
        return None

    def wait_for_function(self, *_args, **_kwargs) -> None:
        return None

    def evaluate(self, script: str, argument: dict) -> dict:
        self.evaluate_args.append(argument)
        if script == PAYMENT_METHOD_BOOTSTRAP_SCRIPT:
            return {"personal_account_id": "personal-account-1"}
        assert script == PAYMENT_METHOD_CONFIRM_SCRIPT
        return self.confirmation
