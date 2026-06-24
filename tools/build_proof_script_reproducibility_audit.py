#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json"


def cmd(*parts: str) -> list[str]:
    return list(parts)


TASKS: list[dict[str, Any]] = [
    {
        "id": "trace_classifier_v2",
        "argv": cmd("python3", "tools/human_trace_classifier_v2.py"),
        "artifact": "output/protocol_reverse/trace_classification_v2/human_trace_classifier_v2_summary.json",
        "expectMin": {"runCount": 13, "observationControlCount": 2},
        "expectStageAtLeast": {
            "full_success_decoded": 3,
            "tf_payload_failure_stage": 3,
            "captcha_success_message_only": 3,
            "microsoft_continue_no_human_decode": 1,
            "browser_success_no_collector_decode": 1,
        },
    },
    {
        "id": "trace_classifier_raw_coverage_gap",
        "argv": cmd("python3", "tools/audit_trace_classifier_raw_coverage_gap.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/trace_classifier_raw_coverage_gap_audit.json",
        "expectChecks": {
            "authoritativePlanExists": True,
            "classifierScriptExists": True,
            "classifierSummaryExists": True,
            "rawAuditExists": True,
            "crosswalkExists": True,
            "classifierRunCount": 14,
            "unreferencedRawTraceCount": 0,
            "safeToAutoAppendToClassifier": False,
            "proposalWorthyCoverageGapCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "collector_decoder_coverage",
        "argv": cmd("python3", "tools/audit_collector_decoder_coverage.py"),
        "artifact": "output/protocol_reverse/collector_decode/collector_decoder_coverage_audit.json",
        "expectChecksTrue": ["allDecodeFilesExist", "allRowsMatchExpectedSuccessHandler"],
    },
    {
        "id": "collector_request_build_exact_coverage",
        "argv": cmd("python3", "tools/audit_collector_request_build_exact_coverage.py"),
        "artifact": "output/protocol_reverse/goal_audit/collector_request_build_exact_coverage_audit.json",
        "expectChecksTrue": [
            "hasBuildFiles",
            "allRunsExact",
            "allRunsPayloadExact",
            "allRunsPcExact",
            "s00BeaconExact",
            "s00BeaconUsesPayloadInverseMarker",
            "s00BeaconMarkerQiIsEarlierJo",
        ],
    },
    {
        "id": "pow_to_px561_osk",
        "argv": cmd("python3", "tools/audit_pow_to_px561_osk.py"),
        "artifact": "output/protocol_reverse/pow/pow_to_px561_osk_audit.json",
        "expectChecksTrue": [
            "acceptedRowsHaveValidOsk",
            "acceptedRowsMatchPowHit",
            "acceptedRowsMatchCollectorChallengeHash",
            "controlsHaveNoPowHit",
            "controlsHaveNoValidOsk",
            "controlsStillHaveCollectorChallenges",
        ],
    },
    {
        "id": "pow_solver_px561_tail_inputs",
        "argv": cmd("python3", "tools/audit_pow_solver_px561_tail_inputs.py"),
        "artifact": "output/protocol_reverse/pow/pow_solver_px561_tail_inputs_audit.json",
        "expectChecksTrue": [
            "staticOskPropagationClosed",
            "runtimeAcceptedOskMatchesPowHit",
            "acceptedSolverOutputsMatchObservedOsk",
            "acceptedBztObservedNonNull",
            "liveProbePowSolved",
        ],
    },
    {
        "id": "px_cookie_jar_updater_multi",
        "argv": cmd(
            "python3",
            "tools/audit_px_cookie_jar_updater.py",
            "--run",
            "ni109xdjp5zp_1780948211",
            "--run",
            "hcxwyrtiudbg_1780949301",
            "--run",
            "whsnxy8ag5ji_1781017142",
            "--out-prefix",
            "px_cookie_jar_updater_multi_audit",
        ),
        "artifact": "output/protocol_reverse/cookie_jar/px_cookie_jar_updater_multi_audit.json",
        "expectChecksTrue": [
            "allRunsHaveTimeline",
            "allRunsHaveRiskMaterial",
            "allRunsHaveDecodedPxEvents",
            "allRunsHaveCorrelatedPx3PxdePxvid",
            "allRunsHaveRiskVerifyRequests",
            "allRunsRiskProviderMetadataValuesMatchJar",
            "anyRunProvesContinueRiskVerifyMatchesJar",
        ],
    },
    {
        "id": "risk_verify_build_ni109",
        "argv": cmd(
            "python3",
            "tools/build_risk_verify_request.py",
            "output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json",
            "--collector-state",
            "output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.json",
        ),
        "artifact": "output/protocol_reverse/risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.json",
        "expectChecksTrue": [
            "initialObjectMatch",
            "initialJsonMatch",
            "solutionObjectMatch",
            "solutionJsonMatch",
            "createContinuationMatch",
            "createObjectMatch",
            "createJsonMatch",
        ],
    },
    {
        "id": "wasm_nq_replay_s00",
        "argv": cmd(
            "node",
            "tools/replay_captcha_wasm_nq.mjs",
            "s00ld1lglrw0_1781191381",
            "output/protocol_reverse/wasm/captcha_s00ld1lglrw0_1781191381.wasm",
            "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl",
            "output/protocol_reverse/wasm",
        ),
        "artifact": "output/protocol_reverse/wasm/captcha_wasm_nq_replay_s00ld1lglrw0_1781191381.json",
        "expectChecksTrue": [
            "hasAfterNqSamples",
            "wrapperNgExportExists",
            "wrapperNqExportExists",
            "hasRuntimePxUuidEvidence",
            "pxUuidNqOnlyMatchesAnyTrace",
            "pxUuidNgThenNqMatchesAnyTrace",
            "pxUuidReplayMatchesAnyTrace",
        ],
    },
    {
        "id": "wasm_ng_runtime_random_replay",
        "argv": None,
        "artifact": "output/protocol_reverse/wasm/wasm_ng_runtime_random_replay_audit_gwyi06rpe015_1781208840.json",
        "expectChecksTrue": [
            "hasNineRandomHex",
            "randomLensMatchOfflineNgShape",
            "offlineNgMatchesRuntimeAeax",
            "offlineNqMatchesRuntimeTbr9",
            "offlineNqExpectMatches",
            "usedPxUuidImportPath",
            "allReplayRandomSourcesProvided",
        ],
    },
    {
        "id": "recursive_evidence_blindspot",
        "argv": cmd("python3", "tools/build_recursive_evidence_blindspot_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/recursive_evidence_blindspot_audit.json",
        "expectChecks": {
            "unclassifiedRecursiveSuccessSignalCount": 0,
            "replayableFreshNoBrowserSuccessEvidenceCount": 0,
            "hasReplayableFreshNoBrowserSuccessEvidence": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "non_json_evidence_blindspot",
        "argv": cmd("python3", "tools/build_non_json_evidence_blindspot_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/non_json_evidence_blindspot_audit.json",
        "expectChecks": {
            "unclassifiedSuccessSignalCount": 0,
            "replayableFreshNoBrowserSuccessEvidenceCount": 0,
            "hasReplayableFreshNoBrowserSuccessEvidence": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "collector_server_expected_state_boundary",
        "argv": cmd("python3", "tools/build_collector_server_expected_state_boundary_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/collector_server_expected_state_boundary_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "clientVisibleProxyFoundCount": 0,
            "serverStateBoundaryNotClientVisible": True,
            "promotedSingleTransitionCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "promoted_transition_candidate_proposals_lint",
        "argv": cmd("python3", "tools/lint_promoted_transition_candidate_proposals.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals_lint.json",
        "expectChecks": {
            "proposalFileExists": True,
            "schemaHasRequiredFields": True,
            "proposalCount": 0,
            "invalidProposalCount": 0,
            "promotableShapeCount": 0,
            "allProposalsStructurallyValid": True,
            "emptyProposalSet": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "promoted_transition_candidate_proposals_lint_controls",
        "argv": cmd("python3", "tools/audit_promoted_transition_candidate_proposals_lint_controls.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals_lint_controls.json",
        "expectChecks": {
            "controlCount": 4,
            "passedControlCount": 4,
            "failedControlCount": 0,
            "positiveShapeControlPassed": True,
            "missingEvidenceControlPassed": True,
            "badValueChainControlPassed": True,
            "contradictedControlPassed": True,
            "allControlsPassed": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "promoted_transition_candidate_intake",
        "argv": cmd("python3", "tools/build_promoted_transition_candidate_intake.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_intake.json",
        "expectChecks": {
            "allInputsExist": True,
            "candidateSourceCount": 7,
            "candidateCount": 0,
            "pureProtocolConstructibleCandidateCount": 0,
            "promotedSingleTransitionCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "remaining_boundary_proposal_gate",
        "argv": cmd("python3", "tools/build_remaining_boundary_proposal_gate_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/remaining_boundary_proposal_gate_audit.json",
        "expectChecks": {
            "currentPlanExists": True,
            "allInputsExist": True,
            "proposalFileProposalCount": 0,
            "candidateIntakePromotedCount": 0,
            "singleTransitionMatrixReadyCount": 0,
            "singleTransitionMatrixNoReadyCandidate": True,
            "proposalGateRowCount": 5,
            "proposalReadyRowCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "candidate_source_contradiction_ledger",
        "argv": cmd("python3", "tools/build_candidate_source_contradiction_ledger.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/candidate_source_contradiction_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "intakeRowCount": 7,
            "intakeAcceptedCount": 0,
            "gateRowCount": 5,
            "gateReadyCount": 0,
            "matrixRowCount": 8,
            "matrixReadyCount": 0,
            "matrixNoReadySingleTransitionCandidate": True,
            "collectorClientVisibleProxyFoundCount": 0,
            "collectorServerStateBoundaryNotClientVisible": True,
            "minimalExperimentBlockedByGate": True,
            "minimalExperimentNetworkAttemptExecuted": False,
            "promotedCandidateTotal": 0,
            "allCandidateSourcesClosed": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "server_state_value_consumption_ledger",
        "argv": cmd("python3", "tools/build_server_state_value_consumption_ledger.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/server_state_value_consumption_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "valueComparisonCount": 11,
            "valueMismatchCount": 11,
            "consumedValueCount": 11,
            "allNegativeControlRefsExist": True,
            "allRowsCoveredByControlOrCoupling": True,
            "singleValueProposalReadyCount": 0,
            "serverStateModelFinalS00Success": True,
            "serverStateModelFinalFreshRejected": True,
            "line922DecodedFieldsEqual": True,
            "stateLineageHasServerAcceptanceBoundary": True,
            "encodedDecodedJsonEqual": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "coupled_boundary_terminal_ledger",
        "argv": cmd("python3", "tools/build_coupled_boundary_terminal_ledger.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/coupled_boundary_terminal_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "finalMatrixNoBoundaryAllowsFreshExperiment": True,
            "coupledBoundaryRowCount": 3,
            "proposalReadyRowCount": 0,
            "outerTupleClosedNoSingle": True,
            "encodedSessionSingleAxisEliminated": True,
            "encoderVariantFamilyClosedNoSuccess": True,
            "serverStateValueSingleReadyCount": 0,
            "serverStateValueAllCovered": True,
            "collectorServerStateNotClientVisible": True,
            "candidateSourcePromotedTotal": 0,
            "allCoupledBoundariesClosedForCurrentEvidence": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "current_evidence_entrance_terminal_ledger",
        "argv": cmd("python3", "tools/build_current_evidence_entrance_terminal_ledger.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "nextPointerCount": 54,
            "unresolvedNextPointerCount": 0,
            "readySignalNextPointerCount": 1,
            "activeActionableNextPointerCount": 0,
            "currentPromotedSingleTransitionCandidateCount": 0,
            "hypothesisPlanStaleHistoricalNextPointerCount": 14,
            "hypothesisPlanAllHypothesesCovered": True,
            "allKnownLocalEvidenceEntrancesClosed": True,
            "allCoupledBoundariesClosedForCurrentEvidence": True,
            "goalCompletionVerified": False,
            "allNextPointersClosedOrSuperseded": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "convergent_evidence_entrance_matrix",
        "argv": cmd("python3", "tools/build_convergent_evidence_entrance_matrix.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/convergent_evidence_entrance_matrix.json",
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
        "argv": cmd("python3", "tools/build_manifest_coverage_gap_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/manifest_coverage_gap_audit.json",
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
        "argv": cmd("python3", "tools/build_live_runner_gate_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/live_runner_gate_audit.json",
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
        "argv": cmd("python3", "tools/build_objective_requirement_crosswalk.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/objective_requirement_crosswalk.json",
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
        "argv": cmd("python3", "tools/build_promotion_predicate_blocker_crosswalk.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/promotion_predicate_blocker_crosswalk.json",
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
        "argv": cmd("python3", "tools/build_candidate_executor_readiness_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/candidate_executor_readiness_audit.json",
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
        "argv": cmd("python3", "tools/build_hypothesis_tree_current_authority_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/hypothesis_tree_current_authority_audit.json",
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
        "argv": cmd("python3", "tools/build_nearest_miss_promotion_candidate_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/nearest_miss_promotion_candidate_audit.json",
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
        "argv": cmd("python3", "tools/build_nearest_miss_blocker_resolution_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/nearest_miss_blocker_resolution_audit.json",
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
        "argv": cmd("python3", "tools/build_remaining_nearest_miss_resolution_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/remaining_nearest_miss_resolution_audit.json",
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
        "argv": cmd("python3", "tools/build_exhaustive_promotion_candidate_resolution_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/exhaustive_promotion_candidate_resolution_audit.json",
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
        "argv": cmd("python3", "tools/build_next_evidence_surface_discovery_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/next_evidence_surface_discovery_audit.json",
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
        "argv": cmd("python3", "tools/build_external_output_surface_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/external_output_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 5,
            "existingScanDirectoryCount": 5,
            "signalFileCount": 11,
            "collectorSuccess0SignalFileCount": 0,
            "proposalWorthyExternalSignalCount": 0,
            "currentEvidenceEntrancesClosed": True,
            "nonJsonReplayableSuccessCount": 0,
            "rawProposalWorthySignalCount": 0,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "evidence_package_surface_audit",
        "argv": cmd("python3", "tools/build_evidence_package_surface_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/evidence_package_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 2,
            "existingScanDirectoryCount": 2,
            "textFileCount": 173,
            "imageFileCount": 4,
            "zipFileCount": 1,
            "signalFileCount": 84,
            "collectorSuccess0SignalFileCount": 5,
            "proposalWorthyEvidencePackageSignalCount": 0,
            "externalOutputProposalWorthySignalCount": 0,
            "currentEvidenceEntrancesClosed": True,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "ctf_reg_output_surface_audit",
        "argv": cmd("python3", "tools/build_ctf_reg_output_surface_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/ctf_reg_output_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 1,
            "existingScanDirectoryCount": 1,
            "textFileCount": 63,
            "imageFileCount": 29,
            "sqliteFileCount": 1,
            "skippedFileCount": 8,
            "signalFileCount": 63,
            "collectorSuccess0SignalFileCount": 0,
            "proposalWorthyCtfRegSignalCount": 0,
            "evidencePackageProposalWorthySignalCount": 0,
            "currentEvidenceEntrancesClosed": True,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "auxiliary_trace_surface_audit",
        "argv": cmd("python3", "tools/build_auxiliary_trace_surface_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/auxiliary_trace_surface_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "scanDirectoryCount": 2,
            "existingScanDirectoryCount": 2,
            "textFileCount": 26,
            "harFileCount": 7,
            "jsonlFileCount": 14,
            "htmlFileCount": 5,
            "skippedFileCount": 1,
            "signalFileCount": 25,
            "collectorSuccess0SignalFileCount": 0,
            "proposalWorthyAuxiliarySignalCount": 0,
            "ctfRegProposalWorthySignalCount": 0,
            "currentEvidenceEntrancesClosed": True,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "stale_positive_signal_authority",
        "argv": cmd("python3", "tools/build_stale_positive_signal_authority_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/stale_positive_signal_authority_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "positiveSignalCount": 5,
            "activeActionablePositiveSignalCount": 0,
            "supersededOrNonAuthoritativePositiveSignalCount": 5,
            "staleReadyArtifactCount": 2,
            "currentEvidenceActiveActionableNextPointerCount": 0,
            "candidateIntakePromotedCount": 0,
            "goalCompletionVerified": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "local_trace_evidence_freshness",
        "argv": cmd("python3", "tools/build_local_trace_evidence_freshness_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/local_trace_evidence_freshness_audit.json",
        "expectChecks": {
            "currentPlanExists": True,
            "allInputsExist": True,
            "inventoryRuntimeCountMatchesCurrent": False,
            "inventoryJsCountMatchesCurrent": False,
            "unclassifiedHighValueSignalRunCount": 79,
            "unclassifiedCollectorMaterialRunCount": 155,
            "proposalWorthyNowCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "unclassified_trace_signal_reduction",
        "argv": cmd("python3", "tools/build_unclassified_trace_signal_reduction_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/unclassified_trace_signal_reduction_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "freshnessAuditExists": True,
            "freshnessUnclassifiedRunCount": 162,
            "browserSuccessChainRunCount": 18,
            "proposalReadyRunCount": 0,
            "classificationEvidenceOnly": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "browser_success_chain_classification_backlog",
        "argv": cmd("python3", "tools/build_browser_success_chain_classification_backlog.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/browser_success_chain_classification_backlog.json",
        "expectChecks": {
            "allInputsExist": True,
            "browserSuccessChainRunCount": 18,
            "browserParentSuccessCookieChainRunCount": 6,
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
        "argv": cmd("python3", "tools/build_browser_success_chain_server_visible_diff_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/browser_success_chain_server_visible_diff_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "positiveRunCount": 18,
            "negativeControlRunCount": 16,
            "earliestServerVisibleDiffCount": 10,
            "singleFieldDiffCandidateCount": 4,
            "pureProtocolConstructibleDiffCount": 1,
            "contradictedDiffCount": 10,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "browser_success_payload_pc_session_lineage",
        "argv": cmd("python3", "tools/build_browser_success_payload_pc_session_lineage_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/browser_success_payload_pc_session_lineage_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "positiveRunCount": 18,
            "positiveBundleBuildRunCount": 1,
            "positivePx561BundleBuildRunCount": 1,
            "fieldLineageRowCount": 3,
            "fieldLineageContradictedCount": 3,
            "payloadExactControlRejected": True,
            "pcAloneEliminated": True,
            "outerTupleNoSingleReadyGroup": True,
            "encoderFamilyStillTwoAxis": True,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "collector_response_handler_value_lineage",
        "argv": cmd("python3", "tools/build_collector_response_handler_value_lineage_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/collector_response_handler_value_lineage_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "decodedRunCount": 14,
            "decodedSuccessRunCount": 4,
            "decodedFailureRunCount": 3,
            "successRowsWithSuccessHandlerCount": 4,
            "failureRowsWithPx3PxdeCount": 3,
            "handlerSurfacePromotedCount": 0,
            "finalResponsesAllMinusOne": True,
            "cookieMutationFailureStillMutates": True,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "downstream_success_without_collector_decode",
        "argv": cmd("python3", "tools/build_downstream_success_without_collector_decode_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/downstream_success_without_collector_decode_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "downstreamClassRunCount": 55,
            "downstreamSuccessRunCount": 2,
            "collectorSuccessDecodeRunCount": 0,
            "allDownstreamRowsLackCollectorSuccessDecode": True,
            "downstreamEvidenceIsPostAccept": True,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "collector_material_only_response_class",
        "argv": cmd("python3", "tools/build_collector_material_only_response_class_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/collector_material_only_response_class_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "collectorMaterialOnlyRunCount": 76,
            "collectorSuccessDecodeRunCount": 0,
            "riskContinueRunCount": 1,
            "createRedirectRunCount": 0,
            "allRowsLackCollectorSuccessDecode": True,
            "allRowsLackCreateRedirect": True,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "low_value_unclassified_trace_closure",
        "argv": cmd("python3", "tools/build_low_value_unclassified_trace_closure_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/low_value_unclassified_trace_closure_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "lowValueRunCount": 7,
            "rescannedProposalRelevantSignalRunCount": 0,
            "requestFailedRunCount": 3,
            "riskInitializeRunCount": 3,
            "allRowsRemainLowValue": True,
            "proposalCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "unclassified_trace_class_closure_ledger",
        "argv": cmd("python3", "tools/build_unclassified_trace_class_closure_ledger.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/unclassified_trace_class_closure_ledger.json",
        "expectChecks": {
            "allInputsExist": True,
            "reducedRunCount": 162,
            "ledgerClassCount": 5,
            "ledgerRunCount": 162,
            "perClassClosureCountsMatch": True,
            "unexpectedClassCount": 0,
            "missingExpectedClassCount": 0,
            "proposalCandidateTotal": 0,
            "allTraceClassesClosed": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_proposal_evidence_triage",
        "argv": cmd("python3", "tools/build_phase3_proposal_evidence_triage.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/phase3_proposal_evidence_triage.json",
        "expectChecks": {
            "authoritativePlanExists": True,
            "allNamedInputsExist": True,
            "proposalCount": 0,
            "proposalWorthyEvidenceCount": 0,
            "recursiveJsonReadyOrPromotedSignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_evidence_entrance_coverage",
        "argv": cmd("python3", "tools/build_phase3_evidence_entrance_coverage_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/phase3_evidence_entrance_coverage_audit.json",
        "expectChecks": {
            "authoritativePlanExists": True,
            "allInputsExist": True,
            "uncoveredEntranceRowCount": 0,
            "highValueUnclassifiedSuccessSignalCount": 0,
            "highValueReplayableFreshSuccessCount": 0,
            "phase3ProposalWorthyEvidenceCount": 0,
            "phase3RecursiveReadyOrPromotedSignalCount": 0,
            "proposalEntranceExhaustedForCurrentEvidence": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_raw_evidence_entrance",
        "argv": cmd("python3", "tools/build_phase3_raw_evidence_entrance_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/phase3_raw_evidence_entrance_audit.json",
        "expectChecks": {
            "authoritativePlanExists": True,
            "classifierExists": True,
            "protocolReverseExcluded": True,
            "otherRawSignalCount": 0,
            "proposalWorthyRawSignalCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "phase3_raw_trace_crosswalk",
        "argv": cmd("python3", "tools/build_phase3_raw_trace_crosswalk_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/phase3_raw_trace_crosswalk_audit.json",
        "expectChecks": {
            "rawAuditExists": True,
            "unindexedBrowserTraceSignalCount": 87,
            "crosswalkRowCount": 87,
            "referencedTraceCount": 87,
            "unreferencedTraceCount": 0,
            "proposalWorthyRawTraceCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "hypothesis_plan_coverage",
        "argv": cmd("python3", "tools/build_hypothesis_plan_coverage_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/hypothesis_plan_coverage_audit.json",
        "expectChecks": {
            "missingRequiredPhaseArtifactCount": 0,
            "minimalExperimentMissingAllowedByGate": True,
            "allHypothesesCovered": True,
            "h3RemainingNotClientVisible": True,
            "currentPromotedSingleTransitionCandidateCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "minimal_promoted_transition_experiment",
        "argv": cmd("python3", "tools/run_minimal_promoted_transition_experiment.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/minimal_promoted_transition_experiment.json",
        "expectChecks": {
            "gateEvaluated": True,
            "candidateIntakePromotedCount": 0,
            "candidateIntakeReadyForFreshExperiment": False,
            "networkAttemptExecuted": False,
            "blockedByGate": True,
            "singleTransitionExperimentExecuted": False,
            "stageAdvanced": False,
            "advancedToCollectorOIIoIooo0": False,
            "advancedToRiskVerifyContinue": False,
            "advancedToCreateAccountRedirectUrl": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "evidence_gated_end_to_end_poc",
        "argv": cmd("python3", "tools/run_evidence_gated_end_to_end_pure_protocol_poc.py"),
        "artifact": "output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json",
        "expectChecks": {
            "gateEvaluated": True,
            "candidateIntakePromotedCount": 0,
            "candidateIntakeReadyForFreshExperiment": False,
            "networkAttemptExecuted": False,
            "blockedByGate": True,
            "freshNoBrowserCollectorSuccess": False,
            "freshDecodedOIIoIooo0": False,
            "freshRiskVerifyContinue": False,
            "freshCreateAccountRedirectUrl": False,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "completion_requirements",
        "argv": cmd("python3", "tools/build_pure_protocol_completion_requirements_audit.py"),
        "artifact": "output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json",
        "expectChecks": {
            "freshSuccessMissing": True,
            "noCurrentExperimentRoute": True,
            "blockingRequirementCount": 4,
            "hypothesisPlanCoverageReady": True,
            "convergentEvidenceEntranceMatrixRecommendedNextEntranceCount": 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "final_pure_protocol_replay_audit",
        "argv": cmd("python3", "tools/build_final_pure_protocol_replay_audit.py"),
        "artifact": "output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json",
        "expectChecks": {
            "gateEvaluated": True,
            "blockedByGate": True,
            "readyForFreshReplay": False,
            "replayAttemptExecuted": False,
            "networkAttemptExecuted": False,
            "pocNetworkAttemptExecuted": False,
            "pocFreshNoBrowserCollectorSuccess": False,
            "pocFreshDecodedOIIoIooo0": False,
            "pocFreshRiskVerifyContinue": False,
            "pocFreshCreateAccountRedirectUrl": False,
            "minimalTransitionStageAdvanced": False,
            "candidateIntakePromotedCount": 0,
            "goalComplete": False,
        },
    },
    {
        "id": "reset_terminal_boundary",
        "argv": cmd("python3", "tools/build_reset_terminal_boundary_audit.py"),
        "artifact": "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json",
        "expectChecks": {
            "allInputsExist": True,
            "collectorServerExpectedStateBoundaryAuditExists": True,
            "collectorServerExpectedStatePromotedCount": 0,
            "hypothesisPlanCoverageAuditExists": True,
            "hypothesisPlanMissingRequiredPhaseArtifactCount": 0,
            "hypothesisPlanMinimalExperimentMissingAllowedByGate": True,
            "hypothesisPlanPromotedCount": 0,
            "completionRequirementsAuditExists": True,
            "completionFreshSuccessMissing": True,
            "completionNoCurrentExperimentRoute": True,
            "convergentEvidenceEntranceMatrixRecommendedNextEntranceCount": 0,
            "resetLocalProxySearchesNegative": True,
            "noCurrentRouteToPhase5": True,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    },
    {
        "id": "goal_gap_audit",
        "argv": cmd("python3", "tools/audit_pure_protocol_goal_gap.py"),
        "artifact": "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json",
        "expectSummary": {
            "goalComplete": False,
            "blockingOrMissing": ["end_to_end_pure_protocol_poc"],
        },
        "expect": {
            "currentDecision.readyForFreshExperiment": False,
            "currentDecision.nextArtifact": None,
            "currentDecision.nextScript": None,
        },
    },
    {
        "id": "goal_completion_verifier",
        "argv": cmd("python3", "tools/verify_pure_protocol_goal_completion.py"),
        "artifact": "output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json",
        "expectChecks": {
            "authoritativePlanExists": True,
            "allInputsExist": True,
            "inputCount": 17,
            "completionBlockingRequirementCount": 4,
            "completionFreshSuccessMissing": True,
            "completionNoCurrentExperimentRoute": True,
            "pocNetworkAttemptExecuted": False,
            "pocFreshNoBrowserCollectorSuccess": False,
            "finalReplayAttemptExecuted": False,
            "goalGapBlockingOrMissingCount": 1,
            "promotionPredicateUnsatisfiedCount": 6,
            "promotionPredicateCandidateIntakePromotedCount": 0,
            "promotionPredicateRemainingBoundaryProposalReadyRowCount": 0,
            "promotionPredicateReadyForFreshExperiment": False,
            "manifestVerifyAllHashesMatch": True,
            "failedGateCount": 48,
            "completionVerified": False,
            "goalComplete": False,
            "readyForFreshExperiment": False,
        },
    },
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_checks(doc: Any) -> dict[str, Any]:
    if isinstance(doc, dict):
        if isinstance(doc.get("checks"), dict):
            return doc["checks"]
        if isinstance(doc.get("summary"), dict):
            return doc["summary"]
    return {}


def value_at(doc: Any, key: str) -> Any:
    if "." in key:
        cur = doc
        for part in key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur
    if isinstance(doc, dict) and key in doc:
        return doc[key]
    checks = extract_checks(doc)
    if key in checks:
        return checks[key]
    return None


def evaluate(task: dict[str, Any], doc: Any) -> tuple[bool, list[str]]:
    failures: list[str] = []
    checks = extract_checks(doc)
    for key, expected in (task.get("expect") or {}).items():
        actual = value_at(doc, key)
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")
    for key, expected_min in (task.get("expectMin") or {}).items():
        actual = value_at(doc, key)
        if not isinstance(actual, (int, float)) or actual < expected_min:
            failures.append(f"{key}: expected >= {expected_min!r}, got {actual!r}")
    if task.get("expectStageAtLeast"):
        stage_counts: dict[str, int] = {}
        if isinstance(doc, dict):
            for run in doc.get("runs") or []:
                if isinstance(run, dict):
                    stage = run.get("stage")
                    if stage:
                        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        for stage, expected_min in task["expectStageAtLeast"].items():
            actual = stage_counts.get(stage, 0)
            if actual < expected_min:
                failures.append(f"stage[{stage}]: expected >= {expected_min}, got {actual}")
    for key in task.get("expectChecksTrue") or []:
        if checks.get(key) is not True:
            failures.append(f"checks.{key}: expected True, got {checks.get(key)!r}")
    for key, expected in (task.get("expectChecks") or {}).items():
        if checks.get(key) != expected:
            failures.append(f"checks.{key}: expected {expected!r}, got {checks.get(key)!r}")
    summary = doc.get("summary") if isinstance(doc, dict) else None
    if isinstance(summary, dict):
        for key, expected in (task.get("expectSummary") or {}).items():
            if summary.get(key) != expected:
                failures.append(f"summary.{key}: expected {expected!r}, got {summary.get(key)!r}")
    elif task.get("expectSummary"):
        failures.append("summary: missing")
    return not failures, failures


def run_task(task: dict[str, Any]) -> dict[str, Any]:
    artifact = ROOT / task["artifact"]
    before_mtime = artifact.stat().st_mtime_ns if artifact.exists() else None
    if task.get("argv") is None:
        proc = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    else:
        proc = subprocess.run(
            task["argv"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=180,
        )
    after_exists = artifact.exists()
    after_mtime = artifact.stat().st_mtime_ns if after_exists else None
    row: dict[str, Any] = {
        "id": task["id"],
        "argv": task["argv"],
        "artifact": str(artifact),
        "returncode": proc.returncode,
        "stdoutTail": proc.stdout[-3000:],
        "stderrTail": proc.stderr[-3000:],
        "artifactExists": after_exists,
        "artifactMtimeChanged": before_mtime != after_mtime,
        "failures": [],
    }
    if proc.returncode != 0:
        row["failures"].append(f"returncode={proc.returncode}")
        row["passed"] = False
        return row
    if not after_exists:
        row["failures"].append("artifact missing after run")
        row["passed"] = False
        return row
    try:
        doc = read_json(artifact)
    except Exception as exc:
        row["failures"].append(f"artifact json read failed: {exc}")
        row["passed"] = False
        return row
    passed, failures = evaluate(task, doc)
    row["failures"].extend(failures)
    row["passed"] = passed
    row["checks"] = extract_checks(doc)
    return row


def main() -> int:
    rows = []
    for task in TASKS:
        try:
            rows.append(run_task(task))
        except subprocess.TimeoutExpired as exc:
            rows.append(
                {
                    "id": task["id"],
                    "argv": task["argv"],
                    "artifact": str(ROOT / task["artifact"]),
                    "returncode": None,
                    "stdoutTail": (exc.stdout or "")[-3000:] if isinstance(exc.stdout, str) else "",
                    "stderrTail": (exc.stderr or "")[-3000:] if isinstance(exc.stderr, str) else "",
                    "artifactExists": (ROOT / task["artifact"]).exists(),
                    "artifactMtimeChanged": None,
                    "passed": False,
                    "failures": ["timeout"],
                }
            )
    checks = {
        "taskCount": len(rows),
        "passedTaskCount": sum(1 for row in rows if row.get("passed") is True),
        "failedTaskCount": sum(1 for row in rows if row.get("passed") is not True),
        "allProofScriptsReproducible": all(row.get("passed") is True for row in rows),
        "offlineOnly": True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Re-run the key offline proof/audit scripts and verify their current artifacts still satisfy the checks used by the pure-protocol HUMAN goal audit.",
        "checks": checks,
        "rows": rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": (
                "This is an offline reproducibility audit. Passing scripts strengthen existing evidence, but do not create the missing end-to-end pure-protocol HUMAN success PoC."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if checks["allProofScriptsReproducible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
