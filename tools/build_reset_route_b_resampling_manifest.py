#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
LIFECYCLE = RESET / "reset_unobserved_lifecycle_surface_audit.json"
TERMINAL = RESET / "reset_terminal_boundary_audit.json"
OUT = RESET / "reset_route_b_resampling_manifest.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def route_b_sample_class(class_id: str, minimum_count: int, success_like: bool) -> dict[str, Any]:
    return {
        "classId": class_id,
        "minimumCount": minimum_count,
        "transport": "webshare",
        "usesBrowserForEvidenceOnly": True,
        "countsTowardFinalPureProtocolSuccess": False,
        "purpose": "Capture Route B newly instrumented lifecycle/fingerprint hooks under browser Webshare control.",
        "successLikeExpected": success_like,
        "perAttemptRules": {
            "freshSessionRequired": True,
            "newSessionIdForEveryAttempt": True,
            "recordWebshareSessionAndExitIp": True,
            "OUTLOOK_JS_INTERNAL_TRACE": "1",
            "OUTLOOK_HSPROTECT_JS_PATCH": "1",
            "OUTLOOK_HSPROTECT_JS_PATCH_APPLY": "1",
            "sameInstrumentationPatchApplyForSuccessAndFailure": True,
            "noProtocolFieldMutation": True,
            "browserSamplesAreEvidenceOnly": True,
        },
        "requiredHookKinds": [
            "webkit.messageHandlers.pxMobileData.wrap",
            "webkit.messageHandlers.pxMobileData.postMessage",
            "OfflineAudioContext.wrap",
            "OfflineAudioContext.new",
            "OfflineAudioContext.startRendering",
            "OfflineAudioContext.startRendering.resolved",
            "serviceWorker.snapshot",
            "serviceWorker.register",
            "caches.wrap",
            "caches.open",
            "caches.match",
        ],
        "requiredArtifacts": [
            "attempt_summary_json",
            "runtime_trace_jsonl",
            "js_internal_trace_jsonl",
            "network_trace_or_har",
            "collector_decoded_response_json",
            "cookie_timeline_json",
            "proxy_or_direct_ip_evidence_json",
        ],
        "classificationFields": [
            "sessionId",
            "successLike",
            "finalStage",
            "hookKindsObserved",
            "routeBHookKindsObserved",
            "routeBHookKindsMissing",
            "collectorFinalResponseClass",
            "riskVerifyState",
            "createAccountRedirectUrl",
        ],
    }


def build() -> dict[str, Any]:
    lifecycle = read_json(LIFECYCLE)
    terminal = read_json(TERMINAL)
    c_lifecycle = lifecycle.get("checks") or {}
    c_terminal = terminal.get("checks") or {}

    sample_classes = [
        route_b_sample_class("route_b_browser_success_webshare", 1, True),
        route_b_sample_class("route_b_browser_failure_webshare", 1, False),
    ]

    checks = {
        "planExists": PLAN.exists(),
        "lifecycleAuditExists": LIFECYCLE.exists(),
        "terminalAuditExists": TERMINAL.exists(),
        "routeBImplementedHookCount": c_lifecycle.get("implementedRouteBRecommendedHookCount"),
        "routeBRecommendedNewHookCount": c_lifecycle.get("recommendedNewHookCount"),
        "routeBReadyForResampling": c_lifecycle.get("readyForResampling") is True,
        "terminalReadyForFreshExperiment": c_terminal.get("readyForFreshExperiment") is True,
        "terminalNoCurrentRouteToPhase5": c_terminal.get("noCurrentRouteToPhase5") is True,
        "sampleClassCount": len(sample_classes),
        "manifestComplete": len(sample_classes) == 2
        and c_lifecycle.get("implementedRouteBRecommendedHookCount") == 3
        and c_lifecycle.get("recommendedNewHookCount") == 0,
        "readyForRouteBControlledBrowserResampling": False,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    checks["readyForRouteBControlledBrowserResampling"] = (
        checks["manifestComplete"] is True
        and checks["routeBReadyForResampling"] is True
        and checks["terminalReadyForFreshExperiment"] is False
        and checks["terminalNoCurrentRouteToPhase5"] is True
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Dedicated Route B manifest for browser-only controlled resampling after adding lifecycle/fingerprint hooks.",
        "inputs": {
            "lifecycleAudit": str(LIFECYCLE),
            "terminalBoundaryAudit": str(TERMINAL),
        },
        "checks": checks,
        "sampleClasses": sample_classes,
        "globalRules": {
            "doNotRunPureProtocolPhase5": True,
            "doNotInferIpCause": True,
            "everyAttemptUsesNewSession": True,
            "webshareAttemptsMustRecordSessionAndExitIp": True,
            "browserSamplesAreEvidenceOnly": True,
            "newHooksOnlyEstablishObservability": True,
        },
        "plannedOutputs": {
            "routeBResamplingMatrix": str(RESET / "reset_route_b_resampling_matrix.json"),
            "routeBLifecycleContrastAudit": str(RESET / "reset_route_b_lifecycle_contrast_audit.json"),
            "updatedHookAxisPlan": str(RESET / "reset_new_hook_axis_plan.json"),
            "updatedTerminalBoundaryAudit": str(TERMINAL),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForRouteBControlledBrowserResampling": checks["readyForRouteBControlledBrowserResampling"],
            "recommendedExperiment": None,
            "nextArtifact": str(RESET / "reset_route_b_resampling_matrix.json")
            if checks["readyForRouteBControlledBrowserResampling"]
            else None,
            "nextScript": str(ROOT / "tools/run_reset_route_b_browser_resampling.py")
            if checks["readyForRouteBControlledBrowserResampling"]
            else None,
            "reason": (
                "Route B hooks are implemented and may be sampled in browser evidence mode. "
                "This does not authorize pure-protocol Phase 5; it only collects lifecycle/fingerprint contrast evidence."
            )
            if checks["readyForRouteBControlledBrowserResampling"]
            else "Route B resampling is not ready; inspect checks.",
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
