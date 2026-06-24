#!/usr/bin/env python3
from __future__ import annotations

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
OUT = GOAL / "pure_protocol_goal_completion_verifier.json"

INPUTS = {
    "authoritativePlan": PLAN,
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "evidenceGatedPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalReplayAudit": GOAL / "final_pure_protocol_replay_audit.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalGapAudit": GOAL / "pure_protocol_goal_gap_audit.json",
    "objectiveRequirementCrosswalk": HYP / "objective_requirement_crosswalk.json",
    "promotionPredicateBlockerCrosswalk": HYP / "promotion_predicate_blocker_crosswalk.json",
    "candidateExecutorReadiness": HYP / "candidate_executor_readiness_audit.json",
    "hypothesisTreeCurrentAuthority": HYP / "hypothesis_tree_current_authority_audit.json",
    "nearestMissPromotionCandidate": HYP / "nearest_miss_promotion_candidate_audit.json",
    "nearestMissBlockerResolution": HYP / "nearest_miss_blocker_resolution_audit.json",
    "remainingNearestMissResolution": HYP / "remaining_nearest_miss_resolution_audit.json",
    "exhaustivePromotionCandidateResolution": HYP / "exhaustive_promotion_candidate_resolution_audit.json",
    "nextEvidenceSurfaceDiscovery": HYP / "next_evidence_surface_discovery_audit.json",
    "evidenceGateChain": GOAL / "pure_protocol_evidence_gate_chain_audit.json",
    "evidenceManifestVerify": GOAL / "pure_protocol_evidence_manifest_verify.json",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def main() -> int:
    docs = {name: load_json(path) for name, path in INPUTS.items() if path.suffix == ".json"}
    completion = checks(docs.get("completionRequirements", {}))
    poc = checks(docs.get("evidenceGatedPoc", {}))
    final_replay = checks(docs.get("finalReplayAudit", {}))
    reset = checks(docs.get("resetTerminal", {}))
    goal = summary(docs.get("goalGapAudit", {}))
    objective = checks(docs.get("objectiveRequirementCrosswalk", {}))
    promotion_blocker = checks(docs.get("promotionPredicateBlockerCrosswalk", {}))
    candidate_executor = checks(docs.get("candidateExecutorReadiness", {}))
    hypothesis_tree = checks(docs.get("hypothesisTreeCurrentAuthority", {}))
    nearest_miss = checks(docs.get("nearestMissPromotionCandidate", {}))
    nearest_miss_blocker = checks(docs.get("nearestMissBlockerResolution", {}))
    remaining_nearest = checks(docs.get("remainingNearestMissResolution", {}))
    exhaustive_candidate = checks(docs.get("exhaustivePromotionCandidateResolution", {}))
    next_surface = checks(docs.get("nextEvidenceSurfaceDiscovery", {}))
    chain = checks(docs.get("evidenceGateChain", {}))
    manifest_verify = checks(docs.get("evidenceManifestVerify", {}))

    required_replay_fields = [
        "freshSessionIdRecorded",
        "transportEvidenceRecorded",
        "webshareOrDirectControlRecorded",
        "collectorRequestResponseRecorded",
        "decodedCollectorResponseRecorded",
        "pxJarMutationRecorded",
        "riskVerifyResponseRecorded",
        "createAccountResponseRecorded",
        "replayCommandsRecorded",
        "artifactHashesRecorded",
    ]

    goal_gap_blocking = goal.get("blockingOrMissing") or []
    all_inputs_exist = all(path.exists() for path in INPUTS.values())
    final_replay_all_required_recorded = all(final_replay.get(key) is True for key in required_replay_fields)

    completion_gates = {
        "completionRequirementsGoalComplete": completion.get("goalComplete") is True,
        "completionBlockingRequirementCountZero": completion.get("blockingRequirementCount") == 0,
        "completionFreshSuccessMissingFalse": completion.get("freshSuccessMissing") is False,
        "completionNoCurrentExperimentRouteFalse": completion.get("noCurrentExperimentRoute") is False,
        "pocNetworkAttemptExecuted": poc.get("networkAttemptExecuted") is True,
        "pocBlockedByGateFalse": poc.get("blockedByGate") is False,
        "pocFreshNoBrowserCollectorSuccess": poc.get("freshNoBrowserCollectorSuccess") is True,
        "pocFreshDecodedOIIoIooo0": poc.get("freshDecodedOIIoIooo0") is True,
        "pocFreshDecodedPxJarReplayed": poc.get("freshDecodedPxJarReplayed") is True,
        "pocFreshRiskVerifyContinue": poc.get("freshRiskVerifyContinue") is True,
        "pocFreshCreateAccountRedirectUrl": poc.get("freshCreateAccountRedirectUrl") is True,
        "pocGoalComplete": poc.get("goalComplete") is True,
        "finalReplayAttemptExecuted": final_replay.get("replayAttemptExecuted") is True,
        "finalReplayNetworkAttemptExecuted": final_replay.get("networkAttemptExecuted") is True,
        "finalReplayBlockedByGateFalse": final_replay.get("blockedByGate") is False,
        "finalReplayAllRequiredEvidenceRecorded": final_replay_all_required_recorded,
        "finalReplayGoalComplete": final_replay.get("goalComplete") is True,
        "resetGoalComplete": reset.get("goalComplete") is True,
        "goalGapBlockingOrMissingEmpty": goal_gap_blocking == [],
        "goalGapGoalComplete": goal.get("goalComplete") is True,
        "objectiveCrosswalkNoBlockingRequirements": objective.get("blockingRequirementCount") == 0,
        "objectiveCrosswalkEndToEndPocMissingFalse": objective.get("endToEndPocMissing") is False,
        "objectiveCrosswalkFullNoBrowserIndependenceProven": objective.get("fullNoBrowserIndependenceNotProven") is False,
        "objectiveCrosswalkTraceabilityFullyProven": objective.get("traceabilityOnlyPartiallyProven") is False,
        "objectiveCrosswalkGoalComplete": objective.get("goalComplete") is True,
        "promotionPredicateAllSatisfied": promotion_blocker.get("unsatisfiedPromotionPredicateCount") == 0,
        "promotionPredicateCandidatePromoted": promotion_blocker.get("candidateIntakePromotedCount") == 1,
        "promotionPredicateProposalReady": promotion_blocker.get("remainingBoundaryProposalReadyRowCount") == 1,
        "promotionPredicateReadyForFreshExperiment": promotion_blocker.get("readyForFreshExperiment") is True,
        "promotionPredicateGoalComplete": promotion_blocker.get("goalComplete") is True,
        "candidateExecutorReadyForPromotedCandidate": candidate_executor.get("executorReadyForPromotedCandidate") is True,
        "candidateExecutorReadyForFreshExperiment": candidate_executor.get("readyForFreshExperiment") is True,
        "candidateExecutorGoalComplete": candidate_executor.get("goalComplete") is True,
        "hypothesisTreeReadyForFreshExperiment": hypothesis_tree.get("readyForFreshExperiment") is True,
        "hypothesisTreeGoalComplete": hypothesis_tree.get("goalComplete") is True,
        "hypothesisTreeNotTerminalNegativeAuthority": hypothesis_tree.get("convergentPlanIsCurrentAuthority") is not True,
        "nearestMissHasProposalReadyCandidate": nearest_miss.get("proposalReadyCandidateCount") == 1,
        "nearestMissReadyForFreshExperiment": nearest_miss.get("readyForFreshExperiment") is True,
        "nearestMissBlockerHasProposalReadyCandidate": nearest_miss_blocker.get("proposalReadyCandidateCount") == 1,
        "nearestMissBlockerReadyForFreshExperiment": nearest_miss_blocker.get("readyForFreshExperiment") is True,
        "remainingNearestMissHasProposalReadyCandidate": remaining_nearest.get("proposalReadyCandidateCount") == 1,
        "remainingNearestMissReadyForFreshExperiment": remaining_nearest.get("readyForFreshExperiment") is True,
        "exhaustiveCandidateHasProposalReadyCandidate": exhaustive_candidate.get("proposalReadyCandidateCount") == 1,
        "exhaustiveCandidateReadyForFreshExperiment": exhaustive_candidate.get("readyForFreshExperiment") is True,
        "nextEvidenceSurfaceHasNewCandidate": next_surface.get("newCandidateSurfaceCount", 0) > 0,
        "nextEvidenceSurfaceReadyForFreshExperiment": next_surface.get("readyForFreshExperiment") is True,
        "gateChainGoalComplete": chain.get("goalComplete") is True,
        "manifestVerifyAllFilesExist": manifest_verify.get("allFilesExist") is True,
        "manifestVerifyAllHashesMatch": manifest_verify.get("allHashesMatch") is True,
        "manifestVerifyGoalComplete": manifest_verify.get("goalComplete") is True,
    }

    failed_gates = [key for key, value in completion_gates.items() if value is not True]
    completion_verified = all_inputs_exist and not failed_gates

    checks_out = {
        "authoritativePlanExists": PLAN.exists(),
        "allInputsExist": all_inputs_exist,
        "inputCount": len(INPUTS),
        "completionRequirementsGoalComplete": completion_gates["completionRequirementsGoalComplete"],
        "completionBlockingRequirementCount": completion.get("blockingRequirementCount"),
        "completionFreshSuccessMissing": completion.get("freshSuccessMissing"),
        "completionNoCurrentExperimentRoute": completion.get("noCurrentExperimentRoute"),
        "pocNetworkAttemptExecuted": completion_gates["pocNetworkAttemptExecuted"],
        "pocFreshNoBrowserCollectorSuccess": completion_gates["pocFreshNoBrowserCollectorSuccess"],
        "pocFreshDecodedOIIoIooo0": completion_gates["pocFreshDecodedOIIoIooo0"],
        "pocFreshDecodedPxJarReplayed": completion_gates["pocFreshDecodedPxJarReplayed"],
        "pocFreshRiskVerifyContinue": completion_gates["pocFreshRiskVerifyContinue"],
        "pocFreshCreateAccountRedirectUrl": completion_gates["pocFreshCreateAccountRedirectUrl"],
        "finalReplayAttemptExecuted": completion_gates["finalReplayAttemptExecuted"],
        "finalReplayGoalComplete": completion_gates["finalReplayGoalComplete"],
        "finalReplayRequiredEvidenceRecordedCount": sum(1 for key in required_replay_fields if final_replay.get(key) is True),
        "finalReplayRequiredEvidenceFieldCount": len(required_replay_fields),
        "goalGapBlockingOrMissingCount": len(goal_gap_blocking),
        "objectiveCrosswalkBlockingRequirementCount": objective.get("blockingRequirementCount"),
        "objectiveCrosswalkEndToEndPocMissing": objective.get("endToEndPocMissing"),
        "objectiveCrosswalkFullNoBrowserIndependenceNotProven": objective.get("fullNoBrowserIndependenceNotProven"),
        "objectiveCrosswalkTraceabilityOnlyPartiallyProven": objective.get("traceabilityOnlyPartiallyProven"),
        "promotionPredicateUnsatisfiedCount": promotion_blocker.get("unsatisfiedPromotionPredicateCount"),
        "promotionPredicateCandidateIntakePromotedCount": promotion_blocker.get("candidateIntakePromotedCount"),
        "promotionPredicateRemainingBoundaryProposalReadyRowCount": promotion_blocker.get("remainingBoundaryProposalReadyRowCount"),
        "promotionPredicateReadyForFreshExperiment": promotion_blocker.get("readyForFreshExperiment"),
        "candidateExecutorPlanRequiresCandidateSpecificExecutor": candidate_executor.get("planRequiresCandidateSpecificExecutor"),
        "candidateExecutorHarnessDeclaresMissingCandidateSpecificExecutor": candidate_executor.get("harnessDeclaresMissingCandidateSpecificExecutor"),
        "candidateExecutorCurrentGateClosedNoNetworkAttempt": candidate_executor.get("currentGateClosedNoNetworkAttempt"),
        "candidateExecutorReadyForPromotedCandidate": candidate_executor.get("executorReadyForPromotedCandidate"),
        "candidateExecutorReadyForFreshExperiment": candidate_executor.get("readyForFreshExperiment"),
        "hypothesisTreeH3Terminal": hypothesis_tree.get("h3CollectorServerStateTerminalForCurrentEvidence"),
        "hypothesisTreeH4Terminal": hypothesis_tree.get("h4BrowserOnlyRuntimeTerminalForCurrentEvidence"),
        "hypothesisTreeOldPlanNoLongerAuthorizesPhase5": hypothesis_tree.get("oldPlanNoLongerAuthorizesPhase5"),
        "hypothesisTreeConvergentPlanIsCurrentAuthority": hypothesis_tree.get("convergentPlanIsCurrentAuthority"),
        "hypothesisTreeReadyForFreshExperiment": hypothesis_tree.get("readyForFreshExperiment"),
        "nearestMissCandidateRowCount": nearest_miss.get("candidateRowCount"),
        "nearestMissNearestSatisfiedPredicateCount": nearest_miss.get("nearestSatisfiedPredicateCount"),
        "nearestMissNearestMissingPredicateCount": nearest_miss.get("nearestMissingPredicateCount"),
        "nearestMissProposalReadyCandidateCount": nearest_miss.get("proposalReadyCandidateCount"),
        "nearestMissSingleMissingPredicateCandidateCount": nearest_miss.get("singleMissingPredicateCandidateCount"),
        "nearestMissReadyForFreshExperiment": nearest_miss.get("readyForFreshExperiment"),
        "nearestMissBlockerClosedByExistingControlsCount": nearest_miss_blocker.get("closedByExistingControlsCount"),
        "nearestMissBlockerNeedsMoreEvidenceCount": nearest_miss_blocker.get("needsMoreEvidenceCount"),
        "nearestMissBlockerProposalReadyCandidateCount": nearest_miss_blocker.get("proposalReadyCandidateCount"),
        "nearestMissBlockerReadyForFreshExperiment": nearest_miss_blocker.get("readyForFreshExperiment"),
        "remainingNearestMissRowCount": remaining_nearest.get("remainingNearestRowCount"),
        "remainingNearestMissClosedByExistingControlsCount": remaining_nearest.get("closedByExistingControlsCount"),
        "remainingNearestMissOpenRowCount": remaining_nearest.get("openRemainingNearestRowCount"),
        "remainingNearestMissProposalReadyCandidateCount": remaining_nearest.get("proposalReadyCandidateCount"),
        "remainingNearestMissReadyForFreshExperiment": remaining_nearest.get("readyForFreshExperiment"),
        "exhaustiveCandidateRowCount": exhaustive_candidate.get("candidateRowCount"),
        "exhaustiveResolvedCandidateCount": exhaustive_candidate.get("resolvedCandidateCount"),
        "exhaustiveOpenNeedsSpecificEvidenceCount": exhaustive_candidate.get("openNeedsSpecificEvidenceCount"),
        "exhaustiveProposalReadyCandidateCount": exhaustive_candidate.get("proposalReadyCandidateCount"),
        "exhaustiveReadyForFreshExperiment": exhaustive_candidate.get("readyForFreshExperiment"),
        "nextEvidenceSurfaceCount": next_surface.get("surfaceCount"),
        "nextEvidenceClosedSurfaceCount": next_surface.get("closedSurfaceCount"),
        "nextEvidenceOpenSurfaceCount": next_surface.get("openSurfaceCount"),
        "nextEvidenceNewCandidateSurfaceCount": next_surface.get("newCandidateSurfaceCount"),
        "nextEvidenceReadyForFreshExperiment": next_surface.get("readyForFreshExperiment"),
        "gateChainAllStepsPassed": chain.get("allStepsPassed"),
        "manifestVerifyAllHashesMatch": completion_gates["manifestVerifyAllHashesMatch"],
        "failedGateCount": len(failed_gates),
        "completionVerified": completion_verified,
        "goalComplete": completion_verified,
        "readyForFreshExperiment": poc.get("readyForFreshExperiment") is True or reset.get("readyForFreshExperiment") is True,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Strict final verifier for the full fresh no-browser pure-protocol HUMAN success objective.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "requiredReplayFields": required_replay_fields,
        "completionGates": completion_gates,
        "failedGates": failed_gates,
        "checks": checks_out,
        "decision": {
            "goalComplete": completion_verified,
            "completionVerified": completion_verified,
            "readyForFreshExperiment": checks_out["readyForFreshExperiment"],
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All final fresh pure-protocol success gates are satisfied."
                if completion_verified
                else "Goal completion is not proven; at least one fresh end-to-end success/replay/completion gate is still false."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "failedGates": failed_gates}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
