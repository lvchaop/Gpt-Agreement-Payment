from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

import refactor_app.application.workflows.personal_payment_method as payment_workflow
from refactor_app.api.routes.resources import PersonalPaymentMethodBindJobRequest
from refactor_app.application.workflows.personal_payment_method import (
    PersonalPaymentMethodBindError,
    PersonalPaymentMethodBindWorkflow,
    _BindingContext,
    _is_network_payment_method_error,
    _ReservedPaymentAttempt,
    mail_provider_name_for_email,
)
from refactor_app.application.workflows.registration_proxy import (
    CliproxyProxy,
)
from refactor_app.plugins.openai_auth_browser import (
    BrowserAccountDeactivatedError,
    BrowserPaymentMethodConfirmError,
    BrowserPaymentMethodResult,
    BrowserPersonalPaymentMethodError,
)
from refactor_app.plugins.openai_auth_protocol.card_payment import (
    CardPaymentConfirmError,
    CardPaymentResult,
    CardPaymentUnknownResultError,
)


def test_payment_method_workflow_tries_three_distinct_cards_then_stops() -> None:
    attempts = [_attempt(1), _attempt(2), _attempt(3)]
    failures: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempts.pop(0)

        def _bind_attempt(self, *, attempt, **_kwargs):
            raise BrowserPaymentMethodConfirmError(
                "card_declined",
                f"card-{attempt.attempt_count}",
            )

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


def test_payment_method_bind_job_defaults_to_continue_into_plus_checkout() -> None:
    assert PersonalPaymentMethodBindJobRequest().auto_start_plus_checkout is True


def test_payment_card_selection_randomizes_within_preferred_bin8_pool() -> None:
    preferred_card = object()

    class Session:
        def __init__(self):
            self.statements = []

        def scalar(self, statement):
            self.statements.append(statement)
            return preferred_card

    session = Session()

    selected = payment_workflow._select_available_payment_card(session)

    assert selected is preferred_card
    assert len(session.statements) == 1
    sql = _postgresql_sql(session.statements[0])
    assert "substr(payment_card_pool.card_number, 1, 8)" in sql
    for prefix in payment_workflow.PREFERRED_PAYMENT_CARD_BIN8_PREFIXES:
        assert f"'{prefix}'" in sql
    assert "ORDER BY random()" in sql


def test_payment_card_selection_falls_back_to_full_pool() -> None:
    fallback_card = object()

    class Session:
        def __init__(self):
            self.responses = [None, fallback_card]
            self.statements = []

        def scalar(self, statement):
            self.statements.append(statement)
            return self.responses.pop(0)

    session = Session()

    selected = payment_workflow._select_available_payment_card(session)

    assert selected is fallback_card
    assert len(session.statements) == 2
    preferred_sql = _postgresql_sql(session.statements[0])
    fallback_sql = _postgresql_sql(session.statements[1])
    assert "substr(payment_card_pool.card_number, 1, 8)" in preferred_sql
    assert "substr(payment_card_pool.card_number, 1, 8)" not in fallback_sql
    assert "ORDER BY random()" in fallback_sql


def test_payment_card_selection_honors_explicit_card_id() -> None:
    explicit_card = object()

    class Session:
        def __init__(self):
            self.statements = []

        def scalar(self, statement):
            self.statements.append(statement)
            return explicit_card

    session = Session()

    selected = payment_workflow._select_available_payment_card(
        session,
        payment_card_id=" card-1 ",
    )

    assert selected is explicit_card
    assert len(session.statements) == 1
    sql = _postgresql_sql(session.statements[0])
    assert "payment_card_pool.id = 'card-1'" in sql
    assert "substr(payment_card_pool.card_number, 1, 8)" not in sql
    assert "ORDER BY random()" not in sql


