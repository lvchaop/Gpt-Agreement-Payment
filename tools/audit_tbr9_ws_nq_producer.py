#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BOUNDARY = REPO / "output/protocol_reverse/source_offsets/tbr9_micro_runtime_boundary_audit.json"
WASM = REPO / "output/protocol_reverse/source_offsets/captcha_wasm_pow_boundaries_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def cycle_summary(cycle: dict[str, Any]) -> dict[str, Any]:
    events = cycle.get("events") or []
    by_kind = {ev.get("kind"): ev for ev in events}
    after_ng = by_kind.get("hsprotect.captcha.tbr9.after_ng") or {}
    after_nq = by_kind.get("hsprotect.captcha.tbr9.after_nq") or {}
    after_inner = by_kind.get("hsprotect.captcha.tbr9.after_inner") or {}
    return {
        "startLine": cycle.get("startLine"),
        "firstLongStringBoundary": cycle.get("firstLongStringBoundary"),
        "afterNg": {
            "line": after_ng.get("line"),
            "key": after_ng.get("key"),
            "tbr": after_ng.get("tbr"),
            "aeaxKey": after_ng.get("aeaxKey"),
            "aeaxValue": after_ng.get("aeaxValue"),
        },
        "afterNq": {
            "line": after_nq.get("line"),
            "key": after_nq.get("key"),
            "rawKey": after_nq.get("rawKey"),
            "nqKey": after_nq.get("nqKey"),
            "nInput": after_nq.get("nInput"),
            "nInputType": after_nq.get("nInputType"),
            "nInputLen": after_nq.get("nInputLen"),
            "tbr": after_nq.get("tbr"),
        },
        "afterInner": {
            "line": after_inner.get("line"),
            "key": after_inner.get("key"),
            "tbr": after_inner.get("tbr"),
        },
    }


def main() -> None:
    boundary = load_json(BOUNDARY)
    wasm = load_json(WASM)
    trace_results = boundary.get("traceResults") or []
    cycles = [cycle_summary(c) for tr in trace_results for c in (tr.get("cycles") or [])]

    wasm_facts = wasm.get("staticBoundaries", {}).get("wasmGlue", {}).get("facts") or []
    ws_nq_fact = next((fact for fact in wasm_facts if "Ws.NQ" in fact), None)
    textdecoder_fact = next((fact for fact in wasm_facts if "TextDecoder" in fact and "y(ptr,len)" in fact), None)
    d_ts = wasm.get("staticBoundaries", {}).get("D_Ts_px561", {})

    checks = {
        "boundaryAuditExists": BOUNDARY.exists(),
        "wasmAuditExists": WASM.exists(),
        "allCyclesAfterNqKeyIsTbr9": bool(cycles)
        and all(c["afterNq"].get("key") == "TBR9Ugl7emA=" for c in cycles),
        "allCyclesAfterNqIsLongString": bool(cycles)
        and all((c["afterNq"].get("tbr") or {}).get("isLongString") is True for c in cycles),
        "allCyclesAfterNgStillTracksBooleanGuard": bool(cycles)
        and all((c["afterNg"].get("tbr") or {}).get("isBoolean") is True for c in cycles),
        "firstBoundaryIsAfterNq": bool(cycles)
        and all((c.get("firstLongStringBoundary") or {}).get("kind") == "hsprotect.captcha.tbr9.after_nq" for c in cycles),
        "allCyclesHaveNInput": bool(cycles)
        and all(c["afterNq"].get("nInputType") == "string" and c["afterNq"].get("nInputLen") == 64 for c in cycles),
        "staticWsNqReturnsTextDecoderString": bool(
            ws_nq_fact and "returns y(ptr,len)" in ws_nq_fact and textdecoder_fact and "returns a JS string" in textdecoder_fact
        ),
    }
    result = {
        "purpose": "Close the runtime producer boundary for TBR9Ugl7emA= by combining after_nq hook evidence with static Ws.NQ WASM wrapper evidence.",
        "inputs": {
            "boundaryAudit": str(BOUNDARY),
            "wasmAudit": str(WASM),
        },
        "checks": checks,
        "runtimeCycles": cycles,
        "staticEvidence": {
            "wsNqFact": ws_nq_fact,
            "textDecoderFact": textdecoder_fact,
            "dTsPx561Lines": d_ts.get("lines"),
            "dTsPx561Snippet": d_ts.get("snippet"),
        },
        "correction": [
            "Earlier static decode artifacts that mapped t(v(-541,-541)) to 'succeeded' are weaker than live runtime hook evidence.",
            "In the latest successful run, after_nq reports nqKey=TBR9Ugl7emA= and nqValue as the long string in both PX561 cycles.",
            "The boolean key tracked by after_s/after_rs/after_ng is a separate guard key, not the final TBR9Ugl7emA= value.",
        ],
        "conclusion": (
            "For the audited successful run, the fresh TBR9Ugl7emA= value is produced at "
            "r[t(v(-541,-541))] = Ws[t('NQ')](n). Static WASM glue evidence shows Ws.NQ encodes its JS string input "
            "into WASM memory, calls the NQ export, and returns a TextDecoder JS string. The remaining pure-protocol gap "
            "is reproducing that Ws.NQ/WASM transform without browser runtime."
        ),
        "nextEvidenceTargets": [
            "Extract or reimplement the Ws.NQ WASM module transform for input n.",
            "Record the exact n input used for accepted cycles and verify pure JS/WASM replay returns the observed TBR9 string.",
            "Replace stale-template TBR9 in px561_pow_tail_constructor with fresh Ws.NQ output.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "tbr9_ws_nq_producer_audit.json"
    md_path = OUT_DIR / "tbr9_ws_nq_producer_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# TBR9 Ws.NQ producer audit",
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
        *[f"| `{k}` | `{v}` |" for k, v in checks.items()],
        "",
        "## Runtime cycles",
        "",
        "| start line | first boundary | nInput len | after_ng key/type | after_nq key/type/len |",
        "|---:|---|---|---|",
    ]
    for c in cycles:
        ng = c["afterNg"].get("tbr") or {}
        nq = c["afterNq"].get("tbr") or {}
        boundary_kind = (c.get("firstLongStringBoundary") or {}).get("kind")
        md.append(
            f"| {c.get('startLine')} | `{boundary_kind}` | `{c['afterNq'].get('nInputLen')}` | `{c['afterNg'].get('key')}` `{ng.get('type')}` | "
            f"`{c['afterNq'].get('key')}` `{nq.get('type')}` len `{nq.get('len')}` |"
        )
    md += [
        "",
        "## Static Ws.NQ evidence",
        "",
        f"- {ws_nq_fact}",
        f"- {textdecoder_fact}",
        "",
        "## Correction",
        "",
        *[f"- {x}" for x in result["correction"]],
        "",
        "## Conclusion",
        "",
        result["conclusion"],
    ]
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
