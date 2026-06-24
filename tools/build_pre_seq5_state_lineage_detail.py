#!/usr/bin/env python3
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json"


def load_json(rel):
    p = ROOT / rel
    with p.open() as f:
        return json.load(f)


def load_jsonl(rel, lo, hi):
    p = ROOT / rel
    rows = []
    with p.open() as f:
        for line_no, line in enumerate(f, 1):
            if lo <= line_no <= hi:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    obj = {"_parseError": True, "rawPreview": line[:300]}
                rows.append((line_no, obj))
    return rows


def sha256_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def preview(value, n=160):
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value[:n]


def compact_event(line_no, obj):
    data = obj.get("data", {}) if isinstance(obj.get("data"), dict) else {}
    kind = obj.get("kind") or obj.get("type") or obj.get("event")
    out = {"line": line_no, "kind": kind}
    if kind in {"request", "response"} or obj.get("kind") in {"request", "response"}:
        out.update({
            "status": obj.get("status"),
            "method": obj.get("method"),
            "url": obj.get("url"),
            "bodyLen": obj.get("body_len") or obj.get("bodyLen"),
            "hasBody": bool(obj.get("body")),
            "headerKeys": sorted((obj.get("headers") or {}).keys())[:30],
        })
        return out
    if kind == "hsprotect.main.jl.item":
        raw = data.get("raw")
        out.update({
            "handlerKey": data.get("handlerKey"),
            "index": data.get("index"),
            "rawPreview": preview(raw, 220),
            "rawSha256": sha256_text(raw),
        })
    elif kind == "hsprotect.main.jl.dispatch":
        out.update({
            "handlerKey": data.get("handlerKey"),
            "args": data.get("args"),
        })
    elif kind == "hsprotect.Xn.trigger":
        out.update({
            "channel": data.get("channel"),
            "argsPreview": preview(data.get("args"), 300),
        })
    elif kind == "window.message.recv":
        raw = data.get("data")
        parsed = None
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
        out.update({
            "eventOrigin": data.get("eventOrigin"),
            "dataType": data.get("dataType"),
            "messageType": parsed.get("type") if isinstance(parsed, dict) else None,
            "messageName": parsed.get("name") if isinstance(parsed, dict) else None,
            "valueSha256": sha256_text(parsed.get("value")) if isinstance(parsed, dict) else None,
            "rawPreview": preview(raw, 260),
        })
    elif kind and "captcha.qs.start" in kind:
        out.update({k: data.get(k) for k in ["from", "to", "mask", "len", "prefix", "salt", "target"]})
    elif kind == "hsprotect.captcha.pow.hit":
        out.update({k: data.get(k) for k in ["i", "value", "sha256", "target"]})
    elif kind and ("wasm" in kind or "tbr9" in kind or "captcha" in kind):
        keys = [
            "arg", "key", "valueType", "nqKey", "nqValue", "nInput", "ngValue",
            "retPreview", "activityType", "from", "to", "target", "i", "value",
        ]
        for k in keys:
            if k in data:
                out[k] = preview(data.get(k), 240)
        if "value" in data and "value" not in out:
            out["valuePreview"] = preview(data.get("value"), 240)
            out["valueSha256"] = sha256_text(data.get("value"))
    elif kind in {"hsprotect.main.$c.yc", "hsprotect.main.jc.yc", "hsprotect.main.tf.enter", "hsprotect.main.tf.prepc", "hsprotect.main.tf.payload"}:
        activities = data.get("activities")
        inp = data.get("input")
        out.update({
            "activityType": data.get("activityType"),
            "activityCount": len(activities) if isinstance(activities, list) else None,
            "inputKeys": data.get("inputKeys") or (sorted(inp.keys()) if isinstance(inp, dict) else None),
            "dataSha256": sha256_text(data),
        })
    return out


def summarize_runtime_window():
    rel = "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl"
    rows = load_jsonl(rel, 635, 933)
    network = []
    counts = Counter()
    for line_no, obj in rows:
        kind = obj.get("kind")
        typ = obj.get("type")
        counts[kind or typ or "unknown"] += 1
        if kind in {"request", "response"}:
            network.append(compact_event(line_no, obj))
    return {
        "source": str(ROOT / rel),
        "lineRange": [635, 933],
        "eventCounts": dict(counts),
        "networkEvents": network,
        "observedCollectorSeq4ResponseLine": 635,
        "observedCaptchaHeadRequestLine": next((e["line"] for e in network if e.get("method") == "HEAD" and "captcha.hsprotect.net" in (e.get("url") or "")), None),
        "observedCaptchaHeadResponseLine": next((e["line"] for e in network if e.get("status") == 200 and "captcha.hsprotect.net" in (e.get("url") or "")), None),
        "observedFinalSeq5RequestLine": 933,
    }


