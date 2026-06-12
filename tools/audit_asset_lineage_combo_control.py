#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "goal_audit"

DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781234850000_1781234850.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_a505e6de-660e-11f1-95e3-62666cc2b93d_1781234877.json"
ACTIVITY_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_a505e6de-660e-11f1-95e3-62666cc2b93d_1781234877_seq5_full_activity_diff.json"
FIELD_DIFF = PROTO / "px561_compare/seq5_seq6_combo_probe_a505e6de-660e-11f1-95e3-62666cc2b93d_1781234877_seq5_full_field_diff.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def step_summary(direct: dict[str, Any], name: str) -> dict[str, Any]:
    return (((direct.get("steps") or {}).get(name) or {}).get("summary") or {})


def ok(summary: dict[str, Any], key: str = "httpStatusOkOrCacheable") -> bool:
    return (summary.get("checks") or {}).get(key) is True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    activity = read_json(ACTIVITY_DIFF)
    field = read_json(FIELD_DIFF)
    pre_stk = step_summary(direct, "preStkNs")
    cap_get = step_summary(direct, "preCaptchaGet")
    cap_head = step_summary(direct, "preCaptchaHead")
    iframe_get = step_summary(direct, "preIframeGet")
    main_get = step_summary(direct, "preMainGet")
    main_head = step_summary(direct, "preMainHead")
    result = {
        "purpose": "Test direct lineage with stk/ns, fresh-cookie iframe/main asset requests, fresh-cookie captcha GET, captcha/main HEAD, and exact-whole-activities seq5/seq6.",
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
            "preIframeGet": iframe_get,
            "preMainGet": main_get,
            "preMainHead": main_head,
            "comboChecks": combo.get("checks"),
            "activityChecks": activity.get("checks"),
            "fieldChecks": field.get("checks"),
            "fieldDiffCountVsS00Success": field.get("diffCountVsS00Success"),
        },
        "checks": {
            "preStkNsOk": (pre_stk.get("checks") or {}).get("httpStatusOk") is True,
            "preCaptchaGetOk": ok(cap_get),
            "preCaptchaGetFreshCookie": (cap_get.get("checks") or {}).get("requestCookieUsesFreshPx3") is True and (cap_get.get("checks") or {}).get("requestCookieUsesFreshPxvid") is True,
            "preCaptchaHeadOk": ok(cap_head),
            "preIframeGetOk": ok(iframe_get),
            "preIframeGetFreshCookieAndSid": (iframe_get.get("checks") or {}).get("requestCookieUsesFreshPx3") is True and (iframe_get.get("checks") or {}).get("requestCookieUsesFreshPxvid") is True and (iframe_get.get("checks") or {}).get("iframeUrlUsesFreshSid") is True,
            "preMainGetOk": ok(main_get),
            "preMainGetFreshCookie": (main_get.get("checks") or {}).get("requestCookieUsesFreshPx3") is True and (main_get.get("checks") or {}).get("requestCookieUsesFreshPxvid") is True,
            "preMainHeadOk": ok(main_head),
            "seq5Seq6BothDelivered": (combo.get("checks") or {}).get("seq5Http200") is True and (combo.get("checks") or {}).get("seq6Http200") is True,
            "seq5WholeActivitiesEqualS00Success": (activity.get("checks") or {}).get("wholeActivitiesEqual") is True,
            "seq5FieldDiffZero": field.get("diffCountVsS00Success") == 0,
            "stillRejected": (combo.get("checks") or {}).get("anySuccessHandler") is False and (combo.get("checks") or {}).get("seq5HasOIIoIooo") is True,
        },
        "conclusion": (
            "A fresh direct Webshare session replayed stk/ns, s00 line171 iframe GET with fresh sid and fresh _px cookies, "
            "s00 line185 main.min.js GET with fresh _px cookies, s00 line265 main HEAD, captcha.js GET with fresh _px cookies, and captcha.js HEAD. "
            "All network probes returned OK/cacheable status. The subsequent seq5+seq6 pair was delivered, and seq5 decoded whole activities plus field set were equal to s00 success, "
            "but collector still returned oIIoIooo|-1. Therefore iframe/main/captcha simple asset-load lineage, including the observed fresh-cookie GET cases, is not sufficient."
        ),
    }
    json_path = OUT_DIR / "asset_lineage_combo_control_audit.json"
    md_path = OUT_DIR / "asset_lineage_combo_control_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(
        "\n".join([
            "# asset lineage combo control audit",
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
