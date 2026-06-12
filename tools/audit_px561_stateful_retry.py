#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
STATE = PROTO / "fresh_px561_state/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201693_state_after_response.json"
RETRY = PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201860.json"
RETRY_DIFF = PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201860_full_activity_diff.json"
OUT = PROTO / "goal_audit/px561_stateful_retry_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    state = read_json(STATE)
    retry = read_json(RETRY)
    diff = read_json(RETRY_DIFF)
    result = {
        "purpose": "Test whether carrying _px3/_pxde returned by a rejected PX561 probe into the next exact-activity PX561 request changes collector acceptance.",
        "inputs": {
            "stateFromRejectedProbe": str(STATE.resolve()),
            "retryProbe": str(RETRY.resolve()),
            "retryActivityDiff": str(RETRY_DIFF.resolve()),
        },
        "stateUpdate": {
            "checks": state.get("checks"),
            "before": state.get("before"),
            "after": state.get("after"),
        },
        "retry": {
            "status": (retry.get("response") or {}).get("status"),
            "handlers": (retry.get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (retry.get("decoded") or {}).get("hasSuccessHandler"),
            "stateInput": {key: ((retry.get("material") or {}).get("freshState") or {}).get(key) for key in ["jo", "ci", "cs", "px3", "pxde"]},
            "activityChecks": diff.get("checks"),
        },
        "checks": {
            "responseStateUpdatedPx3": (state.get("checks") or {}).get("px3Changed") is True,
            "responseStateUpdatedPxde": (state.get("checks") or {}).get("pxdeChanged") is True,
            "retryUsedUpdatedPx3": ((retry.get("material") or {}).get("freshState") or {}).get("px3") == (state.get("after") or {}).get("px3"),
            "retryUsedUpdatedPxde": ((retry.get("material") or {}).get("freshState") or {}).get("pxde") == (state.get("after") or {}).get("pxde"),
            "retryDecodedActivitiesEqual": (diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "retryRejected": (retry.get("decoded") or {}).get("hasSuccessHandler") is False,
        },
        "conclusion": (
            "A rejected exact-activity PX561 response updated _px3/_pxde, and the next PX561 request used those updated values while keeping decoded activities equal to s00 line922. "
            "Collector still returned oIIoIooo|-1. Therefore a single rejected-PX561 token/cookie update round is not sufficient to reach HUMAN success."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
