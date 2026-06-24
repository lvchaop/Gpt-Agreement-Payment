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
OUT = HYP / "stale_positive_signal_authority_audit.json"

AUTHORITY_INPUTS = {
    "currentRouteAuthority": HYP / "current_route_authority_audit.json",
    "currentEvidenceEntranceTerminalLedger": HYP / "current_evidence_entrance_terminal_ledger.json",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
    "evidenceGatedPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "minimalTransitionExperiment": HYP / "minimal_promoted_transition_experiment.json",
    "finalReplayAudit": GOAL / "final_pure_protocol_replay_audit.json",
}

POSITIVE_KEYS = {
    "readyForFreshExperiment",
    "goalComplete",
    "networkAttemptExecuted",
    "stageAdvanced",
    "freshNoBrowserCollectorSuccess",
    "freshDecodedOIIoIooo0",
    "freshDecodedPxJarReplayed",
    "freshRiskVerifyContinue",
    "freshCreateAccountRedirectUrl",
    "promotedSingleTransitionCandidateCount",
    "proposalCandidateCount",
    "proposalReadyRowCount",
    "candidateIntakePromotedCount",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def is_positive(value: Any) -> bool:
    return value is True or (isinstance(value, int) and not isinstance(value, bool) and value > 0)


def collect_positive_rows(path: Path, obj: Any, pointer: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_pointer = f"{pointer}/{key}"
            if key in POSITIVE_KEYS and is_positive(value):
                rows.append({
                    "path": str(path),
                    "relPath": str(path.relative_to(ROOT)),
                    "jsonPointer": child_pointer,
                    "key": key,
                    "value": value,
                })
            rows.extend(collect_positive_rows(path, value, child_pointer))
    elif isinstance(obj, list):
        for idx, value in enumerate(obj[:5000]):
            rows.extend(collect_positive_rows(path, value, f"{pointer}/{idx}"))
    return rows


def classify(row: dict[str, Any], authority: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rel = row["relPath"]
    ptr = row["jsonPointer"]
    key = row["key"]
    category = "unclassified_positive_signal"
    active = False
    reason = "Positive-looking signal is not classified by authority rules."

    c_route = checks(authority["currentRouteAuthority"])
    c_entrance = checks(authority["currentEvidenceEntranceTerminalLedger"])
    c_candidate = checks(authority["candidateIntake"])
    c_completion = checks(authority["completionRequirements"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])
    c_poc = checks(authority["evidenceGatedPoc"])
    c_minimal = checks(authority["minimalTransitionExperiment"])
    c_final = checks(authority["finalReplayAudit"])

    if rel == "output/protocol_reverse/hypothesis_reframe/coherent_encoder_variant_experiment_manifest.json":
        category = "superseded_coherent_encoder_ready_signal"
        reason = (
            "Old coherent encoder ready signal was superseded by current_route_authority: "
            f"liveProbeClosedNoSuccess={c_route.get('liveProbeClosedNoSuccess')}, "
            f"currentPromotedSingleTransitionCandidateCount={c_route.get('currentPromotedSingleTransitionCandidateCount')}."
        )
    elif rel == "output/protocol_reverse/hypothesis_reframe/current_route_authority_audit.json":
        category = "recorded_superseded_ready_signal"
        reason = "current_route_authority stores old ready signals only inside supersededReadyArtifacts; top-level readyForFreshExperiment is false."
    elif rel == "output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json":
        category = "recorded_historical_ready_next_pointer"
        reason = (
            "current evidence entrance ledger records a historical ready next pointer, but "
            f"activeActionableNextPointerCount={c_entrance.get('activeActionableNextPointerCount')} and current promoted count is 0."
        )
    elif rel == "output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json" and "requiresBeforeExecution" in ptr:
        category = "requirement_expression_not_current_state"
        reason = (
            "The positive value is an attempted precondition description, not current execution; "
            f"networkAttemptExecuted={c_poc.get('networkAttemptExecuted')}, blockedByGate={c_poc.get('blockedByGate')}."
        )
    elif key == "readyForFreshExperiment" and c_reset.get("readyForFreshExperiment") is True:
        category = "active_ready_signal"
        active = True
        reason = "Top-level reset authority currently permits fresh experiment."
    elif key == "goalComplete" and c_verifier.get("goalComplete") is True:
        category = "active_goal_complete_signal"
        active = True
        reason = "Strict goal completion verifier is true."
    elif key == "networkAttemptExecuted" and (
        c_poc.get("networkAttemptExecuted") is True
        or c_minimal.get("networkAttemptExecuted") is True
        or c_final.get("networkAttemptExecuted") is True
    ):
        category = "active_network_attempt_signal"
        active = True
        reason = "Current active PoC/minimal/final replay authority records a network attempt."
    elif key in {"promotedSingleTransitionCandidateCount", "proposalCandidateCount", "proposalReadyRowCount", "candidateIntakePromotedCount"} and (
        c_candidate.get("promotedSingleTransitionCandidateCount") or 0
    ) > 0:
        category = "active_promoted_candidate_signal"
        active = True
        reason = "Current candidate intake contains promoted candidates."
    else:
        category = "non_authoritative_positive_signal"
        reason = (
            "Current terminal authorities keep the route closed: "
            f"candidateIntakePromotedCount={c_candidate.get('promotedSingleTransitionCandidateCount')}, "
            f"completionNoCurrentExperimentRoute={c_completion.get('noCurrentExperimentRoute')}, "
            f"resetNoCurrentRouteToPhase5={c_reset.get('noCurrentRouteToPhase5')}, "
            f"completionVerified={c_verifier.get('completionVerified')}."
        )

    return {**row, "category": category, "activeActionable": active, "reason": reason}


def main() -> int:
    authority = {name: read_json(path) for name, path in AUTHORITY_INPUTS.items()}
    raw_rows: list[dict[str, Any]] = []
    for path in sorted(PROTO.rglob("*.json")):
        try:
            data = read_json(path)
        except json.JSONDecodeError:
            continue
        raw_rows.extend(collect_positive_rows(path, data))

    rows = [classify(row, authority) for row in raw_rows]
    active_rows = [row for row in rows if row["activeActionable"]]
    category_counts: dict[str, int] = {}
    for row in rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1

    c_route = checks(authority["currentRouteAuthority"])
    c_entrance = checks(authority["currentEvidenceEntranceTerminalLedger"])
    c_candidate = checks(authority["candidateIntake"])
    c_completion = checks(authority["completionRequirements"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scannedJsonFileCount": sum(1 for _ in PROTO.rglob("*.json")),
        "positiveSignalCount": len(rows),
        "activeActionablePositiveSignalCount": len(active_rows),
        "supersededOrNonAuthoritativePositiveSignalCount": len(rows) - len(active_rows),
        "staleReadyArtifactCount": c_route.get("staleReadyArtifactCount"),
        "currentEvidenceActiveActionableNextPointerCount": c_entrance.get("activeActionableNextPointerCount"),
        "candidateIntakePromotedCount": c_candidate.get("promotedSingleTransitionCandidateCount"),
        "completionNoCurrentExperimentRoute": c_completion.get("noCurrentExperimentRoute") is True,
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit positive-looking ready/goal/proposal/network signals and classify them against current terminal authority so stale artifacts cannot reopen fresh experiments.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "checks": checks_out,
        "categoryCounts": category_counts,
        "positiveSignalRows": rows,
        "activeActionableRows": active_rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All positive-looking ready/proposal/network signals are stale, superseded, or requirement expressions. "
                "Current terminal authority still has zero promoted candidates, no current experiment route, and incomplete goal verification."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "categoryCounts": category_counts, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
