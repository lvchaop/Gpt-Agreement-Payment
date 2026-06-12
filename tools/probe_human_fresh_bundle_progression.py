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
FRESH_BUNDLE_DIR = PROTO / "fresh_bundle_probe"
OUT_DIR = PROTO / "fresh_bundle_progression_probe"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
BOOTSTRAP_TOOL = REPO / "tools/probe_human_fresh_bootstrap.py"
LIVE_PROBE = REPO / "tools/probe_human_collector_live.py"

STEP_SPECS = [
    {"name": "bundle_seq1", "jsLine": 286, "runtimeLine": 293, "seq": "1", "rsc": "2", "activityCount": 1},
    {"name": "bundle_seq3", "jsLine": 569, "runtimeLine": 578, "seq": "3", "rsc": "4", "activityCount": 1},
    {"name": "bundle_seq4", "jsLine": 622, "runtimeLine": 634, "seq": "4", "rsc": "5", "activityCount": 1},
]

OLD = {
    "uuid": "7bbba710-65a9-11f1-bc5b-d972b0447135",
    "p1": "ac9e68ae-7803-6e7d-a972-775cf9afdf80",
    "vid": "7cefb5a4-65a9-11f1-94dc-0f9258987c3d",
    "cts": "7cefbdd9-65a9-11f1-94dd-04d8ba8dbf5b",
    "cs": "f21dd0d7dffe52acbd3f2b5a54c85f72049f9064aea8ada9d215cd7fdf37bc3d",
    "ci_initial": "911cacd0-65a9-11f1-b9e4-f30710b600a5",
    "ci_success": "b06407a0-65a9-11f1-a5f4-a312f8704e8f",
    "jo_initial": "1781191438365",
    "jo_success": "1781191490842",
}


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


def latest_fresh_bundle() -> Path:
    candidates: list[Path] = []
    for file in sorted(glob.glob(str(FRESH_BUNDLE_DIR / "fresh_bundle_probe_*.json"))):
        path = Path(file)
        doc = read_json(path)
        if doc.get("sent") is True and (doc.get("response") or {}).get("status") == 200:
            candidates.append(path)
    if not candidates:
        raise RuntimeError(f"no sent fresh bundle probe under {FRESH_BUNDLE_DIR}")
    return candidates[-1]


def kl(value: str | None) -> str:
    if not value:
        return ""
    return "".join(chr(0xE0100 + ord(ch)) for ch in str(value))


