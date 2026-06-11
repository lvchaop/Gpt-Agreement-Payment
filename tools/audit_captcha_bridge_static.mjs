#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const repo = process.cwd();
const sourcePath = process.argv[2] || path.join(repo, "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js");
const beautifiedPath = process.argv[3] || path.join(repo, "output/outlook_browser/js_static_analysis/captcha.beautified.js");
const outDir = process.argv[4] || path.join(repo, "output/protocol_reverse/source_offsets");
const label = process.argv[5] || "captcha_bridge_static_audit";

const source = fs.readFileSync(sourcePath, "utf8");
const beautified = fs.readFileSync(beautifiedPath, "utf8");
const lineNo = 1724;
const sourceLine = source.split(/\r?\n/)[lineNo - 1];

function globalU(encoded) {
  const key = "W6ypnhT";
  const padded = encoded + "=".repeat((4 - encoded.length % 4) % 4);
  const buf = Buffer.from(padded, "base64");
  let out = "";
  for (let i = 0; i < buf.length; i++) out += String.fromCharCode(buf[i] ^ key.charCodeAt(i % key.length));
  return out;
}

function evalDecoder(startNeedle, endNeedle, returnExpr) {
  const start = sourceLine.indexOf(startNeedle);
  const end = sourceLine.indexOf(endNeedle, start);
  if (start < 0 || end < 0) throw new Error(`cannot locate decoder block ${startNeedle} -> ${endNeedle}`);
  const code = sourceLine.slice(start, end);
  return { start, end, api: Function(`${code}; return ${returnExpr};`)() };
}

function evalVuDecoder() {
  const vuStart = sourceLine.indexOf("function Vu(){var r=");
  const start = sourceLine.lastIndexOf("!function(r,n){var u=r();", vuStart);
  const end = sourceLine.indexOf("function $u", vuStart);
  if (start < 0 || end < 0) throw new Error("cannot locate rotated Vu/_u decoder block");
  const code = sourceLine.slice(start, end);
  return { start, end, api: Function(`${code}; return { _u };`)() };
}

const vuDecoder = evalVuDecoder();
const lzDecoder = evalDecoder("function lz(r,n){var u=Az()", "var gz", "{ Hz }");
const { _u } = vuDecoder.api;
const { Hz } = lzDecoder.api;

function decodeSafe(raw) {
  try {
    return globalU(raw);
  } catch (e) {
    return null;
  }
}

function captchaSuExprs() {
  const out = [];
  function suR(r, n) {
    return _u(r - 938, n);
  }
  function fuV(r, n) {
    return _u(r + 789, n);
  }
  function fuE(r, n) {
    return fuV(n - 1162, r);
  }
  for (const rec of [
    ["Su prefix n(\"CA\")", "CA"],
    ["Su location key n(r(1190,1187))", suR(1190, 1187)],
    ["Su replace method n(\"JVMJHA8LMQ\")", "JVMJHA8LMQ"],
    ["Su regex replace arg n(\"\")", ""],
    ["Su suffix n(r(1195,1187))", suR(1195, 1187)],
    ["Fu visible key t(v(-543,-542))", fuV(-543, -542)],
    ["Fu Array property n(e(630,633))", fuE(630, 633)],
    ["Fu bind/call property n(e(636,634))", fuE(636, 634)],
    ["Fu slice/apply property n(e(625,622))", fuE(625, 622)],
    ["Fu apply call n(\"NkYJHBc\")", "NkYJHBc"],
  ]) {
    out.push({ expr: rec[0], raw: rec[1], decoded: decodeSafe(rec[1]) });
  }
  return out;
}

function captchaIzDExprs() {
  function cIz(r, n) {
    return Hz(r, n - 193);
  }
  function dK(r, n) {
    return cIz(r, n - -1147);
  }
  const exprs = [
    ["D checks window[L][K(-173,-184)]", dK(-173, -184)],
    ["D typeof literal K(-185,-191)", dK(-185, -191)],
    ["D calls window[L][K(-166,-160)]", dK(-166, -160)],
    ["D PX1200 payload type K(-169,-188)", dK(-169, -188)],
    ["D delete key K(-158,-171)", dK(-158, -171)],
    ["Iz assigns window[Su()][B25IQVhdbQ]", "B25IQVhdbQ"],
    ["runtime $t checks window[n][B25IQFlQ]", "B25IQFlQ"],
    ["Rt helper visible r(\"B25IQFlQ\")", "B25IQFlQ"],
  ];
  return exprs.map(([expr, raw]) => ({ expr, raw, decoded: decodeSafe(raw) }));
}

