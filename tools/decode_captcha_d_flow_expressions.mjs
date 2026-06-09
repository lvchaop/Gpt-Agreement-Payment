#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const sourcePath = process.argv[2] || "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js";
const outDir = process.argv[3] || "output/protocol_reverse/source_offsets";
const label = process.argv[4] || "captcha_d_flow_expressions";

const source = fs.readFileSync(sourcePath, "utf8");
const line = source.split(/\r?\n/)[1723];
const decoderStart = line.indexOf("function lz(r,n){var u=Az()");
const decoderEnd = line.indexOf("var gz", decoderStart);
if (decoderStart < 0 || decoderEnd < 0) {
  throw new Error("cannot locate lz/Az decoder block");
}
const decoderCode = line.slice(decoderStart, decoderEnd);
// Evaluates only the local decoder table/functions copied from the captured source.
const { Hz } = Function(`${decoderCode}; return { Hz };`)();

function cOuter(r, n) {
  return Hz(r, n - 193);
}
function K(r, n) {
  // Exact source inside D(): function K(r,n){return c(r,n- -1147)}
  return cOuter(r, n - -1147);
}
function cInner(r, n) {
  // Exact source inside Ts callback: function c(r,n){return K(n,r-597)}
  return K(n, r - 597);
}
function globalU(encoded) {
  const key = "W6ypnhT";
  const buf = Buffer.from(encoded, "base64");
  let out = "";
  for (let i = 0; i < buf.length; i++) {
    out += String.fromCharCode(buf[i] ^ key.charCodeAt(i % key.length));
  }
  return out;
}
const expressions = [
  ["K(-179,-198)", () => K(-179, -198), "setTimeout bind"],
  ["K(-169,-188)", () => K(-169, -188), "PX1200 first argument"],
  ["K(-173,-184)", () => K(-173, -184), "window method type guard"],
  ["K(-185,-191)", () => K(-185, -191), "function type literal"],
  ["K(-166,-160)", () => K(-166, -160), "PX1200 method"],
  ["K(-185,-194)", () => K(-185, -194), "pre-submit extra field key"],
  ["K(-158,-171)", () => K(-158, -171), "deleted field key"],
  ["K(-177,-178)", () => K(-177, -178), "pt input key"],
  ["K(-174,-196)", () => K(-174, -196), "pn field key"],
  ["K(-165,-176)", () => K(-165, -176), "worker count key"],
  ["c(410,395)", () => cInner(410, 395), "Ts arg v field"],
  ["c(414,426)", () => cInner(414, 426), "Ts arg e / POW field"],
  ["c(411,413)", () => cInner(411, 413), "Ts arg n field"],
  ["c(429,410)", () => cInner(429, 410), "os field"],
  ["c(415,422)", () => cInner(415, 422), "Ks field"],
  ["c(439,441)", () => cInner(439, 441), "Ou activity type"],
  ["c(413,425)", () => cInner(413, 425), "window method call"],
];

const records = expressions.map(([expr, fn, note]) => {
  const raw = fn();
  let decoded = null;
  let error = null;
  try {
    decoded = globalU(raw);
  } catch (e) {
    error = String(e && e.stack || e);
  }
  return { expr, raw, decoded, error, note };
});

fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `${label}.json`);
const mdPath = path.join(outDir, `${label}.md`);
fs.writeFileSync(jsonPath, JSON.stringify({
  source: sourcePath,
  line: 1724,
  decoderRange: [decoderStart + 1, decoderEnd],
  records,
}, null, 2));

const lines = [
  `# Captcha D flow decoded expressions: ${label}`,
  "",
  `- source: \`${sourcePath}\``,
  "- line: `1724`",
  `- decoder range: \`${decoderStart + 1}..${decoderEnd}\``,
  `- json: \`${jsonPath}\``,
  "",
  "| expression | raw | decoded | note |",
  "|---|---|---|---|",
];
for (const r of records) {
  lines.push(`| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded || ""}\` | ${r.note} |`);
}
fs.writeFileSync(mdPath, lines.join("\n"));
console.log(mdPath);
console.log(jsonPath);
