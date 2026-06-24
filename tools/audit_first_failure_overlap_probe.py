#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/first_failure_overlap_probe_audit.json"
PROBE = PROTO / "first_failure_overlap_probe/first_failure_overlap_probe_5e23a4a0-666c-11f1-8626-62666cc2b93d_1781278922.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def result_row(probe: dict[str, Any], name: str) -> dict[str, Any]:
    row = ((probe.get("results") or {}).get(name) or {})
    decoded = row.get("decoded") or {}
    response = row.get("response") or {}
    return {
        "startedAt": row.get("startedAt"),
        "endedAt": row.get("endedAt"),
        "status": response.get("status"),
        "transport": response.get("transport"),
        "handlers": decoded.get("handlers"),
        "successParts": [part for part in decoded.get("parts") or [] if str(part).startswith("oIIoIooo|")],
        "hasPowResult": decoded.get("hasPowResult"),
    }


def main() -> int:
    probe = read_json(PROBE)
    seq2 = result_row(probe, "seq2")
    seq3 = result_row(probe, "seq3")
    timing = probe.get("timing") or {}
    audit = {
        "purpose": "Test the previously uncovered first-failure overlap: s00 sends seq2 PX561 and seq3 non-PX requests before receiving either response.",
        "probe": str(PROBE),
        "inputs": {
            "freshBundle": probe.get("freshBundle"),
            "powJson": probe.get("powJson"),
            "nqJson": probe.get("nqJson"),
            "ngNqJson": probe.get("ngNqJson"),
            "gapSeconds": probe.get("gapSeconds"),
            "h2BodyOrder": probe.get("h2BodyOrder", "normal"),
        },
        "timing": timing,
        "checks": probe.get("checks"),
        "seq2": seq2,
        "seq3": seq3,
        "s00Reference": {
            "seq2RequestLine": 574,
            "seq3RequestLine": 578,
            "seq3ResponseLine": 579,
            "seq2RejectedDecodeLine": 592,
            "observedRequestGapSecondsApprox": 0.5344,
            "observedResponseOrder": "seq3-before-seq2-rejection",
        },
        "derivedChecks": {
            "h2SingleSessionStream1And3": (seq2.get("transport") or {}).get("alpn") == "h2"
            and (seq3.get("transport") or {}).get("alpn") == "h2"
            and (seq2.get("transport") or {}).get("streamId") == 1
            and (seq3.get("transport") or {}).get("streamId") == 3,
            "requestGapMatchesS00Approx": abs(float(timing.get("seq3StartMinusSeq2Start") or 0) - 0.5344) < 0.05,
            "probeDidNotMatchS00ResponseOrder": timing.get("firstResponse") == "seq2",
            "seq2RejectedAndSeq3Progressed": probe.get("checks", {}).get("seq2Rejected") is True
            and probe.get("checks", {}).get("finalStateHasPow") is True,
        },
        "conclusion": (
            "The normal-body first-failure overlap probe used one h2 session and matched the s00 request gap, and both requests returned HTTP 200. "
            "However, it did not match the s00 response order: seq2 rejection completed before seq3, while s00 has the seq3 response before the seq2 rejected decode. "
            "Therefore first-failure overlap remains an active timing variable; the next control should force seq3 body/response before seq2 body or response."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "derivedChecks": audit["derivedChecks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
