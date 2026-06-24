#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
BASE = REPO / "output/protocol_reverse/hypothesis_reframe"
OUT = BASE / "actionable_frontier_audit.json"

TERMINAL_AUTHORITY = {
    "hypothesis_reframe_status.json",
    "server_internal_unobserved_state_final_gap.json",
    "pure_protocol_completion_requirements_audit.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_next_refs(obj: Any, source: Path, loc: str = "") -> list[dict[str, Any]]:
    rows = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{loc}/{key}"
            if key in {"nextArtifact", "nextScript", "nextRecommendedArtifact", "nextRecommendedScript"}:
                rows.append({"source": source.name, "path": child, "key": key, "value": value})
            rows.extend(collect_next_refs(value, source, child))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            rows.extend(collect_next_refs(value, source, f"{loc}/{index}"))
    return rows


def normalize_artifact(value: Any) -> Path | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = REPO / value
    return path


def build() -> dict[str, Any]:
    json_files = sorted(BASE.glob("*.json"))
    refs = []
    for path in json_files:
        refs.extend(collect_next_refs(load_json(path), path))

    artifact_refs = [row for row in refs if "Artifact" in row["key"]]
    script_refs = [row for row in refs if "Script" in row["key"]]
    rows = []
    for row in artifact_refs:
        target = normalize_artifact(row.get("value"))
        exists = target.exists() if target else False
        terminal_source = row["source"] in TERMINAL_AUTHORITY
        actionable = bool(target and not exists and not terminal_source)
        rows.append(
            {
                **row,
                "target": str(target) if target else None,
                "targetExists": exists,
                "terminalAuthoritySource": terminal_source,
                "actionableMissingArtifact": actionable,
            }
        )

    terminal_rows = [
        row for row in rows
        if row["source"] in TERMINAL_AUTHORITY
    ]
    terminal_next_null = all(row.get("value") is None for row in terminal_rows)
    actionable_missing = [row for row in rows if row["actionableMissingArtifact"]]
    nonterminal_missing = [
        row for row in rows
        if row["target"] and not row["targetExists"] and not row["terminalAuthoritySource"]
    ]
    completed_frontier_refs = [
        row for row in rows
        if row["target"] and row["targetExists"]
    ]

    status = load_json(BASE / "hypothesis_reframe_status.json")
    final_gap = load_json(BASE / "server_internal_unobserved_state_final_gap.json")
    requirements = load_json(BASE / "pure_protocol_completion_requirements_audit.json")

    checks = {
        "jsonArtifactCount": len(json_files),
        "nextArtifactRefCount": len(artifact_refs),
        "nextScriptRefCount": len(script_refs),
        "terminalAuthorityNextNull": terminal_next_null,
        "completedFrontierRefCount": len(completed_frontier_refs),
        "actionableMissingArtifactCount": len(actionable_missing),
        "nonterminalMissingArtifactCount": len(nonterminal_missing),
        "statusNextRecommendedArtifactIsNull": (status.get("currentDecision") or {}).get("nextRecommendedArtifact") is None,
        "finalGapNextArtifactIsNull": (final_gap.get("decision") or {}).get("nextArtifact") is None,
        "requirementsNextArtifactIsNull": (requirements.get("decision") or {}).get("nextArtifact") is None,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Audit all nextArtifact/nextScript references and decide whether any unfinished local actionable frontier remains.",
        "terminalAuthority": sorted(TERMINAL_AUTHORITY),
        "nextArtifactRows": rows,
        "actionableMissingArtifacts": actionable_missing,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "actionableFrontierExists": bool(actionable_missing),
            "reason": (
                "No actionable missing artifact remains: terminal authority artifacts point to null next steps and non-terminal nextArtifact references resolve to existing artifacts."
                if not actionable_missing
                else "At least one non-terminal nextArtifact target is missing and should be built before considering blocked."
            ),
            "nextArtifact": str(actionable_missing[0]["target"]) if actionable_missing else None,
            "nextScript": None,
        },
        "checks": checks,
    }


def main() -> int:
    result = build()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
