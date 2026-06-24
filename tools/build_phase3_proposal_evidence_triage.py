#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
RESET = PROTO / "reset_plan"
GOAL = PROTO / "goal_audit"
PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
OUT = HYP / "phase3_proposal_evidence_triage.json"

NAMED_INPUTS = {
    "authoritativePlan": PLAN,
    "candidateProposals": HYP / "promoted_transition_candidate_proposals.json",
    "candidateProposalsLint": HYP / "promoted_transition_candidate_proposals_lint.json",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "collectorServerExpectedState": HYP / "collector_server_expected_state_boundary_audit.json",
    "endToEndRemainingBoundary": HYP / "end_to_end_remaining_boundary_audit.json",
    "browserCookieBridgeCandidate": HYP / "browser_cookie_bridge_candidate_audit.json",
    "encodedSessionBindingCandidate": HYP / "encoded_session_binding_candidate_audit.json",
    "currentRouteAuthority": HYP / "current_route_authority_audit.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def value(doc: dict[str, Any], key: str) -> Any:
    if key in doc:
        return doc.get(key)
    return checks(doc).get(key)


def evidence_exists(v: Any) -> bool:
    if isinstance(v, str):
        return Path(v).exists()
    if isinstance(v, list):
        return bool(v) and all(evidence_exists(item) for item in v)
    return False


def proposal_worthy(row: dict[str, Any]) -> bool:
    return (
        row.get("preAccept") is True
        and row.get("clientVisible") is True
        and row.get("pureProtocolConstructible") is True
        and row.get("valueChain") in {"request", "cookie", "risk", "verify"}
        and row.get("evidenceExists") is True
        and row.get("negativeControlRefsExist") is True
        and row.get("contradicted") is not True
    )


def named_rows(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []

    def add(
        source: str,
        evidence: Path,
        *,
        pre_accept: bool | None,
        client_visible: bool | None,
        pure_protocol_constructible: bool | None,
        value_chain: str | None,
        negative_refs: list[str] | None,
        contradicted: bool | None,
        reason: str,
    ) -> None:
        row = {
            "source": source,
            "evidence": str(evidence),
            "evidenceExists": evidence.exists(),
            "preAccept": pre_accept,
            "clientVisible": client_visible,
            "pureProtocolConstructible": pure_protocol_constructible,
            "valueChain": value_chain,
            "negativeControlRefs": negative_refs or [],
            "negativeControlRefsExist": evidence_exists(negative_refs or []),
            "contradicted": contradicted,
            "reason": reason,
        }
        row["proposalWorthy"] = proposal_worthy(row)
        rows.append(row)

    reset = checks(docs["resetTerminal"])
    collector = checks(docs["collectorServerExpectedState"])
    e2e = checks(docs["endToEndRemainingBoundary"])
    cookie = checks(docs["browserCookieBridgeCandidate"])
    encoded = checks(docs["encodedSessionBindingCandidate"])
    route = checks(docs["currentRouteAuthority"])

    add(
        "reset_terminal_single_transition",
        NAMED_INPUTS["resetTerminal"],
        pre_accept=None,
        client_visible=reset.get("stateMachineClientVisibleProxyCount", 0) not in {None, 0},
        pure_protocol_constructible=None,
        value_chain=None,
        negative_refs=[str(NAMED_INPUTS["resetTerminal"])],
        contradicted=reset.get("noCurrentRouteToPhase5") is True,
        reason="terminal audit reports singleTransitionCandidateCount=0 and promotedSingleTransitionCandidateCount=0",
    )
    add(
        "collector_server_expected_state",
        NAMED_INPUTS["collectorServerExpectedState"],
        pre_accept=None,
        client_visible=collector.get("clientVisibleProxyFoundCount", 0) not in {None, 0},
        pure_protocol_constructible=None,
        value_chain=None,
        negative_refs=[str(NAMED_INPUTS["collectorServerExpectedState"])],
        contradicted=collector.get("serverStateBoundaryNotClientVisible") is True,
        reason="remaining server expected state is explicitly non-client-visible",
    )
    add(
        "end_to_end_remaining_boundary",
        NAMED_INPUTS["endToEndRemainingBoundary"],
        pre_accept=True,
        client_visible=True,
        pure_protocol_constructible=False,
        value_chain="request",
        negative_refs=[str(NAMED_INPUTS["endToEndRemainingBoundary"])],
        contradicted=e2e.get("exactPayloadPcAndExactBodyNoSuccess") is True,
        reason="remaining boundary is coupled; exact payload/pc/body controls did not produce success",
    )
    add(
        "browser_cookie_bridge",
        NAMED_INPUTS["browserCookieBridgeCandidate"],
        pre_accept=None,
        client_visible=True,
        pure_protocol_constructible=False,
        value_chain="cookie",
        negative_refs=[str(NAMED_INPUTS["browserCookieBridgeCandidate"])],
        contradicted=(
            cookie.get("cookieBridgeCorrelationAlsoPresentInTfFailures") is True
            or cookie.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader") is True
        ),
        reason="cookie bridge is present in tf failures and primary collector flow has no Cookie header",
    )
    add(
        "encoded_session_binding",
        NAMED_INPUTS["encodedSessionBindingCandidate"],
        pre_accept=True,
        client_visible=True,
        pure_protocol_constructible=False,
        value_chain="request",
        negative_refs=[str(NAMED_INPUTS["encodedSessionBindingCandidate"])],
        contradicted=encoded.get("singleAxisEliminatedCount") == encoded.get("singleAxisRowCount"),
        reason="all six single-axis encoded/session controls are eliminated",
    )
    add(
        "stale_ready_route_authority",
        NAMED_INPUTS["currentRouteAuthority"],
        pre_accept=None,
        client_visible=None,
        pure_protocol_constructible=None,
        value_chain=None,
        negative_refs=[str(NAMED_INPUTS["currentRouteAuthority"])],
        contradicted=route.get("liveProbeClosedNoSuccess") is True,
        reason="old ready signals are stale after authorized live probe closed no-success",
    )
    return rows


def recursive_signal_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(PROTO.rglob("*.json")):
        try:
            doc = load_json(path)
        except Exception:
            continue
        c = checks(doc)
        ready = c.get("readyForFreshExperiment")
        promoted = c.get("promotedSingleTransitionCandidateCount")
        current_promoted = c.get("currentPromotedSingleTransitionCandidateCount")
        if ready is True or (isinstance(promoted, int) and promoted > 0) or (isinstance(current_promoted, int) and current_promoted > 0):
            rows.append(
                {
                    "path": str(path),
                    "readyForFreshExperiment": ready,
                    "promotedSingleTransitionCandidateCount": promoted,
                    "currentPromotedSingleTransitionCandidateCount": current_promoted,
                    "goalComplete": c.get("goalComplete"),
                }
            )
    return rows


def main() -> int:
    docs = {name: load_json(path) for name, path in NAMED_INPUTS.items() if path.suffix == ".json"}
    rows = named_rows(docs)
    recursive_rows = recursive_signal_rows()
    proposal_doc = docs.get("candidateProposals", {})
    proposal_count = len(proposal_doc.get("proposals") or [])
    worthy = [row for row in rows if row.get("proposalWorthy") is True]
    checks_out = {
        "authoritativePlanExists": PLAN.exists(),
        "allNamedInputsExist": all(path.exists() for path in NAMED_INPUTS.values()),
        "namedInputCount": len(NAMED_INPUTS),
        "triagedSourceCount": len(rows),
        "proposalCount": proposal_count,
        "proposalWorthyEvidenceCount": len(worthy),
        "recursiveJsonReadyOrPromotedSignalCount": len(recursive_rows),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Phase 3 triage: decide whether current local evidence can be written into promoted_transition_candidate_proposals.json.",
        "inputs": {name: str(path) for name, path in NAMED_INPUTS.items()},
        "rows": rows,
        "recursiveReadyOrPromotedSignals": recursive_rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedProposal": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "No current local evidence row satisfies proposal predicates; keep candidate proposals empty and do not run network."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
