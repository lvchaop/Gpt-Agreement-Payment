#!/usr/bin/env node
import fs from "fs";
import path from "path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const mainPath = path.join(repo, "output/outlook_browser/js_static_analysis/main.beautified.js");
const outDir = path.join(repo, "output/protocol_reverse/source_offsets");
const target = "TBR9Ugl7emA=";

function extractNv(source) {
  const m = source.match(/function Nv\(\) \{\n\s*var t = (\[[\s\S]*?\]);\n\s*return/);
  if (!m) throw new Error("Nv array not found");
  return Function(`return ${m[1]}`)();
}

function rotateNv(arr) {
  function Bv(i) {
    return arr[i - 229];
  }
  let rotations = 0;
  for (;;) {
    try {
      const expr =
        -parseInt(Bv(271)) / 1 * (parseInt(Bv(231)) / 2) +
        parseInt(Bv(257)) / 3 +
        -parseInt(Bv(252)) / 4 * (parseInt(Bv(250)) / 5) +
        parseInt(Bv(270)) / 6 +
        parseInt(Bv(249)) / 7 +
        -parseInt(Bv(273)) / 8 * (parseInt(Bv(281)) / 9) +
        parseInt(Bv(237)) / 10;
      if (expr === 408184) break;
      arr.push(arr.shift());
      rotations += 1;
      if (rotations > arr.length * 3) throw new Error("Nv rotation did not converge");
    } catch (e) {
      arr.push(arr.shift());
      rotations += 1;
      if (rotations > arr.length * 3) throw e;
    }
  }
  return { arr, rotations, Bv };
}

function lineSnippet(lines, start, end) {
  const out = [];
  for (let line = start; line <= end; line += 1) {
    out.push({ line, text: lines[line - 1] });
  }
  return out;
}

function main() {
  const source = fs.readFileSync(mainPath, "utf8");
  const lines = source.split(/\r?\n/);
  const rotated = rotateNv(extractNv(source));
  const Bv = rotated.Bv;

  const decoded = Object.fromEntries(
    [229, 230, 232, 233, 234, 236, 239, 241, 243, 246, 258, 259, 260, 264, 266, 274, 276, 277, 279, 282].map((idx) => [idx, Bv(idx)])
  );

  const dsMutations = [
    {
      line: 3456,
      expression: 'e["HUlnQ1slanM="] = us++',
      key: "HUlnQ1slanM=",
      appliesToPx561: true,
      isTbr9: false,
    },
    {
      line: 3456,
      expression: 'e["R3c9PQEXNg8="] = qi() || It()',
      key: "R3c9PQEXNg8=",
      appliesToPx561: true,
      isTbr9: false,
    },
  ];

  const unSpecialTypes = [Bv(259), Bv(229)];
  const unSpecialMutations = [
    { line: 8519, expression: "w.d[R(i)] = $o", key: Bv(233), appliesToPx561: false, isTbr9: Bv(233) === target },
    { line: 8520, expression: "w.d[R(c)] = Fi()", key: Bv(266), appliesToPx561: false, isTbr9: Bv(266) === target },
    { line: 8521, expression: "w.d[R(u)] = ti", key: Bv(243), appliesToPx561: false, isTbr9: Bv(243) === target },
  ];
  const unCommonMutations = [
    { line: 8523, expression: "w.d[R(s)] = (new Date).getTime()", key: Bv(234), appliesToPx561: true, isTbr9: Bv(234) === target },
    { line: 8523, expression: "w.d[R(h)] = po()", key: Bv(241), appliesToPx561: true, isTbr9: Bv(241) === target },
    { line: 8523, expression: "w.d[R(d)] = Sv", key: Bv(276), appliesToPx561: true, isTbr9: Bv(276) === target },
    { line: 8523, expression: "w.d[R(v)] = Tv", key: Bv(260), appliesToPx561: true, isTbr9: Bv(260) === target },
  ];

  const tfCalls = [
    {
      line: 8527,
      expression: "var F = tf(A, np)",
      source: "np[un] flushes queued activities after deleting ts and adding common fields.",
    },
    {
      line: 8591,
      expression: "tf(p, np)",
      source: "np[ln] beacon path over rp() queued activities.",
    },
    {
      line: 8600,
      expression: "tf(m[g], np)",
      source: "np[ln] XHR/noCors path over filtered queued activities.",
    },
  ];

  const result = {
    inputs: {
      main: mainPath,
      minimalExperiment: path.join(outDir, "tbr9_minimal_yc_tf_experiment.json"),
    },
    decoder: {
      table: "Nv/Bv",
      rotations: rotated.rotations,
      decoded,
    },
    queueFlow: [
      {
        stage: "$c/jc -> Rc",
        evidence: "main.beautified.js:3048 and 3078-3079 call Rc(type,Yc(...)); qc(ds) at line 9208 binds Rc=ds.",
        px561Meaning: "PX561 reaches ds as already-Yc-flattened d object.",
      },
      {
        stage: "ds",
        evidence: "main.beautified.js:3455-3468 mutates d with HU/R3 and pushes {t,d,ts} into ss or ls.",
        mutations: dsMutations,
      },
      {
        stage: "rp/scheduled flush",
        evidence: "main.beautified.js:8630-8638 uses ss.splice(0,o) to take up to 10 queued entries; no d mutation.",
      },
      {
        stage: "np[sn] ls flush",
        evidence: "main.beautified.js:8560-8567 copies ls with splice(0,len) and calls np[un](r,true); no d mutation before np[un].",
      },
      {
        stage: "np[un]",
        evidence: "main.beautified.js:8515-8528 deletes ts, optionally mutates special activity types, appends common fields, then calls tf(A,np).",
        specialTypes: unSpecialTypes,
        px561IsSpecialType: unSpecialTypes.includes("PX561"),
        specialMutations: unSpecialMutations,
        commonMutations: unCommonMutations,
        tfCalls: [tfCalls[0]],
      },
      {
        stage: "np[ln]",
        evidence: "main.beautified.js:8568-8601 calls tf(p,np) or tf(m[g],np) over rp() output / filtered groups; visible code does not add semantic fields before tf.",
        tfCalls: tfCalls.slice(1),
      },
    ],
    sourceSnippets: {
      ds: lineSnippet(lines, 3455, 3468),
      np_un: lineSnippet(lines, 8514, 8528),
      np_sn_ln: lineSnippet(lines, 8560, 8601),
      qc_bind: lineSnippet(lines, 9204, 9209),
    },
    checks: {
      anyDsMutationIsTbr9: dsMutations.some((m) => m.isTbr9),
      px561SpecialBranchInNpUn: unSpecialTypes.includes("PX561"),
      anyNpUnMutationIsTbr9: [...unSpecialMutations, ...unCommonMutations].some((m) => m.isTbr9),
      anyVisibleQueueToTfTbr9Producer: false,
    },
    findings: [
      "qc(ds) binds Rc to ds, so $c(PX561,r) reaches ds as Rc('PX561', Yc(r,'PX561')).",
      "ds mutates the queued d object only by adding HUlnQ1slanM= and R3c9PQEXNg8= before pushing {t,d,ts}.",
      "rp() and np[sn] use splice to select queued entries but do not mutate activity.d before np[un].",
      "np[un] deletes the wrapper ts, appends four common fields to every activity.d, and calls tf(A,np).",
      "The np[un] special branch applies only to decoded types Y1NZWSUzXWs= and GCQiLl1BJhk=, not PX561.",
      "No decoded ds/np[un]/np[ln] visible mutation key equals TBR9Ugl7emA=.",
      "Therefore visible queue-to-tf code does not explain insertion or overwrite of the final 127-byte TBR9 in PX561.",
    ],
    conclusion: "The visible Rc/ds queue through np[un]/np[ln] to tf(A,np) path does not contain a TBR9 producer or PX561-specific normalizer. The remaining TBR9 gap must be before ds, inside/after tf/Vs/ut interpretation, or in runtime behavior not represented by these visible static mutations.",
  };

  fs.mkdirSync(outDir, { recursive: true });
  const jsonPath = path.join(outDir, "tbr9_queue_to_tf_static_audit.json");
  const mdPath = path.join(outDir, "tbr9_queue_to_tf_static_audit.md");
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

  const md = [
    "# TBR9 queue-to-tf static audit",
    "",
    "## Decoded mutation keys",
    "",
    "| site | expression | key | applies to PX561 | is TBR9 |",
    "|---|---|---|---:|---:|",
    ...dsMutations.map((m) => `| ds:${m.line} | \`${m.expression}\` | \`${m.key}\` | \`${m.appliesToPx561}\` | \`${m.isTbr9}\` |`),
    ...unSpecialMutations.map((m) => `| np[un]:${m.line} special | \`${m.expression}\` | \`${m.key}\` | \`${m.appliesToPx561}\` | \`${m.isTbr9}\` |`),
    ...unCommonMutations.map((m) => `| np[un]:${m.line} common | \`${m.expression}\` | \`${m.key}\` | \`${m.appliesToPx561}\` | \`${m.isTbr9}\` |`),
    "",
    "## Checks",
    "",
    ...Object.entries(result.checks).map(([k, v]) => `- ${k}: \`${v}\``),
    "",
    "## Findings",
    "",
    ...result.findings.map((x) => `- ${x}`),
    "",
    "## Conclusion",
    "",
    result.conclusion,
    "",
  ].join("\n");
  fs.writeFileSync(mdPath, md, "utf8");
  console.log(JSON.stringify({ json: jsonPath, md: mdPath }, null, 2));
}

main();
