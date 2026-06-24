#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUTLOOK = REPO / "output/outlook_browser"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "local_trace_evidence_freshness_audit.json"

INPUTS = {
    "currentPlan": REPO / "docs/pure-protocol-human-evidence-first-current-plan.md",
    "classifierSummary": PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json",
    "crossSampleMatrix": BASE / "cross_sample_server_state_proxy_matrix.json",
    "serverInternalGapEvidenceInventory": BASE / "server_internal_gap_evidence_inventory.json",
    "remainingBoundaryProposalGate": BASE / "remaining_boundary_proposal_gate_audit.json",
}


TOKENS = {
    "parentSucceeded": ['"succeeded"', "'succeeded'"],
    "parentFailed": ['"failed"', "'failed'"],
    "collectorSuccess0": ["oIIoIooo|0"],
    "collectorFailureMinus1": ["oIIoIooo|-1"],
    "riskContinue": ['"state":"continue"', '"state": "continue"'],
    "createRedirect": ["redirectUrl"],
    "collectorMsft": ["collector-pxzc5j78di.hsprotect.net/api/v2/msft"],
    "collectorBundle": ["collector-pxzc5j78di.hsprotect.net/assets/js/bundle"],
    "px3": ["_px3"],
    "pxde": ["_pxde"],
    "wasm": ["wasm", "WebAssembly"],
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def run_from_prefixed(path: Path, prefix: str, suffix: str) -> str:
    name = path.name
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name.removesuffix(suffix)


def trace_classification_run(path: Path) -> str:
    return run_from_prefixed(path, "trace_classification_", ".json")


def scan_text(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    token_counts = {
        name: sum(text.count(token) for token in tokens)
        for name, tokens in TOKENS.items()
    }
    high_value = (
        token_counts["parentSucceeded"] > 0
        or token_counts["collectorSuccess0"] > 0
        or token_counts["riskContinue"] > 0
        or token_counts["createRedirect"] > 0
    )
    full_browser_success_like = (
        token_counts["riskContinue"] > 0
        and token_counts["createRedirect"] > 0
        and (token_counts["parentSucceeded"] > 0 or token_counts["collectorSuccess0"] > 0)
    )
    collector_material_like = token_counts["collectorMsft"] > 0 or token_counts["collectorBundle"] > 0
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else None,
        "tokenCounts": token_counts,
        "hasHighValueSignal": high_value,
        "hasFullBrowserSuccessLikeSignal": full_browser_success_like,
        "hasCollectorMaterialSignal": collector_material_like,
    }


def build() -> dict[str, Any]:
    runtime_paths = sorted(OUTLOOK.glob("runtime_trace_*.jsonl"))
    js_paths = sorted(OUTLOOK.glob("js_internal_trace_*.jsonl"))
    classification_paths = [
        p for p in sorted(PROTO.glob("trace_classification_*.json"))
        if p.name != "trace_classification_summary.json"
    ]
    runtime_by_run = {run_from_prefixed(p, "runtime_trace_", ".jsonl"): p for p in runtime_paths}
    js_by_run = {run_from_prefixed(p, "js_internal_trace_", ".jsonl"): p for p in js_paths}
    classified_runs = {trace_classification_run(p) for p in classification_paths}

    cross_sample = load_json(INPUTS["crossSampleMatrix"])
    cross_sample_runs = {
        row.get("run")
        for row in cross_sample.get("sampleSummaries") or []
        if row.get("run")
    }
    inventory = load_json(INPUTS["serverInternalGapEvidenceInventory"])
    inventory_checks = inventory.get("checks") or {}

    all_runs = sorted(set(runtime_by_run) | set(js_by_run))
    unclassified_runs = [run for run in all_runs if run not in classified_runs]
    not_in_cross_sample_runs = [run for run in all_runs if run not in cross_sample_runs]

    unclassified_rows = []
    for run in unclassified_runs:
        runtime_scan = scan_text(runtime_by_run[run]) if run in runtime_by_run else None
        js_scan = scan_text(js_by_run[run]) if run in js_by_run else None
        row = {
            "run": run,
            "hasRuntimeTrace": run in runtime_by_run,
            "hasJsInternalTrace": run in js_by_run,
            "runtime": runtime_scan,
            "js": js_scan,
        }
        row["hasHighValueSignal"] = any(
            scan and scan.get("hasHighValueSignal") for scan in [runtime_scan, js_scan]
        )
        row["hasFullBrowserSuccessLikeSignal"] = any(
            scan and scan.get("hasFullBrowserSuccessLikeSignal") for scan in [runtime_scan, js_scan]
        )
        row["hasCollectorMaterialSignal"] = any(
            scan and scan.get("hasCollectorMaterialSignal") for scan in [runtime_scan, js_scan]
        )
        unclassified_rows.append(row)

    high_value_rows = [row for row in unclassified_rows if row["hasHighValueSignal"]]
    full_browser_like_rows = [row for row in unclassified_rows if row["hasFullBrowserSuccessLikeSignal"]]
    collector_material_rows = [row for row in unclassified_rows if row["hasCollectorMaterialSignal"]]

    # Browser traces can provide comparison evidence, but they are not no-browser
    # proof. Promotion still requires a later reducer to map them to one
    # request/cookie/risk/verify transition.
    proposal_worthy_now = []

    checks = {
        "currentPlanExists": INPUTS["currentPlan"].exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "runtimeTraceCount": len(runtime_paths),
        "jsTraceCount": len(js_paths),
        "allLocalTraceRunCount": len(all_runs),
        "classificationFileCount": len(classification_paths),
        "classifiedRunCount": len(classified_runs),
        "crossSampleRunCount": len(cross_sample_runs),
        "inventoryRuntimeTraceCount": inventory_checks.get("runtimeTraceCount"),
        "inventoryJsTraceCount": inventory_checks.get("jsTraceCount"),
        "inventoryRuntimeCountMatchesCurrent": inventory_checks.get("runtimeTraceCount") == len(runtime_paths),
        "inventoryJsCountMatchesCurrent": inventory_checks.get("jsTraceCount") == len(js_paths),
        "unclassifiedRunCount": len(unclassified_runs),
        "notInCrossSampleRunCount": len(not_in_cross_sample_runs),
        "unclassifiedHighValueSignalRunCount": len(high_value_rows),
        "unclassifiedFullBrowserSuccessLikeRunCount": len(full_browser_like_rows),
        "unclassifiedCollectorMaterialRunCount": len(collector_material_rows),
        "proposalWorthyNowCount": len(proposal_worthy_now),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    has_new_offline_work = len(high_value_rows) > 0 or len(collector_material_rows) > 0
    decision = {
        "goalComplete": False,
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "nextArtifact": str(BASE / "unclassified_trace_signal_reduction_audit.json") if has_new_offline_work else None,
        "nextScript": str(REPO / "tools/build_unclassified_trace_signal_reduction_audit.py") if has_new_offline_work else None,
        "reason": (
            "Unclassified local browser traces contain high-value or collector material signals; reduce them offline before any fresh network experiment."
            if has_new_offline_work
            else "Current local trace files do not expose an unclassified high-value evidence entrance."
        ),
    }

    return {
        "artifact": str(OUT),
        "purpose": "Check whether local runtime/js trace evidence has drifted beyond the classified/cross-sample evidence used by the current proposal gate.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "counts": {
            "runtimeTraceCount": len(runtime_paths),
            "jsTraceCount": len(js_paths),
            "allLocalTraceRunCount": len(all_runs),
            "classifiedRunCount": len(classified_runs),
            "crossSampleRunCount": len(cross_sample_runs),
        },
        "unclassifiedRows": unclassified_rows,
        "unclassifiedHighValueRows": high_value_rows[:50],
        "unclassifiedFullBrowserSuccessLikeRows": full_browser_like_rows[:50],
        "unclassifiedCollectorMaterialRows": collector_material_rows[:50],
        "checks": checks,
        "decision": decision,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
