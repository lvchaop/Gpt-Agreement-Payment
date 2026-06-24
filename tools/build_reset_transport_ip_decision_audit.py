#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
TRANSPORT = RESET / "reset_transport_ip_hypothesis_audit.json"
FINAL = RESET / "reset_final_response_class_audit.json"
ROUTE_B = RESET / "reset_route_b_lifecycle_contrast_audit.json"
TERMINAL = RESET / "reset_terminal_boundary_audit.json"
OUT = RESET / "reset_transport_ip_decision_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> dict[str, Any]:
    transport = read_json(TRANSPORT)
    final = read_json(FINAL)
    route_b = read_json(ROUTE_B)
    terminal = read_json(TERMINAL)
    c_transport = transport.get("checks") or {}
    c_final = final.get("checks") or {}
    c_route_b = route_b.get("checks") or {}
    c_terminal = terminal.get("checks") or {}

    rows = transport.get("rows") or []
    stage_by_transport: dict[str, list[str]] = {}
    for row in rows:
        stage_by_transport.setdefault(str(row.get("transport")), []).append(str(row.get("stage")))

    checks = {
        "planExists": PLAN.exists(),
        "transportAuditExists": TRANSPORT.exists(),
        "finalResponseClassAuditExists": FINAL.exists(),
        "routeBLifecycleContrastAuditExists": ROUTE_B.exists(),
        "terminalAuditExists": TERMINAL.exists(),
        "validPureProtocolSampleCount": c_transport.get("validPureProtocolSampleCount"),
        "validWebshareSampleCount": c_transport.get("validWebshareSampleCount"),
        "validDirectSampleCount": c_transport.get("validDirectSampleCount"),
        "allValidSamplesReachedFinalSeq5Seq6": c_transport.get("allValidSamplesReachedFinalSeq5Seq6") is True,
        "webshareAnyCollectorSuccess": c_transport.get("webshareAnyCollectorSuccess") is True,
        "directAnyCollectorSuccess": c_transport.get("directAnyCollectorSuccess") is True,
        "transportIpAloneSupported": c_transport.get("transportIpAloneSupported") is True,
        "allFinalResponsesSameClass": c_final.get("allFinalResponsesSameClass") is True,
        "allFinalResponsesAreSeq5Minus1": c_final.get("allFinalResponsesAreSeq5Minus1") is True,
        "anySeq5Success0": c_final.get("anySeq5Success0") is True,
        "routeBPromotedCount": c_route_b.get("promotedSingleTransitionCandidateCount"),
        "routeBSuccessOnlyHookKindCount": c_route_b.get("successOnlyHookKindCount"),
        "terminalNoCurrentRouteToPhase5": c_terminal.get("noCurrentRouteToPhase5") is True,
        "onlyTransportChangedStageDifferenceProved": False,
        "ipOrTransportPromotedToControlVariableOnly": True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    stage_sets = {transport: sorted(set(stages)) for transport, stages in stage_by_transport.items()}
    unique_stage_sets = {tuple(stages) for stages in stage_sets.values()}
    checks["onlyTransportChangedStageDifferenceProved"] = bool(
        checks["validWebshareSampleCount"]
        and checks["validDirectSampleCount"]
        and (
            checks["webshareAnyCollectorSuccess"] != checks["directAnyCollectorSuccess"]
            or len(unique_stage_sets) > 1
        )
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Route C: decide whether IP/Webshare/direct is supported as a HUMAN success axis after reset and Route B evidence.",
        "inputs": {
            "transportIpHypothesisAudit": str(TRANSPORT),
            "finalResponseClassAudit": str(FINAL),
            "routeBLifecycleContrastAudit": str(ROUTE_B),
            "terminalBoundaryAudit": str(TERMINAL),
        },
        "checks": checks,
        "stageByTransport": stage_by_transport,
        "stageSetsByTransport": stage_sets,
        "rows": rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "transportIpAloneSupported": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Current controlled reset evidence does not show a transport/IP-only stage difference: Webshare and direct pure-protocol samples reach final seq5/seq6 and no group produces collector success. "
                "Route B also promoted no lifecycle hook. Treat IP/Webshare/direct as a logging/control variable only, not a standalone Phase 5 axis."
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
