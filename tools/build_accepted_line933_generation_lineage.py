#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            row["_line"] = line_no
            rows.append(row)
    return rows


def sha(value: Any) -> str:
    if isinstance(value, str):
        data = value.encode()
    else:
        data = json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def short(value: Any, n: int = 180) -> Any:
    if isinstance(value, str):
        return value[:n]
    return value


def js_line(rows: list[dict[str, Any]], line_no: int) -> dict[str, Any]:
    for row in rows:
        if row["_line"] == line_no:
            return row
    raise RuntimeError(f"missing js line {line_no}")


def activity_summary(activity: dict[str, Any]) -> dict[str, Any]:
    d = activity.get("d") or {}
    return {
        "type": activity.get("t"),
        "fieldCount": len(d),
        "fieldKeys": list(d.keys()),
        "sha256": sha(activity),
        "dynamicFieldHashes": {
            k: sha(v)
            for k, v in d.items()
            if k in {
                "GUVjT1wnbn4=",  # injected _px3
                "SlpwEAw5eSc=",  # current href
                "FUFvS1Mga38=",  # uuid-like captcha field
                "fg4ERDtuD3I=",  # large token/en field
                "QS07ZwRKPlU=",  # timestamp-like field
                "X08lRRkjIXQ=",  # qi/jo-like field
                "b19VUy0/",      # ci-like field in captcha activity
            }
        },
        "dynamicFieldPreview": {
            k: short(v)
            for k, v in d.items()
            if k in {
                "GUVjT1wnbn4=",
                "SlpwEAw5eSc=",
                "FUFvS1Mga38=",
                "fg4ERDtuD3I=",
                "QS07ZwRKPlU=",
                "X08lRRkjIXQ=",
                "b19VUy0/",
            }
        },
    }


