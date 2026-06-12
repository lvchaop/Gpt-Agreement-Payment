#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/captcha_head_control_audit.json"

HEAD = PROTO / "captcha_head_probe/captcha_head_probe_705bae4a-65c9-11f1-8d53-62666cc2b93d_1781205230.json"
PX = PROTO / "fresh_px561_probe/fresh_px561_probe_705bae4a-65c9-11f1-8d53-62666cc2b93d_1781205262.json"
DIFF = PROTO / "px561_compare/fresh_px561_probe_705bae4a-65c9-11f1-8d53-62666cc2b93d_1781205262_full_activity_diff.json"
S00_RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"


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
    head = read_json(HEAD)
    px = read_json(PX)
    diff = read_json(DIFF)
    runtime_head = read_jsonl_line(S00_RUNTIME, 692)
    runtime_success = read_jsonl_line(S00_RUNTIME, 933)
    decoded = px.get("decoded") or {}
    checks = {
        "s00ObservedHeadBeforeSuccess": runtime_head.get("method") == "HEAD"
        and "captcha.hsprotect.net/PXzC5j78di/captcha.js" in str(runtime_head.get("url") or "")
        and float(runtime_head.get("t") or 0) < float(runtime_success.get("t") or 0),
        "freshHeadSent": head.get("sent") is True,
        "freshHeadHttp200": (head.get("response") or {}).get("status") == 200,
        "freshHeadUsesFreshUuidAndVid": (head.get("checks") or {}).get("urlUsesFreshUuid") is True
        and (head.get("checks") or {}).get("urlUsesFreshVid") is True,
        "postHeadPxSent": px.get("sent") is True,
        "postHeadPxHttp200": (px.get("response") or {}).get("status") == 200,
        "postHeadPxRejected": decoded.get("hasSuccessHandler") is False
        and "oIIoIooo" in (decoded.get("handlers") or []),
        "postHeadDecodedActivitiesEqualS00Line922": (diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
        "postHeadPx561ActivityEqualS00Line922": (diff.get("checks") or {}).get("px561ActivityEqual") is True,
        "postHeadNonPxActivitiesEqualS00Line922": (diff.get("checks") or {}).get("nonPx561ActivitiesAllEqual") is True,
    }
    result = {
        "purpose": "Control whether replaying the captcha.js HEAD request observed before s00 success is sufficient to make a fresh exact-activities PX561 request accepted.",
        "evidence": {
            "s00RuntimeTrace": str(S00_RUNTIME.resolve()),
            "s00HeadLine": {
                "line": 692,
                "t": runtime_head.get("t"),
                "method": runtime_head.get("method"),
                "url": runtime_head.get("url"),
            },
            "s00SuccessCollectorLine": {
                "line": 933,
                "t": runtime_success.get("t"),
                "url": runtime_success.get("url"),
            },
            "freshHeadProbe": {
                "path": str(HEAD.resolve()),
                "startedAt": head.get("startedAt"),
                "status": (head.get("response") or {}).get("status"),
                "url": ((head.get("request") or {}).get("url")),
                "checks": head.get("checks"),
            },
            "postHeadPx561Probe": {
                "path": str(PX.resolve()),
                "startedAt": px.get("startedAt"),
                "status": (px.get("response") or {}).get("status"),
                "handlers": decoded.get("handlers"),
                "hasSuccessHandler": decoded.get("hasSuccessHandler"),
                "checks": (px.get("material") or {}).get("checks"),
                "meta": {
                    key: ((px.get("material") or {}).get("meta") or {}).get(key)
                    for key in [
                        "templateJsTraceLine",
                        "seq",
                        "rsc",
                        "payloadUuidSource",
                        "pcUuidSource",
                        "markerSource",
                        "formOuterSource",
                        "markerJo",
                    ]
                },
            },
            "activityDiff": {
                "path": str(DIFF.resolve()),
                "checks": diff.get("checks"),
                "activityCounts": diff.get("activityCounts"),
                "activityTypes": diff.get("activityTypes"),
            },
        },
        "checks": checks,
        "conclusion": (
            "s00 has an observed captcha.js HEAD request before the accepted collector line933. "
            "A fresh session sent the same kind of HEAD request patched to its fresh uuid/vid and received HTTP 200, "
            "then sent a collector request whose decoded activities exactly equal s00 line922. "
            "The collector still returned oIIoIooo|-1. This disproves captcha HEAD replay alone as the missing acceptance condition."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
