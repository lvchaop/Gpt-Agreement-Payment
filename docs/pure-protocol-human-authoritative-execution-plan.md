# 纯协议 HUMAN 成功复现：权威执行计划

> 2026-06-13 更新：后续当前执行入口已迁移到
> `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-first-current-plan.md`。
> 本文档保留为历史权威计划和证据索引，不再作为线性执行入口。

日期：2026-06-13

## 0. 本文档地位

后续实现以本文档为当前权威计划：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-authoritative-execution-plan.md`

以下文档降级为历史证据和设计输入，不再作为线性执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`

本文档不是目标完成证明。目标只能由 fresh、no-browser、pure-protocol 端到端成功 artifact 证明。

## 1. 最终目标不变

实现并验证一个完整 fresh pure-protocol HUMAN 成功闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP、JS 解析、加密、payload 构造、请求重放；
3. 从 Outlook signup fresh session 推进到 HUMAN collector 成功；
4. collector decoded response 出现成功事件；
5. `_px` cookie/token jar mutation 可复现；
6. `/API/Proofs/risk/verify` 返回 `state=continue`；
7. `/API/CreateAccount` 返回 `redirectUrl`；
8. 每一步都有本地证据路径、脚本、输入输出 artifact、可复现命令。

完成条件：

- fresh 网络尝试已执行；
- session id 已记录；
- transport/direct/Webshare 控制变量已记录；
- collector request/response 已记录；
- decoded collector response 已记录且为成功类；
- `_px` jar mutation 已重放；
- risk/verify 已返回 continue；
- CreateAccount 已返回 redirectUrl；
- 最终 replay audit 和 goal completion verifier 同时为 true。

## 2. 当前证据基线

### 2.1 Candidate intake 当前不允许实验

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_intake.json`

当前 checks：

- `proposalCount=0`
- `proposalAcceptedCount=0`
- `proposalInvalidCount=0`
- `candidateCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前没有晋升后的单一 transition；
- 不能因为“可能是 IP / Webshare / direct / session”直接跑 fresh 网络。

### 2.2 Proposal lint 当前为空集且结构有效

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals_lint.json`

当前 checks：

- `proposalFileExists=true`
- `schemaRequiredCount=8`
- `schemaHasRequiredFields=true`
- `proposalCount=0`
- `validProposalCount=0`
- `invalidProposalCount=0`
- `promotableShapeCount=0`
- `allProposalsStructurallyValid=true`
- `emptyProposalSet=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 现在缺的不是“再试一次”，而是缺一个结构化 candidate proposal；
- 新假设必须先进入 proposal 文件并通过 lint。

### 2.3 Minimal transition experiment 被 gate 阻止

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`

当前 checks：

- `networkAttemptExecuted=false`
- `blockedByGate=true`
- `candidateIntakePromotedCount=0`
- `minimalTransitionExperimentStageAdvanced=false`
- `freshNoBrowserCollectorSuccess=false`
- `freshDecodedOIIoIooo0=false`
- `freshDecodedPxJarReplayed=false`
- `freshRiskVerifyContinue=false`
- `freshCreateAccountRedirectUrl=false`
- `goalComplete=false`

结论：

- 已有唯一 PoC 入口；
- 下一次网络必须通过该入口或其明确后继，不能绕过 gate 写临时脚本。

### 2.4 最终 replay 当前未执行

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`

当前 checks：

- `blockedByGate=true`
- `readyForFreshReplay=false`
- `replayAttemptExecuted=false`
- `networkAttemptExecuted=false`
- `pocFreshNoBrowserCollectorSuccess=false`
- `pocFreshRiskVerifyContinue=false`
- `pocFreshCreateAccountRedirectUrl=false`
- `goalComplete=false`

结论：

- 不能把 gate chain 通过、manifest 完整、历史 accepted downstream 成功误认为最终目标完成。

