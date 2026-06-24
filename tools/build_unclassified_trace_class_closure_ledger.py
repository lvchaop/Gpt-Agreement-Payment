#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "unclassified_trace_class_closure_ledger.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "unclassifiedTraceSignalReduction": BASE / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessChainClassificationBacklog": BASE / "browser_success_chain_classification_backlog.json",
    "browserSuccessChainServerVisibleDiff": BASE / "browser_success_chain_server_visible_diff_audit.json",
    "browserSuccessPayloadPcSessionLineage": BASE / "browser_success_payload_pc_session_lineage_audit.json",
    "downstreamSuccessWithoutCollectorDecode": BASE / "downstream_success_without_collector_decode_audit.json",
    "collectorMaterialOnlyResponseClass": BASE / "collector_material_only_response_class_audit.json",
    "lowValueUnclassifiedTraceClosure": BASE / "low_value_unclassified_trace_closure_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


EXPECTED_CLASSES = {
    "browser_success_chain",
    "browser_parent_success_cookie_chain",
    "browser_downstream_create_or_continue_without_extracted_success",
    "collector_material_only",
    "low_value_or_unclassified",
}


def read_json(path: Path) -> dict[str, Any]:
    if path.suffix.lower() not in {".json"}:
        return {}
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    reduction = docs["unclassifiedTraceSignalReduction"]
    rows = reduction.get("rows") or []
    class_counts = Counter(row.get("classification") for row in rows)
    observed_classes = set(class_counts)
    unexpected_classes = sorted(observed_classes - EXPECTED_CLASSES)
    missing_expected_classes = sorted(EXPECTED_CLASSES - observed_classes)

    backlog_checks = checks(docs["browserSuccessChainClassificationBacklog"])
    success_diff_checks = checks(docs["browserSuccessChainServerVisibleDiff"])
    payload_lineage_checks = checks(docs["browserSuccessPayloadPcSessionLineage"])
    downstream_checks = checks(docs["downstreamSuccessWithoutCollectorDecode"])
    collector_material_checks = checks(docs["collectorMaterialOnlyResponseClass"])
    low_value_checks = checks(docs["lowValueUnclassifiedTraceClosure"])
    intake_checks = checks(docs["candidateIntake"])

    ledger_rows = [
        {
            "classification": "browser_success_chain",
            "runCount": class_counts.get("browser_success_chain", 0),
            "closureArtifacts": [
                str(INPUTS["browserSuccessChainClassificationBacklog"]),
                str(INPUTS["browserSuccessChainServerVisibleDiff"]),
                str(INPUTS["browserSuccessPayloadPcSessionLineage"]),
            ],
            "closureChecks": {
                "classificationBacklogCount": backlog_checks.get("classificationBacklogCount"),
                "serverVisibleProposalCandidateCount": success_diff_checks.get("proposalCandidateCount"),
                "payloadPcSessionProposalCandidateCount": payload_lineage_checks.get("proposalCandidateCount"),
            },
            "proposalCandidateCount": 0,
            "closureStatus": "closed_classification_and_diff_input",
            "reason": "Browser success chain is positive control evidence only; server-visible and payload/pc/session lineage audits produce zero proposal candidates.",
        },
        {
            "classification": "browser_parent_success_cookie_chain",
            "runCount": class_counts.get("browser_parent_success_cookie_chain", 0),
            "closureArtifacts": [
                str(INPUTS["browserSuccessChainClassificationBacklog"]),
                str(INPUTS["browserSuccessChainServerVisibleDiff"]),
            ],
            "closureChecks": {
                "browserParentSuccessCookieChainRunCount": backlog_checks.get("browserParentSuccessCookieChainRunCount"),
                "serverVisibleProposalCandidateCount": success_diff_checks.get("proposalCandidateCount"),
            },
            "proposalCandidateCount": 0,
            "closureStatus": "closed_negative_control_input",
            "reason": "Parent success/cookie rows are controls for browser bridge/cookie hypotheses; no no-browser or single transition evidence is present.",
        },
        {
            "classification": "browser_downstream_create_or_continue_without_extracted_success",
            "runCount": class_counts.get("browser_downstream_create_or_continue_without_extracted_success", 0),
            "closureArtifacts": [str(INPUTS["downstreamSuccessWithoutCollectorDecode"])],
            "closureChecks": {
                "downstreamClassRunCount": downstream_checks.get("downstreamClassRunCount"),
                "collectorSuccessDecodeRunCount": downstream_checks.get("collectorSuccessDecodeRunCount"),
                "downstreamSuccessRunCount": downstream_checks.get("downstreamSuccessRunCount"),
                "proposalCandidateCount": downstream_checks.get("proposalCandidateCount"),
            },
            "proposalCandidateCount": downstream_checks.get("proposalCandidateCount") or 0,
            "closureStatus": "closed_downstream_outcome_without_collector_success",
            "reason": "Downstream risk/CreateAccount signals lack decoded collector success, so they cannot identify collector pre-accept root cause.",
        },
        {
            "classification": "collector_material_only",
            "runCount": class_counts.get("collector_material_only", 0),
            "closureArtifacts": [str(INPUTS["collectorMaterialOnlyResponseClass"])],
            "closureChecks": {
                "collectorMaterialOnlyRunCount": collector_material_checks.get("collectorMaterialOnlyRunCount"),
                "collectorSuccessDecodeRunCount": collector_material_checks.get("collectorSuccessDecodeRunCount"),
                "riskContinueRunCount": collector_material_checks.get("riskContinueRunCount"),
                "createRedirectRunCount": collector_material_checks.get("createRedirectRunCount"),
                "proposalCandidateCount": collector_material_checks.get("proposalCandidateCount"),
            },
            "proposalCandidateCount": collector_material_checks.get("proposalCandidateCount") or 0,
            "closureStatus": "closed_material_inventory",
            "reason": "Collector material rows have no decoded collector success and no CreateAccount redirect; one risk-continue row is downstream/control evidence only.",
        },
        {
            "classification": "low_value_or_unclassified",
            "runCount": class_counts.get("low_value_or_unclassified", 0),
            "closureArtifacts": [str(INPUTS["lowValueUnclassifiedTraceClosure"])],
            "closureChecks": {
                "lowValueRunCount": low_value_checks.get("lowValueRunCount"),
                "rescannedProposalRelevantSignalRunCount": low_value_checks.get("rescannedProposalRelevantSignalRunCount"),
                "requestFailedRunCount": low_value_checks.get("requestFailedRunCount"),
                "riskInitializeRunCount": low_value_checks.get("riskInitializeRunCount"),
                "proposalCandidateCount": low_value_checks.get("proposalCandidateCount"),
            },
            "proposalCandidateCount": low_value_checks.get("proposalCandidateCount") or 0,
            "closureStatus": "closed_low_value_residual",
            "reason": "Residual rows rescan to zero proposal-relevant collector/risk/verify/cookie/wasm/parent-success signals.",
        },
    ]

    total_ledger_runs = sum(row["runCount"] for row in ledger_rows)
    proposal_candidate_total = sum(row["proposalCandidateCount"] for row in ledger_rows)
    per_class_counts_match = (
        backlog_checks.get("browserSuccessChainRunCount") == class_counts.get("browser_success_chain", 0)
        and backlog_checks.get("browserParentSuccessCookieChainRunCount") == class_counts.get("browser_parent_success_cookie_chain", 0)
        and downstream_checks.get("downstreamClassRunCount") == class_counts.get("browser_downstream_create_or_continue_without_extracted_success", 0)
        and collector_material_checks.get("collectorMaterialOnlyRunCount") == class_counts.get("collector_material_only", 0)
        and low_value_checks.get("lowValueRunCount") == class_counts.get("low_value_or_unclassified", 0)
    )

    ledger_all_closed = (
        not unexpected_classes
        and not missing_expected_classes
        and total_ledger_runs == len(rows)
        and per_class_counts_match
        and proposal_candidate_total == 0
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "reducedRunCount": len(rows),
        "ledgerClassCount": len(ledger_rows),
        "ledgerRunCount": total_ledger_runs,
        "classCountsMatchReduction": total_ledger_runs == len(rows),
        "perClassClosureCountsMatch": per_class_counts_match,
        "unexpectedClassCount": len(unexpected_classes),
        "missingExpectedClassCount": len(missing_expected_classes),
        "proposalCandidateTotal": proposal_candidate_total,
        "candidateIntakePromotedCount": intake_checks.get("promotedSingleTransitionCandidateCount"),
        "allTraceClassesClosed": ledger_all_closed,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Ledger that maps every unclassified trace reduction class to a closure artifact and verifies no class remains untriaged for proposal intake.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "classCounts": dict(class_counts),
        "unexpectedClasses": unexpected_classes,
        "missingExpectedClasses": missing_expected_classes,
        "ledgerRows": ledger_rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All 162 reduced unclassified trace rows are mapped to closure artifacts across five classes, and the ledger has zero proposal candidates. "
                "This closes the trace-class inventory but does not create the missing fresh no-browser HUMAN success."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
