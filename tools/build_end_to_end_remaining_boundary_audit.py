#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOAL = ROOT / "output/protocol_reverse/goal_audit"
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
OUT = HYP / "end_to_end_remaining_boundary_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"


INPUTS = {
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "constructorSpec": GOAL / "s00_success_constructor_spec_audit.json",
    "sessionStateBoundary": GOAL / "s00_success_session_state_boundary_audit.json",
    "freshStateParamSources": GOAL / "s00_fresh_state_param_sources_audit.json",
    "h2StrongestFreshTail": GOAL / "h2_fresh_tail_strongest_control_audit.json",
    "h2FreshTailOnly": GOAL / "h2_fresh_tail_only_control_audit.json",
    "h2FreshTailInnerUuid": GOAL / "h2_fresh_tail_inner_uuid_control_audit.json",
    "h2InnerUuidOnly": GOAL / "h2_inner_uuid_binding_control_audit.json",
    "h2FreshStackOnly": GOAL / "h2_fresh_stack_only_control_audit.json",
    "h2DualActivityEqual": GOAL / "h2_dual_activity_equal_control_audit.json",
    "h2FirstFailureDualActivity": GOAL / "h2_first_failure_dual_activity_control_audit.json",
    "h2FirstFailureHeadDelay": GOAL / "h2_first_failure_head_delay_control_audit.json",
    "assetLineageCombo": GOAL / "asset_lineage_combo_control_audit.json",
    "encodedBoundary": GOAL / "latest_asset_lineage_encoded_boundary_audit.json",
    "exactPayloadBodyControls": GOAL / "latest_exact_payload_body_controls_audit.json",
    "cookieSessionLineage": GOAL / "cookie_session_lineage_gap_audit.json",
    "sendBeaconBoundary": GOAL / "sendbeacon_temporal_boundary_audit.json",
    "crclduBoundary": GOAL / "crcldu_sync_message_boundary_audit.json",
    "proofRepro": HYP / "proof_script_reproducibility_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def goal_missing(doc: dict[str, Any]) -> bool:
    summary = doc.get("summary") or {}
    return "end_to_end_pure_protocol_poc" in (summary.get("blockingOrMissing") or [])


def fact(name: str, key: str, docs: dict[str, dict[str, Any]]) -> Any:
    return checks(docs[name]).get(key)


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    c = {name: checks(doc) for name, doc in docs.items()}

    eliminated = [
        {
            "id": "pow_wasm_tail_correctness",
            "status": "not_sufficient_alone",
            "evidence": str(INPUTS["h2FreshTailOnly"]),
            "facts": {
                "usesFreshTailOnly": fact("h2FreshTailOnly", "usesFreshTailOnly", docs),
                "onlyPowWasmTailDiffVsS00": fact("h2FreshTailOnly", "onlyPowWasmTailDiffVsS00", docs),
                "stillRejected": fact("h2FreshTailOnly", "stillRejected", docs),
            },
        },
        {
            "id": "pow_wasm_tail_plus_inner_uuid",
            "status": "not_sufficient_as_pair",
            "evidence": str(INPUTS["h2FreshTailInnerUuid"]),
            "facts": {
                "usesFreshTailAndFreshInnerUuid": fact("h2FreshTailInnerUuid", "usesFreshTailAndFreshInnerUuid", docs),
                "onlyTailAndInnerUuidDiffVsS00": fact("h2FreshTailInnerUuid", "onlyTailAndInnerUuidDiffVsS00", docs),
                "stillRejected": fact("h2FreshTailInnerUuid", "stillRejected", docs),
            },
        },
        {
            "id": "inner_outer_uuid_binding",
            "status": "not_sufficient_alone",
            "evidence": str(INPUTS["h2InnerUuidOnly"]),
            "facts": {
                "onlyPx561InnerUuidDiffVsS00": fact("h2InnerUuidOnly", "onlyPx561InnerUuidDiffVsS00", docs),
                "stillRejected": fact("h2InnerUuidOnly", "stillRejected", docs),
            },
        },
        {
            "id": "stack_freshness",
            "status": "not_sufficient_alone",
            "evidence": str(INPUTS["h2FreshStackOnly"]),
            "facts": {
                "usesFreshProbeStackOnly": fact("h2FreshStackOnly", "usesFreshProbeStackOnly", docs),
                "onlyStackDiffVsS00": fact("h2FreshStackOnly", "onlyStackDiffVsS00", docs),
                "stillRejected": fact("h2FreshStackOnly", "stillRejected", docs),
            },
        },
        {
            "id": "decoded_seq5_seq6_activity_equality",
            "status": "not_sufficient",
            "evidence": str(INPUTS["h2DualActivityEqual"]),
            "facts": {
                "seq5WholeActivitiesEqualS00Line922": fact("h2DualActivityEqual", "seq5WholeActivitiesEqualS00Line922", docs),
                "seq6WholeActivityEqualS00Line925": fact("h2DualActivityEqual", "seq6WholeActivityEqualS00Line925", docs),
                "h2SingleSession": fact("h2DualActivityEqual", "h2SingleSession", docs),
                "seq6ResponseFirst": fact("h2DualActivityEqual", "seq6ResponseFirst", docs),
                "stillRejected": fact("h2DualActivityEqual", "stillRejected", docs),
            },
        },
        {
            "id": "first_failure_history_plus_head_delay",
            "status": "not_sufficient",
            "evidence": str(INPUTS["h2FirstFailureHeadDelay"]),
            "facts": {
                "firstFailureHistoryIncludedAndStateUpdated": fact("h2FirstFailureHeadDelay", "firstFailureHistoryIncludedAndStateUpdated", docs),
                "captchaHeadDelayApplied": fact("h2FirstFailureHeadDelay", "captchaHeadDelayApplied", docs),
                "stillRejected": fact("h2FirstFailureHeadDelay", "stillRejected", docs),
            },
        },
        {
            "id": "asset_lineage_preloads",
            "status": "not_sufficient",
            "evidence": str(INPUTS["assetLineageCombo"]),
            "facts": {
                "preStkNsOk": fact("assetLineageCombo", "preStkNsOk", docs),
                "preCaptchaGetOk": fact("assetLineageCombo", "preCaptchaGetOk", docs),
                "preIframeGetOk": fact("assetLineageCombo", "preIframeGetOk", docs),
                "preMainGetOk": fact("assetLineageCombo", "preMainGetOk", docs),
                "stillRejected": fact("assetLineageCombo", "stillRejected", docs),
            },
        },
        {
            "id": "exact_payload_pc_or_exact_body_replay",
            "status": "not_sufficient",
            "evidence": str(INPUTS["exactPayloadBodyControls"]),
            "facts": {
                "exactPayloadPcReturnedDoEmpty": fact("exactPayloadBodyControls", "exactPayloadPcReturnedDoEmpty", docs),
                "exactPayloadPcNoSuccess": fact("exactPayloadBodyControls", "exactPayloadPcNoSuccess", docs),
                "exactBodyRejectedMinusOne": fact("exactPayloadBodyControls", "exactBodyRejectedMinusOne", docs),
                "exactBodyNoSuccess": fact("exactPayloadBodyControls", "exactBodyNoSuccess", docs),
            },
        },
        {
            "id": "sendbeacon_pre_success_requirement",
            "status": "contradicted_by_temporal_order",
            "evidence": str(INPUTS["sendBeaconBoundary"]),
            "facts": {
                "firstBeaconAfterFirstSuccessByJsLine": fact("sendBeaconBoundary", "firstBeaconAfterFirstSuccessByJsLine", docs),
                "firstBeaconAfterFirstSuccessByWallTime": fact("sendBeaconBoundary", "firstBeaconAfterFirstSuccessByWallTime", docs),
            },
        },
        {
            "id": "crcldu_direct_collector_network_transition",
            "status": "not_observed_as_network_transition",
            "evidence": str(INPUTS["crclduBoundary"]),
            "facts": {
                "hasPreSuccessCrclduMessages": fact("crclduBoundary", "hasPreSuccessCrclduMessages", docs),
                "noRuntimeCrclduRequestOrResponseRows": fact("crclduBoundary", "noRuntimeCrclduRequestOrResponseRows", docs),
            },
        },
    ]

    remaining_boundaries = [
        {
            "id": "encoded_payload_pc_session_server_state_binding",
            "status": "remaining_boundary_not_single_transition",
            "evidence": str(INPUTS["encodedBoundary"]),
            "facts": {
                "decodedActivitiesEqual": fact("encodedBoundary", "decodedActivitiesEqual", docs),
                "decodedFieldsEqual": fact("encodedBoundary", "decodedFieldsEqual", docs),
                "bodyLenEqual": fact("encodedBoundary", "bodyLenEqual", docs),
                "payloadLenEqual": fact("encodedBoundary", "payloadLenEqual", docs),
                "encodedPayloadDiffers": fact("encodedBoundary", "encodedPayloadDiffers", docs),
                "pcDiffers": fact("encodedBoundary", "pcDiffers", docs),
                "onlyPayloadPcAndSessionParamsDiffer": fact("encodedBoundary", "onlyPayloadPcAndSessionParamsDiffer", docs),
                "freshStillRejected": fact("encodedBoundary", "freshStillRejected", docs),
            },
            "whyNotPromoted": "The boundary is coupled: exact payload+pc and exact whole body controls both fail, so no isolated payload/pc/session-param transition is proven.",
        },
        {
            "id": "browser_parent_cookie_bridge_or_hidden_browser_state",
            "status": "remaining_observability_boundary_not_cause",
            "evidence": str(INPUTS["cookieSessionLineage"]),
            "facts": {
                "s00HasParentCookieBridgeBeforeSuccess": fact("cookieSessionLineage", "s00HasParentCookieBridgeBeforeSuccess", docs),
                "freshHasNoBrowserParentBridgeEvidence": fact("cookieSessionLineage", "freshHasNoBrowserParentBridgeEvidence", docs),
                "line933RequestHasNoCookieHeader": fact("cookieSessionLineage", "line933RequestHasNoCookieHeader", docs),
                "freshSeq5RequestHasNoCookieHeader": fact("cookieSessionLineage", "freshSeq5RequestHasNoCookieHeader", docs),
            },
            "whyNotPromoted": "The cookie bridge is observed in browser lineage, but collector requests have no Cookie header in both success and fresh failure; no request/cookie/risk mutation candidate is proven.",
        },
        {
            "id": "collector_server_side_expected_state",
            "status": "remaining_highest_level_boundary",
            "evidence": [
                str(INPUTS["h2FirstFailureHeadDelay"]),
                str(INPUTS["exactPayloadBodyControls"]),
                str(INPUTS["goalGap"]),
            ],
            "facts": {
                "decodedActivitiesEqualButRejected": fact("h2FirstFailureHeadDelay", "seq5WholeActivitiesEqualS00Line922", docs) is True
                and fact("h2FirstFailureHeadDelay", "stillRejected", docs) is True,
                "exactBodyReplayRejected": fact("exactPayloadBodyControls", "exactBodyRejectedMinusOne", docs),
                "endToEndPocMissing": goal_missing(docs["goalGap"]),
            },
            "whyNotPromoted": "This is a server-state boundary, not a client-visible, pure-protocol constructible single variable.",
        },
    ]

    promoted = [
        row
        for row in remaining_boundaries
        if row.get("status") == "promoted_single_transition_candidate"
    ]

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "eliminatedBoundaryCount": len(eliminated),
        "remainingBoundaryCount": len(remaining_boundaries),
        "promotedSingleTransitionCandidateCount": len(promoted),
        "decodedSeq5Seq6ActivityEqualityRejected": fact("h2DualActivityEqual", "stillRejected", docs) is True
        and fact("h2DualActivityEqual", "seq5WholeActivitiesEqualS00Line922", docs) is True
        and fact("h2DualActivityEqual", "seq6WholeActivityEqualS00Line925", docs) is True,
        "freshServerBoundTailStrongestRejected": fact("h2StrongestFreshTail", "stillRejected", docs) is True
        and fact("h2StrongestFreshTail", "usesFreshServerBoundTail", docs) is True,
        "exactPayloadPcAndExactBodyNoSuccess": fact("exactPayloadBodyControls", "exactPayloadPcNoSuccess", docs) is True
        and fact("exactPayloadBodyControls", "exactBodyNoSuccess", docs) is True,
        "encodedBoundaryStillCoupled": fact("encodedBoundary", "onlyPayloadPcAndSessionParamsDiffer", docs) is True
        and fact("encodedBoundary", "freshStillRejected", docs) is True,
        "cookieBridgeNotCookieHeader": fact("cookieSessionLineage", "line933RequestHasNoCookieHeader", docs) is True
        and fact("cookieSessionLineage", "freshSeq5RequestHasNoCookieHeader", docs) is True,
        "sendBeaconPostSuccess": fact("sendBeaconBoundary", "firstBeaconAfterFirstSuccessByWallTime", docs) is True,
        "crclduNoNetworkTransitionObserved": fact("crclduBoundary", "noRuntimeCrclduRequestOrResponseRows", docs) is True,
        "proofScriptsReproducible": fact("proofRepro", "allProofScriptsReproducible", docs) is True,
        "endToEndPureProtocolPocMissing": goal_missing(docs["goalGap"]),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Collapse the long end-to-end PoC gap narrative into eliminated boundaries, remaining coupled boundaries, and promotion status for the next fresh experiment gate.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "eliminatedBoundaries": eliminated,
        "remainingBoundaries": remaining_boundaries,
        "promotionGate": {
            "singleTransitionCandidateCount": len(promoted),
            "readyForFreshExperiment": False,
            "reason": "Remaining evidence boundaries are coupled payload/pc/session/server-state or browser-state observability boundaries; none is a concrete pre-accept, client-visible, pure-protocol constructible single transition.",
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextEvidenceNeeded": [
                "A runtime/static lineage proof that converts one remaining boundary into a specific request/cookie/risk field or state mutation.",
                "A negative-control-resistant candidate where only one pre-accept client-visible value changes and prior controls do not already contradict it.",
            ],
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "promotionGate": doc["promotionGate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
