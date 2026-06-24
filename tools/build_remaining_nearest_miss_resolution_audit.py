#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
OUT = HYP / "remaining_nearest_miss_resolution_audit.json"

INPUTS = {
    "nearestMiss": HYP / "nearest_miss_promotion_candidate_audit.json",
    "nearestMissBlockerResolution": HYP / "nearest_miss_blocker_resolution_audit.json",
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

CLOSED_TOP2 = {"pc_value", "collector_cookie_header"}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    nearest = [row for row in docs["nearestMiss"].get("nearestRows") or [] if row.get("id") not in CLOSED_TOP2]

    c_line922 = checks(docs["line922CandidateReduction"])
    c_encoded = checks(docs["encodedPayloadPcFormDiff"])
    c_order = checks(docs["requestHistoryCoherence"])
    c_lineage = checks(docs["serverStateValueToRequestLineage"])
    c_inventory = checks(docs["serverObservableStateInventory"])
    c_encoder = checks(docs["coupledEncoderVariant"])
    c_build = checks(docs["remainingEncoderVariantBuildMatrix"])
    c_bridge = checks(docs["bridgeToPayloadContext"])
    c_risk = checks(docs["collectorToRiskConsumptionChain"])

    closure_by_id = {
        "RB4_collector_success_to_risk_verify": {
            "status": "closed_post_accept",
            "closed": c_risk.get("riskContinueTokenFeedsCreateAccount") is True and c_risk.get("line933DivergenceIsAccepted") is True,
            "facts": {
                "riskContinueTokenFeedsCreateAccount": c_risk.get("riskContinueTokenFeedsCreateAccount"),
                "line933DivergenceIsAccepted": c_risk.get("line933DivergenceIsAccepted"),
            },
        },
        "C8_collector_success_to_risk_verify": {
            "status": "closed_post_accept",
            "closed": c_risk.get("riskContinueTokenFeedsCreateAccount") is True and c_risk.get("successEntryHasChallengeSuccess0") is True,
            "facts": {
                "riskContinueTokenFeedsCreateAccount": c_risk.get("riskContinueTokenFeedsCreateAccount"),
                "successEntryHasChallengeSuccess0": c_risk.get("successEntryHasChallengeSuccess0"),
            },
        },
        "C1_decoded_line922_activity_fields": {
            "status": "closed_not_observed_divergence",
            "closed": c_line922.get("decodedActivityFieldsEqual") is True and c_line922.get("exactPayloadPcControlExists") is True,
            "facts": {
                "decodedActivityFieldsEqual": c_line922.get("decodedActivityFieldsEqual"),
                "decodedBoundaryAuditSaysDecodedEqual": c_line922.get("decodedBoundaryAuditSaysDecodedEqual"),
                "exactPayloadPcControlExists": c_line922.get("exactPayloadPcControlExists"),
            },
        },
        "C2_request_history_order": {
            "status": "closed_order_gap_falsified",
            "closed": c_order.get("hasOrderGap") is False and c_order.get("finalDivergenceStillSeq5") is True,
            "facts": {
                "hasOrderGap": c_order.get("hasOrderGap"),
                "finalDivergenceStillSeq5": c_order.get("finalDivergenceStillSeq5"),
            },
        },
        "C3_static_payload_pc_transplant": {
            "status": "closed_static_transplant_control_rejected",
            "closed": c_encoded.get("staticPayloadPcControlExists") is True and c_lineage.get("payloadPcSplitControlRejected") is True,
            "facts": {
                "staticPayloadPcControlExists": c_encoded.get("staticPayloadPcControlExists"),
                "payloadPcSplitControlRejected": c_lineage.get("payloadPcSplitControlRejected"),
            },
        },
        "C4_outer_session_tuple": {
            "status": "closed_coupled_tuple_not_single_transition",
            "closed": c_lineage.get("hasOuterSessionTupleBoundary") is True and c_lineage.get("outerBindingControlsRejected") is True and c_inventory.get("finalConsumedFieldsAllDiffer") is True,
            "facts": {
                "hasOuterSessionTupleBoundary": c_lineage.get("hasOuterSessionTupleBoundary"),
                "outerBindingControlsRejected": c_lineage.get("outerBindingControlsRejected"),
                "finalConsumedFieldsAllDiffer": c_inventory.get("finalConsumedFieldsAllDiffer"),
            },
        },
        "C5_pc_marker_uuid_encoder_binding": {
            "status": "closed_coupled_encoder_family_not_single",
            "closed": c_encoder.get("singleRecommendedVariant") is False and c_build.get("variantFamilyNotSingle") is True,
            "facts": {
                "singleRecommendedVariant": c_encoder.get("singleRecommendedVariant"),
                "justifiedUntestedVariantCount": c_encoder.get("justifiedUntestedVariantCount"),
                "variantFamilyNotSingle": c_build.get("variantFamilyNotSingle"),
            },
        },
        "C7_parent_bridge_cookie_header": {
            "status": "closed_not_cookie_header_transition",
            "closed": c_bridge.get("line933NoCookieHeader") is True and c_bridge.get("freshSeq5NoCookieHeader") is True and c_bridge.get("decodedPayloadAlreadyEqual") is True,
            "facts": {
                "line933NoCookieHeader": c_bridge.get("line933NoCookieHeader"),
                "freshSeq5NoCookieHeader": c_bridge.get("freshSeq5NoCookieHeader"),
                "decodedPayloadAlreadyEqual": c_bridge.get("decodedPayloadAlreadyEqual"),
                "parentPx3MatchesLine922Payload": c_bridge.get("parentPx3MatchesLine922Payload"),
            },
        },
    }

    rows = []
    for row in nearest:
        rid = row.get("id")
        closure = closure_by_id.get(rid, {"status": "unmapped", "closed": False, "facts": {}})
        rows.append(
            {
                "id": rid,
                "source": row.get("source"),
                "satisfiedPredicateCount": row.get("satisfiedPredicateCount"),
                "missingPredicates": row.get("missingPredicates"),
                "previousBlockers": row.get("blockers"),
                "status": closure["status"],
                "closedByExistingControls": closure["closed"],
                "facts": closure["facts"],
                "evidence": row.get("evidence"),
            }
        )

    open_rows = [row for row in rows if row["closedByExistingControls"] is not True]
    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "remainingNearestRowCount": len(rows),
        "closedByExistingControlsCount": sum(1 for row in rows if row["closedByExistingControls"] is True),
        "openRemainingNearestRowCount": len(open_rows),
        "proposalReadyCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "After closing pc_value and collector_cookie_header, resolve the remaining nearest-miss candidates so the next step is not pulled back to already-closed branches.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "rows": rows,
        "openRows": open_rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All remaining nearest-miss rows are closed by current local controls."
                if not open_rows
                else "Some nearest-miss rows remain open and need targeted evidence before any proposal."
            ),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "openRows": open_rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
