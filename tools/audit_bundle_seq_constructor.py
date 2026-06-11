#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
OUT_DIR = REPO / "output/protocol_reverse/bundle_constructor"
RUN = "ni109xdjp5zp_1780948211"
TARGET_REQUEST_LINES = {308, 309}
TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "KVkYX28zG2o=",
    "Ew9iCVZkZD4=",
]


JSON_ESCAPES = {
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
    '"': '\\"',
    "\\": "\\\\",
}


def load_decode_tool():
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_form(body: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(str(body or "").replace("+", "%2B"), keep_blank_values=True))


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def xor_string(value: str, key: int) -> str:
    return "".join(chr(ord(ch) ^ key) for ch in value)


def quote_string(value: str) -> str:
    out = ['"']
    for ch in str(value):
        code = ord(ch)
        if ch in JSON_ESCAPES:
            out.append(JSON_ESCAPES[ch])
        elif (
            0 <= code <= 0x1F
            or 0x7F <= code <= 0x9F
            or code == 0xAD
            or 0x0600 <= code <= 0x0604
            or code == 0x070F
            or code in (0x17B4, 0x17B5)
            or 0x200C <= code <= 0x200F
            or 0x2028 <= code <= 0x202F
            or 0x2060 <= code <= 0x206F
            or code == 0xFEFF
            or 0xFFF0 <= code <= 0xFFFF
        ):
            out.append("\\u" + format(code, "04x"))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def ut(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str):
        return quote_string(value)
    if isinstance(value, list):
        return "[" + ",".join(ut(item) for item in value) + "]"
    if isinstance(value, dict):
        parts = []
        for key, child in value.items():
            parts.append(quote_string(str(key)) + ":" + ut(child))
        return "{" + ",".join(parts) + "}"
    return "null"


def insertion_positions(chars: str, base_len: int, cu: str) -> list[int]:
    h = xor_string(b64(str(cu)), 10)
    positions: list[int] = []
    max_value = -1
    for p in range(len(chars)):
        m = p // len(h) + 1
        g = p % len(h) if p >= len(h) else p
        max_value = max(max_value, ord(h[g]) * ord(h[m]))
    for idx in range(len(chars)):
        i = idx // len(h) + 1
        e = idx % len(h)
        pos = ord(h[e]) * ord(h[i])
        if pos >= base_len:
            pos = int((pos / max_value) * (base_len - 1))
        while pos in positions:
            pos += 1
        positions.append(pos)
    return sorted(positions)


def insert_chars(chars: str, base: str, positions: list[int]) -> str:
    out = ""
    start = 0
    for i, ch in enumerate(chars):
        cut = positions[i] - i - 1
        out += base[start:cut] + ch
        start = cut
    return out + base[start:]


def encode_serialized(serialized: str, marker: str, uuid: str) -> dict[str, Any]:
    # Static J(t) applies btoa to the UTF-8 bytes produced by
    # encodeURIComponent(t), not to latin-1 code units.
    base = base64.b64encode(xor_string(serialized, 50).encode("utf-8")).decode("ascii")
    positions = insertion_positions(marker, len(base), uuid)
    payload = insert_chars(marker, base, positions)
    return {
        "serialized": serialized,
        "basePayload": base,
        "positions": positions,
        "payload": payload,
    }


def pc_value(serialized: str, uuid: str, tag: str, ft: str) -> str:
    key = f"{uuid}:{tag}:{ft}"
    digest = hmac.new(key.encode("utf-8"), serialized.encode("utf-8"), hashlib.md5).hexdigest()
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


def first_diff(a: str, b: str) -> dict[str, Any] | None:
    for idx, (ca, cb) in enumerate(zip(a, b)):
        if ca != cb:
            return {"index": idx, "actual": ca, "expected": cb, "actualCode": ord(ca), "expectedCode": ord(cb)}
    if len(a) != len(b):
        return {"index": min(len(a), len(b)), "actualLen": len(a), "expectedLen": len(b)}
    return None


def preview(value: Any, limit: int = 160) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<len={len(value)}>"
    return value


