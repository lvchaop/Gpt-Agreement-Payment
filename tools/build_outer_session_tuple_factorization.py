#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "outer_session_tuple_factorization.json"

INPUTS = {
    "coupledBoundaryReductionPlan": BASE / "coupled_boundary_reduction_plan.json",
    "serverStateValueToRequestLineage": BASE / "server_state_value_to_request_lineage.json",
    "serverObservableStateInventory": BASE / "server_observable_state_inventory.json",
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
    "encodedPayloadPcFormDiffMap": BASE / "encoded_payload_pc_form_diff_map.json",
}

FIELDS = ["uuid", "cs", "ci", "sid", "p1", "vid", "cts"]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_group(source: str) -> str:
    low = source.lower()
    if "seq4" in low:
        return "seq4_response_state"
    if "bootstrap" in low:
        return "bootstrap_session_state"
    if "derived" in low or "sidwith" in low or "jo" in low:
        return "derived_session_state"
    if "session" in low:
        return "bootstrap_session_state"
    return "unknown"


def consumed_group(consumed_by: list[str]) -> list[str]:
    groups: list[str] = []
    for item in consumed_by:
        if item.startswith("form."):
            groups.append("outer_form")
        elif item.startswith("tfPayload.meta"):
            groups.append("payload_meta")
        elif "payload marker" in item:
            groups.append("payload_encoding")
        elif "captcha activity" in item:
            groups.append("decoded_activity")
        elif "iframe" in item:
            groups.append("microsoft_iframe_context")
        else:
            groups.append("other")
    return sorted(set(groups))


def factorize_rows(lineage: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    by_field = {row.get("requestField"): row for row in lineage.get("requestValueLineage", [])}
    for field in FIELDS:
        row = by_field.get(field) or {}
        src = row.get("source") or ""
        consumed = row.get("consumedBy") or []
        controls = row.get("existingControlCoverage") or []
        rows.append(
            {
                "field": field,
                "s00ValueSha256": row.get("s00ValueSha256"),
                "freshValueSha256": row.get("freshValueSha256"),
                "equal": row.get("equal"),
                "source": src,
                "sourceGroup": source_group(src),
                "consumedBy": consumed,
                "consumedGroups": consumed_group(consumed),
                "existingControlCoverage": controls,
                "negativeControlCovered": bool(controls),
                "serverObservable": True,
                "singleFieldExperimentReady": False,
                "whyNotSingleField": "Field is part of a source/consumption tuple; current evidence does not show independent server acceptance impact.",
            }
        )
    return rows


def group_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["sourceGroup"], []).append(row)
    result = []
    for group, members in sorted(groups.items()):
        consumed = sorted({g for row in members for g in row["consumedGroups"]})
        result.append(
            {
                "id": group,
                "fields": [row["field"] for row in members],
                "fieldCount": len(members),
                "consumedGroups": consumed,
                "allFieldsNegativeControlCovered": all(row["negativeControlCovered"] for row in members),
                "singleVariable": len(members) == 1,
                "serverObservable": True,
                "readyForFreshExperiment": False,
                "reason": (
                    "Single-member group still lacks evidence that this field independently changes acceptance."
                    if len(members) == 1
                    else "Multiple fields share source lineage and cannot be mutated as one isolated request transition."
                ),
            }
        )
    return result


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    reduction = docs["coupledBoundaryReductionPlan"]
    lineage = docs["serverStateValueToRequestLineage"]
    rows = factorize_rows(lineage)
    groups = group_rows(rows)
    ready_groups = [g for g in groups if g["readyForFreshExperiment"]]
    singleton_groups = [g for g in groups if g["singleVariable"]]
    multi_groups = [g for g in groups if not g["singleVariable"]]

    checks = {
        "reductionPlanRequiresThisArtifact": (reduction.get("decision") or {}).get("nextArtifact") == str(OUT),
        "hasAllOuterTupleFields": sorted(row["field"] for row in rows) == sorted(FIELDS),
        "allFieldsDiffer": all(row["equal"] is False for row in rows),
        "hasBootstrapSessionGroup": any(g["id"] == "bootstrap_session_state" for g in groups),
        "hasSeq4ResponseGroup": any(g["id"] == "seq4_response_state" for g in groups),
        "hasDerivedSessionGroup": any(g["id"] == "derived_session_state" for g in groups),
        "sourceGroupCount": len(groups),
        "singletonSourceGroupCount": len(singleton_groups),
        "multiFieldSourceGroupCount": len(multi_groups),
        "singleReadyGroupCount": len(ready_groups),
        "noSingleFieldExperimentReady": len(ready_groups) == 0,
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "Outer tuple factorization splits the fields into bootstrap/session, seq4-response, and derived-session groups, "
            "but no group has evidence that one independently mutable field changes collector acceptance. This keeps C4 as coupled."
        ),
        "nextArtifact": str(BASE / "encoder_axis_equivalence.json"),
        "nextScript": str(REPO / "tools/build_encoder_axis_equivalence.py"),
    }

    return {
        "artifact": str(OUT),
        "purpose": "Factor C4 outer session tuple into source/consumption groups and decide whether any field is a single transition.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "fieldRows": rows,
        "sourceGroups": groups,
        "summary": {
            "fieldCount": len(rows),
            "sourceGroupCount": len(groups),
            "singletonSourceGroupIds": [g["id"] for g in singleton_groups],
            "multiFieldSourceGroupIds": [g["id"] for g in multi_groups],
            "singleReadyGroupCount": len(ready_groups),
            "readyGroupIds": [g["id"] for g in ready_groups],
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
