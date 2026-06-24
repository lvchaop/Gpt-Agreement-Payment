#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "unmined_local_evidence_source_audit.json"


COVERED_DIRS = {
    "collector_decode",
    "cookie_timeline",
    "direct_webshare_attempt",
    "first_failure_overlap_attempt",
    "goal_audit",
    "hypothesis_reframe",
    "pow_response",
    "px561_compare",
    "reset_plan",
    "risk_verify",
    "risk_verify_build",
    "seq5_seq6_combo_probe",
    "trace_classification_v2",
    "wasm",
}

HIGH_VALUE_UNMINED_DIRS = {
    "asset_request_probe",
    "bundle_constructor",
    "bundle_payload_decode",
    "bundle_request_build",
    "captcha_head_probe",
    "collector_activity_dynamic",
    "collector_activity_patch_body",
    "collector_chain",
    "collector_field_map",
    "collector_live_probe",
    "collector_live_state_body",
    "collector_marker_state",
    "collector_replay_material",
    "collector_request_build",
    "collector_request_state",
    "collector_state",
    "fresh_bootstrap_probe",
    "fresh_bundle_probe",
    "fresh_bundle_progression_probe",
    "fresh_px561_probe",
    "fresh_px561_state",
    "fresh_second_probe",
    "fresh_sequence_probe",
    "head_delay_px561_probe",
    "payload_chain",
    "payload_replay",
    "pow",
    "px561_collector_handlers",
    "px561_constructor",
    "px561_protocol_inputs",
    "px561_static_field_map",
    "source_offsets",
    "stk_ns_probe",
    "tbr9",
}

SUCCESS_TOKENS = [
    "oIIoIooo|0",
    '"hasSuccessHandler": true',
    '"risk_verify_state_continue": true',
    '"create_account_redirectUrl": true',
    '"redirectUrl"',
    '"state":"continue"',
    '"state": "continue"',
]

NEGATIVE_TOKENS = [
    "oIIoIooo|-1",
    '"hasSuccessHandler": false',
    '"hasHistoricalNoBrowserSuccess0": false',
]


def safe_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def scan_file(path: Path) -> dict[str, Any]:
    text = safe_text(path)
    success_hits = [token for token in SUCCESS_TOKENS if token in text]
    negative_hits = [token for token in NEGATIVE_TOKENS if token in text]
    return {
        "path": str(path.resolve()),
        "size": path.stat().st_size,
        "successHits": success_hits,
        "negativeHits": negative_hits,
    }


def build() -> dict[str, Any]:
    rows = []
    unmined_success_files = []
    unmined_high_value_dirs = []

    for directory in sorted(p for p in PROTO.iterdir() if p.is_dir()):
        files = sorted(directory.glob("*.json"))
        if not files:
            continue
        file_scans = [scan_file(path) for path in files]
        success_files = [row for row in file_scans if row["successHits"]]
        negative_files = [row for row in file_scans if row["negativeHits"]]
        covered = directory.name in COVERED_DIRS
        high_value = directory.name in HIGH_VALUE_UNMINED_DIRS
        if not covered and high_value:
            unmined_high_value_dirs.append(directory.name)
        if not covered:
            unmined_success_files.extend(
                {
                    "dir": directory.name,
                    "path": row["path"],
                    "successHits": row["successHits"],
                }
                for row in success_files
            )
        rows.append(
            {
                "dir": directory.name,
                "jsonFileCount": len(files),
                "coveredByCurrentFinalGap": covered,
                "highValueUnmined": high_value and not covered,
                "successSignalFileCount": len(success_files),
                "negativeSignalFileCount": len(negative_files),
                "successSignalSample": [
                    {
                        "path": row["path"],
                        "successHits": row["successHits"],
                    }
                    for row in success_files[:5]
                ],
                "negativeSignalSample": [
                    {
                        "path": row["path"],
                        "negativeHits": row["negativeHits"],
                    }
                    for row in negative_files[:5]
                ],
            }
        )

    high_value_unmined_rows = [row for row in rows if row["highValueUnmined"]]
    checks = {
        "directoryCount": len(rows),
        "coveredDirectoryCount": sum(1 for row in rows if row["coveredByCurrentFinalGap"]),
        "uncoveredDirectoryCount": sum(1 for row in rows if not row["coveredByCurrentFinalGap"]),
        "highValueUnminedDirectoryCount": len(high_value_unmined_rows),
        "unminedSuccessSignalFileCount": len(unmined_success_files),
        "hasUnminedSuccessSignal": len(unmined_success_files) > 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    decision = {
        "goalComplete": False,
        "readyForFreshExperiment": False,
        "reason": (
            "Additional local evidence directories exist outside the current final-gap artifact. "
            "They must be triaged before treating the server-internal/unobserved-state gap as fully exhausted."
            if checks["highValueUnminedDirectoryCount"]
            else "No high-value local evidence directories remain outside the current final-gap artifact."
        ),
        "nextArtifact": str((BASE / "high_value_unmined_evidence_triage.json").resolve())
        if checks["highValueUnminedDirectoryCount"]
        else None,
        "nextScript": str((REPO / "tools/build_high_value_unmined_evidence_triage.py").resolve())
        if checks["highValueUnminedDirectoryCount"]
        else None,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Audit whether local evidence directories outside the current final-gap artifact may still contain relevant success/failure proof.",
        "coveredDirs": sorted(COVERED_DIRS),
        "highValueUnminedDirs": sorted(unmined_high_value_dirs),
        "rows": rows,
        "unminedSuccessSignalFiles": unmined_success_files[:100],
        "checks": checks,
        "decision": decision,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
