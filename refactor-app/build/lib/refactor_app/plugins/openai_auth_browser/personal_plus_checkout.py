from __future__ import annotations

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


MOUNT_PLUS_CHECKOUT_PLUGIN_SCRIPT = _plugin_mount_expression(
    SUBMIT_PLUS_CHECKOUT_SCRIPT
)
MOUNT_OAICS_PLUS_CHECKOUT_PLUGIN_SCRIPT = _plugin_mount_expression(
    OAICS_SUBMIT_PLUS_CHECKOUT_SCRIPT
)


def _plugin_state_script(*, state_key: str, host_id: str) -> str:
    return rf"""mw:() => {{
  const state = window.{state_key};
  if (!state) return {{ phase: 'missing', panel_visible: false, last_error: '' }};
  const status = typeof state.status === 'function' ? state.status() : {{}};
  const error = state.lastError;
  return {{
    phase: String(state.phase || status?.phase || ''),
    panel_visible: Boolean(document.getElementById('{host_id}')),
    default_payment_method_id: String(state.defaultPaymentMethodId || ''),
    last_error: String(error?.message || error || ''),
  }};
}}"""


def _plugin_submit_script(*, state_key: str) -> str:
    return rf"""mw:async () => {{
  const state = window.{state_key};
  if (!state || typeof state.submitCheckout !== 'function') {{
    throw new Error('plus_checkout_plugin_submit_missing');
  }}
  const result = await state.submitCheckout();
  return {{
    phase: String(state.phase || ''),
    confirm_result: result?.confirmResult || result?.stripeConfirmResult || null,
    approval_requests: result?.approvalRequests || [],
    session_after_confirm: result?.sessionAfterConfirm || null,
    redirect_url: String(result?.redirectUrl || ''),
    checkout_confirm: result?.checkoutConfirm || null,
    confirmation_token: result?.confirmationToken || null,
    elements_submit_result: result?.elementsSubmitResult || null,
  }};
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
)
INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT = _plugin_submit_script(
    state_key="__oaicsDefaultPaymentMethodMount",
)

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
) -> dict[str, Any]:
    """Dispatch the current Checkout to its OAICS or cs_live payment adapter."""
    detected = page.evaluate(READ_PLUS_CHECKOUT_PROVIDER_SCRIPT)
    if not isinstance(detected, dict):
        raise PlusCheckoutPluginError("plus_checkout_plugin_provider_result_invalid")
    provider = str(detected.get("provider") or "")
    config = _PLUS_CHECKOUT_PLUGIN_CONFIG.get(provider)
    if config is None:
        pathname = str(detected.get("pathname") or "")
        raise PlusCheckoutPluginError(
            f"plus_checkout_plugin_provider_unsupported: {pathname}"
        )

    mount_script = _plugin_mount_expression(str(config["script"]))
    state_script = _plugin_state_script(
        state_key=str(config["state_key"]),
        host_id=str(config["host_id"]),
    )
    submit_script = _plugin_submit_script(state_key=str(config["state_key"]))
    page.evaluate(mount_script)
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    while True:
        state = page.evaluate(state_script)
        if not isinstance(state, dict):
            raise PlusCheckoutPluginError("plus_checkout_plugin_state_invalid")
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

    result = page.evaluate(submit_script)
    if not isinstance(result, dict):
        raise PlusCheckoutPluginError("plus_checkout_plugin_submit_result_invalid")
    if str(result.get("phase") or "") != "submitted":
        raise PlusCheckoutPluginError("plus_checkout_plugin_submit_not_completed")
    return {
        "provider": provider,
        "checkout_session_id": str(detected.get("checkout_session_id") or ""),
        **result,
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
