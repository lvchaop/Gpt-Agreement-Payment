#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
GOAL = ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json"
STATE = RESET / "reset_state_machine.json"
SINGLE = RESET / "reset_single_transition_candidates.json"
FINAL_CLASS = RESET / "reset_final_response_class_audit.json"
COOKIE = RESET / "reset_cookie_mutation_audit.json"
NEW_HOOK_AXIS = RESET / "reset_new_hook_axis_plan.json"
WASM_REPLAY = ROOT / "output/protocol_reverse/wasm/wasm_ng_runtime_random_replay_audit_gwyi06rpe015_1781208840.json"
OUT = RESET / "reset_hook_feature_candidate_reduction.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def goal_proved(goal: dict[str, Any], item: str) -> bool:
    return item in ((goal.get("summary") or {}).get("proved") or [])


def feature_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for cand in state.get("candidateClientVisibleProxies") or []:
        if cand.get("candidateType") == "success_only_hook_feature":
            out.append(cand)
    return out


def reduce_feature(
    feature: str,
    cand: dict[str, Any],
    *,
    state: dict[str, Any],
    single: dict[str, Any],
    goal: dict[str, Any],
    final_class: dict[str, Any],
    cookie: dict[str, Any],
    new_hook_axis: dict[str, Any],
    wasm_replay: dict[str, Any],
) -> dict[str, Any]:
    final_checks = final_class.get("checks") or {}
    cookie_checks = cookie.get("checks") or {}
    hook_checks = new_hook_axis.get("checks") or {}
    wasm_checks = wasm_replay.get("checks") or {}
    state_checks = state.get("checks") or {}
    single_checks = single.get("checks") or {}

    common_negative_controls = {
        "pureProtocolEndToEndStillMissing": "end_to_end_pure_protocol_poc"
        in ((goal.get("summary") or {}).get("blockingOrMissing") or []),
        "resetPureFinalResponsesSameFailureClass": final_checks.get("allFinalResponsesSameClass") is True
        and final_checks.get("allFinalResponsesAreSeq5Minus1") is True
        and final_checks.get("anySeq5Success0") is False,
        "decodedFailureStillMutatesPx3PxdeButNotSuccess": cookie_checks.get("allOfflineJarHasPx3Pxde") is True
        and cookie_checks.get("allHaveFailureMinus1") is True
        and cookie_checks.get("anySuccess0") is False,
        "noSingleTransitionCandidate": single_checks.get("singleTransitionCandidateCount") == 0,
    }

    per_feature: dict[str, Any]
    if feature == "worker":
        per_feature = {
            "semanticEquivalentAlreadyCovered": goal_proved(goal, "pow_recompute"),
            "browserOnlyContextStillUnprovedAsProtocolInput": True,
            "reason": (
                "Worker presence is success-only in counted browser reset hooks, but the locally proved "
                "protocol equivalent is the POW value, and reset pure-protocol samples already reach POW stages "
                "without producing collector success."
            ),
        }
    elif feature == "pow_worker":
        per_feature = {
            "semanticEquivalentAlreadyCovered": goal_proved(goal, "pow_recompute"),
            "browserOnlyContextStillUnprovedAsProtocolInput": True,
            "reason": (
                "pow_worker is the observed browser execution path for POW. Existing audits prove POW recompute, "
                "but final reset responses remain the same seq5/seq6 failure class, so this feature is not a "
                "standalone transition candidate."
            ),
        }
    elif feature == "wasm":
        per_feature = {
            "semanticEquivalentAlreadyCovered": goal_proved(goal, "fresh_tbr9_ws_nq")
            and goal_proved(goal, "fresh_aeax_ws_ng"),
            "offlineNgNqReplayMatchesRuntime": wasm_checks.get("offlineNgMatchesRuntimeAeax") is True
            and wasm_checks.get("offlineNqMatchesRuntimeTbr9") is True,
            "browserOnlyContextStillUnprovedAsProtocolInput": True,
            "reason": (
                "WASM execution is success-only in counted browser reset hooks, but fresh Ws.NQ/TBR9 and "
                "Ws.Ng/AEAx replay are already proved in local audits. The remaining failure is therefore not "
                "reduced by merely observing that WASM ran in the successful browser path."
            ),
        }
    else:
        per_feature = {
            "semanticEquivalentAlreadyCovered": False,
            "browserOnlyContextStillUnprovedAsProtocolInput": True,
            "reason": "No feature-specific reducer exists; keep it blocked rather than promoting it without evidence.",
        }

    constructible_semantic = per_feature.get("semanticEquivalentAlreadyCovered") is True
    negative_control_blocks = all(common_negative_controls.values())
    can_promote = constructible_semantic and not negative_control_blocks

    return {
        "feature": feature,
        "sourceCandidate": cand,
        "observedBrowserContrast": {
            "successCount": cand.get("successCount"),
            "failureCount": cand.get("failureCount"),
            "hookFeatureCounts": (state_checks.get("hookFeatureCounts") or {}).get(feature),
        },
        "evidence": {
            "stateMachine": str(STATE),
            "singleTransitionCandidates": str(SINGLE),
            "goalGapAudit": str(GOAL),
            "finalResponseClassAudit": str(FINAL_CLASS),
            "cookieMutationAudit": str(COOKIE),
            "newHookAxisPlan": str(NEW_HOOK_AXIS),
            "wasmRuntimeRandomReplayAudit": str(WASM_REPLAY) if feature == "wasm" else None,
        },
        "featureReduction": per_feature,
        "negativeControls": common_negative_controls,
        "decision": {
            "promoteToSingleTransitionCandidate": can_promote,
            "clientVisibleProxy": False,
            "constructiblePreAcceptTransitionProved": False,
            "classification": "correlated_browser_success_feature_not_phase5_input",
            "reason": (
                "The feature is browser-success-correlated, but local reset audits do not prove a single "
                "client-visible, constructible, pre-accept transition that can be changed in pure protocol."
            ),
        },
    }


