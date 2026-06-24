# 纯协议 HUMAN 成功复现：方法论落地执行计划

日期：2026-06-13

## 0. 文档地位

后续实现以本文档作为新的执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodology-implementation-plan.md`

以下文档和产物只作为证据输入，不作为线性推进入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-first-current-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-authoritative-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`

本文档不是完成证明。最终完成只能由 fresh、no-browser、pure-protocol 端到端成功产物证明。

## 1. 最终目标不变

目标仍是实现并验证完整 fresh pure-protocol HUMAN 成功闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP、JS 解析、加密、payload 构造、请求重放；
3. fresh Outlook signup session 推进到 HUMAN collector 成功；
4. decoded collector response 出现成功事件；
5. `_px` cookie/token jar mutation 可复现；
6. `/API/Proofs/risk/verify` 返回 `state=continue`；
7. `/API/CreateAccount` 返回 `redirectUrl`；
8. 全链路有本地证据路径、脚本、输入输出 artifact、可复现命令。

最终完成门槛保持不变：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`
  - `networkAttemptExecuted=true`
  - `freshNoBrowserCollectorSuccess=true`
  - `freshDecodedOIIoIooo0=true`
  - `freshDecodedPxJarReplayed=true`
  - `freshRiskVerifyContinue=true`
  - `freshCreateAccountRedirectUrl=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`
  - `replayAttemptExecuted=true`
  - `goalComplete=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`
  - `completionVerified=true`
  - `goalComplete=true`

## 2. 当前证据基线

### 2.1 当前没有 fresh 网络准入

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_intake.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_boundary_proposal_gate_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/local_trace_evidence_freshness_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unclassified_trace_signal_reduction_audit.json`

当前关键 checks：

- `proposalCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `proposalReadyRowCount=0`
- `proposalWorthyNowCount=0`
- `proposalReadyRunCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前不能直接做 direct/Webshare/IP/session 网络重试；
- 当前缺口不是执行权限或网络权限，而是没有 evidence-backed promoted transition。

### 2.2 新增本地 trace 是有效线索，但不是 no-browser 成功

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/local_trace_evidence_freshness_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unclassified_trace_signal_reduction_audit.json`

当前关键 checks：

- `runtimeTraceCount=172`
- `jsTraceCount=45`
- `inventoryRuntimeTraceCount=157`
- `inventoryJsTraceCount=36`
- `inventoryRuntimeCountMatchesCurrent=false`
- `inventoryJsCountMatchesCurrent=false`
- `unclassifiedRunCount=162`
- `unclassifiedHighValueSignalRunCount=79`
- `unclassifiedCollectorMaterialRunCount=155`
- `browserSuccessChainRunCount=18`
- `browserParentSuccessCookieChainRunCount=6`
- `collectorMaterialOnlyRunCount=76`
- `classificationEvidenceOnly=true`

结论：

- 旧 inventory 确实落后，新增 trace 必须消化；
- 18 个 browser success chain run 只能作为分类/对照/差异归约证据；
- 它们不能被写成 no-browser pure-protocol 成功结论。

### 2.3 当前离线审计链可复现，但目标未完成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

当前关键 checks：

- `allStepsPassed=true`
- `allHashesMatch=true`
- `blockingRequirementCount=4`
- `freshSuccessMissing=true`
- `noCurrentExperimentRoute=true`
- `completionVerified=false`
- `blockingOrMissing=["end_to_end_pure_protocol_poc"]`

结论：

- 当前 44 项 proof、32 步 gate、71 文件 manifest 是稳定证据链；
- 稳定证据链只能证明当前状态，不能替代 fresh 端到端成功；
- 当前唯一最终缺口仍是 `end_to_end_pure_protocol_poc`。

## 3. 方法论

后续不再按“看到什么补什么证据”推进，而按“阻塞字段反推最小事实”推进。

固定顺序：

1. 读取最终完成字段；
2. 定位当前阻塞字段；
3. 定义能改变阻塞字段的最小新增事实；
4. 找能产生该事实的本地证据入口；
5. 本地证据能形成 proposal 时才晋升；
6. 只有 exactly one promoted transition 时才 fresh 实验；
7. fresh 实验只验证一个 transition，不做无边界重试。

禁止：

- 用 IP/Webshare/direct 猜测绕过 gate；
- 用 browser success trace 冒充 no-browser 成功；
- 用 WASM/glue 复杂度默认解释失败；
- 用 decoded equality 默认推出 server accept；
- 在没有 proposal 的情况下换 session、换 IP、换 transport 撞结果。

证据优先级：

1. fresh live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage / session timeline；
6. 静态 JS；
7. 推断。

## 4. 新执行计划

### Phase 0：基线锁定

目标：

- 确认当前没有网络准入；
- 确认 manifest/hash/gate/completion 状态未漂移；
- 后续每新增 artifact 后重复执行。

命令：

```bash
python3 -m py_compile \
  tools/build_proof_script_reproducibility_audit.py \
  tools/run_pure_protocol_evidence_gate_chain.py \
  tools/build_pure_protocol_evidence_manifest.py \
  tools/verify_pure_protocol_evidence_manifest.py \
  tools/build_pure_protocol_completion_requirements_audit.py \
  tools/verify_pure_protocol_goal_completion.py

