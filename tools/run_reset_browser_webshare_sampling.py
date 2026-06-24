#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET_DIR = ROOT / "output/protocol_reverse/reset_plan"
PLAN = RESET_DIR / "reset_browser_sampling_runner_plan.json"
OUT_DIR = RESET_DIR / "browser_sampling_attempts"
OUTLOOK_BROWSER_DIR = ROOT / "output/outlook_browser"
DEFAULT_CARDW_CONFIG = ROOT / "CTF-reg/config.paypal-proxy.json"


VALID_CLASSES = {"browser_success_webshare", "browser_failure_webshare"}
DEFAULT_ENV = {
    "OUTLOOK_JS_INTERNAL_TRACE": "1",
    "OUTLOOK_HSPROTECT_JS_PATCH": "1",
    "REGISTER_ONLY_MAX_ATTEMPTS": "1",
    "OUTLOOK_HEADLESS": "1",
    "OUTLOOK_SKIP_WEBMAIL_INIT": "1",
    "OUTLOOK_BROWSER_OAUTH_TIMEOUT_S": "240",
    "OUTLOOK_OAUTH_DENIED_RETRIES": "1",
    "WEBUI_REG_METHOD": "portal_browser",
}
BASE_CMD = [
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
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_session(prefix: str = "ibtvqcnm-JP") -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def proxy_url(*, session: str, password: str, endpoint: str) -> str:
    host, sep, port = endpoint.partition(":")
    if not sep:
        port = "80"
    return f"http://{session}:{password}@{host}:{port}"


def write_attempt_config(
    *,
    source_config: Path,
    out_dir: Path,
    session: str,
    password: str,
    endpoint: str,
) -> dict[str, Any]:
    raw = source_config.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    proxy = proxy_url(session=session, password=password, endpoint=endpoint)
    data["proxy"] = proxy
    data["proxy_meta"] = {
        "source": "reset_browser_webshare_sampling",
        "transport": "webshare",
        "sessionUser": session,
        "endpoint": endpoint,
        "region": "JP" if "-JP-" in session else "",
        "freshSession": True,
    }
    config_dir = out_dir / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"cardw_{session}.json"
    encoded = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    config_path.write_bytes(encoded + b"\n")
    redacted_proxy = proxy.replace(f":{password}@", ":***@")
    return {
        "sourceConfig": str(source_config.resolve()),
        "sourceConfigSha256": sha256_bytes(raw),
        "attemptConfig": str(config_path.resolve()),
        "attemptConfigSha256": sha256_bytes(encoded + b"\n"),
        "proxy": redacted_proxy,
        "proxySessionUser": session,
        "proxyEndpoint": endpoint,
    }


def command_with_config(config_path: Path) -> list[str]:
    cmd = list(BASE_CMD)
    idx = cmd.index("--cardw-config")
    cmd[idx + 1] = str(config_path)
    return cmd


def latest_files_since(directory: Path, pattern: str, since: float) -> list[str]:
    if not directory.exists():
        return []
    rows = []
    for path in directory.glob(pattern):
        try:
            if path.stat().st_mtime >= since - 2:
                rows.append(str(path.resolve()))
        except OSError:
            continue
    return sorted(rows)


def run_command(cmd: list[str], env_overlay: dict[str, str], timeout: float) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(env_overlay)
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    ended = time.time()
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "startedAt": started,
        "endedAt": ended,
        "elapsedSeconds": ended - started,
        "stdoutTail": proc.stdout[-8000:],
        "stderrTail": proc.stderr[-8000:],
    }


def scan_runtime_trace(paths: list[str]) -> dict[str, Any]:
    flags: dict[str, Any] = {
        "hasCollectorSuccess0": False,
        "hasCaptchaSucceededZero": False,
        "hasRiskVerifyRequest": False,
        "hasRiskVerifyStateContinue": False,
        "hasCreateAccountRequest": False,
        "hasCreateAccountRedirectUrl": False,
        "evidenceLines": [],
    }
    patterns = {
        "hasCollectorSuccess0": "collector oIIoIooo success marker",
        "hasCaptchaSucceededZero": "captcha succeeded zero marker",
        "hasRiskVerifyRequest": "risk/verify request or response observed",
        "hasRiskVerifyStateContinue": "risk/verify state=continue observed",
        "hasCreateAccountRequest": "CreateAccount request or response observed",
        "hasCreateAccountRedirectUrl": "CreateAccount redirectUrl observed",
    }

    for path_text in paths:
        path = Path(path_text)
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, 1):
            view = line.replace('\\"', '"')
            low = view.lower()
            matched: list[str] = []
            if "oiioiooo" in low and ('["0"]' in view or '"0"' in view or "|0" in view):
                flags["hasCollectorSuccess0"] = True
                matched.append("hasCollectorSuccess0")
            if '"state":"succeeded"' in low and '"zero":true' in low:
                flags["hasCaptchaSucceededZero"] = True
                matched.append("hasCaptchaSucceededZero")
            if "risk/verify" in low:
                flags["hasRiskVerifyRequest"] = True
                matched.append("hasRiskVerifyRequest")
                if '"state":"continue"' in low:
                    flags["hasRiskVerifyStateContinue"] = True
                    matched.append("hasRiskVerifyStateContinue")
            if "createaccount" in low:
                flags["hasCreateAccountRequest"] = True
                matched.append("hasCreateAccountRequest")
                if "redirecturl" in low:
                    flags["hasCreateAccountRedirectUrl"] = True
                    matched.append("hasCreateAccountRedirectUrl")

            for key in matched:
                flags["evidenceLines"].append(
                    {
                        "path": str(path.resolve()),
                        "line": line_no,
                        "marker": key,
                        "meaning": patterns[key],
                    }
                )

    flags["browserSuccessLike"] = (
        (flags["hasCollectorSuccess0"] or flags["hasCaptchaSucceededZero"])
        and flags["hasRiskVerifyStateContinue"]
        and flags["hasCreateAccountRedirectUrl"]
    )
    return flags


