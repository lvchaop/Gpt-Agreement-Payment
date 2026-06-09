#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
COMPARE_JSON = REPO / "output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json"
CAPTCHA_D_FLOW_JSON = REPO / "output/protocol_reverse/source_offsets/captcha_d_flow_expressions.json"
POW_JSON = REPO / "output/protocol_reverse/pow_response/pow_response_ni109xdjp5zp_1780948211.json"
BUNDLE_MATCH_JSON = REPO / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
COLLECTOR_FIELD_MAP_JSON = REPO / "output/protocol_reverse/collector_field_map/collector_field_map.json"
OUT_DIR = REPO / "output/protocol_reverse/px561_protocol_inputs"


D_FLOW_NOTES = {
    "Bzt2fUFRcw==": "captcha D/Ts callback arg v; source assignment r[f(c(410,395))]=v",
    "OSkIb39DDA==": "captcha D/Ts callback arg e; POW value Ps; source assignment r[f(c(414,426))]=e",
    "Ew9iCVZjYDw=": "captcha D/Ts callback arg n; source assignment r[f(c(411,413))]=n",
    "XGRtYhkLbFM=": "captcha D/Ts callback Ks; source assignment r[f(c(415,422))]=Ks",
    "FU1kS1AhYX4=": "captcha D pre-submit pn/o field; source assignment pn(...[f(K(-174,-196))]=o...)",
    "VQ0kCxNgJz0=": "captcha D PX1200 pre-submit extra field; source assignment d[f(K(-185,-194))]=ke()",
    "TlJ/FAs7fSY=": "captcha D PX1200 deleted field; source has delete d[f(K(-158,-171))]",
    "V0smTREkJXc=": "captcha D pt input key; source uses r[f(K(-177,-178))] while building z",
    "usedWebWorkers": "captcha D worker count key; source decoded K(-165,-176)",
}

MAIN_TF_KEYS = {
    "RTE/ewNXNUA=": "tf() injects xt into every activity before payload encode",
    "O2sBIX4NDBQ=": "tf() injects eu() result when present",
    "AzN5eUVQckM=": "tf() injects Pr() result when present",
    "WQUjDxxjKjU=": "tf() injects Di() paired with Pr()",
    "GUVjT1wnbn4=": "tf() injects _px3 cookie value when present",
}

Yc_BASE_HINTS = {
    "VGBuahICYlE=": "Yc() base activity field; present in success and tf samples",
    "W0shQR0nJHc=": "Yc() base stack field; present in success and tf samples",
    "KVUTX285HW4=": "Yc() base pr() boolean field; present in success and tf samples",
    "DFg2Eko5PiQ=": "Yc() base visibility field; present in success and tf samples",
    "JVEfW2A0G2A=": "Yc() base encoded environment field; present in success and tf samples",
    "S3sxMQ0YNQo=": "Yc() base time/na field; present in success and tf samples",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def value_preview(value: Any, limit: int = 180) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 3] + "..."


def type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def load_d_flow() -> dict[str, dict[str, Any]]:
    data = read_json(CAPTCHA_D_FLOW_JSON)
    out: dict[str, dict[str, Any]] = {}
    for row in data["records"]:
        decoded = row.get("decoded")
        if decoded:
            out[decoded] = row
    return out


def load_bundle_match() -> dict[str, Any] | None:
    data = read_json(BUNDLE_MATCH_JSON)
    for req in data.get("requests", []):
        if req.get("requestLine") != 308:
            continue
        for activity in req.get("activitiesWithMatches", []):
            if activity.get("type") == "PX561":
                return {
                    "requestLine": req.get("requestLine"),
                    "seq": req.get("seq"),
                    "uuid": req.get("uuid"),
                    "markerQi": req.get("markerQi"),
                    "markerMatch": req.get("markerMatch"),
                    "activityIndex": activity.get("index"),
                    "matches": activity.get("matches", []),
                }
    return None


