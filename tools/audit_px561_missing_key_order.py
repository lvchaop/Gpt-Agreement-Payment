#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
COMPARE = REPO / "output/protocol_reverse/px561_compare/px561_accepted_vs_aeax_controls.json"
STATIC_FILES = [
    REPO / "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.json",
    REPO / "output/protocol_reverse/source_offsets/captcha_px561_extra_fields.json",
    REPO / "output/protocol_reverse/source_offsets/captcha_state_submit_fields.json",
]
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"
TARGETS = {"fyNOZTpPQF4=", "AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA==", "Ew9iCVZkZD4=", "KVkYX28zG2o="}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def static_map() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for path in STATIC_FILES:
        if not path.exists():
            continue
        doc = load_json(path)
        for rec in doc.get("records") or []:
            decoded = rec.get("decoded")
            if not decoded:
                continue
            out.setdefault(decoded, []).append(
                {
                    "file": str(path.resolve()),
                    "expr": rec.get("expr"),
                    "raw": rec.get("raw"),
                    "assignment": rec.get("assignment"),
                }
            )
    return out


def contiguous_segments(indexes: list[int]) -> list[dict[str, int]]:
    if not indexes:
        return []
    indexes = sorted(indexes)
    segments = []
    start = prev = indexes[0]
    for idx in indexes[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        segments.append({"start": start, "end": prev, "count": prev - start + 1})
        start = prev = idx
    segments.append({"start": start, "end": prev, "count": prev - start + 1})
    return segments


def main() -> int:
    doc = load_json(COMPARE)
    accepted = doc["acceptedReference"]
    accepted_keys = accepted["keys"]
    controls = doc["comparisons"]
    static = static_map()
    missing_sets = [set(row["missingComparedToAccepted"]) for row in controls]
    missing_all = set.intersection(*missing_sets) if missing_sets else set()
    key_rows = []
    for idx, key in enumerate(accepted_keys):
        in_all_controls_missing = key in missing_all
        in_any_control_missing = any(key in s for s in missing_sets)
        if not in_all_controls_missing and key not in TARGETS:
            continue
        key_rows.append(
            {
                "index": idx,
                "key": key,
                "target": key in TARGETS,
                "missingInAllControls": in_all_controls_missing,
                "missingInAnyControl": in_any_control_missing,
                "acceptedValue": accepted.get("targetValues", {}).get(key),
                "staticEvidence": static.get(key, []),
            }
        )
    missing_indexes = [row["index"] for row in key_rows if row["missingInAllControls"]]
    target_window = [
        row
        for row in key_rows
        if 70 <= row["index"] <= 80 or row["key"] in {"Ew9iCVZkZD4=", "KVkYX28zG2o="}
    ]
    result = {
        "purpose": "Use accepted PX561 key order and AEAx-only controls to bound the missing-key/TBR9/POW-answer injection window.",
        "sourceCompare": str(COMPARE.resolve()),
        "accepted": {
            "run": accepted["run"],
            "tfLine": accepted["tfLine"],
            "seq": accepted["request"].get("seq"),
            "fieldCount": accepted["fieldCount"],
        },
        "controlRuns": [row["run"] for row in controls],
        "missingInAllControlsCount": len(missing_all),
        "missingSegmentsInAcceptedOrder": contiguous_segments(missing_indexes),
        "keyRows": key_rows,
        "targetWindow": target_window,
        "checks": {
            "missingSetsIdenticalAcrossControls": all(s == missing_sets[0] for s in missing_sets[1:]) if missing_sets else False,
            "tbr9MissingInAllControls": "TBR9Ugl7emA=" in missing_all,
            "aeaxNotMissingInControls": "AEAxBkUsPjQ=" not in missing_all,
            "powKeyNotMissingButInvalidInControls": "OSkIb39DDA==" not in missing_all and doc["checks"].get("noControlsHavePowAnswer") is True,
            "hasTailMissingSegmentBeforeTbr9": any(seg["start"] <= 65 and seg["end"] >= 72 for seg in contiguous_segments(missing_indexes)),
        },
        "conclusion": (
            "Accepted PX561 has a shared missing-in-controls tail segment at indexes 65-72, then state/AEAx at 74-75, TBR9 at 76, and POW metadata/answer keys at 77-78. "
            "AEAx is present in controls, but TBR9 is absent and OSkIb39DDA is only a null key there, so the next producer boundary should focus on the transition from AEAx-only PX561 to the TBR9 plus valid POW-answer tail."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_missing_key_order_audit.json"
    out_md = OUT_DIR / "px561_missing_key_order_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# PX561 missing key order audit",
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Missing segments in accepted key order",
        "",
        "| start | end | count |",
        "|---:|---:|---:|",
    ]
    for seg in result["missingSegmentsInAcceptedOrder"]:
        lines.append(f"| {seg['start']} | {seg['end']} | {seg['count']} |")
    lines += [
        "",
        "## Target window",
        "",
        "| index | key | target | missing all controls | static evidence |",
        "|---:|---|---:|---:|---|",
    ]
    for row in result["targetWindow"]:
        evidence = "; ".join(item.get("assignment") or item.get("expr") or "" for item in row["staticEvidence"]) or "-"
        lines.append(f"| {row['index']} | `{row['key']}` | {row['target']} | {row['missingInAllControls']} | {evidence} |")
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
