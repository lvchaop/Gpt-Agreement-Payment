#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
RESET_DIR = PROTO / "reset_plan"
MATRIX = RESET_DIR / "reset_sampling_matrix.json"
OUT = RESET_DIR / "reset_state_machine.json"


HOOK_MARKERS = {
    "message_bridge": ["window.postMessage.call", "window.message.recv", "MessagePort.postMessage", "MessagePort.message"],
    "worker": ["Worker.new", "Worker.postMessage", "Worker.message", "hsprotect.captcha.worker.new"],
    "document_cookie": ["document.cookie.set"],
    "network": ["fetch.call", "xhr.open", "xhr.send", "sendBeacon"],
    "wasm": ["hsprotect.captcha.wasm.material", "hsprotect.captcha.wasm.nq.before", "hsprotect.captcha.wasm.nq.after"],
    "pow_worker": ["hsprotect.captcha.qs.start", "hsprotect.captcha.pow.hit"],
    "storage": ["localStorage", "sessionStorage", "indexedDB"],
    "crypto": ["crypto.snapshot", "crypto.getRandomValues", "crypto.subtle"],
    "performance": ["performance.snapshot", "performance.now.call", "Date.now.call"],
}

TEXT_CACHE: dict[str, str] = {}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def abs_path(path: Path | str | None) -> str | None:
    if not path:
        return None
    p = Path(str(path))
    return str(p if p.is_absolute() else ROOT / p)


def file_has(path: str | None, needle: str) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        return False
    key = str(p.resolve())
    if key not in TEXT_CACHE:
        TEXT_CACHE[key] = p.read_text(encoding="utf-8", errors="ignore").lower()
    return needle.lower() in TEXT_CACHE[key]


def file_has_any(paths: list[str], markers: list[str]) -> bool:
    return any(file_has(path, marker) for path in paths for marker in markers)


def hook_features(paths: list[str]) -> dict[str, bool]:
    return {name: file_has_any(paths, markers) for name, markers in HOOK_MARKERS.items()}


def browser_stage(row: dict[str, Any]) -> str:
    checks = row.get("checks") or {}
    if checks.get("decoded_oIIoIooo_0") and checks.get("risk_verify_state_continue") and checks.get("create_account_redirectUrl"):
        return "create_account_redirectUrl"
    if checks.get("risk_verify_state_continue"):
        return "risk_verify_state_continue"
    if checks.get("decoded_oIIoIooo_0"):
        return "collector_success_oIIoIooo_0"
    return str(row.get("stage") or "browser_non_success")


def pure_stage(row: dict[str, Any]) -> str:
    cls = row.get("classification") or {}
    return str(cls.get("stage") or "pure_protocol_unclassified")


def browser_sample_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    existing = matrix.get("existingBaselineRows") or {}
    for class_id in ["browser_success_webshare", "browser_failure_webshare"]:
        for row in existing.get(class_id) or []:
            runtime = row.get("evidence", {}).get("runtimeTrace")
            js_trace = row.get("evidence", {}).get("jsTrace")
            rows.append(
                {
                    "sampleId": row.get("run"),
                    "sampleClass": class_id,
                    "source": row.get("source"),
                    "transport": row.get("transport"),
                    "stage": browser_stage(row),
                    "successLike": class_id == "browser_success_webshare",
                    "resetCollected": False,
                    "evidence": row.get("evidence"),
                    "checks": {
                        **(row.get("checks") or {}),
                        "runtimeHasProxyAuthorization": file_has(runtime, "proxy-authorization"),
                        "runtimeHasCollector": file_has(runtime, "collector-pxzc5j78di.hsprotect.net"),
                        "jsTraceExists": Path(abs_path(js_trace) or "").exists() if js_trace else False,
                    },
                }
            )
    return rows


