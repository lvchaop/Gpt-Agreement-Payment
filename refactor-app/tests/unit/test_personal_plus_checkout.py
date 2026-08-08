from __future__ import annotations

import hashlib
from types import SimpleNamespace

import refactor_app.application.workflows.personal_plus_checkout as checkout_workflow_module
import refactor_app.plugins.openai_auth_browser.personal_plus_checkout as checkout_plugin_module
from refactor_app.api.routes.resources import (
    PersonalPaymentMethodBindJobRequest,
    PersonalPaymentMethodBindSelectedJobRequest,
    PersonalPlusCheckoutJobRequest,
)
from refactor_app.api.routes.resources import (
    router as resources_router,
)
from refactor_app.application.jobs import handlers
from refactor_app.application.jobs.handlers import register_core_handlers
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.application.workflows.personal_plus_checkout import (
    PersonalPlusCheckoutWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.plugins.openai_auth_browser.personal_plus_checkout import (
    CREATE_PLUS_CHECKOUT_SCRIPT,
    INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT,
    INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT,
    MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT,
    MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT,
    OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT,
    READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
    READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
    READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT,
    READ_PLUS_CHECKOUT_PROVIDER_SCRIPT,
    READ_PLUS_CHECKOUT_SESSION_SCRIPT,
    RETRIEVE_OAICS_STRIPE_INTENT_SCRIPT,
    SUBMIT_PLUS_CHECKOUT_SCRIPT,
    create_plus_checkout_with_script,
    poll_plus_checkout_result,
    submit_plus_checkout_with_plugin,
    update_plus_checkout_promotion,
)


def test_plus_checkout_defaults_are_configurable() -> None:
    settings = Settings()
    assert settings.personal_plus_checkout_create_proxy_country == "US"
    assert settings.personal_plus_checkout_promo_proxy_country == "JP"
    assert settings.personal_plus_checkout_promo_campaign_id == "plus-1-month-free"


def test_payment_browser_mode_defaults_to_headless_and_supports_headed_override() -> None:
    assert PersonalPaymentMethodBindJobRequest().browser_headless is True
    assert (
        PersonalPaymentMethodBindSelectedJobRequest(space_ids=["space-1"]).browser_headless
        is True
    )
    assert PersonalPlusCheckoutJobRequest().browser_headless is True
    assert PersonalPlusCheckoutJobRequest(browser_headless=False).browser_headless is False


def test_plus_checkout_scripts_cover_required_request_chain() -> None:
    assert hashlib.sha256(CREATE_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "378d3113da5be44f3ac89251fffa0f10a79052c46005e26f077d1997cc592df3"
    )
    assert hashlib.sha256(SUBMIT_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "a01869e92762ca72136f49d6b43f23423fab32ee20e34920d9ce8c653e8d8056"
    )
    assert hashlib.sha256(OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "8ee5665f400fdbd38e69d25f327e5918833aeb179ccfd396ef94781ce7c279d1"
    )
    assert "/backend-api/payments/checkout" in CREATE_PLUS_CHECKOUT_SCRIPT
    assert "checkout_ui_mode" in CREATE_PLUS_CHECKOUT_SCRIPT
    assert "/api/auth/session" in READ_PLUS_CHECKOUT_SESSION_SCRIPT
    assert "/backend-api/payments/checkout/update" not in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "promo_campaign_id" not in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "initCheckout" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "checkout.confirm" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "/backend-api/payments/checkout/approve" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert 'const PaymentMethodsPath = "/backend-api/payments/payment_methods"' in (
        SUBMIT_PLUS_CHECKOUT_SCRIPT
    )
    assert "?account_id=${encodeURIComponent(accountId)}" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "const serialized = JSON.parse(" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "decodeReactRouterTable(serialized)" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "/backend-api/payments/checkout/confirm" in OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "customer_session_client_secret" in OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "confirmation_tokens" in OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "stripe.confirmPayment" in OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT


def test_visible_plus_checkout_plugin_waits_until_ready_before_submit(monkeypatch) -> None:
    calls: list[str] = []
    poll_calls: list[tuple[object, dict]] = []
    states = iter(
        [
            {"phase": "loading", "panel_visible": True},
            {"phase": "ready", "panel_visible": True},
            {"phase": "submitting", "panel_visible": True},
            {
                "phase": "submitted",
                "panel_visible": True,
                "confirm_result": {"type": "success"},
                "checkout_confirm": None,
            },
        ]
    )

    class Page:
        @staticmethod
        def evaluate(script):
            calls.append(script)
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            raise AssertionError("unexpected script")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda page, **kwargs: poll_calls.append((page, kwargs)) or {"state": "succeeded"},
    )

    page = Page()
    result = submit_plus_checkout_with_plugin(page)

    assert result["phase"] == "submitted"
    assert result["provider"] == "stripe"
    assert result["checkout_session_id"] == "cs_live_checkout_1"
    assert result["payment_result"] == {"state": "succeeded"}
    assert poll_calls == [
        (
            page,
            {
                "provider": "stripe",
                "checkout_session_id": "cs_live_checkout_1",
                "checkout_confirm": None,
                "max_attempts": 30,
                "interval_s": 2.0,
            },
        )
    ]
    assert calls == [
        READ_PLUS_CHECKOUT_PROVIDER_SCRIPT,
        MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT,
        READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
        READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
        INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT,
        READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
        READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
    ]


