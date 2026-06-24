# 纯协议 HUMAN 成功复现：下一轮证据驱动实现计划

日期：2026-06-13

## 0. 文档地位

后续实现以本文档作为新的线性执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-next-execution-plan.md`

上一版收敛计划作为证据背景，不再作为下一步执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-convergent-plan.md`

本文档不改变最终目标，不声明目标完成；它只规定接下来如何避免被旧证据、旧 positive signal、IP/direct/Webshare 猜测、WASM/material 单点线索牵着走。

## 1. 最终目标不变

最终目标仍是实现并验证 fresh、no-browser、pure-protocol HUMAN 成功闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP、JS 解析、加密、payload 构造、请求重放；
3. fresh Outlook signup session 推进到 HUMAN collector success；
4. decoded collector response 出现成功事件；
5. `_px` cookie/token jar mutation 可复现；
6. `/API/Proofs/risk/verify` 返回 `state=continue`；
7. `/API/CreateAccount` 返回 `redirectUrl`；
8. 所有关键结论都有本地证据路径、脚本、输入输出 artifact、hash 或可复现命令。

最终完成只接受以下 artifact 的正向结果：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`

目标完成字段必须同时满足：

- `networkAttemptExecuted=true`
- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`
- `replayAttemptExecuted=true`
- `completionVerified=true`
- `goalComplete=true`

## 2. 当前证据基线

本节只记录已由本地 artifact 证明的状态，禁止推断。

### 2.1 当前 proof/gate 链稳定，但不是完成证明

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`

当前关键字段：

- `taskCount=58`
- `passedTaskCount=58`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`
- `stepCount=46`
- `passedStepCount=46`
- `failedStepCount=0`
- `allStepsPassed=true`
- `allHashesMatch=true`

结论：

- 离线证据链可复现；
- 这只证明已有离线审计稳定，不证明 fresh no-browser 成功。

### 2.2 当前 completion verifier 明确未完成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`

当前关键字段：

- `inputCount=15`
- `failedGateCount=44`
- `completionVerified=false`
- `goalComplete=false`
- `readyForFreshExperiment=false`

结论：

- 不能声明最终目标完成；
- 当前没有 fresh 网络实验准入；
- “权限已开、网络可用、可以直连”不等于 `readyForFreshExperiment=true`。

### 2.3 当前 nearest-miss 前 10 个候选已被现有控制实验关闭

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/nearest_miss_promotion_candidate_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/nearest_miss_blocker_resolution_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_nearest_miss_resolution_audit.json`

当前关键字段：

- `candidateRowCount=32`
- `nearestSatisfiedPredicateCount=6`
- `nearestMissingPredicateCount=2`
- `proposalReadyCandidateCount=0`
- `singleMissingPredicateCandidateCount=0`
- `closedByExistingControlsCount=2`
- `remainingNearestRowCount=8`
- `closedByExistingControlsCount=8`
- `openRemainingNearestRowCount=0`

结论：

- `pc_value` 和 `collector_cookie_header` 已关闭；
- remaining nearest-miss top10 已关闭；
- 但 32 个候选是否全部被逐项关闭，还需要下一轮 exhaustive audit 证明。

## 3. 方法论

下一轮执行采用“反证驱动的候选穷尽法”，而不是继续补散点证据。

固定顺序：

1. 从 final verifier 失败字段反推还缺什么；
2. 从缺口映射到候选晋升八字段；
3. 对当前候选全集做穷尽分类；
4. 每个候选只能进入三种状态之一：
   - `closedByExistingControls`
   - `openNeedsSpecificEvidence`
   - `proposalReady`
5. 如果 `proposalReady=0` 且 `openNeedsSpecificEvidence=0`，说明当前候选全集耗尽，必须回到证据入口发现，而不是网络重试；
6. 如果 `openNeedsSpecificEvidence>0`，只补该候选缺失的最小事实；
7. 如果 `proposalReady=1`，才写入 promoted proposal 并进入 fresh gate；
8. 如果 `proposalReady>1`，必须继续归约到 exactly one transition。

候选晋升八字段不变：

1. `preAccept=true`
2. `clientVisible=true`
3. `pureProtocolConstructible=true`
4. `valueChain=true`
5. `negativeControlNotContradicted=true`
6. `singleTransition=true`
7. `artifactBacked=true`
8. `staleAuthorityClean=true`

## 4. 当前禁止事项

在 `readyForFreshExperiment=false` 时禁止：

- direct/Webshare/IP/session fresh 重试；
- “同一会话同一 IP 多试几次”；
- 每次新尝试换 session 的网络实验；
- 用旧 ready/proposal/next pointer 打开实验；
- 用 browser success trace 冒充 no-browser success；
- 用 WASM/material hook 复杂度默认解释失败；
- 用 IP、Webshare、直连差异单独作为根因；
- 用 decoded equality 默认推出 server accept；
- 绕过 promoted-transition gate 手动跑 live runner。

这些禁止项不是权限限制，而是证据门限制。

## 5. 下一轮实现计划

### Phase A：锁定当前基线

目的：

- 确认新计划开始前没有 artifact 漂移；
- 作为后续每次修改后的回归入口。

命令：

```bash
python3 -m py_compile \
  tools/build_proof_script_reproducibility_audit.py \
  tools/run_pure_protocol_evidence_gate_chain.py \
  tools/build_pure_protocol_evidence_manifest.py \
  tools/verify_pure_protocol_evidence_manifest.py \
  tools/verify_pure_protocol_goal_completion.py

