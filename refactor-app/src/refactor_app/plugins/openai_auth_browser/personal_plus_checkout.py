from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import sys
import time
import uuid
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlsplit

import requests

from refactor_app.plugins.openai_auth_protocol.http_client import create_http_session

logger = logging.getLogger(__name__)

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
    plan_type: String(session?.account?.planType || session?.account?.plan_type || ''),
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
    def __init__(self, message: str, *, result: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.result = dict(result) if isinstance(result, dict) else {}
        self.http_status = int(self.result.get("http_status") or 0)


class PlusCheckoutAlreadyPaidError(PlusCheckoutCreateError):
    """Checkout creation was rejected because the account is already paid."""


def _checkout_create_result_is_already_paid(result: dict[str, Any]) -> bool:
    """Recognize the documented/observed already-paid response without guessing from 400 alone."""
    try:
        text = json.dumps(result, ensure_ascii=True, separators=(",", ":")).casefold()
    except (TypeError, ValueError):
        text = str(result).casefold()
    return bool(
        re.search(r"\buser\s+is\s+already\s+paid\b", text)
        or re.search(r"\balready[ _-]paid\b", text)
    )


class PlusCheckoutPluginError(RuntimeError):
    pass


class _HcaptchaVisualSurfaceNotReady(PlusCheckoutPluginError):
    """The challenge shell is visible, but its rendered image is still empty."""

    def __init__(self, message: str, *, probe: dict[str, Any]) -> None:
        super().__init__(message)
        self.probe = probe


CheckoutChallengeTraceEmitter = Callable[[str, dict[str, Any], str], None]


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
_STRIPE_CONFIRM_PATH_RE = re.compile(
    r"^/v1/(?:setup_intents|payment_intents)/[^/]+/confirm$",
    re.IGNORECASE,
)
_STRIPE_PAYMENT_PAGE_PATH_RE = re.compile(
    r"^/v1/payment_pages/[^/]+$",
    re.IGNORECASE,
)
_STRIPE_PAYMENT_PAGE_CONFIRM_PATH_RE = re.compile(
    r"^/v1/payment_pages/[^/]+/confirm$",
    re.IGNORECASE,
)
_STRIPE_CLIENT_SECRET_RE = re.compile(
    r"^(?P<intent_id>(?P<prefix>seti|pi)_[A-Za-z0-9_-]+)_secret_[A-Za-z0-9_-]+$"
)
_HCAPTCHA_CHECKBOX_SELECTORS = (
    "#checkbox",
    "[role='checkbox']",
    "div[aria-checked]",
    "[aria-checked]",
    ".checkbox",
)
_HCAPTCHA_VISUAL_SELECTORS = (
    ".challenge-container",
    ".task-grid",
    ".task-image",
    ".task",
    "[class*='challenge']",
    "canvas",
)
_HCAPTCHA_GRID_IMAGE_SELECTORS = (
    ".task-image",
    "[class*='task-image']",
)
_HCAPTCHA_GRID_CLICK_SELECTORS = (
    ".task",
    "[class*='task']:not([class*='task-image'])",
)
_HCAPTCHA_ANCHOR_SELECTORS = (
    ".challenge-example .image",
    ".challenge-example img",
    ".challenge-example",
)
_HCAPTCHA_PROMPT_SELECTORS = (
    "#prompt-question",
    ".prompt-text",
    "[data-theme='challenge-container'] h2",
    "[class*='prompt']",
    ".challenge-header",
)
_HCAPTCHA_VERIFY_SELECTORS = (
    "button.verify-button",
    "button:has-text('Verify')",
    "button:has-text('Submit')",
    "button:has-text('Next')",
    "[aria-label*='Verify']",
    "[aria-label*='Submit']",
    "[aria-label*='Next']",
    "button.button-submit",
    "div.button-submit",
    ".button-submit",
    "[class*='submit']",
)
_HCAPTCHA_SKIP_SELECTORS = (
    "button:has-text('Skip')",
    "[aria-label*='Skip']",
    "button[data-action='skip']",
    "[data-action='skip']",
)
_HCAPTCHA_VISUAL_WAIT_S = 8.0
_HCAPTCHA_VISUAL_READY_WAIT_S = 20.0
_HCAPTCHA_VISUAL_READY_POLL_S = 0.25
_HCAPTCHA_VISUAL_STABLE_SAMPLES = 3
_HCAPTCHA_VISUAL_MIN_SETTLE_S = 1.5
_HCAPTCHA_VISUAL_ADVANCE_WAIT_S = 12.0
_HCAPTCHA_CHECKBOX_WAIT_S = 15.0
_HCAPTCHA_CHECKBOX_POLL_S = 0.25
# The vision service normalizes its input; browser coordinates remain dynamic.
_IMAGE_TO_TEXT_COORDINATE_SPACE = {"width": 1440.0, "height": 900.0}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_VISUAL_PIXEL_FOCUS = (0.15, 0.32, 0.85, 0.80)
_VISUAL_PIXEL_READY_RATIO = 0.02

_HCAPTCHA_VISUAL_RESOURCE_STATE_SCRIPT = r"""() => {
  const visible = (element) => {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none'
      && style.visibility !== 'hidden'
      && style.opacity !== '0';
  };
  const visibleImages = Array.from(document.images).filter(visible);
  const pendingImages = visibleImages.filter((image) => {
    const source = String(image.currentSrc || image.src || '');
    return source && (!image.complete || Number(image.naturalWidth || 0) <= 0);
  });
  const tileNodes = Array.from(
    document.querySelectorAll('.task-image,[class*="task-image"]'),
  ).filter(visible);
  const visibleCanvases = Array.from(document.querySelectorAll('canvas')).filter(visible);
  const canvasStates = visibleCanvases.map((canvas) => {
    const width = Number(canvas.width || 0);
    const height = Number(canvas.height || 0);
    let bitmapProbe = 'unavailable';
    let bitmapReady = null;
    let sampledPixels = 0;
    let nonBlankPixels = 0;
    let colorRange = 0;
    let dataUrlLength = 0;
    try {
      if (width > 0 && height > 0) {
        const context = canvas.getContext('2d', { willReadFrequently: true });
        if (context) {
          const data = context.getImageData(0, 0, width, height).data;
          const step = Math.max(1, Math.floor(Math.max(width, height) / 32));
          let minChannel = 255;
          let maxChannel = 0;
          for (let y = 0; y < height; y += step) {
            for (let x = 0; x < width; x += step) {
              const offset = (y * width + x) * 4;
              const red = Number(data[offset] || 0);
              const green = Number(data[offset + 1] || 0);
              const blue = Number(data[offset + 2] || 0);
              const alpha = Number(data[offset + 3] || 0);
              sampledPixels += 1;
              minChannel = Math.min(minChannel, red, green, blue);
              maxChannel = Math.max(maxChannel, red, green, blue);
              if (
                alpha > 10
                && (
                  red < 245
                  || green < 245
                  || blue < 245
                  || Math.max(red, green, blue) - Math.min(red, green, blue) > 10
                )
              ) {
                nonBlankPixels += 1;
              }
            }
          }
          colorRange = maxChannel - minChannel;
          bitmapProbe = 'readable';
          bitmapReady = Boolean(
            sampledPixels >= 3
            && nonBlankPixels >= Math.max(3, Math.ceil(sampledPixels * 0.01))
            && colorRange >= 8,
          );
        }
      }
    } catch (_error) {
      // Cross-origin canvas content can be readable by a browser screenshot
      // while getImageData/toDataURL is blocked. Keep this as an advisory
      // probe and let stable screenshot checks handle that compatibility path.
      bitmapProbe = 'tainted';
      bitmapReady = null;
    }
    try {
      dataUrlLength = String(canvas.toDataURL('image/png') || '').length;
    } catch (_error) {
      dataUrlLength = 0;
    }
    if (bitmapProbe === 'unavailable' && dataUrlLength > 0) {
      bitmapProbe = 'data_url';
      bitmapReady = dataUrlLength >= 512;
    }
    const rect = canvas.getBoundingClientRect();
    return {
      width,
      height,
      css_width: Number(rect.width || 0),
      css_height: Number(rect.height || 0),
      bitmap_probe: bitmapProbe,
      bitmap_ready: bitmapReady,
      sampled_pixels: sampledPixels,
      non_blank_pixels: nonBlankPixels,
      color_range: colorRange,
      data_url_length: dataUrlLength,
    };
  });
  const primaryCanvasState = canvasStates.reduce(
    (largest, state) => (
      !largest
      || Number(state.css_width || 0) * Number(state.css_height || 0)
        > Number(largest.css_width || 0) * Number(largest.css_height || 0)
        ? state
        : largest
    ),
    null,
  );
  const canvasBitmapReady = primaryCanvasState
    ? primaryCanvasState.bitmap_ready
    : true;
  const canvasBlankCount = canvasStates.filter((state) => state.bitmap_ready === false).length;
  const canvasDataUrlLength = canvasStates.reduce(
    (maximum, state) => Math.max(maximum, Number(state.data_url_length || 0)),
    0,
  );
  const challengeImages = visibleImages.filter((image) => Boolean(
    image.closest('.challenge-container,.task-grid,.task,[class*="challenge"],[class*="task"]'),
  ));
  const tileVisualMissing = tileNodes.filter((node) => {
    const style = getComputedStyle(node);
    const background = String(style.backgroundImage || '');
    const hasBackground = background && background !== 'none';
    const hasImage = node.matches('img') || Boolean(node.querySelector('img'));
    const hasCanvas = node.matches('canvas') || Boolean(node.querySelector('canvas'));
    return !hasBackground && !hasImage && !hasCanvas;
  });
  const body = document.body;
  const bodyRect = body ? body.getBoundingClientRect() : null;
  const bodyReady = Boolean(
    bodyRect && bodyRect.width > 0 && bodyRect.height > 0 && visible(body),
  );
  const visualContentCount = tileNodes.length + challengeImages.length + visibleCanvases.length;
  const visualContentPresent = visualContentCount > 0;
  return {
    probe_ok: true,
    body_ready: bodyReady,
    image_count: visibleImages.length,
    challenge_image_count: challengeImages.length,
    pending_image_count: pendingImages.length,
    tile_count: tileNodes.length,
    tile_visual_missing_count: tileVisualMissing.length,
    canvas_count: visibleCanvases.length,
    canvas_bitmap_ready: canvasBitmapReady,
    canvas_blank_count: canvasBlankCount,
    canvas_data_url_length: canvasDataUrlLength,
    visual_content_count: visualContentCount,
    visual_content_present: visualContentPresent,
    // hCaptcha can paint tile pixels through a pseudo-element or a wrapper
    // node. `tileVisualMissing` is therefore diagnostic only; the Python side
    // still requires a stable screenshot before it sends anything to the
    // classifier.
    ready: bodyReady
      && visualContentPresent
      && pendingImages.length === 0
      && canvasBitmapReady !== false,
  };
}"""


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
        self._checkout_confirms: list[dict[str, str]] = []
        self._active_stripe_challenges: list[dict[str, str]] = []
        self._active_stripe_challenge: dict[str, str] | None = None
        self._deferred_trace_keys: set[str] = set()
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
        if self._checkout_confirms:
            latest_confirm = self._checkout_confirms[-1]
            context = _stripe_challenge_context_from_checkout_confirm(latest_confirm)
            snapshot["stripe_confirm_capture_count"] = len(self._checkout_confirms)
            snapshot["stripe_confirm"] = {
                "type": latest_confirm["type"],
                "intent_id": str((context or {}).get("intent_id") or ""),
            }
        if self._active_stripe_challenge is not None:
            latest_active = self._active_stripe_challenge
            snapshot["stripe_active_challenge_capture_count"] = len(
                self._active_stripe_challenges
            )
            snapshot["stripe_active_challenge"] = {
                "type": str(latest_active.get("type") or ""),
                "status": str(latest_active.get("status") or ""),
                "intent_id": str(latest_active.get("intent_id") or ""),
                "site_key_present": bool(str(latest_active.get("site_key") or "")),
                "verify_path": urlsplit(
                    unquote(str(latest_active.get("verify_url") or ""))
                ).path,
            }
        return snapshot

    def latest_checkout_confirm(self) -> dict[str, str] | None:
        if not self._checkout_confirms:
            return None
        return dict(self._checkout_confirms[-1])

    def latest_active_stripe_challenge(self) -> dict[str, str] | None:
        if self._active_stripe_challenge is None:
            return None
        return dict(self._active_stripe_challenge)

    def mark_deferred_trace_once(
        self,
        *,
        reason: str,
        challenge: dict[str, Any],
    ) -> bool:
        identity = _challenge_identity(challenge) or str(
            challenge.get("page_url") or ""
        ).strip()
        key = f"{str(reason or '').strip()}|{identity}"
        if key in self._deferred_trace_keys:
            return False
        self._deferred_trace_keys.add(key)
        return True

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
        self._capture_stripe_payment_response(response)
        try:
            request = getattr(response, "request", None)
            status = getattr(response, "status", None)
        except BaseException:
            return
        self._record(request, event="response", status=status)

    def _capture_stripe_payment_response(self, response: Any) -> None:
        if self._closed:
            return
        try:
            request = getattr(response, "request", None)
            method = str(getattr(request, "method", "") or "").strip().upper()
            response_url = str(getattr(response, "url", "") or "").strip()
            request_url = str(getattr(request, "url", "") or "").strip()
            parsed = urlsplit(response_url or request_url)
            direct_intent_confirm = (
                method == "POST"
                and _STRIPE_CONFIRM_PATH_RE.fullmatch(parsed.path) is not None
            )
            payment_page_response = (
                method == "GET"
                and _STRIPE_PAYMENT_PAGE_PATH_RE.fullmatch(parsed.path) is not None
            ) or (
                method == "POST"
                and _STRIPE_PAYMENT_PAGE_CONFIRM_PATH_RE.fullmatch(parsed.path)
                is not None
            )
            if (
                parsed.netloc.lower() != "api.stripe.com"
                or not (direct_intent_confirm or payment_page_response)
            ):
                return

            payload: Any = None
            response_json = getattr(response, "json", None)
            if callable(response_json):
                try:
                    payload = response_json()
                except Exception:
                    payload = None
            if not isinstance(payload, (dict, list)):
                response_text = getattr(response, "text", None)
                if callable(response_text):
                    response_text = response_text()
                payload = json.loads(str(response_text or ""))

            checkout_confirm = _stripe_checkout_confirm_from_payload(payload)
            if checkout_confirm is not None and (
                not self._checkout_confirms
                or self._checkout_confirms[-1] != checkout_confirm
            ):
                self._checkout_confirms.append(checkout_confirm)
                if len(self._checkout_confirms) > 8:
                    self._checkout_confirms = self._checkout_confirms[-8:]
            active_challenge = _stripe_active_challenge_from_payload(payload)
            self._active_stripe_challenge = (
                dict(active_challenge) if active_challenge is not None else None
            )
            if active_challenge is not None and (
                not self._active_stripe_challenges
                or self._active_stripe_challenges[-1] != active_challenge
            ):
                self._active_stripe_challenges.append(active_challenge)
                if len(self._active_stripe_challenges) > 8:
                    self._active_stripe_challenges = self._active_stripe_challenges[-8:]
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException:
            # Network capture must not interfere with the Checkout page lifecycle.
            return

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


def _stripe_checkout_confirm_from_payload(payload: Any) -> dict[str, str] | None:
    if isinstance(payload, dict):
        client_secret = str(payload.get("client_secret") or "").strip()
        secret_match = _STRIPE_CLIENT_SECRET_RE.fullmatch(client_secret)
        if secret_match is not None:
            return {
                "type": (
                    "setup_intent"
                    if secret_match.group("prefix") == "seti"
                    else "payment_intent"
                ),
                "client_secret": client_secret,
            }
        for value in payload.values():
            checkout_confirm = _stripe_checkout_confirm_from_payload(value)
            if checkout_confirm is not None:
                return checkout_confirm
        return None
    if isinstance(payload, list):
        for value in payload:
            checkout_confirm = _stripe_checkout_confirm_from_payload(value)
            if checkout_confirm is not None:
                return checkout_confirm
    return None


def _stripe_active_challenge_from_payload(payload: Any) -> dict[str, str] | None:
    """Extract one currently actionable Stripe hCaptcha intent from a response."""
    if isinstance(payload, dict):
        status = str(payload.get("status") or "").strip().lower()
        client_secret = str(payload.get("client_secret") or "").strip()
        secret_match = _STRIPE_CLIENT_SECRET_RE.fullmatch(client_secret)
        next_action = payload.get("next_action")
        if (
            status == "requires_action"
            and secret_match is not None
            and isinstance(next_action, dict)
            and str(next_action.get("type") or "").strip().lower() == "use_stripe_sdk"
        ):
            use_stripe_sdk = next_action.get("use_stripe_sdk")
            stripe_js = (
                use_stripe_sdk.get("stripe_js")
                if isinstance(use_stripe_sdk, dict)
                else None
            )
            if isinstance(stripe_js, dict):
                intent_id = str(payload.get("id") or secret_match.group("intent_id")).strip()
                site_key = str(stripe_js.get("site_key") or "").strip()
                verify_url = str(stripe_js.get("verification_url") or "").strip()
                if (
                    intent_id == secret_match.group("intent_id")
                    and site_key
                    and verify_url
                ):
                    return {
                        "type": (
                            "setup_intent"
                            if secret_match.group("prefix") == "seti"
                            else "payment_intent"
                        ),
                        "status": "requires_action",
                        "provider": "hcaptcha",
                        "intent_id": intent_id,
                        "client_secret": client_secret,
                        "site_key": site_key,
                        "rqdata": str(stripe_js.get("rqdata") or "").strip(),
                        "verify_url": verify_url,
                    }
        for value in payload.values():
            challenge = _stripe_active_challenge_from_payload(value)
            if challenge is not None:
                return challenge
        return None
    if isinstance(payload, list):
        for value in payload:
            challenge = _stripe_active_challenge_from_payload(value)
            if challenge is not None:
                return challenge
    return None


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


def _emit_checkout_challenge_trace(
    emitter: CheckoutChallengeTraceEmitter | None,
    event_type: str,
    data: dict[str, Any],
    level: str = "INFO",
) -> None:
    log_level = (
        logging.ERROR
        if level == "ERROR"
        else logging.WARNING
        if level == "WARN"
        else logging.INFO
    )
    logger.log(log_level, "plus_checkout.%s %s", event_type, _compact_json(data))
    if emitter is None:
        return
    try:
        emitter(event_type, data, level)
    except Exception:
        logger.exception("plus_checkout.challenge.trace_emit_failed")


def _mark_deferred_challenge_trace_once(
    challenge_capture: Any,
    *,
    reason: str,
    challenge: dict[str, Any],
) -> bool:
    marker = getattr(challenge_capture, "mark_deferred_trace_once", None)
    if not callable(marker):
        return True
    try:
        return bool(marker(reason=reason, challenge=challenge))
    except Exception:
        logger.exception("plus_checkout.challenge.deferred_trace_failed")
        return True


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
    captured_active = challenge_capture.latest_active_stripe_challenge()
    if captured_active is not None:
        hydrated["checkout_confirm"] = captured_active
    elif _stripe_challenge_context_from_checkout_confirm(
        hydrated.get("checkout_confirm")
    ) is None:
        captured_confirm = challenge_capture.latest_checkout_confirm()
        if captured_confirm is not None:
            hydrated["checkout_confirm"] = captured_confirm
    fallback = challenge_capture.best_challenge(page_url=page_url)
    merged = _merge_challenge_details(
        hydrated.get("challenge") if isinstance(hydrated.get("challenge"), dict) else None,
        fallback,
        page_url=page_url,
    )
    if captured_active is not None:
        merged = _merge_challenge_details(
            captured_active,
            merged,
            page_url=page_url,
        )
    if merged:
        hydrated["challenge"] = merged
        active_stripe_context = _stripe_active_challenge_context(merged)
        if active_stripe_context is not None:
            hydrated["challenge_pending"] = merged.get("token_injected") is not True
        elif _is_stripe_hcaptcha_challenge(merged):
            # Stripe loads passive hCaptcha resources before some payment
            # attempts. Only a requires_action Intent proves that verify_challenge
            # is currently valid for this payment attempt.
            hydrated["challenge_pending"] = False
        elif hydrated.get("challenge_pending") is not True:
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


def _is_stripe_hcaptcha_frame(challenge: dict[str, Any]) -> bool:
    if str(challenge.get("provider") or "").strip().lower() != "hcaptcha":
        return False
    for key in (
        "page_url",
        "challenge_frame_url",
        "solver_page_url",
        "stripe_hcaptcha_wrapper_url",
    ):
        raw_url = str(challenge.get(key) or "").strip()
        if not raw_url:
            continue
        try:
            host = str(urlsplit(unquote(raw_url)).netloc or "").strip().lower()
        except (TypeError, ValueError):
            continue
        if host in {"js.stripe.com", "b.stripecdn.com"}:
            return True
    return False


def _is_stripe_hcaptcha_challenge(challenge: dict[str, Any]) -> bool:
    if str(challenge.get("provider") or "").strip().lower() != "hcaptcha":
        return False
    if _is_stripe_hcaptcha_frame(challenge):
        return True
    intent_id = str(challenge.get("intent_id") or "").strip()
    client_secret = str(challenge.get("client_secret") or "").strip()
    verify_url = unquote(str(challenge.get("verify_url") or "").strip())
    return (
        intent_id.startswith(("seti_", "pi_"))
        or client_secret.startswith(("seti_", "pi_"))
        or "/v1/setup_intents/" in verify_url
        or "/v1/payment_intents/" in verify_url
    )


def _stripe_challenge_context_from_checkout_confirm(
    checkout_confirm: Any,
) -> dict[str, str] | None:
    if not isinstance(checkout_confirm, dict):
        return None
    intent_type = str(checkout_confirm.get("type") or "").strip().lower()
    client_secret = str(checkout_confirm.get("client_secret") or "").strip()
    intent_id, separator, secret_suffix = client_secret.partition("_secret_")
    if not separator or not intent_id or not secret_suffix:
        return None

    if intent_id.startswith("seti_"):
        expected_type = "setup_intent"
        intent_collection = "setup_intents"
    elif intent_id.startswith("pi_"):
        expected_type = "payment_intent"
        intent_collection = "payment_intents"
    else:
        return None
    if intent_type != expected_type:
        return None
    return {
        "intent_id": intent_id,
        "client_secret": client_secret,
        "verify_url": f"/v1/{intent_collection}/{intent_id}/verify_challenge",
    }


def _stripe_active_challenge_context(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    if str(value.get("status") or "").strip().lower() != "requires_action":
        return None
    context = _stripe_challenge_context_from_checkout_confirm(value)
    if context is None:
        return None
    site_key = str(value.get("site_key") or "").strip()
    raw_verify_url = unquote(str(value.get("verify_url") or "").strip())
    if not site_key or not raw_verify_url:
        return None
    parsed_verify_url = urlsplit(raw_verify_url)
    verify_path = parsed_verify_url.path if parsed_verify_url.scheme else raw_verify_url
    if verify_path != context["verify_url"]:
        return None
    return {
        "type": str(value.get("type") or "").strip().lower(),
        "status": "requires_action",
        "provider": "hcaptcha",
        "intent_id": context["intent_id"],
        "client_secret": context["client_secret"],
        "site_key": site_key,
        "rqdata": str(value.get("rqdata") or "").strip(),
        "verify_url": raw_verify_url,
    }


def _page_frames(page: Any) -> list[Any]:
    raw_frames = getattr(page, "frames", None)
    if raw_frames is None:
        return []
    try:
        frames = raw_frames() if callable(raw_frames) else raw_frames
        return list(frames or [])
    except Exception:
        return []


def _frame_url(frame: Any) -> str:
    try:
        raw_url = getattr(frame, "url", "")
        return str(raw_url() if callable(raw_url) else raw_url or "").strip()
    except Exception:
        return ""


def _first_locator(locator: Any) -> Any:
    first = getattr(locator, "first", None)
    if first is None:
        return locator
    return first() if callable(first) else first


def _visible_frame_locator(frame: Any, selectors: tuple[str, ...]) -> tuple[Any, str] | None:
    locate = getattr(frame, "locator", None)
    if not callable(locate):
        return None
    for selector in selectors:
        try:
            locator = _first_locator(locate(selector))
            if bool(locator.is_visible(timeout=250)):
                return locator, selector
        except Exception:
            continue
    return None


def _visible_frame_locators(frame: Any, selectors: tuple[str, ...]) -> tuple[list[Any], str]:
    locate = getattr(frame, "locator", None)
    if not callable(locate):
        return [], ""
    for selector in selectors:
        try:
            collection = locate(selector)
            count = int(collection.count())
        except Exception:
            continue
        visible: list[Any] = []
        for index in range(count):
            try:
                locator = collection.nth(index)
                if bool(locator.is_visible(timeout=250)):
                    visible.append(locator)
            except Exception:
                continue
        if visible:
            return visible, selector
    return [], ""


def _hcaptcha_frames(page: Any) -> list[Any]:
    return [
        frame
        for frame in _page_frames(page)
        if "hcaptcha" in _frame_url(frame).lower()
    ]


def _find_hcaptcha_visual_frame(page: Any) -> Any | None:
    for frame in reversed(_hcaptcha_frames(page)):
        if "frame=checkbox" in _frame_url(frame).lower():
            continue
        if _visible_frame_locator(frame, _HCAPTCHA_VISUAL_SELECTORS) is not None:
            return frame
    return None


def _find_hcaptcha_checkbox_frame(page: Any) -> Any | None:
    for frame in reversed(_hcaptcha_frames(page)):
        frame_url = _frame_url(frame).lower()
        if "frame=challenge" in frame_url:
            continue
        if "frame=checkbox" in frame_url:
            return frame
        if _visible_frame_locator(frame, _HCAPTCHA_CHECKBOX_SELECTORS) is not None:
            return frame
    return None


def _hcaptcha_checkbox_locator(frame: Any) -> tuple[Any, str] | None:
    locate = getattr(frame, "locator", None)
    if not callable(locate):
        return None
    for selector in _HCAPTCHA_CHECKBOX_SELECTORS:
        try:
            raw_locator = locate(selector)
            locator = _first_locator(raw_locator)
            count = int(raw_locator.count())
            if count > 0:
                return locator, selector
        except Exception:
            try:
                if bool(locator.is_visible(timeout=250)):
                    return locator, selector
            except Exception:
                continue
    return None


def _wait_for_hcaptcha_checkbox(page: Any, *, timeout_s: float) -> dict[str, Any]:
    started_at = time.monotonic()
    deadline = started_at + max(0.0, float(timeout_s))
    probes = 0

    if getattr(page, "frames", None) is None:
        return {
            "status": "unavailable",
            "reason": "page_frames_unavailable",
            "probe_count": probes,
            "waited_ms": 0,
            "frame_count": 0,
        }

    def elapsed_ms() -> int:
        return max(0, int((time.monotonic() - started_at) * 1000))

    while True:
        probes += 1
        frame = _find_hcaptcha_checkbox_frame(page)
        if frame is not None:
            located = _hcaptcha_checkbox_locator(frame)
            if located is not None:
                return {
                    "status": "ready",
                    "frame": frame,
                    "located": located,
                    "probe_count": probes,
                    "waited_ms": elapsed_ms(),
                }
        if _is_plus_checkout_success_url(_page_url(page)):
            return {
                "status": "passed",
                "probe_count": probes,
                "waited_ms": elapsed_ms(),
            }
        if time.monotonic() >= deadline:
            return {
                "status": "unavailable",
                "reason": "checkbox_not_ready",
                "probe_count": probes,
                "waited_ms": elapsed_ms(),
                "frame_count": len(_hcaptcha_frames(page)),
            }
        time.sleep(_HCAPTCHA_CHECKBOX_POLL_S)


def _click_hcaptcha_checkbox(page: Any) -> dict[str, Any]:
    readiness = _wait_for_hcaptcha_checkbox(
        page,
        timeout_s=_HCAPTCHA_CHECKBOX_WAIT_S,
    )
    if readiness.get("status") == "passed":
        return {
            "clicked": False,
            "passed": True,
            "reason": "checkout_already_advanced",
            "probe_count": readiness.get("probe_count", 0),
            "waited_ms": readiness.get("waited_ms", 0),
        }
    if readiness.get("status") != "ready":
        return {
            "clicked": False,
            "reason": str(readiness.get("reason") or "checkbox_frame_missing"),
            "probe_count": readiness.get("probe_count", 0),
            "waited_ms": readiness.get("waited_ms", 0),
            "frame_count": readiness.get("frame_count", 0),
        }
    frame = readiness["frame"]
    located = readiness["located"]
    locator, selector = located
    click_error: Exception | None = None
    for force in (False, True):
        try:
            locator.click(timeout=1_500, force=force)
            return {
                "clicked": True,
                "method": "locator" if not force else "locator_force",
                "selector": selector,
                "frame_url": _frame_url(frame),
                "probe_count": readiness.get("probe_count", 0),
                "waited_ms": readiness.get("waited_ms", 0),
            }
        except Exception as error:
            click_error = error
    try:
        box = locator.bounding_box(timeout=1_000)
    except Exception:
        box = None
    if isinstance(box, dict) and float(box.get("width") or 0) > 0:
        x = float(box["x"]) + float(box["width"]) / 2
        y = float(box["y"]) + float(box["height"]) / 2
        mouse = getattr(page, "mouse", None)
        if mouse is not None:
            mouse.move(x, y, steps=6)
            mouse.click(x, y)
            return {
                "clicked": True,
                "method": "mouse",
                "selector": selector,
                "frame_url": _frame_url(frame),
                "probe_count": readiness.get("probe_count", 0),
                "waited_ms": readiness.get("waited_ms", 0),
            }
    return {
        "clicked": False,
        "reason": "checkbox_click_failed",
        "error_type": type(click_error).__name__ if click_error else "UnknownError",
        "selector": selector,
        "frame_url": _frame_url(frame),
        "probe_count": readiness.get("probe_count", 0),
        "waited_ms": readiness.get("waited_ms", 0),
    }


def _hcaptcha_checkbox_checked(page: Any) -> bool:
    frame = _find_hcaptcha_checkbox_frame(page)
    if frame is None:
        return False
    located = _hcaptcha_checkbox_locator(frame)
    if located is None:
        return False
    locator, _selector = located
    try:
        aria_checked = str(locator.get_attribute("aria-checked") or "").strip().lower()
        if aria_checked == "true":
            return True
        classes = str(locator.get_attribute("class") or "").strip().lower().split()
        return "checked" in classes
    except Exception:
        return False


def _wait_for_hcaptcha_visual_frame(
    page: Any,
    *,
    challenge_capture: _CheckoutChallengeCapture,
    active_intent_id: str,
    timeout_s: float = _HCAPTCHA_VISUAL_WAIT_S,
) -> tuple[str, Any | None]:
    captured_before = challenge_capture.latest_active_stripe_challenge()
    captured_before_id = str((captured_before or {}).get("intent_id") or "")
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        visual_frame = _find_hcaptcha_visual_frame(page)
        if visual_frame is not None:
            return "visual", visual_frame
        if _hcaptcha_checkbox_checked(page):
            return "passed", None
        if _is_plus_checkout_success_url(_page_url(page)):
            return "passed", None
        captured_now = challenge_capture.latest_active_stripe_challenge()
        if (
            captured_before_id == active_intent_id
            and captured_now is None
        ):
            return "passed", None
        if time.monotonic() >= deadline:
            return "not_visible", None
        time.sleep(0.25)


def _read_hcaptcha_prompt(frame: Any, body: Any) -> str:
    located = _visible_frame_locator(frame, _HCAPTCHA_PROMPT_SELECTORS)
    candidates = [located[0]] if located is not None else []
    candidates.append(body)
    for locator in candidates:
        try:
            text = " ".join(str(locator.inner_text(timeout=1_000) or "").split())
        except Exception:
            continue
        if text:
            return text[:500]
    return ""


def _locator_jpeg(locator: Any) -> bytes:
    try:
        value = locator.screenshot(
            timeout=10_000,
            type="jpeg",
            quality=90,
            scale="css",
        )
    except Exception as error:
        raise PlusCheckoutPluginError(
            f"plus_checkout_captcha_visual_capture_failed:{type(error).__name__}:{error}"
        ) from error
    if not value:
        raise PlusCheckoutPluginError("plus_checkout_captcha_visual_capture_invalid")
    return bytes(value)


def _locator_png(locator: Any) -> bytes:
    """Capture a lossless probe image without changing the solver payload path."""
    try:
        value = locator.screenshot(
            timeout=10_000,
            type="png",
            scale="css",
        )
    except Exception:
        return b""
    return bytes(value or b"")


def _png_visual_stats(
    value: bytes,
    *,
    focus: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
) -> dict[str, Any] | None:
    """Read a small pixel sample from an 8-bit, non-interlaced PNG.

    Playwright can screenshot a cross-origin canvas even when the page cannot
    read it with ``getImageData``. This parser gives the Python side an
    independent rendered-pixel check without adding an image dependency.
    """
    data = bytes(value or b"")
    if not data.startswith(_PNG_SIGNATURE):
        return None
    width = height = bit_depth = color_type = interlace = 0
    idat = bytearray()
    offset = len(_PNG_SIGNATURE)
    while offset + 12 <= len(data):
        chunk_length = int.from_bytes(data[offset : offset + 4], "big")
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_length
        if chunk_end + 4 > len(data):
            return None
        chunk_type = data[offset + 4 : offset + 8]
        chunk = data[chunk_start:chunk_end]
        offset = chunk_end + 4
        if chunk_type == b"IHDR" and len(chunk) >= 13:
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            bit_depth = int(chunk[8])
            color_type = int(chunk[9])
            interlace = int(chunk[12])
        elif chunk_type == b"IDAT":
            idat.extend(chunk)
        elif chunk_type == b"IEND":
            break
    channels_by_type = {0: 1, 2: 3, 4: 2, 6: 4}
    channels = channels_by_type.get(color_type)
    if (
        width <= 0
        or height <= 0
        or bit_depth != 8
        or channels is None
        or interlace != 0
        or not idat
    ):
        return None
    try:
        decoded = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    row_bytes = width * channels
    expected_length = height * (row_bytes + 1)
    if len(decoded) < expected_length:
        return None

    try:
        focus_x0, focus_y0, focus_x1, focus_y1 = (float(item) for item in focus)
    except (TypeError, ValueError):
        return None
    x0 = max(0, min(width - 1, int(width * max(0.0, min(1.0, focus_x0)))))
    y0 = max(0, min(height - 1, int(height * max(0.0, min(1.0, focus_y0)))))
    x1 = max(x0 + 1, min(width, int(width * max(0.0, min(1.0, focus_x1)))))
    y1 = max(y0 + 1, min(height, int(height * max(0.0, min(1.0, focus_y1)))))
    step = max(1, int(max(x1 - x0, y1 - y0) / 64))
    sampled = 0
    non_blank = 0
    colorful = 0
    min_channel = 255
    max_channel = 0
    cursor = 0
    previous: bytearray | None = None
    for y in range(height):
        filter_type = decoded[cursor]
        cursor += 1
        row = bytearray(decoded[cursor : cursor + row_bytes])
        cursor += row_bytes
        if filter_type not in {0, 1, 2, 3, 4}:
            return None
        for index in range(row_bytes):
            left = row[index - channels] if index >= channels else 0
            up = previous[index] if previous is not None else 0
            upper_left = (
                previous[index - channels]
                if previous is not None and index >= channels
                else 0
            )
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                estimate = left + up - upper_left
                distance_left = abs(estimate - left)
                distance_up = abs(estimate - up)
                distance_upper_left = abs(estimate - upper_left)
                predictor = (
                    left
                    if distance_left <= distance_up and distance_left <= distance_upper_left
                    else up
                    if distance_up <= distance_upper_left
                    else upper_left
                )
                row[index] = (row[index] + predictor) & 0xFF

        if y0 <= y < y1 and (y - y0) % step == 0:
            for x in range(x0, x1, step):
                offset = x * channels
                if color_type == 0:
                    red = green = blue = row[offset]
                    alpha = 255
                elif color_type == 2:
                    red, green, blue = row[offset : offset + 3]
                    alpha = 255
                elif color_type == 4:
                    red = green = blue = row[offset]
                    alpha = row[offset + 1]
                else:
                    red, green, blue, alpha = row[offset : offset + 4]
                sampled += 1
                min_channel = min(min_channel, red, green, blue)
                max_channel = max(max_channel, red, green, blue)
                channel_range = max(red, green, blue) - min(red, green, blue)
                if alpha > 10 and (min(red, green, blue) < 245 or channel_range > 10):
                    non_blank += 1
                if alpha > 10 and channel_range > 30:
                    colorful += 1
        previous = row

    if sampled == 0:
        return None
    non_blank_ratio = non_blank / sampled
    colorful_ratio = colorful / sampled
    return {
        "format": "png",
        "width": width,
        "height": height,
        "sampled_pixels": sampled,
        "non_blank_pixels": non_blank,
        "non_blank_ratio": round(non_blank_ratio, 6),
        "colorful_pixels": colorful,
        "colorful_ratio": round(colorful_ratio, 6),
        "color_range": max_channel - min_channel,
        "ready": bool(
            non_blank_ratio >= _VISUAL_PIXEL_READY_RATIO
            or (non_blank_ratio >= 0.01 and colorful_ratio >= 0.01)
        ),
    }


def _hcaptcha_visual_pixel_probe(
    frame: Any,
    body: Any,
    *,
    body_png: bytes = b"",
) -> dict[str, Any]:
    """Check rendered pixels, including the cross-origin canvas compatibility path."""
    body_stats = _png_visual_stats(body_png, focus=_VISUAL_PIXEL_FOCUS)
    canvas_stats: list[dict[str, Any]] = []
    locate = getattr(frame, "locator", None)
    if callable(locate):
        try:
            canvas_collection = locate("canvas")
            canvas_count = int(canvas_collection.count())
        except Exception:
            canvas_count = 0
        for index in range(canvas_count):
            try:
                canvas = canvas_collection.nth(index)
                if not bool(canvas.is_visible(timeout=250)):
                    continue
                stats = _png_visual_stats(_locator_png(canvas))
            except Exception:
                stats = None
            if stats is not None:
                canvas_stats.append(stats)
    probes = ([body_stats] if body_stats is not None else []) + canvas_stats
    body_ready = body_stats.get("ready") is True if body_stats is not None else None
    canvas_ready = any(item.get("ready") is True for item in canvas_stats)
    return {
        "available": bool(probes),
        # The body screenshot is the exact payload sent to the classifier. A
        # canvas is only a fallback when that PNG cannot be inspected.
        "ready": body_ready if body_ready is not None else canvas_ready,
        "source": "body" if body_ready is not None else "canvas" if canvas_stats else "none",
        "body": body_stats,
        "canvas": canvas_stats,
    }


def _jpeg_image_size(value: bytes) -> tuple[int, int] | None:
    data = bytes(value)
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    index = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while index + 4 <= len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        while index < len(data) and data[index] == 0xFF:
            index += 1
        if index >= len(data):
            break
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xDA or index + 2 > len(data):
            break
        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2 or index + segment_length > len(data):
            break
        if marker in sof_markers and segment_length >= 7:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return (width, height) if width > 0 and height > 0 else None
        index += segment_length
    return None


def _png_image_size(value: bytes) -> tuple[int, int] | None:
    data = bytes(value or b"")
    if not data.startswith(_PNG_SIGNATURE) or len(data) < 24:
        return None
    if data[12:16] != b"IHDR":
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return (width, height) if width > 0 and height > 0 else None


def _image_size(value: bytes) -> tuple[int, int] | None:
    return _png_image_size(value) or _jpeg_image_size(value)


def _raw_image_base64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _locator_boxes(locators: list[Any]) -> list[dict[str, float]]:
    boxes: list[dict[str, float]] = []
    for locator in locators:
        try:
            box = locator.bounding_box(timeout=2_000)
        except Exception:
            box = None
        if (
            not isinstance(box, dict)
            or float(box.get("width") or 0) <= 0
            or float(box.get("height") or 0) <= 0
        ):
            return []
        boxes.append(
            {
                "x": float(box["x"]),
                "y": float(box["y"]),
                "width": float(box["width"]),
                "height": float(box["height"]),
            }
        )
    return boxes


def _capture_hcaptcha_anchors(frame: Any) -> list[str]:
    locators, _selector = _visible_frame_locators(frame, _HCAPTCHA_ANCHOR_SELECTORS)
    anchors: list[str] = []
    for locator in locators[:4]:
        try:
            anchors.append(_raw_image_base64(_locator_jpeg(locator)))
        except PlusCheckoutPluginError:
            continue
    return anchors


def _hcaptcha_visual_resource_state(frame: Any) -> dict[str, Any]:
    evaluate = getattr(frame, "evaluate", None)
    if not callable(evaluate):
        # A non-Playwright test double may expose only screenshot/locator APIs.
        # Let the capture plus digest-stability checks guard that compatibility path.
        return {
            "inspection": "unavailable",
            "ready": True,
            "visual_content_count": 1,
            "visual_content_present": True,
        }
    try:
        raw_state = evaluate(_HCAPTCHA_VISUAL_RESOURCE_STATE_SCRIPT)
    except Exception as error:
        return {
            "inspection": "error",
            "ready": False,
            "reason": f"resource_probe_error:{type(error).__name__}",
        }
    if not isinstance(raw_state, dict) or raw_state.get("probe_ok") is not True:
        return {
            "inspection": "invalid",
            "ready": False,
            "reason": "resource_probe_invalid",
        }
    raw_canvas_bitmap_ready = raw_state.get("canvas_bitmap_ready")
    canvas_bitmap_ready = (
        raw_canvas_bitmap_ready
        if isinstance(raw_canvas_bitmap_ready, bool)
        else None
    )
    ready = raw_state.get("ready") is True and canvas_bitmap_ready is not False
    raw_visual_content_present = raw_state.get("visual_content_present")
    visual_content_present = (
        raw_visual_content_present
        if isinstance(raw_visual_content_present, bool)
        else None
    )
    return {
        "inspection": "dom",
        "ready": ready,
        "reason": (
            ""
            if ready
            else "canvas_bitmap_pending"
            if canvas_bitmap_ready is False
            else "resources_pending"
        ),
        "image_count": int(raw_state.get("image_count") or 0),
        "challenge_image_count": int(raw_state.get("challenge_image_count") or 0),
        "pending_image_count": int(raw_state.get("pending_image_count") or 0),
        "tile_count": int(raw_state.get("tile_count") or 0),
        "tile_visual_missing_count": int(
            raw_state.get("tile_visual_missing_count") or 0
        ),
        "canvas_count": int(raw_state.get("canvas_count") or 0),
        "canvas_bitmap_ready": canvas_bitmap_ready,
        "canvas_blank_count": int(raw_state.get("canvas_blank_count") or 0),
        "canvas_data_url_length": int(raw_state.get("canvas_data_url_length") or 0),
        "visual_content_count": int(raw_state.get("visual_content_count") or 0),
        "visual_content_present": visual_content_present,
    }


def _hcaptcha_visual_capture_candidate(resource_state: dict[str, Any]) -> bool:
    """Allow screenshot stability to decide when DOM readiness is advisory.

    The hCaptcha tile shell may exist before its pixels are attached to the
    element inspected by the probe (for example via a pseudo-element). When
    the frame is visible, no image is still pending, and a visual surface is
    present, `_capture_hcaptcha_visual` is the authoritative check. This keeps
    the classifier path alive without accepting an empty challenge surface.
    """
    if resource_state.get("visual_content_present") is False:
        return False
    if int(resource_state.get("pending_image_count") or 0) > 0:
        return False
    if resource_state.get("body_ready") is False:
        return False
    if resource_state.get("canvas_bitmap_ready") is False:
        return False
    visual_content_count = int(resource_state.get("visual_content_count") or 0)
    tile_count = int(resource_state.get("tile_count") or 0)
    challenge_image_count = int(resource_state.get("challenge_image_count") or 0)
    canvas_count = int(resource_state.get("canvas_count") or 0)
    return bool(
        visual_content_count > 0
        and (tile_count >= 2 or challenge_image_count > 0 or canvas_count > 0)
    )


def _hcaptcha_visual_readiness_trace_fields(
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Return optional probe diagnostics without changing old trace fixtures."""
    return {
        key: readiness[key]
        for key in (
            "tile_visual_missing_count",
            "body_ready",
            "canvas_count",
            "canvas_bitmap_ready",
            "canvas_blank_count",
            "canvas_data_url_length",
            "probe_ready",
            "capture_candidate",
            "visual_pixel_probe",
        )
        if key in readiness
    }


def _capture_hcaptcha_visual(frame: Any) -> dict[str, Any]:
    locate = getattr(frame, "locator", None)
    if not callable(locate):
        raise PlusCheckoutPluginError("plus_checkout_captcha_visual_frame_invalid")
    body = _first_locator(locate("body"))
    try:
        box = body.bounding_box(timeout=2_000)
    except Exception as error:
        raise PlusCheckoutPluginError(
            f"plus_checkout_captcha_visual_capture_failed:{type(error).__name__}:{error}"
        ) from error
    body_png = _locator_png(body)
    pixel_probe = _hcaptcha_visual_pixel_probe(frame, body, body_png=body_png)
    if pixel_probe.get("available") is True and pixel_probe.get("ready") is not True:
        raise _HcaptchaVisualSurfaceNotReady(
            "plus_checkout_captcha_visual_surface_blank",
            probe=pixel_probe,
        )
    screenshot = body_png or _locator_jpeg(body)
    if (
        not isinstance(box, dict)
        or float(box.get("width") or 0) <= 0
        or float(box.get("height") or 0) <= 0
        or not screenshot
    ):
        raise PlusCheckoutPluginError("plus_checkout_captcha_visual_capture_invalid")
    body_bytes = bytes(screenshot)
    image_size = _image_size(body_bytes)
    if image_size is None:
        image_size = (round(float(box["width"])), round(float(box["height"])))
    prompt = _read_hcaptcha_prompt(frame, body)
    image_locators, image_selector = _visible_frame_locators(
        frame,
        _HCAPTCHA_GRID_IMAGE_SELECTORS,
    )
    click_locators, click_selector = _visible_frame_locators(
        frame,
        _HCAPTCHA_GRID_CLICK_SELECTORS,
    )
    grid_mode = len(image_locators) >= 2
    queries: list[str]
    tile_boxes: list[dict[str, float]] = []
    if grid_mode:
        tile_images = [_locator_jpeg(locator) for locator in image_locators]
        queries = [_raw_image_base64(image) for image in tile_images]
        coordinate_locators = (
            click_locators if len(click_locators) == len(image_locators) else image_locators
        )
        tile_boxes = _locator_boxes(coordinate_locators)
        if len(tile_boxes) != len(queries):
            raise PlusCheckoutPluginError("plus_checkout_captcha_grid_coordinates_missing")
    else:
        queries = [_raw_image_base64(body_bytes)]
    return {
        "box": {
            "x": float(box["x"]),
            "y": float(box["y"]),
            "width": float(box["width"]),
            "height": float(box["height"]),
        },
        "query_image_size": {
            "width": int(image_size[0]),
            "height": int(image_size[1]),
        },
        "mode": "grid" if grid_mode else "visual",
        "queries": queries,
        "anchors": _capture_hcaptcha_anchors(frame) if grid_mode else [],
        "tile_boxes": tile_boxes,
        "image_digest": hashlib.sha256(body_bytes).hexdigest(),
        "question": prompt,
        "frame_url": _frame_url(frame),
        "image_selector": image_selector,
        "click_selector": click_selector,
        "visual_pixel_probe": pixel_probe,
    }


def _wait_for_hcaptcha_visual_ready(
    frame: Any,
    *,
    timeout_s: float = _HCAPTCHA_VISUAL_READY_WAIT_S,
    poll_s: float = _HCAPTCHA_VISUAL_READY_POLL_S,
    stable_samples_required: int = _HCAPTCHA_VISUAL_STABLE_SAMPLES,
    min_settle_s: float = _HCAPTCHA_VISUAL_MIN_SETTLE_S,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return the first fully loaded, stable challenge snapshot."""
    started_at = time.monotonic()
    deadline = started_at + max(0.0, float(timeout_s))
    required = max(2, int(stable_samples_required))
    previous_digest = ""
    stable_samples = 0
    probe_count = 0
    resource_state: dict[str, Any] = {"inspection": "unknown"}
    last_reason = "visual_not_ready"
    content_started_at: float | None = None
    min_settle = max(0.0, float(min_settle_s))
    last_pixel_probe: dict[str, Any] | None = None

    while True:
        probe_count += 1
        resource_state = _hcaptcha_visual_resource_state(frame)
        snapshot: dict[str, Any] | None = None
        probe_ready = resource_state.get("ready") is True
        capture_candidate = probe_ready or _hcaptcha_visual_capture_candidate(
            resource_state
        )
        if capture_candidate:
            visual_content_present = resource_state.get("visual_content_present")
            if visual_content_present is None:
                visual_content_present = bool(
                    resource_state.get("visual_content_count")
                    or resource_state.get("challenge_image_count")
                    or resource_state.get("tile_count")
                    or resource_state.get("canvas_count")
                    or resource_state.get("image_count")
                )
            if not visual_content_present:
                content_started_at = None
                stable_samples = 0
                last_reason = "visual_content_missing"
            else:
                now = time.monotonic()
                if content_started_at is None:
                    content_started_at = now
                content_waited_s = now - content_started_at
                if content_waited_s < min_settle:
                    stable_samples = 0
                    last_reason = "visual_render_settling"
                else:
                    try:
                        snapshot = _capture_hcaptcha_visual(frame)
                    except _HcaptchaVisualSurfaceNotReady as error:
                        last_pixel_probe = dict(error.probe)
                        last_reason = str(error)
                    except PlusCheckoutPluginError as error:
                        last_reason = str(error)[:200] or "visual_capture_not_ready"
            if snapshot is not None:
                digest = str(snapshot.get("image_digest") or "")
                stable_samples = stable_samples + 1 if digest == previous_digest else 1
                previous_digest = digest
                if digest and stable_samples >= required:
                    return snapshot, {
                        **resource_state,
                        "status": "ready",
                        "probe_ready": probe_ready,
                        "capture_candidate": capture_candidate,
                        "waited_ms": int((time.monotonic() - started_at) * 1_000),
                        "probe_count": probe_count,
                        "stable_samples": stable_samples,
                        "visual_settle_ms": int(
                            max(0.0, time.monotonic() - (content_started_at or started_at))
                            * 1_000
                        ),
                    }
                last_reason = "visual_render_stabilizing"
        else:
            content_started_at = None
            stable_samples = 0
            last_reason = str(resource_state.get("reason") or "resources_pending")

        if time.monotonic() >= deadline:
            return None, {
                **resource_state,
                "status": "not_ready",
                "probe_ready": resource_state.get("ready") is True,
                "capture_candidate": _hcaptcha_visual_capture_candidate(resource_state),
                "reason": last_reason,
                "visual_pixel_probe": last_pixel_probe,
                "waited_ms": int((time.monotonic() - started_at) * 1_000),
                "probe_count": probe_count,
                "stable_samples": stable_samples,
            }
        time.sleep(max(0.0, float(poll_s)))


def _coordinate_pair(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _image_to_text_point(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, dict) or "x" not in value or "y" not in value:
        return None
    return _coordinate_pair((value.get("x"), value.get("y")))


def _image_to_text_coordinate_space(parsed: dict[str, Any]) -> dict[str, float]:
    raw_space = parsed.get("coordinate_space")
    if raw_space is None:
        return dict(_IMAGE_TO_TEXT_COORDINATE_SPACE)
    if not isinstance(raw_space, dict):
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_coordinate_space_invalid"
        )
    try:
        width = float(raw_space.get("width"))
        height = float(raw_space.get("height"))
    except (TypeError, ValueError) as error:
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_coordinate_space_invalid"
        ) from error
    if width <= 0 or height <= 0:
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_coordinate_space_invalid"
        )
    return {"width": width, "height": height}


def _image_to_text_solution(solution: Any) -> dict[str, Any]:
    if not isinstance(solution, dict):
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_solution_missing"
        )
    raw_text = solution.get("text")
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_solution_missing"
        )
    try:
        parsed = json.loads(raw_text)
    except (TypeError, ValueError) as error:
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_solution_invalid"
        ) from error
    if not isinstance(parsed, dict):
        raise PlusCheckoutPluginError(
            "plus_checkout_captcha_image_to_text_solution_invalid"
        )

    captcha_type = str(parsed.get("captcha_type") or "").strip().lower()
    coordinate_space = _image_to_text_coordinate_space(parsed)
    if captcha_type == "click":
        raw_clicks = parsed.get("clicks")
        if not isinstance(raw_clicks, list):
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_image_to_text_clicks_missing"
            )
        points = [_image_to_text_point(value) for value in raw_clicks]
        if any(point is None for point in points):
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_image_to_text_clicks_invalid"
            )
        normalized = {
            **parsed,
            "type": "click",
            "box": [
                {"x": point[0], "y": point[1]}
                for point in points
                if point is not None
            ],
            "_coordinate_space": coordinate_space,
        }
        if not points:
            normalized["objects"] = []
        return normalized

    if captcha_type == "slide":
        slider = _image_to_text_point(parsed.get("slider"))
        try:
            drag_distance = float(parsed.get("drag_distance"))
        except (TypeError, ValueError) as error:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_image_to_text_slide_invalid"
            ) from error
        if slider is None:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_image_to_text_slide_invalid"
            )
        return {
            **parsed,
            "type": "drag",
            "box": [
                {
                    "start": [slider[0], slider[1]],
                    "end": [slider[0] + drag_distance, slider[1]],
                }
            ],
            "_coordinate_space": coordinate_space,
        }

    if captcha_type == "drag_match":
        raw_pairs = parsed.get("pairs")
        if not isinstance(raw_pairs, list) or not raw_pairs:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_image_to_text_drag_match_missing"
            )
        pairs: list[dict[str, list[float]]] = []
        for value in raw_pairs:
            if not isinstance(value, dict):
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_image_to_text_drag_match_invalid"
                )
            start = _image_to_text_point(value.get("from"))
            end = _image_to_text_point(value.get("to"))
            if start is None or end is None:
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_image_to_text_drag_match_invalid"
                )
            pairs.append(
                {
                    "start": [start[0], start[1]],
                    "end": [end[0], end[1]],
                }
            )
        return {
            **parsed,
            "type": "drag",
            "box": pairs,
            "_coordinate_space": coordinate_space,
        }

    raise PlusCheckoutPluginError(
        f"plus_checkout_captcha_image_to_text_type_unsupported:{captcha_type}"
    )


