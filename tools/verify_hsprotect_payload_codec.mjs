#!/usr/bin/env node
import fs from "fs";
import path from "path";
import {
  computePc,
  decodePayload,
  encodePayload,
  hsUt,
  sha16,
} from "./hsprotect_payload_codec.mjs";

const TRACE_DIR = "output/outlook_browser";
const OUT_DIR = "output/outlook_browser/js_static_analysis/payload_reverse";

function readJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .map((line, index) => ({ line, lineNo: index + 1 }))
    .filter(({ line }) => line.trim())
    .map(({ line, lineNo }) => {
      try {
        return { lineNo, obj: JSON.parse(line) };
      } catch (error) {
        return { lineNo, parseError: error.message };
      }
    });
}

function collectTfEvents() {
  const runtimeByPayload = collectRuntimePosts();
  const files = fs.readdirSync(TRACE_DIR)
    .filter((name) => /^js_internal_trace_.*\.jsonl$/.test(name))
    .map((name) => path.join(TRACE_DIR, name));
  const rows = [];
  for (const file of files) {
    for (const row of readJsonl(file)) {
      const data = row.obj?.data;
      if (row.obj?.kind !== "hsprotect.main.tf.payload" || !data) continue;
      const serialized = hsUt(data.activities);
      const runtime = runtimeByPayload.get(data.payload || "");
      const ft = data.ft || runtime?.ft || "";
      const pc = ft
        ? computePc(serialized, data.meta?.cu || "", data.meta?.tag || "", ft)
        : "";
      const decoded = decodePayload(data.payload || "", data.activities || [], data.meta || {});
      let reencodedMatch = false;
      if (decoded.ok) {
        const reencoded = encodePayload(data.activities || [], data.meta || {}, decoded.qi);
        reencodedMatch = reencoded.payload === data.payload;
      }
      rows.push({
        file,
        lineNo: row.lineNo,
        href: row.obj.href,
        eventType: data.activities?.[0]?.t || "",
        activityCount: data.activities?.length || 0,
        serializedMatch: serialized === data.serialized,
        serializedSha16: sha16(serialized),
        recordedSerializedSha16: sha16(data.serialized || ""),
        payloadOk: decoded.ok,
        reencodedMatch,
        payloadLen: decoded.payloadLen,
        baseLen: decoded.baseLen,
        saltLen: decoded.saltLen,
        payloadSha16: decoded.payloadSha16,
        qiSha16: decoded.qiSha16,
        pcMatch: pc === data.pc,
        networkMatch: Boolean(runtime),
        network: runtime
          ? {
              file: runtime.file,
              lineNo: runtime.lineNo,
              url: runtime.url,
              ft: runtime.ft,
              seq: runtime.seq,
              postLen: runtime.postLen,
              recordedNetworkPc: runtime.pc,
              pcMatchesNetwork: Boolean(pc && pc === runtime.pc),
            }
          : null,
        pc,
        ft,
        recordedPc: data.pc || "",
        csPresent: Boolean(data.cs && data.cs !== "undefined"),
        meta: {
          appID: data.meta?.appID || "",
          tag: data.meta?.tag || "",
          cuSha16: data.meta?.cu ? sha16(data.meta.cu) : "",
          vidSha16: data.meta?.vid ? sha16(data.meta.vid) : "",
        },
      });
    }
  }
  return rows;
}

function collectRuntimePosts() {
  const files = fs.readdirSync(TRACE_DIR)
    .filter((name) => /^runtime_trace_.*\.jsonl$/.test(name))
    .map((name) => path.join(TRACE_DIR, name));
  const byPayload = new Map();
  for (const file of files) {
    for (const row of readJsonl(file)) {
      const obj = row.obj;
      if (obj?.kind !== "request" || !obj.post_data || !String(obj.url || "").includes("collector-")) continue;
      const params = parseFormBody(obj.post_data);
      if (!params.payload) continue;
      byPayload.set(params.payload, {
        file,
        lineNo: row.lineNo,
        url: obj.url,
        postLen: obj.post_len,
        payload: params.payload,
        ft: params.ft || "",
        seq: params.seq || "",
        pc: params.pc || "",
        csPresent: Boolean(params.cs),
      });
    }
  }
  return byPayload;
}

