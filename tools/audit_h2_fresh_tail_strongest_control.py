#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/h2_fresh_tail_strongest_control_audit.json"

DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781238679000_1781238679.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_8eebe304-6617-11f1-8da5-62666cc2b93d_1781238757.json"
SEQ5_ACTIVITY = PROTO / "px561_compare/seq5_seq6_combo_probe_8eebe304-6617-11f1-8da5-62666cc2b93d_1781238757_seq5_full_activity_diff.json"
SEQ5_FIELD = PROTO / "px561_compare/seq5_seq6_combo_probe_8eebe304-6617-11f1-8da5-62666cc2b93d_1781238757_seq5_full_field_diff.json"
SEQ6_ACTIVITY = PROTO / "px561_compare/seq5_seq6_combo_probe_8eebe304-6617-11f1-8da5-62666cc2b93d_1781238757_seq6_full_activity_diff.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def result_row(combo: dict[str, Any], name: str) -> dict[str, Any]:
    row = ((combo.get("results") or {}).get(name) or {})
    decoded = row.get("decoded") or {}
    return {
        "startedAt": row.get("startedAt"),
        "endedAt": row.get("endedAt"),
        "status": (row.get("response") or {}).get("status"),
        "transport": (row.get("response") or {}).get("transport"),
        "handlers": decoded.get("handlers"),
        "hasSuccessHandler": decoded.get("hasSuccessHandler"),
        "successParts": [part for part in decoded.get("parts") or [] if str(part).startswith("oIIoIooo")],
        "materialMeta": (row.get("material") or {}).get("meta"),
    }


def main() -> int:
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    seq5_activity = read_json(SEQ5_ACTIVITY)
    seq5_field = read_json(SEQ5_FIELD)
    seq6_activity = read_json(SEQ6_ACTIVITY)
    seq5 = result_row(combo, "seq5")
    seq6 = result_row(combo, "seq6")
    steps = direct.get("steps") or {}
    delay = ((steps.get("delayAfterPreCaptchaHead") or {}).get("summary") or {})
    timing = {
        "seq6StartMinusSeq5Start": (seq6["startedAt"] or 0) - (seq5["startedAt"] or 0),
        "seq6EndMinusSeq5End": (seq6["endedAt"] or 0) - (seq5["endedAt"] or 0),
        "firstResponse": "seq6" if (seq6["endedAt"] or 0) < (seq5["endedAt"] or 0) else "seq5",
    }
    direct_checks = direct.get("checks") or {}
    meta = seq5.get("materialMeta") or {}
    audit = {
        "purpose": "Test the strongest fresh server-bound no-browser control: fresh POW OSk, offline Ws.Ng/Ws.NQ AEAx/TBR9, solved Bzt, first-failure history, full asset-lineage, HEAD delay, and h2 seq5/seq6.",
        "inputs": {
            "direct": str(DIRECT),
            "combo": str(COMBO),
            "seq5ActivityDiff": str(SEQ5_ACTIVITY),
            "seq5FieldDiff": str(SEQ5_FIELD),
            "seq6ActivityDiff": str(SEQ6_ACTIVITY),
        },
        "directChecks": direct_checks,
        "delayAfterPreCaptchaHead": delay,
        "comboChecks": combo.get("checks"),
        "timing": timing,
        "seq5": seq5,
        "seq6": seq6,
        "seq5Sources": {
            key: meta.get(key)
            for key in [
                "aeaxSource",
                "bztSource",
                "stackSource",
                "tailSource",
                "innerUuidSource",
                "nonPxActivitySource",
                "payloadUuidSource",
                "pcUuidSource",
                "markerSource",
                "formOuterSource",
                "payloadSource",
                "pcSource",
                "bodySource",
            ]
        },
        "activityEvidence": {
            "seq5ActivityChecks": seq5_activity.get("checks"),
            "seq5FieldChecks": seq5_field.get("checks"),
            "seq5FieldDiffCountVsS00Success": seq5_field.get("diffCountVsS00Success"),
            "seq5DiffsByClass": seq5_field.get("diffsByClass"),
            "seq6ActivityChecks": seq6_activity.get("checks"),
        },
        "checks": {
            "firstFailureHistoryIncludedAndStateUpdated": direct_checks.get("firstFailurePx561Rejected") is True
            and direct_checks.get("firstFailureStateUpdated") is True,
            "fullAssetLineageOk": all(
                direct_checks.get(k) is True
                for k in [
                    "preStkNs200",
                    "preCaptchaGetOk",
                    "preCaptchaHeadOk",
                    "preIframeGetOk",
                    "preMainGetOk",
                    "preMainHeadOk",
                ]
            ),
            "captchaHeadDelayApplied": abs(float(delay.get("seconds") or 0) - 52.8) < 0.5,
            "h2SingleSession": (seq5["transport"] or {}).get("alpn") == "h2"
            and (seq6["transport"] or {}).get("alpn") == "h2"
            and (seq5["transport"] or {}).get("streamId") == 1
            and (seq6["transport"] or {}).get("streamId") == 3,
            "seq6ResponseFirst": timing["firstResponse"] == "seq6",
            "usesFreshServerBoundTail": meta.get("aeaxSource") == "offline-ng"
            and meta.get("bztSource") == "solve"
            and meta.get("tailSource") == "fresh"
            and meta.get("stackSource") == "fresh"
            and meta.get("innerUuidSource") == "fresh"
            and meta.get("nonPxActivitySource") == "fresh",
            "seq6WholeActivityEqualS00Line925": (seq6_activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "h2BodyOrderSeq6BodyFirst": ((combo.get("inputs") or {}).get("h2BodyOrder")) == "seq6-body-first",
            "stillRejected": (combo.get("checks") or {}).get("anySuccessHandler") is False
            and seq5["successParts"] == ["oIIoIooo|-1"],
        },
        "conclusion": (
            "The fresh server-bound variant used fresh POW OSk, offline Ws.Ng/Ws.NQ AEAx/TBR9, solved Bzt, fresh session fields, first-failure history, full asset-lineage, observed HEAD delay, and h2 seq5/seq6 delivery. "
            "Collector still returned oIIoIooo|-1. This is stronger for pure-protocol construction than static template-tail equality, but it also shows that fresh POW/WASM tail correctness plus the currently known lineage is not sufficient for accepted HUMAN."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
