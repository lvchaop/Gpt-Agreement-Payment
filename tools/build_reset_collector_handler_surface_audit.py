#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"
RESET = ROOT / "output/protocol_reverse/reset_plan"
TAXONOMY = RESET / "reset_runtime_js_event_taxonomy.json"
RUNTIME_REDUCTION = RESET / "reset_runtime_js_candidate_reduction.json"
COOKIE = RESET / "reset_cookie_mutation_audit.json"
FINAL_CLASS = RESET / "reset_final_response_class_audit.json"
SINGLE = RESET / "reset_single_transition_candidates.json"
OUT = RESET / "reset_collector_handler_surface_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_handler_feature(feature: str) -> dict[str, Any]:
    if feature.startswith("js.data.handlerKey:"):
        return {"kind": "handlerKey", "key": feature.removeprefix("js.data.handlerKey:"), "args": None}
    if feature.startswith("js.data.table:"):
        return {"kind": "table", "key": None, "args": None, "table": feature.removeprefix("js.data.table:")}
    if feature.startswith("js.handlerArgs:"):
        rest = feature.removeprefix("js.handlerArgs:")
        key, sep, raw_args = rest.partition(":")
        args = None
        parse_error = None
        if sep:
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError as exc:
                parse_error = str(exc)
        return {"kind": "handlerArgs", "key": key, "args": args, "rawArgs": raw_args, "parseError": parse_error}
    return {"kind": "other", "key": None, "args": None}


def classify_surface(parsed: dict[str, Any]) -> tuple[str, str, bool, bool]:
    key = parsed.get("key")
    kind = parsed.get("kind")
    args = parsed.get("args") if isinstance(parsed.get("args"), list) else []
    first = args[0] if args else None

    if kind == "table":
        return (
            "collector_handler_table",
            "Handler table identity is response dispatch metadata; no value lineage into pre-accept request/cookie/risk is proven.",
            False,
            False,
        )

    if key in {"IoooII", "oIIoIIoo"} or first in {"_px3", "_pxde"}:
        return (
            "px_cookie_handler",
            "This surface maps to response-side _px cookie mutation. reset_cookie_mutation_audit proves _px3/_pxde mutation occurs offline but still has anySuccess0=false.",
            True,
            False,
        )

    if key == "IIooII":
        return (
            "collector_config_flag_handler",
            "IIooII rows carry collector/browser config flags such as cc/rf/fp/fed/nf; no pre-accept pure-protocol transition is proven.",
            False,
            False,
        )

    if key == "IooIIo":
        return (
            "pow_challenge_handler",
            "IooIIo rows align with challenge/POW target material. POW recompute is already proved and not sufficient for collector success.",
            False,
            False,
        )

    if key == "IooIoI":
        return (
            "encoded_response_state_handler",
            "IooIoI carries per-response encoded state, but no lineage proves it can be independently constructed before collector acceptance.",
            False,
            False,
        )

    if key in {
        "IIoIIo",
        "IIoIoI",
        "IoIIII",
        "IoIIIo",
        "IoIoIo",
        "IooIoo",
        "oIIoIoII",
        "oIIoIoIo",
        "oIIooIIo",
        "oIIooIoo",
        "oIooII",
        "ooooII",
    }:
        return (
            "score_or_response_state_handler",
            "This is response-side score/state/config dispatch observed after collector response handling; no constructible pre-accept transition is proven.",
            False,
            False,
        )

    return (
        "score_or_response_state_handler",
        "Unknown handler key remains response-handler dispatch by source evidence; absent lineage into request/cookie/risk, it is not a Phase 5 input.",
        False,
        False,
    )


def is_handler_candidate(feature: str) -> bool:
    return feature.startswith("js.data.handlerKey:") or feature.startswith("js.handlerArgs:") or feature.startswith("js.data.table:")


