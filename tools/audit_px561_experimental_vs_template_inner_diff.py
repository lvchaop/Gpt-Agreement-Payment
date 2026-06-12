#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
CONSTRUCTOR = REPO / "output/protocol_reverse/px561_constructor/px561_pow_tail_constructor_audit.json"
J0_RUNTIME = REPO / "output/outlook_browser/runtime_trace_j0t8van4qyhm_1781119142.jsonl"
J0_DECODE = REPO / "output/protocol_reverse/bundle_payload_decode/bundle_payload_decode_j0t8van4qyhm_1781119142.json"
LIVE_PROBE = REPO / "output/protocol_reverse/px561_constructor/px561_experimental_live_probe_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"

REQUEST_LINE = 498
TARGET_KEYS = [
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "KVkYX28zG2o=",
    "Ew9iCVZkZD4=",
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


def read_jsonl_line(path: Path, line_no: int) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, 1):
            if idx == line_no:
                row = json.loads(line)
                row["_line"] = idx
                return row
    raise KeyError(f"line not found: {path}:{line_no}")


def shape(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
    return {
        "type": type(value).__name__,
        "len": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "preview": text[:120] + (f"...<len={len(text)}>" if len(text) > 120 else ""),
    }


def px_activity(activities: list[Any]) -> dict[str, Any]:
    for activity in activities:
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return activity
    raise RuntimeError("PX561 activity not found")


def activity_digest(activity: Any) -> dict[str, Any]:
    text = json.dumps(activity, ensure_ascii=False, separators=(",", ":"))
    return {
        "type": activity.get("t") if isinstance(activity, dict) else None,
        "dKeyCount": len((activity.get("d") or {}).keys()) if isinstance(activity, dict) and isinstance(activity.get("d"), dict) else None,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def decode_body(dec: Any, body: str, marker: str) -> dict[str, Any]:
    params = dec.parse_form(body)
    decoded = dec.decode_payload(params["payload"], marker, params["uuid"])
    activities = decoded["json"] if isinstance(decoded.get("json"), list) else []
    px = px_activity(activities)
    d = px["d"]
    keys = list(d.keys())
    return {
        "params": params,
        "decode": {
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "activityTypes": [item.get("t") for item in activities if isinstance(item, dict)],
            "activityDigests": [activity_digest(item) for item in activities],
            "activityCount": len(activities),
        },
        "px": {
            "fieldCount": len(keys),
            "keys": keys,
            "keysSha256": hashlib.sha256(json.dumps(keys, ensure_ascii=False).encode()).hexdigest(),
            "target": {
                key: {
                    "present": key in d,
                    "index": keys.index(key) if key in d else None,
                    "value": d.get(key),
                    "shape": shape(d[key]) if key in d else None,
                }
                for key in TARGET_KEYS
            },
            "allValuesSha256": hashlib.sha256(
                json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        },
    }


def changed_keys(template_px: dict[str, Any], experimental_px: dict[str, Any]) -> list[dict[str, Any]]:
    t_keys = template_px["keys"]
    e_keys = experimental_px["keys"]
    out = []
    for key in t_keys:
        t_val = template_px["target"].get(key, {}).get("value") if key in TARGET_KEYS else None
        if key not in e_keys:
            out.append({"key": key, "change": "removed", "templateIndex": t_keys.index(key), "experimentalIndex": None})
            continue
        # Use target map for target keys; for non-target keys compare via raw values is not stored to keep output compact.
    for key in e_keys:
        if key not in t_keys:
            out.append({"key": key, "change": "added", "templateIndex": None, "experimentalIndex": e_keys.index(key)})
    return out


def main() -> int:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    constructor = read_json(CONSTRUCTOR)
    marker_row = next(row for row in read_json(J0_DECODE)["rows"] if row["requestLine"] == REQUEST_LINE)
    runtime_row = read_jsonl_line(J0_RUNTIME, REQUEST_LINE)
    template_body = runtime_row["post_data"]
    experimental_body = constructor["experimental"]["body"]

    template = decode_body(dec, template_body, marker_row["marker"])
    experimental = decode_body(dec, experimental_body, marker_row["marker"])
    target_diffs = {}
    for key in TARGET_KEYS:
        tv = template["px"]["target"][key]
        ev = experimental["px"]["target"][key]
        target_diffs[key] = {
            "samePresence": tv["present"] == ev["present"],
            "sameIndex": tv["index"] == ev["index"],
            "sameType": (tv["shape"] or {}).get("type") == (ev["shape"] or {}).get("type"),
            "sameLen": (tv["shape"] or {}).get("len") == (ev["shape"] or {}).get("len"),
            "sameSha256": (tv["shape"] or {}).get("sha256") == (ev["shape"] or {}).get("sha256"),
            "template": tv,
            "experimental": ev,
        }

    checks = {
        "bothMarkerMatch": template["decode"]["markerMatch"] is True and experimental["decode"]["markerMatch"] is True,
        "bothJsonDecode": template["decode"]["jsonError"] is None and experimental["decode"]["jsonError"] is None,
        "sameActivityTypes": template["decode"]["activityTypes"] == experimental["decode"]["activityTypes"],
        "sameActivityCount": template["decode"]["activityCount"] == experimental["decode"]["activityCount"],
        "samePxKeySet": set(template["px"]["keys"]) == set(experimental["px"]["keys"]),
        "samePxKeyOrder": template["px"]["keys"] == experimental["px"]["keys"],
        "samePxFieldCount": template["px"]["fieldCount"] == experimental["px"]["fieldCount"],
        "allTargetIndexesSame": all(v["sameIndex"] for v in target_diffs.values()),
        "onlyExpectedTargetValuesDiffer": all(
            target_diffs[key]["sameSha256"] is False if key in {"TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="} else True
            for key in TARGET_KEYS
        ),
        "liveProbeStillFails": read_json(LIVE_PROBE)["liveResponse"].get("handlerStatus") == "failure",
    }
    result = {
        "purpose": "Compare the current experimental fresh-TBR9 PX561 inner payload against its same-run j0t8 accepted template at /assets/js/bundle line 498.",
        "evidenceFiles": {
            "constructor": str(CONSTRUCTOR),
            "runtimeTemplate": f"{J0_RUNTIME}:{REQUEST_LINE}",
            "j0Decode": str(J0_DECODE),
            "liveProbeAudit": str(LIVE_PROBE),
        },
        "outerFormComparison": {
            "sameUuid": template["params"].get("uuid") == experimental["params"].get("uuid"),
            "sameSeq": template["params"].get("seq") == experimental["params"].get("seq"),
            "templatePc": template["params"].get("pc"),
            "experimentalPc": experimental["params"].get("pc"),
            "samePc": template["params"].get("pc") == experimental["params"].get("pc"),
            "sameCs": template["params"].get("cs") == experimental["params"].get("cs"),
            "sameSid": template["params"].get("sid") == experimental["params"].get("sid"),
            "sameVid": template["params"].get("vid") == experimental["params"].get("vid"),
            "sameCts": template["params"].get("cts") == experimental["params"].get("cts"),
        },
        "decodeComparison": {
            "template": template["decode"],
            "experimental": experimental["decode"],
        },
        "pxComparison": {
            "templateFieldCount": template["px"]["fieldCount"],
            "experimentalFieldCount": experimental["px"]["fieldCount"],
            "sameKeyOrder": template["px"]["keys"] == experimental["px"]["keys"],
            "sameAllValuesSha256": template["px"]["allValuesSha256"] == experimental["px"]["allValuesSha256"],
            "targetDiffs": target_diffs,
            "addedRemovedKeys": changed_keys(template["px"], experimental["px"]),
        },
        "checks": checks,
        "conclusion": (
            "The experimental body and its same-run j0t8 template decode with the same marker, activity types, PX561 key set, PX561 key order, and target indexes. "
            "The live failure therefore is not explained by inner activity shape. The decisive remaining evidence is value coupling: which dynamic target/non-target values are safe to replace across sessions and which must be generated coherently from the same collector/session state."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_experimental_vs_template_inner_diff.json"
    out_md = OUT_DIR / "px561_experimental_vs_template_inner_diff.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# PX561 experimental vs template inner diff", "", "## Checks", ""]
    lines.extend(f"- {key}: `{value}`" for key, value in checks.items())
    lines += [
        "",
        "## Outer form",
        "",
        *[f"- {key}: `{value}`" for key, value in result["outerFormComparison"].items()],
        "",
        "## Target diffs",
        "",
        "| key | same index | same type | same len | same sha256 | template | experimental |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for key in TARGET_KEYS:
        diff = target_diffs[key]
        tprev = ((diff["template"].get("shape") or {}).get("preview") or "")
        eprev = ((diff["experimental"].get("shape") or {}).get("preview") or "")
        lines.append(
            f"| `{key}` | {diff['sameIndex']} | {diff['sameType']} | {diff['sameLen']} | {diff['sameSha256']} | `{tprev}` | `{eprev}` |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