def test_visible_plus_checkout_plugin_dispatches_oaics_adapter(monkeypatch) -> None:
    calls: list[str] = []
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {
                "phase": "submitted",
                "panel_visible": True,
                "confirm_result": {"payment_intent": "succeeded"},
                "checkout_confirm": {"type": "payment_intent"},
            },
        ]
    )

    class Page:
        @staticmethod
        def evaluate(script):
            calls.append(script)
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "oaics",
                    "checkout_session_id": "oaics_checkout_1",
                    "pathname": "/checkout/openai_llc/oaics_checkout_1",
                }
            if script == MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            raise AssertionError("unexpected script")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert result == {
        "provider": "oaics",
        "checkout_session_id": "oaics_checkout_1",
        "phase": "submitted",
        "confirm_result": {"payment_intent": "succeeded"},
        "checkout_confirm": {"type": "payment_intent"},
        "payment_result": {"state": "succeeded"},
    }
    assert calls == [
        READ_PLUS_CHECKOUT_PROVIDER_SCRIPT,
        MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT,
        READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
        INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT,
        READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT,
    ]


def test_visible_plus_checkout_plugin_reports_async_submit_failure(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {
                "phase": "submit_failed",
                "panel_visible": True,
                "last_error": "Stripe confirmation_tokens failed (403, code=not_allowed)",
            },
        ]
    )

    class Page:
        @staticmethod
        def evaluate(script):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "oaics",
                    "checkout_session_id": "oaics_checkout_1",
                    "pathname": "/checkout/openai_llc/oaics_checkout_1",
                }
            if script == MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            raise AssertionError("unexpected script")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match=r"plus_checkout_plugin_submit_failed: Stripe confirmation_tokens failed \(403",
    ):
        submit_plus_checkout_with_plugin(Page())


