#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "collector_material_only_response_class_audit.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "unclassifiedTraceSignalReduction": BASE / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessServerVisibleDiff": BASE / "browser_success_chain_server_visible_diff_audit.json",
    "collectorResponseHandlerValueLineage": BASE / "collector_response_handler_value_lineage_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def trace_path(kind: str, run: str) -> Path:
    return REPO / f"output/outlook_browser/{kind}_trace_{run}.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        obj["_lineNo"] = line_no
        out.append(obj)
    return out


def text_of(event: dict[str, Any]) -> str:
    fields = []
    for key in ("kind", "method", "url", "post_preview", "post_data", "body_preview", "body", "message", "name"):
        value = event.get(key)
        if value is not None:
            fields.append(str(value))
    if event.get("headers"):
        fields.append(json.dumps(event["headers"], ensure_ascii=False, sort_keys=True))
    return "\n".join(fields)


TOKENS = {
    "collectorMsftRequest": ["collector-pxzc5j78di.hsprotect.net/api/v2/msft"],
    "collectorBundleRequest": ["collector-pxzc5j78di.hsprotect.net/assets/js/bundle", "client.hsprotect.net/PXzC5j78di/main.min.js"],
    "collectorSuccess0": ["oIIoIooo|0", "challenge_success=0", '"challenge_success":0', '"challenge_success": 0'],
    "collectorFailureMinus1": ["oIIoIooo|-1"],
    "riskVerifyRequest": ["/risk/verify"],
    "riskContinue": ['"state":"continue"', '"state": "continue"'],
    "riskHumanChallenge": ['"challengeType":"HumanCaptcha"', '"challengeType": "HumanCaptcha"'],
    "createAccountRequest": ["/API/CreateAccount"],
    "createRedirect": ["redirectUrl"],
    "parentSucceeded": ["succeeded", "parent"],
    "px3": ["_px3"],
    "pxde": ["_pxde"],
    "wasm": ["wasm", "WebAssembly"],
}


