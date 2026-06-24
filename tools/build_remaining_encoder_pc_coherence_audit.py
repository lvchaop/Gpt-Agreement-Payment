#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "remaining_encoder_pc_coherence_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> dict[str, Any]:
    coverage = read_json(HYP / "remaining_encoder_variant_control_coverage.json")
    matrix = read_json(HYP / "remaining_encoder_variant_build_matrix.json")
    pc_uuid = read_json(GOAL / "clean_history_pc_uuid_controls_audit.json")
    outer = read_json(GOAL / "outer_binding_controls_audit.json")
    open_indexes = set((coverage.get("openVariantSummary") or {}).get("openVariantIndexes") or [])
    rows = [row for row in matrix.get("builtVariants") or [] if row.get("index") in open_indexes]

    classified = []
    for row in rows:
        variant = row.get("variant") or {}
        summary = row.get("summary") or {}
        comparison = row.get("comparison") or {}
        checks = summary.get("checks") or {}
        pc_source = checks.get("pcUuidSource")
        evidence = []
        coherent = None
        if pc_source == "payload":
            coherent = True
            evidence.append(
                {
                    "id": "pc_matches_payload_inserted_uuid",
                    "fact": "pc equals template pc while payload uuid source is template; this is internally coherent for the built payload.",
                    "value": summary.get("pc"),
                }
            )
        elif pc_source == "fresh":
            coherent = False
            evidence.append(
                {
                    "id": "pc_mixed_with_different_payload_uuid",
                    "fact": "pc equals selected fresh pc but payload uuid source remains template; current artifacts do not show this mixed pair as a runtime-produced transition.",
                    "value": summary.get("pc"),
                }
            )
            evidence.append(
                {
                    "id": "fresh_payload_template_pc_negative_control",
                    "fact": "The inverse pc mismatch family is already negatively controlled: fresh-uuid payload with template-uuid pc reaches normal rejection.",
                    "checks": pc_uuid.get("checks"),
                }
            )

        classified.append(
            {
                "index": row.get("index"),
                "variant": variant,
                "pcUuidSource": pc_source,
                "payloadSha256": summary.get("payloadSha256"),
                "pc": summary.get("pc"),
                "pcEqualsS00": comparison.get("pcEqualsS00"),
                "pcEqualsSelectedFresh": comparison.get("pcEqualsSelectedFresh"),
                "payloadEqualsS00": comparison.get("payloadEqualsS00"),
                "payloadEqualsSelectedFresh": comparison.get("payloadEqualsSelectedFresh"),
                "decodedBaseEqualsS00": comparison.get("decodedBaseEqualsS00"),
                "internallyCoherentPayloadPcPair": coherent,
                "evidence": evidence,
            }
        )

    coherent_rows = [row for row in classified if row["internallyCoherentPayloadPcPair"] is True]
    incoherent_rows = [row for row in classified if row["internallyCoherentPayloadPcPair"] is False]

    checks = {
        "planExists": PLAN.exists(),
        "coverageExists": bool(coverage),
        "matrixExists": bool(matrix),
        "openVariantCount": len(rows),
        "coherentPayloadPcPairCount": len(coherent_rows),
        "incoherentPayloadPcPairCount": len(incoherent_rows),
        "singleCoherentVariant": len(coherent_rows) == 1,
        "coherentVariantAlreadySent": False,
        "outerBindingFreshMarkerControlExists": (outer.get("checks") or {}).get("freshOuterFreshMarkerActivitiesEqualRejected") is True,
        "pcMismatchControlExists": (pc_uuid.get("checks") or {}).get("freshPayloadTemplatePcRejected") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Reduce the two open encoder variants by checking whether pc is coherent with the payload uuid source.",
        "inputs": {
            "remainingEncoderVariantControlCoverage": str(HYP / "remaining_encoder_variant_control_coverage.json"),
            "remainingEncoderVariantBuildMatrix": str(HYP / "remaining_encoder_variant_build_matrix.json"),
            "cleanHistoryPcUuidControls": str(GOAL / "clean_history_pc_uuid_controls_audit.json"),
            "outerBindingControls": str(GOAL / "outer_binding_controls_audit.json"),
        },
        "checks": checks,
        "classifiedOpenVariants": classified,
        "coherentVariant": coherent_rows[0] if len(coherent_rows) == 1 else None,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json"),
            "nextScript": str(ROOT / "tools/build_coherent_encoder_variant_vs_prior_controls_audit.py"),
            "reason": (
                "Only one open variant has an internally coherent payload/pc pair, but it is still not authorized for network testing. "
                "It must first be checked against prior outer-binding live controls to determine whether it is already covered by a broader rejected family."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "coherentVariant": doc["coherentVariant"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
