import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import readline from "node:readline";

const protocolOut = process.stdout;
const nativeConsole = globalThis.console;
globalThis.console = {
  ...nativeConsole,
  log: (...args) => process.stderr.write(`${args.join(" ")}\n`),
  info: (...args) => process.stderr.write(`${args.join(" ")}\n`),
  warn: (...args) => process.stderr.write(`${args.join(" ")}\n`),
  error: (...args) => process.stderr.write(`${args.join(" ")}\n`),
};

function emit(message) {
  protocolOut.write(`${JSON.stringify(message)}\n`);
}

class RuntimeEventTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    this.listeners.set(
      type,
      listeners.filter((candidate) => candidate !== listener),
    );
  }

  dispatchEvent(event) {
    for (const listener of this.listeners.get(event.type) || []) {
      listener.call(this, event);
    }
    return true;
  }
}

class RuntimeStorage {
  constructor() {
    this.values = new Map();
  }

  get length() {
    return this.values.size;
  }

  key(index) {
    return [...this.values.keys()][index] ?? null;
  }

  getItem(key) {
    const normalized = String(key);
    return this.values.has(normalized) ? this.values.get(normalized) : null;
  }

  setItem(key, value) {
    this.values.set(String(key), String(value));
  }

  removeItem(key) {
    this.values.delete(String(key));
  }

  clear() {
    this.values.clear();
  }
}

class RuntimePerformanceNavigationTiming {
  constructor(options) {
    this.name = options.pageUrl;
    this.entryType = "navigation";
    this.startTime = 0;
    this.duration = Number(options.navigationDuration || 3459.1);
    this.domInteractive = Number(options.domInteractive || 3425.8);
    this.domContentLoadedEventStart = this.domInteractive + 8;
    this.domContentLoadedEventEnd = this.domInteractive + 12;
    this.loadEventStart = this.duration - 1;
    this.loadEventEnd = this.duration;
    this.responseStart = Math.max(1, this.domInteractive - 350);
    this.responseEnd = this.responseStart + 50;
    this.requestStart = Math.max(1, this.responseStart - 100);
    this.fetchStart = 0;
    this.redirectStart = 0;
    this.redirectEnd = 0;
    this.redirectCount = Number(options.redirectCount ?? 1);
    this.transferSize = Number(options.transferSize || 15989);
    this.encodedBodySize = Math.max(0, this.transferSize - 300);
    this.decodedBodySize = this.encodedBodySize;
    this.type = "navigate";
  }

  toJSON() {
    return { ...this };
  }
}

class RuntimePerformancePaintTiming {
  constructor(name, startTime) {
    this.name = name;
    this.entryType = "paint";
    this.startTime = Number(startTime);
    this.duration = 0;
  }

  toJSON() {
    return { ...this };
  }
}

class RuntimePerformanceObserver {
  static entries = [];

  static get supportedEntryTypes() {
    return [
      "navigation",
      "paint",
      "resource",
      "mark",
      "measure",
      "largest-contentful-paint",
      "layout-shift",
      "first-input",
      "event",
    ];
  }

  constructor(callback) {
    this.callback = callback;
    this.types = new Set();
  }

  observe(options = {}) {
    if (options.type) this.types.add(String(options.type));
    for (const type of options.entryTypes || []) this.types.add(String(type));
    if (options.buffered) {
      const entries = RuntimePerformanceObserver.entries.filter(
        (entry) => this.types.size === 0 || this.types.has(entry.entryType),
      );
      if (entries.length > 0) queueMicrotask(() => this._notify(entries));
    }
  }

  disconnect() {}

  takeRecords() {
    return [];
  }

  _notify(entries) {
    this.callback({
      getEntries: () => entries,
      getEntriesByType: (type) => entries.filter((entry) => entry.entryType === String(type)),
      getEntriesByName: (name) => entries.filter((entry) => entry.name === String(name)),
    });
  }
}

function createPluginArray() {
  const mimeTypes = [
    { type: "application/pdf", suffixes: "pdf", description: "Portable Document Format" },
    { type: "text/pdf", suffixes: "pdf", description: "Portable Document Format" },
  ];
  const names = [
    "PDF Viewer",
    "Chrome PDF Viewer",
    "Chromium PDF Viewer",
    "Microsoft Edge PDF Viewer",
    "WebKit built-in PDF",
  ];
  const plugins = names.map((name) => ({
    name,
    filename: "internal-pdf-viewer",
    description: "Portable Document Format",
    length: mimeTypes.length,
    ...Object.fromEntries(mimeTypes.map((mime, index) => [index, mime])),
  }));
  plugins.item = (index) => plugins[index] || null;
  plugins.namedItem = (name) => plugins.find((plugin) => plugin.name === name) || null;
  plugins.refresh = () => undefined;
  mimeTypes.item = (index) => mimeTypes[index] || null;
  mimeTypes.namedItem = (type) => mimeTypes.find((mime) => mime.type === type) || null;
  return { plugins, mimeTypes };
}

let relaySequence = 0;
const relayWaiters = new Map();
const pendingTransports = new Set();
const TELEMETRY_RELAY_TIMEOUT_MS = 20_000;
const TRANSPORT_DRAIN_TIMEOUT_MS = 2_000;
let datadogRum = null;
let statsigClient = null;
let currentPageUrl = "https://auth.openai.com/";
let currentPageTitle = "";
let currentRouteId = "";
let runtimeDocument = null;
let runtimeCookieValues = new Map();
let authSessionLoggingId = "";
let currentAccessFlowPage = "";
let currentPageEnteredAt = performance.now();
let sentinelSdkTimingStarted = false;
let sentinelSdkTimingCompleted = false;

