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

const inputs = {
  captcha: path.join(repo, "output/outlook_browser/js_probe/captcha.js"),
  main: path.join(repo, "output/outlook_browser/js_probe/main.min.js"),
};

const frames = [
  { id: "captcha_zt", file: "captcha", symbol: "zt", line: 1724, column: 70576 },
  { id: "captcha_Ot", file: "captcha", symbol: "Ot", line: 1724, column: 83058 },
  { id: "main_Wc", file: "main", symbol: "Wc", line: 3, column: 5296 },
  { id: "main_oIIoIooo", file: "main", symbol: "oIIoIooo", line: 3, column: 32384 },
  { id: "main_jl", file: "main", symbol: "jl", line: 3, column: 36109 },
  { id: "main_om_inner", file: "main", symbol: "om/<", line: 3, column: 125998 },
  { id: "main_om", file: "main", symbol: "om", line: 3, column: 126043 },
  { id: "main_fp", file: "main", symbol: "fp", line: 3, column: 120086 },
];

const outDir = path.join(repo, "output/outlook_browser/js_static_analysis/stack_map");
fs.mkdirSync(outDir, { recursive: true });

function lineStarts(source) {
  const starts = [0];
  for (let i = 0; i < source.length; i += 1) {
    if (source.charCodeAt(i) === 10) starts.push(i + 1);
  }
  return starts;
}

function posFromLineColumn(starts, line, column, oneBasedColumn = false) {
  const start = starts[line - 1];
  if (start == null) throw new Error(`line out of range: ${line}`);
  return start + column - (oneBasedColumn ? 1 : 0);
}

function keyName(node) {
  if (!node) return null;
  if (node.type === "Identifier") return node.name;
  if (node.type === "StringLiteral" || node.type === "NumericLiteral") return String(node.value);
  return null;
}

function bindingName(p) {
  const n = p.node;
  if (n.id?.name) return n.id.name;

  const parent = p.parentPath;
  if (!parent) return null;
  if (parent.isVariableDeclarator()) return keyName(parent.node.id);
  if (parent.isAssignmentExpression()) return keyName(parent.node.left);
  if (parent.isObjectProperty() || parent.isObjectMethod()) return keyName(parent.node.key);
  if (parent.isClassMethod() || parent.isClassPrivateMethod()) return keyName(parent.node.key);
  return null;
}

function parseSource(source) {
  return parser.parse(source, {
    sourceType: "script",
    errorRecovery: true,
    allowReturnOutsideFunction: true,
    ranges: true,
    plugins: ["jsx", "objectRestSpread", "optionalChaining", "classProperties"],
  });
}

function collectFunctions(ast) {
  const funcs = [];
  traverse(ast, {
    Function(p) {
      const node = p.node;
      funcs.push({
        name: bindingName(p),
        type: node.type,
        start: node.start,
        end: node.end,
        loc: node.loc,
        node,
      });
    },
  });
  return funcs;
}

function findEnclosing(funcs, offset) {
  return funcs
    .filter((f) => f.start <= offset && offset <= f.end)
    .sort((a, b) => (a.end - a.start) - (b.end - b.start));
}

function findNearestNamed(funcs, offset, name) {
  return funcs
    .filter((f) => f.name === name)
    .map((f) => ({
      ...f,
      distance: offset < f.start ? f.start - offset : offset > f.end ? offset - f.end : 0,
    }))
    .sort((a, b) => a.distance - b.distance || (a.end - a.start) - (b.end - b.start))[0] || null;
}

function rawContext(source, offset, radius = 1600) {
  const start = Math.max(0, offset - radius);
  const end = Math.min(source.length, offset + radius);
  return source.slice(start, end);
}

function codeOf(node) {
  const code = generate(node, {
    comments: false,
    compact: false,
    retainLines: false,
  }).code;
  return beautify(code, { indent_size: 2, max_preserve_newlines: 2 });
}

const parsed = {};
for (const [key, file] of Object.entries(inputs)) {
  const source = fs.readFileSync(file, "utf8");
  const starts = lineStarts(source);
  const ast = parseSource(source);
  const funcs = collectFunctions(ast);
  parsed[key] = { file, source, starts, ast, funcs };
}

const summary = [];

for (const frame of frames) {
  const item = parsed[frame.file];
  const candidates = [
    { mode: "stack_column_zero_based", offset: posFromLineColumn(item.starts, frame.line, frame.column, false) },
    { mode: "stack_column_one_based", offset: posFromLineColumn(item.starts, frame.line, frame.column, true) },
  ];

  let chosen = null;
  for (const c of candidates) {
    const enclosing = findEnclosing(item.funcs, c.offset);
    const smallest = enclosing[0] || null;
    const matching = enclosing.find((f) => f.name === frame.symbol) || null;
    const nearestNamed = matching ? null : findNearestNamed(item.funcs, c.offset, frame.symbol);
    const score = matching ? 0 : nearestNamed ? 1 : smallest ? 2 : 3;
    const result = {
      ...c,
      enclosing,
      selected: matching || nearestNamed || smallest,
      score,
      selectedBy: matching ? "enclosing_name" : nearestNamed ? "nearest_name" : smallest ? "smallest_enclosing" : "none",
    };
    if (!chosen || result.score < chosen.score || (result.selected && !chosen.selected)) chosen = result;
  }

  const selected = chosen.selected;
  const contextFile = path.join(outDir, `${frame.id}.context.txt`);
  fs.writeFileSync(contextFile, rawContext(item.source, chosen.offset), "utf8");

  let functionFile = null;
  if (selected) {
    functionFile = path.join(outDir, `${frame.id}.function.js`);
    fs.writeFileSync(functionFile, codeOf(selected.node), "utf8");
  }

  summary.push({
    id: frame.id,
    file: frame.file,
    sourceFile: item.file,
    runtime: {
      symbol: frame.symbol,
      line: frame.line,
      column: frame.column,
    },
    mapping: {
      columnMode: chosen.mode,
      absoluteOffset: chosen.offset,
      rawContextFile: contextFile,
      selectedBy: chosen.selectedBy,
    },
    selectedFunction: selected ? {
      name: selected.name,
      type: selected.type,
      start: selected.start,
      end: selected.end,
      loc: selected.loc,
      size: selected.end - selected.start,
      functionFile,
    } : null,
    enclosingChain: chosen.enclosing.slice(0, 8).map((f) => ({
      name: f.name,
      type: f.type,
      start: f.start,
      end: f.end,
      loc: f.loc,
      size: f.end - f.start,
    })),
  });
}

const summaryPath = path.join(outDir, "summary.json");
fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2), "utf8");

const md = [
  "# hsprotect stack frame static map",
  "",
  "| id | runtime frame | absolute offset | selected function | function range | artifact |",
  "|---|---:|---:|---|---:|---|",
  ...summary.map((s) => {
    const fn = s.selectedFunction;
    return [
      `| ${s.id}`,
      `${s.file}.js:${s.runtime.line}:${s.runtime.column} ${s.runtime.symbol}`,
      String(s.mapping.absoluteOffset),
      fn ? `${fn.name || "(anonymous)"} / ${fn.type}` : "(none)",
      fn ? `${fn.start}-${fn.end}` : "",
      fn ? path.relative(repo, fn.functionFile) : path.relative(repo, s.mapping.rawContextFile),
      "|",
    ].join(" | ");
  }),
  "",
  `summary_json=${path.relative(repo, summaryPath)}`,
].join("\n");

const mdPath = path.join(outDir, "summary.md");
fs.writeFileSync(mdPath, md, "utf8");
process.stdout.write(md + "\n");