python3 tools/build_proof_script_reproducibility_audit.py
python3 tools/run_pure_protocol_evidence_gate_chain.py
python3 tools/build_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_evidence_manifest.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/verify_pure_protocol_goal_completion.py
```

通过标准：

- `allStepsPassed=true`
- `allHashesMatch=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

### Phase 1：把新增 browser success chain 转成受控分类资产

目标：

- 消化 18 个 browser success chain run；
- 生成可审计 backlog 或等价 `trace_classification_*.json`；
- 明确哪些 run 可作为正样本、负控、或仅 collector material。

计划产物：

- `tools/build_browser_success_chain_classification_backlog.py`
- `output/protocol_reverse/hypothesis_reframe/browser_success_chain_classification_backlog.json`

输入证据：

- `local_trace_evidence_freshness_audit.json`
- `unclassified_trace_signal_reduction_audit.json`
- `trace_classifier_raw_coverage_gap_audit.json`

必须输出字段：

- `browserSuccessChainRunCount`
- `browserParentSuccessCookieChainRunCount`
- `classificationBacklogCount`
- `safeToPromoteToClassifier`
- `noBrowserEvidenceCount`
- `proposalReadyRunCount`
- `readyForFreshExperiment`

通过标准：

- 如果只是补分类：`proposalReadyRunCount=0` 且 `readyForFreshExperiment=false`；
- 如果发现新候选：必须指出它改变 proposal 八字段中的哪一字段，并进入 Phase 3。

当前执行结果：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_browser_success_chain_classification_backlog.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_chain_classification_backlog.json`
- 当前 checks：
  - `browserSuccessChainRunCount=18`
  - `browserParentSuccessCookieChainRunCount=6`
  - `classificationBacklogCount=24`
  - `classificationBacklogNotInClassifierCount=18`
  - `safeToPromoteToClassifier=false`
  - `noBrowserEvidenceCount=0`
  - `proposalReadyRunCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 结论：
  - 18 个 browser success chain 和 6 个 parent-cookie control 已转成受控 backlog；
  - backlog 只提供分类/差异归约输入；
  - 当前没有 no-browser evidence，也没有 proposal-ready run；
  - 下一步进入 Phase 2，做 server-visible diff audit。

### Phase 2：从成功链反推最小 server-visible 分叉

目标：

- 不再泛化分析所有 WASM/material；
- 只比较 success browser chain 与失败/停滞样本之间最早的 server-visible 分叉；
- 分叉必须落在 request/cookie/risk/verify 价值链。

计划产物：

- `tools/build_browser_success_chain_server_visible_diff_audit.py`
- `output/protocol_reverse/hypothesis_reframe/browser_success_chain_server_visible_diff_audit.json`

比较维度：

1. collector request outer tuple；
2. collector encoded payload 解码后的可比较字段；
3. `_px` cookie jar before/after；
4. risk/verify request/response；
5. CreateAccount 前最后状态；
6. transport 只记录为上下文，不作为根因。

必须输出字段：

- `positiveRunCount`
- `negativeControlRunCount`
- `earliestServerVisibleDiffCount`
- `singleFieldDiffCandidateCount`
- `coupledFieldDiffGroupCount`
- `clientVisibleDiffCount`
- `pureProtocolConstructibleDiffCount`
- `contradictedDiffCount`
- `proposalCandidateCount`

通过标准：

- 只有 `proposalCandidateCount=1` 时进入 Phase 3；
- 多候选必须继续归约；
- 零候选则回到 Phase 1/2 选择新的分类维度。

当前执行结果：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_browser_success_chain_server_visible_diff_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_chain_server_visible_diff_audit.json`
- 输入对照：
  - positive：18 个 `browser_success_positive_control`
  - negative：16 个负控，其中 6 个来自 parent-cookie backlog，10 个来自 classifier v2 非 `full_success_decoded` run
- 当前 checks：
  - `positiveRunCount=18`
  - `negativeControlRunCount=16`
  - `positiveRuntimeTraceExistsCount=18`
  - `negativeRuntimeTraceExistsCount=15`
  - `earliestServerVisibleDiffCount=10`
  - `singleFieldDiffCandidateCount=4`
  - `coupledFieldDiffGroupCount=1`
  - `clientVisibleDiffCount=10`
  - `pureProtocolConstructibleDiffCount=1`
  - `contradictedDiffCount=10`
  - `proposalCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 结论：
  - browser success chain 确实暴露 server-visible 差异；
  - 这些差异分布在 request/risk/verify/cookie 价值链；
  - 但所有 10 类差异都被负控矛盾或属于下游 outcome；
  - pre-accept request class 仍与 payload/pc/session state 耦合；
  - 当前没有 exactly one proposal candidate，不能进入 Phase 3/4。

