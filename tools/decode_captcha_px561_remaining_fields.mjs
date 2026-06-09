#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const sourcePath = process.argv[2] || "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js";
const outDir = process.argv[3] || "output/protocol_reverse/source_offsets";
const label = process.argv[4] || "captcha_px561_remaining_fields";

const source = fs.readFileSync(sourcePath, "utf8");
const lineNo = 1724;
const line = source.split(/\r?\n/)[lineNo - 1];

function globalU(encoded) {
  const key = "W6ypnhT";
  const buf = Buffer.from(encoded, "base64");
  let out = "";
  for (let i = 0; i < buf.length; i++) {
    out += String.fromCharCode(buf[i] ^ key.charCodeAt(i % key.length));
  }
  return out;
}

function evalDecoder(startNeedle, endNeedle, returnExpr) {
  const start = line.indexOf(startNeedle);
  const end = line.indexOf(endNeedle, start);
  if (start < 0 || end < 0) {
    throw new Error(`cannot locate decoder block ${startNeedle} -> ${endNeedle}`);
  }
  const code = line.slice(start, end);
  return { start, end, api: Function(`${code}; return ${returnExpr};`)() };
}

const fsDecoder = evalDecoder(
  "function Vs(r,n){return Fs",
  "function _s()",
  "{ Vs, Fs, Ss }",
);
const lzDecoder = evalDecoder(
  "function lz(r,n){var u=Az()",
  "var gz",
  "{ Hz }",
);

const { Vs } = fsDecoder.api;
const { Hz } = lzDecoder.api;

function tsRuntimeKey(r, n) {
  // Source at captcha.beautified.js:11080-11081:
  // function v(r,n){ return Vs(n, r - -148) }
  return Vs(n, r - -148);
}

function cIz(r, n) {
  // Source inside Iz(): function c(r,n){ return Hz(r, n - 193) }
  return Hz(r, n - 193);
}

function dK(r, n) {
  // Source inside D(): function K(r,n){ return c(r, n - -1147) }
  return cIz(r, n - -1147);
}

function tsInner(r, n) {
  // Source inside Ts callback: function c(r,n){ return K(n, r - 597) }
  return dK(n, r - 597);
}

const expressions = [
  {
    expr: 'D submit extra key: f("HGASKTZabC1xSx9T")',
    raw: () => "HGASKTZabC1xSx9T",
    assignment: "captcha.beautified.js:11070 assigns d[key] = jz before PX1200 submit",
  },
  {
    expr: "Ts runtime key: t(v(-540,-543))",
    raw: () => tsRuntimeKey(-540, -543),
    assignment: "captcha.beautified.js:11083 assigns r[key] = _s()",
  },
  {
    expr: "Ts runtime key: t(v(-531,-522))",
    raw: () => tsRuntimeKey(-531, -522),
    assignment: "captcha.beautified.js:11083 assigns r[key] = Rs",
  },
  {
    expr: 'Ts runtime key: t("FnM4CCwDASRmEyFT")',
    raw: () => "FnM4CCwDASRmEyFT",
    assignment: "captcha.beautified.js:11085 assigns r[key] = Ws[Ng]()",
  },
  {
    expr: "Ts runtime key: t(v(-541,-541))",
    raw: () => tsRuntimeKey(-541, -541),
    assignment: "captcha.beautified.js:11088 assigns r[key] = Ws[NQ](n)",
  },
  {
    expr: "Ts Ks field: f(c(415,422))",
    raw: () => tsInner(415, 422),
    assignment: "captcha.beautified.js:11098 assigns r[key] = Ks",
  },
];

const records = expressions.map((item) => {
  const raw = item.raw();
  let decoded = null;
  let error = null;
  try {
    decoded = globalU(raw);
  } catch (e) {
    error = String(e && e.stack || e);
  }
  return { expr: item.expr, raw, decoded, error, assignment: item.assignment };
});

fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `${label}.json`);
const mdPath = path.join(outDir, `${label}.md`);
fs.writeFileSync(jsonPath, JSON.stringify({
  source: sourcePath,
  line: lineNo,
  decoderRanges: {
    fsVs: [fsDecoder.start + 1, fsDecoder.end],
    hzLz: [lzDecoder.start + 1, lzDecoder.end],
  },
  records,
}, null, 2));

const lines = [
  `# Captcha PX561 remaining field decoded expressions: ${label}`,
  "",
  `- source: \`${sourcePath}\``,
  `- line: \`${lineNo}\``,
  `- json: \`${jsonPath}\``,
  "",
  "| expression | raw | decoded | assignment |",
  "|---|---|---|---|",
];
for (const r of records) {
  lines.push(`| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded || ""}\` | ${r.assignment} |`);
}
fs.writeFileSync(mdPath, `${lines.join("\n")}\n`);

console.log(mdPath);
console.log(jsonPath);
