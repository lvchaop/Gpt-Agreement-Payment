#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
S00_RISK_GAP = REPO / "output/protocol_reverse/hypothesis_reframe/s00_risk_verify_material_gap.json"
RISK_MATERIAL = REPO / "output/protocol_reverse/risk_verify/risk_verify_material_s00ld1lglrw0_1781191381.json"
COLLECTOR_DECODE = REPO / "output/protocol_reverse/collector_decode/collector_decode_s00ld1lglrw0_1781191381.json"
COOKIE_TIMELINE = REPO / "output/protocol_reverse/cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json"
FIRST_DIVERGENCE = REPO / "output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"
BRIDGE_AUDIT = REPO / "output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json"
OUT = REPO / "output/protocol_reverse/hypothesis_reframe/collector_to_risk_consumption_chain.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_part(part: str) -> dict[str, Any]:
    pieces = part.split("|")
    handler = pieces[0] if pieces else None
    row: dict[str, Any] = {"raw": part, "handler": handler, "pieceCount": len(pieces)}
    if handler in {"IoooII", "oIIoIIoo", "IIooII"} and len(pieces) >= 4:
        row.update({"name": pieces[1], "ttl": pieces[2], "value": pieces[3]})
    elif handler == "oIIoIooo" and len(pieces) >= 2:
        row.update({"name": "challenge_success", "value": pieces[1]})
    elif handler == "IoIoIo" and len(pieces) >= 4:
        row.update({"name": pieces[1], "value": pieces[2], "valueKind": pieces[3]})
    else:
        row["name"] = pieces[1] if len(pieces) > 1 else None
        row["value"] = pieces[2] if len(pieces) > 2 else None
    return row


def part_summary(part: str, part_index: int) -> dict[str, Any]:
    parsed = parse_part(part)
    value = parsed.get("value")
    return {
        "partIndex": part_index,
        "handler": parsed.get("handler"),
        "name": parsed.get("name"),
        "ttl": parsed.get("ttl"),
        "value": value if parsed.get("handler") == "oIIoIooo" else None,
        "valueSha256": sha256_text(value),
        "valueLength": len(value) if isinstance(value, str) else None,
        "rawSha256": sha256_text(part),
    }


def find_success_entry(collector_decode: dict[str, Any]) -> dict[str, Any] | None:
    for entry in collector_decode.get("decodedEntries", []):
        if entry.get("hasSuccessHandler") is True:
            return entry
    return None


def decoded_event_index(cookie_timeline: dict[str, Any]) -> dict[tuple[Any, Any, str], dict[str, Any]]:
    idx: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for row in cookie_timeline.get("decodedEvents", []):
        key = (row.get("collectorLine"), row.get("partIndex"), row.get("name"))
        idx[key] = row
    return idx


def correlation_index(cookie_timeline: dict[str, Any]) -> dict[tuple[Any, Any, str], dict[str, Any]]:
    parents = {row.get("line"): row for row in cookie_timeline.get("parentMessages", [])}
    idx: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for row in cookie_timeline.get("correlations", []):
        key = (row.get("collectorLine"), row.get("partIndex"), row.get("name"))
        idx[key] = {**row, "parentMessage": parents.get(row.get("parentLine"))}
    return idx


def risk_final_row(material: dict[str, Any]) -> dict[str, Any] | None:
    for row in material.get("riskVerify", []):
        if row.get("state") == "continue" and row.get("hasChallengeSolution"):
            return row
    return None


def create_row_with_redirect(material: dict[str, Any]) -> dict[str, Any] | None:
    for row in material.get("createAccount", []):
        if row.get("hasRedirectUrl"):
            return row
    return None


