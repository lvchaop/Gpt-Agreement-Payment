#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def runtime_path_for(js_trace: Path) -> Path | None:
    name = js_trace.name
    if not name.startswith("js_internal_trace_"):
        return None
    candidate = js_trace.with_name(name.replace("js_internal_trace_", "runtime_trace_", 1))
    return candidate if candidate.exists() else None


def short_stack(stack: str | None) -> list[str]:
    if not stack:
        return []
    return [x for x in stack.splitlines() if x][:12]


def parse_message_payload(data: dict[str, Any]) -> Any:
    payload = data.get("data")
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return payload
    return payload


def find_full_chain(js_trace: Path) -> Path | None:
    base = js_trace.name.removesuffix(".jsonl").removeprefix("js_internal_trace_")
    candidate = REPO / "output/outlook_browser/js_static_analysis/full_chain" / f"full_chain_{base}.json"
    return candidate if candidate.exists() else None


def classify(js_trace: Path) -> dict[str, Any]:
    rows = read_jsonl(js_trace)
    runtime_path = runtime_path_for(js_trace)
    runtime_rows = read_jsonl(runtime_path) if runtime_path else []
    full_chain_path = find_full_chain(js_trace)
    full_chain = json.loads(full_chain_path.read_text(encoding="utf-8")) if full_chain_path else {}

    decoded_packets: list[dict[str, Any]] = []
    dispatches: list[dict[str, Any]] = []
    ot_events: list[dict[str, Any]] = []
    captcha_events: list[dict[str, Any]] = []
    parent_messages: list[dict[str, Any]] = []
    pow_hits: list[dict[str, Any]] = []
    tf_payloads: list[dict[str, Any]] = []
    cookie_events: list[dict[str, Any]] = []

    for row in rows:
        kind = row.get("kind")
        data = row.get("data") or {}
        if kind == "hsprotect.main.om.decode":
            decoded_packets.append(
                {
                    "line": row["_line"],
                    "parts": data.get("parts") or [],
                    "decoded": data.get("decoded"),
                    "el": data.get("el"),
                    "mod": data.get("mod"),
                }
            )
        elif kind == "hsprotect.main.jl.dispatch":
            dispatches.append(
                {
                    "line": row["_line"],
                    "handlerKey": data.get("handlerKey"),
                    "args": data.get("args") or [],
                    "table": data.get("table"),
                    "stack": short_stack(data.get("stack")),
                }
            )
        elif kind == "hsprotect.captcha.Ot.enter":
            ot_events.append(
                {
                    "line": row["_line"],
                    "r": data.get("r"),
                    "state": data.get("state"),
                    "n": data.get("n"),
                    "t": data.get("t"),
                    "v_len": len(str(data.get("v") or "")),
                    "stack": short_stack(data.get("stack")),
                }
            )
        elif kind == "hsprotect.Xn.trigger" and data.get("channel") == "captcha":
            captcha_events.append({"line": row["_line"], "args": data.get("args") or [], "stack": short_stack(data.get("stack"))})
        elif kind == "window.message.recv":
            msg = parse_message_payload(data)
            if isinstance(msg, dict) and msg.get("type"):
                parent_messages.append({"line": row["_line"], "eventOrigin": data.get("eventOrigin"), "data": msg})
        elif kind in {"hsprotect.captcha.pow.hit", "worker.message.recv"}:
            if "pow" in kind or "value" in data:
                pow_hits.append({"line": row["_line"], "kind": kind, "data": data})
        elif kind == "hsprotect.main.tf.payload":
            meta = data.get("meta") or {}
            tf_payloads.append(
                {
                    "line": row["_line"],
                    "activity_count": len(data.get("activities") or []),
                    "activity_types": [x.get("t") for x in (data.get("activities") or [])[:10] if isinstance(x, dict)],
                    "meta": meta,
                    "pc": data.get("pc"),
                    "payload_len": len(str(data.get("payload") or "")),
                    "serialized_len": len(str(data.get("serialized") or "")),
                    "stack": short_stack(data.get("stack")),
                }
            )
        elif "cookie" in str(kind).lower():
            cookie_events.append({"line": row["_line"], "kind": kind, "data": data})

    runtime_hits: list[dict[str, Any]] = []
    for row in runtime_rows:
        url = str(row.get("url") or "")
        body = str(row.get("body") or row.get("response_body") or "")
        post_data = str(row.get("post_data") or "")
        if any(x in url for x in ("risk/verify", "API/CreateAccount", "api/v2/msft", "beacon")):
            runtime_hits.append(
                {
                    "line": row["_line"],
                    "kind": row.get("kind"),
                    "method": row.get("method"),
                    "status": row.get("status"),
                    "url": url,
                    "post_len": len(post_data),
                    "body_len": len(body),
                    "state_continue": '"state":"continue"' in body or '"state": "continue"' in body,
                    "redirect_url": "redirectUrl" in body,
                    "error_1059": '"code":"1059"' in body or '"code": "1059"' in body,
                    "body_excerpt": body[:1000],
                }
            )

    all_parts = [part for pkt in decoded_packets for part in pkt["parts"]]
    has_success_handler = any(part == "oIIoIooo|0" or part.startswith("oIIoIooo|0|") for part in all_parts)
    has_success_dispatch = any(d["handlerKey"] == "oIIoIooo" and (d["args"] or [None])[0] == "0" for d in dispatches)
    has_ot_success = any(ev.get("r") == 0 or ev.get("state") == "succeeded" for ev in ot_events)
    has_captcha_succeeded = any(any("succeeded" in str(x) for x in ev["args"]) for ev in captcha_events)
    has_parent_succeeded = any((ev["data"] or {}).get("type") == "succeeded" for ev in parent_messages)
    has_parent_block = any((ev["data"] or {}).get("type") == "block" for ev in parent_messages)
    risk_continue = any(hit["state_continue"] and "risk/verify" in hit["url"] for hit in runtime_hits)
    create_redirect = any(hit["redirect_url"] and "CreateAccount" in hit["url"] for hit in runtime_hits)
    create_1059 = any(hit["error_1059"] and "CreateAccount" in hit["url"] for hit in runtime_hits)

    final_success = all([has_success_handler or has_success_dispatch, has_ot_success, has_parent_succeeded, risk_continue, create_redirect])
    status = "success" if final_success else "failure"
    if not final_success and (has_parent_block or create_1059):
        status = "failure"
    if status == "failure" and any([has_success_handler, has_success_dispatch, has_ot_success, has_parent_succeeded, risk_continue, create_redirect]):
        status = "partial"

    missing = []
    checks = {
        "decoded_oIIoIooo_0": has_success_handler,
        "dispatch_oIIoIooo_0": has_success_dispatch,
        "ot_succeeded": has_ot_success,
        "captcha_succeeded_event": has_captcha_succeeded,
        "parent_postmessage_succeeded": has_parent_succeeded,
        "risk_verify_state_continue": risk_continue,
        "create_account_redirectUrl": create_redirect,
    }
    for key, ok in checks.items():
        if not ok:
            missing.append(key)

    return {
        "trace": str(js_trace),
        "runtime_trace": str(runtime_path) if runtime_path else None,
        "full_chain": str(full_chain_path) if full_chain_path else None,
        "status": status,
        "checks": checks,
        "missing": missing,
        "counts": {
            "decoded_packets": len(decoded_packets),
            "dispatches": len(dispatches),
            "ot_events": len(ot_events),
            "captcha_events": len(captcha_events),
            "parent_messages": len(parent_messages),
            "pow_hits": len(pow_hits),
            "tf_payloads": len(tf_payloads),
            "runtime_hits": len(runtime_hits),
            "full_chain_ot_events": len(full_chain.get("otEvents") or []),
            "full_chain_tf_payload_events": len(full_chain.get("tfPayloadEvents") or []),
        },
        "evidence": {
            "success_handler_parts": [part for part in all_parts if part.startswith("oIIoIooo")],
            "dispatch_oIIoIooo": [d for d in dispatches if d["handlerKey"] == "oIIoIooo"],
            "ot_events": ot_events,
            "captcha_events": captcha_events,
            "parent_messages": parent_messages,
            "pow_hits": pow_hits[:20],
            "tf_payloads": tf_payloads,
            "runtime_hits": runtime_hits,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify HUMAN/HSProtect Outlook challenge traces.")
    parser.add_argument("traces", nargs="+", type=Path)
    parser.add_argument("--out-dir", type=Path, default=REPO / "output/protocol_reverse")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for trace in args.traces:
        result = classify(trace)
        base = trace.name.removesuffix(".jsonl").removeprefix("js_internal_trace_")
        out = args.out_dir / f"trace_classification_{base}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        summaries.append({"trace": str(trace), "out": str(out), "status": result["status"], "missing": result["missing"]})

    summary_path = args.out_dir / "trace_classification_summary.json"
    summary_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