def build() -> dict[str, Any]:
    taxonomy = read_json(TAXONOMY)
    runtime_reduction = read_json(RUNTIME_REDUCTION)
    cookie = read_json(COOKIE)
    final_class = read_json(FINAL_CLASS)
    single = read_json(SINGLE)

    candidates = [
        cand
        for cand in (taxonomy.get("candidateClientVisibleProxies") or [])
        if is_handler_candidate(cand.get("feature") or "")
    ]

    cookie_checks = cookie.get("checks") or {}
    final_checks = final_class.get("checks") or {}
    single_checks = single.get("checks") or {}
    reduction_checks = runtime_reduction.get("checks") or {}

    surfaces: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "surfaceCount": 0,
            "handlerKeyFeatureCount": 0,
            "handlerArgsFeatureCount": 0,
            "categories": Counter(),
            "argExamples": [],
            "sourceExamples": [],
        }
    )

    for cand in candidates:
        feature = cand.get("feature") or ""
        parsed = parse_handler_feature(feature)
        category, reason, enters_cookie, promoted = classify_surface(parsed)
        key = parsed.get("key") or f"table:{parsed.get('table')}"
        surface = {
            "feature": feature,
            "handlerKey": parsed.get("key"),
            "kind": parsed.get("kind"),
            "args": parsed.get("args"),
            "parseError": parsed.get("parseError"),
            "successCount": cand.get("successCount"),
            "failureCount": cand.get("failureCount"),
            "successWithJsCount": cand.get("successWithJsCount"),
            "failureWithJsCount": cand.get("failureWithJsCount"),
            "examples": cand.get("examples"),
            "classification": {
                "category": category,
                "entersRequestCookieRiskProved": enters_cookie,
                "constructiblePreAcceptTransitionProved": False,
                "promoteToSingleTransitionCandidate": promoted,
                "reason": reason,
            },
        }
        surfaces.append(surface)

        row = by_key[key]
        row["surfaceCount"] += 1
        if parsed.get("kind") == "handlerKey":
            row["handlerKeyFeatureCount"] += 1
        if parsed.get("kind") == "handlerArgs":
            row["handlerArgsFeatureCount"] += 1
            if len(row["argExamples"]) < 8:
                row["argExamples"].append(parsed.get("args"))
        row["categories"][category] += 1
        if len(row["sourceExamples"]) < 4:
            row["sourceExamples"].extend((cand.get("examples") or [])[: max(0, 4 - len(row["sourceExamples"]))])

    category_counts = Counter((s.get("classification") or {}).get("category") for s in surfaces)
    promoted = [s for s in surfaces if (s.get("classification") or {}).get("promoteToSingleTransitionCandidate")]
    unclassified = [s for s in surfaces if not (s.get("classification") or {}).get("category")]
    parse_errors = [s for s in surfaces if s.get("parseError")]

    key_summary = []
    for key, row in sorted(by_key.items()):
        key_summary.append(
            {
                "handlerKey": key,
                "surfaceCount": row["surfaceCount"],
                "handlerKeyFeatureCount": row["handlerKeyFeatureCount"],
                "handlerArgsFeatureCount": row["handlerArgsFeatureCount"],
                "categoryCounts": dict(row["categories"]),
                "argExamples": row["argExamples"],
                "sourceExamples": row["sourceExamples"],
            }
        )

    negative_controls = {
        "runtimeReductionHasCollectorHandlerBucket": (reduction_checks.get("categoryCounts") or {}).get("collector_response_handler") == len(candidates),
        "runtimeReductionPromotedNone": reduction_checks.get("promotedSingleTransitionCandidateCount") == 0,
        "cookieMutationOfflineJarHasPx3Pxde": cookie_checks.get("allOfflineJarHasPx3Pxde") is True,
        "cookieMutationAnySuccess0False": cookie_checks.get("anySuccess0") is False,
        "cookieMutationRiskVerifyCandidateIncomplete": cookie_checks.get("riskVerifyCandidateComplete") is False,
        "finalResponsesSameFailureClass": final_checks.get("allFinalResponsesSameClass") is True
        and final_checks.get("allFinalResponsesAreSeq5Minus1") is True
        and final_checks.get("anySeq5Success0") is False,
        "singleTransitionStillAbsent": single_checks.get("singleTransitionCandidateCount") == 0,
    }

    checks = {
        "taxonomyExists": TAXONOMY.exists(),
        "runtimeReductionExists": RUNTIME_REDUCTION.exists(),
        "cookieMutationAuditExists": COOKIE.exists(),
        "finalResponseClassAuditExists": FINAL_CLASS.exists(),
        "singleTransitionCandidatesExists": SINGLE.exists(),
        "handlerCandidateCount": len(candidates),
        "distinctHandlerKeyCount": len([k for k in by_key if not k.startswith("table:")]),
        "collectorHandlerTableSurfaceCount": category_counts.get("collector_handler_table", 0),
        "pxCookieHandlerSurfaceCount": category_counts.get("px_cookie_handler", 0),
        "powChallengeHandlerSurfaceCount": category_counts.get("pow_challenge_handler", 0),
        "configFlagHandlerSurfaceCount": category_counts.get("collector_config_flag_handler", 0),
        "scoreOrStateHandlerSurfaceCount": category_counts.get("score_or_response_state_handler", 0)
        + category_counts.get("encoded_response_state_handler", 0),
        "unclassifiedHandlerSurfaceCount": len(unclassified),
        "handlerArgParseErrorCount": len(parse_errors),
        "promotedSingleTransitionCandidateCount": len(promoted),
        "negativeControlsAllHold": all(negative_controls.values()),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Route A: split reset collector_response_handler runtime/JS surfaces and decide whether any can be promoted to a pure-protocol Phase 5 transition.",
        "inputs": {
            "taxonomy": str(TAXONOMY),
            "runtimeCandidateReduction": str(RUNTIME_REDUCTION),
            "cookieMutationAudit": str(COOKIE),
            "finalResponseClassAudit": str(FINAL_CLASS),
            "singleTransitionCandidates": str(SINGLE),
        },
        "checks": checks,
        "negativeControls": negative_controls,
        "categoryCounts": dict(category_counts),
        "handlerKeySummary": key_summary,
        "promotedCandidates": promoted,
        "unclassifiedSurfaces": unclassified,
        "parseErrors": parse_errors,
        "surfaceSample": surfaces[:200],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Collector handler surfaces are response-side cookie/config/POW/score/state dispatch. "
                "The only cookie-mutating subgroup is already covered by reset_cookie_mutation_audit and still lacks oIIoIooo|0/risk success. "
                "No handler surface proves a single client-visible, constructible, pre-accept transition."
            ),
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "categoryCounts": doc["categoryCounts"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