### Phase 3：proposal 写入与晋升

目标：

- 把 Phase 1/2 产出的唯一候选写入 proposal schema；
- 由现有 lint/control/intake 决定是否晋升。

写入目标：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`

候选必须包含：

- `id`
- `evidence`
- `preAccept`
- `clientVisible`
- `pureProtocolConstructible`
- `valueChain`
- `negativeControlRefs`
- `contradicted`

验证命令：

```bash
python3 tools/lint_promoted_transition_candidate_proposals.py
python3 tools/audit_promoted_transition_candidate_proposals_lint_controls.py
python3 tools/build_promoted_transition_candidate_intake.py
```

进入网络实验的唯一标准：

- `promotedSingleTransitionCandidateCount=1`
- `readyForFreshExperiment=true`

### Phase 4：最小 fresh 实验

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

前置条件：

- Phase 3 通过；
- exactly one promoted transition；
- 每一次 fresh attempt 必须使用新 session；
- 每个 attempt 的 transport 固定，禁止同一 attempt 内混用 direct/Webshare。

transport 规则：

- 如果当前直链代码证据表明请求不经过本地代理，则默认 direct；
- Webshare 只作为同一 promoted transition 的受控 transport 变量；
- “同一会话、同一 IP、多试几次”只能用于同一个已晋升 transition 的最小重复性验证；
- 新一轮 attempt 必须换 session；
- IP/Webshare/direct 的差异只能作为 transport 证据，不得单独晋升为根因。

必须记录：

- session id；
- transport：direct 或 Webshare；
- Webshare session/IP 标识；
- promoted transition id；
- request diff；
- cookie jar before/after；
- collector response raw；
- collector response decoded；
- 是否推进到 `oIIoIooo|0`；
- 是否推进到 risk/verify continue；
- 是否推进到 CreateAccount redirectUrl。

通过标准：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `stageAdvanced=true`

### Phase 5：evidence-gated end-to-end PoC

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

前置条件：

- Phase 4 成功；
- minimal transition 已证明能推进阶段。

通过标准：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`

### Phase 6：final replay 与 completion verifier

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_final_pure_protocol_replay_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

通过标准：

- `replayAttemptExecuted=true`
- `networkAttemptExecuted=true`
- `collectorRequestResponseRecorded=true`
- `decodedCollectorResponseRecorded=true`
- `pxJarMutationRecorded=true`
- `riskVerifyResponseRecorded=true`
- `createAccountResponseRecorded=true`
- `artifactHashesRecorded=true`
- `completionVerified=true`
- `goalComplete=true`

## 5. 立即执行顺序

下一步从 Phase 1 开始，不从网络重试开始：

1. 建 `browser_success_chain_classification_backlog`；
2. 若只是分类资产，更新 proof/gate/manifest/completion；
3. 基于 backlog 建 `browser_success_chain_server_visible_diff_audit`；
4. 若产出 exactly one proposal candidate，写入 proposal；
5. 通过 lint/control/intake 后，才执行最小 fresh 实验；
6. 若不能产出 proposal，继续寻找能改变 proposal 八字段的新证据维度。

当前进度：

- 第 1 步已完成；
- 第 2 步已完成：
  - `proof_script_reproducibility_audit.json`: `taskCount=33`, `passedTaskCount=33`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=21`, `passedStepCount=21`
  - `pure_protocol_evidence_manifest.json`: `fileCount=49`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=49`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `blockingRequirementCount=4`, `freshSuccessMissing=true`, `noCurrentExperimentRoute=true`
  - `reset_terminal_boundary_audit.json`: `proofScriptTaskCount=33`, `evidenceGateChainStepCount=21`, `evidenceManifestFileCount=49`
  - `pure_protocol_goal_completion_verifier.json`: `completionVerified=false`, `failedGateCount=22`
