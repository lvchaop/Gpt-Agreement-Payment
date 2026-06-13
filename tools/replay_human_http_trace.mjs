#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";
import { decodeOb, runDecodedStateMachine } from "./hsprotect_ob_codec.mjs";

const repo = process.cwd();
const traceDir = path.join(repo, "output/outlook_browser");
const defaultRuntime = path.join(traceDir, "runtime_trace_ifkaruehjmec_1780995305.jsonl");
const outDir = path.join(traceDir, "human_http_replay");

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

const runtimePath = path.resolve(arg("--runtime", defaultRuntime));
const includeCreateAccount = hasFlag("--include-createaccount");
const writeRaw = !hasFlag("--no-raw");
const execute = hasFlag("--execute");

if (execute) {
  throw new Error("--execute is intentionally not implemented yet; this tool first emits an auditable curl replay plan.");
}

function sha16(value) {
  const s = typeof value === "string" ? value : JSON.stringify(value ?? "");
  if (!s) return "";
  return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
}

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

function safeJson(value) {
  try {
    return JSON.parse(String(value || ""));
  } catch {
    return null;
  }
}

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

function pathOf(url) {
  try {
    const u = new URL(url);
    return `${u.pathname}${u.search || ""}`;
  } catch {
    return String(url || "");
  }
}

function targetKind(row) {
  const url = String(row.url || "");
  if (url.includes("/api/v1.0/risk/initialize")) return "risk_initialize";
  if (url.includes("/api/v1.0/risk/verify")) return "risk_verify";
  if (url.includes("iframe.hsprotect.net/index.html")) return "iframe_index";
  if (url.includes("client.hsprotect.net/") && url.includes("main.min.js")) return "hsprotect_main_js";
  if (url.includes("captcha.hsprotect.net/") && url.includes("captcha.js")) return "hsprotect_captcha_js";
  if (url.includes("collector-pxzc5j78di.hsprotect.net/")) return "collector";
  if (url.includes("/API/CreateAccount")) return "create_account";
  return "";
}

function shouldReplay(row) {
  const kind = targetKind(row);
  if (!kind) return false;
  if (kind === "create_account" && !includeCreateAccount) return false;
  return true;
}

function pairResponses(rows, requestRow) {
  const sameUrl = rows.find((row) => (
    row.kind === "response"
    && row.lineNo > requestRow.lineNo
    && row.url === requestRow.url
  ));
  if (sameUrl) return sameUrl;
  const reqKind = targetKind(requestRow);
  return rows.find((row) => row.kind === "response" && row.lineNo > requestRow.lineNo && targetKind(row) === reqKind) || null;
}

function buildCollectorBucketIndex(rows) {
  const requests = rows.filter((row) => row.kind === "collector.request.bucket");
  const responses = rows.filter((row) => row.kind === "collector.response.bucket");
  const rawResponses = rows
    .filter((row) => row.kind === "response" && String(row.url || "").includes("collector-pxzc5j78di.hsprotect.net"))
    .map((row) => ({
      row,
      signal: bodySignal(row.body || ""),
    }));
  const responseBySeq = new Map();
  for (const response of responses) {
    const ob = response.ob || {};
    const raw = ob.sha16
      ? rawResponses.find((item) => item.signal.collectorOb?.obSha16 === ob.sha16 && item.signal.collectorOb?.obLen === ob.len)
      : null;
    responseBySeq.set(response.collector_seq_no, raw ? raw.row : {
      kind: "response",
      lineNo: response.lineNo,
      status: response.status,
      url: response.method_url || "",
      body_len: response.body_len || 0,
      body: "",
      bucketOnly: response,
    });
  }
  const out = new Map();
  for (const request of requests) {
    out.set(request.lineNo, responseBySeq.get(request.collector_seq_no) || null);
  }
  return out;
}

function redactHeaderValue(name, value) {
  const key = String(name || "").toLowerCase();
  const s = String(value || "");
  if (!s) return "";
  if (key === "proxy-authorization") return `<proxy-authorization sha16=${sha16(s)} len=${s.length}>`;
  if (key === "cookie") return summarizeCookieHeader(s);
  if (key === "canary") return `<canary sha16=${sha16(s)} len=${s.length}>`;
  return s;
}

function summarizeCookieHeader(value) {
  const names = String(value || "")
    .split(";")
    .map((x) => x.trim().split("=")[0])
    .filter(Boolean);
  return `<cookies ${names.join(",") || "none"} sha16=${sha16(value)} len=${String(value || "").length}>`;
}

