#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "server_internal_unobserved_state_final_gap.json"


INPUTS = {
    "serverExpectedStateObservableProxy": BASE / "server_expected_state_observable_proxy.json",
    "crossSampleServerStateProxyMatrix": BASE / "cross_sample_server_state_proxy_matrix.json",
    "historicalProbeResponseClassMatrix": BASE / "historical_probe_response_class_matrix.json",
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
    "outerSessionTupleFactorization": BASE / "outer_session_tuple_factorization.json",
    "encoderAxisEquivalence": BASE / "encoder_axis_equivalence.json",
    "collectorToRiskConsumptionChain": BASE / "collector_to_risk_consumption_chain.json",
    "unminedLocalEvidenceSourceAudit": BASE / "unmined_local_evidence_source_audit.json",
    "highValueUnminedEvidenceTriage": BASE / "high_value_unmined_evidence_triage.json",
    "jsInternalEventTaxonomy": BASE / "js_internal_event_taxonomy.json",
    "jsInternalCandidateReduction": BASE / "js_internal_candidate_reduction.json",
    "actionableFrontierAudit": BASE / "actionable_frontier_audit.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict[str, Any]:
    docs = {name: load_json(path) for name, path in INPUTS.items()}
    server_proxy = docs["serverExpectedStateObservableProxy"]
    cross_sample = docs["crossSampleServerStateProxyMatrix"]
    historical = docs["historicalProbeResponseClassMatrix"]
    single = docs["singleTransitionCandidateMatrix"]
    outer = docs["outerSessionTupleFactorization"]
    encoder = docs["encoderAxisEquivalence"]
    risk_chain = docs["collectorToRiskConsumptionChain"]
    unmined = docs["unminedLocalEvidenceSourceAudit"]
    triage = docs["highValueUnminedEvidenceTriage"]
    js_taxonomy = docs["jsInternalEventTaxonomy"]
    js_reduction = docs["jsInternalCandidateReduction"]
    frontier = docs["actionableFrontierAudit"]

    checks = {
        "selectedContrastHasNoReplayableProxy": (server_proxy.get("checks") or {}).get("transitionHasReplayableClientRepresentation") is False,
        "selectedContrastOmittedPreAcceptTransitionCount": (server_proxy.get("checks") or {}).get("omittedPreAcceptTransitionCount"),
        "singleTransitionCandidateCount": (single.get("summary") or {}).get("singleTransitionCandidateCount"),
        "outerTupleNoSingleFieldExperimentReady": (outer.get("checks") or {}).get("noSingleFieldExperimentReady") is True,
        "encoderSingleAxisNotIsolated": (encoder.get("checks") or {}).get("singleEncoderAxisIsolated") is False,
        "crossSampleCandidateClientVisibleProxyCount": (cross_sample.get("checks") or {}).get("candidateClientVisibleProxyCount"),
        "crossSampleHasEnoughSamples": (cross_sample.get("checks") or {}).get("hasAtLeastThreeFullSuccessSamples") is True
        and (cross_sample.get("checks") or {}).get("hasNonFullSuccessControls") is True,
        "historicalProbeHasNoBrowserSuccess0": (historical.get("checks") or {}).get("hasHistoricalNoBrowserSuccess0") is False,
        "historicalProbeHasNearSuccessFailureMinus1": (historical.get("checks") or {}).get("hasNearSuccessFailureMinus1Class") is True,
        "downstreamRiskChainProvenForAcceptedS00": (risk_chain.get("checks") or {}).get("riskContinueTokenFeedsCreateAccount") is True,
        "unminedEvidenceAuditRan": (unmined.get("checks") or {}).get("highValueUnminedDirectoryCount") is not None,
        "unminedEvidenceHadSuccessSignals": (unmined.get("checks") or {}).get("hasUnminedSuccessSignal") is True,
        "highValueUnminedTriageRan": (triage.get("checks") or {}).get("highValueUnminedDirectoryCount") is not None,
        "highValueUnminedReplayableSuccessNotFound": (triage.get("checks") or {}).get("hasReplayableFreshNoBrowserSuccessEvidence") is False,
        "jsInternalEventTaxonomyRan": (js_taxonomy.get("checks") or {}).get("featureCount") is not None,
        "jsInternalCandidateReductionRan": (js_reduction.get("checks") or {}).get("candidateCount") is not None,
        "jsInternalReplayableClientTransitionNotFound": (js_reduction.get("checks") or {}).get("replayableClientTransitionCandidateCount") == 0,
        "actionableFrontierAuditRan": (frontier.get("checks") or {}).get("nextArtifactRefCount") is not None,
        "actionableFrontierNotFound": (frontier.get("checks") or {}).get("actionableMissingArtifactCount") == 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    checks["allLocalProxySearchesNegative"] = (
        checks["selectedContrastHasNoReplayableProxy"] is True
        and checks["singleTransitionCandidateCount"] == 0
        and checks["crossSampleCandidateClientVisibleProxyCount"] == 0
        and checks["historicalProbeHasNoBrowserSuccess0"] is True
        and checks["highValueUnminedReplayableSuccessNotFound"] is True
        and checks["jsInternalReplayableClientTransitionNotFound"] is True
        and checks["actionableFrontierNotFound"] is True
    )

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Consolidate the current final gap after selected-contrast, cross-sample, and historical no-browser local evidence searches.",
        "inputs": {name: str(path.resolve()) for name, path in INPUTS.items()},
        "evidenceBlocks": [
            {
                "id": "selected_contrast",
                "evidence": str(INPUTS["serverExpectedStateObservableProxy"].resolve()),
                "facts": [
                    "omittedPreAcceptTransitionCount=0",
                    "transitionHasReplayableClientRepresentation=false",
                    "readyForFreshExperiment=false",
                ],
            },
            {
                "id": "single_transition_matrix",
                "evidence": str(INPUTS["singleTransitionCandidateMatrix"].resolve()),
                "facts": [
                    "singleTransitionCandidateCount=0",
                    "readyCandidateIds=[]",
                ],
            },
            {
                "id": "coupled_boundaries",
                "evidence": [
                    str(INPUTS["outerSessionTupleFactorization"].resolve()),
                    str(INPUTS["encoderAxisEquivalence"].resolve()),
                ],
                "facts": [
                    "outerTupleNoSingleFieldExperimentReady=true",
                    "encoderSingleAxisNotIsolated=true",
                ],
            },
            {
                "id": "cross_sample_browser_matrix",
                "evidence": str(INPUTS["crossSampleServerStateProxyMatrix"].resolve()),
                "facts": [
                    "sampleCount=14",
                    "fullSuccessCount=4",
                    "nonFullSuccessCount=10",
                    "candidateClientVisibleProxyCount=0",
                ],
            },
            {
                "id": "historical_no_browser_matrix",
                "evidence": str(INPUTS["historicalProbeResponseClassMatrix"].resolve()),
                "facts": [
                    "directAttemptCount=30",
                    "firstFailureOverlapAttemptCount=5",
                    "seq5Seq6ComboProbeCount=38",
                    "hasHistoricalNoBrowserSuccess0=false",
                    "seq5Seq6ComboSeq5FailureMinus1Count=32",
                ],
            },
            {
                "id": "downstream_not_root_cause",
                "evidence": str(INPUTS["collectorToRiskConsumptionChain"].resolve()),
                "facts": [
                    "accepted collector success feeds risk/verify",
                    "risk/verify state=continue feeds CreateAccount redirectUrl",
                    "selected fresh failures occur before this downstream chain exists",
                ],
            },
            {
                "id": "unmined_local_evidence_triage",
                "evidence": [
                    str(INPUTS["unminedLocalEvidenceSourceAudit"].resolve()),
                    str(INPUTS["highValueUnminedEvidenceTriage"].resolve()),
                ],
                "facts": [
                    "highValueUnminedDirectoryCount=34",
                    "classifiedSuccessSignalFileCount=14",
                    "replayableFreshNoBrowserSuccessEvidenceCount=0",
                    "hasReplayableFreshNoBrowserSuccessEvidence=false",
                ],
            },
            {
                "id": "js_internal_event_taxonomy_and_reduction",
                "evidence": [
                    str(INPUTS["jsInternalEventTaxonomy"].resolve()),
                    str(INPUTS["jsInternalCandidateReduction"].resolve()),
                ],
                "facts": [
                    "candidateNonOutcomeClientEventCount=8",
                    "replayableClientTransitionCandidateCount=0",
                    "powChallengeHandlerCandidateCount=4",
                    "cookieFlagHandlerCandidateCount=3",
                    "outcomeHandlerCandidateCount=1",
                ],
            },
            {
                "id": "actionable_frontier",
                "evidence": str(INPUTS["actionableFrontierAudit"].resolve()),
                "facts": [
                    "nextArtifactRefCount=44",
                    "completedFrontierRefCount=40",
                    "actionableMissingArtifactCount=0",
                    "terminalAuthorityNextNull=true",
                ],
            },
        ],
        "remainingGap": {
            "id": "collector_server_internal_or_unobserved_expected_state",
            "status": "not_reduced_to_replayable_client_transition",
            "whatIsProven": (
                "Current local evidence proves the accepted-browser downstream chain and proves that decoded semantics, request order, "
                "single outer/session fields, single encoder axes, selected-contrast visible transitions, cross-sample visible proxies, "
                "and historical no-browser response classes do not yield a ready fresh-session experiment."
                " Additional unmined local evidence triage found 14 success-signal files outside the prior final gap, "
                "but none is classified as replayable fresh no-browser success evidence."
                " JS internal event taxonomy found 8 apparent non-outcome separators, but reduction maps them to POW challenge handlers, "
                "collector cookie/config flags, or outcome handling, with replayableClientTransitionCandidateCount=0."
                " Actionable frontier audit found no missing nextArtifact path and terminal authority artifacts point to null next steps."
            ),
            "whatIsMissing": (
                "A concrete client-visible request/handler transition that maps the collector's server-expected state into a replayable pure-protocol input "
                "for producing oIIoIooo|0 in a fresh no-browser session."
            ),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "The end-to-end pure protocol PoC is still missing; current local evidence leaves only a non-replayable server-internal/unobserved expected-state gap.",
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
