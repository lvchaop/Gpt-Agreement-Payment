#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
RESET = ROOT / "output/protocol_reverse/reset_plan"
TAXONOMY = RESET / "reset_runtime_js_event_taxonomy.json"
HANDLER_AUDIT = RESET / "reset_collector_handler_surface_audit.json"
HOOK_REDUCTION = RESET / "reset_hook_feature_candidate_reduction.json"
FINAL_CLASS = RESET / "reset_final_response_class_audit.json"
COOKIE = RESET / "reset_cookie_mutation_audit.json"
SINGLE = RESET / "reset_single_transition_candidates.json"
ONECOLLECTOR = RESET / "reset_onecollector_surface_audit.json"
GOAL = ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json"
OUT = RESET / "reset_runtime_js_candidate_reduction.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def goal_proved(goal: dict[str, Any], item: str) -> bool:
    return item in ((goal.get("summary") or {}).get("proved") or [])


def classify(feature: str) -> tuple[str, str]:
    if any(token in feature for token in ["oIIoIooo", "succeeded", "challenge_success", "redirectUrl"]):
        return "outcome_or_downstream", "Outcome/downstream markers are not pre-accept replayable inputs."
    if feature.startswith("js.data.channel:") or feature.startswith("js.kind:hsprotect.Xn."):
        return "hsprotect_event_bus", "HUMAN iframe event-bus channel/subscribe/trigger surface; current evidence does not map it to a standalone request input."
    if feature.startswith("js.data.handlerKey:") or feature.startswith("js.handlerArgs:"):
        return "collector_response_handler", "Collector handler dispatch is response-side state, not a pre-accept transition unless its resulting request/cookie/risk input is identified."
    if feature.startswith("js.data.table:"):
        return "collector_response_handler", "Collector handler table identity is response-side dispatch metadata, not a standalone pre-accept request input."
    if feature.startswith("js.data.target:"):
        return "worker_pow_runtime", "captcha.qs.start target values are POW challenge targets; POW recompute is already proved and not sufficient for final collector success."
    if "wasm" in feature or "__wbg_" in feature or "__wbindgen" in feature or "getRandomValues" in feature:
        return "wasm_or_crypto_runtime", "WASM/crypto runtime semantics are already reduced by fresh Ws.NQ/TBR9 and Ws.Ng/AEAx audits."
    if "worker" in feature or "pow" in feature:
        return "worker_pow_runtime", "Worker/POW runtime semantics are already reduced by POW recompute and hook-feature audits."
    if "sendBeacon" in feature:
        return "sendbeacon_internal", "Existing sendBeacon temporal evidence classifies sendBeacon as not a proved pre-success necessary transition."
    if feature.startswith("bridge.cookie"):
        return "cookie_bridge_surface", "Cookie bridge is observable, but current reset cookie audit proves _px3/_pxde mutation alone is not a success/risk candidate."
    if "browser.events.data.microsoft.com/OneCollector/1.0/" in feature:
        return "onecollector_telemetry", "Microsoft OneCollector telemetry is downstream browser telemetry, not a HUMAN collector pre-accept transition."
    if feature.startswith("runtime.request:") or feature.startswith("runtime.url_path:") or feature.startswith("runtime.response:"):
        return "network_surface", "Network surface requires a single differing pre-accept request that is constructible and not already replayed."
    if feature.startswith("runtime.console_token:"):
        return "runtime_console_surface", "Console token mirrors hooked browser internals; needs mapping to request/cookie/risk input before experiment."
    if feature.startswith("js.token:"):
        return "js_token_surface", "Token-level surface is too coarse without a value lineage into request/cookie/risk."
    return "unclassified_surface", "No reduction rule proves this as a replayable transition; keep blocked until value lineage is shown."


