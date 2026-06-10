#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl"
BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
MAIN = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"
OUT_JSON = OUT_DIR / "tbr9_success_boundary_audit.json"
OUT_MD = OUT_DIR / "tbr9_success_boundary_audit.md"

TARGET_KEYS = [
    "bHQdcikYH0Q=",
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "XQUsAxhpKjU=",
    "Ew9iCVZjYDw=",
    "XGRtYhkLbFM=",
]

LITERAL_NEEDLES = [
    "TBR9Ugl7emA=",
    "Y@tvUUF@W",
    "A3QrSTsPOGBTFDFT",
    "FnM4CCwDASRmEyFT",
    "JEMaEwsNMDJS",
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path):
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_line"] = line_no
        rows.append(row)
    return rows


def numbered_lines(path: Path, start: int, end: int):
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        {"line": idx, "text": lines[idx - 1]}
        for idx in range(start, end + 1)
        if 1 <= idx <= len(lines)
    ]


def find_success_px561(bundle: dict):
    for req in bundle.get("requests", []):
        if req.get("requestLine") != 308:
            continue
        for item in req.get("activitiesWithMatches", []):
            activity = item.get("activity") or {}
            if activity.get("t") == "PX561":
                return req, item, activity.get("d") or {}
    raise RuntimeError("success request 308 PX561 activity not found")


def compact_event(row: dict):
    data = row.get("data") or {}
    out = {
        "line": row.get("_line"),
        "kind": row.get("kind"),
        "wall_t": row.get("wall_t"),
        "perf_t": row.get("perf_t"),
        "channel": data.get("channel"),
        "stack": data.get("stack"),
    }
    for key in ("n", "len", "items", "queue", "index", "raw", "handlerKey", "args", "handlerType"):
        if key in data:
            out[key] = data[key]
    if row.get("kind") == "hsprotect.main.om.decode":
        out["decodedParts"] = data.get("parts")
    return out


