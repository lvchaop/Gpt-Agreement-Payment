#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
RESET = ROOT / "output/protocol_reverse/reset_plan"
PROTO = ROOT / "output/protocol_reverse"
OUT = HYP / "browser_context_static_gap_inventory.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def line922_rows_by_key(field_map: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in field_map.get("fieldRows") or []:
        out.setdefault(str(row.get("key")), []).append(row)
    return out


def reduce_static_px561_fields(static_map: dict[str, Any], field_map: dict[str, Any]) -> list[dict[str, Any]]:
    rows_by_key = line922_rows_by_key(field_map)
    reduced = []
    for rec in static_map.get("records") or []:
        key = rec.get("key")
        producer = rec.get("ycProducer") or {}
        line_rows = rows_by_key.get(str(key), [])
        in_line922 = bool(line_rows)
        fresh_equal = bool(line_rows) and all(row.get("freshSeq5EqualS00") is True for row in line_rows if row.get("freshSeq5Present") is True)
        fresh_changed = any(row.get("freshSeq5Present") is True and row.get("freshSeq5EqualS00") is not True for row in line_rows)
        status = rec.get("status")
        promoted = False
        reason = "not_a_static_producer"
        if status == "static_producer_identified" and in_line922 and fresh_equal:
            reason = "producer_maps_to_line922_but_fresh_seq5_already_equal"
        elif status == "static_producer_identified" and in_line922 and fresh_changed:
            reason = "producer_maps_to_changed_line922_field"
            promoted = True
        elif status == "static_producer_identified" and not in_line922:
            reason = "producer_identified_but_not_found_in_line922_payload"
        reduced.append(
            {
                "key": key,
                "status": status,
                "producerMeaning": producer.get("meaning"),
                "producerExpression": producer.get("expression"),
                "inLine922Payload": in_line922,
                "line922FreshEqualS00": fresh_equal,
                "line922FreshChanged": fresh_changed,
                "line922Rows": [
                    {
                        "activityIndex": row.get("activityIndex"),
                        "activityType": row.get("activityType"),
                        "valuePreview": row.get("valuePreview"),
                        "class": row.get("class"),
                        "freshSeq5Present": row.get("freshSeq5Present"),
                        "freshSeq5EqualS00": row.get("freshSeq5EqualS00"),
                    }
                    for row in line_rows[:4]
                ],
                "promoted": promoted,
                "reason": reason,
            }
        )
    return reduced


def reduce_lifecycle_surfaces(lifecycle: dict[str, Any]) -> list[dict[str, Any]]:
    reduced = []
    for surface in lifecycle.get("surfaces") or []:
        coverage = surface.get("coverage")
        sid = surface.get("id")
        promoted = False
        if surface.get("runtimeObserved") is True:
            reason = "runtime_observed_and_already_in_route_b_reduction"
        elif surface.get("hookDeclared") is True and surface.get("staticReachable") is True:
            reason = "static_reachable_hooked_not_observed_in_counted_browser_traces"
        elif sid == "animation_frame_scheduler":
            reason = "static_reachable_but_no_request_cookie_risk_entry_hypothesis"
        else:
            reason = "not_static_reachable_or_not_relevant"
        reduced.append(
            {
                "id": sid,
                "coverage": coverage,
                "staticReachable": surface.get("staticReachable"),
                "hookDeclared": surface.get("hookDeclared"),
                "runtimeObserved": surface.get("runtimeObserved"),
                "preAcceptCandidate": surface.get("preAcceptCandidate"),
                "entersRequestCookieRiskHypothesis": surface.get("entersRequestCookieRiskHypothesis"),
                "recommendNewHook": surface.get("recommendNewHook"),
                "promoted": promoted,
                "reason": reason,
                "staticHitCount": len(surface.get("staticHits") or []),
                "runtimeHits": surface.get("runtimeHits") or [],
            }
        )
    return reduced