function findLineForOffset(text, offset) {
  let line = 1;
  let last = 0;
  while (true) {
    const idx = text.indexOf("\n", last);
    if (idx < 0 || idx >= offset) break;
    line++;
    last = idx + 1;
  }
  return line;
}

function contextByLine(text, line, radius = 3) {
  const lines = text.split(/\r?\n/);
  const start = Math.max(1, line - radius);
  const end = Math.min(lines.length, line + radius);
  return Array.from({ length: end - start + 1 }, (_, i) => {
    const n = start + i;
    return `${String(n).padStart(5)}: ${lines[n - 1]}`;
  }).join("\n");
}

function findWindowSuHits() {
  const needles = ["window[Su()]", "window[L]", "window[n]"];
  const hits = [];
  for (const needle of needles) {
    let offset = 0;
    while (true) {
      const idx = beautified.indexOf(needle, offset);
      if (idx < 0) break;
      const line = findLineForOffset(beautified, idx);
      hits.push({ needle, offset: idx, line, context: contextByLine(beautified, line, 2) });
      offset = idx + needle.length;
    }
  }
  return hits;
}

function scanB25Literals() {
  const found = new Map();
  const re = /"([^"]*B25[^"]*)"/g;
  for (const m of beautified.matchAll(re)) {
    const literal = m[1];
    if (literal.length > 32) continue;
    if (!found.has(literal)) {
      found.set(literal, {
        literal,
        decoded: decodeSafe(literal),
        firstOffset: m.index,
        firstLine: findLineForOffset(beautified, m.index),
      });
    }
  }
  return [...found.values()].sort((a, b) => a.firstLine - b.firstLine);
}

const result = {
  inputs: { sourcePath, beautifiedPath, sourceLine: lineNo },
  decoderRanges: {
    vu: [vuDecoder.start, vuDecoder.end],
    lz: [lzDecoder.start, lzDecoder.end],
  },
  suFuExpressions: captchaSuExprs(),
  izDExpressions: captchaIzDExprs(),
  b25Literals: scanB25Literals(),
  windowSuHits: findWindowSuHits(),
  conclusions: [
    "Su() expression components decode to a deterministic window property name prefix/suffix; exact runtime value still depends on window._pxAppId.",
    "Fu() visible object key decodes to PX762 when the rotated Vu/_u decoder block is evaluated before decoding.",
    "The earlier 'slice' interpretation belonged to the Array.prototype.slice.call helper expression, not the Fu() visible callback key.",
    "Static captcha bridge evidence now supports main Zc/Lc PX762 -> captcha Fu() callback registration; remaining PX561 gaps are downstream field/value producer boundaries, not this bridge.",
  ],
};

fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `${label}.json`);
const mdPath = path.join(outDir, `${label}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));

const md = [
  `# Captcha bridge static audit: ${label}`,
  "",
  `- source: \`${sourcePath}\``,
  `- beautified: \`${beautifiedPath}\``,
  `- json: \`${jsonPath}\``,
  "",
  "## Su/Fu decoded expressions",
  "",
  "| expr | raw | decoded |",
  "|---|---|---|",
  ...result.suFuExpressions.map((r) => `| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded ?? ""}\` |`),
  "",
  "## D/Iz bridge decoded expressions",
  "",
  "| expr | raw | decoded |",
  "|---|---|---|",
  ...result.izDExpressions.map((r) => `| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded ?? ""}\` |`),
  "",
  "## B25 literal scan",
  "",
  "| line | literal | decoded |",
  "|---:|---|---|",
  ...result.b25Literals.map((r) => `| ${r.firstLine} | \`${r.literal}\` | \`${r.decoded ?? ""}\` |`),
  "",
  "## window[Su()] / window[L] / window[n] hits",
  "",
  ...result.windowSuHits.flatMap((h) => [
    `### ${h.needle} at line ${h.line}`,
    "",
    "```js",
    h.context,
    "```",
    "",
  ]),
  "## Conclusions",
  "",
  ...result.conclusions.map((x) => `- ${x}`),
  "",
];
fs.writeFileSync(mdPath, md.join("\n"));

console.log(JSON.stringify({ json: jsonPath, md: mdPath }, null, 2));
