#!/usr/bin/env node
import fs from "fs";
import path from "path";
import {
  decodeOb,
  encodeOb,
  parseDecodedPart,
  runDecodedStateMachine,
  sha16,
} from "./hsprotect_ob_codec.mjs";

const repo = process.cwd();
const traceDir = path.join(repo, "output/outlook_browser");
const outDir = path.join(traceDir, "js_static_analysis/protocol_reverse");

const samples = [
  {
    label: "success_ni109xdjp5zp",
    outcome: "success",
    js: path.join(traceDir, "js_internal_trace_ni109xdjp5zp_1780948211.jsonl"),
    runtime: path.join(traceDir, "runtime_trace_ni109xdjp5zp_1780948211.jsonl"),
  },
  {
    label: "success_zel89cqywfov",
    outcome: "success",
    js: path.join(traceDir, "js_internal_trace_zel89cqywfov_1780988665.jsonl"),
    runtime: path.join(traceDir, "runtime_trace_zel89cqywfov_1780988664.jsonl"),
  },
  {
    label: "failure_hcxwyrtiudbg",
    outcome: "failure",
    js: path.join(traceDir, "js_internal_trace_hcxwyrtiudbg_1780949301.jsonl"),
    runtime: path.join(traceDir, "runtime_trace_hcxwyrtiudbg_1780949301.jsonl"),
  },
  {
    label: "noninvasive_success_ifkaruehjmec",
    outcome: "success_no_decode_hook",
    js: path.join(traceDir, "js_internal_trace_ifkaruehjmec_1780995305.jsonl"),
    runtime: path.join(traceDir, "runtime_trace_ifkaruehjmec_1780995305.jsonl"),
  },
  {
    label: "rewrite_sample_k2y1qcudhaad",
    outcome: "failed_after_captcha_close_404",
    js: path.join(traceDir, "js_internal_trace_k2y1qcudhaad_1780997358.jsonl"),
    runtime: path.join(traceDir, "runtime_trace_k2y1qcudhaad_1780997358.jsonl"),
  },
].filter((x) => fs.existsSync(x.js));

function parseJsonl(file) {
  if (!fs.existsSync(file)) return [];
  return fs.readFileSync(file, "utf8")
    .split(/\n/)
    .map((line, idx) => ({ line, lineNo: idx + 1 }))
    .filter((x) => x.line.trim())
    .map(({ line, lineNo }) => {
      try {
        return { lineNo, ...JSON.parse(line) };
      } catch (error) {
        return { lineNo, kind: "parse_error", error: String(error) };
      }
    });
}

function safeJson(value) {
  try {
    return JSON.parse(String(value || ""));
  } catch {
    return null;
  }
}

function parseCollectorObject(value) {
  const parsed = safeJson(value);
  if (parsed && typeof parsed === "object") return parsed;
  if (typeof parsed === "string") {
    const second = safeJson(parsed);
    if (second && typeof second === "object") return second;
  }
  return null;
}

function extractJsCollectorEvents(jsRows) {
  const events = [];
  for (const row of jsRows) {
    if (row.kind === "hsprotect.main.fp.enter") {
      const obj = parseCollectorObject(row.data?.t);
      if (obj?.ob) {
        events.push({
          source: "fp.enter",
          lineNo: row.lineNo,
          wall_t: row.wall_t,
          ob: String(obj.ob),
          doValue: obj.do ?? null,
        });
      }
    }
    if (row.kind === "hsprotect.Xn.trigger") {
      const channel = row.data?.channel;
      if (channel !== "xhrResponse" && channel !== "xhrSuccess") continue;
      const args = Array.isArray(row.data?.args) ? row.data.args : [];
      const obj = args.map(parseCollectorObject).find((x) => x?.ob);
      if (obj?.ob) {
        events.push({
          source: `Xn.${channel}`,
          lineNo: row.lineNo,
          wall_t: row.wall_t,
          ob: String(obj.ob),
          doValue: obj.do ?? null,
        });
      }
    }
  }
  return events.sort((a, b) => a.lineNo - b.lineNo);
}

