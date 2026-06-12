#!/usr/bin/env python3
from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
SEQ_DIR = PROTO / "fresh_sequence_probe"
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
    candidates: list[Path] = []
    for file in sorted(glob.glob(str(SEQ_DIR / "fresh_sequence_probe_*.json"))):
        path = Path(file)
        doc = read_json(path)
        steps = doc.get("steps") or []
        if doc.get("sent") is True and steps and all((s.get("response") or {}).get("status") for s in steps):
            candidates.append(path)
    if not candidates:
        raise RuntimeError(f"no sent sequence probe with responses under {SEQ_DIR}")
    return candidates[-1]


def verify_step_payload(step: dict[str, Any]) -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    req = step.get("request") or {}
    meta = req.get("meta") or {}
    params = dec.parse_form(req.get("body") or "")
    decoded = dec.decode_payload(params.get("payload", ""), meta.get("marker", ""), params.get("uuid", ""))
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    first = activities[0] if activities and isinstance(activities[0], dict) else {}
    first_d = first.get("d") if isinstance(first.get("d"), dict) else {}
    return {
        "name": req.get("name"),
        "markerMatch": decoded.get("markerMatch"),
        "jsonError": decoded.get("jsonError"),
        "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
        "form": {k: params.get(k) for k in ["uuid", "seq", "cs", "sid", "p1", "vid", "cts", "rsc"]},
        "activity": {
            "uuid": first_d.get("FUFvS1Mga38="),
            "url": first_d.get("SlpwEAw5eSc="),
            "hasPx3": "GUVjT1wnbn4=" in first_d,
            "joKeyValue": first_d.get("X08lRRkjIXQ=") or first_d.get("cR1LFzd8RSQ="),
        },
    }


def build_audit(probe_path: Path | None = None) -> dict[str, Any]:
    path = probe_path or latest_sent_probe()
    probe = read_json(path)
    steps = probe.get("steps") or []
    step_checks = []
    payloads = []
    for step in steps:
        decoded = step.get("decoded") or {}
        payload = verify_step_payload(step)
        payloads.append(payload)
        step_checks.append(
            {
                "name": (step.get("request") or {}).get("name"),
                "http200": (step.get("response") or {}).get("status") == 200,
                "decodedWithoutError": decoded.get("error") is None,
                "payloadMarkerMatches": payload.get("markerMatch") is True,
                "payloadJsonDecodes": payload.get("jsonError") is None,
                "hasPx3": decoded.get("hasPx3") is True,
                "hasPxde": decoded.get("hasPxde") is True,
                "hasPowResult": decoded.get("hasPowResult") is True,
                "hasSuccessHandler": decoded.get("hasSuccessHandler") is True,
                "handlers": decoded.get("handlers"),
            }
        )
    checks = {
        "probeSent": probe.get("sent") is True,
        "allStepsHttp200": bool(step_checks) and all(s["http200"] for s in step_checks),
        "allResponsesDecodedWithoutError": bool(step_checks) and all(s["decodedWithoutError"] for s in step_checks),
        "allRequestPayloadsDecode": bool(step_checks) and all(s["payloadMarkerMatches"] and s["payloadJsonDecodes"] for s in step_checks),
        "anyResponseHasPx3": any(s["hasPx3"] for s in step_checks),
        "allResponsesHavePxde": bool(step_checks) and all(s["hasPxde"] for s in step_checks),
        "anyResponseHasPowResult": any(s["hasPowResult"] for s in step_checks),
        "anyResponseHasSuccessHandler": any(s["hasSuccessHandler"] for s in step_checks),
    }
    checks["freshApiSequenceAdvanced"] = all(
        checks[k]
        for k in [
            "probeSent",
            "allStepsHttp200",
            "allResponsesDecodedWithoutError",
            "allRequestPayloadsDecode",
            "anyResponseHasPx3",
            "allResponsesHavePxde",
        ]
    )
    checks["pureProtocolReady"] = False
    return {
        "purpose": "Audit fresh stateful /api/v2/msft request sequence through observed req2/req3 templates.",
        "probePath": str(path.resolve()),
        "initialState": probe.get("initialState"),
        "finalState": probe.get("finalState"),
        "stepChecks": step_checks,
        "payloadChecks": payloads,
        "checks": checks,
        "remainingGaps": [
            "The fresh /api/v2/msft sequence advances through req2/req3 and returns decodable token updates, but still has no POW challenge.",
            "The runner still uses observed activity templates with fresh state substitutions; non-state fingerprint generation is not pure.",
            "Next target is the first fresh /assets/js/bundle request, because observed line 206 is where the first POW challenge appears.",
        ],
        "conclusion": (
            "Fresh browserless state advanced through additional /api/v2/msft requests with HTTP 200 and decodable responses. "
            "This proves multi-step state progression, but not POW or HUMAN success."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Fresh API sequence live probe audit",
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
    lines += ["", "## Step handlers", "", "| step | handlers |", "|---|---|"]
    for step in result["stepChecks"]:
        lines.append(f"| `{step['name']}` | `{step.get('handlers')}` |")
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
    json_path = OUT_DIR / "fresh_sequence_live_probe_audit.json"
    md_path = OUT_DIR / "fresh_sequence_live_probe_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
