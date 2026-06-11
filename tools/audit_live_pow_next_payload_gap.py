#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any

from decode_bundle_payload_with_marker import decode_payload


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/pow"

DEFAULT_LIVE_PROBE = REPO / "output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.json"
DEFAULT_POW = REPO / "output/protocol_reverse/pow_response/pow_response_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.json"
DEFAULT_NEXT_BODY = REPO / "output/protocol_reverse/collector_live_state_body/collector_live_state_body_hcxwyrtiudbg_1780949301_idx1.json"

TERMS = ["PX561", "TBR9Ugl7emA=", "AEAxBkUsPjQ=", "Bzt2fUFRcw==", "OSkIb39DDA=="]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def text_contains(value: Any, terms: list[str]) -> dict[str, bool]:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return {term: term in text for term in terms}


def activity_summary(parsed: Any) -> list[dict[str, Any]]:
    if not isinstance(parsed, list):
        return []
    rows = []
    for idx, item in enumerate(parsed):
        if not isinstance(item, dict):
            continue
        d = item.get("d") if isinstance(item.get("d"), dict) else {}
        rows.append(
            {
                "index": idx,
                "type": item.get("t"),
                "keyCount": len(d),
                "contains": text_contains(item, TERMS),
                "tail": {key: d.get(key) for key in TERMS if key in d},
            }
        )
    return rows


def pow_summary(pow_doc: dict[str, Any]) -> dict[str, Any]:
    results = pow_doc.get("results") if isinstance(pow_doc.get("results"), list) else []
    return {
        "powPartCount": pow_doc.get("powPartCount"),
        "allSolved": bool(results) and all(r.get("matchesTarget") is True for r in results),
        "results": [
            {
                "raw": r.get("raw"),
                "target": r.get("target"),
                "difficulty": r.get("difficulty"),
                "i": r.get("i"),
                "value": r.get("value"),
                "sha256": r.get("sha256"),
                "matchesTarget": r.get("matchesTarget"),
            }
            for r in results
        ],
    }


def decoded_handlers_summary(live_probe: dict[str, Any]) -> dict[str, Any]:
    decoded = live_probe.get("decoded") or {}
    parts = decoded.get("parts") if isinstance(decoded.get("parts"), list) else []
    return {
        "handlers": decoded.get("handlers") or [],
        "hasSuccessHandler": decoded.get("hasSuccessHandler"),
        "hasPx3": decoded.get("hasPx3"),
        "hasPxde": decoded.get("hasPxde"),
        "hasPowResult": decoded.get("hasPowResult"),
        "powParts": [p for p in parts if str(p).startswith("IooIIo|")],
    }


def analyze(live_probe_path: Path, pow_path: Path, next_body_path: Path) -> dict[str, Any]:
    live_probe = load_json(live_probe_path)
    pow_doc = load_json(pow_path)
    next_body = load_json(next_body_path)
    fields = parse_form(next_body.get("body") or "")
    marker = str((next_body.get("liveState") or {}).get("marker") or next_body.get("newMarker") or "")
    try:
        decoded_next = decode_payload(fields.get("payload", ""), marker, fields.get("uuid", ""))
        decode_error = None
    except Exception as exc:
        decoded_next = {
            "markerMatch": None,
            "jsonError": str(exc),
            "decodedText": "",
            "json": None,
        }
        decode_error = f"{type(exc).__name__}: {exc}"
    parsed = decoded_next.get("json")
    activities = activity_summary(parsed)
    pow_info = pow_summary(pow_doc)
    solved_values = [r.get("value") for r in pow_info["results"] if r.get("value")]
    decoded_text = str(decoded_next.get("decodedText") or "")

    checks = {
        "liveProbeHasPowChallenge": bool(decoded_handlers_summary(live_probe)["powParts"]),
        "liveProbeHasNoSuccessHandler": decoded_handlers_summary(live_probe)["hasSuccessHandler"] is False,
        "powSolverSolvedAll": pow_info["allSolved"],
        "nextBodyDecoded": decoded_next.get("jsonError") is None,
        "nextBodyMarkerMatches": decoded_next.get("markerMatch") is True,
        "nextBodyHasPx561": any(row["type"] == "PX561" for row in activities),
        "nextBodyHasTbr9": "TBR9Ugl7emA=" in decoded_text,
        "nextBodyHasOskKey": "OSkIb39DDA==" in decoded_text,
        "nextBodyContainsSolvedPowValue": any(value in decoded_text for value in solved_values),
    }
    return {
        "purpose": "Audit whether the current live POW solver output is already injected into the next pure-protocol collector payload.",
        "inputs": {
            "liveProbe": str(live_probe_path.resolve()),
            "powResponse": str(pow_path.resolve()),
            "nextBody": str(next_body_path.resolve()),
        },
        "liveProbe": decoded_handlers_summary(live_probe),
        "pow": pow_info,
        "nextBody": {
            "url": next_body.get("url"),
            "fieldValues": next_body.get("fieldValues"),
            "liveState": next_body.get("liveState"),
            "decoded": {
                "markerMatch": decoded_next.get("markerMatch"),
                "jsonError": decoded_next.get("jsonError"),
                "decodeError": decode_error,
                "activityCount": len(activities),
                "activityTypes": [row["type"] for row in activities],
                "contains": text_contains(decoded_text, TERMS + solved_values),
                "activitiesWithTargets": [row for row in activities if any(row["contains"].values())],
            },
        },
        "checks": checks,
        "conclusion": (
            "The live POW challenge is solved, but the current next-body artifact cannot be decoded with the available marker/base64 method, so it does not prove solved POW injection into PX561 OSk/TBR9."
            if checks["powSolverSolvedAll"] and not checks["nextBodyDecoded"]
            else (
                "The live POW challenge is solved, but the decoded next-body artifact does not contain the solved POW value in PX561 OSk/TBR9."
                if checks["powSolverSolvedAll"] and not checks["nextBodyContainsSolvedPowValue"]
                else "The current artifacts do not prove the live POW -> next payload gap."
            )
        ),
        "nextGap": (
            "Need a PX561 activity constructor that inserts OSkIb39DDA== from the solved POW value and Bzt2fUFRcw== from solve elapsed, while TBR9Ugl7emA= remains a separate producer gap."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit live POW solver output against the current next collector payload artifact.")
    parser.add_argument("--live-probe", type=Path, default=DEFAULT_LIVE_PROBE)
    parser.add_argument("--pow", type=Path, default=DEFAULT_POW)
    parser.add_argument("--next-body", type=Path, default=DEFAULT_NEXT_BODY)
    parser.add_argument("--out-prefix", default="live_pow_next_payload_gap_audit")
    args = parser.parse_args()
    result = analyze(args.live_probe, args.pow, args.next_body)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"{args.out_prefix}.json"
    out_md = OUT_DIR / f"{args.out_prefix}.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# live POW -> next payload gap audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        md.append(f"- {key}: `{value}`")
    md += ["", "## POW results", ""]
    for row in result["pow"]["results"]:
        md.append(f"- i={row['i']} value={row['value']} matchesTarget={row['matchesTarget']}")
    md += ["", "## Next body", ""]
    md.append(f"- activityTypes: `{result['nextBody']['decoded']['activityTypes']}`")
    md.append(f"- contains: `{result['nextBody']['decoded']['contains']}`")
    md += ["", "## Conclusion", "", result["conclusion"], "", "## Next gap", "", result["nextGap"], ""]
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
