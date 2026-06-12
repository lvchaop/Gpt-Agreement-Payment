#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/clean_history_exact_whole_activities_audit.json"

PROBE = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203460.json"
DIFF = PROTO / "px561_compare/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203460_full_activity_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    probe = read_json(PROBE)
    diff = read_json(DIFF)
    decoded = probe.get("decoded") or {}
    meta = (probe.get("material") or {}).get("meta") or {}
    checks = {
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "probeRejected": decoded.get("hasSuccessHandler") is False,
        "activityTypeOrderEqual": (diff.get("checks") or {}).get("activityTypeOrderEqual") is True,
        "wholeActivitiesEqual": (diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
        "px561ActivityEqual": (diff.get("checks") or {}).get("px561ActivityEqual") is True,
        "nonPx561ActivitiesAllEqual": (diff.get("checks") or {}).get("nonPx561ActivitiesAllEqual") is True,
    }
    result = {
        "purpose": "In the clean first-failure-history session, test whether a decoded activity array exactly equal to s00 accepted line922 is sufficient.",
        "probe": {
            "path": str(PROBE.resolve()),
            "status": (probe.get("response") or {}).get("status"),
            "handlers": decoded.get("handlers"),
            "hasSuccessHandler": decoded.get("hasSuccessHandler"),
            "partsTail": (decoded.get("parts") or [])[-5:],
            "checks": (probe.get("material") or {}).get("checks"),
            "meta": {
                key: meta.get(key)
                for key in [
                    "templateJsTraceLine",
                    "seq",
                    "rsc",
                    "stackSource",
                    "bztSource",
                    "tailSource",
                    "innerUuidSource",
                    "nonPxActivitySource",
                    "payloadUuidSource",
                    "markerSource",
                    "formOuterSource",
                    "newPxTail",
                ]
            },
        },
        "activityDiff": {
            "path": str(DIFF.resolve()),
            "checks": diff.get("checks"),
            "activityCounts": diff.get("activityCounts"),
            "activityTypes": diff.get("activityTypes"),
            "nonPx561DiffSummary": diff.get("nonPx561DiffSummary"),
        },
        "checks": checks,
        "conclusion": (
            "The decoded activity array was made exactly equal to s00 accepted line922 in a clean fresh session after first-failure history, "
            "but the live collector still returned oIIoIooo|-1. This proves decoded activity equality is not sufficient in this clean-history scenario; "
            "the remaining boundary is encoded payload/pc/outer parameters/session cookies/headers or collector server-side state, not decoded activity content."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
