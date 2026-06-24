#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
GOAL = PROTO / "goal_audit"
OUT = HYP / "nearest_miss_promotion_candidate_audit.json"

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
    "candidateSourceLedger": HYP / "candidate_source_contradiction_ledger.json",
    "remainingBoundaryProposalGate": HYP / "remaining_boundary_proposal_gate_audit.json",
    "singleTransitionCandidateMatrix": HYP / "single_transition_candidate_matrix.json",
    "browserServerVisibleDiff": HYP / "browser_success_chain_server_visible_diff_audit.json",
    "browserPayloadPcSessionLineage": HYP / "browser_success_payload_pc_session_lineage_audit.json",
    "collectorResponseHandlerValueLineage": HYP / "collector_response_handler_value_lineage_audit.json",
    "resetSingleTransitionCandidates": RESET / "reset_single_transition_candidates.json",
    "resetHookFeatureCandidateReduction": RESET / "reset_hook_feature_candidate_reduction.json",
    "hypothesisTreeCurrentAuthority": HYP / "hypothesis_tree_current_authority_audit.json",
    "promotionPredicateBlocker": HYP / "promotion_predicate_blocker_crosswalk.json",
    "candidateExecutorReadiness": HYP / "candidate_executor_readiness_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def evidence_ok(value: Any) -> bool:
    if isinstance(value, str):
        return Path(value).exists()
    if isinstance(value, list):
        return bool(value) and all(evidence_ok(item.get("path") if isinstance(item, dict) else item) for item in value)
    return False


def bool_pred(value: Any) -> bool:
    return value is True


def row_from_gate(row: dict[str, Any]) -> dict[str, Any]:
    fields = row.get("proposalFields") or {}
    predicates = {
        "preAccept": fields.get("preAccept") is True,
        "clientVisible": fields.get("clientVisible") is True,
        "pureProtocolConstructible": fields.get("pureProtocolConstructible") is True,
        "valueChain": fields.get("valueChainAllowed") is True,
        "negativeControlNotContradicted": fields.get("contradicted") is not True,
        "singleTransition": row.get("proposalReady") is True,
        "artifactBacked": fields.get("evidenceExists") is True and evidence_ok(row.get("evidence") or []),
        "staleAuthorityClean": True,
    }
    return {
        "id": row.get("id"),
        "source": "remainingBoundaryProposalGate",
        "title": row.get("title"),
        "predicates": predicates,
        "blockers": row.get("blockers") or [],
        "evidence": row.get("evidence") or [],
        "reason": None,
    }


def row_from_matrix(row: dict[str, Any]) -> dict[str, Any]:
    status = row.get("status")
    predicates = {
        "preAccept": status != "downstream_proven_not_root_cause",
        "clientVisible": row.get("serverObservable") is True,
        "pureProtocolConstructible": status not in {"non_request_boundary", "coupled_boundary"},
        "valueChain": row.get("stageProgressMetricDefined") is True or row.get("serverObservable") is True,
        "negativeControlNotContradicted": row.get("negativeControlCovered") is not True and status != "eliminated",
        "singleTransition": row.get("singleVariable") is True and row.get("readyForFreshExperiment") is True,
        "artifactBacked": evidence_ok(row.get("evidence") or []),
        "staleAuthorityClean": True,
    }
    return {
        "id": row.get("id"),
        "source": "singleTransitionCandidateMatrix",
        "title": row.get("title"),
        "predicates": predicates,
        "blockers": [row.get("reason")] if row.get("reason") else [],
        "evidence": row.get("evidence") or [],
        "reason": row.get("reason"),
        "nextEvidenceNeeded": row.get("nextEvidenceNeeded"),
    }


def row_from_diff(row: dict[str, Any]) -> dict[str, Any]:
    evidence = [str(INPUTS["browserServerVisibleDiff"])]
    predicates = {
        "preAccept": row.get("preAccept") is True,
        "clientVisible": row.get("clientVisible") is True,
        "pureProtocolConstructible": row.get("pureProtocolConstructible") is True,
        "valueChain": bool(row.get("valueChain")),
        "negativeControlNotContradicted": row.get("contradicted") is not True,
        "singleTransition": row.get("proposalReady") is True,
        "artifactBacked": evidence_ok(evidence),
        "staleAuthorityClean": True,
    }
    return {
        "id": row.get("feature") or row.get("id"),
        "source": "browserSuccessChainServerVisibleDiff",
        "title": row.get("feature"),
        "predicates": predicates,
        "blockers": row.get("blockers") or [],
        "evidence": evidence,
        "reason": None,
    }


def row_from_field_lineage(row: dict[str, Any], source: str) -> dict[str, Any]:
    predicates = {
        "preAccept": row.get("preAccept") is True,
        "clientVisible": row.get("clientVisible") is True,
        "pureProtocolConstructible": row.get("pureProtocolConstructible") is True,
        "valueChain": bool(row.get("valueChain")),
        "negativeControlNotContradicted": row.get("contradicted") is not True,
        "singleTransition": row.get("proposalReady") is True,
        "artifactBacked": evidence_ok(row.get("evidence") or []),
        "staleAuthorityClean": True,
    }
    return {
        "id": row.get("id"),
        "source": source,
        "title": row.get("id"),
        "predicates": predicates,
        "blockers": row.get("blockers") or [],
        "evidence": row.get("evidence") or [],
        "reason": None,
    }


