#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const repo = "/Users/chaopenglv/data/me/Gpt-Agreement-Payment";
const run = process.argv[2] || "tuisye6ib170_1781129289";
const wasmPath = process.argv[3] || path.join(repo, "output/protocol_reverse/wasm/captcha_tuisye6ib170_1781129289.wasm");
const tracePath = process.argv[4] || path.join(repo, `output/outlook_browser/js_internal_trace_${run}.jsonl`);
const outDir = process.argv[5] || path.join(repo, "output/protocol_reverse/wasm");

function decodeTopLevelU(encoded) {
  const key = "W6ypnhT";
  const padded = encoded + "=".repeat((4 - encoded.length % 4) % 4);
  const bytes = Buffer.from(padded, "base64");
  let out = "";
  for (let i = 0; i < bytes.length; i++) out += String.fromCharCode(bytes[i] ^ key.charCodeAt(i % key.length));
  return out;
}

function readJsonl(file) {
  return fs.readFileSync(file, "utf8")
    .split(/\r?\n/)
    .map((line, idx) => ({ line, idx: idx + 1 }))
    .filter((row) => row.line.trim())
    .map((row) => ({ ...JSON.parse(row.line), _line: row.idx }));
}

function makeWbgImports(getWasm, record = () => {}, options = {}) {
  const heap = [undefined, null, true, false, globalThis];
  let heapNext = heap.length;
  const textDecoder = new TextDecoder("utf-8", { ignoreBOM: true, fatal: true });
  textDecoder.decode();
  const textEncoder = new TextEncoder();
  let uint8 = null;
  let int32 = null;
  let vectorLen = 0;

  function wasm() {
    return getWasm();
  }
  function addHeapObject(obj) {
    if (heapNext === heap.length) heap.push(heap.length + 1);
    const idx = heapNext;
    heapNext = heap[idx];
    heap[idx] = obj;
    return idx;
  }
  function getObject(idx) {
    return heap[idx];
  }
  function dropObject(idx) {
    if (idx < 5) return;
    heap[idx] = heapNext;
    heapNext = idx;
  }
  function takeObject(idx) {
    const ret = getObject(idx);
    dropObject(idx);
    return ret;
  }
  function getUint8Memory() {
    const w = wasm();
    if (!uint8 || uint8.buffer !== w.memory.buffer) uint8 = new Uint8Array(w.memory.buffer);
    return uint8;
  }
  function getInt32Memory() {
    const w = wasm();
    if (!int32 || int32.buffer !== w.memory.buffer) int32 = new Int32Array(w.memory.buffer);
    return int32;
  }
  function getString(ptr, len) {
    return textDecoder.decode(getUint8Memory().subarray(ptr, ptr + len));
  }
  function passString(arg, malloc, realloc) {
    if (realloc === undefined) {
      const buf = textEncoder.encode(arg);
      const ptr = malloc(buf.length);
      getUint8Memory().subarray(ptr, ptr + buf.length).set(buf);
      vectorLen = buf.length;
      return ptr;
    }
    let len = arg.length;
    let ptr = malloc(len);
    const mem = getUint8Memory();
    let offset = 0;
    for (; offset < len; offset++) {
      const code = arg.charCodeAt(offset);
      if (code > 0x7f) break;
      mem[ptr + offset] = code;
    }
    if (offset !== len) {
      if (offset !== 0) arg = arg.slice(offset);
      ptr = realloc(ptr, len, len = offset + arg.length * 3);
      const view = getUint8Memory().subarray(ptr + offset, ptr + len);
      const ret = textEncoder.encodeInto(arg, view);
      offset += ret.written;
    }
    vectorLen = offset;
    return { ptr, len: vectorLen };
  }
  function readRet(stackPtr) {
    const mem = getInt32Memory();
    const ptr = mem[stackPtr / 4 + 0];
    const len = mem[stackPtr / 4 + 1];
    const errPtr = mem[stackPtr / 4 + 2];
    const err = mem[stackPtr / 4 + 3];
    return { ptr, len, errPtr, err, value: ptr && len ? getString(ptr, len) : "" };
  }
  const imports = {
    wbg: {
      __wbindgen_string_get: (outPtr, heapIdx) => {
        record("__wbindgen_string_get");
        const obj = getObject(heapIdx);
        const ret = typeof obj === "string" ? obj : undefined;
        const encoded = ret == null ? { ptr: 0, len: 0 } : passString(ret, wasm().__wbindgen_malloc, wasm().__wbindgen_realloc);
        getInt32Memory()[outPtr / 4 + 1] = encoded.len;
        getInt32Memory()[outPtr / 4 + 0] = encoded.ptr;
      },
      __wbindgen_object_drop_ref: (idx) => {
        record("__wbindgen_object_drop_ref");
        return dropObject(idx);
      },
      __wbindgen_string_new: (ptr, len) => {
        record("__wbindgen_string_new", { len });
        return addHeapObject(getString(ptr, len));
      },
      __wbg_instanceof_Window_e266f02eee43b570: () => {
        record("__wbg_instanceof_Window_e266f02eee43b570");
        return options.instanceofWindow ? 1 : 0;
      },
      __wbg_get_e6ae480a4b8df368: (objIdx, ptr, len) => {
        record("__wbg_get_e6ae480a4b8df368", { prop: getString(ptr, len) });
        const ret = getObject(objIdx)?.[getString(ptr, len)];
        return ret == null ? 0 : addHeapObject(ret);
      },
      __wbg_crypto_c48a774b022d20ac: (idx) => {
        record("__wbg_crypto_c48a774b022d20ac");
        return addHeapObject(getObject(idx).crypto || crypto.webcrypto);
      },
      __wbindgen_is_object: (idx) => {
        record("__wbindgen_is_object");
        const obj = getObject(idx);
        return typeof obj === "object" && obj !== null;
      },
      __wbg_process_298734cf255a885d: (idx) => {
        record("__wbg_process_298734cf255a885d");
        return addHeapObject(getObject(idx).process || process);
      },
      __wbg_versions_e2e78e134e3e5d01: (idx) => {
        record("__wbg_versions_e2e78e134e3e5d01");
        return addHeapObject(getObject(idx).versions || process.versions);
      },
      __wbg_node_1cd7a5d853dbea79: (idx) => {
        record("__wbg_node_1cd7a5d853dbea79");
        return addHeapObject(getObject(idx).node || process.versions.node);
      },
      __wbindgen_is_string: (idx) => {
        record("__wbindgen_is_string");
        return typeof getObject(idx) === "string";
      },
      __wbg_require_8f08ceecec0f4fee: () => {
        record("__wbg_require_8f08ceecec0f4fee");
        return addHeapObject(require);
      },
      __wbg_msCrypto_bcb970640f50a1e8: (idx) => {
        record("__wbg_msCrypto_bcb970640f50a1e8");
        return addHeapObject(getObject(idx).msCrypto);
      },
      __wbg_getRandomValues_37fa2ca9e4e07fab: (objIdx, arrIdx) => {
        const arr = getObject(arrIdx);
        record("__wbg_getRandomValues_37fa2ca9e4e07fab", { len: arr?.length });
        return getObject(objIdx).getRandomValues(arr);
      },
      __wbg_randomFillSync_dc1e9a60c158336d: (objIdx, arrIdx) => {
        const arr = takeObject(arrIdx);
        record("__wbg_randomFillSync_dc1e9a60c158336d", { len: arr?.length });
        return getObject(objIdx).randomFillSync(arr);
      },
      __wbindgen_is_function: (idx) => {
        record("__wbindgen_is_function");
        return typeof getObject(idx) === "function";
      },
      __wbg_newnoargs_2b8b6bd7753c76ba: (ptr, len) => {
        record("__wbg_newnoargs_2b8b6bd7753c76ba", { source: getString(ptr, len).slice(0, 120) });
        throw new Error(`new Function disabled in offline replay: ${getString(ptr, len)}`);
      },
      __wbg_call_95d1ea488d03e4e8: (fnIdx, thisIdx) => {
        record("__wbg_call_95d1ea488d03e4e8");
        return addHeapObject(getObject(fnIdx).call(getObject(thisIdx)));
      },
      __wbg_new_f9876326328f45ed: () => {
        record("__wbg_new_f9876326328f45ed");
        return addHeapObject({});
      },
      __wbg_self_e7c1f827057f6584: () => {
        record("__wbg_self_e7c1f827057f6584");
        return addHeapObject(globalThis);
      },
      __wbg_window_a09ec664e14b1b81: () => {
        record("__wbg_window_a09ec664e14b1b81");
        return addHeapObject(globalThis);
      },
      __wbg_globalThis_87cbb8506fecf3a9: () => {
        record("__wbg_globalThis_87cbb8506fecf3a9");
        return addHeapObject(globalThis);
      },
      __wbg_global_c85a9259e621f3db: () => {
        record("__wbg_global_c85a9259e621f3db");
        return addHeapObject(globalThis);
      },
      __wbindgen_is_undefined: (idx) => {
        record("__wbindgen_is_undefined");
        return getObject(idx) === undefined;
      },
      __wbg_call_9495de66fdbe016b: (fnIdx, thisIdx, argIdx) => {
        record("__wbg_call_9495de66fdbe016b");
        return addHeapObject(getObject(fnIdx).call(getObject(thisIdx), getObject(argIdx)));
      },
      __wbg_buffer_cf65c07de34b9a08: (idx) => {
        record("__wbg_buffer_cf65c07de34b9a08");
        return addHeapObject(getObject(idx).buffer);
      },
      __wbg_newwithbyteoffsetandlength_9fb2f11355ecadf5: (idx, off, len) => {
        record("__wbg_newwithbyteoffsetandlength_9fb2f11355ecadf5", { off, len });
        return addHeapObject(new Uint8Array(getObject(idx), off >>> 0, len >>> 0));
      },
      __wbg_new_537b7341ce90bb31: (idx) => {
        record("__wbg_new_537b7341ce90bb31");
        return addHeapObject(new Uint8Array(getObject(idx)));
      },
      __wbg_set_17499e8aa4003ebd: (targetIdx, sourceIdx, off) => {
        record("__wbg_set_17499e8aa4003ebd", { off });
        return getObject(targetIdx).set(getObject(sourceIdx), off >>> 0);
      },
      __wbg_newwithlength_b56c882b57805732: (len) => {
        record("__wbg_newwithlength_b56c882b57805732", { len });
        return addHeapObject(new Uint8Array(len >>> 0));
      },
      __wbg_subarray_7526649b91a252a6: (idx, begin, end) => {
        record("__wbg_subarray_7526649b91a252a6", { begin, end });
        return addHeapObject(getObject(idx).subarray(begin >>> 0, end >>> 0));
      },
      __wbindgen_object_clone_ref: (idx) => {
        record("__wbindgen_object_clone_ref");
        return addHeapObject(getObject(idx));
      },
      __wbindgen_throw: (ptr, len) => {
        record("__wbindgen_throw", { message: getString(ptr, len) });
        throw new Error(getString(ptr, len));
      },
      __wbindgen_memory: () => {
        record("__wbindgen_memory");
        return addHeapObject(wasm().memory);
      },
    },
  };
  return { imports, passString, readRet };
}

