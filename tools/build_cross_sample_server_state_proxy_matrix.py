#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUTLOOK = REPO / "output/outlook_browser"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "cross_sample_server_state_proxy_matrix.json"


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_from_trace_classification(path: Path) -> str:
    return path.name.removeprefix("trace_classification_").removesuffix(".json")


def run_from_collector_decode(path: Path) -> str:
    return path.name.removeprefix("collector_decode_").removesuffix(".json")


def run_from_cookie_timeline(path: Path) -> str:
    return path.name.removeprefix("cookie_timeline_").removesuffix(".json")


def shaish(text: str, max_len: int = 80) -> str:
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def success_parts(entry: dict[str, Any]) -> list[str]:
    return [p for p in entry.get("parts") or [] if isinstance(p, str) and p.startswith("oIIoIooo|")]


def count_part_prefix(entries: list[dict[str, Any]], prefix: str, before_line: int | None = None) -> int:
    total = 0
    for entry in entries:
        if before_line is not None and (entry.get("lineNo") or 0) >= before_line:
            continue
        total += sum(1 for part in entry.get("parts") or [] if isinstance(part, str) and part.startswith(prefix))
    return total


def decode_features(path: Path) -> dict[str, Any]:
    data = load_json(path) or {}
    entries = data.get("decodedEntries") or []
    success_entries = [
        entry for entry in entries
        if any(part == "oIIoIooo|0" for part in success_parts(entry))
    ]
    failure_success_entries = [
        entry for entry in entries
        if any(part == "oIIoIooo|-1" for part in success_parts(entry))
    ]
    first_success_line = min([entry.get("lineNo") for entry in success_entries if entry.get("lineNo") is not None], default=None)
    first_failure_line = min([entry.get("lineNo") for entry in failure_success_entries if entry.get("lineNo") is not None], default=None)
    # If a run has no success line, every decoded response is still pre-accept
    # evidence. Treating it as an empty pre-success window creates false
    # separators when comparing success and failure samples.
    pre_accept_entries = [
        entry for entry in entries
        if first_success_line is None or (entry.get("lineNo") or 0) < first_success_line
    ]
    handler_sequences = ["|".join(entry.get("handlers") or []) for entry in entries]
    pre_accept_handler_sequences = ["|".join(entry.get("handlers") or []) for entry in pre_accept_entries]
    return {
        "exists": path.exists(),
        "path": str(path.resolve()),
        "entryCount": len(entries),
        "successLineCount": len(success_entries),
        "failureSuccessLineCount": len(failure_success_entries),
        "firstSuccessLine": first_success_line,
        "firstFailureSuccessLine": first_failure_line,
        "hasDecodedSuccess0": bool(success_entries),
        "hasDecodedFailureMinus1": bool(failure_success_entries),
        "hasFailureBeforeSuccess": bool(first_failure_line is not None and first_success_line is not None and first_failure_line < first_success_line),
        "preAcceptEntryCount": len(pre_accept_entries),
        "preAcceptPowCount": sum(1 for entry in pre_accept_entries if entry.get("hasPowResult") is True),
        "preSuccessPx3Count": count_part_prefix(entries, "IoooII|_px3", first_success_line),
        "preSuccessPxdeCount": count_part_prefix(entries, "oIIoIIoo|_pxde", first_success_line),
        "preSuccessFailureMinus1Count": count_part_prefix(entries, "oIIoIooo|-1", first_success_line),
        "handlerSequenceSet": sorted(set(handler_sequences)),
        "preAcceptHandlerSequenceSet": sorted(set(pre_accept_handler_sequences)),
    }


def js_features(path: Path) -> dict[str, Any]:
    rows = iter_jsonl(path)
    kind_counts = Counter(row.get("kind") for row in rows)
    token_counts = Counter()
    origins = Counter()
    channels = Counter()
    for row in rows:
        text = json.dumps(row, ensure_ascii=False)
        for token in ["oIIoIooo", "succeeded", "failed", "challenge_success", "pow", "_px3", "_pxde", "sendBeacon"]:
            if token in text:
                token_counts[token] += 1
        data = row.get("data") if isinstance(row.get("data"), dict) else {}
        if data:
            if data.get("eventOrigin"):
                origins[data.get("eventOrigin")] += 1
            if data.get("channel"):
                channels[data.get("channel")] += 1
    return {
        "exists": path.exists(),
        "path": str(path.resolve()),
        "rowCount": len(rows),
        "kindCounts": dict(kind_counts),
        "tokenCounts": dict(token_counts),
        "eventOrigins": dict(origins),
        "channels": dict(channels),
        "hasMainDispatch": kind_counts.get("hsprotect.main.jl.dispatch", 0) > 0,
        "hasPowHit": kind_counts.get("hsprotect.captcha.pow.hit", 0) > 0,
        "sendBeaconInternalCount": kind_counts.get("hsprotect.sendBeacon.internal", 0),
        "workerErrorCount": kind_counts.get("hsprotect.captcha.worker.error", 0),
        "documentCookieSetCount": kind_counts.get("document.cookie.set", 0),
        "windowMessageRecvCount": kind_counts.get("window.message.recv", 0),
        "triggerCount": kind_counts.get("hsprotect.Xn.trigger", 0),
        "oIIoIoooTokenCount": token_counts.get("oIIoIooo", 0),
        "succeededTokenCount": token_counts.get("succeeded", 0),
        "failedTokenCount": token_counts.get("failed", 0),
    }


