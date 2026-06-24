#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
OUTLOOK = REPO / "output/outlook_browser"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "js_internal_event_taxonomy.json"

OUTCOME_KINDS = {
    "hsprotect.main.jl.dispatch",
    "hsprotect.main.jl.item",
    "hsprotect.captcha.Ot",
}
OUTCOME_TOKENS = {"oIIoIooo", "succeeded", "challenge_success"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def run_from_classification(path: Path) -> str:
    return path.name.removeprefix("trace_classification_").removesuffix(".json")


def is_full_success(classification: dict[str, Any]) -> bool:
    checks = classification.get("checks") or {}
    return (
        checks.get("decoded_oIIoIooo_0") is True
        and checks.get("risk_verify_state_continue") is True
        and checks.get("create_account_redirectUrl") is True
    )


def event_features(row: dict[str, Any]) -> set[str]:
    features = set()
    kind = row.get("kind")
    if kind:
        features.add(f"kind:{kind}")
    data = row.get("data") if isinstance(row.get("data"), dict) else {}
    if data:
        for key in ["channel", "eventOrigin", "type", "target", "handlerKey", "table"]:
            value = data.get(key)
            if value is not None:
                features.add(f"data.{key}:{value}")
        if data.get("handlerKey") is not None and data.get("args") is not None:
            features.add(f"handlerArgs:{data.get('handlerKey')}:{json.dumps(data.get('args'), ensure_ascii=False)}")
    text = json.dumps(row, ensure_ascii=False)
    for token in ["oIIoIooo", "failed", "succeeded", "pow", "_px3", "_pxde", "sendBeacon", "worker", "challenge_success"]:
        if token in text:
            features.add(f"token:{token}")
    return features


def classify_feature(feature: str) -> str:
    if feature.startswith("kind:"):
        kind = feature.split(":", 1)[1]
        if kind in OUTCOME_KINDS:
            return "outcome_or_handler"
        return "client_event"
    if feature.startswith("token:"):
        token = feature.split(":", 1)[1]
        if token in OUTCOME_TOKENS:
            return "outcome_or_handler"
        return "token_surface"
    if feature.startswith("handlerArgs:oIIoIooo"):
        return "outcome_or_handler"
    return "client_event"


def build() -> dict[str, Any]:
    class_paths = [
        p for p in sorted(PROTO.glob("trace_classification_*.json"))
        if p.name != "trace_classification_summary.json"
    ]
    samples = []
    feature_runs: dict[str, set[str]] = defaultdict(set)
    feature_counts: Counter = Counter()
    kind_counts_by_stage: dict[str, Counter] = defaultdict(Counter)

    for path in class_paths:
        run = run_from_classification(path)
        classification = load_json(path)
        js_path = OUTLOOK / f"js_internal_trace_{run}.jsonl"
        rows = iter_jsonl(js_path)
        full = is_full_success(classification)
        stage = "full_success" if full else "non_full_success"
        sample_features = set()
        for row in rows:
            kind_counts_by_stage[stage][row.get("kind")] += 1
            feats = event_features(row)
            sample_features.update(feats)
            for feat in feats:
                feature_counts[feat] += 1
        for feat in sample_features:
            feature_runs[feat].add(run)
        samples.append(
            {
                "run": run,
                "stage": stage,
                "jsTrace": str(js_path.resolve()),
                "rowCount": len(rows),
                "featureCount": len(sample_features),
            }
        )

    full_runs = {s["run"] for s in samples if s["stage"] == "full_success"}
    non_runs = {s["run"] for s in samples if s["stage"] == "non_full_success"}
    feature_rows = []
    for feature, runs in feature_runs.items():
        full_true = sorted(runs & full_runs)
        non_true = sorted(runs & non_runs)
        category = classify_feature(feature)
        all_full = len(full_true) == len(full_runs) and bool(full_runs)
        absent_non = len(non_true) == 0
        candidate = all_full and absent_non and category not in {"outcome_or_handler"}
        feature_rows.append(
            {
                "feature": feature,
                "category": category,
                "fullTrueCount": len(full_true),
                "nonFullTrueCount": len(non_true),
                "allFullTrue": all_full,
                "absentInNonFull": absent_non,
                "candidateNonOutcomeClientEvent": candidate,
                "fullRuns": full_true,
                "nonFullRuns": non_true[:20],
            }
        )
    feature_rows.sort(key=lambda r: (not r["candidateNonOutcomeClientEvent"], r["category"], r["feature"]))
    candidates = [row for row in feature_rows if row["candidateNonOutcomeClientEvent"]]
    outcome_separators = [
        row for row in feature_rows
        if row["allFullTrue"] and row["absentInNonFull"] and row["category"] == "outcome_or_handler"
    ]

    checks = {
        "sampleCount": len(samples),
        "fullSuccessRunCount": len(full_runs),
        "nonFullSuccessRunCount": len(non_runs),
        "featureCount": len(feature_rows),
        "candidateNonOutcomeClientEventCount": len(candidates),
        "outcomeSeparatorCount": len(outcome_separators),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Cross-sample taxonomy of JS internal hook events to test whether a non-outcome client-only event separates full success from non-full-success runs.",
        "inputs": {
            "traceClassifications": [str(p.resolve()) for p in class_paths],
            "jsTraceDir": str(OUTLOOK.resolve()),
            "serverInternalGapEvidenceInventory": str((BASE / "server_internal_gap_evidence_inventory.json").resolve()),
        },
        "samples": samples,
        "kindCountsByStage": {stage: dict(counter) for stage, counter in kind_counts_by_stage.items()},
        "candidateNonOutcomeClientEvents": candidates,
        "outcomeOnlySeparators": outcome_separators,
        "featureRowsSample": feature_rows[:100],
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "candidateNonOutcomeClientEventFound": bool(candidates),
            "reason": (
                "No non-outcome JS internal event separates all full_success runs from all non-full-success controls."
                if not candidates
                else "Candidate non-outcome JS events exist and need reduction before any experiment."
            ),
            "nextArtifact": None,
            "nextScript": None,
        },
        "checks": checks,
    }


def main() -> int:
    result = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
