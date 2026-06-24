#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
RESET = ROOT / "output/protocol_reverse/reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
OUT = RESET / "next_evidence_entrance_audit.json"

INPUTS = {
    "serverInternalGapEvidenceInventory": HYP / "server_internal_gap_evidence_inventory.json",
    "crossSampleServerStateProxyMatrix": HYP / "cross_sample_server_state_proxy_matrix.json",
    "historicalProbeResponseClassMatrix": HYP / "historical_probe_response_class_matrix.json",
    "jsInternalEventTaxonomy": HYP / "js_internal_event_taxonomy.json",
    "jsInternalCandidateReduction": HYP / "js_internal_candidate_reduction.json",
    "actionableFrontierAudit": HYP / "actionable_frontier_audit.json",
    "serverInternalUnobservedStateFinalGap": HYP / "server_internal_unobserved_state_final_gap.json",
    "methodologicalTerminalBoundaryAudit": RESET / "methodological_terminal_boundary_audit.json",
    "resetTerminalBoundaryAudit": RESET / "reset_terminal_boundary_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def decision(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("decision") or {}


def build() -> dict[str, Any]:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    inventory = docs["serverInternalGapEvidenceInventory"]
    inventory_sources = inventory.get("candidateNewEvidenceSources") or []

    evaluated = [
        {
            "id": "cross_sample_server_state_proxy_matrix",
            "artifact": str(INPUTS["crossSampleServerStateProxyMatrix"]),
            "checks": checks(docs["crossSampleServerStateProxyMatrix"]),
            "decision": decision(docs["crossSampleServerStateProxyMatrix"]),
            "status": "closed_no_proxy",
        },
        {
            "id": "historical_probe_response_class_matrix",
            "artifact": str(INPUTS["historicalProbeResponseClassMatrix"]),
            "checks": checks(docs["historicalProbeResponseClassMatrix"]),
            "decision": decision(docs["historicalProbeResponseClassMatrix"]),
            "status": "closed_no_success0",
        },
        {
            "id": "js_internal_event_taxonomy_and_reduction",
            "artifact": str(INPUTS["jsInternalCandidateReduction"]),
            "checks": checks(docs["jsInternalCandidateReduction"]),
            "decision": decision(docs["jsInternalCandidateReduction"]),
            "status": "closed_no_replayable_transition",
        },
        {
            "id": "methodological_routes_a_b_c",
            "artifact": str(INPUTS["methodologicalTerminalBoundaryAudit"]),
            "checks": checks(docs["methodologicalTerminalBoundaryAudit"]),
            "decision": decision(docs["methodologicalTerminalBoundaryAudit"]),
            "status": "closed_no_promoted_transition",
        },
    ]

    c_cross = checks(docs["crossSampleServerStateProxyMatrix"])
    c_hist = checks(docs["historicalProbeResponseClassMatrix"])
    c_js = checks(docs["jsInternalCandidateReduction"])
    c_frontier = checks(docs["actionableFrontierAudit"])
    c_final_gap = checks(docs["serverInternalUnobservedStateFinalGap"])
    c_method = checks(docs["methodologicalTerminalBoundaryAudit"])
    c_terminal = checks(docs["resetTerminalBoundaryAudit"])

    all_closed = (
        c_cross.get("candidateClientVisibleProxyCount") == 0
        and c_hist.get("hasHistoricalNoBrowserSuccess0") is False
        and c_js.get("replayableClientTransitionCandidateCount") == 0
        and c_frontier.get("actionableMissingArtifactCount") == 0
        and c_final_gap.get("allLocalProxySearchesNegative") is True
        and c_method.get("allRoutesClosed") is True
        and c_terminal.get("noCurrentRouteToPhase5") is True
    )

    checks_out = {
        "planExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "inventoryCandidateSourceCount": len(inventory_sources),
        "crossSampleCandidateClientVisibleProxyCount": c_cross.get("candidateClientVisibleProxyCount"),
        "historicalNoBrowserSuccess0": c_hist.get("hasHistoricalNoBrowserSuccess0"),
        "jsReplayableClientTransitionCandidateCount": c_js.get("replayableClientTransitionCandidateCount"),
        "actionableFrontierMissingArtifactCount": c_frontier.get("actionableMissingArtifactCount"),
        "finalGapAllLocalProxySearchesNegative": c_final_gap.get("allLocalProxySearchesNegative") is True,
        "methodologicalAllRoutesClosed": c_method.get("allRoutesClosed") is True,
        "resetTerminalNoCurrentRouteToPhase5": c_terminal.get("noCurrentRouteToPhase5") is True,
        "allKnownLocalEvidenceEntrancesClosed": all_closed,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Re-evaluate known local evidence entrances after Methodological Routes A/B/C/D to avoid repeating closed paths.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "checks": checks_out,
        "inventoryCandidateNewEvidenceSources": inventory_sources,
        "evaluatedEntrances": evaluated,
        "remainingPossibleEntrances": [
            {
                "id": "new_external_or_runtime_evidence_not_in_current_artifacts",
                "status": "requires_new_evidence_before_action",
                "requirements": [
                    "Must identify a concrete pre-accept client-visible transition not covered by current artifacts.",
                    "Must include local source/runtime/network/cookie evidence path.",
                    "Must show value lineage into request/cookie/risk.",
                    "Must show pure-protocol constructibility before any fresh Phase 5 attempt.",
                ],
            }
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All known local evidence entrances from the old inventory plus reset methodological routes are closed. "
                "Continue only if a genuinely new evidence artifact is introduced; do not repeat old network or field-mutation attempts."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
