#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"

RUNS = [
    "ni109xdjp5zp_1780948211",
    "j0t8van4qyhm_1781119142",
    "a9quwrn1c1j3_1781189801",
    "wdyobrwf3wkl_1781190721",
    "s00ld1lglrw0_1781191381",
]


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def collector_handlers(run: str) -> dict[str, Any]:
    path = PROTO / f"collector_decode/collector_decode_{run}.json"
    doc = load_json(path) or {}
    parts = [
        part
        for entry in doc.get("decodedEntries") or []
        for part in entry.get("parts") or []
    ]
    return {
        "path": str(path),
        "exists": path.exists(),
        "hasSuccess": any(str(part) == "oIIoIooo|0" or str(part).startswith("oIIoIooo|0|") for part in parts),
        "hasFailure": any(str(part) == "oIIoIooo|-1" or str(part).startswith("oIIoIooo|-1|") for part in parts),
        "powPartCount": sum(1 for part in parts if str(part).startswith("IooIIo|")),
    }


def pow_summary(run: str) -> dict[str, Any]:
    path = PROTO / f"pow_response/pow_response_{run}.json"
    doc = load_json(path) or {}
    rows = doc.get("results") or []
    return {
        "path": str(path),
        "exists": path.exists(),
        "powPartCount": doc.get("powPartCount"),
        "solvedCount": sum(1 for row in rows if row.get("matchesTarget") is True),
        "values": [row.get("value") for row in rows if row.get("matchesTarget") is True],
    }


def tbr9_summary(run: str) -> dict[str, Any]:
    path = PROTO / f"wasm/captcha_wasm_nq_replay_{run}.json"
    doc = load_json(path) or {}
    rows = doc.get("pxUuidReplay") or []
    return {
        "path": str(path),
        "exists": path.exists(),
        "pxUuidReplayMatchesAnyTrace": (doc.get("checks") or {}).get("pxUuidReplayMatchesAnyTrace"),
        "runtimePxUuidEvidence": bool(doc.get("runtimePxUuidEvidence")),
        "matchedValues": [
            {
                "line": row.get("line"),
                "value": row.get("value"),
                "runtimePxUuid": row.get("runtimePxUuid"),
            }
            for row in rows
            if row.get("matchesTrace") is True
        ],
    }


def bundle_summary(run: str) -> dict[str, Any]:
    build = PROTO / f"bundle_request_build/bundle_request_build_{run}.json"
    decode = PROTO / f"bundle_payload_decode/bundle_payload_decode_{run}.json"
    build_doc = load_json(build) or {}
    decode_doc = load_json(decode) or {}
    build_rows = build_doc.get("rows") or []
    decode_rows = decode_doc.get("rows") or []
    return {
        "buildPath": str(build),
        "decodePath": str(decode),
        "buildExists": build.exists(),
        "decodeExists": decode.exists(),
        "px561BuildRows": [
            {"requestLine": row.get("requestLine"), "seq": row.get("seq"), "contains": row.get("contains")}
            for row in build_rows
            if (row.get("contains") or {}).get("PX561")
        ],
        "px561DecodeRows": [
            {
                "requestLine": row.get("requestLine"),
                "seq": row.get("seq"),
                "activityTypes": row.get("activityTypes"),
                "contains": row.get("contains"),
                "markerMatch": row.get("markerMatch"),
            }
            for row in decode_rows
            if "PX561" in (row.get("activityTypes") or [])
        ],
    }


def main() -> int:
    run_rows = []
    for run in RUNS:
        collector = collector_handlers(run)
        pow_info = pow_summary(run)
        tbr = tbr9_summary(run)
        bundle = bundle_summary(run)
        checks = {
            "hasCollectorSuccess": collector["hasSuccess"],
            "hasPowSolved": pow_info["exists"] and pow_info["solvedCount"] > 0,
            "hasFreshTbr9Replay": bool(tbr["exists"] and tbr["pxUuidReplayMatchesAnyTrace"] is True),
            "hasBundlePx561Decode": bool(bundle["decodeExists"] and bundle["px561DecodeRows"]),
            "hasBundlePx561Build": bool(bundle["buildExists"] and bundle["px561BuildRows"]),
        }
        checks["hasSameSessionCoherentMaterials"] = all(checks.values())
        run_rows.append(
            {
                "run": run,
                "collector": collector,
                "pow": pow_info,
                "tbr9": tbr,
                "bundle": bundle,
                "checks": checks,
            }
        )

    coherent = [row["run"] for row in run_rows if row["checks"]["hasSameSessionCoherentMaterials"]]
    near = [
        {
            "run": row["run"],
            "missing": [key for key, value in row["checks"].items() if key != "hasSameSessionCoherentMaterials" and not value],
        }
        for row in run_rows
    ]
    result = {
        "purpose": "Audit which existing runs contain same-session materials needed for pure-protocol HUMAN success construction: collector success, solved POW, fresh TBR9 replay, and bundle PX561 outer/inner state.",
        "runs": run_rows,
        "summary": {
            "sameSessionCoherentRuns": coherent,
            "nearCandidates": near,
            "goalReadyFromExistingArtifacts": bool(coherent),
        },
        "conclusion": (
            "No existing artifact set currently has all same-session coherent materials. "
            "Recent successful runs have fresh TBR9 replay plus solved POW after this audit, but lack bundle_request_build/bundle_payload_decode artifacts. "
            "Older accepted runs have bundle/PX561 and POW artifacts but lack fresh _pxUuid-backed TBR9 replay artifacts."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "same_session_material_coverage_audit.json"
    out_md = OUT_DIR / "same_session_material_coverage_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Same-session material coverage audit", "", "## Summary", ""]
    lines.append(f"- sameSessionCoherentRuns: `{coherent}`")
    lines.append(f"- goalReadyFromExistingArtifacts: `{result['summary']['goalReadyFromExistingArtifacts']}`")
    lines += [
        "",
        "| run | success | POW | TBR9 replay | bundle decode PX561 | bundle build PX561 | missing |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row, near_row in zip(run_rows, near):
        c = row["checks"]
        lines.append(
            f"| `{row['run']}` | {c['hasCollectorSuccess']} | {c['hasPowSolved']} | {c['hasFreshTbr9Replay']} | "
            f"{c['hasBundlePx561Decode']} | {c['hasBundlePx561Build']} | `{near_row['missing']}` |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "summary": result["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
