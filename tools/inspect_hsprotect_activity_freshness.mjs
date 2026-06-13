#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { decodePayloadRaw, sha16 } from "./hsprotect_payload_codec.mjs";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const dir = path.resolve(arg("--dir", "output/outlook_browser/js_static_analysis/payload_reverse/success_templates/zel89cqywfov_1780988664_line_305"));
const outName = arg("--out", "activity_freshness_report.json");

function parseRawForm(body) {
  const out = {};
  for (const part of String(body || "").split("&")) {
    const idx = part.indexOf("=");
    if (idx < 0) continue;
    const key = part.slice(0, idx);
    const rawValue = part.slice(idx + 1);
    if (key === "payload") out[key] = rawValue;
    else {
      try {
        out[key] = decodeURIComponent(rawValue.replace(/\+/g, " "));
      } catch {
        out[key] = rawValue;
      }
    }
  }
  return out;
}

function walk(value, visit, pathParts = []) {
  visit(value, pathParts);
  if (Array.isArray(value)) {
    value.forEach((item, idx) => walk(item, visit, pathParts.concat(String(idx))));
  } else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) walk(child, visit, pathParts.concat(key));
  }
}

function primitiveShape(value) {
  if (value === null) return { type: "null" };
  if (Array.isArray(value)) return { type: "array", len: value.length, sha16: sha16(value) };
  if (value && typeof value === "object") return { type: "object", keys: Object.keys(value).length, sha16: sha16(value) };
  if (typeof value === "string") return { type: "string", len: value.length, parts: value.split(":").length, sha16: sha16(value) };
  return { type: typeof value, value };
}

function isTimestampLikeNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return false;
  const abs = Math.abs(value);
  return (abs >= 1_500_000_000_000 && abs <= 2_200_000_000_000)
    || (abs >= 1_500_000_000 && abs <= 2_200_000_000);
}

function stringNumber(value) {
  if (typeof value !== "string") return null;
  if (!/^-?\d{10,17}$/.test(value)) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function isTimestampLikeString(value) {
  const n = stringNumber(value);
  return n !== null && isTimestampLikeNumber(n);
}

function knownValueHits(value, form) {
  if (typeof value !== "string" || !value) return [];
  const hits = [];
  for (const key of ["uuid", "vid", "sid", "cs", "ci", "cts", "tag", "p1"]) {
    if (form[key] && value === form[key]) hits.push(key);
  }
  return hits;
}

const bodyPath = path.join(dir, "request.body.private.txt");
const templatePath = path.join(dir, "template.sanitized.json");
const body = fs.readFileSync(bodyPath, "utf8");
const template = fs.existsSync(templatePath) ? JSON.parse(fs.readFileSync(templatePath, "utf8")) : {};
const form = parseRawForm(body);
const decoded = decodePayloadRaw(form.payload || "", { cu: form.uuid || "" });
if (!decoded.ok) throw new Error(`decode failed: ${decoded.reason}`);

const activities = decoded.activities || [];
const timestampLike = [];
const knownMatches = [];
const largeArrays = [];
const tokenLikeStrings = [];
const primitiveCounts = {};

for (let activityIndex = 0; activityIndex < activities.length; activityIndex += 1) {
  const activity = activities[activityIndex];
  const activityType = activity?.t || "";
  walk(activity, (value, pathParts) => {
    const joinedPath = pathParts.join(".");
    const type = Array.isArray(value) ? "array" : value === null ? "null" : typeof value;
    primitiveCounts[type] = (primitiveCounts[type] || 0) + 1;
    if (isTimestampLikeNumber(value) || isTimestampLikeString(value)) {
      timestampLike.push({
        activityIndex,
        activityType,
        path: joinedPath,
        shape: primitiveShape(value),
      });
    }
    const hits = knownValueHits(value, form);
    if (hits.length) {
      knownMatches.push({
        activityIndex,
        activityType,
        path: joinedPath,
        matchedFormKeys: hits,
        shape: primitiveShape(value),
      });
    }
    if (Array.isArray(value) && value.length >= 20) {
      largeArrays.push({
        activityIndex,
        activityType,
        path: joinedPath,
        len: value.length,
        sha16: sha16(value),
        firstTypes: value.slice(0, 8).map((item) => Array.isArray(item) ? "array" : item === null ? "null" : typeof item),
      });
    }
    if (typeof value === "string" && (value.length >= 32 || value.split(":").length >= 3)) {
      tokenLikeStrings.push({
        activityIndex,
        activityType,
        path: joinedPath,
        len: value.length,
        parts: value.split(":").length,
        sha16: sha16(value),
      });
    }
  });
}

const report = {
  dir,
  generatedAt: new Date().toISOString(),
  source: {
    bodyLen: body.length,
    bodySha16: sha16(body),
    payloadLen: String(form.payload || "").length,
    payloadSha16: sha16(form.payload || ""),
    qiSha16: decoded.qiSha16,
    expectedGate: template.response?.decoded || null,
  },
  formShapes: Object.fromEntries(Object.entries(form).map(([key, value]) => [
    key,
    key === "payload"
      ? { rawLen: value.length, rawSha16: sha16(value) }
      : primitiveShape(value),
  ])),
  codec: {
    ok: decoded.ok,
    saltLen: decoded.saltLen,
    serializedSha16: decoded.serializedSha16,
    activityCount: activities.length,
    activityTypes: activities.map((activity) => activity.t || ""),
  },
  primitiveCounts,
  timestampLike,
  knownMatches,
  largeArrays,
  tokenLikeStrings,
};

const outPath = path.join(dir, outName);
fs.writeFileSync(outPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({
  outPath,
  activityCount: report.codec.activityCount,
  timestampLikeCount: timestampLike.length,
  knownMatchCount: knownMatches.length,
  largeArrayCount: largeArrays.length,
  tokenLikeStringCount: tokenLikeStrings.length,
}, null, 2));
