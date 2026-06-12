#!/usr/bin/env python3
from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
SECOND_DIR = PROTO / "fresh_second_probe"
OUT_DIR = PROTO / "goal_audit"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_sent_probe() -> Path:
    sent: list[Path] = []
    for file in sorted(glob.glob(str(SECOND_DIR / "fresh_second_probe_*.json"))):
        path = Path(file)
        doc = read_json(path)
        if doc.get("sent") is True and (doc.get("response") or {}).get("status") is not None:
            sent.append(path)
    if not sent:
        raise RuntimeError(f"no sent second probe with response under {SECOND_DIR}")
    return sent[-1]


def verify_request_payload(probe: dict[str, Any]) -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    material = probe.get("material") or {}
    state = material.get("derivedState") or {}
    fresh = material.get("freshState") or {}
    params = dec.parse_form(material.get("body") or "")
    decoded = dec.decode_payload(params.get("payload", ""), state.get("marker", ""), params.get("uuid", ""))
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    first = activities[0] if activities and isinstance(activities[0], dict) else {}
    first_d = first.get("d") if isinstance(first.get("d"), dict) else {}
    return {
        "markerMatch": decoded.get("markerMatch"),
        "jsonError": decoded.get("jsonError"),
        "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
        "form": {k: params.get(k) for k in ["uuid", "seq", "cs", "sid", "p1", "vid", "cts", "rsc"]},
        "activityState": {
            "uuid": first_d.get("FUFvS1Mga38="),
            "url": first_d.get("SlpwEAw5eSc="),
            "jo": first_d.get("cR1LFzd8RSQ="),
            "zo": first_d.get("eEQCDj4mDz0="),
            "qo": first_d.get("JxcdHWJzESc="),
            "gl": first_d.get("JnZcfGMXVEo="),
            "hasPx3": "GUVjT1wnbn4=" in first_d,
        },
        "uuidConsistent": params.get("uuid") == fresh.get("uuid") == first_d.get("FUFvS1Mga38="),
        "p1Consistent": params.get("p1") == fresh.get("p1") and str(first_d.get("SlpwEAw5eSc=") or "").endswith(str(fresh.get("p1"))),
        "formUsesBootstrapState": (
            params.get("cs") == state.get("cs")
            and params.get("vid") == state.get("vid")
            and params.get("cts") == state.get("cts")
            and params.get("sid") == state.get("sidWithKlJo")
        ),
    }


def build_audit(probe_path: Path | None = None) -> dict[str, Any]:
    path = probe_path or latest_sent_probe()
    probe = read_json(path)
    decoded = probe.get("decoded") or {}
    handlers = decoded.get("handlers") or []
    payload = verify_request_payload(probe)
    checks = {
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "responseDecodedWithoutError": decoded.get("error") is None,
        "requestPayloadMarkerMatches": payload.get("markerMatch") is True,
        "requestPayloadJsonDecodes": payload.get("jsonError") is None,
        "requestUuidFreshAndConsistent": payload.get("uuidConsistent") is True,
        "requestP1FreshAndConsistent": payload.get("p1Consistent") is True,
        "requestUsesBootstrapState": payload.get("formUsesBootstrapState") is True,
        "responseHasPx3": decoded.get("hasPx3") is True,
        "responseHasPxde": decoded.get("hasPxde") is True,
        "responseHasPowResult": decoded.get("hasPowResult") is True,
        "responseHasSuccessHandler": decoded.get("hasSuccessHandler") is True,
    }
    checks["freshSecondRequestAdvancedState"] = all(
        checks[k]
        for k in [
            "probeSent",
            "probeHttp200",
            "responseDecodedWithoutError",
            "requestPayloadMarkerMatches",
            "requestPayloadJsonDecodes",
            "requestUuidFreshAndConsistent",
            "requestP1FreshAndConsistent",
            "requestUsesBootstrapState",
            "responseHasPx3",
            "responseHasPxde",
        ]
    )
    checks["pureProtocolReady"] = False
    return {
        "purpose": "Audit live fresh second /api/v2/msft request after decoded bootstrap state.",
        "probePath": str(path.resolve()),
        "request": {
            "bodySha256": (probe.get("material") or {}).get("bodySha256"),
            "bodyLenBytes": (probe.get("material") or {}).get("bodyLenBytes"),
            "payloadDecode": payload,
            "derivedState": (probe.get("material") or {}).get("derivedState"),
            "sources": (probe.get("material") or {}).get("sources"),
        },
        "response": {
            "status": (probe.get("response") or {}).get("status"),
            "bodyLen": (probe.get("response") or {}).get("bodyLen"),
            "elapsedSeconds": (probe.get("response") or {}).get("elapsedSeconds"),
            "handlers": handlers,
            "parts": decoded.get("parts"),
        },
        "checks": checks,
        "remainingGaps": [
            "The second live request advances fresh state and returns updated _px3/_pxde, but still has no POW challenge and no oIIoIooo|0.",
            "The activity body still uses observed line85 fingerprint template with state substitutions; non-state fingerprint generation is not pure.",
            "Next target is a stateful runner for request 3/4 templates and then the first /assets/js/bundle request, preserving returned cookie/token updates.",
        ],
        "conclusion": (
            "The fresh bootstrap state was accepted by a second browserless collector request: the request decoded locally, used bootstrap sid/cs/vid/cts/Jo, "
            "and live response returned decodable _px3/_pxde. This proves state can be advanced one step, but not POW or HUMAN success."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Fresh second request live probe audit",
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = build_audit()
    json_path = OUT_DIR / "fresh_second_live_probe_audit.json"
    md_path = OUT_DIR / "fresh_second_live_probe_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
