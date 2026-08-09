from __future__ import annotations

import json
import re
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlsplit

import requests

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
  const challengeBridge = window.__plusCheckoutCaptchaBridge;
  const challengeState = challengeBridge && typeof challengeBridge.snapshot === 'function'
    ? challengeBridge.snapshot()
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
    challenge_pending: Boolean(challengeState?.pending),
    challenge: challengeState?.challenge || null,
    challenge_injections: Array.isArray(challengeState?.injections)
      ? challengeState.injections
      : [],
  }});
}}"""

READ_BROWSER_USER_AGENT_SCRIPT = r"""mw:() => String(navigator.userAgent || '')"""

HAR_CONFIRMED_PUBLISHABLE_KEY = (
    "pk_live_51HOrSwC6h1nxGoI3lTAgRjYVrz4dU3fVOabyCcKR3pbEJguCVAlqCxdxCUvoRh1XWwRacViovU3kLKvpkjh7IqkW00iXQsjo3n"
)


def _plugin_submit_script(*, state_key: str, host_id: str) -> str:
    return rf"""mw:() => {{
  const state = window.{state_key};
  if (!state || typeof state.submitCheckout !== 'function') {{
    return false;
  }}
  if (state.__automationSubmitStarted === true) return false;
  const button = document.querySelector('#{host_id} [data-action="submit"]');
  if (!button || button.disabled) return false;
  state.__automationSubmitStarted = true;
  state.__automationSubmitStartedAt = new Date().toISOString();
  button.click();
  return true;
}}"""


def _is_plus_checkout_success_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    path = parsed.path.rstrip("/") or "/"
    query = dict(parse_qsl(parsed.query))
    if str(query.get("redirect_status") or "").lower() == "succeeded":
        return True
    if path == "/payments/success":
        return True
    return path == "/" and str(query.get("refresh_account") or "").lower() == "true"


def _is_checkout_navigation_context_error(error: BaseException) -> bool:
    detail = str(error or "").lower()
    return (
        "execution context was destroyed" in detail
        or "most likely because of a navigation" in detail
    )


def _page_url(page: Any) -> str:
    """Read the URL without letting a closing page mask the business result."""
    try:
        return str(getattr(page, "url", "") or "").strip()
    except Exception:
        return ""


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

INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT = r"""mw:() => {
  const BridgeKey = "__plusCheckoutCaptchaBridge";
  const existing = window[BridgeKey];
  if (existing?.version === 1 && typeof existing.snapshot === "function") {
    return existing.snapshot();
  }

  const now = () => new Date().toISOString();
  const safeString = (value, max = 4000) => {
    if (typeof value === "string") return value.slice(0, max);
    if (value == null) return "";
    return String(value).slice(0, max);
  };
  const readQuery = (urlText, key) => {
    try {
      return new URL(urlText, location.href).searchParams.get(key) || "";
    } catch {
      return "";
    }
  };

  const bridge = {
    version: 1,
    installedAt: now(),
    widgets: [],
    injections: [],
    lastChallenge: null,
    ticker: null,
    bestChallenge(provider = "") {
      const normalizedProvider = safeString(provider, 32).toLowerCase();
      const candidates = this.widgets.filter((candidate) => {
        if (!candidate || !candidate.provider) return false;
        return !normalizedProvider || candidate.provider === normalizedProvider;
      });
      if (candidates.length === 0) {
        return this.lastChallenge ? { ...this.lastChallenge } : null;
      }
      const ranked = [...candidates].reverse();
      const pendingWithSiteKey = ranked.find(
        (candidate) => candidate.site_key && candidate.token_injected !== true,
      );
      if (pendingWithSiteKey) return { ...pendingWithSiteKey };
      const latestWithSiteKey = ranked.find((candidate) => candidate.site_key);
      if (latestWithSiteKey) return { ...latestWithSiteKey };
      const pendingWithoutSiteKey = ranked.find(
        (candidate) => candidate.token_injected !== true,
      );
      if (pendingWithoutSiteKey) return { ...pendingWithoutSiteKey };
      return { ...ranked[0] };
    },
    record(provider, payload = {}) {
      const widgetId = payload.widget_id == null ? "" : safeString(payload.widget_id, 200);
      const siteKey = safeString(payload.site_key || payload.sitekey || payload.k || "", 512);
      const entry = {
        provider: safeString(provider, 32).toLowerCase(),
        widget_id: widgetId,
        site_key: siteKey,
        page_url: safeString(payload.page_url || location.href, 2000),
        rqdata: safeString(payload.rqdata || "", 4000),
        action: safeString(payload.action || "", 256),
        source: safeString(payload.source || "unknown", 64),
        enterprise: Boolean(payload.enterprise),
        invisible:
          payload.invisible === true ||
          safeString(payload.size || "", 64).toLowerCase() === "invisible",
        callback: typeof payload.callback === "function" ? payload.callback : null,
        success_callback:
          typeof payload.success_callback === "function" ? payload.success_callback : null,
        expired_callback:
          typeof payload.expired_callback === "function" ? payload.expired_callback : null,
        error_callback:
          typeof payload.error_callback === "function" ? payload.error_callback : null,
        token_injected: Boolean(payload.token_injected),
        at: now(),
      };
      const index = this.widgets.findIndex((candidate) => {
        if (!candidate || candidate.provider !== entry.provider) return false;
        if (entry.widget_id && candidate.widget_id) return candidate.widget_id === entry.widget_id;
        if (entry.site_key && candidate.site_key) return candidate.site_key === entry.site_key;
        return false;
      });
      if (index >= 0) {
        const current = this.widgets[index];
        this.widgets[index] = {
          ...current,
          ...entry,
          widget_id: entry.widget_id || current.widget_id,
          site_key: entry.site_key || current.site_key,
          rqdata: entry.rqdata || current.rqdata,
          action: entry.action || current.action,
          page_url: entry.page_url || current.page_url,
          enterprise: current.enterprise || entry.enterprise,
          invisible: entry.invisible,
          callback: entry.callback || current.callback || null,
          success_callback: entry.success_callback || current.success_callback || null,
          expired_callback: entry.expired_callback || current.expired_callback || null,
          error_callback: entry.error_callback || current.error_callback || null,
          token_injected: current.token_injected || entry.token_injected,
        };
      } else {
        this.widgets.push(entry);
      }
      this.lastChallenge = this.bestChallenge(entry.provider) || { ...entry };
      return this.lastChallenge;
    },
    wrapApi(provider, api) {
      if (!api || (typeof api !== "object" && typeof api !== "function")) return;
      if (api.__plusCheckoutCaptchaBridgeWrapped === true) return;
      try {
        Object.defineProperty(api, "__plusCheckoutCaptchaBridgeWrapped", {
          value: true,
          configurable: true,
        });
      } catch {
        api.__plusCheckoutCaptchaBridgeWrapped = true;
      }

      if (typeof api.render === "function") {
        const originalRender = api.render;
        api.render = (...args) => {
          const [, rawConfig] = args;
          const config = rawConfig && typeof rawConfig === "object" ? rawConfig : {};
          const widgetId = originalRender.apply(api, args);
          bridge.record(provider, {
            source: "render",
            widget_id: widgetId,
            site_key: config.sitekey || config.siteKey || "",
            rqdata: config.rqdata || "",
            action: config.action || "",
            size: config.size || "",
            invisible: config.invisible === true,
            enterprise:
              provider === "recaptcha"
              && (config.enterprise === true || api === window.grecaptcha?.enterprise),
            callback: config.callback,
            success_callback: config.callback,
            expired_callback: config["expired-callback"] || config.expiredCallback,
            error_callback: config["error-callback"] || config.errorCallback,
            page_url: location.href,
          });
          return widgetId;
        };
      }

      if (typeof api.execute === "function") {
        const originalExecute = api.execute;
        api.execute = (...args) => {
          const [widgetId, rawConfig] = args;
          const config = rawConfig && typeof rawConfig === "object" ? rawConfig : {};
          bridge.record(provider, {
            source: "execute",
            widget_id: widgetId,
            site_key: config.sitekey || config.siteKey || "",
            rqdata: config.rqdata || "",
            action: config.action || "",
            invisible: true,
            enterprise:
              provider === "recaptcha"
              && (config.enterprise === true || api === window.grecaptcha?.enterprise),
            page_url: location.href,
          });
          return originalExecute.apply(api, args);
        };
      }

      for (const [methodName, fieldName] of [
        ["getResponse", "injected_token"],
        ["getRespKey", "injected_resp_key"],
      ]) {
        if (typeof api[methodName] !== "function") continue;
        const originalMethod = api[methodName];
        api[methodName] = (...args) => {
          const requestedWidgetId = safeString(args[0] ?? "", 200);
          const candidate = [...bridge.widgets].reverse().find((item) => {
            if (!item || item.provider !== provider || !item[fieldName]) return false;
            return !requestedWidgetId || item.widget_id === requestedWidgetId;
          });
          if (candidate) return candidate[fieldName];
          return originalMethod.apply(api, args);
        };
      }
    },
    refresh() {
      try {
        this.wrapApi("hcaptcha", window.hcaptcha);
      } catch {}
      try {
        const recaptcha = window.grecaptcha?.enterprise || window.grecaptcha;
        this.wrapApi("recaptcha", recaptcha);
      } catch {}

      const frames = Array.from(document.querySelectorAll("iframe[src]"));
      for (const frame of frames) {
        const src = safeString(frame.getAttribute("src") || "", 2000);
        if (!src) continue;
        if (/hcaptcha/i.test(src)) {
          this.record("hcaptcha", {
            source: "iframe",
            site_key:
              readQuery(src, "sitekey")
              || readQuery(src, "siteKey")
              || safeString(frame.getAttribute("data-sitekey") || "", 512),
            rqdata: readQuery(src, "rqdata"),
            invisible:
              /invisible/i.test(src)
              || safeString(frame.getAttribute("data-size") || "", 64).toLowerCase()
                === "invisible",
            page_url: location.href,
          });
        } else if (/recaptcha/i.test(src)) {
          this.record("recaptcha", {
            source: "iframe",
            site_key:
              readQuery(src, "k")
              || readQuery(src, "sitekey")
              || safeString(frame.getAttribute("data-sitekey") || "", 512),
            action: readQuery(src, "action"),
            enterprise: /enterprise/i.test(src),
            page_url: location.href,
          });
        }
      }
    },
    snapshot() {
      this.refresh();
      const challenge = this.bestChallenge();
      if (challenge) {
        delete challenge.callback;
        delete challenge.success_callback;
        delete challenge.expired_callback;
        delete challenge.error_callback;
      }
      return {
        installed_at: this.installedAt,
        pending: Boolean(
          challenge && challenge.provider && challenge.site_key && !challenge.token_injected,
        ),
        challenge,
        injections: this.injections.slice(-5).map((item) => ({ ...item })),
      };
    },
    async injectToken(payload = {}) {
      this.refresh();
      const provider = safeString(
        payload.provider || this.lastChallenge?.provider || "",
        32,
      ).toLowerCase();
      const token = safeString(
        payload.token || payload.gRecaptchaResponse || payload.hcaptchaToken || "",
        100000,
      );
      const widgetId = safeString(payload.widget_id || "", 200);
      const siteKey = safeString(payload.site_key || payload.sitekey || payload.k || "", 512);
      const respKey = safeString(payload.resp_key || payload.respKey || "", 100000);
      if (!provider) throw new Error("plus_checkout_captcha_provider_missing");
      if (!token) throw new Error("plus_checkout_captcha_token_missing");
      const providerWidgets = [...this.widgets].reverse().filter(
        (candidate) => candidate?.provider === provider,
      );
      const widget =
        providerWidgets.find((candidate) => widgetId && candidate?.widget_id === widgetId)
        || providerWidgets.find((candidate) => siteKey && candidate?.site_key === siteKey)
        || providerWidgets.find((candidate) => candidate?.site_key || candidate?.widget_id)
        || this.bestChallenge(provider)
        || this.lastChallenge;
      const fieldNames = provider === "hcaptcha"
        ? ["h-captcha-response", "hcaptcha-response", "g-recaptcha-response"]
        : ["g-recaptcha-response"];
      const touched = [];
      for (const name of fieldNames) {
        const nodes = Array.from(
          document.querySelectorAll(`textarea[name="${name}"], input[name="${name}"]`),
        );
        for (const node of nodes) {
          node.value = token;
          node.textContent = token;
          node.dispatchEvent(new Event("input", { bubbles: true }));
          node.dispatchEvent(new Event("change", { bubbles: true }));
          touched.push(node);
        }
      }

      const selectedWidgetId = safeString(widget?.widget_id || widgetId, 200);
      const selectedSiteKey = safeString(widget?.site_key || siteKey, 512);
      const widgetMatches = (candidate) => {
        if (!candidate || candidate.provider !== provider) return false;
        if (selectedWidgetId && candidate.widget_id === selectedWidgetId) return true;
        return Boolean(selectedSiteKey && candidate.site_key === selectedSiteKey);
      };
      this.widgets = this.widgets.map((candidate) => (
        widgetMatches(candidate)
          ? {
              ...candidate,
              injected_token: token,
              injected_resp_key: respKey,
            }
          : candidate
      ));

      let callbackInvoked = false;
      for (const fn of [widget?.callback, widget?.success_callback]) {
        if (typeof fn !== "function") continue;
        const result = fn(token);
        callbackInvoked = true;
        if (result && typeof result.then === "function") {
          await result;
        }
      }

      const tokenApplied = Boolean(widget && callbackInvoked);
      this.injections.push({
        at: now(),
        provider,
        widget_id: safeString(widget?.widget_id || "", 200),
        site_key: safeString(widget?.site_key || siteKey, 512),
        token_length: token.length,
        field_count: touched.length,
        callback_invoked: callbackInvoked,
        token_applied: tokenApplied,
      });
      if (!tokenApplied) {
        this.widgets = this.widgets.map((candidate) => (
          widgetMatches(candidate)
            ? {
                ...candidate,
                injected_token: "",
                injected_resp_key: "",
              }
            : candidate
        ));
        return {
          ok: false,
          provider,
          widget_id: safeString(widget?.widget_id || "", 200),
          site_key: safeString(widget?.site_key || siteKey, 512),
          field_count: touched.length,
          callback_invoked: callbackInvoked,
          resp_key_present: Boolean(respKey),
          error: "plus_checkout_captcha_token_not_applied",
        };
      }
      this.widgets = this.widgets.map((candidate) => {
        if (!widgetMatches(candidate)) return candidate;
        return {
          ...candidate,
          token_injected: true,
          injected_at: now(),
        };
      });
      const bestRemaining = this.bestChallenge(provider);
      if (bestRemaining) {
        this.lastChallenge = bestRemaining;
      } else if (widget) {
        this.lastChallenge = {
          ...widget,
          token_injected: true,
          injected_at: now(),
        };
      }
      return {
        ok: true,
        provider,
        widget_id: safeString(widget?.widget_id || "", 200),
        site_key: safeString(widget?.site_key || siteKey, 512),
        field_count: touched.length,
        callback_invoked: callbackInvoked,
        resp_key_present: Boolean(respKey),
        token_applied: true,
      };
    },
  };

  bridge.ticker = window.setInterval(() => {
    try {
      bridge.refresh();
    } catch {}
  }, 250);
  window[BridgeKey] = bridge;
  return bridge.snapshot();
}"""

INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT = r"""mw:(payload) => {
  const bridge = window.__plusCheckoutCaptchaBridge;
  if (!bridge || typeof bridge.injectToken !== "function") {
    throw new Error("plus_checkout_captcha_bridge_missing");
  }
  const requestId = String(payload?.request_id || "");
  if (!requestId) throw new Error("plus_checkout_captcha_request_id_missing");
  const store = window.__plusCheckoutAsyncResults || (window.__plusCheckoutAsyncResults = {});
  store[requestId] = { status: "pending" };
  Promise.resolve()
    .then(() => bridge.injectToken(payload || {}))
    .then((value) => { store[requestId] = { status: "fulfilled", value }; })
    .catch((error) => {
      store[requestId] = {
        status: "rejected",
        error: String(error?.stack || error?.message || error),
      };
    });
  return JSON.stringify({ started: true, request_id: requestId });
}"""

READ_PLUS_CHECKOUT_ASYNC_RESULT_SCRIPT = r"""mw:(requestId) => {
  const value = window.__plusCheckoutAsyncResults?.[String(requestId || "")] || null;
  return JSON.stringify(value);
}"""

MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT = r"""mw:(verification) => {
  const states = [
    window.__oaicsDefaultPaymentMethodMount,
    window.__csLiveDefaultPaymentMethodMount,
  ];
  const state = states.find((candidate) => candidate && candidate.stripe);
  if (!state) return JSON.stringify({ ok: false, error: "plus_checkout_state_missing" });
  const intentType = String(verification?.intent_type || "");
  const intent = {
    id: String(verification?.intent_id || ""),
    status: String(verification?.intent_status || ""),
  };
  state.challengeVerification = { ...verification };
  if (intentType === "setup_intent") {
    state.stripeConfirmResult = { setupIntent: intent, error: null };
  } else if (intentType === "payment_intent") {
    state.stripeConfirmResult = { paymentIntent: intent, error: null };
  }
  state.phase = "challenge_verified";
  state.lastError = null;
  return JSON.stringify({ ok: true, phase: state.phase });
}"""

CONTINUE_PLUS_CHECKOUT_STRIPE_INTENT_SCRIPT = r"""mw:(payload) => {
  const states = [
    window.__oaicsDefaultPaymentMethodMount,
    window.__csLiveDefaultPaymentMethodMount,
  ];
  const state = states.find((candidate) => candidate && candidate.stripe);
  const requestId = String(payload?.request_id || "");
  if (!requestId) throw new Error("plus_checkout_continuation_request_id_missing");
  const store = window.__plusCheckoutAsyncResults || (window.__plusCheckoutAsyncResults = {});
  if (!state || typeof state.stripe.handleNextAction !== "function") {
    store[requestId] = {
      status: "rejected",
      error: "plus_checkout_stripe_handle_next_action_missing",
    };
    return JSON.stringify({ started: true, request_id: requestId });
  }
  store[requestId] = { status: "pending" };
  Promise.resolve()
    .then(() => state.stripe.handleNextAction({
      clientSecret: String(payload.client_secret || ""),
    }))
    .then((value) => {
      state.stripeConfirmResult = value || null;
      if (value?.error) {
        state.phase = "submit_failed";
        state.lastError = value.error.message || String(value.error);
      } else {
        state.phase = "submitted";
        state.lastError = null;
      }
      store[requestId] = { status: "fulfilled", value: value || null };
    })
    .catch((error) => {
      state.phase = "submit_failed";
      state.lastError = String(error?.stack || error?.message || error);
      store[requestId] = {
        status: "rejected",
        error: String(error?.stack || error?.message || error),
      };
    });
  return JSON.stringify({ started: true, request_id: requestId });
}"""

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
_PROMOTION_UPDATE_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

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


_CHALLENGE_URL_MARKERS = (
    "captcha",
    "challenge",
    "challenge-platform",
)
_CHALLENGE_HOST_MARKERS = (
    "hcaptcha.com",
    "recaptcha.net",
    "google.com/recaptcha",
)
_CHALLENGE_TEXT_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_MAX_CHALLENGE_EVENTS = 32
_CHALLENGE_RETRY_ERROR_MARKERS = ("captcha", "challenge", "recaptcha", "hcaptcha")
_STRIPE_HCAPTCHA_WRAPPER_PATH_RE = re.compile(
    r"^/stripethirdparty-srv/assets/[^/]+/HCaptcha(?:Invisible)?\.html$",
    re.IGNORECASE,
)


def _challenge_url(url: Any) -> tuple[str, str] | None:
    """Return a query-free challenge URL and its provider kind."""
    try:
        parsed = urlsplit(str(url or ""))
    except Exception:
        return None
    host = str(parsed.netloc or "").lower()
    path = str(parsed.path or "").lower()
    haystack = f"{host}{path}"
    if not any(marker in haystack for marker in _CHALLENGE_URL_MARKERS):
        return None
    if any(marker in host for marker in _CHALLENGE_HOST_MARKERS):
        kind = "hcaptcha" if "hcaptcha.com" in host else "recaptcha"
    elif "captcha" in haystack:
        kind = "captcha"
    else:
        kind = "challenge"
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.scheme else parsed.path
    return safe_url, kind


def _stripe_hcaptcha_wrapper(url: Any) -> dict[str, Any] | None:
    """Return the safe Stripe hCaptcha wrapper URL observed by the browser.

    Stripe loads the actual hCaptcha widget in this wrapper and passes the
    site key/rqdata to it at runtime. The wrapper is therefore the solver's
    page, while ``api.hcaptcha.com/checksiteconfig`` is only a discovery
    request and must never be used as ``websiteURL``.
    """
    try:
        parsed = urlsplit(str(url or "").strip())
    except Exception:
        return None
    if (
        parsed.scheme.lower() != "https"
        or parsed.netloc.lower() != "b.stripecdn.com"
        or not _STRIPE_HCAPTCHA_WRAPPER_PATH_RE.fullmatch(parsed.path)
    ):
        return None
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    wrapper_id = str(params.get("id") or "").strip()
    origin = str(params.get("origin") or "").strip()
    if not wrapper_id or not origin:
        return None
    safe_query = urlencode({"id": wrapper_id, "origin": origin})
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{safe_query}"
    return {
        "url": safe_url,
        "invisible": parsed.path.lower().endswith("hcaptchaInvisible.html".lower()),
    }


class _CheckoutChallengeCapture:
    """Capture only challenge request metadata, independently of browser logs."""

    def __init__(self, page: Any) -> None:
        self._page = page
        self._events: list[dict[str, Any]] = []
        self._candidates: list[dict[str, Any]] = []
        self._wrapper_urls: list[dict[str, Any]] = []
        self._handlers: list[tuple[str, Any]] = []
        self._closed = False

    def install(self) -> None:
        on = getattr(self._page, "on", None)
        if not callable(on):
            return
        handlers = {
            "request": self._on_request,
            "response": self._on_response,
            "requestfailed": self._on_request_failed,
            "console": self._on_console,
        }
        for event, handler in handlers.items():
            on(event, handler)
            self._handlers.append((event, handler))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        remove = getattr(self._page, "remove_listener", None)
        if not callable(remove):
            self._handlers.clear()
            return
        for event, handler in self._handlers:
            try:
                remove(event, handler)
            except Exception:
                pass
        self._handlers.clear()

    def snapshot(self) -> dict[str, Any]:
        kinds = sorted(
            {
                str(event["kind"]) for event in self._events
            }
            | {
                str(candidate["provider"]) for candidate in self._candidates
                if str(candidate.get("provider") or "").strip()
            }
        )
        snapshot = {
            "challenge_detected": bool(self._events or self._candidates),
            "challenge_request_count": len(self._events),
            "challenge_kinds": kinds,
            "challenge_requests": list(self._events),
        }
        if self._wrapper_urls:
            snapshot["challenge_wrapper_urls"] = [
                dict(item) for item in self._wrapper_urls[-4:]
            ]
        if self._candidates:
            snapshot["challenge_candidates"] = [
                {
                    key: value
                    for key, value in candidate.items()
                    if key not in {"client_secret"}
                }
                for candidate in self._candidates[-8:]
            ]
        return snapshot

    def best_challenge(self, *, page_url: str = "") -> dict[str, Any] | None:
        candidates = [item for item in self._candidates if str(item.get("site_key") or "").strip()]
        if not candidates:
            return None
        ranked = list(reversed(candidates))
        preferred = next(
            (
                item
                for item in ranked
                if (
                    str(item.get("rqdata") or "").strip()
                    or str(item.get("verify_url") or "").strip()
                )
            ),
            None,
        )
        challenge = dict(preferred or ranked[0])
        if page_url and not str(challenge.get("page_url") or "").strip():
            challenge["page_url"] = str(page_url).strip()
        if self._wrapper_urls and str(challenge.get("provider") or "").lower() == "hcaptcha":
            wrapper = self._wrapper_urls[-1]
            challenge["solver_page_url"] = str(wrapper["url"])
            challenge["stripe_hcaptcha_wrapper_url"] = str(wrapper["url"])
            if wrapper.get("invisible") is True:
                challenge["invisible"] = True
        return challenge

    def _record(
        self,
        request: Any,
        *,
        event: str,
        status: int | None = None,
        failure: str = "",
    ) -> None:
        if self._closed:
            return
        try:
            request_url = getattr(request, "url", "")
            match = _challenge_url(request_url)
            if match is None or len(self._events) >= _MAX_CHALLENGE_EVENTS:
                return
            safe_url, kind = match
            item: dict[str, Any] = {
                "event": event,
                "kind": kind,
                "url": safe_url,
                "method": str(getattr(request, "method", "") or "").upper(),
                "resource_type": str(getattr(request, "resource_type", "") or ""),
            }
            if status is not None:
                item["status"] = int(status)
            if failure:
                item["failure"] = str(failure)[:300]
            self._events.append(item)
            wrapper = _stripe_hcaptcha_wrapper(request_url)
            if wrapper is not None:
                if not any(item["url"] == wrapper["url"] for item in self._wrapper_urls):
                    self._wrapper_urls.append(wrapper)
                    if len(self._wrapper_urls) > 8:
                        self._wrapper_urls = self._wrapper_urls[-8:]
            candidate = self._candidate_from_url(request_url, source=event)
            if candidate is not None:
                self._record_candidate(candidate)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            # Late response events are normal while a page is being torn down.
            # Challenge capture is observability only and must never escape.
            return

    def _on_request(self, request: Any) -> None:
        self._record(request, event="request")

    def _on_response(self, response: Any) -> None:
        try:
            request = getattr(response, "request", None)
            status = getattr(response, "status", None)
        except BaseException:
            return
        self._record(request, event="response", status=status)

    def _on_request_failed(self, request: Any) -> None:
        try:
            failure = getattr(request, "failure", "")
        except BaseException:
            return
        self._record(request, event="requestfailed", failure=failure)

    def _on_console(self, message: Any) -> None:
        text_attr = getattr(message, "text", "")
        try:
            text = text_attr() if callable(text_attr) else text_attr
        except Exception:
            text = text_attr
        text = str(text or "")
        urls = list(_CHALLENGE_TEXT_URL_RE.findall(text))
        location_attr = getattr(message, "location", None)
        location = None
        try:
            location = location_attr() if callable(location_attr) else location_attr
        except Exception:
            location = location_attr
        if isinstance(location, dict):
            location_url = str(location.get("url") or "").strip()
            if location_url:
                urls.append(location_url)
        for url in urls:
            candidate = self._candidate_from_url(url, source="console")
            if candidate is not None:
                self._record_candidate(candidate)

    def _candidate_from_url(self, url_text: Any, *, source: str) -> dict[str, Any] | None:
        try:
            parsed = urlsplit(str(url_text or "").strip())
        except Exception:
            return None
        host = str(parsed.netloc or "").lower()
        path = str(parsed.path or "").lower()
        haystack = f"{host}{path}"
        provider = ""
        if "hcaptcha" in haystack:
            provider = "hcaptcha"
        elif "recaptcha" in haystack:
            provider = "recaptcha"
        if not provider:
            return None
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        fragment = dict(parse_qsl(parsed.fragment, keep_blank_values=True))
        params = {**query, **fragment}
        site_key = str(
            params.get("sitekey")
            or params.get("siteKey")
            or params.get("k")
            or ""
        ).strip()
        if not site_key:
            return None
        origin = str(params.get("origin") or "").strip()
        solver_page_url = ""
        try:
            origin_url = urlsplit(origin)
            if origin_url.scheme == "https" and origin_url.netloc:
                solver_page_url = f"{origin_url.scheme}://{origin_url.netloc}/"
        except Exception:
            solver_page_url = ""
        if not solver_page_url and parsed.scheme == "https" and host in {
            "js.stripe.com",
            "b.stripecdn.com",
        }:
            # Stripe hosts the hCaptcha wrapper in a cross-origin frame. The
            # Checkout page is the caller, not the page on which this widget
            # is registered.
            solver_page_url = f"{parsed.scheme}://{parsed.netloc}/"
        return {
            "provider": provider,
            "site_key": site_key,
            "rqdata": str(params.get("rqdata") or "").strip(),
            "action": str(params.get("action") or "").strip(),
            "verify_url": str(params.get("verifyUrl") or "").strip(),
            "intent_id": str(params.get("intentId") or "").strip(),
            "client_secret": str(params.get("clientSecret") or "").strip(),
            "solver_page_url": solver_page_url,
            "page_url": (
                f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if parsed.scheme
                else parsed.path
            ),
            "source": str(source or "").strip(),
            "enterprise": provider == "recaptcha" and ("enterprise" in haystack),
            "invisible": (
                "invisible" in haystack
                or str(params.get("size") or "").strip().lower() == "invisible"
            ),
        }

    def _record_candidate(self, candidate: dict[str, Any]) -> None:
        provider = str(candidate.get("provider") or "").strip().lower()
        site_key = str(candidate.get("site_key") or "").strip()
        if not provider or not site_key:
            return
        match_index = -1
        candidate_intent_id = str(candidate.get("intent_id") or "").strip()
        candidate_verify_url = str(candidate.get("verify_url") or "").strip()
        for index, current in enumerate(self._candidates):
            if (
                str(current.get("provider") or "").strip().lower() != provider
                or str(current.get("site_key") or "").strip() != site_key
            ):
                continue
            current_intent_id = str(current.get("intent_id") or "").strip()
            current_verify_url = str(current.get("verify_url") or "").strip()
            if candidate_intent_id and current_intent_id:
                if candidate_intent_id == current_intent_id:
                    match_index = index
                    break
                continue
            if candidate_verify_url and current_verify_url:
                if candidate_verify_url == current_verify_url:
                    match_index = index
                    break
                continue
            if not candidate_intent_id and not current_intent_id:
                match_index = index
                break
        if match_index >= 0:
            current = self._candidates[match_index]
            merged = dict(current)
            for key, value in candidate.items():
                if value not in ("", None):
                    merged[key] = value
            self._candidates[match_index] = merged
            return
        self._candidates.append(dict(candidate))
        if len(self._candidates) > _MAX_CHALLENGE_EVENTS:
            self._candidates = self._candidates[-_MAX_CHALLENGE_EVENTS :]


def _compact_json(value: Any, *, limit: int = 2_000) -> str:
    def sanitize(item: Any, key: str = "") -> Any:
        if key.lower() in {
            "client_secret",
            "token",
            "g_recaptcha_response",
            "grecaptcharesponse",
            "hcaptchatoken",
            "resp_key",
            "respkey",
            "cookie",
            "authorization",
        }:
            return "<redacted>"
        if isinstance(item, dict):
            return {str(name): sanitize(child, str(name)) for name, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [sanitize(child) for child in item]
        return item

    try:
        rendered = json.dumps(
            sanitize(value),
            ensure_ascii=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        rendered = repr(value)
    return rendered[:limit]


def _merge_challenge_details(
    primary: dict[str, Any] | None,
    fallback: dict[str, Any] | None,
    *,
    page_url: str = "",
) -> dict[str, Any] | None:
    base = primary if isinstance(primary, dict) else None
    extra = fallback if isinstance(fallback, dict) else None
    if base is None and extra is None:
        return None
    merged: dict[str, Any] = dict(extra or {})
    for key, value in (base or {}).items():
        if key == "page_url":
            if value not in ("", None, [], {}) and not str(merged.get(key) or "").strip():
                merged[key] = value
            continue
        if value not in ("", None, [], {}):
            merged[key] = value
        elif key not in merged:
            merged[key] = value
    if page_url and not str(merged.get("page_url") or "").strip():
        merged["page_url"] = str(page_url).strip()
    return merged


def _hydrate_checkout_challenge_state(
    state: dict[str, Any],
    *,
    challenge_capture: _CheckoutChallengeCapture,
    page_url: str,
) -> dict[str, Any]:
    hydrated = dict(state)
    fallback = challenge_capture.best_challenge(page_url=page_url)
    merged = _merge_challenge_details(
        hydrated.get("challenge") if isinstance(hydrated.get("challenge"), dict) else None,
        fallback,
        page_url=page_url,
    )
    if merged:
        hydrated["challenge"] = merged
        if hydrated.get("challenge_pending") is not True:
            phase = str(hydrated.get("phase") or "").strip().lower()
            if (
                phase not in {"submitted", "missing", "error", "failed", "destroyed", "load_error"}
                and str(merged.get("provider") or "").strip()
                and str(merged.get("site_key") or "").strip()
                and merged.get("token_injected") is not True
            ):
                hydrated["challenge_pending"] = True
    return hydrated


def _challenge_identity(challenge: Any) -> str:
    if not isinstance(challenge, dict):
        return ""
    provider = str(challenge.get("provider") or "").strip().lower()
    site_key = str(challenge.get("site_key") or "").strip()
    intent_id = str(challenge.get("intent_id") or "").strip()
    if intent_id:
        return f"{provider}|{site_key}|{intent_id}"
    return "|".join(
        [
            provider,
            site_key,
            str(challenge.get("widget_id") or "").strip(),
            str(challenge.get("action") or "").strip(),
            str(challenge.get("rqdata") or "").strip(),
        ]
    )


def _json_object(value: Any, *, error_code: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError) as error:
        raise PlusCheckoutPluginError(error_code) from error
    if not isinstance(parsed, dict):
        raise PlusCheckoutPluginError(error_code)
    return parsed


def _run_main_world_async(
    page: Any,
    *,
    start_script: str,
    payload: dict[str, Any],
    timeout_s: float = 10.0,
) -> dict[str, Any]:
    request_id = uuid.uuid4().hex
    initial_url = _page_url(page)
    deadline = time.monotonic() + max(0.5, float(timeout_s))
    try:
        start_raw = page.evaluate(start_script, {**payload, "request_id": request_id})
    except Exception as error:
        if _is_checkout_navigation_context_error(error):
            current_url = _page_url(page)
            return {
                "navigation_interrupted": True,
                "navigation_succeeded": _is_plus_checkout_success_url(current_url),
                "redirect_url": current_url,
                "initial_url": initial_url,
            }
        raise
    start_result = _json_object(
        start_raw,
        error_code="plus_checkout_main_world_async_start_invalid",
    )
    # Test doubles and non-Camoufox engines may still return the final value directly.
    if "started" not in start_result:
        if not start_result:
            return {
                "navigation_interrupted": True,
                "navigation_succeeded": _is_plus_checkout_success_url(_page_url(page)),
                "redirect_url": _page_url(page),
                "initial_url": initial_url,
                "async_result_missing": True,
            }
        return start_result
    if start_result.get("started") is not True:
        raise PlusCheckoutPluginError(
            "plus_checkout_main_world_async_not_started: " + _compact_json(start_result)
        )

    while time.monotonic() < deadline:
        try:
            task_raw = page.evaluate(READ_PLUS_CHECKOUT_ASYNC_RESULT_SCRIPT, request_id)
        except Exception as error:
            if not _is_checkout_navigation_context_error(error):
                raise
            current_url = _page_url(page)
            return {
                "navigation_interrupted": True,
                "navigation_succeeded": _is_plus_checkout_success_url(current_url),
                "redirect_url": current_url,
                "initial_url": initial_url,
            }
        if task_raw in (None, "", "null"):
            # A navigation can replace the document between the async start
            # and the result read. The old promise store is then gone; wait
            # for the new document instead of treating the empty read as a
            # malformed solver result.
            current_url = _page_url(page)
            return {
                "navigation_interrupted": True,
                "navigation_succeeded": _is_plus_checkout_success_url(current_url),
                "redirect_url": current_url,
                "initial_url": initial_url,
                "async_result_missing": True,
            }
        task = _json_object(
            task_raw,
            error_code="plus_checkout_main_world_async_result_invalid",
        )
        status = str(task.get("status") or "").strip().lower()
        if not status:
            return {
                "navigation_interrupted": True,
                "navigation_succeeded": _is_plus_checkout_success_url(_page_url(page)),
                "redirect_url": _page_url(page),
                "initial_url": initial_url,
                "async_result_missing": True,
            }
        if status == "fulfilled":
            return _json_object(
                task.get("value"),
                error_code="plus_checkout_main_world_async_value_invalid",
            )
        if status == "rejected":
            raise PlusCheckoutPluginError(
                "plus_checkout_main_world_async_rejected: "
                + str(task.get("error") or "unknown")[:500]
            )
        time.sleep(0.05)
    raise PlusCheckoutPluginError("plus_checkout_main_world_async_timeout")


def _stripe_verify_challenge_url(challenge: dict[str, Any]) -> tuple[str, str, str]:
    intent_id = str(challenge.get("intent_id") or "").strip()
    client_secret = str(challenge.get("client_secret") or "").strip()
    if intent_id.startswith("seti_"):
        intent_type = "setup_intent"
        expected_path = f"/v1/setup_intents/{intent_id}/verify_challenge"
    elif intent_id.startswith("pi_"):
        intent_type = "payment_intent"
        expected_path = f"/v1/payment_intents/{intent_id}/verify_challenge"
    else:
        raise PlusCheckoutPluginError("plus_checkout_stripe_challenge_intent_missing")
    if not client_secret or not client_secret.startswith(f"{intent_id}_secret_"):
        raise PlusCheckoutPluginError("plus_checkout_stripe_challenge_secret_invalid")

    raw_verify_url = unquote(str(challenge.get("verify_url") or "").strip())
    parsed = urlsplit(raw_verify_url)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme != "https" or parsed.netloc.lower() != "api.stripe.com":
            raise PlusCheckoutPluginError("plus_checkout_stripe_verify_url_invalid")
        verify_path = parsed.path
    else:
        verify_path = raw_verify_url or expected_path
    if verify_path != expected_path:
        raise PlusCheckoutPluginError("plus_checkout_stripe_verify_path_mismatch")
    return f"https://api.stripe.com{expected_path}", intent_type, client_secret


def _stripe_intent_error(payload: dict[str, Any]) -> dict[str, str] | None:
    raw = payload.get("last_payment_error") or payload.get("last_setup_error")
    if not isinstance(raw, dict):
        return None
    return {
        "type": str(raw.get("type") or ""),
        "code": str(raw.get("code") or ""),
        "decline_code": str(raw.get("decline_code") or ""),
        "message": str(raw.get("message") or "")[:500],
    }


def _verify_stripe_checkout_challenge(
    page: Any,
    *,
    challenge: dict[str, Any],
    token: str,
    resp_key: str = "",
) -> dict[str, Any]:
    verify_url, intent_type, client_secret = _stripe_verify_challenge_url(challenge)
    source = _json_object(
        page.evaluate(READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT),
        error_code="plus_checkout_stripe_source_invalid",
    )
    publishable_key = str(source.get("publishable_key") or "").strip()
    if not publishable_key.startswith(("pk_live_", "pk_test_")):
        raise PlusCheckoutPluginError("plus_checkout_stripe_publishable_key_missing")

    form = {
        "client_secret": client_secret,
        "captcha_vendor_name": "hcaptcha",
        "key": publishable_key,
        "_stripe_version": _STRIPE_VERSION_FULL,
        "challenge_response_token": token,
    }
    if resp_key:
        form["challenge_response_ekey"] = resp_key
    try:
        response = page.context.request.post(
            verify_url,
            form=form,
            headers={"accept": "application/json"},
            timeout=30_000,
        )
    except Exception as error:
        raise PlusCheckoutPluginError(
            f"plus_checkout_stripe_verify_request_failed:{type(error).__name__}:{error}"
        ) from error
    status_code = int(getattr(response, "status", 0) or 0)
    response_text = str(response.text() or "")
    try:
        response_payload = json.loads(response_text) if response_text else {}
    except (TypeError, ValueError) as error:
        raise PlusCheckoutPluginError("plus_checkout_stripe_verify_response_invalid") from error
    if not isinstance(response_payload, dict):
        raise PlusCheckoutPluginError("plus_checkout_stripe_verify_response_invalid")

    intent_status = str(response_payload.get("status") or "").strip().lower()
    intent_error = _stripe_intent_error(response_payload)
    verification = {
        "ok": status_code == 200,
        "status_code": status_code,
        "intent_type": intent_type,
        "intent_id": str(challenge.get("intent_id") or "").strip(),
        "intent_status": intent_status,
        "error": intent_error,
    }
    if status_code != 200:
        raise PlusCheckoutPluginError(
            "plus_checkout_stripe_verify_failed: " + _compact_json(verification)
        )
    if intent_status == "requires_action":
        continuation = _run_main_world_async(
            page,
            start_script=CONTINUE_PLUS_CHECKOUT_STRIPE_INTENT_SCRIPT,
            payload={"client_secret": client_secret},
            timeout_s=90.0,
        )
        if continuation.get("navigation_succeeded") is True:
            verification["intent_status"] = "succeeded"
            verification["continuation_status"] = "succeeded"
            verification["redirect_url"] = str(
                continuation.get("redirect_url") or _page_url(page)
            )
            return verification
        if continuation.get("navigation_interrupted") is True:
            verification["continuation_status"] = "navigation_interrupted"
            verification["navigation_interrupted"] = True
            verification["redirect_url"] = str(
                continuation.get("redirect_url") or _page_url(page)
            )
            return verification
        continuation_error = continuation.get("error")
        continuation_intent = continuation.get(
            "setupIntent" if intent_type == "setup_intent" else "paymentIntent"
        )
        if continuation_error:
            verification["error"] = {
                "type": str(continuation_error.get("type") or "")
                if isinstance(continuation_error, dict)
                else "",
                "code": str(continuation_error.get("code") or "")
                if isinstance(continuation_error, dict)
                else "",
                "decline_code": str(continuation_error.get("decline_code") or "")
                if isinstance(continuation_error, dict)
                else "",
                "message": str(
                    continuation_error.get("message")
                    if isinstance(continuation_error, dict)
                    else continuation_error
                )[:500],
            }
            raise PlusCheckoutPluginError(
                "plus_checkout_stripe_verify_continuation_failed: "
                + _compact_json(verification)
            )
        if not isinstance(continuation_intent, dict):
            raise PlusCheckoutPluginError(
                "plus_checkout_stripe_verify_continuation_invalid"
            )
        intent_status = str(continuation_intent.get("status") or "").strip().lower()
        verification["intent_status"] = intent_status
        verification["continuation_status"] = intent_status
    if intent_error or intent_status in _STRIPE_INTENT_FAILURE_STATES:
        raise PlusCheckoutPluginError(
            "plus_checkout_stripe_verify_intent_failed: " + _compact_json(verification)
        )
    if intent_status not in {"succeeded", "processing", "requires_capture"}:
        raise PlusCheckoutPluginError(
            "plus_checkout_stripe_verify_incomplete: " + _compact_json(verification)
        )
    try:
        marked_raw = page.evaluate(
            MARK_PLUS_CHECKOUT_STRIPE_CHALLENGE_VERIFIED_SCRIPT,
            verification,
        )
    except Exception as error:
        if _is_checkout_navigation_context_error(error):
            current_url = _page_url(page)
            verification["navigation_interrupted"] = True
            verification["navigation_succeeded"] = _is_plus_checkout_success_url(
                current_url
            )
            verification["redirect_url"] = current_url
            return verification
        raise
    marked = _json_object(
        marked_raw,
        error_code="plus_checkout_stripe_verify_mark_invalid",
    )
    if marked.get("ok") is not True:
        raise PlusCheckoutPluginError(
            "plus_checkout_stripe_verify_mark_failed: " + _compact_json(marked)
        )
    return verification


def _remote_captcha_task(challenge: dict[str, Any]) -> dict[str, Any]:
    provider = str(challenge.get("provider") or "").strip().lower()
    site_key = str(challenge.get("site_key") or "").strip()
    page_url = str(
        challenge.get("solver_page_url")
        or challenge.get("page_url")
        or ""
    ).strip()
    if not provider or not site_key or not page_url:
        raise PlusCheckoutPluginError("plus_checkout_captcha_context_missing")
    if provider == "hcaptcha":
        task = {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "isInvisible": challenge.get("invisible") is True,
        }
        wrapper = _stripe_hcaptcha_wrapper(
            challenge.get("stripe_hcaptcha_wrapper_url")
            or challenge.get("solver_page_url")
        )
        if wrapper is not None:
            # The captured wrapper is Stripe's enterprise hCaptcha surface.
            # Without this flag the provider opens the
            # generic checkbox flow and reports "checkbox frame not found".
            task["isEnterprise"] = True
        user_agent = str(challenge.get("user_agent") or "").strip()
        if user_agent:
            task["userAgent"] = user_agent
        rqdata = str(challenge.get("rqdata") or "").strip()
        if rqdata:
            task["rqdata"] = rqdata
        return task
    if provider == "recaptcha":
        enterprise = bool(challenge.get("enterprise"))
        action = str(challenge.get("action") or "").strip()
        task = {
            "type": (
                "RecaptchaV3EnterpriseTaskProxyless"
                if enterprise and action
                else "RecaptchaV3TaskProxyless"
                if action
                else "RecaptchaV2EnterpriseTaskProxyless"
                if enterprise
                else "RecaptchaV2TaskProxyless"
            ),
            "websiteURL": page_url,
            "websiteKey": site_key,
        }
        if action:
            task["pageAction"] = action
            task["minScore"] = 0.3
        return task
    raise PlusCheckoutPluginError(f"plus_checkout_captcha_provider_unsupported:{provider}")


def _remote_captcha_task_variants(challenge: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a bounded fallback set for provider compatibility.

    Stripe's wrapper is enterprise hCaptcha in the captured browser flow. A
    regular hCaptcha task remains a compatibility fallback for providers that
    reject the enterprise field, but it is attempted only after the captured
    Stripe task has failed.
    """
    primary = _remote_captcha_task(challenge)
    variants = [primary]
    if str(challenge.get("provider") or "").strip().lower() == "hcaptcha":
        if primary.get("isEnterprise") is True:
            regular = dict(primary)
            regular.pop("isEnterprise", None)
            variants.append(regular)
    return variants