def test_payment_method_workflow_uses_protocol_for_three_card_window(
    monkeypatch,
) -> None:
    attempts = [_attempt(1), _attempt(2), _attempt(3)]
    first_attempt = attempts[0]
    billing_templates: list[_ReservedPaymentAttempt | None] = []
    failed: list[str] = []
    protocol_calls: list[tuple[object, str]] = []

    def run_protocol(config, *, proxy_url, **_kwargs):
        protocol_calls.append((config, proxy_url))
        if len(protocol_calls) < 3:
            raise CardPaymentConfirmError("card_declined", "issuer declined")
        return CardPaymentResult(
            personal_account_id="personal-1",
            payment_method_id="pm_test_3",
            last4="4242",
            brand="visa",
        )

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id, *, billing_template=None):
            billing_templates.append(billing_template)
            return attempts.pop(0)

        def _record_failure(self, *, attempt, **_kwargs):
            failed.append(attempt.card_id)

        def _record_success(self, *, attempt, result, **_kwargs):
            return {
                "space_id": "space-1",
                "payment_method_id": result.payment_method_id,
                "payment_method_last4": result.last4,
                "attempt_count": attempt.attempt_count,
            }

        def _event(self, **_kwargs):
            return None

    monkeypatch.setattr(payment_workflow, "run_card_payment", run_protocol)
    monkeypatch.setattr(
        payment_workflow,
        "resolve_cliproxy_proxy",
        lambda *_args, **_kwargs: CliproxyProxy(
            proxy_url="http://proxy.example:8080",
            country_code="US",
        ),
    )
    monkeypatch.setattr(
        payment_workflow,
        "detect_proxy_egress_country",
        lambda _proxy_url: "US",
    )
    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    result = workflow.run(space_id="space-1")

    assert result["payment_method_id"] == "pm_test_3"
    assert len(protocol_calls) == 3
    assert failed == ["card-1", "card-2"]
    assert billing_templates == [None, first_attempt, first_attempt]
    assert [call[1] for call in protocol_calls] == ["http://proxy.example:8080"] * 3
    assert protocol_calls[0][0].access_token == "access-token"
    assert protocol_calls[0][0].cookie_header == "session=cookie"
    assert protocol_calls[0][0].auth_cookie_header == "auth=cookie"


def test_payment_method_workflow_releases_reserved_card_when_protocol_aborts(
    monkeypatch,
) -> None:
    attempt = _attempt(1)
    released: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id, *, billing_template=None):
            return attempt

        def _release_pre_payment_failure(self, *, attempt, **_kwargs):
            released.append(attempt.card_id)

        def _event(self, **_kwargs):
            return None

    monkeypatch.setattr(
        payment_workflow,
        "run_card_payment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("protocol aborted before confirm")
        ),
    )
    monkeypatch.setattr(
        payment_workflow,
        "resolve_cliproxy_proxy",
        lambda *_args, **_kwargs: CliproxyProxy(
            proxy_url="http://proxy.example:8080",
            country_code="US",
        ),
    )
    monkeypatch.setattr(
        payment_workflow,
        "detect_proxy_egress_country",
        lambda _proxy_url: "US",
    )

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())
    with pytest.raises(
        PersonalPaymentMethodBindError,
        match="protocol aborted before confirm",
    ):
        workflow.run(space_id="space-1")

    assert released == ["card-1"]


def test_payment_method_workflow_stops_before_reserving_card_without_promotion() -> None:
    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            raise PersonalPaymentMethodBindError("payment_method_promotion_required")

        def _reserve_attempt(self, _space_id):
            raise AssertionError("card inventory must not be touched")

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError, match="payment_method_promotion_required"):
        workflow.run(space_id="space-1")


def test_payment_method_reservation_rejects_existing_binding_under_lock() -> None:
    class Space:
        id = "space-1"
        has_promotion = True
        promotion_id = "plus-1-month-free"
        has_payment_method = False
        payment_method_status = "binding"
        payment_method_attempt_count = 1
        payment_method_cooldown_until = None

    class Session:
        def __init__(self):
            self.space = Space()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, row_id, *, with_for_update=False):
            assert model is payment_workflow.SpaceModel
            assert row_id == "space-1"
            assert with_for_update is True
            return self.space

        def scalar(self, _statement):
            raise AssertionError("inventory must not be touched while binding is active")

    workflow = PersonalPaymentMethodBindWorkflow(session_factory=Session)

    with pytest.raises(
        PersonalPaymentMethodBindError,
        match="payment_method_binding_in_progress",
    ):
        workflow._reserve_attempt("space-1")