def browser_reset_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for idx, row in enumerate(matrix.get("executedRows") or []):
        sample_class = row.get("sampleClass")
        if sample_class not in {"browser_success_webshare", "browser_failure_webshare"}:
            continue
        if row.get("countsTowardResetMinimum") is not True:
            continue
        evidence = row.get("evidence") or {}
        classification = row.get("classification") or {}
        runtime = evidence.get("runtimeTrace") or []
        js_trace = evidence.get("jsInternalTrace") or []
        trace_paths = [str(p) for p in runtime + js_trace]
        rows.append(
            {
                "sampleId": evidence.get("sessionId") or f"{sample_class}_reset_{idx}",
                "sampleClass": sample_class,
                "source": row.get("source") or "reset_browser_webshare_sampling_runner",
                "transport": row.get("transport"),
                "stage": str(classification.get("stage") or "browser_reset_unclassified"),
                "successLike": classification.get("successLike") is True,
                "resetCollected": True,
                "evidence": {
                    "attemptSummary": evidence.get("attemptSummary"),
                    "runtimeTrace": runtime,
                    "jsInternalTrace": js_trace,
                    "pxCookieBridge": evidence.get("pxCookieBridge") or [],
                    "browserApiCreate": evidence.get("browserApiCreate") or [],
                    "proxySessionUser": evidence.get("proxySessionUser"),
                },
                "checks": {
                    **(row.get("checks") or {}),
                    "runtimeTraceExists": bool(runtime),
                    "jsInternalTraceExists": bool(js_trace),
                    "runtimeHasProxyAuthorization": any(file_has(path, "proxy-authorization") for path in runtime),
                    "runtimeHasCollector": any(file_has(path, "collector-pxzc5j78di.hsprotect.net") for path in runtime),
                    "hookFeatures": hook_features(trace_paths),
                },
            }
        )
    return rows


def pure_sample_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for idx, row in enumerate(matrix.get("executedRows") or []):
        sample_class = row.get("sampleClass")
        if sample_class not in {"pure_protocol_webshare", "pure_protocol_direct"}:
            continue
        evidence = row.get("evidence") or {}
        attempt_path = evidence.get("attemptSummary")
        attempt = read_json(Path(attempt_path)) if attempt_path else {}
        checks = row.get("checks") or attempt.get("checks") or {}
        rows.append(
            {
                "sampleId": evidence.get("sessionId") or f"{sample_class}_{idx}",
                "sampleClass": sample_class,
                "source": "reset_executed",
                "transport": "direct" if sample_class == "pure_protocol_direct" else "webshare",
                "stage": pure_stage(row),
                "successLike": checks.get("comboAnySuccess") is True,
                "resetCollected": True,
                "evidence": {
                    "attemptSummary": attempt_path,
                    "cmd": (row.get("execution") or {}).get("cmd"),
                    "stderrTail": (row.get("execution") or {}).get("stderrTail"),
                    "comboJson": (((attempt.get("steps") or {}).get("seq5Seq6Combo") or {}).get("summary") or {}).get("json"),
                },
                "checks": {
                    "returncode": (row.get("execution") or {}).get("returncode"),
                    "bootstrap200": checks.get("bootstrap200") is True,
                    "second200": checks.get("second200") is True,
                    "sequence200": checks.get("sequence200") is True,
                    "bundle200Pow": checks.get("bundle200Pow") is True,
                    "progression200Pow": checks.get("progression200Pow") is True,
                    "comboAnySuccess": checks.get("comboAnySuccess") is True,
                    "classificationComplete": ((row.get("classification") or {}).get("classified") is True),
                },
            }
        )
    return rows


def sample_transitions(sample: dict[str, Any]) -> list[str]:
    checks = sample.get("checks") or {}
    stage = sample.get("stage")
    if sample["sampleClass"].startswith("browser_"):
        if stage in {"create_account_redirectUrl", "browser_runtime_success_redirect"}:
            return [
                "browser_runtime_trace",
                "collector_success_oIIoIooo_0",
                "risk_verify_state_continue",
                "create_account_redirectUrl",
            ]
        return ["browser_runtime_trace", stage]
    out = []
    if checks.get("bootstrap200"):
        out.append("bootstrap")
    if checks.get("second200"):
        out.append("second")
    if checks.get("sequence200"):
        out.append("sequence")
    if checks.get("bundle200Pow"):
        out.append("bundle_pow")
    if checks.get("progression200Pow"):
        out.append("progression_pow")
    if stage == "final_seq5_seq6_no_success":
        out.append("final_seq5_seq6_no_success")
    elif stage in {"bootstrap_response_missing_sid", "webshare_proxy_auth_407"}:
        out.append(stage)
    elif checks.get("comboAnySuccess"):
        out.append("collector_success_oIIoIooo_0")
    return out or [stage]