async function instantiateWithLog(bytes, options = {}) {
  let wasmExports;
  const calls = [];
  const glue = makeWbgImports(() => wasmExports, (name, detail = undefined) => {
    calls.push({ name, ...(detail ? { detail } : {}) });
  }, options);
  const { instance } = await WebAssembly.instantiate(bytes, glue.imports);
  wasmExports = instance.exports;
  return { exports: wasmExports, glue, calls };
}

function summarizeCalls(calls) {
  const counts = {};
  for (const call of calls) counts[call.name] = (counts[call.name] || 0) + 1;
  return {
    counts,
    firstCalls: calls.slice(0, 30),
    total: calls.length,
  };
}

function callNg(exports, fnName, readRet) {
  const sp = exports.__wbindgen_add_to_stack_pointer(-16);
  try {
    exports[fnName](sp);
    return readRet(sp);
  } finally {
    exports.__wbindgen_add_to_stack_pointer(16);
  }
}

function callNq(exports, fnName, input, passString, readRet) {
  const sp = exports.__wbindgen_add_to_stack_pointer(-16);
  try {
    const encoded = passString(input, exports.__wbindgen_malloc, exports.__wbindgen_realloc);
    exports[fnName](sp, encoded.ptr, encoded.len);
    return readRet(sp);
  } finally {
    exports.__wbindgen_add_to_stack_pointer(16);
  }
}

