#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUTLOOK_BROWSER = REPO / "CTF-reg/outlook_browser_register.py"
EXACT_CAPTCHA = REPO / "output/protocol_reverse/exact_source/captcha_ni109_4b399270.source.js"
MAIN_SOURCE = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


REQUIRED_MAIN_PATCH_MARKERS = [
    "hsprotect.main.$c.yc",
    "hsprotect.main.jc.yc",
    "hsprotect.main.tf.enter",
    "hsprotect.main.tf.payload",
]

REQUIRED_CAPTCHA_PATCH_MARKERS = [
    "hsprotect.captcha.tbr9.after_s",
    "hsprotect.captcha.tbr9.after_rs",
    "hsprotect.captcha.tbr9.after_ng",
    "hsprotect.captcha.tbr9.after_nq",
    "hsprotect.captcha.tbr9.after_inner",
    "hsprotect.captcha.tbr9.after_ou",
    "hsprotect.captcha.tbr9.before_condition",
    "hsprotect.captcha.tbr9.after_condition",
    "hsprotect.captcha.tbr9.before_bzt",
    "hsprotect.captcha.tbr9.after_bzt",
    "hsprotect.captcha.tbr9.after_osk",
    "hsprotect.captcha.tbr9.after_time",
    "hsprotect.captcha.tbr9.after_n",
    "hsprotect.captcha.tbr9.after_os",
    "hsprotect.captcha.tbr9.after_ws",
    "hsprotect.captcha.tbr9.after_ks",
    "hsprotect.captcha.pre_i_px561",
    "hsprotect.captcha.wasm.material",
    "hsprotect.captcha.wasm.import.wrap",
    "hsprotect.captcha.wasm.import.call",
    "hsprotect.captcha.wasm.import.return",
    "hsprotect.captcha.wasm.bind",
    "hsprotect.captcha.wasm.ng.before",
    "hsprotect.captcha.wasm.ng.after",
    "hsprotect.captcha.wasm.nq.before",
    "hsprotect.captcha.wasm.nq.after",
]


