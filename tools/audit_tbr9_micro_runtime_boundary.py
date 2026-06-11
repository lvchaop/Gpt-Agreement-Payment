#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
TRACE_DIR = REPO / "output/outlook_browser"
READINESS = REPO / "output/protocol_reverse/source_offsets/tbr9_observation_hook_readiness_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

CORE_MICRO_KINDS = [
    "hsprotect.captcha.tbr9.after_s",
    "hsprotect.captcha.tbr9.after_rs",
    "hsprotect.captcha.tbr9.after_ng",
    "hsprotect.captcha.tbr9.after_nq",
]
TAIL_MICRO_KINDS = [
    "hsprotect.captcha.tbr9.after_inner",
    "hsprotect.captcha.tbr9.after_ou",
    "hsprotect.captcha.tbr9.before_condition",
    "hsprotect.captcha.tbr9.after_condition",
    "hsprotect.captcha.tbr9.before_bzt",
    "hsprotect.captcha.tbr9.after_bzt",
    "hsprotect.captcha.tbr9.after_osk",
    "hsprotect.captcha.tbr9.after_time",
    "hsprotect.captcha.tbr9.after_n",
    "hsprotect.captcha.tbr9.after_os",
    "hsprotect.captcha.tbr9.after_ws",
    "hsprotect.captcha.tbr9.after_ks",
]
MICRO_KINDS = CORE_MICRO_KINDS + TAIL_MICRO_KINDS
PRE_I_KIND = "hsprotect.captcha.pre_i_px561"
YC_KINDS = {"hsprotect.main.$c.yc", "hsprotect.main.jc.yc"}
TF_PAYLOAD_KIND = "hsprotect.main.tf.payload"
TARGET = "TBR9Ugl7emA="
TAIL_KEYS = ["AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="]


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"lineNo": line_no, "kind": "__json_decode_error__", "raw": line[:500]})
            continue
        row["lineNo"] = line_no
        rows.append(row)
    return rows


def value_summary(value: Any, value_type: str | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "type": value_type or type(value).__name__,
        "isPresent": value is not None,
        "isString": isinstance(value, str),
        "isLongString": isinstance(value, str) and len(value) >= 80,
        "isBoolean": isinstance(value, bool),
        "len": len(value) if isinstance(value, str) else None,
    }
    if isinstance(value, str):
        summary["prefix"] = value[:24]
        summary["suffix"] = value[-24:]
    else:
        summary["value"] = value
    return summary


def extract_tbr_from_data(data: dict[str, Any]) -> Any:
    if data.get("nqKey") == TARGET:
        return data.get("nqValue")
    if data.get("key") == TARGET and "value" in data:
        return data.get("value")
    snapshot = data.get("snapshot")
    if isinstance(snapshot, dict):
        return snapshot.get(TARGET)
    if "tbrValue" in data:
        return data.get("tbrValue")
    if "value" in data:
        return data.get("value")
    return None


