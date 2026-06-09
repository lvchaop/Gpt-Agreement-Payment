#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const sourcePath = process.argv[2] || "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js";
const outDir = process.argv[3] || "output/protocol_reverse/source_offsets";
const label = process.argv[4] || "captcha_state_submit_fields";

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

const isDecoder = evalDecoder(
  "function zs(){",
  "var cs=0",
  "{ is }",
);
const lzDecoder = evalDecoder(
  "function lz(r,n){var u=Az()",
  "var gz",
  "{ Hz, lz }",
);
const { is } = isDecoder.api;
const { lz } = lzDecoder.api;

function L(r, n) {
  // Source at captcha.beautified.js:8144-8145:
  // function L(r,n){ return is(n - 355, r) }
  return is(n - 355, r);
}

const assignments = [
  ["K[n(L(659,692))] = i", () => L(659, 692), "i: positive Hn interval list"],
  ["K[n(L(720,745))] = v", () => L(720, 745), "v: callback input r[JVMVFQ8bMQNfFBU]"],
  ["K[n(L(768,757))] = !!Hn[...] || t", () => L(768, 757), "boolean challenge state"],
  ["K[n(L(715,698))] = wu()", () => L(715, 698), "wu()"],
  ['K[n(L(749,725))] = Hn[n("MVcSFToHPzJY")]', () => L(749, 725), "Hn[MVcSFToHPzJY]"],
  ['K[n("HGASKTZabC1xSx9T")] = Hn[n(L(740,729))]', () => "HGASKTZabC1xSx9T", "Hn[L(740,729)]"],
  ["K[n(L(804,768))] = z", () => L(804, 768), "z: elapsed since Hn start"],
  ["K[n(L(714,704))] = Hn[n(L(730,696))]", () => L(714, 704), "Hn[L(730,696)]"],
  ["K[n(L(758,769))] = Hn[n(L(734,744))]", () => L(758, 769), "Hn[L(734,744)]"],
  ['K[n(L(707,717))] = Hn[n("NF4YHAINOjBTKxUCDTUkUy0ZAw0nI1cUAB0")]', () => L(707, 717), "Hn[NF4...]"],
  ["K[n(L(728,693))] = Hn[n(L(669,691))]", () => L(728, 693), "Hn[L(669,691)]"],
  ['K[n(L(744,767))] = Hn[n("IlgSHgEfOgRVCxkeHBAyQhwTGg0w")]', () => L(744, 767), "Hn[Ilg...]"],
  ['K[n("H1swBjQuMxp9PylT")] = Hn[n(L(696,716))]', () => "H1swBjQuMxp9PylT", "Hn[L(696,716)]"],
  ["K[n(L(671,707))] = Hn[n(L(737,728))]", () => L(671, 707), "Hn[L(737,728)]"],
  ["K[n(L(776,754))] = Hn[n(L(698,732))][n(L(787,770))]", () => L(776, 754), "Hn[L(698,732)][L(787,770)]"],
  ["K[n(L(684,724))] = window[n(L(701,736))] || -1", () => L(684, 724), "window[L(701,736)] || -1"],
  ["K[n(L(788,759))] = window[n(L(745,748))] || -1", () => L(788, 759), "window[L(745,748)] || -1"],
  ["K[n(L(741,714))] = cs", () => L(741, 714), "cs"],
  ['K[n("AQYKHTo6ETx8IRNT")] = Hn[n(L(720,712))]', () => "AQYKHTo6ETx8IRNT", "Hn[L(720,712)]"],
  ["K[n(L(763,762))] = Hn[n(L(713,699))]", () => L(763, 762), "Hn[L(713,699)]"],
  ["K[n(L(771,734))] = n(L(688,726))", () => L(771, 734), "literal decoded L(688,726)"],
  ["K[n(L(706,721))] = Hn[n(L(671,701))]", () => L(706, 721), "Hn[L(671,701)]"],
  ["K[n(L(746,723))] = Hn[n(L(708,738))]", () => L(746, 723), "Hn[L(708,738)]"],
  ['K[n("NFFNND0sMD50SgNT")] = !!Hn[n(L(759,750))]', () => "NFFNND0sMD50SgNT", "!!Hn[L(759,750)]"],
  ["K[n(L(713,742))] = Hn[n(L(771,750))] && ...", () => L(713, 742), "compound Hn boolean"],
  ['K[n("FXAOQSkDESB7KjFT")] = w', () => "FXAOQSkDESB7KjFT", "w = B()"],
  ['K[n("B10zICwgJyJlA0hT")] = !w && lu()', () => "B10zICwgJyJlA0hT", "!w && lu()"],
  ["K[n(L(705,703))] = Hn[n(L(726,756))]", () => L(705, 703), "Hn[L(726,756)]"],
  ["K[n(L(709,720))] = Hn[n(L(715,733))] === sn[n(L(687,711))]", () => L(709, 720), "Hn[L(715,733)] === sn[L(687,711)]"],
  ["conditional K[n(L(804,764))] = Hn[n(L(716,755))]", () => L(804, 764), "conditional Hn[L(716,755)]"],
];