def classify_from_artifacts(result: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    runtime = scan_runtime_trace([str(p) for p in (artifacts.get("runtimeTrace") or [])])
    if runtime["browserSuccessLike"]:
        return {
            "classified": True,
            "stage": "browser_runtime_success_redirect",
            "successLike": True,
            "reason": "Runtime trace proves collector success, risk/verify state=continue, and CreateAccount redirectUrl.",
            "runtimeEvidence": runtime,
        }

    text = "\n".join(
        str(result.get(key) or "")
        for key in ("stdoutTail", "stderrTail")
    ).lower()
    create_files = artifacts.get("browserApiCreate") or []
    has_redirect = False
    create_error = ""
    for file in create_files:
        doc = read_json(Path(file))
        body = doc.get("response") or doc.get("body") or doc
        raw = json.dumps(body, ensure_ascii=False, default=str)
        if "redirectUrl" in raw or "redirecturl" in raw.lower():
            has_redirect = True
        if not create_error:
            m = re.search(r'"(?:errorCode|code)"\s*:\s*"([^"]+)"', raw)
            if m:
                create_error = m.group(1)
    if has_redirect or "redirecturl" in text:
        return {
            "classified": True,
            "stage": "create_account_redirectUrl",
            "successLike": True,
            "reason": "CreateAccount redirectUrl observed in browser artifacts or process output.",
            "runtimeEvidence": runtime,
        }
    if "oIIoIooo|0".lower() in text or "challenge_success" in text:
        return {
            "classified": True,
            "stage": "collector_success_oIIoIooo_0",
            "successLike": True,
            "reason": "Collector success marker observed in process output.",
            "runtimeEvidence": runtime,
        }
    if result.get("returncode") == 0:
        return {
            "classified": True,
            "stage": "browser_completed_no_redirect_classified",
            "successLike": False,
            "reason": "Runner returned 0 but no redirectUrl or collector success evidence was found by this wrapper.",
            "runtimeEvidence": runtime,
        }
    return {
        "classified": True,
        "stage": "browser_execution_failed",
        "successLike": False,
        "reason": create_error or "Non-zero returncode without success artifact evidence.",
        "runtimeEvidence": runtime,
    }


def build_artifact_index(started: float) -> dict[str, Any]:
    return {
        "runtimeTrace": latest_files_since(OUTLOOK_BROWSER_DIR, "runtime_trace_*.jsonl", started),
        "jsInternalTrace": latest_files_since(OUTLOOK_BROWSER_DIR, "js_internal_trace_*.jsonl", started),
        "pxCookieBridge": latest_files_since(OUTLOOK_BROWSER_DIR, "px_cookie_bridge_*.json", started),
        "browserApiCreate": latest_files_since(OUTLOOK_BROWSER_DIR, "browser_api_create_*.json", started),
        "screenshots": latest_files_since(OUTLOOK_BROWSER_DIR, "*.png", started),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or dry-run reset browser Webshare sampling attempts.")
    parser.add_argument("--sample-class", choices=sorted(VALID_CLASSES), required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--session-prefix", default="ibtvqcnm-JP")
    parser.add_argument("--proxy-endpoint", default="p.webshare.io:80")
    parser.add_argument("--proxy-password", default="zhmbnisigtrt")
    parser.add_argument("--cardw-config", type=Path, default=DEFAULT_CARDW_CONFIG)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--execute", action="store_true", help="Actually run the browser registration command.")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument(
        "--hsprotect-patch-apply",
        choices=["class-default", "0", "1"],
        default="class-default",
        help="Control OUTLOOK_HSPROTECT_JS_PATCH_APPLY. class-default keeps historical success=1/failure=0 behavior.",
    )
    args = parser.parse_args()

    plan = read_json(PLAN)
    if not plan:
        raise SystemExit(f"missing runner plan: {PLAN}")

    outputs = []
    for idx in range(args.count):
        session = make_session(args.session_prefix)
        started = time.time()
        config_evidence = write_attempt_config(
            source_config=args.cardw_config,
            out_dir=args.out_dir,
            session=session,
            password=args.proxy_password,
            endpoint=args.proxy_endpoint,
        )
        cmd = command_with_config(Path(config_evidence["attemptConfig"]))
        env_overlay = dict(DEFAULT_ENV)
        if args.hsprotect_patch_apply == "class-default":
            env_overlay["OUTLOOK_HSPROTECT_JS_PATCH_APPLY"] = "1" if args.sample_class == "browser_success_webshare" else "0"
        else:
            env_overlay["OUTLOOK_HSPROTECT_JS_PATCH_APPLY"] = args.hsprotect_patch_apply
        env_overlay["RESET_BROWSER_SAMPLE_CLASS"] = args.sample_class
        env_overlay["RESET_BROWSER_WEBSHARE_SESSION"] = session
        env_overlay["RESET_BROWSER_PROXY_ENDPOINT"] = args.proxy_endpoint

        attempt = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "plan": str(PLAN.resolve()),
            "sampleClass": args.sample_class,
            "sessionId": session,
            "attemptStartedAt": started,
            "transport": "webshare",
            "usesBrowserForEvidenceOnly": True,
            "countsTowardFinalPureProtocolSuccess": False,
            "freshSession": True,
            "proxyEvidence": {
                "proxyEndpoint": args.proxy_endpoint,
                "proxySessionUser": session,
                "sessionShape": f"{args.session_prefix}-<timestamp_ms>",
                "direct": False,
                "attemptConfigProxy": config_evidence["proxy"],
                "exitIp": None,
                "exitIpSource": "CTF-reg/outlook_browser_register.py _log_browser_evidence uses api.ipify.org; wrapper records generated artifacts after execution.",
            },
            "configEvidence": config_evidence,
            "command": cmd,
            "envOverlay": env_overlay,
            "requiredArtifacts": plan.get("requiredArtifacts"),
            "checks": {
                "runnerPlanLoaded": True,
                "executeRequested": args.execute,
                "newSessionIdGenerated": session.startswith(f"{args.session_prefix}-"),
                "attemptConfigWritten": Path(config_evidence["attemptConfig"]).exists(),
                "commandUsesAttemptConfig": str(config_evidence["attemptConfig"]) in cmd,
                "countsTowardFinalPureProtocolSuccess": False,
                "readyForFreshExperiment": False,
                "goalComplete": False,
            },
            "decision": {
                "goalComplete": False,
                "readyForFreshExperiment": False,
                "countsTowardResetMinimum": False,
                "reason": "Dry-run only; no browser sampling executed." if not args.execute else "Execution requested; classification depends on generated artifacts.",
            },
        }

        if args.execute:
            result = run_command(cmd, env_overlay, args.timeout)
            artifacts = build_artifact_index(started)
            classification = classify_from_artifacts(result, artifacts)
            attempt["execution"] = result
            attempt["artifacts"] = artifacts
            attempt["classification"] = classification
            attempt["finalStage"] = classification.get("stage")
            class_matches = (
                args.sample_class == "browser_success_webshare" and classification.get("successLike") is True
            ) or (
                args.sample_class == "browser_failure_webshare" and classification.get("successLike") is False
            )
            attempt["checks"].update(
                {
                    "runtimeTraceCaptured": bool(artifacts.get("runtimeTrace")),
                    "jsInternalTraceCaptured": bool(artifacts.get("jsInternalTrace")),
                    "pxCookieBridgeArtifactCaptured": bool(artifacts.get("pxCookieBridge")),
                    "browserApiCreateArtifactCaptured": bool(artifacts.get("browserApiCreate")),
                    "classificationMatchesSampleClass": class_matches,
                }
            )
            attempt["decision"]["countsTowardResetMinimum"] = bool(class_matches)
            attempt["decision"]["reason"] = classification.get("reason")
        else:
            attempt["artifacts"] = {}
            attempt["classification"] = {
                "classified": True,
                "stage": "dry_run_not_executed",
                "successLike": False,
                "reason": "No network/browser execution performed.",
            }
            attempt["finalStage"] = "dry_run_not_executed"

        out = args.out_dir / f"browser_sampling_{args.sample_class}_{session}_{int(started)}.json"
        write_json(out, attempt)
        outputs.append(str(out.resolve()))
        time.sleep(0.01)

    result = {
        "outputs": outputs,
        "sampleClass": args.sample_class,
        "count": args.count,
        "executed": args.execute,
        "checks": {
            "outputCount": len(outputs),
            "executeRequested": args.execute,
            "readyForFreshExperiment": False,
            "goalComplete": False,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
