from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from refactor_app.plugins.openai_auth_protocol.http_client import create_http_session

_SCRIPT_PATH = Path(__file__).with_name("personal_plus_checkout.js")
SUBMIT_PLUS_CHECKOUT_SCRIPT = _SCRIPT_PATH.read_text(encoding="utf-8")
_OAICS_SCRIPT_PATH = Path(__file__).with_name("personal_plus_checkout_oaics.js")
OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT = _OAICS_SCRIPT_PATH.read_text(encoding="utf-8")
_CREATE_SCRIPT_PATH = Path(__file__).with_name("personal_checkout_create.js")
CREATE_PLUS_CHECKOUT_SCRIPT = _CREATE_SCRIPT_PATH.read_text(encoding="utf-8")
_PLUS_CHECKOUT_CREATE_RESULT_KEY = "__plusPhOaicsCreateResult"

_PLUS_CHECKOUT_PLUGIN_CONFIG = {
    "oaics": {
        "script": OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT,
        "state_key": "__oaicsDefaultPaymentMethodMount",
        "host_id": "__oaics_default_payment_method_mount__",
    },
    "stripe": {
        "script": SUBMIT_PLUS_CHECKOUT_SCRIPT,
        "state_key": "__csLiveDefaultPaymentMethodMount",
        "host_id": "__cs_live_default_payment_method_mount__",
    },
}

READ_PLUS_CHECKOUT_PROVIDER_SCRIPT = r"""mw:() => {
  const match = location.pathname.match(/^\/checkout\/([^/]+)\/([^/]+)\/?$/);
  const checkoutId = String(match?.[2] || '');
  const provider = checkoutId.startsWith('oaics_')
    ? 'oaics'
    : checkoutId.startsWith('cs_live_')
      ? 'stripe'
      : '';
  return {
    provider,
    checkout_session_id: checkoutId,
    pathname: String(location.pathname || ''),
  };
}"""


def _plugin_mount_expression(script: str) -> str:
    source = str(script or "").strip()
    if not source.startswith("// Browser Console script:") or not source.endswith("})();"):
        raise RuntimeError("plus_checkout_plugin_script_invalid")
    return f"mw:async () => {{ return await {source[:-1]}; }}"


MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT = _plugin_mount_expression(SUBMIT_PLUS_CHECKOUT_SCRIPT)
MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT = _plugin_mount_expression(
    OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT
)


def _plugin_state_script(*, state_key: str, host_id: str) -> str:
    return rf"""mw:() => {{
  const state = window.{state_key};
  if (!state) return JSON.stringify({{ phase: 'missing', panel_visible: false, last_error: '' }});
  const status = typeof state.status === 'function' ? state.status() : {{}};
  const error = state.lastError;
  const checkoutConfirmRecord = Array.isArray(state.checkoutConfirmResponses)
    ? state.checkoutConfirmResponses.at(-1)
    : null;
  return JSON.stringify({{
    phase: String(state.phase || status?.phase || ''),
    panel_visible: Boolean(document.getElementById('{host_id}')),
    default_payment_method_id: String(state.defaultPaymentMethodId || ''),
    last_error: String(error?.message || error || ''),
    confirm_result: state.confirmResult || state.stripeConfirmResult || null,
    approval_requests: state.approvalRequests || [],
    session_after_confirm: state.sessionAfterConfirm || null,
    redirect_url: String(state.redirectUrl || ''),
    checkout_confirm: checkoutConfirmRecord?.response || checkoutConfirmRecord || null,
    confirmation_token: state.confirmationToken || null,
    elements_submit_result: state.elementsSubmitResult || null,
  }});
}}"""


def _plugin_submit_script(*, state_key: str, host_id: str) -> str:
    return rf"""mw:() => {{
  const state = window.{state_key};
  if (!state || typeof state.submitCheckout !== 'function') {{
    return false;
  }}
  const button = document.querySelector('#{host_id} [data-action="submit"]');
  if (!button || button.disabled) return false;
  button.click();
  return true;
}}"""


READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT = _plugin_state_script(
    state_key="__csLiveDefaultPaymentMethodMount",
    host_id="__cs_live_default_payment_method_mount__",
)
READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT = _plugin_state_script(
    state_key="__oaicsDefaultPaymentMethodMount",
    host_id="__oaics_default_payment_method_mount__",
)
INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT = _plugin_submit_script(
    state_key="__csLiveDefaultPaymentMethodMount",
    host_id="__cs_live_default_payment_method_mount__",
)
INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT = _plugin_submit_script(
    state_key="__oaicsDefaultPaymentMethodMount",
    host_id="__oaics_default_payment_method_mount__",
)

READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT = r"""mw:() => {
  const states = [
    window.__csLiveDefaultPaymentMethodMount,
    window.__oaicsDefaultPaymentMethodMount,
  ];
  const state = states.find((candidate) => candidate?.stripeSource?.publishableKey);
  const publishableKey = String(state?.stripeSource?.publishableKey || '');
  return {
    publishable_key: publishableKey,
    user_agent: String(navigator.userAgent || ''),
  };
}"""

RETRIEVE_OAICS_STRIPE_INTENT_SCRIPT = r"""mw:async ({ intentType, clientSecret }) => {
  const state = window.__oaicsDefaultPaymentMethodMount;
  const stripe = state?.stripe;
  if (!stripe) throw new Error('plus_checkout_stripe_instance_missing');
  const isSetup = intentType === 'setup_intent';
  const retrieve = isSetup ? stripe.retrieveSetupIntent : stripe.retrievePaymentIntent;
  if (typeof retrieve !== 'function') {
    throw new Error(`plus_checkout_stripe_retrieve_missing:${intentType}`);
  }
  const result = await retrieve.call(stripe, clientSecret);
  const intent = isSetup ? result?.setupIntent : result?.paymentIntent;
  const error = result?.error || null;
  return {
    intent_type: intentType,
    id: String(intent?.id || ''),
    status: String(intent?.status || ''),
    error: error
      ? {
          type: String(error.type || ''),
          code: String(error.code || ''),
          decline_code: String(error.decline_code || ''),
          message: String(error.message || ''),
        }
      : null,
    last_error: intent?.last_payment_error || intent?.last_setup_error || null,
  };
}"""

_STRIPE_VERSION_FULL = (
    "2025-03-31.basil; checkout_server_update_beta=v1; checkout_manual_approval_preview=v1"
)
_STRIPE_POLL_SUCCESS_STATES = {"succeeded"}
_STRIPE_POLL_FAILURE_STATES = {"failed", "expired", "canceled"}
_STRIPE_INTENT_FAILURE_STATES = {"canceled", "requires_payment_method"}

READ_PLUS_CHECKOUT_SESSION_SCRIPT = r"""async ({ expectedAccountId }) => {
  const response = await fetch('/api/auth/session', {
    credentials: 'include', cache: 'no-store',
  });
  const text = await response.text();
  let session = {};
  try { session = text ? JSON.parse(text) : {}; } catch (_) { session = {}; }
  if (!response.ok) {
    throw new Error(`GET /api/auth/session -> ${response.status}: ${text.slice(0, 500)}`);
  }
  const accessToken = String(session?.accessToken || '');
  const observedAccountId = String(session?.account?.id || '');
  if (expectedAccountId && observedAccountId && observedAccountId !== expectedAccountId) {
    throw new Error(`plus_checkout_account_mismatch:${expectedAccountId}:${observedAccountId}`);
  }
  const accountId = String(observedAccountId || expectedAccountId || '');
  if (!accessToken || !accountId) throw new Error('plus_checkout_session_missing');
  return {
    access_token: accessToken,
    account_id: accountId,
    user_agent: String(navigator.userAgent || ''),
  };
}"""
_CLEAR_PLUS_CHECKOUT_CREATE_RESULT_SCRIPT = (
    f"mw:() => {{ delete window.{_PLUS_CHECKOUT_CREATE_RESULT_KEY}; return true; }}"
)
_RUN_PLUS_CHECKOUT_CREATE_SCRIPT = (
    f"mw:() => {{ {CREATE_PLUS_CHECKOUT_SCRIPT.strip()} return true; }}"
)
_READ_PLUS_CHECKOUT_CREATE_RESULT_SCRIPT = (
    f"mw:() => window.{_PLUS_CHECKOUT_CREATE_RESULT_KEY} || null"
)


