#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/clean_history_exact_px561_control_audit.json"

TEMPLATE_TAIL_INNER_UUID = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203356.json"
TEMPLATE_TAIL_INNER_UUID_DIFF = PROTO / "px561_compare/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203356_full_activity_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    probe = read_json(TEMPLATE_TAIL_INNER_UUID)
    diff = read_json(TEMPLATE_TAIL_INNER_UUID_DIFF)
    decoded = probe.get("decoded") or {}
    meta = (probe.get("material") or {}).get("meta") or {}
    checks = {
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "probeRejected": decoded.get("hasSuccessHandler") is False,
        "activityTypeOrderEqual": (diff.get("checks") or {}).get("activityTypeOrderEqual") is True,
        "px561ActivityEqual": (diff.get("checks") or {}).get("px561ActivityEqual") is True,
        "wholeActivitiesStillDiffer": (diff.get("checks") or {}).get("wholeActivitiesEqual") is False,
        "nonPx561ActivitiesDiffer": (diff.get("checks") or {}).get("nonPx561ActivitiesAllEqual") is False,
    }
    result = {
        "purpose": "In the clean first-failure-history session, test whether making the PX561 activity exactly equal to s00 accepted line922 is sufficient.",
        "probe": {
            "path": str(TEMPLATE_TAIL_INNER_UUID.resolve()),
            "status": (probe.get("response") or {}).get("status"),
            "handlers": decoded.get("handlers"),
            "hasSuccessHandler": decoded.get("hasSuccessHandler"),
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
            "path": str(TEMPLATE_TAIL_INNER_UUID_DIFF.resolve()),
            "checks": diff.get("checks"),
            "nonPx561DiffSummary": diff.get("nonPx561DiffSummary"),
        },
        "checks": checks,
        "conclusion": (
            "With stack, PX561 tail, and PX561 inner uuid all kept from the accepted s00 line922 template, "
            "the decoded PX561 activity is exactly equal to the accepted PX561 activity, but the collector still returns oIIoIooo|-1. "
            "Therefore the remaining blocker is outside the PX561 activity itself in non-PX activities, outer/session binding, or server-side history/context."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
