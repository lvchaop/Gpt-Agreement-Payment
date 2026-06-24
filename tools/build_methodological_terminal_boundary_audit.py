#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
GOAL_DIR = ROOT / "output/protocol_reverse/goal_audit"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
OUT = RESET / "methodological_terminal_boundary_audit.json"

INPUTS = {
    "collectorHandlerSurfaceAudit": RESET / "reset_collector_handler_surface_audit.json",
    "unobservedLifecycleSurfaceAudit": RESET / "reset_unobserved_lifecycle_surface_audit.json",
    "routeBResamplingManifest": RESET / "reset_route_b_resampling_manifest.json",
    "routeBResamplingMatrix": RESET / "reset_route_b_resampling_matrix.json",
    "routeBLifecycleContrastAudit": RESET / "reset_route_b_lifecycle_contrast_audit.json",
    "routeBValueTaxonomyAudit": RESET / "reset_route_b_value_taxonomy_audit.json",
    "routeBInstrumentationControlAudit": RESET / "reset_route_b_instrumentation_control_audit.json",
    "transportIpDecisionAudit": RESET / "reset_transport_ip_decision_audit.json",
    "resetTerminalBoundaryAudit": RESET / "reset_terminal_boundary_audit.json",
    "goalGapAudit": GOAL_DIR / "pure_protocol_goal_gap_audit.json",
}


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
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    c_handler = checks(docs["collectorHandlerSurfaceAudit"])
    c_lifecycle = checks(docs["unobservedLifecycleSurfaceAudit"])
    c_route_b_manifest = checks(docs["routeBResamplingManifest"])
    c_route_b_matrix = checks(docs["routeBResamplingMatrix"])
    c_route_b_contrast = checks(docs["routeBLifecycleContrastAudit"])
    c_route_b_value = checks(docs["routeBValueTaxonomyAudit"])
    c_route_b_instr = checks(docs["routeBInstrumentationControlAudit"])
    c_transport = checks(docs["transportIpDecisionAudit"])
    c_terminal = checks(docs["resetTerminalBoundaryAudit"])
    goal_summary = (docs["goalGapAudit"].get("summary") or {})

    route_checks = {
        "routeACollectorHandlerClosed": c_handler.get("handlerCandidateCount") == 152
        and c_handler.get("unclassifiedHandlerSurfaceCount") == 0
        and c_handler.get("promotedSingleTransitionCandidateCount") == 0,
        "routeBUnobservedLifecycleClosed": c_lifecycle.get("implementedRouteBRecommendedHookCount") == 3
        and c_lifecycle.get("recommendedNewHookCount") == 0
        and c_route_b_manifest.get("readyForRouteBControlledBrowserResampling") is True
        and c_route_b_contrast.get("successOnlyHookKindCount") == 0
        and c_route_b_contrast.get("promotedSingleTransitionCandidateCount") == 0
        and c_route_b_value.get("promotedSingleTransitionCandidateCount") == 0
        and c_route_b_instr.get("valueContrastControlled") is False
        and c_route_b_instr.get("patchApplyCanBeTreatedAsPassiveObserver") is False,
        "routeCTransportIpClosed": c_transport.get("validWebshareSampleCount") == 3
        and c_transport.get("validDirectSampleCount") == 2
        and c_transport.get("allValidSamplesReachedFinalSeq5Seq6") is True
        and c_transport.get("onlyTransportChangedStageDifferenceProved") is False
        and c_transport.get("ipOrTransportPromotedToControlVariableOnly") is True,
    }

    terminal_checks = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        **route_checks,
        "allRoutesClosed": all(route_checks.values()),
        "resetTerminalNoCurrentRouteToPhase5": c_terminal.get("noCurrentRouteToPhase5") is True,
        "resetTerminalReadyForFreshExperiment": c_terminal.get("readyForFreshExperiment") is True,
        "resetTerminalGoalComplete": c_terminal.get("goalComplete") is True,
        "goalAuditEndToEndPocMissing": "end_to_end_pure_protocol_poc" in (goal_summary.get("blockingOrMissing") or []),
        "goalAuditGoalComplete": goal_summary.get("goalComplete") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Route D terminal boundary: consolidate methodological Route A/B/C evidence and prevent Phase 5 without a new single transition.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": terminal_checks,
        "routeSummaries": {
            "routeA": {
                "artifact": str(INPUTS["collectorHandlerSurfaceAudit"]),
                "handlerCandidateCount": c_handler.get("handlerCandidateCount"),
                "promotedSingleTransitionCandidateCount": c_handler.get("promotedSingleTransitionCandidateCount"),
                "status": "closed_no_promoted_transition" if route_checks["routeACollectorHandlerClosed"] else "not_closed",
            },
            "routeB": {
                "artifacts": [
                    str(INPUTS["unobservedLifecycleSurfaceAudit"]),
                    str(INPUTS["routeBResamplingManifest"]),
                    str(INPUTS["routeBResamplingMatrix"]),
                    str(INPUTS["routeBLifecycleContrastAudit"]),
                    str(INPUTS["routeBValueTaxonomyAudit"]),
                    str(INPUTS["routeBInstrumentationControlAudit"]),
                ],
                "implementedHookCount": c_lifecycle.get("implementedRouteBRecommendedHookCount"),
                "realAttemptCount": c_route_b_contrast.get("realAttemptCount"),
                "successOnlyHookKindCount": c_route_b_contrast.get("successOnlyHookKindCount"),
                "valueContrastControlled": c_route_b_instr.get("valueContrastControlled"),
                "patchApply1SuccessCount": c_route_b_instr.get("patchApply1SuccessCount"),
                "patchApply1FailureCount": c_route_b_instr.get("patchApply1FailureCount"),
                "promotedSingleTransitionCandidateCount": c_route_b_contrast.get("promotedSingleTransitionCandidateCount"),
                "status": "closed_no_promoted_transition" if route_checks["routeBUnobservedLifecycleClosed"] else "not_closed",
            },
            "routeC": {
                "artifact": str(INPUTS["transportIpDecisionAudit"]),
                "validWebshareSampleCount": c_transport.get("validWebshareSampleCount"),
                "validDirectSampleCount": c_transport.get("validDirectSampleCount"),
                "onlyTransportChangedStageDifferenceProved": c_transport.get("onlyTransportChangedStageDifferenceProved"),
                "status": "closed_transport_control_variable_only" if route_checks["routeCTransportIpClosed"] else "not_closed",
            },
        },
        "remainingGap": {
            "id": "end_to_end_pure_protocol_poc",
            "status": "missing",
            "whyNotReady": (
                "Routes A/B/C do not produce a single client-visible, pre-accept, pure-protocol constructible transition. "
                "Current reset terminal audit remains noCurrentRouteToPhase5=true and readyForFreshExperiment=false."
            ),
            "minimumEvidenceToReopen": [
                "A new artifact proving one pre-accept client-visible transition with value lineage into request/cookie/risk.",
                "The transition must be constructible without browser/Camoufox/mouse/vision/external captcha.",
                "A negative-control audit must show existing final seq5 oIIoIooo|-1 failures do not already falsify it.",
                "Only then may a fresh session Phase 5 experiment be run.",
            ],
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Methodological routes A/B/C are closed with no promoted transition. "
                "Do not run Phase 5 or repeat network attempts until a new evidence entrance proves a single constructible pre-accept transition."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "remainingGap": doc["remainingGap"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
