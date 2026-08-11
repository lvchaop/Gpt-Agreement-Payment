from __future__ import annotations

import binascii
import hashlib
import struct
import zlib
from types import SimpleNamespace

import pytest

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
from refactor_app.plugins.openai_auth_browser import (
    personal_plus_checkout_submit as checkout_submit_module,
)
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
    settings = Settings(_env_file=None)
    assert settings.personal_plus_checkout_create_proxy_country == "US"
    assert settings.personal_plus_checkout_promo_proxy_country == "JP"
    assert settings.personal_plus_checkout_promo_campaign_id == "plus-1-month-free"
    assert settings.personal_plus_checkout_captcha_api_url == ""
    assert settings.personal_plus_checkout_captcha_client_key == ""


def test_payment_browser_mode_defaults_to_headless_and_supports_headed_override() -> None:
    bind_request = PersonalPaymentMethodBindJobRequest()
    selected_request = PersonalPaymentMethodBindSelectedJobRequest(space_ids=["space-1"])
    checkout_request = PersonalPlusCheckoutJobRequest()

    assert bind_request.browser_headless is True
    assert bind_request.browser_log_enabled is False
    assert bind_request.browser_log_capture_bodies is False
    assert bind_request.captcha_api_url == ""
    assert bind_request.captcha_client_key == ""
    assert selected_request.browser_headless is True
    assert selected_request.browser_log_enabled is False
    assert selected_request.browser_log_capture_bodies is False
    assert checkout_request.browser_headless is True
    assert checkout_request.browser_log_enabled is False
    assert checkout_request.browser_log_capture_bodies is False
    assert checkout_request.captcha_api_url == ""
    assert checkout_request.captcha_client_key == ""
    assert PersonalPlusCheckoutJobRequest(browser_headless=False).browser_headless is False


def test_plus_checkout_scripts_cover_required_request_chain() -> None:
    assert hashlib.sha256(CREATE_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "378d3113da5be44f3ac89251fffa0f10a79052c46005e26f077d1997cc592df3"
    )
    assert hashlib.sha256(SUBMIT_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "43d6e5cd4c6258927db3207098be4e966891d2024a3ad0db8bbc4844a50dc780"
    )
    assert hashlib.sha256(OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT.encode()).hexdigest() == (
        "9119e066957b24c30666d21d8aa9d5957773202ebcb958f56fec479b002e2d05"
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


def test_pending_browser_interaction_respects_checkout_submit_deadline(
    monkeypatch,
) -> None:
    submitter = checkout_submit_module.StablePlusCheckoutSubmitter.__new__(
        checkout_submit_module.StablePlusCheckoutSubmitter
    )
    submitter.timeout_s = 1.0
    solve_calls = {"count": 0}
    finish_calls: list[dict] = []

    submitter._start_once = lambda _ready_state: True
    submitter._read_state = lambda _previous: {
        "phase": "confirming_stripe_intent",
        "challenge_pending": True,
    }

    def solve_once(_state):
        solve_calls["count"] += 1
        if solve_calls["count"] > 1:
            raise AssertionError("deadline must stop the pending interaction loop")
        return {
            "browser_interaction": {
                "status": "pending",
                "method": "checkbox",
                "retry": True,
            }
        }

    submitter._solve_challenge = solve_once
    submitter._finish_at_submit_deadline = lambda state: (
        finish_calls.append(dict(state))
        or {"phase": "submitted", "payment_result": {"state": "succeeded"}}
    )
    clock = iter((100.0, 101.0))
    monkeypatch.setattr(
        checkout_submit_module.time,
        "monotonic",
        lambda: next(clock),
    )

    result = submitter._wait_terminal({"phase": "ready", "panel_visible": True})

    assert result == {
        "phase": "submitted",
        "payment_result": {"state": "succeeded"},
    }
    assert solve_calls["count"] == 1
    assert finish_calls == [
        {
            "phase": "confirming_stripe_intent",
            "challenge_pending": True,
        }
    ]


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
                    "type": "setup_intent",
                    "status": "requires_action",
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
    traces: list[tuple[str, dict, str]] = []

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
                "type": "setup_intent",
                "status": "requires_action",
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
            "task_id": "solver-task-1",
            "user_agent": "YesCaptcha Returned UA",
        },
        solved_challenges=set(),
        trace_emitter=lambda event_type, data, level: traces.append(
            (event_type, data, level)
        ),
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
    assert requests[0][1]["headers"] == {
        "accept": "application/json",
        "user-agent": "YesCaptcha Returned UA",
    }
    assert [event_type for event_type, _data, _level in traces] == [
        "challenge.browser.checkbox_unavailable",
        "challenge.solver.succeeded",
        "challenge.route.selected",
        "challenge.stripe_source.started",
        "challenge.stripe_source.succeeded",
        "challenge.stripe_verify.started",
        "challenge.stripe_verify.response",
    ]
    assert traces[1][1]["solver_task_id"] == "solver-task-1"
    assert traces[1][1]["solver_user_agent_present"] is True
    assert traces[1][1]["solver_user_agent_changed"] is True
    assert traces[2][1]["route"] == "stripe_verify"
    assert traces[5][1]["user_agent_override"] is True
    assert traces[-1][1]["status_code"] == 200
    assert traces[-1][1]["intent_status"] == "succeeded"


def test_stripe_verify_challenge_logs_top_level_error_response() -> None:
    traces: list[tuple[str, dict, str]] = []

    class Response:
        status = 400

        @staticmethod
        def text():
            return (
                '{"error":{"type":"invalid_request_error",'
                '"code":"parameter_missing",'
                '"decline_code":"",'
                '"param":"challenge_response_ekey",'
                '"message":"Missing required param: challenge_response_ekey."}}'
            )

    class Request:
        @staticmethod
        def post(_url, **_kwargs):
            return Response()

    class Context:
        request = Request()

    class Page:
        context = Context()

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            raise AssertionError(f"unexpected script: {script}")

    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError
    ) as caught:
        checkout_plugin_module._verify_stripe_checkout_challenge(
            Page(),
            challenge={
                "intent_id": "seti_1fixture",
                "client_secret": "seti_1fixture_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_1fixture/verify_challenge",
            },
            token="captcha-token-1",
            trace_emitter=lambda event_type, data, level: traces.append(
                (event_type, data, level)
            ),
        )

    response_trace = traces[-1]
    assert response_trace[0] == "challenge.stripe_verify.response"
    assert response_trace[1]["status_code"] == 400
    assert response_trace[1]["response_keys"] == ["error"]
    assert response_trace[1]["error_type"] == "invalid_request_error"
    assert response_trace[1]["error_code"] == "parameter_missing"
    assert response_trace[1]["error_param"] == "challenge_response_ekey"
    assert response_trace[1]["error_message"] == (
        "Missing required param: challenge_response_ekey."
    )
    assert response_trace[2] == "ERROR"
    assert '"code":"parameter_missing"' in str(caught.value)
    assert '"param":"challenge_response_ekey"' in str(caught.value)


def test_stripe_challenge_uses_checkout_confirm_when_frame_context_is_missing() -> None:
    requests: list[tuple[str, dict]] = []
    calls: list[tuple[str, object]] = []
    traces: list[tuple[str, dict, str]] = []

    class Response:
        status = 200

        @staticmethod
        def text():
            return '{"id":"pi_1fixture","status":"succeeded"}'

    class Request:
        @staticmethod
        def post(url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    class Context:
        request = Request()

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/oaics_checkout_1"
        context = Context()

        @staticmethod
        def evaluate(script, payload=None):
            calls.append((script, payload))
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture UA"
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT:
                return '{"ok":true,"phase":"submitted"}'
            if script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT:
                raise AssertionError("Stripe iframe challenge must not use page callback injection")
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
                "page_url": "https://js.stripe.com/v3/hcaptcha-inner-fixture.html",
            },
            "checkout_confirm": {
                "type": "payment_intent",
                "status": "requires_action",
                "provider": "hcaptcha",
                "client_secret": "pi_1fixture_secret_fixture",
                "site_key": "site-key-1",
                "rqdata": "rqdata-1",
                "verify_url": "/v1/payment_intents/pi_1fixture/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda _payload: {
            "provider": "hcaptcha",
            "token": "captcha-token-1",
        },
        solved_challenges=set(),
        trace_emitter=lambda event_type, data, level: traces.append(
            (event_type, data, level)
        ),
    )

    assert outcome is not None
    assert outcome["verification"]["intent_id"] == "pi_1fixture"
    assert requests == [
        (
            "https://api.stripe.com/v1/payment_intents/pi_1fixture/verify_challenge",
            {
                "form": {
                    "client_secret": "pi_1fixture_secret_fixture",
                    "captcha_vendor_name": "hcaptcha",
                    "key": "pk_live_fixture",
                    "_stripe_version": checkout_plugin_module._STRIPE_VERSION_FULL,
                    "challenge_response_token": "captcha-token-1",
                },
                "headers": {"accept": "application/json"},
                "timeout": 30_000,
            },
        )
    ]
    assert not any(script == INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT for script, _ in calls)
    assert traces[0][0] == "challenge.browser.checkbox_unavailable"
    assert traces[1][0] == "challenge.solver.succeeded"
    assert traces[1][1]["context_source"] == "checkout_confirm"
    assert traces[2][0] == "challenge.route.selected"
    assert traces[2][1]["route"] == "stripe_verify"


def test_stripe_challenge_waits_until_checkout_confirm_context_is_available() -> None:
    solver_calls: list[dict] = []
    traces: list[tuple[str, dict, str]] = []
    capture = checkout_plugin_module._CheckoutChallengeCapture(object())
    for _ in range(2):
        outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
            page=object(),
            state={
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "site_key": "site-key-1",
                    "page_url": "https://js.stripe.com/v3/hcaptcha-inner-fixture.html",
                },
                "checkout_confirm": None,
            },
            challenge_capture=capture,
            captcha_solver=lambda payload: solver_calls.append(payload) or {},
            solved_challenges=set(),
            trace_emitter=lambda event_type, data, level: traces.append(
                (event_type, data, level)
            ),
        )
        assert outcome is None

    assert solver_calls == []
    assert traces == [
        (
            "challenge.route.deferred",
            {
                "provider": "hcaptcha",
                "route": "stripe_verify",
                "reason": "active_stripe_challenge_missing",
            },
            "WARN",
        )
    ]


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


