#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT = PROTO / "goal_audit"

FILES = {
    "progression": PROTO / "fresh_bundle_progression_probe/fresh_bundle_progression_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200115.json",
    "pow": PROTO / "pow_response/pow_response_fresh_bundle_progression_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200115.json",
    "wasm": PROTO / "wasm/compute_wasm_nq_once_fresh_progression_d2eae322_1781200115_with_ng.json",
    "offlineNgProbe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200219.json",
    "offlineNgFullDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200219_full_field_diff.json",
    "templateAeaxProbe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200470.json",
    "templateAeaxFullDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200470_full_field_diff.json",
    "templateStackProbe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200661.json",
    "templateStackFullDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200661_full_field_diff.json",
    "templateTailProbe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200729.json",
    "templateTailFullDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200729_full_field_diff.json",
    "exactInnerProbe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200887.json",
    "exactInnerFullDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200887_full_field_diff.json",
    "exactInnerFullActivityDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781200887_full_activity_diff.json",
    "exactWholeActivitiesProbe": PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201361.json",
    "exactWholeActivitiesDiff": PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781201361_full_activity_diff.json",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def file_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "exists": path.exists()}


def probe_summary(path: Path) -> dict[str, Any]:
    doc = load(path)
    return {
        "file": str(path.resolve()),
        "sent": doc.get("sent"),
        "status": (doc.get("response") or {}).get("status"),
        "handlers": (doc.get("decoded") or {}).get("handlers"),
        "hasSuccessHandler": (doc.get("decoded") or {}).get("hasSuccessHandler"),
        "hasPx3": (doc.get("decoded") or {}).get("hasPx3"),
        "hasPxde": (doc.get("decoded") or {}).get("hasPxde"),
        "meta": (doc.get("material") or {}).get("meta"),
    }


def main() -> int:
    progression = load(FILES["progression"])
    pow_doc = load(FILES["pow"])
    wasm = load(FILES["wasm"])
    offline_diff = load(FILES["offlineNgFullDiff"])
    template_diff = load(FILES["templateAeaxFullDiff"])
    stack_diff = load(FILES["templateStackFullDiff"])
    tail_diff = load(FILES["templateTailFullDiff"])
    exact_inner_diff = load(FILES["exactInnerFullDiff"])
    exact_activity_diff = load(FILES["exactInnerFullActivityDiff"])
    exact_whole_activity_diff = load(FILES["exactWholeActivitiesDiff"])
    result = {
        "purpose": "Evidence audit for convergence after no-browser state progression and line922 PX561 success-template probes.",
        "evidenceFiles": {name: file_ref(path) for name, path in FILES.items()},
        "progression": {
            "sent": progression.get("sent"),
            "statuses": [(s.get("response") or {}).get("status") for s in progression.get("steps") or []],
            "handlers": [(s.get("decoded") or {}).get("handlers") for s in progression.get("steps") or []],
            "hasPow": [(s.get("decoded") or {}).get("hasPowResult") for s in progression.get("steps") or []],
            "finalState": {
                key: (progression.get("finalState") or {}).get(key)
                for key in ["uuid", "jo", "ci", "cs", "powChallenge"]
            },
        },
        "pow": {
            "powPartCount": pow_doc.get("powPartCount"),
            "solved": [
                {
                    "value": row.get("value"),
                    "solveElapsedMs": row.get("solveElapsedMs"),
                    "matchesTarget": row.get("matchesTarget"),
                }
                for row in pow_doc.get("results") or []
            ],
        },
        "wasm": {
            "checks": wasm.get("checks"),
            "ngLen": ((wasm.get("output") or {}).get("ngLen")),
            "nqLen": ((wasm.get("output") or {}).get("nqLen")),
        },
        "probes": {
            "offlineNg": probe_summary(FILES["offlineNgProbe"]),
            "templateAeax": probe_summary(FILES["templateAeaxProbe"]),
            "templateStack": probe_summary(FILES["templateStackProbe"]),
            "templateTail": probe_summary(FILES["templateTailProbe"]),
            "exactInner": probe_summary(FILES["exactInnerProbe"]),
            "exactWholeActivities": probe_summary(FILES["exactWholeActivitiesProbe"]),
        },
        "fieldDiffs": {
            "offlineNg": {
                "diffCountVsS00Success": offline_diff.get("diffCountVsS00Success"),
                "diffsByClass": offline_diff.get("diffsByClass"),
                "checks": offline_diff.get("checks"),
            },
            "templateAeax": {
                "diffCountVsS00Success": template_diff.get("diffCountVsS00Success"),
                "diffsByClass": template_diff.get("diffsByClass"),
                "checks": template_diff.get("checks"),
            },
            "templateStack": {
                "diffCountVsS00Success": stack_diff.get("diffCountVsS00Success"),
                "diffsByClass": stack_diff.get("diffsByClass"),
                "checks": stack_diff.get("checks"),
            },
            "templateTail": {
                "diffCountVsS00Success": tail_diff.get("diffCountVsS00Success"),
                "diffsByClass": tail_diff.get("diffsByClass"),
                "checks": tail_diff.get("checks"),
            },
            "exactInner": {
                "diffCountVsS00Success": exact_inner_diff.get("diffCountVsS00Success"),
                "diffsByClass": exact_inner_diff.get("diffsByClass"),
                "checks": exact_inner_diff.get("checks"),
            },
        },
        "activityDiffs": {
            "exactInner": {
                "activityCounts": exact_activity_diff.get("activityCounts"),
                "activityTypes": exact_activity_diff.get("activityTypes"),
                "checks": exact_activity_diff.get("checks"),
                "nonPx561DiffSummary": exact_activity_diff.get("nonPx561DiffSummary"),
            },
            "exactWholeActivities": {
                "activityCounts": exact_whole_activity_diff.get("activityCounts"),
                "activityTypes": exact_whole_activity_diff.get("activityTypes"),
                "checks": exact_whole_activity_diff.get("checks"),
                "nonPx561DiffSummary": exact_whole_activity_diff.get("nonPx561DiffSummary"),
            }
        },
        "checks": {
            "progressionAllHttp200": all((s.get("response") or {}).get("status") == 200 for s in progression.get("steps") or []),
            "progressionReturnedNewPow": any((s.get("decoded") or {}).get("hasPowResult") is True for s in progression.get("steps") or []),
            "powSolved": pow_doc.get("powPartCount") == 1 and any(row.get("matchesTarget") is True for row in pow_doc.get("results") or []),
            "wasmNqComputed": (wasm.get("checks") or {}).get("nqValueNonEmpty") is True,
            "offlineNgRejected": (load(FILES["offlineNgProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False,
            "templateAeaxRejected": (load(FILES["templateAeaxProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False,
            "templateStackRejected": (load(FILES["templateStackProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False,
            "templateTailRejected": (load(FILES["templateTailProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False,
            "exactInnerRejected": (load(FILES["exactInnerProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False,
            "exactWholeActivitiesRejected": (load(FILES["exactWholeActivitiesProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False,
            "templateAeaxDiffsReducedToStackUuidOskTbr9": template_diff.get("diffsByClass") == {
                "other": ["W0shQR0nJHc="],
                "pow_wasm_tail": ["TBR9Ugl7emA=", "OSkIb39DDA=="],
                "session_or_cookie": ["FUFvS1Mga38="],
            },
            "templateStackDiffsReducedToUuidOskTbr9": stack_diff.get("diffsByClass") == {
                "pow_wasm_tail": ["TBR9Ugl7emA=", "OSkIb39DDA=="],
                "session_or_cookie": ["FUFvS1Mga38="],
            },
            "templateTailDiffsReducedToUuidOnly": tail_diff.get("diffsByClass") == {
                "session_or_cookie": ["FUFvS1Mga38="],
            },
            "exactInnerDiffsZero": exact_inner_diff.get("diffCountVsS00Success") == 0,
            "exactInnerPx561EqualButWholeActivitiesDiffer": (
                (exact_activity_diff.get("checks") or {}).get("px561ActivityEqual") is True
                and (exact_activity_diff.get("checks") or {}).get("wholeActivitiesEqual") is False
            ),
            "exactInnerNonPx561ActivitiesDiffer": (exact_activity_diff.get("checks") or {}).get("nonPx561ActivitiesAllEqual") is False,
            "exactWholeActivitiesEqualButRejected": (
                (exact_whole_activity_diff.get("checks") or {}).get("wholeActivitiesEqual") is True
                and (load(FILES["exactWholeActivitiesProbe"]).get("decoded") or {}).get("hasSuccessHandler") is False
            ),
        },
        "conclusion": (
            "No-browser progression reaches a new POW/Jo/ci state and can produce a line922 key-order PX561 body. "
            "With offline Ng AEAx, the fresh rejected body differs from s00 accepted only by stack/uuid and POW/WASM tail. "
            "With template AEAx, the rejected body differs from s00 accepted only by stack/uuid plus the necessarily fresh OSk/TBR9. "
            "With template stack and template tail controls, the rejected body can be reduced to a single inner PX561 difference, FUFvS1Mga38= uuid, while the outer collector session remains fresh. "
            "With template inner UUID too, the inner PX561 activity is byte-level field-equivalent to s00 accepted line922, yet the fresh outer collector session still returns oIIoIooo|-1. "
            "A full-activity diff then proves this exact-inner control does not make the whole decoded activity array equal: non-PX561 activities at indexes 0, 1, and 3 still differ. "
            "A stricter control that keeps all decoded activities equal to s00 accepted line922 still returns oIIoIooo|-1 when sent through the fresh outer collector session. "
            "Therefore standalone decoded activity-array equivalence is not sufficient; the remaining evidence gap is now outside the decoded activities and points to outer form/session/cookie/history state, request context, or prior server-side state."
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    out_json = OUT / "progression_px561_convergence_audit.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(out_json), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
