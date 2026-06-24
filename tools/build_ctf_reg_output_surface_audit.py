#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/ctf_reg_output_surface_audit.json"
SCAN_DIRS = [ROOT / "CTF-reg/output"]
AUTHORITY_INPUTS = {
    "evidencePackageSurfaceAudit": ROOT / "output/protocol_reverse/hypothesis_reframe/evidence_package_surface_audit.json",
    "currentEvidenceEntranceTerminalLedger": ROOT / "output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json",
    "resetTerminal": ROOT / "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json",
}

TEXT_EXTS = {".txt", ".md", ".json", ".jsonl", ".html", ".js"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

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
    "outlook_forwarding": re.compile(r"forwarding|转发和 IMAP|登录并验证你的帐户以转发电子邮件"),
    "openai_platform": re.compile(r"platform\.openai\.com|openai", re.I),
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


def sqlite_table_counts(path: Path) -> dict[str, int]:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
                )
            ]
            return {name: conn.execute(f'select count(*) from "{name}"').fetchone()[0] for name in tables}
    except sqlite3.Error:
        return {}


def classify(path: Path, body: str) -> dict[str, Any]:
    rel = str(path.relative_to(ROOT))
    hits = {name: bool(rx.search(body)) for name, rx in PATTERNS.items()}
    category = "no_relevant_signal"
    reason = "No HUMAN/collector/risk/CreateAccount/cookie/Outlook forwarding signal."
    proposal_worthy = False

    if hits["collector_success0"]:
        if "outlook_browser" in rel or hits["browser_runtime"]:
            category = "browser_or_static_success_reference"
            reason = "Collector success token is in browser/static material, not fresh no-browser replay evidence."
        else:
            category = "unclassified_success0_signal"
            reason = "Collector success token outside known browser paths would require lineage before promotion."
    elif hits["risk_continue"] or hits["create_redirect"]:
        category = "downstream_or_app_success_context"
        reason = "Downstream success token is not collector pre-accept HUMAN success."
    elif hits["human_captcha"] or hits["collector_endpoint"] or hits["risk_verify"] or hits["create_account"] or hits["px_cookie"]:
        if "static_cache" in rel or path.suffix.lower() in {".js", ".html"}:
            category = "static_browser_cache_context"
            reason = "Static/browser cache context can support source mapping but is not a fresh no-browser success artifact."
        elif "phone_trace" in rel and hits["openai_platform"]:
            category = "unrelated_openai_phone_trace_context"
            reason = "Phone trace is OpenAI platform traffic, outside Outlook/HUMAN collector replay chain."
        else:
            category = "browser_material_context"
            reason = "Browser material needs a concrete pre-accept value lineage before proposal."
    elif hits["outlook_forwarding"]:
        category = "outlook_webmail_forwarding_context"
        reason = "Outlook webmail forwarding verification state is post-account/browser UI context, not collector pre-accept HUMAN acceptance."
    elif hits["openai_platform"]:
        category = "unrelated_openai_phone_trace_context"
        reason = "OpenAI platform trace is unrelated to Outlook signup HUMAN collector replay."

    return {
        "path": str(path),
        "relPath": rel,
        "size": path.stat().st_size,
        "category": category,
        "patternHits": hits,
        "proposalWorthy": proposal_worthy,
        "reason": reason,
    }


def main() -> int:
    authority = {name: read_json(path) for name, path in AUTHORITY_INPUTS.items()}
    text_file_count = 0
    image_file_count = 0
    sqlite_file_count = 0
    skipped_file_count = 0
    signal_rows: list[dict[str, Any]] = []
    sqlite_rows: list[dict[str, Any]] = []

    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            suffix = path.suffix.lower()
            if suffix in IMAGE_EXTS:
                image_file_count += 1
                continue
            if suffix in {".sqlite", ".db"}:
                sqlite_file_count += 1
                sqlite_rows.append({
                    "path": str(path),
                    "relPath": str(path.relative_to(ROOT)),
                    "size": path.stat().st_size,
                    "tableCounts": sqlite_table_counts(path),
                    "proposalWorthy": False,
                    "reason": "SQLite account inventory is local account state, not HUMAN collector pre-accept protocol evidence.",
                })
                continue
            if suffix not in TEXT_EXTS:
                skipped_file_count += 1
                continue
            text_file_count += 1
            row = classify(path, read_text_limited(path))
            if any(row["patternHits"].values()):
                signal_rows.append(row)

    categories: dict[str, int] = {}
    for row in signal_rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1

    success0_rows = [row for row in signal_rows if row["patternHits"]["collector_success0"]]
    proposal_rows = [row for row in signal_rows if row["proposalWorthy"]]
    c_pkg = checks(authority["evidencePackageSurfaceAudit"])
    c_current = checks(authority["currentEvidenceEntranceTerminalLedger"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scanDirectoryCount": len(SCAN_DIRS),
        "existingScanDirectoryCount": sum(1 for path in SCAN_DIRS if path.exists()),
        "textFileCount": text_file_count,
        "imageFileCount": image_file_count,
        "sqliteFileCount": sqlite_file_count,
        "skippedFileCount": skipped_file_count,
        "signalFileCount": len(signal_rows),
        "categoryCount": len(categories),
        "collectorSuccess0SignalFileCount": len(success0_rows),
        "proposalWorthyCtfRegSignalCount": len(proposal_rows),
        "evidencePackageProposalWorthySignalCount": c_pkg.get("proposalWorthyEvidencePackageSignalCount"),
        "currentEvidenceEntrancesClosed": c_current.get("allNextPointersClosedOrSuperseded") is True,
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit CTF-reg/output as a separate local evidence surface for fresh no-browser HUMAN success or a new proposal-worthy pre-accept transition.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "scanDirectories": [str(path) for path in SCAN_DIRS],
        "checks": checks_out,
        "categoryCounts": categories,
        "signalRows": signal_rows[:500],
        "collectorSuccess0Rows": success0_rows,
        "proposalWorthyRows": proposal_rows,
        "sqliteRows": sqlite_rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "CTF-reg/output contains Outlook webmail/browser/static-cache/account artifacts and unrelated OpenAI phone trace material, "
                "but no replayable fresh no-browser collector success and no proposal-worthy pre-accept transition."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "categoryCounts": categories, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
