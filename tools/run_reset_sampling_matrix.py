#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
RESET_DIR = PROTO / "reset_plan"
MANIFEST = RESET_DIR / "reset_sampling_manifest.json"
OUT = RESET_DIR / "reset_sampling_matrix.json"
BROWSER_ATTEMPT_DIR = RESET_DIR / "browser_sampling_attempts"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def abs_path(path: Path) -> str:
    return str(path)


def run_cmd(cmd: list[str], timeout: float) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    ended = time.time()
    parsed: Any = None
    if proc.stdout.strip().startswith("{"):
        try:
            parsed = json.loads(proc.stdout)
        except Exception:
            parsed = None
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "startedAt": started,
        "endedAt": ended,
        "elapsedSeconds": ended - started,
        "stdoutTail": proc.stdout[-4000:],
        "stderrTail": proc.stderr[-4000:],
        "parsedJson": parsed,
    }


def classify_execution(row: dict[str, Any]) -> dict[str, Any]:
    execution = row.get("execution") or {}
    parsed = execution.get("parsedJson") or {}
    checks = parsed.get("checks") or row.get("checks") or {}
    stderr = str(execution.get("stderrTail") or "")
    bootstrap_error = None
    m = re.search(r"(/Users/.*?fresh_bootstrap_probe_[^\\\" ]+\.json)", stderr)
    if m:
        bootstrap_doc = read_json(Path(m.group(1)))
        bootstrap_error = bootstrap_doc.get("error")
    if bootstrap_error and "407 Proxy Authentication Required" in str(bootstrap_error):
        return {
            "classified": True,
            "stage": "webshare_proxy_auth_407",
            "reason": "bootstrap artifact records HTTP CONNECT 407 Proxy Authentication Required; no collector response was received",
            "completeRunnerReturn": False,
            "bootstrapError": bootstrap_error,
            "bootstrapArtifact": m.group(1) if m else None,
        }
    if "407 Proxy Authentication Required" in stderr:
        return {
            "classified": True,
            "stage": "webshare_proxy_auth_407",
            "reason": "bootstrap send failed at HTTP CONNECT with 407 Proxy Authentication Required; no collector response was received",
            "completeRunnerReturn": False,
        }
    if execution.get("returncode") == 0:
        if checks.get("comboAnySuccess") is True:
            stage = "collector_success_oIIoIooo_0"
        elif checks.get("progression200Pow") is True:
            stage = "final_seq5_seq6_no_success"
        elif checks.get("bundle200Pow") is True:
            stage = "bundle_pow_reached"
        elif checks.get("second200") is True:
            stage = "second_sequence_reached"
        elif checks.get("bootstrap200") is True:
            stage = "bootstrap_reached"
        else:
            stage = "executed_unclassified_success_returncode"
        return {
            "classified": True,
            "stage": stage,
            "reason": "runner returned JSON and checks were available",
            "completeRunnerReturn": True,
        }
    if "KeyError: 'sid'" in stderr:
        return {
            "classified": True,
            "stage": "bootstrap_response_missing_sid",
            "reason": "runner failed while building second request because bootstrap material lacked memory.sid",
            "completeRunnerReturn": False,
        }
    return {
        "classified": False,
        "stage": "execution_error_unclassified",
        "reason": stderr[-1000:] if stderr else "non-zero returncode without recognized error",
        "completeRunnerReturn": False,
    }


