#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
CTOR = REPO / "tools/audit_bundle_seq_constructor.py"
OUT_DIR = REPO / "output/protocol_reverse/px561_constructor"

RUN = "j0t8van4qyhm_1781119142"
JS_TRACE = REPO / f"output/outlook_browser/js_internal_trace_{RUN}.jsonl"
RUNTIME_TRACE = REPO / f"output/outlook_browser/runtime_trace_{RUN}.jsonl"
BUNDLE_BUILD = REPO / f"output/protocol_reverse/bundle_request_build/bundle_request_build_{RUN}.json"
LIVE_POW = REPO / "output/protocol_reverse/pow_response/pow_response_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.json"

TARGET_KEYS = ["AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA=="]


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ctor = load_module(CTOR, "audit_bundle_seq_constructor_for_px561_tail")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_line"] = line_no
        rows.append(row)
    return rows


def parse_form_ordered(body: str) -> list[dict[str, str]]:
    pairs = []
    for part in str(body or "").split("&"):
        if not part:
            continue
        raw_key, _, raw_value = part.partition("=")
        pairs.append(
            {
                "key": urllib.parse.unquote(raw_key),
                "value": urllib.parse.unquote(raw_value),
                "rawKey": raw_key,
                "rawValue": raw_value,
            }
        )
    return pairs


def rebuild_body(pairs: list[dict[str, str]], replacements: dict[str, str]) -> str:
    out = []
    for pair in pairs:
        key = pair["key"]
        value = replacements.get(key, pair["rawValue"])
        out.append(f"{pair['rawKey']}={value}")
    return "&".join(out)


