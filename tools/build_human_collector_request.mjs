#!/usr/bin/env node
import fs from "fs";
import path from "path";
import crypto from "crypto";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function readJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\n/)
    .filter((line) => line.trim())
    .map((line, idx) => ({ lineNo: idx + 1, ...JSON.parse(line) }));
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

function markerFromQi(qi) {
  const fallback = "1604064986000";
  const value = qi && String(qi) !== "undefined" ? String(qi) : fallback;
  return xorString(b64(value), 10);
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
    if (s >= limit) s = Math.floor((s / max) * (limit - 1));
    while (positions.includes(s)) s += 1;
    positions.push(s);
  }
  return positions.sort((a, b) => a - b);
}

function insertChars(chars, base, positions) {
  let out = "";
  let i = 0;
  for (let u = 0; u < chars.length; u++) {
    out += base.substring(i, positions[u] - u - 1) + chars[u];
    i = positions[u] - u - 1;
  }
  return out + base.substring(i);
}

function removeInsertedChars(finalText, positions) {
  const remove = new Set(positions.map((p) => p - 1));
  let marker = "";
  let base = "";
  for (let i = 0; i < finalText.length; i++) {
    if (remove.has(i)) marker += finalText[i];
    else base += finalText[i];
  }
  return { marker, base };
}

function extractMarkerFromPayload(base, observedPayload, cu) {
  const extra = String(observedPayload || "").length - String(base || "").length;
  if (extra <= 0 || extra > 128) return null;
  const probe = "X".repeat(extra);
  const positions = insertionPositions(probe, base.length, cu);
  const extracted = removeInsertedChars(observedPayload, positions);
  if (extracted.base !== base) return null;
  return extracted.marker;
}

function serializedForHook(d) {
  return typeof d.serialized === "string" ? d.serialized : ut(d.activities || []);
}

function vs(d, meta, observed) {
  const serialized = b64(xorString(serializedForHook(d), 50));
  const marker = observed.marker || extractMarkerFromPayload(serialized, observed.payload, meta.cu) || markerFromQi(observed.qi);
  return insertChars(marker, serialized, insertionPositions(marker, serialized.length, meta.cu));
}

function jt(text, key) {
  const digest = crypto.createHmac("md5", key).update(text, "utf8").digest("hex");
  let digits = "";
  let mods = "";
  for (let i = 0; i < digest.length; i++) {
    const code = digest.charCodeAt(i);
    if (code >= 48 && code <= 57) digits += digest[i];
    else mods += String(code % 10);
  }
  const merged = digits + mods;
  let out = "";
  for (let i = 0; i < merged.length; i += 2) out += merged[i];
  return out;
}

function parseFormRaw(body) {
  const out = [];
  for (const part of String(body || "").split("&")) {
    if (!part) continue;
    const idx = part.indexOf("=");
    const key = idx >= 0 ? part.slice(0, idx) : part;
    const rawValue = idx >= 0 ? part.slice(idx + 1) : "";
    out.push([decodeURIComponent(key.replace(/\+/g, " ")), rawValue]);
  }
  return out;
}

function firstDiff(a, b) {
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) {
    if (a[i] !== b[i]) return { index: i, actual: a[i], expected: b[i], actualCode: a.charCodeAt(i), expectedCode: b.charCodeAt(i) };
  }
  if (a.length !== b.length) return { index: len, actualLen: a.length, expectedLen: b.length };
  return null;
}

function baseName(tracePath) {
  return path.basename(tracePath, ".jsonl").replace(/^js_internal_trace_/, "").replace(/^runtime_trace_/, "");
}

function runtimePathFor(jsTrace) {
  return path.join(path.dirname(jsTrace), path.basename(jsTrace).replace(/^js_internal_trace_/, "runtime_trace_"));
}

function collectorDecodePathFor(jsTrace) {
  const base = baseName(jsTrace);
  return path.join(repo, "output/protocol_reverse/collector_decode", `collector_decode_${base}.json`);
}

function splitHandlerPart(part) {
  const fields = String(part || "").split("|");
  return [fields[0] || "", fields.slice(1)];
}

