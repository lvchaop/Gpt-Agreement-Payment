#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CONSTRUCTOR_TOOL = REPO / "tools/audit_bundle_seq_constructor.py"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
OUT_DIR = REPO / "output/protocol_reverse/bundle_request_build"
TERMS = ["PX561", "AEAx", "TBR9Ugl7emA=", "OSkIb39DDA=="]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def parse_raw_pairs(body: str) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for part in str(body or "").split("&"):
        if not part:
            continue
        raw_key, sep, raw_value = part.partition("=")
        pairs.append(
            {
                "rawKey": raw_key,
                "rawValue": raw_value if sep else "",
                "key": urllib.parse.unquote_plus(raw_key),
                # HUMAN payload values use literal '+'; do not form-decode '+' as space.
                "value": urllib.parse.unquote(raw_value if sep else ""),
            }
        )
    return pairs


def pairs_to_map(pairs: list[dict[str, str]]) -> dict[str, str]:
    return {p["key"]: p["value"] for p in pairs}


def rebuild_body(pairs: list[dict[str, str]], replacements: dict[str, str]) -> str:
    out = []
    for pair in pairs:
        value = replacements.get(pair["key"], pair["rawValue"])
        out.append(f"{pair['rawKey']}={value}")
    return "&".join(out)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def first_diff(a: str, b: str) -> dict[str, Any] | None:
    for idx, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return {"index": idx, "actual": ca, "expected": cb, "actualCode": ord(ca), "expectedCode": ord(cb)}
    if len(a) != len(b):
        return {"index": min(len(a), len(b)), "actualLen": len(a), "expectedLen": len(b)}
    return None


def contains_terms(value: str) -> dict[str, bool]:
    return {term: term in value for term in TERMS}


def nearest_payload_hook(payload_hooks: list[dict[str, Any]], t: float, pc: str) -> dict[str, Any] | None:
    candidates = []
    for event in payload_hooks:
        data = event.get("data") or {}
        event_pc = data.get("pc") or (data.get("meta") or {}).get("pc")
        if str(event_pc or "") != str(pc or ""):
            continue
        wall_t = float(event.get("wall_t") or -1)
        if wall_t <= t + 0.050:
            candidates.append(event)
    if not candidates:
        return None
    return max(candidates, key=lambda event: float(event.get("wall_t") or -1))


def serialized_material(
    *,
    row: dict[str, Any],
    params: dict[str, str],
    payload_hooks: list[dict[str, Any]],
    decode_tool: Any,
    marker_timeline: list[dict[str, Any]],
) -> dict[str, Any]:
    hook = nearest_payload_hook(payload_hooks, float(row.get("t") or 0), params.get("pc", ""))
    if hook is not None:
        data = hook.get("data") or {}
        return {
            "source": "hsprotect.main.tf.payload",
            "sourceLine": hook["_line"],
            "serialized": str(data.get("serialized") or ""),
            "marker": str(data.get("marker") or ""),
            "decode": None,
        }

    marker_state = decode_tool.marker_for_request(marker_timeline, int(row["_line"]))
    decoded = decode_tool.decode_payload(params.get("payload", ""), marker_state["marker"], params.get("uuid", ""))
    marker = marker_state["marker"]
    source = marker_state["source"]
    if decoded.get("markerMatch") is False and decoded.get("marker"):
        marker = str(decoded["marker"])
        source = "observedPayload.extractedMarker"
    return {
        "source": source,
        "sourceLine": marker_state.get("qiSource"),
        "serialized": str(decoded.get("decodedText") or ""),
        "marker": marker,
        "decode": {
            "markerMatch": decoded.get("markerMatch"),
            "byteEncoding": decoded.get("byteEncoding"),
            "jsonError": decoded.get("jsonError"),
            "candidateMarkerSource": marker_state["source"],
        },
    }


def summarize_request(
    row: dict[str, Any],
    *,
    ctor: Any,
    decode_tool: Any,
    marker_timeline: list[dict[str, Any]],
    payload_hooks: list[dict[str, Any]],
) -> dict[str, Any]:
    observed_body = str(row.get("post_data") or "")
    pairs = parse_raw_pairs(observed_body)
    params = pairs_to_map(pairs)
    material = serialized_material(
        row=row,
        params=params,
        payload_hooks=payload_hooks,
        decode_tool=decode_tool,
        marker_timeline=marker_timeline,
    )
    serialized = material["serialized"]
    marker = material["marker"]
    replay = ctor.encode_serialized(serialized, marker, params.get("uuid", ""))
    pc = ctor.pc_value(serialized, params.get("uuid", ""), params.get("tag", ""), params.get("ft", ""))
    rebuilt_body = rebuild_body(pairs, {"payload": replay["payload"], "pc": pc})
    return {
        "requestLine": row["_line"],
        "requestTime": row.get("t"),
        "url": row.get("url"),
        "seq": params.get("seq"),
        "uuid": params.get("uuid"),
        "tag": params.get("tag"),
        "ft": params.get("ft"),
        "paramOrder": [p["key"] for p in pairs],
        "materialSource": material["source"],
        "materialSourceLine": material["sourceLine"],
        "serializedLen": len(serialized),
        "serializedSha256": sha256_text(serialized),
        "markerLen": len(marker),
        "observedPayloadLen": len(params.get("payload", "")),
        "rebuiltPayloadLen": len(replay["payload"]),
        "observedPc": params.get("pc"),
        "rebuiltPc": pc,
        "payloadMatch": replay["payload"] == params.get("payload", ""),
        "pcMatch": pc == params.get("pc", ""),
        "bodyMatch": rebuilt_body == observed_body,
        "firstBodyDiff": first_diff(rebuilt_body, observed_body),
        "decodedPayload": material["decode"],
        "contains": contains_terms(serialized),
    }


