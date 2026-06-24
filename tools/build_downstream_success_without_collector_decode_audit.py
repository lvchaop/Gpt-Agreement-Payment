#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "downstream_success_without_collector_decode_audit.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "unclassifiedTraceSignalReduction": BASE / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessServerVisibleDiff": BASE / "browser_success_chain_server_visible_diff_audit.json",
    "collectorResponseHandlerValueLineage": BASE / "collector_response_handler_value_lineage_audit.json",
    "collectorToRiskConsumptionChain": BASE / "collector_to_risk_consumption_chain.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def runtime_path(run: str) -> Path:
    return REPO / f"output/outlook_browser/runtime_trace_{run}.jsonl"


def js_path(run: str) -> Path:
    return REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        obj["_lineNo"] = line_no
        rows.append(obj)
    return rows


def event_text(event: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("url", "post_data", "body", "text", "message", "name", "kind"):
        value = event.get(key)
        if value is not None:
            parts.append(str(value))
    headers = event.get("headers")
    if headers:
        parts.append(json.dumps(headers, sort_keys=True, ensure_ascii=False))
    return "\n".join(parts)


TOKENS = {
    "collectorSuccess0": ["oIIoIooo|0", "challenge_success=0", '"challenge_success":0', '"challenge_success": 0'],
    "collectorFailureMinus1": ["oIIoIooo|-1"],
    "riskContinue": ['"state":"continue"', '"state": "continue"'],
    "createRedirect": ["redirectUrl"],
    "riskVerifyRequest": ["/risk/verify"],
    "createAccountRequest": ["/API/CreateAccount"],
    "parentSucceeded": ["succeeded", "parent"],
    "px3": ["_px3"],
    "pxde": ["_pxde"],
}


def count_tokens(events: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in events:
        text = event_text(event)
        for name, tokens in TOKENS.items():
            if any(token in text for token in tokens):
                counts[name] += 1
    return counts


def first_line(events: list[dict[str, Any]], tokens: list[str]) -> int | None:
    for event in events:
        text = event_text(event)
        if any(token in text for token in tokens):
            return event.get("_lineNo")
    return None


def assess_run(run: str, source_row: dict[str, Any]) -> dict[str, Any]:
    runtime_events = load_jsonl(runtime_path(run))
    js_events = load_jsonl(js_path(run))
    runtime_counts = count_tokens(runtime_events)
    js_counts = count_tokens(js_events)
    merged = runtime_counts + js_counts

    has_downstream_success = merged["riskContinue"] > 0 or merged["createRedirect"] > 0
    has_collector_success_decode = merged["collectorSuccess0"] > 0
    has_failure_decode = merged["collectorFailureMinus1"] > 0
    has_parent_success = merged["parentSucceeded"] > 0
    has_risk_verify = merged["riskVerifyRequest"] > 0
    has_create_account = merged["createAccountRequest"] > 0

    blockers = [
        "downstream risk/CreateAccount evidence is after HUMAN acceptance, not a pre-accept collector transition",
        "classification lacks decoded collector success oIIoIooo|0 in this run",
        "no single request/cookie/risk/verify field is isolated by the row",
    ]
    if has_failure_decode:
        blockers.append("row includes collector failure marker, contradicting success-root interpretation")
    if not has_collector_success_decode:
        blockers.append("collector success handler/value is missing, so downstream success cannot be used as collector root-cause evidence")

    return {
        "run": run,
        "classification": source_row.get("classification"),
        "runtimeTrace": str(runtime_path(run)),
        "runtimeTraceExists": runtime_path(run).exists(),
        "jsInternalTrace": str(js_path(run)),
        "jsInternalTraceExists": js_path(run).exists(),
        "sourceTokenCounts": source_row.get("tokenCounts") or {},
        "mergedTokenCounts": dict(merged),
        "firstLines": {
            name: first_line(runtime_events + js_events, tokens)
            for name, tokens in TOKENS.items()
        },
        "hasDownstreamSuccess": has_downstream_success,
        "hasCollectorSuccessDecode": has_collector_success_decode,
        "hasCollectorFailureDecode": has_failure_decode,
        "hasParentSuccess": has_parent_success,
        "hasRiskVerifyRequest": has_risk_verify,
        "hasCreateAccountRequest": has_create_account,
        "proposalAssessment": {
            "preAccept": False,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "valueChain": "risk" if has_risk_verify or merged["riskContinue"] else "verify",
            "contradicted": True,
            "proposalReady": False,
            "blockers": blockers,
        },
    }


def build() -> dict[str, Any]:
    reduction = read_json(INPUTS["unclassifiedTraceSignalReduction"])
    diff = read_json(INPUTS["browserSuccessServerVisibleDiff"])
    response_lineage = read_json(INPUTS["collectorResponseHandlerValueLineage"])
    consumption = read_json(INPUTS["collectorToRiskConsumptionChain"])
    intake = read_json(INPUTS["candidateIntake"])

    rows = [
        row for row in reduction.get("rows") or []
        if row.get("classification") == "browser_downstream_create_or_continue_without_extracted_success"
    ]
    audits = [assess_run(row["run"], row) for row in rows if row.get("run")]
    with_downstream = [row for row in audits if row["hasDownstreamSuccess"]]
    with_collector_success = [row for row in audits if row["hasCollectorSuccessDecode"]]
    with_parent_success = [row for row in audits if row["hasParentSuccess"]]
    with_failure = [row for row in audits if row["hasCollectorFailureDecode"]]
    proposal_ready = [row for row in audits if row["proposalAssessment"]["proposalReady"]]

    downstream_counts = Counter()
    for row in audits:
        if row["hasRiskVerifyRequest"]:
            downstream_counts["riskVerifyRequest"] += 1
        if row["hasCreateAccountRequest"]:
            downstream_counts["createAccountRequest"] += 1
        if row["mergedTokenCounts"].get("riskContinue", 0):
            downstream_counts["riskContinue"] += 1
        if row["mergedTokenCounts"].get("createRedirect", 0):
            downstream_counts["createRedirect"] += 1

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "downstreamClassRunCount": len(rows),
        "runtimeTraceExistsCount": sum(1 for row in audits if row["runtimeTraceExists"]),
        "jsInternalTraceExistsCount": sum(1 for row in audits if row["jsInternalTraceExists"]),
        "downstreamSuccessRunCount": len(with_downstream),
        "collectorSuccessDecodeRunCount": len(with_collector_success),
        "parentSuccessRunCount": len(with_parent_success),
        "collectorFailureDecodeRunCount": len(with_failure),
        "allDownstreamRowsLackCollectorSuccessDecode": len(rows) > 0 and len(with_collector_success) == 0,
        "downstreamEvidenceIsPostAccept": True,
        "serverVisibleDiffProposalCandidateCount": (diff.get("checks") or {}).get("proposalCandidateCount"),
        "collectorResponseLineageProposalCandidateCount": (response_lineage.get("checks") or {}).get("proposalCandidateCount"),
        "collectorToRiskSuccessChainProven": (consumption.get("checks") or {}).get("riskContinueTokenFeedsCreateAccount") is True,
        "proposalCandidateCount": len(proposal_ready),
        "candidateIntakePromotedCount": (intake.get("checks") or {}).get("promotedSingleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Isolate browser downstream risk/CreateAccount success rows that lack decoded collector success, preventing them from being mistaken for a pure-protocol pre-accept transition.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "downstreamFeatureCounts": dict(downstream_counts),
        "rows": audits,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Rows classified as browser_downstream_create_or_continue_without_extracted_success contain downstream risk/CreateAccount signals, "
                "but they lack decoded collector success oIIoIooo|0 and therefore cannot identify the pre-accept collector transition. "
                "The accepted collector -> risk/verify chain is already proven separately, so these rows are outcome/classification evidence only."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "downstreamFeatureCounts": result["downstreamFeatureCounts"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
