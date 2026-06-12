#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/h2_multiplex_control_audit.json"
S00_WINDOW = PROTO / "goal_audit/s00_line933_state_window_audit.json"
S00_RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_c8768480-6612-11f1-b7a9-62666cc2b93d_1781236716.json"
SEQ5_EXTRACTED = PROTO / "seq5_seq6_combo_probe/extracted/seq5_seq6_combo_probe_c8768480-6612-11f1-b7a9-62666cc2b93d_1781236716_seq5.json"
ACTIVITY_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_c8768480-6612-11f1-b7a9-62666cc2b93d_1781236716_seq5_full_activity_diff.json"
FIELD_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_c8768480-6612-11f1-b7a9-62666cc2b93d_1781236716_seq5_full_field_diff.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_runtime_lines(lines: set[int]) -> list[dict[str, Any]]:
    out = []
    with S00_RUNTIME.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line_no in lines:
                row = json.loads(line)
                row["_line"] = line_no
                out.append(row)
    return out


def row(combo: dict[str, Any], name: str) -> dict[str, Any]:
    r = ((combo.get("results") or {}).get(name) or {})
    return {
        "startedAt": r.get("startedAt"),
        "endedAt": r.get("endedAt"),
        "status": ((r.get("response") or {}).get("status")),
        "elapsedSeconds": ((r.get("response") or {}).get("elapsedSeconds")),
        "transport": ((r.get("response") or {}).get("transport")),
        "headers": ((r.get("response") or {}).get("headers")),
        "handlers": ((r.get("decoded") or {}).get("handlers")),
        "parts": ((r.get("decoded") or {}).get("parts")),
        "hasSuccessHandler": ((r.get("decoded") or {}).get("hasSuccessHandler")),
    }


def main() -> int:
    s00 = read_json(S00_WINDOW)
    s00_response_rows = read_runtime_lines({938, 961})
    combo = read_json(COMBO)
    activity_diff = read_json(ACTIVITY_DIFF)
    field_diff = read_json(FIELD_DIFF)
    seq5 = row(combo, "seq5")
    seq6 = row(combo, "seq6")
    timing = {
        "seq6StartMinusSeq5Start": (seq6["startedAt"] or 0) - (seq5["startedAt"] or 0),
        "seq6EndMinusSeq5End": (seq6["endedAt"] or 0) - (seq5["endedAt"] or 0),
        "firstResponse": "seq6" if (seq6["endedAt"] or 0) < (seq5["endedAt"] or 0) else "seq5",
    }
    audit = {
        "purpose": "Test whether browser-like HTTP/2 multiplexing over one TLS session is sufficient for HUMAN success.",
        "inputs": {
            "s00Window": str(S00_WINDOW),
            "combo": str(COMBO),
            "seq5Extracted": str(SEQ5_EXTRACTED),
            "activityDiff": str(ACTIVITY_DIFF),
            "fieldDiff": str(FIELD_DIFF),
        },
        "s00Evidence": {
            "responseHeaders": [
                {
                    "line": row.get("_line"),
                    "status": row.get("status"),
                    "url": row.get("url"),
                    "xFirefoxSpdy": ((row.get("headers") or {}).get("x-firefox-spdy")),
                    "headers": row.get("headers"),
                }
                for row in s00_response_rows
            ],
            "checks": s00.get("checks"),
        },
        "control": {
            "comboChecks": combo.get("checks"),
            "timing": timing,
            "seq5": seq5,
            "seq6": seq6,
            "activityChecks": activity_diff.get("checks"),
            "fieldChecks": field_diff.get("checks"),
            "fieldDiffCountVsS00Success": field_diff.get("diffCountVsS00Success"),
        },
        "checks": {
            "s00RuntimeShowsH2Header": all(((row.get("headers") or {}).get("x-firefox-spdy") == "h2") for row in s00_response_rows),
            "controlNegotiatedH2": seq5["transport"].get("alpn") == "h2" and seq6["transport"].get("alpn") == "h2",
            "controlSingleH2SessionStreams": seq5["transport"].get("streamId") == 1 and seq6["transport"].get("streamId") == 3,
            "controlSeq6ResponseFirst": timing["firstResponse"] == "seq6",
            "controlSeq5Seq6BothDelivered": (combo.get("checks") or {}).get("seq5Http200") is True and (combo.get("checks") or {}).get("seq6Http200") is True,
            "controlSeq5WholeActivitiesEqualS00Success": (activity_diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "controlSeq5Px561FieldsEqualS00Success": field_diff.get("diffCountVsS00Success") == 0,
            "controlStillRejected": (combo.get("checks") or {}).get("anySuccessHandler") is False and (combo.get("checks") or {}).get("seq5HasOIIoIooo") is True,
        },
        "conclusion": "The h2 control negotiated ALPN h2 and sent seq5/seq6 as streams 1/3 over one TLS session, with seq6 completing before seq5. Its seq5 decoded activities and PX561 fields equal the s00 accepted payload, but collector still returned oIIoIooo|-1 for seq5. HTTP/2 multiplexing, response order, and decoded payload equality are not sufficient.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
