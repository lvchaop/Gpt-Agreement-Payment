#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
MAIN = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
TBR9_AUDIT = REPO / "output/protocol_reverse/source_offsets/tbr9_success_boundary_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"


NEEDLES = {
    "json_serializer_ut": "function ut(e) {",
    "ds_queue": "function ds(t, e) {",
    "jc_yc": "Rc(r(n), Yc(t, r(n)))",
    "dollar_c_yc": "function $c(t, e) {",
    "tf_enter": "function tf(t, e) {",
    "tf_pc_uses_ut": "h = Jt(ut(t),",
    "tf_vs_call": "v = Vs(t, d),",
    "vs_definition": "Vs = function(t, e) {",
    "vs_clone": "a = t[r(112)](),",
    "vs_serialize_clone": "a = J(ne(ut(a), 50));",
    "np_un_flush": "for (var A = [], M = 0; M < e[R(r)]; M++)",
    "np_un_tf": "var F = tf(A, np),",
    "np_ln_tf": "Cv(tf(m[g], np)",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def line_no(lines: list[str], needle: str) -> int:
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    raise RuntimeError(f"cannot find needle: {needle}")


def snippet(lines: list[str], line: int, radius: int = 4) -> list[dict[str, Any]]:
    start = max(1, line - radius)
    end = min(len(lines), line + radius)
    return [{"line": n, "text": lines[n - 1]} for n in range(start, end + 1)]


def short(value: Any, limit: int = 160) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<len={len(value)}>"
    return value


def main() -> None:
    main_src = MAIN.read_text(encoding="utf-8")
    lines = main_src.splitlines()
    positions = {name: line_no(lines, needle) for name, needle in NEEDLES.items()}
    bundle = load_json(BUNDLE)
    tbr9 = load_json(TBR9_AUDIT)

    success_request = bundle["requests"][0]
    for req in bundle["requests"]:
        if req.get("requestLine") == 308:
            success_request = req
            break
    px561_match = next(
        item
        for item in success_request["activitiesWithMatches"]
        if item.get("type") == "PX561" and item.get("index") == 2
    )
    px561 = px561_match["activity"]["d"]
    ordered_keys = list(px561.keys())

    targets = {}
    for key in [
        "fyNOZTpPQF4=",
        "AEAxBkUsPjQ=",
        "TBR9Ugl7emA=",
        "Bzt2fUFRcw==",
        "OSkIb39DDA==",
    ]:
        targets[key] = {
            "present": key in px561,
            "index": ordered_keys.index(key) if key in px561 else None,
            "value": short(px561.get(key)),
        }

    result = {
        "inputs": {
            "main": str(MAIN),
            "bundle": str(BUNDLE),
            "tbr9Audit": str(TBR9_AUDIT),
        },
        "successRequest": {
            "requestLine": success_request.get("requestLine"),
            "seq": success_request.get("seq"),
            "activityIndex": px561_match.get("index"),
            "activityType": px561_match["activity"]["t"],
            "px561KeyCount": len(px561),
        },
        "targetContext": targets,
        "staticPositions": positions,
        "staticSnippets": {
            name: snippet(lines, line, 5)
            for name, line in positions.items()
        },
        "boundaryChain": [
            {
                "stage": "captcha/main bridge emits activity",
                "evidence": [
                    "main.beautified.js jc(): Rc(r(n), Yc(t, r(n)))",
                    "main.beautified.js $c(): Rc(t, Yc(e, t))",
                ],
                "meaning": "PX561 activity reaches Rc only after Yc(e,'PX561') has flattened primitive/object fields.",
            },
            {
                "stage": "ds queue",
                "evidence": ["main.beautified.js ds(t,e) pushes {t,d:e,ts} into ss/ls"],
                "meaning": "Queued activity keeps the d object reference/value as supplied by Rc/ds, plus sequence/timestamp fields.",
            },
            {
                "stage": "np[un] flush",
                "evidence": [
                    "np[un] loops queued entries into A",
                    "np[un] deletes ts and adds common runtime fields into w.d before tf(A,np)",
                ],
                "meaning": "The flush layer mutates common telemetry fields but does not show a target-specific TBR9 producer.",
            },
            {
                "stage": "tf",
                "evidence": [
                    "tf(t,e) adds fixed common keys to each a.d",
                    "tf computes pc with Jt(ut(t), key)",
                    "tf passes the same activities array to Vs(t,d)",
                ],
                "meaning": "tf sees the activity array before payload encoding; TBR9 should be observable here if present before serialization.",
            },
            {
                "stage": "Vs serializer",
                "evidence": [
                    "Vs(t,e) clones the activities array with t.slice()",
                    "Vs serializes the clone with ut(a), then applies ne/J and marker insertion",
                ],
                "meaning": "Current static evidence shows Vs as serialization/encoding over a clone, not a semantic PX561 field producer.",
            },
        ],
        "findings": [
            "The success decoded bundle has TBR9Ugl7emA= at final PX561 index 75.",
            "Static main flow shows Yc(e,'PX561') output is queued, flushed into A, passed to tf(A,np), and then cloned/serialized by Vs(t,d).",
            "tf adds common fields to every activity d, but the inspected static block has no direct TBR9Ugl7emA= producer.",
            "Vs serializes a cloned activities array via ut(a) before encoding/marker insertion; current static evidence does not show Vs generating semantic PX561 keys.",
            "Therefore the next decisive boundary is tf(A,np) entry / Yc output: if TBR9 is already present there, producer is before or inside Yc flatten; if absent there but present after decode, the missing path is inside Vs/encoding decode assumptions and needs stronger proof.",
        ],
        "nextEvidenceTargets": [
            "Reconstruct or capture the activity array A at tf(A,np) entry for PX561 requestLine=308.",
            "Reconstruct or capture Yc(e,'PX561') output before ds queueing.",
            "If both lack TBR9Ugl7emA=, audit Vs inverse/decode assumptions because static Vs only shows clone -> ut -> encode/marker insertion.",
        ],
        "upstreamTbr9Findings": tbr9["findings"],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "px561_serializer_boundary_audit.json"
    md_path = OUT_DIR / "px561_serializer_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = [
        "# PX561 serializer boundary audit",
        "",
        "## Inputs",
        "",
    ]
    for name, path in result["inputs"].items():
        md.append(f"- {name}: `{path}`")
    md += [
        "",
        "## Success PX561 target context",
        "",
        f"- requestLine: `{result['successRequest']['requestLine']}`",
        f"- seq: `{result['successRequest']['seq']}`",
        f"- activityIndex: `{result['successRequest']['activityIndex']}`",
        f"- keyCount: `{result['successRequest']['px561KeyCount']}`",
        "",
        "| key | present | index | value |",
        "|---|---:|---:|---|",
    ]
    for key, item in targets.items():
        md.append(f"| `{key}` | `{item['present']}` | `{item['index']}` | `{item['value']}` |")
    md += [
        "",
        "## Static boundary positions",
        "",
        "| name | line |",
        "|---|---:|",
    ]
    for name, line in positions.items():
        md.append(f"| `{name}` | {line} |")
    md += ["", "## Boundary chain", ""]
    for item in result["boundaryChain"]:
        md.append(f"### {item['stage']}")
        md.append("")
        md.append(f"- meaning: {item['meaning']}")
        for ev in item["evidence"]:
            md.append(f"- evidence: {ev}")
        md.append("")
    md += ["## Findings", ""]
    for finding in result["findings"]:
        md.append(f"- {finding}")
    md += ["", "## Next evidence targets", ""]
    for target in result["nextEvidenceTargets"]:
        md.append(f"- {target}")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
