#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";
import { computePc, decodePayloadRaw, encodePayload } from "./hsprotect_payload_codec.mjs";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const dir = path.resolve(arg("--dir", "output/outlook_browser/js_static_analysis/payload_reverse/success_templates/zel89cqywfov_1780988664_line_305"));

function sha16(value) {
  const s = typeof value === "string" ? value : JSON.stringify(value ?? "");
  return s ? crypto.createHash("sha256").update(s).digest("hex").slice(0, 16) : "";
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

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

const bodyPath = path.join(dir, "request.body.private.txt");
const templatePath = path.join(dir, "template.sanitized.json");
const body = fs.readFileSync(bodyPath, "utf8");
const template = JSON.parse(fs.readFileSync(templatePath, "utf8"));
const form = parseRawForm(body);
const decoded = decodePayloadRaw(form.payload || "", { cu: form.uuid || "" });
if (!decoded.ok) throw new Error(`decode failed: ${decoded.reason}`);
const reencoded = encodePayload(decoded.activities, { cu: form.uuid || "" }, decoded.qi);
const pc = computePc(decoded.serialized, form.uuid || "", form.tag || "", form.ft || "");

const verified = {
  dir,
  bodyLen: body.length,
  bodySha16: sha16(body),
  expectedBodySha16: template.rawRequestBodySha16,
  payloadLen: String(form.payload || "").length,
  payloadSha16: sha16(form.payload || ""),
  expectedPayloadSha16: template.form.rawPayloadSha16,
  saltLen: decoded.saltLen,
  qiSha16: decoded.qiSha16,
  activityCount: decoded.activities.length,
  activityTypes: decoded.activities.map((activity) => activity.t || ""),
  serializedSha16: decoded.serializedSha16,
  reencodedMatches: reencoded.payload === form.payload,
  pcMatches: pc === form.pc,
  pcSha16: sha16(pc),
  expectedGate: template.response.decoded,
  curlOneShot: [
    "curl",
    "--http1.1",
    "--compressed",
    "-sS",
    "-D",
    shellQuote("collector.headers"),
    "-o",
    shellQuote("collector.body"),
    "-X",
    "POST",
    "-H",
    shellQuote("content-type: application/x-www-form-urlencoded"),
    "-H",
    shellQuote(`origin: ${template.headers.selected.origin || "https://iframe.hsprotect.net"}`),
    "-H",
    shellQuote(`referer: ${template.headers.selected.referer || "https://iframe.hsprotect.net/"}`),
    "--data-binary",
    shellQuote("@request.body.private.txt"),
    shellQuote(template.methodUrl),
  ].join(" "),
};

console.log(JSON.stringify(verified, null, 2));
