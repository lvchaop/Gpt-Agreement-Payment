#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
OUTLOOK = ROOT / "output/outlook_browser"
GOAL = PROTO / "goal_audit"
HYP = PROTO / "hypothesis_reframe"
OUT = HYP / "browser_cookie_bridge_candidate_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"

CLASSIFIER = PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json"
COOKIE_DIR = PROTO / "cookie_timeline"
COOKIE_SESSION_GAP = GOAL / "cookie_session_lineage_gap_audit.json"
PX_COOKIE_JAR = PROTO / "cookie_jar/px_cookie_jar_updater_multi_audit.json"
STATE_WINDOW = GOAL / "s00_line933_state_window_audit.json"


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row["_line"] = line_no
            yield row


def runtime_trace_for(run: str) -> Path | None:
    exact = OUTLOOK / f"runtime_trace_{run}.jsonl"
    if exact.exists():
        return exact
    prefix = run.rsplit("_", 1)[0]
    matches = sorted(OUTLOOK.glob(f"runtime_trace_{prefix}_*.jsonl"))
    return matches[0] if matches else None


def collector_request_cookie_summary(run: str) -> dict[str, Any]:
    trace = runtime_trace_for(run)
    requests = []
    if trace:
        for row in iter_jsonl(trace) or []:
            if row.get("kind") != "request":
                continue
            url = str(row.get("url") or "")
            if "collector-pxzc5j78di.hsprotect.net" not in url:
                continue
            is_primary = "/api/v2/msft" in url or "/assets/js/bundle" in url
            is_beacon = "beacon" in url
            headers = row.get("headers") if isinstance(row.get("headers"), dict) else {}
            cookie = headers.get("cookie") or headers.get("Cookie")
            requests.append(
                {
                    "line": row.get("_line"),
                    "url": url,
                    "isPrimaryCollectorFlow": is_primary and not is_beacon,
                    "isBeacon": is_beacon,
                    "hasCookieHeader": bool(cookie),
                    "cookieLen": len(str(cookie or "")),
                    "seq": _parse_seq(str(row.get("post_data") or "")),
                }
            )
    primary = [r for r in requests if r["isPrimaryCollectorFlow"]]
    beacon = [r for r in requests if r["isBeacon"]]
    return {
        "runtimeTrace": str(trace) if trace else None,
        "collectorRequestCount": len(requests),
        "collectorRequestsWithCookieHeader": sum(1 for r in requests if r["hasCookieHeader"]),
        "primaryCollectorRequestCount": len(primary),
        "primaryCollectorRequestsWithCookieHeader": sum(1 for r in primary if r["hasCookieHeader"]),
        "beaconRequestCount": len(beacon),
        "beaconRequestsWithCookieHeader": sum(1 for r in beacon if r["hasCookieHeader"]),
        "collectorRequestRows": requests[:30],
    }


def _parse_seq(body: str) -> str | None:
    for part in body.split("&"):
        key, _, value = part.partition("=")
        if key == "seq":
            return value
    return None


def stage_index() -> dict[str, str]:
    doc = read_json(CLASSIFIER) or {}
    return {row.get("run"): row.get("stage") for row in doc.get("runs") or [] if row.get("run")}


def success_values(events: list[dict[str, Any]]) -> Counter:
    counter: Counter = Counter()
    for event in events:
        if event.get("name") == "challenge_success":
            counter[str(event.get("value"))] += 1
    return counter


