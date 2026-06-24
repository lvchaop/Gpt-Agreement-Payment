#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "remaining_encoder_variant_control_coverage.json"
PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def classify_variant(row: dict[str, Any], controls: dict[str, dict[str, Any]]) -> dict[str, Any]:
    variant = row.get("variant") or {}
    summary = row.get("summary") or {}
    comparison = row.get("comparison") or {}
    checks = summary.get("checks") or {}

    coverage: list[dict[str, Any]] = []
    eliminated = False
    still_open = True

    if comparison.get("payloadEqualsS00") is True and comparison.get("pcEqualsS00") is True:
        coverage.append(
            {
                "control": "forced_overlap_payload_pc_split_control",
                "evidence": str(GOAL / "forced_overlap_payload_pc_split_control_audit.json"),
                "result": "exact s00 payload+pc with fresh outer returned {do:[]}; no oIIoIooo handler",
                "checks": (controls["forcedExactPayloadPc"].get("checks") or {}),
            }
        )
        eliminated = True
        still_open = False

    if comparison.get("payloadEqualsS00") is True and comparison.get("pcEqualsSelectedFresh") is True:
        coverage.append(
            {
                "control": "clean_history_pc_uuid/exact_payload_fresh_pc",
                "evidence": str(GOAL / "clean_history_pc_uuid_controls_audit.json"),
                "result": "exact s00 payload with fresh-uuid pc returned {do:[]}; no handlers",
                "checks": (controls["pcUuid"].get("checks") or {}),
            }
        )
        eliminated = True
        still_open = False

    if checks.get("payloadUuidSource") == "template" and checks.get("markerSource") == "fresh":
        coverage.append(
            {
                "control": "offline_only_payload_family",
                "evidence": str(HYP / "remaining_encoder_variant_build_matrix.json"),
                "result": "payload differs from s00 and selected fresh while decoded base is equal; no live control for this exact template-uuid/fresh-marker payload family",
                "checks": {"decodedBaseEqualsS00": comparison.get("decodedBaseEqualsS00"), "payloadEqualsS00": comparison.get("payloadEqualsS00")},
            }
        )

    if checks.get("payloadUuidSource") == "template" and checks.get("pcUuidSource") == "fresh":
        coverage.append(
            {
                "control": "coherence_check_pc_uuid_vs_payload_uuid",
                "evidence": str(HYP / "remaining_encoder_variant_build_matrix.json"),
                "result": "pc is computed from fresh uuid while payload insertion uses template uuid; current evidence has not proven this mixed uuid pair is one coherent runtime transition",
                "checks": {
                    "payloadUuidSource": checks.get("payloadUuidSource"),
                    "pcUuidSource": checks.get("pcUuidSource"),
                    "pcEqualsSelectedFresh": comparison.get("pcEqualsSelectedFresh"),
                },
            }
        )

    return {
        "index": row.get("index"),
        "variant": variant,
        "summary": {
            "payloadSha256": summary.get("payloadSha256"),
            "pc": summary.get("pc"),
            "bodySha256": summary.get("bodySha256"),
            "markerSha256": summary.get("markerSha256"),
            "decodedBaseSha256": ((summary.get("decode") or {}).get("baseSha256")),
        },
        "comparison": comparison,
        "coverage": coverage,
        "eliminatedByExistingLiveControl": eliminated,
        "stillOpenAfterExistingControls": still_open,
        "reason": (
            "covered_by_existing_live_control"
            if eliminated
            else "not covered by existing live controls; however it remains a coupled encoder/session variant, not a single ready transition"
        ),
    }


def build() -> dict[str, Any]:
    matrix = read_json(HYP / "remaining_encoder_variant_build_matrix.json")
    controls = {
        "forcedExactPayloadPc": read_json(GOAL / "forced_overlap_payload_pc_split_control_audit.json"),
        "cleanPayloadPc": read_json(GOAL / "clean_history_payload_pc_controls_audit.json"),
        "pcUuid": read_json(GOAL / "clean_history_pc_uuid_controls_audit.json"),
        "outerBinding": read_json(GOAL / "outer_binding_controls_audit.json"),
    }
    rows = matrix.get("builtVariants") or []
    classified = [classify_variant(row, controls) for row in rows]
    open_rows = [row for row in classified if row["stillOpenAfterExistingControls"]]
    live_eliminated = [row for row in classified if row["eliminatedByExistingLiveControl"]]

    open_payloads = sorted({row["summary"]["payloadSha256"] for row in open_rows})
    open_pcs = sorted({row["summary"]["pc"] for row in open_rows})
    open_marker_sources = sorted({(row["variant"] or {}).get("markerSource") for row in open_rows})
    open_pc_uuid_sources = sorted({(row["variant"] or {}).get("pcUuidSource") for row in open_rows})

    checks = {
        "planExists": PLAN.exists(),
        "matrixExists": bool(matrix),
        "builtVariantCount": len(rows),
        "classifiedVariantCount": len(classified),
        "liveControlEliminatedCount": len(live_eliminated),
        "openVariantCount": len(open_rows),
        "openPayloadShaCount": len(open_payloads),
        "openPcCount": len(open_pcs),
        "openMarkerSourceCount": len(open_marker_sources),
        "openPcUuidSourceCount": len(open_pc_uuid_sources),
        "openVariantsSharePayload": len(open_payloads) == 1 if open_rows else False,
        "openVariantsOnlyDifferByPc": len(open_payloads) == 1 and len(open_pcs) == len(open_rows) and len(open_marker_sources) == 1,
        "singleReadyVariant": len(open_rows) == 1,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Classify the four remaining encoder variants against existing live controls before allowing any fresh network experiment.",
        "inputs": {
            "remainingEncoderVariantBuildMatrix": str(HYP / "remaining_encoder_variant_build_matrix.json"),
            "forcedOverlapPayloadPcSplitControl": str(GOAL / "forced_overlap_payload_pc_split_control_audit.json"),
            "cleanHistoryPayloadPcControls": str(GOAL / "clean_history_payload_pc_controls_audit.json"),
            "cleanHistoryPcUuidControls": str(GOAL / "clean_history_pc_uuid_controls_audit.json"),
            "outerBindingControls": str(GOAL / "outer_binding_controls_audit.json"),
        },
        "checks": checks,
        "classifiedVariants": classified,
        "openVariantSummary": {
            "openVariantIndexes": [row["index"] for row in open_rows],
            "openPayloadSha256": open_payloads,
            "openPcValues": open_pcs,
            "openMarkerSources": open_marker_sources,
            "openPcUuidSources": open_pc_uuid_sources,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(HYP / "remaining_encoder_pc_coherence_audit.json"),
            "nextScript": str(ROOT / "tools/build_remaining_encoder_pc_coherence_audit.py"),
            "reason": (
                "Existing live controls eliminate the exact-payload variants, but two variants with template payload uuid + fresh marker remain. "
                "They share the same payload and differ only by pc uuid source, so the next step is offline pc-coherence reduction, not network traffic."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "openVariantSummary": doc["openVariantSummary"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