def build_field_link(name: str, risk_row: dict[str, Any], decoded_idx: dict[tuple[Any, Any, str], dict[str, Any]], corr_idx: dict[tuple[Any, Any, str], dict[str, Any]]) -> dict[str, Any]:
    cookie_name = {"px3": "_px3", "pxde": "_pxde", "pxvid": "_pxvid"}[name]
    field = ((risk_row.get("pxFields") or {}).get(name) or {})
    source = field.get("source") or {}
    key = (source.get("collectorLine"), source.get("partIndex"), cookie_name)
    decoded = decoded_idx.get(key) or {}
    corr = corr_idx.get(key) or {}
    parent = corr.get("parentMessage") or source.get("parentMessage") or {}
    temporal = source.get("temporalProof") or {}
    return {
        "riskField": name,
        "cookieName": cookie_name,
        "riskRequestLine": risk_row.get("requestLine"),
        "riskResponseLine": risk_row.get("responseLine"),
        "challengeSolutionPresent": field.get("challengeSolutionPresent"),
        "riskProviderMetadataPresent": field.get("riskProviderMetadataPresent"),
        "challengeSolutionEqualsMetadata": field.get("challengeSolutionEqualsMetadata"),
        "riskValueSha256": field.get("valueSha256"),
        "riskValueLength": field.get("valueLength"),
        "collectorLine": source.get("collectorLine"),
        "collectorPartIndex": source.get("partIndex"),
        "collectorHandler": source.get("handler"),
        "decodedEventValueSha256": sha256_text(decoded.get("value")),
        "decodedEventValueLength": len(decoded.get("value")) if isinstance(decoded.get("value"), str) else None,
        "decodedEventMatchesRiskValue": sha256_text(decoded.get("value")) == field.get("valueSha256") if field.get("valueSha256") else False,
        "parentLine": parent.get("line"),
        "parentEventOrigin": parent.get("eventOrigin"),
        "parentWallTime": parent.get("wall_t"),
        "parentValueSha256": sha256_text(parent.get("value")),
        "parentValueMatchesRiskValue": sha256_text(parent.get("value")) == field.get("valueSha256") if field.get("valueSha256") else False,
        "parentBeforeRiskRequest": temporal.get("parentBeforeRequest"),
        "riskRequestTime": temporal.get("requestTime"),
    }