def test_payment_method_context_can_skip_local_promotion_for_plus_checkout() -> None:
    class Space:
        id = "space-1"
        space_type = "personal"
        space_status = "active"
        has_promotion = False
        promotion_id = ""
        owner_user_account_id = "account-1"
        external_space_id = "personal-1"
        has_payment_method = False
        payment_method_status = "missing"
        payment_method_attempt_count = 0
        payment_method_cooldown_until = None

    class Account:
        id = "account-1"
        account_status = "active"
        email = "member@outlook.com"
        password = "test-password"
        cookie_header = "session=cookie"
        auth_cookie_header = "auth=cookie"
        mfa_status = "not_configured"
        twofauth_account_id = ""
        access_token = "access-token"
        session_token = "session-token"
        device_id = "device-1"

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, row_id):
            if model is payment_workflow.SpaceModel:
                assert row_id == "space-1"
                return Space()
            assert model is payment_workflow.UserAccountModel
            assert row_id == "account-1"
            return Account()

    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=Session,
        require_local_promotion=False,
    )

    context, existing = workflow._load_context("space-1")

    assert existing is None
    assert context.space_id == "space-1"
    assert context.promotion_id == ""


def test_payment_method_reservation_can_skip_local_promotion_for_plus_checkout() -> None:
    class Space:
        id = "space-1"
        has_promotion = False
        promotion_id = ""
        has_payment_method = False
        payment_method_status = "missing"
        payment_method_attempt_count = 0
        payment_method_cooldown_until = None
        payment_method_last_attempt_at = None
        payment_method_last_error_code = ""
        payment_method_last_error_message = ""
        updated_at = None

    class Card:
        id = "card-2"
        card_number = "4242424242424242"
        cvc = "123"
        last4 = "4242"
        exp_month = 12
        exp_year = 2030
        card_status = "available"
        reserved_by_space_id = ""
        reserved_at = None
        use_count = 0
        last_used_at = None
        last_error_code = ""
        last_error_message = ""
        updated_at = None

    class Session:
        def __init__(self):
            self.space = Space()
            self.card = Card()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, row_id, *, with_for_update=False):
            assert model is payment_workflow.SpaceModel
            assert row_id == "space-1"
            assert with_for_update is True
            return self.space

        def scalar(self, _statement):
            return self.card

        def commit(self):
            self.committed = True

    session = Session()
    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=lambda: session,
        require_local_promotion=False,
    )

    reserved = workflow._reserve_attempt(
        "space-1",
        billing_template=_attempt(1),
        payment_card_id="card-2",
    )

    assert reserved.card_id == "card-2"
    assert reserved.attempt_count == 1
    assert session.space.payment_method_status == "binding"
    assert session.committed is True


def test_payment_method_reservation_filters_address_pool_by_selected_country() -> None:
    space = SimpleNamespace(
        id="space-1",
        has_promotion=True,
        promotion_id="plus-1-month-free",
        has_payment_method=False,
        payment_method_status="missing",
        payment_method_attempt_count=0,
        payment_method_cooldown_until=None,
        payment_method_last_attempt_at=None,
        payment_method_last_error_code="",
        payment_method_last_error_message="",
        updated_at=None,
    )
    name = SimpleNamespace(
        full_name="Erika Mustermann",
        use_count=0,
        last_used_at=None,
        updated_at=None,
    )
    address = SimpleNamespace(
        line1="Musterstrasse 1",
        line2="",
        city="Berlin",
        state="BE",
        postal_code="10115",
        country="DE",
        phone="",
        use_count=0,
        last_used_at=None,
        updated_at=None,
    )
    card = SimpleNamespace(
        id="card-1",
        card_number="4242424242424242",
        cvc="123",
        last4="4242",
        exp_month=12,
        exp_year=2030,
        card_status="available",
        reserved_by_space_id=None,
        reserved_at=None,
        use_count=0,
        last_used_at=None,
        last_error_code="",
        last_error_message="",
        updated_at=None,
    )

    class Session:
        def __init__(self):
            self.statements = []
            self.responses = iter((name, address, card))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, row_id, *, with_for_update=False):
            assert model is payment_workflow.SpaceModel
            assert row_id == "space-1"
            assert with_for_update is True
            return space

        def scalar(self, statement):
            self.statements.append(statement)
            return next(self.responses)

        def commit(self):
            return None

    session = Session()
    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=lambda: session,
        registration_proxy_country="de",
    )

    reserved = workflow._reserve_attempt(
        "space-1",
        payment_card_id="card-1",
    )

    address_sql = _postgresql_sql(session.statements[1])
    assert "payment_address_pool.country = 'DE'" in address_sql
    assert reserved.country == "DE"
    assert reserved.line1 == "Musterstrasse 1"


