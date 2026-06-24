# 纯协议 HUMAN 成功复现：证据门控推进计划

日期：2026-06-13

## 当前权威入口更新（2026-06-13）

本文件保留为证据门控推进阶段的历史记录。后续实现改按新的实现计划执行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-implementation-plan.md`

切换依据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `readyForFreshExperiment=false`
  - `noCurrentRouteToPhase5=true`
  - `singleTransitionCandidateCount=0`
  - `promotedSingleTransitionCandidateCount=0`
  - `evidenceGatedPocBlockedByGate=true`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_plan_coverage_audit.json`
  - `staleHistoricalNextPointerCount=14`
  - `currentPromotedSingleTransitionCandidateCount=0`
  - `endToEndPureProtocolPocMissing=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`
  - `networkAttemptExecuted=false`
  - `blockedByGate=true`
  - `goalComplete=false`

## 0. 权威入口

本节为历史入口记录。当前不再以本文档作为后续实现入口；当前入口见上方“当前权威入口更新”。

后续实现以本文档为当前执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`

历史计划只作为输入证据，不再作为线性执行入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`

## 1. 最终目标不变

最终仍要实现并验证完整纯协议闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP / JS 解析 / 加密 / 请求构造 / 请求重放；
3. 从 Outlook signup 初始状态推进到 HUMAN collector 成功事件；
4. Microsoft `/API/Proofs/risk/verify` 返回 `state=continue`；
5. `/API/CreateAccount` 返回 `redirectUrl`；
6. 每一步都有本地证据路径、脚本和可复现命令。

目标只能由 fresh end-to-end pure-protocol PoC artifact 证明。计划文档、负控闭合、离线能力证明都不能替代目标完成。

## 2. 当前证据边界

### 2.1 终端边界

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`

关键 checks：

- `singleTransitionCandidateCount=0`
- `stateMachineClientVisibleProxyCount=0`
- `runtimeJsCandidateReductionPromotedCount=0`
- `runtimeJsCandidateReductionUnclassifiedCount=0`
- `collectorHandlerPromotedCount=0`
- `collectorHandlerUnclassifiedCount=0`
- `unobservedLifecycleRecommendedNewHookCount=0`
- `routeBValueTaxonomyPromotedCount=0`
- `routeBInstrumentationPatchApplyPassiveObserver=false`
- `encoderVariantFamilyClosedNoSuccess=true`
- `browserContextAllServerVisibleProxiesReduced=true`
- `browserContextStaticAllGapsReduced=true`
- `currentRouteAuthorityPromotedCount=0`
- `recursiveEvidenceReplayableFreshSuccessCount=0`
- `nonJsonEvidenceReplayableFreshSuccessCount=0`
- `allProofScriptsReproducible=true`
- `endToEndEliminatedBoundaryCount=10`
- `endToEndRemainingBoundaryCount=3`
- `endToEndBoundaryPromotedCount=0`
- `browserCookieBridgePromotedCount=0`
- `encodedSessionPromotedCount=0`
- `endToEndPureProtocolPocMissing=true`
- `noCurrentRouteToPhase5=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

### 2.2 目标缺口

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

已证明能力：

- `trace_classifier`
- `collector_response_decoder`
- `collector_payload_constructor`
- `pow_recompute`
- `px_cookie_token_update`
- `risk_verify_rebuild`
- `fresh_tbr9_ws_nq`
- `fresh_aeax_ws_ng`

仍缺：

- `end_to_end_pure_protocol_poc`

结论：

- `goalComplete=false`

## 3. 方法论

### 3.1 不再被旧证据牵引

当前不是“多试几次”阶段。证据显示没有可执行的单一 transition：

