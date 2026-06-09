#!/usr/bin/env node
import fs from "fs";
import path from "path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function readJsonl(file) {
  const rows = [];
  if (!fs.existsSync(file)) return rows;
  const text = fs.readFileSync(file, "utf8");
  for (const [idx, line] of text.split(/\n/).entries()) {
    if (!line.trim()) continue;
    rows.push({ lineNo: idx + 1, ...JSON.parse(line) });
  }
  return rows;
}

function runtimePathFor(jsTrace) {
  const dir = path.dirname(jsTrace);
  const base = path.basename(jsTrace).replace(/^js_internal_trace_/, "runtime_trace_");
  const candidate = path.join(dir, base);
  return fs.existsSync(candidate) ? candidate : null;
}

function parseForm(body) {
  const params = new URLSearchParams(String(body || "").replace(/\+/g, "%2B"));
  const out = {};
  for (const [key, value] of params.entries()) out[key] = value;
  return out;
}

function summarizeCollectorRequest(row) {
  const params = parseForm(row.post_data);
  return {
    line: row.lineNo,
    t: row.t,
    method: row.method,
    url: row.url,
    headerKeys: Object.keys(row.headers || {}),
    headers: row.headers || {},
    post_len: row.post_len ?? String(row.post_data || "").length,
    params,
    paramKeys: Object.keys(params),
    payload_len: String(params.payload || "").length,
  };
}

function summarizeTf(row) {
  const d = row.data || {};
  const meta = d.meta || {};
  return {
    line: row.lineNo,
    wall_t: row.wall_t,
    href: row.href,
    origin: row.origin,
    frameTop: row.frameTop,
    payload: d.payload,
    payload_len: String(d.payload || "").length,
    pc: d.pc,
    meta,
    serialized: d.serialized,
    serialized_len: String(d.serialized || "").length,
    activity_count: Array.isArray(d.activities) ? d.activities.length : null,
    stack: String(d.stack || "").split("\n").filter(Boolean).slice(0, 10),
  };
}

function matchByPayload(tfEvents, requests) {
  return requests.map((req, index) => {
    const exactIndex = tfEvents.findIndex((tf) => tf.payload && tf.payload === req.params.payload);
    const tf = exactIndex >= 0 ? tfEvents[exactIndex] : tfEvents[index] || null;
    return {
      requestIndex: index,
      requestLine: req.line,
      tfLine: tf?.line ?? null,
      exactPayloadMatch: Boolean(tf && tf.payload === req.params.payload),
      payloadLenMatch: Boolean(tf && tf.payload_len === req.payload_len),
      appIdMatch: Boolean(tf && tf.meta?.appID === req.params.appId),
      tagMatch: Boolean(tf && tf.meta?.tag === req.params.tag),
      uuidMatch: Boolean(tf && tf.meta?.cu === req.params.uuid),
      pcMatch: Boolean(tf && String(tf.pc ?? tf.meta?.pc ?? "") === String(req.params.pc ?? "")),
      seq: req.params.seq,
      en: req.params.en,
      ft: req.params.ft,
      optionalParams: Object.fromEntries(
        Object.entries(req.params).filter(([k]) => !["payload", "appId", "tag", "uuid", "ft", "seq", "en"].includes(k)),
      ),
    };
  });
}

function baseName(tracePath) {
  return path.basename(tracePath, ".jsonl").replace(/^js_internal_trace_/, "").replace(/^runtime_trace_/, "");
}

