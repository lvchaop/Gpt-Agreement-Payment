#!/usr/bin/env node
import fs from "fs";
import path from "path";
import crypto from "crypto";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function readJsonl(file) {
  const rows = [];
  const text = fs.readFileSync(file, "utf8");
  for (const [idx, line] of text.split(/\n/).entries()) {
    if (!line.trim()) continue;
    rows.push({ lineNo: idx + 1, ...JSON.parse(line) });
  }
  return rows;
}

function b64(s) {
  return Buffer.from(String(s), "utf8").toString("base64");
}

function xorString(s, key) {
  let out = "";
  for (let i = 0; i < s.length; i++) out += String.fromCharCode(key ^ s.charCodeAt(i));
  return out;
}

const jsonEscapes = {
  "\b": "\\b",
  "\t": "\\t",
  "\n": "\\n",
  "\f": "\\f",
  "\r": "\\r",
  "\v": "\\v",
  '"': '\\"',
  "\\": "\\\\",
};
const escapable = /[\\\"\u0000-\u001f\u007f-\u009f\u00ad\u0600-\u0604\u070f\u17b4\u17b5\u200c-\u200f\u2028-\u202f\u2060-\u206f\ufeff\ufff0-\uffff]/g;

function quoteString(value) {
  const s = String(value);
  escapable.lastIndex = 0;
  return `"${escapable.test(s) ? s.replace(escapable, (ch) => jsonEscapes[ch] || `\\u${(`0000${ch.charCodeAt(0).toString(16)}`).slice(-4)}`) : s}"`;
}

function ut(value) {
  if (value === undefined) return undefined;
  if (typeof value === "string") return quoteString(value);
  if (typeof value === "boolean") return String(value);
  if (typeof value === "number") {
    const s = String(value);
    return s === "NaN" || s === "Infinity" ? "null" : s;
  }
  if (typeof value === "function") return undefined;
  if (value === null || value instanceof RegExp) return "null";
  if (value instanceof Date) {
    return `"${value.getFullYear()}-${value.getMonth() + 1}-${value.getDate()}T${value.getHours()}:${value.getMinutes()}:${value.getSeconds()}.${value.getMilliseconds()}"`;
  }
  if (Array.isArray(value)) {
    const parts = ["["];
    for (let i = 0; i < value.length; i++) parts.push(ut(value[i]) || '"undefined"', ",");
    parts[parts.length > 1 ? parts.length - 1 : parts.length] = "]";
    return parts.join("");
  }
  const parts = ["{"];
  for (const key in value) {
    if (Object.prototype.hasOwnProperty.call(value, key) && value[key] !== undefined) {
      parts.push(quoteString(key), ":", ut(value[key]) || '"undefined"', ",");
    }
  }
  parts[parts.length > 1 ? parts.length - 1 : parts.length] = "}";
  return parts.join("");
}

function insertionPositions(text, limit, cu) {
  const h = xorString(b64(cu), 10);
  const positions = [];
  let max = -1;
  for (let p = 0; p < text.length; p++) {
    const m = Math.floor(p / h.length + 1);
    const g = p >= h.length ? p % h.length : p;
    const y = h.charCodeAt(g) * h.charCodeAt(m);
    if (y > max) max = y;
  }
  for (let b = 0; b < text.length; b++) {
    const i = Math.floor(b / h.length) + 1;
    const e = b % h.length;
    let s = h.charCodeAt(e) * h.charCodeAt(i);
    if (s >= limit) s = Math.floor(((s - 0) / (max - 0)) * (limit - 1 - 0) + 0);
    while (positions.indexOf(s) !== -1) s += 1;
    positions.push(s);
  }
  return positions.sort((a, b) => a - b);
}

function insertChars(chars, base, positions) {
  let out = "";
  let i = 0;
  const c = chars.split("");
  for (let u = 0; u < chars.length; u++) {
    out += base.substring(i, positions[u] - u - 1) + c[u];
    i = positions[u] - u - 1;
  }
  return out + base.substring(i);
}

function vs(activities, meta, observed = {}) {
  let a = activities.slice();
  const marker = markerFromQi(observed.qi);
  a = b64(xorString(ut(a), 50));
  const encodedMeta = marker;
  const positions = insertionPositions(encodedMeta, a.length, meta.cu);
  return insertChars(encodedMeta, a, positions);
}

function markerFromQi(qi) {
  const fallback = "1604064986000";
  const value = qi && String(qi) !== "undefined" ? String(qi) : fallback;
  return xorString(b64(value), 10);
}

function jt(text, key) {
  const digest = crypto.createHmac("md5", key).update(text, "utf8").digest("hex");
  let digits = "";
  let mods = "";
  for (let i = 0; i < digest.length; i++) {
    const ch = digest[i];
    const code = digest.charCodeAt(i);
    if (code >= 48 && code <= 57) digits += ch;
    else mods += String(code % 10);
  }
  const merged = digits + mods;
  let out = "";
  for (let i = 0; i < merged.length; i += 2) out += merged[i];
  return out;
}

function firstDiff(a, b) {
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) {
    if (a[i] !== b[i]) return { index: i, actual: a[i], expected: b[i], actualCode: a.charCodeAt(i), expectedCode: b.charCodeAt(i) };
  }
  if (a.length !== b.length) return { index: len, actual: a[len], expected: b[len], actualLen: a.length, expectedLen: b.length };
  return null;
}