- 第 3 步已完成，结果为 `proposalCandidateCount=0`。
- 已扩展到更细粒度的 payload/pc/session 字段级 lineage：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_browser_success_payload_pc_session_lineage_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_payload_pc_session_lineage_audit.json`
- 字段级 lineage 当前 checks：
  - `positiveRunCount=18`
  - `positiveBundleBuildRunCount=1`
  - `positivePx561BundleBuildRunCount=1`
  - `fieldLineageRowCount=3`
  - `fieldLineageContradictedCount=3`
  - `fieldLineagePureProtocolConstructibleCount=1`
  - `payloadExactControlRejected=true`
  - `pcAloneEliminated=true`
  - `outerTupleNoSingleReadyGroup=true`
  - `encoderFamilyStillTwoAxis=true`
  - `proposalCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=35`, `passedTaskCount=35`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=23`, `passedStepCount=23`
  - `pure_protocol_evidence_manifest.json`: `fileCount=53`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=53`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `browserSuccessPayloadPcSessionLineageProposalCandidateCount=0`
  - `reset_terminal_boundary_audit.json`: `browserSuccessPayloadPcSessionLineageProposalCandidateCount=0`
- 已继续扩展到 collector response handler/value lineage：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_response_handler_value_lineage_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_response_handler_value_lineage_audit.json`
- collector response handler/value lineage 当前 checks：
  - `decodedRunCount=14`
  - `decodedSuccessRunCount=4`
  - `decodedFailureRunCount=3`
  - `successOnlyCommonHandlerCount=1`
  - `failureOnlyCommonHandlerCount=0`
  - `successRowsWithSuccessHandlerCount=4`
  - `failureRowsWithFailureHandlerCount=0`
  - `successRowsWithPx3PxdeCount=4`
  - `failureRowsWithPx3PxdeCount=3`
  - `handlerSurfacePromotedCount=0`
  - `handlerSurfaceNegativeControlsAllHold=true`
  - `finalResponsesAllMinusOne=true`
  - `cookieMutationFailureStillMutates=true`
  - `collectorToRiskSuccessChainProven=true`
  - `collectorServerClientVisibleProxyFoundCount=0`
  - `valueLineageRowCount=3`
  - `proposalCandidateCount=0`
  - `candidateIntakePromotedCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- collector response handler/value lineage 结论：
  - `oIIoIooo_success_value` 是 outcome，不是 pre-accept transition；
  - `_px3/_pxde` mutation 同时存在于成功与失败 controls，不能单独解释 risk/verify 成功；
  - handler surface key 没有晋升，success/failure 的公共 handler surface 不能形成最小可构造分叉；
  - 当前没有 handler key/value 可以成为 pre-accept、未被负控矛盾、pure-protocol constructible 的 transition。
- 已继续扩展到 `browser_downstream_create_or_continue_without_extracted_success` 专项审计：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_downstream_success_without_collector_decode_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/downstream_success_without_collector_decode_audit.json`
- downstream without collector decode 当前 checks：
  - `downstreamClassRunCount=55`
  - `runtimeTraceExistsCount=55`
  - `jsInternalTraceExistsCount=1`
  - `downstreamSuccessRunCount=2`
  - `collectorSuccessDecodeRunCount=0`
  - `parentSuccessRunCount=2`
  - `collectorFailureDecodeRunCount=0`
  - `allDownstreamRowsLackCollectorSuccessDecode=true`
  - `downstreamEvidenceIsPostAccept=true`
  - `serverVisibleDiffProposalCandidateCount=0`
  - `collectorResponseLineageProposalCandidateCount=0`
  - `collectorToRiskSuccessChainProven=true`
  - `proposalCandidateCount=0`
  - `candidateIntakePromotedCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- downstream without collector decode 结论：
  - 55 个下游类 run 均有 risk/verify 与 CreateAccount request；
  - 只有 2 个 run 出现 `state=continue`/`redirectUrl` 下游成功信号；
  - 0 个 run 有 decoded collector success `oIIoIooo|0`；
  - 因此该类 trace 是 outcome/classification 证据，不能作为 collector pre-accept root cause；
  - accepted collector -> risk/verify -> CreateAccount 链已由 `collector_to_risk_consumption_chain.json` 单独证明，不能倒推出 fresh collector success transition。
- 已继续扩展到 `collector_material_only` 专项审计：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_material_only_response_class_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_material_only_response_class_audit.json`
- collector material only 当前 checks：
  - `collectorMaterialOnlyRunCount=76`
  - `runtimeTraceExistsCount=76`
  - `jsInternalTraceExistsCount=4`
  - `collectorSuccessDecodeRunCount=0`
  - `collectorFailureDecodeRunCount=0`
  - `riskVerifyRequestRunCount=67`
  - `riskContinueRunCount=1`
  - `riskHumanChallengeRunCount=34`
  - `createRedirectRunCount=0`
  - `allRowsLackCollectorSuccessDecode=true`
  - `allRowsLackCreateRedirect=true`
  - `serverVisibleDiffProposalCandidateCount=0`
  - `collectorResponseLineageProposalCandidateCount=0`
  - `proposalCandidateCount=0`
  - `candidateIntakePromotedCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- collector material only 结论：
  - 76 个 run 都是 collector/browser material inventory，非 no-browser 成功；
  - 0 个 run 有 decoded collector success `oIIoIooo|0`；
  - 1 个 run 有 `risk continue` 字符串，但仍无 collector success decode、无 CreateAccount redirect，不能倒推出 collector pre-accept transition；
  - 因此该类 trace 不能晋升 proposal，只能作为负控/材料库存证据。
- 已继续扩展到 `low_value_or_unclassified` 专项闭合审计：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_low_value_unclassified_trace_closure_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/low_value_unclassified_trace_closure_audit.json`
- low value unclassified 当前 checks：
  - `lowValueRunCount=7`
  - `runtimeTraceExistsCount=4`
  - `jsInternalTraceExistsCount=6`
  - `rescannedProposalRelevantSignalRunCount=0`
  - `requestFailedRunCount=3`
  - `riskInitializeRunCount=3`
  - `allRowsRemainLowValue=true`
  - `candidateIntakePromotedCount=0`
  - `proposalCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- low value unclassified 结论：
  - 7 个 residual low-value run 经二次扫描仍没有 collector/risk/verify/cookie/wasm/parent success proposal-relevant token；
  - 其中 3 个仅有 `risk/initialize` + `requestfailed` 早期失败信号；
  - 它们不能形成 request/cookie/risk/verify 单 transition，也不能进入 fresh 网络实验。
- 已新增 unclassified trace class closure ledger 总账：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_unclassified_trace_class_closure_ledger.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unclassified_trace_class_closure_ledger.json`
- trace class closure ledger 当前 checks：
  - `reducedRunCount=162`
  - `ledgerClassCount=5`
  - `ledgerRunCount=162`
  - `classCountsMatchReduction=true`
  - `perClassClosureCountsMatch=true`
  - `unexpectedClassCount=0`
  - `missingExpectedClassCount=0`
  - `proposalCandidateTotal=0`
  - `candidateIntakePromotedCount=0`
  - `allTraceClassesClosed=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- trace class closure ledger 结论：
  - 162 个 reduced unclassified trace run 全部映射到 5 个已闭合类别；
  - 没有未识别类别，也没有缺失预期类别；
  - 所有类别总 proposal candidate 为 0；
  - trace-class inventory 已闭合，但不产生 fresh 网络准入。
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=39`, `passedTaskCount=39`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=27`, `passedStepCount=27`
  - `pure_protocol_evidence_manifest.json`: `fileCount=61`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=61`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `downstreamSuccessWithoutCollectorDecodeProposalCandidateCount=0`
  - `reset_terminal_boundary_audit.json`: `downstreamSuccessWithoutCollectorDecodeProposalCandidateCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `collectorMaterialOnlyResponseClassProposalCandidateCount=0`
  - `reset_terminal_boundary_audit.json`: `collectorMaterialOnlyResponseClassProposalCandidateCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `lowValueUnclassifiedTraceClosureProposalCandidateCount=0`
  - `reset_terminal_boundary_audit.json`: `lowValueUnclassifiedTraceClosureProposalCandidateCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `unclassifiedTraceClassClosureLedgerProposalCandidateTotal=0`
  - `reset_terminal_boundary_audit.json`: `unclassifiedTraceClassClosureLedgerProposalCandidateTotal=0`
- 当前下一步不能进入网络；需要选择新的本地证据维度，不再重复 request-class、payload/pc/session 单字段拆分、collector response handler/value outcome 拆分、downstream-without-collector-decode 归因、collector_material_only 材料库存归因、low_value residual trace 归因或 unclassified trace class 总账归因。
- 已新增 candidate source contradiction ledger，总结所有候选入口为何不能晋升：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_candidate_source_contradiction_ledger.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/candidate_source_contradiction_ledger.json`
- candidate source contradiction ledger 当前 checks：
  - `intakeRowCount=7`
  - `intakeAcceptedCount=0`
  - `intakeContradictedCount=7`
  - `gateRowCount=5`
  - `gateReadyCount=0`
  - `matrixRowCount=8`
  - `matrixReadyCount=0`
  - `matrixNoReadySingleTransitionCandidate=true`
  - `collectorClientVisibleProxyFoundCount=0`
  - `collectorServerStateBoundaryNotClientVisible=true`
  - `minimalExperimentBlockedByGate=true`
  - `minimalExperimentNetworkAttemptExecuted=false`
  - `promotedCandidateTotal=0`
  - `allCandidateSourcesClosed=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- candidate source contradiction ledger 结论：
  - 7 个 intake 来源、5 个 remaining-boundary gate row、8 个 single-transition matrix row 均未形成可执行候选；
  - 当前失败谓词集中在 `singleTransition`、`negativeControlNotContradicted`、`pureProtocolConstructible`；
  - collector expected-state 仍是 non-client-visible boundary；
  - 因此 IP/direct/Webshare/session 重试仍无 evidence-backed transition。
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=40`, `passedTaskCount=40`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=28`, `passedStepCount=28`
  - `pure_protocol_evidence_manifest.json`: `fileCount=63`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=63`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `candidateSourceContradictionLedgerPromotedTotal=0`
  - `reset_terminal_boundary_audit.json`: `candidateSourceContradictionLedgerPromotedTotal=0`
