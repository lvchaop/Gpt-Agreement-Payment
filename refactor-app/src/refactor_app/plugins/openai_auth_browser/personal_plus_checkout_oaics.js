// Browser Console script: mount the account's default saved PaymentMethod into
// a real Stripe Payment Element on the current OAICS Checkout page.
//
// Run this entire file in the top-level https://chatgpt.com Console after the
// Checkout form has loaded. It mounts a separate Payment Element. A payment is
// submitted only after the user clicks the button added by this script.

(async function mountDefaultPaymentMethodOnOaicsCheckout() {
  "use strict";

  const StateKey = "__oaicsDefaultPaymentMethodMount";
  const HostId = "__oaics_default_payment_method_mount__";
  const StripeJsUrl = "https://js.stripe.com/basil/stripe.js";
  const PaymentMethodsPath = "/backend-api/payments/payment_methods";
  const CheckoutConfirmPath = "/backend-api/payments/checkout/confirm";
  const SentinelFlow = "checkout_session_approval";
  const SentinelSdkUrl = "/backend-api/sentinel/sdk.js";
  const CheckoutRouteId = "routes/checkout.$entity.$checkoutId";
  const StripeBetas = [
    "custom_checkout_server_updates_1",
    "custom_checkout_manual_approval_1",
  ];

  const previous = window[StateKey];
  if (previous?.destroy) previous.destroy();

  function readJsonOrText(response) {
    return response.text().then((text) => {
      if (!text) return null;
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    });
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
      /^\/checkout\/([^/]+)\/(oaics_[A-Za-z0-9_-]+)\/?$/,
    );
    if (!match) {
      throw new Error(
        "Run this file on /checkout/{processor_entity}/{oaics_...}.",
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
          "[oaics-default-mount] skipped non-Checkout router chunk",
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

  function stripeSourceFromCheckoutSession(checkoutSession) {
    const amount = checkoutSession?.checkout_state?.total?.total?.minorUnitsAmount;
    const currency =
      checkoutSession?.checkout_state?.currency ||
      checkoutSession?.billing_details?.currency ||
      "";
    const publishableKey = checkoutSession?.publishable_key || "";
    const customerSessionClientSecret =
      checkoutSession?.customer_session_client_secret || "";
    const paymentMethodTypes = Array.isArray(checkoutSession?.payment_method_types)
      ? checkoutSession.payment_method_types.filter(
          (type) => typeof type === "string" && type,
        )
      : [];

    if (!/^pk_(?:live|test)_/.test(publishableKey)) {
      throw new Error("Checkout loader data has no Stripe publishable key.");
    }
    if (!customerSessionClientSecret.startsWith("cuss_secret_")) {
      throw new Error("Checkout loader data has no CustomerSession client secret.");
    }
    if (!Number.isSafeInteger(amount) || amount < 0) {
      throw new Error(`Invalid Checkout total minorUnitsAmount: ${amount}`);
    }
    if (!/^[a-z]{3}$/i.test(currency)) {
      throw new Error(`Invalid Checkout currency: ${currency}`);
    }

    return {
      publishableKey,
      customerSessionClientSecret,
      amount,
      currency: currency.toLowerCase(),
      mode: "subscription",
      setupFutureUsage: "off_session",
      paymentMethodTypes: paymentMethodTypes.length
        ? [...new Set(paymentMethodTypes)]
        : ["card"],
    };
  }

  async function loadStripeJs() {
    if (typeof window.Stripe === "function") return window.Stripe;

    await new Promise((resolve, reject) => {
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
      console.warn("[oaics-default-mount] SentinelSDK.init result", error);
    }

    const token = await sdk.token(SentinelFlow);
    const timing = typeof sdk.timing === "function" ? await sdk.timing() : "";
    if (!token) throw new Error("SentinelSDK.token() returned an empty value.");

    return {
      "OpenAI-Sentinel-Token": token,
      ...(timing ? { "OAI-Telemetry": timing } : {}),
    };
  }

  function methodLabel(method) {
    if (method?.type !== "card") return `${method?.type || "payment_method"}`;
    const brand = method.card?.brand || "card";
    const last4 = method.card?.last4 || "----";
    const wallet = method.card?.wallet?.type;
    return `${brand.toUpperCase()} **** ${last4}${wallet ? ` (${wallet})` : ""}`;
  }

  function normalizeSavedPaymentMethod(method, checkoutSession) {
    const checkoutState = checkoutSession?.checkout_state || {};
    const checkoutBilling = checkoutState?.billingAddress || {};
    const address = checkoutBilling?.address || null;

    return {
      object: "payment_method",
      allow_redisplay: "always",
      billing_details: {
        address,
        email: checkoutState?.email || null,
        name: checkoutBilling?.name || null,
        phone: null,
        tax_id: null,
      },
      ...method,
    };
  }

  function controllerAction(controller, namePattern, label) {
    const actions = controller?.innerInitiatedActions || controller?.action || controller?._controller?.action;
    const name = actions
      ? Object.keys(actions).find((candidate) => namePattern.test(candidate))
      : null;
    if (!name || typeof actions[name] !== "function") {
      throw new Error(`Stripe controller has no ${label} action.`);
    }
    return actions[name].bind(actions);
  }

  function stripeController(...roots) {
    const seen = new WeakSet();
    const reports = [];
    const queue = roots
      .filter((root) => root && (typeof root === "object" || typeof root === "function"))
      .map((root, index) => ({ value: root, depth: 0, path: `root[${index}]` }));
    const maxDepth = 8;
    const maxNodes = 5000;
    let visited = 0;

    const ownKeys = (value) => {
      try {
        return Reflect.ownKeys(value).map(String);
      } catch (error) {
        return [`<ownKeys error: ${error?.message || error}>`];
      }
    };
    const protoKeys = (value) => {
      try {
        return Reflect.ownKeys(Object.getPrototypeOf(value) || {}).map(String);
      } catch (error) {
        return [`<protoKeys error: ${error?.message || error}>`];
      }
    };
    const read = (value, key) => {
      try {
        return value?.[key];
      } catch {
        return undefined;
      }
    };
    const candidateActionContainers = (value) => [
      ["innerInitiatedActions", read(value, "innerInitiatedActions")],
      ["action", read(value, "action")],
      ["actions", read(value, "actions")],
      ["_actions", read(value, "_actions")],
      ["_controller.innerInitiatedActions", read(read(value, "_controller"), "innerInitiatedActions")],
      ["_controller.action", read(read(value, "_controller"), "action")],
      ["_implementation.innerInitiatedActions", read(read(value, "_implementation"), "innerInitiatedActions")],
      ["_implementation.action", read(read(value, "_implementation"), "action")],
    ];

    while (queue.length && visited < maxNodes) {
      const { value, depth, path } = queue.shift();
      if (!value || (typeof value !== "object" && typeof value !== "function")) continue;
      if (seen.has(value)) continue;
      seen.add(value);
      visited += 1;

      const keys = ownKeys(value);
      const pKeys = protoKeys(value);
      const interestingKeys = keys
        .concat(pKeys)
        .filter((key) => /controller|action|dispatch|state|element|frame|implementation/i.test(key));
      if (interestingKeys.length || reports.length < 80) {
        reports.push({
          path,
          depth,
          ctor: value?.constructor?.name || null,
          keys: keys.slice(0, 80),
          protoKeys: pKeys.slice(0, 80),
          interestingKeys: interestingKeys.slice(0, 120),
        });
      }

      for (const [containerPath, actions] of candidateActionContainers(value)) {
        const names = actions && (typeof actions === "object" || typeof actions === "function")
          ? Reflect.ownKeys(actions).map(String)
          : [];
        if (names.some((name) => /elementsDispatch/i.test(name))) {
          const controller = containerPath.startsWith("_controller.")
            ? read(value, "_controller")
            : containerPath.startsWith("_implementation.")
              ? read(value, "_implementation")
              : value;
          const getStateName = names.find((name) => /getElementsState/i.test(name)) || null;
          try {
            window[StateKey].availableControllerActions = {
              path,
              depth,
              containerPath,
              hasGetElementsState: Boolean(getStateName),
              hasElementsDispatch: true,
              actionNames: names,
              relevantActionNames: names.filter((name) =>
                /elements|dispatch|state|session|paymentmethod|confirm|validate|store/i.test(name),
              ),
            };
          } catch {}
          console.log("[oaics-default-mount] Stripe controller found", {
            path,
            depth,
            containerPath,
            hasGetElementsState: Boolean(getStateName),
            actionNames: names,
          });
          return controller;
        }
      }

      if (depth >= maxDepth) continue;
      for (const key of keys) {
        if (key === "window" || key === "document" || key === "parent" || key === "top") {
          continue;
        }
        const child = read(value, key);
        if (child && (typeof child === "object" || typeof child === "function")) {
          queue.push({ value: child, depth: depth + 1, path: `${path}.${key}` });
        }
      }
    }

    try {
      window[StateKey].controllerSearchReport = {
        visited,
        maxDepth,
        maxNodes,
        roots: roots.map((root, index) => ({
          index,
          ctor: root?.constructor?.name || null,
          keys: root ? ownKeys(root).slice(0, 120) : null,
          protoKeys: root ? protoKeys(root).slice(0, 120) : null,
        })),
        candidates: reports.slice(0, 160),
      };
      console.warn(
        "[oaics-default-mount] Stripe controller search report",
        window[StateKey].controllerSearchReport,
      );
    } catch {}

    throw new Error(
      "Stripe controller actions were not exposed after Stripe Element creation. Read window.__oaicsDefaultPaymentMethodMount.controllerSearchReport for candidate paths.",
    );
  }

  function buildElementsSessionUrl(source, identifiers, runtime = {}) {
    const url = new URL("https://api.stripe.com/v1/elements/sessions");
    const params = url.searchParams;
    const set = (name, value) => {
      if (value !== undefined && value !== null && value !== "") {
        params.set(name, String(value));
      }
    };

    set("key", source.publishableKey);
    set("type", "deferred_intent");
    set("customer_session_client_secret", source.customerSessionClientSecret);
    set("deferred_intent[mode]", source.mode);
    set("deferred_intent[amount]", source.amount);
    set("deferred_intent[currency]", source.currency);
    set("deferred_intent[setup_future_usage]", source.setupFutureUsage);
    source.paymentMethodTypes.forEach((type, index) => {
      set(`deferred_intent[payment_method_types][${index}]`, type);
    });
    set("currency", source.currency);
    StripeBetas.forEach((beta, index) => set(`client_betas[${index}]`, beta));
    set("elements_init_source", "custom_checkout");
    set("referrer_host", runtime.referrerHost);
    set("stripe_js_id", runtime.stripeJsId);
    set("locale", runtime.locale);
    set("checkout_session_id", identifiers.checkoutSessionId);
    set("_stripe_version", runtime.apiVersion);
    set("_stripe_account", runtime.stripeAccount);
    return url;
  }

  function redactedStripeUrl(url) {
    const redacted = new URL(url.toString());
    ["key", "customer_session_client_secret"].forEach((name) => {
      if (redacted.searchParams.has(name)) redacted.searchParams.set(name, "***");
    });
    return redacted.toString();
  }

  function nativeCustomerAuthorization(payload) {
    const body = payload?.object || payload;
    const customer = body?.customer;
    const customerSession =
      customer?.customer_session || customer?.customerSession;
    const ephemeralKey =
      customerSession?.api_key || customerSession?.apiKey || "";
    const customerId =
      customerSession?.customer || customer?.id || "";
    const defaultPaymentMethodId =
      customer?.default_payment_method || customer?.defaultPaymentMethod || null;

    if (!/^ek_(?:live|test)_/.test(ephemeralKey)) {
      throw new Error(
        "Stripe elements/sessions returned no native customer.customer_session.api_key.",
      );
    }
    if (!/^cus_/.test(customerId)) {
      throw new Error(
        "Stripe elements/sessions returned no native customer ID.",
      );
    }
    return {
      customer,
      customerSession,
      customerId,
      ephemeralKey,
      defaultPaymentMethodId,
    };
  }

  function stripeEphemeralHeaders(
    ephemeralKey,
    runtime = {},
    includeStripeVersion = true,
  ) {
    return {
      Accept: "application/json",
      Authorization: `Bearer ${ephemeralKey}`,
      ...(includeStripeVersion
        ? { "Stripe-Version": runtime.apiVersion || "2020-08-27" }
        : {}),
    };
  }

  async function fetchNativeCardPaymentMethods(
    authorization,
    runtime,
    paymentMethodId,
  ) {
    const state = window[StateKey];
    const url = new URL("https://api.stripe.com/v1/payment_methods");
    url.searchParams.set("customer", authorization.customerId);
    url.searchParams.set("type", "card");
    url.searchParams.set("limit", "100");
    url.searchParams.set(
      "_stripe_version",
      runtime.apiVersion || "2020-08-27",
    );
    if (runtime.stripeAccount) {
      url.searchParams.set("_stripe_account", runtime.stripeAccount);
    }

    const response = await fetch(url, {
      method: "GET",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: stripeEphemeralHeaders(authorization.ephemeralKey, {}, false),
    });
    const body = await readJsonOrText(response);
    const paymentMethods = Array.isArray(body?.data)
      ? body.data
      : Array.isArray(body?.object?.data)
        ? body.object.data
        : [];
    const paymentMethod = paymentMethods.find(
      (method) => method?.id === paymentMethodId,
    );
    const paymentMethodCustomer =
      typeof paymentMethod?.customer === "string"
        ? paymentMethod.customer
        : paymentMethod?.customer?.id || "";

    state.nativePaymentMethodsFetch = {
      at: new Date().toISOString(),
      url: `${url.origin}${url.pathname}?customer=***&type=card&limit=100`,
      status: response.status,
      ok: response.ok,
      requestId: response.headers.get("request-id"),
      authorization: "Bearer ek_*",
      paymentMethodIds: paymentMethods.map((method) => method?.id).filter(Boolean),
    };
    if (!response.ok) {
      const code = body?.error?.code || body?.code || "unknown_error";
      throw new Error(
        `Stripe payment_methods list failed (${response.status}, code=${code}).`,
      );
    }
    if (!paymentMethod) {
      throw new Error(
        `Stripe payment_methods list did not return the default PaymentMethod ${paymentMethodId}.`,
      );
    }
    if (paymentMethodCustomer !== authorization.customerId) {
      throw new Error(
        `Stripe payment_methods list returned ${paymentMethodId} without matching customer ownership.`,
      );
    }

    return { paymentMethods, paymentMethod };
  }

  async function fetchNativeCustomerAuthorization(
    source,
    identifiers,
    runtime,
    paymentMethodId,
  ) {
    const state = window[StateKey];
    const url = buildElementsSessionUrl(source, identifiers, runtime);
    state.phase = "fetching_native_customer_session";
    setStatus("Verifying the native Stripe Customer Session...");

    const response = await fetch(url, {
      method: "GET",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    const body = await readJsonOrText(response);
    state.elementsSessionFetch = {
      at: new Date().toISOString(),
      url: redactedStripeUrl(url),
      status: response.status,
      ok: response.ok,
      requestId: response.headers.get("request-id"),
      bodyKeys:
        body && typeof body === "object"
          ? Reflect.ownKeys(body).map(String).slice(0, 80)
          : null,
    };
    if (!response.ok) {
      const code = body?.error?.code || body?.code || "unknown_error";
      throw new Error(
        `Stripe elements/sessions failed (${response.status}, code=${code}).`,
      );
    }

    const authorization = nativeCustomerAuthorization(body);
    const nativePaymentMethods = await fetchNativeCardPaymentMethods(
      authorization,
      runtime,
      paymentMethodId,
    );
    authorization.paymentMethods = nativePaymentMethods.paymentMethods;
    authorization.paymentMethod = nativePaymentMethods.paymentMethod;
    state.customerAuthorization = {
      customerId: authorization.customerId,
      hasEphemeralKey: true,
      source: "elements_sessions_plus_payment_methods_list",
    };
    state.nativeCustomerProof = {
      customerId: authorization.customerId,
      hasEphemeralKey: true,
      paymentMethodId,
      paymentMethodHasMatchingCustomer: true,
      defaultPaymentMethodId: authorization.defaultPaymentMethodId,
    };
    return authorization;
  }

  async function createSavedPaymentMethodConfirmationToken(
    source,
    runtime,
    authorization,
    paymentMethodId,
  ) {
    const state = window[StateKey];
    const url = new URL("https://api.stripe.com/v1/confirmation_tokens");
    const body = new URLSearchParams();
    body.set("payment_method", paymentMethodId);
    body.set("setup_future_usage", source.setupFutureUsage);
    body.set("key", source.publishableKey);
    if (runtime.stripeAccount) {
      body.set("_stripe_account", runtime.stripeAccount);
    }

    const response = await fetch(url, {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: {
        ...stripeEphemeralHeaders(authorization.ephemeralKey, runtime),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
    const result = await readJsonOrText(response);
    state.confirmationTokenRequest = {
      at: new Date().toISOString(),
      url: url.toString(),
      status: response.status,
      ok: response.ok,
      requestId: response.headers.get("request-id"),
      authorization: "Bearer ek_*",
      paymentMethodId,
      bodyFields: [...body.keys()],
    };
    if (!response.ok) {
      const code = result?.error?.code || result?.code || "unknown_error";
      const message = result?.error?.message || result?.message || "unknown error";
      throw new Error(
        `Stripe confirmation_tokens failed (${response.status}, code=${code}): ${message}`,
      );
    }
    if (!result?.id?.startsWith("ctoken_")) {
      throw new Error("Stripe confirmation_tokens returned no ctoken_* ID.");
    }
    return { confirmationToken: result };
  }

  async function selectedSavedPaymentMethod(
    controller,
    stripe,
    elements,
    expectedPaymentMethodId,
  ) {
    const groupId = elements?._id;
    if (!groupId) throw new Error("Stripe Elements group ID is unavailable.");
    const getElementConfirmingPayment = controllerAction(
      controller,
      /^getElementConfirmingPayment$/,
      "getElementConfirmingPayment",
    );
    const getPaymentMethodDataFromElements = controllerAction(
      controller,
      /^getPaymentMethodDataFromElements$/,
      "getPaymentMethodDataFromElements",
    );
    const elementConfirming = await getElementConfirmingPayment({
      groupId,
      slug: "get_payment_method_data",
    });
    const mids =
      typeof stripe?._mids === "function"
        ? stripe._mids()
        : typeof controller?.mids === "function"
          ? controller.mids()
          : null;
    const result = await getPaymentMethodDataFromElements({
      groupId,
      elements: Array.isArray(elements?._elements) ? elements._elements : [],
      paymentMethodData: {},
      mids,
      elementConfirming,
    });
    const selection = result?.object || result;
    if (selection?.type === "error") {
      throw new Error(
        selection.error?.message || "Stripe could not read the selected PaymentMethod.",
      );
    }
    if (
      selection?.type !== "saved_payment_method" ||
      selection.paymentMethodId !== expectedPaymentMethodId
    ) {
      throw new Error(
        `Selected Stripe PaymentMethod is ${selection?.paymentMethodId || selection?.type || "unknown"}; expected ${expectedPaymentMethodId}.`,
      );
    }
    return {
      type: selection.type,
      paymentMethodId: selection.paymentMethodId,
      selectedPaymentMethod: selection.selectedPaymentMethod || null,
    };
  }

  function paymentElementIdentity(paymentElement) {
    const implementation = paymentElement?._implementation;
    const frameId = implementation?._frame?.id || paymentElement?._frame?.id;
    const elementId =
      paymentElement?._elementId || implementation?._elementId || null;
    if (!frameId) {
      throw new Error("Stripe Payment Element frame ID is unavailable.");
    }
    return { frameId, elementId };
  }

  async function readElementsState(controller, paymentElement) {
    const identity = paymentElementIdentity(paymentElement);
    const actions = controller?.innerInitiatedActions || controller?.action || controller?._controller?.action;
    const actionNames = actions && (typeof actions === "object" || typeof actions === "function")
      ? Reflect.ownKeys(actions).map(String)
      : [];
    const getElementsStateName = actionNames.find((name) => /getElementsState/i.test(name));
    if (!getElementsStateName || typeof actions[getElementsStateName] !== "function") {
      try {
        window[StateKey].availableControllerActions = {
          ...(window[StateKey].availableControllerActions || {}),
          hasGetElementsState: false,
          hasElementsDispatch: actionNames.some((name) => /elementsDispatch/i.test(name)),
          relevantActionNames: actionNames.filter((name) =>
            /elements|dispatch|state|session|paymentmethod|confirm|validate|store/i.test(name),
          ),
        };
      } catch {}
      const captured = window[StateKey].__capturedCustomerAuthorization;
      if (captured?.ephemeralKey && captured?.customerId) {
        const saved = window[StateKey].defaultPaymentMethod;
        const customerSession = {
          ...(captured.customerSession || {}),
          apiKey: captured.ephemeralKey,
          customer: captured.customerId,
        };
        return {
          identity,
          currentState: {
            config: {
              session: {
                customer: {
                  ...(captured.customer || {}),
                  id: captured.customerId,
                  customerSession,
                  paymentMethods: saved ? [saved] : [],
                },
              },
            },
          },
          synthesizedFromCapturedAuthorization: true,
        };
      }
      throw new Error(
        "Stopped before /v1/confirmation_tokens: Stripe basil controller exposes elementsDispatch but no getElementsState/ek_* authorization proof. Continuing would fall back to pk_live_* and reproduce Stripe 403. Read window.__oaicsDefaultPaymentMethodMount.stripeMessageCaptures and availableControllerActions.",
      );
    }
    const response = await actions[getElementsStateName].bind(actions)(identity);
    const currentState = response?.currentState || response?.object?.currentState;
    if (!currentState?.config?.session) {
      throw new Error("Stripe GET_ELEMENTS_STATE returned no session state.");
    }
    return { identity, currentState };
  }

  function realCustomerAuthorization(currentState) {
    const customer = currentState?.config?.session?.customer;
    const customerSession = customer?.customerSession;
    const ephemeralKey = customerSession?.apiKey;
    const customerId = customer?.id || customerSession?.customer;
    if (!/^ek_(?:live|test)_/.test(ephemeralKey || "")) {
      throw new Error("Stripe Customer Session state has no ek_* API key.");
    }
    if (!/^cus_/.test(customerId || "")) {
      throw new Error("Stripe Customer Session state has no cus_* customer ID.");
    }
    return { customer, customerSession, ephemeralKey, customerId };
  }

  function findCustomerAuthorization(value, seen = new WeakSet(), path = "root") {
    if (!value || (typeof value !== "object" && typeof value !== "function")) return null;
    if (seen.has(value)) return null;
    seen.add(value);
    const customerSession = value.customerSession || value.customer_session || null;
    const ephemeralKey =
      customerSession?.apiKey ||
      customerSession?.api_key ||
      value.apiKey ||
      value.api_key ||
      value.ephemeralKey ||
      value.ephemeral_key ||
      null;
    const rawCustomer = customerSession?.customer || value.customer || null;
    const customerId =
      value.id && /^cus_/.test(value.id) ? value.id :
      typeof rawCustomer === "string" && /^cus_/.test(rawCustomer) ? rawCustomer :
      rawCustomer?.id && /^cus_/.test(rawCustomer.id) ? rawCustomer.id :
      customerSession?.customerId && /^cus_/.test(customerSession.customerId) ? customerSession.customerId :
      value.customerId && /^cus_/.test(value.customerId) ? value.customerId :
      null;
    if (/^ek_(?:live|test)_/.test(ephemeralKey || "") && /^cus_/.test(customerId || "")) {
      const customer = value.paymentMethods || value.payment_methods || value.customerSession
        ? value
        : { id: customerId, customerSession };
      return { customer, customerSession, ephemeralKey, customerId, path };
    }
    let keys = [];
    try {
      keys = Reflect.ownKeys(value);
    } catch {
      return null;
    }
    for (const key of keys) {
      const keyText = String(key);
      if (keyText === "window" || keyText === "document" || keyText === "parent" || keyText === "top") {
        continue;
      }
      let child;
      try {
        child = value[key];
      } catch {
        continue;
      }
      const found = findCustomerAuthorization(child, seen, `${path}.${keyText}`);
      if (found) return found;
    }
    return null;
  }

  function mergeAuthorizationIntoElementsSessionPayload(payload, authorization, paymentMethod) {
    if (!payload || !authorization?.ephemeralKey || !authorization?.customerId) return payload;
    const patchedRoots = [];
    const seen = new WeakSet();
    const patchCustomer = (customer, path) => {
      if (!customer || typeof customer !== "object") return false;
      const existingMethods = Array.isArray(customer.paymentMethods)
        ? customer.paymentMethods
        : Array.isArray(customer.payment_methods)
          ? customer.payment_methods
          : [];
      const mergedMethods = paymentMethod
        ? [
            {
              ...paymentMethod,
              customer: authorization.customerId,
              customerSession: {
                ...(authorization.customerSession || {}),
                ...(paymentMethod.customerSession || {}),
                apiKey: authorization.ephemeralKey,
                customer: authorization.customerId,
              },
            },
            ...existingMethods.filter((method) => method?.id !== paymentMethod.id),
          ]
        : existingMethods;
      customer.id = authorization.customerId;
      customer.customerSession = {
        ...(authorization.customerSession || {}),
        ...(customer.customerSession || {}),
        apiKey: authorization.ephemeralKey,
        customer: authorization.customerId,
      };
      customer.paymentMethods = mergedMethods;
      customer.payment_methods = mergedMethods;
      patchedRoots.push(path);
      return true;
    };
    const walk = (value, path = "root") => {
      if (!value || (typeof value !== "object" && typeof value !== "function")) return;
      if (seen.has(value)) return;
      seen.add(value);
      if (value.customer && typeof value.customer === "object") {
        patchCustomer(value.customer, `${path}.customer`);
      }
      if (value.config?.session?.customer) {
        patchCustomer(value.config.session.customer, `${path}.config.session.customer`);
      }
      if (value.session?.customer) {
        patchCustomer(value.session.customer, `${path}.session.customer`);
      }
      if (value.object?.config?.session?.customer) {
        patchCustomer(value.object.config.session.customer, `${path}.object.config.session.customer`);
      }
      let keys = [];
      try {
        keys = Reflect.ownKeys(value);
      } catch {
        return;
      }
      for (const key of keys) {
        const keyText = String(key);
        if (keyText === "window" || keyText === "document" || keyText === "parent" || keyText === "top") continue;
        let child;
        try {
          child = value[key];
        } catch {
          continue;
        }
        walk(child, `${path}.${keyText}`);
      }
    };
    walk(payload);
    try {
      window[StateKey].sessionMergeReport = {
        at: new Date().toISOString(),
        patchedRoots,
        customerId: authorization.customerId,
        hasEphemeralKey: true,
        paymentMethodId: paymentMethod?.id || null,
      };
      console.log("[oaics-default-mount] merged real Customer Session authorization", window[StateKey].sessionMergeReport);
    } catch {}
    return payload;
  }

  function installControllerMessageCapture(controller, label) {
    const state = window[StateKey];
    if (!controller || !state) return;

    state.stripeMessageCaptures = state.stripeMessageCaptures || [];
    state.__controllerActionRequests = state.__controllerActionRequests || {};
    state.controllerCaptureInstallations = state.controllerCaptureInstallations || [];
    state.controllerCaptureInstallations.push({
      at: new Date().toISOString(),
      label,
      hasRequestsResolve: typeof controller?._requests?.resolve === "function",
      hasControllerFrameSend: typeof controller?._controllerFrame?.send === "function",
    });
    state.controllerCaptureInstallations = state.controllerCaptureInstallations.slice(-20);

    const redactedJson = (payload) => {
      try {
        return JSON.stringify(payload, (key, value) =>
          typeof value === "string"
            ? value.replace(
                /(pk_(?:live|test)_|ek_(?:live|test)_|cuss_secret_|cs_(?:live|test)_|pi_|seti_|ctoken_)[A-Za-z0-9_-]+/g,
                "$1***",
              )
            : value,
        ).slice(0, 12000);
      } catch {
        return String(payload);
      }
    };

    const saveAuthorization = (authorization, source) => {
      if (!authorization?.ephemeralKey || !authorization?.customerId) return;
      state.customerAuthorization = {
        customerId: authorization.customerId,
        hasEphemeralKey: true,
        source: `${label}:${source}`,
        path: authorization.path,
      };
      state.__capturedCustomerAuthorization = authorization;
      state.__realCustomerAuthorization = authorization;
    };

    const setupStoreSavedMethods = (request) => {
      const paymentMethods = request?.req?.savedPaymentMethods?.paymentMethods;
      return Array.isArray(paymentMethods) ? paymentMethods : [];
    };

    const capture = (source, payload, extra = {}) => {
      const authorization = findCustomerAuthorization(payload);
      const text = redactedJson(payload);
      const interesting =
        extra.force === true ||
        Boolean(authorization) ||
        /ek_live_|ek_test_|customerSession|customer_session|elements_state|get_elements_state|setupStoreForElementsGroup|setup_store/i.test(
          `${source}\n${text}`,
        );
      if (interesting) {
        const record = {
          at: new Date().toISOString(),
          label,
          source,
          actionName: extra.actionName || null,
          nonce: extra.nonce || null,
          requestHasSavedPaymentMethods: extra.requestHasSavedPaymentMethods === true,
          requestPaymentMethodIds: extra.requestPaymentMethodIds || [],
          bodyKeys:
            payload && typeof payload === "object"
              ? Reflect.ownKeys(payload).map(String).slice(0, 80)
              : null,
          hasEkText: /ek_(?:live|test)_/.test(text),
          hasAuthorization: Boolean(authorization),
          authorizationPath: authorization?.path || null,
          customerId: authorization?.customerId || null,
          hasEphemeralKey: Boolean(authorization?.ephemeralKey),
          preview: text,
        };
        state.stripeMessageCaptures.push(record);
        state.stripeMessageCaptures = state.stripeMessageCaptures.slice(-120);
        console.log("[oaics-default-mount] captured Stripe message", record);
      }
      if (authorization) saveAuthorization(authorization, source);
      return authorization;
    };

    const actions = controller.innerInitiatedActions || controller.action;
    if (actions && actions.__oaicsActionCaptureInstalledFor !== state.installedAt) {
      actions.__oaicsActionCaptureInstalledFor = state.installedAt;
      [
        "setupStoreForElementsGroup",
        "updateElementsOptions",
        "validateElements",
        "createConfirmationTokenWithElements",
        "getPaymentMethodDataFromElements",
      ].forEach((name) => {
        const original = actions[name];
        if (typeof original !== "function") return;
        actions[name] = function patchedControllerAction(arg) {
          const requestSavedMethods = setupStoreSavedMethods(arg);
          capture(`action.${name}:request`, arg, {
            force: name === "setupStoreForElementsGroup",
            actionName: name,
            requestHasSavedPaymentMethods: requestSavedMethods.length > 0,
            requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
          });
          const result = original.apply(this, arguments);
          if (result && typeof result.then === "function") {
            return result.then(
              (value) => {
                capture(`action.${name}:response`, value, {
                  force: name === "setupStoreForElementsGroup",
                  actionName: name,
                  requestHasSavedPaymentMethods: requestSavedMethods.length > 0,
                  requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
                });
                const foundAuthorization = findCustomerAuthorization(value);
                if (foundAuthorization) saveAuthorization(foundAuthorization, `action.${name}:response`);
                const realAuthorization = state.__realCustomerAuthorization || state.__capturedCustomerAuthorization;
                if (name === "setupStoreForElementsGroup" && requestSavedMethods.length && realAuthorization?.ephemeralKey) {
                  return mergeAuthorizationIntoElementsSessionPayload(
                    value,
                    realAuthorization,
                    requestSavedMethods[0],
                  );
                }
                return value;
              },
              (error) => {
                capture(`action.${name}:rejection`, error, {
                  force: name === "setupStoreForElementsGroup",
                  actionName: name,
                  requestHasSavedPaymentMethods: requestSavedMethods.length > 0,
                  requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
                });
                throw error;
              },
            );
          }
          capture(`action.${name}:return`, result, {
            force: name === "setupStoreForElementsGroup",
            actionName: name,
            requestHasSavedPaymentMethods: requestSavedMethods.length > 0,
            requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
          });
          if (name === "setupStoreForElementsGroup") {
            const foundAuthorization = findCustomerAuthorization(result);
            if (foundAuthorization) saveAuthorization(foundAuthorization, `action.${name}:return`);
            const realAuthorization = state.__realCustomerAuthorization || state.__capturedCustomerAuthorization;
            if (requestSavedMethods.length && realAuthorization?.ephemeralKey) {
              return mergeAuthorizationIntoElementsSessionPayload(result, realAuthorization, requestSavedMethods[0]);
            }
          }
          return result;
        };
      });
    }

    const frame = controller._controllerFrame;
    if (frame && frame.__oaicsSendCaptureInstalledFor !== state.installedAt) {
      frame.__oaicsSendCaptureInstalledFor = state.installedAt;
      const originalSend = frame.send;
      if (typeof originalSend === "function") {
        frame.send = function patchedFrameSend(message) {
          if (
            message?.action === "stripe-controller-action-request" &&
            message?.payload?.nonce
          ) {
            const requestSavedMethods = setupStoreSavedMethods(message.payload.request);
            state.__controllerActionRequests[message.payload.nonce] = {
              at: new Date().toISOString(),
              label,
              actionName: message.payload.actionName,
              request: message.payload.request,
              requestHasSavedPaymentMethods: requestSavedMethods.length > 0,
              requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
            };
          }
          capture("_controllerFrame.send", message, {
            force: message?.action === "stripe-controller-action-request" && message?.payload?.actionName === "setupStoreForElementsGroup",
            actionName: message?.payload?.actionName || null,
            nonce: message?.payload?.nonce || null,
          });
          return originalSend.apply(this, arguments);
        };
      }
      const originalOn = frame._on;
      if (typeof originalOn === "function") {
        frame._on = function patchedFrameOn(eventName, handler) {
          return originalOn.call(this, eventName, function patchedFrameHandler(payload) {
            capture(`_controllerFrame._on:${eventName}`, payload);
            return handler.apply(this, arguments);
          });
        };
      }
    }

    const requests = controller._requests;
    if (requests && requests.__oaicsResolveCaptureInstalledFor !== state.installedAt) {
      requests.__oaicsResolveCaptureInstalledFor = state.installedAt;
      const originalResolve = requests.resolve;
      if (typeof originalResolve === "function") {
        requests.resolve = function patchedRequestsResolve(nonce, response) {
          const meta = state.__controllerActionRequests?.[nonce] || null;
          const requestSavedMethods = setupStoreSavedMethods(meta?.request);
          const foundAuthorization = capture(
            `_requests.resolve:${meta?.actionName || "unknown"}`,
            response,
            {
              force: meta?.actionName === "setupStoreForElementsGroup",
              actionName: meta?.actionName || null,
              nonce,
              requestHasSavedPaymentMethods: requestSavedMethods.length > 0,
              requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
            },
          );
          if (foundAuthorization) {
            saveAuthorization(foundAuthorization, `_requests.resolve:${meta?.actionName || "unknown"}`);
          }

          let patchedResponse = response;
          const realAuthorization = state.__realCustomerAuthorization || state.__capturedCustomerAuthorization;
          if (
            meta?.actionName === "setupStoreForElementsGroup" &&
            requestSavedMethods.length &&
            realAuthorization?.ephemeralKey
          ) {
            patchedResponse = mergeAuthorizationIntoElementsSessionPayload(
              response,
              realAuthorization,
              requestSavedMethods[0],
            );
            const mergedAuthorization = findCustomerAuthorization(patchedResponse);
            state.savedPaymentMethodAuthorizationProof = {
              at: new Date().toISOString(),
              source: `_requests.resolve:${meta.actionName}`,
              nonce,
              customerId: realAuthorization.customerId,
              hasEphemeralKey: true,
              paymentMethodId: requestSavedMethods[0]?.id || null,
              responseHasAuthorizationAfterMerge: Boolean(mergedAuthorization?.ephemeralKey),
              responseAuthorizationPath: mergedAuthorization?.path || null,
              patchedRoots: state.sessionMergeReport?.patchedRoots || [],
            };
            capture("_requests.resolve:patched_setupStoreForElementsGroup", patchedResponse, {
              force: true,
              actionName: meta.actionName,
              nonce,
              requestHasSavedPaymentMethods: true,
              requestPaymentMethodIds: requestSavedMethods.map((method) => method?.id).filter(Boolean),
            });
          }

          return originalResolve.call(this, nonce, patchedResponse);
        };
      }
      const originalReject = requests.reject;
      if (typeof originalReject === "function") {
        requests.reject = function patchedRequestsReject(nonce, error) {
          const meta = state.__controllerActionRequests?.[nonce] || null;
          capture(`_requests.reject:${meta?.actionName || "unknown"}`, error, {
            force: meta?.actionName === "setupStoreForElementsGroup",
            actionName: meta?.actionName || null,
            nonce,
          });
          return originalReject.call(this, nonce, error);
        };
      }
    }

    const originalHandleMessage = controller._handleMessage;
    if (
      typeof originalHandleMessage === "function" &&
      controller.__oaicsHandleMessageCaptureInstalledFor !== state.installedAt
    ) {
      controller.__oaicsHandleMessageCaptureInstalledFor = state.installedAt;
      controller._handleMessage = function patchedHandleMessage(event) {
        capture("_handleMessage:event.data", event?.data);
        return originalHandleMessage.apply(this, arguments);
      };
    }
  }

  async function patchSavedMethodAuthorization(
    controller,
    paymentElement,
    authorization,
    paymentMethodId,
  ) {
    const { identity, currentState } = await readElementsState(
      controller,
      paymentElement,
    );
    const session = currentState.config.session;
    const syntheticCustomer = session.customer;
    const syntheticCustomerSession = syntheticCustomer?.customerSession;
    const paymentMethods = Array.isArray(syntheticCustomer?.paymentMethods)
      ? syntheticCustomer.paymentMethods
      : [];
    if (!paymentMethods.some((method) => method?.id === paymentMethodId)) {
      throw new Error(
        `Injected PaymentMethod ${paymentMethodId} is absent from Stripe state.`,
      );
    }

    const patchedCustomerSession = {
      ...authorization.customerSession,
      ...syntheticCustomerSession,
      apiKey: authorization.ephemeralKey,
      customer: authorization.customerId,
      components:
        syntheticCustomerSession?.components ||
        authorization.customerSession?.components,
    };
    const patchedSession = {
      ...session,
      customer: {
        ...authorization.customer,
        ...syntheticCustomer,
        id: authorization.customerId,
        paymentMethods,
        customerSession: patchedCustomerSession,
      },
    };
    const patchedState = {
      ...currentState,
      config: {
        ...currentState.config,
        session: patchedSession,
      },
    };
    const dispatchElements = controllerAction(
      controller,
      /elementsDispatch/i,
      "ELEMENTS_DISPATCH",
    );
    await dispatchElements({
      frameId: identity.frameId,
      action: {
        type: "CONFIG.ASYNC_UPDATE_RECEIVED",
        config: { session: patchedSession },
        prevSession: session,
        consumerSession: currentState.consumer?.consumerSession,
        elementsState: patchedState,
        isLinkPassthroughAlreadyEnabled: false,
      },
    });

    const verified = await readElementsState(controller, paymentElement);
    const verifiedCustomer = verified.currentState.config.session.customer;
    const verifiedKey = verifiedCustomer?.customerSession?.apiKey;
    const verifiedMethods = Array.isArray(verifiedCustomer?.paymentMethods)
      ? verifiedCustomer.paymentMethods
      : [];
    if (
      verifiedKey !== authorization.ephemeralKey ||
      !verifiedMethods.some((method) => method?.id === paymentMethodId)
    ) {
      throw new Error("Stripe saved-PaymentMethod authorization patch did not persist.");
    }
    return verified;
  }

  function hiddenBootstrapHost() {
    const host = document.createElement("div");
    host.style.cssText = [
      "position:fixed",
      "left:-4px",
      "top:-4px",
      "width:2px",
      "height:2px",
      "overflow:hidden",
      "opacity:.001",
      "pointer-events:none",
    ].join(";");
    (document.body || document.documentElement).appendChild(host);
    return host;
  }

  function waitForPaymentElementReady(paymentElement, label) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`${label} did not become ready within 20 seconds.`)),
        20000,
      );
      paymentElement.on("ready", () => {
        clearTimeout(timer);
        resolve({ status: "ready" });
      });
      paymentElement.on("loaderror", (event) => {
        clearTimeout(timer);
        reject(
          new Error(
            event?.error?.message || `${label} emitted a Stripe loaderror.`,
          ),
        );
      });
    });
  }

  function waitForBootstrapPaymentElement(paymentElement, label) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`${label} did not expose a Stripe controller within 20 seconds.`)),
        20000,
      );
      paymentElement.on("ready", () => {
        clearTimeout(timer);
        resolve({ status: "ready" });
      });
      paymentElement.on("loaderror", (event) => {
        clearTimeout(timer);
        resolve({
          status: "loaderror",
          message: event?.error?.message || `${label} emitted a Stripe loaderror.`,
        });
      });
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
        Waiting for payment form
      </button>
    `;
    (document.body || document.documentElement).appendChild(host);
    return {
      host,
      method: host.querySelector('[data-role="method"]'),
      status: host.querySelector('[data-role="status"]'),
      element: host.querySelector('[data-role="element"]'),
      close: host.querySelector('[data-action="close"]'),
      submit: host.querySelector('[data-action="submit"]'),
    };
  }

  const identifiers = checkoutIdentifiers();
  const panel = createPanel();
  const state = {
    phase: "loading",
    installedAt: new Date().toISOString(),
    identifiers,
    accountId: null,
    defaultPaymentMethodId: null,
    defaultPaymentMethod: null,
    checkoutSession: null,
    stripeSource: null,
    stripe: null,
    stripeController: null,
    bootstrapElements: null,
    bootstrapPaymentElement: null,
    bootstrapHost: null,
    customerAuthorization: null,
    elements: null,
    paymentElement: null,
    elementsSubmitResult: null,
    confirmationToken: null,
    checkoutConfirmResponses: [],
    stripeConfirmResult: null,
    events: [],
    lastError: null,
    status() {
      return {
        phase: this.phase,
        identifiers: this.identifiers,
        accountId: this.accountId,
        defaultPaymentMethodId: this.defaultPaymentMethodId,
        defaultPaymentMethod: this.defaultPaymentMethod,
        stripeSource: this.stripeSource
          ? {
              amount: this.stripeSource.amount,
              currency: this.stripeSource.currency,
              mode: this.stripeSource.mode,
              paymentMethodTypes: this.stripeSource.paymentMethodTypes,
              hasCustomerSessionClientSecret: true,
              hasPublishableKey: true,
            }
          : null,
        customerAuthorization: this.customerAuthorization,
        elementsSessionFetch: this.elementsSessionFetch || null,
        nativeCustomerProof: this.nativeCustomerProof || null,
        initialSelectionProof: this.initialSelectionProof || null,
        selectedPaymentMethodProof: this.selectedPaymentMethodProof || null,
        eventCount: this.events.length,
        lastEvent: this.events.at(-1) || null,
        checkoutConfirmCount: this.checkoutConfirmResponses.length,
        checkoutConfirmResponse: this.checkoutConfirmResponses.at(-1) || null,
        stripeConfirmResult: this.stripeConfirmResult,
        lastError: this.lastError,
      };
    },
    async submitElements() {
      if (!this.elements?.submit) throw new Error("Elements is not ready.");
      const result = await this.elements.submit();
      console.log("[oaics-default-mount] elements.submit result", result);
      return result;
    },
    submitCheckout() {
      throw new Error("Checkout submission is not ready.");
    },
    destroy() {
      try {
        this.paymentElement?.destroy?.();
      } catch {}
      try {
        this.bootstrapPaymentElement?.destroy?.();
      } catch {}
      this.bootstrapHost?.remove?.();
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

    setStatus("Reading current Checkout and account state...");
    const checkoutSession = await readCurrentCheckoutSession(identifiers);
    const source = stripeSourceFromCheckoutSession(checkoutSession);
    state.checkoutSession = checkoutSession;
    state.stripeSource = source;

    const sessionResponse = await fetch("/api/auth/session", {
      credentials: "include",
      cache: "no-store",
    });
    const session = await readJsonOrText(sessionResponse);
    if (!sessionResponse.ok || !session?.accessToken) {
      throw new Error(`Session read failed (${sessionResponse.status}).`);
    }

    let accountId = findPersonalAccountId(session, null);
    if (!accountId) {
      const accountsResponse = await fetch(
        "/backend-api/accounts/check/v4-2023-04-27",
        {
          credentials: "include",
          cache: "no-store",
          headers: { Authorization: `Bearer ${session.accessToken}` },
        },
      );
      const accountsData = await readJsonOrText(accountsResponse);
      if (!accountsResponse.ok) {
        throw new Error(`accounts/check failed (${accountsResponse.status}).`);
      }
      accountId = findPersonalAccountId(session, accountsData);
    }
    if (!accountId) throw new Error("No personal account_id was found.");
    state.accountId = accountId;

    async function confirmCheckout(payload) {
      const sentinelHeaders = await freshSentinelHeaders();
      const response = await fetch(CheckoutConfirmPath, {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${session.accessToken}`,
          "Content-Type": "application/json",
          "chatgpt-account-id": accountId,
          "x-openai-target-path": "/payments/checkout/confirm",
          "x-openai-target-route": "/payments/checkout/confirm",
          ...sentinelHeaders,
        },
        body: JSON.stringify(payload),
      });
      const body = await readJsonOrText(response);
      const record = {
        at: new Date().toISOString(),
        ok: response.ok,
        httpStatus: response.status,
        request: payload,
        response: body,
      };
      state.checkoutConfirmResponses.push(record);
      console.log("[oaics-default-mount] checkout/confirm response", record);
      if (!response.ok) {
        throw new Error(
          `Checkout confirm failed (${response.status}): ${JSON.stringify(body)}`,
        );
      }
      if (["blocked", "expired", "error"].includes(body?.status)) {
        throw new Error(
          `Checkout confirm returned status=${body.status}: ${JSON.stringify(body)}`,
        );
      }
      return body;
    }

    const commonHeaders = {
      Authorization: `Bearer ${session.accessToken}`,
      "chatgpt-account-id": accountId,
      "x-openai-target-path": PaymentMethodsPath,
      "x-openai-target-route": PaymentMethodsPath,
    };
    const methodsResponse = await fetch(
      `${PaymentMethodsPath}?account_id=${encodeURIComponent(accountId)}`,
      {
        credentials: "include",
        cache: "no-store",
        headers: commonHeaders,
      },
    );
    const methodsData = await readJsonOrText(methodsResponse);
    if (!methodsResponse.ok) {
      throw new Error(
        `Payment method query failed (${methodsResponse.status}): ${JSON.stringify(methodsData)}`,
      );
    }

    const paymentMethods = Array.isArray(methodsData?.payment_methods)
      ? methodsData.payment_methods
      : [];
    const defaultPaymentMethodId = methodsData?.default_payment_method_id;
    const defaultPaymentMethod = paymentMethods.find(
      (method) => method?.id === defaultPaymentMethodId,
    );
    if (!defaultPaymentMethodId || !defaultPaymentMethod) {
      throw new Error(
        `Default PaymentMethod was not returned: ${String(defaultPaymentMethodId || "null")}`,
      );
    }
    const savedPaymentMethod = normalizeSavedPaymentMethod(
      defaultPaymentMethod,
      checkoutSession,
    );
    state.defaultPaymentMethodId = defaultPaymentMethodId;
    state.defaultPaymentMethod = savedPaymentMethod;
    panel.method.textContent = methodLabel(savedPaymentMethod);

    const StripeConstructor = await loadStripeJs();
    const stripe = StripeConstructor(source.publishableKey, {
      betas: StripeBetas,
    });
    let controller = null;
    state.stripe = stripe;
    state.stripeController = null;
    const baseElementsOptions = {
      mode: source.mode,
      amount: source.amount,
      currency: source.currency,
      setupFutureUsage: source.setupFutureUsage,
      paymentMethodTypes: source.paymentMethodTypes,
      paymentMethodCreation: "manual",
      customerSessionClientSecret: source.customerSessionClientSecret,
      savedPaymentMethod: {
        enableSave: "never",
        enableRedisplay: "auto",
      },
      __elementsInitSource: "custom_checkout",
      __checkoutSessionId: identifiers.checkoutSessionId,
    };

    const metadataController = stripe?._controller || stripe?._implementation?._controller;
    const stripeRuntime = {
      referrerHost: location.host,
      locale: navigator.language || "en-US",
      stripeJsId: metadataController?._stripeJsId,
      apiVersion: metadataController?._apiVersion,
      stripeAccount: metadataController?._stripeAccount,
    };
    const authorization = await fetchNativeCustomerAuthorization(
      source,
      identifiers,
      stripeRuntime,
      defaultPaymentMethodId,
    );
    state.defaultPaymentMethod = authorization.paymentMethod;
    console.log("[oaics-default-mount] native Customer Session verified", {
      customerId: authorization.customerId,
      paymentMethodId: defaultPaymentMethodId,
      defaultPaymentMethodId: authorization.defaultPaymentMethodId,
      hasEphemeralKey: true,
    });

    const elementsOptions = {
      ...baseElementsOptions,
      __customCheckoutSavedPaymentMethods: {
        paymentMethods: [authorization.paymentMethod],
        offerSave: false,
        offerRemove: false,
      },
      __customCheckoutCustomerEmail:
        checkoutSession?.checkout_state?.email || undefined,
      __customCheckoutCustomerName:
        checkoutSession?.checkout_state?.billingAddress?.name || undefined,
      __customCheckoutCustomerAddress:
        checkoutSession?.checkout_state?.billingAddress || undefined,
      appearance: {
        theme: "stripe",
        variables: {
          borderRadius: "6px",
          colorPrimary: "#111827",
        },
      },
    };

    const elements = stripe.elements(elementsOptions);
    const paymentElement = elements.create("payment", {
      layout: "tabs",
      savedPaymentMethod: { collapsed: false },
    });
    state.elements = elements;
    state.paymentElement = paymentElement;

    state.submitCheckout = async function submitCheckout() {
      if (this.phase !== "ready" && this.phase !== "submit_failed") {
        throw new Error(`Payment Element is not ready (phase=${this.phase}).`);
      }

      this.phase = "submitting_elements";
      this.lastError = null;
      setSubmitEnabled(false, "Submitting...");
      setStatus("1/4 Validating the Payment Element...");

      try {
        const submitResult = await elements.submit();
        this.elementsSubmitResult = submitResult;
        console.log("[oaics-default-mount] elements.submit result", submitResult);
        if (submitResult?.error) {
          throw new Error(
            submitResult.error.message || "Payment Element validation failed.",
          );
        }

        const selectionProof = await selectedSavedPaymentMethod(
          controller,
          stripe,
          elements,
          defaultPaymentMethodId,
        );
        this.selectedPaymentMethodProof = {
          ...selectionProof,
          customerId: authorization.customerId,
          nativeCustomerSessionVerified: true,
        };
        console.log(
          "[oaics-default-mount] selected saved PaymentMethod verified",
          this.selectedPaymentMethodProof,
        );

        const selectedPaymentMethodType =
          typeof submitResult?.selectedPaymentMethod === "string"
            ? submitResult.selectedPaymentMethod
            : null;

        this.phase = "creating_confirmation_token";
        setStatus("2/4 Creating the Stripe ConfirmationToken...");
        const tokenResult =
          await createSavedPaymentMethodConfirmationToken(
            source,
            stripeRuntime,
            authorization,
            selectionProof.paymentMethodId,
          );
        this.confirmationToken = tokenResult?.confirmationToken || null;
        console.log(
          "[oaics-default-mount] createConfirmationToken result",
          tokenResult,
        );
        if (tokenResult?.error) {
          throw new Error(
            tokenResult.error.message || "Stripe ConfirmationToken creation failed.",
          );
        }
        const confirmToken = tokenResult?.confirmationToken?.id;
        if (!confirmToken?.startsWith("ctoken_")) {
          throw new Error("Stripe did not return a ctoken_* ConfirmationToken.");
        }

        this.phase = "confirming_checkout";
        setStatus("3/4 Confirming the OAICS Checkout...");
        let checkoutConfirm = await confirmCheckout({
          checkout_session_id: identifiers.checkoutSessionId,
          confirm_token: confirmToken,
          ...(selectedPaymentMethodType
            ? { selected_payment_method_type: selectedPaymentMethodType }
            : {}),
        });

        const conditionalOfferPreflight =
          checkoutConfirm?.conditional_offer_preflight === true;
        if (
          conditionalOfferPreflight &&
          checkoutConfirm?.type === "setup_intent"
        ) {
          if (!checkoutConfirm?.client_secret) {
            throw new Error(
              "Conditional-offer preflight returned no SetupIntent client_secret.",
            );
          }
          const nextActionResult = await stripe.handleNextAction({
            clientSecret: checkoutConfirm.client_secret,
          });
          console.log(
            "[oaics-default-mount] conditional-offer handleNextAction result",
            nextActionResult,
          );
          if (nextActionResult?.error) {
            throw new Error(
              nextActionResult.error.message ||
                "Conditional-offer payment method authentication failed.",
            );
          }
          checkoutConfirm = await confirmCheckout({
            checkout_session_id: identifiers.checkoutSessionId,
          });
        }

        if (
          conditionalOfferPreflight &&
          (checkoutConfirm?.conditional_offer_preflight !== true ||
            checkoutConfirm?.type !== "payment_intent")
        ) {
          throw new Error(
            "Conditional-offer continuation did not return a PaymentIntent.",
          );
        }
        if (!checkoutConfirm?.client_secret) {
          throw new Error("Checkout confirm response has no client_secret.");
        }

        this.phase = "confirming_stripe_intent";
        setStatus("4/4 Confirming the Stripe intent...");
        const returnUrl = checkoutConfirm.confirm_return_url || null;
        const redirectAlways = Boolean(returnUrl);
        let stripeConfirmResult;
        if (checkoutConfirm.type === "setup_intent" && !conditionalOfferPreflight) {
          stripeConfirmResult = await stripe.confirmSetup({
            elements,
            clientSecret: checkoutConfirm.client_secret,
            redirect: redirectAlways ? "always" : "if_required",
            ...(redirectAlways
              ? { confirmParams: { return_url: returnUrl } }
              : {}),
          });
        } else {
          stripeConfirmResult = await stripe.confirmPayment({
            ...(conditionalOfferPreflight ? {} : { elements }),
            clientSecret: checkoutConfirm.client_secret,
            redirect: redirectAlways ? "always" : "if_required",
            ...(redirectAlways
              ? { confirmParams: { return_url: returnUrl } }
              : {}),
          });
        }
        this.stripeConfirmResult = stripeConfirmResult;
        console.log(
          "[oaics-default-mount] Stripe intent confirmation result",
          stripeConfirmResult,
        );
        if (stripeConfirmResult?.error) {
          throw new Error(
            stripeConfirmResult.error.message || "Stripe intent confirmation failed.",
          );
        }

        this.phase = "submitted";
        setStatus("Checkout submitted successfully.", "#087443");
        setSubmitEnabled(false, "Submitted");
        return {
          elementsSubmitResult: submitResult,
          confirmationToken: tokenResult.confirmationToken,
          checkoutConfirm,
          stripeConfirmResult,
        };
      } catch (error) {
        this.phase = "submit_failed";
        this.lastError = String(error?.stack || error);
        setStatus(error?.message || String(error), "#b42318");
        setSubmitEnabled(true, "Retry submission");
        console.error("[oaics-default-mount] submit failed", error);
        throw error;
      }
    };
    panel.submit.addEventListener("click", () => {
      state.submitCheckout().catch(() => {});
    });

    paymentElement.on("change", (event) => {
      const record = {
        at: new Date().toISOString(),
        complete: event?.complete === true,
        empty: event?.empty === true,
        collapsed: event?.collapsed ?? null,
        valueType: event?.value?.type ?? null,
        paymentMethodId:
          event?.value?.payment_method || event?.value?.paymentMethod || null,
        error: event?.error?.message || null,
      };
      state.events.push(record);
      console.log("[oaics-default-mount] change", record);
    });
    paymentElement.on("loaderror", (event) => {
      state.phase = "load_error";
      state.lastError = event?.error?.message || "Payment Element loaderror";
      setStatus(state.lastError, "#b42318");
      setSubmitEnabled(false, "Payment form failed to load");
      console.error("[oaics-default-mount] loaderror", event);
    });

    const ready = waitForPaymentElementReady(paymentElement, "Payment Element");

    paymentElement.mount(panel.element);
    await ready;
    controller = stripeController(
      stripe,
      stripe?._implementation,
      elements,
      elements?._implementation,
      paymentElement,
      paymentElement?._implementation,
    );
    state.stripeController = controller;
    state.phase = "verifying_default_selection";
    setStatus("Verifying the native default saved PaymentMethod...");
    state.initialSelectionProof = await selectedSavedPaymentMethod(
      controller,
      stripe,
      elements,
      defaultPaymentMethodId,
    );
    state.phase = "ready";
    setStatus(
      `Mounted native Customer Session default ${defaultPaymentMethodId}. ` +
        "Click the button below to submit.",
      "#087443",
    );
    setSubmitEnabled(true, "Confirm and submit");
    console.log("[oaics-default-mount] ready", state.status());
  } catch (error) {
    state.phase = "failed";
    state.lastError = String(error?.stack || error);
    setStatus(error?.message || String(error), "#b42318");
    setSubmitEnabled(false, "Payment form unavailable");
    console.error("[oaics-default-mount] failed", error);
  }
})();
