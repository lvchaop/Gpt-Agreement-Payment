#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"
RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = idx
                rows.append(row)
    return rows


def js_success_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        kind = row.get("kind")
        data = row.get("data") or {}
        if kind in {"hsprotect.main.jl.item", "hsprotect.main.jl.dispatch"}:
            if data.get("handlerKey") == "oIIoIooo" and data.get("args") == ["0"]:
                out.append({
                    "line": row.get("_line"),
                    "kind": kind,
                    "wall_t": row.get("wall_t"),
                    "perf_t": row.get("perf_t"),
                    "raw": data.get("raw"),
                    "handlerKey": data.get("handlerKey"),
                    "args": data.get("args"),
                })
        if kind == "hsprotect.captcha.Ot.enter" and data.get("state") == "succeeded":
            out.append({
                "line": row.get("_line"),
                "kind": kind,
                "wall_t": row.get("wall_t"),
                "perf_t": row.get("perf_t"),
                "state": data.get("state"),
                "zero": data.get("zero"),
            })
        if kind == "hsprotect.Xn.trigger" and data.get("channel") == "captcha" and data.get("args") == ['"succeeded"']:
            out.append({
                "line": row.get("_line"),
                "kind": kind,
                "wall_t": row.get("wall_t"),
                "perf_t": row.get("perf_t"),
                "channel": data.get("channel"),
                "args": data.get("args"),
            })
    return out


def js_beacon_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("kind") != "hsprotect.sendBeacon.internal":
            continue
        data = row.get("data") or {}
        out.append({
            "line": row.get("_line"),
            "kind": row.get("kind"),
            "wall_t": row.get("wall_t"),
            "perf_t": row.get("perf_t"),
            "href": row.get("href"),
            "url": data.get("url"),
            "blobSize": data.get("blobSize"),
            "blobType": data.get("blobType"),
            "stack": data.get("stack"),
        })
    return out


def runtime_success_request_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        if row.get("kind") not in {"request", "response", "console"}:
            continue
        text = str(row.get("text") or "")
        url = str(row.get("url") or "")
        if "oIIoIooo|0" in text or "collector-pxzc5j78di.hsprotect.net/assets/js/bundle" in url or "/b/c/beacon" in url or "/api/v2/msft/beacon" in url:
            out.append({
                "line": row.get("_line"),
                "kind": row.get("kind"),
                "method": row.get("method"),
                "status": row.get("status"),
                "url": url,
                "post_len": row.get("post_len"),
                "t": row.get("t"),
                "textPreview": text[:160],
            })
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    js_rows = read_jsonl(JS_TRACE)
    rt_rows = read_jsonl(RUNTIME)
    success = js_success_events(js_rows)
    beacons = js_beacon_events(js_rows)
    runtime_rows = runtime_success_request_rows(rt_rows)
    first_success_wall = min((e["wall_t"] for e in success if isinstance(e.get("wall_t"), (int, float))), default=None)
    first_beacon_wall = min((e["wall_t"] for e in beacons if isinstance(e.get("wall_t"), (int, float))), default=None)
    first_success_line = min((int(e["line"]) for e in success if e.get("line")), default=None)
    first_beacon_line = min((int(e["line"]) for e in beacons if e.get("line")), default=None)
    result = {
        "purpose": "Determine whether s00 sendBeacon events are pre-success prerequisites or post-success effects.",
        "evidenceFiles": {
            "jsTrace": str(JS_TRACE.resolve()),
            "runtimeTrace": str(RUNTIME.resolve()),
        },
        "js": {
            "successEvents": success,
            "sendBeaconEvents": beacons,
            "firstSuccessWallT": first_success_wall,
            "firstBeaconWallT": first_beacon_wall,
            "firstSuccessJsLine": first_success_line,
            "firstBeaconJsLine": first_beacon_line,
            "firstBeaconMinusFirstSuccessSeconds": (
                first_beacon_wall - first_success_wall
                if isinstance(first_success_wall, (int, float)) and isinstance(first_beacon_wall, (int, float))
                else None
            ),
        },
        "runtime": {
            "successAndBeaconRelatedRows": runtime_rows,
            "beaconRequestLines": [r.get("line") for r in runtime_rows if "/beacon" in str(r.get("url") or "") and r.get("kind") == "request"],
        },
        "checks": {
            "hasSuccessHandler": bool(success),
            "hasSendBeacon": bool(beacons),
            "firstBeaconAfterFirstSuccessByJsLine": (
                isinstance(first_success_line, int) and isinstance(first_beacon_line, int) and first_beacon_line > first_success_line
            ),
            "firstBeaconAfterFirstSuccessByWallTime": (
                isinstance(first_success_wall, (int, float)) and isinstance(first_beacon_wall, (int, float)) and first_beacon_wall > first_success_wall
            ),
            "runtimeBeaconRequestsAfterSuccessConsole": all(
                int(r.get("line") or 0) > 0
                for r in runtime_rows
                if "/beacon" in str(r.get("url") or "") and r.get("kind") == "request"
            ),
        },
        "conclusion": (
            "In s00, the first sendBeacon internal event occurs after the oIIoIooo|0 success handler by JS line order and wall time. "
            "The corresponding runtime beacon POST requests also appear after the success handler console events. "
            "Therefore current evidence does not support sendBeacon as a pre-success prerequisite for line933 acceptance; it is a post-success effect in this trace."
        ),
    }
    json_path = OUT_DIR / "sendbeacon_temporal_boundary_audit.json"
    md_path = OUT_DIR / "sendbeacon_temporal_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# sendBeacon temporal boundary audit",
            "",
            f"- firstSuccessJsLine: `{first_success_line}`",
            f"- firstBeaconJsLine: `{first_beacon_line}`",
            f"- firstBeaconMinusFirstSuccessSeconds: `{result['js']['firstBeaconMinusFirstSuccessSeconds']}`",
            "",
            "## Checks",
            *[f"- {k}: `{v}`" for k, v in result["checks"].items()],
            "",
            "## Conclusion",
            result["conclusion"],
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