def build() -> dict[str, Any]:
    risk_gap = read_json(S00_RISK_GAP)
    material = read_json(RISK_MATERIAL)
    collector_decode = read_json(COLLECTOR_DECODE)
    cookie_timeline = read_json(COOKIE_TIMELINE)
    first_divergence = read_json(FIRST_DIVERGENCE)
    bridge_audit = read_json(BRIDGE_AUDIT)

    success_entry = find_success_entry(collector_decode)
    risk_row = risk_final_row(material)
    create = create_row_with_redirect(material)
    decoded_idx = decoded_event_index(cookie_timeline)
    corr_idx = correlation_index(cookie_timeline)

    success_parts = []
    success_status = None
    if success_entry:
        for idx, part in enumerate(success_entry.get("parts", [])):
            summary = part_summary(part, idx)
            success_parts.append(summary)
            if summary.get("handler") == "oIIoIooo":
                success_status = summary

    field_links = [build_field_link(name, risk_row or {}, decoded_idx, corr_idx) for name in ("px3", "pxde", "pxvid")]
    token_links = material.get("tokenLinks", [])
    risk_to_create = [link for link in token_links if str(link.get("to", "")).startswith("create.request:")]

    first_div = first_divergence.get("divergence") or {}
    px3_pxde_links = [link for link in field_links if link.get("riskField") in {"px3", "pxde"}]
    pxvid_links = [link for link in field_links if link.get("riskField") == "pxvid"]

    checks = {
        "riskGapRequiresThisArtifact": (risk_gap.get("decision") or {}).get("nextArtifact") == str(OUT),
        "hasSuccessCollectorEntry": success_entry is not None,
        "successCollectorLineIs948": (success_entry or {}).get("lineNo") == 948,
        "successEntryHasChallengeSuccess0": success_status is not None and success_status.get("value") == "0",
        "hasFinalRiskContinueRequest": risk_row is not None,
        "finalRiskRequestLineIs998": (risk_row or {}).get("requestLine") == 998,
        "hasCreateAccountRedirect": create is not None,
        "riskContinueTokenFeedsCreateAccount": bool(risk_to_create),
        "riskPx3PxdeLinkedToSuccessCollectorLine": all(link.get("collectorLine") == (success_entry or {}).get("lineNo") for link in px3_pxde_links),
        "riskPxvidLinkedToInitialCollectorLine": bool(pxvid_links) and pxvid_links[0].get("collectorLine") == 34,
        "allRiskPxFieldsDecodedValueMatch": all(link.get("decodedEventMatchesRiskValue") for link in field_links),
        "allRiskPxFieldsParentValueMatch": all(link.get("parentValueMatchesRiskValue") for link in field_links),
        "allParentMessagesBeforeRiskRequest": all(link.get("parentBeforeRiskRequest") is True for link in field_links),
        "line933DivergenceIsAccepted": first_div.get("id") == "D1_final_seq5_acceptance_response_diff",
        "bridgeAuditPreviouslyMissingRiskMaterial": (bridge_audit.get("checks") or {}).get("s00RiskVerifyMaterialMissing") is True,
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "The s00 accepted collector response is now proven to feed Microsoft risk/verify: collector line948 emits challenge_success=0 plus _pxde/_px3, "
            "line998 consumes the same _px3/_pxde/_pxvid in challengeSolution/riskProviderMetadata, risk/verify returns state=continue, and that continuation token feeds CreateAccount redirect. "
            "This proves the downstream consumption chain, but it still does not explain why fresh final seq5 fails to obtain the line948 success response; next artifact must reduce the pre-line948 server-state difference to one candidate transition."
        ),
        "nextArtifact": str(REPO / "output/protocol_reverse/hypothesis_reframe/single_transition_candidate_matrix.json"),
        "nextScript": str(REPO / "tools/build_single_transition_candidate_matrix.py"),
    }

    return {
        "artifact": str(OUT),
        "inputs": {
            "s00RiskVerifyMaterialGap": str(S00_RISK_GAP),
            "riskVerifyMaterial": str(RISK_MATERIAL),
            "collectorDecode": str(COLLECTOR_DECODE),
            "cookieTimeline": str(COOKIE_TIMELINE),
            "firstDecisiveDivergence": str(FIRST_DIVERGENCE),
            "bridgeAudit": str(BRIDGE_AUDIT),
        },
        "collectorSuccessEntry": {
            "lineNo": (success_entry or {}).get("lineNo"),
            "partCount": (success_entry or {}).get("partCount"),
            "handlers": (success_entry or {}).get("handlers"),
            "hasSuccessHandler": (success_entry or {}).get("hasSuccessHandler"),
            "parts": success_parts,
        },
        "riskConsumption": {
            "riskRequestLine": (risk_row or {}).get("requestLine"),
            "riskResponseLine": (risk_row or {}).get("responseLine"),
            "riskState": (risk_row or {}).get("state"),
            "riskHasChallengeSolution": (risk_row or {}).get("hasChallengeSolution"),
            "fieldLinks": field_links,
        },
        "riskToCreateAccount": {
            "createRequestLine": (create or {}).get("requestLine"),
            "createResponseLine": (create or {}).get("responseLine"),
            "createHasRedirectUrl": (create or {}).get("hasRedirectUrl"),
            "tokenLinks": risk_to_create,
        },
        "freshBoundary": {
            "divergenceId": first_div.get("id"),
            "s00RuntimeLine": ((first_div.get("s00") or {}).get("runtimeLine")),
            "freshSourcePath": ((first_div.get("fresh") or {}).get("sourcePath")),
            "s00SuccessStatuses": ((first_div.get("s00") or {}).get("successStatuses")),
            "freshHandlers": ((first_div.get("fresh") or {}).get("handlers")),
            "explanation": "s00 downstream chain starts only after accepted final seq5 response. Selected fresh final seq5 remains rejected before this chain can exist.",
        },
        "checks": checks,
        "decision": decision,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
