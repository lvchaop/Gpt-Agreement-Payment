#!/usr/bin/env python3
from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/forced_overlap_payload_pc_split_control_audit.json"

ATTEMPT = PROTO / "first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781282000000_1781280296.json"
BOUNDARY = PROTO / "goal_audit/forced_overlap_exact_payload_pc_boundary_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit forced-overlap exact payload+pc / fresh outer split control.")
    parser.add_argument("--attempt", type=Path, default=ATTEMPT)
    parser.add_argument("--boundary", type=Path, default=BOUNDARY)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    attempt_path = args.attempt if args.attempt.is_absolute() else REPO / args.attempt
    boundary_path = args.boundary if args.boundary.is_absolute() else REPO / args.boundary
    out_path = args.out if args.out.is_absolute() else REPO / args.out
    attempt = read_json(attempt_path)
    boundary = read_json(boundary_path)
    final_combo = ((attempt.get("steps") or {}).get("finalSeq5Seq6Combo") or {}).get("summary") or {}
    combo_path = final_combo.get("json")
    combo = read_json(Path(combo_path)) if combo_path else {}
    seq5 = ((combo.get("results") or {}).get("seq5") or {})
    seq5_material = seq5.get("material") or {}
    seq5_response = seq5.get("response") or {}
    audit = {
        "purpose": "Under forced-overlap lineage, test exact s00 seq5 payload+pc with fresh outer session params.",
        "inputs": {
            "attempt": str(attempt_path),
            "boundary": str(boundary_path),
            "combo": combo_path,
        },
        "attemptChecks": attempt.get("checks"),
        "finalComboChecks": final_combo.get("checks"),
        "seq5Response": {
            "status": seq5_response.get("status"),
            "bodyText": seq5_response.get("bodyText"),
            "handlers": (seq5.get("decoded") or {}).get("handlers"),
            "parts": (seq5.get("decoded") or {}).get("parts"),
        },
        "seq5Material": {
            "checks": seq5_material.get("checks"),
            "meta": {
                key: (seq5_material.get("meta") or {}).get(key)
                for key in [
                    "payloadSource",
                    "pcSource",
                    "bodySource",
                    "payloadEqualsTemplate",
                    "pcEqualsTemplate",
                    "bodyEqualsTemplate",
                    "payloadUuidSource",
                    "pcUuidSource",
                    "markerSource",
                    "formOuterSource",
                    "actualPayloadSha256",
                    "templatePayloadSha256",
                    "pc",
                    "templatePc",
                    "computedPc",
                ]
            },
        },
        "boundaryChecks": boundary.get("checks"),
        "boundarySeq5": {
            "formDiffKeys": ((boundary.get("seq5") or {}).get("formDiffKeys")),
            "payloadEqual": ((boundary.get("seq5") or {}).get("payloadEqual")),
            "pcEqual": ((boundary.get("seq5") or {}).get("pcEqual")),
            "bodyEqual": ((boundary.get("seq5") or {}).get("bodyEqual")),
        },
        "checks": {
            "freshWebshareSession": str(attempt.get("session") or "").startswith("ibtvqcnm-JP-"),
            "forcedFirstFailureResponseOrder": (attempt.get("checks") or {}).get("overlapSeq3ResponseFirst") is True,
            "seq4AfterOverlapPow": (attempt.get("checks") or {}).get("seq4AfterOverlap200Pow") is True,
            "seq5PayloadAndPcExactS00": ((seq5_material.get("checks") or {}).get("payloadEqualsTemplate") is True)
            and ((seq5_material.get("checks") or {}).get("pcEqualsTemplate") is True)
            and ((seq5_material.get("checks") or {}).get("bodyEqualsTemplate") is False),
            "seq5FreshOuter": ((seq5_material.get("checks") or {}).get("formOuterSource") == "fresh"),
            "seq5ReturnedDoEmpty": seq5_response.get("bodyText") == "{\"do\":[]}\n",
            "seq5NoOIIoIooo": (final_combo.get("checks") or {}).get("seq5HasOIIoIooo") is False,
        },
        "conclusion": (
            "With forced first-failure response order and fresh outer session params, exact s00 seq5 payload+pc returns {do:[]} rather than oIIoIooo. "
            "This reproduces the payload/session binding behavior under the stronger forced-overlap lineage: stale exact payload+pc is not accepted with fresh session state."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out_path), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
