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

TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "Ew9iCVZkZD4=",
    "KVkYX28zG2o=",
    "DzN+dUlTekE=",
    "GUloT18mZ3U=",
    "JnpXfGMUUUc=",
    "LVUcU2s1Gmc=",
]


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


def px_activity(activities: list[Any]) -> tuple[int, dict[str, Any]]:
    for idx, activity in enumerate(activities):
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return idx, activity
    raise RuntimeError("PX561 activity not found")


def value_digest(value: Any) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    shape_len = len(value) if isinstance(value, (str, list, dict)) else None
    return {
        "type": type(value).__name__,
        "length": shape_len,
        "sha256": hashlib.sha256(str(text).encode("utf-8")).hexdigest(),
        "preview": str(text)[:160] + (f"...<len={len(str(text))}>" if len(str(text)) > 160 else ""),
    }


def summarize(source: dict[str, Any], activities: list[Any]) -> dict[str, Any]:
    idx, px = px_activity(activities)
    d = px.get("d") or {}
    keys = list(d.keys())
    return {
        **source,
        "activityIndex": idx,
        "fieldCount": len(keys),
        "keys": keys,
        "targets": {
            key: {
                "present": key in d,
                "index": keys.index(key) if key in d else None,
                "value": d.get(key),
                "digest": value_digest(d[key]) if key in d else None,
            }
            for key in TARGET_KEYS
        },
    }


def extract_s00_tf(line_no: int, label: str) -> dict[str, Any]:
    for row in read_jsonl(JS_TRACE):
        if row["_line"] == line_no and row.get("kind") == "hsprotect.main.tf.payload":
            data = row.get("data") or {}
            return summarize(
                {
                    "label": label,
                    "source": "s00 js_internal_trace tf.payload",
                    "evidenceFile": str(JS_TRACE),
                    "sourceLine": line_no,
                    "meta": data.get("meta"),
                },
                data.get("activities") or [],
            )
    raise RuntimeError(f"s00 tf payload line {line_no} not found")


def extract_fresh(path: Path) -> dict[str, Any]:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    doc = read_json(path)
    material = doc["material"]
    params = parse_form(material["body"])
    decoded = dec.decode_payload(params["payload"], material["meta"]["marker"], params["uuid"])
    activities = decoded.get("json") if isinstance(decoded.get("json"), list) else []
    out = summarize(
        {
            "label": "fresh_probe",
            "source": "fresh_px561_probe decoded payload",
            "evidenceFile": str(path),
            "sourceLine": None,
            "request": {
                "seq": params.get("seq"),
                "rsc": params.get("rsc"),
                "uuid": params.get("uuid"),
                "ci": params.get("ci"),
                "pc": params.get("pc"),
                "bodySha256": material.get("bodySha256"),
                "sent": doc.get("sent"),
                "status": (doc.get("response") or {}).get("status"),
                "handlers": (doc.get("decoded") or {}).get("handlers"),
            },
            "decode": {
                "markerMatch": decoded.get("markerMatch"),
                "byteEncoding": decoded.get("byteEncoding"),
                "jsonError": decoded.get("jsonError"),
            },
            "materialMeta": material.get("meta"),
        },
        activities,
    )
    return out


def compare(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    return {
        "against": other["label"],
        "sameKeySet": set(base["keys"]) == set(other["keys"]),
        "sameKeyOrder": base["keys"] == other["keys"],
        "fieldCountDelta": base["fieldCount"] - other["fieldCount"],
        "target": {
            key: {
                "samePresence": base["targets"][key]["present"] == other["targets"][key]["present"],
                "sameIndex": base["targets"][key]["index"] == other["targets"][key]["index"],
                "sameValue": base["targets"][key]["value"] == other["targets"][key]["value"],
                "sameDigest": (base["targets"][key]["digest"] or {}).get("sha256")
                == (other["targets"][key]["digest"] or {}).get("sha256"),
                "fresh": base["targets"][key],
                "other": other["targets"][key],
            }
            for key in TARGET_KEYS
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare a fresh PX561 failure payload with s00 PX561 trace payloads.")
    parser.add_argument("fresh_probe", type=Path)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    fresh = extract_fresh(args.fresh_probe)
    s00_fail = extract_s00_tf(566, "s00_line566_failure_px561")
    s00_success = extract_s00_tf(922, "s00_line922_success_px561")
    result = {
        "purpose": "Classify which PX561 fields in the fresh failed probe are fresh, copied, or still divergent from accepted s00 success/failure trace payloads.",
        "freshProbe": fresh,
        "references": [s00_fail, s00_success],
        "comparisons": [compare(fresh, s00_fail), compare(fresh, s00_success)],
        "checks": {
            "freshDecodeMarkerMatch": fresh["decode"]["markerMatch"],
            "freshCollectorReturnedFailure": fresh["request"]["handlers"] and "oIIoIooo" in fresh["request"]["handlers"],
            "freshSameKeyOrderAsTemplateFailure": fresh["keys"] == s00_fail["keys"],
            "freshSameKeyOrderAsS00Success": fresh["keys"] == s00_success["keys"],
            "ew9iCopiedFromTemplateFailure": fresh["targets"]["Ew9iCVZkZD4="]["value"] == s00_fail["targets"]["Ew9iCVZkZD4="]["value"],
            "kvkCopiedFromTemplateFailure": fresh["targets"]["KVkYX28zG2o="]["value"] == s00_fail["targets"]["KVkYX28zG2o="]["value"],
            "behaviorArraysCopiedFromTemplateFailure": all(
                fresh["targets"][key]["value"] == s00_fail["targets"][key]["value"]
                for key in ["DzN+dUlTekE=", "GUloT18mZ3U=", "JnpXfGMUUUc="]
            ),
            "tailDivergesFromTemplateFailure": any(
                fresh["targets"][key]["value"] != s00_fail["targets"][key]["value"]
                for key in ["AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="]
            ),
            "tailDivergesFromS00Success": any(
                fresh["targets"][key]["value"] != s00_success["targets"][key]["value"]
                for key in ["AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="]
            ),
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_json = args.out_dir / f"{args.fresh_probe.stem}_diff_vs_s00.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
