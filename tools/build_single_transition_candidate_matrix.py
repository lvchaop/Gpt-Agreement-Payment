#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "single_transition_candidate_matrix.json"

INPUTS = {
    "collectorToRiskConsumptionChain": BASE / "collector_to_risk_consumption_chain.json",
    "serverObservableStateInventory": BASE / "server_observable_state_inventory.json",
    "serverStateValueToRequestLineage": BASE / "server_state_value_to_request_lineage.json",
    "encodedPayloadPcFormDiffMap": BASE / "encoded_payload_pc_form_diff_map.json",
    "remainingEncoderVariantBuildMatrix": BASE / "remaining_encoder_variant_build_matrix.json",
    "serverInternalStateGapAudit": BASE / "server_internal_state_gap_audit.json",
    "coupledEncoderVariantAudit": BASE / "coupled_encoder_variant_audit.json",
    "line922CandidateReduction": BASE / "line922_candidate_reduction.json",
    "firstDecisiveDivergence": BASE / "first_decisive_divergence.json",
    "bridgeToPayloadContextAudit": BASE / "bridge_to_payload_context_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs() -> dict[str, dict[str, Any]]:
    return {name: read_json(path) for name, path in INPUTS.items()}


def evidence(path: Path, *fields: str) -> dict[str, Any]:
    row: dict[str, Any] = {"path": str(path)}
    if fields:
        row["fields"] = list(fields)
    return row


def candidate(
    cid: str,
    title: str,
    status: str,
    single_variable: bool,
    server_observable: bool,
    negative_control_covered: bool,
    stage_progress_metric: bool,
    evidence_rows: list[dict[str, Any]],
    reason: str,
    next_evidence_needed: str | None = None,
) -> dict[str, Any]:
    ready = (
        status == "candidate"
        and single_variable
        and server_observable
        and not negative_control_covered
        and stage_progress_metric
    )
    return {
        "id": cid,
        "title": title,
        "status": status,
        "singleVariable": single_variable,
        "serverObservable": server_observable,
        "negativeControlCovered": negative_control_covered,
        "stageProgressMetricDefined": stage_progress_metric,
        "readyForFreshExperiment": ready,
        "evidence": evidence_rows,
        "reason": reason,
        "nextEvidenceNeeded": next_evidence_needed,
    }


def build_candidates(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    lineage = docs["serverStateValueToRequestLineage"]
    coupled = docs["coupledEncoderVariantAudit"]
    remaining_matrix = docs["remainingEncoderVariantBuildMatrix"]
    risk_chain = docs["collectorToRiskConsumptionChain"]
    bridge = docs["bridgeToPayloadContextAudit"]

    justified_variants = coupled.get("justifiedUntestedVariants", [])
    variant_summary = remaining_matrix.get("summary", {})
    remaining_boundaries = lineage.get("remainingBoundaries", [])
    boundary_ids = [row.get("id") for row in remaining_boundaries]

    candidates: list[dict[str, Any]] = [
        candidate(
            "C1_decoded_line922_activity_fields",
            "Decoded final seq5 activity fields",
            "eliminated",
            False,
            True,
            True,
            True,
            [
                evidence(INPUTS["line922CandidateReduction"], "reductions[decoded_line922_activity_fields]"),
                evidence(INPUTS["encodedPayloadPcFormDiffMap"], "checks.decodedJsonEqual", "checks.decodedTextEqual"),
            ],
            "Selected fresh final seq5 decoded activities and decoded text/base match s00; this is not an observed divergence.",
        ),
        candidate(
            "C2_request_history_order",
            "Microsoft seq1-3 before bundle POW ordering",
            "eliminated",
            True,
            True,
            True,
            True,
            [
                evidence(BASE / "request_history_coherence_gap.json", "checks.hasOrderGap"),
            ],
            "The corrected coherence audit shows no order gap for the selected fresh sample.",
        ),
        candidate(
            "C3_static_payload_pc_transplant",
            "Static s00 payload/pc/body transplant",
            "eliminated",
            False,
            True,
            True,
            True,
            [
                evidence(INPUTS["encodedPayloadPcFormDiffMap"], "checks.staticPayloadPcControlExists"),
                evidence(INPUTS["serverStateValueToRequestLineage"], "controlCoverage.payloadPcSplit"),
            ],
            "Exact or static payload/pc controls are already negative and do not represent a coherent session transition.",
        ),
        candidate(
            "C4_outer_session_tuple",
            "Outer session tuple: uuid/cs/ci/sid/p1/vid/cts",
            "coupled_boundary",
            False,
            True,
            False,
            True,
            [
                evidence(INPUTS["serverStateValueToRequestLineage"], "remainingBoundaries.L1_outer_session_tuple"),
                evidence(INPUTS["serverObservableStateInventory"], "checks.finalConsumedFieldsAllDiffer"),
            ],
            "The remaining outer fields differ as a coherent tuple; existing evidence does not isolate one field as the decisive transition.",
            "Find a runtime or server-visible source showing exactly one tuple member changes server acceptance independently.",
        ),
        candidate(
            "C5_pc_marker_uuid_encoder_binding",
            "pc/marker/uuid encoded binding family",
            "coupled_boundary",
            False,
            True,
            False,
            True,
            [
                evidence(INPUTS["coupledEncoderVariantAudit"], "justifiedUntestedVariants"),
                evidence(INPUTS["remainingEncoderVariantBuildMatrix"], "summary.uniquePayloadCount", "summary.uniquePcCount"),
            ],
            (
                f"{len(justified_variants)} encoder variants remain in the coupled audit, and the offline build still has "
                f"{variant_summary.get('uniquePayloadCount')} unique payloads / {variant_summary.get('uniquePcCount')} unique pcs; choosing one would be arbitrary."
            ),
            "Reduce the encoder family to one evidenced axis, or prove all variants are equivalent at the server-consumed boundary.",
        ),
        candidate(
            "C6_collector_server_expected_state",
            "Collector server-side expected state",
            "non_request_boundary",
            False,
            False,
            False,
            True,
            [
                evidence(INPUTS["serverInternalStateGapAudit"], "remainingHypotheses.R2_collector_server_expected_state"),
                evidence(INPUTS["firstDecisiveDivergence"], "checks.firstDivergenceAtFinalSeq5"),
            ],
            "This remains the highest-priority explanatory gap, but it is not directly mutable as one request field.",
            "Find a client-observable token/transition omitted by pure protocol, or prove the gap is server-internal only.",
        ),
        candidate(
            "C7_parent_bridge_cookie_header",
            "Parent bridge as request Cookie/header transition",
            "eliminated",
            True,
            True,
            True,
            True,
            [
                evidence(INPUTS["bridgeToPayloadContextAudit"], "checks.line933NoCookieHeader", "checks.freshSeq5NoCookieHeader"),
            ],
            "Both line933 and selected fresh seq5 have no Cookie header; bridge _px3 is already represented in decoded payload semantics and was not sufficient.",
        ),
        candidate(
            "C8_collector_success_to_risk_verify",
            "Accepted collector response consumed by Microsoft risk/verify",
            "downstream_proven_not_root_cause",
            False,
            True,
            False,
            True,
            [
                evidence(INPUTS["collectorToRiskConsumptionChain"], "checks.riskPx3PxdeLinkedToSuccessCollectorLine", "checks.riskContinueTokenFeedsCreateAccount"),
            ],
            "The downstream consumption chain is proven, but it starts after s00 obtains line948 success; selected fresh fails before this chain can exist.",
            "Continue reducing why fresh final seq5 does not obtain line948 success.",
        ),
    ]

    # Preserve the concrete boundary ids in the matrix for auditability.
    for row in candidates:
        if row["id"] in {"C4_outer_session_tuple", "C5_pc_marker_uuid_encoder_binding", "C6_collector_server_expected_state"}:
            row["lineageRemainingBoundaryIds"] = boundary_ids
    return candidates


def build() -> dict[str, Any]:
    docs = load_inputs()
    candidates = build_candidates(docs)
    ready = [row for row in candidates if row["readyForFreshExperiment"]]
    coupled_or_non_request = [row for row in candidates if row["status"] in {"coupled_boundary", "non_request_boundary"}]
    eliminated = [row for row in candidates if row["status"] == "eliminated"]

    checks = {
        "collectorRiskChainInputReady": (docs["collectorToRiskConsumptionChain"].get("decision") or {}).get("nextArtifact") == str(OUT),
        "firstDivergenceAtFinalSeq5": (docs["firstDecisiveDivergence"].get("checks") or {}).get("firstDivergenceAtFinalSeq5") is True,
        "decodedPayloadSemanticEqual": (docs["encodedPayloadPcFormDiffMap"].get("checks") or {}).get("decodedJsonEqual") is True,
        "requestHistoryOrderGapFalsified": (read_json(BASE / "request_history_coherence_gap.json").get("checks") or {}).get("hasOrderGap") is False,
        "riskChainDownstreamProven": (docs["collectorToRiskConsumptionChain"].get("checks") or {}).get("riskContinueTokenFeedsCreateAccount") is True,
        "remainingEncoderVariantFamilyNotSingle": (docs["remainingEncoderVariantBuildMatrix"].get("checks") or {}).get("variantFamilyNotSingle") is True,
        "hasCandidateRows": bool(candidates),
        "hasEliminatedRows": bool(eliminated),
        "hasCoupledOrNonRequestBoundaries": bool(coupled_or_non_request),
        "singleTransitionCandidateCount": len(ready),
        "noReadySingleTransitionCandidate": len(ready) == 0,
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "No candidate satisfies all required gates: single variable, server-observable, not already covered by negative controls, and with a stage-progress metric. "
            "The remaining explanations are coupled outer/session/encoder boundaries or non-request collector server expected state."
        ),
        "nextArtifact": str(REPO / "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json"),
        "nextScript": str(REPO / "tools/audit_pure_protocol_goal_gap.py"),
    }

    return {
        "artifact": str(OUT),
        "purpose": "Decide whether any remaining boundary is a single transition suitable for one fresh-session experiment.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "gateDefinition": {
            "singleVariable": "Mutates exactly one evidenced transition or value family.",
            "serverObservable": "The mutated value or transition is visible to collector/Microsoft server behavior.",
            "negativeControlCovered": "True means existing live/offline controls already rejected this candidate family.",
            "stageProgressMetricDefined": "A response/cookie/risk state change is defined before running any network experiment.",
            "readyForFreshExperiment": "Allowed only when singleVariable=true, serverObservable=true, negativeControlCovered=false, stageProgressMetricDefined=true.",
        },
        "candidates": candidates,
        "summary": {
            "candidateCount": len(candidates),
            "eliminatedCount": len(eliminated),
            "coupledOrNonRequestBoundaryCount": len(coupled_or_non_request),
            "singleTransitionCandidateCount": len(ready),
            "readyCandidateIds": [row["id"] for row in ready],
        },
        "checks": checks,
        "decision": decision,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "summary": result["summary"], "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
