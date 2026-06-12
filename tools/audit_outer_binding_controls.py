#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/outer_binding_controls_audit.json"
CONTROLS = {
    "freshOuterFreshMarker": {
        "probe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201361.json",
        "activityDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201361_full_activity_diff.json",
    },
    "staleOuterExactBodyDryRun": {
        "probe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201638.json",
        "activityDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201638_full_activity_diff.json",
    },
    "freshOuterTemplateMarker": {
        "probe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201693.json",
        "activityDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201693_full_activity_diff.json",
    },
}
EXACT_REPLAY = PROTO / "goal_audit/s00_exact_success_replay_live_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def control_summary(name: str, cfg: dict[str, Path]) -> dict[str, Any]:
    probe = read_json(cfg["probe"])
    diff = read_json(cfg["activityDiff"])
    body = (probe.get("material") or {}).get("body") or ""
    params = parse_form(body)
    meta = (probe.get("material") or {}).get("meta") or {}
    checks = (probe.get("material") or {}).get("checks") or {}
    decoded = probe.get("decoded") or {}
    response = probe.get("response") or {}
    return {
        "name": name,
        "probe": str(cfg["probe"].resolve()),
        "activityDiff": str(cfg["activityDiff"].resolve()),
        "sent": probe.get("sent"),
        "status": response.get("status"),
        "handlers": decoded.get("handlers"),
        "hasSuccessHandler": decoded.get("hasSuccessHandler"),
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "bodyLen": len(body.encode()),
        "params": {key: params.get(key) for key in ["uuid", "cs", "pc", "sid", "p1", "vid", "ci", "cts", "seq", "rsc"]},
        "meta": {
            "payloadUuidSource": meta.get("payloadUuidSource"),
            "markerSource": meta.get("markerSource"),
            "formOuterSource": meta.get("formOuterSource"),
            "payloadUuid": meta.get("payloadUuid"),
            "markerJo": meta.get("markerJo"),
            "pc": meta.get("pc"),
        },
        "materialChecks": checks,
        "activityChecks": diff.get("checks"),
    }


def main() -> int:
    controls = {name: control_summary(name, cfg) for name, cfg in CONTROLS.items()}
    exact = read_json(EXACT_REPLAY)
    result = {
        "purpose": "Control outer binding variables after decoded activity-array equality was proven insufficient.",
        "controls": controls,
        "exactReplay": {
            "path": str(EXACT_REPLAY.resolve()),
            "checks": exact.get("checks"),
            "observedSuccess": exact.get("observedSuccess"),
            "liveReplay": exact.get("liveReplay"),
        },
        "checks": {
            "freshOuterFreshMarkerActivitiesEqualRejected": (
                (controls["freshOuterFreshMarker"]["activityChecks"] or {}).get("wholeActivitiesEqual") is True
                and controls["freshOuterFreshMarker"]["hasSuccessHandler"] is False
            ),
            "freshOuterTemplateMarkerActivitiesEqualRejected": (
                (controls["freshOuterTemplateMarker"]["activityChecks"] or {}).get("wholeActivitiesEqual") is True
                and controls["freshOuterTemplateMarker"]["hasSuccessHandler"] is False
            ),
            "templateMarkerNotSufficient": controls["freshOuterTemplateMarker"]["hasSuccessHandler"] is False,
            "staleExactBodyKnownRejectedByPriorLiveReplay": ((exact.get("checks") or {}).get("liveReplayReturnsFailure") is True),
            "staleDryRunBodyMatchesExactReplay": controls["staleOuterExactBodyDryRun"]["bodySha256"]
            == ((exact.get("observedSuccess") or {}).get("bodySha256")),
        },
        "conclusion": (
            "With decoded activities held equal to s00 line922, fresh outer state fails with both fresh and template marker/qi encoding. "
            "The fully stale exact body is byte-rebuildable and already known to fail on live replay. "
            "This eliminates marker choice as a single-variable fix and keeps the remaining boundary at coherent live outer/session/cookie/server-side state rather than decoded activity content alone."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
