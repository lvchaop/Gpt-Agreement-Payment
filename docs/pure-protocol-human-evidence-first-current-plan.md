# 纯协议 HUMAN 成功复现：证据优先当前执行计划

日期：2026-06-13

## 0. 文档地位

后续实现以本文档为当前执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-first-current-plan.md`

历史计划只作为证据索引和设计输入，不作为线性执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-authoritative-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`

本文档不是完成证明。最终目标只能由 fresh、no-browser、pure-protocol 端到端成功产物证明。

## 1. 最终目标不变

实现并验证完整 fresh pure-protocol HUMAN 成功闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP、JS 解析、加密、payload 构造、请求重放；
3. 从 Outlook signup fresh session 推进到 HUMAN collector 成功；
4. collector decoded response 出现成功事件；
5. `_px` cookie/token jar mutation 可复现；
6. `/API/Proofs/risk/verify` 返回 `state=continue`；
7. `/API/CreateAccount` 返回 `redirectUrl`；
8. 每一步都有本地证据路径、脚本、输入输出 artifact、可复现命令。

最终完成必须同时满足：

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

## 2. 当前事实基线

### 2.1 当前没有可执行 promoted transition

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_intake.json`

当前 checks：

- `proposalCount=0`
- `candidateCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前不能直接跑 fresh 网络；
- 当前缺的是可证据晋升的单 transition，不是命令权限、网络权限或重试次数。

### 2.2 proposal schema 为空但 lint/control 有效

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals_lint.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals_lint_controls.json`

当前 checks：

- `proposalCount=0`
- `validProposalCount=0`
- `invalidProposalCount=0`
- `promotableShapeCount=0`
- `allProposalsStructurallyValid=true`
- `controlCount=4`
- `passedControlCount=4`
- `failedControlCount=0`
- `allControlsPassed=true`

结论：

- proposal 入口可用；
- 后续任何新假设必须先落入 proposal schema，再经过 lint 和 intake。

### 2.3 Phase 3 已证明当前本地证据没有 proposal-worthy 信号

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_proposal_evidence_triage.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_evidence_entrance_coverage_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_raw_evidence_entrance_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/phase3_raw_trace_crosswalk_audit.json`

当前 checks：

- `proposalWorthyEvidenceCount=0`
- `recursiveJsonReadyOrPromotedSignalCount=0`
- `entranceRowCount=5`
- `coveredEntranceRowCount=5`
- `uncoveredEntranceRowCount=0`
- `rawSuccessSignalFileCount=115`
- `proposalWorthyRawSignalCount=0`
- `unindexedBrowserTraceSignalCount=87`
- `crosswalkRowCount=87`
- `referencedTraceCount=87`
- `unreferencedTraceCount=0`
- `proposalWorthyRawTraceCount=0`

结论：

- 当前已知入口不是没看，而是看完后没有晋升候选；
- 后续不能继续在这些已闭合入口里反复寻找同一类解释，除非先产生新 artifact 或新分类维度。

### 2.4 trace classifier 有覆盖缺口，但不是 promoted transition

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/trace_classifier_raw_coverage_gap_audit.json`

当前 checks：

- `classifierRunCount=14`
- `rawBrowserSuccessRunCount=84`
- `rawBrowserSuccessRunsNotInClassifierCount=73`
- `crosswalkUnclassifiedRowCount=87`
- `referencedButUnclassifiedRawTraceCount=87`
- `unreferencedRawTraceCount=0`
- `safeToAutoAppendToClassifier=false`
- `proposalWorthyCoverageGapCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 不能再说 classifier 覆盖了所有 raw browser success trace；
- 但该缺口已经被 crosswalk 证明不是未引用的新成功证据入口；
- 后续如要补 classifier，必须生成等价 `trace_classification_*.json`，不能把 raw trace 自动塞进 classifier。

