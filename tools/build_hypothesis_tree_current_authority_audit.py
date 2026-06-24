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
OUT = HYP / "hypothesis_tree_current_authority_audit.json"

INPUTS = {
    "historicalHypothesisPlan": ROOT / "docs/pure-protocol-human-hypothesis-plan.md",
    "convergentPlan": ROOT / "docs/pure-protocol-human-evidence-convergent-plan.md",
    "selectedContrastPair": HYP / "selected_contrast_pair.json",
    "hypothesisMatrix": HYP / "hypothesis_matrix.json",
    "collectorStateTransitionDiff": HYP / "collector_state_transition_diff_s00_vs_fresh.json",
    "firstDecisiveDivergence": HYP / "first_decisive_divergence.json",
    "preSeq5StateLineage": HYP / "pre_seq5_state_lineage_detail.json",
    "requestHistoryCoherenceGap": HYP / "request_history_coherence_gap.json",
    "nextDecisiveStaticGap": HYP / "next_decisive_static_gap.json",
    "acceptedLine933GenerationLineage": HYP / "accepted_line933_generation_lineage.json",
    "serverExpectedStatePreSeq5Gap": HYP / "server_expected_state_pre_seq5_gap.json",
    "serverStateTransitionValueModel": HYP / "server_state_transition_value_model.json",
    "singleTransitionCandidateMatrix": HYP / "single_transition_candidate_matrix.json",
    "line922CandidateReduction": HYP / "line922_candidate_reduction.json",
    "jsInternalCandidateReduction": HYP / "js_internal_candidate_reduction.json",
    "collectorToRiskConsumptionChain": HYP / "collector_to_risk_consumption_chain.json",
    "convergentEntranceMatrix": HYP / "convergent_evidence_entrance_matrix.json",
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


def text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items() if path.suffix == ".json"}
    c_hyp = checks(docs["hypothesisMatrix"])
    c_diff = checks(docs["collectorStateTransitionDiff"])
    c_first = checks(docs["firstDecisiveDivergence"])
    c_pre = checks(docs["preSeq5StateLineage"])
    c_order = checks(docs["requestHistoryCoherenceGap"])
    c_static = checks(docs["nextDecisiveStaticGap"])
    c_lineage = checks(docs["acceptedLine933GenerationLineage"])
    c_server_gap = checks(docs["serverExpectedStatePreSeq5Gap"])
    c_value = checks(docs["serverStateTransitionValueModel"])
    c_single = checks(docs["singleTransitionCandidateMatrix"])
    c_line922 = checks(docs["line922CandidateReduction"])
    c_js = checks(docs["jsInternalCandidateReduction"])
    c_risk = checks(docs["collectorToRiskConsumptionChain"])
    c_conv = checks(docs["convergentEntranceMatrix"])
    c_pred = checks(docs["promotionPredicateBlocker"])
    c_exec = checks(docs["candidateExecutorReadiness"])
    c_goal = checks(docs["goalCompletionVerifier"])

    historical_plan = text(INPUTS["historicalHypothesisPlan"])
    convergent_plan = text(INPUTS["convergentPlan"])

    phase_chain_present = all(
        INPUTS[name].exists()
        for name in [
            "selectedContrastPair",
            "hypothesisMatrix",
            "collectorStateTransitionDiff",
            "firstDecisiveDivergence",
            "preSeq5StateLineage",
            "requestHistoryCoherenceGap",
            "nextDecisiveStaticGap",
        ]
    )
    h3_terminal = (
        c_first.get("firstDivergenceAtFinalSeq5") is True
        and c_pre.get("readyForFreshExperiment") is False
        and c_order.get("hasOrderGap") is False
        and c_static.get("readyForFreshExperiment") is False
        and c_single.get("singleTransitionCandidateCount") in {None, 0}
    )
    h4_terminal = (
        c_pre.get("s00JsWindowHasParentBridge") is True
        and c_pre.get("parentBridgeNotCookieHeaderAuditPresent") is True
        and c_lineage.get("existingDecodedEqualityRejected") is True
        and c_line922.get("readyForFreshExperiment") is False
        and c_js.get("replayableClientTransitionCandidateCount") in {None, 0}
    )
    h5_not_current_entrance = (
        c_risk.get("riskContinueTokenFeedsCreateAccount") is True
        and c_risk.get("line933DivergenceIsAccepted") is True
        and c_conv.get("recommendedNextEntranceCount") in {None, 0}
    )
    old_plan_no_longer_authorizes_phase5 = (
        "不在 `singleTransitionCandidateCount=0` 时跑 fresh Phase 5" in historical_plan
        and c_single.get("singleTransitionCandidateCount") in {None, 0}
        and c_exec.get("currentGateClosedNoNetworkAttempt") is True
    )
    convergent_plan_is_current_authority = (
        "后续实现以本文档作为新的执行入口" in convergent_plan
        and c_conv.get("recommendedNextEntranceCount") in {None, 0}
        and c_pred.get("unsatisfiedPromotionPredicateCount", 0) > 0
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "historicalPlanExists": INPUTS["historicalHypothesisPlan"].exists(),
        "convergentPlanExists": INPUTS["convergentPlan"].exists(),
        "phaseChainPresent": phase_chain_present,
        "hypothesisMatrixPrimaryNextIsH3": c_hyp.get("primaryNextIsH3"),
        "diffFirstCandidateIsResponseHandlerDiff": c_diff.get("firstCandidateIsResponseHandlerDiff"),
        "firstDivergenceAtFinalSeq5": c_first.get("firstDivergenceAtFinalSeq5"),
        "requestHistoryOrderGapFalsified": c_order.get("hasOrderGap") is False,
        "nextStaticGapReadyForFreshExperiment": c_static.get("readyForFreshExperiment") is True,
        "h3CollectorServerStateTerminalForCurrentEvidence": h3_terminal,
        "h4BrowserOnlyRuntimeTerminalForCurrentEvidence": h4_terminal,
        "h5MicrosoftContextNotCurrentEntrance": h5_not_current_entrance,
        "singleTransitionCandidateCount": c_single.get("singleTransitionCandidateCount"),
        "jsReplayableClientTransitionCandidateCount": c_js.get("replayableClientTransitionCandidateCount"),
        "convergentRecommendedNextEntranceCount": c_conv.get("recommendedNextEntranceCount"),
        "promotionPredicateUnsatisfiedCount": c_pred.get("unsatisfiedPromotionPredicateCount"),
        "candidateExecutorCurrentGateClosedNoNetworkAttempt": c_exec.get("currentGateClosedNoNetworkAttempt"),
        "oldPlanNoLongerAuthorizesPhase5": old_plan_no_longer_authorizes_phase5,
        "convergentPlanIsCurrentAuthority": convergent_plan_is_current_authority,
        "goalCompletionVerified": c_goal.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    rows = [
        {
            "id": "H3_collector_server_state",
            "status": "terminal_for_current_evidence",
            "evidence": [
                str(INPUTS["firstDecisiveDivergence"]),
                str(INPUTS["preSeq5StateLineage"]),
                str(INPUTS["requestHistoryCoherenceGap"]),
                str(INPUTS["singleTransitionCandidateMatrix"]),
            ],
            "facts": {
                "firstDivergenceAtFinalSeq5": c_first.get("firstDivergenceAtFinalSeq5"),
                "hasOrderGap": c_order.get("hasOrderGap"),
                "singleTransitionCandidateCount": c_single.get("singleTransitionCandidateCount"),
            },
        },
        {
            "id": "H4_browser_only_runtime_state",
            "status": "no_replayable_client_transition_candidate",
            "evidence": [
                str(INPUTS["preSeq5StateLineage"]),
                str(INPUTS["acceptedLine933GenerationLineage"]),
                str(INPUTS["line922CandidateReduction"]),
                str(INPUTS["jsInternalCandidateReduction"]),
            ],
            "facts": {
                "s00JsWindowHasParentBridge": c_pre.get("s00JsWindowHasParentBridge"),
                "existingDecodedEqualityRejected": c_lineage.get("existingDecodedEqualityRejected"),
                "replayableClientTransitionCandidateCount": c_js.get("replayableClientTransitionCandidateCount"),
            },
        },
        {
            "id": "H5_microsoft_context_binding",
            "status": "not_current_experiment_entrance",
            "evidence": [str(INPUTS["collectorToRiskConsumptionChain"]), str(INPUTS["convergentEntranceMatrix"])],
            "facts": {
                "riskContinueTokenFeedsCreateAccount": c_risk.get("riskContinueTokenFeedsCreateAccount"),
                "convergentRecommendedNextEntranceCount": c_conv.get("recommendedNextEntranceCount"),
            },
        },
    ]

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reconcile the historical H0-H5 hypothesis plan with the current convergent gate authority so old H3/H4/H5 wording cannot re-open fresh network experiments without a promoted candidate.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "hypothesisRows": rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "Historical H3/H4/H5 artifacts are present and terminal for current evidence; the current authority remains the convergent gate, which has no recommended entrance, no promoted transition, and no executor-ready candidate.",
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
