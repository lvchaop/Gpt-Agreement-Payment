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


def px_activity(activities: list[Any]) -> dict[str, Any]:
    for activity in activities:
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return activity
    raise RuntimeError("PX561 not found")


def s00_px(line_no: int) -> dict[str, Any]:
    for row in read_jsonl(JS_TRACE):
        if row["_line"] == line_no and row.get("kind") == "hsprotect.main.tf.payload":
            return px_activity((row.get("data") or {}).get("activities") or [])
    raise RuntimeError(f"s00 line {line_no} not found")


def fresh_px(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    doc = read_json(path)
    material = doc["material"]
    params = parse_form(material["body"])
    decoded = dec.decode_payload(params["payload"], material["meta"]["marker"], params["uuid"])
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    return px_activity(activities), {
        "probe": doc,
        "params": params,
        "decode": {
            "markerMatch": decoded.get("markerMatch"),
            "jsonError": decoded.get("jsonError"),
            "byteEncoding": decoded.get("byteEncoding"),
        },
    }


def digest(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return {
        "type": type(value).__name__,
        "len": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": hashlib.sha256(str(text).encode("utf-8")).hexdigest(),
        "preview": str(text)[:140] + (f"...<len={len(str(text))}>" if len(str(text)) > 140 else ""),
    }


def classify_key(key: str, value: Any) -> str:
    text = str(value)
    if key in {"AEAxBkUsPjQ=", "TBR9Ugl7emA=", "OSkIb39DDA==", "Bzt2fUFRcw=="}:
        return "pow_wasm_tail"
    if key in {"FUFvS1Mga38=", "GUVjT1wnbn4=", "fg4ERDtuD3I=", "SlpwEAw5eSc="}:
        return "session_or_cookie"
    if isinstance(value, int) and 1_700_000_000_000 <= value <= 1_900_000_000_000:
        return "epoch_ms"
    if isinstance(value, list) and any(isinstance(x, int) and 1_700_000_000_000 <= x <= 1_900_000_000_000 for x in value):
        return "epoch_ms_list"
    if "65a9-11f1" in text or "178119" in text or "ac9e68ae" in text or "7bbba710" in text:
        return "stale_literal_risk"
    return "other"


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-field diff for fresh PX561 probe against s00 line922 accepted PX561.")
    parser.add_argument("fresh_probe", type=Path)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    fresh, meta = fresh_px(args.fresh_probe)
    success = s00_px(922)
    failure = s00_px(566)
    fd = fresh.get("d") or {}
    sd = success.get("d") or {}
    faild = failure.get("d") or {}
    keys = list(dict.fromkeys([*fd.keys(), *sd.keys()]))
    diffs = []
    same_as_success = []
    same_as_failure = []
    for idx, key in enumerate(keys):
        f_has = key in fd
        s_has = key in sd
        fl_has = key in faild
        same_s = f_has and s_has and fd[key] == sd[key]
        same_f = f_has and fl_has and fd[key] == faild[key]
        row = {
            "key": key,
            "freshIndex": list(fd.keys()).index(key) if f_has else None,
            "successIndex": list(sd.keys()).index(key) if s_has else None,
            "failureIndex": list(faild.keys()).index(key) if fl_has else None,
            "freshPresent": f_has,
            "successPresent": s_has,
            "failurePresent": fl_has,
            "sameAsSuccess": same_s,
            "sameAsFailure": same_f,
            "class": classify_key(key, fd.get(key) if f_has else sd.get(key)),
            "fresh": digest(fd[key]) if f_has else None,
            "success": digest(sd[key]) if s_has else None,
            "failure": digest(faild[key]) if fl_has else None,
        }
        if not same_s:
            diffs.append(row)
        else:
            same_as_success.append(key)
        if same_f:
            same_as_failure.append(key)

    result = {
        "purpose": "Identify every PX561 field still differing after progression+fresh POW/WASM line922 probe.",
        "freshProbe": str(args.fresh_probe),
        "decode": meta["decode"],
        "request": {
            "seq": meta["params"].get("seq"),
            "rsc": meta["params"].get("rsc"),
            "status": (meta["probe"].get("response") or {}).get("status"),
            "handlers": (meta["probe"].get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (meta["probe"].get("decoded") or {}).get("hasSuccessHandler"),
        },
        "fieldCounts": {"fresh": len(fd), "s00Success": len(sd), "s00Failure": len(faild)},
        "keyOrder": {"freshEqualsS00Success": list(fd.keys()) == list(sd.keys())},
        "diffCountVsS00Success": len(diffs),
        "sameAsSuccessCount": len(same_as_success),
        "sameAsFailureCount": len(same_as_failure),
        "diffs": diffs,
        "diffsByClass": {
            cls: [row["key"] for row in diffs if row["class"] == cls]
            for cls in sorted({row["class"] for row in diffs})
        },
        "checks": {
            "freshDecodeMarkerMatch": meta["decode"]["markerMatch"],
            "freshKeyOrderEqualsS00Success": list(fd.keys()) == list(sd.keys()),
            "freshRejected": (meta["probe"].get("decoded") or {}).get("hasSuccessHandler") is False,
            "diffsOnlyTailSessionEpochOrStaleRisk": all(
                row["class"] in {"pow_wasm_tail", "session_or_cookie", "epoch_ms", "epoch_ms_list", "stale_literal_risk"}
                for row in diffs
            ),
        },
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.fresh_probe.stem}_full_field_diff.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "json": str(out),
        "checks": result["checks"],
        "diffCountVsS00Success": result["diffCountVsS00Success"],
        "diffsByClass": result["diffsByClass"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
