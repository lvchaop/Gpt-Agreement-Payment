#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function usage() {
  console.error("usage: node tools/compute_wasm_nq_once.mjs --wasm PATH --pxuuid UUID --ninput HEX --out PATH [--expect VALUE] [--random-hex-seq HEX[,HEX...]]");
  process.exit(2);
}

const args = process.argv.slice(2);
const opts = {};
for (let i = 0; i < args.length; i += 2) {
  if (!args[i]?.startsWith("--") || i + 1 >= args.length) usage();
  opts[args[i].slice(2)] = args[i + 1];
}
if (!opts.wasm || !opts.pxuuid || !opts.ninput || !opts.out) usage();

function parseRandomHexSeq(value) {
  if (!value) return [];
  let parts;
  const trimmed = value.trim();
  if (trimmed.startsWith("[")) parts = JSON.parse(trimmed);
  else parts = trimmed.split(",");
  return parts.map((part, idx) => {
    const hex = String(part).replace(/^0x/i, "").replace(/\s+/g, "");
    if (!/^[0-9a-f]*$/i.test(hex) || hex.length % 2 !== 0) {
      throw new Error(`invalid --random-hex-seq entry ${idx}: expected even-length hex`);
    }
    return Buffer.from(hex, "hex");
  });
}

function decodeTopLevelU(encoded) {
  const key = "W6ypnhT";
  const padded = encoded + "=".repeat((4 - encoded.length % 4) % 4);
  const bytes = Buffer.from(padded, "base64");
  let out = "";
  for (let i = 0; i < bytes.length; i++) out += String.fromCharCode(bytes[i] ^ key.charCodeAt(i % key.length));
  return out;
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
  const randomHexSeq = Array.isArray(options.randomHexSeq) ? options.randomHexSeq : [];
  let randomHexSeqOffset = 0;

  function fillRandom(arr, apiName, objIdx) {
    const len = arr?.length ?? 0;
    if (randomHexSeqOffset < randomHexSeq.length) {
      const next = randomHexSeq[randomHexSeqOffset++];
      if (next.length !== len) {
        throw new Error(`${apiName} deterministic random length mismatch at index ${randomHexSeqOffset - 1}: need ${len}, got ${next.length}`);
      }
      arr.set(next);
      record(apiName, { len, source: "provided", hex: Buffer.from(arr).toString("hex") });
      return arr;
    }
    const obj = getObject(objIdx);
    const ret = apiName === "__wbg_randomFillSync_dc1e9a60c158336d" ? obj.randomFillSync(arr) : obj.getRandomValues(arr);
    record(apiName, { len, source: "runtime", hex: Buffer.from(arr).toString("hex") });
    return ret;
  }

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
        const prop = getString(ptr, len);
        record("__wbg_get_e6ae480a4b8df368", { prop });
        const ret = getObject(objIdx)?.[prop];
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
        return fillRandom(arr, "__wbg_getRandomValues_37fa2ca9e4e07fab", objIdx);
      },
      __wbg_randomFillSync_dc1e9a60c158336d: (objIdx, arrIdx) => {
        const arr = takeObject(arrIdx);
        return fillRandom(arr, "__wbg_randomFillSync_dc1e9a60c158336d", objIdx);
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

function callNg(exports, fnName, readRet) {
  const sp = exports.__wbindgen_add_to_stack_pointer(-16);
  try {
    exports[fnName](sp);
    return readRet(sp);
  } finally {
    exports.__wbindgen_add_to_stack_pointer(16);
  }
}

function summarizeCalls(calls) {
  const counts = {};
  for (const call of calls) counts[call.name] = (counts[call.name] || 0) + 1;
  return { counts, firstCalls: calls.slice(0, 30), total: calls.length };
}

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

async function instantiate(bytes, options) {
  let wasmExports;
  const calls = [];
  const glue = makeWbgImports(() => wasmExports, (name, detail = undefined) => {
    calls.push({ name, ...(detail ? { detail } : {}) });
  }, options);
  const { instance } = await WebAssembly.instantiate(bytes, glue.imports);
  wasmExports = instance.exports;
  return { exports: wasmExports, glue, calls };
}

const randomHexSeq = parseRandomHexSeq(opts["random-hex-seq"]);
const wasmBytes = fs.readFileSync(opts.wasm);
const wasmSha256 = crypto.createHash("sha256").update(wasmBytes).digest("hex");
const nqExport = decodeTopLevelU("NQ");
const exportSummary = WebAssembly.Module.exports(new WebAssembly.Module(wasmBytes));

const result = await withGlobalProps({ _pxUuid: opts.pxuuid }, async () => {
  const inst = await instantiate(wasmBytes, { instanceofWindow: true, randomHexSeq });
  const ngRet = opts["call-ng"] === "1" ? callNg(inst.exports, decodeTopLevelU("Ng"), inst.glue.readRet) : null;
  const beforeNqCallCount = inst.calls.length;
  const ret = callNq(inst.exports, nqExport, opts.ninput, inst.glue.passString, inst.glue.readRet);
  return {
    purpose: "Compute one Ws.NQ(nInput) value from captured captcha WASM using the offline glue path already validated against runtime traces.",
    inputs: {
      wasmPath: opts.wasm,
      pxUuid: opts.pxuuid,
      nInput: opts.ninput,
	      expect: opts.expect || null,
	      randomHexSeqProvided: randomHexSeq.length,
	    },
    wasm: {
      sha256: wasmSha256,
      byteLen: wasmBytes.length,
      exports: exportSummary,
      nqExport,
    },
    output: {
      ngValue: ngRet?.value ?? null,
      ngLen: ngRet?.value?.length ?? null,
      nqValue: ret.value,
      nqLen: ret.value.length,
      returnRecord: ret,
    },
	    importCalls: summarizeCalls(inst.calls),
	    nqImportCalls: summarizeCalls(inst.calls.slice(beforeNqCallCount)),
	    randomFillCalls: inst.calls.filter((row) =>
	      row.name === "__wbg_getRandomValues_37fa2ca9e4e07fab" ||
	      row.name === "__wbg_randomFillSync_dc1e9a60c158336d"
	    ),
    checks: {
      wasmHasNqExport: exportSummary.some((row) => row.name === nqExport && row.kind === "function"),
      pxUuidLooksUuid: /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(opts.pxuuid),
      nInputLooks64Hex: /^[0-9a-f]{64}$/i.test(opts.ninput),
      nqValueNonEmpty: ret.value.length > 0,
      ngCalled: opts["call-ng"] === "1",
      ngValueNonEmpty: opts["call-ng"] === "1" ? (ngRet?.value?.length ?? 0) > 0 : null,
      expectProvided: typeof opts.expect === "string",
      expectMatches: typeof opts.expect === "string" ? ret.value === opts.expect : null,
      usedPxUuidImportPath: inst.calls.some((row) => row.name === "__wbg_get_e6ae480a4b8df368" && row.detail?.prop === "_pxUuid"),
      importCallCount: inst.calls.length,
    },
  };
});

fs.mkdirSync(path.dirname(opts.out), { recursive: true });
fs.writeFileSync(opts.out, JSON.stringify(result, null, 2));
console.log(JSON.stringify({ out: opts.out, checks: result.checks, nqValue: result.output.nqValue }, null, 2));