def replace_strings(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for old, new in replacements.items():
            out = out.replace(old, new)
        return out
    if isinstance(value, list):
        return [replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: replace_strings(child, replacements) for key, child in value.items()}
    return value


def template_activities(js_line: int) -> list[dict[str, Any]]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == js_line:
            return json.loads(json.dumps((row.get("data") or {}).get("activities") or []))
    raise KeyError(f"js trace line {js_line}")


def runtime_request(runtime_line: int) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if int(row.get("_line") or 0) == runtime_line:
            return row
    raise KeyError(f"runtime line {runtime_line}")


def update_state_from_parts(state: dict[str, Any], parts: list[str]) -> dict[str, Any]:
    for part in parts:
        fields = str(part).split("|")
        if fields[:2] == ["IoooII", "_px3"] and len(fields) >= 4:
            state["px3"] = fields[3]
        elif fields[:2] == ["oIIoIIoo", "_pxde"] and len(fields) >= 4:
            state["pxde"] = fields[3]
        elif fields and fields[0] == "IIoIoI" and len(fields) >= 2:
            state["zo"] = fields[1]
        elif fields and fields[0] == "oIIoIoII" and len(fields) >= 2:
            state["jo"] = fields[1]
        elif fields and fields[0] == "ooooII" and len(fields) >= 2:
            state["qo"] = fields[1]
        elif fields and fields[0] == "oIIoIoIo" and len(fields) >= 2:
            state["gl"] = fields[1]
        elif fields and fields[0] == "IoIIII" and len(fields) >= 2:
            state["cs"] = fields[1]
        elif fields and fields[0] == "IooIoI" and len(fields) >= 3:
            state["ci"] = fields[2]
        elif fields and fields[0] == "IooIIo":
            state["powChallenge"] = part
    state["sidWithKlJo"] = state["sid"] + kl(str(state["jo"]))
    return state


def state_from_bundle(bundle_doc: dict[str, Any]) -> dict[str, Any]:
    state = dict((bundle_doc.get("material") or {}).get("freshState") or {})
    update_state_from_parts(state, [str(p) for p in (bundle_doc.get("decoded") or {}).get("parts") or []])
    return state


def state_from_state_probe(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    state = dict(doc.get("finalState") or {})
    if not state:
        raise RuntimeError(f"state probe lacks finalState: {path}")
    return state


def patch_common_activity_fields(activities: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    activities = replace_strings(
        activities,
        {
            OLD["uuid"]: state["uuid"],
            OLD["p1"]: state["p1"],
            OLD["vid"]: state["vid"],
            OLD["cts"]: state["cts"],
            OLD["cs"]: state["cs"],
            OLD["ci_initial"]: state.get("ci") or "",
            OLD["ci_success"]: state.get("ci") or "",
            OLD["jo_initial"]: str(state["jo"]),
            OLD["jo_success"]: str(state["jo"]),
        },
    )
    now_ms = int(time.time() * 1000)
    perf = int(time.monotonic() * 1000) % 100000
    for activity in activities:
        d = activity.get("d")
        if not isinstance(d, dict):
            continue
        if "FUFvS1Mga38=" in d:
            d["FUFvS1Mga38="] = state["uuid"]
        if "SlpwEAw5eSc=" in d:
            d["SlpwEAw5eSc="] = f"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id={state['p1']}&ch_ctx=1"
        if "GUVjT1wnbn4=" in d:
            d["GUVjT1wnbn4="] = state.get("px3")
        if "cR1LFzd8RSQ=" in d:
            d["cR1LFzd8RSQ="] = int(state["jo"]) if str(state["jo"]).isdigit() else state["jo"]
        if "X08lRRkjIXQ=" in d:
            d["X08lRRkjIXQ="] = int(state["jo"]) if str(state["jo"]).isdigit() else state["jo"]
        if "eEQCDj4mDz0=" in d and state.get("zo") is not None:
            d["eEQCDj4mDz0="] = str(state["zo"])
        if "JxcdHWJzESc=" in d and state.get("qo") is not None:
            d["JxcdHWJzESc="] = str(state["qo"])
        if "JnZcfGMXVEo=" in d and state.get("gl") is not None:
            d["JnZcfGMXVEo="] = int(state["gl"]) if str(state["gl"]).isdigit() else state["gl"]
        if "QS07ZwRKPlU=" in d:
            d["QS07ZwRKPlU="] = now_ms
        if "R3c9PQEXNg8=" in d:
            d["R3c9PQEXNg8="] = perf
        if "IU0bR2crHnA=" in d:
            d["IU0bR2crHnA="] = now_ms - 18
    return activities


def build_request(
    spec: dict[str, Any],
    state: dict[str, Any],
    *,
    include_proxy_authorization: bool,
    header_mode: str = "safe",
    activity_source: str = "fresh",
) -> dict[str, Any]:
    boot = load_module(BOOTSTRAP_TOOL, "probe_human_fresh_bootstrap")
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    activities = template_activities(int(spec["jsLine"]))
    if activity_source == "fresh":
        activities = patch_common_activity_fields(activities, state)
    elif activity_source != "template":
        raise ValueError(f"unsupported activity_source: {activity_source}")
    marker = boot.marker_from_qi(str(state["jo"]))
    payload, serialized = boot.encode_payload(activities, state["uuid"], marker)
    pc = boot.pc_value(serialized, state["uuid"], "YjIYfyxJHRR9", "369")
    pairs: list[tuple[str, Any]] = [
        ("payload", payload),
        ("appId", "PXzC5j78di"),
        ("tag", "YjIYfyxJHRR9"),
        ("uuid", state["uuid"]),
        ("ft", "369"),
        ("seq", spec["seq"]),
        ("en", "NTA"),
        ("cs", state["cs"]),
        ("pc", pc),
        ("sid", state.get("sidWithKlJo") or state["sid"] + kl(str(state["jo"]))),
        ("p1", state["p1"]),
        ("vid", state["vid"]),
        ("ci", state.get("ci")),
        ("cts", state["cts"]),
        ("rsc", spec["rsc"]),
    ]
    body = boot.form_encode([(k, v) for k, v in pairs if v is not None])
    runtime = runtime_request(int(spec["runtimeLine"]))
    headers = live.headers_from_runtime(
        runtime,
        body=body,
        url=str(runtime.get("url") or ""),
        include_proxy_authorization=include_proxy_authorization,
        header_mode=header_mode,
    )
    return {
        "name": spec["name"],
        "url": runtime["url"],
        "headers": headers,
        "body": body,
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "bodyLenBytes": len(body.encode()),
        "meta": {
            "seq": spec["seq"],
            "rsc": spec["rsc"],
            "jsLine": spec["jsLine"],
            "runtimeLine": spec["runtimeLine"],
            "marker": marker,
            "headerMode": header_mode,
            "pc": pc,
            "activityTypes": [a.get("t") for a in activities],
            "activitySource": activity_source,
            "serializedSha256": hashlib.sha256(serialized.encode()).hexdigest(),
            "serializedLen": len(serialized),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Advance a fresh /assets/js/bundle session through observed non-PX561 bundle templates.")
    parser.add_argument("--fresh-bundle", type=Path, default=None)
    parser.add_argument("--state-probe", type=Path, default=None)
    parser.add_argument("--steps", default="bundle_seq1,bundle_seq3,bundle_seq4")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--header-mode", choices=["safe", "runtime-exact"], default="safe")
    parser.add_argument("--activity-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    bundle_path = args.fresh_bundle or latest_fresh_bundle()
    if args.state_probe:
        state = state_from_state_probe(args.state_probe)
    else:
        bundle = read_json(bundle_path)
        state = state_from_bundle(bundle)
    initial_state = json.loads(json.dumps(state))
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    wanted = {item.strip() for item in args.steps.split(",") if item.strip()}
    started = time.time()
    steps = []
    for spec in STEP_SPECS:
        if spec["name"] not in wanted:
            continue
        req = build_request(
            spec,
            state,
            include_proxy_authorization=args.include_proxy_authorization,
            header_mode=args.header_mode,
            activity_source=args.activity_source,
        )
        step: dict[str, Any] = {"request": req, "stateBefore": json.loads(json.dumps(state))}
        if args.send:
            try:
                response = live.send_https(req["url"], req["headers"], req["body"], args.timeout)
                decoded = live.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
                step["response"] = response
                step["decoded"] = decoded
                update_state_from_parts(state, [str(p) for p in decoded.get("parts") or []])
            except Exception as exc:
                step["error"] = str(exc)
        step["stateAfter"] = json.loads(json.dumps(state))
        steps.append(step)

    result = {
        "startedAt": started,
        "sent": bool(args.send),
        "freshBundlePath": str(bundle_path),
        "stateProbePath": str(args.state_probe) if args.state_probe else None,
        "initialState": initial_state,
        "finalState": state,
        "steps": steps,
        "boundary": "This only advances non-PX561 bundle templates. It proves or disproves state progression behavior, not final HUMAN success by itself.",
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"fresh_bundle_progression_probe_{state['uuid']}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "sent": result["sent"],
        "statuses": [(s.get("response") or {}).get("status") for s in steps],
        "handlers": [(s.get("decoded") or {}).get("handlers") for s in steps],
        "hasPow": [(s.get("decoded") or {}).get("hasPowResult") for s in steps],
        "finalState": {k: state.get(k) for k in ["uuid", "jo", "ci", "cs", "px3", "pxde", "powChallenge"]},
        "errors": [s.get("error") for s in steps],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
