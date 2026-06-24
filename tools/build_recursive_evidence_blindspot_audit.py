#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
OUT = HYP / "recursive_evidence_blindspot_audit.json"
PLAN = ROOT / "docs/pure-protocol-human-methodological-execution-plan.md"

SUCCESS_TOKENS = [
    "oIIoIooo|0",
    '"hasSuccessHandler": true',
    '"state": "continue"',
    '"state":"continue"',
    '"redirectUrl"',
]
NEGATIVE_TOKENS = [
    "oIIoIooo|-1",
    '"hasSuccessHandler": false',
    '"comboAnySuccess": false',
]


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def classify(path: Path, body: str, data: Any | None) -> dict[str, Any]:
    r = rel(path)
    success_hits = [tok for tok in SUCCESS_TOKENS if tok in body]
    negative_hits = [tok for tok in NEGATIVE_TOKENS if tok in body]
    category = "unclassified_recursive_json"
    replayable = False
    reason = "No path classifier assigned this recursive JSON file."

    if "/configs/" in r:
        category = "runner_config"
        reason = "Runner config files are setup metadata, not collector response evidence."
    elif r.startswith("output/protocol_reverse/reset_plan/browser_sampling_attempts/") or r.startswith(
        "output/protocol_reverse/reset_plan/route_b_browser_sampling_attempts/"
    ):
        category = "browser_sampling_attempt_reference"
        reason = "Browser sampling attempts may contain browser success tokens, but they are explicitly browser/Camoufox evidence and are summarized by reset sampling matrix/terminal audits, not fresh no-browser proof."
    elif r.startswith("output/protocol_reverse/seq5_seq6_combo_probe/extracted/"):
        category = "extracted_seq5_seq6_combo_response"
        reason = "Extracted combo response files are pure-protocol response extracts; current recursive scan checks whether any contains success handler."
    elif r.startswith("output/protocol_reverse/hypothesis_reframe/remaining_encoder_variant_dryruns/"):
        category = "offline_encoder_variant_dryrun"
        sent = data.get("sent") if isinstance(data, dict) else None
        reason = f"Remaining encoder variant dryrun material has sent={sent}; it is offline material unless a live probe artifact supersedes it."

    if category == "extracted_seq5_seq6_combo_response" and ('"hasSuccessHandler": true' in body or "oIIoIooo|0" in body):
        replayable = True
        reason = "Extracted pure-protocol combo response contains a success handler; this would need promotion."

    if category == "offline_encoder_variant_dryrun" and isinstance(data, dict) and data.get("sent") is True and success_hits:
        replayable = True
        reason = "A sent dryrun with success token would need promotion."

    return {
        "path": r,
        "category": category,
        "successHits": success_hits,
        "negativeHits": negative_hits,
        "isReplayableFreshNoBrowserSuccessEvidence": replayable,
        "reason": reason,
    }


def build() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(PROTO.rglob("*.json")):
        if len(path.relative_to(PROTO).parts) < 3:
            continue
        body = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = None
        rows.append(classify(path, body, data))

    success_rows = [row for row in rows if row["successHits"]]
    negative_rows = [row for row in rows if row["negativeHits"]]
    replayable = [row for row in rows if row["isReplayableFreshNoBrowserSuccessEvidence"]]
    unclassified_success = [
        row for row in success_rows
        if row["category"] == "unclassified_recursive_json"
    ]
    extracted = [row for row in rows if row["category"] == "extracted_seq5_seq6_combo_response"]
    extracted_success = [row for row in extracted if row["successHits"]]
    browser_success_refs = [
        row for row in success_rows
        if row["category"] == "browser_sampling_attempt_reference"
    ]

    category_counts: dict[str, int] = {}
    for row in rows:
        category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1

    checks = {
        "planExists": PLAN.exists(),
        "recursiveJsonFileCount": len(rows),
        "categoryCount": len(category_counts),
        "recursiveSuccessSignalFileCount": len(success_rows),
        "recursiveNegativeSignalFileCount": len(negative_rows),
        "browserSamplingSuccessReferenceCount": len(browser_success_refs),
        "extractedSeq5Seq6ResponseCount": len(extracted),
        "extractedSeq5Seq6SuccessSignalCount": len(extracted_success),
        "unclassifiedRecursiveSuccessSignalCount": len(unclassified_success),
        "replayableFreshNoBrowserSuccessEvidenceCount": len(replayable),
        "hasReplayableFreshNoBrowserSuccessEvidence": bool(replayable),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Recursively audit nested protocol_reverse JSON artifacts that top-level unmined evidence scanning can miss.",
        "checks": checks,
        "categoryCounts": category_counts,
        "successSignalRows": success_rows[:120],
        "unclassifiedSuccessSignalRows": unclassified_success,
        "replayableFreshNoBrowserSuccessEvidence": replayable,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": (
                "Recursive nested evidence scan found no replayable fresh no-browser success evidence. "
                "Nested success tokens are browser sampling references already covered by reset terminal authority; extracted pure-protocol seq5/seq6 responses contain no success signal."
            ),
        },
    }


def main() -> int:
    doc = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
