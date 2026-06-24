#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HYP = ROOT / "output/protocol_reverse/hypothesis_reframe"
GOAL = ROOT / "output/protocol_reverse/goal_audit"
OUT = HYP / "coherent_encoder_variant_experiment_manifest.json"
PLAN = ROOT / "docs/pure-protocol-human-hypothesis-plan.md"


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> dict[str, Any]:
    candidate_audit = read_json(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json")
    terminal = read_json(ROOT / "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json")
    goal = read_json(ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json")
    candidate = candidate_audit.get("candidate") or {}
    c = candidate_audit.get("checks") or {}
    t = terminal.get("checks") or {}
    g = goal.get("summary") or {}

    gate = {
        "candidateAuditExists": bool(candidate_audit),
        "singleCandidateFromCandidateAudit": c.get("singleTransitionCandidateCount") == 1,
        "candidateNotCoveredByPriorControls": c.get("candidateNotCoveredByPriorControls") is True,
        "neighborNegativeControlsPresent": c.get("neighborNegativeControlsPresent") is True,
        "terminalCurrentlyBlocksGenericPhase5": t.get("noCurrentRouteToPhase5") is True,
        "goalStillMissingEndToEndPoc": "end_to_end_pure_protocol_poc" in (g.get("blockingOrMissing") or []),
    }
    manifest_complete = all(gate.values())

    checks = {
        **gate,
        "manifestComplete": manifest_complete,
        "readyForOneControlledFreshExperiment": manifest_complete,
        "readyForGenericPhase5": False,
        "goalComplete": False,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "plan": str(PLAN),
        "purpose": "Define the single controlled fresh-session experiment for the only coherent encoder variant not covered by prior controls.",
        "inputs": {
            "candidateAudit": str(HYP / "coherent_encoder_variant_vs_prior_controls_audit.json"),
            "resetTerminalBoundaryAudit": str(ROOT / "output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json"),
            "goalGapAudit": str(ROOT / "output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json"),
        },
        "checks": checks,
        "candidate": candidate,
        "experiment": {
            "id": "coherent_encoder_variant_template_uuid_fresh_marker_template_pc",
            "type": "single_fresh_session_control",
            "countsAsFinalPureProtocolPoCOnlyIf": [
                "collector seq5 returns oIIoIooo|0 or equivalent HUMAN success handler",
                "decoded _px3/_pxde/_pxvid are applied to cookie jar",
                "Microsoft /API/Proofs/risk/verify returns state=continue using those cookies/tokens",
                "/API/CreateAccount returns redirectUrl without browser/Camoufox/mouse/vision/external captcha",
            ],
            "candidateMutation": {
                "payloadUuidSource": "template",
                "markerSource": "fresh",
                "pcUuidSource": "payload",
                "formOuterSource": "fresh",
                "payloadSource": "built",
                "pcSource": "computed",
                "expectedPc": ((candidate.get("summary") or {}).get("pc")),
                "payloadSha256": ((candidate.get("summary") or {}).get("payloadSha256")),
                "bodySha256": ((candidate.get("summary") or {}).get("bodySha256")),
            },
            "fixedControls": [
                "one fresh Webshare session",
                "no browser/Camoufox/mouse/vision/external captcha",
                "same protocol runner and collector decoder as previous seq5/seq6 controls",
                "record request body sha256, decoded collector handlers, cookie jar mutation, risk/verify, and CreateAccount result",
            ],
            "negativeControlsAlreadyCover": [
                str(GOAL / "forced_overlap_payload_pc_split_control_audit.json"),
                str(GOAL / "clean_history_payload_pc_controls_audit.json"),
                str(GOAL / "clean_history_pc_uuid_controls_audit.json"),
                str(GOAL / "outer_binding_controls_audit.json"),
            ],
            "successCriterion": "collector HUMAN success plus downstream risk/verify state=continue and CreateAccount redirectUrl",
            "failureCriterion": "collector still returns oIIoIooo|-1, {do:[]}, no HUMAN handler, or downstream risk/verify/CreateAccount chain fails",
        },
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": manifest_complete,
            "recommendedExperiment": "coherent_encoder_variant_template_uuid_fresh_marker_template_pc" if manifest_complete else None,
            "nextArtifact": str(GOAL / "coherent_encoder_variant_live_probe_audit.json") if manifest_complete else None,
            "nextScript": str(ROOT / "tools/run_coherent_encoder_variant_live_probe.py") if manifest_complete else None,
            "reason": (
                "A single coherent encoder variant is isolated and prior neighboring controls are present. "
                "This authorizes exactly one controlled fresh-session experiment, not generic Phase 5 exploration."
            )
            if manifest_complete
            else "Experiment manifest is incomplete; inspect checks.",
        },
    }


def main() -> int:
    doc = build()
    write_json(OUT, doc)
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "experiment": doc["experiment"], "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