def activity_summary(activity: Any, idx: int) -> dict[str, Any]:
    if not isinstance(activity, dict):
        return {"index": idx, "type": None, "kind": type(activity).__name__}
    d = activity.get("d")
    keys = list(d.keys()) if isinstance(d, dict) else []
    targets = {}
    if isinstance(d, dict):
        for key in TARGET_KEYS:
            if key in d:
                targets[key] = {"index": keys.index(key), "type": type(d[key]).__name__, "value": preview(d[key])}
    return {
        "index": idx,
        "type": activity.get("t"),
        "dKeyCount": len(keys),
        "targetKeys": targets,
        "hasPowAnswer": isinstance(d, dict) and d.get("OSkIb39DDA==") == "218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f",
        "hasTBR9": isinstance(d, dict) and "TBR9Ugl7emA=" in d,
        "hasAEAx": isinstance(d, dict) and "AEAxBkUsPjQ=" in d,
    }


def main() -> int:
    runtime_trace = REPO / f"output/outlook_browser/runtime_trace_{RUN}.jsonl"
    collector_decode = REPO / f"output/protocol_reverse/collector_decode/collector_decode_{RUN}.json"
    decode_tool = load_decode_tool()
    rows = decode_tool.read_jsonl(runtime_trace)
    timeline = decode_tool.build_marker_timeline(collector_decode)
    request_results = []

    for row in rows:
        if row.get("kind") != "request" or int(row.get("_line") or 0) not in TARGET_REQUEST_LINES:
            continue
        params = parse_form(row.get("post_data") or "")
        marker_state = decode_tool.marker_for_request(timeline, int(row["_line"]))
        decoded = decode_tool.decode_payload(params["payload"], marker_state["marker"], params["uuid"])
        activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
        raw_serialized = decoded.get("decodedText") or ""
        parsed_serialized = ut(activities)
        raw_replay = encode_serialized(raw_serialized, marker_state["marker"], params["uuid"])
        parsed_replay = encode_serialized(parsed_serialized, marker_state["marker"], params["uuid"])
        raw_pc_replay = pc_value(raw_replay["serialized"], params["uuid"], params["tag"], params["ft"])
        parsed_pc_replay = pc_value(parsed_replay["serialized"], params["uuid"], params["tag"], params["ft"])
        request_results.append(
            {
                "requestLine": row["_line"],
                "t": row.get("t"),
                "url": row.get("url"),
                "seq": params.get("seq"),
                "ft": params.get("ft"),
                "uuid": params.get("uuid"),
                "tag": params.get("tag"),
                "observedPc": params.get("pc"),
                "rawReplayPc": raw_pc_replay,
                "rawPcMatch": raw_pc_replay == params.get("pc"),
                "parsedReplayPc": parsed_pc_replay,
                "parsedPcMatch": parsed_pc_replay == params.get("pc"),
                "marker": marker_state["marker"],
                "markerQi": marker_state["qi"],
                "markerSource": marker_state["source"],
                "markerMatch": decoded.get("markerMatch"),
                "jsonItemCount": len(activities),
                "rawSerializedLen": len(raw_serialized),
                "parsedSerializedLen": len(parsed_serialized),
                "parsedSerializedMatchesRaw": parsed_serialized == raw_serialized,
                "firstParsedSerializedDiff": first_diff(parsed_serialized, raw_serialized),
                "observedPayloadLen": len(params.get("payload", "")),
                "rawReplayPayloadLen": len(raw_replay["payload"]),
                "rawPayloadMatch": raw_replay["payload"] == params.get("payload"),
                "firstRawPayloadDiff": first_diff(raw_replay["payload"], params.get("payload", "")),
                "parsedReplayPayloadLen": len(parsed_replay["payload"]),
                "parsedPayloadMatch": parsed_replay["payload"] == params.get("payload"),
                "firstParsedPayloadDiff": first_diff(parsed_replay["payload"], params.get("payload", "")),
                "rawSerializedSha256": hashlib.sha256(raw_replay["serialized"].encode("utf-8")).hexdigest(),
                "parsedSerializedSha256": hashlib.sha256(parsed_replay["serialized"].encode("utf-8")).hexdigest(),
                "rawBasePayloadSha256": hashlib.sha256(raw_replay["basePayload"].encode("ascii")).hexdigest(),
                "activitySummaries": [activity_summary(activity, idx) for idx, activity in enumerate(activities)],
            }
        )

    result = {
        "run": RUN,
        "purpose": "Verify that decoded /assets/js/bundle seq=2/3 activities plus observed collector marker state and uuid are sufficient to reconstruct observed payload/pc, and summarize PX561/POW/TBR9 fields.",
        "evidenceFiles": {
            "runtimeTrace": str(runtime_trace.resolve()),
            "collectorDecode": str(collector_decode.resolve()),
            "decodeTool": str(DECODE_TOOL.resolve()),
        },
        "requests": request_results,
        "checks": {
            "allTargetRequestsFound": {line: any(r["requestLine"] == line for r in request_results) for line in sorted(TARGET_REQUEST_LINES)},
            "allRawPayloadsReplay": all(r["rawPayloadMatch"] for r in request_results),
            "allRawPcReplay": all(r["rawPcMatch"] for r in request_results),
            "allParsedPayloadsReplay": all(r["parsedPayloadMatch"] for r in request_results),
            "allParsedPcReplay": all(r["parsedPcMatch"] for r in request_results),
            "allParsedSerializedMatchesRaw": all(r["parsedSerializedMatchesRaw"] for r in request_results),
            "seq2HasPX561PowTbr9Aeax": any(
                r.get("seq") == "2"
                and any(
                    a.get("type") == "PX561" and a.get("hasPowAnswer") and a.get("hasTBR9") and a.get("hasAEAx")
                    for a in r.get("activitySummaries") or []
                )
                for r in request_results
            ),
            "seq3HasNoPX561": any(
                r.get("seq") == "3" and not any(a.get("type") == "PX561" for a in r.get("activitySummaries") or [])
                for r in request_results
            ),
        },
        "conclusion": (
            "For ni109 accepted success, /assets/js/bundle seq=2 and seq=3 payload can be byte-replayed from the exact decoded serialized text plus marker state. "
            "Both seq=2 and seq=3 pc values replay with the documented Jt(serialized, uuid:tag:ft) input after decoding J/Vs payload bytes as UTF-8, matching static J(t) semantics. "
            "The earlier seq=2 pc miss was caused by treating J(t)'s base64 material as latin-1 bytes instead of UTF-8 bytes from encodeURIComponent(t). "
            "Seq=2 is the decoded request that carries PX561 with POW answer, AEAx, and TBR9; seq=3 is a separate one-activity bundle immediately before the success handler."
        ),
        "limitation": (
            "This proves payload/pc replay from exact decoded observed serialized text, not pure production of that text. The remaining pure-protocol gap is deriving the seq=2 serialized activities, especially the PX561 TBR9 value, without observing a successful browser run."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "bundle_seq_constructor_audit_ni109xdjp5zp_1780948211.json"
    out_md = OUT_DIR / "bundle_seq_constructor_audit_ni109xdjp5zp_1780948211.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Bundle seq constructor audit: ni109xdjp5zp_1780948211",
        "",
        f"- runtimeTrace: `{result['evidenceFiles']['runtimeTrace']}`",
        f"- collectorDecode: `{result['evidenceFiles']['collectorDecode']}`",
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
        "| line | seq | raw payload | raw pc | parsed payload | parsed pc | parsed==raw | markerMatch | jsonItems | markerQi |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for req in request_results:
        lines.append(
            f"| {req['requestLine']} | {req['seq']} | {req['rawPayloadMatch']} | {req['rawPcMatch']} | {req['parsedPayloadMatch']} | {req['parsedPcMatch']} | {req['parsedSerializedMatchesRaw']} | {req['markerMatch']} | {req['jsonItemCount']} | `{req['markerQi']}` |"
        )
    lines += [
        "",
        "## Activity summaries",
        "",
    ]
    for req in request_results:
        lines.append(f"### request line {req['requestLine']} seq={req['seq']}")
        lines.append("| idx | type | d keys | POW answer | AEAx | TBR9 | target keys |")
        lines.append("|---:|---|---:|---:|---:|---:|---|")
        for activity in req["activitySummaries"]:
            targets = ",".join(activity.get("targetKeys", {}).keys()) or "-"
            lines.append(
                f"| {activity['index']} | `{activity.get('type')}` | {activity.get('dKeyCount')} | {activity.get('hasPowAnswer')} | {activity.get('hasAEAx')} | {activity.get('hasTBR9')} | {targets} |"
            )
        for activity in req["activitySummaries"]:
            if activity.get("type") == "PX561":
                lines.append("")
                lines.append("PX561 target key details:")
                for key, item in (activity.get("targetKeys") or {}).items():
                    lines.append(f"- `{key}` index `{item['index']}` type `{item['type']}` value `{item['value']}`")
        lines.append("")
    lines += [
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
