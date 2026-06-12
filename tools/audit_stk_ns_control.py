#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"

DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781233946000_1781233946.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_89fc623e-660c-11f1-a9e0-62666cc2b93d_1781233965.json"
ACTIVITY_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_89fc623e-660c-11f1-a9e0-62666cc2b93d_1781233965_seq5_full_activity_diff.json"
FIELD_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_89fc623e-660c-11f1-a9e0-62666cc2b93d_1781233965_seq5_full_field_diff.json"
S00_RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = idx
                rows.append(row)
    return rows


def s00_stk_requests() -> list[dict[str, Any]]:
    out = []
    for row in read_jsonl(S00_RUNTIME):
        if row.get("_line", 999999) > 933:
            break
        if row.get("kind") == "request" and "stk.hsprotect.net/ns" in str(row.get("url")):
            out.append({
                "line": row.get("_line"),
                "method": row.get("method"),
                "url": row.get("url"),
                "t": row.get("t"),
                "headerOrder": list((row.get("headers") or {}).keys()),
            })
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    activity_diff = read_json(ACTIVITY_DIFF)
    field_diff = read_json(FIELD_DIFF)
    pre_stk = (((direct.get("steps") or {}).get("preStkNs") or {}).get("summary") or {})
    result = {
        "purpose": "Test whether replaying the observed stk.hsprotect.net/ns?c=<uuid> GET before bootstrap is sufficient for no-browser HUMAN success.",
        "evidenceFiles": {
            "directAttempt": str(DIRECT.resolve()),
            "combo": str(COMBO.resolve()),
            "activityDiff": str(ACTIVITY_DIFF.resolve()),
            "fieldDiff": str(FIELD_DIFF.resolve()),
            "s00Runtime": str(S00_RUNTIME.resolve()),
        },
        "s00": {
            "stkRequestsBeforeAcceptedLine933": s00_stk_requests(),
        },
        "control": {
            "directChecks": direct.get("checks"),
            "preStkSummary": pre_stk,
            "comboChecks": combo.get("checks"),
            "activityChecks": activity_diff.get("checks"),
            "fieldChecks": field_diff.get("checks"),
            "fieldDiffCountVsS00Success": field_diff.get("diffCountVsS00Success"),
        },
        "checks": {
            "s00HasStkNsBeforeAccepted": len(s00_stk_requests()) > 0,
            "preStkNsSentHttp200": pre_stk.get("status") == 200 and (pre_stk.get("checks") or {}).get("httpStatusOk") is True,
            "preStkUuidMatchesBootstrap": (
                (((direct.get("steps") or {}).get("bootstrap") or {}).get("summary") or {}).get("freshState") or {}
            ).get("uuid") in str(((pre_stk.get("json") and read_json(Path(pre_stk["json"])).get("request")) or {}).get("url")),
            "seq5Seq6BothDelivered": (combo.get("checks") or {}).get("seq5Http200") is True and (combo.get("checks") or {}).get("seq6Http200") is True,
            "seq5WholeActivitiesEqualS00Success": (activity_diff.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "seq5FieldDiffZero": field_diff.get("diffCountVsS00Success") == 0,
            "stillRejected": (combo.get("checks") or {}).get("anySuccessHandler") is False and (combo.get("checks") or {}).get("seq5HasOIIoIooo") is True,
        },
        "conclusion": (
            "s00 has stk.hsprotect.net/ns?c=<uuid> GET requests before the accepted line933. "
            "A direct no-browser control replayed the initial stk/ns GET with the same fresh uuid before bootstrap, received HTTP 200, then sent delivered seq5+seq6 with seq5 decoded activities and fields exactly equal to s00 success. "
            "Collector still returned oIIoIooo|-1. Therefore a single pre-bootstrap stk/ns replay is not sufficient; remaining evidence should focus on broader browser/server-side state lineage, not stk/ns alone."
        ),
    }
    json_path = OUT_DIR / "stk_ns_control_audit.json"
    md_path = OUT_DIR / "stk_ns_control_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# stk/ns control audit",
            "",
            f"- s00 stk/ns count before line933: `{len(result['s00']['stkRequestsBeforeAcceptedLine933'])}`",
            f"- preStk status: `{pre_stk.get('status')}`",
            f"- combo checks: `{combo.get('checks')}`",
            f"- field diff count: `{field_diff.get('diffCountVsS00Success')}`",
            "",
            "## Checks",
            *[f"- {k}: `{v}`" for k, v in result["checks"].items()],
            "",
            "## Conclusion",
            result["conclusion"],
            "",
        ]),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "md": str(md_path), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
