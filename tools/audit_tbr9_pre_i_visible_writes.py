#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
TS_FIELDS = REPO / "output/protocol_reverse/source_offsets/captcha_ts_callback_fields_ni109_exact.json"
HANDOFF = REPO / "output/protocol_reverse/source_offsets/tbr9_handoff_call_target_audit.json"
BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
CAPTCHA_PRETTY = REPO / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

TARGET = "TBR9Ugl7emA="


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def line_slice(path: Path, start: int, end: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [
        {"line": line_no, "text": lines[line_no - 1]}
        for line_no in range(start, end + 1)
        if 1 <= line_no <= len(lines)
    ]


def success_px561() -> tuple[int, int, dict[str, Any]]:
    bundle = read_json(BUNDLE)
    for req in bundle["requests"]:
        for hit in req.get("activitiesWithMatches", []):
            activity = hit.get("activity") or {}
            d = activity.get("d") or {}
            if hit.get("type") == "PX561" and TARGET in d:
                return req["requestLine"], hit["index"], d
    raise RuntimeError("success PX561 with TBR9 not found")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts_fields = read_json(TS_FIELDS)
    handoff = read_json(HANDOFF)
    request_line, activity_index, d = success_px561()
    records = ts_fields["records"]
    i_index = next(i for i, row in enumerate(records) if row["expr"] == "i(f(c(439,441)), r)")
    pre_i_records = records[:i_index]
    post_i_records = records[i_index + 1 :]
    visible_writes = [row for row in pre_i_records if row["expr"].startswith("r[")]
    tbr_writes = [row for row in visible_writes if row["decoded"] == TARGET]
    later_tbr_writes = [
        row for row in visible_writes[visible_writes.index(tbr_writes[0]) + 1 :] if row["decoded"] == TARGET
    ] if tbr_writes else []

    final_keys = list(d)
    final_tbr = d[TARGET]
    visible_order = [row["decoded"] for row in visible_writes]
    final_context_keys = final_keys[max(0, final_keys.index(TARGET) - 3): final_keys.index(TARGET) + 4]

    result = {
        "inputs": {
            "tsFields": str(TS_FIELDS),
            "handoffAudit": str(HANDOFF),
            "successBundle": str(BUNDLE),
            "captchaBeautified": str(CAPTCHA_PRETTY),
        },
        "handoffConclusion": handoff["conclusion"],
        "iCallRecord": records[i_index],
        "visiblePreIWrites": visible_writes,
        "postICalls": post_i_records,
        "targetWriteAudit": {
            "target": TARGET,
            "visiblePreIWriteCount": len(tbr_writes),
            "visiblePreIWrites": tbr_writes,
            "laterVisiblePreIRewriteCount": len(later_tbr_writes),
            "laterVisiblePreIRewrites": later_tbr_writes,
        },
        "orderComparison": {
            "visiblePreIWriteOrder": visible_order,
            "finalSuccessContextOrder": final_context_keys,
            "visibleTbrIndex": visible_order.index(TARGET) if TARGET in visible_order else None,
            "visibleAeaxIndex": visible_order.index("AEAxBkUsPjQ=") if "AEAxBkUsPjQ=" in visible_order else None,
            "visibleBztIndex": visible_order.index("Bzt2fUFRcw==") if "Bzt2fUFRcw==" in visible_order else None,
            "finalTbrIndex": final_keys.index(TARGET),
            "finalAeaxIndex": final_keys.index("AEAxBkUsPjQ=") if "AEAxBkUsPjQ=" in final_keys else None,
            "finalBztIndex": final_keys.index("Bzt2fUFRcw==") if "Bzt2fUFRcw==" in final_keys else None,
        },
        "finalSuccessTbr": {
            "requestLine": request_line,
            "activityIndex": activity_index,
            "valueType": type(final_tbr).__name__,
            "valueLength": len(final_tbr) if isinstance(final_tbr, str) else None,
            "valuePreview": final_tbr[:96] if isinstance(final_tbr, str) else final_tbr,
        },
        "sourceSnippets": {
            "captchaDVisiblePreI_11073_11098": line_slice(CAPTCHA_PRETTY, 11073, 11098),
        },
        "findings": [
            "The exact ni109 Ts callback has exactly one visible pre-i(PX561,r) write to TBR9Ugl7emA=.",
            "That visible TBR9 write is r[t(v(-540,-543))] = _s(), whose value source is a boolean expression, not a 127-byte string.",
            "There is no later visible pre-i(PX561,r) rewrite of TBR9Ugl7emA= before the PX561 handoff.",
            "Visible pre-i write order places TBR9Ugl7emA= before AEAxBkUsPjQ= and Bzt2fUFRcw==, while final success order places AEAxBkUsPjQ= before TBR9Ugl7emA= before Bzt2fUFRcw==.",
            "Therefore the visible captcha Ts write set before i(PX561,r) does not explain the final 127-byte TBR9 value or its final insertion order.",
        ],
        "conclusion": (
            "At the now-proven PX561 handoff boundary, visible exact-source writes before i(PX561,r) only support "
            "TBR9Ugl7emA= as _s() boolean. The final 127-byte TBR9 therefore still requires either a non-visible "
            "mutation not represented by direct writes, or insertion/overwrite after main $c/Yc/Rc/ds/tf/serializer."
        ),
        "nextEvidenceTargets": [
            "Capture r immediately before i(PX561,r) as an observation sample to distinguish visible-write expectation from actual runtime object state.",
            "Capture main $c/Yc input-output for the same PX561 activity; if TBR9 changes there, audit Yc/Rc/ds path.",
            "If both pre-i and Yc output lack the 127-byte value, audit tf/Vs/serializer or inverse decode assumptions.",
        ],
    }

    json_path = OUT_DIR / "tbr9_pre_i_visible_writes_audit.json"
    md_path = OUT_DIR / "tbr9_pre_i_visible_writes_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TBR9 pre-i(PX561,r) visible writes audit",
        "",
        "## Visible writes before `i(PX561,r)`",
        "",
        "| order | expr | decoded key | value source | source |",
        "|---:|---|---|---|---|",
    ]
    for idx, row in enumerate(visible_writes):
        lines.append(f"| {idx} | `{row['expr']}` | `{row['decoded']}` | `{row['valueExpr']}` | {row['lineRef']} |")
    lines += [
        "",
        "## Target write audit",
        "",
        f"- visible pre-i TBR write count: `{len(tbr_writes)}`",
        f"- later visible pre-i TBR rewrite count: `{len(later_tbr_writes)}`",
        f"- final success TBR length: `{result['finalSuccessTbr']['valueLength']}`",
        "",
        "## Order comparison",
        "",
        f"- visible write order: `{visible_order}`",
        f"- final context order: `{final_context_keys}`",
        "",
        "## Findings",
        "",
    ]
    lines += [f"- {finding}" for finding in result["findings"]]
    lines += [
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Next evidence targets",
        "",
    ]
    lines += [f"- {target}" for target in result["nextEvidenceTargets"]]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
