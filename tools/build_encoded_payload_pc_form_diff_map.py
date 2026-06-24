#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"
DECODE_TOOL = ROOT / "tools/decode_bundle_payload_with_marker.py"
S00_RUNTIME = ROOT / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
S00_JS = ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def line(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if row["_line"] == line_no:
            return row
    raise RuntimeError(f"missing line {line_no}")


def load_decode_tool() -> Any:
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def summarize_form(form: dict[str, str], body: str) -> dict[str, Any]:
    return {
        "bodyCharLen": len(body),
        "bodyLenBytes": len(body.encode("utf-8")),
        "bodySha256": sha(body),
        "keys": list(form.keys()),
        "payloadLen": len(form.get("payload", "")),
        "payloadSha256": sha(form.get("payload", "")),
        "uuid": form.get("uuid"),
        "seq": form.get("seq"),
        "rsc": form.get("rsc"),
        "ci": form.get("ci"),
        "csSha256": sha(form.get("cs", "")),
        "pc": form.get("pc"),
        "sidLen": len(form.get("sid", "")),
        "sidSha256": sha(form.get("sid", "")),
        "p1": form.get("p1"),
        "vid": form.get("vid"),
        "cts": form.get("cts"),
        "tag": form.get("tag"),
        "appId": form.get("appId"),
        "ft": form.get("ft"),
        "enSha256": sha(form.get("en", "")),
    }


def diff_forms(a: dict[str, str], b: dict[str, str]) -> list[dict[str, Any]]:
    keys = sorted(set(a) | set(b))
    out = []
    for key in keys:
        av = a.get(key)
        bv = b.get(key)
        equal = av == bv
        out.append({
            "key": key,
            "equal": equal,
            "s00Present": key in a,
            "freshPresent": key in b,
            "s00Len": len(av or ""),
            "freshLen": len(bv or ""),
            "s00Sha256": sha(av or ""),
            "freshSha256": sha(bv or ""),
            "s00Preview": (av or "")[:120],
            "freshPreview": (bv or "")[:120],
        })
    return out


def main() -> int:
    reduction = load("output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json")
    boundary = load("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json")
    split = load("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json")
    combo = load("output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json")

    runtime_rows = read_jsonl(S00_RUNTIME)
    js_rows = read_jsonl(S00_JS)
    s00_runtime_line = line(runtime_rows, 933)
    s00_payload_line = line(js_rows, 922)
    s00_body = s00_runtime_line.get("post_data") or ""
    fresh_body = combo.get("results", {}).get("seq5", {}).get("material", {}).get("body") or ""
    s00_form = parse_form(s00_body)
    fresh_form = parse_form(fresh_body)

    fresh_meta = combo.get("results", {}).get("seq5", {}).get("material", {}).get("meta") or {}
    dec = load_decode_tool()
    s00_marker = (s00_payload_line.get("data") or {}).get("marker")
    fresh_marker = fresh_meta.get("marker")
    s00_decoded = dec.decode_payload(s00_form.get("payload", ""), s00_marker, s00_form.get("uuid", ""))
    fresh_decoded = dec.decode_payload(fresh_form.get("payload", ""), fresh_marker, fresh_meta.get("payloadUuid") or fresh_form.get("uuid", ""))

    form_diffs = diff_forms(s00_form, fresh_form)
    differing_keys = [d["key"] for d in form_diffs if not d["equal"]]
    non_payload_diffs = [d for d in form_diffs if d["key"] != "payload" and not d["equal"]]

    base_equal = s00_decoded.get("base") == fresh_decoded.get("base")
    decoded_text_equal = s00_decoded.get("decodedText") == fresh_decoded.get("decodedText")
    json_equal = s00_decoded.get("json") == fresh_decoded.get("json")
    marker_equal = s00_marker == fresh_marker

    diff_classification = []
    for item in non_payload_diffs:
        key = item["key"]
        status = "session_specific_outer_field"
        prior = []
        if key == "pc":
            status = "computed_encoder_binding"
            prior = [
                "forced_overlap_payload_pc_split_control_audit exact payload+pc was not sufficient",
                "line922_candidate_reduction eliminated decoded activity fields",
            ]
        elif key in {"uuid", "cs", "sid", "p1", "vid", "ci", "cts"}:
            prior = ["outer/session fields differ by selected fresh session design"]
        diff_classification.append({**item, "status": status, "priorControlCoverage": prior})

    result = {
        "purpose": "Map non-decoded encoded payload/pc/form differences between s00 accepted line933 and selected fresh seq5 while decoded activities are equal.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "line922CandidateReduction": str(ROOT / "output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json"),
            "s00Runtime": str(S00_RUNTIME) + ":933",
            "s00JsTrace": str(S00_JS) + ":922",
            "freshSeq5Combo": str(ROOT / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json"),
            "encodedDecodedBoundaryAudit": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
            "payloadPcSplitControl": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
        },
        "s00": {
            "form": summarize_form(s00_form, s00_body),
            "marker": s00_marker,
            "markerSha256": sha(s00_marker or ""),
            "decoded": {
                "markerMatch": s00_decoded.get("markerMatch"),
                "jsonError": s00_decoded.get("jsonError"),
                "baseSha256": sha(s00_decoded.get("base") or ""),
                "decodedTextSha256": sha(s00_decoded.get("decodedText") or ""),
            },
        },
        "fresh": {
            "form": summarize_form(fresh_form, fresh_body),
            "marker": fresh_marker,
            "markerSha256": sha(fresh_marker or ""),
            "decoded": {
                "markerMatch": fresh_decoded.get("markerMatch"),
                "jsonError": fresh_decoded.get("jsonError"),
                "baseSha256": sha(fresh_decoded.get("base") or ""),
                "decodedTextSha256": sha(fresh_decoded.get("decodedText") or ""),
            },
        },
        "payloadLayerComparison": {
            "markerEqual": marker_equal,
            "payloadEqual": s00_form.get("payload") == fresh_form.get("payload"),
            "baseAfterMarkerRemovalEqual": base_equal,
            "decodedTextEqual": decoded_text_equal,
            "jsonEqual": json_equal,
            "pcEqual": s00_form.get("pc") == fresh_form.get("pc"),
            "bodyEqual": s00_body == fresh_body,
        },
        "formDiffs": form_diffs,
        "diffClassification": diff_classification,
        "existingControlCoverage": {
            "boundaryChecks": boundary.get("checks"),
            "payloadPcSplitChecks": split.get("checks"),
            "line922ReductionChecks": reduction.get("checks"),
        },
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "Decoded JSON and decoded text are equal; payload difference is marker/uuid insertion plus session outer/form and pc binding. Static payload+pc transplant is already negatively controlled, so the next evidence must determine which server-state/form field is consumed at final acceptance.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"),
            "nextScript": str(ROOT / "tools/build_server_state_value_to_request_lineage.py"),
        },
        "checks": {
            "candidateReductionRequiresThisArtifact": (reduction.get("decision") or {}).get("nextArtifact") == str(OUT),
            "s00FormParsed": bool(s00_form),
            "freshFormParsed": bool(fresh_form),
            "sameFormKeys": set(s00_form) == set(fresh_form),
            "decodedJsonEqual": json_equal,
            "decodedTextEqual": decoded_text_equal,
            "baseAfterMarkerRemovalEqual": base_equal,
            "payloadDiffers": s00_form.get("payload") != fresh_form.get("payload"),
            "markerDiffers": not marker_equal,
            "pcDiffers": s00_form.get("pc") != fresh_form.get("pc"),
            "nonPayloadDiffKeysPresent": bool(non_payload_diffs),
            "staticPayloadPcControlExists": bool(split.get("checks")),
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "payloadLayerComparison": result["payloadLayerComparison"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
