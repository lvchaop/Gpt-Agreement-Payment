#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BOOTSTRAP_TOOL = REPO / "tools/probe_human_fresh_bootstrap.py"
LIVE_PROBE = REPO / "tools/probe_human_collector_live.py"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
FRESH_BUNDLE = REPO / "output/protocol_reverse/fresh_bundle_probe/fresh_bundle_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781198172.json"
FRESH_POW = REPO / "output/protocol_reverse/pow_response/pow_response_fresh_bundle_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781198172.json"
FRESH_NQ = REPO / "output/protocol_reverse/wasm/compute_wasm_nq_once_fresh_bundle_d2eae322_1781198172.json"
FRESH_NG_NQ = REPO / "output/protocol_reverse/wasm/compute_wasm_nq_once_fresh_bundle_d2eae322_1781198172_with_ng.json"
OUT_DIR = REPO / "output/protocol_reverse/fresh_px561_probe"

OLD = {
    "uuid": "7bbba710-65a9-11f1-bc5b-d972b0447135",
    "p1": "ac9e68ae-7803-6e7d-a972-775cf9afdf80",
    "vid": "7cefb5a4-65a9-11f1-94dc-0f9258987c3d",
    "cts": "7cefbdd9-65a9-11f1-94dd-04d8ba8dbf5b",
    "cs": "f21dd0d7dffe52acbd3f2b5a54c85f72049f9064aea8ada9d215cd7fdf37bc3d",
    "ci": "911cacd0-65a9-11f1-b9e4-f30710b600a5",
    "ci_success": "b06407a0-65a9-11f1-a5f4-a312f8704e8f",
    "sid_success": "7cefbbda-65a9-11f1-94dd-04d8ba8dbf5b",
    "jo": "1781191438365",
    "jo_success": "1781191490842",
}


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
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def kl(value: str | None) -> str:
    if not value:
        return ""
    return "".join(chr(0xE0100 + ord(ch)) for ch in str(value))


def template_activities(line_no: int) -> list[dict[str, Any]]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == line_no:
            return json.loads(json.dumps((row.get("data") or {}).get("activities") or []))
    raise KeyError(f"js trace line {line_no}")


def runtime_request(line_no: int) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME_TRACE):
        if int(row.get("_line") or 0) == line_no:
            return row
    raise KeyError(f"runtime line {line_no}")


def parse_form_body(body: str) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(body, keep_blank_values=True))