def test_stripe_checkout_result_polls_until_succeeded(monkeypatch) -> None:
    responses = iter(
        [
            {"state": "processing", "payment_object_status": "processing"},
            {"state": "succeeded", "payment_object_status": "succeeded"},
        ]
    )
    requests: list[tuple[str, dict]] = []

    class Response:
        status = 200

        def text(self):
            return __import__("json").dumps(next(responses))

    class Request:
        @staticmethod
        def get(url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    class Context:
        request = Request()

    class Page:
        context = Context()

        @staticmethod
        def evaluate(script, payload=None):
            assert script == READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT
            assert payload is None
            return {"publishable_key": "pk_live_fixture", "user_agent": "Fixture UA"}

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    result = poll_plus_checkout_result(
        Page(),
        provider="stripe",
        checkout_session_id="cs_live_fixture",
    )

    assert result["state"] == "succeeded"
    assert result["payment_object_status"] == "succeeded"
    assert result["attempts"] == 2
    assert len(requests) == 2
    assert requests[0][0] == ("https://api.stripe.com/v1/payment_pages/cs_live_fixture/poll")
    assert requests[0][1]["params"] == {
        "key": "pk_live_fixture",
        "_stripe_version": (
            "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1"
        ),
    }
    assert requests[0][1]["headers"]["origin"] == "https://js.stripe.com"
    assert requests[0][1]["headers"]["user-agent"] == "Fixture UA"


def test_stripe_checkout_result_stops_on_terminal_failure(monkeypatch) -> None:
    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"state":"failed","payment_object_status":"requires_payment_method"}'

    class Request:
        @staticmethod
        def get(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    class Page:
        context = Context()

        @staticmethod
        def evaluate(_script):
            return {"publishable_key": "pk_live_fixture", "user_agent": "Fixture UA"}

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    try:
        poll_plus_checkout_result(
            Page(),
            provider="stripe",
            checkout_session_id="cs_live_fixture",
        )
    except checkout_plugin_module.PlusCheckoutPluginError as error:
        assert "plus_checkout_payment_failed" in str(error)
        assert '"state":"failed"' in str(error)
    else:
        raise AssertionError("terminal Stripe failure must fail the checkout")


def test_oaics_checkout_result_retrieves_intent_until_succeeded(monkeypatch) -> None:
    results = iter(
        [
            {"intent_type": "payment_intent", "id": "pi_1", "status": "processing"},
            {"intent_type": "payment_intent", "id": "pi_1", "status": "succeeded"},
        ]
    )
    payloads: list[dict] = []

    class Page:
        @staticmethod
        def evaluate(script, payload):
            assert script == RETRIEVE_OAICS_STRIPE_INTENT_SCRIPT
            payloads.append(payload)
            return next(results)

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    result = poll_plus_checkout_result(
        Page(),
        provider="oaics",
        checkout_session_id="oaics_fixture",
        checkout_confirm={
            "type": "payment_intent",
            "client_secret": "pi_1_secret_fixture",
        },
    )

    assert result["state"] == "succeeded"
    assert result["attempts"] == 2
    assert payloads == [
        {"intentType": "payment_intent", "clientSecret": "pi_1_secret_fixture"},
        {"intentType": "payment_intent", "clientSecret": "pi_1_secret_fixture"},
    ]


def test_stripe_checkout_result_times_out_with_last_response(monkeypatch) -> None:
    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"state":"processing","payment_object_status":"processing"}'

    class Request:
        @staticmethod
        def get(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    class Page:
        context = Context()

        @staticmethod
        def evaluate(_script):
            return {"publishable_key": "pk_live_fixture", "user_agent": "Fixture UA"}

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    try:
        poll_plus_checkout_result(
            Page(),
            provider="stripe",
            checkout_session_id="cs_live_fixture",
            max_attempts=2,
        )
    except checkout_plugin_module.PlusCheckoutPluginError as error:
        assert "plus_checkout_payment_poll_timeout" in str(error)
        assert '"attempt":2' in str(error)
        assert '"state":"processing"' in str(error)
    else:
        raise AssertionError("non-terminal Stripe state must time out")


def test_shared_checkout_creator_treats_session_id_as_opaque() -> None:
    checkout = {
        "ok": True,
        "http_status": 200,
        "checkout_session_id": "opaque-session-id-123",
        "processor_entity": "openai_llc",
        "checkout_url": "https://chatgpt.com/checkout/openai_llc/opaque-session-id-123",
    }

    class Page:
        navigations: list[tuple[str, dict]] = []

        @classmethod
        def goto(cls, url, **kwargs):
            cls.navigations.append((url, kwargs))

        @staticmethod
        def evaluate(script, payload=None):
            if script == f"mw:{READ_PLUS_CHECKOUT_SESSION_SCRIPT}":
                assert payload == {"expectedAccountId": "account-1"}
                return {"account_id": "account-1", "access_token": "token"}
            if script == checkout_plugin_module._CLEAR_PLUS_CHECKOUT_CREATE_RESULT_SCRIPT:
                return True
            if script == checkout_plugin_module._RUN_PLUS_CHECKOUT_CREATE_SCRIPT:
                return None
            if script == checkout_plugin_module._READ_PLUS_CHECKOUT_CREATE_RESULT_SCRIPT:
                return checkout
            raise AssertionError("unexpected browser script")

    assert (
        create_plus_checkout_with_script(
            Page(),
            expected_account_id="account-1",
        )
        == checkout
    )
    assert Page.navigations == [
        ("https://chatgpt.com/", {"wait_until": "load", "timeout": 120_000})
    ]


def test_promotion_update_uses_configured_proxy_for_one_request(monkeypatch) -> None:
    captured: dict = {"post_calls": []}

    class Response:
        status_code = 200
        text = '{"updated":true}'

        @staticmethod
        def json():
            return {"updated": True}

    class Client:
        def post(self, url, **kwargs):
            captured["post_calls"].append((url, kwargs))
            return Response()

        def close(self):
            captured["closed"] = True

    def create_session(*, proxy):
        captured["proxy"] = proxy
        return Client()

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", create_session)

    result = update_plus_checkout_promotion(
        proxy_url="http://jp-proxy.example:8080",
        checkout_url="https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1",
        access_token="access-token",
        account_id="account-1",
        promo_campaign_id="plus-1-month-free",
        cookie_header="session=current",
        user_agent="Browser UA",
    )

    assert result == {"updated": True}
    assert captured["proxy"] == "http://jp-proxy.example:8080"
    assert captured["closed"] is True
    assert len(captured["post_calls"]) == 1
    url, request = captured["post_calls"][0]
    assert url == "https://chatgpt.com/backend-api/payments/checkout/update"
    assert request["headers"]["cookie"] == "session=current"
    assert request["headers"]["authorization"] == "Bearer access-token"
    assert request["json"]["promo_campaign"]["promo_campaign_id"] == "plus-1-month-free"


def test_existing_us_page_only_routes_promotion_update_through_jp(monkeypatch) -> None:
    evaluations: list[tuple[str, object]] = []
    navigations: list[tuple[str, dict]] = []
    promotion_calls: list[dict] = []
    plugin_calls: list[object] = []
    create_calls: list[tuple[object, str]] = []

    class BrowserContext:
        @staticmethod
        def cookies(urls):
            assert urls == ["https://chatgpt.com"]
            return [
                {"name": "session", "value": "fresh-cookie"},
                {"name": "__Secure-next-auth.session-token", "value": "fresh-token"},
            ]

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def get(model, _id):
            if model is checkout_workflow_module.UserAccountModel:
                return SimpleNamespace(
                    access_token="",
                    session_token="",
                    cookie_header="",
                    device_id="",
                    csrf_token="",
                    session_status="unknown",
                    last_session_refresh_at=None,
                    last_login_error_code="old",
                    last_login_error_message="old",
                    updated_at=None,
                )
            raise AssertionError(model)

        @staticmethod
        def commit():
            return None

    class Page:
        context = BrowserContext()
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"

        @staticmethod
        def goto(url, **kwargs):
            navigations.append((url, kwargs))

        @staticmethod
        def evaluate(script, payload=None):
            evaluations.append((script, payload))
            if script == READ_PLUS_CHECKOUT_SESSION_SCRIPT:
                return {
                    "access_token": "current-access-token",
                    "account_id": "account-1",
                    "user_agent": "Current Browser UA",
                }
            raise AssertionError("unexpected browser script")

    def resolve_proxy(*, email, country_code):
        assert email == "person@example.com"
        assert country_code in {"US", "JP"}
        return SimpleNamespace(
            proxy_url=(
                "http://us-proxy.example:8080"
                if country_code == "US"
                else "http://jp-proxy.example:8080"
            ),
            country_code=country_code,
            sid_source="email_sha256",
            probe_attempts=1,
        )

    def promotion_updater(**kwargs):
        promotion_calls.append(kwargs)
        return {"updated": True}

    monkeypatch.setattr(checkout_workflow_module, "resolve_cliproxy_proxy", resolve_proxy)
    monkeypatch.setattr(
        checkout_workflow_module,
        "create_plus_checkout_with_script",
        lambda page, *, expected_account_id: (
            create_calls.append((page, expected_account_id))
            or {
                "checkout_url": "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1",
                "checkout_session_id": "cs_live_checkout_1",
            }
        ),
    )
    monkeypatch.setattr(
        checkout_workflow_module,
        "submit_plus_checkout_with_plugin",
        lambda page: plugin_calls.append(page) or {"confirm_result": {"type": "success"}},
    )
    monkeypatch.setattr(
        checkout_workflow_module.BackfillSessionWorkflow,
        "run",
        lambda _self, **_kwargs: {"status": "refreshed"},
    )

    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=Session,
        mail_provider=object(),
        promotion_updater=promotion_updater,
    )
    monkeypatch.setattr(
        workflow,
        "_load_context",
        lambda *_args, **_kwargs: {
            "user_account_id": "user-account-1",
            "email": "person@example.com",
            "external_space_id": "account-1",
            "cookie_header": "session=stale-cookie",
            "auth_cookie_header": "auth=session",
        },
    )

    result = workflow.run_on_existing_page(space_id="space-1", page=Page())

    assert [script for script, _payload in evaluations] == [
        READ_PLUS_CHECKOUT_SESSION_SCRIPT,
        READ_PLUS_CHECKOUT_SESSION_SCRIPT,
    ]
    assert len(create_calls) == 1
    assert create_calls[0][1] == "account-1"
    assert len(plugin_calls) == 1
    assert navigations == [
        (
            "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1",
            {"wait_until": "load", "timeout": 120_000},
        ),
        (
            "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1",
            {"wait_until": "load", "timeout": 120_000},
        ),
    ]
    assert len(promotion_calls) == 1
    assert promotion_calls[0]["proxy_url"] == "http://jp-proxy.example:8080"
    assert promotion_calls[0]["cookie_header"] == (
        "session=fresh-cookie; __Secure-next-auth.session-token=fresh-token"
    )
    assert promotion_calls[0]["access_token"] == "current-access-token"
    assert result["create_proxy_country"] == "US"
    assert result["promo_proxy_country"] == "JP"
    assert result["checkout_result"]["promo_update"] == {"updated": True}
    assert result["checkout_result"]["session_after_payment"]["status"] == "succeeded"
    assert result["checkout_result"]["confirm_result"] == {"type": "success"}


