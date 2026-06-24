#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
GOAL = PROTO / "goal_audit"
RESET = PROTO / "reset_plan"
OUT = HYP / "pure_protocol_impasse_audit.json"

INPUTS = {
    "nextEvidenceSurfaceDiscovery": HYP / "next_evidence_surface_discovery_audit.json",
    "exhaustiveCandidateResolution": HYP / "exhaustive_promotion_candidate_resolution_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
    "gateChain": GOAL / "pure_protocol_evidence_gate_chain_audit.json",
    "manifestVerify": GOAL / "pure_protocol_evidence_manifest_verify.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "evidenceGatedPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalReplay": GOAL / "final_pure_protocol_replay_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    c = {name: checks(doc) for name, doc in docs.items()}

    same_blocking_condition = (
        c["nextEvidenceSurfaceDiscovery"].get("newCandidateSurfaceCount") == 0
        and c["nextEvidenceSurfaceDiscovery"].get("openSurfaceCount") == 0
        and c["exhaustiveCandidateResolution"].get("proposalReadyCandidateCount") == 0
        and c["exhaustiveCandidateResolution"].get("openNeedsSpecificEvidenceCount") == 0
        and c["completionRequirements"].get("freshSuccessMissing") is True
        and c["completionRequirements"].get("noCurrentExperimentRoute") is True
        and c["resetTerminal"].get("noCurrentRouteToPhase5") is True
        and c["goalCompletionVerifier"].get("readyForFreshExperiment") is False
        and c["goalCompletionVerifier"].get("completionVerified") is False
    )
    no_meaningful_offline_next = (
        c["nextEvidenceSurfaceDiscovery"].get("surfaceCount") == c["nextEvidenceSurfaceDiscovery"].get("closedSurfaceCount")
        and c["nextEvidenceSurfaceDiscovery"].get("surfaceWithNewCandidateCount") == 0
        and c["exhaustiveCandidateResolution"].get("resolvedCandidateCount") == c["exhaustiveCandidateResolution"].get("candidateRowCount")
        and c["gateChain"].get("allStepsPassed") is True
        and c["manifestVerify"].get("allHashesMatch") is True
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "sameBlockingConditionRepeated": same_blocking_condition,
        "noMeaningfulOfflineNext": no_meaningful_offline_next,
        "candidateRowCount": c["exhaustiveCandidateResolution"].get("candidateRowCount"),
        "candidateProposalReadyCount": c["exhaustiveCandidateResolution"].get("proposalReadyCandidateCount"),
        "candidateOpenNeedsSpecificEvidenceCount": c["exhaustiveCandidateResolution"].get("openNeedsSpecificEvidenceCount"),
        "surfaceCount": c["nextEvidenceSurfaceDiscovery"].get("surfaceCount"),
        "surfaceClosedCount": c["nextEvidenceSurfaceDiscovery"].get("closedSurfaceCount"),
        "surfaceOpenCount": c["nextEvidenceSurfaceDiscovery"].get("openSurfaceCount"),
        "newCandidateSurfaceCount": c["nextEvidenceSurfaceDiscovery"].get("newCandidateSurfaceCount"),
        "freshSuccessMissing": c["completionRequirements"].get("freshSuccessMissing"),
        "noCurrentExperimentRoute": c["completionRequirements"].get("noCurrentExperimentRoute"),
        "resetNoCurrentRouteToPhase5": c["resetTerminal"].get("noCurrentRouteToPhase5"),
        "pocNetworkAttemptExecuted": c["evidenceGatedPoc"].get("networkAttemptExecuted"),
        "finalReplayAttemptExecuted": c["finalReplay"].get("replayAttemptExecuted"),
        "gateChainAllStepsPassed": c["gateChain"].get("allStepsPassed"),
        "manifestVerifyAllHashesMatch": c["manifestVerify"].get("allHashesMatch"),
        "completionVerified": c["goalCompletionVerifier"].get("completionVerified"),
        "readyForFreshExperiment": c["goalCompletionVerifier"].get("readyForFreshExperiment"),
        "goalComplete": c["goalCompletionVerifier"].get("goalComplete"),
        "blockedAuditThresholdSatisfied": same_blocking_condition and no_meaningful_offline_next,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit whether the active pure-protocol HUMAN objective is at an evidence impasse under the current local state.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "blocked": checks_out["blockedAuditThresholdSatisfied"],
            "reason": (
                "The current local evidence set has no open candidate, no new evidence surface, no fresh experiment route, and the final PoC remains missing."
                if checks_out["blockedAuditThresholdSatisfied"]
                else "The current state still has a candidate/surface/route that should be pursued before declaring an impasse."
            ),
            "requiredExternalStateChange": (
                "Provide or generate new local evidence such as a fresh trace/HAR/runtime hook/cookie timeline that is not already covered by the current surface audits."
                if checks_out["blockedAuditThresholdSatisfied"]
                else None
            ),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