def test_visible_plus_checkout_plugin_records_console_challenge_without_active_intent(
    monkeypatch,
) -> None:
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
    assert solver_payloads == []
    assert any(script == INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT for script, _ in calls)
    assert not any(
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


def test_stripe_hcaptcha_uses_checkout_page_and_documented_task_fields() -> None:
    wrapper_url = (
        "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
        "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
    )
    checkout_url = "https://chatgpt.com/checkout/openai_llc/cs_live_fixture"
    task = checkout_plugin_module._remote_captcha_task(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-stripe",
            "solver_page_url": wrapper_url,
            "stripe_hcaptcha_wrapper_url": wrapper_url,
            "checkout_page_url": checkout_url,
            "rqdata": "rqdata-stripe",
            "invisible": True,
            "user_agent": "Fixture UA",
        }
    )

    assert task == {
        "type": "HCaptchaTaskProxyless",
        "websiteURL": checkout_url,
        "websiteKey": "site-key-stripe",
        "isInvisible": True,
        "userAgent": "Fixture UA",
        "rqdata": "rqdata-stripe",
    }
    assert checkout_plugin_module._remote_captcha_task_variants(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-stripe",
            "solver_page_url": wrapper_url,
            "stripe_hcaptcha_wrapper_url": wrapper_url,
            "checkout_page_url": checkout_url,
            "invisible": True,
        }
    ) == [
        {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": checkout_url,
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


def test_checkout_challenge_capture_reads_stripe_confirm_after_event_limit() -> None:
    client_secret = "pi_1fixture_secret_fixture"

    class Page:
        def __init__(self) -> None:
            self.handlers: dict[str, list] = {}

        def on(self, event, callback) -> None:
            self.handlers.setdefault(event, []).append(callback)

        def remove_listener(self, event, callback) -> None:
            self.handlers[event].remove(callback)

    class Request:
        method = "POST"
        resource_type = "xhr"

        def __init__(self, url: str) -> None:
            self.url = url

    class Response:
        status = 200

        def __init__(self) -> None:
            self.url = "https://api.stripe.com/v1/payment_intents/pi_1fixture/confirm"
            self.request = Request(self.url)

        @staticmethod
        def json():
            return {
                "error": {
                    "payment_intent": {
                        "id": "pi_1fixture",
                        "client_secret": client_secret,
                    }
                }
            }

    page = Page()
    capture = checkout_plugin_module._CheckoutChallengeCapture(page)
    capture.install()
    request_handler = page.handlers["request"][0]
    for index in range(checkout_plugin_module._MAX_CHALLENGE_EVENTS):
        request_handler(Request(f"https://api.hcaptcha.com/challenge/{index}"))

    page.handlers["response"][0](Response())

    assert capture.latest_checkout_confirm() == {
        "type": "payment_intent",
        "client_secret": client_secret,
    }
    snapshot = capture.snapshot()
    assert snapshot["challenge_request_count"] == checkout_plugin_module._MAX_CHALLENGE_EVENTS
    assert snapshot["stripe_confirm_capture_count"] == 1
    assert snapshot["stripe_confirm"] == {
        "type": "payment_intent",
        "intent_id": "pi_1fixture",
    }
    assert client_secret not in str(snapshot)

    hydrated = checkout_plugin_module._hydrate_checkout_challenge_state(
        {
            "phase": "submitting",
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "site_key": "site-key-1",
                "page_url": "https://js.stripe.com/v3/hcaptcha-inner-fixture.html",
            },
            "checkout_confirm": None,
        },
        challenge_capture=capture,
        page_url="https://chatgpt.com/checkout/openai_llc/cs_live_fixture",
    )
    assert hydrated["checkout_confirm"] == {
        "type": "payment_intent",
        "client_secret": client_secret,
    }
    assert checkout_plugin_module._stripe_challenge_context_from_checkout_confirm(
        hydrated["checkout_confirm"]
    ) == {
        "intent_id": "pi_1fixture",
        "client_secret": client_secret,
        "verify_url": "/v1/payment_intents/pi_1fixture/verify_challenge",
    }
    capture.close()


def test_checkout_challenge_capture_ignores_non_confirm_stripe_response() -> None:
    class Request:
        method = "POST"
        url = "https://api.stripe.com/v1/payment_intents/pi_1fixture/retrieve"

    class Response:
        status = 200
        url = Request.url
        request = Request()

        @staticmethod
        def json():
            return {"client_secret": "pi_1fixture_secret_fixture"}

    capture = checkout_plugin_module._CheckoutChallengeCapture(object())
    capture._on_response(Response())

    assert capture.latest_checkout_confirm() is None


def test_passive_payment_page_hcaptcha_does_not_trigger_solver() -> None:
    wrapper_url = (
        "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
        "HCaptchaInvisible.html?id=passive-frame&origin=https%3A%2F%2Fjs.stripe.com"
    )
    checksiteconfig_url = (
        "https://api.hcaptcha.com/checksiteconfig?sitekey=passive-site-key"
        "&rqdata=passive-rqdata&host=b.stripecdn.com"
    )

    class Page:
        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}

        def on(self, event, callback) -> None:
            self.handlers[event] = callback

        def remove_listener(self, event, callback) -> None:
            assert self.handlers[event] is callback
            del self.handlers[event]

    class Request:
        resource_type = "xhr"

        def __init__(self, url: str, *, method: str = "GET") -> None:
            self.url = url
            self.method = method

    class Response:
        status = 200

        def __init__(self) -> None:
            self.url = "https://api.stripe.com/v1/payment_pages/cs_live_passive/confirm"
            self.request = Request(self.url, method="POST")

        @staticmethod
        def json():
            return {
                "status": "open",
                "site_key": "passive-site-key",
                "rqdata": "passive-rqdata",
                "payment_status": "unpaid",
            }

    page = Page()
    capture = checkout_plugin_module._CheckoutChallengeCapture(page)
    capture.install()
    page.handlers["request"](Request(wrapper_url))
    page.handlers["request"](Request(checksiteconfig_url))
    page.handlers["response"](Response())

    hydrated = checkout_plugin_module._hydrate_checkout_challenge_state(
        {
            "phase": "submitting",
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "site_key": "passive-site-key",
                "page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_passive",
            },
            "checkout_confirm": {
                "type": "payment_intent",
                "client_secret": "pi_stale_secret_stale",
            },
        },
        challenge_capture=capture,
        page_url="https://chatgpt.com/checkout/openai_llc/cs_live_passive",
    )
    solver_calls: list[dict] = []
    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=object(),
        state=hydrated,
        challenge_capture=capture,
        captcha_solver=lambda payload: solver_calls.append(payload) or {},
        solved_challenges=set(),
    )

    assert capture.latest_active_stripe_challenge() is None
    assert hydrated["challenge_pending"] is False
    assert solver_calls == []
    assert outcome is None
    capture.close()


def test_payment_page_active_setup_intent_triggers_solver_and_verify() -> None:
    wrapper_url = (
        "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
        "HCaptchaInvisible.html?id=active-frame&origin=https%3A%2F%2Fjs.stripe.com"
    )
    checksiteconfig_url = (
        "https://api.hcaptcha.com/checksiteconfig?sitekey=active-site-key"
        "&rqdata=active-rqdata&host=b.stripecdn.com"
    )
    verify_requests: list[tuple[str, dict]] = []
    solver_payloads: list[dict] = []

    class VerifyResponse:
        status = 200

        @staticmethod
        def text():
            return '{"id":"seti_active","status":"succeeded"}'

    class ApiRequest:
        @staticmethod
        def post(url, **kwargs):
            verify_requests.append((url, kwargs))
            return VerifyResponse()

    class Context:
        request = ApiRequest()

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_active"
        context = Context()

        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}

        def on(self, event, callback) -> None:
            self.handlers[event] = callback

        def remove_listener(self, event, callback) -> None:
            assert self.handlers[event] is callback
            del self.handlers[event]

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Browser Fixture UA"
            if script == checkout_plugin_module.READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT:
                return {"publishable_key": "pk_live_fixture"}
            if script == checkout_plugin_module.MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT:
                return '{"ok":true,"phase":"submitted"}'
            raise AssertionError(f"unexpected script: {script}")

    class BrowserRequest:
        resource_type = "xhr"

        def __init__(self, url: str, *, method: str = "GET") -> None:
            self.url = url
            self.method = method

    class BrowserResponse:
        status = 200

        def __init__(self) -> None:
            self.url = "https://api.stripe.com/v1/payment_pages/cs_live_active"
            self.request = BrowserRequest(self.url, method="GET")

        @staticmethod
        def json():
            return {
                "setup_intent": {
                    "id": "seti_active",
                    "object": "setup_intent",
                    "status": "requires_action",
                    "client_secret": "seti_active_secret_fixture",
                    "next_action": {
                        "type": "use_stripe_sdk",
                        "use_stripe_sdk": {
                            "stripe_js": {
                                "site_key": "active-site-key",
                                "rqdata": "active-rqdata",
                                "verification_url": (
                                    "/v1/setup_intents/seti_active/verify_challenge"
                                ),
                            }
                        },
                    },
                }
            }

    page = Page()
    capture = checkout_plugin_module._CheckoutChallengeCapture(page)
    capture.install()
    page.handlers["request"](BrowserRequest(wrapper_url))
    page.handlers["request"](BrowserRequest(checksiteconfig_url))
    page.handlers["response"](BrowserResponse())
    hydrated = checkout_plugin_module._hydrate_checkout_challenge_state(
        {
            "phase": "submitting",
            "challenge_pending": False,
            "challenge": None,
            "checkout_confirm": None,
        },
        challenge_capture=capture,
        page_url=page.url,
    )

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=page,
        state=hydrated,
        challenge_capture=capture,
        captcha_solver=lambda payload: solver_payloads.append(payload)
        or {
            "provider": "hcaptcha",
            "token": "active-token",
            "task_id": "active-task",
        },
        solved_challenges=set(),
    )

    assert hydrated["challenge_pending"] is True
    assert hydrated["challenge"]["status"] == "requires_action"
    assert hydrated["challenge"]["intent_id"] == "seti_active"
    assert len(solver_payloads) == 1
    assert solver_payloads[0]["site_key"] == "active-site-key"
    assert outcome is not None
    assert outcome["verification"]["intent_status"] == "succeeded"
    assert verify_requests[0][0] == (
        "https://api.stripe.com/v1/setup_intents/seti_active/verify_challenge"
    )
    snapshot = capture.snapshot()
    assert snapshot["stripe_active_challenge_capture_count"] == 1
    assert snapshot["stripe_active_challenge"] == {
        "type": "setup_intent",
        "status": "requires_action",
        "intent_id": "seti_active",
        "site_key_present": True,
        "verify_path": "/v1/setup_intents/seti_active/verify_challenge",
    }
    assert "seti_active_secret_fixture" not in str(snapshot)
    capture.close()


def test_solve_stripe_hcaptcha_uses_single_documented_task(monkeypatch) -> None:
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
                return Response({"errorId": 0, "taskId": "documented-task"})
            return Response(
                {
                    "errorId": 0,
                    "status": "ready",
                    "solution": {"hcaptchaToken": "documented-token"},
                }
            )

        def close(self):
            return None

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", lambda: Client())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    result = solve_plus_checkout_challenge(
        {
            "provider": "hcaptcha",
            "site_key": "site-key-stripe",
            "solver_page_url": (
                "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
                "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
            ),
            "checkout_page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_fixture",
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
    assert result["token"] == "documented-token"
    assert result["solver_strategy"] == 1
    assert len(requests_seen) == 2
    assert requests_seen[0][1]["json"]["task"] == {
        "type": "HCaptchaTaskProxyless",
        "websiteURL": "https://chatgpt.com/checkout/openai_llc/cs_live_fixture",
        "websiteKey": "site-key-stripe",
        "isInvisible": True,
    }


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
                "checkout_page_url": "https://chatgpt.com/checkout/openai_llc/cs_live_fixture",
                "stripe_hcaptcha_wrapper_url": (
                    "https://b.stripecdn.com/stripethirdparty-srv/assets/v33.6/"
                    "HCaptchaInvisible.html?id=frame-1&origin=https%3A%2F%2Fjs.stripe.com"
                ),
                "invisible": True,
            },
            api_url="https://captcha.example",
            client_key="client-key-1",
        )

    assert len(requests_seen) == 1
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
        "websiteURL": "https://chatgpt.com/checkout/openai_llc/cs_live_1",
        "websiteKey": "site-key-visible",
        "isInvisible": False,
        "userAgent": "Fixture UA",
    }
    assert "isEnterprise" not in task


def test_yescaptcha_hcaptcha_rejects_iframe_as_website_url() -> None:
    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match="plus_checkout_captcha_website_url_missing",
    ):
        checkout_plugin_module._remote_captcha_task(
            {
                "provider": "hcaptcha",
                "site_key": "site-key-frame-only",
                "page_url": "https://js.stripe.com/v3/hcaptcha-inner-fixture.html",
                "solver_page_url": "https://b.stripecdn.com/HCaptchaInvisible.html",
                "invisible": True,
            }
        )


