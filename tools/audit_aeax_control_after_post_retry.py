#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
S00_WASM_VERIFY = PROTO / "wasm/compute_wasm_nq_once_s00_line903_with_ng_verify.json"
OFFLINE_NG_ATTEMPT = PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202104.json"
TEMPLATE_AEAX_ATTEMPT = PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202273.json"
TEMPLATE_FIELD_DIFF = PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202273_full_field_diff.json"
TEMPLATE_ACTIVITY_DIFF = PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202273_full_activity_diff.json"
OUT = PROTO / "goal_audit/aeax_control_after_post_retry_audit.json"
S00_ACCEPTED_AEAX = "20626d6b0c88d972b04471354bb781cd1e4fe061ab15d7de8e38eccf424690a2b2baab430aa572ba48b5975148cf8edc777b171"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    s00_wasm = read_json(S00_WASM_VERIFY)
    offline_attempt = read_json(OFFLINE_NG_ATTEMPT)
    template_attempt = read_json(TEMPLATE_AEAX_ATTEMPT)
    field_diff = read_json(TEMPLATE_FIELD_DIFF)
    activity_diff = read_json(TEMPLATE_ACTIVITY_DIFF)
    s00_ng = (s00_wasm.get("output") or {}).get("ngValue")
    offline_meta = (offline_attempt.get("material") or {}).get("meta") or {}
    template_meta = (template_attempt.get("material") or {}).get("meta") or {}
    result = {
        "purpose": "Separate the unproved offline Ws.Ng/AEAx producer from post-retry fresh POW/TBR9 failures.",
        "inputs": {
            "s00WasmVerify": str(S00_WASM_VERIFY.resolve()),
            "offlineNgAttempt": str(OFFLINE_NG_ATTEMPT.resolve()),
            "templateAeaxAttempt": str(TEMPLATE_AEAX_ATTEMPT.resolve()),
            "templateFieldDiff": str(TEMPLATE_FIELD_DIFF.resolve()),
            "templateActivityDiff": str(TEMPLATE_ACTIVITY_DIFF.resolve()),
        },
        "s00NgEvidence": {
            "nqExpectMatches": (s00_wasm.get("checks") or {}).get("expectMatches"),
            "ngValue": s00_ng,
            "acceptedAeax": S00_ACCEPTED_AEAX,
            "ngEqualsAcceptedAeax": s00_ng == S00_ACCEPTED_AEAX,
        },
        "attempts": {
            "offlineNg": {
                "status": (offline_attempt.get("response") or {}).get("status"),
                "hasSuccessHandler": (offline_attempt.get("decoded") or {}).get("hasSuccessHandler"),
                "newPxTail": offline_meta.get("newPxTail"),
                "checks": (offline_attempt.get("material") or {}).get("checks"),
            },
            "templateAeax": {
                "status": (template_attempt.get("response") or {}).get("status"),
                "hasSuccessHandler": (template_attempt.get("decoded") or {}).get("hasSuccessHandler"),
                "newPxTail": template_meta.get("newPxTail"),
                "checks": (template_attempt.get("material") or {}).get("checks"),
                "fieldDiff": {
                    "diffCountVsS00Success": field_diff.get("diffCountVsS00Success"),
                    "diffsByClass": field_diff.get("diffsByClass"),
                    "checks": field_diff.get("checks"),
                },
                "activityDiff": {
                    "checks": activity_diff.get("checks"),
                    "nonPx561DiffSummary": activity_diff.get("nonPx561DiffSummary"),
                },
            },
        },
        "checks": {
            "offlineNqProvedButNgNotAeax": (s00_wasm.get("checks") or {}).get("expectMatches") is True and s00_ng != S00_ACCEPTED_AEAX,
            "offlineNgAttemptRejected": (offline_attempt.get("decoded") or {}).get("hasSuccessHandler") is False,
            "templateAeaxAttemptRejected": (template_attempt.get("decoded") or {}).get("hasSuccessHandler") is False,
            "templateAeaxHoldsAcceptedAeax": (template_meta.get("newPxTail") or {}).get("AEAxBkUsPjQ=") == S00_ACCEPTED_AEAX,
            "templateAeaxStillUsesFreshOskTbr9": all((template_attempt.get("material") or {}).get("checks", {}).get(k) is True for k in ["hasFreshOsk", "hasFreshTbr9"]),
        },
        "conclusion": (
            "Offline Ws.NQ is validated by s00 expect matching, but offline Ws.Ng does not reproduce the accepted s00 AEAx value. "
            "The post-retry template-AEAx control still fails while holding accepted AEAx and using fresh OSk/TBR9. "
            "Therefore the fresh failure is not explained solely by the unproved offline Ng value, but offline Ng remains unproved as an accepted AEAx producer."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
