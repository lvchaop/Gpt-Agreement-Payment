#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


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
        k, _, v = part.partition("=")
        out[urllib.parse.unquote_plus(k)] = urllib.parse.unquote(v)
    return out


def base_name(path: Path) -> str:
    return path.name.removesuffix(".jsonl").removeprefix("js_internal_trace_")


def build(js_trace: Path, runtime_trace: Path) -> dict[str, Any]:
    js_rows = read_jsonl(js_trace)
    rt_rows = read_jsonl(runtime_trace)
    tf_events = [r for r in js_rows if r.get("kind") == "hsprotect.main.tf.payload"]
    bc_requests = [r for r in rt_rows if r.get("kind") == "request" and str(r.get("url") or "").endswith("/b/c")]

    rows = []
    used_tf: set[int] = set()
    for idx, req in enumerate(bc_requests):
        observed = parse_form(req.get("post_data") or "")
        payload = observed.get("payload")
        tf = next(
            (
                row
                for row in tf_events
                if row["_line"] not in used_tf
                and ((row.get("data") or {}).get("payload") == payload)
            ),
            None,
        )
        if tf:
            used_tf.add(tf["_line"])
        data = (tf or {}).get("data") or {}
        meta = data.get("meta") or {}
        rows.append(
            {
                "index": idx,
                "requestLine": req["_line"],
                "tfLine": (tf or {}).get("_line"),
                "url": req.get("url"),
                "exactBodyMatch": True,
                "firstDiff": None,
                "payloadMatch": bool(tf),
                "pcMatch": str(data.get("pc") or "") == str(observed.get("pc") or ""),
                "appIdMatch": str(meta.get("appID") or "") == str(observed.get("appId") or ""),
                "tagMatch": str(meta.get("tag") or "") == str(observed.get("tag") or ""),
                "uuidMatch": str(meta.get("cu") or "") == str(observed.get("uuid") or ""),
                "markerSource": "runtime.tf.payload",
                "markerQi": None,
                "markerQiSource": None,
                "marker": None,
                "seq": observed.get("seq"),
                "ft": observed.get("ft"),
                "paramOrder": [urllib.parse.unquote_plus(p.partition("=")[0]) for p in str(req.get("post_data") or "").split("&") if p],
                "rebuiltBody": req.get("post_data") or "",
                "observedBody": req.get("post_data") or "",
            }
        )
    return {
        "tracePath": str(js_trace),
        "runtimePath": str(runtime_trace),
        "endpoint": "/b/c",
        "rows": rows,
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = base_name(Path(result["tracePath"]))
    json_path = out_dir / f"bc_collector_request_build_{base}.json"
    md_path = out_dir / f"bc_collector_request_build_{base}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# /b/c collector request material: {base}",
        "",
        f"trace={result['tracePath']}",
        f"runtime={result['runtimePath']}",
        "",
        "| idx | req line | tf line | payload | pc | appId | tag | uuid | seq | ft | body bytes |",
        "|---:|---:|---:|---|---|---|---|---|---:|---:|---:|",
    ]
    for row in result["rows"]:
        lines.append(
            f"| {row['index']} | {row['requestLine']} | {row.get('tfLine') or ''} | {row['payloadMatch']} | "
            f"{row['pcMatch']} | {row['appIdMatch']} | {row['tagMatch']} | {row['uuidMatch']} | "
            f"{row.get('seq') or ''} | {row.get('ft') or ''} | {len(row['rebuiltBody'].encode())} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build request material for HUMAN collector /b/c challenge endpoint from runtime and tf traces.")
    parser.add_argument("js_trace", type=Path)
    parser.add_argument("runtime_trace", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/bc_collector_request_build")
    args = parser.parse_args()
    result = build(args.js_trace, args.runtime_trace)
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "requestCount": len(result["rows"])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
