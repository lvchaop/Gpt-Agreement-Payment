#!/usr/bin/env node
import fs from "fs";
import path from "path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const analysisDir = path.join(repo, "output/outlook_browser/js_static_analysis");
const fullChainDir = path.join(analysisDir, "full_chain");
const outDir = path.join(analysisDir, "normalized_timeline");

const samples = [
  {
    label: "success_ni109xdjp5zp",
    outcome: "success",
    fullChain: path.join(fullChainDir, "full_chain_ni109xdjp5zp_1780948211.json"),
  },
  {
    label: "failure_hcxwyrtiudbg",
    outcome: "failure",
    fullChain: path.join(fullChainDir, "full_chain_hcxwyrtiudbg_1780949301.json"),
  },
];

function parseJsonl(file) {
  const rows = [];
  if (!fs.existsSync(file)) return rows;
  const text = fs.readFileSync(file, "utf8");
  for (const [idx, line] of text.split(/\n/).entries()) {
    if (!line.trim()) continue;
    rows.push({ lineNo: idx + 1, ...JSON.parse(line) });
  }
  return rows;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function parseForm(postData) {
  const out = {};
  const text = String(postData || "");
  for (const pair of text.split("&")) {
    if (!pair) continue;
    const idx = pair.indexOf("=");
    const key = idx >= 0 ? pair.slice(0, idx) : pair;
    const value = idx >= 0 ? pair.slice(idx + 1) : "";
    try {
      out[decodeURIComponent(key)] = decodeURIComponent(value.replace(/\+/g, " "));
    } catch {
      out[key] = value;
    }
  }
  return out;
}

function tokenShape(value) {
  const s = String(value || "");
  const parts = s ? s.split(":") : [];
  let decodedJsonKeys = [];
  const maybeBase64Json = parts.find((p) => /^[A-Za-z0-9+/=_-]{20,}$/.test(p));
  if (maybeBase64Json) {
    try {
      const normalized = maybeBase64Json.replace(/-/g, "+").replace(/_/g, "/");
      const raw = Buffer.from(normalized, "base64").toString("utf8");
      const parsed = JSON.parse(raw);
      decodedJsonKeys = Object.keys(parsed).sort();
    } catch {
      decodedJsonKeys = [];
    }
  }
  return {
    present: Boolean(s),
    length: s.length,
    segments: parts.length,
    prefixLen: parts[0]?.length || 0,
    decodedJsonKeys,
  };
}

function partInfo(part) {
  const fields = String(part || "").split("|");
  const key = fields[0] || "";
  const info = { key, fields };
  if (key === "IoooII" && fields[1] === "_px3") {
    info.kind = "px3";
    info.ttl = fields[2];
    info.shape = tokenShape(fields[3]);
    info.domainFlag = fields[4];
    info.cookieTtl = fields[5];
  } else if (key === "oIIoIIoo" && fields[1] === "_pxde") {
    info.kind = "pxde";
    info.ttl = fields[2];
    info.shape = tokenShape(fields[3]);
    info.domainFlag = fields[4];
    info.cookieTtl = fields[5];
  } else if (key === "IooIoo") {
    info.kind = "pxvid";
    info.ttl = fields[2];
    info.domainFlag = fields[3];
  } else if (key === "IoIoIo" && fields[1] === "score") {
    info.kind = "score";
    info.score = fields[2];
    info.scoreType = fields[3];
  } else if (key === "oIIoIooo") {
    info.kind = "captcha_result_callback";
    info.result = fields[1];
  }
  return info;
}

function summarizeDecodeEvent(ev, jsRows, sample) {
  const infos = (ev.parts || []).map(partInfo);
  const keys = infos.map((x) => x.key);
  const scoreValues = infos.filter((x) => x.kind === "score").map((x) => x.score);
  const px3 = infos.find((x) => x.kind === "px3");
  const pxde = infos.find((x) => x.kind === "pxde");
  const pxvid = infos.find((x) => x.kind === "pxvid");
  const hasOIIoIooo0 = infos.some((x) => x.kind === "captcha_result_callback" && x.result === "0");
  const nextOt = (sample.otEvents || []).find((x) => x.lineNo >= ev.lineNo) || null;
  const powHitsBefore = jsRows.filter((x) => x.kind === "hsprotect.captcha.pow.hit" && x.lineNo <= ev.lineNo).length;
  const workerMessagesBefore = jsRows.filter((x) => x.kind === "hsprotect.captcha.worker.message" && x.lineNo <= ev.lineNo).length;
  const renderedBefore = jsRows.filter((x) => x.kind === "hsprotect.captcha.zt.enter" && x.data?.arg === "rendered" && x.lineNo <= ev.lineNo).length;
  return {
    lineNo: ev.lineNo,
    partCount: (ev.parts || []).length,
    keys,
    uniqueKeys: [...new Set(keys)],
    scoreValues,
    hasPx3Out: Boolean(px3),
    px3Shape: px3?.shape || null,
    hasPxdeOut: Boolean(pxde),
    pxdeShape: pxde?.shape || null,
    hasPxvidOut: Boolean(pxvid),
    hasOIIoIooo0,
    powHitsBefore,
    workerMessagesBefore,
    renderedBefore,
    nextOt: nextOt ? {
      lineNo: nextOt.lineNo,
      r: nextOt.r,
      state: nextOt.state,
      tokenName: nextOt.n,
      tokenTtl: nextOt.t,
      tokenShape: tokenShape(nextOt.v),
    } : null,
  };
}

function summarizeCollectorRuntime(runtimeRows) {
  const rows = [];
  for (const row of runtimeRows) {
    const url = String(row.url || "");
    if (row.kind !== "request" || !url.includes("collector-pxzc5j78di.hsprotect.net")) continue;
    const form = parseForm(row.post_data);
    rows.push({
      lineNo: row.lineNo,
      endpoint: url.replace(/^https:\/\/collector-pxzc5j78di\.hsprotect\.net/, ""),
      postLen: row.post_len || String(row.post_data || "").length,
      payloadLen: String(form.payload || "").length,
      appId: form.appId,
      seq: form.seq,
      ft: form.ft,
      en: form.en,
      hasUuid: Boolean(form.uuid),
      hasVid: Boolean(form.vid),
      hasCts: Boolean(form.cts),
      hasP1: Boolean(form.p1),
      hasCs: Boolean(form.cs),
      hasPc: Boolean(form.pc),
      rsc: form.rsc,
    });
  }
  return rows;
}

function summarizeRuntimeOutcome(runtimeRows) {
  const riskResponses = runtimeRows.filter((x) => x.kind === "response" && String(x.url || "").includes("risk/verify"));
  const createResponses = runtimeRows.filter((x) => x.kind === "response" && String(x.url || "").includes("API/CreateAccount"));
  return {
    riskStateContinue: riskResponses.some((x) => String(x.body || "").includes('"state":"continue"')),
    createRedirectUrl: createResponses.some((x) => String(x.body || "").includes("redirectUrl")),
    createErrorCodes: createResponses
      .map((x) => {
        const m = String(x.body || "").match(/"code":"([^"]+)"/);
        return m?.[1] || null;
      })
      .filter(Boolean),
  };
}