def delta(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for idx, (a, b) in enumerate(zip(before, after)):
        da = a.get("d") or {}
        db = b.get("d") or {}
        added = {k: db[k] for k in db.keys() - da.keys()}
        changed = {k: {"before": da[k], "after": db[k]} for k in da.keys() & db.keys() if da[k] != db[k]}
        out.append({
            "index": idx,
            "type": b.get("t"),
            "addedKeys": list(added.keys()),
            "added": {k: {"preview": short(v), "sha256": sha(v)} for k, v in added.items()},
            "changedKeys": list(changed.keys()),
            "changed": {k: {"beforeSha256": sha(v["before"]), "afterSha256": sha(v["after"])} for k, v in changed.items()},
        })
    return out


def event_digest(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data") or {}
    return {
        "line": row["_line"],
        "kind": row.get("kind"),
        "dataKeys": list(data.keys()) if isinstance(data, dict) else [],
        "activityType": data.get("activityType") if isinstance(data, dict) else None,
        "inputSha256": sha(data.get("input")) if isinstance(data, dict) and "input" in data else None,
        "outputSha256": sha(data.get("output")) if isinstance(data, dict) and "output" in data else None,
        "inputKeys": data.get("inputKeys") if isinstance(data, dict) else None,
        "outputKeys": data.get("outputKeys") if isinstance(data, dict) else None,
    }


def main() -> int:
    rows = read_jsonl(JS)
    pre = read_json(ROOT / "output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json")
    combo = read_json(ROOT / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json")
    encoded = read_json(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json")
    cookie_gap = read_json(ROOT / "output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json")
    px_retry = read_json(ROOT / "output/protocol_reverse/goal_audit/px561_stateful_retry_audit.json")
    outer = read_json(ROOT / "output/protocol_reverse/goal_audit/outer_binding_controls_audit.json")
    h2 = read_json(ROOT / "output/protocol_reverse/goal_audit/h2_dual_activity_equal_control_audit.json")
    h2_seq6 = read_json(ROOT / "output/protocol_reverse/goal_audit/h2_seq6_response_before_seq5_body_control_audit.json")

    y_px561 = js_line(rows, 917)
    y_captcha = js_line(rows, 918)
    trigger = js_line(rows, 919)
    tf_enter = js_line(rows, 920)
    tf_prepc = js_line(rows, 921)
    tf_payload = js_line(rows, 922)

    enter_activities = (tf_enter.get("data") or {}).get("activities") or []
    prepc_activities = (tf_prepc.get("data") or {}).get("activities") or []
    payload_activities = (tf_payload.get("data") or {}).get("activities") or []

    material = combo.get("results", {}).get("seq5", {}).get("material", {})
    meta = material.get("meta") or {}
    material_checks = material.get("checks") or {}
    fresh_state = material.get("freshState") or {}

    s00_px3_values = [
        ((a.get("d") or {}).get("GUVjT1wnbn4="))
        for a in payload_activities
        if isinstance((a.get("d") or {}).get("GUVjT1wnbn4="), str)
    ]
    unique_s00_px3_hashes = sorted({sha(v) for v in s00_px3_values})

    lineage = {
        "purpose": "Trace accepted s00 line922/line933 payload generation inputs and decide whether a single fresh-session experiment is justified.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "jsTrace": str(JS),
            "preSeq5Lineage": str(ROOT / "output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json"),
            "selectedFreshCombo": str(ROOT / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json"),
            "encodedBoundary": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
        },
        "s00GenerationChain": {
            "px561Yc": event_digest(y_px561),
            "captchaJcYc": event_digest(y_captcha),
            "captchaActivityTrigger": {
                "line": trigger["_line"],
                "kind": trigger.get("kind"),
                "channel": (trigger.get("data") or {}).get("channel"),
            },
            "tfEnter": {
                "line": 920,
                "activityCount": len(enter_activities),
                "activities": [activity_summary(a) for a in enter_activities],
            },
            "tfPrepc": {
                "line": 921,
                "pc": (tf_prepc.get("data") or {}).get("pc"),
                "cs": (tf_prepc.get("data") or {}).get("cs"),
                "serializedLen": len((tf_prepc.get("data") or {}).get("serialized") or ""),
                "serializedSha256": sha((tf_prepc.get("data") or {}).get("serialized") or ""),
                "enterToPrepcDelta": delta(enter_activities, prepc_activities),
            },
            "tfPayload": {
                "line": 922,
                "meta": (tf_payload.get("data") or {}).get("meta"),
                "qi": (tf_payload.get("data") or {}).get("qi"),
                "marker": (tf_payload.get("data") or {}).get("marker"),
                "markerLen": (tf_payload.get("data") or {}).get("markerLen"),
                "pc": (tf_payload.get("data") or {}).get("pc"),
                "cs": (tf_payload.get("data") or {}).get("cs"),
                "serializedLen": len((tf_payload.get("data") or {}).get("serialized") or ""),
                "serializedSha256": sha((tf_payload.get("data") or {}).get("serialized") or ""),
                "payloadLen": len((tf_payload.get("data") or {}).get("payload") or ""),
                "payloadSha256": sha((tf_payload.get("data") or {}).get("payload") or ""),
                "prepcActivitiesEqualPayloadActivities": prepc_activities == payload_activities,
                "activities": [activity_summary(a) for a in payload_activities],
            },
        },
        "observedImportantInputs": {
            "prepcInjectsPx3IntoEveryActivity": len(unique_s00_px3_hashes) == 1 and len(s00_px3_values) == len(payload_activities),
            "s00InjectedPx3Sha256": unique_s00_px3_hashes[0] if unique_s00_px3_hashes else None,
            "freshStatePx3Sha256": sha(fresh_state.get("px3")) if fresh_state.get("px3") else None,
            "selectedFreshFinalSeq5MaterialChecks": material_checks,
            "selectedFreshFinalSeq5SourceFlags": {
                k: meta.get(k)
                for k in [
                    "formOuterSource",
                    "payloadSource",
                    "pcSource",
                    "bodySource",
                    "aeaxSource",
                    "bztSource",
                    "stackSource",
                    "tailSource",
                    "innerUuidSource",
                    "nonPxActivitySource",
                    "payloadUuidSource",
                    "pcUuidSource",
                    "markerSource",
                ]
            },
        },
        "existingControlsAgainstSingleVariableTests": {
            "decodedEqualityNotSufficient": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
                "checks": encoded.get("checks"),
                "seq5ActivityCompare": (encoded.get("seq5") or {}).get("activityCompare"),
            },
            "px3CookieStatefulRetryNotSufficient": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/px561_stateful_retry_audit.json"),
                "checks": px_retry.get("checks"),
                "conclusion": px_retry.get("conclusion"),
            },
            "parentBridgeNotSimpleCookieHeader": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
                "checks": cookie_gap.get("checks"),
                "conclusion": cookie_gap.get("conclusion"),
            },
            "markerAndOuterBindingNotSingleVariable": {
                "source": str(ROOT / "output/protocol_reverse/goal_audit/outer_binding_controls_audit.json"),
                "checks": outer.get("checks"),
                "conclusion": outer.get("conclusion"),
            },
            "decodedBodyAndH2TimingNotSufficient": {
                "sources": [
                    str(ROOT / "output/protocol_reverse/goal_audit/h2_dual_activity_equal_control_audit.json"),
                    str(ROOT / "output/protocol_reverse/goal_audit/h2_seq6_response_before_seq5_body_control_audit.json"),
                ],
                "h2DualChecks": h2.get("checks"),
                "h2Seq6BeforeSeq5Checks": h2_seq6.get("checks"),
                "conclusions": [h2.get("conclusion"), h2_seq6.get("conclusion")],
            },
        },
        "candidateStateTransitions": [
            {
                "id": "T1_prepc_px3_injection",
                "observedInS00": "line921 adds GUVjT1wnbn4=(_px3) to all four activities before line922 serialization",
                "evidence": [str(JS) + ":921-922"],
                "status": "not_sufficient_as_single_variable",
                "why": "Existing px561_stateful_retry and exact decoded-activity controls already used updated protocol _px3/_pxde or held decoded activities equal and still rejected.",
            },
            {
                "id": "T2_tf_payload_serialized_payload_pc_binding",
                "observedInS00": "line921 serialized sha256 2104e303... yields pc 5793951654710718; line922 payload sha256 81b5774f...",
                "evidence": [str(JS) + ":921-922", str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json")],
                "status": "supported_boundary_but_not_static_replay",
                "why": "Exact payload+pc and exact whole body replay controls are rejected; this is a coherent live state boundary, not a portable static artifact.",
            },
            {
                "id": "T3_browser_parent_bridge_state",
                "observedInS00": "pre-seq5 parent bridge carries _px3/_pxde and post-success challenge_success; line933 itself has no Cookie header",
                "evidence": [str(ROOT / "output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json")],
                "status": "supported_gap_not_yet_actionable",
                "why": "Current evidence identifies the bridge gap but does not prove which pre-line933 payload input or collector expected-state transition it changes.",
            },
            {
                "id": "T4_collector_server_expected_state",
                "observedInS00": "final seq5/rsc6 response differs while decoded request equality, h2 timing, head timing, fresh tail, and static body replay are not sufficient",
                "evidence": [
                    str(ROOT / "output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
                    str(ROOT / "output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json"),
                ],
                "status": "highest_priority_next_static_audit",
                "why": "No current line922 material single-variable is justified for a fresh experiment; next evidence should isolate server expected-state immediately before seq5.",
            },
        ],
        "decision": {
            "readyForFreshExperiment": False,
            "reason": "Line922 generation inputs are now traced enough to reject the obvious single-variable experiments (_px3 injection, decoded activity equality, marker/outer, h2/head/tail). The remaining supported boundary is coherent collector/server expected state or browser bridge state not mapped to a single request input.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json"),
            "nextWork": [
                "Compare decoded response-handler state mutations at s00 line623-682 and fresh seq4 response at the value level, not just handler-key level.",
                "Track ci/cs/jo/_px3/_pxde/powChallenge values from seq4 response into final seq5 form and activities.",
                "Identify the first value-level state mismatch that existing controls have not already tested."
            ],
        },
        "checks": {
            "hasPx561YcLine917": y_px561.get("kind") == "hsprotect.main.$c.yc",
            "hasCaptchaJcLine918": y_captcha.get("kind") == "hsprotect.main.jc.yc",
            "hasTfEnterLine920": tf_enter.get("kind") == "hsprotect.main.tf.enter",
            "hasTfPrepcLine921": tf_prepc.get("kind") == "hsprotect.main.tf.prepc",
            "hasTfPayloadLine922": tf_payload.get("kind") == "hsprotect.main.tf.payload",
            "prepcActivitiesEqualPayloadActivities": prepc_activities == payload_activities,
            "prepcInjectsPx3IntoEveryActivity": len(unique_s00_px3_hashes) == 1 and len(s00_px3_values) == len(payload_activities),
            "selectedFreshMaterialHasTemplateDecodedActivities": material_checks.get("payloadEqualsTemplate") is False and material_checks.get("tailSource") == "template",
            "existingDecodedEqualityRejected": encoded.get("checks", {}).get("seq5DecodedNotEqualS00") is False,
            "existingPx3StatefulRetryRejected": px_retry.get("checks", {}).get("retryRejected") is True,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(lineage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": lineage["checks"], "decision": lineage["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
