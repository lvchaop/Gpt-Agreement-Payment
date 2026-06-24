# 纯协议 HUMAN 成功复现：证据收敛执行计划

日期：2026-06-13

## 0. 文档地位

后续实现以本文档作为新的执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-convergent-plan.md`

以下文档只作为历史计划和证据背景，不作为当前线性推进入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodology-implementation-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-first-current-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-authoritative-execution-plan.md`

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

### 2.1 当前没有网络实验准入

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/current_evidence_entrance_terminal_ledger.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/candidate_source_contradiction_ledger.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/stale_positive_signal_authority_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_completion_verifier.json`

当前关键 checks：

- `activeActionableNextPointerCount=0`
- `candidateIntakePromotedCount=0`
- `promotedCandidateTotal=0`
- `activeActionablePositiveSignalCount=0`
- `readyForFreshExperiment=false`
- `completionVerified=false`
- `goalComplete=false`

结论：

- 当前不能直接做 direct/Webshare/IP/session 重试；
- 权限和网络可用不等于实验准入；
- 实验准入只由证据门产生，不由执行权限产生。

### 2.2 当前正信号已经过期或不可执行

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/stale_positive_signal_authority_audit.json`

当前关键 checks：

- `scannedJsonFileCount=1342`
- `positiveSignalCount=5`
- `activeActionablePositiveSignalCount=0`
- `supersededOrNonAuthoritativePositiveSignalCount=5`
- `staleReadyArtifactCount=2`
- `currentEvidenceActiveActionableNextPointerCount=0`
- `candidateIntakePromotedCount=0`

结论：

- 旧 `readyForFreshExperiment`、旧 proposal、旧 ready pointer 不能重新打开 fresh 实验；
- 后续任何“看起来能试”的结论，必须先通过当前 authority/gate/intake。

### 2.3 当前离线证据链稳定，但目标未完成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

当前关键 checks：

- `taskCount=54`
- `passedTaskCount=54`
- `allProofScriptsReproducible=true`
- `stepCount=42`
- `passedStepCount=42`
- `allStepsPassed=true`
- `manifestFileCount=92`
- `allHashesMatch=true`
- `blockingOrMissing=["end_to_end_pure_protocol_poc"]`
- `inputCount=11`
- `inputCount=15`
- `failedGateCount=44`
- `completionVerified=false`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- trace classifier、collector response decoder、payload constructor、POW recompute、cookie/token update、risk/verify rebuild 均已有离线证明；
- 仍缺 fresh no-browser end-to-end PoC；
- 不能把离线组件完成等同于最终完成。

### 2.4 当前新增 trace 已被归类，但没有 proposal

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/local_trace_evidence_freshness_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unclassified_trace_signal_reduction_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_chain_classification_backlog.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_chain_server_visible_diff_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_payload_pc_session_lineage_audit.json`

当前关键 checks：

- `runtimeTraceCount=172`
- `jsTraceCount=45`
- `unclassifiedRunCount=162`
- `unclassifiedHighValueSignalRunCount=79`
- `browserSuccessChainRunCount=18`
- `browserParentSuccessCookieChainRunCount=6`
- `classificationBacklogCount=24`
- `earliestServerVisibleDiffCount=10`
- `contradictedDiffCount=10`
- `fieldLineageRowCount=3`
- `fieldLineageContradictedCount=3`
- `proposalCandidateCount=0`
- `readyForFreshExperiment=false`

结论：

- browser success chain 是对照资产，不是 no-browser 成功；
- server-visible diff 存在，但当前全部被负控矛盾或落在下游 outcome；
- payload/pc/session 方向已经证明仍耦合，不能继续随机堆字段。

## 3. 当前方法论

后续不再按“看到什么补什么证据”推进，也不按“先网络多试几次”推进。

固定方法：

1. 从最终完成字段反推当前阻塞字段；
2. 从阻塞字段定义能改变状态的最小新增事实；
3. 从最小新增事实寻找本地证据入口；
4. 本地证据只能产出三类结果：
   - 关闭一个旧入口；
   - 形成一个候选；
   - 证明一个候选被负控矛盾；
5. 只有 exactly one promoted transition 时，才进入 fresh 实验；
6. fresh 实验只验证一个 transition；
7. IP、Webshare、direct、HTTP/2、session 只能作为同一 transition 的受控变量，不能单独作为根因。

证据优先级：

1. fresh live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage / session timeline；
6. 静态 JS；
7. 推断。

禁止：

- 在 `readyForFreshExperiment=false` 时跑 fresh 网络重试；
- 用 browser success trace 冒充 no-browser pure-protocol 成功；
- 用旧 ready/proposal/next pointer 打开新实验；
- 用 IP/Webshare/direct 猜测解释失败；
- 用 WASM/material/glue 复杂度默认解释失败；
- 用 decoded equality 默认推出 server accept；
- 没有候选时做“换 session、换 IP、多试几次”。

## 4. 候选晋升定义

一个候选必须同时满足：

1. `preAccept=true`：发生在 collector accept 前，不是下游 outcome；
2. `clientVisible=true`：可从本地 trace、HAR、hook、cookie、storage 或 JS 推导；
3. `pureProtocolConstructible=true`：纯 HTTP/JS/crypto 可构造，不依赖浏览器实时行为；
4. `valueChain=true`：能连接 collector response、cookie/token、risk/verify 或 CreateAccount；
5. `negativeControlNotContradicted=true`：未被失败样本、历史 probe、exact replay、payload/pc/session 控制实验矛盾；
6. `singleTransition=true`：一次 fresh 实验只改变一个 transition；
7. `artifactBacked=true`：证据路径、脚本、hash、输入输出可复现；
8. `staleAuthorityClean=true`：不依赖过期 ready/proposal/next pointer。

写入位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`

