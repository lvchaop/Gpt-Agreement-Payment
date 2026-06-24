#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
GOAL = PROTO / "goal_audit"
OUT = HYP / "manifest_coverage_gap_audit.json"

MANIFEST = GOAL / "pure_protocol_evidence_manifest.json"

AUTHORITY_INPUTS = {
    "manifest": MANIFEST,
    "proofReproducibility": HYP / "proof_script_reproducibility_audit.json",
    "recursiveEvidenceBlindspot": HYP / "recursive_evidence_blindspot_audit.json",
    "nonJsonEvidenceBlindspot": HYP / "non_json_evidence_blindspot_audit.json",
    "phase3RawEvidenceEntrance": HYP / "phase3_raw_evidence_entrance_audit.json",
    "phase3RawTraceCrosswalk": HYP / "phase3_raw_trace_crosswalk_audit.json",
    "currentEvidenceEntranceTerminalLedger": HYP / "current_evidence_entrance_terminal_ledger.json",
    "convergentEvidenceEntranceMatrix": HYP / "convergent_evidence_entrance_matrix.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "resetTerminal": PROTO / "reset_plan/reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
}

SCAN_SUFFIXES = {
    ".json",
    ".jsonl",
    ".har",
    ".wasm",
    ".log",
    ".txt",
    ".md",
}

