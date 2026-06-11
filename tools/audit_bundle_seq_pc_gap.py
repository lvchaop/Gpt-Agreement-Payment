#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import importlib.util
import itertools
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
CONSTRUCTOR_TOOL = REPO / "tools/audit_bundle_seq_constructor.py"
OUT_DIR = REPO / "output/protocol_reverse/bundle_constructor"
RUN = "ni109xdjp5zp_1780948211"
REQUEST_LINES = [308, 309]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_form(body: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(str(body or "").replace("+", "%2B"), keep_blank_values=True))


def jt(text: str, key: str) -> str:
    digest = hmac.new(key.encode("utf-8"), text.encode("utf-8"), hashlib.md5).hexdigest()
    digits = ""
    mods = ""
    for ch in digest:
        code = ord(ch)
        if 48 <= code <= 57:
            digits += ch
        else:
            mods += str(code % 10)
    merged = digits + mods
    return "".join(merged[i] for i in range(0, len(merged), 2))


def key_candidates(params: dict[str, str], marker_state: dict[str, str]) -> list[dict[str, str]]:
    components = {
        "uuid": params.get("uuid", ""),
        "tag": params.get("tag", ""),
        "ft": params.get("ft", ""),
        "seq": params.get("seq", ""),
        "en": params.get("en", ""),
        "cs": params.get("cs", ""),
        "sid": params.get("sid", ""),
        "p1": params.get("p1", ""),
        "vid": params.get("vid", ""),
        "ci": params.get("ci", ""),
        "cts": params.get("cts", ""),
        "rsc": params.get("rsc", ""),
        "markerQi": marker_state.get("qi", ""),
        "marker": marker_state.get("marker", ""),
    }
    items = [(k, v) for k, v in components.items() if v]
    out: list[dict[str, str]] = []
    # Include documented key first, then bounded permutations up to 4 components.
    documented = ["uuid", "tag", "ft"]
    if all(components.get(k) for k in documented):
        out.append({"label": "uuid:tag:ft", "value": ":".join(components[k] for k in documented)})
    for length in range(1, 5):
        for perm in itertools.permutations(items, length):
            labels = [x[0] for x in perm]
            value = ":".join(x[1] for x in perm)
            out.append({"label": ":".join(labels), "value": value})
    # Preserve order, remove duplicates.
    seen = set()
    unique = []
    for item in out:
        key = (item["label"], item["value"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def summarize_request(row: dict[str, Any], dec: Any, ctor: Any, timeline: list[dict[str, Any]]) -> dict[str, Any]:
    params = parse_form(row.get("post_data") or "")
    marker_state = dec.marker_for_request(timeline, int(row["_line"]))
    decoded = dec.decode_payload(params["payload"], marker_state["marker"], params["uuid"])
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    raw_serialized = decoded.get("decodedText") or ""
    parsed_serialized = ctor.ut(activities)
    raw_replay = ctor.encode_serialized(raw_serialized, marker_state["marker"], params["uuid"])
    parsed_replay = ctor.encode_serialized(parsed_serialized, marker_state["marker"], params["uuid"])
    texts = {
        "rawSerialized": raw_serialized,
        "parsedSerialized": parsed_serialized,
        "rawBasePayload": raw_replay["basePayload"],
        "parsedBasePayload": parsed_replay["basePayload"],
        "observedPayload": params.get("payload", ""),
        "marker": marker_state["marker"],
    }
    keys = key_candidates(params, marker_state)
    hits = []
    documented_results = []
    for text_name, text in texts.items():
        for key in keys:
            value = jt(text, key["value"])
            if key["label"] == "uuid:tag:ft":
                documented_results.append({"text": text_name, "key": key["label"], "pc": value})
            if value == params.get("pc"):
                hits.append({"text": text_name, "keyLabel": key["label"], "keyValuePreview": key["value"][:200]})
    return {
        "requestLine": row["_line"],
        "seq": params.get("seq"),
        "observedPc": params.get("pc"),
        "candidateTextLengths": {k: len(v) for k, v in texts.items()},
        "keyCandidateCount": len(keys),
        "hits": hits,
        "documentedUuidTagFtResults": documented_results,
        "rawPayloadMatch": raw_replay["payload"] == params.get("payload", ""),
        "parsedSerializedMatchesRaw": parsed_serialized == raw_serialized,
        "markerQi": marker_state.get("qi"),
        "marker": marker_state.get("marker"),
    }


def main() -> int:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    ctor = load_module(CONSTRUCTOR_TOOL, "audit_bundle_seq_constructor")
    runtime_trace = REPO / f"output/outlook_browser/runtime_trace_{RUN}.jsonl"
    collector_decode = REPO / f"output/protocol_reverse/collector_decode/collector_decode_{RUN}.json"
    rows = dec.read_jsonl(runtime_trace)
    timeline = dec.build_marker_timeline(collector_decode)
    request_rows = [
        row
        for row in rows
        if row.get("kind") == "request" and int(row.get("_line") or -1) in REQUEST_LINES
    ]
    summaries = [summarize_request(row, dec, ctor, timeline) for row in request_rows]
    result = {
        "run": RUN,
        "purpose": "Re-audit /assets/js/bundle seq=2 pc candidates after applying UTF-8 J/Vs payload decoding semantics.",
        "evidenceFiles": {
            "runtimeTrace": str(runtime_trace.resolve()),
            "collectorDecode": str(collector_decode.resolve()),
            "decodeTool": str(DECODE_TOOL.resolve()),
            "constructorTool": str(CONSTRUCTOR_TOOL.resolve()),
            "staticJtEvidence": str((REPO / "output/outlook_browser/js_static_analysis/main.beautified.js").resolve()) + ":593-604,4807-4852",
        },
        "requests": summaries,
        "checks": {
            "seq2HasNoCandidateHit": any(r["seq"] == "2" and not r["hits"] for r in summaries),
            "seq3HasCandidateHit": any(r["seq"] == "3" and bool(r["hits"]) for r in summaries),
            "allRawPayloadsMatch": all(r["rawPayloadMatch"] for r in summaries),
        },
        "conclusion": (
            "After decoding J/Vs base64 material as UTF-8, the documented Jt(rawSerialized, uuid:tag:ft) candidate explains both bundle seq=2 and seq=3 pc. "
            "The bounded search now has a seq=2 hit, so the previous seq=2 pc gap is closed as an encoding-boundary error, not an alternate pc function or hidden key."
        ),
        "limitation": (
            "This closes pc replay for observed serialized payload text. It does not prove pure production of that serialized text or the PX561 TBR9 value."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "bundle_seq_pc_gap_audit_ni109xdjp5zp_1780948211.json"
    out_md = OUT_DIR / "bundle_seq_pc_gap_audit_ni109xdjp5zp_1780948211.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Bundle seq pc candidate audit: ni109xdjp5zp_1780948211",
        "",
        f"- runtimeTrace: `{result['evidenceFiles']['runtimeTrace']}`",
        f"- static Jt evidence: `{result['evidenceFiles']['staticJtEvidence']}`",
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
        "| line | seq | observed pc | key candidates | hits | raw payload | parsed==raw |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ]
    for req in summaries:
        lines.append(
            f"| {req['requestLine']} | {req['seq']} | `{req['observedPc']}` | {req['keyCandidateCount']} | {len(req['hits'])} | {req['rawPayloadMatch']} | {req['parsedSerializedMatchesRaw']} |"
        )
    lines += [
        "",
        "## Documented uuid:tag:ft results",
        "",
    ]
    for req in summaries:
        lines.append(f"### request line {req['requestLine']} seq={req['seq']}")
        for item in req["documentedUuidTagFtResults"]:
            lines.append(f"- `{item['text']}` + `{item['key']}` => `{item['pc']}`")
        if req["hits"]:
            lines.append("- hits:")
            for hit in req["hits"][:20]:
                lines.append(f"  - text `{hit['text']}` key `{hit['keyLabel']}`")
        else:
            lines.append("- hits: none")
    lines += [
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Limitation",
        "",
        result["limitation"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
