#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
PROTO = REPO / "output/protocol_reverse"
DIFF = PROTO / "hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"
OUT = PROTO / "hypothesis_reframe/first_decisive_divergence.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    diff = read_json(DIFF)
    candidates = diff.get("divergenceCandidates") or []
    if not candidates:
        raise RuntimeError(f"no divergence candidates in {DIFF}")
    first = candidates[0]
    s00_step_no = first.get("s00Step")
    fresh_step_no = first.get("freshStep")
    comparison = next(
        (
            row for row in diff.get("comparisons") or []
            if row.get("s00Step") == s00_step_no and row.get("freshStep") == fresh_step_no
        ),
        None,
    )
    s00_step = next((row for row in diff.get("s00Timeline") or [] if row.get("runtimeLine") == first.get("s00RuntimeLine")), None)
    fresh_step = next((row for row in diff.get("freshTimeline") or [] if row.get("step") == fresh_step_no), None)
    doc: dict[str, Any] = {
        "purpose": "Phase 4 first decisive divergence selected from collector_state_transition_diff_s00_vs_fresh.",
        "plan": str(REPO / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputDiff": str(DIFF),
        "divergence": {
            "id": "D1_final_seq5_acceptance_response_diff",
            "hypothesisId": "H3_collector_server_state",
            "kind": first.get("kind"),
            "priority": first.get("priority"),
            "s00Step": s00_step_no,
            "freshStep": fresh_step_no,
            "s00": {
                "runtimeLine": first.get("s00RuntimeLine"),
                "evidence": {
                    "runtimeTrace": (s00_step or {}).get("evidence", {}).get("runtimeTrace"),
                    "collectorDecode": (s00_step or {}).get("evidence", {}).get("collectorDecode"),
                    "bundlePayloadDecode": (s00_step or {}).get("evidence", {}).get("bundlePayloadDecode"),
                },
                "urlPath": (s00_step or {}).get("urlPath"),
                "request": (s00_step or {}).get("request"),
                "handlers": ((s00_step or {}).get("response") or {}).get("handlers"),
                "successStatuses": (((s00_step or {}).get("response") or {}).get("partsSummary") or {}).get("successStatuses"),
            },
            "fresh": {
                "label": first.get("freshLabel"),
                "sourcePath": (fresh_step or {}).get("sourcePath"),
                "urlPath": (fresh_step or {}).get("urlPath"),
                "request": (fresh_step or {}).get("request"),
                "materialMeta": (fresh_step or {}).get("materialMeta"),
                "handlers": ((fresh_step or {}).get("response") or {}).get("handlers"),
                "successStatuses": (((fresh_step or {}).get("response") or {}).get("partsSummary") or {}).get("successStatuses"),
            },
            "comparison": comparison,
            "whyDecisive": (
                "All compared collector-visible steps before final seq5 have equal handler sequences and success-status shapes. "
                "The first divergence appears at logical seq5/rsc6: s00 returns success status oIIoIooo|0 and then additional _px3/score handlers, "
                "while the selected fresh no-browser run returns oIIoIooo|-1 without the post-success handler tail. "
                "This makes final seq5 acceptance the first collector-visible decisive divergence; earlier request payload hashes differ, "
                "but they did not change handler sequence/status before this point in the selected contrast pair."
            ),
            "falsifiableCondition": (
                "If a future state-transition diff finds an earlier response handler/cookie/session divergence before final seq5, this D1 selection is superseded. "
                "If a minimal fresh-session experiment changes one pre-seq5 state transition and final seq5 advances from oIIoIooo|-1 to oIIoIooo|0 or another later stage, H3 gains support."
            ),
            "minimalExperimentPlan": {
                "doNotRunYetWithoutReview": True,
                "experimentClass": "pre_seq5_state_transition_replay",
                "constraint": "Use fresh session; do not transplant s00 accepted payload/body; modify exactly one state transition identified by a narrower pre-seq5 lineage audit.",
                "nextRequiredAuditBeforeExperiment": str(PROTO / "hypothesis_reframe/pre_seq5_state_lineage_detail.json"),
                "stageProgressionMetric": [
                    "oIIoIooo|-1 -> oIIoIooo|0",
                    "oIIoIooo|-1 -> response without rejection but with cookie/token handler change",
                    "no regression in earlier equal handler sequence",
                ],
            },
        },
        "checks": {
            "inputDiffExists": DIFF.exists(),
            "hasCandidate": bool(first),
            "candidateKindAllowedByPlan": first.get("kind") in {"response_handler_diff", "success_status_diff"},
            "s00AndFreshRequestSeqRscEqual": bool(
                comparison
                and (comparison.get("requestShape") or {}).get("seqEqual") is True
                and (comparison.get("requestShape") or {}).get("rscEqual") is True
            ),
            "firstDivergenceAtFinalSeq5": first.get("s00RuntimeLine") == 933 and first.get("freshLabel") == "seq5",
        },
        "next": {
            "recommended": "Build a narrower pre_seq5_state_lineage_detail.json before any fresh experiment, because D1 is at the final acceptance boundary and the causal pre-state must be isolated.",
            "artifact": str(PROTO / "hypothesis_reframe/pre_seq5_state_lineage_detail.json"),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": doc["checks"], "divergence": doc["divergence"]["id"], "next": doc["next"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
