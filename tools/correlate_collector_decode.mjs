#!/usr/bin/env node
import crypto from "crypto";
import fs from "fs";
import path from "path";

const repo = process.cwd();
const traceDir = path.join(repo, "output/outlook_browser");
const outDir = path.join(traceDir, "js_static_analysis/collector_decode_correlation");

const baselineSamples = [
  {
    label: "success_ni109xdjp5zp",
    outcome: "success",
    runtime: "runtime_trace_ni109xdjp5zp_1780948211.jsonl",
    js: "js_internal_trace_ni109xdjp5zp_1780948211.jsonl",
  },
  {
    label: "failure_hcxwyrtiudbg",
    outcome: "failure",
    runtime: "runtime_trace_hcxwyrtiudbg_1780949301.jsonl",
    js: "js_internal_trace_hcxwyrtiudbg_1780949301.jsonl",
  },
  {
    label: "riskblock_s88goaaiys9e",
    outcome: "riskBlock",
    runtime: "runtime_trace_s88goaaiys9e_1780984922.jsonl",
    js: "js_internal_trace_s88goaaiys9e_1780984922.jsonl",
  },
  {
    label: "partial_squvyrbsp1tp",
    outcome: "password_input_not_found",
    runtime: "runtime_trace_squvyrbsp1tp_1780984971.jsonl",
    js: "js_internal_trace_squvyrbsp1tp_1780984971.jsonl",
  },
  {
    label: "riskblock_ia8z6qxv8ku8",
    outcome: "riskBlock",
    runtime: "runtime_trace_ia8z6qxv8ku8_1780985000.jsonl",
    js: "js_internal_trace_ia8z6qxv8ku8_1780985000.jsonl",
  },
];

function inferOutcomeFromRuntime(runtimeFile) {
  const runtimePath = path.join(traceDir, runtimeFile);
  const rows = parseJsonl(runtimePath);
  const text = rows.map((row) => String(row.body || row.text || "")).join("\n");
  if (text.includes("redirectUrl")) return "success";
  if (text.includes("riskChallengeRequired")) return "riskChallengeRequired";
  if (text.includes("riskBlock") || text.includes("AADSTS7005106")) return "riskBlock";
  if (text.includes('"code":"1059"')) return "CreateAccount_1059";
  if (text.includes("account creation blocked") || text.includes("帐户创建已被阻止")) return "account_creation_blocked";
  return "observed";
}

function discoverTraceSamples() {
  if (!fs.existsSync(traceDir)) return [];
  const files = fs.readdirSync(traceDir);
  const runtimeById = new Map();
  const jsById = new Map();
  for (const file of files) {
    let m = file.match(/^runtime_trace_(.+_\d+)\.jsonl$/);
    if (m) runtimeById.set(m[1], file);
    m = file.match(/^js_internal_trace_(.+_\d+)\.jsonl$/);
    if (m) jsById.set(m[1], file);
  }
  const baselineRuntime = new Set(baselineSamples.map((x) => x.runtime));
  const jsEntries = [...jsById.entries()];
  const usedJsIds = new Set();
  function matchingJsId(runtimeId) {
    if (jsById.has(runtimeId)) return runtimeId;
    const m = runtimeId.match(/^(.+_)(\d+)$/);
    if (!m) return "";
    const prefix = m[1];
    const ts = Number(m[2]);
    const candidates = jsEntries
      .filter(([id]) => id.startsWith(prefix))
      .map(([id]) => ({ id, ts: Number(id.match(/_(\d+)$/)?.[1] || 0) }))
      .filter((x) => Number.isFinite(x.ts) && Math.abs(x.ts - ts) <= 2)
      .sort((a, b) => Math.abs(a.ts - ts) - Math.abs(b.ts - ts));
    return candidates[0]?.id || "";
  }
  return [...runtimeById.entries()]
    .map(([id, runtime]) => ({ id, runtime, jsId: matchingJsId(id) }))
    .filter(({ runtime, jsId }) => jsId && !usedJsIds.has(jsId) && !baselineRuntime.has(runtime))
    .sort((a, b) => {
      const at = Number(a.id.match(/_(\d+)$/)?.[1] || 0);
      const bt = Number(b.id.match(/_(\d+)$/)?.[1] || 0);
      return at - bt;
    })
    .map(({ id, runtime, jsId }) => {
      usedJsIds.add(jsId);
      return ({
      label: `observed_${id.replace(/[^A-Za-z0-9_]/g, "_")}`,
      outcome: inferOutcomeFromRuntime(runtime),
      runtime,
      js: jsById.get(jsId),
    });
    });
}