def classify_key(
    key: str,
    value: Any,
    *,
    missing_from_tf: bool,
    d_flow: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sources: list[str] = []
    gap = ""
    bucket = "unknown_or_unmapped_success_field"
    protocol_action = "需要继续定位 producer；不能在纯协议里凭空填"

    if key in d_flow:
        bucket = "captcha_d_flow_static"
        sources.append(f"captcha_d_flow_expressions.json: {d_flow[key]['expr']} -> {key} ({d_flow[key].get('note')})")
        protocol_action = "按 captcha D/Ts/POW 局部逻辑构造或传递该字段"
        gap = "需确认所有 sibling 字段的运行时输入来源" if key != "OSkIb39DDA==" else ""
    elif key in MAIN_TF_KEYS:
        bucket = "main_tf_injected"
        sources.append(MAIN_TF_KEYS[key])
        protocol_action = "由 collector protocol state/cookie state 注入，不属于 captcha D 原始对象"
    elif key in Yc_BASE_HINTS:
        bucket = "main_yc_base"
        sources.append(Yc_BASE_HINTS[key])
        protocol_action = "由 main Yc() 活动基础字段生成"
    elif missing_from_tf:
        bucket = "success_only_unmapped"
        sources.append("px561_compare_success_vs_tf_samples.json: success 有该 key，3 个 tf.payload 样本均缺失")
        protocol_action = "优先静态定位；该字段不能直接从 tf.payload 失败样本复用"
        gap = "缺静态 producer"
    else:
        bucket = "shared_runtime_field"
        sources.append("px561_compare_success_vs_tf_samples.json: success 与 tf.payload 样本共享该 key")
        protocol_action = "可先从同轮 runtime/tf 构造模板复用，再逐步静态替换"
        gap = "若要完全纯协议，仍需逐项静态定位"

    return {
        "key": key,
        "valueType": type_name(value),
        "successValuePreview": value_preview(value),
        "successOnlyMissingFromTfSamples": missing_from_tf,
        "bucket": bucket,
        "evidence": sources,
        "protocolAction": protocol_action,
        "gap": gap,
    }


def main() -> None:
    compare = read_json(COMPARE_JSON)
    d_flow = load_d_flow()
    pow_data = read_json(POW_JSON)
    bundle_match = load_bundle_match()
    collector_map = read_json(COLLECTOR_FIELD_MAP_JSON)
    success = compare["success"]
    success_d = success["activity"]["d"]
    missing_sets = [set(row["missingComparedToSuccess"]) for row in compare["comparisons"]]
    missing_all = set.intersection(*missing_sets) if missing_sets else set()

    fields = [
        classify_key(k, success_d[k], missing_from_tf=k in missing_all, d_flow=d_flow)
        for k in sorted(success_d)
    ]

    by_bucket: dict[str, list[dict[str, Any]]] = {}
    for row in fields:
        by_bucket.setdefault(row["bucket"], []).append(row)

    result = {
        "inputs": {
            "compare": str(COMPARE_JSON.relative_to(REPO)),
            "captchaDFlow": str(CAPTCHA_D_FLOW_JSON.relative_to(REPO)),
            "pow": str(POW_JSON.relative_to(REPO)),
            "bundleMatch": str(BUNDLE_MATCH_JSON.relative_to(REPO)),
            "collectorFieldMap": str(COLLECTOR_FIELD_MAP_JSON.relative_to(REPO)),
        },
        "success": {
            "source": success["source"],
            "line": success["line"],
            "seq": success.get("seq"),
            "fieldCount": success["fieldCount"],
            "state": success.get("state"),
            "powField": success.get("powField"),
            "pointerEventCount": success.get("pointerEventCount"),
            "motion150Count": success.get("motion150Count"),
            "motion600Count": success.get("motion600Count"),
        },
        "tfSamples": compare["comparisons"],
        "powEvidence": pow_data.get("results", []),
        "bundleEvidence": bundle_match,
        "collectorProtocolFields": collector_map.get("fields", []),
        "bucketCounts": {k: len(v) for k, v in sorted(by_bucket.items())},
        "fields": fields,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "px561_protocol_inputs_ni109_vs_tf.json"
    md_path = OUT_DIR / "px561_protocol_inputs_ni109_vs_tf.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# PX561 protocol input inventory: ni109 success vs tf samples",
        "",
        "## scope",
        "",
        "This artifact is an input inventory for pure-protocol construction. It does not prove end-to-end pure-protocol success.",
        "",
        "## source evidence",
        "",
    ]
    for name, path in result["inputs"].items():
        lines.append(f"- {name}: `{path}`")
    lines.extend([
        "",
        "## success activity",
        "",
        f"- source: `{success['source']}`",
        f"- line: `{success['line']}`",
        f"- seq: `{success.get('seq')}`",
        f"- fieldCount: `{success['fieldCount']}`",
        f"- state: `{success.get('state')}`",
        f"- powField: `{success.get('powField')}`",
        f"- pointer/motion counts: `{success.get('pointerEventCount')}` / `{success.get('motion150Count')}` / `{success.get('motion600Count')}`",
        "",
        "## bucket counts",
        "",
        "| bucket | count |",
        "|---|---:|",
    ])
    for bucket, count in sorted(result["bucketCounts"].items()):
        lines.append(f"| `{bucket}` | {count} |")
    lines.extend([
        "",
        "## proven POW chain",
        "",
    ])
    for row in result["powEvidence"]:
        lines.append(
            f"- raw `{row.get('raw')}` -> i `{row.get('i')}` -> value `{row.get('value')}` -> matchesTarget `{row.get('matchesTarget')}`"
        )
    if bundle_match:
        lines.extend([
            "",
            "## decoded bundle placement",
            "",
            f"- request line `{bundle_match['requestLine']}`, seq `{bundle_match['seq']}`, activity index `{bundle_match['activityIndex']}`, markerMatch `{bundle_match['markerMatch']}`",
        ])
        for match in bundle_match.get("matches", []):
            lines.append(f"- `{match.get('path')}` contains `{match.get('value')}`")

    lines.extend([
        "",
        "## fields",
        "",
        "| key | bucket | type | success-only vs tf | value preview | evidence | gap |",
        "|---|---|---|---|---|---|---|",
    ])
    for row in fields:
        evidence = "<br>".join(row["evidence"]).replace("|", "\\|")
        preview = row["successValuePreview"].replace("|", "\\|")
        lines.append(
            f"| `{row['key']}` | `{row['bucket']}` | {row['valueType']} | {row['successOnlyMissingFromTfSamples']} | "
            f"`{preview}` | {evidence} | {row['gap']} |"
        )

    lines.extend([
        "",
        "## next protocol requirement",
        "",
        "- The next pure-protocol step must build a fresh `PX561` activity whose `d.OSkIb39DDA==` is produced by the solved POW value, not copied from a prior successful request.",
        "- The collector body must then be encoded through the already mapped `tf -> Vs -> payload/pc` path and verified against live collector response.",
        "- This artifact does not yet prove `_px3/_pxde` update or Microsoft `risk/verify state=continue` without browser execution.",
    ])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(json_path), "md": str(md_path), "fieldCount": len(fields)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
