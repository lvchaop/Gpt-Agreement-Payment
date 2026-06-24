#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
GOAL = PROTO / "goal_audit"
OUT = HYP / "exhaustive_promotion_candidate_resolution_audit.json"

INPUTS = {
    "nearestMiss": HYP / "nearest_miss_promotion_candidate_audit.json",
    "nearestMissBlockerResolution": HYP / "nearest_miss_blocker_resolution_audit.json",
    "remainingNearestMissResolution": HYP / "remaining_nearest_miss_resolution_audit.json",
    "promotionPredicateBlocker": HYP / "promotion_predicate_blocker_crosswalk.json",
    "candidateSourceContradictionLedger": HYP / "candidate_source_contradiction_ledger.json",
    "candidateExecutorReadiness": HYP / "candidate_executor_readiness_audit.json",
    "hypothesisTreeCurrentAuthority": HYP / "hypothesis_tree_current_authority_audit.json",
    "remainingBoundaryProposalGate": HYP / "remaining_boundary_proposal_gate_audit.json",
    "singleTransitionCandidateMatrix": HYP / "single_transition_candidate_matrix.json",
    "browserServerVisibleDiff": HYP / "browser_success_chain_server_visible_diff_audit.json",
    "browserPayloadPcSessionLineage": HYP / "browser_success_payload_pc_session_lineage_audit.json",
    "collectorResponseHandlerValueLineage": HYP / "collector_response_handler_value_lineage_audit.json",
    "resetHookFeatureCandidateReduction": PROTO / "reset_plan/reset_hook_feature_candidate_reduction.json",
    "encoderAxisEquivalence": HYP / "encoder_axis_equivalence.json",
    "encodedSessionBinding": HYP / "encoded_session_binding_candidate_audit.json",
    "cleanPayloadPcControls": GOAL / "clean_history_payload_pc_controls_audit.json",
    "forcedOverlapPayloadPcSplit": GOAL / "forced_overlap_payload_pc_split_control_audit.json",
    "browserCookieBridge": HYP / "browser_cookie_bridge_candidate_audit.json",
    "line922CandidateReduction": HYP / "line922_candidate_reduction.json",
    "encodedPayloadPcFormDiff": HYP / "encoded_payload_pc_form_diff_map.json",
    "requestHistoryCoherence": HYP / "request_history_coherence_gap.json",
    "serverStateValueToRequestLineage": HYP / "server_state_value_to_request_lineage.json",
    "serverObservableStateInventory": HYP / "server_observable_state_inventory.json",
    "coupledEncoderVariant": HYP / "coupled_encoder_variant_audit.json",
    "remainingEncoderVariantBuildMatrix": HYP / "remaining_encoder_variant_build_matrix.json",
    "bridgeToPayloadContext": HYP / "bridge_to_payload_context_audit.json",
    "collectorToRiskConsumptionChain": HYP / "collector_to_risk_consumption_chain.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def evidence(*keys: str) -> list[str]:
    return [str(INPUTS[key]) for key in keys]


def norm_id(row: dict[str, Any]) -> str:
    rid = row.get("id")
    if rid:
        return str(rid)
    title = row.get("title")
    source = row.get("source")
    return f"{source}:{title}"


def top10_ids(nearest_doc: dict[str, Any]) -> set[str]:
    return {norm_id(row) for row in nearest_doc.get("nearestRows") or []}


def build_closure_map(docs: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    c_encoder = checks(docs["encoderAxisEquivalence"])
    c_encoded = checks(docs["encodedSessionBinding"])
    c_clean = checks(docs["cleanPayloadPcControls"])
    c_split = checks(docs["forcedOverlapPayloadPcSplit"])
    c_cookie = checks(docs["browserCookieBridge"])
    c_line922 = checks(docs["line922CandidateReduction"])
    c_encoded_form = checks(docs["encodedPayloadPcFormDiff"])
    c_order = checks(docs["requestHistoryCoherence"])
    c_lineage = checks(docs["serverStateValueToRequestLineage"])
    c_inventory = checks(docs["serverObservableStateInventory"])
    c_coupled_encoder = checks(docs["coupledEncoderVariant"])
    c_build = checks(docs["remainingEncoderVariantBuildMatrix"])
    c_bridge = checks(docs["bridgeToPayloadContext"])
    c_risk = checks(docs["collectorToRiskConsumptionChain"])
    c_remaining_gate = checks(docs["remainingBoundaryProposalGate"])
    c_single = checks(docs["singleTransitionCandidateMatrix"])
    c_server_diff = checks(docs["browserServerVisibleDiff"])
    c_payload_lineage = checks(docs["browserPayloadPcSessionLineage"])
    c_handler_lineage = checks(docs["collectorResponseHandlerValueLineage"])
    c_reset = checks(docs["resetHookFeatureCandidateReduction"])
    c_source = checks(docs["candidateSourceContradictionLedger"])
    c_promotion = checks(docs["promotionPredicateBlocker"])
    c_executor = checks(docs["candidateExecutorReadiness"])
    c_hypothesis = checks(docs["hypothesisTreeCurrentAuthority"])

    closure: dict[str, dict[str, Any]] = {
        "pc_value": {
            "status": "closedByExistingControls",
            "reason": "pc alone is eliminated; remaining accepted-shape family is payload/pc/session coupled, not one transition.",
            "evidence": evidence("encoderAxisEquivalence", "encodedSessionBinding", "cleanPayloadPcControls", "forcedOverlapPayloadPcSplit"),
            "facts": {
                "pcUuidSourceDeterminesPc": c_encoder.get("pcUuidSourceDeterminesPc"),
                "singleEncoderAxisIsolated": c_encoder.get("singleEncoderAxisIsolated"),
                "pcAloneEliminated": c_encoded.get("pcAloneEliminated"),
                "remainingDiffKeysArePayloadPcSession": c_encoded.get("remainingDiffKeysArePayloadPcSession"),
                "exactPayloadPcReturnedDoEmpty": c_clean.get("exactPayloadPcReturnedDoEmpty"),
                "seq5NoOIIoIooo": c_split.get("seq5NoOIIoIooo"),
            },
            "closed": (
                c_encoder.get("pcUuidSourceDeterminesPc") is True
                and c_encoder.get("singleEncoderAxisIsolated") is False
                and c_encoded.get("pcAloneEliminated") is True
                and c_encoded.get("remainingDiffKeysArePayloadPcSession") is True
                and c_clean.get("exactPayloadPcReturnedDoEmpty") is True
                and c_split.get("seq5NoOIIoIooo") is True
            ),
        },
        "collector_cookie_header": {
            "status": "closedByExistingControls",
            "reason": "known primary collector flow has no Cookie header; observed Cookie headers are beacon/telemetry or contradicted controls.",
            "evidence": evidence("browserServerVisibleDiff", "browserCookieBridge", "singleTransitionCandidateMatrix"),
            "facts": {
                "earliestServerVisibleDiffCount": c_server_diff.get("earliestServerVisibleDiffCount"),
                "contradictedDiffCount": c_server_diff.get("contradictedDiffCount"),
                "primaryCollectorCookieHeaderObservedRunCount": c_cookie.get("primaryCollectorCookieHeaderObservedRunCount"),
                "allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader": c_cookie.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader"),
                "collectorCookieHeadersOnlyOnBeaconOrTelemetry": c_cookie.get("collectorCookieHeadersOnlyOnBeaconOrTelemetry"),
                "noReadySingleTransitionCandidate": c_single.get("noReadySingleTransitionCandidate"),
            },
            "closed": (
                c_cookie.get("primaryCollectorCookieHeaderObservedRunCount") == 0
                and c_cookie.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader") is True
                and c_cookie.get("collectorCookieHeadersOnlyOnBeaconOrTelemetry") is True
                and c_single.get("noReadySingleTransitionCandidate") is True
            ),
        },
        "RB4_collector_success_to_risk_verify": {
            "status": "closedByExistingControls",
            "reason": "collector success to risk/verify is downstream/post-accept consumption, not the accept-causing transition.",
            "evidence": evidence("collectorToRiskConsumptionChain"),
            "facts": {
                "riskContinueTokenFeedsCreateAccount": c_risk.get("riskContinueTokenFeedsCreateAccount"),
                "line933DivergenceIsAccepted": c_risk.get("line933DivergenceIsAccepted"),
            },
            "closed": c_risk.get("riskContinueTokenFeedsCreateAccount") is True and c_risk.get("line933DivergenceIsAccepted") is True,
        },
        "C8_collector_success_to_risk_verify": {
            "status": "closedByExistingControls",
            "reason": "collector success to risk/verify is downstream/post-accept consumption, not the accept-causing transition.",
            "evidence": evidence("collectorToRiskConsumptionChain"),
            "facts": {
                "riskContinueTokenFeedsCreateAccount": c_risk.get("riskContinueTokenFeedsCreateAccount"),
                "successEntryHasChallengeSuccess0": c_risk.get("successEntryHasChallengeSuccess0"),
            },
            "closed": c_risk.get("riskContinueTokenFeedsCreateAccount") is True and c_risk.get("successEntryHasChallengeSuccess0") is True,
        },
        "C1_decoded_line922_activity_fields": {
            "status": "closedByExistingControls",
            "reason": "decoded line922 activity fields are equal at the relevant boundary; exact payload/pc control exists.",
            "evidence": evidence("line922CandidateReduction"),
            "facts": {
                "decodedActivityFieldsEqual": c_line922.get("decodedActivityFieldsEqual"),
                "exactPayloadPcControlExists": c_line922.get("exactPayloadPcControlExists"),
            },
            "closed": c_line922.get("decodedActivityFieldsEqual") is True and c_line922.get("exactPayloadPcControlExists") is True,
        },
        "C2_request_history_order": {
            "status": "closedByExistingControls",
            "reason": "request history order gap is falsified; final divergence remains seq5.",
            "evidence": evidence("requestHistoryCoherence"),
            "facts": {
                "hasOrderGap": c_order.get("hasOrderGap"),
                "finalDivergenceStillSeq5": c_order.get("finalDivergenceStillSeq5"),
            },
            "closed": c_order.get("hasOrderGap") is False and c_order.get("finalDivergenceStillSeq5") is True,
        },
        "C3_static_payload_pc_transplant": {
            "status": "closedByExistingControls",
            "reason": "static payload/pc transplant exists but was rejected by payload/pc split controls.",
            "evidence": evidence("encodedPayloadPcFormDiff", "serverStateValueToRequestLineage"),
            "facts": {
                "staticPayloadPcControlExists": c_encoded_form.get("staticPayloadPcControlExists"),
                "payloadPcSplitControlRejected": c_lineage.get("payloadPcSplitControlRejected"),
            },
            "closed": c_encoded_form.get("staticPayloadPcControlExists") is True and c_lineage.get("payloadPcSplitControlRejected") is True,
        },
        "C4_outer_session_tuple": {
            "status": "closedByExistingControls",
            "reason": "outer session tuple is a coupled boundary; controls rejected isolated binding and final consumed fields all differ.",
            "evidence": evidence("serverStateValueToRequestLineage", "serverObservableStateInventory"),
            "facts": {
                "hasOuterSessionTupleBoundary": c_lineage.get("hasOuterSessionTupleBoundary"),
                "outerBindingControlsRejected": c_lineage.get("outerBindingControlsRejected"),
                "finalConsumedFieldsAllDiffer": c_inventory.get("finalConsumedFieldsAllDiffer"),
            },
            "closed": (
                c_lineage.get("hasOuterSessionTupleBoundary") is True
                and c_lineage.get("outerBindingControlsRejected") is True
                and c_inventory.get("finalConsumedFieldsAllDiffer") is True
            ),
        },
        "C5_pc_marker_uuid_encoder_binding": {
            "status": "closedByExistingControls",
            "reason": "encoder binding remains a variant family, not a single promoted transition.",
            "evidence": evidence("coupledEncoderVariant", "remainingEncoderVariantBuildMatrix"),
            "facts": {
                "singleRecommendedVariant": c_coupled_encoder.get("singleRecommendedVariant"),
                "variantFamilyNotSingle": c_build.get("variantFamilyNotSingle"),
            },
            "closed": c_coupled_encoder.get("singleRecommendedVariant") is False and c_build.get("variantFamilyNotSingle") is True,
        },
        "C7_parent_bridge_cookie_header": {
            "status": "closedByExistingControls",
            "reason": "parent bridge is not a collector Cookie-header transition; decoded payload was already equal.",
            "evidence": evidence("bridgeToPayloadContext"),
            "facts": {
                "line933NoCookieHeader": c_bridge.get("line933NoCookieHeader"),
                "freshSeq5NoCookieHeader": c_bridge.get("freshSeq5NoCookieHeader"),
                "decodedPayloadAlreadyEqual": c_bridge.get("decodedPayloadAlreadyEqual"),
            },
            "closed": (
                c_bridge.get("line933NoCookieHeader") is True
                and c_bridge.get("freshSeq5NoCookieHeader") is True
                and c_bridge.get("decodedPayloadAlreadyEqual") is True
            ),
        },
    }

    source_closures = {
        "remainingBoundaryProposalGate": {
            "status": "closedByExistingControls",
            "reason": "remaining boundary proposal gate has zero proposal-ready rows and is already covered by candidate-source contradiction ledger.",
            "evidence": evidence("remainingBoundaryProposalGate", "candidateSourceContradictionLedger"),
            "facts": {
                "proposalReadyRowCount": c_remaining_gate.get("proposalReadyRowCount"),
                "gateReadyCount": c_source.get("gateReadyCount"),
                "allCandidateSourcesClosed": c_source.get("allCandidateSourcesClosed"),
            },
            "closed": (
                c_remaining_gate.get("proposalReadyRowCount") in {None, 0}
                and c_source.get("gateReadyCount") == 0
                and c_source.get("allCandidateSourcesClosed") is True
            ),
        },
        "singleTransitionCandidateMatrix": {
            "status": "closedByExistingControls",
            "reason": "single-transition matrix has no ready transition; no candidate can be promoted from this source.",
            "evidence": evidence("singleTransitionCandidateMatrix", "candidateSourceContradictionLedger"),
            "facts": {
                "noReadySingleTransitionCandidate": c_single.get("noReadySingleTransitionCandidate"),
                "matrixReadyCount": c_source.get("matrixReadyCount"),
                "allCandidateSourcesClosed": c_source.get("allCandidateSourcesClosed"),
            },
            "closed": c_single.get("noReadySingleTransitionCandidate") is True and c_source.get("matrixReadyCount") == 0,
        },
        "browserSuccessChainServerVisibleDiff": {
            "status": "closedByExistingControls",
            "reason": "server-visible diff rows are contradicted and produced no proposal-ready transition.",
            "evidence": evidence("browserServerVisibleDiff", "candidateSourceContradictionLedger"),
            "facts": {
                "earliestServerVisibleDiffCount": c_server_diff.get("earliestServerVisibleDiffCount"),
                "contradictedDiffCount": c_server_diff.get("contradictedDiffCount"),
                "proposalCandidateCount": c_server_diff.get("proposalCandidateCount"),
                "allCandidateSourcesClosed": c_source.get("allCandidateSourcesClosed"),
            },
            "closed": (
                c_server_diff.get("proposalCandidateCount") in {None, 0}
                and c_server_diff.get("contradictedDiffCount") == c_server_diff.get("earliestServerVisibleDiffCount")
            ),
        },
        "browserPayloadPcSessionLineage": {
            "status": "closedByExistingControls",
            "reason": "payload/pc/session lineage rows are contradicted and do not isolate a single transition.",
            "evidence": evidence("browserPayloadPcSessionLineage"),
            "facts": {
                "fieldLineageRowCount": c_payload_lineage.get("fieldLineageRowCount"),
                "fieldLineageContradictedCount": c_payload_lineage.get("fieldLineageContradictedCount"),
                "proposalCandidateCount": c_payload_lineage.get("proposalCandidateCount"),
            },
            "closed": (
                c_payload_lineage.get("proposalCandidateCount") in {None, 0}
                and c_payload_lineage.get("fieldLineageContradictedCount") == c_payload_lineage.get("fieldLineageRowCount")
            ),
        },
        "collectorResponseHandlerValueLineage": {
            "status": "closedByExistingControls",
            "reason": "collector response handler/value lineage did not produce a proposal-ready pre-accept transition.",
            "evidence": evidence("collectorResponseHandlerValueLineage"),
            "facts": {
                "valueLineageRowCount": c_handler_lineage.get("valueLineageRowCount"),
                "proposalCandidateCount": c_handler_lineage.get("proposalCandidateCount"),
                "readyForFreshExperiment": c_handler_lineage.get("readyForFreshExperiment"),
            },
            "closed": c_handler_lineage.get("proposalCandidateCount") in {None, 0} and c_handler_lineage.get("readyForFreshExperiment") is not True,
        },
        "resetHookFeatureCandidateReduction": {
            "status": "closedByExistingControls",
            "reason": "reset hook feature reduction has no promoted single transition and no fresh experiment readiness.",
            "evidence": evidence("resetHookFeatureCandidateReduction"),
            "facts": {
                "promotedSingleTransitionCandidateCount": c_reset.get("promotedSingleTransitionCandidateCount"),
                "readyForFreshExperiment": c_reset.get("readyForFreshExperiment"),
            },
            "closed": c_reset.get("promotedSingleTransitionCandidateCount") in {None, 0} and c_reset.get("readyForFreshExperiment") is not True,
        },
    }

    generic_negative_gate = {
        "status": "closedByExistingControls",
        "reason": "candidate source is closed by contradiction/intake ledgers and the global promotion gate has no ready candidate.",
        "evidence": evidence("promotionPredicateBlocker", "candidateSourceContradictionLedger", "candidateExecutorReadiness", "hypothesisTreeCurrentAuthority"),
        "facts": {
            "allCandidateSourcesClosed": c_source.get("allCandidateSourcesClosed"),
            "unsatisfiedPromotionPredicateCount": c_promotion.get("unsatisfiedPromotionPredicateCount"),
            "executorReadyForPromotedCandidate": c_executor.get("executorReadyForPromotedCandidate"),
            "oldPlanNoLongerAuthorizesPhase5": c_hypothesis.get("oldPlanNoLongerAuthorizesPhase5"),
            "readyForFreshExperiment": c_promotion.get("readyForFreshExperiment"),
        },
        "closed": (
            c_source.get("allCandidateSourcesClosed") is True
            and c_promotion.get("unsatisfiedPromotionPredicateCount", 0) > 0
            and c_executor.get("executorReadyForPromotedCandidate") is False
            and c_hypothesis.get("oldPlanNoLongerAuthorizesPhase5") is True
        ),
    }

    closure["_by_source"] = source_closures
    closure["_generic"] = generic_negative_gate
    return closure


def resolve_row(row: dict[str, Any], closure_map: dict[str, dict[str, Any]], top_ids: set[str]) -> dict[str, Any]:
    candidate_id = norm_id(row)
    specific = closure_map.get(candidate_id)
    source_specific = (closure_map.get("_by_source") or {}).get(row.get("source"))
    closure = specific or source_specific or closure_map["_generic"]
    closed = closure.get("closed") is True
    proposal_ready = row.get("proposalReady") is True and not row.get("missingPredicates")
    if proposal_ready:
        status = "proposalReady"
    elif closed:
        status = closure["status"]
    else:
        status = "openNeedsSpecificEvidence"

    return {
        "candidateId": candidate_id,
        "source": row.get("source"),
        "title": row.get("title"),
        "inNearestTop10": candidate_id in top_ids,
        "satisfiedPredicateCount": row.get("satisfiedPredicateCount"),
        "missingPredicates": row.get("missingPredicates") or [],
        "resolutionStatus": status,
        "closureReason": closure.get("reason") if closed else None,
        "closureFacts": closure.get("facts") or {},
        "evidencePaths": closure.get("evidence") or row.get("evidence") or [],
        "nextMinimalFact": None if status != "openNeedsSpecificEvidence" else "Map this candidate to a concrete local control that resolves its missing predicates without a fresh network attempt.",
    }


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    nearest_doc = docs["nearestMiss"]
    all_rows = nearest_doc.get("allRows") or []
    if not all_rows:
        all_rows = nearest_doc.get("nearestRows") or []
    closure_map = build_closure_map(docs)
    top_ids = top10_ids(nearest_doc)

    rows = [resolve_row(row, closure_map, top_ids) for row in all_rows]
    proposal_ready_rows = [row for row in rows if row["resolutionStatus"] == "proposalReady"]
    open_rows = [row for row in rows if row["resolutionStatus"] == "openNeedsSpecificEvidence"]
    closed_rows = [row for row in rows if row["resolutionStatus"] == "closedByExistingControls"]

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "candidateRowCount": len(rows),
        "nearestMissAllRowCount": checks(nearest_doc).get("allRowCount"),
        "resolvedCandidateCount": len(closed_rows) + len(proposal_ready_rows),
        "closedByExistingControlsCount": len(closed_rows),
        "openNeedsSpecificEvidenceCount": len(open_rows),
        "proposalReadyCandidateCount": len(proposal_ready_rows),
        "top10CandidateCount": len(top_ids),
        "top10ResolvedCandidateCount": sum(1 for row in rows if row["inNearestTop10"] and row["resolutionStatus"] != "openNeedsSpecificEvidence"),
        "nonTop10CandidateCount": sum(1 for row in rows if not row["inNearestTop10"]),
        "nonTop10OpenCandidateCount": sum(1 for row in open_rows if not row["inNearestTop10"]),
        "nonTop10ProposalReadyCandidateCount": sum(1 for row in proposal_ready_rows if not row["inNearestTop10"]),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Resolve the full current promotion-candidate set, not only the nearest top10, so execution is not biased by stale ranking or single-signal evidence.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "rows": rows,
        "openNeedsSpecificEvidenceRows": open_rows,
        "proposalReadyRows": proposal_ready_rows,
        "unresolvedCandidateIds": [row["candidateId"] for row in open_rows],
        "proposalReadyCandidateIds": [row["candidateId"] for row in proposal_ready_rows],
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": (
                None
                if not open_rows and not proposal_ready_rows
                else "output/protocol_reverse/hypothesis_reframe/<candidate_id>_minimal_fact_audit.json"
            ),
            "nextScript": (
                None
                if not open_rows and not proposal_ready_rows
                else "tools/build_<candidate_id>_minimal_fact_audit.py"
            ),
            "reason": (
                "All current promotion-candidate rows are closed by existing local controls; no fresh network experiment is authorized."
                if not open_rows and not proposal_ready_rows
                else "Some candidate rows remain open or proposal-ready and must be handled before any fresh network experiment."
            ),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "openRows": open_rows[:5]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
