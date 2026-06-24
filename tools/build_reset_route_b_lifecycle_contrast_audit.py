#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESET = ROOT / "output/protocol_reverse/reset_plan"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
MATRIX = RESET / "reset_route_b_resampling_matrix.json"
TERMINAL = RESET / "reset_terminal_boundary_audit.json"
OUT = RESET / "reset_route_b_lifecycle_contrast_audit.json"

ROUTE_B_HOOK_KINDS = [
    "webkit.messageHandlers.pxMobileData.wrap",
    "webkit.messageHandlers.pxMobileData.postMessage",
    "OfflineAudioContext.wrap",
    "OfflineAudioContext.new",
    "OfflineAudioContext.startRendering",
    "OfflineAudioContext.startRendering.resolved",
    "serviceWorker.snapshot",
    "serviceWorker.register",
    "caches.wrap",
    "caches.open",
    "caches.match",
]


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def real_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in matrix.get("executedRows") or []:
        if row.get("attemptSummary") and row.get("routeBHookScan"):
            rows.append(row)
    return rows


def hook_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label, pred in {
        "success": lambda r: (r.get("classification") or {}).get("successLike") is True,
        "failure": lambda r: (r.get("classification") or {}).get("successLike") is not True,
    }.items():
        subset = [r for r in rows if pred(r)]
        count = Counter()
        observed_samples: dict[str, list[str]] = defaultdict(list)
        for row in subset:
            session = str(row.get("sessionId") or "")
            scan = row.get("routeBHookScan") or {}
            for kind, n in (scan.get("counts") or {}).items():
                if n:
                    count[kind] += n
                    observed_samples[kind].append(session)
        out[label] = {
            "sampleCount": len(subset),
            "counts": dict(count),
            "observedKinds": sorted([k for k, v in count.items() if v > 0]),
            "observedSamples": dict(observed_samples),
        }
    return out


def build() -> dict[str, Any]:
    matrix = read_json(MATRIX)
    terminal = read_json(TERMINAL)
    rows = real_rows(matrix)
    counts = hook_counts(rows)

    success_observed = set(counts["success"]["observedKinds"])
    failure_observed = set(counts["failure"]["observedKinds"])
    success_only = sorted(success_observed - failure_observed)
    failure_only = sorted(failure_observed - success_observed)
    both = sorted(success_observed & failure_observed)
    neither = sorted(set(ROUTE_B_HOOK_KINDS) - success_observed - failure_observed)

    promoted = []
    for kind in success_only:
        promoted.append(
            {
                "kind": kind,
                "promoteToSingleTransitionCandidate": False,
                "reason": "Success-only Route B hook observation is not enough: no value lineage into pre-accept request/cookie/risk and no pure-protocol constructible transition is proven.",
            }
        )

    checks = {
        "planExists": PLAN.exists(),
        "matrixExists": MATRIX.exists(),
        "terminalExists": TERMINAL.exists(),
        "matrixReadyForLifecycleContrastAudit": (matrix.get("checks") or {}).get("readyForLifecycleContrastAudit") is True,
        "realAttemptCount": len(rows),
        "successSampleCount": counts["success"]["sampleCount"],
        "failureSampleCount": counts["failure"]["sampleCount"],
        "routeBHookKindCount": len(ROUTE_B_HOOK_KINDS),
        "successObservedKindCount": len(success_observed),
        "failureObservedKindCount": len(failure_observed),
        "bothObservedKindCount": len(both),
        "successOnlyHookKindCount": len(success_only),
        "failureOnlyHookKindCount": len(failure_only),
        "neitherObservedHookKindCount": len(neither),
        "promotedSingleTransitionCandidateCount": 0,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Contrast Route B newly instrumented lifecycle/fingerprint hooks between browser success and failure samples.",
        "inputs": {
            "routeBResamplingMatrix": str(MATRIX),
            "terminalBoundaryAudit": str(TERMINAL),
        },
        "checks": checks,
        "hookCounts": counts,
        "contrast": {
            "successOnly": success_only,
            "failureOnly": failure_only,
            "both": both,
            "neither": neither,
        },
        "promotedCandidates": promoted,
        "realRows": [
            {
                "sampleClass": row.get("sampleClass"),
                "sessionId": row.get("sessionId"),
                "successLike": (row.get("classification") or {}).get("successLike"),
                "stage": (row.get("classification") or {}).get("stage"),
                "attemptSummary": row.get("attemptSummary"),
                "observedHooks": (row.get("routeBHookScan") or {}).get("observed"),
                "missingHooks": (row.get("routeBHookScan") or {}).get("missing"),
            }
            for row in rows
        ],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Route B hooks produced browser evidence, but observed hooks are not promoted to a pure-protocol Phase 5 input. "
                "A hook must expose a pre-accept value lineage into request/cookie/risk and be constructible without browser before Phase 5 is allowed."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "contrast": doc["contrast"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