def summarize_js_window():
    rel = "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl"
    rows = load_jsonl(rel, 623, 922)
    counts = Counter(obj.get("kind") for _, obj in rows)
    wanted = []
    for line_no, obj in rows:
        kind = obj.get("kind")
        data = obj.get("data", {}) if isinstance(obj.get("data"), dict) else {}
        include = (
            kind in {
                "hsprotect.main.fp.enter",
                "hsprotect.main.om.decode",
                "hsprotect.main.jl.enter",
                "hsprotect.main.jl.item",
                "hsprotect.main.jl.dispatch",
                "hsprotect.Xn.trigger",
                "window.message.recv",
                "hsprotect.main.$c.yc",
                "hsprotect.main.jc.yc",
                "hsprotect.main.tf.enter",
                "hsprotect.main.tf.prepc",
                "hsprotect.main.tf.payload",
            }
            or (kind and ("captcha" in kind or "wasm" in kind or "tbr9" in kind))
        )
        if include:
            ce = compact_event(line_no, obj)
            if kind == "hsprotect.main.jl.item" and data.get("handlerKey") not in {"IooIIo", "IooIoI", "IoooII", "oIIoIIoo", "oIIoIooo"}:
                continue
            wanted.append(ce)
    handlers = [
        e for e in wanted
        if e.get("kind") == "hsprotect.main.jl.item"
    ]
    pow_hit = next((e for e in wanted if e.get("kind") == "hsprotect.captcha.pow.hit"), None)
    return {
        "source": str(ROOT / rel),
        "lineRange": [623, 922],
        "eventCounts": dict(counts),
        "importantEvents": wanted,
        "seq4DecodedHandlerItems": handlers,
        "observedPowHit": pow_hit,
        "observedParentBridgeLines": [
            e for e in wanted
            if e.get("kind") == "window.message.recv" and e.get("messageType") in {"cookie", "rendered"}
        ],
        "payloadGenerationLines": [
            e for e in wanted
            if e.get("kind") in {"hsprotect.main.$c.yc", "hsprotect.main.jc.yc", "hsprotect.main.tf.enter", "hsprotect.main.tf.prepc", "hsprotect.main.tf.payload"}
        ],
    }


def get_combo_material(combo):
    seq5 = combo.get("results", {}).get("seq5", {})
    mat = seq5.get("material", {})
    resp = seq5.get("response", {})
    dec = seq5.get("decoded", {})
    return {
        "source": combo_path,
        "inputs": combo.get("inputs"),
        "checks": combo.get("checks"),
        "seq5Material": mat,
        "seq5Response": resp,
        "seq5DecodedSummary": {
            "handlers": dec.get("handlers"),
            "successStatuses": dec.get("successStatuses"),
            "doLen": len(dec.get("do") or []) if isinstance(dec.get("do"), list) else None,
        },
    }