def row_from_reset_hook(row: dict[str, Any]) -> dict[str, Any]:
    fr = row.get("featureReduction") or {}
    sc = row.get("sourceCandidate") or {}
    predicates = {
        "preAccept": fr.get("browserOnlyExecutionContext") is not True,
        "clientVisible": sc.get("clientVisibleProxy") is True,
        "pureProtocolConstructible": fr.get("pureProtocolConstructible") is True,
        "valueChain": bool(row.get("feature")),
        "negativeControlNotContradicted": fr.get("negativeControlsContradict") is not True,
        "singleTransition": row.get("promotedSingleTransitionCandidate") is True,
        "artifactBacked": evidence_ok(list((row.get("evidence") or {}).values())),
        "staleAuthorityClean": True,
    }
    return {
        "id": row.get("feature"),
        "source": "resetHookFeatureCandidateReduction",
        "title": row.get("feature"),
        "predicates": predicates,
        "blockers": [fr.get("reason") or sc.get("reason")],
        "evidence": row.get("evidence") or {},
        "reason": fr.get("reason") or sc.get("reason"),
    }


def annotate(row: dict[str, Any]) -> dict[str, Any]:
    predicates = row["predicates"]
    satisfied = [key for key in PREDICATES if predicates.get(key) is True]
    missing = [key for key in PREDICATES if predicates.get(key) is not True]
    blocker_classes = []
    if "pureProtocolConstructible" in missing:
        blocker_classes.append("needs_constructibility_proof")
    if "negativeControlNotContradicted" in missing:
        blocker_classes.append("needs_negative_control_escape")
    if "singleTransition" in missing:
        blocker_classes.append("needs_single_transition_factorization")
    if "clientVisible" in missing:
        blocker_classes.append("needs_client_visible_proxy")
    if "preAccept" in missing:
        blocker_classes.append("is_post_accept_or_outcome")
    if "artifactBacked" in missing:
        blocker_classes.append("needs_artifact_backing")
    row["satisfiedPredicates"] = satisfied
    row["missingPredicates"] = missing
    row["satisfiedPredicateCount"] = len(satisfied)
    row["missingPredicateCount"] = len(missing)
    row["blockerClasses"] = blocker_classes
    row["proposalReady"] = len(missing) == 0
    return row


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    candidates: list[dict[str, Any]] = []
    for row in docs["remainingBoundaryProposalGate"].get("rows") or []:
        candidates.append(annotate(row_from_gate(row)))
    for row in docs["singleTransitionCandidateMatrix"].get("candidates") or []:
        candidates.append(annotate(row_from_matrix(row)))
    for row in docs["browserServerVisibleDiff"].get("earliestServerVisibleDiffRows") or []:
        candidates.append(annotate(row_from_diff(row)))
    for row in docs["browserPayloadPcSessionLineage"].get("fieldLineageRows") or []:
        candidates.append(annotate(row_from_field_lineage(row, "browserPayloadPcSessionLineage")))
    for row in docs["collectorResponseHandlerValueLineage"].get("valueLineageRows") or []:
        candidates.append(annotate(row_from_field_lineage(row, "collectorResponseHandlerValueLineage")))
    for row in docs["resetHookFeatureCandidateReduction"].get("reductions") or []:
        candidates.append(annotate(row_from_reset_hook(row)))

    candidates.sort(key=lambda row: (-row["satisfiedPredicateCount"], row["missingPredicateCount"], row["source"], str(row["id"])))
    nearest = candidates[:10]
    proposal_ready = [row for row in candidates if row.get("proposalReady") is True]
    nearest_score = nearest[0]["satisfiedPredicateCount"] if nearest else 0
    nearest_missing = nearest[0]["missingPredicateCount"] if nearest else len(PREDICATES)

    c_pred = checks(docs["promotionPredicateBlocker"])
    c_exec = checks(docs["candidateExecutorReadiness"])
    c_goal = checks(docs["goalCompletionVerifier"])

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "candidateRowCount": len(candidates),
        "allRowCount": len(candidates),
        "nearestSatisfiedPredicateCount": nearest_score,
        "nearestMissingPredicateCount": nearest_missing,
        "proposalReadyCandidateCount": len(proposal_ready),
        "singleMissingPredicateCandidateCount": sum(1 for row in candidates if row["missingPredicateCount"] == 1),
        "candidateWithConstructibilityProofCount": sum(1 for row in candidates if row["predicates"].get("pureProtocolConstructible") is True),
        "candidateWithNegativeControlEscapeCount": sum(1 for row in candidates if row["predicates"].get("negativeControlNotContradicted") is True),
        "candidateWithSingleTransitionCount": sum(1 for row in candidates if row["predicates"].get("singleTransition") is True),
        "promotionPredicateUnsatisfiedCount": c_pred.get("unsatisfiedPromotionPredicateCount"),
        "executorReadyForPromotedCandidate": c_exec.get("executorReadyForPromotedCandidate"),
        "goalCompletionVerified": c_goal.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Rank all current near-miss promotion candidates by the eight promotion predicates so the next evidence search targets the smallest missing proof instead of broad negative-control accumulation.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "predicates": PREDICATES,
        "allRows": candidates,
        "nearestRows": nearest,
        "proposalReadyRows": proposal_ready,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "No current near-miss satisfies all promotion predicates. The nearest rows still need constructibility, negative-control escape, and/or single-transition factorization before any proposal or network experiment."
            ),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "nearestRows": nearest[:3]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
