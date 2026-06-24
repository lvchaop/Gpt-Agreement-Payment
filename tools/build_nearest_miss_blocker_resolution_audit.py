#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
GOAL = PROTO / "goal_audit"
OUT = HYP / "nearest_miss_blocker_resolution_audit.json"

INPUTS = {
    "nearestMiss": HYP / "nearest_miss_promotion_candidate_audit.json",
    "encoderAxisEquivalence": HYP / "encoder_axis_equivalence.json",
    "encodedSessionBinding": HYP / "encoded_session_binding_candidate_audit.json",
    "browserServerVisibleDiff": HYP / "browser_success_chain_server_visible_diff_audit.json",
    "browserCookieBridge": HYP / "browser_cookie_bridge_candidate_audit.json",
    "singleTransitionMatrix": HYP / "single_transition_candidate_matrix.json",
    "cleanPayloadPcControls": GOAL / "clean_history_payload_pc_controls_audit.json",
    "exactPayloadBodyControls": GOAL / "latest_exact_payload_body_controls_audit.json",
    "forcedOverlapPayloadPcSplit": GOAL / "forced_overlap_payload_pc_split_control_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def find_row(rows: list[dict[str, Any]], *, id_: str | None = None, feature: str | None = None) -> dict[str, Any]:
    for row in rows:
        if id_ is not None and row.get("id") == id_:
            return row
        if feature is not None and row.get("feature") == feature:
            return row
    return {}


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    nearest_rows = docs["nearestMiss"].get("nearestRows") or []
    pc_nearest = find_row(nearest_rows, id_="pc_value")
    cookie_nearest = find_row(nearest_rows, id_="collector_cookie_header")
    pc_lineage = find_row(docs["browserServerVisibleDiff"].get("fieldLineageRows") or [], id_="pc_value")
    if not pc_lineage:
        pc_lineage = find_row(docs.get("browserPayloadPcSessionLineage", {}).get("fieldLineageRows") or [], id_="pc_value")
    cookie_diff = find_row(docs["browserServerVisibleDiff"].get("diffRows") or [], feature="collector_cookie_header")

    c_encoder = checks(docs["encoderAxisEquivalence"])
    c_encoded = checks(docs["encodedSessionBinding"])
    c_cookie = checks(docs["browserCookieBridge"])
    c_single = checks(docs["singleTransitionMatrix"])
    c_clean = checks(docs["cleanPayloadPcControls"])
    c_exact = checks(docs["exactPayloadBodyControls"])
    c_split = checks(docs["forcedOverlapPayloadPcSplit"])

    pc_closed_by_controls = (
        c_encoder.get("pcUuidSourceDeterminesPc") is True
        and c_encoder.get("remainingFamilyIsIndependent2x2") is True
        and c_encoder.get("singleEncoderAxisIsolated") is False
        and c_encoded.get("pcAloneEliminated") is True
        and c_encoded.get("exactPayloadPcNoSuccess") is True
        and c_clean.get("exactPayloadPcReturnedDoEmpty") is True
        and c_split.get("seq5PayloadAndPcExactS00") is True
        and c_split.get("seq5NoOIIoIooo") is True
    )
    pc_single_transition_blocker_proven = (
        c_encoder.get("remainingEncoderAxisCount") == 2
        and c_encoded.get("remainingDiffKeysArePayloadPcSession") is True
    )
    cookie_closed_by_controls = (
        cookie_diff.get("positivePresence") == 17
        and cookie_diff.get("negativePresence") == 5
        and cookie_diff.get("contradicted") is True
        and c_cookie.get("primaryCollectorCookieHeaderObservedRunCount") == 0
        and c_cookie.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader") is True
        and c_cookie.get("collectorCookieHeadersOnlyOnBeaconOrTelemetry") is True
        and c_cookie.get("stateWindowLine933NoCookieHeader") is True
        and c_cookie.get("cookieSessionGapLine933AndFreshNoCookieHeader") is True
    )
    cookie_single_transition_blocker_proven = (
        c_single.get("noReadySingleTransitionCandidate") is True
        and c_cookie.get("promotedSingleTransitionCandidateCount") in {None, 0}
    )

    rows = [
        {
            "id": "pc_value",
            "status": "closed_by_existing_controls" if pc_closed_by_controls and pc_single_transition_blocker_proven else "needs_more_evidence",
            "nearestMissingPredicates": pc_nearest.get("missingPredicates"),
            "closureChecks": {
                "pcClosedByControls": pc_closed_by_controls,
                "pcSingleTransitionBlockerProven": pc_single_transition_blocker_proven,
                "pcUuidSourceDeterminesPc": c_encoder.get("pcUuidSourceDeterminesPc"),
                "remainingEncoderAxisCount": c_encoder.get("remainingEncoderAxisCount"),
                "pcAloneEliminated": c_encoded.get("pcAloneEliminated"),
                "exactPayloadPcNoSuccess": c_encoded.get("exactPayloadPcNoSuccess"),
                "exactPayloadPcReturnedDoEmpty": c_clean.get("exactPayloadPcReturnedDoEmpty"),
                "forcedOverlapExactPayloadPcNoSuccess": c_split.get("seq5NoOIIoIooo"),
            },
            "evidence": [
                str(INPUTS["encoderAxisEquivalence"]),
                str(INPUTS["encodedSessionBinding"]),
                str(INPUTS["cleanPayloadPcControls"]),
                str(INPUTS["exactPayloadBodyControls"]),
                str(INPUTS["forcedOverlapPayloadPcSplit"]),
            ],
            "nextIfReopened": "Only new evidence that factorizes the remaining payload/pc/session family into one accepted server-visible transition can reopen pc_value.",
        },
        {
            "id": "collector_cookie_header",
            "status": "closed_by_existing_controls" if cookie_closed_by_controls and cookie_single_transition_blocker_proven else "needs_more_evidence",
            "nearestMissingPredicates": cookie_nearest.get("missingPredicates"),
            "closureChecks": {
                "cookieClosedByControls": cookie_closed_by_controls,
                "cookieSingleTransitionBlockerProven": cookie_single_transition_blocker_proven,
                "positivePresence": cookie_diff.get("positivePresence"),
                "negativePresence": cookie_diff.get("negativePresence"),
                "primaryCollectorCookieHeaderObservedRunCount": c_cookie.get("primaryCollectorCookieHeaderObservedRunCount"),
                "allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader": c_cookie.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader"),
                "collectorCookieHeadersOnlyOnBeaconOrTelemetry": c_cookie.get("collectorCookieHeadersOnlyOnBeaconOrTelemetry"),
                "stateWindowLine933NoCookieHeader": c_cookie.get("stateWindowLine933NoCookieHeader"),
                "cookieSessionGapLine933AndFreshNoCookieHeader": c_cookie.get("cookieSessionGapLine933AndFreshNoCookieHeader"),
            },
            "evidence": [
                str(INPUTS["browserServerVisibleDiff"]),
                str(INPUTS["browserCookieBridge"]),
                str(INPUTS["singleTransitionMatrix"]),
            ],
            "nextIfReopened": "Only a primary collector request with a pre-accept Cookie header that is absent from negative controls can reopen collector_cookie_header.",
        },
    ]

    closed_count = sum(1 for row in rows if row["status"] == "closed_by_existing_controls")
    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "rowCount": len(rows),
        "closedByExistingControlsCount": closed_count,
        "needsMoreEvidenceCount": len(rows) - closed_count,
        "pcValueClosedByExistingControls": rows[0]["status"] == "closed_by_existing_controls",
        "collectorCookieHeaderClosedByExistingControls": rows[1]["status"] == "closed_by_existing_controls",
        "pcValueCanPromote": False,
        "collectorCookieHeaderCanPromote": False,
        "proposalReadyCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Resolve the two nearest-miss promotion candidates by checking whether their remaining blockers are already proven by local controls.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "rows": rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "pc_value and collector_cookie_header remain closed by existing controls; neither can be promoted without new factorization or primary-collector cookie evidence.",
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "rows": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