def test_payment_method_reservation_reports_selected_country_without_address() -> None:
    space = SimpleNamespace(
        id="space-1",
        has_promotion=True,
        promotion_id="plus-1-month-free",
        has_payment_method=False,
        payment_method_status="missing",
        payment_method_attempt_count=0,
        payment_method_cooldown_until=None,
        payment_method_last_error_code="",
        payment_method_last_error_message="",
        updated_at=None,
    )
    name = SimpleNamespace(full_name="Taro Yamada")
    card = SimpleNamespace(id="card-1")

    class Session:
        def __init__(self):
            self.responses = iter((name, None, card))
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _model, _row_id, *, with_for_update=False):
            assert with_for_update is True
            return space

        def scalar(self, _statement):
            return next(self.responses)

        def commit(self):
            self.committed = True

    session = Session()
    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=lambda: session,
        registration_proxy_country="jp",
    )

    with pytest.raises(PersonalPaymentMethodBindError) as raised:
        workflow._reserve_attempt("space-1", payment_card_id="card-1")

    assert raised.value.error_code == "payment_address_pool_country_empty"
    assert raised.value.error_message == "no active payment address for JP"
    assert raised.value.diagnostics == {"country": "JP"}
    assert space.payment_method_status == "failed"
    assert space.payment_method_last_error_code == "payment_address_pool_country_empty"
    assert session.committed is True


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
                raise BrowserPaymentMethodConfirmError("card_declined")
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


def test_payment_method_workflow_does_not_fallback_after_explicit_card_decline() -> None:
    attempts = [_attempt(1), _attempt(2)]
    reserve_card_ids: list[str] = []
    failures: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id, *, payment_card_id=""):
            reserve_card_ids.append(payment_card_id)
            return attempts.pop(0)

        def _bind_attempt(self, **_kwargs):
            raise BrowserPaymentMethodConfirmError("card_declined")

        def _record_failure(self, *, attempt, **_kwargs):
            failures.append(attempt.card_id)

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError, match="card_declined"):
        workflow.run(space_id="space-1", payment_card_id="card-explicit")

    assert reserve_card_ids == ["card-explicit"]
    assert failures == ["card-1"]
    assert [attempt.card_id for attempt in attempts] == ["card-2"]


def test_payment_method_workflow_writes_structured_stripe_diagnostics() -> None:
    events: list[dict] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return _attempt(3)

        def _bind_attempt(self, **_kwargs):
            raise BrowserPaymentMethodConfirmError(
                "card_declined",
                "The card was declined.",
                diagnostics={
                    "error_type": "card_error",
                    "decline_code": "do_not_honor",
                    "setup_intent_id": "seti_test_1",
                },
            )

        def _record_failure(self, **_kwargs):
            return None

        def _event(self, **kwargs):
            events.append(kwargs)

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError, match="card_declined"):
        workflow.run(space_id="space-1", run_id="run-1")

    failed = next(
        event for event in events if event["event_type"] == "personal_payment_method.attempt_failed"
    )
    assert failed["data_json"]["stripe_diagnostics"] == {
        "error_type": "card_error",
        "decline_code": "do_not_honor",
        "setup_intent_id": "seti_test_1",
    }


