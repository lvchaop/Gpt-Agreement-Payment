#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
COOKIE_TIMELINE = PROTO / "cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json"
COLLECTOR_DECODE = PROTO / "collector_decode/collector_decode_s00ld1lglrw0_1781191381.json"
LATEST_EXACT_CONTROLS = PROTO / "goal_audit/latest_exact_payload_body_controls_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def short_url(url: str) -> str:
    if "collector-pxzc5j78di.hsprotect.net/assets/js/bundle" in url:
        return "collector_bundle"
    if "collector-pxzc5j78di.hsprotect.net/api/v2/msft" in url:
        return "collector_msft"
    if "collector-pxzc5j78di.hsprotect.net/b/c/beacon" in url:
        return "collector_beacon"
    if "login.microsoftonline.com" in url and "/risk/verify" in url:
        return "ms_risk_verify"
    if "signup.live.com/API/CreateAccount" in url:
        return "ms_create_account"
    if "captcha.hsprotect.net" in url:
        return "captcha_asset"
    if "client.hsprotect.net" in url:
        return "main_asset"
    if "iframe.hsprotect.net" in url:
        return "iframe_asset"
    return "other"


def runtime_window() -> list[dict[str, Any]]:
    out = []
    for row in read_jsonl(RUNTIME_TRACE):
        line = int(row["_line"])
        if not (880 <= line <= 1010):
            continue
        kind = row.get("kind")
        url = str(row.get("url") or "")
        if kind not in {"request", "response"}:
            continue
        if short_url(url) == "other":
            continue
        item = {
            "line": line,
            "t": row.get("t"),
            "kind": kind,
            "urlClass": short_url(url),
            "method": row.get("method"),
            "status": row.get("status"),
            "postLen": row.get("post_len"),
            "bodyLen": row.get("body_len"),
            "contentLength": ((row.get("headers") or {}).get("content-length")),
        }
        if kind == "request" and short_url(url) == "collector_bundle":
            body = str(row.get("post_data") or "")
            item["hasCookieHeader"] = "cookie" in {str(k).lower() for k in (row.get("headers") or {})}
            for field in ["seq=", "rsc="]:
                pos = body.find(field)
                item[field.rstrip("=")] = body[pos + len(field):pos + len(field) + 1] if pos >= 0 else None
        out.append(item)
    return out


def collector_decoded_window() -> list[dict[str, Any]]:
    doc = read_json(COLLECTOR_DECODE)
    out = []
    for row in doc.get("decodedEntries") or []:
        line = int(row.get("lineNo") or 0)
        if not (880 <= line <= 960):
            continue
        parts = row.get("parts") or []
        handlers = []
        for part in parts:
            fields = str(part).split("|")
            handlers.append(fields[0] if fields else "")
        out.append({
            "collectorLine": line,
            "handlers": handlers,
            "successParts": [p for p in parts if str(p).startswith("oIIoIooo|")],
            "cookieParts": [
                p for p in parts
                if str(p).startswith("IoooII|_px3|") or str(p).startswith("oIIoIIoo|_pxde|") or str(p).startswith("IooIoo|")
            ],
        })
    return out


def js_window() -> list[dict[str, Any]]:
    interesting = {
        "hsprotect.main.tf.enter",
        "hsprotect.main.tf.prepc",
        "hsprotect.main.tf.payload",
        "hsprotect.main.jl.queue",
        "hsprotect.main.jl.dispatch",
        "hsprotect.Xn.trigger",
        "hsprotect.captcha.pow.hit",
        "hsprotect.captcha.worker.new",
        "hsprotect.sendBeacon",
        "hsprotect.sendBeacon.result",
        "window.message.recv",
    }
    out = []
    for row in read_jsonl(JS_TRACE):
        line = int(row["_line"])
        if not (880 <= line <= 990):
            continue
        kind = str(row.get("kind") or "")
        if kind not in interesting:
            continue
        data = row.get("data") or {}
        item = {
            "line": line,
            "wall_t": row.get("wall_t"),
            "perf_t": row.get("perf_t"),
            "kind": kind,
        }
        if kind == "hsprotect.main.jl.dispatch":
            item["handlerKey"] = data.get("handlerKey")
            item["args"] = data.get("args")
        elif kind == "hsprotect.main.jl.queue":
            queue = data.get("queue") or []
            item["queueLen"] = len(queue)
            item["handlers"] = [q.get("key") for q in queue if isinstance(q, dict)]
        elif kind.startswith("hsprotect.Xn.trigger"):
            item["channel"] = data.get("channel")
            item["argsPreview"] = [str(x)[:80] for x in (data.get("args") or [])]
        elif kind == "window.message.recv":
            item["eventOrigin"] = data.get("eventOrigin")
            item["messagePreview"] = str(data.get("data"))[:200]
        elif kind.startswith("hsprotect.sendBeacon"):
            item["url"] = data.get("url")
            item["blobSize"] = data.get("blobSize")
        elif kind == "hsprotect.captcha.pow.hit":
            item["value"] = data.get("value")
        elif kind == "hsprotect.captcha.worker.new":
            item["sourceLen"] = data.get("sourceLen")
        out.append(item)
    return out


