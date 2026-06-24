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
OUT = HYP / "phase3_evidence_entrance_coverage_audit.json"

INPUTS = {
    "authoritativePlan": PLAN,
    "phase3ProposalEvidenceTriage": HYP / "phase3_proposal_evidence_triage.json",
    "unminedLocalEvidenceSourceAudit": HYP / "unmined_local_evidence_source_audit.json",
    "highValueUnminedEvidenceTriage": HYP / "high_value_unmined_evidence_triage.json",
    "recursiveEvidenceBlindspotAudit": HYP / "recursive_evidence_blindspot_audit.json",
    "nonJsonEvidenceBlindspotAudit": HYP / "non_json_evidence_blindspot_audit.json",
    "nextEvidenceEntranceAudit": RESET / "next_evidence_entrance_audit.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def main() -> int:
    docs = {name: load_json(path) for name, path in INPUTS.items() if path.suffix == ".json"}
    phase3 = checks(docs["phase3ProposalEvidenceTriage"])
    unmined = checks(docs["unminedLocalEvidenceSourceAudit"])
    high_value = checks(docs["highValueUnminedEvidenceTriage"])
    recursive = checks(docs["recursiveEvidenceBlindspotAudit"])
    non_json = checks(docs["nonJsonEvidenceBlindspotAudit"])
    next_entrance = checks(docs["nextEvidenceEntranceAudit"])
    reset = checks(docs["resetTerminal"])
    goal = summary(docs["goalGap"])

    entrance_rows = [
        {
            "id": "phase3_named_and_recursive_triage",
            "artifact": str(INPUTS["phase3ProposalEvidenceTriage"]),
            "covered": phase3.get("proposalWorthyEvidenceCount") == 0
            and phase3.get("recursiveJsonReadyOrPromotedSignalCount") == 0,
            "facts": {
                "proposalWorthyEvidenceCount": phase3.get("proposalWorthyEvidenceCount"),
                "recursiveJsonReadyOrPromotedSignalCount": phase3.get("recursiveJsonReadyOrPromotedSignalCount"),
            },
        },
        {
            "id": "high_value_unmined_success_signals",
            "artifact": str(INPUTS["highValueUnminedEvidenceTriage"]),
            "covered": high_value.get("unclassifiedSuccessSignalCount") == 0
            and high_value.get("replayableFreshNoBrowserSuccessEvidenceCount") == 0
            and high_value.get("hasReplayableFreshNoBrowserSuccessEvidence") is False,
            "facts": {
                "highValueUnminedDirectoryCount": high_value.get("highValueUnminedDirectoryCount"),
                "classifiedSuccessSignalFileCount": high_value.get("classifiedSuccessSignalFileCount"),
                "unclassifiedSuccessSignalCount": high_value.get("unclassifiedSuccessSignalCount"),
                "replayableFreshNoBrowserSuccessEvidenceCount": high_value.get("replayableFreshNoBrowserSuccessEvidenceCount"),
                "hasReplayableFreshNoBrowserSuccessEvidence": high_value.get("hasReplayableFreshNoBrowserSuccessEvidence"),
            },
        },
        {
            "id": "recursive_json_blindspot",
            "artifact": str(INPUTS["recursiveEvidenceBlindspotAudit"]),
            "covered": recursive.get("unclassifiedRecursiveSuccessSignalCount") == 0
            and recursive.get("replayableFreshNoBrowserSuccessEvidenceCount") == 0,
            "facts": {
                "recursiveJsonFileCount": recursive.get("recursiveJsonFileCount"),
                "unclassifiedRecursiveSuccessSignalCount": recursive.get("unclassifiedRecursiveSuccessSignalCount"),
                "replayableFreshNoBrowserSuccessEvidenceCount": recursive.get("replayableFreshNoBrowserSuccessEvidenceCount"),
            },
        },
        {
            "id": "non_json_blindspot",
            "artifact": str(INPUTS["nonJsonEvidenceBlindspotAudit"]),
            "covered": non_json.get("unclassifiedSuccessSignalCount") == 0
            and non_json.get("replayableFreshNoBrowserSuccessEvidenceCount") == 0,
            "facts": {
                "scannedTextFileCount": non_json.get("scannedTextFileCount"),
                "successSignalFileCount": non_json.get("successSignalFileCount"),
                "unclassifiedSuccessSignalCount": non_json.get("unclassifiedSuccessSignalCount"),
                "replayableFreshNoBrowserSuccessEvidenceCount": non_json.get("replayableFreshNoBrowserSuccessEvidenceCount"),
            },
        },
        {
            "id": "old_inventory_and_methodological_routes",
            "artifact": str(INPUTS["nextEvidenceEntranceAudit"]),
            "covered": next_entrance.get("allKnownLocalEvidenceEntrancesClosed") is True,
            "facts": {
                "inventoryCandidateSourceCount": next_entrance.get("inventoryCandidateSourceCount"),
                "crossSampleCandidateClientVisibleProxyCount": next_entrance.get("crossSampleCandidateClientVisibleProxyCount"),
                "historicalNoBrowserSuccess0": next_entrance.get("historicalNoBrowserSuccess0"),
                "jsReplayableClientTransitionCandidateCount": next_entrance.get("jsReplayableClientTransitionCandidateCount"),
                "allKnownLocalEvidenceEntrancesClosed": next_entrance.get("allKnownLocalEvidenceEntrancesClosed"),
            },
        },
    ]

    uncovered = [row for row in entrance_rows if row["covered"] is not True]
    proposal_entrance_exhausted = not uncovered
    checks_out = {
        "authoritativePlanExists": PLAN.exists(),
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "entranceRowCount": len(entrance_rows),
        "coveredEntranceRowCount": sum(1 for row in entrance_rows if row["covered"] is True),
        "uncoveredEntranceRowCount": len(uncovered),
        "unminedHighValueDirectoryCount": unmined.get("highValueUnminedDirectoryCount"),
        "highValueUnclassifiedSuccessSignalCount": high_value.get("unclassifiedSuccessSignalCount"),
        "highValueReplayableFreshSuccessCount": high_value.get("replayableFreshNoBrowserSuccessEvidenceCount"),
        "phase3ProposalWorthyEvidenceCount": phase3.get("proposalWorthyEvidenceCount"),
        "phase3RecursiveReadyOrPromotedSignalCount": phase3.get("recursiveJsonReadyOrPromotedSignalCount"),
        "resetNoCurrentRouteToPhase5": reset.get("noCurrentRouteToPhase5") is True,
        "goalBlockingOnlyEndToEndPoc": goal.get("blockingOrMissing") == ["end_to_end_pure_protocol_poc"],
        "proposalEntranceExhaustedForCurrentEvidence": proposal_entrance_exhausted,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Phase 3 entrance coverage audit: verify whether current local evidence entrances leave any proposal-worthy route untriaged.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "entranceRows": entrance_rows,
        "uncoveredEntranceRows": uncovered,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedProposal": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All current local evidence entrances are covered for proposal-intake purposes; no proposal-worthy route is untriaged."
                if proposal_entrance_exhausted
                else "At least one local evidence entrance remains uncovered and must be triaged before deciding proposal intake."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks_out["allInputsExist"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