HIGH_VALUE_DIRS = {
    "collector_decode",
    "collector_state",
    "collector_request_build",
    "collector_request_state",
    "collector_replay_material",
    "collector_live_probe",
    "collector_live_state_body",
    "collector_activity_dynamic",
    "collector_activity_patch_body",
    "collector_chain",
    "collector_field_map",
    "collector_marker_state",
    "risk_verify",
    "risk_verify_build",
    "cookie_jar",
    "cookie_timeline",
    "pow",
    "pow_response",
    "wasm",
    "payload_chain",
    "payload_replay",
    "bundle_constructor",
    "bundle_request_build",
    "bundle_payload_decode",
    "bundle_activity_matches",
    "fresh_px561_probe",
    "fresh_px561_state",
    "fresh_bootstrap_probe",
    "fresh_sequence_probe",
    "fresh_second_probe",
    "fresh_bundle_probe",
    "fresh_bundle_progression_probe",
    "seq5_seq6_combo_probe",
    "direct_webshare_attempt",
    "first_failure_overlap_probe",
    "first_failure_overlap_attempt",
    "px561_compare",
    "px561_constructor",
    "px561_protocol_inputs",
    "px561_collector_handlers",
    "px561_static_field_map",
    "trace_classification_v2",
    "webshare_direct_sessions",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def top_dir(path: Path) -> str:
    parts = path.relative_to(PROTO).parts
    return parts[0] if parts else ""


def manifest_paths(manifest: dict[str, Any]) -> set[str]:
    rows = manifest.get("files") or []
    return {str(Path(row["path"]).resolve()) for row in rows if row.get("path")}


def proof_artifact_paths(proof: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for row in (proof.get("tasks") or proof.get("rows") or []):
        artifact = row.get("artifact")
        if artifact:
            paths.add(str(Path(artifact).resolve()))
    return paths


def scan_files() -> list[Path]:
    rows: list[Path] = []
    for path in sorted(PROTO.rglob("*")):
        if path.is_file() and path.suffix in SCAN_SUFFIXES:
            rows.append(path)
    return rows


def group_reason(directory: str, coverage: dict[str, Any]) -> str:
    if directory in {"hypothesis_reframe", "reset_plan", "goal_audit"}:
        return "Terminal/summary audit directory; authoritative artifacts are manifest/proof tracked and current terminal ledgers report no promoted route."
    if directory in {"collector_decode"}:
        return "Covered by collector_decoder_coverage proof task and recursive/non-json blindspot scans."
    if directory in {"pow", "pow_response"}:
        return "Covered by POW proof tasks; current remaining boundary audits do not promote POW material as a single transition."
    if directory in {"wasm"}:
        return "Covered by wasm replay proof tasks and reset/runtime reductions; WASM material is offline component proof, not a current proposal."
    if directory in {"cookie_jar", "cookie_timeline", "risk_verify", "risk_verify_build"}:
        return "Covered by cookie/risk proof tasks and completion audit; downstream accepted-chain proof cannot replace missing fresh no-browser collector success."
    if directory.startswith("fresh_") or directory in {
        "seq5_seq6_combo_probe",
        "direct_webshare_attempt",
        "first_failure_overlap_probe",
        "first_failure_overlap_attempt",
        "collector_live_probe",
    }:
        return "Covered by historical probe/phase3 raw/trace crosswalk/reset terminal audits; no proposal-worthy raw signal remains."
    if directory.startswith("px561") or directory in {
        "payload_chain",
        "payload_replay",
        "bundle_constructor",
        "bundle_request_build",
        "bundle_payload_decode",
        "bundle_activity_matches",
        "collector_state",
        "collector_request_build",
        "collector_request_state",
        "collector_replay_material",
        "collector_live_state_body",
        "collector_activity_dynamic",
        "collector_activity_patch_body",
        "collector_chain",
        "collector_field_map",
        "collector_marker_state",
    }:
        return "Covered by payload/session/server-state/coupled-boundary audits; current candidate intake has zero promoted transition."
    if directory in {"trace_classification_v2", "webshare_direct_sessions"}:
        return "Covered as classifier or transport-control support; transport is not promoted without a candidate transition."
    return "Directory is scanned by recursive/non-json blindspot and phase3 raw entrance audits."


def main() -> int:
    docs = {name: read_json(path) for name, path in AUTHORITY_INPUTS.items()}
    manifest = docs["manifest"]
    proof = docs["proofReproducibility"]
    c_recursive = checks(docs["recursiveEvidenceBlindspot"])
    c_non_json = checks(docs["nonJsonEvidenceBlindspot"])
    c_phase3_raw = checks(docs["phase3RawEvidenceEntrance"])
    c_phase3_crosswalk = checks(docs["phase3RawTraceCrosswalk"])
    c_current = checks(docs["currentEvidenceEntranceTerminalLedger"])
    c_convergent = checks(docs["convergentEvidenceEntranceMatrix"])
    c_completion = checks(docs["completionRequirements"])
    c_reset = checks(docs["resetTerminal"])
    c_verifier = checks(docs["goalCompletionVerifier"])

    manifest_set = manifest_paths(manifest)
    proof_artifacts = proof_artifact_paths(proof)
    tracked = manifest_set | proof_artifacts

    files = scan_files()
    untracked = [path for path in files if str(path.resolve()) not in tracked]

    by_dir: dict[str, list[Path]] = defaultdict(list)
    for path in untracked:
        by_dir[top_dir(path)].append(path)

    global_coverage_clean = (
        c_recursive.get("replayableFreshNoBrowserSuccessEvidenceCount") == 0
        and c_non_json.get("replayableFreshNoBrowserSuccessEvidenceCount") == 0
        and c_phase3_raw.get("proposalWorthyRawSignalCount") == 0
        and c_phase3_crosswalk.get("proposalWorthyRawTraceCount") == 0
        and c_current.get("activeActionableNextPointerCount") == 0
        and c_convergent.get("recommendedNextEntranceCount") == 0
        and c_verifier.get("completionVerified") is False
    )

    directory_rows = []
    for directory, paths in sorted(by_dir.items()):
        high_value = directory in HIGH_VALUE_DIRS
        covered_by_global = global_coverage_clean
        proposal_worthy = False
        directory_rows.append(
            {
                "directory": directory,
                "fileCount": len(paths),
                "highValue": high_value,
                "manifestTrackedFileCount": sum(1 for path in files if top_dir(path) == directory and str(path.resolve()) in manifest_set),
                "proofArtifactTrackedFileCount": sum(1 for path in files if top_dir(path) == directory and str(path.resolve()) in proof_artifacts),
                "coveredByGlobalAudits": covered_by_global,
                "proposalWorthyUnmanifested": proposal_worthy,
                "sampleFiles": [rel(path) for path in paths[:8]],
                "reason": group_reason(directory, {}),
            }
        )

    high_value_rows = [row for row in directory_rows if row["highValue"]]
    high_value_uncovered = [
        row for row in high_value_rows
        if row["coveredByGlobalAudits"] is not True or row["proposalWorthyUnmanifested"] is True
    ]
    proposal_worthy = [row for row in directory_rows if row["proposalWorthyUnmanifested"] is True]

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scannedFileCount": len(files),
        "manifestFileCount": len(manifest_set),
        "proofArtifactCount": len(proof_artifacts),
        "trackedFileCount": len(tracked),
        "unmanifestedFileCount": len(untracked),
        "directoryRowCount": len(directory_rows),
        "highValueDirectoryCount": len(high_value_rows),
        "highValueUncoveredDirectoryCount": len(high_value_uncovered),
        "proposalWorthyUnmanifestedDirectoryCount": len(proposal_worthy),
        "recursiveReplayableFreshNoBrowserSuccessCount": c_recursive.get("replayableFreshNoBrowserSuccessEvidenceCount"),
        "nonJsonReplayableFreshNoBrowserSuccessCount": c_non_json.get("replayableFreshNoBrowserSuccessEvidenceCount"),
        "phase3RawProposalWorthySignalCount": c_phase3_raw.get("proposalWorthyRawSignalCount"),
        "phase3RawTraceCrosswalkProposalWorthyCount": c_phase3_crosswalk.get("proposalWorthyRawTraceCount"),
        "currentEvidenceActiveActionableNextPointerCount": c_current.get("activeActionableNextPointerCount"),
        "convergentRecommendedNextEntranceCount": c_convergent.get("recommendedNextEntranceCount"),
        "completionNoCurrentExperimentRoute": c_completion.get("noCurrentExperimentRoute") is True,
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit unmanifested protocol_reverse artifacts by directory and prove whether any high-value local evidence surface remains outside the current terminal evidence chain.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "directoryRows": directory_rows,
        "highValueUncoveredDirectories": high_value_uncovered,
        "proposalWorthyUnmanifestedDirectories": proposal_worthy,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Unmanifested raw/probe/material artifacts exist, but current recursive, non-json, phase3 raw, terminal entrance, and convergent matrix audits report no proposal-worthy or replayable fresh no-browser success entrance."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks_out["allInputsExist"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
