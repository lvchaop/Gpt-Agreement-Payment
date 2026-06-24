#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def p(rel: str) -> str:
    return str(ROOT / rel)


def main() -> int:
    artifacts = [
        "selected_contrast_pair.json",
        "hypothesis_matrix.json",
        "collector_state_transition_diff_s00_vs_fresh.json",
        "first_decisive_divergence.json",
        "pre_seq5_state_lineage_detail.json",
        "accepted_line933_generation_lineage.json",
        "server_expected_state_pre_seq5_gap.json",
        "server_state_transition_value_model.json",
        "request_history_coherence_gap.json",
        "next_decisive_static_gap.json",
        "line922_dynamic_field_source_map.json",
        "line922_candidate_reduction.json",
        "encoded_payload_pc_form_diff_map.json",
        "server_state_value_to_request_lineage.json",
        "final_boundary_decision_matrix.json",
        "coupled_encoder_variant_audit.json",
        "server_internal_state_gap_audit.json",
        "remaining_encoder_variant_build_matrix.json",
        "server_observable_state_inventory.json",
        "bridge_to_payload_context_audit.json",
        "s00_risk_verify_material_gap.json",
        "collector_to_risk_consumption_chain.json",
        "single_transition_candidate_matrix.json",
        "coupled_boundary_reduction_plan.json",
        "outer_session_tuple_factorization.json",
        "encoder_axis_equivalence.json",
        "server_expected_state_observable_proxy.json",
        "server_internal_gap_evidence_inventory.json",
        "cross_sample_server_state_proxy_matrix.json",
        "historical_probe_response_class_matrix.json",
        "unmined_local_evidence_source_audit.json",
        "high_value_unmined_evidence_triage.json",
        "js_internal_event_taxonomy.json",
        "js_internal_candidate_reduction.json",
        "actionable_frontier_audit.json",
        "server_internal_unobserved_state_final_gap.json",
        "pure_protocol_completion_requirements_audit.json",
    ]
    loaded = {}
    for name in artifacts:
        rel = f"output/protocol_reverse/hypothesis_reframe/{name}"
        path = ROOT / rel
        loaded[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    status = {
        "purpose": "Current machine-readable status for pure-protocol HUMAN hypothesis reframe execution.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "artifactOrder": [p(f"output/protocol_reverse/hypothesis_reframe/{name}") for name in artifacts],
        "provenEliminations": [
            {
                "id": "decoded_activity_semantics",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
                "facts": [
                    "freshSeq5ActivityTypesEqualS00=true",
                    "freshSeq5ChangedFieldInstances=0",
                    "decodedJsonEqual=true",
                    "decodedTextEqual=true",
                ],
            },
            {
                "id": "request_history_order_gap",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
                "facts": ["hasOrderGap=false"],
            },
            {
                "id": "marker_only_static_payload_pc",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
                "facts": [
                    "baseAfterMarkerRemovalEqual=true",
                    "payloadDiffers=true",
                    "pcDiffers=true",
                    "static payload/pc controls rejected",
                ],
            },
            {
                "id": "outer_session_tuple_single_field",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/outer_session_tuple_factorization.json"),
                "facts": [
                    "singleReadyGroupCount=0",
                    "noSingleFieldExperimentReady=true",
                ],
            },
            {
                "id": "encoder_single_axis",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/encoder_axis_equivalence.json"),
                "facts": [
                    "remainingFamilyIsIndependent2x2=true",
                    "remainingEncoderAxisCount=2",
                    "singleEncoderAxisIsolated=false",
                ],
            },
            {
                "id": "client_observable_pre_accept_transition",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/server_expected_state_observable_proxy.json"),
                "facts": [
                    "omittedPreAcceptTransitionCount=0",
                    "transitionHasReplayableClientRepresentation=false",
                ],
            },
            {
                "id": "selected_contrast_exhausted_requires_cross_sample_inventory",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/server_internal_gap_evidence_inventory.json"),
                "facts": [
                    "runtimeTraceCount=157",
                    "jsTraceCount=36",
                    "collectorDecodeCount=17",
                    "cookieTimelineCount=11",
                    "multiSurfaceBrowserRunCount=10",
                    "recommendedNextIsOffline=true",
                ],
            },
            {
                "id": "cross_sample_client_visible_proxy",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/cross_sample_server_state_proxy_matrix.json"),
                "facts": [
                    "sampleCount=14",
                    "fullSuccessCount=4",
                    "nonFullSuccessCount=10",
                    "multiSurfaceSampleCount=10",
                    "candidateClientVisibleProxyCount=0",
                    "outcomeOnlySeparatorCount=1",
                    "readyForFreshExperiment=false",
                ],
            },
            {
                "id": "historical_no_browser_response_classes",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/historical_probe_response_class_matrix.json"),
                "facts": [
                    "directAttemptCount=30",
                    "firstFailureOverlapAttemptCount=5",
                    "seq5Seq6ComboProbeCount=38",
                    "allDirectReachBundlePow=true",
                    "allOverlapReachBundlePow=true",
                    "hasHistoricalNoBrowserSuccess0=false",
                    "seq5Seq6ComboSeq5FailureMinus1Count=32",
                    "readyForFreshExperiment=false",
                ],
            },
            {
                "id": "server_internal_unobserved_state_final_gap",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/server_internal_unobserved_state_final_gap.json"),
                "facts": [
                    "allLocalProxySearchesNegative=true",
                    "highValueUnminedReplayableSuccessNotFound=true",
                    "jsInternalReplayableClientTransitionNotFound=true",
                    "actionableFrontierNotFound=true",
                    "readyForFreshExperiment=false",
                    "goalComplete=false",
                ],
            },
            {
                "id": "completion_requirements",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json"),
                "facts": [
                    "requirementCount=7",
                    "provenCount=3",
                    "missingCount=2",
                    "notProvenCount=1",
                    "partiallyProvenCount=1",
                    "blockingRequirementCount=4",
                    "goalComplete=false",
                ],
            },
        ],
        "remainingBoundaries": [
            "collector server-internal or unobserved expected state",
        ],
        "currentDecision": {
            "readyForFreshExperiment": False,
            "reason": "T1 keeps C4 coupled, T2 keeps C5 as an independent 2x2 family, T3 finds no selected-contrast omitted pre-accept transition, cross-sample matrix finds candidateClientVisibleProxyCount=0 across 14 classifier samples, historical no-browser probes contain no oIIoIooo|0 despite repeated bundle POW and seq5 oIIoIooo|-1 classes, unmined local triage finds 14 success-signal files but replayableFreshNoBrowserSuccessEvidenceCount=0, JS internal candidate reduction finds replayableClientTransitionCandidateCount=0, actionable frontier audit finds actionableMissingArtifactCount=0, final gap audit sets allLocalProxySearchesNegative=true, and completion requirements audit shows 4 blocking requirements remain. Current local evidence leaves a server-internal/unobserved expected-state final gap.",
            "nextRecommendedArtifact": None,
            "nextRecommendedScript": None,
        },
        "checks": {
            "allArtifactsPresent": all(loaded[name] is not None for name in artifacts),
            "firstDivergenceAtFinalSeq5": ((loaded["first_decisive_divergence.json"] or {}).get("checks") or {}).get("firstDivergenceAtFinalSeq5") is True,
            "decodedJsonEqual": ((loaded["encoded_payload_pc_form_diff_map.json"] or {}).get("checks") or {}).get("decodedJsonEqual") is True,
            "requestHistoryOrderGapFalsified": ((loaded["request_history_coherence_gap.json"] or {}).get("checks") or {}).get("hasOrderGap") is False,
            "remainingVariantFamilyNotSingle": ((loaded["remaining_encoder_variant_build_matrix.json"] or {}).get("checks") or {}).get("variantFamilyNotSingle") is True,
            "outerTupleNoSingleFieldExperimentReady": ((loaded["outer_session_tuple_factorization.json"] or {}).get("checks") or {}).get("noSingleFieldExperimentReady") is True,
            "encoderSingleAxisNotIsolated": ((loaded["encoder_axis_equivalence.json"] or {}).get("checks") or {}).get("singleEncoderAxisIsolated") is False,
            "serverObservableProxyNotFound": ((loaded["server_expected_state_observable_proxy.json"] or {}).get("checks") or {}).get("transitionHasReplayableClientRepresentation") is False,
            "serverInternalGapInventoryReady": ((loaded["server_internal_gap_evidence_inventory.json"] or {}).get("checks") or {}).get("hasCandidateLocalEvidenceSources") is True,
            "serverInternalGapInventoryRecommendsOffline": ((loaded["server_internal_gap_evidence_inventory.json"] or {}).get("checks") or {}).get("recommendedNextIsOffline") is True,
            "crossSampleMatrixReady": ((loaded["cross_sample_server_state_proxy_matrix.json"] or {}).get("checks") or {}).get("hasAtLeastThreeFullSuccessSamples") is True,
            "crossSampleCandidateProxyNotFound": ((loaded["cross_sample_server_state_proxy_matrix.json"] or {}).get("checks") or {}).get("candidateClientVisibleProxyCount") == 0,
            "historicalProbeMatrixReady": ((loaded["historical_probe_response_class_matrix.json"] or {}).get("checks") or {}).get("directAttemptCount") == 30,
            "historicalProbeSuccess0NotFound": ((loaded["historical_probe_response_class_matrix.json"] or {}).get("checks") or {}).get("hasHistoricalNoBrowserSuccess0") is False,
            "unminedAuditRan": ((loaded["unmined_local_evidence_source_audit.json"] or {}).get("checks") or {}).get("highValueUnminedDirectoryCount") == 34,
            "highValueUnminedReplayableSuccessNotFound": ((loaded["high_value_unmined_evidence_triage.json"] or {}).get("checks") or {}).get("hasReplayableFreshNoBrowserSuccessEvidence") is False,
            "jsInternalTaxonomyRan": ((loaded["js_internal_event_taxonomy.json"] or {}).get("checks") or {}).get("sampleCount") == 14,
            "jsInternalReplayableTransitionNotFound": ((loaded["js_internal_candidate_reduction.json"] or {}).get("checks") or {}).get("replayableClientTransitionCandidateCount") == 0,
            "actionableFrontierNotFound": ((loaded["actionable_frontier_audit.json"] or {}).get("checks") or {}).get("actionableMissingArtifactCount") == 0,
            "serverInternalFinalGapReady": ((loaded["server_internal_unobserved_state_final_gap.json"] or {}).get("checks") or {}).get("allLocalProxySearchesNegative") is True,
            "serverInternalFinalGapGoalNotComplete": ((loaded["server_internal_unobserved_state_final_gap.json"] or {}).get("checks") or {}).get("goalComplete") is False,
            "completionRequirementsAuditReady": ((loaded["pure_protocol_completion_requirements_audit.json"] or {}).get("checks") or {}).get("requirementCount") == 7,
            "completionRequirementsBlockingRemain": ((loaded["pure_protocol_completion_requirements_audit.json"] or {}).get("checks") or {}).get("blockingRequirementCount", 0) > 0,
            "latestArtifactSaysReadyForFreshExperiment": ((loaded["server_expected_state_observable_proxy.json"] or {}).get("checks") or {}).get("readyForFreshExperiment") is True,
            "latestArtifactSaysNotReadyForFreshExperiment": ((loaded["server_expected_state_observable_proxy.json"] or {}).get("checks") or {}).get("readyForFreshExperiment") is False,
        },
    }
    status["checks"]["readyForFreshExperiment"] = False

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": status["checks"], "currentDecision": status["currentDecision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
