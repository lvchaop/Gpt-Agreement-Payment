#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT = REPO / "output/protocol_reverse/goal_audit/latest_exact_payload_body_controls_audit.json"

EXACT_PAYLOAD_PC_DIRECT = REPO / "output/protocol_reverse/direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781235846000_1781235846.json"
EXACT_PAYLOAD_PC_COMBO = REPO / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_f62be69c-6610-11f1-9e77-62666cc2b93d_1781235871.json"
EXACT_BODY_DIRECT = REPO / "output/protocol_reverse/direct_webshare_attempt/direct_webshare_attempt_ibtvqcnm-JP-1781235884000_1781235884.json"
EXACT_BODY_COMBO = REPO / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_0d231a50-6611-11f1-80b6-62666cc2b93d_1781235909.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def combo_seq5(combo: dict[str, Any]) -> dict[str, Any]:
    return ((combo.get("results") or {}).get("seq5") or {})


def direct_asset_checks_ok(doc: dict[str, Any]) -> bool:
    checks = doc.get("checks") or {}
    keys = [
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
    ]
    return all(checks.get(key) is True for key in keys)


def summarize(direct_path: Path, combo_path: Path) -> dict[str, Any]:
    direct = read_json(direct_path)
    combo = read_json(combo_path)
    seq5 = combo_seq5(combo)
    material = seq5.get("material") or {}
    decoded = seq5.get("decoded") or {}
    checks = material.get("checks") or {}
    response = seq5.get("response") or {}
    return {
        "directJson": str(direct_path),
        "comboJson": str(combo_path),
        "session": direct.get("session"),
        "assetLineageChecksOk": direct_asset_checks_ok(direct),
        "comboChecks": combo.get("checks") or {},
        "materialChecks": {
            "payloadSource": checks.get("payloadSource"),
            "pcSource": checks.get("pcSource"),
            "bodySource": checks.get("bodySource"),
            "payloadEqualsTemplate": checks.get("payloadEqualsTemplate"),
            "pcEqualsTemplate": checks.get("pcEqualsTemplate"),
            "bodyEqualsTemplate": checks.get("bodyEqualsTemplate"),
            "hasFreshUuid": checks.get("hasFreshUuid"),
            "hasFreshP1": checks.get("hasFreshP1"),
            "hasFreshCi": checks.get("hasFreshCi"),
            "hasFreshCs": checks.get("hasFreshCs"),
        },
        "seq5": {
            "status": response.get("status"),
            "bodyText": response.get("bodyText"),
            "handlers": decoded.get("handlers"),
            "parts": decoded.get("parts"),
            "hasSuccessHandler": decoded.get("hasSuccessHandler"),
        },
    }


def main() -> int:
    exact_payload_pc = summarize(EXACT_PAYLOAD_PC_DIRECT, EXACT_PAYLOAD_PC_COMBO)
    exact_body = summarize(EXACT_BODY_DIRECT, EXACT_BODY_COMBO)
    audit = {
        "inputs": {
            "exactPayloadPcDirect": str(EXACT_PAYLOAD_PC_DIRECT),
            "exactPayloadPcCombo": str(EXACT_PAYLOAD_PC_COMBO),
            "exactBodyDirect": str(EXACT_BODY_DIRECT),
            "exactBodyCombo": str(EXACT_BODY_COMBO),
        },
        "exactPayloadPcFreshOuter": exact_payload_pc,
        "exactWholeBody": exact_body,
        "checks": {
            "exactPayloadPcAssetLineageOk": exact_payload_pc["assetLineageChecksOk"] is True,
            "exactPayloadPcSeq5Http200": exact_payload_pc["seq5"]["status"] == 200,
            "exactPayloadPcMaterialPayloadPcTemplate": (
                exact_payload_pc["materialChecks"]["payloadEqualsTemplate"] is True
                and exact_payload_pc["materialChecks"]["pcEqualsTemplate"] is True
                and exact_payload_pc["materialChecks"]["bodyEqualsTemplate"] is False
            ),
            "exactPayloadPcReturnedDoEmpty": exact_payload_pc["seq5"]["bodyText"] == "{\"do\":[]}\n",
            "exactPayloadPcNoSuccess": exact_payload_pc["seq5"]["hasSuccessHandler"] is not True,
            "exactBodyAssetLineageOk": exact_body["assetLineageChecksOk"] is True,
            "exactBodySeq5Http200": exact_body["seq5"]["status"] == 200,
            "exactBodyMaterialBodyTemplate": exact_body["materialChecks"]["bodyEqualsTemplate"] is True,
            "exactBodyRejectedMinusOne": "oIIoIooo|-1" in (exact_body["seq5"]["parts"] or []),
            "exactBodyNoSuccess": exact_body["seq5"]["hasSuccessHandler"] is not True,
        },
        "conclusion": "In fresh direct Webshare sessions with full asset-lineage preloads, exact s00 payload+pc with fresh outer returns {do:[]} and exact whole s00 body returns oIIoIooo|-1; neither reproduces the s00 success handler.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
