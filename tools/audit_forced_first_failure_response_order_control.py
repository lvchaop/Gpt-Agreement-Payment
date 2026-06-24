#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/forced_first_failure_response_order_control_audit.json"

ATTEMPT = PROTO / "first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781280000000_1781279346.json"
OVERLAP = PROTO / "first_failure_overlap_probe/first_failure_overlap_probe_3e4d7f2a-6676-11f1-8398-62666cc2b93d_1781279360.json"
SEQ4 = PROTO / "fresh_bundle_progression_probe/fresh_bundle_progression_probe_3e4d7f2a-6676-11f1-8398-62666cc2b93d_1781279414.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_3e4d7f2a-6676-11f1-8398-62666cc2b93d_1781279482.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def result_row(combo: dict[str, Any], name: str) -> dict[str, Any]:
    row = ((combo.get("results") or {}).get(name) or {})
    decoded = row.get("decoded") or {}
    response = row.get("response") or {}
    return {
        "startedAt": row.get("startedAt"),
        "endedAt": row.get("endedAt"),
        "status": response.get("status"),
        "transport": response.get("transport"),
        "handlers": decoded.get("handlers"),
        "successParts": [part for part in decoded.get("parts") or [] if str(part).startswith("oIIoIooo|")],
    }


def main() -> int:
    attempt = read_json(ATTEMPT)
    overlap = read_json(OVERLAP)
    seq4 = read_json(SEQ4)
    combo = read_json(COMBO)
    seq4_statuses = [((step.get("response") or {}).get("status")) for step in seq4.get("steps") or []]
    seq4_has_pow = [((step.get("decoded") or {}).get("hasPowResult")) for step in seq4.get("steps") or []]
    seq5 = result_row(combo, "seq5")
    seq6 = result_row(combo, "seq6")
    combo_timing = {
        "seq6StartMinusSeq5Start": (seq6["startedAt"] or 0) - (seq5["startedAt"] or 0),
        "seq6EndMinusSeq5End": (seq6["endedAt"] or 0) - (seq5["endedAt"] or 0),
        "seq6EndedBeforeSeq5": (seq6["endedAt"] or 0) < (seq5["endedAt"] or 0),
    }
    audit = {
        "purpose": "Test whether reproducing s00 first-failure response order before final seq5/seq6 closes the pure-protocol acceptance gap.",
        "inputs": {
            "attempt": str(ATTEMPT),
            "overlap": str(OVERLAP),
            "seq4": str(SEQ4),
            "combo": str(COMBO),
        },
        "attemptChecks": attempt.get("checks"),
        "overlap": {
            "h2BodyOrder": overlap.get("h2BodyOrder"),
            "timing": overlap.get("timing"),
            "checks": overlap.get("checks"),
        },
        "seq4": {
            "statuses": seq4_statuses,
            "handlers": [((step.get("decoded") or {}).get("handlers")) for step in seq4.get("steps") or []],
            "hasPow": seq4_has_pow,
            "finalState": {k: (seq4.get("finalState") or {}).get(k) for k in ["uuid", "jo", "ci", "cs", "powChallenge"]},
        },
        "combo": {
            "inputs": combo.get("inputs"),
            "checks": combo.get("checks"),
            "timing": combo_timing,
            "seq5": seq5,
            "seq6": seq6,
        },
        "checks": {
            "freshWebshareSession": attempt.get("session") == "ibtvqcnm-JP-1781280000000",
            "bootstrapThroughBundlePowOk": all(
                (attempt.get("checks") or {}).get(k) is True
                for k in ["bootstrap200", "second200", "sequence200", "bundle200Pow"]
            ),
            "forcedFirstFailureMatchesS00ResponseOrder": (overlap.get("checks") or {}).get("seq3ResponseFirst") is True
            and (overlap.get("checks") or {}).get("seq2Rejected") is True
            and (overlap.get("timing") or {}).get("firstResponse") == "seq3",
            "seq4AfterForcedOverlapReturnedPow": seq4_statuses == [200] and seq4_has_pow == [True],
            "finalH2Seq6BeforeSeq5Body": ((combo.get("inputs") or {}).get("h2BodyOrder")) == "seq6-response-before-seq5-body"
            and combo_timing["seq6EndedBeforeSeq5"] is True,
            "finalSeq5StillRejected": seq5["successParts"] == ["oIIoIooo|-1"]
            and (combo.get("checks") or {}).get("anySuccessHandler") is False,
        },
        "conclusion": (
            "A fresh Webshare control reproduced the s00 first-failure response order by forcing seq3 response before seq2 rejection, then advanced seq4 to a new POW and sent final seq5/seq6 with seq6 completed before seq5 body. "
            "The final seq5 still returned oIIoIooo|-1. Therefore first-failure response ordering is not sufficient to close the current pure-protocol success gap."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