function messageType(row) {
  if (row.kind !== "window.message.recv") return "";
  const raw = row.data?.data;
  const parsed = typeof raw === "string" ? safeJson(raw) : raw;
  return parsed?.type || "";
}

function summarizeDecodedPacket(row, collectorEvents, jsRows) {
  const parts = Array.isArray(row.data?.parts) ? row.data.parts : [];
  const infos = parts.map(parseDecodedPart);
  const stateMachine = runDecodedStateMachine(parts);
  const previousCollector = [...collectorEvents].reverse().find((x) => x.lineNo <= row.lineNo) || null;
  const xorKey = Number(row.data?.mod);
  const decoded = String(row.data?.decoded || parts.join("~~~~"));
  const reencoded = Number.isFinite(xorKey) ? encodeOb(decoded, xorKey) : null;
  const decodedByCodec = previousCollector && Number.isFinite(xorKey)
    ? decodeOb(previousCollector.ob, xorKey)
    : null;
  const nextOt = jsRows.find((x) => x.kind === "hsprotect.captcha.Ot.enter" && x.lineNo >= row.lineNo) || null;
  const succeeded = jsRows.find((x) => x.lineNo >= row.lineNo && messageType(x) === "succeeded") || null;
  const dispatches = jsRows
    .filter((x) => x.kind === "hsprotect.main.jl.dispatch" && x.lineNo >= row.lineNo && x.lineNo <= (nextOt?.lineNo || row.lineNo + 40))
    .map((x) => ({ lineNo: x.lineNo, key: x.data?.handlerKey || "", args: x.data?.args || [] }));
  return {
    lineNo: row.lineNo,
    wall_t: row.wall_t,
    xor: {
      el: row.data?.el || "",
      mod: xorKey,
    },
    collector: previousCollector ? {
      source: previousCollector.source,
      lineNo: previousCollector.lineNo,
      deltaLine: row.lineNo - previousCollector.lineNo,
      deltaMs: typeof row.wall_t === "number" && typeof previousCollector.wall_t === "number"
        ? Math.round((row.wall_t - previousCollector.wall_t) * 1000)
        : null,
      obLen: previousCollector.ob.length,
      obSha16: sha16(previousCollector.ob),
    } : null,
    codecVerification: {
      decodedMatchesTrace: decodedByCodec ? decodedByCodec.decoded === decoded : null,
      reencodedMatchesCollector: previousCollector && reencoded ? reencoded.ob === previousCollector.ob.replace(/=+$/g, "") : null,
      decodedSha16: sha16(decoded),
    },
    parts: infos.map((x) => ({
      key: x.key,
      kind: x.kind || "unknown",
      score: x.score || "",
      result: x.result || "",
      tokenLen: x.token?.len ?? x.valueShape?.len ?? 0,
      valueSha16: x.value ? sha16(x.value) : "",
      rawSha16: sha16(x.raw),
    })),
    keys: [...new Set(infos.map((x) => x.key))],
    scores: infos.filter((x) => x.kind === "score").map((x) => x.score),
    cs: infos.find((x) => x.kind === "cs")?.token || null,
    hasOIIoIooo0: infos.some((x) => x.kind === "captcha_result_callback" && x.result === "0"),
    stateMachine,
    dispatches,
    nextOt: nextOt ? {
      lineNo: nextOt.lineNo,
      r: nextOt.data?.r,
      state: nextOt.data?.state,
      stackHasOIIoIooo: String(nextOt.data?.stack || "").includes("oIIoIooo"),
    } : null,
    parentSucceeded: succeeded ? { lineNo: succeeded.lineNo } : null,
  };
}

