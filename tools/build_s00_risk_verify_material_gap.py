#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
COOKIE_TIMELINE = REPO / "output/protocol_reverse/cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json"
COLLECTOR_DECODE = REPO / "output/protocol_reverse/collector_decode/collector_decode_s00ld1lglrw0_1781191381.json"
BRIDGE_AUDIT = REPO / "output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json"
OUT = REPO / "output/protocol_reverse/hypothesis_reframe/s00_risk_verify_material_gap.json"
MATERIAL_OUT = REPO / "output/protocol_reverse/risk_verify/risk_verify_material_s00ld1lglrw0_1781191381.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def maybe_json(text: Any) -> Any:
    if not isinstance(text, str) or not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def sha256_text(text: Any) -> str | None:
    if not isinstance(text, str):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_http_pairs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pending: dict[str, list[dict[str, Any]]] = {}
    pairs: list[dict[str, Any]] = []
    for row in rows:
        url = row.get("url")
        if not isinstance(url, str):
            continue
        if row.get("kind") == "request":
            pending.setdefault(url, []).append(row)
            continue
        if row.get("kind") == "response":
            queue = pending.get(url) or []
            req = queue.pop(0) if queue else None
            pairs.append({"request": req, "response": row})
    return pairs


def first_meta(req_body: dict[str, Any]) -> dict[str, Any]:
    meta = req_body.get("riskProviderMetadata")
    if isinstance(meta, list) and meta and isinstance(meta[0], dict):
        return meta[0]
    if isinstance(meta, dict):
        return meta
    return {}


