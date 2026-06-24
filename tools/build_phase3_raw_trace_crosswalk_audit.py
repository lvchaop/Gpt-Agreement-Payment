#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
PLAN = ROOT / "docs/pure-protocol-human-authoritative-execution-plan.md"
RAW_AUDIT = HYP / "phase3_raw_evidence_entrance_audit.json"
OUT = HYP / "phase3_raw_trace_crosswalk_audit.json"
RUN_RE = re.compile(r"[a-z0-9]{12}_\d{10}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def protocol_reverse_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for path in sorted(PROTO.rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        keys = set(RUN_RE.findall(text))
        for key in keys:
            index.setdefault(key, []).append(str(path))
    return index


def main() -> int:
    raw = load_json(RAW_AUDIT)
    rows = raw.get("rows") or []
    unindexed = [row for row in rows if row.get("category") == "unindexed_browser_trace"]
    idx = protocol_reverse_index()
    crosswalk = []
    for row in unindexed:
        run_ids = row.get("runIds") or []
        refs = sorted({ref for run_id in run_ids for ref in idx.get(run_id, [])})
        crosswalk.append(
            {
                "path": row.get("path"),
                "tokens": row.get("tokens"),
                "runIds": run_ids,
                "referencedByProtocolReverse": bool(refs),
                "referenceCount": len(refs),
                "referenceSample": refs[:10],
                "proposalWorthy": False,
                "reason": (
                    "raw browser trace is already referenced by protocol_reverse audits"
                    if refs
                    else "raw browser trace is not referenced by protocol_reverse audits; classify before any proposal decision"
                ),
            }
        )

    unreferenced = [row for row in crosswalk if row["referencedByProtocolReverse"] is not True]
    token_counts = Counter(token for row in crosswalk for token in row.get("tokens") or [])
    checks = {
        "authoritativePlanExists": PLAN.exists(),
        "rawAuditExists": RAW_AUDIT.exists(),
        "unindexedBrowserTraceSignalCount": len(unindexed),
        "crosswalkRowCount": len(crosswalk),
        "referencedTraceCount": sum(1 for row in crosswalk if row["referencedByProtocolReverse"] is True),
        "unreferencedTraceCount": len(unreferenced),
        "unreferencedCollectorSuccessTokenCount": sum(
            1 for row in unreferenced if "collector_success_token" in (row.get("tokens") or [])
        ),
        "proposalWorthyRawTraceCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }
    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Crosswalk unindexed browser success-token traces against protocol_reverse audit references.",
        "inputs": {"rawEvidenceEntranceAudit": str(RAW_AUDIT)},
        "tokenCounts": dict(sorted(token_counts.items())),
        "rows": crosswalk,
        "unreferencedRows": unreferenced,
        "checks": checks,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedProposal": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Some raw browser traces with success tokens are not referenced by protocol_reverse audits; classify them before proposal intake."
                if unreferenced
                else "All raw browser traces with success tokens are referenced by existing protocol_reverse audits."
            ),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