const samples = [...baselineSamples, ...discoverTraceSamples()];

function parseJsonl(file) {
  const rows = [];
  if (!fs.existsSync(file)) return rows;
  for (const [idx, line] of fs.readFileSync(file, "utf8").split(/\n/).entries()) {
    if (!line.trim()) continue;
    try {
      rows.push({ lineNo: idx + 1, ...JSON.parse(line) });
    } catch (error) {
      rows.push({ lineNo: idx + 1, kind: "parse_error", error: String(error) });
    }
  }
  return rows;
}

function sha16(value) {
  const s = String(value || "");
  if (!s) return "";
  return crypto.createHash("sha256").update(s).digest("hex").slice(0, 16);
}

function tryJson(value) {
  if (typeof value !== "string") return value;
  let current = value.trim();
  for (let i = 0; i < 3; i += 1) {
    try {
      const parsed = JSON.parse(current);
      if (typeof parsed === "string") {
        current = parsed.trim();
        continue;
      }
      return parsed;
    } catch {
      return current;
    }
  }
  return current;
}

function parseCollectorObjectFromArg(value) {
  const parsed = tryJson(value);
  if (parsed && typeof parsed === "object") return parsed;
  if (typeof parsed !== "string") return null;
  const second = tryJson(parsed);
  return second && typeof second === "object" ? second : null;
}

function summarizeOb(ob) {
  const s = String(ob || "");
  return {
    present: Boolean(s),
    len: s.length,
    sha16: sha16(s),
  };
}

function partInfo(part) {
  const fields = String(part || "").split("|");
  const key = fields[0] || "";
  const info = { key, fieldsLen: fields.length };
  if (key === "IoIoIo" && fields[1] === "score") {
    info.kind = "score";
    info.value = fields[2] || "";
  } else if (key === "oIIoIooo") {
    info.kind = "captcha_result_callback";
    info.value = fields[1] || "";
  } else if (key === "IoooII" && fields[1] === "_px3") {
    info.kind = "px3";
    info.tokenShape = tokenShape(fields[3]);
  } else if (key === "oIIoIIoo" && fields[1] === "_pxde") {
    info.kind = "pxde";
    info.tokenShape = tokenShape(fields[3]);
  } else if (key === "IooIoo") {
    info.kind = "pxvid";
  }
  return info;
}

function tokenShape(token) {
  const s = String(token || "");
  return {
    present: Boolean(s),
    len: s.length,
    segments: s ? s.split(":").length : 0,
    prefixLen: s.split(":")[0]?.length || 0,
  };
}

function extractJsCollectorEvents(jsRows) {
  const events = [];
  for (const row of jsRows) {
    if (row.kind === "hsprotect.Xn.trigger") {
      const channel = row.data?.channel;
      if (channel !== "xhrResponse" && channel !== "xhrSuccess") continue;
      const args = Array.isArray(row.data?.args) ? row.data.args : [];
      const obj = args.map(parseCollectorObjectFromArg).find((x) => x?.ob);
      if (!obj) continue;
      events.push({
        source: `Xn.${channel}`,
        lineNo: row.lineNo,
        wall_t: row.wall_t,
        perf_t: row.perf_t,
        ob: summarizeOb(obj.ob),
        doValue: obj.do ?? null,
      });
    }

    if (row.kind === "hsprotect.main.fp.enter") {
      const obj = parseCollectorObjectFromArg(row.data?.t);
      if (!obj?.ob) continue;
      events.push({
        source: "fp.enter",
        lineNo: row.lineNo,
        wall_t: row.wall_t,
        perf_t: row.perf_t,
        ob: summarizeOb(obj.ob),
        doValue: obj.do ?? null,
      });
    }
  }
  return events.sort((a, b) => a.lineNo - b.lineNo);
}

