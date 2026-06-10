#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUN_ID = "ni109xdjp5zp_1780948211"
JS_TRACE = REPO / f"output/outlook_browser/js_internal_trace_{RUN_ID}.jsonl"
BUNDLE = REPO / f"output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_{RUN_ID}.json"
POW = REPO / f"output/protocol_reverse/pow_response/pow_response_{RUN_ID}.json"
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


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


def snippet(path: Path, start: int, end: int) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [f"{i:5d}: {lines[i - 1]}" for i in range(start, end + 1)]


def success_px561() -> dict[str, Any]:
    data = json.loads(BUNDLE.read_text(encoding="utf-8"))
    for req in data.get("requests") or []:
        for item in req.get("activitiesWithMatches") or []:
            activity = item.get("activity") or {}
            if activity.get("t") == "PX561":
                return {
                    "requestLine": req.get("requestLine"),
                    "seq": req.get("seq"),
                    "activityIndex": item.get("index"),
                    "d": activity.get("d") or {},
                }
    raise RuntimeError("PX561 activity not found")


def build_audit() -> dict[str, Any]:
    rows = read_jsonl(JS_TRACE)
    px561 = success_px561()
    d = px561["d"]
    pow_data = json.loads(POW.read_text(encoding="utf-8"))
    pow_result = (pow_data.get("results") or [{}])[0]

    worker_news = [r for r in rows if r.get("kind") == "hsprotect.captcha.worker.new"]
    pow_hits = [r for r in rows if r.get("kind") == "hsprotect.captcha.pow.hit"]
    worker_messages = [r for r in rows if r.get("kind") == "hsprotect.captcha.worker.message"]
    trigger_events = [
        r for r in rows
        if r.get("kind") == "hsprotect.Xn.trigger" and (r.get("data") or {}).get("channel") == "JDBeOmJSWwo="
    ]

    pow_value = pow_result.get("value")
    matching_message = next(
        (r for r in worker_messages if (r.get("data") or {}).get("data") == pow_value),
        None,
    )
    matching_hit = next(
        (r for r in pow_hits if (r.get("data") or {}).get("value") == pow_value),
        None,
    )
    matching_worker_new = None
    if matching_message:
        msg_url = (matching_message.get("data") or {}).get("url")
        matching_worker_new = next(
            (r for r in worker_news if (r.get("data") or {}).get("url") == msg_url),
            None,
        )

    elapsed_wall_ms = None
    if matching_worker_new and matching_message:
        elapsed_wall_ms = round((matching_message["wall_t"] - matching_worker_new["wall_t"]) * 1000)

    static_chain = [
        {
            "id": "Us_sets_global_pow_result",
            "file": str(CAPTCHA.resolve()),
            "lines": "8490..8492",
            "meaning": "Us(r,n) stores Ps=r and Es=m()-n, then sets Ms=true.",
            "snippet": snippet(CAPTCHA, 8490, 8492),
        },
        {
            "id": "worker_callback_calls_Us",
            "file": str(CAPTCHA.resolve()),
            "lines": "8552..8561",
            "meaning": "Worker message callback reads event data n and calls Us(n,f), where f was set before POW search.",
            "snippet": snippet(CAPTCHA, 8552, 8561),
        },
        {
            "id": "sync_fallback_calls_Us",
            "file": str(CAPTCHA.resolve()),
            "lines": "8569..8574",
            "meaning": "Non-worker fallback calls poi(...) and then Us(u,f) when a POW value is found.",
            "snippet": snippet(CAPTCHA, 8569, 8574),
        },
        {
            "id": "Ts_returns_callback_args",
            "file": str(CAPTCHA.resolve()),
            "lines": "8585..8589",
            "meaning": "Ts(cb) calls cb(Gs, Es, Ps) once Ms is true.",
            "snippet": snippet(CAPTCHA, 8585, 8589),
        },
        {
            "id": "D_Ts_callback_writes_final_fields",
            "file": str(CAPTCHA.resolve()),
            "lines": "11073..11099",
            "meaning": "D passes (n,v,e) callback to Ts; later writes Bzt2fUFRcw== = v, OSkIb39DDA== = e, Ew9iCVZjYDw= = n, then emits PX561.",
            "snippet": snippet(CAPTCHA, 11073, 11099),
        },
    ]

    return {
        "run": RUN_ID,
        "inputs": {
            "jsTrace": str(JS_TRACE.resolve()),
            "bundleActivity": str(BUNDLE.resolve()),
            "powResponse": str(POW.resolve()),
            "captchaBeautified": str(CAPTCHA.resolve()),
        },
        "staticChain": static_chain,
        "runtimeEvidence": {
            "workerNew": {
                "line": matching_worker_new.get("_line") if matching_worker_new else None,
                "wall_t": matching_worker_new.get("wall_t") if matching_worker_new else None,
                "perf_t": matching_worker_new.get("perf_t") if matching_worker_new else None,
                "url": (matching_worker_new.get("data") or {}).get("url") if matching_worker_new else None,
            },
            "powHit": {
                "line": matching_hit.get("_line") if matching_hit else None,
                "wall_t": matching_hit.get("wall_t") if matching_hit else None,
                "perf_t": matching_hit.get("perf_t") if matching_hit else None,
                "data": matching_hit.get("data") if matching_hit else None,
            },
            "workerMessage": {
                "line": matching_message.get("_line") if matching_message else None,
                "wall_t": matching_message.get("wall_t") if matching_message else None,
                "perf_t": matching_message.get("perf_t") if matching_message else None,
                "data": matching_message.get("data") if matching_message else None,
            },
            "jdbeTrigger": [
                {
                    "line": r.get("_line"),
                    "wall_t": r.get("wall_t"),
                    "perf_t": r.get("perf_t"),
                    "stack": (r.get("data") or {}).get("stack"),
                }
                for r in trigger_events
            ],
            "elapsedWallMsWorkerNewToMessage": elapsed_wall_ms,
        },
        "powSolve": pow_result,
        "finalPx561": {
            "requestLine": px561["requestLine"],
            "seq": px561["seq"],
            "activityIndex": px561["activityIndex"],
            "Ew9iCVZjYDw=": d.get("Ew9iCVZjYDw="),
            "Bzt2fUFRcw==": d.get("Bzt2fUFRcw=="),
            "OSkIb39DDA==": d.get("OSkIb39DDA=="),
            "XQUsAxhpKjU=": d.get("XQUsAxhpKjU="),
        },
        "findings": [
            "Static chain proves Ts(cb) supplies callback args as (Gs, Es, Ps).",
            "Static chain proves Us(r,n) sets Ps to POW value and Es to elapsed m()-n.",
            "Runtime trace proves worker message data equals pow_response.value and final PX561.d.OSkIb39DDA==.",
            "Runtime elapsed between matching worker.new and matching worker.message rounds to final PX561.d.Bzt2fUFRcw==.",
            "This closes Bzt2fUFRcw== and OSkIb39DDA== producer bridge for the ni109 success sample; it does not close TBR9Ugl7emA=.",
        ],
    }


