#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "output/protocol_reverse"
HYP = PROTO / "hypothesis_reframe"
GOAL = PROTO / "goal_audit"
RESET = PROTO / "reset_plan"
OUT = HYP / "objective_requirement_crosswalk.json"

OBJECTIVE = (
    "实现并验证“完全纯协议解析 + 复现 HUMAN 成功包”的可行闭环：不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码，"
    "先完成成功/失败 trace 分类器与 collector response 离线解码器，再推进 collector payload 构造、POW 复算、"
    "_px cookie/token 更新、Microsoft risk/verify 重放与端到端纯协议 PoC；所有结论必须可追溯到本地静态 JS、"
    "运行时 hook、network trace、HAR、cookie 时间线或成功/失败对照样本，禁止猜测，缺证据先补证据。"
)

INPUTS = {
    "goalGap": GOAL / "pure_protocol_goal_gap_audit.json",
    "completionRequirements": HYP / "pure_protocol_completion_requirements_audit.json",
    "goalCompletionVerifier": GOAL / "pure_protocol_goal_completion_verifier.json",
    "traceClassifier": PROTO / "trace_classification_v2/human_trace_classifier_v2_summary.json",
    "collectorDecoder": PROTO / "collector_decode/collector_decoder_coverage_audit.json",
    "collectorBuildExact": GOAL / "collector_request_build_exact_coverage_audit.json",
    "powOsk": PROTO / "pow/pow_to_px561_osk_audit.json",
    "powTailInputs": PROTO / "pow/pow_solver_px561_tail_inputs_audit.json",
    "cookieJar": PROTO / "cookie_jar/px_cookie_jar_updater_multi_audit.json",
    "collectorToRisk": HYP / "collector_to_risk_consumption_chain.json",
    "s00RiskGap": HYP / "s00_risk_verify_material_gap.json",
    "candidateIntake": HYP / "promoted_transition_candidate_intake.json",
    "minimalTransition": HYP / "minimal_promoted_transition_experiment.json",
    "evidenceGatedPoc": GOAL / "evidence_gated_end_to_end_pure_protocol_poc.json",
    "finalReplay": GOAL / "final_pure_protocol_replay_audit.json",
    "gateChain": GOAL / "pure_protocol_evidence_gate_chain_audit.json",
    "manifest": GOAL / "pure_protocol_evidence_manifest.json",
    "manifestVerify": GOAL / "pure_protocol_evidence_manifest_verify.json",
    "liveRunnerGate": HYP / "live_runner_gate_audit.json",
    "convergentMatrix": HYP / "convergent_evidence_entrance_matrix.json",
    "manifestCoverageGap": HYP / "manifest_coverage_gap_audit.json",
}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def checks(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("checks") or {}


def summary(doc: dict[str, Any]) -> dict[str, Any]:
    return doc.get("summary") or {}


def proven(value: bool) -> str:
    return "proven" if value else "not_proven"


def main() -> int:
    docs = {name: read_json(path) for name, path in INPUTS.items()}
    c = {name: checks(doc) for name, doc in docs.items()}
    trace_doc = docs["traceClassifier"]
    s_goal = summary(docs["goalGap"])
    proved = set(s_goal.get("proved") or [])

    requirements = [
        {
            "id": "OBJ01_success_failure_trace_classifier",
            "text": "完成成功/失败 trace 分类器。",
            "status": proven(
                trace_doc.get("runCount", 0) >= 14
                and trace_doc.get("observationControlCount", 0) >= 2
                and "trace_classifier" in proved
            ),
            "evidence": [str(INPUTS["traceClassifier"]), str(INPUTS["goalGap"])],
            "facts": {
                "classifierRunCount": trace_doc.get("runCount"),
                "observationControlCount": trace_doc.get("observationControlCount"),
                "goalGapProvedTraceClassifier": "trace_classifier" in proved,
            },
            "blocking": False,
        },
        {
            "id": "OBJ02_collector_response_offline_decoder",
            "text": "完成 collector response 离线解码器。",
            "status": proven(
                c["collectorDecoder"].get("allDecodeFilesExist") is True
                and c["collectorDecoder"].get("allRowsMatchExpectedSuccessHandler") is True
                and "collector_response_decoder" in proved
            ),
            "evidence": [str(INPUTS["collectorDecoder"]), str(INPUTS["goalGap"])],
            "facts": {
                "allDecodeFilesExist": c["collectorDecoder"].get("allDecodeFilesExist"),
                "allRowsMatchExpectedSuccessHandler": c["collectorDecoder"].get("allRowsMatchExpectedSuccessHandler"),
                "goalGapProvedCollectorDecoder": "collector_response_decoder" in proved,
            },
            "blocking": False,
        },
        {
            "id": "OBJ03_collector_payload_constructor",
            "text": "推进并验证 collector payload/body/pc 构造。",
            "status": proven(
                c["collectorBuildExact"].get("allRunsExact") is True
                and c["collectorBuildExact"].get("allRunsPayloadExact") is True
                and c["collectorBuildExact"].get("allRunsPcExact") is True
                and "collector_payload_constructor" in proved
            ),
            "evidence": [str(INPUTS["collectorBuildExact"]), str(INPUTS["goalGap"])],
            "facts": {
                "allRunsExact": c["collectorBuildExact"].get("allRunsExact"),
                "allRunsPayloadExact": c["collectorBuildExact"].get("allRunsPayloadExact"),
                "allRunsPcExact": c["collectorBuildExact"].get("allRunsPcExact"),
                "goalGapProvedPayloadConstructor": "collector_payload_constructor" in proved,
            },
            "blocking": False,
        },
        {
            "id": "OBJ04_pow_recompute",
            "text": "推进并验证 POW 复算。",
            "status": proven(
                c["powOsk"].get("acceptedRowsMatchPowHit") is True
                and c["powTailInputs"].get("acceptedSolverOutputsMatchObservedOsk") is True
                and "pow_recompute" in proved
            ),
            "evidence": [str(INPUTS["powOsk"]), str(INPUTS["powTailInputs"]), str(INPUTS["goalGap"])],
            "facts": {
                "acceptedRowsMatchPowHit": c["powOsk"].get("acceptedRowsMatchPowHit"),
                "acceptedSolverOutputsMatchObservedOsk": c["powTailInputs"].get("acceptedSolverOutputsMatchObservedOsk"),
                "goalGapProvedPowRecompute": "pow_recompute" in proved,
            },
            "blocking": False,
        },
        {
            "id": "OBJ05_px_cookie_token_update",
            "text": "推进并验证 _px cookie/token 更新。",
            "status": proven("px_cookie_token_update" in proved),
            "evidence": [str(INPUTS["cookieJar"]), str(INPUTS["goalGap"])],
            "facts": {
                "goalGapProvedPxCookieTokenUpdate": "px_cookie_token_update" in proved,
                "allRunsRiskProviderMetadataValuesMatchJar": c["cookieJar"].get("allRunsRiskProviderMetadataValuesMatchJar"),
                "anyRunProvesContinueRiskVerifyMatchesJar": c["cookieJar"].get("anyRunProvesContinueRiskVerifyMatchesJar"),
            },
            "blocking": False,
        },
        {
            "id": "OBJ06_msft_risk_verify_replay",
            "text": "推进并验证 Microsoft risk/verify 重放。",
            "status": proven("risk_verify_rebuild" in proved),
            "evidence": [str(INPUTS["collectorToRisk"]), str(INPUTS["s00RiskGap"]), str(INPUTS["goalGap"])],
            "facts": {
                "goalGapProvedRiskVerifyRebuild": "risk_verify_rebuild" in proved,
                "riskContinueTokenFeedsCreateAccount": c["collectorToRisk"].get("riskContinueTokenFeedsCreateAccount"),
                "s00RiskVerifyStateContinue": c["s00RiskGap"].get("riskVerifyStateContinue"),
            },
            "blocking": False,
            "scope": "已由 accepted s00/downstream material 证明；fresh no-browser collector success 缺失时不能证明完整 fresh flow。",
        },
        {
            "id": "OBJ07_end_to_end_pure_protocol_poc",
            "text": "完成端到端纯协议 PoC：fresh collector success -> risk/verify continue -> CreateAccount redirectUrl。",
            "status": "missing",
            "evidence": [
                str(INPUTS["evidenceGatedPoc"]),
                str(INPUTS["finalReplay"]),
                str(INPUTS["completionRequirements"]),
                str(INPUTS["goalCompletionVerifier"]),
            ],
            "facts": {
                "pocNetworkAttemptExecuted": c["evidenceGatedPoc"].get("networkAttemptExecuted"),
                "pocBlockedByGate": c["evidenceGatedPoc"].get("blockedByGate"),
                "freshNoBrowserCollectorSuccess": c["evidenceGatedPoc"].get("freshNoBrowserCollectorSuccess"),
                "freshDecodedOIIoIooo0": c["evidenceGatedPoc"].get("freshDecodedOIIoIooo0"),
                "freshRiskVerifyContinue": c["evidenceGatedPoc"].get("freshRiskVerifyContinue"),
                "freshCreateAccountRedirectUrl": c["evidenceGatedPoc"].get("freshCreateAccountRedirectUrl"),
                "finalReplayAttemptExecuted": c["finalReplay"].get("replayAttemptExecuted"),
                "completionVerified": c["goalCompletionVerifier"].get("completionVerified"),
            },
            "blocking": True,
        },
        {
            "id": "OBJ08_no_browser_camoufox_mouse_vision_external_captcha",
            "text": "完整成功闭环不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码。",
            "status": "not_proven",
            "evidence": [str(INPUTS["evidenceGatedPoc"]), str(INPUTS["completionRequirements"])],
            "facts": {
                "reason": "没有 fresh no-browser end-to-end success artifact，不能证明完整闭环的独立性。",
                "pocBlockedByGate": c["evidenceGatedPoc"].get("blockedByGate"),
                "completionFreshSuccessMissing": c["completionRequirements"].get("freshSuccessMissing"),
            },
            "blocking": True,
        },
        {
            "id": "OBJ09_all_conclusions_traceable_to_local_evidence",
            "text": "所有结论可追溯到本地静态 JS、runtime hook、network trace/HAR、cookie timeline、成功/失败对照样本；缺证据先补证据。",
            "status": "partially_proven",
            "evidence": [
                str(INPUTS["gateChain"]),
                str(INPUTS["manifest"]),
                str(INPUTS["manifestVerify"]),
                str(INPUTS["manifestCoverageGap"]),
                str(INPUTS["convergentMatrix"]),
            ],
            "facts": {
                "gateChainAllStepsPassed": c["gateChain"].get("allStepsPassed"),
                "manifestAllFilesHashed": c["manifest"].get("allFilesHashed"),
                "manifestVerifyAllHashesMatch": c["manifestVerify"].get("allHashesMatch"),
                "manifestCoverageHighValueUncoveredDirectoryCount": c["manifestCoverageGap"].get("highValueUncoveredDirectoryCount"),
                "convergentRecommendedNextEntranceCount": c["convergentMatrix"].get("recommendedNextEntranceCount"),
                "limitation": "缺失的端到端 fresh success 仍无成功证据，不能标为 proven。",
            },
            "blocking": True,
        },
        {
            "id": "OBJ10_no_ungated_fresh_network_retry",
            "text": "fresh/direct/Webshare/session 网络尝试必须由唯一 promoted transition gate 授权，不能随机重试。",
            "status": proven(
                c["liveRunnerGate"].get("currentNetworkAttemptBlocked") is True
                and c["liveRunnerGate"].get("proofInvokedUngatedLiveRunnerCount") == 0
                and c["liveRunnerGate"].get("gateChainInvokedUngatedLiveRunnerCount") == 0
                and c["candidateIntake"].get("promotedSingleTransitionCandidateCount") in {None, 0}
            ),
            "evidence": [str(INPUTS["liveRunnerGate"]), str(INPUTS["candidateIntake"]), str(INPUTS["minimalTransition"])],
            "facts": {
                "candidateIntakePromotedCount": c["candidateIntake"].get("promotedSingleTransitionCandidateCount"),
                "minimalTransitionNetworkAttemptExecuted": c["minimalTransition"].get("networkAttemptExecuted"),
                "currentNetworkAttemptBlocked": c["liveRunnerGate"].get("currentNetworkAttemptBlocked"),
                "proofInvokedUngatedLiveRunnerCount": c["liveRunnerGate"].get("proofInvokedUngatedLiveRunnerCount"),
                "gateChainInvokedUngatedLiveRunnerCount": c["liveRunnerGate"].get("gateChainInvokedUngatedLiveRunnerCount"),
            },
            "blocking": False,
        },
    ]

    blocking = [row["id"] for row in requirements if row.get("blocking") and row["status"] != "proven"]
    status_counts: dict[str, int] = {}
    for row in requirements:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1

    checks_out = {
        "allInputsExist": all(path.exists() for path in INPUTS.values()),
        "requirementCount": len(requirements),
        "provenCount": status_counts.get("proven", 0),
        "missingCount": status_counts.get("missing", 0),
        "notProvenCount": status_counts.get("not_proven", 0),
        "partiallyProvenCount": status_counts.get("partially_proven", 0),
        "blockingRequirementCount": len(blocking),
        "endToEndPocMissing": "OBJ07_end_to_end_pure_protocol_poc" in blocking,
        "fullNoBrowserIndependenceNotProven": "OBJ08_no_browser_camoufox_mouse_vision_external_captcha" in blocking,
        "traceabilityOnlyPartiallyProven": "OBJ09_all_conclusions_traceable_to_local_evidence" in blocking,
        "gateChainAllStepsPassed": c["gateChain"].get("allStepsPassed") is True,
        "manifestVerifyAllHashesMatch": c["manifestVerify"].get("allHashesMatch") is True,
        "readyForFreshExperiment": False,
        "goalComplete": False,
    }

    doc = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "objective": OBJECTIVE,
        "purpose": "Map the user-provided active objective to concrete local evidence, so completion cannot be claimed from a narrower proof subset.",
        "inputs": {name: str(path) for name, path in INPUTS.items()},
        "requirements": requirements,
        "blockingRequirements": blocking,
        "checks": checks_out,
        "decision": {
            "goalComplete": False,
            "readyForFreshExperiment": False,
            "recommendedExperiment": None,
            "nextArtifact": None,
            "nextScript": None,
            "reason": "The objective crosswalk proves several subcomponents, but the fresh no-browser end-to-end PoC remains missing and full no-browser independence is therefore not proven.",
        },
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"json": str(OUT), "checks": checks_out, "decision": doc["decision"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
