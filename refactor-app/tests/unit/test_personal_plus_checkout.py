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
    INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT,
    INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT,
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
    solve_plus_checkout_challenge,
    submit_plus_checkout_with_plugin,
    update_plus_checkout_promotion,
)


def test_plus_checkout_defaults_are_configurable() -> None:
    settings = Settings()
    assert settings.personal_plus_checkout_create_proxy_country == "US"
    assert settings.personal_plus_checkout_promo_proxy_country == "JP"
    assert settings.personal_plus_checkout_promo_campaign_id == "plus-1-month-free"
    assert settings.personal_plus_checkout_captcha_api_url == ""
    assert settings.personal_plus_checkout_captcha_client_key == ""


def test_payment_browser_mode_defaults_to_headless_and_supports_headed_override() -> None:
    assert PersonalPaymentMethodBindJobRequest().browser_headless is True
    assert PersonalPaymentMethodBindJobRequest().captcha_api_url == ""
    assert PersonalPaymentMethodBindJobRequest().captcha_client_key == ""
    assert (
        PersonalPaymentMethodBindSelectedJobRequest(space_ids=["space-1"]).browser_headless
        is True
    )
    assert PersonalPlusCheckoutJobRequest().browser_headless is True
    assert PersonalPlusCheckoutJobRequest().captcha_api_url == ""
    assert PersonalPlusCheckoutJobRequest().captcha_client_key == ""
    assert PersonalPlusCheckoutJobRequest(browser_headless=False).browser_headless is False


def test_plus_checkout_scripts_cover_required_request_chain() -> None:
    assert hashlib.sha256(CREATE_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "378d3113da5be44f3ac89251fffa0f10a79052c46005e26f077d1997cc592df3"
    )
    assert hashlib.sha256(SUBMIT_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "ef75edf4edadd71ac9606d951e82d5cbb4502da454f6483ddb6897d674cd0be3"
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
    assert "let approvalPromise = null" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "if (approvalPromise) return approvalPromise" in SUBMIT_PLUS_CHECKOUT_SCRIPT
    assert "submitAttemptCount" in SUBMIT_PLUS_CHECKOUT_SCRIPT
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
    assert "bestChallenge(provider = \"\")" in INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT
    assert "site_key: entry.site_key || current.site_key" in (
        INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT
    )
    assert "const challenge = this.bestChallenge();" in INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT


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


def test_stripe_checkout_polls_without_preterminal_page_reload(
    monkeypatch,
) -> None:
    checkout_url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {"phase": "submitted", "panel_visible": True, "checkout_confirm": None},
        ]
    )
    poll_calls: list[dict] = []

    class Page:
        url = checkout_url
        reload_calls = 0
        submit_calls = 0

        @classmethod
        def evaluate(cls, script):
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
                cls.submit_calls += 1
                return True
            raise AssertionError(f"unexpected script: {script}")

        @classmethod
        def reload(cls, **kwargs):
            cls.reload_calls += 1
            assert kwargs == {"wait_until": "domcontentloaded", "timeout": 30_000}

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda _page, **kwargs: poll_calls.append(kwargs) or {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert Page.submit_calls == 1
    assert Page.reload_calls == 0
    assert "post_submit_refresh" not in result
    assert result["payment_result"] == {"state": "succeeded"}
    assert len(poll_calls) == 1


def test_stripe_checkout_does_not_refresh_after_success_redirect(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {"phase": "submitted", "panel_visible": True, "checkout_confirm": None},
        ]
    )

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"

        @classmethod
        def evaluate(cls, script):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                state = next(states)
                if state["phase"] == "submitted":
                    cls.url = "https://chatgpt.com/?refresh_account=true"
                return state
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            raise AssertionError(f"unexpected script: {script}")

        @staticmethod
        def reload(**_kwargs):
            raise AssertionError("success redirect must not be refreshed")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert "post_submit_refresh" not in result
    assert result["redirect_url"] == "https://chatgpt.com/?refresh_account=true"


def test_stripe_checkout_does_not_reload_before_terminal_poll(
    monkeypatch,
) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {"phase": "submitted", "panel_visible": True, "checkout_confirm": None},
        ]
    )
    submit_calls = {"count": 0}
    poll_calls = {"count": 0}

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"

        @staticmethod
        def evaluate(script):
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
                submit_calls["count"] += 1
                return True
            raise AssertionError(f"unexpected script: {script}")

        @staticmethod
        def reload(**_kwargs):
            raise RuntimeError("reload failed")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: poll_calls.__setitem__("count", poll_calls["count"] + 1)
        or {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert submit_calls["count"] == 1
    assert poll_calls["count"] == 1
    assert "post_submit_refresh" not in result
    assert result["payment_result"] == {"state": "succeeded"}


def test_submitted_checkout_skips_stale_captcha_before_terminal_poll(monkeypatch) -> None:
    checkout_url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {
                "phase": "submitted",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "stale-site-key",
                },
            },
        ]
    )

    class Page:
        url = checkout_url
        reload_calls = 0

        @classmethod
        def evaluate(cls, script):
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
            raise AssertionError(f"unexpected script: {script}")

        @classmethod
        def reload(cls, **kwargs):
            cls.reload_calls += 1
            assert kwargs == {"wait_until": "domcontentloaded", "timeout": 30_000}

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "_maybe_solve_checkout_challenge",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("submitted checkout must not invoke captcha solver")
        ),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert result["phase"] == "submitted"
    assert "post_submit_refresh" not in result
    assert result["payment_result"] == {"state": "succeeded"}
    assert Page.reload_calls == 0


