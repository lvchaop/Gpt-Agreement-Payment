#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/seq6_response_first_control_audit.json"
S00_WINDOW = PROTO / "goal_audit/s00_line933_state_window_audit.json"
DIRECT = PROTO / "direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781236297000_1781236297.json"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_03142dd2-6612-11f1-8c32-62666cc2b93d_1781236331.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def timing(combo: dict[str, Any]) -> dict[str, Any]:
    seq5 = ((combo.get("results") or {}).get("seq5") or {})
    seq6 = ((combo.get("results") or {}).get("seq6") or {})
    return {
        "seq5StartedAt": seq5.get("startedAt"),
        "seq6StartedAt": seq6.get("startedAt"),
        "seq5EndedAt": seq5.get("endedAt"),
        "seq6EndedAt": seq6.get("endedAt"),
        "seq6StartMinusSeq5Start": (seq6.get("startedAt") or 0) - (seq5.get("startedAt") or 0),
        "seq6EndMinusSeq5End": (seq6.get("endedAt") or 0) - (seq5.get("endedAt") or 0),
        "firstResponse": "seq6" if (seq6.get("endedAt") or 0) < (seq5.get("endedAt") or 0) else "seq5",
    }


def s00_timing(window: dict[str, Any]) -> dict[str, Any]:
    runtime = ((window.get("s00Window") or {}).get("runtime") or [])
    by_line = {row.get("line"): row for row in runtime}
    return {
        "seq5RequestLine": 933,
        "seq6RequestLine": 937,
        "seq6ResponseLine": 938,
        "seq5ResponseLine": 961,
        "seq6StartMinusSeq5Start": (by_line.get(937, {}).get("t") or 0) - (by_line.get(933, {}).get("t") or 0),
        "seq6ResponseMinusSeq5Response": (by_line.get(938, {}).get("t") or 0) - (by_line.get(961, {}).get("t") or 0),
        "firstResponse": "seq6" if (by_line.get(938, {}).get("t") or 0) < (by_line.get(961, {}).get("t") or 0) else "seq5",
    }


def main() -> int:
    s00 = read_json(S00_WINDOW)
    direct = read_json(DIRECT)
    combo = read_json(COMBO)
    combo_timing = timing(combo)
    seq5 = ((combo.get("results") or {}).get("seq5") or {})
    seq6 = ((combo.get("results") or {}).get("seq6") or {})
    audit = {
        "purpose": "Test whether reproducing the s00 response ordering (seq6 response before seq5 response) is sufficient for HUMAN success.",
        "inputs": {
            "s00Window": str(S00_WINDOW),
            "directAttempt": str(DIRECT),
            "combo": str(COMBO),
        },
        "s00": s00_timing(s00),
        "control": {
            "session": direct.get("session"),
            "directChecks": direct.get("checks"),
            "comboChecks": combo.get("checks"),
            "timing": combo_timing,
            "seq5": {
                "status": ((seq5.get("response") or {}).get("status")),
                "handlers": ((seq5.get("decoded") or {}).get("handlers")),
                "parts": ((seq5.get("decoded") or {}).get("parts")),
                "hasSuccessHandler": ((seq5.get("decoded") or {}).get("hasSuccessHandler")),
            },
            "seq6": {
                "status": ((seq6.get("response") or {}).get("status")),
                "handlers": ((seq6.get("decoded") or {}).get("handlers")),
                "hasSuccessHandler": ((seq6.get("decoded") or {}).get("hasSuccessHandler")),
            },
        },
        "checks": {
            "s00Seq6ResponseFirst": s00_timing(s00)["firstResponse"] == "seq6",
            "controlSeq6ResponseFirst": combo_timing["firstResponse"] == "seq6",
            "controlSeq5Seq6BothDelivered": ((combo.get("checks") or {}).get("seq5Http200") is True and (combo.get("checks") or {}).get("seq6Http200") is True),
            "controlAssetLineageOk": all((direct.get("checks") or {}).get(key) is True for key in [
                "bootstrap200",
                "preStkNs200",
                "preCaptchaGetOk",
                "preCaptchaHeadOk",
                "preIframeGetOk",
                "preMainGetOk",
                "preMainHeadOk",
                "second200",
                "sequence200",
                "bundle200Pow",
                "progression200Pow",
            ]),
            "controlStillRejected": ((combo.get("checks") or {}).get("anySuccessHandler") is False and (combo.get("checks") or {}).get("seq5HasOIIoIooo") is True),
        },
        "conclusion": "A new direct Webshare session reproduced s00's response ordering with seq6 completing before seq5, while full asset-lineage preloads and seq5/seq6 delivery succeeded. The seq5 response still contained oIIoIooo|-1, so response ordering alone is not sufficient.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
