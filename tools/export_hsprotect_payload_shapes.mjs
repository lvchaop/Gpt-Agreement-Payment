#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";
import {
  computePc,
  decodePayloadRaw,
  encodePayload,
} from "./hsprotect_payload_codec.mjs";

const TRACE_DIR = "output/outlook_browser";
const OUT_DIR = "output/outlook_browser/js_static_analysis/payload_reverse";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const runtimePath = path.resolve(arg("--runtime", path.join(TRACE_DIR, "runtime_trace_zel89cqywfov_1780988664.jsonl")));
const linesArg = arg("--lines", "249,251,305,307");
const targetLines = linesArg.split(",").map((x) => Number(x.trim())).filter(Boolean);

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

function parseRawForm(body) {
  const out = {};
  for (const part of String(body || "").split("&")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const key = part.slice(0, idx);
    const value = part.slice(idx + 1);
    if (key === "payload") {
      out[key] = value;
    } else {
      try {
        out[key] = decodeURIComponent(value.replace(/\+/g, " "));
      } catch {
        out[key] = value;
      }
    }
  }
  return out;
}

function valueShape(value) {
  if (value === null) return { type: "null" };
  if (Array.isArray(value)) return { type: "array", len: value.length, sha16: sha16(value) };
  if (typeof value === "object") return { type: "object", keys: Object.keys(value || {}).sort(), sha16: sha16(value) };
  if (typeof value === "string") return { type: "string", len: value.length, parts: value.split(":").length, sha16: sha16(value) };
  return { type: typeof value, value };
}

function activityShape(activity) {
  const d = activity?.d || {};
  const keys = Object.keys(d).sort();
  return {
    type: activity?.t || "",
    keyCount: keys.length,
    keySha16: sha16(keys.join(",")),
    selectedFields: Object.fromEntries(keys
      .filter((key) => {
        const shape = valueShape(d[key]);
        return shape.type === "array" || shape.type === "object" || (shape.type === "string" && (shape.len > 80 || shape.parts > 1));
      })
      .slice(0, 20)
      .map((key) => [key, valueShape(d[key])])),
  };
}

function decodeRawPayloadShape(payload, form) {
  const decoded = decodePayloadRaw(payload, { cu: form.uuid || "" });
  if (!decoded.ok) return { decoded: false, reason: decoded.reason || "" };
  const reencoded = encodePayload(decoded.activities, { cu: form.uuid || "" }, decoded.qi || "");
  const pcFromDecoded = computePc(decoded.serialized, form.uuid || "", form.tag || "", form.ft || "");
  return {
    decoded: true,
    saltLen: decoded.saltLen,
    qiSha16: decoded.qiSha16,
    serializedLen: decoded.serialized.length,
    serializedSha16: decoded.serializedSha16,
    canonicalLen: decoded.serialized.length,
    canonicalSha16: decoded.canonicalSha16,
    canonicalMatchesSerialized: true,
    reencodedMatches: reencoded.payload === payload,
    pcFromDecodedSha16: sha16(pcFromDecoded),
    pcFromCanonicalSha16: sha16(pcFromDecoded),
    formPcSha16: sha16(form.pc || ""),
    pcFromDecodedMatches: pcFromDecoded === form.pc,
    pcFromCanonicalMatches: pcFromDecoded === form.pc,
    activityCount: decoded.activities.length,
    activityTypes: decoded.activities.map((activity) => activity.t || ""),
    activities: decoded.activities.map(activityShape),
  };
}

function analyzeRow(row) {
  const form = parseRawForm(row.post_data || "");
  const payload = form.payload || "";
  return {
    requestLine: row.lineNo,
    url: row.url,
    endpoint: safePath(row.url),
    postLen: row.post_len || String(row.post_data || "").length,
    form: {
      seq: form.seq || "",
      rsc: form.rsc || "",
      ft: form.ft || "",
      hasCs: Boolean(form.cs),
      csSha16: sha16(form.cs || ""),
      pcSha16: sha16(form.pc || ""),
      tagSha16: sha16(form.tag || ""),
      uuidSha16: sha16(form.uuid || ""),
      vidSha16: sha16(form.vid || ""),
    },
    payload: {
      rawLen: payload.length,
      rawSha16: sha16(payload),
      caretCount: (payload.match(/\^/g) || []).length,
      plusCount: (payload.match(/\+/g) || []).length,
      equalsCount: (payload.match(/=/g) || []).length,
    },
    decode: decodeRawPayloadShape(payload, form),
  };
}

function safePath(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return "";
  }
}

function markdown(report) {
  const lines = [];
  lines.push("# hsprotect raw payload shape export");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push(`runtime=${report.runtime}`);
  lines.push("");
  lines.push("## Request payload table");
  lines.push("");
  lines.push("| line | endpoint | seq | rsc | rawLen | rawSha16 | caret | plus | decoded | saltLen | activities | types | canonical | reencode | pc decoded | pc canonical |");
  lines.push("|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|");
  for (const row of report.rows) {
    lines.push(`| ${row.requestLine} | ${row.endpoint} | ${row.form.seq || "-"} | ${row.form.rsc || "-"} | ${row.payload.rawLen} | ${row.payload.rawSha16} | ${row.payload.caretCount} | ${row.payload.plusCount} | ${row.decode.decoded ? "yes" : "no"} | ${row.decode.saltLen ?? "-"} | ${row.decode.activityCount ?? "-"} | ${row.decode.activityTypes?.join(",") || "-"} | ${row.decode.canonicalMatchesSerialized ? "yes" : "no"} | ${row.decode.reencodedMatches ? "yes" : "no"} | ${row.decode.pcFromDecodedMatches ? "yes" : "no"} | ${row.decode.pcFromCanonicalMatches ? "yes" : "no"} |`);
  }
  lines.push("");
  lines.push("## Activity field signatures");
  lines.push("");
  lines.push("| line | activity | keyCount | keySha16 | selected field keys |");
  lines.push("|---:|---|---:|---|---|");
  for (const row of report.rows) {
    for (const activity of row.decode.activities || []) {
      lines.push(`| ${row.requestLine} | ${activity.type} | ${activity.keyCount} | ${activity.keySha16} | ${Object.keys(activity.selectedFields).join(",") || "-"} |`);
    }
  }
  lines.push("");
  lines.push("## Evidence notes");
  lines.push("");
  lines.push("- Raw payload must be parsed from the form body without URLSearchParams/parse_qsl `+` to space conversion.");
  lines.push("- `reencode=yes` and `pc=yes` are required before treating an offline-decoded activity list as byte-exact.");
  lines.push("- Payload base64 must be decoded with the same UTF-8 semantics as `J(ne(ut(a), 50))`; binary-string decoding corrupts non-ASCII plugin/name fields.");
  return `${lines.join("\n")}\n`;
}

const rows = readJsonl(runtimePath).filter((row) => targetLines.includes(row.lineNo));
const report = {
  generatedAt: new Date().toISOString(),
  runtime: runtimePath,
  rows: rows.map(analyzeRow),
};
fs.mkdirSync(OUT_DIR, { recursive: true });
const label = path.basename(runtimePath).replace(/^runtime_trace_/, "").replace(/\.jsonl$/, "");
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(OUT_DIR, `hsprotect_payload_shapes_${label}_${stamp}.json`);
const mdPath = path.join(OUT_DIR, `hsprotect_payload_shapes_${label}_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(report), "utf8");
console.log(JSON.stringify({ jsonPath, mdPath, rows: report.rows.length }, null, 2));
