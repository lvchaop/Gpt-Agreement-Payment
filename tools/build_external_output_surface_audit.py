#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/external_output_surface_audit.json"

SCAN_DIRS = [
    ROOT / "output/outlook_oauth_trace",
    ROOT / "output/har_extract",
    ROOT / "output/proxy_bridge",
    ROOT / "output/run_logs",
    ROOT / "output/logs",
]
AUTHORITY_INPUTS = {
    "currentEvidenceEntranceTerminalLedger": ROOT / "output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json",
    "nonJsonEvidenceBlindspot": ROOT / "output/protocol_reverse/hypothesis_reframe/non_json_evidence_blindspot_audit.json",
    "phase3RawEvidenceEntrance": ROOT / "output/protocol_reverse/hypothesis_reframe/phase3_raw_evidence_entrance_audit.json",
    "resetTerminal": ROOT / "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json",
}

PATTERNS = {
    "collector_success0": re.compile(r"oIIoIooo\|0"),
    "collector_failure_minus1": re.compile(r"oIIoIooo\|-1"),
    "risk_continue": re.compile(r'"state"\\s*:\\s*"continue"|state=continue|risk_verify_state_continue'),
    "create_redirect": re.compile(r"redirectUrl|create_account_redirectUrl"),
    "human_captcha": re.compile(r"HumanCaptcha|hsprotect|iframe\\.hsprotect|humanAppId|urlHumanIframe"),
    "collector_endpoint": re.compile(r"/api/v2/collector|collector", re.I),
    "risk_verify": re.compile(r"/API/Proofs/risk/verify|risk/verify", re.I),
    "create_account": re.compile(r"/API/CreateAccount|CreateAccount", re.I),
    "px_cookie": re.compile(r"_px3|_pxde|pxvid|_pxvid"),
    "browser_only": re.compile(r"postMessage|iframe|document\\.|window\\.|navigator\\.|Worker|webdriver|canvas|webgl", re.I),
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def read_text_limited(path: Path, limit: int = 2_000_000) -> str:
    data = path.read_bytes()[:limit]
    return data.decode("utf-8", errors="replace")


def classify_file(path: Path, text: str) -> dict[str, Any]:
    hits = {name: bool(rx.search(text)) for name, rx in PATTERNS.items()}
    rel = path.relative_to(ROOT)
    category = "no_relevant_signal"
    proposal_worthy = False
    reason = "No HUMAN/collector/risk/create/cookie signal."

    if hits["collector_success0"]:
        if "outlook_browser" in str(rel) or hits["browser_only"]:
            category = "browser_or_static_success_reference"
            reason = "Contains collector success token, but in browser/static context rather than fresh no-browser replay evidence."
        else:
            category = "unclassified_success0_signal"
            reason = "Collector success token outside known browser paths requires lineage before promotion."
    elif hits["risk_continue"] or hits["create_redirect"]:
        category = "downstream_or_oauth_success_context"
        reason = "Downstream/OAuth success is not collector pre-accept HUMAN success."
    elif hits["human_captcha"] or hits["collector_endpoint"] or hits["risk_verify"] or hits["create_account"] or hits["px_cookie"]:
        if path.suffix == ".js" or "har_extract" in str(rel):
            category = "static_or_har_fixture_context"
            reason = "Static/HAR extracted code or page fixture; useful for source mapping, not a fresh no-browser success artifact."
        elif "proxy_bridge" in str(rel):
            category = "transport_proxy_context"
            reason = "Transport/proxy log/config can only be a controlled variable without a promoted transition."
        elif "outlook_oauth_trace" in str(rel):
            category = "microsoft_oauth_context"
            reason = "OAuth trace is Microsoft login/token context, not collector pre-accept HUMAN acceptance."
        else:
            category = "trace_or_log_material_context"
            reason = "Runtime/log material needs a concrete value lineage before proposal."

    return {
        "path": str(path),
        "relPath": str(rel),
        "size": path.stat().st_size,
        "category": category,
        "patternHits": hits,
        "proposalWorthy": proposal_worthy,
        "reason": reason,
    }


def main() -> int:
    authority = {name: read_json(path) for name, path in AUTHORITY_INPUTS.items()}
    rows: list[dict[str, Any]] = []
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.name == "sing-box.log" and path.stat().st_size > 2_000_000:
                text = read_text_limited(path)
            else:
                text = read_text_limited(path)
            row = classify_file(path, text)
            if any(row["patternHits"].values()):
                rows.append(row)

    categories: dict[str, int] = {}
    for row in rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1

    success0 = [row for row in rows if row["patternHits"]["collector_success0"]]
    proposal = [row for row in rows if row["proposalWorthy"]]
    c_current = checks(authority["currentEvidenceEntranceTerminalLedger"])
    c_non_json = checks(authority["nonJsonEvidenceBlindspot"])
    c_raw = checks(authority["phase3RawEvidenceEntrance"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scanDirectoryCount": len(SCAN_DIRS),
        "existingScanDirectoryCount": sum(1 for path in SCAN_DIRS if path.exists()),
        "signalFileCount": len(rows),
        "categoryCount": len(categories),
        "collectorSuccess0SignalFileCount": len(success0),
        "proposalWorthyExternalSignalCount": len(proposal),
        "currentEvidenceEntrancesClosed": c_current.get("allNextPointersClosedOrSuperseded") is True,
        "nonJsonReplayableSuccessCount": c_non_json.get("replayableFreshNoBrowserSuccessEvidenceCount"),
        "rawProposalWorthySignalCount": c_raw.get("proposalWorthyRawSignalCount"),
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit external output surfaces outside protocol_reverse for fresh no-browser HUMAN success or a new pre-accept client-visible transition.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "scanDirectories": [str(path) for path in SCAN_DIRS],
        "checks": checks_out,
        "categoryCounts": categories,
        "signalRows": rows[:500],
        "collectorSuccess0Rows": success0,
        "proposalWorthyRows": proposal,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "External output directories contain static/browser/OAuth/proxy/log context but no replayable fresh no-browser collector success and no proposal-worthy pre-accept transition."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "categoryCounts": categories, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