function keptHeaders(headers = {}) {
  const drop = new Set([
    "host",
    "content-length",
    "connection",
    "accept-encoding",
    "proxy-authorization",
  ]);
  const kept = {};
  for (const [key, value] of Object.entries(headers || {})) {
    const lower = key.toLowerCase();
    if (drop.has(lower)) continue;
    kept[lower] = String(value);
  }
  return kept;
}

function sanitizedHeaders(headers = {}) {
  const out = {};
  for (const [key, value] of Object.entries(headers || {})) {
    out[key.toLowerCase()] = redactHeaderValue(key, value);
  }
  return out;
}

function bodySignal(body) {
  const text = String(body || "");
  const parsed = safeJson(text);
  const signal = {
    len: text.length,
    sha16: text ? sha16(text) : "",
    jsonKeys: parsed && typeof parsed === "object" ? Object.keys(parsed).sort() : [],
  };
  if (text.includes("HumanCaptcha")) signal.humanCaptcha = true;
  if (text.includes('"state":"continue"')) signal.riskContinue = true;
  if (text.includes("redirectUrl")) signal.redirectUrl = true;
  if (text.includes("riskBlock") || text.includes("AADSTS7005106")) signal.riskBlock = true;
  if (parsed?.challengeDetails || parsed?.challengeMetadata) {
    signal.challenge = {
      type: parsed.challengeDetails?.challengeType || "",
      appId: parsed.challengeMetadata?.appId || "",
      uuid: parsed.challengeMetadata?.uuid || parsed.challengeDetails?.uuid || "",
      vid: parsed.challengeMetadata?.vid || parsed.challengeDetails?.vid || "",
    };
  }
  if (parsed?.challengeSolution) {
    signal.challengeSolution = {
      type: parsed.challengeSolution.challengeType || "",
      px3Len: String(parsed.challengeSolution.px3 || "").length,
      pxdeLen: String(parsed.challengeSolution.pxde || "").length,
      pxvid: parsed.challengeSolution.pxvid || "",
    };
  }
  if (parsed?.ob) {
    const decoded = decodeOb(String(parsed.ob), 50);
    const sm = runDecodedStateMachine(decoded.parts);
    signal.collectorOb = {
      obLen: String(parsed.ob).length,
      obSha16: sha16(parsed.ob),
      partCount: decoded.parts.length,
      keys: [...new Set(decoded.parts.map((part) => String(part).split("|")[0]))],
      scores: decoded.parts
        .filter((part) => String(part).startsWith("IoIoIo|score|"))
        .map((part) => String(part).split("|")[2] || ""),
      hasOIIoIooo0: decoded.parts.some((part) => part === "oIIoIooo|0"),
      terminal: sm.state.terminal,
    };
  }
  return signal;
}

function bucketBodySignal(bucket) {
  const signal = {
    len: bucket?.body_len ?? 0,
    sha16: "",
    jsonKeys: bucket?.json_keys || [],
  };
  if (!bucket?.has_ob) return signal;
  signal.collectorOb = {
    obLen: bucket.ob?.len || 0,
    obSha16: bucket.ob?.sha16 || "",
    partCount: null,
    keys: [],
    scores: [],
    hasOIIoIooo0: false,
    terminal: "",
  };
  return signal;
}