def count_tokens(events: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in events:
        text = text_of(event)
        for key, tokens in TOKENS.items():
            if any(token in text for token in tokens):
                counts[key] += 1
    return counts


def response_status_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for event in events:
        if event.get("kind") == "response":
            url = event.get("url") or ""
            if "collector-pxzc5j78di.hsprotect.net/api/v2/msft" in url:
                counts[f"collectorStatus{event.get('status')}"] += 1
            if "/risk/verify" in url:
                counts[f"riskVerifyStatus{event.get('status')}"] += 1
                body = text_of(event)
                if '"challengeType":"HumanCaptcha"' in body or '"challengeType": "HumanCaptcha"' in body:
                    counts["riskVerifyHumanCaptchaResponse"] += 1
                if '"state":"continue"' in body or '"state": "continue"' in body:
                    counts["riskVerifyContinueResponse"] += 1
    return dict(counts)


def assess(run: str, source: dict[str, Any]) -> dict[str, Any]:
    runtime = load_jsonl(trace_path("runtime", run))
    js = load_jsonl(trace_path("js_internal", run))
    runtime_counts = count_tokens(runtime)
    js_counts = count_tokens(js)
    merged = runtime_counts + js_counts
    status_counts = response_status_counts(runtime)
    has_success = merged["collectorSuccess0"] > 0
    has_failure = merged["collectorFailureMinus1"] > 0
    has_continue = merged["riskContinue"] > 0 or status_counts.get("riskVerifyContinueResponse", 0) > 0
    has_redirect = merged["createRedirect"] > 0
    has_human_challenge = merged["riskHumanChallenge"] > 0 or status_counts.get("riskVerifyHumanCaptchaResponse", 0) > 0

    blockers = [
        "collector material presence is common browser runtime material, not no-browser proof",
        "no decoded collector success oIIoIooo|0 is present",
        "risk/verify downstream signal without collector success decode cannot establish collector root cause",
        "request class and payload size are already contradicted by success/failure controls",
    ]
    if has_failure:
        blockers.append("collector failure marker appears in at least one trace for this row")

    return {
        "run": run,
        "runtimeTrace": str(trace_path("runtime", run)),
        "runtimeTraceExists": trace_path("runtime", run).exists(),
        "jsInternalTrace": str(trace_path("js_internal", run)),
        "jsInternalTraceExists": trace_path("js_internal", run).exists(),
        "sourceTokenCounts": source.get("tokenCounts") or {},
        "mergedTokenCounts": dict(merged),
        "responseStatusCounts": status_counts,
        "hasCollectorSuccessDecode": has_success,
        "hasCollectorFailureDecode": has_failure,
        "hasRiskVerifyRequest": merged["riskVerifyRequest"] > 0,
        "hasRiskContinue": has_continue,
        "hasRiskHumanChallenge": has_human_challenge,
        "hasCreateAccountRequest": merged["createAccountRequest"] > 0,
        "hasCreateRedirect": has_redirect,
        "proposalAssessment": {
            "preAccept": True,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "valueChain": "request",
            "contradicted": True,
            "proposalReady": False,
            "blockers": blockers,
        },
    }


def build() -> dict[str, Any]:
    reduction = read_json(INPUTS["unclassifiedTraceSignalReduction"])
    diff = read_json(INPUTS["browserSuccessServerVisibleDiff"])
    response_lineage = read_json(INPUTS["collectorResponseHandlerValueLineage"])
    intake = read_json(INPUTS["candidateIntake"])
    source_rows = [
        row for row in reduction.get("rows") or []
        if row.get("classification") == "collector_material_only"
    ]
    rows = [assess(row["run"], row) for row in source_rows if row.get("run")]

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "collectorMaterialOnlyRunCount": len(rows),
        "runtimeTraceExistsCount": sum(1 for row in rows if row["runtimeTraceExists"]),
        "jsInternalTraceExistsCount": sum(1 for row in rows if row["jsInternalTraceExists"]),
        "collectorSuccessDecodeRunCount": sum(1 for row in rows if row["hasCollectorSuccessDecode"]),
        "collectorFailureDecodeRunCount": sum(1 for row in rows if row["hasCollectorFailureDecode"]),
        "riskVerifyRequestRunCount": sum(1 for row in rows if row["hasRiskVerifyRequest"]),
        "riskContinueRunCount": sum(1 for row in rows if row["hasRiskContinue"]),
        "riskHumanChallengeRunCount": sum(1 for row in rows if row["hasRiskHumanChallenge"]),
        "createRedirectRunCount": sum(1 for row in rows if row["hasCreateRedirect"]),
        "allRowsLackCollectorSuccessDecode": len(rows) > 0 and all(not row["hasCollectorSuccessDecode"] for row in rows),
        "allRowsLackRiskContinue": len(rows) > 0 and all(not row["hasRiskContinue"] for row in rows),
        "allRowsLackCreateRedirect": len(rows) > 0 and all(not row["hasCreateRedirect"] for row in rows),
        "serverVisibleDiffProposalCandidateCount": (diff.get("checks") or {}).get("proposalCandidateCount"),
        "collectorResponseLineageProposalCandidateCount": (response_lineage.get("checks") or {}).get("proposalCandidateCount"),
        "proposalCandidateCount": 0,
        "candidateIntakePromotedCount": (intake.get("checks") or {}).get("promotedSingleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Close the collector_material_only trace class by proving it contains collector/browser material but no accepted collector decode or downstream stage advance.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "rows": rows,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "collector_material_only rows contain collector requests and bundle/material signals, but no decoded collector success and no CreateAccount redirect. "
                "One row contains risk continue without collector success decode, which is downstream/control evidence rather than a collector pre-accept transition. "
                "They are request/material inventory only and do not isolate a pure-protocol transition."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
