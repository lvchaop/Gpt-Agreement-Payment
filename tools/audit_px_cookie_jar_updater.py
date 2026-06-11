#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
TIMELINE_DIR = REPO / "output/protocol_reverse/cookie_timeline"
RISK_DIR = REPO / "output/protocol_reverse/risk_verify"
OUT_DIR = REPO / "output/protocol_reverse/cookie_jar"

PX_NAMES = {"_px3", "_pxde", "_pxvid", "_pxhd_candidate"}
RISK_MAP = {"_px3": "px3", "_pxde": "pxde", "_pxvid": "pxvid"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def host_from_parent_message(msg: dict[str, Any] | None) -> str | None:
    if not msg:
        return None
    href = str(msg.get("href") or "")
    if not href:
        return None
    parsed = urlparse(href)
    return parsed.hostname


def correlation_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (row.get("collectorLine"), row.get("partIndex"), row.get("name"))


def parent_key(row: dict[str, Any]) -> tuple[Any, Any]:
    return (row.get("parentLine") or row.get("line"), row.get("name"))


def build_parent_lookup(timeline: dict[str, Any]) -> dict[tuple[Any, Any], dict[str, Any]]:
    lookup: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in timeline.get("parentMessages") or []:
        lookup[parent_key(row)] = row
    return lookup


def build_corr_lookup(timeline: dict[str, Any]) -> dict[tuple[Any, Any, Any], dict[str, Any]]:
    lookup: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for row in timeline.get("correlations") or []:
        lookup[correlation_key(row)] = row
    return lookup


def decoded_events_with_parent(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    parent_lookup = build_parent_lookup(timeline)
    corr_lookup = build_corr_lookup(timeline)
    out: list[dict[str, Any]] = []
    for order, event in enumerate(timeline.get("decodedEvents") or []):
        name = event.get("name")
        if name not in PX_NAMES and name != "challenge_success":
            continue
        corr = corr_lookup.get(correlation_key(event))
        parent = None
        if corr:
            parent = parent_lookup.get((corr.get("parentLine"), corr.get("name")))
        item = dict(event)
        item["order"] = order
        item["correlation"] = corr
        item["parentMessage"] = parent
        item["parentWallTime"] = parent.get("wall_t") if parent else None
        item["parentLine"] = parent.get("line") if parent else None
        item["valueMatchesParent"] = (
            True
            if name == "challenge_success" and parent
            else bool(parent and parent.get("value") == event.get("value"))
        )
        item["cookieHost"] = host_from_parent_message(parent)
        out.append(item)
    return out


def apply_events_until(events: list[dict[str, Any]], request_time: float | None) -> dict[str, Any]:
    jar: dict[str, Any] = {}
    applied: list[dict[str, Any]] = []
    for event in events:
        name = event.get("name")
        if name not in PX_NAMES:
            continue
        wall = event.get("parentWallTime")
        if request_time is not None and wall is not None and wall > request_time:
            continue
        if request_time is not None and wall is None:
            # Without runtime wall time this event cannot prove it preceded the Microsoft request.
            continue
        jar[name] = {
            "name": name,
            "value": event.get("value"),
            "ttl": event.get("ttl"),
            "handler": event.get("handler"),
            "collectorLine": event.get("collectorLine"),
            "partIndex": event.get("partIndex"),
            "parentLine": event.get("parentLine"),
            "parentWallTime": wall,
            "host": event.get("cookieHost"),
            "source": "collector_decoded+parent_postmessage",
        }
        applied.append(
            {
                "name": name,
                "collectorLine": event.get("collectorLine"),
                "partIndex": event.get("partIndex"),
                "parentLine": event.get("parentLine"),
                "parentWallTime": wall,
            }
        )
    return {"jar": jar, "appliedEvents": applied}


def human_meta_from_request(req: dict[str, Any]) -> dict[str, Any]:
    body = req.get("requestBody") or {}
    solution = body.get("challengeSolution") if isinstance(body.get("challengeSolution"), dict) else {}
    metas = body.get("riskProviderMetadata") if isinstance(body.get("riskProviderMetadata"), list) else []
    human_meta = next((m for m in metas if isinstance(m, dict) and m.get("riskProvider") == "Human"), {})
    return {
        "challengeSolution": {key: solution.get(field) for key, field in RISK_MAP.items()},
        "riskProviderMetadata": {key: human_meta.get(field) for key, field in RISK_MAP.items()},
    }


def compare_jar_to_request(jar: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    req_values = human_meta_from_request(req)
    comparisons: dict[str, Any] = {}
    for target, values in req_values.items():
        comparisons[target] = {}
        for cookie_name, requested_value in values.items():
            jar_value = (jar.get(cookie_name) or {}).get("value")
            comparisons[target][cookie_name] = {
                "requestHasValue": requested_value is not None,
                "jarHasValue": jar_value is not None,
                "match": requested_value == jar_value if requested_value is not None else None,
                "jarSource": {
                    key: (jar.get(cookie_name) or {}).get(key)
                    for key in ("handler", "collectorLine", "partIndex", "parentLine", "parentWallTime", "host")
                },
            }
    return comparisons


def all_requested_values_match(comparisons: dict[str, Any], target: str) -> bool:
    rows = comparisons.get(target) or {}
    requested = [row for row in rows.values() if row.get("requestHasValue")]
    return bool(requested) and all(row.get("match") is True for row in requested)


def analyze_run(run: str) -> dict[str, Any]:
    timeline_path = TIMELINE_DIR / f"cookie_timeline_{run}.json"
    risk_path = RISK_DIR / f"risk_verify_material_{run}.json"
    if not timeline_path.exists():
        checks = {
            "timelineExists": False,
            "riskMaterialExists": risk_path.exists(),
            "hasDecodedPxEvents": False,
            "hasCorrelatedPx3PxdePxvid": False,
            "hasSuccessEvent": False,
            "hasRiskVerifyRequests": False,
            "allRiskProviderMetadataValuesMatchJar": False,
            "challengeSolutionRequestMatchesJar": False,
            "continueRiskVerifyMatchesJar": False,
        }
        return {
            "run": run,
            "evidenceFiles": {
                "cookieTimeline": str(timeline_path.resolve()),
                "riskVerifyMaterial": str(risk_path.resolve()) if risk_path.exists() else None,
            },
            "eventCount": 0,
            "successEvents": [],
            "finalCookieJar": {},
            "riskVerifyRows": [],
            "checks": checks,
            "conclusion": "Missing cookie timeline; this run cannot prove decoded-handler-to-risk/verify cookie jar mapping.",
        }
    timeline = load_json(timeline_path)
    risk = load_json(risk_path) if risk_path.exists() else {}
    events = decoded_events_with_parent(timeline)
    risk_requests = risk.get("riskVerify") if isinstance(risk.get("riskVerify"), list) else []
    request_rows = []
    for req in risk_requests:
        request_time = req.get("requestTime")
        state = req.get("state")
        replay = apply_events_until(events, request_time)
        comparisons = compare_jar_to_request(replay["jar"], req)
        request_rows.append(
            {
                "requestLine": req.get("requestLine"),
                "requestTime": request_time,
                "state": state,
                "hasChallengeSolution": req.get("hasChallengeSolution"),
                "jar": replay["jar"],
                "appliedEvents": replay["appliedEvents"],
                "comparisons": comparisons,
                "riskProviderMetadataMatchesJar": all_requested_values_match(comparisons, "riskProviderMetadata"),
                "challengeSolutionMatchesJar": all_requested_values_match(comparisons, "challengeSolution"),
            }
        )
    success_events = [e for e in events if e.get("name") == "challenge_success"]
    final_replay = apply_events_until(events, None)
    checks = {
        "timelineExists": timeline_path.exists(),
        "riskMaterialExists": risk_path.exists(),
        "hasDecodedPxEvents": any(e.get("name") in PX_NAMES for e in events),
        "hasCorrelatedPx3PxdePxvid": all(
            any(e.get("name") == name and e.get("valueMatchesParent") for e in events)
            for name in ("_px3", "_pxde", "_pxvid")
        ),
        "hasSuccessEvent": bool(success_events),
        "hasRiskVerifyRequests": bool(risk_requests),
        "allRiskProviderMetadataValuesMatchJar": bool(request_rows)
        and all(row["riskProviderMetadataMatchesJar"] for row in request_rows),
        "challengeSolutionRequestMatchesJar": any(row["challengeSolutionMatchesJar"] for row in request_rows),
        "continueRiskVerifyMatchesJar": any(
            row.get("state") == "continue" and row["challengeSolutionMatchesJar"] for row in request_rows
        ),
    }
    return {
        "run": run,
        "evidenceFiles": {
            "cookieTimeline": str(timeline_path.resolve()),
            "riskVerifyMaterial": str(risk_path.resolve()) if risk_path.exists() else None,
        },
        "eventCount": len(events),
        "successEvents": success_events,
        "finalCookieJar": final_replay["jar"],
        "riskVerifyRows": request_rows,
        "checks": checks,
        "conclusion": (
            "Decoded collector cookie handlers can be replayed into a protocol-side _px jar, and the jar values match Microsoft risk/verify Human metadata/challengeSolution for this run."
            if checks["continueRiskVerifyMatchesJar"]
            else "This run does not prove a complete decoded-handler-to-risk/verify cookie jar match."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay decoded HUMAN collector cookie handlers into a protocol cookie jar and audit risk/verify usage.")
    parser.add_argument("--run", action="append", default=None, help="Run id without prefix, e.g. ni109xdjp5zp_1780948211")
    parser.add_argument("--out-prefix", default="px_cookie_jar_updater_audit")
    args = parser.parse_args()
    runs = args.run or ["ni109xdjp5zp_1780948211"]
    results = [analyze_run(run) for run in runs]
    checks = {
        "allRunsHaveTimeline": all(r["checks"]["timelineExists"] for r in results),
        "allRunsHaveDecodedPxEvents": all(r["checks"]["hasDecodedPxEvents"] for r in results),
        "anyRunProvesContinueRiskVerifyMatchesJar": any(r["checks"]["continueRiskVerifyMatchesJar"] for r in results),
    }
    result = {
        "purpose": "Offline _px cookie/token updater audit from decoded collector handlers to Microsoft risk/verify request values.",
        "runs": results,
        "checks": checks,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUT_DIR / f"{args.out_prefix}.json"
    out_md = OUT_DIR / f"{args.out_prefix}.md"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# _px cookie jar updater audit", "", "## Checks", ""]
    for key, value in checks.items():
        md.append(f"- {key}: `{value}`")
    for run in results:
        md += ["", f"## Run `{run['run']}`", "", "### Run checks", ""]
        for key, value in run["checks"].items():
            md.append(f"- {key}: `{value}`")
        md += ["", "### risk/verify rows", ""]
        for row in run["riskVerifyRows"]:
            md.append(
                f"- line={row['requestLine']} state={row['state']} "
                f"riskMetaMatches={row['riskProviderMetadataMatchesJar']} "
                f"challengeSolutionMatches={row['challengeSolutionMatchesJar']}"
            )
            for name in ("_px3", "_pxde", "_pxvid"):
                source = (row["jar"].get(name) or {})
                md.append(
                    f"  - {name}: collectorLine={source.get('collectorLine')} part={source.get('partIndex')} "
                    f"parentLine={source.get('parentLine')} host={source.get('host')}"
                )
        md += ["", "### Conclusion", "", run["conclusion"]]
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "md": str(out_md), "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