const STRUCTURED_EVENT_TYPE_PREFIX =
  "openai.buf.dev/openai/protobuf-analytics-events/protobuf_analytics_events.v1.";
const ROUTE_TELEMETRY = {
  EMAIL_VERIFICATION: {
    title: "Email Verification",
    page: "ACCESS_FLOW_PAGE_TYPE_EMAIL_OTP_VERIFICATION",
  },
  ABOUT_YOU: {
    title: "About You",
    page: "ACCESS_FLOW_PAGE_TYPE_ABOUT_YOU",
  },
  CREATE_ACCOUNT_PASSWORD: {
    title: "Create Account Password",
    page: "ACCESS_FLOW_PAGE_TYPE_CREATE_ACCOUNT_PASSWORD",
  },
  CREATE_ACCOUNT: {
    title: "Create Account",
    page: "ACCESS_FLOW_PAGE_TYPE_CREATE_ACCOUNT_START",
  },
  LOG_IN: {
    title: "Log In",
    page: "ACCESS_FLOW_PAGE_TYPE_LOGIN_START",
  },
  LOG_IN_PASSWORD: {
    title: "Log In Password",
    page: "ACCESS_FLOW_PAGE_TYPE_LOGIN_PASSWORD",
  },
};

const EMAIL_VERIFICATION_FEATURE_READS = {
  gates: [
    "login_web_sentinel_killswitch",
    "hydra_web_clients_exclude_webview_fg",
    "login_web_show_terms_and_privacy_footer_by_default",
    "login_web_disable_animate_input_label",
    "login_web_enable_session_turtle_read",
  ],
  layers: {
    auth_unify_login_signup_layer: {
      login_web_sentinel_ssr_bootstrap_enabled: false,
    },
    otp_verification_layer: {
      otp_input_variant: "",
      should_auto_submit: false,
      use_6_input_boxes: false,
      use_six_digit_content: false,
      show_email_as_readonly_input: false,
    },
    auth_login_signup_opt_layer: {
      access_design_v2_content_variation: "",
      enable_clickable_wordmark_mobile: false,
      enable_clickable_wordmark: false,
    },
    passwordless_login_and_signup: {
      show_contact_verification_password_cta: false,
      show_contact_verification_social_ctas_passwordless: false,
    },
  },
};

const ABOUT_YOU_FEATURE_READS = {
  gates: ["login_web_explicit_consent_required"],
  configs: ["login_web_external_url_override", "login_web_about_you_footer"],
  layers: {
    auth_simplification_layer: {
      is_age_fallback_enabled: false,
      should_default_birthday_to_today: false,
      should_hide_age_fallback_confirm_dialog: false,
      should_hide_age_fallback_use_dob_link: false,
      should_show_warnIng_alert_on_close: false,
      should_use_age_fallback_default_experience: false,
      should_use_birthday_dropdowns: false,
      should_use_client_side_minimum_age_check: false,
      should_use_finish_creating_account_cta: false,
      should_use_last_step_confirm_age_title: false,
    },
  },
};

const CREATE_ACCOUNT_PASSWORD_FEATURE_READS = {
  layers: {
    passwordless_login_and_signup: {
      signup_password_variant: "no_passwordless",
    },
  },
};

function replaceRuntimeCookies(headerValue) {
  runtimeCookieValues = new Map();
  for (const part of String(headerValue || "").split(";")) {
    const separator = part.indexOf("=");
    if (separator > 0) {
      runtimeCookieValues.set(part.slice(0, separator).trim(), part.slice(separator + 1));
    }
  }
}

function responseHeaders(headers) {
  const output = new Headers();
  for (const [name, value] of Object.entries(headers || {})) {
    if (Array.isArray(value)) {
      for (const item of value) output.append(name, String(item));
    } else if (value !== null && value !== undefined) {
      output.append(name, String(value));
    }
  }
  return output;
}

async function bodyToBase64(body) {
  if (body === undefined || body === null) return "";
  if (typeof body === "string") return Buffer.from(body).toString("base64");
  if (body instanceof Blob || body instanceof ArrayBuffer || ArrayBuffer.isView(body)) {
    const buffer =
      body instanceof Blob
        ? Buffer.from(await body.arrayBuffer())
        : body instanceof ArrayBuffer
          ? Buffer.from(body)
          : Buffer.from(body.buffer, body.byteOffset, body.byteLength);
    return buffer.toString("base64");
  }
  return Buffer.from(String(body)).toString("base64");
}

function relayTransport(request) {
  const transportId = `transport-${++relaySequence}`;
  let timeoutMs = Math.max(5_000, Number(request.timeoutMs || 60_000));
  try {
    const url = new URL(String(request.url), currentPageUrl);
    const isTelemetry =
      url.hostname === "ab.chatgpt.com" ||
      url.pathname === "/ces/v1/rgstr" ||
      url.pathname === "/awe/api/v2/rum";
    if (isTelemetry) timeoutMs = Math.min(timeoutMs, TELEMETRY_RELAY_TIMEOUT_MS);
  } catch {}
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      relayWaiters.delete(transportId);
      reject(new Error(`transport response timeout: ${request.url}`));
    }, timeoutMs);
    relayWaiters.set(transportId, {
      resolve: (response) => {
        clearTimeout(timeout);
        resolve(response);
      },
      reject,
    });
    emit({ type: "transport_request", transportId, ...request });
  });
}

function trackPendingTransport(task) {
  pendingTransports.add(task);
  void task.then(
    () => pendingTransports.delete(task),
    () => pendingTransports.delete(task),
  );
}

