#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "pure_protocol_completion_requirements_audit.json"


PATHS = {
    "goalAudit": PROTO / "goal_audit/pure_protocol_goal_gap_audit.json",
    "finalGap": BASE / "server_internal_unobserved_state_final_gap.json",
    "resetTerminal": PROTO / "reset_plan/reset_terminal_boundary_audit.json",
    "hypothesisPlanCoverage": BASE / "hypothesis_plan_coverage_audit.json",
    "collectorServerExpectedState": BASE / "collector_server_expected_state_boundary_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
    "phase3ProposalEvidenceTriage": BASE / "phase3_proposal_evidence_triage.json",
    "phase3EvidenceEntranceCoverage": BASE / "phase3_evidence_entrance_coverage_audit.json",
    "phase3RawEvidenceEntrance": BASE / "phase3_raw_evidence_entrance_audit.json",
    "phase3RawTraceCrosswalk": BASE / "phase3_raw_trace_crosswalk_audit.json",
    "traceClassifierRawCoverageGap": BASE / "trace_classifier_raw_coverage_gap_audit.json",
    "remainingBoundaryProposalGate": BASE / "remaining_boundary_proposal_gate_audit.json",
    "candidateSourceContradictionLedger": BASE / "candidate_source_contradiction_ledger.json",
    "serverStateValueConsumptionLedger": BASE / "server_state_value_consumption_ledger.json",
    "coupledBoundaryTerminalLedger": BASE / "coupled_boundary_terminal_ledger.json",
    "currentEvidenceEntranceTerminalLedger": BASE / "current_evidence_entrance_terminal_ledger.json",
    "convergentEvidenceEntranceMatrix": BASE / "convergent_evidence_entrance_matrix.json",
    "manifestCoverageGap": BASE / "manifest_coverage_gap_audit.json",
    "liveRunnerGate": BASE / "live_runner_gate_audit.json",
    "objectiveRequirementCrosswalk": BASE / "objective_requirement_crosswalk.json",
    "promotionPredicateBlockerCrosswalk": BASE / "promotion_predicate_blocker_crosswalk.json",
    "candidateExecutorReadiness": BASE / "candidate_executor_readiness_audit.json",
    "hypothesisTreeCurrentAuthority": BASE / "hypothesis_tree_current_authority_audit.json",
    "nearestMissPromotionCandidate": BASE / "nearest_miss_promotion_candidate_audit.json",
    "nearestMissBlockerResolution": BASE / "nearest_miss_blocker_resolution_audit.json",
    "remainingNearestMissResolution": BASE / "remaining_nearest_miss_resolution_audit.json",
    "exhaustivePromotionCandidateResolution": BASE / "exhaustive_promotion_candidate_resolution_audit.json",
    "nextEvidenceSurfaceDiscovery": BASE / "next_evidence_surface_discovery_audit.json",
    "externalOutputSurfaceAudit": BASE / "external_output_surface_audit.json",
    "evidencePackageSurfaceAudit": BASE / "evidence_package_surface_audit.json",
    "ctfRegOutputSurfaceAudit": BASE / "ctf_reg_output_surface_audit.json",
    "auxiliaryTraceSurfaceAudit": BASE / "auxiliary_trace_surface_audit.json",
    "stalePositiveSignalAuthority": BASE / "stale_positive_signal_authority_audit.json",
    "localTraceEvidenceFreshness": BASE / "local_trace_evidence_freshness_audit.json",
    "unclassifiedTraceSignalReduction": BASE / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessChainClassificationBacklog": BASE / "browser_success_chain_classification_backlog.json",
    "browserSuccessChainServerVisibleDiff": BASE / "browser_success_chain_server_visible_diff_audit.json",
    "browserSuccessPayloadPcSessionLineage": BASE / "browser_success_payload_pc_session_lineage_audit.json",
    "collectorResponseHandlerValueLineage": BASE / "collector_response_handler_value_lineage_audit.json",
    "downstreamSuccessWithoutCollectorDecode": BASE / "downstream_success_without_collector_decode_audit.json",
    "collectorMaterialOnlyResponseClass": BASE / "collector_material_only_response_class_audit.json",
    "lowValueUnclassifiedTraceClosure": BASE / "low_value_unclassified_trace_closure_audit.json",
    "unclassifiedTraceClassClosureLedger": BASE / "unclassified_trace_class_closure_ledger.json",
    "proofScriptReproducibility": BASE / "proof_script_reproducibility_audit.json",
    "evidenceGatedPoc": PROTO / "goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json",
    "minimalTransitionExperiment": BASE / "minimal_promoted_transition_experiment.json",
    "finalReplayAudit": PROTO / "goal_audit/final_pure_protocol_replay_audit.json",
    "evidenceGateChain": PROTO / "goal_audit/pure_protocol_evidence_gate_chain_audit.json",
    "evidenceManifest": PROTO / "goal_audit/pure_protocol_evidence_manifest.json",
    "evidenceManifestVerify": PROTO / "goal_audit/pure_protocol_evidence_manifest_verify.json",
    "goalCompletionVerifier": PROTO / "goal_audit/pure_protocol_goal_completion_verifier.json",
    "currentRouteAuthority": BASE / "current_route_authority_audit.json",
    "historicalProbe": BASE / "historical_probe_response_class_matrix.json",
    "crossSample": BASE / "cross_sample_server_state_proxy_matrix.json",
    "collectorToRisk": BASE / "collector_to_risk_consumption_chain.json",
    "cookieJar": PROTO / "cookie_jar/px_cookie_jar_updater_multi_audit.json",
    "riskVerifyMaterial": PROTO / "risk_verify/risk_verify_material_s00ld1lglrw0_1781191381.json",
    "s00RiskGap": BASE / "s00_risk_verify_material_gap.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def status(proven: bool, missing: bool = False) -> str:
    if proven:
        return "proven"
    if missing:
        return "missing"
    return "not_proven"


def build() -> dict[str, Any]:
    docs = {key: load_json(path) for key, path in PATHS.items()}
    goal_summary = (docs["goalAudit"].get("summary") or {})
    final_checks = docs["finalGap"].get("checks") or {}
    historical_checks = docs["historicalProbe"].get("checks") or {}
    reset_checks = docs["resetTerminal"].get("checks") or {}
    hypothesis_coverage_checks = docs["hypothesisPlanCoverage"].get("checks") or {}
    collector_server_checks = docs["collectorServerExpectedState"].get("checks") or {}
    candidate_intake_checks = docs["candidateIntake"].get("checks") or {}
    phase3_triage_checks = docs["phase3ProposalEvidenceTriage"].get("checks") or {}
    phase3_entrance_checks = docs["phase3EvidenceEntranceCoverage"].get("checks") or {}
    phase3_raw_checks = docs["phase3RawEvidenceEntrance"].get("checks") or {}
    phase3_crosswalk_checks = docs["phase3RawTraceCrosswalk"].get("checks") or {}
    trace_classifier_gap_checks = docs["traceClassifierRawCoverageGap"].get("checks") or {}
    remaining_boundary_gate_checks = docs["remainingBoundaryProposalGate"].get("checks") or {}
    candidate_source_ledger_checks = docs["candidateSourceContradictionLedger"].get("checks") or {}
    server_state_value_consumption_checks = docs["serverStateValueConsumptionLedger"].get("checks") or {}
    coupled_boundary_terminal_checks = docs["coupledBoundaryTerminalLedger"].get("checks") or {}
    current_evidence_entrance_terminal_checks = docs["currentEvidenceEntranceTerminalLedger"].get("checks") or {}
    convergent_evidence_entrance_matrix_checks = docs["convergentEvidenceEntranceMatrix"].get("checks") or {}
    manifest_coverage_gap_checks = docs["manifestCoverageGap"].get("checks") or {}
    live_runner_gate_checks = docs["liveRunnerGate"].get("checks") or {}
    objective_crosswalk_checks = docs["objectiveRequirementCrosswalk"].get("checks") or {}
    promotion_blocker_checks = docs["promotionPredicateBlockerCrosswalk"].get("checks") or {}
    candidate_executor_checks = docs["candidateExecutorReadiness"].get("checks") or {}
    hypothesis_tree_authority_checks = docs["hypothesisTreeCurrentAuthority"].get("checks") or {}
    nearest_miss_checks = docs["nearestMissPromotionCandidate"].get("checks") or {}
    nearest_miss_blocker_checks = docs["nearestMissBlockerResolution"].get("checks") or {}
    remaining_nearest_checks = docs["remainingNearestMissResolution"].get("checks") or {}
    exhaustive_candidate_checks = docs["exhaustivePromotionCandidateResolution"].get("checks") or {}
    next_surface_checks = docs["nextEvidenceSurfaceDiscovery"].get("checks") or {}
    external_output_surface_checks = docs["externalOutputSurfaceAudit"].get("checks") or {}
    evidence_package_surface_checks = docs["evidencePackageSurfaceAudit"].get("checks") or {}
    ctf_reg_output_surface_checks = docs["ctfRegOutputSurfaceAudit"].get("checks") or {}
    auxiliary_trace_surface_checks = docs["auxiliaryTraceSurfaceAudit"].get("checks") or {}
    stale_positive_signal_authority_checks = docs["stalePositiveSignalAuthority"].get("checks") or {}
    local_trace_freshness_checks = docs["localTraceEvidenceFreshness"].get("checks") or {}
    unclassified_trace_reduction_checks = docs["unclassifiedTraceSignalReduction"].get("checks") or {}
    browser_success_backlog_checks = docs["browserSuccessChainClassificationBacklog"].get("checks") or {}
    browser_success_diff_checks = docs["browserSuccessChainServerVisibleDiff"].get("checks") or {}
    payload_pc_session_lineage_checks = docs["browserSuccessPayloadPcSessionLineage"].get("checks") or {}
    collector_handler_value_lineage_checks = docs["collectorResponseHandlerValueLineage"].get("checks") or {}
    downstream_without_collector_checks = docs["downstreamSuccessWithoutCollectorDecode"].get("checks") or {}
    collector_material_only_checks = docs["collectorMaterialOnlyResponseClass"].get("checks") or {}
    low_value_closure_checks = docs["lowValueUnclassifiedTraceClosure"].get("checks") or {}
    trace_class_ledger_checks = docs["unclassifiedTraceClassClosureLedger"].get("checks") or {}
    proof_checks = docs["proofScriptReproducibility"].get("checks") or {}
    gated_poc_checks = docs["evidenceGatedPoc"].get("checks") or {}
    minimal_experiment_checks = docs["minimalTransitionExperiment"].get("checks") or {}
    final_replay_checks = docs["finalReplayAudit"].get("checks") or {}
    gate_chain_checks = docs["evidenceGateChain"].get("checks") or {}
    evidence_manifest_checks = docs["evidenceManifest"].get("checks") or {}
    evidence_manifest_verify_checks = docs["evidenceManifestVerify"].get("checks") or {}
    goal_completion_verifier_checks = docs["goalCompletionVerifier"].get("checks") or {}
    route_authority_checks = docs["currentRouteAuthority"].get("checks") or {}
    risk_checks = docs["collectorToRisk"].get("checks") or {}
    cookie_checks = docs["cookieJar"].get("checks") or {}
    s00_risk_checks = docs["s00RiskGap"].get("checks") or {}

    fresh_success_missing = (
        historical_checks.get("hasHistoricalNoBrowserSuccess0") is False
        and final_checks.get("highValueUnminedReplayableSuccessNotFound") is True
        and final_checks.get("allLocalProxySearchesNegative") is True
        and reset_checks.get("endToEndPureProtocolPocMissing") is True
    )
    no_current_experiment_route = (
        reset_checks.get("readyForFreshExperiment") is False
        and hypothesis_coverage_checks.get("minimalExperimentMissingAllowedByGate") is True
        and collector_server_checks.get("promotedSingleTransitionCandidateCount") == 0
        and candidate_intake_checks.get("promotedSingleTransitionCandidateCount") in {None, 0}
        and minimal_experiment_checks.get("networkAttemptExecuted") is not True
    )

    requirements = [
        {
            "id": "R1_fresh_pure_protocol_collector_human_success",
            "requirement": "pure protocol fresh session produces collector HUMAN success / oIIoIooo|0.",
            "status": status(False, missing=fresh_success_missing),
            "evidence": [
                str(PATHS["historicalProbe"].resolve()),
                str(PATHS["finalGap"].resolve()),
                str(PATHS["resetTerminal"].resolve()),
                str(PATHS["hypothesisPlanCoverage"].resolve()),
                str(PATHS["collectorServerExpectedState"].resolve()),
                str(PATHS["evidenceGatedPoc"].resolve()),
            ],
            "facts": [
                f"hasHistoricalNoBrowserSuccess0={historical_checks.get('hasHistoricalNoBrowserSuccess0')}",
                f"allLocalProxySearchesNegative={final_checks.get('allLocalProxySearchesNegative')}",
                f"highValueUnminedReplayableSuccessNotFound={final_checks.get('highValueUnminedReplayableSuccessNotFound')}",
                f"resetEndToEndPureProtocolPocMissing={reset_checks.get('endToEndPureProtocolPocMissing')}",
                f"resetNoCurrentRouteToPhase5={reset_checks.get('noCurrentRouteToPhase5')}",
                f"collectorServerExpectedStatePromotedCount={collector_server_checks.get('promotedSingleTransitionCandidateCount')}",
                f"candidateIntakePromotedCount={candidate_intake_checks.get('promotedSingleTransitionCandidateCount')}",
                f"minimalTransitionExperimentNetworkAttemptExecuted={minimal_experiment_checks.get('networkAttemptExecuted')}",
                f"minimalTransitionExperimentBlockedByGate={minimal_experiment_checks.get('blockedByGate')}",
                f"evidenceGatedPocFreshNoBrowserCollectorSuccess={gated_poc_checks.get('freshNoBrowserCollectorSuccess')}",
                f"evidenceGatedPocBlockedByGate={gated_poc_checks.get('blockedByGate')}",
                f"finalReplayBlockedByGate={final_replay_checks.get('blockedByGate')}",
                f"finalReplayGoalComplete={final_replay_checks.get('goalComplete')}",
            ],
            "blocking": True,
        },
        {
            "id": "R2_fresh_collector_response_decodes_success",
            "requirement": "collector response offline decoder contains success status for the fresh pure-protocol session.",
            "status": status(False, missing=fresh_success_missing),
            "evidence": [
                str(PATHS["historicalProbe"].resolve()),
                str(PATHS["goalAudit"].resolve()),
                str(PATHS["resetTerminal"].resolve()),
                str(PATHS["evidenceGatedPoc"].resolve()),
            ],
            "facts": [
                f"seq5Seq6ComboSuccess0Count={historical_checks.get('seq5Seq6ComboSuccess0Count')}",
                f"resetAnySeq5Success0={reset_checks.get('anySeq5Success0')}",
                f"resetAllFinalResponsesAreSeq5Minus1={reset_checks.get('allFinalResponsesAreSeq5Minus1')}",
                f"evidenceGatedPocFreshDecodedOIIoIooo0={gated_poc_checks.get('freshDecodedOIIoIooo0')}",
                "decoder is proven generally, but no fresh no-browser success response exists to decode",
            ],
            "blocking": True,
        },
        {
            "id": "R3_decoded_response_updates_px_cookie_jar",
            "requirement": "decoded response handler can update _px cookie/token jar offline.",
            "status": status(cookie_checks.get("multiRunJarUpdateWorks") is True or "px_cookie_token_update" in (goal_summary.get("proved") or [])),
            "evidence": [str(PATHS["cookieJar"].resolve()), str(PATHS["goalAudit"].resolve())],
            "facts": [
                f"goalAudit.provedContainsPxCookieTokenUpdate={'px_cookie_token_update' in (goal_summary.get('proved') or [])}",
                f"cookieChecks={cookie_checks}",
            ],
            "blocking": False,
        },
        {
            "id": "R4_risk_verify_returns_continue_with_jar",
            "requirement": "risk/verify using that jar returns state=continue.",
            "status": status(
                risk_checks.get("riskContinueTokenFeedsCreateAccount") is True
                or s00_risk_checks.get("riskVerifyStateContinue") is True
                or "risk_verify_rebuild" in (goal_summary.get("proved") or [])
            ),
            "evidence": [
                str(PATHS["collectorToRisk"].resolve()),
                str(PATHS["s00RiskGap"].resolve()),
                str(PATHS["goalAudit"].resolve()),
            ],
            "facts": [
                f"riskContinueTokenFeedsCreateAccount={risk_checks.get('riskContinueTokenFeedsCreateAccount')}",
                f"s00RiskVerifyStateContinue={s00_risk_checks.get('riskVerifyStateContinue')}",
                f"goalAudit.provedContainsRiskVerifyRebuild={'risk_verify_rebuild' in (goal_summary.get('proved') or [])}",
            ],
            "blocking": False,
            "scopeNote": "Proven for accepted s00/downstream material, not for a missing fresh no-browser collector success.",
        },
        {
            "id": "R5_create_account_redirect_url",
            "requirement": "CreateAccount returns redirectUrl.",
            "status": status(risk_checks.get("riskContinueTokenFeedsCreateAccount") is True or s00_risk_checks.get("createAccountRedirectUrl") is True),
            "evidence": [
                str(PATHS["collectorToRisk"].resolve()),
                str(PATHS["s00RiskGap"].resolve()),
            ],
            "facts": [
                f"riskContinueTokenFeedsCreateAccount={risk_checks.get('riskContinueTokenFeedsCreateAccount')}",
                f"createAccountRedirectUrl={s00_risk_checks.get('createAccountRedirectUrl')}",
            ],
            "blocking": False,
            "scopeNote": "Proven downstream for accepted s00 chain, not for a missing fresh no-browser collector success.",
        },
        {
            "id": "R6_no_browser_camoufox_mouse_vision_external_captcha",
            "requirement": "Full flow does not depend on browser/Camoufox/real mouse/vision/external captcha.",
            "status": "not_proven",
            "evidence": [str(PATHS["finalGap"].resolve()), str(PATHS["goalAudit"].resolve())],
            "facts": [
                "No full fresh no-browser success flow exists, so independence of the full flow cannot be proven.",
                f"goalComplete={goal_summary.get('goalComplete')}",
                f"resetReadyForFreshExperiment={reset_checks.get('readyForFreshExperiment')}",
                f"hypothesisMinimalExperimentMissingAllowedByGate={hypothesis_coverage_checks.get('minimalExperimentMissingAllowedByGate')}",
                f"evidenceGatedPocNetworkAttemptExecuted={gated_poc_checks.get('networkAttemptExecuted')}",
                f"minimalTransitionExperimentStageAdvanced={minimal_experiment_checks.get('stageAdvanced')}",
                f"candidateIntakeReadyForFreshExperiment={candidate_intake_checks.get('readyForFreshExperiment')}",
            ],
            "blocking": True,
        },
        {
            "id": "R7_reproducible_evidence_paths_commands",
            "requirement": "Every step has local evidence paths and reproducible commands.",
            "status": "partially_proven",
            "evidence": [
                str(PATHS["goalAudit"].resolve()),
                str(PATHS["finalGap"].resolve()),
                str(PATHS["proofScriptReproducibility"].resolve()),
                str(PATHS["resetTerminal"].resolve()),
                str(PATHS["evidenceGatedPoc"].resolve()),
            ],
            "facts": [
                "Existing proved subcomponents have local evidence paths.",
                "The missing end-to-end fresh no-browser PoC has no reproducible success command.",
                f"proofTaskCount={proof_checks.get('taskCount')}",
                f"proofPassedTaskCount={proof_checks.get('passedTaskCount')}",
                f"allProofScriptsReproducible={proof_checks.get('allProofScriptsReproducible')}",
                f"evidenceGatedPocExists={PATHS['evidenceGatedPoc'].exists()}",
                f"minimalTransitionExperimentExists={PATHS['minimalTransitionExperiment'].exists()}",
                f"minimalTransitionExperimentGoalComplete={minimal_experiment_checks.get('goalComplete')}",
                f"evidenceGatedPocGoalComplete={gated_poc_checks.get('goalComplete')}",
                f"finalReplayAuditExists={PATHS['finalReplayAudit'].exists()}",
                f"finalReplayReplayAttemptExecuted={final_replay_checks.get('replayAttemptExecuted')}",
                f"evidenceGateChainAllStepsPassed={gate_chain_checks.get('allStepsPassed')}",
                f"evidenceGateChainFinalProofTaskCount={gate_chain_checks.get('finalProofTaskCount')}",
                f"evidenceManifestAllFilesHashed={evidence_manifest_checks.get('allFilesHashed')}",
                f"evidenceManifestVerifyAllHashesMatch={evidence_manifest_verify_checks.get('allHashesMatch')}",
            ],
            "blocking": True,
        },
        {
            "id": "R8_no_stale_or_ungated_network_experiment",
            "requirement": "Network experiment is gated by one promoted pre-accept client-visible pure-protocol transition, not stale nextArtifact pointers or random retries.",
            "status": status(no_current_experiment_route),
            "evidence": [
                str(PATHS["resetTerminal"].resolve()),
                str(PATHS["hypothesisPlanCoverage"].resolve()),
                str(PATHS["currentRouteAuthority"].resolve()),
            ],
            "facts": [
                f"resetReadyForFreshExperiment={reset_checks.get('readyForFreshExperiment')}",
                f"resetNoCurrentRouteToPhase5={reset_checks.get('noCurrentRouteToPhase5')}",
                f"hypothesisPlanStaleHistoricalNextPointerCount={hypothesis_coverage_checks.get('staleHistoricalNextPointerCount')}",
                f"hypothesisPlanPromotedCount={hypothesis_coverage_checks.get('currentPromotedSingleTransitionCandidateCount')}",
                f"currentRouteAuthorityPromotedCount={route_authority_checks.get('currentPromotedSingleTransitionCandidateCount')}",
                f"candidateIntakePromotedCount={candidate_intake_checks.get('promotedSingleTransitionCandidateCount')}",
            ],
            "blocking": False,
            "scopeNote": "This proves the current no-network gate, not the missing end-to-end success.",
        },
    ]

    blocking = [row["id"] for row in requirements if row.get("blocking") and row["status"] != "proven"]
    checks = {
        "requirementCount": len(requirements),
        "provenCount": sum(1 for row in requirements if row["status"] == "proven"),
        "missingCount": sum(1 for row in requirements if row["status"] == "missing"),
        "notProvenCount": sum(1 for row in requirements if row["status"] == "not_proven"),
        "partiallyProvenCount": sum(1 for row in requirements if row["status"] == "partially_proven"),
        "blockingRequirementCount": len(blocking),
        "freshSuccessMissing": fresh_success_missing,
        "noCurrentExperimentRoute": no_current_experiment_route,
        "evidenceGatedPocExists": PATHS["evidenceGatedPoc"].exists(),
        "evidenceGatedPocBlockedByGate": gated_poc_checks.get("blockedByGate") is True,
        "evidenceGatedPocNetworkAttemptExecuted": gated_poc_checks.get("networkAttemptExecuted") is True,
        "evidenceGatedPocFreshCollectorSuccess": gated_poc_checks.get("freshNoBrowserCollectorSuccess") is True,
        "candidateIntakeExists": PATHS["candidateIntake"].exists(),
        "candidateIntakePromotedCount": candidate_intake_checks.get("promotedSingleTransitionCandidateCount"),
        "candidateIntakeReadyForFreshExperiment": candidate_intake_checks.get("readyForFreshExperiment") is True,
        "phase3ProposalEvidenceTriageExists": PATHS["phase3ProposalEvidenceTriage"].exists(),
        "phase3ProposalWorthyEvidenceCount": phase3_triage_checks.get("proposalWorthyEvidenceCount"),
        "phase3RecursiveReadyOrPromotedSignalCount": phase3_triage_checks.get("recursiveJsonReadyOrPromotedSignalCount"),
        "phase3ReadyForFreshExperiment": phase3_triage_checks.get("readyForFreshExperiment") is True,
        "phase3EvidenceEntranceCoverageExists": PATHS["phase3EvidenceEntranceCoverage"].exists(),
        "phase3UncoveredEntranceRowCount": phase3_entrance_checks.get("uncoveredEntranceRowCount"),
        "phase3ProposalEntranceExhaustedForCurrentEvidence": phase3_entrance_checks.get("proposalEntranceExhaustedForCurrentEvidence") is True,
        "phase3RawEvidenceEntranceExists": PATHS["phase3RawEvidenceEntrance"].exists(),
        "phase3RawSuccessSignalFileCount": phase3_raw_checks.get("rawSuccessSignalFileCount"),
        "phase3RawProposalWorthySignalCount": phase3_raw_checks.get("proposalWorthyRawSignalCount"),
        "phase3RawTraceCrosswalkExists": PATHS["phase3RawTraceCrosswalk"].exists(),
        "phase3RawTraceCrosswalkUnreferencedCount": phase3_crosswalk_checks.get("unreferencedTraceCount"),
        "phase3RawTraceCrosswalkProposalWorthyCount": phase3_crosswalk_checks.get("proposalWorthyRawTraceCount"),
        "traceClassifierRawCoverageGapExists": PATHS["traceClassifierRawCoverageGap"].exists(),
        "traceClassifierReferencedButUnclassifiedRawTraceCount": trace_classifier_gap_checks.get("referencedButUnclassifiedRawTraceCount"),
        "traceClassifierSafeToAutoAppend": trace_classifier_gap_checks.get("safeToAutoAppendToClassifier") is True,
        "traceClassifierProposalWorthyCoverageGapCount": trace_classifier_gap_checks.get("proposalWorthyCoverageGapCount"),
        "remainingBoundaryProposalGateExists": PATHS["remainingBoundaryProposalGate"].exists(),
        "remainingBoundaryProposalGateRowCount": remaining_boundary_gate_checks.get("proposalGateRowCount"),
        "remainingBoundaryProposalReadyRowCount": remaining_boundary_gate_checks.get("proposalReadyRowCount"),
        "remainingBoundaryProposalReadyForFreshExperiment": remaining_boundary_gate_checks.get("readyForFreshExperiment") is True,
        "candidateSourceContradictionLedgerExists": PATHS["candidateSourceContradictionLedger"].exists(),
        "candidateSourceContradictionLedgerIntakeRowCount": candidate_source_ledger_checks.get("intakeRowCount"),
        "candidateSourceContradictionLedgerGateRowCount": candidate_source_ledger_checks.get("gateRowCount"),
        "candidateSourceContradictionLedgerMatrixRowCount": candidate_source_ledger_checks.get("matrixRowCount"),
        "candidateSourceContradictionLedgerPromotedTotal": candidate_source_ledger_checks.get("promotedCandidateTotal"),
        "candidateSourceContradictionLedgerAllSourcesClosed": candidate_source_ledger_checks.get("allCandidateSourcesClosed"),
        "candidateSourceContradictionLedgerReadyForFreshExperiment": candidate_source_ledger_checks.get("readyForFreshExperiment") is True,
        "serverStateValueConsumptionLedgerExists": PATHS["serverStateValueConsumptionLedger"].exists(),
        "serverStateValueConsumptionLedgerValueComparisonCount": server_state_value_consumption_checks.get("valueComparisonCount"),
        "serverStateValueConsumptionLedgerConsumedValueCount": server_state_value_consumption_checks.get("consumedValueCount"),
        "serverStateValueConsumptionLedgerAllRowsCovered": server_state_value_consumption_checks.get("allRowsCoveredByControlOrCoupling"),
        "serverStateValueConsumptionLedgerSingleValueProposalReadyCount": server_state_value_consumption_checks.get("singleValueProposalReadyCount"),
        "serverStateValueConsumptionLedgerReadyForFreshExperiment": server_state_value_consumption_checks.get("readyForFreshExperiment") is True,
        "coupledBoundaryTerminalLedgerExists": PATHS["coupledBoundaryTerminalLedger"].exists(),
        "coupledBoundaryTerminalLedgerRowCount": coupled_boundary_terminal_checks.get("coupledBoundaryRowCount"),
        "coupledBoundaryTerminalLedgerProposalReadyRowCount": coupled_boundary_terminal_checks.get("proposalReadyRowCount"),
        "coupledBoundaryTerminalLedgerAllClosed": coupled_boundary_terminal_checks.get("allCoupledBoundariesClosedForCurrentEvidence"),
        "coupledBoundaryTerminalLedgerReadyForFreshExperiment": coupled_boundary_terminal_checks.get("readyForFreshExperiment") is True,
        "currentEvidenceEntranceTerminalLedgerExists": PATHS["currentEvidenceEntranceTerminalLedger"].exists(),
        "currentEvidenceEntranceTerminalLedgerNextPointerCount": current_evidence_entrance_terminal_checks.get("nextPointerCount"),
        "currentEvidenceEntranceTerminalLedgerUnresolvedNextPointerCount": current_evidence_entrance_terminal_checks.get("unresolvedNextPointerCount"),
        "currentEvidenceEntranceTerminalLedgerActiveActionableNextPointerCount": current_evidence_entrance_terminal_checks.get("activeActionableNextPointerCount"),
        "currentEvidenceEntranceTerminalLedgerAllClosedOrSuperseded": current_evidence_entrance_terminal_checks.get("allNextPointersClosedOrSuperseded"),
        "currentEvidenceEntranceTerminalLedgerReadyForFreshExperiment": current_evidence_entrance_terminal_checks.get("readyForFreshExperiment") is True,
        "convergentEvidenceEntranceMatrixExists": PATHS["convergentEvidenceEntranceMatrix"].exists(),
        "convergentEvidenceEntranceMatrixEntranceCount": convergent_evidence_entrance_matrix_checks.get("entranceCount"),
        "convergentEvidenceEntranceMatrixClosedEntranceCount": convergent_evidence_entrance_matrix_checks.get("closedEntranceCount"),
        "convergentEvidenceEntranceMatrixCandidateAffectingEntranceCount": convergent_evidence_entrance_matrix_checks.get("candidateAffectingEntranceCount"),
        "convergentEvidenceEntranceMatrixUncoveredCandidateAffectingEntranceCount": convergent_evidence_entrance_matrix_checks.get("uncoveredCandidateAffectingEntranceCount"),
        "convergentEvidenceEntranceMatrixRecommendedNextEntranceCount": convergent_evidence_entrance_matrix_checks.get("recommendedNextEntranceCount"),
        "convergentEvidenceEntranceMatrixReadyForFreshExperiment": convergent_evidence_entrance_matrix_checks.get("readyForFreshExperiment") is True,
        "manifestCoverageGapExists": PATHS["manifestCoverageGap"].exists(),
        "manifestCoverageGapScannedFileCount": manifest_coverage_gap_checks.get("scannedFileCount"),
        "manifestCoverageGapUnmanifestedFileCount": manifest_coverage_gap_checks.get("unmanifestedFileCount"),
        "manifestCoverageGapHighValueUncoveredDirectoryCount": manifest_coverage_gap_checks.get("highValueUncoveredDirectoryCount"),
        "manifestCoverageGapProposalWorthyUnmanifestedDirectoryCount": manifest_coverage_gap_checks.get("proposalWorthyUnmanifestedDirectoryCount"),
        "manifestCoverageGapConvergentRecommendedNextEntranceCount": manifest_coverage_gap_checks.get("convergentRecommendedNextEntranceCount"),
        "manifestCoverageGapReadyForFreshExperiment": manifest_coverage_gap_checks.get("readyForFreshExperiment") is True,
        "liveRunnerGateExists": PATHS["liveRunnerGate"].exists(),
        "liveRunnerGateAuthoritativeHarnessCount": live_runner_gate_checks.get("authoritativeHarnessCount"),
        "liveRunnerGateAuthoritativeHarnessBlockedCount": live_runner_gate_checks.get("authoritativeHarnessBlockedCount"),
        "liveRunnerGateProofInvokedUngatedLiveRunnerCount": live_runner_gate_checks.get("proofInvokedUngatedLiveRunnerCount"),
        "liveRunnerGateGateChainInvokedUngatedLiveRunnerCount": live_runner_gate_checks.get("gateChainInvokedUngatedLiveRunnerCount"),
        "liveRunnerGateCurrentNetworkAttemptBlocked": live_runner_gate_checks.get("currentNetworkAttemptBlocked"),
        "liveRunnerGateReadyForFreshExperiment": live_runner_gate_checks.get("readyForFreshExperiment") is True,
        "objectiveRequirementCrosswalkExists": PATHS["objectiveRequirementCrosswalk"].exists(),
        "objectiveRequirementCrosswalkRequirementCount": objective_crosswalk_checks.get("requirementCount"),
        "objectiveRequirementCrosswalkProvenCount": objective_crosswalk_checks.get("provenCount"),
        "objectiveRequirementCrosswalkBlockingRequirementCount": objective_crosswalk_checks.get("blockingRequirementCount"),
        "objectiveRequirementCrosswalkEndToEndPocMissing": objective_crosswalk_checks.get("endToEndPocMissing"),
        "objectiveRequirementCrosswalkFullNoBrowserIndependenceNotProven": objective_crosswalk_checks.get("fullNoBrowserIndependenceNotProven"),
        "objectiveRequirementCrosswalkTraceabilityOnlyPartiallyProven": objective_crosswalk_checks.get("traceabilityOnlyPartiallyProven"),
        "objectiveRequirementCrosswalkReadyForFreshExperiment": objective_crosswalk_checks.get("readyForFreshExperiment") is True,
        "objectiveRequirementCrosswalkGoalComplete": objective_crosswalk_checks.get("goalComplete") is True,
        "promotionPredicateBlockerCrosswalkExists": PATHS["promotionPredicateBlockerCrosswalk"].exists(),
        "promotionPredicateBlockerPredicateCount": promotion_blocker_checks.get("predicateCount"),
        "promotionPredicateBlockerUnsatisfiedPromotionPredicateCount": promotion_blocker_checks.get("unsatisfiedPromotionPredicateCount"),
        "promotionPredicateBlockerArtifactBackedNegativeDecision": promotion_blocker_checks.get("artifactBackedNegativeDecision"),
        "promotionPredicateBlockerStaleAuthorityCleanForNegativeDecision": promotion_blocker_checks.get("staleAuthorityCleanForNegativeDecision"),
        "promotionPredicateBlockerCandidateIntakePromotedCount": promotion_blocker_checks.get("candidateIntakePromotedCount"),
        "promotionPredicateBlockerRemainingBoundaryProposalReadyRowCount": promotion_blocker_checks.get("remainingBoundaryProposalReadyRowCount"),
        "promotionPredicateBlockerReadyForFreshExperiment": promotion_blocker_checks.get("readyForFreshExperiment") is True,
        "candidateExecutorReadinessExists": PATHS["candidateExecutorReadiness"].exists(),
        "candidateExecutorPlanRequiresCandidateSpecificExecutor": candidate_executor_checks.get("planRequiresCandidateSpecificExecutor"),
        "candidateExecutorHarnessDeclaresMissingCandidateSpecificExecutor": candidate_executor_checks.get("harnessDeclaresMissingCandidateSpecificExecutor"),
        "candidateExecutorCurrentGateClosedNoNetworkAttempt": candidate_executor_checks.get("currentGateClosedNoNetworkAttempt"),
        "candidateExecutorReadyForPromotedCandidate": candidate_executor_checks.get("executorReadyForPromotedCandidate") is True,
        "candidateExecutorReadyForFreshExperiment": candidate_executor_checks.get("readyForFreshExperiment") is True,
        "hypothesisTreeCurrentAuthorityExists": PATHS["hypothesisTreeCurrentAuthority"].exists(),
        "hypothesisTreeH3Terminal": hypothesis_tree_authority_checks.get("h3CollectorServerStateTerminalForCurrentEvidence"),
        "hypothesisTreeH4Terminal": hypothesis_tree_authority_checks.get("h4BrowserOnlyRuntimeTerminalForCurrentEvidence"),
        "hypothesisTreeH5NotCurrentEntrance": hypothesis_tree_authority_checks.get("h5MicrosoftContextNotCurrentEntrance"),
        "hypothesisTreeOldPlanNoLongerAuthorizesPhase5": hypothesis_tree_authority_checks.get("oldPlanNoLongerAuthorizesPhase5"),
        "hypothesisTreeConvergentPlanIsCurrentAuthority": hypothesis_tree_authority_checks.get("convergentPlanIsCurrentAuthority"),
        "hypothesisTreeReadyForFreshExperiment": hypothesis_tree_authority_checks.get("readyForFreshExperiment") is True,
        "nearestMissPromotionCandidateExists": PATHS["nearestMissPromotionCandidate"].exists(),
        "nearestMissCandidateRowCount": nearest_miss_checks.get("candidateRowCount"),
        "nearestMissNearestSatisfiedPredicateCount": nearest_miss_checks.get("nearestSatisfiedPredicateCount"),
        "nearestMissNearestMissingPredicateCount": nearest_miss_checks.get("nearestMissingPredicateCount"),
        "nearestMissProposalReadyCandidateCount": nearest_miss_checks.get("proposalReadyCandidateCount"),
        "nearestMissSingleMissingPredicateCandidateCount": nearest_miss_checks.get("singleMissingPredicateCandidateCount"),
        "nearestMissCandidateWithSingleTransitionCount": nearest_miss_checks.get("candidateWithSingleTransitionCount"),
        "nearestMissReadyForFreshExperiment": nearest_miss_checks.get("readyForFreshExperiment") is True,
        "nearestMissBlockerResolutionExists": PATHS["nearestMissBlockerResolution"].exists(),
        "nearestMissBlockerClosedByExistingControlsCount": nearest_miss_blocker_checks.get("closedByExistingControlsCount"),
        "nearestMissBlockerNeedsMoreEvidenceCount": nearest_miss_blocker_checks.get("needsMoreEvidenceCount"),
        "nearestMissBlockerPcValueClosed": nearest_miss_blocker_checks.get("pcValueClosedByExistingControls"),
        "nearestMissBlockerCollectorCookieHeaderClosed": nearest_miss_blocker_checks.get("collectorCookieHeaderClosedByExistingControls"),
        "nearestMissBlockerProposalReadyCandidateCount": nearest_miss_blocker_checks.get("proposalReadyCandidateCount"),
        "nearestMissBlockerReadyForFreshExperiment": nearest_miss_blocker_checks.get("readyForFreshExperiment") is True,
        "remainingNearestMissResolutionExists": PATHS["remainingNearestMissResolution"].exists(),
        "remainingNearestMissRowCount": remaining_nearest_checks.get("remainingNearestRowCount"),
        "remainingNearestMissClosedByExistingControlsCount": remaining_nearest_checks.get("closedByExistingControlsCount"),
        "remainingNearestMissOpenRowCount": remaining_nearest_checks.get("openRemainingNearestRowCount"),
        "remainingNearestMissProposalReadyCandidateCount": remaining_nearest_checks.get("proposalReadyCandidateCount"),
        "remainingNearestMissReadyForFreshExperiment": remaining_nearest_checks.get("readyForFreshExperiment") is True,
        "exhaustivePromotionCandidateResolutionExists": PATHS["exhaustivePromotionCandidateResolution"].exists(),
        "exhaustiveCandidateRowCount": exhaustive_candidate_checks.get("candidateRowCount"),
        "exhaustiveResolvedCandidateCount": exhaustive_candidate_checks.get("resolvedCandidateCount"),
        "exhaustiveClosedByExistingControlsCount": exhaustive_candidate_checks.get("closedByExistingControlsCount"),
        "exhaustiveOpenNeedsSpecificEvidenceCount": exhaustive_candidate_checks.get("openNeedsSpecificEvidenceCount"),
        "exhaustiveProposalReadyCandidateCount": exhaustive_candidate_checks.get("proposalReadyCandidateCount"),
        "exhaustiveReadyForFreshExperiment": exhaustive_candidate_checks.get("readyForFreshExperiment") is True,
        "nextEvidenceSurfaceDiscoveryExists": PATHS["nextEvidenceSurfaceDiscovery"].exists(),
        "nextEvidenceSurfaceCount": next_surface_checks.get("surfaceCount"),
        "nextEvidenceClosedSurfaceCount": next_surface_checks.get("closedSurfaceCount"),
        "nextEvidenceOpenSurfaceCount": next_surface_checks.get("openSurfaceCount"),
        "nextEvidenceNewCandidateSurfaceCount": next_surface_checks.get("newCandidateSurfaceCount"),
        "nextEvidenceSurfaceWithNewCandidateCount": next_surface_checks.get("surfaceWithNewCandidateCount"),
        "nextEvidenceReadyForFreshExperiment": next_surface_checks.get("readyForFreshExperiment") is True,
        "externalOutputSurfaceAuditExists": PATHS["externalOutputSurfaceAudit"].exists(),
        "externalOutputSurfaceAuditSignalFileCount": external_output_surface_checks.get("signalFileCount"),
        "externalOutputSurfaceAuditCollectorSuccess0SignalFileCount": external_output_surface_checks.get("collectorSuccess0SignalFileCount"),
        "externalOutputSurfaceAuditProposalWorthySignalCount": external_output_surface_checks.get("proposalWorthyExternalSignalCount"),
        "externalOutputSurfaceAuditReadyForFreshExperiment": external_output_surface_checks.get("readyForFreshExperiment") is True,
        "evidencePackageSurfaceAuditExists": PATHS["evidencePackageSurfaceAudit"].exists(),
        "evidencePackageSurfaceAuditSignalFileCount": evidence_package_surface_checks.get("signalFileCount"),
        "evidencePackageSurfaceAuditCollectorSuccess0SignalFileCount": evidence_package_surface_checks.get("collectorSuccess0SignalFileCount"),
        "evidencePackageSurfaceAuditProposalWorthySignalCount": evidence_package_surface_checks.get("proposalWorthyEvidencePackageSignalCount"),
        "evidencePackageSurfaceAuditReadyForFreshExperiment": evidence_package_surface_checks.get("readyForFreshExperiment") is True,
        "ctfRegOutputSurfaceAuditExists": PATHS["ctfRegOutputSurfaceAudit"].exists(),
        "ctfRegOutputSurfaceAuditSignalFileCount": ctf_reg_output_surface_checks.get("signalFileCount"),
        "ctfRegOutputSurfaceAuditCollectorSuccess0SignalFileCount": ctf_reg_output_surface_checks.get("collectorSuccess0SignalFileCount"),
        "ctfRegOutputSurfaceAuditProposalWorthySignalCount": ctf_reg_output_surface_checks.get("proposalWorthyCtfRegSignalCount"),
        "ctfRegOutputSurfaceAuditReadyForFreshExperiment": ctf_reg_output_surface_checks.get("readyForFreshExperiment") is True,
        "auxiliaryTraceSurfaceAuditExists": PATHS["auxiliaryTraceSurfaceAudit"].exists(),
        "auxiliaryTraceSurfaceAuditSignalFileCount": auxiliary_trace_surface_checks.get("signalFileCount"),
        "auxiliaryTraceSurfaceAuditCollectorSuccess0SignalFileCount": auxiliary_trace_surface_checks.get("collectorSuccess0SignalFileCount"),
        "auxiliaryTraceSurfaceAuditProposalWorthySignalCount": auxiliary_trace_surface_checks.get("proposalWorthyAuxiliarySignalCount"),
        "auxiliaryTraceSurfaceAuditReadyForFreshExperiment": auxiliary_trace_surface_checks.get("readyForFreshExperiment") is True,
        "stalePositiveSignalAuthorityExists": PATHS["stalePositiveSignalAuthority"].exists(),
        "stalePositiveSignalAuthorityPositiveSignalCount": stale_positive_signal_authority_checks.get("positiveSignalCount"),
        "stalePositiveSignalAuthorityActiveActionablePositiveSignalCount": stale_positive_signal_authority_checks.get("activeActionablePositiveSignalCount"),
        "stalePositiveSignalAuthorityCandidateIntakePromotedCount": stale_positive_signal_authority_checks.get("candidateIntakePromotedCount"),
        "stalePositiveSignalAuthorityReadyForFreshExperiment": stale_positive_signal_authority_checks.get("readyForFreshExperiment") is True,
        "localTraceEvidenceFreshnessExists": PATHS["localTraceEvidenceFreshness"].exists(),
        "localTraceUnclassifiedHighValueSignalRunCount": local_trace_freshness_checks.get("unclassifiedHighValueSignalRunCount"),
        "localTraceProposalWorthyNowCount": local_trace_freshness_checks.get("proposalWorthyNowCount"),
        "unclassifiedTraceSignalReductionExists": PATHS["unclassifiedTraceSignalReduction"].exists(),
        "unclassifiedTraceBrowserSuccessChainRunCount": unclassified_trace_reduction_checks.get("browserSuccessChainRunCount"),
        "unclassifiedTraceProposalReadyRunCount": unclassified_trace_reduction_checks.get("proposalReadyRunCount"),
        "browserSuccessChainClassificationBacklogExists": PATHS["browserSuccessChainClassificationBacklog"].exists(),
        "browserSuccessChainClassificationBacklogCount": browser_success_backlog_checks.get("classificationBacklogCount"),
        "browserSuccessChainClassificationBacklogNoBrowserEvidenceCount": browser_success_backlog_checks.get("noBrowserEvidenceCount"),
        "browserSuccessChainClassificationBacklogProposalReadyRunCount": browser_success_backlog_checks.get("proposalReadyRunCount"),
        "browserSuccessChainClassificationBacklogSafeToPromoteToClassifier": browser_success_backlog_checks.get("safeToPromoteToClassifier") is True,
        "browserSuccessChainServerVisibleDiffExists": PATHS["browserSuccessChainServerVisibleDiff"].exists(),
        "browserSuccessChainServerVisibleDiffCount": browser_success_diff_checks.get("earliestServerVisibleDiffCount"),
        "browserSuccessChainServerVisibleProposalCandidateCount": browser_success_diff_checks.get("proposalCandidateCount"),
        "browserSuccessChainServerVisibleContradictedDiffCount": browser_success_diff_checks.get("contradictedDiffCount"),
        "browserSuccessPayloadPcSessionLineageExists": PATHS["browserSuccessPayloadPcSessionLineage"].exists(),
        "browserSuccessPayloadPcSessionLineageRowCount": payload_pc_session_lineage_checks.get("fieldLineageRowCount"),
        "browserSuccessPayloadPcSessionLineageContradictedCount": payload_pc_session_lineage_checks.get("fieldLineageContradictedCount"),
        "browserSuccessPayloadPcSessionLineageProposalCandidateCount": payload_pc_session_lineage_checks.get("proposalCandidateCount"),
        "collectorResponseHandlerValueLineageExists": PATHS["collectorResponseHandlerValueLineage"].exists(),
        "collectorResponseHandlerValueLineageDecodedRunCount": collector_handler_value_lineage_checks.get("decodedRunCount"),
        "collectorResponseHandlerValueLineageProposalCandidateCount": collector_handler_value_lineage_checks.get("proposalCandidateCount"),
        "collectorResponseHandlerValueLineageCookieFailureStillMutates": collector_handler_value_lineage_checks.get("cookieMutationFailureStillMutates"),
        "downstreamSuccessWithoutCollectorDecodeExists": PATHS["downstreamSuccessWithoutCollectorDecode"].exists(),
        "downstreamSuccessWithoutCollectorDecodeRunCount": downstream_without_collector_checks.get("downstreamClassRunCount"),
        "downstreamSuccessWithoutCollectorDecodeSuccessRunCount": downstream_without_collector_checks.get("downstreamSuccessRunCount"),
        "downstreamSuccessWithoutCollectorDecodeCollectorSuccessCount": downstream_without_collector_checks.get("collectorSuccessDecodeRunCount"),
        "downstreamSuccessWithoutCollectorDecodeAllLackCollectorSuccess": downstream_without_collector_checks.get("allDownstreamRowsLackCollectorSuccessDecode"),
        "downstreamSuccessWithoutCollectorDecodeProposalCandidateCount": downstream_without_collector_checks.get("proposalCandidateCount"),
        "collectorMaterialOnlyResponseClassExists": PATHS["collectorMaterialOnlyResponseClass"].exists(),
        "collectorMaterialOnlyResponseClassRunCount": collector_material_only_checks.get("collectorMaterialOnlyRunCount"),
        "collectorMaterialOnlyResponseClassCollectorSuccessCount": collector_material_only_checks.get("collectorSuccessDecodeRunCount"),
        "collectorMaterialOnlyResponseClassRiskContinueCount": collector_material_only_checks.get("riskContinueRunCount"),
        "collectorMaterialOnlyResponseClassCreateRedirectCount": collector_material_only_checks.get("createRedirectRunCount"),
        "collectorMaterialOnlyResponseClassProposalCandidateCount": collector_material_only_checks.get("proposalCandidateCount"),
        "lowValueUnclassifiedTraceClosureExists": PATHS["lowValueUnclassifiedTraceClosure"].exists(),
        "lowValueUnclassifiedTraceClosureRunCount": low_value_closure_checks.get("lowValueRunCount"),
        "lowValueUnclassifiedTraceClosureProposalRelevantCount": low_value_closure_checks.get("rescannedProposalRelevantSignalRunCount"),
        "lowValueUnclassifiedTraceClosureAllRemainLowValue": low_value_closure_checks.get("allRowsRemainLowValue"),
        "lowValueUnclassifiedTraceClosureProposalCandidateCount": low_value_closure_checks.get("proposalCandidateCount"),
        "unclassifiedTraceClassClosureLedgerExists": PATHS["unclassifiedTraceClassClosureLedger"].exists(),
        "unclassifiedTraceClassClosureLedgerRunCount": trace_class_ledger_checks.get("ledgerRunCount"),
        "unclassifiedTraceClassClosureLedgerAllClosed": trace_class_ledger_checks.get("allTraceClassesClosed"),
        "unclassifiedTraceClassClosureLedgerProposalCandidateTotal": trace_class_ledger_checks.get("proposalCandidateTotal"),
        "minimalTransitionExperimentExists": PATHS["minimalTransitionExperiment"].exists(),
        "minimalTransitionExperimentBlockedByGate": minimal_experiment_checks.get("blockedByGate") is True,
        "minimalTransitionExperimentNetworkAttemptExecuted": minimal_experiment_checks.get("networkAttemptExecuted") is True,
        "minimalTransitionExperimentStageAdvanced": minimal_experiment_checks.get("stageAdvanced") is True,
        "finalReplayAuditExists": PATHS["finalReplayAudit"].exists(),
        "finalReplayBlockedByGate": final_replay_checks.get("blockedByGate") is True,
        "finalReplayAttemptExecuted": final_replay_checks.get("replayAttemptExecuted") is True,
        "finalReplayGoalComplete": final_replay_checks.get("goalComplete") is True,
        "evidenceGateChainExists": PATHS["evidenceGateChain"].exists(),
        "evidenceGateChainAllStepsPassed": gate_chain_checks.get("allStepsPassed") is True,
        "evidenceGateChainFinalProofTaskCount": gate_chain_checks.get("finalProofTaskCount"),
        "evidenceGateChainGoalComplete": gate_chain_checks.get("goalComplete") is True,
        "evidenceManifestExists": PATHS["evidenceManifest"].exists(),
        "evidenceManifestAllFilesExist": evidence_manifest_checks.get("allFilesExist") is True,
        "evidenceManifestAllFilesHashed": evidence_manifest_checks.get("allFilesHashed") is True,
        "evidenceManifestDuplicateHashCount": evidence_manifest_checks.get("duplicateHashCount"),
        "evidenceManifestGoalComplete": evidence_manifest_checks.get("goalComplete") is True,
        "evidenceManifestVerifyExists": PATHS["evidenceManifestVerify"].exists(),
        "evidenceManifestVerifyAllFilesExist": evidence_manifest_verify_checks.get("allFilesExist") is True,
        "evidenceManifestVerifyAllHashesMatch": evidence_manifest_verify_checks.get("allHashesMatch") is True,
        "evidenceManifestVerifyHashMismatchCount": evidence_manifest_verify_checks.get("hashMismatchCount"),
        "evidenceManifestVerifyGoalComplete": evidence_manifest_verify_checks.get("goalComplete") is True,
        "goalCompletionVerifierExists": PATHS["goalCompletionVerifier"].exists(),
        "goalCompletionVerifierCompletionVerified": goal_completion_verifier_checks.get("completionVerified") is True,
        "goalCompletionVerifierFailedGateCount": goal_completion_verifier_checks.get("failedGateCount"),
        "goalCompletionVerifierGoalComplete": goal_completion_verifier_checks.get("goalComplete") is True,
        "allProofScriptsReproducible": proof_checks.get("allProofScriptsReproducible") is True,
        "proofTaskCount": proof_checks.get("taskCount"),
        "resetNoCurrentRouteToPhase5": reset_checks.get("noCurrentRouteToPhase5") is True,
        "hypothesisPlanCoverageReady": hypothesis_coverage_checks.get("allHypothesesCovered") is True,
        "goalComplete": False,
        "readyForFreshExperiment": False,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Requirement-level completion audit for the pure-protocol HUMAN end-to-end objective.",
        "inputs": {key: str(path.resolve()) for key, path in PATHS.items()},
        "requirements": requirements,
        "blockingRequirements": blocking,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "reason": "The required fresh pure-protocol collector HUMAN success is missing; downstream accepted-s00 proof cannot satisfy the end-to-end fresh no-browser PoC requirement.",
            "nextArtifact": None,
            "nextScript": None,
        },
        "checks": checks,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
