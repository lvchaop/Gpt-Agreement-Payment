#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PRE_I = REPO / "output/protocol_reverse/source_offsets/tbr9_pre_i_visible_writes_audit.json"
ACTIVITY_UNIQUE = REPO / "output/protocol_reverse/source_offsets/tbr9_activity_uniqueness_audit.json"
BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

TARGET = "TBR9Ugl7emA="

YC_BASE_KEYS = [
    "VGBuahICYlE=",
    "KDRSPm1TWQg=",
    "W0shQR0nJHc=",
    "KVUTX285HW4=",
    "DFg2Eko5PiQ=",
    "JVEfW2A0G2A=",
    "S3sxMQ0YNQo=",
]

TF_COMMON_KEYS = [
    "RTE/ewNXNUA=",
    "O2sBIX4NDBQ=",
    "P28FJXoMCRI=",
    "YGwaZiUPFVQ=",
    "MkJICHQkQj8=",
    "AzN5eUVQckM=",
    "WQUjDxxjKjU=",
    "CXVzP0wWeQQ=",
    "GUVjT1wnbn4=",
    "NABOSnFiQ3o=",
    "SlpwEAw5eSc=",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)


def short(value: Any, limit: int = 160) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<len={len(value)}>"
    return value


def success_px561_d() -> OrderedDict[str, Any]:
    bundle = load_json(BUNDLE)
    req = next(r for r in bundle["requests"] if r.get("requestLine") == 308)
    match = next(item for item in req["activitiesWithMatches"] if item.get("type") == "PX561")
    return match["activity"]["d"]


def value_for_visible_write(row: dict[str, Any], final_d: OrderedDict[str, Any]) -> Any:
    key = row["decoded"]
    expr = row["valueExpr"]
    if key == TARGET:
        return True
    if key == "instantiating":
        return "instantiate"
    if key == "succeeded":
        return "succeeded"
    if key in final_d:
        return final_d[key]
    if expr == "os":
        return "PX12616-placeholder"
    if expr == "ws":
        return "PX12617-placeholder"
    return None


