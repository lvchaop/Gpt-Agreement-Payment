#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
GOAL = PROTO / "goal_audit"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"
OUT = GOAL / "final_pure_protocol_replay_audit.json"

INPUTS = {
    "evidenceGatedEndToEndPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "minimalTransitionExperiment": HYP / "minimal_promoted_transition_experiment.json",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    poc = checks(docs["evidenceGatedEndToEndPoc"])
    minimal = checks(docs["minimalTransitionExperiment"])
    intake = checks(docs["candidateIntake"])
    reset = checks(docs["resetTerminal"])
    completion = checks(docs["completionRequirements"])
    goal_summary = summary(docs["goalGap"])

    poc_complete = (
        poc.get("networkAttemptExecuted") is True
        and poc.get("freshNoBrowserCollectorSuccess") is True
        and poc.get("freshDecodedOIIoIooo0") is True
        and poc.get("freshDecodedPxJarReplayed") is True
        and poc.get("freshRiskVerifyContinue") is True
        and poc.get("freshCreateAccountRedirectUrl") is True
        and poc.get("goalComplete") is True
    )

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "gateEvaluated": True,
        "blockedByGate": not poc_complete,
        "readyForFreshReplay": poc_complete,
        "replayAttemptExecuted": False,
        "networkAttemptExecuted": False,
        "freshSessionIdRecorded": False,
        "transportEvidenceRecorded": False,
        "webshareOrDirectControlRecorded": False,
        "collectorRequestResponseRecorded": False,
        "decodedCollectorResponseRecorded": False,
        "pxJarMutationRecorded": False,
        "riskVerifyResponseRecorded": False,
        "createAccountResponseRecorded": False,
        "replayCommandsRecorded": False,
        "artifactHashesRecorded": False,
        "pocNetworkAttemptExecuted": poc.get("networkAttemptExecuted") is True,
        "pocFreshNoBrowserCollectorSuccess": poc.get("freshNoBrowserCollectorSuccess") is True,
        "pocFreshDecodedOIIoIooo0": poc.get("freshDecodedOIIoIooo0") is True,
        "pocFreshDecodedPxJarReplayed": poc.get("freshDecodedPxJarReplayed") is True,
        "pocFreshRiskVerifyContinue": poc.get("freshRiskVerifyContinue") is True,
        "pocFreshCreateAccountRedirectUrl": poc.get("freshCreateAccountRedirectUrl") is True,
        "minimalTransitionStageAdvanced": minimal.get("stageAdvanced") is True,
        "candidateIntakePromotedCount": intake.get("promotedSingleTransitionCandidateCount"),
        "resetReadyForFreshExperiment": reset.get("readyForFreshExperiment") is True,
        "completionFreshSuccessMissing": completion.get("freshSuccessMissing") is True,
        "goalMissingEndToEndPoc": "end_to_end_pure_protocol_poc" in (goal_summary.get("blockingOrMissing") or []),
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": (
            "Final replay audit harness for the pure-protocol HUMAN objective. It can prove completion only after "
            "the evidence-gated end-to-end PoC has produced a fresh no-browser success chain."
        ),
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "replay": {
            "executed": False,
            "freshSessionId": None,
            "transportEvidence": {},
            "webshareOrDirectControl": {},
            "collectorRequestResponse": {},
            "decodedCollectorResponse": {},
            "pxJarMutation": {},
            "riskVerifyResponse": {},
            "createAccountResponse": {},
            "replayCommands": [],
            "artifactHashes": {},
            "reason": (
                "Final replay is blocked because the evidence-gated end-to-end PoC has not produced a fresh no-browser success chain."
                if not poc_complete
                else "PoC completion evidence exists, but final replay execution is not implemented in this generic harness."
            ),
        },
        "evidenceBlocks": [
            {
                "id": "final_replay_gate",
                "facts": [
                    f"pocNetworkAttemptExecuted={checks_out['pocNetworkAttemptExecuted']}",
                    f"pocFreshNoBrowserCollectorSuccess={checks_out['pocFreshNoBrowserCollectorSuccess']}",
                    f"pocFreshDecodedOIIoIooo0={checks_out['pocFreshDecodedOIIoIooo0']}",
                    f"pocFreshRiskVerifyContinue={checks_out['pocFreshRiskVerifyContinue']}",
                    f"pocFreshCreateAccountRedirectUrl={checks_out['pocFreshCreateAccountRedirectUrl']}",
                    f"replayAttemptExecuted={checks_out['replayAttemptExecuted']}",
                    f"blockedByGate={checks_out['blockedByGate']}",
                ],
                "meaning": "The final replay completion gate is present and currently blocks completion because end-to-end PoC success is absent.",
            }
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Final replay is blocked until evidence_gated_end_to_end_pure_protocol_poc proves collector success, decoded _px jar replay, risk/verify continue, and CreateAccount redirectUrl."
                if not poc_complete
                else "PoC is complete; attach final replay executor before setting goalComplete."
            ),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
