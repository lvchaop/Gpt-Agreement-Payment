#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/final_boundary_decision_matrix.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def p(rel: str) -> str:
    return str(ROOT / rel)


def main() -> int:
    docs = {
        "firstDivergence": load("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
        "line922Map": load("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
        "candidateReduction": load("output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json"),
        "encodedDiff": load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
        "stateLineage": load("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"),
        "requestHistory": load("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
    }

    matrix = [
        {
            "boundary": "decoded_activity_semantics",
            "status": "eliminated_for_selected_contrast",
            "evidence": [
                p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
                p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            ],
            "decisiveChecks": {
                "freshSeq5ChangedFieldInstances": (docs["line922Map"].get("summary") or {}).get("freshSeq5ChangedFieldInstances"),
                "decodedJsonEqual": (docs["encodedDiff"].get("checks") or {}).get("decodedJsonEqual"),
                "decodedTextEqual": (docs["encodedDiff"].get("checks") or {}).get("decodedTextEqual"),
            },
            "freshExperimentAllowed": False,
        },
        {
            "boundary": "request_history_order",
            "status": "eliminated_for_selected_contrast",
            "evidence": [p("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json")],
            "decisiveChecks": {
                "hasOrderGap": (docs["requestHistory"].get("checks") or {}).get("hasOrderGap"),
            },
            "freshExperimentAllowed": False,
        },
        {
            "boundary": "marker_only_or_static_payload_pc",
            "status": "eliminated_as_single_variable",
            "evidence": [
                p("output/protocol_reverse/goal_audit/outer_binding_controls_audit.json"),
                p("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
                p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            ],
            "decisiveChecks": {
                "baseAfterMarkerRemovalEqual": (docs["encodedDiff"].get("checks") or {}).get("baseAfterMarkerRemovalEqual"),
                "payloadDiffers": (docs["encodedDiff"].get("checks") or {}).get("payloadDiffers"),
                "pcDiffers": (docs["encodedDiff"].get("checks") or {}).get("pcDiffers"),
                "staticPayloadPcControlExists": (docs["encodedDiff"].get("checks") or {}).get("staticPayloadPcControlExists"),
            },
            "freshExperimentAllowed": False,
        },
        {
            "boundary": "coherent_outer_session_tuple",
            "status": "remaining_not_single_field",
            "evidence": [p("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json")],
            "decisiveChecks": {
                "hasOuterSessionTupleBoundary": (docs["stateLineage"].get("checks") or {}).get("hasOuterSessionTupleBoundary"),
                "allRowsDiffer": (docs["stateLineage"].get("checks") or {}).get("allRowsDiffer"),
            },
            "freshExperimentAllowed": False,
            "why": "Changing this tuple coherently would require generating a new server-accepted session state, not one request-field mutation.",
        },
        {
            "boundary": "encoder_pc_marker_uuid_binding",
            "status": "remaining_coupled_with_outer_state",
            "evidence": [
                p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
                p("tools/probe_human_fresh_px561.py"),
            ],
            "decisiveChecks": {
                "baseAfterMarkerRemovalEqual": (docs["encodedDiff"].get("checks") or {}).get("baseAfterMarkerRemovalEqual"),
                "markerDiffers": (docs["encodedDiff"].get("checks") or {}).get("markerDiffers"),
                "pcDiffers": (docs["encodedDiff"].get("checks") or {}).get("pcDiffers"),
            },
            "freshExperimentAllowed": False,
            "why": "The builder can vary payload uuid, pc uuid, marker source, and outer source, but prior controls already show marker-only/static-pc variants are insufficient; a justified experiment needs an untested coupled variant derived from evidence.",
        },
        {
            "boundary": "server_internal_expected_state",
            "status": "remaining_highest_priority_static_gap",
            "evidence": [
                p("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
                p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
                p("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"),
            ],
            "decisiveChecks": {
                "firstDivergenceAtFinalSeq5": (docs["firstDivergence"].get("checks") or {}).get("firstDivergenceAtFinalSeq5"),
                "finalS00Success": (load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json").get("checks") or {}).get("finalS00Success"),
                "finalFreshRejected": (load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json").get("checks") or {}).get("finalFreshRejected"),
            },
            "freshExperimentAllowed": False,
            "why": "The acceptance difference may be server-internal expected state, but no one transition has been isolated for a pure-protocol mutation.",
        },
    ]

    next_static = {
        "artifact": p("output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json"),
        "script": str(ROOT / "tools/build_coupled_encoder_variant_audit.py"),
        "purpose": "Enumerate the already-supported builder knobs (payload_uuid_source, pc_uuid_source, marker_source, form_outer_source, payload_source, pc_source), match them to existing controls, and identify whether exactly one untested coupled variant remains justified by evidence.",
        "mustNotSendNetwork": True,
    }

    result = {
        "purpose": "Final Phase 4 static boundary decision matrix before any Phase 5 fresh-session experiment.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "firstDecisiveDivergence": p("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
            "line922DynamicFieldSourceMap": p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
            "line922CandidateReduction": p("output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json"),
            "encodedPayloadPcFormDiffMap": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "serverStateValueToRequestLineage": p("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"),
        },
        "boundaryMatrix": matrix,
        "nextStaticWork": next_static,
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "All eliminated boundaries are covered by current evidence. The remaining boundaries are coupled encoder/session/server-state boundaries; no single state transition is isolated yet.",
            "nextArtifact": next_static["artifact"],
            "nextScript": next_static["script"],
        },
        "checks": {
            "decodedActivityBoundaryEliminated": matrix[0]["status"] == "eliminated_for_selected_contrast",
            "requestHistoryBoundaryEliminated": matrix[1]["status"] == "eliminated_for_selected_contrast",
            "markerStaticPayloadBoundaryEliminated": matrix[2]["status"] == "eliminated_as_single_variable",
            "hasRemainingOuterSessionTupleBoundary": matrix[3]["status"] == "remaining_not_single_field",
            "hasRemainingEncoderBindingBoundary": matrix[4]["status"] == "remaining_coupled_with_outer_state",
            "hasRemainingServerInternalBoundary": matrix[5]["status"] == "remaining_highest_priority_static_gap",
            "noBoundaryAllowsFreshExperiment": all(item.get("freshExperimentAllowed") is False for item in matrix),
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
