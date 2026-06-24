#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
OUT_DIR = PROTO / "reset_plan"
OUT = OUT_DIR / "reset_sampling_manifest.json"

RESET_PLAN = ROOT / "docs/pure-protocol-human-reset-execution-plan.md"
HYPOTHESIS_PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path)


def file_info(path: Path, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": rel(path),
        "exists": path.exists(),
        "sizeBytes": path.stat().st_size if path.exists() else None,
    }


def count_files(path: Path, pattern: str = "*.json") -> int:
    return len(list(path.glob(pattern))) if path.exists() else 0


def load_classifier_runs() -> list[dict[str, Any]]:
    summary = read_json(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json")
    runs = summary.get("runs") or []
    return runs if isinstance(runs, list) else []


def summarize_classifier_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage: dict[str, int] = {}
    full_success = []
    non_success = []
    for run in runs:
        stage = str(run.get("stage") or "unknown")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        checks = run.get("checks") or {}
        row = {
            "run": run.get("run"),
            "stage": stage,
            "runtimeTrace": rel(ROOT / str(run.get("runtimeTrace"))) if run.get("runtimeTrace") else None,
            "jsTrace": rel(ROOT / str(run.get("jsTrace"))) if run.get("jsTrace") else None,
            "decoded_oIIoIooo_0": checks.get("decoded_oIIoIooo_0") is True,
            "risk_verify_state_continue": checks.get("risk_verify_state_continue") is True,
            "create_account_redirectUrl": checks.get("create_account_redirectUrl") is True,
            "cookieTimelineExists": bool(((run.get("cookieTimeline") or {}).get("exists"))),
            "riskVerifyExists": bool(((run.get("riskVerify") or {}).get("exists"))),
        }
        if checks.get("decoded_oIIoIooo_0") is True:
            full_success.append(row)
        else:
            non_success.append(row)
    return {
        "runCount": len(runs),
        "stageCounts": by_stage,
        "fullSuccessCount": len(full_success),
        "nonFullSuccessCount": len(non_success),
        "fullSuccessRuns": full_success,
        "nonFullSuccessRuns": non_success,
    }


def summarize_protocol_attempts() -> dict[str, Any]:
    dirs = {
        "directWebshareAttempt": PROTO / "direct_webshare_attempt",
        "firstFailureOverlapAttempt": PROTO / "first_failure_overlap_attempt",
        "seq5Seq6ComboProbe": PROTO / "seq5_seq6_combo_probe",
        "webshareDirectSessions": PROTO / "webshare_direct_sessions",
    }
    counts = {name: count_files(path) for name, path in dirs.items()}

    direct_rows = []
    for path in sorted((PROTO / "direct_webshare_attempt").glob("*.json")):
        doc = read_json(path)
        checks = doc.get("checks") or {}
        direct_rows.append(
            {
                "path": rel(path),
                "session": doc.get("session"),
                "proxyEndpoint": doc.get("proxyEndpoint"),
                "bootstrap200": checks.get("bootstrap200") is True,
                "bundle200Pow": checks.get("bundle200Pow") is True,
                "progression200Pow": checks.get("progression200Pow") is True,
                "comboAnySuccess": checks.get("comboAnySuccess") is True,
            }
        )

    overlap_rows = []
    for path in sorted((PROTO / "first_failure_overlap_attempt").glob("*.json")):
        doc = read_json(path)
        checks = doc.get("checks") or {}
        overlap_rows.append(
            {
                "path": rel(path),
                "session": doc.get("session"),
                "bootstrap200": checks.get("bootstrap200") is True,
                "bundle200Pow": checks.get("bundle200Pow") is True,
                "overlapSeq3ResponseFirst": checks.get("overlapSeq3ResponseFirst") is True,
                "overlapSeq2Rejected": checks.get("overlapSeq2Rejected") is True,
                "seq4AfterOverlap200Pow": checks.get("seq4AfterOverlap200Pow") is True,
                "finalComboAnySuccess": checks.get("finalComboAnySuccess") is True,
            }
        )

    session_probe_rows = []
    for path in sorted((PROTO / "webshare_direct_sessions").glob("*.json")):
        doc = read_json(path)
        rows = doc.get("rows") or []
        session_probe_rows.append(
            {
                "path": rel(path),
                "rowCount": len(rows) if isinstance(rows, list) else 0,
                "sessions": [row.get("session") for row in rows[:5]] if isinstance(rows, list) else [],
                "httpCodes": [
                    (((row.get("result") or {}).get("parsed") or {}).get("httpCode"))
                    for row in rows[:5]
                ]
                if isinstance(rows, list)
                else [],
            }
        )

    return {
        "counts": counts,
        "directWebshareRows": direct_rows,
        "firstFailureOverlapRows": overlap_rows,
        "webshareSessionProbeRows": session_probe_rows,
    }


def sample_class(
    class_id: str,
    count: int,
    transport: str,
    uses_browser: bool,
    purpose: str,
    success_predicate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "classId": class_id,
        "minimumCount": count,
        "transport": transport,
        "usesBrowserForEvidenceOnly": uses_browser,
        "countsTowardFinalPureProtocolSuccess": not uses_browser,
        "purpose": purpose,
        "perAttemptRules": {
            "freshSessionRequired": True,
            "newSessionIdForEveryAttempt": True,
            "recordProxyOrDirectEvidence": True,
            "noFieldMutationDuringSampling": True,
            "stopAtPredefinedEndpoint": True,
        },
        "successPredicate": success_predicate,
        "requiredArtifacts": [
            "attempt_summary_json",
            "raw_network_trace_or_har",
            "collector_request_response_trace",
            "collector_decoded_response_json",
            "cookie_or_storage_timeline_json",
            "js_runtime_hook_trace_jsonl",
            "risk_verify_material_json",
            "create_account_material_json",
            "proxy_or_direct_ip_evidence_json",
        ],
        "requiredFields": [
            "sessionId",
            "attemptStartedAt",
            "transport",
            "proxyEndpoint",
            "exitIpOrDirectEvidence",
            "collectorRequests[].seq",
            "collectorRequests[].rsc",
            "collectorResponses[].rawBody",
            "collectorResponses[].decodedHandlers",
            "cookieTimeline._px3",
            "cookieTimeline._pxde",
            "cookieTimeline._pxvid",
            "riskVerify.state",
            "createAccount.redirectUrl",
            "finalStage",
        ],
    }


def main() -> int:
    status = read_json(PROTO / "hypothesis_reframe/hypothesis_reframe_status.json")
    final_gap = read_json(PROTO / "hypothesis_reframe/server_internal_unobserved_state_final_gap.json")
    actionable = read_json(PROTO / "hypothesis_reframe/actionable_frontier_audit.json")
    goal_audit = read_json(PROTO / "goal_audit/pure_protocol_goal_gap_audit.json")
    classifier_runs = load_classifier_runs()
    classifier_summary = summarize_classifier_runs(classifier_runs)
    protocol_summary = summarize_protocol_attempts()

    sample_classes = [
        sample_class(
            "browser_success_webshare",
            2,
            "webshare",
            True,
            "Capture successful browser HUMAN lifecycle with proxy/IP/session evidence; evidence only, not final PoC.",
            {
                "decoded_oIIoIooo_0": True,
                "risk_verify_state_continue": True,
                "create_account_redirectUrl": True,
            },
        ),
        sample_class(
            "browser_failure_webshare",
            2,
            "webshare",
            True,
            "Capture browser near-failure or failure lifecycle under comparable Webshare conditions.",
            {
                "decoded_oIIoIooo_0": False,
                "stageMustBeClassified": True,
            },
        ),
        sample_class(
            "pure_protocol_webshare",
            3,
            "webshare",
            False,
            "Capture no-browser pure-protocol attempts with Webshare as a controlled variable.",
            {
                "noBrowser": True,
                "noCamoufox": True,
                "noMouse": True,
                "noVision": True,
                "noExternalCaptcha": True,
                "stageMustBeClassified": True,
            },
        ),
        sample_class(
            "pure_protocol_direct",
            2,
            "direct",
            False,
            "Capture no-browser pure-protocol attempts without proxy to test IP/session as a controlled variable.",
            {
                "noProxy": True,
                "noBrowser": True,
                "noCamoufox": True,
                "noMouse": True,
                "noVision": True,
                "noExternalCaptcha": True,
                "stageMustBeClassified": True,
            },
        ),
    ]

    current_checks = {
        "resetPlanExists": RESET_PLAN.exists(),
        "hypothesisPlanExists": HYPOTHESIS_PLAN.exists(),
        "statusReadyForFreshExperimentFalse": ((status.get("checks") or {}).get("readyForFreshExperiment") is False),
        "oldActionableFrontierNotFound": ((actionable.get("checks") or {}).get("actionableMissingArtifactCount") == 0),
        "serverInternalFinalGapPresent": (
            ((final_gap.get("remainingGap") or {}).get("id") == "collector_server_internal_or_unobserved_expected_state")
        ),
        "goalStillMissingEndToEndPoc": "end_to_end_pure_protocol_poc"
        in (((goal_audit.get("summary") or {}).get("blockingOrMissing")) or []),
        "classifierHasBrowserSuccessEvidence": classifier_summary["fullSuccessCount"] >= 1,
        "classifierHasBrowserFailureEvidence": classifier_summary["nonFullSuccessCount"] >= 1,
        "historicalPureProtocolAttemptsExist": (
            protocol_summary["counts"]["directWebshareAttempt"] > 0
            or protocol_summary["counts"]["firstFailureOverlapAttempt"] > 0
        ),
        "manifestSampleClassesComplete": len(sample_classes) == 4
        and all(c["minimumCount"] > 0 for c in sample_classes),
    }

    manifest = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Reset-plan sampling manifest for rebuilding a controlled evidence base before any new minimal transition experiment.",
        "plan": rel(RESET_PLAN),
        "upstreamPlan": rel(HYPOTHESIS_PLAN),
        "inputs": [
            file_info(PROTO / "hypothesis_reframe/hypothesis_reframe_status.json", "current_hypothesis_status"),
            file_info(PROTO / "hypothesis_reframe/server_internal_unobserved_state_final_gap.json", "final_gap"),
            file_info(PROTO / "hypothesis_reframe/actionable_frontier_audit.json", "actionable_frontier_audit"),
            file_info(PROTO / "goal_audit/pure_protocol_goal_gap_audit.json", "goal_audit"),
            file_info(PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json", "trace_classifier_summary"),
        ],
        "currentEvidenceBoundary": {
            "hypothesisStatusChecks": status.get("checks"),
            "finalGapChecks": final_gap.get("checks"),
            "actionableFrontierChecks": actionable.get("checks"),
            "goalSummary": goal_audit.get("summary"),
        },
        "existingEvidenceInventory": {
            "classifier": classifier_summary,
            "protocolAttempts": protocol_summary,
        },
        "sampleClasses": sample_classes,
        "globalSamplingRules": {
            "everyNewAttemptMustUseNewSession": True,
            "webshareAttemptsMustRecordProxySessionAndExitIp": True,
            "directAttemptsMustRecordNoProxyEvidence": True,
            "browserSamplesAreEvidenceOnly": True,
            "pureProtocolSamplesMustNotUseBrowserCamoufoxMouseVisionOrExternalCaptcha": True,
            "samplingDoesNotMutateProtocolFields": True,
            "ipIsControlledVariableNotConclusion": True,
        },
        "stageOrder": [
            "bootstrap",
            "second",
            "sequence",
            "bundle_pow",
            "first_failure_or_overlap",
            "progression_pow",
            "final_seq5_seq6",
            "collector_success_oIIoIooo_0",
            "risk_verify_state_continue",
            "create_account_redirectUrl",
        ],
        "stageAdvanceDefinitions": [
            "oIIoIooo|-1 -> {do:[]}",
            "{do:[]} -> cookie/token handler",
            "cookie/token handler -> oIIoIooo|0",
            "oIIoIooo|0 -> risk/verify state=continue",
            "risk/verify state=continue -> CreateAccount redirectUrl",
        ],
        "plannedOutputs": {
            "samplingMatrix": rel(PROTO / "reset_plan/reset_sampling_matrix.json"),
            "stateMachine": rel(PROTO / "reset_plan/reset_state_machine.json"),
            "singleTransitionCandidates": rel(PROTO / "reset_plan/reset_single_transition_candidates.json"),
            "minimalTransitionExperimentAudit": rel(PROTO / "reset_plan/reset_minimal_transition_experiment_audit.json"),
            "endToEndPoc": rel(PROTO / "reset_plan/reset_end_to_end_pure_protocol_poc.json"),
        },
        "checks": current_checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyForControlledSampling": all(
                [
                    current_checks["resetPlanExists"],
                    current_checks["statusReadyForFreshExperimentFalse"],
                    current_checks["oldActionableFrontierNotFound"],
                    current_checks["serverInternalFinalGapPresent"],
                    current_checks["goalStillMissingEndToEndPoc"],
                    current_checks["manifestSampleClassesComplete"],
                ]
            ),
            "recommendedExperiment": None,
            "nextArtifact": rel(PROTO / "reset_plan/reset_sampling_matrix.json"),
            "nextScript": rel(ROOT / "tools/run_reset_sampling_matrix.py"),
            "reason": (
                "The old hypothesis frontier is exhausted and the end-to-end pure protocol PoC is still missing. "
                "The next evidence-producing step is controlled sampling, not a field-mutation fresh experiment."
            ),
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "json": rel(OUT),
                "checks": manifest["checks"],
                "decision": manifest["decision"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