### 2.5 端到端 PoC 和 final replay 当前都未执行

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`

当前 checks：

- `networkAttemptExecuted=false`
- `blockedByGate=true`
- `freshNoBrowserCollectorSuccess=false`
- `freshDecodedOIIoIooo0=false`
- `freshDecodedPxJarReplayed=false`
- `freshRiskVerifyContinue=false`
- `freshCreateAccountRedirectUrl=false`
- `replayAttemptExecuted=false`
- `readyForFreshReplay=false`
- `goalComplete=false`

结论：

- 目标未完成；
- gate chain、manifest、离线子能力通过，都不能替代 fresh 端到端成功。

### 2.5.1 剩余边界不满足 proposal 晋升条件

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_boundary_proposal_gate_audit.json`

当前 checks：

- `proposalGateRowCount=5`
- `proposalReadyRowCount=0`
- `proposalFileProposalCount=0`
- `candidateIntakePromotedCount=0`
- `singleTransitionMatrixReadyCount=0`
- `singleTransitionMatrixNoReadyCandidate=true`
- `serverLineageHasOuterTupleBoundary=true`
- `serverLineageHasEncoderBindingBoundary=true`
- `serverLineageHasServerAcceptanceStateBoundary=true`
- `outerSingleReadyGroupCount=0`
- `encoderRemainingAxisCount=2`
- `serverExpectedStateClientVisibleProxyCount=0`
- `serverExpectedStateTransitionHasReplayableClientRepresentation=false`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前剩余五类边界逐项套入 proposal schema 后，没有任何一项可写入 promoted proposal；
- outer/session tuple 仍是耦合组；
- pc/marker/uuid/payload encoder binding 仍是两轴耦合族；
- collector server expected state 当前没有 client-visible、replayable 表示；
- collector success -> risk/verify -> CreateAccount 已证明是下游消费链，但不是 fresh collector rejection 的根因候选；
- browser cookie bridge 已被失败样本和无 Cookie header 负控覆盖。

### 2.5.2 本地 trace 证据覆盖已发现新增浏览器成功样本，但仍不能晋升 proposal

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/local_trace_evidence_freshness_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unclassified_trace_signal_reduction_audit.json`

当前 freshness checks：

- `runtimeTraceCount=172`
- `jsTraceCount=45`
- `inventoryRuntimeTraceCount=157`
- `inventoryJsTraceCount=36`
- `inventoryRuntimeCountMatchesCurrent=false`
- `inventoryJsCountMatchesCurrent=false`
- `unclassifiedRunCount=162`
- `unclassifiedHighValueSignalRunCount=79`
- `unclassifiedCollectorMaterialRunCount=155`
- `proposalWorthyNowCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

当前 reduction checks：

- `reducedRunCount=162`
- `browserSuccessChainRunCount=18`
- `browserParentSuccessCookieChainRunCount=6`
- `collectorMaterialOnlyRunCount=76`
- `proposalReadyRunCount=0`
- `classificationEvidenceOnly=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前工作区确实比旧 inventory 多出本地 runtime/js trace；
- 未分类 trace 中存在浏览器成功链证据，可用于补分类器/覆盖审计；
- 这些证据仍是 browser runtime/js trace，不是 no-browser pure-protocol 成功；
- 归约后没有任何 run 满足 proposal 八字段，不能触发 fresh 网络。

### 2.6 当前离线审计链稳定

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`

当前 checks：

- `taskCount=31`
- `passedTaskCount=31`
- `stepCount=19`
- `passedStepCount=19`
- `manifestFileCount=44`
- `hashMismatchCount=0`
- `allHashesMatch=true`
- `proofScriptTaskCount=31`
- `evidenceGateChainStepCount=19`
- `evidenceManifestFileCount=44`

结论：

- 现有离线结论可复现；
- 后续每新增关键脚本或 artifact，必须重新跑这条链。

### 2.7 completion verifier 当前明确未完成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

当前 checks：

- `blockingRequirementCount=4`
- `freshSuccessMissing=true`
- `noCurrentExperimentRoute=true`
- `evidenceGatedPocNetworkAttemptExecuted=false`
- `candidateIntakePromotedCount=0`
- `traceClassifierReferencedButUnclassifiedRawTraceCount=87`
- `traceClassifierSafeToAutoAppend=false`
- `traceClassifierProposalWorthyCoverageGapCount=0`
- `completionVerified=false`
- `finalReplayGoalComplete=false`
- `remainingBoundaryProposalReadyRowCount=0`
- `localTraceProposalWorthyNowCount=0`
- `unclassifiedTraceProposalReadyRunCount=0`
- `blockingOrMissing=["end_to_end_pure_protocol_poc"]`
- `goalComplete=false`

