#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"
CAPTCHA = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
MAIN = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
RUN = "ni109xdjp5zp_1780948211"


def lines(path: Path, start: int, end: int) -> str:
    out: list[str] = []
    for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if start <= no <= end:
            out.append(f"{no}: {line}")
    return "\n".join(out)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def pick_js_events() -> list[dict[str, Any]]:
    js_path = REPO / f"output/outlook_browser/js_internal_trace_{RUN}.jsonl"
    rows = read_jsonl(js_path)
    selected: list[dict[str, Any]] = []
    for row in rows:
        no = int(row["_line"])
        if no not in {301, 323, 324, 325, 332}:
            continue
        data = row.get("data") or {}
        selected.append({
            "line": no,
            "kind": row.get("kind"),
            "channel": data.get("channel"),
            "arg": data.get("arg"),
            "state": data.get("state"),
            "args": data.get("args"),
            "stack": "\n".join(str(data.get("stack") or "").splitlines()[:10]),
        })
    return selected


def main() -> None:
    ts_fields = json.loads((OUT_DIR / "captcha_ts_callback_fields.json").read_text(encoding="utf-8"))
    success_stage = json.loads((OUT_DIR / "success_bundle_stage_audit.json").read_text(encoding="utf-8"))
    pow_response = json.loads((REPO / f"output/protocol_reverse/pow_response/pow_response_{RUN}.json").read_text(encoding="utf-8"))

    result = {
        "inputs": {
            "captcha": str(CAPTCHA),
            "main": str(MAIN),
            "tsFields": str(OUT_DIR / "captcha_ts_callback_fields.json"),
            "successStage": str(OUT_DIR / "success_bundle_stage_audit.json"),
            "powResponse": str(REPO / f"output/protocol_reverse/pow_response/pow_response_{RUN}.json"),
        },
        "staticBoundaries": {
            "wasmGlue": {
                "file": str(CAPTCHA),
                "lines": "9115-9197,9428-9468",
                "snippet": lines(CAPTCHA, 9115, 9197) + "\n...\n" + lines(CAPTCHA, 9428, 9468),
                "facts": [
                    "w(index) reads JS object heap.",
                    "a(value,malloc,realloc) encodes JS string into WASM memory and stores K length.",
                    "H() exposes Int32Array view of WASM memory.",
                    "y(ptr,len) TextDecoder-decodes bytes from WASM memory and returns a JS string.",
                    "Ws.Ng() calls c.Ng(stackPtr), reads ptr/len from H(), then returns y(ptr,len).",
                    "Ws.NQ(r) encodes JS string r into WASM memory, calls c.NQ(stackPtr, ptr, len), reads ptr/len, then returns y(ptr,len).",
                ],
            },
            "_s": {
                "file": str(CAPTCHA),
                "lines": "9638-9644",
                "snippet": lines(CAPTCHA, 9638, 9644),
                "fact": "_s() returns boolean: presence of a window object and nested property; it does not directly produce the 127-byte TBR9 string.",
            },
            "Ts": {
                "file": str(CAPTCHA),
                "rawSource": "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js around function Ts",
                "fact": "Ts(callback) passes callback(Gs, Es, Ps) once Ms is true; otherwise it retries every 500 ms.",
            },
            "D_Ts_px561": {
                "file": str(CAPTCHA),
                "lines": "11073-11099",
                "snippet": lines(CAPTCHA, 11073, 11099),
                "decodedFields": ts_fields.get("records"),
            },
            "Yc_flatten": {
                "file": str(MAIN),
                "lines": "2963-3009",
                "snippet": lines(MAIN, 2963, 3009),
                "fact": "Yc flattens only values whose runtime typeof is object, non-null, and not array-like by Zt(k). A string returned by Ws.NQ is copied under its outer key, not flattened.",
            },
        },
        "successRuntimeBoundary": {
            "events": pick_js_events(),
            "successRequest308": success_stage["request308"],
        },
        "powEvidence": {
            "powPartCount": pow_response.get("powPartCount"),
            "results": pow_response.get("results"),
        },
        "corrections": [
            "Previous hypothesis that Ws.NQ(n) directly returns an object for Yc flatten is not supported by wasm glue evidence; wrapper returns TextDecoder string y(ptr,len).",
            "Final absence of outer key 'succeeded' still needs a separate explanation: either key is deleted/rewritten before Yc, static decoded key is version/context-sensitive, or the final fyNOZ/TBR9 group is inserted by a different path. Current artifacts do not prove which.",
            "TBR9Ugl7emA= cannot be direct _s() output because _s() is boolean and final value is a 127-byte string.",
            "Bzt2fUFRcw== and OSkIb39DDA== map to Ts callback params v/e at captcha.beautified.js:11097; pow_response artifact proves OSk has one POW result but the exact Ts param assignment bridge still needs runtime argument capture.",
        ],
        "nextEvidenceNeeded": [
            "Runtime capture of Ts callback arguments (n,v,e) immediately before line 11097 assignment.",
            "Runtime capture of Ws.Ng() and Ws.NQ(n) return values in the success source version without triggering risk detection.",
            "A source-version-matched main.min.js body for success etag c84dd4de247dae690c1b1b4e99cce4e8, or a proof that current main.beautified.js matches that etag.",
            "Proof of where final TBR9Ugl7emA= is inserted/overwritten if not direct _s().",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "captcha_wasm_pow_boundaries_audit.json"
    md_path = OUT_DIR / "captcha_wasm_pow_boundaries_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines_md = [
        "# captcha WASM / POW boundary audit",
        "",
        "## static facts",
        "- `Ws.Ng()` and `Ws.NQ(r)` both return `y(ptr,len)`, where `y` is a TextDecoder string decode over WASM memory.",
        "- `_s()` is boolean and cannot directly be the final 127-byte `TBR9Ugl7emA=` value.",
        "- `Yc()` only flattens runtime object values; it does not flatten strings.",
        "",
        "## success runtime boundary",
        "| line | kind | channel/arg/state | stack head |",
        "|---:|---|---|---|",
    ]
    for ev in result["successRuntimeBoundary"]["events"]:
        label = ev.get("channel") or ev.get("arg") or ev.get("state")
        stack = str(ev.get("stack") or "").replace("\n", "<br>")
        lines_md.append(f"| {ev['line']} | `{ev['kind']}` | `{label}` | {stack} |")
    lines_md += [
        "",
        "## corrections",
    ]
    for item in result["corrections"]:
        lines_md.append(f"- {item}")
    lines_md += ["", "## next evidence needed"]
    for item in result["nextEvidenceNeeded"]:
        lines_md.append(f"- {item}")
    md_path.write_text("\n".join(lines_md) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