- `singleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `noCurrentRouteToPhase5=true`

因此禁止继续围绕旧 accepted packet、payload/pc/body 拼接、IP 猜测、WASM tail、timing、HTTP2 order 或 success-only hook 做随机网络重试。

### 3.2 证据优先级

后续所有判断按以下优先级处理：

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage / session timeline；
6. 静态 JS；
7. 推断。

低优先级证据不能覆盖高优先级证据。所有结论必须引用本地证据路径和具体 check。缺少证据时先产出证据 artifact，不写结论。

### 3.3 网络实验门

fresh 网络实验只能验证一个已归约的候选。必须同时满足：

- `singleTransitionCandidateCount=1`
- `readyForFreshExperiment=true`
- candidate 是 pre-accept；
- candidate 是 client-visible；
- candidate 可由 pure protocol 构造；
- candidate 有值链进入 request / cookie / risk / verify 之一；
- 现有负控没有直接证伪它；
- 实验只改变这个 candidate；
- 每次 attempt 使用新 `session_id`；
- Webshare 记录 proxy session 和出口 IP；
- direct 记录无代理证据。

任一条件不满足，不跑网络。

## 4. 已关闭方向

以下方向已有本地证据关闭，除非出现新的更高优先级证据，否则不再作为推进路线：

1. Route A collector response handler surface：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_collector_handler_surface_audit.json`
   - 终端 check：`collectorHandlerPromotedCount=0`、`collectorHandlerUnclassifiedCount=0`
2. Route B unobserved lifecycle / hook surface：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_unobserved_lifecycle_surface_audit.json`
   - 终端 check：`unobservedLifecycleRecommendedNewHookCount=0`
3. Route B value taxonomy / instrumentation-control：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_value_taxonomy_audit.json`
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_instrumentation_control_audit.json`
   - 终端 check：`routeBInstrumentationPatchApplyPassiveObserver=false`
4. Route C transport / IP / Webshare / direct：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_transport_ip_decision_audit.json`
   - 终端 check：`transportDecisionOnlyTransportChangedStageDifferenceProved=false`
5. C5 encoder variant family：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_variant_terminal_audit.json`
   - 终端 check：`encoderVariantFamilyClosedNoSuccess=true`
6. Browser context / parent bridge / static context：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_context_to_server_state_proxy_audit.json`
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_context_static_gap_inventory.json`
   - 终端 check：`browserContextAllServerVisibleProxiesReduced=true`、`browserContextStaticAllGapsReduced=true`
7. Browser cookie bridge：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_cookie_bridge_candidate_audit.json`
   - 终端 check：`browserCookieBridgePromotedCount=0`
8. Encoded/session binding single-axis controls：
   - 证据：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_session_binding_candidate_audit.json`
   - 终端 check：`encodedSessionSingleAxisEliminatedCount=6`、`encodedSessionPromotedCount=0`

## 5. 当前剩余边界

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/end_to_end_remaining_boundary_audit.json`

关键 checks：

- `eliminatedBoundaryCount=10`
- `remainingBoundaryCount=3`
- `promotedSingleTransitionCandidateCount=0`
- `decodedSeq5Seq6ActivityEqualityRejected=true`
- `freshServerBoundTailStrongestRejected=true`
- `exactPayloadPcAndExactBodyNoSuccess=true`
- `encodedBoundaryStillCoupled=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

剩余边界：

1. `encoded_payload_pc_session_server_state_binding`
2. `browser_parent_cookie_bridge_or_hidden_browser_state`
3. `collector_server_side_expected_state`

其中前两项已有 candidate audit 未晋升：

- browser cookie bridge：`browserCookieBridgePromotedCount=0`
- encoded/session binding：`encodedSessionPromotedCount=0`

因此当前唯一值得继续整理的边界是：

- `collector_server_side_expected_state`

它不是结论，只是当前尚未被还原为 client-visible transition 的边界。

## 6. 新执行路线

### Phase 1: collector server expected state 边界审计

目的：

- 不猜测服务端内部状态；
- 系统整理已经被镜像、已经被反证、仍不可观测的 expected state；
- 判断是否存在新的 client-visible proxy。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_server_expected_state_boundary_audit.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_server_expected_state_boundary_audit.json`

