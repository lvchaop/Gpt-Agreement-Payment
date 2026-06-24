#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "encoder_axis_equivalence.json"

INPUTS = {
    "coupledBoundaryReductionPlan": BASE / "coupled_boundary_reduction_plan.json",
    "remainingEncoderVariantBuildMatrix": BASE / "remaining_encoder_variant_build_matrix.json",
    "coupledEncoderVariantAudit": BASE / "coupled_encoder_variant_audit.json",
    "encodedPayloadPcFormDiffMap": BASE / "encoded_payload_pc_form_diff_map.json",
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        value = ((row.get("variant") or {}).get(key))
        grouped[str(value)].append(row.get("index"))
    return dict(grouped)


def group_by_summary(rows: list[dict[str, Any]], key: str) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        value = ((row.get("summary") or {}).get(key))
        grouped[str(value)].append(row.get("index"))
    return dict(grouped)


def variant_projection(row: dict[str, Any]) -> dict[str, Any]:
    variant = row.get("variant") or {}
    summary = row.get("summary") or {}
    comp = row.get("comparison") or {}
    return {
        "index": row.get("index"),
        "payloadUuidSource": variant.get("payloadUuidSource"),
        "pcUuidSource": variant.get("pcUuidSource"),
        "markerSource": variant.get("markerSource"),
        "formOuterSource": variant.get("formOuterSource"),
        "payloadSource": variant.get("payloadSource"),
        "pcSource": variant.get("pcSource"),
        "payloadSha256": summary.get("payloadSha256"),
        "pc": summary.get("pc"),
        "pcSha256": summary.get("pcSha256"),
        "bodySha256": summary.get("bodySha256"),
        "markerSha256": summary.get("markerSha256"),
        "decodedBaseSha256": ((summary.get("decode") or {}).get("baseSha256")),
        "payloadEqualsS00": comp.get("payloadEqualsS00"),
        "pcEqualsS00": comp.get("pcEqualsS00"),
        "decodedBaseEqualsS00": comp.get("decodedBaseEqualsS00"),
    }


def axis_row(axis: str, groups: dict[str, list[int]], conclusion: str) -> dict[str, Any]:
    return {
        "axis": axis,
        "valueCount": len(groups),
        "groups": groups,
        "singleAxis": len(groups) == 1,
        "conclusion": conclusion,
    }


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    reduction = docs["coupledBoundaryReductionPlan"]
    matrix = docs["remainingEncoderVariantBuildMatrix"]
    variants = matrix.get("builtVariants") or []
    projections = [variant_projection(row) for row in variants]

    axes = [
        axis_row(
            "markerSource",
            group_by(variants, "markerSource"),
            "markerSource has two values and exactly determines payloadSha256 in the remaining 2x2 family.",
        ),
        axis_row(
            "pcUuidSource",
            group_by(variants, "pcUuidSource"),
            "pcUuidSource has two values and exactly determines pc/pcSha256 in the remaining 2x2 family.",
        ),
        axis_row(
            "payloadUuidSource",
            group_by(variants, "payloadUuidSource"),
            "constant template payload uuid across remaining variants.",
        ),
        axis_row(
            "formOuterSource",
            group_by(variants, "formOuterSource"),
            "constant fresh outer across remaining variants.",
        ),
    ]

    payload_groups = group_by_summary(variants, "payloadSha256")
    pc_groups = group_by_summary(variants, "pcSha256")
    body_groups = group_by_summary(variants, "bodySha256")
    decoded_groups = defaultdict(list)
    for row in variants:
        decoded_groups[str(((row.get("summary") or {}).get("decode") or {}).get("baseSha256"))].append(row.get("index"))

    marker_to_payload_ok = True
    for marker, idxs in group_by(variants, "markerSource").items():
        payloads = {projections[i]["payloadSha256"] for i in idxs}
        marker_to_payload_ok = marker_to_payload_ok and len(payloads) == 1

    pc_uuid_to_pc_ok = True
    for pc_uuid, idxs in group_by(variants, "pcUuidSource").items():
        pcs = {projections[i]["pcSha256"] for i in idxs}
        pc_uuid_to_pc_ok = pc_uuid_to_pc_ok and len(pcs) == 1

    independent_2x2 = (
        len(group_by(variants, "markerSource")) == 2
        and len(group_by(variants, "pcUuidSource")) == 2
        and len(payload_groups) == 2
        and len(pc_groups) == 2
        and marker_to_payload_ok
        and pc_uuid_to_pc_ok
        and len(body_groups) == 4
    )

    checks = {
        "reductionPlanHasT2": any(t.get("id") == "T2_encoder_axis_equivalence" for t in reduction.get("reductionTracks", [])),
        "builtAllRemainingVariants": (matrix.get("checks") or {}).get("builtAllRemainingVariants") is True,
        "variantCountIsFour": len(variants) == 4,
        "allDecodedBaseEqual": len(decoded_groups) == 1,
        "markerSourceValueCount": len(group_by(variants, "markerSource")),
        "pcUuidSourceValueCount": len(group_by(variants, "pcUuidSource")),
        "payloadSha256ValueCount": len(payload_groups),
        "pcSha256ValueCount": len(pc_groups),
        "bodySha256ValueCount": len(body_groups),
        "markerSourceDeterminesPayload": marker_to_payload_ok,
        "pcUuidSourceDeterminesPc": pc_uuid_to_pc_ok,
        "remainingFamilyIsIndependent2x2": independent_2x2,
        "remainingEncoderAxisCount": 2 if independent_2x2 else None,
        "singleEncoderAxisIsolated": False,
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "The remaining encoder variants are an independent 2x2 family: markerSource determines payload, pcUuidSource determines pc, "
            "all decoded bases are equal, and all four bodies differ. No single encoder axis is isolated."
        ),
        "nextArtifact": str(BASE / "server_expected_state_observable_proxy.json"),
        "nextScript": str(REPO / "tools/build_server_expected_state_observable_proxy.py"),
    }

    return {
        "artifact": str(OUT),
        "purpose": "Reduce C5 encoder binding variants to one axis if evidence allows; otherwise prove the remaining family is multi-axis.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "variantProjections": projections,
        "axisGroups": axes,
        "equivalenceGroups": {
            "payloadSha256": payload_groups,
            "pcSha256": pc_groups,
            "bodySha256": body_groups,
            "decodedBaseSha256": dict(decoded_groups),
        },
        "summary": {
            "variantCount": len(variants),
            "uniquePayloadCount": len(payload_groups),
            "uniquePcCount": len(pc_groups),
            "uniqueBodyCount": len(body_groups),
            "uniqueDecodedBaseCount": len(decoded_groups),
            "independentAxes": ["markerSource", "pcUuidSource"] if independent_2x2 else [],
            "remainingEncoderAxisCount": checks["remainingEncoderAxisCount"],
            "singleEncoderAxisIsolated": False,
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
