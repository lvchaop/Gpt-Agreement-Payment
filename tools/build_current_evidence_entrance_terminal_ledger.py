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
OUT = HYP / "current_evidence_entrance_terminal_ledger.json"

SCAN_ROOTS = [HYP, RESET, GOAL]
AUTHORITY_INPUTS = {
    "currentRouteAuthority": HYP / "current_route_authority_audit.json",
    "hypothesisPlanCoverage": HYP / "hypothesis_plan_coverage_audit.json",
    "nextEvidenceEntrance": RESET / "next_evidence_entrance_audit.json",
    "coupledBoundaryTerminal": HYP / "coupled_boundary_terminal_ledger.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "resetTerminal": RESET / "reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def decision(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("decision") or {}


def resolve_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path


def path_exists(value: str | None) -> bool:
    if not value:
        return False
    return resolve_path(value).exists()


def extract_next(doc: dict[str, Any]) -> tuple[str | None, str | None]:
    d = decision(doc)
    next_block = doc.get("next") or {}
    return (
        d.get("nextArtifact") or next_block.get("artifact"),
        d.get("nextScript") or next_block.get("script"),
    )


def scan_next_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.glob("*.json")):
            doc = read_json(path)
            next_artifact, next_script = extract_next(doc)
            if not next_artifact and not next_script:
                continue
            c = checks(doc)
            d = decision(doc)
            ready = c.get("readyForFreshExperiment", d.get("readyForFreshExperiment"))
            goal_complete = c.get("goalComplete", d.get("goalComplete"))
            rows.append(
                {
                    "source": str(path),
                    "sourceRel": str(path.relative_to(ROOT)),
                    "readyForFreshExperiment": ready,
                    "goalComplete": goal_complete,
                    "nextArtifact": next_artifact,
                    "nextArtifactExists": path_exists(next_artifact),
                    "nextScript": next_script,
                    "nextScriptExists": path_exists(next_script),
                }
            )
    return rows


def main() -> int:
    authority = {name: read_json(path) for name, path in AUTHORITY_INPUTS.items()}
    c_current = checks(authority["currentRouteAuthority"])
    c_coverage = checks(authority["hypothesisPlanCoverage"])
    c_next = checks(authority["nextEvidenceEntrance"])
    c_coupled = checks(authority["coupledBoundaryTerminal"])
    c_completion = checks(authority["completionRequirements"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])

    rows = scan_next_rows()
    unresolved = [
        row
        for row in rows
        if (row["nextArtifact"] and not row["nextArtifactExists"])
        or (row["nextScript"] and not row["nextScriptExists"])
    ]
    ready_rows = [row for row in rows if row.get("readyForFreshExperiment") is True]
    active_ready_rows = [
        row
        for row in ready_rows
        if c_current.get("currentPromotedSingleTransitionCandidateCount") == 1
        and c_reset.get("readyForFreshExperiment") is True
    ]

    all_closed = (
        len(unresolved) == 0
        and len(active_ready_rows) == 0
        and c_current.get("currentPromotedSingleTransitionCandidateCount") == 0
        and c_coverage.get("allHypothesesCovered") is True
        and c_next.get("allKnownLocalEvidenceEntrancesClosed") is True
        and c_coupled.get("allCoupledBoundariesClosedForCurrentEvidence") is True
    )

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scannedDirectoryCount": len(SCAN_ROOTS),
        "nextPointerCount": len(rows),
        "unresolvedNextPointerCount": len(unresolved),
        "readySignalNextPointerCount": len(ready_rows),
        "activeActionableNextPointerCount": len(active_ready_rows),
        "currentPromotedSingleTransitionCandidateCount": c_current.get("currentPromotedSingleTransitionCandidateCount"),
        "hypothesisPlanStaleHistoricalNextPointerCount": c_coverage.get("staleHistoricalNextPointerCount"),
        "hypothesisPlanAllHypothesesCovered": c_coverage.get("allHypothesesCovered") is True,
        "allKnownLocalEvidenceEntrancesClosed": c_next.get("allKnownLocalEvidenceEntrancesClosed") is True,
        "allCoupledBoundariesClosedForCurrentEvidence": c_coupled.get("allCoupledBoundariesClosedForCurrentEvidence") is True,
        "completionNoCurrentExperimentRoute": c_completion.get("noCurrentExperimentRoute") is True,
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "allNextPointersClosedOrSuperseded": all_closed,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Terminal ledger for historical nextArtifact/nextScript pointers so stale execution hints do not reopen closed routes.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "checks": checks_out,
        "nextPointers": rows,
        "unresolvedNextPointers": unresolved,
        "readySignalNextPointers": ready_rows,
        "activeActionableNextPointers": active_ready_rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Historical nextArtifact pointers are either already materialized or superseded by current terminal authority. "
                "There is no active actionable next pointer because current promoted transition count is zero and the goal verifier remains incomplete."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
