# 纯协议 HUMAN 成功复现：证据门控实现计划

日期：2026-06-13

## 0. 当前权威入口

后续实现以本文档为执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md`

历史文档只作为输入证据，不作为线性执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`

## 1. 最终目标不变

实现并验证一个 fresh、no-browser、pure-protocol 的完整闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP、JS 解析、加密、payload 构造、请求重放；
3. 从 Outlook signup fresh session 推进到 HUMAN collector 成功；
4. collector decoded response 出现成功事件；
5. `_px` cookie/token jar mutation 可复现；
6. `/API/Proofs/risk/verify` 返回 `state=continue`；
7. `/API/CreateAccount` 返回 `redirectUrl`；
8. 每一步都有本地证据路径、脚本和可复现命令。

完成条件只能由 fresh end-to-end pure-protocol PoC artifact 证明。离线能力、历史 accepted 包、负控闭合、计划文档本身都不能证明目标完成。

## 2. 当前硬证据状态

### 2.1 终端审计

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`

当前 checks：

- `readyForFreshExperiment=false`
- `noCurrentRouteToPhase5=true`
- `singleTransitionCandidateCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `collectorServerExpectedStatePromotedCount=0`
- `hypothesisPlanPromotedCount=0`
- `evidenceGatedPocBlockedByGate=true`
- `goalComplete=false`

含义：

- 当前没有可执行的单一 transition；
- 不能用 IP、Webshare、direct、timing、payload 拼接等理由直接跑网络；
- 只能先找能晋升为 candidate 的新证据。

### 2.2 假设覆盖审计

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_plan_coverage_audit.json`

当前 checks：

- `allHypothesesCovered=true`
- `staleHistoricalNextPointerCount=14`
- `currentPromotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `endToEndPureProtocolPocMissing=true`
- `goalComplete=false`

含义：

- 旧计划中的历史 `nextArtifact` 指针不能继续作为执行路线；
- 缺失的最小实验 artifact 是被 gate 阻止，不是遗漏；
- 不重新打开旧 H0-H5 分支，除非出现更高优先级新证据。

### 2.3 collector server expected state 边界

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_server_expected_state_boundary_audit.json`

当前 checks：

- `clientVisibleProxyFoundCount=0`
- `requestMirroredStateCount=4`
- `cookieMirroredStateCount=2`
- `riskVerifyMirroredStateCount=1`
- `unobservableServerStateCount=1`
- `serverStateBoundaryNotClientVisible=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

含义：

- request/cookie/risk/verify 可见面已被整理；
- 当前剩余边界只能描述为不可观测的 server expected state；
- 不能把该边界猜成 IP、浏览器 cookie、encoded payload 或 WASM tail。

### 2.4 端到端 PoC gate

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`

当前 checks：

- `networkAttemptExecuted=false`
- `blockedByGate=true`
- `readyForFreshExperiment=false`
- `freshNoBrowserCollectorSuccess=false`
- `freshRiskVerifyContinue=false`
- `freshCreateAccountRedirectUrl=false`
- `goalComplete=false`

含义：

- 现在已有唯一 PoC 入口；
- 它被证据门阻止，没有误跑网络；
- 后续必须把唯一 promoted transition 接入该入口，而不是另写临时重试脚本。

### 2.5 完成要求审计

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json`

当前 checks：

- `requirementCount=8`
- `blockingRequirementCount=4`
- `freshSuccessMissing=true`
- `noCurrentExperimentRoute=true`
- `allProofScriptsReproducible=true`
- `goalComplete=false`

含义：

- 已证明的子能力可复现；
- 阻塞项仍是 fresh no-browser collector HUMAN success 及其下游完整闭环；
- 当前没有合法网络实验路线。

## 3. 方法论约束

### 3.1 先证据，后实验

所有新动作必须先回答：

