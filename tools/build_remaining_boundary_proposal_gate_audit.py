#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "remaining_boundary_proposal_gate_audit.json"

INPUTS = {
    "currentPlan": REPO / "docs/pure-protocol-human-evidence-first-current-plan.md",
    "singleTransitionCandidateMatrix": BASE / "single_transition_candidate_matrix.json",
    "serverStateValueToRequestLineage": BASE / "server_state_value_to_request_lineage.json",
    "outerSessionTupleFactorization": BASE / "outer_session_tuple_factorization.json",
    "encoderAxisEquivalence": BASE / "encoder_axis_equivalence.json",
    "serverExpectedStateObservableProxy": BASE / "server_expected_state_observable_proxy.json",
    "collectorServerExpectedStateBoundary": BASE / "collector_server_expected_state_boundary_audit.json",
    "collectorToRiskConsumptionChain": BASE / "collector_to_risk_consumption_chain.json",
    "encodedSessionBindingCandidate": BASE / "encoded_session_binding_candidate_audit.json",
    "browserCookieBridgeCandidate": BASE / "browser_cookie_bridge_candidate_audit.json",
    "promotedTransitionCandidateIntake": BASE / "promoted_transition_candidate_intake.json",
    "promotedTransitionCandidateProposals": BASE / "promoted_transition_candidate_proposals.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def evidence(path: Path, *fields: str) -> dict[str, Any]:
    row: dict[str, Any] = {"path": str(path)}
    if fields:
        row["fields"] = list(fields)
    return row


def gate_row(
    gate_id: str,
    title: str,
    pre_accept: bool | None,
    client_visible: bool | None,
    constructible: bool | None,
    value_chain: str | None,
    negative_controls: list[str],
    contradicted: bool | None,
    evidence_rows: list[dict[str, Any]],
    blockers: list[str],
) -> dict[str, Any]:
    value_chain_allowed = value_chain in {"request", "cookie", "risk", "verify"}
    negative_refs_exist = bool(negative_controls) and all(Path(path).exists() for path in negative_controls)
    evidence_exists = bool(evidence_rows) and all(Path(row["path"]).exists() for row in evidence_rows)
    proposal_ready = (
        pre_accept is True
        and client_visible is True
        and constructible is True
        and value_chain_allowed
        and negative_refs_exist
        and evidence_exists
        and contradicted is False
        and not blockers
    )
    return {
        "id": gate_id,
        "title": title,
        "proposalFields": {
            "preAccept": pre_accept,
            "clientVisible": client_visible,
            "pureProtocolConstructible": constructible,
            "valueChain": value_chain,
            "valueChainAllowed": value_chain_allowed,
            "negativeControlRefs": negative_controls,
            "negativeControlRefsExist": negative_refs_exist,
            "contradicted": contradicted,
            "evidenceExists": evidence_exists,
        },
        "proposalReady": proposal_ready,
        "evidence": evidence_rows,
        "blockers": blockers,
    }


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items() if path.suffix == ".json"}
    single = docs["singleTransitionCandidateMatrix"]
    lineage = docs["serverStateValueToRequestLineage"]
    outer = docs["outerSessionTupleFactorization"]
    encoder = docs["encoderAxisEquivalence"]
    server_proxy = docs["serverExpectedStateObservableProxy"]
    collector_expected = docs["collectorServerExpectedStateBoundary"]
    risk_chain = docs["collectorToRiskConsumptionChain"]
    encoded = docs["encodedSessionBindingCandidate"]
    cookie = docs["browserCookieBridgeCandidate"]
    intake = docs["promotedTransitionCandidateIntake"]
    proposals = docs["promotedTransitionCandidateProposals"]

    c_single = checks(single)
    s_single = summary(single)
    c_lineage = checks(lineage)
    c_outer = checks(outer)
    s_outer = summary(outer)
    c_encoder = checks(encoder)
    s_encoder = summary(encoder)
    c_server_proxy = checks(server_proxy)
    c_collector_expected = checks(collector_expected)
    c_risk_chain = checks(risk_chain)
    c_encoded = checks(encoded)
    c_cookie = checks(cookie)
    c_intake = checks(intake)

    rows = [
        gate_row(
            "RB1_outer_session_tuple",
            "Outer session tuple: uuid/cs/ci/sid/p1/vid/cts",
            pre_accept=True,
            client_visible=True,
            constructible=False,
            value_chain="request",
            negative_controls=[
                str(INPUTS["serverStateValueToRequestLineage"]),
                str(INPUTS["outerSessionTupleFactorization"]),
            ],
            contradicted=True,
            evidence_rows=[
                evidence(INPUTS["serverStateValueToRequestLineage"], "remainingBoundaries.L1_outer_session_tuple"),
                evidence(INPUTS["outerSessionTupleFactorization"], "summary.readyGroupCount", "checks.noReadyOuterTupleGroup"),
            ],
            blockers=[
                "remaining boundary is a coherent tuple, not one transition",
                f"outerSingleReadyGroupCount={s_outer.get('singleReadyGroupCount')}",
                f"outerNoSingleFieldExperimentReady={c_outer.get('noSingleFieldExperimentReady')}",
                f"outerBindingControlsRejected={c_lineage.get('outerBindingControlsRejected')}",
            ],
        ),
        gate_row(
            "RB2_pc_marker_uuid_encoder_binding",
            "pc/marker/uuid/payload encoder binding",
            pre_accept=True,
            client_visible=True,
            constructible=False,
            value_chain="request",
            negative_controls=[
                str(INPUTS["encodedSessionBindingCandidate"]),
                str(INPUTS["encoderAxisEquivalence"]),
            ],
            contradicted=True,
            evidence_rows=[
                evidence(INPUTS["encodedSessionBindingCandidate"], "checks.singleAxisEliminatedCount", "checks.remainingDiffKeysArePayloadPcSession"),
                evidence(INPUTS["encoderAxisEquivalence"], "summary.readyAxisCount", "checks.markerAndPcAxesRemainIndependent"),
            ],
            blockers=[
                "single-axis encoded session controls are eliminated",
                "remaining encoder axes are a coupled family, not one proposal-safe transition",
                f"singleAxisEliminatedCount={c_encoded.get('singleAxisEliminatedCount')}",
                f"singleAxisRowCount={c_encoded.get('singleAxisRowCount')}",
                f"encoderRemainingAxisCount={s_encoder.get('remainingEncoderAxisCount')}",
                f"remainingFamilyIsIndependent2x2={c_encoder.get('remainingFamilyIsIndependent2x2')}",
            ],
        ),
        gate_row(
            "RB3_collector_server_expected_state",
            "Collector server-side expected state",
            pre_accept=None,
            client_visible=False,
            constructible=False,
            value_chain=None,
            negative_controls=[
                str(INPUTS["collectorServerExpectedStateBoundary"]),
                str(INPUTS["serverExpectedStateObservableProxy"]),
            ],
            contradicted=True,
            evidence_rows=[
                evidence(INPUTS["collectorServerExpectedStateBoundary"], "checks.clientVisibleProxyFoundCount", "checks.serverStateBoundaryNotClientVisible"),
                evidence(INPUTS["serverExpectedStateObservableProxy"], "checks.omittedPreAcceptTransitionCount", "checks.replayableClientRepresentationCount"),
            ],
            blockers=[
                "server expected state is not directly client-visible in current evidence",
                "no replayable client representation has been found",
                f"clientVisibleProxyFoundCount={c_collector_expected.get('clientVisibleProxyFoundCount')}",
                f"serverStateBoundaryNotClientVisible={c_collector_expected.get('serverStateBoundaryNotClientVisible')}",
                f"omittedPreAcceptTransitionCount={c_server_proxy.get('omittedPreAcceptTransitionCount')}",
                f"transitionHasReplayableClientRepresentation={c_server_proxy.get('transitionHasReplayableClientRepresentation')}",
            ],
        ),
        gate_row(
            "RB4_collector_success_to_risk_verify",
            "Accepted collector response -> risk/verify -> CreateAccount",
            pre_accept=False,
            client_visible=True,
            constructible=True,
            value_chain="risk",
            negative_controls=[str(INPUTS["collectorToRiskConsumptionChain"])],
            contradicted=False,
            evidence_rows=[
                evidence(INPUTS["collectorToRiskConsumptionChain"], "checks.riskContinueTokenFeedsCreateAccount", "checks.riskPx3PxdeLinkedToSuccessCollectorLine"),
            ],
            blockers=[
                "this chain is downstream of collector success and cannot explain fresh pre-accept collector rejection",
                f"riskContinueTokenFeedsCreateAccount={c_risk_chain.get('riskContinueTokenFeedsCreateAccount')}",
                f"successEntryHasChallengeSuccess0={c_risk_chain.get('successEntryHasChallengeSuccess0')}",
            ],
        ),
        gate_row(
            "RB5_browser_cookie_bridge",
            "Browser bridge/cookie header candidate",
            pre_accept=True,
            client_visible=True,
            constructible=False,
            value_chain="cookie",
            negative_controls=[str(INPUTS["browserCookieBridgeCandidate"])],
            contradicted=True,
            evidence_rows=[
                evidence(INPUTS["browserCookieBridgeCandidate"], "checks.cookieBridgeCorrelationAlsoPresentInTfFailures", "checks.allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader"),
            ],
            blockers=[
                "bridge correlation is also present in tf failures",
                "known primary collector requests have no Cookie header",
                f"cookieBridgeCorrelationAlsoPresentInTfFailures={c_cookie.get('cookieBridgeCorrelationAlsoPresentInTfFailures')}",
                f"allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader={c_cookie.get('allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader')}",
            ],
        ),
    ]

    ready = [row for row in rows if row["proposalReady"]]
    checks_out = {
        "currentPlanExists": INPUTS["currentPlan"].exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "proposalFileProposalCount": len(proposals.get("proposals") or []),
        "candidateIntakePromotedCount": c_intake.get("promotedSingleTransitionCandidateCount"),
        "singleTransitionMatrixReadyCount": s_single.get("singleTransitionCandidateCount"),
        "singleTransitionMatrixNoReadyCandidate": c_single.get("noReadySingleTransitionCandidate") is True,
        "serverLineageHasOuterTupleBoundary": c_lineage.get("hasOuterSessionTupleBoundary") is True,
        "serverLineageHasEncoderBindingBoundary": c_lineage.get("hasEncoderBindingBoundary") is True,
        "serverLineageHasServerAcceptanceStateBoundary": c_lineage.get("hasServerAcceptanceStateBoundary") is True,
        "outerSingleReadyGroupCount": s_outer.get("singleReadyGroupCount"),
        "encoderRemainingAxisCount": s_encoder.get("remainingEncoderAxisCount"),
        "serverExpectedStateClientVisibleProxyCount": c_collector_expected.get("clientVisibleProxyFoundCount"),
        "serverExpectedStateTransitionHasReplayableClientRepresentation": c_server_proxy.get("transitionHasReplayableClientRepresentation") is True,
        "proposalGateRowCount": len(rows),
        "proposalReadyRowCount": len(ready),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Apply the live proposal schema predicates to each remaining boundary before writing any promoted transition proposal.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "proposalSchemaPredicates": [
            "preAccept",
            "clientVisible",
            "pureProtocolConstructible",
            "valueChain in request|cookie|risk|verify",
            "negativeControlRefs non-empty and existing",
            "contradicted=false",
        ],
        "rows": rows,
        "summary": {
            "proposalGateRowCount": len(rows),
            "proposalReadyRowCount": len(ready),
            "readyProposalIds": [row["id"] for row in ready],
        },
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "No remaining boundary satisfies the proposal predicates. Current evidence still supports no fresh network experiment.",
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "summary": result["summary"], "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
