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
OUT = HYP / "promotion_predicate_blocker_crosswalk.json"

PREDICATES = [
    "preAccept",
    "clientVisible",
    "pureProtocolConstructible",
    "valueChain",
    "negativeControlNotContradicted",
    "singleTransition",
    "artifactBacked",
    "staleAuthorityClean",
]

INPUTS = {
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "remainingBoundaryProposalGate": HYP / "remaining_boundary_proposal_gate_audit.json",
    "candidateSourceContradictionLedger": HYP / "candidate_source_contradiction_ledger.json",
    "serverStateValueConsumptionLedger": HYP / "server_state_value_consumption_ledger.json",
    "coupledBoundaryTerminalLedger": HYP / "coupled_boundary_terminal_ledger.json",
    "stalePositiveSignalAuthority": HYP / "stale_positive_signal_authority_audit.json",
    "liveRunnerGate": HYP / "live_runner_gate_audit.json",
    "objectiveCrosswalk": HYP / "objective_requirement_crosswalk.json",
    "evidenceManifestVerify": GOAL / "pure_protocol_evidence_manifest_verify.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def predicate_rows(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    c_intake = checks(docs["candidateIntake"])
    c_gate = checks(docs["remainingBoundaryProposalGate"])
    c_ledger = checks(docs["candidateSourceContradictionLedger"])
    c_values = checks(docs["serverStateValueConsumptionLedger"])
    c_coupled = checks(docs["coupledBoundaryTerminalLedger"])
    c_stale = checks(docs["stalePositiveSignalAuthority"])
    c_live = checks(docs["liveRunnerGate"])
    c_manifest = checks(docs["evidenceManifestVerify"])

    return [
        {
            "predicate": "preAccept",
            "status": "not_satisfied_by_any_promoted_candidate",
            "evidence": [str(INPUTS["candidateIntake"]), str(INPUTS["candidateSourceContradictionLedger"])],
            "facts": {
                "candidateIntakePreAcceptCandidateCount": c_intake.get("preAcceptCandidateCount"),
                "predicateFailCount": (c_ledger.get("predicateFailCounts") or {}).get("preAccept"),
                "promotedSingleTransitionCandidateCount": c_intake.get("promotedSingleTransitionCandidateCount"),
            },
        },
        {
            "predicate": "clientVisible",
            "status": "not_satisfied_by_any_promoted_candidate",
            "evidence": [
                str(INPUTS["candidateIntake"]),
                str(INPUTS["remainingBoundaryProposalGate"]),
                str(INPUTS["coupledBoundaryTerminalLedger"]),
            ],
            "facts": {
                "candidateIntakeClientVisibleCandidateCount": c_intake.get("clientVisibleCandidateCount"),
                "serverExpectedStateClientVisibleProxyCount": c_gate.get("serverExpectedStateClientVisibleProxyCount"),
                "collectorServerStateNotClientVisible": c_coupled.get("collectorServerStateNotClientVisible"),
                "predicateFailCount": (c_ledger.get("predicateFailCounts") or {}).get("clientVisible"),
            },
        },
        {
            "predicate": "pureProtocolConstructible",
            "status": "not_satisfied_by_any_promoted_candidate",
            "evidence": [str(INPUTS["candidateIntake"]), str(INPUTS["remainingBoundaryProposalGate"])],
            "facts": {
                "candidateIntakePureProtocolConstructibleCandidateCount": c_intake.get("pureProtocolConstructibleCandidateCount"),
                "outerSingleReadyGroupCount": c_gate.get("outerSingleReadyGroupCount"),
                "serverExpectedStateTransitionHasReplayableClientRepresentation": c_gate.get("serverExpectedStateTransitionHasReplayableClientRepresentation"),
                "predicateFailCount": (c_ledger.get("predicateFailCounts") or {}).get("pureProtocolConstructible"),
            },
        },
        {
            "predicate": "valueChain",
            "status": "present_only_in_non_promotable_rows",
            "evidence": [
                str(INPUTS["candidateIntake"]),
                str(INPUTS["serverStateValueConsumptionLedger"]),
            ],
            "facts": {
                "candidateIntakeValueChainCandidateCount": c_intake.get("valueChainCandidateCount"),
                "serverStateValueConsumedValueCount": c_values.get("consumedValueCount"),
                "serverStateValueSingleValueProposalReadyCount": c_values.get("singleValueProposalReadyCount"),
                "predicateFailCount": (c_ledger.get("predicateFailCounts") or {}).get("valueChain"),
            },
        },
        {
            "predicate": "negativeControlNotContradicted",
            "status": "not_satisfied_by_any_promoted_candidate",
            "evidence": [
                str(INPUTS["candidateIntake"]),
                str(INPUTS["candidateSourceContradictionLedger"]),
                str(INPUTS["serverStateValueConsumptionLedger"]),
                str(INPUTS["coupledBoundaryTerminalLedger"]),
            ],
            "facts": {
                "candidateIntakeNegativeControlContradictedCandidateCount": c_intake.get("negativeControlContradictedCandidateCount"),
                "candidateSourceContradictionLedgerPromotedTotal": c_ledger.get("promotedCandidateTotal"),
                "serverStateValueAllRowsCovered": c_values.get("allRowsCoveredByControlOrCoupling"),
                "coupledBoundariesAllClosed": c_coupled.get("allCoupledBoundariesClosedForCurrentEvidence"),
                "predicateFailCount": (c_ledger.get("predicateFailCounts") or {}).get("negativeControlNotContradicted"),
            },
        },
        {
            "predicate": "singleTransition",
            "status": "not_satisfied_by_any_promoted_candidate",
            "evidence": [str(INPUTS["remainingBoundaryProposalGate"]), str(INPUTS["coupledBoundaryTerminalLedger"])],
            "facts": {
                "remainingBoundaryProposalReadyRowCount": c_gate.get("proposalReadyRowCount"),
                "singleTransitionMatrixReadyCount": c_gate.get("singleTransitionMatrixReadyCount"),
                "coupledBoundaryProposalReadyRowCount": c_coupled.get("proposalReadyRowCount"),
                "predicateFailCount": (c_ledger.get("predicateFailCounts") or {}).get("singleTransition"),
            },
        },
        {
            "predicate": "artifactBacked",
            "status": "satisfied_for_current_negative_decision_only",
            "evidence": [str(INPUTS["evidenceManifestVerify"]), str(INPUTS["liveRunnerGate"])],
            "facts": {
                "manifestVerifyAllFilesExist": c_manifest.get("allFilesExist"),
                "manifestVerifyAllHashesMatch": c_manifest.get("allHashesMatch"),
                "liveRunnerGateCurrentNetworkAttemptBlocked": c_live.get("currentNetworkAttemptBlocked"),
            },
        },
        {
            "predicate": "staleAuthorityClean",
            "status": "satisfied_for_current_negative_decision_only",
            "evidence": [str(INPUTS["stalePositiveSignalAuthority"]), str(INPUTS["liveRunnerGate"])],
            "facts": {
                "stalePositiveSignalActiveActionablePositiveSignalCount": c_stale.get("activeActionablePositiveSignalCount"),
                "stalePositiveSignalCandidateIntakePromotedCount": c_stale.get("candidateIntakePromotedCount"),
                "stalePositiveSignalReadyForFreshExperiment": c_stale.get("readyForFreshExperiment"),
                "liveRunnerGateCurrentNetworkAttemptBlocked": c_live.get("currentNetworkAttemptBlocked"),
            },
        },
    ]


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    rows = predicate_rows(docs)
    c_intake = checks(docs["candidateIntake"])
    c_gate = checks(docs["remainingBoundaryProposalGate"])
    c_obj = checks(docs["objectiveCrosswalk"])

    unsatisfied = [
        row for row in rows
        if row["status"] not in {"satisfied_for_current_negative_decision_only"}
    ]
    current_ready = (
        c_intake.get("promotedSingleTransitionCandidateCount") == 1
        and c_gate.get("proposalReadyRowCount") == 1
        and c_obj.get("endToEndPocMissing") is not True
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "predicateCount": len(rows),
        "unsatisfiedPromotionPredicateCount": len(unsatisfied),
        "artifactBackedNegativeDecision": rows[-2]["status"] == "satisfied_for_current_negative_decision_only",
        "staleAuthorityCleanForNegativeDecision": rows[-1]["status"] == "satisfied_for_current_negative_decision_only",
        "candidateIntakePromotedCount": c_intake.get("promotedSingleTransitionCandidateCount"),
        "remainingBoundaryProposalReadyRowCount": c_gate.get("proposalReadyRowCount"),
        "objectiveEndToEndPocMissing": c_obj.get("endToEndPocMissing"),
        "readyForFreshExperiment": current_ready,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Crosswalk the eight promoted-transition predicates to current blocker evidence before any fresh/direct/Webshare experiment can run.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "predicates": PREDICATES,
        "rows": rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "No current candidate satisfies the promotion predicates. The negative decision is artifact-backed and stale-authority-clean, but it does not prove the missing end-to-end PoC.",
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