验证链：

```bash
python3 tools/lint_promoted_transition_candidate_proposals.py
python3 tools/audit_promoted_transition_candidate_proposals_lint_controls.py
python3 tools/build_promoted_transition_candidate_intake.py
```

进入 fresh 实验的唯一标准：

- `promotedSingleTransitionCandidateCount=1`
- `readyForFreshExperiment=true`

## 5. 新执行计划

### Phase A：基线锁定

目标：

- 确认当前证据链没有漂移；
- 确认没有 stale 正信号打开 fresh 实验；
- 后续每新增 artifact 后重复执行。

命令：

```bash
python3 -m py_compile \
  tools/build_proof_script_reproducibility_audit.py \
  tools/run_pure_protocol_evidence_gate_chain.py \
  tools/build_pure_protocol_evidence_manifest.py \
  tools/verify_pure_protocol_evidence_manifest.py \
  tools/build_pure_protocol_completion_requirements_audit.py \
  tools/build_reset_terminal_boundary_audit.py \
  tools/verify_pure_protocol_goal_completion.py

python3 tools/build_proof_script_reproducibility_audit.py
python3 tools/run_pure_protocol_evidence_gate_chain.py
python3 tools/build_pure_protocol_evidence_manifest.py
python3 tools/verify_pure_protocol_evidence_manifest.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/build_reset_terminal_boundary_audit.py
python3 tools/verify_pure_protocol_goal_completion.py
```

通过标准：

- `allProofScriptsReproducible=true`
- `allStepsPassed=true`
- `allHashesMatch=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

### Phase B：重新定义可影响阻塞字段的证据入口

目标：

- 不再围绕旧 payload/pc/session、transport、WASM 单点打转；
- 从 `end_to_end_pure_protocol_poc` 缺口反推还可能改变 proposal 八字段的本地证据入口；
- 只保留能改变候选晋升结果的入口。

计划产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_convergent_evidence_entrance_matrix.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/convergent_evidence_entrance_matrix.json`

输入证据：

- `current_evidence_entrance_terminal_ledger.json`
- `candidate_source_contradiction_ledger.json`
- `server_state_value_consumption_ledger.json`
- `coupled_boundary_terminal_ledger.json`
- `stale_positive_signal_authority_audit.json`
- `pure_protocol_goal_completion_verifier.json`
- `pure_protocol_goal_gap_audit.json`

必须输出字段：

- `entranceCount`
- `closedEntranceCount`
- `staleEntranceCount`
- `candidateAffectingEntranceCount`
- `uncoveredCandidateAffectingEntranceCount`
- `recommendedNextEntranceCount`
- `recommendedNextEntranceIds`
- `readyForFreshExperiment`
- `goalComplete`

通过标准：

- 如果 `recommendedNextEntranceCount=0`：当前本地证据入口全部耗尽，不能网络重试，只能报告“缺少可晋升本地入口”；
- 如果 `recommendedNextEntranceCount=1`：进入 Phase C；
- 如果 `recommendedNextEntranceCount>1`：先用证据优先级排序，不能并行推进多个根因猜测。

### Phase C：针对唯一入口做最小事实审计

目标：

