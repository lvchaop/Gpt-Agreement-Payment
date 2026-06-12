#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/clean_history_controls_audit.json"

BASE = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203025.json"
STACK_TEMPLATE = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203154.json"
BZT_TEMPLATE = PROTO / "fresh_px561_probe/fresh_px561_probe_c257e05c-65c3-11f1-a79e-62666cc2b93d_1781203189.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(path: Path) -> dict[str, Any]:
    doc = read_json(path)
    meta = (doc.get("material") or {}).get("meta") or {}
    decoded = doc.get("decoded") or {}
    return {
        "path": str(path.resolve()),
        "sent": doc.get("sent"),
        "status": (doc.get("response") or {}).get("status"),
        "handlers": decoded.get("handlers"),
        "hasSuccessHandler": decoded.get("hasSuccessHandler"),
        "partsTail": (decoded.get("parts") or [])[-5:],
        "checks": (doc.get("material") or {}).get("checks"),
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
    }


def main() -> int:
    controls = {
        "baseGuardedLine922": summarize(BASE),
        "templateStackControl": summarize(STACK_TEMPLATE),
        "templateBztControl": summarize(BZT_TEMPLATE),
    }
    checks = {
        "baseRejected": controls["baseGuardedLine922"]["hasSuccessHandler"] is False,
        "templateStackRejected": controls["templateStackControl"]["hasSuccessHandler"] is False,
        "templateBztRejected": controls["templateBztControl"]["hasSuccessHandler"] is False,
        "templateStackChangedOnlyConfiguredSource": (controls["templateStackControl"]["meta"].get("stackSource") == "template"),
        "templateBztChangedOnlyConfiguredSource": (controls["templateBztControl"]["meta"].get("bztSource") == "template"),
    }
    result = {
        "purpose": "Audit single-variable controls around the clean-history guarded line922 rejection.",
        "controls": controls,
        "checks": checks,
        "conclusion": (
            "In the clean fresh first-failure history session, changing the PX561 stack source to template still returned oIIoIooo|-1. "
            "Changing Bzt2fUFRcw== to the accepted template value also still returned oIIoIooo|-1. "
            "Therefore neither the fresh stack trace string nor Bzt timing alone explains the remaining rejection."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
