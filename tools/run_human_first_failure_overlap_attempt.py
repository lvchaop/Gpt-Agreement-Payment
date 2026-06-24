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
OUT_DIR = REPO / "output/protocol_reverse/first_failure_overlap_attempt"
WASM = "output/protocol_reverse/wasm/captcha_s00ld1lglrw0_1781191381.wasm"


def run_json(cmd: list[str], env: dict[str, str], timeout: float) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=REPO, env=env, text=True, capture_output=True, check=False, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(json.dumps({
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }, ensure_ascii=False))
    return json.loads(proc.stdout)


def read_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.is_absolute():
        p = REPO / p
    return json.loads(p.read_text(encoding="utf-8"))


def solved_pow_value(pow_json: str | Path) -> str:
    doc = read_json(pow_json)
    for row in doc.get("results") or []:
        if row.get("matchesTarget") is True and row.get("value"):
            return str(row["value"])
    raise RuntimeError(f"no solved pow in {pow_json}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a fresh no-browser chain through first bundle POW and first-failure overlap control.")
    parser.add_argument("--session", default="")
    parser.add_argument("--base-user", default="ibtvqcnm")
    parser.add_argument("--country", default="JP")
    parser.add_argument("--password", default="e5wruchrofwl")
    parser.add_argument("--host", default="p.webshare.io")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=35.0)
    parser.add_argument("--h2-body-order", choices=["normal", "seq3-body-first", "seq3-response-before-seq2-body"], default="seq3-response-before-seq2-body")
    parser.add_argument("--gap-seconds", type=float, default=0.5344)
    parser.add_argument("--header-mode", choices=["safe", "runtime-exact"], default="runtime-exact")
    parser.add_argument("--aeax-source", choices=["template", "offline-ng"], default="offline-ng")
    parser.add_argument("--bzt-source", choices=["solve", "template"], default="solve")
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--run-final-combo", action="store_true")
    parser.add_argument("--final-stack-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--final-tail-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--final-inner-uuid-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--final-non-px-activity-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--final-seq6-activity-source", choices=["fresh", "template"], default="template")
    parser.add_argument("--final-aeax-source", choices=["template", "offline-ng"], default="template")
    parser.add_argument("--final-bzt-source", choices=["solve", "template"], default="template")
    parser.add_argument("--final-payload-uuid-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--final-pc-uuid-source", choices=["payload", "fresh", "template"], default="payload")
    parser.add_argument("--final-marker-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--final-form-outer-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--final-payload-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--final-pc-source", choices=["computed", "template-exact"], default="computed")
    parser.add_argument("--final-body-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    started = time.time()
    session = args.session or f"{args.base_user}-{args.country.upper()}-{int(started) * 1000}"
    env = dict(os.environ)
    env["HSPROTECT_PROXY_URL"] = f"http://{session}:{args.password}@{args.host}:{args.port}"
    steps: dict[str, Any] = {}

    def step(name: str, cmd: list[str]) -> dict[str, Any]:
        out = run_json(cmd, env, args.timeout + 20)
        steps[name] = {"cmd": cmd, "summary": out}
        return out

    bootstrap = step("bootstrap", ["python3", "tools/probe_human_fresh_bootstrap.py", "--send", "--timeout", str(args.timeout)])
    second = step("second", ["python3", "tools/probe_human_fresh_second_request.py", "--bootstrap-audit", bootstrap["json"], "--send", "--timeout", str(args.timeout)])
    sequence = step("sequence", ["python3", "tools/probe_human_fresh_sequence.py", "--second-probe", second["json"], "--send", "--timeout", str(args.timeout)])
    bundle = step("bundle", ["python3", "tools/probe_human_fresh_bundle.py", "--sequence-probe", sequence["json"], "--send", "--timeout", str(args.timeout)])
    first_pow = run_json(["node", "tools/solve_collector_pow_from_response.mjs", bundle["json"]], env, args.timeout + 20)
    steps["firstPow"] = {"summary": first_pow}
    first_ninput = solved_pow_value(first_pow["jsonPath"])
    first_uuid = read_json(bundle["json"])["material"]["freshState"]["uuid"]
    nq_out = REPO / "output/protocol_reverse/wasm" / f"compute_wasm_ng_nq_once_first_overlap_{first_uuid.split('-')[0]}_{int(started)}_with_ng.json"
    first_nq = run_json([
        "node", "tools/compute_wasm_nq_once.mjs",
        "--wasm", WASM,
        "--pxuuid", first_uuid,
        "--ninput", first_ninput,
        "--call-ng", "1",
        "--out", str(nq_out),
    ], env, args.timeout + 20)
    steps["firstNq"] = {"summary": first_nq, "nInput": first_ninput}
    overlap_cmd = [
        ".venv/bin/python", "tools/probe_human_first_failure_overlap.py",
        "--fresh-bundle", bundle["json"],
        "--pow-json", first_pow["jsonPath"],
        "--nq-json", str(nq_out),
        "--ng-nq-json", str(nq_out),
        "--h2-body-order", args.h2_body_order,
        "--gap-seconds", str(args.gap_seconds),
        "--header-mode", args.header_mode,
        "--aeax-source", args.aeax_source,
        "--bzt-source", args.bzt_source,
        "--timeout", str(args.timeout),
    ]
    if args.include_proxy_authorization:
        overlap_cmd.append("--include-proxy-authorization")
    overlap = step("firstFailureOverlap", overlap_cmd)
    final_combo = None
    seq4 = None
    progression_pow = None
    if args.run_final_combo:
        seq4 = step("seq4AfterOverlap", [
            "python3", "tools/probe_human_fresh_bundle_progression.py",
            "--fresh-bundle", bundle["json"],
            "--state-probe", overlap["json"],
            "--steps", "bundle_seq4",
            "--send",
            "--timeout", str(args.timeout),
            "--header-mode", args.header_mode,
        ] + (["--include-proxy-authorization"] if args.include_proxy_authorization else []))
        progression_pow = run_json(["node", "tools/solve_collector_pow_from_response.mjs", seq4["json"]], env, args.timeout + 20)
        steps["progressionPow"] = {"summary": progression_pow}
        ninput = solved_pow_value(progression_pow["jsonPath"])
        nq2_out = REPO / "output/protocol_reverse/wasm" / f"compute_wasm_ng_nq_once_forced_overlap_final_{first_uuid.split('-')[0]}_{int(started)}_with_ng.json"
        nq2 = run_json([
            "node", "tools/compute_wasm_nq_once.mjs",
            "--wasm", WASM,
            "--pxuuid", first_uuid,
            "--ninput", ninput,
            "--call-ng", "1",
            "--out", str(nq2_out),
        ], env, args.timeout + 20)
        steps["finalNq"] = {"summary": nq2, "nInput": ninput}
        combo_cmd = [
            ".venv/bin/python", "tools/probe_human_seq5_seq6_combo.py",
            "--state-probe", seq4["json"],
            "--pow-json", progression_pow["jsonPath"],
            "--nq-json", str(nq2_out),
            "--ng-nq-json", str(nq2_out),
            "--aeax-source", args.final_aeax_source,
            "--bzt-source", args.final_bzt_source,
            "--stack-source", args.final_stack_source,
            "--tail-source", args.final_tail_source,
            "--inner-uuid-source", args.final_inner_uuid_source,
            "--non-px-activity-source", args.final_non_px_activity_source,
            "--seq6-activity-source", args.final_seq6_activity_source,
            "--payload-uuid-source", args.final_payload_uuid_source,
            "--pc-uuid-source", args.final_pc_uuid_source,
            "--marker-source", args.final_marker_source,
            "--form-outer-source", args.final_form_outer_source,
            "--payload-source", args.final_payload_source,
            "--pc-source", args.final_pc_source,
            "--body-source", args.final_body_source,
            "--header-mode", args.header_mode,
            "--transport", "h2-single-session",
            "--h2-body-order", "seq6-response-before-seq5-body",
            "--gap-seconds", "0.1816",
            "--timeout", str(args.timeout),
        ]
        if args.include_proxy_authorization:
            combo_cmd.append("--include-proxy-authorization")
        final_combo = step("finalSeq5Seq6Combo", combo_cmd)

    result = {
        "startedAt": started,
        "session": session,
        "proxyEndpoint": f"http://{args.host}:{args.port}",
        "h2BodyOrder": args.h2_body_order,
        "gapSeconds": args.gap_seconds,
        "steps": steps,
        "checks": {
            "bootstrap200": bootstrap.get("status") == 200,
            "second200": second.get("status") == 200,
            "sequence200": sequence.get("statuses") == [200, 200],
            "bundle200Pow": bundle.get("status") == 200 and bundle.get("hasPowResult") is True,
            "overlapSeq3ResponseFirst": (overlap.get("checks") or {}).get("seq3ResponseFirst") is True,
            "overlapSeq2Rejected": (overlap.get("checks") or {}).get("seq2Rejected") is True,
            "overlapFinalStateHasPow": (overlap.get("checks") or {}).get("finalStateHasPow") is True,
            "seq4AfterOverlap200Pow": (
                seq4 is not None
                and seq4.get("statuses") == [200]
                and seq4.get("hasPow") == [True]
            ) if args.run_final_combo else None,
            "finalComboAnySuccess": ((final_combo or {}).get("checks") or {}).get("anySuccessHandler") is True if args.run_final_combo else None,
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"first_failure_overlap_attempt_{session}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "session": session, "checks": result["checks"], "overlap": overlap, "finalCombo": final_combo}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
