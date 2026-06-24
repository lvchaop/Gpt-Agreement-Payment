#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
BASE = PROTO / "hypothesis_reframe"
OUT = BASE / "high_value_unmined_evidence_triage.json"
UNMINED = BASE / "unmined_local_evidence_source_audit.json"


def load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def classify_success_file(path: Path, directory: str) -> dict[str, Any]:
    body = text(path)
    lower_name = path.name.lower()
    if directory in {"collector_chain", "baseline", "collector_state"}:
        category = "accepted_browser_or_baseline_success"
        replayable = False
        reason = "Contains known browser/baseline accepted success evidence, not a fresh no-browser success."
    elif directory == "reset_plan":
        category = "reset_terminal_or_manifest_reference"
        replayable = False
        reason = "Reset plan files reference success criteria or browser success samples already covered by reset terminal authority; they are not independent fresh no-browser success evidence."
    elif directory == "collector_replay_material":
        category = "template_or_replay_material_contains_success_literal"
        replayable = False
        reason = "Replay material can contain success literal from source run; not proof that replay produced fresh oIIoIooo|0."
    elif directory == "cookie_jar":
        category = "downstream_cookie_risk_success"
        replayable = False
        reason = "Cookie/risk state=continue is downstream of accepted collector success; final gap already treats downstream as proven but not root cause."
    elif directory == "px561_constructor":
        category = "live_probe_or_constructor_control"
        replayable = "hasSuccessHandler\": true" in body and "observedSuccess" in body
        reason = "Constructor/live-probe artifact needs explicit observed live success; otherwise it is not a fresh no-browser HUMAN success proof."
    elif directory == "source_offsets":
        category = "static_or_reconciliation_source_offset"
        replayable = False
        reason = "Source-offset reconciliation explains known success/failure boundaries; static evidence cannot override runtime/probe failures."
    else:
        category = "unclassified_success_signal"
        replayable = False
        reason = "Success token exists but no classifier maps it to fresh no-browser oIIoIooo|0."
    return {
        "dir": directory,
        "path": str(path.resolve()),
        "category": category,
        "containsSuccess0": "oIIoIooo|0" in body,
        "containsRiskContinue": '"state": "continue"' in body or '"state":"continue"' in body or '"risk_verify_state_continue": true' in body,
        "containsCreateAccountRedirect": '"create_account_redirectUrl": true' in body or '"redirectUrl"' in body,
        "isReplayableFreshNoBrowserSuccessEvidence": replayable,
        "reason": reason,
    }


def summarize_dir(directory: str) -> dict[str, Any]:
    path = PROTO / directory
    files = sorted(path.glob("*.json"))
    success_files = []
    negative_files = 0
    sent_true = 0
    sent_false = 0
    has_success_handler_true = 0
    has_success_handler_false = 0
    http200 = 0
    for file in files:
        body = text(file)
        if "oIIoIooo|0" in body or '"hasSuccessHandler": true' in body or '"state": "continue"' in body or '"state":"continue"' in body:
            success_files.append(file)
        if "oIIoIooo|-1" in body or '"hasSuccessHandler": false' in body:
            negative_files += 1
        data = load_json(file)
        if isinstance(data, dict):
            if data.get("sent") is True:
                sent_true += 1
            if data.get("sent") is False:
                sent_false += 1
            compact = json.dumps(data, ensure_ascii=False)
            has_success_handler_true += int('"hasSuccessHandler": true' in compact)
            has_success_handler_false += int('"hasSuccessHandler": false' in compact)
            http200 += int('"status": 200' in compact or '"statuses": [200' in compact)
    return {
        "dir": directory,
        "jsonFileCount": len(files),
        "successSignalFileCount": len(success_files),
        "negativeSignalFileCount": negative_files,
        "sentTrueFileCount": sent_true,
        "sentFalseFileCount": sent_false,
        "hasSuccessHandlerTrueFileCount": has_success_handler_true,
        "hasSuccessHandlerFalseFileCount": has_success_handler_false,
        "http200SignalFileCount": http200,
        "successSignalSample": [str(p.resolve()) for p in success_files[:5]],
    }


def build() -> dict[str, Any]:
    unmined = load_json(UNMINED) or {}
    high_value_dirs = unmined.get("highValueUnminedDirs") or []
    success_rows = unmined.get("unminedSuccessSignalFiles") or []

    classified_success = [
        classify_success_file(Path(row["path"]), row["dir"])
        for row in success_rows
    ]
    dir_summaries = [summarize_dir(name) for name in high_value_dirs]

    replayable_success = [row for row in classified_success if row["isReplayableFreshNoBrowserSuccessEvidence"]]
    unclassified = [row for row in classified_success if row["category"] == "unclassified_success_signal"]
    dirs_with_success = [row for row in dir_summaries if row["successSignalFileCount"] > 0]
    dirs_with_live_negatives = [
        row for row in dir_summaries
        if row["sentTrueFileCount"] > 0 and row["hasSuccessHandlerFalseFileCount"] > 0
    ]

    checks = {
        "highValueUnminedDirectoryCount": len(high_value_dirs),
        "classifiedSuccessSignalFileCount": len(classified_success),
        "replayableFreshNoBrowserSuccessEvidenceCount": len(replayable_success),
        "unclassifiedSuccessSignalCount": len(unclassified),
        "dirsWithSuccessSignalCount": len(dirs_with_success),
        "dirsWithLiveNegativeSignalsCount": len(dirs_with_live_negatives),
        "hasReplayableFreshNoBrowserSuccessEvidence": bool(replayable_success),
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    return {
        "artifact": str(OUT.resolve()),
        "purpose": "Triage high-value local evidence directories that were not included in the current final-gap artifact.",
        "inputs": {
            "unminedLocalEvidenceSourceAudit": str(UNMINED.resolve()),
            "serverInternalUnobservedStateFinalGap": str((BASE / "server_internal_unobserved_state_final_gap.json").resolve()),
        },
        "dirSummaries": dir_summaries,
        "classifiedSuccessSignals": classified_success,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "replayableFreshNoBrowserSuccessEvidenceFound": bool(replayable_success),
            "reason": (
                "No unmined success-signal file is classified as replayable fresh no-browser oIIoIooo|0 evidence; "
                "the remaining high-value directories contain constructor/source/downstream/negative probe evidence that should be referenced in final gap but do not unlock a fresh experiment."
            ),
            "nextArtifact": str((BASE / "server_internal_unobserved_state_final_gap.json").resolve()),
            "nextScript": str((REPO / "tools/build_server_internal_unobserved_state_final_gap.py").resolve()),
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
