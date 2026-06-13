#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";

const repo = process.cwd();
const traceDir = path.join(repo, "output/outlook_browser");
const defaultRuntime = path.join(traceDir, "runtime_trace_ifkaruehjmec_1780995305.jsonl");
const defaultJs = path.join(traceDir, "js_internal_trace_ifkaruehjmec_1780995305.jsonl");
const outDir = path.join(traceDir, "human_replay_bundles");

function argValue(name, fallback) {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const runtimePath = path.resolve(argValue("--runtime", defaultRuntime));
const jsPath = path.resolve(argValue("--js", defaultJs));

function parseJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\n/)
    .map((line, idx) => ({ line, lineNo: idx + 1 }))
    .filter((x) => x.line.trim())
    .map(({ line, lineNo }) => {
      try {
        return { lineNo, ...JSON.parse(line) };
      } catch (error) {
        return { lineNo, kind: "parse_error", error: String(error) };
      }
    });
}

function sha16(value) {
  const s = typeof value === "string" ? value : JSON.stringify(value ?? "");
  if (!s) return "";
  return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
}

function safeJson(value) {
  if (typeof value !== "string") return value && typeof value === "object" ? value : null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function tokenShape(value) {
  const s = String(value || "");
  return {
    present: Boolean(s),
    len: s.length,
    parts: s ? s.split(":").length : 0,
    sha16: s ? sha16(s) : "",
  };
}

function headerSummary(headers = {}) {
  const names = Object.keys(headers).sort();
  const pick = {};
  for (const key of [
    "accept",
    "accept-language",
    "content-type",
    "origin",
    "referer",
    "sec-fetch-dest",
    "sec-fetch-mode",
    "sec-fetch-site",
    "user-agent",
  ]) {
    if (headers[key]) pick[key] = headers[key];
  }
  return {
    names,
    selected: pick,
    cookieNames: cookieNames(headers.cookie),
    proxyAuthorizationPresent: Boolean(headers["proxy-authorization"]),
    proxyAuthorizationSha16: headers["proxy-authorization"] ? sha16(headers["proxy-authorization"]) : "",
  };
}

function cookieNames(cookieHeader) {
  return String(cookieHeader || "")
    .split(";")
    .map((x) => x.trim().split("=")[0])
    .filter(Boolean);
}

function bodySummary(raw) {
  const s = String(raw || "");
  const parsed = safeJson(s);
  const out = {
    len: s.length,
    sha16: s ? sha16(s) : "",
    json: Boolean(parsed && typeof parsed === "object"),
    keys: parsed && typeof parsed === "object" ? Object.keys(parsed).sort() : [],
  };
  if (!parsed || typeof parsed !== "object") return out;

  if (parsed.challengeDetails || parsed.challengeMetadata || parsed.challengeSolution || parsed.riskProviderMetadata) {
    const details = parsed.challengeDetails || {};
    const metadata = parsed.challengeMetadata || {};
    out.human = {
      state: parsed.state || "",
      challengeType: details.challengeType || parsed.challengeSolution?.challengeType || "",
      appId: metadata.appId || "",
      uuid: metadata.uuid || details.uuid || "",
      vid: metadata.vid || details.vid || "",
      challengeUrlHost: hostOf(details.challengeUrl || metadata.challengeUrl || ""),
      challengeUrlPath: pathOfUrl(details.challengeUrl || metadata.challengeUrl || ""),
      px3: tokenShape(parsed.challengeSolution?.px3 || parsed.riskProviderMetadata?.[0]?.px3),
      pxde: tokenShape(parsed.challengeSolution?.pxde || parsed.riskProviderMetadata?.[0]?.pxde),
      pxvid: tokenShape(parsed.challengeSolution?.pxvid || parsed.riskProviderMetadata?.[0]?.pxvid),
    };
  }
  if (parsed.state || parsed.continuationToken) {
    out.risk = {
      state: parsed.state || "",
      continuationToken: tokenShape(parsed.continuationToken),
    };
  }
  if (Object.prototype.hasOwnProperty.call(parsed, "Password") || Object.prototype.hasOwnProperty.call(parsed, "ContinuationToken")) {
    out.createAccountPost = {
      memberNameSha16: parsed.MemberName ? sha16(parsed.MemberName) : "",
      memberNameDomain: String(parsed.MemberName || "").split("@")[1] || "",
      passwordPresent: Object.prototype.hasOwnProperty.call(parsed, "Password"),
      continuationToken: tokenShape(parsed.ContinuationToken),
      challengeSolutionPresent: Boolean(parsed.challengeSolution),
    };
  }
  if (parsed.redirectUrl || parsed.signinName || parsed.code) {
    out.createAccountResponse = {
      hasRedirectUrl: Boolean(parsed.redirectUrl),
      redirectHost: hostOf(parsed.redirectUrl || ""),
      signinNameSha16: parsed.signinName ? sha16(parsed.signinName) : "",
      code: parsed.code || "",
    };
  }
  return out;
}

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

function pathOfUrl(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return "";
  }
}

