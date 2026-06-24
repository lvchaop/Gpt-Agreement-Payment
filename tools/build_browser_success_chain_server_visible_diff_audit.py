#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "browser_success_chain_server_visible_diff_audit.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "classificationBacklog": BASE / "browser_success_chain_classification_backlog.json",
    "classifierV2Summary": PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


SERVER_FEATURES = {
    "collector_msft_request": {
        "kind": "request",
        "urlContains": "collector-pxzc5j78di.hsprotect.net/api/v2/msft",
        "valueChain": "request",
        "preAccept": True,
    },
    "collector_bundle_request": {
        "kind": "request",
        "urlContains": "collector-pxzc5j78di.hsprotect.net/assets/js/bundle",
        "valueChain": "request",
        "preAccept": True,
    },
    "collector_bc_request": {
        "kind": "request",
        "urlContains": "collector-pxzc5j78di.hsprotect.net/b/c",
        "valueChain": "request",
        "preAccept": True,
    },
    "collector_beacon_request": {
        "kind": "request",
        "urlContains": "collector-pxzc5j78di.hsprotect.net",
        "urlAlsoContains": "beacon",
        "valueChain": "request",
        "preAccept": False,
    },
    "risk_verify_request": {
        "kind": "request",
        "urlContains": "/risk/verify",
        "valueChain": "risk",
        "preAccept": False,
    },
    "risk_continue_response": {
        "textContainsAny": ['"state":"continue"', '"state": "continue"'],
        "valueChain": "risk",
        "preAccept": False,
    },
    "create_account_request": {
        "kind": "request",
        "urlContains": "/API/CreateAccount",
        "valueChain": "verify",
        "preAccept": False,
    },
    "create_account_redirect_response": {
        "textContainsAny": ["redirectUrl"],
        "valueChain": "verify",
        "preAccept": False,
    },
    "risk_provider_human_metadata": {
        "kind": "request",
        "urlContains": "/risk/verify",
        "textContainsAny": ['"riskProvider":"Human"', '"riskProvider": "Human"'],
        "valueChain": "risk",
        "preAccept": False,
    },
    "collector_cookie_header": {
        "kind": "request",
        "urlContains": "collector-pxzc5j78di.hsprotect.net",
        "headerKey": "cookie",
        "valueChain": "cookie",
        "preAccept": True,
    },
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def runtime_path(run: str) -> Path:
    return REPO / f"output/outlook_browser/runtime_trace_{run}.jsonl"


def load_runtime_events(run: str) -> list[dict[str, Any]]:
    path = runtime_path(run)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        obj["_lineNo"] = line_no
        events.append(obj)
    return events


def event_matches(event: dict[str, Any], spec: dict[str, Any]) -> bool:
    if spec.get("kind") and event.get("kind") != spec["kind"]:
        return False
    url = event.get("url") or ""
    if spec.get("urlContains") and spec["urlContains"] not in url:
        return False
    if spec.get("urlAlsoContains") and spec["urlAlsoContains"] not in url:
        return False
    text = f"{event.get('post_data') or ''}\n{event.get('body') or ''}"
    if spec.get("textContainsAny") and not any(token in text for token in spec["textContainsAny"]):
        return False
    if spec.get("headerKey"):
        headers = event.get("headers") or {}
        wanted = spec["headerKey"].lower()
        if not any(str(key).lower() == wanted for key in headers):
            return False
    return True


def feature_summary(run: str) -> dict[str, Any]:
    events = load_runtime_events(run)
    features: dict[str, Any] = {}
    for feature, spec in SERVER_FEATURES.items():
        matches = [event for event in events if event_matches(event, spec)]
        first = matches[0] if matches else None
        features[feature] = {
            "present": bool(matches),
            "count": len(matches),
            "firstLine": first.get("_lineNo") if first else None,
            "firstTime": first.get("t") if first else None,
            "firstUrl": first.get("url") if first else None,
            "valueChain": spec["valueChain"],
            "preAccept": spec["preAccept"],
        }
    return {
        "run": run,
        "runtimeTrace": str(runtime_path(run)),
        "runtimeTraceExists": runtime_path(run).exists(),
        "eventCount": len(events),
        "features": features,
    }


def feature_presence(rows: list[dict[str, Any]], feature: str) -> int:
    return sum(1 for row in rows if (row.get("features") or {}).get(feature, {}).get("present") is True)


def earliest_positive_line(rows: list[dict[str, Any]], feature: str) -> int | None:
    lines = [
        (row.get("features") or {}).get(feature, {}).get("firstLine")
        for row in rows
        if (row.get("features") or {}).get(feature, {}).get("firstLine") is not None
    ]
    return min(lines) if lines else None


def assess_diff(feature: str, positive_count: int, negative_count: int, positive_total: int, negative_total: int) -> dict[str, Any]:
    spec = SERVER_FEATURES[feature]
    positive_all = positive_total > 0 and positive_count == positive_total
    negative_all = negative_total > 0 and negative_count == negative_total
    prevalence_diff = positive_count != negative_count or positive_all != negative_all
    pre_accept = spec["preAccept"]
    value_chain = spec["valueChain"]
    client_visible = True

    blockers: list[str] = []
    pure_protocol_constructible = False
    contradicted = False

    if feature in {"risk_continue_response", "create_account_redirect_response"}:
        blockers.append("downstream accepted outcome, not a pre-accept cause")
        contradicted = negative_count > 0
    elif feature in {"risk_verify_request", "risk_provider_human_metadata", "create_account_request"}:
        blockers.append("downstream Microsoft request after HUMAN/browser state has already been consumed")
        contradicted = negative_count > 0
    elif feature == "collector_cookie_header":
        blockers.append("primary collector flow does not require Cookie header in existing controls")
        pure_protocol_constructible = True
        contradicted = True
    elif feature == "collector_beacon_request":
        blockers.append("beacon/telemetry endpoint is not the primary accepted collector transition")
        contradicted = negative_count > 0
    else:
        blockers.append("request class also appears in negative controls; no single request field is isolated")
        blockers.append("payload/pc/session material remains coupled for accepted collector state")
        pure_protocol_constructible = False
        contradicted = negative_count > 0

    proposal_ready = (
        prevalence_diff
        and pre_accept
        and client_visible
        and pure_protocol_constructible
        and value_chain in {"request", "cookie", "risk", "verify"}
        and not contradicted
    )
    return {
        "feature": feature,
        "valueChain": value_chain,
        "positivePresence": positive_count,
        "positiveTotal": positive_total,
        "negativePresence": negative_count,
        "negativeTotal": negative_total,
        "prevalenceDiff": prevalence_diff,
        "preAccept": pre_accept,
        "clientVisible": client_visible,
        "pureProtocolConstructible": pure_protocol_constructible,
        "contradicted": contradicted,
        "proposalReady": proposal_ready,
        "blockers": blockers,
    }


def build() -> dict[str, Any]:
    backlog = read_json(INPUTS["classificationBacklog"])
    classifier = read_json(INPUTS["classifierV2Summary"])
    intake = read_json(INPUTS["candidateIntake"])

    backlog_rows = backlog.get("rows") or []
    positive_runs = sorted(
        row["run"]
        for row in backlog_rows
        if row.get("backlogRole") == "browser_success_positive_control"
    )
    parent_cookie_controls = sorted(
        row["run"]
        for row in backlog_rows
        if row.get("backlogRole") == "browser_parent_cookie_control"
    )
    classifier_negative_runs = sorted(
        row["run"]
        for row in classifier.get("runs") or []
        if row.get("stage") != "full_success_decoded"
    )
    negative_runs = sorted(set(parent_cookie_controls) | set(classifier_negative_runs))

    positive_rows = [feature_summary(run) for run in positive_runs]
    negative_rows = [feature_summary(run) for run in negative_runs]

    diff_rows = []
    for feature in SERVER_FEATURES:
        pos_count = feature_presence(positive_rows, feature)
        neg_count = feature_presence(negative_rows, feature)
        row = assess_diff(feature, pos_count, neg_count, len(positive_rows), len(negative_rows))
        row["earliestPositiveLine"] = earliest_positive_line(positive_rows, feature)
        diff_rows.append(row)

    earliest_diff_rows = [
        row for row in diff_rows
        if row["prevalenceDiff"] and row["earliestPositiveLine"] is not None
    ]
    earliest_diff_rows.sort(key=lambda row: row["earliestPositiveLine"])
    single_field_candidates = [
        row for row in diff_rows
        if row["prevalenceDiff"] and row["preAccept"] and row["clientVisible"]
    ]
    proposal_candidates = [row for row in diff_rows if row["proposalReady"]]
    contradicted = [row for row in diff_rows if row["contradicted"]]
    pure_constructible = [row for row in diff_rows if row["pureProtocolConstructible"]]
    value_chains = Counter(row["valueChain"] for row in diff_rows if row["prevalenceDiff"])

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "positiveRunCount": len(positive_rows),
        "negativeControlRunCount": len(negative_rows),
        "parentCookieNegativeControlRunCount": len(parent_cookie_controls),
        "classifierNegativeControlRunCount": len(classifier_negative_runs),
        "positiveRuntimeTraceExistsCount": sum(1 for row in positive_rows if row["runtimeTraceExists"]),
        "negativeRuntimeTraceExistsCount": sum(1 for row in negative_rows if row["runtimeTraceExists"]),
        "earliestServerVisibleDiffCount": len(earliest_diff_rows),
        "singleFieldDiffCandidateCount": len(single_field_candidates),
        "coupledFieldDiffGroupCount": 1 if single_field_candidates else 0,
        "clientVisibleDiffCount": sum(1 for row in diff_rows if row["prevalenceDiff"] and row["clientVisible"]),
        "pureProtocolConstructibleDiffCount": len(pure_constructible),
        "contradictedDiffCount": len(contradicted),
        "proposalCandidateCount": len(proposal_candidates),
        "candidateIntakePromotedCount": (intake.get("checks") or {}).get("promotedSingleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Compare browser success-chain backlog against failure/stall controls to find the earliest server-visible request/cookie/risk/verify diff without running network.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "positiveRuns": positive_runs,
        "negativeControlRuns": negative_runs,
        "valueChainDiffCounts": dict(value_chains),
        "diffRows": diff_rows,
        "earliestServerVisibleDiffRows": earliest_diff_rows,
        "positiveRows": positive_rows,
        "negativeRows": negative_rows,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Browser success chains expose downstream risk/verify/CreateAccount outcome differences and request-class differences, "
                "but all pre-accept server-visible request classes remain contradicted by controls or coupled to payload/pc/session state. "
                "No single proposal-ready transition is isolated."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "valueChainDiffCounts": result["valueChainDiffCounts"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
