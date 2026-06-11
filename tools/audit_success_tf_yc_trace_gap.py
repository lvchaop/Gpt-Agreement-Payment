#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
TRACE_V2 = REPO / "output/protocol_reverse/trace_classification_v2/human_trace_classifier_v2_summary.json"
SUCCESS_TRACE = REPO / "output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl"
SUCCESS_BUNDLE = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
FAILURE_TRACE = REPO / "output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

HOOK_KINDS = [
    "hsprotect.main.$c.yc",
    "hsprotect.main.jc.yc",
    "hsprotect.main.tf.enter",
    "hsprotect.main.tf.payload",
]
TARGET_KEYS = [
    "TBR9Ugl7emA=",
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        row["_line"] = line_no
        rows.append(row)
    return rows


def short(value: Any, limit: int = 180) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"...<len={len(value)}>"
    return value


def trace_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    hook_events = []
    jdbe_events = []
    target_literal_hits = {key: [] for key in TARGET_KEYS}
    for row in rows:
        kind = row.get("kind")
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind in HOOK_KINDS:
            hook_events.append(
                {
                    "line": row["_line"],
                    "kind": kind,
                    "dataKeys": sorted((row.get("data") or {}).keys()),
                    "data": short(row.get("data")),
                }
            )
        data = row.get("data") or {}
        if kind == "hsprotect.Xn.trigger" and data.get("channel") == "JDBeOmJSWwo=":
            jdbe_events.append(
                {
                    "line": row["_line"],
                    "kind": kind,
                    "argsLen": len(data.get("args") or []),
                    "stack": data.get("stack"),
                }
            )
        text = json.dumps(row, ensure_ascii=False)
        for key in TARGET_KEYS:
            if key in text:
                target_literal_hits[key].append(row["_line"])
    return {
        "lineCount": len(rows),
        "kindCounts": kinds,
        "hookEvents": hook_events,
        "jdbeEvents": jdbe_events,
        "targetLiteralHits": target_literal_hits,
    }


def extract_success_px561() -> dict[str, Any]:
    bundle = load_json(SUCCESS_BUNDLE)
    req = next(r for r in bundle["requests"] if r.get("requestLine") == 308)
    px561_match = next(item for item in req["activitiesWithMatches"] if item.get("type") == "PX561")
    d = px561_match["activity"]["d"]
    keys = list(d.keys())
    return {
        "requestLine": req["requestLine"],
        "seq": req["seq"],
        "activityIndex": px561_match["index"],
        "keyCount": len(d),
        "targetKeys": {
            key: {
                "present": key in d,
                "index": keys.index(key) if key in d else None,
                "value": short(d.get(key)),
            }
            for key in TARGET_KEYS
        },
    }


def main() -> None:
    trace_v2 = load_json(TRACE_V2)
    success_rows = iter_jsonl(SUCCESS_TRACE)
    failure_rows = iter_jsonl(FAILURE_TRACE)
    success = trace_summary(success_rows)
    failure = trace_summary(failure_rows)
    px561 = extract_success_px561()

    success_run = next(r for r in trace_v2["runs"] if r["run"] == "ni109xdjp5zp_1780948211")
    failure_run = next(r for r in trace_v2["runs"] if r["run"] == "hcxwyrtiudbg_1780949301")

    result = {
        "inputs": {
            "traceV2": str(TRACE_V2),
            "successTrace": str(SUCCESS_TRACE),
            "successBundle": str(SUCCESS_BUNDLE),
            "failureTraceControl": str(FAILURE_TRACE),
        },
        "successRun": {
            "run": success_run["run"],
            "stage": success_run["stage"],
            "checks": success_run["checks"],
            "counts": success_run["counts"],
            "sourceVersion": success_run["sourceVersion"],
        },
        "failureControlRun": {
            "run": failure_run["run"],
            "stage": failure_run["stage"],
            "counts": failure_run["counts"],
            "sourceVersion": failure_run["sourceVersion"],
        },
        "successTraceSummary": success,
        "failureControlTraceSummary": failure,
        "successFinalPx561": px561,
        "findings": [
            "The authoritative success trace has final decoded PX561 with TBR9Ugl7emA= present at requestLine 308 activity index 2.",
            "The same success js_internal_trace does not contain hsprotect.main.$c.yc, hsprotect.main.jc.yc, hsprotect.main.tf.enter, or hsprotect.main.tf.payload hook events.",
            "The success trace contains a JDBeOmJSWwo= trigger with stack ds -> jc -> Iz/D/Ts, but its args array is empty and does not carry the Yc output or tf activity array.",
            "The hcxwyrtiudbg control has tf hook material but is classified as tf_payload_failure_stage, not full_success_decoded, so it cannot substitute for success Yc/tf evidence.",
            "Therefore existing unpatched success evidence proves final TBR9 presence but cannot prove whether TBR9 existed at Yc output or tf(A,np) entry.",
        ],
        "nextEvidenceRequired": [
            "Need a success-equivalent Yc/tf boundary artifact: either reconstruct Yc output offline from captcha D/Ts objects or collect an observation sample that captures main.$c.yc/main.jc.yc and tf.enter without treating it as authoritative success baseline.",
            "Do not infer TBR9 producer from hcx tf.payload controls because v2 classifier marks them as failure-stage controls.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "success_tf_yc_trace_gap_audit.json"
    md_path = OUT_DIR / "success_tf_yc_trace_gap_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = [
        "# Success Yc/tf trace gap audit",
        "",
        "## Inputs",
        "",
    ]
    for name, path in result["inputs"].items():
        md.append(f"- {name}: `{path}`")
    md += [
        "",
        "## Success final PX561",
        "",
        f"- run: `{result['successRun']['run']}`",
        f"- stage: `{result['successRun']['stage']}`",
        f"- requestLine: `{px561['requestLine']}`",
        f"- activityIndex: `{px561['activityIndex']}`",
        f"- keyCount: `{px561['keyCount']}`",
        "",
        "| key | present | index | value |",
        "|---|---:|---:|---|",
    ]
    for key, item in px561["targetKeys"].items():
        md.append(f"| `{key}` | `{item['present']}` | `{item['index']}` | `{item['value']}` |")
    md += [
        "",
        "## Hook coverage",
        "",
        "| trace | hook | count |",
        "|---|---|---:|",
    ]
    for hook in HOOK_KINDS:
        md.append(f"| success | `{hook}` | {success['kindCounts'].get(hook, 0)} |")
    for hook in HOOK_KINDS:
        md.append(f"| failure control | `{hook}` | {failure['kindCounts'].get(hook, 0)} |")
    md += [
        "",
        "## Success JDBeOmJSWwo= trigger",
        "",
    ]
    for event in success["jdbeEvents"]:
        md.append(f"- line `{event['line']}` argsLen=`{event['argsLen']}`")
        md.append("```text")
        md.append(event["stack"] or "")
        md.append("```")
    md += ["", "## Findings", ""]
    for finding in result["findings"]:
        md.append(f"- {finding}")
    md += ["", "## Next evidence required", ""]
    for item in result["nextEvidenceRequired"]:
        md.append(f"- {item}")
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
