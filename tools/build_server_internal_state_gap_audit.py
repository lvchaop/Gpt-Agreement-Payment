#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/server_internal_state_gap_audit.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def p(rel: str) -> str:
    return str(ROOT / rel)


def main() -> int:
    coupled = load("output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json")
    first = load("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json")
    diff = load("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json")
    model = load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")
    encoded = load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")

    justified = coupled.get("justifiedUntestedVariants") or []
    shared = {
        "payloadUuidSourceValues": sorted({v.get("payloadUuidSource") for v in justified}),
        "formOuterSourceValues": sorted({v.get("formOuterSource") for v in justified}),
        "pcUuidSourceValues": sorted({v.get("pcUuidSource") for v in justified}),
        "markerSourceValues": sorted({v.get("markerSource") for v in justified}),
        "payloadSourceValues": sorted({v.get("payloadSource") for v in justified}),
        "pcSourceValues": sorted({v.get("pcSource") for v in justified}),
    }

    result = {
        "purpose": "State the remaining server-internal/encoder-session gap after all currently justified single-variable request boundaries failed the decision gate.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "coupledEncoderVariantAudit": p("output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json"),
            "firstDecisiveDivergence": p("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
            "collectorStateTransitionDiff": p("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
            "serverStateTransitionValueModel": p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
            "encodedPayloadPcFormDiffMap": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
        },
        "remainingFacts": [
            {
                "id": "F1_final_boundary",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
                "fact": "first decisive divergence remains final seq5/rsc6 acceptance response",
                "checks": first.get("checks"),
            },
            {
                "id": "F2_decoded_semantics_equal",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
                "fact": "decoded JSON, decoded text, and base after marker removal are equal between s00 and selected fresh seq5",
                "checks": {
                    k: (encoded.get("checks") or {}).get(k)
                    for k in ["decodedJsonEqual", "decodedTextEqual", "baseAfterMarkerRemovalEqual", "payloadDiffers", "pcDiffers"]
                },
            },
            {
                "id": "F3_request_history_aligned",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
                "fact": "selected fresh request order is not missing msft seq1-3 before bundle POW",
            },
            {
                "id": "F4_encoder_variants_not_single",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json"),
                "fact": "coupled encoder audit leaves multiple variants, not a single decisive experiment",
                "sharedVariantProperties": shared,
                "justifiedUntestedVariantCount": len(justified),
            },
        ],
        "remainingHypotheses": [
            {
                "id": "R1_payload_insertion_uuid_outer_session_mismatch_family",
                "status": "coupled_variant_family_not_single_experiment",
                "basis": "The remaining encoder variants all use template payloadUuidSource with fresh formOuterSource, while pc/marker choices vary.",
                "whyNotRunYet": "Four variants remain; choosing one would be arbitrary without evidence that pcUuidSource or markerSource is the decisive axis.",
                "nextEvidenceNeeded": "Offline-build and compare the four remaining variants at payload/pc/body level, then rank by whether each collapses to an already-tested exact/template-marker family.",
            },
            {
                "id": "R2_collector_server_expected_state",
                "status": "highest_priority_non_request_gap",
                "basis": "The same decoded request semantics produce success in s00 and rejection in selected fresh.",
                "whyNotRunYet": "Server expected state is not directly mutable as one request field.",
                "nextEvidenceNeeded": "Find a client-observable server-state token or transition not currently included in pure protocol; otherwise update goal audit to state server-internal gap remains.",
            },
        ],
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "No single experiment is supported. The immediate next progress item is an offline build matrix for the four remaining encoder variants, not network traffic.",
            "nextArtifact": p("output/protocol_reverse/hypothesis_reframe/remaining_encoder_variant_build_matrix.json"),
            "nextScript": str(ROOT / "tools/build_remaining_encoder_variant_build_matrix.py"),
        },
        "checks": {
            "coupledAuditNotReady": (coupled.get("checks") or {}).get("readyForFreshExperiment") is False,
            "hasFourRemainingEncoderVariants": len(justified) == 4,
            "remainingVariantsShareTemplatePayloadUuid": shared["payloadUuidSourceValues"] == ["template"],
            "remainingVariantsShareFreshOuter": shared["formOuterSourceValues"] == ["fresh"],
            "decodedJsonEqual": (encoded.get("checks") or {}).get("decodedJsonEqual") is True,
            "finalDivergenceStillSeq5": (first.get("checks") or {}).get("firstDivergenceAtFinalSeq5") is True,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
