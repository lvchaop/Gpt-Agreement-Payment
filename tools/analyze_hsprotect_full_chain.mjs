#!/usr/bin/env node
import fs from "fs";
import path from "path";
import { createRequire } from "module";

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const require = createRequire("/tmp/hsprotect-js-tools/package.json");
const parser = require("@babel/parser");
const traverse = require("@babel/traverse").default;
const generate = require("@babel/generator").default;
const beautify = require("js-beautify").js;

const tracePath = process.argv[2] || path.join(repo, "output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl");
const mainPath = path.join(repo, "output/outlook_browser/js_probe/main.min.js");
const runtimePath = tracePath.replace("js_internal_trace_", "runtime_trace_");
const outDir = path.join(repo, "output/outlook_browser/js_static_analysis/full_chain");
fs.mkdirSync(outDir, { recursive: true });

function parseJsonl(file) {
  const rows = [];
  const text = fs.readFileSync(file, "utf8");
  for (const [idx, line] of text.split(/\n/).entries()) {
    if (!line.trim()) continue;
    rows.push({ lineNo: idx + 1, ...JSON.parse(line) });
  }
  return rows;
}

function codeOf(node) {
  return beautify(generate(node, { comments: false, compact: false }).code, {
    indent_size: 2,
    max_preserve_newlines: 2,
  });
}

function keyName(node) {
  if (!node) return "";
  if (node.type === "Identifier") return node.name;
  if (node.type === "StringLiteral" || node.type === "NumericLiteral") return String(node.value);
  return generate(node, { comments: false, compact: true }).code;
}

function bindingName(p) {
  const n = p.node;
  if (n.id?.name) return n.id.name;
  const parent = p.parentPath;
  if (!parent) return null;
  if (parent.isVariableDeclarator()) return keyName(parent.node.id);
  if (parent.isObjectProperty() || parent.isObjectMethod()) return keyName(parent.node.key);
  return null;
}

const rows = parseJsonl(tracePath);
const runtimeRows = fs.existsSync(runtimePath) ? parseJsonl(runtimePath) : [];
const counts = {};
const keys = {};
const decodeEvents = [];
const otEvents = [];
const messageEvents = [];
const beaconEvents = [];
const tfPayloadEvents = [];

for (const row of rows) {
  counts[row.kind] = (counts[row.kind] || 0) + 1;
  const d = row.data || {};
  if (row.kind === "hsprotect.main.om.decode") {
    decodeEvents.push({
      lineNo: row.lineNo,
      el: d.el,
      mod: d.mod,
      parts: d.parts || [],
      decoded: d.decoded,
    });
  }
  if (row.kind === "hsprotect.main.jl.item") {
    const key = String(d.handlerKey || "");
    if (!keys[key]) keys[key] = { itemLines: [], dispatchLines: [], table: d.table, handlerType: d.handlerType, examples: [] };
    keys[key].itemLines.push(row.lineNo);
    if (keys[key].examples.length < 3) keys[key].examples.push({ lineNo: row.lineNo, args: d.args, raw: d.raw });
  }
  if (row.kind === "hsprotect.main.jl.dispatch") {
    const key = String(d.handlerKey || "");
    if (!keys[key]) keys[key] = { itemLines: [], dispatchLines: [], table: d.table, handlerType: null, examples: [] };
    keys[key].dispatchLines.push(row.lineNo);
  }
  if (row.kind === "hsprotect.captcha.Ot.enter") otEvents.push({ lineNo: row.lineNo, ...d });
  if (row.kind === "hsprotect.main.tf.payload") {
    const activities = Array.isArray(d.activities) ? d.activities : [];
    tfPayloadEvents.push({
      lineNo: row.lineNo,
      href: row.href,
      perf_t: row.perf_t,
      activityCount: activities.length,
      activityTypes: activities.slice(0, 8).map((x) => x?.t),
      firstActivityKeys: Object.keys(activities[0]?.d || {}).slice(0, 40),
      meta: d.meta || {},
      pc: d.pc,
      cs: d.cs,
      payloadLen: String(d.payload || "").length,
      serializedLen: String(d.serialized || "").length,
      stack: String(d.stack || "").split("\n").filter(Boolean).slice(0, 5),
    });
  }
  if (row.kind === "window.message.recv") {
    const data = d.data || {};
    if (data.type) messageEvents.push({ lineNo: row.lineNo, data });
  }
  if (row.kind === "hsprotect.sendBeacon.internal" || row.kind === "hsprotect.sendBeacon.blobText") {
    beaconEvents.push({ lineNo: row.lineNo, kind: row.kind, url: d.url, blobSize: d.blobSize, blobType: d.blobType, textLen: d.text ? String(d.text).length : undefined, text: d.text });
  }
}

const source = fs.readFileSync(mainPath, "utf8");
const ast = parser.parse(source, {
  sourceType: "script",
  errorRecovery: true,
  ranges: true,
  allowReturnOutsideFunction: true,
});
const functions = [];
traverse(ast, {
  Function(p) {
    functions.push({
      name: bindingName(p),
      type: p.node.type,
      start: p.node.start,
      end: p.node.end,
      node: p.node,
    });
  },
});
function findFunctionByName(name) {
  return functions
    .filter((f) => f.name === name)
    .sort((a, b) => (a.end - a.start) - (b.end - b.start))[0] || null;
}