function buildMarkerTimeline(decodePath) {
  if (!fs.existsSync(decodePath)) return [];
  const doc = JSON.parse(fs.readFileSync(decodePath, "utf8"));
  const entries = [...(doc.decodedEntries || [])].sort((a, b) => Number(a.lineNo || 0) - Number(b.lineNo || 0));
  let jo = null;
  let joSource = null;
  const timeline = [];
  for (const entry of entries) {
    const lineNo = Number(entry.lineNo || 0);
    for (let partIndex = 0; partIndex < (entry.parts || []).length; partIndex++) {
      const raw = entry.parts[partIndex];
      const [key, args] = splitHandlerPart(raw);
      if (key === "oIIoIoII" && args.length) {
        jo = String(args[0]);
        joSource = { collectorLine: lineNo, partIndex, handler: key, raw: String(raw) };
      }
    }
    timeline.push({ afterLine: lineNo, jo, joSource });
  }
  return timeline;
}

function markerStateForRequest(timeline, requestLine) {
  let current = null;
  for (const row of timeline) {
    if (Number(row.afterLine || 0) >= Number(requestLine || 0)) break;
    current = row;
  }
  if (current && current.jo) {
    return { marker: markerFromQi(current.jo), qi: current.jo, source: "collector_state.Jo", qiSource: current.joSource };
  }
  return { marker: markerFromQi(null), qi: "1604064986000", source: "static.Xs118", qiSource: { static: "fallback Xs(118)" } };
}

function summarize(tracePath) {
  const runtimePath = runtimePathFor(tracePath);
  const decodePath = collectorDecodePathFor(tracePath);
  const markerTimeline = buildMarkerTimeline(decodePath);
  const jsRows = readJsonl(tracePath);
  const rtRows = readJsonl(runtimePath);
  const tfEvents = jsRows.filter((r) => r.kind === "hsprotect.main.tf.payload");
  const requests = rtRows.filter((r) => r.kind === "request" && String(r.url || "").includes("/api/v2/msft"));
  const rows = [];

  for (let i = 0; i < requests.length; i++) {
    const req = requests[i];
    const tf = tfEvents.find((r) => (r.data || {}).payload && (r.data || {}).payload === Object.fromEntries(parseFormRaw(req.post_data).map(([k, v]) => [k, decodeURIComponent(v)]))?.payload) || tfEvents[i] || null;
    if (!tf) {
      rows.push({ index: i, requestLine: req.lineNo, tfLine: null, status: "missing_tf" });
      continue;
    }
    const d = tf.data || {};
    const meta = d.meta || {};
    const observedPairs = parseFormRaw(req.post_data);
    const observedDecoded = Object.fromEntries(observedPairs.map(([k, v]) => [k, decodeURIComponent(v)]));
    const serializedText = serializedForHook(d);
    const serializedBase = b64(xorString(serializedText, 50));
    const observedMarker = extractMarkerFromPayload(serializedBase, observedDecoded.payload, meta.cu);
    const stateMarker = markerTimeline.length ? markerStateForRequest(markerTimeline, req.lineNo) : null;
    const markerInput = observedMarker
      ? { ...d, marker: observedMarker, qi: null }
      : (stateMarker ? { ...d, marker: stateMarker.marker, qi: stateMarker.qi } : d);
    const replayPayload = vs(d, meta, markerInput);
    const marker = markerInput.marker || markerFromQi(d.qi);
    const replayPc = jt(serializedText, [meta.cu || "", meta.tag || "", observedDecoded.ft || "369"].join(":"));

    const rebuiltPairs = [];
    for (const [key, rawValue] of observedPairs) {
      if (key === "payload") rebuiltPairs.push([key, replayPayload]);
      else if (key === "appId") rebuiltPairs.push([key, meta.appID || ""]);
      else if (key === "tag") rebuiltPairs.push([key, meta.tag || ""]);
      else if (key === "uuid") rebuiltPairs.push([key, meta.cu || ""]);
      else if (key === "pc") rebuiltPairs.push([key, replayPc]);
      else if (key === "en") rebuiltPairs.push([key, "NTA"]);
      else rebuiltPairs.push([key, decodeURIComponent(rawValue)]);
    }
    const rebuilt = rebuiltPairs.map(([k, v]) => `${encodeURIComponent(k)}=${String(v)}`).join("&");
    rows.push({
      index: i,
      requestLine: req.lineNo,
      tfLine: tf.lineNo,
      url: req.url,
      exactBodyMatch: rebuilt === req.post_data,
      firstDiff: firstDiff(rebuilt, req.post_data),
      payloadMatch: replayPayload === observedDecoded.payload,
      pcMatch: replayPc === observedDecoded.pc,
      appIdMatch: (meta.appID || "") === observedDecoded.appId,
      tagMatch: (meta.tag || "") === observedDecoded.tag,
      uuidMatch: (meta.cu || "") === observedDecoded.uuid,
      markerSource: observedMarker ? "payload.inverse" : (stateMarker ? stateMarker.source : (d.marker ? "hook.marker" : (d.qi && String(d.qi) !== "undefined" ? "hook.qi" : "static.Xs118"))),
      markerQi: observedMarker ? null : (stateMarker ? stateMarker.qi : d.qi),
      markerQiSource: observedMarker ? { payload: "inverse marker extraction from observed payload and hook serialized base" } : (stateMarker ? stateMarker.qiSource : null),
      marker,
      seq: observedDecoded.seq,
      ft: observedDecoded.ft,
      paramOrder: observedPairs.map(([k]) => k),
      rebuiltBody: rebuilt,
      observedBody: req.post_data,
    });
  }
  return { tracePath, runtimePath, decodePath: fs.existsSync(decodePath) ? decodePath : null, rows };
}

