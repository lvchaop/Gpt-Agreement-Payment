#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"

DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781234385000_1781234385.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_8fb43188-660d-11f1-95a4-62666cc2b93d_1781234407.json"
ACTIVITY_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_8fb43188-660d-11f1-95a4-62666cc2b93d_1781234407_seq5_full_activity_diff.json"
FIELD_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_8fb43188-660d-11f1-95a4-62666cc2b93d_1781234407_seq5_full_field_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def step_summary(direct: dict[str, Any], name: str) -> dict[str, Any]:
    return (((direct.get("steps") or {}).get(name) or {}).get("summary") or {})


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    activity = read_json(ACTIVITY_DIFF)
    field = read_json(FIELD_DIFF)
    pre_stk = step_summary(direct, "preStkNs")
    cap_get = step_summary(direct, "preCaptchaGet")
    cap_head = step_summary(direct, "preCaptchaHead")
    result = {
        "purpose": "Test a combined direct lineage with stk/ns plus captcha.js GET and HEAD before exact-whole-activities seq5/seq6.",
        "evidenceFiles": {
            "directAttempt": str(DIRECT.resolve()),
            "combo": str(COMBO.resolve()),
            "activityDiff": str(ACTIVITY_DIFF.resolve()),
            "fieldDiff": str(FIELD_DIFF.resolve()),
        },
        "control": {
            "directChecks": direct.get("checks"),
            "preStkNs": pre_stk,
            "preCaptchaGet": cap_get,
            "preCaptchaHead": cap_head,
            "comboChecks": combo.get("checks"),
            "activityChecks": activity.get("checks"),
            "fieldChecks": field.get("checks"),
            "fieldDiffCountVsS00Success": field.get("diffCountVsS00Success"),
        },
        "checks": {
            "preStkNsOk": (pre_stk.get("checks") or {}).get("httpStatusOk") is True,
            "preCaptchaGetOk": (cap_get.get("checks") or {}).get("httpStatusOkOrCacheable") is True,
            "preCaptchaHeadOk": (cap_head.get("checks") or {}).get("httpStatusOkOrCacheable") is True,
            "seq5Seq6BothDelivered": (combo.get("checks") or {}).get("seq5Http200") is True and (combo.get("checks") or {}).get("seq6Http200") is True,
            "seq5WholeActivitiesEqualS00Success": (activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "seq5FieldDiffZero": field.get("diffCountVsS00Success") == 0,
            "stillRejected": (combo.get("checks") or {}).get("anySuccessHandler") is False and (combo.get("checks") or {}).get("seq5HasOIIoIooo") is True,
        },
        "conclusion": (
            "A combined direct lineage replayed stk/ns, captcha.js GET, and captcha.js HEAD with the fresh uuid/vid, all returning OK/cacheable status. "
            "It then delivered seq5+seq6, with seq5 decoded activities and fields exactly equal to s00 success, but collector still returned oIIoIooo|-1. "
            "Therefore captcha.js GET/HEAD placement plus stk/ns is not sufficient. Remaining unreplayed classes are broader iframe/main asset lineage and sendBeacon/internal post-success dispatch, or non-request server-side/browser state not represented by these simple network hits."
        ),
    }
    json_path = OUT_DIR / "captcha_asset_combo_control_audit.json"
    md_path = OUT_DIR / "captcha_asset_combo_control_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# captcha asset combo control audit",
            "",
            f"- direct checks: `{direct.get('checks')}`",
            f"- combo checks: `{combo.get('checks')}`",
            f"- field diff count: `{field.get('diffCountVsS00Success')}`",
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
