#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const exactPath = path.join(repo, "output/protocol_reverse/exact_source/captcha_ni109_4b399270.source.js");
const captchaPrettyPath = path.join(repo, "output/outlook_browser/js_static_analysis/captcha.beautified.js");
const mainPrettyPath = path.join(repo, "output/outlook_browser/js_static_analysis/main.beautified.js");
const bridgePath = path.join(repo, "output/protocol_reverse/source_offsets/captcha_bridge_static_audit.json");
const outDir = path.join(repo, "output/protocol_reverse/source_offsets");

function read(p) {
  return fs.readFileSync(p, "utf8");
}

function globalU(encoded) {
  const key = "W6ypnhT";
  const padded = encoded + "=".repeat((4 - encoded.length % 4) % 4);
  const buf = Buffer.from(padded, "base64");
  let out = "";
  for (let i = 0; i < buf.length; i++) out += String.fromCharCode(buf[i] ^ key.charCodeAt(i % key.length));
  return out;
}

function evalDecoder(line, startNeedle, endNeedle, returnExpr) {
  const start = line.indexOf(startNeedle);
  const end = line.indexOf(endNeedle, start);
  if (start < 0 || end < 0) throw new Error(`cannot locate decoder block ${startNeedle} -> ${endNeedle}`);
  const code = line.slice(start, end);
  return { start, end, api: Function(`${code}; return ${returnExpr};`)() };
}

function sourceLines(pathname, start, end) {
  const arr = read(pathname).split(/\r?\n/);
  const out = [];
  for (let line = start; line <= end; line++) {
    if (line >= 1 && line <= arr.length) out.push({ line, text: arr[line - 1] });
  }
  return out;
}

function byExpr(rows, expr) {
  return rows.find((row) => row.expr === expr);
}