function summarizeRuntimeBuckets(runtimeRows) {
  const reqs = runtimeRows.filter((x) => x.kind === "collector.request.bucket");
  const resps = runtimeRows.filter((x) => x.kind === "collector.response.bucket");
  const reqBySeq = new Map(reqs.map((x) => [x.collector_seq_no, x]));
  return resps.map((res) => {
    const req = reqBySeq.get(res.collector_seq_no);
    return {
      collectorSeq: res.collector_seq_no,
      requestLine: req?.lineNo ?? null,
      responseLine: res.lineNo,
      endpoint: res.endpoint,
      formSeq: req?.fields?.seq ?? "",
      rsc: req?.fields?.rsc ?? "",
      payloadLen: req?.payload?.len ?? null,
      payloadSha16: req?.payload?.sha16 || "",
      obLen: res.ob?.len ?? 0,
      obSha16: res.ob?.sha16 || "",
    };
  });
}

function summarizeRuntimeDecodedResponses(runtimeRows, xorKey = 50) {
  const bucketRows = runtimeRows.filter((x) => x.kind === "collector.response.bucket");
  return runtimeRows
    .filter((x) => x.kind === "response" && String(x.url || "").includes("collector-pxzc5j78di.hsprotect.net"))
    .map((row) => {
      const parsed = safeJson(row.body || "");
      const ob = parsed?.ob ? String(parsed.ob) : "";
      const bucket = bucketRows.find((x) => x.lineNo > row.lineNo) || null;
      if (!ob) {
        return {
          responseLine: row.lineNo,
          bucketLine: bucket?.lineNo ?? null,
          collectorSeq: bucket?.collector_seq_no ?? null,
          endpoint: bucket?.endpoint || "",
          status: row.status,
          hasOb: false,
          obLen: 0,
          obSha16: "",
          decoded: null,
        };
      }
      const decoded = decodeOb(ob, xorKey);
      const stateMachine = runDecodedStateMachine(decoded.parts);
      return {
        responseLine: row.lineNo,
        bucketLine: bucket?.lineNo ?? null,
        collectorSeq: bucket?.collector_seq_no ?? null,
        endpoint: bucket?.endpoint || "",
        status: row.status,
        hasOb: true,
        obLen: ob.length,
        obSha16: sha16(ob),
        decoded: {
          xorKey,
          partCount: decoded.parts.length,
          keys: [...new Set(decoded.parts.map((x) => String(x).split("|")[0]))],
          scores: decoded.parts.filter((x) => x.startsWith("IoIoIo|score|")).map((x) => x.split("|")[2] || ""),
          hasOIIoIooo0: decoded.parts.some((x) => x === "oIIoIooo|0"),
          terminal: stateMachine.state.terminal,
          parts: decoded.parts.map((part) => {
            const parsedPart = parseDecodedPart(part);
            return {
              key: parsedPart.key,
              kind: parsedPart.kind || "unknown",
              score: parsedPart.score || "",
              result: parsedPart.result || "",
              tokenLen: parsedPart.token?.len ?? parsedPart.valueShape?.len ?? 0,
              valueSha16: parsedPart.value ? sha16(parsedPart.value) : "",
              rawSha16: sha16(part),
            };
          }),
        },
      };
    });
}