function parseFormBody(body) {
  const out = {};
  for (const part of String(body || "").split("&")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    const key = part.slice(0, idx);
    const value = part.slice(idx + 1);
    try {
      out[key] = decodeURIComponent(value.replace(/\+/g, " "));
    } catch {
      out[key] = value;
    }
  }
  return out;
}

function summarize(rows) {
  const byFile = new Map();
  for (const row of rows) {
    const key = path.basename(row.file);
    if (!byFile.has(key)) {
      byFile.set(key, { file: key, events: 0, serializedOk: 0, payloadOk: 0, reencodedOk: 0, pcOk: 0, payloadSamples: [] });
    }
    const entry = byFile.get(key);
    entry.events += 1;
    if (row.serializedMatch) entry.serializedOk += 1;
    if (row.payloadOk) entry.payloadOk += 1;
    if (row.reencodedMatch) entry.reencodedOk += 1;
    if (row.pcMatch) entry.pcOk += 1;
    if (entry.payloadSamples.length < 4) {
      entry.payloadSamples.push({
        lineNo: row.lineNo,
        eventType: row.eventType,
        payloadLen: row.payloadLen,
        saltLen: row.saltLen,
        payloadSha16: row.payloadSha16,
        pcMatch: row.pcMatch,
        networkMatch: row.networkMatch,
      });
    }
  }
  return [...byFile.values()].sort((a, b) => a.file.localeCompare(b.file));
}

function writeReport(rows, summary) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
  const jsonPath = path.join(OUT_DIR, `hsprotect_payload_codec_verify_${stamp}.json`);
  const mdPath = path.join(OUT_DIR, `hsprotect_payload_codec_verify_${stamp}.md`);
  const payloadOk = rows.filter((row) => row.payloadOk).length;
  const pcOk = rows.filter((row) => row.pcMatch).length;
  const serializedOk = rows.filter((row) => row.serializedMatch).length;

  fs.writeFileSync(jsonPath, JSON.stringify({ rows, summary }, null, 2));
  const lines = [
    "# HSPROTECT payload codec verification",
    "",
    `- generated: ${new Date().toISOString()}`,
    `- events: ${rows.length}`,
    `- serialized matches: ${serializedOk}/${rows.length}`,
    `- payload decoded/re-encoded matches: ${payloadOk}/${rows.length}`,
    `- pc matches: ${pcOk}/${rows.length}`,
    "",
    "## by trace",
    "",
  ];
  for (const item of summary) {
    lines.push(`- ${item.file}: events=${item.events} serialized=${item.serializedOk}/${item.events} payload=${item.payloadOk}/${item.events} reencode=${item.reencodedOk}/${item.events} pc=${item.pcOk}/${item.events}`);
    for (const sample of item.payloadSamples) {
      lines.push(`  - line ${sample.lineNo}: type=${sample.eventType} payloadLen=${sample.payloadLen} saltLen=${sample.saltLen} payloadSha16=${sample.payloadSha16} networkMatch=${sample.networkMatch} pcMatch=${sample.pcMatch}`);
    }
  }
  fs.writeFileSync(mdPath, `${lines.join("\n")}\n`);
  return { jsonPath, mdPath };
}

const rows = collectTfEvents();
const summary = summarize(rows);
const out = writeReport(rows, summary);
console.log(JSON.stringify({
  events: rows.length,
  serializedMatches: rows.filter((row) => row.serializedMatch).length,
  payloadMatches: rows.filter((row) => row.payloadOk && row.reencodedMatch).length,
  pcMatches: rows.filter((row) => row.pcMatch).length,
  mdPath: out.mdPath,
  jsonPath: out.jsonPath,
}, null, 2));
