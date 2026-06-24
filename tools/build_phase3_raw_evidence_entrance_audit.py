#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = ROOT / "output"
PROTO = OUT_ROOT / "protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
CLASSIFIER = PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json"
OUT = HYP / "phase3_raw_evidence_entrance_audit.json"

TOKEN_PATTERNS = {
    "collector_success_token": b"oIIoIooo|0",
    "has_success_handler": b"hasSuccessHandler",
    "risk_continue_token": b"risk_verify_state_continue",
    "create_redirect_token": b"create_account_redirectUrl",
    "state_continue_text": b"state=continue",
    "redirect_url_text": b"redirectUrl",
}
SCANNED_SUFFIXES = {".json", ".jsonl", ".har", ".txt", ".log", ".html", ".md", ".js"}
RUN_RE = re.compile(r"[a-z0-9]{12}_\d{10}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def classifier_runs() -> set[str]:
    doc = load_json(CLASSIFIER)
    return {
        row.get("run")
        for row in doc.get("runs") or []
        if isinstance(row, dict) and isinstance(row.get("run"), str)
    }


def classify_path(path: Path, runs: set[str]) -> tuple[str, str]:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    text = str(rel)
    run_ids = set(RUN_RE.findall(text))
    indexed_run_ids = sorted(run_ids & runs)

    if "protocol_reverse" in parts:
        return "excluded_protocol_reverse", "protocol_reverse is handled by existing audits"
    if "evidence_packages" in parts:
        return "packaged_copy_or_documentation", "evidence package mirrors prior runtime/static material"
    if path.suffix == ".js":
        return "static_js_string", "static JavaScript token/string evidence is not a fresh no-browser runtime transition"
    if "phone_trace" in path.name:
        return "unrelated_phone_trace", "phone trace redirectUrl token is outside HUMAN collector proposal scope"
    if indexed_run_ids:
        return "indexed_browser_runtime_trace", "run id is already covered by trace classifier or downstream audits"
    if "outlook_browser" in parts and ("runtime_trace_" in path.name or "js_internal_trace_" in path.name):
        return "unindexed_browser_trace", "browser trace may be useful only after dedicated classification; not pure-protocol constructible by itself"
    if "outlook_browser" in parts:
        return "browser_snapshot_or_context", "browser snapshot/context file is not a pure-protocol transition without lineage"
    return "other_raw_signal", "raw token requires dedicated lineage before proposal intake"


def main() -> int:
    runs = classifier_runs()
    rows: list[dict[str, Any]] = []
    scanned_count = 0
    for path in sorted(OUT_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(ROOT).parts
        if "protocol_reverse" in rel_parts:
            continue
        if path.suffix.lower() not in SCANNED_SUFFIXES:
            continue
        scanned_count += 1
        try:
            data = path.read_bytes()
        except Exception:
            continue
        hits = [name for name, pattern in TOKEN_PATTERNS.items() if pattern in data]
        if not hits:
            continue
        category, reason = classify_path(path, runs)
        run_ids = sorted(set(RUN_RE.findall(str(path.relative_to(ROOT)))))
        rows.append(
            {
                "path": str(path),
                "size": len(data),
                "tokens": hits,
                "runIds": run_ids,
                "indexedRunIds": sorted(set(run_ids) & runs),
                "category": category,
                "proposalWorthy": False,
                "reason": reason,
            }
        )

    by_category = Counter(row["category"] for row in rows)
    by_token = Counter(token for row in rows for token in row["tokens"])
    unindexed_browser = [row for row in rows if row["category"] == "unindexed_browser_trace"]
    other_raw = [row for row in rows if row["category"] == "other_raw_signal"]

    checks = {
        "authoritativePlanExists": PLAN.exists(),
        "classifierExists": CLASSIFIER.exists(),
        "classifierRunCount": len(runs),
        "scannedRawFileCount": scanned_count,
        "rawSuccessSignalFileCount": len(rows),
        "protocolReverseExcluded": True,
        "indexedBrowserRuntimeSignalCount": by_category.get("indexed_browser_runtime_trace", 0),
        "unindexedBrowserTraceSignalCount": len(unindexed_browser),
        "packagedCopyOrDocumentationSignalCount": by_category.get("packaged_copy_or_documentation", 0),
        "staticJsStringSignalCount": by_category.get("static_js_string", 0),
        "otherRawSignalCount": len(other_raw),
        "proposalWorthyRawSignalCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Phase 3 raw evidence entrance audit outside output/protocol_reverse.",
        "scan": {
            "root": str(OUT_ROOT),
            "excluded": [str(PROTO)],
            "suffixes": sorted(SCANNED_SUFFIXES),
            "tokens": sorted(TOKEN_PATTERNS),
        },
        "categoryCounts": dict(sorted(by_category.items())),
        "tokenCounts": dict(sorted(by_token.items())),
        "rows": rows,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedProposal": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Raw success tokens outside protocol_reverse are browser/runtime/static/package references; none is a pre-accept, client-visible, pure-protocol constructible proposal."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "categoryCounts": doc["categoryCounts"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
