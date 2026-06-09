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


def find_matches(value: Any, terms: list[str], path: str = "") -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            matches.extend(find_matches(child, terms, child_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            matches.extend(find_matches(child, terms, f"{path}[{idx}]"))
    elif isinstance(value, str):
        for term in terms:
            if term in value:
                matches.append({"path": path, "term": term, "value": value})
    else:
        text = str(value)
        for term in terms:
            if term in text:
                matches.append({"path": path, "term": term, "value": value})
    return matches


def extract(runtime_trace: Path, collector_decode: Path, terms: list[str]) -> dict[str, Any]:
    dec = load_decode_tool()
    rows = dec.read_jsonl(runtime_trace)
    timeline = dec.build_marker_timeline(collector_decode)
    request_results = []
    for row in rows:
        if row.get("kind") != "request":
            continue
        url = str(row.get("url") or "")
        if not url.endswith("/assets/js/bundle"):
            continue
        params = dec.parse_form(row.get("post_data") or "")
        marker = dec.marker_for_request(timeline, int(row["_line"]))
        if not params.get("payload") or not params.get("uuid"):
            request_results.append({
                "requestLine": row["_line"],
                "url": url,
                "seq": params.get("seq"),
                "ft": params.get("ft"),
                "uuid": params.get("uuid"),
                "payloadLen": len(params.get("payload", "")),
                "markerQi": marker["qi"],
                "marker": marker["marker"],
                "markerMatch": None,
                "jsonError": "missing payload or uuid",
                "jsonItemCount": None,
                "activitiesWithMatches": [],
            })
            continue
        try:
            decoded = dec.decode_payload(params.get("payload", ""), marker["marker"], params.get("uuid", ""))
        except Exception as exc:
            request_results.append({
                "requestLine": row["_line"],
                "url": url,
                "seq": params.get("seq"),
                "ft": params.get("ft"),
                "uuid": params.get("uuid"),
                "payloadLen": len(params.get("payload", "")),
                "markerQi": marker["qi"],
                "marker": marker["marker"],
                "markerMatch": None,
                "jsonError": f"decode failed: {exc}",
                "jsonItemCount": None,
                "activitiesWithMatches": [],
            })
            continue
        parsed = decoded.get("json")
        activities = parsed if isinstance(parsed, list) else []
        activity_results = []
        for idx, activity in enumerate(activities):
            matches = find_matches(activity, terms)
            if not matches:
                continue
            activity_results.append({
                "index": idx,
                "type": activity.get("t") if isinstance(activity, dict) else None,
                "matches": matches,
                "activity": activity,
            })
        request_results.append({
            "requestLine": row["_line"],
            "url": url,
            "seq": params.get("seq"),
            "ft": params.get("ft"),
            "uuid": params.get("uuid"),
            "payloadLen": len(params.get("payload", "")),
            "markerQi": marker["qi"],
            "marker": marker["marker"],
            "markerMatch": decoded.get("markerMatch"),
            "jsonError": decoded.get("jsonError"),
            "jsonItemCount": len(activities) if isinstance(parsed, list) else None,
            "activitiesWithMatches": activity_results,
        })
    return {
        "runtimeTrace": str(runtime_trace),
        "collectorDecode": str(collector_decode),
        "terms": terms,
        "requests": request_results,
    }


def base_name(path: Path) -> str:
    return path.name.removesuffix(".jsonl").removeprefix("runtime_trace_")


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["runtimeTrace"]))
    json_path = out_dir / f"bundle_activity_matches_{base}.json"
    md_path = out_dir / f"bundle_activity_matches_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Bundle activity matches: {base}",
        "",
        f"runtime={result['runtimeTrace']}",
        f"decode={result['collectorDecode']}",
        f"terms={','.join(result['terms'])}",
        "",
        "| req line | seq | markerMatch | items | activity index | activity type | match path | term | value preview |",
        "|---:|---:|---|---:|---:|---|---|---|---|",
    ]
    for req in result["requests"]:
        for activity in req["activitiesWithMatches"]:
            for match in activity["matches"]:
                value = str(match["value"]).replace("\n", "\\n")
                if len(value) > 160:
                    value = value[:157] + "..."
                lines.append(
                    f"| {req['requestLine']} | {req.get('seq') or ''} | {req.get('markerMatch')} | "
                    f"{req.get('jsonItemCount') or ''} | {activity['index']} | {activity.get('type') or ''} | "
                    f"{match['path']} | {match['term']} | `{value}` |"
                )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract activities from decoded HUMAN /assets/js/bundle payloads that contain target terms.")
    parser.add_argument("runtime_trace", type=Path)
    parser.add_argument("collector_decode", type=Path)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/bundle_activity_matches")
    args = parser.parse_args()
    terms = args.term or ["218e34c1", "50239", "1366f575"]
    result = extract(args.runtime_trace, args.collector_decode, terms)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