const handlerMap = {};
traverse(ast, {
  VariableDeclarator(p) {
    if (p.node.id?.type === "Identifier" && p.node.id.name === "Xl" && p.node.init?.type === "ObjectExpression") {
      for (const prop of p.node.init.properties) {
        if (!prop.key) continue;
        const key = keyName(prop.key);
        const value = prop.value || prop;
        let handler = { key, valueType: value.type, code: codeOf(value), artifact: null, targetName: null, range: [value.start, value.end] };
        if (value.type === "Identifier") {
          const target = findFunctionByName(value.name);
          handler.targetName = value.name;
          if (target) {
            const file = path.join(outDir, `handler_Xl_${key}_${value.name}.js`);
            fs.writeFileSync(file, codeOf(target.node), "utf8");
            handler.artifact = file;
            handler.range = [target.start, target.end];
          }
        } else if (value.type === "FunctionExpression" || value.type === "ArrowFunctionExpression" || prop.type === "ObjectMethod") {
          const file = path.join(outDir, `handler_Xl_${key}.js`);
          fs.writeFileSync(file, codeOf(value), "utf8");
          handler.artifact = file;
        }
        handlerMap[key] = handler;
      }
      p.stop();
    }
  },
});

const runtime = [];
for (const row of runtimeRows) {
  const url = row.url || "";
  if (url.includes("risk/verify") || url.includes("API/CreateAccount") || url.includes("api/v2/msft")) {
    runtime.push({
      lineNo: row.lineNo,
      kind: row.kind,
      method: row.method,
      status: row.status,
      url,
      postLen: row.post_data ? String(row.post_data).length : 0,
      bodyLen: row.body ? String(row.body).length : 0,
      stateContinue: String(row.body || "").includes('"state":"continue"'),
      redirectUrl: String(row.body || "").includes("redirectUrl"),
    });
  }
}

const result = {
  tracePath,
  runtimePath: fs.existsSync(runtimePath) ? runtimePath : null,
  counts,
  otEvents,
  tfPayloadEvents,
  messageEvents,
  beaconEvents,
  decodeEvents,
  observedKeys: Object.fromEntries(Object.entries(keys).sort((a, b) => a[0].localeCompare(b[0]))),
  observedHandlerMap: Object.fromEntries(Object.keys(keys).sort().map((key) => [key, handlerMap[key] || null])),
  runtime,
};

const base = path.basename(tracePath, ".jsonl").replace(/^js_internal_trace_/, "");
const jsonPath = path.join(outDir, `full_chain_${base}.json`);
fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2), "utf8");

const md = [];
md.push(`# hsprotect full chain analysis: ${base}`);
md.push("");
md.push(`trace=${tracePath}`);
md.push(`runtime=${result.runtimePath || ""}`);
md.push("");
md.push("## counts");
for (const [k, v] of Object.entries(counts).sort((a, b) => b[1] - a[1])) md.push(`- ${k}: ${v}`);
md.push("");
md.push("## Ot events");
md.push("| line | r | state | n | t | v length |");
md.push("|---:|---:|---|---|---|---:|");
for (const ev of otEvents) md.push(`| ${ev.lineNo} | ${ev.r} | ${ev.state} | ${ev.n} | ${ev.t} | ${String(ev.v || "").length} |`);
md.push("");
md.push("## tf payload events");
md.push("| line | href | activityCount | activityTypes | meta | pc | cs | serializedLen | payloadLen | stack top |");
md.push("|---:|---|---:|---|---|---|---|---:|---:|---|");
for (const ev of tfPayloadEvents) {
  const meta = JSON.stringify(ev.meta || {});
  const stackTop = (ev.stack || []).join("<br>");
  md.push(`| ${ev.lineNo} | ${ev.href} | ${ev.activityCount} | ${JSON.stringify(ev.activityTypes)} | ${meta.replaceAll("|", "\\|")} | ${ev.pc || ""} | ${ev.cs || ""} | ${ev.serializedLen} | ${ev.payloadLen} | ${stackTop.replaceAll("|", "\\|")} |`);
}
md.push("");
md.push("## decoded event packets");
for (const ev of decodeEvents) {
  md.push(`- line ${ev.lineNo}: el=${ev.el} mod=${ev.mod} parts=${ev.parts.length}`);
  for (const part of ev.parts) md.push(`  - ${part}`);
}
md.push("");
md.push("## observed Xl handler keys");
md.push("| key | item lines | dispatch lines | handler | artifact | examples |");
md.push("|---|---|---|---|---|---|");
for (const [key, info] of Object.entries(result.observedKeys)) {
  const handler = result.observedHandlerMap[key];
  const artifact = handler?.artifact ? path.relative(repo, handler.artifact) : "";
  const handlerName = handler ? `${handler.targetName || ""} ${handler.valueType}`.trim() : "";
  const examples = (info.examples || []).map((x) => `line ${x.lineNo}: ${JSON.stringify(x.args)}`).join("<br>");
  md.push(`| ${key} | ${info.itemLines.join(",")} | ${info.dispatchLines.join(",")} | ${handlerName} | ${artifact} | ${examples.replaceAll("|", "\\|")} |`);
}
md.push("");
md.push("## runtime network checkpoints");
md.push("| line | kind | status | url | postLen | bodyLen | flags |");
md.push("|---:|---|---:|---|---:|---:|---|");
for (const r of runtime) {
  const flags = [r.stateContinue ? "state_continue" : "", r.redirectUrl ? "redirectUrl" : ""].filter(Boolean).join(",");
  md.push(`| ${r.lineNo} | ${r.kind} | ${r.status || ""} | ${r.url} | ${r.postLen} | ${r.bodyLen} | ${flags} |`);
}
md.push("");
md.push(`json=${jsonPath}`);

const mdPath = path.join(outDir, `full_chain_${base}.md`);
fs.writeFileSync(mdPath, md.join("\n") + "\n", "utf8");
console.log(mdPath);
console.log(jsonPath);
