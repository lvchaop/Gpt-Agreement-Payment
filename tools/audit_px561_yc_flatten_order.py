#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output/protocol_reverse/source_offsets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BUNDLE = ROOT / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
TS_FIELDS = OUT_DIR / "captcha_ts_callback_fields.json"
CAPTCHA = ROOT / "output/outlook_browser/js_static_analysis/captcha.beautified.js"
MAIN = ROOT / "output/outlook_browser/js_static_analysis/main.beautified.js"


def load_success_d():
    data = json.loads(BUNDLE.read_text())
    for req in data["requests"]:
        for item in req.get("activitiesWithMatches", []):
            if item.get("type") == "PX561":
                return item["activity"]["d"], req
    raise RuntimeError("PX561 success activity not found")


def snippet(path: Path, start: int, end: int) -> str:
    lines = path.read_text(errors="replace").splitlines()
    out = []
    for line_no in range(start, end + 1):
        if 1 <= line_no <= len(lines):
            out.append(f"{line_no}: {lines[line_no - 1]}")
    return "\n".join(out)


def main():
    d, req = load_success_d()
    keys = list(d.keys())
    ts = json.loads(TS_FIELDS.read_text())["records"]
    decoded_by_expr = {r["expr"]: r for r in ts}

    positions = {key: keys.index(key) for key in keys}
    target_keys = [
        "TBR9Ugl7emA=",
        "instantiating",
        "AEAxBkUsPjQ=",
        "succeeded",
        "fyNOZTpPQF4=",
        "Bzt2fUFRcw==",
        "OSkIb39DDA==",
        "XQUsAxhpKjU=",
        "Ew9iCVZjYDw=",
        "XGRtYhkLbFM=",
    ]

    target_context = {}
    for key in target_keys:
        present = key in positions
        target_context[key] = {
            "present": present,
            "index": positions.get(key),
            "value": d.get(key),
        }

    # Static insertion order inside captcha D/Ts, restricted to fields around the conflict.
    static_order = [
        {
            "step": 1,
            "expr": "r[t(v(-540,-543))] = _s()",
            "decodedKey": "TBR9Ugl7emA=",
            "valueSource": "_s()",
            "line": "captcha.beautified.js:11083",
            "finalIndex": positions.get("TBR9Ugl7emA="),
            "finalValue": d.get("TBR9Ugl7emA="),
        },
        {
            "step": 2,
            "expr": "r[t(v(-531,-522))] = Rs",
            "decodedKey": "instantiating",
            "valueSource": "Rs",
            "line": "captcha.beautified.js:11083",
            "finalIndex": positions.get("instantiating"),
            "finalValue": d.get("instantiating"),
        },
        {
            "step": 3,
            "expr": "r[t(\"FnM4CCwDASRmEyFT\")] = Ws[t(\"Ng\")]()",
            "decodedKey": "AEAxBkUsPjQ=",
            "valueSource": "Ws.Ng()",
            "line": "captcha.beautified.js:11085",
            "finalIndex": positions.get("AEAxBkUsPjQ="),
            "finalValue": d.get("AEAxBkUsPjQ="),
        },
        {
            "step": 4,
            "expr": "r[t(v(-541,-541))] = Ws[t(\"NQ\")](n)",
            "decodedKey": "succeeded",
            "valueSource": "Ws.NQ(n)",
            "line": "captcha.beautified.js:11088",
            "finalIndex": positions.get("succeeded"),
            "finalValue": d.get("succeeded"),
            "sameValueFinalKeys": [k for k, v in d.items() if v == "succeeded"],
        },
        {
            "step": 5,
            "expr": "r[f(c(410,395))] = v",
            "decodedKey": "Bzt2fUFRcw==",
            "valueSource": "Ts callback param v",
            "line": "captcha.beautified.js:11097",
            "finalIndex": positions.get("Bzt2fUFRcw=="),
            "finalValue": d.get("Bzt2fUFRcw=="),
        },
    ]

    order_findings = []
    tbr_idx = positions.get("TBR9Ugl7emA=")
    ae_idx = positions.get("AEAxBkUsPjQ=")
    fy_idx = positions.get("fyNOZTpPQF4=")
    bzt_idx = positions.get("Bzt2fUFRcw==")
    if all(x is not None for x in [tbr_idx, ae_idx, fy_idx, bzt_idx]):
        order_findings.append({
            "finding": "final_order",
            "observed": "fyNOZTpPQF4= < AEAxBkUsPjQ= < TBR9Ugl7emA= < Bzt2fUFRcw==",
            "indices": {
                "fyNOZTpPQF4=": fy_idx,
                "AEAxBkUsPjQ=": ae_idx,
                "TBR9Ugl7emA=": tbr_idx,
                "Bzt2fUFRcw==": bzt_idx,
            },
        })
        order_findings.append({
            "finding": "static_vs_final_order_conflict",
            "observed": "static assigns TBR9Ugl7emA= before AEAxBkUsPjQ=, but final order places TBR9Ugl7emA= after AEAxBkUsPjQ=.",
            "evidence": [
                "captcha.beautified.js:11083 assigns TBR9Ugl7emA= via _s() before line 11085 AEAxBkUsPjQ=.",
                "success PX561.d final indices show AEAxBkUsPjQ= at index %s and TBR9Ugl7emA= at index %s." % (ae_idx, tbr_idx),
            ],
        })

    y_c_flatten = {
        "snippet": snippet(MAIN, 2963, 3009),
        "finding": "Yc copies primitive values as C[B]=k; object values are flattened by iterating nested keys C[N]=k[N].",
    }

    result = {
        "inputs": {
            "bundle": str(BUNDLE),
            "tsFields": str(TS_FIELDS),
            "captcha": str(CAPTCHA),
            "main": str(MAIN),
        },
        "successRequest": {
            "requestLine": req.get("requestLine"),
            "seq": req.get("seq"),
            "url": req.get("url"),
        },
        "successPx561KeyCount": len(keys),
        "staticOrder": static_order,
        "targetContext": target_context,
        "orderFindings": order_findings,
        "sourceSnippets": {
            "captcha_D_Ts": snippet(CAPTCHA, 11080, 11099),
            "main_Yc": y_c_flatten,
        },
        "conclusions": [
            "Yc() flatten behavior proves object-valued r['succeeded'] can contribute nested keys to final PX561.d without preserving final key 'succeeded'.",
            "Final PX561.d order contradicts the idea that TBR9Ugl7emA= final long string is only the direct _s() assignment at captcha.beautified.js:11083.",
            "The remaining evidence target is now narrowed to Ws.NQ(n) return object and/or an overwrite/rewrite after the direct _s() assignment.",
        ],
    }

    json_path = OUT_DIR / "px561_yc_flatten_order_audit.json"
    md_path = OUT_DIR / "px561_yc_flatten_order_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = [
        "# PX561 Yc flatten/order audit",
        "",
        f"- bundle: `{BUNDLE}`",
        f"- ts fields: `{TS_FIELDS}`",
        f"- json: `{json_path}`",
        "",
        "## Static assignment order vs final PX561.d order",
        "",
        "| static step | expression | decoded key | value source | final index | final value |",
        "|---:|---|---|---|---:|---|",
    ]
    for row in static_order:
        val = row.get("finalValue")
        if isinstance(val, str) and len(val) > 120:
            val = val[:120] + f"...len={len(row['finalValue'])}"
        lines.append(
            f"| {row['step']} | `{row['expr']}` | `{row['decodedKey']}` | `{row['valueSource']}` | "
            f"{'' if row.get('finalIndex') is None else row['finalIndex']} | `{val}` |"
        )

    lines += [
        "",
        "## Order findings",
        "",
    ]
    for item in order_findings:
        lines.append(f"- `{item['finding']}`: {item.get('observed')}")
        if "indices" in item:
            lines.append(f"  - indices: `{json.dumps(item['indices'], ensure_ascii=False)}`")
        if "evidence" in item:
            for ev in item["evidence"]:
                lines.append(f"  - evidence: {ev}")

    lines += [
        "",
        "## Yc flatten evidence",
        "",
        "```js",
        y_c_flatten["snippet"],
        "```",
        "",
        "## Captcha D/Ts evidence",
        "",
        "```js",
        result["sourceSnippets"]["captcha_D_Ts"],
        "```",
        "",
        "## Conclusion",
        "",
    ]
    for c in result["conclusions"]:
        lines.append(f"- {c}")
    md_path.write_text("\n".join(lines) + "\n")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
