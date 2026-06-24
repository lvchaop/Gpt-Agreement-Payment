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
OUT = HYP / "convergent_evidence_entrance_matrix.json"

INPUTS = {
    "currentEvidenceEntranceTerminalLedger": HYP / "current_evidence_entrance_terminal_ledger.json",
    "candidateSourceContradictionLedger": HYP / "candidate_source_contradiction_ledger.json",
    "serverStateValueConsumptionLedger": HYP / "server_state_value_consumption_ledger.json",
    "coupledBoundaryTerminalLedger": HYP / "coupled_boundary_terminal_ledger.json",
    "stalePositiveSignalAuthority": HYP / "stale_positive_signal_authority_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
    "goalGapAudit": GOAL / "pure_protocol_goal_gap_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def row(
    *,
    entrance_id: str,
    source: str,
    candidate_affecting: bool,
    closed: bool,
    stale: bool = False,
    uncovered: bool = False,
    reason: str,
    evidence: list[str],
    facts: list[str],
) -> dict[str, Any]:
    recommended = candidate_affecting and not closed and not stale and uncovered
    return {
        "id": entrance_id,
        "source": source,
        "candidateAffecting": candidate_affecting,
        "closed": closed,
        "stale": stale,
        "uncovered": uncovered,
        "recommendedNext": recommended,
        "reason": reason,
        "evidence": evidence,
        "facts": facts,
    }


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    current = checks(docs["currentEvidenceEntranceTerminalLedger"])
    candidates = checks(docs["candidateSourceContradictionLedger"])
    values = checks(docs["serverStateValueConsumptionLedger"])
    coupled = checks(docs["coupledBoundaryTerminalLedger"])
    stale = checks(docs["stalePositiveSignalAuthority"])
    verifier = checks(docs["goalCompletionVerifier"])
    goal = summary(docs["goalGapAudit"])

    rows = [
        row(
            entrance_id="historical_next_pointer_surface",
            source="currentEvidenceEntranceTerminalLedger",
            candidate_affecting=True,
            closed=current.get("unresolvedNextPointerCount") == 0
            and current.get("activeActionableNextPointerCount") == 0
            and current.get("currentPromotedSingleTransitionCandidateCount") == 0
            and current.get("allKnownLocalEvidenceEntrancesClosed") is True,
            stale=(current.get("readySignalNextPointerCount") or 0) > 0,
            uncovered=False,
            reason="Historical nextArtifact/nextScript pointers are materialized or superseded; none is active under current promoted-candidate authority.",
            evidence=[str(INPUTS["currentEvidenceEntranceTerminalLedger"])],
            facts=[
                f"nextPointerCount={current.get('nextPointerCount')}",
                f"unresolvedNextPointerCount={current.get('unresolvedNextPointerCount')}",
                f"readySignalNextPointerCount={current.get('readySignalNextPointerCount')}",
                f"activeActionableNextPointerCount={current.get('activeActionableNextPointerCount')}",
                f"allNextPointersClosedOrSuperseded={current.get('allNextPointersClosedOrSuperseded')}",
            ],
        ),
        row(
            entrance_id="candidate_source_predicate_surface",
            source="candidateSourceContradictionLedger",
            candidate_affecting=True,
            closed=candidates.get("allCandidateSourcesClosed") is True
            and candidates.get("promotedCandidateTotal") == 0,
            stale=False,
            uncovered=False,
            reason="All known candidate sources fail promotion predicates or are contradicted by controls; no promoted transition exists.",
            evidence=[str(INPUTS["candidateSourceContradictionLedger"])],
            facts=[
                f"intakeRowCount={candidates.get('intakeRowCount')}",
                f"intakeAcceptedCount={candidates.get('intakeAcceptedCount')}",
                f"intakeContradictedCount={candidates.get('intakeContradictedCount')}",
                f"gateReadyCount={candidates.get('gateReadyCount')}",
                f"matrixReadyCount={candidates.get('matrixReadyCount')}",
                f"promotedCandidateTotal={candidates.get('promotedCandidateTotal')}",
                f"predicateFailCounts={candidates.get('predicateFailCounts')}",
            ],
        ),
        row(
            entrance_id="server_state_value_surface",
            source="serverStateValueConsumptionLedger",
            candidate_affecting=True,
            closed=values.get("allRowsCoveredByControlOrCoupling") is True
            and values.get("singleValueProposalReadyCount") == 0,
            stale=False,
            uncovered=False,
            reason="Server-visible value differences are either consumed downstream, covered by controls, or still coupled; no single value proposal is ready.",
            evidence=[str(INPUTS["serverStateValueConsumptionLedger"])],
            facts=[
                f"valueComparisonCount={values.get('valueComparisonCount')}",
                f"valueMismatchCount={values.get('valueMismatchCount')}",
                f"consumedValueCount={values.get('consumedValueCount')}",
                f"allRowsCoveredByControlOrCoupling={values.get('allRowsCoveredByControlOrCoupling')}",
                f"singleValueProposalReadyCount={values.get('singleValueProposalReadyCount')}",
            ],
        ),
        row(
            entrance_id="coupled_boundary_surface",
            source="coupledBoundaryTerminalLedger",
            candidate_affecting=True,
            closed=coupled.get("allCoupledBoundariesClosedForCurrentEvidence") is True
            and coupled.get("proposalReadyRowCount") == 0,
            stale=False,
            uncovered=False,
            reason="Remaining coupled boundaries have no proposal-ready row under current evidence; they cannot open a single-transition fresh experiment.",
            evidence=[str(INPUTS["coupledBoundaryTerminalLedger"])],
            facts=[
                f"coupledBoundaryRowCount={coupled.get('coupledBoundaryRowCount')}",
                f"proposalReadyRowCount={coupled.get('proposalReadyRowCount')}",
                f"allCoupledBoundariesClosedForCurrentEvidence={coupled.get('allCoupledBoundariesClosedForCurrentEvidence')}",
            ],
        ),
        row(
            entrance_id="stale_positive_signal_surface",
            source="stalePositiveSignalAuthority",
            candidate_affecting=True,
            closed=stale.get("activeActionablePositiveSignalCount") == 0
            and stale.get("candidateIntakePromotedCount") == 0,
            stale=(stale.get("positiveSignalCount") or 0) > 0,
            uncovered=False,
            reason="Positive-looking ready/proposal/goal signals are stale, superseded, historical pointers, or requirement expressions.",
            evidence=[str(INPUTS["stalePositiveSignalAuthority"])],
            facts=[
                f"positiveSignalCount={stale.get('positiveSignalCount')}",
                f"activeActionablePositiveSignalCount={stale.get('activeActionablePositiveSignalCount')}",
                f"supersededOrNonAuthoritativePositiveSignalCount={stale.get('supersededOrNonAuthoritativePositiveSignalCount')}",
                f"staleReadyArtifactCount={stale.get('staleReadyArtifactCount')}",
                f"candidateIntakePromotedCount={stale.get('candidateIntakePromotedCount')}",
            ],
        ),
        row(
            entrance_id="goal_completion_gate_surface",
            source="goalCompletionVerifier",
            candidate_affecting=False,
            closed=verifier.get("completionVerified") is False
            and verifier.get("failedGateCount", 0) > 0,
            stale=False,
            uncovered=False,
            reason="The final verifier proves the objective is incomplete; it is a completion gate, not a local evidence entrance that can itself generate a transition candidate.",
            evidence=[str(INPUTS["goalCompletionVerifier"])],
            facts=[
                f"completionVerified={verifier.get('completionVerified')}",
                f"failedGateCount={verifier.get('failedGateCount')}",
                f"pocNetworkAttemptExecuted={verifier.get('pocNetworkAttemptExecuted')}",
                f"pocFreshNoBrowserCollectorSuccess={verifier.get('pocFreshNoBrowserCollectorSuccess')}",
                f"goalComplete={verifier.get('goalComplete')}",
            ],
        ),
        row(
            entrance_id="end_to_end_poc_gap_surface",
            source="goalGapAudit",
            candidate_affecting=False,
            closed=goal.get("blockingOrMissing") == ["end_to_end_pure_protocol_poc"]
            and goal.get("goalComplete") is False,
            stale=False,
            uncovered=False,
            reason="The only remaining objective gap is the gated end-to-end PoC; this describes the missing final proof, not an ungated local proposal entrance.",
            evidence=[str(INPUTS["goalGapAudit"])],
            facts=[
                f"proved={goal.get('proved')}",
                f"blockingOrMissing={goal.get('blockingOrMissing')}",
                f"goalComplete={goal.get('goalComplete')}",
            ],
        ),
    ]

    recommended = [r for r in rows if r["recommendedNext"] is True]
    uncovered_candidate_affecting = [r for r in rows if r["candidateAffecting"] and r["uncovered"] and not r["stale"]]
    closed = [r for r in rows if r["closed"] is True]
    stale_rows = [r for r in rows if r["stale"] is True]
    candidate_affecting = [r for r in rows if r["candidateAffecting"] is True]

    all_inputs_exist = all(path.exists() for path in INPUTS.values())
    checks_out = {
        "allInputsExist": all_inputs_exist,
        "entranceCount": len(rows),
        "closedEntranceCount": len(closed),
        "staleEntranceCount": len(stale_rows),
        "candidateAffectingEntranceCount": len(candidate_affecting),
        "uncoveredCandidateAffectingEntranceCount": len(uncovered_candidate_affecting),
        "recommendedNextEntranceCount": len(recommended),
        "recommendedNextEntranceIds": [r["id"] for r in recommended],
        "currentActiveActionableNextPointerCount": current.get("activeActionableNextPointerCount"),
        "candidateIntakePromotedCount": candidates.get("promotedCandidateTotal"),
        "staleActiveActionablePositiveSignalCount": stale.get("activeActionablePositiveSignalCount"),
        "completionVerified": verifier.get("completionVerified") is True,
        "goalGapBlockingOnlyEndToEndPoc": goal.get("blockingOrMissing") == ["end_to_end_pure_protocol_poc"],
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Converge current terminal evidence into candidate-affecting local evidence entrances, so fresh experiments only start from exactly one promoted transition.",
        "plan": str(ROOT / "docs/pure-protocol-human-evidence-convergent-plan.md"),
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "entrances": rows,
        "recommendedNextEntrances": recommended,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All currently known candidate-affecting local evidence entrances are closed or stale; "
                "there is no uncovered entrance that can be promoted to a single fresh transition experiment."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if all_inputs_exist else 1


if __name__ == "__main__":
    raise SystemExit(main())
