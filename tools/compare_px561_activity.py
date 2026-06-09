#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"


def load_decode_tool():
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_px561_from_tf(js_trace: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line_no, line in enumerate(js_trace.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") != "hsprotect.main.tf.payload":
            continue
        data = row.get("data") or {}
        activities = data.get("activities") or []
        for idx, activity in enumerate(activities):
            if isinstance(activity, dict) and activity.get("t") == "PX561":
                out.append({
                    "source": str(js_trace),
                    "sourceKind": "tf.payload",
                    "line": line_no,
                    "activityIndex": idx,
                    "href": row.get("href"),
                    "activity": activity,
                })
    return out


def extract_px561_from_bundle(runtime_trace: Path, collector_decode: Path) -> list[dict[str, Any]]:
    dec = load_decode_tool()
    rows = dec.read_jsonl(runtime_trace)
    timeline = dec.build_marker_timeline(collector_decode)
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("kind") != "request" or not str(row.get("url") or "").endswith("/assets/js/bundle"):
            continue
        params = dec.parse_form(row.get("post_data") or "")
        if not params.get("payload") or not params.get("uuid"):
            continue
        marker = dec.marker_for_request(timeline, int(row["_line"]))
        try:
            decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])
        except Exception:
            continue
        parsed = decoded.get("json")
        if not isinstance(parsed, list):
            continue
        for idx, activity in enumerate(parsed):
            if isinstance(activity, dict) and activity.get("t") == "PX561":
                out.append({
                    "source": str(runtime_trace),
                    "sourceKind": "bundle.payload",
                    "line": row["_line"],
                    "activityIndex": idx,
                    "seq": params.get("seq"),
                    "markerQi": marker["qi"],
                    "activity": activity,
                })
    return out


def summarize_activity(row: dict[str, Any]) -> dict[str, Any]:
    d = row["activity"].get("d") or {}
    return {
        "source": row["source"],
        "sourceKind": row["sourceKind"],
        "line": row["line"],
        "seq": row.get("seq"),
        "href": row.get("href"),
        "activityIndex": row["activityIndex"],
        "fieldCount": len(d),
        "state": d.get("fyNOZTpPQF4="),
        "powField": d.get("OSkIb39DDA=="),
        "pointerDown": d.get("FwtmDVFqaD0="),
        "pointerUp": d.get("cRFAFzdwTyM="),
        "pointerUpTime": d.get("WiZrIB9LbBU="),
        "pointerEventCount": len(d.get("DzN+dUlTekE=") or []),
        "motion150Count": len(d.get("GUloT18mZ3U=") or []),
        "motion600Count": len(d.get("JnpXfGMUUUc=") or []),
        "keys": sorted(d.keys()),
        "activity": row["activity"],
    }


def compare(success: dict[str, Any], others: list[dict[str, Any]]) -> dict[str, Any]:
    success_keys = set(success["keys"])
    rows = []
    for item in others:
        keys = set(item["keys"])
        rows.append({
            "source": item["source"],
            "sourceKind": item["sourceKind"],
            "line": item["line"],
            "fieldCount": item["fieldCount"],
            "state": item["state"],
            "hasPowField": bool(item.get("powField")),
            "missingComparedToSuccess": sorted(success_keys - keys),
            "extraComparedToSuccess": sorted(keys - success_keys),
            "pointerEventCount": item["pointerEventCount"],
            "motion150Count": item["motion150Count"],
            "motion600Count": item["motion600Count"],
        })
    return {"success": success, "comparisons": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare PX561 activity fields between success bundle payload and tf.payload samples.")
    parser.add_argument("--success-runtime", type=Path, required=True)
    parser.add_argument("--success-decode", type=Path, required=True)
    parser.add_argument("--sample-js", type=Path, action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/px561_compare")
    args = parser.parse_args()

    success_rows = [summarize_activity(x) for x in extract_px561_from_bundle(args.success_runtime, args.success_decode)]
    if not success_rows:
        raise SystemExit("no success PX561 activity found")
    success = success_rows[-1]
    samples: list[dict[str, Any]] = []
    for js_trace in args.sample_js:
        samples.extend(summarize_activity(x) for x in extract_px561_from_tf(js_trace))
    result = compare(success, samples)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "px561_compare_success_vs_tf_samples.json"
    md_path = args.out_dir / "px561_compare_success_vs_tf_samples.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# PX561 activity compare: success vs tf samples",
        "",
        f"success={success['source']} line={success['line']} seq={success.get('seq')}",
        f"successFieldCount={success['fieldCount']}",
        f"successPowField={success.get('powField')}",
        "",
        "| source | line | fields | state | hasPow | pointerEvents | motion150 | motion600 | missing key count |",
        "|---|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in result["comparisons"]:
        lines.append(
            f"| {row['source']} | {row['line']} | {row['fieldCount']} | {row.get('state') or ''} | "
            f"{row['hasPowField']} | {row['pointerEventCount']} | {row['motion150Count']} | {row['motion600Count']} | "
            f"{len(row['missingComparedToSuccess'])} |"
        )
    lines.append("")
    lines.append("## missing keys compared to success")
    for row in result["comparisons"]:
        lines.append(f"### {row['source']}:{row['line']}")
        for key in row["missingComparedToSuccess"]:
            lines.append(f"- {key}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path), "samples": len(samples)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
