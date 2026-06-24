#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"
OUT = HYP / "promoted_transition_candidate_intake.json"

INPUTS = {
    "resetTerminalBoundary": RESET / "reset_terminal_boundary_audit.json",
    "hypothesisPlanCoverage": HYP / "hypothesis_plan_coverage_audit.json",
    "collectorServerExpectedState": HYP / "collector_server_expected_state_boundary_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "evidenceGatedEndToEndPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "endToEndRemainingBoundary": HYP / "end_to_end_remaining_boundary_audit.json",
    "browserCookieBridgeCandidate": HYP / "browser_cookie_bridge_candidate_audit.json",
    "encodedSessionBindingCandidate": HYP / "encoded_session_binding_candidate_audit.json",
    "currentRouteAuthority": HYP / "current_route_authority_audit.json",
    "candidateProposals": HYP / "promoted_transition_candidate_proposals.json",
    "candidateProposalsLint": HYP / "promoted_transition_candidate_proposals_lint.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def evidence_exists(value: Any) -> bool:
    if isinstance(value, str):
        return Path(value).exists()
    if isinstance(value, list):
        return bool(value) and all(evidence_exists(item) for item in value)
    return False


def build_proposal_rows(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    proposal_doc = docs["candidateProposals"]
    rows: list[dict[str, Any]] = []
    allowed_value_chains = set((proposal_doc.get("schema") or {}).get("valueChainAllowed") or [])
    for proposal in proposal_doc.get("proposals") or []:
        value_chain = proposal.get("valueChain")
        negative_refs = proposal.get("negativeControlRefs")
        row = {
            "id": f"proposal:{proposal.get('id')}",
            "evidence": proposal.get("evidence"),
            "reportedCount": 1,
            "promotedCount": 1,
            "preAccept": proposal.get("preAccept"),
            "clientVisible": proposal.get("clientVisible"),
            "pureProtocolConstructible": proposal.get("pureProtocolConstructible"),
            "valueChain": value_chain,
            "negativeControlRefs": negative_refs,
            "contradicted": proposal.get("contradicted"),
            "evidenceExists": evidence_exists(proposal.get("evidence")),
            "negativeControlRefsExist": evidence_exists(negative_refs),
            "valueChainAllowed": value_chain in allowed_value_chains,
            "source": "candidateProposals",
        }
        accepted = (
            row["preAccept"] is True
            and row["clientVisible"] is True
            and row["pureProtocolConstructible"] is True
            and row["valueChainAllowed"] is True
            and row["evidenceExists"] is True
            and row["negativeControlRefsExist"] is True
            and row["contradicted"] is not True
        )
        row["candidateAccepted"] = accepted
        row["whyNotAccepted"] = None if accepted else "proposal does not satisfy all intake predicates"
        rows.append(row)
    return rows


def build_candidate_rows(docs: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    reset = checks(docs["resetTerminalBoundary"])
    hyp = checks(docs["hypothesisPlanCoverage"])
    collector = checks(docs["collectorServerExpectedState"])
    e2e = checks(docs["endToEndRemainingBoundary"])
    cookie = checks(docs["browserCookieBridgeCandidate"])
    encoded = checks(docs["encodedSessionBindingCandidate"])
    route = checks(docs["currentRouteAuthority"])

    rows: list[dict[str, Any]] = []

    raw_sources = [
        {
            "id": "reset_single_transition_candidates",
            "evidence": str(INPUTS["resetTerminalBoundary"]),
            "reportedCount": reset.get("singleTransitionCandidateCount"),
            "promotedCount": reset.get("promotedSingleTransitionCandidateCount"),
            "preAccept": None,
            "clientVisible": reset.get("stateMachineClientVisibleProxyCount", 0) not in {None, 0},
            "pureProtocolConstructible": None,
            "valueChain": None,
            "contradicted": reset.get("noCurrentRouteToPhase5") is True,
        },
        {
            "id": "hypothesis_plan_current_promoted_transition",
            "evidence": str(INPUTS["hypothesisPlanCoverage"]),
            "reportedCount": hyp.get("currentPromotedSingleTransitionCandidateCount"),
            "promotedCount": hyp.get("currentPromotedSingleTransitionCandidateCount"),
            "preAccept": None,
            "clientVisible": None,
            "pureProtocolConstructible": None,
            "valueChain": None,
            "contradicted": hyp.get("minimalExperimentMissingAllowedByGate") is True,
        },
        {
            "id": "collector_server_expected_state_proxy",
            "evidence": str(INPUTS["collectorServerExpectedState"]),
            "reportedCount": collector.get("clientVisibleProxyFoundCount"),
            "promotedCount": collector.get("promotedSingleTransitionCandidateCount"),
            "preAccept": None,
            "clientVisible": collector.get("clientVisibleProxyFoundCount", 0) not in {None, 0},
            "pureProtocolConstructible": None,
            "valueChain": (
                collector.get("requestMirroredStateCount", 0),
                collector.get("cookieMirroredStateCount", 0),
                collector.get("riskVerifyMirroredStateCount", 0),
            ),
            "contradicted": collector.get("serverStateBoundaryNotClientVisible") is True,
        },
        {
            "id": "end_to_end_remaining_boundary",
            "evidence": str(INPUTS["endToEndRemainingBoundary"]),
            "reportedCount": e2e.get("remainingBoundaryCount"),
            "promotedCount": e2e.get("promotedSingleTransitionCandidateCount"),
            "preAccept": None,
            "clientVisible": None,
            "pureProtocolConstructible": None,
            "valueChain": None,
            "contradicted": e2e.get("exactPayloadPcAndExactBodyNoSuccess") is True,
        },
        {
            "id": "browser_cookie_bridge",
            "evidence": str(INPUTS["browserCookieBridgeCandidate"]),
            "reportedCount": cookie.get("timelineFileCount"),
            "promotedCount": cookie.get("promotedSingleTransitionCandidateCount"),
            "preAccept": None,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "valueChain": "cookie",
            "contradicted": (
                cookie.get("cookieBridgeCorrelationAlsoPresentInTfFailures") is True
                or cookie.get("allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader") is True
            ),
        },
        {
            "id": "encoded_session_binding",
            "evidence": str(INPUTS["encodedSessionBindingCandidate"]),
            "reportedCount": encoded.get("singleAxisRowCount"),
            "promotedCount": encoded.get("promotedSingleTransitionCandidateCount"),
            "preAccept": True,
            "clientVisible": True,
            "pureProtocolConstructible": False,
            "valueChain": "request",
            "contradicted": encoded.get("singleAxisEliminatedCount") == encoded.get("singleAxisRowCount"),
        },
        {
            "id": "current_route_authority",
            "evidence": str(INPUTS["currentRouteAuthority"]),
            "reportedCount": route.get("staleReadyArtifactCount"),
            "promotedCount": route.get("currentPromotedSingleTransitionCandidateCount"),
            "preAccept": None,
            "clientVisible": None,
            "pureProtocolConstructible": None,
            "valueChain": None,
            "contradicted": route.get("liveProbeClosedNoSuccess") is True,
        },
    ]

    for source in raw_sources:
        promoted_count = source.get("promotedCount")
        if promoted_count in {None, 0}:
            rows.append(
                {
                    **source,
                    "candidateAccepted": False,
                    "whyNotAccepted": "source reports zero promoted transition candidates",
                }
            )
            continue
        accepted = (
            promoted_count == 1
            and source.get("preAccept") is True
            and source.get("clientVisible") is True
            and source.get("pureProtocolConstructible") is True
            and bool(source.get("valueChain"))
            and source.get("contradicted") is not True
        )
        rows.append(
            {
                **source,
                "candidateAccepted": accepted,
                "whyNotAccepted": None
                if accepted
                else "reported candidate does not satisfy all intake predicates",
            }
        )

    rows.extend(build_proposal_rows(docs))
    return rows


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    rows = build_candidate_rows(docs)
    accepted = [row for row in rows if row.get("candidateAccepted") is True]
    proposal_rows = [row for row in rows if row.get("source") == "candidateProposals"]

    pre_accept_count = sum(1 for row in rows if row.get("preAccept") is True)
    client_visible_count = sum(1 for row in rows if row.get("clientVisible") is True)
    constructible_count = sum(1 for row in rows if row.get("pureProtocolConstructible") is True)
    value_chain_count = sum(1 for row in rows if bool(row.get("valueChain")))
    contradicted_count = sum(1 for row in rows if row.get("contradicted") is True)
    promoted = len(accepted)
    ready = promoted == 1
    goal = docs["goalGap"]
    poc = checks(docs["evidenceGatedEndToEndPoc"])
    proposal_lint = checks(docs["candidateProposalsLint"])

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "candidateSourceCount": len(rows),
        "proposalCount": len(proposal_rows),
        "proposalAcceptedCount": sum(1 for row in proposal_rows if row.get("candidateAccepted") is True),
        "proposalInvalidCount": sum(1 for row in proposal_rows if row.get("candidateAccepted") is not True),
        "proposalLintExists": bool(docs["candidateProposalsLint"]),
        "proposalLintAllStructurallyValid": proposal_lint.get("allProposalsStructurallyValid") is True,
        "proposalLintPromotableShapeCount": proposal_lint.get("promotableShapeCount"),
        "candidateCount": promoted,
        "preAcceptCandidateCount": pre_accept_count,
        "clientVisibleCandidateCount": client_visible_count,
        "pureProtocolConstructibleCandidateCount": constructible_count,
        "valueChainCandidateCount": value_chain_count,
        "negativeControlContradictedCandidateCount": contradicted_count,
        "promotedSingleTransitionCandidateCount": promoted,
        "resetReadyForFreshExperiment": checks(docs["resetTerminalBoundary"]).get("readyForFreshExperiment"),
        "resetNoCurrentRouteToPhase5": checks(docs["resetTerminalBoundary"]).get("noCurrentRouteToPhase5"),
        "hypothesisPlanStaleHistoricalNextPointerCount": checks(docs["hypothesisPlanCoverage"]).get("staleHistoricalNextPointerCount"),
        "evidenceGatedPocBlockedByGate": poc.get("blockedByGate") is True,
        "endToEndPureProtocolPocMissing": "end_to_end_pure_protocol_poc" in (summary(goal).get("blockingOrMissing") or []),
        "readyForFreshExperiment": ready,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Machine-gate any proposed next network experiment behind one promoted pre-accept client-visible pure-protocol transition.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "candidateRows": rows,
        "promotedCandidates": accepted,
        "evidenceBlocks": [
            {
                "id": "intake_gate",
                "facts": [
                    f"candidateSourceCount={checks_out['candidateSourceCount']}",
                    f"promotedSingleTransitionCandidateCount={checks_out['promotedSingleTransitionCandidateCount']}",
                    f"negativeControlContradictedCandidateCount={checks_out['negativeControlContradictedCandidateCount']}",
                    f"resetReadyForFreshExperiment={checks_out['resetReadyForFreshExperiment']}",
                    f"resetNoCurrentRouteToPhase5={checks_out['resetNoCurrentRouteToPhase5']}",
                    f"evidenceGatedPocBlockedByGate={checks_out['evidenceGatedPocBlockedByGate']}",
                ],
                "meaning": "Current evidence sources do not provide a single promoted transition; network experiments remain gated off.",
            }
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": ready,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "No intake candidate satisfies all required predicates: pre-accept, client-visible, pure-protocol constructible, "
                "value-chain-linked, and not contradicted by existing negative controls."
                if not ready
                else "Exactly one promoted transition is ready for a minimal transition experiment."
            ),
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
