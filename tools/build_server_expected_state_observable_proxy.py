#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "server_expected_state_observable_proxy.json"

INPUTS = {
    "collectorStateTransitionDiff": BASE / "collector_state_transition_diff_s00_vs_fresh.json",
    "firstDecisiveDivergence": BASE / "first_decisive_divergence.json",
    "serverInternalStateGapAudit": BASE / "server_internal_state_gap_audit.json",
    "collectorToRiskConsumptionChain": BASE / "collector_to_risk_consumption_chain.json",
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
    "encodedPayloadPcFormDiffMap": BASE / "encoded_payload_pc_form_diff_map.json",
    "encoderAxisEquivalence": BASE / "encoder_axis_equivalence.json",
    "outerSessionTupleFactorization": BASE / "outer_session_tuple_factorization.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def success_statuses(step: dict[str, Any]) -> list[str]:
    response = step.get("response") or {}
    parts = response.get("partsSummary") or {}
    return parts.get("successStatuses") or step.get("successStatuses") or []


def handlers(step: dict[str, Any]) -> list[str]:
    response = step.get("response") or {}
    return response.get("handlers") or step.get("handlers") or []


def pre_final_comparisons(diff: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in diff.get("comparisons", []):
        if row.get("freshLabel") == "seq5":
            continue
        response_shape = row.get("responseShape") or {}
        rows.append(
            {
                "s00Step": row.get("s00Step"),
                "freshStep": row.get("freshStep"),
                "s00RuntimeLine": row.get("s00RuntimeLine"),
                "freshLabel": row.get("freshLabel"),
                "handlersEqual": response_shape.get("handlersEqual"),
                "successStatusEqual": response_shape.get("successStatusEqual"),
                "powEqual": response_shape.get("powEqual"),
                "px3MutationEqualByPresence": response_shape.get("px3MutationEqualByPresence"),
                "pxdeMutationEqualByPresence": response_shape.get("pxdeMutationEqualByPresence"),
            }
        )
    return rows


def final_comparison(diff: dict[str, Any]) -> dict[str, Any]:
    for row in diff.get("comparisons", []):
        if row.get("freshLabel") == "seq5":
            return row
    return {}


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    diff = docs["collectorStateTransitionDiff"]
    first = docs["firstDecisiveDivergence"]
    risk_chain = docs["collectorToRiskConsumptionChain"]
    single_matrix = docs["singleTransitionCandidateMatrix"]
    encoder_axis = docs["encoderAxisEquivalence"]
    outer_tuple = docs["outerSessionTupleFactorization"]

    pre_rows = pre_final_comparisons(diff)
    final_row = final_comparison(diff)
    final_response = final_row.get("responseShape") or {}
    divergence = first.get("divergence") or {}
    downstream_checks = risk_chain.get("checks") or {}

    omitted_pre_accept = [
        row for row in pre_rows
        if not (
            row.get("handlersEqual") is True
            and row.get("successStatusEqual") is True
            and row.get("powEqual") is True
            and row.get("px3MutationEqualByPresence") is True
            and row.get("pxdeMutationEqualByPresence") is True
        )
    ]

    eliminated_boundaries = [
        {
            "id": "decoded_payload_semantics",
            "evidence": str(INPUTS["encodedPayloadPcFormDiffMap"]),
            "eliminated": (docs["encodedPayloadPcFormDiffMap"].get("checks") or {}).get("decodedJsonEqual") is True,
            "reason": "decoded JSON/text/base equality is already proven and final seq5 still diverges.",
        },
        {
            "id": "outer_session_tuple_single_field",
            "evidence": str(INPUTS["outerSessionTupleFactorization"]),
            "eliminated": (outer_tuple.get("checks") or {}).get("noSingleFieldExperimentReady") is True,
            "reason": "C4 factorization has zero ready source groups.",
        },
        {
            "id": "encoder_single_axis",
            "evidence": str(INPUTS["encoderAxisEquivalence"]),
            "eliminated": (encoder_axis.get("checks") or {}).get("singleEncoderAxisIsolated") is False,
            "reason": "C5 remains a 2x2 markerSource/pcUuidSource family.",
        },
        {
            "id": "downstream_risk_verify_chain_as_root_cause",
            "evidence": str(INPUTS["collectorToRiskConsumptionChain"]),
            "eliminated": downstream_checks.get("riskContinueTokenFeedsCreateAccount") is True,
            "reason": "line948 success feeds risk/verify after acceptance; selected fresh fails before this chain exists.",
        },
    ]

    checks = {
        "hasPreFinalComparisons": bool(pre_rows),
        "allPreFinalHandlersEqual": all(row.get("handlersEqual") is True for row in pre_rows),
        "allPreFinalSuccessStatusEqual": all(row.get("successStatusEqual") is True for row in pre_rows),
        "allPreFinalPowPresenceEqual": all(row.get("powEqual") is True for row in pre_rows),
        "allPreFinalPxMutationPresenceEqual": all(
            row.get("px3MutationEqualByPresence") is True and row.get("pxdeMutationEqualByPresence") is True
            for row in pre_rows
        ),
        "omittedPreAcceptTransitionCount": len(omitted_pre_accept),
        "hasFinalSeq5Divergence": bool(final_row) and final_response.get("successStatusEqual") is False,
        "firstDivergenceAtFinalSeq5": (first.get("checks") or {}).get("firstDivergenceAtFinalSeq5") is True,
        "downstreamRiskChainStartsAfterSuccess": downstream_checks.get("successCollectorLineIs948") is True,
        "outerTupleStillCoupled": (outer_tuple.get("checks") or {}).get("noSingleFieldExperimentReady") is True,
        "encoderStillCoupled": (encoder_axis.get("checks") or {}).get("remainingFamilyIsIndependent2x2") is True,
        "singleTransitionCandidateCount": (single_matrix.get("summary") or {}).get("singleTransitionCandidateCount"),
        "transitionHasReplayableClientRepresentation": False,
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "No client-observable omitted pre-accept transition is present in the selected contrast: all pre-final handler/status/pow/_px mutation-presence shapes align, "
            "while final seq5 alone diverges. C4 and C5 remain coupled, and line948->risk/verify is downstream of acceptance. "
            "The remaining C6 gap is therefore collector server expected state not represented as a single replayable client transition in current evidence."
        ),
        "nextArtifact": str(BASE / "hypothesis_reframe_status.json"),
        "nextScript": str(REPO / "tools/build_hypothesis_reframe_status.py"),
    }

    return {
        "artifact": str(OUT),
        "purpose": "Determine whether C6 collector server expected state has a client-observable pre-accept proxy transition.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "preFinalComparisonSummary": pre_rows,
        "omittedPreAcceptTransitions": omitted_pre_accept,
        "finalSeq5Divergence": {
            "s00RuntimeLine": divergence.get("s00", {}).get("runtimeLine"),
            "freshLabel": divergence.get("fresh", {}).get("label"),
            "s00SuccessStatuses": divergence.get("s00", {}).get("successStatuses"),
            "freshSuccessStatuses": divergence.get("fresh", {}).get("successStatuses"),
            "s00Handlers": final_response.get("s00Handlers"),
            "freshHandlers": final_response.get("freshHandlers"),
        },
        "eliminatedBoundaries": eliminated_boundaries,
        "remainingGap": {
            "id": "C6_collector_server_expected_state",
            "status": "server_internal_or_unobserved_expected_state",
            "clientObservableProxyFound": False,
            "replayableClientTransitionFound": False,
            "basis": [
                "pre-final collector-visible response shapes align in selected contrast",
                "final seq5 is first decisive divergence",
                "decoded semantic payload equality is proven",
                "C4 outer tuple and C5 encoder axes remain coupled",
                "line948 success to risk/verify is downstream, not root cause",
            ],
        },
        "checks": checks,
        "decision": decision,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
