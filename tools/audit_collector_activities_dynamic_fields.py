#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
HEX_RE = re.compile(r"^[0-9a-f]{8,}$", re.I)
BASE64ISH_RE = re.compile(r"^[A-Za-z0-9+/=_-]{32,}$")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def base_name(path: Path) -> str:
    return path.name.removesuffix(".jsonl").removeprefix("js_internal_trace_")


def flatten(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        out: list[tuple[str, Any]] = []
        for k, v in value.items():
            out.extend(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(value, list):
        out = []
        for idx, v in enumerate(value):
            out.extend(flatten(v, f"{prefix}[{idx}]"))
        return out
    return [(prefix, value)]


def classify_value(value: Any, live_state: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    if isinstance(value, bool) or value is None:
        return labels
    if isinstance(value, int):
        if 1_600_000_000_000 <= value <= 2_000_000_000_000:
            labels.append("epoch_ms")
        elif value > 10_000:
            labels.append("large_number")
        return labels
    if not isinstance(value, str):
        return labels
    if UUID_RE.match(value):
        labels.append("uuid")
    if HEX_RE.match(value):
        labels.append("hex")
    if BASE64ISH_RE.match(value):
        labels.append("base64ish")
    if value.startswith("http://") or value.startswith("https://"):
        labels.append("url")
    if "session_id=" in value:
        labels.append("contains_session_id")
    if "captcha.hsprotect.net" in value:
        labels.append("captcha_url")
    if "client.hsprotect.net" in value:
        labels.append("client_js_url")
    for key, state_value in live_state.items():
        if not isinstance(state_value, str) or not state_value:
            continue
        if value == state_value:
            labels.append(f"equals_live_{key}")
        elif state_value in value:
            labels.append(f"contains_live_{key}")
    return labels


def extract_live_state(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    doc = read_json(path)
    body_override = ((doc.get("probe") or {}).get("source") or {}).get("bodyOverrideSummary") or {}
    state = body_override.get("liveState")
    if not state:
        state = doc.get("liveState") or {}
    decoded = doc.get("decoded") or {}
    if decoded.get("parts"):
        state = dict(state)
        for part in decoded.get("parts") or []:
            fields = str(part).split("|")
            key, args = fields[0], fields[1:]
            if key == "IIoIIo" and args:
                state["sidBase"] = args[0]
            elif key == "oIIoIoII" and args:
                state["Jo"] = args[0]
            elif key == "IooIoo" and args:
                state["vid"] = args[0]
            elif key == "oIIooIIo" and args:
                state["cts"] = args[0]
            elif key == "IoIIII" and args:
                state["cs"] = args[0]
    return {k: v for k, v in state.items() if isinstance(v, str)}


def audit(trace_path: Path, request_build_path: Path, live_state_path: Path | None) -> dict[str, Any]:
    js_rows = read_jsonl(trace_path)
    request_build = read_json(request_build_path)
    tf_by_line = {int(r.get("_line") or 0): r for r in js_rows if r.get("kind") == "hsprotect.main.tf.payload"}
    live_state = extract_live_state(live_state_path)
    rows: list[dict[str, Any]] = []
    for req in request_build.get("rows") or []:
        tf_line = int(req.get("tfLine") or 0)
        tf = tf_by_line.get(tf_line)
        data = (tf or {}).get("data") or {}
        activities = data.get("activities") or []
        field_rows: list[dict[str, Any]] = []
        for activity_index, activity in enumerate(activities):
            for path, value in flatten(activity):
                labels = classify_value(value, live_state)
                if labels:
                    field_rows.append(
                        {
                            "activityIndex": activity_index,
                            "path": path,
                            "value": value,
                            "labels": labels,
                        }
                    )
        rows.append(
            {
                "requestIndex": req.get("index"),
                "requestLine": req.get("requestLine"),
                "tfLine": tf_line,
                "activityCount": len(activities),
                "meta": data.get("meta"),
                "dynamicFieldCount": len(field_rows),
                "dynamicFields": field_rows,
            }
        )
    return {
        "tracePath": str(trace_path),
        "requestBuildPath": str(request_build_path),
        "liveStatePath": str(live_state_path) if live_state_path else None,
        "liveState": live_state,
        "rows": rows,
        "summary": {
            "requestCount": len(rows),
            "dynamicFieldCount": sum(r["dynamicFieldCount"] for r in rows),
            "idx1DynamicFields": next((r["dynamicFieldCount"] for r in rows if r["requestIndex"] == 1), None),
        },
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["tracePath"]))
    json_path = out_dir / f"collector_activity_dynamic_audit_{base}.json"
    md_path = out_dir / f"collector_activity_dynamic_audit_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# collector activity dynamic audit: {base}",
        "",
        f"trace={result['tracePath']}",
        f"requestBuild={result['requestBuildPath']}",
        f"liveState={result.get('liveStatePath') or ''}",
        "",
        "## summary",
    ]
    for k, v in result["summary"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## live state")
    for k, v in result.get("liveState", {}).items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")
    for row in result["rows"]:
        lines.append(f"## request idx={row['requestIndex']} tfLine={row['tfLine']} activityCount={row['activityCount']}")
        lines.append(f"- dynamicFieldCount: {row['dynamicFieldCount']}")
        lines.append(f"- meta: `{json.dumps(row.get('meta'), ensure_ascii=False)}`")
        for field in row["dynamicFields"][:200]:
            value = field["value"]
            preview = json.dumps(value, ensure_ascii=False)
            if len(preview) > 500:
                preview = preview[:500] + "...<truncated>"
            lines.append(f"- act={field['activityIndex']} path=`{field['path']}` labels={','.join(field['labels'])} value={preview}")
        if len(row["dynamicFields"]) > 200:
            lines.append(f"- ... truncated {len(row['dynamicFields']) - 200} fields in md; full data in json")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit dynamic-looking fields inside HUMAN collector tf activities.")
    parser.add_argument("trace", type=Path)
    parser.add_argument("request_build", type=Path)
    parser.add_argument("--live-state", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_activity_dynamic")
    args = parser.parse_args()
    result = audit(args.trace, args.request_build, args.live_state)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
