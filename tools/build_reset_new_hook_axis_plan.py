#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET_DIR = ROOT / "output/protocol_reverse/reset_plan"
COVERAGE = RESET_DIR / "reset_sampling_coverage_audit.json"
RUNNER_AUDIT = RESET_DIR / "reset_browser_sampling_runner_audit.json"
RECLASS = RESET_DIR / "reset_browser_sampling_reclassification_audit.json"
STATE = RESET_DIR / "reset_state_machine.json"
SINGLE = RESET_DIR / "reset_single_transition_candidates.json"
RUNNER = ROOT / "tools/run_reset_browser_webshare_sampling.py"
OUTLOOK_BROWSER = ROOT / "CTF-reg/outlook_browser_register.py"
PLAN_DOC = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"
OUT = RESET_DIR / "reset_new_hook_axis_plan.json"


HOOK_MARKERS = {
    "message_bridge": ["window.postMessage.call", "window.message.recv", "MessagePort.postMessage", "MessagePort.message"],
    "worker": ["Worker.new", "Worker.postMessage", "Worker.message", "hsprotect.captcha.worker.new"],
    "document_cookie": ["document.cookie.set"],
    "network": ["fetch.call", "XMLHttpRequest.open", "XMLHttpRequest.send", "sendBeacon"],
    "wasm": ["hsprotect.captcha.wasm.material", "hsprotect.captcha.wasm.nq.before", "hsprotect.captcha.wasm.nq.after"],
    "pow_worker": ["hsprotect.captcha.qs.start", "hsprotect.captcha.pow.hit"],
    "storage": ["localStorage", "sessionStorage", "indexedDB"],
    "crypto": ["crypto.snapshot", "crypto.getRandomValues", "crypto.subtle", "randomFillSync"],
    "performance": ["performance.now", "timeOrigin"],
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def abs_path(path: Path | str | None) -> str | None:
    if not path:
        return None
    return str(Path(path).resolve())


TEXT_CACHE: dict[str, str] = {}


def read_text(path: Path | str | None) -> str:
    if not path:
        return ""
    p = Path(str(path))
    if not p.is_absolute():
        p = ROOT / p
    if not p.is_file():
        return ""
    key = str(p.resolve())
    if key not in TEXT_CACHE:
        TEXT_CACHE[key] = p.read_text(encoding="utf-8", errors="replace").lower()
    return TEXT_CACHE[key]


def source_has(markers: list[str]) -> bool:
    text = read_text(OUTLOOK_BROWSER)
    return any(marker.lower() in text for marker in markers)


def file_has_any(path: str | None, markers: list[str]) -> bool:
    text = read_text(path)
    return bool(text) and any(marker.lower() in text for marker in markers)


def counted_attempts() -> list[dict[str, Any]]:
    runner = read_json(RUNNER_AUDIT)
    rows = []
    for row in runner.get("attempts") or []:
        if row.get("countsTowardResetMinimum") is not True:
            continue
        path = row.get("path")
        doc = read_json(Path(path)) if path else {}
        artifacts = doc.get("artifacts") or {}
        rows.append(
            {
                "path": path,
                "sampleClass": row.get("sampleClass"),
                "sessionId": row.get("sessionId"),
                "stage": row.get("stage"),
                "runtimeTrace": artifacts.get("runtimeTrace") or [],
                "jsInternalTrace": artifacts.get("jsInternalTrace") or [],
                "pxCookieBridge": artifacts.get("pxCookieBridge") or [],
                "envOverlay": doc.get("envOverlay") or {},
            }
        )
    return rows


def hook_coverage_for_attempt(attempt: dict[str, Any]) -> dict[str, Any]:
    runtime_paths = [str(p) for p in attempt.get("runtimeTrace") or []]
    js_paths = [str(p) for p in attempt.get("jsInternalTrace") or []]
    all_paths = runtime_paths + js_paths
    hooks: dict[str, Any] = {}
    for hook, markers in HOOK_MARKERS.items():
        hooks[hook] = {
            "sourceInstrumented": source_has(markers),
            "observedInRuntimeOrJsTrace": any(file_has_any(path, markers) for path in all_paths),
        }
    return hooks


def aggregate_hook_coverage(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = {}
    for hook, markers in HOOK_MARKERS.items():
        aggregate[hook] = {
            "sourceInstrumented": source_has(markers),
            "observedInCountedAttempts": sum(
                1
                for attempt in attempts
                if any(file_has_any(path, markers) for path in (attempt.get("runtimeTrace") or []) + (attempt.get("jsInternalTrace") or []))
            ),
            "observedInSuccessCounted": sum(
                1
                for attempt in attempts
                if attempt.get("sampleClass") == "browser_success_webshare"
                and any(file_has_any(path, markers) for path in (attempt.get("runtimeTrace") or []) + (attempt.get("jsInternalTrace") or []))
            ),
            "observedInFailureCounted": sum(
                1
                for attempt in attempts
                if attempt.get("sampleClass") == "browser_failure_webshare"
                and any(file_has_any(path, markers) for path in (attempt.get("runtimeTrace") or []) + (attempt.get("jsInternalTrace") or []))
            ),
        }
    return aggregate


def main() -> int:
    coverage = read_json(COVERAGE)
    state = read_json(STATE)
    single = read_json(SINGLE)
    attempts = counted_attempts()
    per_attempt = []
    for attempt in attempts:
        per_attempt.append({**attempt, "hookCoverage": hook_coverage_for_attempt(attempt)})
    aggregate = aggregate_hook_coverage(attempts)

    counted_js_trace_count = sum(1 for attempt in attempts if attempt.get("jsInternalTrace"))
    counted_runtime_trace_count = sum(1 for attempt in attempts if attempt.get("runtimeTrace"))
    js_trace_success_count = sum(
        1 for attempt in attempts
        if attempt.get("sampleClass") == "browser_success_webshare" and attempt.get("jsInternalTrace")
    )
    js_trace_failure_count = sum(
        1 for attempt in attempts
        if attempt.get("sampleClass") == "browser_failure_webshare" and attempt.get("jsInternalTrace")
    )
    missing_observed_hooks = [
        hook
        for hook, row in aggregate.items()
        if row["sourceInstrumented"] is True and row["observedInCountedAttempts"] == 0
    ]
    missing_contrast_hooks = [
        hook
        for hook in ["message_bridge", "storage", "crypto", "performance"]
        if aggregate.get(hook, {}).get("sourceInstrumented") is True
        and (
            aggregate.get(hook, {}).get("observedInSuccessCounted", 0) == 0
            or aggregate.get(hook, {}).get("observedInFailureCounted", 0) == 0
        )
    ]
    not_instrumented_hooks = [
        hook
        for hook, row in aggregate.items()
        if row["sourceInstrumented"] is False
    ]

    recommended_axes = []
    if js_trace_success_count < 1 or js_trace_failure_count < 1:
        recommended_axes.append(
            {
                "axis": "reset_browser_js_internal_trace",
                "reason": "Need at least one counted browser success and one counted browser failure with jsInternalTrace artifacts; Phase 3 requires worker/iframe/parent bridge/crypto/performance hook evidence.",
                "runnerChange": "OUTLOOK_JS_INTERNAL_TRACE=1",
                "sampleClasses": ["browser_success_webshare", "browser_failure_webshare"],
                "minimumPerClass": 1,
            }
        )
    if "storage" in missing_observed_hooks or "storage" in missing_contrast_hooks or "storage" in not_instrumented_hooks:
        recommended_axes.append(
            {
                "axis": "storage_api_hook",
                "reason": "Reset plan NH3 names storage as possible missed transition; current counted samples do not prove storage hook observation.",
                "targetApis": ["localStorage", "sessionStorage", "indexedDB"],
            }
        )
    if "crypto" in missing_observed_hooks or "crypto" in missing_contrast_hooks or "crypto" in not_instrumented_hooks:
        recommended_axes.append(
            {
                "axis": "crypto_random_hook",
                "reason": "Reset plan NH3 names crypto input as possible missed transition; current counted samples do not prove browser-level crypto hook installation or calls.",
                "targetApis": ["crypto.getRandomValues", "crypto.subtle"],
            }
        )
    if "performance" in missing_observed_hooks or "performance" in missing_contrast_hooks or "performance" in not_instrumented_hooks:
        recommended_axes.append(
            {
                "axis": "performance_time_origin_hook",
                "reason": "Reset plan NH3 names performance/time origin as possible missed transition; current counted samples only use perf_t in emitted events, not a value-flow hook.",
                "targetApis": ["performance.now", "performance.timeOrigin", "Date.now"],
            }
        )

    checks = {
        "coverageComplete": ((coverage.get("checks") or {}).get("allResetCoverageComplete") is True),
        "stateHasClientVisibleProxy": ((state.get("checks") or {}).get("clientVisibleProxyCount") or 0) > 0,
        "singleTransitionCandidateCount": (single.get("checks") or {}).get("singleTransitionCandidateCount"),
        "countedAttemptCount": len(attempts),
        "countedRuntimeTraceCount": counted_runtime_trace_count,
        "countedJsInternalTraceCount": counted_js_trace_count,
        "countedSuccessWithJsInternalTraceCount": js_trace_success_count,
        "countedFailureWithJsInternalTraceCount": js_trace_failure_count,
        "allCountedAttemptsHaveRuntimeTrace": counted_runtime_trace_count == len(attempts) and len(attempts) > 0,
        "hasCountedSuccessAndFailureJsInternalTrace": js_trace_success_count >= 1 and js_trace_failure_count >= 1,
        "missingObservedHookCount": len(missing_observed_hooks),
        "missingContrastHookCount": len(missing_contrast_hooks),
        "notInstrumentedHookCount": len(not_instrumented_hooks),
        "recommendedAxisCount": len(recommended_axes),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Plan the next new_hook_or_sampling_axis step after reset sampling coverage completed but no client-visible transition candidate was found.",
        "plan": abs_path(PLAN_DOC),
        "inputs": [abs_path(COVERAGE), abs_path(RUNNER_AUDIT), abs_path(RECLASS), abs_path(STATE), abs_path(SINGLE), abs_path(OUTLOOK_BROWSER), abs_path(RUNNER)],
        "countedAttempts": per_attempt,
        "aggregateHookCoverage": aggregate,
        "missingObservedHooks": missing_observed_hooks,
        "missingContrastHooks": missing_contrast_hooks,
        "notInstrumentedHooks": not_instrumented_hooks,
        "recommendedAxes": recommended_axes,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": {
                "kind": "new_hook_or_sampling_axis_execution",
                "axes": [axis["axis"] for axis in recommended_axes],
                "reason": "Current reset coverage is complete, but counted browser reset samples lack enough hook evidence to test NH3 before declaring server-internal boundary.",
            }
            if recommended_axes
            else None,
            "nextArtifact": str(OUT.resolve()),
            "nextScript": str(RUNNER.resolve()) if recommended_axes else None,
            "reason": (
                "Enable and collect the recommended hook/sampling axes before Phase 5; current evidence has no single transition candidate."
                if recommended_axes
                else "No additional hook axis was identified from current local evidence; do not run Phase 5 without a single transition candidate."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
