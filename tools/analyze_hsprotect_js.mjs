import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const toolRequire = createRequire("/tmp/hsprotect-js-tools/package.json");
let jsBeautify = null;
let parser = null;
let traverse = null;
let generate = null;
try {
  jsBeautify = toolRequire("js-beautify").js;
} catch {}
try {
  parser = toolRequire("@babel/parser");
  traverse = toolRequire("@babel/traverse").default;
  generate = toolRequire("@babel/generator").default;
} catch {}

const root = process.cwd();
const inputs = [
  ["main", "output/outlook_browser/js_probe/main.min.js"],
  ["captcha", "output/outlook_browser/js_probe/captcha.js"],
  ["har_main", "output/har_extract/js/hsprotect_main.min.js"],
  ["har_captcha", "output/har_extract/js/hsprotect_captcha.js"],
];

const probes = {
  main: [
    "Xn={on:",
    "subscribe:function",
    "trigger:function",
    "inject_succeeded",
    "inject_failed",
    "postMessage",
    "sendBeacon",
    "new XMLHttpRequest",
    "XMLHttpRequest",
    "new Worker",
    "_px3",
    "/api/v2/msft",
    "/assets/js/bundle",
    "/b/c",
    "captcha_callback",
  ],
  captcha: [
    "function sha256",
    "sha256(",
    "function poi",
    "function qs",
    "postMessage(z)",
    "postMessage(!1)",
    "new Blob",
    "new Worker",
    "onmessage",
    "captcha_callback",
    "XMLHttpRequest",
  ],
};

function sha256(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function lineCol(text, offset) {
  if (offset < 0) return { line: -1, col: -1 };
  let line = 1;
  let last = 0;
  for (let i = 0; i < offset; i++) {
    if (text.charCodeAt(i) === 10) {
      line++;
      last = i + 1;
    }
  }
  return { line, col: offset - last + 1 };
}

function allIndexes(text, needle, limit = 30) {
  const out = [];
  let pos = 0;
  while (out.length < limit) {
    const idx = text.indexOf(needle, pos);
    if (idx < 0) break;
    out.push(idx);
    pos = idx + Math.max(needle.length, 1);
  }
  return out;
}

function snippet(text, offset, radius = 700) {
  const start = Math.max(0, offset - radius);
  const end = Math.min(text.length, offset + radius);
  return {
    start,
    end,
    text: text.slice(start, end),
  };
}

function compactSnippet(s) {
  return s.replace(/\s+/g, " ").slice(0, 2400);
}

function writeFile(file, content) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, content);
}

const outDir = path.join(root, "output/outlook_browser/js_static_analysis");
fs.mkdirSync(outDir, { recursive: true });

function beautifySource(text) {
  if (jsBeautify) {
    return jsBeautify(text, {
      indent_size: 2,
      max_preserve_newlines: 2,
      wrap_line_length: 160,
      space_in_empty_paren: false,
    });
  }
  return text;
}

function extractAstFacts(label, rel, text) {
  const facts = {
    parserAvailable: !!parser,
    parseOk: false,
    parseError: "",
    functions: [],
    objectMethods: [],
    callExpressions: [],
    assignments: [],
  };
  if (!parser || !traverse || !generate) return facts;
  let ast;
  try {
    ast = parser.parse(text, {
      sourceType: "script",
      errorRecovery: true,
      allowReturnOutsideFunction: true,
      ranges: true,
      tokens: false,
    });
    facts.parseOk = true;
  } catch (e) {
    facts.parseError = String(e && e.message || e);
    return facts;
  }

  const interestingCalls = new Set([
    "postMessage",
    "sendBeacon",
    "fetch",
    "XMLHttpRequest",
    "Worker",
    "Blob",
    "createObjectURL",
    "sha256",
    "poi",
    "qs",
    "trigger",
    "subscribe",
    "on",
  ]);
  const pushLimited = (arr, item, limit = 200) => {
    if (arr.length < limit) arr.push(item);
  };
  const locOf = (node) => {
    const start = typeof node.start === "number" ? node.start : -1;
    return { offset: start, ...lineCol(text, start) };
  };
  const codeOf = (node, max = 900) => {
    try {
      return generate(node, { compact: false, minified: false, comments: false }).code.slice(0, max);
    } catch {
      return text.slice(node.start || 0, Math.min(text.length, (node.end || 0))).slice(0, max);
    }
  };

  traverse(ast, {
    FunctionDeclaration(p) {
      const name = p.node.id && p.node.id.name || "";
      if (/^(sha256|poi|qs)$/.test(name)) {
        pushLimited(facts.functions, { name, ...locOf(p.node), code: codeOf(p.node, 1800) });
      }
    },
    VariableDeclarator(p) {
      const id = p.node.id;
      const init = p.node.init;
      if (id && id.type === "Identifier" && init && /Function/.test(init.type || "")) {
        if (/^(Xn|ts|as|ep|Iv)$/.test(id.name)) {
          pushLimited(facts.assignments, { name: id.name, ...locOf(p.node), code: codeOf(p.node, 1800) });
        }
      }
    },
    ObjectProperty(p) {
      const key = p.node.key;
      const name = key && (key.name || key.value);
      if (["on", "one", "off", "subscribe", "trigger"].includes(name)) {
        pushLimited(facts.objectMethods, { name, ...locOf(p.node), code: codeOf(p.node, 1400) });
      }
    },
    ObjectMethod(p) {
      const key = p.node.key;
      const name = key && (key.name || key.value);
      if (["on", "one", "off", "subscribe", "trigger"].includes(name)) {
        pushLimited(facts.objectMethods, { name, ...locOf(p.node), code: codeOf(p.node, 1400) });
      }
    },
    CallExpression(p) {
      const callee = p.node.callee;
      let name = "";
      if (callee.type === "Identifier") name = callee.name;
      if (callee.type === "MemberExpression") {
        name = callee.property && (callee.property.name || callee.property.value) || "";
      }
      if (interestingCalls.has(name)) {
        pushLimited(facts.callExpressions, {
          callee: name,
          ...locOf(p.node),
          args: p.node.arguments.map((a) => codeOf(a, 220)),
          code: codeOf(p.node, 900),
        }, 500);
      }
    },
    NewExpression(p) {
      const callee = p.node.callee;
      const name = callee.type === "Identifier" ? callee.name : "";
      if (interestingCalls.has(name)) {
        pushLimited(facts.callExpressions, {
          callee: `new ${name}`,
          ...locOf(p.node),
          args: p.node.arguments.map((a) => codeOf(a, 220)),
          code: codeOf(p.node, 900),
        }, 500);
      }
    },
  });
  return facts;
}

