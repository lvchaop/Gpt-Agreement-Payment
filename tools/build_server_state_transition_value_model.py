#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def mutation_digest(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "handler": m.get("handler"),
        "name": m.get("name"),
        "valueSha256": m.get("valueSha256"),
        "value": m.get("value"),
        "fieldCount": m.get("fieldCount"),
    }


def step_digest(step: dict[str, Any]) -> dict[str, Any]:
    resp = step.get("response") or {}
    ps = resp.get("partsSummary") or {}
    req = step.get("request") or {}
    return {
        "step": step.get("step"),
        "label": step.get("label"),
        "runtimeLine": step.get("runtimeLine"),
        "sourcePath": step.get("sourcePath"),
        "urlPath": step.get("urlPath"),
        "request": {
            "seq": req.get("seq"),
            "rsc": req.get("rsc"),
            "uuid": req.get("uuid"),
            "ci": req.get("ci"),
            "pc": req.get("pc"),
            "payloadSha256": req.get("payloadSha256"),
            "bodySha256": req.get("bodySha256"),
        },
        "response": {
            "decodedLine": resp.get("decodedLine"),
            "handlers": resp.get("handlers"),
            "successStatuses": ps.get("successStatuses"),
            "hasPx3": ps.get("hasPx3"),
            "hasPxde": ps.get("hasPxde"),
            "hasPow": ps.get("hasPow"),
            "mutations": [mutation_digest(m) for m in ps.get("mutations") or []],
        },
        "materialMeta": step.get("materialMeta"),
    }


def classify_step(step: dict[str, Any]) -> str:
    resp = step.get("response") or {}
    ps = resp.get("partsSummary") or {}
    statuses = ps.get("successStatuses") or []
    if "oIIoIooo|0" in statuses:
        return "success"
    if "oIIoIooo|-1" in statuses:
        return "rejected_px561"
    if ps.get("hasPow"):
        return "pow_challenge"
    if ps.get("hasPx3") or ps.get("hasPxde"):
        return "token_update"
    return "other"


def main() -> int:
    diff = load("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json")
    lineage = load("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json")
    accepted = load("output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json")

    s00 = diff.get("s00Timeline") or []
    fresh = diff.get("freshTimeline") or []
    s00_model = [step_digest(s) | {"class": classify_step(s)} for s in s00]
    fresh_model = [step_digest(s) | {"class": classify_step(s)} for s in fresh]

    s00_classes = [s["class"] for s in s00_model]
    fresh_classes = [s["class"] for s in fresh_model]

    first_class_divergence = None
    for idx, (a, b) in enumerate(zip(s00_classes, fresh_classes)):
        if a != b:
            first_class_divergence = {"index": idx, "s00Class": a, "freshClass": b}
            break

    final_s00 = next((s for s in s00_model if s.get("request", {}).get("seq") == "5" and s.get("request", {}).get("rsc") == "6"), None)
    final_fresh = next((s for s in fresh_model if s.get("request", {}).get("seq") == "5" and s.get("request", {}).get("rsc") == "6"), None)

    result = {
        "purpose": "Whole-sequence value model for collector server-state transitions before deciding any fresh-session experiment.",
        "inputs": {
            "collectorStateTransitionDiff": str(ROOT / "output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
            "serverExpectedStatePreSeq5Gap": str(ROOT / "output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"),
            "acceptedLine933GenerationLineage": str(ROOT / "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
        },
        "s00Model": s00_model,
        "freshModel": fresh_model,
        "sequenceClasses": {
            "s00": s00_classes,
            "fresh": fresh_classes,
            "firstClassDivergence": first_class_divergence,
        },
        "finalSeq5Comparison": {
            "s00": final_s00,
            "fresh": final_fresh,
        },
        "observations": [
            "Both sequences reach a final seq5/rsc6 request.",
            "The final response class diverges at seq5/rsc6: s00 is success and fresh is rejected_px561.",
            "Earlier value differences are session-specific token/challenge values; existing controls already tested obvious transplant or decoded-equality variants.",
            "The current evidence supports a server expected-state/history gap, not a justified new single-field fresh experiment.",
        ],
        "decision": {
            "readyForFreshExperiment": False,
            "reason": "The model still does not identify a single untested state transition. It narrows next work to request-history coherence: compare which exact prior request classes/bodies are included or missing before final seq5, especially first rejected PX561 + seq6/seq5 pairing in the same selected contrast.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"),
        },
        "checks": {
            "hasS00Model": bool(s00_model),
            "hasFreshModel": bool(fresh_model),
            "hasFinalS00Seq5": final_s00 is not None,
            "hasFinalFreshSeq5": final_fresh is not None,
            "finalS00Success": final_s00 is not None and final_s00["class"] == "success",
            "finalFreshRejected": final_fresh is not None and final_fresh["class"] == "rejected_px561",
            "priorSingleValueGapNotExperimentReady": lineage.get("checks", {}).get("readyForFreshExperiment") is False,
            "generationLineageNotExperimentReady": accepted.get("checks", {}).get("readyForFreshExperiment") is False,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
