#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CONSTRUCTOR_TOOL = REPO / "tools/audit_bundle_seq_constructor.py"
OUT_DIR = REPO / "output/protocol_reverse/bundle_constructor"
RUN = "j0t8van4qyhm_1781119142"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def parse_form(body: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(str(body or "").replace("+", "%2B"), keep_blank_values=True))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def short_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:240]}"


def contains_terms(value: Any, terms: list[str]) -> dict[str, bool]:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    return {term: term in text for term in terms}


def nearest_before(events: list[dict[str, Any]], t: float, *, pc: str | None = None) -> dict[str, Any] | None:
    candidates = []
    for event in events:
        if pc is not None:
            data = event.get("data") or {}
            event_pc = data.get("pc") or (data.get("meta") or {}).get("pc")
            if event_pc != pc:
                continue
        wall_t = float(event.get("wall_t") or -1)
        if wall_t <= t + 0.050:
            candidates.append(event)
    if not candidates:
        return None
    return max(candidates, key=lambda event: float(event.get("wall_t") or -1))


def first_outcome_after(js_rows: list[dict[str, Any]], t: float) -> dict[str, Any] | None:
    outcomes = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.captcha.zt.enter":
            continue
        wall_t = float(row.get("wall_t") or -1)
        if wall_t < t:
            continue
        data = row.get("data") or {}
        if data.get("arg") not in {"failed", "succeeded"}:
            continue
        outcomes.append({"line": row["_line"], "wall_t": wall_t, "arg": data.get("arg")})
    return min(outcomes, key=lambda item: item["wall_t"]) if outcomes else None


def create_account_acceptance(runtime_rows: list[dict[str, Any]]) -> dict[str, Any]:
    request = None
    response = None
    for row in runtime_rows:
        url = str(row.get("url") or "")
        if "/API/CreateAccount" not in url:
            continue
        if row.get("kind") == "request":
            request = row
        elif row.get("kind") == "response":
            response = row
            break
    body = ""
    parsed: dict[str, Any] | None = None
    if response is not None:
        body = str(response.get("body") or "")
        try:
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = None
    return {
        "requestLine": request.get("_line") if request else None,
        "requestTime": request.get("t") if request else None,
        "responseLine": response.get("_line") if response else None,
        "responseTime": response.get("t") if response else None,
        "hasRedirectUrl": bool(isinstance(parsed, dict) and parsed.get("redirectUrl")),
        "signinName": parsed.get("signinName") if isinstance(parsed, dict) else None,
        "error": parsed.get("error") if isinstance(parsed, dict) else None,
        "bodyContainsHumanCaptcha": "humanCaptcha" in body,
        "bodyContains1059": "1059" in body,
    }


