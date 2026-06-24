#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"


def load(rel: str) -> Any:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def sha(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode("utf-8")
    else:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def p(rel: str) -> str:
    return str(ROOT / rel)


def state_preview(state: dict[str, Any], key: str) -> Any:
    item = state.get(key) or {}
    return item.get("preview")


def lineage_row(field: str, *, s00_value: Any, fresh_value: Any, source: str, consumed_by: list[str], control: list[str]) -> dict[str, Any]:
    return {
        "requestField": field,
        "s00ValueSha256": sha(s00_value or ""),
        "freshValueSha256": sha(fresh_value or ""),
        "equal": s00_value == fresh_value,
        "s00Preview": str(s00_value or "")[:160],
        "freshPreview": str(fresh_value or "")[:160],
        "source": source,
        "consumedBy": consumed_by,
        "existingControlCoverage": control,
    }


def main() -> int:
    encoded = load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")
    state_gap = load("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json")
    model = load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")
    field_map = load("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json")
    split = load("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json")
    outer = load("output/protocol_reverse/goal_audit/outer_binding_controls_audit.json")
    cookie_gap = load("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json")

    s00_form = encoded.get("s00", {}).get("form", {})
    fresh_form = encoded.get("fresh", {}).get("form", {})
    s00_state = state_gap.get("s00Seq4ResponseState") or {}
    fresh_state = state_gap.get("freshSeq4ResponseState") or {}
    fresh_subset = state_gap.get("freshFinalStateSubset") or {}
    form_diffs = {item["key"]: item for item in encoded.get("formDiffs") or [] if not item.get("equal")}

    rows = [
        lineage_row(
            "uuid",
            s00_value=s00_form.get("uuid"),
            fresh_value=fresh_form.get("uuid"),
            source="session/bootstrap uuid; also used as payload insertion key",
            consumed_by=["form.uuid", "payload marker insertion positions", "tfPayload.meta.cu"],
            control=["stale exact body replay known rejected", "fresh outer with equal decoded activities rejected"],
        ),
        lineage_row(
            "cs",
            s00_value=state_preview(s00_state, "cs"),
            fresh_value=state_preview(fresh_state, "cs"),
            source="seq4 response state",
            consumed_by=["form.cs", "tfPayload.meta.cs"],
            control=["fresh seq4 cs used in selected contrast and still rejected", "s00 exact payload+pc with fresh outer not accepted"],
        ),
        lineage_row(
            "ci",
            s00_value=state_preview(s00_state, "ci"),
            fresh_value=state_preview(fresh_state, "ci"),
            source="seq4 response IooIoI ci value",
            consumed_by=["form.ci", "captcha activity field b19VUy0/ in s00 decoded JSON"],
            control=["decoded JSON equal despite fresh outer ci differing", "fresh outer selected contrast rejected"],
        ),
        lineage_row(
            "sid",
            s00_value=s00_form.get("sidSha256"),
            fresh_value=fresh_form.get("sidSha256"),
            source="session state / sidWithKlJo derived from sid and jo",
            consumed_by=["form.sid"],
            control=["fresh outer selected contrast rejected", "exact payload+pc with fresh outer returns do=[]"],
        ),
        lineage_row(
            "p1",
            s00_value=s00_form.get("p1"),
            fresh_value=fresh_form.get("p1"),
            source="bootstrap/session p1",
            consumed_by=["form.p1", "iframe session id lineage"],
            control=["fresh outer selected contrast rejected", "template marker not sufficient"],
        ),
        lineage_row(
            "vid",
            s00_value=s00_form.get("vid"),
            fresh_value=fresh_form.get("vid"),
            source="bootstrap/session vid",
            consumed_by=["form.vid", "tfPayload.meta.vid"],
            control=["fresh outer selected contrast rejected"],
        ),
        lineage_row(
            "cts",
            s00_value=s00_form.get("cts"),
            fresh_value=fresh_form.get("cts"),
            source="bootstrap/session cts",
            consumed_by=["form.cts"],
            control=["fresh outer selected contrast rejected"],
        ),
        lineage_row(
            "pc",
            s00_value=s00_form.get("pc"),
            fresh_value=fresh_form.get("pc"),
            source="encoder output from serialized decoded text + uuid/tag/key material",
            consumed_by=["form.pc", "collector encoded payload binding"],
            control=["exact s00 payload+pc with fresh outer returns do=[]", "decoded JSON/base equal but pc differs"],
        ),
        lineage_row(
            "marker",
            s00_value=encoded.get("s00", {}).get("marker"),
            fresh_value=encoded.get("fresh", {}).get("marker"),
            source="jo/qi marker derived from server state",
            consumed_by=["payload marker insertion"],
            control=["template marker not sufficient", "baseAfterMarkerRemovalEqual=true"],
        ),
    ]

    remaining = [
        {
            "id": "L1_outer_session_tuple",
            "fields": ["uuid", "cs", "ci", "sid", "p1", "vid", "cts"],
            "status": "coherent_tuple_required_but_not_single_field",
            "evidence": [p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")],
            "reason": "All these fields differ as a coherent session tuple. Existing controls show stale payload/pc with fresh outer and fresh outer with equal decoded JSON are not accepted, but do not isolate one field.",
        },
        {
            "id": "L2_pc_marker_uuid_encoder_binding",
            "fields": ["pc", "marker", "uuid", "payload"],
            "status": "encoded_binding_remaining",
            "evidence": [p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")],
            "reason": "Decoded text/base are equal; payload differs only by marker insertion and uuid-derived insertion positions, while pc differs. Existing controls eliminate static transplant and marker-only variants.",
        },
        {
            "id": "L3_server_acceptance_state",
            "fields": ["collector server-side expected state"],
            "status": "not_directly_observable_in_request",
            "evidence": [p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")],
            "reason": "Final seq5 request semantic content is equal but response differs, so a server-side expected-state variable remains possible and not directly represented by decoded activities.",
        },
    ]

    result = {
        "purpose": "Trace final seq5 outer/form/encoder fields back to server/session state and decide whether a single field can be tested.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "encodedPayloadPcFormDiffMap": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "serverExpectedStatePreSeq5Gap": p("output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"),
            "serverStateTransitionValueModel": p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
            "line922DynamicFieldSourceMap": p("output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json"),
            "payloadPcSplitControl": p("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
            "outerBindingControls": p("output/protocol_reverse/goal_audit/outer_binding_controls_audit.json"),
            "cookieSessionLineageGap": p("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
        },
        "requestValueLineage": rows,
        "remainingBoundaries": remaining,
        "controlCoverage": {
            "payloadPcSplit": split.get("checks"),
            "outerBinding": outer.get("checks"),
            "cookieBridge": cookie_gap.get("checks"),
            "encodedDiff": encoded.get("checks"),
            "serverModel": model.get("checks"),
            "line922Map": field_map.get("checks"),
        },
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "The remaining candidates are coherent tuples or server-internal expected state, not one evidenced request-field transition. A fresh experiment would currently change multiple coupled variables.",
            "nextArtifact": p("output/protocol_reverse/hypothesis_reframe/final_boundary_decision_matrix.json"),
            "nextScript": str(ROOT / "tools/build_final_boundary_decision_matrix.py"),
        },
        "checks": {
            "encodedDiffInputReady": (encoded.get("checks") or {}).get("decodedJsonEqual") is True,
            "hasFormDiffs": bool(form_diffs),
            "hasRequestValueLineage": bool(rows),
            "allRowsDiffer": all(row["equal"] is False for row in rows),
            "hasOuterSessionTupleBoundary": True,
            "hasEncoderBindingBoundary": True,
            "hasServerAcceptanceStateBoundary": True,
            "payloadPcSplitControlRejected": (split.get("checks") or {}).get("seq5PayloadAndPcExactS00") is True and (split.get("checks") or {}).get("seq5NoOIIoIooo") is True,
            "outerBindingControlsRejected": (outer.get("checks") or {}).get("freshOuterFreshMarkerActivitiesEqualRejected") is True,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": result["checks"], "decision": result["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