def classifier_runs() -> list[dict[str, Any]]:
    doc = read_json(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json")
    runs = doc.get("runs") or []
    return runs if isinstance(runs, list) else []


def browser_existing_rows(class_id: str, minimum: int) -> list[dict[str, Any]]:
    want_success = class_id == "browser_success_webshare"
    rows = []
    for run in classifier_runs():
        checks = run.get("checks") or {}
        is_success = (
            checks.get("decoded_oIIoIooo_0") is True
            and checks.get("risk_verify_state_continue") is True
            and checks.get("create_account_redirectUrl") is True
        )
        if is_success != want_success:
            continue
        run_id = str(run.get("run") or "")
        rows.append(
            {
                "source": "existing_trace_classifier",
                "run": run_id,
                "stage": run.get("stage"),
                "transport": "webshare_or_unknown_from_existing_trace",
                "usesBrowserForEvidenceOnly": True,
                "countsTowardResetMinimum": False,
                "reasonNotCountingTowardResetMinimum": "Existing classifier evidence predates reset manifest and lacks mandatory reset proxy/direct session evidence.",
                "evidence": {
                    "runtimeTrace": abs_path(ROOT / str(run.get("runtimeTrace"))) if run.get("runtimeTrace") else None,
                    "jsTrace": abs_path(ROOT / str(run.get("jsTrace"))) if run.get("jsTrace") else None,
                    "traceClassification": run.get("traceClassificationPath"),
                    "cookieTimeline": (run.get("cookieTimeline") or {}).get("path"),
                    "riskVerify": (run.get("riskVerify") or {}).get("path"),
                },
                "checks": {
                    "decoded_oIIoIooo_0": checks.get("decoded_oIIoIooo_0") is True,
                    "risk_verify_state_continue": checks.get("risk_verify_state_continue") is True,
                    "create_account_redirectUrl": checks.get("create_account_redirectUrl") is True,
                    "runtimeTraceExists": (ROOT / str(run.get("runtimeTrace"))).exists() if run.get("runtimeTrace") else False,
                    "jsTraceExists": (ROOT / str(run.get("jsTrace"))).exists() if run.get("jsTrace") else False,
                },
            }
        )
        if len(rows) >= max(minimum, 4):
            break
    return rows


def pure_protocol_existing_rows(class_id: str, minimum: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if class_id == "pure_protocol_webshare":
        for path in sorted((PROTO / "direct_webshare_attempt").glob("*.json")):
            doc = read_json(path)
            checks = doc.get("checks") or {}
            rows.append(
                {
                    "source": "existing_direct_webshare_attempt",
                    "sessionId": doc.get("session"),
                    "transport": "webshare",
                    "usesBrowserForEvidenceOnly": False,
                    "countsTowardResetMinimum": False,
                    "reasonNotCountingTowardResetMinimum": "Existing attempt predates reset manifest; useful baseline but not a fresh reset sample.",
                    "evidence": {
                        "attemptSummary": abs_path(path),
                        "proxyEndpoint": doc.get("proxyEndpoint"),
                    },
                    "checks": {
                        "bootstrap200": checks.get("bootstrap200") is True,
                        "bundle200Pow": checks.get("bundle200Pow") is True,
                        "progression200Pow": checks.get("progression200Pow") is True,
                        "comboAnySuccess": checks.get("comboAnySuccess") is True,
                    },
                }
            )
            if len(rows) >= max(minimum, 6):
                break
    return rows


def planned_command(class_id: str, idx: int) -> dict[str, Any]:
    if class_id in {"browser_success_webshare", "browser_failure_webshare"}:
        return {
            "kind": "executable_command",
            "cmd": [
                "python3",
                "tools/run_reset_browser_webshare_sampling.py",
                "--sample-class",
                class_id,
                "--count",
                "1",
            ],
            "sessionId": f"runner_generated_{class_id}_{idx}",
            "newSession": True,
            "executeFlagRequiredForNetwork": True,
        }
    if class_id == "pure_protocol_webshare":
        # Preserve the Webshare username shape proven by historical successful
        # CONNECT probes: <base-user>-<country>-<numeric-session>.
        session = f"ibtvqcnm-JP-{int(time.time()) * 1000 + idx}"
        reset_sample_id = f"reset-webshare-{int(time.time())}-{idx}"
        return {
            "kind": "executable_command",
            "cmd": [
                "python3",
                "tools/run_human_direct_webshare_attempt.py",
                "--session",
                session,
                "--combo-transport",
                "https-threads",
                "--combo-header-mode",
                "safe",
                "--combo-aeax-source",
                "offline-ng",
                "--combo-bzt-source",
                "solve",
                "--combo-stack-source",
                "template",
                "--combo-tail-source",
                "fresh",
                "--combo-inner-uuid-source",
                "fresh",
                "--combo-non-px-activity-source",
                "fresh",
                "--combo-seq6-activity-source",
                "fresh",
                "--combo-payload-uuid-source",
                "fresh",
                "--combo-pc-uuid-source",
                "payload",
                "--combo-marker-source",
                "fresh",
                "--combo-form-outer-source",
                "fresh",
                "--combo-payload-source",
                "built",
                "--combo-pc-source",
                "computed",
                "--combo-body-source",
                "built",
            ],
            "sessionId": session,
            "newSession": True,
            "resetSampleId": reset_sample_id,
        }
    if class_id == "pure_protocol_direct":
        session = f"reset-direct-{int(time.time())}-{idx}"
        return {
            "kind": "executable_command",
            "cmd": [
                "python3",
                "tools/run_human_direct_webshare_attempt.py",
                "--direct",
                "--session",
                session,
                "--combo-transport",
                "https-threads",
                "--combo-header-mode",
                "safe",
                "--combo-aeax-source",
                "offline-ng",
                "--combo-bzt-source",
                "solve",
                "--combo-stack-source",
                "template",
                "--combo-tail-source",
                "fresh",
                "--combo-inner-uuid-source",
                "fresh",
                "--combo-non-px-activity-source",
                "fresh",
                "--combo-seq6-activity-source",
                "fresh",
                "--combo-payload-uuid-source",
                "fresh",
                "--combo-pc-uuid-source",
                "payload",
                "--combo-marker-source",
                "fresh",
                "--combo-form-outer-source",
                "fresh",
                "--combo-payload-source",
                "built",
                "--combo-pc-source",
                "computed",
                "--combo-body-source",
                "built",
            ],
            "sessionId": session,
            "newSession": True,
        }
    return {
        "kind": "collection_instruction",
        "cmd": None,
        "sessionId": f"unsupported-{int(time.time())}-{idx}",
        "newSession": True,
        "missingRunnerCapability": f"No runner registered for sample class {class_id}.",
    }


def build_planned_rows(sample_class: dict[str, Any], existing_count: int) -> list[dict[str, Any]]:
    class_id = str(sample_class["classId"])
    minimum = int(sample_class["minimumCount"])
    rows = []
    for idx in range(minimum):
        rows.append(
            {
                "sampleClass": class_id,
                "plannedIndex": idx,
                "status": "planned_not_run",
                "transport": sample_class.get("transport"),
                "usesBrowserForEvidenceOnly": sample_class.get("usesBrowserForEvidenceOnly"),
                "countsTowardFinalPureProtocolSuccess": sample_class.get("countsTowardFinalPureProtocolSuccess"),
                "command": planned_command(class_id, idx),
                "requiredArtifacts": sample_class.get("requiredArtifacts"),
                "requiredFields": sample_class.get("requiredFields"),
                "existingBaselineRowsAvailable": existing_count,
            }
        )
    return rows


def execute_pure_protocol(planned_rows: list[dict[str, Any]], sample_class: str, max_count: int, timeout: float) -> list[dict[str, Any]]:
    executed = []
    for row in planned_rows:
        if row.get("sampleClass") != sample_class:
            continue
        command = row.get("command") or {}
        cmd = command.get("cmd")
        if not cmd:
            continue
        if len(executed) >= max_count:
            break
        result = run_cmd(cmd, timeout=timeout)
        row["status"] = "executed"
        row["execution"] = result
        parsed = result.get("parsedJson") or {}
        row["evidence"] = {
            "attemptSummary": parsed.get("json"),
            "sessionId": parsed.get("session"),
        }
        row["checks"] = parsed.get("checks")
        row["classification"] = classify_execution(row)
        row["countsTowardResetMinimum"] = (
            row["classification"]["classified"] is True
            and row["classification"].get("stage") != "webshare_proxy_auth_407"
        )
        executed.append(row)
    return executed


def classify_browser_attempt(doc: dict[str, Any]) -> dict[str, Any]:
    classification = doc.get("classification") or {}
    if classification:
        return {
            "classified": classification.get("classified") is True,
            "stage": classification.get("stage"),
            "reason": classification.get("reason"),
            "completeRunnerReturn": (doc.get("checks") or {}).get("executeRequested") is True,
            "successLike": classification.get("successLike") is True,
        }
    return {
        "classified": False,
        "stage": "browser_attempt_unclassified",
        "reason": "Browser attempt summary did not include classification.",
        "completeRunnerReturn": False,
        "successLike": False,
    }


def load_browser_attempt_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(BROWSER_ATTEMPT_DIR.glob("browser_sampling_*.json")):
        doc = read_json(path)
        sample_class = doc.get("sampleClass")
        if sample_class not in {"browser_success_webshare", "browser_failure_webshare"}:
            continue
        checks = doc.get("checks") or {}
        decision = doc.get("decision") or {}
        config = doc.get("configEvidence") or {}
        rows.append(
            {
                "sampleClass": sample_class,
                "plannedIndex": None,
                "status": "executed" if checks.get("executeRequested") is True else "dry_run_not_executed",
                "source": "reset_browser_webshare_sampling_runner",
                "transport": "webshare",
                "usesBrowserForEvidenceOnly": True,
                "countsTowardFinalPureProtocolSuccess": False,
                "evidence": {
                    "attemptSummary": abs_path(path),
                    "sessionId": doc.get("sessionId"),
                    "proxyEndpoint": ((doc.get("proxyEvidence") or {}).get("proxyEndpoint")),
                    "proxySessionUser": ((doc.get("proxyEvidence") or {}).get("proxySessionUser")),
                    "attemptConfig": config.get("attemptConfig"),
                    "attemptConfigSha256": config.get("attemptConfigSha256"),
                    "runtimeTrace": ((doc.get("artifacts") or {}).get("runtimeTrace") or []),
                    "jsInternalTrace": ((doc.get("artifacts") or {}).get("jsInternalTrace") or []),
                    "pxCookieBridge": ((doc.get("artifacts") or {}).get("pxCookieBridge") or []),
                    "browserApiCreate": ((doc.get("artifacts") or {}).get("browserApiCreate") or []),
                },
                "execution": doc.get("execution"),
                "checks": {
                    "executeRequested": checks.get("executeRequested") is True,
                    "newSessionIdGenerated": checks.get("newSessionIdGenerated") is True,
                    "attemptConfigWritten": checks.get("attemptConfigWritten") is True,
                    "commandUsesAttemptConfig": checks.get("commandUsesAttemptConfig") is True,
                    "runtimeTraceCaptured": checks.get("runtimeTraceCaptured") is True,
                    "jsInternalTraceCaptured": checks.get("jsInternalTraceCaptured") is True,
                    "pxCookieBridgeArtifactCaptured": checks.get("pxCookieBridgeArtifactCaptured") is True,
                    "browserApiCreateArtifactCaptured": checks.get("browserApiCreateArtifactCaptured") is True,
                    "classificationMatchesSampleClass": checks.get("classificationMatchesSampleClass") is True,
                },
                "classification": classify_browser_attempt(doc),
                "countsTowardResetMinimum": decision.get("countsTowardResetMinimum") is True,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or execute the reset controlled sampling matrix.")
    parser.add_argument("--execute-pure-webshare", type=int, default=0, help="Run N planned pure_protocol_webshare attempts.")
    parser.add_argument("--execute-pure-direct", type=int, default=0, help="Run N planned pure_protocol_direct attempts.")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    manifest = read_json(MANIFEST)
    if not manifest:
        raise SystemExit(f"missing manifest: {MANIFEST}")
    previous = read_json(OUT)
    previous_executed = previous.get("executedRows") or []
    if not isinstance(previous_executed, list):
        previous_executed = []

    sample_classes = manifest.get("sampleClasses") or []
    class_rows: list[dict[str, Any]] = []
    baseline_rows: dict[str, list[dict[str, Any]]] = {}
    planned_rows: list[dict[str, Any]] = []

    for sample_class in sample_classes:
        class_id = str(sample_class.get("classId"))
        minimum = int(sample_class.get("minimumCount") or 0)
        if class_id.startswith("browser_"):
            existing = browser_existing_rows(class_id, minimum)
        else:
            existing = pure_protocol_existing_rows(class_id, minimum)
        baseline_rows[class_id] = existing
        planned = build_planned_rows(sample_class, len(existing))
        planned_rows.extend(planned)
        class_rows.append(
            {
                "classId": class_id,
                "minimumCount": minimum,
                "transport": sample_class.get("transport"),
                "usesBrowserForEvidenceOnly": sample_class.get("usesBrowserForEvidenceOnly"),
                "existingBaselineCount": len(existing),
                "resetCollectedCount": 0,
                "plannedCount": len(planned),
                "resetMinimumSatisfied": False,
            }
        )

    executed = []
    if args.execute_pure_webshare > 0:
        executed.extend(execute_pure_protocol(planned_rows, "pure_protocol_webshare", args.execute_pure_webshare, args.timeout))
        for class_row in class_rows:
            if class_row["classId"] == "pure_protocol_webshare":
                class_row["resetCollectedCount"] = sum(
                    1
                    for row in planned_rows
                    if row.get("sampleClass") == "pure_protocol_webshare"
                    and row.get("countsTowardResetMinimum") is True
                )
                class_row["resetMinimumSatisfied"] = class_row["resetCollectedCount"] >= class_row["minimumCount"]
    if args.execute_pure_direct > 0:
        executed.extend(execute_pure_protocol(planned_rows, "pure_protocol_direct", args.execute_pure_direct, args.timeout))

    browser_attempt_rows = load_browser_attempt_rows()
    all_executed = browser_attempt_rows + executed + previous_executed
    seen_exec_keys: set[tuple[str, str, str]] = set()
    deduped_executed = []
    for row in all_executed:
        evidence = row.get("evidence") or {}
        execution = row.get("execution") or {}
        cmd_key = " ".join(str(part) for part in (execution.get("cmd") or []))
        key = (
            str(row.get("sampleClass")),
            str(evidence.get("attemptSummary") or ""),
            str(evidence.get("sessionId") or cmd_key),
        )
        if key in seen_exec_keys:
            continue
        seen_exec_keys.add(key)
        if str(row.get("sampleClass")).startswith("browser_"):
            row["classification"] = row.get("classification") or classify_browser_attempt(row)
            row["countsTowardResetMinimum"] = (row.get("countsTowardResetMinimum") is True)
        else:
            row["classification"] = classify_execution(row)
            row["countsTowardResetMinimum"] = (
                row["classification"]["classified"] is True
                and row["classification"].get("stage") != "webshare_proxy_auth_407"
            )
        deduped_executed.append(row)

    for class_row in class_rows:
        class_row["resetCollectedCount"] = sum(
            1
            for row in deduped_executed
            if row.get("sampleClass") == class_row["classId"]
            and row.get("countsTowardResetMinimum") is True
        )
        class_row["resetMinimumSatisfied"] = class_row["resetCollectedCount"] >= class_row["minimumCount"]

    reset_complete = all(row["resetMinimumSatisfied"] for row in class_rows)
    pure_protocol_reset_complete = all(
        row["resetMinimumSatisfied"]
        for row in class_rows
        if row["classId"] in {"pure_protocol_webshare", "pure_protocol_direct"}
    )
    browser_baseline_available = all(
        row["existingBaselineCount"] >= row["minimumCount"]
        for row in class_rows
        if row["classId"] in {"browser_success_webshare", "browser_failure_webshare"}
    )
    ready_for_baseline_state_machine = pure_protocol_reset_complete and browser_baseline_available
    pure_webshare_executable = any(
        ((row.get("command") or {}).get("cmd"))
        for row in planned_rows
        if row.get("sampleClass") == "pure_protocol_webshare"
    )
    direct_runner_missing = any(
        row.get("sampleClass") == "pure_protocol_direct"
        and (row.get("command") or {}).get("cmd") is None
        for row in planned_rows
    )
    browser_runner_missing = any(
        str(row.get("sampleClass")).startswith("browser_")
        and (row.get("command") or {}).get("cmd") is None
        for row in planned_rows
    )
    browser_runner_attempt_count = sum(1 for row in deduped_executed if str(row.get("sampleClass")).startswith("browser_"))
    browser_runner_executed_count = sum(
        1
        for row in deduped_executed
        if str(row.get("sampleClass")).startswith("browser_")
        and (row.get("checks") or {}).get("executeRequested") is True
    )

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Controlled reset sampling matrix. Existing evidence is separated from reset-collected samples so old traces cannot be mistaken for new controlled sampling.",
        "plan": manifest.get("plan"),
        "manifest": abs_path(MANIFEST),
        "inputs": manifest.get("inputs"),
        "classSummary": class_rows,
        "existingBaselineRows": baseline_rows,
        "plannedRows": planned_rows,
        "executedRows": deduped_executed,
        "checks": {
            "manifestLoaded": True,
            "sampleClassCount": len(sample_classes),
            "allFourSampleClassesPresent": {row["classId"] for row in class_rows}
            == {
                "browser_success_webshare",
                "browser_failure_webshare",
                "pure_protocol_webshare",
                "pure_protocol_direct",
            },
            "existingEvidenceSeparatedFromResetCollection": True,
            "pureWebshareRunnerExecutable": pure_webshare_executable,
            "directRunnerMissing": direct_runner_missing,
            "browserRunnerMissing": browser_runner_missing,
            "browserRunnerAttemptCount": browser_runner_attempt_count,
            "browserRunnerExecutedCount": browser_runner_executed_count,
            "resetSamplingComplete": reset_complete,
            "pureProtocolResetSamplingComplete": pure_protocol_reset_complete,
            "browserBaselineAvailable": browser_baseline_available,
            "readyForBaselineStateMachine": ready_for_baseline_state_machine,
            "readyForStateMachine": reset_complete,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForStateMachine": reset_complete,
            "readyForBaselineStateMachine": ready_for_baseline_state_machine,
            "recommendedExperiment": None,
            "nextArtifact": abs_path(PROTO / "reset_plan/reset_state_machine.json") if ready_for_baseline_state_machine else abs_path(OUT),
            "nextScript": abs_path(ROOT / "tools/build_reset_state_machine.py") if ready_for_baseline_state_machine else abs_path(ROOT / "tools/run_reset_sampling_matrix.py"),
            "reason": (
                "Pure-protocol reset sampling is complete and browser baseline evidence is available; proceed to baseline+reset state-machine induction, while retaining that browser reset samples are not freshly collected."
                if ready_for_baseline_state_machine
                else "Reset sampling is not complete. Existing traces are baseline evidence only; fresh reset samples still need collection, and missing runner capabilities are explicitly recorded."
            ),
        },
    }
    write_json(OUT, doc)
    print(
        json.dumps(
            {
                "json": abs_path(OUT),
                "checks": doc["checks"],
                "decision": doc["decision"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