function analyze(tracePath) {
  const rows = readJsonl(tracePath);
  const events = rows.filter((r) => r.kind === "hsprotect.main.tf.payload");
  return events.map((row) => {
    const d = row.data || {};
    const meta = d.meta || {};
    const serialized = ut(d.activities || []);
    const ft = String(d.ft || meta.ft || "369");
    const pcKey = [meta.cu || "", meta.tag || "", ft].join(":");
    const pcReplay = jt(serialized, pcKey);
    const replay = vs(d.activities || [], meta, d);
    const markerReplay = markerFromQi(d.qi);
    return {
      line: row.lineNo,
      observedPayloadLen: String(d.payload || "").length,
      replayPayloadLen: replay.length,
      payloadMatch: replay === d.payload,
      serializedMatch: serialized === d.serialized,
      firstDiff: firstDiff(replay, String(d.payload || "")),
      markerUsed: d.qi && String(d.qi) !== "undefined" ? "qi" : "static.Xs118",
      markerLen: String(d.marker || "").length,
      markerObserved: String(d.marker || ""),
      markerReplay,
      markerMatch: markerReplay === String(d.marker || ""),
      ft,
      pcKey,
      pcReplay,
      pcObserved: String(d.pc || meta.pc || ""),
      pcMatch: pcReplay === String(d.pc || meta.pc || ""),
      meta,
      replay,
      observed: d.payload,
    };
  });
}

function main() {
  const traces = process.argv.slice(2);
  if (!traces.length) {
    console.error("usage: node tools/replay_human_vs_payload.mjs <js_internal_trace.jsonl> [...]");
    process.exit(2);
  }
  const outDir = path.join(repo, "output/protocol_reverse/payload_replay");
  fs.mkdirSync(outDir, { recursive: true });
  const outputs = [];
  for (const trace of traces) {
    const result = analyze(trace);
    const base = path.basename(trace, ".jsonl").replace(/^js_internal_trace_/, "");
    const jsonPath = path.join(outDir, `vs_payload_replay_${base}.json`);
    fs.writeFileSync(jsonPath, JSON.stringify({ trace, result }, null, 2), "utf8");
    const md = [];
    md.push(`# Vs payload replay: ${base}`);
    md.push("");
    md.push("| line | serialized | marker | payload | pc | observed len | replay len | first diff |");
    md.push("|---:|---|---|---|---|---:|---:|---|");
    for (const row of result) {
      md.push(`| ${row.line} | ${row.serializedMatch} | ${row.markerMatch} | ${row.payloadMatch} | ${row.pcMatch} | ${row.observedPayloadLen} | ${row.replayPayloadLen} | ${row.firstDiff ? JSON.stringify(row.firstDiff) : ""} |`);
    }
    const mdPath = path.join(outDir, `vs_payload_replay_${base}.md`);
    fs.writeFileSync(mdPath, md.join("\n"), "utf8");
    outputs.push({
      trace,
      jsonPath,
      mdPath,
      eventCount: result.length,
      payloadMatches: result.filter((r) => r.payloadMatch).length,
      serializedMatches: result.filter((r) => r.serializedMatch).length,
      markerMatches: result.filter((r) => r.markerMatch).length,
      pcMatches: result.filter((r) => r.pcMatch).length,
    });
  }
  console.log(JSON.stringify(outputs, null, 2));
}

main();