def test_plus_checkout_success_redirect_survives_plugin_state_disposal(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {
                "phase": "confirming_stripe_intent",
                "panel_visible": True,
                "checkout_confirm": {
                    "type": "setup_intent",
                    "client_secret": "seti_secret_1",
                },
            },
            {"phase": "missing", "panel_visible": False, "last_error": ""},
        ]
    )
    poll_calls: list[dict] = []

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1"

        @classmethod
        def evaluate(cls, script):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "oaics",
                    "checkout_session_id": "oaics_checkout_1",
                    "pathname": "/checkout/openai_llc/oaics_checkout_1",
                }
            if script == MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                state = next(states)
                if state["phase"] == "missing":
                    cls.url = (
                        "https://chatgpt.com/checkout/verify?"
                        "stripe_session_id=oaics_checkout_1&plan_type=plus&redirect_status=succeeded"
                    )
                return state
            if script == INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda _page, **kwargs: poll_calls.append(kwargs) or {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert result["phase"] == "submitted"
    assert result["redirect_url"].startswith("https://chatgpt.com/checkout/verify?")
    assert result["checkout_confirm"] == {
        "type": "setup_intent",
        "client_secret": "seti_secret_1",
    }
    assert poll_calls == [
        {
            "provider": "oaics",
            "checkout_session_id": "oaics_checkout_1",
            "checkout_confirm": {
                "type": "setup_intent",
                "client_secret": "seti_secret_1",
            },
            "max_attempts": 30,
            "interval_s": 2.0,
        }
    ]


def test_plus_checkout_success_navigation_during_state_read_is_accepted(monkeypatch) -> None:
    checkout_url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"
    success_url = "https://chatgpt.com/?refresh_account=true"
    state_reads = {"count": 0}

    class Page:
        url = checkout_url

        @classmethod
        def evaluate(cls, script):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                state_reads["count"] += 1
                if state_reads["count"] == 1:
                    return {"phase": "ready", "panel_visible": True}
                cls.url = success_url
                raise RuntimeError(
                    "Page.evaluate: Execution context was destroyed, most likely "
                    "because of a navigation."
                )
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert result["phase"] == "submitted"
    assert result["redirect_url"] == success_url
    assert state_reads["count"] == 2


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
        url = "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1"

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

        @staticmethod
        def reload(**_kwargs):
            raise AssertionError("OAICS checkout must not be refreshed")

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
        "submit_attempts": 1,
        "challenge_attempts": 0,
        "challenge_detected": False,
        "challenge_request_count": 0,
        "challenge_kinds": [],
        "challenge_requests": [],
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


def test_visible_plus_checkout_plugin_solves_captcha_without_resubmit(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    states = iter(
        [
            {"phase": "ready", "panel_visible": True, "challenge_pending": False},
            {
                "phase": "confirming_stripe_intent",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
                    "rqdata": "rqdata-1",
                    "invisible": True,
                    "widget_id": "widget-1",
                },
            },
            {
                "phase": "submit_failed",
                "panel_visible": True,
                "last_error": "captcha token accepted but checkout requires one more submit",
                "challenge_pending": False,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
                    "rqdata": "rqdata-1",
                    "invisible": True,
                    "widget_id": "widget-1",
                    "token_injected": True,
                },
            },
            {
                "phase": "submitted",
                "panel_visible": True,
                "confirm_result": {"payment_intent": "succeeded"},
                "checkout_confirm": {"type": "payment_intent"},
                "challenge_pending": False,
            },
        ]
    )
    solver_payloads: list[dict] = []
    submit_calls = {"count": 0}

    class Page:
        @staticmethod
        def evaluate(script, payload=None):
            calls.append((script, payload))
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "oaics",
                    "checkout_session_id": "oaics_checkout_1",
                    "pathname": "/checkout/openai_llc/oaics_checkout_1",
                }
            if script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT:
                return {"installed_at": "now"}
            if script == MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                submit_calls["count"] += 1
                return True
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                assert payload.items() >= {
                    "provider": "hcaptcha",
                    "token": "captcha-token-1",
                    "site_key": "site-key-1",
                    "widget_id": "widget-1",
                    "resp_key": "",
                }.items()
                assert payload["request_id"]
                return {
                    "ok": True,
                    "provider": "hcaptcha",
                    "field_count": 1,
                    "callback_invoked": True,
                    "token_applied": True,
                }
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    def solver(payload: dict) -> dict:
        solver_payloads.append(payload)
        return {
            "provider": "hcaptcha",
            "token": "captcha-token-1",
        }

    result = submit_plus_checkout_with_plugin(
        Page(),
        captcha_solver=solver,
    )

    assert result["phase"] == "submitted"
    assert result["provider"] == "oaics"
    assert submit_calls["count"] == 1
    assert len(solver_payloads) == 1
    assert solver_payloads[0]["provider"] == "hcaptcha"
    assert solver_payloads[0]["site_key"] == "site-key-1"
    assert any(script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT for script, _ in calls)
    assert any(script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT for script, _ in calls)


def test_stripe_captcha_verification_polls_terminal_without_resubmit(
    monkeypatch,
) -> None:
    checkout_url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"
    success_url = "https://chatgpt.com/checkout/verify?redirect_status=succeeded"
    states = iter(
        [
            {"phase": "ready", "panel_visible": True, "challenge_pending": False},
            {
                "phase": "confirming_stripe_intent",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://js.stripe.com/v3/hcaptcha-inner-fixture.html",
                    "intent_id": "seti_1fixture",
                    "client_secret": "seti_1fixture_secret_fixture",
                    "verify_url": "/v1/setup_intents/seti_1fixture/verify_challenge",
                    "invisible": True,
                },
            },
        ]
    )
    submit_calls = {"count": 0}

    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"id":"seti_1fixture","status":"succeeded"}'

    class Request:
        @staticmethod
        def post(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    class Page:
        url = checkout_url
        context = Context()

        @staticmethod
        def on(_event, _handler):
            return None

        @staticmethod
        def remove_listener(_event, _handler):
            return None

        @classmethod
        def evaluate(cls, script, payload=None):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT:
                return {"installed_at": "now"}
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture UA"
            if script == READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT:
                return '{"ok":true,"phase":"submit_failed"}'
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                submit_calls["count"] += 1
                if submit_calls["count"] == 2:
                    cls.url = success_url
                    raise RuntimeError(
                        "Page.evaluate: Execution context was destroyed, "
                        "most likely because of a navigation."
                    )
                return True
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {
            "state": "succeeded",
            "payment_object_status": "succeeded",
        },
    )

    result = submit_plus_checkout_with_plugin(
        Page(),
        captcha_solver=lambda _payload: {
            "provider": "hcaptcha",
            "token": "captcha-token-1",
        },
    )

    assert result["phase"] == "submitted"
    assert result["payment_result"]["state"] == "succeeded"
    assert result["submit_attempts"] == 1
    assert submit_calls["count"] == 1