def main() -> int:
    matrix = read_json(MATRIX)
    if not matrix:
        raise SystemExit(f"missing matrix: {MATRIX}")

    samples = browser_sample_rows(matrix) + browser_reset_rows(matrix) + pure_sample_rows(matrix)
    stage_counts = Counter(sample["stage"] for sample in samples)
    class_stage_counts: dict[str, Counter[str]] = defaultdict(Counter)
    transition_counts: Counter[str] = Counter()
    transition_samples: dict[str, list[str]] = defaultdict(list)
    for sample in samples:
        class_stage_counts[sample["sampleClass"]][sample["stage"]] += 1
        transitions = sample_transitions(sample)
        for a, b in zip(transitions, transitions[1:]):
            key = f"{a}->{b}"
            transition_counts[key] += 1
            transition_samples[key].append(str(sample["sampleId"]))

    browser_success_stages = {
        sample["stage"]
        for sample in samples
        if sample["sampleClass"] == "browser_success_webshare"
    }
    browser_failure_stages = {
        sample["stage"]
        for sample in samples
        if sample["sampleClass"] == "browser_failure_webshare"
    }
    pure_stages = {
        sample["stage"]
        for sample in samples
        if sample["sampleClass"] in {"pure_protocol_webshare", "pure_protocol_direct"}
    }

    success_only_stages = sorted(browser_success_stages - browser_failure_stages - pure_stages)
    pure_missing_success_stages = sorted(browser_success_stages - pure_stages)

    candidate_proxies = []
    for stage in success_only_stages:
        if stage in {"collector_success_oIIoIooo_0", "risk_verify_state_continue", "create_account_redirectUrl", "browser_runtime_success_redirect"}:
            candidate_proxies.append(
                {
                    "stage": stage,
                    "candidateType": "outcome_or_downstream_result",
                    "clientVisibleProxy": False,
                    "reason": "This is an outcome/downstream state, not a pre-accept replayable transition.",
                }
            )
        else:
            candidate_proxies.append(
                {
                    "stage": stage,
                    "candidateType": "unclassified_stage",
                    "clientVisibleProxy": False,
                    "reason": "Reset evidence does not yet prove this stage enters a request/cookie/risk input as a replayable transition.",
                }
            )

    reset_browser_samples = [
        sample for sample in samples
        if sample["sampleClass"].startswith("browser_") and sample.get("resetCollected")
    ]
    hook_feature_counts = {}
    hook_feature_proxies = []
    for feature in HOOK_MARKERS:
        success_count = sum(
            1
            for sample in reset_browser_samples
            if sample["sampleClass"] == "browser_success_webshare"
            and ((sample.get("checks") or {}).get("hookFeatures") or {}).get(feature) is True
        )
        failure_count = sum(
            1
            for sample in reset_browser_samples
            if sample["sampleClass"] == "browser_failure_webshare"
            and ((sample.get("checks") or {}).get("hookFeatures") or {}).get(feature) is True
        )
        hook_feature_counts[feature] = {
            "successCount": success_count,
            "failureCount": failure_count,
        }
        if success_count > 0 and failure_count == 0:
            hook_feature_proxies.append(
                {
                    "stage": f"hook_feature:{feature}",
                    "candidateType": "success_only_hook_feature",
                    "clientVisibleProxy": False,
                    "successCount": success_count,
                    "failureCount": failure_count,
                    "reason": "Feature is success-only in reset browser hook samples, but current evidence does not prove it is constructible by pure protocol or a pre-accept transition rather than browser-only execution context.",
                }
            )
    candidate_proxies.extend(hook_feature_proxies)

    stage_nodes = [
        {
            "id": stage,
            "count": count,
            "classes": {
                class_id: class_stage_counts[class_id].get(stage, 0)
                for class_id in sorted(class_stage_counts)
            },
        }
        for stage, count in sorted(stage_counts.items())
    ]
    transitions = [
        {
            "id": key,
            "count": count,
            "samples": transition_samples[key],
        }
        for key, count in sorted(transition_counts.items())
    ]

    client_visible_proxy_count = sum(1 for row in candidate_proxies if row["clientVisibleProxy"])
    pure_webshare_proxy_auth_407_failures = sum(
        1
        for sample in samples
        if sample["sampleClass"] == "pure_protocol_webshare"
        and sample["stage"] == "webshare_proxy_auth_407"
    )
    pure_webshare_final_failures = sum(
        1
        for sample in samples
        if sample["sampleClass"] == "pure_protocol_webshare"
        and sample["stage"] == "final_seq5_seq6_no_success"
    )
    pure_webshare_bootstrap_sid_failures = sum(
        1
        for sample in samples
        if sample["sampleClass"] == "pure_protocol_webshare"
        and sample["stage"] == "bootstrap_response_missing_sid"
    )
    pure_direct_final_failures = sum(
        1
        for sample in samples
        if sample["sampleClass"] == "pure_protocol_direct"
        and sample["stage"] == "final_seq5_seq6_no_success"
    )

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Baseline+reset state-machine induction from browser classifier evidence and fresh pure-protocol reset sampling.",
        "plan": matrix.get("plan"),
        "matrix": abs_path(MATRIX),
        "inputs": [
            abs_path(MATRIX),
            abs_path(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json"),
        ],
        "samples": samples,
        "stateNodes": stage_nodes,
        "transitions": transitions,
        "successOnlyStages": success_only_stages,
        "pureProtocolMissingSuccessStages": pure_missing_success_stages,
        "candidateClientVisibleProxies": candidate_proxies,
        "observations": [
            {
                "id": "pure_webshare_reset_final_no_success",
                "evidence": abs_path(MATRIX),
                "count": pure_webshare_final_failures,
                "meaning": "Valid reset Webshare pure-protocol attempts reach final seq5/seq6 but do not produce collector success.",
            },
            {
                "id": "pure_webshare_reset_proxy_auth_407",
                "evidence": abs_path(MATRIX),
                "count": pure_webshare_proxy_auth_407_failures,
                "meaning": "Reset Webshare pure-protocol attempts do not reach collector bootstrap because proxy CONNECT returns 407 Proxy Authentication Required.",
            },
            {
                "id": "pure_webshare_reset_bootstrap_sid_gap",
                "evidence": abs_path(MATRIX),
                "count": pure_webshare_bootstrap_sid_failures,
                "meaning": "Attempts with collector bootstrap response but missing sid. This must not count proxy-auth failures.",
            },
            {
                "id": "pure_direct_reset_final_no_success",
                "evidence": abs_path(MATRIX),
                "count": pure_direct_final_failures,
                "meaning": "Reset direct pure-protocol attempts reach final seq5/seq6 but do not produce collector success.",
            },
        ],
        "checks": {
            "matrixLoaded": True,
            "sampleCount": len(samples),
            "browserSuccessBaselineCount": sum(1 for s in samples if s["sampleClass"] == "browser_success_webshare"),
            "browserFailureBaselineCount": sum(1 for s in samples if s["sampleClass"] == "browser_failure_webshare"),
            "browserSuccessResetCount": sum(1 for s in samples if s["sampleClass"] == "browser_success_webshare" and s.get("resetCollected")),
            "browserFailureResetCount": sum(1 for s in samples if s["sampleClass"] == "browser_failure_webshare" and s.get("resetCollected")),
            "browserResetWithJsInternalTraceCount": sum(1 for s in reset_browser_samples if ((s.get("checks") or {}).get("jsInternalTraceExists") is True)),
            "pureProtocolWebshareResetCount": sum(1 for s in samples if s["sampleClass"] == "pure_protocol_webshare"),
            "pureProtocolDirectResetCount": sum(1 for s in samples if s["sampleClass"] == "pure_protocol_direct"),
            "pureWebshareFinalNoSuccessCount": pure_webshare_final_failures,
            "pureWebshareProxyAuth407Count": pure_webshare_proxy_auth_407_failures,
            "pureWebshareBootstrapSidFailureCount": pure_webshare_bootstrap_sid_failures,
            "pureDirectFinalNoSuccessCount": pure_direct_final_failures,
            "clientVisibleProxyCount": client_visible_proxy_count,
            "hasOutcomeOnlySuccessStages": any(
                row["candidateType"] == "outcome_or_downstream_result"
                for row in candidate_proxies
            ),
            "hookFeatureSuccessOnlyCount": len(hook_feature_proxies),
            "hookFeatureCounts": hook_feature_counts,
            "readyForSingleTransitionReduction": client_visible_proxy_count > 0,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForSingleTransitionReduction": client_visible_proxy_count > 0,
            "recommendedExperiment": None,
            "nextArtifact": str(RESET_DIR / "reset_single_transition_candidates.json")
            if client_visible_proxy_count > 0
            else str(RESET_DIR / "reset_final_response_class_audit.json"),
            "nextScript": str(ROOT / "tools/build_reset_single_transition_candidates.py")
            if client_visible_proxy_count > 0
            else str(ROOT / "tools/build_reset_final_response_class_audit.py"),
            "reason": (
                "A client-visible proxy candidate exists and should be reduced to a single transition."
                if client_visible_proxy_count > 0
                else "No replayable client-visible proxy was identified. Current valid reset evidence shows both Webshare and direct pure-protocol samples can reach final seq5/seq6 with no collector success; older malformed reset Webshare rows are separately classified as proxy CONNECT 407."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
