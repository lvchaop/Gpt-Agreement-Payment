#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "encoder_variant_terminal_audit.json"
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
    pc = read_json(HYP / "remaining_encoder_pc_coherence_audit.json")
    candidate = read_json(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json")
    manifest = read_json(HYP / "coherent_encoder_variant_experiment_manifest.json")
    live = read_json(GOAL / "coherent_encoder_variant_live_probe_audit.json")

    c_coverage = coverage.get("checks") or {}
    c_pc = pc.get("checks") or {}
    c_candidate = candidate.get("checks") or {}
    c_manifest = manifest.get("checks") or {}
    c_live = live.get("checks") or {}

    checks = {
        "planExists": PLAN.exists(),
        "coverageAuditExists": bool(coverage),
        "pcCoherenceAuditExists": bool(pc),
        "candidateAuditExists": bool(candidate),
        "manifestExists": bool(manifest),
        "liveProbeAuditExists": bool(live),
        "initialRemainingVariantCount": c_coverage.get("builtVariantCount"),
        "liveControlEliminatedCount": c_coverage.get("liveControlEliminatedCount"),
        "openVariantCountAfterCoverage": c_coverage.get("openVariantCount"),
        "singleCoherentVariantFound": c_pc.get("singleCoherentVariant") is True,
        "candidateNotCoveredByPriorControls": c_candidate.get("candidateNotCoveredByPriorControls") is True,
        "manifestAuthorizedOneExperiment": c_manifest.get("readyForOneControlledFreshExperiment") is True,
        "liveProbeExecuted": c_live.get("executed") is True,
        "liveProbeFreshWebshareSession": c_live.get("freshWebshareSession") is True,
        "liveProbeAnyCollectorSuccess": c_live.get("anyCollectorSuccess") is True,
        "liveProbeSeq5ReturnedDoEmpty": c_live.get("seq5ReturnedDoEmpty") is True,
        "liveProbeSeq5ReturnedMinusOne": c_live.get("seq5ReturnedMinusOne") is True,
        "encoderVariantFamilyClosedNoSuccess": (
            c_coverage.get("builtVariantCount") == 4
            and c_coverage.get("liveControlEliminatedCount") == 2
            and c_pc.get("singleCoherentVariant") is True
            and c_manifest.get("readyForOneControlledFreshExperiment") is True
            and c_live.get("executed") is True
            and c_live.get("anyCollectorSuccess") is False
        ),
        "promotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Terminal audit for the remaining C5 encoder variant family after running the single coherent live probe.",
        "inputs": {
            "remainingEncoderVariantControlCoverage": str(HYP / "remaining_encoder_variant_control_coverage.json"),
            "remainingEncoderPcCoherenceAudit": str(HYP / "remaining_encoder_pc_coherence_audit.json"),
            "coherentEncoderVariantVsPriorControlsAudit": str(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json"),
            "coherentEncoderVariantExperimentManifest": str(HYP / "coherent_encoder_variant_experiment_manifest.json"),
            "coherentEncoderVariantLiveProbeAudit": str(GOAL / "coherent_encoder_variant_live_probe_audit.json"),
        },
        "checks": checks,
        "liveProbeSummary": {
            "artifacts": live.get("artifacts"),
            "checks": c_live,
            "responseSummary": live.get("responseSummary"),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "The remaining C5 encoder family is closed for current evidence: exact-payload variants were eliminated by prior controls, "
                "the only coherent untested variant was run once in a fresh Webshare session and returned {do:[]} with no collector success. "
                "No downstream risk/verify replay is justified from this branch."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
