#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
TS_FIELDS = REPO / "output/protocol_reverse/source_offsets/captcha_ts_callback_fields.json"
REMAINING_FIELDS = REPO / "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.json"
BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def short(value: Any, limit: int = 180) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<len={len(value)}>"
    return value


def value_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return f"str[{len(value)}]"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def extract_success_px561() -> dict[str, Any]:
    bundle = load_json(BUNDLE)
    req = next(r for r in bundle["requests"] if r.get("requestLine") == 308)
    px561_match = next(item for item in req["activitiesWithMatches"] if item.get("type") == "PX561")
    d = px561_match["activity"]["d"]
    return {
        "requestLine": req["requestLine"],
        "seq": req["seq"],
        "activityIndex": px561_match["index"],
        "d": d,
        "keys": list(d.keys()),
    }


def line_slice(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [{"line": n, "text": lines[n - 1]} for n in range(start, end + 1)]


def main() -> None:
    ts = load_json(TS_FIELDS)
    remaining = load_json(REMAINING_FIELDS)
    success = extract_success_px561()
    final_d = success["d"]
    final_keys = success["keys"]

    # These are the assignments made to the same r object in captcha.beautified.js:11083-11098
    # before i("PX561", r) hands r to main. Window handler calls are not fields on r.
    direct_records = [
        rec
        for rec in ts["records"]
        if rec["expr"].startswith("r[")
    ]
    direct_rows = []
    for idx, rec in enumerate(direct_records, start=1):
        key = rec["decoded"]
        present = key in final_d
        final_index = final_keys.index(key) if present else None
        final_value = final_d.get(key)
        direct_rows.append(
            {
                "directOrder": idx,
                "expr": rec["expr"],
                "decoded": key,
                "valueExpr": rec["valueExpr"],
                "lineRef": rec["lineRef"],
                "finalPresent": present,
                "finalIndex": final_index,
                "finalValueKind": value_kind(final_value),
                "finalValue": short(final_value),
            }
        )

    by_key = {row["decoded"]: row for row in direct_rows}
    tbr = by_key["TBR9Ugl7emA="]
    aeax = by_key["AEAxBkUsPjQ="]
    bzt = by_key["Bzt2fUFRcw=="]

    tbr_static_before_aeax = tbr["directOrder"] < aeax["directOrder"]
    tbr_final_after_aeax = tbr["finalIndex"] > aeax["finalIndex"]

    captcha_snippet = line_slice(CAPTCHA, 11066, 11099)
    snippet_text = "\n".join(item["text"] for item in captcha_snippet)
    delete_mentions = [
        item for item in captcha_snippet if "delete" in item["text"] or "TBR9Ugl7emA" in item["text"]
    ]

    result = {
        "inputs": {
            "tsFields": str(TS_FIELDS),
            "remainingFields": str(REMAINING_FIELDS),
            "bundle": str(BUNDLE),
            "captcha": str(CAPTCHA),
        },
        "successPx561": {
            "requestLine": success["requestLine"],
            "seq": success["seq"],
            "activityIndex": success["activityIndex"],
            "keyCount": len(final_d),
        },
        "preYcDirectRows": direct_rows,
        "orderChecks": {
            "tbrDirectOrder": tbr["directOrder"],
            "aeaxDirectOrder": aeax["directOrder"],
            "tbrStaticBeforeAeax": tbr_static_before_aeax,
            "tbrFinalIndex": tbr["finalIndex"],
            "aeaxFinalIndex": aeax["finalIndex"],
            "bztFinalIndex": bzt["finalIndex"],
            "tbrFinalAfterAeax": tbr_final_after_aeax,
        },
        "sourceSnippet": {
            "captcha_11066_11099": captcha_snippet,
            "deleteMentionsInSnippet": delete_mentions,
            "containsDeleteTbrInSnippet": "delete" in snippet_text and "TBR9Ugl7emA=" in snippet_text,
        },
        "remainingFieldEvidence": remaining["records"],
        "findings": [
            "Static captcha D/Ts direct assignments put TBR9Ugl7emA= before AEAxBkUsPjQ= on the same r object.",
            "The final decoded success PX561 order puts AEAxBkUsPjQ= at index 74 and TBR9Ugl7emA= at index 75.",
            "The direct TBR9 assignment value expression is _s() boolean, while the final success value is a 127-byte string.",
            "The inspected D/Ts snippet has no delete/re-add of TBR9Ugl7emA=; only a separate delete on the PX1200 pre-submit d object is visible.",
            "Therefore the final TBR9 long string cannot be explained by the direct captcha.beautified.js:11083 assignment alone.",
        ],
        "nextEvidenceTargets": [
            "Audit Ws.NQ(n) return material because Yc flattens object-valued fields and the final sequence around fyNOZTpPQF4=/AEAx/TBR9 is consistent with a nested success object or later rewrite.",
            "If Ws.NQ(n) does not contain TBR9Ugl7emA=, inspect the main-side payload decode/inverse assumptions around Vs marker insertion and bundle decode.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "px561_preyc_static_reconstruction.json"
    md_path = OUT_DIR / "px561_preyc_static_reconstruction.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = [
        "# PX561 pre-Yc static reconstruction",
        "",
        "## Inputs",
        "",
    ]
    for name, path in result["inputs"].items():
        md.append(f"- {name}: `{path}`")
    md += [
        "",
        "## Success target",
        "",
        f"- requestLine: `{result['successPx561']['requestLine']}`",
        f"- seq: `{result['successPx561']['seq']}`",
        f"- activityIndex: `{result['successPx561']['activityIndex']}`",
        f"- keyCount: `{result['successPx561']['keyCount']}`",
        "",
        "## Direct pre-Yc r assignments vs final PX561",
        "",
        "| direct order | decoded key | value expr | final present | final index | final value kind | final value |",
        "|---:|---|---|---:|---:|---|---|",
    ]
    for row in direct_rows:
        md.append(
            f"| {row['directOrder']} | `{row['decoded']}` | `{row['valueExpr']}` | "
            f"`{row['finalPresent']}` | `{row['finalIndex']}` | `{row['finalValueKind']}` | `{row['finalValue']}` |"
        )
    md += [
        "",
        "## Order checks",
        "",
    ]
    for key, value in result["orderChecks"].items():
        md.append(f"- {key}: `{value}`")
    md += [
        "",
        "## Findings",
        "",
    ]
    for finding in result["findings"]:
        md.append(f"- {finding}")
    md += [
        "",
        "## Next evidence targets",
        "",
    ]
    for target in result["nextEvidenceTargets"]:
        md.append(f"- {target}")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
