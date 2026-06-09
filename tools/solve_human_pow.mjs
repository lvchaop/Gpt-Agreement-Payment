#!/usr/bin/env node
import fs from "fs";
import path from "path";
import crypto from "crypto";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function parseJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\n/)
    .filter((line) => line.trim())
    .map((line, idx) => ({ lineNo: idx + 1, ...JSON.parse(line) }));
}

function sha256Hex(s) {
  return crypto.createHash("sha256").update(s, "utf8").digest("hex");
}

function poi(i, mask, pad, width, prefixBase, seed) {
  const low = (pad + (i & mask).toString(16)).slice(-width);
  return seed + (prefixBase + (i >> (width << 2))).toString(16) + low;
}

function solvePow({ from, to, mask, len, prefix, salt, seed, target }) {
  for (let i = from; i <= to; i++) {
    const value = poi(i, mask, len, prefix, salt, seed);
    if (sha256Hex(value) === target) return { i, value };
  }
  return null;
}

function collectPowFromTrace(tracePath) {
  const rows = parseJsonl(tracePath);
  const ranges = [];
  const hits = [];
  for (const row of rows) {
    if (row.kind === "hsprotect.captcha.qs.start") {
      const d = row.data || {};
      ranges.push({
        lineNo: row.lineNo,
        from: Number(d.from),
        to: Number(d.to),
        mask: Number(d.mask),
        len: String(d.len),
        prefix: Number(d.prefix),
        salt: Number(d.salt),
        target: String(d.target),
      });
    }
    if (row.kind === "hsprotect.captcha.pow.hit") {
      hits.push({ lineNo: row.lineNo, ...(row.data || {}) });
    }
  }
  return { ranges, hits };
}

function collectPowSeedsFromCollectorDecode(decodePath) {
  const doc = JSON.parse(fs.readFileSync(decodePath, "utf8"));
  const items = [];
  for (const entry of doc.decodedEntries || []) {
    for (const part of entry.parts || []) {
      const fields = String(part).split("|");
      if (fields[0] === "IooIIo") {
        const combinedSeed = fields[2] || "";
        const salt = combinedSeed ? parseInt(combinedSeed.slice(-1), 16) : null;
        items.push({
          lineNo: entry.lineNo,
          raw: part,
          enabled: fields[1],
          combinedSeed,
          seed: combinedSeed.slice(0, -1),
          salt,
          target: fields[3],
          difficulty: fields[4],
          flag: fields[5],
        });
      }
    }
  }
  return items;
}

function main() {
  const tracePath = process.argv[2] || path.join(repo, "output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl");
  const base = path.basename(tracePath, ".jsonl").replace(/^js_internal_trace_/, "");
  const decodePath = path.join(repo, "output/protocol_reverse/collector_decode", `collector_decode_${base}.json`);
  const outDir = path.join(repo, "output/protocol_reverse/pow");
  fs.mkdirSync(outDir, { recursive: true });

  const { ranges, hits } = collectPowFromTrace(tracePath);
  const seeds = fs.existsSync(decodePath) ? collectPowSeedsFromCollectorDecode(decodePath) : [];
  const results = [];
  for (const seed of seeds) {
    for (const range of ranges.filter((r) => r.target === seed.target)) {
      const solved = solvePow({ ...range, seed: seed.seed, salt: seed.salt ?? range.salt });
      results.push({ seedLine: seed.lineNo, rangeLine: range.lineNo, seed, range, solved, matchesObserved: hits.some((h) => h.i === solved?.i && h.value === solved?.value) });
    }
  }

  const result = { tracePath, decodePath: fs.existsSync(decodePath) ? decodePath : null, ranges, seeds, hits, results };
  const jsonPath = path.join(outDir, `pow_replay_${base}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

  const md = [];
  md.push(`# HUMAN POW replay: ${base}`);
  md.push("");
  md.push(`trace=${tracePath}`);
  md.push(`collectorDecode=${result.decodePath || ""}`);
  md.push("");
  md.push("## observed hits");
  for (const h of hits) md.push(`- line ${h.lineNo}: i=${h.i} value=${h.value}`);
  md.push("");
  md.push("## replay results");
  md.push("| seedLine | rangeLine | from | to | target | solved i | solved value | matchesObserved |");
  md.push("|---:|---:|---:|---:|---|---:|---|---|");
  for (const r of results) {
    md.push(`| ${r.seedLine} | ${r.rangeLine} | ${r.range.from} | ${r.range.to} | ${r.seed.target} | ${r.solved?.i ?? ""} | ${r.solved?.value ?? ""} | ${r.matchesObserved} |`);
  }
  const mdPath = path.join(outDir, `pow_replay_${base}.md`);
  fs.writeFileSync(mdPath, md.join("\n"), "utf8");

  console.log(JSON.stringify({ jsonPath, mdPath, rangeCount: ranges.length, seedCount: seeds.length, hitCount: hits.length, solvedCount: results.filter((r) => r.solved).length }, null, 2));
}

main();