def test_verified_stripe_challenge_never_submits_checkout_twice(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True, "challenge_pending": False},
            {
                "phase": "submitting",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "intent_id": "seti_1fixture",
                    "client_secret": "seti_1fixture_secret_fixture",
                    "verify_url": "/v1/setup_intents/seti_1fixture/verify_challenge",
                },
            },
        ]
    )
    submit_calls = {"count": 0}

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"

        @staticmethod
        def on(_event, _handler):
            return None

        @staticmethod
        def remove_listener(_event, _handler):
            return None

        @staticmethod
        def evaluate(script, _payload=None):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT:
                return {"installed_at": "now"}
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                submit_calls["count"] += 1
                if submit_calls["count"] > 1:
                    raise AssertionError("duplicate Checkout submit")
                return True
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "_maybe_solve_checkout_challenge",
        lambda **_kwargs: {
            "identity": "hcaptcha|site-key-1|seti_1fixture",
            "verification": {
                "intent_status": "succeeded",
                "intent_id": "seti_1fixture",
            },
            "solver_task_id": "solver-task-1",
            "requires_resubmit": True,
        },
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {
            "state": "succeeded",
            "payment_object_status": "succeeded",
        },
    )

    result = submit_plus_checkout_with_plugin(
        Page(),
        captcha_solver=lambda _payload: {"token": "unused-by-fixture"},
    )

    assert result["payment_result"]["state"] == "succeeded"
    assert submit_calls["count"] == 1


def test_navigation_context_loss_polls_terminal_state_without_resubmit(monkeypatch) -> None:
    submit_calls = {"count": 0}
    state_reads = iter([{"phase": "ready", "panel_visible": True}])

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"

        @staticmethod
        def on(_event, _handler):
            return None

        @staticmethod
        def remove_listener(_event, _handler):
            return None

        @staticmethod
        def evaluate(script, _payload=None):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(state_reads)
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                submit_calls["count"] += 1
                raise RuntimeError(
                    "Page.evaluate: Execution context was destroyed, most likely "
                    "because of a navigation."
                )
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {
            "state": "succeeded",
            "payment_object_status": "succeeded",
        },
    )

    result = submit_plus_checkout_with_plugin(Page())

    assert result["payment_result"]["state"] == "succeeded"
    assert result["submit_navigation_interrupted"] == 1
    assert submit_calls["count"] == 1


def test_checkout_captcha_bridge_uses_latest_visible_widget_state() -> None:
    assert "invisible: entry.invisible," in INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT
    assert (
        "invisible: current.invisible || entry.invisible,"
        not in INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT
    )


def test_checkout_captcha_rejects_token_not_applied_to_real_widget() -> None:
    calls: list[tuple[str, object]] = []

    class Page:
        @staticmethod
        def evaluate(script, payload=None):
            calls.append((script, payload))
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture UA"
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                return {
                    "ok": False,
                    "provider": "hcaptcha",
                    "field_count": 0,
                    "callback_invoked": False,
                    "token_applied": False,
                    "error": "plus_checkout_captcha_token_not_applied",
                }
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match="plus_checkout_captcha_token_not_applied",
    ):
        checkout_plugin_module._maybe_solve_checkout_challenge(
            page=Page(),
            state={
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "widget_id": "widget-1",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_1",
                },
            },
            challenge_capture=Capture(),
            captcha_solver=lambda _payload: {
                "provider": "hcaptcha",
                "token": "captcha-token-1",
            },
            solved_challenges=set(),
        )

    assert any(script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT for script, _ in calls)


def test_camoufox_async_injection_result_is_polled_until_final_value(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    poll_count = {"value": 0}

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_1"

        @staticmethod
        def evaluate(script, payload=None):
            calls.append((script, payload))
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture UA"
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                # This is the synchronous Camoufox return from scheduling the Promise.
                return '{"started":true,"request_id":"fixture-request"}'
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_ASYNC_RESULT_SCRIPT:
                poll_count["value"] += 1
                if poll_count["value"] == 1:
                    return '{"status":"pending"}'
                return (
                    '{"status":"fulfilled","value":{"ok":true,'
                    '"token_applied":true,"callback_invoked":true}}'
                )
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=Page(),
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "site_key": "site-key-1",
                "widget_id": "widget-1",
                "page_url": Page.url,
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda _payload: {
            "provider": "hcaptcha",
            "token": "captcha-token-1",
        },
        solved_challenges=set(),
    )

    assert outcome is not None
    assert outcome["injection"]["token_applied"] is True
    assert poll_count["value"] == 2


def test_camoufox_empty_async_result_is_recovered_by_terminal_poll() -> None:
    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_1"

        @staticmethod
        def evaluate(script, _payload=None):
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                return {}
            raise AssertionError(f"unexpected script: {script}")

    result = checkout_plugin_module._run_main_world_async(
        Page(),
        start_script=INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT,
        payload={"token": "captcha-token-1"},
    )

    assert result["navigation_interrupted"] is True
    assert result["async_result_missing"] is True


def test_stripe_cross_origin_challenge_uses_verify_challenge_when_callback_is_unavailable(
    monkeypatch,
) -> None:
    requests: list[tuple[str, dict]] = []

    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"id":"seti_1fixture","status":"succeeded"}'

    class Request:
        @staticmethod
        def post(url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    class Context:
        request = Request()

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_1"
        context = Context()

        @staticmethod
        def evaluate(script, payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture UA"
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                return {
                    "ok": False,
                    "provider": "hcaptcha",
                    "field_count": 0,
                    "callback_invoked": False,
                    "token_applied": False,
                }
            if script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT:
                return '{"ok":true,"phase":"submitted"}'
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=Page(),
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "site_key": "site-key-1",
                "widget_id": "widget-1",
                "page_url": "https://js.stripe.com/v3/hcaptcha-inner-fixture.html",
                "intent_id": "seti_1fixture",
                "client_secret": "seti_1fixture_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_1fixture/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda _payload: {
            "provider": "hcaptcha",
            "token": "captcha-token-1",
        },
        solved_challenges=set(),
    )

    assert outcome is not None
    assert outcome["verification"]["intent_status"] == "succeeded"
    assert requests[0][0] == "https://api.stripe.com/v1/setup_intents/seti_1fixture/verify_challenge"
    assert requests[0][1]["form"] == {
        "client_secret": "seti_1fixture_secret_fixture",
        "captcha_vendor_name": "hcaptcha",
        "key": "pk_live_fixture",
        "_stripe_version": checkout_plugin_module._STRIPE_VERSION_FULL,
        "challenge_response_token": "captcha-token-1",
    }


