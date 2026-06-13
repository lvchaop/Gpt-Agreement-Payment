#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { sha16 } from "./hsprotect_payload_codec.mjs";
import { decodeOb, runDecodedStateMachine } from "./hsprotect_ob_codec.mjs";

const TRACE_DIR = "output/outlook_browser";
const OUT_DIR = "output/outlook_browser/js_static_analysis/activity_reverse";

const samples = [
  { label: "success_zel89cqywfov", outcome: "success", js: "js_internal_trace_zel89cqywfov_1780988665.jsonl", runtime: "runtime_trace_zel89cqywfov_1780988664.jsonl" },
  { label: "success_ni109xdjp5zp", outcome: "success", js: "js_internal_trace_ni109xdjp5zp_1780948211.jsonl", runtime: "runtime_trace_ni109xdjp5zp_1780948211.jsonl" },
  { label: "failure_hcxwyrtiudbg", outcome: "failure", js: "js_internal_trace_hcxwyrtiudbg_1780949301.jsonl", runtime: "runtime_trace_hcxwyrtiudbg_1780949301.jsonl" },
  { label: "rewrite_sample_k2y1qcudhaad", outcome: "failed_after_captcha_close_404", js: "js_internal_trace_k2y1qcudhaad_1780997358.jsonl", runtime: "runtime_trace_k2y1qcudhaad_1780997358.jsonl" },
].filter((s) => fs.existsSync(path.join(TRACE_DIR, s.js)));

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

function parseForm(body) {
  const out = {};
  for (const part of String(body || "").split("&")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const k = part.slice(0, idx);
    const v = part.slice(idx + 1);
    if (k === "payload") {
      out[k] = v;
      continue;
    }
    try {
      out[k] = decodeURIComponent(v.replace(/\+/g, " "));
    } catch {
      out[k] = v;
    }
  }
  return out;
}

function safeJson(value) {
  try {
    return JSON.parse(String(value || ""));
  } catch {
    return null;
  }
}

function runtimePayloadIndex(runtimeFile) {
  const rows = fs.existsSync(runtimeFile) ? readJsonl(runtimeFile) : [];
  const byPayload = new Map();
  const bySha = new Map();
  const buckets = [];
  const responseBySeq = new Map();
  const rawResponses = rows
    .filter((row) => row.kind === "response" && String(row.url || "").includes("collector-pxzc5j78di.hsprotect.net"))
    .map((row) => {
      const parsed = safeJson(row.body || "");
      const ob = parsed?.ob ? String(parsed.ob) : "";
      const decoded = ob ? decodeOb(ob, 50) : null;
      const stateMachine = decoded ? runDecodedStateMachine(decoded.parts) : null;
      return {
        lineNo: row.lineNo,
        status: row.status,
        obLen: ob.length,
        obSha16: sha16(ob),
        decoded: decoded ? {
          keys: [...new Set(decoded.parts.map((part) => String(part).split("|")[0]))],
          scores: decoded.parts.filter((part) => String(part).startsWith("IoIoIo|score|")).map((part) => String(part).split("|")[2] || ""),
          hasOIIoIooo0: decoded.parts.some((part) => part === "oIIoIooo|0"),
          terminal: stateMachine.state.terminal,
        } : null,
      };
    });
  for (const row of rows) {
    if (row.kind === "collector.response.bucket") {
      const raw = rawResponses.find((x) => x.lineNo < row.lineNo && x.obLen === (row.ob?.len || 0) && x.obSha16 === (row.ob?.sha16 || ""));
      responseBySeq.set(row.collector_seq_no, { ...row, decodedOb: raw?.decoded || null });
    }
  }
  for (const row of rows) {
    if (row.kind !== "request" || !row.post_data || !String(row.url || "").includes("collector-")) continue;
    const form = parseForm(row.post_data);
    if (!form.payload) continue;
    byPayload.set(form.payload, {
      lineNo: row.lineNo,
      url: row.url,
      endpoint: new URL(row.url).pathname,
      form,
      payloadSha16: sha16(form.payload),
      response: null,
    });
    bySha.set(sha16(form.payload), byPayload.get(form.payload));
  }
  for (const bucket of rows.filter((r) => r.kind === "collector.request.bucket")) {
    const payloadSha = bucket.payload?.sha16;
    const response = responseBySeq.get(bucket.collector_seq_no) || null;
    buckets.push({
      lineNo: bucket.lineNo,
      endpoint: bucket.endpoint,
      collectorSeq: bucket.collector_seq_no,
      formSeq: bucket.fields?.seq || "",
      rsc: bucket.fields?.rsc || "",
      payloadLen: bucket.payload?.len || 0,
      payloadSha16: payloadSha || "",
      response,
    });
    if (!payloadSha) continue;
    const match = [...byPayload.values()].find((x) => x.payloadSha16 === payloadSha);
    if (match) match.response = response;
  }
  return { byPayload, bySha, buckets };
}

