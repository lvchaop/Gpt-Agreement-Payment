#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
RESET_DIR = PROTO / "reset_plan"
STATE_MACHINE = RESET_DIR / "reset_state_machine.json"
FINAL_CLASS = RESET_DIR / "reset_final_response_class_audit.json"
COOKIE_MUTATION = RESET_DIR / "reset_cookie_mutation_audit.json"
OUT = RESET_DIR / "reset_single_transition_candidates.json"
PLAN = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def abs_path(path: Path) -> str:
    return str(path.resolve())


def main() -> int:
    state = read_json(STATE_MACHINE)
    final_class = read_json(FINAL_CLASS)
    cookie = read_json(COOKIE_MUTATION)

    candidate_proxies = state.get("candidateClientVisibleProxies") or []
    replayable_proxies = [
        row for row in candidate_proxies
        if row.get("clientVisibleProxy") is True
    ]
    outcome_only = [
        row for row in candidate_proxies
        if row.get("candidateType") == "outcome_or_downstream_result"
    ]

    candidates: list[dict[str, Any]] = []
    for idx, proxy in enumerate(replayable_proxies):
        candidates.append(
            {
                "id": f"reset_candidate_{idx}",
                "stage": proxy.get("stage"),
                "sourceEvidence": abs_path(STATE_MACHINE),
                "appearsInSuccess": True,
                "missingInFailure": True,
                "entersRequestCookieOrRisk": False,
                "constructibleByPureProtocol": False,
                "ipSessionDecoupled": None,
                "negativeControlCovered": False,
                "stageProgressMetricDefined": False,
                "readyForFreshExperiment": False,
                "reason": proxy.get("reason"),
            }
        )

    checks = {
        "stateMachineExists": STATE_MACHINE.exists(),
        "finalResponseClassAuditExists": FINAL_CLASS.exists(),
        "cookieMutationAuditExists": COOKIE_MUTATION.exists(),
        "stateMachineClientVisibleProxyCount": ((state.get("checks") or {}).get("clientVisibleProxyCount")),
        "candidateClientVisibleProxyCount": len(replayable_proxies),
        "outcomeOnlyCandidateCount": len(outcome_only),
        "singleTransitionCandidateCount": len(candidates),
        "allFinalResponsesSameClass": ((final_class.get("checks") or {}).get("allFinalResponsesSameClass")),
        "allFinalResponsesAreSeq5Minus1": ((final_class.get("checks") or {}).get("allFinalResponsesAreSeq5Minus1")),
        "anySeq5Success0": ((final_class.get("checks") or {}).get("anySeq5Success0")),
        "allOfflineJarHasPx3Pxde": ((cookie.get("checks") or {}).get("allOfflineJarHasPx3Pxde")),
        "riskVerifyCandidateComplete": ((cookie.get("checks") or {}).get("riskVerifyCandidateComplete")),
    }
    checks["readyForFreshExperiment"] = (
        checks["singleTransitionCandidateCount"] == 1
        and any(row.get("readyForFreshExperiment") is True for row in candidates)
    )
    checks["goalComplete"] = False

    blockers = []
    if checks["candidateClientVisibleProxyCount"] == 0:
        blockers.append(
            {
                "id": "no_client_visible_proxy",
                "evidence": abs_path(STATE_MACHINE),
                "reason": "Reset state machine found no pre-accept replayable client-visible proxy; success-only stages are outcome/downstream states.",
            }
        )
    if checks["allFinalResponsesAreSeq5Minus1"] is True and checks["anySeq5Success0"] is False:
        blockers.append(
            {
                "id": "final_class_terminal_failure",
                "evidence": abs_path(FINAL_CLASS),
                "reason": "All valid pure-protocol reset final seq5 responses are oIIoIooo|-1, not oIIoIooo|0.",
            }
        )
    if checks["riskVerifyCandidateComplete"] is False:
        blockers.append(
            {
                "id": "no_risk_verify_success_cookie_candidate",
                "evidence": abs_path(COOKIE_MUTATION),
                "reason": "Offline cookie mutation is proven for _px3/_pxde, but the failure jar is not a complete risk/verify success-cookie candidate.",
            }
        )

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": abs_path(PLAN),
        "purpose": "Phase 4 reset single-transition reduction from reset state-machine, final response class, and cookie mutation evidence.",
        "inputs": [
            abs_path(STATE_MACHINE),
            abs_path(FINAL_CLASS),
            abs_path(COOKIE_MUTATION),
        ],
        "candidateClientVisibleProxies": candidate_proxies,
        "singleTransitionCandidates": candidates,
        "blockers": blockers,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": checks["readyForFreshExperiment"],
            "recommendedExperiment": None,
            "nextArtifact": None if not checks["readyForFreshExperiment"] else str((RESET_DIR / "reset_minimal_transition_experiment_audit.json").resolve()),
            "nextScript": None if not checks["readyForFreshExperiment"] else str((ROOT / "tools/run_reset_minimal_transition_experiment.py").resolve()),
            "reason": (
                "No single replayable transition candidate is available. Do not run Phase 5 fresh-session experiments until reset sampling exposes exactly one client-visible, constructible transition."
                if not checks["readyForFreshExperiment"]
                else "Exactly one replayable transition candidate is ready for a Phase 5 fresh-session experiment."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