const bytes = fs.readFileSync(wasmPath);
const wasmSha256 = crypto.createHash("sha256").update(bytes).digest("hex");
const samples = readJsonl(tracePath)
  .filter((row) => row.kind === "hsprotect.captcha.tbr9.after_nq")
  .map((row) => ({
    line: row._line,
    nInput: row.data?.nInput,
    nInputLen: row.data?.nInputLen,
    nqValue: row.data?.nqValue,
    nqLen: row.data?.nqValue?.length,
    href: row.href,
  }));
const runtimePxUuidEvidence = readJsonl(tracePath)
  .filter((row) => row.kind === "hsprotect.captcha.wasm.import.return")
  .map((row) => ({ line: row._line, ...(row.data || {}) }))
  .filter((row) => row.name === "__wbindgen_string_get" && typeof row.outStringPreview === "string" && row.outStringPreview.length === 36)
  .map((row) => ({
    line: row.line,
    fn: row.active?.fn,
    input: row.active?.input,
    value: row.outStringPreview,
    len: row.outStringLen,
  }));
const runtimePxUuid = runtimePxUuidEvidence.find((row) => row.fn === "NQ")?.value
  || runtimePxUuidEvidence.find((row) => row.fn === "Ng")?.value
  || null;

async function withGlobalProps(props, fn) {
  const prior = {};
  const had = {};
  for (const [key, value] of Object.entries(props || {})) {
    had[key] = Object.prototype.hasOwnProperty.call(globalThis, key);
    prior[key] = globalThis[key];
    globalThis[key] = value;
  }
  try {
    return await fn();
  } finally {
    for (const key of Object.keys(props || {})) {
      if (had[key]) globalThis[key] = prior[key];
      else delete globalThis[key];
    }
  }
}

