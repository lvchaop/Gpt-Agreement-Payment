#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET_DIR = ROOT / "output/protocol_reverse/reset_plan"
PLAN = RESET_DIR / "reset_browser_sampling_runner_plan.json"
ATTEMPT_DIR = RESET_DIR / "browser_sampling_attempts"
RUNNER = ROOT / "tools/run_reset_browser_webshare_sampling.py"
OUT = RESET_DIR / "reset_browser_sampling_runner_audit.json"
RESET_PLAN = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def abs_path(path: Path) -> str:
    return str(path.resolve())


def attempt_rows() -> list[dict[str, Any]]:
    rows = []
    for path in sorted(ATTEMPT_DIR.glob("browser_sampling_*.json")):
        doc = read_json(path)
        decision = doc.get("decision") or {}
        checks = doc.get("checks") or {}
        config_evidence = doc.get("configEvidence") or {}
        config_path_text = str(config_evidence.get("attemptConfig") or "")
        config_path = Path(config_path_text) if config_path_text else None
        config_doc = read_json(config_path) if config_path and config_path.is_file() else {}
        proxy_meta = config_doc.get("proxy_meta") if isinstance(config_doc.get("proxy_meta"), dict) else {}
        command = doc.get("command") or []
        session_id = doc.get("sessionId")
        config_proxy = str(config_doc.get("proxy") or "")
        rows.append(
            {
                "path": abs_path(path),
                "sampleClass": doc.get("sampleClass"),
                "sessionId": session_id,
                "executeRequested": checks.get("executeRequested") is True,
                "stage": doc.get("finalStage"),
                "countsTowardResetMinimum": decision.get("countsTowardResetMinimum") is True,
                "runtimeTraceCaptured": checks.get("runtimeTraceCaptured") is True,
                "jsInternalTraceCaptured": checks.get("jsInternalTraceCaptured") is True,
                "freshSession": doc.get("freshSession") is True,
                "countsTowardFinalPureProtocolSuccess": doc.get("countsTowardFinalPureProtocolSuccess") is True,
                "attemptConfigWritten": checks.get("attemptConfigWritten") is True,
                "commandUsesAttemptConfig": checks.get("commandUsesAttemptConfig") is True,
                "attemptConfig": str(config_path) if config_path and config_path.is_file() else None,
                "configProxyHasSession": bool(session_id) and str(session_id) in config_proxy,
                "configProxyMetaSessionMatches": proxy_meta.get("sessionUser") == session_id,
                "command": command,
            }
        )
    return rows


def main() -> int:
    plan = read_json(PLAN)
    rows = attempt_rows()
    executed = [row for row in rows if row["executeRequested"]]
    counted = [row for row in rows if row["countsTowardResetMinimum"]]
    success_counted = [row for row in counted if row["sampleClass"] == "browser_success_webshare"]
    failure_counted = [row for row in counted if row["sampleClass"] == "browser_failure_webshare"]
    config_rows = [row for row in rows if row["attemptConfig"]]

    checks = {
        "runnerPlanExists": PLAN.exists(),
        "runnerExists": RUNNER.exists(),
        "attemptDirExists": ATTEMPT_DIR.exists(),
        "dryRunAttemptCount": len([row for row in rows if not row["executeRequested"]]),
        "executedAttemptCount": len(executed),
        "countedResetAttemptCount": len(counted),
        "countedBrowserSuccessResetCount": len(success_counted),
        "countedBrowserFailureResetCount": len(failure_counted),
        "attemptWithConfigCount": len(config_rows),
        "attemptMissingConfigCount": len(rows) - len(config_rows),
        "allAttemptsFreshSession": bool(rows) and all(row["freshSession"] for row in rows),
        "allNewAttemptsHaveConfigWritten": bool(config_rows) and all(row["attemptConfigWritten"] for row in config_rows),
        "allNewCommandsUseAttemptConfig": bool(config_rows) and all(row["commandUsesAttemptConfig"] for row in config_rows),
        "allNewConfigsProxyHasSession": bool(config_rows) and all(row["configProxyHasSession"] for row in config_rows),
        "allNewConfigProxyMetaSessionMatches": bool(config_rows) and all(row["configProxyMetaSessionMatches"] for row in config_rows),
        "noAttemptCountsTowardFinalPureProtocolSuccess": all(not row["countsTowardFinalPureProtocolSuccess"] for row in rows),
        "readyToExecuteBrowserSampling": RUNNER.exists() and PLAN.exists(),
        "browserResetCoverageComplete": len(success_counted) >= 2 and len(failure_counted) >= 2,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": abs_path(RESET_PLAN),
        "runnerPlan": abs_path(PLAN),
        "runner": abs_path(RUNNER),
        "purpose": "Audit reset browser Webshare sampling runner implementation and distinguish dry-run outputs from reset-counted browser samples.",
        "inputs": [abs_path(PLAN), abs_path(RUNNER), abs_path(ATTEMPT_DIR)],
        "attempts": rows,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyToExecuteBrowserSampling": checks["readyToExecuteBrowserSampling"],
            "recommendedExperiment": None,
            "nextArtifact": abs_path(ATTEMPT_DIR),
            "nextScript": abs_path(RUNNER),
            "reason": (
                "Runner exists and dry-run attempts prove output schema, but no executed browser reset samples count toward coverage yet."
                if checks["countedResetAttemptCount"] == 0
                else "Browser reset samples exist; rerun reset sampling coverage/state-machine audits before Phase 4 decisions."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
