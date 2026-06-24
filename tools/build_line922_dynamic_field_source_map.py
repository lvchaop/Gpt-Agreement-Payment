#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"
DECODE_TOOL = ROOT / "tools/decode_bundle_payload_with_marker.py"


def load_json(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def js_line(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if row["_line"] == line_no:
            return row
    raise RuntimeError(f"missing js trace line {line_no}")


def sha(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def short(value: Any, n: int = 160) -> Any:
    if isinstance(value, str):
        return value[:n]
    return value


def load_decode_tool() -> Any:
    spec = importlib.util.spec_from_file_location("decode_bundle_payload_with_marker", DECODE_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DECODE_TOOL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in str(body or "").split("&"):
        if not part:
            continue
        key, _, raw = part.partition("=")
        out[urllib.parse.unquote_plus(key)] = urllib.parse.unquote(raw)
    return out


def activity_key(activity: dict[str, Any], idx: int) -> str:
    return f"{idx}:{activity.get('t')}"


def known_values_from_state(name: str, state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for field, item in state.items():
        if not isinstance(item, dict) or item.get("present") is not True:
            continue
        preview = item.get("preview")
        digest = item.get("sha256")
        if preview is not None and digest:
            out[str(digest)] = {"source": name, "field": field, "preview": preview}
    return out


def exact_value_sources(*, value: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    digest = sha(value)
    sources: list[dict[str, Any]] = []
    for item in context["knownBySha"].get(digest, []):
        sources.append({"match": "sha256", **item})

    if isinstance(value, str):
        if value == context["s00Uuid"]:
            sources.append({"match": "literal", "source": "s00_session", "field": "uuid"})
        if value == context["s00Vid"]:
            sources.append({"match": "literal", "source": "s00_session", "field": "vid"})
        if value == context["s00Ci"]:
            sources.append({"match": "literal", "source": "s00_seq4_response", "field": "ci"})
        if value == context["s00Cs"]:
            sources.append({"match": "literal", "source": "s00_seq4_response", "field": "cs"})
        if value == context["s00Jo"]:
            sources.append({"match": "literal", "source": "s00_seq4_response", "field": "jo/qi"})
        if value == context["href"]:
            sources.append({"match": "literal", "source": "browser_runtime", "field": "iframe_href"})
        if value == context["px3"]:
            sources.append({"match": "literal", "source": "s00_seq4_response", "field": "_px3"})
    return sources


def classify_key(key: str, value: Any, exact_sources: list[dict[str, Any]], added_by_prepc: bool) -> dict[str, Any]:
    if exact_sources:
        return {"class": "exact_value_mapped", "sources": exact_sources}
    if added_by_prepc:
        return {"class": "prepc_injected_unmapped", "sources": []}
    if key in {"AEAxBkUsPjQ=", "TBR9Ugl7emA=", "Bzt2fUFRcw==", "OSkIb39DDA==", "fyNOZTpPQF4="}:
        return {"class": "captcha_pow_wasm_tail_unmapped", "sources": []}
    if key in {"W0shQR0nJHc=", "GCgpLl1AKRw=", "GUloT18mZ3U=", "JnpXfGMUUUc="}:
        return {"class": "browser_dom_or_motion_runtime_unmapped", "sources": []}
    if isinstance(value, (int, float, bool, list, dict)):
        return {"class": "browser_runtime_or_static_value_unmapped", "sources": []}
    return {"class": "unmapped_string", "sources": []}


def main() -> int:
    rows = read_jsonl(JS)
    gen = load_json("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json")
    next_gap = load_json("output/protocol_reverse/hypothesis_reframe/next_decisive_static_gap.json")
    state_gap = load_json("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json")
    combo = load_json("output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json")

    tf_enter = js_line(rows, 920)
    tf_prepc = js_line(rows, 921)
    tf_payload = js_line(rows, 922)
    enter_activities = (tf_enter.get("data") or {}).get("activities") or []
    prepc_activities = (tf_prepc.get("data") or {}).get("activities") or []
    payload_activities = (tf_payload.get("data") or {}).get("activities") or []

    material = combo.get("results", {}).get("seq5", {}).get("material", {})
    material_meta = material.get("meta") or {}
    material_checks = material.get("checks") or {}
    form = parse_form(material.get("body") or "")
    dec = load_decode_tool()
    decoded_fresh = dec.decode_payload(form.get("payload", ""), material_meta.get("marker") or "", material_meta.get("payloadUuid") or form.get("uuid") or "")
    fresh_activities = decoded_fresh.get("json") if isinstance(decoded_fresh.get("json"), list) else []

    s00_state = state_gap.get("s00Seq4ResponseState") or {}
    known_by_sha: dict[str, list[dict[str, Any]]] = {}
    for digest, src in known_values_from_state("s00_seq4_response", s00_state).items():
        known_by_sha.setdefault(digest, []).append(src)

    s00_meta = (tf_payload.get("data") or {}).get("meta") or {}
    context = {
        "knownBySha": known_by_sha,
        "s00Uuid": s00_meta.get("cu"),
        "s00Vid": s00_meta.get("vid"),
        "s00Ci": ((s00_state.get("ci") or {}).get("preview")),
        "s00Cs": ((s00_state.get("cs") or {}).get("preview")),
        "s00Jo": (tf_payload.get("data") or {}).get("qi"),
        "href": tf_payload.get("href"),
        "px3": ((s00_state.get("px3") or {}).get("preview")),
    }

    rows_out: list[dict[str, Any]] = []
    exact_mapped = 0
    unmapped = 0
    fresh_changed = 0
    fresh_equal = 0
    added_key_count = 0

    for idx, activity in enumerate(payload_activities):
        d = activity.get("d") or {}
        enter_d = ((enter_activities[idx] if idx < len(enter_activities) else {}).get("d") or {})
        prepc_d = ((prepc_activities[idx] if idx < len(prepc_activities) else {}).get("d") or {})
        fresh_d = ((fresh_activities[idx] if idx < len(fresh_activities) else {}).get("d") or {})
        for key, value in d.items():
            added_by_prepc = key not in enter_d and key in prepc_d
            if added_by_prepc:
                added_key_count += 1
            exact_sources = exact_value_sources(value=value, context=context)
            classification = classify_key(key, value, exact_sources, added_by_prepc)
            if classification["class"] == "exact_value_mapped":
                exact_mapped += 1
            else:
                unmapped += 1
            fresh_value = fresh_d.get(key, None)
            fresh_present = key in fresh_d
            if fresh_present and fresh_value == value:
                fresh_equal += 1
            elif fresh_present:
                fresh_changed += 1
            rows_out.append({
                "activityIndex": idx,
                "activityType": activity.get("t"),
                "key": key,
                "valueSha256": sha(value),
                "valuePreview": short(value),
                "presentAtTfEnter": key in enter_d,
                "addedByTfPrepc": added_by_prepc,
                "freshSeq5Present": fresh_present,
                "freshSeq5EqualS00": fresh_present and fresh_value == value,
                "freshSeq5ValueSha256": sha(fresh_value) if fresh_present else None,
                **classification,
            })

    class_counts: dict[str, int] = {}
    key_counts: dict[str, int] = {}
    for row in rows_out:
        class_counts[row["class"]] = class_counts.get(row["class"], 0) + 1
        key_counts[row["key"]] = key_counts.get(row["key"], 0) + 1

    unresolved_candidates = [
        row for row in rows_out
        if row["class"] != "exact_value_mapped" and row["freshSeq5Present"] and not row["freshSeq5EqualS00"]
    ]
    exact_mapped_changed = [
        row for row in rows_out
        if row["class"] == "exact_value_mapped" and row["freshSeq5Present"] and not row["freshSeq5EqualS00"]
    ]

    result = {
        "purpose": "Map every s00 accepted line922 payload field to exact evidence sources where possible, and identify remaining unmapped line922 inputs before any fresh-session experiment.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "jsTrace": str(JS),
            "acceptedLine933GenerationLineage": str(ROOT / "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
            "nextDecisiveStaticGap": str(ROOT / "output/protocol_reverse/hypothesis_reframe/next_decisive_static_gap.json"),
            "serverExpectedStatePreSeq5Gap": str(ROOT / "output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"),
            "freshSeq5Combo": str(ROOT / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json"),
        },
        "lineage": {
            "tfEnterLine": 920,
            "tfPrepcLine": 921,
            "tfPayloadLine": 922,
            "activityTypes": [a.get("t") for a in payload_activities],
            "freshDecode": {
                "markerMatch": decoded_fresh.get("markerMatch"),
                "jsonError": decoded_fresh.get("jsonError"),
                "activityTypes": [a.get("t") for a in fresh_activities] if isinstance(fresh_activities, list) else [],
            },
            "materialChecks": material_checks,
        },
        "fieldRows": rows_out,
        "unresolvedChangedCandidates": unresolved_candidates,
        "exactMappedChangedFields": exact_mapped_changed,
        "summary": {
            "fieldInstanceCount": len(rows_out),
            "uniqueKeyCount": len(key_counts),
            "classCounts": class_counts,
            "tfPrepcAddedFieldInstances": added_key_count,
            "exactMappedFieldInstances": exact_mapped,
            "unmappedFieldInstances": unmapped,
            "freshSeq5EqualS00FieldInstances": fresh_equal,
            "freshSeq5ChangedFieldInstances": fresh_changed,
            "unresolvedChangedCandidateCount": len(unresolved_candidates),
            "exactMappedChangedFieldCount": len(exact_mapped_changed),
        },
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "This artifact maps exact value sources but still leaves many browser runtime/static fields unmapped; changed fields are not yet reduced to one untested state transition.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json"),
            "nextScript": str(ROOT / "tools/build_line922_candidate_reduction.py"),
        },
        "checks": {
            "nextGapRequiresThisArtifact": (next_gap.get("decision") or {}).get("nextArtifact") == str(OUT),
            "hasTfPayloadActivities": bool(payload_activities),
            "freshSeq5PayloadDecoded": decoded_fresh.get("jsonError") is None and isinstance(fresh_activities, list),
            "freshSeq5ActivityTypesEqualS00": [a.get("t") for a in fresh_activities] == [a.get("t") for a in payload_activities],
            "hasFieldRows": bool(rows_out),
            "hasExactMappedFields": exact_mapped > 0,
            "hasUnmappedFields": unmapped > 0,
            "hasUnresolvedChangedCandidates": bool(unresolved_candidates),
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "summary": result["summary"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