- 对 Phase B 选出的唯一入口，判断它是否能改变候选八字段；
- 不补随机证据，只补“能改变晋升判断”的字段。

计划产物命名规则：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_<entrance_id>_minimal_fact_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/<entrance_id>_minimal_fact_audit.json`

必须输出字段：

- `entranceId`
- `minimalFactCount`
- `preAcceptFactCount`
- `clientVisibleFactCount`
- `pureProtocolConstructibleFactCount`
- `valueChainFactCount`
- `negativeControlContradictedFactCount`
- `singleTransitionFactCount`
- `proposalCandidateCount`
- `readyForFreshExperiment`
- `goalComplete`

通过标准：

- `proposalCandidateCount=0`：关闭该入口，回到 Phase B；
- `proposalCandidateCount=1`：进入 Phase D；
- `proposalCandidateCount>1`：继续归约，不能进入网络。

### Phase D：proposal 写入与 gate 晋升

目标：

- 把唯一候选写入 proposal schema；
- 用 lint/control/intake 证明候选是当前唯一晋升 transition。

写入目标：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`

验证命令：

```bash
python3 tools/lint_promoted_transition_candidate_proposals.py
python3 tools/audit_promoted_transition_candidate_proposals_lint_controls.py
python3 tools/build_promoted_transition_candidate_intake.py
python3 tools/build_stale_positive_signal_authority_audit.py
python3 tools/build_pure_protocol_completion_requirements_audit.py
python3 tools/build_reset_terminal_boundary_audit.py
```

通过标准：

- `promotedSingleTransitionCandidateCount=1`
- `activeActionablePositiveSignalCount=1`
- `readyForFreshExperiment=true`

### Phase E：最小 fresh 实验

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

前置条件：

- Phase D 通过；
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

### Phase F：evidence-gated end-to-end PoC

入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

前置条件：

- Phase E 成功；
- minimal transition 已证明能推进阶段。

通过标准：