def runtime_features(path: Path) -> dict[str, Any]:
    rows = iter_jsonl(path)
    request_paths = Counter()
    response_paths = Counter()
    statuses = Counter()
    risk_continue = False
    create_redirect = False
    collector_request_count = 0
    collector_bundle_count = 0
    msft_count = 0
    for row in rows:
        url = row.get("url") or ""
        parsed = urlparse(url)
        path_key = parsed.netloc + parsed.path
        if row.get("kind") == "request":
            request_paths[path_key] += 1
            if "collector-pxzc5j78di.hsprotect.net" in parsed.netloc:
                collector_request_count += 1
            if parsed.path == "/assets/js/bundle":
                collector_bundle_count += 1
            if parsed.path == "/api/v2/msft":
                msft_count += 1
        elif row.get("kind") == "response":
            response_paths[path_key] += 1
            statuses[str(row.get("status"))] += 1
            body = row.get("body")
            if isinstance(body, str):
                risk_continue = risk_continue or '"state":"continue"' in body or '"state": "continue"' in body
                create_redirect = create_redirect or "redirectUrl" in body
    return {
        "exists": path.exists(),
        "path": str(path.resolve()),
        "rowCount": len(rows),
        "requestPathCounts": dict(request_paths),
        "responsePathCounts": dict(response_paths),
        "statusCounts": dict(statuses),
        "collectorRequestCount": collector_request_count,
        "collectorBundleRequestCount": collector_bundle_count,
        "apiV2MsftRequestCount": msft_count,
        "riskContinueSeen": risk_continue,
        "createAccountRedirectSeen": create_redirect,
    }


def cookie_features(path: Path) -> dict[str, Any]:
    data = load_json(path) or {}
    decoded = data.get("decodedEvents") or []
    parent = data.get("parentMessages") or []
    corr = data.get("correlations") or []
    success_events = [ev for ev in decoded if ev.get("handler") == "oIIoIooo" and ev.get("value") == "0"]
    failure_events = [ev for ev in decoded if ev.get("handler") == "oIIoIooo" and ev.get("value") == "-1"]
    px3_events = [ev for ev in decoded if ev.get("name") == "_px3"]
    pxde_events = [ev for ev in decoded if ev.get("name") == "_pxde"]
    pxvid_events = [ev for ev in decoded if ev.get("name") == "_pxvid"]
    return {
        "exists": path.exists(),
        "path": str(path.resolve()),
        "decodedEventCount": len(decoded),
        "parentMessageCount": len(parent),
        "correlationCount": len(corr),
        "successEventCount": len(success_events),
        "failureEventCount": len(failure_events),
        "px3EventCount": len(px3_events),
        "pxdeEventCount": len(pxde_events),
        "pxvidEventCount": len(pxvid_events),
        "hasCookieSuccess0": bool(success_events),
        "hasCookieFailureMinus1": bool(failure_events),
    }