function extractDecodePackets(jsRows, collectorEvents) {
  const decodeRows = jsRows.filter((row) => row.kind === "hsprotect.main.om.decode");
  return decodeRows
    .map((row, index) => {
      const nextDecodeLine = decodeRows[index + 1]?.lineNo ?? Infinity;
      const parts = Array.isArray(row.data?.parts) ? row.data.parts : [];
      const infos = parts.map(partInfo);
      const keys = infos.map((x) => x.key);
      const prevCollector = [...collectorEvents].reverse().find((x) => x.lineNo <= row.lineNo) || null;
      const nextOt = jsRows.find((x) => x.kind === "hsprotect.captcha.Ot.enter" && x.lineNo >= row.lineNo && x.lineNo < nextDecodeLine) || null;
      const nextSucceededMessage = jsRows.find((x) => {
        if (x.kind !== "window.message.recv" || x.lineNo < row.lineNo || x.lineNo >= nextDecodeLine) return false;
        try {
          const raw = x.data?.data;
          const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
          return parsed?.type === "succeeded";
        } catch {
          return false;
        }
      }) || null;
      return {
        lineNo: row.lineNo,
        wall_t: row.wall_t,
        perf_t: row.perf_t,
        partCount: parts.length,
        nextDecodeLine: Number.isFinite(nextDecodeLine) ? nextDecodeLine : null,
        keys,
        uniqueKeys: [...new Set(keys)],
        scores: infos.filter((x) => x.kind === "score").map((x) => x.value),
        hasPx3: infos.some((x) => x.kind === "px3"),
        hasPxde: infos.some((x) => x.kind === "pxde"),
        hasPxvid: infos.some((x) => x.kind === "pxvid"),
        hasOIIoIooo0: infos.some((x) => x.kind === "captcha_result_callback" && x.value === "0"),
        correlatedCollector: prevCollector
          ? {
              source: prevCollector.source,
              lineNo: prevCollector.lineNo,
              deltaLine: row.lineNo - prevCollector.lineNo,
              deltaMs: typeof row.wall_t === "number" && typeof prevCollector.wall_t === "number"
                ? Math.round((row.wall_t - prevCollector.wall_t) * 1000)
                : null,
              ob: prevCollector.ob,
            }
          : null,
        nextOt: nextOt
          ? {
              lineNo: nextOt.lineNo,
              r: nextOt.data?.r ?? null,
              state: nextOt.data?.state ?? null,
            }
          : null,
        nextSucceededMessage: nextSucceededMessage ? { lineNo: nextSucceededMessage.lineNo } : null,
      };
    });
}

function extractRuntimeBuckets(runtimeRows) {
  const requests = runtimeRows
    .filter((row) => row.kind === "collector.request.bucket")
    .map((row) => ({
      lineNo: row.lineNo,
      t: row.t,
      collectorSeqNo: row.collector_seq_no,
      endpoint: row.endpoint,
      postLen: row.post_len,
      payloadLen: row.payload?.len ?? null,
      seq: row.fields?.seq ?? null,
      rsc: row.fields?.rsc ?? null,
      hasUuid: Boolean(row.fields?.uuid?.present),
      hasVid: Boolean(row.fields?.vid?.present),
      hasCs: Boolean(row.fields?.cs?.present),
      hasPc: Boolean(row.fields?.pc?.present),
    }));
  const responses = runtimeRows
    .filter((row) => row.kind === "collector.response.bucket")
    .map((row) => ({
      lineNo: row.lineNo,
      t: row.t,
      collectorSeqNo: row.collector_seq_no,
      endpoint: row.endpoint,
      status: row.status,
      bodyLen: row.body_len,
      ob: row.ob || summarizeOb(""),
      jsonKeys: row.json_keys || [],
    }));
  return { requests, responses };
}

function messageType(row) {
  if (row.kind !== "window.message.recv") return "";
  try {
    const raw = row.data?.data;
    const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
    return String(parsed?.type || "");
  } catch {
    return "";
  }
}