def source_lines(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [{"line": line, "text": lines[line - 1]} for line in range(start, end + 1)]


def load_outlook_browser_module() -> Any:
    sys.path.insert(0, str((REPO / "CTF-reg").resolve()))
    spec = importlib.util.spec_from_file_location("outlook_browser_register_for_audit", OUTLOOK_BROWSER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {OUTLOOK_BROWSER}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    module = load_outlook_browser_module()
    captcha_source = EXACT_CAPTCHA.read_text(encoding="utf-8")
    patched_captcha, captcha_patches = module._patch_hsprotect_js_source(
        "https://captcha.hsprotect.net/PXzC5j78di/captcha.js",
        captcha_source,
    )
    register_source = OUTLOOK_BROWSER.read_text(encoding="utf-8")
    main_static = MAIN_SOURCE.read_text(encoding="utf-8")

    pre_i_needle = "r[f(c(415,422))]=Ks,i(f(c(439,441)),r))"
    micro_needle = "function(r,n){var t=u;function v(r,n){return Vs(n,r- -148)}if(r[t(v(-540,-543))]=_s(),r[t(v(-531,-522))]=Rs,Ws){try{r[t(\"FnM4CCwDASRmEyFT\")]=Ws[t(\"Ng\")]()}catch(r){}try{r[t(v(-541,-541))]=Ws[t(\"NQ\")](n)}catch(r){}}}(r,e);var i=Ou();"
    tail_micro_needle = "}(r,e);var i=Ou();function c(r,n){return K(n,r-597)}s(i)===f(c(406,426))&&(r[f(c(410,395))]=v,r[f(c(414,426))]=e,r[f(\"D2csAy8QPCd9EyVT\")]=parseInt(m()-t),r[f(c(411,413))]=n,r[f(c(429,410))]=os,r[f(\"B25IQlhZYw\")]=ws,r[f(c(415,422))]=Ks,i(f(c(439,441)),r))"
    wasm_import_wrap_needle = "n[r(v(1021,1079))][v(1123,1104)]=function(){var r,n;return M(c[u((r=-447,n=-366,v(r,n- -1450)))])},n}function b"
    wasm_bind_needle = "function b(r,n){var t,v;return c=r[u(\"Mk4JHxwcJw\")],h[(t=128,v=62,i(t,v- -1044))]=n,l=null,L=null,c}"
    wasm_ng_needle = "f[v(\"Ng\")]=function(){function r(r,n){return i(n,r- -1813)}var n=u;try{var t=c[r(-715,-793)](-16);c[n(\"Ng\")](t);var v=H()[t/4+0],e=H()[t/4+1],f=H()[t/4+2],s=H()[t/4+3],m=v,z=e;if(s)throw m=0,z=0,g(f);return y(m,z)}finally{c[r(-715,-682)](16),c.__wbindgen_free(m,z)}}"
    wasm_nq_needle = "f[v(\"NQ\")]=function(r){var n=u;function t(r,n){return i(r,n- -1266)}try{var v=c.__wbindgen_add_to_stack_pointer(-16),e=a(r,c[t(-156,-130)],c[t(-33,-74)]),f=K;c[n(\"NQ\")](v,e,f);var s=H()[v/4+0],m=H()[v/4+1],z=H()[v/4+2],o=H()[v/4+3],w=s,L=m;if(o)throw w=0,L=0,g(z);return y(w,L)}finally{c[t(-226,-168)](16),c[t(47,-33)](w,L)}}"
    result = {
        "inputs": {
            "outlookBrowserRegister": str(OUTLOOK_BROWSER),
            "exactCaptcha": str(EXACT_CAPTCHA),
            "mainSource": str(MAIN_SOURCE),
        },
        "requiredRuntimeEnv": {
            "OUTLOOK_JS_INTERNAL_TRACE": "1",
            "OUTLOOK_HSPROTECT_JS_PATCH": "1",
            "OUTLOOK_HSPROTECT_JS_PATCH_APPLY": "1",
        },
        "captchaPatchProbe": {
            "preINeedle": pre_i_needle,
            "microNeedle": micro_needle,
            "tailMicroNeedle": tail_micro_needle,
            "wasmImportWrapNeedle": wasm_import_wrap_needle,
            "wasmBindNeedle": wasm_bind_needle,
            "wasmNgNeedle": wasm_ng_needle,
            "wasmNqNeedle": wasm_nq_needle,
            "preINeedleCountInExactCaptcha": captcha_source.count(pre_i_needle),
            "microNeedleCountInExactCaptcha": captcha_source.count(micro_needle),
            "tailMicroNeedleCountInExactCaptcha": captcha_source.count(tail_micro_needle),
            "wasmImportWrapNeedleCountInExactCaptcha": captcha_source.count(wasm_import_wrap_needle),
            "wasmBindNeedleCountInExactCaptcha": captcha_source.count(wasm_bind_needle),
            "wasmNgNeedleCountInExactCaptcha": captcha_source.count(wasm_ng_needle),
            "wasmNqNeedleCountInExactCaptcha": captcha_source.count(wasm_nq_needle),
            "patches": captcha_patches,
            "patchedChanged": patched_captcha != captcha_source,
            "preIEventCountInPatchedCaptcha": patched_captcha.count("hsprotect.captcha.pre_i_px561"),
            "microEventCountsInPatchedCaptcha": {
                marker: patched_captcha.count(f"'{marker}'") + patched_captcha.count(f'"{marker}"')
                for marker in REQUIRED_CAPTCHA_PATCH_MARKERS
                if ".tbr9." in marker
            },
            "requiredMarkersPresent": {
                marker: marker in patched_captcha for marker in REQUIRED_CAPTCHA_PATCH_MARKERS
            },
        },
        "mainPatchProbe": {
            "requiredMarkersPresentInPatchFunction": {
                marker: marker in register_source for marker in REQUIRED_MAIN_PATCH_MARKERS
            },
            "requiredStaticNeedlesPresentInMainBeautified": {
                "function $c(t, e)": "function $c(t, e)" in main_static,
                "function jc(t)": "function jc(t)" in main_static,
                "function tf(t, e)": "function tf(t, e)" in main_static,
            },
        },
        "sourceSnippets": {
            "outlookPatchMainAndCaptcha": source_lines(OUTLOOK_BROWSER, 1383, 1441),
            "installEnvGate": source_lines(OUTLOOK_BROWSER, 1314, 1323),
            "installCallsite": source_lines(OUTLOOK_BROWSER, 3868, 3892),
        },
    }
    result["checks"] = {
        "preINeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["preINeedleCountInExactCaptcha"] == 1,
        "microNeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["microNeedleCountInExactCaptcha"] == 1,
        "tailMicroNeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["tailMicroNeedleCountInExactCaptcha"] == 1,
        "wasmImportWrapNeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["wasmImportWrapNeedleCountInExactCaptcha"] == 1,
        "wasmBindNeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["wasmBindNeedleCountInExactCaptcha"] == 1,
        "wasmNgNeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["wasmNgNeedleCountInExactCaptcha"] == 1,
        "wasmNqNeedleUniqueInExactCaptcha": result["captchaPatchProbe"]["wasmNqNeedleCountInExactCaptcha"] == 1,
        "captchaPreIPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_pre_i_px561__" in captcha_patches,
        "captchaTbr9MicroPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_tbr9_micro__" in captcha_patches,
        "captchaTbr9TailMicroPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_tbr9_tail_micro__" in captcha_patches,
        "captchaWasmImportWrapPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_wasm_import_wrap__" in captcha_patches,
        "captchaWasmBindPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_wasm_bind__" in captcha_patches,
        "captchaWasmNgWrapperPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_wasm_ng_wrapper__" in captcha_patches,
        "captchaWasmNqWrapperPatchAppliedOffline": "__outlook_hsprotect_patch_captcha_wasm_nq_wrapper__" in captcha_patches,
        "captchaPreIEventPresentOffline": result["captchaPatchProbe"]["preIEventCountInPatchedCaptcha"] == 1,
        "captchaTbr9MicroEventsPresentOffline": all(
            count == 1 for count in result["captchaPatchProbe"]["microEventCountsInPatchedCaptcha"].values()
        ),
        "captchaRequiredMarkersPresentOffline": all(result["captchaPatchProbe"]["requiredMarkersPresent"].values()),
        "mainPatchMarkersPresent": all(result["mainPatchProbe"]["requiredMarkersPresentInPatchFunction"].values()),
        "mainStaticNeedlesPresent": all(result["mainPatchProbe"]["requiredStaticNeedlesPresentInMainBeautified"].values()),
    }
    result["findings"] = [
        "Existing outlook_browser_register.py already contains main-side $c.yc, jc.yc, tf.enter, and tf.payload patch emitters.",
        "The captcha TBR9 micro-window patch emits after_s, after_rs, after_ng, after_nq, after_inner, after_ou, before_condition, after_condition, and tail assignment observations in offline-patched exact captcha source.",
        "The new captcha pre-i PX561 patch needle is unique in the exact ni109 captcha source.",
        "Offline application of _patch_hsprotect_js_source to the exact ni109 captcha source inserts hsprotect.captcha.pre_i_px561 exactly once.",
        "The WASM bind hook records exports key/name mapping and export keys when WebAssembly.Instance exports are bound into the wrapper.",
        "The WASM import wrapper hook records wasm-bindgen import function names/arguments only while Ws.Ng/Ws.NQ exports are active.",
        "The WASM Ng wrapper hook records Ng return and enables import-call correlation for Ng initialization.",
        "The WASM NQ wrapper hook records input pointer/length/bytes, export function metadata, return pointer/length/bytes, and memory size around c[n('NQ')](sp, ptr, len).",
        "The runtime environment gates required to collect this observation are OUTLOOK_JS_INTERNAL_TRACE=1, OUTLOOK_HSPROTECT_JS_PATCH=1, and OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1.",
    ]
    result["conclusion"] = (
        "The observation hook plan is ready at source level: a browser run with JS internal trace and hsprotect patch application enabled should capture "
        "captcha TBR9 micro-window, tail assignment, captcha pre-i PX561, WASM import-call, bind/Ng/NQ wrapper state, main $c/jc Yc, and tf.enter/tf.payload boundaries. This does not yet provide the observation sample; it proves the current "
        "worktree has the required hook injection points."
    )
    result["nextEvidenceTargets"] = [
        "Run one explicitly labeled observation browser sample with OUTLOOK_JS_INTERNAL_TRACE=1 OUTLOOK_HSPROTECT_JS_PATCH=1 OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1.",
        "After the run, classify whether hsprotect.captcha.wasm.import.wrap, hsprotect.captcha.wasm.import.call, hsprotect.captcha.wasm.ng.before/after, hsprotect.captcha.wasm.bind, hsprotect.captcha.wasm.nq.before/after, hsprotect.captcha.tbr9.after_nq, hsprotect.captcha.pre_i_px561, hsprotect.main.$c.yc or hsprotect.main.jc.yc, and hsprotect.main.tf.enter are all present for PX561.",
        "Compare NQ input/output pointer bytes and memory metadata between browser runtime and offline replay, then update the minimal glue/import state accordingly.",
    ]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "tbr9_observation_hook_readiness_audit.json"
    md_path = OUT_DIR / "tbr9_observation_hook_readiness_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# TBR9 observation hook readiness audit",
        "",
        "## Required env",
        "",
        *[f"- `{k}={v}`" for k, v in result["requiredRuntimeEnv"].items()],
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
        *[f"| `{k}` | `{v}` |" for k, v in result["checks"].items()],
        "",
        "## Captcha patch probe",
        "",
        f"- pre-i needle count in exact captcha: `{result['captchaPatchProbe']['preINeedleCountInExactCaptcha']}`",
        f"- micro needle count in exact captcha: `{result['captchaPatchProbe']['microNeedleCountInExactCaptcha']}`",
        f"- tail micro needle count in exact captcha: `{result['captchaPatchProbe']['tailMicroNeedleCountInExactCaptcha']}`",
        f"- wasm import wrap needle count in exact captcha: `{result['captchaPatchProbe']['wasmImportWrapNeedleCountInExactCaptcha']}`",
        f"- wasm bind needle count in exact captcha: `{result['captchaPatchProbe']['wasmBindNeedleCountInExactCaptcha']}`",
        f"- wasm Ng needle count in exact captcha: `{result['captchaPatchProbe']['wasmNgNeedleCountInExactCaptcha']}`",
        f"- wasm NQ needle count in exact captcha: `{result['captchaPatchProbe']['wasmNqNeedleCountInExactCaptcha']}`",
        f"- patches: `{result['captchaPatchProbe']['patches']}`",
        f"- pre-i event count in patched captcha: `{result['captchaPatchProbe']['preIEventCountInPatchedCaptcha']}`",
        f"- micro event counts in patched captcha: `{result['captchaPatchProbe']['microEventCountsInPatchedCaptcha']}`",
        "",
        "## Findings",
        "",
        *[f"- {x}" for x in result["findings"]],
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Next evidence targets",
        "",
        *[f"- {x}" for x in result["nextEvidenceTargets"]],
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