输入至少包括：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/end_to_end_remaining_boundary_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_cookie_bridge_candidate_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_session_binding_candidate_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/current_route_authority_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/recursive_evidence_blindspot_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/non_json_evidence_blindspot_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`

必须输出 checks：

- `allInputsExist`
- `remainingBoundaryCount`
- `encodedSessionBoundaryPromotedCount`
- `browserCookieBridgePromotedCount`
- `collectorServerStateBoundaryExists`
- `clientVisibleProxyFoundCount`
- `requestMirroredStateCount`
- `cookieMirroredStateCount`
- `riskVerifyMirroredStateCount`
- `negativeControlCoveredStateCount`
- `unobservableServerStateCount`
- `promotedSingleTransitionCandidateCount`
- `readyForFreshExperiment`
- `goalComplete`

晋升规则：

- 只有找到 pre-accept、client-visible、pure-protocol constructible、并能进入 request/cookie/risk/verify 的 proxy，才能设置 `promotedSingleTransitionCandidateCount=1`。
- 如果只剩服务端不可观测 expected state，则输出 `server_state_boundary_not_client_visible=true`，但不得写成目标完成或失败完成。

### Phase 2: terminal audit 接入 Phase 1

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

要求：

- terminal audit 增加 Phase 1 产物输入；
- 同步输出：
  - `collectorServerExpectedStateBoundaryAuditExists`
  - `collectorServerExpectedStateClientVisibleProxyFoundCount`
  - `collectorServerExpectedStatePromotedCount`
  - `collectorServerExpectedStateReadyForFreshExperiment`

决策：

- 若 Phase 1 仍为 0 promoted，则保持：
  - `readyForFreshExperiment=false`
  - `noCurrentRouteToPhase5=true`
  - `goalComplete=false`
- 若 Phase 1 给出 1 个 promoted candidate，则进入 Phase 3。

### Phase 3: 最小 transition 实验

前置条件：

- terminal audit 给出 `singleTransitionCandidateCount=1`
- terminal audit 给出 `readyForFreshExperiment=true`
- Phase 1 candidate audit 给出具体构造方式和修改点。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_collector_server_state_minimal_transition_experiment.py`

实验规则：

1. 每次新尝试必须新 `session_id`；
2. Webshare attempt 必须记录 proxy session 和出口 IP；
3. direct attempt 必须记录无代理证据；
4. 每次实验只改 candidate 指定的一个 transition；
5. 不搬运历史 accepted packet；
6. 不临时拼接 payload/pc/body/marker/uuid/tail/stack；
7. 不使用浏览器、Camoufox、真实鼠标、视觉或外部打码。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_server_state_minimal_transition_experiment.json`

阶段推进判定：

- `seq5 oIIoIooo|-1` 到 `{do:[]}`；
- `{do:[]}` 到 cookie/token handler；
- cookie/token handler 到 `oIIoIooo|0`；
- `oIIoIooo|0` 到 risk/verify `state=continue`；
- risk/verify `state=continue` 到 CreateAccount `redirectUrl`。

### Phase 4: end-to-end pure-protocol PoC

只有 Phase 3 证明阶段推进后执行。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`

完成门：

- fresh no-browser collector success；
- decoded collector response 中出现成功事件；
- `_px` jar mutation 可复现；
- risk/verify 返回 `state=continue`；
- CreateAccount 返回 `redirectUrl`；
- 命令可从干净 fresh session 复现；
- 没有浏览器/Camoufox/真实鼠标/视觉/外部打码依赖。

只有该产物满足完成门后，`goalComplete` 才能置为 `true`。

## 7. 实施顺序

### Step 1: 产出 Phase 1 审计脚本

命令：

```bash
python3 -m py_compile /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_server_expected_state_boundary_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_server_expected_state_boundary_audit.py
```

### Step 2: 更新 terminal / goal audit

命令：

```bash
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py
```

### Step 3: 根据决策门选择分支

若 Phase 1 没有 promoted candidate：

- 不跑网络；
- 输出当前边界和缺口；
- 只接受新的证据入口，不重复旧路线。

若 Phase 1 有且只有一个 promoted candidate：

- 执行 Phase 3 最小 transition 实验；
- 每次新尝试换新 session；
- Webshare/direct 只作为控制变量记录，不作为原因预设。

若 Phase 3 有阶段推进：

- 执行 Phase 4 end-to-end PoC。

## 8. 明确禁止事项

除非 terminal audit 重新给出 `readyForFreshExperiment=true`，禁止：