function summarizeSample(sample) {
  const jsRows = parseJsonl(sample.js);
  const runtimeRows = parseJsonl(sample.runtime);
  const collectorEvents = extractJsCollectorEvents(jsRows);
  const decodedPackets = jsRows
    .filter((x) => x.kind === "hsprotect.main.om.decode")
    .map((x) => summarizeDecodedPacket(x, collectorEvents, jsRows));
  const otRows = jsRows.filter((x) => x.kind === "hsprotect.captcha.Ot.enter");
  const messages = jsRows.filter((x) => messageType(x)).map((x) => ({ lineNo: x.lineNo, type: messageType(x) }));
  return {
    label: sample.label,
    outcome: sample.outcome,
    source: {
      js: sample.js,
      runtime: sample.runtime,
    },
    counts: {
      jsRows: jsRows.length,
      collectorEvents: collectorEvents.length,
      decodedPackets: decodedPackets.length,
      otEvents: otRows.length,
      runtimeBuckets: runtimeRows.filter((x) => x.kind === "collector.response.bucket").length,
    },
    decodedPackets,
    otEvents: otRows.map((x) => ({
      lineNo: x.lineNo,
      r: x.data?.r,
      state: x.data?.state,
      stackHasOIIoIooo: String(x.data?.stack || "").includes("oIIoIooo"),
    })),
    messages,
    runtimeBuckets: summarizeRuntimeBuckets(runtimeRows),
    runtimeDecodedResponses: summarizeRuntimeDecodedResponses(runtimeRows, 50),
  };
}

function mdBool(v) {
  return v ? "yes" : "no";
}