- `networkAttemptExecuted=true`
- `blockedByGate=false`
- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`

### Phase G：final replay 与 completion verifier

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

## 6. 立即执行顺序

下一步不从网络重试开始，也不继续围绕旧 WASM/material hook 单点补证据。

立即执行：

1. 建 `convergent_evidence_entrance_matrix`；
2. 从当前 48 个 proof task、36 个 gate step、79 个 manifest file 中反推未耗尽入口；
3. 如果没有入口，产出“本地证据入口耗尽”结论，并停止 fresh 实验；
4. 如果只有一个入口，对它做 `<entrance_id>_minimal_fact_audit`；
5. 只有产出 exactly one proposal candidate，才写入 proposal 并跑 gate；
6. 只有 gate 证明 `readyForFreshExperiment=true`，才执行最小 fresh 实验；
7. fresh 实验成功后才进入 end-to-end PoC 和 final replay。

## 7. 当前状态摘要

当前状态：

- 离线 proof/gate/manifest 可复现；
- stale 正信号已隔离；
- browser success chain 已转成对照资产；
- server-visible diff、payload/pc/session、handler/value、downstream-without-collector、collector-material-only、低价值未分类 trace 均未产生 proposal；
- 当前没有 fresh 网络准入；
- 当前最终目标未完成。

最新 Phase B 执行结果：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_convergent_evidence_entrance_matrix.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/convergent_evidence_entrance_matrix.json`
- 当前 checks：
  - `entranceCount=7`
  - `closedEntranceCount=7`
  - `staleEntranceCount=2`
  - `candidateAffectingEntranceCount=5`
  - `uncoveredCandidateAffectingEntranceCount=0`
  - `recommendedNextEntranceCount=0`
  - `recommendedNextEntranceIds=[]`
  - `currentActiveActionableNextPointerCount=0`
  - `candidateIntakePromotedCount=0`
  - `staleActiveActionablePositiveSignalCount=0`
  - `completionVerified=false`
  - `goalGapBlockingOnlyEndToEndPoc=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=49`, `passedTaskCount=49`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=37`, `passedStepCount=37`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=82`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=82`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `convergentEvidenceEntranceMatrixRecommendedNextEntranceCount=0`
  - `reset_terminal_boundary_audit.json`: `convergentEvidenceEntranceMatrixRecommendedNextEntranceCount=0`
  - `pure_protocol_goal_completion_verifier.json`: `completionVerified=false`, `failedGateCount=22`
- 结论：
  - 当前本地证据入口没有可晋升为 Phase C 的唯一入口；
  - 不能执行 direct/Webshare/IP/session fresh 重试；
  - 最终目标仍未完成，阻塞仍是 fresh no-browser end-to-end PoC 缺失。

最新 manifest 覆盖缺口审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_manifest_coverage_gap_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/manifest_coverage_gap_audit.json`
- 当前 checks：
  - `scannedFileCount=1671`
  - `manifestFileCount=82`
  - `proofArtifactCount=50`
  - `trackedFileCount=97`
  - `unmanifestedFileCount=1618`
  - `directoryRowCount=74`
  - `highValueDirectoryCount=43`
  - `highValueUncoveredDirectoryCount=0`
  - `proposalWorthyUnmanifestedDirectoryCount=0`
  - `recursiveReplayableFreshNoBrowserSuccessCount=0`
  - `nonJsonReplayableFreshNoBrowserSuccessCount=0`
  - `phase3RawProposalWorthySignalCount=0`
  - `phase3RawTraceCrosswalkProposalWorthyCount=0`
  - `currentEvidenceActiveActionableNextPointerCount=0`
  - `convergentRecommendedNextEntranceCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=50`, `passedTaskCount=50`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=38`, `passedStepCount=38`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=84`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=84`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `manifestCoverageGapHighValueUncoveredDirectoryCount=0`
  - `reset_terminal_boundary_audit.json`: `manifestCoverageGapHighValueUncoveredDirectoryCount=0`
  - `pure_protocol_goal_completion_verifier.json`: `completionVerified=false`, `failedGateCount=22`
- 结论：
  - `output/protocol_reverse` 中存在大量未入 manifest 的 raw/probe/material 文件；
  - 但高价值目录均已由 recursive、non-json、phase3 raw、terminal entrance、convergent matrix 覆盖；
  - 当前未发现能改变候选晋升八字段的未覆盖本地证据入口。

最新 live runner gate 审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_live_runner_gate_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/live_runner_gate_audit.json`
- 当前 checks：
  - `scannedToolFileCount=302`
  - `liveRunnerCount=15`
  - `authoritativeHarnessCount=3`
  - `authoritativeHarnessBlockedCount=3`
  - `legacyControlledLiveProbeCount=1`
  - `historicalUngatedLiveRunnerNotCurrentEntrypointCount=14`
  - `proofInvokedUngatedLiveRunnerCount=0`
  - `gateChainInvokedUngatedLiveRunnerCount=0`
  - `candidateIntakePromotedCount=0`
  - `resetReadyForFreshExperiment=false`
  - `convergentRecommendedNextEntranceCount=0`
  - `manifestCoverageProposalWorthyUnmanifestedDirectoryCount=0`
  - `minimalTransitionNetworkAttemptExecuted=false`
  - `evidenceGatedPocNetworkAttemptExecuted=false`
  - `finalReplayNetworkAttemptExecuted=false`
  - `currentNetworkAttemptBlocked=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=51`, `passedTaskCount=51`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=39`, `passedStepCount=39`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=86`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=86`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `liveRunnerGateCurrentNetworkAttemptBlocked=true`
  - `reset_terminal_boundary_audit.json`: `liveRunnerGateCurrentNetworkAttemptBlocked=true`
  - `pure_protocol_goal_completion_verifier.json`: `completionVerified=false`, `failedGateCount=22`
- 结论：
  - 历史 live runner 中确实存在可手动直连的脚本，但当前 proof/gate 链没有调用这些 ungated runner；
  - 三个权威网络入口均被 promoted-transition gate 阻断，且记录为未发起网络尝试；
  - “直接网络/Webshare/换 session 多试几次”不是当前证据体系下的合法下一步，除非先产生 exactly one promoted transition candidate。

最新 objective requirement crosswalk：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_objective_requirement_crosswalk.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/objective_requirement_crosswalk.json`
- 目的：
  - 把用户原始目标逐项映射到本地证据，防止把 proof/gate 通过误判为完整目标完成；
  - final completion verifier 必须同时满足该 crosswalk，不能绕过“fresh no-browser end-to-end PoC”要求。
