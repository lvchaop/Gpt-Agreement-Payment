#!/usr/bin/env python3
from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def p(rel: str) -> str:
    return str(ROOT / rel)


def main() -> int:
    final = load("output/protocol_reverse/hypothesis_reframe/final_boundary_decision_matrix.json")
    encoded = load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")
    controls = {
        "exact_payload_pc_fresh_outer": load("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
        "clean_payload_pc": load("output/protocol_reverse/goal_audit/clean_history_payload_pc_controls_audit.json"),
        "pc_uuid": load("output/protocol_reverse/goal_audit/clean_history_pc_uuid_controls_audit.json"),
        "form_outer": load("output/protocol_reverse/goal_audit/clean_history_form_outer_controls_audit.json"),
        "outer_binding": load("output/protocol_reverse/goal_audit/outer_binding_controls_audit.json"),
        "fresh_tail_strongest": load("output/protocol_reverse/goal_audit/h2_fresh_tail_strongest_control_audit.json"),
        "inner_uuid": load("output/protocol_reverse/goal_audit/h2_inner_uuid_binding_control_audit.json"),
    }

    variants = []
    for payload_uuid_source, pc_uuid_source, marker_source, form_outer_source, payload_source, pc_source in product(
        ["fresh", "template"],
        ["payload", "fresh", "template"],
        ["fresh", "template"],
        ["fresh", "template"],
        ["built", "template-exact"],
        ["computed", "template-exact"],
    ):
        variant = {
            "payloadUuidSource": payload_uuid_source,
            "pcUuidSource": pc_uuid_source,
            "markerSource": marker_source,
            "formOuterSource": form_outer_source,
            "payloadSource": payload_source,
            "pcSource": pc_source,
        }
        matched = []
        eliminated = False
        reason = []
        if payload_source == "template-exact" and pc_source == "template-exact" and form_outer_source == "fresh":
            matched.append("forced_overlap_payload_pc_split_control")
            eliminated = True
            reason.append("exact s00 payload+pc with fresh outer returned do=[] or no success")
        if payload_source == "template-exact" and form_outer_source == "template":
            matched.append("clean_history_form_outer/exact_body")
            eliminated = True
            reason.append("exact s00 body/template outer is known rejected on live replay")
        if marker_source == "template" and payload_uuid_source == "fresh" and form_outer_source == "fresh" and payload_source == "built":
            matched.append("outer_binding_controls/template_marker")
            eliminated = True
            reason.append("template marker with decoded equality and fresh outer still rejected")
        if pc_uuid_source == "fresh" and payload_source == "template-exact":
            matched.append("clean_history_pc_uuid/exact_payload_fresh_pc")
            eliminated = True
            reason.append("exact payload with fresh-uuid pc returns do=[]")
        if payload_source == "template-exact":
            matched.append("exact_payload_family")
            eliminated = True
            reason.append("template-exact payload variants are covered by exact payload/body and pc-uuid split controls; static exact payload is not a valid next mutation")
        if pc_uuid_source == "template" and payload_source == "built":
            matched.append("clean_history_pc_uuid/fresh_payload_template_pc")
            eliminated = True
            reason.append("fresh-uuid payload with template-uuid pc still rejected")
        if pc_source == "template-exact" and payload_source == "built":
            matched.append("template_pc_family")
            eliminated = True
            reason.append("template pc with a built/equal-decoded payload is covered by pc mismatch controls and remains rejected")
        if payload_uuid_source == "fresh" and marker_source == "fresh" and form_outer_source == "fresh" and payload_source == "built" and pc_source == "computed":
            matched.append("selected_contrast")
            eliminated = True
            reason.append("selected fresh contrast itself is rejected")
        if payload_uuid_source == "fresh" and pc_uuid_source in {"payload", "fresh"} and marker_source == "fresh" and form_outer_source == "fresh" and payload_source == "built" and pc_source == "computed":
            matched.append("h2_fresh_tail_strongest_family")
            reason.append("strongest fresh tail/h2 controls still rejected for this family")

        # Do not recommend variants that combine stale/template outer with fresh server-state values unless a prior
        # artifact proves this is one coherent state transition.
        coherent = not (
            form_outer_source == "template"
            and (payload_uuid_source == "fresh" or marker_source == "fresh" or pc_uuid_source == "fresh")
        )
        if form_outer_source == "template" and payload_source == "built":
            coherent = False
            reason.append("template outer plus rebuilt payload is not one coherent observed server-state transition")
        justified = coherent and not eliminated
        variants.append({
            **variant,
            "matchedControls": matched,
            "eliminatedByControl": eliminated,
            "coherentSingleTransitionByCurrentEvidence": coherent,
            "currentlyJustifiedUntested": justified,
            "reason": reason,
        })

    justified = [v for v in variants if v["currentlyJustifiedUntested"]]
    # Additional gate: if more than one remains, none is a single decisive experiment.
    single_recommended = len(justified) == 1

    result = {
        "purpose": "Enumerate encoder/session variant knobs and match them to existing controls before allowing any fresh-session experiment.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "finalBoundaryDecisionMatrix": p("output/protocol_reverse/hypothesis_reframe/final_boundary_decision_matrix.json"),
            "encodedPayloadPcFormDiffMap": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "builder": p("tools/probe_human_fresh_px561.py"),
            "controls": {name: p(f"output/protocol_reverse/goal_audit/{file}") for name, file in {
                "exact_payload_pc_fresh_outer": "forced_overlap_payload_pc_split_control_audit.json",
                "clean_payload_pc": "clean_history_payload_pc_controls_audit.json",
                "pc_uuid": "clean_history_pc_uuid_controls_audit.json",
                "form_outer": "clean_history_form_outer_controls_audit.json",
                "outer_binding": "outer_binding_controls_audit.json",
                "fresh_tail_strongest": "h2_fresh_tail_strongest_control_audit.json",
                "inner_uuid": "h2_inner_uuid_binding_control_audit.json",
            }.items()},
        },
        "knobs": {
            "payloadUuidSource": ["fresh", "template"],
            "pcUuidSource": ["payload", "fresh", "template"],
            "markerSource": ["fresh", "template"],
            "formOuterSource": ["fresh", "template"],
            "payloadSource": ["built", "template-exact"],
            "pcSource": ["computed", "template-exact"],
        },
        "variants": variants,
        "justifiedUntestedVariants": justified,
        "controlChecks": {name: doc.get("checks") for name, doc in controls.items()},
        "encodedLayerChecks": encoded.get("checks"),
        "decision": {
            "readyForFreshExperiment": single_recommended,
            "recommendedExperiment": justified[0] if single_recommended else None,
            "reason": (
                "Exactly one coherent untested coupled encoder variant remains."
                if single_recommended
                else "No single decisive coupled encoder variant is isolated: either variants are already negatively controlled, incoherent by current evidence, or multiple coupled choices remain."
            ),
            "nextArtifact": (
                p("output/protocol_reverse/hypothesis_reframe/minimal_divergence_experiment_audit.json")
                if single_recommended
                else p("output/protocol_reverse/hypothesis_reframe/server_internal_state_gap_audit.json")
            ),
            "nextScript": (
                str(ROOT / "tools/run_minimal_divergence_experiment.py")
                if single_recommended
                else str(ROOT / "tools/build_server_internal_state_gap_audit.py")
            ),
        },
        "checks": {
            "finalMatrixRequiresThisArtifact": (final.get("decision") or {}).get("nextArtifact") == str(OUT),
            "enumeratedVariantCount": len(variants),
            "hasMatchedControls": any(v["matchedControls"] for v in variants),
            "hasJustifiedUntestedVariants": bool(justified),
            "justifiedUntestedVariantCount": len(justified),
            "singleRecommendedVariant": single_recommended,
            "readyForFreshExperiment": single_recommended,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
