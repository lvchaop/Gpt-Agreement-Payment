#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
GOAL = PROTO / "goal_audit"
PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
OUT = GOAL / "pure_protocol_evidence_gate_chain_audit.json"


STEPS: list[dict[str, Any]] = [
    {
        "id": "candidate_intake",
        "argv": ["python3", "tools/build_promoted_transition_candidate_intake.py"],
        "artifact": HYP / "promoted_transition_candidate_intake.json",
        "expectChecks": {
            "promotedSingleTransitionCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "trace_classifier_raw_coverage_gap",
        "argv": ["python3", "tools/audit_trace_classifier_raw_coverage_gap.py"],
        "artifact": HYP / "trace_classifier_raw_coverage_gap_audit.json",
        "expectChecks": {
            "unreferencedRawTraceCount": 0,
            "safeToAutoAppendToClassifier": False,
            "proposalWorthyCoverageGapCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "remaining_boundary_proposal_gate",
        "argv": ["python3", "tools/build_remaining_boundary_proposal_gate_audit.py"],
        "artifact": HYP / "remaining_boundary_proposal_gate_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "proposalReadyRowCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "candidate_source_contradiction_ledger",
        "argv": ["python3", "tools/build_candidate_source_contradiction_ledger.py"],
        "artifact": HYP / "candidate_source_contradiction_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "intakeRowCount": 7,
            "intakeAcceptedCount": 0,
            "gateRowCount": 5,
            "gateReadyCount": 0,
            "matrixRowCount": 8,
            "matrixReadyCount": 0,
            "promotedCandidateTotal": 0,
            "allCandidateSourcesClosed": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "server_state_value_consumption_ledger",
        "argv": ["python3", "tools/build_server_state_value_consumption_ledger.py"],
        "artifact": HYP / "server_state_value_consumption_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "valueComparisonCount": 11,
            "valueMismatchCount": 11,
            "consumedValueCount": 11,
            "allRowsCoveredByControlOrCoupling": True,
            "singleValueProposalReadyCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "coupled_boundary_terminal_ledger",
        "argv": ["python3", "tools/build_coupled_boundary_terminal_ledger.py"],
        "artifact": HYP / "coupled_boundary_terminal_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "coupledBoundaryRowCount": 3,
            "proposalReadyRowCount": 0,
            "allCoupledBoundariesClosedForCurrentEvidence": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "current_evidence_entrance_terminal_ledger",
        "argv": ["python3", "tools/build_current_evidence_entrance_terminal_ledger.py"],
        "artifact": HYP / "current_evidence_entrance_terminal_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "nextPointerCount": 54,
            "unresolvedNextPointerCount": 0,
            "activeActionableNextPointerCount": 0,
            "currentPromotedSingleTransitionCandidateCount": 0,
            "allNextPointersClosedOrSuperseded": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "convergent_evidence_entrance_matrix",
        "argv": ["python3", "tools/build_convergent_evidence_entrance_matrix.py"],
        "artifact": HYP / "convergent_evidence_entrance_matrix.json",
        "expectChecks": {
            "allInputsExist": True,
            "entranceCount": 7,
            "closedEntranceCount": 7,
            "staleEntranceCount": 2,
            "candidateAffectingEntranceCount": 5,
            "uncoveredCandidateAffectingEntranceCount": 0,
            "recommendedNextEntranceCount": 0,
            "currentActiveActionableNextPointerCount": 0,
            "candidateIntakePromotedCount": 0,
            "staleActiveActionablePositiveSignalCount": 0,
            "completionVerified": False,
            "goalGapBlockingOnlyEndToEndPoc": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "manifest_coverage_gap",
        "argv": ["python3", "tools/build_manifest_coverage_gap_audit.py"],
        "artifact": HYP / "manifest_coverage_gap_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "highValueUncoveredDirectoryCount": 0,
            "proposalWorthyUnmanifestedDirectoryCount": 0,
            "recursiveReplayableFreshNoBrowserSuccessCount": 0,
            "nonJsonReplayableFreshNoBrowserSuccessCount": 0,
            "phase3RawProposalWorthySignalCount": 0,
            "phase3RawTraceCrosswalkProposalWorthyCount": 0,
            "currentEvidenceActiveActionableNextPointerCount": 0,
            "convergentRecommendedNextEntranceCount": 0,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "live_runner_gate",
        "argv": ["python3", "tools/build_live_runner_gate_audit.py"],
        "artifact": HYP / "live_runner_gate_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "authoritativeHarnessCount": 3,
            "authoritativeHarnessBlockedCount": 3,
            "proofInvokedUngatedLiveRunnerCount": 0,
            "gateChainInvokedUngatedLiveRunnerCount": 0,
            "candidateIntakePromotedCount": 0,
            "resetReadyForFreshExperiment": False,
            "convergentRecommendedNextEntranceCount": 0,
            "manifestCoverageProposalWorthyUnmanifestedDirectoryCount": 0,
            "minimalTransitionNetworkAttemptExecuted": False,
            "evidenceGatedPocNetworkAttemptExecuted": False,
            "finalReplayNetworkAttemptExecuted": False,
            "currentNetworkAttemptBlocked": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "objective_requirement_crosswalk",
        "argv": ["python3", "tools/build_objective_requirement_crosswalk.py"],
        "artifact": HYP / "objective_requirement_crosswalk.json",
        "expectChecks": {
            "allInputsExist": True,
            "requirementCount": 10,
            "provenCount": 7,
            "missingCount": 1,
            "notProvenCount": 1,
            "partiallyProvenCount": 1,
            "blockingRequirementCount": 3,
            "endToEndPocMissing": True,
            "fullNoBrowserIndependenceNotProven": True,
            "traceabilityOnlyPartiallyProven": True,
            "manifestVerifyAllHashesMatch": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "promotion_predicate_blocker_crosswalk",
        "argv": ["python3", "tools/build_promotion_predicate_blocker_crosswalk.py"],
        "artifact": HYP / "promotion_predicate_blocker_crosswalk.json",
        "expectChecks": {
            "allInputsExist": True,
            "predicateCount": 8,
            "unsatisfiedPromotionPredicateCount": 6,
            "artifactBackedNegativeDecision": True,
            "staleAuthorityCleanForNegativeDecision": True,
            "candidateIntakePromotedCount": 0,
            "remainingBoundaryProposalReadyRowCount": 0,
            "objectiveEndToEndPocMissing": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "candidate_executor_readiness",
        "argv": ["python3", "tools/build_candidate_executor_readiness_audit.py"],
        "artifact": HYP / "candidate_executor_readiness_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "planRequiresCandidateSpecificExecutor": True,
            "harnessDeclaresMissingCandidateSpecificExecutor": True,
            "candidateIntakePromotedCount": 0,
            "promotionPredicateUnsatisfiedCount": 6,
            "minimalExperimentNetworkAttemptExecuted": False,
            "evidenceGatedPocNetworkAttemptExecuted": False,
            "finalReplayNetworkAttemptExecuted": False,
            "liveRunnerCurrentNetworkAttemptBlocked": True,
            "currentGateClosedNoNetworkAttempt": True,
            "executorReadyForPromotedCandidate": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "hypothesis_tree_current_authority",
        "argv": ["python3", "tools/build_hypothesis_tree_current_authority_audit.py"],
        "artifact": HYP / "hypothesis_tree_current_authority_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "phaseChainPresent": True,
            "hypothesisMatrixPrimaryNextIsH3": True,
            "firstDivergenceAtFinalSeq5": True,
            "requestHistoryOrderGapFalsified": True,
            "nextStaticGapReadyForFreshExperiment": False,
            "h3CollectorServerStateTerminalForCurrentEvidence": True,
            "h4BrowserOnlyRuntimeTerminalForCurrentEvidence": True,
            "h5MicrosoftContextNotCurrentEntrance": True,
            "singleTransitionCandidateCount": 0,
            "jsReplayableClientTransitionCandidateCount": 0,
            "convergentRecommendedNextEntranceCount": 0,
            "promotionPredicateUnsatisfiedCount": 6,
            "candidateExecutorCurrentGateClosedNoNetworkAttempt": True,
            "oldPlanNoLongerAuthorizesPhase5": True,
            "convergentPlanIsCurrentAuthority": True,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "nearest_miss_promotion_candidate",
        "argv": ["python3", "tools/build_nearest_miss_promotion_candidate_audit.py"],
        "artifact": HYP / "nearest_miss_promotion_candidate_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "candidateRowCount": 32,
            "allRowCount": 32,
            "nearestSatisfiedPredicateCount": 6,
            "nearestMissingPredicateCount": 2,
            "proposalReadyCandidateCount": 0,
            "singleMissingPredicateCandidateCount": 0,
            "candidateWithConstructibilityProofCount": 9,
            "candidateWithNegativeControlEscapeCount": 8,
            "candidateWithSingleTransitionCount": 0,
            "promotionPredicateUnsatisfiedCount": 6,
            "executorReadyForPromotedCandidate": False,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "nearest_miss_blocker_resolution",
        "argv": ["python3", "tools/build_nearest_miss_blocker_resolution_audit.py"],
        "artifact": HYP / "nearest_miss_blocker_resolution_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "rowCount": 2,
            "closedByExistingControlsCount": 2,
            "needsMoreEvidenceCount": 0,
            "pcValueClosedByExistingControls": True,
            "collectorCookieHeaderClosedByExistingControls": True,
            "pcValueCanPromote": False,
            "collectorCookieHeaderCanPromote": False,
            "proposalReadyCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "remaining_nearest_miss_resolution",
        "argv": ["python3", "tools/build_remaining_nearest_miss_resolution_audit.py"],
        "artifact": HYP / "remaining_nearest_miss_resolution_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "remainingNearestRowCount": 8,
            "closedByExistingControlsCount": 8,
            "openRemainingNearestRowCount": 0,
            "proposalReadyCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "exhaustive_promotion_candidate_resolution",
        "argv": ["python3", "tools/build_exhaustive_promotion_candidate_resolution_audit.py"],
        "artifact": HYP / "exhaustive_promotion_candidate_resolution_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "candidateRowCount": 32,
            "nearestMissAllRowCount": 32,
            "resolvedCandidateCount": 32,
            "closedByExistingControlsCount": 32,
            "openNeedsSpecificEvidenceCount": 0,
            "proposalReadyCandidateCount": 0,
            "top10CandidateCount": 10,
            "top10ResolvedCandidateCount": 10,
            "nonTop10CandidateCount": 22,
            "nonTop10OpenCandidateCount": 0,
            "nonTop10ProposalReadyCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "next_evidence_surface_discovery",
        "argv": ["python3", "tools/build_next_evidence_surface_discovery_audit.py"],
        "artifact": HYP / "next_evidence_surface_discovery_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "surfaceCount": 16,
            "closedSurfaceCount": 16,
            "openSurfaceCount": 0,
            "newCandidateSurfaceCount": 0,
            "surfaceWithNewCandidateCount": 0,
            "proposalReadyCandidateCount": 0,
            "openNeedsSpecificEvidenceCount": 0,
            "manifestProposalWorthyUnmanifestedDirectoryCount": 0,
            "convergentRecommendedNextEntranceCount": 0,
            "externalProposalWorthySignalCount": 0,
            "evidencePackageProposalWorthySignalCount": 0,
            "ctfRegProposalWorthySignalCount": 0,
            "auxiliaryProposalWorthySignalCount": 0,
            "localTraceProposalWorthyNowCount": 0,
            "unclassifiedTraceProposalReadyRunCount": 0,
            "liveRunnerCurrentNetworkAttemptBlocked": True,
            "objectiveEndToEndPocMissing": True,
            "goalCompletionVerified": False,
            "resetNoCurrentRouteToPhase5": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "external_output_surface_audit",
        "argv": ["python3", "tools/build_external_output_surface_audit.py"],
        "artifact": HYP / "external_output_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 5,
            "collectorSuccess0SignalFileCount": 0,
            "proposalWorthyExternalSignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "evidence_package_surface_audit",
        "argv": ["python3", "tools/build_evidence_package_surface_audit.py"],
        "artifact": HYP / "evidence_package_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 2,
            "existingScanDirectoryCount": 2,
            "signalFileCount": 84,
            "collectorSuccess0SignalFileCount": 5,
            "proposalWorthyEvidencePackageSignalCount": 0,
            "externalOutputProposalWorthySignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "ctf_reg_output_surface_audit",
        "argv": ["python3", "tools/build_ctf_reg_output_surface_audit.py"],
        "artifact": HYP / "ctf_reg_output_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 1,
            "existingScanDirectoryCount": 1,
            "signalFileCount": 63,
            "collectorSuccess0SignalFileCount": 0,
            "proposalWorthyCtfRegSignalCount": 0,
            "evidencePackageProposalWorthySignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "auxiliary_trace_surface_audit",
        "argv": ["python3", "tools/build_auxiliary_trace_surface_audit.py"],
        "artifact": HYP / "auxiliary_trace_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 2,
            "existingScanDirectoryCount": 2,
            "signalFileCount": 25,
            "collectorSuccess0SignalFileCount": 0,
            "proposalWorthyAuxiliarySignalCount": 0,
            "ctfRegProposalWorthySignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "stale_positive_signal_authority",
        "argv": ["python3", "tools/build_stale_positive_signal_authority_audit.py"],
        "artifact": HYP / "stale_positive_signal_authority_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "positiveSignalCount": 5,
            "activeActionablePositiveSignalCount": 0,
            "candidateIntakePromotedCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "local_trace_evidence_freshness",
        "argv": ["python3", "tools/build_local_trace_evidence_freshness_audit.py"],
        "artifact": HYP / "local_trace_evidence_freshness_audit.json",
        "expectChecks": {
            "unclassifiedHighValueSignalRunCount": 79,
            "proposalWorthyNowCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "unclassified_trace_signal_reduction",
        "argv": ["python3", "tools/build_unclassified_trace_signal_reduction_audit.py"],
        "artifact": HYP / "unclassified_trace_signal_reduction_audit.json",
        "expectChecks": {
            "browserSuccessChainRunCount": 18,
            "proposalReadyRunCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "browser_success_chain_classification_backlog",
        "argv": ["python3", "tools/build_browser_success_chain_classification_backlog.py"],
        "artifact": HYP / "browser_success_chain_classification_backlog.json",
        "expectChecks": {
            "classificationBacklogCount": 24,
            "safeToPromoteToClassifier": False,
            "noBrowserEvidenceCount": 0,
            "proposalReadyRunCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "browser_success_chain_server_visible_diff",
        "argv": ["python3", "tools/build_browser_success_chain_server_visible_diff_audit.py"],
        "artifact": HYP / "browser_success_chain_server_visible_diff_audit.json",
        "expectChecks": {
            "positiveRunCount": 18,
            "negativeControlRunCount": 16,
            "earliestServerVisibleDiffCount": 10,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "browser_success_payload_pc_session_lineage",
        "argv": ["python3", "tools/build_browser_success_payload_pc_session_lineage_audit.py"],
        "artifact": HYP / "browser_success_payload_pc_session_lineage_audit.json",
        "expectChecks": {
            "fieldLineageRowCount": 3,
            "fieldLineageContradictedCount": 3,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "collector_response_handler_value_lineage",
        "argv": ["python3", "tools/build_collector_response_handler_value_lineage_audit.py"],
        "artifact": HYP / "collector_response_handler_value_lineage_audit.json",
        "expectChecks": {
            "decodedSuccessRunCount": 4,
            "decodedFailureRunCount": 3,
            "handlerSurfacePromotedCount": 0,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "downstream_success_without_collector_decode",
        "argv": ["python3", "tools/build_downstream_success_without_collector_decode_audit.py"],
        "artifact": HYP / "downstream_success_without_collector_decode_audit.json",
        "expectChecks": {
            "downstreamClassRunCount": 55,
            "downstreamSuccessRunCount": 2,
            "collectorSuccessDecodeRunCount": 0,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "collector_material_only_response_class",
        "argv": ["python3", "tools/build_collector_material_only_response_class_audit.py"],
        "artifact": HYP / "collector_material_only_response_class_audit.json",
        "expectChecks": {
            "collectorMaterialOnlyRunCount": 76,
            "collectorSuccessDecodeRunCount": 0,
            "riskContinueRunCount": 1,
            "createRedirectRunCount": 0,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "low_value_unclassified_trace_closure",
        "argv": ["python3", "tools/build_low_value_unclassified_trace_closure_audit.py"],
        "artifact": HYP / "low_value_unclassified_trace_closure_audit.json",
        "expectChecks": {
            "lowValueRunCount": 7,
            "rescannedProposalRelevantSignalRunCount": 0,
            "allRowsRemainLowValue": True,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "unclassified_trace_class_closure_ledger",
        "argv": ["python3", "tools/build_unclassified_trace_class_closure_ledger.py"],
        "artifact": HYP / "unclassified_trace_class_closure_ledger.json",
        "expectChecks": {
            "reducedRunCount": 162,
            "ledgerRunCount": 162,
            "allTraceClassesClosed": True,
            "proposalCandidateTotal": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_proposal_evidence_triage",
        "argv": ["python3", "tools/build_phase3_proposal_evidence_triage.py"],
        "artifact": HYP / "phase3_proposal_evidence_triage.json",
        "expectChecks": {
            "proposalWorthyEvidenceCount": 0,
            "recursiveJsonReadyOrPromotedSignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_evidence_entrance_coverage",
        "argv": ["python3", "tools/build_phase3_evidence_entrance_coverage_audit.py"],
        "artifact": HYP / "phase3_evidence_entrance_coverage_audit.json",
        "expectChecks": {
            "uncoveredEntranceRowCount": 0,
            "proposalEntranceExhaustedForCurrentEvidence": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_raw_evidence_entrance",
        "argv": ["python3", "tools/build_phase3_raw_evidence_entrance_audit.py"],
        "artifact": HYP / "phase3_raw_evidence_entrance_audit.json",
        "expectChecks": {
            "proposalWorthyRawSignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_raw_trace_crosswalk",
        "argv": ["python3", "tools/build_phase3_raw_trace_crosswalk_audit.py"],
        "artifact": HYP / "phase3_raw_trace_crosswalk_audit.json",
        "expectChecks": {
            "unreferencedTraceCount": 0,
            "proposalWorthyRawTraceCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "minimal_transition_experiment",
        "argv": ["python3", "tools/run_minimal_promoted_transition_experiment.py"],
        "artifact": HYP / "minimal_promoted_transition_experiment.json",
        "expectChecks": {
            "networkAttemptExecuted": False,
            "blockedByGate": True,
            "stageAdvanced": False,
            "goalComplete": False,
        },
    },
    {
        "id": "evidence_gated_end_to_end_poc",
        "argv": ["python3", "tools/run_evidence_gated_end_to_end_pure_protocol_poc.py"],
        "artifact": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
        "expectChecks": {
            "networkAttemptExecuted": False,
            "blockedByGate": True,
            "freshNoBrowserCollectorSuccess": False,
            "goalComplete": False,
        },
    },
    {
        "id": "final_replay_audit",
        "argv": ["python3", "tools/build_final_pure_protocol_replay_audit.py"],
        "artifact": GOAL / "final_pure_protocol_replay_audit.json",
        "expectChecks": {
            "replayAttemptExecuted": False,
            "networkAttemptExecuted": False,
            "blockedByGate": True,
            "goalComplete": False,
        },
    },
    {
        "id": "completion_requirements",
        "argv": ["python3", "tools/build_pure_protocol_completion_requirements_audit.py"],
        "artifact": HYP / "pure_protocol_completion_requirements_audit.json",
        "expectChecks": {
            "freshSuccessMissing": True,
            "noCurrentExperimentRoute": True,
            "goalComplete": False,
            "readyForFreshExperiment": False,
        },
    },
    {
        "id": "proof_reproducibility",
        "argv": ["python3", "tools/build_proof_script_reproducibility_audit.py"],
        "artifact": HYP / "proof_script_reproducibility_audit.json",
        "expectChecks": {
            "allProofScriptsReproducible": True,
            "failedTaskCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "reset_terminal_boundary",
        "argv": ["python3", "tools/build_reset_terminal_boundary_audit.py"],
        "artifact": RESET / "reset_terminal_boundary_audit.json",
        "expectChecks": {
            "resetLocalProxySearchesNegative": True,
            "noCurrentRouteToPhase5": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "goal_gap_audit",
        "argv": ["python3", "tools/audit_pure_protocol_goal_gap.py"],
        "artifact": GOAL / "pure_protocol_goal_gap_audit.json",
        "expectSummary": {
            "blockingOrMissing": ["end_to_end_pure_protocol_poc"],
            "goalComplete": False,
        },
    },
    {
        "id": "completion_requirements_final_sync",
        "argv": ["python3", "tools/build_pure_protocol_completion_requirements_audit.py"],
        "artifact": HYP / "pure_protocol_completion_requirements_audit.json",
        "expectChecks": {
            "proofTaskCount": 60,
            "freshSuccessMissing": True,
            "noCurrentExperimentRoute": True,
            "goalComplete": False,
            "readyForFreshExperiment": False,
        },
    },
    {
        "id": "reset_terminal_boundary_final_sync",
        "argv": ["python3", "tools/build_reset_terminal_boundary_audit.py"],
        "artifact": RESET / "reset_terminal_boundary_audit.json",
        "expectChecks": {
            "proofScriptTaskCount": 60,
            "resetLocalProxySearchesNegative": True,
            "noCurrentRouteToPhase5": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "goal_completion_verifier",
        "argv": ["python3", "tools/verify_pure_protocol_goal_completion.py"],
        "artifact": GOAL / "pure_protocol_goal_completion_verifier.json",
        "expectChecks": {
            "allInputsExist": True,
            "inputCount": 17,
            "promotionPredicateUnsatisfiedCount": 6,
            "promotionPredicateCandidateIntakePromotedCount": 0,
            "promotionPredicateRemainingBoundaryProposalReadyRowCount": 0,
            "promotionPredicateReadyForFreshExperiment": False,
            "failedGateCount": 48,
            "completionVerified": False,
            "goalComplete": False,
            "readyForFreshExperiment": False,
        },
    },
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def evaluate(step: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    c = checks(doc)
    s = summary(doc)
    for key, expected in (step.get("expectChecks") or {}).items():
        if c.get(key) != expected:
            failures.append(f"checks.{key}: expected {expected!r}, got {c.get(key)!r}")
    for key, expected in (step.get("expectSummary") or {}).items():
        if s.get(key) != expected:
            failures.append(f"summary.{key}: expected {expected!r}, got {s.get(key)!r}")
    return failures


def run_step(step: dict[str, Any]) -> dict[str, Any]:
    artifact: Path = step["artifact"]
    before_mtime = artifact.stat().st_mtime_ns if artifact.exists() else None
    proc = subprocess.run(
        step["argv"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    after_exists = artifact.exists()
    after_mtime = artifact.stat().st_mtime_ns if after_exists else None
    row: dict[str, Any] = {
        "id": step["id"],
        "argv": step["argv"],
        "artifact": str(artifact),
        "returncode": proc.returncode,
        "stdoutTail": proc.stdout[-2000:],
        "stderrTail": proc.stderr[-2000:],
        "artifactExists": after_exists,
        "artifactMtimeChanged": before_mtime != after_mtime,
        "failures": [],
    }
    if proc.returncode != 0:
        row["failures"].append(f"returncode={proc.returncode}")
        row["passed"] = False
        return row
    if not after_exists:
        row["failures"].append("artifact missing after step")
        row["passed"] = False
        return row
    doc = read_json(artifact)
    row["checks"] = checks(doc)
    row["summary"] = summary(doc)
    row["failures"].extend(evaluate(step, doc))
    row["passed"] = not row["failures"]
    return row


def main() -> int:
    rows = []
    for step in STEPS:
        try:
            rows.append(run_step(step))
        except subprocess.TimeoutExpired as exc:
            rows.append(
                {
                    "id": step["id"],
                    "argv": step["argv"],
                    "artifact": str(step["artifact"]),
                    "returncode": None,
                    "stdoutTail": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
                    "stderrTail": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
                    "artifactExists": step["artifact"].exists(),
                    "artifactMtimeChanged": None,
                    "failures": ["timeout"],
                    "passed": False,
                }
            )

    final_reset = read_json(RESET / "reset_terminal_boundary_audit.json")
    final_completion = read_json(HYP / "pure_protocol_completion_requirements_audit.json")
    final_goal = read_json(GOAL / "pure_protocol_goal_gap_audit.json")
    reset_checks = checks(final_reset)
    completion_checks = checks(final_completion)
    goal_summary = summary(final_goal)

    checks_out = {
        "planExists": PLAN.exists(),
        "stepCount": len(rows),
        "passedStepCount": sum(1 for row in rows if row.get("passed") is True),
        "failedStepCount": sum(1 for row in rows if row.get("passed") is not True),
        "allStepsPassed": all(row.get("passed") is True for row in rows),
        "offlineOnly": True,
        "finalProofTaskCount": reset_checks.get("proofScriptTaskCount"),
        "finalProofPassedTaskCount": reset_checks.get("proofScriptPassedTaskCount"),
        "finalNoCurrentRouteToPhase5": reset_checks.get("noCurrentRouteToPhase5") is True,
        "finalReadyForFreshExperiment": reset_checks.get("readyForFreshExperiment") is True,
        "finalCompletionFreshSuccessMissing": completion_checks.get("freshSuccessMissing") is True,
        "finalCompletionNoCurrentExperimentRoute": completion_checks.get("noCurrentExperimentRoute") is True,
        "finalGoalBlockingOnlyEndToEndPoc": goal_summary.get("blockingOrMissing") == ["end_to_end_pure_protocol_poc"],
        "goalComplete": False,
        "readyForFreshExperiment": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "One-command offline rebuild of the current pure-protocol HUMAN evidence gate chain.",
        "steps": rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "The offline gate chain is reproducible, but current evidence still has zero promoted transition candidates and no end-to-end fresh pure-protocol HUMAN success."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks_out["allStepsPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