def test_yescaptcha_hcaptcha_classification_task_uses_raw_image_base64() -> None:
    task = checkout_plugin_module._remote_captcha_task(
        {
            "browser_classification": True,
            "classification_mode": "grid",
            "classification_queries": [
                "data:image/jpeg;base64,dGlsZS0w",
                "dGlsZS0x",
            ],
            "classification_anchors": ["data:image/jpeg;base64,YW5jaG9y"],
            "classification_question": "Please select every image with a truck",
        }
    )

    assert task == {
        "type": "HCaptchaClassification",
        "queries": ["dGlsZS0w", "dGlsZS0x"],
        "question": "Please select every image with a truck",
        "anchors": ["YW5jaG9y"],
    }


def test_visual_captcha_uses_hcaptcha_classification_task_with_full_canvas_image() -> None:
    task = checkout_plugin_module._remote_captcha_task(
        {
            "browser_classification": True,
            "classification_mode": "visual",
            "classification_queries": [
                "data:image/jpeg;base64,ZnVsbC1jYW52YXM="
            ],
            "classification_anchors": [],
            "classification_question": (
                "Identify all characters that show up more than once"
            ),
        }
    )

    assert task == {
        "type": "HCaptchaClassification",
        "queries": ["ZnVsbC1jYW52YXM="],
        "question": "Identify all characters that show up more than once",
    }


def test_yescaptcha_hcaptcha_classification_accepts_solution_without_token(monkeypatch) -> None:
    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.text = __import__("json").dumps(payload)

        def json(self):
            return self._payload

    class Client:
        calls = 0

        @classmethod
        def post(cls, url, **_kwargs):
            cls.calls += 1
            if url.endswith("/createTask"):
                return Response({"errorId": 0, "taskId": "classification-task-1"})
            return Response(
                {
                    "errorId": 0,
                    "status": "ready",
                    "solution": {
                        "type": "drag",
                        "box": [{"start": [644, 218], "end": [239, 315]}],
                    },
                }
            )

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    result = checkout_plugin_module._solve_remote_captcha_task(
        Client(),
        base_url="https://captcha.example",
        client_key="client-key-1",
        task={
            "type": "HCaptchaClassification",
            "queries": ["aW1hZ2U="],
            "question": "Please drag the icon",
        },
        deadline=checkout_plugin_module.time.monotonic() + 10,
        poll_interval_s=0,
    )

    assert result["token"] == ""
    assert result["task_id"] == "classification-task-1"
    assert result["task_type"] == "HCaptchaClassification"
    assert result["solution"]["type"] == "drag"
    assert Client.calls == 2


def test_image_to_text_click_response_is_parsed_without_token(monkeypatch) -> None:
    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload
            self.text = __import__("json").dumps(payload)

        def json(self):
            return self._payload

    class Client:
        calls = 0

        @classmethod
        def post(cls, url, **_kwargs):
            cls.calls += 1
            if url.endswith("/createTask"):
                return Response({"errorId": 0, "taskId": "image-task-1"})
            return Response(
                {
                    "errorId": 0,
                    "status": "ready",
                    "solution": {
                        "text": __import__("json").dumps(
                            {
                                "captcha_type": "click",
                                "reason": "two repeated characters",
                                "action": "click",
                                "clicks": [
                                    {"x": 360, "y": 225, "label": "first"},
                                    {"x": 1080, "y": 675, "label": "second"},
                                ],
                            }
                        )
                    },
                }
            )

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    result = checkout_plugin_module._solve_remote_captcha_task(
        Client(),
        base_url="https://captcha.example",
        client_key="client-key-1",
        task={"type": "ImageToTextTask", "body": "aW1hZ2U="},
        deadline=checkout_plugin_module.time.monotonic() + 10,
        poll_interval_s=0,
    )

    assert result["token"] == ""
    assert result["task_id"] == "image-task-1"
    assert result["task_type"] == "ImageToTextTask"
    assert result["solution"]["type"] == "click"
    assert result["solution"]["box"] == [
        {"x": 360.0, "y": 225.0},
        {"x": 1080.0, "y": 675.0},
    ]
    assert result["solution"]["_coordinate_space"] == {
        "width": 1440.0,
        "height": 900.0,
    }
    assert Client.calls == 2


def test_hcaptcha_visual_capture_detects_grid_and_splits_tile_images() -> None:
    class Locator:
        def __init__(self, *, image=b"", box=None, text="", visible=True):
            self.image = image
            self.box = box or {"x": 0, "y": 0, "width": 100, "height": 100}
            self.text = text
            self.visible = visible

        def is_visible(self, **_kwargs):
            return self.visible

        def screenshot(self, **_kwargs):
            return self.image

        def bounding_box(self, **_kwargs):
            return dict(self.box)

        def inner_text(self, **_kwargs):
            return self.text

    class Collection:
        def __init__(self, locators):
            self.locators = list(locators)

        def first(self):
            return self.locators[0] if self.locators else Locator(visible=False)

        def count(self):
            return len(self.locators)

        def nth(self, index):
            return self.locators[index]

    class Frame:
        url = "https://newassets.hcaptcha.com/captcha/v1/fixture/hcaptcha.html#frame=challenge"

        def __init__(self):
            self.mapping = {
                "body": Collection(
                    [
                        Locator(
                            image=b"body-image",
                            box={"x": 100, "y": 50, "width": 600, "height": 500},
                            text="Please select every truck Verify",
                        )
                    ]
                ),
                "#prompt-question": Collection(
                    [Locator(text="Please select every truck")]
                ),
                ".task-image": Collection(
                    [Locator(image=b"tile-0"), Locator(image=b"tile-1")]
                ),
                ".task": Collection(
                    [
                        Locator(box={"x": 120, "y": 180, "width": 80, "height": 80}),
                        Locator(box={"x": 220, "y": 180, "width": 80, "height": 80}),
                    ]
                ),
            }

        def locator(self, selector):
            return self.mapping.get(selector, Collection([]))

    snapshot = checkout_plugin_module._capture_hcaptcha_visual(Frame())

    assert snapshot["mode"] == "grid"
    assert snapshot["queries"] == ["dGlsZS0w", "dGlsZS0x"]
    assert snapshot["question"] == "Please select every truck"
    assert snapshot["query_image_size"] == {"width": 600, "height": 500}
    assert snapshot["tile_boxes"] == [
        {"x": 120.0, "y": 180.0, "width": 80.0, "height": 80.0},
        {"x": 220.0, "y": 180.0, "width": 80.0, "height": 80.0},
    ]
    assert "data:image" not in str(snapshot["queries"])


def _fixture_rgba_png(*, ready: bool, width: int = 64, height: int = 64) -> bytes:
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            in_surface = ready and 16 <= x < 48 and 16 <= y < 48
            row.extend((32, 148, 212, 255) if in_surface else (255, 255, 255, 255))
        rows.append(b"\x00" + bytes(row))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = binascii.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        checkout_plugin_module._PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + chunk(b"IEND", b"")
    )


def test_hcaptcha_png_pixel_probe_rejects_blank_surface_and_accepts_loaded_surface() -> None:
    blank = checkout_plugin_module._png_visual_stats(
        _fixture_rgba_png(ready=False),
        focus=checkout_plugin_module._VISUAL_PIXEL_FOCUS,
    )
    loaded = checkout_plugin_module._png_visual_stats(
        _fixture_rgba_png(ready=True),
        focus=checkout_plugin_module._VISUAL_PIXEL_FOCUS,
    )

    assert blank is not None
    assert blank["ready"] is False
    assert blank["non_blank_ratio"] == 0.0
    assert loaded is not None
    assert loaded["ready"] is True
    assert loaded["non_blank_ratio"] > 0.5


def test_hcaptcha_visual_capture_rejects_blank_rendered_png() -> None:
    class Locator:
        def __init__(self, image: bytes, *, text: str = "") -> None:
            self.image = image
            self.text = text

        def is_visible(self, **_kwargs):
            return True

        def screenshot(self, **_kwargs):
            return self.image

        def bounding_box(self, **_kwargs):
            return {"x": 0, "y": 0, "width": 640, "height": 640}

        def inner_text(self, **_kwargs):
            return self.text

    class Collection:
        def __init__(self, locators):
            self.locators = list(locators)

        def count(self):
            return len(self.locators)

        def nth(self, index):
            return self.locators[index]

        def first(self):
            return self.locators[0]

    body = Locator(_fixture_rgba_png(ready=False), text="Click on all animals Verify")
    canvas = Locator(_fixture_rgba_png(ready=True))

    class Frame:
        def locator(self, selector):
            if selector == "body":
                return Collection([body])
            if selector == "canvas":
                return Collection([canvas])
            return Collection([])

    with __import__("pytest").raises(
        checkout_plugin_module._HcaptchaVisualSurfaceNotReady,
        match="plus_checkout_captcha_visual_surface_blank",
    ) as raised:
        checkout_plugin_module._capture_hcaptcha_visual(Frame())

    assert raised.value.probe["available"] is True
    assert raised.value.probe["ready"] is False
    assert raised.value.probe["source"] == "body"
    assert raised.value.probe["canvas"][0]["ready"] is True


