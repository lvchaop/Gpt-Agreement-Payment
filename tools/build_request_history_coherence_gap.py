#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def classify(step: dict[str, Any]) -> str:
    url = step.get("urlPath")
    req = step.get("request") or {}
    resp = step.get("response") or {}
    ps = resp.get("partsSummary") or {}
    statuses = ps.get("successStatuses") or []
    if url == "/api/v2/msft":
        return f"msft_seq{req.get('seq')}_rsc{req.get('rsc')}"
    if url == "/assets/js/bundle" and ps.get("hasPow"):
        return f"bundle_seq{req.get('seq')}_pow"
    if url == "/assets/js/bundle" and "oIIoIooo|-1" in statuses:
        return f"bundle_seq{req.get('seq')}_px561_reject"
    if url == "/assets/js/bundle" and "oIIoIooo|0" in statuses:
        return f"bundle_seq{req.get('seq')}_px561_success"
    if url == "/assets/js/bundle":
        return f"bundle_seq{req.get('seq')}_token"
    return f"{url}_seq{req.get('seq')}"


def compact(step: dict[str, Any]) -> dict[str, Any]:
    req = step.get("request") or {}
    resp = step.get("response") or {}
    ps = resp.get("partsSummary") or {}
    return {
        "step": step.get("step"),
        "label": step.get("label"),
        "runtimeLine": step.get("runtimeLine"),
        "sourcePath": step.get("sourcePath"),
        "class": classify(step),
        "urlPath": step.get("urlPath"),
        "seq": req.get("seq"),
        "rsc": req.get("rsc"),
        "ci": req.get("ci"),
        "activityTypes": (step.get("decodedPayload") or {}).get("activityTypes") or (step.get("materialMeta") or {}).get("activityTypes"),
        "responseHandlers": resp.get("handlers"),
        "successStatuses": ps.get("successStatuses"),
        "hasPow": ps.get("hasPow"),
        "payloadSha256": req.get("payloadSha256"),
        "bodySha256": req.get("bodySha256"),
    }


def index_of(classes: list[str], prefix: str) -> int | None:
    for i, c in enumerate(classes):
        if c.startswith(prefix):
            return i
    return None


def main() -> int:
    diff = load("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json")
    model = load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")
    matrix = load("output/protocol_reverse/hypothesis_reframe/hypothesis_matrix.json")

    s00 = [compact(s) for s in diff.get("s00Timeline") or []]
    fresh = [compact(s) for s in diff.get("freshTimeline") or []]
    s00_classes = [s["class"] for s in s00]
    fresh_classes = [s["class"] for s in fresh]

    s00_msft_before_first_bundle_pow = [
        c for c in s00_classes[: index_of(s00_classes, "bundle_seq0_pow")]
        if c.startswith("msft_")
    ]
    fresh_msft_before_first_bundle_pow = [
        c for c in fresh_classes[: index_of(fresh_classes, "bundle_seq0_pow")]
        if c.startswith("msft_")
    ]
    s00_has_msft_seq1_to_3_before_bundle_pow = all(
        item in s00_msft_before_first_bundle_pow
        for item in ["msft_seq1_rsc2", "msft_seq2_rsc3", "msft_seq3_rsc4"]
    )
    fresh_lacks_msft_seq1_to_3_before_bundle_pow = fresh_msft_before_first_bundle_pow == ["msft_seq0_rsc1"]
    has_order_gap = s00_has_msft_seq1_to_3_before_bundle_pow and fresh_lacks_msft_seq1_to_3_before_bundle_pow

    result = {
        "purpose": "Compare chronological request-history coherence before final seq5; identify whether selected fresh contrast follows s00 state-transition order.",
        "inputs": {
            "collectorStateTransitionDiff": str(ROOT / "output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
            "serverStateTransitionValueModel": str(ROOT / "output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
            "hypothesisMatrix": str(ROOT / "output/protocol_reverse/hypothesis_reframe/hypothesis_matrix.json"),
        },
        "s00Chronology": s00,
        "freshChronology": fresh,
        "classSequences": {
            "s00": s00_classes,
            "fresh": fresh_classes,
        },
        "coherenceGap": {
            "id": "R1_msft_seq1_3_before_bundle_pow_order",
            "s00Evidence": {
                "msftBeforeFirstBundlePow": s00_msft_before_first_bundle_pow,
                "firstBundlePowIndex": index_of(s00_classes, "bundle_seq0_pow"),
            },
            "freshEvidence": {
                "msftBeforeFirstBundlePow": fresh_msft_before_first_bundle_pow,
                "firstBundlePowIndex": index_of(fresh_classes, "bundle_seq0_pow"),
            },
            "observedDifference": (
                "s00 completes msft seq1/rsc2, seq2/rsc3, and seq3/rsc4 before first bundle POW; "
                "selected fresh performs bundle seq0 POW immediately after bootstrap, before msft seq1-3."
                if has_order_gap
                else "No order gap: selected fresh also completes msft seq1/rsc2, seq2/rsc3, and seq3/rsc4 before first bundle POW."
            ),
            "whyThisCanAffectServerState": "The first bundle POW response seeds ci/cs/jo/powChallenge for later PX561. If collector/HUMAN expected state is tied to the preceding Microsoft msft collector history, generating bundle POW before msft seq1-3 can produce a coherent but wrong expected state.",
            "existingControlsStatus": (
                "No current artifact in the hypothesis_reframe sequence proves a fresh run with s00 chronological order and the same later final seq5 construction. Prior controls tested many field/timing variants but the selected contrast still contains this order mismatch."
                if has_order_gap
                else "The selected contrast already follows this chronological order, so R1 is not a valid minimal-divergence experiment."
            ),
        },
        "decision": {
            "readyForFreshExperiment": has_order_gap,
            "recommendedExperiment": (
                "Run one fresh Webshare session with s00 chronological order: bootstrap msft seq0, msft seq1, msft seq2, msft seq3, then bundle seq0 POW, bundle seq1 token, first PX561 reject, bundle seq3 token, bundle seq4 POW, final seq5/seq6. Change only request-history order versus the selected contrast; keep pure protocol and new session."
                if has_order_gap
                else None
            ),
            "nextArtifact": (
                str(ROOT / "output/protocol_reverse/hypothesis_reframe/minimal_divergence_experiment_audit.json")
                if has_order_gap
                else str(ROOT / "output/protocol_reverse/hypothesis_reframe/next_decisive_static_gap.json")
            ),
        },
        "checks": {
            "hasS00Chronology": bool(s00),
            "hasFreshChronology": bool(fresh),
            "s00HasMsftSeq1To3BeforeBundlePow": s00_has_msft_seq1_to_3_before_bundle_pow,
            "freshLacksMsftSeq1To3BeforeBundlePow": fresh_lacks_msft_seq1_to_3_before_bundle_pow,
            "hasOrderGap": has_order_gap,
            "finalDivergenceStillSeq5": model.get("checks", {}).get("finalS00Success") is True and model.get("checks", {}).get("finalFreshRejected") is True,
            "primaryHypothesisH3": matrix.get("decision", {}).get("primaryNextHypothesis") == "H3_collector_server_state",
            "readyForFreshExperiment": has_order_gap,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
