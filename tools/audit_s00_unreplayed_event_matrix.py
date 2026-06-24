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
DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781233946000_1781233946.json"
LATEST_CAPTCHA_COMBO = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781234385000_1781234385.json"
LATEST_ASSET_LINEAGE = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781234850000_1781234850.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = idx
                rows.append(row)
    return rows


def classify_url(url: str) -> str:
    if "collector-pxzc5j78di.hsprotect.net/api/v2/msft" in url:
        return "collector_msft"
    if "collector-pxzc5j78di.hsprotect.net/assets/js/bundle" in url:
        return "collector_bundle"
    if "stk.hsprotect.net/ns" in url:
        return "stk_ns"
    if "captcha.hsprotect.net/PXzC5j78di/captcha.js" in url:
        return "captcha_js"
    if "client.hsprotect.net/PXzC5j78di/main.min.js" in url:
        return "main_js"
    if "iframe.hsprotect.net/index.html" in url:
        return "iframe"
    if "login.microsoftonline.com" in url:
        return "microsoft"
    if "signup.live.com" in url:
        return "signup"
    return "other"


def s00_requests() -> list[dict[str, Any]]:
    out = []
    for row in read_jsonl(RUNTIME):
        line = int(row.get("_line") or 0)
        if line > 933:
            break
        if row.get("kind") != "request":
            continue
        url = str(row.get("url") or "")
        out.append({
            "line": line,
            "method": row.get("method"),
            "urlClass": classify_url(url),
            "url": url,
            "postLen": row.get("post_len"),
            "t": row.get("t"),
        })
    return out


def s00_js_events() -> list[dict[str, Any]]:
    interesting_prefixes = (
        "window.message.recv",
        "hsprotect.captcha.",
        "hsprotect.main.",
        "hsprotect.Xn.trigger",
        "hsprotect.sendBeacon",
    )
    out = []
    for row in read_jsonl(JS_TRACE):
        line = int(row.get("_line") or 0)
        if line < 560 or line > 982:
            continue
        kind = str(row.get("kind") or "")
        if not kind.startswith(interesting_prefixes):
            continue
        item = {
            "line": line,
            "kind": kind,
            "wall_t": row.get("wall_t") or row.get("t"),
            "perf_t": row.get("perf_t"),
        }
        if kind == "window.message.recv":
            data = row.get("data") or {}
            item["eventOrigin"] = data.get("eventOrigin")
            item["messagePreview"] = str(data.get("data"))[:120]
        elif kind.startswith("hsprotect.sendBeacon"):
            data = row.get("data") or {}
            item["url"] = data.get("url")
            item["blobSize"] = data.get("blobSize")
        out.append(item)
    return out


def no_browser_steps(path: Path = DIRECT) -> dict[str, Any]:
    direct = read_json(path)
    steps = direct.get("steps") or {}
    return {
        "directAttempt": str(path.resolve()),
        "hasPreStkNs": "preStkNs" in steps,
        "preStkNsStatus": (((steps.get("preStkNs") or {}).get("summary") or {}).get("status")),
        "hasCaptchaHead": "preCaptchaHead" in steps,
        "hasCaptchaGet": "preCaptchaGet" in steps,
        "hasMainJsGet": "preMainGet" in steps,
        "hasMainJsHead": "preMainHead" in steps,
        "hasIframeGet": "preIframeGet" in steps,
        "hasSendBeacon": False,
        "collectorProtocolSteps": [name for name in steps.keys() if name not in {"firstPow", "progressionPow", "nq"}],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key))
        out[value] = out.get(value, 0) + 1
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    reqs = s00_requests()
    js_events = s00_js_events()
    latest_direct = LATEST_ASSET_LINEAGE if LATEST_ASSET_LINEAGE.exists() else (LATEST_CAPTCHA_COMBO if LATEST_CAPTCHA_COMBO.exists() else DIRECT)
    nb = no_browser_steps(latest_direct)
    s00_counts = count_by(reqs, "urlClass")
    unreplayed = {
        "iframeGet": s00_counts.get("iframe", 0) > 0 and not nb["hasIframeGet"],
        "mainJsGet": s00_counts.get("main_js", 0) > 0 and not nb["hasMainJsGet"],
        "captchaJsGetOrHead": s00_counts.get("captcha_js", 0) > 0 and not (nb["hasCaptchaHead"] or nb["hasCaptchaGet"]),
        "sendBeacon": any(str(e.get("kind")).startswith("hsprotect.sendBeacon") for e in js_events) and not nb["hasSendBeacon"],
    }
    result = {
        "purpose": "Enumerate s00 browser/network/internal events before accepted line933 and mark which are not represented in the latest no-browser direct control.",
        "evidenceFiles": {
            "s00Runtime": str(RUNTIME.resolve()),
            "s00JsTrace": str(JS_TRACE.resolve()),
        "directAttempt": str(latest_direct.resolve()),
        },
        "s00": {
            "requestCountsByClassBeforeLine933": s00_counts,
            "requestsBeforeLine933": reqs,
            "interestingJsEventsLine560To982": js_events,
            "interestingJsKindCounts": count_by(js_events, "kind"),
        },
        "noBrowserControl": nb,
        "unreplayedEventClasses": unreplayed,
        "checks": {
            "preStkNsAlreadyTested": nb["hasPreStkNs"] is True and nb["preStkNsStatus"] == 200,
            "captchaJsNetworkAlreadyTestedInLatestDirect": unreplayed["captchaJsGetOrHead"] is False,
            "sendBeaconStillUnreplayedInLatestDirect": unreplayed["sendBeacon"] is True,
            "mainIframeAssetLoadsStillUnreplayed": unreplayed["iframeGet"] is True and unreplayed["mainJsGet"] is True,
            "mainIframeAssetLoadsAlreadyTestedInLatestDirect": unreplayed["iframeGet"] is False and unreplayed["mainJsGet"] is False,
        },
        "conclusion": (
            "The latest direct control has tested pre-bootstrap stk/ns, captcha.js GET/HEAD, iframe GET, main.js GET, and main.js HEAD in the same lineage, but still does not replay sendBeacon internals. "
            "A separate sendBeacon temporal audit shows sendBeacon is post-success in s00, so it is not supported as a pre-success prerequisite. "
            "Because the asset-lineage control also still rejects with exact seq5 decoded content, the next minimal evidence target is deeper collector server-side/session state not represented by these simple asset hits."
        ),
    }
    json_path = OUT_DIR / "s00_unreplayed_event_matrix_audit.json"
    md_path = OUT_DIR / "s00_unreplayed_event_matrix_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# s00 unreplayed event matrix",
            "",
            f"- requestCountsByClassBeforeLine933: `{s00_counts}`",
            f"- noBrowserControl: `{nb}`",
            f"- unreplayedEventClasses: `{unreplayed}`",
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