def _solve_remote_captcha_task(
    client: Any,
    *,
    base_url: str,
    client_key: str,
    task: dict[str, Any],
    deadline: float,
    poll_interval_s: float,
) -> dict[str, Any]:
    create_response = client.post(
        f"{base_url}/createTask",
        json={"clientKey": client_key, "task": task},
        timeout=30,
    )
    create_status = int(getattr(create_response, "status_code", 200) or 200)
    create_text = str(getattr(create_response, "text", "") or "")
    try:
        create_payload = create_response.json() if create_text else {}
    except Exception as error:
        raise PlusCheckoutPluginError("plus_checkout_captcha_create_invalid") from error
    if create_status < 200 or create_status >= 300:
        raise PlusCheckoutPluginError(
            f"plus_checkout_captcha_create_http_failed:{create_status}:"
            + _compact_json(create_payload)
        )
    if int(create_payload.get("errorId", 1) or 0) != 0:
        error_description = str(create_payload.get("errorDescription") or create_payload)
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_create_failed: " + error_description
        )
    task_id = create_payload.get("taskId")
    if not task_id:
        raise PlusCheckoutPluginError("plus_checkout_captcha_task_missing")

    while True:
        if time.monotonic() >= deadline:
            raise PlusCheckoutPluginError(
                f"plus_checkout_captcha_timeout: task_id={task_id}"
            )
        time.sleep(max(0.2, float(poll_interval_s)))
        poll_response = client.post(
            f"{base_url}/getTaskResult",
            json={"clientKey": client_key, "taskId": task_id},
            timeout=30,
        )
        poll_status = int(getattr(poll_response, "status_code", 200) or 200)
        poll_text = str(getattr(poll_response, "text", "") or "")
        try:
            poll_payload = poll_response.json() if poll_text else {}
        except Exception as error:
            raise PlusCheckoutPluginError("plus_checkout_captcha_poll_invalid") from error
        if poll_status < 200 or poll_status >= 300:
            raise PlusCheckoutPluginError(
                f"plus_checkout_captcha_poll_http_failed:{poll_status}:"
                + _compact_json(poll_payload)
            )
        if int(poll_payload.get("errorId", 0) or 0) != 0:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_poll_failed: "
                + str(poll_payload.get("errorDescription") or poll_payload)
            )
        status = str(poll_payload.get("status") or "").strip().lower()
        if status in {"failed", "error", "expired"}:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_poll_failed: "
                + str(
                    poll_payload.get("errorDescription")
                    or poll_payload.get("errorCode")
                    or status
                )
            )
        if status != "ready":
            continue
        solution = poll_payload.get("solution") or {}
        solved = (
            solution.get("gRecaptchaResponse")
            or solution.get("token")
            or solution.get("hcaptchaToken")
            or solution.get("response")
            or ""
        )
        solved_token = str(solved or "").strip()
        if not solved_token:
            raise PlusCheckoutPluginError("plus_checkout_captcha_solution_missing")
        return {
            "provider": str(task.get("provider") or "").strip().lower(),
            "token": solved_token,
            "task_id": task_id,
            "task_type": str(task.get("type") or ""),
            "user_agent": str(
                solution.get("userAgent")
                or solution.get("user_agent")
                or task.get("userAgent")
                or ""
            ).strip(),
            "resp_key": str(
                solution.get("respKey")
                or solution.get("resp_key")
                or ""
            ).strip(),
            "solution": solution,
        }


