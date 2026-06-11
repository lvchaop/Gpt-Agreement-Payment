#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "collector_chain"

RUNS = [
    ("ni109xdjp5zp_1780948211", "accepted_success"),
    ("hcxwyrtiudbg_1780949301", "tf_failure_control"),
    ("fk8zn2nqhex1_1781115338", "aeax_only_negative_control"),
    ("b0hnt0zycbpx_1781116322", "aeax_only_negative_control"),
]


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["_line"] = line_no
        rows.append(row)
    return rows


def form_params(post_data: str) -> dict[str, str]:
    # Existing tooling intentionally preserves literal plus signs in HUMAN payloads.
    parsed = urllib.parse.parse_qsl(str(post_data or "").replace("+", "%2B"), keep_blank_values=True)
    return {k: v for k, v in parsed}


def js_path(run: str) -> Path:
    return REPO / "output/outlook_browser" / f"js_internal_trace_{run}.jsonl"


def runtime_path(run: str) -> Path:
    return REPO / "output/outlook_browser" / f"runtime_trace_{run}.jsonl"


def nearest_preceding(events: list[dict[str, Any]], t: float | None) -> dict[str, Any] | None:
    if t is None:
        return None
    candidates = [event for event in events if isinstance(event.get("t"), (int, float)) and event["t"] <= t]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x["t"])


def nearest_following(events: list[dict[str, Any]], t: float | None) -> dict[str, Any] | None:
    if t is None:
        return None
    candidates = [event for event in events if isinstance(event.get("t"), (int, float)) and event["t"] >= t]
    if not candidates:
        return None
    return min(candidates, key=lambda x: x["t"])


