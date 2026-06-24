#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "js_internal_candidate_reduction.json"

INPUTS = {
    "jsInternalEventTaxonomy": BASE / "js_internal_event_taxonomy.json",
    "historicalProbeResponseClassMatrix": BASE / "historical_probe_response_class_matrix.json",
    "crossSampleServerStateProxyMatrix": BASE / "cross_sample_server_state_proxy_matrix.json",
    "serverInternalUnobservedStateFinalGap": BASE / "server_internal_unobserved_state_final_gap.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_candidate(feature: str) -> tuple[str, str, bool]:
    if "oIIoIooo" in feature:
        return (
            "outcome_handler",
            "oIIoIooo dispatch is the success/failure result handler itself; it is not a pre-accept replayable input.",
            False,
        )
    if any(token in feature for token in ["IooIIo", "IooIoI", "oIIooIoo"]):
        return (
            "pow_challenge_response_handler",
            "These handlers are emitted by collector POW challenge responses. Historical no-browser probes already reach bundle POW and still fail at seq5 oIIoIooo|-1, so POW handler presence is not sufficient.",
            False,
        )
    if any(token in feature for token in ['["fp"', '["rf"', '["nf"']):
        return (
            "collector_cookie_flag_handler",
            "IIooII fp/rf/nf flags are response-side cookie/config mutations. They are downstream of collector response handling and have no standalone request transition in current evidence.",
            False,
        )
    return (
        "unclassified_js_candidate",
        "No reduction rule exists for this candidate; keep it non-ready until mapped to a request/handler transition.",
        False,
    )


def build() -> dict[str, Any]:
    docs = {name: load_json(path) for name, path in INPUTS.items()}
    taxonomy = docs["jsInternalEventTaxonomy"]
    historical = docs["historicalProbeResponseClassMatrix"]

    candidates = taxonomy.get("candidateNonOutcomeClientEvents") or []
    rows = []
    for candidate in candidates:
        category, reason, replayable = classify_candidate(candidate.get("feature") or "")
        rows.append(
            {
                "feature": candidate.get("feature"),
                "taxonomyCategory": candidate.get("category"),
                "reductionCategory": category,
                "fullTrueCount": candidate.get("fullTrueCount"),
                "nonFullTrueCount": candidate.get("nonFullTrueCount"),
                "replayableClientTransition": replayable,
                "reason": reason,
            }
        )

    replayable_rows = [row for row in rows if row["replayableClientTransition"]]
    pow_rows = [row for row in rows if row["reductionCategory"] == "pow_challenge_response_handler"]
    flag_rows = [row for row in rows if row["reductionCategory"] == "collector_cookie_flag_handler"]
    outcome_rows = [row for row in rows if row["reductionCategory"] == "outcome_handler"]
    unclassified = [row for row in rows if row["reductionCategory"] == "unclassified_js_candidate"]

    hist_checks = historical.get("checks") or {}
    checks = {
        "candidateCount": len(rows),
        "powChallengeHandlerCandidateCount": len(pow_rows),
        "cookieFlagHandlerCandidateCount": len(flag_rows),
        "outcomeHandlerCandidateCount": len(outcome_rows),
        "unclassifiedCandidateCount": len(unclassified),
        "replayableClientTransitionCandidateCount": len(replayable_rows),
        "historicalDirectReachBundlePow": hist_checks.get("allDirectReachBundlePow") is True,
        "historicalOverlapReachBundlePow": hist_checks.get("allOverlapReachBundlePow") is True,
        "historicalSeq5FailureMinus1Count": hist_checks.get("seq5Seq6ComboSeq5FailureMinus1Count"),
        "historicalNoBrowserSuccess0": hist_checks.get("hasHistoricalNoBrowserSuccess0") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Reduce JS internal event taxonomy candidates to determine whether any is a replayable client transition.",
        "inputs": {name: str(path.resolve()) for name, path in INPUTS.items()},
        "candidateReductions": rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "replayableClientTransitionFound": bool(replayable_rows),
            "reason": (
                "JS candidates reduce to POW challenge handlers, collector cookie/config flags, or outcome handlers. "
                "Existing no-browser probes already reach POW but still fail at seq5 oIIoIooo|-1, so these candidates do not unlock a fresh experiment."
            ),
            "nextArtifact": str((BASE / "server_internal_unobserved_state_final_gap.json").resolve()),
            "nextScript": str((REPO / "tools/build_server_internal_unobserved_state_final_gap.py").resolve()),
        },
        "checks": checks,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