async function normalizeFetchRequest(input, init = {}) {
  let target = input;
  if (typeof input === "string" || input instanceof URL) {
    target = new URL(String(input), currentPageUrl).toString();
  }
  const request = new Request(target, init);
  const headers = Object.fromEntries(request.headers.entries());
  const bridgeRequestId = headers["x-refactor-auth-runtime-request-id"] || "";
  delete headers["x-refactor-auth-runtime-request-id"];
  const bodyBase64 = ["GET", "HEAD"].includes(request.method)
    ? ""
    : Buffer.from(await request.clone().arrayBuffer()).toString("base64");
  return {
    method: request.method,
    url: request.url,
    headers,
    bodyBase64,
    bridgeRequestId,
    allowRedirects: request.redirect !== "manual",
  };
}

async function bridgeFetch(input, init = {}) {
  const request = await normalizeFetchRequest(input, init);
  const response = await relayTransport({
    ...request,
    timeoutMs: Number(init.runtimeTimeoutMs || 60_000),
  });
  const body = response.bodyBase64 ? Buffer.from(response.bodyBase64, "base64") : null;
  const noBodyStatus = [101, 103, 204, 205, 304].includes(Number(response.status));
  return new Response(noBodyStatus ? null : body, {
    status: Number(response.status || 500),
    statusText: String(response.statusText || ""),
    headers: responseHeaders(response.headers),
  });
}

class RuntimeXMLHttpRequest extends RuntimeEventTarget {
  constructor() {
    super();
    this.readyState = 0;
    this.status = 0;
    this.statusText = "";
    this.response = "";
    this.responseText = "";
    this.responseType = "";
    this.requestHeaders = {};
    this.responseHeaderValues = {};
  }

  open(method, url) {
    this.method = String(method || "GET").toUpperCase();
    this.url = new URL(String(url), currentPageUrl).toString();
    this.readyState = 1;
  }

  setRequestHeader(name, value) {
    this.requestHeaders[String(name)] = String(value);
  }

  getResponseHeader(name) {
    return this.responseHeaderValues[String(name).toLowerCase()] || null;
  }

  getAllResponseHeaders() {
    return Object.entries(this.responseHeaderValues)
      .map(([name, value]) => `${name}: ${value}`)
      .join("\r\n");
  }

  send(body = null) {
    const task = (async () => {
      const headers = { ...this.requestHeaders };
      const bridgeRequestId = headers["x-refactor-auth-runtime-request-id"] || "";
      delete headers["x-refactor-auth-runtime-request-id"];
      const response = await relayTransport({
        method: this.method,
        url: this.url,
        headers,
        bodyBase64: await bodyToBase64(body),
        bridgeRequestId,
        timeoutMs: 60_000,
      });
      this.status = Number(response.status || 0);
      this.statusText = String(response.statusText || "");
      this.responseHeaderValues = Object.fromEntries(
        Object.entries(response.headers || {}).map(([name, value]) => [
          name.toLowerCase(),
          String(value),
        ]),
      );
      const responseBuffer = response.bodyBase64
        ? Buffer.from(response.bodyBase64, "base64")
        : Buffer.alloc(0);
      this.responseText = responseBuffer.toString("utf8");
      this.response = this.responseType === "arraybuffer" ? responseBuffer.buffer : this.responseText;
      this.readyState = 4;
      const event = new Event("readystatechange");
      this.onreadystatechange?.(event);
      this.dispatchEvent(event);
      const loadEvent = new Event("load");
      this.onload?.(loadEvent);
      this.dispatchEvent(loadEvent);
      const loadEndEvent = new Event("loadend");
      this.onloadend?.(loadEndEvent);
      this.dispatchEvent(loadEndEvent);
    })();
    trackPendingTransport(task);
  }

  abort() {}
}

function runtimeAnchor() {
  let value = new URL(currentPageUrl);
  return {
    set href(next) {
      value = new URL(String(next), currentPageUrl);
    },
    get href() {
      return value.href;
    },
    get protocol() {
      return value.protocol;
    },
    get host() {
      return value.host;
    },
    get hostname() {
      return value.hostname;
    },
    get port() {
      return value.port;
    },
    get pathname() {
      return value.pathname;
    },
    get search() {
      return value.search;
    },
    get hash() {
      return value.hash;
    },
  };
}