const primary = await instantiateWithLog(bytes);
const wasmExports = primary.exports;
const glue = primary.glue;

const exportSummary = WebAssembly.Module.exports(new WebAssembly.Module(bytes));
const wrapperMapping = {
  evidence: {
    source: path.join(repo, "output/outlook_browser/js_static_analysis/captcha.beautified.js"),
    lines: "wrapper around f[v(\"Ng\")] and f[v(\"NQ\")] calls c[n(\"Ng\")]/c[n(\"NQ\")] at approximately 9428-9468",
    decoder: "top-level u(): base64 decode then XOR with key W6ypnhT; observed in captcha.beautified.js lines 1-30",
  },
  encoded: {
    ng: "Ng",
    nq: "NQ",
    exportsProperty: "Mk4JHxwcJw",
  },
  decoded: {
    ngExport: decodeTopLevelU("Ng"),
    nqExport: decodeTopLevelU("NQ"),
    exportsProperty: decodeTopLevelU("Mk4JHxwcJw"),
  },
};
const replay = [];
for (const sample of samples) {
  const perExport = {};
  for (const fnName of ["a", "b"]) {
    const nq = callNq(wasmExports, fnName, sample.nInput, glue.passString, glue.readRet);
    perExport[fnName] = {
      functionLength: wasmExports[fnName].length,
      asNq: {
        len: nq.value.length,
        value: nq.value,
        matchesTrace: nq.value === sample.nqValue,
      },
    };
  }
  replay.push({ ...sample, perExport });
}

const sequenceReplay = [];
for (const sample of samples) {
  const nqOnly = await instantiateWithLog(bytes);
  const nqOnlyStart = nqOnly.calls.length;
  const nqOnlyRet = callNq(nqOnly.exports, wrapperMapping.decoded.nqExport, sample.nInput, nqOnly.glue.passString, nqOnly.glue.readRet);

  const ngThenNq = await instantiateWithLog(bytes);
  const ngRet = callNg(ngThenNq.exports, wrapperMapping.decoded.ngExport, ngThenNq.glue.readRet);
  const afterNgCallCount = ngThenNq.calls.length;
  const nqAfterNgRet = callNq(ngThenNq.exports, wrapperMapping.decoded.nqExport, sample.nInput, ngThenNq.glue.passString, ngThenNq.glue.readRet);

  sequenceReplay.push({
    line: sample.line,
    nInput: sample.nInput,
    nqOnly: {
      len: nqOnlyRet.value.length,
      value: nqOnlyRet.value,
      matchesTrace: nqOnlyRet.value === sample.nqValue,
      importCalls: summarizeCalls(nqOnly.calls.slice(nqOnlyStart)),
    },
    ngThenNq: {
      ngLen: ngRet.value.length,
      ngValue: ngRet.value,
      nqLen: nqAfterNgRet.value.length,
      nqValue: nqAfterNgRet.value,
      matchesTrace: nqAfterNgRet.value === sample.nqValue,
      ngImportCalls: summarizeCalls(ngThenNq.calls.slice(0, afterNgCallCount)),
      nqImportCalls: summarizeCalls(ngThenNq.calls.slice(afterNgCallCount)),
    },
  });
}

