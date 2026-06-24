#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/server_observable_state_inventory.json"


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


def mutation_items(step: dict[str, Any]) -> list[dict[str, Any]]:
    resp = step.get("response") or {}
    ps = resp.get("partsSummary") or {}
    return ps.get("mutations") or resp.get("mutations") or []


def observable_mutations(model: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for step in model:
        req = step.get("request") or {}
        for idx, mut in enumerate(mutation_items(step)):
            handler = mut.get("handler")
            name = mut.get("name")
            value = mut.get("value")
            value_sha = mut.get("valueSha256") or (sha(value) if value is not None else None)
            semantic = None
            if name in {"_px3", "_pxde"}:
                semantic = "cookie_token"
            elif handler == "IooIIo":
                semantic = "pow_challenge"
            elif handler == "IooIoI":
                semantic = "ci_or_challenge_token"
            elif handler in {"oIIoIoII", "ooooII", "oIIoIoIo", "IoIIII", "IooIoo", "oIIooIoo", "IIoIoI"}:
                semantic = "session_scalar"
            elif handler == "oIIoIooo":
                semantic = "acceptance_status"
            out.append({
                "step": step.get("step"),
                "label": step.get("label"),
                "urlPath": step.get("urlPath"),
                "seq": req.get("seq"),
                "rsc": req.get("rsc"),
                "handlerIndex": idx,
                "handler": handler,
                "name": name,
                "semantic": semantic,
                "valueSha256": value_sha,
                "fieldCount": mut.get("fieldCount"),
            })
    return out


def request_consumption(model: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for step in model:
        req = step.get("request") or {}
        out.append({
            "step": step.get("step"),
            "label": step.get("label"),
            "urlPath": step.get("urlPath"),
            "seq": req.get("seq"),
            "rsc": req.get("rsc"),
            "outerFieldsPresent": {
                "uuid": bool(req.get("uuid")),
                "ci": bool(req.get("ci")),
                "cs": bool(req.get("hasCs")) if "hasCs" in req else bool(req.get("cs")),
                "sid": bool(req.get("hasSid")) if "hasSid" in req else bool(req.get("sid")),
                "vid": bool(req.get("hasVid")) if "hasVid" in req else bool(req.get("vid")),
                "cts": bool(req.get("hasCts")) if "hasCts" in req else bool(req.get("cts")),
                "pc": bool(req.get("pc")),
                "payload": bool(req.get("payloadSha256")),
            },
            "requestDigests": {
                "payloadSha256": req.get("payloadSha256"),
                "bodySha256": req.get("bodySha256"),
                "pc": req.get("pc"),
                "ci": req.get("ci"),
            },
            "materialMeta": step.get("materialMeta"),
        })
    return out


def count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        value = str(item.get(key))
        out[value] = out.get(value, 0) + 1
    return out


def main() -> int:
    status = load("output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json")
    diff = load("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json")
    model = load("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json")
    state_lineage = load("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json")
    encoded = load("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json")
    cookie_gap = load("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json")

    s00_model = model.get("s00Model") or []
    fresh_model = model.get("freshModel") or []
    s00_mutations = observable_mutations(s00_model)
    fresh_mutations = observable_mutations(fresh_model)
    s00_consumption = request_consumption(diff.get("s00Timeline") or [])
    fresh_consumption = request_consumption(diff.get("freshTimeline") or [])

    # Inventory state variables that are both server-observable and final-request-consumed.
    final_lineage = state_lineage.get("requestValueLineage") or []
    final_consumed = []
    for row in final_lineage:
        final_consumed.append({
            "requestField": row.get("requestField"),
            "source": row.get("source"),
            "consumedBy": row.get("consumedBy"),
            "equal": row.get("equal"),
            "controlCoverage": row.get("existingControlCoverage"),
        })

    # Handler shape inventory.
    s00_classes = (model.get("sequenceClasses") or {}).get("s00") or []
    fresh_classes = (model.get("sequenceClasses") or {}).get("fresh") or []
    sequence_alignment = {
        "s00Length": len(s00_classes),
        "freshLength": len(fresh_classes),
        "classSequencesEqualUpToFreshLength": s00_classes[: len(fresh_classes)] == fresh_classes,
        "s00Classes": s00_classes,
        "freshClasses": fresh_classes,
    }

    inventory = {
        "purpose": "Inventory server-observable state and its proven consumption into final seq5 request surfaces.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "hypothesisReframeStatus": p("output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json"),
            "collectorStateTransitionDiff": p("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
            "serverStateTransitionValueModel": p("output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json"),
            "serverStateValueToRequestLineage": p("output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json"),
            "encodedPayloadPcFormDiffMap": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
            "cookieSessionLineageGap": p("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
        },
        "observableMutations": {
            "s00": s00_mutations,
            "fresh": fresh_mutations,
            "counts": {
                "s00BySemantic": count_by(s00_mutations, "semantic"),
                "freshBySemantic": count_by(fresh_mutations, "semantic"),
                "s00ByHandler": count_by(s00_mutations, "handler"),
                "freshByHandler": count_by(fresh_mutations, "handler"),
            },
        },
        "requestConsumption": {
            "s00": s00_consumption,
            "fresh": fresh_consumption,
            "finalSeq5ConsumedFields": final_consumed,
        },
        "sequenceAlignment": sequence_alignment,
        "observableGaps": [
            {
                "id": "O1_final_response_handler_extra_s00",
                "status": "observed_at_acceptance_boundary",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
                "fact": "s00 final seq5 response has success plus extra token handlers; fresh final seq5 has rejection.",
                "actionability": "response consequence, not pre-request mutation.",
            },
            {
                "id": "O2_final_request_decoded_equal_outer_diff",
                "status": "pre-request_surface_boundary",
                "evidence": p("output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json"),
                "fact": "final decoded JSON/base equal; outer/session/pc/marker differ.",
                "actionability": "coupled tuple, not single field under current evidence.",
            },
            {
                "id": "O3_parent_bridge",
                "status": "browser_observable_not_request_cookie",
                "evidence": p("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
                "fact": "parent bridge exists in s00 and is absent in fresh, but line933/fresh seq5 have no Cookie header.",
                "checks": cookie_gap.get("checks"),
                "actionability": "requires mapping bridge state to payload generation or Microsoft context.",
            },
        ],
        "decision": {
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "reason": "Inventory confirms the remaining pre-request observable boundary is a coupled outer/session/encoder tuple; browser bridge remains unmapped to a request input. No single fresh-session mutation is justified.",
            "nextArtifact": p("output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json"),
            "nextScript": str(ROOT / "tools/build_bridge_to_payload_context_audit.py"),
        },
        "checks": {
            "statusRequiresThisArtifact": (status.get("currentDecision") or {}).get("nextRecommendedArtifact") == str(OUT),
            "hasS00ObservableMutations": bool(s00_mutations),
            "hasFreshObservableMutations": bool(fresh_mutations),
            "hasFinalConsumedFields": bool(final_consumed),
            "decodedJsonEqual": (encoded.get("checks") or {}).get("decodedJsonEqual") is True,
            "finalConsumedFieldsAllDiffer": all(item.get("equal") is False for item in final_consumed),
            "parentBridgeGapKnown": (cookie_gap.get("checks") or {}).get("s00HasParentCookieBridgeBeforeSuccess") is True,
            "parentBridgeNotCookieHeader": (cookie_gap.get("checks") or {}).get("line933RequestHasNoCookieHeader") is True,
            "readyForFreshExperiment": False,
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "checks": inventory["checks"], "decision": inventory["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