结论：

- 当前唯一最终缺口仍是 end-to-end pure-protocol PoC；
- 但进入 PoC 前必须先找到一个 evidence-backed promoted transition；
- 当前剩余边界没有任何 proposal-ready row；
- 新发现的未分类浏览器 trace 只增加分类/覆盖证据，不改变 fresh 实验准入。

## 3. 方法论

### 3.1 从目标反推，不从旧证据惯性推进

执行顺序固定为：

1. 最终成功条件；
2. 当前阻塞字段；
3. 阻塞字段需要的最小新增事实；
4. 能产生该事实的本地证据入口；
5. 若本地证据不足，才设计最小 fresh 实验；
6. fresh 实验只能验证一个 promoted transition。

禁止行为：

- 看到历史 success token 就推断当前可复现；
- 看到 success-only hook 就推断其为原因；
- 看到 IP / Webshare / direct 差异就直接网络重试；
- 看到 WASM/glue 复杂就默认缺口在 WASM；
- 把 decoded equality 当成成功充分条件。

### 3.2 证据优先级

冲突时按以下顺序裁决：

1. fresh live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage / session timeline；
6. 静态 JS；
7. 推断。

低优先级证据只能生成假设，不能覆盖高优先级证据。

### 3.3 candidate promotion 标准

新 proposal 必须包含：

- `id`
- `evidence`
- `preAccept`
- `clientVisible`
- `pureProtocolConstructible`
- `valueChain`
- `negativeControlRefs`
- `contradicted`

晋升门槛：

1. `preAccept=true`
2. `clientVisible=true`
3. `pureProtocolConstructible=true`
4. `valueChain` 属于 `request|cookie|risk|verify`
5. `negativeControlRefs` 非空
6. `contradicted=false`
7. lint structurally valid
8. candidate intake 输出 `promotedSingleTransitionCandidateCount=1`
9. candidate intake 输出 `readyForFreshExperiment=true`

不满足任一项，不进入网络实验。

### 3.4 transport/IP 处理

IP、Webshare、direct 只作为 transport 控制变量，不作为独立解释。

允许：

- 在同一个 promoted transition 下做 direct/Webshare 对照；
- 每次 fresh attempt 使用新 session；
- 同一 attempt 内记录 transport、session、cookie、request/response；
- 将 transport 证据写入对应 experiment artifact。

禁止：

- 没有 promoted transition 时多换 IP 重试；
- 用“可能是 IP”绕过 candidate gate；
- 混用旧 session 结论解释 fresh session；
- 用 direct/Webshare 差异替代 request/cookie/risk/verify 价值链证据。

## 4. 当前执行计划

### Phase A: 固化当前事实，不再重复旧路线

目标：

- 保持当前 31 项 proof、19 步 gate chain、44 文件 manifest 可复现；
- 每次新增 artifact 后立即更新 manifest、gate chain、completion verifier。

验证命令：

```bash
python3 -m py_compile \
  tools/audit_trace_classifier_raw_coverage_gap.py \
  tools/build_proof_script_reproducibility_audit.py \
  tools/run_pure_protocol_evidence_gate_chain.py \
  tools/build_pure_protocol_evidence_manifest.py \
  tools/verify_pure_protocol_evidence_manifest.py \
  tools/verify_pure_protocol_goal_completion.py \
  tools/build_pure_protocol_completion_requirements_audit.py \
  tools/build_reset_terminal_boundary_audit.py \
  tools/audit_pure_protocol_goal_gap.py

python3 tools/build_proof_script_reproducibility_audit.py
python3 tools/run_pure_protocol_evidence_gate_chain.py
python3 tools/build_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_evidence_manifest.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/build_reset_terminal_boundary_audit.py
python3 tools/audit_pure_protocol_goal_gap.py
python3 tools/verify_pure_protocol_goal_completion.py
```

通过标准：

- `taskCount=31`
- `passedTaskCount=31`
- `stepCount=19`
- `passedStepCount=19`
- `manifestFileCount=44`
- `hashMismatchCount=0`
- `completionVerified=false`
- `goalComplete=false`

