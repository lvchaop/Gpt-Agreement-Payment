#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/bundle_constructor"
PATCHER = REPO / "CTF-reg/outlook_browser_register.py"
MAIN_SOURCES = [
    REPO / "output/outlook_browser/hsprotect_js_patch/main_main_1781017193_50a16178f090.source.js",
    REPO / "output/outlook_browser/hsprotect_js_patch/main_main_1781116333_2d8c43c5c510.source.js",
    REPO / "output/outlook_browser/js_probe/main.min.js",
]


def load_patcher():
    sys.path.insert(0, str((REPO / "CTF-reg").resolve()))
    spec = importlib.util.spec_from_file_location("outlook_browser_register_for_pc_hook_audit", PATCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PATCHER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def snippet(text: str, needle: str, radius: int = 180) -> dict[str, Any]:
    idx = text.find(needle)
    if idx < 0:
        return {"found": False, "index": -1, "text": ""}
    return {
        "found": True,
        "index": idx,
        "text": text[max(0, idx - radius) : min(len(text), idx + len(needle) + radius)],
    }


def audit_source(patcher: Any, path: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8", errors="replace")
    patched, patches = patcher._patch_hsprotect_js_source(
        "https://client.hsprotect.net/PXzC5j78di/main.min.js",
        source,
    )
    prepc = snippet(patched, "hsprotect.main.tf.prepc")
    payload = snippet(patched, "hsprotect.main.tf.payload")
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "sourceSha256": hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest(),
        "sourceLen": len(source),
        "patches": patches,
        "hasTfEnterPatch": any("main_tf_enter" in p for p in patches),
        "hasTfPrepcPatch": any("main_tf_prepc" in p for p in patches),
        "hasTfPayloadPatch": any("main_tf_payload" in p for p in patches),
        "prepcEmitCount": patched.count("hsprotect.main.tf.prepc"),
        "payloadEmitCount": patched.count("hsprotect.main.tf.payload"),
        "prepcNeedlePresentInSource": "var s,l,f=Li(),h=Jt(ut(t),(s=e[on],l=e[cn],[po(),s,l].join(\":\"))),d={" in source,
        "payloadNeedlePresentInSource": "d={vid:Ct(),tag:e[on],appID:e[an],cu:po(),cs:f,pc:h},v=Vs(t,d),p=[" in source,
        "patchedHasSerializedForPc": "__outlookTfPcSerialized=ut(t)" in patched,
        "patchedJtUsesSerializedForPc": "h=Jt(__outlookTfPcSerialized,__outlookTfPcKey)" in patched,
        "patchedPrepcBeforePayload": (
            patched.find("hsprotect.main.tf.prepc") >= 0
            and patched.find("hsprotect.main.tf.payload") >= 0
            and patched.find("hsprotect.main.tf.prepc") < patched.find("hsprotect.main.tf.payload")
        ),
        "patchedDeclaresVarPAfterBreakingVarChain": "var p=[mr+v" in patched,
        "patchedHasBarePAfterCatch": "}catch(_){}p=[mr+v" in patched,
        "prepcSnippet": prepc,
        "payloadSnippet": payload,
    }


def main() -> int:
    patcher = load_patcher()
    rows = [audit_source(patcher, path) for path in MAIN_SOURCES if path.exists()]
    result = {
        "purpose": "Verify that the hsprotect main patch can capture the pre-pc serialized string used by Jt(ut(t), key), before Vs(t,d) serializes the payload.",
        "evidenceFiles": {
            "patcher": str(PATCHER.resolve()),
            "sources": [str(p.resolve()) for p in MAIN_SOURCES if p.exists()],
        },
        "rows": rows,
        "checks": {
            "allRowsHaveTfPrepcPatch": all(r["hasTfPrepcPatch"] for r in rows),
            "allRowsHaveTfPayloadPatch": all(r["hasTfPayloadPatch"] for r in rows),
            "allRowsEmitPrepcBeforePayload": all(r["patchedPrepcBeforePayload"] for r in rows),
            "allRowsJtUseCapturedSerializedOnce": all(r["patchedJtUsesSerializedForPc"] for r in rows),
            "allRowsDeclareVarPAfterVarChainBreak": all(r["patchedDeclaresVarPAfterBreakingVarChain"] for r in rows),
            "noRowsHaveBarePAfterCatch": not any(r["patchedHasBarePAfterCatch"] for r in rows),
        },
        "conclusion": (
            "The local hsprotect main patcher is now ready to emit hsprotect.main.tf.prepc with the exact serialized string passed into Jt and the derived key/pc before Vs(t,d). "
            "This does not prove seq=2 pc for the accepted ni109 run; it proves the next observation run can distinguish pc-time ut(t) from payload-time ut(t.slice())."
        ),
        "limitation": (
            "This is patch-readiness evidence only. It must be followed by an observation run and compared against accepted-success criteria; AEAx-only negative controls remain insufficient."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "bundle_pc_prepc_hook_readiness_audit.json"
    out_md = OUT_DIR / "bundle_pc_prepc_hook_readiness_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Bundle pc prepc hook readiness audit",
        "",
        f"- patcher: `{result['evidenceFiles']['patcher']}`",
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Sources",
        "",
        "| source | tf.enter | tf.prepc | tf.payload | prepc before payload | var p fixed | bare p bad |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| `{source}` | {enter} | {prepc} | {payload} | {order} | {varp} | {barep} |".format(
                source=row["path"],
                enter=row["hasTfEnterPatch"],
                prepc=row["hasTfPrepcPatch"],
                payload=row["hasTfPayloadPatch"],
                order=row["patchedPrepcBeforePayload"],
                varp=row["patchedDeclaresVarPAfterBreakingVarChain"],
                barep=row["patchedHasBarePAfterCatch"],
            )
        )
    lines += [
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Limitation",
        "",
        result["limitation"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