function requestBodySignal(body) {
  const text = String(body || "");
  const parsed = safeJson(text);
  const signal = {
    len: text.length,
    sha16: text ? sha16(text) : "",
    jsonKeys: parsed && typeof parsed === "object" ? Object.keys(parsed).sort() : [],
  };
  if (parsed?.challengeSolution) {
    signal.challengeSolution = {
      type: parsed.challengeSolution.challengeType || "",
      px3Len: String(parsed.challengeSolution.px3 || "").length,
      pxdeLen: String(parsed.challengeSolution.pxde || "").length,
      pxvid: parsed.challengeSolution.pxvid || "",
    };
  }
  if (parsed?.ContinuationToken) {
    signal.continuationTokenLen = String(parsed.ContinuationToken).length;
  }
  if (text.startsWith("payload=")) {
    const params = new URLSearchParams(text);
    signal.formKeys = [...params.keys()].sort();
    signal.collector = {
      endpointFormSeq: params.get("seq") || "",
      rsc: params.get("rsc") || "",
      payloadLen: String(params.get("payload") || "").length,
      payloadSha16: sha16(params.get("payload") || ""),
      appId: params.get("appId") || "",
      uuidPresent: Boolean(params.get("uuid")),
      vidPresent: Boolean(params.get("vid")),
      csPresent: Boolean(params.get("cs")),
    };
  }
  return signal;
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function curlCommand(step, bodyFile) {
  const parts = ["curl", "--http1.1", "--compressed", "-sS", "-D", shellQuote(`${step.id}.headers`), "-o", shellQuote(`${step.id}.body`)];
  parts.push("-X", shellQuote(step.method));
  for (const [key, value] of Object.entries(step.replayHeaders)) {
    parts.push("-H", shellQuote(`${key}: ${value}`));
  }
  if (bodyFile) {
    parts.push("--data-binary", shellQuote(`@${bodyFile}`));
  }
  parts.push(shellQuote(step.url));
  return parts.join(" ");
}

function stepId(index, row) {
  const kind = targetKind(row);
  return `${String(index + 1).padStart(2, "0")}_${kind}_${row.lineNo}`;
}

function buildPlan(rows, baseDir) {
  const requests = rows.filter((row) => row.kind === "request" && shouldReplay(row));
  const collectorBucketsByRawLine = buildCollectorBucketIndex(rows);
  const steps = requests.map((row, index) => {
    const bucketLine = rows.find((candidate) => (
      candidate.kind === "collector.request.bucket"
      && candidate.lineNo >= row.lineNo
      && candidate.lineNo <= row.lineNo + 2
    ))?.lineNo;
    const response = bucketLine && String(row.url || "").includes("collector-pxzc5j78di.hsprotect.net")
      ? collectorBucketsByRawLine.get(bucketLine)
      : pairResponses(rows, row);
    const id = stepId(index, row);
    const rawBody = String(row.post_data || "");
    const bodyFile = rawBody ? `${id}.request.body` : "";
    return {
      id,
      kind: targetKind(row),
      source: {
        requestLine: row.lineNo,
        responseLine: response?.lineNo ?? null,
      },
      t: row.t ?? null,
      method: row.method || "GET",
      url: row.url,
      host: hostOf(row.url),
      path: pathOf(row.url),
      replayHeaders: keptHeaders(row.headers || {}),
      sanitizedHeaders: sanitizedHeaders(row.headers || {}),
      requestBody: requestBodySignal(rawBody),
      rawRequestBodyFile: bodyFile ? path.join(baseDir, bodyFile) : "",
      expected: response ? {
        status: response.status,
        body: response.bucketOnly ? bucketBodySignal(response.bucketOnly) : bodySignal(response.body || ""),
      } : null,
    };
  });
  return steps;
}

function writeRawArtifacts(steps, baseDir, rows) {
  fs.mkdirSync(baseDir, { recursive: true });
  for (const step of steps) {
    const req = rows.find((row) => row.lineNo === step.source.requestLine);
    const body = String(req?.post_data || "");
    if (!body) continue;
    fs.writeFileSync(step.rawRequestBodyFile, body, "utf8");
    fs.chmodSync(step.rawRequestBodyFile, 0o600);
  }
}

function writeCurlScript(steps, baseDir) {
  const lines = [];
  lines.push("#!/usr/bin/env bash");
  lines.push("set -euo pipefail");
  lines.push("");
  lines.push("# Generated from browser runtime trace. It intentionally omits proxy credentials.");
  lines.push("# If replaying through Webshare, export:");
  lines.push("#   export HTTPS_PROXY=http://USER:PASS@p.webshare.io:80");
  lines.push("#   export HTTP_PROXY=http://USER:PASS@p.webshare.io:80");
  lines.push("");
  lines.push("mkdir -p replay_responses");
  lines.push("cd replay_responses");
  lines.push("");
  for (const step of steps) {
    const relativeBody = step.rawRequestBodyFile ? path.relative(path.join(baseDir, "replay_responses"), step.rawRequestBodyFile) : "";
    lines.push(`echo '[${step.id}] ${step.method} ${step.host}${step.path}'`);
    lines.push(curlCommand(step, relativeBody));
    lines.push("");
  }
  const scriptPath = path.join(baseDir, "replay_with_curl.sh");
  fs.writeFileSync(scriptPath, lines.join("\n"), "utf8");
  fs.chmodSync(scriptPath, 0o700);
  return scriptPath;
}

function markdown(plan) {
  const lines = [];
  lines.push("# HUMAN HTTP replay plan");
  lines.push("");
  lines.push(`generatedAt=${plan.generatedAt}`);
  lines.push(`runtime=${plan.runtime}`);
  lines.push(`includeCreateAccount=${plan.includeCreateAccount}`);
  lines.push("");
  lines.push("## Steps");
  lines.push("");
  lines.push("| id | source | method | host/path | request signal | expected signal |");
  lines.push("|---|---|---|---|---|---|");
  for (const step of plan.steps) {
    const reqSignal = [
      step.requestBody.collector ? `collectorSeq=${step.requestBody.collector.endpointFormSeq}` : "",
      step.requestBody.collector ? `rsc=${step.requestBody.collector.rsc}` : "",
      step.requestBody.collector ? `payloadLen=${step.requestBody.collector.payloadLen}` : "",
      step.requestBody.challengeSolution ? `challengeSolution=${step.requestBody.challengeSolution.type}` : "",
      step.requestBody.challengeSolution ? `px3Len=${step.requestBody.challengeSolution.px3Len}` : "",
      step.requestBody.len ? `bodyLen=${step.requestBody.len}` : "",
    ].filter(Boolean).join(" ");
    const expected = [
      step.expected ? `status=${step.expected.status}` : "",
      step.expected?.body?.humanCaptcha ? "HumanCaptcha" : "",
      step.expected?.body?.riskContinue ? "state=continue" : "",
      step.expected?.body?.redirectUrl ? "redirectUrl" : "",
      step.expected?.body?.riskBlock ? "riskBlock" : "",
      step.expected?.body?.collectorOb ? `obLen=${step.expected.body.collectorOb.obLen}` : "",
      step.expected?.body?.collectorOb?.scores?.length ? `scores=${step.expected.body.collectorOb.scores.join(",")}` : "",
      step.expected?.body?.collectorOb?.hasOIIoIooo0 ? "oIIoIooo&#124;0" : "",
      step.expected?.body?.collectorOb?.terminal ? `terminal=${step.expected.body.collectorOb.terminal}` : "",
      step.expected?.body?.challenge?.uuid ? `uuid=${step.expected.body.challenge.uuid}` : "",
      step.expected?.body?.challenge?.vid ? `vid=${step.expected.body.challenge.vid}` : "",
    ].filter(Boolean).join(" ");
    lines.push(`| ${step.id} | req:${step.source.requestLine} res:${step.source.responseLine ?? "-"} | ${step.method} | ${step.host}${step.path} | ${reqSignal || "-"} | ${expected || "-"} |`);
  }
  lines.push("");
  lines.push("## Gate");
  lines.push("");
  lines.push("The first HTTP replay gate is `risk_verify` returning `state=continue`; `CreateAccount` is excluded unless `--include-createaccount` is passed.");
  lines.push("");
  lines.push("## Files");
  lines.push("");
  lines.push(`- rawPlan=${plan.rawPlanPath}`);
  lines.push(`- sanitizedPlan=${plan.sanitizedPlanPath}`);
  lines.push(`- curlScript=${plan.curlScriptPath}`);
  return lines.join("\n") + "\n";
}

function sanitizedPlan(plan) {
  return {
    ...plan,
    steps: plan.steps.map((step) => ({
      ...step,
      replayHeaders: undefined,
      rawRequestBodyFile: step.rawRequestBodyFile ? path.basename(step.rawRequestBodyFile) : "",
    })),
  };
}

const rows = parseJsonl(runtimePath);
const label = path.basename(runtimePath).replace(/^runtime_trace_/, "").replace(/\.jsonl$/, "");
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const baseDir = path.join(outDir, `human_http_replay_${label}_${stamp}`);
fs.mkdirSync(baseDir, { recursive: true });

const steps = buildPlan(rows, baseDir);
if (writeRaw) writeRawArtifacts(steps, baseDir, rows);
const curlScriptPath = writeCurlScript(steps, baseDir);
const rawPlanPath = path.join(baseDir, "raw_replay_plan.private.json");
const sanitizedPlanPath = path.join(baseDir, "sanitized_replay_plan.json");
const mdPath = path.join(baseDir, "README.md");
const plan = {
  generatedAt: new Date().toISOString(),
  runtime: runtimePath,
  includeCreateAccount,
  rawPlanPath,
  sanitizedPlanPath,
  curlScriptPath,
  stepCount: steps.length,
  steps,
};

fs.writeFileSync(rawPlanPath, JSON.stringify(plan, null, 2), "utf8");
fs.chmodSync(rawPlanPath, 0o600);
fs.writeFileSync(sanitizedPlanPath, JSON.stringify(sanitizedPlan(plan), null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(plan), "utf8");

console.log(JSON.stringify({
  stepCount: steps.length,
  mdPath,
  sanitizedPlanPath,
  rawPlanPath,
  curlScriptPath,
}, null, 2));