def emulate_yc(pre_i: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
    out: OrderedDict[str, Any] = OrderedDict()
    for key in YC_BASE_KEYS:
        out[key] = f"yc_base:{key}"
    for key, value in pre_i.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                out[nested_key] = nested_value
        else:
            out[key] = value
    return out


def emulate_ds(activity_type: str, d: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
    out = OrderedDict(d)
    out["HUlnQ1slanM="] = 0
    out["R3c9PQEXNg8="] = "qi_or_time_placeholder"
    return OrderedDict([("t", activity_type), ("d", out), ("ts", 1780948253000)])


def emulate_tf_entry(activity: OrderedDict[str, Any]) -> OrderedDict[str, Any]:
    out = OrderedDict(activity)
    d = OrderedDict(out["d"])
    for key in TF_COMMON_KEYS:
        if key == "SlpwEAw5eSc=":
            continue
        d[key] = f"tf_common:{key}"
    d["SlpwEAw5eSc="] = "tf_first_activity_common"
    out["d"] = d
    return out


def summarize_tbr(stage: str, d: OrderedDict[str, Any]) -> dict[str, Any]:
    keys = list(d)
    value = d.get(TARGET)
    idx = keys.index(TARGET) if TARGET in d else None
    return {
        "stage": stage,
        "present": TARGET in d,
        "index": idx,
        "valueType": type(value).__name__ if TARGET in d else None,
        "valueLen": len(value) if isinstance(value, str) else None,
        "value": short(value),
        "neighborKeys": keys[max(0, idx - 4): min(len(keys), idx + 5)] if idx is not None else [],
    }


def main() -> None:
    pre_i_audit = load_json(PRE_I)
    activity_unique = load_json(ACTIVITY_UNIQUE)
    final_d = success_px561_d()
    final_keys = list(final_d)

    pre_i_obj: OrderedDict[str, Any] = OrderedDict()
    source_rows = []
    for row in pre_i_audit["visiblePreIWrites"]:
        key = row["decoded"]
        value = value_for_visible_write(row, final_d)
        pre_i_obj[key] = value
        source_rows.append({
            "key": key,
            "valueExpr": row["valueExpr"],
            "emulatedValue": short(value),
            "emulatedType": type(value).__name__,
            "lineRef": row["lineRef"],
        })

    yc_out = emulate_yc(pre_i_obj)
    ds_item = emulate_ds("PX561", yc_out)
    tf_item = emulate_tf_entry(ds_item)
    serialized = json.dumps([tf_item], ensure_ascii=False, separators=(",", ":"))
    final_tbr_value = final_d[TARGET]

    summaries = [
        summarize_tbr("pre_i_visible_object", pre_i_obj),
        summarize_tbr("yc_output_emulated", yc_out),
        summarize_tbr("ds_queue_item_d_emulated", ds_item["d"]),
        summarize_tbr("tf_entry_activity_d_emulated", tf_item["d"]),
        summarize_tbr("final_success_px561", final_d),
    ]

    result = {
        "inputs": {
            "preI": str(PRE_I),
            "activityUniqueness": str(ACTIVITY_UNIQUE),
            "bundle": str(BUNDLE),
        },
        "sourceRows": source_rows,
        "staticSemanticsApplied": {
            "Yc": "main.beautified.js:2963-3009 creates base C, then copies primitive/null/array input fields by key and flattens only plain object values.",
            "ds": "main.beautified.js:3455-3468 adds HUlnQ1slanM=/R3c9PQEXNg8= and queues {t,d,ts}; no TBR producer.",
            "tf": "main.beautified.js:4807-4825 adds fixed common keys to activity.d; inspected keys do not include TBR9Ugl7emA=.",
            "Vs": "main.beautified.js:3560-3598 clones the activity array, serializes with ut(a), encodes, and marker-inserts; no semantic field producer is visible.",
        },
        "tbrSummaries": summaries,
        "serializedChecks": {
            "serializedHasTargetKey": f'"{TARGET}"' in serialized,
            "serializedHasFinalTbrValue": final_tbr_value in serialized,
            "serializedHasBooleanTbr": f'"{TARGET}":true' in serialized,
            "serializedSnippetAroundTbr": short(serialized[max(0, serialized.find(f'"{TARGET}"') - 80): serialized.find(f'"{TARGET}"') + 220]),
        },
        "finalSuccess": {
            "activityLine": 308,
            "activityIndex": activity_unique["targetHits"][0]["index"],
            "activityType": activity_unique["targetHits"][0]["type"],
            "tbrIndex": final_keys.index(TARGET),
            "tbrValueLen": len(final_tbr_value),
            "tbrValue": final_tbr_value,
        },
        "checks": {
            "preIHasBooleanTbr": pre_i_obj.get(TARGET) is True,
            "ycPreservesBooleanTbr": yc_out.get(TARGET) is True,
            "tfPreservesBooleanTbr": tf_item["d"].get(TARGET) is True,
            "finalHasStringTbr": isinstance(final_tbr_value, str) and len(final_tbr_value) == 127,
            "emulatedOrderHasTbrBeforeAeax": list(tf_item["d"]).index(TARGET) < list(tf_item["d"]).index("AEAxBkUsPjQ="),
            "finalOrderHasTbrAfterAeax": final_keys.index(TARGET) > final_keys.index("AEAxBkUsPjQ="),
        },
        "findings": [
            "Using the visible pre-i(PX561,r) write set and preserving all known success values except the direct TBR9 source, TBR9 remains boolean true through the emulated Yc, ds queue item, and tf entry stages.",
            "The emulated serialized activity contains \"TBR9Ugl7emA=\":true and does not contain the final 127-byte TBR9 value.",
            "The emulated key order keeps TBR9Ugl7emA= before AEAxBkUsPjQ=, while the final success PX561 places AEAxBkUsPjQ= before TBR9Ugl7emA=.",
            "Static Yc/ds/tf/Vs semantics visible in main.beautified.js do not provide a semantic TBR9 producer over this minimal object.",
            "Therefore the final TBR9 still requires evidence for a runtime non-visible mutation before Yc, a computed insertion/overwrite before tf/Vs serialization, or a still-unproven serializer/decode interpretation layer.",
        ],
        "conclusion": "The exact visible pre-i write set plus visible main-side Yc/ds/tf semantics cannot produce the final 127-byte TBR9. This narrows the remaining P0 to non-visible runtime mutation, computed main-side insertion/overwrite, or serializer/decode interpretation evidence.",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "tbr9_minimal_yc_tf_experiment.json"
    md_path = OUT_DIR / "tbr9_minimal_yc_tf_experiment.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TBR9 minimal Yc/tf experiment",
        "",
        "## Static semantics applied",
        "",
    ]
    for name, text in result["staticSemanticsApplied"].items():
        lines.append(f"- {name}: {text}")
    lines += [
        "",
        "## TBR summaries",
        "",
        "| stage | present | index | type | len | value |",
        "|---|---:|---:|---|---:|---|",
    ]
    for row in summaries:
        lines.append(
            f"| `{row['stage']}` | `{row['present']}` | `{row['index']}` | "
            f"`{row['valueType']}` | `{row['valueLen']}` | `{row['value']}` |"
        )
    lines += [
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Serialized checks",
        "",
    ]
    for key, value in result["serializedChecks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Findings",
        "",
    ]
    for finding in result["findings"]:
        lines.append(f"- {finding}")
    lines += ["", "## Conclusion", "", result["conclusion"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
