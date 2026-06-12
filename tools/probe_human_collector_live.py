#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import http.client
import json
import os
import ssl
import time
import urllib.parse
import zlib
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def tag_key(tag: str) -> int:
    value = 0
    for ch in tag:
        value = (31 * value + ord(ch)) % 2147483647
    return ((value % 900) + 100) % 128


def xor_string(value: str, key: int) -> str:
    return "".join(chr(ord(ch) ^ key) for ch in value)


def decode_collector_response(raw: str, tag: str) -> dict[str, Any]:
    json_value: Any = None
    mode = "encoded"
    try:
        json_value = json.loads(raw)
    except Exception:
        json_value = None
    if isinstance(json_value, dict) and (json_value.get("do") is not None or json_value.get("ob") is not None):
        inner = json_value.get("do") if json_value.get("do") is not None else json_value.get("ob")
        if not isinstance(inner, str):
            parts = inner if isinstance(inner, list) else [inner]
            return {
                "mode": "json-direct",
                "tag": tag,
                "key": tag_key(tag),
                "decoded": inner,
                "parts": parts,
                "handlers": [str(p).split("|")[0] for p in parts],
                "error": None,
            }
        raw = inner
        mode = "json-ob-encoded"
    key = tag_key(tag)
    try:
        binary = base64.b64decode(raw).decode("latin-1")
        decoded = xor_string(binary, key)
        parts = decoded.split("~~~~")
        return {
            "mode": mode,
            "tag": tag,
            "key": key,
            "decoded": decoded,
            "parts": parts,
            "handlers": [str(p).split("|")[0] for p in parts],
            "hasSuccessHandler": any(str(p) == "oIIoIooo|0" or str(p).startswith("oIIoIooo|0|") for p in parts),
            "hasPx3": any(str(p).startswith("IoooII|_px3|") for p in parts),
            "hasPxde": any(str(p).startswith("oIIoIIoo|_pxde|") for p in parts),
            "hasPowResult": any(str(p).startswith("IooIIo|") for p in parts),
            "error": None,
        }
    except Exception as exc:
        return {
            "mode": mode,
            "tag": tag,
            "key": key,
            "decoded": None,
            "parts": [],
            "handlers": [],
            "error": str(exc),
        }


def base_from_request_build(path: Path) -> str:
    return (
        path.name.removeprefix("collector_request_build_")
        .removeprefix("bundle_request_build_")
        .removesuffix(".json")
    )


def headers_from_runtime(
    row: dict[str, Any],
    *,
    body: str,
    url: str,
    include_proxy_authorization: bool,
    header_mode: str = "safe",
) -> dict[str, str]:
    parsed = urllib.parse.urlparse(url)
    headers: dict[str, str] = {}
    runtime_exact = header_mode == "runtime-exact"
    # Keep runtime order as much as Python dict preserves insertion order from JSON.
    runtime = row.get("runtimeHeaders") or row.get("headers") or {}
    for name, value in runtime.items():
        lower = str(name).lower()
        if runtime_exact and lower == "host":
            headers[name] = parsed.netloc
            continue
        if runtime_exact and lower == "content-length":
            headers[name] = str(len(body.encode("utf-8")))
            continue
        if runtime_exact and lower == "content-type":
            headers[name] = "application/x-www-form-urlencoded"
            continue
        if lower in {"host", "content-length"}:
            continue
        if lower == "connection" and not runtime_exact:
            continue
        if lower == "proxy-authorization" and not include_proxy_authorization:
            continue
        # stdlib cannot decode zstd/br; request gzip/deflate only unless this is a header-parity control.
        if lower == "accept-encoding" and not runtime_exact:
            headers[name] = "gzip, deflate"
            continue
        headers[name] = str(value)
    if not any(k.lower() == "host" for k in headers):
        headers["Host"] = parsed.netloc
    if not any(k.lower() == "content-type" for k in headers):
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if not any(k.lower() == "content-length" for k in headers):
        headers["Content-Length"] = str(len(body.encode("utf-8")))
    return headers