function summarizeSample(sampleDef) {
  const full = readJson(sampleDef.fullChain);
  const tracePath = path.isAbsolute(full.tracePath) ? full.tracePath : path.join(repo, full.tracePath);
  const runtimePath = full.runtimePath
    ? (path.isAbsolute(full.runtimePath) ? full.runtimePath : path.join(repo, full.runtimePath))
    : null;
  const jsRows = parseJsonl(tracePath);
  const runtimeRows = runtimePath ? parseJsonl(runtimePath) : [];
  const decodePackets = (full.decodeEvents || []).map((ev) => summarizeDecodeEvent(ev, jsRows, full));
  const parentMessages = jsRows
    .filter((x) => x.kind === "window.message.recv")
    .map((x) => {
      let type = null;
      try {
        const raw = x.data?.data;
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        type = parsed?.type || null;
      } catch {}
      return { lineNo: x.lineNo, type };
    })
    .filter((x) => x.type);

  return {
    label: sampleDef.label,
    outcome: sampleDef.outcome,
    source: {
      fullChain: path.relative(repo, sampleDef.fullChain),
      trace: path.relative(repo, tracePath),
      runtime: runtimePath ? path.relative(repo, runtimePath) : null,
    },
    counts: full.counts || {},
    outcomeSignals: {
      otStates: (full.otEvents || []).map((x) => ({ lineNo: x.lineNo, r: x.r, state: x.state })),
      parentMessageTypes: parentMessages.map((x) => x.type),
      runtime: summarizeRuntimeOutcome(runtimeRows),
    },
    collectorPosts: summarizeCollectorRuntime(runtimeRows),
    decodePackets,
  };
}