def summarize_event(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data") or {}
    value = extract_tbr_from_data(data)
    key = data.get("nqKey") if data.get("nqKey") == TARGET else data.get("key") or data.get("tbrKey")
    item = {
        "line": row.get("lineNo"),
        "kind": row.get("kind"),
        "perf_t": row.get("perf_t"),
        "key": key,
        "rawKey": data.get("key") or data.get("tbrKey"),
        "tbr": value_summary(value, data.get("valueType") if key != TARGET else None or data.get("tbrType")),
        "keysCount": len(data.get("keys") or []),
    }
    for key in ("aeaxKey", "aeaxValue", "nqKey", "activityType"):
        if key in data:
            item[key] = value_summary(data[key]) if key.endswith("Value") else data[key]
    for key in ("nInput", "nInputType", "nInputLen"):
        if key in data:
            item[key] = data[key]
    snapshot = data.get("snapshot")
    if isinstance(snapshot, dict):
        item["tail"] = {key: value_summary(snapshot.get(key)) for key in TAIL_KEYS if key in snapshot}
    return item


def summarize_yc(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data") or {}
    input_obj = data.get("input") if isinstance(data.get("input"), dict) else {}
    output_obj = data.get("output") if isinstance(data.get("output"), dict) else {}
    return {
        "line": row.get("lineNo"),
        "kind": row.get("kind"),
        "activityType": data.get("activityType"),
        "inputTbr": value_summary(input_obj.get(TARGET)),
        "outputTbr": value_summary(output_obj.get(TARGET)),
        "inputTail": {key: value_summary(input_obj.get(key)) for key in TAIL_KEYS if key in input_obj},
        "outputTail": {key: value_summary(output_obj.get(key)) for key in TAIL_KEYS if key in output_obj},
    }


def summarize_tf_payload(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data") or {}
    serialized = str(data.get("serialized") or "")
    activities = data.get("activities") if isinstance(data.get("activities"), list) else []
    px561 = []
    for idx, activity in enumerate(activities):
        if not isinstance(activity, dict):
            continue
        d = activity.get("d") if isinstance(activity.get("d"), dict) else {}
        if any(key in d for key in TAIL_KEYS):
            px561.append(
                {
                    "activityIndex": idx,
                    "type": activity.get("t"),
                    "tail": {key: value_summary(d.get(key)) for key in TAIL_KEYS if key in d},
                }
            )
    return {
        "line": row.get("lineNo"),
        "serializedHasTbr9": TARGET in serialized,
        "serializedLen": len(serialized),
        "px561Candidates": px561,
    }


def build_cycles(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cycles: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for row in events:
        kind = row.get("kind")
        if kind == CORE_MICRO_KINDS[0]:
            if current:
                cycles.append(current)
            current = {"startLine": row.get("lineNo"), "events": [summarize_event(row)], "preI": None}
            continue
        if kind in MICRO_KINDS:
            if current is None:
                current = {"startLine": row.get("lineNo"), "events": [], "preI": None, "startedMidSequence": True}
            current["events"].append(summarize_event(row))
            continue
        if kind == PRE_I_KIND:
            if current is None:
                current = {"startLine": row.get("lineNo"), "events": [], "preI": summarize_event(row), "startedAtPreI": True}
                cycles.append(current)
                current = None
            else:
                current["preI"] = summarize_event(row)
                cycles.append(current)
                current = None
    if current:
        cycles.append(current)

    for cycle in cycles:
        sequence = list(cycle.get("events") or [])
        if cycle.get("preI"):
            sequence.append(cycle["preI"])
        first_long = next((event for event in sequence if event.get("tbr", {}).get("isLongString")), None)
        cycle["firstLongStringBoundary"] = {
            "line": first_long.get("line"),
            "kind": first_long.get("kind"),
        } if first_long else None
        kinds = [event.get("kind") for event in cycle.get("events") or []]
        cycle["hasCompleteCoreMicroSequence"] = kinds[: len(CORE_MICRO_KINDS)] == CORE_MICRO_KINDS
        cycle["hasCompleteTailMicroSequence"] = all(kind in kinds for kind in TAIL_MICRO_KINDS)
        cycle["hasCompleteMicroSequence"] = cycle["hasCompleteCoreMicroSequence"] and cycle["hasCompleteTailMicroSequence"]
    return cycles


def analyze_trace(path: Path) -> dict[str, Any]:
    rows = parse_jsonl(path)
    interesting = [
        row
        for row in rows
        if row.get("kind") in set(MICRO_KINDS + [PRE_I_KIND, TF_PAYLOAD_KIND]) | YC_KINDS
    ]
    micro_rows = [row for row in interesting if row.get("kind") in MICRO_KINDS]
    pre_i_rows = [row for row in interesting if row.get("kind") == PRE_I_KIND]
    yc_rows = [row for row in interesting if row.get("kind") in YC_KINDS]
    tf_rows = [row for row in interesting if row.get("kind") == TF_PAYLOAD_KIND]
    cycles = build_cycles([row for row in interesting if row.get("kind") in set(MICRO_KINDS + [PRE_I_KIND])])

    return {
        "trace": str(path.resolve()),
        "run": path.name.removeprefix("js_internal_trace_").removesuffix(".jsonl"),
        "lineCount": len(rows),
        "hookCounts": {
            kind: sum(1 for row in interesting if row.get("kind") == kind)
            for kind in MICRO_KINDS + [PRE_I_KIND, "hsprotect.main.$c.yc", "hsprotect.main.jc.yc", TF_PAYLOAD_KIND]
        },
        "cycles": cycles,
        "ycRowsWithTbrOrPx561": [
            item
            for item in (summarize_yc(row) for row in yc_rows)
            if item["activityType"] == "PX561"
            or item["inputTbr"]["isPresent"]
            or item["outputTbr"]["isPresent"]
        ],
        "tfPayloadRowsWithTbr": [
            item for item in (summarize_tf_payload(row) for row in tf_rows) if item["serializedHasTbr9"] or item["px561Candidates"]
        ],
        "hasMicroHooks": bool(micro_rows),
        "hasPreIHook": bool(pre_i_rows),
        "hasAnyLongTbrInCycle": any(cycle.get("firstLongStringBoundary") for cycle in cycles),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", action="append", help="Specific js_internal_trace_*.jsonl file. Defaults to all traces.")
    parser.add_argument("--out-prefix", default="tbr9_micro_runtime_boundary_audit")
    args = parser.parse_args()

    if args.trace:
        traces = [Path(x) if Path(x).is_absolute() else REPO / x for x in args.trace]
    else:
        traces = sorted(TRACE_DIR.glob("js_internal_trace_*.jsonl"))

    trace_results = [analyze_trace(path) for path in traces if path.exists()]
    traces_with_micro = [item for item in trace_results if item["hasMicroHooks"]]
    traces_with_pre_i = [item for item in trace_results if item["hasPreIHook"]]
    complete_core_cycles = [
        cycle
        for item in traces_with_micro
        for cycle in item["cycles"]
        if cycle.get("hasCompleteCoreMicroSequence")
    ]
    complete_tail_cycles = [
        cycle
        for item in traces_with_micro
        for cycle in item["cycles"]
        if cycle.get("hasCompleteTailMicroSequence")
    ]
    first_boundaries = [
        {
            "run": item["run"],
            "line": cycle["firstLongStringBoundary"]["line"],
            "kind": cycle["firstLongStringBoundary"]["kind"],
        }
        for item in traces_with_micro
        for cycle in item["cycles"]
        if cycle.get("firstLongStringBoundary")
    ]

    readiness = json.loads(READINESS.read_text(encoding="utf-8")) if READINESS.exists() else {}
    checks = {
        "readinessAuditExists": READINESS.exists(),
        "readinessMicroPatchAppliedOffline": bool(
            readiness.get("checks", {}).get("captchaTbr9MicroPatchAppliedOffline")
        ),
        "inputTracesExist": bool(trace_results),
        "anyTraceHasMicroHooks": bool(traces_with_micro),
        "anyTraceHasPreIHook": bool(traces_with_pre_i),
            "anyCompleteMicroCycle": bool(complete_core_cycles),
            "anyCompleteTailMicroCycle": bool(complete_tail_cycles),
        "anyFirstLongStringBoundaryIdentified": bool(first_boundaries),
    }

    result = {
        "purpose": "Classify runtime TBR9 micro-window observations and locate the first hook boundary where TBR9 becomes a long string.",
        "inputs": {
            "traceCount": len(trace_results),
            "readinessAudit": str(READINESS.resolve()),
        },
        "checks": checks,
        "tracesWithMicroHooks": [
            {
                "run": item["run"],
                "hookCounts": item["hookCounts"],
                "cycleCount": len(item["cycles"]),
                "firstBoundaries": [
                    cycle.get("firstLongStringBoundary") for cycle in item["cycles"] if cycle.get("firstLongStringBoundary")
                ],
            }
            for item in traces_with_micro
        ],
        "tracesWithPreIOnly": [
            {
                "run": item["run"],
                "hookCounts": item["hookCounts"],
                "cycleCount": len(item["cycles"]),
            }
            for item in traces_with_pre_i
            if not item["hasMicroHooks"]
        ],
        "firstLongStringBoundaries": first_boundaries,
        "traceResults": trace_results,
        "conclusion": (
            "At least one runtime trace contains TBR9 micro-window hooks and a first long-string boundary was identified."
            if first_boundaries
            else "No runtime trace currently contains enough TBR9 micro-window observations to identify the first long-string boundary. The hook is ready offline, but a new patched observation run is still required."
        ),
        "nextEvidenceTargets": [
            "Run an accepted-equivalent browser observation with OUTLOOK_JS_INTERNAL_TRACE=1 OUTLOOK_HSPROTECT_JS_PATCH=1 OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1.",
            "Re-run this audit on the new js_internal_trace file.",
            "Use the same OSk/POW/request line to connect the identified micro boundary to pre_i, Yc, tf.payload, and decoded /assets/js/bundle.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"{args.out_prefix}.json"
    out_md = OUT_DIR / f"{args.out_prefix}.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# TBR9 micro runtime boundary audit", "", "## Checks", ""]
    for key, value in checks.items():
        md.append(f"- {key}: `{value}`")
    md += ["", "## Traces with micro hooks", ""]
    if traces_with_micro:
        for item in result["tracesWithMicroHooks"]:
            md.append(f"- `{item['run']}` counts={item['hookCounts']} firstBoundaries={item['firstBoundaries']}")
    else:
        md.append("- none")
    md += ["", "## Traces with pre_i but no micro hooks", ""]
    if result["tracesWithPreIOnly"]:
        for item in result["tracesWithPreIOnly"]:
            md.append(f"- `{item['run']}` counts={item['hookCounts']}")
    else:
        md.append("- none")
    md += ["", "## Conclusion", "", result["conclusion"], "", "## Next evidence targets", ""]
    md.extend(f"- {item}" for item in result["nextEvidenceTargets"])
    out_md.write_text("\n".join(md), encoding="utf-8")

    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