const records = assignments.map(([expr, rawFn, valueExpr]) => {
  const raw = rawFn();
  let decoded = null;
  let error = null;
  try {
    decoded = globalU(raw);
  } catch (e) {
    error = String(e && e.stack || e);
  }
  return { expr, raw, decoded, error, valueExpr };
});

function wInit(r, n) {
  // Source at captcha.beautified.js:8151-8152:
  // function w(r,n){ return is(n - -848, r) }
  return is(n - -848, r);
}

function qCallSecondArgKey() {
  // Source at captcha.beautified.js:11031:
  // r((t = -109, v = -121, lz(v - -409, t)))
  return lz((-121) - -409, -109);
}

const initAssignments = [
  ['Hn[o(w(-490,-474))] = r', () => wInit(-490, -474), "challengeTime? initialized from first Ls.PlqQBA arg"],
  ['Hn[o("MVcSFToHPzJY")] = e[o(w(-499,-476))]', () => "MVcSFToHPzJY", "fakeToken slot receives secondArg.token"],
  ['e[o(w(-499,-476))]', () => wInit(-499, -476), "token property read from second Ls.PlqQBA arg"],
  ['Hn[o(w(-453,-443))] = f', () => wInit(-453, -443), "onSolvedCallback initialized from third arg"],
  ['Hn[o(w(-468,-438))] = m()', () => wInit(-468, -438), "challengeStartTime"],
  ['Hn[o(w(-525,-507))] = i()', () => wInit(-525, -507), "challengeRenderTimestamp"],
  ['Hn[o(w(-449,-448))] = z', () => wInit(-449, -448), "accessibilityMode"],
  ['Kf(Hn[o(w(-490,-474))], Hn[o(w(-450,-472))], n)', () => wInit(-450, -472), "fakeToken read passed into Kf"],
  ['Ls.PlqQBA second arg key at captcha.beautified.js:11031', () => qCallSecondArgKey(), "secondArg[decodedKey] = yz"],
];

const initRecords = initAssignments.map(([expr, rawFn, valueExpr]) => {
  const raw = rawFn();
  let decoded = null;
  let error = null;
  try {
    decoded = globalU(raw);
  } catch (e) {
    error = String(e && e.stack || e);
  }
  return { expr, raw, decoded, error, valueExpr };
});

fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `${label}.json`);
const mdPath = path.join(outDir, `${label}.md`);
fs.writeFileSync(jsonPath, JSON.stringify({
  source: sourcePath,
  line: lineNo,
  beautifiedLines: "captcha.beautified.js:8131-8140",
  decoderRange: [isDecoder.start + 1, isDecoder.end],
  initBeautifiedLines: "captcha.beautified.js:8148-8155",
  initRecords,
  records,
}, null, 2));

const lines = [
  `# Captcha state submit fields: ${label}`,
  "",
  `- source: \`${sourcePath}\``,
  `- source line: \`${lineNo}\``,
  "- beautified evidence: `output/outlook_browser/js_static_analysis/captcha.beautified.js:8131-8140`",
  "- initialization evidence: `output/outlook_browser/js_static_analysis/captcha.beautified.js:8148-8155`",
  `- json: \`${jsonPath}\``,
];
lines.push("", "## Ls.PlqQBA initialization fields", "", "| expression | raw | decoded | value expression |", "|---|---|---|---|");
for (const r of initRecords) {
  lines.push(`| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded || ""}\` | ${r.valueExpr} |`);
}
lines.push("", "## submit K fields", "", "| expression | raw | decoded | value expression |", "|---|---|---|---|");
for (const r of records) {
  lines.push(`| \`${r.expr}\` | \`${r.raw}\` | \`${r.decoded || ""}\` | ${r.valueExpr} |`);
}
fs.writeFileSync(mdPath, `${lines.join("\n")}\n`);

console.log(JSON.stringify({ json: jsonPath, md: mdPath }, null, 2));
