#!/usr/bin/env node
import fs from "fs";
import path from "path";
import {
  computePc,
  decodePayloadRaw,
  encodePayload,
  hsUt,
  sha16,
} from "./hsprotect_payload_codec.mjs";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

const dir = path.resolve(arg("--dir", "output/outlook_browser/js_static_analysis/payload_reverse/success_templates/zel89cqywfov_1780988664_line_305"));
const qi = arg("--qi", String(Date.now()));
const outPrefix = arg("--out-prefix", "request.fresh_qi");
const seqOverride = arg("--seq", "");
const rscOverride = arg("--rsc", "");
const ctsOverride = arg("--cts", "");
const freshCts = hasFlag("--fresh-cts");
const freshInternalTimestamps = hasFlag("--fresh-internal-timestamps");

function parseRawFormEntries(body) {
  return String(body || "").split("&").map((part) => {
    const idx = part.indexOf("=");
    const key = idx < 0 ? part : part.slice(0, idx);
    const rawValue = idx < 0 ? "" : part.slice(idx + 1);
    let decodedValue = rawValue;
    if (key !== "payload") {
      try {
        decodedValue = decodeURIComponent(rawValue.replace(/\+/g, " "));
      } catch {
        decodedValue = rawValue;
      }
    }
    return { key, rawValue, decodedValue };
  });
}

function formObject(entries) {
  const out = {};
  for (const entry of entries) out[entry.key] = entry.decodedValue;
  return out;
}

function updateRaw(entries, key, rawValue) {
  const entry = entries.find((item) => item.key === key);
  if (!entry) throw new Error(`form key not found: ${key}`);
  entry.rawValue = rawValue;
  entry.decodedValue = key === "payload" ? rawValue : rawValue;
}

function writeCurlConfig(template, bodyFile, id) {
  const headers = template.headers?.selected || {};
  const lines = [
    "http1.1",
    "compressed",
    "silent",
    "show-error",
    "request = \"POST\"",
    `url = "${String(template.methodUrl).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`,
    `dump-header = "${id}.headers"`,
    `output = "${id}.body"`,
    `data-binary = "@${bodyFile}"`,
  ];
  for (const [key, value] of Object.entries(headers)) {
    lines.push(`header = "${String(`${key}: ${value}`).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`);
  }
  if (!Object.keys(headers).some((key) => key.toLowerCase() === "content-type")) {
    lines.push("header = \"content-type: application/x-www-form-urlencoded\"");
  }
  const configPath = path.join(dir, `${id}.curl.private.conf`);
  fs.writeFileSync(configPath, `${lines.join("\n")}\n`, "utf8");
  fs.chmodSync(configPath, 0o600);
  return configPath;
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function isTimestampLikeNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return false;
  const abs = Math.abs(value);
  return (abs >= 1_500_000_000_000 && abs <= 2_200_000_000_000)
    || (abs >= 1_500_000_000 && abs <= 2_200_000_000);
}

function stringTimestampNumber(value) {
  if (typeof value !== "string" || !/^-?\d{10,17}$/.test(value)) return null;
  const n = Number(value);
  return isTimestampLikeNumber(n) ? n : null;
}

function shiftInternalTimestamps(value, oldBase, newBase, pathParts = [], mutations = []) {
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i += 1) {
      const child = value[i];
      if (isTimestampLikeNumber(child)) {
        const shifted = newBase + (child - oldBase);
        value[i] = shifted;
        mutations.push({ path: pathParts.concat(String(i)).join("."), fromSha16: sha16(String(child)), toSha16: sha16(String(shifted)), type: "number" });
      } else {
        const stringNumber = stringTimestampNumber(child);
        if (stringNumber !== null) {
          const shifted = String(newBase + (stringNumber - oldBase));
          value[i] = shifted;
          mutations.push({ path: pathParts.concat(String(i)).join("."), fromSha16: sha16(child), toSha16: sha16(shifted), type: "string" });
        } else {
          shiftInternalTimestamps(child, oldBase, newBase, pathParts.concat(String(i)), mutations);
        }
      }
    }
    return mutations;
  }
  if (!value || typeof value !== "object") return mutations;
  for (const [key, child] of Object.entries(value)) {
    if (isTimestampLikeNumber(child)) {
      const shifted = newBase + (child - oldBase);
      value[key] = shifted;
      mutations.push({ path: pathParts.concat(key).join("."), fromSha16: sha16(String(child)), toSha16: sha16(String(shifted)), type: "number" });
      continue;
    }
    const stringNumber = stringTimestampNumber(child);
    if (stringNumber !== null) {
      const shifted = String(newBase + (stringNumber - oldBase));
      value[key] = shifted;
      mutations.push({ path: pathParts.concat(key).join("."), fromSha16: sha16(child), toSha16: sha16(shifted), type: "string" });
      continue;
    }
    shiftInternalTimestamps(child, oldBase, newBase, pathParts.concat(key), mutations);
  }
  return mutations;
}