1. 它来自哪个本地证据文件、trace、HAR、runtime hook 或源码位置；
2. 它是否是 pre-accept；
3. 它是否 client-visible；
4. 它是否 pure-protocol constructible；
5. 它是否能进入 request、cookie、risk、verify 任一值链；
6. 它是否被现有负控直接证伪；
7. 它是否只改变一个 transition。

缺任一项，不能进入网络。

### 3.2 证据优先级

判断冲突时按以下顺序：

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage / session timeline；
6. 静态 JS；
7. 推断。

低优先级证据不能覆盖高优先级证据。没有证据时只产出审计 artifact，不写结论。

### 3.3 禁止路线

在 `readyForFreshExperiment=false` 时禁止：

1. 直接跑 fresh 网络重试；
2. 以“可能是 IP / Webshare / direct”为唯一理由实验；
3. 搬运历史 accepted body、payload、pc；
4. 随机替换 marker、uuid、tail、stack、AEAx、TBR9、Bzt；
5. 把 decoded equality 写成成功充分条件；
6. 把 success-only hook/value 写成原因；
7. 使用旧 stale `nextArtifact` 打开实验阶段；
8. 临时写绕过 gate 的网络脚本。

## 4. 实现路线

### Phase A: 建立 candidate intake gate

目的：

- 把“新证据是否足够进入实验”变成机器可审计 artifact；
- 防止再次被旧证据或猜测牵引。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promoted_transition_candidate_intake.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_intake.json`

输入：

- `reset_terminal_boundary_audit.json`
- `hypothesis_plan_coverage_audit.json`
- `collector_server_expected_state_boundary_audit.json`
- `pure_protocol_goal_gap_audit.json`
- `evidence_gated_end_to_end_pure_protocol_poc.json`
- 新发现 candidate 的证据路径列表。

必须输出 checks：

- `allInputsExist`
- `candidateCount`
- `preAcceptCandidateCount`
- `clientVisibleCandidateCount`
- `pureProtocolConstructibleCandidateCount`
- `valueChainCandidateCount`
- `negativeControlContradictedCandidateCount`
- `promotedSingleTransitionCandidateCount`
- `readyForFreshExperiment`
- `goalComplete`

晋升规则：

- 只有且仅有一个 candidate 同时满足 pre-accept、client-visible、pure-protocol constructible、value-chain-linked、not-contradicted，才能输出：
  - `promotedSingleTransitionCandidateCount=1`
  - `readyForFreshExperiment=true`
- 否则保持：
  - `promotedSingleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`

### Phase B: 接入 terminal / goal / proof audits

更新脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`

新增 terminal checks：

- `candidateIntakeAuditExists`
- `candidateIntakeCandidateCount`
- `candidateIntakePromotedCount`
- `candidateIntakeReadyForFreshExperiment`

门控决策：

- 若 candidate intake promoted count 为 0：不跑网络；
- 若 promoted count 大于 1：先归约，不跑网络；
- 若 promoted count 等于 1：进入 Phase C。

### Phase C: 最小 transition 实验

前置条件：

- `candidateIntakePromotedCount=1`
- `readyForFreshExperiment=true`
- candidate artifact 给出精确构造方式、请求字段、cookie/storage 依赖、负控引用。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/minimal_promoted_transition_experiment.json`

实验规则：

1. 每一次新尝试必须新 `session_id`；
2. Webshare attempt 必须记录 proxy session 和出口 IP；
3. direct attempt 必须记录无代理证据；
4. 每次只改 candidate 指定的一个 transition；
5. 不搬运历史 accepted packet；
6. 不使用浏览器、Camoufox、真实鼠标、视觉或外部打码；
7. 记录完整请求、响应、decoded collector、cookie timeline、risk/verify、CreateAccount。

阶段推进判定：

- `seq5 oIIoIooo|-1` 推进到 `{do:[]}`；
- `{do:[]}` 推进到 cookie/token handler；
- cookie/token handler 推进到 `oIIoIooo|0`；
- `oIIoIooo|0` 推进到 risk/verify `state=continue`；
- risk/verify `state=continue` 推进到 CreateAccount `redirectUrl`。

任一阶段无推进：

- 写明失败阶段；
- 把该 candidate 降级或关闭；
- 不继续扩大变量。

### Phase D: 接入 evidence-gated end-to-end PoC

前置条件：

- Phase C 证明阶段推进；
- minimal experiment artifact 中有 fresh success evidence；
- terminal audit 仍为 `readyForFreshExperiment=true`。

更新脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

完成产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`