### 2.5 Gate chain 只证明离线门控可复现

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`

当前 checks：

- `stepCount=10`
- `passedStepCount=10`
- `failedStepCount=0`
- `allStepsPassed=true`
- `offlineOnly=true`
- `finalProofTaskCount=22`
- `finalProofPassedTaskCount=22`
- `finalNoCurrentRouteToPhase5=true`
- `finalReadyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前离线审计链稳定；
- 离线审计链通过不是 fresh HUMAN 成功。

### 2.6 Completion requirements 仍有阻塞项

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json`

当前 checks：

- `requirementCount=8`
- `blockingRequirementCount=4`
- `freshSuccessMissing=true`
- `noCurrentExperimentRoute=true`
- `evidenceGatedPocNetworkAttemptExecuted=false`
- `candidateIntakePromotedCount=0`
- `minimalTransitionExperimentStageAdvanced=false`
- `finalReplayAttemptExecuted=false`
- `goalComplete=false`
- `readyForFreshExperiment=false`

结论：

- 目标未完成；
- 当前阻塞不是权限、不是网络开关，而是没有可证据晋升的单 transition。

### 2.7 Goal gap 只剩端到端 PoC

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

当前 summary：

- `proved`: `trace_classifier`, `collector_response_decoder`, `collector_payload_constructor`, `pow_recompute`, `px_cookie_token_update`, `risk_verify_rebuild`, `fresh_tbr9_ws_nq`, `fresh_aeax_ws_ng`
- `blockingOrMissing`: `end_to_end_pure_protocol_poc`
- `goalComplete=false`

结论：

- 不再重做已证明子能力；
- 所有工作聚焦于把一个新 evidence-backed transition 推进到端到端 PoC。

## 3. 方法论约束

### 3.1 禁止猜测

任何结论必须带：

- 本地证据路径；
- 具体 check、字段、trace 片段、源码位置或 hook 产物；
- 可复现命令或生成脚本。

缺证据时只做取证、审计、归约，不下结论。

### 3.2 证据优先级

冲突时按以下顺序裁决：

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage / session timeline；
6. 静态 JS；
7. 推断。

低优先级证据不能覆盖高优先级证据。

### 3.3 Fresh 网络实验准入门

同时满足以下条件才允许 fresh 网络：

1. `proposal` 存在且 lint valid；
2. `proposal.preAccept=true`;
3. `proposal.clientVisible=true`;
4. `proposal.pureProtocolConstructible=true`;
5. `proposal.valueChain` 属于 `request|cookie|risk|verify`;
6. `proposal.negativeControlRefs` 非空；
7. `proposal.contradicted=false`;
8. candidate intake 输出 `promotedSingleTransitionCandidateCount=1`;
9. candidate intake 输出 `readyForFreshExperiment=true`;
10. minimal transition experiment gate 输出可执行；
11. 每次 fresh attempt 使用新 session；
12. 实验只改变这个 promoted transition。

不满足任一项，禁止网络。

### 3.4 IP / Webshare / direct 的处理

IP、Webshare、direct 可以作为 transport 控制变量，但不能单独作为原因。

允许做的事情：

- 在同一 evidence-backed transition 下记录 direct 与 Webshare 的对照；
- 每个 fresh attempt 换新 session；
- 保持同一 attempt 内 transport 变量可解释；
- 把 IP/session 结果写入 transport audit。

禁止做的事情：

- 在没有 promoted transition 时反复换 IP 重试；
- 用“可能是 IP”绕过 candidate gate；
- 混用旧 session 的成功/失败状态推断 fresh session。

## 4. 执行阶段

### Phase 1: 固化完成判定，防止误完成

目标：

- 增加最终 goal completion verifier；
- 明确什么时候可以调用目标完成，什么时候必须继续找证据。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`

输入：

- `pure_protocol_completion_requirements_audit.json`
- `evidence_gated_end_to_end_pure_protocol_poc.json`
- `final_pure_protocol_replay_audit.json`
- `reset_terminal_boundary_audit.json`
- `pure_protocol_goal_gap_audit.json`
- `pure_protocol_evidence_gate_chain_audit.json`
- `pure_protocol_evidence_manifest_verify.json`

必须输出 checks：