def test_subscription_sync_uses_refreshed_session_and_writes_snapshot() -> None:
    account = SimpleNamespace(
        access_token="fresh-personal-token",
        cookie_header="session=fresh-cookie",
        auth_cookie_header="auth-cookie",
    )
    space = SimpleNamespace(
        external_space_id="personal-account-1",
        plan_type="free",
        seats_entitled=0,
        seat_limit=0,
        seats_in_use=0,
        raw_space_json={},
        last_subscription_sync_at=None,
        updated_at=None,
    )

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, model, _id):
            if model is checkout_workflow_module.UserAccountModel:
                return account
            if model is checkout_workflow_module.SpaceModel:
                return space
            raise AssertionError(model)

        def commit(self):
            return None

    class Provider:
        def __init__(self):
            self.calls = []

        def fetch_subscription(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "plan_type": "plus",
                "seats_entitled": 1,
                "seats_in_use": 1,
                "subscription_id": "sub-1",
            }

    provider = Provider()
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=Session,
        mail_provider=object(),
        openai_provider=provider,
    )

    result = workflow._sync_subscription_snapshot(
        space_id="space-1",
        user_account_id="user-1",
        proxy_url="http://us-proxy.example:8080",
        run_id="",
        work_id="work-1",
    )

    assert result["status"] == "succeeded"
    assert provider.calls == [
        {
            "access_token": "fresh-personal-token",
            "account_id": "personal-account-1",
            "cookie_header": "session=fresh-cookie",
            "proxy_url": "http://us-proxy.example:8080",
        }
    ]
    assert space.plan_type == "plus"
    assert space.seats_entitled == 1
    assert space.seat_limit == 1
    assert space.seats_in_use == 1
    assert space.raw_space_json["subscription_id"] == "sub-1"
    assert space.last_subscription_sync_at is not None


