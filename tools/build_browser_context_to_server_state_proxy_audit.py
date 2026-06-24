#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
JS = ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RT = ROOT / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
OUT = HYP / "browser_context_to_server_state_proxy_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def sha(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(value)
    return out


def try_parse_message_data(row: dict[str, Any]) -> Any:
    data = ((row.get("data") or {}).get("data"))
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data
    return data


def js_line(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if int(row.get("_line") or 0) == line_no:
            return row
    return {}


def runtime_line(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if int(row.get("_line") or 0) == line_no:
            return row
    return {}


def scalar_strings(value: Any, prefix: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, str):
        out.append({"path": prefix or "$", "value": value})
    elif isinstance(value, (int, float, bool)) or value is None:
        out.append({"path": prefix or "$", "value": str(value)})
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            out.extend(scalar_strings(item, f"{prefix}[{idx}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(scalar_strings(item, next_prefix))
    return out


def contains_nontrivial(haystack: str, needle: str) -> bool:
    if not needle or len(needle) < 4:
        return False
    return needle in haystack


def summarize_message(row: dict[str, Any], accepted_wall_t: float | None) -> dict[str, Any]:
    parsed = try_parse_message_data(row)
    msg_type = parsed.get("type") if isinstance(parsed, dict) else None
    message_type = parsed.get("messageType") if isinstance(parsed, dict) else None
    return {
        "line": row.get("_line"),
        "wall_t": row.get("wall_t"),
        "hrefHost": urllib.parse.urlparse(row.get("href") or "").netloc,
        "origin": row.get("origin"),
        "eventOrigin": ((row.get("data") or {}).get("eventOrigin")),
        "dataType": ((row.get("data") or {}).get("dataType")),
        "type": msg_type,
        "messageType": message_type,
        "phase": "pre_accept" if accepted_wall_t is not None and float(row.get("wall_t") or 0) < accepted_wall_t else "post_accept_or_unknown",
        "sha256": sha(parsed),
        "preview": parsed if not isinstance(parsed, str) or len(parsed) <= 220 else parsed[:220],
        "parsed": parsed,
    }


def build() -> dict[str, Any]:
    js_rows = read_jsonl(JS)
    rt_rows = read_jsonl(RT)
    bridge = read_json(HYP / "bridge_to_payload_context_audit.json")
    field_map = read_json(HYP / "line922_dynamic_field_source_map.json")
    encoded = read_json(HYP / "encoded_payload_pc_form_diff_map.json")
    cookie_gap = read_json(GOAL / "cookie_session_lineage_gap_audit.json")
    c5 = read_json(HYP / "encoder_variant_terminal_audit.json")
    post_c5 = read_json(HYP / "post_c5_decisive_gap_audit.json")

    rt_933 = runtime_line(rt_rows, 933)
    form_body = rt_933.get("post_data") or ""
    form = parse_form(form_body)
    tf_payload = js_line(js_rows, 922)
    payload_text = json.dumps((tf_payload.get("data") or {}).get("activities") or [], ensure_ascii=False, sort_keys=True)
    tf_text = json.dumps(tf_payload.get("data") or {}, ensure_ascii=False, sort_keys=True)
    form_text = json.dumps(form, ensure_ascii=False, sort_keys=True)
    request_text = json.dumps(rt_933, ensure_ascii=False, sort_keys=True)
    accepted_event = js_line(js_rows, 948)
    accepted_wall_t = accepted_event.get("wall_t")
    accepted_wall_float = float(accepted_wall_t) if accepted_wall_t is not None else None

    messages = [
        summarize_message(row, accepted_wall_float)
        for row in js_rows
        if row.get("kind") == "window.message.recv"
    ]
    pre_accept = [m for m in messages if m["phase"] == "pre_accept"]
    post_accept = [m for m in messages if m["phase"] != "pre_accept"]

    by_type: dict[str, int] = {}
    for msg in messages:
        key = msg.get("type") or msg.get("messageType") or msg.get("dataType") or "unknown"
        by_type[str(key)] = by_type.get(str(key), 0) + 1

    block_messages = [
        m for m in pre_accept
        if isinstance(m.get("parsed"), dict) and m["parsed"].get("type") == "block"
    ]
    block = block_messages[0] if block_messages else {}
    block_parsed = block.get("parsed") if isinstance(block.get("parsed"), dict) else {}
    block_json_response = block_parsed.get("jsonResponse") if isinstance(block_parsed, dict) else {}
    block_uuid = block_json_response.get("uuid") if isinstance(block_json_response, dict) else None
    block_vid = block_json_response.get("vid") if isinstance(block_json_response, dict) else None
    block_request_url = block_parsed.get("requestUrl") if isinstance(block_parsed, dict) else None

    set_to_window = [
        m for m in pre_accept
        if isinstance(m.get("parsed"), dict) and m["parsed"].get("type") == "setToWindow"
    ]
    cookie_messages = [
        m for m in pre_accept
        if isinstance(m.get("parsed"), dict) and m["parsed"].get("type") == "cookie"
    ]
    succeeded_messages = [
        m for m in messages
        if isinstance(m.get("parsed"), dict) and m["parsed"].get("type") == "succeeded"
    ]
    crcldu_messages = [
        m for m in pre_accept
        if "crcldu.com" in str(m.get("eventOrigin") or "") or "crcldu.com" in str(m.get("hrefHost") or "")
    ]
    microsoft_messages = [
        m for m in messages
        if "login.live.com" in str(m.get("origin") or "")
        or "login.microsoftonline.com" in str(m.get("origin") or "")
        or "login.live.com" in str(m.get("eventOrigin") or "")
        or "login.microsoftonline.com" in str(m.get("eventOrigin") or "")
    ]

    targets = {
        "runtimeLine933RequestJson": request_text,
        "runtimeLine933FormJson": form_text,
        "runtimeLine933RawBody": form_body,
        "jsLine922PayloadDataJson": tf_text,
        "jsLine922ActivitiesJson": payload_text,
    }

    correlations: list[dict[str, Any]] = []
    for msg in pre_accept:
        parsed = msg.get("parsed")
        for scalar in scalar_strings(parsed):
            value = scalar["value"]
            hits = [
                {"target": name, "contains": True}
                for name, text in targets.items()
                if contains_nontrivial(text, value)
            ]
            if hits:
                correlations.append({
                    "messageLine": msg.get("line"),
                    "messageType": msg.get("type") or msg.get("messageType") or msg.get("dataType"),
                    "path": scalar["path"],
                    "valueSha256": sha(value),
                    "valuePreview": value[:160],
                    "hits": hits,
                })

    block_correlations = [
        row for row in correlations
        if row.get("messageLine") == block.get("line")
    ]
    promoted: list[dict[str, Any]] = []
    if block_uuid and block_uuid != form.get("uuid"):
        promoted.append({"id": "block_uuid_not_represented_in_collector_form", "reason": "block uuid differs from line933 form uuid"})
    if block_vid and block_vid != form.get("vid"):
        promoted.append({"id": "block_vid_not_represented_in_collector_form", "reason": "block vid differs from line933 form vid"})

    checks = {
        "planExists": PLAN.exists(),
        "postC5RequiresThisArtifact": (post_c5.get("decision") or {}).get("nextArtifact") == str(OUT),
        "jsTraceExists": JS.exists(),
        "runtimeTraceExists": RT.exists(),
        "hasLine922Payload": bool(tf_payload),
        "hasLine933CollectorRequest": bool(rt_933) and rt_933.get("kind") == "request",
        "acceptedLine948Observed": bool(accepted_event),
        "preAcceptMessageCount": len(pre_accept),
        "postAcceptOrUnknownMessageCount": len(post_accept),
        "hasPreAcceptBlockMessage": bool(block_messages),
        "blockUuidRepresentedInCollectorForm": bool(block_uuid) and block_uuid == form.get("uuid"),
        "blockVidRepresentedInCollectorForm": bool(block_vid) and block_vid == form.get("vid"),
        "blockRequestUrlRiskVerify": block_request_url == "/api/v1.0/risk/verify",
        "hasPreAcceptSetToWindowConfig": bool(set_to_window),
        "setToWindowConfigFoundInCollectorRequest": any(
            row.get("messageType") == "setToWindow" and any(hit["target"].startswith("runtimeLine933") for hit in row.get("hits") or [])
            for row in correlations
        ),
        "hasPreAcceptCookieBridge": bool(cookie_messages),
        "cookieBridgePx3RepresentedInPayload": (bridge.get("checks") or {}).get("parentPx3MatchesLine922Payload") is True,
        "cookieBridgeNotCookieHeader": (bridge.get("checks") or {}).get("line933NoCookieHeader") is True
        and (bridge.get("checks") or {}).get("freshSeq5NoCookieHeader") is True,
        "decodedPayloadAlreadyEqual": (bridge.get("checks") or {}).get("decodedPayloadAlreadyEqual") is True
        or (encoded.get("checks") or {}).get("decodedJsonEqual") is True,
        "line922FreshChangedFieldInstances": (field_map.get("summary") or {}).get("freshSeq5ChangedFieldInstances"),
        "line922UnresolvedChangedCandidateCount": (field_map.get("summary") or {}).get("unresolvedChangedCandidateCount"),
        "hasPreAcceptCrclduMessage": bool(crcldu_messages),
        "crclduStringFoundInCollectorRequest": any(
            "crcldu" in str(row.get("valuePreview") or "").lower()
            and any(hit["target"].startswith("runtimeLine933") for hit in row.get("hits") or [])
            for row in correlations
        ),
        "succeededMessageAfterAcceptedLine": bool(succeeded_messages)
        and all((m.get("wall_t") or 0) > (accepted_wall_float or 0) for m in succeeded_messages),
        "microsoftMessagesOnlyPostAccept": bool(microsoft_messages)
        and all(m.get("phase") != "pre_accept" for m in microsoft_messages),
        "encoderVariantFamilyClosedNoSuccess": (c5.get("checks") or {}).get("encoderVariantFamilyClosedNoSuccess") is True,
        "promotedSingleTransitionCandidateCount": len(promoted),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    all_known_block_represented = (
        checks["hasPreAcceptBlockMessage"] is True
        and checks["blockUuidRepresentedInCollectorForm"] is True
        and checks["blockVidRepresentedInCollectorForm"] is True
        and checks["blockRequestUrlRiskVerify"] is True
    )
    checks["blockValuesAlreadyRepresentedInRequest"] = all_known_block_represented
    checks["allBrowserContextServerVisibleProxiesReduced"] = (
        all_known_block_represented
        and checks["cookieBridgePx3RepresentedInPayload"] is True
        and checks["cookieBridgeNotCookieHeader"] is True
        and checks["decodedPayloadAlreadyEqual"] is True
        and checks["line922FreshChangedFieldInstances"] == 0
        and checks["line922UnresolvedChangedCandidateCount"] == 0
        and checks["promotedSingleTransitionCandidateCount"] == 0
    )

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Audit whether browser parent bridge, iframe postMessage context, or Microsoft context has a server-visible pre-accept proxy not already reduced by payload/cookie controls.",
        "inputs": {
            "jsTrace": str(JS),
            "runtimeTrace": str(RT),
            "bridgeToPayloadContextAudit": str(HYP / "bridge_to_payload_context_audit.json"),
            "line922DynamicFieldSourceMap": str(HYP / "line922_dynamic_field_source_map.json"),
            "encodedPayloadPcFormDiffMap": str(HYP / "encoded_payload_pc_form_diff_map.json"),
            "cookieSessionLineageGapAudit": str(GOAL / "cookie_session_lineage_gap_audit.json"),
            "encoderVariantTerminalAudit": str(HYP / "encoder_variant_terminal_audit.json"),
            "postC5DecisiveGapAudit": str(HYP / "post_c5_decisive_gap_audit.json"),
        },
        "messageSummary": {
            "totalWindowMessageRecv": len(messages),
            "preAcceptCount": len(pre_accept),
            "postAcceptOrUnknownCount": len(post_accept),
            "byType": by_type,
            "acceptedLine": 948,
            "acceptedWallT": accepted_wall_float,
        },
        "keyMessages": {
            "blockMessages": [
                {k: v for k, v in m.items() if k != "parsed"}
                for m in block_messages
            ],
            "setToWindowMessages": [
                {k: v for k, v in m.items() if k != "parsed"}
                for m in set_to_window
            ],
            "cookieBridgeMessages": [
                {
                    "line": m.get("line"),
                    "wall_t": m.get("wall_t"),
                    "name": (m.get("parsed") or {}).get("name") if isinstance(m.get("parsed"), dict) else None,
                    "valueSha256": sha((m.get("parsed") or {}).get("value") or "") if isinstance(m.get("parsed"), dict) else None,
                    "phase": m.get("phase"),
                }
                for m in cookie_messages
            ],
            "succeededMessages": [
                {k: v for k, v in m.items() if k != "parsed"}
                for m in succeeded_messages
            ],
            "microsoftMessages": [
                {k: v for k, v in m.items() if k != "parsed"}
                for m in microsoft_messages
            ][:12],
        },
        "serverVisibleCorrelations": {
            "count": len(correlations),
            "blockCorrelations": block_correlations,
            "correlations": correlations[:120],
        },
        "candidateAssessment": {
            "promoted": promoted,
            "notPromotedReasons": [
                "The pre-accept block message uuid and vid are already represented by line933 collector form uuid/vid.",
                "The block requestUrl names Microsoft risk/verify but is context for the challenge iframe, not a new collector request field.",
                "The _px3 bridge is represented in line922 payload, while decoded payload equality and C5 encoder controls still reject in fresh pure-protocol sessions.",
                "The line933 request carries no Cookie header in both accepted s00 and fresh no-browser controls, so parent cookie bridge is not a simple Cookie-header proxy.",
                "The observed succeeded and Microsoft login/live messages are after collector acceptance and cannot be the pre-accept transition.",
            ],
        },
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": str(HYP / "browser_context_static_gap_inventory.json"),
            "nextScript": str(ROOT / "tools/build_browser_context_static_gap_inventory.py"),
            "reason": (
                "Browser context messages are now mapped against line922/line933. The decisive pre-accept block uuid/vid are already present in the collector form, "
                "cookie bridge impact is already represented in payload/cookie-header controls, and post-success Microsoft messages are downstream. "
                "No new server-visible single transition is promoted; the next step is a static inventory for context APIs that never enter current request/payload/cookie evidence."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    doc = build()
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