def build() -> dict[str, Any]:
    context_proxy = read_json(HYP / "browser_context_to_server_state_proxy_audit.json")
    lifecycle = read_json(RESET / "reset_unobserved_lifecycle_surface_audit.json")
    line922 = read_json(HYP / "line922_dynamic_field_source_map.json")
    px561_static = read_json(PROTO / "px561_static_field_map/px561_static_field_map_success_only.json")
    c5 = read_json(HYP / "encoder_variant_terminal_audit.json")
    terminal = read_json(RESET / "reset_terminal_boundary_audit.json")

    static_field_reduction = reduce_static_px561_fields(px561_static, line922)
    lifecycle_reduction = reduce_lifecycle_surfaces(lifecycle)
    promoted_static_fields = [row for row in static_field_reduction if row.get("promoted") is True]
    promoted_lifecycle = [row for row in lifecycle_reduction if row.get("promoted") is True]
    hooked_unobserved = [
        row for row in lifecycle_reduction
        if row.get("coverage") == "hooked_not_observed"
    ]
    static_producer_equal = [
        row for row in static_field_reduction
        if row.get("reason") == "producer_maps_to_line922_but_fresh_seq5_already_equal"
    ]

    c_context = checks(context_proxy)
    c_lifecycle = checks(lifecycle)
    c_line922 = line922.get("summary") or {}
    c_c5 = checks(c5)
    c_terminal = checks(terminal)

    promoted = promoted_static_fields + promoted_lifecycle
    out_checks = {
        "planExists": PLAN.exists(),
        "contextProxyAuditExists": bool(context_proxy),
        "contextProxyAllServerVisibleProxiesReduced": c_context.get("allBrowserContextServerVisibleProxiesReduced") is True,
        "lifecycleAuditExists": bool(lifecycle),
        "lifecycleRecommendedNewHookCount": c_lifecycle.get("recommendedNewHookCount"),
        "lifecycleStaticReachableButRuntimeUnobservedCount": c_lifecycle.get("staticReachableButRuntimeUnobservedCount"),
        "hookedButUnobservedSurfaceCount": len(hooked_unobserved),
        "line922MapExists": bool(line922),
        "line922FreshChangedFieldInstances": c_line922.get("freshSeq5ChangedFieldInstances"),
        "line922UnresolvedChangedCandidateCount": c_line922.get("unresolvedChangedCandidateCount"),
        "px561StaticMapExists": bool(px561_static),
        "staticProducerIdentifiedCount": sum(1 for row in static_field_reduction if row.get("status") == "static_producer_identified"),
        "staticProducerLine922FreshEqualCount": len(static_producer_equal),
        "staticProducerPromotedCount": len(promoted_static_fields),
        "encoderVariantFamilyClosedNoSuccess": c_c5.get("encoderVariantFamilyClosedNoSuccess") is True,
        "terminalNoCurrentRouteToPhase5": c_terminal.get("noCurrentRouteToPhase5") is True,
        "promotedSingleTransitionCandidateCount": len(promoted),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    out_checks["allStaticContextGapsReduced"] = (
        out_checks["contextProxyAllServerVisibleProxiesReduced"] is True
        and out_checks["lifecycleRecommendedNewHookCount"] == 0
        and out_checks["line922FreshChangedFieldInstances"] == 0
        and out_checks["line922UnresolvedChangedCandidateCount"] == 0
        and out_checks["staticProducerPromotedCount"] == 0
        and out_checks["promotedSingleTransitionCandidateCount"] == 0
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Inventory browser-context static surfaces that are not already represented by request/payload/cookie evidence, and decide whether any can be promoted to a single pure-protocol transition.",
        "inputs": {
            "browserContextToServerStateProxyAudit": str(HYP / "browser_context_to_server_state_proxy_audit.json"),
            "resetUnobservedLifecycleSurfaceAudit": str(RESET / "reset_unobserved_lifecycle_surface_audit.json"),
            "line922DynamicFieldSourceMap": str(HYP / "line922_dynamic_field_source_map.json"),
            "px561StaticFieldMapSuccessOnly": str(PROTO / "px561_static_field_map/px561_static_field_map_success_only.json"),
            "encoderVariantTerminalAudit": str(HYP / "encoder_variant_terminal_audit.json"),
            "resetTerminalBoundaryAudit": str(RESET / "reset_terminal_boundary_audit.json"),
        },
        "checks": out_checks,
        "staticPx561FieldReduction": static_field_reduction,
        "lifecycleSurfaceReduction": lifecycle_reduction,
        "candidateAssessment": {
            "promoted": promoted,
            "hookedButUnobservedSurfaces": hooked_unobserved,
            "staticProducerFieldsAlreadyEqual": static_producer_equal,
            "notPromotedReasons": [
                "Pre-accept postMessage/block/cookie bridge values are already reduced by browser_context_to_server_state_proxy_audit.",
                "Route B lifecycle audit has no new hook recommendation; hooked-but-unobserved surfaces are not active in counted success/failure traces.",
                "Identified PX561 static producers map to line922 fields whose fresh seq5 values are already equal to s00, so they are not a new transition.",
                "C5 encoder family is closed with no collector success, so equal decoded payload fields do not authorize another network run.",
            ],
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(HYP / "post_static_context_terminal_gap_audit.json"),
            "nextScript": str(ROOT / "tools/build_post_static_context_terminal_gap_audit.py"),
            "reason": (
                "Static browser-context inventory does not promote a single transition: context messages are already represented/reduced, "
                "Route B has no new hook, and identified PX561 context/static producers are already equal in fresh seq5 line922. "
                "The remaining gap is still non-replayable server-internal or unobserved expected state."
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
