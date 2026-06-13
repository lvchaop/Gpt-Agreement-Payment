#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";
import {
  computePc,
  decodePayloadRaw,
  encodePayload,
  sha16,
} from "./hsprotect_payload_codec.mjs";
import { decodeOb, runDecodedStateMachine } from "./hsprotect_ob_codec.mjs";

const TRACE_DIR = "output/outlook_browser";
const OUT_DIR = "output/outlook_browser/js_static_analysis/payload_reverse/success_templates";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const runtimePath = path.resolve(arg("--runtime", path.join(TRACE_DIR, "runtime_trace_zel89cqywfov_1780988664.jsonl")));
const requestLine = Number(arg("--request-line", "305"));

function hash(value) {
  const s = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return s ? crypto.createHash("sha256").update(s).digest("hex").slice(0, 16) : "";
}

function readJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .map((line, idx) => ({ line, lineNo: idx + 1 }))
    .filter((x) => x.line.trim())
    .map(({ line, lineNo }) => {
      try {
        return { lineNo, ...JSON.parse(line) };
      } catch {
        return { lineNo, kind: "parse_error" };
      }
    });
}

function parseRawForm(body) {
  const out = {};
  const raw = {};
  for (const part of String(body || "").split("&")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const key = part.slice(0, idx);
    const value = part.slice(idx + 1);
    raw[key] = value;
    if (key === "payload") out[key] = value;
    else {
      try {
        out[key] = decodeURIComponent(value.replace(/\+/g, " "));
      } catch {
        out[key] = value;
      }
    }
  }
  return { decoded: out, raw };
}

function safeJson(value) {
  try {
    return JSON.parse(String(value || ""));
  } catch {
    return null;
  }
}

function responseForRequest(rows, requestRow) {
  const bucket = rows.find((row) => row.kind === "collector.request.bucket" && Math.abs(row.lineNo - requestRow.lineNo) <= 2);
  const responseBucket = bucket
    ? rows.find((row) => row.kind === "collector.response.bucket" && row.collector_seq_no === bucket.collector_seq_no)
    : null;
  const rawResponse = responseBucket?.ob?.sha16
    ? rows.find((row) => {
        if (row.kind !== "response" || !String(row.url || "").includes("collector-pxzc5j78di.hsprotect.net")) return false;
        const ob = safeJson(row.body || "")?.ob || "";
        return ob.length === responseBucket.ob.len && hash(ob) === responseBucket.ob.sha16;
      })
    : null;
  return { bucket, responseBucket, rawResponse };
}

function decodedResponse(rawResponse) {
  const ob = safeJson(rawResponse?.body || "")?.ob || "";
  if (!ob) return null;
  const decoded = decodeOb(ob, 50);
  const sm = runDecodedStateMachine(decoded.parts);
  return {
    responseLine: rawResponse.lineNo,
    obLen: ob.length,
    obSha16: hash(ob),
    keys: [...new Set(decoded.parts.map((part) => String(part).split("|")[0]))],
    scores: decoded.parts.filter((part) => String(part).startsWith("IoIoIo|score|")).map((part) => String(part).split("|")[2] || ""),
    hasOIIoIooo0: decoded.parts.some((part) => part === "oIIoIooo|0"),
    terminal: sm.state.terminal,
  };
}

function valueShape(value) {
  if (value === undefined) return { present: false };
  if (value === null) return { present: true, type: "null" };
  if (Array.isArray(value)) return { present: true, type: "array", len: value.length, sha16: hash(value) };
  if (typeof value === "object") return { present: true, type: "object", keys: Object.keys(value).sort(), sha16: hash(value) };
  if (typeof value === "string") return { present: true, type: "string", len: value.length, parts: value.split(":").length, sha16: hash(value) };
  return { present: true, type: typeof value, value };
}

function activityTemplate(activities) {
  return activities.map((activity) => {
    const d = activity.d || {};
    const keys = Object.keys(d).sort();
    return {
      type: activity.t || "",
      keyCount: keys.length,
      keySha16: hash(keys.join(",")),
      fields: Object.fromEntries(keys.map((key) => [key, valueShape(d[key])])),
    };
  });
}

