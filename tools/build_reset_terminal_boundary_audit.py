#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-forward-plan.md"
IMPLEMENTATION_PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"
AUTHORITATIVE_PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
RESET = ROOT / "output/protocol_reverse/reset_plan"
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json"
OUT = RESET / "reset_terminal_boundary_audit.json"

INPUTS = {
    "resetSamplingCoverage": RESET / "reset_sampling_coverage_audit.json",
    "resetSamplingMatrix": RESET / "reset_sampling_matrix.json",
    "resetStateMachine": RESET / "reset_state_machine.json",
    "resetSingleTransitionCandidates": RESET / "reset_single_transition_candidates.json",
    "resetNewHookAxisPlan": RESET / "reset_new_hook_axis_plan.json",
    "resetHookFeatureCandidateReduction": RESET / "reset_hook_feature_candidate_reduction.json",
    "resetRuntimeJsEventTaxonomy": RESET / "reset_runtime_js_event_taxonomy.json",
    "resetRuntimeJsCandidateReduction": RESET / "reset_runtime_js_candidate_reduction.json",
    "resetCollectorHandlerSurfaceAudit": RESET / "reset_collector_handler_surface_audit.json",
    "resetUnobservedLifecycleSurfaceAudit": RESET / "reset_unobserved_lifecycle_surface_audit.json",
    "resetRouteBResamplingManifest": RESET / "reset_route_b_resampling_manifest.json",
    "resetRouteBLifecycleContrastAudit": RESET / "reset_route_b_lifecycle_contrast_audit.json",
    "resetRouteBValueTaxonomyAudit": RESET / "reset_route_b_value_taxonomy_audit.json",
    "resetRouteBInstrumentationControlAudit": RESET / "reset_route_b_instrumentation_control_audit.json",
    "resetOneCollectorSurfaceAudit": RESET / "reset_onecollector_surface_audit.json",
    "methodologicalTerminalBoundaryAudit": RESET / "methodological_terminal_boundary_audit.json",
    "nextEvidenceEntranceAudit": RESET / "next_evidence_entrance_audit.json",
    "encoderVariantTerminalAudit": HYP / "encoder_variant_terminal_audit.json",
    "browserContextToServerStateProxyAudit": HYP / "browser_context_to_server_state_proxy_audit.json",
    "browserContextStaticGapInventory": HYP / "browser_context_static_gap_inventory.json",
    "postStaticContextTerminalGapAudit": HYP / "post_static_context_terminal_gap_audit.json",
    "currentRouteAuthorityAudit": HYP / "current_route_authority_audit.json",
    "recursiveEvidenceBlindspotAudit": HYP / "recursive_evidence_blindspot_audit.json",
    "nonJsonEvidenceBlindspotAudit": HYP / "non_json_evidence_blindspot_audit.json",
    "proofScriptReproducibilityAudit": HYP / "proof_script_reproducibility_audit.json",
    "endToEndRemainingBoundaryAudit": HYP / "end_to_end_remaining_boundary_audit.json",
    "browserCookieBridgeCandidateAudit": HYP / "browser_cookie_bridge_candidate_audit.json",
    "encodedSessionBindingCandidateAudit": HYP / "encoded_session_binding_candidate_audit.json",
    "collectorServerExpectedStateBoundaryAudit": HYP / "collector_server_expected_state_boundary_audit.json",
    "promotedTransitionCandidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "phase3ProposalEvidenceTriage": HYP / "phase3_proposal_evidence_triage.json",
    "phase3EvidenceEntranceCoverage": HYP / "phase3_evidence_entrance_coverage_audit.json",
    "phase3RawEvidenceEntrance": HYP / "phase3_raw_evidence_entrance_audit.json",
    "phase3RawTraceCrosswalk": HYP / "phase3_raw_trace_crosswalk_audit.json",
    "traceClassifierRawCoverageGap": HYP / "trace_classifier_raw_coverage_gap_audit.json",
    "remainingBoundaryProposalGate": HYP / "remaining_boundary_proposal_gate_audit.json",
    "candidateSourceContradictionLedger": HYP / "candidate_source_contradiction_ledger.json",
    "serverStateValueConsumptionLedger": HYP / "server_state_value_consumption_ledger.json",
    "coupledBoundaryTerminalLedger": HYP / "coupled_boundary_terminal_ledger.json",
    "currentEvidenceEntranceTerminalLedger": HYP / "current_evidence_entrance_terminal_ledger.json",
    "convergentEvidenceEntranceMatrix": HYP / "convergent_evidence_entrance_matrix.json",
    "manifestCoverageGap": HYP / "manifest_coverage_gap_audit.json",
    "liveRunnerGate": HYP / "live_runner_gate_audit.json",
    "objectiveRequirementCrosswalk": HYP / "objective_requirement_crosswalk.json",
    "promotionPredicateBlockerCrosswalk": HYP / "promotion_predicate_blocker_crosswalk.json",
    "candidateExecutorReadiness": HYP / "candidate_executor_readiness_audit.json",
    "hypothesisTreeCurrentAuthority": HYP / "hypothesis_tree_current_authority_audit.json",
    "nearestMissPromotionCandidate": HYP / "nearest_miss_promotion_candidate_audit.json",
    "nearestMissBlockerResolution": HYP / "nearest_miss_blocker_resolution_audit.json",
    "remainingNearestMissResolution": HYP / "remaining_nearest_miss_resolution_audit.json",
    "exhaustivePromotionCandidateResolution": HYP / "exhaustive_promotion_candidate_resolution_audit.json",
    "nextEvidenceSurfaceDiscovery": HYP / "next_evidence_surface_discovery_audit.json",
    "externalOutputSurfaceAudit": HYP / "external_output_surface_audit.json",
    "evidencePackageSurfaceAudit": HYP / "evidence_package_surface_audit.json",
    "ctfRegOutputSurfaceAudit": HYP / "ctf_reg_output_surface_audit.json",
    "auxiliaryTraceSurfaceAudit": HYP / "auxiliary_trace_surface_audit.json",
    "stalePositiveSignalAuthority": HYP / "stale_positive_signal_authority_audit.json",
    "localTraceEvidenceFreshness": HYP / "local_trace_evidence_freshness_audit.json",
    "unclassifiedTraceSignalReduction": HYP / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessChainClassificationBacklog": HYP / "browser_success_chain_classification_backlog.json",
    "browserSuccessChainServerVisibleDiff": HYP / "browser_success_chain_server_visible_diff_audit.json",
    "browserSuccessPayloadPcSessionLineage": HYP / "browser_success_payload_pc_session_lineage_audit.json",
    "collectorResponseHandlerValueLineage": HYP / "collector_response_handler_value_lineage_audit.json",
    "downstreamSuccessWithoutCollectorDecode": HYP / "downstream_success_without_collector_decode_audit.json",
    "collectorMaterialOnlyResponseClass": HYP / "collector_material_only_response_class_audit.json",
    "lowValueUnclassifiedTraceClosure": HYP / "low_value_unclassified_trace_closure_audit.json",
    "unclassifiedTraceClassClosureLedger": HYP / "unclassified_trace_class_closure_ledger.json",
    "hypothesisPlanCoverageAudit": HYP / "hypothesis_plan_coverage_audit.json",
    "pureProtocolCompletionRequirementsAudit": HYP / "pure_protocol_completion_requirements_audit.json",
    "minimalPromotedTransitionExperiment": HYP / "minimal_promoted_transition_experiment.json",
    "resetFinalResponseClassAudit": RESET / "reset_final_response_class_audit.json",
    "resetCookieMutationAudit": RESET / "reset_cookie_mutation_audit.json",
    "resetTransportIpHypothesisAudit": RESET / "reset_transport_ip_hypothesis_audit.json",
    "resetTransportIpDecisionAudit": RESET / "reset_transport_ip_decision_audit.json",
    "webshareProxyAuthGapAudit": RESET / "webshare_proxy_auth_gap_audit.json",
    "legacyServerInternalGap": HYP / "server_internal_unobserved_state_final_gap.json",
    "legacyActionableFrontier": HYP / "actionable_frontier_audit.json",
    "legacyUnminedLocalEvidenceSourceAudit": HYP / "unmined_local_evidence_source_audit.json",
    "legacyHighValueUnminedTriage": HYP / "high_value_unmined_evidence_triage.json",
    "goalGapAudit": GOAL,
    "evidenceGatedEndToEndPoc": ROOT / "output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalPureProtocolReplayAudit": ROOT / "output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json",
    "evidenceGateChainAudit": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json",
    "evidenceManifest": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest.json",
    "evidenceManifestVerify": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json",
    "goalCompletionVerifier": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json",
    "candidateProposalsLintControls": HYP / "promoted_transition_candidate_proposals_lint_controls.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    coverage = docs["resetSamplingCoverage"]
    matrix = docs["resetSamplingMatrix"]
    state = docs["resetStateMachine"]
    single = docs["resetSingleTransitionCandidates"]
    hook_axis = docs["resetNewHookAxisPlan"]
    reducer = docs["resetHookFeatureCandidateReduction"]
    runtime_taxonomy = docs["resetRuntimeJsEventTaxonomy"]
    runtime_reduction = docs["resetRuntimeJsCandidateReduction"]
    handler_audit = docs["resetCollectorHandlerSurfaceAudit"]
    lifecycle_audit = docs["resetUnobservedLifecycleSurfaceAudit"]
    route_b_manifest = docs["resetRouteBResamplingManifest"]
    route_b_contrast = docs["resetRouteBLifecycleContrastAudit"]
    route_b_value = docs["resetRouteBValueTaxonomyAudit"]
    route_b_instr = docs["resetRouteBInstrumentationControlAudit"]
    onecollector = docs["resetOneCollectorSurfaceAudit"]
    methodological_terminal = docs["methodologicalTerminalBoundaryAudit"]
    next_entrance = docs["nextEvidenceEntranceAudit"]
    encoder_variant_terminal = docs["encoderVariantTerminalAudit"]
    browser_context_proxy = docs["browserContextToServerStateProxyAudit"]
    browser_context_static = docs["browserContextStaticGapInventory"]
    post_static_context_terminal = docs["postStaticContextTerminalGapAudit"]
    current_route_authority = docs["currentRouteAuthorityAudit"]
    recursive_blindspot = docs["recursiveEvidenceBlindspotAudit"]
    non_json_blindspot = docs["nonJsonEvidenceBlindspotAudit"]
    proof_repro = docs["proofScriptReproducibilityAudit"]
    e2e_boundary = docs["endToEndRemainingBoundaryAudit"]
    cookie_bridge_candidate = docs["browserCookieBridgeCandidateAudit"]
    encoded_session_candidate = docs["encodedSessionBindingCandidateAudit"]
    collector_server_expected = docs["collectorServerExpectedStateBoundaryAudit"]
    candidate_intake = docs["promotedTransitionCandidateIntake"]
    phase3_triage = docs["phase3ProposalEvidenceTriage"]
    phase3_entrance = docs["phase3EvidenceEntranceCoverage"]
    phase3_raw = docs["phase3RawEvidenceEntrance"]
    phase3_crosswalk = docs["phase3RawTraceCrosswalk"]
    trace_classifier_gap = docs["traceClassifierRawCoverageGap"]
    remaining_boundary_gate = docs["remainingBoundaryProposalGate"]
    candidate_source_ledger = docs["candidateSourceContradictionLedger"]
    server_state_value_consumption = docs["serverStateValueConsumptionLedger"]
    coupled_boundary_terminal = docs["coupledBoundaryTerminalLedger"]
    current_evidence_entrance_terminal = docs["currentEvidenceEntranceTerminalLedger"]
    convergent_evidence_entrance_matrix = docs["convergentEvidenceEntranceMatrix"]
    manifest_coverage_gap = docs["manifestCoverageGap"]
    live_runner_gate = docs["liveRunnerGate"]
    objective_crosswalk = docs["objectiveRequirementCrosswalk"]
    promotion_blocker = docs["promotionPredicateBlockerCrosswalk"]
    candidate_executor_readiness = docs["candidateExecutorReadiness"]
    hypothesis_tree_authority = docs["hypothesisTreeCurrentAuthority"]
    nearest_miss_promotion = docs["nearestMissPromotionCandidate"]
    nearest_miss_blocker = docs["nearestMissBlockerResolution"]
    remaining_nearest_miss = docs["remainingNearestMissResolution"]
    exhaustive_candidate_resolution = docs["exhaustivePromotionCandidateResolution"]
    next_evidence_surface = docs["nextEvidenceSurfaceDiscovery"]
    external_output_surface = docs["externalOutputSurfaceAudit"]
    evidence_package_surface = docs["evidencePackageSurfaceAudit"]
    ctf_reg_output_surface = docs["ctfRegOutputSurfaceAudit"]
    auxiliary_trace_surface = docs["auxiliaryTraceSurfaceAudit"]
    stale_positive_signal_authority = docs["stalePositiveSignalAuthority"]
    local_trace_freshness = docs["localTraceEvidenceFreshness"]
    unclassified_trace_reduction = docs["unclassifiedTraceSignalReduction"]
    browser_success_backlog = docs["browserSuccessChainClassificationBacklog"]
    browser_success_diff = docs["browserSuccessChainServerVisibleDiff"]
    payload_pc_session_lineage = docs["browserSuccessPayloadPcSessionLineage"]
    collector_handler_value_lineage = docs["collectorResponseHandlerValueLineage"]
    downstream_without_collector = docs["downstreamSuccessWithoutCollectorDecode"]
    collector_material_only_response = docs["collectorMaterialOnlyResponseClass"]
    low_value_closure = docs["lowValueUnclassifiedTraceClosure"]
    trace_class_ledger = docs["unclassifiedTraceClassClosureLedger"]
    hypothesis_plan_coverage = docs["hypothesisPlanCoverageAudit"]
    completion_requirements = docs["pureProtocolCompletionRequirementsAudit"]
    minimal_transition_experiment = docs["minimalPromotedTransitionExperiment"]
    final_class = docs["resetFinalResponseClassAudit"]
    cookie = docs["resetCookieMutationAudit"]
    transport = docs["resetTransportIpHypothesisAudit"]
    transport_decision = docs["resetTransportIpDecisionAudit"]
    proxy_auth = docs["webshareProxyAuthGapAudit"]
    legacy_gap = docs["legacyServerInternalGap"]
    legacy_frontier = docs["legacyActionableFrontier"]
    legacy_triage = docs["legacyHighValueUnminedTriage"]
    legacy_unmined = docs.get("legacyUnminedLocalEvidenceSourceAudit") or {}
    goal = docs["goalGapAudit"]
    evidence_gated_poc = docs["evidenceGatedEndToEndPoc"]
    final_replay = docs["finalPureProtocolReplayAudit"]
    gate_chain = docs["evidenceGateChainAudit"]
    evidence_manifest = docs["evidenceManifest"]
    evidence_manifest_verify = docs["evidenceManifestVerify"]
    goal_completion_verifier = docs["goalCompletionVerifier"]
    proposal_lint_controls = docs["candidateProposalsLintControls"]

    c_coverage = checks(coverage)
    c_matrix = checks(matrix)
    c_state = checks(state)
    c_single = checks(single)
    c_hook_axis = checks(hook_axis)
    c_reducer = checks(reducer)
    c_runtime_taxonomy = checks(runtime_taxonomy)
    c_runtime_reduction = checks(runtime_reduction)
    c_handler = checks(handler_audit)
    c_lifecycle = checks(lifecycle_audit)
    c_route_b_manifest = checks(route_b_manifest)
    c_route_b_contrast = checks(route_b_contrast)
    c_route_b_value = checks(route_b_value)
    c_route_b_instr = checks(route_b_instr)
    c_onecollector = checks(onecollector)
    c_methodological = checks(methodological_terminal)
    c_next_entrance = checks(next_entrance)
    c_encoder_terminal = checks(encoder_variant_terminal)
    c_browser_context_proxy = checks(browser_context_proxy)
    c_browser_context_static = checks(browser_context_static)
    c_post_static_context_terminal = checks(post_static_context_terminal)
    c_current_route_authority = checks(current_route_authority)
    c_recursive_blindspot = checks(recursive_blindspot)
    c_non_json_blindspot = checks(non_json_blindspot)
    c_proof_repro = checks(proof_repro)
    c_e2e_boundary = checks(e2e_boundary)
    c_cookie_bridge_candidate = checks(cookie_bridge_candidate)
    c_encoded_session_candidate = checks(encoded_session_candidate)
    c_collector_server_expected = checks(collector_server_expected)
    c_candidate_intake = checks(candidate_intake)
    c_phase3_triage = checks(phase3_triage)
    c_phase3_entrance = checks(phase3_entrance)
    c_phase3_raw = checks(phase3_raw)
    c_phase3_crosswalk = checks(phase3_crosswalk)
    c_trace_classifier_gap = checks(trace_classifier_gap)
    c_remaining_boundary_gate = checks(remaining_boundary_gate)
    c_candidate_source_ledger = checks(candidate_source_ledger)
    c_server_state_value_consumption = checks(server_state_value_consumption)
    c_coupled_boundary_terminal = checks(coupled_boundary_terminal)
    c_current_evidence_entrance_terminal = checks(current_evidence_entrance_terminal)
    c_convergent_evidence_entrance_matrix = checks(convergent_evidence_entrance_matrix)
    c_manifest_coverage_gap = checks(manifest_coverage_gap)
    c_live_runner_gate = checks(live_runner_gate)
    c_objective_crosswalk = checks(objective_crosswalk)
    c_promotion_blocker = checks(promotion_blocker)
    c_candidate_executor = checks(candidate_executor_readiness)
    c_hypothesis_tree_authority = checks(hypothesis_tree_authority)
    c_nearest_miss = checks(nearest_miss_promotion)
    c_nearest_miss_blocker = checks(nearest_miss_blocker)
    c_remaining_nearest = checks(remaining_nearest_miss)
    c_exhaustive_candidate = checks(exhaustive_candidate_resolution)
    c_next_surface = checks(next_evidence_surface)
    c_external_output_surface = checks(external_output_surface)
    c_evidence_package_surface = checks(evidence_package_surface)
    c_ctf_reg_output_surface = checks(ctf_reg_output_surface)
    c_auxiliary_trace_surface = checks(auxiliary_trace_surface)
    c_stale_positive_signal_authority = checks(stale_positive_signal_authority)
    c_local_trace_freshness = checks(local_trace_freshness)
    c_unclassified_trace_reduction = checks(unclassified_trace_reduction)
    c_browser_success_backlog = checks(browser_success_backlog)
    c_browser_success_diff = checks(browser_success_diff)
    c_payload_pc_session_lineage = checks(payload_pc_session_lineage)
    c_collector_handler_value_lineage = checks(collector_handler_value_lineage)
    c_downstream_without_collector = checks(downstream_without_collector)
    c_collector_material_only_response = checks(collector_material_only_response)
    c_low_value_closure = checks(low_value_closure)
    c_trace_class_ledger = checks(trace_class_ledger)
    c_hypothesis_plan_coverage = checks(hypothesis_plan_coverage)
    c_completion_requirements = checks(completion_requirements)
    c_minimal_transition_experiment = checks(minimal_transition_experiment)
    c_final = checks(final_class)
    c_cookie = checks(cookie)
    c_transport = checks(transport)
    c_transport_decision = checks(transport_decision)
    c_proxy_auth = checks(proxy_auth)
    c_legacy_gap = checks(legacy_gap)
    c_legacy_frontier = checks(legacy_frontier)
    c_legacy_triage = checks(legacy_triage)
    c_legacy_unmined = checks(legacy_unmined)
    s_goal = summary(goal)
    c_evidence_gated_poc = checks(evidence_gated_poc)
    c_final_replay = checks(final_replay)
    c_gate_chain = checks(gate_chain)
    c_evidence_manifest = checks(evidence_manifest)
    c_evidence_manifest_verify = checks(evidence_manifest_verify)
    c_goal_completion_verifier = checks(goal_completion_verifier)
    c_proposal_lint_controls = checks(proposal_lint_controls)

    reset_checks = {
        "planExists": PLAN.exists(),
        "implementationPlanExists": IMPLEMENTATION_PLAN.exists(),
        "authoritativePlanExists": AUTHORITATIVE_PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "resetSamplingComplete": c_matrix.get("resetSamplingComplete") is True,
        "pureProtocolResetSamplingComplete": c_matrix.get("pureProtocolResetSamplingComplete") is True,
        "allResetCoverageComplete": c_coverage.get("allResetCoverageComplete") is True,
        "browserResetCoverageComplete": c_coverage.get("browserResetCoverageComplete") is True,
        "pureProtocolResetCoverageComplete": c_coverage.get("pureProtocolResetCoverageComplete") is True,
        "stateMachineClientVisibleProxyCount": c_state.get("clientVisibleProxyCount"),
        "singleTransitionCandidateCount": c_single.get("singleTransitionCandidateCount"),
        "hookAxisRecommendedAxisCount": c_hook_axis.get("recommendedAxisCount"),
        "hookAxisMissingObservedHookCount": c_hook_axis.get("missingObservedHookCount"),
        "hookAxisMissingContrastHookCount": c_hook_axis.get("missingContrastHookCount"),
        "hookAxisNotInstrumentedHookCount": c_hook_axis.get("notInstrumentedHookCount"),
        "successOnlyHookFeatureCandidateCount": c_reducer.get("successOnlyHookFeatureCandidateCount"),
        "promotedSingleTransitionCandidateCount": c_reducer.get("promotedSingleTransitionCandidateCount"),
        "allHookAxesClosed": c_reducer.get("allHookAxesClosed") is True,
        "runtimeJsTaxonomyCandidateCount": c_runtime_taxonomy.get("candidateClientVisibleProxyCount"),
        "runtimeJsTaxonomyStrongContrastCandidateCount": c_runtime_taxonomy.get("strongJsContrastCandidateCount"),
        "runtimeJsCandidateReductionPromotedCount": c_runtime_reduction.get("promotedSingleTransitionCandidateCount"),
        "runtimeJsCandidateReductionUnclassifiedCount": c_runtime_reduction.get("unclassifiedReductionCount"),
        "runtimeJsAllCandidatesReduced": c_runtime_reduction.get("allCandidatesReduced") is True,
        "collectorHandlerAuditExists": bool(handler_audit),
        "collectorHandlerCandidateCount": c_handler.get("handlerCandidateCount"),
        "collectorHandlerDistinctKeyCount": c_handler.get("distinctHandlerKeyCount"),
        "collectorHandlerPromotedCount": c_handler.get("promotedSingleTransitionCandidateCount"),
        "collectorHandlerUnclassifiedCount": c_handler.get("unclassifiedHandlerSurfaceCount"),
        "collectorHandlerNegativeControlsAllHold": c_handler.get("negativeControlsAllHold") is True,
        "collectorHandlerNotPromoted": c_handler.get("promotedSingleTransitionCandidateCount") == 0
        and c_handler.get("unclassifiedHandlerSurfaceCount") == 0,
        "unobservedLifecycleAuditExists": bool(lifecycle_audit),
        "unobservedLifecycleRecommendedNewHookCount": c_lifecycle.get("recommendedNewHookCount"),
        "unobservedLifecycleReadyForResampling": c_lifecycle.get("readyForResampling") is True,
        "unobservedLifecycleReadyForFreshExperiment": c_lifecycle.get("readyForFreshExperiment") is True,
        "routeBResamplingManifestExists": bool(route_b_manifest),
        "routeBControlledBrowserResamplingReady": c_route_b_manifest.get("readyForRouteBControlledBrowserResampling") is True,
        "routeBLifecycleContrastAuditExists": bool(route_b_contrast),
        "routeBLifecycleContrastRealAttemptCount": c_route_b_contrast.get("realAttemptCount"),
        "routeBLifecycleContrastSuccessOnlyHookKindCount": c_route_b_contrast.get("successOnlyHookKindCount"),
        "routeBLifecycleContrastPromotedCount": c_route_b_contrast.get("promotedSingleTransitionCandidateCount"),
        "routeBValueTaxonomyAuditExists": bool(route_b_value),
        "routeBValueTaxonomyPromotedCount": c_route_b_value.get("promotedSingleTransitionCandidateCount"),
        "routeBValueTaxonomyHsprotectValueContrastControlled": c_route_b_value.get("hsprotectValueContrastControlled") is True,
        "routeBInstrumentationControlAuditExists": bool(route_b_instr),
        "routeBInstrumentationPatchApply1SuccessCount": c_route_b_instr.get("patchApply1SuccessCount"),
        "routeBInstrumentationPatchApply1FailureCount": c_route_b_instr.get("patchApply1FailureCount"),
        "routeBInstrumentationValueContrastControlled": c_route_b_instr.get("valueContrastControlled") is True,
        "routeBInstrumentationPatchApplyPassiveObserver": c_route_b_instr.get("patchApplyCanBeTreatedAsPassiveObserver") is True,
        "oneCollectorSuccessSampleCount": c_onecollector.get("oneCollectorSuccessSampleCount"),
        "oneCollectorFailureSampleCount": c_onecollector.get("oneCollectorFailureSampleCount"),
        "oneCollectorAfterAcceptedChainCount": c_onecollector.get("oneCollectorAfterAcceptedChainCount"),
        "oneCollectorNotPromoted": c_onecollector.get("promoteToSingleTransitionCandidate") is False,
        "methodologicalTerminalAuditExists": bool(methodological_terminal),
        "methodologicalAllRoutesClosed": c_methodological.get("allRoutesClosed") is True,
        "methodologicalReadyForFreshExperiment": c_methodological.get("readyForFreshExperiment") is True,
        "methodologicalGoalComplete": c_methodological.get("goalComplete") is True,
        "nextEvidenceEntranceAuditExists": bool(next_entrance),
        "allKnownLocalEvidenceEntrancesClosed": c_next_entrance.get("allKnownLocalEvidenceEntrancesClosed") is True,
        "encoderVariantTerminalAuditExists": bool(encoder_variant_terminal),
        "encoderVariantFamilyClosedNoSuccess": c_encoder_terminal.get("encoderVariantFamilyClosedNoSuccess") is True,
        "encoderVariantTerminalPromotedCount": c_encoder_terminal.get("promotedSingleTransitionCandidateCount"),
        "encoderVariantTerminalReadyForFreshExperiment": c_encoder_terminal.get("readyForFreshExperiment") is True,
        "browserContextProxyAuditExists": bool(browser_context_proxy),
        "browserContextPreAcceptMessageCount": c_browser_context_proxy.get("preAcceptMessageCount"),
        "browserContextBlockValuesAlreadyRepresentedInRequest": c_browser_context_proxy.get("blockValuesAlreadyRepresentedInRequest") is True,
        "browserContextAllServerVisibleProxiesReduced": c_browser_context_proxy.get("allBrowserContextServerVisibleProxiesReduced") is True,
        "browserContextPromotedCount": c_browser_context_proxy.get("promotedSingleTransitionCandidateCount"),
        "browserContextReadyForFreshExperiment": c_browser_context_proxy.get("readyForFreshExperiment") is True,
        "browserContextStaticInventoryExists": bool(browser_context_static),
        "browserContextStaticAllGapsReduced": c_browser_context_static.get("allStaticContextGapsReduced") is True,
        "browserContextStaticPromotedCount": c_browser_context_static.get("promotedSingleTransitionCandidateCount"),
        "browserContextStaticReadyForFreshExperiment": c_browser_context_static.get("readyForFreshExperiment") is True,
        "postStaticContextTerminalAuditExists": bool(post_static_context_terminal),
        "postStaticContextAllClosedBranchesClosed": c_post_static_context_terminal.get("allClosedBranchesClosed") is True,
        "postStaticContextPromotedCount": c_post_static_context_terminal.get("promotedSingleTransitionCandidateCount"),
        "postStaticContextReadyForFreshExperiment": c_post_static_context_terminal.get("readyForFreshExperiment") is True,
        "currentRouteAuthorityAuditExists": bool(current_route_authority),
        "currentRouteAuthorityStaleReadyArtifactCount": c_current_route_authority.get("staleReadyArtifactCount"),
        "currentRouteAuthorityPromotedCount": c_current_route_authority.get("currentPromotedSingleTransitionCandidateCount"),
        "currentRouteAuthorityReadyForFreshExperiment": c_current_route_authority.get("readyForFreshExperiment") is True,
        "recursiveEvidenceBlindspotAuditExists": bool(recursive_blindspot),
        "recursiveEvidenceFileCount": c_recursive_blindspot.get("recursiveJsonFileCount"),
        "recursiveEvidenceUnclassifiedSuccessSignalCount": c_recursive_blindspot.get("unclassifiedRecursiveSuccessSignalCount"),
        "recursiveEvidenceReplayableFreshSuccessCount": c_recursive_blindspot.get("replayableFreshNoBrowserSuccessEvidenceCount"),
        "recursiveEvidenceReadyForFreshExperiment": c_recursive_blindspot.get("readyForFreshExperiment") is True,
        "nonJsonEvidenceBlindspotAuditExists": bool(non_json_blindspot),
        "nonJsonEvidenceScannedTextFileCount": c_non_json_blindspot.get("scannedTextFileCount"),
        "nonJsonEvidenceSuccessSignalFileCount": c_non_json_blindspot.get("successSignalFileCount"),
        "nonJsonEvidenceUnclassifiedSuccessSignalCount": c_non_json_blindspot.get("unclassifiedSuccessSignalCount"),
        "nonJsonEvidenceReplayableFreshSuccessCount": c_non_json_blindspot.get("replayableFreshNoBrowserSuccessEvidenceCount"),
        "nonJsonEvidenceReadyForFreshExperiment": c_non_json_blindspot.get("readyForFreshExperiment") is True,
        "proofScriptReproducibilityAuditExists": bool(proof_repro),
        "proofScriptTaskCount": c_proof_repro.get("taskCount"),
        "proofScriptPassedTaskCount": c_proof_repro.get("passedTaskCount"),
        "proofScriptFailedTaskCount": c_proof_repro.get("failedTaskCount"),
        "allProofScriptsReproducible": c_proof_repro.get("allProofScriptsReproducible") is True,
        "proofScriptReadyForFreshExperiment": c_proof_repro.get("readyForFreshExperiment") is True,
        "endToEndRemainingBoundaryAuditExists": bool(e2e_boundary),
        "endToEndEliminatedBoundaryCount": c_e2e_boundary.get("eliminatedBoundaryCount"),
        "endToEndRemainingBoundaryCount": c_e2e_boundary.get("remainingBoundaryCount"),
        "endToEndBoundaryPromotedCount": c_e2e_boundary.get("promotedSingleTransitionCandidateCount"),
        "endToEndBoundaryDecodedSeq5Seq6Rejected": c_e2e_boundary.get("decodedSeq5Seq6ActivityEqualityRejected") is True,
        "endToEndBoundaryFreshServerBoundTailRejected": c_e2e_boundary.get("freshServerBoundTailStrongestRejected") is True,
        "endToEndBoundaryExactPayloadPcAndExactBodyNoSuccess": c_e2e_boundary.get("exactPayloadPcAndExactBodyNoSuccess") is True,
        "endToEndBoundaryEncodedStillCoupled": c_e2e_boundary.get("encodedBoundaryStillCoupled") is True,
        "endToEndBoundaryReadyForFreshExperiment": c_e2e_boundary.get("readyForFreshExperiment") is True,
        "browserCookieBridgeCandidateAuditExists": bool(cookie_bridge_candidate),
        "browserCookieBridgeTimelineFileCount": c_cookie_bridge_candidate.get("timelineFileCount"),
        "browserCookieBridgeAlsoPresentInTfFailures": c_cookie_bridge_candidate.get("cookieBridgeCorrelationAlsoPresentInTfFailures") is True,
        "browserCookieBridgeTfFailuresNoParentSuccessCount": c_cookie_bridge_candidate.get("tfFailuresWithCookieBridgeNoParentSuccessCount"),
        "browserCookieBridgeParentSuccessCanExistWithoutDecodedSuccess0": c_cookie_bridge_candidate.get("parentChallengeSuccessCanExistWithoutDecodedSuccess0") is True,
        "browserCookieBridgePrimaryCollectorNoCookieHeader": c_cookie_bridge_candidate.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader") is True,
        "browserCookieBridgeHeadersOnlyBeaconOrTelemetry": c_cookie_bridge_candidate.get("collectorCookieHeadersOnlyOnBeaconOrTelemetry") is True,
        "browserCookieBridgePromotedCount": c_cookie_bridge_candidate.get("promotedSingleTransitionCandidateCount"),
        "browserCookieBridgeReadyForFreshExperiment": c_cookie_bridge_candidate.get("readyForFreshExperiment") is True,
        "encodedSessionBindingCandidateAuditExists": bool(encoded_session_candidate),
        "encodedSessionSingleAxisRowCount": c_encoded_session_candidate.get("singleAxisRowCount"),
        "encodedSessionSingleAxisEliminatedCount": c_encoded_session_candidate.get("singleAxisEliminatedCount"),
        "encodedSessionExactPayloadPcNoSuccess": c_encoded_session_candidate.get("exactPayloadPcNoSuccess") is True,
        "encodedSessionExactBodyNoSuccess": c_encoded_session_candidate.get("exactBodyNoSuccess") is True,
        "encodedSessionPcAloneEliminated": c_encoded_session_candidate.get("pcAloneEliminated") is True,
        "encodedSessionMarkerChoiceEliminated": c_encoded_session_candidate.get("markerChoiceEliminated") is True,
        "encodedSessionTemplateOuterFreshPayloadPcNoSuccess": c_encoded_session_candidate.get("templateOuterFreshPayloadPcNoSuccess") is True,
        "encodedSessionForcedOverlapExactPayloadPcNoSuccess": c_encoded_session_candidate.get("forcedOverlapExactPayloadPcNoSuccess") is True,
        "encodedSessionDecodedEqualButBoundaryRemains": c_encoded_session_candidate.get("decodedEqualButEncodedBoundaryRemains") is True,
        "encodedSessionRemainingDiffKeysArePayloadPcSession": c_encoded_session_candidate.get("remainingDiffKeysArePayloadPcSession") is True,
        "encodedSessionPromotedCount": c_encoded_session_candidate.get("promotedSingleTransitionCandidateCount"),
        "encodedSessionReadyForFreshExperiment": c_encoded_session_candidate.get("readyForFreshExperiment") is True,
        "collectorServerExpectedStateBoundaryAuditExists": bool(collector_server_expected),
        "collectorServerExpectedStateClientVisibleProxyFoundCount": c_collector_server_expected.get("clientVisibleProxyFoundCount"),
        "collectorServerExpectedStateRequestMirroredStateCount": c_collector_server_expected.get("requestMirroredStateCount"),
        "collectorServerExpectedStateCookieMirroredStateCount": c_collector_server_expected.get("cookieMirroredStateCount"),
        "collectorServerExpectedStateRiskVerifyMirroredStateCount": c_collector_server_expected.get("riskVerifyMirroredStateCount"),
        "collectorServerExpectedStateUnobservableServerStateCount": c_collector_server_expected.get("unobservableServerStateCount"),
        "collectorServerExpectedStateNotClientVisible": c_collector_server_expected.get("serverStateBoundaryNotClientVisible") is True,
        "collectorServerExpectedStatePromotedCount": c_collector_server_expected.get("promotedSingleTransitionCandidateCount"),
        "collectorServerExpectedStateReadyForFreshExperiment": c_collector_server_expected.get("readyForFreshExperiment") is True,
        "candidateIntakeAuditExists": bool(candidate_intake),
        "candidateIntakeCandidateSourceCount": c_candidate_intake.get("candidateSourceCount"),
        "candidateIntakeProposalCount": c_candidate_intake.get("proposalCount"),
        "candidateIntakeProposalAcceptedCount": c_candidate_intake.get("proposalAcceptedCount"),
        "candidateIntakeProposalInvalidCount": c_candidate_intake.get("proposalInvalidCount"),
        "candidateIntakeProposalLintExists": c_candidate_intake.get("proposalLintExists") is True,
        "candidateIntakeProposalLintAllStructurallyValid": c_candidate_intake.get("proposalLintAllStructurallyValid") is True,
        "candidateIntakeProposalLintPromotableShapeCount": c_candidate_intake.get("proposalLintPromotableShapeCount"),
        "candidateProposalLintControlsExists": bool(proposal_lint_controls),
        "candidateProposalLintControlsAllPassed": c_proposal_lint_controls.get("allControlsPassed") is True,
        "candidateProposalLintControlsPassedCount": c_proposal_lint_controls.get("passedControlCount"),
        "candidateProposalLintControlsFailedCount": c_proposal_lint_controls.get("failedControlCount"),
        "candidateIntakeCandidateCount": c_candidate_intake.get("candidateCount"),
        "candidateIntakePromotedCount": c_candidate_intake.get("promotedSingleTransitionCandidateCount"),
        "candidateIntakePreAcceptCandidateCount": c_candidate_intake.get("preAcceptCandidateCount"),
        "candidateIntakeClientVisibleCandidateCount": c_candidate_intake.get("clientVisibleCandidateCount"),
        "candidateIntakePureProtocolConstructibleCandidateCount": c_candidate_intake.get("pureProtocolConstructibleCandidateCount"),
        "candidateIntakeNegativeControlContradictedCandidateCount": c_candidate_intake.get("negativeControlContradictedCandidateCount"),
        "candidateIntakeReadyForFreshExperiment": c_candidate_intake.get("readyForFreshExperiment") is True,
        "phase3ProposalEvidenceTriageExists": bool(phase3_triage),
        "phase3ProposalWorthyEvidenceCount": c_phase3_triage.get("proposalWorthyEvidenceCount"),
        "phase3RecursiveReadyOrPromotedSignalCount": c_phase3_triage.get("recursiveJsonReadyOrPromotedSignalCount"),
        "phase3ReadyForFreshExperiment": c_phase3_triage.get("readyForFreshExperiment") is True,
        "phase3EvidenceEntranceCoverageExists": bool(phase3_entrance),
        "phase3UncoveredEntranceRowCount": c_phase3_entrance.get("uncoveredEntranceRowCount"),
        "phase3ProposalEntranceExhaustedForCurrentEvidence": c_phase3_entrance.get("proposalEntranceExhaustedForCurrentEvidence") is True,
        "phase3RawEvidenceEntranceExists": bool(phase3_raw),
        "phase3RawSuccessSignalFileCount": c_phase3_raw.get("rawSuccessSignalFileCount"),
        "phase3RawUnindexedBrowserTraceSignalCount": c_phase3_raw.get("unindexedBrowserTraceSignalCount"),
        "phase3RawProposalWorthySignalCount": c_phase3_raw.get("proposalWorthyRawSignalCount"),
        "phase3RawTraceCrosswalkExists": bool(phase3_crosswalk),
        "phase3RawTraceCrosswalkUnreferencedCount": c_phase3_crosswalk.get("unreferencedTraceCount"),
        "phase3RawTraceCrosswalkProposalWorthyCount": c_phase3_crosswalk.get("proposalWorthyRawTraceCount"),
        "traceClassifierRawCoverageGapExists": bool(trace_classifier_gap),
        "traceClassifierRawBrowserSuccessRunsNotInClassifierCount": c_trace_classifier_gap.get("rawBrowserSuccessRunsNotInClassifierCount"),
        "traceClassifierReferencedButUnclassifiedRawTraceCount": c_trace_classifier_gap.get("referencedButUnclassifiedRawTraceCount"),
        "traceClassifierSafeToAutoAppend": c_trace_classifier_gap.get("safeToAutoAppendToClassifier") is True,
        "traceClassifierProposalWorthyCoverageGapCount": c_trace_classifier_gap.get("proposalWorthyCoverageGapCount"),
        "remainingBoundaryProposalGateExists": bool(remaining_boundary_gate),
        "remainingBoundaryProposalGateRowCount": c_remaining_boundary_gate.get("proposalGateRowCount"),
        "remainingBoundaryProposalReadyRowCount": c_remaining_boundary_gate.get("proposalReadyRowCount"),
        "remainingBoundaryProposalReadyForFreshExperiment": c_remaining_boundary_gate.get("readyForFreshExperiment") is True,
        "candidateSourceContradictionLedgerExists": bool(candidate_source_ledger),
        "candidateSourceContradictionLedgerIntakeRowCount": c_candidate_source_ledger.get("intakeRowCount"),
        "candidateSourceContradictionLedgerGateRowCount": c_candidate_source_ledger.get("gateRowCount"),
        "candidateSourceContradictionLedgerMatrixRowCount": c_candidate_source_ledger.get("matrixRowCount"),
        "candidateSourceContradictionLedgerPromotedTotal": c_candidate_source_ledger.get("promotedCandidateTotal"),
        "candidateSourceContradictionLedgerAllSourcesClosed": c_candidate_source_ledger.get("allCandidateSourcesClosed") is True,
        "candidateSourceContradictionLedgerReadyForFreshExperiment": c_candidate_source_ledger.get("readyForFreshExperiment") is True,
        "serverStateValueConsumptionLedgerExists": bool(server_state_value_consumption),
        "serverStateValueConsumptionLedgerValueComparisonCount": c_server_state_value_consumption.get("valueComparisonCount"),
        "serverStateValueConsumptionLedgerConsumedValueCount": c_server_state_value_consumption.get("consumedValueCount"),
        "serverStateValueConsumptionLedgerAllRowsCovered": c_server_state_value_consumption.get("allRowsCoveredByControlOrCoupling") is True,
        "serverStateValueConsumptionLedgerSingleValueProposalReadyCount": c_server_state_value_consumption.get("singleValueProposalReadyCount"),
        "serverStateValueConsumptionLedgerReadyForFreshExperiment": c_server_state_value_consumption.get("readyForFreshExperiment") is True,
        "coupledBoundaryTerminalLedgerExists": bool(coupled_boundary_terminal),
        "coupledBoundaryTerminalLedgerRowCount": c_coupled_boundary_terminal.get("coupledBoundaryRowCount"),
        "coupledBoundaryTerminalLedgerProposalReadyRowCount": c_coupled_boundary_terminal.get("proposalReadyRowCount"),
        "coupledBoundaryTerminalLedgerAllClosed": c_coupled_boundary_terminal.get("allCoupledBoundariesClosedForCurrentEvidence") is True,
        "coupledBoundaryTerminalLedgerReadyForFreshExperiment": c_coupled_boundary_terminal.get("readyForFreshExperiment") is True,
        "currentEvidenceEntranceTerminalLedgerExists": bool(current_evidence_entrance_terminal),
        "currentEvidenceEntranceTerminalLedgerNextPointerCount": c_current_evidence_entrance_terminal.get("nextPointerCount"),
        "currentEvidenceEntranceTerminalLedgerUnresolvedNextPointerCount": c_current_evidence_entrance_terminal.get("unresolvedNextPointerCount"),
        "currentEvidenceEntranceTerminalLedgerActiveActionableNextPointerCount": c_current_evidence_entrance_terminal.get("activeActionableNextPointerCount"),
        "currentEvidenceEntranceTerminalLedgerAllClosedOrSuperseded": c_current_evidence_entrance_terminal.get("allNextPointersClosedOrSuperseded") is True,
        "currentEvidenceEntranceTerminalLedgerReadyForFreshExperiment": c_current_evidence_entrance_terminal.get("readyForFreshExperiment") is True,
        "convergentEvidenceEntranceMatrixExists": bool(convergent_evidence_entrance_matrix),
        "convergentEvidenceEntranceMatrixEntranceCount": c_convergent_evidence_entrance_matrix.get("entranceCount"),
        "convergentEvidenceEntranceMatrixClosedEntranceCount": c_convergent_evidence_entrance_matrix.get("closedEntranceCount"),
        "convergentEvidenceEntranceMatrixCandidateAffectingEntranceCount": c_convergent_evidence_entrance_matrix.get("candidateAffectingEntranceCount"),
        "convergentEvidenceEntranceMatrixUncoveredCandidateAffectingEntranceCount": c_convergent_evidence_entrance_matrix.get("uncoveredCandidateAffectingEntranceCount"),
        "convergentEvidenceEntranceMatrixRecommendedNextEntranceCount": c_convergent_evidence_entrance_matrix.get("recommendedNextEntranceCount"),
        "convergentEvidenceEntranceMatrixReadyForFreshExperiment": c_convergent_evidence_entrance_matrix.get("readyForFreshExperiment") is True,
        "manifestCoverageGapExists": bool(manifest_coverage_gap),
        "manifestCoverageGapScannedFileCount": c_manifest_coverage_gap.get("scannedFileCount"),
        "manifestCoverageGapUnmanifestedFileCount": c_manifest_coverage_gap.get("unmanifestedFileCount"),
        "manifestCoverageGapHighValueUncoveredDirectoryCount": c_manifest_coverage_gap.get("highValueUncoveredDirectoryCount"),
        "manifestCoverageGapProposalWorthyUnmanifestedDirectoryCount": c_manifest_coverage_gap.get("proposalWorthyUnmanifestedDirectoryCount"),
        "manifestCoverageGapConvergentRecommendedNextEntranceCount": c_manifest_coverage_gap.get("convergentRecommendedNextEntranceCount"),
        "manifestCoverageGapReadyForFreshExperiment": c_manifest_coverage_gap.get("readyForFreshExperiment") is True,
        "liveRunnerGateExists": bool(live_runner_gate),
        "liveRunnerGateAuthoritativeHarnessCount": c_live_runner_gate.get("authoritativeHarnessCount"),
        "liveRunnerGateAuthoritativeHarnessBlockedCount": c_live_runner_gate.get("authoritativeHarnessBlockedCount"),
        "liveRunnerGateProofInvokedUngatedLiveRunnerCount": c_live_runner_gate.get("proofInvokedUngatedLiveRunnerCount"),
        "liveRunnerGateGateChainInvokedUngatedLiveRunnerCount": c_live_runner_gate.get("gateChainInvokedUngatedLiveRunnerCount"),
        "liveRunnerGateCurrentNetworkAttemptBlocked": c_live_runner_gate.get("currentNetworkAttemptBlocked") is True,
        "liveRunnerGateReadyForFreshExperiment": c_live_runner_gate.get("readyForFreshExperiment") is True,
        "objectiveRequirementCrosswalkExists": bool(objective_crosswalk),
        "objectiveRequirementCrosswalkRequirementCount": c_objective_crosswalk.get("requirementCount"),
        "objectiveRequirementCrosswalkProvenCount": c_objective_crosswalk.get("provenCount"),
        "objectiveRequirementCrosswalkBlockingRequirementCount": c_objective_crosswalk.get("blockingRequirementCount"),
        "objectiveRequirementCrosswalkEndToEndPocMissing": c_objective_crosswalk.get("endToEndPocMissing") is True,
        "objectiveRequirementCrosswalkFullNoBrowserIndependenceNotProven": c_objective_crosswalk.get("fullNoBrowserIndependenceNotProven") is True,
        "objectiveRequirementCrosswalkTraceabilityOnlyPartiallyProven": c_objective_crosswalk.get("traceabilityOnlyPartiallyProven") is True,
        "objectiveRequirementCrosswalkReadyForFreshExperiment": c_objective_crosswalk.get("readyForFreshExperiment") is True,
        "objectiveRequirementCrosswalkGoalComplete": c_objective_crosswalk.get("goalComplete") is True,
        "promotionPredicateBlockerCrosswalkExists": bool(promotion_blocker),
        "promotionPredicateBlockerPredicateCount": c_promotion_blocker.get("predicateCount"),
        "promotionPredicateBlockerUnsatisfiedPromotionPredicateCount": c_promotion_blocker.get("unsatisfiedPromotionPredicateCount"),
        "promotionPredicateBlockerArtifactBackedNegativeDecision": c_promotion_blocker.get("artifactBackedNegativeDecision") is True,
        "promotionPredicateBlockerStaleAuthorityCleanForNegativeDecision": c_promotion_blocker.get("staleAuthorityCleanForNegativeDecision") is True,
        "promotionPredicateBlockerCandidateIntakePromotedCount": c_promotion_blocker.get("candidateIntakePromotedCount"),
        "promotionPredicateBlockerRemainingBoundaryProposalReadyRowCount": c_promotion_blocker.get("remainingBoundaryProposalReadyRowCount"),
        "promotionPredicateBlockerReadyForFreshExperiment": c_promotion_blocker.get("readyForFreshExperiment") is True,
        "candidateExecutorReadinessExists": bool(candidate_executor_readiness),
        "candidateExecutorPlanRequiresCandidateSpecificExecutor": c_candidate_executor.get("planRequiresCandidateSpecificExecutor") is True,
        "candidateExecutorHarnessDeclaresMissingCandidateSpecificExecutor": c_candidate_executor.get("harnessDeclaresMissingCandidateSpecificExecutor") is True,
        "candidateExecutorCurrentGateClosedNoNetworkAttempt": c_candidate_executor.get("currentGateClosedNoNetworkAttempt") is True,
        "candidateExecutorReadyForPromotedCandidate": c_candidate_executor.get("executorReadyForPromotedCandidate") is True,
        "candidateExecutorReadyForFreshExperiment": c_candidate_executor.get("readyForFreshExperiment") is True,
        "hypothesisTreeCurrentAuthorityExists": bool(hypothesis_tree_authority),
        "hypothesisTreeH3Terminal": c_hypothesis_tree_authority.get("h3CollectorServerStateTerminalForCurrentEvidence") is True,
        "hypothesisTreeH4Terminal": c_hypothesis_tree_authority.get("h4BrowserOnlyRuntimeTerminalForCurrentEvidence") is True,
        "hypothesisTreeH5NotCurrentEntrance": c_hypothesis_tree_authority.get("h5MicrosoftContextNotCurrentEntrance") is True,
        "hypothesisTreeOldPlanNoLongerAuthorizesPhase5": c_hypothesis_tree_authority.get("oldPlanNoLongerAuthorizesPhase5") is True,
        "hypothesisTreeConvergentPlanIsCurrentAuthority": c_hypothesis_tree_authority.get("convergentPlanIsCurrentAuthority") is True,
        "hypothesisTreeReadyForFreshExperiment": c_hypothesis_tree_authority.get("readyForFreshExperiment") is True,
        "nearestMissPromotionCandidateExists": bool(nearest_miss_promotion),
        "nearestMissCandidateRowCount": c_nearest_miss.get("candidateRowCount"),
        "nearestMissNearestSatisfiedPredicateCount": c_nearest_miss.get("nearestSatisfiedPredicateCount"),
        "nearestMissNearestMissingPredicateCount": c_nearest_miss.get("nearestMissingPredicateCount"),
        "nearestMissProposalReadyCandidateCount": c_nearest_miss.get("proposalReadyCandidateCount"),
        "nearestMissSingleMissingPredicateCandidateCount": c_nearest_miss.get("singleMissingPredicateCandidateCount"),
        "nearestMissCandidateWithSingleTransitionCount": c_nearest_miss.get("candidateWithSingleTransitionCount"),
        "nearestMissReadyForFreshExperiment": c_nearest_miss.get("readyForFreshExperiment") is True,
        "nearestMissBlockerResolutionExists": bool(nearest_miss_blocker),
        "nearestMissBlockerClosedByExistingControlsCount": c_nearest_miss_blocker.get("closedByExistingControlsCount"),
        "nearestMissBlockerNeedsMoreEvidenceCount": c_nearest_miss_blocker.get("needsMoreEvidenceCount"),
        "nearestMissBlockerPcValueClosed": c_nearest_miss_blocker.get("pcValueClosedByExistingControls") is True,
        "nearestMissBlockerCollectorCookieHeaderClosed": c_nearest_miss_blocker.get("collectorCookieHeaderClosedByExistingControls") is True,
        "nearestMissBlockerProposalReadyCandidateCount": c_nearest_miss_blocker.get("proposalReadyCandidateCount"),
        "nearestMissBlockerReadyForFreshExperiment": c_nearest_miss_blocker.get("readyForFreshExperiment") is True,
        "remainingNearestMissResolutionExists": bool(remaining_nearest_miss),
        "remainingNearestMissRowCount": c_remaining_nearest.get("remainingNearestRowCount"),
        "remainingNearestMissClosedByExistingControlsCount": c_remaining_nearest.get("closedByExistingControlsCount"),
        "remainingNearestMissOpenRowCount": c_remaining_nearest.get("openRemainingNearestRowCount"),
        "remainingNearestMissProposalReadyCandidateCount": c_remaining_nearest.get("proposalReadyCandidateCount"),
        "remainingNearestMissReadyForFreshExperiment": c_remaining_nearest.get("readyForFreshExperiment") is True,
        "exhaustivePromotionCandidateResolutionExists": bool(exhaustive_candidate_resolution),
        "exhaustiveCandidateRowCount": c_exhaustive_candidate.get("candidateRowCount"),
        "exhaustiveResolvedCandidateCount": c_exhaustive_candidate.get("resolvedCandidateCount"),
        "exhaustiveClosedByExistingControlsCount": c_exhaustive_candidate.get("closedByExistingControlsCount"),
        "exhaustiveOpenNeedsSpecificEvidenceCount": c_exhaustive_candidate.get("openNeedsSpecificEvidenceCount"),
        "exhaustiveProposalReadyCandidateCount": c_exhaustive_candidate.get("proposalReadyCandidateCount"),
        "exhaustiveReadyForFreshExperiment": c_exhaustive_candidate.get("readyForFreshExperiment") is True,
        "nextEvidenceSurfaceDiscoveryExists": bool(next_evidence_surface),
        "nextEvidenceSurfaceCount": c_next_surface.get("surfaceCount"),
        "nextEvidenceClosedSurfaceCount": c_next_surface.get("closedSurfaceCount"),
        "nextEvidenceOpenSurfaceCount": c_next_surface.get("openSurfaceCount"),
        "nextEvidenceNewCandidateSurfaceCount": c_next_surface.get("newCandidateSurfaceCount"),
        "nextEvidenceSurfaceWithNewCandidateCount": c_next_surface.get("surfaceWithNewCandidateCount"),
        "nextEvidenceReadyForFreshExperiment": c_next_surface.get("readyForFreshExperiment") is True,
        "externalOutputSurfaceAuditExists": bool(external_output_surface),
        "externalOutputSurfaceAuditSignalFileCount": c_external_output_surface.get("signalFileCount"),
        "externalOutputSurfaceAuditCollectorSuccess0SignalFileCount": c_external_output_surface.get("collectorSuccess0SignalFileCount"),
        "externalOutputSurfaceAuditProposalWorthySignalCount": c_external_output_surface.get("proposalWorthyExternalSignalCount"),
        "externalOutputSurfaceAuditReadyForFreshExperiment": c_external_output_surface.get("readyForFreshExperiment") is True,
        "evidencePackageSurfaceAuditExists": bool(evidence_package_surface),
        "evidencePackageSurfaceAuditSignalFileCount": c_evidence_package_surface.get("signalFileCount"),
        "evidencePackageSurfaceAuditCollectorSuccess0SignalFileCount": c_evidence_package_surface.get("collectorSuccess0SignalFileCount"),
        "evidencePackageSurfaceAuditProposalWorthySignalCount": c_evidence_package_surface.get("proposalWorthyEvidencePackageSignalCount"),
        "evidencePackageSurfaceAuditReadyForFreshExperiment": c_evidence_package_surface.get("readyForFreshExperiment") is True,
        "ctfRegOutputSurfaceAuditExists": bool(ctf_reg_output_surface),
        "ctfRegOutputSurfaceAuditSignalFileCount": c_ctf_reg_output_surface.get("signalFileCount"),
        "ctfRegOutputSurfaceAuditCollectorSuccess0SignalFileCount": c_ctf_reg_output_surface.get("collectorSuccess0SignalFileCount"),
        "ctfRegOutputSurfaceAuditProposalWorthySignalCount": c_ctf_reg_output_surface.get("proposalWorthyCtfRegSignalCount"),
        "ctfRegOutputSurfaceAuditReadyForFreshExperiment": c_ctf_reg_output_surface.get("readyForFreshExperiment") is True,
        "auxiliaryTraceSurfaceAuditExists": bool(auxiliary_trace_surface),
        "auxiliaryTraceSurfaceAuditSignalFileCount": c_auxiliary_trace_surface.get("signalFileCount"),
        "auxiliaryTraceSurfaceAuditCollectorSuccess0SignalFileCount": c_auxiliary_trace_surface.get("collectorSuccess0SignalFileCount"),
        "auxiliaryTraceSurfaceAuditProposalWorthySignalCount": c_auxiliary_trace_surface.get("proposalWorthyAuxiliarySignalCount"),
        "auxiliaryTraceSurfaceAuditReadyForFreshExperiment": c_auxiliary_trace_surface.get("readyForFreshExperiment") is True,
        "stalePositiveSignalAuthorityExists": bool(stale_positive_signal_authority),
        "stalePositiveSignalAuthorityPositiveSignalCount": c_stale_positive_signal_authority.get("positiveSignalCount"),
        "stalePositiveSignalAuthorityActiveActionablePositiveSignalCount": c_stale_positive_signal_authority.get("activeActionablePositiveSignalCount"),
        "stalePositiveSignalAuthorityCandidateIntakePromotedCount": c_stale_positive_signal_authority.get("candidateIntakePromotedCount"),
        "stalePositiveSignalAuthorityReadyForFreshExperiment": c_stale_positive_signal_authority.get("readyForFreshExperiment") is True,
        "localTraceEvidenceFreshnessExists": bool(local_trace_freshness),
        "localTraceUnclassifiedHighValueSignalRunCount": c_local_trace_freshness.get("unclassifiedHighValueSignalRunCount"),
        "localTraceProposalWorthyNowCount": c_local_trace_freshness.get("proposalWorthyNowCount"),
        "unclassifiedTraceSignalReductionExists": bool(unclassified_trace_reduction),
        "unclassifiedTraceBrowserSuccessChainRunCount": c_unclassified_trace_reduction.get("browserSuccessChainRunCount"),
        "unclassifiedTraceProposalReadyRunCount": c_unclassified_trace_reduction.get("proposalReadyRunCount"),
        "browserSuccessChainClassificationBacklogExists": bool(browser_success_backlog),
        "browserSuccessChainClassificationBacklogCount": c_browser_success_backlog.get("classificationBacklogCount"),
        "browserSuccessChainClassificationBacklogNoBrowserEvidenceCount": c_browser_success_backlog.get("noBrowserEvidenceCount"),
        "browserSuccessChainClassificationBacklogProposalReadyRunCount": c_browser_success_backlog.get("proposalReadyRunCount"),
        "browserSuccessChainClassificationBacklogSafeToPromoteToClassifier": c_browser_success_backlog.get("safeToPromoteToClassifier") is True,
        "browserSuccessChainServerVisibleDiffExists": bool(browser_success_diff),
        "browserSuccessChainServerVisibleDiffCount": c_browser_success_diff.get("earliestServerVisibleDiffCount"),
        "browserSuccessChainServerVisibleSingleFieldCandidateCount": c_browser_success_diff.get("singleFieldDiffCandidateCount"),
        "browserSuccessChainServerVisibleContradictedDiffCount": c_browser_success_diff.get("contradictedDiffCount"),
        "browserSuccessChainServerVisibleProposalCandidateCount": c_browser_success_diff.get("proposalCandidateCount"),
        "browserSuccessPayloadPcSessionLineageExists": bool(payload_pc_session_lineage),
        "browserSuccessPayloadPcSessionLineageRowCount": c_payload_pc_session_lineage.get("fieldLineageRowCount"),
        "browserSuccessPayloadPcSessionLineageContradictedCount": c_payload_pc_session_lineage.get("fieldLineageContradictedCount"),
        "browserSuccessPayloadPcSessionLineageProposalCandidateCount": c_payload_pc_session_lineage.get("proposalCandidateCount"),
        "collectorResponseHandlerValueLineageExists": bool(collector_handler_value_lineage),
        "collectorResponseHandlerValueLineageDecodedRunCount": c_collector_handler_value_lineage.get("decodedRunCount"),
        "collectorResponseHandlerValueLineageProposalCandidateCount": c_collector_handler_value_lineage.get("proposalCandidateCount"),
        "collectorResponseHandlerValueLineageCookieFailureStillMutates": c_collector_handler_value_lineage.get("cookieMutationFailureStillMutates") is True,
        "downstreamSuccessWithoutCollectorDecodeExists": bool(downstream_without_collector),
        "downstreamSuccessWithoutCollectorDecodeRunCount": c_downstream_without_collector.get("downstreamClassRunCount"),
        "downstreamSuccessWithoutCollectorDecodeSuccessRunCount": c_downstream_without_collector.get("downstreamSuccessRunCount"),
        "downstreamSuccessWithoutCollectorDecodeCollectorSuccessCount": c_downstream_without_collector.get("collectorSuccessDecodeRunCount"),
        "downstreamSuccessWithoutCollectorDecodeAllLackCollectorSuccess": c_downstream_without_collector.get("allDownstreamRowsLackCollectorSuccessDecode") is True,
        "downstreamSuccessWithoutCollectorDecodeProposalCandidateCount": c_downstream_without_collector.get("proposalCandidateCount"),
        "collectorMaterialOnlyResponseClassExists": bool(collector_material_only_response),
        "collectorMaterialOnlyResponseClassRunCount": c_collector_material_only_response.get("collectorMaterialOnlyRunCount"),
        "collectorMaterialOnlyResponseClassCollectorSuccessCount": c_collector_material_only_response.get("collectorSuccessDecodeRunCount"),
        "collectorMaterialOnlyResponseClassRiskContinueCount": c_collector_material_only_response.get("riskContinueRunCount"),
        "collectorMaterialOnlyResponseClassCreateRedirectCount": c_collector_material_only_response.get("createRedirectRunCount"),
        "collectorMaterialOnlyResponseClassProposalCandidateCount": c_collector_material_only_response.get("proposalCandidateCount"),
        "lowValueUnclassifiedTraceClosureExists": bool(low_value_closure),
        "lowValueUnclassifiedTraceClosureRunCount": c_low_value_closure.get("lowValueRunCount"),
        "lowValueUnclassifiedTraceClosureProposalRelevantCount": c_low_value_closure.get("rescannedProposalRelevantSignalRunCount"),
        "lowValueUnclassifiedTraceClosureAllRemainLowValue": c_low_value_closure.get("allRowsRemainLowValue") is True,
        "lowValueUnclassifiedTraceClosureProposalCandidateCount": c_low_value_closure.get("proposalCandidateCount"),
        "unclassifiedTraceClassClosureLedgerExists": bool(trace_class_ledger),
        "unclassifiedTraceClassClosureLedgerRunCount": c_trace_class_ledger.get("ledgerRunCount"),
        "unclassifiedTraceClassClosureLedgerAllClosed": c_trace_class_ledger.get("allTraceClassesClosed") is True,
        "unclassifiedTraceClassClosureLedgerProposalCandidateTotal": c_trace_class_ledger.get("proposalCandidateTotal"),
        "hypothesisPlanCoverageAuditExists": bool(hypothesis_plan_coverage),
        "hypothesisPlanExistingPhaseArtifactCount": c_hypothesis_plan_coverage.get("existingPhaseArtifactCount"),
        "hypothesisPlanMissingRequiredPhaseArtifactCount": c_hypothesis_plan_coverage.get("missingRequiredPhaseArtifactCount"),
        "hypothesisPlanMinimalExperimentMissingAllowedByGate": c_hypothesis_plan_coverage.get("minimalExperimentMissingAllowedByGate") is True,
        "hypothesisPlanStaleHistoricalNextPointerCount": c_hypothesis_plan_coverage.get("staleHistoricalNextPointerCount"),
        "hypothesisPlanAllHypothesesCovered": c_hypothesis_plan_coverage.get("allHypothesesCovered") is True,
        "hypothesisPlanH3RemainingNotClientVisible": c_hypothesis_plan_coverage.get("h3RemainingNotClientVisible") is True,
        "hypothesisPlanPromotedCount": c_hypothesis_plan_coverage.get("currentPromotedSingleTransitionCandidateCount"),
        "hypothesisPlanReadyForFreshExperiment": c_hypothesis_plan_coverage.get("readyForFreshExperiment") is True,
        "completionRequirementsAuditExists": bool(completion_requirements),
        "completionRequirementCount": c_completion_requirements.get("requirementCount"),
        "completionBlockingRequirementCount": c_completion_requirements.get("blockingRequirementCount"),
        "completionFreshSuccessMissing": c_completion_requirements.get("freshSuccessMissing") is True,
        "completionNoCurrentExperimentRoute": c_completion_requirements.get("noCurrentExperimentRoute") is True,
        "completionAllProofScriptsReproducible": c_completion_requirements.get("allProofScriptsReproducible") is True,
        "completionReadyForFreshExperiment": c_completion_requirements.get("readyForFreshExperiment") is True,
        "completionGoalComplete": c_completion_requirements.get("goalComplete") is True,
        "minimalTransitionExperimentExists": bool(minimal_transition_experiment),
        "minimalTransitionExperimentGateEvaluated": c_minimal_transition_experiment.get("gateEvaluated") is True,
        "minimalTransitionExperimentBlockedByGate": c_minimal_transition_experiment.get("blockedByGate") is True,
        "minimalTransitionExperimentNetworkAttemptExecuted": c_minimal_transition_experiment.get("networkAttemptExecuted") is True,
        "minimalTransitionExperimentStageAdvanced": c_minimal_transition_experiment.get("stageAdvanced") is True,
        "minimalTransitionExperimentReadyForFreshExperiment": c_minimal_transition_experiment.get("readyForFreshExperiment") is True,
        "minimalTransitionExperimentGoalComplete": c_minimal_transition_experiment.get("goalComplete") is True,
        "allFinalResponsesSameClass": c_final.get("allFinalResponsesSameClass") is True,
        "allFinalResponsesAreSeq5Minus1": c_final.get("allFinalResponsesAreSeq5Minus1") is True,
        "anySeq5Success0": c_final.get("anySeq5Success0") is True,
        "decodedFailureStillMutatesPx3Pxde": c_cookie.get("allOfflineJarHasPx3Pxde") is True,
        "decodedFailureHasNoSuccess0": c_cookie.get("anySuccess0") is False,
        "transportAuditExists": bool(transport),
        "transportDecisionAuditExists": bool(transport_decision),
        "transportDecisionOnlyTransportChangedStageDifferenceProved": c_transport_decision.get("onlyTransportChangedStageDifferenceProved") is True,
        "transportDecisionPromotedToControlVariableOnly": c_transport_decision.get("ipOrTransportPromotedToControlVariableOnly") is True,
        "webshareProxyAuthAuditExists": bool(proxy_auth),
        "legacyAllLocalProxySearchesNegative": c_legacy_gap.get("allLocalProxySearchesNegative") is True,
        "legacyActionableFrontierNotFound": c_legacy_frontier.get("actionableMissingArtifactCount") == 0,
        "legacyUnminedCoveredDirectoryCount": c_legacy_unmined.get("coveredDirectoryCount"),
        "legacyUnminedSuccessSignalFileCount": c_legacy_unmined.get("unminedSuccessSignalFileCount"),
        "legacyHighValueUnminedUnclassifiedSuccessSignalCount": c_legacy_triage.get("unclassifiedSuccessSignalCount"),
        "legacyHighValueUnminedReplayableSuccessNotFound": c_legacy_triage.get("hasReplayableFreshNoBrowserSuccessEvidence") is False,
        "evidenceGatedPocExists": bool(evidence_gated_poc),
        "evidenceGatedPocBlockedByGate": c_evidence_gated_poc.get("blockedByGate") is True,
        "evidenceGatedPocNetworkAttemptExecuted": c_evidence_gated_poc.get("networkAttemptExecuted") is True,
        "evidenceGatedPocFreshCollectorSuccess": c_evidence_gated_poc.get("freshNoBrowserCollectorSuccess") is True,
        "evidenceGatedPocFreshDecodedOIIoIooo0": c_evidence_gated_poc.get("freshDecodedOIIoIooo0") is True,
        "evidenceGatedPocFreshRiskVerifyContinue": c_evidence_gated_poc.get("freshRiskVerifyContinue") is True,
        "evidenceGatedPocFreshCreateAccountRedirectUrl": c_evidence_gated_poc.get("freshCreateAccountRedirectUrl") is True,
        "evidenceGatedPocReadyForFreshExperiment": c_evidence_gated_poc.get("readyForFreshExperiment") is True,
        "evidenceGatedPocGoalComplete": c_evidence_gated_poc.get("goalComplete") is True,
        "finalReplayAuditExists": bool(final_replay),
        "finalReplayGateEvaluated": c_final_replay.get("gateEvaluated") is True,
        "finalReplayBlockedByGate": c_final_replay.get("blockedByGate") is True,
        "finalReplayReadyForFreshReplay": c_final_replay.get("readyForFreshReplay") is True,
        "finalReplayAttemptExecuted": c_final_replay.get("replayAttemptExecuted") is True,
        "finalReplayNetworkAttemptExecuted": c_final_replay.get("networkAttemptExecuted") is True,
        "finalReplayPocFreshNoBrowserCollectorSuccess": c_final_replay.get("pocFreshNoBrowserCollectorSuccess") is True,
        "finalReplayGoalComplete": c_final_replay.get("goalComplete") is True,
        "evidenceGateChainAuditExists": bool(gate_chain),
        "evidenceGateChainAllStepsPassed": c_gate_chain.get("allStepsPassed") is True,
        "evidenceGateChainStepCount": c_gate_chain.get("stepCount"),
        "evidenceGateChainFinalProofTaskCount": c_gate_chain.get("finalProofTaskCount"),
        "evidenceGateChainFinalNoCurrentRouteToPhase5": c_gate_chain.get("finalNoCurrentRouteToPhase5") is True,
        "evidenceGateChainFinalReadyForFreshExperiment": c_gate_chain.get("finalReadyForFreshExperiment") is True,
        "evidenceGateChainGoalComplete": c_gate_chain.get("goalComplete") is True,
        "evidenceManifestExists": bool(evidence_manifest),
        "evidenceManifestFileCount": c_evidence_manifest.get("fileCount"),
        "evidenceManifestAllFilesExist": c_evidence_manifest.get("allFilesExist") is True,
        "evidenceManifestAllFilesHashed": c_evidence_manifest.get("allFilesHashed") is True,
        "evidenceManifestDuplicateHashCount": c_evidence_manifest.get("duplicateHashCount"),
        "evidenceManifestGateChainAllStepsPassed": c_evidence_manifest.get("gateChainAllStepsPassed") is True,
        "evidenceManifestGoalComplete": c_evidence_manifest.get("goalComplete") is True,
        "evidenceManifestVerifyExists": bool(evidence_manifest_verify),
        "evidenceManifestVerifyAllFilesExist": c_evidence_manifest_verify.get("allFilesExist") is True,
        "evidenceManifestVerifyAllHashesMatch": c_evidence_manifest_verify.get("allHashesMatch") is True,
        "evidenceManifestVerifyHashMismatchCount": c_evidence_manifest_verify.get("hashMismatchCount"),
        "evidenceManifestVerifyGoalComplete": c_evidence_manifest_verify.get("goalComplete") is True,
        "goalCompletionVerifierExists": bool(goal_completion_verifier),
        "goalCompletionVerifierCompletionVerified": c_goal_completion_verifier.get("completionVerified") is True,
        "goalCompletionVerifierFailedGateCount": c_goal_completion_verifier.get("failedGateCount"),
        "goalCompletionVerifierGoalComplete": c_goal_completion_verifier.get("goalComplete") is True,
        "endToEndPureProtocolPocMissing": "end_to_end_pure_protocol_poc" in (s_goal.get("blockingOrMissing") or []),
        "goalComplete": False,
        "readyForFreshExperiment": False,
    }

    reset_checks["resetLocalProxySearchesNegative"] = (
        reset_checks["resetSamplingComplete"] is True
        and reset_checks["allResetCoverageComplete"] is True
        and reset_checks["stateMachineClientVisibleProxyCount"] == 0
        and reset_checks["singleTransitionCandidateCount"] == 0
        and reset_checks["hookAxisRecommendedAxisCount"] == 0
        and reset_checks["hookAxisMissingObservedHookCount"] == 0
        and reset_checks["hookAxisMissingContrastHookCount"] == 0
        and reset_checks["hookAxisNotInstrumentedHookCount"] == 0
        and reset_checks["promotedSingleTransitionCandidateCount"] == 0
        and reset_checks["runtimeJsCandidateReductionPromotedCount"] == 0
        and reset_checks["runtimeJsCandidateReductionUnclassifiedCount"] == 0
        and reset_checks["runtimeJsAllCandidatesReduced"] is True
        and reset_checks["collectorHandlerNotPromoted"] is True
        and reset_checks["unobservedLifecycleReadyForFreshExperiment"] is not True
        and reset_checks["routeBLifecycleContrastPromotedCount"] in {None, 0}
        and reset_checks["routeBValueTaxonomyPromotedCount"] in {None, 0}
        and reset_checks["routeBInstrumentationValueContrastControlled"] is not True
        and reset_checks["routeBInstrumentationPatchApplyPassiveObserver"] is not True
        and reset_checks["oneCollectorNotPromoted"] is True
        and reset_checks["methodologicalReadyForFreshExperiment"] is not True
        and reset_checks["encoderVariantFamilyClosedNoSuccess"] is True
        and reset_checks["encoderVariantTerminalPromotedCount"] in {None, 0}
        and reset_checks["encoderVariantTerminalReadyForFreshExperiment"] is not True
        and reset_checks["browserContextAllServerVisibleProxiesReduced"] is True
        and reset_checks["browserContextPromotedCount"] in {None, 0}
        and reset_checks["browserContextReadyForFreshExperiment"] is not True
        and reset_checks["browserContextStaticAllGapsReduced"] is True
        and reset_checks["browserContextStaticPromotedCount"] in {None, 0}
        and reset_checks["browserContextStaticReadyForFreshExperiment"] is not True
        and reset_checks["postStaticContextAllClosedBranchesClosed"] is True
        and reset_checks["postStaticContextPromotedCount"] in {None, 0}
        and reset_checks["postStaticContextReadyForFreshExperiment"] is not True
        and reset_checks["currentRouteAuthorityPromotedCount"] in {None, 0}
        and reset_checks["currentRouteAuthorityReadyForFreshExperiment"] is not True
        and reset_checks["recursiveEvidenceUnclassifiedSuccessSignalCount"] in {None, 0}
        and reset_checks["recursiveEvidenceReplayableFreshSuccessCount"] in {None, 0}
        and reset_checks["recursiveEvidenceReadyForFreshExperiment"] is not True
        and reset_checks["nonJsonEvidenceUnclassifiedSuccessSignalCount"] in {None, 0}
        and reset_checks["nonJsonEvidenceReplayableFreshSuccessCount"] in {None, 0}
        and reset_checks["nonJsonEvidenceReadyForFreshExperiment"] is not True
        and reset_checks["endToEndBoundaryPromotedCount"] in {None, 0}
        and reset_checks["endToEndBoundaryReadyForFreshExperiment"] is not True
        and reset_checks["browserCookieBridgeAlsoPresentInTfFailures"] is True
        and reset_checks["browserCookieBridgePrimaryCollectorNoCookieHeader"] is True
        and reset_checks["browserCookieBridgePromotedCount"] in {None, 0}
        and reset_checks["browserCookieBridgeReadyForFreshExperiment"] is not True
        and reset_checks["encodedSessionSingleAxisEliminatedCount"] == reset_checks["encodedSessionSingleAxisRowCount"]
        and reset_checks["encodedSessionPromotedCount"] in {None, 0}
        and reset_checks["encodedSessionReadyForFreshExperiment"] is not True
        and reset_checks["collectorServerExpectedStateBoundaryAuditExists"] is True
        and reset_checks["collectorServerExpectedStateClientVisibleProxyFoundCount"] in {None, 0}
        and reset_checks["collectorServerExpectedStateNotClientVisible"] is True
        and reset_checks["collectorServerExpectedStatePromotedCount"] in {None, 0}
        and reset_checks["collectorServerExpectedStateReadyForFreshExperiment"] is not True
        and reset_checks["candidateIntakeAuditExists"] is True
        and reset_checks["candidateIntakePromotedCount"] in {None, 0}
        and reset_checks["candidateIntakeReadyForFreshExperiment"] is not True
        and reset_checks["phase3ProposalEvidenceTriageExists"] is True
        and reset_checks["phase3ProposalWorthyEvidenceCount"] in {None, 0}
        and reset_checks["phase3RecursiveReadyOrPromotedSignalCount"] in {None, 0}
        and reset_checks["phase3ReadyForFreshExperiment"] is not True
        and reset_checks["phase3EvidenceEntranceCoverageExists"] is True
        and reset_checks["phase3UncoveredEntranceRowCount"] in {None, 0}
        and reset_checks["phase3ProposalEntranceExhaustedForCurrentEvidence"] is True
        and reset_checks["phase3RawEvidenceEntranceExists"] is True
        and reset_checks["phase3RawProposalWorthySignalCount"] in {None, 0}
        and reset_checks["phase3RawTraceCrosswalkExists"] is True
        and reset_checks["phase3RawTraceCrosswalkUnreferencedCount"] in {None, 0}
        and reset_checks["phase3RawTraceCrosswalkProposalWorthyCount"] in {None, 0}
        and reset_checks["traceClassifierRawCoverageGapExists"] is True
        and reset_checks["traceClassifierSafeToAutoAppend"] is not True
        and reset_checks["traceClassifierProposalWorthyCoverageGapCount"] in {None, 0}
        and reset_checks["remainingBoundaryProposalGateExists"] is True
        and reset_checks["remainingBoundaryProposalReadyRowCount"] in {None, 0}
        and reset_checks["remainingBoundaryProposalReadyForFreshExperiment"] is not True
        and reset_checks["candidateSourceContradictionLedgerExists"] is True
        and reset_checks["candidateSourceContradictionLedgerPromotedTotal"] in {None, 0}
        and reset_checks["candidateSourceContradictionLedgerAllSourcesClosed"] is True
        and reset_checks["candidateSourceContradictionLedgerReadyForFreshExperiment"] is not True
        and reset_checks["serverStateValueConsumptionLedgerExists"] is True
        and reset_checks["serverStateValueConsumptionLedgerAllRowsCovered"] is True
        and reset_checks["serverStateValueConsumptionLedgerSingleValueProposalReadyCount"] in {None, 0}
        and reset_checks["serverStateValueConsumptionLedgerReadyForFreshExperiment"] is not True
        and reset_checks["coupledBoundaryTerminalLedgerExists"] is True
        and reset_checks["coupledBoundaryTerminalLedgerProposalReadyRowCount"] in {None, 0}
        and reset_checks["coupledBoundaryTerminalLedgerAllClosed"] is True
        and reset_checks["coupledBoundaryTerminalLedgerReadyForFreshExperiment"] is not True
        and reset_checks["currentEvidenceEntranceTerminalLedgerExists"] is True
        and reset_checks["currentEvidenceEntranceTerminalLedgerUnresolvedNextPointerCount"] in {None, 0}
        and reset_checks["currentEvidenceEntranceTerminalLedgerActiveActionableNextPointerCount"] in {None, 0}
        and reset_checks["currentEvidenceEntranceTerminalLedgerAllClosedOrSuperseded"] is True
        and reset_checks["currentEvidenceEntranceTerminalLedgerReadyForFreshExperiment"] is not True
        and reset_checks["convergentEvidenceEntranceMatrixExists"] is True
        and reset_checks["convergentEvidenceEntranceMatrixRecommendedNextEntranceCount"] in {None, 0}
        and reset_checks["convergentEvidenceEntranceMatrixReadyForFreshExperiment"] is not True
        and reset_checks["manifestCoverageGapExists"] is True
        and reset_checks["manifestCoverageGapHighValueUncoveredDirectoryCount"] in {None, 0}
        and reset_checks["manifestCoverageGapProposalWorthyUnmanifestedDirectoryCount"] in {None, 0}
        and reset_checks["manifestCoverageGapReadyForFreshExperiment"] is not True
        and reset_checks["liveRunnerGateExists"] is True
        and reset_checks["liveRunnerGateProofInvokedUngatedLiveRunnerCount"] in {None, 0}
        and reset_checks["liveRunnerGateGateChainInvokedUngatedLiveRunnerCount"] in {None, 0}
        and reset_checks["liveRunnerGateCurrentNetworkAttemptBlocked"] is True
        and reset_checks["liveRunnerGateReadyForFreshExperiment"] is not True
        and reset_checks["objectiveRequirementCrosswalkExists"] is True
        and reset_checks["objectiveRequirementCrosswalkEndToEndPocMissing"] is True
        and reset_checks["objectiveRequirementCrosswalkFullNoBrowserIndependenceNotProven"] is True
        and reset_checks["objectiveRequirementCrosswalkTraceabilityOnlyPartiallyProven"] is True
        and reset_checks["objectiveRequirementCrosswalkReadyForFreshExperiment"] is not True
        and reset_checks["objectiveRequirementCrosswalkGoalComplete"] is not True
        and reset_checks["promotionPredicateBlockerCrosswalkExists"] is True
        and reset_checks["promotionPredicateBlockerUnsatisfiedPromotionPredicateCount"] and reset_checks["promotionPredicateBlockerUnsatisfiedPromotionPredicateCount"] > 0
        and reset_checks["promotionPredicateBlockerArtifactBackedNegativeDecision"] is True
        and reset_checks["promotionPredicateBlockerStaleAuthorityCleanForNegativeDecision"] is True
        and reset_checks["promotionPredicateBlockerCandidateIntakePromotedCount"] in {None, 0}
        and reset_checks["promotionPredicateBlockerRemainingBoundaryProposalReadyRowCount"] in {None, 0}
        and reset_checks["promotionPredicateBlockerReadyForFreshExperiment"] is not True
        and reset_checks["candidateExecutorReadinessExists"] is True
        and reset_checks["candidateExecutorPlanRequiresCandidateSpecificExecutor"] is True
        and reset_checks["candidateExecutorHarnessDeclaresMissingCandidateSpecificExecutor"] is True
        and reset_checks["candidateExecutorCurrentGateClosedNoNetworkAttempt"] is True
        and reset_checks["candidateExecutorReadyForPromotedCandidate"] is not True
        and reset_checks["candidateExecutorReadyForFreshExperiment"] is not True
        and reset_checks["hypothesisTreeCurrentAuthorityExists"] is True
        and reset_checks["hypothesisTreeH3Terminal"] is True
        and reset_checks["hypothesisTreeH4Terminal"] is True
        and reset_checks["hypothesisTreeH5NotCurrentEntrance"] is True
        and reset_checks["hypothesisTreeOldPlanNoLongerAuthorizesPhase5"] is True
        and reset_checks["hypothesisTreeConvergentPlanIsCurrentAuthority"] is True
        and reset_checks["hypothesisTreeReadyForFreshExperiment"] is not True
        and reset_checks["nearestMissPromotionCandidateExists"] is True
        and reset_checks["nearestMissProposalReadyCandidateCount"] in {None, 0}
        and reset_checks["nearestMissSingleMissingPredicateCandidateCount"] in {None, 0}
        and reset_checks["nearestMissCandidateWithSingleTransitionCount"] in {None, 0}
        and reset_checks["nearestMissReadyForFreshExperiment"] is not True
        and reset_checks["nearestMissBlockerResolutionExists"] is True
        and reset_checks["nearestMissBlockerClosedByExistingControlsCount"] == 2
        and reset_checks["nearestMissBlockerNeedsMoreEvidenceCount"] in {None, 0}
        and reset_checks["nearestMissBlockerPcValueClosed"] is True
        and reset_checks["nearestMissBlockerCollectorCookieHeaderClosed"] is True
        and reset_checks["nearestMissBlockerProposalReadyCandidateCount"] in {None, 0}
        and reset_checks["nearestMissBlockerReadyForFreshExperiment"] is not True
        and reset_checks["remainingNearestMissResolutionExists"] is True
        and reset_checks["remainingNearestMissClosedByExistingControlsCount"] == reset_checks["remainingNearestMissRowCount"]
        and reset_checks["remainingNearestMissOpenRowCount"] in {None, 0}
        and reset_checks["remainingNearestMissProposalReadyCandidateCount"] in {None, 0}
        and reset_checks["remainingNearestMissReadyForFreshExperiment"] is not True
        and reset_checks["exhaustivePromotionCandidateResolutionExists"] is True
        and reset_checks["exhaustiveResolvedCandidateCount"] == reset_checks["exhaustiveCandidateRowCount"]
        and reset_checks["exhaustiveOpenNeedsSpecificEvidenceCount"] in {None, 0}
        and reset_checks["exhaustiveProposalReadyCandidateCount"] in {None, 0}
        and reset_checks["exhaustiveReadyForFreshExperiment"] is not True
        and reset_checks["nextEvidenceSurfaceDiscoveryExists"] is True
        and reset_checks["nextEvidenceClosedSurfaceCount"] == reset_checks["nextEvidenceSurfaceCount"]
        and reset_checks["nextEvidenceOpenSurfaceCount"] in {None, 0}
        and reset_checks["nextEvidenceNewCandidateSurfaceCount"] in {None, 0}
        and reset_checks["nextEvidenceSurfaceWithNewCandidateCount"] in {None, 0}
        and reset_checks["nextEvidenceReadyForFreshExperiment"] is not True
        and reset_checks["externalOutputSurfaceAuditExists"] is True
        and reset_checks["externalOutputSurfaceAuditCollectorSuccess0SignalFileCount"] in {None, 0}
        and reset_checks["externalOutputSurfaceAuditProposalWorthySignalCount"] in {None, 0}
        and reset_checks["externalOutputSurfaceAuditReadyForFreshExperiment"] is not True
        and reset_checks["evidencePackageSurfaceAuditExists"] is True
        and reset_checks["evidencePackageSurfaceAuditProposalWorthySignalCount"] in {None, 0}
        and reset_checks["evidencePackageSurfaceAuditReadyForFreshExperiment"] is not True
        and reset_checks["ctfRegOutputSurfaceAuditExists"] is True
        and reset_checks["ctfRegOutputSurfaceAuditCollectorSuccess0SignalFileCount"] in {None, 0}
        and reset_checks["ctfRegOutputSurfaceAuditProposalWorthySignalCount"] in {None, 0}
        and reset_checks["ctfRegOutputSurfaceAuditReadyForFreshExperiment"] is not True
        and reset_checks["auxiliaryTraceSurfaceAuditExists"] is True
        and reset_checks["auxiliaryTraceSurfaceAuditCollectorSuccess0SignalFileCount"] in {None, 0}
        and reset_checks["auxiliaryTraceSurfaceAuditProposalWorthySignalCount"] in {None, 0}
        and reset_checks["auxiliaryTraceSurfaceAuditReadyForFreshExperiment"] is not True
        and reset_checks["stalePositiveSignalAuthorityExists"] is True
        and reset_checks["stalePositiveSignalAuthorityActiveActionablePositiveSignalCount"] in {None, 0}
        and reset_checks["stalePositiveSignalAuthorityCandidateIntakePromotedCount"] in {None, 0}
        and reset_checks["stalePositiveSignalAuthorityReadyForFreshExperiment"] is not True
        and reset_checks["localTraceEvidenceFreshnessExists"] is True
        and reset_checks["localTraceProposalWorthyNowCount"] in {None, 0}
        and reset_checks["unclassifiedTraceSignalReductionExists"] is True
        and reset_checks["unclassifiedTraceProposalReadyRunCount"] in {None, 0}
        and reset_checks["browserSuccessChainClassificationBacklogExists"] is True
        and reset_checks["browserSuccessChainClassificationBacklogNoBrowserEvidenceCount"] in {None, 0}
        and reset_checks["browserSuccessChainClassificationBacklogProposalReadyRunCount"] in {None, 0}
        and reset_checks["browserSuccessChainClassificationBacklogSafeToPromoteToClassifier"] is not True
        and reset_checks["browserSuccessChainServerVisibleDiffExists"] is True
        and reset_checks["browserSuccessChainServerVisibleProposalCandidateCount"] in {None, 0}
        and reset_checks["browserSuccessPayloadPcSessionLineageExists"] is True
        and reset_checks["browserSuccessPayloadPcSessionLineageProposalCandidateCount"] in {None, 0}
        and reset_checks["collectorResponseHandlerValueLineageExists"] is True
        and reset_checks["collectorResponseHandlerValueLineageProposalCandidateCount"] in {None, 0}
        and reset_checks["downstreamSuccessWithoutCollectorDecodeExists"] is True
        and reset_checks["downstreamSuccessWithoutCollectorDecodeAllLackCollectorSuccess"] is True
        and reset_checks["downstreamSuccessWithoutCollectorDecodeProposalCandidateCount"] in {None, 0}
        and reset_checks["collectorMaterialOnlyResponseClassExists"] is True
        and reset_checks["collectorMaterialOnlyResponseClassCollectorSuccessCount"] in {None, 0}
        and reset_checks["collectorMaterialOnlyResponseClassCreateRedirectCount"] in {None, 0}
        and reset_checks["collectorMaterialOnlyResponseClassProposalCandidateCount"] in {None, 0}
        and reset_checks["lowValueUnclassifiedTraceClosureExists"] is True
        and reset_checks["lowValueUnclassifiedTraceClosureProposalRelevantCount"] in {None, 0}
        and reset_checks["lowValueUnclassifiedTraceClosureAllRemainLowValue"] is True
        and reset_checks["lowValueUnclassifiedTraceClosureProposalCandidateCount"] in {None, 0}
        and reset_checks["unclassifiedTraceClassClosureLedgerExists"] is True
        and reset_checks["unclassifiedTraceClassClosureLedgerAllClosed"] is True
        and reset_checks["unclassifiedTraceClassClosureLedgerProposalCandidateTotal"] in {None, 0}
        and reset_checks["hypothesisPlanCoverageAuditExists"] is True
        and reset_checks["hypothesisPlanMissingRequiredPhaseArtifactCount"] in {None, 0}
        and reset_checks["hypothesisPlanMinimalExperimentMissingAllowedByGate"] is True
        and reset_checks["hypothesisPlanAllHypothesesCovered"] is True
        and reset_checks["hypothesisPlanH3RemainingNotClientVisible"] is True
        and reset_checks["hypothesisPlanPromotedCount"] in {None, 0}
        and reset_checks["hypothesisPlanReadyForFreshExperiment"] is not True
        and reset_checks["completionRequirementsAuditExists"] is True
        and reset_checks["completionFreshSuccessMissing"] is True
        and reset_checks["completionNoCurrentExperimentRoute"] is True
        and reset_checks["completionReadyForFreshExperiment"] is not True
        and reset_checks["completionGoalComplete"] is not True
        and reset_checks["minimalTransitionExperimentExists"] is True
        and reset_checks["minimalTransitionExperimentGateEvaluated"] is True
        and reset_checks["minimalTransitionExperimentBlockedByGate"] is True
        and reset_checks["minimalTransitionExperimentNetworkAttemptExecuted"] is not True
        and reset_checks["minimalTransitionExperimentStageAdvanced"] is not True
        and reset_checks["minimalTransitionExperimentReadyForFreshExperiment"] is not True
        and reset_checks["minimalTransitionExperimentGoalComplete"] is not True
        and reset_checks["allFinalResponsesSameClass"] is True
        and reset_checks["allFinalResponsesAreSeq5Minus1"] is True
        and reset_checks["anySeq5Success0"] is False
        and reset_checks["decodedFailureStillMutatesPx3Pxde"] is True
        and reset_checks["decodedFailureHasNoSuccess0"] is True
        and reset_checks["transportDecisionOnlyTransportChangedStageDifferenceProved"] is not True
        and reset_checks["legacyHighValueUnminedUnclassifiedSuccessSignalCount"] in {None, 0}
        and reset_checks["legacyHighValueUnminedReplayableSuccessNotFound"] is True
        and reset_checks["evidenceGatedPocExists"] is True
        and reset_checks["evidenceGatedPocBlockedByGate"] is True
        and reset_checks["evidenceGatedPocNetworkAttemptExecuted"] is not True
        and reset_checks["evidenceGatedPocFreshCollectorSuccess"] is not True
        and reset_checks["evidenceGatedPocReadyForFreshExperiment"] is not True
        and reset_checks["evidenceGatedPocGoalComplete"] is not True
        and reset_checks["finalReplayAuditExists"] is True
        and reset_checks["finalReplayGateEvaluated"] is True
        and reset_checks["finalReplayBlockedByGate"] is True
        and reset_checks["finalReplayReadyForFreshReplay"] is not True
        and reset_checks["finalReplayAttemptExecuted"] is not True
        and reset_checks["finalReplayNetworkAttemptExecuted"] is not True
        and reset_checks["finalReplayGoalComplete"] is not True
        and reset_checks["evidenceGateChainFinalReadyForFreshExperiment"] is not True
        and reset_checks["evidenceGateChainGoalComplete"] is not True
        and reset_checks["evidenceManifestGoalComplete"] is not True
        and reset_checks["evidenceManifestVerifyGoalComplete"] is not True
        and reset_checks["goalCompletionVerifierGoalComplete"] is not True
    )
    reset_checks["noCurrentRouteToPhase5"] = (
        reset_checks["resetLocalProxySearchesNegative"] is True
        and reset_checks["endToEndPureProtocolPocMissing"] is True
    )

    evidence_blocks = [
        {
            "id": "reset_sampling_complete",
            "evidence": str(INPUTS["resetSamplingMatrix"]),
            "facts": [
                f"resetSamplingComplete={c_matrix.get('resetSamplingComplete')}",
                f"pureProtocolResetSamplingComplete={c_matrix.get('pureProtocolResetSamplingComplete')}",
                f"browserRunnerExecutedCount={c_matrix.get('browserRunnerExecutedCount')}",
            ],
            "meaning": "The reset matrix has enough current browser and pure-protocol evidence; lack of candidate is not caused by missing minimum sampling.",
        },
        {
            "id": "coverage_complete",
            "evidence": str(INPUTS["resetSamplingCoverage"]),
            "facts": [
                f"allResetCoverageComplete={c_coverage.get('allResetCoverageComplete')}",
                f"browserResetCoverageComplete={c_coverage.get('browserResetCoverageComplete')}",
                f"pureProtocolResetCoverageComplete={c_coverage.get('pureProtocolResetCoverageComplete')}",
            ],
            "meaning": "The current reset coverage gate is closed.",
        },
        {
            "id": "state_machine_no_proxy",
            "evidence": str(INPUTS["resetStateMachine"]),
            "facts": [
                f"sampleCount={c_state.get('sampleCount')}",
                f"clientVisibleProxyCount={c_state.get('clientVisibleProxyCount')}",
                f"hookFeatureSuccessOnlyCount={c_state.get('hookFeatureSuccessOnlyCount')}",
                f"readyForFreshExperiment={c_state.get('readyForFreshExperiment')}",
            ],
            "meaning": "The reset state machine does not expose a pre-accept client-visible proxy.",
        },
        {
            "id": "single_transition_absent",
            "evidence": str(INPUTS["resetSingleTransitionCandidates"]),
            "facts": [
                f"singleTransitionCandidateCount={c_single.get('singleTransitionCandidateCount')}",
                f"candidateClientVisibleProxyCount={c_single.get('candidateClientVisibleProxyCount')}",
                f"readyForFreshExperiment={c_single.get('readyForFreshExperiment')}",
            ],
            "meaning": "There is no one-variable pure-protocol experiment to run.",
        },
        {
            "id": "hook_axes_closed",
            "evidence": str(INPUTS["resetNewHookAxisPlan"]),
            "facts": [
                f"missingObservedHookCount={c_hook_axis.get('missingObservedHookCount')}",
                f"missingContrastHookCount={c_hook_axis.get('missingContrastHookCount')}",
                f"notInstrumentedHookCount={c_hook_axis.get('notInstrumentedHookCount')}",
                f"recommendedAxisCount={c_hook_axis.get('recommendedAxisCount')}",
            ],
            "meaning": "The currently defined hook/sampling axes do not justify another browser sample or hook expansion.",
        },
        {
            "id": "success_only_hook_features_reduced",
            "evidence": str(INPUTS["resetHookFeatureCandidateReduction"]),
            "facts": [
                f"successOnlyHookFeatureCandidateCount={c_reducer.get('successOnlyHookFeatureCandidateCount')}",
                f"promotedSingleTransitionCandidateCount={c_reducer.get('promotedSingleTransitionCandidateCount')}",
                f"allHookAxesClosed={c_reducer.get('allHookAxesClosed')}",
            ],
            "meaning": "worker/wasm/pow_worker remain correlated browser-success features, not Phase 5 inputs.",
        },
        {
            "id": "reset_runtime_js_taxonomy_reduced",
            "evidence": [
                str(INPUTS["resetRuntimeJsEventTaxonomy"]),
                str(INPUTS["resetRuntimeJsCandidateReduction"]),
                str(INPUTS["resetOneCollectorSurfaceAudit"]),
            ],
            "facts": [
                f"candidateClientVisibleProxyCount={c_runtime_taxonomy.get('candidateClientVisibleProxyCount')}",
                f"strongJsContrastCandidateCount={c_runtime_taxonomy.get('strongJsContrastCandidateCount')}",
                f"reductionCount={c_runtime_reduction.get('reductionCount')}",
                f"promotedSingleTransitionCandidateCount={c_runtime_reduction.get('promotedSingleTransitionCandidateCount')}",
                f"unclassifiedReductionCount={c_runtime_reduction.get('unclassifiedReductionCount')}",
                f"oneCollectorSuccessSampleCount={c_onecollector.get('oneCollectorSuccessSampleCount')}",
                f"oneCollectorAfterAcceptedChainCount={c_onecollector.get('oneCollectorAfterAcceptedChainCount')}",
            ],
            "meaning": "Reset runtime/JS traces expose many correlated event-bus/handler/WASM/POW/OneCollector surfaces, but reduction promotes none to a constructible Phase 5 transition.",
        },
        {
            "id": "collector_handler_surfaces_reduced",
            "evidence": str(INPUTS["resetCollectorHandlerSurfaceAudit"]),
            "facts": [
                f"handlerCandidateCount={c_handler.get('handlerCandidateCount')}",
                f"distinctHandlerKeyCount={c_handler.get('distinctHandlerKeyCount')}",
                f"pxCookieHandlerSurfaceCount={c_handler.get('pxCookieHandlerSurfaceCount')}",
                f"powChallengeHandlerSurfaceCount={c_handler.get('powChallengeHandlerSurfaceCount')}",
                f"configFlagHandlerSurfaceCount={c_handler.get('configFlagHandlerSurfaceCount')}",
                f"scoreOrStateHandlerSurfaceCount={c_handler.get('scoreOrStateHandlerSurfaceCount')}",
                f"unclassifiedHandlerSurfaceCount={c_handler.get('unclassifiedHandlerSurfaceCount')}",
                f"promotedSingleTransitionCandidateCount={c_handler.get('promotedSingleTransitionCandidateCount')}",
            ],
            "meaning": "The largest reset runtime/JS bucket, collector_response_handler, has been split into response-side cookie/config/POW/score/state surfaces; none proves a constructible pre-accept Phase 5 transition.",
        },
        {
            "id": "unobserved_lifecycle_surface_audit",
            "evidence": str(INPUTS["resetUnobservedLifecycleSurfaceAudit"]),
            "facts": [
                f"surfaceCount={c_lifecycle.get('surfaceCount')}",
                f"staticReachableSurfaceCount={c_lifecycle.get('staticReachableSurfaceCount')}",
                f"runtimeObservedSurfaceCount={c_lifecycle.get('runtimeObservedSurfaceCount')}",
                f"staticReachableButRuntimeUnobservedCount={c_lifecycle.get('staticReachableButRuntimeUnobservedCount')}",
                f"recommendedNewHookCount={c_lifecycle.get('recommendedNewHookCount')}",
                f"readyForResampling={c_lifecycle.get('readyForResampling')}",
                f"readyForFreshExperiment={c_lifecycle.get('readyForFreshExperiment')}",
            ],
            "meaning": "Route B enumerates static-reachable lifecycle/fingerprint surfaces against current hooks. Recommendations are hook work only and do not authorize Phase 5.",
        },
        {
            "id": "route_b_resampling_manifest",
            "evidence": str(INPUTS["resetRouteBResamplingManifest"]),
            "facts": [
                f"routeBImplementedHookCount={c_route_b_manifest.get('routeBImplementedHookCount')}",
                f"routeBRecommendedNewHookCount={c_route_b_manifest.get('routeBRecommendedNewHookCount')}",
                f"readyForRouteBControlledBrowserResampling={c_route_b_manifest.get('readyForRouteBControlledBrowserResampling')}",
                f"readyForFreshExperiment={c_route_b_manifest.get('readyForFreshExperiment')}",
            ],
            "meaning": "Route B may proceed to browser evidence resampling only; this is not a pure-protocol Phase 5 authorization.",
        },
        {
            "id": "route_b_lifecycle_contrast",
            "evidence": str(INPUTS["resetRouteBLifecycleContrastAudit"]),
            "facts": [
                f"realAttemptCount={c_route_b_contrast.get('realAttemptCount')}",
                f"successSampleCount={c_route_b_contrast.get('successSampleCount')}",
                f"failureSampleCount={c_route_b_contrast.get('failureSampleCount')}",
                f"successOnlyHookKindCount={c_route_b_contrast.get('successOnlyHookKindCount')}",
                f"promotedSingleTransitionCandidateCount={c_route_b_contrast.get('promotedSingleTransitionCandidateCount')}",
                f"readyForFreshExperiment={c_route_b_contrast.get('readyForFreshExperiment')}",
            ],
            "meaning": "Route B browser contrast has no promoted pure-protocol transition unless value lineage into request/cookie/risk is proven.",
        },
        {
            "id": "methodological_terminal_boundary",
            "evidence": str(INPUTS["methodologicalTerminalBoundaryAudit"]),
            "facts": [
                f"allRoutesClosed={c_methodological.get('allRoutesClosed')}",
                f"readyForFreshExperiment={c_methodological.get('readyForFreshExperiment')}",
                f"goalComplete={c_methodological.get('goalComplete')}",
            ],
            "meaning": "Methodological Route A/B/C terminal consolidation is closed without a promoted transition.",
        },
        {
            "id": "next_evidence_entrance_audit",
            "evidence": str(INPUTS["nextEvidenceEntranceAudit"]),
            "facts": [
                f"inventoryCandidateSourceCount={c_next_entrance.get('inventoryCandidateSourceCount')}",
                f"crossSampleCandidateClientVisibleProxyCount={c_next_entrance.get('crossSampleCandidateClientVisibleProxyCount')}",
                f"historicalNoBrowserSuccess0={c_next_entrance.get('historicalNoBrowserSuccess0')}",
                f"jsReplayableClientTransitionCandidateCount={c_next_entrance.get('jsReplayableClientTransitionCandidateCount')}",
                f"allKnownLocalEvidenceEntrancesClosed={c_next_entrance.get('allKnownLocalEvidenceEntrancesClosed')}",
            ],
            "meaning": "Known local evidence entrances from old inventory and reset routes are closed; reopening requires genuinely new evidence.",
        },
        {
            "id": "final_failure_class_stable",
            "evidence": str(INPUTS["resetFinalResponseClassAudit"]),
            "facts": [
                f"sampleCount={c_final.get('sampleCount')}",
                f"allFinalResponsesSameClass={c_final.get('allFinalResponsesSameClass')}",
                f"allFinalResponsesAreSeq5Minus1={c_final.get('allFinalResponsesAreSeq5Minus1')}",
                f"anySeq5Success0={c_final.get('anySeq5Success0')}",
            ],
            "meaning": "Pure-protocol reset samples reach final collector responses but remain in the same failure class.",
        },
        {
            "id": "browser_context_proxy_reduced",
            "evidence": str(INPUTS["browserContextToServerStateProxyAudit"]),
            "facts": [
                f"preAcceptMessageCount={c_browser_context_proxy.get('preAcceptMessageCount')}",
                f"blockValuesAlreadyRepresentedInRequest={c_browser_context_proxy.get('blockValuesAlreadyRepresentedInRequest')}",
                f"allBrowserContextServerVisibleProxiesReduced={c_browser_context_proxy.get('allBrowserContextServerVisibleProxiesReduced')}",
                f"promotedSingleTransitionCandidateCount={c_browser_context_proxy.get('promotedSingleTransitionCandidateCount')}",
                f"readyForFreshExperiment={c_browser_context_proxy.get('readyForFreshExperiment')}",
            ],
            "meaning": "Browser parent bridge, iframe postMessage, and Microsoft context were mapped against line922/line933; no new pre-accept server-visible single transition is promoted.",
        },
        {
            "id": "browser_context_static_inventory_reduced",
            "evidence": [
                str(INPUTS["browserContextStaticGapInventory"]),
                str(INPUTS["postStaticContextTerminalGapAudit"]),
            ],
            "facts": [
                f"allStaticContextGapsReduced={c_browser_context_static.get('allStaticContextGapsReduced')}",
                f"staticProducerIdentifiedCount={c_browser_context_static.get('staticProducerIdentifiedCount')}",
                f"staticProducerLine922FreshEqualCount={c_browser_context_static.get('staticProducerLine922FreshEqualCount')}",
                f"promotedSingleTransitionCandidateCount={c_browser_context_static.get('promotedSingleTransitionCandidateCount')}",
                f"allClosedBranchesClosed={c_post_static_context_terminal.get('allClosedBranchesClosed')}",
                f"postStaticContextPromotedCount={c_post_static_context_terminal.get('promotedSingleTransitionCandidateCount')}",
            ],
            "meaning": "Static browser-context/PX561 producer inventory found no new request/payload/cookie/risk transition; identified static producers already equal in fresh line922 or are inactive in counted traces.",
        },
        {
            "id": "current_route_authority",
            "evidence": str(INPUTS["currentRouteAuthorityAudit"]),
            "facts": [
                f"staleReadyArtifactCount={c_current_route_authority.get('staleReadyArtifactCount')}",
                f"liveProbeClosedNoSuccess={c_current_route_authority.get('liveProbeClosedNoSuccess')}",
                f"currentPromotedSingleTransitionCandidateCount={c_current_route_authority.get('currentPromotedSingleTransitionCandidateCount')}",
                f"readyForFreshExperiment={c_current_route_authority.get('readyForFreshExperiment')}",
            ],
            "meaning": "Older ready/single-transition artifacts are superseded by the executed live probe and terminal audits; they no longer authorize network execution.",
        },
        {
            "id": "recursive_evidence_blindspot_audit",
            "evidence": str(INPUTS["recursiveEvidenceBlindspotAudit"]),
            "facts": [
                f"recursiveJsonFileCount={c_recursive_blindspot.get('recursiveJsonFileCount')}",
                f"recursiveSuccessSignalFileCount={c_recursive_blindspot.get('recursiveSuccessSignalFileCount')}",
                f"extractedSeq5Seq6ResponseCount={c_recursive_blindspot.get('extractedSeq5Seq6ResponseCount')}",
                f"extractedSeq5Seq6SuccessSignalCount={c_recursive_blindspot.get('extractedSeq5Seq6SuccessSignalCount')}",
                f"unclassifiedRecursiveSuccessSignalCount={c_recursive_blindspot.get('unclassifiedRecursiveSuccessSignalCount')}",
                f"replayableFreshNoBrowserSuccessEvidenceCount={c_recursive_blindspot.get('replayableFreshNoBrowserSuccessEvidenceCount')}",
            ],
            "meaning": "Nested JSON artifacts that top-level scans can miss were scanned recursively; success tokens are browser-sampling references, and extracted pure-protocol seq5/seq6 responses contain no success handler.",
        },
        {
            "id": "non_json_evidence_blindspot_audit",
            "evidence": str(INPUTS["nonJsonEvidenceBlindspotAudit"]),
            "facts": [
                f"scannedTextFileCount={c_non_json_blindspot.get('scannedTextFileCount')}",
                f"successSignalFileCount={c_non_json_blindspot.get('successSignalFileCount')}",
                f"browserReferenceSuccessSignalCount={c_non_json_blindspot.get('browserReferenceSuccessSignalCount')}",
                f"documentationOrManifestSuccessSignalCount={c_non_json_blindspot.get('documentationOrManifestSuccessSignalCount')}",
                f"pureProtocolSuccessSignalFileCount={c_non_json_blindspot.get('pureProtocolSuccessSignalFileCount')}",
                f"unclassifiedSuccessSignalCount={c_non_json_blindspot.get('unclassifiedSuccessSignalCount')}",
                f"replayableFreshNoBrowserSuccessEvidenceCount={c_non_json_blindspot.get('replayableFreshNoBrowserSuccessEvidenceCount')}",
            ],
            "meaning": "Non-JSON local evidence files, including logs, markdown, HAR-like text, HTML, txt, jsonl, and patches, were scanned for success tokens; no replayable fresh no-browser success proof was found.",
        },
        {
            "id": "proof_script_reproducibility_audit",
            "evidence": str(INPUTS["proofScriptReproducibilityAudit"]),
            "facts": [
                f"taskCount={c_proof_repro.get('taskCount')}",
                f"passedTaskCount={c_proof_repro.get('passedTaskCount')}",
                f"failedTaskCount={c_proof_repro.get('failedTaskCount')}",
                f"allProofScriptsReproducible={c_proof_repro.get('allProofScriptsReproducible')}",
                f"readyForFreshExperiment={c_proof_repro.get('readyForFreshExperiment')}",
            ],
            "meaning": "Key offline proof scripts for classifier, decoder, payload constructor, POW, cookie jar, risk/verify rebuild, WASM NQ/NG, evidence blindspots, and goal gap were rerun and still satisfy their expected checks.",
        },
        {
            "id": "end_to_end_remaining_boundary_audit",
            "evidence": str(INPUTS["endToEndRemainingBoundaryAudit"]),
            "facts": [
                f"eliminatedBoundaryCount={c_e2e_boundary.get('eliminatedBoundaryCount')}",
                f"remainingBoundaryCount={c_e2e_boundary.get('remainingBoundaryCount')}",
                f"promotedSingleTransitionCandidateCount={c_e2e_boundary.get('promotedSingleTransitionCandidateCount')}",
                f"decodedSeq5Seq6ActivityEqualityRejected={c_e2e_boundary.get('decodedSeq5Seq6ActivityEqualityRejected')}",
                f"freshServerBoundTailStrongestRejected={c_e2e_boundary.get('freshServerBoundTailStrongestRejected')}",
                f"exactPayloadPcAndExactBodyNoSuccess={c_e2e_boundary.get('exactPayloadPcAndExactBodyNoSuccess')}",
                f"encodedBoundaryStillCoupled={c_e2e_boundary.get('encodedBoundaryStillCoupled')}",
                f"readyForFreshExperiment={c_e2e_boundary.get('readyForFreshExperiment')}",
            ],
            "meaning": "The end-to-end PoC gap is now collapsed into eliminated boundaries and three remaining coupled boundaries; none is promoted to a fresh-experiment single transition.",
        },
        {
            "id": "browser_cookie_bridge_candidate_audit",
            "evidence": str(INPUTS["browserCookieBridgeCandidateAudit"]),
            "facts": [
                f"timelineFileCount={c_cookie_bridge_candidate.get('timelineFileCount')}",
                f"cookieBridgeCorrelationAlsoPresentInTfFailures={c_cookie_bridge_candidate.get('cookieBridgeCorrelationAlsoPresentInTfFailures')}",
                f"tfFailuresWithCookieBridgeNoParentSuccessCount={c_cookie_bridge_candidate.get('tfFailuresWithCookieBridgeNoParentSuccessCount')}",
                f"parentChallengeSuccessCanExistWithoutDecodedSuccess0={c_cookie_bridge_candidate.get('parentChallengeSuccessCanExistWithoutDecodedSuccess0')}",
                f"primaryCollectorCookieHeaderObservedRunCount={c_cookie_bridge_candidate.get('primaryCollectorCookieHeaderObservedRunCount')}",
                f"collectorCookieHeadersOnlyOnBeaconOrTelemetry={c_cookie_bridge_candidate.get('collectorCookieHeadersOnlyOnBeaconOrTelemetry')}",
                f"promotedSingleTransitionCandidateCount={c_cookie_bridge_candidate.get('promotedSingleTransitionCandidateCount')}",
            ],
            "meaning": "The browser parent cookie bridge does not currently promote to a pure-protocol candidate: it is present in tf-failure runs without parent success, and primary collector flow requests carry no Cookie header.",
        },
        {
            "id": "encoded_session_binding_candidate_audit",
            "evidence": str(INPUTS["encodedSessionBindingCandidateAudit"]),
            "facts": [
                f"singleAxisRowCount={c_encoded_session_candidate.get('singleAxisRowCount')}",
                f"singleAxisEliminatedCount={c_encoded_session_candidate.get('singleAxisEliminatedCount')}",
                f"exactPayloadPcNoSuccess={c_encoded_session_candidate.get('exactPayloadPcNoSuccess')}",
                f"exactBodyNoSuccess={c_encoded_session_candidate.get('exactBodyNoSuccess')}",
                f"pcAloneEliminated={c_encoded_session_candidate.get('pcAloneEliminated')}",
                f"markerChoiceEliminated={c_encoded_session_candidate.get('markerChoiceEliminated')}",
                f"templateOuterFreshPayloadPcNoSuccess={c_encoded_session_candidate.get('templateOuterFreshPayloadPcNoSuccess')}",
                f"forcedOverlapExactPayloadPcNoSuccess={c_encoded_session_candidate.get('forcedOverlapExactPayloadPcNoSuccess')}",
                f"promotedSingleTransitionCandidateCount={c_encoded_session_candidate.get('promotedSingleTransitionCandidateCount')}",
            ],
            "meaning": "Payload/pc/session binding has been decomposed into six single-axis controls; all are negative, so the remaining boundary is still coupled live session/server-state binding.",
        },
        {
            "id": "cookie_handler_not_enough",
            "evidence": str(INPUTS["resetCookieMutationAudit"]),
            "facts": [
                f"allOfflineJarHasPx3Pxde={c_cookie.get('allOfflineJarHasPx3Pxde')}",
                f"allFinalJarUsesSeq6Values={c_cookie.get('allFinalJarUsesSeq6Values')}",
                f"anySuccess0={c_cookie.get('anySuccess0')}",
                f"riskVerifyCandidateComplete={c_cookie.get('riskVerifyCandidateComplete')}",
            ],
            "meaning": "Decoded failure handlers can mutate _px3/_pxde, but that is not a success-cookie/risk candidate.",
        },
        {
            "id": "transport_ip_not_promoted",
            "evidence": [str(INPUTS["resetTransportIpHypothesisAudit"]), str(INPUTS["resetTransportIpDecisionAudit"])],
            "facts": [
                f"readyForFreshExperiment={c_transport.get('readyForFreshExperiment')}",
                f"goalComplete={c_transport.get('goalComplete')}",
                f"onlyTransportChangedStageDifferenceProved={c_transport_decision.get('onlyTransportChangedStageDifferenceProved')}",
                f"ipOrTransportPromotedToControlVariableOnly={c_transport_decision.get('ipOrTransportPromotedToControlVariableOnly')}",
            ],
            "meaning": "Current reset evidence does not prove IP/Webshare/direct as the single cause.",
        },
        {
            "id": "legacy_frontier_consistency",
            "evidence": [
                str(INPUTS["legacyServerInternalGap"]),
                str(INPUTS["legacyActionableFrontier"]),
                str(INPUTS["legacyHighValueUnminedTriage"]),
            ],
            "facts": [
                f"legacyAllLocalProxySearchesNegative={c_legacy_gap.get('allLocalProxySearchesNegative')}",
                f"legacyActionableMissingArtifactCount={c_legacy_frontier.get('actionableMissingArtifactCount')}",
                f"legacyUnminedCoveredDirectoryCount={c_legacy_unmined.get('coveredDirectoryCount')}",
                f"legacyUnminedSuccessSignalFileCount={c_legacy_unmined.get('unminedSuccessSignalFileCount')}",
                f"legacyUnclassifiedSuccessSignalCount={c_legacy_triage.get('unclassifiedSuccessSignalCount')}",
                f"legacyReplayableFreshNoBrowserSuccessEvidence={c_legacy_triage.get('hasReplayableFreshNoBrowserSuccessEvidence')}",
            ],
            "meaning": "The reset result is consistent with the older reframe audits; it does not rely on them alone.",
        },
    ]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": (
            "Route B terminal audit for the reset plan: consolidate current reset sampling, hook, reducer, "
            "final-response, cookie, transport, and legacy-frontier evidence before deciding whether Phase 5 is justified."
        ),
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": reset_checks,
        "evidenceBlocks": evidence_blocks,
        "remainingGap": {
            "id": "collector_server_internal_or_unobserved_expected_state_after_reset",
            "status": "not_reduced_to_replayable_client_transition",
            "whatIsProven": (
                "Current reset evidence proves that minimum sampling is complete, current hook axes have both observed and contrast coverage, "
                "success-only worker/wasm/pow_worker features do not reduce to a standalone pure-protocol transition, pure-protocol final responses "
                "remain in the same oIIoIooo|-1 failure class, decoded _px3/_pxde mutation is not enough to produce risk/verify success, "
                "and reset runtime/JS taxonomy candidates reduce to correlated surfaces without a promoted transition; the only network surface is OneCollector telemetry after accepted downstream chain."
                " The largest collector response-handler subgroup has also been split and promotes no single transition. Browser context bridge/postMessage evidence has now also been mapped to line922/line933 without promoting a new server-visible transition. Static browser-context/PX561 producer inventory is also reduced without a promoted transition. Recursive nested JSON and non-JSON text/log evidence blindspot scanning found no replayable fresh no-browser success evidence. Key offline proof scripts are reproducible in the current worktree. The end-to-end gap is currently reduced to coupled payload/pc/session/server-state or browser-state boundaries, with no promoted single transition."
            ),
            "whatIsMissing": (
                "A concrete client-visible, pre-accept, pure-protocol constructible transition that can be changed in a fresh no-browser session "
                "to produce collector oIIoIooo|0."
            ),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Do not run Phase 5 from the current state: reset sampling/hook coverage is complete, but there is still no single "
                "client-visible transition candidate. The end-to-end pure protocol PoC remains missing."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
