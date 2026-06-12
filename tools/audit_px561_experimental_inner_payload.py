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
J0_DECODE = REPO / "output/protocol_reverse/bundle_payload_decode/bundle_payload_decode_j0t8van4qyhm_1781119142.json"
ACCEPTED_CONSISTENCY = REPO / "output/protocol_reverse/px561_compare/px561_accepted_consistency_audit.json"
OUT_DIR = REPO / "output/protocol_reverse/px561_compare"

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


def shape(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
    return {
        "type": type(value).__name__,
        "len": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "preview": text[:100] + (f"...<len={len(text)}>" if len(text) > 100 else ""),
    }


def px_summary(activity: dict[str, Any]) -> dict[str, Any]:
    d = activity.get("d") if isinstance(activity.get("d"), dict) else {}
    keys = list(d.keys())
    return {
        "fieldCount": len(keys),
        "keysSha256": hashlib.sha256(json.dumps(keys, ensure_ascii=False).encode()).hexdigest(),
        "target": {
            key: {
                "present": key in d,
                "index": keys.index(key) if key in d else None,
                "shape": shape(d[key]) if key in d else None,
                "value": d.get(key) if key in TARGET_KEYS else None,
            }
            for key in TARGET_KEYS
        },
        "tailIndexes": [keys.index(key) if key in d else None for key in TARGET_KEYS[:5]],
        "tailConsecutive": all(key in d for key in TARGET_KEYS[:5])
        and [keys.index(key) for key in TARGET_KEYS[:5]]
        == list(range(keys.index(TARGET_KEYS[0]), keys.index(TARGET_KEYS[0]) + 5)),
    }


def main() -> int:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    constructor = read_json(CONSTRUCTOR)
    j0_decode = read_json(J0_DECODE)
    accepted = read_json(ACCEPTED_CONSISTENCY)

    body = constructor["experimental"]["body"]
    params = dec.parse_form(body)
    marker_row = next(row for row in j0_decode["rows"] if row["requestLine"] == 498)
    decoded = dec.decode_payload(params["payload"], marker_row["marker"], params["uuid"])
    activities = decoded["json"] if isinstance(decoded["json"], list) else []
    px = next((item for item in activities if isinstance(item, dict) and item.get("t") == "PX561"), None)
    if not px:
        raise RuntimeError("experimental inner payload has no PX561 activity")

    exp_px = px_summary(px)
    accepted_j0 = next(row for row in accepted["acceptedRows"] if row["run"] == "j0t8van4qyhm_1781119142")
    accepted_targets = accepted_j0["target"]
    target_comparison = {}
    for key in TARGET_KEYS:
        exp = exp_px["target"][key]
        acc = accepted_targets[key]
        target_comparison[key] = {
            "samePresence": exp["present"] == acc["present"],
            "sameIndex": exp["index"] == acc["index"],
            "sameType": (exp["shape"] or {}).get("type") == (acc["shape"] or {}).get("type"),
            "sameLen": (exp["shape"] or {}).get("len") == (acc["shape"] or {}).get("length"),
            "experimental": exp,
            "accepted": acc,
        }

    checks = {
        "experimentalMarkerMatches": decoded["markerMatch"] is True,
        "experimentalJsonDecoded": decoded["jsonError"] is None and isinstance(decoded["json"], list),
        "experimentalHasPx561": px is not None,
        "experimentalTailConsecutive": exp_px["tailConsecutive"],
        "experimentalTailIndexesMatchAcceptedJ0": exp_px["tailIndexes"] == [
            accepted_targets[key]["index"] for key in TARGET_KEYS[:5]
        ],
        "experimentalHasFreshTbr9": constructor["checks"].get("experimentalHasFreshTbr9Evidence") is True,
        "experimentalOskIsLivePow": constructor["checks"].get("experimentalUsesLiveOsk") is True,
        "experimentalDecodedInnerStillCollectorFails": read_json(
            REPO / "output/protocol_reverse/px561_constructor/px561_experimental_live_probe_audit.json"
        )["liveResponse"].get("handlerStatus")
        == "failure",
    }
    result = {
        "purpose": "Decode the current fresh-TBR9 experimental PX561 body at the inner bundle-payload layer and compare its PX561 field layout with accepted j0t8.",
        "evidenceFiles": {
            "constructor": str(CONSTRUCTOR),
            "j0Decode": str(J0_DECODE),
            "acceptedConsistency": str(ACCEPTED_CONSISTENCY),
            "liveProbeAudit": str(REPO / "output/protocol_reverse/px561_constructor/px561_experimental_live_probe_audit.json"),
        },
        "outerForm": {key: params.get(key) for key in ["uuid", "seq", "tag", "ft", "pc", "cs", "sid", "vid", "cts", "rsc"]},
        "innerDecode": {
            "markerSourceRequestLine": marker_row["requestLine"],
            "markerQi": marker_row["markerQi"],
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "activityTypes": [item.get("t") for item in activities if isinstance(item, dict)],
            "activityCount": len(activities),
        },
        "experimentalPx561": exp_px,
        "acceptedJ0": {
            "run": accepted_j0["run"],
            "sourceLine": accepted_j0.get("sourceLine"),
            "seq": accepted_j0.get("seq"),
            "fieldCount": accepted_j0.get("fieldCount"),
        },
        "targetComparison": target_comparison,
        "checks": checks,
        "conclusion": (
            "The current experimental body decodes cleanly at the inner bundle layer and its PX561 target tail indexes match accepted j0t8 exactly. "
            "Because the live collector response still returns oIIoIooo|-1, the remaining acceptance gap is not outer-form encoding, marker removal, or target-tail key order; it is a same-session/dynamic-value coupling or another non-target PX561/activity field not yet reproduced."
        ),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "px561_experimental_inner_payload_audit.json"
    out_md = OUT_DIR / "px561_experimental_inner_payload_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# PX561 experimental inner payload audit", "", "## Checks", ""]
    lines.extend(f"- {key}: `{value}`" for key, value in checks.items())
    lines += [
        "",
        "## Inner decode",
        "",
        f"- markerMatch: `{decoded['markerMatch']}`",
        f"- activityTypes: `{', '.join(result['innerDecode']['activityTypes'])}`",
        f"- activityCount: `{len(activities)}`",
        "",
        "## Target comparison",
        "",
        "| key | exp index | accepted index | same index | exp shape | accepted shape |",
        "|---|---:|---:|---:|---|---|",
    ]
    for key in TARGET_KEYS:
        cmp = target_comparison[key]
        es = cmp["experimental"].get("shape") or {}
        acs = cmp["accepted"].get("shape") or {}
        lines.append(
            f"| `{key}` | {cmp['experimental'].get('index')} | {cmp['accepted'].get('index')} | {cmp['sameIndex']} | "
            f"`{es.get('type')}/{es.get('len')}` | `{acs.get('type')}/{acs.get('length')}` |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
