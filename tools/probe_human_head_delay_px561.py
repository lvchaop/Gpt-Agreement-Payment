#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/head_delay_px561_probe"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def run_json(cmd: list[str]) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            json.dumps(
                {
                    "cmd": cmd,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-2000:],
                    "stderr": proc.stderr[-2000:],
                },
                ensure_ascii=False,
            )
        )
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        raise RuntimeError(f"command did not emit json: {cmd}\nstdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Send captcha HEAD, wait a controlled interval, then send an exact-activities PX561 probe.")
    parser.add_argument("--state-probe", type=Path, required=True)
    parser.add_argument("--pow-json", type=Path, required=True)
    parser.add_argument("--nq-json", type=Path, required=True)
    parser.add_argument("--ng-nq-json", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=52.8)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    started = time.time()
    head_cmd = [
        sys.executable,
        "tools/probe_human_captcha_head.py",
        "--state-probe",
        str(args.state_probe),
        "--send",
        "--timeout",
        str(args.timeout),
    ]
    head_summary = run_json(head_cmd)
    head_path = Path(head_summary["json"])
    head_doc = read_json(head_path)
    head_done = time.time()
    target_px_start = head_doc.get("startedAt", started) + args.delay_seconds
    sleep_seconds = max(0.0, target_px_start - time.time())
    if sleep_seconds:
        time.sleep(sleep_seconds)
    before_px = time.time()
    px_cmd = [
        sys.executable,
        "tools/probe_human_fresh_px561.py",
        "--state-probe",
        str(args.state_probe),
        "--pow-json",
        str(args.pow_json),
        "--nq-json",
        str(args.nq_json),
        "--ng-nq-json",
        str(args.ng_nq_json),
        "--template-line",
        "922",
        "--seq",
        "5",
        "--rsc",
        "6",
        "--aeax-source",
        "template",
        "--bzt-source",
        "template",
        "--stack-source",
        "template",
        "--tail-source",
        "template",
        "--inner-uuid-source",
        "template",
        "--non-px-activity-source",
        "template",
        "--payload-uuid-source",
        "fresh",
        "--pc-uuid-source",
        "payload",
        "--marker-source",
        "fresh",
        "--form-outer-source",
        "fresh",
        "--send",
        "--timeout",
        str(args.timeout),
    ]
    px_summary = run_json(px_cmd)
    px_path = Path(px_summary["json"])
    px_doc = read_json(px_path)
    result = {
        "startedAt": started,
        "sent": True,
        "inputs": {
            "stateProbe": str(args.state_probe),
            "powJson": str(args.pow_json),
            "nqJson": str(args.nq_json),
            "ngNqJson": str(args.ng_nq_json),
            "delaySeconds": args.delay_seconds,
        },
        "head": {
            "summary": head_summary,
            "path": str(head_path),
            "startedAt": head_doc.get("startedAt"),
            "status": (head_doc.get("response") or {}).get("status"),
            "elapsedSeconds": (head_doc.get("response") or {}).get("elapsedSeconds"),
            "checks": head_doc.get("checks"),
        },
        "timing": {
            "headCommandDoneAt": head_done,
            "targetPxStartAt": target_px_start,
            "sleptSeconds": sleep_seconds,
            "beforePxAt": before_px,
            "actualHeadStartToBeforePxSeconds": before_px - float(head_doc.get("startedAt") or started),
            "actualHeadDoneToBeforePxSeconds": before_px - head_done,
        },
        "px561": {
            "summary": px_summary,
            "path": str(px_path),
            "startedAt": px_doc.get("startedAt"),
            "status": (px_doc.get("response") or {}).get("status"),
            "elapsedSeconds": (px_doc.get("response") or {}).get("elapsedSeconds"),
            "handlers": (px_doc.get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (px_doc.get("decoded") or {}).get("hasSuccessHandler"),
            "checks": (px_doc.get("material") or {}).get("checks"),
        },
        "checks": {
            "headHttp200": (head_doc.get("response") or {}).get("status") == 200,
            "pxHttp200": (px_doc.get("response") or {}).get("status") == 200,
            "pxRejected": (px_doc.get("decoded") or {}).get("hasSuccessHandler") is False,
            "delayWithinOneSecond": abs((before_px - float(head_doc.get("startedAt") or started)) - args.delay_seconds) <= 1.0,
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"head_delay_px561_probe_{(read_json(args.state_probe).get('finalState') or {}).get('uuid', 'unknown')}_{int(started)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out), "checks": result["checks"], "px561": result["px561"]["summary"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
