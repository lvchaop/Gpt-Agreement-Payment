#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "post_c5_decisive_gap_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def build() -> dict[str, Any]:
    line922 = read_json(HYP / "line922_dynamic_field_source_map.json")
    c5 = read_json(HYP / "encoder_variant_terminal_audit.json")
    server_proxy = read_json(HYP / "server_expected_state_observable_proxy.json")
    final_gap = read_json(HYP / "server_internal_unobserved_state_final_gap.json")
    bridge = read_json(HYP / "bridge_to_payload_context_audit.json")
    cookie_bridge = read_json(GOAL / "cookie_session_lineage_gap_audit.json")
    risk_gap = read_json(HYP / "s00_risk_verify_material_gap.json")
    route_b = read_json(ROOT / "output/protocol_reverse/reset_plan/reset_route_b_instrumentation_control_audit.json")

    c_line922 = checks(line922)
    c5_checks = checks(c5)
    c_server = checks(server_proxy)
    c_final = checks(final_gap)
    c_bridge = checks(bridge)
    c_cookie = checks(cookie_bridge)
    c_risk = checks(risk_gap)
    c_route_b = checks(route_b)

    candidates = [
        {
            "id": "C5_payload_pc_marker_uuid_encoder_family",
            "status": "closed_no_success",
            "evidence": str(HYP / "encoder_variant_terminal_audit.json"),
            "facts": {
                "encoderVariantFamilyClosedNoSuccess": c5_checks.get("encoderVariantFamilyClosedNoSuccess"),
                "liveProbeAnyCollectorSuccess": c5_checks.get("liveProbeAnyCollectorSuccess"),
                "liveProbeSeq5ReturnedDoEmpty": c5_checks.get("liveProbeSeq5ReturnedDoEmpty"),
            },
            "readyForFreshExperiment": False,
        },
        {
            "id": "H3_C6_collector_server_expected_state",
            "status": "remaining_non_replayable_gap",
            "evidence": str(HYP / "server_internal_unobserved_state_final_gap.json"),
            "facts": {
                "serverObservableProxyNotFound": c_server.get("transitionHasReplayableClientRepresentation") is False,
                "allLocalProxySearchesNegative": c_final.get("allLocalProxySearchesNegative"),
                "singleTransitionCandidateCount": c_final.get("singleTransitionCandidateCount"),
            },
            "whyNotReady": "No client-visible request/handler transition currently maps server expected state to a replayable pure-protocol input.",
            "readyForFreshExperiment": False,
        },
        {
            "id": "H4_browser_parent_bridge_or_in_memory_context",
            "status": "highest_priority_static_lineage_gap",
            "evidence": [
                str(HYP / "bridge_to_payload_context_audit.json"),
                str(GOAL / "cookie_session_lineage_gap_audit.json"),
                str(HYP / "line922_dynamic_field_source_map.json"),
            ],
            "facts": {
                "hasParentPx3BeforeLine922": c_bridge.get("hasParentPx3BeforeLine922"),
                "parentPx3MatchesLine922Payload": c_bridge.get("parentPx3MatchesLine922Payload"),
                "line933NoCookieHeader": c_bridge.get("line933NoCookieHeader"),
                "freshSeq5NoCookieHeader": c_bridge.get("freshSeq5NoCookieHeader"),
                "decodedPayloadAlreadyEqual": c_bridge.get("decodedPayloadAlreadyEqual"),
                "freshStillRejectedDespiteDecodedEquality": c_cookie.get("freshStillRejected"),
                "line922HasUnmappedFields": c_line922.get("hasUnmappedFields"),
                "line922HasUnresolvedChangedCandidates": c_line922.get("hasUnresolvedChangedCandidates"),
            },
            "whyNotReady": "Bridge/cookie context is correlated and not a Cookie header gap; it is not yet mapped to a specific server-visible request field or Microsoft risk context.",
            "nextArtifact": str(HYP / "browser_context_to_server_state_proxy_audit.json"),
            "nextScript": str(ROOT / "tools/build_browser_context_to_server_state_proxy_audit.py"),
            "readyForFreshExperiment": False,
        },
        {
            "id": "H5_microsoft_context_or_risk_binding",
            "status": "static_gap_due_missing_s00_risk_material",
            "evidence": str(HYP / "s00_risk_verify_material_gap.json"),
            "facts": {
                "s00RiskVerifyMaterialMissing": c_bridge.get("s00RiskVerifyMaterialMissing"),
                "riskGapChecks": c_risk,
            },
            "whyNotReady": "Current s00 run lacks sufficient risk/verify material linkage for a Microsoft-context experiment; must first map available context artifacts.",
            "readyForFreshExperiment": False,
        },
        {
            "id": "RouteB_applied_js_patch_axis",
            "status": "closed_active_instrumentation_not_passive_evidence",
            "evidence": str(ROOT / "output/protocol_reverse/reset_plan/reset_route_b_instrumentation_control_audit.json"),
            "facts": {
                "patchApply1SuccessCount": c_route_b.get("patchApply1SuccessCount"),
                "patchApply1FailureCount": c_route_b.get("patchApply1FailureCount"),
                "patchApplyCanBeTreatedAsPassiveObserver": c_route_b.get("patchApplyCanBeTreatedAsPassiveObserver"),
            },
            "readyForFreshExperiment": False,
        },
    ]

    checks_out = {
        "planExists": PLAN.exists(),
        "line922MapExists": bool(line922),
        "c5TerminalExists": bool(c5),
        "c5ClosedNoSuccess": c5_checks.get("encoderVariantFamilyClosedNoSuccess") is True,
        "serverInternalFinalGapExists": bool(final_gap),
        "serverInternalAllLocalProxySearchesNegative": c_final.get("allLocalProxySearchesNegative") is True,
        "bridgeAuditExists": bool(bridge),
        "bridgeNotCookieHeader": c_bridge.get("line933NoCookieHeader") is True and c_bridge.get("freshSeq5NoCookieHeader") is True,
        "decodedPayloadAlreadyEqual": c_bridge.get("decodedPayloadAlreadyEqual") is True,
        "hasHighestPriorityStaticLineageGap": True,
        "recommendedNextIsStatic": True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Re-rank decisive gaps after C5 encoder family is closed by the coherent live probe.",
        "inputs": {
            "line922DynamicFieldSourceMap": str(HYP / "line922_dynamic_field_source_map.json"),
            "encoderVariantTerminalAudit": str(HYP / "encoder_variant_terminal_audit.json"),
            "serverInternalFinalGap": str(HYP / "server_internal_unobserved_state_final_gap.json"),
            "bridgeToPayloadContextAudit": str(HYP / "bridge_to_payload_context_audit.json"),
            "cookieSessionLineageGapAudit": str(GOAL / "cookie_session_lineage_gap_audit.json"),
        },
        "checks": checks_out,
        "candidates": candidates,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(HYP / "browser_context_to_server_state_proxy_audit.json"),
            "nextScript": str(ROOT / "tools/build_browser_context_to_server_state_proxy_audit.py"),
            "reason": (
                "C5 encoded payload/pc/marker/uuid family is closed. C6 remains non-replayable server-internal expected state. "
                "The highest-priority actionable static gap is now H4/H5 context lineage: determine whether browser parent bridge, iframe messages, or Microsoft context have a server-visible proxy."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
