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
OUT = HYP / "minimal_promoted_transition_experiment.json"

INPUTS = {
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "evidenceGatedEndToEndPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
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
    intake = docs["candidateIntake"]
    intake_checks = checks(intake)
    reset_checks = checks(docs["resetTerminal"])
    completion_checks = checks(docs["completionRequirements"])
    poc_checks = checks(docs["evidenceGatedEndToEndPoc"])
    goal_summary = summary(docs["goalGap"])
    candidates = intake.get("promotedCandidates") or []

    ready = (
        intake_checks.get("promotedSingleTransitionCandidateCount") == 1
        and intake_checks.get("readyForFreshExperiment") is True
        and reset_checks.get("readyForFreshExperiment") is True
        and len(candidates) == 1
    )
    candidate = candidates[0] if ready else None

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "gateEvaluated": True,
        "candidateIntakePromotedCount": intake_checks.get("promotedSingleTransitionCandidateCount"),
        "candidateIntakeReadyForFreshExperiment": intake_checks.get("readyForFreshExperiment") is True,
        "resetReadyForFreshExperiment": reset_checks.get("readyForFreshExperiment") is True,
        "resetNoCurrentRouteToPhase5": reset_checks.get("noCurrentRouteToPhase5") is True,
        "completionNoCurrentExperimentRoute": completion_checks.get("noCurrentExperimentRoute") is True,
        "evidenceGatedPocBlockedByGate": poc_checks.get("blockedByGate") is True,
        "goalMissingEndToEndPoc": "end_to_end_pure_protocol_poc" in (goal_summary.get("blockingOrMissing") or []),
        "readyForFreshExperiment": ready,
        "networkAttemptExecuted": False,
        "blockedByGate": not ready,
        "singleTransitionExperimentExecuted": False,
        "stageAdvanced": False,
        "advancedToDoEmpty": False,
        "advancedToCookieTokenHandler": False,
        "advancedToCollectorOIIoIooo0": False,
        "advancedToRiskVerifyContinue": False,
        "advancedToCreateAccountRedirectUrl": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": (
            "Minimal transition experiment harness for Phase C. It may execute network only after "
            "candidate intake promotes exactly one transition and terminal audit is ready."
        ),
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "attempt": {
            "sessionId": None,
            "freshSession": None,
            "transport": None,
            "proxyEvidence": {},
            "ipEvidence": {},
            "executed": False,
            "networkAttemptExecuted": False,
            "reason": (
                "Gate blocked: no unique promoted transition candidate exists, so no network attempt was executed."
                if not ready
                else "Gate ready, but candidate-specific executor is intentionally not implemented in this generic harness."
            ),
        },
        "candidate": candidate
        or {
            "id": None,
            "singleTransition": False,
            "preAccept": False,
            "clientVisible": False,
            "pureProtocolConstructible": False,
            "valueChain": None,
            "source": str(INPUTS["candidateIntake"]),
        },
        "stage": {
            "before": None,
            "after": None,
            "advanced": False,
            "milestones": {
                "seq5Minus1ToDoEmpty": False,
                "doEmptyToCookieTokenHandler": False,
                "cookieTokenHandlerToOIIoIooo0": False,
                "oIIoIooo0ToRiskVerifyContinue": False,
                "riskVerifyContinueToCreateAccountRedirectUrl": False,
            },
        },
        "evidenceBlocks": [
            {
                "id": "phase_c_gate",
                "facts": [
                    f"candidateIntakePromotedCount={checks_out['candidateIntakePromotedCount']}",
                    f"candidateIntakeReadyForFreshExperiment={checks_out['candidateIntakeReadyForFreshExperiment']}",
                    f"resetReadyForFreshExperiment={checks_out['resetReadyForFreshExperiment']}",
                    f"networkAttemptExecuted={checks_out['networkAttemptExecuted']}",
                    f"blockedByGate={checks_out['blockedByGate']}",
                ],
                "meaning": "The minimal transition experiment entrypoint exists and is reproducible; current evidence does not authorize network execution.",
            }
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": ready,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Phase C is blocked by evidence gate: candidate intake has no unique promoted transition."
                if not ready
                else "Phase C gate is open; attach a candidate-specific executor before network execution."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
