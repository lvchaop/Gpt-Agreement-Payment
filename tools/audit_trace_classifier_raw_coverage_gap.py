#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
TRACE_DIR = PROTO / "trace_classification_v2"
PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
CLASSIFIER_SCRIPT = ROOT / "tools/human_trace_classifier_v2.py"
CLASSIFIER_SUMMARY = TRACE_DIR / "human_trace_classifier_v2_summary.json"
RAW_AUDIT = HYP / "phase3_raw_evidence_entrance_audit.json"
CROSSWALK = HYP / "phase3_raw_trace_crosswalk_audit.json"
OUT = HYP / "trace_classifier_raw_coverage_gap_audit.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def main() -> int:
    summary = load_json(CLASSIFIER_SUMMARY)
    raw = load_json(RAW_AUDIT)
    crosswalk = load_json(CROSSWALK)
    classifier_runs = {
        row.get("run")
        for row in summary.get("runs") or []
        if isinstance(row, dict) and isinstance(row.get("run"), str)
    }
    raw_rows = raw.get("rows") or []
    crosswalk_rows = crosswalk.get("rows") or []
    raw_browser_success_runs = {
        run_id
        for row in raw_rows
        if row.get("category") in {"indexed_browser_runtime_trace", "unindexed_browser_trace"}
        for run_id in row.get("runIds") or []
    }
    crosswalk_unclassified = [
        row for row in crosswalk_rows
        if not any(run_id in classifier_runs for run_id in (row.get("runIds") or []))
    ]
    referenced_unclassified = [row for row in crosswalk_unclassified if row.get("referencedByProtocolReverse") is True]
    checks = {
        "authoritativePlanExists": PLAN.exists(),
        "classifierScriptExists": CLASSIFIER_SCRIPT.exists(),
        "classifierSummaryExists": CLASSIFIER_SUMMARY.exists(),
        "rawAuditExists": RAW_AUDIT.exists(),
        "crosswalkExists": CROSSWALK.exists(),
        "classifierRunCount": len(classifier_runs),
        "rawBrowserSuccessRunCount": len(raw_browser_success_runs),
        "rawBrowserSuccessRunsNotInClassifierCount": len(raw_browser_success_runs - classifier_runs),
        "crosswalkUnclassifiedRowCount": len(crosswalk_unclassified),
        "referencedButUnclassifiedRawTraceCount": len(referenced_unclassified),
        "unreferencedRawTraceCount": (crosswalk.get("checks") or {}).get("unreferencedTraceCount"),
        "safeToAutoAppendToClassifier": False,
        "proposalWorthyCoverageGapCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Audit classifier v2 coverage of raw browser success-token traces without changing classifier semantics.",
        "inputs": {
            "classifierScript": str(CLASSIFIER_SCRIPT),
            "classifierSummary": str(CLASSIFIER_SUMMARY),
            "rawEvidenceEntranceAudit": str(RAW_AUDIT),
            "rawTraceCrosswalkAudit": str(CROSSWALK),
        },
        "classifierRuns": sorted(classifier_runs),
        "rawBrowserSuccessRuns": sorted(raw_browser_success_runs),
        "rawBrowserSuccessRunsNotInClassifier": sorted(raw_browser_success_runs - classifier_runs),
        "referencedButUnclassifiedRawTraceRows": referenced_unclassified,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedProposal": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Classifier v2 intentionally indexes trace_classification_*.json artifacts; raw browser success-token traces are referenced by protocol_reverse audits but are not safe to append without generating equivalent trace_classification artifacts."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