const summary = {
  generatedAt: new Date().toISOString(),
  files: {},
};

let md = "# hsprotect JS 静态索引\n\n";
md += `生成时间：${summary.generatedAt}\n\n`;

for (const [label, rel] of inputs) {
  const file = path.join(root, rel);
  if (!fs.existsSync(file)) {
    summary.files[label] = { path: rel, exists: false };
    continue;
  }
  const buf = fs.readFileSync(file);
  const text = buf.toString("utf8");
  const fileSummary = {
    path: rel,
    exists: true,
    bytes: buf.length,
    chars: text.length,
    sha256: sha256(buf),
    probes: {},
    astFactsPath: "",
    beautifiedPath: "",
  };
  const probeList = probes[label.replace(/^har_/, "")] || [];
  md += `## ${label}\n\n`;
  md += `- path: \`${rel}\`\n`;
  md += `- bytes: ${buf.length}\n`;
  md += `- sha256: \`${fileSummary.sha256}\`\n\n`;

  const beautified = beautifySource(text);
  const beautifiedName = `${label}.beautified.js`;
  writeFile(path.join(outDir, beautifiedName), beautified);
  fileSummary.beautifiedPath = `output/outlook_browser/js_static_analysis/${beautifiedName}`;
  md += `- beautified: \`${fileSummary.beautifiedPath}\`\n`;

  const astFacts = extractAstFacts(label, rel, text);
  const astFactsName = `${label}.ast_facts.json`;
  writeFile(path.join(outDir, astFactsName), JSON.stringify(astFacts, null, 2));
  fileSummary.astFactsPath = `output/outlook_browser/js_static_analysis/${astFactsName}`;
  md += `- ast_facts: \`${fileSummary.astFactsPath}\`\n`;
  md += `- ast_parse_ok: ${astFacts.parseOk}\n\n`;

  for (const needle of probeList) {
    const indexes = allIndexes(text, needle);
    fileSummary.probes[needle] = indexes.map((offset) => ({
      offset,
      ...lineCol(text, offset),
    }));
    md += `### ${needle}\n\n`;
    if (!indexes.length) {
      md += "- 未命中\n\n";
      continue;
    }
    for (const offset of indexes.slice(0, 5)) {
      const loc = lineCol(text, offset);
      const snip = snippet(text, offset);
      const snipName = `${label}_${needle.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "")}_${offset}.txt`;
      writeFile(path.join(outDir, snipName), snip.text);
      md += `- offset=${offset}, line=${loc.line}, col=${loc.col}, snippet=\`${snipName}\`\n`;
      md += `  - preview: \`${compactSnippet(snip.text).replace(/`/g, "\\`")}\`\n`;
    }
    md += "\n";
  }
  summary.files[label] = fileSummary;
}

writeFile(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
writeFile(path.join(outDir, "summary.md"), md);
console.log(JSON.stringify({
  outDir,
  summary: path.join(outDir, "summary.json"),
  markdown: path.join(outDir, "summary.md"),
}, null, 2));