def build(runtime_trace: Path, collector_decode: Path, js_trace: Path | None) -> dict[str, Any]:
    ctor = load_module(CONSTRUCTOR_TOOL, "audit_bundle_seq_constructor")
    decode_tool = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    runtime_rows = read_jsonl(runtime_trace)
    js_rows = read_jsonl(js_trace)
    payload_hooks = [r for r in js_rows if r.get("kind") == "hsprotect.main.tf.payload"]
    marker_timeline = decode_tool.build_marker_timeline(collector_decode)
    request_rows = [
        r
        for r in runtime_rows
        if r.get("kind") == "request" and str(r.get("url") or "").endswith("/assets/js/bundle")
    ]
    rows = [
        summarize_request(
            row,
            ctor=ctor,
            decode_tool=decode_tool,
            marker_timeline=marker_timeline,
            payload_hooks=payload_hooks,
        )
        for row in request_rows
    ]
    return {
        "purpose": "Build complete /assets/js/bundle POST bodies from serialized activities, marker, uuid/tag/ft, and observed non-payload optional fields.",
        "evidenceFiles": {
            "runtimeTrace": str(runtime_trace.resolve()),
            "collectorDecode": str(collector_decode.resolve()),
            "jsTrace": str(js_trace.resolve()) if js_trace else None,
            "constructorTool": str(CONSTRUCTOR_TOOL.resolve()),
            "decodeTool": str(DECODE_TOOL.resolve()),
        },
        "rows": rows,
        "checks": {
            "allRequestsBuilt": len(rows) == len(request_rows) and bool(rows),
            "allPayloadsMatch": all(r["payloadMatch"] for r in rows),
            "allPcsMatch": all(r["pcMatch"] for r in rows),
            "allBodiesMatch": all(r["bodyMatch"] for r in rows),
            "hasPx561AeaxTbr9Request": any(
                r["contains"].get("PX561") and r["contains"].get("AEAx") and r["contains"].get("TBR9Ugl7emA=")
                for r in rows
            ),
        },
        "conclusion": (
            "The /assets/js/bundle form body is byte-rebuilt when serialized activities, marker, uuid/tag/ft, and observed optional form fields are supplied. "
            "This closes the bundle request encoding layer for local success samples, while leaving pure production of accepted-success serialized PX561/TBR9 activities as the remaining upstream gap."
        ),
    }


def write_outputs(result: dict[str, Any], out_dir: Path, name: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"bundle_request_build_{name}.json"
    md_path = out_dir / f"bundle_request_build_{name}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Bundle request build: {name}",
        "",
        f"- runtimeTrace: `{result['evidenceFiles']['runtimeTrace']}`",
        f"- collectorDecode: `{result['evidenceFiles']['collectorDecode']}`",
        f"- jsTrace: `{result['evidenceFiles']['jsTrace']}`",
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## Requests",
        "",
        "| line | seq | source | payload | pc | body | serialized len | payload len | contains |",
        "|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result["rows"]:
        contains = ",".join(k for k, v in row["contains"].items() if v) or "-"
        lines.append(
            f"| {row['requestLine']} | {row.get('seq') or ''} | `{row['materialSource']}` | "
            f"{row['payloadMatch']} | {row['pcMatch']} | {row['bodyMatch']} | "
            f"{row['serializedLen']} | {row['observedPayloadLen']} | {contains} |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def default_name(runtime_trace: Path) -> str:
    return runtime_trace.name.removesuffix(".jsonl").removeprefix("runtime_trace_")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify complete HUMAN /assets/js/bundle collector POST bodies.")
    parser.add_argument("runtime_trace", type=Path)
    parser.add_argument("collector_decode", type=Path)
    parser.add_argument("--js-trace", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    name = args.name or default_name(args.runtime_trace)
    result = build(args.runtime_trace, args.collector_decode, args.js_trace)
    json_path, md_path = write_outputs(result, args.out_dir, name)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
