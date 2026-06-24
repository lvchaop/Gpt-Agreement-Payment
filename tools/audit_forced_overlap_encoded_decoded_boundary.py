#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit/forced_overlap_encoded_decoded_boundary_audit.json"

DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
COMBO = PROTO / "seq5_seq6_combo_probe/seq5_seq6_combo_probe_3e4d7f2a-6676-11f1-8398-62666cc2b93d_1781279482.json"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def s00_runtime_request(line: int) -> dict[str, Any]:
    for row in read_jsonl(RUNTIME):
        if int(row.get("_line") or 0) == line:
            return row
    raise RuntimeError(f"runtime line not found: {line}")


def s00_activities(line: int) -> list[dict[str, Any]]:
    for row in read_jsonl(JS_TRACE):
        if int(row.get("_line") or 0) == line and row.get("kind") == "hsprotect.main.tf.payload":
            return json.loads(json.dumps((row.get("data") or {}).get("activities") or []))
    raise RuntimeError(f"tf.payload line not found: {line}")


def decode_combo_activities(row: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    material = row.get("material") or {}
    meta = material.get("meta") or {}
    form = dec.parse_form(str(material.get("body") or ""))
    decoded = dec.decode_payload(form.get("payload", ""), str(meta.get("marker") or ""), str(form.get("uuid") or ""))
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    return activities, {"form": form, "decode": decoded}


def summarize_form(body: str, form: dict[str, str]) -> dict[str, Any]:
    return {
        "bodyLenBytes": len(body.encode("utf-8")),
        "bodySha256": sha(body),
        "payloadLen": len(form.get("payload", "")),
        "payloadSha256": sha(form.get("payload", "")),
        "pc": form.get("pc"),
        "uuid": form.get("uuid"),
        "seq": form.get("seq"),
        "rsc": form.get("rsc"),
        "ci": form.get("ci"),
        "csSha256": sha(form.get("cs", "")) if form.get("cs") else None,
        "sidLen": len(form.get("sid", "")),
        "sidSha256": sha(form.get("sid", "")) if form.get("sid") else None,
        "p1": form.get("p1"),
        "vid": form.get("vid"),
        "cts": form.get("cts"),
    }


def compare_activities(fresh: list[dict[str, Any]], s00: list[dict[str, Any]]) -> dict[str, Any]:
    max_len = max(len(fresh), len(s00))
    diffs = []
    for idx in range(max_len):
        f = fresh[idx] if idx < len(fresh) else None
        s = s00[idx] if idx < len(s00) else None
        if f == s:
            continue
        fd = f.get("d") if isinstance(f, dict) and isinstance(f.get("d"), dict) else {}
        sd = s.get("d") if isinstance(s, dict) and isinstance(s.get("d"), dict) else {}
        keys = list(dict.fromkeys([*fd.keys(), *sd.keys()]))
        field_diff_keys = [key for key in keys if fd.get(key, object()) != sd.get(key, object()) or (key in fd) != (key in sd)]
        diffs.append({
            "index": idx,
            "freshType": f.get("t") if isinstance(f, dict) else None,
            "s00Type": s.get("t") if isinstance(s, dict) else None,
            "keyOrderEqual": list(fd.keys()) == list(sd.keys()),
            "fieldDiffCount": len(field_diff_keys),
            "fieldDiffKeys": field_diff_keys[:40],
        })
    return {
        "freshCount": len(fresh),
        "s00Count": len(s00),
        "freshTypes": [item.get("t") for item in fresh if isinstance(item, dict)],
        "s00Types": [item.get("t") for item in s00 if isinstance(item, dict)],
        "typeOrderEqual": [item.get("t") for item in fresh if isinstance(item, dict)] == [item.get("t") for item in s00 if isinstance(item, dict)],
        "wholeActivitiesEqual": fresh == s00,
        "diffCount": len(diffs),
        "diffs": diffs,
    }


def compare_request(name: str, forced_row: dict[str, Any], s00_runtime_line: int, s00_js_line: int) -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    forced_body = str(((forced_row.get("material") or {}).get("body")) or "")
    forced_activities, forced_decoded = decode_combo_activities(forced_row)
    forced_form = forced_decoded["form"]
    s00_body = str(s00_runtime_request(s00_runtime_line).get("post_data") or "")
    s00_form = dec.parse_form(s00_body)
    s00 = s00_activities(s00_js_line)
    form_diff_keys = [
        key for key in list(dict.fromkeys([*s00_form.keys(), *forced_form.keys()]))
        if s00_form.get(key) != forced_form.get(key)
    ]
    return {
        "name": name,
        "s00RuntimeLine": s00_runtime_line,
        "s00JsLine": s00_js_line,
        "forced": summarize_form(forced_body, forced_form),
        "s00": summarize_form(s00_body, s00_form),
        "formDiffKeys": form_diff_keys,
        "payloadEqual": forced_form.get("payload") == s00_form.get("payload"),
        "pcEqual": forced_form.get("pc") == s00_form.get("pc"),
        "bodyEqual": forced_body == s00_body,
        "decode": {
            "forcedMarkerMatch": forced_decoded["decode"].get("markerMatch"),
            "forcedJsonError": forced_decoded["decode"].get("jsonError"),
        },
        "activityCompare": compare_activities(forced_activities, s00),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare forced-overlap final seq5/seq6 encoded and decoded boundary against s00.")
    parser.add_argument("--combo", type=Path, default=COMBO)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    combo_path = args.combo if args.combo.is_absolute() else REPO / args.combo
    combo = read_json(combo_path)
    seq5 = compare_request("seq5", (combo.get("results") or {}).get("seq5") or {}, 933, 922)
    seq6 = compare_request("seq6", (combo.get("results") or {}).get("seq6") or {}, 937, 925)
    seq5_decoded_equal = seq5["activityCompare"]["wholeActivitiesEqual"] is True
    seq6_decoded_equal = seq6["activityCompare"]["wholeActivitiesEqual"] is True
    if seq5_decoded_equal and seq6_decoded_equal:
        conclusion = (
            "The forced-first-failure final control matches s00 decoded activities for both seq5 and seq6, but encoded payload/pc plus outer session fields still differ. "
            "Its rejection therefore closes response ordering plus decoded-activity equality as sufficient, while leaving encoded payload/session/server-state binding open."
        )
    else:
        conclusion = (
            "The forced-first-failure final control was a timing/state-lineage test, not a decoded-equality test: seq5 or seq6 decoded activities still differ from s00, and encoded payload/pc plus outer session fields differ. "
            "Its rejection therefore rules out the tested response ordering as a sufficient condition, but does not by itself close hidden decoded-material or encoded payload/session binding gaps."
        )
    audit = {
        "purpose": "Strictly compare the forced-first-failure final seq5/seq6 encoded and decoded request boundary against s00 accepted-window material.",
        "inputs": {
            "combo": str(combo_path),
            "runtime": str(RUNTIME),
            "jsTrace": str(JS_TRACE),
        },
        "seq5": seq5,
        "seq6": seq6,
        "checks": {
            "seq5DecodedNotEqualS00": seq5["activityCompare"]["wholeActivitiesEqual"] is False,
            "seq6DecodedNotEqualS00": seq6["activityCompare"]["wholeActivitiesEqual"] is False,
            "seq5EncodedPayloadDiffers": seq5["payloadEqual"] is False,
            "seq6EncodedPayloadDiffers": seq6["payloadEqual"] is False,
            "seq5OnlyExpectedOuterAndPayloadPcFormDiffs": seq5["formDiffKeys"] == ["payload", "uuid", "cs", "pc", "sid", "p1", "vid", "ci", "cts"],
            "seq6OnlyExpectedOuterAndPayloadPcFormDiffs": seq6["formDiffKeys"] == ["payload", "uuid", "cs", "pc", "sid", "p1", "vid", "ci", "cts"],
        },
        "conclusion": conclusion,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(args.out), "checks": audit["checks"], "conclusion": audit["conclusion"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