1. fresh 网络重试；
2. 以“可能是 IP / Webshare / direct”作为实验理由；
3. 搬运历史 accepted body / payload / pc；
4. 随机替换 marker、uuid、PX561 tail、stack、AEAx、TBR9、Bzt；
5. 把 decoded equality 写成成功充分条件；
6. 把 success-only hook/value 写成原因；
7. 把 hsprotect patch apply 样本当 passive observer 证据；
8. 用旧 stale ready artifact 打开 Phase 5。

## 9. 新 artifact 统一格式

所有新增审计 JSON 必须包含：

```json
{
  "generatedAt": "",
  "plan": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md",
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

进入网络实验的 JSON 必须额外包含：

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

## 10. 当前执行记录

### 10.1 Phase 1 已执行

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_server_expected_state_boundary_audit.py`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_server_expected_state_boundary_audit.json`

关键 checks：

- `allInputsExist=true`
- `remainingBoundaryCount=3`
- `encodedSessionBoundaryPromotedCount=0`
- `browserCookieBridgePromotedCount=0`
- `collectorServerStateBoundaryExists=true`
- `clientVisibleProxyFoundCount=0`
- `requestMirroredStateCount=4`
- `cookieMirroredStateCount=2`
- `riskVerifyMirroredStateCount=1`
- `negativeControlCoveredStateCount=3`
- `unobservableServerStateCount=1`
- `serverStateBoundaryNotClientVisible=true`
- `proofScriptsReproducible=true`
- `endToEndPureProtocolPocMissing=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

Phase 1 结论边界：

- 已整理 request/cookie/risk 可见 surface：
  - exact payload+pc / exact body / decoded activity equality 均已镜像但仍 rejected；
  - browser parent cookie bridge 未进入 primary collector Cookie header，且也出现在 tf failure；
  - `_px` jar 到 risk/verify rebuild 已证明，但不能推出 collector success；
  - encoded/session single-axis controls 已全部 negative。
- 当前 `collector_server_side_expected_state` 只能表述为服务端 expected state 边界；
- 没有发现 pre-accept、client-visible、pure-protocol constructible proxy；
- 不打开 fresh 网络实验。

### 10.2 Terminal / goal audit 已同步

已更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`

新增 terminal checks：

- `collectorServerExpectedStateBoundaryAuditExists=true`
- `collectorServerExpectedStateClientVisibleProxyFoundCount=0`
- `collectorServerExpectedStateRequestMirroredStateCount=4`
- `collectorServerExpectedStateCookieMirroredStateCount=2`
- `collectorServerExpectedStateRiskVerifyMirroredStateCount=1`
- `collectorServerExpectedStateUnobservableServerStateCount=1`
- `collectorServerExpectedStateNotClientVisible=true`
- `collectorServerExpectedStatePromotedCount=0`
- `collectorServerExpectedStateReadyForFreshExperiment=false`

终端决策仍为：

- `resetLocalProxySearchesNegative=true`
- `noCurrentRouteToPhase5=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

