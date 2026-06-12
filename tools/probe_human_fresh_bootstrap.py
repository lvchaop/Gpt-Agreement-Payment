#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import importlib.util
import json
import time
import urllib.parse
import uuid
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUN_ID = "s00ld1lglrw0_1781191381"
JS_TRACE = REPO / f"output/outlook_browser/js_internal_trace_{RUN_ID}.jsonl"
RUNTIME_TRACE = REPO / f"output/outlook_browser/runtime_trace_{RUN_ID}.jsonl"
OUT_DIR = REPO / "output/protocol_reverse/fresh_bootstrap_probe"
LIVE_PROBE = REPO / "tools/probe_human_collector_live.py"


JSON_ESCAPES = {
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
    '"': '\\"',
    "\\": "\\\\",
}


def load_live_probe() -> Any:
    spec = importlib.util.spec_from_file_location("probe_human_collector_live", LIVE_PROBE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {LIVE_PROBE}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def xor_string(value: str, key: int) -> str:
    return "".join(chr(ord(ch) ^ key) for ch in value)


def marker_from_qi(qi: str | None) -> str:
    value = qi if qi and qi != "undefined" else "1604064986000"
    return xor_string(base64.b64encode(str(value).encode()).decode(), 10)


def quote_string(value: str) -> str:
    out = ['"']
    for ch in str(value):
        code = ord(ch)
        if ch in JSON_ESCAPES:
            out.append(JSON_ESCAPES[ch])
        elif (
            0 <= code <= 0x1F
            or 0x7F <= code <= 0x9F
            or code == 0xAD
            or 0x0600 <= code <= 0x0604
            or code == 0x070F
            or code in (0x17B4, 0x17B5)
            or 0x200C <= code <= 0x200F
            or 0x2028 <= code <= 0x202F
            or 0x2060 <= code <= 0x206F
            or code == 0xFEFF
            or 0xFFF0 <= code <= 0xFFFF
        ):
            out.append("\\u" + format(code, "04x"))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def ut(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str):
        return quote_string(value)
    if isinstance(value, list):
        return "[" + ",".join(ut(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(quote_string(str(k)) + ":" + ut(v) for k, v in value.items()) + "}"
    return "null"


def insertion_positions(chars: str, base_len: int, cu: str) -> list[int]:
    h = xor_string(base64.b64encode(str(cu).encode()).decode(), 10)
    positions: list[int] = []
    max_value = -1
    for p in range(len(chars)):
        m = p // len(h) + 1
        g = p % len(h) if p >= len(h) else p
        max_value = max(max_value, ord(h[g]) * ord(h[m]))
    for idx in range(len(chars)):
        i = idx // len(h) + 1
        e = idx % len(h)
        pos = ord(h[e]) * ord(h[i])
        if pos >= base_len:
            pos = int((pos / max_value) * (base_len - 1))
        while pos in positions:
            pos += 1
        positions.append(pos)
    return sorted(positions)


def insert_chars(chars: str, base: str, positions: list[int]) -> str:
    out = ""
    start = 0
    for i, ch in enumerate(chars):
        cut = positions[i] - i - 1
        out += base[start:cut] + ch
        start = cut
    return out + base[start:]


def encode_payload(activities: list[dict[str, Any]], uuid_value: str, marker: str) -> tuple[str, str]:
    serialized = ut(activities)
    base = base64.b64encode(xor_string(serialized, 50).encode("utf-8")).decode("ascii")
    return insert_chars(marker, base, insertion_positions(marker, len(base), uuid_value)), serialized


def pc_value(serialized: str, uuid_value: str, tag: str, ft: str) -> str:
    digest = hmac.new(f"{uuid_value}:{tag}:{ft}".encode(), serialized.encode(), hashlib.md5).hexdigest()
    digits = ""
    mods = ""
    for ch in digest:
        code = ord(ch)
        if 48 <= code <= 57:
            digits += ch
        else:
            mods += str(code % 10)
    merged = digits + mods
    return "".join(merged[i] for i in range(0, len(merged), 2))


def form_encode(pairs: list[tuple[str, Any]]) -> str:
    return "&".join(f"{urllib.parse.quote(str(k))}={str(v)}" for k, v in pairs)


def runtime_request(line_no: int) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if int(row.get("_line") or 0) == line_no:
            return row
    raise KeyError(line_no)


def initial_activity_template() -> dict[str, Any]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == 33:
            activities = (row.get("data") or {}).get("activities") or []
            return json.loads(json.dumps(activities[0]))
    raise KeyError("js trace line 33")


def headers_from_runtime(row: dict[str, Any], *, body: str, include_proxy_authorization: bool) -> dict[str, str]:
    live_probe = load_live_probe()
    return live_probe.headers_from_runtime(
        row,
        body=body,
        url=str(row.get("url") or ""),
        include_proxy_authorization=include_proxy_authorization,
    )


def build_material(*, fresh_uuid: str, fresh_p1: str, include_proxy_authorization: bool) -> dict[str, Any]:
    request_row = runtime_request(29)
    activity = initial_activity_template()
    d = activity["d"]
    now_ms = int(time.time() * 1000)
    perf = int(time.monotonic() * 1000) % 100000
    d["SlpwEAw5eSc="] = f"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id={fresh_p1}"
    d["R3c9PQEXNg8="] = perf
    d["IU0bR2crHnA="] = now_ms - 18
    d["QS07ZwRKPlU="] = now_ms
    d["FUFvS1Mga38="] = fresh_uuid
    marker = marker_from_qi(None)
    payload, serialized = encode_payload([activity], fresh_uuid, marker)
    pc = pc_value(serialized, fresh_uuid, "YjIYfyxJHRR9", "369")
    body = form_encode(
        [
            ("payload", payload),
            ("appId", "PXzC5j78di"),
            ("tag", "YjIYfyxJHRR9"),
            ("uuid", fresh_uuid),
            ("ft", "369"),
            ("seq", "0"),
            ("en", "NTA"),
            ("pc", pc),
            ("p1", fresh_p1),
            ("rsc", "1"),
        ]
    )
    return {
        "url": request_row["url"],
        "body": body,
        "headers": headers_from_runtime(request_row, body=body, include_proxy_authorization=include_proxy_authorization),
        "freshState": {"uuid": fresh_uuid, "p1": fresh_p1, "marker": marker, "pc": pc},
        "sources": {
            "templateJsTraceLine": 33,
            "templateRuntimeRequestLine": 29,
            "staticEvidence": [
                "main.beautified.js:406-408 constants gt/yt/bt",
                "main.beautified.js:4804-4837 ql/$l and form construction",
                "main.beautified.js:1551-1573 io() uuid generator",
                "main.beautified.js:1593-1595 po() _pxUuid source",
            ],
            "boundary": "Only uuid/p1/time fields are fresh; non-browser activity template remains copied from observed runtime line 33.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and optionally send a fresh initial HUMAN collector /api/v2/msft bootstrap request.")
    parser.add_argument("--uuid")
    parser.add_argument("--p1")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    fresh_uuid = args.uuid or str(uuid.uuid1())
    fresh_p1 = args.p1 or str(uuid.uuid4())
    started = time.time()
    material = build_material(
        fresh_uuid=fresh_uuid,
        fresh_p1=fresh_p1,
        include_proxy_authorization=args.include_proxy_authorization,
    )
    result: dict[str, Any] = {
        "startedAt": started,
        "sent": bool(args.send),
        "material": {
            **material,
            "bodySha256": hashlib.sha256(material["body"].encode()).hexdigest(),
            "bodyLenBytes": len(material["body"].encode()),
        },
    }
    if args.send:
        live_probe = load_live_probe()
        try:
            response = live_probe.send_https(material["url"], material["headers"], material["body"], args.timeout)
            result["response"] = response
            result["decoded"] = live_probe.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
        except Exception as exc:
            result["error"] = str(exc)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fresh_bootstrap_probe_{fresh_uuid}_{int(started)}"
    json_path = out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path),
        "sent": result["sent"],
        "status": (result.get("response") or {}).get("status"),
        "handlers": (result.get("decoded") or {}).get("handlers"),
        "error": result.get("error"),
        "freshState": material["freshState"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