function installWebApis(options) {
  const windowTarget = new RuntimeEventTarget();
  const documentTarget = new RuntimeEventTarget();
  replaceRuntimeCookies(options.documentCookie);
  currentPageUrl = options.pageUrl;
  currentPageTitle = options.pageTitle || "";

  Object.defineProperty(globalThis, "window", { value: globalThis, configurable: true });
  Object.defineProperty(globalThis, "self", { value: globalThis, configurable: true });
  Object.defineProperty(globalThis, "top", { value: globalThis, configurable: true });
  Object.defineProperty(globalThis, "parent", { value: globalThis, configurable: true });
  globalThis.addEventListener = windowTarget.addEventListener.bind(windowTarget);
  globalThis.removeEventListener = windowTarget.removeEventListener.bind(windowTarget);
  globalThis.dispatchEvent = windowTarget.dispatchEvent.bind(windowTarget);

  const connection = new RuntimeEventTarget();
  Object.assign(connection, {
    effectiveType: options.effectiveType || "4g",
    downlink: Number(options.downlink || 10),
    rtt: Number(options.rtt || 50),
    saveData: false,
  });
  const { plugins, mimeTypes } = createPluginArray();
  const userAgentDataProfile = options.userAgentData;
  if (
    !userAgentDataProfile ||
    !Array.isArray(userAgentDataProfile.brands) ||
    !Array.isArray(userAgentDataProfile.fullVersionList)
  ) {
    throw new Error("Auth Web browser profile is missing Client Hint brand data");
  }
  const userAgentDataBrands = userAgentDataProfile.brands.map(({ brand, version }) => ({
    brand: String(brand),
    version: String(version),
  }));
  const userAgentDataFullVersionList = userAgentDataProfile.fullVersionList.map(
    ({ brand, version }) => ({ brand: String(brand), version: String(version) }),
  );
  const navigatorValue = {
    language: options.language,
    languages: options.languages,
    userAgent: options.userAgent,
    platform: options.platform,
    vendor: "Google Inc.",
    hardwareConcurrency: Number(options.hardwareConcurrency || 8),
    deviceMemory: Number(options.deviceMemory || 8),
    cookieEnabled: true,
    maxTouchPoints: 0,
    pdfViewerEnabled: true,
    webdriver: false,
    plugins,
    mimeTypes,
    userAgentData: {
      brands: userAgentDataBrands,
      mobile: Boolean(userAgentDataProfile.mobile),
      platform: String(userAgentDataProfile.platform),
      async getHighEntropyValues(hints = []) {
        const values = {
          architecture: String(userAgentDataProfile.architecture),
          bitness: String(userAgentDataProfile.bitness),
          brands: this.brands,
          fullVersionList: userAgentDataFullVersionList,
          mobile: this.mobile,
          model: String(userAgentDataProfile.model),
          platform: this.platform,
          platformVersion: String(userAgentDataProfile.platformVersion),
          uaFullVersion: String(userAgentDataProfile.uaFullVersion),
        };
        return Object.fromEntries(hints.filter((hint) => hint in values).map((hint) => [hint, values[hint]]));
      },
      toJSON() {
        return { brands: this.brands, mobile: this.mobile, platform: this.platform };
      },
    },
    onLine: true,
    connection,
    sendBeacon(url, body) {
      const task = (async () => {
        const contentType = body instanceof Blob && body.type ? { "content-type": body.type } : {};
        await relayTransport({
          method: "POST",
          url: new URL(String(url), currentPageUrl).toString(),
          headers: contentType,
          bodyBase64: await bodyToBase64(body),
        bridgeRequestId: "",
        allowRedirects: true,
        timeoutMs: 60_000,
        });
      })();
      trackPendingTransport(task);
      return true;
    },
  };
  Object.defineProperty(globalThis, "navigator", {
    value: navigatorValue,
    configurable: true,
  });
  Object.defineProperty(globalThis, "location", {
    value: new URL(currentPageUrl),
    configurable: true,
  });
  Object.defineProperty(globalThis, "screen", {
    value: {
      width: Number(options.screenWidth || 1512),
      height: Number(options.screenHeight || 982),
      availWidth: Number(options.screenWidth || 1512),
      availHeight: Number(options.screenHeight || 982) - 35,
      colorDepth: 24,
      pixelDepth: 24,
      orientation: { angle: 0, type: "landscape-primary" },
    },
    configurable: true,
  });
  globalThis.innerWidth = Number(options.screenWidth || 1512);
  globalThis.innerHeight = Number(options.screenHeight || 982) - 120;
  globalThis.outerWidth = Number(options.screenWidth || 1512);
  globalThis.outerHeight = Number(options.screenHeight || 982);
  globalThis.devicePixelRatio = Number(options.devicePixelRatio || 2);

  const navigationStart = Date.now() - Math.round(performance.now());
  Object.defineProperty(globalThis.performance, "timing", {
    value: { navigationStart },
    configurable: true,
  });
  const navigationEntry = new RuntimePerformanceNavigationTiming(options);
  const paintEntries = [
    new RuntimePerformancePaintTiming("first-paint", options.firstContentfulPaint || 3296),
    new RuntimePerformancePaintTiming(
      "first-contentful-paint",
      options.firstContentfulPaint || 3296,
    ),
  ];
  const firstContentfulPaint = Number(options.firstContentfulPaint || 3296);
  const performanceEntries = [
    navigationEntry,
    ...paintEntries,
    {
      name: "",
      entryType: "largest-contentful-paint",
      startTime: firstContentfulPaint,
      renderTime: firstContentfulPaint,
      loadTime: firstContentfulPaint,
      size: 1,
    },
    {
      name: "",
      entryType: "layout-shift",
      startTime: 0,
      value: 0,
      hadRecentInput: false,
      sources: [],
    },
  ];
  RuntimePerformanceObserver.entries = performanceEntries;
  globalThis.PerformanceNavigationTiming = RuntimePerformanceNavigationTiming;
  globalThis.PerformancePaintTiming = RuntimePerformancePaintTiming;
  globalThis.PerformanceObserver = RuntimePerformanceObserver;
  globalThis.performance.getEntries = () => [...performanceEntries];
  globalThis.performance.getEntriesByType = (type) =>
    performanceEntries.filter((entry) => entry.entryType === String(type));
  globalThis.performance.getEntriesByName = (name) =>
    performanceEntries.filter((entry) => entry.name === String(name));
  globalThis.requestAnimationFrame = (callback) =>
    setTimeout(() => callback(performance.now()), 16);
  globalThis.cancelAnimationFrame = (handle) => clearTimeout(handle);
  globalThis.MutationObserver = class RuntimeMutationObserver {
    observe() {}

    disconnect() {}

    takeRecords() {
      return [];
    }
  };
  globalThis.history = { state: null, length: 1, pushState() {}, replaceState() {} };
  globalThis.localStorage = new RuntimeStorage();
  globalThis.sessionStorage = new RuntimeStorage();
  globalThis.CustomEvent = class RuntimeCustomEvent extends Event {
    constructor(type, init = {}) {
      super(type);
      this.detail = init.detail;
    }
  };

  runtimeDocument = {
    title: options.pageTitle || "",
    referrer: options.referrer || "https://chatgpt.com/",
    childNodes: [],
    visibilityState: "visible",
    readyState: "complete",
    hidden: false,
    addEventListener: documentTarget.addEventListener.bind(documentTarget),
    removeEventListener: documentTarget.removeEventListener.bind(documentTarget),
    dispatchEvent: documentTarget.dispatchEvent.bind(documentTarget),
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
    getElementById() {
      return null;
    },
    getElementsByTagName() {
      return [];
    },
    hasFocus() {
      return true;
    },
    createElement(tagName) {
      return String(tagName).toLowerCase() === "a" ? runtimeAnchor() : new RuntimeEventTarget();
    },
    documentElement: {
      lang: options.language,
      clientWidth: Number(options.screenWidth || 1512),
      clientHeight: Number(options.screenHeight || 982) - 120,
      scrollWidth: Number(options.screenWidth || 1512),
      scrollHeight: Number(options.screenHeight || 982) - 120,
      getAttribute() {
        return null;
      },
      contains() {
        return false;
      },
    },
    body: {
      childNodes: [],
      clientWidth: Number(options.screenWidth || 1512),
      clientHeight: Number(options.screenHeight || 982) - 120,
      scrollWidth: Number(options.screenWidth || 1512),
      scrollHeight: Number(options.screenHeight || 982) - 120,
      addEventListener() {},
      removeEventListener() {},
      contains() {
        return false;
      },
    },
  };
  Object.defineProperty(runtimeDocument, "cookie", {
    configurable: true,
    get() {
      return [...runtimeCookieValues.entries()]
        .map(([name, value]) => `${name}=${value}`)
        .join("; ");
    },
    set(rawValue) {
      const firstPart = String(rawValue).split(";", 1)[0];
      const separator = firstPart.indexOf("=");
      if (separator > 0) {
        runtimeCookieValues.set(
          firstPart.slice(0, separator).trim(),
          firstPart.slice(separator + 1),
        );
      }
    },
  });
  Object.defineProperty(globalThis, "document", {
    value: runtimeDocument,
    configurable: true,
  });
  globalThis.fetch = bridgeFetch;
  globalThis.XMLHttpRequest = RuntimeXMLHttpRequest;
}

