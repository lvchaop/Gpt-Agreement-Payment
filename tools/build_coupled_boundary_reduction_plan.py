#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "coupled_boundary_reduction_plan.json"

INPUTS = {
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
    "serverStateValueToRequestLineage": BASE / "server_state_value_to_request_lineage.json",
    "coupledEncoderVariantAudit": BASE / "coupled_encoder_variant_audit.json",
    "remainingEncoderVariantBuildMatrix": BASE / "remaining_encoder_variant_build_matrix.json",
    "serverInternalStateGapAudit": BASE / "server_internal_state_gap_audit.json",
    "serverObservableStateInventory": BASE / "server_observable_state_inventory.json",
    "collectorToRiskConsumptionChain": BASE / "collector_to_risk_consumption_chain.json",
    "encodedPayloadPcFormDiffMap": BASE / "encoded_payload_pc_form_diff_map.json",
    "firstDecisiveDivergence": BASE / "first_decisive_divergence.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def evidence(path: Path, *fields: str) -> dict[str, Any]:
    row: dict[str, Any] = {"path": str(path)}
    if fields:
        row["fields"] = list(fields)
    return row


def candidate_by_id(matrix: dict[str, Any], cid: str) -> dict[str, Any]:
    for row in matrix.get("candidates", []):
        if row.get("id") == cid:
            return row
    return {}


def build_track(
    track_id: str,
    candidate: dict[str, Any],
    priority: int,
    reduction_goal: str,
    offline_steps: list[dict[str, Any]],
    success_gate: dict[str, Any],
    fail_gate: dict[str, Any],
    next_artifact: Path,
    next_script: Path,
) -> dict[str, Any]:
    return {
        "id": track_id,
        "sourceCandidateId": candidate.get("id"),
        "title": candidate.get("title"),
        "priority": priority,
        "currentStatus": candidate.get("status"),
        "currentReadyForFreshExperiment": candidate.get("readyForFreshExperiment"),
        "whyNotExperimentNow": candidate.get("reason"),
        "reductionGoal": reduction_goal,
        "offlineEvidenceSteps": offline_steps,
        "successGateToBecomeSingleTransition": success_gate,
        "failGateIfStillCoupled": fail_gate,
        "nextArtifact": str(next_artifact),
        "nextScript": str(next_script),
    }


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    matrix = docs["singleTransitionCandidateMatrix"]
    lineage = docs["serverStateValueToRequestLineage"]
    encoder = docs["remainingEncoderVariantBuildMatrix"]

    c4 = candidate_by_id(matrix, "C4_outer_session_tuple")
    c5 = candidate_by_id(matrix, "C5_pc_marker_uuid_encoder_binding")
    c6 = candidate_by_id(matrix, "C6_collector_server_expected_state")

    tracks = [
        build_track(
            "T1_outer_session_tuple_factorization",
            c4,
            1,
            "Split uuid/cs/ci/sid/p1/vid/cts into independently sourced state values vs derived tuple members, without network traffic.",
            [
                {
                    "step": "Extract requestValueLineage rows for uuid/cs/ci/sid/p1/vid/cts and classify each as bootstrap, seq4 response, risk/Microsoft context, or derived.",
                    "evidence": [evidence(INPUTS["serverStateValueToRequestLineage"], "requestValueLineage", "remainingBoundaries.L1_outer_session_tuple")],
                },
                {
                    "step": "Build dependency groups by shared source and shared consumedBy targets; fields sharing the same source mutation remain coupled.",
                    "evidence": [evidence(INPUTS["serverObservableStateInventory"], "checks.finalConsumedFieldsAllDiffer")],
                },
                {
                    "step": "Mark any field already covered by exact payload/pc, fresh outer, or template outer controls as not independently experiment-ready.",
                    "evidence": [evidence(INPUTS["serverStateValueToRequestLineage"], "controlCoverage")],
                },
            ],
            {
                "condition": "Exactly one dependency group remains untested and has a direct request-field mutation with a defined stage-progress metric.",
                "requiredChecks": [
                    "outerDependencyGroupCountAfterControls == 1",
                    "singleVariable == true",
                    "serverObservable == true",
                    "negativeControlCovered == false",
                ],
            },
            {
                "condition": "More than one dependency group remains, or all groups are already covered by negative controls.",
                "action": "Do not run fresh session; feed unresolved groups back into C6 server-state analysis.",
            },
            BASE / "outer_session_tuple_factorization.json",
            REPO / "tools/build_outer_session_tuple_factorization.py",
        ),
        build_track(
            "T2_encoder_axis_equivalence",
            c5,
            2,
            "Reduce the four remaining payloadUuid/pcUuid/marker variants to one decisive axis, or prove they are still a family.",
            [
                {
                    "step": "Compare the four already-built variants by payloadSha256, pc, bodySha256, decoded base, and marker source.",
                    "evidence": [evidence(INPUTS["remainingEncoderVariantBuildMatrix"], "summary", "checks")],
                },
                {
                    "step": "Group variants by payload equality and pc equality; identify whether pcUuidSource or markerSource is the only remaining independent axis.",
                    "evidence": [evidence(INPUTS["coupledEncoderVariantAudit"], "justifiedUntestedVariants")],
                },
                {
                    "step": "Map each group to prior negative controls: exact payload+pc, template marker, template pc, exact body, fresh outer.",
                    "evidence": [evidence(INPUTS["coupledEncoderVariantAudit"], "controlChecks")],
                },
            ],
            {
                "condition": "Exactly one encoder axis remains untested after grouping and control coverage.",
                "requiredChecks": [
                    "remainingEncoderAxisCount == 1",
                    "axisHasOfflineBuiltBodies == true",
                    "axisNotCoveredByPriorControls == true",
                ],
            },
            {
                "condition": "At least two axes remain or all variant groups preserve the same decoded base without a server-consumed discriminator.",
                "action": "Do not network-test arbitrary variants; treat encoder binding as coupled with C4/C6.",
            },
            BASE / "encoder_axis_equivalence.json",
            REPO / "tools/build_encoder_axis_equivalence.py",
        ),
        build_track(
            "T3_server_expected_state_observable_proxy",
            c6,
            3,
            "Find a client-observable proxy for collector server expected state before final seq5, or explicitly mark it non-request-internal.",
            [
                {
                    "step": "Enumerate every s00 collector decoded mutation before line948 and every selected fresh mutation before final rejection; compare handler/value classes, not payload fields.",
                    "evidence": [evidence(INPUTS["firstDecisiveDivergence"], "divergence"), evidence(INPUTS["serverInternalStateGapAudit"], "remainingHypotheses")],
                },
                {
                    "step": "Separate downstream-proven state from root-cause state: line948 _px3/_pxde feeds risk/verify but occurs after acceptance, so it is not the missing pre-accept transition.",
                    "evidence": [evidence(INPUTS["collectorToRiskConsumptionChain"], "checks", "riskConsumption")],
                },
                {
                    "step": "Identify whether any pre-line948 state mutation exists in s00 but has no selected-fresh analogue and is not decoded payload content, transport, IP, HEAD timing, seq6 timing, or exact body replay.",
                    "evidence": [
                        evidence(INPUTS["singleTransitionCandidateMatrix"], "candidates"),
                        evidence(INPUTS["encodedPayloadPcFormDiffMap"], "checks.decodedJsonEqual"),
                    ],
                },
            ],
            {
                "condition": "One omitted pre-accept state mutation is found and can be represented as a client-visible request or handler transition.",
                "requiredChecks": [
                    "omittedPreAcceptTransitionCount == 1",
                    "transitionAfterExistingNegativeControls == true",
                    "transitionHasReplayableClientRepresentation == true",
                ],
            },
            {
                "condition": "No client-visible omitted transition remains.",
                "action": "State current gap as collector server-internal expected state; do not claim pure-protocol success.",
            },
            BASE / "server_expected_state_observable_proxy.json",
            REPO / "tools/build_server_expected_state_observable_proxy.py",
        ),
    ]

    checks = {
        "singleTransitionMatrixReady": (matrix.get("checks") or {}).get("noReadySingleTransitionCandidate") is True,
        "hasC4": bool(c4),
        "hasC5": bool(c5),
        "hasC6": bool(c6),
        "hasThreeReductionTracks": len(tracks) == 3,
        "tracksAreOfflineOnly": all("fresh" not in " ".join(step["step"].lower() for step in t["offlineEvidenceSteps"]) or "do not run fresh" for t in tracks),
        "outerTupleBoundaryPresent": any(row.get("id") == "L1_outer_session_tuple" for row in lineage.get("remainingBoundaries", [])),
        "encoderVariantFamilyPresent": (encoder.get("checks") or {}).get("variantFamilyNotSingle") is True,
        "serverExpectedStateBoundaryPresent": any(row.get("id") == "C6_collector_server_expected_state" for row in matrix.get("candidates", [])),
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": "This is a reduction plan, not an experiment plan. Current evidence has zero ready single-transition candidates.",
        "recommendedNextTrack": "T1_outer_session_tuple_factorization",
        "nextArtifact": str(BASE / "outer_session_tuple_factorization.json"),
        "nextScript": str(REPO / "tools/build_outer_session_tuple_factorization.py"),
    }

    return {
        "artifact": str(OUT),
        "purpose": "Define offline evidence required to reduce C4/C5/C6 coupled boundaries into a single transition before any fresh-session experiment.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "sourceSummary": {
            "singleTransitionCandidateMatrix": matrix.get("summary"),
            "serverStateRemainingBoundaries": lineage.get("remainingBoundaries"),
            "remainingEncoderVariantSummary": encoder.get("summary"),
        },
        "reductionTracks": tracks,
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