function markdown(report) {
  const lines = [];
  lines.push("# hsprotect protocol reverse workbench");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push("");
  lines.push("## Offline codec proof");
  lines.push("");
  lines.push("Static function evidence from `har_main.beautified.js`:");
  lines.push("");
  lines.push("```text");
  lines.push("Wl(e): JSON-parse collector response, return n.do || n.ob");
  lines.push("j(t): base64 decode");
  lines.push("ne(t,e): XOR every char with e");
  lines.push("om(e,n): decoded = ne(j(ob), parseInt(el(Tt()),10)%128); parts = decoded.split('~~~~'); jl(parts,false)");
  lines.push("jl(parts,false): dispatch each part to Xl[handlerKey].apply({[xn]: queue}, args)");
  lines.push("Xl.oIIoIooo(t): Wc.apply(this, [t].concat(_l(this[xn])))");
  lines.push("oIIoIooo|0 -> Wc -> captcha Ot(0) -> succeeded");
  lines.push("```");
  lines.push("");
  lines.push("## Sample summary");
  lines.push("");
  lines.push("| sample | outcome | decoded packets | codec ok | oIIoIooo|0 | Ot states | succeeded msg | runtime buckets |");
  lines.push("|---|---|---:|---:|---:|---|---:|---:|");
  for (const s of report.samples) {
    const codecOk = s.decodedPackets.length
      ? s.decodedPackets.every((p) => p.codecVerification.decodedMatchesTrace && p.codecVerification.reencodedMatchesCollector)
      : false;
    const hasSuccess = s.decodedPackets.some((p) => p.hasOIIoIooo0)
      || s.runtimeDecodedResponses.some((p) => p.decoded?.hasOIIoIooo0);
    const ot = s.otEvents.map((x) => `${x.r}:${x.state}@${x.lineNo}`).join(", ") || "-";
    const succeeded = s.messages.some((x) => x.type === "succeeded");
    lines.push(`| ${s.label} | ${s.outcome} | ${s.counts.decodedPackets} | ${mdBool(codecOk)} | ${mdBool(hasSuccess)} | ${ot} | ${mdBool(succeeded)} | ${s.counts.runtimeBuckets} |`);
  }
  lines.push("");
  lines.push("## Decoded packet table");
  lines.push("");
  lines.push("| sample | decode line | collector | xor | decoded ok | reencode ok | keys | scores | csSha16 | terminal | next Ot |");
  lines.push("|---|---:|---|---:|---:|---:|---|---|---|---|---|");
  for (const s of report.samples) {
    if (!s.decodedPackets.length) {
      lines.push(`| ${s.label} | - | - | - | no decode hook | no decode hook | - | - | - | - | - |`);
      continue;
    }
    for (const p of s.decodedPackets) {
      const terminal = p.stateMachine.state.terminal;
      const collector = p.collector ? `${p.collector.source}@${p.collector.lineNo} obLen=${p.collector.obLen} sha16=${p.collector.obSha16}` : "-";
      const nextOt = p.nextOt ? `${p.nextOt.r}:${p.nextOt.state}@${p.nextOt.lineNo}` : "-";
      lines.push(`| ${s.label} | ${p.lineNo} | ${collector} | ${p.xor.mod} | ${mdBool(p.codecVerification.decodedMatchesTrace)} | ${mdBool(p.codecVerification.reencodedMatchesCollector)} | ${p.keys.join(",")} | ${p.scores.join(",") || "-"} | ${p.cs?.sha16 || "-"} | ${terminal} | ${nextOt} |`);
    }
  }
  lines.push("");
  lines.push("## Runtime response offline decode");
  lines.push("");
  lines.push("| sample | response line | bucket | endpoint | obLen | obSha16 | keys | scores | csSha16 | oIIoIooo|0 | terminal |");
  lines.push("|---|---:|---|---|---:|---|---|---|---|---:|---|");
  for (const s of report.samples) {
    const rows = s.runtimeDecodedResponses.filter((x) => x.hasOb);
    if (!rows.length) {
      lines.push(`| ${s.label} | - | - | - | - | - | no raw runtime ob | - | - | no | - |`);
      continue;
    }
    for (const row of rows) {
      const cs = row.decoded.parts.find((x) => x.kind === "cs");
      lines.push(`| ${s.label} | ${row.responseLine} | seq${row.collectorSeq ?? "?"}@${row.bucketLine ?? "-"} | ${row.endpoint || "-"} | ${row.obLen} | ${row.obSha16} | ${row.decoded.keys.join(",")} | ${row.decoded.scores.join(",") || "-"} | ${cs?.valueSha16 || "-"} | ${mdBool(row.decoded.hasOIIoIooo0)} | ${row.decoded.terminal} |`);
    }
  }
  lines.push("");
  lines.push("## State-machine rewrite target");
  lines.push("");
  lines.push("The offline state machine already reproduces the client-side terminal state from decoded parts:");
  lines.push("");
  lines.push("```text");
  lines.push("part IoIoIo|score|N|binary      -> score event");
  lines.push("part IoooII|_px3|...            -> cookie/risk token event");
  lines.push("part oIIoIIoo|_pxde|...         -> enrich token event");
  lines.push("part IoIIIo|cu                  -> challenge user/context marker");
  lines.push("part IoIIII|<hex>               -> cs event; Xl.IoIIII stores Yo, Li() returns Yo");
  lines.push("part oIIoIooo|0                 -> synthetic oIIoIooo('0') -> Wc -> Ot(0) -> succeeded");
  lines.push("absence of oIIoIooo|0           -> no local success transition");
  lines.push("```");
  lines.push("");
  lines.push("## Runtime bucket table for samples with bucket observer");
  lines.push("");
  lines.push("| sample | seq | endpoint | req line | res line | formSeq | rsc | payloadLen | payloadSha16 | obLen | obSha16 |");
  lines.push("|---|---:|---|---:|---:|---:|---:|---:|---|---:|---|");
  for (const s of report.samples) {
    for (const b of s.runtimeBuckets) {
      lines.push(`| ${s.label} | ${b.collectorSeq} | ${b.endpoint} | ${b.requestLine ?? "-"} | ${b.responseLine} | ${b.formSeq || "-"} | ${b.rsc || "-"} | ${b.payloadLen ?? "-"} | ${b.payloadSha16 || "-"} | ${b.obLen} | ${b.obSha16 || "-"} |`);
    }
  }
  return lines.join("\n") + "\n";
}

fs.mkdirSync(outDir, { recursive: true });
const report = {
  generatedAt: new Date().toISOString(),
  samples: samples.map(summarizeSample),
};
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(outDir, `hsprotect_protocol_reverse_${stamp}.json`);
const mdPath = path.join(outDir, `hsprotect_protocol_reverse_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(report), "utf8");
console.log(JSON.stringify({ jsonPath, mdPath }, null, 2));