总目标审计仍为：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - proved: `trace_classifier`, `collector_response_decoder`, `collector_payload_constructor`, `pow_recompute`, `_px cookie/token update`, `risk_verify_rebuild`, `fresh_tbr9_ws_nq`, `fresh_aeax_ws_ng`
  - blocking: `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

### 10.3 Hypothesis plan 覆盖审计已执行

用户目标仍引用 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`。为避免被历史 `nextArtifact` 指针误导，已新增覆盖审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_hypothesis_plan_coverage_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_plan_coverage_audit.json`

关键 checks：

- `phaseArtifactCount=21`
- `existingPhaseArtifactCount=20`
- `missingRequiredPhaseArtifactCount=0`
- `minimalExperimentArtifactMissing=true`
- `minimalExperimentMissingAllowedByGate=true`
- `authorityArtifactCount=9`
- `existingAuthorityArtifactCount=9`
- `staleHistoricalNextPointerCount=14`
- `allHypothesesCovered=true`
- `h0Closed=true`
- `h1Closed=true`
- `h2Closed=true`
- `h3RemainingNotClientVisible=true`
- `h4Closed=true`
- `h5Reduced=true`
- `currentPromotedSingleTransitionCandidateCount=0`
- `resetTerminalNoCurrentRouteToPhase5=true`
- `collectorServerExpectedStatePromotedCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`
- `endToEndPureProtocolPocMissing=true`

解释：

- hypothesis plan 的 Phase 1-4.7 静态/lineage 产物均已有覆盖；
- Phase 5 `minimal_divergence_experiment_audit.json` 缺失是 gate 允许的缺失，因为当前仍无 promoted single transition；
- 历史产物中仍存在 `nextArtifact` 指向下游已存在 artifact 的旧指针，共 14 个，不能作为重新打开网络实验的依据；
- H0/H1/H2/H4 已关闭，H5 已降为无 promoted context proxy，H3 仍是非 client-visible server-state 边界。

已同步 terminal audit：

- `hypothesisPlanCoverageAuditExists=true`
- `hypothesisPlanMissingRequiredPhaseArtifactCount=0`
- `hypothesisPlanMinimalExperimentMissingAllowedByGate=true`
- `hypothesisPlanAllHypothesesCovered=true`
- `hypothesisPlanH3RemainingNotClientVisible=true`
- `hypothesisPlanPromotedCount=0`
- `hypothesisPlanReadyForFreshExperiment=false`

### 10.4 当前下一步

当前没有 Phase 3 网络实验入口。继续推进只能接受新的证据入口，最低要求是：

1. 指向一个尚未被上述负控覆盖的 surface；
2. 能证明 pre-accept；
3. 能证明 client-visible；
4. 能证明 pure-protocol constructible；
5. 能证明值链进入 request / cookie / risk / verify；
6. 使 terminal audit 从 `readyForFreshExperiment=false` 变为 `true`。

在该证据出现前，不跑 fresh 网络，不做 IP/Webshare/direct 随机重试。

### 10.5 Goal-level audit 已同步最新决策

已更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.md`

修正内容：

- goal-level audit 现在显式接入：
  - `hypothesis_plan_coverage_audit.json`
  - `collector_server_expected_state_boundary_audit.json`
  - `reset_terminal_boundary_audit.json`
  - `current_route_authority_audit.json`
- `currentDecision` 明确：
  - `readyForFreshExperiment=false`
  - `recommendedExperiment=null`
  - `nextArtifact=null`
  - `nextScript=null`
- `nextEvidenceTargets` 已移除旧的字段/IP/timing/accepted-packet 重试建议，只保留当前证据门：
  1. 不在 `readyForFreshExperiment=false` 时跑 fresh 网络；
  2. 不跟随 stale hypothesis-plan `nextArtifact` 指针；
  3. 新路线必须先证明唯一 pre-accept、client-visible、pure-protocol constructible transition；
  4. 有 transition 后先创建 minimal experiment artifact；
  5. 完成仍要求 fresh no-browser `oIIoIooo|0`、decoded `_px` jar、risk/verify `state=continue`、CreateAccount `redirectUrl`。

总目标状态仍为：

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

### 10.6 Proof reproducibility 已覆盖最新 gate 脚本

已更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`

新增纳入复现的 gate/authority 脚本：

- `collector_server_expected_state_boundary`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_server_expected_state_boundary_audit.py`
- `hypothesis_plan_coverage`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_hypothesis_plan_coverage_audit.py`
- `reset_terminal_boundary`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`

当前 proof checks：

- `taskCount=15`
- `passedTaskCount=15`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`
- `offlineOnly=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

已同步 terminal audit：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `proofScriptTaskCount=15`
  - `proofScriptPassedTaskCount=15`
  - `proofScriptFailedTaskCount=0`
  - `allProofScriptsReproducible=true`
  - `noCurrentRouteToPhase5=true`
  - `readyForFreshExperiment=false`

解释：

- 当前决策门依赖的新增 gate 脚本已经进入离线复现审计；
- 这增强了现有证据链可复现性，但不产生 end-to-end HUMAN success；
- `end_to_end_pure_protocol_poc` 仍是唯一 blocking requirement。

### 10.7 Completion requirements audit 已同步最新 gate

已更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pure_protocol_completion_requirements_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pure_protocol_completion_requirements_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`

completion checks：

- `requirementCount=8`
- `provenCount=4`
- `missingCount=2`
- `notProvenCount=1`
- `partiallyProvenCount=1`
- `blockingRequirementCount=4`
- `freshSuccessMissing=true`
- `noCurrentExperimentRoute=true`
- `allProofScriptsReproducible=true`
- `proofTaskCount=16`
- `resetNoCurrentRouteToPhase5=true`
- `hypothesisPlanCoverageReady=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