- `allInputsExist`
- `completionRequirementsGoalComplete`
- `completionBlockingRequirementCount`
- `pocNetworkAttemptExecuted`
- `pocFreshNoBrowserCollectorSuccess`
- `pocFreshDecodedOIIoIooo0`
- `pocFreshDecodedPxJarReplayed`
- `pocFreshRiskVerifyContinue`
- `pocFreshCreateAccountRedirectUrl`
- `finalReplayAttemptExecuted`
- `finalReplayGoalComplete`
- `goalGapBlockingOrMissingCount`
- `gateChainAllStepsPassed`
- `manifestVerifyAllHashesMatch`
- `completionVerified`
- `goalComplete`

当前预期：

- `completionVerified=false`
- `goalComplete=false`

### Phase 2: 把 completion verifier 接入离线审计链

目标：

- 让 terminal、completion、goal gap、manifest、gate chain 都引用 completion verifier；
- gate chain 从 10 步扩展为 11 步；
- proof reproducibility 从 22 项扩展为 23 项。

需要更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_pure_protocol_evidence_gate_chain.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

验证命令：

```bash
python3 -m py_compile \
  tools/verify_pure_protocol_goal_completion.py \
  tools/build_proof_script_reproducibility_audit.py \
  tools/run_pure_protocol_evidence_gate_chain.py \
  tools/build_pure_protocol_evidence_manifest.py \
  tools/build_reset_terminal_boundary_audit.py \
  tools/build_pure_protocol_completion_requirements_audit.py \
  tools/audit_pure_protocol_goal_gap.py

python3 tools/run_pure_protocol_evidence_gate_chain.py
python3 tools/build_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_evidence_manifest.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/build_reset_terminal_boundary_audit.py
python3 tools/audit_pure_protocol_goal_gap.py
python3 tools/verify_pure_protocol_goal_completion.py
```

### Phase 3: 新 candidate proposal 入口

目标：

- 只接收能改变决策的新证据；
- 所有新假设必须先落到 proposal schema。

现有 proposal 文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`

proposal 必须包含：

- `id`
- `evidence`
- `preAccept`
- `clientVisible`
- `pureProtocolConstructible`
- `valueChain`
- `negativeControlRefs`
- `contradicted`

执行规则：

1. 先从本地 trace/HAR/hook/source 中找证据；
2. 证据不足时补 artifact，不写 proposal；
3. proposal 写入后先跑 lint；
4. lint valid 后跑 candidate intake；
5. 只有一个 proposal 晋升时进入 Phase 4。

### Phase 4: Minimal promoted transition experiment

目标：

- 只验证一个 promoted transition；
- 不做随机网络重试；
- 每次新 attempt 换 session。

入口脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/minimal_promoted_transition_experiment.json`

必须记录：

- session id；
- transport 类型：direct 或 Webshare；
- Webshare session 标识；
- request diff；
- cookie jar before/after；
- collector response raw；
- collector response decoded；
- 是否推进到 `oIIoIooo|0`；
- 是否推进到 risk/verify continue；
- 是否推进到 CreateAccount redirectUrl。

通过条件：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `stageAdvanced=true`

失败条件：

- 仍为同类 failure response；
- 负控命中；
- transport 变量无法隔离；
- session 复用污染。

### Phase 5: Evidence-gated end-to-end PoC

目标：

- 将 Phase 4 成功 transition 放入完整 pure-protocol PoC。

入口脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`

通过条件：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`
- `goalComplete=true`

### Phase 6: Final replay audit

目标：

- 对 fresh 成功 PoC 做可复现 replay 审计；
- 防止一次性偶然成功被误认作可复现闭环。