def summarize_fresh_lineage():
    progression = load_json("output/protocol_reverse/fresh_bundle_progression_probe/fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json")
    pow_json = load_json("output/protocol_reverse/pow_response/pow_response_fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json")
    wasm = load_json("output/protocol_reverse/wasm/compute_wasm_ng_nq_once_forced_overlap_final_9acd2880_1781279930_with_ng.json")
    combo = load_json("output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json")
    step = (progression.get("steps") or [{}])[0]
    pow_result = (pow_json.get("results") or [{}])[0]
    return {
        "seq4AfterOverlap": {
            "source": str(ROOT / "output/protocol_reverse/fresh_bundle_progression_probe/fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json"),
            "request": step.get("request"),
            "decodedHandlers": step.get("decoded", {}).get("handlers"),
            "successStatuses": step.get("decoded", {}).get("successStatuses"),
            "stateAfterSubset": {k: progression.get("finalState", {}).get(k) for k in ["uuid", "p1", "sid", "jo", "cs", "vid", "cts", "ci", "powChallenge"]},
        },
        "pow": {
            "source": str(ROOT / "output/protocol_reverse/pow_response/pow_response_fresh_bundle_progression_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279943.json"),
            "raw": pow_result.get("raw"),
            "i": pow_result.get("i"),
            "value": pow_result.get("value"),
            "target": pow_result.get("target"),
            "matchesTarget": pow_result.get("matchesTarget"),
        },
        "wasmNgNq": {
            "source": str(ROOT / "output/protocol_reverse/wasm/compute_wasm_ng_nq_once_forced_overlap_final_9acd2880_1781279930_with_ng.json"),
            "inputs": wasm.get("inputs"),
            "checks": wasm.get("checks"),
            "ngLen": wasm.get("output", {}).get("ngLen"),
            "ngSha256": sha256_text(wasm.get("output", {}).get("ngValue")),
            "nqLen": wasm.get("output", {}).get("nqLen"),
            "nqSha256": sha256_text(wasm.get("output", {}).get("nqValue")),
        },
        "finalSeq5": {
            "source": str(ROOT / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json"),
            "inputs": combo.get("inputs"),
            "checks": combo.get("checks"),
            "material": combo.get("results", {}).get("seq5", {}).get("material"),
            "decoded": {
                "handlers": combo.get("results", {}).get("seq5", {}).get("decoded", {}).get("handlers"),
                "successStatuses": combo.get("results", {}).get("seq5", {}).get("decoded", {}).get("successStatuses"),
            },
        },
    }


def summarize_boundaries():
    encoded = load_json("output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json")
    split = load_json("output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json")
    h2_head = load_json("output/protocol_reverse/goal_audit/h2_first_failure_head_delay_control_audit.json")
    head = load_json("output/protocol_reverse/goal_audit/captcha_head_delay_control_audit.json")
    cookie = load_json("output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json")
    fresh_tail = load_json("output/protocol_reverse/goal_audit/h2_fresh_tail_strongest_control_audit.json")
    fresh_tail_only = load_json("output/protocol_reverse/goal_audit/h2_fresh_tail_only_control_audit.json")
    fresh_tail_inner = load_json("output/protocol_reverse/goal_audit/h2_fresh_tail_inner_uuid_control_audit.json")
    aeax = load_json("output/protocol_reverse/goal_audit/aeax_control_after_post_retry_audit.json")
    return {
        "decodedEqualButEncodedDiffers": {
            "source": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json"),
            "checks": encoded.get("checks"),
            "seq5": {
                "payloadEqual": encoded.get("seq5", {}).get("payloadEqual"),
                "pcEqual": encoded.get("seq5", {}).get("pcEqual"),
                "bodyEqual": encoded.get("seq5", {}).get("bodyEqual"),
                "formDiffKeys": encoded.get("seq5", {}).get("formDiffKeys"),
                "activityCompare": encoded.get("seq5", {}).get("activityCompare"),
            },
            "conclusion": encoded.get("conclusion"),
        },
        "exactPayloadPcFreshOuterNotSufficient": {
            "source": str(ROOT / "output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json"),
            "checks": split.get("checks"),
            "seq5Response": split.get("seq5Response"),
            "conclusion": split.get("conclusion"),
        },
        "headTimingH2ResponseOrderNotSufficient": {
            "sources": [
                str(ROOT / "output/protocol_reverse/goal_audit/h2_first_failure_head_delay_control_audit.json"),
                str(ROOT / "output/protocol_reverse/goal_audit/captcha_head_delay_control_audit.json"),
            ],
            "h2HeadChecks": h2_head.get("checks"),
            "captchaHeadChecks": head.get("checks"),
            "conclusions": [h2_head.get("conclusion"), head.get("conclusion")],
        },
        "parentBridgeGapNotCookieHeader": {
            "source": str(ROOT / "output/protocol_reverse/goal_audit/cookie_session_lineage_gap_audit.json"),
            "checks": cookie.get("checks"),
            "conclusion": cookie.get("conclusion"),
        },
        "freshPowWasmTailNotSufficient": {
            "sources": [
                str(ROOT / "output/protocol_reverse/goal_audit/h2_fresh_tail_strongest_control_audit.json"),
                str(ROOT / "output/protocol_reverse/goal_audit/h2_fresh_tail_only_control_audit.json"),
                str(ROOT / "output/protocol_reverse/goal_audit/h2_fresh_tail_inner_uuid_control_audit.json"),
                str(ROOT / "output/protocol_reverse/goal_audit/aeax_control_after_post_retry_audit.json"),
            ],
            "freshTailStrongestChecks": fresh_tail.get("checks"),
            "freshTailOnlyChecks": fresh_tail_only.get("checks"),
            "freshTailInnerChecks": fresh_tail_inner.get("checks"),
            "aeaxChecks": aeax.get("checks"),
            "conclusions": [
                fresh_tail.get("conclusion"),
                fresh_tail_only.get("conclusion"),
                fresh_tail_inner.get("conclusion"),
                aeax.get("conclusion"),
            ],
        },
    }


combo_path = str(ROOT / "output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_9acd2880-6677-11f1-8a37-62666cc2b93d_1781279945.json")


def main():
    selected = load_json("output/protocol_reverse/hypothesis_reframe/selected_contrast_pair.json")
    matrix = load_json("output/protocol_reverse/hypothesis_reframe/hypothesis_matrix.json")
    diff = load_json("output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json")
    div = load_json("output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json")
    runtime = summarize_runtime_window()
    js = summarize_js_window()
    fresh = summarize_fresh_lineage()
    boundaries = summarize_boundaries()

    candidates = [
        {
            "id": "B1_encoded_payload_session_binding",
            "status": "supported_boundary_not_root_cause_proven",
            "evidence": [
                boundaries["decodedEqualButEncodedDiffers"]["source"],
                boundaries["exactPayloadPcFreshOuterNotSufficient"]["source"],
                str(ROOT / "output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
            ],
            "observedFacts": [
                "seq5 decoded activities equal in forced-overlap audit while encoded payload/body/pc differ",
                "exact s00 payload+pc with fresh outer returned do=[] and no success handler",
                "current D1 is seq5/rsc6 acceptance response diff with different payload/body sha256",
            ],
            "falsification": "A fresh session reaches later stage after reproducing one pre-seq5 encoded/session state transition without adding browser-only bridge state.",
            "allowedNextTest": "Only after this lineage identifies which encoded/session input is generated before line933 and missing from pure protocol.",
        },
        {
            "id": "B2_browser_parent_bridge_or_in_memory_state",
            "status": "supported_gap_not_simple_cookie_header",
            "evidence": [
                str(ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl") + ":688-689",
                boundaries["parentBridgeGapNotCookieHeader"]["source"],
            ],
            "observedFacts": [
                "s00 has parent bridge cookie messages for _px3/_pxde before line933",
                "cookie_session_lineage_gap audit says both s00 line933 and fresh seq5 have no Cookie header",
                "therefore the observed bridge gap is not proven to be a missing collector Cookie request header",
            ],
            "falsification": "A pure protocol run reproduces equivalent parent-bridge-consumed state or proves no pre-line933 payload input depends on it and still diverges.",
            "allowedNextTest": "Trace whether bridge-mutated values enter payload generation, session counters, or Microsoft risk context before constructing a network experiment.",
        },
        {
            "id": "B3_captcha_lifecycle_runtime_state",
            "status": "partially_supported_head_timing_not_sufficient",
            "evidence": [
                str(ROOT / "output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl") + ":692,712",
                str(ROOT / "output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl") + ":690-919",
                boundaries["headTimingH2ResponseOrderNotSufficient"]["sources"][0],
                boundaries["headTimingH2ResponseOrderNotSufficient"]["sources"][1],
            ],
            "observedFacts": [
                "s00 has captcha rendered, POW worker, WASM Ng/NQ, TBR9/PX561 generation before line933",
                "fresh has offline POW and WASM Ng/NQ evidence",
                "HEAD request, observed delay, h2 multiplexing, and response order are not sufficient per existing controls",
                "fresh POW/WASM tail controls are not sufficient per existing h2_fresh_tail audits",
            ],
            "falsification": "If pre_seq5 payload inputs and server response state are fully reproduced without browser captcha lifecycle and still fail, this boundary remains only contextual.",
            "allowedNextTest": "Do not test HEAD/timing again; only test a lifecycle-derived state input if lineage shows it is absent from pure protocol material.",
        },
        {
            "id": "B4_collector_server_expected_state_after_seq4",
            "status": "supported_by_D1_location_requires_more_lineage",
            "evidence": [
                str(ROOT / "output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
                str(ROOT / "output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
            ],
            "observedFacts": [
                "collector-visible compared steps match until final seq5 response boundary",
                "fresh final seq5 receives oIIoIooo|-1 while s00 receives success status oIIoIooo|0 plus extra handlers",
            ],
            "falsification": "A fresh session with the same collector-visible pre-seq5 state but different browser-only lineage succeeds, or vice versa.",
            "allowedNextTest": "Only after identifying one server-expected state transition that can be changed without moving multiple variables.",
        },
    ]

    checks = {
        "selectedContrastPairExists": bool(selected),
        "hypothesisPrimaryH3": matrix.get("decision", {}).get("primaryNextHypothesis") == "H3_collector_server_state",
        "diffFirstCandidateFinalSeq5": diff.get("firstCandidate", {}).get("freshLabel") == "seq5",
        "firstDivergenceAtFinalSeq5": div.get("checks", {}).get("firstDivergenceAtFinalSeq5") is True,
        "s00RuntimeWindowHasCaptchaHead": runtime.get("observedCaptchaHeadRequestLine") is not None and runtime.get("observedCaptchaHeadResponseLine") is not None,
        "s00JsWindowHasParentBridge": any(e.get("messageType") == "cookie" for e in js.get("observedParentBridgeLines", [])),
        "s00JsWindowHasPayloadGeneration": len(js.get("payloadGenerationLines", [])) >= 3,
        "freshHasPowSolved": fresh.get("pow", {}).get("matchesTarget") is True,
        "freshHasWasmNgNq": fresh.get("wasmNgNq", {}).get("checks", {}).get("nqValueNonEmpty") is True and fresh.get("wasmNgNq", {}).get("checks", {}).get("ngValueNonEmpty") is True,
        "decodedEqualButEncodedDiffersAuditPresent": boundaries.get("decodedEqualButEncodedDiffers", {}).get("checks", {}).get("seq5EncodedPayloadDiffers") is True,
        "headTimingAlreadyNotSufficient": boundaries.get("headTimingH2ResponseOrderNotSufficient", {}).get("captchaHeadChecks", {}).get("controlPxRejected") is True,
        "freshPowWasmTailAlreadyNotSufficient": boundaries.get("freshPowWasmTailNotSufficient", {}).get("freshTailStrongestChecks", {}).get("usesFreshServerBoundTail") is True and boundaries.get("freshPowWasmTailNotSufficient", {}).get("freshTailStrongestChecks", {}).get("stillRejected") is True,
        "parentBridgeNotCookieHeaderAuditPresent": boundaries.get("parentBridgeGapNotCookieHeader", {}).get("checks", {}).get("line933RequestHasNoCookieHeader") is True,
        "readyForFreshExperiment": False,
    }

    result = {
        "purpose": "Phase 4.5 pre-seq5 lineage detail: narrow D1 final seq5 acceptance divergence before any new fresh-session experiment.",
        "plan": str(ROOT / "docs/pure-protocol-human-hypothesis-plan.md"),
        "inputs": {
            "selectedContrastPair": str(ROOT / "output/protocol_reverse/hypothesis_reframe/selected_contrast_pair.json"),
            "hypothesisMatrix": str(ROOT / "output/protocol_reverse/hypothesis_reframe/hypothesis_matrix.json"),
            "collectorStateTransitionDiff": str(ROOT / "output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json"),
            "firstDecisiveDivergence": str(ROOT / "output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json"),
        },
        "currentDivergence": {
            "id": div.get("divergence", {}).get("id"),
            "checks": div.get("checks"),
            "s00Request": div.get("divergence", {}).get("s00", {}).get("request"),
            "freshRequest": div.get("divergence", {}).get("fresh", {}).get("request"),
        },
        "s00PreSeq5": {
            "runtimeWindow": runtime,
            "jsWindow": js,
        },
        "freshPreSeq5": fresh,
        "boundaryAudits": boundaries,
        "candidateBoundaries": candidates,
        "decision": {
            "readyForFreshExperiment": False,
            "reason": "The first divergence is localized to final seq5 response, but this artifact still identifies multiple supported pre-state boundaries. The next implementation must isolate one concrete state transition before running a fresh-session experiment.",
            "nextArtifact": str(ROOT / "output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json"),
            "requiredBeforeNextArtifact": [
                "Trace line922/line933 payload-generation inputs to network response, cookie bridge, captcha lifecycle, or local in-memory state.",
                "Identify one field or state transition whose source is not reproduced by the current pure-protocol material.",
                "Show why existing controls do not already falsify that transition.",
            ],
        },
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(OUT)
    print(json.dumps({"checks": checks, "candidateCount": len(candidates)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
