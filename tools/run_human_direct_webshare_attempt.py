#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/direct_webshare_attempt"
WASM = "output/protocol_reverse/wasm/captcha_s00ld1lglrw0_1781191381.wasm"


def run_json(cmd: list[str], env: dict[str, str] | None = None, timeout: float | None = None) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=REPO, env=env, text=True, capture_output=True, check=False, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(json.dumps({
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }, ensure_ascii=False))
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"command did not emit JSON: {cmd}\nstdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}") from exc


def read_json(path: str | Path) -> dict[str, Any]:
    return json.loads((REPO / path if not Path(path).is_absolute() else Path(path)).read_text(encoding="utf-8"))


def solved_pow_value(pow_json: str | Path) -> str:
    doc = read_json(pow_json)
    for row in doc.get("results") or []:
        if row.get("matchesTarget") is True and row.get("value"):
            return str(row["value"])
    raise RuntimeError(f"no solved pow in {pow_json}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a clean no-browser HUMAN attempt through direct Webshare and final seq5+seq6 combo.")
    parser.add_argument("--session", default="")
    parser.add_argument("--base-user", default="ibtvqcnm")
    parser.add_argument("--country", default="JP")
    parser.add_argument("--password", default="e5wruchrofwl")
    parser.add_argument("--host", default="p.webshare.io")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--gap-seconds", type=float, default=0.1816)
    parser.add_argument("--pre-stk-ns", action="store_true")
    parser.add_argument("--pre-captcha-get", action="store_true")
    parser.add_argument("--pre-captcha-head", action="store_true")
    parser.add_argument("--delay-after-pre-captcha-head", type=float, default=0.0)
    parser.add_argument("--pre-iframe-get", action="store_true")
    parser.add_argument("--pre-main-get", action="store_true")
    parser.add_argument("--pre-main-head", action="store_true")
    parser.add_argument("--include-first-failure-history", action="store_true")
    parser.add_argument("--combo-header-mode", choices=["safe", "runtime-exact"], default="safe")
    parser.add_argument("--combo-include-proxy-authorization", action="store_true")
    parser.add_argument("--combo-parallel", action="store_true")
    parser.add_argument("--combo-transport", choices=["https-threads", "h2-single-session"], default="https-threads")
    parser.add_argument("--combo-h2-body-order", choices=["normal", "seq6-body-first"], default="normal")
    parser.add_argument("--combo-aeax-source", choices=["template", "offline-ng"], default="offline-ng")
    parser.add_argument("--combo-bzt-source", choices=["solve", "template"], default="solve")
    parser.add_argument("--combo-stack-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--combo-tail-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-inner-uuid-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-non-px-activity-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-seq6-activity-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-payload-uuid-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-pc-uuid-source", choices=["payload", "fresh", "template"], default="payload")
    parser.add_argument("--combo-marker-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-form-outer-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--combo-payload-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--combo-pc-source", choices=["computed", "template-exact"], default="computed")
    parser.add_argument("--combo-body-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    started = time.time()
    session = args.session or f"{args.base_user}-{args.country.upper()}-{int(started) * 1000}"
    proxy_url = f"http://{session}:{args.password}@{args.host}:{args.port}"
    env = dict(os.environ)
    env["HSPROTECT_PROXY_URL"] = proxy_url
    steps: dict[str, Any] = {}
    fresh_uuid = str(uuid.uuid1()) if args.pre_stk_ns else ""

    def step(name: str, cmd: list[str]) -> dict[str, Any]:
        out = run_json(cmd, env=env, timeout=args.timeout + 10)
        steps[name] = {"cmd": cmd, "summary": out}
        return out

    if args.pre_stk_ns:
        pre_stk = step("preStkNs", [
            "python3", "tools/probe_human_stk_ns.py",
            "--uuid", fresh_uuid,
            "--send",
            "--timeout", str(args.timeout),
            "--include-proxy-authorization",
        ])
    else:
        pre_stk = {}

    bootstrap_cmd = ["python3", "tools/probe_human_fresh_bootstrap.py", "--send", "--timeout", str(args.timeout)]
    if fresh_uuid:
        bootstrap_cmd.extend(["--uuid", fresh_uuid])
    bootstrap = step("bootstrap", bootstrap_cmd)
    second = step("second", ["python3", "tools/probe_human_fresh_second_request.py", "--bootstrap-audit", bootstrap["json"], "--send", "--timeout", str(args.timeout)])
    sequence = step("sequence", ["python3", "tools/probe_human_fresh_sequence.py", "--second-probe", second["json"], "--send", "--timeout", str(args.timeout)])
    bundle = step("bundle", ["python3", "tools/probe_human_fresh_bundle.py", "--sequence-probe", sequence["json"], "--send", "--timeout", str(args.timeout)])

    first_pow = run_json(["node", "tools/solve_collector_pow_from_response.mjs", bundle["json"]])
    steps["firstPow"] = {"summary": first_pow}

    if args.include_first_failure_history:
        first_ninput = solved_pow_value(first_pow["jsonPath"])
        first_uuid = read_json(bundle["json"])["material"]["freshState"]["uuid"]
        first_nq_out = REPO / "output/protocol_reverse/wasm" / f"compute_wasm_ng_nq_once_first_failure_{first_uuid.split('-')[0]}_{int(started)}_with_ng.json"
        first_nq = run_json([
            "node", "tools/compute_wasm_nq_once.mjs",
            "--wasm", WASM,
            "--pxuuid", first_uuid,
            "--ninput", first_ninput,
            "--call-ng", "1",
            "--out", str(first_nq_out),
        ])
        steps["firstNq"] = {"summary": first_nq, "nInput": first_ninput}
        first_px = step("firstFailurePx561", [
            "python3", "tools/probe_human_fresh_px561.py",
            "--fresh-bundle", bundle["json"],
            "--pow-json", first_pow["jsonPath"],
            "--nq-json", str(first_nq_out),
            "--ng-nq-json", str(first_nq_out),
            "--template-line", "566",
            "--seq", "2",
            "--rsc", "3",
            "--send",
            "--timeout", str(args.timeout),
        ])
        first_px_state = step("firstFailureState", [
            "python3", "tools/build_state_from_px561_probe_response.py",
            first_px["json"],
        ])
        progression = step("progression", [
            "python3", "tools/probe_human_fresh_bundle_progression.py",
            "--fresh-bundle", bundle["json"],
            "--state-probe", first_px_state["json"],
            "--steps", "bundle_seq3,bundle_seq4",
            "--send",
            "--timeout", str(args.timeout),
        ])
    else:
        progression = step("progression", ["python3", "tools/probe_human_fresh_bundle_progression.py", "--fresh-bundle", bundle["json"], "--send", "--timeout", str(args.timeout)])
    progression_pow = run_json(["node", "tools/solve_collector_pow_from_response.mjs", progression["json"]])
    steps["progressionPow"] = {"summary": progression_pow}

    if args.pre_captcha_get:
        step("preCaptchaGet", [
            "python3", "tools/probe_human_captcha_head.py",
            "--state-probe", progression["json"],
            "--method", "GET",
            "--send",
            "--timeout", str(args.timeout),
            "--include-proxy-authorization",
        ])
    if args.pre_iframe_get:
        step("preIframeGet", [
            "python3", "tools/probe_human_asset_request.py",
            "--state-probe", progression["json"],
            "--runtime-line", "171",
            "--send",
            "--timeout", str(args.timeout),
            "--include-proxy-authorization",
        ])
    if args.pre_main_get:
        step("preMainGet", [
            "python3", "tools/probe_human_asset_request.py",
            "--state-probe", progression["json"],
            "--runtime-line", "185",
            "--send",
            "--timeout", str(args.timeout),
            "--include-proxy-authorization",
        ])
    if args.pre_main_head:
        step("preMainHead", [
            "python3", "tools/probe_human_asset_request.py",
            "--state-probe", progression["json"],
            "--runtime-line", "265",
            "--send",
            "--timeout", str(args.timeout),
            "--include-proxy-authorization",
        ])
    if args.pre_captcha_head:
        step("preCaptchaHead", [
            "python3", "tools/probe_human_captcha_head.py",
            "--state-probe", progression["json"],
            "--method", "HEAD",
            "--send",
            "--timeout", str(args.timeout),
            "--include-proxy-authorization",
        ])
        if args.delay_after_pre_captcha_head > 0:
            time.sleep(args.delay_after_pre_captcha_head)
            steps["delayAfterPreCaptchaHead"] = {
                "summary": {
                    "seconds": args.delay_after_pre_captcha_head,
                    "startedAt": time.time() - args.delay_after_pre_captcha_head,
                    "endedAt": time.time(),
                }
            }

    ninput = solved_pow_value(progression_pow["jsonPath"])
    nq_out = REPO / "output/protocol_reverse/wasm" / f"compute_wasm_ng_nq_once_fresh_progression_{read_json(progression['json'])['finalState']['uuid'].split('-')[0]}_{int(started)}_with_ng.json"
    nq = run_json([
        "node", "tools/compute_wasm_nq_once.mjs",
        "--wasm", WASM,
        "--pxuuid", read_json(progression["json"])["finalState"]["uuid"],
        "--ninput", ninput,
        "--call-ng", "1",
        "--out", str(nq_out),
    ])
    steps["nq"] = {"summary": nq, "nInput": ninput}

    combo = step("seq5Seq6Combo", [
        "python3", "tools/probe_human_seq5_seq6_combo.py",
        "--state-probe", progression["json"],
        "--pow-json", progression_pow["jsonPath"],
        "--nq-json", str(nq_out),
        "--ng-nq-json", str(nq_out),
        "--aeax-source", args.combo_aeax_source,
        "--bzt-source", args.combo_bzt_source,
        "--stack-source", args.combo_stack_source,
        "--tail-source", args.combo_tail_source,
        "--inner-uuid-source", args.combo_inner_uuid_source,
        "--non-px-activity-source", args.combo_non_px_activity_source,
        "--seq6-activity-source", args.combo_seq6_activity_source,
        "--payload-uuid-source", args.combo_payload_uuid_source,
        "--pc-uuid-source", args.combo_pc_uuid_source,
        "--marker-source", args.combo_marker_source,
        "--form-outer-source", args.combo_form_outer_source,
        "--payload-source", args.combo_payload_source,
        "--pc-source", args.combo_pc_source,
        "--body-source", args.combo_body_source,
        "--header-mode", args.combo_header_mode,
        "--transport", args.combo_transport,
        "--h2-body-order", args.combo_h2_body_order,
        "--gap-seconds", str(args.gap_seconds),
        "--timeout", str(args.timeout),
    ]
        + (["--include-proxy-authorization"] if args.combo_include_proxy_authorization else [])
        + (["--parallel"] if args.combo_parallel else [])
    )

    result = {
        "startedAt": started,
        "session": session,
        "proxyEndpoint": f"http://{args.host}:{args.port}",
        "comboHeaderMode": args.combo_header_mode,
        "comboIncludeProxyAuthorization": args.combo_include_proxy_authorization,
        "comboParallel": args.combo_parallel,
        "comboTransport": args.combo_transport,
        "comboH2BodyOrder": args.combo_h2_body_order,
        "preStkNs": bool(args.pre_stk_ns),
        "preCaptchaGet": bool(args.pre_captcha_get),
        "preCaptchaHead": bool(args.pre_captcha_head),
        "delayAfterPreCaptchaHead": args.delay_after_pre_captcha_head,
        "preIframeGet": bool(args.pre_iframe_get),
        "preMainGet": bool(args.pre_main_get),
        "preMainHead": bool(args.pre_main_head),
        "includeFirstFailureHistory": bool(args.include_first_failure_history),
        "comboSources": {
            "stack": args.combo_stack_source,
            "tail": args.combo_tail_source,
            "innerUuid": args.combo_inner_uuid_source,
            "nonPxActivity": args.combo_non_px_activity_source,
            "seq6Activity": args.combo_seq6_activity_source,
            "payloadUuid": args.combo_payload_uuid_source,
            "pcUuid": args.combo_pc_uuid_source,
            "marker": args.combo_marker_source,
            "formOuter": args.combo_form_outer_source,
            "payload": args.combo_payload_source,
            "pc": args.combo_pc_source,
            "body": args.combo_body_source,
            "aeax": args.combo_aeax_source,
            "bzt": args.combo_bzt_source,
        },
        "steps": steps,
        "checks": {
            "bootstrap200": bootstrap.get("status") == 200,
            "preStkNs200": (pre_stk.get("status") == 200) if args.pre_stk_ns else None,
            "preCaptchaGetOk": (
                (((steps.get("preCaptchaGet") or {}).get("summary") or {}).get("checks") or {}).get("httpStatusOkOrCacheable") is True
            ) if args.pre_captcha_get else None,
            "preCaptchaHeadOk": (
                (((steps.get("preCaptchaHead") or {}).get("summary") or {}).get("checks") or {}).get("httpStatusOkOrCacheable") is True
            ) if args.pre_captcha_head else None,
            "preIframeGetOk": (
                (((steps.get("preIframeGet") or {}).get("summary") or {}).get("checks") or {}).get("httpStatusOkOrCacheable") is True
            ) if args.pre_iframe_get else None,
            "preMainGetOk": (
                (((steps.get("preMainGet") or {}).get("summary") or {}).get("checks") or {}).get("httpStatusOkOrCacheable") is True
            ) if args.pre_main_get else None,
            "preMainHeadOk": (
                (((steps.get("preMainHead") or {}).get("summary") or {}).get("checks") or {}).get("httpStatusOkOrCacheable") is True
            ) if args.pre_main_head else None,
            "second200": second.get("status") == 200,
            "sequence200": sequence.get("statuses") == [200, 200],
            "bundle200Pow": bundle.get("status") == 200 and bundle.get("hasPowResult") is True,
            "firstFailurePx561Rejected": (
                (((steps.get("firstFailurePx561") or {}).get("summary") or {}).get("hasSuccessHandler") is False)
                and (((steps.get("firstFailurePx561") or {}).get("summary") or {}).get("status") == 200)
            ) if args.include_first_failure_history else None,
            "firstFailureStateUpdated": all(
                (((steps.get("firstFailureState") or {}).get("summary") or {}).get("checks") or {}).get(k) is True
                for k in ["px3Changed", "pxdeChanged"]
            ) if args.include_first_failure_history else None,
            "progression200Pow": (
                progression.get("statuses") == [200, 200] and progression.get("hasPow") == [False, True]
            ) if args.include_first_failure_history else (
                progression.get("statuses") == [200, 200, 200] and progression.get("hasPow") == [False, False, True]
            ),
            "comboAnySuccess": (combo.get("checks") or {}).get("anySuccessHandler") is True,
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"direct_webshare_attempt_{session}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "session": session, "checks": result["checks"], "combo": combo}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