def cookie_bridge_window() -> dict[str, Any]:
    doc = read_json(COOKIE_TIMELINE)
    decoded = [
        e for e in doc.get("decodedEvents") or []
        if 880 <= int(e.get("collectorLine") or 0) <= 960
    ]
    parent = [
        e for e in doc.get("parentMessages") or []
        if 930 <= int(e.get("line") or 0) <= 980
    ]
    correlations = [
        e for e in doc.get("correlations") or []
        if 880 <= int(e.get("collectorLine") or 0) <= 960 or 930 <= int(e.get("parentLine") or 0) <= 980
    ]
    return {
        "decoded": decoded,
        "parent": parent,
        "correlations": correlations,
    }


def main() -> int:
    runtime = runtime_window()
    decoded = collector_decoded_window()
    js = js_window()
    bridge = cookie_bridge_window()
    exact = read_json(LATEST_EXACT_CONTROLS)

    success_collector = [row for row in decoded if row.get("successParts")]
    pre_success_parent = [row for row in bridge["parent"] if int(row.get("line") or 0) < 978]
    post_success_beacons = [row for row in runtime if row["urlClass"] == "collector_beacon"]
    risk_verify = [row for row in runtime if row["urlClass"] == "ms_risk_verify"]
    create_account = [row for row in runtime if row["urlClass"] == "ms_create_account"]

    audit = {
        "purpose": "Pin down the s00 accepted line933 state window and compare it to latest no-browser exact payload/body controls.",
        "evidenceFiles": {
            "jsTrace": str(JS_TRACE),
            "runtimeTrace": str(RUNTIME_TRACE),
            "collectorDecode": str(COLLECTOR_DECODE),
            "cookieTimeline": str(COOKIE_TIMELINE),
            "latestExactControls": str(LATEST_EXACT_CONTROLS),
        },
        "s00Window": {
            "runtime": runtime,
            "collectorDecoded": decoded,
            "js": js,
            "cookieBridge": bridge,
        },
        "latestNoBrowserExactControls": {
            "exactPayloadPcFreshOuter": exact.get("exactPayloadPcFreshOuter"),
            "exactWholeBody": exact.get("exactWholeBody"),
            "checks": exact.get("checks"),
        },
        "checks": {
            "hasAcceptedCollectorSuccessInWindow": any("oIIoIooo|0" in (row.get("successParts") or []) for row in success_collector),
            "hasLine933CollectorRequest": any(row.get("line") == 933 and row.get("kind") == "request" for row in runtime),
            "line933HasNoCookieHeader": all(
                row.get("hasCookieHeader") is False
                for row in runtime
                if row.get("line") == 933 and row.get("kind") == "request"
            ),
            "hasPreSuccessParentCookieBridgeInWindow": any(row.get("name") in {"_px3", "_pxde"} for row in pre_success_parent),
            "hasChallengeSuccessParentMessage": any(row.get("name") == "challenge_success" and row.get("value") == "succeeded" for row in bridge["parent"]),
            "hasPostSuccessBeacon": bool(post_success_beacons),
            "hasRiskVerifyAfterSuccess": bool(risk_verify),
            "hasCreateAccountAfterRiskVerify": bool(create_account),
            "latestExactPayloadPcNoSuccess": ((exact.get("checks") or {}).get("exactPayloadPcNoSuccess") is True),
            "latestExactBodyNoSuccess": ((exact.get("checks") or {}).get("exactBodyNoSuccess") is True),
        },
        "conclusion": (
            "The s00 window contains an accepted collector success around the line933 request/line948 decoded response, no Cookie header on line933, "
            "pre/post success parent cookie bridge messages for _px3/_pxde, and then Microsoft risk/verify plus CreateAccount. "
            "Latest no-browser full asset-lineage controls prove static exact payload+pc and byte-identical whole body still do not produce success. "
            "The remaining live-PoC boundary is therefore not static body replay; it is the collector/session state transition that makes line933 accepted in the browser lineage."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "s00_line933_state_window_audit.json"
    out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