- 当前 checks：
  - `requirementCount=10`
  - `provenCount=7`
  - `missingCount=1`
  - `notProvenCount=1`
  - `partiallyProvenCount=1`
  - `blockingRequirementCount=3`
  - `endToEndPocMissing=true`
  - `fullNoBrowserIndependenceNotProven=true`
  - `traceabilityOnlyPartiallyProven=true`
  - `gateChainAllStepsPassed=true`
  - `manifestVerifyAllHashesMatch=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=52`, `passedTaskCount=52`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=40`, `passedStepCount=40`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=88`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=88`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `objectiveRequirementCrosswalkBlockingRequirementCount=3`
  - `reset_terminal_boundary_audit.json`: `objectiveRequirementCrosswalkBlockingRequirementCount=3`
  - `pure_protocol_goal_completion_verifier.json`: `completionVerified=false`, `failedGateCount=32`
- 结论：
  - `trace_classifier`、`collector_response_decoder`、`collector_payload_constructor`、`pow_recompute`、`px_cookie_token_update`、`risk_verify_rebuild`、`no_ungated_fresh_network_retry` 已有本地证据支撑；
  - `end_to_end_pure_protocol_poc` 仍缺失；
  - 因缺少 fresh no-browser end-to-end success artifact，完整“不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码”的闭环独立性不能证明；
  - 证据可追溯性对已证子项成立，但对缺失的端到端 fresh success 只能标为 partially proven。

最新 promotion predicate blocker crosswalk：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promotion_predicate_blocker_crosswalk.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promotion_predicate_blocker_crosswalk.json`
- 目的：
  - 把进入 fresh 实验所需的八个候选晋升谓词逐项映射到当前 blocker；
  - 明确当前不是“没有继续尝试”，而是没有任何候选同时满足八个谓词；
  - 让 `artifactBacked` 和 `staleAuthorityClean` 只证明当前负决策有效，不能被误用为成功或网络准入。
- 当前 checks：
  - `predicateCount=8`
  - `unsatisfiedPromotionPredicateCount=6`
  - `artifactBackedNegativeDecision=true`
  - `staleAuthorityCleanForNegativeDecision=true`
  - `candidateIntakePromotedCount=0`
  - `remainingBoundaryProposalReadyRowCount=0`
  - `objectiveEndToEndPocMissing=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=53`, `passedTaskCount=53`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=41`, `passedStepCount=41`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=90`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=90`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `promotionPredicateBlockerUnsatisfiedPromotionPredicateCount=6`
  - `reset_terminal_boundary_audit.json`: `promotionPredicateBlockerUnsatisfiedPromotionPredicateCount=6`
  - `pure_protocol_goal_completion_verifier.json`: `completionVerified=false`, `failedGateCount=27`
- 结论：
  - `preAccept`、`clientVisible`、`pureProtocolConstructible`、`valueChain`、`negativeControlNotContradicted`、`singleTransition` 这六类晋升谓词没有被任何 promoted candidate 同时满足；
  - `artifactBacked` 与 `staleAuthorityClean` 仅支持“当前负决策可复现且不依赖 stale ready 指针”；
  - final completion verifier 已把 promotion predicate blocker 作为独立 completion gate：`promotionPredicateUnsatisfiedCount=6`、`promotionPredicateCandidateIntakePromotedCount=0`、`promotionPredicateRemainingBoundaryProposalReadyRowCount=0`；
  - 当前不能写 proposal，不能进入最小 fresh 实验，不能执行 direct/Webshare/session 网络重试。

最新 candidate executor readiness 审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_candidate_executor_readiness_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/candidate_executor_readiness_audit.json`
- 目的：
  - 防止把“gate 将来 ready”误判为“已有可执行纯协议网络 PoC”；
  - 明确当前 generic harness 只负责 gate 记录，不包含候选专用 executor；
  - 要求后续如果出现 exactly one promoted candidate，必须先补候选专用 executor，再允许 fresh 网络实验。