python3 tools/build_proof_script_reproducibility_audit.py
python3 tools/run_pure_protocol_evidence_gate_chain.py
python3 tools/build_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_goal_completion.py
```

通过标准：

- `allProofScriptsReproducible=true`
- `allStepsPassed=true`
- `allHashesMatch=true`
- `completionVerified=false`
- `goalComplete=false`
- `readyForFreshExperiment=false`

### Phase B：扩展 nearest-miss artifact 到候选全集

目的：

- 当前 `nearest_miss_promotion_candidate_audit.json` 只暴露 `nearestRows`，但 checks 已证明内部有 `candidateRowCount=32`；
- 下一步需要把 32 个候选全部落盘，避免只看 top10 被旧排序牵着走。

修改目标：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_nearest_miss_promotion_candidate_audit.py`

输出目标：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/nearest_miss_promotion_candidate_audit.json`

新增或确认字段：

- `allRows`
- `checks.allRowCount`
- `checks.candidateRowCount=32`
- `checks.proposalReadyCandidateCount=0`

通过标准：

- `len(allRows)==candidateRowCount`
- 原有 checks 不退化；
- proof/gate/manifest 仍通过。

### Phase C：构建候选全集关闭审计

目的：

- 对 32 个候选逐项分类；
- 证明是否还有非 top10 的 open candidate；
- 把“是不是陷入死胡同”转成可验证数据。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_exhaustive_promotion_candidate_resolution_audit.py`

新增 artifact：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/exhaustive_promotion_candidate_resolution_audit.json`

输入证据：

- `nearest_miss_promotion_candidate_audit.json`
- `nearest_miss_blocker_resolution_audit.json`
- `remaining_nearest_miss_resolution_audit.json`
- `promotion_predicate_blocker_crosswalk.json`
- `candidate_source_contradiction_ledger.json`
- `candidate_executor_readiness_audit.json`
- `hypothesis_tree_current_authority_audit.json`
- 与各候选对应的负控、lineage、bridge、state、transport、WASM/material 审计 artifact

必须输出字段：

- `candidateRowCount`
- `resolvedCandidateCount`
- `closedByExistingControlsCount`
- `openNeedsSpecificEvidenceCount`
- `proposalReadyCandidateCount`
- `unresolvedCandidateIds`
- `proposalReadyCandidateIds`
- `openNeedsSpecificEvidenceRows`
- `readyForFreshExperiment`
- `goalComplete`

每个候选行必须输出：

- `candidateId`
- `satisfiedPredicateCount`
- `missingPredicates`
- `resolutionStatus`
- `closureReason`
- `evidencePaths`
- `nextMinimalFact`

通过标准分支：

- 如果 `proposalReadyCandidateCount=0` 且 `openNeedsSpecificEvidenceCount=0`：
  - 当前候选全集耗尽；
  - 进入 Phase D，重新发现证据入口。
- 如果 `proposalReadyCandidateCount=0` 且 `openNeedsSpecificEvidenceCount>0`：
  - 进入 Phase E，只补 open rows 的最小事实。
- 如果 `proposalReadyCandidateCount=1`：
  - 进入 Phase F，写入 promoted proposal。
- 如果 `proposalReadyCandidateCount>1`：
  - 先归约候选，不能网络实验。

### Phase D：候选全集耗尽后的证据入口再发现

触发条件：

- Phase C 输出 `proposalReadyCandidateCount=0`
- Phase C 输出 `openNeedsSpecificEvidenceCount=0`

目的：

- 如果 32 个候选全部关闭，不能继续围绕这 32 个候选打转；
- 需要从未覆盖 evidence surface 找新入口，而不是网络重试。

优先审计方向：

1. manifest 已覆盖目录外是否存在新的 high-value evidence surface；
2. runtime trace 中是否有未被候选模型编码的 pre-accept client-visible transition；
3. collector request/response 中是否有未入候选模型的 state mutation；
4. cookie/storage/session timeline 中是否有未入候选模型的 accept 前变化；
5. static JS glue/WASM material 是否只影响构造，还是能产生新的 server-visible transition。

计划产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_next_evidence_surface_discovery_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/next_evidence_surface_discovery_audit.json`