- 下一步不得再重复候选入口汇总。若继续推进，应只找能改变以下任一 promotion predicate 的新证据：
  - 把 non-client-visible collector server expected state 映射成一个 client-visible pre-accept token/transition；
  - 或把 coupled payload/pc/session/server-state boundary 约束成 exactly one pure-protocol-constructible transition；
  - 或找到现有负控没有覆盖、且能进入 request/cookie/risk/verify value chain 的新 runtime/network/cookie 事实。
- 已新增 server state value consumption ledger，从 seq4 response value mismatch 追到 final request/payload/cookie/risk 消费面：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_state_value_consumption_ledger.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_state_value_consumption_ledger.json`
- server state value consumption ledger 当前 checks：
  - `valueComparisonCount=11`
  - `valueMismatchCount=11`
  - `consumedValueCount=11`
  - `statusCounts.consumed_but_negative_controlled=3`
  - `statusCounts.downstream_or_failure_mutation_not_collector_acceptance=1`
  - `statusCounts.session_specific_not_request_isolated=4`
  - `statusCounts.consumed_but_coupled=3`
  - `allNegativeControlRefsExist=true`
  - `allRowsCoveredByControlOrCoupling=true`
  - `singleValueProposalReadyCount=0`
  - `serverStateModelFinalS00Success=true`
  - `serverStateModelFinalFreshRejected=true`
  - `line922DecodedFieldsEqual=true`
  - `stateLineageHasServerAcceptanceBoundary=true`
  - `encodedDecodedJsonEqual=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- server state value consumption ledger 结论：
  - seq4 response 的 11 个 value mismatch 全部被归入已负控消费面、coupled session/encoder 状态，或 session-specific 且未映射成可重放单 transition；
  - 没有任何单 value 可晋升为 fresh experiment proposal；
  - 这进一步收紧 H3/C6：剩余 server expected state 仍非 client-visible、非单字段、非纯协议可构造候选。
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=43`, `passedTaskCount=43`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=31`, `passedStepCount=31`
  - `pure_protocol_evidence_manifest.json`: `fileCount=69`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=69`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `serverStateValueConsumptionLedgerSingleValueProposalReadyCount=0`
  - `reset_terminal_boundary_audit.json`: `serverStateValueConsumptionLedgerSingleValueProposalReadyCount=0`
- 已新增 coupled boundary terminal ledger，把 C4 outer tuple、C5 encoded/session/encoder、C6 server state value 三类耦合边界合并成终态判定：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_coupled_boundary_terminal_ledger.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coupled_boundary_terminal_ledger.json`
- coupled boundary terminal ledger 当前 checks：
  - `allInputsExist=true`
  - `finalMatrixNoBoundaryAllowsFreshExperiment=true`
  - `coupledBoundaryRowCount=3`
  - `proposalReadyRowCount=0`
  - `outerTupleClosedNoSingle=true`
  - `encodedSessionSingleAxisEliminated=true`
  - `encoderVariantFamilyClosedNoSuccess=true`
  - `serverStateValueSingleReadyCount=0`
  - `serverStateValueAllCovered=true`
  - `collectorServerStateNotClientVisible=true`
  - `candidateSourcePromotedTotal=0`
  - `allCoupledBoundariesClosedForCurrentEvidence=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- coupled boundary terminal ledger 结论：
  - C4 没有 single outer/session field；
  - C5 已把 encoder variant family 收敛到一个 coherent live probe，且 fresh Webshare probe 未产生 collector success，seq5 返回 `do=""`；
  - C6 仍是 non-client-visible server state boundary，所有 value mismatch 已被负控或耦合解释覆盖；
  - 当前没有 exactly-one、pre-accept、client-visible、pure-protocol-constructible transition。
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=43`, `passedTaskCount=43`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=31`, `passedStepCount=31`
  - `pure_protocol_evidence_manifest.json`: `fileCount=69`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=69`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `coupledBoundaryTerminalLedgerProposalReadyRowCount=0`
  - `reset_terminal_boundary_audit.json`: `coupledBoundaryTerminalLedgerProposalReadyRowCount=0`
