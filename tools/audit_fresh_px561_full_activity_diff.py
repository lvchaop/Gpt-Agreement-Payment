#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
JS_TRACE = REPO / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"


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
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def digest(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return {
        "type": type(value).__name__,
        "len": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": hashlib.sha256(str(text).encode("utf-8")).hexdigest(),
        "preview": str(text)[:180] + (f"...<len={len(str(text))}>" if len(str(text)) > 180 else ""),
    }


def s00_activities(line_no: int) -> list[dict[str, Any]]:
    for row in read_jsonl(JS_TRACE):
        if row["_line"] == line_no and row.get("kind") == "hsprotect.main.tf.payload":
            activities = (row.get("data") or {}).get("activities") or []
            return json.loads(json.dumps(activities))
    raise RuntimeError(f"s00 tf.payload line {line_no} not found")


def fresh_activities(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    doc = read_json(path)
    material = doc["material"]
    params = parse_form(material["body"])
    decoded = dec.decode_payload(params["payload"], material["meta"]["marker"], params["uuid"])
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    return activities, {
        "probe": doc,
        "params": params,
        "decode": {
            "markerMatch": decoded.get("markerMatch"),
            "jsonError": decoded.get("jsonError"),
            "byteEncoding": decoded.get("byteEncoding"),
            "decodedTextSha256": hashlib.sha256(str(decoded.get("decodedText") or "").encode()).hexdigest(),
        },
    }


def compare_activity(fresh: dict[str, Any] | None, success: dict[str, Any] | None, idx: int) -> dict[str, Any]:
    fd = fresh.get("d") if isinstance(fresh, dict) and isinstance(fresh.get("d"), dict) else {}
    sd = success.get("d") if isinstance(success, dict) and isinstance(success.get("d"), dict) else {}
    keys = list(dict.fromkeys([*fd.keys(), *sd.keys()]))
    field_diffs = []
    for key in keys:
        f_has = key in fd
        s_has = key in sd
        same = f_has and s_has and fd[key] == sd[key]
        if same:
            continue
        field_diffs.append(
            {
                "key": key,
                "freshPresent": f_has,
                "successPresent": s_has,
                "freshIndex": list(fd.keys()).index(key) if f_has else None,
                "successIndex": list(sd.keys()).index(key) if s_has else None,
                "fresh": digest(fd[key]) if f_has else None,
                "success": digest(sd[key]) if s_has else None,
            }
        )
    return {
        "index": idx,
        "freshType": fresh.get("t") if isinstance(fresh, dict) else None,
        "successType": success.get("t") if isinstance(success, dict) else None,
        "typeEqual": isinstance(fresh, dict) and isinstance(success, dict) and fresh.get("t") == success.get("t"),
        "fieldCount": {"fresh": len(fd), "success": len(sd)},
        "keyOrderEqual": list(fd.keys()) == list(sd.keys()),
        "wholeActivityEqual": fresh == success,
        "fieldDiffCount": len(field_diffs),
        "fieldDiffKeys": [row["key"] for row in field_diffs],
        "fieldDiffs": field_diffs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare every decoded activity in a fresh PX561 probe against s00 accepted line922.")
    parser.add_argument("fresh_probe", type=Path)
    parser.add_argument("--s00-line", type=int, default=922)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    fresh, meta = fresh_activities(args.fresh_probe)
    success = s00_activities(args.s00_line)
    max_len = max(len(fresh), len(success))
    activity_diffs = [
        compare_activity(
            fresh[idx] if idx < len(fresh) and isinstance(fresh[idx], dict) else None,
            success[idx] if idx < len(success) and isinstance(success[idx], dict) else None,
            idx,
        )
        for idx in range(max_len)
    ]
    result = {
        "purpose": "Test whether a fresh exact-inner PX561 probe matches the whole decoded collector activity array, not only the PX561 activity.",
        "freshProbe": str(args.fresh_probe),
        "s00Trace": str(JS_TRACE),
        "s00Line": args.s00_line,
        "decode": meta["decode"],
        "request": {
            "seq": meta["params"].get("seq"),
            "rsc": meta["params"].get("rsc"),
            "status": (meta["probe"].get("response") or {}).get("status"),
            "handlers": (meta["probe"].get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (meta["probe"].get("decoded") or {}).get("hasSuccessHandler"),
        },
        "activityCounts": {"fresh": len(fresh), "s00Success": len(success)},
        "activityTypes": {
            "fresh": [a.get("t") for a in fresh if isinstance(a, dict)],
            "s00Success": [a.get("t") for a in success if isinstance(a, dict)],
        },
        "activityTypeOrderEqual": [a.get("t") for a in fresh if isinstance(a, dict)]
        == [a.get("t") for a in success if isinstance(a, dict)],
        "wholeActivitiesEqual": fresh == success,
        "activityDiffs": activity_diffs,
        "nonPx561DiffSummary": [
            {
                "index": row["index"],
                "type": row["freshType"] or row["successType"],
                "fieldDiffCount": row["fieldDiffCount"],
                "keyOrderEqual": row["keyOrderEqual"],
                "wholeActivityEqual": row["wholeActivityEqual"],
                "firstDiffKeys": row["fieldDiffKeys"][:20],
            }
            for row in activity_diffs
            if (row["freshType"] or row["successType"]) != "PX561" and not row["wholeActivityEqual"]
        ],
        "checks": {
            "freshDecodeMarkerMatch": meta["decode"]["markerMatch"],
            "freshRejected": (meta["probe"].get("decoded") or {}).get("hasSuccessHandler") is False,
            "activityTypeOrderEqual": [a.get("t") for a in fresh if isinstance(a, dict)]
            == [a.get("t") for a in success if isinstance(a, dict)],
            "wholeActivitiesEqual": fresh == success,
            "px561ActivityEqual": any(row["freshType"] == "PX561" and row["wholeActivityEqual"] for row in activity_diffs),
            "nonPx561ActivitiesAllEqual": all(
                row["wholeActivityEqual"]
                for row in activity_diffs
                if (row["freshType"] or row["successType"]) != "PX561"
            ),
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.fresh_probe.stem}_full_activity_diff.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "json": str(out),
                "checks": result["checks"],
                "activityCounts": result["activityCounts"],
                "activityTypes": result["activityTypes"],
                "nonPx561DiffSummary": result["nonPx561DiffSummary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