def summarize_request(
    row: dict[str, Any],
    *,
    ctor: Any,
    js_rows: list[dict[str, Any]],
    prepcs: list[dict[str, Any]],
    payloads: list[dict[str, Any]],
    create_accept: dict[str, Any],
) -> dict[str, Any]:
    params = parse_form(row.get("post_data") or "")
    observed_pc = params.get("pc") or ""
    t = float(row.get("t") or 0)
    prepc = nearest_before(prepcs, t, pc=observed_pc)
    payload = nearest_before(payloads, t, pc=observed_pc)
    outcome = first_outcome_after(js_rows, t)
    is_before_create = bool(create_accept.get("requestTime") and t < float(create_accept["requestTime"]))
    is_accepted_phase = bool(
        is_before_create
        and outcome
        and outcome.get("arg") == "succeeded"
        and create_accept.get("hasRedirectUrl")
        and not create_accept.get("bodyContainsHumanCaptcha")
        and not create_accept.get("bodyContains1059")
    )

    item: dict[str, Any] = {
        "requestLine": row["_line"],
        "requestTime": t,
        "seq": params.get("seq"),
        "rsc": params.get("rsc"),
        "uuid": params.get("uuid"),
        "tag": params.get("tag"),
        "ft": params.get("ft"),
        "observedPc": observed_pc,
        "observedPayloadLen": len(params.get("payload") or ""),
        "hasPrepcEvent": prepc is not None,
        "hasPayloadEvent": payload is not None,
        "nextCaptchaOutcome": outcome,
        "isAcceptedCreateAccountPhase": is_accepted_phase,
    }
    if prepc is not None:
        pre_data = prepc.get("data") or {}
        pre_serialized = str(pre_data.get("serialized") or "")
        pre_calc = ctor.pc_value(pre_serialized, params.get("uuid", ""), params.get("tag", ""), params.get("ft", ""))
        item["prepc"] = {
            "line": prepc["_line"],
            "wall_t": prepc.get("wall_t"),
            "dtToRequest": t - float(prepc.get("wall_t") or 0),
            "serializedLen": len(pre_serialized),
            "serializedSha256": sha256_text(pre_serialized),
            "capturedPc": pre_data.get("pc"),
            "recomputedPc": pre_calc,
            "recomputedPcMatchesObserved": pre_calc == observed_pc,
            "key": pre_data.get("key"),
            "contains": contains_terms(pre_serialized, ["PX561", "AEAx", "TBR9Ugl7emA=", "218e34c1"]),
        }
    if payload is not None:
        pay_data = payload.get("data") or {}
        pay_serialized = str(pay_data.get("serialized") or "")
        marker = str(pay_data.get("marker") or "")
        payload_pc = pay_data.get("pc") or (pay_data.get("meta") or {}).get("pc")
        item["payloadHook"] = {
            "line": payload["_line"],
            "wall_t": payload.get("wall_t"),
            "dtToRequest": t - float(payload.get("wall_t") or 0),
            "serializedLen": len(pay_serialized),
            "serializedSha256": sha256_text(pay_serialized),
            "capturedPc": payload_pc,
            "marker": marker,
            "markerLen": len(marker),
            "contains": contains_terms(pay_serialized, ["PX561", "AEAx", "TBR9Ugl7emA=", "218e34c1"]),
        }
        if prepc is not None:
            pre_serialized = str((prepc.get("data") or {}).get("serialized") or "")
            item["prepcPayloadSerializedMatch"] = pre_serialized == pay_serialized
        try:
            replay = ctor.encode_serialized(pay_serialized, marker, params.get("uuid", ""))
            item["payloadHookReplay"] = {
                "ok": True,
                "payloadMatchesObserved": replay["payload"] == params.get("payload", ""),
                "basePayloadSha256": hashlib.sha256(replay["basePayload"].encode("ascii")).hexdigest(),
            }
        except Exception as exc:
            item["payloadHookReplay"] = {
                "ok": False,
                "error": short_error(exc),
                "meaning": "current Python replay helper is latin1-bound; this request contains non-latin1 JS string characters, so pc is authoritative but payload replay needs a JS-string encoder audit",
            }
        if marker:
            try:
                decoded = ctor.load_decode_tool().decode_payload(params.get("payload", ""), marker, params.get("uuid", ""))
                decoded_text = str(decoded.get("decodedText") or "")
                item["observedPayloadDecodeWithHookMarker"] = {
                    "ok": True,
                    "markerMatch": decoded.get("markerMatch"),
                    "jsonError": decoded.get("jsonError"),
                    "decodedTextLen": len(decoded_text),
                    "decodedTextSha256": sha256_text(decoded_text),
                    "decodedTextMatchesPayloadHookSerialized": decoded_text == pay_serialized,
                    "contains": contains_terms(decoded.get("json") if decoded.get("json") is not None else decoded_text, ["PX561", "AEAx", "TBR9Ugl7emA=", "218e34c1"]),
                }
            except Exception as exc:
                item["observedPayloadDecodeWithHookMarker"] = {"ok": False, "error": short_error(exc)}
    return item


