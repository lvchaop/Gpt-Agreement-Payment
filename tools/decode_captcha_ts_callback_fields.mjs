#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const sourcePath = process.argv[2] || "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js";
const outDir = process.argv[3] || "output/protocol_reverse/source_offsets";
const label = process.argv[4] || "captcha_ts_callback_fields";

const source = fs.readFileSync(sourcePath, "utf8");
const lineNo = 1724;
const line = source.split(/\r?\n/)[lineNo - 1];

function globalU(encoded) {
  const key = "W6ypnhT";
  const padded = encoded + "=".repeat((4 - encoded.length % 4) % 4);
  const buf = Buffer.from(padded, "base64");
  let out = "";
  for (let i = 0; i < buf.length; i++) out += String.fromCharCode(buf[i] ^ key.charCodeAt(i % key.length));
  return out;
}

function evalDecoder(startNeedle, endNeedle, returnExpr) {
  const start = line.indexOf(startNeedle);
  const end = line.indexOf(endNeedle, start);
  if (start < 0 || end < 0) throw new Error(`cannot locate decoder block ${startNeedle} -> ${endNeedle}`);
  const code = line.slice(start, end);
  return { start, end, api: Function(`${code}; return ${returnExpr};`)() };
}

const fsDecoder = evalDecoder("function Vs(r,n){return Fs", "function _s()", "{ Vs, Fs, Ss }");
const lzDecoder = evalDecoder("function lz(r,n){var u=Az()", "var gz", "{ Hz }");
const { Vs } = fsDecoder.api;
const { Hz } = lzDecoder.api;

function cIz(r, n) {
  // Iz local: function c(r,n){ return Hz(r, n - 193) }
  return Hz(r, n - 193);
}

function dK(r, n) {
  // D local: function K(r,n){ return c(r, n - -1147) }
  return cIz(r, n - -1147);
}

function tsV(r, n) {
  // Ts inner: function v(r,n){ return Vs(n, r - -148) }
  return Vs(n, r - -148);
}

function tsC(r, n) {
  // Ts callback c(): function c(r,n){ return K(n, r - 597) }
  return dK(n, r - 597);
}

function rec(expr, raw, valueExpr, lineRef) {
  let decoded = null;
  let error = null;
  try {
    decoded = globalU(raw);
  } catch (e) {
    error = String(e && e.stack || e);
  }
  return { expr, raw, decoded, error, valueExpr, lineRef };
}

const records = [
  rec("r[t(v(-540,-543))] = _s()", tsV(-540, -543), "_s() boolean", "captcha.beautified.js:11083"),
  rec("r[t(v(-531,-522))] = Rs", tsV(-531, -522), "Rs", "captcha.beautified.js:11083"),
  rec('r[t("FnM4CCwDASRmEyFT")] = Ws[t("Ng")]()', "FnM4CCwDASRmEyFT", "Ws[Ng]()", "captcha.beautified.js:11085"),
  rec("r[t(v(-541,-541))] = Ws[t(\"NQ\")](n)", tsV(-541, -541), "Ws[NQ](n)", "captcha.beautified.js:11088"),
  rec("r[f(c(410,395))] = v", tsC(410, 395), "Ts callback param v", "captcha.beautified.js:11097"),
  rec("r[f(c(414,426))] = e", tsC(414, 426), "Ts callback param e", "captcha.beautified.js:11097"),
  rec('r[f("D2csAy8QPCd9EyVT")] = parseInt(m() - t)', "D2csAy8QPCd9EyVT", "elapsed parseInt(m() - t)", "captcha.beautified.js:11097"),
  rec("r[f(c(411,413))] = n", tsC(411, 413), "Ts callback param n", "captcha.beautified.js:11097"),
  rec("r[f(c(429,410))] = os", tsC(429, 410), "os", "captcha.beautified.js:11098"),
  rec('r[f("B25IQlhZYw")] = ws', "B25IQlhZYw", "ws", "captcha.beautified.js:11098"),
  rec("r[f(c(415,422))] = Ks", tsC(415, 422), "Ks", "captcha.beautified.js:11098"),
  rec("i(f(c(439,441)), r)", tsC(439, 441), "activity type passed to Ou() callback", "captcha.beautified.js:11098"),
  rec("window[L][f(c(413,425))](z)", tsC(413, 425), "post-submit window handler call", "captcha.beautified.js:11098"),
  rec('window[L][f("B25ORlo")] = Ot', "B25ORlo", "Ot callback slot", "captcha.beautified.js:11099"),
];

fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `${label}.json`);
const mdPath = path.join(outDir, `${label}.md`);
fs.writeFileSync(jsonPath, JSON.stringify({ source: sourcePath, line: lineNo, records }, null, 2));

const lines = [
  `# Captcha Ts callback fields: ${label}`,
  "",
  `- source: \`${sourcePath}\``,
  `- source line: \`${lineNo}\``,
  "- beautified evidence: `output/outlook_browser/js_static_analysis/captcha.beautified.js:11083-11099`",
  `- json: \`${jsonPath}\``,
  "",
  "| expression | raw | decoded | value expression | source |",
  "|---|---|---|---|---|",
];
for (const r of records) {
  lines.push(`| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded || ""}\` | ${r.valueExpr} | ${r.lineRef} |`);
}
fs.writeFileSync(mdPath, lines.join("\n") + "\n");

console.log(JSON.stringify({ json: jsonPath, md: mdPath }, null, 2));