function buildTemplate(rows) {
  const request = rows.find((row) => row.lineNo === requestLine && row.kind === "request");
  if (!request) throw new Error(`request line not found: ${requestLine}`);
  const form = parseRawForm(request.post_data || "");
  const decoded = decodePayloadRaw(form.decoded.payload || "", { cu: form.decoded.uuid || "" });
  if (!decoded.ok) throw new Error(`payload decode failed: ${decoded.reason}`);
  const reencoded = encodePayload(decoded.activities, { cu: form.decoded.uuid || "" }, decoded.qi);
  const pc = computePc(decoded.serialized, form.decoded.uuid || "", form.decoded.tag || "", form.decoded.ft || "");
  const response = responseForRequest(rows, request);
  return {
    generatedAt: new Date().toISOString(),
    runtime: runtimePath,
    requestLine,
    endpoint: new URL(request.url).pathname,
    methodUrl: request.url,
    rawRequestBodySha16: hash(request.post_data || ""),
    rawRequestBodyLen: String(request.post_data || "").length,
    headers: {
      selected: Object.fromEntries(Object.entries(request.headers || {})
        .filter(([key]) => ["accept", "accept-language", "content-type", "origin", "referer", "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "user-agent"].includes(key.toLowerCase()))),
      cookiePresent: Boolean(request.headers?.cookie),
      cookieSha16: hash(request.headers?.cookie || ""),
      proxyAuthorizationPresent: Boolean(request.headers?.["proxy-authorization"]),
    },
    form: {
      keys: Object.keys(form.decoded).sort(),
      appId: form.decoded.appId || "",
      seq: form.decoded.seq || "",
      rsc: form.decoded.rsc || "",
      ft: form.decoded.ft || "",
      en: form.decoded.en || "",
      uuidSha16: hash(form.decoded.uuid || ""),
      vidSha16: hash(form.decoded.vid || ""),
      ctsSha16: hash(form.decoded.cts || ""),
      p1Sha16: hash(form.decoded.p1 || ""),
      sidSha16: hash(form.decoded.sid || ""),
      csSha16: hash(form.decoded.cs || ""),
      tagSha16: hash(form.decoded.tag || ""),
      pcSha16: hash(form.decoded.pc || ""),
      ciSha16: hash(form.decoded.ci || ""),
      rawPayloadLen: String(form.decoded.payload || "").length,
      rawPayloadSha16: hash(form.decoded.payload || ""),
      rawPayloadCaretCount: (String(form.decoded.payload || "").match(/\^/g) || []).length,
      rawPayloadPlusCount: (String(form.decoded.payload || "").match(/\+/g) || []).length,
    },
    codec: {
      saltLen: decoded.saltLen,
      qiSha16: decoded.qiSha16,
      serializedLen: decoded.serialized.length,
      serializedSha16: decoded.serializedSha16,
      activityCount: decoded.activities.length,
      activityTypes: decoded.activities.map((activity) => activity.t || ""),
      reencodedMatches: reencoded.payload === form.decoded.payload,
      pcMatches: pc === form.decoded.pc,
      pcSha16: hash(pc),
    },
    response: {
      requestBucketLine: response.bucket?.lineNo ?? null,
      collectorSeqNo: response.bucket?.collector_seq_no ?? null,
      responseBucketLine: response.responseBucket?.lineNo ?? null,
      rawResponseLine: response.rawResponse?.lineNo ?? null,
      decoded: decodedResponse(response.rawResponse),
    },
    activityTemplate: activityTemplate(decoded.activities),
  };
}

function markdown(template, relRawBody, relActivities) {
  const lines = [];
  lines.push("# hsprotect success request template");
  lines.push("");
  lines.push(`generatedAt=${template.generatedAt}`);
  lines.push(`runtime=${template.runtime}`);
  lines.push("");
  lines.push("## Request");
  lines.push("");
  lines.push(`- requestLine=${template.requestLine}`);
  lines.push(`- endpoint=${template.endpoint}`);
  lines.push(`- rawRequestBodyLen=${template.rawRequestBodyLen}`);
  lines.push(`- rawRequestBodySha16=${template.rawRequestBodySha16}`);
  lines.push(`- rawBody=${relRawBody}`);
  lines.push(`- activities=${relActivities}`);
  lines.push("");
  lines.push("## Form/codec");
  lines.push("");
  lines.push(`- seq=${template.form.seq}`);
  lines.push(`- rsc=${template.form.rsc}`);
  lines.push(`- ft=${template.form.ft}`);
  lines.push(`- rawPayloadLen=${template.form.rawPayloadLen}`);
  lines.push(`- rawPayloadSha16=${template.form.rawPayloadSha16}`);
  lines.push(`- saltLen=${template.codec.saltLen}`);
  lines.push(`- qiSha16=${template.codec.qiSha16}`);
  lines.push(`- activityTypes=${template.codec.activityTypes.join(",")}`);
  lines.push(`- reencodedMatches=${template.codec.reencodedMatches}`);
  lines.push(`- pcMatches=${template.codec.pcMatches}`);
  lines.push("");
  lines.push("## Expected collector gate");
  lines.push("");
  lines.push(`- collectorSeqNo=${template.response.collectorSeqNo}`);
  lines.push(`- rawResponseLine=${template.response.rawResponseLine}`);
  lines.push(`- obLen=${template.response.decoded?.obLen ?? ""}`);
  lines.push(`- obSha16=${template.response.decoded?.obSha16 ?? ""}`);
  lines.push(`- scores=${template.response.decoded?.scores?.join(",") || ""}`);
  lines.push(`- hasOIIoIooo0=${Boolean(template.response.decoded?.hasOIIoIooo0)}`);
  lines.push(`- terminal=${template.response.decoded?.terminal || ""}`);
  lines.push("");
  lines.push("## Activity field signatures");
  lines.push("");
  lines.push("| activity | keyCount | keySha16 |");
  lines.push("|---|---:|---|");
  for (const activity of template.activityTemplate) {
    lines.push(`| ${activity.type} | ${activity.keyCount} | ${activity.keySha16} |`);
  }
  return `${lines.join("\n")}\n`;
}

const rows = readJsonl(runtimePath);
const template = buildTemplate(rows);
const label = path.basename(runtimePath).replace(/^runtime_trace_/, "").replace(/\.jsonl$/, "");
const baseDir = path.join(OUT_DIR, `${label}_line_${requestLine}`);
fs.mkdirSync(baseDir, { recursive: true });

const requestRow = rows.find((row) => row.lineNo === requestLine);
const decodedForm = parseRawForm(requestRow.post_data || "").decoded;
const rawBodyPath = path.join(baseDir, "request.body.private.txt");
const activitiesPath = path.join(baseDir, "activities.private.json");
const templatePath = path.join(baseDir, "template.sanitized.json");
const mdPath = path.join(baseDir, "README.md");
fs.writeFileSync(rawBodyPath, requestRow.post_data || "", "utf8");
fs.chmodSync(rawBodyPath, 0o600);
const payloadDecoded = decodePayloadRaw(decodedForm.payload || "", { cu: decodedForm.uuid || "" });
fs.writeFileSync(activitiesPath, JSON.stringify(payloadDecoded.activities, null, 2), "utf8");
fs.chmodSync(activitiesPath, 0o600);
fs.writeFileSync(templatePath, JSON.stringify(template, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(template, path.basename(rawBodyPath), path.basename(activitiesPath)), "utf8");

console.log(JSON.stringify({
  baseDir,
  templatePath,
  mdPath,
  rawBodyPath,
  activitiesPath,
  reencodedMatches: template.codec.reencodedMatches,
  pcMatches: template.codec.pcMatches,
  gate: template.response.decoded?.terminal || "",
}, null, 2));
