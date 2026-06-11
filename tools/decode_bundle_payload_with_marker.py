#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


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


def xor_string(value: str, key: int) -> str:
    return "".join(chr(ord(ch) ^ key) for ch in value)


def marker_from_qi(qi: str) -> str:
    return xor_string(base64.b64encode(str(qi).encode()).decode(), 10)


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def insertion_positions(chars: str, base_len: int, cu: str) -> list[int]:
    h = xor_string(base64.b64encode(str(cu).encode()).decode(), 10)
    positions: list[int] = []
    max_value = -1
    for p in range(len(chars)):
        m = p // len(h) + 1
        g = p % len(h) if p >= len(h) else p
        max_value = max(max_value, ord(h[g]) * ord(h[m]))
    for b in range(len(chars)):
        i = b // len(h) + 1
        e = b % len(h)
        pos = ord(h[e]) * ord(h[i])
        if pos >= base_len:
            pos = int((pos / max_value) * (base_len - 1))
        while pos in positions:
            pos += 1
        positions.append(pos)
    return sorted(positions)


def remove_marker(payload: str, marker: str, cu: str) -> dict[str, str]:
    positions = insertion_positions(marker, len(payload) - len(marker), cu)
    remove = {pos - 1 for pos in positions}
    extracted = []
    base = []
    for idx, ch in enumerate(payload):
        if idx in remove:
            extracted.append(ch)
        else:
            base.append(ch)
    return {"marker": "".join(extracted), "base": "".join(base)}


def decode_payload(payload: str, marker: str, cu: str) -> dict[str, Any]:
    removed = remove_marker(payload, marker, cu)
    raw_bytes = base64.b64decode(removed["base"])
    try:
        raw = raw_bytes.decode("utf-8")
        byte_encoding = "utf-8"
    except UnicodeDecodeError:
        raw = raw_bytes.decode("latin1")
        byte_encoding = "latin1-fallback"
    text = xor_string(raw, 50)
    try:
        parsed: Any = json.loads(text)
        json_error = None
    except Exception as exc:
        parsed = None
        json_error = str(exc)
    return {
        **removed,
        "markerMatch": removed["marker"] == marker,
        "byteEncoding": byte_encoding,
        "decodedText": text,
        "json": parsed,
        "jsonError": json_error,
    }


def build_marker_timeline(decode_path: Path) -> list[dict[str, Any]]:
    doc = json.loads(decode_path.read_text(encoding="utf-8"))
    timeline: list[dict[str, Any]] = []
    qi: str | None = None
    for entry in sorted(doc.get("decodedEntries", []), key=lambda x: int(x.get("lineNo") or 0)):
        for part in entry.get("parts") or []:
            fields = str(part).split("|")
            if fields[0] == "oIIoIoII" and len(fields) > 1:
                qi = fields[1]
        if qi:
            timeline.append({"afterLine": int(entry.get("lineNo") or 0), "qi": qi, "marker": marker_from_qi(qi)})
    return timeline


def marker_for_request(timeline: list[dict[str, Any]], request_line: int) -> dict[str, str]:
    current = None
    for item in timeline:
        if int(item["afterLine"]) >= request_line:
            break
        current = item
    if current:
        return {"qi": current["qi"], "marker": current["marker"], "source": f"collector oIIoIoII before line {request_line}"}
    return {"qi": "1604064986000", "marker": marker_from_qi("1604064986000"), "source": "static fallback"}


def contains_terms(value: Any, terms: list[str]) -> dict[str, bool]:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return {term: term in text for term in terms}


def base_name(path: Path) -> str:
    return path.name.removesuffix(".jsonl").removeprefix("runtime_trace_")


def run(runtime_trace: Path, decode_path: Path, terms: list[str]) -> dict[str, Any]:
    rows = read_jsonl(runtime_trace)
    timeline = build_marker_timeline(decode_path)
    out_rows = []
    for row in rows:
        if row.get("kind") != "request":
            continue
        url = str(row.get("url") or "")
        if not url.endswith("/assets/js/bundle"):
            continue
        params = parse_form(row.get("post_data") or "")
        marker = marker_for_request(timeline, int(row["_line"]))
        decoded = decode_payload(params.get("payload", ""), marker["marker"], params.get("uuid", ""))
        parsed = decoded["json"]
        out_rows.append({
            "requestLine": row["_line"],
            "url": url,
            "seq": params.get("seq"),
            "ft": params.get("ft"),
            "uuid": params.get("uuid"),
            "payloadLen": len(params.get("payload", "")),
            "markerQi": marker["qi"],
            "marker": marker["marker"],
            "markerSource": marker["source"],
            "extractedMarker": decoded["marker"],
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "jsonItemCount": len(parsed) if isinstance(parsed, list) else None,
            "activityTypes": [item.get("t") for item in parsed[:10]] if isinstance(parsed, list) else [],
            "contains": contains_terms(parsed if parsed is not None else decoded["decodedText"], terms),
            "decodedTextPreview": decoded["decodedText"][:500],
        })
    return {"runtimeTrace": str(runtime_trace), "decodePath": str(decode_path), "terms": terms, "rows": out_rows}


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["runtimeTrace"]))
    json_path = out_dir / f"bundle_payload_decode_{base}.json"
    md_path = out_dir / f"bundle_payload_decode_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Bundle payload decode with collector marker: {base}",
        "",
        f"runtime={result['runtimeTrace']}",
        f"decode={result['decodePath']}",
        "",
        "| req line | seq | payloadLen | markerQi | markerMatch | jsonItems | contains | activityTypes |",
        "|---:|---:|---:|---|---|---:|---|---|",
    ]
    for row in result["rows"]:
        contains = ",".join(k for k, v in row["contains"].items() if v)
        lines.append(
            f"| {row['requestLine']} | {row.get('seq') or ''} | {row['payloadLen']} | {row['markerQi']} | "
            f"{row['markerMatch']} | {row.get('jsonItemCount') or ''} | {contains} | {','.join(row['activityTypes'])} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Decode HUMAN /assets/js/bundle request payload using collector oIIoIoII marker state.")
    parser.add_argument("runtime_trace", type=Path)
    parser.add_argument("collector_decode", type=Path)
    parser.add_argument("--term", action="append", default=[])
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/bundle_payload_decode")
    args = parser.parse_args()
    terms = args.term or ["218e34c1", "50239", "1366f575", "oIIoIooo"]
    result = run(args.runtime_trace, args.collector_decode, terms)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "requestCount": len(result["rows"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