def test_bind_attempt_uses_cliproxy_and_protocol_credentials(monkeypatch) -> None:
    captured: dict = {}

    def resolve_proxy(*, email, country_code):
        captured["proxy_email"] = email
        captured["proxy_country"] = country_code
        return CliproxyProxy(
            proxy_url="http://backbone-proxy.example:8080",
            country_code=country_code,
        )

    def run_protocol(config, *, proxy_url, event_callback, **_kwargs):
        captured["config"] = config
        captured["proxy_url"] = proxy_url
        captured["event_callback"] = event_callback
        return CardPaymentResult(
            personal_account_id=config.account_id,
            payment_method_id="pm_test_1",
            last4="4242",
            brand="visa",
        )

    monkeypatch.setattr(
        payment_workflow,
        "resolve_cliproxy_proxy",
        resolve_proxy,
    )
    monkeypatch.setattr(
        payment_workflow,
        "detect_proxy_egress_country",
        lambda proxy_url: captured.__setitem__("egress_proxy_url", proxy_url) or "US",
    )
    monkeypatch.setattr(payment_workflow, "run_card_payment", run_protocol)
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
    assert captured["proxy_url"] == "http://backbone-proxy.example:8080"
    assert captured["egress_proxy_url"] == "http://backbone-proxy.example:8080"
    assert callable(captured["event_callback"])
    assert captured["config"].access_token == "access-token"
    assert captured["config"].session_token == "session-token"
    assert captured["config"].device_id == "device-1"
    assert captured["config"].card["number"] == "4242424242424242"
    assert captured["config"].card["cvc"] == "123"
    assert captured["config"].billing["email"] == "member@outlook.com"
    assert captured["config"].captcha_api_url == ""
    assert captured["config"].captcha_client_key == ""
    assert captured["config"].locale == "en-US"
    assert captured["config"].browser_timezone == "America/Los_Angeles"


def test_payment_protocol_locale_tracks_proxy_egress_country() -> None:
    assert payment_workflow._payment_locale_for_proxy_country("US") == "en-US"
    assert payment_workflow._payment_locale_for_proxy_country("jp") == "ja-JP"
    assert payment_workflow._payment_timezone_for_proxy_country("US") == (
        "America/Los_Angeles"
    )
    assert payment_workflow._payment_timezone_for_proxy_country("jp") == "Asia/Tokyo"
    assert payment_workflow._payment_timezone_for_proxy_country("de") == "Europe/Berlin"
    with pytest.raises(ValueError, match="ISO alpha-2"):
        payment_workflow._payment_locale_for_proxy_country("unknown")
    with pytest.raises(ValueError, match="ISO alpha-2"):
        payment_workflow._payment_timezone_for_proxy_country("unknown")


def test_payment_mail_provider_mapping_matches_supported_mail_sources() -> None:
    assert mail_provider_name_for_email("member@hotmail.com") == "outlook"
    assert mail_provider_name_for_email("member@icloud.com") == "icloud_hide_my_email"
    assert mail_provider_name_for_email("member@example.test") == "cloudflare_temp_mail"


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


@pytest.mark.parametrize(
    "error",
    [
        BrowserPersonalPaymentMethodError("payment account bootstrap failed"),
        BrowserPaymentMethodConfirmError(
            "payment_method_stripe_timeout",
            "confirm timed out",
        ),
    ],
)
def test_payment_method_workflow_releases_non_consuming_failure_without_retry(
    error: Exception,
) -> None:
    attempts = [_attempt(1), _attempt(2)]
    released: list[str] = []
    consumed: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempts.pop(0)

        def _bind_attempt(self, **_kwargs):
            raise error

        def _release_pre_payment_failure(self, *, attempt, **_kwargs):
            released.append(attempt.card_id)

        def _record_failure(self, *, attempt, **_kwargs):
            consumed.append(attempt.card_id)

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError):
        workflow.run(space_id="space-1")

    assert released == ["card-1"]
    assert consumed == []
    assert [attempt.card_id for attempt in attempts] == ["card-2"]


def test_payment_method_workflow_stops_after_unknown_confirm_result() -> None:
    attempts = [_attempt(1), _attempt(2)]
    released: list[str] = []
    consumed: list[tuple[str, bool]] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempts.pop(0)

        def _bind_attempt(self, **_kwargs):
            raise CardPaymentUnknownResultError(
                "payment_method_confirm_result_unknown",
                "connection reset after submit",
            )

        def _release_pre_payment_failure(self, *, attempt, **_kwargs):
            released.append(attempt.card_id)

        def _record_failure(self, *, attempt, stop_replay=False, **_kwargs):
            consumed.append((attempt.card_id, stop_replay))

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError, match="result_unknown"):
        workflow.run(space_id="space-1")

    assert released == []
    assert consumed == [("card-1", True)]
    assert [attempt.card_id for attempt in attempts] == ["card-2"]