const environmentReplay = [];
for (const sample of samples) {
  for (const env of [
    { name: "node_like_instanceof_window_false", options: { instanceofWindow: false } },
    { name: "browser_like_instanceof_window_true", options: { instanceofWindow: true } },
  ]) {
    const inst = await instantiateWithLog(bytes, env.options);
    const ret = callNq(inst.exports, wrapperMapping.decoded.nqExport, sample.nInput, inst.glue.passString, inst.glue.readRet);
    environmentReplay.push({
      line: sample.line,
      env: env.name,
      len: ret.value.length,
      value: ret.value,
      matchesTrace: ret.value === sample.nqValue,
      importCalls: summarizeCalls(inst.calls),
    });
  }
}

const pxUuidReplay = [];
if (runtimePxUuid) {
  for (const sample of samples) {
    for (const env of [
      { name: "pxuuid_nq_only_window_true", options: { instanceofWindow: true }, sequence: "nqOnly" },
      { name: "pxuuid_ng_then_nq_window_true", options: { instanceofWindow: true }, sequence: "ngThenNq" },
    ]) {
      await withGlobalProps({ _pxUuid: runtimePxUuid }, async () => {
        const inst = await instantiateWithLog(bytes, env.options);
        let ngRet = null;
        const beforeNqCallCount = inst.calls.length;
        if (env.sequence === "ngThenNq") {
          ngRet = callNg(inst.exports, wrapperMapping.decoded.ngExport, inst.glue.readRet);
        }
        const afterNgCallCount = inst.calls.length;
        const ret = callNq(inst.exports, wrapperMapping.decoded.nqExport, sample.nInput, inst.glue.passString, inst.glue.readRet);
        pxUuidReplay.push({
          line: sample.line,
          env: env.name,
          runtimePxUuid,
          sequence: env.sequence,
          ngLen: ngRet?.value?.length ?? null,
          ngValue: ngRet?.value ?? null,
          len: ret.value.length,
          value: ret.value,
          matchesTrace: ret.value === sample.nqValue,
          allImportCalls: summarizeCalls(inst.calls.slice(beforeNqCallCount)),
          nqImportCalls: summarizeCalls(inst.calls.slice(afterNgCallCount)),
        });
      });
    }
  }
}

const ngProbe = {};
for (const fnName of ["a", "b"]) {
  const ret = callNg(wasmExports, fnName, glue.readRet);
  ngProbe[fnName] = {
    functionLength: wasmExports[fnName].length,
    len: ret.value.length,
    value: ret.value,
  };
}

const result = {
  purpose: "Offline replay captcha WASM exports against runtime hsprotect.captcha.tbr9.after_nq samples.",
  inputs: { run, wasmPath, tracePath },
  wasm: { sha256: wasmSha256, byteLen: bytes.length, exports: exportSummary },
  wrapperMapping,
  samples,
  runtimePxUuidEvidence,
  ngProbe,
  replay,
  sequenceReplay,
  environmentReplay,
  pxUuidReplay,
  checks: {
    hasAfterNqSamples: samples.length > 0,
    wrapperExportsPropertyIsExports: wrapperMapping.decoded.exportsProperty === "exports",
    wrapperNgExportExists: typeof wasmExports[wrapperMapping.decoded.ngExport] === "function",
    wrapperNqExportExists: typeof wasmExports[wrapperMapping.decoded.nqExport] === "function",
    wrapperNqExportMatchesAnyTrace: replay.some((row) => row.perExport[wrapperMapping.decoded.nqExport]?.asNq.matchesTrace),
    wrapperNqFreshInstanceMatchesAnyTrace: sequenceReplay.some((row) => row.nqOnly.matchesTrace || row.ngThenNq.matchesTrace),
    wrapperNqFreshInstanceAlwaysEmpty: sequenceReplay.every((row) => row.nqOnly.len === 0 && row.ngThenNq.nqLen === 0),
    browserLikeInstanceofWindowMatchesAnyTrace: environmentReplay.some((row) => row.env === "browser_like_instanceof_window_true" && row.matchesTrace),
    browserLikeInstanceofWindowAlwaysEmpty: environmentReplay
      .filter((row) => row.env === "browser_like_instanceof_window_true")
      .every((row) => row.len === 0),
    hasRuntimePxUuidEvidence: !!runtimePxUuid,
    pxUuidNqOnlyMatchesAnyTrace: pxUuidReplay.some((row) => row.sequence === "nqOnly" && row.matchesTrace),
    pxUuidNgThenNqMatchesAnyTrace: pxUuidReplay.some((row) => row.sequence === "ngThenNq" && row.matchesTrace),
    pxUuidReplayMatchesAnyTrace: pxUuidReplay.some((row) => row.matchesTrace),
    anyExportMatchesAnyTrace: replay.some((row) => Object.values(row.perExport).some((v) => v.asNq.matchesTrace)),
    allBAsNqEmpty: replay.every((row) => row.perExport.b.asNq.len === 0),
    aAsNqProducesHexLike127: replay.every((row) => /^[0-9a-f]+$/.test(row.perExport.a.asNq.value) && row.perExport.a.asNq.len === 127),
  },
  conclusion: "Static wrapper decoding proves Ws.NQ maps to WASM export b and Ws.Ng maps to export a. This standalone replay instantiates the captured WASM but does not reproduce runtime Ws.NQ(n): mapped export b returns empty under fresh NQ-only, fresh Ng-then-NQ, and a forced browser-like instanceof(Window)=true probe with the minimal offline glue, while export a returns hex-like output that does not match runtime nqValue. More browser wasm-bindgen state/import behavior must be captured before replacing runtime Ws.NQ.",
};