def line_row(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if row.get("_line") == line_no:
            return row
    raise KeyError(f"line not found: {line_no}")


def template_material(run: str, tf_line: int | None = None) -> dict[str, Any]:
    js_trace = REPO / f"output/outlook_browser/js_internal_trace_{run}.jsonl"
    runtime_trace = REPO / f"output/outlook_browser/runtime_trace_{run}.jsonl"
    bundle_build = REPO / f"output/protocol_reverse/bundle_request_build/bundle_request_build_{run}.json"
    js_rows = read_jsonl(js_trace)
    runtime_rows = read_jsonl(runtime_trace)
    build = json.loads(bundle_build.read_text(encoding="utf-8"))
    candidates = [
        row
        for row in build.get("rows") or []
        if (row.get("contains") or {}).get("PX561") and (row.get("contains") or {}).get("OSkIb39DDA==")
    ]
    if tf_line is not None:
        candidates = [row for row in candidates if row.get("materialSourceLine") == tf_line]
    if not candidates:
        raise RuntimeError("no PX561/OSk template candidate found")
    row = candidates[-1]
    tf = line_row(js_rows, int(row["materialSourceLine"]))
    req = line_row(runtime_rows, int(row["requestLine"]))
    data = tf.get("data") or {}
    activities = data.get("activities")
    if not isinstance(activities, list):
        raise RuntimeError("tf.payload row has no activities")
    px_idx = next(
        (idx for idx, activity in enumerate(activities) if isinstance(activity, dict) and activity.get("t") == "PX561"),
        None,
    )
    if px_idx is None:
        raise RuntimeError("template activities contain no PX561")
    return {
        "run": run,
        "buildRow": row,
        "tfLine": row["materialSourceLine"],
        "requestLine": row["requestLine"],
        "tfData": data,
        "activities": activities,
        "pxIndex": px_idx,
        "request": req,
    }


def first_solved_pow(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    for row in doc.get("results") or []:
        if row.get("matchesTarget") is True and row.get("value"):
            return row
    return None


def build_from_activities(material: dict[str, Any], activities: list[dict[str, Any]]) -> dict[str, Any]:
    row = material["buildRow"]
    params = {pair["key"]: pair["value"] for pair in parse_form_ordered(material["request"].get("post_data") or "")}
    pairs = parse_form_ordered(material["request"].get("post_data") or "")
    serialized = ctor.ut(activities)
    marker = str((material["tfData"] or {}).get("marker") or "")
    replay = ctor.encode_serialized(serialized, marker, params["uuid"])
    pc = ctor.pc_value(serialized, params["uuid"], params["tag"], params["ft"])
    body = rebuild_body(pairs, {"payload": replay["payload"], "pc": pc})
    return {
        "serialized": serialized,
        "payload": replay["payload"],
        "pc": pc,
        "body": body,
        "payloadMatchesObserved": replay["payload"] == params.get("payload"),
        "pcMatchesObserved": pc == params.get("pc"),
        "bodyMatchesObserved": body == (material["request"].get("post_data") or ""),
        "rowPayloadMatchFlag": row.get("payloadMatch"),
        "rowPcMatchFlag": row.get("pcMatch"),
        "rowBodyMatchFlag": row.get("bodyMatch"),
    }


def target_summary(activity: dict[str, Any]) -> dict[str, Any]:
    d = activity.get("d") if isinstance(activity.get("d"), dict) else {}
    return {
        key: {
            "present": key in d,
            "type": type(d.get(key)).__name__,
            "len": len(d.get(key)) if isinstance(d.get(key), str) else None,
            "value": d.get(key),
        }
        for key in TARGET_KEYS
    }


def analyze(run: str, tf_line: int | None, live_pow: Path, bzt: str | None) -> dict[str, Any]:
    material = template_material(run, tf_line)
    original_activities = material["activities"]
    px_idx = material["pxIndex"]
    px = original_activities[px_idx]
    original_tail = target_summary(px)
    original_rebuild = build_from_activities(material, original_activities)

    same_activities = copy.deepcopy(original_activities)
    same_d = same_activities[px_idx]["d"]
    same_d["OSkIb39DDA=="] = px["d"].get("OSkIb39DDA==")
    same_d["Bzt2fUFRcw=="] = px["d"].get("Bzt2fUFRcw==")
    same_rebuild = build_from_activities(material, same_activities)

    pow_row = first_solved_pow(live_pow)
    experimental = None
    if pow_row:
        exp_activities = copy.deepcopy(original_activities)
        exp_d = exp_activities[px_idx]["d"]
        exp_d["OSkIb39DDA=="] = pow_row["value"]
        bzt_source = "argument"
        if bzt is None:
            if pow_row.get("solveElapsedMs") is not None:
                bzt = str(pow_row.get("solveElapsedMs"))
                bzt_source = "live_pow_solve_elapsed_ms"
            else:
                bzt = str(exp_d.get("Bzt2fUFRcw=="))
                bzt_source = "template_original_placeholder"
        exp_d["Bzt2fUFRcw=="] = bzt
        exp_rebuild = build_from_activities(material, exp_activities)
        experimental = {
            "livePowSource": str(live_pow.resolve()),
            "oskSource": {
                "raw": pow_row.get("raw"),
                "value": pow_row.get("value"),
                "sha256": pow_row.get("sha256"),
                "matchesTarget": pow_row.get("matchesTarget"),
            },
            "bztSource": bzt_source,
            "bzt": bzt,
            "tbr9Source": "template_original_stale_not_proven_reusable",
            "rebuild": {
                "serializedLen": len(exp_rebuild["serialized"]),
                "payloadLen": len(exp_rebuild["payload"]),
                "pc": exp_rebuild["pc"],
                "bodyLen": len(exp_rebuild["body"]),
            },
            "body": exp_rebuild["body"],
        }

    checks = {
        "templateHasPx561": px.get("t") == "PX561",
        "templateHasTbr9BztOsk": all(original_tail[key]["present"] for key in ("TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA==")),
        "originalRebuildMatchesObserved": original_rebuild["payloadMatchesObserved"] and original_rebuild["pcMatchesObserved"] and original_rebuild["bodyMatchesObserved"],
        "sameValueReplacementMatchesObserved": same_rebuild["payloadMatchesObserved"] and same_rebuild["pcMatchesObserved"] and same_rebuild["bodyMatchesObserved"],
        "livePowValueAvailable": pow_row is not None,
        "experimentalBodyBuilt": experimental is not None,
        "experimentalUsesLiveOsk": bool(experimental and experimental["oskSource"]["matchesTarget"] is True),
        "experimentalHasLiveBztEvidence": bool(
            experimental and experimental["bztSource"] in {"argument", "live_pow_solve_elapsed_ms"}
        ),
        "experimentalHasFreshTbr9Evidence": False,
    }
    return {
        "purpose": "Parameterize accepted PX561 POW tail fields while keeping evidence boundaries explicit.",
        "template": {
            "run": run,
            "tfLine": material["tfLine"],
            "requestLine": material["requestLine"],
            "seq": material["buildRow"].get("seq"),
            "pxIndex": px_idx,
            "tail": original_tail,
        },
        "originalRebuild": {k: v for k, v in original_rebuild.items() if k != "body" and k != "serialized" and k != "payload"},
        "sameValueRebuild": {k: v for k, v in same_rebuild.items() if k != "body" and k != "serialized" and k != "payload"},
        "experimental": experimental,
        "checks": checks,
        "conclusion": (
            "Accepted PX561 activities can be parameterized and re-encoded: same-value OSk/Bzt replacement is byte-exact. "
            "A live-OSk/live-Bzt experimental body can be built, but it is not success-ready because fresh TBR9 producer evidence is still missing."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit PX561 POW-tail constructor readiness from accepted template and live POW output.")
    parser.add_argument("--run", default=RUN)
    parser.add_argument("--tf-line", type=int, default=487)
    parser.add_argument("--live-pow", type=Path, default=LIVE_POW)
    parser.add_argument("--bzt", default=None, help="Optional live solve elapsed value for Bzt2fUFRcw==.")
    parser.add_argument("--out-prefix", default="px561_pow_tail_constructor_audit")
    args = parser.parse_args()
    result = analyze(args.run, args.tf_line, args.live_pow, args.bzt)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"{args.out_prefix}.json"
    out_md = OUT_DIR / f"{args.out_prefix}.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["# PX561 POW-tail constructor audit", "", "## Checks", ""]
    for key, value in result["checks"].items():
        md.append(f"- {key}: `{value}`")
    md += ["", "## Template", ""]
    md.append(f"- run: `{result['template']['run']}`")
    md.append(f"- tfLine: `{result['template']['tfLine']}`")
    md.append(f"- requestLine: `{result['template']['requestLine']}`")
    md.append(f"- pxIndex: `{result['template']['pxIndex']}`")
    md += ["", "## Experimental boundary", ""]
    if result["experimental"]:
        md.append(f"- oskSource.matchesTarget: `{result['experimental']['oskSource']['matchesTarget']}`")
        md.append(f"- bztSource: `{result['experimental']['bztSource']}`")
        md.append(f"- tbr9Source: `{result['experimental']['tbr9Source']}`")
        md.append(f"- bodyLen: `{result['experimental']['rebuild']['bodyLen']}`")
    md += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