function analyze(jsTrace) {
  const runtimeTrace = runtimePathFor(jsTrace);
  const jsRows = readJsonl(jsTrace);
  const runtimeRows = readJsonl(runtimeTrace);
  const tfEvents = jsRows.filter((r) => r.kind === "hsprotect.main.tf.payload").map(summarizeTf);
  const collectorRequests = runtimeRows
    .filter((r) => r.kind === "request" && String(r.url || "").includes("/api/v2/msft"))
    .map(summarizeCollectorRequest);
  const matches = matchByPayload(tfEvents, collectorRequests);

  const staticEvidence = [
    {
      file: path.join(repo, "output/outlook_browser/js_static_analysis/main.beautified.js"),
      lines: "4807-4852",
      fact: "tf(t,e) mutates activities, computes pc=Jt(ut(t), [po(),tag,ft].join(':')), calls Vs(t,d), then returns form params payload/appId/tag/uuid/ft/seq/en plus optional params.",
    },
    {
      file: path.join(repo, "output/outlook_browser/js_static_analysis/main.beautified.js"),
      lines: "3560-3598",
      fact: "Vs(t,d) stringifies/clones activity array, inserts an encoded metadata string into the serialized activity string at positions derived from cu.",
    },
    {
      file: path.join(repo, "output/outlook_browser/js_static_analysis/main.beautified.js"),
      lines: "321-340",
      fact: "ut(e) is the local JSON-like serializer used before pc/payload construction.",
    },
    {
      file: path.join(repo, "output/outlook_browser/js_static_analysis/main.beautified.js"),
      lines: "593-604",
      fact: "Jt(t,e) derives pc from P(t,e), then filters the transformed string.",
    },
  ];

  return {
    jsTrace,
    runtimeTrace,
    counts: {
      tfPayloadEvents: tfEvents.length,
      collectorRequests: collectorRequests.length,
      exactPayloadMatches: matches.filter((m) => m.exactPayloadMatch).length,
      appIdMatches: matches.filter((m) => m.appIdMatch).length,
      tagMatches: matches.filter((m) => m.tagMatch).length,
      uuidMatches: matches.filter((m) => m.uuidMatch).length,
      pcMatches: matches.filter((m) => m.pcMatch).length,
    },
    staticEvidence,
    tfEvents,
    collectorRequests,
    matches,
  };
}

function writeReport(result, outDir) {
  fs.mkdirSync(outDir, { recursive: true });
  const base = baseName(result.jsTrace);
  const jsonPath = path.join(outDir, `payload_chain_${base}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

  const md = [];
  md.push(`# HUMAN collector payload chain: ${base}`);
  md.push("");
  md.push(`jsTrace=${result.jsTrace}`);
  md.push(`runtimeTrace=${result.runtimeTrace}`);
  md.push("");
  md.push("## counts");
  for (const [k, v] of Object.entries(result.counts)) md.push(`- ${k}: ${v}`);
  md.push("");
  md.push("## static evidence");
  for (const ev of result.staticEvidence) md.push(`- ${ev.file}:${ev.lines} — ${ev.fact}`);
  md.push("");
  md.push("## request / tf match table");
  md.push("| idx | req line | tf line | payload | appId | tag | uuid | pc | seq | ft | optional |");
  md.push("|---:|---:|---:|---|---|---|---|---|---:|---:|---|");
  for (const m of result.matches) {
    md.push(
      `| ${m.requestIndex} | ${m.requestLine} | ${m.tfLine ?? ""} | ${m.exactPayloadMatch} | ${m.appIdMatch} | ${m.tagMatch} | ${m.uuidMatch} | ${m.pcMatch} | ${m.seq ?? ""} | ${m.ft ?? ""} | ${Object.keys(m.optionalParams).join(",")} |`,
    );
  }
  md.push("");
  md.push("## collector request params");
  for (const req of result.collectorRequests) {
    md.push(`### request line ${req.line}`);
    md.push(`- url=${req.url}`);
    md.push(`- post_len=${req.post_len}`);
    md.push(`- paramKeys=${req.paramKeys.join(",")}`);
    md.push(`- payload_len=${req.payload_len}`);
    md.push(`- appId=${req.params.appId}`);
    md.push(`- tag=${req.params.tag}`);
    md.push(`- uuid=${req.params.uuid}`);
    md.push(`- ft=${req.params.ft}`);
    md.push(`- seq=${req.params.seq}`);
    md.push(`- en=${req.params.en}`);
    md.push(`- pc=${req.params.pc}`);
    md.push("");
  }
  const mdPath = path.join(outDir, `payload_chain_${base}.md`);
  fs.writeFileSync(mdPath, md.join("\n"), "utf8");
  return { jsonPath, mdPath };
}

function main() {
  const traces = process.argv.slice(2);
  if (!traces.length) {
    console.error("usage: node tools/analyze_human_payload_chain.mjs <js_internal_trace.jsonl> [...]");
    process.exit(2);
  }
  const outDir = path.join(repo, "output/protocol_reverse/payload_chain");
  const outputs = traces.map((trace) => {
    const result = analyze(trace);
    return { trace, ...writeReport(result, outDir), counts: result.counts };
  });
  console.log(JSON.stringify(outputs, null, 2));
}

main();
