#!/usr/bin/env python3
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output/protocol_reverse/source_offsets"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUCCESS_BUNDLE = ROOT / "output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json"
TF_TRACES = [
    ROOT / "output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl",
    ROOT / "output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl",
    ROOT / "output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl",
]

TARGET_KEYS = [
    "bHQdcikYH0Q=",
    "fyNOZTpPQF4=",
    "AEAxBkUsPjQ=",
    "TBR9Ugl7emA=",
    "Bzt2fUFRcw==",
    "OSkIb39DDA==",
    "XQUsAxhpKjU=",
    "Ew9iCVZjYDw=",
    "XGRtYhkLbFM=",
]


def preview(v):
    if isinstance(v, str) and len(v) > 140:
        return v[:140] + f"...len={len(v)}"
    return v


def load_success_px561():
    data = json.loads(SUCCESS_BUNDLE.read_text())
    for req in data["requests"]:
        for item in req.get("activitiesWithMatches", []):
            if item.get("type") == "PX561":
                return {
                    "source": str(SUCCESS_BUNDLE),
                    "sourceKind": "collector.bundle.decoded",
                    "line": req.get("requestLine"),
                    "seq": req.get("seq"),
                    "activity": item["activity"],
                }
    raise RuntimeError("success PX561 not found")


def load_tf_px561(path: Path):
    for line_no, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if '"kind": "hsprotect.main.tf.payload"' not in line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        for activity in ev.get("data", {}).get("activities", []):
            if activity.get("t") == "PX561":
                return {
                    "source": str(path),
                    "sourceKind": "js_internal_trace.tf.payload",
                    "line": line_no,
                    "seq": None,
                    "activity": activity,
                }
    raise RuntimeError(f"PX561 tf.payload not found in {path}")


def summarize(record):
    d = record["activity"]["d"]
    keys = list(d)
    out = {
        "source": record["source"],
        "sourceKind": record["sourceKind"],
        "line": record["line"],
        "seq": record.get("seq"),
        "fieldCount": len(d),
        "targetContext": {},
    }
    for key in TARGET_KEYS:
        out["targetContext"][key] = {
            "present": key in d,
            "index": keys.index(key) if key in d else None,
            "value": preview(d.get(key)),
            "valueType": type(d.get(key)).__name__ if key in d else None,
        }
    if "fyNOZTpPQF4=" in d:
        idx = keys.index("fyNOZTpPQF4=")
        out["windowAroundState"] = [
            {
                "index": i,
                "key": keys[i],
                "value": preview(d[keys[i]]),
            }
            for i in range(max(0, idx - 5), min(len(keys), idx + 10))
        ]
    return out


def main():
    success = summarize(load_success_px561())
    tf_samples = [summarize(load_tf_px561(p)) for p in TF_TRACES]

    matrix = []
    for key in TARGET_KEYS:
        matrix.append({
            "key": key,
            "success": success["targetContext"][key],
            "tf": [s["targetContext"][key] for s in tf_samples],
        })

    findings = []
    if success["targetContext"]["fyNOZTpPQF4="]["value"] == "succeeded" and all(
        s["targetContext"]["fyNOZTpPQF4="]["value"] == "succeeded" for s in tf_samples
    ):
        findings.append("fyNOZTpPQF4=succeeded is shared by success and all three tf.payload samples; it is not sufficient to distinguish HUMAN success.")
    if success["targetContext"]["TBR9Ugl7emA="]["present"] and all(
        not s["targetContext"]["TBR9Ugl7emA="]["present"] for s in tf_samples
    ):
        findings.append("TBR9Ugl7emA= is present only in the decoded success bundle sample and absent from all three tf.payload samples.")
    if success["targetContext"]["Bzt2fUFRcw=="]["value"] is not None and all(
        s["targetContext"]["Bzt2fUFRcw=="]["value"] is None for s in tf_samples
    ):
        findings.append("Bzt2fUFRcw== is non-null in success but null in all three tf.payload samples.")
    if success["targetContext"]["OSkIb39DDA=="]["value"] is not None and all(
        s["targetContext"]["OSkIb39DDA=="]["value"] is None for s in tf_samples
    ):
        findings.append("OSkIb39DDA== POW answer is non-null in success but null in all three tf.payload samples.")

    result = {
        "inputs": {
            "successBundle": str(SUCCESS_BUNDLE),
            "tfTraces": [str(p) for p in TF_TRACES],
        },
        "success": success,
        "tfSamples": tf_samples,
        "matrix": matrix,
        "findings": findings,
        "nextEvidenceTargets": [
            "Locate condition/path that injects or preserves TBR9Ugl7emA= between captcha Ts object and final collector bundle.",
            "Determine why direct captcha.beautified.js:11083 assignment does not appear in tf.payload samples.",
            "Separate Ws.NQ(n) state object evidence from success-only collector bundle mutations.",
        ],
    }

    json_path = OUT_DIR / "px561_success_tf_gap_audit.json"
    md_path = OUT_DIR / "px561_success_tf_gap_audit.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    lines = [
        "# PX561 success vs tf.payload gap audit",
        "",
        f"- success bundle: `{SUCCESS_BUNDLE}`",
        f"- json: `{json_path}`",
        "",
        "## Target matrix",
        "",
        "| key | success present/index/value | tf0 | tf1 | tf2 |",
        "|---|---|---|---|---|",
    ]
    for row in matrix:
        def cell(ctx):
            return f"{ctx['present']}/{ctx['index']}/`{ctx['value']}`"
        lines.append(
            f"| `{row['key']}` | {cell(row['success'])} | "
            f"{cell(row['tf'][0])} | {cell(row['tf'][1])} | {cell(row['tf'][2])} |"
        )
    lines += ["", "## Findings", ""]
    for finding in findings:
        lines.append(f"- {finding}")
    lines += ["", "## Window around `fyNOZTpPQF4=`", ""]
    for label, sample in [("success", success)] + [(f"tf{i}", s) for i, s in enumerate(tf_samples)]:
        lines += [f"### {label}: `{sample['source']}` line `{sample['line']}`", "", "| index | key | value |", "|---:|---|---|"]
        for item in sample.get("windowAroundState", []):
            lines.append(f"| {item['index']} | `{item['key']}` | `{item['value']}` |")
        lines.append("")
    lines += ["## Next evidence targets", ""]
    for item in result["nextEvidenceTargets"]:
        lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n")

    print(json.dumps({"json": str(json_path), "md": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
