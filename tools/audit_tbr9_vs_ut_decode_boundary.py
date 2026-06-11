#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
MAIN = REPO / "output/outlook_browser/js_static_analysis/main.beautified.js"
RUNTIME_TRACE = REPO / "output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl"
COLLECTOR_DECODE = REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json"
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
REPLAY_FILES = [
    REPO / "output/protocol_reverse/payload_replay/vs_payload_replay_i294e72kliud_1781017380.json",
    REPO / "output/protocol_reverse/payload_replay/vs_payload_replay_whsnxy8ag5ji_1781017142.json",
]
OUT_DIR = REPO / "output/protocol_reverse/source_offsets"

TARGET = "TBR9Ugl7emA="
TARGET_VALUE = (
    "Y@tvUUF@W!kfHgFtWXNlXwpXFSUQa#E@JWcdNy!uUxIeWg(beEAsCx!sFE(ZFl$N)"
    "QFWUdcMkZWLFhtVl%EFBRNG@)oBWxofy$@TDoBGmpvNidTdExVQAURc)cBSDcg"
)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_decode_tool() -> Any:
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, start=1):
            if line.strip():
                rows.append({"_line": idx, **json.loads(line)})
    return rows


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[unquote(key)] = unquote(value)
    return out


def line_no(lines: list[str], needle: str) -> int:
    for idx, line in enumerate(lines, start=1):
        if needle in line:
            return idx
    raise RuntimeError(f"needle not found: {needle}")


def snippet(lines: list[str], start: int, end: int) -> list[dict[str, Any]]:
    return [{"line": i, "text": lines[i - 1]} for i in range(start, end + 1)]


def replay_summary() -> dict[str, Any]:
    rows = []
    totals = {
        "events": 0,
        "serializedMatches": 0,
        "payloadMatches": 0,
        "pcMatches": 0,
        "markerMatches": 0,
    }
    for path in REPLAY_FILES:
        doc = load_json(path)
        result = doc["result"]
        row = {
            "path": str(path),
            "events": len(result),
            "serializedMatches": sum(1 for x in result if x["serializedMatch"]),
            "payloadMatches": sum(1 for x in result if x["payloadMatch"]),
            "pcMatches": sum(1 for x in result if x["pcMatch"]),
            "markerMatches": sum(1 for x in result if x["markerMatch"]),
        }
        rows.append(row)
        for key in totals:
            totals[key] += row[key]
    return {"files": rows, "totals": totals}