def build() -> dict[str, Any]:
    taxonomy = read_json(TAXONOMY)
    hook_reduction = read_json(HOOK_REDUCTION)
    handler_audit = read_json(HANDLER_AUDIT)
    final_class = read_json(FINAL_CLASS)
    cookie = read_json(COOKIE)
    single = read_json(SINGLE)
    onecollector = read_json(ONECOLLECTOR)
    goal = read_json(GOAL)
    candidates = taxonomy.get("candidateClientVisibleProxies") or []

    final_checks = final_class.get("checks") or {}
    cookie_checks = cookie.get("checks") or {}
    single_checks = single.get("checks") or {}
    onecollector_checks = onecollector.get("checks") or {}
    hook_checks = hook_reduction.get("checks") or {}
    handler_checks = handler_audit.get("checks") or {}
    negative_controls = {
        "powRecomputeProved": goal_proved(goal, "pow_recompute"),
        "freshTbr9WsNqProved": goal_proved(goal, "fresh_tbr9_ws_nq"),
        "freshAeaxWsNgProved": goal_proved(goal, "fresh_aeax_ws_ng"),
        "hookFeatureReductionPromotedNone": hook_checks.get("promotedSingleTransitionCandidateCount") == 0,
        "pureProtocolFinalResponsesSameFailureClass": final_checks.get("allFinalResponsesSameClass") is True
        and final_checks.get("allFinalResponsesAreSeq5Minus1") is True
        and final_checks.get("anySeq5Success0") is False,
        "decodedCookieMutationNotSuccess": cookie_checks.get("allOfflineJarHasPx3Pxde") is True
        and cookie_checks.get("anySuccess0") is False,
        "singleTransitionCandidateStillAbsent": single_checks.get("singleTransitionCandidateCount") == 0,
        "oneCollectorNotPromoted": onecollector_checks.get("promoteToSingleTransitionCandidate") is False
        and onecollector_checks.get("allOneCollectorSuccessRowsAfterAcceptedChain") is True,
        "collectorHandlerSurfaceAuditNotPromoted": handler_checks.get("promotedSingleTransitionCandidateCount") == 0
        and handler_checks.get("unclassifiedHandlerSurfaceCount") == 0,
    }

    reductions = []
    for cand in candidates:
        feature = cand.get("feature") or ""
        category, reason = classify(feature)
        enters_request_cookie_risk = category in {"network_surface", "cookie_bridge_surface"}
        constructible = False
        # A network/cookie surface only becomes constructible after a value-level lineage exists; taxonomy features are labels only.
        promoted = enters_request_cookie_risk and constructible
        reductions.append(
            {
                "feature": feature,
                "sourceCategory": cand.get("category"),
                "reductionCategory": category,
                "successCount": cand.get("successCount"),
                "failureCount": cand.get("failureCount"),
                "successWithJsCount": cand.get("successWithJsCount"),
                "failureWithJsCount": cand.get("failureWithJsCount"),
                "examples": cand.get("examples"),
                "evidence": {
                    "taxonomy": str(TAXONOMY),
                    "collectorHandlerSurfaceAudit": str(HANDLER_AUDIT),
                    "hookFeatureReduction": str(HOOK_REDUCTION),
                    "finalResponseClassAudit": str(FINAL_CLASS),
                    "cookieMutationAudit": str(COOKIE),
                    "singleTransitionCandidates": str(SINGLE),
                    "oneCollectorSurfaceAudit": str(ONECOLLECTOR),
                },
                "decision": {
                    "promoteToSingleTransitionCandidate": promoted,
                    "clientVisibleProxy": False,
                    "constructiblePreAcceptTransitionProved": False,
                    "entersRequestCookieRiskProved": enters_request_cookie_risk,
                    "classification": "not_phase5_input",
                    "reason": reason,
                },
            }
        )

    category_counts = Counter(row["reductionCategory"] for row in reductions)
    promoted_rows = [r for r in reductions if (r.get("decision") or {}).get("promoteToSingleTransitionCandidate")]
    unclassified_rows = [r for r in reductions if r["reductionCategory"] == "unclassified_surface"]
    checks = {
        "taxonomyExists": TAXONOMY.exists(),
        "candidateInputCount": len(candidates),
        "reductionCount": len(reductions),
        "categoryCounts": dict(category_counts),
        "promotedSingleTransitionCandidateCount": len(promoted_rows),
        "unclassifiedReductionCount": len(unclassified_rows),
        "allCandidatesReduced": len(reductions) == len(candidates),
        "negativeControlsAllHold": all(negative_controls.values()),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Reduce reset runtime/JS taxonomy candidates into replayable Phase 5 candidates or blocked correlated surfaces.",
        "inputs": {
            "taxonomy": str(TAXONOMY),
            "hookFeatureReduction": str(HOOK_REDUCTION),
            "collectorHandlerSurfaceAudit": str(HANDLER_AUDIT),
            "finalResponseClassAudit": str(FINAL_CLASS),
            "cookieMutationAudit": str(COOKIE),
            "singleTransitionCandidates": str(SINGLE),
            "goalGapAudit": str(GOAL),
        },
        "checks": checks,
        "negativeControls": negative_controls,
        "categoryCounts": dict(category_counts),
        "promotedCandidates": promoted_rows,
        "unclassifiedReductions": unclassified_rows[:50],
        "reductionsSample": reductions[:200],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All reset runtime/JS taxonomy candidates are correlated surfaces only; none is proved as a single "
                "client-visible, constructible, pre-accept transition. Do not run Phase 5."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "categoryCounts": doc["categoryCounts"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