完成 checks 必须全部为 true：

- `networkAttemptExecuted=true`
- `freshNoBrowserCollectorSuccess=true`
- `freshDecodedOIIoIooo0=true`
- `freshDecodedPxJarReplayed=true`
- `freshRiskVerifyContinue=true`
- `freshCreateAccountRedirectUrl=true`
- `goalComplete=true`

### Phase E: 最终复现审计

目的：

- 从干净 fresh session 复现一次完整闭环；
- 证明不是历史状态、缓存、旧 cookie、旧 accepted packet 或浏览器副作用。

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`

必须包含：

- fresh session id；
- transport 证据；
- Webshare/direct 控制变量记录；
- collector request/response；
- decoded collector response；
- `_px` jar mutation；
- risk/verify response；
- CreateAccount response；
- replay commands；
- artifact hashes；
- `goalComplete=true`。

## 5. 当前立即执行项

按顺序执行：

1. 创建 candidate intake gate 脚本和空基线 artifact；
2. 把 candidate intake 接入 terminal / goal / proof / completion audits；
3. 重新运行所有审计；
4. 若仍为 0 promoted，则停止在证据门，输出“当前无网络实验路线”；
5. 只有出现唯一 promoted transition，才写并运行最小 transition 实验；
6. 只有最小实验产生阶段推进，才接入端到端 PoC。

当前根据既有证据，预期第一轮 candidate intake 输出：

- `candidateCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

## 6. 统一 artifact schema

所有新增审计 JSON 必须包含：

```json
{
  "generatedAt": "",
  "plan": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md",
  "purpose": "",
  "inputs": {},
  "checks": {},
  "evidenceBlocks": [],
  "decision": {
    "goalComplete": false,
    "readyForFreshExperiment": false,
    "recommendedExperiment": null,
    "nextArtifact": null,
    "nextScript": null,
    "reason": ""
  }
}
```

网络实验 artifact 必须额外包含：

```json
{
  "attempt": {
    "sessionId": "",
    "freshSession": true,
    "transport": "webshare_or_direct",
    "proxyEvidence": {},
    "ipEvidence": {}
  },
  "candidate": {
    "id": "",
    "singleTransition": true,
    "preAccept": true,
    "clientVisible": true,
    "pureProtocolConstructible": true,
    "valueChain": "request_or_cookie_or_risk_or_verify"
  },
  "stage": {
    "before": "",
    "after": "",
    "advanced": false
  }
}
```

## 7. 实施命令清单

当前先执行离线审计链：

```bash
python3 -m py_compile /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promoted_transition_candidate_intake.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promoted_transition_candidate_intake.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py
```

网络命令不写入本节。只有 Phase C 前置条件满足后，才在 candidate-specific script 中生成可执行命令。

## 8. 当前执行记录

### 8.1 Phase A candidate intake gate 已实现

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promoted_transition_candidate_intake.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_intake.json`

当前 checks：

- `allInputsExist=true`
- `candidateSourceCount=7`
- `candidateCount=0`
- `preAcceptCandidateCount=1`
- `clientVisibleCandidateCount=2`
- `pureProtocolConstructibleCandidateCount=0`
- `valueChainCandidateCount=3`
- `negativeControlContradictedCandidateCount=7`
- `promotedSingleTransitionCandidateCount=0`
- `resetReadyForFreshExperiment=false`
- `resetNoCurrentRouteToPhase5=true`
- `hypothesisPlanStaleHistoricalNextPointerCount=14`
- `evidenceGatedPocBlockedByGate=true`
- `endToEndPureProtocolPocMissing=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前没有 candidate 同时满足 pre-accept、client-visible、pure-protocol constructible、value-chain-linked、not-contradicted；
- 继续禁止 fresh 网络实验；
- 后续任何新路线必须先通过该 intake gate。