- 当前 checks：
  - `allInputsExist=true`
  - `planRequiresCandidateSpecificExecutor=true`
  - `harnessDeclaresMissingCandidateSpecificExecutor=true`
  - `candidateIntakePromotedCount=0`
  - `promotionPredicateUnsatisfiedCount=6`
  - `minimalExperimentNetworkAttemptExecuted=false`
  - `evidenceGatedPocNetworkAttemptExecuted=false`
  - `finalReplayNetworkAttemptExecuted=false`
  - `liveRunnerCurrentNetworkAttemptBlocked=true`
  - `currentGateClosedNoNetworkAttempt=true`
  - `executorReadyForPromotedCandidate=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=54`, `passedTaskCount=54`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=42`, `passedStepCount=42`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=92`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=92`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `candidateExecutorCurrentGateClosedNoNetworkAttempt=true`
  - `reset_terminal_boundary_audit.json`: `candidateExecutorCurrentGateClosedNoNetworkAttempt=true`
  - `pure_protocol_goal_completion_verifier.json`: `inputCount=11`, `failedGateCount=35`, `completionVerified=false`
- 结论：
  - 当前没有网络尝试执行；
  - 当前没有 promoted candidate；
  - 当前没有候选专用 executor；
  - 即便未来 promotion gate 变为 ready，仍必须先生成并审计 candidate-specific executor，不能直接调用历史 ungated live runner。

最新 hypothesis tree current authority 审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_hypothesis_tree_current_authority_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_tree_current_authority_audit.json`
- 目的：
  - 把历史 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md` 中 H3/H4/H5 的后续路线，与当前 convergent gate 权威状态对齐；
  - 防止旧计划里“Phase 5 最小实验”文字在 `singleTransitionCandidateCount=0` 时被误用为网络准入；
  - 明确旧 H3/H4/H5 产物已经存在，但当前证据下只支持终止/负决策，不产生 fresh 实验入口。
- 当前 checks：
  - `allInputsExist=true`
  - `phaseChainPresent=true`
  - `hypothesisMatrixPrimaryNextIsH3=true`
  - `firstDivergenceAtFinalSeq5=true`
  - `requestHistoryOrderGapFalsified=true`
  - `nextStaticGapReadyForFreshExperiment=false`
  - `h3CollectorServerStateTerminalForCurrentEvidence=true`
  - `h4BrowserOnlyRuntimeTerminalForCurrentEvidence=true`
  - `h5MicrosoftContextNotCurrentEntrance=true`
  - `singleTransitionCandidateCount=0`
  - `jsReplayableClientTransitionCandidateCount=0`
  - `convergentRecommendedNextEntranceCount=0`
  - `promotionPredicateUnsatisfiedCount=6`
  - `candidateExecutorCurrentGateClosedNoNetworkAttempt=true`
  - `oldPlanNoLongerAuthorizesPhase5=true`
  - `convergentPlanIsCurrentAuthority=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=55`, `passedTaskCount=55`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=43`, `passedStepCount=43`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=94`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=94`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `hypothesisTreeH3Terminal=true`, `hypothesisTreeH4Terminal=true`
  - `reset_terminal_boundary_audit.json`: `hypothesisTreeOldPlanNoLongerAuthorizesPhase5=true`
  - `pure_protocol_goal_completion_verifier.json`: `inputCount=12`, `failedGateCount=38`, `completionVerified=false`
- 结论：
  - 历史 H3/H4/H5 不是未执行的新入口；它们在当前证据下已收敛到“没有 single transition candidate / 没有 replayable client transition / 没有 current Microsoft-context entrance”；
  - 后续即使用户要求“按照 hypothesis plan”，也必须先经过当前 convergent gate，而不能回退到旧 Phase 5 网络实验；
  - 当前仍只能继续寻找新的本地证据入口，或者证明现有入口能改变候选晋升八字段之一。

