#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
OUT = HYP / "collector_server_expected_state_boundary_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-forward-plan.md"

INPUTS = {
    "endToEndRemainingBoundary": HYP / "end_to_end_remaining_boundary_audit.json",
    "browserCookieBridgeCandidate": HYP / "browser_cookie_bridge_candidate_audit.json",
    "encodedSessionBindingCandidate": HYP / "encoded_session_binding_candidate_audit.json",
    "resetTerminalBoundary": RESET / "reset_terminal_boundary_audit.json",
    "currentRouteAuthority": HYP / "current_route_authority_audit.json",
    "recursiveEvidenceBlindspot": HYP / "recursive_evidence_blindspot_audit.json",
    "nonJsonEvidenceBlindspot": HYP / "non_json_evidence_blindspot_audit.json",
    "proofScriptReproducibility": HYP / "proof_script_reproducibility_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "latestExactPayloadBodyControls": GOAL / "latest_exact_payload_body_controls_audit.json",
    "h2FirstFailureHeadDelay": GOAL / "h2_first_failure_head_delay_control_audit.json",
    "latestAssetLineageEncodedBoundary": GOAL / "latest_asset_lineage_encoded_boundary_audit.json",
    "cookieSessionLineageGap": GOAL / "cookie_session_lineage_gap_audit.json",
    "pxCookieJarUpdater": ROOT / "output/protocol_reverse/cookie_jar/px_cookie_jar_updater_multi_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def c(docs: dict[str, dict[str, Any]], name: str, key: str) -> Any:
    return checks(docs[name]).get(key)


def goal_missing_end_to_end(doc: dict[str, Any]) -> bool:
    return "end_to_end_pure_protocol_poc" in (summary(doc).get("blockingOrMissing") or [])


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}

    request_mirrored = [
        {
            "id": "exact_payload_pc_control",
            "surface": "collector_request_payload_pc",
            "status": "mirrored_but_not_sufficient",
            "evidence": str(INPUTS["latestExactPayloadBodyControls"]),
            "facts": {
                "exactPayloadPcReturnedDoEmpty": c(docs, "latestExactPayloadBodyControls", "exactPayloadPcReturnedDoEmpty"),
                "exactPayloadPcNoSuccess": c(docs, "latestExactPayloadBodyControls", "exactPayloadPcNoSuccess"),
            },
        },
        {
            "id": "exact_body_replay_control",
            "surface": "collector_request_body",
            "status": "mirrored_but_not_sufficient",
            "evidence": str(INPUTS["latestExactPayloadBodyControls"]),
            "facts": {
                "exactBodyRejectedMinusOne": c(docs, "latestExactPayloadBodyControls", "exactBodyRejectedMinusOne"),
                "exactBodyNoSuccess": c(docs, "latestExactPayloadBodyControls", "exactBodyNoSuccess"),
            },
        },
        {
            "id": "decoded_seq5_seq6_activity_equality",
            "surface": "collector_decoded_activity",
            "status": "mirrored_but_not_sufficient",
            "evidence": str(INPUTS["h2FirstFailureHeadDelay"]),
            "facts": {
                "seq5WholeActivitiesEqualS00Line922": c(docs, "h2FirstFailureHeadDelay", "seq5WholeActivitiesEqualS00Line922"),
                "firstFailureHistoryIncludedAndStateUpdated": c(docs, "h2FirstFailureHeadDelay", "firstFailureHistoryIncludedAndStateUpdated"),
                "captchaHeadDelayApplied": c(docs, "h2FirstFailureHeadDelay", "captchaHeadDelayApplied"),
                "stillRejected": c(docs, "h2FirstFailureHeadDelay", "stillRejected"),
            },
        },
        {
            "id": "encoded_payload_pc_session_bundle",
            "surface": "collector_encoded_payload_pc_session_params",
            "status": "coupled_boundary_not_single_proxy",
            "evidence": str(INPUTS["latestAssetLineageEncodedBoundary"]),
            "facts": {
                "decodedActivitiesEqual": c(docs, "latestAssetLineageEncodedBoundary", "decodedActivitiesEqual"),
                "decodedFieldsEqual": c(docs, "latestAssetLineageEncodedBoundary", "decodedFieldsEqual"),
                "onlyPayloadPcAndSessionParamsDiffer": c(docs, "latestAssetLineageEncodedBoundary", "onlyPayloadPcAndSessionParamsDiffer"),
                "freshStillRejected": c(docs, "latestAssetLineageEncodedBoundary", "freshStillRejected"),
            },
        },
    ]

    cookie_mirrored = [
        {
            "id": "browser_parent_cookie_bridge",
            "surface": "parent_cookie_bridge_to_collector",
            "status": "observed_but_not_primary_collector_cookie_header",
            "evidence": str(INPUTS["browserCookieBridgeCandidate"]),
            "facts": {
                "cookieBridgeCorrelationAlsoPresentInTfFailures": c(docs, "browserCookieBridgeCandidate", "cookieBridgeCorrelationAlsoPresentInTfFailures"),
                "tfFailuresWithCookieBridgeNoParentSuccessCount": c(docs, "browserCookieBridgeCandidate", "tfFailuresWithCookieBridgeNoParentSuccessCount"),
                "allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader": c(docs, "browserCookieBridgeCandidate", "allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader"),
                "promotedSingleTransitionCandidateCount": c(docs, "browserCookieBridgeCandidate", "promotedSingleTransitionCandidateCount"),
            },
        },
        {
            "id": "cookie_session_lineage",
            "surface": "collector_request_cookie_header",
            "status": "mirrored_absence_in_success_and_fresh_failure",
            "evidence": str(INPUTS["cookieSessionLineageGap"]),
            "facts": {
                "line933RequestHasNoCookieHeader": c(docs, "cookieSessionLineageGap", "line933RequestHasNoCookieHeader"),
                "freshSeq5RequestHasNoCookieHeader": c(docs, "cookieSessionLineageGap", "freshSeq5RequestHasNoCookieHeader"),
            },
        },
    ]

    risk_verify_mirrored = [
        {
            "id": "px_cookie_jar_to_risk_verify",
            "surface": "_px_cookie_token_risk_verify",
            "status": "offline_rebuild_proved_but_not_collector_success",
            "evidence": str(INPUTS["pxCookieJarUpdater"]),
            "facts": {
                "anyRunProvesContinueRiskVerifyMatchesJar": c(docs, "pxCookieJarUpdater", "anyRunProvesContinueRiskVerifyMatchesJar"),
                "allOfflineJarHasPx3Pxde": c(docs, "pxCookieJarUpdater", "allOfflineJarHasPx3Pxde"),
                "anySuccess0": c(docs, "pxCookieJarUpdater", "anySuccess0"),
            },
        }
    ]

    negative_controls = [
        {
            "id": "encoded_session_single_axis_controls",
            "evidence": str(INPUTS["encodedSessionBindingCandidate"]),
            "facts": {
                "singleAxisRowCount": c(docs, "encodedSessionBindingCandidate", "singleAxisRowCount"),
                "singleAxisEliminatedCount": c(docs, "encodedSessionBindingCandidate", "singleAxisEliminatedCount"),
                "exactPayloadPcNoSuccess": c(docs, "encodedSessionBindingCandidate", "exactPayloadPcNoSuccess"),
                "exactBodyNoSuccess": c(docs, "encodedSessionBindingCandidate", "exactBodyNoSuccess"),
                "promotedSingleTransitionCandidateCount": c(docs, "encodedSessionBindingCandidate", "promotedSingleTransitionCandidateCount"),
            },
        },
        {
            "id": "end_to_end_boundary_controls",
            "evidence": str(INPUTS["endToEndRemainingBoundary"]),
            "facts": {
                "eliminatedBoundaryCount": c(docs, "endToEndRemainingBoundary", "eliminatedBoundaryCount"),
                "remainingBoundaryCount": c(docs, "endToEndRemainingBoundary", "remainingBoundaryCount"),
                "promotedSingleTransitionCandidateCount": c(docs, "endToEndRemainingBoundary", "promotedSingleTransitionCandidateCount"),
                "exactPayloadPcAndExactBodyNoSuccess": c(docs, "endToEndRemainingBoundary", "exactPayloadPcAndExactBodyNoSuccess"),
                "encodedBoundaryStillCoupled": c(docs, "endToEndRemainingBoundary", "encodedBoundaryStillCoupled"),
            },
        },
        {
            "id": "route_authority_and_blindspots",
            "evidence": [
                str(INPUTS["currentRouteAuthority"]),
                str(INPUTS["recursiveEvidenceBlindspot"]),
                str(INPUTS["nonJsonEvidenceBlindspot"]),
            ],
            "facts": {
                "currentPromotedSingleTransitionCandidateCount": c(docs, "currentRouteAuthority", "currentPromotedSingleTransitionCandidateCount"),
                "recursiveReplayableFreshNoBrowserSuccessEvidenceCount": c(docs, "recursiveEvidenceBlindspot", "replayableFreshNoBrowserSuccessEvidenceCount"),
                "nonJsonReplayableFreshNoBrowserSuccessEvidenceCount": c(docs, "nonJsonEvidenceBlindspot", "replayableFreshNoBrowserSuccessEvidenceCount"),
            },
        },
    ]

    unobservable_server_state = [
        {
            "id": "collector_server_side_expected_state",
            "status": "server_state_boundary_not_client_visible",
            "evidence": [
                str(INPUTS["endToEndRemainingBoundary"]),
                str(INPUTS["resetTerminalBoundary"]),
                str(INPUTS["goalGap"]),
            ],
            "facts": {
                "endToEndRemainingBoundaryCount": c(docs, "endToEndRemainingBoundary", "remainingBoundaryCount"),
                "resetSingleTransitionCandidateCount": c(docs, "resetTerminalBoundary", "singleTransitionCandidateCount"),
                "resetStateMachineClientVisibleProxyCount": c(docs, "resetTerminalBoundary", "stateMachineClientVisibleProxyCount"),
                "resetNoCurrentRouteToPhase5": c(docs, "resetTerminalBoundary", "noCurrentRouteToPhase5"),
                "goalMissingEndToEndPoc": goal_missing_end_to_end(docs["goalGap"]),
            },
            "whyNotPromoted": (
                "It names the remaining server expectation after request/cookie/risk-visible surfaces have been mirrored or contradicted. "
                "The current local evidence does not expose a pre-accept client-visible proxy that pure protocol can construct."
            ),
        }
    ]

    client_visible_proxy_found = 0
    promoted = 0
    all_inputs_exist = all(path.exists() for path in INPUTS.values())
    proof_reproducible = c(docs, "proofScriptReproducibility", "allProofScriptsReproducible") is True
    end_to_end_missing = goal_missing_end_to_end(docs["goalGap"])

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all_inputs_exist,
        "remainingBoundaryCount": c(docs, "endToEndRemainingBoundary", "remainingBoundaryCount"),
        "encodedSessionBoundaryPromotedCount": c(docs, "encodedSessionBindingCandidate", "promotedSingleTransitionCandidateCount"),
        "browserCookieBridgePromotedCount": c(docs, "browserCookieBridgeCandidate", "promotedSingleTransitionCandidateCount"),
        "collectorServerStateBoundaryExists": True,
        "clientVisibleProxyFoundCount": client_visible_proxy_found,
        "requestMirroredStateCount": len(request_mirrored),
        "cookieMirroredStateCount": len(cookie_mirrored),
        "riskVerifyMirroredStateCount": len(risk_verify_mirrored),
        "negativeControlCoveredStateCount": len(negative_controls),
        "unobservableServerStateCount": len(unobservable_server_state),
        "serverStateBoundaryNotClientVisible": True,
        "proofScriptsReproducible": proof_reproducible,
        "endToEndPureProtocolPocMissing": end_to_end_missing,
        "promotedSingleTransitionCandidateCount": promoted,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Audit the remaining collector server-side expected-state boundary after encoded/session and browser-cookie bridge candidates failed promotion.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "requestMirroredStates": request_mirrored,
        "cookieMirroredStates": cookie_mirrored,
        "riskVerifyMirroredStates": risk_verify_mirrored,
        "negativeControlCoveredStates": negative_controls,
        "unobservableServerStates": unobservable_server_state,
        "promotionGate": {
            "singleTransitionCandidateCount": promoted,
            "readyForFreshExperiment": False,
            "reason": (
                "All currently identified request/cookie/risk-visible surfaces are either mirrored and still rejected, "
                "covered by negative controls, or reduced to a coupled live server/session boundary. No client-visible "
                "pre-accept pure-protocol constructible proxy is promoted."
            ),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "Collector server expected state remains a non-client-visible boundary in current evidence; do not run fresh network experiments without a new promoted transition.",
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
