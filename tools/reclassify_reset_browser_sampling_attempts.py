#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_reset_browser_webshare_sampling import classify_from_artifacts


ROOT = Path(__file__).resolve().parents[1]
ATTEMPT_DIR = ROOT / "output/protocol_reverse/reset_plan/browser_sampling_attempts"
OUT = ROOT / "output/protocol_reverse/reset_plan/reset_browser_sampling_reclassification_audit.json"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def class_matches(sample_class: str, classification: dict[str, Any]) -> bool:
    if sample_class == "browser_success_webshare":
        return classification.get("successLike") is True
    if sample_class == "browser_failure_webshare":
        return classification.get("successLike") is False
    return False


def main() -> int:
    rows = []
    changed = []
    for path in sorted(ATTEMPT_DIR.glob("browser_sampling_*.json")):
        doc = read_json(path)
        checks = doc.get("checks") or {}
        if checks.get("executeRequested") is not True:
            continue

        old_classification = doc.get("classification") or {}
        result = doc.get("execution") or {}
        artifacts = doc.get("artifacts") or {}
        new_classification = classify_from_artifacts(result, artifacts)
        matches = class_matches(str(doc.get("sampleClass") or ""), new_classification)

        row = {
            "path": str(path.resolve()),
            "sampleClass": doc.get("sampleClass"),
            "sessionId": doc.get("sessionId"),
            "oldStage": old_classification.get("stage"),
            "newStage": new_classification.get("stage"),
            "oldSuccessLike": old_classification.get("successLike"),
            "newSuccessLike": new_classification.get("successLike"),
            "classificationChanged": old_classification.get("stage") != new_classification.get("stage")
            or old_classification.get("successLike") != new_classification.get("successLike"),
            "classificationMatchesSampleClass": matches,
            "countsTowardResetMinimum": matches,
            "runtimeEvidence": new_classification.get("runtimeEvidence"),
        }
        rows.append(row)

        if row["classificationChanged"] or checks.get("classificationMatchesSampleClass") is not matches:
            doc["previousClassification"] = old_classification
            doc["classification"] = new_classification
            doc["runtimeEvidenceClassification"] = new_classification
            doc["finalStage"] = new_classification.get("stage")
            doc.setdefault("checks", {})["classificationMatchesSampleClass"] = matches
            doc.setdefault("decision", {})["countsTowardResetMinimum"] = matches
            doc.setdefault("decision", {})["reason"] = new_classification.get("reason")
            write_json(path, doc)
            changed.append(str(path.resolve()))

    audit = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "attemptDir": str(ATTEMPT_DIR.resolve()),
        "changedCount": len(changed),
        "changed": changed,
        "rows": rows,
        "checks": {
            "executedAttemptCount": len(rows),
            "successLikeCount": len([row for row in rows if row["newSuccessLike"] is True]),
            "failureLikeCount": len([row for row in rows if row["newSuccessLike"] is False]),
            "countedResetAttemptCount": len([row for row in rows if row["countsTowardResetMinimum"] is True]),
            "goalComplete": False,
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "reason": "Reclassified executed browser reset sampling attempts from runtime trace evidence.",
        },
    }
    write_json(OUT, audit)
    print(json.dumps({"json": str(OUT), "checks": audit["checks"], "changed": changed}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