def summarize_network_requests(rows: list[dict[str, Any]], suffix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("kind") != "request":
            continue
        url = str(row.get("url") or "")
        if not url.endswith(suffix):
            continue
        params = form_params(row.get("post_data") or "")
        out.append(
            {
                "line": row.get("_line"),
                "t": row.get("t"),
                "url": url,
                "seq": params.get("seq"),
                "ft": params.get("ft"),
                "uuid": params.get("uuid"),
                "postLen": row.get("post_len"),
                "payloadLen": len(params.get("payload", "")),
                "paramKeys": sorted(params.keys()),
                "hasCs": "cs" in params,
                "hasSid": "sid" in params,
                "hasVid": "vid" in params,
                "hasCts": "cts" in params,
                "hasCi": "ci" in params,
            }
        )
    return out


def summarize_fp_entries(run: str, js_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decode = load_json(PROTO / "collector_decode" / f"collector_decode_{run}.json")
    by_line = {}
    if decode:
        for entry in decode.get("decodedEntries") or []:
            by_line[int(entry.get("lineNo") or -1)] = entry
    out: list[dict[str, Any]] = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.main.fp.enter":
            continue
        entry = by_line.get(row.get("_line"), {})
        parts = entry.get("parts") or []
        out.append(
            {
                "line": row.get("_line"),
                "t": row.get("wall_t"),
                "rawLen": entry.get("rawLen"),
                "partCount": entry.get("partCount"),
                "handlers": entry.get("handlers") or [],
                "successParts": [p for p in parts if str(p).startswith("oIIoIooo|0")],
                "powParts": [p for p in parts if str(p).startswith("IooIIo|")],
                "hasSuccessHandler": bool(entry.get("hasSuccessHandler")),
                "hasPowResult": bool(entry.get("hasPowResult")),
                "hasPx3": bool(entry.get("hasPx3")),
                "hasPxde": bool(entry.get("hasPxde")),
            }
        )
    return out


def summarize_pow(run: str, js_rows: list[dict[str, Any]]) -> dict[str, Any]:
    replay = load_json(PROTO / "pow" / f"pow_replay_{run}.json") or {}
    hit_lines = {int(hit.get("lineNo") or -1): hit for hit in replay.get("hits") or []}
    runtime_hits = []
    for row in js_rows:
        if row.get("kind") != "hsprotect.captcha.pow.hit":
            continue
        d = row.get("data") or {}
        runtime_hits.append(
            {
                "line": row.get("_line"),
                "t": row.get("wall_t"),
                "i": d.get("i"),
                "value": d.get("value"),
                "replayHit": hit_lines.get(int(row.get("_line") or -1)),
            }
        )
    return {
        "path": str((PROTO / "pow" / f"pow_replay_{run}.json").resolve()),
        "exists": bool(replay),
        "seedCount": len(replay.get("seeds") or []),
        "rangeCount": len(replay.get("ranges") or []),
        "runtimeHitCount": len(runtime_hits),
        "runtimeHits": runtime_hits,
    }


def summarize_bundle_payload(run: str) -> dict[str, Any]:
    data = load_json(PROTO / "bundle_payload_decode" / f"bundle_payload_decode_{run}.json")
    if data is None:
        return {"exists": False, "path": str((PROTO / "bundle_payload_decode" / f"bundle_payload_decode_{run}.json").resolve())}
    rows = []
    for row in data.get("rows") or []:
        activity_types = row.get("activityTypes") or []
        contains = row.get("contains") or {}
        rows.append(
            {
                "requestLine": row.get("requestLine"),
                "seq": row.get("seq"),
                "payloadLen": row.get("payloadLen"),
                "markerQi": row.get("markerQi"),
                "markerMatch": row.get("markerMatch"),
                "jsonItemCount": row.get("jsonItemCount"),
                "activityTypes": activity_types,
                "hasPX561": "PX561" in activity_types,
                "containsPowSeedPrefix": bool(contains.get("218e34c1")),
                "containsPowSolutionIndex": bool(contains.get("50239")),
                "containsPowTargetPrefix": bool(contains.get("1366f575")),
            }
        )
    return {
        "exists": True,
        "path": str((PROTO / "bundle_payload_decode" / f"bundle_payload_decode_{run}.json").resolve()),
        "rows": rows,
    }


def summarize_bundle_activity(run: str) -> dict[str, Any]:
    data = load_json(PROTO / "bundle_activity_matches" / f"bundle_activity_matches_{run}.json")
    if data is None:
        return {"exists": False, "path": str((PROTO / "bundle_activity_matches" / f"bundle_activity_matches_{run}.json").resolve())}
    px561 = []
    for req in data.get("requests") or []:
        for item in req.get("activitiesWithMatches") or []:
            activity = item.get("activity") or {}
            if item.get("type") != "PX561" and activity.get("t") != "PX561":
                continue
            d = activity.get("d") or {}
            px561.append(
                {
                    "requestLine": req.get("requestLine"),
                    "seq": req.get("seq"),
                    "activityIndex": item.get("index"),
                    "dKeyCount": len(d),
                    "hasAEAx": "AEAxBkUsPjQ=" in d,
                    "hasTBR9": "TBR9Ugl7emA=" in d,
                    "tbr9Len": len(str(d.get("TBR9Ugl7emA=", ""))) if "TBR9Ugl7emA=" in d else None,
                    "aeaxLen": len(str(d.get("AEAxBkUsPjQ=", ""))) if "AEAxBkUsPjQ=" in d else None,
                }
            )
    return {
        "exists": True,
        "path": str((PROTO / "bundle_activity_matches" / f"bundle_activity_matches_{run}.json").resolve()),
        "px561": px561,
    }


def summarize_trace_classification(run: str) -> dict[str, Any]:
    data = load_json(PROTO / f"trace_classification_{run}.json")
    if data is None:
        return {"exists": False, "path": str((PROTO / f"trace_classification_{run}.json").resolve())}
    checks = data.get("checks") or {}
    return {
        "exists": True,
        "path": str((PROTO / f"trace_classification_{run}.json").resolve()),
        "checks": {
            "decoded_oIIoIooo_0": checks.get("decoded_oIIoIooo_0"),
            "dispatch_oIIoIooo_0": checks.get("dispatch_oIIoIooo_0"),
            "risk_verify_state_continue": checks.get("risk_verify_state_continue"),
            "create_account_redirectUrl": checks.get("create_account_redirectUrl"),
        },
    }


def summarize_run(run: str, role: str) -> dict[str, Any]:
    js_rows = read_jsonl(js_path(run))
    runtime_rows = read_jsonl(runtime_path(run))
    api_requests = summarize_network_requests(runtime_rows, "/api/v2/msft")
    bundle_requests = summarize_network_requests(runtime_rows, "/assets/js/bundle")
    fp_entries = summarize_fp_entries(run, js_rows)
    success_entries = [entry for entry in fp_entries if entry.get("hasSuccessHandler")]
    pow_summary = summarize_pow(run, js_rows)
    bundle_payload = summarize_bundle_payload(run)
    bundle_activity = summarize_bundle_activity(run)

    links = []
    for entry in success_entries:
        t = entry.get("t")
        prev_bundle = nearest_preceding(bundle_requests, t)
        next_bundle = nearest_following(bundle_requests, t)
        prev_api = nearest_preceding(api_requests, t)
        links.append(
            {
                "successFpLine": entry.get("line"),
                "successFpTime": t,
                "successParts": entry.get("successParts"),
                "nearestPrecedingBundleRequest": prev_bundle,
                "deltaFromPrecedingBundleSeconds": round(t - prev_bundle["t"], 6) if prev_bundle and t else None,
                "nearestFollowingBundleRequest": next_bundle,
                "deltaToFollowingBundleSeconds": round(next_bundle["t"] - t, 6) if next_bundle and t else None,
                "nearestPrecedingApiRequest": prev_api,
                "deltaFromPrecedingApiSeconds": round(t - prev_api["t"], 6) if prev_api and t else None,
            }
        )

    return {
        "run": run,
        "role": role,
        "paths": {
            "jsTrace": str(js_path(run).resolve()),
            "runtimeTrace": str(runtime_path(run).resolve()),
        },
        "traceClassification": summarize_trace_classification(run),
        "apiMsftRequests": api_requests,
        "bundleRequests": bundle_requests,
        "decodedFpEntries": fp_entries,
        "pow": pow_summary,
        "bundlePayloadDecode": bundle_payload,
        "bundleActivityMatches": bundle_activity,
        "successHandlerTimeLinks": links,
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines = [
        "# Collector request/response chain audit",
        "",
        "Evidence rule: line numbers are only compared within the same trace file. Cross-file ordering uses epoch fields (`runtime_trace.t` and `js_internal_trace.wall_t`) and is labeled as time-neighbor evidence.",
        "",
        "## Summary",
        "",
        "| run | role | success handler | runtime POW hit | decoded POW result | bundle PX561 | PX561 TBR9 | CreateAccount redirect |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["runs"]:
        fp_success = sum(1 for e in row["decodedFpEntries"] if e.get("hasSuccessHandler"))
        runtime_pow_hits = row["pow"].get("runtimeHitCount")
        decoded_pow_results = sum(1 for e in row["decodedFpEntries"] if e.get("hasPowResult"))
        bundle_px = sum(1 for r in (row["bundlePayloadDecode"].get("rows") or []) if r.get("hasPX561"))
        px561 = row["bundleActivityMatches"].get("px561") or []
        tbr9 = any(x.get("hasTBR9") for x in px561)
        checks = row["traceClassification"].get("checks") or {}
        lines.append(
            f"| {row['run']} | {row['role']} | {fp_success} | {runtime_pow_hits} | {decoded_pow_results} | {bundle_px} | {tbr9} | {checks.get('create_account_redirectUrl')} |"
        )

    for row in result["runs"]:
        lines += ["", f"## {row['run']} ({row['role']})", ""]
        lines.append(f"- jsTrace: `{row['paths']['jsTrace']}`")
        lines.append(f"- runtimeTrace: `{row['paths']['runtimeTrace']}`")
        lines.append(f"- traceClassification: `{row['traceClassification'].get('path')}`")
        lines.append("")
        lines.append("### `/api/v2/msft` requests")
        lines.append("| line | t | seq | payloadLen | state params |")
        lines.append("|---:|---:|---:|---:|---|")
        for req in row["apiMsftRequests"]:
            state = ",".join(k for k in ["hasCs", "hasSid", "hasVid", "hasCts", "hasCi"] if req.get(k)) or "-"
            lines.append(f"| {req['line']} | {req.get('t')} | {req.get('seq')} | {req.get('payloadLen')} | {state} |")
        lines.append("")
        lines.append("### `/assets/js/bundle` requests")
        lines.append("| line | t | seq | payloadLen |")
        lines.append("|---:|---:|---:|---:|")
        for req in row["bundleRequests"]:
            lines.append(f"| {req['line']} | {req.get('t')} | {req.get('seq')} | {req.get('payloadLen')} |")
        lines.append("")
        lines.append("### decoded fp entries")
        lines.append("| js line | wall_t | success | powResult | px3 | pxde | handlers |")
        lines.append("|---:|---:|---:|---:|---:|---:|---|")
        for entry in row["decodedFpEntries"]:
            lines.append(
                f"| {entry['line']} | {entry.get('t')} | {entry.get('hasSuccessHandler')} | {entry.get('hasPowResult')} | {entry.get('hasPx3')} | {entry.get('hasPxde')} | {','.join(entry.get('handlers') or [])} |"
            )
        lines.append("")
        lines.append("### time-neighbor links for success handler")
        if not row["successHandlerTimeLinks"]:
            lines.append("- no decoded `oIIoIooo|0` success handler")
        for link in row["successHandlerTimeLinks"]:
            prev_bundle = link.get("nearestPrecedingBundleRequest") or {}
            next_bundle = link.get("nearestFollowingBundleRequest") or {}
            prev_api = link.get("nearestPrecedingApiRequest") or {}
            lines.append(
                f"- fp line `{link['successFpLine']}` at `{link['successFpTime']}`: "
                f"prev bundle line `{prev_bundle.get('line')}` seq `{prev_bundle.get('seq')}` delta `{link.get('deltaFromPrecedingBundleSeconds')}`s; "
                f"next bundle line `{next_bundle.get('line')}` seq `{next_bundle.get('seq')}` delta `{link.get('deltaToFollowingBundleSeconds')}`s; "
                f"prev api line `{prev_api.get('line')}` seq `{prev_api.get('seq')}` delta `{link.get('deltaFromPrecedingApiSeconds')}`s"
            )
        lines.append("")
        lines.append("### POW")
        lines.append(f"- pow replay: `{row['pow'].get('path')}`")
        lines.append(f"- runtimeHitCount: `{row['pow'].get('runtimeHitCount')}`")
        for hit in row["pow"].get("runtimeHits") or []:
            value = str(hit.get("value") or "")
            lines.append(f"  - line `{hit.get('line')}` t `{hit.get('t')}` i `{hit.get('i')}` valuePrefix `{value[:32]}`")
        lines.append("")
        lines.append("### bundle payload / PX561")
        lines.append(f"- bundle payload decode: `{row['bundlePayloadDecode'].get('path')}` exists=`{row['bundlePayloadDecode'].get('exists')}`")
        lines.append("| line | seq | markerMatch | jsonItems | hasPX561 | containsPowSeedPrefix |")
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for br in row["bundlePayloadDecode"].get("rows") or []:
            lines.append(
                f"| {br.get('requestLine')} | {br.get('seq')} | {br.get('markerMatch')} | {br.get('jsonItemCount')} | {br.get('hasPX561')} | {br.get('containsPowSeedPrefix')} |"
            )
        lines.append("")
        lines.append(f"- bundle activity matches: `{row['bundleActivityMatches'].get('path')}` exists=`{row['bundleActivityMatches'].get('exists')}`")
        for px in row["bundleActivityMatches"].get("px561") or []:
            lines.append(
                f"  - requestLine `{px.get('requestLine')}` seq `{px.get('seq')}` activityIndex `{px.get('activityIndex')}` "
                f"hasAEAx `{px.get('hasAEAx')}` aeaxLen `{px.get('aeaxLen')}` hasTBR9 `{px.get('hasTBR9')}` tbr9Len `{px.get('tbr9Len')}`"
            )
    lines += [
        "",
        "## Evidence-backed conclusion",
        "",
        result["conclusion"],
        "",
        "## Limitation",
        "",
        result["limitation"],
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = [summarize_run(run, role) for run, role in RUNS]
    result = {
        "purpose": "Map decoded HUMAN collector response handlers to observed request timelines, POW hit evidence, and decoded bundle PX561 payloads without assuming cross-file line-number equivalence.",
        "runs": runs,
        "conclusion": (
            "In the accepted ni109 sample, decoded `oIIoIooo|0` is present and time-neighbor evidence places it immediately after "
            "`/assets/js/bundle` seq=3, while the same run has a preceding POW runtime hit and a decoded bundle seq=2 PX561 payload containing "
            "the POW seed prefix and TBR9/AEAx target fields. The audited failure/negative-control rows do not currently provide the same "
            "complete chain in local artifacts."
        ),
        "limitation": (
            "This is an offline trace audit. It links already-captured events by decoded handler content, per-trace line numbers, and epoch "
            "time proximity. It does not prove fresh pure-protocol POST acceptance and does not prove that any one field alone causes HUMAN acceptance."
        ),
    }
    out_json = OUT_DIR / "collector_request_response_chain_audit.json"
    out_md = OUT_DIR / "collector_request_response_chain_audit.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(result, out_md)
    print(json.dumps({"json": str(out_json), "md": str(out_md), "runCount": len(runs)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