def bool_feature_rows(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feature_defs = [
        ("decode.hasDecodedSuccess0", lambda s: (s["decode"].get("hasDecodedSuccess0") is True), "outcome"),
        ("decode.hasDecodedFailureMinus1", lambda s: (s["decode"].get("hasDecodedFailureMinus1") is True), "pre_accept_or_failure_response"),
        ("decode.hasFailureBeforeSuccess", lambda s: (s["decode"].get("hasFailureBeforeSuccess") is True), "pre_accept"),
        ("decode.preAcceptPowCount>0", lambda s: (s["decode"].get("preAcceptPowCount") or 0) > 0, "pre_accept"),
        ("decode.preSuccessFailureMinus1Count>0", lambda s: (s["decode"].get("preSuccessFailureMinus1Count") or 0) > 0, "pre_accept"),
        ("decode.preSuccessPx3Count>=2", lambda s: (s["decode"].get("preSuccessPx3Count") or 0) >= 2, "pre_accept"),
        ("js.hasMainDispatch", lambda s: (s["js"].get("hasMainDispatch") is True), "client_visible"),
        ("js.hasPowHit", lambda s: (s["js"].get("hasPowHit") is True), "client_visible"),
        ("js.workerErrorCount>0", lambda s: (s["js"].get("workerErrorCount") or 0) > 0, "client_visible"),
        ("js.sendBeaconInternalCount>0", lambda s: (s["js"].get("sendBeaconInternalCount") or 0) > 0, "client_visible"),
        ("js.oIIoIoooTokenCount>0", lambda s: (s["js"].get("oIIoIoooTokenCount") or 0) > 0, "outcome_or_handler"),
        ("runtime.apiV2MsftRequestCount>=5", lambda s: (s["runtime"].get("apiV2MsftRequestCount") or 0) >= 5, "request_surface"),
        ("runtime.collectorBundleRequestCount>=3", lambda s: (s["runtime"].get("collectorBundleRequestCount") or 0) >= 3, "request_surface"),
        ("runtime.riskContinueSeen", lambda s: (s["runtime"].get("riskContinueSeen") is True), "downstream_outcome"),
        ("runtime.createAccountRedirectSeen", lambda s: (s["runtime"].get("createAccountRedirectSeen") is True), "downstream_outcome"),
        ("cookie.hasCookieSuccess0", lambda s: (s["cookie"].get("hasCookieSuccess0") is True), "outcome"),
        ("cookie.hasCookieFailureMinus1", lambda s: (s["cookie"].get("hasCookieFailureMinus1") is True), "pre_accept_or_failure_response"),
        ("cookie.px3EventCount>=5", lambda s: (s["cookie"].get("px3EventCount") or 0) >= 5, "client_visible_cookie"),
        ("cookie.parentMessageCount>=20", lambda s: (s["cookie"].get("parentMessageCount") or 0) >= 20, "client_visible_parent"),
    ]
    full = [s for s in samples if s["isFullSuccess"]]
    non = [s for s in samples if not s["isFullSuccess"]]
    rows = []
    for name, func, category in feature_defs:
        full_true = [s["run"] for s in full if func(s)]
        non_true = [s["run"] for s in non if func(s)]
        all_full = len(full_true) == len(full) and bool(full)
        absent_non = len(non_true) == 0
        candidate = all_full and absent_non and category in {"pre_accept", "client_visible", "request_surface", "client_visible_cookie", "client_visible_parent"}
        rows.append(
            {
                "feature": name,
                "category": category,
                "fullSuccessTrueCount": len(full_true),
                "nonFullSuccessTrueCount": len(non_true),
                "fullSuccessCount": len(full),
                "nonFullSuccessCount": len(non),
                "allFullSuccessTrue": all_full,
                "absentInNonFullSuccess": absent_non,
                "candidateClientVisibleProxy": candidate,
                "trueFullSuccessRuns": full_true,
                "trueNonFullSuccessRuns": non_true[:20],
            }
        )
    return rows


def build_sample(run: str, classification: dict[str, Any]) -> dict[str, Any]:
    js_path = OUTLOOK / f"js_internal_trace_{run}.jsonl"
    runtime_path = OUTLOOK / f"runtime_trace_{run}.jsonl"
    decode_path = PROTO / "collector_decode" / f"collector_decode_{run}.json"
    cookie_path = PROTO / "cookie_timeline" / f"cookie_timeline_{run}.json"
    checks = classification.get("checks") or {}
    return {
        "run": run,
        "status": classification.get("status"),
        "checks": checks,
        "isFullSuccess": checks.get("decoded_oIIoIooo_0") is True
        and checks.get("risk_verify_state_continue") is True
        and checks.get("create_account_redirectUrl") is True,
        "surfaces": {
            "classification": True,
            "js": js_path.exists(),
            "runtime": runtime_path.exists(),
            "decode": decode_path.exists(),
            "cookie": cookie_path.exists(),
        },
        "decode": decode_features(decode_path),
        "js": js_features(js_path),
        "runtime": runtime_features(runtime_path),
        "cookie": cookie_features(cookie_path),
    }


def build() -> dict[str, Any]:
    classification_paths = [
        p for p in sorted(PROTO.glob("trace_classification_*.json"))
        if p.name != "trace_classification_summary.json"
    ]
    samples = []
    for path in classification_paths:
        run = run_from_trace_classification(path)
        data = load_json(path) or {}
        samples.append(build_sample(run, data))

    full_success = [s for s in samples if s["isFullSuccess"]]
    non_full = [s for s in samples if not s["isFullSuccess"]]
    multi_surface = [
        s for s in samples
        if s["surfaces"].get("js") and s["surfaces"].get("runtime") and s["surfaces"].get("decode") and s["surfaces"].get("cookie")
    ]
    rows = bool_feature_rows(samples)
    candidate_rows = [row for row in rows if row["candidateClientVisibleProxy"]]
    outcome_only_separators = [
        row for row in rows
        if row["allFullSuccessTrue"] and row["absentInNonFullSuccess"] and not row["candidateClientVisibleProxy"]
    ]

    stage_counts = Counter(s.get("status") for s in samples)
    checks = {
        "sampleCount": len(samples),
        "fullSuccessCount": len(full_success),
        "nonFullSuccessCount": len(non_full),
        "multiSurfaceSampleCount": len(multi_surface),
        "hasAtLeastThreeFullSuccessSamples": len(full_success) >= 3,
        "hasNonFullSuccessControls": len(non_full) > 0,
        "hasMultiSurfaceSamples": len(multi_surface) > 0,
        "candidateClientVisibleProxyCount": len(candidate_rows),
        "outcomeOnlySeparatorCount": len(outcome_only_separators),
        "readyForFreshExperiment": False,
    }

    decision_reason = (
        "Cross-sample matrix found no pre-accept/client-visible feature that is present in all full_success samples and absent in all non-full-success controls."
        if not candidate_rows
        else "Cross-sample matrix found candidate client-visible proxy rows; each candidate must be reduced to a replayable request/handler transition before any fresh network experiment."
    )

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Use existing browser success/failure samples to test whether the remaining collector server-internal expected-state gap has a cross-sample client-visible proxy.",
        "inputs": {
            "plan": str((REPO / "docs/pure-protocol-human-hypothesis-plan.md").resolve()),
            "traceClassifications": [str(p.resolve()) for p in classification_paths],
            "serverInternalGapEvidenceInventory": str((BASE / "server_internal_gap_evidence_inventory.json").resolve()),
        },
        "summary": {
            "sampleCount": len(samples),
            "stageCounts": dict(stage_counts),
            "fullSuccessRuns": [s["run"] for s in full_success],
            "nonFullSuccessRuns": [s["run"] for s in non_full],
            "multiSurfaceRuns": [s["run"] for s in multi_surface],
        },
        "featureRows": rows,
        "candidateClientVisibleProxyRows": candidate_rows,
        "outcomeOnlySeparators": outcome_only_separators,
        "sampleSummaries": [
            {
                "run": s["run"],
                "status": s["status"],
                "isFullSuccess": s["isFullSuccess"],
                "surfaces": s["surfaces"],
                "decode": {
                    k: s["decode"].get(k)
                    for k in [
                        "entryCount",
                        "firstSuccessLine",
                        "firstFailureSuccessLine",
                        "hasDecodedSuccess0",
                        "hasDecodedFailureMinus1",
                        "hasFailureBeforeSuccess",
                        "preAcceptEntryCount",
                        "preAcceptPowCount",
                        "preSuccessFailureMinus1Count",
                    ]
                },
                "js": {
                    k: s["js"].get(k)
                    for k in [
                        "rowCount",
                        "hasMainDispatch",
                        "hasPowHit",
                        "sendBeaconInternalCount",
                        "workerErrorCount",
                        "documentCookieSetCount",
                        "windowMessageRecvCount",
                        "oIIoIoooTokenCount",
                    ]
                },
                "runtime": {
                    k: s["runtime"].get(k)
                    for k in [
                        "rowCount",
                        "collectorRequestCount",
                        "collectorBundleRequestCount",
                        "apiV2MsftRequestCount",
                        "riskContinueSeen",
                        "createAccountRedirectSeen",
                    ]
                },
                "cookie": {
                    k: s["cookie"].get(k)
                    for k in [
                        "decodedEventCount",
                        "parentMessageCount",
                        "successEventCount",
                        "failureEventCount",
                        "px3EventCount",
                        "pxdeEventCount",
                    ]
                },
            }
            for s in samples
        ],
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "candidateClientVisibleProxyFound": bool(candidate_rows),
            "reason": decision_reason,
            "nextArtifact": str((BASE / "historical_probe_response_class_matrix.json").resolve()) if not candidate_rows else str((BASE / "client_visible_proxy_reduction.json").resolve()),
            "nextScript": str((REPO / "tools/build_historical_probe_response_class_matrix.py").resolve()) if not candidate_rows else str((REPO / "tools/build_client_visible_proxy_reduction.py").resolve()),
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
