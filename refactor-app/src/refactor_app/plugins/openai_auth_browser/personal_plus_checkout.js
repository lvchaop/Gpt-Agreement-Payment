// Browser Console script: mount the current cs_live_* Custom Checkout and submit
// the account's default saved PaymentMethod through Stripe Checkout SDK.
//
// Evidence used by this implementation:
// - cs_live_* route loader data contains publishable_key and cs_*_secret_*.
// - Stripe Custom Checkout initializes with stripe.initCheckout({fetchClientSecret}).
// - Checkout SDK exposes createPaymentElement() and confirm({paymentMethod}).
// - ChatGPT's native cs_live flow enables server updates and manual approval betas.
// - This flow does not use an OAICS CustomerSession or cuss_secret_*.
//
// Run this entire file in the top-level Console on:
//   https://chatgpt.com/checkout/{processor_entity}/{cs_live_...}

(async function mountDefaultPaymentMethodOnCsLiveCheckout() {
  "use strict";

  const StateKey = "__csLiveDefaultPaymentMethodMount";
  const HostId = "__cs_live_default_payment_method_mount__";
  const StripeJsUrl = "https://js.stripe.com/basil/stripe.js";
  const StripeBetas = Object.freeze([
    "custom_checkout_server_updates_1",
    "custom_checkout_manual_approval_1",
  ]);
  const CheckoutRouteId = "routes/checkout.$entity.$checkoutId";
  const PaymentMethodsPath = "/backend-api/payments/payment_methods";
  const CheckoutApprovePath = "/backend-api/payments/checkout/approve";
  const SentinelFlow = "checkout_session_approval";
  const SentinelSdkUrl = "/backend-api/sentinel/sdk.js";
  const NavigateOnSuccess = true;
  const SavedPaymentMethodOptions = {
    enableRedisplay: "auto",
    enableSave: "never",
  };

  const previous = window[StateKey];
  if (previous?.destroy) previous.destroy();

  function now() {
    return new Date().toISOString();
  }

  async function readJsonOrText(response) {
    const text = await response.text();
    if (!text) return null;
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  function findString(value, predicate, seen = new WeakSet()) {
    if (typeof value === "string") return predicate(value) ? value : null;
    if (!value || typeof value !== "object" || seen.has(value)) return null;
    seen.add(value);
    for (const child of Object.values(value)) {
      const found = findString(child, predicate, seen);
      if (found) return found;
    }
    return null;
  }

  function findPersonalAccountId(session, accountsData) {
    if (typeof session?.account?.id === "string" && session.account.id) {
      return session.account.id;
    }

    const accounts = accountsData?.accounts;
    if (!accounts || typeof accounts !== "object") return null;

    const direct = accounts.person?.account || accounts.person;
    if (typeof direct?.account_id === "string" && direct.account_id) {
      return direct.account_id;
    }

    const defaultAccount = accounts.default?.account || accounts.default;
    if (
      defaultAccount?.structure === "personal" &&
      typeof defaultAccount?.account_id === "string" &&
      defaultAccount.account_id
    ) {
      return defaultAccount.account_id;
    }

    for (const entry of Object.values(accounts)) {
      const account = entry?.account || entry;
      if (
        account?.structure === "personal" &&
        typeof account?.account_id === "string" &&
        account.account_id
      ) {
        return account.account_id;
      }
    }
    return null;
  }

  function checkoutIdentifiers() {
    const match = location.pathname.match(
      /^\/checkout\/([^/]+)\/(cs_live_[A-Za-z0-9_-]+)\/?$/,
    );
    if (!match) {
      throw new Error(
        "Run this file on /checkout/{processor_entity}/{cs_live_...}.",
      );
    }
    return {
      processorEntity: decodeURIComponent(match[1]),
      checkoutSessionId: match[2],
    };
  }

  function decodeReactRouterTable(serialized) {
    const table = JSON.parse(serialized);
    const memo = new Map();

    function decodeReference(index) {
      if (index === -5) return null;
      if (index === -1) return undefined;
      if (!Number.isInteger(index) || index < 0 || index >= table.length) {
        throw new Error(`Unsupported React Router reference: ${index}`);
      }
      if (memo.has(index)) return memo.get(index);

      const value = table[index];
      if (value === null || typeof value !== "object") return value;

      if (Array.isArray(value)) {
        const output = [];
        memo.set(index, output);
        for (const child of value) {
          output.push(
            typeof child === "number" ? decodeReference(child) : child,
          );
        }
        return output;
      }

      const output = {};
      memo.set(index, output);
      for (const [encodedKey, child] of Object.entries(value)) {
        const key = /^_\d+$/.test(encodedKey)
          ? decodeReference(Number(encodedKey.slice(1)))
          : encodedKey;
        output[key] =
          typeof child === "number" ? decodeReference(child) : child;
      }
      return output;
    }

    return decodeReference(0);
  }

  function checkoutSessionFromHtml(html) {
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const marker = "window.__reactRouterContext.streamController.enqueue(";

    for (const script of parsed.scripts) {
      const text = script.textContent || "";
      const start = text.indexOf(marker);
      const end = text.lastIndexOf(");");
      if (start < 0 || end <= start) continue;

      try {
        const serialized = JSON.parse(
          text.slice(start + marker.length, end),
        );
        const root = decodeReactRouterTable(serialized);
        const checkoutSession =
          root?.loaderData?.[CheckoutRouteId]?.checkoutSession;
        if (checkoutSession?.checkout_session_id) return checkoutSession;
      } catch (error) {
        console.debug(
          "[cs-live-default-mount] skipped non-Checkout router chunk",
          error?.message || String(error),
        );
      }
    }

    throw new Error("Current Checkout HTML has no checkoutSession loader data.");
  }

  async function readCurrentCheckoutSession(identifiers) {
    const response = await fetch(location.href, {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "text/html" },
    });
    const html = await response.text();
    if (!response.ok) {
      throw new Error(`Checkout page read failed (${response.status}).`);
    }

    const checkoutSession = checkoutSessionFromHtml(html);
    if (checkoutSession.checkout_session_id !== identifiers.checkoutSessionId) {
      throw new Error(
        `Checkout ID mismatch: ${checkoutSession.checkout_session_id}`,
      );
    }
    return checkoutSession;
  }

  function stripeSourceFromCheckoutSession(checkoutSession, identifiers) {
    const clientSecret =
      checkoutSession?.client_secret ||
      checkoutSession?.checkout_session?.client_secret ||
      findString(
        checkoutSession,
        (value) => /^cs_(?:live|test)_[A-Za-z0-9_-]+_secret_[A-Za-z0-9_-]+$/.test(value),
      ) ||
      "";
    const publishableKey =
      checkoutSession?.publishable_key ||
      checkoutSession?.checkout_session?.publishable_key ||
      findString(checkoutSession, (value) => /^pk_(?:live|test)_/.test(value)) ||
      "";

    if (!clientSecret.startsWith(`${identifiers.checkoutSessionId}_secret_`)) {
      throw new Error(
        "Checkout loader data has no matching cs_*_secret_* client secret.",
      );
    }
    if (!/^pk_(?:live|test)_/.test(publishableKey)) {
      throw new Error("Checkout loader data has no Stripe publishable key.");
    }

    return { clientSecret, publishableKey };
  }

  function hostedSavedPaymentMethods(checkoutSdkSession) {
    const candidates = [
      checkoutSdkSession?.elements_options
        ?.__custom_checkout_saved_payment_methods?.payment_methods,
      checkoutSdkSession?.elementsOptions
        ?.__customCheckoutSavedPaymentMethods?.paymentMethods,
      checkoutSdkSession?.customer?.payment_methods,
      checkoutSdkSession?.customer?.paymentMethods,
    ];
    const byId = new Map();
    for (const methods of candidates) {
      if (!Array.isArray(methods)) continue;
      for (const method of methods) {
        if (typeof method?.id === "string" && method.id.startsWith("pm_")) {
          byId.set(method.id, method);
        }
      }
    }
    return [...byId.values()];
  }

  function buildConfirmOptions(paymentMethodId, onRequiresApproval) {
    if (!/^pm_[A-Za-z0-9_-]+$/.test(paymentMethodId)) {
      throw new Error(`Invalid default PaymentMethod ID: ${paymentMethodId}`);
    }
    return {
      paymentMethod: paymentMethodId,
      redirect: "if_required",
      onRequiresApproval,
    };
  }

  function methodLabel(method) {
    if (method?.type !== "card") return method?.type || "Payment method";
    const brand = method.card?.brand || "card";
    const last4 = method.card?.last4 || "----";
    const wallet = method.card?.wallet?.type;
    return `${brand.toUpperCase()} **** ${last4}${wallet ? ` (${wallet})` : ""}`;
  }

  function extractRedirectUrl(value) {
    return (
      value?.redirectUrl ||
      value?.next_action?.redirect_to_url?.url ||
      value?.payment_intent?.next_action?.redirect_to_url?.url ||
      value?.setup_intent?.next_action?.redirect_to_url?.url ||
      value?.session?.payment_intent?.next_action?.redirect_to_url?.url ||
      value?.session?.setup_intent?.next_action?.redirect_to_url?.url ||
      null
    );
  }

  async function loadStripeJs() {
    if (typeof window.Stripe === "function") return window.Stripe;

    await new Promise((resolve, reject) => {
      const existing = [...document.scripts].find(
        (script) => script.src === StripeJsUrl,
      );
      if (existing) {
        if (typeof window.Stripe === "function") {
          resolve();
          return;
        }
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", reject, { once: true });
        return;
      }

      const script = document.createElement("script");
      script.src = StripeJsUrl;
      script.async = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`Stripe.js load failed: ${StripeJsUrl}`));
      document.head.appendChild(script);
    });

    if (typeof window.Stripe !== "function") {
      throw new Error("Stripe.js loaded without window.Stripe.");
    }
    return window.Stripe;
  }

  async function loadSentinelSdk() {
    if (window.SentinelSDK?.token) return window.SentinelSDK;

    let script = [...document.scripts].find((item) => {
      try {
        return new URL(item.src, location.href).pathname === SentinelSdkUrl;
      } catch {
        return false;
      }
    });

    if (!script) {
      script = document.createElement("script");
      script.src = SentinelSdkUrl;
      script.async = true;
      document.head.appendChild(script);
    }

    await new Promise((resolve, reject) => {
      const deadline = Date.now() + 15000;
      const timer = setInterval(() => {
        if (window.SentinelSDK?.token) {
          clearInterval(timer);
          resolve();
          return;
        }
        if (Date.now() >= deadline) {
          clearInterval(timer);
          reject(new Error("SentinelSDK.token() was not ready within 15 seconds."));
        }
      }, 50);
      script.addEventListener(
        "error",
        () => {
          clearInterval(timer);
          reject(new Error(`Sentinel SDK load failed: ${SentinelSdkUrl}`));
        },
        { once: true },
      );
    });

    return window.SentinelSDK;
  }

  async function freshSentinelHeaders() {
    const sdk = await loadSentinelSdk();
    try {
      if (typeof sdk.init === "function") await sdk.init(SentinelFlow);
    } catch (error) {
      console.warn("[cs-live-default-mount] SentinelSDK.init result", error);
    }

    const token = await sdk.token(SentinelFlow);
    const timing = typeof sdk.timing === "function" ? await sdk.timing() : "";
    if (!token) throw new Error("SentinelSDK.token() returned an empty value.");

    return {
      "OpenAI-Sentinel-Token": token,
      ...(timing ? { "OAI-Telemetry": timing } : {}),
    };
  }

  function storageText() {
    const chunks = [];
    for (const storage of [window.localStorage, window.sessionStorage]) {
      try {
        for (let index = 0; index < storage.length; index += 1) {
          const key = storage.key(index);
          chunks.push(`${key}=${storage.getItem(key)}`);
        }
      } catch {}
    }
    return chunks.join("\n");
  }

  function firstMatch(text, regex) {
    return String(text || "").match(regex)?.[1] || "";
  }

  function compactHeaders(headers) {
    return Object.fromEntries(
      Object.entries(headers).filter(
        ([, value]) => value !== undefined && value !== null && value !== "",
      ),
    );
  }

  function currentClientHeaders(targetPath) {
    const storage = storageText();
    const page = `${document.documentElement.innerHTML}\n${storage}`;
    const buildNumber =
      firstMatch(
        page,
        /["']?oai-client-build-number["']?\s*[:=]\s*["']?(\d{5,})/i,
      ) ||
      firstMatch(
        page,
        /["']?(?:clientBuildNumber|buildNumber)["']?\s*[:=]\s*["']?(\d{5,})/i,
      );
    const clientVersion = firstMatch(page, /\b(prod-[a-f0-9]{40})\b/i);
    const deviceId =
      firstMatch(
        storage,
        /(?:oai[-_]?device[-_]?id|device[-_]?id)["'=:\s]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i,
      ) ||
      firstMatch(
        storage,
        /\bdevice[^=:\n]*[=:\s"]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/i,
      );
    const sessionId =
      firstMatch(
        storage,
        /(?:oai[-_]?session[-_]?id|session[-_]?id)["'=:\s]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i,
      ) ||
      firstMatch(
        storage,
        /\bsession[^=:\n]*[=:\s"]+([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/i,
      );
    const deploymentAttestation = firstMatch(
      page,
      /\b(eyJ2ZXJzaW9uIjox[0-9A-Za-z._-]+)\b/,
    );

    return compactHeaders({
      "oai-client-build-number": buildNumber,
      "oai-client-version": clientVersion,
      "oai-device-id": deviceId,
      "oai-language": navigator.language || "",
      "oai-session-id": sessionId,
      "oai-web-deployment-attestation": deploymentAttestation,
      "x-oai-is-client-observation": "true",
      "x-openai-target-path": targetPath,
      "x-openai-target-route": targetPath,
    });
  }

  function createPanel() {
    document.getElementById(HostId)?.remove();
    const host = document.createElement("section");
    host.id = HostId;
    host.style.cssText = [
      "position:fixed",
      "right:18px",
      "bottom:18px",
      "z-index:2147483647",
      "width:min(520px,calc(100vw - 36px))",
      "max-height:calc(100vh - 36px)",
      "overflow:auto",
      "box-sizing:border-box",
      "border:1px solid #d7d7d7",
      "border-radius:8px",
      "background:#fff",
      "box-shadow:0 18px 55px rgba(0,0,0,.28)",
      "padding:16px",
      "color:#202123",
      "font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif",
    ].join(";");
    host.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px">
        <strong style="font-size:16px;letter-spacing:0">Default payment method</strong>
        <button data-action="close" type="button" title="Close" aria-label="Close"
          style="width:32px;height:32px;border:0;background:#f1f1f1;cursor:pointer;font-size:20px;line-height:1">&times;</button>
      </div>
      <div data-role="method" style="margin:12px 0;padding:10px;border:1px solid #ddd;border-radius:6px;background:#f7f7f7"></div>
      <div data-role="status" style="margin-bottom:12px;color:#555;white-space:pre-wrap"></div>
      <div data-role="element" style="min-height:92px"></div>
      <button data-action="submit" type="button" disabled
        style="display:block;width:100%;min-height:44px;margin-top:14px;border:0;border-radius:6px;background:#111827;color:#fff;font:600 14px/1.2 system-ui,-apple-system,Segoe UI,sans-serif;cursor:not-allowed;opacity:.5">
        Waiting for Checkout SDK
      </button>
    `;
    (document.body || document.documentElement).appendChild(host);
    return {
      host,
      method: host.querySelector('[data-role="method"]'),
      status: host.querySelector('[data-role="status"]'),
      close: host.querySelector('[data-action="close"]'),
      submit: host.querySelector('[data-action="submit"]'),
    };
  }

  const panel = createPanel();
  const state = {
    phase: "loading",
    installedAt: now(),
    identifiers: null,
    accountId: null,
    defaultPaymentMethodId: null,
    defaultPaymentMethod: null,
    checkoutSession: null,
    stripeSource: null,
    checkoutSdkSession: null,
    hostedSavedPaymentMethodIds: [],
    defaultPresentInHostedSession: false,
    stripe: null,
    checkoutSdk: null,
    paymentElement: null,
    paymentEvents: [],
    approvalRequests: [],
    approvalClientHeaderNames: [],
    lastRequiresApprovalArgs: null,
    confirmResult: null,
    sessionAfterConfirm: null,
    redirectUrl: null,
    lastError: null,
    status() {
      return {
        phase: this.phase,
        identifiers: this.identifiers,
        accountId: this.accountId,
        defaultPaymentMethodId: this.defaultPaymentMethodId,
        defaultPaymentMethod: this.defaultPaymentMethod,
        stripeSource: this.stripeSource
          ? { hasClientSecret: true, hasPublishableKey: true }
          : null,
        hostedSavedPaymentMethodIds: this.hostedSavedPaymentMethodIds,
        defaultPresentInHostedSession: this.defaultPresentInHostedSession,
        paymentEventCount: this.paymentEvents.length,
        lastPaymentEvent: this.paymentEvents.at(-1) || null,
        approvalRequests: this.approvalRequests,
        approvalClientHeaderNames: this.approvalClientHeaderNames,
        confirmResult: this.confirmResult,
        lastError: this.lastError,
      };
    },
    submitCheckout() {
      throw new Error("Checkout submission is not ready.");
    },
    destroy() {
      try {
        this.paymentElement?.destroy?.();
      } catch {}
      try {
        this.checkoutSdk?.destroy?.();
      } catch {}
      document.getElementById(HostId)?.remove();
      this.phase = "destroyed";
    },
  };
  window[StateKey] = state;
  panel.close.addEventListener("click", () => state.destroy());

  function setSubmitEnabled(enabled, label) {
    panel.submit.disabled = !enabled;
    panel.submit.textContent = label;
    panel.submit.style.cursor = enabled ? "pointer" : "not-allowed";
    panel.submit.style.opacity = enabled ? "1" : ".5";
  }

  function setStatus(message, color = "#555") {
    panel.status.textContent = message;
    panel.status.style.color = color;
  }

  try {
    if (window !== window.top || location.hostname !== "chatgpt.com") {
      throw new Error("Run this file in the top-level chatgpt.com Console context.");
    }

    const identifiers = checkoutIdentifiers();
    state.identifiers = identifiers;
    setStatus("Reading the current cs_live Checkout and account state...");

    const checkoutSession = await readCurrentCheckoutSession(identifiers);
    const stripeSource = stripeSourceFromCheckoutSession(
      checkoutSession,
      identifiers,
    );
    state.checkoutSession = checkoutSession;
    state.stripeSource = stripeSource;

    const authResponse = await fetch("/api/auth/session", {
      credentials: "include",
      cache: "no-store",
    });
    const authSession = await readJsonOrText(authResponse);
    if (!authResponse.ok || !authSession?.accessToken) {
      throw new Error(`Session read failed (${authResponse.status}).`);
    }

    let accountId = findPersonalAccountId(authSession, null);
    if (!accountId) {
      const accountsResponse = await fetch(
        "/backend-api/accounts/check/v4-2023-04-27",
        {
          credentials: "include",
          cache: "no-store",
          headers: { Authorization: `Bearer ${authSession.accessToken}` },
        },
      );
      const accountsData = await readJsonOrText(accountsResponse);
      if (!accountsResponse.ok) {
        throw new Error(`accounts/check failed (${accountsResponse.status}).`);
      }
      accountId = findPersonalAccountId(authSession, accountsData);
    }
    if (!accountId) throw new Error("No personal account_id was found.");
    state.accountId = accountId;

    const paymentMethodsResponse = await fetch(
      `${PaymentMethodsPath}?account_id=${encodeURIComponent(accountId)}`,
      {
        credentials: "include",
        cache: "no-store",
        headers: {
          Authorization: `Bearer ${authSession.accessToken}`,
          "chatgpt-account-id": accountId,
          "x-openai-target-path": PaymentMethodsPath,
          "x-openai-target-route": PaymentMethodsPath,
        },
      },
    );
    const paymentMethodsData = await readJsonOrText(paymentMethodsResponse);
    if (!paymentMethodsResponse.ok) {
      throw new Error(
        `Payment method query failed (${paymentMethodsResponse.status}): ${JSON.stringify(paymentMethodsData)}`,
      );
    }

    const paymentMethods = Array.isArray(paymentMethodsData?.payment_methods)
      ? paymentMethodsData.payment_methods
      : [];
    const defaultPaymentMethodId = paymentMethodsData?.default_payment_method_id;
    const defaultPaymentMethod = paymentMethods.find(
      (method) => method?.id === defaultPaymentMethodId,
    );
    if (!defaultPaymentMethodId || !defaultPaymentMethod) {
      throw new Error(
        `Default PaymentMethod was not returned: ${String(defaultPaymentMethodId || "null")}`,
      );
    }
    state.defaultPaymentMethodId = defaultPaymentMethodId;
    state.defaultPaymentMethod = defaultPaymentMethod;
    const defaultMethodLabel = methodLabel(defaultPaymentMethod);
    panel.method.textContent = `${defaultMethodLabel} (${defaultPaymentMethodId})`;

    const StripeConstructor = await loadStripeJs();
    const stripe = StripeConstructor(stripeSource.publishableKey, {
      betas: StripeBetas,
    });
    if (typeof stripe.initCheckout !== "function") {
      throw new Error("Current Stripe.js has no initCheckout().");
    }

    const checkoutSdk = await stripe.initCheckout({
      fetchClientSecret: async () => stripeSource.clientSecret,
      elementsOptions: {
        savedPaymentMethod: SavedPaymentMethodOptions,
      },
    });
    if (typeof checkoutSdk.createPaymentElement !== "function") {
      throw new Error("Checkout SDK has no createPaymentElement().");
    }
    if (typeof checkoutSdk.confirm !== "function") {
      throw new Error("Checkout SDK has no confirm().");
    }
    state.stripe = stripe;
    state.checkoutSdk = checkoutSdk;

    const checkoutSdkSession =
      typeof checkoutSdk.session === "function"
        ? await checkoutSdk.session()
        : null;
    state.checkoutSdkSession = checkoutSdkSession;
    const hostedMethods = hostedSavedPaymentMethods(checkoutSdkSession);
    state.hostedSavedPaymentMethodIds = hostedMethods.map((method) => method.id);
    state.defaultPresentInHostedSession = state.hostedSavedPaymentMethodIds.includes(
      defaultPaymentMethodId,
    );

    async function approveCheckout() {
      const sentinelHeaders = await freshSentinelHeaders();
      const clientHeaders = currentClientHeaders("/payments/checkout/approve");
      state.approvalClientHeaderNames = Object.keys(clientHeaders);
      const payload = {
        checkout_session_id: identifiers.checkoutSessionId,
        processor_entity: identifiers.processorEntity,
      };
      const response = await fetch(CheckoutApprovePath, {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${authSession.accessToken}`,
          "Content-Type": "application/json",
          "chatgpt-account-id": accountId,
          ...clientHeaders,
          ...sentinelHeaders,
        },
        body: JSON.stringify(payload),
      });
      const body = await readJsonOrText(response);
      const record = {
        at: now(),
        ok: response.ok,
        httpStatus: response.status,
        request: payload,
        response: body,
      };
      state.approvalRequests.push(record);
      console.log("[cs-live-default-mount] checkout/approve response", record);
      if (!response.ok) {
        throw new Error(
          `Checkout approve failed (${response.status}): ${JSON.stringify(body)}`,
        );
      }
      if (["blocked", "exception", "denied", "error"].includes(body?.result)) {
        throw new Error(
          `Checkout approve returned result=${body.result}: ${JSON.stringify(body)}`,
        );
      }
      return body;
    }

    async function onRequiresApproval(...args) {
      state.lastRequiresApprovalArgs = args;
      console.log("[cs-live-default-mount] onRequiresApproval", args);
      return await approveCheckout();
    }

    const paymentElement = checkoutSdk.createPaymentElement({});
    state.paymentElement = paymentElement;
    paymentElement.on("change", (event) => {
      const record = {
        at: now(),
        complete: event?.complete === true,
        empty: event?.empty === true,
        type:
          event?.value?.type ||
          event?.value?.payment_method?.type ||
          null,
        paymentMethodId:
          event?.value?.payment_method?.id ||
          event?.value?.paymentMethod?.id ||
          null,
        error: event?.error?.message || null,
      };
      state.paymentEvents.push(record);
      console.log("[cs-live-default-mount] payment change", record);
    });
    paymentElement.on("ready", () => {
      state.phase = "ready";
      const proof = state.defaultPresentInHostedSession
        ? "The Hosted Checkout session lists this saved PaymentMethod."
        : "The account default will be passed to session-bound Checkout confirm for validation.";
      setStatus(`Checkout SDK ready.\n${proof}`, "#087443");
      setSubmitEnabled(true, `Pay with ${defaultMethodLabel}`);
      console.log("[cs-live-default-mount] ready", state.status());
    });
    paymentElement.mount(`#${HostId} [data-role="element"]`);

    state.submitCheckout = async function submitCheckout() {
      if (!["ready", "submit_failed"].includes(this.phase)) {
        throw new Error(`Checkout SDK is not ready (phase=${this.phase}).`);
      }

      this.phase = "submitting";
      this.lastError = null;
      setSubmitEnabled(false, "Submitting...");
      setStatus("Confirming the cs_live Checkout with the account default...");

      try {
        const confirmOptions = buildConfirmOptions(
          defaultPaymentMethodId,
          onRequiresApproval,
        );
        console.log("[cs-live-default-mount] checkout.confirm options", {
          paymentMethod: confirmOptions.paymentMethod,
          redirect: confirmOptions.redirect,
          hasOnRequiresApproval: true,
        });
        const result = await checkoutSdk.confirm(confirmOptions);
        this.confirmResult = result;
        console.log("[cs-live-default-mount] checkout.confirm result", result);

        const resultError = result?.error;
        if (result?.type === "error" || resultError) {
          throw new Error(
            resultError?.message ||
              result?.message ||
              "Stripe Checkout confirm returned an error.",
          );
        }

        this.sessionAfterConfirm =
          typeof checkoutSdk.session === "function"
            ? await checkoutSdk.session()
            : null;
        const redirectUrl =
          extractRedirectUrl(result) ||
          extractRedirectUrl(this.sessionAfterConfirm);
        this.redirectUrl = redirectUrl;

        this.phase = "submitted";
        setStatus("Checkout submitted successfully.", "#087443");
        setSubmitEnabled(false, "Submitted");

        if (NavigateOnSuccess && redirectUrl) {
          location.assign(redirectUrl);
        }
        return {
          confirmResult: result,
          approvalRequests: this.approvalRequests,
          sessionAfterConfirm: this.sessionAfterConfirm,
          redirectUrl,
        };
      } catch (error) {
        this.phase = "submit_failed";
        this.lastError = error;
        setStatus(error?.message || String(error), "#b42318");
        setSubmitEnabled(true, `Retry with ${defaultMethodLabel}`);
        console.error("[cs-live-default-mount] submit failed", error, this.status());
        throw error;
      }
    };

    panel.submit.addEventListener("click", () => {
      state.submitCheckout().catch(() => {});
    });
  } catch (error) {
    state.phase = "error";
    state.lastError = error;
    setStatus(error?.message || String(error), "#b42318");
    setSubmitEnabled(false, "Unavailable");
    console.error("[cs-live-default-mount] failed", error, state.status());
  }
})();