def test_hcaptcha_visual_ready_waits_for_images_and_stable_render(monkeypatch) -> None:
    class Body:
        def __init__(self) -> None:
            self.screenshots = [b"loaded-body", b"loaded-body", b"loaded-body"]

        @staticmethod
        def bounding_box(**_kwargs):
            return {"x": 0, "y": 0, "width": 600, "height": 500}

        def screenshot(self, **_kwargs):
            return self.screenshots.pop(0)

    class EmptyCollection:
        @staticmethod
        def count():
            return 0

    class Frame:
        def __init__(self) -> None:
            self.body = Body()
            self.states = iter(
                [
                    {
                        "probe_ok": True,
                        "ready": False,
                        "image_count": 1,
                        "pending_image_count": 1,
                        "tile_count": 0,
                        "tile_visual_missing_count": 0,
                    },
                    {
                        "probe_ok": True,
                        "ready": True,
                        "image_count": 1,
                        "pending_image_count": 0,
                        "tile_count": 0,
                        "tile_visual_missing_count": 0,
                    },
                    {
                        "probe_ok": True,
                        "ready": True,
                        "image_count": 1,
                        "pending_image_count": 0,
                        "tile_count": 0,
                        "tile_visual_missing_count": 0,
                    },
                    {
                        "probe_ok": True,
                        "ready": True,
                        "image_count": 1,
                        "pending_image_count": 0,
                        "tile_count": 0,
                        "tile_visual_missing_count": 0,
                    },
                    {
                        "probe_ok": True,
                        "ready": True,
                        "image_count": 1,
                        "pending_image_count": 0,
                        "tile_count": 0,
                        "tile_visual_missing_count": 0,
                    },
                    {
                        "probe_ok": True,
                        "ready": True,
                        "image_count": 1,
                        "pending_image_count": 0,
                        "tile_count": 0,
                        "tile_visual_missing_count": 0,
                    },
                ]
            )

        def evaluate(self, script):
            assert script == checkout_plugin_module._HCAPTCHA_VISUAL_RESOURCE_STATE_SCRIPT
            return next(self.states)

        def locator(self, selector):
            return self.body if selector == "body" else EmptyCollection()

    clock = [0.0]
    monkeypatch.setattr(checkout_plugin_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    snapshot, result = checkout_plugin_module._wait_for_hcaptcha_visual_ready(
        Frame(),
        timeout_s=2.0,
        poll_s=0.25,
        stable_samples_required=3,
        min_settle_s=0.5,
    )

    assert snapshot is not None
    assert result["status"] == "ready"
    assert result["probe_count"] == 6
    assert result["stable_samples"] == 3
    assert result["pending_image_count"] == 0
    assert result["waited_ms"] == 1_250


def test_hcaptcha_visual_ready_uses_stable_tiles_when_dom_probe_is_advisory(
    monkeypatch,
) -> None:
    state = {
        "inspection": "dom",
        "ready": False,
        "body_ready": True,
        "visual_content_present": True,
        "visual_content_count": 9,
        "tile_count": 9,
        "challenge_image_count": 0,
        "canvas_count": 0,
        "pending_image_count": 0,
        # The live hCaptcha shell can report this while pixels are painted by
        # a wrapper/pseudo-element. Stable screenshots remain the source of
        # truth for whether the classifier should receive an image.
        "tile_visual_missing_count": 9,
    }
    monkeypatch.setattr(
        checkout_plugin_module,
        "_hcaptcha_visual_resource_state",
        lambda _frame: dict(state),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_capture_hcaptcha_visual",
        lambda _frame: {"image_digest": "stable-grid", "queries": ["tile"]},
    )
    clock = [0.0]
    monkeypatch.setattr(checkout_plugin_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    snapshot, result = checkout_plugin_module._wait_for_hcaptcha_visual_ready(
        object(),
        timeout_s=2.0,
        poll_s=0.25,
        stable_samples_required=3,
        min_settle_s=0.5,
    )

    assert snapshot is not None
    assert result["status"] == "ready"
    assert result["probe_ready"] is False
    assert result["capture_candidate"] is True
    assert result["stable_samples"] == 3


def test_hcaptcha_visual_ready_rejects_empty_challenge_surface(monkeypatch) -> None:
    class Body:
        @staticmethod
        def bounding_box(**_kwargs):
            return {"x": 0, "y": 0, "width": 520, "height": 570}

        @staticmethod
        def screenshot(**_kwargs):
            return b"blank-challenge-body"

    class Frame:
        def __init__(self) -> None:
            self.body = Body()

        @staticmethod
        def evaluate(script):
            assert script == checkout_plugin_module._HCAPTCHA_VISUAL_RESOURCE_STATE_SCRIPT
            return {
                "probe_ok": True,
                "ready": True,
                "image_count": 0,
                "challenge_image_count": 0,
                "pending_image_count": 0,
                "tile_count": 0,
                "tile_visual_missing_count": 0,
                "canvas_count": 0,
                "visual_content_count": 0,
                "visual_content_present": False,
            }

        def locator(self, selector):
            return self.body if selector == "body" else object()

    clock = [0.0]
    monkeypatch.setattr(checkout_plugin_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    snapshot, result = checkout_plugin_module._wait_for_hcaptcha_visual_ready(
        Frame(),
        timeout_s=0.5,
        poll_s=0.25,
        min_settle_s=0,
    )

    assert snapshot is None
    assert result["status"] == "not_ready"
    assert result["reason"] == "visual_content_missing"
    assert result["visual_content_count"] == 0


def test_hcaptcha_visual_ready_waits_for_canvas_bitmap_before_capture(monkeypatch) -> None:
    class Frame:
        @staticmethod
        def evaluate(script):
            assert script == checkout_plugin_module._HCAPTCHA_VISUAL_RESOURCE_STATE_SCRIPT
            return {
                "probe_ok": True,
                "ready": False,
                "body_ready": True,
                "image_count": 0,
                "challenge_image_count": 0,
                "pending_image_count": 0,
                "tile_count": 0,
                "tile_visual_missing_count": 0,
                "canvas_count": 1,
                "canvas_bitmap_ready": False,
                "canvas_blank_count": 1,
                "canvas_data_url_length": 320,
                "visual_content_count": 1,
                "visual_content_present": True,
            }

    monkeypatch.setattr(
        checkout_plugin_module,
        "_capture_hcaptcha_visual",
        lambda _frame: (_ for _ in ()).throw(
            AssertionError("blank canvas must not be sent to the classifier")
        ),
    )
    clock = [0.0]
    monkeypatch.setattr(checkout_plugin_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    snapshot, result = checkout_plugin_module._wait_for_hcaptcha_visual_ready(
        Frame(),
        timeout_s=0.5,
        poll_s=0.25,
    )

    assert snapshot is None
    assert result["status"] == "not_ready"
    assert result["reason"] == "canvas_bitmap_pending"
    assert result["canvas_bitmap_ready"] is False
    assert result["canvas_blank_count"] == 1


def test_hcaptcha_visual_ready_timeout_returns_no_snapshot(monkeypatch) -> None:
    class Frame:
        @staticmethod
        def evaluate(script):
            assert script == checkout_plugin_module._HCAPTCHA_VISUAL_RESOURCE_STATE_SCRIPT
            return {
                "probe_ok": True,
                "ready": False,
                "image_count": 3,
                "pending_image_count": 3,
                "tile_count": 9,
                "tile_visual_missing_count": 0,
            }

    clock = [0.0]
    monkeypatch.setattr(checkout_plugin_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        checkout_plugin_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    snapshot, result = checkout_plugin_module._wait_for_hcaptcha_visual_ready(
        Frame(),
        timeout_s=0.5,
        poll_s=0.25,
    )

    assert snapshot is None
    assert result["status"] == "not_ready"
    assert result["reason"] == "resources_pending"
    assert result["probe_count"] == 3
    assert result["pending_image_count"] == 3
    assert result["waited_ms"] == 500


def test_hcaptcha_visual_not_ready_does_not_call_classifier(monkeypatch) -> None:
    solver_calls: list[dict] = []
    traces: list[tuple[str, dict, str]] = []
    visual_frame = object()

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_not_ready"

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

        @staticmethod
        def mark_deferred_trace_once(*, reason, challenge):
            return True

    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: visual_frame,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_ready",
        lambda _frame: (
            None,
            {
                "status": "not_ready",
                "reason": "resources_pending",
                "waited_ms": 1_250,
                "probe_count": 6,
                "pending_image_count": 2,
                "tile_count": 9,
            },
        ),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_capture_hcaptcha_visual",
        lambda _frame: (_ for _ in ()).throw(
            AssertionError("capture must not run before visual readiness")
        ),
    )

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=Page(),
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "type": "setup_intent",
                "status": "requires_action",
                "site_key": "site-key-not-ready",
                "page_url": "https://js.stripe.com/fixture",
                "intent_id": "seti_not_ready",
                "client_secret": "seti_not_ready_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_not_ready/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda payload: solver_calls.append(payload) or {},
        solved_challenges=set(),
        classified_visuals=set(),
        trace_emitter=lambda event_type, data, level: traces.append(
            (event_type, data, level)
        ),
    )

    assert outcome is not None
    assert outcome["browser_interaction"] == {
        "status": "pending",
        "method": "visual",
        "retry": True,
        "reason": "resources_pending",
        "waited_ms": 1_250,
    }
    assert solver_calls == []
    assert traces == [
        (
            "challenge.browser.visual_waiting",
                {
                    "reason": "resources_pending",
                    "waited_ms": 1_250,
                    "probe_count": 6,
                    "pending_image_count": 2,
                    "tile_count": 9,
                    "visual_content_count": 0,
                },
            "INFO",
        )
    ]


def test_jpeg_image_size_reads_sof_dimensions() -> None:
    jpeg = (
        b"\xff\xd8\xff\xc0\x00\x11\x08\x01\xf4\x02\x58"
        b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    )

    assert checkout_plugin_module._jpeg_image_size(jpeg) == (600, 500)


def test_hcaptcha_visual_point_scales_query_pixels_to_current_css_box() -> None:
    snapshot = {
        "box": {"x": 100, "y": 50, "width": 600, "height": 500},
        "query_image_size": {"width": 1200, "height": 1000},
    }
    current_box = {"x": 300, "y": 200, "width": 600, "height": 500}

    assert checkout_plugin_module._visual_relative_point(
        snapshot,
        (260, 509),
        box=current_box,
    ) == (130.0, 254.5)
    assert checkout_plugin_module._visual_page_point(
        snapshot,
        (260, 509),
        box=current_box,
    ) == (430.0, 454.5)


def test_hcaptcha_visual_click_targets_current_frame_body(monkeypatch) -> None:
    class Mouse:
        def __init__(self) -> None:
            self.events: list[tuple] = []

        def move(self, *args, **kwargs):
            self.events.append(("move", args, kwargs))

        def click(self, *args, **kwargs):
            self.events.append(("click", args, kwargs))

    class Body:
        def __init__(self) -> None:
            self.clicks: list[dict] = []
            self.screenshots = [b"before-selection", b"after-selection"]

        @staticmethod
        def bounding_box(**_kwargs):
            return {"x": 300, "y": 200, "width": 600, "height": 500}

        def screenshot(self, **_kwargs):
            return self.screenshots.pop(0)

        def click(self, **kwargs):
            self.clicks.append(kwargs)

    body = Body()
    frame = SimpleNamespace(locator=lambda selector: body if selector == "body" else None)
    page = SimpleNamespace(mouse=Mouse())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    applied = checkout_plugin_module._apply_hcaptcha_classification(
        page,
        snapshot={
            "box": {"x": 100, "y": 50, "width": 600, "height": 500},
            "query_image_size": {"width": 1200, "height": 1000},
        },
        solution={"type": "click", "box": [260, 509]},
        frame=frame,
    )

    assert body.clicks == [
        {"position": {"x": 130.0, "y": 254.5}, "timeout": 5_000}
    ]
    assert page.mouse.events == []
    assert applied == [
        {
            "type": "click",
            "raw_point": (260.0, 509.0),
            "relative_point": (130.0, 254.5),
            "point": (430.0, 454.5),
            "method": "frame_body",
            "visual_changed": True,
        }
    ]


def test_hcaptcha_visual_surface_uses_page_mouse_for_canvas_clicks(monkeypatch) -> None:
    class Mouse:
        def __init__(self) -> None:
            self.events: list[tuple] = []

        def move(self, *args, **kwargs):
            self.events.append(("move", args, kwargs))

        def click(self, *args, **kwargs):
            self.events.append(("click", args, kwargs))

    class Body:
        def __init__(self) -> None:
            self.click_called = False
            self.screenshots = [b"before-canvas", b"after-canvas"]

        @staticmethod
        def bounding_box(**_kwargs):
            return {"x": 300, "y": 200, "width": 600, "height": 500}

        def screenshot(self, **_kwargs):
            return self.screenshots.pop(0)

        def click(self, **_kwargs):
            self.click_called = True
            raise AssertionError("canvas path must use page.mouse")

    body = Body()
    frame = SimpleNamespace(locator=lambda selector: body if selector == "body" else None)
    page = SimpleNamespace(mouse=Mouse())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    applied = checkout_plugin_module._apply_hcaptcha_classification(
        page,
        snapshot={
            "mode": "visual",
            "box": {"x": 100, "y": 50, "width": 600, "height": 500},
            "query_image_size": {"width": 1200, "height": 1000},
        },
        solution={"type": "click", "box": [260, 509]},
        frame=frame,
    )

    assert body.click_called is False
    assert page.mouse.events == [
        ("move", (430.0, 454.5), {"steps": 1}),
        ("click", (430.0, 454.5), {}),
    ]
    assert applied[0]["method"] == "page_mouse"
    assert applied[0]["visual_changed"] is True


def test_hcaptcha_visual_surface_maps_image_to_text_coordinates(monkeypatch) -> None:
    class Mouse:
        def __init__(self) -> None:
            self.events: list[tuple] = []

        def move(self, *args, **kwargs):
            self.events.append(("move", args, kwargs))

        def click(self, *args, **kwargs):
            self.events.append(("click", args, kwargs))

    class Body:
        screenshots = [b"before-image-task", b"after-image-task"]

        @staticmethod
        def bounding_box(**_kwargs):
            return {"x": 300, "y": 200, "width": 600, "height": 500}

        def screenshot(self, **_kwargs):
            return self.screenshots.pop(0)

    body = Body()
    frame = SimpleNamespace(locator=lambda selector: body if selector == "body" else None)
    page = SimpleNamespace(mouse=Mouse())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    solution = checkout_plugin_module._image_to_text_solution(
        {
            "text": __import__("json").dumps(
                {
                    "captcha_type": "click",
                    "clicks": [{"x": 720, "y": 450, "label": "center"}],
                }
            )
        }
    )
    applied = checkout_plugin_module._apply_hcaptcha_classification(
        page,
        snapshot={
            "mode": "visual",
            "box": {"x": 100, "y": 50, "width": 600, "height": 500},
            "query_image_size": {"width": 1200, "height": 1000},
        },
        solution=solution,
        frame=frame,
    )

    assert page.mouse.events == [
        ("move", (600.0, 450.0), {"steps": 1}),
        ("click", (600.0, 450.0), {}),
    ]
    assert applied[0]["raw_point"] == (720.0, 450.0)
    assert applied[0]["relative_point"] == (300.0, 250.0)
    assert applied[0]["point"] == (600.0, 450.0)


def test_image_to_text_coordinate_space_uses_response_dimensions_when_present() -> None:
    solution = checkout_plugin_module._image_to_text_solution(
        {
            "text": __import__("json").dumps(
                {
                    "captcha_type": "click",
                    "coordinate_space": {"width": 1000, "height": 500},
                    "clicks": [{"x": 500, "y": 250}],
                }
            )
        }
    )

    assert solution["_coordinate_space"] == {"width": 1000.0, "height": 500.0}


def test_hcaptcha_visual_image_to_text_solution_runs_current_browser_round(
    monkeypatch,
) -> None:
    solver_payloads: list[dict] = []
    visual_frame = object()

    class Mouse:
        def __init__(self) -> None:
            self.events: list[tuple] = []

        def move(self, *args, **kwargs):
            self.events.append(("move", args, kwargs))

        def click(self, *args, **kwargs):
            self.events.append(("click", args, kwargs))

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_image_task"

        def __init__(self) -> None:
            self.mouse = Mouse()

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    snapshot = {
        "mode": "visual",
        "queries": ["aW1hZ2U="],
        "anchors": [],
        "question": "Identify all characters that show up more than once",
        "image_digest": "image-to-text-round",
        "box": {"x": 100.0, "y": 50.0, "width": 600.0, "height": 500.0},
        "query_image_size": {"width": 1200, "height": 1000},
        "tile_boxes": [],
    }
    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: visual_frame,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_ready",
        lambda _frame: (dict(snapshot), {"waited_ms": 0}),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_click_hcaptcha_verify",
        lambda _frame, **_kwargs: True,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_hcaptcha_visual_digest",
        lambda _frame: "post-click-digest",
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_advance",
        lambda _page, *, previous_digest: (
            "completed" if previous_digest == "post-click-digest" else "unchanged"
        ),
    )
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    page = Page()

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=page,
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "type": "setup_intent",
                "status": "requires_action",
                "site_key": "site-key-image-task",
                "page_url": "https://js.stripe.com/fixture",
                "intent_id": "seti_image_task",
                "client_secret": "seti_image_task_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_image_task/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda payload: solver_payloads.append(payload)
        or {
            "provider": "hcaptcha",
            "task_id": "image-task-browser-round",
            "task_type": "ImageToTextTask",
            "solution": checkout_plugin_module._image_to_text_solution(
                {
                    "text": __import__("json").dumps(
                        {
                            "captcha_type": "click",
                            "clicks": [{"x": 720, "y": 450, "label": "duplicate"}],
                        }
                    )
                }
            ),
        },
        solved_challenges=set(),
        classified_visuals=set(),
    )

    assert solver_payloads[0]["classification_mode"] == "visual"
    assert solver_payloads[0]["classification_queries"] == ["aW1hZ2U="]
    assert page.mouse.events == [
        ("move", (400.0, 300.0), {"steps": 1}),
        ("click", (400.0, 300.0), {}),
    ]
    assert outcome is not None
    assert outcome["solver_task_id"] == "image-task-browser-round"
    assert outcome["browser_interaction"] == {
        "status": "completed",
        "mode": "visual",
        "action_count": 1,
    }


def test_hcaptcha_body_click_timeout_falls_back_to_page_mouse(monkeypatch) -> None:
    class Mouse:
        def __init__(self) -> None:
            self.events: list[tuple] = []

        def move(self, *args, **kwargs):
            self.events.append(("move", args, kwargs))

        def click(self, *args, **kwargs):
            self.events.append(("click", args, kwargs))

    class Body:
        screenshots = [b"before-fallback", b"after-fallback"]

        @staticmethod
        def bounding_box(**_kwargs):
            return {"x": 300, "y": 200, "width": 600, "height": 500}

        def screenshot(self, **_kwargs):
            return self.screenshots.pop(0)

        @staticmethod
        def click(**_kwargs):
            raise TimeoutError("body click timed out")

    body = Body()
    frame = SimpleNamespace(locator=lambda selector: body if selector == "body" else None)
    page = SimpleNamespace(mouse=Mouse())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    applied = checkout_plugin_module._apply_hcaptcha_classification(
        page,
        snapshot={
            "mode": "grid",
            "box": {"x": 100, "y": 50, "width": 600, "height": 500},
            "query_image_size": {"width": 1200, "height": 1000},
        },
        solution={"type": "click", "box": [260, 509]},
        frame=frame,
    )

    assert page.mouse.events == [
        ("move", (430.0, 454.5), {"steps": 1}),
        ("click", (430.0, 454.5), {}),
    ]
    assert applied[0]["method"] == "page_mouse_fallback"
    assert "TimeoutError:body click timed out" in applied[0]["fallback_error"]
    assert applied[0]["visual_changed"] is True


def test_checkout_payment_panels_are_fixed_at_top_left() -> None:
    for script in (
        checkout_plugin_module.SUBMIT_PLUS_CHECKOUT_SCRIPT,
        checkout_plugin_module.OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT,
    ):
        assert '"left:18px"' in script
        assert '"top:18px"' in script
        assert '"right:18px"' not in script
        assert '"bottom:18px"' not in script


def test_hcaptcha_grid_classification_clicks_documented_top_k_tiles(monkeypatch) -> None:
    class Mouse:
        def __init__(self):
            self.clicks: list[tuple[float, float]] = []

        @staticmethod
        def move(_x, _y, **_kwargs):
            return None

        def click(self, x, y):
            self.clicks.append((x, y))

    page = SimpleNamespace(mouse=Mouse())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    applied = checkout_plugin_module._apply_hcaptcha_classification(
        page,
        snapshot={
            "tile_boxes": [
                {"x": 10, "y": 20, "width": 80, "height": 80},
                {"x": 100, "y": 20, "width": 80, "height": 80},
                {"x": 190, "y": 20, "width": 80, "height": 80},
            ]
        },
        solution={"objects": [True, False, True], "top_k": [0, 2]},
    )

    assert applied == [{"type": "tile", "index": 0}, {"type": "tile", "index": 2}]
    assert page.mouse.clicks == [(50.0, 60.0), (230.0, 60.0)]


def test_hcaptcha_classification_accepts_integer_indexes_and_answer_alias() -> None:
    assert checkout_plugin_module._hcaptcha_classification_actions(
        {"type": "click", "objects": [1, 2, 6]}
    ) == [
        {"type": "tile", "index": 1},
        {"type": "tile", "index": 2},
        {"type": "tile", "index": 6},
    ]
    assert checkout_plugin_module._hcaptcha_classification_actions(
        {"type": "click", "answer": ["1", "2", "6"]}
    ) == [
        {"type": "tile", "index": 1},
        {"type": "tile", "index": 2},
        {"type": "tile", "index": 6},
    ]
    assert checkout_plugin_module._hcaptcha_classification_actions(
        {"type": "click", "objects": [False, False, False]}
    ) == []


def test_hcaptcha_visual_key_distinguishes_round_prompt_and_anchor() -> None:
    snapshot = {
        "image_digest": "same-grid",
        "queries": ["tile-1", "tile-2"],
        "anchors": ["anchor-1"],
        "question": "Find ALL animals the exact number of times indicated",
    }
    prompt_round = {
        **snapshot,
        "question": "Find ALL animals the exact number of times indicated: deer 1x",
    }
    anchor_round = {**snapshot, "anchors": ["anchor-2"]}

    assert checkout_plugin_module._hcaptcha_visual_key(snapshot) != (
        checkout_plugin_module._hcaptcha_visual_key(prompt_round)
    )
    assert checkout_plugin_module._hcaptcha_visual_key(snapshot) != (
        checkout_plugin_module._hcaptcha_visual_key(anchor_round)
    )


def test_hcaptcha_same_grid_with_new_prompt_is_classified_again(monkeypatch) -> None:
    visual_frame = object()
    snapshots = [
        {
            "mode": "grid",
            "queries": ["tile-1"] * 9,
            "anchors": ["anchor"],
            "question": "deer 1x and lion 2x",
            "image_digest": "same-grid",
            "box": {"x": 0.0, "y": 0.0, "width": 600.0, "height": 500.0},
            "tile_boxes": [
                {"x": float(index), "y": 0.0, "width": 10.0, "height": 10.0}
                for index in range(9)
            ],
        },
        {
            "mode": "grid",
            "queries": ["tile-1"] * 9,
            "anchors": ["anchor"],
            "question": "mouse 3x",
            "image_digest": "same-grid",
            "box": {"x": 0.0, "y": 0.0, "width": 600.0, "height": 500.0},
            "tile_boxes": [
                {"x": float(index), "y": 0.0, "width": 10.0, "height": 10.0}
                for index in range(9)
            ],
        },
    ]
    solver_payloads: list[dict] = []
    classified_visuals: set[str] = set()

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_rounds"

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: visual_frame,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_ready",
        lambda _frame: (snapshots.pop(0), {"waited_ms": 0}),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_apply_hcaptcha_classification",
        lambda *_args, **_kwargs: [{"type": "tile", "index": 0}],
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_click_hcaptcha_verify",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_advance",
        lambda *_args, **_kwargs: "advanced",
    )
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    for _ in range(2):
        outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
            page=Page(),
            state={
                "challenge_pending": True,
                "challenge": {
                    "provider": "hcaptcha",
                    "type": "setup_intent",
                    "status": "requires_action",
                    "site_key": "site-key-rounds",
                    "page_url": "https://js.stripe.com/fixture",
                    "intent_id": "seti_rounds",
                    "client_secret": "seti_rounds_secret_fixture",
                    "verify_url": "/v1/setup_intents/seti_rounds/verify_challenge",
                },
            },
            challenge_capture=Capture(),
            captcha_solver=lambda payload: solver_payloads.append(payload)
            or {
                "task_id": f"task-{len(solver_payloads)}",
                "task_type": "HCaptchaClassification",
                "solution": {"type": "click", "objects": [0]},
            },
            solved_challenges=set(),
            classified_visuals=classified_visuals,
        )
        assert outcome is not None
        assert outcome["browser_interaction"]["status"] == "advanced"

    assert len(solver_payloads) == 2
    assert [payload["classification_question"] for payload in solver_payloads] == [
        "deer 1x and lion 2x",
        "mouse 3x",
    ]
    assert len(classified_visuals) == 2


