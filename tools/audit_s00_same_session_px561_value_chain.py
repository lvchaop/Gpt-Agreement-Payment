#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
DECODE_TOOL = REPO / "tools/decode_bundle_payload_with_marker.py"
RUN_ID = "s00ld1lglrw0_1781191381"
RUNTIME_TRACE = REPO / f"output/outlook_browser/runtime_trace_{RUN_ID}.jsonl"
COLLECTOR_DECODE = REPO / f"output/protocol_reverse/collector_decode/collector_decode_{RUN_ID}.json"
POW_RESPONSE = REPO / f"output/protocol_reverse/pow_response/pow_response_{RUN_ID}.json"
NQ_REPLAY = REPO / f"output/protocol_reverse/wasm/captcha_wasm_nq_replay_{RUN_ID}.json"
OUT_DIR = REPO / "output/protocol_reverse/goal_audit"

REQUEST_LINES = [574, 933]
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


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def shape(value: Any) -> dict[str, Any]:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if not isinstance(value, str) else value
    return {
        "type": type(value).__name__,
        "len": len(value) if isinstance(value, (str, list, dict)) else None,
        "sha256": sha256_text(text),
        "preview": text[:160] + (f"...<len={len(text)}>" if len(text) > 160 else ""),
    }


def px_activity(activities: list[Any]) -> dict[str, Any]:
    for activity in activities:
        if isinstance(activity, dict) and activity.get("t") == "PX561":
            return activity
    raise RuntimeError("PX561 activity not found")


def decode_request(dec: Any, timeline: list[dict[str, Any]], request_line: int) -> dict[str, Any]:
    runtime_row = read_jsonl_line(RUNTIME_TRACE, request_line)
    params = dec.parse_form(runtime_row.get("post_data") or "")
    marker = dec.marker_for_request(timeline, request_line)
    decoded = dec.decode_payload(params["payload"], marker["marker"], params["uuid"])
    activities = decoded["json"] if isinstance(decoded.get("json"), list) else []
    px = px_activity(activities)
    d = px.get("d") or {}
    keys = list(d.keys())
    return {
        "requestLine": request_line,
        "url": runtime_row.get("url"),
        "params": {k: params.get(k) for k in ["uuid", "seq", "pc", "ft", "cs", "sid", "vid", "cts"]},
        "payloadLen": len(params.get("payload", "")),
        "postDataSha256": sha256_text(runtime_row.get("post_data") or ""),
        "marker": marker,
        "decode": {
            "markerMatch": decoded["markerMatch"],
            "jsonError": decoded["jsonError"],
            "activityCount": len(activities),
            "activityTypes": [item.get("t") for item in activities if isinstance(item, dict)],
        },
        "px": {
            "fieldCount": len(keys),
            "keysSha256": sha256_text(json.dumps(keys, ensure_ascii=False)),
            "targetValues": {
                key: {
                    "present": key in d,
                    "index": keys.index(key) if key in d else None,
                    "value": d.get(key),
                    "shape": shape(d[key]) if key in d else None,
                }
                for key in TARGET_KEYS
            },
        },
    }


def decoded_entries() -> list[dict[str, Any]]:
    doc = read_json(COLLECTOR_DECODE)
    return sorted(doc.get("decodedEntries", []), key=lambda x: int(x.get("lineNo") or 0))


def next_handler(entries: list[dict[str, Any]], request_line: int) -> dict[str, Any] | None:
    for entry in entries:
        line_no = int(entry.get("lineNo") or 0)
        if line_no <= request_line:
            continue
        for part in entry.get("parts") or []:
            fields = str(part).split("|")
            if fields and fields[0] == "oIIoIooo":
                return {"lineNo": line_no, "part": part, "status": fields[1] if len(fields) > 1 else None}
    return None


