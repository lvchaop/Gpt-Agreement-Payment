#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/h2_seq6_response_before_seq5_body_control_audit.json"

DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781242000000_1781240960.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_de659678-661c-11f1-9d2e-62666cc2b93d_1781241031.json"


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
        "hasSuccessHandler": decoded.get("hasSuccessHandler"),
        "successParts": [part for part in decoded.get("parts") or [] if str(part).startswith("oIIoIooo")],
        "decodedTail": str(decoded.get("decoded") or "")[-120:],
        "materialMeta": (row.get("material") or {}).get("meta"),
    }


def main() -> int:
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    seq5 = result_row(combo, "seq5")
    seq6 = result_row(combo, "seq6")
    delay = (((direct.get("steps") or {}).get("delayAfterPreCaptchaHead") or {}).get("summary") or {})
    timing = {
        "seq6StartMinusSeq5Start": (seq6["startedAt"] or 0) - (seq5["startedAt"] or 0),
        "seq6EndMinusSeq5End": (seq6["endedAt"] or 0) - (seq5["endedAt"] or 0),
        "seq6EndedBeforeSeq5": (seq6["endedAt"] or 0) < (seq5["endedAt"] or 0),
    }
    direct_checks = direct.get("checks") or {}
    inputs = combo.get("inputs") or {}
    audit = {
        "purpose": (
            "Control the still-uncovered timing edge after s00 line938: send seq5 headers on h2 stream 1, send seq6 on stream 3, "
            "wait until seq6 response is fully received, then send seq5 body."
        ),
        "inputs": {
            "direct": str(DIRECT),
            "combo": str(COMBO),
        },
        "directChecks": direct_checks,
        "comboInputs": inputs,
        "comboChecks": combo.get("checks"),
        "delayAfterPreCaptchaHead": delay,
        "timing": timing,
        "seq5": seq5,
        "seq6": seq6,
        "checks": {
            "freshWebshareSession": direct.get("session") == "ibtvqcnm-JP-1781242000000",
            "firstFailureHistoryIncludedAndStateUpdated": direct_checks.get("firstFailurePx561Rejected") is True
            and direct_checks.get("firstFailureStateUpdated") is True,
            "captchaHeadDelayApplied": direct_checks.get("preCaptchaHeadOk") is True
            and abs(float(delay.get("seconds") or 0) - 52.8) < 0.5,
            "h2SingleSessionStream1And3": (seq5["transport"] or {}).get("alpn") == "h2"
            and (seq6["transport"] or {}).get("alpn") == "h2"
            and (seq5["transport"] or {}).get("streamId") == 1
            and (seq6["transport"] or {}).get("streamId") == 3,
            "h2BodyOrderSeq6ResponseBeforeSeq5Body": inputs.get("h2BodyOrder") == "seq6-response-before-seq5-body",
            "seq6ResponseEndedBeforeSeq5": timing["seq6EndedBeforeSeq5"] is True,
            "seq5Seq6Http200": seq5["status"] == 200 and seq6["status"] == 200,
            "seq5StillRejected": seq5["successParts"] == ["oIIoIooo|-1"]
            and (combo.get("checks") or {}).get("anySuccessHandler") is False,
            "seq6HasCookieTokenHandlers": all(h in (seq6.get("handlers") or []) for h in ["IoooII", "oIIoIIoo"]),
        },
        "conclusion": (
            "Even when the no-browser client receives the full seq6 cookie/token response before sending seq5 body, using one h2 TLS session "
            "with stream 1/3, first-failure state, captcha HEAD delay, fresh stack, fresh server-bound tail material, and fresh Webshare session, "
            "seq5 still returns oIIoIooo|-1. Therefore the missing condition is not merely response-before-response order nor the ability to observe "
            "seq6 _px3/_pxde before seq5 completes; it remains outside the current two-request decoded body/timing model."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