### 8.2 Phase B 审计接入已完成

已更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`

terminal audit 新增 checks：

- `implementationPlanExists=true`
- `candidateIntakeAuditExists=true`
- `candidateIntakeCandidateSourceCount=7`
- `candidateIntakeCandidateCount=0`
- `candidateIntakePromotedCount=0`
- `candidateIntakePreAcceptCandidateCount=1`
- `candidateIntakeClientVisibleCandidateCount=2`
- `candidateIntakePureProtocolConstructibleCandidateCount=0`
- `candidateIntakeNegativeControlContradictedCandidateCount=7`
- `candidateIntakeReadyForFreshExperiment=false`

completion audit 新增 checks：

- `candidateIntakeExists=true`
- `candidateIntakePromotedCount=0`
- `candidateIntakeReadyForFreshExperiment=false`
- `proofTaskCount=18`

proof reproducibility 当前 checks：

- `taskCount=19`
- `passedTaskCount=19`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`
- `offlineOnly=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

goal audit 当前 summary：

- proved:
  - `trace_classifier`
  - `collector_response_decoder`
  - `collector_payload_constructor`
  - `pow_recompute`
  - `px_cookie_token_update`
  - `risk_verify_rebuild`
  - `fresh_tbr9_ws_nq`
  - `fresh_aeax_ws_ng`
- blocking:
  - `end_to_end_pure_protocol_poc`
- `goalComplete=false`

当前决策：

- `readyForFreshExperiment=false`
- `recommendedExperiment=null`
- `nextArtifact=null`
- `nextScript=null`

含义：

- 本轮只强化了“如何进入下一次实验”的证据门；
- 目标仍未完成；
- 只有新证据让 `promoted_transition_candidate_intake.json` 输出唯一 promoted transition，才进入 Phase C。

### 8.3 Phase C minimal transition experiment harness 已实现

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_minimal_promoted_transition_experiment.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/minimal_promoted_transition_experiment.json`

当前 checks：

- `gateEvaluated=true`
- `candidateIntakePromotedCount=0`
- `candidateIntakeReadyForFreshExperiment=false`
- `resetReadyForFreshExperiment=false`
- `resetNoCurrentRouteToPhase5=true`
- `completionNoCurrentExperimentRoute=true`
- `evidenceGatedPocBlockedByGate=true`
- `goalMissingEndToEndPoc=true`
- `readyForFreshExperiment=false`
- `networkAttemptExecuted=false`
- `blockedByGate=true`
- `singleTransitionExperimentExecuted=false`
- `stageAdvanced=false`
- `advancedToDoEmpty=false`
- `advancedToCookieTokenHandler=false`
- `advancedToCollectorOIIoIooo0=false`
- `advancedToRiskVerifyContinue=false`
- `advancedToCreateAccountRedirectUrl=false`
- `goalComplete=false`

已接入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

当前 proof reproducibility：

- `taskCount=19`
- `passedTaskCount=19`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`

意义：

- Phase C 已有唯一入口；
- 当前入口证明自己被 `candidate_intake` gate 阻断；
- 当前没有网络请求执行；
- 端到端 PoC harness 也已改为依赖 Phase C stage advancement；
- 后续只有当 `candidateIntakePromotedCount=1` 且 Phase C 产生 `stageAdvanced=true` 时，才能继续接入真实 end-to-end PoC executor。

### 8.4 Phase E final replay audit harness 已实现

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_final_pure_protocol_replay_audit.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/final_pure_protocol_replay_audit.json`

当前 checks：

