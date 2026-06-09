#!/usr/bin/env node
import fs from "fs";
import path from "path";
import crypto from "crypto";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function readJsonl(file) {
  return fs.readFileSync(file, "utf8").split(/\n/).filter(Boolean).map((line, idx) => ({ lineNo: idx + 1, ...JSON.parse(line) }));
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

function insertionPositions(text, limit, cu) {
  const h = xorString(b64(cu), 10);
  const positions = [];
  let max = -1;
  for (let p = 0; p < text.length; p++) {
    const m = Math.floor(p / h.length + 1);
    const g = p >= h.length ? p % h.length : p;
    const y = h.charCodeAt(g) * h.charCodeAt(m);
    if (Number.isFinite(y) && y > max) max = y;
  }
  for (let b = 0; b < text.length; b++) {
    const i = Math.floor(b / h.length) + 1;
    const e = b % h.length;
    let s = h.charCodeAt(e) * h.charCodeAt(i);
    if (!Number.isFinite(s)) continue;
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

function markerFromQi(qi) {
  return xorString(b64(qi || "1604064986000"), 10);
}

function vs(activities, meta, marker) {
  const serialized = b64(xorString(ut(activities), 50));
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

function parseForm(body) {
  return String(body || "").split("&").filter(Boolean).map((part) => {
    const idx = part.indexOf("=");
    const k = idx >= 0 ? part.slice(0, idx) : part;
    const v = idx >= 0 ? part.slice(idx + 1) : "";
    return [decodeURIComponent(k.replace(/\+/g, " ")), decodeURIComponent(v.replace(/\+/g, " "))];
  });
}

function encodeForm(pairs) {
  return pairs.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join("&");
}

function liveStateFromProbe(file) {
  const doc = readJson(file);
  const state = {};
  for (const part of doc.decoded?.parts || []) {
    const [key, ...args] = String(part).split("|");
    if (key === "oIIoIoII") state.Jo = args[0];
    else if (key === "IIoIIo") state.sidBase = args[0];
    else if (key === "IooIoo") state.vid = args[0];
    else if (key === "oIIooIIo") state.cts = args[0];
    else if (key === "IoIIII") state.cs = args[0];
  }
  return state;
}

function patchActivities(activities, { liveState, oldSessionId, newSessionId, oldCu, nowMs }) {
  const out = JSON.parse(JSON.stringify(activities));
  const oldJo = "1780949314598";
  const walk = (obj) => {
    if (!obj || typeof obj !== "object") return;
    for (const key of Object.keys(obj)) {
      const val = obj[key];
      if (typeof val === "number" && val >= 1_600_000_000_000 && val <= 2_000_000_000_000) {
        obj[key] = nowMs;
      } else if (typeof val === "string") {
        if (val === oldJo && liveState.Jo) obj[key] = liveState.Jo;
        else if (oldSessionId && val.includes(oldSessionId)) obj[key] = val.replaceAll(oldSessionId, newSessionId || oldSessionId);
        else if (oldCu && val === oldCu) obj[key] = oldCu;
      } else if (val && typeof val === "object") {
        walk(val);
      }
    }
  };
  walk(out);
  return out;
}

function main() {
  const [tracePath, requestBuildPath, liveProbePath, indexArg] = process.argv.slice(2);
  if (!tracePath || !requestBuildPath || !liveProbePath) {
    console.error("usage: node tools/build_collector_body_with_activity_patch.mjs <js_trace> <request_build> <live_probe> [index=1]");
    process.exit(2);
  }
  const index = Number(indexArg || 1);
  const build = readJson(requestBuildPath);
  const row = build.rows[index];
  const tfLine = Number(row.tfLine);
  const tf = readJsonl(tracePath).find((r) => r.lineNo === tfLine);
  if (!tf) throw new Error(`tf line not found: ${tfLine}`);
  const d = tf.data || {};
  const oldPairs = parseForm(row.rebuiltBody || row.observedBody);
  const old = Object.fromEntries(oldPairs);
  const liveState = liveStateFromProbe(liveProbePath);
  const oldSessionId = String(old.p1 || "");
  const newSessionId = oldSessionId; // p1 is still tied to iframe URL; do not invent a new session without evidence.
  const nowMs = Date.now();
  const patchedActivities = patchActivities(d.activities || [], {
    liveState,
    oldSessionId,
    newSessionId,
    oldCu: d.meta?.cu,
    nowMs,
  });
  const meta = { ...(d.meta || {}), vid: liveState.vid || d.meta?.vid, cs: liveState.cs || d.meta?.cs };
  const marker = markerFromQi(liveState.Jo);
  const payload = vs(patchedActivities, meta, marker);
  const pc = jt(ut(patchedActivities), [meta.cu || "", meta.tag || "", old.ft || "369"].join(":"));
  const replacements = {
    payload,
    pc,
    cs: liveState.cs,
    sid: liveState.sidBase && liveState.Jo ? liveState.sidBase + [...String(liveState.Jo)].map((ch) => String.fromCodePoint(0xE0100 + ch.charCodeAt(0))).join("") : undefined,
    vid: liveState.vid,
    cts: liveState.cts,
  };
  const newPairs = oldPairs.map(([k, v]) => [k, replacements[k] ?? v]);
  const body = encodeForm(newPairs);
  const base = path.basename(tracePath, ".jsonl").replace(/^js_internal_trace_/, "");
  const requestKind = path.basename(requestBuildPath, ".json").startsWith("bc_collector_request_build_") ? "bc" : "api";
  const ts = Math.floor(Date.now() / 1000);
  const outDir = path.join(repo, "output/protocol_reverse/collector_activity_patch_body");
  fs.mkdirSync(outDir, { recursive: true });
  const out = {
    tracePath,
    requestBuildPath,
    liveProbePath,
    index,
    tfLine,
    liveState,
    nowMs,
    marker,
    pc,
    body,
    bodyLenBytes: Buffer.byteLength(body, "utf8"),
    bodySha256: crypto.createHash("sha256").update(body).digest("hex"),
    patchPolicy: "replace epoch_ms with nowMs; replace old Jo literal with live Jo; replace form cs/sid/vid/cts; keep p1/session_id unchanged",
    patchedActivityCount: patchedActivities.length,
  };
  const jsonPath = path.join(outDir, `collector_activity_patch_body_${requestKind}_${base}_idx${index}_${ts}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify(out, null, 2), "utf8");
  const mdPath = path.join(outDir, `collector_activity_patch_body_${requestKind}_${base}_idx${index}_${ts}.md`);
  fs.writeFileSync(mdPath, [
    `# collector activity patch body: ${base} idx=${index}`,
    "",
    `trace=${tracePath}`,
    `requestBuild=${requestBuildPath}`,
    `liveProbe=${liveProbePath}`,
    "",
    `- nowMs: ${nowMs}`,
    `- liveJo: ${liveState.Jo || ""}`,
    `- marker: ${marker}`,
    `- pc: ${pc}`,
    `- bodyLenBytes: ${out.bodyLenBytes}`,
    `- bodySha256: ${out.bodySha256}`,
    `- patchPolicy: ${out.patchPolicy}`,
    "",
  ].join("\n"), "utf8");
  console.log(JSON.stringify({ json: jsonPath, md: mdPath, bodyLenBytes: out.bodyLenBytes, marker, pc }, null, 2));
}

main();
