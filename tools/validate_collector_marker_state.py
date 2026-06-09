#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
FALLBACK_QI = "1604064986000"


def marker_from_qi(qi: str | None) -> str:
    value = str(qi or FALLBACK_QI)
    b64 = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return "".join(chr(ord(ch) ^ 10) for ch in b64)


def split_handler(part: str) -> tuple[str, list[str]]:
    fields = str(part).split("|")
    return fields[0] if fields else "", fields[1:]


def apply_marker_state(state: dict[str, Any], entry: dict[str, Any]) -> None:
    line_no = int(entry.get("lineNo") or 0)
    for part_index, part in enumerate(entry.get("parts", [])):
        key, args = split_handler(str(part))
        if key == "oIIoIoII" and args:
            state["Jo"] = args[0]
            state["JoSource"] = {
                "collectorLine": line_no,
                "partIndex": part_index,
                "handler": key,
                "raw": str(part),
            }


def validate(request_build_path: Path, collector_decode_path: Path) -> dict[str, Any]:
    request_build = json.loads(request_build_path.read_text(encoding="utf-8"))
    collector_decode = json.loads(collector_decode_path.read_text(encoding="utf-8"))
    entries = sorted(collector_decode.get("decodedEntries", []), key=lambda e: int(e.get("lineNo") or 0))
    requests = sorted(request_build.get("rows", []), key=lambda r: int(r.get("requestLine") or 0))
    state: dict[str, Any] = {}
    entry_pos = 0
    rows: list[dict[str, Any]] = []
    for req in requests:
        request_line = int(req.get("requestLine") or 0)
        applied: list[int] = []
        while entry_pos < len(entries) and int(entries[entry_pos].get("lineNo") or 0) < request_line:
            entry = entries[entry_pos]
            apply_marker_state(state, entry)
            applied.append(int(entry.get("lineNo") or 0))
            entry_pos += 1
        qi = state.get("Jo") or FALLBACK_QI
        expected = marker_from_qi(qi)
        observed = req.get("marker")
        rows.append(
            {
                "index": req.get("index"),
                "requestLine": request_line,
                "tfLine": req.get("tfLine"),
                "appliedCollectorLines": applied,
                "qi": qi,
                "qiSource": state.get("JoSource") or {"static": "fallback Xs(118)", "value": FALLBACK_QI},
                "expectedMarker": expected,
                "observedMarker": observed,
                "observedMarkerSource": req.get("markerSource"),
                "match": expected == observed,
            }
        )
    return {
        "requestBuildPath": str(request_build_path),
        "collectorDecodePath": str(collector_decode_path),
        "rows": rows,
        "summary": {
            "requestCount": len(rows),
            "matches": sum(1 for row in rows if row["match"]),
            "mismatches": sum(1 for row in rows if not row["match"]),
            "fallbackCount": sum(1 for row in rows if (row.get("qiSource") or {}).get("static") == "fallback Xs(118)"),
        },
        "evidence": [
            "main.beautified.js:3566 Vs marker path uses ne(J(Qi() || Xs(118)), 10)",
            "main.beautified.js:2675-2677 Qi() returns Jo",
            "main.beautified.js:4486-4488 handler oIIoIoII maps to Yl",
            "main.beautified.js:4701-4702 Yl(t) sets Jo=t and zo=floor(parseInt(Jo)/1000)",
        ],
    }


def base_name(path: Path) -> str:
    return path.name.removesuffix(".json").replace("collector_request_build_", "")


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["requestBuildPath"]))
    json_path = out_dir / f"collector_marker_state_validation_{base}.json"
    md_path = out_dir / f"collector_marker_state_validation_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines: list[str] = []
    lines.append(f"# collector marker state validation: {base}")
    lines.append("")
    lines.append(f"requestBuild={result['requestBuildPath']}")
    lines.append(f"collectorDecode={result['collectorDecodePath']}")
    lines.append("")
    lines.append("## summary")
    for key, value in result["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("| idx | req line | tf line | applied collector lines | qi | observed source | match | marker |")
    lines.append("|---:|---:|---:|---|---|---|---|---|")
    for row in result["rows"]:
        lines.append(
            f"| {row['index']} | {row['requestLine']} | {row.get('tfLine') or ''} | "
            f"{','.join(map(str, row['appliedCollectorLines']))} | {row['qi']} | "
            f"{row.get('observedMarkerSource') or ''} | {row['match']} | `{row['expectedMarker']}` |"
        )
    lines.append("")
    lines.append("## static evidence")
    for item in result["evidence"]:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## boundary")
    lines.append("- This validates marker generation from decoded collector state and static JS for existing samples.")
    lines.append("- It does not prove a fresh pure-protocol collector request will be accepted by the remote service.")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate collector payload marker from prior decoded Jo/Qi state.")
    parser.add_argument("request_build_json", type=Path)
    parser.add_argument("collector_decode_json", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_marker_state")
    args = parser.parse_args()
    result = validate(args.request_build_json, args.collector_decode_json)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"jsonPath": str(json_path), "mdPath": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