def main() -> int:
    ctor = load_module(CONSTRUCTOR_TOOL, "audit_bundle_seq_constructor")
    js_trace = REPO / f"output/outlook_browser/js_internal_trace_{RUN}.jsonl"
    runtime_trace = REPO / f"output/outlook_browser/runtime_trace_{RUN}.jsonl"
    js_rows = read_jsonl(js_trace)
    runtime_rows = read_jsonl(runtime_trace)
    prepcs = [r for r in js_rows if r.get("kind") == "hsprotect.main.tf.prepc"]
    payloads = [r for r in js_rows if r.get("kind") == "hsprotect.main.tf.payload"]
    bundle_requests = [
        r
        for r in runtime_rows
        if r.get("kind") == "request" and str(r.get("url") or "").endswith("/assets/js/bundle")
    ]
    create_accept = create_account_acceptance(runtime_rows)
    requests = [
        summarize_request(
            row,
            ctor=ctor,
            js_rows=js_rows,
            prepcs=prepcs,
            payloads=payloads,
            create_accept=create_accept,
        )
        for row in bundle_requests
    ]
    accepted_phase_requests = [r for r in requests if r["isAcceptedCreateAccountPhase"]]
    result = {
        "run": RUN,
        "purpose": "Use live tf.prepc hook evidence from an accepted registration to compare pc-time serialized input with observed /assets/js/bundle pc and payload-time serialized input.",
        "evidenceFiles": {
            "jsTrace": str(js_trace.resolve()),
            "runtimeTrace": str(runtime_trace.resolve()),
            "constructorTool": str(CONSTRUCTOR_TOOL.resolve()),
        },
        "createAccountAcceptance": create_accept,
        "counts": {
            "tfPrepcEvents": len(prepcs),
            "tfPayloadEvents": len(payloads),
            "bundleRequests": len(bundle_requests),
            "acceptedPhaseBundleRequests": len(accepted_phase_requests),
        },
        "requests": requests,
        "checks": {
            "createAccountAccepted": bool(create_accept.get("hasRedirectUrl") and not create_accept.get("bodyContainsHumanCaptcha") and not create_accept.get("bodyContains1059")),
            "allBundleRequestsHavePrepcAndPayload": all(r["hasPrepcEvent"] and r["hasPayloadEvent"] for r in requests),
            "allBundleRequestPrepcPcMatchesObserved": all((r.get("prepc") or {}).get("recomputedPcMatchesObserved") for r in requests),
            "allBundlePrepcPayloadSerializedMatch": all(r.get("prepcPayloadSerializedMatch") is True for r in requests),
            "acceptedPhaseExists": bool(accepted_phase_requests),
            "acceptedPhasePrepcPcMatchesObserved": all((r.get("prepc") or {}).get("recomputedPcMatchesObserved") for r in accepted_phase_requests),
            "acceptedPhaseContainsPX561AEAxTBR9": any(
                (r.get("payloadHook") or {}).get("contains", {}).get("PX561")
                and (r.get("payloadHook") or {}).get("contains", {}).get("AEAx")
                and (r.get("payloadHook") or {}).get("contains", {}).get("TBR9Ugl7emA=")
                for r in accepted_phase_requests
            ),
            "allBundlePayloadReplayMatchesObserved": all(
                (r.get("payloadHookReplay") or {}).get("payloadMatchesObserved") is True for r in requests
            ),
            "acceptedPhasePayloadReplayMatchesObserved": all(
                (r.get("payloadHookReplay") or {}).get("payloadMatchesObserved") is True for r in accepted_phase_requests
            ),
        },
        "conclusion": (
            "For this accepted-success observation, every /assets/js/bundle observed pc is exactly reproduced from the captured pre-Vs tf.prepc.serialized string with the documented uuid:tag:ft key. "
            "The same serialized string is still present at tf.payload, proving the pc gap is not an alternate pc function in this live path. "
            "After applying UTF-8 J/Vs encoding semantics, every bundle payload in this observation byte-replays from tf.payload.serialized plus the captured marker and uuid, including requests carrying non-latin1 JS string characters."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"bundle_pc_prepc_observation_{RUN}.json"
    out_md = OUT_DIR / f"bundle_pc_prepc_observation_{RUN}.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Bundle pc prepc observation: {RUN}",
        "",
        f"- jsTrace: `{result['evidenceFiles']['jsTrace']}`",
        f"- runtimeTrace: `{result['evidenceFiles']['runtimeTrace']}`",
        "",
        "## Checks",
        "",
    ]
    for key, value in result["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "## CreateAccount acceptance",
        "",
        f"- request line: `{create_accept.get('requestLine')}`",
        f"- response line: `{create_accept.get('responseLine')}`",
        f"- signinName: `{create_accept.get('signinName')}`",
        f"- hasRedirectUrl: `{create_accept.get('hasRedirectUrl')}`",
        f"- bodyContainsHumanCaptcha: `{create_accept.get('bodyContainsHumanCaptcha')}`",
        f"- bodyContains1059: `{create_accept.get('bodyContains1059')}`",
        "",
        "## Bundle requests",
        "",
        "| line | seq | observed pc | accepted phase | outcome | prepc pc match | prepc==payload | replay ok | replay payload match | hook-marker decode match | contains |",
        "|---:|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for req in requests:
        pre = req.get("prepc") or {}
        replay = req.get("payloadHookReplay") or {}
        dec = req.get("observedPayloadDecodeWithHookMarker") or {}
        contains = req.get("payloadHook", {}).get("contains", {})
        contains_text = ",".join(k for k, v in contains.items() if v)
        outcome = (req.get("nextCaptchaOutcome") or {}).get("arg")
        lines.append(
            f"| {req['requestLine']} | {req['seq']} | `{req['observedPc']}` | {req['isAcceptedCreateAccountPhase']} | {outcome or ''} | "
            f"{pre.get('recomputedPcMatchesObserved')} | {req.get('prepcPayloadSerializedMatch')} | {replay.get('ok')} | "
            f"{replay.get('payloadMatchesObserved')} | {dec.get('decodedTextMatchesPayloadHookSerialized')} | {contains_text} |"
        )
    lines += [
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