async function importBundle(path) {
  const source = await readFile(path, "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

function logStructuredEvent(eventType, eventParams = {}) {
  if (!statsigClient) return;
  statsigClient.logEvent("__protobuf_structured_event__", undefined, {
    eventId: randomUUID(),
    eventCreatedAt: new Date().toISOString(),
    eventType: "web",
    deviceParams: {},
    eventParams: {
      "@type": `${STRUCTURED_EVENT_TYPE_PREFIX}${eventType}`,
      ...eventParams,
    },
  });
}

function logUserAction(actionType, extra = {}) {
  if (!currentAccessFlowPage) return;
  logStructuredEvent("AccessFlowUserAction", {
    authSessionLoggingId,
    actionType,
    page: currentAccessFlowPage,
    ...extra,
  });
}

function readFeatureConfiguration(reads) {
  if (!statsigClient || !reads) return;
  for (const gate of reads.gates || []) {
    statsigClient.checkGate(gate);
  }
  for (const config of reads.configs || []) {
    statsigClient.getDynamicConfig(config);
  }
  for (const [layerName, parameters] of Object.entries(reads.layers || {})) {
    const layer = statsigClient.getLayer(layerName);
    for (const [parameterName, fallback] of Object.entries(parameters)) {
      layer.get(parameterName, fallback);
    }
  }
}

function recordPageLifecycle(routeId, { initial = false } = {}) {
  const route = ROUTE_TELEMETRY[routeId];
  if (!route || !statsigClient) return;
  const previousPage = currentAccessFlowPage;
  const now = performance.now();
  const transitionLatencyMs = Math.max(0, Math.round(now - currentPageEnteredAt));
  currentAccessFlowPage = route.page;
  currentPageEnteredAt = now;

  statsigClient.logEvent(`Login Web: Page View: ${route.title}`, routeId, {
    routeId,
    isError: "false",
  });
  logStructuredEvent("AccessFlowPageLoad", {
    authSessionLoggingId,
    page: route.page,
    ...(!initial && previousPage
      ? { previousPage, transitionLatencyMs }
      : {}),
  });

  if (routeId === "EMAIL_VERIFICATION") {
    readFeatureConfiguration(EMAIL_VERIFICATION_FEATURE_READS);
  } else if (routeId === "ABOUT_YOU") {
    readFeatureConfiguration(ABOUT_YOU_FEATURE_READS);
  } else if (routeId === "CREATE_ACCOUNT_PASSWORD") {
    readFeatureConfiguration(CREATE_ACCOUNT_PASSWORD_FEATURE_READS);
  }
}

function recordRequestStartTelemetry(url, headers) {
  const path = url.pathname;
  if (path === "/api/accounts/email-otp/validate") {
    logUserAction("ACCESS_FLOW_USER_ACTION_TYPE_CONTINUE");
    statsigClient.logEvent("login_web_validate_otp", undefined, {
      intent: "validate",
      kind: "email",
      routeId: "email_otp_verification",
    });
  } else if (path === "/api/accounts/user/register") {
    statsigClient.logEvent("login_web_register_user", "email");
  } else if (path === "/api/accounts/create_account") {
    logUserAction("ACCESS_FLOW_USER_ACTION_TYPE_INPUT", {
      field: "ACCESS_FLOW_FIELD_NAME",
    });
    logUserAction("ACCESS_FLOW_USER_ACTION_TYPE_CONTINUE");
    statsigClient.logEvent("login_web_onboarding_user_info_complete", undefined, {
      flow: "authapi",
      loginWebUI: "new",
    });
  }
  return headers.get("x-access-flow-invocation-id") || randomUUID();
}

function recordApiInvocation(url, response, latencyMs, invocationId) {
  if (!currentAccessFlowPage || !url.pathname.startsWith("/api/accounts/")) return;
  const apiPath = url.pathname.slice("/api/accounts".length) || "/";
  logStructuredEvent("AccessFlowApiInvocation", {
    authSessionLoggingId,
    path: apiPath,
    status: response.ok
      ? "ACCESS_FLOW_API_STATUS_SUCCESS"
      : "ACCESS_FLOW_API_STATUS_FAILURE",
    responseCode: response.status,
    latencyMs: Math.max(0, Math.round(latencyMs)),
    page: currentAccessFlowPage,
    invocationId,
  });
}

function redactUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl, "https://openai.invalid");
    let changed = parsed.hash.length > 0;
    for (const key of ["email", "mfa_token", "prompt"]) {
      if (parsed.searchParams.has(key)) {
        parsed.searchParams.set(key, "<redacted>");
        changed = true;
      }
    }
    parsed.hash = "";
    if (!changed) return rawUrl;
    return /^[a-z][a-z\d+.-]*:/i.test(rawUrl)
      ? parsed.toString()
      : `${parsed.pathname}${parsed.search}`;
  } catch {
    return "https://openai.invalid/redacted";
  }
}

