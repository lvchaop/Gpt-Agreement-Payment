#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"
RESET = ROOT / "output/protocol_reverse/reset_plan"
MATRIX = RESET / "reset_sampling_matrix.json"
OUT = RESET / "reset_runtime_js_event_taxonomy.json"

OUTCOME_TOKENS = {
    "oIIoIooo",
    "succeeded",
    "challenge_success",
    "redirectUrl",
    "state=continue",
    '"state":"continue"',
}
KNOWN_NON_INPUT_KINDS = {
    "hook_installed",
    "performance.snapshot",
    "crypto.snapshot",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: str | Path | None):
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for idx, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row["_line"] = idx
            yield row


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def norm_path(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    return f"{parsed.netloc}{parsed.path}"


def text_contains_outcome(text: str) -> bool:
    return any(token in text for token in OUTCOME_TOKENS)


def runtime_features(row: dict[str, Any]) -> set[str]:
    feats: set[str] = set()
    kind = row.get("kind")
    if kind:
        feats.add(f"runtime.kind:{kind}")
    url = str(row.get("url") or "")
    path = norm_path(url)
    if path:
        feats.add(f"runtime.url_path:{path}")
    if kind == "request":
        method = row.get("method")
        if method and path:
            feats.add(f"runtime.request:{method}:{path}")
        post_data = str(row.get("post_data") or "")
        for token in ["continuationToken", "risk/initialize", "risk/verify", "CreateAccount", "HumanCaptcha"]:
            if token in post_data or token in url:
                feats.add(f"runtime.request_token:{token}")
    if kind == "response":
        status = row.get("status")
        if status is not None and path:
            feats.add(f"runtime.response:{status}:{path}")
        body = str(row.get("body") or "")
        for token in ["HumanCaptcha", "state", "continue", "redirectUrl", "riskBlock", "oIIoIooo", "_px3", "_pxde"]:
            if token in body:
                feats.add(f"runtime.response_token:{token}")
    if kind == "console":
        text = str(row.get("text") or "")
        for token in [
            "window.message.recv",
            "hsprotect.captcha.wasm",
            "hsprotect.captcha.worker",
            "hsprotect.captcha.pow",
            "document.cookie",
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "crypto.",
            "performance.",
            "oIIoIooo",
            "succeeded",
            "failed",
            "challenge_success",
        ]:
            if token in text:
                feats.add(f"runtime.console_token:{token}")
    return feats


def js_features(row: dict[str, Any]) -> set[str]:
    feats: set[str] = set()
    kind = str(row.get("kind") or "")
    if kind:
        feats.add(f"js.kind:{kind}")
    origin = str(row.get("origin") or "")
    if origin:
        feats.add(f"js.origin:{origin}")
    if row.get("frameTop") is not None:
        feats.add(f"js.frameTop:{row.get('frameTop')}")
    href = str(row.get("href") or "")
    href_path = norm_path(href)
    if href_path:
        feats.add(f"js.href_path:{href_path}")
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    for key in ["type", "target", "channel", "eventOrigin", "handlerKey", "table", "name", "method"]:
        value = data.get(key)
        if value is not None:
            feats.add(f"js.data.{key}:{value}")
    if data.get("handlerKey") is not None and data.get("args") is not None:
        feats.add(f"js.handlerArgs:{data.get('handlerKey')}:{json.dumps(data.get('args'), ensure_ascii=False)}")
    stack = str(data.get("stack") or "")
    for token in [
        "signup-fluent",
        "fluent-chunk_vendors",
        "captcha.hsprotect.net",
        "iframe.hsprotect.net",
        "collector-pxzc5j78di",
        "main.min.js",
        "captcha.js",
    ]:
        if token in stack or token in href:
            feats.add(f"js.stack_or_href_token:{token}")
    text = json.dumps(row, ensure_ascii=False)
    for token in [
        "oIIoIooo",
        "succeeded",
        "failed",
        "challenge_success",
        "_px3",
        "_pxde",
        "_pxvid",
        "sendBeacon",
        "Worker",
        "worker",
        "wasm",
        "pow",
        "localStorage",
        "sessionStorage",
        "indexedDB",
        "getRandomValues",
        "subtle",
    ]:
        if token in text:
            feats.add(f"js.token:{token}")
    return feats


def bridge_features(path: str | Path | None) -> set[str]:
    feats: set[str] = set()
    if not path:
        return feats
    p = Path(path)
    if not p.exists():
        return feats
    doc = read_json(p)
    feats.add(f"bridge.label:{doc.get('label')}")
    for row in doc.get("source") or []:
        if isinstance(row, dict):
            name = row.get("name")
            domain = row.get("domain")
            if name:
                feats.add(f"bridge.cookie_name:{name}")
            if domain and name:
                feats.add(f"bridge.cookie:{domain}:{name}")
    return feats


def classify_feature(feature: str) -> dict[str, Any]:
    outcome = any(token in feature for token in ["oIIoIooo", "succeeded", "challenge_success", "redirectUrl", "state=continue"])
    if outcome:
        return {"category": "outcome_or_downstream", "preAcceptCandidate": False}
    if any(feature.startswith(prefix) for prefix in ["runtime.request:", "runtime.response:", "runtime.url_path:"]):
        return {"category": "network_surface", "preAcceptCandidate": True}
    if feature.startswith("runtime.response_token:"):
        return {"category": "response_body_surface", "preAcceptCandidate": False}
    if feature.startswith("js.kind:") and feature.removeprefix("js.kind:") in KNOWN_NON_INPUT_KINDS:
        return {"category": "instrumentation_presence", "preAcceptCandidate": False}
    if feature.startswith("bridge.cookie"):
        return {"category": "cookie_bridge_surface", "preAcceptCandidate": True}
    if feature.startswith("js.data.") or feature.startswith("js.handlerArgs:") or feature.startswith("js.token:"):
        return {"category": "js_internal_surface", "preAcceptCandidate": True}
    if feature.startswith("runtime.console_token:"):
        return {"category": "runtime_console_surface", "preAcceptCandidate": True}
    return {"category": "context_surface", "preAcceptCandidate": False}


def sample_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for idx, row in enumerate(matrix.get("executedRows") or []):
        if row.get("countsTowardResetMinimum") is not True:
            continue
        sample_class = row.get("sampleClass")
        if sample_class not in {"browser_success_webshare", "browser_failure_webshare"}:
            continue
        evidence = row.get("evidence") or {}
        classification = row.get("classification") or {}
        rows.append(
            {
                "id": evidence.get("sessionId") or f"{sample_class}_{idx}",
                "sampleClass": sample_class,
                "successLike": classification.get("successLike") is True,
                "stage": classification.get("stage"),
                "runtimeTrace": evidence.get("runtimeTrace") or [],
                "jsInternalTrace": evidence.get("jsInternalTrace") or [],
                "pxCookieBridge": evidence.get("pxCookieBridge") or [],
                "attemptSummary": evidence.get("attemptSummary"),
            }
        )
    return rows


def build() -> dict[str, Any]:
    matrix = read_json(MATRIX)
    samples = sample_rows(matrix)
    feature_samples: dict[str, set[str]] = defaultdict(set)
    feature_counts: Counter[str] = Counter()
    feature_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_docs = []

    for sample in samples:
        sid = sample["id"]
        sample_feature_set: set[str] = set()
        source_counts = Counter()
        for path in sample["runtimeTrace"]:
            for row in iter_jsonl(path):
                source_counts["runtimeRows"] += 1
                for feat in runtime_features(row):
                    sample_feature_set.add(feat)
                    feature_counts[feat] += 1
                    if len(feature_examples[feat]) < 3:
                        feature_examples[feat].append({"sample": sid, "source": str(path), "line": row.get("_line"), "kind": row.get("kind"), "url": row.get("url")})
        for path in sample["jsInternalTrace"]:
            for row in iter_jsonl(path):
                source_counts["jsRows"] += 1
                for feat in js_features(row):
                    sample_feature_set.add(feat)
                    feature_counts[feat] += 1
                    if len(feature_examples[feat]) < 3:
                        feature_examples[feat].append({"sample": sid, "source": str(path), "line": row.get("_line"), "kind": row.get("kind"), "origin": row.get("origin")})
        for path in sample["pxCookieBridge"]:
            for feat in bridge_features(path):
                sample_feature_set.add(feat)
                feature_counts[feat] += 1
                if len(feature_examples[feat]) < 3:
                    feature_examples[feat].append({"sample": sid, "source": str(path), "kind": "px_cookie_bridge"})
        for feat in sample_feature_set:
            feature_samples[feat].add(sid)
        sample_docs.append({**sample, "featureCount": len(sample_feature_set), "sourceCounts": dict(source_counts)})

    success_ids = {s["id"] for s in samples if s["successLike"]}
    failure_ids = {s["id"] for s in samples if not s["successLike"]}
    success_with_js = {s["id"] for s in samples if s["successLike"] and s["jsInternalTrace"]}
    failure_with_js = {s["id"] for s in samples if (not s["successLike"]) and s["jsInternalTrace"]}

    rows = []
    for feat, seen in feature_samples.items():
        meta = classify_feature(feat)
        succ = seen & success_ids
        fail = seen & failure_ids
        succ_js = seen & success_with_js
        fail_js = seen & failure_with_js
        success_only = bool(succ) and not fail
        failure_only = bool(fail) and not succ
        all_success = success_ids and succ == success_ids
        all_failure = failure_ids and fail == failure_ids
        all_success_with_js = success_with_js and succ_js == success_with_js
        absent_failure_with_js = not fail_js
        candidate = (
            success_only
            and meta["preAcceptCandidate"] is True
            and meta["category"] not in {"outcome_or_downstream", "instrumentation_presence"}
        )
        rows.append(
            {
                "feature": feat,
                "category": meta["category"],
                "preAcceptCandidate": meta["preAcceptCandidate"],
                "successCount": len(succ),
                "failureCount": len(fail),
                "successWithJsCount": len(succ_js),
                "failureWithJsCount": len(fail_js),
                "successOnly": success_only,
                "failureOnly": failure_only,
                "allSuccess": bool(all_success),
                "allFailure": bool(all_failure),
                "allSuccessWithJs": bool(all_success_with_js),
                "absentFailureWithJs": absent_failure_with_js,
                "candidateClientVisibleProxy": candidate,
                "count": feature_counts[feat],
                "examples": feature_examples[feat],
            }
        )
    rows.sort(key=lambda r: (not r["candidateClientVisibleProxy"], r["category"], -r["successCount"], r["feature"]))
    candidates = [r for r in rows if r["candidateClientVisibleProxy"]]
    strong_js_candidates = [
        r for r in rows
        if r["preAcceptCandidate"] and r["successWithJsCount"] and r["allSuccessWithJs"] and r["absentFailureWithJs"]
    ]

    checks = {
        "matrixExists": MATRIX.exists(),
        "countedBrowserSampleCount": len(samples),
        "countedSuccessCount": len(success_ids),
        "countedFailureCount": len(failure_ids),
        "successWithJsTraceCount": len(success_with_js),
        "failureWithJsTraceCount": len(failure_with_js),
        "featureCount": len(rows),
        "candidateClientVisibleProxyCount": len(candidates),
        "strongJsContrastCandidateCount": len(strong_js_candidates),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Route A reset-only taxonomy over counted browser reset runtime traces, JS internal traces, and px cookie bridge artifacts.",
        "inputs": {
            "matrix": str(MATRIX),
            "samples": sample_docs,
        },
        "checks": checks,
        "candidateClientVisibleProxies": candidates,
        "strongJsContrastCandidates": strong_js_candidates,
        "featureRowsSample": rows[:200],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None if not candidates else {"kind": "candidate_reduction", "artifact": str(OUT)},
            "nextArtifact": str(OUT),
            "nextScript": None if not candidates else str(ROOT / "tools/build_reset_runtime_js_candidate_reduction.py"),
            "reason": (
                "Reset runtime/JS taxonomy found client-visible proxy candidates; reduce them before any Phase 5 experiment."
                if candidates
                else "Reset runtime/JS taxonomy found no success-only pre-accept client-visible proxy candidate."
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
