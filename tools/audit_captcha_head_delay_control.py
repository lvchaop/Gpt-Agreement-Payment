#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/captcha_head_delay_control_audit.json"

RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
CONTROL = PROTO / "head_delay_px561_probe/head_delay_px561_probe_705bae4a-65c9-11f1-8d53-62666cc2b93d_1781205619.json"
DIFF = PROTO / "px561_compare/fresh_px561_probe_705bae4a-65c9-11f1-8d53-62666cc2b93d_1781205672_full_activity_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_line(path: Path, line_no: int) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if idx == line_no:
                row = json.loads(line)
                row["_line"] = idx
                return row
    raise KeyError(line_no)


def main() -> int:
    control = read_json(CONTROL)
    diff = read_json(DIFF)
    s00_head = read_jsonl_line(RUNTIME, 692)
    s00_success = read_jsonl_line(RUNTIME, 933)
    s00_delta = float(s00_success["t"]) - float(s00_head["t"])
    timing = control.get("timing") or {}
    px = control.get("px561") or {}
    head = control.get("head") or {}
    checks = {
        "s00HeadToSuccessDeltaKnown": 52.0 < s00_delta < 54.0,
        "controlHeadHttp200": head.get("status") == 200,
        "controlDelayWithinOneSecond": (control.get("checks") or {}).get("delayWithinOneSecond") is True,
        "controlDelayMatchesS00WithinOneSecond": abs(float(timing.get("actualHeadStartToBeforePxSeconds") or 0) - s00_delta) <= 1.0,
        "controlPxHttp200": px.get("status") == 200,
        "controlPxRejected": px.get("hasSuccessHandler") is False
        and "oIIoIooo" in (px.get("handlers") or []),
        "controlDecodedActivitiesEqualS00Line922": (diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
        "controlPx561ActivityEqualS00Line922": (diff.get("checks") or {}).get("px561ActivityEqual") is True,
        "controlNonPxActivitiesEqualS00Line922": (diff.get("checks") or {}).get("nonPx561ActivitiesAllEqual") is True,
    }
    result = {
        "purpose": "Control whether matching the observed s00 captcha HEAD -> success timing interval is sufficient for fresh exact-activities PX561 acceptance.",
        "s00Timing": {
            "runtimeTrace": str(RUNTIME.resolve()),
            "headLine": 692,
            "headT": s00_head.get("t"),
            "successRequestLine": 933,
            "successT": s00_success.get("t"),
            "headToSuccessSeconds": s00_delta,
        },
        "control": {
            "path": str(CONTROL.resolve()),
            "head": head,
            "timing": timing,
            "px561": px,
            "checks": control.get("checks"),
        },
        "activityDiff": {
            "path": str(DIFF.resolve()),
            "checks": diff.get("checks"),
            "activityCounts": diff.get("activityCounts"),
            "activityTypes": diff.get("activityTypes"),
        },
        "checks": checks,
        "conclusion": (
            "The accepted s00 runtime has about 52.8055 seconds between captcha.js HEAD and the accepted collector request. "
            "The fresh control sent captcha HEAD, waited the same interval within one second, then sent a decoded-activities-exact line922 collector request. "
            "The collector still returned oIIoIooo|-1. Therefore matching the HEAD request and its observed timing interval is not sufficient."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
