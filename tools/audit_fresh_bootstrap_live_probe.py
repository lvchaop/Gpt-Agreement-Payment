#!/usr/bin/env python3
from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
FRESH_DIR = PROTO / "fresh_bootstrap_probe"
OUT_DIR = PROTO / "goal_audit"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"


REQUIRED_STATE_HANDLERS = {
    "IoooII",
    "IIoIIo",
    "oIIoIoII",
    "oIIooIIo",
    "IoIIII",
    "IooIoo",
    "oIIoIIoo",
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


def latest_probe_path() -> Path:
    files = sorted(glob.glob(str(FRESH_DIR / "fresh_bootstrap_probe_*.json")))
    sent = []
    for file in files:
        doc = read_json(Path(file))
        if doc.get("sent") is True:
            sent.append(Path(file))
    if not sent:
        raise RuntimeError(f"no sent fresh bootstrap probe under {FRESH_DIR}")
    return sent[-1]


def split_part(part: str) -> tuple[str, list[str]]:
    fields = str(part).split("|")
    return fields[0] if fields else "", fields[1:]


def state_from_parts(parts: list[str]) -> dict[str, Any]:
    state: dict[str, Any] = {"cookies": {}, "memory": {}, "parts": []}
    for idx, part in enumerate(parts):
        key, args = split_part(part)
        source = {"partIndex": idx, "handler": key, "raw": part}
        state["parts"].append(source)
        if key == "IoooII" and len(args) >= 3:
            state["cookies"][args[0]] = {"value": args[2], "ttl": args[1], "source": source}
        elif key == "oIIoIIoo" and len(args) >= 3:
            state["cookies"][args[0]] = {"value": args[2], "ttl": args[1], "source": source}
        elif key == "IooIoo" and args:
            state["cookies"]["_pxvid"] = {"value": args[0], "ttl": args[1] if len(args) > 1 else None, "source": source}
            state["memory"]["vid"] = {"value": args[0], "source": source}
        elif key == "IIoIIo" and args:
            state["memory"]["sid"] = {"value": args[0], "source": source}
        elif key == "oIIoIoII" and args:
            state["memory"]["Jo"] = {"value": args[0], "source": source}
        elif key == "oIIooIIo" and args:
            state["memory"]["cts"] = {"value": args[0], "source": source}
        elif key == "IoIIII" and args:
            state["memory"]["cs"] = {"value": args[0], "source": source}
        elif key == "IIoIoI" and args:
            state["memory"]["Zo"] = {"value": args[0], "source": source}
        elif key == "ooooII" and args:
            state["memory"]["Qo"] = {"value": args[0], "source": source}
        elif key == "oIIoIoIo" and args:
            state["memory"]["Gl"] = {"value": args[0], "source": source}
    return state


def verify_request_payload(probe: dict[str, Any]) -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    material = probe.get("material") or {}
    fresh = material.get("freshState") or {}
    params = dec.parse_form(material.get("body") or "")
    decoded = dec.decode_payload(params.get("payload", ""), fresh.get("marker", ""), params.get("uuid", ""))
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    first = activities[0] if activities and isinstance(activities[0], dict) else {}
    first_d = first.get("d") if isinstance(first.get("d"), dict) else {}
    return {
        "markerMatch": decoded.get("markerMatch"),
        "jsonError": decoded.get("jsonError"),
        "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
        "formUuid": params.get("uuid"),
        "formP1": params.get("p1"),
        "activityUuid": first_d.get("FUFvS1Mga38="),
        "activityUrl": first_d.get("SlpwEAw5eSc="),
        "uuidAllMatch": params.get("uuid") == fresh.get("uuid") == first_d.get("FUFvS1Mga38="),
        "p1AllMatch": params.get("p1") == fresh.get("p1") and str(first_d.get("SlpwEAw5eSc=") or "").endswith(str(fresh.get("p1"))),
    }


def build_audit(probe_path: Path | None = None) -> dict[str, Any]:
    path = probe_path or latest_probe_path()
    probe = read_json(path)
    decoded = probe.get("decoded") or {}
    parts = [str(p) for p in decoded.get("parts") or []]
    handlers = set(decoded.get("handlers") or [])
    request_decode = verify_request_payload(probe)
    response_state = state_from_parts(parts)
    checks = {
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "responseDecodedWithoutError": decoded.get("error") is None,
        "requestPayloadMarkerMatches": request_decode.get("markerMatch") is True,
        "requestPayloadJsonDecodes": request_decode.get("jsonError") is None,
        "requestUuidFreshAndConsistent": request_decode.get("uuidAllMatch") is True,
        "requestP1FreshAndConsistent": request_decode.get("p1AllMatch") is True,
        "responseHasInitialStateHandlers": REQUIRED_STATE_HANDLERS.issubset(handlers),
        "responseHasPx3": decoded.get("hasPx3") is True,
        "responseHasPxde": decoded.get("hasPxde") is True,
        "responseHasSuccessHandler": decoded.get("hasSuccessHandler") is True,
        "responseHasPowResult": decoded.get("hasPowResult") is True,
    }
    checks["freshBootstrapStateProved"] = all(
        checks[k]
        for k in [
            "probeSent",
            "probeHttp200",
            "responseDecodedWithoutError",
            "requestPayloadMarkerMatches",
            "requestPayloadJsonDecodes",
            "requestUuidFreshAndConsistent",
            "requestP1FreshAndConsistent",
            "responseHasInitialStateHandlers",
            "responseHasPx3",
            "responseHasPxde",
        ]
    )
    checks["pureProtocolReady"] = False
    return {
        "purpose": "Audit live fresh browserless bootstrap request to HUMAN collector /api/v2/msft.",
        "probePath": str(path.resolve()),
        "freshState": (probe.get("material") or {}).get("freshState"),
        "request": {
            "url": (probe.get("material") or {}).get("url"),
            "bodySha256": (probe.get("material") or {}).get("bodySha256"),
            "bodyLenBytes": (probe.get("material") or {}).get("bodyLenBytes"),
            "payloadDecode": request_decode,
            "sources": (probe.get("material") or {}).get("sources"),
        },
        "response": {
            "status": (probe.get("response") or {}).get("status"),
            "bodyLen": (probe.get("response") or {}).get("bodyLen"),
            "elapsedSeconds": (probe.get("response") or {}).get("elapsedSeconds"),
            "handlers": decoded.get("handlers"),
            "state": response_state,
        },
        "checks": checks,
        "remainingGaps": [
            "This proves only fresh initial state bootstrap; it is not a HUMAN success packet and has no oIIoIooo|0.",
            "The initial activity template is still copied from observed runtime line 33 except uuid/p1/timing substitutions.",
            "Next proof target is a stateful fresh sequence that consumes this decoded sid/cs/vid/cts/Jo/_px3/_pxde and reaches a live POW/PX561 response, then accepted success.",
        ],
        "conclusion": (
            "A fresh uuid/p1 no-browser initial collector request was constructed, decoded locally, sent live, and returned decodable initial collector state. "
            "This closes fresh bootstrap state acquisition, but not the end-to-end pure protocol HUMAN success PoC."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Fresh bootstrap live probe audit",
        "",
        f"- probe: `{result['probePath']}`",
        "",
        "## Checks",
        "",
        "| check | value |",
        "|---|---:|",
    ]
    for key, value in result["checks"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines += [
        "",
        "## Remaining gaps",
        "",
        *[f"- {gap}" for gap in result["remainingGaps"]],
        "",
        result["conclusion"],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Audit a fresh browserless bootstrap collector probe.")
    parser.add_argument("--probe", type=Path, default=None)
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build_audit(args.probe)
    json_path = OUT_DIR / "fresh_bootstrap_live_probe_audit.json"
    md_path = OUT_DIR / "fresh_bootstrap_live_probe_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