新增/更新的完成门解释：

- `R1_fresh_pure_protocol_collector_human_success`: 仍 missing；
- `R2_fresh_collector_response_decodes_success`: 仍 missing；
- `R6_no_browser_camoufox_mouse_vision_external_captcha`: full flow 未存在，因此仍 not_proven；
- `R7_reproducible_evidence_paths_commands`: 子能力可复现，但缺 end-to-end 成功命令，因此 partially_proven；
- `R8_no_stale_or_ungated_network_experiment`: proven，证明当前网络实验 gate 由 terminal/hypothesis coverage/current authority 控制，而不是 stale `nextArtifact` 或随机重试。

terminal audit 已新增 completion checks：

- `completionRequirementsAuditExists=true`
- `completionRequirementCount=8`
- `completionBlockingRequirementCount=4`
- `completionFreshSuccessMissing=true`
- `completionNoCurrentExperimentRoute=true`
- `completionAllProofScriptsReproducible=true`
- `completionReadyForFreshExperiment=false`
- `completionGoalComplete=false`

当前完成审计结论：

- 子能力与 gate 证据链可复现；
- 端到端 fresh no-browser HUMAN success 仍不存在；
- 不能标记 goal complete；
- 仍不能跑 fresh 网络实验。

### 10.8 Evidence-gated end-to-end PoC harness 已建立

已新增唯一端到端 PoC 入口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_evidence_gated_end_to_end_pure_protocol_poc.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/evidence_gated_end_to_end_pure_protocol_poc.json`

该脚本当前不会发网络请求。它只做 gate evaluation；只有当前 terminal/hypothesis/server-state authority 同时证明存在唯一 promoted transition 时，才允许进入后续真实 PoC executor。

当前 PoC harness checks：

- `gateEvaluated=true`
- `readyForFreshExperiment=false`
- `networkAttemptExecuted=false`
- `blockedByGate=true`
- `resetReadyForFreshExperiment=false`
- `resetNoCurrentRouteToPhase5=true`
- `resetSingleTransitionCandidateCount=0`
- `hypothesisPlanPromotedCount=0`
- `collectorServerExpectedStatePromotedCount=0`
- `currentRouteAuthorityPromotedCount=0`
- `goalMissingEndToEndPoc=true`
- `freshNoBrowserCollectorSuccess=false`
- `freshDecodedOIIoIooo0=false`
- `freshDecodedPxJarReplayed=false`
- `freshRiskVerifyContinue=false`
- `freshCreateAccountRedirectUrl=false`
- `goalComplete=false`

已接入：

- `build_pure_protocol_completion_requirements_audit.py`
  - `evidenceGatedPocExists=true`
  - `evidenceGatedPocBlockedByGate=true`
  - `evidenceGatedPocNetworkAttemptExecuted=false`
  - `evidenceGatedPocFreshCollectorSuccess=false`
- `build_proof_script_reproducibility_audit.py`
  - proof task `evidence_gated_end_to_end_poc`
- `build_reset_terminal_boundary_audit.py`
  - `evidenceGatedPocExists=true`
  - `evidenceGatedPocBlockedByGate=true`
  - `evidenceGatedPocNetworkAttemptExecuted=false`
  - `evidenceGatedPocFreshCollectorSuccess=false`
  - `evidenceGatedPocFreshDecodedOIIoIooo0=false`
  - `evidenceGatedPocFreshRiskVerifyContinue=false`
  - `evidenceGatedPocFreshCreateAccountRedirectUrl=false`
  - `evidenceGatedPocReadyForFreshExperiment=false`
  - `evidenceGatedPocGoalComplete=false`

当前 proof checks：

- `taskCount=17`
- `passedTaskCount=17`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`

意义：

- 现在端到端 PoC 有了唯一受控入口；
- 当前 artifact 明确证明它被 gate 阻止，而不是未实现、误跑或随机网络失败；
- 后续若出现唯一 promoted transition，只需要把该 transition-specific executor 接到此 harness，而不是另开临时网络脚本。