### Phase B: 重新找“最小可晋升 transition”，不是重试网络

目标：

- 找到一个能改变 server 决策的、client-visible、pure-protocol-constructible transition；
- 输出 proposal，而不是直接实验。

优先证据入口：

1. 现有 raw browser traces 的未结构化差异，但不能重复使用已被 crosswalk 判定为 referenced 的 success token；
2. collector request 与 decoded response 的最早分叉字段；
3. `_px` jar mutation 前后的最小 server-visible 差异；
4. risk/verify request 中可由 collector response 或 cookie 价值链解释的字段；
5. CreateAccount 前最后一个可见状态转移；
6. trace classifier 覆盖缺口的等价 `trace_classification_*.json` 生成，不把 raw trace 自动并入 classifier。

产物要求：

- 若发现候选，写入：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`
- 然后运行：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/lint_promoted_transition_candidate_proposals.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promoted_transition_candidate_intake.py`

通过标准：

- `promotedSingleTransitionCandidateCount=1`
- `readyForFreshExperiment=true`

失败标准：

- `pureProtocolConstructible=false`
- `negativeControlRefs` 为空
- `contradicted=true`
- 只能解释浏览器行为，不能形成 request/cookie/risk/verify 价值链

当前新增 proposal gate 审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_remaining_boundary_proposal_gate_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_boundary_proposal_gate_audit.json`

该审计把当前剩余边界直接套入 proposal schema；当前 `proposalReadyRowCount=0`，因此仍不能进入 fresh 网络实验。

当前新增本地 trace 新鲜度与归约审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_local_trace_evidence_freshness_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/local_trace_evidence_freshness_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_unclassified_trace_signal_reduction_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unclassified_trace_signal_reduction_audit.json`

当前发现旧 inventory 覆盖落后于工作区现状：`runtimeTraceCount=172`、`jsTraceCount=45`，而旧 inventory 为 `157/36`；归约后 `browserSuccessChainRunCount=18`，但 `proposalReadyRunCount=0`。

### Phase C: 最小 fresh 实验

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

执行前置条件：

- Phase B 通过；
- 只有一个 promoted transition；
- 每次 fresh attempt 换 session。

必须记录：

- session id；
- transport：direct 或 Webshare；
- Webshare session 标识；
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

如果失败：

- 只允许根据失败 response 与负控结果更新 proposal/intake；
- 不允许无差别换 IP/换 session 继续撞。

### Phase D: evidence-gated end-to-end PoC

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

执行前置条件：

- Phase C 成功；
- minimal transition 已证明能推进阶段。

通过标准：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`

### Phase E: final replay audit

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_final_pure_protocol_replay_audit.py`

通过标准：

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

### Phase F: completion verification

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

通过标准：

- `completionVerified=true`
- `goalComplete=true`

只有 Phase F 通过，才允许宣告最终目标完成。

## 5. 立即下一步

当前不是网络阶段。下一步是 Phase B：

1. 不再把当前五类剩余边界直接写 proposal，因为 proposal gate 已证明 `proposalReadyRowCount=0`；
2. 不把新增 browser success trace 当 no-browser 成功，因为 unclassified reduction 已证明 `proposalReadyRunCount=0`；
3. 下一步只能寻找新的证据入口或新分类维度，目标是改变 proposal 八字段之一；
4. 若新 artifact 支持候选，写入 proposal schema；
5. 跑 lint 和 candidate intake；
6. 只有 intake 晋升 exactly one candidate，才进入 minimal fresh experiment。

当前不执行：

- direct 多试几次；
- Webshare 同会话同 IP 多试几次；
- 每次新尝试换 session 的网络批量实验；
- wasm material hook 的离线补证据，除非它直接产出 `pureProtocolConstructible=true` 的 proposal；
- 未经 proposal/intake 的临时网络脚本。

## 6. 计划更新规则

每次新增或修改关键 artifact 后，必须同步更新本文档：

- 新增 evidence path；
- 新增或变化的 checks；
- 对当前 phase 的影响；
- 是否改变 `readyForFreshExperiment`；
- 是否改变 `goalComplete`。

不写无证据判断。缺证据时，下一步只能是找证据。
