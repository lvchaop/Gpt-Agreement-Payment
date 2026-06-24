#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
RESET = ROOT / "output/protocol_reverse/reset_plan"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "post_static_context_terminal_gap_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build() -> dict[str, Any]:
    context_proxy = read_json(HYP / "browser_context_to_server_state_proxy_audit.json")
    static_inventory = read_json(HYP / "browser_context_static_gap_inventory.json")
    c5 = read_json(HYP / "encoder_variant_terminal_audit.json")
    server_gap = read_json(HYP / "server_internal_unobserved_state_final_gap.json")
    reset_terminal = read_json(RESET / "reset_terminal_boundary_audit.json")
    goal = read_json(GOAL / "pure_protocol_goal_gap_audit.json")

    c_context = checks(context_proxy)
    c_static = checks(static_inventory)
    c_c5 = checks(c5)
    c_server = checks(server_gap)
    c_reset = checks(reset_terminal)
    goal_summary = goal.get("summary") or {}

    closed_branches = [
        {
            "id": "C5_encoder_family",
            "evidence": str(HYP / "encoder_variant_terminal_audit.json"),
            "closed": c_c5.get("encoderVariantFamilyClosedNoSuccess") is True,
            "promoted": c_c5.get("promotedSingleTransitionCandidateCount") or 0,
        },
        {
            "id": "H4_H5_browser_context_proxy",
            "evidence": str(HYP / "browser_context_to_server_state_proxy_audit.json"),
            "closed": c_context.get("allBrowserContextServerVisibleProxiesReduced") is True,
            "promoted": c_context.get("promotedSingleTransitionCandidateCount") or 0,
        },
        {
            "id": "H4_static_context_inventory",
            "evidence": str(HYP / "browser_context_static_gap_inventory.json"),
            "closed": c_static.get("allStaticContextGapsReduced") is True,
            "promoted": c_static.get("promotedSingleTransitionCandidateCount") or 0,
        },
        {
            "id": "reset_terminal_routes",
            "evidence": str(RESET / "reset_terminal_boundary_audit.json"),
            "closed": c_reset.get("noCurrentRouteToPhase5") is True,
            "promoted": c_reset.get("singleTransitionCandidateCount") or 0,
        },
    ]

    promoted_total = sum(int(row.get("promoted") or 0) for row in closed_branches)
    all_closed = all(row.get("closed") is True for row in closed_branches)
    goal_missing = "end_to_end_pure_protocol_poc" in (goal_summary.get("blockingOrMissing") or [])
    out_checks = {
        "planExists": PLAN.exists(),
        "contextProxyReduced": c_context.get("allBrowserContextServerVisibleProxiesReduced") is True,
        "staticContextReduced": c_static.get("allStaticContextGapsReduced") is True,
        "c5ClosedNoSuccess": c_c5.get("encoderVariantFamilyClosedNoSuccess") is True,
        "serverInternalAllLocalProxySearchesNegative": c_server.get("allLocalProxySearchesNegative") is True,
        "resetTerminalNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "endToEndPureProtocolPocMissing": goal_missing,
        "closedBranchCount": sum(1 for row in closed_branches if row.get("closed") is True),
        "allClosedBranchesClosed": all_closed,
        "promotedSingleTransitionCandidateCount": promoted_total,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Terminal consolidation after browser-context static inventory: decide whether any current branch authorizes a fresh pure-protocol network experiment.",
        "inputs": {
            "browserContextToServerStateProxyAudit": str(HYP / "browser_context_to_server_state_proxy_audit.json"),
            "browserContextStaticGapInventory": str(HYP / "browser_context_static_gap_inventory.json"),
            "encoderVariantTerminalAudit": str(HYP / "encoder_variant_terminal_audit.json"),
            "serverInternalUnobservedStateFinalGap": str(HYP / "server_internal_unobserved_state_final_gap.json"),
            "resetTerminalBoundaryAudit": str(RESET / "reset_terminal_boundary_audit.json"),
            "goalGapAudit": str(GOAL / "pure_protocol_goal_gap_audit.json"),
        },
        "checks": out_checks,
        "closedBranches": closed_branches,
        "remainingGap": {
            "id": "collector_server_internal_or_unobserved_expected_state_after_context_inventory",
            "status": "not_reduced_to_replayable_client_transition",
            "whatIsProven": (
                "C5 encoder family, browser context postMessage/cookie bridge proxies, static PX561 context producers, "
                "and reset Route A/B/C/D evidence do not promote a single pure-protocol transition."
            ),
            "whatIsMissing": (
                "A concrete client-visible pre-accept transition with value lineage into request/cookie/risk that can be changed alone "
                "in a fresh no-browser session to produce collector oIIoIooo|0."
            ),
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "All current local evidence entrances after C5 and browser-context inventory are closed without a promoted single transition. "
                "Do not run fresh network attempts from this state; reopen only with genuinely new evidence that maps to request/cookie/risk before acceptance."
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