function valueShape(value) {
  if (value === null) return { type: "null" };
  if (Array.isArray(value)) return { type: "array", len: value.length, sha16: sha16(value) };
  if (typeof value === "object") return { type: "object", keys: Object.keys(value).sort(), sha16: sha16(value) };
  if (typeof value === "string") return { type: "string", len: value.length, parts: value.split(":").length, sha16: sha16(value) };
  return { type: typeof value, value };
}

function summarizeActivity(activity) {
  const d = activity?.d || {};
  const keys = Object.keys(d).sort();
  return {
    type: activity?.t || "",
    keyCount: keys.length,
    keys,
    keySha16: sha16(keys.join(",")),
    fields: Object.fromEntries(keys.map((k) => [k, valueShape(d[k])])),
  };
}

function sampleSummary(sample) {
  const jsFile = path.join(TRACE_DIR, sample.js);
  const runtimeFile = path.join(TRACE_DIR, sample.runtime);
  const runtimeIndex = runtimePayloadIndex(runtimeFile);
  const rows = readJsonl(jsFile);
  const endpointCounts = new Map();
  function inferredEndpoint(activityTypes, href) {
    if (activityTypes.includes("W0cqQR4rLnA=") || (activityTypes.includes("GCQiLl1BJhk=") && String(href || "").includes("ch_ctx=1"))) {
      return "/b/c";
    }
    if (activityTypes.includes("RBB+WgJzc28=")) return "/api/v2/msft/beacon";
    return "/api/v2/msft";
  }
  function bucketFallback(activityTypes, href, payload) {
    const endpoint = inferredEndpoint(activityTypes, href);
    const nth = endpointCounts.get(endpoint) || 0;
    const candidates = runtimeIndex.buckets.filter((x) => x.endpoint === endpoint && x.payloadLen === String(payload || "").length);
    endpointCounts.set(endpoint, nth + 1);
    return candidates[nth] || candidates[0] || null;
  }
  const tfEvents = rows
    .filter((row) => row.kind === "hsprotect.main.tf.payload")
    .map((row) => {
      const data = row.data || {};
      const payload = data.payload || "";
      const activityTypes = (data.activities || []).map((a) => a.t);
      let runtime = runtimeIndex.byPayload.get(payload) || runtimeIndex.bySha.get(sha16(payload));
      if (!runtime || !runtime.response) {
        const fallback = bucketFallback(activityTypes, row.href, payload);
        if (fallback) runtime = fallback;
      }
      return {
        lineNo: row.lineNo,
        perf_t: row.perf_t,
        href: row.href,
        activityTypes,
        activityCount: (data.activities || []).length,
        activities: (data.activities || []).map(summarizeActivity),
        payloadLen: String(data.payload || "").length,
        payloadSha16: sha16(data.payload || ""),
        ft: data.ft || "",
        pc: data.pc || "",
        csPresent: Boolean(data.cs && data.cs !== "undefined"),
        csSha16: data.cs && data.cs !== "undefined" ? sha16(data.cs) : "",
        runtime: runtime ? {
          endpoint: runtime.endpoint,
          requestLine: runtime.lineNo,
          formSeq: runtime.form?.seq || runtime.formSeq || "",
          rsc: runtime.form?.rsc || runtime.rsc || "",
          responseLine: runtime.response?.lineNo || null,
          status: runtime.response?.status || null,
          obLen: runtime.response?.ob?.len || 0,
          obSha16: runtime.response?.ob?.sha16 || "",
          hasOb: Boolean(runtime.response?.has_ob),
          decoded: runtime.response?.decodedOb || null,
        } : null,
      };
    });
  return {
    label: sample.label,
    outcome: sample.outcome,
    source: { js: jsFile, runtime: runtimeFile },
    tfEvents,
  };
}