function endpointOf(url) {
  try {
    const u = new URL(url);
    return `${u.host}${u.pathname}`;
  } catch {
    return String(url || "");
  }
}

function requestSummary(row) {
  return {
    line: row.lineNo,
    t: row.t ?? null,
    method: row.method,
    endpoint: endpointOf(row.url),
    postLen: row.post_len ?? 0,
    postSha16: row.post_data ? sha16(row.post_data) : "",
    headers: headerSummary(row.headers || {}),
    body: bodySummary(row.post_data || ""),
  };
}

function responseSummary(row) {
  return {
    line: row.lineNo,
    t: row.t ?? null,
    status: row.status,
    endpoint: endpointOf(row.url),
    bodyLen: row.body_len ?? 0,
    bodySha16: row.body ? sha16(row.body) : "",
    headers: headerSummary(row.headers || {}),
    body: bodySummary(row.body || ""),
  };
}

function extractRunMeta(rows) {
  const run = rows.find((x) => x.kind === "run.meta") || {};
  const evidence = rows.filter((x) => x.kind === "browser.evidence");
  const first = evidence[0] || {};
  const last = evidence[evidence.length - 1] || first;
  return {
    label: run.label || "",
    runtimeTrace: runtimePath,
    jsTrace: jsPath,
    proxy: {
      enabled: Boolean(run.meta?.proxy?.enabled),
      endpoint: run.meta?.proxy?.endpoint || "",
      endpointSha16: run.meta?.proxy?.endpoint_sha16 || "",
      hasAuth: Boolean(run.meta?.proxy?.has_auth),
      usernameLen: run.meta?.proxy?.username_len ?? null,
      usernameSha16: run.meta?.proxy?.username_sha16 || "",
      passwordLen: run.meta?.proxy?.password_len ?? null,
      passwordSha16: run.meta?.proxy?.password_sha16 || "",
    },
    camoufox: run.meta?.camoufox || {},
    geoip: Boolean(run.meta?.geoip),
    egress: evidence.map((row) => ({
      line: row.lineNo,
      label: row.label || "",
      t: row.t ?? null,
      ip: safeJson(row.egress?.body)?.ip || "",
    })),
    fingerprint: {
      timezone: (last.fingerprint || first.fingerprint || {}).timezone || "",
      language: (last.fingerprint || first.fingerprint || {}).language || "",
      platform: (last.fingerprint || first.fingerprint || {}).platform || "",
      webdriver: (last.fingerprint || first.fingerprint || {}).webdriver ?? null,
      userAgentSha16: (last.fingerprint || first.fingerprint || {}).userAgent
        ? sha16((last.fingerprint || first.fingerprint || {}).userAgent)
        : "",
    },
  };
}

function pairResponses(rows, predicate) {
  const reqs = rows.filter((row) => row.kind === "request" && predicate(row));
  const resps = rows.filter((row) => row.kind === "response" && predicate(row));
  return reqs.map((req) => {
    const res = resps.find((x) => x.lineNo > req.lineNo);
    return {
      request: requestSummary(req),
      response: res ? responseSummary(res) : null,
    };
  });
}

function extractCollectorBuckets(rows) {
  const requests = rows.filter((row) => row.kind === "collector.request.bucket");
  const responses = rows.filter((row) => row.kind === "collector.response.bucket");
  const bySeq = new Map();
  for (const row of requests) {
    bySeq.set(row.collector_seq_no, { request: row, response: null });
  }
  for (const row of responses) {
    const item = bySeq.get(row.collector_seq_no) || { request: null, response: null };
    item.response = row;
    bySeq.set(row.collector_seq_no, item);
  }
  return [...bySeq.entries()]
    .sort((a, b) => Number(a[0]) - Number(b[0]))
    .map(([seq, { request, response }]) => ({
      collectorSeq: seq,
      requestLine: request?.lineNo ?? null,
      responseLine: response?.lineNo ?? null,
      tRequest: request?.t ?? null,
      tResponse: response?.t ?? null,
      endpoint: request?.endpoint || response?.endpoint || "",
      secFetch: request?.sec_fetch || {},
      origin: request?.origin || "",
      refererHost: hostOf(request?.referer || ""),
      postLen: request?.post_len ?? null,
      formKeys: request?.form_keys || [],
      payload: request?.payload || tokenShape(""),
      fields: summarizeCollectorFields(request?.fields || {}),
      cookieBridgeAtRequest: request?.cookies || { names: [], px: {} },
      response: response ? {
        status: response.status,
        bodyLen: response.body_len,
        jsonKeys: response.json_keys || [],
        do: response.do ?? null,
        ob: response.ob || tokenShape(""),
        hasOb: Boolean(response.has_ob),
      } : null,
    }));
}

