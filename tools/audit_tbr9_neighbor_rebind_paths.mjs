#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const exactPath = path.join(repo, "output/protocol_reverse/exact_source/captcha_ni109_4b399270.source.js");
const prettyPath = path.join(repo, "output/outlook_browser/js_static_analysis/captcha.beautified.js");
const bundlePath = path.join(repo, "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json");
const decodePath = path.join(repo, "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields_ni109_exact.json");
const outDir = path.join(repo, "output/protocol_reverse/source_offsets");

const TARGET = "TBR9Ugl7emA=";
const TBR_PREFIX = "Y@tvUUF@W";

function read(p) {
  return fs.readFileSync(p, "utf8");
}

function globalU(encoded) {
  const key = "W6ypnhT";
  const buf = Buffer.from(encoded, "base64");
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

function lines(pathname, start, end) {
  const arr = read(pathname).split(/\r?\n/);
  const out = [];
  for (let line = start; line <= end; line++) {
    if (line >= 1 && line <= arr.length) out.push({ line, text: arr[line - 1] });
  }
  return out;
}

function countAll(haystack, needle) {
  let count = 0;
  let pos = 0;
  while ((pos = haystack.indexOf(needle, pos)) !== -1) {
    count++;
    pos += needle.length || 1;
  }
  return count;
}

function finalPx561D() {
  const bundle = JSON.parse(read(bundlePath));
  for (const req of bundle.requests || []) {
    for (const hit of req.activitiesWithMatches || []) {
      if (hit.type === "PX561" && hit.activity && hit.activity.d && Object.prototype.hasOwnProperty.call(hit.activity.d, TARGET)) {
        return { requestLine: req.requestLine, activityIndex: hit.index, d: hit.activity.d };
      }
    }
  }
  throw new Error("success PX561 with TBR9 not found");
}

function aroundKeys(obj, target, radius = 3) {
  const keys = Object.keys(obj);
  const idx = keys.indexOf(target);
  return {
    index: idx,
    window: keys.slice(Math.max(0, idx - radius), Math.min(keys.length, idx + radius + 1)).map((key) => ({
      index: keys.indexOf(key),
      key,
      valueType: obj[key] === null ? "null" : Array.isArray(obj[key]) ? "array" : typeof obj[key],
      valueLength: typeof obj[key] === "string" ? obj[key].length : null,
      valuePreview: typeof obj[key] === "string" ? obj[key].slice(0, 80) : obj[key],
    })),
  };
}

function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const exact = read(exactPath);
  const pretty = read(prettyPath);
  const exactLine = exact.split(/\r?\n/)[1723];
  const fsDecoder = evalDecoder(exactLine, "function Vs(r,n){return Fs", "function _s()", "{ Vs }");
  const { Vs } = fsDecoder.api;

  const tsRuntimeKey = (r, n) => Vs(n, r - -148);
  const rsRawCandidates = {
    Qs: Vs(-390, -384),
    Ys: Vs(-393, -394),
    ps: "MVcQHAsM",
  };
  const rsValueCandidates = Object.fromEntries(
    Object.entries(rsRawCandidates).map(([key, raw]) => [key, { raw, decoded: globalU(raw), length: globalU(raw).length }]),
  );

  const decodedRows = JSON.parse(read(decodePath)).records;
  const directRows = decodedRows.filter((row) =>
    [
      "Ts runtime key: t(v(-540,-543))",
      "Ts runtime key: t(v(-531,-522))",
      'Ts runtime key: t("FnM4CCwDASRmEyFT")',
      "Ts runtime key: t(v(-541,-541))",
    ].includes(row.expr)
  );
  const directRowsWithValues = directRows.map((row) => ({
    ...row,
    candidateRuntimeValue:
      row.decoded === "instantiating" ? rsValueCandidates :
      row.decoded === TARGET ? { staticSource: "_s()", runtimeType: "boolean" } :
      row.decoded === "AEAxBkUsPjQ=" ? { staticSource: "Ws.Ng()", runtimeType: "string" } :
      row.decoded === "succeeded" ? { staticSource: "Ws.NQ(n)", runtimeType: "string" } :
      null,
  }));

  const final = finalPx561D();
  const finalTbr = final.d[TARGET];
  const finalSummary = {
    requestLine: final.requestLine,
    activityIndex: final.activityIndex,
    fieldCount: Object.keys(final.d).length,
    tbr: {
      present: Object.prototype.hasOwnProperty.call(final.d, TARGET),
      index: Object.keys(final.d).indexOf(TARGET),
      type: typeof finalTbr,
      length: typeof finalTbr === "string" ? finalTbr.length : null,
      preview: typeof finalTbr === "string" ? finalTbr.slice(0, 80) : finalTbr,
    },
    instantiating: {
      present: Object.prototype.hasOwnProperty.call(final.d, "instantiating"),
      value: final.d.instantiating,
    },
    succeeded: {
      present: Object.prototype.hasOwnProperty.call(final.d, "succeeded"),
      value: final.d.succeeded,
    },
    aroundTbr: aroundKeys(final.d, TARGET),
  };

  const rsMatchFinalTbr = Object.fromEntries(
    Object.entries(rsValueCandidates).map(([key, row]) => [key, row.decoded === finalTbr]),
  );

  const counts = {
    exact: {
      rsIdentifier: (exact.match(/\bRs\b/g) || []).length,
      rsAssignments: (exact.match(/\bRs=/g) || []).length,
      instantiatingDecodedLiteral: countAll(exact, "instantiating"),
      targetDecodedLiteral: countAll(exact, TARGET),
      targetValuePrefix: countAll(exact, TBR_PREFIX),
      pnCallsNearD: countAll(exact.slice(Math.max(0, exact.indexOf("function D(")), exact.indexOf("tv(),", exact.indexOf("function D("))), "pn("),
    },
    beautified: {
      rsIdentifier: (pretty.match(/\bRs\b/g) || []).length,
      pnFunctionLine: 3648,
      tsFunctionLine: 8585,
      rsInitLine: 9578,
      dFunctionWindowStart: 11060,
    },
  };

  const result = {
    inputs: {
      exactCaptcha: exactPath,
      beautifiedCaptcha: prettyPath,
      successBundle: bundlePath,
      decodedDirectKeys: decodePath,
    },
    decoderRanges: {
      fsVs: [fsDecoder.start + 1, fsDecoder.end],
    },
    directAssignmentNeighborhood: directRowsWithValues,
    rsValueCandidates,
    rsMatchFinalTbr,
    finalSuccessPx561: finalSummary,
    counts,
    sourceSnippets: {
      pnMergeHelper_3648_3662: lines(prettyPath, 3648, 3662),
      tsWaiter_8585_8590: lines(prettyPath, 8585, 8590),
      rsInitialization_9578_9603: lines(prettyPath, 9578, 9603),
      sBoolean_9638_9644: lines(prettyPath, 9638, 9644),
      dTsNeighborhood_11066_11099: lines(prettyPath, 11066, 11099),
    },
    findings: [
      "The only direct neighbor field carrying Rs is decoded key instantiating, not TBR9Ugl7emA=.",
      "All statically possible Rs values are short strings and none equals the final 127-byte TBR9 value.",
      "The pn merge helper copies enumerable properties as r[e] = n[e]; the inspected helper has no key remap/rebind logic.",
      "Final success PX561.d still has no key instantiating and no key succeeded, while TBR9Ugl7emA= is present at the decoded success bundle boundary.",
      "This excludes the concrete hypothesis that the final TBR9 long string is simply the adjacent Rs value rebound through pn/Ts neighborhood code.",
    ],
    conclusion: "The adjacent Rs producer is not the final TBR9 producer under the audited exact-source path. TBR9 remains a collector-payload-construction blocker, and the next evidence boundary is a computed post-Ts/pre-Yc rewrite or a serialization/queue-stage insertion that is not visible in the direct D/Ts neighbor assignments.",
    nextEvidenceTargets: [
      "Instrument or statically audit window[L][f(c(413,425))] and i(f(c(439,441)), r) call targets to identify whether they mutate r before main Yc.",
      "Capture a labeled observation sample at Yc(e,'PX561') output and tf(A,np) entry to locate whether TBR9 exists before queueing or appears in/after serializer staging.",
      "Audit exact-source call target for the D/Ts callback handoff rather than continuing adjacent direct-assignment hypotheses.",
    ],
  };

  const jsonPath = path.join(outDir, "tbr9_neighbor_rebind_paths_audit.json");
  const mdPath = path.join(outDir, "tbr9_neighbor_rebind_paths_audit.md");
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));

  const md = [
    "# TBR9 neighbor rebind path audit",
    "",
    "## Direct assignment neighborhood",
    "",
    "| expression | decoded key | value source |",
    "|---|---|---|",
    ...directRowsWithValues.map((row) => `| \`${row.expr}\` | \`${row.decoded}\` | \`${JSON.stringify(row.candidateRuntimeValue).replaceAll("|", "\\|")}\` |`),
    "",
    "## Rs value candidates",
    "",
    "| name | raw | decoded | length | equals final TBR9 |",
    "|---|---|---|---:|---:|",
    ...Object.entries(rsValueCandidates).map(([key, row]) => `| \`${key}\` | \`${row.raw}\` | \`${row.decoded}\` | ${row.length} | \`${rsMatchFinalTbr[key]}\` |`),
    "",
    "## Final success PX561 boundary",
    "",
    `- requestLine: \`${finalSummary.requestLine}\``,
    `- activityIndex: \`${finalSummary.activityIndex}\``,
    `- fieldCount: \`${finalSummary.fieldCount}\``,
    `- TBR9 index: \`${finalSummary.tbr.index}\``,
    `- TBR9 length: \`${finalSummary.tbr.length}\``,
    `- instantiating present: \`${finalSummary.instantiating.present}\``,
    `- succeeded present: \`${finalSummary.succeeded.present}\``,
    "",
    "## Findings",
    "",
    ...result.findings.map((x) => `- ${x}`),
    "",
    "## Conclusion",
    "",
    result.conclusion,
    "",
    "## Next evidence targets",
    "",
    ...result.nextEvidenceTargets.map((x) => `- ${x}`),
    "",
  ].join("\n");
  fs.writeFileSync(mdPath, md);
  console.log(JSON.stringify({ json: jsonPath, md: mdPath }, null, 2));
}

main();