- `gateEvaluated=true`
- `blockedByGate=true`
- `readyForFreshReplay=false`
- `replayAttemptExecuted=false`
- `networkAttemptExecuted=false`
- `freshSessionIdRecorded=false`
- `transportEvidenceRecorded=false`
- `webshareOrDirectControlRecorded=false`
- `collectorRequestResponseRecorded=false`
- `decodedCollectorResponseRecorded=false`
- `pxJarMutationRecorded=false`
- `riskVerifyResponseRecorded=false`
- `createAccountResponseRecorded=false`
- `replayCommandsRecorded=false`
- `artifactHashesRecorded=false`
- `pocNetworkAttemptExecuted=false`
- `pocFreshNoBrowserCollectorSuccess=false`
- `pocFreshDecodedOIIoIooo0=false`
- `pocFreshDecodedPxJarReplayed=false`
- `pocFreshRiskVerifyContinue=false`
- `pocFreshCreateAccountRedirectUrl=false`
- `minimalTransitionStageAdvanced=false`
- `candidateIntakePromotedCount=0`
- `resetReadyForFreshExperiment=false`
- `completionFreshSuccessMissing=true`
- `goalMissingEndToEndPoc=true`
- `goalComplete=false`

已接入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

当前 proof reproducibility：

- `taskCount=20`
- `passedTaskCount=20`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`

意义：

- Phase E 已有最终完成审计入口；
- 当前入口证明自己被 end-to-end PoC gate 阻断；
- 当前没有 replay/network 执行；
- 即使后续 PoC artifact 出现，也必须通过 final replay audit 记录 fresh session、transport、collector、decoded response、`_px` jar、risk/verify、CreateAccount、replay commands、artifact hashes 后才能把目标置为完成。

### 8.5 One-command offline evidence gate chain 已实现

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_pure_protocol_evidence_gate_chain.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_gate_chain_audit.json`

该脚本按固定顺序离线重建当前 gate 链：

1. candidate intake；
2. minimal transition experiment harness；
3. evidence-gated end-to-end PoC harness；
4. final replay audit harness；
5. completion requirements audit；
6. proof reproducibility audit；
7. reset terminal boundary audit；
8. goal gap audit；
9. completion final sync；
10. reset terminal final sync。

当前 checks：

- `stepCount=10`
- `passedStepCount=10`
- `failedStepCount=0`
- `allStepsPassed=true`
- `offlineOnly=true`
- `finalProofTaskCount=20`
- `finalProofPassedTaskCount=20`
- `finalNoCurrentRouteToPhase5=true`
- `finalReadyForFreshExperiment=false`
- `finalCompletionFreshSuccessMissing=true`
- `finalCompletionNoCurrentExperimentRoute=true`
- `finalGoalBlockingOnlyEndToEndPoc=true`
- `goalComplete=false`
- `readyForFreshExperiment=false`

已接入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

意义：

- 当前 terminal decision 可由一条离线命令重建；
- 不依赖手工执行顺序或历史上下文；
- 该 chain 证明当前所有 gate 产物自洽，但仍以 `goalComplete=false`、`readyForFreshExperiment=false` 结束；
- 后续如果引入新证据，必须先跑该 chain 验证它是否真正改变 promoted transition / PoC / final replay 状态。

### 8.6 Evidence manifest 已实现

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/verify_pure_protocol_evidence_manifest.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_evidence_manifest_verify.json`

manifest 当前覆盖：

- 当前实现计划；
- candidate intake / Phase C / PoC / final replay / completion / proof / terminal / goal / gate-chain / manifest / manifest-verify 脚本；
- candidate intake / Phase C / PoC / final replay / completion / proof / terminal / goal / gate-chain 产物。

manifest 当前 checks：

- `fileCount=21`
- `allFilesExist=true`
- `allFilesHashed=true`
- `duplicateHashCount=0`
- `gateChainAllStepsPassed=true`
- `gateChainStepCount=10`
- `resetReadyForFreshExperiment=false`
- `resetNoCurrentRouteToPhase5=true`
- `completionFreshSuccessMissing=true`
- `completionNoCurrentExperimentRoute=true`
- `goalBlockingOnlyEndToEndPoc=true`
- `goalComplete=false`
- `readyForFreshExperiment=false`

manifest verify 当前 checks：

- `manifestExists=true`
- `manifestFileCount=21`
- `verifiedFileCount=21`
- `missingFileCount=0`
- `hashMismatchCount=0`
- `allFilesExist=true`
- `allHashesMatch=true`
- `manifestGoalComplete=false`
- `goalComplete=false`
- `readyForFreshExperiment=false`

已接入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

意义：

- 当前关键脚本和终端产物都有 SHA-256；
- 当前文件已通过 manifest verify，未发现 hash drift；
- 后续任何新证据路线都可以先比较 manifest，确认结论变化来自证据而不是脚本/产物漂移；
- manifest 本身不改变目标状态：当前仍是 `goalComplete=false`、`readyForFreshExperiment=false`。

### 8.7 Candidate proposals 入口已标准化

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals.json`

