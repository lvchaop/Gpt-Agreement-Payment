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
OUT_DIR = REPO / "output/protocol_reverse/stk_ns_probe"
RUNTIME_STK_LINE = 28


def read_jsonl_line(path: Path, line_no: int) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if idx == line_no:
                row = json.loads(line)
                row["_line"] = idx
                return row
    raise KeyError(f"line not found: {path}:{line_no}")


def proxy_auth_header(proxy: urllib.parse.ParseResult) -> str | None:
    if proxy.username is None:
        return None
    import base64

    user = urllib.parse.unquote(proxy.username)
    password = urllib.parse.unquote(proxy.password or "")
    return "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")


def https_connection(
    parsed: urllib.parse.ParseResult,
    *,
    timeout: float,
    context: ssl.SSLContext,
    proxy_url: str | None,
) -> tuple[http.client.HTTPSConnection, dict[str, Any]]:
    if not proxy_url:
        return http.client.HTTPSConnection(parsed.netloc, timeout=timeout, context=context), {
            "mode": "direct",
            "target": parsed.netloc,
        }
    proxy = urllib.parse.urlparse(proxy_url)
    if proxy.scheme not in {"http", "https"} or not proxy.hostname:
        raise ValueError(f"unsupported proxy url: {proxy_url}")
    proxy_port = proxy.port or (443 if proxy.scheme == "https" else 80)
    target_port = parsed.port or 443
    conn = http.client.HTTPSConnection(proxy.hostname, proxy_port, timeout=timeout, context=context)
    tunnel_headers: dict[str, str] = {}
    auth = proxy_auth_header(proxy)
    if auth:
        tunnel_headers["Proxy-Authorization"] = auth
    conn.set_tunnel(parsed.hostname or parsed.netloc, target_port, headers=tunnel_headers)
    return conn, {
        "mode": "https-over-http-connect",
        "proxy": f"{proxy.scheme}://{proxy.hostname}:{proxy_port}",
        "target": f"{parsed.hostname}:{target_port}",
        "hasProxyAuthorization": auth is not None,
        "proxyUsername": urllib.parse.unquote(proxy.username) if proxy.username else None,
    }


def headers_from_runtime(row: dict[str, Any], *, include_proxy_authorization: bool) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in (row.get("headers") or {}).items():
        lower = str(name).lower()
        if lower in {"host", "content-length", "connection"}:
            continue
        if lower == "proxy-authorization" and not include_proxy_authorization:
            continue
        headers[str(name)] = str(value)
    headers["Host"] = "stk.hsprotect.net"
    return headers


def send_get(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"only https is supported: {url}")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    started = time.time()
    ctx = ssl.create_default_context()
    conn, transport = https_connection(parsed, timeout=timeout, context=ctx, proxy_url=os.environ.get("HSPROTECT_PROXY_URL"))
    try:
        conn.request("GET", path, headers=headers)
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
    parser = argparse.ArgumentParser(description="Send the stk.hsprotect.net/ns?c=<uuid> GET observed before s00 collector bootstrap.")
    parser.add_argument("--uuid", required=True)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    runtime = read_jsonl_line(RUNTIME_TRACE, RUNTIME_STK_LINE)
    url = f"https://stk.hsprotect.net/ns?c={urllib.parse.quote(str(args.uuid))}"
    headers = headers_from_runtime(runtime, include_proxy_authorization=args.include_proxy_authorization)
    started = time.time()
    result: dict[str, Any] = {
        "startedAt": started,
        "sent": bool(args.send),
        "source": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "runtimeStkLine": RUNTIME_STK_LINE,
        },
        "request": {
            "method": "GET",
            "url": url,
            "headers": headers,
            "includeProxyAuthorization": bool(args.include_proxy_authorization),
        },
        "checks": {
            "runtimeLineWasStkGet": runtime.get("method") == "GET" and "stk.hsprotect.net/ns" in str(runtime.get("url")),
            "urlUsesFreshUuid": str(args.uuid) in url,
        },
    }
    if args.send:
        try:
            result["response"] = send_get(url, headers, args.timeout)
            result["checks"]["httpStatusOk"] = result["response"].get("status") == 200
        except Exception as exc:
            result["error"] = str(exc)
            result["checks"]["httpStatusOk"] = False

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"stk_ns_probe_{args.uuid}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "sent": result["sent"],
        "status": (result.get("response") or {}).get("status"),
        "checks": result["checks"],
        "error": result.get("error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
