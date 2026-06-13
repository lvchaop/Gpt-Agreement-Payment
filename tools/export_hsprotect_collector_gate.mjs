#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";
import { decodeOb, runDecodedStateMachine } from "./hsprotect_ob_codec.mjs";

const repo = process.cwd();
const traceDir = path.join(repo, "output/outlook_browser");
const outDir = path.join(traceDir, "js_static_analysis/protocol_reverse");

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const runtimePath = path.resolve(arg("--runtime", path.join(traceDir, "runtime_trace_zel89cqywfov_1780988664.jsonl")));

function sha16(value) {
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

function decodedObSummary(ob, row = {}) {
  const value = String(ob || "");
  if (!value) {
    return {
      lineNo: row.lineNo ?? null,
      status: row.status ?? null,
      hasOb: false,
      bodyLen: row.body_len ?? 0,
    };
  }
  const decoded = decodeOb(value, 50);
  const stateMachine = runDecodedStateMachine(decoded.parts);
  return {
    lineNo: row.lineNo ?? null,
    status: row.status ?? null,
    hasOb: true,
    bodyLen: row.body_len ?? 0,
    obLen: value.length,
    obSha16: sha16(value),
    decodedSha16: decoded.decodedSha16,
    partCount: decoded.parts.length,
    keys: [...new Set(decoded.parts.map((part) => String(part).split("|")[0]))],
    scores: decoded.parts.filter((part) => String(part).startsWith("IoIoIo|score|")).map((part) => String(part).split("|")[2] || ""),
    hasOIIoIooo0: decoded.parts.some((part) => part === "oIIoIooo|0"),
    terminal: stateMachine.state.terminal,
    stateMachine,
  };
}

function decodedResponse(row) {
  const parsed = safeJson(row.body || "");
  const ob = parsed?.ob ? String(parsed.ob) : "";
  return decodedObSummary(ob, row);
}

function responseAfter(rows, request) {
  return rows.find((row) => (
    row.kind === "response"
    && row.lineNo > request.lineNo
    && row.url === request.url
  )) || null;
}

function summarizeRequest(row) {
  const payload = row.payload || {};
  const fields = row.fields || {};
  return {
    lineNo: row.lineNo,
    collectorSeqNo: row.collector_seq_no,
    endpoint: row.endpoint,
    methodUrlHost: hostOf(row.method_url),
    postLen: row.post_len,
    payloadLen: payload.len || 0,
    payloadSha16: payload.sha16 || "",
    formSeq: fields.seq || "",
    rsc: fields.rsc || "",
    ft: fields.ft || "",
    appId: fields.appId || "",
    uuidPresent: Boolean(fields.uuid?.present),
    vidPresent: Boolean(fields.vid?.present),
    csPresent: Boolean(fields.cs?.present),
    pcSha16: fields.pc?.sha16 || "",
    tagSha16: fields.tag?.sha16 || "",
    cookieNames: row.cookies?.names || [],
  };
}

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

function buildReport(rows) {
  const rawRequests = rows.filter((row) => row.kind === "request" && String(row.url || "").includes("collector-pxzc5j78di.hsprotect.net"));
  const rawByLine = new Map(rawRequests.map((row) => [row.lineNo, row]));
  const rawResponses = rows
    .filter((row) => row.kind === "response" && String(row.url || "").includes("collector-pxzc5j78di.hsprotect.net"))
    .map((row) => {
      const decoded = decodedResponse(row);
      return { row, decoded };
    });
  const responseBuckets = new Map(rows
    .filter((row) => row.kind === "collector.response.bucket")
    .map((row) => [row.collector_seq_no, row]));
  const buckets = rows.filter((row) => row.kind === "collector.request.bucket").map((bucket) => {
    const raw = rawRequests.find((row) => {
      if (row.lineNo > bucket.lineNo) return false;
      const response = responseAfter(rows, row);
      return !response || response.lineNo >= bucket.lineNo;
    }) || rawByLine.get(bucket.lineNo - 1) || null;
    const responseBucket = responseBuckets.get(bucket.collector_seq_no) || null;
    const rawResponse = responseBucket?.has_ob
      ? rawResponses.find((item) => (
          item.decoded.hasOb
          && item.decoded.obLen === (responseBucket.ob?.len || 0)
          && item.decoded.obSha16 === (responseBucket.ob?.sha16 || "")
        ))
      : null;
    return {
      request: summarizeRequest(bucket),
      rawRequestLine: raw?.lineNo ?? null,
      response: responseBucket ? {
        ...(rawResponse?.decoded || {
          lineNo: responseBucket.lineNo,
          status: responseBucket.status,
          hasOb: Boolean(responseBucket.has_ob),
          bodyLen: responseBucket.body_len ?? 0,
          obLen: responseBucket.ob?.len || 0,
          obSha16: responseBucket.ob?.sha16 || "",
        }),
        bucketLineNo: responseBucket.lineNo,
      } : null,
      responseBucketLine: responseBucket?.lineNo ?? null,
    };
  });
  return {
    generatedAt: new Date().toISOString(),
    runtime: runtimePath,
    buckets,
    successBuckets: buckets.filter((bucket) => bucket.response?.hasOIIoIooo0),
    failedCallbackBuckets: buckets.filter((bucket) => bucket.response?.keys?.includes("oIIoIooo") && !bucket.response?.hasOIIoIooo0),
  };
}

function markdown(report) {
  const lines = [];
  lines.push("# hsprotect collector success gate");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push(`runtime=${report.runtime}`);
  lines.push("");
  lines.push("## Collector gate table");
  lines.push("");
  lines.push("| bucket | raw request | response | endpoint | formSeq | rsc | payloadLen | payloadSha16 | scores | callback | terminal | obLen | obSha16 |");
  lines.push("|---:|---:|---:|---|---:|---:|---:|---|---|---|---|---:|---|");
  for (const bucket of report.buckets) {
    const req = bucket.request;
    const res = bucket.response;
    const callback = res?.hasOIIoIooo0 ? "oIIoIooo|0" : (res?.keys || []).includes("oIIoIooo") ? "oIIoIooo|nonzero" : "-";
    lines.push(`| ${req.collectorSeqNo} | ${bucket.rawRequestLine ?? "-"} | ${res?.lineNo ?? "-"} | ${req.endpoint} | ${req.formSeq || "-"} | ${req.rsc || "-"} | ${req.payloadLen} | ${req.payloadSha16 || "-"} | ${res?.scores?.join(",") || "-"} | ${callback} | ${res?.terminal || "-"} | ${res?.obLen ?? "-"} | ${res?.obSha16 || "-"} |`);
  }
  lines.push("");
  lines.push("## Gate definition");
  lines.push("");
  lines.push("- success gate: decoded collector response contains exact part `oIIoIooo|0`.");
  lines.push("- local state transition: `oIIoIooo|0 -> Wc -> Ot(0) -> succeeded`.");
  lines.push("- non-success collector scores are not enough: observed `score=1` without `oIIoIooo|0` keeps terminal state `observed`.");
  return `${lines.join("\n")}\n`;
}

const rows = readJsonl(runtimePath);
const report = buildReport(rows);
fs.mkdirSync(outDir, { recursive: true });
const label = path.basename(runtimePath).replace(/^runtime_trace_/, "").replace(/\.jsonl$/, "");
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(outDir, `hsprotect_collector_gate_${label}_${stamp}.json`);
const mdPath = path.join(outDir, `hsprotect_collector_gate_${label}_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(report), "utf8");
console.log(JSON.stringify({
  jsonPath,
  mdPath,
  buckets: report.buckets.length,
  successBuckets: report.successBuckets.map((bucket) => bucket.request.collectorSeqNo),
}, null, 2));