def _classification_index_list(value: Any) -> list[int] | None:
    """Normalize a provider's 0-based tile answer.

    YesCaptcha-compatible providers have returned both an index list
    (``[1, 4, 6]``) and a boolean mask (``[False, True, ...]``).  Some
    compatibility layers serialize the index list as JSON or a comma-
    separated string, so accept those representations at this boundary.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            value = json.loads(text)
        except (TypeError, ValueError):
            parts = [part for part in re.split(r"[\s,;]+", text) if part]
            if not parts or not all(re.fullmatch(r"\d+", part) for part in parts):
                return None
            value = parts
    if not isinstance(value, (list, tuple)):
        return None
    if not value:
        return []
    if all(isinstance(item, bool) for item in value):
        return [index for index, selected in enumerate(value) if selected]

    indexes: list[int] = []
    for item in value:
        if isinstance(item, bool):
            return None
        if isinstance(item, int):
            index = item
        elif isinstance(item, str) and re.fullmatch(r"\d+", item.strip()):
            index = int(item.strip())
        else:
            return None
        if index < 0:
            return None
        if index not in indexes:
            indexes.append(index)
    return indexes


def _hcaptcha_classification_actions(solution: dict[str, Any]) -> list[dict[str, Any]]:
    kind = str(solution.get("type") or "").strip().lower()
    # Prefer an explicit ranked answer when present.  The provider's
    # ``top_k`` is already a 0-based index list; do not treat an empty list by
    # itself as a valid answer because an absent/unparsed response also often
    # contains an empty compatibility field.
    top_k = solution.get("top_k")
    explicit_empty_classification = False
    top_k_indexes = _classification_index_list(top_k)
    if top_k_indexes:
        return [{"type": "tile", "index": index} for index in top_k_indexes]

    for field in ("objects", "answer"):
        if field not in solution:
            continue
        indexes = _classification_index_list(solution.get(field))
        if indexes is None:
            continue
        tile_actions = [{"type": "tile", "index": index} for index in indexes]
        if tile_actions:
            return tile_actions
        if indexes == []:
            explicit_empty_classification = True

    boxes = solution.get("box")
    actions: list[dict[str, Any]] = []
    if isinstance(boxes, dict):
        boxes = [boxes]
    if isinstance(boxes, list):
        for item in boxes:
            if isinstance(item, dict):
                start = _coordinate_pair(item.get("start"))
                end = _coordinate_pair(item.get("end"))
                if start is not None and end is not None:
                    actions.append({"type": "drag", "start": start, "end": end})
                    continue
                point = _coordinate_pair(item.get("point") or item.get("position"))
                if point is None and "x" in item and "y" in item:
                    point = _coordinate_pair((item.get("x"), item.get("y")))
                if point is not None:
                    actions.append({"type": "click", "point": point})
            else:
                point = _coordinate_pair(item)
                if point is not None:
                    actions.append({"type": "click", "point": point})
        if not actions and boxes and all(
            isinstance(value, (int, float, str)) for value in boxes
        ):
            for index in range(0, len(boxes) - 1, 2):
                point = _coordinate_pair(boxes[index : index + 2])
                if point is not None:
                    actions.append({"type": "click", "point": point})
    if kind == "drag" and any(action["type"] != "drag" for action in actions):
        raise PlusCheckoutPluginError("plus_checkout_captcha_classification_drag_invalid")
    if not actions:
        if explicit_empty_classification and kind != "drag":
            # An explicit empty classification means the current visual round
            # should use hCaptcha's Skip control to request the next round.
            return []
        raise PlusCheckoutPluginError("plus_checkout_captcha_classification_actions_missing")
    return actions


def _visual_relative_point(
    snapshot: dict[str, Any],
    point: tuple[float, float],
    *,
    box: dict[str, Any] | None = None,
    source_size: dict[str, Any] | None = None,
) -> tuple[float, float]:
    target_box = box if isinstance(box, dict) else snapshot["box"]
    image_size = (
        source_size if isinstance(source_size, dict) else snapshot.get("query_image_size")
    )
    source_width = float(
        image_size.get("width")
        if isinstance(image_size, dict) and image_size.get("width")
        else snapshot["box"]["width"]
    )
    source_height = float(
        image_size.get("height")
        if isinstance(image_size, dict) and image_size.get("height")
        else snapshot["box"]["height"]
    )
    source_x = min(max(float(point[0]), 0.0), source_width)
    source_y = min(max(float(point[1]), 0.0), source_height)
    return (
        source_x * float(target_box["width"]) / source_width,
        source_y * float(target_box["height"]) / source_height,
    )


def _visual_page_point(
    snapshot: dict[str, Any],
    point: tuple[float, float],
    *,
    box: dict[str, Any] | None = None,
    source_size: dict[str, Any] | None = None,
) -> tuple[float, float]:
    target_box = box if isinstance(box, dict) else snapshot["box"]
    relative_x, relative_y = _visual_relative_point(
        snapshot,
        point,
        box=target_box,
        source_size=source_size,
    )
    return float(target_box["x"]) + relative_x, float(target_box["y"]) + relative_y


def _hcaptcha_body(frame: Any | None) -> Any | None:
    locate = getattr(frame, "locator", None)
    if not callable(locate):
        return None
    try:
        return _first_locator(locate("body"))
    except Exception:
        return None


def _locator_visual_digest(locator: Any | None) -> str:
    if locator is None:
        return ""
    try:
        return hashlib.sha256(_locator_jpeg(locator)).hexdigest()
    except (AttributeError, PlusCheckoutPluginError):
        return ""


def _apply_hcaptcha_classification(
    page: Any,
    *,
    snapshot: dict[str, Any],
    solution: dict[str, Any],
    frame: Any | None = None,
) -> list[dict[str, Any]]:
    mouse = getattr(page, "mouse", None)
    if mouse is None:
        raise PlusCheckoutPluginError("plus_checkout_captcha_browser_mouse_missing")
    actions = _hcaptcha_classification_actions(solution)
    source_size = solution.get("_coordinate_space")
    if not isinstance(source_size, dict):
        source_size = None
    applied: list[dict[str, Any]] = []
    body = _hcaptcha_body(frame)
    for action in actions:
        if action["type"] == "tile":
            index = int(action["index"])
            tile_boxes = snapshot.get("tile_boxes")
            if not isinstance(tile_boxes, list) or index >= len(tile_boxes):
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_classification_tile_invalid"
                )
            box = tile_boxes[index]
            point = (
                float(box["x"]) + float(box["width"]) / 2,
                float(box["y"]) + float(box["height"]) / 2,
            )
            mouse.move(*point, steps=6)
            mouse.click(*point)
            applied.append({"type": "tile", "index": index})
        elif action["type"] == "drag":
            current_box = None
            if body is not None:
                try:
                    current_box = body.bounding_box(timeout=2_000)
                except Exception:
                    current_box = None
            start = _visual_page_point(
                snapshot,
                action["start"],
                box=current_box,
                source_size=source_size,
            )
            end = _visual_page_point(
                snapshot,
                action["end"],
                box=current_box,
                source_size=source_size,
            )
            # Camoufox humanizes every generated mouse step. The previous
            # 8+16-step gesture kept the button down for tens of seconds and
            # hCaptcha discarded the drag before mouseup.
            mouse.move(*start, steps=1)
            mouse.down()
            try:
                time.sleep(0.08)
                mouse.move(*end, steps=2)
                time.sleep(0.08)
            finally:
                mouse.up()
            applied.append({"type": "drag", "start": start, "end": end})
        else:
            current_box = None
            if body is not None:
                try:
                    current_box = body.bounding_box(timeout=2_000)
                except Exception:
                    current_box = None
            raw_point = action["point"]
            relative_point = _visual_relative_point(
                snapshot,
                raw_point,
                box=current_box,
                source_size=source_size,
            )
            point = _visual_page_point(
                snapshot,
                raw_point,
                box=current_box,
                source_size=source_size,
            )
            before_digest = _locator_visual_digest(body)
            method = "page_mouse"
            click_fallback_error = ""
            visual_surface = str(snapshot.get("mode") or "").strip().lower() == "visual"
            if (
                body is not None
                and callable(getattr(body, "click", None))
                and not visual_surface
            ):
                try:
                    body.click(
                        position={"x": relative_point[0], "y": relative_point[1]},
                        timeout=5_000,
                    )
                    method = "frame_body"
                except Exception as error:
                    click_fallback_error = f"{type(error).__name__}:{error}"
                    try:
                        mouse.move(*point, steps=1)
                        mouse.click(*point)
                        method = "page_mouse_fallback"
                    except Exception as fallback_error:
                        raise PlusCheckoutPluginError(
                            "plus_checkout_captcha_click_failed:"
                            f"body={click_fallback_error};"
                            f"mouse={type(fallback_error).__name__}:{fallback_error}"
                        ) from fallback_error
            else:
                mouse.move(*point, steps=1)
                mouse.click(*point)
            time.sleep(0.2)
            after_digest = _locator_visual_digest(body)
            visual_changed = (
                before_digest != after_digest
                if before_digest and after_digest
                else None
            )
            applied.append(
                {
                    "type": "click",
                    "raw_point": raw_point,
                    "relative_point": relative_point,
                    "point": point,
                    "method": method,
                    "visual_changed": visual_changed,
                    **(
                        {"fallback_error": click_fallback_error}
                        if click_fallback_error
                        else {}
                    ),
                }
            )
            continue
        time.sleep(0.2)
    return applied


def _hcaptcha_control_label(locator: Any) -> str:
    values: list[str] = []
    for attribute in ("aria-label", "title"):
        try:
            values.append(str(locator.get_attribute(attribute) or ""))
        except Exception:
            pass
    try:
        values.append(str(locator.inner_text(timeout=500) or ""))
    except Exception:
        pass
    return " ".join(" ".join(values).lower().split())


def _click_hcaptcha_control(frame: Any, *, control: str) -> bool:
    selectors = (
        _HCAPTCHA_SKIP_SELECTORS
        if control == "skip"
        else _HCAPTCHA_VERIFY_SELECTORS
    )
    for selector in selectors:
        located = _visible_frame_locator(frame, (selector,))
        if located is None:
            continue
        locator, _selector = located
        label = _hcaptcha_control_label(locator)
        if control == "skip":
            if "skip" not in label:
                continue
        elif "skip" in label or not any(
            marker in label for marker in ("verify", "submit", "next")
        ):
            continue
        for force in (False, True):
            try:
                locator.click(timeout=1_200, force=force)
                return True
            except Exception:
                pass
        try:
            if locator.evaluate("(element) => { element.click(); return true; }"):
                return True
        except Exception:
            continue
    return False


def _click_hcaptcha_verify(frame: Any, *, allow_skip: bool = False) -> bool:
    """Click the requested hCaptcha control without mixing Verify and Skip."""
    return _click_hcaptcha_control(
        frame,
        control="skip" if allow_skip else "verify",
    )


def _hcaptcha_visual_digest(frame: Any) -> str:
    locate = getattr(frame, "locator", None)
    if not callable(locate):
        return ""
    try:
        body = _first_locator(locate("body"))
        return hashlib.sha256(_locator_jpeg(body)).hexdigest()
    except (AttributeError, PlusCheckoutPluginError):
        return ""


def _hcaptcha_visual_key(snapshot: dict[str, Any]) -> str:
    """Identify one challenge round without exposing its image contents.

    hCaptcha can reuse the same grid while changing the target prompt (and
    the anchor image can change independently).  The full-page screenshot
    digest alone therefore cannot identify a round reliably.
    """
    def digest_value(value: Any) -> str:
        text = str(value or "").strip()
        if text.startswith("data:") and "," in text:
            text = text.split(",", 1)[1]
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    material = {
        "image_digest": str(snapshot.get("image_digest") or ""),
        "question": " ".join(str(snapshot.get("question") or "").split()),
        "anchors": [digest_value(value) for value in (snapshot.get("anchors") or [])],
        "queries": [digest_value(value) for value in (snapshot.get("queries") or [])],
    }
    return hashlib.sha256(
        json.dumps(material, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _wait_for_hcaptcha_visual_advance(
    page: Any,
    *,
    previous_digest: str,
    timeout_s: float = _HCAPTCHA_VISUAL_ADVANCE_WAIT_S,
) -> str:
    deadline = time.monotonic() + max(0.0, float(timeout_s))
    while True:
        frame = _find_hcaptcha_visual_frame(page)
        if frame is None:
            return "completed"
        current_digest = _hcaptcha_visual_digest(frame)
        if current_digest and current_digest != previous_digest:
            return "advanced"
        if time.monotonic() >= deadline:
            return "unchanged"
        time.sleep(0.5)


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
    source = "error"
    raw = payload.get("error")
    if not isinstance(raw, dict):
        source = "last_payment_error"
        raw = payload.get("last_payment_error")
    if not isinstance(raw, dict):
        source = "last_setup_error"
        raw = payload.get("last_setup_error")
    if not isinstance(raw, dict) and any(
        key in payload for key in ("type", "code", "decline_code", "param", "message")
    ):
        source = "response"
        raw = payload
    if not isinstance(raw, dict):
        return None
    return {
        "source": source,
        "type": str(raw.get("type") or ""),
        "code": str(raw.get("code") or ""),
        "decline_code": str(raw.get("decline_code") or ""),
        "param": str(raw.get("param") or ""),
        "message": str(raw.get("message") or "")[:500],
    }


def _verify_stripe_checkout_challenge(
    page: Any,
    *,
    challenge: dict[str, Any],
    token: str,
    resp_key: str = "",
    user_agent: str = "",
    trace_emitter: CheckoutChallengeTraceEmitter | None = None,
) -> dict[str, Any]:
    verify_url, intent_type, client_secret = _stripe_verify_challenge_url(challenge)
    trace_context = {
        "intent_id": str(challenge.get("intent_id") or "").strip(),
        "intent_type": intent_type,
        "verify_path": urlsplit(verify_url).path,
    }
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.stripe_source.started",
        trace_context,
    )
    try:
        source = _json_object(
            page.evaluate(READ_PLUS_CHECKOUT_POLL_SOURCE_SCRIPT),
            error_code="plus_checkout_stripe_source_invalid",
        )
    except Exception as error:
        _emit_checkout_challenge_trace(
            trace_emitter,
            "challenge.stripe_source.failed",
            {
                **trace_context,
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            },
            "ERROR",
        )
        raise
    publishable_key = str(source.get("publishable_key") or "").strip()
    if not publishable_key.startswith(("pk_live_", "pk_test_")):
        _emit_checkout_challenge_trace(
            trace_emitter,
            "challenge.stripe_source.failed",
            {**trace_context, "error": "publishable_key_missing"},
            "ERROR",
        )
        raise PlusCheckoutPluginError("plus_checkout_stripe_publishable_key_missing")
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.stripe_source.succeeded",
        {**trace_context, "publishable_key_present": True},
    )

    form = {
        "client_secret": client_secret,
        "captcha_vendor_name": "hcaptcha",
        "key": publishable_key,
        "_stripe_version": _STRIPE_VERSION_FULL,
        "challenge_response_token": token,
    }
    if resp_key:
        form["challenge_response_ekey"] = resp_key
    verify_headers = {"accept": "application/json"}
    solver_user_agent = str(user_agent or "").strip()
    if solver_user_agent:
        verify_headers["user-agent"] = solver_user_agent
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.stripe_verify.started",
        {
            **trace_context,
            "token_length": len(token),
            "resp_key_present": bool(resp_key),
            "user_agent_override": bool(solver_user_agent),
        },
    )
    try:
        response = page.context.request.post(
            verify_url,
            form=form,
            headers=verify_headers,
            timeout=30_000,
        )
    except Exception as error:
        _emit_checkout_challenge_trace(
            trace_emitter,
            "challenge.stripe_verify.failed",
            {
                **trace_context,
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            },
            "ERROR",
        )
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
    response_keys = sorted(str(key) for key in response_payload)[:50]
    verification = {
        "ok": status_code == 200,
        "status_code": status_code,
        "intent_type": intent_type,
        "intent_id": str(challenge.get("intent_id") or "").strip(),
        "intent_status": intent_status,
        "error": intent_error,
        "response_keys": response_keys,
        "response_body_chars": len(response_text),
    }
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.stripe_verify.response",
        {
            **trace_context,
            "status_code": status_code,
            "intent_status": intent_status,
            "response_keys": response_keys,
            "response_body_chars": len(response_text),
            "error_source": str((intent_error or {}).get("source") or ""),
            "error_type": str((intent_error or {}).get("type") or ""),
            "error_code": str((intent_error or {}).get("code") or ""),
            "decline_code": str((intent_error or {}).get("decline_code") or ""),
            "error_param": str((intent_error or {}).get("param") or ""),
            "error_message": str((intent_error or {}).get("message") or ""),
        },
        "INFO" if status_code == 200 else "ERROR",
    )
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
    if challenge.get("browser_classification") is True:
        classification_mode = str(
            challenge.get("classification_mode") or "grid"
        ).strip().lower()
        raw_queries = challenge.get("classification_queries")
        if not isinstance(raw_queries, list):
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_classification_queries_missing"
            )
        queries = []
        for value in raw_queries:
            encoded = str(value or "").strip()
            if encoded.startswith("data:") and "," in encoded:
                encoded = encoded.split(",", 1)[1]
            if encoded:
                queries.append(encoded)
        if not queries:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_classification_queries_missing"
            )
        if classification_mode not in {"grid", "visual"}:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_classification_mode_invalid:"
                + classification_mode
            )
        raw_anchors = challenge.get("classification_anchors")
        anchors = []
        if isinstance(raw_anchors, list):
            for value in raw_anchors:
                encoded = str(value or "").strip()
                if encoded.startswith("data:") and "," in encoded:
                    encoded = encoded.split(",", 1)[1]
                if encoded:
                    anchors.append(encoded)
        question = str(challenge.get("classification_question") or "").strip()
        if not question and not anchors:
            raise PlusCheckoutPluginError(
                "plus_checkout_captcha_classification_question_missing"
            )
        task: dict[str, Any] = {
            "type": "HCaptchaClassification",
            "queries": queries,
        }
        if question:
            task["question"] = question
        if anchors:
            task["anchors"] = anchors
        return task

    provider = str(challenge.get("provider") or "").strip().lower()
    site_key = str(challenge.get("site_key") or "").strip()
    if not provider or not site_key:
        raise PlusCheckoutPluginError("plus_checkout_captcha_context_missing")
    page_url = _yescaptcha_website_url(challenge)
    if provider == "hcaptcha":
        task = {
            "type": "HCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "isInvisible": challenge.get("invisible") is True,
        }
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


_YESCAPTCHA_FRAME_HOSTS = {
    "api.hcaptcha.com",
    "assets.hcaptcha.com",
    "b.stripecdn.com",
    "js.stripe.com",
    "newassets.hcaptcha.com",
    "hcaptcha.com",
    "www.hcaptcha.com",
}


def _yescaptcha_website_url(challenge: dict[str, Any]) -> str:
    """Select the real page URL required by YesCaptcha, never a captcha frame URL."""
    candidates = (
        challenge.get("checkout_page_url"),
        challenge.get("website_url"),
        challenge.get("page_url"),
    )
    for raw in candidates:
        value = str(raw or "").strip()
        if not value:
            continue
        try:
            parsed = urlsplit(unquote(value))
        except ValueError:
            continue
        host = str(parsed.hostname or "").strip().lower()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if host in _YESCAPTCHA_FRAME_HOSTS or "hcaptcha" in host:
            continue
        return value
    raise PlusCheckoutPluginError(
        "plus_checkout_captcha_website_url_missing:"
        " provide the Checkout page URL, not the hCaptcha iframe"
    )


def _remote_captcha_task_variants(challenge: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the single task shape documented by YesCaptcha."""
    return [_remote_captcha_task(challenge)]


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
        task_type = str(task.get("type") or "")
        if task_type == "ImageToTextTask":
            return {
                "provider": "hcaptcha",
                "token": "",
                "task_id": task_id,
                "task_type": task_type,
                "user_agent": "",
                "resp_key": "",
                "solution": _image_to_text_solution(solution),
            }
        if task_type == "HCaptchaClassification":
            if not isinstance(solution, dict) or not solution:
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_classification_solution_missing"
                )
            return {
                "provider": "hcaptcha",
                "token": "",
                "task_id": task_id,
                "task_type": "HCaptchaClassification",
                "user_agent": "",
                "resp_key": "",
                "solution": solution,
            }
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
    classified_visuals: set[str] | None = None,
    trace_emitter: CheckoutChallengeTraceEmitter | None = None,
) -> dict[str, Any] | None:
    if not callable(captcha_solver):
        return None
    challenge = state.get("challenge")
    if not isinstance(challenge, dict) or state.get("challenge_pending") is not True:
        return None
    challenge = dict(challenge)
    route_context_source = "challenge"
    stripe_hcaptcha_challenge = _is_stripe_hcaptcha_challenge(challenge)
    if stripe_hcaptcha_challenge:
        active_context = _stripe_active_challenge_context(challenge)
        if active_context is None:
            active_context = _stripe_active_challenge_context(state.get("checkout_confirm"))
            if active_context is not None:
                route_context_source = "checkout_confirm"
        if active_context is not None:
            challenge = _merge_challenge_details(
                active_context,
                challenge,
            ) or challenge
        else:
            if _mark_deferred_challenge_trace_once(
                challenge_capture,
                reason="active_stripe_challenge_missing",
                challenge=challenge,
            ):
                _emit_checkout_challenge_trace(
                    trace_emitter,
                    "challenge.route.deferred",
                    {
                        "provider": "hcaptcha",
                        "route": "stripe_verify",
                        "reason": "active_stripe_challenge_missing",
                    },
                    "WARN",
                )
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
        payload["page_url"] = top_page_url
    try:
        user_agent = str(page.evaluate(READ_BROWSER_USER_AGENT_SCRIPT) or "").strip()
    except Exception:
        user_agent = ""
    if user_agent:
        payload["user_agent"] = user_agent

    if str(challenge.get("provider") or "").strip().lower() == "hcaptcha":
        visual_frame = _find_hcaptcha_visual_frame(page)
        checkbox: dict[str, Any] = {"clicked": False, "reason": "not_attempted"}
        if visual_frame is None:
            checkbox = _click_hcaptcha_checkbox(page)
            if checkbox.get("passed") is True:
                solved_challenges.add(identity)
                _emit_checkout_challenge_trace(
                    trace_emitter,
                    "challenge.browser.completed",
                    {
                        "method": "checkbox",
                        "intent_id": str(challenge.get("intent_id") or ""),
                        "already_advanced": True,
                    },
                )
                return {
                    "identity": identity,
                    "verification": None,
                    "injection": None,
                    "solver_task_id": "",
                    "browser_interaction": {"status": "completed", "method": "checkbox"},
                }
            if checkbox.get("clicked") is True:
                _emit_checkout_challenge_trace(
                    trace_emitter,
                    "challenge.browser.checkbox_clicked",
                    {
                        "method": str(checkbox.get("method") or ""),
                        "intent_id": str(challenge.get("intent_id") or ""),
                        "waited_ms": checkbox.get("waited_ms", 0),
                        "probe_count": checkbox.get("probe_count", 0),
                    },
                )
                visual_status, visual_frame = _wait_for_hcaptcha_visual_frame(
                    page,
                    challenge_capture=challenge_capture,
                    active_intent_id=str(challenge.get("intent_id") or ""),
                )
                if visual_status == "passed":
                    solved_challenges.add(identity)
                    _emit_checkout_challenge_trace(
                        trace_emitter,
                        "challenge.browser.completed",
                        {
                            "method": "checkbox",
                            "intent_id": str(challenge.get("intent_id") or ""),
                        },
                    )
                    return {
                        "identity": identity,
                        "verification": None,
                        "injection": None,
                        "solver_task_id": "",
                        "browser_interaction": {"status": "completed", "method": "checkbox"},
                    }
            if visual_frame is None:
                if checkbox.get("clicked") is True:
                    _emit_checkout_challenge_trace(
                        trace_emitter,
                        "challenge.browser.checkbox_pending",
                        {
                            "checkbox_clicked": True,
                            "reason": "outcome_not_observed",
                            "wait_status": visual_status,
                            "next_action": "retry_checkbox",
                        },
                        "INFO",
                    )
                    return {
                        "identity": identity,
                        "verification": None,
                        "injection": None,
                        "solver_task_id": "",
                        "browser_interaction": {
                            "status": "pending",
                            "method": "checkbox",
                            "retry": True,
                        },
                    }
                else:
                    _emit_checkout_challenge_trace(
                        trace_emitter,
                        "challenge.browser.checkbox_unavailable",
                        {
                            "reason": str(checkbox.get("reason") or "unknown"),
                            "waited_ms": checkbox.get("waited_ms", 0),
                            "probe_count": checkbox.get("probe_count", 0),
                            "frame_count": checkbox.get("frame_count", 0),
                            "fallback": "token_solver",
                        },
                        "WARN",
                    )
        if visual_frame is not None:
            snapshot, visual_readiness = _wait_for_hcaptcha_visual_ready(visual_frame)
            if snapshot is None:
                if _mark_deferred_challenge_trace_once(
                    challenge_capture,
                    reason="visual_not_ready",
                    challenge=challenge,
                ):
                    _emit_checkout_challenge_trace(
                        trace_emitter,
                        "challenge.browser.visual_waiting",
                        {
                            "reason": str(
                                visual_readiness.get("reason")
                                or "visual_not_ready"
                            ),
                            "waited_ms": visual_readiness.get("waited_ms", 0),
                            "probe_count": visual_readiness.get("probe_count", 0),
                            "pending_image_count": visual_readiness.get(
                                "pending_image_count", 0
                            ),
                            "tile_count": visual_readiness.get("tile_count", 0),
                            "visual_content_count": visual_readiness.get(
                                "visual_content_count", 0
                            ),
                            **_hcaptcha_visual_readiness_trace_fields(visual_readiness),
                        },
                        "INFO",
                    )
                return {
                    "identity": identity,
                    "verification": None,
                    "injection": None,
                    "solver_task_id": "",
                    "browser_interaction": {
                        "status": "pending",
                        "method": "visual",
                        "retry": True,
                        "reason": str(
                            visual_readiness.get("reason")
                            or "visual_not_ready"
                        ),
                        "waited_ms": visual_readiness.get("waited_ms", 0),
                    },
                }
            if int(visual_readiness.get("waited_ms") or 0) > 0:
                _emit_checkout_challenge_trace(
                    trace_emitter,
                    "challenge.browser.visual_ready",
                    {
                        "waited_ms": visual_readiness.get("waited_ms", 0),
                        "probe_count": visual_readiness.get("probe_count", 0),
                        "stable_samples": visual_readiness.get("stable_samples", 0),
                        "image_count": visual_readiness.get("image_count", 0),
                        "tile_count": visual_readiness.get("tile_count", 0),
                        "visual_content_count": visual_readiness.get(
                            "visual_content_count", 0
                        ),
                        **_hcaptcha_visual_readiness_trace_fields(visual_readiness),
                        "visual_settle_ms": visual_readiness.get(
                            "visual_settle_ms", 0
                        ),
                    },
                )
            image_digest = str(snapshot["image_digest"])
            seen_visuals = classified_visuals if classified_visuals is not None else set()
            visual_key = _hcaptcha_visual_key(snapshot)
            if visual_key in seen_visuals:
                return None
            _emit_checkout_challenge_trace(
                trace_emitter,
                "challenge.browser.visual_detected",
                {
                    "mode": str(snapshot.get("mode") or ""),
                    "query_count": len(snapshot.get("queries") or []),
                    "anchor_count": len(snapshot.get("anchors") or []),
                    "image_digest": image_digest[:12],
                    "visual_key": visual_key[:12],
                    "css_box": snapshot.get("box"),
                    "query_image_size": snapshot.get("query_image_size"),
                },
            )
            classification_payload = {
                **payload,
                "browser_classification": True,
                "classification_mode": str(snapshot.get("mode") or ""),
                "classification_queries": snapshot["queries"],
                "classification_anchors": snapshot["anchors"],
                "classification_question": snapshot["question"],
            }
            classified = captcha_solver(classification_payload)
            if not isinstance(classified, dict):
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_classification_result_invalid"
                )
            solution = classified.get("solution")
            if not isinstance(solution, dict):
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_classification_solution_missing"
                )
            actions = _hcaptcha_classification_actions(solution)
            _emit_checkout_challenge_trace(
                trace_emitter,
                "challenge.classification.succeeded",
                {
                    "solver_task_id": str(classified.get("task_id") or ""),
                    "task_type": str(classified.get("task_type") or ""),
                    "solution_type": str(solution.get("type") or snapshot.get("mode") or ""),
                    "action_count": len(actions),
                    "empty_selection": not actions,
                },
            )
            action_started_at = time.monotonic()
            applied = _apply_hcaptcha_classification(
                page,
                snapshot=snapshot,
                solution=solution,
                frame=visual_frame,
            )
            action_elapsed_ms = int((time.monotonic() - action_started_at) * 1_000)
            action_types = sorted({str(action.get("type") or "") for action in applied})
            _emit_checkout_challenge_trace(
                trace_emitter,
                "challenge.classification.actions_dispatched",
                {
                    "mode": str(snapshot.get("mode") or ""),
                    "action_count": len(applied),
                    "action_types": action_types,
                    "elapsed_ms": action_elapsed_ms,
                    "actions": applied,
                },
            )
            click_evidence = [
                action.get("visual_changed")
                for action in applied
                if action.get("type") == "click"
                and action.get("visual_changed") is not None
            ]
            if click_evidence and not any(click_evidence):
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_click_not_applied"
                )
            pure_drag = bool(applied) and set(action_types) == {"drag"}
            post_action_digest = _hcaptcha_visual_digest(visual_frame) or image_digest
            control = "verify" if applied else "skip"
            control_required = True if not applied else not pure_drag
            verify_clicked = _click_hcaptcha_verify(visual_frame, allow_skip=not applied)
            if pure_drag and not verify_clicked:
                # Some drag challenges advance on mouseup and never expose a
                # Verify button. Compare against the pre-drag image only for
                # that compatibility path.
                post_action_digest = image_digest
            _emit_checkout_challenge_trace(
                trace_emitter,
                "challenge.browser.verify_clicked",
                {
                    "clicked": verify_clicked,
                    "required": control_required,
                    "control": control,
                    "skip_allowed": not applied,
                    "optional_for_drag": pure_drag,
                },
                "INFO" if verify_clicked or not control_required else "ERROR",
            )
            if control_required and not verify_clicked:
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_visual_skip_missing"
                    if not applied
                    else "plus_checkout_captcha_visual_verify_missing"
                )
            advance_status = _wait_for_hcaptcha_visual_advance(
                page,
                previous_digest=post_action_digest,
            )
            if advance_status == "unchanged":
                raise PlusCheckoutPluginError(
                    "plus_checkout_captcha_visual_not_advanced"
                )
            # Only suppress a visual after the browser accepted the action and
            # moved to the next round (or completed).  A solver/parser/click
            # failure must be retryable, including when the screenshot is
            # unchanged.
            seen_visuals.add(visual_key)
            if advance_status == "completed":
                solved_challenges.add(identity)
            _emit_checkout_challenge_trace(
                trace_emitter,
                f"challenge.browser.{advance_status}",
                {
                    "mode": str(snapshot.get("mode") or ""),
                    "solver_task_id": str(classified.get("task_id") or ""),
                },
            )
            return {
                "identity": identity,
                "verification": None,
                "injection": None,
                "solver_task_id": str(classified.get("task_id") or ""),
                "browser_interaction": {
                    "status": advance_status,
                    "mode": str(snapshot.get("mode") or ""),
                    "action_count": len(applied),
                },
            }

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
        "user_agent": str(
            solved.get("user_agent")
            or solved.get("userAgent")
            or ""
        ).strip(),
    }
    if not injection_payload["provider"] or not injection_payload["token"]:
        raise PlusCheckoutPluginError("plus_checkout_captcha_solver_result_missing")
    route_context = {
        "provider": injection_payload["provider"],
        "solver_task_id": str(solved.get("task_id") or ""),
        "solver_task_type": str(solved.get("task_type") or ""),
        "solver_strategy": solved.get("solver_strategy"),
        "token_length": len(injection_payload["token"]),
        "resp_key_present": bool(injection_payload["resp_key"]),
        "solver_user_agent_present": bool(injection_payload["user_agent"]),
        "solver_user_agent_changed": bool(
            injection_payload["user_agent"]
            and user_agent
            and injection_payload["user_agent"] != user_agent
        ),
        "intent_id": str(challenge.get("intent_id") or "").strip(),
        "has_client_secret": bool(str(challenge.get("client_secret") or "").strip()),
        "has_verify_url": bool(str(challenge.get("verify_url") or "").strip()),
        "context_source": route_context_source,
    }
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.solver.succeeded",
        route_context,
    )
    is_stripe_cross_origin = (
        injection_payload["provider"] == "hcaptcha"
        and str(challenge.get("intent_id") or "").strip()
        and str(challenge.get("client_secret") or "").strip()
    )
    if is_stripe_cross_origin:
        _emit_checkout_challenge_trace(
            trace_emitter,
            "challenge.route.selected",
            {**route_context, "route": "stripe_verify"},
        )
        verification = _verify_stripe_checkout_challenge(
            page,
            challenge=challenge,
            token=injection_payload["token"],
            resp_key=injection_payload["resp_key"],
            user_agent=injection_payload["user_agent"],
            trace_emitter=trace_emitter,
        )
        solved_challenges.add(identity)
        return {
            "identity": identity,
            "verification": verification,
            "injection": None,
            "solver_task_id": str(solved.get("task_id") or ""),
        }
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.route.selected",
        {**route_context, "route": "page_callback_injection"},
    )
    try:
        injection_result = _run_main_world_async(
            page,
            start_script=INJECT_PLUS_CHECKOUT_CAPTCHA_TOKEN_SCRIPT,
            payload=injection_payload,
        )
    except Exception as error:
        _emit_checkout_challenge_trace(
            trace_emitter,
            "challenge.page_injection.failed",
            {
                **route_context,
                "error_type": type(error).__name__,
                "error": str(error)[:500],
            },
            "ERROR",
        )
        raise
    if not isinstance(injection_result, dict):
        raise PlusCheckoutPluginError("plus_checkout_captcha_injection_result_invalid")
    _emit_checkout_challenge_trace(
        trace_emitter,
        "challenge.page_injection.result",
        {
            **route_context,
            "ok": injection_result.get("ok") is True,
            "token_applied": injection_result.get("token_applied") is True,
            "callback_invoked": injection_result.get("callback_invoked") is True,
            "navigation_interrupted": injection_result.get("navigation_interrupted") is True,
        },
        "INFO" if injection_result.get("ok") is True else "ERROR",
    )
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
        detail = _compact_json(
            {
                "http_status": status,
                "tag": result.get("tag"),
                "response": result.get("response"),
            },
            limit=1_500,
        )
        error_type = (
            PlusCheckoutAlreadyPaidError
            if _checkout_create_result_is_already_paid(result)
            else PlusCheckoutCreateError
        )
        error_code = (
            "plus_checkout_already_paid"
            if error_type is PlusCheckoutAlreadyPaidError
            else "plus_checkout_create_failed"
        )
        raise error_type(
            f"{error_code}: HTTP {status} response={detail}",
            result=result,
        )
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
    trace_emitter: CheckoutChallengeTraceEmitter | None = None,
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
        trace_emitter=trace_emitter,
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
    retry_attempts: int = 0,
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
                    allow_redirects=False,
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
    "PlusCheckoutAlreadyPaidError",
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
