#!/usr/bin/env node
import fs from "fs";
import path from "path";

const TRACE_DIR = "output/outlook_browser";
const TEMPLATE_DIR = "output/outlook_browser/js_static_analysis/payload_reverse/success_templates/zel89cqywfov_1780988664_line_305";

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  return idx >= 0 && process.argv[idx + 1] ? process.argv[idx + 1] : fallback;
}

const runtimePath = path.resolve(arg("--runtime", path.join(TRACE_DIR, "runtime_trace_zel89cqywfov_1780988664.jsonl")));
const requestLine = Number(arg("--request-line", "305"));
const templateDir = path.resolve(arg("--dir", TEMPLATE_DIR));

function readJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .map((line, idx) => ({ line, lineNo: idx + 1 }))
    .filter((x) => x.line.trim())
    .map(({ line, lineNo }) => {
      try {
        return { lineNo, ...JSON.parse(line) };
      } catch {
        return { lineNo, kind: "parse_error" };
      }
    });
}

function shellConfigQuote(value) {
  return `"${String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function proxyUserFromHeader(header) {
  const match = String(header || "").match(/^Basic\s+(.+)$/i);
  if (!match) return "";
  return Buffer.from(match[1], "base64").toString("utf8");
}

function writeConfig({ request, id, useProxy }) {
  const headers = request.headers || {};
  const drop = new Set(["host", "content-length", "connection", "accept-encoding", "proxy-authorization"]);
  const out = [];
  out.push("http1.1");
  out.push("compressed");
  out.push("silent");
  out.push("show-error");
  out.push("request = \"POST\"");
  out.push(`url = ${shellConfigQuote(request.url)}`);
  out.push(`dump-header = ${shellConfigQuote(`${id}.headers`)}`);
  out.push(`output = ${shellConfigQuote(`${id}.body`)}`);
  out.push(`data-binary = ${shellConfigQuote("@request.body.private.txt")}`);
  for (const [key, value] of Object.entries(headers)) {
    const lower = key.toLowerCase();
    if (drop.has(lower)) continue;
    out.push(`header = ${shellConfigQuote(`${key}: ${value}`)}`);
  }
  if (!headers["content-type"]) {
    out.push(`header = ${shellConfigQuote("content-type: application/x-www-form-urlencoded")}`);
  }
  if (useProxy) {
    const runMeta = readJsonl(runtimePath).find((row) => row.kind === "run.meta");
    const endpoint = runMeta?.meta?.proxy?.endpoint || "http://p.webshare.io:80";
    const proxyUser = proxyUserFromHeader(headers["proxy-authorization"]);
    out.push(`proxy = ${shellConfigQuote(endpoint)}`);
    if (proxyUser) out.push(`proxy-user = ${shellConfigQuote(proxyUser)}`);
  }
  const configPath = path.join(templateDir, `${id}.curl.private.conf`);
  fs.writeFileSync(configPath, `${out.join("\n")}\n`, "utf8");
  fs.chmodSync(configPath, 0o600);
  return configPath;
}

const rows = readJsonl(runtimePath);
const request = rows.find((row) => row.lineNo === requestLine && row.kind === "request");
if (!request) throw new Error(`request line not found: ${requestLine}`);

const noProxy = writeConfig({ request, id: "collector_full_headers_noproxy", useProxy: false });
const proxy = writeConfig({ request, id: "collector_full_headers_proxy", useProxy: true });
console.log(JSON.stringify({
  templateDir,
  requestLine,
  noProxy,
  proxy,
  headerNames: Object.keys(request.headers || {}).sort(),
  proxyConfigured: true,
}, null, 2));