function aggregate(samplesOut) {
  const rows = [];
  for (const sample of samplesOut) {
    for (const event of sample.tfEvents) {
      rows.push({
        sample: sample.label,
        outcome: sample.outcome,
        lineNo: event.lineNo,
        endpoint: event.runtime?.endpoint || "",
        formSeq: event.runtime?.formSeq || "",
        rsc: event.runtime?.rsc || "",
        activityTypes: event.activityTypes.join(","),
        payloadLen: event.payloadLen,
        payloadSha16: event.payloadSha16,
        obLen: event.runtime?.obLen || 0,
        obSha16: event.runtime?.obSha16 || "",
        decodedTerminal: event.runtime?.decoded?.terminal || "",
        decodedHasOIIoIooo0: Boolean(event.runtime?.decoded?.hasOIIoIooo0),
        decodedScores: event.runtime?.decoded?.scores?.join(",") || "",
        csPresent: event.csPresent,
      });
    }
  }
  return rows;
}

function markdown(report) {
  const lines = [];
  lines.push("# hsprotect activity comparison");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push("");
  lines.push("## tf event table");
  lines.push("");
  lines.push("| sample | outcome | line | endpoint | seq | rsc | activity types | payloadLen | payloadSha16 | obLen | obSha16 | scores | oIIoIooo|0 | terminal | cs |");
  lines.push("|---|---|---:|---|---:|---:|---|---:|---|---:|---|---|---:|---|---:|");
  for (const row of report.aggregate) {
    lines.push(`| ${row.sample} | ${row.outcome} | ${row.lineNo} | ${row.endpoint || "-"} | ${row.formSeq || "-"} | ${row.rsc || "-"} | ${row.activityTypes || "-"} | ${row.payloadLen} | ${row.payloadSha16} | ${row.obLen} | ${row.obSha16 || "-"} | ${row.decodedScores || "-"} | ${row.decodedHasOIIoIooo0 ? "yes" : "no"} | ${row.decodedTerminal || "-"} | ${row.csPresent ? "yes" : "no"} |`);
  }
  lines.push("");
  lines.push("## Activity type/key signatures");
  lines.push("");
  lines.push("| sample | line | activity type | keyCount | keySha16 | selected field keys |");
  lines.push("|---|---:|---|---:|---|---|");
  for (const sample of report.samples) {
    for (const event of sample.tfEvents) {
      for (const activity of event.activities) {
        const selected = activity.keys.filter((k) => {
          const f = activity.fields[k];
          return f.type === "string" && (f.len > 80 || f.parts > 1) || f.type === "object" || f.type === "array";
        }).slice(0, 12);
        lines.push(`| ${sample.label} | ${event.lineNo} | ${activity.type} | ${activity.keyCount} | ${activity.keySha16} | ${selected.join(",") || "-"} |`);
      }
    }
  }
  return `${lines.join("\n")}\n`;
}

fs.mkdirSync(OUT_DIR, { recursive: true });
const report = {
  generatedAt: new Date().toISOString(),
  samples: samples.map(sampleSummary),
};
report.aggregate = aggregate(report.samples);
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(OUT_DIR, `hsprotect_activity_compare_${stamp}.json`);
const mdPath = path.join(OUT_DIR, `hsprotect_activity_compare_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2));
fs.writeFileSync(mdPath, markdown(report));
console.log(JSON.stringify({ jsonPath, mdPath, events: report.aggregate.length }, null, 2));
