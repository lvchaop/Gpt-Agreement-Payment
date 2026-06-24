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
OUT = GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"

INPUTS = {
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "hypothesisPlanCoverage": HYP / "hypothesis_plan_coverage_audit.json",
    "collectorServerExpectedState": HYP / "collector_server_expected_state_boundary_audit.json",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "minimalTransitionExperiment": HYP / "minimal_promoted_transition_experiment.json",
    "currentRouteAuthority": HYP / "current_route_authority_audit.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
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
    reset_checks = checks(docs["resetTerminal"])
    goal_summary = summary(docs["goalGap"])
    hyp_checks = checks(docs["hypothesisPlanCoverage"])
    server_checks = checks(docs["collectorServerExpectedState"])
    candidate_checks = checks(docs["candidateIntake"])
    minimal_checks = checks(docs["minimalTransitionExperiment"])
    route_checks = checks(docs["currentRouteAuthority"])
    completion_checks = checks(docs["completionRequirements"])

    ready = (
        reset_checks.get("readyForFreshExperiment") is True
        and reset_checks.get("singleTransitionCandidateCount") == 1
        and hyp_checks.get("currentPromotedSingleTransitionCandidateCount") == 1
        and server_checks.get("promotedSingleTransitionCandidateCount") == 1
        and candidate_checks.get("promotedSingleTransitionCandidateCount") == 1
        and minimal_checks.get("stageAdvanced") is True
    )

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "gateEvaluated": True,
        "readyForFreshExperiment": ready,
        "networkAttemptExecuted": False,
        "blockedByGate": not ready,
        "resetReadyForFreshExperiment": reset_checks.get("readyForFreshExperiment") is True,
        "resetNoCurrentRouteToPhase5": reset_checks.get("noCurrentRouteToPhase5") is True,
        "resetSingleTransitionCandidateCount": reset_checks.get("singleTransitionCandidateCount"),
        "hypothesisPlanPromotedCount": hyp_checks.get("currentPromotedSingleTransitionCandidateCount"),
        "collectorServerExpectedStatePromotedCount": server_checks.get("promotedSingleTransitionCandidateCount"),
        "candidateIntakePromotedCount": candidate_checks.get("promotedSingleTransitionCandidateCount"),
        "candidateIntakeReadyForFreshExperiment": candidate_checks.get("readyForFreshExperiment") is True,
        "minimalTransitionExperimentExists": bool(docs["minimalTransitionExperiment"]),
        "minimalTransitionExperimentBlockedByGate": minimal_checks.get("blockedByGate") is True,
        "minimalTransitionExperimentNetworkAttemptExecuted": minimal_checks.get("networkAttemptExecuted") is True,
        "minimalTransitionExperimentStageAdvanced": minimal_checks.get("stageAdvanced") is True,
        "currentRouteAuthorityPromotedCount": route_checks.get("currentPromotedSingleTransitionCandidateCount"),
        "completionFreshSuccessMissing": completion_checks.get("freshSuccessMissing") is True,
        "completionNoCurrentExperimentRoute": completion_checks.get("noCurrentExperimentRoute") is True,
        "goalMissingEndToEndPoc": "end_to_end_pure_protocol_poc" in (goal_summary.get("blockingOrMissing") or []),
        "freshNoBrowserCollectorSuccess": False,
        "freshDecodedOIIoIooo0": False,
        "freshDecodedPxJarReplayed": False,
        "freshRiskVerifyContinue": False,
        "freshCreateAccountRedirectUrl": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": (
            "Single evidence-gated entrypoint for the end-to-end pure-protocol HUMAN PoC. "
            "It refuses to run a network attempt unless current audits promote exactly one constructible transition."
        ),
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "attempt": {
            "executed": False,
            "reason": (
                "No network attempt executed because current terminal authority has no single promoted transition candidate."
                if not ready
                else "Gate is ready, but the live network PoC executor has not been implemented in this harness yet."
            ),
            "requiresBeforeExecution": {
                "singleTransitionCandidateCount": 1,
                "readyForFreshExperiment": True,
                "candidatePreAccept": True,
                "candidateClientVisible": True,
                "candidatePureProtocolConstructible": True,
                "candidateValueChainEnters": "request_or_cookie_or_risk_or_verify",
            },
        },
        "stageProof": {
            "collectorOIIoIooo0": False,
            "decodedPxJarReplay": False,
            "riskVerifyStateContinue": False,
            "createAccountRedirectUrl": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": ready,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Gate blocked: no fresh no-browser HUMAN PoC can be attempted from current evidence."
                if not ready
                else "Gate ready but no candidate-specific executor is attached."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
