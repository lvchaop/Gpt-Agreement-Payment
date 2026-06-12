#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import importlib.util
import json
import os
import socket
import ssl
import threading
import time
import urllib.parse
import zlib
from pathlib import Path
from typing import Any

import h2.connection
import h2.events
import h2.config


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PX_TOOL = REPO / "tools/probe_human_fresh_px561.py"
PROGRESSION_TOOL = REPO / "tools/probe_human_fresh_bundle_progression.py"
LIVE_PROBE = REPO / "tools/probe_human_collector_live.py"
OUT_DIR = REPO / "output/protocol_reverse/seq5_seq6_combo_probe"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_material(px: Any, *, template_line: int, seq: str, rsc: str, runtime_line: int, args: argparse.Namespace) -> dict[str, Any]:
    return px.build_material(
        send=True,
        include_proxy_authorization=args.include_proxy_authorization,
        header_mode=args.header_mode,
        aeax_source=args.aeax_source,
        bzt_source=args.bzt_source,
        bzt_value=args.bzt_value,
        template_line=template_line,
        runtime_line=runtime_line,
        seq=seq,
        rsc=rsc,
        state_probe=args.state_probe,
        fresh_bundle=args.fresh_bundle,
        pow_json=args.pow_json,
        nq_json=args.nq_json,
        ng_nq_json=args.ng_nq_json,
        stack_source=args.stack_source,
        tail_source=args.tail_source,
        inner_uuid_source=args.inner_uuid_source,
        non_px_activity_source=args.non_px_activity_source,
        payload_uuid_source=args.payload_uuid_source,
        pc_uuid_source=args.pc_uuid_source,
        marker_source=args.marker_source,
        form_outer_source=args.form_outer_source,
        payload_source=args.payload_source,
        pc_source=args.pc_source,
        body_source=args.body_source,
    )


def build_seq6_material(prog: Any, *, args: argparse.Namespace) -> dict[str, Any]:
    state = prog.state_from_state_probe(args.state_probe) if args.state_probe else prog.state_from_bundle(read_json(args.fresh_bundle))
    return prog.build_request(
        {"name": "bundle_seq6", "jsLine": 925, "runtimeLine": 937, "seq": "6", "rsc": "7", "activityCount": 1},
        state,
        include_proxy_authorization=args.include_proxy_authorization,
        header_mode=args.header_mode,
        activity_source=args.seq6_activity_source,
    )


def send_one(live: Any, name: str, material: dict[str, Any], timeout: float, out: dict[str, Any]) -> None:
    started = time.time()
    row: dict[str, Any] = {"startedAt": started, "material": material}
    try:
        response = live.send_https(material["url"], material["headers"], material["body"], timeout)
        row["response"] = response
        row["decoded"] = live.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
    except Exception as exc:
        row["error"] = str(exc)
    row["endedAt"] = time.time()
    out[name] = row


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


def proxy_auth_header(proxy: urllib.parse.ParseResult) -> str | None:
    if proxy.username is None:
        return None
    user = urllib.parse.unquote(proxy.username)
    password = urllib.parse.unquote(proxy.password or "")
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode("ascii")