def test_stripe_verify_challenge_continues_requires_action_in_main_world(monkeypatch) -> None:
    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"id":"seti_1fixture","status":"requires_action"}'

    class Request:
        @staticmethod
        def post(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    calls: list[str] = []

    class Page:
        context = Context()

        @staticmethod
        def evaluate(script, payload=None):
            calls.append(script)
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == checkout_plugin_module.CONTINUE_PLUS_CHECKOUT_STRIPE_INTENT_SCRIPT:
                return '{"started":true,"request_id":"fixture"}'
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_ASYNC_RESULT_SCRIPT:
                return '{"status":"fulfilled","value":{"setupIntent":{"status":"succeeded"}}}'
            if script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT:
                return '{"ok":true}'
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    result = checkout_plugin_module._verify_stripe_checkout_challenge(
        Page(),
        challenge={
            "intent_id": "seti_1fixture",
            "client_secret": "seti_1fixture_secret_fixture",
            "verify_url": "/v1/setup_intents/seti_1fixture/verify_challenge",
        },
        token="captcha-token-1",
    )

    assert result["intent_status"] == "succeeded"
    assert checkout_plugin_module.CONTINUE_PLUS_CHECKOUT_STRIPE_INTENT_SCRIPT in calls


def test_stripe_verify_challenge_accepts_success_navigation_during_continuation(
    monkeypatch,
) -> None:
    checkout_url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1"
    success_url = "https://chatgpt.com/?refresh_account=true"

    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"id":"seti_1fixture","status":"requires_action"}'

    class Request:
        @staticmethod
        def post(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    class Page:
        url = checkout_url
        context = Context()

        @classmethod
        def evaluate(cls, script, payload=None):
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == checkout_plugin_module.CONTINUE_PLUS_CHECKOUT_STRIPE_INTENT_SCRIPT:
                return '{"started":true,"request_id":"fixture"}'
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_ASYNC_RESULT_SCRIPT:
                cls.url = success_url
                raise RuntimeError(
                    "Page.evaluate: Execution context was destroyed, "
                    "most likely because of a navigation."
                )
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    result = checkout_plugin_module._verify_stripe_checkout_challenge(
        Page(),
        challenge={
            "intent_id": "seti_1fixture",
            "client_secret": "seti_1fixture_secret_fixture",
            "verify_url": "/v1/setup_intents/seti_1fixture/verify_challenge",
        },
        token="captcha-token-1",
    )

    assert result["intent_status"] == "succeeded"
    assert result["continuation_status"] == "succeeded"
    assert result["redirect_url"] == success_url


def test_visible_plus_checkout_plugin_preserves_captcha_solver_failure(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True, "challenge_pending": False},
            {
                "phase": "confirming_stripe_intent",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
                    "rqdata": "rqdata-1",
                    "invisible": True,
                    "widget_id": "widget-1",
                },
            },
            {
                "phase": "submitted",
                "panel_visible": True,
                "confirm_result": {"payment_intent": "succeeded"},
                "checkout_confirm": {"type": "payment_intent"},
                "challenge_pending": False,
            },
        ]
    )
    solver_payloads: list[dict] = []
    submit_calls = {"count": 0}

    class Page:
        @staticmethod
        def evaluate(script, payload=None):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "oaics",
                    "checkout_session_id": "oaics_checkout_1",
                    "pathname": "/checkout/openai_llc/oaics_checkout_1",
                }
            if script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT:
                return {"installed_at": "now"}
            if script == MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                submit_calls["count"] += 1
                return True
            raise AssertionError(f"unexpected script: {script}")

        @property
        def url(self) -> str:
            return "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1"

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    def solver(payload: dict) -> dict:
        solver_payloads.append(payload)
        raise checkout_plugin_module.PlusCheckoutPluginError(
            "plus_checkout_captcha_poll_failed: HCaptcha failed after 3 attempts: "
            "hCaptcha checkbox frame not found"
        )

    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match="plus_checkout_captcha_poll_failed:.*hCaptcha checkbox frame not found",
    ):
        submit_plus_checkout_with_plugin(
            Page(),
            captcha_solver=solver,
        )

    assert submit_calls["count"] == 1
    assert len(solver_payloads) == 1


def test_checkout_plugin_timeout_preserves_captcha_solver_error(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True, "challenge_pending": False},
            {
                "phase": "confirming_stripe_intent",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_1",
                    "invisible": False,
                    "widget_id": "widget-1",
                },
            },
            {
                "phase": "confirming_stripe_intent",
                "panel_visible": True,
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_1",
                    "invisible": False,
                    "widget_id": "widget-1",
                },
            },
        ]
    )
    monotonic_values = iter([0.0, 0.0, 2.0])

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_1"

        @staticmethod
        def evaluate(script, payload=None):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_1",
                    "pathname": "/checkout/openai_llc/cs_live_1",
                }
            if script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT:
                return {"installed_at": "now"}
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture UA"
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "monotonic",
        lambda: next(monotonic_values),
    )

    def solver(_payload: dict) -> dict:
        raise checkout_plugin_module.PlusCheckoutPluginError(
            "plus_checkout_captcha_create_failed: ERROR_TASK_NOT_SUPPORTED"
        )

    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match=(
            "plus_checkout_captcha_create_failed: ERROR_TASK_NOT_SUPPORTED; "
            "challenge="
        ),
    ):
        submit_plus_checkout_with_plugin(
            Page(),
            timeout_s=1,
            captcha_solver=solver,
        )