def test_hcaptcha_empty_grid_classification_submits_skip(monkeypatch) -> None:
    traces: list[tuple[str, dict, str]] = []
    verify_frames: list[tuple[object, dict[str, object]]] = []
    solved_challenges: set[str] = set()
    visual_frame = object()

    class Mouse:
        def __init__(self):
            self.events: list[tuple] = []

        def move(self, *args, **kwargs):
            self.events.append(("move", args, kwargs))

        def click(self, *args, **kwargs):
            self.events.append(("click", args, kwargs))

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_skip"

        def __init__(self):
            self.mouse = Mouse()

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    snapshot = {
        "mode": "grid",
        "queries": ["aW1hZ2U="] * 9,
        "anchors": ["YW5jaG9y"],
        "question": "Click on all things you can process using the object shown",
        "image_digest": "digest-skip-1",
        "box": {"x": 100.0, "y": 50.0, "width": 600.0, "height": 500.0},
        "tile_boxes": [
            {"x": float(index * 10), "y": 20.0, "width": 8.0, "height": 8.0}
            for index in range(9)
        ],
    }
    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: visual_frame,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_capture_hcaptcha_visual",
        lambda _frame: dict(snapshot),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_click_hcaptcha_verify",
        lambda frame, **kwargs: verify_frames.append((frame, kwargs)) or True,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_hcaptcha_visual_digest",
        lambda _frame: "post-skip-digest",
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_advance",
        lambda _page, *, previous_digest: "advanced",
    )
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    page = Page()

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=page,
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "type": "setup_intent",
                "status": "requires_action",
                "site_key": "site-key-skip",
                "page_url": "https://js.stripe.com/fixture",
                "intent_id": "seti_skip",
                "client_secret": "seti_skip_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_skip/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda _payload: {
            "provider": "hcaptcha",
            "task_id": "a033c396-9468-11f1-b428-525400423cb8",
            "task_type": "HCaptchaClassification",
            "solution": {
                "box": [],
                "clicks": [],
                "confidences": [
                    0.1824,
                    0.0067,
                    0.0059,
                    0.0124,
                    0.0086,
                    0.0017,
                    0.001,
                    0.0004,
                    0.0006,
                ],
                "objects": [False] * 9,
                "question": snapshot["question"],
                "top_k": [],
                "type": "click",
            },
        },
        solved_challenges=solved_challenges,
        classified_visuals=set(),
        trace_emitter=lambda event_type, data, level: traces.append(
            (event_type, data, level)
        ),
    )

    assert outcome is not None
    assert outcome["browser_interaction"] == {
        "status": "advanced",
        "mode": "grid",
        "action_count": 0,
    }
    assert page.mouse.events == []
    assert verify_frames == [(visual_frame, {"allow_skip": True})]
    classification_trace = next(
        data for event, data, _level in traces if event == "challenge.classification.succeeded"
    )
    assert classification_trace["action_count"] == 0
    assert classification_trace["empty_selection"] is True
    assert "button:has-text('Skip')" in checkout_plugin_module._HCAPTCHA_SKIP_SELECTORS