def open_h2_socket(url: str, timeout: float) -> tuple[ssl.SSLSocket, dict[str, Any]]:
    parsed = urllib.parse.urlparse(url)
    target_host = parsed.hostname or parsed.netloc
    target_port = parsed.port or 443
    proxy_url = os.environ.get("HSPROTECT_PROXY_URL")
    transport: dict[str, Any] = {"mode": "h2-direct", "target": f"{target_host}:{target_port}"}
    if proxy_url:
        proxy = urllib.parse.urlparse(proxy_url)
        if proxy.scheme not in {"http", "https"} or not proxy.hostname:
            raise ValueError(f"unsupported proxy url: {proxy_url}")
        proxy_port = proxy.port or (443 if proxy.scheme == "https" else 80)
        raw = socket.create_connection((proxy.hostname, proxy_port), timeout=timeout)
        raw.settimeout(timeout)
        auth = proxy_auth_header(proxy)
        lines = [
            f"CONNECT {target_host}:{target_port} HTTP/1.1",
            f"Host: {target_host}:{target_port}",
        ]
        if auth:
            lines.append(f"Proxy-Authorization: {auth}")
        lines.extend(["", ""])
        raw.sendall("\r\n".join(lines).encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = raw.recv(4096)
            if not chunk:
                break
            buf += chunk
        status_line = buf.split(b"\r\n", 1)[0].decode("latin-1", errors="replace")
        if " 200 " not in status_line:
            raw.close()
            raise RuntimeError(f"proxy CONNECT failed: {status_line}")
        transport = {
            "mode": "h2-over-http-connect",
            "proxy": f"{proxy.scheme}://{proxy.hostname}:{proxy_port}",
            "target": f"{target_host}:{target_port}",
            "hasProxyAuthorization": auth is not None,
            "proxyUsername": urllib.parse.unquote(proxy.username) if proxy.username else None,
        }
    else:
        raw = socket.create_connection((target_host, target_port), timeout=timeout)
        raw.settimeout(timeout)
    ctx = ssl.create_default_context()
    ctx.set_alpn_protocols(["h2"])
    tls = ctx.wrap_socket(raw, server_hostname=target_host)
    transport["alpn"] = tls.selected_alpn_protocol()
    if transport["alpn"] != "h2":
        tls.close()
        raise RuntimeError(f"server did not negotiate h2: {transport['alpn']}")
    return tls, transport


def h2_headers(material: dict[str, Any]) -> list[tuple[str, str]]:
    parsed = urllib.parse.urlparse(material["url"])
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    out = [
        (":method", "POST"),
        (":scheme", "https"),
        (":authority", parsed.netloc),
        (":path", path),
    ]
    for name, value in (material.get("headers") or {}).items():
        lower = str(name).lower()
        if lower in {"host", "connection", "proxy-authorization", "transfer-encoding"}:
            continue
        out.append((lower, str(value)))
    return out


def send_h2_pair(
    live: Any,
    seq5: dict[str, Any],
    seq6: dict[str, Any],
    timeout: float,
    gap_seconds: float,
    h2_body_order: str = "normal",
) -> dict[str, Any]:
    started = time.time()
    sock, transport = open_h2_socket(seq5["url"], timeout)
    config = h2.config.H2Configuration(client_side=True, header_encoding="utf-8")
    conn = h2.connection.H2Connection(config=config)
    streams: dict[int, str] = {}
    results: dict[str, Any] = {
        "seq5": {"startedAt": None, "endedAt": None, "material": seq5},
        "seq6": {"startedAt": None, "endedAt": None, "material": seq6},
    }
    response_headers: dict[int, list[tuple[str, str]]] = {}
    response_body: dict[int, bytearray] = {}
    response_done: set[int] = set()

    def send_body(stream_id: int, body: bytes) -> None:
        max_frame = min(conn.max_outbound_frame_size, conn.local_flow_control_window(stream_id), 16384)
        offset = 0
        if not body:
            conn.end_stream(stream_id)
            return
        while offset < len(body):
            chunk = body[offset:offset + max_frame]
            offset += len(chunk)
            conn.send_data(stream_id, chunk, end_stream=offset >= len(body))

    try:
        conn.initiate_connection()
        sock.sendall(conn.data_to_send())

        stream5 = conn.get_next_available_stream_id()
        streams[stream5] = "seq5"
        results["seq5"]["startedAt"] = time.time()
        body5 = seq5["body"].encode("utf-8")
        conn.send_headers(stream5, h2_headers(seq5), end_stream=False)
        if h2_body_order == "normal":
            send_body(stream5, body5)
        sock.sendall(conn.data_to_send())

        if gap_seconds > 0:
            time.sleep(gap_seconds)

        stream6 = conn.get_next_available_stream_id()
        streams[stream6] = "seq6"
        results["seq6"]["startedAt"] = time.time()
        body6 = seq6["body"].encode("utf-8")
        conn.send_headers(stream6, h2_headers(seq6), end_stream=False)
        send_body(stream6, body6)
        sock.sendall(conn.data_to_send())

        if h2_body_order == "seq6-body-first":
            send_body(stream5, body5)
            sock.sendall(conn.data_to_send())
        elif h2_body_order != "normal":
            raise ValueError(f"unsupported h2 body order: {h2_body_order}")

        deadline = time.time() + timeout
        while len(response_done) < 2:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError("h2 pair timed out")
            sock.settimeout(remaining)
            data = sock.recv(65535)
            if not data:
                break
            events = conn.receive_data(data)
            for event in events:
                sid = getattr(event, "stream_id", None)
                if sid not in streams:
                    continue
                if isinstance(event, h2.events.ResponseReceived):
                    response_headers[sid] = list(event.headers)
                elif isinstance(event, h2.events.DataReceived):
                    response_body.setdefault(sid, bytearray()).extend(event.data)
                    conn.acknowledge_received_data(event.flow_controlled_length, sid)
                elif isinstance(event, h2.events.StreamEnded):
                    response_done.add(sid)
                    results[streams[sid]]["endedAt"] = time.time()
            out = conn.data_to_send()
            if out:
                sock.sendall(out)
    finally:
        sock.close()

    for sid, name in streams.items():
        hdrs = {str(k).lower(): str(v) for k, v in response_headers.get(sid, [])}
        status = int(hdrs.get(":status", "0") or 0)
        raw = bytes(response_body.get(sid, b""))
        body = decompress_body(raw, hdrs.get("content-encoding", ""))
        ended = results[name].get("endedAt") or time.time()
        response = {
            "status": status,
            "reason": "",
            "headers": {k: v for k, v in hdrs.items() if not k.startswith(":")},
            "rawBodyLen": len(raw),
            "bodyLen": len(body),
            "bodyText": body.decode("utf-8", errors="replace"),
            "elapsedSeconds": ended - (results[name].get("startedAt") or started),
            "transport": dict(transport, streamId=sid),
        }
        results[name]["response"] = response
        results[name]["decoded"] = live.decode_collector_response(response["bodyText"], "YjIYfyxJHRR9")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Send s00 success-neighbor seq5 and seq6 templates through a fresh state in one timing-controlled combo.")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--gap-seconds", type=float, default=0.1816)
    parser.add_argument("--parallel", action="store_true")
    parser.add_argument("--transport", choices=["https-threads", "h2-single-session"], default="https-threads")
    parser.add_argument("--h2-body-order", choices=["normal", "seq6-body-first"], default="normal")
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--header-mode", choices=["safe", "runtime-exact"], default="safe")
    parser.add_argument("--aeax-source", choices=["template", "offline-ng"], default="template")
    parser.add_argument("--bzt-source", choices=["solve", "template", "value"], default="template")
    parser.add_argument("--bzt-value", default=None)
    parser.add_argument("--state-probe", type=Path, default=None)
    parser.add_argument("--fresh-bundle", type=Path, default=None)
    parser.add_argument("--pow-json", type=Path, required=True)
    parser.add_argument("--nq-json", type=Path, required=True)
    parser.add_argument("--ng-nq-json", type=Path, required=True)
    parser.add_argument("--stack-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--tail-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--inner-uuid-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--non-px-activity-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--seq6-activity-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--payload-uuid-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--pc-uuid-source", choices=["payload", "fresh", "template"], default="payload")
    parser.add_argument("--marker-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--form-outer-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--payload-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--pc-source", choices=["computed", "template-exact"], default="computed")
    parser.add_argument("--body-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    px = load_module(PX_TOOL, "probe_human_fresh_px561")
    prog = load_module(PROGRESSION_TOOL, "probe_human_fresh_bundle_progression")
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    started = time.time()
    seq5 = build_material(px, template_line=922, runtime_line=933, seq="5", rsc="6", args=args)
    seq6 = build_seq6_material(prog, args=args)
    results: dict[str, Any] = {}

    if args.transport == "h2-single-session":
        results = send_h2_pair(live, seq5, seq6, args.timeout, args.gap_seconds, args.h2_body_order)
    elif args.parallel:
        t5 = threading.Thread(target=send_one, args=(live, "seq5", seq5, args.timeout, results))
        t6 = threading.Thread(target=send_one, args=(live, "seq6", seq6, args.timeout, results))
        t5.start()
        if args.gap_seconds > 0:
            time.sleep(args.gap_seconds)
        t6.start()
        t5.join()
        t6.join()
    else:
        send_one(live, "seq5", seq5, args.timeout, results)
        if args.gap_seconds > 0:
            time.sleep(args.gap_seconds)
        send_one(live, "seq6", seq6, args.timeout, results)

    result = {
        "startedAt": started,
        "sent": True,
        "mode": "parallel" if args.parallel else "sequential",
        "gapSeconds": args.gap_seconds,
        "inputs": {
            "stateProbe": str(args.state_probe) if args.state_probe else None,
            "freshBundle": str(args.fresh_bundle) if args.fresh_bundle else None,
            "powJson": str(args.pow_json),
            "nqJson": str(args.nq_json),
            "ngNqJson": str(args.ng_nq_json),
            "includeProxyAuthorization": args.include_proxy_authorization,
            "headerMode": args.header_mode,
            "payloadSource": args.payload_source,
            "pcSource": args.pc_source,
            "bodySource": args.body_source,
            "seq6ActivitySource": args.seq6_activity_source,
            "h2BodyOrder": args.h2_body_order,
        },
        "results": results,
        "checks": {
            "seq5Http200": (results.get("seq5", {}).get("response") or {}).get("status") == 200,
            "seq6Http200": (results.get("seq6", {}).get("response") or {}).get("status") == 200,
            "anySuccessHandler": any(
                ((row.get("decoded") or {}).get("hasSuccessHandler") is True)
                for row in results.values()
                if isinstance(row, dict)
            ),
            "seq5HasOIIoIooo": "oIIoIooo" in ((results.get("seq5", {}).get("decoded") or {}).get("handlers") or []),
            "seq6HasOIIoIooo": "oIIoIooo" in ((results.get("seq6", {}).get("decoded") or {}).get("handlers") or []),
        },
    }
    uuid_value = (seq5.get("freshState") or {}).get("uuid", "unknown")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"seq5_seq6_combo_probe_{uuid_value}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "checks": result["checks"],
        "handlers": {
            name: (row.get("decoded") or {}).get("handlers")
            for name, row in results.items()
        },
        "errors": {name: row.get("error") for name, row in results.items()},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
