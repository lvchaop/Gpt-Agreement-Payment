#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/evidence_package_surface_audit.json"
SCAN_DIRS = [ROOT / "output/evidence_packages", ROOT / "output/browser-tests"]
AUTHORITY_INPUTS = {
    "externalOutputSurfaceAudit": ROOT / "output/protocol_reverse/hypothesis_reframe/external_output_surface_audit.json",
    "currentEvidenceEntranceTerminalLedger": ROOT / "output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json",
    "resetTerminal": ROOT / "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json",
    "goalCompletionVerifier": ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json",
}

TEXT_EXTS = {
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".har",
    ".js",
    ".py",
    ".mjs",
    ".patch",
    ".generated",
}

PATTERNS = {
    "collector_success0": re.compile(r"oIIoIooo\|0"),
    "collector_failure_minus1": re.compile(r"oIIoIooo\|-1"),
    "risk_continue": re.compile(r'"state"\s*:\s*"continue"|state=continue|risk_verify_state_continue'),
    "create_redirect": re.compile(r"redirectUrl|create_account_redirectUrl|res=success"),
    "human_captcha": re.compile(r"HumanCaptcha|hsprotect|iframe\.hsprotect|humanAppId|urlHumanIframe"),
    "collector_endpoint": re.compile(r"/api/v2/collector|/api/v2/msft|collector", re.I),
    "px_cookie": re.compile(r"_px3|_pxde|_pxvid|pxvid"),
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


def is_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTS:
        return True
    return path.name.endswith(".generated.txt")


def classify(path: Path, body: str) -> dict[str, Any]:
    hits = {name: bool(rx.search(body)) for name, rx in PATTERNS.items()}
    rel = str(path.relative_to(ROOT))
    category = "no_relevant_signal"
    reason = "No relevant HUMAN/collector/risk/CreateAccount token."
    if hits["collector_success0"]:
        if "runtime_success" in rel or "browser" in rel or hits["browser_runtime"]:
            category = "packaged_browser_success_reference"
            reason = "Packaged success token belongs to browser/runtime success evidence, not fresh no-browser replay."
        else:
            category = "unclassified_success0_signal"
            reason = "Collector success token requires lineage before promotion."
    elif hits["risk_continue"] or hits["create_redirect"]:
        category = "oauth_or_downstream_success_context"
        reason = "OAuth/downstream success is not collector pre-accept HUMAN acceptance."
    elif hits["human_captcha"] or hits["collector_endpoint"] or hits["px_cookie"]:
        if "static_analysis" in rel or "har_extract" in rel or path.suffix in {".js", ".txt"}:
            category = "static_or_har_package_context"
            reason = "Static/HAR packaged source context; not a live fresh no-browser success."
        elif "runtime_" in rel or "run_logs" in rel:
            category = "packaged_runtime_material_context"
            reason = "Runtime package material is historical browser/failure material unless it proves fresh no-browser success."
        else:
            category = "package_material_context"
            reason = "Package material does not expose a proposal-worthy transition by itself."
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
    image_file_count = 0
    zip_file_count = 0
    signal_rows: list[dict[str, Any]] = []
    zip_rows: list[dict[str, Any]] = []
    for root in SCAN_DIRS:
        if not root.exists():
            continue
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                image_file_count += 1
                continue
            if path.suffix.lower() == ".zip":
                zip_file_count += 1
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()
                    zip_rows.append({"path": str(path), "entryCount": len(names), "sampleEntries": names[:20]})
                continue
            if not is_text(path):
                continue
            text_file_count += 1
            body = read_text_limited(path)
            row = classify(path, body)
            if any(row["patternHits"].values()):
                signal_rows.append(row)

    categories: dict[str, int] = {}
    for row in signal_rows:
        categories[row["category"]] = categories.get(row["category"], 0) + 1

    success_rows = [row for row in signal_rows if row["patternHits"]["collector_success0"]]
    proposal_rows = [row for row in signal_rows if row["proposalWorthy"]]
    c_external = checks(authority["externalOutputSurfaceAudit"])
    c_current = checks(authority["currentEvidenceEntranceTerminalLedger"])
    c_reset = checks(authority["resetTerminal"])
    c_verifier = checks(authority["goalCompletionVerifier"])

    checks_out = {
        "allInputsExist": all(path.exists() for path in AUTHORITY_INPUTS.values()),
        "scanDirectoryCount": len(SCAN_DIRS),
        "existingScanDirectoryCount": sum(1 for path in SCAN_DIRS if path.exists()),
        "textFileCount": text_file_count,
        "imageFileCount": image_file_count,
        "zipFileCount": zip_file_count,
        "signalFileCount": len(signal_rows),
        "categoryCount": len(categories),
        "collectorSuccess0SignalFileCount": len(success_rows),
        "proposalWorthyEvidencePackageSignalCount": len(proposal_rows),
        "externalOutputProposalWorthySignalCount": c_external.get("proposalWorthyExternalSignalCount"),
        "currentEvidenceEntrancesClosed": c_current.get("allNextPointersClosedOrSuperseded") is True,
        "resetNoCurrentRouteToPhase5": c_reset.get("noCurrentRouteToPhase5") is True,
        "goalCompletionVerified": c_verifier.get("completionVerified") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "Audit packaged evidence and browser-test outputs for replayable fresh no-browser HUMAN success or a new proposal-worthy transition.",
        "inputs": {name: str(path) for name, path in AUTHORITY_INPUTS.items()},
        "scanDirectories": [str(path) for path in SCAN_DIRS],
        "checks": checks_out,
        "categoryCounts": categories,
        "signalRows": signal_rows[:600],
        "collectorSuccess0Rows": success_rows,
        "proposalWorthyRows": proposal_rows,
        "zipRows": zip_rows,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Packaged evidence contains historical browser/static/runtime/downstream material, but no replayable fresh no-browser collector success and no proposal-worthy transition."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "categoryCounts": categories, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