def test_hcaptcha_unclassified_empty_solution_still_fails() -> None:
    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutPluginError,
        match="plus_checkout_captcha_classification_actions_missing",
    ):
        checkout_plugin_module._hcaptcha_classification_actions(
            {"box": [], "clicks": [], "top_k": [], "type": "click"}
        )


def test_expanded_hcaptcha_drag_is_classified_and_applied_in_current_browser(
    monkeypatch,
) -> None:
    traces: list[tuple[str, dict, str]] = []
    solver_payloads: list[dict] = []
    advance_baselines: list[str] = []
    verify_frames: list[tuple[object, dict[str, object]]] = []
    solved_challenges: set[str] = set()
    classified_visuals: set[str] = set()
    visual_frame = object()

    class Mouse:
        def __init__(self):
            self.events: list[tuple] = []

        def move(self, x, y, **kwargs):
            self.events.append(("move", x, y, kwargs))

        def down(self):
            self.events.append(("down",))

        def up(self):
            self.events.append(("up",))

        def click(self, x, y):
            self.events.append(("click", x, y))

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_drag"

        def __init__(self):
            self.mouse = Mouse()

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    snapshot = {
        "mode": "visual",
        "queries": ["aW1hZ2U="],
        "anchors": [],
        "question": "Please drag the icon to the place where it fits",
        "image_digest": "digest-drag-1",
        "box": {"x": 100.0, "y": 50.0, "width": 600.0, "height": 500.0},
        "tile_boxes": [],
    }
    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: visual_frame,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_capture_hcaptcha_visual",
        lambda _frame: dict(snapshot),
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_click_hcaptcha_verify",
        lambda frame, **kwargs: verify_frames.append((frame, kwargs)) or True,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_hcaptcha_visual_digest",
        lambda frame: "post-action-digest" if frame is visual_frame else "",
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_advance",
        lambda _page, *, previous_digest: advance_baselines.append(previous_digest)
        or "completed",
    )
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)
    page = Page()

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=page,
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "type": "setup_intent",
                "status": "requires_action",
                "site_key": "site-key-drag",
                "page_url": "https://js.stripe.com/fixture",
                "intent_id": "seti_drag",
                "client_secret": "seti_drag_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_drag/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda payload: solver_payloads.append(payload)
        or {
            "provider": "hcaptcha",
            "task_id": "classification-task-drag",
            "task_type": "HCaptchaClassification",
            "solution": {
                "type": "drag",
                "box": [{"start": [10, 20], "end": [80, 90]}],
            },
        },
        solved_challenges=solved_challenges,
        classified_visuals=classified_visuals,
        trace_emitter=lambda event_type, data, level: traces.append(
            (event_type, data, level)
        ),
    )

    assert outcome is not None
    assert outcome["browser_interaction"] == {
        "status": "completed",
        "mode": "visual",
        "action_count": 1,
    }
    assert solver_payloads[0]["browser_classification"] is True
    assert solver_payloads[0]["classification_queries"] == ["aW1hZ2U="]
    assert page.mouse.events == [
        ("move", 110.0, 70.0, {"steps": 1}),
        ("down",),
        ("move", 180.0, 140.0, {"steps": 2}),
        ("up",),
    ]
    assert classified_visuals == {
        checkout_plugin_module._hcaptcha_visual_key(snapshot)
    }
    assert advance_baselines == ["post-action-digest"]
    assert verify_frames == [(visual_frame, {"allow_skip": False})]
    assert solved_challenges
    assert [event for event, _data, _level in traces] == [
        "challenge.browser.visual_ready",
        "challenge.browser.visual_detected",
        "challenge.classification.succeeded",
        "challenge.classification.actions_dispatched",
        "challenge.browser.verify_clicked",
        "challenge.browser.completed",
    ]
    verify_trace = next(
        data for event, data, _level in traces if event == "challenge.browser.verify_clicked"
    )
    assert verify_trace == {
        "clicked": True,
        "required": False,
        "control": "verify",
        "skip_allowed": False,
        "optional_for_drag": True,
    }
    assert "aW1hZ2U=" not in str(traces)


def test_hcaptcha_drag_releases_mouse_when_move_fails(monkeypatch) -> None:
    class Mouse:
        def __init__(self) -> None:
            self.events: list[tuple] = []

        def move(self, x, y, **kwargs):
            self.events.append(("move", x, y, kwargs))
            if len([event for event in self.events if event[0] == "move"]) == 2:
                raise RuntimeError("fixture move failed")

        def down(self):
            self.events.append(("down",))

        def up(self):
            self.events.append(("up",))

    page = SimpleNamespace(mouse=Mouse())
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    with __import__("pytest").raises(RuntimeError, match="fixture move failed"):
        checkout_plugin_module._apply_hcaptcha_classification(
            page,
            snapshot={"box": {"x": 100, "y": 50, "width": 600, "height": 500}},
            solution={
                "type": "drag",
                "box": [{"start": [10, 20], "end": [80, 90]}],
            },
        )

    assert page.mouse.events == [
        ("move", 110.0, 70.0, {"steps": 1}),
        ("down",),
        ("move", 180.0, 140.0, {"steps": 2}),
        ("up",),
    ]


def test_hcaptcha_verify_ignores_skip_for_drag() -> None:
    class Locator:
        def __init__(self) -> None:
            self.clicks: list[dict] = []
            self.evaluations: list[str] = []

        @staticmethod
        def is_visible(**_kwargs):
            return True

        @staticmethod
        def get_attribute(name):
            return "Skip Challenge" if name in {"aria-label", "title"} else ""

        @staticmethod
        def inner_text(**_kwargs):
            return ""

        def click(self, **kwargs):
            self.clicks.append(kwargs)

        def evaluate(self, script):
            self.evaluations.append(script)
            return True

    locator = Locator()

    class Frame:
        @staticmethod
        def locator(_selector):
            return locator

    assert checkout_plugin_module._click_hcaptcha_verify(Frame(), allow_skip=False) is False
    assert locator.clicks == []
    assert locator.evaluations == []


def test_hcaptcha_skip_control_never_clicks_verify() -> None:
    class Locator:
        def __init__(self, label: str) -> None:
            self.label = label
            self.clicks: list[dict] = []

        @staticmethod
        def is_visible(**_kwargs):
            return True

        def get_attribute(self, name):
            return self.label if name in {"aria-label", "title"} else ""

        @staticmethod
        def inner_text(**_kwargs):
            return ""

        def click(self, **kwargs):
            self.clicks.append(kwargs)

    verify = Locator("Verify")
    skip = Locator("Skip Challenge")

    class Frame:
        @staticmethod
        def locator(selector):
            return skip if "Skip" in selector or "skip" in selector else verify

    assert checkout_plugin_module._click_hcaptcha_verify(Frame(), allow_skip=True) is True
    assert skip.clicks == [{"timeout": 1_200, "force": False}]
    assert verify.clicks == []


def test_hcaptcha_verify_falls_back_to_dom_click_when_overlay_blocks_pointer() -> None:
    class Locator:
        def __init__(self) -> None:
            self.clicks: list[dict] = []
            self.evaluations: list[str] = []

        @staticmethod
        def is_visible(**_kwargs):
            return True

        @staticmethod
        def get_attribute(name):
            return "Verify" if name in {"aria-label", "title"} else ""

        @staticmethod
        def inner_text(**_kwargs):
            return "Verify"

        def click(self, **kwargs):
            self.clicks.append(kwargs)
            raise RuntimeError("fixture overlay intercepts pointer events")

        def evaluate(self, script):
            self.evaluations.append(script)
            return True

    locator = Locator()

    class Frame:
        @staticmethod
        def locator(_selector):
            return locator

    assert checkout_plugin_module._click_hcaptcha_verify(Frame()) is True
    assert locator.clicks == [
        {"timeout": 1_200, "force": False},
        {"timeout": 1_200, "force": True},
    ]
    assert locator.evaluations == ["(element) => { element.click(); return true; }"]


def test_hcaptcha_checkbox_without_visual_challenge_waits_in_browser(
    monkeypatch,
) -> None:
    solver_payloads: list[dict] = []
    traces: list[tuple[str, dict, str]] = []

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_checkbox"

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: None,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_click_hcaptcha_checkbox",
        lambda _page: {"clicked": True, "method": "mouse"},
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_wait_for_hcaptcha_visual_frame",
        lambda *_args, **_kwargs: ("not_visible", None),
    )
    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=Page(),
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "type": "payment_intent",
                "status": "requires_action",
                "site_key": "site-key-checkbox",
                "page_url": "https://js.stripe.com/fixture",
                "intent_id": "pi_checkbox",
                "client_secret": "pi_checkbox_secret_fixture",
                "verify_url": "/v1/payment_intents/pi_checkbox/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda payload: solver_payloads.append(payload)
        or {"provider": "hcaptcha", "token": "solver-token", "task_id": "task-1"},
        solved_challenges=set(),
        classified_visuals=set(),
        trace_emitter=lambda event_type, data, level: traces.append(
            (event_type, data, level)
        ),
    )

    assert outcome is not None
    assert outcome["verification"] is None
    assert outcome["browser_interaction"] == {
        "status": "pending",
        "method": "checkbox",
        "retry": True,
    }
    assert solver_payloads == []
    assert traces[0][0] == "challenge.browser.checkbox_clicked"
    assert traces[1][0] == "challenge.browser.checkbox_pending"
    assert traces[1][1] == {
        "checkbox_clicked": True,
        "reason": "outcome_not_observed",
        "wait_status": "not_visible",
        "next_action": "retry_checkbox",
    }