def test_checkout_plugin_captures_challenge_requests_without_browser_logging(monkeypatch) -> None:
    states = iter(
        [
            {"phase": "ready", "panel_visible": True},
            {"phase": "submitted", "panel_visible": True},
        ]
    )

    class Request:
        method = "POST"
        url = "https://api.hcaptcha.com/checksiteconfig?sitekey=secret&token=secret"
        resource_type = "xhr"
        failure = ""

    class Response:
        status = 200

        def __init__(self, request):
            self.request = request

    class Page:
        def __init__(self):
            self.handlers = {}

        def on(self, event, handler):
            self.handlers[event] = handler

        def remove_listener(self, event, handler):
            assert self.handlers.get(event) is handler
            del self.handlers[event]

        def evaluate(self, script):
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "stripe",
                    "checkout_session_id": "cs_live_checkout_1",
                    "pathname": "/checkout/openai_llc/cs_live_checkout_1",
                }
            if script == MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                request = Request()
                self.handlers["request"](request)
                self.handlers["response"](Response(request))
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
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    callbacks: list[dict] = []
    result = submit_plus_checkout_with_plugin(
        Page(),
        challenge_callback=callbacks.append,
    )

    assert result["challenge_detected"] is True
    assert result["challenge_request_count"] == 2
    assert result["challenge_kinds"] == ["hcaptcha"]
    assert result["challenge_requests"][0] == {
        "event": "request",
        "kind": "hcaptcha",
        "url": "https://api.hcaptcha.com/checksiteconfig",
        "method": "POST",
        "resource_type": "xhr",
    }
    assert result["challenge_requests"][1]["status"] == 200
    assert len(callbacks) == 1
    assert callbacks[0]["challenge_kinds"] == ["hcaptcha"]


def test_visible_plus_checkout_plugin_uses_console_challenge_fallback(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    states = iter(
        [
            {"phase": "ready", "panel_visible": True, "challenge_pending": False},
            {
                "phase": "submitting",
                "panel_visible": True,
                "challenge_pending": False,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "",
                    "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
                    "rqdata": "",
                    "widget_id": "",
                },
            },
            {
                "phase": "submitted",
                "panel_visible": True,
                "confirm_result": {"payment_intent": "succeeded"},
                "checkout_confirm": {"type": "payment_intent"},
                "challenge_pending": False,
            },
        ]
    )
    solver_payloads: list[dict] = []

    class ConsoleMessage:
        def __init__(self, text: str, url: str) -> None:
            self._text = text
            self._url = url

        def text(self) -> str:
            return self._text

        def location(self) -> dict[str, str]:
            return {"url": self._url}

    class Response:
        status = 200

        @staticmethod
        def text() -> str:
            return '{"id":"seti_1U2D0zC6h1nxGoI3642bZZQN","status":"succeeded"}'

    class Request:
        @staticmethod
        def post(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    class Page:
        context = Context()

        def __init__(self) -> None:
            self.handlers = {}

        def on(self, event, handler):
            self.handlers[event] = handler

        def remove_listener(self, event, handler):
            assert self.handlers.get(event) is handler
            del self.handlers[event]

        @property
        def url(self) -> str:
            return "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1"

        def evaluate(self, script, payload=None):
            calls.append((script, payload))
            if script == READ_PLUS_CHECKOUT_PROVIDER_SCRIPT:
                return {
                    "provider": "oaics",
                    "checkout_session_id": "oaics_checkout_1",
                    "pathname": "/checkout/openai_llc/oaics_checkout_1",
                }
            if script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT:
                self.handlers["console"](
                    ConsoleMessage(
                        'hCaptcha frame https://js.stripe.com/v3/hcaptcha-inner-7130c264741c32724680bb23dfce4f6a.html#intentId=seti_1U2D0zC6h1nxGoI3642bZZQN&clientSecret=seti_1U2D0zC6h1nxGoI3642bZZQN_secret_V2HabaQc7bSKeeoNEVmTWRiiVk8UvRS&locale=en&sitekey=c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a&verifyUrl=%2Fv1%2Fsetup_intents%2Fseti_1U2D0zC6h1nxGoI3642bZZQN%2Fverify_challenge&rqdata=RQTOKEN&size=invisible',
                        'https://js.stripe.com/v3/hcaptcha-inner-7130c264741c32724680bb23dfce4f6a.html',
                    )
                )
                return {"installed_at": "now"}
            if script == MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT:
                return None
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT:
                return '{"ok":true,"phase":"submit_failed"}'
            if script == READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT:
                return next(states)
            if script == INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT:
                return True
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                assert payload.items() >= {
                    "provider": "hcaptcha",
                    "token": "captcha-token-1",
                    "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
                    "widget_id": "",
                    "resp_key": "resp-key-3",
                }.items()
                assert payload["request_id"]
                return {
                    "ok": True,
                    "provider": "hcaptcha",
                    "field_count": 1,
                    "callback_invoked": True,
                    "token_applied": True,
                }
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        checkout_plugin_module,
        "poll_plus_checkout_result",
        lambda *_args, **_kwargs: {"state": "succeeded"},
    )

    def solver(payload: dict) -> dict:
        solver_payloads.append(payload)
        return {
            "provider": "hcaptcha",
            "token": "captcha-token-1",
            "resp_key": "resp-key-3",
        }

    result = submit_plus_checkout_with_plugin(
        Page(),
        captcha_solver=solver,
    )

    assert result["challenge_detected"] is True
    assert result["challenge"]["site_key"] == "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"
    assert result["challenge"]["page_url"].startswith("https://js.stripe.com/v3/hcaptcha-inner-")
    assert len(solver_payloads) == 1
    assert solver_payloads[0]["site_key"] == "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"
    assert solver_payloads[0]["page_url"] == "https://js.stripe.com/"
    assert solver_payloads[0]["challenge_frame_url"].startswith(
        "https://js.stripe.com/v3/hcaptcha-inner-"
    )
    assert any(script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT for script, _ in calls)
    assert any(
        script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT
        for script, _ in calls
    )
    assert not any(script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT for script, _ in calls)


