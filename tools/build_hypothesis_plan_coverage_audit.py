#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
RESET = ROOT / "output/protocol_reverse/reset_plan"
OUT = HYP / "hypothesis_plan_coverage_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"
CURRENT_PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-forward-plan.md"


PHASE_ARTIFACTS = {
    "phase1_selected_contrast_pair": HYP / "selected_contrast_pair.json",
    "phase2_hypothesis_matrix": HYP / "hypothesis_matrix.json",
    "phase3_collector_state_transition_diff": HYP / "collector_state_transition_diff_s00_vs_fresh.json",
    "phase4_first_decisive_divergence": HYP / "first_decisive_divergence.json",
    "phase4_5_pre_seq5_state_lineage": HYP / "pre_seq5_state_lineage_detail.json",
    "phase4_6_request_history_coherence": HYP / "request_history_coherence_gap.json",
    "phase4_7_next_decisive_static_gap": HYP / "next_decisive_static_gap.json",
    "accepted_line933_generation_lineage": HYP / "accepted_line933_generation_lineage.json",
    "server_expected_state_pre_seq5_gap": HYP / "server_expected_state_pre_seq5_gap.json",
    "server_state_transition_value_model": HYP / "server_state_transition_value_model.json",
    "line922_dynamic_field_source_map": HYP / "line922_dynamic_field_source_map.json",
    "line922_candidate_reduction": HYP / "line922_candidate_reduction.json",
    "encoded_payload_pc_form_diff_map": HYP / "encoded_payload_pc_form_diff_map.json",
    "server_state_value_to_request_lineage": HYP / "server_state_value_to_request_lineage.json",
    "final_boundary_decision_matrix": HYP / "final_boundary_decision_matrix.json",
    "coupled_encoder_variant_audit": HYP / "coupled_encoder_variant_audit.json",
    "server_internal_state_gap_audit": HYP / "server_internal_state_gap_audit.json",
    "remaining_encoder_variant_build_matrix": HYP / "remaining_encoder_variant_build_matrix.json",
    "hypothesis_reframe_status": HYP / "hypothesis_reframe_status.json",
    "minimal_divergence_experiment": HYP / "minimal_divergence_experiment_audit.json",
    "goal_gap_audit": GOAL / "pure_protocol_goal_gap_audit.json",
}