通过标准：

- `newCandidateSurfaceCount=0`：报告当前本地证据入口耗尽，等待新 trace 或新 runtime observation；
- `newCandidateSurfaceCount=1`：回到 Phase B/C，将其编码成候选；
- `newCandidateSurfaceCount>1`：按证据优先级排序，只推进最小可验证入口。

### Phase E：open candidate 最小事实补证

触发条件：

- Phase C 输出 `openNeedsSpecificEvidenceCount>0`

规则：

- 一次只处理一个 `openNeedsSpecificEvidenceRows[0]`；
- 只补该候选缺失 predicate 对应的最小事实；
- 不补“看起来相关”的旁证；
- 不执行网络。

计划产物命名：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_<candidate_id>_minimal_fact_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/<candidate_id>_minimal_fact_audit.json`

通过标准：

- 如果补证后关闭：回 Phase C；
- 如果补证后仍 open：继续同一候选的下一最小事实；
- 如果补证后 proposal-ready：进入 Phase F。

### Phase F：proposal 写入与 promoted-transition gate

触发条件：

- exactly one `proposalReady` candidate。

写入目标：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`

验证命令：

```bash
python3 tools/lint_promoted_transition_candidate_proposals.py
python3 tools/audit_promoted_transition_candidate_proposals_lint_controls.py
python3 tools/build_promoted_transition_candidate_intake.py
python3 tools/build_candidate_executor_readiness_audit.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/build_reset_terminal_boundary_audit.py
python3 tools/verify_pure_protocol_goal_completion.py
```

通过标准：

- `promotedSingleTransitionCandidateCount=1`
- `executorReadyForPromotedCandidate=true`
- `readyForFreshExperiment=true`

### Phase G：最小 fresh 实验

触发条件：

- Phase F 通过；
- verifier 或 intake 明确 `readyForFreshExperiment=true`。

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

实验规则：

- 每一次 fresh attempt 必须换 session；
- 一个 attempt 内 transport 固定；
- 如果证据显示直链代码没有走本地代理，默认 direct；
- Webshare 只能作为同一个 promoted transition 的 transport 受控变量；
- 同一 session、同一 IP、多次尝试只允许用于同一 promoted transition 的重复性验证；
- IP/Webshare/direct 只能作为变量记录，不能在无 promoted transition 时作为根因。

必须记录：

- session id；
- transport；
- Webshare session/IP 标识；
- promoted transition id；
- request diff；
- cookie jar before/after；
- collector raw response；
- collector decoded response；
- risk/verify response；
- CreateAccount response。

通过标准：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `stageAdvanced=true`

### Phase H：end-to-end PoC 与 final replay

触发条件：

- Phase G 证明最小 promoted transition 可推进阶段。

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_final_pure_protocol_replay_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

最终通过标准：

- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`
- `replayAttemptExecuted=true`
- `completionVerified=true`
- `goalComplete=true`

## 6. 脚本接入要求

新增 Phase B/C/D/E 任何 artifact 后，必须同步接入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_pure_protocol_evidence_gate_chain.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

每次接入后必须重跑：

```bash
python3 tools/build_proof_script_reproducibility_audit.py
python3 tools/run_pure_protocol_evidence_gate_chain.py
python3 tools/build_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_evidence_manifest.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/build_reset_terminal_boundary_audit.py
python3 tools/verify_pure_protocol_goal_completion.py
```

## 7. 立即执行入口

下一步只做以下动作：

1. 修改 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_nearest_miss_promotion_candidate_audit.py`，让 32 个候选全部落盘为 `allRows`；
2. 新增 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_exhaustive_promotion_candidate_resolution_audit.py`；
3. 对 32 个候选逐项输出 `closed/open/proposalReady`；
4. 接入 proof/gate/manifest/final verifier；
5. 根据 Phase C 的分支结果决定下一步。

当前不执行：

- fresh 网络；
- direct/Webshare/IP 切换；
- 换 session 重试；
- 浏览器或 Camoufox；
- 围绕 WASM/material hook 的无目标补证。

## 8. Phase B/C 执行结果

已完成：

1. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_nearest_miss_promotion_candidate_audit.py`
   - 新增 `allRows`
   - 新增 `checks.allRowCount`
2. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_exhaustive_promotion_candidate_resolution_audit.py`
3. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/exhaustive_promotion_candidate_resolution_audit.json`
4. 已接入：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_pure_protocol_evidence_gate_chain.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

全集候选审计当前 checks：

- `candidateRowCount=32`
- `nearestMissAllRowCount=32`
- `resolvedCandidateCount=32`
- `closedByExistingControlsCount=32`
- `openNeedsSpecificEvidenceCount=0`
- `proposalReadyCandidateCount=0`
- `top10CandidateCount=10`
- `top10ResolvedCandidateCount=10`
- `nonTop10CandidateCount=22`
- `nonTop10OpenCandidateCount=0`
- `nonTop10ProposalReadyCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

验证链当前 checks：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
  - `taskCount=59`
  - `passedTaskCount=59`
  - `failedTaskCount=0`
  - `allProofScriptsReproducible=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
  - `stepCount=47`
  - `passedStepCount=47`
  - `failedStepCount=0`
  - `allStepsPassed=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`
  - `manifestFileCount=102`
  - `hashMismatchCount=0`
  - `allHashesMatch=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`
  - `inputCount=16`
  - `failedGateCount=46`
  - `completionVerified=false`
  - `goalComplete=false`
  - `readyForFreshExperiment=false`

结论：

- 当前 32 个 promotion candidate 全部被现有本地控制实验关闭；
- 没有 open candidate；
- 没有 proposal-ready candidate；
- 当前不能执行 fresh 网络、direct/Webshare/IP/session 重试；
- 下一步进入 Phase D：候选全集耗尽后的证据入口再发现。

## 9. Phase D 执行结果

已完成：

1. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_next_evidence_surface_discovery_audit.py`
2. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/next_evidence_surface_discovery_audit.json`
3. 已接入：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_pure_protocol_evidence_gate_chain.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_goal_completion.py`

Phase D surface discovery 当前 checks：

- `surfaceCount=16`
- `closedSurfaceCount=16`
- `openSurfaceCount=0`
- `newCandidateSurfaceCount=0`
- `surfaceWithNewCandidateCount=0`
- `proposalReadyCandidateCount=0`
- `openNeedsSpecificEvidenceCount=0`
- `manifestProposalWorthyUnmanifestedDirectoryCount=0`
- `convergentRecommendedNextEntranceCount=0`
- `externalProposalWorthySignalCount=0`
- `evidencePackageProposalWorthySignalCount=0`
- `ctfRegProposalWorthySignalCount=0`
- `auxiliaryProposalWorthySignalCount=0`
- `localTraceProposalWorthyNowCount=0`
- `unclassifiedTraceProposalReadyRunCount=0`
- `liveRunnerCurrentNetworkAttemptBlocked=true`
- `objectiveEndToEndPocMissing=true`
- `goalCompletionVerified=false`
- `resetNoCurrentRouteToPhase5=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

验证链当前 checks：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
  - `taskCount=60`
  - `passedTaskCount=60`
  - `failedTaskCount=0`
  - `allProofScriptsReproducible=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
  - `stepCount=48`
  - `passedStepCount=48`
  - `failedStepCount=0`
  - `allStepsPassed=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`
  - `manifestFileCount=104`
  - `hashMismatchCount=0`
  - `allHashesMatch=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`
  - `inputCount=17`
  - `failedGateCount=48`
  - `completionVerified=false`
  - `goalComplete=false`
  - `readyForFreshExperiment=false`

结论：

- 当前本地 evidence surface 未发现新的 promotion candidate 入口；
- 当前没有 open surface；
- 当前没有 new candidate surface；
- 当前仍不能执行 fresh 网络、direct/Webshare/IP/session 重试；
- 最终目标仍未完成，缺口仍是 fresh no-browser end-to-end PoC。

下一步只能走两条之一：

1. 引入新的本地证据样本后，重新跑 Phase D；
2. 若没有新证据输入，则报告当前本地证据入口耗尽，不能继续用旧证据打开网络实验。