入口脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_final_pure_protocol_replay_audit.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`

通过条件：

- `replayAttemptExecuted=true`
- `networkAttemptExecuted=true`
- `freshSessionIdRecorded=true`
- `transportEvidenceRecorded=true`
- `webshareOrDirectControlRecorded=true`
- `collectorRequestResponseRecorded=true`
- `decodedCollectorResponseRecorded=true`
- `pxJarMutationRecorded=true`
- `riskVerifyResponseRecorded=true`
- `createAccountResponseRecorded=true`
- `replayCommandsRecorded=true`
- `artifactHashesRecorded=true`
- `goalComplete=true`

### Phase 7: Goal completion verification

目标：

- 只有 completion verifier 通过时才允许宣告最终目标完成。

入口脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

通过条件：

- `completionVerified=true`
- `goalComplete=true`

## 5. 当前下一步

Phase 1/2 已完成当前轮落地：

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`

当前 checks：

- `authoritativePlanExists=true`
- `allInputsExist=true`
- `completionBlockingRequirementCount=4`
- `completionFreshSuccessMissing=true`
- `completionNoCurrentExperimentRoute=true`
- `pocNetworkAttemptExecuted=false`
- `pocFreshNoBrowserCollectorSuccess=false`
- `pocFreshDecodedOIIoIooo0=false`
- `pocFreshRiskVerifyContinue=false`
- `pocFreshCreateAccountRedirectUrl=false`
- `finalReplayAttemptExecuted=false`
- `goalGapBlockingOrMissingCount=1`
- `gateChainAllStepsPassed=true`
- `manifestVerifyAllHashesMatch=true`
- `failedGateCount=22`
- `completionVerified=false`
- `goalComplete=false`
- `readyForFreshExperiment=false`

审计链当前状态：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
  - `taskCount=23`
  - `passedTaskCount=23`
  - `failedTaskCount=0`
  - `allProofScriptsReproducible=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
  - `stepCount=11`
  - `passedStepCount=11`
  - `failedStepCount=0`
  - `allStepsPassed=true`
  - `finalProofTaskCount=23`
  - `finalReadyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest.json`
  - `fileCount=27`
  - `allFilesExist=true`
  - `allFilesHashed=true`
  - `duplicateHashCount=0`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`
  - `manifestFileCount=27`
  - `verifiedFileCount=27`
  - `missingFileCount=0`
  - `hashMismatchCount=0`
  - `allHashesMatch=true`

Phase 3 当前轮已完成 evidence triage：

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_phase3_proposal_evidence_triage.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_proposal_evidence_triage.json`

当前 checks：

- `authoritativePlanExists=true`
- `allNamedInputsExist=true`
- `namedInputCount=12`
- `triagedSourceCount=6`
- `proposalCount=0`
- `proposalWorthyEvidenceCount=0`
- `recursiveJsonReadyOrPromotedSignalCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

审计链当前状态：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
  - `taskCount=24`
  - `passedTaskCount=24`
  - `failedTaskCount=0`
  - `allProofScriptsReproducible=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
  - `stepCount=12`
  - `passedStepCount=12`
  - `failedStepCount=0`
  - `allStepsPassed=true`
  - `finalProofTaskCount=24`
  - `finalReadyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest.json`
  - `fileCount=29`
  - `allFilesExist=true`
  - `allFilesHashed=true`
  - `duplicateHashCount=0`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `phase3ProposalEvidenceTriageExists=true`
  - `phase3ProposalWorthyEvidenceCount=0`
  - `phase3RecursiveReadyOrPromotedSignalCount=0`

Phase 3 evidence entrance coverage 已完成当前轮落地：

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_phase3_evidence_entrance_coverage_audit.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_evidence_entrance_coverage_audit.json`

当前 checks：

- `authoritativePlanExists=true`
- `allInputsExist=true`
- `entranceRowCount=5`
- `coveredEntranceRowCount=5`
- `uncoveredEntranceRowCount=0`
- `unminedHighValueDirectoryCount=34`
- `highValueUnclassifiedSuccessSignalCount=0`
- `highValueReplayableFreshSuccessCount=0`
- `phase3ProposalWorthyEvidenceCount=0`
- `phase3RecursiveReadyOrPromotedSignalCount=0`
- `resetNoCurrentRouteToPhase5=true`
- `goalBlockingOnlyEndToEndPoc=true`
- `proposalEntranceExhaustedForCurrentEvidence=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

审计链当前状态：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
  - `taskCount=25`
  - `passedTaskCount=25`
  - `failedTaskCount=0`
  - `allProofScriptsReproducible=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
  - `stepCount=13`
  - `passedStepCount=13`
  - `failedStepCount=0`
  - `allStepsPassed=true`
  - `finalProofTaskCount=25`
  - `finalReadyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest.json`
  - `fileCount=31`
  - `allFilesExist=true`
  - `allFilesHashed=true`
  - `duplicateHashCount=0`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `phase3EvidenceEntranceCoverageExists=true`
  - `phase3UncoveredEntranceRowCount=0`
  - `phase3ProposalEntranceExhaustedForCurrentEvidence=true`

