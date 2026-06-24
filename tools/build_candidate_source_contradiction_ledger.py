#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "candidate_source_contradiction_ledger.json"

INPUTS = {
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
    "remainingBoundaryProposalGate": BASE / "remaining_boundary_proposal_gate_audit.json",
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
    "collectorServerExpectedStateBoundary": BASE / "collector_server_expected_state_boundary_audit.json",
    "minimalTransitionExperiment": BASE / "minimal_promoted_transition_experiment.json",
}

PROMOTION_PREDICATES = [
    "preAccept",
    "clientVisible",
    "pureProtocolConstructible",
    "valueChain",
    "negativeControlNotContradicted",
    "singleTransition",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def missing_intake_predicates(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if row.get("preAccept") is not True:
        missing.append("preAccept")
    if row.get("clientVisible") is not True:
        missing.append("clientVisible")
    if row.get("pureProtocolConstructible") is not True:
        missing.append("pureProtocolConstructible")
    if not row.get("valueChain"):
        missing.append("valueChain")
    if row.get("contradicted") is True:
        missing.append("negativeControlNotContradicted")
    if row.get("promotedCount") != 1:
        missing.append("singleTransition")
    return missing


def missing_gate_predicates(row: dict[str, Any]) -> list[str]:
    fields = row.get("proposalFields") or {}
    missing: list[str] = []
    if fields.get("preAccept") is not True:
        missing.append("preAccept")
    if fields.get("clientVisible") is not True:
        missing.append("clientVisible")
    if fields.get("pureProtocolConstructible") is not True:
        missing.append("pureProtocolConstructible")
    if fields.get("valueChainAllowed") is not True:
        missing.append("valueChain")
    if fields.get("contradicted") is True:
        missing.append("negativeControlNotContradicted")
    if row.get("proposalReady") is not True:
        missing.append("singleTransition")
    return missing


def missing_matrix_predicates(row: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if row.get("status") in {"downstream_proven_not_root_cause"}:
        missing.append("preAccept")
    if row.get("serverObservable") is not True:
        missing.append("clientVisible")
    if row.get("status") in {"non_request_boundary", "coupled_boundary"}:
        missing.append("pureProtocolConstructible")
    if row.get("status") == "eliminated" or row.get("negativeControlCovered") is True:
        missing.append("negativeControlNotContradicted")
    if row.get("singleVariable") is not True:
        missing.append("singleTransition")
    return missing


def bump(counter: dict[str, int], keys: list[str]) -> None:
    for key in keys:
        counter[key] = counter.get(key, 0) + 1


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    intake = docs["candidateIntake"]
    gate = docs["remainingBoundaryProposalGate"]
    matrix = docs["singleTransitionCandidateMatrix"]
    collector = docs["collectorServerExpectedStateBoundary"]
    minimal = docs["minimalTransitionExperiment"]

    predicate_fail_counts = {key: 0 for key in PROMOTION_PREDICATES}

    intake_rows = []
    for row in intake.get("candidateRows") or []:
        missing = missing_intake_predicates(row)
        bump(predicate_fail_counts, missing)
        intake_rows.append(
            {
                "id": row.get("id"),
                "source": "candidateIntake",
                "evidence": row.get("evidence"),
                "reportedCount": row.get("reportedCount"),
                "promotedCount": row.get("promotedCount"),
                "candidateAccepted": row.get("candidateAccepted") is True,
                "contradicted": row.get("contradicted") is True,
                "missingPredicates": missing,
                "whyNotAccepted": row.get("whyNotAccepted"),
            }
        )

    gate_rows = []
    for row in gate.get("rows") or []:
        missing = missing_gate_predicates(row)
        bump(predicate_fail_counts, missing)
        gate_rows.append(
            {
                "id": row.get("id"),
                "source": "remainingBoundaryProposalGate",
                "proposalReady": row.get("proposalReady") is True,
                "proposalFields": row.get("proposalFields"),
                "missingPredicates": missing,
                "blockers": row.get("blockers") or [],
                "evidence": row.get("evidence") or [],
            }
        )

    matrix_rows = []
    for row in matrix.get("candidates") or matrix.get("candidateRows") or []:
        missing = missing_matrix_predicates(row)
        bump(predicate_fail_counts, missing)
        matrix_rows.append(
            {
                "id": row.get("id"),
                "source": "singleTransitionCandidateMatrix",
                "status": row.get("status"),
                "readyForFreshExperiment": row.get("readyForFreshExperiment") is True,
                "singleVariable": row.get("singleVariable"),
                "serverObservable": row.get("serverObservable"),
                "negativeControlCovered": row.get("negativeControlCovered"),
                "missingPredicates": missing,
                "reason": row.get("reason"),
                "nextEvidenceNeeded": row.get("nextEvidenceNeeded"),
            }
        )

    c_intake = checks(intake)
    c_gate = checks(gate)
    c_matrix = checks(matrix)
    s_matrix = summary(matrix)
    c_collector = checks(collector)
    c_minimal = checks(minimal)

    promoted_total = (
        (c_intake.get("promotedSingleTransitionCandidateCount") or 0)
        + (c_gate.get("proposalReadyRowCount") or 0)
        + (s_matrix.get("singleTransitionCandidateCount") or 0)
    )
    all_sources_closed = (
        c_intake.get("promotedSingleTransitionCandidateCount") in {None, 0}
        and c_intake.get("candidateCount") in {None, 0}
        and c_intake.get("proposalAcceptedCount") in {None, 0}
        and c_gate.get("proposalReadyRowCount") in {None, 0}
        and c_matrix.get("noReadySingleTransitionCandidate") is True
        and c_collector.get("clientVisibleProxyFoundCount") in {None, 0}
        and c_collector.get("serverStateBoundaryNotClientVisible") is True
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "intakeRowCount": len(intake_rows),
        "intakeAcceptedCount": sum(1 for row in intake_rows if row["candidateAccepted"]),
        "intakeContradictedCount": sum(1 for row in intake_rows if row["contradicted"]),
        "gateRowCount": len(gate_rows),
        "gateReadyCount": sum(1 for row in gate_rows if row["proposalReady"]),
        "matrixRowCount": len(matrix_rows),
        "matrixReadyCount": sum(1 for row in matrix_rows if row["readyForFreshExperiment"]),
        "matrixNoReadySingleTransitionCandidate": c_matrix.get("noReadySingleTransitionCandidate") is True,
        "collectorClientVisibleProxyFoundCount": c_collector.get("clientVisibleProxyFoundCount"),
        "collectorServerStateBoundaryNotClientVisible": c_collector.get("serverStateBoundaryNotClientVisible") is True,
        "minimalExperimentBlockedByGate": c_minimal.get("blockedByGate") is True,
        "minimalExperimentNetworkAttemptExecuted": c_minimal.get("networkAttemptExecuted") is True,
        "promotedCandidateTotal": promoted_total,
        "predicateFailCounts": predicate_fail_counts,
        "allCandidateSourcesClosed": all_sources_closed,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Explain, source by source, why the current candidate intake cannot promote a fresh network experiment.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "promotionPredicates": PROMOTION_PREDICATES,
        "intakeRows": intake_rows,
        "remainingBoundaryRows": gate_rows,
        "singleTransitionRows": matrix_rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All current candidate sources fail at least one promotion predicate, and the remaining collector expected-state "
                "boundary is not client-visible in current evidence."
            ),
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