def corrected_success_correlations(decoded: list[dict[str, Any]], parent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent_success = [p for p in parent if p.get("name") == "challenge_success"]
    decoded_success0 = [d for d in decoded if d.get("name") == "challenge_success" and str(d.get("value")) == "0"]
    rows = []
    for d in decoded_success0:
        for p in parent_success:
            rows.append(
                {
                    "collectorLine": d.get("collectorLine"),
                    "partIndex": d.get("partIndex"),
                    "decodedValue": d.get("value"),
                    "parentLine": p.get("line"),
                    "parentWallTime": p.get("wall_t"),
                    "parentValue": p.get("value"),
                    "valueMatch": p.get("value") == "succeeded",
                }
            )
    return rows


def analyze_timeline(path: Path, stages: dict[str, str]) -> dict[str, Any]:
    run = path.name.removeprefix("cookie_timeline_").removesuffix(".json")
    doc = read_json(path) or {}
    decoded = doc.get("decodedEvents") or []
    parent = doc.get("parentMessages") or []
    correlations = doc.get("correlations") or []
    parent_names = Counter(p.get("name") for p in parent)
    decoded_success_counts = success_values(decoded)
    parent_success_count = parent_names.get("challenge_success", 0)
    cookie_corr = [c for c in correlations if c.get("name") in {"_px3", "_pxde", "_pxvid"} and c.get("valueMatch") is True]
    corrected_success = corrected_success_correlations(decoded, parent)
    req_summary = collector_request_cookie_summary(run)
    return {
        "run": run,
        "stage": stages.get(run),
        "timeline": str(path),
        "counts": doc.get("counts") or {},
        "decodedSuccessValues": dict(decoded_success_counts),
        "hasDecodedSuccess0": decoded_success_counts.get("0", 0) > 0,
        "hasDecodedMinus1": decoded_success_counts.get("-1", 0) > 0,
        "hasParentChallengeSuccess": parent_success_count > 0,
        "parentChallengeSuccessCount": parent_success_count,
        "parentCookieMessageCount": sum(parent_names.get(name, 0) for name in ["_px3", "_pxde", "_pxvid"]),
        "cookieCorrelationCount": len(cookie_corr),
        "hasCookieBridgeCorrelation": bool(cookie_corr),
        "correctedSuccessCorrelationCount": len(corrected_success),
        "correctedSuccessCorrelations": corrected_success,
        "legacyCorrelationMatchedMinusOne": any(
            c.get("name") == "challenge_success"
            and any(d.get("collectorLine") == c.get("collectorLine") and str(d.get("value")) == "-1" for d in decoded)
            for c in correlations
        ),
        "collectorRequestCookieSummary": req_summary,
    }


def build() -> dict[str, Any]:
    stages = stage_index()
    rows = [analyze_timeline(path, stages) for path in sorted(COOKIE_DIR.glob("cookie_timeline_*.json"))]
    success_rows = [r for r in rows if r["stage"] == "full_success_decoded"]
    tf_failure_rows = [r for r in rows if r["stage"] == "tf_payload_failure_stage"]
    parent_success_without_decode_rows = [
        r for r in rows if r["hasParentChallengeSuccess"] and not r["hasDecodedSuccess0"]
    ]
    cookie_bridge_in_failure_rows = [
        r for r in tf_failure_rows if r["hasCookieBridgeCorrelation"] and not r["hasParentChallengeSuccess"]
    ]
    collector_cookie_header_rows = [
        r
        for r in rows
        if (r["collectorRequestCookieSummary"] or {}).get("collectorRequestsWithCookieHeader", 0) > 0
    ]
    primary_collector_cookie_header_rows = [
        r
        for r in rows
        if (r["collectorRequestCookieSummary"] or {}).get("primaryCollectorRequestsWithCookieHeader", 0) > 0
    ]
    legacy_bad_success_rows = [r for r in rows if r["legacyCorrelationMatchedMinusOne"]]

    cookie_gap = read_json(COOKIE_SESSION_GAP) or {}
    state_window = read_json(STATE_WINDOW) or {}
    px_cookie = read_json(PX_COOKIE_JAR) or {}

    checks = {
        "planExists": PLAN.exists(),
        "classifierExists": CLASSIFIER.exists(),
        "timelineFileCount": len(rows),
        "fullSuccessDecodedTimelineCount": len(success_rows),
        "tfFailureTimelineCount": len(tf_failure_rows),
        "allFullSuccessHaveCorrectedSuccessCorrelation": bool(success_rows)
        and all(r["correctedSuccessCorrelationCount"] > 0 for r in success_rows),
        "cookieBridgeCorrelationAlsoPresentInTfFailures": bool(cookie_bridge_in_failure_rows),
        "tfFailuresWithCookieBridgeNoParentSuccessCount": len(cookie_bridge_in_failure_rows),
        "parentChallengeSuccessCanExistWithoutDecodedSuccess0": bool(parent_success_without_decode_rows),
        "collectorCookieHeaderObservedRunCount": len(collector_cookie_header_rows),
        "primaryCollectorCookieHeaderObservedRunCount": len(primary_collector_cookie_header_rows),
        "allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader": len(primary_collector_cookie_header_rows) == 0,
        "collectorCookieHeadersOnlyOnBeaconOrTelemetry": len(collector_cookie_header_rows) > 0
        and len(primary_collector_cookie_header_rows) == 0,
        "legacyTimelineSuccessCorrelationBugFound": bool(legacy_bad_success_rows),
        "stateWindowLine933NoCookieHeader": (state_window.get("checks") or {}).get("line933HasNoCookieHeader") is True,
        "cookieSessionGapLine933AndFreshNoCookieHeader": (cookie_gap.get("checks") or {}).get("line933RequestHasNoCookieHeader") is True
        and (cookie_gap.get("checks") or {}).get("freshSeq5RequestHasNoCookieHeader") is True,
        "pxCookieJarRiskVerifyRebuildStillProved": (px_cookie.get("checks") or {}).get("anyRunProvesContinueRiskVerifyMatchesJar") is True,
        "promotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit whether the browser parent cookie bridge can be promoted from a remaining observability boundary to a concrete pure-protocol request/cookie/risk transition candidate.",
        "inputs": {
            "classifier": str(CLASSIFIER),
            "cookieTimelineDir": str(COOKIE_DIR),
            "cookieSessionGapAudit": str(COOKIE_SESSION_GAP),
            "pxCookieJarAudit": str(PX_COOKIE_JAR),
            "stateWindowAudit": str(STATE_WINDOW),
        },
        "checks": checks,
        "rows": rows,
        "evidenceSummary": {
            "cookieBridgeInTfFailures": [
                {
                    "run": r["run"],
                    "stage": r["stage"],
                    "cookieCorrelationCount": r["cookieCorrelationCount"],
                    "parentChallengeSuccessCount": r["parentChallengeSuccessCount"],
                }
                for r in cookie_bridge_in_failure_rows
            ],
            "parentChallengeSuccessWithoutDecodedSuccess0": [
                {"run": r["run"], "stage": r["stage"], "parentChallengeSuccessCount": r["parentChallengeSuccessCount"]}
                for r in parent_success_without_decode_rows
            ],
            "legacyTimelineSuccessCorrelationBugRows": [
                {"run": r["run"], "stage": r["stage"], "decodedSuccessValues": r["decodedSuccessValues"]}
                for r in legacy_bad_success_rows
            ],
            "collectorCookieHeaderObservedRows": [
                {"run": r["run"], "summary": r["collectorRequestCookieSummary"]}
                for r in collector_cookie_header_rows
            ],
            "primaryCollectorCookieHeaderObservedRows": [
                {"run": r["run"], "summary": r["collectorRequestCookieSummary"]}
                for r in primary_collector_cookie_header_rows
            ],
        },
        "promotionGate": {
            "singleTransitionCandidateCount": 0,
            "readyForFreshExperiment": False,
            "reason": (
                "Parent cookie bridge is a browser projection of decoded collector cookie handlers. "
                "It appears in decoded tf-failure runs without parent challenge_success, and known collector requests carry no Cookie header. "
                "The protocol-side _px jar already rebuilds risk/verify values, so this bridge does not expose a new pre-accept request/cookie/risk field."
            ),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextEvidenceNeeded": "A browser-bridge artifact must be traced to a concrete outbound request, cookie header, risk field, or collector state mutation before it can be promoted.",
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "promotionGate": doc["promotionGate"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
