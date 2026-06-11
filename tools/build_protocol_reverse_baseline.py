#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO = Path("/Users/chaopenglv/data/me/Gpt-Agreement-Payment")
OUT_DIR = REPO / "output/protocol_reverse/baseline"


FILES = {
    "plan": REPO / "docs/pure-protocol-human-plan.md",
    "trace_success": REPO / "output/protocol_reverse/trace_classification_ni109xdjp5zp_1780948211.json",
    "trace_summary": REPO / "output/protocol_reverse/trace_classification_summary.json",
    "trace_v2_summary": REPO / "output/protocol_reverse/trace_classification_v2/human_trace_classifier_v2_summary.json",
    "px561_compare": REPO / "output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json",
    "collector_decode_success": REPO / "output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json",
    "collector_decoder_coverage_audit": REPO / "output/protocol_reverse/collector_decode/collector_decoder_coverage_audit.json",
    "collector_request_response_chain_audit": REPO / "output/protocol_reverse/collector_chain/collector_request_response_chain_audit.json",
    "bundle_seq_constructor_audit": REPO / "output/protocol_reverse/bundle_constructor/bundle_seq_constructor_audit_ni109xdjp5zp_1780948211.json",
    "bundle_seq_pc_gap_audit": REPO / "output/protocol_reverse/bundle_constructor/bundle_seq_pc_gap_audit_ni109xdjp5zp_1780948211.json",
    "bundle_pc_static_boundary_audit": REPO / "output/protocol_reverse/bundle_constructor/bundle_pc_static_boundary_audit_ni109xdjp5zp_1780948211.json",
    "bundle_pc_prepc_hook_readiness_audit": REPO / "output/protocol_reverse/bundle_constructor/bundle_pc_prepc_hook_readiness_audit.json",
    "bundle_pc_prepc_observation_j0t8": REPO / "output/protocol_reverse/bundle_constructor/bundle_pc_prepc_observation_j0t8van4qyhm_1781119142.json",
    "pow_success": REPO / "output/protocol_reverse/pow_response/pow_response_ni109xdjp5zp_1780948211.json",
    "risk_success": REPO / "output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json",
    "captcha_state_fields": REPO / "output/protocol_reverse/source_offsets/captcha_state_submit_fields.json",
    "captcha_remaining_fields": REPO / "output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.json",
    "collector_handlers": REPO / "output/protocol_reverse/px561_collector_handlers/px561_collector_handlers_ni109.json",
    "captcha_bridge_audit": REPO / "output/protocol_reverse/source_offsets/captcha_bridge_static_audit.json",
    "px561_yc_flatten_order_audit": REPO / "output/protocol_reverse/source_offsets/px561_yc_flatten_order_audit.json",
    "tbr9_success_boundary_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_success_boundary_audit.json",
    "px561_serializer_boundary_audit": REPO / "output/protocol_reverse/source_offsets/px561_serializer_boundary_audit.json",
    "success_tf_yc_trace_gap_audit": REPO / "output/protocol_reverse/source_offsets/success_tf_yc_trace_gap_audit.json",
    "px561_preyc_static_reconstruction": REPO / "output/protocol_reverse/source_offsets/px561_preyc_static_reconstruction.json",
    "ws_nq_return_boundary_audit": REPO / "output/protocol_reverse/source_offsets/ws_nq_return_boundary_audit.json",
    "tbr9_decode_context_integrity_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_decode_context_integrity_audit.json",
    "tbr9_rewrite_delete_paths_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_rewrite_delete_paths_audit.json",
    "tbr9_neighbor_rebind_paths_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_neighbor_rebind_paths_audit.json",
    "tbr9_handoff_call_target_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_handoff_call_target_audit.json",
    "tbr9_pre_i_visible_writes_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_pre_i_visible_writes_audit.json",
    "tbr9_pre_i_side_effect_calls_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_pre_i_side_effect_calls_audit.json",
    "tbr9_observation_hook_readiness_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_observation_hook_readiness_audit.json",
    "tbr9_runtime_observation_20260611_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_runtime_observation_20260611_audit.json",
    "tbr9_aeax_negative_control_b0_20260611": REPO / "output/protocol_reverse/source_offsets/tbr9_aeax_negative_control_b0_20260611.json",
    "tbr9_activity_uniqueness_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_activity_uniqueness_audit.json",
    "tbr9_minimal_yc_tf_experiment": REPO / "output/protocol_reverse/source_offsets/tbr9_minimal_yc_tf_experiment.json",
    "tbr9_queue_to_tf_static_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_queue_to_tf_static_audit.json",
    "tbr9_vs_ut_decode_boundary_audit": REPO / "output/protocol_reverse/source_offsets/tbr9_vs_ut_decode_boundary_audit.json",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: Path) -> str:
    return str(path.relative_to(REPO))