def test_hcaptcha_checkbox_waits_for_delayed_frame_before_clicking(monkeypatch) -> None:
    class Locator:
        def __init__(self, *, visible=True):
            self.visible = visible
            self.clicks = []

        def is_visible(self, **_kwargs):
            return self.visible

        def bounding_box(self, **_kwargs):
            return {"x": 10, "y": 20, "width": 30, "height": 30}

        def click(self, **kwargs):
            self.clicks.append(kwargs)

    class Frame:
        url = "https://newassets.hcaptcha.com/captcha/fixture.html#frame=checkbox"

        def __init__(self):
            self.checkbox = Locator()

        def locator(self, selector):
            return self.checkbox if selector == "div[aria-checked]" else Locator(visible=False)

    class Mouse:
        def __init__(self):
            self.events = []

        def move(self, x, y, **kwargs):
            self.events.append(("move", x, y, kwargs))

        def click(self, x, y):
            self.events.append(("click", x, y))

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_delayed"

        def __init__(self):
            self.frames = []
            self.mouse = Mouse()

    page = Page()
    frame = Frame()

    def release_frame(_seconds):
        page.frames[:] = [frame]

    monkeypatch.setattr(checkout_plugin_module.time, "sleep", release_frame)

    result = checkout_plugin_module._click_hcaptcha_checkbox(page)

    assert result["clicked"] is True
    assert result["method"] == "locator"
    assert result["probe_count"] == 2
    assert frame.checkbox.clicks == [{"timeout": 1_500, "force": False}]
    assert page.mouse.events == []


def test_hcaptcha_checked_checkbox_without_visual_challenge_continues_immediately(
    monkeypatch,
) -> None:
    class Capture:
        @staticmethod
        def latest_active_stripe_challenge():
            return {"intent_id": "seti_checkbox_passed"}

    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: None,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_hcaptcha_checkbox_checked",
        lambda _page: True,
    )

    status, frame = checkout_plugin_module._wait_for_hcaptcha_visual_frame(
        SimpleNamespace(url="https://chatgpt.com/checkout/openai_llc/cs_live_checkbox"),
        challenge_capture=Capture(),
        active_intent_id="seti_checkbox_passed",
        timeout_s=8,
    )

    assert status == "passed"
    assert frame is None


def test_hcaptcha_same_visual_is_not_sent_to_classifier_twice(monkeypatch) -> None:
    solver_calls: list[dict] = []
    visual_frame = object()

    class Page:
        url = "https://chatgpt.com/checkout/openai_llc/cs_live_duplicate"

        @staticmethod
        def evaluate(script, _payload=None):
            if script == checkout_plugin_module.READ_BROWSER_USER_AGENT_SCRIPT:
                return "Fixture Browser UA"
            raise AssertionError(f"unexpected script: {script}")

    class Capture:
        @staticmethod
        def snapshot():
            return {"challenge_requests": []}

    monkeypatch.setattr(
        checkout_plugin_module,
        "_find_hcaptcha_visual_frame",
        lambda _page: visual_frame,
    )
    monkeypatch.setattr(
        checkout_plugin_module,
        "_capture_hcaptcha_visual",
        lambda _frame: {
            "mode": "visual",
            "queries": ["aW1hZ2U="],
            "anchors": [],
            "question": "Please drag the icon",
            "image_digest": "already-classified-digest",
            "box": {"x": 0.0, "y": 0.0, "width": 600.0, "height": 500.0},
            "tile_boxes": [],
        },
    )
    monkeypatch.setattr(checkout_plugin_module.time, "sleep", lambda _seconds: None)

    outcome = checkout_plugin_module._maybe_solve_checkout_challenge(
        page=Page(),
        state={
            "challenge_pending": True,
            "challenge": {
                "provider": "hcaptcha",
                "type": "setup_intent",
                "status": "requires_action",
                "site_key": "site-key-duplicate",
                "page_url": "https://js.stripe.com/fixture",
                "intent_id": "seti_duplicate",
                "client_secret": "seti_duplicate_secret_fixture",
                "verify_url": "/v1/setup_intents/seti_duplicate/verify_challenge",
            },
        },
        challenge_capture=Capture(),
        captcha_solver=lambda payload: solver_calls.append(payload) or {},
        solved_challenges=set(),
            classified_visuals={
                checkout_plugin_module._hcaptcha_visual_key(
                    {
                        "image_digest": "already-classified-digest",
                        "queries": ["aW1hZ2U="],
                        "anchors": [],
                        "question": "Please drag the icon",
                    }
                )
            },
    )

    assert outcome is None
    assert solver_calls == []


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
            "user_agent": "Original Browser UA",
        },
        api_url="https://api.yescaptcha.com",
        client_key="client-key-yescaptcha",
    )

    assert requests_seen[0][0] == "https://api.yescaptcha.com/createTask"
    assert requests_seen[0][1]["json"]["task"]["userAgent"] == "Original Browser UA"
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


def test_shared_checkout_creator_preserves_explicit_already_paid_response() -> None:
    checkout = {
        "ok": False,
        "http_status": 400,
        "tag": "invalid_request_error",
        "response": {"detail": {"message": "User is already paid"}},
    }

    class Page:
        @staticmethod
        def goto(_url, **_kwargs):
            return None

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

    with __import__("pytest").raises(
        checkout_plugin_module.PlusCheckoutAlreadyPaidError
    ) as captured:
        create_plus_checkout_with_script(Page(), expected_account_id="account-1")

    assert captured.value.http_status == 400
    assert captured.value.result == checkout
    assert "User is already paid" in str(captured.value)


def test_checkout_already_paid_skips_new_payment_and_refreshes_current_session(
    monkeypatch,
) -> None:
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        promotion_updater=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("promotion update must be skipped")
        ),
    )
    refresh_calls: list[dict] = []
    monkeypatch.setattr(
        workflow,
        "_create_checkout",
        lambda _page, *, account_id: {
            "already_paid": True,
            "http_status": 400,
            "checkout_session_id": "",
            "checkout_url": "",
            "response": {"detail": {"message": "User is already paid"}},
        },
    )
    monkeypatch.setattr(
        workflow,
        "_refresh_session_after_payment",
        lambda **kwargs: refresh_calls.append(kwargs)
        or {"status": "succeeded", "plan_type": "plus"},
    )

    page = object()
    result = workflow._checkout_on_page(
        page=page,
        context={"external_space_id": "account-1"},
        promotion_proxy_url="http://jp-proxy.example:8080",
    )

    assert refresh_calls == [
        {
            "page": page,
            "checkout_url": "",
            "context": {"external_space_id": "account-1"},
        }
    ]
    assert result["submitted"]["phase"] == "already_paid"
    assert result["submitted"]["payment_result"]["state"] == "succeeded"
    assert result["submitted"]["session_after_payment"]["plan_type"] == "plus"


@pytest.mark.parametrize(
    ("checkout_id", "provider"),
    [
        ("cs_live_protocol_fixture", "stripe_custom_checkout"),
        ("oaics_protocol_fixture", "oaics_checkout"),
    ],
)
def test_workflow_run_uses_protocol_checkout_and_persists_session_before_sync(
    monkeypatch: pytest.MonkeyPatch,
    checkout_id: str,
    provider: str,
) -> None:
    order: list[str] = []
    account = SimpleNamespace(
        id="user-1",
        email="person@example.com",
        password="unused-browser-password",
        access_token="access-old",
        session_token="session-old",
        cookie_header="oai-did=device-1; session=old",
        auth_cookie_header="auth=old",
        device_id="device-1",
        csrf_token="csrf-old",
        mfa_status="configured",
        twofauth_account_id="totp-unused",
        account_status="active",
        session_status="active",
        last_session_refresh_at=None,
        last_login_error_code="old",
        last_login_error_message="old",
        updated_at=None,
    )
    space = SimpleNamespace(
        id="space-1",
        provider="openai_chatgpt",
        space_type="personal",
        space_status="active",
        has_promotion=True,
        promotion_id="promo-space",
        has_payment_method=True,
        payment_method_status="bound",
        payment_method_id="pm-bound",
        owner_user_account_id="user-1",
        external_space_id="account-1",
    )

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def get(model, _id):
            if model is checkout_workflow_module.UserAccountModel:
                return account
            if model is checkout_workflow_module.SpaceModel:
                return space
            raise AssertionError(model)

        @staticmethod
        def commit():
            order.append("persist")

    def resolve_proxy(*, email: str, country_code: str):
        assert email == "person@example.com"
        return SimpleNamespace(
            proxy_url=f"http://{country_code.lower()}-proxy.example:8080",
            country_code=country_code,
            sid_source="email_sha256",
            probe_attempts=1,
        )

    promotion_calls: list[dict] = []

    def promotion_updater(**kwargs):
        order.append("promotion")
        promotion_calls.append(kwargs)
        return {"success": True}

    def protocol_runner(config, **kwargs):
        order.append("create")
        assert config.account_id == "account-1"
        assert config.access_token == "access-old"
        assert config.session_token == "session-old"
        assert config.promo_campaign_id == "promo-space"
        assert config.billing == {"email": "person@example.com"}
        assert kwargs["payment_method_id"] == "pm-bound"
        assert kwargs["proxy_url"] == "http://us-proxy.example:8080"
        promo = kwargs["promotion_callback"](
            checkout_url=(
                f"https://chatgpt.com/checkout/openai_llc/{checkout_id}"
            ),
            access_token="access-refreshed-before-promotion",
            cookie_header="session=promotion",
            user_agent="Protocol UA",
        )
        order.append("submit")
        kwargs["session_update_callback"](
            {
                "access_token": "access-new",
                "session_token": "session-new",
                "cookie_header": "session=new",
                "device_id": "device-new",
                "csrf_token": "csrf-new",
            }
        )
        return SimpleNamespace(
            to_dict=lambda: {
                "created": {
                    "checkout_session_id": checkout_id,
                    "processor_entity": "openai_llc",
                    "provider": provider,
                    "checkout_url": (
                        f"https://chatgpt.com/checkout/openai_llc/{checkout_id}"
                    ),
                },
                "submitted": {
                    "phase": "submitted",
                    "provider": provider,
                    "promo_update": promo,
                    "payment_result": {"state": "succeeded"},
                    "session_after_payment": {
                        "status": "succeeded",
                        "has_access_token": True,
                        "has_cookie_header": True,
                    },
                },
            }
        )

    monkeypatch.setattr(checkout_workflow_module, "resolve_cliproxy_proxy", resolve_proxy)
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=Session,
        mail_provider=object(),
        promotion_updater=promotion_updater,
        protocol_checkout_runner=protocol_runner,
    )

    def sync_subscription(**_kwargs):
        order.append("subscription")
        assert account.access_token == "access-new"
        assert account.session_token == "session-new"
        assert account.cookie_header == "session=new"
        return {"status": "succeeded", "plan_type": "plus"}

    monkeypatch.setattr(workflow, "_sync_subscription_snapshot", sync_subscription)

    result = workflow.run(space_id="space-1")

    assert order == ["create", "promotion", "submit", "persist", "subscription"]
    assert promotion_calls == [
        {
            "proxy_url": "http://jp-proxy.example:8080",
            "checkout_url": (
                f"https://chatgpt.com/checkout/openai_llc/{checkout_id}"
            ),
            "access_token": "access-refreshed-before-promotion",
            "account_id": "account-1",
            "promo_campaign_id": "promo-space",
            "cookie_header": "session=promotion",
            "user_agent": "Protocol UA",
        }
    ]
    assert result["checkout_session_id"] == checkout_id
    assert result["checkout_result"]["provider"] == provider
    assert result["create_proxy_country"] == "US"
    assert result["promo_proxy_country"] == "JP"
    assert "access_token" not in result["session_refresh"]
    assert "cookie_header" not in result["session_refresh"]