const bodyPath = path.join(dir, "request.body.private.txt");
const templatePath = path.join(dir, "template.sanitized.json");
const body = fs.readFileSync(bodyPath, "utf8");
const template = JSON.parse(fs.readFileSync(templatePath, "utf8"));
const entries = parseRawFormEntries(body);
const form = formObject(entries);
const decoded = decodePayloadRaw(form.payload || "", { cu: form.uuid || "" });
if (!decoded.ok) throw new Error(`decode failed: ${decoded.reason}`);

const activities = deepClone(decoded.activities);
const internalTimestampMutations = [];
const oldQiNumber = Number(decoded.qi);
const newQiNumber = Number(qi);
if (freshInternalTimestamps) {
  if (!Number.isFinite(oldQiNumber) || !Number.isFinite(newQiNumber)) {
    throw new Error(`cannot shift internal timestamps with non-numeric qi: old=${decoded.qi} new=${qi}`);
  }
  shiftInternalTimestamps(activities, oldQiNumber, newQiNumber, [], internalTimestampMutations);
}

const serialized = hsUt(activities);
const encoded = encodePayload(activities, { cu: form.uuid || "" }, qi);
const pc = computePc(serialized, form.uuid || "", form.tag || "", form.ft || "");

updateRaw(entries, "payload", encoded.payload);
updateRaw(entries, "pc", pc);
if (seqOverride) updateRaw(entries, "seq", seqOverride);
if (rscOverride) updateRaw(entries, "rsc", rscOverride);
if (ctsOverride) updateRaw(entries, "cts", ctsOverride);
else if (freshCts) updateRaw(entries, "cts", qi);

const outBody = entries.map((entry) => `${entry.key}=${entry.rawValue}`).join("&");
const bodyFile = `${outPrefix}.body.private.txt`;
const bodyOutPath = path.join(dir, bodyFile);
fs.writeFileSync(bodyOutPath, outBody, "utf8");
fs.chmodSync(bodyOutPath, 0o600);

const curlId = `${outPrefix}.full_headers_noproxy`;
const curlConfig = writeCurlConfig(template, bodyFile, curlId);
const mutatedForm = formObject(entries);
const checkDecoded = decodePayloadRaw(mutatedForm.payload || "", { cu: mutatedForm.uuid || "" });
const checkPc = computePc(checkDecoded.serialized || "", mutatedForm.uuid || "", mutatedForm.tag || "", mutatedForm.ft || "");

const report = {
  dir,
  generatedAt: new Date().toISOString(),
  sourceBody: {
    path: bodyPath,
    len: body.length,
    sha16: sha16(body),
  },
  outputBody: {
    path: bodyOutPath,
    len: outBody.length,
    sha16: sha16(outBody),
  },
  curlConfig,
  changes: {
    qiSha16Before: decoded.qiSha16,
    qiSha16After: sha16(qi),
    payloadSha16Before: sha16(form.payload || ""),
    payloadSha16After: sha16(mutatedForm.payload || ""),
    pcSha16Before: sha16(form.pc || ""),
    pcSha16After: sha16(mutatedForm.pc || ""),
    pcChanged: String(form.pc || "") !== String(mutatedForm.pc || ""),
    seqBefore: form.seq || "",
    seqAfter: mutatedForm.seq || "",
    rscBefore: form.rsc || "",
    rscAfter: mutatedForm.rsc || "",
    ctsBeforeSha16: sha16(form.cts || ""),
    ctsAfterSha16: sha16(mutatedForm.cts || ""),
    ctsChanged: String(form.cts || "") !== String(mutatedForm.cts || ""),
    internalTimestampMutationCount: internalTimestampMutations.length,
    internalTimestampMutations,
  },
  codecCheck: {
    ok: checkDecoded.ok,
    saltLen: checkDecoded.saltLen,
    qiSha16: checkDecoded.qiSha16,
    activityCount: checkDecoded.activities?.length || 0,
    activityTypes: (checkDecoded.activities || []).map((activity) => activity.t || ""),
    serializedSha16: checkDecoded.serializedSha16 || "",
    payloadSha16: sha16(mutatedForm.payload || ""),
    pcMatches: checkPc === mutatedForm.pc,
    pcSha16: sha16(checkPc),
  },
  expectedHistoricalGate: template.response?.decoded || null,
};

const reportPath = path.join(dir, `${outPrefix}.mutation_report.json`);
fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));
