#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "browser_success_chain_classification_backlog.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "localTraceEvidenceFreshness": BASE / "local_trace_evidence_freshness_audit.json",
    "unclassifiedTraceSignalReduction": BASE / "unclassified_trace_signal_reduction_audit.json",
    "traceClassifierRawCoverageGap": BASE / "trace_classifier_raw_coverage_gap_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def index_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row.get("run"): row for row in rows if row.get("run")}


def build() -> dict[str, Any]:
    reduction = read_json(INPUTS["unclassifiedTraceSignalReduction"])
    freshness = read_json(INPUTS["localTraceEvidenceFreshness"])
    coverage_gap = read_json(INPUTS["traceClassifierRawCoverageGap"])

    reduction_rows = index_rows(reduction.get("rows") or [])
    freshness_rows = index_rows(freshness.get("unclassifiedRows") or [])
    classifier_runs = set(coverage_gap.get("classifierRuns") or [])
    raw_success_not_in_classifier = set(coverage_gap.get("rawBrowserSuccessRunsNotInClassifier") or [])

    browser_success_runs = reduction.get("browserSuccessChainRuns") or []
    parent_cookie_runs = reduction.get("browserParentSuccessCookieChainRuns") or []
    backlog_runs = sorted(set(browser_success_runs) | set(parent_cookie_runs))

    rows: list[dict[str, Any]] = []
    for run in backlog_runs:
        reduced = reduction_rows.get(run) or {}
        fresh = freshness_rows.get(run) or {}
        classification = reduced.get("classification")
        role = (
            "browser_success_positive_control"
            if classification == "browser_success_chain"
            else "browser_parent_cookie_control"
        )
        rows.append(
            {
                "run": run,
                "classification": classification,
                "backlogRole": role,
                "hasRuntimeTrace": reduced.get("hasRuntimeTrace"),
                "hasJsInternalTrace": reduced.get("hasJsInternalTrace"),
                "runtimeTracePath": (fresh.get("runtime") or {}).get("path"),
                "jsInternalTracePath": (fresh.get("js") or {}).get("path"),
                "tokenCounts": reduced.get("tokenCounts") or {},
                "alreadyInClassifier": run in classifier_runs,
                "rawBrowserSuccessRunNotInClassifier": run in raw_success_not_in_classifier,
                "noBrowserEvidence": False,
                "proposalReady": False,
                "proposalBlockers": [
                    "source is browser runtime/js trace, not fresh no-browser pure-protocol execution",
                    "row does not isolate one request/cookie/risk/verify transition",
                    "classification backlog is evidence inventory, not a promoted proposal",
                ],
            }
        )

    class_counts = Counter(row["classification"] for row in rows)
    role_counts = Counter(row["backlogRole"] for row in rows)
    not_in_classifier_count = sum(1 for row in rows if row["rawBrowserSuccessRunNotInClassifier"])
    no_browser_count = sum(1 for row in rows if row["noBrowserEvidence"])
    proposal_ready_count = sum(1 for row in rows if row["proposalReady"])

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "methodologyPlanExists": INPUTS["methodologyPlan"].exists(),
        "localTraceEvidenceFreshnessExists": INPUTS["localTraceEvidenceFreshness"].exists(),
        "unclassifiedTraceSignalReductionExists": INPUTS["unclassifiedTraceSignalReduction"].exists(),
        "traceClassifierRawCoverageGapExists": INPUTS["traceClassifierRawCoverageGap"].exists(),
        "browserSuccessChainRunCount": len(browser_success_runs),
        "browserParentSuccessCookieChainRunCount": len(parent_cookie_runs),
        "classificationBacklogCount": len(rows),
        "classificationBacklogNotInClassifierCount": not_in_classifier_count,
        "safeToPromoteToClassifier": False,
        "noBrowserEvidenceCount": no_browser_count,
        "proposalReadyRunCount": proposal_ready_count,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Turn newly found browser success-chain traces into a controlled classification backlog without treating them as no-browser proof.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "classCounts": dict(class_counts),
        "roleCounts": dict(role_counts),
        "rows": rows,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(BASE / "browser_success_chain_server_visible_diff_audit.json"),
            "nextScript": str(REPO / "tools/build_browser_success_chain_server_visible_diff_audit.py"),
            "reason": (
                "The backlog preserves browser success-chain evidence for classification/diff work. "
                "It contains no fresh no-browser evidence and no isolated proposal-ready transition."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "roleCounts": result["roleCounts"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