最新 nearest-miss promotion candidate 审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_nearest_miss_promotion_candidate_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/nearest_miss_promotion_candidate_audit.json`
- 目的：
  - 不再只输出“没有 promoted candidate”；
  - 对当前所有近似候选按八个晋升谓词打分；
  - 找出最接近 proposal 的候选及其最小缺口，避免继续 broad negative-control scan。
- 当前 checks：
  - `candidateRowCount=32`
  - `nearestSatisfiedPredicateCount=6`
  - `nearestMissingPredicateCount=2`
  - `proposalReadyCandidateCount=0`
  - `singleMissingPredicateCandidateCount=0`
  - `candidateWithConstructibilityProofCount=9`
  - `candidateWithNegativeControlEscapeCount=8`
  - `candidateWithSingleTransitionCount=0`
  - `promotionPredicateUnsatisfiedCount=6`
  - `executorReadyForPromotedCandidate=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 当前最近候选：
  - `pc_value`
    - 已满足：`preAccept`、`clientVisible`、`pureProtocolConstructible`、`valueChain`、`artifactBacked`、`staleAuthorityClean`
    - 仍缺：`negativeControlNotContradicted`、`singleTransition`
    - blockers：`pc alone is eliminated by existing control`、`pc participates in a coupled payload/pc/session family`
    - 证据：
      - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_axis_equivalence.json`
      - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_session_binding_candidate_audit.json`
  - `collector_cookie_header`
    - 已满足：`preAccept`、`clientVisible`、`pureProtocolConstructible`、`valueChain`、`artifactBacked`、`staleAuthorityClean`
    - 仍缺：`negativeControlNotContradicted`、`singleTransition`
    - blocker：`primary collector flow does not require Cookie header in existing controls`
    - 证据：
      - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_chain_server_visible_diff_audit.json`
  - `RB4_collector_success_to_risk_verify`
    - 已满足 6 个谓词，但缺 `preAccept` 与 `singleTransition`，属于 post-accept/downstream，不是当前 fresh collector rejection 的根因入口。
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=56`, `passedTaskCount=56`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=44`, `passedStepCount=44`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=96`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=96`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `nearestMissNearestSatisfiedPredicateCount=6`, `nearestMissNearestMissingPredicateCount=2`
  - `reset_terminal_boundary_audit.json`: `nearestMissProposalReadyCandidateCount=0`, `nearestMissCandidateWithSingleTransitionCount=0`
  - `pure_protocol_goal_completion_verifier.json`: `inputCount=13`, `failedGateCount=40`, `completionVerified=false`
- 结论：
  - 当前不是“完全没有方向”；最接近 proposal 的方向已经收敛到 `pc_value` 与 `collector_cookie_header`；
  - 但二者都被现有负控或耦合关系阻断，且都不是 single transition；
  - 下一步若继续推进，应优先围绕这两个 nearest-miss 做定向离线审计：要么证明某一个 blocker 可被新证据解除，要么把它们彻底关闭并寻找下一个 nearest-miss。

最新 nearest-miss blocker resolution 审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_nearest_miss_blocker_resolution_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/nearest_miss_blocker_resolution_audit.json`
- 目的：
  - 对上一轮最近候选 `pc_value` 与 `collector_cookie_header` 做定向 blocker 判定；
  - 不再停留在“还缺两个谓词”，而是判断这两个 blocker 是否已经由本地控制实验证明无法解除；
  - 若无法解除，关闭这两个最近候选，避免反复回到相同方向。
- 当前 checks：
  - `rowCount=2`
  - `closedByExistingControlsCount=2`
  - `needsMoreEvidenceCount=0`
  - `pcValueClosedByExistingControls=true`
  - `collectorCookieHeaderClosedByExistingControls=true`
  - `pcValueCanPromote=false`
  - `collectorCookieHeaderCanPromote=false`
  - `proposalReadyCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `pc_value` closure 证据：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_axis_equivalence.json`
    - `pcUuidSourceDeterminesPc=true`
    - `remainingEncoderAxisCount=2`
    - `singleEncoderAxisIsolated=false`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_session_binding_candidate_audit.json`
    - `pcAloneEliminated=true`
    - `exactPayloadPcNoSuccess=true`
    - `remainingDiffKeysArePayloadPcSession=true`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/clean_history_payload_pc_controls_audit.json`
    - `exactPayloadPcReturnedDoEmpty=true`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/forced_overlap_payload_pc_split_control_audit.json`
    - `seq5PayloadAndPcExactS00=true`
    - `seq5NoOIIoIooo=true`
- `collector_cookie_header` closure 证据：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_success_chain_server_visible_diff_audit.json`
    - positive presence `17/18`
    - negative presence `5/16`
    - `contradicted=true`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_cookie_bridge_candidate_audit.json`
    - `primaryCollectorCookieHeaderObservedRunCount=0`
    - `allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader=true`
    - `collectorCookieHeadersOnlyOnBeaconOrTelemetry=true`
    - `stateWindowLine933NoCookieHeader=true`
    - `cookieSessionGapLine933AndFreshNoCookieHeader=true`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=57`, `passedTaskCount=57`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=45`, `passedStepCount=45`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=98`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=98`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `nearestMissBlockerClosedByExistingControlsCount=2`
  - `reset_terminal_boundary_audit.json`: `nearestMissBlockerPcValueClosed=true`, `nearestMissBlockerCollectorCookieHeaderClosed=true`
  - `pure_protocol_goal_completion_verifier.json`: `inputCount=14`, `failedGateCount=42`, `completionVerified=false`
- 结论：
  - 最近的两个 pre-accept near-miss 候选均不能晋升；
  - `pc_value` 不能作为单变量，因为已被 pc-alone、exact payload+pc、2x2 encoder-axis 控制关闭；
  - `collector_cookie_header` 不能作为单变量，因为 primary collector flow 无 Cookie header，观察到的 Cookie header 只落在 beacon/telemetry，且该特征也出现在负控；
  - 后续应转向下一批 nearest-miss 候选或新增证据入口，而不是继续围绕 `pc_value` / `collector_cookie_header` 重复验证。

最新 remaining nearest-miss resolution 审计：

- 已生成：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_remaining_nearest_miss_resolution_audit.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_nearest_miss_resolution_audit.json`
- 目的：
  - 在关闭 `pc_value` 与 `collector_cookie_header` 后，继续审计 nearest-miss 列表剩余 8 个 6/8 候选；
  - 判断是否还存在未关闭的 proposal 近邻入口；
  - 防止后续从 top2 转移到同样已被旧控制关闭的分支。
