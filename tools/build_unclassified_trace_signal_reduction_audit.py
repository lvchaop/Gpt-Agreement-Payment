#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "unclassified_trace_signal_reduction_audit.json"

INPUTS = {
    "freshness": BASE / "local_trace_evidence_freshness_audit.json",
    "remainingBoundaryProposalGate": BASE / "remaining_boundary_proposal_gate_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
    "currentPlan": REPO / "docs/pure-protocol-human-evidence-first-current-plan.md",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def merged_counts(row: dict[str, Any]) -> Counter[str]:
    out: Counter[str] = Counter()
    for key in ("runtime", "js"):
        scan = row.get(key)
        if not scan:
            continue
        for name, count in (scan.get("tokenCounts") or {}).items():
            if count:
                out[name] += count
    return out


def classify(row: dict[str, Any]) -> str:
    counts = merged_counts(row)
    has_success = counts["parentSucceeded"] > 0 or counts["collectorSuccess0"] > 0
    has_failure = counts["parentFailed"] > 0 or counts["collectorFailureMinus1"] > 0
    has_downstream = counts["riskContinue"] > 0 or counts["createRedirect"] > 0
    has_collector = counts["collectorMsft"] > 0 or counts["collectorBundle"] > 0
    has_px = counts["px3"] > 0 or counts["pxde"] > 0
    if has_success and has_downstream:
        return "browser_success_chain"
    if has_success and has_px:
        return "browser_parent_success_cookie_chain"
    if has_failure:
        return "browser_failure_or_retry_chain"
    if has_downstream and has_collector:
        return "browser_downstream_create_or_continue_without_extracted_success"
    if has_collector:
        return "collector_material_only"
    if has_px:
        return "px_cookie_material_only"
    return "low_value_or_unclassified"


def proposal_assessment(row: dict[str, Any], cls: str) -> dict[str, Any]:
    # These are browser traces. They can become classification/comparison
    # evidence, but do not by themselves prove a no-browser constructible
    # transition.
    pre_accept = cls in {
        "browser_success_chain",
        "browser_parent_success_cookie_chain",
        "browser_downstream_create_or_continue_without_extracted_success",
        "collector_material_only",
    }
    client_visible = True
    pure_protocol_constructible = False
    value_chain = "request" if "collector" in cls else "cookie"
    contradicted = True
    blockers = [
        "source is browser runtime/js trace, not no-browser pure-protocol execution",
        "no single request/cookie/risk/verify transition is isolated",
        "existing candidate intake still has promotedSingleTransitionCandidateCount=0",
    ]
    if cls == "browser_success_chain":
        blockers.append("success/downstream chain is outcome evidence and requires separate classifier/decode material before proposal use")
    if cls == "collector_material_only":
        blockers.append("collector traffic presence alone is already common in failure controls")
    return {
        "preAccept": pre_accept,
        "clientVisible": client_visible,
        "pureProtocolConstructible": pure_protocol_constructible,
        "valueChain": value_chain,
        "contradicted": contradicted,
        "proposalReady": False,
        "blockers": blockers,
    }


def build() -> dict[str, Any]:
    freshness = read_json(INPUTS["freshness"])
    intake = read_json(INPUTS["candidateIntake"])
    rows = freshness.get("unclassifiedRows") or []

    reduced = []
    for row in rows:
        cls = classify(row)
        counts = dict(merged_counts(row))
        reduced.append(
            {
                "run": row.get("run"),
                "hasRuntimeTrace": row.get("hasRuntimeTrace"),
                "hasJsInternalTrace": row.get("hasJsInternalTrace"),
                "classification": cls,
                "tokenCounts": counts,
                "proposalAssessment": proposal_assessment(row, cls),
            }
        )

    class_counts = Counter(row["classification"] for row in reduced)
    browser_success = [row for row in reduced if row["classification"] == "browser_success_chain"]
    parent_cookie = [row for row in reduced if row["classification"] == "browser_parent_success_cookie_chain"]
    collector_only = [row for row in reduced if row["classification"] == "collector_material_only"]
    proposal_ready = [row for row in reduced if row["proposalAssessment"]["proposalReady"]]

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "freshnessAuditExists": INPUTS["freshness"].exists(),
        "freshnessUnclassifiedRunCount": (freshness.get("checks") or {}).get("unclassifiedRunCount"),
        "reducedRunCount": len(reduced),
        "browserSuccessChainRunCount": len(browser_success),
        "browserParentSuccessCookieChainRunCount": len(parent_cookie),
        "collectorMaterialOnlyRunCount": len(collector_only),
        "proposalReadyRunCount": len(proposal_ready),
        "candidateIntakePromotedCount": (intake.get("checks") or {}).get("promotedSingleTransitionCandidateCount"),
        "classificationEvidenceOnly": len(browser_success) > 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Reduce unclassified local browser trace signals into proposal-relevant categories without running network.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "classCounts": dict(class_counts),
        "browserSuccessChainRuns": [row["run"] for row in browser_success],
        "browserParentSuccessCookieChainRuns": [row["run"] for row in parent_cookie],
        "proposalReadyRows": proposal_ready,
        "rows": reduced,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Unclassified traces add browser-side success/classification evidence, but every reduced row remains non-constructible as a pure-protocol proposal. "
                "They should update coverage/classification evidence, not trigger a fresh network experiment."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "classCounts": result["classCounts"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
