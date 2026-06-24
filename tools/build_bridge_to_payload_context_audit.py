#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json"
JS = ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def sha(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def js_line(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if row["_line"] == line_no:
            return row
    raise RuntimeError(f"missing js line {line_no}")


def p(rel: str) -> str:
    return str(ROOT / rel)


def find_parent(parent: list[dict[str, Any]], line_no: int) -> dict[str, Any] | None:
    return next((row for row in parent if int(row.get("line") or -1) == line_no), None)


def all_activity_values(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for idx, act in enumerate(activities):
        for key, value in (act.get("d") or {}).items():
            out.append({
                "activityIndex": idx,
                "activityType": act.get("t"),
                "key": key,
                "value": value,
                "valueSha256": sha(value),
            })
    return out


def main() -> int:
    inventory = load("output/protocol_reverse/hypothesis_reframe/server_observable_state_inventory.json")
    timeline = load("output/protocol_reverse/cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json")
    field_map = load("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json")
    encoded = load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")
    cookie_gap = load("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json")

    rows = read_jsonl(JS)
    tf_payload = js_line(rows, 922)
    tf_prepc = js_line(rows, 921)
    payload_activities = (tf_payload.get("data") or {}).get("activities") or []
    prepc_activities = (tf_prepc.get("data") or {}).get("activities") or []
    payload_values = all_activity_values(payload_activities)
    prepc_values = all_activity_values(prepc_activities)

    parent_messages = timeline.get("parentMessages") or []
    correlations = timeline.get("correlations") or []
    p688 = find_parent(parent_messages, 688)
    p689 = find_parent(parent_messages, 689)

    px3_payload_matches = [
        {k: v for k, v in item.items() if k != "value"}
        for item in payload_values
        if p688 and item.get("value") == p688.get("value")
    ]
    pxde_payload_matches = [
        {k: v for k, v in item.items() if k != "value"}
        for item in payload_values
        if p689 and item.get("value") == p689.get("value")
    ]
    px3_prepc_matches = [
        {k: v for k, v in item.items() if k != "value"}
        for item in prepc_values
        if p688 and item.get("value") == p688.get("value")
    ]

    pre_seq5_parent = [
        row for row in parent_messages
        if int(row.get("line") or 0) < 933 and row.get("name") in {"_px3", "_pxde", "_pxvid", "challenge_success"}
    ]
    post_seq5_parent = [
        row for row in parent_messages
        if int(row.get("line") or 0) >= 933 and row.get("name") in {"_px3", "_pxde", "_pxvid", "challenge_success"}
    ]

    result = {
        "purpose": "Audit whether browser parent bridge state is mapped to final line922 payload fields or only to outer browser/Microsoft context.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "serverObservableStateInventory": p("output/protocol_reverse/hypothesis_reframe/server_observable_state_inventory.json"),
            "cookieTimeline": p("output/protocol_reverse/cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json"),
            "jsTrace": str(JS),
            "line922DynamicFieldSourceMap": p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
            "encodedPayloadPcFormDiffMap": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "cookieSessionLineageGap": p("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
        },
        "preSeq5Bridge": {
            "parentLine688Px3": {
                "present": p688 is not None,
                "name": (p688 or {}).get("name"),
                "valueSha256": sha((p688 or {}).get("value") or ""),
                "correlation": next((c for c in correlations if c.get("parentLine") == 688), None),
            },
            "parentLine689Pxde": {
                "present": p689 is not None,
                "name": (p689 or {}).get("name"),
                "valueSha256": sha((p689 or {}).get("value") or ""),
                "correlation": next((c for c in correlations if c.get("parentLine") == 689), None),
            },
            "preSeq5ParentCount": len(pre_seq5_parent),
            "postSeq5ParentCount": len(post_seq5_parent),
        },
        "payloadMapping": {
            "px3ParentValueMatchesLine921Prepc": px3_prepc_matches,
            "px3ParentValueMatchesLine922Payload": px3_payload_matches,
            "pxdeParentValueMatchesLine922Payload": pxde_payload_matches,
            "line922FieldMapSummary": field_map.get("summary"),
            "encodedLayerChecks": encoded.get("checks"),
        },
        "contextEvidence": {
            "line933HasNoCookieHeader": (cookie_gap.get("checks") or {}).get("line933RequestHasNoCookieHeader"),
            "freshSeq5HasNoCookieHeader": (cookie_gap.get("checks") or {}).get("freshSeq5RequestHasNoCookieHeader"),
            "s00ChallengeSuccessParentMessageObserved": (cookie_gap.get("checks") or {}).get("s00ChallengeSuccessParentMessageObserved"),
            "riskVerifyMaterialForS00Present": (ROOT / "output/protocol_reverse/risk_verify/risk_verify_material_s00ld1lglrw0_1781191381.json").exists(),
        },
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "The _px3 bridge value is proven to enter line921/922 payload activities, but decoded payload equality controls already reproduce this semantic field and still reject. _pxde does not map to line922 payload fields. The remaining bridge impact, if any, is browser/Microsoft context or server state, and s00 risk/verify material is missing for this run.",
            "nextArtifact": p("output/protocol_reverse/hypothesis_reframe/s00_risk_verify_material_gap.json"),
            "nextScript": str(ROOT / "tools/build_s00_risk_verify_material_gap.py"),
        },
        "checks": {
            "inventoryRequiresThisArtifact": (inventory.get("decision") or {}).get("nextArtifact") == str(OUT),
            "hasParentPx3BeforeLine922": p688 is not None,
            "hasParentPxdeBeforeLine922": p689 is not None,
            "parentPx3MatchesLine922Payload": bool(px3_payload_matches),
            "parentPxdeMatchesLine922Payload": bool(pxde_payload_matches),
            "decodedPayloadAlreadyEqual": (encoded.get("checks") or {}).get("decodedJsonEqual") is True,
            "line933NoCookieHeader": (cookie_gap.get("checks") or {}).get("line933RequestHasNoCookieHeader") is True,
            "freshSeq5NoCookieHeader": (cookie_gap.get("checks") or {}).get("freshSeq5RequestHasNoCookieHeader") is True,
            "s00RiskVerifyMaterialMissing": not (ROOT / "output/protocol_reverse/risk_verify/risk_verify_material_s00ld1lglrw0_1781191381.json").exists(),
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
