#!/usr/bin/env python3
import base64
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output/protocol_reverse/source_offsets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TS_FIELDS = OUT_DIR / "captcha_ts_callback_fields.json"
BUNDLE_MATCHES = ROOT / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
CAPTCHA_SOURCE = ROOT / "output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js"
CAPTCHA_BEAUTIFIED = ROOT / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
MAIN_BEAUTIFIED = ROOT / "output/outlook_browser/js_static_analysis/main.beautified.js"


TARGET_KEYS = [
    "TBR9Ugl7emA=",
    "AEAxBkUsPjQ=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "XQUsAxhpKjU=",
    "Ew9iCVZjYDw=",
    "XGRtYhkLbFM=",
    "fyNOZTpPQF4=",
    "succeeded",
    "instantiating",
]


def global_u(encoded: str):
    key = b"W6ypnhT"
    try:
        padded = encoded + "=" * ((4 - len(encoded) % 4) % 4)
        raw = base64.b64decode(padded, validate=False)
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode("latin1")
    except Exception:
        return None


def load_success_d() -> dict:
    data = json.loads(BUNDLE_MATCHES.read_text())
    for req in data["requests"]:
        for item in req.get("activitiesWithMatches", []):
            if item.get("type") == "PX561":
                return item["activity"]["d"]
    raise RuntimeError("PX561 success activity not found")


def find_string_hits(path: Path) -> list[dict]:
    text = path.read_text(errors="replace")
    hits = []
    for m in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text):
        try:
            literal = json.loads('"' + m.group(1) + '"')
        except Exception:
            literal = m.group(1)
        if literal in TARGET_KEYS:
            hits.append({"file": str(path), "offset": m.start(), "mode": "literal", "literal": literal, "decoded": literal})
        decoded = global_u(literal)
        if decoded in TARGET_KEYS:
            hits.append({"file": str(path), "offset": m.start(), "mode": "globalU", "literal": literal, "decoded": decoded})
    return hits


def context_for_key(keys: list[str], d: dict, key: str, radius: int = 4) -> dict:
    if key not in d:
        return {"present": False}
    idx = keys.index(key)
    window = []
    for i in range(max(0, idx - radius), min(len(keys), idx + radius + 1)):
        v = d[keys[i]]
        if isinstance(v, str) and len(v) > 180:
            v = v[:180] + f"...len={len(v)}"
        window.append({"index": i, "key": keys[i], "value": v})
    value = d[key]
    if isinstance(value, str) and len(value) > 240:
        value = value[:240] + f"...len={len(value)}"
    return {"present": True, "index": idx, "value": value, "window": window}


def main() -> None:
    ts = json.loads(TS_FIELDS.read_text())
    d = load_success_d()
    keys = list(d.keys())

    ts_presence = []
    for rec in ts["records"]:
        decoded = rec.get("decoded")
        row = {
            "expr": rec.get("expr"),
            "raw": rec.get("raw"),
            "decoded": decoded,
            "valueExpr": rec.get("valueExpr"),
            "lineRef": rec.get("lineRef"),
            "presentInFinalPx561": decoded in d,
            "finalValue": d.get(decoded) if decoded in d else None,
            "sameValueFinalKeys": [k for k, v in d.items() if v == decoded],
        }
        if isinstance(row["finalValue"], str) and len(row["finalValue"]) > 240:
            row["finalValue"] = row["finalValue"][:240] + f"...len={len(d[decoded])}"
        ts_presence.append(row)

    target_context = {k: context_for_key(keys, d, k) for k in TARGET_KEYS}
    string_hits = []
    for path in [CAPTCHA_SOURCE, CAPTCHA_BEAUTIFIED, MAIN_BEAUTIFIED]:
        if path.exists():
            string_hits.extend(find_string_hits(path))

    result = {
        "successBundle": str(BUNDLE_MATCHES),
        "tsFields": str(TS_FIELDS),
        "successPx561KeyCount": len(d),
        "tsPresence": ts_presence,
        "targetContext": target_context,
        "stringHits": string_hits,
        "conclusions": [
            "Ts callback decoded key succeeded is absent from final PX561.d, but final key fyNOZTpPQF4= has value succeeded.",
            "Yc() evidence must be combined with a key-layer audit before treating Ts local decoded keys as final payload keys.",
            "TBR9Ugl7emA= remains present in final PX561.d with a long string value, while Ts static expression still maps it to _s() boolean.",
        ],
    }

    json_path = OUT_DIR / "px561_ts_key_layer_audit.json"
    md_path = OUT_DIR / "px561_ts_key_layer_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = [
        "# PX561 Ts key-layer audit",
        "",
        f"- success bundle: `{BUNDLE_MATCHES}`",
        f"- Ts decoded fields: `{TS_FIELDS}`",
        f"- success PX561.d key count: `{len(d)}`",
        "",
        "## Ts decoded key presence in final PX561.d",
        "",
        "| expr | decoded key | value expr | present in final | final value | final keys with value == decoded |",
        "|---|---|---|---|---|---|",
    ]
    for row in ts_presence:
        final_value = row["finalValue"]
        if isinstance(final_value, (dict, list)):
            final_value = json.dumps(final_value, ensure_ascii=False)
        lines.append(
            f"| `{row['expr']}` | `{row['decoded']}` | `{row['valueExpr']}` | "
            f"{row['presentInFinalPx561']} | `{final_value}` | `{', '.join(row['sameValueFinalKeys'])}` |"
        )

    lines += ["", "## Target key context in final PX561.d", ""]
    for key, ctx in target_context.items():
        lines.append(f"### `{key}`")
        if not ctx["present"]:
            lines.append("- not present")
            continue
        lines.append(f"- index: `{ctx['index']}`")
        lines.append(f"- value: `{ctx['value']}`")
        lines.append("")
        lines.append("| index | key | value |")
        lines.append("|---:|---|---|")
        for item in ctx["window"]:
            val = item["value"]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=False)
            lines.append(f"| {item['index']} | `{item['key']}` | `{val}` |")
        lines.append("")

    lines += [
        "## Static string hits",
        "",
        "| file | offset | mode | literal | decoded |",
        "|---|---:|---|---|---|",
    ]
    for hit in string_hits:
        lines.append(f"| `{hit['file']}` | {hit['offset']} | {hit['mode']} | `{hit['literal']}` | `{hit['decoded']}` |")

    lines += [
        "",
        "## Evidence conclusion",
        "",
        "- `succeeded` 作为 Ts callback 局部 decoded key 不存在于 final `PX561.d` key 集合。",
        "- final `PX561.d` 中 `fyNOZTpPQF4=` 的 value 是 `succeeded`，说明不能把 Ts 局部 key 直接等同于最终 payload key。",
        "- `TBR9Ugl7emA=` 在 final `PX561.d` 中仍为长字符串；与 Ts 静态表达式 `_s() boolean` 的冲突仍未闭合。",
    ]
    md_path.write_text("\n".join(lines) + "\n")
    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