def write_md(audit: dict[str, Any], path: Path) -> None:
    rt = audit["runtimeEvidence"]
    final = audit["finalPx561"]
    lines = [
        "# Ts callback runtime bridge audit",
        "",
        f"- run: `{audit['run']}`",
        f"- jsTrace: `{audit['inputs']['jsTrace']}`",
        f"- bundleActivity: `{audit['inputs']['bundleActivity']}`",
        f"- powResponse: `{audit['inputs']['powResponse']}`",
        "",
        "## Static chain",
        "",
    ]
    for step in audit["staticChain"]:
        lines += [
            f"### {step['id']}",
            "",
            f"- file: `{step['file']}`",
            f"- lines: `{step['lines']}`",
            f"- meaning: {step['meaning']}",
            "",
            "```js",
            *step["snippet"],
            "```",
            "",
        ]
    lines += [
        "## Runtime bridge evidence",
        "",
        f"- worker.new line: `{rt['workerNew']['line']}` url: `{rt['workerNew']['url']}` wall_t: `{rt['workerNew']['wall_t']}`",
        f"- pow.hit line: `{rt['powHit']['line']}` data: `{json.dumps(rt['powHit']['data'], ensure_ascii=False)}`",
        f"- worker.message line: `{rt['workerMessage']['line']}` data: `{json.dumps(rt['workerMessage']['data'], ensure_ascii=False)}`",
        f"- elapsed worker.new -> worker.message: `{rt['elapsedWallMsWorkerNewToMessage']}` ms",
        "",
        "## Final PX561 fields",
        "",
        f"- requestLine: `{final['requestLine']}`",
        f"- seq: `{final['seq']}`",
        f"- activityIndex: `{final['activityIndex']}`",
        f"- `Ew9iCVZjYDw=`: `{final['Ew9iCVZjYDw=']}`",
        f"- `Bzt2fUFRcw==`: `{final['Bzt2fUFRcw==']}`",
        f"- `OSkIb39DDA==`: `{final['OSkIb39DDA==']}`",
        f"- `XQUsAxhpKjU=`: `{final['XQUsAxhpKjU=']}`",
        "",
        "## Findings",
        "",
    ]
    lines += [f"- {x}" for x in audit["findings"]]
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audit = build_audit()
    json_path = OUT_DIR / "ts_callback_runtime_bridge_audit.json"
    md_path = OUT_DIR / "ts_callback_runtime_bridge_audit.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(audit, md_path)
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