function buildDatadogConfig(config) {
  const rumProxyPath = config.rumProxyPath || "/awe/api/v2/rum";
  const isRumProxy = (url) => {
    try {
      const parsed = new URL(url, location.origin);
      return parsed.origin === location.origin && parsed.pathname === rumProxyPath;
    } catch {
      return false;
    }
  };
  const isTraceable = (url) => {
    try {
      const parsed = new URL(url, location.origin);
      return parsed.origin === location.origin && parsed.pathname !== rumProxyPath;
    } catch {
      return false;
    }
  };
  return {
    applicationId: config.applicationId,
    clientToken: config.clientToken,
    site: config.site,
    service: config.service,
    env: config.env,
    version: config.version,
    sessionSampleRate: Number(config.sessionSampleRate ?? 100),
    sessionReplaySampleRate: Number(config.sessionReplaySampleRate ?? 1),
    trackUserInteractions: true,
    trackResources: true,
    trackLongTasks: true,
    allowedTracingUrls: [isTraceable],
    defaultPrivacyLevel: config.defaultPrivacyLevel,
    trackViewsManually: true,
    trackFeatureFlagsForEvents: ["vital", "action", "long_task", "resource"],
    proxy: ({ path, parameters }) => {
      const base = path === "/api/v2/rum" ? rumProxyPath : `https://browser-intake-datadoghq.com${path}`;
      return parameters ? `${base}?${parameters}` : base;
    },
    beforeSend: (event) => {
      if (event.type === "resource" && isRumProxy(event.resource.url)) return false;
      event.view.url = redactUrl(event.view.url);
      if (event.view.referrer) event.view.referrer = redactUrl(event.view.referrer);
      if (event.type === "resource") event.resource.url = redactUrl(event.resource.url);
      if (event.type === "error" && event.error.resource) {
        event.error.resource.url = redactUrl(event.error.resource.url);
      }
      return true;
    },
  };
}

async function flushRuntime({ toggleVisibility = true } = {}) {
  await new Promise((resolve) => setTimeout(resolve, 25));
  if (toggleVisibility && runtimeDocument) {
    runtimeDocument.visibilityState = "hidden";
    runtimeDocument.hidden = true;
    const hidden = {
      type: "visibilitychange",
      isTrusted: true,
      timeStamp: performance.now(),
    };
    globalThis.dispatchEvent(hidden);
    runtimeDocument.dispatchEvent(hidden);
  }
  if (statsigClient && typeof statsigClient.flush === "function") {
    await Promise.race([
      statsigClient.flush(),
      new Promise((resolve) => setTimeout(resolve, 1_000)),
    ]).catch(() => {});
  }
  await new Promise((resolve) => setTimeout(resolve, 30));
  if (pendingTransports.size > 0) {
    await Promise.race([
      Promise.allSettled([...pendingTransports]),
      new Promise((resolve) => setTimeout(resolve, TRANSPORT_DRAIN_TIMEOUT_MS)),
    ]);
  }
  if (toggleVisibility && runtimeDocument) {
    runtimeDocument.visibilityState = "visible";
    runtimeDocument.hidden = false;
    const visible = {
      type: "visibilitychange",
      isTrusted: true,
      timeStamp: performance.now(),
    };
    globalThis.dispatchEvent(visible);
    runtimeDocument.dispatchEvent(visible);
  }
}

