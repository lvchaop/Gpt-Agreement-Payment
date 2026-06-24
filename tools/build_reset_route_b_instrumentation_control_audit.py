#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
MATRIX = RESET / "reset_route_b_resampling_matrix.json"
OUT = RESET / "reset_route_b_instrumentation_control_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def attempt_env(row: dict[str, Any]) -> dict[str, Any]:
    path = row.get("attemptSummary")
    doc = read_json(Path(path)) if path else {}
    return doc.get("envOverlay") or {}


def build() -> dict[str, Any]:
    matrix = read_json(MATRIX)
    rows = [row for row in matrix.get("executedRows") or [] if row.get("attemptSummary")]
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized = []
    for row in rows:
        env = attempt_env(row)
        patch_apply = str(env.get("OUTLOOK_HSPROTECT_JS_PATCH_APPLY") or "")
        sample_class = str(row.get("sampleClass") or "")
        expected_success = sample_class == "route_b_browser_success_webshare"
        actual_success = (row.get("classification") or {}).get("successLike") is True
        item = {
            "sampleClass": sample_class,
            "sessionId": row.get("sessionId"),
            "stage": (row.get("classification") or {}).get("stage"),
            "successLike": actual_success,
            "expectedSuccessLike": expected_success,
            "classOutcomeMatches": actual_success == expected_success,
            "patchApply": patch_apply,
            "attemptSummary": row.get("attemptSummary"),
            "jsInternalTrace": (row.get("artifacts") or {}).get("jsInternalTrace"),
            "runtimeTrace": (row.get("artifacts") or {}).get("runtimeTrace"),
        }
        normalized.append(item)
        buckets[f"patch_apply_{patch_apply}"].append(item)

    patch1 = buckets.get("patch_apply_1", [])
    patch0 = buckets.get("patch_apply_0", [])
    patch1_failures = [x for x in patch1 if x["successLike"] is False]
    patch1_successes = [x for x in patch1 if x["successLike"] is True]
    mismatch_rows = [x for x in normalized if x["classOutcomeMatches"] is False]

    checks = {
        "planExists": PLAN.exists(),
        "matrixExists": MATRIX.exists(),
        "executedAttemptCount": len(rows),
        "patchApply0AttemptCount": len(patch0),
        "patchApply1AttemptCount": len(patch1),
        "patchApply1SuccessCount": len(patch1_successes),
        "patchApply1FailureCount": len(patch1_failures),
        "classOutcomeMismatchCount": len(mismatch_rows),
        "hasControlledPatchApply1SuccessAndFailurePair": bool(patch1_successes) and bool(patch1_failures),
        "oldFailurePatchApply0Only": any(x["successLike"] is False for x in patch0) and not bool(patch1_failures),
        "valueContrastControlled": bool(patch1_successes) and bool(patch1_failures),
        "patchApplyCanBeTreatedAsPassiveObserver": False,
        "promotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Audit whether Route B value contrast is controlled for OUTLOOK_HSPROTECT_JS_PATCH_APPLY.",
        "inputs": {
            "routeBResamplingMatrix": str(MATRIX),
        },
        "checks": checks,
        "attempts": normalized,
        "buckets": dict(buckets),
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "The attempted patch_apply=1 failure-class browser sample ended successLike=true, so current Route B value contrast lacks a controlled "
                "patch_apply=1 success/failure pair. Existing success-only hsprotect events are therefore not promoted to pure-protocol transition evidence. "
                "The applied JS patch is an active browser-source intervention for evidence collection, not a passive protocol variable."
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
