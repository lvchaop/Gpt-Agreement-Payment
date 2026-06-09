#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const sourcePath = process.argv[2] || "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js";
const outDir = process.argv[3] || "output/protocol_reverse/source_offsets";
const label = process.argv[4] || "captcha_px561_extra_fields";

const source = fs.readFileSync(sourcePath, "utf8");
const lineNo = 1724;
const line = source.split(/\r?\n/)[lineNo - 1];
const decoderStart = line.indexOf("function lz(r,n){var u=Az()");
const decoderEnd = line.indexOf("var gz", decoderStart);
if (decoderStart < 0 || decoderEnd < 0) {
  throw new Error("cannot locate lz/Az decoder block");
}

const decoderCode = line.slice(decoderStart, decoderEnd);
// Evaluates only the local decoder table/functions copied from captured source.
const { Hz } = Function(`${decoderCode}; return { Hz };`)();

function globalU(encoded) {
  const key = "W6ypnhT";
  const buf = Buffer.from(encoded, "base64");
  let out = "";
  for (let i = 0; i < buf.length; i++) {
    out += String.fromCharCode(buf[i] ^ key.charCodeAt(i % key.length));
  }
  return out;
}

function cIz(r, n) {
  // Exact source inside Iz(): function c(r,n){return Hz(r,n-193)}
  return Hz(r, n - 193);
}

function jInner(r, n) {
  // Exact source inside J(): function n(r,n){return c(n,r- -67)}
  return cIz(n, r - -67);
}

function dK(r, n) {
  // Exact source inside D(): function K(r,n){return c(r,n- -1147)}
  return cIz(r, n - -1147);
}

function tsInner(r, n) {
  // Exact source inside Ts callback: function c(r,n){return K(n,r-597)}
  return dK(n, r - 597);
}

const expressions = [
  ["J left key: z(\"Em4/FyBZBTJsODFT\")", () => "Em4/FyBZBTJsODFT", "J(r) bm/Zm mapped field 1 left"],
  ["J right key: z(n(901,884))", () => jInner(901, 884), "J(r) bm/Zm mapped field 1 source"],
  ["J left key: z(\"DWRIJSkRFi5jOkhT\")", () => "DWRIJSkRFi5jOkhT", "J(r) mapped field 2 left"],
  ["J right key: z(\"IF8dBAY\")", () => "IF8dBAY", "J(r) mapped field 2 source"],
  ["J left key: z(n(908,909))", () => jInner(908, 909), "J(r) mapped field 3 left"],
  ["J right key: z(\"IF8dBAYiITpG\")", () => "IF8dBAYiITpG", "J(r) mapped field 3 source"],
  ["J left key: z(n(924,940))", () => jInner(924, 940), "J(r) mapped field 4 left"],
  ["J right key: z(\"P1MQFwYcHiJbCQ\")", () => "P1MQFwYcHiJbCQ", "J(r) mapped field 4 source"],
  ["J left key: z(\"FEwdRg09YQ5QEh9T\")", () => "FEwdRg09YQ5QEh9T", "J(r) mapped field 5 left"],
  ["J right key: z(n(921,939))", () => jInner(921, 939), "J(r) mapped field 5 source"],
  ["J left key: z(n(915,900))", () => jInner(915, 900), "J(r) mapped field 6 left"],
  ["J right key: z(\"P1cKGA\")", () => "P1cKGA", "J(r) mapped field 6 source"],
  ["J left key: z(n(925,939))", () => jInner(925, 939), "J(r) mapped field 7 left"],
  ["J right key: z(\"PkIcAg8cPThYCg\")", () => "PkIcAg8cPThYCg", "J(r) mapped field 7 source"],
  ["J left key: z(n(900,904))", () => jInner(900, 904), "J(r) mapped field 8 left"],
  ["J right key: z(\"I18UFToHBzhaDxU\")", () => "I18UFToHBzhaDxU", "J(r) mapped field 8 source"],
  ["J optional condition/source: z(n(885,907))", () => jInner(885, 907), "J(r) optional condition/source"],
  ["J optional left/source: z(n(907,909))", () => jInner(907, 909), "J(r) optional left"],
  ["J optional right/source: z(n(885,904))", () => jInner(885, 904), "J(r) optional right"],
  ["D worker count key: K(-165,-176)", () => dK(-165, -176), "D pn() worker count key"],
  ["D pn key: K(-174,-196)", () => dK(-174, -196), "D pn() field key"],
  ["Ts v field: c(410,395)", () => tsInner(410, 395), "Ts callback assigns v"],
  ["Ts e / POW field: c(414,426)", () => tsInner(414, 426), "Ts callback assigns e POW"],
  ["Ts n field: c(411,413)", () => tsInner(411, 413), "Ts callback assigns n"],
  ["Ts PX561 type: c(439,441)", () => tsInner(439, 441), "Ou activity type"],
];

const records = expressions.map(([expr, rawFn, note]) => {
  const raw = rawFn();
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
  line: lineNo,
  decoderRange: [decoderStart + 1, decoderEnd],
  records,
}, null, 2));

const lines = [
  `# Captcha PX561 extra field decoded expressions: ${label}`,
  "",
  `- source: \`${sourcePath}\``,
  `- line: \`${lineNo}\``,
  `- decoder range: \`${decoderStart + 1}..${decoderEnd}\``,
  `- json: \`${jsonPath}\``,
  "",
  "| expression | raw | decoded | note |",
  "|---|---|---|---|",
];
for (const r of records) {
  lines.push(`| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded || ""}\` | ${r.note} |`);
}
fs.writeFileSync(mdPath, `${lines.join("\n")}\n`);

console.log(mdPath);
console.log(jsonPath);
