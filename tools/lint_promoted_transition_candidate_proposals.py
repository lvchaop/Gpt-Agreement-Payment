#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
PLAN = ROOT / "docs/pure-protocol-human-evidence-gated-implementation-plan.md"
PROPOSALS = HYP / "promoted_transition_candidate_proposals.json"
OUT = HYP / "promoted_transition_candidate_proposals_lint.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def evidence_exists(value: Any) -> bool:
    if isinstance(value, str):
        return Path(value).exists()
    if isinstance(value, list):
        return bool(value) and all(evidence_exists(item) for item in value)
    return False


def main() -> int:
    doc = read_json(PROPOSALS)
    schema = doc.get("schema") or {}
    required = schema.get("required") or []
    allowed = set(schema.get("valueChainAllowed") or [])
    rows: list[dict[str, Any]] = []

    for index, proposal in enumerate(doc.get("proposals") or []):
        missing = [key for key in required if key not in proposal]
        evidence_ok = evidence_exists(proposal.get("evidence"))
        negative_refs_ok = evidence_exists(proposal.get("negativeControlRefs"))
        value_chain_ok = proposal.get("valueChain") in allowed
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
        rows.append(
            {
                "index": index,
                "id": proposal.get("id"),
                "missingRequired": missing,
                "evidenceExists": evidence_ok,
                "negativeControlRefsExist": negative_refs_ok,
                "valueChainAllowed": value_chain_ok,
                "booleanFieldsOk": boolean_fields_ok,
                "structurallyValid": structurally_valid,
                "promotableShape": promotable_shape,
            }
        )

    checks = {
        "planExists": PLAN.exists(),
        "proposalFileExists": PROPOSALS.exists(),
        "schemaRequiredCount": len(required),
        "schemaHasRequiredFields": set(required) >= {
            "id",
            "evidence",
            "preAccept",
            "clientVisible",
            "pureProtocolConstructible",
            "valueChain",
            "negativeControlRefs",
            "contradicted",
        },
        "proposalCount": len(rows),
        "validProposalCount": sum(1 for row in rows if row["structurallyValid"]),
        "invalidProposalCount": sum(1 for row in rows if not row["structurallyValid"]),
        "promotableShapeCount": sum(1 for row in rows if row["promotableShape"]),
        "allProposalsStructurallyValid": all(row["structurallyValid"] for row in rows),
        "emptyProposalSet": len(rows) == 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    result = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Lint promoted_transition_candidate_proposals.json before candidate intake consumes proposed new evidence routes.",
        "inputs": {"candidateProposals": str(PROPOSALS)},
        "checks": checks,
        "rows": rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "No proposals are present; proposal lint passes as an empty gated input."
                if checks["emptyProposalSet"]
                else "Proposal lint completed; candidate intake must still decide promotion."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0 if checks["proposalFileExists"] and checks["allProposalsStructurallyValid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
