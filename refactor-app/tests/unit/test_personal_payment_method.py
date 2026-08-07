from __future__ import annotations

import pytest

import refactor_app.application.workflows.personal_payment_method as payment_workflow
from refactor_app.application.workflows.personal_payment_method import (
    PersonalPaymentMethodBindError,
    PersonalPaymentMethodBindWorkflow,
    _BindingContext,
    _is_network_payment_method_error,
    _mail_provider_name,
    _ReservedPaymentAttempt,
)
from refactor_app.application.workflows.registration_proxy import (
    RegistrationBackboneProxy,
)
from refactor_app.plugins.openai_auth_browser import BrowserPaymentMethodResult


def test_payment_method_workflow_tries_three_distinct_cards_then_stops() -> None:
    attempts = [_attempt(1), _attempt(2), _attempt(3)]
    failures: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempts.pop(0)

        def _bind_attempt(self, *, attempt, **_kwargs):
            raise RuntimeError(f"card_declined: card-{attempt.attempt_count}")

        def _record_failure(self, *, attempt, **_kwargs):
            failures.append(attempt.card_id)

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(
        session_factory=lambda: None,
        mail_provider=object(),
    )

    with pytest.raises(PersonalPaymentMethodBindError, match="card_declined"):
        workflow.run(space_id="space-1")

    assert failures == ["card-1", "card-2", "card-3"]
    assert attempts == []


def test_payment_method_workflow_returns_after_later_card_succeeds() -> None:
    attempts = [_attempt(1), _attempt(2)]
    failures: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempts.pop(0)

        def _bind_attempt(self, *, attempt, **_kwargs):
            if attempt.attempt_count == 1:
                raise RuntimeError("card_declined")
            return BrowserPaymentMethodResult(
                personal_account_id="personal-1",
                payment_method_id="pm_test_2",
                last4="4242",
                brand="visa",
            )

        def _record_failure(self, *, attempt, **_kwargs):
            failures.append(attempt.card_id)

        def _record_success(self, *, attempt, result, **_kwargs):
            return {
                "space_id": "space-1",
                "payment_method_id": result.payment_method_id,
                "attempt_count": attempt.attempt_count,
            }

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(
        session_factory=lambda: None,
        mail_provider=object(),
    )

    result = workflow.run(space_id="space-1")

    assert result["payment_method_id"] == "pm_test_2"
    assert result["attempt_count"] == 2
    assert failures == ["card-1"]
    assert attempts == []


def test_bind_attempt_uses_registration_backbone_proxy_and_plaintext_card(monkeypatch) -> None:
    captured: dict = {}

    def resolve_proxy(_session_factory, *, email, country_code):
        captured["proxy_email"] = email
        captured["proxy_country"] = country_code
        return RegistrationBackboneProxy(
            proxy_url="http://backbone-proxy.example:8080",
            endpoint_id="backbone-42",
            endpoint_number=42,
            endpoint_count=20_000,
            country_code=country_code,
        )

    class Browser:
        def __init__(self, config):
            captured["browser_proxy"] = config.proxy_url

        def bind_personal_payment_method(
            self,
            mail,
            *,
            expected_personal_account_id,
            card,
            billing,
        ):
            captured["mail"] = mail
            captured["expected_personal_account_id"] = expected_personal_account_id
            captured["card"] = card
            captured["billing"] = billing
            return BrowserPaymentMethodResult(
                personal_account_id=expected_personal_account_id,
                payment_method_id="pm_test_1",
                last4="4242",
                brand="visa",
            )

    monkeypatch.setattr(
        payment_workflow,
        "resolve_registration_backbone_proxy",
        resolve_proxy,
    )
    monkeypatch.setattr(payment_workflow, "CamoufoxEmailRegistration", Browser)
    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        registration_proxy_country="JP",
    )
    attempt = _attempt(1)

    result = workflow._bind_attempt(
        context=_context(),
        attempt=attempt,
        work_id="work-1",
    )

    assert result.payment_method_id == "pm_test_1"
    assert captured["proxy_email"] == "member@outlook.com"
    assert captured["proxy_country"] == "JP"
    assert captured["browser_proxy"] == "http://backbone-proxy.example:8080"
    assert captured["card"].number == "4242424242424242"
    assert captured["card"].cvc == "123"
    assert captured["billing"].email == "member@outlook.com"


def test_payment_mail_provider_mapping_matches_supported_mail_sources() -> None:
    assert _mail_provider_name("member@hotmail.com") == "outlook"
    assert _mail_provider_name("member@icloud.com") == "icloud_hide_my_email"
    assert _mail_provider_name("member@example.test") == "cloudflare_temp_mail"


@pytest.mark.parametrize(
    ("error", "network"),
    [
        (PersonalPaymentMethodBindError("payment_method_stripe_timeout"), True),
        (PersonalPaymentMethodBindError("stripe_js_load_failed"), True),
        (PersonalPaymentMethodBindError("http_503", "upstream unavailable"), True),
        (PersonalPaymentMethodBindError("card_declined", "issuer declined"), False),
        (PersonalPaymentMethodBindError("incorrect_number", "card number is invalid"), False),
    ],
)
def test_payment_method_failure_classification_preserves_only_network_cards(
    error: PersonalPaymentMethodBindError,
    network: bool,
) -> None:
    assert _is_network_payment_method_error(error) is network


def _context() -> _BindingContext:
    return _BindingContext(
        space_id="space-1",
        external_space_id="personal-1",
        user_account_id="account-1",
        email="member@outlook.com",
    )


def _attempt(
    number: int,
) -> _ReservedPaymentAttempt:
    return _ReservedPaymentAttempt(
        card_id=f"card-{number}",
        card_number="4242424242424242",
        cvc="123",
        card_last4="4242",
        exp_month=12,
        exp_year=2030,
        full_name="Ada Lovelace",
        line1="123 Test Street",
        line2="",
        city="New York",
        state="NY",
        postal_code="10001",
        country="US",
        phone="",
        attempt_count=number,
    )