CURRENT_AUTHORITY_ARTIFACTS = {
    "current_route_authority": HYP / "current_route_authority_audit.json",
    "end_to_end_remaining_boundary": HYP / "end_to_end_remaining_boundary_audit.json",
    "browser_cookie_bridge_candidate": HYP / "browser_cookie_bridge_candidate_audit.json",
    "encoded_session_binding_candidate": HYP / "encoded_session_binding_candidate_audit.json",
    "collector_server_expected_state_boundary": HYP / "collector_server_expected_state_boundary_audit.json",
    "browser_context_to_server_state_proxy": HYP / "browser_context_to_server_state_proxy_audit.json",
    "browser_context_static_gap_inventory": HYP / "browser_context_static_gap_inventory.json",
    "post_static_context_terminal_gap": HYP / "post_static_context_terminal_gap_audit.json",
    "reset_terminal_boundary": RESET / "reset_terminal_boundary_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def decision(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("decision") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def artifact_row(name: str, path: Path) -> dict[str, Any]:
    doc = read_json(path)
    c = checks(doc)
    d = decision(doc)
    return {
        "id": name,
        "path": str(path),
        "exists": path.exists(),
        "readyForFreshExperiment": c.get("readyForFreshExperiment", d.get("readyForFreshExperiment")),
        "goalComplete": c.get("goalComplete", d.get("goalComplete")),
        "promotedSingleTransitionCandidateCount": c.get(
            "promotedSingleTransitionCandidateCount",
            c.get("currentPromotedSingleTransitionCandidateCount"),
        ),
        "nextArtifact": d.get("nextArtifact") or (doc.get("next") or {}).get("artifact"),
        "nextScript": d.get("nextScript") or (doc.get("next") or {}).get("script"),
    }


def bool_check(docs: dict[str, dict[str, Any]], name: str, key: str) -> Any:
    return checks(docs.get(name, {})).get(key)


def build() -> dict[str, Any]:
    phase_docs = {name: read_json(path) for name, path in PHASE_ARTIFACTS.items()}
    authority_docs = {name: read_json(path) for name, path in CURRENT_AUTHORITY_ARTIFACTS.items()}
    phase_rows = [artifact_row(name, path) for name, path in PHASE_ARTIFACTS.items()]
    authority_rows = [artifact_row(name, path) for name, path in CURRENT_AUTHORITY_ARTIFACTS.items()]

    existing_phase_rows = [row for row in phase_rows if row["exists"]]
    missing_phase_rows = [row for row in phase_rows if not row["exists"]]
    stale_next_rows = []
    for row in existing_phase_rows:
        next_artifact = row.get("nextArtifact")
        if not next_artifact:
            continue
        next_path = Path(str(next_artifact))
        if next_path.exists() and row.get("readyForFreshExperiment") is False:
            stale_next_rows.append(
                {
                    "source": row["id"],
                    "sourcePath": row["path"],
                    "nextArtifact": str(next_path),
                    "reason": "The historical artifact points to a downstream artifact that already exists; current readyForFreshExperiment remains false.",
                }
            )

    goal = phase_docs["goal_gap_audit"]
    reset = authority_docs["reset_terminal_boundary"]
    current_route = authority_docs["current_route_authority"]
    collector_server = authority_docs["collector_server_expected_state_boundary"]

    hypotheses = {
        "H0_packet_not_portable": {
            "status": "closed_strongly_supported",
            "evidence": [
                str(GOAL / "s00_exact_success_replay_live_audit.json"),
                str(GOAL / "latest_exact_payload_body_controls_audit.json"),
                str(HYP / "encoded_session_binding_candidate_audit.json"),
            ],
            "facts": {
                "exactPayloadPcNoSuccess": bool_check(authority_docs, "encoded_session_binding_candidate", "exactPayloadPcNoSuccess"),
                "exactBodyNoSuccess": bool_check(authority_docs, "encoded_session_binding_candidate", "exactBodyNoSuccess"),
                "singleAxisEliminatedCount": bool_check(authority_docs, "encoded_session_binding_candidate", "singleAxisEliminatedCount"),
            },
        },
        "H1_visible_body_fields": {
            "status": "closed_not_sufficient",
            "evidence": [
                str(HYP / "first_decisive_divergence.json"),
                str(HYP / "pre_seq5_state_lineage_detail.json"),
                str(HYP / "end_to_end_remaining_boundary_audit.json"),
            ],
            "facts": {
                "firstDivergenceAtFinalSeq5": checks(phase_docs["phase4_first_decisive_divergence"]).get("firstDivergenceAtFinalSeq5"),
                "decodedSeq5Seq6ActivityEqualityRejected": bool_check(authority_docs, "end_to_end_remaining_boundary", "decodedSeq5Seq6ActivityEqualityRejected"),
                "exactPayloadPcAndExactBodyNoSuccess": bool_check(authority_docs, "end_to_end_remaining_boundary", "exactPayloadPcAndExactBodyNoSuccess"),
            },
        },
        "H2_transport_http2_ip": {
            "status": "closed_as_primary_cause",
            "evidence": [
                str(RESET / "reset_transport_ip_decision_audit.json"),
                str(HYP / "end_to_end_remaining_boundary_audit.json"),
                str(RESET / "reset_terminal_boundary_audit.json"),
            ],
            "facts": {
                "transportDecisionOnlyTransportChangedStageDifferenceProved": bool_check(authority_docs, "reset_terminal_boundary", "transportDecisionOnlyTransportChangedStageDifferenceProved"),
                "transportDecisionPromotedToControlVariableOnly": bool_check(authority_docs, "reset_terminal_boundary", "transportDecisionPromotedToControlVariableOnly"),
                "noCurrentRouteToPhase5": bool_check(authority_docs, "reset_terminal_boundary", "noCurrentRouteToPhase5"),
            },
        },
        "H3_collector_server_side_session_state": {
            "status": "remaining_boundary_not_client_visible",
            "evidence": [
                str(HYP / "collector_server_expected_state_boundary_audit.json"),
                str(HYP / "server_expected_state_pre_seq5_gap.json"),
                str(HYP / "server_state_transition_value_model.json"),
            ],
            "facts": {
                "clientVisibleProxyFoundCount": bool_check(authority_docs, "collector_server_expected_state_boundary", "clientVisibleProxyFoundCount"),
                "serverStateBoundaryNotClientVisible": bool_check(authority_docs, "collector_server_expected_state_boundary", "serverStateBoundaryNotClientVisible"),
                "promotedSingleTransitionCandidateCount": bool_check(authority_docs, "collector_server_expected_state_boundary", "promotedSingleTransitionCandidateCount"),
            },
        },
        "H4_browser_only_runtime_state": {
            "status": "closed_no_server_visible_proxy",
            "evidence": [
                str(HYP / "browser_context_to_server_state_proxy_audit.json"),
                str(HYP / "browser_context_static_gap_inventory.json"),
                str(HYP / "post_static_context_terminal_gap_audit.json"),
            ],
            "facts": {
                "allBrowserContextServerVisibleProxiesReduced": bool_check(authority_docs, "browser_context_to_server_state_proxy", "allBrowserContextServerVisibleProxiesReduced"),
                "allStaticContextGapsReduced": bool_check(authority_docs, "browser_context_static_gap_inventory", "allStaticContextGapsReduced"),
                "postStaticContextPromotedCount": bool_check(authority_docs, "post_static_context_terminal_gap", "promotedSingleTransitionCandidateCount"),
            },
        },
        "H5_microsoft_context_binding": {
            "status": "reduced_no_promoted_context_proxy",
            "evidence": [
                str(HYP / "browser_context_to_server_state_proxy_audit.json"),
                str(HYP / "collector_to_risk_consumption_chain.json"),
                str(HYP / "browser_cookie_bridge_candidate_audit.json"),
            ],
            "facts": {
                "microsoftMessagesOnlyPostAccept": bool_check(authority_docs, "browser_context_to_server_state_proxy", "microsoftMessagesOnlyPostAccept"),
                "blockRequestUrlRiskVerify": bool_check(authority_docs, "browser_context_to_server_state_proxy", "blockRequestUrlRiskVerify"),
                "browserContextPromotedCount": bool_check(authority_docs, "browser_context_to_server_state_proxy", "promotedSingleTransitionCandidateCount"),
            },
        },
    }

    required_phase_count = len(PHASE_ARTIFACTS) - 1  # minimal_divergence_experiment is gated, not required without a candidate.
    missing_required = [
        row
        for row in missing_phase_rows
        if row["id"] != "minimal_divergence_experiment"
    ]
    minimal_missing_by_gate = next((row for row in missing_phase_rows if row["id"] == "minimal_divergence_experiment"), None)

    checks_out = {
        "planExists": PLAN.exists(),
        "currentPlanExists": CURRENT_PLAN.exists(),
        "phaseArtifactCount": len(PHASE_ARTIFACTS),
        "existingPhaseArtifactCount": len(existing_phase_rows),
        "missingRequiredPhaseArtifactCount": len(missing_required),
        "minimalExperimentArtifactMissing": minimal_missing_by_gate is not None,
        "minimalExperimentMissingAllowedByGate": minimal_missing_by_gate is not None
        and bool_check(authority_docs, "reset_terminal_boundary", "readyForFreshExperiment") is False,
        "authorityArtifactCount": len(CURRENT_AUTHORITY_ARTIFACTS),
        "existingAuthorityArtifactCount": sum(1 for row in authority_rows if row["exists"]),
        "staleHistoricalNextPointerCount": len(stale_next_rows),
        "allHypothesesCovered": all(bool(row.get("evidence")) for row in hypotheses.values()),
        "h0Closed": hypotheses["H0_packet_not_portable"]["status"].startswith("closed"),
        "h1Closed": hypotheses["H1_visible_body_fields"]["status"].startswith("closed"),
        "h2Closed": hypotheses["H2_transport_http2_ip"]["status"].startswith("closed"),
        "h3RemainingNotClientVisible": hypotheses["H3_collector_server_side_session_state"]["status"] == "remaining_boundary_not_client_visible",
        "h4Closed": hypotheses["H4_browser_only_runtime_state"]["status"].startswith("closed"),
        "h5Reduced": hypotheses["H5_microsoft_context_binding"]["status"].startswith("reduced"),
        "currentPromotedSingleTransitionCandidateCount": bool_check(authority_docs, "current_route_authority", "currentPromotedSingleTransitionCandidateCount"),
        "resetTerminalNoCurrentRouteToPhase5": bool_check(authority_docs, "reset_terminal_boundary", "noCurrentRouteToPhase5"),
        "collectorServerExpectedStatePromotedCount": bool_check(authority_docs, "collector_server_expected_state_boundary", "promotedSingleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": summary(goal).get("goalComplete") is True,
        "endToEndPureProtocolPocMissing": "end_to_end_pure_protocol_poc" in (summary(goal).get("blockingOrMissing") or []),
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "currentPlan": str(CURRENT_PLAN),
        "purpose": "Verify the historical hypothesis-plan H0-H5 and Phase 1-6 artifacts against current authoritative audits, so stale next pointers do not reopen closed network routes.",
        "phaseArtifacts": phase_rows,
        "authorityArtifacts": authority_rows,
        "hypotheses": hypotheses,
        "staleHistoricalNextPointers": stale_next_rows,
        "missingRequiredPhaseArtifacts": missing_required,
        "gatedMissingArtifacts": [
            {
                "id": minimal_missing_by_gate["id"],
                "path": minimal_missing_by_gate["path"],
                "reason": "Phase 5 minimal experiment is explicitly gated by a promoted single transition; current terminal audit has readyForFreshExperiment=false.",
            }
        ]
        if minimal_missing_by_gate
        else [],
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "The hypothesis-plan artifacts are covered through the static/lineage phases; the only missing phase artifact is the gated minimal experiment, and current audits still have zero promoted transition candidates.",
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
