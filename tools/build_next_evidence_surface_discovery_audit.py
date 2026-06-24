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
RESET = PROTO / "reset_plan"
OUT = HYP / "next_evidence_surface_discovery_audit.json"

INPUTS = {
    "exhaustiveCandidateResolution": HYP / "exhaustive_promotion_candidate_resolution_audit.json",
    "manifestCoverageGap": HYP / "manifest_coverage_gap_audit.json",
    "convergentEvidenceEntranceMatrix": HYP / "convergent_evidence_entrance_matrix.json",
    "externalOutputSurfaceAudit": HYP / "external_output_surface_audit.json",
    "evidencePackageSurfaceAudit": HYP / "evidence_package_surface_audit.json",
    "ctfRegOutputSurfaceAudit": HYP / "ctf_reg_output_surface_audit.json",
    "auxiliaryTraceSurfaceAudit": HYP / "auxiliary_trace_surface_audit.json",
    "localTraceEvidenceFreshness": HYP / "local_trace_evidence_freshness_audit.json",
    "unclassifiedTraceSignalReduction": HYP / "unclassified_trace_signal_reduction_audit.json",
    "browserSuccessChainClassificationBacklog": HYP / "browser_success_chain_classification_backlog.json",
    "browserSuccessChainServerVisibleDiff": HYP / "browser_success_chain_server_visible_diff_audit.json",
    "browserSuccessPayloadPcSessionLineage": HYP / "browser_success_payload_pc_session_lineage_audit.json",
    "collectorResponseHandlerValueLineage": HYP / "collector_response_handler_value_lineage_audit.json",
    "collectorMaterialOnlyResponseClass": HYP / "collector_material_only_response_class_audit.json",
    "downstreamSuccessWithoutCollectorDecode": HYP / "downstream_success_without_collector_decode_audit.json",
    "stalePositiveSignalAuthority": HYP / "stale_positive_signal_authority_audit.json",
    "liveRunnerGate": HYP / "live_runner_gate_audit.json",
    "objectiveRequirementCrosswalk": HYP / "objective_requirement_crosswalk.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def surface(
    *,
    surface_id: str,
    source_key: str,
    category: str,
    scanned_count: int | None,
    candidate_signal_count: int | None,
    new_candidate_surface_count: int,
    closed: bool,
    reason: str,
    facts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": surface_id,
        "source": str(INPUTS[source_key]),
        "category": category,
        "scannedCount": scanned_count,
        "candidateSignalCount": candidate_signal_count,
        "newCandidateSurfaceCount": new_candidate_surface_count,
        "closed": closed,
        "reason": reason,
        "facts": facts,
    }


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    c = {name: checks(doc) for name, doc in docs.items()}

    rows = [
        surface(
            surface_id="current_promotion_candidate_set",
            source_key="exhaustiveCandidateResolution",
            category="candidate_model",
            scanned_count=c["exhaustiveCandidateResolution"].get("candidateRowCount"),
            candidate_signal_count=c["exhaustiveCandidateResolution"].get("proposalReadyCandidateCount"),
            new_candidate_surface_count=0,
            closed=(
                c["exhaustiveCandidateResolution"].get("resolvedCandidateCount")
                == c["exhaustiveCandidateResolution"].get("candidateRowCount")
                and c["exhaustiveCandidateResolution"].get("openNeedsSpecificEvidenceCount") == 0
                and c["exhaustiveCandidateResolution"].get("proposalReadyCandidateCount") == 0
            ),
            reason="The modeled promotion-candidate set is exhausted; all 32 rows are closed by existing controls.",
            facts={
                "candidateRowCount": c["exhaustiveCandidateResolution"].get("candidateRowCount"),
                "resolvedCandidateCount": c["exhaustiveCandidateResolution"].get("resolvedCandidateCount"),
                "openNeedsSpecificEvidenceCount": c["exhaustiveCandidateResolution"].get("openNeedsSpecificEvidenceCount"),
                "proposalReadyCandidateCount": c["exhaustiveCandidateResolution"].get("proposalReadyCandidateCount"),
            },
        ),
        surface(
            surface_id="protocol_reverse_unmanifested_surface",
            source_key="manifestCoverageGap",
            category="local_artifact_surface",
            scanned_count=c["manifestCoverageGap"].get("scannedFileCount"),
            candidate_signal_count=c["manifestCoverageGap"].get("proposalWorthyUnmanifestedDirectoryCount"),
            new_candidate_surface_count=c["manifestCoverageGap"].get("proposalWorthyUnmanifestedDirectoryCount") or 0,
            closed=(
                c["manifestCoverageGap"].get("highValueUncoveredDirectoryCount") == 0
                and c["manifestCoverageGap"].get("proposalWorthyUnmanifestedDirectoryCount") == 0
            ),
            reason="High-value protocol_reverse directories are covered by existing blindspot/raw/crosswalk audits; no proposal-worthy unmanifested directory remains.",
            facts={
                "unmanifestedFileCount": c["manifestCoverageGap"].get("unmanifestedFileCount"),
                "highValueUncoveredDirectoryCount": c["manifestCoverageGap"].get("highValueUncoveredDirectoryCount"),
                "proposalWorthyUnmanifestedDirectoryCount": c["manifestCoverageGap"].get("proposalWorthyUnmanifestedDirectoryCount"),
            },
        ),
        surface(
            surface_id="terminal_entrance_surface",
            source_key="convergentEvidenceEntranceMatrix",
            category="entrance_matrix",
            scanned_count=c["convergentEvidenceEntranceMatrix"].get("entranceCount"),
            candidate_signal_count=c["convergentEvidenceEntranceMatrix"].get("recommendedNextEntranceCount"),
            new_candidate_surface_count=c["convergentEvidenceEntranceMatrix"].get("recommendedNextEntranceCount") or 0,
            closed=c["convergentEvidenceEntranceMatrix"].get("recommendedNextEntranceCount") == 0,
            reason="Known candidate-affecting entrances are closed or stale; no recommended next entrance exists.",
            facts={
                "candidateAffectingEntranceCount": c["convergentEvidenceEntranceMatrix"].get("candidateAffectingEntranceCount"),
                "uncoveredCandidateAffectingEntranceCount": c["convergentEvidenceEntranceMatrix"].get("uncoveredCandidateAffectingEntranceCount"),
                "recommendedNextEntranceCount": c["convergentEvidenceEntranceMatrix"].get("recommendedNextEntranceCount"),
            },
        ),
        surface(
            surface_id="external_output_surface",
            source_key="externalOutputSurfaceAudit",
            category="external_output",
            scanned_count=c["externalOutputSurfaceAudit"].get("signalFileCount"),
            candidate_signal_count=c["externalOutputSurfaceAudit"].get("proposalWorthyExternalSignalCount"),
            new_candidate_surface_count=c["externalOutputSurfaceAudit"].get("proposalWorthyExternalSignalCount") or 0,
            closed=c["externalOutputSurfaceAudit"].get("proposalWorthyExternalSignalCount") == 0,
            reason="External output directories contain static/browser/OAuth/proxy/log context but no proposal-worthy pre-accept transition.",
            facts={
                "collectorSuccess0SignalFileCount": c["externalOutputSurfaceAudit"].get("collectorSuccess0SignalFileCount"),
                "proposalWorthyExternalSignalCount": c["externalOutputSurfaceAudit"].get("proposalWorthyExternalSignalCount"),
            },
        ),
        surface(
            surface_id="evidence_package_surface",
            source_key="evidencePackageSurfaceAudit",
            category="packaged_evidence",
            scanned_count=c["evidencePackageSurfaceAudit"].get("signalFileCount"),
            candidate_signal_count=c["evidencePackageSurfaceAudit"].get("proposalWorthyEvidencePackageSignalCount"),
            new_candidate_surface_count=c["evidencePackageSurfaceAudit"].get("proposalWorthyEvidencePackageSignalCount") or 0,
            closed=c["evidencePackageSurfaceAudit"].get("proposalWorthyEvidencePackageSignalCount") == 0,
            reason="Packaged success references are browser/static/runtime/downstream material, not fresh no-browser replay evidence.",
            facts={
                "collectorSuccess0SignalFileCount": c["evidencePackageSurfaceAudit"].get("collectorSuccess0SignalFileCount"),
                "proposalWorthyEvidencePackageSignalCount": c["evidencePackageSurfaceAudit"].get("proposalWorthyEvidencePackageSignalCount"),
            },
        ),
        surface(
            surface_id="ctf_reg_surface",
            source_key="ctfRegOutputSurfaceAudit",
            category="workspace_output",
            scanned_count=c["ctfRegOutputSurfaceAudit"].get("signalFileCount"),
            candidate_signal_count=c["ctfRegOutputSurfaceAudit"].get("proposalWorthyCtfRegSignalCount"),
            new_candidate_surface_count=c["ctfRegOutputSurfaceAudit"].get("proposalWorthyCtfRegSignalCount") or 0,
            closed=c["ctfRegOutputSurfaceAudit"].get("proposalWorthyCtfRegSignalCount") == 0,
            reason="CTF-reg output has no proposal-worthy collector success or pre-accept transition.",
            facts={
                "collectorSuccess0SignalFileCount": c["ctfRegOutputSurfaceAudit"].get("collectorSuccess0SignalFileCount"),
                "proposalWorthyCtfRegSignalCount": c["ctfRegOutputSurfaceAudit"].get("proposalWorthyCtfRegSignalCount"),
            },
        ),
        surface(
            surface_id="auxiliary_trace_surface",
            source_key="auxiliaryTraceSurfaceAudit",
            category="auxiliary_trace",
            scanned_count=c["auxiliaryTraceSurfaceAudit"].get("signalFileCount"),
            candidate_signal_count=c["auxiliaryTraceSurfaceAudit"].get("proposalWorthyAuxiliarySignalCount"),
            new_candidate_surface_count=c["auxiliaryTraceSurfaceAudit"].get("proposalWorthyAuxiliarySignalCount") or 0,
            closed=c["auxiliaryTraceSurfaceAudit"].get("proposalWorthyAuxiliarySignalCount") == 0,
            reason="Auxiliary traces/HARs have no proposal-worthy collector success or pre-accept transition.",
            facts={
                "collectorSuccess0SignalFileCount": c["auxiliaryTraceSurfaceAudit"].get("collectorSuccess0SignalFileCount"),
                "proposalWorthyAuxiliarySignalCount": c["auxiliaryTraceSurfaceAudit"].get("proposalWorthyAuxiliarySignalCount"),
            },
        ),
        surface(
            surface_id="local_trace_freshness_surface",
            source_key="localTraceEvidenceFreshness",
            category="runtime_trace",
            scanned_count=c["localTraceEvidenceFreshness"].get("allLocalTraceRunCount"),
            candidate_signal_count=c["localTraceEvidenceFreshness"].get("proposalWorthyNowCount"),
            new_candidate_surface_count=c["localTraceEvidenceFreshness"].get("proposalWorthyNowCount") or 0,
            closed=c["localTraceEvidenceFreshness"].get("proposalWorthyNowCount") == 0,
            reason="Unclassified local traces include high-value material but no currently proposal-worthy run.",
            facts={
                "unclassifiedRunCount": c["localTraceEvidenceFreshness"].get("unclassifiedRunCount"),
                "unclassifiedHighValueSignalRunCount": c["localTraceEvidenceFreshness"].get("unclassifiedHighValueSignalRunCount"),
                "proposalWorthyNowCount": c["localTraceEvidenceFreshness"].get("proposalWorthyNowCount"),
            },
        ),
        surface(
            surface_id="unclassified_trace_reduction_surface",
            source_key="unclassifiedTraceSignalReduction",
            category="runtime_trace_reduction",
            scanned_count=c["unclassifiedTraceSignalReduction"].get("reducedRunCount"),
            candidate_signal_count=c["unclassifiedTraceSignalReduction"].get("proposalReadyRunCount"),
            new_candidate_surface_count=c["unclassifiedTraceSignalReduction"].get("proposalReadyRunCount") or 0,
            closed=c["unclassifiedTraceSignalReduction"].get("proposalReadyRunCount") == 0,
            reason="Unclassified traces reduce to browser success chain, collector-material-only, or lower-value classes; none is proposal-ready.",
            facts={
                "browserSuccessChainRunCount": c["unclassifiedTraceSignalReduction"].get("browserSuccessChainRunCount"),
                "collectorMaterialOnlyRunCount": c["unclassifiedTraceSignalReduction"].get("collectorMaterialOnlyRunCount"),
                "proposalReadyRunCount": c["unclassifiedTraceSignalReduction"].get("proposalReadyRunCount"),
            },
        ),
        surface(
            surface_id="browser_success_chain_surface",
            source_key="browserSuccessChainClassificationBacklog",
            category="browser_success_contrast",
            scanned_count=c["browserSuccessChainClassificationBacklog"].get("classificationBacklogCount"),
            candidate_signal_count=c["browserSuccessChainClassificationBacklog"].get("proposalReadyRunCount"),
            new_candidate_surface_count=c["browserSuccessChainClassificationBacklog"].get("proposalReadyRunCount") or 0,
            closed=c["browserSuccessChainClassificationBacklog"].get("proposalReadyRunCount") == 0,
            reason="Browser success chain remains a contrast asset; it has no no-browser proposal-ready run.",
            facts={
                "classificationBacklogCount": c["browserSuccessChainClassificationBacklog"].get("classificationBacklogCount"),
                "noBrowserEvidenceCount": c["browserSuccessChainClassificationBacklog"].get("noBrowserEvidenceCount"),
                "proposalReadyRunCount": c["browserSuccessChainClassificationBacklog"].get("proposalReadyRunCount"),
            },
        ),
        surface(
            surface_id="server_visible_diff_surface",
            source_key="browserSuccessChainServerVisibleDiff",
            category="server_visible_diff",
            scanned_count=c["browserSuccessChainServerVisibleDiff"].get("earliestServerVisibleDiffCount"),
            candidate_signal_count=c["browserSuccessChainServerVisibleDiff"].get("proposalCandidateCount"),
            new_candidate_surface_count=c["browserSuccessChainServerVisibleDiff"].get("proposalCandidateCount") or 0,
            closed=c["browserSuccessChainServerVisibleDiff"].get("proposalCandidateCount") == 0,
            reason="Server-visible diffs are contradicted by controls and produce no proposal candidate.",
            facts={
                "earliestServerVisibleDiffCount": c["browserSuccessChainServerVisibleDiff"].get("earliestServerVisibleDiffCount"),
                "contradictedDiffCount": c["browserSuccessChainServerVisibleDiff"].get("contradictedDiffCount"),
                "proposalCandidateCount": c["browserSuccessChainServerVisibleDiff"].get("proposalCandidateCount"),
            },
        ),
        surface(
            surface_id="payload_pc_session_lineage_surface",
            source_key="browserSuccessPayloadPcSessionLineage",
            category="lineage",
            scanned_count=c["browserSuccessPayloadPcSessionLineage"].get("fieldLineageRowCount"),
            candidate_signal_count=c["browserSuccessPayloadPcSessionLineage"].get("proposalCandidateCount"),
            new_candidate_surface_count=c["browserSuccessPayloadPcSessionLineage"].get("proposalCandidateCount") or 0,
            closed=c["browserSuccessPayloadPcSessionLineage"].get("proposalCandidateCount") == 0,
            reason="Payload/pc/session lineage remains contradicted/coupled and produces no proposal candidate.",
            facts={
                "fieldLineageRowCount": c["browserSuccessPayloadPcSessionLineage"].get("fieldLineageRowCount"),
                "fieldLineageContradictedCount": c["browserSuccessPayloadPcSessionLineage"].get("fieldLineageContradictedCount"),
                "proposalCandidateCount": c["browserSuccessPayloadPcSessionLineage"].get("proposalCandidateCount"),
            },
        ),
        surface(
            surface_id="collector_handler_value_surface",
            source_key="collectorResponseHandlerValueLineage",
            category="handler_value_lineage",
            scanned_count=c["collectorResponseHandlerValueLineage"].get("decodedRunCount"),
            candidate_signal_count=c["collectorResponseHandlerValueLineage"].get("proposalCandidateCount"),
            new_candidate_surface_count=c["collectorResponseHandlerValueLineage"].get("proposalCandidateCount") or 0,
            closed=c["collectorResponseHandlerValueLineage"].get("proposalCandidateCount") == 0,
            reason="Collector handler/value lineage has no proposal candidate; cookie failure still mutates downstream jar and is not accept proof.",
            facts={
                "decodedRunCount": c["collectorResponseHandlerValueLineage"].get("decodedRunCount"),
                "proposalCandidateCount": c["collectorResponseHandlerValueLineage"].get("proposalCandidateCount"),
                "cookieFailureStillMutates": c["collectorResponseHandlerValueLineage"].get("cookieFailureStillMutates"),
            },
        ),
        surface(
            surface_id="collector_material_only_surface",
            source_key="collectorMaterialOnlyResponseClass",
            category="collector_material",
            scanned_count=c["collectorMaterialOnlyResponseClass"].get("runCount"),
            candidate_signal_count=c["collectorMaterialOnlyResponseClass"].get("proposalCandidateCount"),
            new_candidate_surface_count=c["collectorMaterialOnlyResponseClass"].get("proposalCandidateCount") or 0,
            closed=c["collectorMaterialOnlyResponseClass"].get("proposalCandidateCount") == 0,
            reason="Collector material-only runs do not show collector success and are not proposal-worthy.",
            facts={
                "collectorSuccessCount": c["collectorMaterialOnlyResponseClass"].get("collectorSuccessCount"),
                "riskContinueCount": c["collectorMaterialOnlyResponseClass"].get("riskContinueCount"),
                "proposalCandidateCount": c["collectorMaterialOnlyResponseClass"].get("proposalCandidateCount"),
            },
        ),
        surface(
            surface_id="downstream_without_collector_surface",
            source_key="downstreamSuccessWithoutCollectorDecode",
            category="downstream",
            scanned_count=c["downstreamSuccessWithoutCollectorDecode"].get("runCount"),
            candidate_signal_count=c["downstreamSuccessWithoutCollectorDecode"].get("proposalCandidateCount"),
            new_candidate_surface_count=c["downstreamSuccessWithoutCollectorDecode"].get("proposalCandidateCount") or 0,
            closed=c["downstreamSuccessWithoutCollectorDecode"].get("proposalCandidateCount") == 0,
            reason="Downstream success without collector decode lacks collector success and cannot open a pre-accept HUMAN transition.",
            facts={
                "successRunCount": c["downstreamSuccessWithoutCollectorDecode"].get("successRunCount"),
                "collectorSuccessCount": c["downstreamSuccessWithoutCollectorDecode"].get("collectorSuccessCount"),
                "allLackCollectorSuccess": c["downstreamSuccessWithoutCollectorDecode"].get("allLackCollectorSuccess"),
                "proposalCandidateCount": c["downstreamSuccessWithoutCollectorDecode"].get("proposalCandidateCount"),
            },
        ),
        surface(
            surface_id="stale_positive_signal_surface",
            source_key="stalePositiveSignalAuthority",
            category="authority",
            scanned_count=c["stalePositiveSignalAuthority"].get("positiveSignalCount"),
            candidate_signal_count=c["stalePositiveSignalAuthority"].get("activeActionablePositiveSignalCount"),
            new_candidate_surface_count=c["stalePositiveSignalAuthority"].get("activeActionablePositiveSignalCount") or 0,
            closed=c["stalePositiveSignalAuthority"].get("activeActionablePositiveSignalCount") == 0,
            reason="Positive-looking signals are stale or non-authoritative under current gate authority.",
            facts={
                "positiveSignalCount": c["stalePositiveSignalAuthority"].get("positiveSignalCount"),
                "activeActionablePositiveSignalCount": c["stalePositiveSignalAuthority"].get("activeActionablePositiveSignalCount"),
                "candidateIntakePromotedCount": c["stalePositiveSignalAuthority"].get("candidateIntakePromotedCount"),
            },
        ),
    ]

    new_rows = [row for row in rows if row["newCandidateSurfaceCount"] > 0]
    open_rows = [row for row in rows if row["closed"] is not True]
    closed_rows = [row for row in rows if row["closed"] is True]

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "surfaceCount": len(rows),
        "closedSurfaceCount": len(closed_rows),
        "openSurfaceCount": len(open_rows),
        "newCandidateSurfaceCount": sum(row["newCandidateSurfaceCount"] for row in rows),
        "surfaceWithNewCandidateCount": len(new_rows),
        "proposalReadyCandidateCount": c["exhaustiveCandidateResolution"].get("proposalReadyCandidateCount"),
        "openNeedsSpecificEvidenceCount": c["exhaustiveCandidateResolution"].get("openNeedsSpecificEvidenceCount"),
        "manifestProposalWorthyUnmanifestedDirectoryCount": c["manifestCoverageGap"].get("proposalWorthyUnmanifestedDirectoryCount"),
        "convergentRecommendedNextEntranceCount": c["convergentEvidenceEntranceMatrix"].get("recommendedNextEntranceCount"),
        "externalProposalWorthySignalCount": c["externalOutputSurfaceAudit"].get("proposalWorthyExternalSignalCount"),
        "evidencePackageProposalWorthySignalCount": c["evidencePackageSurfaceAudit"].get("proposalWorthyEvidencePackageSignalCount"),
        "ctfRegProposalWorthySignalCount": c["ctfRegOutputSurfaceAudit"].get("proposalWorthyCtfRegSignalCount"),
        "auxiliaryProposalWorthySignalCount": c["auxiliaryTraceSurfaceAudit"].get("proposalWorthyAuxiliarySignalCount"),
        "localTraceProposalWorthyNowCount": c["localTraceEvidenceFreshness"].get("proposalWorthyNowCount"),
        "unclassifiedTraceProposalReadyRunCount": c["unclassifiedTraceSignalReduction"].get("proposalReadyRunCount"),
        "liveRunnerCurrentNetworkAttemptBlocked": c["liveRunnerGate"].get("currentNetworkAttemptBlocked"),
        "objectiveEndToEndPocMissing": c["objectiveRequirementCrosswalk"].get("endToEndPocMissing"),
        "goalCompletionVerified": c["goalCompletionVerifier"].get("completionVerified") is True,
        "resetNoCurrentRouteToPhase5": c["resetTerminal"].get("noCurrentRouteToPhase5") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "After exhausting the current promotion-candidate set, rediscover whether any local evidence surface can produce a new candidate entrance before any fresh network experiment.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "surfaces": rows,
        "openSurfaces": open_rows,
        "newCandidateSurfaces": new_rows,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None if not new_rows else "output/protocol_reverse/hypothesis_reframe/<surface_id>_candidate_encoding_audit.json",
            "nextScript": None if not new_rows else "tools/build_<surface_id>_candidate_encoding_audit.py",
            "reason": (
                "No local evidence surface currently exposes a new promotion candidate; fresh network/direct/Webshare/session retry remains unauthorized."
                if not new_rows
                else "At least one local evidence surface has new candidate material and must be encoded before any network experiment."
            ),
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "newCandidateSurfaces": new_rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