def source_literal_counts():
    result = {}
    for path in [MAIN, CAPTCHA]:
        text = path.read_text(encoding="utf-8", errors="replace")
        result[str(path.relative_to(REPO))] = {needle: text.count(needle) for needle in LITERAL_NEEDLES}
    return result


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle = read_json(BUNDLE)
    req, item, px561 = find_success_px561(bundle)
    keys = list(px561)
    key_context = {}
    for key in TARGET_KEYS:
        idx = keys.index(key) if key in px561 else None
        key_context[key] = {
            "present": key in px561,
            "index": idx,
            "value": px561.get(key),
        }

    rows = read_jsonl(JS_TRACE)
    boundary_lines = []
    for row in rows:
        line = row["_line"]
        kind = row.get("kind")
        data = row.get("data") or {}
        if 301 <= line <= 329 and (
            kind in {
                "hsprotect.Xn.trigger",
                "hsprotect.main.om.decode",
                "hsprotect.main.jl.enter",
                "hsprotect.main.jl.item",
                "hsprotect.main.jl.queue",
                "hsprotect.main.jl.dispatch",
                "hsprotect.captcha.Ot.enter",
                "hsprotect.captcha.zt.enter",
            }
        ):
            boundary_lines.append(compact_event(row))

    decoded_success = None
    for event in boundary_lines:
        if event.get("kind") == "hsprotect.main.om.decode":
            parts = event.get("decodedParts") or []
            decoded_success = {
                "line": event["line"],
                "parts": parts,
                "hasSuccessHandler": "oIIoIooo|0" in parts,
                "hasTbr9Literal": any("TBR9Ugl7emA=" in p or "Y@tvUUF@W" in p for p in parts),
            }

    findings = [
        "Success final PX561.d contains TBR9Ugl7emA= at index 75, after AEAxBkUsPjQ= and before Bzt2fUFRcw==.",
        "captcha.beautified.js direct assignment order is TBR9Ugl7emA= via _s() before AEAxBkUsPjQ= via Ws.Ng(); simple reassignment cannot explain final insertion order.",
        "The success collector response decoded at js trace line 306 contains handler oIIoIooo|0 but does not contain TBR9Ugl7emA= or the long TBR9 value.",
        "Existing runtime boundary after line 301 captures response handlers and captcha succeeded trigger, but not the pre-serialization PX561 object immediately before tf()/Vs().",
        "Therefore current evidence narrows TBR9Ugl7emA= to a final PX561 bundle construction/serialization-stage gap; producer/overwrite remains unclosed.",
    ]

    audit = {
        "inputs": {
            "jsTrace": str(JS_TRACE),
            "bundle": str(BUNDLE),
            "main": str(MAIN),
            "captcha": str(CAPTCHA),
        },
        "successRequest": {
            "requestLine": req.get("requestLine"),
            "seq": req.get("seq"),
            "payloadLen": req.get("payloadLen"),
            "activityIndex": item.get("index"),
            "activityType": item.get("type"),
            "px561KeyCount": len(px561),
        },
        "targetKeyContext": key_context,
        "staticEvidence": {
            "captcha_D_Ts_11073_11099": numbered_lines(CAPTCHA, 11073, 11099),
            "captcha__s_9638_9644": numbered_lines(CAPTCHA, 9638, 9644),
            "main_Yc_2963_3010": numbered_lines(MAIN, 2963, 3010),
            "main_ds_3455_3469": numbered_lines(MAIN, 3455, 3469),
            "main_tf_4807_4852": numbered_lines(MAIN, 4807, 4852),
        },
        "literalCounts": source_literal_counts(),
        "runtimeBoundary301_329": boundary_lines,
        "decodedSuccessResponse": decoded_success,
        "findings": findings,
        "nextEvidenceTargets": [
            "Capture or statically reconstruct the object passed into main Yc(e,'PX561') before flattening.",
            "Capture or reconstruct the activity array passed to tf(t,e) immediately before ut(t)/Vs(t,d).",
            "Prove whether TBR9Ugl7emA= is deleted/re-added, nested under a field flattened by Yc(), or generated by a serializer/wasm transform after captcha D().",
        ],
    }
    OUT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TBR9 success boundary audit",
        "",
        "## Inputs",
        "",
        f"- JS trace: `{JS_TRACE}`",
        f"- Success bundle: `{BUNDLE}`",
        f"- main source: `{MAIN}`",
        f"- captcha source: `{CAPTCHA}`",
        "",
        "## Final PX561 context",
        "",
        "| index | key | value |",
        "|---:|---|---|",
    ]
    for key in TARGET_KEYS:
        ctx = key_context[key]
        value = ctx["value"]
        text = repr(value)
        if len(text) > 180:
            text = text[:177] + "..."
        lines.append(f"| {ctx['index']} | `{key}` | `{text}` |")
    lines += [
        "",
        "## Runtime boundary",
        "",
        f"- `hsprotect.Xn.trigger` line 301 emits `JDBeOmJSWwo=` with stack entering `ds -> jc -> Iz/D/Ts`.",
        f"- `hsprotect.main.om.decode` line {decoded_success['line'] if decoded_success else 'N/A'} has `oIIoIooo|0`: `{decoded_success['hasSuccessHandler'] if decoded_success else 'N/A'}`.",
        f"- same decoded response has TBR9 literal/value: `{decoded_success['hasTbr9Literal'] if decoded_success else 'N/A'}`.",
        "- line 307-329 then dispatches `_px3`, `_pxde`, `score`, and `captcha succeeded` handlers.",
        "",
        "## Static conflict",
        "",
        "- `captcha.beautified.js:11083` assigns decoded `TBR9Ugl7emA=` from `_s()`.",
        "- `captcha.beautified.js:9638-9644` shows `_s()` returns a boolean expression.",
        "- `captcha.beautified.js:11085` assigns decoded `AEAxBkUsPjQ=` from `Ws.Ng()` after the `_s()` assignment.",
        "- Final `PX561.d` order is `AEAxBkUsPjQ=` index 74 then `TBR9Ugl7emA=` index 75.",
        "",
        "## Findings",
        "",
    ]
    lines += [f"- {finding}" for finding in findings]
    lines += [
        "",
        "## Next evidence targets",
        "",
    ]
    lines += [f"- {target}" for target in audit["nextEvidenceTargets"]]
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(OUT_JSON)
    print(OUT_MD)


if __name__ == "__main__":
    main()