async function initializeRuntime(payload) {
  const clientEntryStartedAt = performance.now();
  installWebApis(payload.webProfile);
  const datadogModule = await importBundle(payload.datadogBundlePath);
  const statsigModule = await importBundle(payload.statsigBundlePath);
  datadogRum = datadogModule.d;
  const datadogConfig = buildDatadogConfig({
    ...payload.datadogConfig,
    defaultPrivacyLevel: datadogModule.D.MASK_USER_INPUT,
  });
  datadogRum.init(datadogConfig);

  datadogRum.startDurationVital("parse_bootstrap");
  const bootstrapParseStartedAt = performance.now();
  const bootstrap = JSON.parse(payload.bootstrapJson);
  const bootstrapParseDurationMs = performance.now() - bootstrapParseStartedAt;
  datadogRum.stopDurationVital("parse_bootstrap");
  const metadata = bootstrap.immutableClientSessionMetadata;
  const identity = bootstrap.statsigClientInitData.identity;
  authSessionLoggingId = String(metadata.auth_session_logging_id || identity.sessionLoggingId || "");

  datadogRum.startDurationVital("initialize_intl");
  let intlLocale = String(payload.webProfile.language || identity.locale || "");
  try {
    intlLocale = Intl.getCanonicalLocales(intlLocale)[0];
    new Intl.DateTimeFormat(intlLocale, { dateStyle: "medium", timeStyle: "short" }).format(
      new Date(),
    );
    new Intl.NumberFormat(intlLocale).format(123456.789);
    new Intl.RelativeTimeFormat(intlLocale, { numeric: "auto" }).format(-1, "day");
  } finally {
    datadogRum.stopDurationVital("initialize_intl");
  }

  datadogRum.startDurationVital("initialize_statsig_client");
  const statsigSdk = statsigModule.a;
  const statsigPlugins = statsigModule.b;
  const options = {
    environment: { tier: "production" },
    networkConfig: {
      api: payload.statsigApiUrl,
      logEventUrl: payload.statsigLogEventUrl,
    },
  };
  if (statsigPlugins?.StatsigAutoCapturePlugin) {
    const allowedAutoCaptureEvents = new Set([
      statsigPlugins.AutoCaptureEventName?.PERFORMANCE,
      statsigPlugins.AutoCaptureEventName?.WEB_VITALS,
    ]);
    options.plugins = [
      new statsigPlugins.StatsigAutoCapturePlugin({
        eventFilterFunc: (event) => allowedAutoCaptureEvents.has(event.eventName),
      }),
    ];
  }
  const statsigInitializeStartedAt = performance.now();
  statsigClient = new statsigSdk.StatsigClient(
    payload.statsigClientKey,
    {
      locale: intlLocale,
      ...(identity.ip ? { ip: identity.ip } : {}),
      ...(identity.country ? { country: identity.country } : {}),
      appVersion: payload.datadogConfig.version,
      userAgent: identity.userAgent,
      customIDs: {
        WebAnonymousCookieID: identity.deviceId,
        DeviceId: identity.deviceId,
        stableID: identity.deviceId,
        ...(identity.oaicomStableId ? { oaicom_stable_id: identity.oaicomStableId } : {}),
        ...(identity.sourceSurfaceStableId
          ? { source_surface_stable_id: identity.sourceSurfaceStableId }
          : {}),
        AuthSessionLoggingId: identity.sessionLoggingId,
      },
      custom: {
        client_id: identity.clientId,
        app_name_enum: identity.appNameEnum,
        originator: identity.originator,
        AuthSessionLoggingId: identity.sessionLoggingId,
        client_type: "web",
        route: identity.route,
      },
    },
    options,
  );
  statsigClient.dataAdapter.setData(bootstrap.statsigClientInitData.bootstrap);
  statsigClient.initializeSync({ disableBackgroundCacheRefresh: false });
  const statsigInitializeDurationMs = performance.now() - statsigInitializeStartedAt;
  datadogRum.stopDurationVital("initialize_statsig_client");

  datadogRum.setGlobalContext({
    clientId: metadata.openai_client_id,
    appNameEnum: metadata.app_name_enum,
    sessionLoggingId: metadata.auth_session_logging_id,
    track: bootstrap.track,
    deviceId: identity.deviceId,
  });
  currentPageTitle = payload.pageTitle;
  currentRouteId = payload.routeId;
  datadogRum.startView({
    name: payload.pageTitle,
    context: { routeId: payload.routeId, isError: false },
  });
  statsigClient.logEvent("client_bootstrap_bytes", Buffer.byteLength(payload.bootstrapJson));
  statsigClient.logEvent(
    "server_request_start_to_client_entry_start_duration_ms",
    Date.now() - Number(bootstrap.requestStartMillis),
  );
  statsigClient.logEvent(
    "statsig_bootstrap_bytes",
    bootstrap.statsigClientInitData.bootstrap.length,
  );
  statsigClient.logEvent("bootstrap_parse_duration_ms", bootstrapParseDurationMs);
  statsigClient.logEvent("statsig_initialize_duration_ms", statsigInitializeDurationMs);
  statsigClient.logEvent("client_entry_duration_ms", performance.now() - clientEntryStartedAt);
  logStructuredEvent("ChatgptUserIdentified");
  currentPageEnteredAt = performance.now();
  recordPageLifecycle(payload.routeId, { initial: true });
  await flushRuntime();
  const datadogInternalContext =
    datadogRum.getInternalContext(performance.now()) || datadogRum.getInternalContext() || null;
  const userAgentDataHighEntropyValues = await navigator.userAgentData.getHighEntropyValues([
    "architecture",
    "bitness",
    "brands",
    "fullVersionList",
    "mobile",
    "model",
    "platform",
    "platformVersion",
    "uaFullVersion",
  ]);
  return {
    authSessionLoggingId: metadata.auth_session_logging_id,
    deviceId: identity.deviceId,
    statsigSessionReady: Boolean(statsigClient),
    datadogSessionReady: Boolean(datadogRum.getInitConfiguration()),
    datadogInternalContext,
    datadogGlobalContext: datadogRum.getGlobalContext() || null,
    intlInitialized: Boolean(intlLocale),
    intlLocale,
    browserProfile: {
      userAgent: navigator.userAgent,
      language: navigator.language,
      languages: navigator.languages,
      platform: navigator.platform,
      hardwareConcurrency: navigator.hardwareConcurrency,
      deviceMemory: navigator.deviceMemory,
      cookieEnabled: navigator.cookieEnabled,
      maxTouchPoints: navigator.maxTouchPoints,
      webdriver: navigator.webdriver,
      screenWidth: screen.width,
      screenHeight: screen.height,
      innerWidth: globalThis.innerWidth,
      innerHeight: globalThis.innerHeight,
      devicePixelRatio: globalThis.devicePixelRatio,
      userAgentData: navigator.userAgentData,
      userAgentDataHighEntropyValues,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
  };
}

async function runtimeRequest(payload) {
  const headers = new Headers(payload.headers || {});
  headers.set("x-refactor-auth-runtime-request-id", payload.bridgeRequestId);
  const body = payload.bodyBase64 ? Buffer.from(payload.bodyBase64, "base64") : undefined;
  const requestUrl = new URL(payload.url, currentPageUrl);
  const invocationId = recordRequestStartTelemetry(requestUrl, headers);
  const requestStartedAt = performance.now();
  const response = await fetch(payload.url, {
    method: payload.method,
    headers,
    body: ["GET", "HEAD"].includes(payload.method) ? undefined : body,
    redirect: payload.allowRedirects ? "follow" : "manual",
    runtimeTimeoutMs: payload.timeoutMs,
  });
  recordApiInvocation(
    requestUrl,
    response,
    performance.now() - requestStartedAt,
    invocationId,
  );
  if (
    requestUrl.pathname === "/api/accounts/email-otp/validate" &&
    response.ok
  ) {
    statsigClient.checkGate("login_web_single_read_continuation_json");
  }
  const responseBody = Buffer.from(await response.arrayBuffer()).toString("base64");
  await flushRuntime({ toggleVisibility: false });
  return {
    status: response.status,
    headers: Object.fromEntries(response.headers.entries()),
    bodyBase64: responseBody,
  };
}

async function recordStage(payload) {
  const context = {
    runtime: "protocol",
    phase: payload.phase,
    ...(payload.status !== undefined ? { status: payload.status } : {}),
  };
  datadogRum.addAction(payload.name, context);
  await flushRuntime({ toggleVisibility: false });
  return { recorded: true };
}

async function navigateRuntime(payload) {
  const nextPageUrl = new URL(payload.pageUrl, currentPageUrl).toString();
  const nextPageTitle = String(payload.pageTitle || "");
  const nextRouteId = String(payload.routeId || "");
  const previousPageUrl = currentPageUrl;
  const changed =
    nextPageUrl !== currentPageUrl ||
    nextPageTitle !== currentPageTitle ||
    nextRouteId !== currentRouteId;

  currentPageUrl = nextPageUrl;
  currentPageTitle = nextPageTitle;
  currentRouteId = nextRouteId;
  globalThis.location.href = nextPageUrl;
  if (runtimeDocument) {
    runtimeDocument.referrer = previousPageUrl;
    runtimeDocument.title = nextPageTitle;
  }
  replaceRuntimeCookies(payload.documentCookie);

  if (changed) {
    datadogRum.startView({
      name: nextPageTitle,
      context: { routeId: nextRouteId, isError: false },
    });
    recordPageLifecycle(nextRouteId);
  }
  await flushRuntime({ toggleVisibility: false });
  return {
    changed,
    pageUrl: currentPageUrl,
    pageTitle: currentPageTitle,
    routeId: currentRouteId,
  };
}

async function recordSentinelTiming(payload) {
  if (payload.stage === "request_start" && !sentinelSdkTimingStarted) {
    sentinelSdkTimingStarted = true;
    statsigClient.logEvent("login_web_sentinel_sdk_request_start_ms", performance.now());
  } else if (payload.stage === "ready" && !sentinelSdkTimingCompleted) {
    sentinelSdkTimingStarted = true;
    sentinelSdkTimingCompleted = true;
    statsigClient.logEvent("login_web_sentinel_sdk_ready_ms", performance.now());
  }
  await flushRuntime({ toggleVisibility: false });
  return {
    requestStarted: sentinelSdkTimingStarted,
    ready: sentinelSdkTimingCompleted,
  };
}

async function handleCommand(message) {
  const commandId = message.commandId;
  try {
    let result;
    if (message.type === "init") result = await initializeRuntime(message);
    else if (message.type === "request") result = await runtimeRequest(message);
    else if (message.type === "stage") result = await recordStage(message);
    else if (message.type === "navigate") result = await navigateRuntime(message);
    else if (message.type === "sentinel_timing") result = await recordSentinelTiming(message);
    else if (message.type === "flush") {
      await flushRuntime();
      result = { flushed: true };
    } else if (message.type === "close") {
      await flushRuntime();
      result = { closed: true, documentCookie: runtimeDocument?.cookie || "" };
    } else {
      throw new Error(`unknown command: ${message.type}`);
    }
    emit({ type: "command_result", commandId, ok: true, result });
    if (message.type === "close") setTimeout(() => process.exit(0), 10);
  } catch (error) {
    emit({
      type: "command_result",
      commandId,
      ok: false,
      error: error?.stack || String(error),
    });
  }
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch (error) {
    emit({ type: "protocol_error", error: `invalid JSON command: ${error}` });
    return;
  }
  if (message.type === "transport_response") {
    const waiter = relayWaiters.get(message.transportId);
    if (waiter) {
      relayWaiters.delete(message.transportId);
      waiter.resolve(message);
    }
    return;
  }
  void handleCommand(message);
});

input.on("close", () => process.exit(0));
