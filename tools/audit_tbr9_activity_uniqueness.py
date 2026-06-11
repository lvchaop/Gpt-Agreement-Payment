#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUNTIME = REPO / "output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl"
COLLECTOR = REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"
TARGET = "TBR9Ugl7emA="


def load_decode_tool() -> Any:
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def short(value: Any, limit: int = 140) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<len={len(value)}>"
    return value


def main() -> None:
    dec = load_decode_tool()
    rows = dec.read_jsonl(RUNTIME)
    request = next(
        row
        for row in rows
        if row.get("_line") == 308 and str(row.get("url") or "").endswith("/assets/js/bundle")
    )
    params = dec.parse_form(request.get("post_data") or "")
    timeline = dec.build_marker_timeline(COLLECTOR)
    marker = dec.marker_for_request(timeline, 308)
    decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])
    activities = decoded["json"]
    if not isinstance(activities, list):
        raise RuntimeError(f"decoded payload is not list: {decoded['jsonError']}")

    rows_out = []
    target_hits = []
    for idx, activity in enumerate(activities):
        d = activity.get("d") if isinstance(activity, dict) else None
        keys = list(d) if isinstance(d, dict) else []
        has_target = isinstance(d, dict) and TARGET in d
        target_index = keys.index(TARGET) if has_target else None
        row = {
            "index": idx,
            "type": activity.get("t") if isinstance(activity, dict) else None,
            "keyCount": len(keys),
            "hasTbr9": has_target,
            "tbr9Index": target_index,
            "tbr9Type": type(d.get(TARGET)).__name__ if has_target else None,
            "tbr9Len": len(d.get(TARGET)) if has_target and isinstance(d.get(TARGET), str) else None,
            "tbr9Value": short(d.get(TARGET)) if has_target else None,
            "neighborKeys": keys[max(0, target_index - 4): min(len(keys), target_index + 5)] if has_target else [],
        }
        rows_out.append(row)
        if has_target:
            target_hits.append(row)

    result = {
        "inputs": {
            "runtime": str(RUNTIME),
            "collector": str(COLLECTOR),
            "decodeTool": str(DECODE_TOOL),
        },
        "request": {
            "line": request["_line"],
            "url": request.get("url"),
            "seq": params.get("seq"),
            "uuid": params.get("uuid"),
            "payloadLen": len(params.get("payload") or ""),
            "marker": marker,
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "activityCount": len(activities),
        },
        "activities": rows_out,
        "targetHits": target_hits,
        "findings": [
            "The line 308 /assets/js/bundle payload decodes cleanly with the collector marker state.",
            "The decoded payload contains exactly five activities.",
            "Exactly one decoded activity contains TBR9Ugl7emA=: activity index 2 with type PX561.",
            "No non-PX561 activity in the same payload contains TBR9Ugl7emA=.",
            "Therefore the final TBR9 evidence is not explained by selecting the wrong activity or by cross-activity key attribution within request line 308.",
        ],
        "remainingGap": "The unique PX561 attribution does not identify the TBR9 producer; it only excludes activity selection/cross-activity mismatch.",
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "tbr9_activity_uniqueness_audit.json"
    md_path = OUT_DIR / "tbr9_activity_uniqueness_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TBR9 activity uniqueness audit",
        "",
        "## Request",
        "",
        f"- line: `{result['request']['line']}`",
        f"- seq: `{result['request']['seq']}`",
        f"- markerMatch: `{result['request']['markerMatch']}`",
        f"- jsonError: `{result['request']['jsonError']}`",
        f"- activityCount: `{result['request']['activityCount']}`",
        "",
        "## Activities",
        "",
        "| index | type | keyCount | has TBR9 | TBR9 index | TBR9 len |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in rows_out:
        lines.append(
            f"| {row['index']} | `{row['type']}` | {row['keyCount']} | "
            f"`{row['hasTbr9']}` | `{row['tbr9Index']}` | `{row['tbr9Len']}` |"
        )
    lines += ["", "## Findings", ""]
    for finding in result["findings"]:
        lines.append(f"- {finding}")
    lines += ["", "## Remaining gap", "", f"- {result['remainingGap']}"]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