function summarizeCollectorFields(fields) {
  const out = {};
  for (const key of ["appId", "seq", "ft", "en", "rsc"]) {
    out[key] = fields[key] ?? "";
  }
  for (const key of ["uuid", "vid", "cts", "p1"]) {
    const obj = fields[key] || {};
    out[key] = {
      present: Boolean(obj.present),
      looksUuid: Boolean(obj.looks_uuid),
      len: obj.len ?? 0,
      sha16: obj.value ? sha16(obj.value) : "",
      value: key === "uuid" || key === "vid" ? obj.value || "" : undefined,
    };
  }
  for (const key of ["sid", "pc", "cs", "tag"]) {
    out[key] = fields[key] || tokenShape("");
  }
  return out;
}

function parseMessageData(row) {
  const raw = row.data?.data;
  const parsed = typeof raw === "string" ? safeJson(raw) : raw;
  if (!parsed || typeof parsed !== "object") return null;
  return parsed;
}

function extractMessages(jsRows) {
  return jsRows
    .filter((row) => row.kind === "window.message.recv")
    .map((row) => {
      const data = parseMessageData(row);
      return {
        line: row.lineNo,
        wall_t: row.wall_t ?? null,
        hrefHost: hostOf(row.href || ""),
        origin: row.origin || "",
        frameTop: Boolean(row.frameTop),
        eventOrigin: row.data?.eventOrigin || "",
        dataType: row.data?.dataType || "",
        type: data?.type || "",
        requestUrl: data?.requestUrl || "",
        cookie: data?.type === "cookie"
          ? { name: data.name || "", value: tokenShape(data.value), expiresPresent: Boolean(data.expires) }
          : null,
        jsonResponse: data?.jsonResponse
          ? {
              uuid: data.jsonResponse.uuid || "",
              vid: data.jsonResponse.vid || "",
            }
          : null,
      };
    });
}

function buildStateMachine(runtimeRows, jsRows, riskVerify, createAccount, messages, collectors) {
  const events = [];
  for (const pair of riskVerify) {
    const body = pair.response?.body?.human || pair.response?.body?.risk || {};
    if (body.challengeType === "HumanCaptcha") {
      events.push({
        state: "risk_verify_human_captcha",
        evidence: { requestLine: pair.request.line, responseLine: pair.response?.line },
        t: pair.response?.t ?? pair.request.t,
        appId: body.appId || "",
        uuid: body.uuid || "",
        vid: body.vid || "",
      });
    } else if (pair.response?.body?.risk?.state === "continue") {
      events.push({
        state: "risk_verify_continue",
        evidence: { requestLine: pair.request.line, responseLine: pair.response?.line },
        t: pair.response?.t ?? pair.request.t,
        continuationToken: pair.response.body.risk.continuationToken,
      });
    }
  }
  for (const msg of messages.filter((x) => ["block", "rendered", "succeeded"].includes(x.type))) {
    events.push({
      state: `message_${msg.type}`,
      evidence: { jsLine: msg.line },
      t: msg.wall_t,
      source: `${msg.eventOrigin} -> ${msg.origin}`,
      requestUrl: msg.requestUrl || "",
      jsonResponse: msg.jsonResponse || null,
    });
  }
  const cookieNamesSeen = [...new Set(messages.filter((x) => x.cookie).map((x) => x.cookie.name))];
  if (cookieNamesSeen.length) {
    const firstCookie = messages.find((x) => x.cookie);
    events.push({
      state: "cookie_bridge",
      evidence: { firstJsLine: firstCookie.line },
      t: firstCookie.wall_t,
      cookieNames: cookieNamesSeen,
    });
  }
  const successCollectors = collectors.filter((x) => x.endpoint === "/assets/js/bundle" && x.response?.hasOb);
  for (const c of successCollectors.slice(-3)) {
    events.push({
      state: "collector_challenge_bucket",
      evidence: { requestLine: c.requestLine, responseLine: c.responseLine },
      t: c.tResponse ?? c.tRequest,
      collectorSeq: c.collectorSeq,
      endpoint: c.endpoint,
      payloadLen: c.payload?.len ?? null,
      obLen: c.response?.ob?.len ?? null,
      obSha16: c.response?.ob?.sha16 || "",
    });
  }
  for (const pair of createAccount) {
    if (pair.response?.body?.createAccountResponse?.hasRedirectUrl) {
      events.push({
        state: "create_account_redirect",
        evidence: { requestLine: pair.request.line, responseLine: pair.response.line },
        t: pair.response.t,
        redirectHost: pair.response.body.createAccountResponse.redirectHost,
      });
    }
  }
  return events.sort((a, b) => Number(a.t || 0) - Number(b.t || 0));
}

