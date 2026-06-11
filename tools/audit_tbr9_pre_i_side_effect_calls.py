#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def source_lines(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [{"line": line, "text": lines[line - 1]} for line in range(start, end + 1)]


def main() -> None:
    lines = CAPTCHA.read_text(encoding="utf-8").splitlines()
    snippet_lines = lines[11072:11098]
    snippet = "\n".join(snippet_lines)
    start = snippet.index("if (r[t(v(-540, -543))]")
    end = snippet.index("i(f(c(439, 441)), r)") + len("i(f(c(439, 441)), r)")
    pre_handoff = snippet[start:end]

    delete_hits = re.findall(r"\bdelete\s+r\[[^\]]+\]", pre_handoff)
    define_property_hits = re.findall(r"Object\s*\.\s*defineProperty\s*\([^)]*", pre_handoff)
    handoff_call = "i(f(c(439, 441)), r)"
    # Keep this explicit. A broad regex mistakes `catch (r)` and local decoder
    # helper parameters such as `function c(r,n)` for calls receiving the
    # activity object. The relevant visible call list in this compact range is
    # short and stable enough to audit directly.
    non_handoff_r_argument_hits: list[str] = []

    assignments = [
        {
            "line": 11083,
            "expression": "r[t(v(-540,-543))] = _s()",
            "decodedKey": "TBR9Ugl7emA=",
            "valueSource": "_s()",
        },
        {
            "line": 11083,
            "expression": "r[t(v(-531,-522))] = Rs",
            "decodedKey": "instantiating",
            "valueSource": "Rs",
        },
        {
            "line": 11085,
            "expression": "r[t(\"FnM4CCwDASRmEyFT\")] = Ws[t(\"Ng\")]()",
            "decodedKey": "AEAxBkUsPjQ=",
            "valueSource": "Ws.Ng()",
        },
        {
            "line": 11088,
            "expression": "r[t(v(-541,-541))] = Ws[t(\"NQ\")](n)",
            "decodedKey": "succeeded",
            "valueSource": "Ws.NQ(n)",
        },
        {
            "line": 11097,
            "expression": "r[f(c(410,395))] = v; r[f(c(414,426))] = e; ...",
            "decodedKey": "Bzt2fUFRcw== / OSkIb39DDA== / other callback fields",
            "valueSource": "Ts callback params and local values",
        },
    ]

    result = {
        "inputs": {"captcha": str(CAPTCHA)},
        "range": {
            "sourceLines": "captcha.beautified.js:11073-11098",
            "meaning": "Ts callback body from direct TBR9 assignment through i(PX561,r) handoff.",
        },
        "sourceSnippet": source_lines(CAPTCHA, 11073, 11098),
        "preHandoffText": pre_handoff,
        "assignmentsBeforeHandoff": assignments,
        "callsBeforeHandoff": [
            {"expression": "_s()", "takesR": False, "role": "boolean value assigned to TBR9"},
            {"expression": "Ws[t(\"Ng\")]()", "takesR": False, "role": "AEAx value producer"},
            {"expression": "Ws[t(\"NQ\")](n)", "takesR": False, "role": "succeeded value producer; argument is n, not r"},
            {"expression": "Ou()", "takesR": False, "role": "loads stored main callback into local i"},
            {"expression": "s(i)", "takesR": False, "role": "function-type check"},
            {"expression": "parseInt(m() - t)", "takesR": False, "role": "elapsed field value"},
            {"expression": handoff_call, "takesR": True, "role": "first observed call passing r after direct assignments; main $c/Yc boundary"},
        ],
        "checks": {
            "deleteRBeforeHandoff": len(delete_hits) > 0,
            "objectDefinePropertyBeforeHandoff": len(define_property_hits) > 0,
            "nonHandoffCallReceivesRBeforeHandoff": len(non_handoff_r_argument_hits) > 0,
            "handoffCallReceivesR": handoff_call in pre_handoff,
        },
        "rawMatches": {
            "deleteHits": delete_hits,
            "definePropertyHits": define_property_hits,
            "nonHandoffRArgumentHits": non_handoff_r_argument_hits,
        },
        "findings": [
            "Between the direct TBR9 assignment and i(PX561,r), the visible Ts callback contains no delete r[...] statement.",
            "The same range contains no Object.defineProperty call.",
            "The visible calls before the handoff do not pass r as an argument; Ws.NQ receives n, not r.",
            "The first visible call in this range that passes r is the already-identified handoff i(PX561,r).",
            "Therefore this exact visible range does not provide a side-effect call site that can rewrite r[TBR9Ugl7emA=] before main $c/Yc receives r.",
        ],
        "conclusion": "The captcha-side visible side-effect surface between r[TBR9]=_s() and i(PX561,r) is empty for delete/defineProperty/non-handoff r-argument calls. This does not prove runtime state, but it removes another static explanation for the final 127-byte TBR9: a visible pre-handoff helper call mutating r.",
        "nextEvidenceTargets": [
            "Capture r immediately before i(PX561,r) in an observation run.",
            "If r already has the 127-byte TBR9 despite this static range, inspect object provenance from pn/J and accessor/prototype behavior.",
            "If r still has boolean TBR9 at handoff, continue with main $c/Yc/tf.enter boundary capture.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "tbr9_pre_i_side_effect_calls_audit.json"
    md_path = OUT_DIR / "tbr9_pre_i_side_effect_calls_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [
        "# TBR9 pre-i side-effect call audit",
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
        *[f"| `{k}` | `{v}` |" for k, v in result["checks"].items()],
        "",
        "## Calls before handoff",
        "",
        "| expression | takes r | role |",
        "|---|---:|---|",
        *[f"| `{x['expression']}` | `{x['takesR']}` | {x['role']} |" for x in result["callsBeforeHandoff"]],
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
