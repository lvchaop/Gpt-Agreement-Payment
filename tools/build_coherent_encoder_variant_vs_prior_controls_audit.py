#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "coherent_encoder_variant_vs_prior_controls_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> dict[str, Any]:
    pc = read_json(HYP / "remaining_encoder_pc_coherence_audit.json")
    matrix = read_json(HYP / "remaining_encoder_variant_build_matrix.json")
    outer = read_json(GOAL / "outer_binding_controls_audit.json")
    payload_pc = read_json(GOAL / "clean_history_payload_pc_controls_audit.json")
    pc_uuid = read_json(GOAL / "clean_history_pc_uuid_controls_audit.json")
    exact = read_json(GOAL / "forced_overlap_payload_pc_split_control_audit.json")

    candidate = pc.get("coherentVariant") or {}
    candidate_index = candidate.get("index")
    matrix_row = next((row for row in matrix.get("builtVariants") or [] if row.get("index") == candidate_index), {})
    summary = matrix_row.get("summary") or {}
    comparison = matrix_row.get("comparison") or {}
    candidate_checks = summary.get("checks") or {}

    prior_controls = [
        {
            "id": "outer_binding_fresh_outer_fresh_marker",
            "evidence": str(GOAL / "outer_binding_controls_audit.json"),
            "covered": False,
            "whyNotExactCoverage": "Prior freshOuterFreshMarker used fresh payload uuid/pc; candidate uses template payload uuid/template pc with fresh marker.",
            "relevantChecks": (outer.get("checks") or {}),
        },
        {
            "id": "outer_binding_fresh_outer_template_marker",
            "evidence": str(GOAL / "outer_binding_controls_audit.json"),
            "covered": False,
            "whyNotExactCoverage": "Prior freshOuterTemplateMarker used fresh payload uuid/pc and template marker; candidate uses template payload uuid/template pc and fresh marker.",
            "relevantChecks": (outer.get("checks") or {}),
        },
        {
            "id": "exact_payload_pc_fresh_outer",
            "evidence": str(GOAL / "forced_overlap_payload_pc_split_control_audit.json"),
            "covered": False,
            "whyNotExactCoverage": "Exact s00 payload+pc control uses template marker; candidate rebuilds payload with fresh marker while preserving template payload uuid and pc.",
            "relevantChecks": (exact.get("checks") or {}),
        },
        {
            "id": "clean_history_pc_uuid",
            "evidence": str(GOAL / "clean_history_pc_uuid_controls_audit.json"),
            "covered": False,
            "whyNotExactCoverage": "PC uuid controls cover exact-payload/fresh-pc and fresh-payload/template-pc families; candidate is rebuilt template-uuid payload with fresh marker and template pc.",
            "relevantChecks": (pc_uuid.get("checks") or {}),
        },
        {
            "id": "clean_history_payload_pc",
            "evidence": str(GOAL / "clean_history_payload_pc_controls_audit.json"),
            "covered": False,
            "whyNotExactCoverage": "Payload/pc controls cover exact payload+pc and template marker with fresh payload uuid; candidate uses fresh marker with template payload uuid.",
            "relevantChecks": (payload_pc.get("checks") or {}),
        },
    ]

    exact_prior_coverage = any(row["covered"] for row in prior_controls)
    candidate_is_single = bool(candidate) and candidate_checks.get("payloadUuidSource") == "template" and candidate_checks.get("markerSource") == "fresh" and candidate_checks.get("pcUuidSource") == "payload"
    negative_controls_cover_neighbors = all(bool(row.get("relevantChecks")) for row in prior_controls)

    checks = {
        "planExists": PLAN.exists(),
        "pcCoherenceExists": bool(pc),
        "matrixExists": bool(matrix),
        "hasSingleCoherentCandidate": candidate_is_single,
        "candidatePayloadUuidSourceTemplate": candidate_checks.get("payloadUuidSource") == "template",
        "candidateMarkerSourceFresh": candidate_checks.get("markerSource") == "fresh",
        "candidatePcUuidSourcePayload": candidate_checks.get("pcUuidSource") == "payload",
        "candidateDecodedBaseEqualsS00": comparison.get("decodedBaseEqualsS00") is True,
        "candidatePayloadNotEqualS00": comparison.get("payloadEqualsS00") is False,
        "candidatePcEqualsS00": comparison.get("pcEqualsS00") is True,
        "exactPriorCoverageFound": exact_prior_coverage,
        "neighborNegativeControlsPresent": negative_controls_cover_neighbors,
        "candidateNotCoveredByPriorControls": not exact_prior_coverage,
        "singleTransitionCandidateCount": 1 if candidate_is_single and not exact_prior_coverage else 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Check the single coherent encoder variant against existing live controls before any network experiment.",
        "inputs": {
            "remainingEncoderPcCoherenceAudit": str(HYP / "remaining_encoder_pc_coherence_audit.json"),
            "remainingEncoderVariantBuildMatrix": str(HYP / "remaining_encoder_variant_build_matrix.json"),
            "outerBindingControls": str(GOAL / "outer_binding_controls_audit.json"),
            "cleanHistoryPayloadPcControls": str(GOAL / "clean_history_payload_pc_controls_audit.json"),
            "cleanHistoryPcUuidControls": str(GOAL / "clean_history_pc_uuid_controls_audit.json"),
            "forcedOverlapPayloadPcSplitControl": str(GOAL / "forced_overlap_payload_pc_split_control_audit.json"),
        },
        "checks": checks,
        "candidate": {
            "index": candidate_index,
            "variant": candidate.get("variant"),
            "summary": {
                "payloadSha256": summary.get("payloadSha256"),
                "pc": summary.get("pc"),
                "bodySha256": summary.get("bodySha256"),
                "markerSha256": summary.get("markerSha256"),
                "checks": candidate_checks,
            },
            "comparison": comparison,
        },
        "priorControlComparison": prior_controls,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(HYP / "coherent_encoder_variant_experiment_manifest.json"),
            "nextScript": str(ROOT / "tools/build_coherent_encoder_variant_experiment_manifest.py"),
            "reason": (
                "One coherent encoder variant is not exactly covered by prior controls, but this audit does not itself authorize a network run. "
                "The next artifact must define a negative-control manifest and terminal gate for a single fresh-session experiment."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "candidate": doc["candidate"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
