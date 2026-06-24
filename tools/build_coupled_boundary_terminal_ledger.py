#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
OUT = HYP / "coupled_boundary_terminal_ledger.json"

INPUTS = {
    "finalBoundaryDecisionMatrix": HYP / "final_boundary_decision_matrix.json",
    "outerSessionTupleFactorization": HYP / "outer_session_tuple_factorization.json",
    "encodedSessionBindingCandidate": HYP / "encoded_session_binding_candidate_audit.json",
    "encoderAxisEquivalence": HYP / "encoder_axis_equivalence.json",
    "remainingEncoderVariantControlCoverage": HYP / "remaining_encoder_variant_control_coverage.json",
    "remainingEncoderPcCoherence": HYP / "remaining_encoder_pc_coherence_audit.json",
    "encoderVariantTerminal": HYP / "encoder_variant_terminal_audit.json",
    "collectorServerExpectedStateBoundary": HYP / "collector_server_expected_state_boundary_audit.json",
    "serverStateValueConsumptionLedger": HYP / "server_state_value_consumption_ledger.json",
    "candidateSourceContradictionLedger": HYP / "candidate_source_contradiction_ledger.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    c_final = checks(docs["finalBoundaryDecisionMatrix"])
    c_outer = checks(docs["outerSessionTupleFactorization"])
    c_encoded = checks(docs["encodedSessionBindingCandidate"])
    c_axis = checks(docs["encoderAxisEquivalence"])
    c_coverage = checks(docs["remainingEncoderVariantControlCoverage"])
    c_pc = checks(docs["remainingEncoderPcCoherence"])
    c_terminal = checks(docs["encoderVariantTerminal"])
    c_collector = checks(docs["collectorServerExpectedStateBoundary"])
    c_value = checks(docs["serverStateValueConsumptionLedger"])
    c_candidate = checks(docs["candidateSourceContradictionLedger"])

    rows = [
        {
            "id": "C4_outer_session_tuple",
            "status": "closed_as_coupled_not_single_transition",
            "evidence": [
                str(INPUTS["outerSessionTupleFactorization"]),
                str(INPUTS["finalBoundaryDecisionMatrix"]),
            ],
            "facts": {
                "hasAllOuterTupleFields": c_outer.get("hasAllOuterTupleFields"),
                "sourceGroupCount": c_outer.get("sourceGroupCount"),
                "singleReadyGroupCount": c_outer.get("singleReadyGroupCount"),
                "noSingleFieldExperimentReady": c_outer.get("noSingleFieldExperimentReady"),
            },
            "promotionPredicatesMissing": ["singleTransition", "pureProtocolConstructible"],
            "proposalReady": False,
        },
        {
            "id": "C5_encoded_payload_pc_session_binding",
            "status": "closed_no_success_after_single_coherent_probe",
            "evidence": [
                str(INPUTS["encodedSessionBindingCandidate"]),
                str(INPUTS["encoderAxisEquivalence"]),
                str(INPUTS["remainingEncoderVariantControlCoverage"]),
                str(INPUTS["remainingEncoderPcCoherence"]),
                str(INPUTS["encoderVariantTerminal"]),
            ],
            "facts": {
                "singleAxisRowCount": c_encoded.get("singleAxisRowCount"),
                "singleAxisEliminatedCount": c_encoded.get("singleAxisEliminatedCount"),
                "remainingEncoderAxisCount": c_axis.get("remainingEncoderAxisCount"),
                "openVariantCountAfterCoverage": c_coverage.get("openVariantCount"),
                "singleCoherentVariantFound": c_pc.get("singleCoherentVariant"),
                "liveProbeExecuted": c_terminal.get("liveProbeExecuted"),
                "liveProbeAnyCollectorSuccess": c_terminal.get("liveProbeAnyCollectorSuccess"),
                "encoderVariantFamilyClosedNoSuccess": c_terminal.get("encoderVariantFamilyClosedNoSuccess"),
            },
            "promotionPredicatesMissing": ["negativeControlNotContradicted"],
            "proposalReady": False,
        },
        {
            "id": "C6_collector_server_expected_state",
            "status": "closed_for_current_local_evidence_as_non_client_visible",
            "evidence": [
                str(INPUTS["collectorServerExpectedStateBoundary"]),
                str(INPUTS["serverStateValueConsumptionLedger"]),
                str(INPUTS["candidateSourceContradictionLedger"]),
            ],
            "facts": {
                "clientVisibleProxyFoundCount": c_collector.get("clientVisibleProxyFoundCount"),
                "serverStateBoundaryNotClientVisible": c_collector.get("serverStateBoundaryNotClientVisible"),
                "valueComparisonCount": c_value.get("valueComparisonCount"),
                "allRowsCoveredByControlOrCoupling": c_value.get("allRowsCoveredByControlOrCoupling"),
                "singleValueProposalReadyCount": c_value.get("singleValueProposalReadyCount"),
                "candidateSourcePromotedTotal": c_candidate.get("promotedCandidateTotal"),
            },
            "promotionPredicatesMissing": ["clientVisible", "pureProtocolConstructible", "singleTransition"],
            "proposalReady": False,
        },
    ]

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "finalMatrixNoBoundaryAllowsFreshExperiment": c_final.get("noBoundaryAllowsFreshExperiment") is True,
        "coupledBoundaryRowCount": len(rows),
        "proposalReadyRowCount": sum(1 for row in rows if row["proposalReady"] is True),
        "outerTupleClosedNoSingle": c_outer.get("noSingleFieldExperimentReady") is True
        and c_outer.get("singleReadyGroupCount") in {None, 0},
        "encodedSessionSingleAxisEliminated": c_encoded.get("singleAxisEliminatedCount") == c_encoded.get("singleAxisRowCount"),
        "encoderVariantFamilyClosedNoSuccess": c_terminal.get("encoderVariantFamilyClosedNoSuccess") is True,
        "serverStateValueSingleReadyCount": c_value.get("singleValueProposalReadyCount"),
        "serverStateValueAllCovered": c_value.get("allRowsCoveredByControlOrCoupling") is True,
        "collectorServerStateNotClientVisible": c_collector.get("serverStateBoundaryNotClientVisible") is True,
        "candidateSourcePromotedTotal": c_candidate.get("promotedCandidateTotal"),
        "allCoupledBoundariesClosedForCurrentEvidence": all(row["proposalReady"] is False for row in rows)
        and c_outer.get("noSingleFieldExperimentReady") is True
        and c_encoded.get("singleAxisEliminatedCount") == c_encoded.get("singleAxisRowCount")
        and c_terminal.get("encoderVariantFamilyClosedNoSuccess") is True
        and c_value.get("singleValueProposalReadyCount") in {None, 0}
        and c_collector.get("serverStateBoundaryNotClientVisible") is True
        and c_candidate.get("promotedCandidateTotal") in {None, 0},
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Terminal ledger for the three remaining coupled boundaries C4/C5/C6 after candidate-source and server-state value consumption closure.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "rows": rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "C4 has no single outer/session field, C5 was reduced to one coherent encoder variant and the live probe produced no collector success, "
                "and C6 remains non-client-visible with all value mismatches covered by controls or coupling."
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
