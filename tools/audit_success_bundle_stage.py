#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"
RUN = "ni109xdjp5zp_1780948211"
TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "KVkYX28zG2o=",
    "Ew9iCVZkZD4=",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def preview(value: Any, limit: int = 180) -> Any:
    if not isinstance(value, str):
        return value
    return value if len(value) <= limit else value[:limit] + f"...<len={len(value)}>"


def compact_event(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data") or {}
    out: dict[str, Any] = {
        "line": row.get("_line"),
        "kind": row.get("kind"),
        "wall_t": row.get("wall_t") or row.get("t"),
    }
    if row.get("kind") == "request":
        out.update({
            "method": row.get("method"),
            "url": row.get("url"),
            "post_len": row.get("post_len"),
            "contentLength": (row.get("headers") or {}).get("content-length"),
        })
    elif row.get("kind") == "response":
        out.update({
            "status": row.get("status"),
            "url": row.get("url"),
            "contentLength": (row.get("headers") or {}).get("content-length"),
            "body_len": row.get("body_len"),
        })
    else:
        out.update({
            "channel": data.get("channel"),
            "args": [preview(x, 260) for x in (data.get("args") or [])[:4]],
            "stack": "\n".join(str(data.get("stack") or "").splitlines()[:8]),
            "raw": preview(data.get("raw"), 260),
        })
    return out


def main() -> None:
    runtime_path = REPO / f"output/outlook_browser/runtime_trace_{RUN}.jsonl"
    js_path = REPO / f"output/outlook_browser/js_internal_trace_{RUN}.jsonl"
    matches_path = REPO / f"output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_{RUN}.json"
    payload_chain_path = REPO / f"output/protocol_reverse/payload_chain/payload_chain_{RUN}.json"
    trace_class_path = REPO / f"output/protocol_reverse/trace_classification_{RUN}.json"

    runtime_rows = read_jsonl(runtime_path)
    js_rows = read_jsonl(js_path)
    matches = json.loads(matches_path.read_text(encoding="utf-8"))
    payload_chain = json.loads(payload_chain_path.read_text(encoding="utf-8"))
    trace_class = json.loads(trace_class_path.read_text(encoding="utf-8"))

    request_308 = None
    activity = None
    activity_index = None
    for req in matches["requests"]:
        if req.get("requestLine") == 308:
            request_308 = req
            acts = req.get("activitiesWithMatches") or []
            if acts:
                activity_index = acts[0].get("index")
                activity = acts[0].get("activity")
            break
    if request_308 is None or activity is None:
        raise SystemExit("request 308 PX561 activity not found")

    d = activity.get("d") or {}
    key_positions = []
    for idx, key in enumerate(d.keys()):
        if key in TARGET_KEYS:
            key_positions.append({
                "index": idx,
                "key": key,
                "value": preview(d.get(key)),
                "type": type(d.get(key)).__name__,
            })

    runtime_window = [compact_event(row) for row in runtime_rows if 295 <= int(row.get("_line") or 0) <= 312]
    js_window = [compact_event(row) for row in js_rows if 295 <= int(row.get("_line") or 0) <= 332]
    tf_payload_events = [row for row in js_rows if row.get("kind") == "hsprotect.main.tf.payload"]

    result = {
        "run": RUN,
        "evidenceFiles": {
            "runtimeTrace": str(runtime_path),
            "jsTrace": str(js_path),
            "bundleActivityMatches": str(matches_path),
            "payloadChain": str(payload_chain_path),
            "traceClassification": str(trace_class_path),
        },
        "traceCounts": trace_class.get("counts"),
        "request308": {
            "requestLine": request_308.get("requestLine"),
            "seq": request_308.get("seq"),
            "ft": request_308.get("ft"),
            "uuid": request_308.get("uuid"),
            "payloadLen": request_308.get("payloadLen"),
            "markerMatch": request_308.get("markerMatch"),
            "jsonItemCount": request_308.get("jsonItemCount"),
            "activityIndex": activity_index,
            "activityType": activity.get("t"),
            "px561KeyCount": len(d),
            "targetKeyPositions": key_positions,
        },
        "payloadChainCounts": payload_chain.get("counts"),
        "tfPayloadEventCountInSuccessJsTrace": len(tf_payload_events),
        "runtimeWindow295_312": runtime_window,
        "jsWindow295_332": js_window,
        "findings": [
            "success key material is present in decoded /assets/js/bundle request line 308, not in a hsprotect.main.tf.payload hook event; success js trace has zero tf.payload events.",
            "line 307 JDBeOmJSWwo= trigger stack enters Iz/D/Ts in captcha.js immediately before runtime request line 308; this is the closest current runtime boundary for PX561 success bundle construction.",
            "line 310 response body was not captured (body_len=0), so current artifact proves request payload contents but not response-body semantics for /assets/js/bundle.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "success_bundle_stage_audit.json"
    md_path = OUT_DIR / "success_bundle_stage_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# success bundle stage audit",
        "",
        f"run=`{RUN}`",
        "",
        "## target key positions in decoded request line 308",
        "| index | key | type | value |",
        "|---:|---|---|---|",
    ]
    for item in key_positions:
        lines.append(f"| {item['index']} | `{item['key']}` | {item['type']} | `{item['value']}` |")
    lines += [
        "",
        "## counts",
        f"- traceClassification.counts.tf_payloads={trace_class.get('counts', {}).get('tf_payloads')}",
        f"- traceClassification.counts.full_chain_tf_payload_events={trace_class.get('counts', {}).get('full_chain_tf_payload_events')}",
        f"- payloadChain.counts.tfPayloadEvents={payload_chain.get('counts', {}).get('tfPayloadEvents')}",
        f"- request308.markerMatch={request_308.get('markerMatch')}",
        f"- request308.jsonItemCount={request_308.get('jsonItemCount')}",
        "",
        "## local runtime boundary",
        "- runtime line 307: `hsprotect.Xn.trigger` channel `JDBeOmJSWwo=` stack includes `Iz/D/Ts` in `captcha.js`.",
        "- runtime line 308: POST `/assets/js/bundle`, decoded PX561 contains target keys.",
        "- runtime line 310: `/assets/js/bundle` response has `body_len=0` in current trace artifact.",
        "",
        "## findings",
    ]
    for finding in result["findings"]:
        lines.append(f"- {finding}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