def test_solve_plus_checkout_challenge_uses_remote_provider(monkeypatch) -> None:
    requests: list[tuple[str, dict]] = []

    class Response:
        def __init__(self, payload):
            self._payload = payload
            self.text = __import__("json").dumps(payload)

        def json(self):
            return self._payload

    class Client:
        def post(self, url, **kwargs):
            requests.append((url, kwargs))
            if url.endswith("/createTask"):
                return Response({"errorId": 0, "taskId": 12345})
            if url.endswith("/getTaskResult"):
                return Response(
                    {
                        "errorId": 0,
                        "status": "ready",
                        "solution": {"gRecaptchaResponse": "solver-token-1"},
                    }
                )
            raise AssertionError(url)

        def close(self):
            requests.append(("close", {}))

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", lambda: Client())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    result = solve_plus_checkout_challenge(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-1",
            "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
            "rqdata": "rqdata-1",
            "invisible": True,
        },
        api_url="https://captcha.example",
        client_key="client-key-1",
    )

    assert result["provider"] == "hcaptcha"
    assert result["token"] == "solver-token-1"
    assert requests[0][0] == "https://captcha.example/createTask"
    assert requests[0][1]["json"] == {
        "clientKey": "client-key-1",
        "task": {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
            "websiteKey": "site-key-1",
            "isInvisible": True,
            "rqdata": "rqdata-1",
        },
    }
    assert requests[1][0] == "https://captcha.example/getTaskResult"
    assert requests[-1][0] == "close"


def test_stripe_hcaptcha_uses_captured_wrapper_and_enterprise_task() -> None:
    wrapper_url = (
        "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
        "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
    )
    task = checkout_plugin_module._remote_captcha_task(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-stripe",
            "solver_page_url": wrapper_url,
            "stripe_hcaptcha_wrapper_url": wrapper_url,
            "rqdata": "rqdata-stripe",
            "invisible": True,
            "user_agent": "Fixture UA",
        }
    )

    assert task == {
        "type": "HCaptchaTaskProxyless",
        "websiteURL": wrapper_url,
        "websiteKey": "site-key-stripe",
        "isInvisible": True,
        "isEnterprise": True,
        "userAgent": "Fixture UA",
        "rqdata": "rqdata-stripe",
    }
    assert checkout_plugin_module._remote_captcha_task_variants(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-stripe",
            "solver_page_url": wrapper_url,
            "stripe_hcaptcha_wrapper_url": wrapper_url,
            "invisible": True,
        }
    ) == [
        {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": wrapper_url,
            "websiteKey": "site-key-stripe",
            "isInvisible": True,
            "isEnterprise": True,
        },
        {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": wrapper_url,
            "websiteKey": "site-key-stripe",
            "isInvisible": True,
        },
    ]


def test_checkout_challenge_capture_links_stripe_wrapper_to_site_key() -> None:
    wrapper_url = (
        "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
        "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
    )
    checksiteconfig_url = (
        "https://api.hcaptcha.com/checksiteconfig?sitekey=site-key-stripe"
        "&rqdata=rqdata-stripe&host=b.stripecdn.com"
    )

    class Page:
        def __init__(self) -> None:
            self.handlers: dict[str, list] = {}

        def on(self, event, callback) -> None:
            self.handlers.setdefault(event, []).append(callback)

        def remove_listener(self, event, callback) -> None:
            self.handlers[event].remove(callback)

    class Request:
        method = "GET"
        resource_type = "document"

        def __init__(self, url: str) -> None:
            self.url = url

    page = Page()
    capture = checkout_plugin_module._CheckoutChallengeCapture(page)
    capture.install()
    capture.handlers = page.handlers
    request_handlers = page.handlers["request"]
    request_handlers[0](Request(wrapper_url))
    request_handlers[0](Request(checksiteconfig_url))

    challenge = capture.best_challenge(
        page_url="https://chatgpt.com/checkout/openai_llc/cs_live_fixture"
    )

    assert challenge is not None
    assert challenge["site_key"] == "site-key-stripe"
    assert challenge["rqdata"] == "rqdata-stripe"
    assert challenge["solver_page_url"] == wrapper_url
    assert challenge["stripe_hcaptcha_wrapper_url"] == wrapper_url
    assert challenge["invisible"] is True
    capture.close()


def test_solve_stripe_hcaptcha_falls_back_after_enterprise_task_failure(monkeypatch) -> None:
    requests_seen: list[tuple[int, str, dict]] = []
    clients = []

    class Response:
        def __init__(self, payload):
            self._payload = payload
            self.text = __import__("json").dumps(payload)

        def json(self):
            return self._payload

    class Client:
        def __init__(self, index: int) -> None:
            self.index = index

        def post(self, url, **kwargs):
            requests_seen.append((self.index, url, kwargs))
            if self.index == 1:
                return Response(
                    {
                        "errorId": 1,
                        "errorDescription": "enterprise task unsupported",
                    }
                )
            if url.endswith("/createTask"):
                return Response({"errorId": 0, "taskId": "fallback-task"})
            return Response(
                {
                    "errorId": 0,
                    "status": "ready",
                    "solution": {"hcaptchaToken": "fallback-token"},
                }
            )

        def close(self):
            return None

    def create_client():
        client = Client(len(clients) + 1)
        clients.append(client)
        return client

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", create_client)
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    result = solve_plus_checkout_challenge(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-stripe",
            "solver_page_url": (
                "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
                "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
            ),
            "stripe_hcaptcha_wrapper_url": (
                "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
                "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
            ),
            "invisible": True,
        },
        api_url="https://captcha.example",
        client_key="client-key-1",
    )

    assert result["provider"] == "hcaptcha"
    assert result["token"] == "fallback-token"
    assert result["solver_strategy"] == 2
    assert requests_seen[0][2]["json"]["task"]["isEnterprise"] is True
    assert "isEnterprise" not in requests_seen[1][2]["json"]["task"]


