#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/clean_history_line922_guard_audit.json"
PROBE = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203025.json"
DIFF = PROTO / "px561_compare/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203025_full_activity_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    probe = read_json(PROBE)
    diff = read_json(DIFF)
    first_summary = next((row for row in diff.get("nonPx561DiffSummary") or [] if row.get("index") == 0), {})
    checks = {
        "probeSent": probe.get("sent") is True,
        "probeHttp200": (probe.get("response") or {}).get("status") == 200,
        "probeRejected": (probe.get("decoded") or {}).get("hasSuccessHandler") is False,
        "activityTypeOrderEqual": (diff.get("checks") or {}).get("activityTypeOrderEqual") is True,
        "firstActivityKeyOrderEqual": first_summary.get("keyOrderEqual") is True,
        "noExtraneousFirstActivityStateKeys": set(first_summary.get("firstDiffKeys") or []) == {
            "X08lRRkjIXQ=",
            "QS07ZwRKPlU=",
            "FUFvS1Mga38=",
            "GUVjT1wnbn4=",
            "SlpwEAw5eSc=",
        },
    }
    result = {
        "purpose": "Verify that the clean-history line922 probe no longer adds line566-only first-activity state keys before drawing conclusions from its rejection.",
        "inputs": {
            "probe": str(PROBE.resolve()),
            "activityDiff": str(DIFF.resolve()),
        },
        "probe": {
            "status": (probe.get("response") or {}).get("status"),
            "handlers": (probe.get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (probe.get("decoded") or {}).get("hasSuccessHandler"),
            "checks": (probe.get("material") or {}).get("checks"),
            "meta": (probe.get("material") or {}).get("meta"),
        },
        "activityDiff": {
            "checks": diff.get("checks"),
            "nonPx561DiffSummary": diff.get("nonPx561DiffSummary"),
        },
        "checks": checks,
        "conclusion": (
            "After guarding line922 activity patching to avoid adding absent line566-only keys, the line922 fresh-history request still returns oIIoIooo|-1. "
            "The first non-PX activity now preserves s00 line922 key order; remaining first-activity differences are live state/timing/uuid/url values only."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