def test_unknown_confirm_failure_persists_manual_review_block() -> None:
    class Space:
        id = "space-1"
        has_payment_method = False
        payment_method_attempt_count = 1
        payment_method_status = "binding"
        payment_method_cooldown_until = None
        payment_method_last_error_code = ""
        payment_method_last_error_message = ""
        updated_at = None

    class Card:
        id = "card-1"
        card_status = "in_use"
        reserved_by_space_id = "space-1"
        reserved_at = object()
        last_error_code = ""
        last_error_message = ""
        updated_at = None

    class Session:
        def __init__(self):
            self.space = Space()
            self.card = Card()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, row_id, *, with_for_update=False):
            assert with_for_update is True
            if model is payment_workflow.SpaceModel:
                assert row_id == "space-1"
                return self.space
            assert model is payment_workflow.PaymentCardPoolModel
            assert row_id == "card-1"
            return self.card

        def commit(self):
            self.committed = True

    session = Session()
    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=lambda: session,
        mail_provider=object(),
    )

    workflow._record_failure(
        context=_context(),
        attempt=_attempt(1),
        error=PersonalPaymentMethodBindError(
            "payment_method_confirm_result_unknown",
            "remote result is unknown",
        ),
        stop_replay=True,
    )

    assert session.space.payment_method_attempt_count == (
        payment_workflow.MAX_PAYMENT_METHOD_CARD_ATTEMPTS
    )
    assert session.space.payment_method_status == "failed"
    assert session.space.payment_method_cooldown_until is None
    assert payment_workflow._payment_method_cooldown_active(
        session.space,
        now=payment_workflow.datetime.now(payment_workflow.UTC),
    )
    assert session.card.card_status == "failed"
    assert session.card.reserved_by_space_id is None
    assert session.card.reserved_at is None
    assert session.committed is True


def test_remote_success_transient_persistence_failure_retries_local_write_only() -> None:
    attempt = _attempt(1)
    result = CardPaymentResult(
        personal_account_id="personal-1",
        payment_method_id="pm_remote_success",
        last4="4242",
        brand="visa",
    )

    class Space:
        id = "space-1"
        external_space_id = "personal-1"
        has_payment_method = False
        payment_method_attempt_count = 1
        payment_method_status = "binding"
        payment_method_cooldown_until = None
        payment_method_last_error_code = ""
        payment_method_last_error_message = ""
        updated_at = None

    class Card:
        id = "card-1"
        card_status = "in_use"
        reserved_by_space_id = "space-1"
        reserved_at = object()
        last_error_code = ""
        last_error_message = ""
        updated_at = None

    class Session:
        def __init__(self):
            self.space = Space()
            self.card = Card()
            self.commit_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, row_id, *, with_for_update=False):
            assert with_for_update is True
            if model is payment_workflow.SpaceModel:
                assert row_id == "space-1"
                return self.space
            assert model is payment_workflow.PaymentCardPoolModel
            assert row_id == "card-1"
            return self.card

        def commit(self):
            self.commit_calls += 1
            if self.commit_calls == 1:
                raise RuntimeError("database write failed")

    session = Session()

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempt

        def _bind_attempt(self, **_kwargs):
            return result

        def _release_pre_payment_failure(self, **_kwargs):
            raise AssertionError("remote success must not release the card as available")

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(session_factory=lambda: session, mail_provider=object())

    output = workflow.run(space_id="space-1")

    assert output["payment_method_id"] == "pm_remote_success"
    assert output["payment_method_status"] == "bound"
    assert session.space.has_payment_method is True
    assert session.space.payment_method_status == "bound"
    assert session.space.payment_method_id == "pm_remote_success"
    assert session.space.payment_method_last_error_code == ""
    assert session.card.card_status == "used"
    assert session.card.reserved_by_space_id is None
    assert session.card.reserved_at is None
    assert session.card.last_error_code == ""
    assert session.commit_calls == 2


