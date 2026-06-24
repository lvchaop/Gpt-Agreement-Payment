#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/next_decisive_static_gap.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def input_path(rel: str) -> str:
    return str(ROOT / rel)


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def decision(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("decision") or {}


def candidate(id_: str, source: str, status: str, evidence: list[str], facts: list[str], blockers: list[str], next_static: str) -> dict[str, Any]:
    return {
        "id": id_,
        "sourceArtifact": input_path(source),
        "status": status,
        "evidence": evidence,
        "facts": facts,
        "whyNotFreshExperimentYet": blockers,
        "nextStaticEvidenceNeeded": next_static,
    }


def main() -> int:
    pre = load("output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json")
    gen = load("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json")
    seq4 = load("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json")
    model = load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")
    history = load("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json")

    gen_checks = checks(gen)
    gen_inputs = gen.get("observedImportantInputs") or {}
    fresh_material = gen_inputs.get("selectedFreshFinalSeq5MaterialChecks") or {}
    controls = gen.get("existingControlsAgainstSingleVariableTests") or {}

    candidates = [
        candidate(
            "G1_tf_payload_serialized_pc_binding",
            "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json",
            "supported_static_gap_not_actionable",
            [
                input_path("output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl") + ":921-922",
                input_path("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
                input_path("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
            ],
            [
                "s00 line921 produces serialized activity material and pc before line922 payload.",
                "selected fresh final seq5 material has payloadSource=built and pcSource=computed.",
                "exact s00 payload+pc replay in a fresh outer session is rejected or returns no success.",
            ],
            [
                "The evidence identifies a live binding boundary, not which single input to change.",
                "decoded equality and exact payload/pc replay controls already falsify static payload transplant.",
            ],
            "Build line922_dynamic_field_source_map.json: enumerate every dynamic field in line920/921 activities, map each value to network response, cookie bridge, POW/WASM output, marker/clock, or template-only source.",
        ),
        candidate(
            "G2_template_sourced_final_seq5_material",
            "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json",
            "partially_supported_but_existing_controls_cover_obvious_variants",
            [
                input_path("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
                input_path("output/protocol_reverse/goal_audit/h2_fresh_tail_strongest_control_audit.json"),
                input_path("output/protocol_reverse/goal_audit/h2_fresh_tail_inner_uuid_control_audit.json"),
                input_path("output/protocol_reverse/goal_audit/outer_binding_controls_audit.json"),
            ],
            [
                f"selected fresh has aeaxSource={fresh_material.get('aeaxSourceOfflineNg')}, tailSource={fresh_material.get('tailSource')}, innerUuidSource={fresh_material.get('innerUuidSource')}, nonPxActivitySource={fresh_material.get('nonPxActivitySource')}.",
                "Existing controls already test fresh POW/WASM tail, inner uuid, decoded equality, marker/outer variants, h2 timing, and static body replay.",
            ],
            [
                "Template-sourced material is a real difference, but the current controls show obvious substitutions are not sufficient.",
                "No existing artifact proves one remaining template-sourced field is independently decisive.",
            ],
            "Use line922_dynamic_field_source_map.json to separate already-tested template fields from template-only fields that still enter payload/pc and have no negative control.",
        ),
        candidate(
            "G3_server_expected_state_after_seq4",
            "output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json",
            "supported_but_not_single_value_mutation",
            [
                input_path("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"),
                input_path("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
            ],
            [
                "s00 and fresh seq4 responses have the same handler sequence and 18 decoded parts.",
                "value-level differences are present but classified as session-specific token/challenge values.",
                "final seq5 still diverges: s00 success, fresh rejected_px561.",
            ],
            [
                "The current model does not isolate a missing transition; it only confirms final expected-state divergence.",
                "Transplanting session-specific values would change multiple variables and violate the single-transition rule.",
            ],
            "Augment server_state_transition_value_model.json with per-step handler/value lineage from response mutation to the next request field/activity field before choosing a mutation.",
        ),
        candidate(
            "G4_request_history_order",
            "output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json",
            "falsified_for_selected_contrast",
            [
                input_path("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
                input_path("output/protocol_reverse/first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781281000000_1781279930.json"),
            ],
            [
                "s00 completes msft seq1/rsc2, seq2/rsc3, and seq3/rsc4 before first bundle POW.",
                "selected fresh also completes msft seq1/rsc2, seq2/rsc3, and seq3/rsc4 before first bundle POW.",
                "request_history_coherence_gap has hasOrderGap=false.",
            ],
            [
                "There is no order gap to test for this contrast.",
                "A fresh-session experiment changing this order would not be tied to a proven divergence.",
            ],
            "No next experiment from this candidate; keep it only as a guardrail against the earlier sorted-timeline error.",
        ),
        candidate(
            "G5_browser_parent_bridge_or_in_memory_state",
            "output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json",
            "supported_gap_not_mapped_to_payload_or_server_visible_state",
            [
                input_path("output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl") + ":688-689",
                input_path("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
                input_path("output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json"),
            ],
            [
                "s00 has parent bridge cookie messages before accepted line933.",
                "line933 and fresh seq5 both have no Cookie header.",
                "cookie_session_lineage_gap identifies this as not a simple missing Cookie request header.",
            ],
            [
                "The bridge gap is not yet mapped to a specific payload-generation input or collector-visible state transition.",
                "Testing generic browser bridge behavior would violate the pure-protocol and single-transition rules.",
            ],
            "Map parent-bridge values to line920-922 activity fields or to subsequent Microsoft risk context before considering an experiment.",
        ),
    ]

    ready_candidates = [
        c for c in candidates
        if c["status"] not in {
            "supported_static_gap_not_actionable",
            "partially_supported_but_existing_controls_cover_obvious_variants",
            "supported_but_not_single_value_mutation",
            "falsified_for_selected_contrast",
            "supported_gap_not_mapped_to_payload_or_server_visible_state",
        }
    ]

    result = {
        "purpose": "Phase 4.7 static decision gate: aggregate existing lineage artifacts and determine whether any single decisive gap is ready for a fresh-session experiment.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "preSeq5StateLineageDetail": input_path("output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json"),
            "acceptedLine933GenerationLineage": input_path("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
            "serverExpectedStatePreSeq5Gap": input_path("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"),
            "serverStateTransitionValueModel": input_path("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
            "requestHistoryCoherenceGap": input_path("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
        },
        "candidateGaps": candidates,
        "decision": {
            "readyForFreshExperiment": bool(ready_candidates),
            "recommendedExperiment": None,
            "reason": "No candidate currently identifies one untested, single-variable state transition. Existing evidence narrows the next static task to line922 dynamic field/source mapping rather than a new network run.",
            "nextArtifact": input_path("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
            "nextScript": str(ROOT / "tools/build_line922_dynamic_field_source_map.py"),
        },
        "checks": {
            "preSeq5NotExperimentReady": checks(pre).get("readyForFreshExperiment") is False,
            "generationLineageNotExperimentReady": gen_checks.get("readyForFreshExperiment") is False,
            "serverExpectedStateNotExperimentReady": checks(seq4).get("readyForFreshExperiment") is False,
            "serverStateModelNotExperimentReady": checks(model).get("readyForFreshExperiment") is False,
            "requestHistoryOrderGapFalsified": checks(history).get("hasOrderGap") is False,
            "hasCandidateGaps": bool(candidates),
            "hasTfPayloadBindingCandidate": any(c["id"] == "G1_tf_payload_serialized_pc_binding" for c in candidates),
            "hasServerExpectedStateCandidate": any(c["id"] == "G3_server_expected_state_after_seq4" for c in candidates),
            "hasBrowserBridgeCandidate": any(c["id"] == "G5_browser_parent_bridge_or_in_memory_state" for c in candidates),
            "recommendedNextArtifactIsStatic": True,
            "readyForFreshExperiment": bool(ready_candidates),
        },
        "sourceDecisions": {
            "preSeq5": decision(pre),
            "acceptedLine933Generation": decision(gen),
            "serverExpectedStatePreSeq5": decision(seq4),
            "serverStateTransitionValueModel": decision(model),
            "requestHistoryCoherence": decision(history),
        },
        "controlCoverageSummary": {
            "decodedEqualityNotSufficient": bool(controls.get("decodedEqualityNotSufficient")),
            "px3CookieStatefulRetryNotSufficient": bool(controls.get("px3CookieStatefulRetryNotSufficient")),
            "parentBridgeNotSimpleCookieHeader": bool(controls.get("parentBridgeNotSimpleCookieHeader")),
            "markerAndOuterBindingNotSingleVariable": bool(controls.get("markerAndOuterBindingNotSingleVariable")),
            "decodedBodyAndH2TimingNotSufficient": bool(controls.get("decodedBodyAndH2TimingNotSufficient")),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
