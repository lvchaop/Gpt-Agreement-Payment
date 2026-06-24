#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUTLOOK = REPO / "output/outlook_browser"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "server_internal_gap_evidence_inventory.json"


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def rel_glob(root: Path, pattern: str) -> list[Path]:
    return sorted(root.glob(pattern))


def sample(paths: list[Path], limit: int = 8) -> list[str]:
    return [str(p.resolve()) for p in paths[:limit]]


def run_id_from_trace(path: Path, prefix: str) -> str:
    name = path.name
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name.removesuffix(".jsonl")


def run_id_from_named_json(path: Path, prefix: str) -> str:
    name = path.name
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name.removesuffix(".json")


def file_group(name: str, paths: list[Path], purpose: str) -> dict[str, Any]:
    return {
        "id": name,
        "purpose": purpose,
        "count": len(paths),
        "sample": sample(paths),
    }


def classifier_summary(path: Path) -> dict[str, Any]:
    data = load_json(path) or {}
    runs = data.get("runs") or []
    stage_counts: dict[str, int] = {}
    runs_with_full_success = []
    runs_with_parent_success_only = []
    for row in runs:
        stage = row.get("stage")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        checks = row.get("checks") or {}
        if checks.get("risk_verify_state_continue") is True and checks.get("create_account_redirectUrl") is True:
            runs_with_full_success.append(row.get("run"))
        elif checks.get("parent_postmessage_succeeded") is True:
            runs_with_parent_success_only.append(row.get("run"))
    return {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "runCount": data.get("runCount"),
        "stageCounts": stage_counts,
        "fullSuccessRuns": runs_with_full_success,
        "parentSuccessOnlyRuns": runs_with_parent_success_only,
    }


def direct_attempt_summary(paths: list[Path]) -> dict[str, Any]:
    rows = []
    for path in paths:
        data = load_json(path) or {}
        steps = data.get("steps") or {}
        checks = data.get("checks") or {}
        rows.append(
            {
                "path": str(path.resolve()),
                "session": data.get("session"),
                "stepNames": list(steps.keys()),
                "checks": checks,
            }
        )
    check_keys = sorted({key for row in rows for key in (row.get("checks") or {}).keys()})
    true_counts = {
        key: sum(1 for row in rows if (row.get("checks") or {}).get(key) is True)
        for key in check_keys
    }
    return {
        "count": len(paths),
        "checkKeys": check_keys,
        "trueCounts": true_counts,
        "sampleRows": rows[:5],
    }