def test_payment_method_workflow_preserves_account_deactivated_error_code() -> None:
    attempt = _attempt(1)
    released: list[PersonalPaymentMethodBindError] = []
    deactivated: list[PersonalPaymentMethodBindError] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id):
            return attempt

        def _bind_attempt(self, **_kwargs):
            raise BrowserAccountDeactivatedError(
                "OpenAI browser flow failed: code=account_deactivated"
            )

        def _release_pre_payment_failure(self, *, error, **_kwargs):
            released.append(error)

        def _mark_account_deactivated(self, *, error, **_kwargs):
            deactivated.append(error)

        def _event(self, **_kwargs):
            return None

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError) as raised:
        workflow.run(space_id="space-1")

    assert raised.value.error_code == "account_deactivated"
    assert "account_deactivated" in raised.value.error_message
    assert [error.error_code for error in released] == ["account_deactivated"]
    assert [error.error_code for error in deactivated] == ["account_deactivated"]


def test_payment_method_protocol_marks_wrapped_account_deactivated(monkeypatch) -> None:
    attempt = _attempt(1)
    deactivated: list[PersonalPaymentMethodBindError] = []
    released: list[str] = []

    class Workflow(PersonalPaymentMethodBindWorkflow):
        def _load_context(self, _space_id):
            return _context(), None

        def _reserve_attempt(self, _space_id, **_kwargs):
            return attempt

        def _mark_account_deactivated(self, *, error, **_kwargs):
            deactivated.append(error)

        def _release_pre_payment_failure(self, *, attempt, **_kwargs):
            released.append(attempt.card_id)

        def _record_failure(self, **_kwargs):
            raise AssertionError("deactivated account must not consume a card")

        def _event(self, **_kwargs):
            return None

    monkeypatch.setattr(
        payment_workflow,
        "resolve_cliproxy_proxy",
        lambda *_args, **_kwargs: CliproxyProxy(
            proxy_url="http://proxy.example:8080",
            country_code="US",
        ),
    )
    monkeypatch.setattr(
        payment_workflow,
        "detect_proxy_egress_country",
        lambda _proxy_url: "US",
    )
    monkeypatch.setattr(
        payment_workflow,
        "run_card_payment",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("CardPaymentError: account_deactivated")
        ),
    )
    workflow = Workflow(session_factory=lambda: None, mail_provider=object())

    with pytest.raises(PersonalPaymentMethodBindError) as raised:
        workflow.run(space_id="space-1")

    assert raised.value.error_code == "account_deactivated"
    assert [error.error_code for error in deactivated] == ["account_deactivated"]
    assert released == ["card-1"]


def test_mark_account_deactivated_updates_account_state() -> None:
    class Account:
        account_status = "active"
        session_status = "active"
        last_login_error_code = ""
        last_login_error_message = ""
        updated_at = None

    class Session:
        def __init__(self):
            self.account = Account()
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, model, account_id, *, with_for_update=False):
            assert model is payment_workflow.UserAccountModel
            assert account_id == "account-1"
            assert with_for_update is True
            return self.account

        def commit(self):
            self.committed = True

    session = Session()
    workflow = PersonalPaymentMethodBindWorkflow(
        session_factory=lambda: session,
        mail_provider=object(),
    )

    workflow._mark_account_deactivated(
        context=_context(),
        error=PersonalPaymentMethodBindError(
            "account_deactivated",
            "OpenAI browser flow failed: code=account_deactivated",
        ),
    )

    assert session.account.account_status == "invalid"
    assert session.account.session_status == "dead"
    assert session.account.last_login_error_code == "account_deactivated"
    assert "account_deactivated" in session.account.last_login_error_message
    assert session.account.updated_at is not None
    assert session.committed is True


def _context() -> _BindingContext:
    return _BindingContext(
        space_id="space-1",
        external_space_id="personal-1",
        user_account_id="account-1",
        email="member@outlook.com",
        password="test-password",
        cookie_header="session=cookie",
        auth_cookie_header="auth=cookie",
        mfa_status="not_configured",
        twofauth_account_id="",
        access_token="access-token",
        session_token="session-token",
        device_id="device-1",
        promotion_id="plus-1-month-free",
    )


def _postgresql_sql(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
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
