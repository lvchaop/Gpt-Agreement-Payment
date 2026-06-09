#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def parse_nested_message(data: dict[str, Any]) -> Any:
    payload = data.get("data")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload
    return payload


def base_name(path: Path) -> str:
    return path.name.removesuffix(".jsonl").removeprefix("js_internal_trace_")


def decode_path_for(trace: Path) -> Path:
    return REPO / "output/protocol_reverse/collector_decode" / f"collector_decode_{base_name(trace)}.json"


def collect_decoded_cookie_events(decode_path: Path) -> list[dict[str, Any]]:
    if not decode_path.exists():
        return []
    doc = json.loads(decode_path.read_text(encoding="utf-8"))
    events: list[dict[str, Any]] = []
    for entry in doc.get("decodedEntries", []):
        for idx, part in enumerate(entry.get("parts", [])):
            fields = str(part).split("|")
            key = fields[0] if fields else ""
            event: dict[str, Any] | None = None
            if key == "IoooII" and len(fields) >= 4:
                event = {
                    "source": "collector_decoded",
                    "collectorLine": entry.get("lineNo"),
                    "partIndex": idx,
                    "handler": key,
                    "name": fields[1],
                    "ttl": fields[2],
                    "value": fields[3],
                    "raw": part,
                }
            elif key == "oIIoIIoo" and len(fields) >= 4:
                event = {
                    "source": "collector_decoded",
                    "collectorLine": entry.get("lineNo"),
                    "partIndex": idx,
                    "handler": key,
                    "name": fields[1],
                    "ttl": fields[2],
                    "value": fields[3],
                    "raw": part,
                }
            elif key == "IooIoo" and len(fields) >= 2:
                event = {
                    "source": "collector_decoded",
                    "collectorLine": entry.get("lineNo"),
                    "partIndex": idx,
                    "handler": key,
                    "name": "_pxvid",
                    "ttl": fields[2] if len(fields) > 2 else None,
                    "value": fields[1],
                    "raw": part,
                }
            elif key == "IIooII" and len(fields) >= 4:
                event = {
                    "source": "collector_decoded",
                    "collectorLine": entry.get("lineNo"),
                    "partIndex": idx,
                    "handler": key,
                    "name": fields[1],
                    "ttl": fields[2],
                    "value": fields[3],
                    "raw": part,
                }
            elif key == "oIIoIooo":
                event = {
                    "source": "collector_decoded",
                    "collectorLine": entry.get("lineNo"),
                    "partIndex": idx,
                    "handler": key,
                    "name": "challenge_success",
                    "value": "|".join(fields[1:]),
                    "raw": part,
                }
            if event:
                events.append(event)
    return events


def collect_parent_cookie_messages(trace: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in read_jsonl(trace):
        if row.get("kind") != "window.message.recv":
            continue
        msg = parse_nested_message(row.get("data") or {})
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "cookie":
            events.append(
                {
                    "source": "parent_postmessage",
                    "line": row["_line"],
                    "wall_t": row.get("wall_t"),
                    "perf_t": row.get("perf_t"),
                    "eventOrigin": (row.get("data") or {}).get("eventOrigin"),
                    "name": msg.get("name"),
                    "value": msg.get("value"),
                    "expires": msg.get("expires"),
                    "raw": msg,
                }
            )
        elif msg.get("type") == "succeeded":
            events.append(
                {
                    "source": "parent_postmessage",
                    "line": row["_line"],
                    "wall_t": row.get("wall_t"),
                    "perf_t": row.get("perf_t"),
                    "eventOrigin": (row.get("data") or {}).get("eventOrigin"),
                    "name": "challenge_success",
                    "value": "succeeded",
                    "raw": msg,
                }
            )
    return events


def correlate(decoded: list[dict[str, Any]], parent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    used: set[int] = set()
    for de in decoded:
        if de.get("name") not in {"_px3", "_pxde", "_pxvid", "challenge_success"}:
            continue
        match_index = None
        for idx, pe in enumerate(parent):
            if idx in used:
                continue
            if pe.get("name") != de.get("name"):
                continue
            if de.get("name") == "challenge_success" or pe.get("value") == de.get("value"):
                match_index = idx
                break
        if match_index is not None:
            used.add(match_index)
            pe = parent[match_index]
            pairs.append(
                {
                    "name": de.get("name"),
                    "collectorLine": de.get("collectorLine"),
                    "partIndex": de.get("partIndex"),
                    "parentLine": pe.get("line"),
                    "valueMatch": de.get("name") == "challenge_success" or pe.get("value") == de.get("value"),
                    "handler": de.get("handler"),
                }
            )
    return pairs


def analyze(trace: Path) -> dict[str, Any]:
    decode_path = decode_path_for(trace)
    decoded = collect_decoded_cookie_events(decode_path)
    parent = collect_parent_cookie_messages(trace)
    pairs = correlate(decoded, parent)
    return {
        "trace": str(trace),
        "decodePath": str(decode_path),
        "counts": {
            "decodedCookieOrSuccessEvents": len(decoded),
            "parentCookieOrSuccessMessages": len(parent),
            "correlatedEvents": len(pairs),
        },
        "decodedEvents": decoded,
        "parentMessages": parent,
        "correlations": pairs,
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["trace"]))
    json_path = out_dir / f"cookie_timeline_{base}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append(f"# HUMAN cookie timeline: {base}")
    lines.append("")
    lines.append(f"trace={result['trace']}")
    lines.append(f"decodePath={result['decodePath']}")
    lines.append("")
    lines.append("## counts")
    for key, value in result["counts"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## correlations")
    lines.append("| name | collector line | part index | parent line | value match | handler |")
    lines.append("|---|---:|---:|---:|---|---|")
    for row in result["correlations"]:
        lines.append(
            f"| {row.get('name')} | {row.get('collectorLine')} | {row.get('partIndex')} | {row.get('parentLine')} | {row.get('valueMatch')} | {row.get('handler')} |"
        )
    lines.append("")
    lines.append("## decoded events")
    for row in result["decodedEvents"]:
        value = str(row.get("value") or "")
        lines.append(
            f"- collectorLine={row.get('collectorLine')} part={row.get('partIndex')} handler={row.get('handler')} name={row.get('name')} ttl={row.get('ttl')} valueLen={len(value)}"
        )
    lines.append("")
    lines.append("## parent messages")
    for row in result["parentMessages"]:
        value = str(row.get("value") or "")
        lines.append(
            f"- line={row.get('line')} perf_t={row.get('perf_t')} origin={row.get('eventOrigin')} name={row.get('name')} expires={row.get('expires')} valueLen={len(value)}"
        )
    md_path = out_dir / f"cookie_timeline_{base}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build HUMAN _px cookie/success timeline from decoded collector responses and parent postMessages.")
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/cookie_timeline")
    args = parser.parse_args()

    outputs = []
    for trace in args.traces:
        result = analyze(trace)
        json_path, md_path = write_outputs(result, args.out_dir)
        outputs.append({"trace": str(trace), "jsonPath": str(json_path), "mdPath": str(md_path), "counts": result["counts"]})
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