function extractOtRuntimeCorrelation(jsRows, runtimeBuckets, runtimeOutcome) {
  const responses = runtimeBuckets.responses
    .filter((row) => typeof row.t === "number")
    .sort((a, b) => a.t - b.t);
  const riskRows = runtimeOutcome.riskVerify || [];
  const createRows = runtimeOutcome.createAccount || [];
  return jsRows
    .filter((row) => row.kind === "hsprotect.captcha.Ot.enter")
    .map((row, index, otRows) => {
      const wallT = typeof row.wall_t === "number" ? row.wall_t : null;
      const nextOtWallT = typeof otRows[index + 1]?.wall_t === "number" ? otRows[index + 1].wall_t : null;
      const beforeNextOt = (x) => (
        typeof x.t === "number"
        && wallT !== null
        && x.t >= wallT
        && (nextOtWallT === null || x.t < nextOtWallT)
      );
      const previous = wallT === null
        ? null
        : [...responses].reverse().find((x) => x.t <= wallT + 0.002) || null;
      const parent = jsRows.find((x) => x.lineNo >= row.lineNo && x.lineNo <= row.lineNo + 8 && messageType(x)) || null;
      const nextRisk = riskRows.find(beforeNextOt) || null;
      const nextCreate = createRows.find(beforeNextOt) || null;
      return {
        lineNo: row.lineNo,
        wall_t: row.wall_t,
        r: row.data?.r ?? null,
        state: row.data?.state ?? null,
        zero: Boolean(row.data?.zero),
        stackHasSuccessHandler: String(row.data?.stack || "").includes("oIIoIooo"),
        previousRuntimeResponse: previous
          ? {
              lineNo: previous.lineNo,
              collectorSeqNo: previous.collectorSeqNo,
              endpoint: previous.endpoint,
              status: previous.status,
              ob: previous.ob || summarizeOb(""),
              deltaMs: wallT === null ? null : Math.round((wallT - previous.t) * 1000),
            }
          : null,
        parentMessage: parent ? { lineNo: parent.lineNo, type: messageType(parent) } : null,
        nextRisk,
        nextCreate,
      };
    });
}

function extractRuntimeOutcome(runtimeRows) {
  const risk = runtimeRows.filter((row) => row.kind === "response" && String(row.url || "").includes("risk/verify"));
  const create = runtimeRows.filter((row) => row.kind === "response" && String(row.url || "").includes("API/CreateAccount"));
  return {
    riskVerify: risk.map((row) => ({
      lineNo: row.lineNo,
      t: row.t,
      status: row.status,
      stateContinue: String(row.body || "").includes('"state":"continue"'),
      riskBlock: String(row.body || "").includes("riskBlock") || String(row.body || "").includes("AADSTS7005106"),
    })),
    createAccount: create.map((row) => {
      const body = String(row.body || "");
      const code = body.match(/"code":"([^"]+)"/)?.[1] || null;
      return {
        lineNo: row.lineNo,
        t: row.t,
        status: row.status,
        hasRedirectUrl: body.includes("redirectUrl"),
        code,
      };
    }),
  };
}

function extractRuntimeMeta(runtimeRows) {
  const runMetaRow = runtimeRows.find((row) => row.kind === "run.meta");
  const runMeta = runMetaRow?.meta || {};
  const evidences = runtimeRows.filter((row) => row.kind === "browser.evidence");
  const firstEvidence = evidences[0] || {};
  const lastEvidence = evidences[evidences.length - 1] || firstEvidence;
  function egressIp(row) {
    const body = String(row?.egress?.body || "");
    try {
      const parsed = JSON.parse(body);
      return String(parsed.ip || "");
    } catch {
      return body.match(/"ip"\s*:\s*"([^"]+)"/)?.[1] || "";
    }
  }
  return {
    hasRunMeta: Boolean(runMetaRow),
    proxyEnabled: Boolean(runMeta?.proxy?.enabled),
    proxyEndpoint: String(runMeta?.proxy?.endpoint || ""),
    proxyEndpointSha16: String(runMeta?.proxy?.endpoint_sha16 || ""),
    proxyHasAuth: Boolean(runMeta?.proxy?.has_auth),
    geoip: Boolean(runMeta?.geoip),
    camoufoxOs: String(runMeta?.camoufox?.os || ""),
    locale: String(runMeta?.camoufox?.locale || ""),
    egressIp: egressIp(lastEvidence),
    timezone: String((lastEvidence?.fingerprint || firstEvidence?.fingerprint || {}).timezone || ""),
    language: String((lastEvidence?.fingerprint || firstEvidence?.fingerprint || {}).language || ""),
  };
}

