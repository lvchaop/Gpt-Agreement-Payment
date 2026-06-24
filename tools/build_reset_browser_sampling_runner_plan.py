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
HYPOTHESIS_PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"
COVERAGE = RESET_DIR / "reset_sampling_coverage_audit.json"
OUT = RESET_DIR / "reset_browser_sampling_runner_plan.json"

OUTLOOK_BROWSER = ROOT / "CTF-reg/outlook_browser_register.py"
PIPELINE = ROOT / "pipeline.py"
CLASSIFIER = ROOT / "tools/human_trace_classifier_v2.py"
COOKIE_TIMELINE_DIR = PROTO / "cookie_timeline"
OUTLOOK_BROWSER_OUT = ROOT / "output/outlook_browser"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def abs_path(path: Path) -> str:
    return str(path.resolve())


def file_has(path: Path, needle: str) -> bool:
    if not path.exists():
        return False
    return needle in path.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    coverage = read_json(COVERAGE)
    coverage_checks = coverage.get("checks") or {}
    coverage_decision = coverage.get("decision") or {}
    required_gaps = (((coverage_decision.get("recommendedExperiment") or {}).get("requiredGapCounts")) or {})

    instrumentation_evidence = {
        "outlookBrowserRegister": {
            "path": abs_path(OUTLOOK_BROWSER),
            "exists": OUTLOOK_BROWSER.exists(),
            "hasRuntimeTraceInstaller": file_has(OUTLOOK_BROWSER, "def _install_runtime_trace"),
            "hasJsInternalTraceInstaller": file_has(OUTLOOK_BROWSER, "def _install_js_internal_trace"),
            "hasHsprotectPatchToggle": file_has(OUTLOOK_BROWSER, "OUTLOOK_HSPROTECT_JS_PATCH"),
            "hasCookieBridgeArtifact": file_has(OUTLOOK_BROWSER, "px_cookie_bridge_"),
            "hasBrowserApiCreateArtifact": file_has(OUTLOOK_BROWSER, "browser_api_create_"),
            "hasIpifyEvidence": file_has(OUTLOOK_BROWSER, "api.ipify.org"),
        },
        "classifier": {
            "path": abs_path(CLASSIFIER),
            "exists": CLASSIFIER.exists(),
            "hasRuntimeTraceInput": file_has(CLASSIFIER, "runtimeTrace"),
            "hasJsTraceInput": file_has(CLASSIFIER, "jsTrace"),
            "hasCookieTimelineSummary": file_has(CLASSIFIER, "summarize_cookie_timeline"),
        },
        "pipeline": {
            "path": abs_path(PIPELINE),
            "exists": PIPELINE.exists(),
        },
    }

    sample_classes = []
    for class_id in ("browser_success_webshare", "browser_failure_webshare"):
        sample_classes.append(
            {
                "classId": class_id,
                "requiredFreshResetCount": int(required_gaps.get(class_id) or 0),
                "transport": "webshare",
                "usesBrowserForEvidenceOnly": True,
                "countsTowardFinalPureProtocolSuccess": False,
                "freshSessionPerAttempt": True,
                "webshareSessionShape": "ibtvqcnm-JP-<numeric-session>",
                "successPredicate": (
                    {
                        "decoded_oIIoIooo_0": True,
                        "risk_verify_state_continue": True,
                        "create_account_redirectUrl": True,
                    }
                    if class_id == "browser_success_webshare"
                    else {
                        "decoded_oIIoIooo_0": False,
                        "stageMustBeClassified": True,
                    }
                ),
            }
        )

    runner_contract = {
        "proposedScript": abs_path(ROOT / "tools/run_reset_browser_webshare_sampling.py"),
        "mode": "instrumented_browser_evidence_only",
        "allowedBecause": "Reset plan Phase 2 uses browser samples only as success/failure evidence baselines; they do not count toward final pure-protocol PoC.",
        "mustNotDo": [
            "Do not claim browser samples satisfy the final no-browser objective.",
            "Do not run Phase 5 fresh pure-protocol mutation experiments from browser samples unless Phase 4 later yields exactly one candidate.",
            "Do not reuse an old browser run as a reset sample.",
            "Do not reuse a Webshare session across attempts.",
        ],
        "environment": {
            "OUTLOOK_HSPROTECT_JS_PATCH": "1",
            "OUTLOOK_HSPROTECT_JS_PATCH_APPLY": "1",
            "REGISTER_ONLY_MAX_ATTEMPTS": "1",
            "OUTLOOK_HEADLESS": "1",
            "OUTLOOK_SKIP_WEBMAIL_INIT": "1",
            "OUTLOOK_BROWSER_OAUTH_TIMEOUT_S": "240",
            "OUTLOOK_OAUTH_DENIED_RETRIES": "1",
            "WEBUI_REG_METHOD": "portal_browser",
        },
        "baseCommandTemplate": [
            ".venv/bin/python",
            "-u",
            "pipeline.py",
            "--config",
            "CTF-pay/config.paypal.json",
            "--register-only",
            "--register-method",
            "portal_browser",
            "--cardw-config",
            "CTF-reg/config.paypal-proxy.json",
        ],
        "perAttemptSessionRequirement": {
            "newSessionIdForEveryAttempt": True,
            "proxyUsernameShape": "ibtvqcnm-JP-<numeric-session>",
            "mustRecordProxyEndpoint": True,
            "mustRecordExitIp": True,
        },
    }

    required_artifacts = [
        {
            "name": "attempt_summary_json",
            "required": True,
            "fields": ["sampleClass", "sessionId", "startedAt", "endedAt", "command", "returncode", "finalStage"],
        },
        {
            "name": "runtime_trace_jsonl",
            "required": True,
            "source": "CTF-reg/outlook_browser_register.py:_install_runtime_trace",
            "mustContain": ["request", "response", "collector-pxzc5j78di.hsprotect.net", "/API/Proofs/risk/verify", "/API/CreateAccount"],
        },
        {
            "name": "js_internal_trace_jsonl",
            "required": True,
            "source": "CTF-reg/outlook_browser_register.py:_install_js_internal_trace",
            "mustContainAny": ["document.cookie.set", "window.message.recv", "fetch.response", "xhr.response"],
        },
        {
            "name": "cookie_timeline_json",
            "required": True,
            "mustContain": ["_px3", "_pxde", "_pxvid"],
        },
        {
            "name": "collector_decode_json",
            "required": True,
            "mustClassify": ["oIIoIooo|0", "oIIoIooo|-1", "{do:[]}"],
        },
        {
            "name": "risk_verify_material_json",
            "requiredForSuccessClass": True,
            "mustContain": ["state=continue", "_px3", "_pxde", "_pxvid"],
        },
        {
            "name": "create_account_material_json",
            "requiredForSuccessClass": True,
            "mustContain": ["redirectUrl"],
        },
        {
            "name": "proxy_ip_evidence_json",
            "required": True,
            "mustContain": ["proxyEndpoint", "proxySessionUser", "exitIp", "direct=false"],
        },
    ]

    acceptance_gates = {
        "runnerPlanInputGate": {
            "coverageAuditExists": COVERAGE.exists(),
            "browserResetCoverageIncomplete": coverage_checks.get("browserResetCoverageComplete") is False,
            "pureProtocolResetCoverageComplete": coverage_checks.get("pureProtocolResetCoverageComplete") is True,
        },
        "implementationGate": {
            "runnerScriptMustExistBeforeExecution": abs_path(ROOT / "tools/run_reset_browser_webshare_sampling.py"),
            "mustSupportClassIds": ["browser_success_webshare", "browser_failure_webshare"],
            "mustWriteAttemptSummary": True,
            "mustAppendOrRegenerateResetSamplingMatrix": True,
            "mustRerun": [
                abs_path(ROOT / "tools/run_reset_sampling_matrix.py"),
                abs_path(ROOT / "tools/build_reset_sampling_coverage_audit.py"),
                abs_path(ROOT / "tools/build_reset_state_machine.py"),
                abs_path(ROOT / "tools/build_reset_single_transition_candidates.py"),
                abs_path(ROOT / "tools/audit_pure_protocol_goal_gap.py"),
            ],
        },
        "freshExperimentGate": {
            "readyForFreshExperiment": False,
            "reason": "Browser sampling can only update state-machine evidence. Phase 5 remains forbidden unless a later Phase 4 audit has singleTransitionCandidateCount=1 and readyForFreshExperiment=true.",
        },
    }

    checks = {
        "coverageAuditExists": COVERAGE.exists(),
        "coverageSaysBrowserResetIncomplete": coverage_checks.get("browserResetCoverageComplete") is False,
        "coverageSaysPureProtocolResetComplete": coverage_checks.get("pureProtocolResetCoverageComplete") is True,
        "requiredBrowserSuccessGap": int(required_gaps.get("browser_success_webshare") or 0),
        "requiredBrowserFailureGap": int(required_gaps.get("browser_failure_webshare") or 0),
        "outlookBrowserRegisterExists": OUTLOOK_BROWSER.exists(),
        "hasRuntimeTraceInstaller": instrumentation_evidence["outlookBrowserRegister"]["hasRuntimeTraceInstaller"],
        "hasJsInternalTraceInstaller": instrumentation_evidence["outlookBrowserRegister"]["hasJsInternalTraceInstaller"],
        "hasCookieBridgeArtifact": instrumentation_evidence["outlookBrowserRegister"]["hasCookieBridgeArtifact"],
        "hasIpifyEvidence": instrumentation_evidence["outlookBrowserRegister"]["hasIpifyEvidence"],
        "classifierExists": CLASSIFIER.exists(),
        "readyToImplementRunner": True,
        "readyToExecuteBrowserSampling": False,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": abs_path(PLAN),
        "hypothesisPlan": abs_path(HYPOTHESIS_PLAN),
        "purpose": "Define the browser Webshare reset sampling runner required to close Phase 2 coverage gaps before relying on Phase 4 no-candidate conclusions.",
        "inputs": [abs_path(COVERAGE), abs_path(OUTLOOK_BROWSER), abs_path(CLASSIFIER), abs_path(PIPELINE)],
        "sampleClasses": sample_classes,
        "instrumentationEvidence": instrumentation_evidence,
        "runnerContract": runner_contract,
        "requiredArtifacts": required_artifacts,
        "acceptanceGates": acceptance_gates,
        "outputLocations": {
            "browserArtifactsDir": abs_path(OUTLOOK_BROWSER_OUT),
            "cookieTimelineDir": abs_path(COOKIE_TIMELINE_DIR),
            "resetAttemptDir": abs_path(RESET_DIR / "browser_sampling_attempts"),
            "resetSamplingMatrix": abs_path(RESET_DIR / "reset_sampling_matrix.json"),
        },
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "readyToExecuteBrowserSampling": False,
            "recommendedExperiment": None,
            "nextArtifact": abs_path(RESET_DIR / "browser_sampling_attempts"),
            "nextScript": abs_path(ROOT / "tools/run_reset_browser_webshare_sampling.py"),
            "reason": (
                "Instrumentation sources exist for runtime trace, JS internal trace, cookie bridge artifacts, and IP evidence. "
                "Next implement the reset browser Webshare sampling runner; do not execute browser sampling until that runner records all required artifacts and fresh session ids."
            ),
        },
    }
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