def test_plus_checkout_job_route_is_registered() -> None:
    paths = {route.path for route in resources_router.routes if hasattr(route, "path")}
    assert "/spaces/{space_id}/plus-checkout-job" in paths


def test_plus_checkout_job_and_work_handlers_are_registered() -> None:
    runner = JobRunner(lambda: None)  # registration does not open a session
    register_core_handlers(runner, session_factory=lambda: None, settings=Settings())
    assert "space.personal_plus_checkout.tick" in runner._handlers
    assert "space.personal_plus_checkout.space" in runner._work_handlers


def test_payment_method_work_handler_defaults_to_existing_page_plus_checkout(monkeypatch) -> None:
    captured: dict = {}

    class PlusWorkflow:
        def __init__(self, **_kwargs):
            captured["plus_created"] = True

        def run_on_existing_page(self, **kwargs):
            captured["plus_run"] = kwargs
            return {"status": "succeeded"}

    class BindWorkflow:
        def __init__(self, *, after_bind_success=None, **_kwargs):
            captured["after_bind_success"] = after_bind_success

        def run(self, **kwargs):
            captured["bind_run"] = kwargs
            return captured["after_bind_success"](
                kwargs["space_id"],
                object(),
                object(),
            )

    monkeypatch.setattr(handlers, "PersonalPlusCheckoutWorkflow", PlusWorkflow)
    monkeypatch.setattr(handlers, "PersonalPaymentMethodBindWorkflow", BindWorkflow)
    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())
    monkeypatch.setattr(handlers, "_twofauth_otp_resolver", lambda _settings: None)
    runner = JobRunner(lambda: None)
    register_core_handlers(runner, session_factory=lambda: None, settings=Settings())

    result = runner._work_handlers["space.personal_payment_method_bind.space"](
        None,
        {"space_id": "space-1"},
    )

    assert captured["plus_created"] is True
    assert captured["bind_run"]["space_id"] == "space-1"
    assert captured["plus_run"]["space_id"] == "space-1"
    assert result == {"status": "succeeded"}
