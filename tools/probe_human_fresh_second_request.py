#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BOOTSTRAP_AUDIT = REPO / "output/protocol_reverse/goal_audit/fresh_bootstrap_live_probe_audit.json"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
OUT_DIR = REPO / "output/protocol_reverse/fresh_second_probe"
BOOTSTRAP_TOOL = REPO / "tools/probe_human_fresh_bootstrap.py"
LIVE_PROBE = REPO / "tools/probe_human_collector_live.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def kl(value: str | None) -> str:
    if not value:
        return ""
    return "".join(chr(0xE0100 + ord(ch)) for ch in str(value))


def split_part(part: str) -> tuple[str, list[str]]:
    fields = str(part).split("|")
    return fields[0] if fields else "", fields[1:]


def state_from_bootstrap_probe(audit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fresh = audit.get("freshState") or ((audit.get("material") or {}).get("freshState"))
    if not fresh:
        raise KeyError("freshState")
    memory = ((audit.get("response") or {}).get("state") or {}).get("memory") or {}
    cookies = ((audit.get("response") or {}).get("state") or {}).get("cookies") or {}
    if memory and cookies:
        return fresh, memory, cookies
    for part in (audit.get("decoded") or {}).get("parts") or []:
        key, args = split_part(str(part))
        source = {"raw": str(part)}
        if key == "IoooII" and len(args) >= 3:
            cookies[args[0]] = {"value": args[2], "ttl": args[1], "source": source}
        elif key == "oIIoIIoo" and len(args) >= 3:
            cookies[args[0]] = {"value": args[2], "ttl": args[1], "source": source}
        elif key == "IIoIIo" and args:
            memory["sid"] = {"value": args[0], "source": source}
        elif key == "IIoIoI" and args:
            memory["Zo"] = {"value": args[0], "source": source}
        elif key == "oIIoIoII" and args:
            memory["Jo"] = {"value": args[0], "source": source}
        elif key == "ooooII" and args:
            memory["Qo"] = {"value": args[0], "source": source}
        elif key == "oIIoIoIo" and args:
            memory["Gl"] = {"value": args[0], "source": source}
        elif key == "oIIooIIo" and args:
            memory["cts"] = {"value": args[0], "source": source}
        elif key == "IoIIII" and args:
            memory["cs"] = {"value": args[0], "source": source}
        elif key == "IooIoo" and args:
            memory["vid"] = {"value": args[0], "source": source}
    return fresh, memory, cookies


def template_activity() -> dict[str, Any]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == 85:
            activities = (row.get("data") or {}).get("activities") or []
            return json.loads(json.dumps(activities[0]))
    raise KeyError("js trace line 85")


def runtime_request(line_no: int) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if int(row.get("_line") or 0) == line_no:
            return row
    raise KeyError(line_no)


def build_material(audit_path: Path, *, include_proxy_authorization: bool) -> dict[str, Any]:
    boot = load_module(BOOTSTRAP_TOOL, "probe_human_fresh_bootstrap")
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    audit = read_json(audit_path)
    fresh, memory, cookies = state_from_bootstrap_probe(audit)

    uuid_value = fresh["uuid"]
    p1 = fresh["p1"]
    sid = memory["sid"]["value"]
    jo = memory["Jo"]["value"]
    cs = memory["cs"]["value"]
    vid = memory["vid"]["value"]
    cts = memory["cts"]["value"]
    zo = memory["Zo"]["value"]
    qo = memory["Qo"]["value"]
    gl = memory["Gl"]["value"]
    px3 = cookies["_px3"]["value"]

    activity = template_activity()
    d = activity["d"]
    d["cR1LFzd8RSQ="] = int(jo) if str(jo).isdigit() else jo
    d["eEQCDj4mDz0="] = zo
    d["JxcdHWJzESc="] = qo
    d["JnZcfGMXVEo="] = int(gl) if str(gl).isdigit() else gl
    d["SlpwEAw5eSc="] = f"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id={p1}"
    d["FUFvS1Mga38="] = uuid_value
    d["GUVjT1wnbn4="] = px3
    now_ms = int(time.time() * 1000)
    d["QS07ZwRKPlU="] = now_ms
    if "IU0bR2crHnA=" in d:
        d["IU0bR2crHnA="] = now_ms - 18

    marker = boot.marker_from_qi(jo)
    payload, serialized = boot.encode_payload([activity], uuid_value, marker)
    pc = boot.pc_value(serialized, uuid_value, "YjIYfyxJHRR9", "369")
    sid_with_jo = sid + kl(jo)
    body = boot.form_encode(
        [
            ("payload", payload),
            ("appId", "PXzC5j78di"),
            ("tag", "YjIYfyxJHRR9"),
            ("uuid", uuid_value),
            ("ft", "369"),
            ("seq", "1"),
            ("en", "NTA"),
            ("cs", cs),
            ("pc", pc),
            ("sid", sid_with_jo),
            ("p1", p1),
            ("vid", vid),
            ("cts", cts),
            ("rsc", "2"),
        ]
    )
    runtime = runtime_request(84)
    headers = live.headers_from_runtime(
        runtime,
        body=body,
        url=str(runtime.get("url") or ""),
        include_proxy_authorization=include_proxy_authorization,
    )
    return {
        "url": runtime["url"],
        "headers": headers,
        "body": body,
        "stateSourceAudit": str(audit_path),
        "freshState": fresh,
        "derivedState": {
            "sid": sid,
            "jo": jo,
            "cs": cs,
            "vid": vid,
            "cts": cts,
            "zo": zo,
            "qo": qo,
            "gl": gl,
            "sidWithKlJo": sid_with_jo,
            "marker": marker,
            "pc": pc,
        },
        "sources": {
            "templateJsTraceLine": 85,
            "templateRuntimeRequestLine": 84,
            "boundary": (
                "Second request uses fresh bootstrap decoded state and substitutes known state fields into observed line85 activity template; "
                "non-state fingerprint fields remain copied artifacts."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send fresh-state second /api/v2/msft request after bootstrap.")
    parser.add_argument("--bootstrap-audit", type=Path, default=BOOTSTRAP_AUDIT)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    started = time.time()
    material = build_material(args.bootstrap_audit, include_proxy_authorization=args.include_proxy_authorization)
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
        try:
            response = live.send_https(material["url"], material["headers"], material["body"], args.timeout)
            result["response"] = response
            result["decoded"] = live.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
        except Exception as exc:
            result["error"] = str(exc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fresh_second_probe_{material['freshState']['uuid']}_{int(started)}"
    json_path = args.out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path),
        "sent": result["sent"],
        "status": (result.get("response") or {}).get("status"),
        "handlers": (result.get("decoded") or {}).get("handlers"),
        "hasPowResult": (result.get("decoded") or {}).get("hasPowResult"),
        "hasSuccessHandler": (result.get("decoded") or {}).get("hasSuccessHandler"),
        "error": result.get("error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
