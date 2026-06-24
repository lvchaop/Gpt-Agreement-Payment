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
OUT = HYP / "candidate_executor_readiness_audit.json"

INPUTS = {
    "implementationPlan": ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md",
    "forwardPlan": ROOT / "docs/pure-protocol-human-evidence-gated-forward-plan.md",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "promotionPredicateBlocker": HYP / "promotion_predicate_blocker_crosswalk.json",
    "minimalExperiment": HYP / "minimal_promoted_transition_experiment.json",
    "evidenceGatedPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalReplay": GOAL / "final_pure_protocol_replay_audit.json",
    "liveRunnerGate": HYP / "live_runner_gate_audit.json",
}

HARNESS_FILES = {
    "minimalExperimentScript": ROOT / "tools/run_minimal_promoted_transition_experiment.py",
    "evidenceGatedPocScript": ROOT / "tools/run_evidence_gated_end_to_end_pure_protocol_poc.py",
    "finalReplayScript": ROOT / "tools/build_final_pure_protocol_replay_audit.py",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items() if path.suffix == ".json"}
    c_intake = checks(docs["candidateIntake"])
    c_blocker = checks(docs["promotionPredicateBlocker"])
    c_minimal = checks(docs["minimalExperiment"])
    c_poc = checks(docs["evidenceGatedPoc"])
    c_final = checks(docs["finalReplay"])
    c_live = checks(docs["liveRunnerGate"])

    plan_text = "\n".join(read_text(path) for name, path in INPUTS.items() if path.suffix == ".md")
    harness_texts = {name: read_text(path) for name, path in HARNESS_FILES.items()}

    plan_requires_candidate_specific = "candidate-specific" in plan_text and "网络命令不写入" in plan_text
    harness_declares_missing_executor = (
        "candidate-specific executor is intentionally not implemented" in harness_texts["minimalExperimentScript"]
        and "live network PoC executor has not been implemented" in harness_texts["evidenceGatedPocScript"]
        and "final replay execution is not implemented" in harness_texts["finalReplayScript"]
    )
    current_gate_closed = (
        c_intake.get("promotedSingleTransitionCandidateCount") in {None, 0}
        and c_blocker.get("unsatisfiedPromotionPredicateCount", 0) > 0
        and c_minimal.get("networkAttemptExecuted") is not True
        and c_poc.get("networkAttemptExecuted") is not True
        and c_final.get("networkAttemptExecuted") is not True
        and c_live.get("currentNetworkAttemptBlocked") is True
    )
    executor_ready_for_promoted_candidate = False

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()) and all(path.exists() for path in HARNESS_FILES.values()),
        "planRequiresCandidateSpecificExecutor": plan_requires_candidate_specific,
        "harnessDeclaresMissingCandidateSpecificExecutor": harness_declares_missing_executor,
        "candidateIntakePromotedCount": c_intake.get("promotedSingleTransitionCandidateCount"),
        "promotionPredicateUnsatisfiedCount": c_blocker.get("unsatisfiedPromotionPredicateCount"),
        "minimalExperimentNetworkAttemptExecuted": c_minimal.get("networkAttemptExecuted"),
        "evidenceGatedPocNetworkAttemptExecuted": c_poc.get("networkAttemptExecuted"),
        "finalReplayNetworkAttemptExecuted": c_final.get("networkAttemptExecuted"),
        "liveRunnerCurrentNetworkAttemptBlocked": c_live.get("currentNetworkAttemptBlocked"),
        "currentGateClosedNoNetworkAttempt": current_gate_closed,
        "executorReadyForPromotedCandidate": executor_ready_for_promoted_candidate,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit whether the minimal/PoC/final replay harnesses have a candidate-specific executor path, so future gate readiness cannot be mistaken for executable network approval.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "harnessFiles": {name: str(path) for name, path in HARNESS_FILES.items()},
        "checks": checks_out,
        "readinessRows": [
            {
                "id": "current_no_candidate_state",
                "status": "closed",
                "evidence": [
                    str(INPUTS["candidateIntake"]),
                    str(INPUTS["promotionPredicateBlocker"]),
                    str(INPUTS["minimalExperiment"]),
                    str(INPUTS["evidenceGatedPoc"]),
                    str(INPUTS["finalReplay"]),
                ],
                "facts": {
                    "candidateIntakePromotedCount": c_intake.get("promotedSingleTransitionCandidateCount"),
                    "promotionPredicateUnsatisfiedCount": c_blocker.get("unsatisfiedPromotionPredicateCount"),
                    "currentGateClosedNoNetworkAttempt": current_gate_closed,
                },
            },
            {
                "id": "future_promoted_candidate_executor_contract",
                "status": "not_ready_until_candidate_specific_executor_exists",
                "evidence": [str(INPUTS["implementationPlan"]), *[str(path) for path in HARNESS_FILES.values()]],
                "facts": {
                    "planRequiresCandidateSpecificExecutor": plan_requires_candidate_specific,
                    "harnessDeclaresMissingCandidateSpecificExecutor": harness_declares_missing_executor,
                    "executorReadyForPromotedCandidate": executor_ready_for_promoted_candidate,
                },
            },
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Current gates are closed and no network attempt executed. If a future candidate is promoted, a candidate-specific executor must be attached before any fresh network run; the generic harnesses are not themselves executable PoC implementations."
            ),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