- 已新增 current evidence entrance terminal ledger，审计历史 artifact 中的 `nextArtifact` / `nextScript` 指针，防止被旧执行提示重新牵引：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_current_evidence_entrance_terminal_ledger.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json`
- current evidence entrance terminal ledger 当前 checks：
  - `allInputsExist=true`
  - `scannedDirectoryCount=3`
  - `nextPointerCount=54`
  - `unresolvedNextPointerCount=0`
  - `readySignalNextPointerCount=1`
  - `activeActionableNextPointerCount=0`
  - `currentPromotedSingleTransitionCandidateCount=0`
  - `hypothesisPlanStaleHistoricalNextPointerCount=14`
  - `hypothesisPlanAllHypothesesCovered=true`
  - `allKnownLocalEvidenceEntrancesClosed=true`
  - `allCoupledBoundariesClosedForCurrentEvidence=true`
  - `completionNoCurrentExperimentRoute=true`
  - `resetNoCurrentRouteToPhase5=true`
  - `goalCompletionVerified=false`
  - `allNextPointersClosedOrSuperseded=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- current evidence entrance terminal ledger 结论：
  - 54 个历史 next 指针均已 materialized 或被当前 terminal authority supersede；
  - 1 个历史 ready 信号不是 active actionable，因为当前 promoted transition count 仍为 0；
  - 当前没有未闭合的本地 artifact 入口，也没有可执行 fresh 网络入口。
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=44`, `passedTaskCount=44`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=32`, `passedStepCount=32`
  - `pure_protocol_evidence_manifest.json`: `fileCount=71`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=71`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `currentEvidenceEntranceTerminalLedgerActiveActionableNextPointerCount=0`
  - `reset_terminal_boundary_audit.json`: `currentEvidenceEntranceTerminalLedgerActiveActionableNextPointerCount=0`
- 已新增 external output surface audit，审计 `output/outlook_oauth_trace`、`output/har_extract`、`output/proxy_bridge`、`output/run_logs`、`output/logs` 这 5 个外部 output 面：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_external_output_surface_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/external_output_surface_audit.json`
- external output surface audit 当前 checks：
  - `allInputsExist=true`
  - `scanDirectoryCount=5`
  - `existingScanDirectoryCount=5`
  - `signalFileCount=11`
  - `categoryCount=4`
  - `collectorSuccess0SignalFileCount=0`
  - `proposalWorthyExternalSignalCount=0`
  - `currentEvidenceEntrancesClosed=true`
  - `nonJsonReplayableSuccessCount=0`
  - `rawProposalWorthySignalCount=0`
  - `resetNoCurrentRouteToPhase5=true`
  - `goalCompletionVerified=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- external output surface audit 结论：
  - 外部 output 面只有 static/HAR fixture、OAuth/downstream、proxy/log/runtime material context；
  - 没有 fresh no-browser `oIIoIooo|0`；
  - 没有可晋升为 pre-accept、client-visible、pure-protocol-constructible transition 的信号。
- 已新增 evidence package surface audit，审计 `output/evidence_packages`、`output/browser-tests` 这 2 个打包证据/浏览器测试面：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_evidence_package_surface_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/evidence_package_surface_audit.json`
- evidence package surface audit 当前 checks：
  - `allInputsExist=true`
  - `scanDirectoryCount=2`
  - `existingScanDirectoryCount=2`
  - `textFileCount=173`
  - `imageFileCount=4`
  - `zipFileCount=1`
  - `signalFileCount=84`
  - `categoryCount=6`
  - `collectorSuccess0SignalFileCount=5`
  - `proposalWorthyEvidencePackageSignalCount=0`
  - `externalOutputProposalWorthySignalCount=0`
  - `currentEvidenceEntrancesClosed=true`
  - `resetNoCurrentRouteToPhase5=true`
  - `goalCompletionVerified=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- evidence package surface audit 结论：
  - 打包证据面确有 5 个 collector success0 信号，但分类均为 historical packaged browser success reference；
  - 这些信号不是 fresh no-browser replayable 成功样本；
  - 没有产生可晋升为 pre-accept、client-visible、pure-protocol-constructible transition 的 proposal-worthy 信号。
- 已新增 CTF-reg output surface audit，审计 `CTF-reg/output` 这个独立本地证据面：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_ctf_reg_output_surface_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/ctf_reg_output_surface_audit.json`
- CTF-reg output surface audit 当前 checks：
  - `allInputsExist=true`
  - `scanDirectoryCount=1`
  - `existingScanDirectoryCount=1`
  - `textFileCount=63`
  - `imageFileCount=29`
  - `sqliteFileCount=1`
  - `skippedFileCount=8`
  - `signalFileCount=63`
  - `categoryCount=5`
  - `collectorSuccess0SignalFileCount=0`
  - `proposalWorthyCtfRegSignalCount=0`
  - `evidencePackageProposalWorthySignalCount=0`
  - `currentEvidenceEntrancesClosed=true`
  - `resetNoCurrentRouteToPhase5=true`
  - `goalCompletionVerified=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- CTF-reg output surface audit 结论：
  - `CTF-reg/output` 主要包含 Outlook webmail/browser/static-cache/account artifacts、图片和本地 account sqlite；
  - 没有 collector success0 信号；
  - 没有 fresh no-browser replayable HUMAN success；
  - 没有可晋升为 pre-accept、client-visible、pure-protocol-constructible transition 的 proposal-worthy 信号。
- 已新增 auxiliary trace surface audit，审计 `CTF-reg/outputs` 与 `tem` 这两个辅助 trace/HAR/HTML 证据面：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_auxiliary_trace_surface_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/auxiliary_trace_surface_audit.json`
- auxiliary trace surface audit 当前 checks：
  - `allInputsExist=true`
  - `scanDirectoryCount=2`
  - `existingScanDirectoryCount=2`
  - `textFileCount=26`
  - `harFileCount=7`
  - `jsonlFileCount=14`
  - `htmlFileCount=5`
  - `skippedFileCount=1`
  - `signalFileCount=25`
  - `categoryCount=5`
  - `collectorSuccess0SignalFileCount=0`
  - `proposalWorthyAuxiliarySignalCount=0`
  - `ctfRegProposalWorthySignalCount=0`
  - `currentEvidenceEntrancesClosed=true`
  - `resetNoCurrentRouteToPhase5=true`
  - `goalCompletionVerified=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- auxiliary trace surface audit 结论：
  - `CTF-reg/outputs` 是 ChatGPT auth trace；
  - `tem` 主要是 PayPal/Stripe HAR/HTML；
  - 这些辅助 trace 不属于 Outlook signup HUMAN collector replay chain；
  - 没有 collector `oIIoIooo|0`；
  - 没有可晋升为 pre-accept、client-visible、pure-protocol-constructible transition 的 proposal-worthy 信号。
- 已新增 stale positive signal authority audit，审计 `output/protocol_reverse` 内所有看似正向的 ready/goal/proposal/network 信号，防止旧 ready 产物重新牵引执行：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_stale_positive_signal_authority_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/stale_positive_signal_authority_audit.json`
- stale positive signal authority audit 当前 checks：
  - `allInputsExist=true`
  - `scannedJsonFileCount=1341`
  - `positiveSignalCount=5`
  - `activeActionablePositiveSignalCount=0`
  - `supersededOrNonAuthoritativePositiveSignalCount=5`
  - `staleReadyArtifactCount=2`
  - `currentEvidenceActiveActionableNextPointerCount=0`
  - `candidateIntakePromotedCount=0`
  - `completionNoCurrentExperimentRoute=true`
  - `resetNoCurrentRouteToPhase5=true`
  - `goalCompletionVerified=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- stale positive signal authority audit 结论：
  - 5 个正向信号全部是 superseded、historical pointer 或 requirement expression；
  - 旧 `coherent_encoder_variant_experiment_manifest.json` 的 ready 信号已由 live probe no-success 与 current route authority 关闭；
  - 当前没有 active actionable ready/proposal/network/goal-complete 信号；
  - 因此不能基于旧 ready artifact 进入 fresh 网络实验。
- 当前证据链状态：
  - `proof_script_reproducibility_audit.json`: `taskCount=48`, `passedTaskCount=48`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=36`, `passedStepCount=36`
  - `pure_protocol_evidence_manifest.json`: `fileCount=79`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=79`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `externalOutputSurfaceAuditProposalWorthySignalCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `evidencePackageSurfaceAuditProposalWorthySignalCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `ctfRegOutputSurfaceAuditProposalWorthySignalCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `auxiliaryTraceSurfaceAuditProposalWorthySignalCount=0`
  - `pure_protocol_completion_requirements_audit.json`: `stalePositiveSignalAuthorityActiveActionablePositiveSignalCount=0`
  - `reset_terminal_boundary_audit.json`: `externalOutputSurfaceAuditProposalWorthySignalCount=0`
  - `reset_terminal_boundary_audit.json`: `evidencePackageSurfaceAuditProposalWorthySignalCount=0`
  - `reset_terminal_boundary_audit.json`: `ctfRegOutputSurfaceAuditProposalWorthySignalCount=0`
  - `reset_terminal_boundary_audit.json`: `auxiliaryTraceSurfaceAuditProposalWorthySignalCount=0`
  - `reset_terminal_boundary_audit.json`: `stalePositiveSignalAuthorityActiveActionablePositiveSignalCount=0`

当前不执行：

- direct 多试；
- Webshare 多试；
- 每次换 session 撞结果；
- 未经 proposal/intake 的 fresh 请求；
- 单纯 WASM material hook 补证据。

## 6. 更新规则

每新增或修改关键 artifact，必须同步更新本文档或新增同级修订文档，记录：

- 新增 evidence path；
- 关键 checks；
- 是否改变 `readyForFreshExperiment`；
- 是否改变 `goalComplete`；
- 是否产生 proposal；
- 若没有证据，下一步只能继续找证据。