def main() -> None:
    main_lines = MAIN.read_text(encoding="utf-8").splitlines()
    positions = {
        "ut": line_no(main_lines, "function ut(e) {"),
        "ut_object_loop": line_no(main_lines, "for (var o in n = [\"{\"], e)"),
        "J": line_no(main_lines, "function J(t) {"),
        "ne": line_no(main_lines, "function ne(t, e) {"),
        "Qi": line_no(main_lines, "function Qi() {"),
        "Vs": line_no(main_lines, "Vs = function(t, e) {"),
        "Vs_marker": line_no(main_lines, "return ne(J(Qi() || t(118)), 10)"),
        "Vs_serialize": line_no(main_lines, "a = J(ne(ut(a), 50));"),
        "Vs_insert": line_no(main_lines, "return o += e[a(r.l)](i), o"),
        "tf_pc_ut": line_no(main_lines, "h = Jt(ut(t),"),
        "tf_vs": line_no(main_lines, "v = Vs(t, d),"),
    }

    dec = load_decode_tool()
    rows = read_jsonl(RUNTIME_TRACE)
    req308 = next(
        r for r in rows
        if r.get("_line") == 308 and r.get("kind") == "request" and str(r.get("url") or "").endswith("/assets/js/bundle")
    )
    params = parse_form(req308.get("post_data") or "")
    timeline = dec.build_marker_timeline(COLLECTOR_DECODE)
    marker = dec.marker_for_request(timeline, 308)
    decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])
    text = decoded["decodedText"]
    parsed = decoded["json"]
    px561 = next(item for item in parsed if item.get("t") == "PX561" and TARGET in item.get("d", {}))
    keys = list(px561["d"])

    replay = replay_summary()
    target_index_text = text.index(TARGET) if TARGET in text else None
    target_value_index_text = text.index(TARGET_VALUE) if TARGET_VALUE in text else None

    result = {
        "inputs": {
            "main": str(MAIN),
            "runtimeTrace": str(RUNTIME_TRACE),
            "collectorDecode": str(COLLECTOR_DECODE),
            "decodeTool": str(DECODE_TOOL),
            "replayFiles": [str(p) for p in REPLAY_FILES],
        },
        "staticPositions": positions,
        "staticSnippets": {
            "ut": snippet(main_lines, positions["ut"], positions["ut_object_loop"] + 1),
            "J_ne_Qi": snippet(main_lines, positions["J"], positions["J"] + 20)
            + snippet(main_lines, positions["ne"], positions["ne"] + 3)
            + snippet(main_lines, positions["Qi"], positions["Qi"] + 2),
            "Vs": snippet(main_lines, positions["Vs"], positions["Vs_insert"] + 1),
            "tf": snippet(main_lines, positions["tf_pc_ut"], positions["tf_vs"]),
        },
        "successLine308Decode": {
            "requestLine": 308,
            "payloadLen": len(params["payload"]),
            "uuid": params["uuid"],
            "marker": marker,
            "extractedMarker": decoded["marker"],
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "jsonItemCount": len(parsed),
            "decodedTextHasTargetKey": TARGET in text,
            "decodedTextHasTargetValue": TARGET_VALUE in text,
            "targetKeyTextIndex": target_index_text,
            "targetValueTextIndex": target_value_index_text,
            "markerContainsTargetKey": TARGET in marker["marker"],
            "markerContainsTargetValue": TARGET_VALUE in marker["marker"],
            "removedBaseContainsTargetKeyBeforeBase64Xor": TARGET in decoded["base"],
            "removedBaseContainsTargetValueBeforeBase64Xor": TARGET_VALUE in decoded["base"],
            "px561TbrIndexAfterJsonParse": keys.index(TARGET),
            "px561TbrValueLenAfterJsonParse": len(px561["d"][TARGET]),
            "decodedTextAroundTbr": text[max(0, target_index_text - 120): target_index_text + 220] if target_index_text is not None else None,
        },
        "vsReplayEvidence": replay,
        "checks": {
            "successMarkerMatch": decoded["markerMatch"] is True,
            "successDecodedTextHasTbrBeforeJsonParse": TARGET in text and TARGET_VALUE in text,
            "successJsonParseHasTbr": TARGET in px561["d"] and px561["d"][TARGET] == TARGET_VALUE,
            "markerDoesNotCarryTbr": TARGET not in marker["marker"] and TARGET_VALUE not in marker["marker"],
            "encodedBaseDoesNotPlainlyCarryTbr": TARGET not in decoded["base"] and TARGET_VALUE not in decoded["base"],
            "replayAllSerializedMatch": replay["totals"]["serializedMatches"] == replay["totals"]["events"],
            "replayAllPayloadMatch": replay["totals"]["payloadMatches"] == replay["totals"]["events"],
            "replayAllPcMatch": replay["totals"]["pcMatches"] == replay["totals"]["events"],
            "replayAllMarkerMatch": replay["totals"]["markerMatches"] == replay["totals"]["events"],
        },
        "findings": [
            "main.ut is a JSON-style serializer over the input object/array; its object branch iterates existing own enumerable keys and does not synthesize a PX561 semantic key.",
            "main.Vs first clones the activity array with slice(), then serializes that clone through ut(a), XORs the serialized text with 50, base64-encodes it through J(), and inserts a marker derived from Qi()/fallback.",
            "The line 308 success payload decodes with markerMatch=true; after removing the marker and applying base64 decode + XOR 50, decodedText already contains TBR9Ugl7emA= and the 127-byte value before json.loads.",
            "The extracted marker string itself does not contain TBR9Ugl7emA= or the 127-byte value, and the marker-removed encoded base does not contain those strings in plaintext.",
            "Existing tf.payload replay samples validate the local ut/Vs/pc implementation against observed runtime payloads: all selected events match serialized, payload, marker, and pc.",
            "Therefore the current evidence does not support a Vs marker/decode artifact as the source of semantic TBR9; if TBR9 is absent at tf entry, the remaining conflict is a missing runtime mutation or an unobserved producer before ut serializes the activity array.",
        ],
        "conclusion": "The visible ut/Vs layer is now constrained to serialize existing activity fields and encode/marker-insert the resulting string. For success line 308, TBR9 exists in decodedText before JSON parsing and is not carried by the marker. This narrows P0 away from a JSON extraction or marker artifact and back to the pre-ut activity object boundary: capture/reconstruct Yc output and tf entry for the success-equivalent PX561.",
        "nextEvidenceTargets": [
            "Capture an observation sample that executes browser hsprotect JS and logs main.$c.yc/main.jc.yc plus tf.enter for PX561.",
            "If tf.enter already has the 127-byte TBR9, audit captcha-side runtime mutation between visible _s() assignment and i(PX561,r).",
            "If tf.enter lacks TBR9 but payload decode has it in the same run, inspect non-visible hooks around ut(t) argument or monkey-patched object enumeration/prototype behavior.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "tbr9_vs_ut_decode_boundary_audit.json"
    md_path = OUT_DIR / "tbr9_vs_ut_decode_boundary_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# TBR9 Vs/ut/decode boundary audit",
        "",
        "## Success line 308 decode checks",
        "",
        "| check | value |",
        "|---|---:|",
        *[f"| `{k}` | `{v}` |" for k, v in result["checks"].items()],
        "",
        "## Static positions",
        "",
        "| name | line |",
        "|---|---:|",
        *[f"| `{k}` | {v} |" for k, v in positions.items()],
        "",
        "## Vs replay evidence",
        "",
        "| file | events | serialized | payload | marker | pc |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in replay["files"]:
        md.append(
            f"| `{Path(row['path']).name}` | {row['events']} | {row['serializedMatches']} | "
            f"{row['payloadMatches']} | {row['markerMatches']} | {row['pcMatches']} |"
        )
    md += [
        "",
        "## Findings",
        "",
        *[f"- {x}" for x in result["findings"]],
        "",
        "## Conclusion",
        "",
        result["conclusion"],
        "",
        "## Next evidence targets",
        "",
        *[f"- {x}" for x in result["nextEvidenceTargets"]],
        "",
    ]
    md_path.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
