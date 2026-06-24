#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/auxiliary_trace_surface_audit.json"
SCAN_DIRS = [ROOT / "CTF-reg/outputs", ROOT / "tem"]
AUTHORITY_INPUTS = {
    "ctfRegOutputSurfaceAudit": ROOT / "output/protocol_reverse/hypothesis_reframe/ctf_reg_output_surface_audit.json",
    "currentEvidenceEntranceTerminalLedger": ROOT / "output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json",
    "resetTerminal": ROOT / "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json",
}

TEXT_EXTS = {".jsonl", ".har", ".html", ".json", ".txt", ".log"}

PATTERNS = {
    "collector_success0": re.compile(r"oIIoIooo\|0"),
    "collector_failure_minus1": re.compile(r"oIIoIooo\|-1"),
    "risk_continue": re.compile(r'"state"\s*:\s*"continue"|state=continue|risk_verify_state_continue'),
    "create_redirect": re.compile(r"redirectUrl|create_account_redirectUrl|res=success"),
    "human_captcha": re.compile(r"HumanCaptcha|hsprotect|captcha\.hsprotect|iframe\.hsprotect|humanAppId|urlHumanIframe", re.I),
    "collector_endpoint": re.compile(r"/api/v2/collector|/api/v2/msft|collector", re.I),
    "risk_verify": re.compile(r"/API/Proofs/risk/verify|risk/verify", re.I),
    "create_account": re.compile(r"/API/CreateAccount|CreateAccount", re.I),
    "px_cookie": re.compile(r"_px3|_pxde|_pxvid|pxvid"),
    "chatgpt_auth": re.compile(r"chatgpt\.com|auth0\.openai\.com|/api/auth/", re.I),
    "paypal": re.compile(r"paypal\.com|paypalobjects\.com|checkoutnow|webapps/hermes", re.I),
    "stripe": re.compile(r"stripe\.com|stripe\.network|js\.stripe\.com", re.I),
    "browser_runtime": re.compile(r"postMessage|iframe|document\.|window\.|navigator\.|Worker|webdriver|canvas|webgl", re.I),
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def read_text_limited(path: Path, limit: int = 2_000_000) -> str:
    return path.read_bytes()[:limit].decode("utf-8", errors="replace")


def har_summary(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(read_text_limited(path, 50_000_000))
    except json.JSONDecodeError:
        return {"parseable": False}
    entries = ((data.get("log") or {}).get("entries") or [])
    hosts: dict[str, int] = {}
    for entry in entries[:5000]:
        url = ((entry.get("request") or {}).get("url") or "")
        host = re.sub(r"^https?://([^/]+).*", r"\1", url)
        if host and host != url:
            hosts[host] = hosts.get(host, 0) + 1
    return {"parseable": True, "entryCount": len(entries), "hostCounts": dict(sorted(hosts.items())[:30])}


def classify(path: Path, body: str) -> dict[str, Any]:
    rel = str(path.relative_to(ROOT))
    hits = {name: bool(rx.search(body)) for name, rx in PATTERNS.items()}
    category = "no_relevant_signal"
    reason = "No HUMAN/collector/risk/CreateAccount/cookie signal."

    if hits["collector_success0"]:
        if hits["browser_runtime"]:
            category = "browser_success_reference"
            reason = "Collector success token is embedded in browser/runtime material, not fresh no-browser replay evidence."
        else:
            category = "unclassified_success0_signal"
            reason = "Collector success token outside known browser paths would require lineage before promotion."
    elif hits["human_captcha"] or hits["collector_endpoint"] or hits["risk_verify"] or hits["create_account"] or hits["px_cookie"]:
        if hits["paypal"] or hits["stripe"] or hits["chatgpt_auth"]:
            category = "unrelated_third_party_auth_or_payment_context"
            reason = "Signal-like tokens occur in unrelated ChatGPT/PayPal/Stripe auth or payment traces, outside Outlook HUMAN collector chain."
        else:
            category = "human_related_material_context"
            reason = "HUMAN-related material exists but lacks a fresh no-browser success or proposal-ready lineage."
    elif hits["risk_continue"] or hits["create_redirect"]:
        category = "downstream_or_payment_success_context"
        reason = "Continue/redirect tokens appear in auth/payment page state, not collector pre-accept HUMAN acceptance."
    elif hits["chatgpt_auth"]:
        category = "unrelated_chatgpt_auth_context"
        reason = "ChatGPT auth traces are outside Outlook signup HUMAN collector replay."
    elif hits["paypal"]:
        category = "unrelated_paypal_context"
        reason = "PayPal checkout traces are outside Outlook signup HUMAN collector replay."
    elif hits["stripe"]:
        category = "unrelated_stripe_context"
        reason = "Stripe traces are outside Outlook signup HUMAN collector replay."

    return {
        "path": str(path),
        "relPath": rel,
        "size": path.stat().st_size,
        "category": category,
        "patternHits": hits,
        "proposalWorthy": False,
        "reason": reason,
    }


def main() -> int:
    authority = {name: read_json(path) for name, path in AUTHORITY_INPUTS.items()}
    text_file_count = 0
    har_file_count = 0
    jsonl_file_count = 0
    html_file_count = 0
    skipped_file_count = 0
    signal_rows: list[dict[str, Any]] = []
    har_rows: list[dict[str, Any]] = []

    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            suffix = path.suffix.lower()
            if suffix not in TEXT_EXTS:
                skipped_file_count += 1
                continue
            text_file_count += 1
            if suffix == ".har":
                har_file_count += 1
                har_rows.append({"path": str(path), "relPath": str(path.relative_to(ROOT)), **har_summary(path)})
            if suffix == ".jsonl":
                jsonl_file_count += 1
            if suffix == ".html":
                html_file_count += 1
            row = classify(path, read_text_limited(path))
            if any(row["patternHits"].values()):
                signal_rows.append(row)

    categories: dict[str, int] = {}
    for row in signal_rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1

    success0_rows = [row for row in signal_rows if row["patternHits"]["collector_success0"]]
    proposal_rows = [row for row in signal_rows if row["proposalWorthy"]]
    c_ctf = checks(authority["ctfRegOutputSurfaceAudit"])
    c_current = checks(authority["currentEvidenceEntranceTerminalLedger"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scanDirectoryCount": len(SCAN_DIRS),
        "existingScanDirectoryCount": sum(1 for path in SCAN_DIRS if path.exists()),
        "textFileCount": text_file_count,
        "harFileCount": har_file_count,
        "jsonlFileCount": jsonl_file_count,
        "htmlFileCount": html_file_count,
        "skippedFileCount": skipped_file_count,
        "signalFileCount": len(signal_rows),
        "categoryCount": len(categories),
        "collectorSuccess0SignalFileCount": len(success0_rows),
        "proposalWorthyAuxiliarySignalCount": len(proposal_rows),
        "ctfRegProposalWorthySignalCount": c_ctf.get("proposalWorthyCtfRegSignalCount"),
        "currentEvidenceEntrancesClosed": c_current.get("allNextPointersClosedOrSuperseded") is True,
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit CTF-reg/outputs and tem HAR/HTML traces for fresh no-browser HUMAN success or a proposal-worthy Outlook/HUMAN transition.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "scanDirectories": [str(path) for path in SCAN_DIRS],
        "checks": checks_out,
        "categoryCounts": categories,
        "signalRows": signal_rows[:500],
        "collectorSuccess0Rows": success0_rows,
        "proposalWorthyRows": proposal_rows,
        "harRows": har_rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Auxiliary traces are ChatGPT auth, PayPal, or Stripe payment/browser artifacts. "
                "They contain no collector oIIoIooo|0 evidence and no proposal-worthy Outlook/HUMAN pre-accept transition."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "categoryCounts": categories, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
