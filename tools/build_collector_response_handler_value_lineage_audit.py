#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
OUT = BASE / "collector_response_handler_value_lineage_audit.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "classifierV2Summary": PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json",
    "collectorDecoderCoverage": PROTO / "collector_decode/collector_decoder_coverage_audit.json",
    "collectorHandlerSurface": RESET / "reset_collector_handler_surface_audit.json",
    "finalResponseClass": RESET / "reset_final_response_class_audit.json",
    "cookieMutation": RESET / "reset_cookie_mutation_audit.json",
    "collectorToRiskChain": BASE / "collector_to_risk_consumption_chain.json",
    "collectorServerExpectedState": BASE / "collector_server_expected_state_boundary_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def decode_path(run: str) -> Path:
    return PROTO / f"collector_decode/collector_decode_{run}.json"


def load_decode(run: str) -> dict[str, Any]:
    return read_json(decode_path(run))


def summarize_run(run: str, stage: str) -> dict[str, Any]:
    doc = load_decode(run)
    entries = doc.get("decodedEntries") or []
    handler_counter: Counter[str] = Counter()
    success_values: list[str] = []
    failure_values: list[str] = []
    px3_count = 0
    pxde_count = 0
    pow_count = 0
    for entry in entries:
        for handler in entry.get("handlers") or []:
            handler_counter[handler] += 1
        for part in entry.get("parts") or []:
            if part.startswith("oIIoIooo|0"):
                success_values.append(part)
            if part.startswith("oIIoIooo|-1"):
                failure_values.append(part)
        if entry.get("hasPx3"):
            px3_count += 1
        if entry.get("hasPxde"):
            pxde_count += 1
        if entry.get("hasPowResult"):
            pow_count += 1
    return {
        "run": run,
        "stage": stage,
        "decodePath": str(decode_path(run)),
        "decodeExists": decode_path(run).exists(),
        "entryCount": len(entries),
        "distinctHandlers": sorted(handler_counter),
        "handlerCounts": dict(handler_counter),
        "successHandlerCount": len(success_values),
        "failureHandlerCount": len(failure_values),
        "px3EntryCount": px3_count,
        "pxdeEntryCount": pxde_count,
        "powEntryCount": pow_count,
    }


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    classifier_rows = docs["classifierV2Summary"].get("runs") or []
    decoded_rows = [
        summarize_run(row["run"], row.get("stage"))
        for row in classifier_rows
        if decode_path(row["run"]).exists()
    ]
    success_rows = [row for row in decoded_rows if row["stage"] == "full_success_decoded"]
    failure_rows = [row for row in decoded_rows if row["stage"] == "tf_payload_failure_stage"]

    success_handler_sets = [set(row["distinctHandlers"]) for row in success_rows]
    failure_handler_sets = [set(row["distinctHandlers"]) for row in failure_rows]
    common_success_handlers = set.intersection(*success_handler_sets) if success_handler_sets else set()
    common_failure_handlers = set.intersection(*failure_handler_sets) if failure_handler_sets else set()
    success_only_common_handlers = sorted(common_success_handlers - common_failure_handlers)
    failure_only_common_handlers = sorted(common_failure_handlers - common_success_handlers)

    handler_surface_checks = docs["collectorHandlerSurface"].get("checks") or {}
    final_class_checks = docs["finalResponseClass"].get("checks") or {}
    cookie_checks = docs["cookieMutation"].get("checks") or {}
    risk_checks = docs["collectorToRiskChain"].get("checks") or {}
    server_state_checks = docs["collectorServerExpectedState"].get("checks") or {}
    intake_checks = docs["candidateIntake"].get("checks") or {}

    value_rows = [
        {
            "id": "oIIoIooo_success_value",
            "valueChain": "risk",
            "preAccept": False,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "contradicted": True,
            "proposalReady": False,
            "facts": {
                "successRowsWithHandler": sum(1 for row in success_rows if row["successHandlerCount"] > 0),
                "failureRowsWithMinusOne": sum(1 for row in failure_rows if row["failureHandlerCount"] > 0),
                "resetAllFinalResponsesAreSeq5Minus1": final_class_checks.get("allFinalResponsesAreSeq5Minus1"),
                "resetAnySeq5Success0": final_class_checks.get("anySeq5Success0"),
            },
            "blockers": [
                "oIIoIooo|0 is a collector outcome, not a pre-accept client-controlled transition",
                "pure protocol controls currently produce oIIoIooo|-1 with the same response class family",
            ],
        },
        {
            "id": "px_cookie_mutation_values",
            "valueChain": "cookie",
            "preAccept": True,
            "clientVisible": True,
            "pureProtocolConstructible": True,
            "contradicted": True,
            "proposalReady": False,
            "facts": {
                "successRowsWithPx3": sum(1 for row in success_rows if row["px3EntryCount"] > 0),
                "failureRowsWithPx3": sum(1 for row in failure_rows if row["px3EntryCount"] > 0),
                "resetAllSeq5HasPx3Pxde": cookie_checks.get("allSeq5HasPx3Pxde"),
                "resetAllOfflineJarHasPx3Pxde": cookie_checks.get("allOfflineJarHasPx3Pxde"),
                "resetRiskVerifyCandidateComplete": cookie_checks.get("riskVerifyCandidateComplete"),
            },
            "blockers": [
                "px3/pxde mutation appears in failure controls as well as success samples",
                "offline jar update works but failure jar is not sufficient for risk/verify success",
            ],
        },
        {
            "id": "handler_surface_key",
            "valueChain": "request",
            "preAccept": True,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "contradicted": True,
            "proposalReady": False,
            "facts": {
                "successOnlyCommonHandlers": success_only_common_handlers,
                "failureOnlyCommonHandlers": failure_only_common_handlers,
                "handlerCandidateCount": handler_surface_checks.get("handlerCandidateCount"),
                "distinctHandlerKeyCount": handler_surface_checks.get("distinctHandlerKeyCount"),
                "unclassifiedHandlerSurfaceCount": handler_surface_checks.get("unclassifiedHandlerSurfaceCount"),
                "promotedSingleTransitionCandidateCount": handler_surface_checks.get("promotedSingleTransitionCandidateCount"),
                "negativeControlsAllHold": handler_surface_checks.get("negativeControlsAllHold"),
            },
            "blockers": [
                "decoded success/failure runs share the same common handler surface except outcome value",
                "existing handler surface audit promotes zero handler-key candidates",
            ],
        },
    ]
    proposal_candidates = [row for row in value_rows if row["proposalReady"]]

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "decodedRunCount": len(decoded_rows),
        "decodedSuccessRunCount": len(success_rows),
        "decodedFailureRunCount": len(failure_rows),
        "successOnlyCommonHandlerCount": len(success_only_common_handlers),
        "failureOnlyCommonHandlerCount": len(failure_only_common_handlers),
        "successRowsWithSuccessHandlerCount": sum(1 for row in success_rows if row["successHandlerCount"] > 0),
        "failureRowsWithFailureHandlerCount": sum(1 for row in failure_rows if row["failureHandlerCount"] > 0),
        "successRowsWithPx3PxdeCount": sum(1 for row in success_rows if row["px3EntryCount"] > 0 and row["pxdeEntryCount"] > 0),
        "failureRowsWithPx3PxdeCount": sum(1 for row in failure_rows if row["px3EntryCount"] > 0 and row["pxdeEntryCount"] > 0),
        "handlerSurfacePromotedCount": handler_surface_checks.get("promotedSingleTransitionCandidateCount"),
        "handlerSurfaceNegativeControlsAllHold": handler_surface_checks.get("negativeControlsAllHold") is True,
        "finalResponsesAllMinusOne": final_class_checks.get("allFinalResponsesAreSeq5Minus1") is True,
        "cookieMutationFailureStillMutates": cookie_checks.get("allOfflineJarHasPx3Pxde") is True,
        "collectorToRiskSuccessChainProven": risk_checks.get("riskContinueTokenFeedsCreateAccount") is True,
        "collectorServerClientVisibleProxyFoundCount": server_state_checks.get("clientVisibleProxyFoundCount"),
        "valueLineageRowCount": len(value_rows),
        "proposalCandidateCount": len(proposal_candidates),
        "candidateIntakePromotedCount": intake_checks.get("promotedSingleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Compare collector decoded response handlers/values across success and failure controls to find response-side proposal candidates.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "decodedRows": decoded_rows,
        "valueLineageRows": value_rows,
        "proposalCandidates": proposal_candidates,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Collector response-side lineage isolates oIIoIooo|0 as an outcome and px cookie mutation as a shared success/failure surface. "
                "No handler key or decoded value becomes a pre-accept, uncontradicted, pure-protocol constructible transition."
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
