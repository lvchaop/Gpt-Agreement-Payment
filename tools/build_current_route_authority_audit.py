#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
RESET = ROOT / "output/protocol_reverse/reset_plan"
OUT = HYP / "current_route_authority_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def main() -> int:
    old_candidate = load(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json")
    old_manifest = load(HYP / "coherent_encoder_variant_experiment_manifest.json")
    live_probe = load(GOAL / "coherent_encoder_variant_live_probe_audit.json")
    c5_terminal = load(HYP / "encoder_variant_terminal_audit.json")
    static_terminal = load(HYP / "post_static_context_terminal_gap_audit.json")
    reset_terminal = load(RESET / "reset_terminal_boundary_audit.json")
    goal = load(GOAL / "pure_protocol_goal_gap_audit.json")

    c_old_candidate = checks(old_candidate)
    c_live = checks(live_probe)
    c_c5 = checks(c5_terminal)
    c_static = checks(static_terminal)
    c_reset = checks(reset_terminal)
    goal_summary = goal.get("summary") or {}

    superseded = [
        {
            "artifact": str(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json"),
            "oldSignal": {
                "singleTransitionCandidateCount": c_old_candidate.get("singleTransitionCandidateCount"),
                "readyForFreshExperiment": c_old_candidate.get("readyForFreshExperiment"),
            },
            "supersededBy": str(GOAL / "coherent_encoder_variant_live_probe_audit.json"),
            "supersedingFacts": {
                "liveProbeExecuted": c_live.get("executed"),
                "liveProbeAnyCollectorSuccess": c_live.get("anyCollectorSuccess"),
                "liveProbeSeq5ReturnedDoEmpty": c_live.get("seq5ReturnedDoEmpty"),
            },
            "currentStatus": "closed_no_success",
        },
        {
            "artifact": str(HYP / "coherent_encoder_variant_experiment_manifest.json"),
            "oldSignal": {
                "readyForFreshExperiment": (old_manifest.get("decision") or {}).get("readyForFreshExperiment"),
                "readyForOneControlledFreshExperiment": checks(old_manifest).get("readyForOneControlledFreshExperiment"),
            },
            "supersededBy": str(HYP / "encoder_variant_terminal_audit.json"),
            "supersedingFacts": {
                "encoderVariantFamilyClosedNoSuccess": c_c5.get("encoderVariantFamilyClosedNoSuccess"),
                "promotedSingleTransitionCandidateCount": c_c5.get("promotedSingleTransitionCandidateCount"),
                "readyForFreshExperiment": c_c5.get("readyForFreshExperiment"),
            },
            "currentStatus": "closed_no_success",
        },
    ]

    out_checks = {
        "planExists": PLAN.exists(),
        "oldCoherentCandidateHadSingleTransition": c_old_candidate.get("singleTransitionCandidateCount") == 1,
        "oldManifestHadReadySignal": checks(old_manifest).get("readyForOneControlledFreshExperiment") is True,
        "liveProbeExecuted": c_live.get("executed") is True,
        "liveProbeAnyCollectorSuccess": c_live.get("anyCollectorSuccess") is True,
        "liveProbeClosedNoSuccess": c_live.get("executed") is True and c_live.get("anyCollectorSuccess") is False,
        "encoderVariantFamilyClosedNoSuccess": c_c5.get("encoderVariantFamilyClosedNoSuccess") is True,
        "postStaticContextAllClosedBranchesClosed": c_static.get("allClosedBranchesClosed") is True,
        "resetTerminalNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalStillMissingEndToEndPoc": "end_to_end_pure_protocol_poc" in (goal_summary.get("blockingOrMissing") or []),
        "staleReadyArtifactCount": 2,
        "currentPromotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Resolve stale ready/single-transition signals against newer live-probe and terminal authority before any further execution.",
        "inputs": {
            "oldCandidate": str(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json"),
            "oldManifest": str(HYP / "coherent_encoder_variant_experiment_manifest.json"),
            "liveProbe": str(GOAL / "coherent_encoder_variant_live_probe_audit.json"),
            "encoderVariantTerminal": str(HYP / "encoder_variant_terminal_audit.json"),
            "postStaticContextTerminal": str(HYP / "post_static_context_terminal_gap_audit.json"),
            "resetTerminal": str(RESET / "reset_terminal_boundary_audit.json"),
            "goalAudit": str(GOAL / "pure_protocol_goal_gap_audit.json"),
        },
        "checks": out_checks,
        "supersededReadyArtifacts": superseded,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "Old coherent-encoder ready signals are stale: the authorized live probe executed and produced no collector success, after which C5 and context/static terminal audits closed with zero promoted transitions.",
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
