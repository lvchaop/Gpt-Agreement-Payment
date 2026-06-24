#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
PAIR = PROTO / "hypothesis_reframe/selected_contrast_pair.json"
OUT = PROTO / "hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"

S00_RUNTIME = REPO / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
S00_BUNDLE_DECODE = PROTO / "bundle_payload_decode/bundle_payload_decode_s00ld1lglrw0_1781191381.json"
S00_COLLECTOR_DECODE = PROTO / "collector_decode/collector_decode_s00ld1lglrw0_1781191381.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if line.strip():
                row = json.loads(line)
                row["_line"] = line_no
                rows.append(row)
    return rows


def parse_form(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in body.split("&"):
        if not part:
            continue
        key, sep, value = part.partition("=")
        out[urllib.parse.unquote(key)] = urllib.parse.unquote(value if sep else "")
    return out


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def handlers_from_parts(parts: list[str]) -> list[str]:
    return [str(part).split("|", 1)[0] for part in parts]


def summarize_parts(parts: list[str]) -> dict[str, Any]:
    mutations = []
    for part in parts:
        fields = str(part).split("|")
        handler = fields[0] if fields else None
        item: dict[str, Any] = {"handler": handler, "raw": part}
        if handler in {"IoooII", "oIIoIIoo"} and len(fields) >= 4:
            item.update({"name": fields[1], "ttl": fields[2], "valueSha256": sha(fields[3]), "fieldCount": len(fields)})
        elif handler == "oIIoIooo" and len(fields) >= 2:
            item.update({"status": fields[1]})
        elif handler == "IooIIo":
            item.update({"powChallenge": "|".join(fields[1:])})
        elif handler in {"IIoIoI", "oIIoIoII", "ooooII", "oIIoIoIo", "IoIIII", "IooIoo", "oIIooIoo"}:
            item.update({"value": "|".join(fields[1:])})
        mutations.append(item)
    return {
        "handlers": handlers_from_parts(parts),
        "hasPx3": any(part.startswith("IoooII|_px3|") for part in parts),
        "hasPxde": any(part.startswith("oIIoIIoo|_pxde|") for part in parts),
        "hasPow": any(part.startswith("IooIIo|") for part in parts),
        "successStatuses": [part for part in parts if part.startswith("oIIoIooo|")],
        "mutations": mutations,
    }


def request_summary_from_body(body: str) -> dict[str, Any]:
    form = parse_form(body)
    payload = form.get("payload", "")
    return {
        "seq": form.get("seq"),
        "rsc": form.get("rsc"),
        "uuid": form.get("uuid"),
        "pc": form.get("pc"),
        "ci": form.get("ci"),
        "hasCs": bool(form.get("cs")),
        "hasSid": bool(form.get("sid")),
        "hasVid": bool(form.get("vid")),
        "hasCts": bool(form.get("cts")),
        "payloadLen": len(payload),
        "payloadSha256": sha(payload) if payload else None,
        "bodyLenBytes": len(body.encode("utf-8")),
        "bodySha256": sha(body),
    }


def s00_response_by_request_line(decoded_entries: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    by_decode_line = {int(entry["lineNo"]): entry for entry in decoded_entries if entry.get("lineNo") is not None}
    # Runtime request lines and JS decode hook lines are not always identical because the hook logs when
    # the response is consumed. This map is derived from the s00 runtime/js trace ordering.
    request_to_decode = {
        29: 34,
        84: 88,
        111: 118,
        140: 149,
        206: 206,
        293: 289,
        574: 592,
        578: 570,
        634: 623,
        933: 948,
        937: 926,
    }
    return {request_line: by_decode_line[decode_line] for request_line, decode_line in request_to_decode.items() if decode_line in by_decode_line}


def build_s00_timeline() -> list[dict[str, Any]]:
    runtime_rows = read_jsonl(S00_RUNTIME)
    bundle_rows = {int(row["requestLine"]): row for row in (read_json(S00_BUNDLE_DECODE).get("rows") or [])}
    decoded_entries = read_json(S00_COLLECTOR_DECODE).get("decodedEntries") or []
    decoded_by_line = s00_response_by_request_line(decoded_entries)
    timeline = []
    for row in runtime_rows:
        if row.get("kind") != "request":
            continue
        url = str(row.get("url") or "")
        if "collector-pxzc5j78di.hsprotect.net" not in url:
            continue
        body = str(row.get("post_data") or "")
        req = request_summary_from_body(body)
        line_no = int(row["_line"])
        decoded = decoded_by_line.get(line_no) or {}
        parts = decoded.get("parts") or []
        bundle = bundle_rows.get(line_no) or {}
        timeline.append({
            "sample": "s00_success",
            "step": len(timeline),
            "runtimeLine": line_no,
            "urlPath": url.replace("https://collector-pxzc5j78di.hsprotect.net", ""),
            "method": row.get("method"),
            "request": req,
            "decodedPayload": {
                "jsonItemCount": bundle.get("jsonItemCount"),
                "activityTypes": bundle.get("activityTypes"),
                "contains": bundle.get("contains"),
                "markerMatch": bundle.get("markerMatch"),
                "markerSource": bundle.get("markerSource"),
            },
            "response": {
                "decodedLine": decoded.get("lineNo"),
                "handlers": decoded.get("handlers"),
                "hasSuccessHandler": decoded.get("hasSuccessHandler"),
                "hasPowResult": decoded.get("hasPowResult"),
                "partCount": decoded.get("partCount"),
                "partsSummary": summarize_parts(parts),
            },
            "evidence": {
                "runtimeTrace": str(S00_RUNTIME),
                "bundlePayloadDecode": str(S00_BUNDLE_DECODE),
                "collectorDecode": str(S00_COLLECTOR_DECODE),
            },
        })
    return timeline


def normalize_path(path: str | None) -> Path | None:
    if not path:
        return None
    p = Path(path)
    return p if p.is_absolute() else REPO / p


def fresh_single_step(path: Path, label: str, step: int) -> dict[str, Any]:
    doc = read_json(path)
    material = doc.get("material") or {}
    response = doc.get("response") or {}
    decoded = doc.get("decoded") or {}
    body = str(material.get("body") or "")
    parts = decoded.get("parts") or []
    return {
        "sample": "fresh_failed",
        "step": step,
        "label": label,
        "sourcePath": str(path),
        "urlPath": str(material.get("url") or "").replace("https://collector-pxzc5j78di.hsprotect.net", ""),
        "method": "POST",
        "request": request_summary_from_body(body),
        "materialMeta": material.get("meta") or material.get("freshState") or {},
        "response": {
            "status": response.get("status"),
            "handlers": decoded.get("handlers"),
            "hasSuccessHandler": decoded.get("hasSuccessHandler"),
            "hasPowResult": decoded.get("hasPowResult"),
            "bodyText": response.get("bodyText"),
            "partsSummary": summarize_parts(parts),
        },
    }


def fresh_steps_from_sequence(path: Path, start_step: int) -> list[dict[str, Any]]:
    doc = read_json(path)
    out = []
    for raw in doc.get("steps") or []:
        req = raw.get("request") or {}
        resp = raw.get("response") or {}
        dec = raw.get("decoded") or {}
        body = str(req.get("body") or "")
        parts = dec.get("parts") or []
        out.append({
            "sample": "fresh_failed",
            "step": start_step + len(out),
            "label": req.get("name"),
            "sourcePath": str(path),
            "urlPath": str(req.get("url") or "").replace("https://collector-pxzc5j78di.hsprotect.net", ""),
            "method": "POST",
            "request": request_summary_from_body(body),
            "materialMeta": req.get("meta") or {},
            "stateBefore": raw.get("stateBefore"),
            "stateAfter": raw.get("stateAfter"),
            "response": {
                "status": resp.get("status"),
                "handlers": dec.get("handlers"),
                "hasSuccessHandler": dec.get("hasSuccessHandler"),
                "hasPowResult": dec.get("hasPowResult"),
                "bodyText": resp.get("bodyText"),
                "partsSummary": summarize_parts(parts),
            },
        })
    return out


def fresh_steps_from_results(path: Path, start_step: int, order: list[str]) -> list[dict[str, Any]]:
    doc = read_json(path)
    out = []
    for key in order:
        raw = (doc.get("results") or {}).get(key) or {}
        material = raw.get("material") or {}
        response = raw.get("response") or {}
        dec = raw.get("decoded") or {}
        parts = dec.get("parts") or []
        body = str(material.get("body") or "")
        out.append({
            "sample": "fresh_failed",
            "step": start_step + len(out),
            "label": key,
            "sourcePath": str(path),
            "urlPath": str(material.get("url") or "").replace("https://collector-pxzc5j78di.hsprotect.net", ""),
            "method": "POST",
            "request": request_summary_from_body(body),
            "materialMeta": material.get("meta") or {},
            "response": {
                "status": response.get("status"),
                "handlers": dec.get("handlers"),
                "hasSuccessHandler": dec.get("hasSuccessHandler"),
                "hasPowResult": dec.get("hasPowResult"),
                "bodyText": response.get("bodyText"),
                "partsSummary": summarize_parts(parts),
            },
        })
    return out


def build_fresh_timeline(pair: dict[str, Any]) -> list[dict[str, Any]]:
    paths = {entry["role"]: normalize_path(entry.get("path")) for entry in ((pair.get("freshFailedSample") or {}).get("paths") or [])}
    timeline: list[dict[str, Any]] = []
    for role in ["bootstrap", "second"]:
        path = paths.get(role)
        if path:
            timeline.append(fresh_single_step(path, role, len(timeline)))
    for role in ["sequence"]:
        path = paths.get(role)
        if path:
            timeline.extend(fresh_steps_from_sequence(path, len(timeline)))
    path = paths.get("bundle")
    if path:
        timeline.append(fresh_single_step(path, "bundle_seq0", len(timeline)))
    path = paths.get("firstFailureOverlap")
    if path:
        timeline.extend(fresh_steps_from_results(path, len(timeline), ["seq2", "seq3"]))
    path = paths.get("seq4AfterOverlap")
    if path:
        timeline.extend(fresh_steps_from_sequence(path, len(timeline)))
    path = paths.get("finalSeq5Seq6Combo")
    if path:
        timeline.extend(fresh_steps_from_results(path, len(timeline), ["seq5", "seq6"]))
    for idx, item in enumerate(timeline):
        item["step"] = idx
    return timeline


def compare_steps(s00: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    sreq, freq = s00.get("request") or {}, fresh.get("request") or {}
    sresp, fresp = s00.get("response") or {}, fresh.get("response") or {}
    return {
        "s00Step": s00.get("step"),
        "freshStep": fresh.get("step"),
        "s00RuntimeLine": s00.get("runtimeLine"),
        "freshLabel": fresh.get("label"),
        "freshSourcePath": fresh.get("sourcePath"),
        "requestShape": {
            "seqEqual": sreq.get("seq") == freq.get("seq"),
            "rscEqual": sreq.get("rsc") == freq.get("rsc"),
            "urlPathEqual": s00.get("urlPath") == fresh.get("urlPath"),
            "activityTypesEqual": (s00.get("decodedPayload") or {}).get("activityTypes") == (fresh.get("materialMeta") or {}).get("activityTypes"),
            "payloadShaEqual": sreq.get("payloadSha256") == freq.get("payloadSha256"),
            "pcEqual": sreq.get("pc") == freq.get("pc"),
        },
        "responseShape": {
            "handlersEqual": sresp.get("handlers") == fresp.get("handlers"),
            "s00Handlers": sresp.get("handlers"),
            "freshHandlers": fresp.get("handlers"),
            "successStatusEqual": (sresp.get("partsSummary") or {}).get("successStatuses") == (fresp.get("partsSummary") or {}).get("successStatuses"),
            "s00SuccessStatuses": (sresp.get("partsSummary") or {}).get("successStatuses"),
            "freshSuccessStatuses": (fresp.get("partsSummary") or {}).get("successStatuses"),
            "powEqual": sresp.get("hasPowResult") == fresp.get("hasPowResult"),
            "px3MutationEqualByPresence": (sresp.get("partsSummary") or {}).get("hasPx3") == (fresp.get("partsSummary") or {}).get("hasPx3"),
            "pxdeMutationEqualByPresence": (sresp.get("partsSummary") or {}).get("hasPxde") == (fresp.get("partsSummary") or {}).get("hasPxde"),
        },
    }


def divergence_candidates(comparisons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for comp in comparisons:
        req = comp["requestShape"]
        resp = comp["responseShape"]
        if not resp["handlersEqual"]:
            out.append({
                "kind": "response_handler_diff",
                "priority": 1,
                "s00Step": comp["s00Step"],
                "freshStep": comp["freshStep"],
                "s00RuntimeLine": comp["s00RuntimeLine"],
                "freshLabel": comp["freshLabel"],
                "freshSourcePath": comp["freshSourcePath"],
                "details": {
                    "s00Handlers": resp["s00Handlers"],
                    "freshHandlers": resp["freshHandlers"],
                },
                "mayAffect": "response handlers mutate _px3/_pxde/session variables and server/client state consumed by later requests",
            })
        if not resp["successStatusEqual"]:
            out.append({
                "kind": "success_status_diff",
                "priority": 1,
                "s00Step": comp["s00Step"],
                "freshStep": comp["freshStep"],
                "s00RuntimeLine": comp["s00RuntimeLine"],
                "freshLabel": comp["freshLabel"],
                "freshSourcePath": comp["freshSourcePath"],
                "details": {
                    "s00SuccessStatuses": resp["s00SuccessStatuses"],
                    "freshSuccessStatuses": resp["freshSuccessStatuses"],
                },
                "mayAffect": "this is the direct HUMAN acceptance divergence",
            })
        if not req["urlPathEqual"] or not req["seqEqual"] or not req["rscEqual"]:
            out.append({
                "kind": "request_sequence_or_endpoint_diff",
                "priority": 2,
                "s00Step": comp["s00Step"],
                "freshStep": comp["freshStep"],
                "s00RuntimeLine": comp["s00RuntimeLine"],
                "freshLabel": comp["freshLabel"],
                "freshSourcePath": comp["freshSourcePath"],
                "details": req,
                "mayAffect": "collector server-side expected sequence and route state",
            })
    return sorted(out, key=lambda item: (item["priority"], item["s00Step"], item["freshStep"]))


def main() -> int:
    pair = read_json(PAIR)
    s00 = [item for item in build_s00_timeline() if item["urlPath"] in {"/api/v2/msft", "/assets/js/bundle"}]
    fresh = build_fresh_timeline(pair)
    # Compare same logical seq/rsc pairs where present.
    s00_by_key = {(x["request"].get("seq"), x["request"].get("rsc"), x["urlPath"]): x for x in s00}
    comparisons = []
    for f in fresh:
        key = (f["request"].get("seq"), f["request"].get("rsc"), f["urlPath"])
        if key in s00_by_key:
            comparisons.append(compare_steps(s00_by_key[key], f))
        else:
            # fallback compare by seq/rsc only
            for skey, sitem in s00_by_key.items():
                if skey[:2] == key[:2]:
                    comparisons.append(compare_steps(sitem, f))
                    break
    candidates = divergence_candidates(comparisons)
    doc = {
        "purpose": "Phase 3 collector-visible state transition diff between s00 browser success and selected fresh no-browser failure.",
        "plan": str(REPO / "docs/pure-protocol-human-hypothesis-plan.md"),
        "selectedContrastPair": str(PAIR),
        "inputs": {
            "s00Runtime": str(S00_RUNTIME),
            "s00BundleDecode": str(S00_BUNDLE_DECODE),
            "s00CollectorDecode": str(S00_COLLECTOR_DECODE),
            "freshSelectedPair": str(PAIR),
        },
        "s00Timeline": s00,
        "freshTimeline": fresh,
        "comparisons": comparisons,
        "divergenceCandidates": candidates,
        "firstCandidate": candidates[0] if candidates else None,
        "checks": {
            "hasS00Timeline": bool(s00),
            "hasFreshTimeline": bool(fresh),
            "hasComparisons": bool(comparisons),
            "hasDivergenceCandidates": bool(candidates),
            "firstCandidateIsResponseHandlerDiff": bool(candidates and candidates[0]["kind"] == "response_handler_diff"),
        },
        "next": {
            "phase": "Phase 4",
            "artifact": str(PROTO / "hypothesis_reframe/first_decisive_divergence.json"),
            "script": str(REPO / "tools/find_first_decisive_divergence.py"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "firstCandidate": doc["firstCandidate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