function markdownReport(report) {
  const lines = [];
  lines.push("# hsprotect normalized timeline for pure HTTP/offline analysis");
  lines.push("");
  lines.push(`generatedAt=${report.generatedAt}`);
  lines.push("");
  lines.push("## Outcome signals");
  lines.push("");
  lines.push("| sample | outcome | Ot states | parent messages | risk_continue | create_redirect | create_errors |");
  lines.push("|---|---|---|---|---:|---:|---|");
  for (const s of report.samples) {
    lines.push([
      `| ${s.label}`,
      s.outcome,
      s.outcomeSignals.otStates.map((x) => `${x.r}:${x.state}@${x.lineNo}`).join(", ") || "-",
      [...new Set(s.outcomeSignals.parentMessageTypes)].join(", ") || "-",
      String(s.outcomeSignals.runtime.riskStateContinue),
      String(s.outcomeSignals.runtime.createRedirectUrl),
      s.outcomeSignals.runtime.createErrorCodes.join(", ") || "-",
      "|",
    ].join(" | "));
  }
  lines.push("");
  lines.push("## Decoded response packets");
  lines.push("");
  lines.push("| sample | line | parts | keys | scores | px3 | pxde | pxvid | powHitsBefore | oIIoIooo|0 | next Ot |");
  lines.push("|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|");
  for (const s of report.samples) {
    for (const p of s.decodePackets) {
      lines.push([
        `| ${s.label}`,
        String(p.lineNo),
        String(p.partCount),
        p.uniqueKeys.join(","),
        p.scoreValues.join(",") || "-",
        String(p.hasPx3Out),
        String(p.hasPxdeOut),
        String(p.hasPxvidOut),
        String(p.powHitsBefore),
        String(p.hasOIIoIooo0),
        p.nextOt ? `${p.nextOt.r}:${p.nextOt.state}@${p.nextOt.lineNo}` : "-",
        "|",
      ].join(" | "));
    }
  }
  lines.push("");
  lines.push("## Collector POST shape");
  lines.push("");
  lines.push("| sample | runtime line | endpoint | seq | postLen | payloadLen | uuid | vid | cts | p1 | cs | pc | rsc |");
  lines.push("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|");
  for (const s of report.samples) {
    for (const c of s.collectorPosts) {
      lines.push([
        `| ${s.label}`,
        String(c.lineNo),
        c.endpoint,
        c.seq || "-",
        String(c.postLen),
        String(c.payloadLen),
        String(c.hasUuid),
        String(c.hasVid),
        String(c.hasCts),
        String(c.hasP1),
        String(c.hasCs),
        String(c.hasPc),
        c.rsc || "-",
        "|",
      ].join(" | "));
    }
  }
  lines.push("");
  lines.push("## Current black-box hypotheses");
  lines.push("");
  lines.push("1. `oIIoIooo|0` is the client-observable success decision delivered by collector response decoding, not a locally generated random value.");
  lines.push("2. Raw token equality is not useful across samples; useful features are token presence, shape, phase, decoded handler keys, and relative order.");
  lines.push("3. In the current paired samples, collector/cookie/score activity exists in both success and failure; success requires the additional decoded handler `oIIoIooo|0`, followed by `Ot(0)` and parent `succeeded`.");
  lines.push("4. A pure HTTP/offline attempt would need to reproduce the collector request state that makes the service return an `ob` decoding to `oIIoIooo|0`; local evidence does not yet prove that state is sufficient.");
  lines.push("");
  lines.push("## Evidence boundary");
  lines.push("");
  lines.push("- This report normalizes structure and phase only; it intentionally avoids comparing random token values.");
  lines.push("- Server-side scoring remains unobserved. Conclusions here are black-box correlations, not proof of HUMAN/Microsoft internal scoring formulas.");
  return lines.join("\n") + "\n";
}

fs.mkdirSync(outDir, { recursive: true });
const report = {
  generatedAt: new Date().toISOString(),
  samples: samples.map(summarizeSample),
};
const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+$/, "Z");
const jsonPath = path.join(outDir, `normalized_timeline_${stamp}.json`);
const mdPath = path.join(outDir, `normalized_timeline_${stamp}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(report, null, 2), "utf8");
fs.writeFileSync(mdPath, markdownReport(report), "utf8");
console.log(JSON.stringify({ jsonPath, mdPath }, null, 2));