function markdown(bundle) {
  const lines = [];
  lines.push("# HUMAN challenge replay bundle");
  lines.push("");
  lines.push(`generatedAt=${bundle.generatedAt}`);
  lines.push(`runtime=${bundle.sources.runtime}`);
  lines.push(`js=${bundle.sources.js}`);
  lines.push("");
  lines.push("## State machine");
  lines.push("");
  lines.push("| state | evidence | detail |");
  lines.push("|---|---|---|");
  for (const ev of bundle.stateMachine) {
    const evidence = Object.entries(ev.evidence || {}).map(([k, v]) => `${k}=${v}`).join(" ");
    const detail = [
      ev.collectorSeq ? `seq=${ev.collectorSeq}` : "",
      ev.endpoint || "",
      ev.appId ? `appId=${ev.appId}` : "",
      ev.uuid ? `uuid=${ev.uuid}` : "",
      ev.vid ? `vid=${ev.vid}` : "",
      ev.payloadLen ? `payloadLen=${ev.payloadLen}` : "",
      ev.obLen ? `obLen=${ev.obLen}` : "",
      ev.obSha16 ? `obSha16=${ev.obSha16}` : "",
      ev.redirectHost ? `redirectHost=${ev.redirectHost}` : "",
      ev.cookieNames ? `cookies=${ev.cookieNames.join(",")}` : "",
    ].filter(Boolean).join(" ");
    lines.push(`| ${ev.state} | ${evidence} | ${detail} |`);
  }
  lines.push("");
  lines.push("## Collector buckets");
  lines.push("");
  lines.push("| seq | request | response | endpoint | formSeq | rsc | payloadLen | payloadSha16 | obLen | obSha16 | cookies |");
  lines.push("|---:|---:|---:|---|---:|---:|---:|---|---:|---|---|");
  for (const c of bundle.collectorBuckets) {
    lines.push(`| ${c.collectorSeq} | ${c.requestLine ?? "-"} | ${c.responseLine ?? "-"} | ${c.endpoint} | ${c.fields.seq || "-"} | ${c.fields.rsc || "-"} | ${c.payload?.len ?? "-"} | ${c.payload?.sha16 || "-"} | ${c.response?.ob?.len ?? "-"} | ${c.response?.ob?.sha16 || "-"} | ${(c.cookieBridgeAtRequest?.names || []).join(",") || "-"} |`);
  }
  lines.push("");
  lines.push("## Replay boundary");
  lines.push("");
  lines.push("- Raw payload/token/password/canary/proxy credential values are not copied into this bundle; use the source traces for byte-exact replay if needed.");
  lines.push("- This bundle captures the minimal observable state machine: HumanCaptcha -> collector buckets/cookie bridge -> succeeded message -> risk continue -> CreateAccount redirect.");
  return lines.join("\n") + "\n";
}

const runtimeRows = parseJsonl(runtimePath);
const jsRows = parseJsonl(jsPath);
const riskVerify = pairResponses(runtimeRows, (row) => String(row.url || "").includes("/api/v1.0/risk/verify"));
const createAccount = pairResponses(runtimeRows, (row) => String(row.url || "").includes("/API/CreateAccount"));
const collectorBuckets = extractCollectorBuckets(runtimeRows);
const messages = extractMessages(jsRows);

const bundle = {
  generatedAt: new Date().toISOString(),
  sources: {
    runtime: runtimePath,
    js: jsPath,
  },
  runMeta: extractRunMeta(runtimeRows),
  riskVerify,
  createAccount,
  collectorBuckets,
  messages: messages.filter((x) => x.type || x.cookie),
  stateMachine: buildStateMachine(runtimeRows, jsRows, riskVerify, createAccount, messages, collectorBuckets),
  negativeSignals: {
    invasiveRewriteSeen: runtimeRows.some((x) => String(x.text || "").includes("invasive hsprotect JS rewrite enabled") || String(x.text || "").includes("hsprotect JS patched")),
    captchaCloseSeen: runtimeRows.some((x) => String(x.url || x.text || "").includes("captcha_close")),
    statusMinusOneSeen: runtimeRows.some((x) => String(x.url || x.text || "").includes("status=-1")),
    omDecodeObserved: jsRows.some((x) => x.kind === "hsprotect.main.om.decode"),
    otObserved: jsRows.some((x) => x.kind === "hsprotect.captcha.Ot.enter"),
  },
};

fs.mkdirSync(outDir, { recursive: true });
const label = path.basename(runtimePath).replace(/^runtime_trace_/, "").replace(/\.jsonl$/, "");
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(outDir, `human_replay_bundle_${label}_${stamp}.json`);
const mdPath = path.join(outDir, `human_replay_bundle_${label}_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(bundle, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(bundle), "utf8");
console.log(JSON.stringify({ jsonPath, mdPath }, null, 2));
