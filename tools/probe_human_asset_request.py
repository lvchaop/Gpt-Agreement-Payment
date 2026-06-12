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
OUT_DIR = REPO / "output/protocol_reverse/asset_request_probe"
APP_ID = "PXzC5j78di"


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
    for key in ["finalState", "freshState"]:
        state = dict(doc.get(key) or {})
        if state:
            return state
    state = dict((doc.get("material") or {}).get("freshState") or {})
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
    return headers


def patched_url(runtime_url: str, state: dict[str, Any]) -> str:
    parsed = urllib.parse.urlparse(runtime_url)
    if parsed.netloc == "iframe.hsprotect.net":
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        patched: list[tuple[str, str]] = []
        for key, value in query:
            if key == "session_id" and state.get("sid"):
                patched.append((key, str(state["sid"])))
            else:
                patched.append((key, value))
        if not any(k == "app_id" for k, _ in patched):
            patched.insert(0, ("app_id", APP_ID))
        return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(patched)))
    return runtime_url


def send_request(method: str, url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"only https is supported: {url}")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    headers = dict(headers)
    headers["Host"] = parsed.netloc
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
    parser = argparse.ArgumentParser(description="Replay a hsprotect iframe/client asset request from s00 with fresh state cookies/session.")
    parser.add_argument("--state-probe", type=Path, required=True)
    parser.add_argument("--runtime-line", type=int, required=True)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    state = state_from_probe(args.state_probe)
    runtime = read_jsonl_line(RUNTIME_TRACE, args.runtime_line)
    runtime_url = str(runtime.get("url") or "")
    url = patched_url(runtime_url, state)
    headers = headers_from_runtime(runtime, include_proxy_authorization=args.include_proxy_authorization, state=state)
    method = str(runtime.get("method") or "GET")
    started = time.time()
    runtime_cookie = str((runtime.get("headers") or {}).get("cookie") or "")
    request_cookie = str(headers.get("cookie") or headers.get("Cookie") or "")
    result: dict[str, Any] = {
        "startedAt": started,
        "sent": bool(args.send),
        "source": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "runtimeLine": args.runtime_line,
            "stateProbe": str(args.state_probe),
            "runtimeUrl": runtime_url,
        },
        "state": {k: state.get(k) for k in ["uuid", "sid", "vid", "cts", "px3", "pxde"]},
        "request": {
            "method": method,
            "url": url,
            "headers": headers,
            "includeProxyAuthorization": bool(args.include_proxy_authorization),
        },
        "checks": {
            "runtimeLineHadMethod": bool(runtime.get("method")),
            "runtimeHadCookieHeader": bool(runtime_cookie),
            "requestCookieUsesFreshPx3": (not state.get("px3")) or (str(state.get("px3")) in request_cookie),
            "requestCookieUsesFreshPxvid": (not state.get("vid")) or (str(state.get("vid")) in request_cookie),
            "requestCookieAvoidsRuntimeCookie": (not runtime_cookie) or (runtime_cookie != request_cookie) or (str(state.get("px3") or "") in runtime_cookie),
            "iframeUrlUsesFreshSid": ("iframe.hsprotect.net" not in url) or (not state.get("sid")) or (str(state.get("sid")) in url),
        },
    }
    if args.send:
        try:
            result["response"] = send_request(method, url, headers, args.timeout)
            result["checks"]["httpStatusOkOrCacheable"] = result["response"].get("status") in {200, 204, 304}
        except Exception as exc:
            result["error"] = str(exc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    suffix = urllib.parse.urlparse(url).netloc.split(".")[0] or "asset"
    out = args.out_dir / f"asset_request_probe_line{args.runtime_line}_{suffix}_{state.get('uuid', 'no-uuid')}_{int(started)}.json"
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
