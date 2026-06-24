#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
GOAL = PROTO / "goal_audit"
PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
OUT = GOAL / "pure_protocol_evidence_manifest.json"

FILES = {
    "implementationPlan": PLAN,
    "convergentExecutionPlan": ROOT / "docs/pure-protocol-human-evidence-convergent-plan.md",
    "currentExecutionPlan": ROOT / "docs/pure-protocol-human-evidence-first-current-plan.md",
    "methodologyImplementationPlan": ROOT / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "candidateIntakeScript": ROOT / "tools/build_promoted_transition_candidate_intake.py",
    "minimalTransitionScript": ROOT / "tools/run_minimal_promoted_transition_experiment.py",
    "evidenceGatedPocScript": ROOT / "tools/run_evidence_gated_end_to_end_pure_protocol_poc.py",
    "finalReplayScript": ROOT / "tools/build_final_pure_protocol_replay_audit.py",
    "completionRequirementsScript": ROOT / "tools/build_pure_protocol_completion_requirements_audit.py",
    "goalCompletionVerifierScript": ROOT / "tools/verify_pure_protocol_goal_completion.py",
    "traceClassifierRawCoverageGapScript": ROOT / "tools/audit_trace_classifier_raw_coverage_gap.py",
    "remainingBoundaryProposalGateScript": ROOT / "tools/build_remaining_boundary_proposal_gate_audit.py",
    "candidateSourceContradictionLedgerScript": ROOT / "tools/build_candidate_source_contradiction_ledger.py",
    "serverStateValueConsumptionLedgerScript": ROOT / "tools/build_server_state_value_consumption_ledger.py",
    "coupledBoundaryTerminalLedgerScript": ROOT / "tools/build_coupled_boundary_terminal_ledger.py",
    "currentEvidenceEntranceTerminalLedgerScript": ROOT / "tools/build_current_evidence_entrance_terminal_ledger.py",
    "convergentEvidenceEntranceMatrixScript": ROOT / "tools/build_convergent_evidence_entrance_matrix.py",
    "manifestCoverageGapScript": ROOT / "tools/build_manifest_coverage_gap_audit.py",
    "liveRunnerGateScript": ROOT / "tools/build_live_runner_gate_audit.py",
    "objectiveRequirementCrosswalkScript": ROOT / "tools/build_objective_requirement_crosswalk.py",
    "promotionPredicateBlockerCrosswalkScript": ROOT / "tools/build_promotion_predicate_blocker_crosswalk.py",
    "candidateExecutorReadinessScript": ROOT / "tools/build_candidate_executor_readiness_audit.py",
    "hypothesisTreeCurrentAuthorityScript": ROOT / "tools/build_hypothesis_tree_current_authority_audit.py",
    "nearestMissPromotionCandidateScript": ROOT / "tools/build_nearest_miss_promotion_candidate_audit.py",
    "nearestMissBlockerResolutionScript": ROOT / "tools/build_nearest_miss_blocker_resolution_audit.py",
    "remainingNearestMissResolutionScript": ROOT / "tools/build_remaining_nearest_miss_resolution_audit.py",
    "exhaustivePromotionCandidateResolutionScript": ROOT / "tools/build_exhaustive_promotion_candidate_resolution_audit.py",
    "nextEvidenceSurfaceDiscoveryScript": ROOT / "tools/build_next_evidence_surface_discovery_audit.py",
    "externalOutputSurfaceAuditScript": ROOT / "tools/build_external_output_surface_audit.py",
    "evidencePackageSurfaceAuditScript": ROOT / "tools/build_evidence_package_surface_audit.py",
    "ctfRegOutputSurfaceAuditScript": ROOT / "tools/build_ctf_reg_output_surface_audit.py",
    "auxiliaryTraceSurfaceAuditScript": ROOT / "tools/build_auxiliary_trace_surface_audit.py",
    "stalePositiveSignalAuthorityScript": ROOT / "tools/build_stale_positive_signal_authority_audit.py",
    "localTraceEvidenceFreshnessScript": ROOT / "tools/build_local_trace_evidence_freshness_audit.py",
    "unclassifiedTraceSignalReductionScript": ROOT / "tools/build_unclassified_trace_signal_reduction_audit.py",
    "browserSuccessChainClassificationBacklogScript": ROOT / "tools/build_browser_success_chain_classification_backlog.py",
    "browserSuccessChainServerVisibleDiffScript": ROOT / "tools/build_browser_success_chain_server_visible_diff_audit.py",
    "browserSuccessPayloadPcSessionLineageScript": ROOT / "tools/build_browser_success_payload_pc_session_lineage_audit.py",
    "collectorResponseHandlerValueLineageScript": ROOT / "tools/build_collector_response_handler_value_lineage_audit.py",
    "downstreamSuccessWithoutCollectorDecodeScript": ROOT / "tools/build_downstream_success_without_collector_decode_audit.py",
    "collectorMaterialOnlyResponseClassScript": ROOT / "tools/build_collector_material_only_response_class_audit.py",
    "lowValueUnclassifiedTraceClosureScript": ROOT / "tools/build_low_value_unclassified_trace_closure_audit.py",
    "unclassifiedTraceClassClosureLedgerScript": ROOT / "tools/build_unclassified_trace_class_closure_ledger.py",
    "proofReproducibilityScript": ROOT / "tools/build_proof_script_reproducibility_audit.py",
    "resetTerminalScript": ROOT / "tools/build_reset_terminal_boundary_audit.py",
    "goalGapScript": ROOT / "tools/audit_pure_protocol_goal_gap.py",
    "gateChainScript": ROOT / "tools/run_pure_protocol_evidence_gate_chain.py",
    "evidenceManifestScript": ROOT / "tools/build_pure_protocol_evidence_manifest.py",
    "evidenceManifestVerifyScript": ROOT / "tools/verify_pure_protocol_evidence_manifest.py",
    "candidateProposalsLintScript": ROOT / "tools/lint_promoted_transition_candidate_proposals.py",
    "candidateProposalsLintControlsScript": ROOT / "tools/audit_promoted_transition_candidate_proposals_lint_controls.py",
    "phase3ProposalEvidenceTriageScript": ROOT / "tools/build_phase3_proposal_evidence_triage.py",
    "phase3EvidenceEntranceCoverageScript": ROOT / "tools/build_phase3_evidence_entrance_coverage_audit.py",
    "phase3RawEvidenceEntranceScript": ROOT / "tools/build_phase3_raw_evidence_entrance_audit.py",
    "phase3RawTraceCrosswalkScript": ROOT / "tools/build_phase3_raw_trace_crosswalk_audit.py",
    "candidateProposalsArtifact": HYP / "promoted_transition_candidate_proposals.json",
    "candidateProposalsLintArtifact": HYP / "promoted_transition_candidate_proposals_lint.json",
    "candidateProposalsLintControlsArtifact": HYP / "promoted_transition_candidate_proposals_lint_controls.json",
    "phase3ProposalEvidenceTriageArtifact": HYP / "phase3_proposal_evidence_triage.json",
    "phase3EvidenceEntranceCoverageArtifact": HYP / "phase3_evidence_entrance_coverage_audit.json",
    "phase3RawEvidenceEntranceArtifact": HYP / "phase3_raw_evidence_entrance_audit.json",
    "phase3RawTraceCrosswalkArtifact": HYP / "phase3_raw_trace_crosswalk_audit.json",
    "traceClassifierRawCoverageGapArtifact": HYP / "trace_classifier_raw_coverage_gap_audit.json",
    "remainingBoundaryProposalGateArtifact": HYP / "remaining_boundary_proposal_gate_audit.json",
    "candidateSourceContradictionLedgerArtifact": HYP / "candidate_source_contradiction_ledger.json",
    "serverStateValueConsumptionLedgerArtifact": HYP / "server_state_value_consumption_ledger.json",
    "coupledBoundaryTerminalLedgerArtifact": HYP / "coupled_boundary_terminal_ledger.json",
    "currentEvidenceEntranceTerminalLedgerArtifact": HYP / "current_evidence_entrance_terminal_ledger.json",
    "convergentEvidenceEntranceMatrixArtifact": HYP / "convergent_evidence_entrance_matrix.json",
    "manifestCoverageGapArtifact": HYP / "manifest_coverage_gap_audit.json",
    "liveRunnerGateArtifact": HYP / "live_runner_gate_audit.json",
    "objectiveRequirementCrosswalkArtifact": HYP / "objective_requirement_crosswalk.json",
    "promotionPredicateBlockerCrosswalkArtifact": HYP / "promotion_predicate_blocker_crosswalk.json",
    "candidateExecutorReadinessArtifact": HYP / "candidate_executor_readiness_audit.json",
    "hypothesisTreeCurrentAuthorityArtifact": HYP / "hypothesis_tree_current_authority_audit.json",
    "nearestMissPromotionCandidateArtifact": HYP / "nearest_miss_promotion_candidate_audit.json",
    "nearestMissBlockerResolutionArtifact": HYP / "nearest_miss_blocker_resolution_audit.json",
    "remainingNearestMissResolutionArtifact": HYP / "remaining_nearest_miss_resolution_audit.json",
    "exhaustivePromotionCandidateResolutionArtifact": HYP / "exhaustive_promotion_candidate_resolution_audit.json",
    "nextEvidenceSurfaceDiscoveryArtifact": HYP / "next_evidence_surface_discovery_audit.json",
    "externalOutputSurfaceAuditArtifact": HYP / "external_output_surface_audit.json",
    "evidencePackageSurfaceAuditArtifact": HYP / "evidence_package_surface_audit.json",
    "ctfRegOutputSurfaceAuditArtifact": HYP / "ctf_reg_output_surface_audit.json",
    "auxiliaryTraceSurfaceAuditArtifact": HYP / "auxiliary_trace_surface_audit.json",
    "stalePositiveSignalAuthorityArtifact": HYP / "stale_positive_signal_authority_audit.json",
    "localTraceEvidenceFreshnessArtifact": HYP / "local_trace_evidence_freshness_audit.json",
    "unclassifiedTraceSignalReductionArtifact": HYP / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessChainClassificationBacklogArtifact": HYP / "browser_success_chain_classification_backlog.json",
    "browserSuccessChainServerVisibleDiffArtifact": HYP / "browser_success_chain_server_visible_diff_audit.json",
    "browserSuccessPayloadPcSessionLineageArtifact": HYP / "browser_success_payload_pc_session_lineage_audit.json",
    "collectorResponseHandlerValueLineageArtifact": HYP / "collector_response_handler_value_lineage_audit.json",
    "downstreamSuccessWithoutCollectorDecodeArtifact": HYP / "downstream_success_without_collector_decode_audit.json",
    "collectorMaterialOnlyResponseClassArtifact": HYP / "collector_material_only_response_class_audit.json",
    "lowValueUnclassifiedTraceClosureArtifact": HYP / "low_value_unclassified_trace_closure_audit.json",
    "unclassifiedTraceClassClosureLedgerArtifact": HYP / "unclassified_trace_class_closure_ledger.json",
    "candidateIntakeArtifact": HYP / "promoted_transition_candidate_intake.json",
    "minimalTransitionArtifact": HYP / "minimal_promoted_transition_experiment.json",
    "evidenceGatedPocArtifact": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalReplayArtifact": GOAL / "final_pure_protocol_replay_audit.json",
    "completionRequirementsArtifact": HYP / "pure_protocol_completion_requirements_audit.json",
    "proofReproducibilityArtifact": HYP / "proof_script_reproducibility_audit.json",
    "resetTerminalArtifact": RESET / "reset_terminal_boundary_audit.json",
    "goalGapArtifact": GOAL / "pure_protocol_goal_gap_audit.json",
    "gateChainArtifact": GOAL / "pure_protocol_evidence_gate_chain_audit.json",
}


def sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_row(name: str, path: Path) -> dict[str, Any]:
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "id": name,
        "path": str(path),
        "exists": exists,
        "size": stat.st_size if stat else None,
        "mtimeNs": stat.st_mtime_ns if stat else None,
        "sha256": sha256(path),
    }


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def main() -> int:
    files = [file_row(name, path) for name, path in FILES.items()]
    reset = checks(read_json(RESET / "reset_terminal_boundary_audit.json"))
    completion = checks(read_json(HYP / "pure_protocol_completion_requirements_audit.json"))
    goal = summary(read_json(GOAL / "pure_protocol_goal_gap_audit.json"))
    chain = checks(read_json(GOAL / "pure_protocol_evidence_gate_chain_audit.json"))

    all_exist = all(row["exists"] for row in files)
    all_hashed = all(row["sha256"] for row in files)
    duplicate_hashes = sorted(
        {
            row["sha256"]
            for row in files
            if row["sha256"] and sum(1 for other in files if other["sha256"] == row["sha256"]) > 1
        }
    )

    checks_out = {
        "fileCount": len(files),
        "allFilesExist": all_exist,
        "allFilesHashed": all_hashed,
        "duplicateHashCount": len(duplicate_hashes),
        "gateChainAllStepsPassed": chain.get("allStepsPassed") is True,
        "gateChainStepCount": chain.get("stepCount"),
        "resetReadyForFreshExperiment": reset.get("readyForFreshExperiment") is True,
        "resetNoCurrentRouteToPhase5": reset.get("noCurrentRouteToPhase5") is True,
        "completionFreshSuccessMissing": completion.get("freshSuccessMissing") is True,
        "completionNoCurrentExperimentRoute": completion.get("noCurrentExperimentRoute") is True,
        "goalBlockingOnlyEndToEndPoc": goal.get("blockingOrMissing") == ["end_to_end_pure_protocol_poc"],
        "goalComplete": False,
        "readyForFreshExperiment": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Hash manifest for the current pure-protocol HUMAN evidence-gated implementation scripts and terminal artifacts.",
        "files": files,
        "duplicateHashes": duplicate_hashes,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "The evidence files are hashed for reproducibility; this manifest does not change the missing fresh end-to-end pure-protocol HUMAN success.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if all_exist and all_hashed else 1


if __name__ == "__main__":
    raise SystemExit(main())
