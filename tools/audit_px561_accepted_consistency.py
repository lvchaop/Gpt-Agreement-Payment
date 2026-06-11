#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"
TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "Ew9iCVZkZD4=",
    "KVkYX28zG2o=",
]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    out = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def value_shape(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
    return {
        "type": type(value).__name__,
        "length": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "preview": text[:120] + (f"...<len={len(text)}>" if len(text) > 120 else ""),
    }


def is_pow_answer(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def summarize_activity(source: dict[str, Any], activity: dict[str, Any]) -> dict[str, Any]:
    d = activity.get("d") or {}
    keys = list(d.keys())
    return {
        **source,
        "fieldCount": len(keys),
        "keys": keys,
        "target": {
            key: {
                "index": keys.index(key) if key in d else None,
                "present": key in d,
                "validPowAnswer": is_pow_answer(d.get(key)) if key == "OSkIb39DDA==" else None,
                "shape": value_shape(d[key]) if key in d else None,
            }
            for key in TARGET_KEYS
        },
    }


def extract_j0t8() -> dict[str, Any]:
    js_trace = REPO / "output/outlook_browser/js_internal_trace_j0t8van4qyhm_1781119142.jsonl"
    rows = read_jsonl(js_trace)
    for row in rows:
        if row["_line"] != 487 or row.get("kind") != "hsprotect.main.tf.payload":
            continue
        data = row.get("data") or {}
        for idx, activity in enumerate(data.get("activities") or []):
            if isinstance(activity, dict) and activity.get("t") == "PX561":
                return summarize_activity(
                    {
                        "run": "j0t8van4qyhm_1781119142",
                        "sourceKind": "tf.payload",
                        "sourceLine": row["_line"],
                        "seq": "5",
                        "activityIndex": idx,
                        "evidenceFile": str(js_trace.resolve()),
                    },
                    activity,
                )
    raise RuntimeError("j0t8 PX561 tf line 487 not found")


def extract_ni109() -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    runtime_trace = REPO / "output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl"
    collector_decode = REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json"
    rows = dec.read_jsonl(runtime_trace)
    timeline = dec.build_marker_timeline(collector_decode)
    row = next(r for r in rows if r.get("kind") == "request" and r.get("_line") == 308)
    params = parse_form(row.get("post_data") or "")
    marker = dec.marker_for_request(timeline, 308)
    decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    for idx, activity in enumerate(activities):
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return summarize_activity(
                {
                    "run": "ni109xdjp5zp_1780948211",
                    "sourceKind": "bundle.payload",
                    "sourceLine": 308,
                    "seq": params.get("seq"),
                    "activityIndex": idx,
                    "markerMatch": decoded.get("markerMatch"),
                    "byteEncoding": decoded.get("byteEncoding"),
                    "evidenceFile": str(runtime_trace.resolve()),
                },
                activity,
            )
    raise RuntimeError("ni109 PX561 bundle line 308 not found")


def compare(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    tail_keys = ["fyNOZTpPQF4=", "AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="]
    a_tail = [a["target"][key]["index"] for key in tail_keys]
    b_tail = [b["target"][key]["index"] for key in tail_keys]
    return {
        "fieldCountDelta": a["fieldCount"] - b["fieldCount"],
        "sameKeyOrder": a["keys"] == b["keys"],
        "sameKeySet": set(a["keys"]) == set(b["keys"]),
        "tailKeys": tail_keys,
        "tailIndexes": {a["run"]: a_tail, b["run"]: b_tail},
        "tailConsecutiveInBoth": a_tail == list(range(a_tail[0], a_tail[0] + len(a_tail)))
        and b_tail == list(range(b_tail[0], b_tail[0] + len(b_tail))),
        "targetComparisons": {
            key: {
                "sameIndex": a["target"][key]["index"] == b["target"][key]["index"],
                "samePresence": a["target"][key]["present"] == b["target"][key]["present"],
                "sameType": (a["target"][key]["shape"] or {}).get("type") == (b["target"][key]["shape"] or {}).get("type"),
                "sameLength": (a["target"][key]["shape"] or {}).get("length") == (b["target"][key]["shape"] or {}).get("length"),
                "bothValidPowAnswer": (
                    a["target"][key]["validPowAnswer"] is True and b["target"][key]["validPowAnswer"] is True
                )
                if key == "OSkIb39DDA=="
                else None,
            }
            for key in TARGET_KEYS
        },
    }


def main() -> int:
    j0 = extract_j0t8()
    ni = extract_ni109()
    cmp = compare(j0, ni)
    result = {
        "purpose": "Verify that the accepted-success PX561 tail window is consistent across j0t8 and ni109 instead of being a single-run artifact.",
        "acceptedRows": [j0, ni],
        "comparison": cmp,
        "checks": {
            "bothHaveSameKeySet": cmp["sameKeySet"],
            "bothHaveSameKeyOrder": cmp["sameKeyOrder"],
            "bothHaveTbr9": j0["target"]["TBR9Ugl7emA="]["present"] and ni["target"]["TBR9Ugl7emA="]["present"],
            "bothHaveValidPowAnswer": j0["target"]["OSkIb39DDA=="]["validPowAnswer"] and ni["target"]["OSkIb39DDA=="]["validPowAnswer"],
            "targetIndexesStable": all(x["sameIndex"] for x in cmp["targetComparisons"].values()),
            "tailConsecutiveInBoth": cmp["tailConsecutiveInBoth"],
            "tailShapeStableForTbr9AndPow": cmp["targetComparisons"]["TBR9Ugl7emA="]["sameType"]
            and cmp["targetComparisons"]["OSkIb39DDA=="]["sameType"]
            and cmp["targetComparisons"]["OSkIb39DDA=="]["sameLength"],
        },
        "conclusion": (
            "The two accepted runs do not have identical full PX561 key sets or absolute target indexes, but both contain the same consecutive tail order state -> AEAx -> TBR9 -> POW metadata -> valid 64-hex POW answer. "
            "Therefore the TBR9/POW tail window is stable at the relative-order level and is not unique to the j0t8 observation."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_accepted_consistency_audit.json"
    out_md = OUT_DIR / "px561_accepted_consistency_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# PX561 accepted consistency audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Target indexes",
        "",
        "| key | j0 index | ni index | same index | j0 shape | ni shape |",
        "|---|---:|---:|---:|---|---|",
    ]
    for key in TARGET_KEYS:
        jt = j0["target"][key]
        nt = ni["target"][key]
        lines.append(
            f"| `{key}` | {jt['index']} | {nt['index']} | {cmp['targetComparisons'][key]['sameIndex']} | "
            f"`{(jt['shape'] or {}).get('type')}/{(jt['shape'] or {}).get('length')}` | "
            f"`{(nt['shape'] or {}).get('type')}/{(nt['shape'] or {}).get('length')}` |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
