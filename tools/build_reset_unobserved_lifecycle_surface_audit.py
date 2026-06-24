#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
RESET = ROOT / "output/protocol_reverse/reset_plan"
OUTLOOK = ROOT / "output/outlook_browser"
STATIC = OUTLOOK / "js_static_analysis"
HOOK_SOURCE = ROOT / "CTF-reg/outlook_browser_register.py"
MATRIX = RESET / "reset_sampling_matrix.json"
HOOK_AXIS = RESET / "reset_new_hook_axis_plan.json"
TERMINAL = RESET / "reset_terminal_boundary_audit.json"
OUT = RESET / "reset_unobserved_lifecycle_surface_audit.json"

STATIC_FILES = [
    STATIC / "har_main.beautified.js",
    STATIC / "captcha.beautified.js",
    STATIC / "summary.md",
    STATIC / "har_captcha.ast_facts.json",
]

SURFACES: list[dict[str, Any]] = [
    {
        "id": "message_channel_iframe_sync",
        "staticPatterns": ["new MessageChannel", "contentWindow.postMessage"],
        "hookPatterns": ["MessageChannel.new", "MessagePort.postMessage", "window.postMessage.call"],
        "runtimeKinds": ["MessageChannel.new", "MessagePort.postMessage", "window.postMessage.call", "window.message.recv"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "native_mobile_bridge_pxMobileData",
        "staticPatterns": ["webkit.messageHandlers.pxMobileData.postMessage", "pxMobileData"],
        "hookPatterns": ["webkit.messageHandlers.pxMobileData.postMessage", "webkit.messageHandlers.pxMobileData.wrap"],
        "runtimeKinds": ["webkit.messageHandlers.pxMobileData.postMessage", "pxMobileData"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "offline_audio_fingerprint",
        "staticPatterns": ["OfflineAudioContext", "webkitOfflineAudioContext", "startRendering"],
        "hookPatterns": ["OfflineAudioContext.new", "OfflineAudioContext.startRendering", "OfflineAudioContext.startRendering.resolved"],
        "runtimeKinds": ["OfflineAudioContext.new", "OfflineAudioContext.startRendering", "audio.fingerprint"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "animation_frame_scheduler",
        "staticPatterns": ["requestAnimationFrame"],
        "hookPatterns": [],
        "runtimeKinds": ["requestAnimationFrame.call", "requestAnimationFrame.fire"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": False,
        "recommendHookIfUncovered": False,
    },
    {
        "id": "visibility_storage_online_events",
        "staticPatterns": ["visibilitychange", "online", "offline", "storage:"],
        "hookPatterns": ["addEventListener", "dispatchEvent"],
        "runtimeKinds": ["addEventListener", "dispatchEvent"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "service_worker_cache_fingerprint",
        "staticPatterns": ["serviceWorker", "caches"],
        "hookPatterns": ["serviceWorker.register", "serviceWorker.snapshot", "caches."],
        "runtimeKinds": ["serviceWorker.register", "serviceWorker.controller", "caches.open", "caches.match"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "network_transport_xhr_fetch_beacon",
        "staticPatterns": ["XMLHttpRequest", "fetch(", "sendBeacon"],
        "hookPatterns": ["xhr.open", "xhr.send", "fetch.call", "sendBeacon.call", "hsprotect.sendBeacon.internal"],
        "runtimeKinds": ["xhr.open", "xhr.send", "xhr.loadend", "fetch.call", "fetch.response", "sendBeacon.call", "hsprotect.sendBeacon.internal"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "worker_blob_pow",
        "staticPatterns": ["new Worker", "new Blob", "postMessage(z)", "function qs"],
        "hookPatterns": ["Worker.new", "Blob.created", "hsprotect.captcha.worker.new", "hsprotect.captcha.qs.start"],
        "runtimeKinds": ["Worker.new", "Blob.created", "Worker.message", "hsprotect.captcha.worker.new", "hsprotect.captcha.qs.start"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "wasm_crypto_random",
        "staticPatterns": ["WebAssembly", "getRandomValues", "crypto.subtle"],
        "hookPatterns": ["crypto.getRandomValues", "crypto.subtle.", "hsprotect.captcha.wasm."],
        "runtimeKinds": ["crypto.getRandomValues", "crypto.subtle.digest", "hsprotect.captcha.wasm.import.call", "hsprotect.captcha.wasm.nq.before"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "cookie_storage_indexeddb",
        "staticPatterns": ["document.cookie", "localStorage", "sessionStorage", "indexedDB"],
        "hookPatterns": ["document.cookie.set", "localStorage.", "sessionStorage.", "indexedDB."],
        "runtimeKinds": ["document.cookie.set", "localStorage.setItem", "sessionStorage.setItem", "indexedDB.open"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
    {
        "id": "performance_resource_timing",
        "staticPatterns": ["performance.getEntries", "performance.memory", "performance.timing"],
        "hookPatterns": ["performance.snapshot", "performance.now.call"],
        "runtimeKinds": ["performance.snapshot", "performance.now.call"],
        "preAcceptCandidate": True,
        "entersRequestCookieRiskHypothesis": True,
        "recommendHookIfUncovered": True,
    },
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def static_hits(patterns: list[str]) -> list[dict[str, Any]]:
    hits = []
    for path in STATIC_FILES:
        text = read_text(path)
        if not text:
            continue
        for pat in patterns:
            idx = text.find(pat)
            if idx >= 0:
                line = text.count("\n", 0, idx) + 1
                start = max(0, idx - 160)
                end = min(len(text), idx + len(pat) + 220)
                hits.append({"pattern": pat, "path": str(path), "line": line, "preview": text[start:end].replace("\n", "\\n")[:600]})
    return hits


def hook_hits(patterns: list[str]) -> list[dict[str, Any]]:
    text = read_text(HOOK_SOURCE)
    hits = []
    for pat in patterns:
        idx = text.find(pat)
        if idx >= 0:
            hits.append({"pattern": pat, "path": str(HOOK_SOURCE), "line": text.count("\n", 0, idx) + 1})
    return hits


def counted_js_trace_paths(matrix: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for row in matrix.get("executedRows") or []:
        if row.get("countsTowardResetMinimum") is not True:
            continue
        sample_class = str(row.get("sampleClass") or "")
        if not sample_class.startswith("browser_"):
            continue
        evidence = row.get("evidence") or {}
        for p in evidence.get("jsInternalTrace") or []:
            path = Path(p)
            if path.exists():
                paths.append(path)
    return paths


def runtime_kind_counts(paths: list[Path]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = item.get("kind")
                if kind:
                    counts[str(kind)] += 1
    return counts


def runtime_hits(kinds: list[str], counts: Counter[str]) -> list[dict[str, Any]]:
    hits = []
    for wanted in kinds:
        total = sum(count for kind, count in counts.items() if kind == wanted or kind.startswith(wanted))
        if total:
            hits.append({"kind": wanted, "count": total})
    return hits


def static_probe_lineage(surface_id: str, static: list[dict[str, Any]]) -> str:
    if surface_id == "native_mobile_bridge_pxMobileData":
        return "Static JS shows pxMobileData behind webkit.messageHandlers guard; current traces do not show calls, so this is an unobserved native-bridge surface, not a proved active transition."
    if surface_id == "offline_audio_fingerprint":
        return "Static JS constructs OfflineAudioContext and hashes rendering output; this is fingerprint material that can enter collector activities, but current hooks do not record the values."
    if surface_id == "service_worker_cache_fingerprint":
        return "Static JS token table references serviceWorker/caches; current evidence does not prove active use, so this is a low-confidence unobserved fingerprint surface."
    if surface_id == "visibility_storage_online_events":
        return "Static JS defines visibility/storage/online/offline event collectors; current addEventListener hook only records a limited event-type allowlist."
    if surface_id == "performance_resource_timing":
        return "Static JS reads performance resource/timing/memory fields; current hook records now/timeOrigin but not getEntries/getEntriesByName/resource entries."
    return "Static/runtime coverage is summarized by pattern hits."


def build() -> dict[str, Any]:
    matrix = read_json(MATRIX)
    hook_axis = read_json(HOOK_AXIS)
    terminal = read_json(TERMINAL)
    js_paths = counted_js_trace_paths(matrix)
    kind_counts = runtime_kind_counts(js_paths)

    surfaces = []
    recommended = []
    uncovered_static_reachable = []
    for spec in SURFACES:
        s_hits = static_hits(spec["staticPatterns"])
        h_hits = hook_hits(spec["hookPatterns"])
        r_hits = runtime_hits(spec["runtimeKinds"], kind_counts)
        static_reachable = bool(s_hits)
        hook_declared = bool(h_hits)
        runtime_observed = bool(r_hits)
        uncovered = static_reachable and not hook_declared
        limited_hook = static_reachable and hook_declared and not runtime_observed and spec["id"] in {"visibility_storage_online_events", "performance_resource_timing"}
        recommend = bool(
            spec["recommendHookIfUncovered"]
            and spec["preAcceptCandidate"]
            and spec["entersRequestCookieRiskHypothesis"]
            and (uncovered or limited_hook)
        )
        row = {
            "id": spec["id"],
            "staticReachable": static_reachable,
            "hookDeclared": hook_declared,
            "runtimeObserved": runtime_observed,
            "preAcceptCandidate": spec["preAcceptCandidate"],
            "entersRequestCookieRiskHypothesis": spec["entersRequestCookieRiskHypothesis"],
            "staticHits": s_hits[:8],
            "hookHits": h_hits[:8],
            "runtimeHits": r_hits,
            "coverage": "observed" if runtime_observed else ("hooked_not_observed" if hook_declared else ("static_unhooked" if static_reachable else "not_seen_static")),
            "recommendNewHook": recommend,
            "reason": static_probe_lineage(spec["id"], s_hits),
        }
        surfaces.append(row)
        if static_reachable and not runtime_observed:
            uncovered_static_reachable.append(row)
        if recommend:
            recommended.append(row)

    implemented_recommended_hook_count = sum(
        1
        for s in surfaces
        if s["id"] in {"native_mobile_bridge_pxMobileData", "offline_audio_fingerprint", "service_worker_cache_fingerprint"}
        and s["staticReachable"]
        and s["hookDeclared"]
    )

    checks = {
        "planExists": PLAN.exists(),
        "hookSourceExists": HOOK_SOURCE.exists(),
        "matrixExists": MATRIX.exists(),
        "staticInputFileCount": len([p for p in STATIC_FILES if p.exists()]),
        "countedJsTraceCount": len(js_paths),
        "observedRuntimeKindCount": len(kind_counts),
        "surfaceCount": len(surfaces),
        "staticReachableSurfaceCount": sum(1 for s in surfaces if s["staticReachable"]),
        "runtimeObservedSurfaceCount": sum(1 for s in surfaces if s["runtimeObserved"]),
        "staticReachableButRuntimeUnobservedCount": len(uncovered_static_reachable),
        "implementedRouteBRecommendedHookCount": implemented_recommended_hook_count,
        "recommendedNewHookCount": len(recommended),
        "previousHookAxisRecommendedAxisCount": (hook_axis.get("checks") or {}).get("recommendedAxisCount"),
        "terminalNoCurrentRouteToPhase5": (terminal.get("checks") or {}).get("noCurrentRouteToPhase5") is True,
        "readyForResampling": implemented_recommended_hook_count == 3 and len(recommended) == 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    decision_reason = (
        "Route B found static-reachable lifecycle/fingerprint surfaces that are not fully observed by current hooks. "
        "These are hook recommendations only; they do not prove a pure-protocol success transition and do not authorize Phase 5."
        if recommended
        else "Route B found no new static-reachable hook recommendation; current evidence still does not authorize Phase 5."
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Route B: enumerate static JS lifecycle/fingerprint surfaces against current hook and runtime trace coverage.",
        "inputs": {
            "hookSource": str(HOOK_SOURCE),
            "matrix": str(MATRIX),
            "hookAxisPlan": str(HOOK_AXIS),
            "terminalBoundaryAudit": str(TERMINAL),
            "staticFiles": [str(p) for p in STATIC_FILES],
            "jsInternalTraces": [str(p) for p in js_paths],
        },
        "checks": checks,
        "runtimeKindTop": kind_counts.most_common(80),
        "surfaces": surfaces,
        "recommendedNewHooks": [
            {
                "id": s["id"],
                "coverage": s["coverage"],
                "reason": s["reason"],
                "staticHits": s["staticHits"][:3],
            }
            for s in recommended
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForResampling": checks["readyForResampling"],
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": decision_reason,
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "recommendedNewHooks": doc["recommendedNewHooks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
