#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def p(rel: str) -> str:
    return str(ROOT / rel)


def main() -> int:
    field_map = load("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json")
    encoded = load("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json")
    split = load("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json")
    first = load("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json")
    model = load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")
    gen = load("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json")

    field_checks = field_map.get("checks") or {}
    field_summary = field_map.get("summary") or {}
    encoded_checks = encoded.get("checks") or {}
    split_checks = split.get("checks") or {}

    reductions = [
        {
            "candidate": "decoded_line922_activity_fields",
            "status": "eliminated_for_selected_contrast",
            "evidence": [
                p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
                p("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
            ],
            "facts": [
                f"freshSeq5ActivityTypesEqualS00={field_checks.get('freshSeq5ActivityTypesEqualS00')}",
                f"freshSeq5ChangedFieldInstances={field_summary.get('freshSeq5ChangedFieldInstances')}",
                f"fieldInstanceCount={field_summary.get('fieldInstanceCount')}",
                f"seq5DecodedNotEqualS00={encoded_checks.get('seq5DecodedNotEqualS00')}",
            ],
            "reason": "For the selected contrast, decoded line922 activity fields are identical to s00; changing an activity field would not target an observed divergence.",
        },
        {
            "candidate": "static_payload_or_pc_transplant",
            "status": "eliminated_as_static_fix",
            "evidence": [
                p("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
                p("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
            ],
            "facts": [
                f"seq5EncodedPayloadDiffers={encoded_checks.get('seq5EncodedPayloadDiffers')}",
                f"seq5OnlyExpectedOuterAndPayloadPcFormDiffs={encoded_checks.get('seq5OnlyExpectedOuterAndPayloadPcFormDiffs')}",
                f"exactPayloadPcControlChecks={split_checks}",
            ],
            "reason": "Encoded payload/pc differ while decoded activities match, but exact payload+pc transplant is already rejected or returns no success.",
        },
        {
            "candidate": "request_history_order",
            "status": "eliminated_for_selected_contrast",
            "evidence": [
                p("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
            ],
            "facts": [
                "request_history_coherence_gap.checks.hasOrderGap=false",
            ],
            "reason": "The selected fresh contrast has the same msft-before-bundle POW order as s00.",
        },
        {
            "candidate": "server_expected_state_or_encoder_state",
            "status": "remaining_boundary_not_experiment_ready",
            "evidence": [
                p("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
                p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
                p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
            ],
            "facts": [
                f"firstDivergenceAtFinalSeq5={(first.get('checks') or {}).get('firstDivergenceAtFinalSeq5')}",
                f"finalS00Success={(model.get('checks') or {}).get('finalS00Success')}",
                f"finalFreshRejected={(model.get('checks') or {}).get('finalFreshRejected')}",
                f"decodedLine922Equal={(field_summary.get('freshSeq5ChangedFieldInstances') == 0)}",
            ],
            "reason": "The remaining observed difference is outside decoded activity fields: encoded payload/pc/form binding and/or collector server expected state. Current evidence still does not isolate one reversible transition.",
        },
    ]

    next_work = [
        {
            "id": "E1_encoder_binding_diff",
            "artifact": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "script": str(ROOT / "tools/build_encoded_payload_pc_form_diff_map.py"),
            "purpose": "Compare s00 line933 and fresh seq5 form/body/payload/pc/marker/uuid/ci/cs fields while decoded activities are equal; identify exact non-decoded diffs and whether each has prior negative control.",
        },
        {
            "id": "E2_server_state_value_to_request_lineage",
            "artifact": p("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"),
            "script": str(ROOT / "tools/build_server_state_value_to_request_lineage.py"),
            "purpose": "Trace seq4 response values into final seq5 form fields and decoded activities to separate consumed state from unused state.",
        },
    ]

    result = {
        "purpose": "Reduce line922-derived hypotheses after proving selected fresh seq5 decoded activity fields match s00 line922.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "line922DynamicFieldSourceMap": p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
            "encodedDecodedBoundaryAudit": p("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
            "payloadPcSplitControl": p("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
            "firstDecisiveDivergence": p("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
            "serverStateTransitionValueModel": p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
        },
        "reductions": reductions,
        "remainingBoundaries": [
            "encoded_payload_pc_form_binding",
            "collector_server_expected_state_not_visible_in_decoded_activities",
        ],
        "nextStaticWork": next_work,
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "Decoded activity fields are eliminated for this contrast, and static payload/pc transplant is already negatively controlled. The next decisive evidence must map non-decoded encoded/form diffs and server-state value consumption.",
            "nextArtifact": next_work[0]["artifact"],
            "nextScript": next_work[0]["script"],
        },
        "checks": {
            "line922MapExists": bool(field_map),
            "freshSeq5PayloadDecoded": field_checks.get("freshSeq5PayloadDecoded") is True,
            "decodedActivityFieldsEqual": field_summary.get("freshSeq5ChangedFieldInstances") == 0,
            "decodedBoundaryAuditSaysDecodedEqual": encoded_checks.get("seq5DecodedNotEqualS00") is False,
            "encodedPayloadDiffers": encoded_checks.get("seq5EncodedPayloadDiffers") is True,
            "exactPayloadPcControlExists": bool(split_checks),
            "finalDivergenceStillSeq5": (first.get("checks") or {}).get("firstDivergenceAtFinalSeq5") is True,
            "hasRemainingBoundary": True,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
