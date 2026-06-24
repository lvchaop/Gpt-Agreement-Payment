#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
RESET = ROOT / "output/protocol_reverse/reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"
OUT = HYP / "promoted_transition_candidate_proposals_lint_controls.json"

EVIDENCE = HYP / "collector_server_expected_state_boundary_audit.json"
NEGATIVE = HYP / "encoded_session_binding_candidate_audit.json"
MISSING = HYP / "does_not_exist_for_lint_control.json"

REQUIRED = [
    "id",
    "evidence",
    "preAccept",
    "clientVisible",
    "pureProtocolConstructible",
    "valueChain",
    "negativeControlRefs",
    "contradicted",
]
ALLOWED = {"request", "cookie", "risk", "verify"}


def evidence_exists(value: Any) -> bool:
    if isinstance(value, str):
        return Path(value).exists()
    if isinstance(value, list):
        return bool(value) and all(evidence_exists(item) for item in value)
    return False


def lint_row(proposal: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in REQUIRED if key not in proposal]
    evidence_ok = evidence_exists(proposal.get("evidence"))
    negative_refs_ok = evidence_exists(proposal.get("negativeControlRefs"))
    value_chain_ok = proposal.get("valueChain") in ALLOWED
    boolean_fields_ok = all(
        isinstance(proposal.get(key), bool)
        for key in ["preAccept", "clientVisible", "pureProtocolConstructible", "contradicted"]
        if key in proposal
    )
    structurally_valid = not missing and evidence_ok and negative_refs_ok and value_chain_ok and boolean_fields_ok
    promotable_shape = (
        structurally_valid
        and proposal.get("preAccept") is True
        and proposal.get("clientVisible") is True
        and proposal.get("pureProtocolConstructible") is True
        and proposal.get("contradicted") is not True
    )
    return {
        "id": proposal.get("id"),
        "missingRequired": missing,
        "evidenceExists": evidence_ok,
        "negativeControlRefsExist": negative_refs_ok,
        "valueChainAllowed": value_chain_ok,
        "booleanFieldsOk": boolean_fields_ok,
        "structurallyValid": structurally_valid,
        "promotableShape": promotable_shape,
    }


def main() -> int:
    controls = [
        {
            "id": "positive_shape_control",
            "proposal": {
                "id": "positive_shape_control",
                "evidence": str(EVIDENCE),
                "preAccept": True,
                "clientVisible": True,
                "pureProtocolConstructible": True,
                "valueChain": "request",
                "negativeControlRefs": [str(NEGATIVE)],
                "contradicted": False,
            },
            "expect": {"structurallyValid": True, "promotableShape": True},
        },
        {
            "id": "missing_evidence_control",
            "proposal": {
                "id": "missing_evidence_control",
                "evidence": str(MISSING),
                "preAccept": True,
                "clientVisible": True,
                "pureProtocolConstructible": True,
                "valueChain": "request",
                "negativeControlRefs": [str(NEGATIVE)],
                "contradicted": False,
            },
            "expect": {"structurallyValid": False, "promotableShape": False},
        },
        {
            "id": "bad_value_chain_control",
            "proposal": {
                "id": "bad_value_chain_control",
                "evidence": str(EVIDENCE),
                "preAccept": True,
                "clientVisible": True,
                "pureProtocolConstructible": True,
                "valueChain": "timing",
                "negativeControlRefs": [str(NEGATIVE)],
                "contradicted": False,
            },
            "expect": {"structurallyValid": False, "promotableShape": False},
        },
        {
            "id": "contradicted_control",
            "proposal": {
                "id": "contradicted_control",
                "evidence": str(EVIDENCE),
                "preAccept": True,
                "clientVisible": True,
                "pureProtocolConstructible": True,
                "valueChain": "request",
                "negativeControlRefs": [str(NEGATIVE)],
                "contradicted": True,
            },
            "expect": {"structurallyValid": True, "promotableShape": False},
        },
    ]

    rows = []
    for control in controls:
        lint = lint_row(control["proposal"])
        failures = [
            f"{key}: expected {expected!r}, got {lint.get(key)!r}"
            for key, expected in control["expect"].items()
            if lint.get(key) != expected
        ]
        rows.append({**control, "lint": lint, "failures": failures, "passed": not failures})

    checks = {
        "planExists": PLAN.exists(),
        "controlCount": len(rows),
        "passedControlCount": sum(1 for row in rows if row["passed"]),
        "failedControlCount": sum(1 for row in rows if not row["passed"]),
        "positiveShapeControlPassed": next(row for row in rows if row["id"] == "positive_shape_control")["passed"],
        "missingEvidenceControlPassed": next(row for row in rows if row["id"] == "missing_evidence_control")["passed"],
        "badValueChainControlPassed": next(row for row in rows if row["id"] == "bad_value_chain_control")["passed"],
        "contradictedControlPassed": next(row for row in rows if row["id"] == "contradicted_control")["passed"],
        "allControlsPassed": all(row["passed"] for row in rows),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Control audit for promoted transition proposal lint predicates without modifying the live proposals file.",
        "inputs": {
            "positiveEvidence": str(EVIDENCE),
            "negativeControlRef": str(NEGATIVE),
            "resetTerminal": str(RESET / "reset_terminal_boundary_audit.json"),
        },
        "checks": checks,
        "rows": rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "Proposal lint controls pass; this only validates gate behavior and does not create a live promoted transition.",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks["allControlsPassed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
