#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
GOAL = PROTO / "goal_audit"
OUT = BASE / "browser_success_payload_pc_session_lineage_audit.json"

INPUTS = {
    "methodologyPlan": REPO / "docs/pure-protocol-human-methodology-implementation-plan.md",
    "classificationBacklog": BASE / "browser_success_chain_classification_backlog.json",
    "serverVisibleDiff": BASE / "browser_success_chain_server_visible_diff_audit.json",
    "encodedPayloadPcFormDiffMap": BASE / "encoded_payload_pc_form_diff_map.json",
    "serverStateValueToRequestLineage": BASE / "server_state_value_to_request_lineage.json",
    "outerSessionTupleFactorization": BASE / "outer_session_tuple_factorization.json",
    "encoderAxisEquivalence": BASE / "encoder_axis_equivalence.json",
    "encodedSessionBindingCandidate": BASE / "encoded_session_binding_candidate_audit.json",
    "remainingEncoderPcCoherence": BASE / "remaining_encoder_pc_coherence_audit.json",
    "latestExactPayloadBodyControls": GOAL / "latest_exact_payload_body_controls_audit.json",
    "forcedOverlapPayloadPcSplitControl": GOAL / "forced_overlap_payload_pc_split_control_audit.json",
    "cleanHistoryPayloadPcControls": GOAL / "clean_history_payload_pc_controls_audit.json",
    "candidateIntake": BASE / "promoted_transition_candidate_intake.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def bundle_build_path(run: str) -> Path:
    return PROTO / f"bundle_request_build/bundle_request_build_{run}.json"


def bundle_payload_decode_path(run: str) -> Path:
    return PROTO / f"bundle_payload_decode/bundle_payload_decode_{run}.json"


def load_bundle_build(run: str) -> dict[str, Any]:
    return read_json(bundle_build_path(run))


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    backlog_rows = docs["classificationBacklog"].get("rows") or []
    positive_runs = [
        row["run"] for row in backlog_rows
        if row.get("backlogRole") == "browser_success_positive_control"
    ]

    bundle_rows = []
    for run in positive_runs:
        build_doc = load_bundle_build(run)
        rows = build_doc.get("rows") or []
        px_rows = [row for row in rows if (row.get("contains") or {}).get("PX561") is True]
        bundle_rows.append(
            {
                "run": run,
                "bundleBuildPath": str(bundle_build_path(run)),
                "bundleBuildExists": bundle_build_path(run).exists(),
                "bundlePayloadDecodePath": str(bundle_payload_decode_path(run)),
                "bundlePayloadDecodeExists": bundle_payload_decode_path(run).exists(),
                "bundleBuildRowCount": len(rows),
                "px561RequestRowCount": len(px_rows),
                "allBuiltRowsPayloadMatch": all(row.get("payloadMatch") is True for row in rows) if rows else None,
                "allBuiltRowsPcMatch": all(row.get("pcMatch") is True for row in rows) if rows else None,
                "allBuiltRowsBodyMatch": all(row.get("bodyMatch") is True for row in rows) if rows else None,
                "seqs": [row.get("seq") for row in rows],
            }
        )

    encoded = docs["encodedPayloadPcFormDiffMap"].get("checks") or {}
    lineage = docs["serverStateValueToRequestLineage"].get("checks") or {}
    outer = docs["outerSessionTupleFactorization"].get("checks") or {}
    encoder = docs["encoderAxisEquivalence"].get("checks") or {}
    binding = docs["encodedSessionBindingCandidate"].get("checks") or {}
    coherence = docs["remainingEncoderPcCoherence"].get("checks") or {}
    exact_body = docs["latestExactPayloadBodyControls"].get("checks") or {}
    split = docs["forcedOverlapPayloadPcSplitControl"].get("checks") or {}
    clean = docs["cleanHistoryPayloadPcControls"].get("checks") or {}
    server_diff = docs["serverVisibleDiff"].get("checks") or {}
    intake = docs["candidateIntake"].get("checks") or {}

    field_rows = [
        {
            "id": "payload_encoded_body",
            "valueChain": "request",
            "preAccept": True,
            "clientVisible": True,
            "evidence": [
                str(INPUTS["encodedPayloadPcFormDiffMap"]),
                str(INPUTS["latestExactPayloadBodyControls"]),
                str(INPUTS["forcedOverlapPayloadPcSplitControl"]),
                str(INPUTS["cleanHistoryPayloadPcControls"]),
            ],
            "facts": {
                "payloadDiffers": encoded.get("payloadDiffers"),
                "decodedJsonEqual": encoded.get("decodedJsonEqual"),
                "exactPayloadPcNoSuccess": exact_body.get("exactPayloadPcNoSuccess"),
                "forcedSeq5PayloadAndPcExactS00": split.get("seq5PayloadAndPcExactS00"),
                "cleanExactPayloadPcReturnedDoEmpty": clean.get("exactPayloadPcReturnedDoEmpty"),
            },
            "pureProtocolConstructible": False,
            "contradicted": True,
            "proposalReady": False,
            "blockers": [
                "decoded semantic equality is already proven while encoded payload still differs",
                "exact payload+pc and exact body controls did not produce success",
                "payload remains bound to marker/session/pc family",
            ],
        },
        {
            "id": "pc_value",
            "valueChain": "request",
            "preAccept": True,
            "clientVisible": True,
            "evidence": [
                str(INPUTS["encoderAxisEquivalence"]),
                str(INPUTS["encodedSessionBindingCandidate"]),
            ],
            "facts": {
                "pcUuidSourceDeterminesPc": encoder.get("pcUuidSourceDeterminesPc"),
                "pcAloneEliminated": binding.get("pcAloneEliminated"),
                "encodedSessionExactPayloadPcNoSuccess": binding.get("exactPayloadPcNoSuccess"),
            },
            "pureProtocolConstructible": True,
            "contradicted": True,
            "proposalReady": False,
            "blockers": [
                "pc alone is eliminated by existing control",
                "pc participates in a coupled payload/pc/session family",
            ],
        },
        {
            "id": "marker_uuid_session_tuple",
            "valueChain": "request",
            "preAccept": True,
            "clientVisible": True,
            "evidence": [
                str(INPUTS["outerSessionTupleFactorization"]),
                str(INPUTS["serverStateValueToRequestLineage"]),
                str(INPUTS["remainingEncoderPcCoherence"]),
            ],
            "facts": {
                "outerSingleReadyGroupCount": outer.get("singleReadyGroupCount"),
                "outerNoSingleFieldExperimentReady": outer.get("noSingleFieldExperimentReady"),
                "hasOuterSessionTupleBoundary": lineage.get("hasOuterSessionTupleBoundary"),
                "singleCoherentVariant": coherence.get("singleCoherentVariant"),
                "coherentVariantAlreadySent": coherence.get("coherentVariantAlreadySent"),
            },
            "pureProtocolConstructible": False,
            "contradicted": True,
            "proposalReady": False,
            "blockers": [
                "outer/session tuple has no single ready source group",
                "remaining coherent encoder variant is still not a promoted transition",
                "client-visible representation of server acceptance state is not isolated",
            ],
        },
    ]

    proposal_candidates = [row for row in field_rows if row["proposalReady"]]

    checks = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "positiveRunCount": len(positive_runs),
        "positiveBundleBuildRunCount": sum(1 for row in bundle_rows if row["bundleBuildExists"]),
        "positivePx561BundleBuildRunCount": sum(1 for row in bundle_rows if row["px561RequestRowCount"] > 0),
        "serverVisibleDiffProposalCandidateCount": server_diff.get("proposalCandidateCount"),
        "fieldLineageRowCount": len(field_rows),
        "fieldLineageContradictedCount": sum(1 for row in field_rows if row["contradicted"]),
        "fieldLineagePureProtocolConstructibleCount": sum(1 for row in field_rows if row["pureProtocolConstructible"]),
        "payloadExactControlRejected": exact_body.get("exactPayloadPcNoSuccess") is True or split.get("seq5NoOIIoIooo") is True,
        "pcAloneEliminated": binding.get("pcAloneEliminated") is True,
        "outerTupleNoSingleReadyGroup": outer.get("noSingleFieldExperimentReady") is True,
        "encoderFamilyStillTwoAxis": encoder.get("remainingEncoderAxisCount") == 2,
        "proposalCandidateCount": len(proposal_candidates),
        "candidateIntakePromotedCount": intake.get("promotedSingleTransitionCandidateCount"),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT),
        "purpose": "Drill browser-success request-class diffs down to payload/pc/session field lineage and determine whether any proposal-ready transition remains.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "bundleRows": bundle_rows,
        "fieldLineageRows": field_rows,
        "proposalCandidates": proposal_candidates,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "The request-class diff drills down to payload, pc, and marker/uuid/session fields. "
                "Existing controls eliminate exact payload+pc/body, pc alone, and single outer tuple fields. "
                "The remaining lineage is still a coupled payload/pc/session/server-state boundary, not one proposal-ready transition."
            ),
        },
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