def main() -> None:
    missing_files = [rel(path) for path in FILES.values() if not path.exists()]
    if missing_files:
        raise SystemExit(f"missing required evidence files: {missing_files}")

    trace_success = load_json(FILES["trace_success"])
    trace_summary = load_json(FILES["trace_summary"])
    trace_v2_summary = load_json(FILES["trace_v2_summary"])
    px561 = load_json(FILES["px561_compare"])
    collector_decoder_coverage = load_json(FILES["collector_decoder_coverage_audit"])
    collector_chain = load_json(FILES["collector_request_response_chain_audit"])
    bundle_seq_constructor = load_json(FILES["bundle_seq_constructor_audit"])
    bundle_seq_pc_gap = load_json(FILES["bundle_seq_pc_gap_audit"])
    bundle_pc_static_boundary = load_json(FILES["bundle_pc_static_boundary_audit"])
    bundle_pc_prepc_hook_readiness = load_json(FILES["bundle_pc_prepc_hook_readiness_audit"])
    bundle_pc_prepc_observation_j0t8 = load_json(FILES["bundle_pc_prepc_observation_j0t8"])
    pow_success = load_json(FILES["pow_success"])
    risk_success = load_json(FILES["risk_success"])
    state_fields = load_json(FILES["captcha_state_fields"])
    remaining_fields = load_json(FILES["captcha_remaining_fields"])
    collector_handlers = load_json(FILES["collector_handlers"])
    captcha_bridge = load_json(FILES["captcha_bridge_audit"])
    yc_flatten = load_json(FILES["px561_yc_flatten_order_audit"])
    tbr9_boundary = load_json(FILES["tbr9_success_boundary_audit"])
    serializer_boundary = load_json(FILES["px561_serializer_boundary_audit"])
    success_trace_gap = load_json(FILES["success_tf_yc_trace_gap_audit"])
    preyc_static = load_json(FILES["px561_preyc_static_reconstruction"])
    ws_nq_boundary = load_json(FILES["ws_nq_return_boundary_audit"])
    tbr9_decode_context = load_json(FILES["tbr9_decode_context_integrity_audit"])
    tbr9_rewrite_delete = load_json(FILES["tbr9_rewrite_delete_paths_audit"])
    tbr9_neighbor_rebind = load_json(FILES["tbr9_neighbor_rebind_paths_audit"])
    tbr9_handoff_call_target = load_json(FILES["tbr9_handoff_call_target_audit"])
    tbr9_pre_i_visible_writes = load_json(FILES["tbr9_pre_i_visible_writes_audit"])
    tbr9_pre_i_side_effect_calls = load_json(FILES["tbr9_pre_i_side_effect_calls_audit"])
    tbr9_observation_hook_readiness = load_json(FILES["tbr9_observation_hook_readiness_audit"])
    tbr9_runtime_observation = load_json(FILES["tbr9_runtime_observation_20260611_audit"])
    tbr9_aeax_negative_control_b0 = load_json(FILES["tbr9_aeax_negative_control_b0_20260611"])
    tbr9_activity_uniqueness = load_json(FILES["tbr9_activity_uniqueness_audit"])
    tbr9_minimal_yc_tf = load_json(FILES["tbr9_minimal_yc_tf_experiment"])
    tbr9_queue_to_tf = load_json(FILES["tbr9_queue_to_tf_static_audit"])
    tbr9_vs_ut_decode = load_json(FILES["tbr9_vs_ut_decode_boundary_audit"])

    success_d = px561["success"]["activity"]["d"]
    full_success_runs = [r for r in trace_v2_summary["runs"] if r["stage"] == "full_success_decoded"]
    tf_failure_runs = [r for r in trace_v2_summary["runs"] if r["stage"] == "tf_payload_failure_stage"]
    fu_visible = next(
        (r for r in captcha_bridge["suFuExpressions"] if r["expr"] == "Fu visible key t(v(-543,-542))"),
        None,
    )
    yc_tbr9_context = yc_flatten["targetContext"]["TBR9Ugl7emA="]
    tbr9_context = tbr9_boundary["targetKeyContext"]["TBR9Ugl7emA="]
    key_status = {
        "KVkYX28zG2o=": {
            "successValue": success_d.get("KVkYX28zG2o="),
            "staticEvidence": [
                "captcha_state_submit_fields.json: K[n(\"HGASKTZabC1xSx9T\")] = Hn[challengeTime]",
                "captcha_px561_remaining_fields.json: D submit extra key assigns d[key] = jz",
                "main.beautified.js:4504 decodes IooIoI rSplit[1] by ne(..., Vl)",
                "main.beautified.js:4640 sets Vl = 10",
            ],
            "currentStatus": "closed for ni109 success sample: IooIoI encoded delay XOR 10 yields 4948; all runtime branches not exhaustively proven",
        },
        "Ew9iCVZkZD4=": {
            "successValue": success_d.get("Ew9iCVZkZD4="),
            "staticEvidence": [
                "captcha_state_submit_fields.json: K[key] = Hn[fakeToken]",
                "captcha.beautified.js:8154 assigns fakeToken = secondArg.token",
                "captcha.beautified.js:11031 builds secondArg[token] = yz",
                "main.beautified.js:4504 splits IooIoI rRaw by '_' and passes rSplit[0] into Hc/Zc path",
                "captcha_bridge_static_audit.json: Fu visible key decodes to PX762, closing the previously stale slice/PX762 bridge confusion",
            ],
            "currentStatus": "producer located; PX762 bridge corrected/closed statically; remaining boundary is value propagation through the success callback path",
        },
        "TBR9Ugl7emA=": {
            "successValue": success_d.get("TBR9Ugl7emA="),
            "staticEvidence": [
                "captcha_px561_remaining_fields.json: t(v(-540,-543)) decodes to TBR9Ugl7emA=",
                "captcha.beautified.js:11083 assigns r[key] = _s()",
                "captcha.beautified.js:9638-9644 shows _s() returns a boolean expression",
                "px561_yc_flatten_order_audit.json: final order places TBR9 after AEAx, contradicting simple direct assignment",
                "tbr9_success_boundary_audit.json: decoded success response has oIIoIooo|0 but does not contain TBR9 key/value",
                "tbr9_decode_context_integrity_audit.json: decodedText contains TBR9 and exact decodedText re-encodes to observed payload",
                "tbr9_neighbor_rebind_paths_audit.json: adjacent Rs/instantiating hypothesis excluded; Rs candidates do not equal final 127-byte TBR9",
                "tbr9_handoff_call_target_audit.json: exact D/Ts handoff resolves to i(PX561,r) -> main $c(PX561,r) -> Yc(r,'PX561') -> Rc",
                "tbr9_pre_i_visible_writes_audit.json: visible exact-source writes before i(PX561,r) only write TBR9 as _s() boolean, with no later visible pre-i TBR rewrite",
                "tbr9_pre_i_side_effect_calls_audit.json: visible range from r[TBR9]=_s() to i(PX561,r) has no delete/defineProperty/non-handoff call receiving r",
                "tbr9_observation_hook_readiness_audit.json: worktree now has source-verified hooks for captcha pre-i PX561 plus main $c/jc Yc and tf.enter/tf.payload observation",
                "tbr9_runtime_observation_20260611_audit.json: decisive runtime sample has pre-i PX561 TBR9 undefined/absent, $c.yc input/output without TBR9, and final PX561 tf.payload without TBR9 but with AEAx",
                "tbr9_aeax_negative_control_b0_20260611.json: second AEAx-only observation has pre-i/$c.yc/final tf.payload AEAx with no TBR9, cookie bridge ok, but CreateAccount returns error.code=1059 field=humanCaptcha",
                "tbr9_activity_uniqueness_audit.json: decoded request line 308 has exactly one TBR9-bearing activity, index 2 type PX561; no cross-activity attribution mismatch",
                "tbr9_minimal_yc_tf_experiment.json: visible pre-i object through emulated Yc/ds/tf keeps TBR9 boolean and cannot create final 127-byte string",
                "tbr9_queue_to_tf_static_audit.json: visible Rc/ds queue through np[un]/np[ln] to tf has no TBR9 producer and no PX561 special normalizer",
                "tbr9_vs_ut_decode_boundary_audit.json: success line 308 has TBR9 in decodedText before JSON parse; marker/base artifacts and visible ut/Vs semantic insertion are unsupported",
            ],
            "currentStatus": "still P0 for HUMAN accepted success: accepted ni109 decoded PX561 contains TBR9 and AEAx, while fk8 and b0 runtime observations are AEAx-only negative controls that reach cookie bridge/CreateAccount but fail with error.code=1059 / field=humanCaptcha; next target is accepted redirectUrl + captcha.pre_i_px561 + main.$c.yc + main.tf.payload in the same run",
        },
    }

    ioo = collector_handlers["IooIoI"]["hcInputsBeforeRuntimeDecode"]
    encoded_delay = ioo.get("encodedDelaySource")
    decoded_delay = "".join(chr(ord(ch) ^ 10) for ch in encoded_delay) if encoded_delay else None

    result = {
        "objective": "完全纯协议解析 + 复现 HUMAN 成功包",
        "evidenceFiles": {name: rel(path) for name, path in FILES.items()},
        "traceBaseline": {
            "successTrace": {
                "path": trace_success["trace"],
                "status": trace_success["status"],
                "checks": trace_success["checks"],
                "counts": trace_success["counts"],
            },
            "summaryEntries": trace_summary,
            "v2": {
                "runCount": trace_v2_summary["runCount"],
                "observationControlCount": trace_v2_summary.get("observationControlCount", 0),
                "fullSuccessRuns": [
                    {
                        "run": r["run"],
                        "stage": r["stage"],
                        "checks": r["checks"],
                        "counts": r["counts"],
                        "sourceVersion": r["sourceVersion"],
                    }
                    for r in full_success_runs
                ],
                "tfPayloadFailureControls": [
                    {
                        "run": r["run"],
                        "stage": r["stage"],
                        "counts": r["counts"],
                        "sourceVersion": r["sourceVersion"],
                    }
                    for r in tf_failure_runs
                ],
                "observationControls": trace_v2_summary.get("observationControls", []),
            },
            "warning": "Use human_trace_classifier_v2_summary.json and trace_classification_ni109...json as the current authoritative success/failure evidence index.",
        },
        "collectorPowRiskBaseline": {
            "collectorSuccessHandler": trace_success["checks"].get("decoded_oIIoIooo_0"),
            "collectorDecoderCoverage": {
                "checks": collector_decoder_coverage["checks"],
                "rows": collector_decoder_coverage["rows"],
                "conclusion": collector_decoder_coverage["conclusion"],
                "limitation": collector_decoder_coverage["limitation"],
            },
            "collectorRequestResponseChain": {
                "runs": [
                    {
                        "run": r["run"],
                        "role": r["role"],
                        "successHandlerCount": len([e for e in r["decodedFpEntries"] if e.get("hasSuccessHandler")]),
                        "runtimePowHitCount": r["pow"].get("runtimeHitCount"),
                        "decodedPowResultCount": len([e for e in r["decodedFpEntries"] if e.get("hasPowResult")]),
                        "bundlePx561Count": len([x for x in (r["bundlePayloadDecode"].get("rows") or []) if x.get("hasPX561")]),
                        "px561Tbr9Count": len([x for x in (r["bundleActivityMatches"].get("px561") or []) if x.get("hasTBR9")]),
                        "successHandlerTimeLinks": r["successHandlerTimeLinks"],
                    }
                    for r in collector_chain["runs"]
                ],
                "conclusion": collector_chain["conclusion"],
                "limitation": collector_chain["limitation"],
            },
            "bundleSeqConstructor": {
                "checks": bundle_seq_constructor["checks"],
                "requests": [
                    {
                        "requestLine": r["requestLine"],
                        "seq": r["seq"],
                        "rawPayloadMatch": r["rawPayloadMatch"],
                        "rawPcMatch": r["rawPcMatch"],
                        "parsedPayloadMatch": r["parsedPayloadMatch"],
                        "parsedPcMatch": r["parsedPcMatch"],
                        "parsedSerializedMatchesRaw": r["parsedSerializedMatchesRaw"],
                        "jsonItemCount": r["jsonItemCount"],
                    }
                    for r in bundle_seq_constructor["requests"]
                ],
                "conclusion": bundle_seq_constructor["conclusion"],
                "limitation": bundle_seq_constructor["limitation"],
            },
            "bundleSeqPcGap": {
                "checks": bundle_seq_pc_gap["checks"],
                "requests": [
                    {
                        "requestLine": r["requestLine"],
                        "seq": r["seq"],
                        "observedPc": r["observedPc"],
                        "keyCandidateCount": r["keyCandidateCount"],
                        "hitCount": len(r["hits"]),
                        "documentedUuidTagFtResults": r["documentedUuidTagFtResults"],
                    }
                    for r in bundle_seq_pc_gap["requests"]
                ],
                "conclusion": bundle_seq_pc_gap["conclusion"],
                "limitation": bundle_seq_pc_gap["limitation"],
            },
            "bundlePcStaticBoundary": {
                "checks": bundle_pc_static_boundary["checks"],
                "requests": [
                    {
                        "requestLine": r["requestLine"],
                        "seq": r["seq"],
                        "observedPc": r["observedPc"],
                        "rawPayloadMatch": r["rawPayloadMatch"],
                        "rawPcMatch": r["rawPcMatch"],
                        "boundedHitCount": r["boundedHitCount"],
                        "parsedSerializedMatchesRaw": r["parsedSerializedMatchesRaw"],
                        "c1ControlCharCodes": r["c1ControlCharCodes"],
                        "documentedRawSerializedUuidTagFtPc": r["documentedRawSerializedUuidTagFtPc"],
                    }
                    for r in bundle_pc_static_boundary["requests"]
                ],
                "deduction": bundle_pc_static_boundary["deduction"],
                "limitation": bundle_pc_static_boundary["limitation"],
            },
            "bundlePcPrepcHookReadiness": {
                "checks": bundle_pc_prepc_hook_readiness["checks"],
                "sources": [
                    {
                        "path": r["path"],
                        "hasTfEnterPatch": r["hasTfEnterPatch"],
                        "hasTfPrepcPatch": r["hasTfPrepcPatch"],
                        "hasTfPayloadPatch": r["hasTfPayloadPatch"],
                        "patchedPrepcBeforePayload": r["patchedPrepcBeforePayload"],
                        "patchedDeclaresVarPAfterBreakingVarChain": r["patchedDeclaresVarPAfterBreakingVarChain"],
                        "patchedHasBarePAfterCatch": r["patchedHasBarePAfterCatch"],
                    }
                    for r in bundle_pc_prepc_hook_readiness["rows"]
                ],
                "conclusion": bundle_pc_prepc_hook_readiness["conclusion"],
                "limitation": bundle_pc_prepc_hook_readiness["limitation"],
            },
            "bundlePcPrepcObservation": {
                "run": bundle_pc_prepc_observation_j0t8["run"],
                "checks": bundle_pc_prepc_observation_j0t8["checks"],
                "createAccountAcceptance": bundle_pc_prepc_observation_j0t8["createAccountAcceptance"],
                "counts": bundle_pc_prepc_observation_j0t8["counts"],
                "requests": [
                    {
                        "requestLine": r["requestLine"],
                        "seq": r["seq"],
                        "observedPc": r["observedPc"],
                        "isAcceptedCreateAccountPhase": r["isAcceptedCreateAccountPhase"],
                        "nextCaptchaOutcome": r["nextCaptchaOutcome"],
                        "prepcPcMatchesObserved": (r.get("prepc") or {}).get("recomputedPcMatchesObserved"),
                        "prepcPayloadSerializedMatch": r.get("prepcPayloadSerializedMatch"),
                        "payloadReplayOk": (r.get("payloadHookReplay") or {}).get("ok"),
                        "payloadReplayMatchesObserved": (r.get("payloadHookReplay") or {}).get("payloadMatchesObserved"),
                        "hookMarkerDecodedTextMatchesPayloadSerialized": (r.get("observedPayloadDecodeWithHookMarker") or {}).get("decodedTextMatchesPayloadHookSerialized"),
                        "contains": (r.get("payloadHook") or {}).get("contains"),
                    }
                    for r in bundle_pc_prepc_observation_j0t8["requests"]
                ],
                "conclusion": bundle_pc_prepc_observation_j0t8["conclusion"],
            },
            "pow": pow_success["results"][0],
            "riskVerifyCounts": risk_success["counts"],
        },
        "px561Baseline": {
            "successSource": px561["success"]["source"],
            "successLine": px561["success"]["line"],
            "fieldCount": px561["success"]["fieldCount"],
            "state": px561["success"]["state"],
            "keyStatus": key_status,
            "iooIoI": {
                "collectorPart": collector_handlers["IooIoI"]["collectorPart"],
                "rSplit": ioo.get("rSplit"),
                "encodedDelaySource": encoded_delay,
                "decodedDelayByXor10": decoded_delay,
                "hashPrefix": ioo.get("observedHashPrefix"),
            },
            "captchaBridge": {
                "fuVisibleKey": fu_visible,
                "conclusions": captcha_bridge["conclusions"],
            },
            "tbr9Boundary": {
                "finalContext": tbr9_context,
                "ycFlattenContext": yc_tbr9_context,
                "findings": tbr9_boundary["findings"],
                "nextEvidenceTargets": tbr9_boundary["nextEvidenceTargets"],
                "ycFlattenConclusions": yc_flatten["conclusions"],
                "serializerBoundaryFindings": serializer_boundary["findings"],
                "serializerBoundaryNextTargets": serializer_boundary["nextEvidenceTargets"],
                "successTraceGapFindings": success_trace_gap["findings"],
                "successTraceGapNextTargets": success_trace_gap["nextEvidenceRequired"],
                "preYcStaticFindings": preyc_static["findings"],
                "preYcStaticNextTargets": preyc_static["nextEvidenceTargets"],
                "wsNqBoundaryFindings": ws_nq_boundary["findings"],
                "wsNqEliminatedHypotheses": ws_nq_boundary["eliminatedHypotheses"],
                "wsNqNextTargets": ws_nq_boundary["nextEvidenceTargets"],
                "decodeContextIntegrity": tbr9_decode_context["bundleDecodeIntegrity"],
                "decodeContextFindings": tbr9_decode_context["findings"],
                "decodeContextNextTargets": tbr9_decode_context["nextEvidenceTargets"],
                "rewriteDeleteFindings": tbr9_rewrite_delete["findings"],
                "rewriteDeleteConclusion": tbr9_rewrite_delete["conclusion"],
                "rewriteDeleteNextTargets": tbr9_rewrite_delete["nextEvidenceTargets"],
                "neighborRebindFindings": tbr9_neighbor_rebind["findings"],
                "neighborRebindConclusion": tbr9_neighbor_rebind["conclusion"],
                "neighborRebindNextTargets": tbr9_neighbor_rebind["nextEvidenceTargets"],
                "neighborRebindRsMatchFinalTbr": tbr9_neighbor_rebind["rsMatchFinalTbr"],
                "handoffCallTargetFindings": tbr9_handoff_call_target["findings"],
                "handoffCallTargetConclusion": tbr9_handoff_call_target["conclusion"],
                "handoffCallTargetNextTargets": tbr9_handoff_call_target["nextEvidenceTargets"],
                "handoffCallTargetDecodedExpressions": tbr9_handoff_call_target["decodedCaptchaHandoff"]["tsCallbackExpressions"],
                "preIVisibleWritesFindings": tbr9_pre_i_visible_writes["findings"],
                "preIVisibleWritesConclusion": tbr9_pre_i_visible_writes["conclusion"],
                "preIVisibleWritesNextTargets": tbr9_pre_i_visible_writes["nextEvidenceTargets"],
                "preIVisibleTargetWriteAudit": tbr9_pre_i_visible_writes["targetWriteAudit"],
                "preISideEffectFindings": tbr9_pre_i_side_effect_calls["findings"],
                "preISideEffectConclusion": tbr9_pre_i_side_effect_calls["conclusion"],
                "preISideEffectChecks": tbr9_pre_i_side_effect_calls["checks"],
                "observationHookReadinessFindings": tbr9_observation_hook_readiness["findings"],
                "observationHookReadinessConclusion": tbr9_observation_hook_readiness["conclusion"],
                "observationHookReadinessChecks": tbr9_observation_hook_readiness["checks"],
                "observationHookReadinessEnv": tbr9_observation_hook_readiness["requiredRuntimeEnv"],
                "runtimeObservationConclusion": tbr9_runtime_observation["conclusion"],
                "runtimeObservationPreI": tbr9_runtime_observation["captcha_pre_i_px561"],
                "runtimeObservationMainYcBridge": tbr9_runtime_observation["main_yc_bridge"],
                "runtimeObservationTfPayloadSummary": tbr9_runtime_observation["tf_payload_summary"],
                "aeaxOnlyNegativeControls": {
                    "fk8": next(
                        (
                            c
                            for c in trace_v2_summary.get("observationControls", [])
                            if c.get("run") == "fk8zn2nqhex1_1781115338"
                        ),
                        None,
                    ),
                    "b0": tbr9_aeax_negative_control_b0,
                },
                "activityUniquenessFindings": tbr9_activity_uniqueness["findings"],
                "activityUniquenessRemainingGap": tbr9_activity_uniqueness["remainingGap"],
                "activityUniquenessTargetHits": tbr9_activity_uniqueness["targetHits"],
                "minimalYcTfExperimentFindings": tbr9_minimal_yc_tf["findings"],
                "minimalYcTfExperimentConclusion": tbr9_minimal_yc_tf["conclusion"],
                "minimalYcTfExperimentChecks": tbr9_minimal_yc_tf["checks"],
                "minimalYcTfSerializedChecks": tbr9_minimal_yc_tf["serializedChecks"],
                "queueToTfFindings": tbr9_queue_to_tf["findings"],
                "queueToTfConclusion": tbr9_queue_to_tf["conclusion"],
                "queueToTfChecks": tbr9_queue_to_tf["checks"],
                "vsUtDecodeFindings": tbr9_vs_ut_decode["findings"],
                "vsUtDecodeConclusion": tbr9_vs_ut_decode["conclusion"],
                "vsUtDecodeChecks": tbr9_vs_ut_decode["checks"],
                "vsUtReplayTotals": tbr9_vs_ut_decode["vsReplayEvidence"]["totals"],
            },
        },
        "nextEvidenceRequired": [
            "P0: Capture an accepted CreateAccount redirectUrl run with captcha.pre_i_px561, main.$c.yc, and main.tf.payload hooks enabled in the same run; the existing fk8 and b0 AEAx-only traces are negative controls and do not remove TBR9 from the HUMAN-success constructor target.",
            "P1: Use the v2 trace classifier output as the canonical sample selector for full_success_decoded, tf_payload_failure_stage, and AEAx-only negative controls.",
            "P2: After the final PX561 field gap closes, build an offline collector body from static producers plus decoded collector state and only then live probe for oIIoIooo|0.",
        ],
        "sourceSnapshots": {
            "stateSubmitRecords": state_fields["records"],
            "stateInitRecords": state_fields["initRecords"],
            "remainingFieldRecords": remaining_fields["records"],
        },
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "protocol_reverse_baseline_latest.json"
    md_path = OUT_DIR / "protocol_reverse_baseline_latest.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Protocol reverse baseline latest",
        "",
        "## evidence files",
        "",
    ]
    for name, path in result["evidenceFiles"].items():
        lines.append(f"- {name}: `{path}`")
    lines += [
        "",
        "## trace baseline",
        "",
        f"- success trace: `{result['traceBaseline']['successTrace']['path']}`",
        f"- status: `{result['traceBaseline']['successTrace']['status']}`",
        f"- v2 run count: `{result['traceBaseline']['v2']['runCount']}`",
        f"- v2 observation controls: `{result['traceBaseline']['v2']['observationControlCount']}`",
        f"- v2 full success runs: `{', '.join(r['run'] for r in result['traceBaseline']['v2']['fullSuccessRuns'])}`",
        f"- warning: {result['traceBaseline']['warning']}",
        "",
        "## collector response decoder coverage",
        "",
        f"- checks: `{result['collectorPowRiskBaseline']['collectorDecoderCoverage']['checks']}`",
        f"- conclusion: {result['collectorPowRiskBaseline']['collectorDecoderCoverage']['conclusion']}",
        f"- limitation: {result['collectorPowRiskBaseline']['collectorDecoderCoverage']['limitation']}",
        "",
        "| run | role | entries | success lines | POW lines | px3 | pxde | ok |",
        "|---|---|---:|---|---|---:|---:|---:|",
    ]
    for row in result["collectorPowRiskBaseline"]["collectorDecoderCoverage"]["rows"]:
        lines.append(
            "| {run} | {role} | {entries} | {success} | {pow} | {px3} | {pxde} | {ok} |".format(
                run=row["run"],
                role=row["role"],
                entries=row.get("entryCount"),
                success=",".join(str(x) for x in row.get("successLines") or []) or "-",
                pow=",".join(str(x) for x in row.get("powLines") or []) or "-",
                px3=len(row.get("px3Lines") or []),
                pxde=len(row.get("pxdeLines") or []),
                ok=row.get("ok"),
            )
        )
    lines += [
        "",
        "## collector request/response chain audit",
        "",
        f"- conclusion: {result['collectorPowRiskBaseline']['collectorRequestResponseChain']['conclusion']}",
        f"- limitation: {result['collectorPowRiskBaseline']['collectorRequestResponseChain']['limitation']}",
        "",
        "| run | role | success handler | runtime POW hit | decoded POW result | bundle PX561 | PX561 TBR9 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in result["collectorPowRiskBaseline"]["collectorRequestResponseChain"]["runs"]:
        lines.append(
            "| {run} | {role} | {success} | {runtime_pow} | {decoded_pow} | {bundle_px} | {tbr9} |".format(
                run=row["run"],
                role=row["role"],
                success=row["successHandlerCount"],
                runtime_pow=row["runtimePowHitCount"],
                decoded_pow=row["decodedPowResultCount"],
                bundle_px=row["bundlePx561Count"],
                tbr9=row["px561Tbr9Count"],
            )
        )
    ni109_chain = next(
        (
            r
            for r in result["collectorPowRiskBaseline"]["collectorRequestResponseChain"]["runs"]
            if r["run"] == "ni109xdjp5zp_1780948211"
        ),
        None,
    )
    if ni109_chain:
        for link in ni109_chain.get("successHandlerTimeLinks") or []:
            prev_bundle = link.get("nearestPrecedingBundleRequest") or {}
            prev_api = link.get("nearestPrecedingApiRequest") or {}
            lines.append(
                "- ni109 success handler line `{line}` time `{time}` follows bundle line `{bline}` seq `{bseq}` by `{bdelta}`s; "
                "preceding api line `{aline}` seq `{aseq}` is `{adelta}`s earlier.".format(
                    line=link.get("successFpLine"),
                    time=link.get("successFpTime"),
                    bline=prev_bundle.get("line"),
                    bseq=prev_bundle.get("seq"),
                    bdelta=link.get("deltaFromPrecedingBundleSeconds"),
                    aline=prev_api.get("line"),
                    aseq=prev_api.get("seq"),
                    adelta=link.get("deltaFromPrecedingApiSeconds"),
                )
            )
    lines += [
        "",
        "## bundle seq=2/3 constructor audit",
        "",
        f"- checks: `{result['collectorPowRiskBaseline']['bundleSeqConstructor']['checks']}`",
        f"- conclusion: {result['collectorPowRiskBaseline']['bundleSeqConstructor']['conclusion']}",
        f"- limitation: {result['collectorPowRiskBaseline']['bundleSeqConstructor']['limitation']}",
        "",
        "| request line | seq | raw payload | raw pc | parsed payload | parsed pc | parsed==raw | json items |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["collectorPowRiskBaseline"]["bundleSeqConstructor"]["requests"]:
        lines.append(
            "| {line} | {seq} | {raw_payload} | {raw_pc} | {parsed_payload} | {parsed_pc} | {parsed_raw} | {items} |".format(
                line=row["requestLine"],
                seq=row["seq"],
                raw_payload=row["rawPayloadMatch"],
                raw_pc=row["rawPcMatch"],
                parsed_payload=row["parsedPayloadMatch"],
                parsed_pc=row["parsedPcMatch"],
                parsed_raw=row["parsedSerializedMatchesRaw"],
                items=row["jsonItemCount"],
            )
        )
    lines += [
        "",
        "## bundle seq=2 pc gap audit",
        "",
        f"- checks: `{result['collectorPowRiskBaseline']['bundleSeqPcGap']['checks']}`",
        f"- conclusion: {result['collectorPowRiskBaseline']['bundleSeqPcGap']['conclusion']}",
        f"- limitation: {result['collectorPowRiskBaseline']['bundleSeqPcGap']['limitation']}",
        "",
        "| request line | seq | observed pc | key candidates | hits | documented rawSerialized uuid:tag:ft |",
        "|---:|---:|---|---:|---:|---|",
    ]
    for row in result["collectorPowRiskBaseline"]["bundleSeqPcGap"]["requests"]:
        documented = next(
            (
                item["pc"]
                for item in row["documentedUuidTagFtResults"]
                if item.get("text") == "rawSerialized" and item.get("key") == "uuid:tag:ft"
            ),
            None,
        )
        lines.append(
            "| {line} | {seq} | `{observed}` | {candidates} | {hits} | `{documented}` |".format(
                line=row["requestLine"],
                seq=row["seq"],
                observed=row["observedPc"],
                candidates=row["keyCandidateCount"],
                hits=row["hitCount"],
                documented=documented,
            )
        )
    lines += [
        "",
        "## bundle pc static-boundary audit",
        "",
        f"- checks: `{result['collectorPowRiskBaseline']['bundlePcStaticBoundary']['checks']}`",
        f"- deduction: {result['collectorPowRiskBaseline']['bundlePcStaticBoundary']['deduction']}",
        f"- limitation: {result['collectorPowRiskBaseline']['bundlePcStaticBoundary']['limitation']}",
        "",
        "| request line | seq | observed pc | raw payload | raw pc | bounded hits | parsed==raw | C1 controls | documented rawSerialized uuid:tag:ft |",
        "|---:|---:|---|---:|---:|---:|---:|---|---|",
    ]
    for row in result["collectorPowRiskBaseline"]["bundlePcStaticBoundary"]["requests"]:
        lines.append(
            "| {line} | {seq} | `{observed}` | {raw_payload} | {raw_pc} | {hits} | {parsed_raw} | `{c1}` | `{documented}` |".format(
                line=row["requestLine"],
                seq=row["seq"],
                observed=row["observedPc"],
                raw_payload=row["rawPayloadMatch"],
                raw_pc=row["rawPcMatch"],
                hits=row["boundedHitCount"],
                parsed_raw=row["parsedSerializedMatchesRaw"],
                c1=",".join(row["c1ControlCharCodes"]) or "-",
                documented=row["documentedRawSerializedUuidTagFtPc"],
            )
        )
    lines += [
        "",
        "## bundle pc prepc hook readiness",
        "",
        f"- checks: `{result['collectorPowRiskBaseline']['bundlePcPrepcHookReadiness']['checks']}`",
        f"- conclusion: {result['collectorPowRiskBaseline']['bundlePcPrepcHookReadiness']['conclusion']}",
        f"- limitation: {result['collectorPowRiskBaseline']['bundlePcPrepcHookReadiness']['limitation']}",
        "",
        "| source | tf.enter | tf.prepc | tf.payload | prepc before payload | var p fixed | bare p bad |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["collectorPowRiskBaseline"]["bundlePcPrepcHookReadiness"]["sources"]:
        lines.append(
            "| `{source}` | {enter} | {prepc} | {payload} | {order} | {varp} | {barep} |".format(
                source=row["path"],
                enter=row["hasTfEnterPatch"],
                prepc=row["hasTfPrepcPatch"],
                payload=row["hasTfPayloadPatch"],
                order=row["patchedPrepcBeforePayload"],
                varp=row["patchedDeclaresVarPAfterBreakingVarChain"],
                barep=row["patchedHasBarePAfterCatch"],
            )
        )
    prepc_obs = result["collectorPowRiskBaseline"]["bundlePcPrepcObservation"]
    lines += [
        "",
        "## bundle pc prepc observation",
        "",
        f"- run: `{prepc_obs['run']}`",
        f"- checks: `{prepc_obs['checks']}`",
        f"- CreateAccount: `{prepc_obs['createAccountAcceptance']}`",
        f"- conclusion: {prepc_obs['conclusion']}",
        "",
        "| request line | seq | observed pc | accepted phase | outcome | prepc pc match | prepc==payload | replay ok | replay payload match | hook-marker decode match | contains |",
        "|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in prepc_obs["requests"]:
        outcome = (row.get("nextCaptchaOutcome") or {}).get("arg")
        contains = row.get("contains") or {}
        contains_text = ",".join(k for k, v in contains.items() if v)
        lines.append(
            "| {line} | {seq} | `{observed}` | {accepted} | {outcome} | {pc} | {prepay} | {replay} | {replay_match} | {decode_match} | {contains} |".format(
                line=row["requestLine"],
                seq=row["seq"],
                observed=row["observedPc"],
                accepted=row["isAcceptedCreateAccountPhase"],
                outcome=outcome or "",
                pc=row["prepcPcMatchesObserved"],
                prepay=row["prepcPayloadSerializedMatch"],
                replay=row["payloadReplayOk"],
                replay_match=row["payloadReplayMatchesObserved"],
                decode_match=row["hookMarkerDecodedTextMatchesPayloadSerialized"],
                contains=contains_text,
            )
        )
    lines += [
        "",
        "## PX561 key status",
        "",
        "| key | success value | status |",
        "|---|---|---|",
    ]
    for key, item in key_status.items():
        value = item["successValue"]
        shown = value if not isinstance(value, str) or len(value) <= 96 else value[:96] + "..."
        lines.append(f"| `{key}` | `{shown}` | {item['currentStatus']} |")
    lines += [
        "",
        "## IooIoI delay evidence",
        "",
        f"- collector part: `{collector_handlers['IooIoI']['collectorPart']}`",
        f"- encoded delay source: `{encoded_delay}`",
        f"- `encodedDelaySource XOR 10`: `{decoded_delay}`",
        f"- success `KVkYX28zG2o=`: `{success_d.get('KVkYX28zG2o=')}`",
        "",
        "## PX762 bridge status",
        "",
        f"- Fu visible key expression: `{fu_visible['expr'] if fu_visible else None}`",
        f"- raw: `{fu_visible['raw'] if fu_visible else None}`",
        f"- decoded: `{fu_visible['decoded'] if fu_visible else None}`",
        "- status: corrected/closed statically; old baseline text saying this decoded to `slice` is stale.",
        "",
        "## TBR9 boundary",
        "",
        f"- final index: `{tbr9_context['index']}`",
        f"- final value type: `{type(tbr9_context['value']).__name__}`",
        f"- Yc flatten audit index: `{yc_tbr9_context['index']}`",
        "- current status: open P0 gap at final PX561 construction/serialization boundary.",
        "",
        "### TBR9 findings",
        "",
    ]
    for item in tbr9_boundary["findings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "### Serializer boundary findings",
        "",
    ]
    for item in serializer_boundary["findings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "### Existing success trace gap findings",
        "",
    ]
    for item in success_trace_gap["findings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "### Pre-Yc static reconstruction findings",
        "",
    ]
    for item in preyc_static["findings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "### Ws.NQ return boundary findings",
        "",
    ]
    for item in ws_nq_boundary["findings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "### TBR9 decode/context integrity findings",
        "",
        f"- decodedTextHasTbrKey: `{tbr9_decode_context['bundleDecodeIntegrity']['decodedTextHasTbrKey']}`",
        f"- replayPayloadMatchesObserved: `{tbr9_decode_context['bundleDecodeIntegrity']['replayPayloadMatchesObserved']}`",
        f"- remainingFields source is ni109 success run: `{tbr9_decode_context['staticDecoderContext']['remainingFieldsSourceIsSuccessRun']}`",
        f"- exact source matches later captured source: `{tbr9_decode_context['staticDecoderContext']['exactNi109SourceMatchesLaterCapturedSource']}`",
    ]
    for item in tbr9_decode_context["findings"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "### TBR9 rewrite/delete findings",
        "",
    ]
    for item in tbr9_rewrite_delete["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_rewrite_delete['conclusion']}")
    lines += [
        "",
        "### TBR9 neighbor rebind findings",
        "",
    ]
    for item in tbr9_neighbor_rebind["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- Rs candidates equal final TBR9: `{tbr9_neighbor_rebind['rsMatchFinalTbr']}`")
    lines.append(f"- conclusion: {tbr9_neighbor_rebind['conclusion']}")
    lines += [
        "",
        "### TBR9 handoff call target findings",
        "",
    ]
    for item in tbr9_handoff_call_target["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_handoff_call_target['conclusion']}")
    lines += [
        "",
        "### TBR9 pre-i(PX561,r) visible write findings",
        "",
    ]
    for item in tbr9_pre_i_visible_writes["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- target write audit: `{tbr9_pre_i_visible_writes['targetWriteAudit']}`")
    lines.append(f"- conclusion: {tbr9_pre_i_visible_writes['conclusion']}")
    lines += [
        "",
        "### TBR9 pre-i(PX561,r) side-effect call findings",
        "",
        f"- checks: `{tbr9_pre_i_side_effect_calls['checks']}`",
    ]
    for item in tbr9_pre_i_side_effect_calls["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_pre_i_side_effect_calls['conclusion']}")
    lines += [
        "",
        "### TBR9 observation hook readiness findings",
        "",
        f"- required env: `{tbr9_observation_hook_readiness['requiredRuntimeEnv']}`",
        f"- checks: `{tbr9_observation_hook_readiness['checks']}`",
    ]
    for item in tbr9_observation_hook_readiness["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_observation_hook_readiness['conclusion']}")
    lines += [
        "",
        "### TBR9 runtime observation findings",
        "",
        f"- trace: `{tbr9_runtime_observation['trace_path']}`",
        f"- event counts: `{tbr9_runtime_observation['event_counts']}`",
        f"- pre-i PX561: `{tbr9_runtime_observation['captcha_pre_i_px561']}`",
        f"- main Yc bridge: `{tbr9_runtime_observation['main_yc_bridge']}`",
        f"- runtime conclusion: `{tbr9_runtime_observation['conclusion']}`",
        "",
        "### TBR9 / AEAx negative-control findings",
        "",
    ]
    for control in result["traceBaseline"]["v2"].get("observationControls", []):
        lines.append(
            "- {run}: stage={stage}, preI TBR={pre_tbr}, preI AEAx={pre_aeax}, "
            "tf TBR={tf_tbr}, tf AEAx={tf_aeax}, cookieBridge={bridge}, "
            "CreateAccount status={status} redirect={redirect} error={code}/{field}".format(
                run=control.get("run"),
                stage=control.get("stage"),
                pre_tbr=control.get("preIHasTBR"),
                pre_aeax=control.get("preIHasAEAx"),
                tf_tbr=control.get("finalTfHasTBR"),
                tf_aeax=control.get("finalTfHasAEAx"),
                bridge=control.get("cookieBridgeOk"),
                status=control.get("createAccountStatus"),
                redirect=control.get("createAccountHasRedirect"),
                code=control.get("createAccountErrorCode"),
                field=control.get("createAccountErrorField"),
            )
        )
    lines += [
        "- Therefore AEAx-only PX561 is a negative control, not an accepted-success constructor target. It does not remove `TBR9Ugl7emA=` from P0.",
        "",
        "",
        "### TBR9 activity uniqueness findings",
        "",
    ]
    for item in tbr9_activity_uniqueness["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- remaining gap: {tbr9_activity_uniqueness['remainingGap']}")
    lines += [
        "",
        "### TBR9 minimal Yc/tf experiment findings",
        "",
    ]
    for item in tbr9_minimal_yc_tf["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_minimal_yc_tf['conclusion']}")
    lines += [
        "",
        "### TBR9 queue-to-tf static findings",
        "",
    ]
    for item in tbr9_queue_to_tf["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_queue_to_tf['conclusion']}")
    lines += [
        "",
        "### TBR9 Vs/ut/decode boundary findings",
        "",
        f"- checks: `{tbr9_vs_ut_decode['checks']}`",
        f"- replay totals: `{tbr9_vs_ut_decode['vsReplayEvidence']['totals']}`",
    ]
    for item in tbr9_vs_ut_decode["findings"]:
        lines.append(f"- {item}")
    lines.append(f"- conclusion: {tbr9_vs_ut_decode['conclusion']}")
    lines += [
        "",
        "### Eliminated TBR9 hypotheses",
        "",
    ]
    for item in ws_nq_boundary["eliminatedHypotheses"]:
        lines.append(f"- {item}")
    lines += [
        "",
        "## next evidence required",
        "",
    ]
    for item in result["nextEvidenceRequired"]:
        lines.append(f"- {item}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"json": rel(json_path), "md": rel(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