function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const exactLine = read(exactPath).split(/\r?\n/)[1723];
  const lzDecoder = evalDecoder(exactLine, "function lz(r,n){var u=Az()", "var gz", "{ Hz }");
  const { Hz } = lzDecoder.api;
  function cIz(r, n) {
    return Hz(r, n - 193);
  }
  function dK(r, n) {
    return cIz(r, n - -1147);
  }
  function tsC(r, n) {
    return dK(n, r - 597);
  }

  const tsCallbackExpressions = [
    ["Ts callback dynamic activity type f(c(439,441))", tsC(439, 441), "first arg to i(..., r)"],
    ["Ts callback post-queue window[L][f(c(413,425))]", tsC(413, 425), "called after i(PX561,r)"],
    ["Ts callback final window[L][f(\"B25ORlo\")]", "B25ORlo", "assigned Ot after post-queue call"],
    ["Ts callback POW answer field f(c(414,426))", tsC(414, 426), "assigned before i(PX561,r) when Ou() is function"],
    ["Ts callback Bzt field f(c(410,395))", tsC(410, 395), "assigned before i(PX561,r) when Ou() is function"],
  ].map(([expr, raw, role]) => ({ expr, raw, decoded: globalU(raw), role }));

  const bridge = JSON.parse(read(bridgePath));
  const dCheck = byExpr(bridge.izDExpressions, "D checks window[L][K(-173,-184)]");
  const px1200 = byExpr(bridge.izDExpressions, "D calls window[L][K(-166,-160)]");
  const fuVisible = byExpr(bridge.suFuExpressions, "Fu visible key t(v(-543,-542))");
  const px764Literal = bridge.b25Literals.find((row) => row.literal === "B25ORlo");

  const result = {
    inputs: {
      exactCaptcha: exactPath,
      captchaBeautified: captchaPrettyPath,
      mainBeautified: mainPrettyPath,
      bridgeAudit: bridgePath,
    },
    decoderRanges: {
      lzHz: [lzDecoder.start + 1, lzDecoder.end],
    },
    decodedCaptchaHandoff: {
      tsCallbackExpressions,
      bridgePreconditions: {
        fuVisibleKey: fuVisible,
        dChecksWindowLFunction: dCheck,
        dOptionalPreSubmit: px1200,
        px764Literal,
      },
    },
    staticHandoffChain: [
      {
        step: "main Zc locates captcha Fu bridge",
        evidence: "main.beautified.js:3032-3041: f = l && l[s(277)], then f($c, t, e, n, r)",
        decodedKey: "s(277) is PX762 from captcha_bridge_static_audit Fu visible key PX762",
      },
      {
        step: "captcha Fu callback stores first arg as gz",
        evidence: "captcha.beautified.js:11001-11008: Fu callback assigns gz = r; captcha.beautified.js:11027 calls pu(gz)",
        decodedKey: "first arg from main Zc is $c",
      },
      {
        step: "captcha Ou returns the stored callback",
        evidence: "captcha.beautified.js:4438-4442: pu(r){Yu=r}; Ou(){return Yu}",
        decodedKey: "Ou() returns $c after pu(gz)",
      },
      {
        step: "Ts callback calls i(PX561, r)",
        evidence: "captcha.beautified.js:11092-11098 and exact decode f(c(439,441)) -> PX561",
        decodedKey: "PX561",
      },
      {
        step: "main $c queues Yc output",
        evidence: "main.beautified.js:3078-3080: function $c(t,e){ Rc(t, Yc(e,t)) }",
        decodedKey: "PX561 path enters Yc before Rc",
      },
    ],
    ordering: {
      inTsCallback: [
        "assign success-only callback fields to r when Ou() is function",
        "call i(PX561, r), where i is the stored main $c callback",
        "call window[L][PX763](z)",
        "assign window[L][PX764] = Ot",
      ],
      implication: "For the PX561 activity, the decisive pre-Yc object is r at i(PX561,r); window[L][PX763](z) is a later separate bridge call and is not the PX561 Yc entry.",
    },
    sourceSnippets: {
      captchaPuOu_4438_4442: sourceLines(captchaPrettyPath, 4438, 4442),
      captchaFu_4469_4475: sourceLines(captchaPrettyPath, 4469, 4475),
      captchaFuCallbackAndQ_11001_11031: sourceLines(captchaPrettyPath, 11001, 11031),
      captchaDCallback_11046_11100: sourceLines(captchaPrettyPath, 11046, 11100),
      mainZcJcDollarC_3032_3080: sourceLines(mainPrettyPath, 3032, 3080),
    },
    findings: [
      "The exact ni109 decoder resolves f(c(439,441)) in the Ts callback to PX561.",
      "The main-side callback passed into captcha Fu is $c, and $c calls Rc(t, Yc(e,t)).",
      "Therefore the PX561 collector activity is emitted by i(PX561,r) where i is $c and r is the captcha Ts object after its direct assignments.",
      "The subsequent window[L][PX763](z) call is ordered after i(PX561,r) and maps to a separate bridge handler path; it is not the PX561 Yc entry.",
      "This makes r at i(PX561,r) the next decisive boundary for TBR9: if TBR9 is absent there, the insertion must occur in main Yc/Rc/ds/tf/serializer; if present there, the producer is in captcha before that call.",
    ],
    conclusion: "The D/Ts callback handoff is now statically narrowed to i(PX561,r) -> main $c(PX561,r) -> Yc(r,'PX561') -> Rc. This does not close TBR9, but it replaces the broader 'window[L] handoff' search with a precise pre-Yc boundary required for collector payload construction.",
    nextEvidenceTargets: [
      "Capture or reconstruct r immediately before i(PX561,r) in a labeled observation sample.",
      "Capture or reconstruct main $c/Yc input-output for that same PX561 activity.",
      "If r already has TBR9 as a 127-byte value, audit captcha-side producers before line 11098; otherwise audit main Yc/Rc/ds/tf/serializer mutation after $c.",
    ],
  };

  const jsonPath = path.join(outDir, "tbr9_handoff_call_target_audit.json");
  const mdPath = path.join(outDir, "tbr9_handoff_call_target_audit.md");
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));

  const md = [
    "# TBR9 handoff call target audit",
    "",
    "## Decoded Ts callback expressions",
    "",
    "| expr | raw | decoded | role |",
    "|---|---|---|---|",
    ...tsCallbackExpressions.map((row) => `| \`${row.expr}\` | \`${row.raw}\` | \`${row.decoded}\` | ${row.role} |`),
    "",
    "## Static handoff chain",
    "",
    "| step | evidence | decoded key |",
    "|---|---|---|",
    ...result.staticHandoffChain.map((row) => `| ${row.step} | ${row.evidence} | \`${row.decodedKey}\` |`),
    "",
    "## Ordering implication",
    "",
    result.ordering.implication,
    "",
    "## Findings",
    "",
    ...result.findings.map((item) => `- ${item}`),
    "",
    "## Conclusion",
    "",
    result.conclusion,
    "",
    "## Next evidence targets",
    "",
    ...result.nextEvidenceTargets.map((item) => `- ${item}`),
    "",
  ].join("\n");
  fs.writeFileSync(mdPath, md);
  console.log(JSON.stringify({ json: jsonPath, md: mdPath }, null, 2));
}

main();
