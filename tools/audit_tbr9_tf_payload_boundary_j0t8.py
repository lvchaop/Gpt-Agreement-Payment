#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
RUN = "j0t8van4qyhm_1781119142"
JS_TRACE = REPO / f"output/outlook_browser/js_internal_trace_{RUN}.jsonl"
BUNDLE_BUILD = REPO / f"output/protocol_reverse/bundle_request_build/bundle_request_build_{RUN}.json"
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

TARGETS = ["TBR9Ugl7emA=", "AEAxBkUsPjQ=", "Bzt2fUFRcw==", "OSkIb39DDA=="]
HOOK_KINDS = [
    "hsprotect.captcha.pre_i_px561",
    "hsprotect.main.$c.yc",
    "hsprotect.main.jc.yc",
    "hsprotect.main.tf.enter",
    "hsprotect.main.tf.payload",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for idx, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["lineNo"] = idx
        rows.append(row)
    return rows


def target_presence(text: str) -> dict[str, bool]:
    return {key: key in text for key in TARGETS}


def pick_targets(d: dict[str, Any] | None) -> dict[str, Any]:
    d = d or {}
    return {
        "hasTBR9": "TBR9Ugl7emA=" in d,
        "tbr9Len": len(d.get("TBR9Ugl7emA=", "")) if isinstance(d.get("TBR9Ugl7emA="), str) else None,
        "tbr9Value": d.get("TBR9Ugl7emA="),
        "hasAEAx": "AEAxBkUsPjQ=" in d,
        "aeaxValue": d.get("AEAxBkUsPjQ="),
        "bzt": d.get("Bzt2fUFRcw=="),
        "osk": d.get("OSkIb39DDA=="),
        "state": d.get("fyNOZTpPQF4="),
    }


def main() -> int:
    trace_rows = parse_jsonl(JS_TRACE)
    build = load_json(BUNDLE_BUILD)

    hook_counts = {kind: 0 for kind in HOOK_KINDS}
    for row in trace_rows:
        kind = row.get("kind")
        if kind in hook_counts:
            hook_counts[kind] += 1

    tf_payload_rows = []
    for row in trace_rows:
        if row.get("kind") != "hsprotect.main.tf.payload":
            continue
        serialized = str((row.get("data") or {}).get("serialized") or "")
        presence = target_presence(serialized)
        activities = (row.get("data") or {}).get("activities") or []
        px561_candidates = []
        for idx, activity in enumerate(activities):
            d = activity.get("d") or {}
            if any(k in d for k in TARGETS):
                px561_candidates.append(
                    {
                        "activityIndex": idx,
                        "type": activity.get("t"),
                        "targetPresence": {k: k in d for k in TARGETS},
                        "tbr9Len": len(d.get("TBR9Ugl7emA=", "")) if isinstance(d.get("TBR9Ugl7emA="), str) else None,
                        "bzt": d.get("Bzt2fUFRcw=="),
                        "osk": d.get("OSkIb39DDA=="),
                    }
                )
        tf_payload_rows.append(
            {
                "line": row["lineNo"],
                "targetPresenceInSerialized": presence,
                "activityCount": len(activities),
                "px561Candidates": px561_candidates,
                "serializedLen": len(serialized),
            }
        )

    pre_i_rows = []
    yc_rows = []
    for row in trace_rows:
        data = row.get("data") or {}
        kind = row.get("kind")
        if kind == "hsprotect.captcha.pre_i_px561":
            snapshot = data.get("snapshot") or {}
            pre_i_rows.append(
                {
                    "line": row["lineNo"],
                    "activityType": data.get("activityType"),
                    "targets": pick_targets(snapshot),
                    "keyCount": len(data.get("keys") or snapshot.keys()),
                }
            )
        if kind in ("hsprotect.main.$c.yc", "hsprotect.main.jc.yc"):
            input_d = data.get("input") or {}
            output_d = data.get("output") or {}
            yc_rows.append(
                {
                    "line": row["lineNo"],
                    "kind": kind,
                    "activityType": data.get("activityType"),
                    "inputTargets": pick_targets(input_d),
                    "outputTargets": pick_targets(output_d),
                    "inputKeyCount": len(data.get("inputKeys") or input_d.keys()),
                    "outputKeyCount": len(data.get("outputKeys") or output_d.keys()),
                }
            )

    build_rows = []
    for row in build.get("rows", []):
        contains = row.get("contains") or {}
        if contains.get("TBR9Ugl7emA=") or contains.get("AEAx") or contains.get("AEAxBkUsPjQ="):
            build_rows.append(
                {
                    "requestLine": row.get("requestLine"),
                    "seq": row.get("seq"),
                    "materialSource": row.get("materialSource"),
                    "materialSourceLine": row.get("materialSourceLine"),
                    "contains": contains,
                    "payloadMatch": row.get("payloadMatch"),
                    "pcMatch": row.get("pcMatch"),
                    "bodyMatch": row.get("bodyMatch"),
                    "serializedSha256": row.get("serializedSha256"),
                    "serializedLen": row.get("serializedLen"),
                }
            )

    tbr_tf_lines = {
        row["line"]
        for row in tf_payload_rows
        if row["targetPresenceInSerialized"].get("TBR9Ugl7emA=")
    }
    tbr_build_rows = [
        row
        for row in build_rows
        if (row.get("contains") or {}).get("TBR9Ugl7emA=")
    ]
    matched_build_rows = [
        row
        for row in tbr_build_rows
        if row.get("materialSource") == "hsprotect.main.tf.payload"
        and row.get("materialSourceLine") in tbr_tf_lines
        and row.get("payloadMatch") is True
        and row.get("pcMatch") is True
        and row.get("bodyMatch") is True
    ]

    checks = {
        "acceptedRunHasTfPayloadHook": hook_counts["hsprotect.main.tf.payload"] > 0,
        "acceptedRunHasTfPayloadTbr9Serialized": bool(tbr_tf_lines),
        "tbr9TfPayloadRowsReplayToObservedBundle": len(matched_build_rows) == len(tbr_build_rows) and bool(matched_build_rows),
        "acceptedSeq5Tbr9ComesFromTfPayload": any(row.get("seq") == "5" for row in matched_build_rows),
        "acceptedRunHasPreIAndYcHooks": hook_counts["hsprotect.captcha.pre_i_px561"] > 0
        and hook_counts["hsprotect.main.$c.yc"] > 0
        and hook_counts["hsprotect.main.jc.yc"] > 0,
        "preIPx561RowsHaveTbr9String": bool(pre_i_rows)
        and all(row["targets"]["hasTBR9"] and row["targets"]["tbr9Len"] for row in pre_i_rows),
        "dollarCYcPx561InputOutputHaveTbr9": any(
            row["kind"] == "hsprotect.main.$c.yc"
            and row["activityType"] == "PX561"
            and row["inputTargets"]["hasTBR9"]
            and row["outputTargets"]["hasTBR9"]
            for row in yc_rows
        ),
    }

    result = {
        "purpose": "Locate TBR9 boundary in accepted j0t8: tf.payload serialized versus downstream bundle encoding.",
        "evidenceFiles": {
            "jsTrace": str(JS_TRACE.resolve()),
            "bundleRequestBuild": str(BUNDLE_BUILD.resolve()),
        },
        "hookCounts": hook_counts,
        "preIPx561Rows": pre_i_rows,
        "ycRowsWithTargets": [
            row
            for row in yc_rows
            if row["inputTargets"]["hasTBR9"] or row["outputTargets"]["hasTBR9"] or row["activityType"] == "PX561"
        ],
        "tfPayloadRowsWithTargets": [
            row
            for row in tf_payload_rows
            if any(row["targetPresenceInSerialized"].values()) or row["px561Candidates"]
        ],
        "bundleRowsWithTargets": build_rows,
        "matchedTbr9BuildRows": matched_build_rows,
        "checks": checks,
        "conclusion": (
            "In accepted j0t8, TBR9Ugl7emA= is already present in captcha.pre_i_px561, main.$c.yc input/output, and hsprotect.main.tf.payload serialized text. "
            "Those tf.payload serialized rows rebuild the observed /assets/js/bundle requests byte-exactly, including payload, pc, and full body. "
            "Therefore TBR9 is not introduced by Yc, tf, Vs/ut, base64, marker, pc construction, or downstream JSON extraction for this accepted run; the remaining producer boundary is before the captcha pre_i_px561 hook inside the captcha D/Ts pre-handoff object construction."
        ),
        "boundary": (
            "This audit proves where TBR9 already exists, but not the exact statement/function that creates the long string before captcha.pre_i_px561. Static source still shows the visible direct assignment as _s() boolean, so a hidden/side-effect producer before the pre_i hook remains to be found."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "tbr9_tf_payload_boundary_j0t8_audit.json"
    out_md = OUT_DIR / "tbr9_tf_payload_boundary_j0t8_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = ["# TBR9 tf.payload boundary audit: j0t8", "", "## Checks", ""]
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## Hook counts", ""]
    for key, value in hook_counts.items():
        lines.append(f"- {key}: `{value}`")
    lines += ["", "## pre_i PX561 rows", ""]
    for row in pre_i_rows:
        t = row["targets"]
        lines.append(
            f"- line {row['line']}: type={row['activityType']} tbr9Len={t['tbr9Len']} bzt={t['bzt']} osk={t['osk']} state={t['state']}"
        )
    lines += ["", "## Yc rows with targets", ""]
    for row in result["ycRowsWithTargets"]:
        lines.append(
            f"- line {row['line']} {row['kind']} type={row['activityType']} "
            f"inputTbr9={row['inputTargets']['hasTBR9']} outputTbr9={row['outputTargets']['hasTBR9']} "
            f"inputOsk={row['inputTargets']['osk']} outputOsk={row['outputTargets']['osk']}"
        )
    lines += ["", "## TBR9 tf.payload rows", ""]
    for row in result["tfPayloadRowsWithTargets"]:
        if not row["targetPresenceInSerialized"].get("TBR9Ugl7emA="):
            continue
        lines.append(f"- line {row['line']}: serializedLen={row['serializedLen']} activityCount={row['activityCount']}")
        for px in row["px561Candidates"]:
            lines.append(
                f"  - activityIndex={px['activityIndex']} type={px['type']} tbr9Len={px['tbr9Len']} bzt={px['bzt']} osk={px['osk']}"
            )
    lines += ["", "## Matched bundle rows", ""]
    for row in matched_build_rows:
        lines.append(
            f"- requestLine={row['requestLine']} seq={row['seq']} materialSourceLine={row['materialSourceLine']} "
            f"payloadMatch={row['payloadMatch']} pcMatch={row['pcMatch']} bodyMatch={row['bodyMatch']}"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], "", "## Boundary", "", result["boundary"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