function summarizeSample(def) {
  const runtimePath = path.join(traceDir, def.runtime);
  const jsPath = path.join(traceDir, def.js);
  const runtimeRows = parseJsonl(runtimePath);
  const jsRows = parseJsonl(jsPath);
  const collectorEvents = extractJsCollectorEvents(jsRows);
  const decodePackets = extractDecodePackets(jsRows, collectorEvents);
  const runtimeBuckets = extractRuntimeBuckets(runtimeRows);
  const runtimeOutcome = extractRuntimeOutcome(runtimeRows);
  return {
    label: def.label,
    outcome: def.outcome,
    source: {
      runtime: path.relative(repo, runtimePath),
      js: path.relative(repo, jsPath),
    },
    counts: {
      runtimeRows: runtimeRows.length,
      jsRows: jsRows.length,
      jsCollectorEvents: collectorEvents.length,
      decodePackets: decodePackets.length,
      runtimeCollectorRequests: runtimeBuckets.requests.length,
      runtimeCollectorResponses: runtimeBuckets.responses.length,
    },
    jsCollectorEvents: collectorEvents,
    decodePackets,
    runtimeBuckets,
    runtimeMeta: extractRuntimeMeta(runtimeRows),
    runtimeOutcome,
    otRuntimeCorrelation: extractOtRuntimeCorrelation(jsRows, runtimeBuckets, runtimeOutcome),
  };
}

function mdBool(value) {
  return value ? "yes" : "no";
}

