#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
MANIFEST = RESET / "reset_route_b_resampling_manifest.json"
OUT = RESET / "reset_route_b_resampling_matrix.json"
ATTEMPT_DIR = RESET / "route_b_browser_sampling_attempts"

ROUTE_B_CLASSES = {
    "route_b_browser_success_webshare": "browser_success_webshare",
    "route_b_browser_failure_webshare": "browser_failure_webshare",
}
ROUTE_B_HOOK_KINDS = [
    "webkit.messageHandlers.pxMobileData.wrap",
    "webkit.messageHandlers.pxMobileData.postMessage",
    "OfflineAudioContext.wrap",
    "OfflineAudioContext.new",
    "OfflineAudioContext.startRendering",
    "OfflineAudioContext.startRendering.resolved",
    "serviceWorker.snapshot",
    "serviceWorker.register",
    "caches.wrap",
    "caches.open",
    "caches.match",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def scan_hook_kinds(paths: list[str]) -> dict[str, Any]:
    counts = {kind: 0 for kind in ROUTE_B_HOOK_KINDS}
    examples: list[dict[str, Any]] = []
    for text in paths:
        path = Path(text)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = str(item.get("kind") or "")
                for wanted in ROUTE_B_HOOK_KINDS:
                    if kind == wanted or kind.startswith(wanted):
                        counts[wanted] += 1
                        if len(examples) < 40:
                            examples.append({"path": str(path), "line": line_no, "kind": kind, "data": item.get("data")})
    observed = [k for k, v in counts.items() if v > 0]
    return {
        "counts": counts,
        "observed": observed,
        "missing": [k for k, v in counts.items() if v == 0],
        "examples": examples,
    }


def run_cmd(cmd: list[str], timeout: float) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False, timeout=timeout)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "startedAt": started,
        "endedAt": time.time(),
        "stdoutTail": proc.stdout[-8000:],
        "stderrTail": proc.stderr[-8000:],
        "parsedJson": json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else None,
    }


def planned_row(class_id: str, idx: int) -> dict[str, Any]:
    mapped = ROUTE_B_CLASSES[class_id]
    patch_apply = "1"
    cmd = [
        "python3",
        "tools/run_reset_browser_webshare_sampling.py",
        "--sample-class",
        mapped,
        "--count",
        "1",
        "--out-dir",
        str(ATTEMPT_DIR),
        "--hsprotect-patch-apply",
        patch_apply,
    ]
    return {
        "sampleClass": class_id,
        "mappedRunnerSampleClass": mapped,
        "plannedIndex": idx,
        "status": "planned_not_run",
        "command": {
            "cmd": cmd,
            "executeByAdding": "--execute",
            "freshSessionGeneratedByRunner": True,
        },
        "routeBHookKindsRequired": ROUTE_B_HOOK_KINDS,
        "instrumentationControls": {
            "OUTLOOK_HSPROTECT_JS_PATCH_APPLY": patch_apply,
            "reason": "Route B value taxonomy requires success/failure samples under the same hsprotect JS patch application setting.",
        },
        "countsTowardFinalPureProtocolSuccess": False,
    }


def load_attempts() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(ATTEMPT_DIR.glob("browser_sampling_*.json")):
        doc = read_json(path)
        mapped = str(doc.get("sampleClass") or "")
        route_class = next((k for k, v in ROUTE_B_CLASSES.items() if v == mapped), None)
        if not route_class:
            continue
        artifacts = doc.get("artifacts") or {}
        hook_scan = scan_hook_kinds([str(p) for p in artifacts.get("jsInternalTrace") or []])
        rows.append(
            {
                "sampleClass": route_class,
                "mappedRunnerSampleClass": mapped,
                "status": "executed" if (doc.get("checks") or {}).get("executeRequested") else "dry_run_not_executed",
                "attemptSummary": str(path),
                "sessionId": doc.get("sessionId"),
                "classification": doc.get("classification"),
                "artifacts": artifacts,
                "routeBHookScan": hook_scan,
                "countsTowardRouteBResampling": bool(hook_scan["observed"]) and (doc.get("checks") or {}).get("executeRequested") is True,
            }
        )
    return rows


def build_matrix(executed_now: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    manifest = read_json(MANIFEST)
    sample_classes = manifest.get("sampleClasses") or []
    planned = []
    for sample in sample_classes:
        class_id = sample.get("classId")
        minimum = int(sample.get("minimumCount") or 0)
        for idx in range(minimum):
            planned.append(planned_row(class_id, idx))
    executed = load_attempts()
    if executed_now:
        executed.extend(executed_now)
    class_summary = []
    for sample in sample_classes:
        class_id = sample.get("classId")
        minimum = int(sample.get("minimumCount") or 0)
        expected_success = class_id == "route_b_browser_success_webshare"
        count = 0
        for row in executed:
            if row.get("sampleClass") != class_id or row.get("countsTowardRouteBResampling") is not True:
                continue
            if ((row.get("classification") or {}).get("successLike") is True) != expected_success:
                continue
            attempt = read_json(Path(row.get("attemptSummary"))) if row.get("attemptSummary") else {}
            env = attempt.get("envOverlay") or {}
            if env.get("OUTLOOK_HSPROTECT_JS_PATCH_APPLY") != "1":
                continue
            count += 1
        class_summary.append({"classId": class_id, "minimumCount": minimum, "collectedCount": count, "minimumSatisfied": count >= minimum})
    checks = {
        "manifestLoaded": bool(manifest),
        "plannedRowCount": len(planned),
        "executedRowCount": len(executed),
        "routeBResamplingComplete": all(row["minimumSatisfied"] for row in class_summary),
        "readyForLifecycleContrastAudit": all(row["minimumSatisfied"] for row in class_summary),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": manifest.get("plan"),
        "manifest": str(MANIFEST),
        "purpose": "Route B browser evidence resampling matrix for newly added lifecycle/fingerprint hooks.",
        "classSummary": class_summary,
        "plannedRows": planned,
        "executedRows": executed,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForLifecycleContrastAudit": checks["readyForLifecycleContrastAudit"],
            "recommendedExperiment": None,
            "nextArtifact": str(RESET / "reset_route_b_lifecycle_contrast_audit.json") if checks["readyForLifecycleContrastAudit"] else str(OUT),
            "nextScript": str(ROOT / "tools/build_reset_route_b_lifecycle_contrast_audit.py") if checks["readyForLifecycleContrastAudit"] else str(ROOT / "tools/run_reset_route_b_browser_resampling.py"),
            "reason": "Route B resampling is browser evidence only; it does not authorize pure-protocol Phase 5.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or execute Route B browser resampling matrix.")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--sample-class", choices=sorted(ROUTE_B_CLASSES), action="append")
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    executed_now = []
    if args.execute:
        classes = args.sample_class or sorted(ROUTE_B_CLASSES)
        for class_id in classes:
            row = planned_row(class_id, 0)
            cmd = list((row["command"] or {}).get("cmd") or []) + ["--execute"]
            result = run_cmd(cmd, args.timeout)
            row["status"] = "executed_command"
            row["execution"] = result
            executed_now.append(row)
    matrix = build_matrix(executed_now)
    write_json(OUT, matrix)
    print(json.dumps({"json": str(OUT), "checks": matrix["checks"], "decision": matrix["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
