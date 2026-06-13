#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";
import { decodePayloadRaw } from "./hsprotect_payload_codec.mjs";

const TRACE_DIR = "output/outlook_browser";
const OUT_DIR = "output/outlook_browser/js_static_analysis/payload_reverse";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const runtimePath = path.resolve(arg("--runtime", path.join(TRACE_DIR, "runtime_trace_zel89cqywfov_1780988664.jsonl")));
const leftLine = Number(arg("--left-line", "249"));
const rightLine = Number(arg("--right-line", "305"));

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
      } catch {
        return { lineNo, kind: "parse_error" };
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
    if (key === "payload") out[key] = value;
    else {
      try {
        out[key] = decodeURIComponent(value.replace(/\+/g, " "));
      } catch {
        out[key] = value;
      }
    }
  }
  return out;
}

function valueSummary(value) {
  if (value === undefined) return { present: false };
  if (value === null) return { present: true, type: "null" };
  if (Array.isArray(value)) return { present: true, type: "array", len: value.length, sha16: sha16(value) };
  if (typeof value === "object") return { present: true, type: "object", keys: Object.keys(value).sort(), sha16: sha16(value) };
  if (typeof value === "string") return { present: true, type: "string", len: value.length, parts: value.split(":").length, sha16: sha16(value) };
  return { present: true, type: typeof value, value };
}

function decodeRequest(row) {
  const form = parseRawForm(row.post_data || "");
  const decoded = decodePayloadRaw(form.payload || "", { cu: form.uuid || "" });
  if (!decoded.ok) throw new Error(`cannot decode payload at line ${row.lineNo}: ${decoded.reason}`);
  return {
    lineNo: row.lineNo,
    endpoint: safePath(row.url),
    form: {
      seq: form.seq || "",
      rsc: form.rsc || "",
      ft: form.ft || "",
      pcSha16: sha16(form.pc || ""),
      csSha16: sha16(form.cs || ""),
      payloadSha16: sha16(form.payload || ""),
      payloadLen: String(form.payload || "").length,
    },
    activities: decoded.activities,
    activityTypes: decoded.activities.map((activity) => activity.t || ""),
  };
}

function safePath(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return "";
  }
}

function byType(activities) {
  const out = new Map();
  for (const activity of activities) {
    const type = activity.t || "";
    if (!out.has(type)) out.set(type, []);
    out.get(type).push(activity);
  }
  return out;
}

function diffActivity(left, right) {
  const leftD = left?.d || {};
  const rightD = right?.d || {};
  const keys = [...new Set([...Object.keys(leftD), ...Object.keys(rightD)])].sort();
  const added = [];
  const removed = [];
  const changed = [];
  const same = [];
  for (const key of keys) {
    const l = leftD[key];
    const r = rightD[key];
    if (l === undefined) added.push({ key, right: valueSummary(r) });
    else if (r === undefined) removed.push({ key, left: valueSummary(l) });
    else if (JSON.stringify(l) !== JSON.stringify(r)) changed.push({ key, left: valueSummary(l), right: valueSummary(r) });
    else same.push(key);
  }
  return {
    leftKeyCount: Object.keys(leftD).length,
    rightKeyCount: Object.keys(rightD).length,
    added,
    removed,
    changed,
    sameCount: same.length,
  };
}

function buildReport(left, right) {
  const leftByType = byType(left.activities);
  const rightByType = byType(right.activities);
  const allTypes = [...new Set([...leftByType.keys(), ...rightByType.keys()])];
  const diffs = allTypes.map((type) => {
    const leftItems = leftByType.get(type) || [];
    const rightItems = rightByType.get(type) || [];
    return {
      type,
      leftCount: leftItems.length,
      rightCount: rightItems.length,
      pairs: Array.from({ length: Math.max(leftItems.length, rightItems.length) }, (_, idx) => ({
        index: idx,
        diff: diffActivity(leftItems[idx], rightItems[idx]),
      })),
    };
  });
  return {
    generatedAt: new Date().toISOString(),
    runtime: runtimePath,
    left,
    right,
    diffs,
  };
}

function markdown(report) {
  const lines = [];
  lines.push("# hsprotect activity diff");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push(`runtime=${report.runtime}`);
  lines.push("");
  lines.push("## Compared requests");
  lines.push("");
  lines.push("| side | line | endpoint | seq | rsc | payloadLen | payloadSha16 | pcSha16 | activity types |");
  lines.push("|---|---:|---|---:|---:|---:|---|---|---|");
  for (const [side, item] of [["left", report.left], ["right", report.right]]) {
    lines.push(`| ${side} | ${item.lineNo} | ${item.endpoint} | ${item.form.seq || "-"} | ${item.form.rsc || "-"} | ${item.form.payloadLen} | ${item.form.payloadSha16} | ${item.form.pcSha16} | ${item.activityTypes.join(",")} |`);
  }
  lines.push("");
  lines.push("## Activity diff summary");
  lines.push("");
  lines.push("| activity | left count | right count | pair | left keys | right keys | added | removed | changed | same |");
  lines.push("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|");
  for (const item of report.diffs) {
    for (const pair of item.pairs) {
      const d = pair.diff;
      lines.push(`| ${item.type} | ${item.leftCount} | ${item.rightCount} | ${pair.index} | ${d.leftKeyCount} | ${d.rightKeyCount} | ${d.added.length} | ${d.removed.length} | ${d.changed.length} | ${d.sameCount} |`);
    }
  }
  lines.push("");
  lines.push("## Changed field keys");
  for (const item of report.diffs) {
    for (const pair of item.pairs) {
      const d = pair.diff;
      lines.push("");
      lines.push(`### ${item.type} pair ${pair.index}`);
      lines.push("");
      lines.push(`- added: ${d.added.map((x) => x.key).join(",") || "-"}`);
      lines.push(`- removed: ${d.removed.map((x) => x.key).join(",") || "-"}`);
      lines.push(`- changed: ${d.changed.map((x) => x.key).join(",") || "-"}`);
    }
  }
  return `${lines.join("\n")}\n`;
}

const rows = readJsonl(runtimePath);
const left = decodeRequest(rows.find((row) => row.lineNo === leftLine));
const right = decodeRequest(rows.find((row) => row.lineNo === rightLine));
const report = buildReport(left, right);
fs.mkdirSync(OUT_DIR, { recursive: true });
const label = path.basename(runtimePath).replace(/^runtime_trace_/, "").replace(/\.jsonl$/, "");
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(OUT_DIR, `hsprotect_activity_diff_${label}_${leftLine}_vs_${rightLine}_${stamp}.json`);
const mdPath = path.join(OUT_DIR, `hsprotect_activity_diff_${label}_${leftLine}_vs_${rightLine}_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(report), "utf8");
console.log(JSON.stringify({ jsonPath, mdPath }, null, 2));
