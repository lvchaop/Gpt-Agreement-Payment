#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/s00_seq6_to_seq5_success_bridge_window_audit.json"

RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
DECODE = PROTO / "collector_decode/collector_decode_s00ld1lglrw0_1781191381.json"
TIMELINE = PROTO / "cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            out.append(row)
    return out


def compact_runtime(row: dict[str, Any]) -> dict[str, Any]:
    headers = row.get("headers") or {}
    return {
        key: value
        for key, value in {
            "line": row.get("_line"),
            "t": row.get("t"),
            "kind": row.get("kind"),
            "method": row.get("method"),
            "status": row.get("status"),
            "url": row.get("url"),
            "postLen": row.get("post_len"),
            "bodyLen": row.get("body_len"),
            "contentLength": headers.get("content-length"),
            "xFirefoxSpdy": headers.get("x-firefox-spdy"),
        }.items()
        if value not in (None, "")
    }


def compact_js(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data") or {}
    kind = str(row.get("kind") or "")
    item: dict[str, Any] = {
        "line": row.get("_line"),
        "wall_t": row.get("wall_t"),
        "perf_t": row.get("perf_t"),
        "kind": kind,
    }
    if kind == "window.message.recv":
        item.update({"eventOrigin": data.get("eventOrigin"), "data": data.get("data")})
    elif kind == "hsprotect.main.jl.dispatch":
        item.update({"handlerKey": data.get("handlerKey"), "args": data.get("args")})
    elif kind == "hsprotect.main.jl.queue":
        queue = data.get("queue") or []
        item.update({"handlers": [entry.get("key") for entry in queue if isinstance(entry, dict)]})
    elif kind.startswith("hsprotect.Xn.trigger"):
        item.update({"channel": data.get("channel"), "argsPreview": [str(arg)[:160] for arg in data.get("args") or []]})
    elif kind.startswith("hsprotect.sendBeacon"):
        item.update({"url": data.get("url"), "blobSize": data.get("blobSize"), "ok": data.get("ok")})
    return item


def decoded_window() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in (read_json(DECODE).get("decodedEntries") or []):
        line = int(entry.get("lineNo") or 0)
        if not (926 <= line <= 948):
            continue
        parts = entry.get("parts") or []
        out.append(
            {
                "collectorLine": line,
                "handlers": [str(part).split("|")[0] for part in parts],
                "successParts": [part for part in parts if str(part).startswith("oIIoIooo|")],
                "cookieParts": [
                    part
                    for part in parts
                    if str(part).startswith(("IoooII|_px3|", "oIIoIIoo|_pxde|", "IooIoo|"))
                ],
            }
        )
    return out


def main() -> int:
    runtime_rows = read_jsonl(RUNTIME)
    js_rows = read_jsonl(JS_TRACE)
    timeline = read_json(TIMELINE)

    runtime_window = [
        compact_runtime(row)
        for row in runtime_rows
        if 938 <= int(row.get("_line") or 0) <= 961 and row.get("kind") in {"request", "response"}
    ]
    js_window = [
        compact_js(row)
        for row in js_rows
        if 938 <= int(row.get("_line") or 0) <= 961
        and row.get("kind")
        in {
            "window.message.recv",
            "hsprotect.main.jl.dispatch",
            "hsprotect.main.jl.queue",
            "hsprotect.Xn.trigger",
            "hsprotect.Xn.trigger.result",
            "hsprotect.sendBeacon",
            "hsprotect.sendBeacon.result",
        }
    ]
    parent = [
        row
        for row in timeline.get("parentMessages") or []
        if 938 <= int(row.get("line") or 0) <= 961
    ]
    correlations = [
        row
        for row in timeline.get("correlations") or []
        if 926 <= int(row.get("collectorLine") or 0) <= 948 or 938 <= int(row.get("parentLine") or 0) <= 961
    ]

    runtime_requests = [row for row in runtime_window if row.get("kind") == "request"]
    runtime_responses = [row for row in runtime_window if row.get("kind") == "response"]
    parent_cookie_names = {row.get("name") for row in parent}
    line926_names = {
        str(part).split("|")[1]
        for row in decoded_window()
        if row.get("collectorLine") == 926
        for part in row.get("cookieParts") or []
        if len(str(part).split("|")) > 2
    }
    audit = {
        "purpose": "Pin down the narrow browser window from s00 seq6 response to accepted seq5 success response.",
        "evidenceFiles": {
            "runtimeTrace": str(RUNTIME),
            "jsTrace": str(JS_TRACE),
            "collectorDecode": str(DECODE),
            "cookieTimeline": str(TIMELINE),
        },
        "window": {
            "runtimeLineRange": [938, 961],
            "collectorDecodeLineRange": [926, 948],
            "runtime": runtime_window,
            "js": js_window,
            "decoded": decoded_window(),
            "parentMessages": parent,
            "correlations": correlations,
        },
        "checks": {
            "runtimeWindowHasNoRequests": len(runtime_requests) == 0,
            "runtimeWindowHasOnlySeq6AndSeq5Responses": len(runtime_responses) == 2
            and all("collector-pxzc5j78di.hsprotect.net/assets/js/bundle" in str(row.get("url") or "") for row in runtime_responses),
            "seq6ResponseBeforeSeq5Response": len(runtime_responses) == 2
            and int(runtime_responses[0].get("line") or 0) == 938
            and int(runtime_responses[1].get("line") or 0) == 961,
            "parentBridgeCarriesSeq6Px3Pxde": {"_px3", "_pxde"}.issubset(parent_cookie_names)
            and {"_px3", "_pxde"}.issubset(line926_names),
            "parentBridgeValuesCorrelateToLine926": all(
                row.get("valueMatch") is True
                for row in correlations
                if row.get("collectorLine") == 926 and row.get("name") in {"_px3", "_pxde"}
            )
            and sum(1 for row in correlations if row.get("collectorLine") == 926 and row.get("name") in {"_px3", "_pxde"}) == 2,
            "successLine948Observed": any("oIIoIooo|0" in (row.get("successParts") or []) for row in decoded_window()),
        },
        "conclusion": (
            "Between the s00 seq6 response at runtime line 938 and the accepted seq5 response at runtime line 961, the runtime trace contains no request events. "
            "The observable bridge is local JS/parent postMessage for _px3/_pxde, and those values correlate exactly to collector decoded line 926. "
            "Therefore current evidence does not support a missing network request between seq6 response and seq5 success; the remaining pure-protocol gap is earlier server/session lineage or hidden request material outside this narrow bridge window."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