class PlusCheckoutPromotionUpdateError(RuntimeError):
    pass


class PlusCheckoutCreateError(RuntimeError):
    pass


class PlusCheckoutPluginError(RuntimeError):
    pass


def _compact_json(value: Any, *, limit: int = 2_000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    except (TypeError, ValueError):
        rendered = repr(value)
    return rendered[:limit]


def _read_plugin_state(page: Any, state_script: str) -> dict[str, Any]:
    raw_state = page.evaluate(state_script)
    if isinstance(raw_state, dict):
        return raw_state
    try:
        state = json.loads(str(raw_state or ""))
    except (TypeError, ValueError) as error:
        raise PlusCheckoutPluginError("plus_checkout_plugin_state_invalid") from error
    if not isinstance(state, dict):
        raise PlusCheckoutPluginError("plus_checkout_plugin_state_invalid")
    return state


def _poll_stripe_payment_page(
    page: Any,
    *,
    checkout_session_id: str,
    max_attempts: int,
    interval_s: float,
) -> dict[str, Any]:
    if not checkout_session_id.startswith(("cs_live_", "cs_test_")):
        raise PlusCheckoutPluginError("plus_checkout_stripe_poll_id_invalid")
    source = page.evaluate(READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT)
    if not isinstance(source, dict):
        raise PlusCheckoutPluginError("plus_checkout_stripe_poll_source_invalid")
    publishable_key = str(source.get("publishable_key") or "").strip()
    if not publishable_key.startswith(("pk_live_", "pk_test_")):
        raise PlusCheckoutPluginError("plus_checkout_stripe_publishable_key_missing")

    url = f"https://api.stripe.com/v1/payment_pages/{checkout_session_id}/poll"
    params = {
        "key": publishable_key,
        "_stripe_version": _STRIPE_VERSION_FULL,
    }
    headers = {
        "accept": "application/json",
        "origin": "https://js.stripe.com",
        "referer": "https://js.stripe.com/",
    }
    user_agent = str(source.get("user_agent") or "").strip()
    if user_agent:
        headers["user-agent"] = user_agent

    started_at = time.monotonic()
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        time.sleep(interval_s)
        try:
            response = page.context.request.get(
                url,
                params=params,
                headers=headers,
                timeout=15_000,
            )
        except Exception as error:
            attempts.append(
                {
                    "attempt": attempt,
                    "request_error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        status_code = int(response.status)
        text = response.text()
        try:
            payload = json.loads(text) if text else None
        except json.JSONDecodeError:
            payload = text
        record = {
            "attempt": attempt,
            "http_status": status_code,
            "response": payload,
        }
        attempts.append(record)
        if status_code != 200 or not isinstance(payload, dict):
            continue

        state = str(payload.get("state") or "").strip().lower()
        payment_status = str(payload.get("payment_object_status") or "").strip()
        result = {
            "provider": "stripe",
            "attempts": attempt,
            "elapsed_ms": round((time.monotonic() - started_at) * 1_000),
            "state": state,
            "payment_object_status": payment_status,
            "response": payload,
        }
        if state in _STRIPE_POLL_SUCCESS_STATES:
            return result
        if state in _STRIPE_POLL_FAILURE_STATES:
            raise PlusCheckoutPluginError("plus_checkout_payment_failed: " + _compact_json(result))

    raise PlusCheckoutPluginError(
        "plus_checkout_payment_poll_timeout: "
        + _compact_json({"attempts": max_attempts, "last": attempts[-1] if attempts else None})
    )


def _poll_oaics_stripe_intent(
    page: Any,
    *,
    checkout_confirm: Any,
    max_attempts: int,
    interval_s: float,
) -> dict[str, Any]:
    if not isinstance(checkout_confirm, dict):
        raise PlusCheckoutPluginError("plus_checkout_intent_poll_confirm_missing")
    intent_type = str(checkout_confirm.get("type") or "").strip()
    client_secret = str(checkout_confirm.get("client_secret") or "").strip()
    if intent_type not in {"payment_intent", "setup_intent"} or not client_secret:
        raise PlusCheckoutPluginError("plus_checkout_intent_poll_source_invalid")

    started_at = time.monotonic()
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        time.sleep(interval_s)
        try:
            payload = page.evaluate(
                RETRIEVE_OAICS_STRIPE_INTENT_SCRIPT,
                {"intentType": intent_type, "clientSecret": client_secret},
            )
        except Exception as error:
            attempts.append(
                {
                    "attempt": attempt,
                    "request_error": f"{type(error).__name__}: {error}",
                }
            )
            continue
        if not isinstance(payload, dict):
            payload = {"status": "", "invalid_response": payload}
        status = str(payload.get("status") or "").strip().lower()
        record = {"attempt": attempt, **payload}
        attempts.append(record)
        result = {
            "provider": "oaics",
            "attempts": attempt,
            "elapsed_ms": round((time.monotonic() - started_at) * 1_000),
            "state": "succeeded" if status == "succeeded" else status,
            "payment_object_status": status,
            "response": payload,
        }
        if status == "succeeded":
            return result
        if payload.get("error") or status in _STRIPE_INTENT_FAILURE_STATES:
            raise PlusCheckoutPluginError("plus_checkout_payment_failed: " + _compact_json(result))

    raise PlusCheckoutPluginError(
        "plus_checkout_payment_poll_timeout: "
        + _compact_json({"attempts": max_attempts, "last": attempts[-1] if attempts else None})
    )


def poll_plus_checkout_result(
    page: Any,
    *,
    provider: str,
    checkout_session_id: str,
    checkout_confirm: Any = None,
    max_attempts: int = 30,
    interval_s: float = 2.0,
) -> dict[str, Any]:
    """Wait for Stripe's terminal payment result before the browser can close."""
    attempts = max(1, int(max_attempts))
    interval = max(0.0, float(interval_s))
    if provider == "stripe":
        return _poll_stripe_payment_page(
            page,
            checkout_session_id=checkout_session_id,
            max_attempts=attempts,
            interval_s=interval,
        )
    if provider == "oaics":
        return _poll_oaics_stripe_intent(
            page,
            checkout_confirm=checkout_confirm,
            max_attempts=attempts,
            interval_s=interval,
        )
    raise PlusCheckoutPluginError(f"plus_checkout_poll_provider_unsupported:{provider}")


def create_plus_checkout_with_script(
    page: Any,
    *,
    expected_account_id: str,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Execute the shared Checkout creator script and read its window result."""
    expected = str(expected_account_id or "").strip()
    if not expected:
        raise PlusCheckoutCreateError("plus_checkout_expected_account_missing")
    page.goto("https://chatgpt.com/", wait_until="load", timeout=120_000)
    page.evaluate(
        f"mw:{READ_PLUS_CHECKOUT_SESSION_SCRIPT}",
        {"expectedAccountId": expected},
    )
    page.evaluate(_CLEAR_PLUS_CHECKOUT_CREATE_RESULT_SCRIPT)
    page.evaluate(_RUN_PLUS_CHECKOUT_CREATE_SCRIPT)
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    while True:
        result = page.evaluate(_READ_PLUS_CHECKOUT_CREATE_RESULT_SCRIPT)
        if isinstance(result, dict):
            break
        if time.monotonic() >= deadline:
            raise PlusCheckoutCreateError("plus_checkout_create_result_timeout")
        time.sleep(0.1)

    status = int(result.get("http_status") or 0)
    if result.get("ok") is not True or status < 200 or status >= 300:
        raise PlusCheckoutCreateError(f"plus_checkout_create_failed: HTTP {status}")
    checkout_id = str(result.get("checkout_session_id") or "").strip()
    checkout_url = str(result.get("checkout_url") or "").strip()
    if not checkout_id:
        raise PlusCheckoutCreateError("plus_checkout_create_id_missing")
    parsed = urlparse(checkout_url)
    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or len(parts) != 3
        or parts[0] != "checkout"
        or parts[2] != checkout_id
    ):
        raise PlusCheckoutCreateError("plus_checkout_create_url_invalid")
    return result


def submit_plus_checkout_with_plugin(
    page: Any,
    *,
    timeout_s: float = 120.0,
    result_poll_attempts: int = 30,
    result_poll_interval_s: float = 2.0,
) -> dict[str, Any]:
    """Dispatch the current Checkout to its OAICS or cs_live payment adapter."""
    detected = page.evaluate(READ_PLUS_CHECKOUT_PROVIDER_SCRIPT)
    if not isinstance(detected, dict):
        raise PlusCheckoutPluginError("plus_checkout_plugin_provider_result_invalid")
    provider = str(detected.get("provider") or "")
    config = _PLUS_CHECKOUT_PLUGIN_CONFIG.get(provider)
    if config is None:
        pathname = str(detected.get("pathname") or "")
        raise PlusCheckoutPluginError(f"plus_checkout_plugin_provider_unsupported: {pathname}")

    mount_script = _plugin_mount_expression(str(config["script"]))
    state_script = _plugin_state_script(
        state_key=str(config["state_key"]),
        host_id=str(config["host_id"]),
    )
    submit_script = _plugin_submit_script(
        state_key=str(config["state_key"]),
        host_id=str(config["host_id"]),
    )
    page.evaluate(mount_script)
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    while True:
        state = _read_plugin_state(page, state_script)
        phase = str(state.get("phase") or "")
        if phase == "ready":
            if state.get("panel_visible") is not True:
                raise PlusCheckoutPluginError("plus_checkout_plugin_panel_missing")
            break
        if phase in {"error", "failed", "load_error", "destroyed", "submit_failed"}:
            detail = str(state.get("last_error") or phase)
            raise PlusCheckoutPluginError(f"plus_checkout_plugin_{phase}: {detail}")
        if time.monotonic() >= deadline:
            raise PlusCheckoutPluginError(
                f"plus_checkout_plugin_ready_timeout: phase={phase or 'unknown'}"
            )
        time.sleep(0.1)

    started = page.evaluate(submit_script)
    if started is not True:
        raise PlusCheckoutPluginError(
            "plus_checkout_plugin_submit_unavailable: " + _compact_json(state)
        )

    submit_deadline = time.monotonic() + max(1.0, float(timeout_s))
    while True:
        result = _read_plugin_state(page, state_script)
        phase = str(result.get("phase") or "")
        if phase == "submitted":
            break
        if phase in {"error", "failed", "load_error", "destroyed", "submit_failed"}:
            detail = str(result.get("last_error") or phase)
            raise PlusCheckoutPluginError(
                f"plus_checkout_plugin_{phase}: {detail}; state={_compact_json(result)}"
            )
        if time.monotonic() >= submit_deadline:
            raise PlusCheckoutPluginError(
                "plus_checkout_plugin_submit_timeout: " + _compact_json(result)
            )
        time.sleep(0.1)
    result = {
        key: value
        for key, value in result.items()
        if key not in {"panel_visible", "default_payment_method_id", "last_error"}
    }
    payment_result = poll_plus_checkout_result(
        page,
        provider=provider,
        checkout_session_id=str(detected.get("checkout_session_id") or ""),
        checkout_confirm=result.get("checkout_confirm"),
        max_attempts=result_poll_attempts,
        interval_s=result_poll_interval_s,
    )
    return {
        "provider": provider,
        "checkout_session_id": str(detected.get("checkout_session_id") or ""),
        **result,
        "payment_result": payment_result,
    }


def update_plus_checkout_promotion(
    *,
    proxy_url: str,
    checkout_url: str,
    access_token: str,
    account_id: str,
    promo_campaign_id: str,
    cookie_header: str,
    user_agent: str = "",
    timeout_s: float = 60.0,
) -> Any:
    """Send only the promotion update request through the promotion proxy."""
    parsed = urlparse(str(checkout_url or "").strip())
    path_parts = [unquote(part) for part in parsed.path.split("/") if part]
    if parsed.netloc != "chatgpt.com" or len(path_parts) != 3 or path_parts[0] != "checkout":
        raise PlusCheckoutPromotionUpdateError("plus_checkout_url_invalid")

    processor_entity = path_parts[1]
    checkout_session_id = path_parts[2]
    if not checkout_session_id:
        raise PlusCheckoutPromotionUpdateError("plus_checkout_session_id_invalid")

    token = str(access_token or "").strip()
    target_account_id = str(account_id or "").strip()
    campaign_id = str(promo_campaign_id or "").strip()
    if not token or not target_account_id or not campaign_id:
        raise PlusCheckoutPromotionUpdateError("plus_checkout_promotion_context_missing")

    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "chatgpt-account-id": target_account_id,
        "origin": "https://chatgpt.com",
        "referer": str(checkout_url),
    }
    if str(cookie_header or "").strip():
        headers["cookie"] = str(cookie_header).strip()
    if str(user_agent or "").strip():
        headers["user-agent"] = str(user_agent).strip()

    client = create_http_session(proxy=str(proxy_url or "").strip())
    try:
        response = client.post(
            "https://chatgpt.com/backend-api/payments/checkout/update",
            headers=headers,
            json={
                "checkout_session_id": checkout_session_id,
                "processor_entity": processor_entity,
                "plan_name": "chatgptplusplan",
                "price_interval": "month",
                "seat_quantity": 1,
                "promo_campaign": {
                    "promo_campaign_id": campaign_id,
                    "is_coupon_from_query_param": False,
                },
            },
            timeout=float(timeout_s),
        )
        text = str(getattr(response, "text", "") or "")
        try:
            body = response.json() if text else None
        except Exception:
            body = text
        status_code = int(getattr(response, "status_code", 0) or 0)
        if status_code < 200 or status_code >= 300:
            raise PlusCheckoutPromotionUpdateError(
                f"POST /backend-api/payments/checkout/update -> {status_code}: {text[:500]}"
            )
        return body
    finally:
        client.close()


__all__ = [
    "CREATE_PLUS_CHECKOUT_SCRIPT",
    "INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT",
    "INVOKE_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT",
    "MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT",
    "MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT",
    "OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT",
    "PlusCheckoutCreateError",
    "PlusCheckoutPluginError",
    "PlusCheckoutPromotionUpdateError",
    "READ_OAICS_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT",
    "READ_PLUS_CHECKOUT_PROVIDER_SCRIPT",
    "READ_PLUS_CHECKOUT_PLUGIN_STATE_SCRIPT",
    "READ_PLUS_CHECKOUT_SESSION_SCRIPT",
    "SUBMIT_PLUS_CHECKOUT_SCRIPT",
    "create_plus_checkout_with_script",
    "submit_plus_checkout_with_plugin",
    "update_plus_checkout_promotion",
]