def test_solve_stripe_hcaptcha_reports_all_strategy_failures(monkeypatch) -> None:
    requests_seen: list[dict] = []

    class Response:
        text = '{"errorId":1,"errorDescription":"unsupported"}'

        @staticmethod
        def json():
            return {"errorId": 1, "errorDescription": "unsupported"}

    class Client:
        def post(self, url, **kwargs):
            requests_seen.append(kwargs["json"])
            return Response()

        def close(self):
            return None

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", lambda: Client())

    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match="all task strategies failed",
    ) as raised:
        solve_plus_checkout_challenge(
            {
                "provider": "hcaptcha",
                "site_key": "site-key-stripe",
                "solver_page_url": (
                    "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
                    "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
                ),
                "stripe_hcaptcha_wrapper_url": (
                    "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
                    "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
                ),
                "invisible": True,
            },
            api_url="https://captcha.example",
            client_key="client-key-1",
        )

    assert len(requests_seen) == 2
    assert "enterprise task unsupported" not in str(raised.value)
    assert "unsupported" in str(raised.value)


def test_solve_plus_checkout_challenge_uses_requests_for_http_api(monkeypatch) -> None:
    requests_seen: list[tuple[str, dict]] = []

    class Response:
        def __init__(self, payload):
            self._payload = payload
            self.text = __import__("json").dumps(payload)

        def json(self):
            return self._payload

    class Client:
        def post(self, url, **kwargs):
            requests_seen.append((url, kwargs))
            if url.endswith("/createTask"):
                return Response({"errorId": 0, "taskId": 12345})
            if url.endswith("/getTaskResult"):
                return Response(
                    {
                        "errorId": 0,
                        "status": "ready",
                        "solution": {"hcaptchaToken": "solver-token-2"},
                    }
                )
            raise AssertionError(url)

        def close(self):
            requests_seen.append(("close", {}))

    monkeypatch.setattr(checkout_plugin_module.requests, "Session", lambda: Client())
    monkeypatch.setattr(
        checkout_plugin_module,
        "create_http_session",
        lambda: (_ for _ in ()).throw(AssertionError("create_http_session should not be used")),
    )

    result = solve_plus_checkout_challenge(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-1",
            "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
            "rqdata": "rqdata-1",
            "invisible": True,
        },
        api_url="http://127.0.0.1:18000",
        client_key="client-key-1",
    )

    assert result["token"] == "solver-token-2"
    assert requests_seen[0][0] == "http://127.0.0.1:18000/createTask"
    assert requests_seen[0][1]["json"]["task"]["type"] == "HCaptchaTaskProxyless"
    assert requests_seen[1][0] == "http://127.0.0.1:18000/getTaskResult"
    assert requests_seen[-1][0] == "close"


def test_yescaptcha_visible_hcaptcha_task_matches_documented_fields() -> None:
    task = checkout_plugin_module._remote_captcha_task(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-visible",
            "page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_1",
            "solver_page_url": "https://js.stripe.com/",
            "invisible": False,
            "user_agent": "Fixture UA",
        }
    )

    assert task == {
        "type": "HCaptchaTaskProxyless",
        "websiteURL": "https://js.stripe.com/",
        "websiteKey": "site-key-visible",
        "isInvisible": False,
        "userAgent": "Fixture UA",
    }
    assert "isEnterprise" not in task


def test_solve_plus_checkout_challenge_includes_yescaptcha_hcaptcha_user_agent(monkeypatch) -> None:
    requests_seen: list[tuple[str, dict]] = []

    class Response:
        def __init__(self, payload):
            self._payload = payload
            self.text = __import__("json").dumps(payload)

        def json(self):
            return self._payload

    class Client:
        def post(self, url, **kwargs):
            requests_seen.append((url, kwargs))
            if url.endswith("/createTask"):
                return Response({"errorId": 0, "taskId": 7788})
            if url.endswith("/getTaskResult"):
                return Response(
                    {
                        "errorId": 0,
                        "status": "ready",
                        "solution": {
                            "gRecaptchaResponse": "solver-token-3",
                            "userAgent": "Mozilla/5.0 Example",
                            "respKey": "resp-key-3",
                        },
                    }
                )
            raise AssertionError(url)

        def close(self):
            requests_seen.append(("close", {}))

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", lambda: Client())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    result = solve_plus_checkout_challenge(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-yescaptcha",
            "page_url": "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1",
            "rqdata": "rqdata-yescaptcha",
            "user_agent": "Mozilla/5.0 Example",
        },
        api_url="https://api.yescaptcha.com",
        client_key="client-key-yescaptcha",
    )

    assert requests_seen[0][0] == "https://api.yescaptcha.com/createTask"
    assert requests_seen[0][1]["json"]["task"]["userAgent"] == "Mozilla/5.0 Example"
    assert result["user_agent"] == "Mozilla/5.0 Example"
    assert result["resp_key"] == "resp-key-3"


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


def test_stripe_checkout_result_short_circuits_on_success_redirect(monkeypatch) -> None:
    class Page:
        url = "https://chatgpt.com/payments/success?redirect_status=succeeded"

        @staticmethod
        def evaluate(_script):
            raise AssertionError("success redirect must skip publishable-key lookup")

    result = poll_plus_checkout_result(
        Page(),
        provider="stripe",
        checkout_session_id="cs_live_fixture",
    )

    assert result["state"] == "succeeded"
    assert result["payment_object_status"] == "succeeded"
    assert result["attempts"] == 0
    assert result["response"]["source"] == "success_redirect"
    assert result["response"]["redirect_url"] == Page.url


def test_stripe_checkout_result_accepts_redirect_during_source_read(monkeypatch) -> None:
    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_fixture"

        def evaluate(self, script):
            assert script == READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT
            self.url = "https://chatgpt.com/payments/success?redirect_status=succeeded"
            raise RuntimeError(
                "Page.evaluate: Execution context was destroyed, "
                "most likely because of a navigation."
            )

    page = Page()
    result = poll_plus_checkout_result(
        page,
        provider="stripe",
        checkout_session_id="cs_live_fixture",
    )

    assert result["state"] == "succeeded"
    assert result["payment_object_status"] == "succeeded"
    assert result["attempts"] == 0
    assert result["response"]["source"] == "success_redirect"
    assert result["response"]["redirect_url"] == page.url


