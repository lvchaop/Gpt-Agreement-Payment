#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/h2_dual_activity_equal_control_audit.json"
DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781237267000_1781237267.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_453388c8-6614-11f1-a43c-62666cc2b93d_1781237289.json"
SEQ5_ACTIVITY = PROTO / "px561_compare/seq5_seq6_combo_probe_453388c8-6614-11f1-a43c-62666cc2b93d_1781237289_seq5_full_activity_diff.json"
SEQ5_FIELD = PROTO / "px561_compare/seq5_seq6_combo_probe_453388c8-6614-11f1-a43c-62666cc2b93d_1781237289_seq5_full_field_diff.json"
SEQ6_ACTIVITY = PROTO / "px561_compare/seq5_seq6_combo_probe_453388c8-6614-11f1-a43c-62666cc2b93d_1781237289_seq6_full_activity_diff.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def result_row(combo: dict[str, Any], name: str) -> dict[str, Any]:
    row = ((combo.get("results") or {}).get(name) or {})
    return {
        "startedAt": row.get("startedAt"),
        "endedAt": row.get("endedAt"),
        "status": ((row.get("response") or {}).get("status")),
        "transport": ((row.get("response") or {}).get("transport")),
        "handlers": ((row.get("decoded") or {}).get("handlers")),
        "hasSuccessHandler": ((row.get("decoded") or {}).get("hasSuccessHandler")),
        "successParts": [
            part for part in ((row.get("decoded") or {}).get("parts") or [])
            if str(part).startswith("oIIoIooo")
        ],
        "materialMeta": ((row.get("material") or {}).get("meta")),
    }


def main() -> int:
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    seq5_activity = read_json(SEQ5_ACTIVITY)
    seq5_field = read_json(SEQ5_FIELD)
    seq6_activity = read_json(SEQ6_ACTIVITY)
    seq5 = result_row(combo, "seq5")
    seq6 = result_row(combo, "seq6")
    timing = {
        "seq6StartMinusSeq5Start": (seq6["startedAt"] or 0) - (seq5["startedAt"] or 0),
        "seq6EndMinusSeq5End": (seq6["endedAt"] or 0) - (seq5["endedAt"] or 0),
        "firstResponse": "seq6" if (seq6["endedAt"] or 0) < (seq5["endedAt"] or 0) else "seq5",
    }
    audit = {
        "purpose": "Test the strongest no-browser h2 control so far: full asset-lineage preload, one Webshare session, one h2 TLS session, seq5 decoded activities equal s00 line922, and seq6 decoded activity equal s00 line925.",
        "inputs": {
            "direct": str(DIRECT),
            "combo": str(COMBO),
            "seq5ActivityDiff": str(SEQ5_ACTIVITY),
            "seq5FieldDiff": str(SEQ5_FIELD),
            "seq6ActivityDiff": str(SEQ6_ACTIVITY),
        },
        "directChecks": direct.get("checks"),
        "comboChecks": combo.get("checks"),
        "timing": timing,
        "seq5": seq5,
        "seq6": seq6,
        "activityEvidence": {
            "seq5ActivityChecks": seq5_activity.get("checks"),
            "seq5FieldChecks": seq5_field.get("checks"),
            "seq5FieldDiffCountVsS00Success": seq5_field.get("diffCountVsS00Success"),
            "seq6ActivityChecks": seq6_activity.get("checks"),
        },
        "checks": {
            "fullAssetLineageOk": all(
                direct.get("checks", {}).get(k) is True
                for k in [
                    "preStkNs200",
                    "preCaptchaGetOk",
                    "preCaptchaHeadOk",
                    "preIframeGetOk",
                    "preMainGetOk",
                    "preMainHeadOk",
                ]
            ),
            "h2SingleSession": (seq5["transport"] or {}).get("alpn") == "h2"
            and (seq6["transport"] or {}).get("alpn") == "h2"
            and (seq5["transport"] or {}).get("streamId") == 1
            and (seq6["transport"] or {}).get("streamId") == 3,
            "seq6ResponseFirst": timing["firstResponse"] == "seq6",
            "seq5WholeActivitiesEqualS00Line922": (seq5_activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "seq5Px561FieldDiffZeroVsS00Line922": seq5_field.get("diffCountVsS00Success") == 0,
            "seq6WholeActivityEqualS00Line925": (seq6_activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "stillRejected": (combo.get("checks") or {}).get("anySuccessHandler") is False
            and seq5["successParts"] == ["oIIoIooo|-1"],
        },
        "conclusion": "Even with full asset-lineage preloads, one direct Webshare session, one h2 TLS session, seq6 completing before seq5, seq5 decoded activities/PX561 fields equal to s00 accepted line922, and seq6 decoded activity equal to s00 line925, collector still returns oIIoIooo|-1. The remaining boundary is not seq5/seq6 decoded request content or h2 multiplex timing; it is server-side/session lineage or hidden material outside these decoded bodies.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