def find_runtime_request(runtime_path: Path, request_line: int) -> dict[str, Any] | None:
    with runtime_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line_no != request_line:
                continue
            row = json.loads(line)
            row["_line"] = line_no
            return row
    return None


def decompress_body(body: bytes, encoding: str) -> bytes:
    enc = encoding.lower()
    if "gzip" in enc:
        return gzip.decompress(body)
    if "deflate" in enc:
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def _proxy_auth_header(proxy: urllib.parse.ParseResult) -> str | None:
    if proxy.username is None:
        return None
    user = urllib.parse.unquote(proxy.username)
    password = urllib.parse.unquote(proxy.password or "")
    return "Basic " + base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")


def _https_connection(
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
    auth = _proxy_auth_header(proxy)
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


def send_https(url: str, headers: dict[str, str], body: str, timeout: float, proxy_url: str | None = None) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"only https is supported: {url}")
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    started = time.time()
    ctx = ssl.create_default_context()
    effective_proxy_url = proxy_url or os.environ.get("HSPROTECT_PROXY_URL")
    conn, transport = _https_connection(parsed, timeout=timeout, context=ctx, proxy_url=effective_proxy_url)
    try:
        conn.request("POST", path, body=body.encode("utf-8"), headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        response_headers = {k.lower(): v for k, v in resp.getheaders()}
        decoded_bytes = decompress_body(raw, response_headers.get("content-encoding", ""))
        elapsed = time.time() - started
        return {
            "status": resp.status,
            "reason": resp.reason,
            "headers": response_headers,
            "rawBodyLen": len(raw),
            "bodyLen": len(decoded_bytes),
            "bodyText": decoded_bytes.decode("utf-8", errors="replace"),
            "elapsedSeconds": elapsed,
            "transport": transport,
        }
    finally:
        conn.close()


def build_probe(
    request_build_path: Path,
    index: int,
    *,
    include_proxy_authorization: bool,
    body_override_path: Path | None = None,
) -> dict[str, Any]:
    build = read_json(request_build_path)
    rows = build.get("rows") or []
    if index < 0 or index >= len(rows):
        raise IndexError(f"request index out of range: {index}; rows={len(rows)}")
    row = rows[index]
    evidence = build.get("evidenceFiles") or {}
    runtime_path = Path(build.get("runtimePath") or evidence.get("runtimeTrace") or "")
    if runtime_path and not runtime_path.is_absolute():
        runtime_path = REPO / runtime_path
    runtime_req = find_runtime_request(runtime_path, int(row.get("requestLine") or 0)) or {}
    body_source = "request_build.rebuiltBody"
    body = row.get("rebuiltBody") or row.get("observedBody") or runtime_req.get("post_data") or ""
    override_doc = None
    if body_override_path:
        override_doc = read_json(body_override_path)
        body = (
            override_doc.get("body")
            or ((override_doc.get("experimental") or {}).get("body") if isinstance(override_doc.get("experimental"), dict) else None)
            or body
        )
        body_source = str(body_override_path)
    url = row.get("url") or runtime_req.get("url")
    headers = headers_from_runtime(runtime_req, body=body, url=url, include_proxy_authorization=include_proxy_authorization)
    return {
        "base": base_from_request_build(request_build_path),
        "requestBuildPath": str(request_build_path),
        "runtimePath": str(runtime_path),
        "index": index,
        "requestLine": row.get("requestLine"),
        "runtimeStatus": None,
        "url": url,
        "method": "POST",
        "headers": headers,
        "body": body,
        "bodySha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "bodyLenBytes": len(body.encode("utf-8")),
        "source": {
            "bodySource": body_source,
            "bodyExactMatch": row.get("exactBodyMatch") if row.get("exactBodyMatch") is not None else row.get("bodyMatch"),
            "markerSource": row.get("markerSource"),
            "markerQi": row.get("markerQi"),
            "runtimeHeaderLine": runtime_req.get("_line"),
            "includeProxyAuthorization": include_proxy_authorization,
            "bodyOverrideSummary": {
                "liveProbePath": override_doc.get("liveProbePath"),
                "newMarker": override_doc.get("newMarker"),
                "liveState": override_doc.get("liveState"),
            } if override_doc else None,
        },
    }


def write_outputs(result: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = result["probe"]["base"]
    idx = result["probe"]["index"]
    ts = int(result["startedAt"])
    stem = f"collector_live_probe_{base}_idx{idx}_{ts}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    decoded = result.get("decoded") or {}
    response = result.get("response") or {}
    lines = [
        f"# collector live probe: {base} idx={idx}",
        "",
        f"requestBuild={result['probe']['requestBuildPath']}",
        f"runtime={result['probe']['runtimePath']}",
        f"url={result['probe']['url']}",
        f"sent={result['sent']}",
        f"error={result.get('error') or ''}",
        "",
        "## request",
        f"- bodyLenBytes: {result['probe']['bodyLenBytes']}",
        f"- bodySha256: {result['probe']['bodySha256']}",
        f"- bodyExactMatchInRuntime: {result['probe']['source'].get('bodyExactMatch')}",
        f"- markerSource: {result['probe']['source'].get('markerSource')}",
        f"- markerQi: {result['probe']['source'].get('markerQi')}",
        "",
        "## response",
        f"- status: {response.get('status')}",
        f"- reason: {response.get('reason')}",
        f"- rawBodyLen: {response.get('rawBodyLen')}",
        f"- bodyLen: {response.get('bodyLen')}",
        f"- elapsedSeconds: {response.get('elapsedSeconds')}",
        "",
        "## decoded",
        f"- mode: {decoded.get('mode')}",
        f"- key: {decoded.get('key')}",
        f"- partCount: {len(decoded.get('parts') or [])}",
        f"- handlers: {', '.join(decoded.get('handlers') or [])}",
        f"- hasSuccessHandler: {decoded.get('hasSuccessHandler')}",
        f"- hasPx3: {decoded.get('hasPx3')}",
        f"- hasPxde: {decoded.get('hasPxde')}",
        f"- hasPowResult: {decoded.get('hasPowResult')}",
        f"- decodeError: {decoded.get('error')}",
        "",
        "## response body preview",
        "```text",
        str(response.get("bodyText") or "")[:4000],
        "```",
        "",
        "## boundary",
        "- This probe proves only the observed response for this explicit POST material and current transport.",
        "- It does not prove a fresh end-to-end pure-protocol HUMAN success unless decoded has `oIIoIooo|0` and the subsequent Microsoft risk/verify flow is replayed.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Send a replay-built HUMAN collector POST and decode the live response.")
    parser.add_argument("request_build", type=Path)
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--tag", default="YjIYfyxJHRR9")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--send", action="store_true", help="Actually send the HTTPS POST. Without this, only material is written.")
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--body-override-json", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse/collector_live_probe")
    args = parser.parse_args()

    started = time.time()
    probe = build_probe(
        args.request_build,
        args.index,
        include_proxy_authorization=args.include_proxy_authorization,
        body_override_path=args.body_override_json,
    )
    result: dict[str, Any] = {"startedAt": started, "sent": bool(args.send), "probe": probe}
    if args.send:
        try:
            response = send_https(probe["url"], probe["headers"], probe["body"], args.timeout)
            result["response"] = response
            result["decoded"] = decode_collector_response(response.get("bodyText") or "", args.tag)
        except Exception as exc:
            result["error"] = str(exc)
    else:
        result["response"] = None
        result["decoded"] = None
    json_path, md_path = write_outputs(result, args.out_dir)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "sent": result["sent"], "status": (result.get("response") or {}).get("status"), "decode": result.get("decoded")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