def pow_challenges(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        line_no = int(entry.get("lineNo") or 0)
        for part in entry.get("parts") or []:
            fields = str(part).split("|")
            if fields and fields[0] == "IooIIo":
                out.append({
                    "lineNo": line_no,
                    "raw": part,
                    "combinedSeed": fields[2] if len(fields) > 2 else None,
                    "target": fields[3] if len(fields) > 3 else None,
                    "difficulty": fields[4] if len(fields) > 4 else None,
                })
    return out


def main() -> int:
    dec = load_module(DECODE_TOOL, "decode_bundle_payload_with_marker")
    timeline = dec.build_marker_timeline(COLLECTOR_DECODE)
    entries = decoded_entries()
    pow_doc = read_json(POW_RESPONSE)
    nq_doc = read_json(NQ_REPLAY)
    pow_results = pow_doc.get("results") or []
    nq_samples = nq_doc.get("samples") or []

    observed_requests = [decode_request(dec, timeline, line) for line in REQUEST_LINES]
    challenge_rows = pow_challenges(entries)
    chains: list[dict[str, Any]] = []
    for idx, request in enumerate(observed_requests):
        pow_result = pow_results[idx] if idx < len(pow_results) else {}
        nq_sample = nq_samples[idx] if idx < len(nq_samples) else {}
        challenge = challenge_rows[idx] if idx < len(challenge_rows) else {}
        target = request["px"]["targetValues"]
        osk = target["OSkIb39DDA=="].get("value")
        tbr9 = target["TBR9Ugl7emA="].get("value")
        bzt = target["Bzt2fUFRcw=="].get("value")
        handler = next_handler(entries, int(request["requestLine"]))
        chains.append({
            "cycleIndex": idx,
            "request": request,
            "precedingPowChallenge": challenge,
            "solvedPow": {
                "raw": pow_result.get("raw"),
                "value": pow_result.get("value"),
                "sha256": pow_result.get("sha256"),
                "matchesTarget": pow_result.get("matchesTarget"),
                "solveElapsedMs": pow_result.get("solveElapsedMs"),
            },
            "nqRuntimeSample": {
                "line": nq_sample.get("line"),
                "nInput": nq_sample.get("nInput"),
                "nqValue": nq_sample.get("nqValue"),
                "nqLen": nq_sample.get("nqLen"),
            },
            "px561Extracted": {
                "OSkIb39DDA==": target["OSkIb39DDA=="],
                "TBR9Ugl7emA=": target["TBR9Ugl7emA="],
                "Bzt2fUFRcw==": target["Bzt2fUFRcw=="],
            },
            "comparisons": {
                "powChallengeRawMatchesSolvedRaw": challenge.get("raw") == pow_result.get("raw"),
                "oskEqualsSolvedPowValue": osk == pow_result.get("value"),
                "oskSha256EqualsSolvedPowSha256": sha256_text(osk or "") == pow_result.get("sha256"),
                "nqInputEqualsSolvedPowValue": nq_sample.get("nInput") == pow_result.get("value"),
                "tbr9EqualsNqValue": tbr9 == nq_sample.get("nqValue"),
                "bztEqualsPowSolveElapsedMsString": bzt == str(pow_result.get("solveElapsedMs")),
            },
            "nextCollectorHandler": handler,
        })

    checks = {
        "allRequestsDecoded": all(c["request"]["decode"]["jsonError"] is None for c in chains),
        "allMarkersMatch": all(c["request"]["decode"]["markerMatch"] is True for c in chains),
        "allPowChallengesMatchSolvedRows": all(c["comparisons"]["powChallengeRawMatchesSolvedRaw"] for c in chains),
        "allOskValuesMatchSolvedPow": all(c["comparisons"]["oskEqualsSolvedPowValue"] for c in chains),
        "allOskSha256MatchPowTargets": all(c["comparisons"]["oskSha256EqualsSolvedPowSha256"] for c in chains),
        "allNqInputsEqualSolvedPowValues": all(c["comparisons"]["nqInputEqualsSolvedPowValue"] for c in chains),
        "allTbr9ValuesEqualNqRuntimeValues": all(c["comparisons"]["tbr9EqualsNqValue"] for c in chains),
        "line574HandlerFailure": chains[0]["nextCollectorHandler"] and chains[0]["nextCollectorHandler"].get("status") == "-1",
        "line933HandlerSuccess": chains[1]["nextCollectorHandler"] and chains[1]["nextCollectorHandler"].get("status") == "0",
        "successRowSameSessionCoherent": (
            len(chains) > 1
            and chains[1]["comparisons"]["powChallengeRawMatchesSolvedRaw"]
            and chains[1]["comparisons"]["oskEqualsSolvedPowValue"]
            and chains[1]["comparisons"]["nqInputEqualsSolvedPowValue"]
            and chains[1]["comparisons"]["tbr9EqualsNqValue"]
            and chains[1]["nextCollectorHandler"]
            and chains[1]["nextCollectorHandler"].get("status") == "0"
        ),
    }
    result = {
        "purpose": "Prove the same-session value chain for s00 PX561 requests: collector POW challenge -> solved OSk -> Ws.NQ input/output -> PX561 target values -> next collector handler.",
        "runId": RUN_ID,
        "evidenceFiles": {
            "runtimeTrace": str(RUNTIME_TRACE),
            "collectorDecode": str(COLLECTOR_DECODE),
            "powResponse": str(POW_RESPONSE),
            "nqReplay": str(NQ_REPLAY),
            "decodeTool": str(DECODE_TOOL),
        },
        "chains": chains,
        "checks": checks,
        "conclusion": (
            "The observed browser session contains two same-session PX561 cycles. In both cycles OSk equals the locally solved POW value and TBR9 equals the runtime Ws.NQ output for that POW value. "
            "The first coherent cycle is followed by collector handler -1; the second coherent cycle is followed by handler 0. This proves the same-session successful value chain exists in artifacts, but it is not by itself an end-to-end pure-protocol PoC."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / "s00_same_session_px561_value_chain_audit.json"
    out_md = OUT_DIR / "s00_same_session_px561_value_chain_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# s00 same-session PX561 value chain audit",
        "",
        "## Checks",
        "",
        *[f"- {key}: `{value}`" for key, value in checks.items()],
        "",
        "## Chains",
        "",
        "| cycle | request line | NQ line | POW value matches OSk | TBR9 matches NQ | handler | Bzt |",
        "|---:|---:|---:|---:|---:|---|---|",
    ]
    for chain in chains:
        bzt_val = chain["px561Extracted"]["Bzt2fUFRcw=="].get("value")
        lines.append(
            f"| {chain['cycleIndex']} | {chain['request']['requestLine']} | {chain['nqRuntimeSample'].get('line')} | "
            f"{chain['comparisons']['oskEqualsSolvedPowValue']} | {chain['comparisons']['tbr9EqualsNqValue']} | "
            f"{(chain['nextCollectorHandler'] or {}).get('part')} | `{bzt_val}` |"
        )
    lines += ["", "## Conclusion", "", result["conclusion"], ""]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