def test_workflow_preserves_protocol_consume_stop_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol_error = checkout_workflow_module.PlusCheckoutError(
        "plus_checkout_result_unknown",
        "mutation result is unknown",
        {"stage": "fixture_mutation"},
        attempt_disposition="consume_stop",
    )

    def raise_protocol_error(*_args, **_kwargs):
        raise protocol_error

    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        protocol_checkout_runner=raise_protocol_error,
    )
    monkeypatch.setattr(
        workflow,
        "_load_context",
        lambda _space_id: {
            "user_account_id": "user-1",
            "email": "person@example.com",
            "external_space_id": "account-1",
            "access_token": "access-fixture",
            "session_token": "session-fixture",
            "cookie_header": "session=fixture",
            "auth_cookie_header": "auth=fixture",
            "device_id": "device-fixture",
            "payment_method_id": "pm_fixture",
            "promotion_id": "plus-1-month-free",
        },
    )
    monkeypatch.setattr(
        checkout_workflow_module,
        "resolve_cliproxy_proxy",
        lambda **_kwargs: SimpleNamespace(
            proxy_url="http://proxy.example:8080",
            country_code="US",
            sid_source="fixture",
            probe_attempts=1,
        ),
    )

    with pytest.raises(
        checkout_workflow_module.PersonalPlusCheckoutError
    ) as captured:
        workflow.run(space_id="space-1")

    assert captured.value.attempt_disposition == "consume_stop"
    assert captured.value.error_code == "plus_checkout_result_unknown"
    assert captured.value.diagnostics == {"stage": "fixture_mutation"}


def test_workflow_skips_remote_checkout_when_local_space_is_already_plus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        protocol_checkout_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("already-Plus space must not submit checkout")
        ),
    )
    monkeypatch.setattr(
        workflow,
        "_load_context",
        lambda _space_id: {
            "user_account_id": "user-1",
            "plan_type": "plus",
        },
    )
    monkeypatch.setattr(
        checkout_workflow_module,
        "resolve_cliproxy_proxy",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("already-Plus space does not need a payment proxy")
        ),
    )

    result = workflow.run(space_id="space-1")

    assert result["mode"] == "already_plus"
    assert result["already_plus"] is True
    assert result["subscription_sync"]["plan_type"] == "plus"


def test_post_payment_session_waits_for_final_browser_navigation() -> None:
    waits: list[tuple[str, int]] = []

    class Page:
        @staticmethod
        def wait_for_load_state(state, *, timeout):
            waits.append((state, timeout))

        @staticmethod
        def wait_for_timeout(timeout):
            waits.append(("settle", timeout))

    PersonalPlusCheckoutWorkflow._wait_for_browser_navigation(Page())

    assert waits == [
        ("domcontentloaded", 15_000),
        ("load", 15_000),
        ("networkidle", 5_000),
        ("settle", 3_000),
    ]


def test_failed_subscription_sync_fails_checkout_work() -> None:
    with __import__("pytest").raises(
        checkout_workflow_module.PersonalPlusCheckoutError,
        match="plus_checkout_subscription_sync_failed",
    ):
        PersonalPlusCheckoutWorkflow._require_subscription_sync(
            {
                "status": "failed",
                "error_type": "OpenAIChatGPTClientError",
                "error_message": "HTTP 401 token_expired",
            }
        )


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
    assert request["allow_redirects"] is False


def test_promotion_update_does_not_retry_transport_failure_by_default(monkeypatch) -> None:
    captured = {"post_calls": 0, "sessions": 0, "closed": 0}

    class Client:
        @staticmethod
        def post(_url, **kwargs):
            captured["post_calls"] += 1
            assert kwargs["allow_redirects"] is False
            raise RuntimeError("fixture response lost")

        @staticmethod
        def close():
            captured["closed"] += 1

    def create_session(*, proxy):
        assert proxy == "http://jp-proxy.example:8080"
        captured["sessions"] += 1
        return Client()

    monkeypatch.setattr(checkout_plugin_module, "create_http_session", create_session)

    with pytest.raises(RuntimeError, match="fixture response lost"):
        update_plus_checkout_promotion(
            proxy_url="http://jp-proxy.example:8080",
            checkout_url="https://chatgpt.com/checkout/openai_llc/cs_live_checkout_1",
            access_token="access-token",
            account_id="account-1",
            promo_campaign_id="plus-1-month-free",
            cookie_header="session=current",
        )

    assert captured == {"post_calls": 1, "sessions": 1, "closed": 1}


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
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=Session,
        mail_provider=object(),
        promotion_updater=promotion_updater,
    )
    monkeypatch.setattr(
        workflow,
        "_sync_subscription_snapshot",
        lambda **_kwargs: {"status": "succeeded", "plan_type": "plus"},
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
    assert result["session_refresh"]["status"] == "succeeded"
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


def test_subscription_sync_retries_empty_and_free_until_plus(monkeypatch) -> None:
    responses = [
        {},
        {"plan_type": "free", "has_active_subscription": False},
        {"plan_type": "plus", "has_active_subscription": True},
    ]
    calls = []
    sleeps = []

    class Provider:
        @staticmethod
        def fetch_subscription(**kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    monkeypatch.setattr(checkout_workflow_module.time, "sleep", sleeps.append)
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        openai_provider=Provider(),
    )

    result = workflow._fetch_active_plus_subscription(
        access_token="access-fixture",
        account_id="account-fixture",
        cookie_header="session=fixture",
        proxy_url="http://proxy.example:8080",
    )

    assert result["plan_type"] == "plus"
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_subscription_sync_persistent_free_is_not_success(monkeypatch) -> None:
    calls = []

    class Provider:
        @staticmethod
        def fetch_subscription(**kwargs):
            calls.append(kwargs)
            return {"plan_type": "free", "has_active_subscription": False}

    monkeypatch.setattr(checkout_workflow_module.time, "sleep", lambda _delay: None)
    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        openai_provider=Provider(),
    )

    with pytest.raises(
        checkout_workflow_module.PersonalPlusCheckoutError,
        match="plus_checkout_subscription_not_active_plus",
    ):
        workflow._fetch_active_plus_subscription(
            access_token="access-fixture",
            account_id="account-fixture",
            cookie_header="session=fixture",
            proxy_url="http://proxy.example:8080",
        )

    assert len(calls) == 5


def test_subscription_event_failure_is_best_effort() -> None:
    class Session:
        def __enter__(self):
            raise RuntimeError("fixture event database failure")

        def __exit__(self, *_args):
            return False

    workflow = PersonalPlusCheckoutWorkflow(
        session_factory=Session,
        mail_provider=object(),
    )

    workflow._write_subscription_event(
        run_id="run-1",
        work_id="work-1",
        space_id="space-1",
        result={"status": "failed"},
    )


def test_plus_checkout_job_route_is_registered() -> None:
    paths = {route.path for route in resources_router.routes if hasattr(route, "path")}
    assert "/spaces/{space_id}/plus-checkout-job" in paths


def test_plus_checkout_job_and_work_handlers_are_registered() -> None:
    runner = JobRunner(lambda: None)  # registration does not open a session
    register_core_handlers(runner, session_factory=lambda: None, settings=Settings())
    assert "space.personal_plus_checkout.tick" in runner._handlers
    assert "space.personal_plus_checkout.space" in runner._work_handlers


def test_payment_method_work_handler_runs_protocol_bind_before_plus_checkout(monkeypatch) -> None:
    captured: dict = {}
    settings = Settings()
    settings.personal_plus_checkout_captcha_api_url = "https://captcha.example"
    settings.personal_plus_checkout_captcha_client_key = "client-key-1"

    class PlusWorkflow:
        def __init__(self, **kwargs):
            captured["plus_created"] = kwargs

        def run(self, **kwargs):
            captured["plus_run"] = kwargs
            return {"status": "succeeded"}

    class BindWorkflow:
        def __init__(self, **kwargs):
            captured["bind_created"] = kwargs

        def run(self, **kwargs):
            captured["bind_run"] = kwargs
            return {"payment_method_status": "bound"}

    monkeypatch.setattr(handlers, "PersonalPlusCheckoutWorkflow", PlusWorkflow)
    monkeypatch.setattr(handlers, "PersonalPaymentMethodBindWorkflow", BindWorkflow)
    monkeypatch.setattr(
        handlers,
        "_mail_plugin",
        lambda _settings: (_ for _ in ()).throw(AssertionError("mail plugin must stay unused")),
    )
    monkeypatch.setattr(handlers, "_twofauth_otp_resolver", lambda _settings: None)
    runner = JobRunner(lambda: None)
    register_core_handlers(
        runner,
        session_factory=lambda: None,
        settings=settings,
    )

    result = runner._work_handlers["space.personal_payment_method_bind.space"](
        None,
        {"space_id": "space-1", "checkout_ui_mode": "custom"},
    )

    assert captured["plus_created"]["captcha_api_url"] == "https://captcha.example"
    assert captured["plus_created"]["captcha_client_key"] == "client-key-1"
    assert captured["plus_created"]["checkout_ui_mode"] == "custom"
    assert "mail_provider" not in captured["plus_created"]
    assert "captcha_api_url" not in captured["bind_created"]
    assert "captcha_client_key" not in captured["bind_created"]
    assert captured["bind_created"]["checkout_ui_mode"] == "custom"
    assert "mail_provider" not in captured["bind_created"]
    assert captured["bind_run"]["space_id"] == "space-1"
    assert captured["plus_run"]["space_id"] == "space-1"
    assert result == {
        "payment_method_status": "bound",
        "after_bind_success": {"status": "succeeded"},
    }


@pytest.mark.parametrize("checkout_ui_mode", ["hosted", "custom"])
def test_personal_plus_checkout_tick_job_propagates_settings_captcha_config(
    monkeypatch,
    checkout_ui_mode: str,
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

    result = handlers._run_personal_plus_checkout_tick_job(
        session_factory=lambda: FakeSession(),
        settings=settings,
        input_json={
            "_job_id": "job-1",
            "_run_id": "run-1",
            "space_id": "space-1",
            "limit": 1,
            "work_count": 1,
            "checkout_ui_mode": checkout_ui_mode,
            "checkout_attempt_mode": "new",
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
                "checkout_attempt_mode": "new",
                "create_proxy_country": "US",
                "promo_proxy_country": "JP",
                "promo_campaign_id": "plus-1-month-free",
                "checkout_ui_mode": checkout_ui_mode,
                "browser_headless": True,
                "captcha_api_url": "https://captcha.example",
                "captcha_client_key": "client-key-1",
                "_run_id": "run-1",
            },
        }
    ]
    assert result["checkout_attempt_mode"] == "new"


@pytest.mark.parametrize("checkout_ui_mode", ["hosted", "custom"])
def test_personal_payment_method_bind_tick_job_propagates_settings_captcha_config(
    monkeypatch,
    checkout_ui_mode: str,
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
            "checkout_ui_mode": checkout_ui_mode,
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
                "checkout_ui_mode": checkout_ui_mode,
                "browser_headless": True,
                "captcha_api_url": "https://captcha.example",
                "captcha_client_key": "client-key-1",
                "payment_card_id": "card-1",
                "_run_id": "run-1",
            },
        }
    ]
