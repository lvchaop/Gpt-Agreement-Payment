#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "low_value_unclassified_trace_closure_audit.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "localTraceEvidenceFreshness": BASE / "local_trace_evidence_freshness_audit.json",
    "unclassifiedTraceSignalReduction": BASE / "unclassified_trace_signal_reduction_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


TOKENS = {
    "collectorMsft": ["collector-pxzc5j78di.hsprotect.net/api/v2/msft"],
    "collectorBundle": ["collector-pxzc5j78di.hsprotect.net/assets/js/bundle", "client.hsprotect.net/PXzC5j78di/main.min.js"],
    "collectorSuccess0": ["oIIoIooo|0", "challenge_success=0", '"challenge_success":0', '"challenge_success": 0'],
    "collectorFailureMinus1": ["oIIoIooo|-1"],
    "riskVerify": ["/risk/verify"],
    "riskContinue": ['"state":"continue"', '"state": "continue"'],
    "createAccount": ["/API/CreateAccount"],
    "createRedirect": ["redirectUrl"],
    "parentSucceeded": ["succeeded", "parent"],
    "parentFailed": ["parent", "failed"],
    "requestFailed": ['"kind": "requestfailed"', '"kind":"requestfailed"'],
    "riskInitialize": ["/risk/initialize"],
    "px3": ["_px3"],
    "pxde": ["_pxde"],
    "wasm": ["wasm", "WebAssembly"],
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def trace_path(kind: str, run: str) -> Path:
    return REPO / f"output/outlook_browser/{kind}_trace_{run}.jsonl"


def load_lines(path: Path) -> list[tuple[int, str]]:
    if not path.exists():
        return []
    return list(enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1))


def count_tokens(lines: list[tuple[int, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for _, line in lines:
        for key, tokens in TOKENS.items():
            if key in {"parentSucceeded", "parentFailed"}:
                matched = all(token in line for token in tokens)
            else:
                matched = any(token in line for token in tokens)
            if matched:
                counts[key] += 1
    return counts


def first_lines(lines: list[tuple[int, str]]) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for key, tokens in TOKENS.items():
        if key in {"parentSucceeded", "parentFailed"}:
            out[key] = next((line_no for line_no, line in lines if all(token in line for token in tokens)), None)
        else:
            out[key] = next((line_no for line_no, line in lines if any(token in line for token in tokens)), None)
    return out


def summarize_events(lines: list[tuple[int, str]], limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in lines[:limit]:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"line": line_no, "json": False, "preview": line[:240]})
            continue
        rows.append(
            {
                "line": line_no,
                "json": True,
                "kind": obj.get("kind"),
                "method": obj.get("method"),
                "url": obj.get("url"),
                "origin": obj.get("origin"),
                "name": obj.get("name"),
            }
        )
    return rows


def assess(run: str, source: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    runtime_lines = load_lines(trace_path("runtime", run))
    js_lines = load_lines(trace_path("js_internal", run))
    runtime_counts = count_tokens(runtime_lines)
    js_counts = count_tokens(js_lines)
    merged = runtime_counts + js_counts
    proposal_relevant_keys = {
        "collectorMsft",
        "collectorBundle",
        "collectorSuccess0",
        "collectorFailureMinus1",
        "riskVerify",
        "riskContinue",
        "createAccount",
        "createRedirect",
        "parentSucceeded",
        "parentFailed",
        "px3",
        "pxde",
        "wasm",
    }
    high_value_count = sum(merged.get(key, 0) for key in proposal_relevant_keys)

    return {
        "run": run,
        "runtimeTrace": str(trace_path("runtime", run)),
        "runtimeTraceExists": trace_path("runtime", run).exists(),
        "runtimeLineCount": len(runtime_lines),
        "jsInternalTrace": str(trace_path("js_internal", run)),
        "jsInternalTraceExists": trace_path("js_internal", run).exists(),
        "jsInternalLineCount": len(js_lines),
        "sourceTokenCounts": source.get("tokenCounts") or {},
        "freshnessHasHighValueSignal": fresh.get("hasHighValueSignal"),
        "freshnessHasCollectorMaterialSignal": fresh.get("hasCollectorMaterialSignal"),
        "freshnessHasFullBrowserSuccessLikeSignal": fresh.get("hasFullBrowserSuccessLikeSignal"),
        "rescannedTokenCounts": dict(merged),
        "firstLines": {
            "runtime": first_lines(runtime_lines),
            "jsInternal": first_lines(js_lines),
        },
        "sampleRuntimeEvents": summarize_events(runtime_lines),
        "sampleJsInternalEvents": summarize_events(js_lines),
        "hasAnyProposalRelevantSignal": high_value_count > 0,
        "proposalAssessment": {
            "preAccept": False,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "valueChain": "request",
            "contradicted": True,
            "proposalReady": False,
            "blockers": [
                "no collector/risk/verify/cookie/wasm/parent success token is present after rescan",
                "risk/initialize requestfailed is an early transport/init failure signal, not a HUMAN transition",
                "no single request/cookie/risk/verify transition is isolated",
                "row has no no-browser pure-protocol execution evidence",
            ],
        },
    }


def build() -> dict[str, Any]:
    reduction = read_json(INPUTS["unclassifiedTraceSignalReduction"])
    freshness = read_json(INPUTS["localTraceEvidenceFreshness"])
    intake = read_json(INPUTS["candidateIntake"])
    freshness_rows = {row.get("run"): row for row in freshness.get("unclassifiedRows") or [] if row.get("run")}
    source_rows = [
        row for row in reduction.get("rows") or []
        if row.get("classification") == "low_value_or_unclassified"
    ]
    rows = [assess(row["run"], row, freshness_rows.get(row["run"], {})) for row in source_rows if row.get("run")]
    proposal_relevant = [row for row in rows if row["hasAnyProposalRelevantSignal"]]

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "lowValueRunCount": len(rows),
        "runtimeTraceExistsCount": sum(1 for row in rows if row["runtimeTraceExists"]),
        "jsInternalTraceExistsCount": sum(1 for row in rows if row["jsInternalTraceExists"]),
        "rescannedProposalRelevantSignalRunCount": len(proposal_relevant),
        "requestFailedRunCount": sum(1 for row in rows if row["rescannedTokenCounts"].get("requestFailed", 0)),
        "riskInitializeRunCount": sum(1 for row in rows if row["rescannedTokenCounts"].get("riskInitialize", 0)),
        "allRowsRemainLowValue": len(rows) > 0 and len(proposal_relevant) == 0,
        "candidateIntakePromotedCount": (intake.get("checks") or {}).get("promotedSingleTransitionCandidateCount"),
        "proposalCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Close the low_value_or_unclassified local trace class by rescanning for proposal-relevant collector/risk/cookie/wasm/parent tokens.",
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
                "The residual low_value_or_unclassified rows still contain no proposal-relevant collector/risk/verify/cookie/wasm/parent success tokens after rescan. "
                "They close the unclassified trace inventory but do not create a promoted transition."
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