- 当前 checks：
  - `remainingNearestRowCount=8`
  - `closedByExistingControlsCount=8`
  - `openRemainingNearestRowCount=0`
  - `proposalReadyCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- 已关闭的剩余 nearest-miss 类别：
  - `RB4_collector_success_to_risk_verify` / `C8_collector_success_to_risk_verify`
    - 关闭原因：post-accept/downstream；`riskContinueTokenFeedsCreateAccount=true`、`line933DivergenceIsAccepted=true`、`successEntryHasChallengeSuccess0=true`
  - `C1_decoded_line922_activity_fields`
    - 关闭原因：不是 observed divergence；`decodedActivityFieldsEqual=true` 且 exact payload/pc 控制存在
  - `C2_request_history_order`
    - 关闭原因：order gap 已反证；`hasOrderGap=false`
  - `C3_static_payload_pc_transplant`
    - 关闭原因：static payload/pc transplant 控制已拒绝；`staticPayloadPcControlExists=true`、`payloadPcSplitControlRejected=true`
  - `C4_outer_session_tuple`
    - 关闭原因：outer tuple 是耦合边界，不是 single transition；`hasOuterSessionTupleBoundary=true`、`outerBindingControlsRejected=true`、`finalConsumedFieldsAllDiffer=true`
  - `C5_pc_marker_uuid_encoder_binding`
    - 关闭原因：encoder family 仍是耦合族；`singleRecommendedVariant=false`、`variantFamilyNotSingle=true`
  - `C7_parent_bridge_cookie_header`
    - 关闭原因：不是 Cookie header transition；`line933NoCookieHeader=true`、`freshSeq5NoCookieHeader=true`、`decodedPayloadAlreadyEqual=true`
- 已接入并重跑验证链：
  - `proof_script_reproducibility_audit.json`: `taskCount=58`, `passedTaskCount=58`, `failedTaskCount=0`
  - `pure_protocol_evidence_gate_chain_audit.json`: `stepCount=46`, `passedStepCount=46`, `failedStepCount=0`
  - `pure_protocol_evidence_manifest.json`: `fileCount=100`, `allFilesExist=true`, `allFilesHashed=true`
  - `pure_protocol_evidence_manifest_verify.json`: `manifestFileCount=100`, `allHashesMatch=true`
  - `pure_protocol_completion_requirements_audit.json`: `remainingNearestMissOpenRowCount=0`
  - `reset_terminal_boundary_audit.json`: `remainingNearestMissClosedByExistingControlsCount=8`
  - `pure_protocol_goal_completion_verifier.json`: `inputCount=15`, `failedGateCount=44`, `completionVerified=false`
- 结论：
  - 当前 nearest-miss 前 10 个候选已经全部由本地证据关闭；
  - 继续在这些候选上做网络、payload、pc、Cookie、order、decoded activity、risk/verify 下游实验，不会提高晋升谓词；
  - 后续只能寻找新的证据入口，或扩展 nearest-miss 审计覆盖范围到非 top10 候选，但仍必须先本地证明能改变晋升八字段。

下一步唯一合法动作：

- 不做 fresh 网络重试；
- 不进入 Phase C，因为 `recommendedNextEntranceCount=0`；
- 不手动调用历史 ungated live runner；
- 若继续推进，只能先引入新的、本地可验证的证据入口，并证明它能改变候选晋升八字段之一；
- `pc_value` 与 `collector_cookie_header` 已由定向 blocker resolution 关闭；后续不再围绕这两个候选重复试验；
- nearest-miss top10 已全部关闭；下一步只能扩展候选覆盖或引入新的本地证据入口，且必须证明它能改变晋升八字段之一；
- 若证据入口成功产生 exactly one promoted candidate，下一步也不是直接网络重试，而是先实现并审计该 candidate 的专用 executor；
- 只有 `readyForFreshExperiment=true`、exactly one promoted candidate、candidate-specific executor ready 三者同时成立，才进入 direct/Webshare/session fresh 实验。