fs.mkdirSync(outDir, { recursive: true });
const jsonPath = path.join(outDir, `captcha_wasm_nq_replay_${run}.json`);
const mdPath = path.join(outDir, `captcha_wasm_nq_replay_${run}.md`);
fs.writeFileSync(jsonPath, JSON.stringify(result, null, 2));

const md = [
  "# captcha WASM NQ offline replay",
  "",
  `- run: \`${run}\``,
  `- wasm: \`${wasmPath}\``,
  `- trace: \`${tracePath}\``,
  `- sha256: \`${wasmSha256}\``,
  `- wrapper Ng export: \`${wrapperMapping.decoded.ngExport}\``,
  `- wrapper NQ export: \`${wrapperMapping.decoded.nqExport}\``,
  `- wrapper instance property: \`${wrapperMapping.decoded.exportsProperty}\``,
  "",
  "## Checks",
  "",
  "| check | value |",
  "|---|---:|",
  ...Object.entries(result.checks).map(([k, v]) => `| \`${k}\` | \`${v}\` |`),
  "",
  "## Replay rows",
  "",
  "| trace line | nInput len | trace nq len | export a len/match | export b len/match |",
  "|---:|---:|---:|---:|---:|",
  ...replay.map((row) => `| ${row.line} | ${row.nInputLen} | ${row.nqLen} | ${row.perExport.a.asNq.len}/\`${row.perExport.a.asNq.matchesTrace}\` | ${row.perExport.b.asNq.len}/\`${row.perExport.b.asNq.matchesTrace}\` |`),
  "",
  "## Fresh instance sequences",
  "",
  "| trace line | NQ-only len/match | Ng len then NQ len/match | NQ-only import calls | Ng-then-NQ import calls |",
  "|---:|---:|---:|---:|---:|",
  ...sequenceReplay.map((row) => `| ${row.line} | ${row.nqOnly.len}/\`${row.nqOnly.matchesTrace}\` | ${row.ngThenNq.ngLen} then ${row.ngThenNq.nqLen}/\`${row.ngThenNq.matchesTrace}\` | ${row.nqOnly.importCalls.total} | ${row.ngThenNq.nqImportCalls.total} |`),
  "",
  "## Environment probes",
  "",
  "| trace line | environment | len/match | import calls |",
  "|---:|---|---:|---:|",
  ...environmentReplay.map((row) => `| ${row.line} | \`${row.env}\` | ${row.len}/\`${row.matchesTrace}\` | ${row.importCalls.total} |`),
  "",
  "## Runtime _pxUuid probes",
  "",
  `- runtime _pxUuid: \`${runtimePxUuid || ""}\``,
  "",
  "| trace line | environment | Ng len | NQ len/match | NQ import calls |",
  "|---:|---|---:|---:|---:|",
  ...pxUuidReplay.map((row) => `| ${row.line} | \`${row.env}\` | ${row.ngLen ?? ""} | ${row.len}/\`${row.matchesTrace}\` | ${row.nqImportCalls.total} |`),
  "",
  "## Conclusion",
  "",
  result.conclusion,
];
fs.writeFileSync(mdPath, md.join("\n") + "\n");

console.log(JSON.stringify({ json: jsonPath, md: mdPath, checks: result.checks }, null, 2));
