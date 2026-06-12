#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import time
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
OUT_DIR = REPO / "output/protocol_reverse/captcha_head_probe"
RUNTIME_HEAD_LINE = 692
RUNTIME_GET_LINE = 181


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_line(path: Path, line_no: int) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if idx == line_no:
                row = json.loads(line)
                row["_line"] = idx
                return row
    raise KeyError(f"line not found: {path}:{line_no}")


def state_from_probe(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    state = dict(doc.get("finalState") or {})
    if state:
        return state
    state = dict((doc.get("material") or {}).get("freshState") or {})
    if state:
        return state
    state = dict(doc.get("freshState") or {})
    if state:
        return state
    raise RuntimeError(f"no state found in {path}")


def cookie_header_from_state(state: dict[str, Any]) -> str:
    parts: list[str] = []
    if state.get("px3"):
        parts.append(f"_px3={state['px3']}")
    if state.get("cts"):
        parts.append(f"pxcts={state['cts']}")
    if state.get("vid"):
        parts.append(f"_pxvid={state['vid']}")
    if state.get("pxde"):
        parts.append(f"_pxde={state['pxde']}")
    return "; ".join(parts)


def headers_from_runtime(row: dict[str, Any], *, include_proxy_authorization: bool, state: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in (row.get("headers") or {}).items():
        lower = str(name).lower()
        if lower in {"host", "content-length", "connection"}:
            continue
        if lower == "proxy-authorization" and not include_proxy_authorization:
            continue
        if lower == "accept-encoding":
            headers[name] = "gzip, deflate"
            continue
        if lower == "cookie":
            fresh_cookie = cookie_header_from_state(state)
            if fresh_cookie:
                headers[name] = fresh_cookie
            continue
        headers[name] = str(value)
    headers["Host"] = "captcha.hsprotect.net"
    return headers


def send_request(method: str, url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"only https is supported: {url}")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    started = time.time()
    ctx = ssl.create_default_context()
    proxy_url = os.environ.get("HSPROTECT_PROXY_URL")
    transport: dict[str, Any] = {"mode": "direct", "target": parsed.netloc}
    if proxy_url:
        from probe_human_collector_live import _https_connection

        conn, transport = _https_connection(parsed, timeout=timeout, context=ctx, proxy_url=proxy_url)
    else:
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=timeout, context=ctx)
    try:
        conn.request(method, path, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        return {
            "status": resp.status,
            "reason": resp.reason,
            "headers": {k.lower(): v for k, v in resp.getheaders()},
            "rawBodyLen": len(raw),
            "bodyPreview": raw[:200].decode("utf-8", errors="replace"),
            "elapsedSeconds": time.time() - started,
            "transport": transport,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Send the captcha.js GET/HEAD request observed before s00 success, patched to a fresh uuid/vid.")
    parser.add_argument("--state-probe", type=Path, required=True)
    parser.add_argument("--method", choices=["GET", "HEAD"], default="HEAD")
    parser.add_argument("--runtime-line", type=int, default=None)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    state = state_from_probe(args.state_probe)
    runtime_line = args.runtime_line or (RUNTIME_GET_LINE if args.method == "GET" else RUNTIME_HEAD_LINE)
    runtime = read_jsonl_line(RUNTIME_TRACE, runtime_line)
    uuid_value = state.get("uuid")
    vid = state.get("vid")
    if not uuid_value or not vid:
        raise RuntimeError("state lacks uuid or vid")
    url = f"https://captcha.hsprotect.net/PXzC5j78di/captcha.js?a=c&m=0&u={urllib.parse.quote(str(uuid_value))}&v={urllib.parse.quote(str(vid))}"
    headers = headers_from_runtime(runtime, include_proxy_authorization=args.include_proxy_authorization, state=state)
    started = time.time()
    result: dict[str, Any] = {
        "startedAt": started,
        "sent": bool(args.send),
        "source": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "runtimeLine": runtime_line,
            "stateProbe": str(args.state_probe),
        },
        "state": {k: state.get(k) for k in ["uuid", "vid", "p1", "jo", "ci", "cs"]},
        "request": {
            "method": args.method,
            "url": url,
            "headers": headers,
            "includeProxyAuthorization": bool(args.include_proxy_authorization),
        },
        "checks": {
            "runtimeLineWasExpectedMethod": runtime.get("method") == args.method,
            "urlUsesFreshUuid": str(uuid_value) in url,
            "urlUsesFreshVid": str(vid) in url,
            "runtimeHadCookieHeader": any(str(k).lower() == "cookie" for k in (runtime.get("headers") or {})),
            "requestCookieUsesFreshPx3": (not state.get("px3")) or (str(state.get("px3")) in str(headers.get("cookie") or headers.get("Cookie") or "")),
            "requestCookieUsesFreshPxvid": (not state.get("vid")) or (str(state.get("vid")) in str(headers.get("cookie") or headers.get("Cookie") or "")),
            "requestCookieAvoidsRuntimePx3": (not (runtime.get("headers") or {}).get("cookie")) or (str(state.get("px3")) in str((runtime.get("headers") or {}).get("cookie"))) or (str((runtime.get("headers") or {}).get("cookie")) != str(headers.get("cookie") or headers.get("Cookie") or "")),
        },
    }
    if args.send:
        try:
            result["response"] = send_request(args.method, url, headers, args.timeout)
            result["checks"]["httpStatusOkOrCacheable"] = result["response"].get("status") in {200, 204, 304}
        except Exception as exc:
            result["error"] = str(exc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"captcha_{args.method.lower()}_probe_{uuid_value}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "sent": result["sent"],
        "status": (result.get("response") or {}).get("status"),
        "checks": result.get("checks"),
        "error": result.get("error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
