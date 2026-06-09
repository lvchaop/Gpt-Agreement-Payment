#!/usr/bin/env node
import fs from "fs";
import path from "path";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function parseJsonl(file) {
  const rows = [];
  const text = fs.readFileSync(file, "utf8");
  for (const [idx, line] of text.split(/\n/).entries()) {
    if (!line.trim()) continue;
    rows.push({ lineNo: idx + 1, ...JSON.parse(line) });
  }
  return rows;
}

function atobBinary(s) {
  return Buffer.from(String(s), "base64").toString("binary");
}

function xorString(s, key) {
  let out = "";
  for (let i = 0; i < s.length; i++) out += String.fromCharCode(key ^ s.charCodeAt(i));
  return out;
}

function el(tag) {
  let e = 0;
  for (let n = 0; n < tag.length; n++) e = (31 * e + tag.charCodeAt(n)) % 2147483647;
  return String((e % 900) + 100);
}

function decodeCollectorResponse(raw, tag = "YjIYfyxJHRR9") {
  let jsonValue = null;
  try {
    jsonValue = JSON.parse(raw);
  } catch {}
  if (jsonValue && typeof jsonValue === "object" && (jsonValue.do || jsonValue.ob)) {
    const inner = jsonValue.do || jsonValue.ob;
    if (typeof inner !== "string") return { mode: "json-direct", decoded: inner, parts: Array.isArray(inner) ? inner : [inner] };
    raw = inner;
  }
  const binary = atobBinary(raw);
  const key = parseInt(el(tag), 10) % 128;
  const decoded = xorString(binary, key);
  const parts = decoded.split("~~~~");
  return { mode: jsonValue ? "json-ob-encoded" : "encoded", tag, key, decoded, parts };
}

function collectFpEntries(tracePath) {
  const rows = parseJsonl(tracePath);
  const entries = [];
  for (const row of rows) {
    if (row.kind !== "hsprotect.main.fp.enter") continue;
    const d = row.data || {};
    entries.push({
      lineNo: row.lineNo,
      raw: d.t,
      e: d.e,
      rawLen: String(d.t || "").length,
      stack: String(d.stack || "").split("\n").filter(Boolean).slice(0, 8),
    });
  }
  return entries;
}

function summarizeDecoded(entry, decoded) {
  const parts = decoded.parts || [];
  const handlers = parts.map((part) => String(part).split("|")[0]).filter(Boolean);
  return {
    lineNo: entry.lineNo,
    rawLen: entry.rawLen,
    mode: decoded.mode,
    key: decoded.key,
    partCount: parts.length,
    handlers,
    hasSuccessHandler: parts.some((p) => p === "oIIoIooo|0" || String(p).startsWith("oIIoIooo|0|")),
    hasPx3: parts.some((p) => String(p).startsWith("IoooII|_px3|")),
    hasPxde: parts.some((p) => String(p).startsWith("oIIoIIoo|_pxde|")),
    hasPowResult: parts.some((p) => String(p).startsWith("IooIIo|")),
    parts,
  };
}

function main() {
  const tracePath = process.argv[2] || path.join(repo, "output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl");
  const tag = process.argv[3] || "YjIYfyxJHRR9";
  const outDir = path.join(repo, "output/protocol_reverse/collector_decode");
  fs.mkdirSync(outDir, { recursive: true });

  const entries = collectFpEntries(tracePath);
  const decodedEntries = entries.map((entry) => {
    const decoded = decodeCollectorResponse(entry.raw, tag);
    return summarizeDecoded(entry, decoded);
  });

  const base = path.basename(tracePath, ".jsonl").replace(/^js_internal_trace_/, "");
  const result = {
    tracePath,
    tag,
    key: parseInt(el(tag), 10) % 128,
    entryCount: entries.length,
    decodedEntries,
  };
  const jsonPath = path.join(outDir, `collector_decode_${base}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

  const md = [];
  md.push(`# collector response decode: ${base}`);
  md.push("");
  md.push(`trace=${tracePath}`);
  md.push(`tag=${tag}`);
  md.push(`xorKey=${result.key}`);
  md.push("");
  md.push("| line | rawLen | mode | parts | success | px3 | pxde | pow | handlers |");
  md.push("|---:|---:|---|---:|---|---|---|---|---|");
  for (const row of decodedEntries) {
    md.push(`| ${row.lineNo} | ${row.rawLen} | ${row.mode} | ${row.partCount} | ${row.hasSuccessHandler} | ${row.hasPx3} | ${row.hasPxde} | ${row.hasPowResult} | ${row.handlers.join(", ")} |`);
  }
  md.push("");
  for (const row of decodedEntries) {
    md.push(`## line ${row.lineNo}`);
    for (const part of row.parts) md.push(`- ${part}`);
    md.push("");
  }
  const mdPath = path.join(outDir, `collector_decode_${base}.md`);
  fs.writeFileSync(mdPath, md.join("\n"), "utf8");

  console.log(JSON.stringify({ jsonPath, mdPath, entryCount: entries.length }, null, 2));
}

main();
