#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUT_DIR = PROTO / "hypothesis_reframe"
OUT = OUT_DIR / "selected_contrast_pair.json"

SUCCESS_ID = "s00ld1lglrw0_1781191381"
FRESH_ATTEMPT = PROTO / "first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781281000000_1781279930.json"
TEMPLATE_FINAL_AUDIT = PROTO / "goal_audit/forced_overlap_template_final_control_audit.json"
BOUNDARY_AUDIT = PROTO / "goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_entry(path: Path, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "path": str(path),
        "exists": path.exists(),
        "sizeBytes": path.stat().st_size if path.exists() else None,
    }


def step_summary(attempt: dict[str, Any], name: str) -> dict[str, Any]:
    step = ((attempt.get("steps") or {}).get(name) or {}).get("summary") or {}
    return json.loads(json.dumps(step))


def main() -> int:
    attempt = read_json(FRESH_ATTEMPT)
    template_audit = read_json(TEMPLATE_FINAL_AUDIT)
    boundary = read_json(BOUNDARY_AUDIT)
    final_combo = step_summary(attempt, "finalSeq5Seq6Combo")
    final_combo_path = Path(str(final_combo.get("json") or ""))
    final_combo_doc = read_json(final_combo_path) if final_combo_path.exists() else {}
    seq5 = ((final_combo_doc.get("results") or {}).get("seq5") or {})
    seq6 = ((final_combo_doc.get("results") or {}).get("seq6") or {})

    success_runtime = REPO / f"output/outlook_browser/runtime_trace_{SUCCESS_ID}.jsonl"
    success_js = REPO / f"output/outlook_browser/js_internal_trace_{SUCCESS_ID}.jsonl"
    success_cookie_json = PROTO / f"cookie_timeline/cookie_timeline_{SUCCESS_ID}.json"
    success_cookie_md = PROTO / f"cookie_timeline/cookie_timeline_{SUCCESS_ID}.md"
    success_bundle_decode_json = PROTO / f"bundle_payload_decode/bundle_payload_decode_{SUCCESS_ID}.json"
    success_bundle_decode_md = PROTO / f"bundle_payload_decode/bundle_payload_decode_{SUCCESS_ID}.md"

    fresh_paths = {
        "attempt": FRESH_ATTEMPT,
        "bootstrap": Path(step_summary(attempt, "bootstrap").get("json") or ""),
        "second": Path(step_summary(attempt, "second").get("json") or ""),
        "sequence": Path(step_summary(attempt, "sequence").get("json") or ""),
        "bundle": Path(step_summary(attempt, "bundle").get("json") or ""),
        "firstPow": Path(step_summary(attempt, "firstPow").get("jsonPath") or ""),
        "firstNq": Path(step_summary(attempt, "firstNq").get("out") or ""),
        "firstFailureOverlap": Path(step_summary(attempt, "firstFailureOverlap").get("json") or ""),
        "seq4AfterOverlap": Path(step_summary(attempt, "seq4AfterOverlap").get("json") or ""),
        "progressionPow": Path(step_summary(attempt, "progressionPow").get("jsonPath") or ""),
        "finalNq": Path(step_summary(attempt, "finalNq").get("out") or ""),
        "finalSeq5Seq6Combo": final_combo_path,
        "templateFinalAudit": TEMPLATE_FINAL_AUDIT,
        "boundaryAudit": BOUNDARY_AUDIT,
    }

    criteria = {
        "bootstrapCompleted": (attempt.get("checks") or {}).get("bootstrap200") is True,
        "secondCompleted": (attempt.get("checks") or {}).get("second200") is True,
        "sequenceCompleted": (attempt.get("checks") or {}).get("sequence200") is True,
        "bundlePowCompleted": (attempt.get("checks") or {}).get("bundle200Pow") is True,
        "firstFailureOverlapCompleted": (attempt.get("checks") or {}).get("overlapSeq3ResponseFirst") is True
        and (attempt.get("checks") or {}).get("overlapSeq2Rejected") is True,
        "seq4AfterOverlapPowCompleted": (attempt.get("checks") or {}).get("seq4AfterOverlap200Pow") is True,
        "finalSeq5Seq6Sent": (final_combo.get("checks") or {}).get("seq5Http200") is True
        and (final_combo.get("checks") or {}).get("seq6Http200") is True,
        "collectorResponseDecoded": bool(final_combo.get("handlers")),
        "finalDecodedActivitiesEqualS00": (template_audit.get("checks") or {}).get("finalDecodedActivitiesEqualS00") is True,
        "finalRejected": (template_audit.get("checks") or {}).get("finalStillRejected") is True,
        "cookieJarReconstructableFromHandlers": bool(step_summary(attempt, "seq4AfterOverlap").get("finalState")),
    }

    doc = {
        "purpose": "Phase 1 contrast pair for hypothesis-driven HUMAN pure-protocol reframe.",
        "plan": str((REPO / "docs/pure-protocol-human-hypothesis-plan.md")),
        "selectionCriteria": criteria,
        "successSample": {
            "id": SUCCESS_ID,
            "reason": "Known browser success sample used throughout previous accepted-window audits; line933 is the accepted seq5 collector request and line937 is paired seq6.",
            "tracePaths": [
                file_entry(success_runtime, "runtime_trace"),
                file_entry(success_js, "js_internal_trace"),
            ],
            "decodedResponsePaths": [
                file_entry(success_bundle_decode_json, "bundle_payload_decode_json"),
                file_entry(success_bundle_decode_md, "bundle_payload_decode_md"),
            ],
            "cookieTimelinePaths": [
                file_entry(success_cookie_json, "cookie_timeline_json"),
                file_entry(success_cookie_md, "cookie_timeline_md"),
            ],
            "acceptedWindow": {
                "seq5RuntimeLine": 933,
                "seq5JsPayloadLine": 922,
                "seq6RuntimeLine": 937,
                "seq6JsPayloadLine": 925,
                "seq6ResponseRuntimeLine": 938,
            },
        },
        "freshFailedSample": {
            "id": attempt.get("session"),
            "reason": (
                "Complete fresh pure-protocol forced-overlap run: bootstrap/second/sequence/bundle POW completed, "
                "first-failure response order matched s00, seq4 advanced to a new POW, and final seq5/seq6 decoded activities equal s00 but still rejected."
            ),
            "knownLimitations": [
                "It is a no-browser protocol run, so browser-only runtime state is absent by design.",
                "Encoded payload/pc/outer session fields still differ from s00 according to the boundary audit.",
                "It is selected for state-transition divergence analysis, not as a successful PoC.",
            ],
            "paths": [file_entry(path, role) for role, path in fresh_paths.items()],
            "attemptChecks": attempt.get("checks"),
            "stepSummaries": {
                name: step_summary(attempt, name)
                for name in [
                    "bootstrap",
                    "second",
                    "sequence",
                    "bundle",
                    "firstFailureOverlap",
                    "seq4AfterOverlap",
                    "finalSeq5Seq6Combo",
                ]
            },
            "finalResponses": {
                "seq5": {
                    "status": (seq5.get("response") or {}).get("status"),
                    "bodyText": (seq5.get("response") or {}).get("bodyText"),
                    "handlers": (seq5.get("decoded") or {}).get("handlers"),
                    "parts": (seq5.get("decoded") or {}).get("parts"),
                },
                "seq6": {
                    "status": (seq6.get("response") or {}).get("status"),
                    "handlers": (seq6.get("decoded") or {}).get("handlers"),
                },
            },
            "boundaryChecks": boundary.get("checks"),
        },
        "phase1Checks": {
            "allSuccessEvidenceFilesExist": all(
                p.exists()
                for p in [
                    success_runtime,
                    success_js,
                    success_cookie_json,
                    success_cookie_md,
                    success_bundle_decode_json,
                    success_bundle_decode_md,
                ]
            ),
            "allFreshEvidenceFilesExist": all(path.exists() for path in fresh_paths.values()),
            "freshMeetsSelectionCriteria": all(criteria.values()),
        },
        "next": {
            "phase": "Phase 2",
            "artifact": str(OUT_DIR / "hypothesis_matrix.json"),
            "script": str(REPO / "tools/build_hypothesis_matrix.py"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["phase1Checks"], "freshId": attempt.get("session")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