function markdown(report) {
  const lines = [];
  lines.push("# collector response / JS decode correlation");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push("");
  lines.push("## Sample summary");
  lines.push("");
  lines.push("| sample | outcome | proxy | egress | tz | js collector | decode packets | runtime buckets | terminal signal |");
  lines.push("|---|---|---:|---|---|---:|---:|---:|---|");
  for (const s of report.samples) {
    const riskSignals = s.runtimeOutcome.riskVerify.map((x) => x.riskBlock ? `riskBlock@${x.lineNo}` : x.stateContinue ? `continue@${x.lineNo}` : `status${x.status}@${x.lineNo}`);
    const createSignals = s.runtimeOutcome.createAccount.map((x) => x.hasRedirectUrl ? `redirect@${x.lineNo}` : x.code ? `${x.code}@${x.lineNo}` : `status${x.status}@${x.lineNo}`);
    const proxyCell = !s.runtimeMeta.hasRunMeta
      ? "unknown"
      : s.runtimeMeta.proxyEnabled
        ? `yes:${s.runtimeMeta.proxyEndpoint || s.runtimeMeta.proxyEndpointSha16 || "unknown"}`
        : "no";
    lines.push(`| ${s.label} | ${s.outcome} | ${proxyCell} | ${s.runtimeMeta.egressIp || "-"} | ${s.runtimeMeta.timezone || "-"} | ${s.counts.jsCollectorEvents} | ${s.counts.decodePackets} | ${s.counts.runtimeCollectorResponses} | ${[...riskSignals, ...createSignals].join(", ") || "-"} |`);
  }
  lines.push("");
  lines.push("## Decode packets correlated to previous collector response");
  lines.push("");
  lines.push("| sample | decode line | previous collector | delta | ob len | ob sha16 | keys | scores | oIIoIooo=0 | next Ot | parent succeeded |");
  lines.push("|---|---:|---|---:|---:|---|---|---|---:|---|---:|");
  for (const s of report.samples) {
    if (!s.decodePackets.length) {
      lines.push(`| ${s.label} | - | - | - | - | - | no om.decode observed | - | no | - | no |`);
      continue;
    }
    for (const p of s.decodePackets) {
      const prev = p.correlatedCollector;
      lines.push(`| ${s.label} | ${p.lineNo} | ${prev ? `${prev.source}@${prev.lineNo}` : "-"} | ${prev?.deltaMs ?? "-"} | ${prev?.ob?.len ?? "-"} | ${prev?.ob?.sha16 || "-"} | ${p.uniqueKeys.join(",")} | ${p.scores.join(",") || "-"} | ${mdBool(p.hasOIIoIooo0)} | ${p.nextOt ? `${p.nextOt.r}:${p.nextOt.state}@${p.nextOt.lineNo}` : "-"} | ${mdBool(Boolean(p.nextSucceededMessage))} |`);
    }
  }
  lines.push("");
  lines.push("## Ot events correlated to previous runtime collector response");
  lines.push("");
  lines.push("| sample | Ot line | r | state | stack has oIIoIooo | previous runtime response | delta ms | obLen | obSha16 | parent message | terminal signal |");
  lines.push("|---|---:|---:|---|---:|---|---:|---:|---|---|---|");
  for (const s of report.samples) {
    if (!s.otRuntimeCorrelation.length) {
      lines.push(`| ${s.label} | - | - | - | no | - | - | - | - | no Ot observed | - |`);
      continue;
    }
    for (const ot of s.otRuntimeCorrelation) {
      const prev = ot.previousRuntimeResponse;
      const terminal = [
        ot.nextRisk
          ? (ot.nextRisk.riskBlock ? `riskBlock@${ot.nextRisk.lineNo}` : ot.nextRisk.stateContinue ? `continue@${ot.nextRisk.lineNo}` : `riskStatus${ot.nextRisk.status}@${ot.nextRisk.lineNo}`)
          : "",
        ot.nextCreate
          ? (ot.nextCreate.hasRedirectUrl ? `redirect@${ot.nextCreate.lineNo}` : ot.nextCreate.code ? `${ot.nextCreate.code}@${ot.nextCreate.lineNo}` : `createStatus${ot.nextCreate.status}@${ot.nextCreate.lineNo}`)
          : "",
      ].filter(Boolean).join(", ") || "-";
      lines.push(`| ${s.label} | ${ot.lineNo} | ${ot.r ?? "-"} | ${ot.state || "-"} | ${mdBool(ot.stackHasSuccessHandler)} | ${prev ? `seq${prev.collectorSeqNo}:${prev.endpoint}@${prev.lineNo}` : "-"} | ${prev?.deltaMs ?? "-"} | ${prev?.ob?.len ?? "-"} | ${prev?.ob?.sha16 || "-"} | ${ot.parentMessage ? `${ot.parentMessage.type}@${ot.parentMessage.lineNo}` : "-"} | ${terminal} |`);
    }
  }
  lines.push("");
  lines.push("## Runtime collector buckets");
  lines.push("");
  lines.push("| sample | request line | response line | collectorSeq | formSeq | rsc | payloadLen | uuid | vid | cs | pc | obLen | obSha16 |");
  lines.push("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|");
  for (const s of report.samples) {
    const seqs = new Set([
      ...s.runtimeBuckets.requests.map((x) => x.collectorSeqNo),
      ...s.runtimeBuckets.responses.map((x) => x.collectorSeqNo),
    ].filter((x) => x !== null && x !== undefined));
    if (!seqs.size) {
      lines.push(`| ${s.label} | - | - | - | - | - | - | - | - | - | - | - | no runtime bucket in this older trace |`);
      continue;
    }
    const reqBySeq = new Map(s.runtimeBuckets.requests.map((x) => [x.collectorSeqNo, x]));
    const resBySeq = new Map(s.runtimeBuckets.responses.map((x) => [x.collectorSeqNo, x]));
    for (const seq of [...seqs].sort((a, b) => Number(a) - Number(b))) {
      const req = reqBySeq.get(seq) || {};
      const res = resBySeq.get(seq) || {};
      lines.push(`| ${s.label} | ${req.lineNo ?? "-"} | ${res.lineNo ?? "-"} | ${seq} | ${req.seq ?? "-"} | ${req.rsc ?? "-"} | ${req.payloadLen ?? "-"} | ${mdBool(req.hasUuid)} | ${mdBool(req.hasVid)} | ${mdBool(req.hasCs)} | ${mdBool(req.hasPc)} | ${res.ob?.len ?? "-"} | ${res.ob?.sha16 || "-"} |`);
    }
  }
  lines.push("");
  lines.push("## Evidence-backed observations");
  lines.push("");
  lines.push("- Historical success has a JS-level collector response immediately followed by `om.decode` containing `oIIoIooo|0`; that decode then reaches `Ot(0)` and parent `succeeded`.");
  lines.push("- Historical failure has JS-level collector responses and cookie/risk handlers, but no decoded `oIIoIooo|0`, no `Ot`, and no parent `succeeded`.");
  lines.push("- New riskBlock samples have runtime collector response buckets, but no `om.decode` in the JS internal trace; they prove the bucket observer works, not why the server selects the success callback.");
  lines.push("- Raw `ob`, `_px3`, `_pxde`, `payload`, `pc`, and `cs` values are per-run unstable. The comparable evidence is phase, length bucket, handler keys, score values, and next state transition.");
  return lines.join("\n") + "\n";
}

fs.mkdirSync(outDir, { recursive: true });
const report = {
  generatedAt: new Date().toISOString(),
  samples: samples.map(summarizeSample),
};
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(outDir, `collector_decode_correlation_${stamp}.json`);
const mdPath = path.join(outDir, `collector_decode_correlation_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(mdPath, markdown(report), "utf8");
console.log(JSON.stringify({ jsonPath, mdPath }, null, 2));