def source_index(cookie_timeline: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    parent_by_line = {row.get("line"): row for row in cookie_timeline.get("parentMessages", [])}
    parent_by_event: dict[tuple[Any, Any, str], dict[str, Any]] = {}
    for row in cookie_timeline.get("correlations", []):
        key = (row.get("collectorLine"), row.get("partIndex"), row.get("name"))
        parent_by_event[key] = parent_by_line.get(row.get("parentLine")) or {}

    sources: dict[str, list[dict[str, Any]]] = {}
    for ev in cookie_timeline.get("decodedEvents", []):
        name = ev.get("name")
        value = ev.get("value")
        if not isinstance(name, str) or value is None:
            continue
        item = {
            "source": ev.get("source"),
            "collectorLine": ev.get("collectorLine"),
            "partIndex": ev.get("partIndex"),
            "handler": ev.get("handler"),
            "ttl": ev.get("ttl"),
            "value": value,
            "parentMessage": parent_by_event.get((ev.get("collectorLine"), ev.get("partIndex"), name)),
        }
        sources.setdefault(name, []).append(item)
    return sources


def find_value_source(sources: dict[str, list[dict[str, Any]]], name: str, value: Any, request_time: Any) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    for row in sources.get(name, []):
        if row.get("value") != value:
            continue
        parent = row.get("parentMessage") or {}
        parent_t = parent.get("wall_t")
        return {
            **row,
            "temporalProof": {
                "parentWallTime": parent_t,
                "requestTime": request_time,
                "parentBeforeRequest": isinstance(parent_t, (int, float))
                and isinstance(request_time, (int, float))
                and parent_t <= request_time,
            },
        }
    return None


def summarize_headers(headers: Any) -> dict[str, Any]:
    if not isinstance(headers, dict):
        return {}
    wanted = {}
    for key in [
        "origin",
        "referer",
        "content-type",
        "user-agent",
        "cookie",
        "x-ms-apiversion",
        "canary",
        "hpgid",
        "scid",
    ]:
        for actual, value in headers.items():
            if str(actual).lower() == key:
                wanted[str(actual)] = value
    return wanted


def summarize_risk_pair(pair: dict[str, Any], sources: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    req = pair.get("request") or {}
    resp = pair.get("response") or {}
    req_text = req.get("post_data")
    resp_text = resp.get("body")
    req_body = maybe_json(req_text)
    resp_body = maybe_json(resp_text)
    req_body_dict = req_body if isinstance(req_body, dict) else {}
    resp_body_dict = resp_body if isinstance(resp_body, dict) else {}
    challenge = req_body_dict.get("challengeSolution") if isinstance(req_body_dict.get("challengeSolution"), dict) else {}
    meta = first_meta(req_body_dict)

    fields: dict[str, dict[str, Any]] = {}
    for logical, cookie_name in (("px3", "_px3"), ("pxde", "_pxde"), ("pxvid", "_pxvid")):
        challenge_value = challenge.get(logical)
        meta_value = meta.get(logical)
        value = challenge_value if challenge_value is not None else meta_value
        fields[logical] = {
            "challengeSolutionPresent": challenge_value is not None,
            "riskProviderMetadataPresent": meta_value is not None,
            "challengeSolutionEqualsMetadata": challenge_value == meta_value if challenge_value is not None and meta_value is not None else None,
            "valueSha256": sha256_text(value),
            "valueLength": len(value) if isinstance(value, str) else None,
            "source": find_value_source(sources, cookie_name, value, req.get("t")),
        }

    return {
        "requestLine": req.get("_line"),
        "responseLine": resp.get("_line"),
        "url": req.get("url") or resp.get("url"),
        "method": req.get("method"),
        "status": resp.get("status"),
        "requestTime": req.get("t"),
        "responseTime": resp.get("t"),
        "requestHeadersSubset": summarize_headers(req.get("headers")),
        "responseHeadersSubset": summarize_headers(resp.get("headers")),
        "requestBodySha256": sha256_text(req_text),
        "responseBodySha256": sha256_text(resp_text),
        "requestKeys": sorted(req_body_dict.keys()),
        "responseKeys": sorted(resp_body_dict.keys()),
        "state": resp_body_dict.get("state"),
        "challengeType": (challenge or {}).get("challengeType"),
        "hasChallengeSolution": bool(challenge),
        "hasRiskProviderMetadata": bool(req_body_dict.get("riskProviderMetadata")),
        "hasMsaRiskVerifySignature": "msaRiskVerifySignature" in req_body_dict,
        "continuationTokenSha256": sha256_text(req_body_dict.get("continuationToken")),
        "responseContinuationTokenSha256": sha256_text(resp_body_dict.get("continuationToken")),
        "challengeDetails": resp_body_dict.get("challengeDetails"),
        "pxFields": fields,
    }


def summarize_create_pair(pair: dict[str, Any]) -> dict[str, Any]:
    req = pair.get("request") or {}
    resp = pair.get("response") or {}
    req_body = maybe_json(req.get("post_data"))
    resp_body = maybe_json(resp.get("body"))
    req_body_dict = req_body if isinstance(req_body, dict) else {}
    resp_body_dict = resp_body if isinstance(resp_body, dict) else {}
    return {
        "requestLine": req.get("_line"),
        "responseLine": resp.get("_line"),
        "url": req.get("url"),
        "method": req.get("method"),
        "status": resp.get("status"),
        "requestTime": req.get("t"),
        "responseTime": resp.get("t"),
        "requestHeadersSubset": summarize_headers(req.get("headers")),
        "responseHeadersSubset": summarize_headers(resp.get("headers")),
        "requestBodySha256": sha256_text(req.get("post_data")),
        "responseBodySha256": sha256_text(resp.get("body")),
        "requestKeys": sorted(req_body_dict.keys()),
        "responseKeys": sorted(resp_body_dict.keys()),
        "continuationTokenSha256": sha256_text(req_body_dict.get("ContinuationToken")),
        "hasRedirectUrl": bool(resp_body_dict.get("redirectUrl")),
        "redirectUrlPrefix": str(resp_body_dict.get("redirectUrl", ""))[:180] if resp_body_dict.get("redirectUrl") else None,
        "signinName": resp_body_dict.get("signinName"),
    }


def token_links(risk_rows: list[dict[str, Any]], create_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for idx, row in enumerate(risk_rows):
        token = row.get("responseContinuationTokenSha256")
        if not token:
            continue
        for next_row in risk_rows[idx + 1 :]:
            if next_row.get("continuationTokenSha256") == token:
                links.append(
                    {
                        "from": f"risk.response:{row.get('responseLine')}",
                        "to": f"risk.request:{next_row.get('requestLine')}",
                        "field": "continuationToken",
                        "match": True,
                    }
                )
        for create in create_rows:
            if create.get("continuationTokenSha256") == token:
                links.append(
                    {
                        "from": f"risk.response:{row.get('responseLine')}",
                        "to": f"create.request:{create.get('requestLine')}",
                        "field": "ContinuationToken",
                        "match": True,
                    }
                )
    return links


def px_source_stats(risk_rows: list[dict[str, Any]]) -> dict[str, Any]:
    final_rows = [row for row in risk_rows if row.get("hasChallengeSolution")]
    mapped: dict[str, bool] = {}
    before: dict[str, bool] = {}
    equal_meta: dict[str, bool] = {}
    for name in ("px3", "pxde", "pxvid"):
        field_rows = [(row.get("pxFields") or {}).get(name) or {} for row in final_rows]
        mapped[name] = bool(field_rows) and all(bool(row.get("source")) for row in field_rows)
        equal_meta[name] = bool(field_rows) and all(row.get("challengeSolutionEqualsMetadata") is True for row in field_rows)
        before[name] = bool(field_rows) and all(((row.get("source") or {}).get("temporalProof") or {}).get("parentBeforeRequest") is True for row in field_rows)
    return {
        "challengeSolutionRows": len(final_rows),
        "allChallengePxFieldsMappedToCookieTimeline": bool(final_rows) and all(mapped.values()),
        "allMappedParentMessagesBeforeRiskVerify": bool(final_rows) and all(before.values()),
        "allChallengeSolutionPxFieldsEqualRiskProviderMetadata": bool(final_rows) and all(equal_meta.values()),
        "perFieldMapped": mapped,
        "perFieldParentBeforeRequest": before,
        "perFieldChallengeEqualsMetadata": equal_meta,
    }


def build() -> dict[str, Any]:
    rows = read_jsonl(RUNTIME_TRACE)
    cookie_timeline = read_json(COOKIE_TIMELINE)
    collector_decode = read_json(COLLECTOR_DECODE)
    bridge_audit = read_json(BRIDGE_AUDIT)

    pairs = find_http_pairs(rows)
    sources = source_index(cookie_timeline)
    initialize_pairs = [p for p in pairs if "risk/initialize" in str(((p.get("request") or {}).get("url") or (p.get("response") or {}).get("url") or ""))]
    risk_pairs = [p for p in pairs if "risk/verify" in str(((p.get("request") or {}).get("url") or ""))]
    create_pairs = [p for p in pairs if "API/CreateAccount" in str(((p.get("request") or {}).get("url") or ""))]

    risk_rows = [summarize_risk_pair(pair, sources) for pair in risk_pairs]
    create_rows = [summarize_create_pair(pair) for pair in create_pairs]
    links = token_links(risk_rows, create_rows)
    px_stats = px_source_stats(risk_rows)
    final_continue = [row for row in risk_rows if row.get("state") == "continue"]
    create_redirect = [row for row in create_rows if row.get("hasRedirectUrl")]

    material = {
        "runtimeTrace": str(RUNTIME_TRACE),
        "cookieTimeline": str(COOKIE_TIMELINE),
        "collectorDecode": str(COLLECTOR_DECODE),
        "riskVerify": risk_rows,
        "createAccount": create_rows,
        "tokenLinks": links,
        "pxSourceStats": px_stats,
    }
    MATERIAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    MATERIAL_OUT.write_text(json.dumps(material, ensure_ascii=False, indent=2), encoding="utf-8")

    checks = {
        "bridgeAuditRequiresThisArtifact": (bridge_audit.get("decision") or {}).get("nextArtifact") == str(OUT),
        "runtimeTraceExists": RUNTIME_TRACE.exists(),
        "cookieTimelineExists": COOKIE_TIMELINE.exists(),
        "collectorDecodeExists": COLLECTOR_DECODE.exists(),
        "hasRiskInitialize": bool(initialize_pairs),
        "hasRiskVerify": bool(risk_rows),
        "hasTwoRiskVerifyRequests": len(risk_rows) == 2,
        "hasCreateAccount": bool(create_rows),
        "riskVerifyStateContinue": bool(final_continue),
        "createAccountRedirectUrl": bool(create_redirect),
        "riskResponseTokenFeedsCreateAccount": any(link.get("to", "").startswith("create.request:") for link in links),
        "finalRiskHasChallengeSolution": any(row.get("hasChallengeSolution") and row.get("state") == "continue" for row in risk_rows),
        "finalChallengePxFieldsMappedToCookieTimeline": px_stats["allChallengePxFieldsMappedToCookieTimeline"],
        "finalMappedParentMessagesBeforeRiskVerify": px_stats["allMappedParentMessagesBeforeRiskVerify"],
        "challengePxEqualsRiskProviderMetadata": px_stats["allChallengeSolutionPxFieldsEqualRiskProviderMetadata"],
        "riskVerifyMaterialGenerated": MATERIAL_OUT.exists(),
        "readyForFreshExperiment": False,
    }

    decision = {
        "readyForFreshExperiment": False,
        "recommendedExperiment": None,
        "reason": (
            "s00 risk/verify and CreateAccount material is now structured: final risk/verify returns state=continue and its continuation token feeds CreateAccount redirect. "
            "This resolves the missing-material gap but does not yet identify a single fresh-session state transition; next evidence must map collector accepted line933 output to the risk/verify consumed fields."
        ),
        "nextArtifact": str(REPO / "output/protocol_reverse/hypothesis_reframe/collector_to_risk_consumption_chain.json"),
        "nextScript": str(REPO / "tools/build_collector_to_risk_consumption_chain.py"),
    }

    return {
        "artifact": str(OUT),
        "inputs": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "cookieTimeline": str(COOKIE_TIMELINE),
            "collectorDecode": str(COLLECTOR_DECODE),
            "bridgeAudit": str(BRIDGE_AUDIT),
            "materialOutput": str(MATERIAL_OUT),
        },
        "counts": {
            "runtimeRows": len(rows),
            "httpPairs": len(pairs),
            "riskInitializePairs": len(initialize_pairs),
            "riskVerifyPairs": len(risk_rows),
            "createAccountPairs": len(create_rows),
            "riskContinueResponses": len(final_continue),
            "createAccountRedirectResponses": len(create_redirect),
            "tokenLinks": len(links),
            "collectorDecodedEntries": collector_decode.get("entryCount"),
            "cookieDecodedEvents": len(cookie_timeline.get("decodedEvents", [])),
            "parentMessages": len(cookie_timeline.get("parentMessages", [])),
            "correlations": len(cookie_timeline.get("correlations", [])),
        },
        "riskVerifyLines": [
            {
                "requestLine": row.get("requestLine"),
                "responseLine": row.get("responseLine"),
                "status": row.get("status"),
                "state": row.get("state"),
                "requestKeys": row.get("requestKeys"),
                "responseKeys": row.get("responseKeys"),
                "hasChallengeSolution": row.get("hasChallengeSolution"),
                "hasRiskProviderMetadata": row.get("hasRiskProviderMetadata"),
                "challengeType": row.get("challengeType"),
            }
            for row in risk_rows
        ],
        "createAccountLines": [
            {
                "requestLine": row.get("requestLine"),
                "responseLine": row.get("responseLine"),
                "status": row.get("status"),
                "hasRedirectUrl": row.get("hasRedirectUrl"),
                "requestKeys": row.get("requestKeys"),
                "responseKeys": row.get("responseKeys"),
            }
            for row in create_rows
        ],
        "tokenLinks": links,
        "pxSourceStats": px_stats,
        "checks": checks,
        "decision": decision,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "material": str(MATERIAL_OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