def replace_strings(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        out = value
        for old, new in replacements.items():
            out = out.replace(old, new)
        return out
    if isinstance(value, list):
        return [replace_strings(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: replace_strings(child, replacements) for key, child in value.items()}
    return value


def decoded_fresh_state(bundle: dict[str, Any]) -> dict[str, Any]:
    base = dict((bundle.get("material") or {}).get("freshState") or {})
    parts = (bundle.get("decoded") or {}).get("parts") or []
    for part in parts:
        fields = str(part).split("|")
        if fields[:2] == ["IoooII", "_px3"]:
            base["px3"] = fields[3]
        elif fields and fields[0] == "IIoIoI":
            base["zo"] = fields[1]
        elif fields and fields[0] == "oIIoIoII":
            base["jo"] = fields[1]
        elif fields and fields[0] == "ooooII":
            base["qo"] = fields[1]
        elif fields and fields[0] == "oIIoIoIo":
            base["gl"] = fields[1]
        elif fields and fields[0] == "IooIoI":
            base["ci"] = fields[2]
        elif fields[:2] == ["oIIoIIoo", "_pxde"]:
            base["pxde"] = fields[3]
    return base


def progression_state(doc: dict[str, Any]) -> dict[str, Any]:
    state = dict(doc.get("finalState") or {})
    if not state:
        raise RuntimeError("progression state doc lacks finalState")
    return state


def first_pow(pow_doc: dict[str, Any]) -> dict[str, Any]:
    for row in pow_doc.get("results") or []:
        if row.get("matchesTarget") is True and row.get("value"):
            return row
    raise RuntimeError("no solved POW")


def px_activity(activities: list[dict[str, Any]]) -> dict[str, Any]:
    for activity in activities:
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return activity
    raise RuntimeError("PX561 activity not found")


def build_material(
    *,
    send: bool,
    include_proxy_authorization: bool,
    header_mode: str,
    aeax_source: str,
    bzt_source: str,
    bzt_value: str | None,
    template_line: int,
    runtime_line: int,
    seq: str,
    rsc: str,
    state_probe: Path | None,
    fresh_bundle: Path | None,
    pow_json: Path,
    nq_json: Path,
    ng_nq_json: Path,
    stack_source: str,
    tail_source: str,
    inner_uuid_source: str,
    non_px_activity_source: str,
    payload_uuid_source: str,
    pc_uuid_source: str,
    marker_source: str,
    form_outer_source: str,
    payload_source: str = "built",
    pc_source: str = "computed",
    body_source: str = "built",
) -> dict[str, Any]:
    boot = load_module(BOOTSTRAP_TOOL, "probe_human_fresh_bootstrap")
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    state_doc = read_json(state_probe) if state_probe else read_json(fresh_bundle or FRESH_BUNDLE)
    state = progression_state(state_doc) if state_probe else decoded_fresh_state(state_doc)
    pow_row = first_pow(read_json(pow_json))
    nq = read_json(nq_json)
    nq_value = nq["output"]["nqValue"]
    ng_nq = read_json(ng_nq_json) if ng_nq_json.exists() else None
    ng_value = ((ng_nq or {}).get("output") or {}).get("ngValue")

    original_activities = template_activities(template_line)
    original_px_stack = (px_activity(original_activities).get("d") or {}).get("W0shQR0nJHc=")
    if non_px_activity_source == "fresh":
        activities = replace_strings(
            original_activities,
            {
                OLD["uuid"]: state["uuid"],
                OLD["p1"]: state["p1"],
                OLD["vid"]: state["vid"],
                OLD["cts"]: state["cts"],
                OLD["cs"]: state["cs"],
                OLD["ci"]: state["ci"],
                OLD["ci_success"]: state["ci"],
                OLD["jo"]: str(state["jo"]),
                OLD["jo_success"]: str(state["jo"]),
            },
        )
        first = activities[0]["d"]
        if "cR1LFzd8RSQ=" in first:
            first["cR1LFzd8RSQ="] = int(state["jo"])
        if "eEQCDj4mDz0=" in first:
            first["eEQCDj4mDz0="] = str(state["zo"])
        if "JxcdHWJzESc=" in first:
            first["JxcdHWJzESc="] = str(state["qo"])
        if "JnZcfGMXVEo=" in first:
            first["JnZcfGMXVEo="] = int(state["gl"])
        first["SlpwEAw5eSc="] = f"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id={state['p1']}&ch_ctx=1"
        first["FUFvS1Mga38="] = state["uuid"]
        first["GUVjT1wnbn4="] = state["px3"]
        now_ms = int(time.time() * 1000)
        first["QS07ZwRKPlU="] = now_ms
        if "IU0bR2crHnA=" in first:
            first["IU0bR2crHnA="] = now_ms - 20
    elif non_px_activity_source == "template":
        activities = json.loads(json.dumps(original_activities))
    else:
        raise RuntimeError(f"unsupported non-PX activity source: {non_px_activity_source}")

    px = px_activity(activities)
    px_d = px["d"]
    original_px_d = px_activity(original_activities).get("d") or {}
    if stack_source == "template" and original_px_stack is not None:
        px_d["W0shQR0nJHc="] = original_px_stack
    elif stack_source != "fresh":
        raise RuntimeError(f"unsupported stack source: {stack_source}")
    if inner_uuid_source == "template" and original_px_d.get("FUFvS1Mga38=") is not None:
        px_d["FUFvS1Mga38="] = original_px_d["FUFvS1Mga38="]
    elif inner_uuid_source != "fresh":
        raise RuntimeError(f"unsupported inner uuid source: {inner_uuid_source}")
    old_tail = {k: px_d.get(k) for k in ["OSkIb39DDA==", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "AEAxBkUsPjQ=", "fyNOZTpPQF4="]}
    if tail_source == "fresh":
        px_d["OSkIb39DDA=="] = pow_row["value"]
        px_d["TBR9Ugl7emA="] = nq_value
    elif tail_source != "template":
        raise RuntimeError(f"unsupported tail source: {tail_source}")
    if bzt_source == "solve":
        px_d["Bzt2fUFRcw=="] = int(pow_row.get("solveElapsedMs") or 0)
    elif bzt_source == "template":
        px_d["Bzt2fUFRcw=="] = old_tail["Bzt2fUFRcw=="]
    elif bzt_source == "value":
        if bzt_value is None:
            raise RuntimeError("--bzt-source value requires --bzt-value")
        px_d["Bzt2fUFRcw=="] = int(bzt_value)
    else:
        raise RuntimeError(f"unsupported bzt source: {bzt_source}")
    if aeax_source == "offline-ng":
        if not ng_value:
            raise RuntimeError(f"offline Ng value missing: {FRESH_NG_NQ}")
        px_d["AEAxBkUsPjQ="] = ng_value

    template_outer = {
        "uuid": OLD["uuid"],
        "p1": OLD["p1"],
        "vid": OLD["vid"],
        "cts": OLD["cts"],
        "cs": OLD["cs"],
        "ci": OLD["ci_success"],
        "sid": OLD["sid_success"],
        "jo": OLD["jo_success"],
    }
    if payload_uuid_source == "fresh":
        payload_uuid = state["uuid"]
    elif payload_uuid_source == "template":
        payload_uuid = template_outer["uuid"]
    else:
        raise RuntimeError(f"unsupported payload uuid source: {payload_uuid_source}")
    if pc_uuid_source == "payload":
        pc_uuid = payload_uuid
    elif pc_uuid_source == "fresh":
        pc_uuid = state["uuid"]
    elif pc_uuid_source == "template":
        pc_uuid = template_outer["uuid"]
    else:
        raise RuntimeError(f"unsupported pc uuid source: {pc_uuid_source}")
    if marker_source == "fresh":
        marker_jo = str(state["jo"])
    elif marker_source == "template":
        marker_jo = str(template_outer["jo"])
    else:
        raise RuntimeError(f"unsupported marker source: {marker_source}")
    if form_outer_source == "fresh":
        form_state = state
    elif form_outer_source == "template":
        form_state = template_outer
    else:
        raise RuntimeError(f"unsupported form outer source: {form_outer_source}")
    runtime = runtime_request(runtime_line)
    template_body = str(runtime.get("post_data") or "")
    template_form = parse_form_body(template_body)
    marker = boot.marker_from_qi(marker_jo)
    payload, serialized = boot.encode_payload(activities, payload_uuid, marker)
    built_payload = payload
    if payload_source == "template-exact":
        payload = template_form["payload"]
    elif payload_source != "built":
        raise RuntimeError(f"unsupported payload source: {payload_source}")
    pc = boot.pc_value(serialized, pc_uuid, "YjIYfyxJHRR9", "369")
    computed_pc = pc
    if pc_source == "template-exact":
        pc = template_form["pc"]
    elif pc_source != "computed":
        raise RuntimeError(f"unsupported pc source: {pc_source}")
    if body_source == "template-exact":
        body = template_body
    elif body_source == "built":
        body = boot.form_encode(
            [
                ("payload", payload),
                ("appId", "PXzC5j78di"),
                ("tag", "YjIYfyxJHRR9"),
                ("uuid", form_state["uuid"]),
                ("ft", "369"),
                ("seq", seq),
                ("en", "NTA"),
                ("cs", form_state["cs"]),
                ("pc", pc),
                ("sid", form_state["sid"] + kl(str(form_state["jo"]))),
                ("p1", form_state["p1"]),
                ("vid", form_state["vid"]),
                ("ci", form_state["ci"]),
                ("cts", form_state["cts"]),
                ("rsc", rsc),
            ]
        )
    else:
        raise RuntimeError(f"unsupported body source: {body_source}")
    headers = live.headers_from_runtime(
        runtime,
        body=body,
        url=str(runtime.get("url") or ""),
        include_proxy_authorization=include_proxy_authorization,
        header_mode=header_mode,
    )
    return {
        "url": runtime["url"],
        "headers": headers,
        "body": body,
        "bodySha256": hashlib.sha256(body.encode()).hexdigest(),
        "bodyLenBytes": len(body.encode()),
        "freshState": state,
        "meta": {
            "templateJsTraceLine": template_line,
            "templateRuntimeRequestLine": runtime_line,
            "seq": seq,
            "rsc": rsc,
            "marker": marker,
            "markerJo": marker_jo,
            "payloadUuid": payload_uuid,
            "pcUuid": pc_uuid,
            "formOuterSource": form_outer_source,
            "pc": pc,
            "oldPxTail": old_tail,
            "newPxTail": {k: px_d.get(k) for k in old_tail},
            "stateSource": str(state_probe or fresh_bundle or FRESH_BUNDLE),
            "nqSource": str(nq_json),
            "aeaxSource": aeax_source,
            "bztSource": bzt_source,
            "bztValueArg": bzt_value,
            "stackSource": stack_source,
            "tailSource": tail_source,
            "innerUuidSource": inner_uuid_source,
            "nonPxActivitySource": non_px_activity_source,
            "payloadUuidSource": payload_uuid_source,
            "pcUuidSource": pc_uuid_source,
            "payloadSource": payload_source,
            "pcSource": pc_source,
            "bodySource": body_source,
            "markerSource": marker_source,
            "builtPayloadSha256": hashlib.sha256(built_payload.encode()).hexdigest(),
            "actualPayloadSha256": hashlib.sha256(payload.encode()).hexdigest(),
            "templatePayloadSha256": hashlib.sha256(template_form["payload"].encode()).hexdigest(),
            "computedPc": computed_pc,
            "templatePc": template_form["pc"],
            "ngSource": str(ng_nq_json) if aeax_source == "offline-ng" else None,
            "powSource": str(pow_json),
            "boundary": "PX561 OSk/TBR9 and known session fields are fresh; when aeax_source=offline-ng AEAx is fresh offline Ws.Ng, otherwise AEAx/Ew9i/KVk and behavior arrays remain copied from observed s00 line566 template. Bzt source is controlled independently for single-variable probes.",
        },
        "checks": {
            "hasFreshOsk": pow_row["value"] in serialized,
            "hasFreshTbr9": nq_value in serialized,
            "builtSerializedHasFreshUuid": state["uuid"] in serialized and OLD["uuid"] not in serialized,
            "builtSerializedHasFreshP1": state["p1"] in serialized and OLD["p1"] not in serialized,
            "hasFreshUuid": state["uuid"] in body and OLD["uuid"] not in body,
            "hasFreshP1": state["p1"] in body and OLD["p1"] not in body,
            "hasFreshCi": state["ci"] in body and OLD["ci"] not in body,
            "hasFreshCs": state["cs"] in body and OLD["cs"] not in body,
            "payloadDoesNotLeakFreshTbr9Plaintext": nq_value not in payload,
            "payloadSource": payload_source,
            "pcSource": pc_source,
            "bodySource": body_source,
            "payloadEqualsTemplate": payload == template_form["payload"],
            "pcEqualsTemplate": pc == template_form["pc"],
            "bodyEqualsTemplate": body == template_body,
            "aeaxSourceOfflineNg": aeax_source == "offline-ng",
            "hasOfflineNgAeax": aeax_source == "offline-ng" and bool(ng_value) and ng_value in serialized,
            "bztSource": bzt_source,
            "stackSource": stack_source,
            "tailSource": tail_source,
            "innerUuidSource": inner_uuid_source,
            "nonPxActivitySource": non_px_activity_source,
            "payloadUuidSource": payload_uuid_source,
            "pcUuidSource": pc_uuid_source,
            "markerSource": marker_source,
            "formOuterSource": form_outer_source,
            "templateLine": template_line,
            "runtimeLine": runtime_line,
            "sendRequested": send,
            "headerMode": header_mode,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build/send a fresh-state PX561 bundle request from s00 PX561 templates.")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--include-proxy-authorization", action="store_true")
    parser.add_argument("--header-mode", choices=["safe", "runtime-exact"], default="safe")
    parser.add_argument("--aeax-source", choices=["template", "offline-ng"], default="template")
    parser.add_argument("--bzt-source", choices=["solve", "template", "value"], default="solve")
    parser.add_argument("--bzt-value", default=None)
    parser.add_argument("--template-line", type=int, choices=[566, 922], default=566)
    parser.add_argument("--seq", default="2")
    parser.add_argument("--rsc", default="3")
    parser.add_argument("--state-probe", type=Path, default=None)
    parser.add_argument("--fresh-bundle", type=Path, default=None)
    parser.add_argument("--pow-json", type=Path, default=FRESH_POW)
    parser.add_argument("--nq-json", type=Path, default=FRESH_NQ)
    parser.add_argument("--ng-nq-json", type=Path, default=FRESH_NG_NQ)
    parser.add_argument("--stack-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--tail-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--inner-uuid-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--non-px-activity-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--payload-uuid-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--pc-uuid-source", choices=["payload", "fresh", "template"], default="payload")
    parser.add_argument("--marker-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--form-outer-source", choices=["fresh", "template"], default="fresh")
    parser.add_argument("--payload-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--pc-source", choices=["computed", "template-exact"], default="computed")
    parser.add_argument("--body-source", choices=["built", "template-exact"], default="built")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    live = load_module(LIVE_PROBE, "probe_human_collector_live")
    started = time.time()
    material = build_material(
        send=args.send,
        include_proxy_authorization=args.include_proxy_authorization,
        header_mode=args.header_mode,
        aeax_source=args.aeax_source,
        bzt_source=args.bzt_source,
        bzt_value=args.bzt_value,
        template_line=args.template_line,
        runtime_line=933 if args.template_line == 922 else 574,
        seq=args.seq,
        rsc=args.rsc,
        state_probe=args.state_probe,
        fresh_bundle=args.fresh_bundle,
        pow_json=args.pow_json,
        nq_json=args.nq_json,
        ng_nq_json=args.ng_nq_json,
        stack_source=args.stack_source,
        tail_source=args.tail_source,
        inner_uuid_source=args.inner_uuid_source,
        non_px_activity_source=args.non_px_activity_source,
        payload_uuid_source=args.payload_uuid_source,
        pc_uuid_source=args.pc_uuid_source,
        marker_source=args.marker_source,
        form_outer_source=args.form_outer_source,
        payload_source=args.payload_source,
        pc_source=args.pc_source,
        body_source=args.body_source,
    )
    result: dict[str, Any] = {"startedAt": started, "sent": bool(args.send), "material": material}
    if args.send:
        try:
            response = live.send_https(material["url"], material["headers"], material["body"], args.timeout)
            result["response"] = response
            result["decoded"] = live.decode_collector_response(response.get("bodyText") or "", "YjIYfyxJHRR9")
        except Exception as exc:
            result["error"] = str(exc)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"fresh_px561_probe_{material['freshState']['uuid']}_{int(started)}"
    out = args.out_dir / f"{stem}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "sent": result["sent"],
        "status": (result.get("response") or {}).get("status"),
        "handlers": (result.get("decoded") or {}).get("handlers"),
        "hasSuccessHandler": (result.get("decoded") or {}).get("hasSuccessHandler"),
        "hasPowResult": (result.get("decoded") or {}).get("hasPowResult"),
        "checks": material["checks"],
        "error": result.get("error"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