def test_stripe_checkout_result_uses_har_fallback_when_live_publishable_key_missing(
    monkeypatch,
) -> None:
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
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_fixture"
        context = Context()

        @staticmethod
        def evaluate(script):
            assert script == READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT
            return {"publishable_key": "", "user_agent": "Fixture UA"}

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
    assert requests[0][1]["params"]["key"] == (
        checkout_plugin_module.HAR_CONFIRMED_PUBLISHABLE_KEY
    )


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


def test_promotion_update_retries_transport_errors_three_times(monkeypatch) -> None:
    captured: dict = {"post_calls": 0, "sessions": 0, "closed": 0, "sleep": []}

    class Response:
        status_code = 200
        text = '{"updated":true}'

        @staticmethod
        def json():
            return {"updated": True}

    class Client:
        def post(self, _url, **_kwargs):
            captured["post_calls"] += 1
            if captured["post_calls"] <= 3:
                raise RuntimeError("TLS connect error: WRONG_VERSION_NUMBER")
            return Response()

        def close(self):
            captured["closed"] += 1

    def create_session(*, proxy):
        assert proxy == "http://jp-proxy.example:8080"
        captured["sessions"] += 1
        return Client()

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", create_session)
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "sleep",
        lambda delay: captured["sleep"].append(delay),
    )

    result = update_plus_checkout_promotion(
        proxy_url="http://jp-proxy.example:8080",
        checkout_url="https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1",
        access_token="access-token",
        account_id="account-1",
        promo_campaign_id="plus-1-month-free",
        cookie_header="session=current",
        retry_attempts=3,
        retry_delay_s=1,
    )

    assert result == {"updated": True}
    assert captured["post_calls"] == 4
    assert captured["sessions"] == 4
    assert captured["closed"] == 4
    assert captured["sleep"] == [1, 1, 1]


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
        lambda page: plugin_calls.append(page)
        or {
            "confirm_result": {"type": "success"},
            "payment_result": {"state": "succeeded"},
        },
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
    settings = Settings()
    settings.personal_plus_checkout_captcha_api_url = "https://captcha.example"
    settings.personal_plus_checkout_captcha_client_key = "client-key-1"

    class PlusWorkflow:
        def __init__(self, **kwargs):
            captured["plus_created"] = kwargs

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
    register_core_handlers(
        runner,
        session_factory=lambda: None,
        settings=settings,
    )

    result = runner._work_handlers["space.personal_payment_method_bind.space"](
        None,
        {"space_id": "space-1"},
    )

    assert captured["plus_created"]["captcha_api_url"] == "https://captcha.example"
    assert captured["plus_created"]["captcha_client_key"] == "client-key-1"
    assert captured["bind_run"]["space_id"] == "space-1"
    assert captured["plus_run"]["space_id"] == "space-1"
    assert result == {"status": "succeeded"}


def test_personal_plus_checkout_tick_job_propagates_settings_captcha_config(monkeypatch) -> None:
    enqueued: list[dict] = []
    settings = Settings()
    settings.personal_plus_checkout_captcha_api_url = "https://captcha.example"
    settings.personal_plus_checkout_captcha_client_key = "client-key-1"

    class FakeQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            enqueued.append(kwargs)

    class FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeSession:
        def scalar(self, _stmt):
            return 0

        def scalars(self, _stmt):
            return FakeScalars(
                [
                    SimpleNamespace(id="space-1"),
                ]
            )

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(handlers, "WorkQueue", FakeQueue)
    monkeypatch.setattr(handlers, "_work_summary", lambda **_kwargs: {})

    result = handlers._run_personal_plus_checkout_tick_job(
        session_factory=lambda: FakeSession(),
        settings=settings,
        input_json={
            "_job_id": "job-1",
            "_run_id": "run-1",
            "space_id": "space-1",
            "limit": 1,
            "work_count": 1,
        },
    )

    assert result["space_id"] == "space-1"
    assert enqueued == [
        {
            "job_id": "job-1",
            "work_type": "space.personal_plus_checkout.space",
            "execution_key": "personal-plus-checkout:space-1",
            "input_json": {
                "space_id": "space-1",
                "create_proxy_country": "US",
                "promo_proxy_country": "JP",
                "promo_campaign_id": "plus-1-month-free",
                "browser_headless": True,
                "captcha_api_url": "https://captcha.example",
                "captcha_client_key": "client-key-1",
                "_run_id": "run-1",
            },
        }
    ]


def test_personal_payment_method_bind_tick_job_propagates_settings_captcha_config(
    monkeypatch,
) -> None:
    enqueued: list[dict] = []
    settings = Settings()
    settings.personal_plus_checkout_captcha_api_url = "https://captcha.example"
    settings.personal_plus_checkout_captcha_client_key = "client-key-1"

    class FakeQueue:
        def __init__(self, _session):
            pass

        def enqueue(self, **kwargs):
            enqueued.append(kwargs)

    class FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeSession:
        def scalar(self, _stmt):
            return 0

        def scalars(self, _stmt):
            return FakeScalars(
                [
                    SimpleNamespace(id="space-1"),
                ]
            )

        def commit(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(handlers, "WorkQueue", FakeQueue)
    monkeypatch.setattr(handlers, "_work_summary", lambda **_kwargs: {})

    result = handlers._run_personal_payment_method_bind_tick_job(
        session_factory=lambda: FakeSession(),
        settings=settings,
        input_json={
            "_job_id": "job-1",
            "_run_id": "run-1",
            "space_id": "space-1",
            "limit": 1,
            "work_count": 1,
            "payment_card_id": "card-1",
        },
    )

    assert result["space_id"] == "space-1"
    assert enqueued == [
        {
            "job_id": "job-1",
            "work_type": "space.personal_payment_method_bind.space",
            "execution_key": "personal-payment-method:space-1",
            "input_json": {
                "space_id": "space-1",
                "auto_start_plus_checkout": True,
                "browser_headless": True,
                "captcha_api_url": "https://captcha.example",
                "captcha_client_key": "client-key-1",
                "payment_card_id": "card-1",
                "_run_id": "run-1",
            },
        }
    ]