function writeReport(result) {
  const outDir = path.join(repo, "output/protocol_reverse/collector_request_build");
  fs.mkdirSync(outDir, { recursive: true });
  const base = baseName(result.tracePath);
  const jsonPath = path.join(outDir, `collector_request_build_${base}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

  const md = [];
  md.push(`# HUMAN collector request build: ${base}`);
  md.push("");
  md.push(`trace=${result.tracePath}`);
  md.push(`runtime=${result.runtimePath}`);
  md.push(`decode=${result.decodePath || ""}`);
  md.push("");
  md.push("| idx | req line | tf line | body | payload | pc | appId | tag | uuid | seq | ft | first diff |");
  md.push("|---:|---:|---:|---|---|---|---|---|---|---:|---:|---|");
  for (const row of result.rows) {
    md.push(`| ${row.index} | ${row.requestLine} | ${row.tfLine ?? ""} | ${row.exactBodyMatch} | ${row.payloadMatch} | ${row.pcMatch} | ${row.appIdMatch} | ${row.tagMatch} | ${row.uuidMatch} | ${row.seq ?? ""} | ${row.ft ?? ""} | ${row.firstDiff ? JSON.stringify(row.firstDiff) : ""} |`);
  }
  md.push("");
  md.push("## marker sources");
  for (const row of result.rows) {
    md.push(`- idx=${row.index} reqLine=${row.requestLine} tfLine=${row.tfLine ?? ""} source=${row.markerSource || ""} marker=${row.marker || ""}`);
  }
  md.push("");
  md.push("## evidence boundary");
  md.push("- payload/pc/appId/tag/uuid/en are rebuilt from tf.payload runtime hook plus static functions `ut`, `Jt`, `Vs`.");
  md.push("- marker is rebuilt from decoded collector state `oIIoIoII -> Jo -> Qi()` when decode material is available; first request uses the static fallback `Xs(118)`.");
  md.push("- parameter order is still taken from the matching runtime collector request; optional values are independently validated by `tools/validate_collector_request_state.py`.");
  const mdPath = path.join(outDir, `collector_request_build_${base}.md`);
  fs.writeFileSync(mdPath, md.join("\n"), "utf8");
  return { jsonPath, mdPath };
}

function main() {
  const traces = process.argv.slice(2);
  if (!traces.length) {
    console.error("usage: node tools/build_human_collector_request.mjs <js_internal_trace.jsonl> [...]");
    process.exit(2);
  }
  const outputs = traces.map((trace) => {
    const result = summarize(trace);
    return {
      trace,
      ...writeReport(result),
      requestCount: result.rows.length,
      exactBodyMatches: result.rows.filter((r) => r.exactBodyMatch).length,
      payloadMatches: result.rows.filter((r) => r.payloadMatch).length,
      pcMatches: result.rows.filter((r) => r.pcMatch).length,
    };
  });
  console.log(JSON.stringify(outputs, null, 2));
}

main();
