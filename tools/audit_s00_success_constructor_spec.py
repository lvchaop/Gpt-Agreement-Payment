#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUN_ID = "s00ld1lglrw0_1781191381"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
RUNTIME_TRACE = REPO / f"output/outlook_browser/runtime_trace_{RUN_ID}.jsonl"
JS_TRACE = REPO / f"output/outlook_browser/js_internal_trace_{RUN_ID}.jsonl"
COLLECTOR_DECODE = REPO / f"output/protocol_reverse/collector_decode/collector_decode_{RUN_ID}.json"
BUNDLE_BUILD = REPO / f"output/protocol_reverse/bundle_request_build/bundle_request_build_{RUN_ID}.json"
VALUE_CHAIN = REPO / "output/protocol_reverse/goal_audit/s00_same_session_px561_value_chain_audit.json"
POW_RESPONSE = REPO / f"output/protocol_reverse/pow_response/pow_response_{RUN_ID}.json"
NQ_REPLAY = REPO / f"output/protocol_reverse/wasm/captcha_wasm_nq_replay_{RUN_ID}.json"
OUT_DIR = REPO / "output/protocol_reverse/goal_audit"

SUCCESS_REQUEST_LINE = 933
SUCCESS_TF_LINE = 922
SUCCESS_CHAIN_INDEX = 1
TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "Ew9iCVZkZD4=",
    "KVkYX28zG2o=",
]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def row_at(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if int(row.get("_line") or 0) == line_no:
            return row
    raise KeyError(line_no)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def shape(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
    return {
        "type": type(value).__name__,
        "len": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": sha256_text(text),
        "preview": text[:160] + (f"...<len={len(text)}>" if len(text) > 160 else ""),
    }


def px_activity(activities: list[Any]) -> dict[str, Any]:
    for activity in activities:
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return activity
    raise RuntimeError("PX561 not found")


def decoded_success_request(dec: Any, runtime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = dec.build_marker_timeline(COLLECTOR_DECODE)
    row = row_at(runtime_rows, SUCCESS_REQUEST_LINE)
    params = dec.parse_form(row.get("post_data") or "")
    marker = dec.marker_for_request(timeline, SUCCESS_REQUEST_LINE)
    decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])
    activities = decoded["json"] if isinstance(decoded.get("json"), list) else []
    px = px_activity(activities)
    return {
        "runtimeLine": SUCCESS_REQUEST_LINE,
        "params": params,
        "marker": marker,
        "postDataSha256": sha256_text(row.get("post_data") or ""),
        "decode": {
            "markerMatch": decoded.get("markerMatch"),
            "jsonError": decoded.get("jsonError"),
            "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
            "activityCount": len(activities),
        },
        "px": px,
    }


def tf_success_material(js_rows: list[dict[str, Any]]) -> dict[str, Any]:
    row = row_at(js_rows, SUCCESS_TF_LINE)
    data = row.get("data") or {}
    activities = data.get("activities") or []
    return {
        "line": SUCCESS_TF_LINE,
        "kind": row.get("kind"),
        "wall_t": row.get("wall_t"),
        "perf_t": row.get("perf_t"),
        "serializedSha256": sha256_text(str(data.get("serialized") or "")),
        "serializedLen": len(str(data.get("serialized") or "")),
        "pc": data.get("pc"),
        "cs": data.get("cs"),
        "qi": data.get("qi"),
        "marker": data.get("marker"),
        "activityTypes": [a.get("t") for a in activities if isinstance(a, dict)],
        "activityCount": len(activities),
        "px": px_activity(activities),
    }


def find_js_row(js_rows: list[dict[str, Any]], kind: str, predicate) -> dict[str, Any] | None:
    for row in js_rows:
        if row.get("kind") == kind and predicate(row.get("data") or {}):
            return row
    return None


def source_apply_args(source: str) -> list[Any] | None:
    match = re.search(r"\.apply\(null, \[(.*?)\]\)", source)
    if not match:
        return None
    text = "[" + match.group(1) + "]"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def worker_timing(js_rows: list[dict[str, Any]], pow_value: str, actual_bzt: int | None) -> dict[str, Any]:
    msg = find_js_row(js_rows, "hsprotect.captcha.worker.message", lambda d: d.get("data") == pow_value)
    new = None
    args = None
    if msg:
        url = (msg.get("data") or {}).get("url")
        new = find_js_row(js_rows, "hsprotect.captcha.worker.new", lambda d: d.get("url") == url)
        if new:
            args = source_apply_args(str((new.get("data") or {}).get("source") or ""))
    start_perf_arg = args[7] if args and len(args) > 7 else None
    perf_delta = None
    wall_delta = None
    if msg and new:
        wall_delta = round((float(msg.get("wall_t") or 0) - float(new.get("wall_t") or 0)) * 1000)
    if msg and start_perf_arg is not None:
        perf_delta = int(msg.get("perf_t") or 0) - int(start_perf_arg)
    return {
        "workerNewLine": new.get("_line") if new else None,
        "workerMessageLine": msg.get("_line") if msg else None,
        "workerNewWallT": new.get("wall_t") if new else None,
        "workerMessageWallT": msg.get("wall_t") if msg else None,
        "workerNewPerfT": new.get("perf_t") if new else None,
        "workerMessagePerfT": msg.get("perf_t") if msg else None,
        "sourceApplyArgsPreview": args,
        "sourceStartPerfArg": start_perf_arg,
        "wallDeltaRoundedMs": wall_delta,
        "perfDeltaFromSourceStart": perf_delta,
        "actualBzt": actual_bzt,
        "actualBztWithinOneMsOfPerfDelta": (
            isinstance(actual_bzt, int) and isinstance(perf_delta, int) and abs(actual_bzt - perf_delta) <= 1
        ),
    }


def main() -> int:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    runtime_rows = read_jsonl(RUNTIME_TRACE)
    js_rows = read_jsonl(JS_TRACE)
    request = decoded_success_request(dec, runtime_rows)
    tf = tf_success_material(js_rows)
    build_row = next(r for r in read_json(BUNDLE_BUILD).get("rows") or [] if r.get("requestLine") == SUCCESS_REQUEST_LINE)
    value_chain = read_json(VALUE_CHAIN)["chains"][SUCCESS_CHAIN_INDEX]
    pow_doc = read_json(POW_RESPONSE)
    nq_doc = read_json(NQ_REPLAY)

    px_d = request["px"]["d"]
    tf_px_d = tf["px"]["d"]
    pow_value = value_chain["solvedPow"]["value"]
    actual_bzt = px_d.get("Bzt2fUFRcw==") if isinstance(px_d.get("Bzt2fUFRcw=="), int) else None
    aeax_row = find_js_row(
        js_rows,
        "hsprotect.captcha.tbr9.after_ng",
        lambda d: d.get("aeaxValue") == px_d.get("AEAxBkUsPjQ="),
    )
    nq_row = find_js_row(
        js_rows,
        "hsprotect.captcha.tbr9.after_nq",
        lambda d: d.get("nqValue") == px_d.get("TBR9Ugl7emA=") and d.get("nInput") == pow_value,
    )

    form_sources = {
        "payload": {
            "status": "constructible_from_serialized_marker_uuid",
            "evidence": "bundle_request_build line 933 payloadMatch/bodyMatch",
            "proved": build_row.get("payloadMatch") is True and build_row.get("bodyMatch") is True,
        },
        "pc": {
            "status": "constructible_hmac_md5_from_serialized_uuid_tag_ft",
            "observed": request["params"].get("pc"),
            "rebuilt": build_row.get("rebuiltPc"),
            "proved": build_row.get("pcMatch") is True,
        },
        "marker": {
            "status": "collector_oIIoIoII_marker_before_request",
            "qi": request["marker"].get("qi"),
            "source": request["marker"].get("source"),
            "proved": request["decode"]["markerMatch"] is True,
        },
        "session_params": {
            "status": "observed_runtime_session_state_not_yet_protocol_generated",
            "keys": ["uuid", "tag", "ft", "seq", "en", "cs", "sid", "vid", "cts", "rsc"],
            "values": {k: request["params"].get(k) for k in ["uuid", "tag", "ft", "seq", "en", "cs", "sid", "vid", "cts", "rsc"]},
        },
    }

    target_sources = {
        "OSkIb39DDA==": {
            "status": "proved_constructible_from_collector_pow",
            "value": px_d.get("OSkIb39DDA=="),
            "evidence": {
                "collectorPowLine": value_chain["precedingPowChallenge"].get("lineNo"),
                "powResponseMatchesTarget": value_chain["solvedPow"].get("matchesTarget"),
                "sameSessionCheck": value_chain["comparisons"].get("oskEqualsSolvedPowValue"),
            },
        },
        "TBR9Ugl7emA=": {
            "status": "proved_constructible_from_offline_wasm_NQ_with_pxUuid_and_pow_value",
            "value": px_d.get("TBR9Ugl7emA="),
            "evidence": {
                "runtimeNqLine": nq_row.get("_line") if nq_row else None,
                "nqReplayChecks": nq_doc.get("checks"),
                "sameSessionCheck": value_chain["comparisons"].get("tbr9EqualsNqValue"),
            },
        },
        "AEAxBkUsPjQ=": {
            "status": "producer_identified_as_Ws.Ng_but_live_accepted_substitution_unproved",
            "value": px_d.get("AEAxBkUsPjQ="),
            "evidence": {
                "runtimeAfterNgLine": aeax_row.get("_line") if aeax_row else None,
                "runtimeAfterNgMatchesPx561": bool(aeax_row),
                "offlineNgProbe": (nq_doc.get("ngProbe") or {}).get("a"),
            },
        },
        "Bzt2fUFRcw==": {
            "status": "static_runtime_bridge_identified_but_protocol_timing_policy_unproved",
            "value": px_d.get("Bzt2fUFRcw=="),
            "evidence": worker_timing(js_rows, pow_value, actual_bzt),
        },
    }
    for key in ["fyNOZTpPQF4=", "Ew9iCVZkZD4=", "KVkYX28zG2o="]:
        target_sources[key] = {
            "status": "observed_in_success_px561_not_yet_independently_constructed",
            "value": px_d.get(key),
            "shape": shape(px_d.get(key)),
        }

    checks = {
        "successRequestDecoded": request["decode"]["jsonError"] is None,
        "successMarkerMatches": request["decode"]["markerMatch"] is True,
        "tfMaterialMatchesRequestActivities": tf["activityTypes"] == request["decode"]["activityTypes"],
        "tfMaterialPcMatchesRequest": tf["pc"] == request["params"].get("pc"),
        "bundleRebuildBodyExact": build_row.get("bodyMatch") is True,
        "valueChainSuccessCoherent": (read_json(VALUE_CHAIN).get("checks") or {}).get("successRowSameSessionCoherent") is True,
        "oskConstructible": target_sources["OSkIb39DDA=="]["evidence"]["sameSessionCheck"] is True,
        "tbr9Constructible": target_sources["TBR9Ugl7emA="]["evidence"]["sameSessionCheck"] is True,
        "aeaxProducerObserved": target_sources["AEAxBkUsPjQ="]["evidence"]["runtimeAfterNgMatchesPx561"] is True,
        "bztTimingCompatibleWithinOneMs": target_sources["Bzt2fUFRcw=="]["evidence"]["actualBztWithinOneMsOfPerfDelta"] is True,
        "allPxTargetValuesMatchTfPayload": all(px_d.get(k) == tf_px_d.get(k) for k in TARGET_KEYS),
        "pureProtocolReady": False,
    }

    result = {
        "purpose": "Convert the s00 line 933 observed HUMAN success request into a minimal constructor specification with evidence-labeled source boundaries.",
        "runId": RUN_ID,
        "successRequestLine": SUCCESS_REQUEST_LINE,
        "successTfPayloadLine": SUCCESS_TF_LINE,
        "evidenceFiles": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "jsTrace": str(JS_TRACE),
            "collectorDecode": str(COLLECTOR_DECODE),
            "bundleBuild": str(BUNDLE_BUILD),
            "valueChain": str(VALUE_CHAIN),
            "powResponse": str(POW_RESPONSE),
            "nqReplay": str(NQ_REPLAY),
        },
        "observedSuccess": {
            "request": {
                "postDataSha256": request["postDataSha256"],
                "params": {k: request["params"].get(k) for k in ["uuid", "tag", "ft", "seq", "cs", "pc", "sid", "vid", "cts"]},
                "activityTypes": request["decode"]["activityTypes"],
                "pxFieldCount": len(px_d),
                "targetShapes": {k: shape(px_d.get(k)) for k in TARGET_KEYS},
            },
            "tfPayload": {
                "line": tf["line"],
                "serializedSha256": tf["serializedSha256"],
                "serializedLen": tf["serializedLen"],
                "pc": tf["pc"],
                "qi": tf["qi"],
                "activityTypes": tf["activityTypes"],
            },
        },
        "constructorSpec": {
            "formSources": form_sources,
            "px561TargetSources": target_sources,
            "activityTemplateBoundary": {
                "status": "success activity array is byte-rebuildable but most non-tail fields are still observed artifacts",
                "activityTypes": tf["activityTypes"],
                "pxFieldCount": len(tf_px_d),
                "unclosedScope": "non-tail fingerprint, DOM, timing, mouse/pointer and session-dependent fields still need pure protocol generation or a live-accepted minimal subset proof",
            },
        },
        "checks": checks,
        "remainingGaps": [
            "Generate session params uuid/tag/ft/seq/cs/sid/vid/cts/rsc from live protocol state instead of copying an observed browser run.",
            "Prove AEAxBkUsPjQ= generated by offline Ws.Ng is accepted when paired with same-session state.",
            "Define and live-test Bzt2fUFRcw== timing policy for the pure-protocol solver; observed Bzt is compatible with browser worker perf timing, not with the faster offline solver elapsed.",
            "Construct or minimize non-tail PX561 activities without browser-derived mouse/DOM/fingerprint artifacts, then verify collector returns oIIoIooo|0.",
            "After collector success, replay decoded _px jar through risk/verify and CreateAccount without browser.",
        ],
        "conclusion": (
            "Line 933 is now a concrete constructor target: the encoding layer, pc, marker, OSk and TBR9 sources are proved, and AEAx/Bzt producers are bounded by runtime evidence. "
            "The remaining gap is not body encoding; it is live same-session generation/acceptance of session state, AEAx/Bzt policy, and non-tail PX561 activity material without browser artifacts."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "s00_success_constructor_spec_audit.json"
    out_md = OUT_DIR / "s00_success_constructor_spec_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# s00 success constructor spec audit",
        "",
        "## Checks",
        "",
        *[f"- {k}: `{v}`" for k, v in checks.items()],
        "",
        "## PX561 target source status",
        "",
        "| key | status | value shape |",
        "|---|---|---|",
    ]
    for key in TARGET_KEYS:
        src = target_sources[key]
        lines.append(f"| `{key}` | `{src['status']}` | `{json.dumps(shape(src.get('value')), ensure_ascii=False)}` |")
    lines += ["", "## Remaining gaps", "", *[f"- {gap}" for gap in result["remainingGaps"]], "", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