def probe_summary(paths: list[Path]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    success_handler_count = 0
    pow_result_count = 0
    rows = []
    for path in paths:
        data = load_json(path) or {}
        checks = data.get("checks") or {}
        results = data.get("results") or {}
        response_statuses = []
        has_success = False
        has_pow = False
        for result in results.values():
            if isinstance(result, dict):
                status = result.get("status") or (result.get("response") or {}).get("status")
                if status is not None:
                    response_statuses.append(str(status))
                text = json.dumps(result, ensure_ascii=False)
                has_success = has_success or "oIIoIooo" in text and "|0" in text
                has_pow = has_pow or "pow" in text.lower()
        for status in response_statuses:
            status_counts[status] = status_counts.get(status, 0) + 1
        success_handler_count += int(has_success)
        pow_result_count += int(has_pow)
        rows.append(
            {
                "path": str(path.resolve()),
                "checks": checks,
                "responseStatuses": response_statuses,
                "hasSuccessText": has_success,
                "hasPowText": has_pow,
            }
        )
    return {
        "count": len(paths),
        "responseStatusCounts": status_counts,
        "filesWithSuccessText": success_handler_count,
        "filesWithPowText": pow_result_count,
        "sampleRows": rows[:5],
    }


def build() -> dict[str, Any]:
    server_proxy_path = BASE / "server_expected_state_observable_proxy.json"
    status_path = BASE / "hypothesis_reframe_status.json"
    goal_audit_path = PROTO / "goal_audit/pure_protocol_goal_gap_audit.json"
    classifier_path = PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json"

    server_proxy = load_json(server_proxy_path) or {}
    status = load_json(status_path) or {}

    runtime_traces = rel_glob(OUTLOOK, "runtime_trace_*.jsonl")
    js_traces = rel_glob(OUTLOOK, "js_internal_trace_*.jsonl")
    static_files = rel_glob(OUTLOOK / "js_static_analysis", "**/*")
    static_files = [p for p in static_files if p.is_file()]
    collector_decodes = rel_glob(PROTO / "collector_decode", "collector_decode_*.json")
    cookie_timelines = rel_glob(PROTO / "cookie_timeline", "cookie_timeline_*.json")
    direct_attempts = rel_glob(PROTO / "direct_webshare_attempt", "direct_webshare_attempt_*.json")
    overlap_attempts = rel_glob(PROTO / "first_failure_overlap_attempt", "first_failure_overlap_attempt_*.json")
    combo_probes = rel_glob(PROTO / "seq5_seq6_combo_probe", "seq5_seq6_combo_probe_*.json")
    combo_extracted = rel_glob(PROTO / "seq5_seq6_combo_probe/extracted", "*.json")
    px561_compares = rel_glob(PROTO / "px561_compare", "seq5_seq6_combo_probe_*_seq*_full_*_diff.json")

    runtime_ids = {run_id_from_trace(p, "runtime_trace_") for p in runtime_traces}
    js_ids = {run_id_from_trace(p, "js_internal_trace_") for p in js_traces}
    decode_ids = {run_id_from_named_json(p, "collector_decode_") for p in collector_decodes}
    cookie_ids = {run_id_from_named_json(p, "cookie_timeline_") for p in cookie_timelines}
    multi_surface_ids = sorted(runtime_ids & js_ids & decode_ids & cookie_ids)

    evidence_sources = [
        file_group(
            "browser_runtime_traces",
            runtime_traces,
            "Existing browser-side request/response runtime traces; usable for cross-run visible transition comparison without new network.",
        ),
        file_group(
            "browser_js_internal_traces",
            js_traces,
            "Existing JS hook traces; usable to search for non-network client-visible state changes around accepted/rejected boundaries.",
        ),
        file_group(
            "collector_decode_outputs",
            collector_decodes,
            "Decoded collector responses; usable to compare handler/status sequences across browser runs.",
        ),
        file_group(
            "cookie_timelines",
            cookie_timelines,
            "Cookie/token mutation timelines; usable to compare _px mutation order and values across browser runs.",
        ),
        file_group(
            "static_js_analysis",
            static_files,
            "Static JS facts and handler snippets; lower-priority support evidence for explaining runtime-observed transitions.",
        ),
        file_group(
            "direct_webshare_attempts",
            direct_attempts,
            "Existing pure-protocol Webshare attempts; usable only as negative/control history unless a decoded success exists.",
        ),
        file_group(
            "first_failure_overlap_attempts",
            overlap_attempts,
            "Existing no-browser overlap attempts; usable to compare request order/body-order controls.",
        ),
        file_group(
            "seq5_seq6_combo_probes",
            combo_probes,
            "Existing seq5/seq6 combo probes; usable to mine response classes for already-run variants.",
        ),
        file_group(
            "seq5_seq6_extracted_requests",
            combo_extracted,
            "Extracted seq5/seq6 request material; usable for offline request-shape clustering.",
        ),
        file_group(
            "px561_compare_diffs",
            px561_compares,
            "Existing full activity/field diffs; usable for clustering already-run seq5 variants.",
        ),
    ]

    exhausted = [
        {
            "id": "selected_s00_vs_fresh_pre_final_visible_transition",
            "evidence": str(server_proxy_path.resolve()),
            "facts": [
                "omittedPreAcceptTransitionCount=0",
                "transitionHasReplayableClientRepresentation=false",
                "readyForFreshExperiment=false",
            ],
        },
        {
            "id": "single_transition_candidate_matrix",
            "evidence": str((BASE / "single_transition_candidate_matrix.json").resolve()),
            "facts": [
                "singleTransitionCandidateCount=0",
                "readyCandidateIds=[]",
            ],
        },
        {
            "id": "coupled_boundary_reduction_T1_T2_T3",
            "evidence": str(status_path.resolve()),
            "facts": [
                "outerTupleNoSingleFieldExperimentReady=true",
                "encoderSingleAxisNotIsolated=true",
                "serverObservableProxyNotFound=true",
            ],
        },
    ]

    candidate_next_sources = [
        {
            "id": "cross_sample_server_state_proxy_matrix",
            "inputEvidence": [
                "browser_runtime_traces",
                "browser_js_internal_traces",
                "collector_decode_outputs",
                "cookie_timelines",
                "trace_classifier_v2",
            ],
            "whyThisIsNewEvidence": "The current T3 result is based on the selected s00/fresh contrast. The repo contains multiple browser runs with classifier stages and overlapping runtime/js/decode/cookie surfaces, which can test whether a client-visible transition correlates across samples.",
            "nextArtifact": str((BASE / "cross_sample_server_state_proxy_matrix.json").resolve()),
            "nextScript": str((REPO / "tools/build_cross_sample_server_state_proxy_matrix.py").resolve()),
            "networkRequired": False,
        },
        {
            "id": "historical_probe_response_class_matrix",
            "inputEvidence": [
                "direct_webshare_attempts",
                "first_failure_overlap_attempts",
                "seq5_seq6_combo_probes",
                "px561_compare_diffs",
            ],
            "whyThisIsNewEvidence": "Existing no-browser attempts can be clustered by already-sent variant and response class before any new network run is allowed.",
            "nextArtifact": str((BASE / "historical_probe_response_class_matrix.json").resolve()),
            "nextScript": str((REPO / "tools/build_historical_probe_response_class_matrix.py").resolve()),
            "networkRequired": False,
        },
        {
            "id": "js_internal_event_taxonomy",
            "inputEvidence": [
                "browser_js_internal_traces",
                "static_js_analysis",
            ],
            "whyThisIsNewEvidence": "JS hook traces may contain client-only events not represented in collector request/response summaries; static JS may explain only transitions first observed at runtime.",
            "nextArtifact": str((BASE / "js_internal_event_taxonomy.json").resolve()),
            "nextScript": str((REPO / "tools/build_js_internal_event_taxonomy.py").resolve()),
            "networkRequired": False,
        },
    ]

    checks = {
        "serverProxyRequiresNewEvidence": ((server_proxy.get("checks") or {}).get("transitionHasReplayableClientRepresentation") is False),
        "statusSaysNotReadyForFreshExperiment": ((status.get("checks") or {}).get("readyForFreshExperiment") is False),
        "hasGoalAudit": goal_audit_path.exists(),
        "hasTraceClassifierV2": classifier_path.exists(),
        "runtimeTraceCount": len(runtime_traces),
        "jsTraceCount": len(js_traces),
        "collectorDecodeCount": len(collector_decodes),
        "cookieTimelineCount": len(cookie_timelines),
        "multiSurfaceBrowserRunCount": len(multi_surface_ids),
        "directWebshareAttemptCount": len(direct_attempts),
        "firstFailureOverlapAttemptCount": len(overlap_attempts),
        "seq5Seq6ComboProbeCount": len(combo_probes),
        "staticJsFileCount": len(static_files),
        "hasCandidateLocalEvidenceSources": len(candidate_next_sources) > 0,
        "recommendedNextIsOffline": candidate_next_sources[0]["networkRequired"] is False,
        "readyForFreshExperiment": False,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Inventory local evidence sources that can reduce the remaining collector server-internal/unobserved expected-state gap without running a fresh network experiment.",
        "inputs": {
            "serverExpectedStateObservableProxy": str(server_proxy_path.resolve()),
            "hypothesisReframeStatus": str(status_path.resolve()),
            "goalAudit": str(goal_audit_path.resolve()),
            "traceClassifierV2": str(classifier_path.resolve()),
        },
        "classifierSummary": classifier_summary(classifier_path),
        "evidenceSources": evidence_sources,
        "multiSurfaceBrowserRuns": {
            "count": len(multi_surface_ids),
            "sample": multi_surface_ids[:12],
        },
        "historicalNoBrowserAttempts": {
            "directWebshare": direct_attempt_summary(direct_attempts),
            "firstFailureOverlap": direct_attempt_summary(overlap_attempts),
            "seq5Seq6Combo": probe_summary(combo_probes),
        },
        "exhaustedEvidence": exhausted,
        "candidateNewEvidenceSources": candidate_next_sources,
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedNextArtifact": candidate_next_sources[0]["nextArtifact"],
            "recommendedNextScript": candidate_next_sources[0]["nextScript"],
            "reason": "Current selected-contrast evidence is exhausted for a single replayable transition. Local cross-sample browser evidence exists and must be mined before any fresh network experiment.",
        },
        "checks": checks,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