def main() -> int:
    state = read_json(STATE)
    single = read_json(SINGLE)
    goal = read_json(GOAL)
    final_class = read_json(FINAL_CLASS)
    cookie = read_json(COOKIE)
    new_hook_axis = read_json(NEW_HOOK_AXIS)
    wasm_replay = read_json(WASM_REPLAY)

    candidates = feature_candidates(state)
    reductions = [
        reduce_feature(
            str(cand.get("stage", "")).split("hook_feature:", 1)[-1],
            cand,
            state=state,
            single=single,
            goal=goal,
            final_class=final_class,
            cookie=cookie,
            new_hook_axis=new_hook_axis,
            wasm_replay=wasm_replay,
        )
        for cand in candidates
    ]

    promoted = [r for r in reductions if (r.get("decision") or {}).get("promoteToSingleTransitionCandidate")]
    checks = {
        "stateMachineExists": STATE.exists(),
        "singleTransitionCandidatesExists": SINGLE.exists(),
        "goalGapAuditExists": GOAL.exists(),
        "finalResponseClassAuditExists": FINAL_CLASS.exists(),
        "cookieMutationAuditExists": COOKIE.exists(),
        "newHookAxisPlanExists": NEW_HOOK_AXIS.exists(),
        "successOnlyHookFeatureCandidateCount": len(candidates),
        "reductionCount": len(reductions),
        "promotedSingleTransitionCandidateCount": len(promoted),
        "allHookAxesClosed": (new_hook_axis.get("checks") or {}).get("recommendedAxisCount") == 0,
        "existingSingleTransitionCandidateCount": (single.get("checks") or {}).get("singleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": (
            "Reduce success-only browser hook features into either replayable Phase 5 candidates or explicitly "
            "blocked correlated features using only local reset evidence."
        ),
        "inputs": {
            "stateMachine": str(STATE),
            "singleTransitionCandidates": str(SINGLE),
            "goalGapAudit": str(GOAL),
            "finalResponseClassAudit": str(FINAL_CLASS),
            "cookieMutationAudit": str(COOKIE),
            "newHookAxisPlan": str(NEW_HOOK_AXIS),
            "wasmRuntimeRandomReplayAudit": str(WASM_REPLAY),
        },
        "checks": checks,
        "reductions": reductions,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Hook coverage and contrast are closed, but success-only hook features reduce to correlated "
                "browser execution evidence rather than a single constructible transition. Do not run Phase 5 "
                "until new local evidence exposes a client-visible pre-accept candidate."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
