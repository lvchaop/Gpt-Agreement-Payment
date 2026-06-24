#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GOAL = ROOT / "output/protocol_reverse/goal_audit"
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
OUT = HYP / "encoded_session_binding_candidate_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"

INPUTS = {
    "encodedBoundary": GOAL / "latest_asset_lineage_encoded_boundary_audit.json",
    "exactPayloadBody": GOAL / "latest_exact_payload_body_controls_audit.json",
    "outerBinding": GOAL / "clean_history_outer_binding_audit.json",
    "payloadPcControls": GOAL / "clean_history_payload_pc_controls_audit.json",
    "pcUuidControls": GOAL / "clean_history_pc_uuid_controls_audit.json",
    "formOuterControls": GOAL / "clean_history_form_outer_controls_audit.json",
    "outerBindingControls": GOAL / "outer_binding_controls_audit.json",
    "forcedOverlapPayloadPcSplit": GOAL / "forced_overlap_payload_pc_split_control_audit.json",
    "requestContextDiff": GOAL / "collector_request_context_diff_s00_line933_vs_direct_seq5.json",
    "headerParityContextDiff": GOAL / "collector_request_context_diff_s00_line933_vs_direct_header_parity_seq5.json",
    "endToEndRemainingBoundary": HYP / "end_to_end_remaining_boundary_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def get(docs: dict[str, dict[str, Any]], name: str, key: str) -> Any:
    return checks(docs[name]).get(key)


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    request_diff = (docs["requestContextDiff"].get("diffs") or {})
    header_parity_diff = (docs["headerParityContextDiff"].get("diffs") or {})
    remaining_param_diff_keys = checks(docs["outerBinding"]).get("remainingParamDiffKeys") or []
    request_form_diff_keys = request_diff.get("formValueDiffKeys") or []
    header_parity_form_diff_keys = header_parity_diff.get("formValueDiffKeys") or []

    single_axis_rows = [
        {
            "axis": "exact_payload_plus_pc_with_fresh_outer",
            "status": "eliminated_as_success_candidate",
            "evidence": str(INPUTS["exactPayloadBody"]),
            "facts": {
                "exactPayloadPcReturnedDoEmpty": get(docs, "exactPayloadBody", "exactPayloadPcReturnedDoEmpty"),
                "exactPayloadPcNoSuccess": get(docs, "exactPayloadBody", "exactPayloadPcNoSuccess"),
            },
            "meaning": "Stale exact s00 payload+pc is not accepted in a fresh outer/session context.",
        },
        {
            "axis": "exact_whole_body_replay",
            "status": "eliminated_as_success_candidate",
            "evidence": str(INPUTS["exactPayloadBody"]),
            "facts": {
                "exactBodyRejectedMinusOne": get(docs, "exactPayloadBody", "exactBodyRejectedMinusOne"),
                "exactBodyNoSuccess": get(docs, "exactPayloadBody", "exactBodyNoSuccess"),
            },
            "meaning": "Byte-identical s00 body replay is not sufficient without the original live server/session state.",
        },
        {
            "axis": "pc_alone",
            "status": "eliminated_as_single_variable",
            "evidence": str(INPUTS["pcUuidControls"]),
            "facts": {
                "exactPayloadFreshPcReturnedDoEmpty": get(docs, "pcUuidControls", "exactPayloadFreshPcReturnedDoEmpty"),
                "freshPayloadTemplatePcRejected": get(docs, "pcUuidControls", "freshPayloadTemplatePcRejected"),
                "pcUuidControlImplemented": get(docs, "pcUuidControls", "pcUuidControlImplemented"),
            },
            "meaning": "PC mismatch does not explain either empty-do or normal -1 paths by itself.",
        },
        {
            "axis": "marker_or_payload_uuid_choice",
            "status": "eliminated_as_single_variable",
            "evidence": [
                str(INPUTS["payloadPcControls"]),
                str(INPUTS["outerBindingControls"]),
            ],
            "facts": {
                "templateMarkerRejected": get(docs, "payloadPcControls", "templateMarkerRejected"),
                "templateMarkerWholeActivitiesEqual": get(docs, "payloadPcControls", "templateMarkerWholeActivitiesEqual"),
                "templateMarkerNotSufficient": get(docs, "outerBindingControls", "templateMarkerNotSufficient"),
            },
            "meaning": "Fresh vs template marker/uuid encoding choice can preserve decoded equality but still fails.",
        },
        {
            "axis": "template_outer_with_fresh_payload_pc",
            "status": "eliminated_as_success_candidate",
            "evidence": str(INPUTS["formOuterControls"]),
            "facts": {
                "freshPayloadTemplateOuterReturnedDoEmpty": get(docs, "formOuterControls", "freshPayloadTemplateOuterReturnedDoEmpty"),
                "freshPayloadTemplateOuterDiffOnlyPayloadPc": get(docs, "formOuterControls", "freshPayloadTemplateOuterDiffOnlyPayloadPc"),
            },
            "meaning": "Using accepted outer params with fresh payload/pc still fails before normal success.",
        },
        {
            "axis": "forced_overlap_exact_payload_pc",
            "status": "eliminated_under_stronger_lineage",
            "evidence": str(INPUTS["forcedOverlapPayloadPcSplit"]),
            "facts": {
                "forcedFirstFailureResponseOrder": get(docs, "forcedOverlapPayloadPcSplit", "forcedFirstFailureResponseOrder"),
                "seq5PayloadAndPcExactS00": get(docs, "forcedOverlapPayloadPcSplit", "seq5PayloadAndPcExactS00"),
                "seq5FreshOuter": get(docs, "forcedOverlapPayloadPcSplit", "seq5FreshOuter"),
                "seq5ReturnedDoEmpty": get(docs, "forcedOverlapPayloadPcSplit", "seq5ReturnedDoEmpty"),
                "seq5NoOIIoIooo": get(docs, "forcedOverlapPayloadPcSplit", "seq5NoOIIoIooo"),
            },
            "meaning": "Even with stronger forced-overlap lineage, exact s00 payload+pc with fresh outer returns empty-do.",
        },
    ]

    coupled_boundary = {
        "id": "encoded_payload_pc_session_server_state_binding",
        "status": "coupled_remaining_boundary_not_promoted",
        "evidence": [
            str(INPUTS["encodedBoundary"]),
            str(INPUTS["requestContextDiff"]),
            str(INPUTS["outerBinding"]),
        ],
        "facts": {
            "decodedActivitiesEqual": get(docs, "encodedBoundary", "decodedActivitiesEqual"),
            "decodedFieldsEqual": get(docs, "encodedBoundary", "decodedFieldsEqual"),
            "bodyLenEqual": get(docs, "encodedBoundary", "bodyLenEqual"),
            "payloadLenEqual": get(docs, "encodedBoundary", "payloadLenEqual"),
            "encodedPayloadDiffers": get(docs, "encodedBoundary", "encodedPayloadDiffers"),
            "pcDiffers": get(docs, "encodedBoundary", "pcDiffers"),
            "onlyPayloadPcAndSessionParamsDiffer": get(docs, "encodedBoundary", "onlyPayloadPcAndSessionParamsDiffer"),
            "freshStillRejected": get(docs, "encodedBoundary", "freshStillRejected"),
            "requestContextSameUrl": get(docs, "requestContextDiff", "sameUrl"),
            "requestContextSameMethod": get(docs, "requestContextDiff", "sameMethod"),
            "requestContextSameFormOrder": get(docs, "requestContextDiff", "sameFormOrder"),
            "requestContextHeadersDifferOnlyExpectedLengthsAndProxyAuth": get(docs, "requestContextDiff", "headersDifferOnlyExpectedLengthsAndProxyAuth"),
            "requestFormDiffKeys": request_form_diff_keys,
            "remainingParamDiffKeys": remaining_param_diff_keys,
            "headerParityFormDiffKeys": header_parity_form_diff_keys,
        },
        "whyNotPromoted": (
            "The remaining diff set is a coupled bundle of payload, pc, and live session params "
            "(uuid/cs/sid/p1/vid/ci/cts plus sometimes rsc). Existing controls show individual payload/pc/marker/body/outer substitutions do not produce success."
        ),
    }

    eliminated_count = sum(1 for row in single_axis_rows if row["status"].startswith("eliminated"))
    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "singleAxisRowCount": len(single_axis_rows),
        "singleAxisEliminatedCount": eliminated_count,
        "exactPayloadPcNoSuccess": get(docs, "exactPayloadBody", "exactPayloadPcNoSuccess") is True,
        "exactBodyNoSuccess": get(docs, "exactPayloadBody", "exactBodyNoSuccess") is True,
        "pcAloneEliminated": get(docs, "pcUuidControls", "pcUuidControlImplemented") is True
        and get(docs, "pcUuidControls", "exactPayloadFreshPcReturnedDoEmpty") is True
        and get(docs, "pcUuidControls", "freshPayloadTemplatePcRejected") is True,
        "markerChoiceEliminated": get(docs, "outerBindingControls", "templateMarkerNotSufficient") is True,
        "templateOuterFreshPayloadPcNoSuccess": get(docs, "formOuterControls", "freshPayloadTemplateOuterReturnedDoEmpty") is True,
        "forcedOverlapExactPayloadPcNoSuccess": get(docs, "forcedOverlapPayloadPcSplit", "seq5ReturnedDoEmpty") is True,
        "decodedEqualButEncodedBoundaryRemains": get(docs, "encodedBoundary", "decodedActivitiesEqual") is True
        and get(docs, "encodedBoundary", "decodedFieldsEqual") is True
        and get(docs, "encodedBoundary", "freshStillRejected") is True,
        "remainingDiffKeysArePayloadPcSession": set(remaining_param_diff_keys) == {"payload", "uuid", "cs", "pc", "sid", "p1", "vid", "ci", "cts"},
        "promotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit whether the encoded payload/pc/session binding boundary can be promoted to a concrete single transition candidate.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "singleAxisRows": single_axis_rows,
        "remainingCoupledBoundary": coupled_boundary,
        "promotionGate": {
            "singleTransitionCandidateCount": 0,
            "readyForFreshExperiment": False,
            "reason": "Payload, pc, marker/uuid, outer params, exact body, and forced-overlap exact payload+pc controls are all negative; remaining boundary is coupled live session/server-state binding.",
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextEvidenceNeeded": (
                "A lineage proof that decomposes the coupled payload/pc/session/server-state boundary into one concrete "
                "pre-accept, client-visible, constructible field or state mutation not already contradicted by existing controls."
            ),
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