Phase 3 raw evidence entrance audit 已完成当前轮落地：

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_phase3_raw_evidence_entrance_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_phase3_raw_trace_crosswalk_audit.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_raw_evidence_entrance_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_raw_trace_crosswalk_audit.json`

当前 raw evidence checks：

- `classifierRunCount=14`
- `scannedRawFileCount=15399`
- `rawSuccessSignalFileCount=115`
- `indexedBrowserRuntimeSignalCount=17`
- `unindexedBrowserTraceSignalCount=87`
- `packagedCopyOrDocumentationSignalCount=8`
- `staticJsStringSignalCount=1`
- `otherRawSignalCount=0`
- `proposalWorthyRawSignalCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

当前 raw trace crosswalk checks：

- `unindexedBrowserTraceSignalCount=87`
- `crosswalkRowCount=87`
- `referencedTraceCount=87`
- `unreferencedTraceCount=0`
- `unreferencedCollectorSuccessTokenCount=0`
- `proposalWorthyRawTraceCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

审计链当前状态：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
  - `taskCount=27`
  - `passedTaskCount=27`
  - `failedTaskCount=0`
  - `allProofScriptsReproducible=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
  - `stepCount=15`
  - `passedStepCount=15`
  - `failedStepCount=0`
  - `allStepsPassed=true`
  - `finalProofTaskCount=27`
  - `finalReadyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest.json`
  - `fileCount=35`
  - `allFilesExist=true`
  - `allFilesHashed=true`
  - `duplicateHashCount=0`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `phase3RawEvidenceEntranceExists=true`
  - `phase3RawSuccessSignalFileCount=115`
  - `phase3RawUnindexedBrowserTraceSignalCount=87`
  - `phase3RawProposalWorthySignalCount=0`
  - `phase3RawTraceCrosswalkExists=true`
  - `phase3RawTraceCrosswalkUnreferencedCount=0`
  - `phase3RawTraceCrosswalkProposalWorthyCount=0`

下一步仍属于 Phase 3，但只能做新证据发现：

1. 只从本地 trace/HAR/hook/source 中找新证据；
2. 新证据必须先落入 promoted transition proposal schema；
3. proposal lint 通过后再进入 candidate intake；
4. 只有 `promotedSingleTransitionCandidateCount=1` 且 `readyForFreshExperiment=true`，才进入 Phase 4；
5. 当前仍无 promoted transition，因此不跑网络。

## 6. 不再执行的路线

在 `readyForFreshExperiment=false` 且 `promotedSingleTransitionCandidateCount=0` 时，以下路线禁止执行：

- 直接 Webshare 多试几次；
- 直接 direct 多试几次；
- 只换 IP 或只换 session；
- 搬运历史 accepted payload；
- 随机拼接 encoded、pc、uuid、marker、tail、stack、WASM 输出；
- 把 decoded equality 当成成功充分条件；
- 把 success-only hook 当成原因；
- 绕过 `run_minimal_promoted_transition_experiment.py` 和 `run_evidence_gated_end_to_end_pure_protocol_poc.py` 写临时网络脚本。

## 7. 计划更新规则

每次新增或修改关键 artifact 后，必须同步更新本文档的以下部分之一：

- 当前证据基线；
- 执行阶段状态；
- 网络实验准入门；
- 完成判定；
- 禁止路线。

更新必须引用真实 artifact path 和 check，不写无证据判断。
