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
SEQ_DIR = PROTO / "fresh_sequence_probe"
OUT_DIR = PROTO / "fresh_bundle_probe"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
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


def latest_sequence_probe() -> Path:
    candidates: list[Path] = []
    for file in sorted(glob.glob(str(SEQ_DIR / "fresh_sequence_probe_*.json"))):
        path = Path(file)
        doc = read_json(path)
        steps = doc.get("steps") or []
        if doc.get("sent") is True and steps and all((s.get("response") or {}).get("status") == 200 for s in steps):
            candidates.append(path)
    if not candidates:
        raise RuntimeError(f"no sent fresh sequence probe found under {SEQ_DIR}")
    return candidates[-1]


def template_activity() -> dict[str, Any]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == 205:
            activities = (row.get("data") or {}).get("activities") or []
            return json.loads(json.dumps(activities[0]))
    raise KeyError("js trace line 205")


def runtime_request() -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if int(row.get("_line") or 0) == 206:
            return row
    raise KeyError("runtime line 206")


def build_material(sequence_path: Path, *, include_proxy_authorization: bool) -> dict[str, Any]:
    boot = load_module(BOOTSTRAP_TOOL, "probe_human_fresh_bootstrap")
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    sequence = read_json(sequence_path)
    state = sequence["finalState"]

    activity = template_activity()
    d = activity["d"]
    now_ms = int(time.time() * 1000)
    perf = int(time.monotonic() * 1000) % 100000
    d["SlpwEAw5eSc="] = f"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id={state['p1']}&ch_ctx=1"
    d["FUFvS1Mga38="] = state["uuid"]
    d["GUVjT1wnbn4="] = state["px3"]
    d["R3c9PQEXNg8="] = perf
    d["QS07ZwRKPlU="] = now_ms
    if "IU0bR2crHnA=" in d:
        d["IU0bR2crHnA="] = now_ms - 15

    marker = boot.marker_from_qi(None)
    payload, serialized = boot.encode_payload([activity], state["uuid"], marker)
    pc = boot.pc_value(serialized, state["uuid"], "YjIYfyxJHRR9", "369")
    body = boot.form_encode(
        [
            ("payload", payload),
            ("appId", "PXzC5j78di"),
            ("tag", "YjIYfyxJHRR9"),
            ("uuid", state["uuid"]),
            ("ft", "369"),
            ("seq", "0"),
            ("en", "NTA"),
            ("pc", pc),
            ("sid", state["sid"]),
            ("p1", state["p1"]),
            ("vid", state["vid"]),
            ("cts", state["cts"]),
            ("rsc", "1"),
        ]
    )
    runtime = runtime_request()
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
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "bodyLenBytes": len(body.encode()),
        "sequenceProbePath": str(sequence_path),
        "freshState": state,
        "meta": {
            "seq": "0",
            "rsc": "1",
            "jsLine": 205,
            "runtimeLine": 206,
            "marker": marker,
            "pc": pc,
        },
        "sources": {
            "templateJsTraceLine": 205,
            "templateRuntimeRequestLine": 206,
            "boundary": (
                "First bundle request uses current fresh /api/v2/msft state for uuid/p1/sid/vid/cts/_px3; "
                "non-state activity fields remain observed line205 template artifacts."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send first fresh /assets/js/bundle request after fresh API sequence.")
    parser.add_argument("--sequence-probe", type=Path, default=None)
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    seq_path = args.sequence_probe or latest_sequence_probe()
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    started = time.time()
    material = build_material(seq_path, include_proxy_authorization=args.include_proxy_authorization)
    result: dict[str, Any] = {"startedAt": started, "sent": bool(args.send), "material": material}
    if args.send:
        try:
            response = live.send_https(material["url"], material["headers"], material["body"], args.timeout)
            decoded = live.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
            result["response"] = response
            result["decoded"] = decoded
        except Exception as exc:
            result["error"] = str(exc)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fresh_bundle_probe_{material['freshState']['uuid']}_{int(started)}"
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
