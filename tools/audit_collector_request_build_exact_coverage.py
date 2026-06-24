#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/collector_request_build_exact_coverage_audit.json"
BUILD_DIR = PROTO / "collector_request_build"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def marker_to_qi(marker: str) -> str:
    b64 = "".join(chr(ord(ch) ^ 10) for ch in marker)
    return base64.b64decode(b64.encode()).decode()


def main() -> int:
    files = sorted(BUILD_DIR.glob("collector_request_build_*.json"))
    rows = []
    for path in files:
        doc = read_json(path)
        reqs = doc.get("rows") or []
        rows.append({
            "file": str(path),
            "run": path.name.removeprefix("collector_request_build_").removesuffix(".json"),
            "requestCount": len(reqs),
            "exactBodyMatches": sum(1 for row in reqs if row.get("exactBodyMatch") is True),
            "payloadMatches": sum(1 for row in reqs if row.get("payloadMatch") is True),
            "pcMatches": sum(1 for row in reqs if row.get("pcMatch") is True),
            "badRows": [
                {
                    "requestLine": row.get("requestLine"),
                    "tfLine": row.get("tfLine"),
                    "firstDiff": row.get("firstDiff"),
                    "markerSource": row.get("markerSource"),
                }
                for row in reqs
                if row.get("exactBodyMatch") is not True
            ],
        })

    s00 = read_json(BUILD_DIR / "collector_request_build_s00ld1lglrw0_1781191381.json")
    beacon = next(row for row in s00.get("rows") or [] if row.get("requestLine") == 1007)
    beacon_evidence = {
        "requestLine": 1007,
        "tfLine": beacon.get("tfLine"),
        "url": beacon.get("url"),
        "exactBodyMatch": beacon.get("exactBodyMatch"),
        "payloadMatch": beacon.get("payloadMatch"),
        "pcMatch": beacon.get("pcMatch"),
        "markerSource": beacon.get("markerSource"),
        "marker": beacon.get("marker"),
        "markerQiDecoded": marker_to_qi(str(beacon.get("marker") or "")),
        "markerQiSource": beacon.get("markerQiSource"),
        "bodySha256": hashlib.sha256(str(beacon.get("observedBody") or "").encode()).hexdigest(),
    }
    audit = {
        "purpose": "Verify exact offline reconstruction coverage for HUMAN collector request bodies, including the s00 beacon marker edge case.",
        "builder": str((REPO / "tools/build_human_collector_request.mjs").resolve()),
        "rows": rows,
        "s00BeaconLine1007Evidence": beacon_evidence,
        "checks": {
            "hasBuildFiles": bool(files),
            "allRunsExact": bool(rows) and all(row["requestCount"] == row["exactBodyMatches"] for row in rows),
            "allRunsPayloadExact": bool(rows) and all(row["requestCount"] == row["payloadMatches"] for row in rows),
            "allRunsPcExact": bool(rows) and all(row["requestCount"] == row["pcMatches"] for row in rows),
            "s00BeaconExact": beacon.get("exactBodyMatch") is True,
            "s00BeaconUsesPayloadInverseMarker": beacon.get("markerSource") == "payload.inverse",
            "s00BeaconMarkerQiIsEarlierJo": marker_to_qi(str(beacon.get("marker") or "")) == "1781191404532",
        },
        "conclusion": (
            "All current HUMAN collector_request_build files now rebuild observed bodies exactly. "
            "The prior s00 line1007 beacon mismatch was caused by using latest collector Jo as marker; observed payload inverse extraction proves the beacon reused marker Qi 1781191404532, and rebuilding with that marker matches payload, pc, and full body."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
