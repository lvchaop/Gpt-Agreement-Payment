#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/forced_overlap_template_final_control_audit.json"

ATTEMPT = PROTO / "first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781281000000_1781279930.json"
BOUNDARY = PROTO / "goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    attempt = read_json(ATTEMPT)
    boundary = read_json(BOUNDARY)
    final_combo = ((attempt.get("steps") or {}).get("finalSeq5Seq6Combo") or {}).get("summary") or {}
    overlap = attempt.get("overlap") or ((attempt.get("steps") or {}).get("firstFailureOverlap") or {}).get("summary") or {}
    audit = {
        "purpose": "Combine forced s00 first-failure response order with final seq5/seq6 decoded-activity equality against s00.",
        "inputs": {
            "attempt": str(ATTEMPT),
            "boundary": str(BOUNDARY),
            "finalCombo": final_combo.get("json"),
            "overlap": overlap.get("json"),
        },
        "attemptChecks": attempt.get("checks"),
        "overlap": {
            "checks": overlap.get("checks"),
            "timing": overlap.get("timing"),
        },
        "finalCombo": {
            "checks": final_combo.get("checks"),
            "handlers": final_combo.get("handlers"),
        },
        "boundaryChecks": boundary.get("checks"),
        "boundarySeq5": {
            "formDiffKeys": ((boundary.get("seq5") or {}).get("formDiffKeys")),
            "activityCompare": ((boundary.get("seq5") or {}).get("activityCompare")),
        },
        "boundarySeq6": {
            "formDiffKeys": ((boundary.get("seq6") or {}).get("formDiffKeys")),
            "activityCompare": ((boundary.get("seq6") or {}).get("activityCompare")),
        },
        "checks": {
            "freshWebshareSession": attempt.get("session") == "ibtvqcnm-JP-1781281000000",
            "forcedFirstFailureResponseOrder": (attempt.get("checks") or {}).get("overlapSeq3ResponseFirst") is True
            and (attempt.get("checks") or {}).get("overlapSeq2Rejected") is True,
            "seq4AfterOverlapPow": (attempt.get("checks") or {}).get("seq4AfterOverlap200Pow") is True,
            "finalSeq5Seq6Http200": (final_combo.get("checks") or {}).get("seq5Http200") is True
            and (final_combo.get("checks") or {}).get("seq6Http200") is True,
            "finalDecodedActivitiesEqualS00": (boundary.get("checks") or {}).get("seq5DecodedNotEqualS00") is False
            and (boundary.get("checks") or {}).get("seq6DecodedNotEqualS00") is False,
            "finalStillRejected": (final_combo.get("checks") or {}).get("anySuccessHandler") is False
            and "oIIoIooo" in ((final_combo.get("handlers") or {}).get("seq5") or []),
            "encodedPayloadPcOuterStillDiffer": (boundary.get("checks") or {}).get("seq5EncodedPayloadDiffers") is True
            and (boundary.get("checks") or {}).get("seq6EncodedPayloadDiffers") is True,
        },
        "conclusion": (
            "A fresh Webshare control combined forced s00 first-failure response ordering with final seq5/seq6 decoded activities equal to s00. "
            "The collector still returned oIIoIooo|-1. This rules out first-failure response ordering plus decoded final activity equality as sufficient; "
            "the remaining boundary is encoded payload/pc with coherent fresh session/server state, or server-side state not represented in decoded activities."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
