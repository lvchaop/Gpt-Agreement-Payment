#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
PROGRESSION = PROTO / "fresh_bundle_progression_probe/fresh_bundle_progression_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202033.json"
POW = PROTO / "pow_response/pow_response_fresh_bundle_progression_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202033.json"
WASM = PROTO / "wasm/compute_wasm_nq_once_fresh_after_px_retry_d2eae322_1781202033_with_ng.json"
ATTEMPT = PROTO / "fresh_px561_probe/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202104.json"
FIELD_DIFF = PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202104_full_field_diff.json"
ACTIVITY_DIFF = PROTO / "px561_compare/fresh_px561_probe_d2eae322-65b6-11f1-8553-62666cc2b93d_1781202104_full_activity_diff.json"
OUT = PROTO / "goal_audit/post_px_retry_fresh_pow_attempt_audit.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def solved_pow(doc: dict[str, Any]) -> str | None:
    for row in doc.get("results") or []:
        if row.get("matchesTarget") is True:
            return row.get("value")
    return None


def main() -> int:
    progression = read_json(PROGRESSION)
    pow_doc = read_json(POW)
    wasm = read_json(WASM)
    attempt = read_json(ATTEMPT)
    field_diff = read_json(FIELD_DIFF)
    activity_diff = read_json(ACTIVITY_DIFF)
    state = progression.get("finalState") or {}
    meta = (attempt.get("material") or {}).get("meta") or {}
    material_checks = (attempt.get("material") or {}).get("checks") or {}
    result = {
        "purpose": "After a rejected exact-activity PX561 response, advance non-PX seq3/seq4 to obtain a new POW, compute fresh Ws.NQ/Ng, then send a coherent fresh-tail PX561 attempt.",
        "inputs": {
            "progression": str(PROGRESSION.resolve()),
            "pow": str(POW.resolve()),
            "wasm": str(WASM.resolve()),
            "attempt": str(ATTEMPT.resolve()),
            "fieldDiff": str(FIELD_DIFF.resolve()),
            "activityDiff": str(ACTIVITY_DIFF.resolve()),
        },
        "progression": {
            "statuses": [(s.get("response") or {}).get("status") for s in progression.get("steps") or []],
            "handlers": [(s.get("decoded") or {}).get("handlers") for s in progression.get("steps") or []],
            "hasPow": [(s.get("decoded") or {}).get("hasPowResult") for s in progression.get("steps") or []],
            "finalState": {k: state.get(k) for k in ["jo", "ci", "cs", "px3", "pxde", "powChallenge"]},
        },
        "pow": {
            "powPartCount": pow_doc.get("powPartCount"),
            "solved": solved_pow(pow_doc),
        },
        "wasm": {
            "checks": wasm.get("checks"),
            "output": wasm.get("output"),
        },
        "attempt": {
            "status": (attempt.get("response") or {}).get("status"),
            "handlers": (attempt.get("decoded") or {}).get("handlers"),
            "hasSuccessHandler": (attempt.get("decoded") or {}).get("hasSuccessHandler"),
            "meta": {
                "seq": meta.get("seq"),
                "rsc": meta.get("rsc"),
                "pc": meta.get("pc"),
                "newPxTail": meta.get("newPxTail"),
            },
            "materialChecks": material_checks,
            "fieldDiff": {
                "diffCountVsS00Success": field_diff.get("diffCountVsS00Success"),
                "diffsByClass": field_diff.get("diffsByClass"),
                "checks": field_diff.get("checks"),
            },
            "activityDiff": {
                "checks": activity_diff.get("checks"),
                "nonPx561DiffSummary": activity_diff.get("nonPx561DiffSummary"),
            },
        },
        "checks": {
            "progressionHttp200": all((s.get("response") or {}).get("status") == 200 for s in progression.get("steps") or []),
            "progressionReturnedNewPow": any((s.get("decoded") or {}).get("hasPowResult") is True for s in progression.get("steps") or []),
            "powSolved": bool(solved_pow(pow_doc)),
            "wasmNqComputed": (wasm.get("checks") or {}).get("nqValueNonEmpty") is True,
            "wasmNgComputed": (wasm.get("checks") or {}).get("ngValueNonEmpty") is True,
            "attemptUsesFreshOsk": material_checks.get("hasFreshOsk") is True,
            "attemptUsesFreshTbr9": material_checks.get("hasFreshTbr9") is True,
            "attemptUsesOfflineNg": material_checks.get("hasOfflineNgAeax") is True,
            "attemptRejected": (attempt.get("decoded") or {}).get("hasSuccessHandler") is False,
        },
        "conclusion": (
            "From the rejected PX561 state, non-PX seq3/seq4 can still advance collector state and return a new POW. "
            "A follow-up PX561 using that new solved POW, fresh Ws.NQ TBR9, and offline Ng still returns oIIoIooo|-1. "
            "Thus a post-rejection fresh POW/TBR9/Ng cycle is not sufficient with the current activity/template material."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": result["checks"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