def solve_plus_checkout_challenge(
    challenge: dict[str, Any],
    *,
    api_url: str,
    client_key: str,
    timeout_s: float = 180.0,
    poll_interval_s: float = 3.0,
) -> dict[str, Any]:
    base_url = str(api_url or "").rstrip("/")
    token = str(client_key or "").strip()
    if not base_url or not token:
        raise PlusCheckoutPluginError("plus_checkout_captcha_provider_missing")
    tasks = _remote_captcha_task_variants(challenge)
    deadline = time.monotonic() + max(1.0, float(timeout_s))
    failures: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        if time.monotonic() >= deadline:
            break
        client = requests.Session() if base_url.startswith("http://") else create_http_session()
        try:
            client.trust_env = False
            solved = _solve_remote_captcha_task(
                client,
                base_url=base_url,
                client_key=token,
                task=task,
                deadline=deadline,
                poll_interval_s=poll_interval_s,
            )
            solved.update(
                {
                    "provider": str(challenge.get("provider") or "").strip().lower(),
                    "solver_strategy": index,
                    "solver_strategy_count": len(tasks),
                    "task_website_url": task.get("websiteURL", ""),
                    "task_is_enterprise": task.get("isEnterprise") is True,
                }
            )
            return solved
        except PlusCheckoutPluginError as error:
            failures.append(
                {
                    "strategy": index,
                    "task_type": task.get("type", ""),
                    "website_url": task.get("websiteURL", ""),
                    "error": str(error),
                }
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
    raise PlusCheckoutPluginError(
        "plus_checkout_captcha_poll_failed: all task strategies failed: "
        + _compact_json(failures)
    )


def _maybe_solve_checkout_challenge(
    *,
    page: Any,
    state: dict[str, Any],
    challenge_capture: _CheckoutChallengeCapture,
    captcha_solver: Callable[[dict[str, Any]], dict[str, Any]] | None,
    solved_challenges: set[str],
) -> dict[str, Any] | None:
    if not callable(captcha_solver):
        return None
    challenge = state.get("challenge")
    if not isinstance(challenge, dict) or state.get("challenge_pending") is not True:
        return None
    identity = _challenge_identity(challenge)
    if not identity or identity in solved_challenges:
        return None
    payload = {
        **challenge,
        "challenge_requests": challenge_capture.snapshot()["challenge_requests"],
    }
    frame_url = str(payload.get("page_url") or "").strip()
    top_page_url = str(getattr(page, "url", "") or "").strip()
    if top_page_url:
        # The solver needs the page where Checkout loaded the challenge. The
        # hCaptcha iframe URL is only useful for extracting site_key/rqdata.
        payload["challenge_frame_url"] = frame_url
        payload["checkout_page_url"] = top_page_url
        payload["page_url"] = str(
            payload.get("solver_page_url") or top_page_url
        ).strip()
    try:
        user_agent = str(page.evaluate(READ_BROWSER_USER_AGENT_SCRIPT) or "").strip()
    except Exception:
        user_agent = ""
    if user_agent:
        payload["user_agent"] = user_agent
    solved = captcha_solver(payload)
    if not isinstance(solved, dict):
        raise PlusCheckoutPluginError("plus_checkout_captcha_solver_result_invalid")
    injection_payload = {
        "provider": str(solved.get("provider") or challenge.get("provider") or "").strip().lower(),
        "token": str(
            solved.get("token")
            or solved.get("gRecaptchaResponse")
            or solved.get("hcaptchaToken")
            or ""
        ).strip(),
        "site_key": str(challenge.get("site_key") or "").strip(),
        "widget_id": str(challenge.get("widget_id") or "").strip(),
        "resp_key": str(
            solved.get("resp_key")
            or solved.get("respKey")
            or ""
        ).strip(),
    }
    if not injection_payload["provider"] or not injection_payload["token"]:
        raise PlusCheckoutPluginError("plus_checkout_captcha_solver_result_missing")
    is_stripe_cross_origin = (
        injection_payload["provider"] == "hcaptcha"
        and str(challenge.get("intent_id") or "").strip()
        and str(challenge.get("client_secret") or "").strip()
    )
    if is_stripe_cross_origin:
        verification = _verify_stripe_checkout_challenge(
            page,
            challenge=challenge,
            token=injection_payload["token"],
            resp_key=injection_payload["resp_key"],
        )
        solved_challenges.add(identity)
        return {
            "identity": identity,
            "verification": verification,
            "injection": None,
            "solver_task_id": str(solved.get("task_id") or ""),
        }
    injection_result = _run_main_world_async(
        page,
        start_script=INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT,
        payload=injection_payload,
    )
    if not isinstance(injection_result, dict):
        raise PlusCheckoutPluginError("plus_checkout_captcha_injection_result_invalid")
    if injection_result.get("navigation_interrupted") is True:
        solved_challenges.add(identity)
        return {
            "identity": identity,
            "verification": None,
            "injection": injection_result,
            "solver_task_id": str(solved.get("task_id") or ""),
        }
    if (
        injection_result.get("ok") is not True
        or injection_result.get("token_applied") is not True
        or injection_result.get("callback_invoked") is not True
    ):
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_token_not_applied: "
            + _compact_json(injection_result)
        )
    solved_challenges.add(identity)
    return {
        "identity": identity,
        "verification": None,
        "injection": injection_result,
        "solver_task_id": str(solved.get("task_id") or ""),
    }


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

    current_url = str(getattr(page, "url", "") or "")
    if _is_plus_checkout_success_url(current_url):
        return {
            "provider": "stripe",
            "attempts": 0,
            "elapsed_ms": 0,
            "state": "succeeded",
            "payment_object_status": "succeeded",
            "response": {
                "state": "succeeded",
                "payment_object_status": "succeeded",
                "redirect_url": current_url,
                "source": "success_redirect",
            },
        }

    source: dict[str, Any]
    while True:
        current_url = str(getattr(page, "url", "") or "")
        if _is_plus_checkout_success_url(current_url):
            return {
                "provider": "stripe",
                "attempts": 0,
                "elapsed_ms": 0,
                "state": "succeeded",
                "payment_object_status": "succeeded",
                "response": {
                    "state": "succeeded",
                    "payment_object_status": "succeeded",
                    "redirect_url": current_url,
                    "source": "success_redirect",
                },
            }
        try:
            raw_source = page.evaluate(READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT)
            source = raw_source if isinstance(raw_source, dict) else {}
            break
        except Exception as error:
            current_url = str(getattr(page, "url", "") or "")
            if _is_plus_checkout_success_url(current_url):
                return {
                    "provider": "stripe",
                    "attempts": 0,
                    "elapsed_ms": 0,
                    "state": "succeeded",
                    "payment_object_status": "succeeded",
                    "response": {
                        "state": "succeeded",
                        "payment_object_status": "succeeded",
                        "redirect_url": current_url,
                        "source": "success_redirect",
                    },
                }
            if not _is_checkout_navigation_context_error(error):
                raise
            # The Checkout page can lose its JS world while Stripe replaces an
            # iframe/document. A live cs_* poll does not need that world: use
            # the captured live publishable key and continue the terminal poll.
            source = {"publishable_key": HAR_CONFIRMED_PUBLISHABLE_KEY}
            break
    if not isinstance(source, dict):
        raise PlusCheckoutPluginError("plus_checkout_stripe_poll_source_invalid")
    publishable_key = str(source.get("publishable_key") or "").strip()
    if not publishable_key.startswith(("pk_live_", "pk_test_")):
        if checkout_session_id.startswith("cs_live_"):
            publishable_key = HAR_CONFIRMED_PUBLISHABLE_KEY
        else:
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
    challenge_callback: Callable[[dict[str, Any]], None] | None = None,
    captcha_solver: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the single-flight Checkout submitter."""
    from refactor_app.plugins.openai_auth_browser.personal_plus_checkout_submit import (
        submit_plus_checkout_stably,
    )

    return submit_plus_checkout_stably(
        page,
        timeout_s=timeout_s,
        result_poll_attempts=result_poll_attempts,
        result_poll_interval_s=result_poll_interval_s,
        challenge_callback=challenge_callback,
        captcha_solver=captcha_solver,
        runtime=sys.modules[__name__],
    )


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
    retry_attempts: int = 3,
    retry_delay_s: float = 1.0,
) -> Any:
    """Send only the promotion update request through the promotion proxy.

    A failed transport can leave the proxy connection unusable, so each retry
    gets a fresh HTTP session. ``retry_attempts`` counts retries after the
    initial request.
    """
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

    payload = {
        "checkout_session_id": checkout_session_id,
        "processor_entity": processor_entity,
        "plan_name": "chatgptplusplan",
        "price_interval": "month",
        "seat_quantity": 1,
        "promo_campaign": {
            "promo_campaign_id": campaign_id,
            "is_coupon_from_query_param": False,
        },
    }
    retries = max(0, int(retry_attempts))
    delay_s = max(0.0, float(retry_delay_s))
    total_attempts = retries + 1
    last_retryable_error: Exception | None = None

    for attempt in range(1, total_attempts + 1):
        client = create_http_session(proxy=str(proxy_url or "").strip())
        try:
            try:
                response = client.post(
                    "https://chatgpt.com/backend-api/payments/checkout/update",
                    headers=headers,
                    json=payload,
                    timeout=float(timeout_s),
                )
            except Exception as error:
                if attempt >= total_attempts:
                    raise
                last_retryable_error = error
                if delay_s:
                    time.sleep(delay_s)
                continue

            text = str(getattr(response, "text", "") or "")
            try:
                body = response.json() if text else None
            except Exception:
                body = text
            status_code = int(getattr(response, "status_code", 0) or 0)
            if 200 <= status_code < 300:
                return body

            error = PlusCheckoutPromotionUpdateError(
                f"POST /backend-api/payments/checkout/update -> {status_code}: {text[:500]}"
            )
            if status_code not in _PROMOTION_UPDATE_RETRYABLE_STATUS_CODES:
                raise error
            if attempt >= total_attempts:
                raise error
            last_retryable_error = error
            if delay_s:
                time.sleep(delay_s)
        finally:
            client.close()

    if last_retryable_error is not None:
        raise last_retryable_error
    raise PlusCheckoutPromotionUpdateError("plus_checkout_promotion_update_failed")


__all__ = [
    "CREATE_PLUS_CHECKOUT_SCRIPT",
    "INVOKE_OAICS_PLUS_CHECKOUT_PLUGIN_SUBMIT_SCRIPT",
    "INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT",
    "INSTALL_PLUS_CHECKOUT_CAPTCHA_BRIDGE_SCRIPT",
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
    "solve_plus_checkout_challenge",
    "submit_plus_checkout_with_plugin",
    "update_plus_checkout_promotion",
]
