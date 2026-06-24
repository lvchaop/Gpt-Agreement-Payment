#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
RESET_DIR = PROTO / "reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"
MANIFEST = RESET_DIR / "reset_sampling_manifest.json"
MATRIX = RESET_DIR / "reset_sampling_matrix.json"
STATE_MACHINE = RESET_DIR / "reset_state_machine.json"
SINGLE_CANDIDATES = RESET_DIR / "reset_single_transition_candidates.json"
OUT = RESET_DIR / "reset_sampling_coverage_audit.json"


REQUIRED_COUNTS = {
    "browser_success_webshare": 2,
    "browser_failure_webshare": 2,
    "pure_protocol_webshare": 3,
    "pure_protocol_direct": 2,
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def abs_path(path: Path) -> str:
    return str(path.resolve())


def count_existing_baseline(matrix: dict[str, Any], class_id: str) -> int:
    rows = ((matrix.get("existingBaselineRows") or {}).get(class_id) or [])
    return len(rows)


def executed_rows(matrix: dict[str, Any], class_id: str) -> list[dict[str, Any]]:
    return [
        row for row in matrix.get("executedRows") or []
        if row.get("sampleClass") == class_id
    ]


def valid_executed_reset_rows(matrix: dict[str, Any], class_id: str) -> list[dict[str, Any]]:
    rows = []
    for row in executed_rows(matrix, class_id):
        if class_id.startswith("browser_"):
            if row.get("countsTowardResetMinimum") is True:
                rows.append(row)
            continue
        classification = row.get("classification") or {}
        if classification.get("completeRunnerReturn") is not True:
            continue
        checks = row.get("checks") or {}
        if class_id == "pure_protocol_webshare":
            if checks.get("bootstrap200") is True and checks.get("progression200Pow") is True:
                rows.append(row)
        elif class_id == "pure_protocol_direct":
            if checks.get("bootstrap200") is True and checks.get("progression200Pow") is True:
                rows.append(row)
    return rows


def class_coverage(matrix: dict[str, Any], class_id: str) -> dict[str, Any]:
    required = REQUIRED_COUNTS[class_id]
    baseline_count = count_existing_baseline(matrix, class_id)
    executed_count = len(executed_rows(matrix, class_id))
    valid_reset_count = len(valid_executed_reset_rows(matrix, class_id))
    is_browser = class_id.startswith("browser_")
    counted_count = valid_reset_count
    return {
        "classId": class_id,
        "requiredResetCount": required,
        "existingBaselineCount": baseline_count,
        "executedResetCount": executed_count,
        "validExecutedResetCount": valid_reset_count,
        "countsTowardResetMinimum": counted_count,
        "minimumMetByResetCollection": counted_count >= required,
        "baselineAvailable": baseline_count >= required,
        "gapCount": max(required - counted_count, 0),
        "usesBrowser": is_browser,
        "reason": (
            "Browser reset runner rows do not yet meet the fresh executed success/failure minimum."
            if is_browser and counted_count < required
            else "Browser reset runner rows meet the fresh executed success/failure minimum."
            if is_browser and counted_count >= required
            else "Pure-protocol reset rows meet minimum with valid complete runner returns."
            if counted_count >= required
            else "Pure-protocol reset rows do not meet minimum."
        ),
    }


def main() -> int:
    manifest = read_json(MANIFEST)
    matrix = read_json(MATRIX)
    state = read_json(STATE_MACHINE)
    single = read_json(SINGLE_CANDIDATES)

    coverage = [class_coverage(matrix, class_id) for class_id in REQUIRED_COUNTS]
    browser_gaps = [row for row in coverage if row["usesBrowser"] and not row["minimumMetByResetCollection"]]
    pure_gaps = [row for row in coverage if not row["usesBrowser"] and not row["minimumMetByResetCollection"]]

    matrix_checks = matrix.get("checks") or {}
    single_checks = single.get("checks") or {}
    checks = {
        "manifestExists": MANIFEST.exists(),
        "matrixExists": MATRIX.exists(),
        "stateMachineExists": STATE_MACHINE.exists(),
        "singleTransitionCandidatesExists": SINGLE_CANDIDATES.exists(),
        "manifestReadyForControlledSampling": ((manifest.get("decision") or {}).get("readyForControlledSampling") is True),
        "matrixResetSamplingComplete": matrix_checks.get("resetSamplingComplete") is True,
        "matrixPureProtocolResetSamplingComplete": matrix_checks.get("pureProtocolResetSamplingComplete") is True,
        "matrixBrowserRunnerMissing": matrix_checks.get("browserRunnerMissing") is True,
        "browserResetCoverageComplete": len(browser_gaps) == 0,
        "pureProtocolResetCoverageComplete": len(pure_gaps) == 0,
        "allResetCoverageComplete": len(browser_gaps) == 0 and len(pure_gaps) == 0,
        "stateMachineClientVisibleProxyCount": ((state.get("checks") or {}).get("clientVisibleProxyCount")),
        "singleTransitionCandidateCount": single_checks.get("singleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    if not checks["browserResetCoverageComplete"]:
        recommended = {
            "kind": "browser_reset_sampling_execution"
            if checks["matrixBrowserRunnerMissing"] is False
            else "sampling_instrumentation",
            "classIds": [row["classId"] for row in browser_gaps],
            "requiredGapCounts": {row["classId"]: row["gapCount"] for row in browser_gaps},
            "reason": (
                "Reset browser runner exists, but fresh executed browser Webshare success/failure samples are still missing."
                if checks["matrixBrowserRunnerMissing"] is False
                else "Reset plan requires fresh browser Webshare success/failure sampling with proxy/IP/session evidence before treating no-candidate Phase 4 as sampled-complete."
            ),
        }
        next_artifact = str(
            (
                RESET_DIR / "browser_sampling_attempts"
                if checks["matrixBrowserRunnerMissing"] is False
                else RESET_DIR / "reset_browser_sampling_runner_plan.json"
            ).resolve()
        )
        next_script = str(
            (
                ROOT / "tools/run_reset_browser_webshare_sampling.py"
                if checks["matrixBrowserRunnerMissing"] is False
                else ROOT / "tools/build_reset_browser_sampling_runner_plan.py"
            ).resolve()
        )
    elif checks["singleTransitionCandidateCount"] == 0:
        recommended = {
            "kind": "new_hook_or_sampling_axis",
            "reason": "Sampling coverage is complete but no client-visible transition candidate exists; add hook coverage before Phase 5.",
        }
        next_artifact = None
        next_script = None
    else:
        recommended = None
        next_artifact = None
        next_script = None

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": abs_path(PLAN),
        "purpose": "Audit whether reset Phase 2 sampling coverage is complete enough to rely on Phase 4 no-candidate conclusions.",
        "inputs": [
            abs_path(MANIFEST),
            abs_path(MATRIX),
            abs_path(STATE_MACHINE),
            abs_path(SINGLE_CANDIDATES),
        ],
        "requiredCounts": REQUIRED_COUNTS,
        "coverage": coverage,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": recommended,
            "nextArtifact": next_artifact,
            "nextScript": next_script,
            "reason": (
                "Reset sampling coverage is complete, but no fresh experiment is ready unless Phase 4 exposes exactly one transition candidate."
                if checks["browserResetCoverageComplete"] and checks["pureProtocolResetCoverageComplete"]
                else "Pure-protocol reset coverage is complete and the browser reset runner is now present, but browser reset coverage is still incomplete because no executed browser Webshare samples count toward the reset minimum."
                if checks["matrixBrowserRunnerMissing"] is False
                else "Pure-protocol reset coverage is complete, but browser reset coverage is not: current browser success/failure rows are existing classifier baselines and browserRunnerMissing=true. Build browser reset sampling instrumentation before treating no-candidate state as sampled-complete."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
