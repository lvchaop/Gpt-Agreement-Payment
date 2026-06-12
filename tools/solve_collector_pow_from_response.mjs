#!/usr/bin/env node
import fs from "fs";
import path from "path";
import crypto from "crypto";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";

function sha256Hex(s) {
  return crypto.createHash("sha256").update(s, "utf8").digest("hex");
}

function candidateValue(i, width, prefixBase, seed) {
  const mask = (1 << (width << 2)) - 1;
  const pad = "0".repeat(width);
  const low = (pad + (i & mask).toString(16)).slice(-width);
  return seed + (prefixBase + (i >> (width << 2))).toString(16) + low;
}

function parseParts(doc) {
  if (Array.isArray(doc?.decoded?.parts)) return doc.decoded.parts;
  if (Array.isArray(doc?.parts)) return doc.parts;
  if (Array.isArray(doc?.steps)) {
    const parts = [];
    for (const step of doc.steps) {
      for (const part of step?.decoded?.parts || []) parts.push(part);
    }
    return parts;
  }
  const parts = [];
  for (const entry of doc?.decodedEntries || []) {
    for (const part of entry.parts || []) parts.push(part);
  }
  return parts;
}

function sourceRef(doc, file) {
  if (doc?.tracePath) return doc.tracePath;
  if (doc?.sent?.url) return doc.sent.url;
  return file;
}

function solveSeed(part) {
  const startedAtMs = Date.now();
  const fields = String(part).split("|");
  if (fields[0] !== "IooIIo") return null;
  const combinedSeed = fields[2] || "";
  const seed = combinedSeed.slice(0, -1);
  const salt = combinedSeed ? parseInt(combinedSeed.slice(-1), 16) : null;
  const target = fields[3] || "";
  const difficulty = Number(fields[4]);
  const width = Math.max(1, Math.floor(difficulty / 4));
  const max = Math.pow(16, width);
  for (let prefixBase = 0; prefixBase <= 15; prefixBase++) {
    for (let i = 0; i < max; i++) {
      const value = candidateValue(i, width, prefixBase, seed);
      if (sha256Hex(value) === target) {
        const endedAtMs = Date.now();
        return {
          raw: part,
          enabled: fields[1],
          combinedSeed,
          seed,
          salt,
          target,
          difficulty,
          flag: fields[5],
          width,
          searchSpacePerPrefix: max,
          prefixBase,
          i,
          value,
          sha256: sha256Hex(value),
          matchesTarget: true,
          solveStartedAtMs: startedAtMs,
          solveEndedAtMs: endedAtMs,
          solveElapsedMs: endedAtMs - startedAtMs,
        };
      }
    }
  }
  const endedAtMs = Date.now();
  return {
    raw: part,
    enabled: fields[1],
    combinedSeed,
    seed,
    salt,
    target,
    difficulty,
    flag: fields[5],
    width,
    searchSpacePerPrefix: max,
    solved: false,
    solveStartedAtMs: startedAtMs,
    solveEndedAtMs: endedAtMs,
    solveElapsedMs: endedAtMs - startedAtMs,
  };
}

function main() {
  const input = process.argv[2];
  if (!input) {
    console.error("usage: node tools/solve_collector_pow_from_response.mjs <collector_decode_or_live_probe.json>");
    process.exit(2);
  }
  const abs = path.isAbsolute(input) ? input : path.join(repo, input);
  const doc = JSON.parse(fs.readFileSync(abs, "utf8"));
  const base = path.basename(abs, ".json").replace(/^collector_(decode|live_probe)_/, "");
  const outDir = path.join(repo, "output/protocol_reverse/pow_response");
  fs.mkdirSync(outDir, { recursive: true });

  const parts = parseParts(doc);
  const powParts = parts.filter((part) => String(part).startsWith("IooIIo|"));
  const solveStartedAtMs = Date.now();
  const results = powParts.map(solveSeed);
  const solveEndedAtMs = Date.now();
  const result = {
    input: abs,
    source: sourceRef(doc, abs),
    powPartCount: powParts.length,
    solveStartedAtMs,
    solveEndedAtMs,
    solveElapsedMs: solveEndedAtMs - solveStartedAtMs,
    results,
  };

  const jsonPath = path.join(outDir, `pow_response_${base}.json`);
  const mdPath = path.join(outDir, `pow_response_${base}.md`);
  fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

  const md = [];
  md.push(`# Collector POW response solve: ${base}`);
  md.push("");
  md.push(`input=${abs}`);
  md.push(`source=${result.source}`);
  md.push("");
  md.push("| idx | difficulty | width | salt | prefixBase | i | elapsed ms | value | matchesTarget | raw |");
  md.push("|---:|---:|---:|---:|---:|---:|---:|---|---|---|");
  for (const [idx, r] of results.entries()) {
    md.push(`| ${idx} | ${r.difficulty ?? ""} | ${r.width ?? ""} | ${r.salt ?? ""} | ${r.prefixBase ?? ""} | ${r.i ?? ""} | ${r.solveElapsedMs ?? ""} | ${r.value ?? ""} | ${r.matchesTarget === true} | \`${r.raw || ""}\` |`);
  }
  fs.writeFileSync(mdPath, md.join("\n"), "utf8");

  console.log(JSON.stringify({
    jsonPath,
    mdPath,
    powPartCount: result.powPartCount,
    solvedCount: results.filter((r) => r?.matchesTarget).length,
  }, null, 2));
}

main();
