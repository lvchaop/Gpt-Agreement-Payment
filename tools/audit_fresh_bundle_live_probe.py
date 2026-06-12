#!/usr/bin/env python3
from __future__ import annotations

import glob
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BUNDLE_DIR = PROTO / "fresh_bundle_probe"
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
    for file in sorted(glob.glob(str(BUNDLE_DIR / "fresh_bundle_probe_*.json"))):
        path = Path(file)
        doc = read_json(path)
        if doc.get("sent") is True and (doc.get("response") or {}).get("status") == 200:
            candidates.append(path)
    if not candidates:
        raise RuntimeError(f"no sent bundle probe under {BUNDLE_DIR}")
    return candidates[-1]


def pow_path_for_probe(probe_path: Path) -> Path:
    base = probe_path.name.removesuffix(".json")
    return PROTO / "pow_response" / f"pow_response_{base}.json"


def verify_request_payload(probe: dict[str, Any]) -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    material = probe.get("material") or {}
    meta = material.get("meta") or {}
    params = dec.parse_form(material.get("body") or "")
    decoded = dec.decode_payload(params.get("payload", ""), meta.get("marker", ""), params.get("uuid", ""))
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    first = activities[0] if activities and isinstance(activities[0], dict) else {}
    first_d = first.get("d") if isinstance(first.get("d"), dict) else {}
    return {
        "markerMatch": decoded.get("markerMatch"),
        "jsonError": decoded.get("jsonError"),
        "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
        "form": {k: params.get(k) for k in ["uuid", "seq", "pc", "sid", "p1", "vid", "cts", "rsc"]},
        "activity": {
            "uuid": first_d.get("FUFvS1Mga38="),
            "url": first_d.get("SlpwEAw5eSc="),
            "hasPx3": "GUVjT1wnbn4=" in first_d,
        },
        "containsChCtx": "&ch_ctx=1" in str(first_d.get("SlpwEAw5eSc=") or ""),
    }


def build_audit(probe_path: Path | None = None) -> dict[str, Any]:
    path = probe_path or latest_sent_probe()
    probe = read_json(path)
    decoded = probe.get("decoded") or {}
    payload = verify_request_payload(probe)
    pow_path = pow_path_for_probe(path)
    pow_doc = read_json(pow_path) if pow_path.exists() else {}
    checks = {
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "responseDecodedWithoutError": decoded.get("error") is None,
        "requestPayloadMarkerMatches": payload.get("markerMatch") is True,
        "requestPayloadJsonDecodes": payload.get("jsonError") is None,
        "requestContainsChCtx": payload.get("containsChCtx") is True,
        "responseHasPowResult": decoded.get("hasPowResult") is True,
        "powSolverOutputExists": pow_path.exists(),
        "powSolved": pow_doc.get("powPartCount") == 1 and len([r for r in pow_doc.get("results") or [] if r.get("matchesTarget") is True]) == 1,
        "responseHasSuccessHandler": decoded.get("hasSuccessHandler") is True,
    }
    checks["freshBundlePowProved"] = all(
        checks[k]
        for k in [
            "probeSent",
            "probeHttp200",
            "responseDecodedWithoutError",
            "requestPayloadMarkerMatches",
            "requestPayloadJsonDecodes",
            "requestContainsChCtx",
            "responseHasPowResult",
            "powSolverOutputExists",
            "powSolved",
        ]
    )
    checks["pureProtocolReady"] = False
    return {
        "purpose": "Audit first fresh /assets/js/bundle request and live POW challenge.",
        "probePath": str(path.resolve()),
        "powResponsePath": str(pow_path.resolve()),
        "request": {
            "bodySha256": (probe.get("material") or {}).get("bodySha256"),
            "bodyLenBytes": (probe.get("material") or {}).get("bodyLenBytes"),
            "payloadDecode": payload,
            "freshState": (probe.get("material") or {}).get("freshState"),
            "sources": (probe.get("material") or {}).get("sources"),
        },
        "response": {
            "status": (probe.get("response") or {}).get("status"),
            "bodyLen": (probe.get("response") or {}).get("bodyLen"),
            "elapsedSeconds": (probe.get("response") or {}).get("elapsedSeconds"),
            "handlers": decoded.get("handlers"),
            "parts": decoded.get("parts"),
        },
        "pow": {
            "powPartCount": pow_doc.get("powPartCount"),
            "solved": [
                {
                    "value": r.get("value"),
                    "target": r.get("target"),
                    "difficulty": r.get("difficulty"),
                    "elapsedMs": r.get("solveElapsedMs"),
                    "matchesTarget": r.get("matchesTarget"),
                }
                for r in pow_doc.get("results") or []
            ],
        },
        "checks": checks,
        "remainingGaps": [
            "This proves fresh live POW challenge and POW solve, not HUMAN success.",
            "Next request must use solved POW as OSk, compute fresh TBR9 via Ws.NQ with same fresh _pxUuid, and construct the PX561 bundle body.",
            "AEAx live-accepted generation, Bzt timing policy, and non-tail PX561 material remain unproved for the fresh session.",
        ],
        "conclusion": (
            "The first fresh browserless /assets/js/bundle request returned a live POW challenge and the offline solver solved it. "
            "This closes fresh POW acquisition, but not the accepted HUMAN packet."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Fresh bundle live POW audit",
        "",
        f"- probe: `{result['probePath']}`",
        f"- pow: `{result['powResponsePath']}`",
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
    json_path = OUT_DIR / "fresh_bundle_live_probe_audit.json"
    md_path = OUT_DIR / "fresh_bundle_live_probe_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
