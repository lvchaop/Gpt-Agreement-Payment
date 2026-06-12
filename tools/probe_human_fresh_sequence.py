#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
SECOND_DIR = PROTO / "fresh_second_probe"
OUT_DIR = PROTO / "fresh_sequence_probe"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
BOOTSTRAP_TOOL = REPO / "tools/probe_human_fresh_bootstrap.py"
LIVE_PROBE = REPO / "tools/probe_human_collector_live.py"


REQUEST_SPECS = [
    {"name": "req2", "jsLine": 112, "runtimeLine": 111, "seq": "2", "rsc": "3", "joKey": "X08lRRkjIXQ="},
    {"name": "req3", "jsLine": 148, "runtimeLine": 140, "seq": "3", "rsc": "4", "joKey": "cR1LFzd8RSQ="},
]


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


def latest_second_probe() -> Path:
    candidates = []
    for file in sorted(glob.glob(str(SECOND_DIR / "fresh_second_probe_*.json"))):
        path = Path(file)
        doc = read_json(path)
        if doc.get("sent") is True and (doc.get("response") or {}).get("status") == 200:
            candidates.append(path)
    if not candidates:
        raise RuntimeError(f"no sent second probe found under {SECOND_DIR}")
    return candidates[-1]


def split_part(part: str) -> tuple[str, list[str]]:
    fields = str(part).split("|")
    return fields[0] if fields else "", fields[1:]


def kl(value: str | None) -> str:
    if not value:
        return ""
    return "".join(chr(0xE0100 + ord(ch)) for ch in str(value))


def update_tokens_from_parts(state: dict[str, Any], parts: list[str]) -> None:
    for part in parts:
        key, args = split_part(part)
        if key == "IoooII" and len(args) >= 3 and args[0] == "_px3":
            state["px3"] = args[2]
        elif key == "oIIoIIoo" and len(args) >= 3 and args[0] == "_pxde":
            state["pxde"] = args[2]


def template_activity(js_line: int) -> dict[str, Any]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == js_line:
            activities = (row.get("data") or {}).get("activities") or []
            return json.loads(json.dumps(activities[0]))
    raise KeyError(js_line)


def runtime_request(runtime_line: int) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if int(row.get("_line") or 0) == runtime_line:
            return row
    raise KeyError(runtime_line)


def initial_state(second_probe: dict[str, Any]) -> dict[str, Any]:
    material = second_probe["material"]
    derived = material["derivedState"]
    fresh = material["freshState"]
    state = {
        "uuid": fresh["uuid"],
        "p1": fresh["p1"],
        "sid": derived["sid"],
        "jo": derived["jo"],
        "cs": derived["cs"],
        "vid": derived["vid"],
        "cts": derived["cts"],
        "sidWithKlJo": derived["sidWithKlJo"],
        "px3": None,
        "pxde": None,
    }
    update_tokens_from_parts(state, [str(p) for p in (second_probe.get("decoded") or {}).get("parts") or []])
    return state


def build_request(spec: dict[str, str], state: dict[str, Any], *, include_proxy_authorization: bool) -> dict[str, Any]:
    boot = load_module(BOOTSTRAP_TOOL, "probe_human_fresh_bootstrap")
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    activity = template_activity(int(spec["jsLine"]))
    d = activity["d"]
    now_ms = int(time.time() * 1000)
    perf = int(time.monotonic() * 1000) % 100000
    d["FUFvS1Mga38="] = state["uuid"]
    d["SlpwEAw5eSc="] = f"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id={state['p1']}"
    d["GUVjT1wnbn4="] = state["px3"]
    d[spec["joKey"]] = int(state["jo"]) if str(state["jo"]).isdigit() else state["jo"]
    d["QS07ZwRKPlU="] = now_ms
    d["R3c9PQEXNg8="] = perf
    if "IU0bR2crHnA=" in d:
        d["IU0bR2crHnA="] = now_ms - 18
    marker = boot.marker_from_qi(state["jo"])
    payload, serialized = boot.encode_payload([activity], state["uuid"], marker)
    pc = boot.pc_value(serialized, state["uuid"], "YjIYfyxJHRR9", "369")
    body = boot.form_encode(
        [
            ("payload", payload),
            ("appId", "PXzC5j78di"),
            ("tag", "YjIYfyxJHRR9"),
            ("uuid", state["uuid"]),
            ("ft", "369"),
            ("seq", spec["seq"]),
            ("en", "NTA"),
            ("cs", state["cs"]),
            ("pc", pc),
            ("sid", state["sidWithKlJo"] or state["sid"] + kl(state["jo"])),
            ("p1", state["p1"]),
            ("vid", state["vid"]),
            ("cts", state["cts"]),
            ("rsc", spec["rsc"]),
        ]
    )
    runtime = runtime_request(int(spec["runtimeLine"]))
    headers = live.headers_from_runtime(
        runtime,
        body=body,
        url=str(runtime.get("url") or ""),
        include_proxy_authorization=include_proxy_authorization,
    )
    return {
        "name": spec["name"],
        "url": runtime["url"],
        "headers": headers,
        "body": body,
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "bodyLenBytes": len(body.encode()),
        "meta": {"seq": spec["seq"], "rsc": spec["rsc"], "jsLine": spec["jsLine"], "runtimeLine": spec["runtimeLine"], "marker": marker, "pc": pc},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Continue fresh HUMAN collector sequence through observed req2/req3 templates.")
    parser.add_argument("--second-probe", type=Path, default=None)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    second_path = args.second_probe or latest_second_probe()
    second = read_json(second_path)
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    started = time.time()
    state = initial_state(second)
    requests: list[dict[str, Any]] = []
    for spec in REQUEST_SPECS:
        req = build_request(spec, state, include_proxy_authorization=args.include_proxy_authorization)
        step: dict[str, Any] = {"request": req}
        if args.send:
            try:
                response = live.send_https(req["url"], req["headers"], req["body"], args.timeout)
                decoded = live.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
                step["response"] = response
                step["decoded"] = decoded
                update_tokens_from_parts(state, [str(p) for p in decoded.get("parts") or []])
            except Exception as exc:
                step["error"] = str(exc)
        requests.append(step)

    result = {
        "startedAt": started,
        "sent": bool(args.send),
        "secondProbePath": str(second_path),
        "initialState": initial_state(second),
        "finalState": state,
        "steps": requests,
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fresh_sequence_probe_{state['uuid']}_{int(started)}"
    json_path = args.out_dir / f"{stem}.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(json_path),
        "sent": result["sent"],
        "statuses": [(s.get("response") or {}).get("status") for s in requests],
        "handlers": [(s.get("decoded") or {}).get("handlers") for s in requests],
        "hasPow": [((s.get("decoded") or {}).get("hasPowResult")) for s in requests],
        "errors": [s.get("error") for s in requests],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
