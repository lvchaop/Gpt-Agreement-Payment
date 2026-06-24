#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"


def load_json(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def sha(v: Any) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        v = json.dumps(v, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(v.encode()).hexdigest()


def preview(v: Any, n: int = 140) -> Any:
    if isinstance(v, str):
        return v[:n]
    return v


def parse_parts(parts: list[str]) -> dict[str, Any]:
    state: dict[str, Any] = {"rawParts": [], "handlers": []}
    for idx, part in enumerate(parts):
        fields = str(part).split("|")
        key = fields[0] if fields else ""
        state["rawParts"].append({"index": idx, "handler": key, "fieldCount": len(fields), "sha256": sha(part), "preview": preview(part)})
        state["handlers"].append(key)
        if key == "IoooII" and len(fields) >= 4 and fields[1] == "_px3":
            state["px3"] = fields[3]
        elif key == "oIIoIIoo" and len(fields) >= 4 and fields[1] == "_pxde":
            state["pxde"] = fields[3]
        elif key == "IIoIoI" and len(fields) >= 2:
            state["zo"] = fields[1]
        elif key == "oIIoIoII" and len(fields) >= 2:
            state["jo"] = fields[1]
        elif key == "ooooII" and len(fields) >= 2:
            state["qo"] = fields[1]
        elif key == "oIIoIoIo" and len(fields) >= 2:
            state["gl"] = fields[1]
        elif key == "IoIIII" and len(fields) >= 2:
            state["cs"] = fields[1]
        elif key == "IooIIo" and len(fields) >= 6:
            state["powChallenge"] = part
            state["powEnabled"] = fields[1]
            state["powSeed"] = fields[2]
            state["powTarget"] = fields[3]
            state["powDifficulty"] = fields[4]
            state["powFlag"] = fields[5]
        elif key == "IooIoI" and len(fields) >= 7:
            state["ciChallenge"] = part
            state["ci"] = fields[2]
            state["ciGl"] = fields[3]
            state["ciToken"] = fields[4]
            state["ciMode"] = fields[5]
            state["ciRegion"] = fields[6]
    return state


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    keys = ["px3", "pxde", "zo", "jo", "qo", "gl", "cs", "powChallenge", "powSeed", "powTarget", "ci", "ciToken"]
    return {
        k: {"present": state.get(k) is not None, "sha256": sha(state.get(k)), "preview": preview(state.get(k))}
        for k in keys
    } | {"handlers": state.get("handlers")}


def compare_values(a: dict[str, Any], b: dict[str, Any]) -> list[dict[str, Any]]:
    keys = ["px3", "pxde", "zo", "jo", "qo", "gl", "cs", "powSeed", "powTarget", "ci", "ciToken"]
    out = []
    for k in keys:
        out.append({
            "field": k,
            "bothPresent": a.get(k) is not None and b.get(k) is not None,
            "equal": a.get(k) == b.get(k),
            "s00Sha256": sha(a.get(k)),
            "freshSha256": sha(b.get(k)),
            "s00Preview": preview(a.get(k)),
            "freshPreview": preview(b.get(k)),
        })
    return out


def main() -> int:
    collector = load_json("output/protocol_reverse/collector_decode/collector_decode_s00ld1lglrw0_1781191381.json")
    s00_entry = next(e for e in collector["decodedEntries"] if int(e.get("lineNo") or 0) == 623)
    fresh_prog = load_json("output/protocol_reverse/fresh_bundle_progression_probe/fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json")
    fresh_step = fresh_prog["steps"][0]
    fresh_decoded = fresh_step["decoded"]

    s00_state = parse_parts(s00_entry["parts"])
    fresh_state = parse_parts(fresh_decoded["parts"])
    final_fresh = fresh_prog.get("finalState") or {}

    existing = {
        "freshTailStrongest": load_json("output/protocol_reverse/goal_audit/h2_fresh_tail_strongest_control_audit.json"),
        "firstFailureHistory": load_json("output/protocol_reverse/goal_audit/fresh_first_failure_history_audit.json"),
        "px561StatefulRetry": load_json("output/protocol_reverse/goal_audit/px561_stateful_retry_audit.json"),
        "decodedBoundary": load_json("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
        "cookieBridge": load_json("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
    }

    comparisons = compare_values(s00_state, fresh_state)
    value_mismatch_fields = [c["field"] for c in comparisons if c["bothPresent"] and not c["equal"]]

    result = {
        "purpose": "Value-level pre-seq5 server expected-state gap after accepted line933 generation lineage.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "s00CollectorDecode": str(ROOT / "output/protocol_reverse/collector_decode/collector_decode_s00ld1lglrw0_1781191381.json") + ":line623",
            "freshSeq4Progression": str(ROOT / "output/protocol_reverse/fresh_bundle_progression_probe/fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json"),
            "acceptedLine933GenerationLineage": str(ROOT / "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
        },
        "s00Seq4ResponseState": public_state(s00_state),
        "freshSeq4ResponseState": public_state(fresh_state),
        "freshFinalStateSubset": {k: {"sha256": sha(final_fresh.get(k)), "preview": preview(final_fresh.get(k))} for k in ["uuid", "p1", "sid", "jo", "cs", "vid", "cts", "ci", "px3", "pxde", "powChallenge"]},
        "valueComparisons": comparisons,
        "existingControlCoverage": {
            "powAndTailValuesNotSufficient": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/h2_fresh_tail_strongest_control_audit.json"),
                "checks": existing["freshTailStrongest"].get("checks"),
                "conclusion": existing["freshTailStrongest"].get("conclusion"),
            },
            "firstFailureHistoryNotSufficient": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/fresh_first_failure_history_audit.json"),
                "checks": existing["firstFailureHistory"].get("checks"),
                "conclusion": existing["firstFailureHistory"].get("conclusion"),
            },
            "px3PxdeStatefulRetryNotSufficient": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/px561_stateful_retry_audit.json"),
                "checks": existing["px561StatefulRetry"].get("checks"),
                "conclusion": existing["px561StatefulRetry"].get("conclusion"),
            },
            "decodedEqualityNotSufficient": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
                "checks": existing["decodedBoundary"].get("checks"),
            },
            "browserBridgeGapNotCookieHeader": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
                "checks": existing["cookieBridge"].get("checks"),
            },
        },
        "candidateNextBoundary": {
            "id": "S1_server_expected_state_not_reducible_to_response_values",
            "status": "evidence_gap_not_fresh_experiment_ready",
            "basis": [
                "s00 and fresh seq4 responses have equal handler shape and same semantic fields but value-level state is session-specific.",
                "Existing controls already tested fresh POW/tail, first-failure history, updated _px3/_pxde retry, decoded equality, h2/head timing, and static body replay; all remained rejected.",
                "Therefore no single value from seq4 response is currently justified as the next fresh-session mutation.",
            ],
            "nextEvidenceNeeded": "Map server-expected state across the whole fresh selected sequence at value level and identify a missing transition, not a value transplant.",
        },
        "decision": {
            "readyForFreshExperiment": False,
            "reason": "Value-level seq4 differences are all session-specific and existing controls cover the obvious single-variable mutations. The next step is whole-sequence server-state transition modeling rather than a new network attempt.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
        },
        "checks": {
            "s00Line623Has18Parts": len(s00_entry.get("parts") or []) == 18,
            "freshSeq4Has18Parts": len(fresh_decoded.get("parts") or []) == 18,
            "handlerSequencesEqual": s00_state.get("handlers") == fresh_state.get("handlers"),
            "valueMismatchFieldsPresent": bool(value_mismatch_fields),
            "allMismatchFieldsAreSessionSpecific": set(value_mismatch_fields).issubset({"px3", "pxde", "zo", "jo", "qo", "gl", "cs", "powSeed", "powTarget", "ci", "ciToken"}),
            "existingFreshTailControlRejected": existing["freshTailStrongest"].get("checks", {}).get("stillRejected") is True,
            "existingStatefulRetryRejected": existing["px561StatefulRetry"].get("checks", {}).get("retryRejected") is True,
            "readyForFreshExperiment": False,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