用途：

- 后续任何新候选 transition 必须先写入该 proposals 文件；
- candidate intake 只接受满足以下条件的 proposal：
  - `preAccept=true`
  - `clientVisible=true`
  - `pureProtocolConstructible=true`
  - `valueChain` 属于 `request|cookie|risk|verify`
  - `evidence` 指向存在的本地证据路径
  - `negativeControlRefs` 指向存在的负控证据路径
  - `contradicted` 不是 `true`

已更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_promoted_transition_candidate_intake.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/lint_promoted_transition_candidate_proposals.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`

当前 checks：

- `proposalCount=0`
- `proposalAcceptedCount=0`
- `proposalInvalidCount=0`
- `candidateCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

proposal lint 当前 checks：

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

terminal audit 当前新增 checks：

- `candidateIntakeProposalCount=0`
- `candidateIntakeProposalAcceptedCount=0`
- `candidateIntakeProposalInvalidCount=0`
- `candidateIntakeProposalLintExists=true`
- `candidateIntakeProposalLintAllStructurallyValid=true`
- `candidateIntakeProposalLintPromotableShapeCount=0`

manifest 当前覆盖文件数：

- `fileCount=24`
- `allFilesExist=true`
- `allFilesHashed=true`
- `hashMismatchCount=0`

意义：

- 新证据入口已经有机器可校验 schema；
- 不再允许口头把 IP、timing、cookie、WASM tail 或旧 accepted body 直接升级为实验；
- 任何 proposal 都必须先通过 intake gate，随后再由 Phase C harness 决定是否允许网络。

### 8.8 Candidate proposal lint controls 已实现

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_promoted_transition_candidate_proposals_lint_controls.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/promoted_transition_candidate_proposals_lint_controls.json`

控制样本：

1. `positive_shape_control`：本地证据、负控引用、`request` valueChain、四个布尔字段齐全，应判定为 structurally valid 与 promotable shape；
2. `missing_evidence_control`：证据路径不存在，应判定 invalid；
3. `bad_value_chain_control`：`valueChain=timing`，应判定 invalid；
4. `contradicted_control`：结构有效但 `contradicted=true`，应判定 non-promotable。

当前 checks：

- `controlCount=4`
- `passedControlCount=4`
- `failedControlCount=0`
- `positiveShapeControlPassed=true`
- `missingEvidenceControlPassed=true`
- `badValueChainControlPassed=true`
- `contradictedControlPassed=true`
- `allControlsPassed=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

已接入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_pure_protocol_evidence_gate_chain.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_evidence_manifest.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`

当前 proof / chain / manifest：

- `proofScriptTaskCount=22`
- `proofScriptPassedTaskCount=22`
- `evidenceGateChainFinalProofTaskCount=22`
- `evidenceManifestFileCount=26`
- `evidenceManifestVerifyAllHashesMatch=true`

意义：

- proposals lint 不只是空文件通过；其正/负控制样本也通过；
- 可以证明 gate 会识别结构完整的候选形态，也会拒绝缺证据、非法 valueChain、已被反证的候选；
- 该控制审计不修改 live proposals，不产生 promoted transition。
