#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "server_state_value_consumption_ledger.json"

INPUTS = {
    "serverExpectedStatePreSeq5Gap": HYP / "server_expected_state_pre_seq5_gap.json",
    "serverStateTransitionValueModel": HYP / "server_state_transition_value_model.json",
    "serverStateValueToRequestLineage": HYP / "server_state_value_to_request_lineage.json",
    "line922DynamicFieldSourceMap": HYP / "line922_dynamic_field_source_map.json",
    "encodedPayloadPcFormDiffMap": HYP / "encoded_payload_pc_form_diff_map.json",
    "forcedOverlapTemplateBoundary": GOAL / "forced_overlap_template_final_encoded_decoded_boundary_audit.json",
    "forcedOverlapPayloadPcSplit": GOAL / "forced_overlap_payload_pc_split_control_audit.json",
    "outerBindingControls": GOAL / "outer_binding_controls_audit.json",
    "freshTailStrongestControl": GOAL / "h2_fresh_tail_strongest_control_audit.json",
    "px561StatefulRetry": GOAL / "px561_stateful_retry_audit.json",
    "cookieSessionLineageGap": GOAL / "cookie_session_lineage_gap_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def map_field(field: str) -> dict[str, Any]:
    mappings: dict[str, dict[str, Any]] = {
        "px3": {
            "consumedBy": ["decoded activity _px3 field", "cookie jar state"],
            "status": "consumed_but_negative_controlled",
            "negativeControls": ["px561StatefulRetry", "forcedOverlapTemplateBoundary", "cookieSessionLineageGap"],
            "reason": "_px3 is represented in decoded activities/cookie state, but decoded equality and stateful retry controls still reject.",
        },
        "pxde": {
            "consumedBy": ["cookie jar state", "risk/verify downstream material"],
            "status": "downstream_or_failure_mutation_not_collector_acceptance",
            "negativeControls": ["px561StatefulRetry", "cookieSessionLineageGap"],
            "reason": "_pxde mutation exists in rejected paths and is not a primary collector Cookie header transition.",
        },
        "zo": {
            "consumedBy": ["response-local token state"],
            "status": "session_specific_not_request_isolated",
            "negativeControls": [],
            "reason": "No evidence maps this value to one final request field whose mutation is independently controllable.",
        },
        "jo": {
            "consumedBy": ["payload marker/sid derivation"],
            "status": "consumed_but_coupled",
            "negativeControls": ["outerBindingControls", "forcedOverlapTemplateBoundary"],
            "reason": "jo participates in marker/session derivation, but marker/static payload variants are already negative and remaining binding is coupled.",
        },
        "qo": {
            "consumedBy": ["response-local token state"],
            "status": "session_specific_not_request_isolated",
            "negativeControls": [],
            "reason": "No evidence maps this value to a replayable final collector request field.",
        },
        "gl": {
            "consumedBy": ["response-local token state"],
            "status": "session_specific_not_request_isolated",
            "negativeControls": [],
            "reason": "No evidence maps this value to a replayable final collector request field.",
        },
        "cs": {
            "consumedBy": ["form.cs", "payload meta.cs"],
            "status": "consumed_but_coupled",
            "negativeControls": ["forcedOverlapPayloadPcSplit", "outerBindingControls"],
            "reason": "cs is consumed by final request state but belongs to the coherent outer/session tuple, not a single accepted transition.",
        },
        "powSeed": {
            "consumedBy": ["POW challenge input"],
            "status": "consumed_but_negative_controlled",
            "negativeControls": ["freshTailStrongestControl"],
            "reason": "fresh POW/tail correctness has already been controlled and still rejected.",
        },
        "powTarget": {
            "consumedBy": ["POW challenge input"],
            "status": "consumed_but_negative_controlled",
            "negativeControls": ["freshTailStrongestControl"],
            "reason": "fresh POW/tail correctness has already been controlled and still rejected.",
        },
        "ci": {
            "consumedBy": ["form.ci", "decoded activity ci-like field"],
            "status": "consumed_but_coupled",
            "negativeControls": ["forcedOverlapTemplateBoundary", "forcedOverlapPayloadPcSplit"],
            "reason": "ci is consumed but decoded equality/fresh-outer controls still reject; it remains part of seq4-response state tuple.",
        },
        "ciToken": {
            "consumedBy": ["ci/session verifier state"],
            "status": "session_specific_not_request_isolated",
            "negativeControls": [],
            "reason": "No current artifact exposes this as a standalone replayable request/cookie/risk transition.",
        },
    }
    return mappings.get(
        field,
        {
            "consumedBy": [],
            "status": "unmapped",
            "negativeControls": [],
            "reason": "Field has no explicit consumption mapping in this ledger.",
        },
    )


def negative_control_exists(control: str) -> bool:
    path_by_control = {
        "px561StatefulRetry": INPUTS["px561StatefulRetry"],
        "forcedOverlapTemplateBoundary": INPUTS["forcedOverlapTemplateBoundary"],
        "cookieSessionLineageGap": INPUTS["cookieSessionLineageGap"],
        "outerBindingControls": INPUTS["outerBindingControls"],
        "forcedOverlapPayloadPcSplit": INPUTS["forcedOverlapPayloadPcSplit"],
        "freshTailStrongestControl": INPUTS["freshTailStrongestControl"],
    }
    return path_by_control.get(control, Path("/missing")).exists()


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    state_gap = docs["serverExpectedStatePreSeq5Gap"]
    model = docs["serverStateTransitionValueModel"]
    value_lineage = docs["serverStateValueToRequestLineage"]
    line922 = docs["line922DynamicFieldSourceMap"]
    encoded = docs["encodedPayloadPcFormDiffMap"]

    rows: list[dict[str, Any]] = []
    for item in state_gap.get("valueComparisons") or []:
        field = item.get("field")
        mapped = map_field(str(field))
        controls = mapped["negativeControls"]
        row = {
            "field": field,
            "bothPresent": item.get("bothPresent"),
            "equal": item.get("equal"),
            "s00Sha256": item.get("s00Sha256"),
            "freshSha256": item.get("freshSha256"),
            "consumedBy": mapped["consumedBy"],
            "status": mapped["status"],
            "negativeControls": controls,
            "negativeControlsExist": all(negative_control_exists(control) for control in controls) if controls else True,
            "proposalReady": False,
            "reason": mapped["reason"],
        }
        rows.append(row)

    status_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    consumed_rows = [row for row in rows if row["consumedBy"]]
    negative_controlled_or_coupled = [
        row
        for row in rows
        if row["status"] in {
            "consumed_but_negative_controlled",
            "downstream_or_failure_mutation_not_collector_acceptance",
            "consumed_but_coupled",
            "session_specific_not_request_isolated",
        }
    ]

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "valueComparisonCount": len(rows),
        "valueMismatchCount": sum(1 for row in rows if row["equal"] is False),
        "consumedValueCount": len(consumed_rows),
        "statusCounts": status_counts,
        "allNegativeControlRefsExist": all(row["negativeControlsExist"] for row in rows),
        "allRowsCoveredByControlOrCoupling": len(negative_controlled_or_coupled) == len(rows),
        "singleValueProposalReadyCount": sum(1 for row in rows if row["proposalReady"] is True),
        "serverStateModelFinalS00Success": checks(model).get("finalS00Success") is True,
        "serverStateModelFinalFreshRejected": checks(model).get("finalFreshRejected") is True,
        "line922DecodedFieldsEqual": (line922.get("summary") or {}).get("freshSeq5ChangedFieldInstances") == 0,
        "stateLineageHasServerAcceptanceBoundary": checks(value_lineage).get("hasServerAcceptanceStateBoundary") is True,
        "encodedDecodedJsonEqual": checks(encoded).get("decodedJsonEqual") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Map seq4 response value mismatches to final request/payload/cookie/risk consumption surfaces and decide whether any single value can become a fresh experiment.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "rows": rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Seq4 value mismatches are either already consumed by negatively controlled surfaces, part of coupled session/encoder state, "
                "or not mapped to a standalone replayable request/cookie/risk transition."
            ),
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
