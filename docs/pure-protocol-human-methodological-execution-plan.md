# 纯协议 HUMAN 成功复现：方法论驱动执行计划

日期：2026-06-13

## 当前权威入口更新（2026-06-13）

本文件保留为方法论阶段的历史证据和执行记录。后续实现改按新的证据门控推进计划执行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-evidence-gated-forward-plan.md`

切换依据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `singleTransitionCandidateCount=0`
  - `endToEndRemainingBoundaryCount=3`
  - `browserCookieBridgePromotedCount=0`
  - `encodedSessionPromotedCount=0`
  - `endToEndPureProtocolPocMissing=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - remaining blocking requirement: `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

## 0. 权威入口

本节是历史入口记录。当前不再以本文档作为后续线性执行入口；当前入口见上方“当前权威入口更新”。

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`

本文档曾替代旧 reset 计划线性推进，但现在只保留为历史证据。旧计划和旧审计只作为输入证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-hypothesis-plan.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

## 1. 最终目标不变

最终仍要实现并验证完整纯协议闭环：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 只使用 HTTP / JS 解析 / 加密 / 请求重放；
3. 从 Outlook signup 初始状态推进到 HUMAN collector 成功事件；
4. Microsoft `/API/Proofs/risk/verify` 返回 `state=continue`；
5. `/API/CreateAccount` 返回 `redirectUrl`；
6. 每一步都有本地证据路径、脚本和可复现命令。

本文档完成不代表目标完成。目标只能由 end-to-end pure-protocol PoC artifact 证明。

## 2. 当前硬证据边界

### 2.1 终端边界审计

证据文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`

关键 checks：

- `resetSamplingComplete=true`
- `pureProtocolResetSamplingComplete=true`
- `allResetCoverageComplete=true`
- `browserResetCoverageComplete=true`
- `pureProtocolResetCoverageComplete=true`
- `stateMachineClientVisibleProxyCount=0`
- `singleTransitionCandidateCount=0`
- `hookAxisRecommendedAxisCount=0`
- `hookAxisMissingObservedHookCount=0`
- `hookAxisMissingContrastHookCount=0`
- `hookAxisNotInstrumentedHookCount=0`
- `successOnlyHookFeatureCandidateCount=3`
- `promotedSingleTransitionCandidateCount=0`
- `allHookAxesClosed=true`
- `runtimeJsTaxonomyCandidateCount=194`
- `runtimeJsTaxonomyStrongContrastCandidateCount=62`
- `runtimeJsCandidateReductionPromotedCount=0`
- `runtimeJsCandidateReductionUnclassifiedCount=0`
- `runtimeJsAllCandidatesReduced=true`
- `oneCollectorSuccessSampleCount=3`
- `oneCollectorFailureSampleCount=0`
- `oneCollectorAfterAcceptedChainCount=3`
- `oneCollectorNotPromoted=true`
- `allFinalResponsesSameClass=true`
- `allFinalResponsesAreSeq5Minus1=true`
- `anySeq5Success0=false`
- `decodedFailureStillMutatesPx3Pxde=true`
- `decodedFailureHasNoSuccess0=true`
- `endToEndPureProtocolPocMissing=true`
- `resetLocalProxySearchesNegative=true`
- `noCurrentRouteToPhase5=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

当前 remaining gap：

- `collector_server_internal_or_unobserved_expected_state_after_reset`
- status: `not_reduced_to_replayable_client_transition`
- missing: 一个具体的、client-visible、pre-accept、pure-protocol constructible transition，能在 fresh no-browser session 中把 collector 推到 `oIIoIooo|0`。

### 2.2 总目标审计

证据文件：

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

## 3. 为什么必须换执行方法

当前不是“缺多试几次”，而是“没有可执行的单 transition”。

已闭合或已反证的方向：

1. 已完成 reset browser / pure-protocol 最小覆盖；
2. Webshare 与 direct pure-protocol 样本都没有 collector success；
3. `worker/wasm/pow_worker` success-only 相关性没有晋升为 single transition；
4. runtime/JS taxonomy 的 194 个候选全部归约，未产生 promoted transition；
5. OneCollector telemetry 发生在 accepted downstream chain 后，不是 HUMAN collector pre-accept transition；
6. pure-protocol final response 仍是同类 `seq5 oIIoIooo|-1`；
7. decoded `_px3/_pxde` mutation 不足以产生 `success0` 或 risk/verify success；
8. 当前 terminal audit 明确 `noCurrentRouteToPhase5=true`。

因此，后续禁止继续被旧证据链牵引去做随机网络重试、字段拼接、payload 搬运或“补负控”。新的执行方法必须先产出能改变决策的证据入口。

## 4. 方法论

### 4.1 证据规则

1. 禁止猜测；缺证据先找证据。
2. 每个结论必须落到本地证据路径和具体 check。
3. 假设必须可证伪。
4. 低优先级证据不能覆盖高优先级证据。
5. 网络实验只能验证一个已归约的 transition，不能用于随机探索。
6. 每一次 fresh attempt 必须使用新 `session_id`。
7. Webshare / direct / IP 只能作为受控变量，不得直接写成原因。

### 4.2 证据优先级

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage timeline；
6. 静态 JS；
7. 推断。

### 4.3 决策门

任何网络 fresh experiment 必须同时满足：

- `singleTransitionCandidateCount=1`
- `readyForFreshExperiment=true`
- candidate 是 pre-accept；
- candidate 是 client-visible；
- candidate 可由 pure protocol 构造；
- candidate 能进入 request / cookie / risk 之一；
- 已有负控没有直接反证它；
- 实验只修改这个 candidate。

否则不跑网络。

## 5. 重新组织假设树

### H1: collector success 依赖服务端内部或未观测 expected state

当前状态：最高优先级缺口，但不是结论。

支持证据：

- `stateMachineClientVisibleProxyCount=0`
- `singleTransitionCandidateCount=0`
- `resetLocalProxySearchesNegative=true`
- `noCurrentRouteToPhase5=true`

可证伪条件：

- 找到一个 pre-accept、client-visible、pure-protocol constructible transition，并能在 fresh session 中推进 collector response class。

下一步：

- 不直接跑网络；
- 先扩大或重切 observability surface，证明是否有未观测边。

### H2: runtime/JS response handler 中存在未被归约的 decisive transition

当前状态：需要做细分审计。

支持证据：

- `runtimeJsTaxonomyCandidateCount=194`
- `runtimeJsTaxonomyStrongContrastCandidateCount=62`
- `collector_response_handler=152` 是当前最大归约类别。

限制证据：

- `runtimeJsCandidateReductionPromotedCount=0`
- `runtimeJsCandidateReductionUnclassifiedCount=0`
- `runtimeJsAllCandidatesReduced=true`

可证伪条件：

- dedicated handler audit 证明这些 handler 只是 response-side cookie/config/score/state 分发，无法形成 pre-accept pure-protocol transition。

晋升条件：

- 只有当某个 handler value 的来源能追到 request/cookie/risk 输入，且 pure-protocol 可构造，才晋升为 single transition candidate。

### H3: IP / Webshare session 是必要边界条件

当前状态：可能变量，非主因结论。

已有证据边界：

- Webshare pure-protocol 和 direct pure-protocol 当前都没有 success；
- final responses 同类，`anySeq5Success0=false`。

可证伪/提升条件：

- 在同一协议状态、同一 candidate、仅 transport/IP/session 变量变化时，collector stage 稳定变化。

执行规则：

- 没有 single transition candidate 时，不以 IP 为理由继续 fresh 网络重试；
- 若后续进入网络实验，Webshare attempt 必须记录 proxy session 和出口 IP，direct attempt 必须记录无代理证据。

### H4: 浏览器 success 里仍有未 hook 的 lifecycle 边

当前状态：只允许由新证据重新打开。

当前限制证据：

- `hookAxisMissingObservedHookCount=0`
- `hookAxisMissingContrastHookCount=0`
- `hookAxisNotInstrumentedHookCount=0`
- `allHookAxesClosed=true`

重新打开条件：

- 静态 JS 或 runtime 证据指出一个现有 hook 没覆盖的具体 API / bridge / worker / storage / iframe lifecycle 边。

禁止：

- 不能只因为“可能漏 hook”就重新采样。

## 6. 新执行路线

后续按四条路线推进，但同一时刻只能推进一条。每条路线必须产出 JSON audit，并由 terminal audit 汇总。

### Route A: collector response handler surface 细分归约

目的：

- 把 `collector_response_handler=152` 从大类拆成可审计 surface；
- 判断是否存在可晋升 single transition 的 handler。

输入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_runtime_js_event_taxonomy.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_runtime_js_candidate_reduction.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_cookie_mutation_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_final_response_class_audit.json`

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_collector_handler_surface_audit.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_collector_handler_surface_audit.json`

必须输出 checks：

- `handlerCandidateCount`
- `distinctHandlerKeyCount`
- `pxCookieHandlerSurfaceCount`
- `powChallengeHandlerSurfaceCount`
- `configFlagHandlerSurfaceCount`
- `scoreOrStateHandlerSurfaceCount`
- `unclassifiedHandlerSurfaceCount`
- `promotedSingleTransitionCandidateCount`
- `readyForFreshExperiment`
- `goalComplete`

晋升规则：

- 仅 response-side cookie mutation 不晋升；
- 仅 config / score / telemetry / event bus 不晋升；
- 仅 success-correlated 不晋升；
- 必须证明进入 pre-accept request/cookie/risk 且 pure-protocol 可构造，才晋升。

### Route B: 未观测 lifecycle 边枚举

目的：

- 不猜漏点，系统枚举当前 hook 已覆盖和未覆盖的边。

输入：

- browser success/failure runtime trace；
- JS internal trace；
- active JS assets；
- hook 代码 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_unobserved_lifecycle_surface_audit.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_unobserved_lifecycle_surface_audit.json`

必须输出：

- observed surface list；
- known hook coverage；
- static JS API references；
- uncovered but reachable API list；
- each uncovered API 是否 pre-accept；
- each uncovered API 是否可能进入 request/cookie/risk；
- `recommendedNewHookCount`；
- `readyForResampling`。

决策：

- `recommendedNewHookCount=0`：Route B 关闭；
- `recommendedNewHookCount>0`：先实现 hook，再重开采样矩阵；
- 未实现 hook 前不跑 fresh pure-protocol 实验。

### Route C: transport/IP 受控变量审计

目的：

- 回答“有没有可能是 IP / Webshare / direct”，但只用受控证据回答。

输入：

- reset sampling matrix；
- proxy auth audit；
- transport audit；
- final response class audit。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_transport_ip_decision_audit.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_transport_ip_decision_audit.json`

必须输出：

- Webshare sample count；
- direct sample count；
- per-attempt session id；
- proxy session evidence；
- exit IP evidence；
- final collector class；
- risk/verify/CreateAccount result；
- 是否存在“仅 transport 变化导致 stage 变化”。

决策：

- 若无 stage 差异：不允许以 IP 为原因继续网络重试；
- 若有 stage 差异：只把 transport 作为 Phase 5 的控制变量，不把它当作单独 success mechanism。

### Route D: terminal boundary 更新

目的：

- 每完成一条路线，都更新当前边界，避免旧证据继续误导执行。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

必须维持：

- 没有 end-to-end PoC 前，`goalComplete=false`；
- 没有 single transition 前，`readyForFreshExperiment=false`；
- 没有阶段推进前，不写成“IP/handler/worker/wasm 是原因”。

## 7. 实施顺序

### Step 1: 固定本文档为入口

操作：

- 创建本文档；
- 更新旧计划顶部入口，指向本文档。

完成证据：

- 本文档存在；
- 旧计划显示“后续按 methodological plan 执行”。

### Step 2: 先做 Route A

理由：

- 当前最大未细分 surface 是 `collector_response_handler=152`；
- 它来自真实 JS runtime trace；
- 它比继续网络重试更接近可观测 transition。

执行：

```bash
python3 -m py_compile /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_collector_handler_surface_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_collector_handler_surface_audit.py
```

然后更新：

```bash
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_runtime_js_candidate_reduction.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py
```

决策：

- 若 `promotedSingleTransitionCandidateCount=0`：Route A 关闭，进入 Route B；
- 若 `promotedSingleTransitionCandidateCount=1` 且 `readyForFreshExperiment=true`：进入 Step 6；
- 若多个候选：先离线归约，不跑网络。

### Step 3: Route B 枚举未观测 lifecycle

执行：

```bash
python3 -m py_compile /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_unobserved_lifecycle_surface_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_unobserved_lifecycle_surface_audit.py
```

决策：

- `recommendedNewHookCount=0`：进入 Step 4；
- `recommendedNewHookCount>0`：先补 hook，再更新采样 manifest，之后才允许重采样。

### Step 4: Route C 回答 IP / Webshare / direct

执行：

```bash
python3 -m py_compile /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_transport_ip_decision_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_transport_ip_decision_audit.py
```

决策：

- 无 stage 差异：IP 降级为普通控制变量；
- 有 stage 差异：把 transport 加入 Phase 5 实验约束，但仍需 single transition candidate。

### Step 5: 更新 terminal / goal audit

执行：

```bash
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py
python3 /Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py
```

决策：

- 若仍无 candidate：停止网络实验，输出当前不可推进边界；
- 若出现 candidate：进入 Step 6。

### Step 6: single transition 最小实验

前置条件：

- `singleTransitionCandidateCount=1`
- `readyForFreshExperiment=true`
- candidate audit 给出具体可构造输入、修改点和预期阶段推进。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_minimal_transition_experiment.py`

规则：

1. 每次新尝试换新 `session_id`；
2. Webshare 记录 proxy session 和出口 IP；
3. direct 记录无代理证据；
4. 只改 candidate 指定的一个 transition；
5. 不临时拼字段；
6. 不使用浏览器、Camoufox、真实鼠标、视觉、外部打码。

阶段推进标准：

- `oIIoIooo|-1` -> `{do:[]}`；
- `{do:[]}` -> cookie/token handler；
- cookie/token handler -> `oIIoIooo|0`；
- `oIIoIooo|0` -> risk/verify `state=continue`；
- risk/verify `state=continue` -> CreateAccount `redirectUrl`。

### Step 7: 完整 PoC

只有 Step 6 有阶段推进后执行。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_end_to_end_pure_protocol_poc.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_end_to_end_pure_protocol_poc.json`

完成门：

- fresh pure-protocol collector success；
- decoded success response；
- `_px` jar mutation；
- risk/verify `state=continue`；
- CreateAccount `redirectUrl`；
- 全流程命令可复现；
- 不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码。

## 8. 明确禁止事项

除非新的 artifact 改变决策，禁止：

1. 在 `singleTransitionCandidateCount=0` 时跑 fresh Phase 5；
2. 因为“可能是 IP”继续多试几次；
3. 搬运历史 accepted packet；
4. 随机替换 payload / pc / body / marker / uuid / tail / stack / AEAx / TBR9 / Bzt；
5. 把 decoded equality 当作成功充分条件；
6. 把 success-only correlation 当作 cause；
7. 在没有 proxy/IP/session 证据时讨论 transport 结论；
8. 没有新增 hook 证据时重复采样。

## 9. 新 artifact 统一格式

所有新审计 JSON 必须包含：

```json
{
  "generatedAt": "",
  "plan": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md",
  "inputs": [],
  "checks": {},
  "evidence": {},
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

进入网络实验的 artifact 必须额外包含：

```json
{
  "attempt": {
    "sessionId": "",
    "transport": "webshare_or_direct",
    "proxyEvidence": {},
    "ipEvidence": {},
    "freshSession": true
  },
  "candidate": {
    "id": "",
    "singleTransition": true,
    "preAccept": true,
    "clientVisible": true,
    "pureProtocolConstructible": true
  },
  "stage": {
    "before": "",
    "after": "",
    "advanced": false
  }
}
```

## 10. 当前下一步

### 10.1 Route A 已执行

Route A 已按本文档执行，产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_collector_handler_surface_audit.json`

关键 checks：

- `handlerCandidateCount=152`
- `distinctHandlerKeyCount=17`
- `collectorHandlerTableSurfaceCount=1`
- `pxCookieHandlerSurfaceCount=66`
- `powChallengeHandlerSurfaceCount=8`
- `configFlagHandlerSurfaceCount=6`
- `scoreOrStateHandlerSurfaceCount=71`
- `unclassifiedHandlerSurfaceCount=0`
- `handlerArgParseErrorCount=0`
- `promotedSingleTransitionCandidateCount=0`
- `negativeControlsAllHold=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

分类结果：

- `px_cookie_handler=66`
- `collector_config_flag_handler=6`
- `pow_challenge_handler=8`
- `encoded_response_state_handler=8`
- `score_or_response_state_handler=63`
- `collector_handler_table=1`

结论边界：

- `collector_response_handler=152` 已不再是未细分大类；
- cookie-mutating subgroup 已由 `reset_cookie_mutation_audit.json` 负控覆盖，仍无 `oIIoIooo|0` / risk success；
- POW subgroup 已由 `pow_recompute` 和 hook-feature reducer 覆盖；
- config / score / encoded response state / table subgroup 都没有证明 pre-accept、client-visible、pure-protocol constructible transition；
- 因此 Route A 不打开 Phase 5。

终端审计已同步更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `collectorHandlerAuditExists=true`
  - `collectorHandlerCandidateCount=152`
  - `collectorHandlerDistinctKeyCount=17`
  - `collectorHandlerPromotedCount=0`
  - `collectorHandlerUnclassifiedCount=0`
  - `collectorHandlerNegativeControlsAllHold=true`
  - `collectorHandlerNotPromoted=true`
  - `noCurrentRouteToPhase5=true`
  - `readyForFreshExperiment=false`

总目标审计仍显示：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - blocking remains `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

### 10.2 Route B 已执行

Route B 已按本文档执行，产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_unobserved_lifecycle_surface_audit.json`

关键 checks：

- `staticInputFileCount=4`
- `countedJsTraceCount=4`
- `observedRuntimeKindCount=62`
- `surfaceCount=11`
- `staticReachableSurfaceCount=11`
- `runtimeObservedSurfaceCount=7`
- `staticReachableButRuntimeUnobservedCount=4`
- `recommendedNewHookCount=3`
- `readyForResampling=false`
- `readyForFreshExperiment=false`
- `goalComplete=false`

Route B 首轮推荐的新 hook 入口：

1. `native_mobile_bridge_pxMobileData`
   - 静态证据：`webkit.messageHandlers.pxMobileData.postMessage`
   - 边界：当前 trace 没有调用证据；这是 native bridge surface，不是已证明 transition。
2. `offline_audio_fingerprint`
   - 静态证据：`new OfflineAudioContext || webkitOfflineAudioContext` 和 `startRendering`
   - 边界：这是 fingerprint material，可进入 collector activities，但当前 hook 没记录值。
3. `service_worker_cache_fingerprint`
   - 静态证据：`serviceWorker` / `caches` token surface
   - 边界：当前只证明 token/static reference，未证明 active use，低置信度。

已实现最小观测 hook：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`
  - `webkit.messageHandlers.pxMobileData.postMessage`
  - `OfflineAudioContext` / `webkitOfflineAudioContext` constructor
  - `OfflineAudioContext.startRendering` and resolved fingerprint summary
  - `navigator.serviceWorker.register` and snapshot
  - `caches.open/match/has/keys/delete`

实现后 Route B 审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_unobserved_lifecycle_surface_audit.json`
  - `implementedRouteBRecommendedHookCount=3`
  - `recommendedNewHookCount=0`
  - `readyForResampling=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

终端审计已同步：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `unobservedLifecycleAuditExists=true`
  - `unobservedLifecycleRecommendedNewHookCount=0`
  - `unobservedLifecycleReadyForResampling=true`
  - `unobservedLifecycleReadyForFreshExperiment=false`
  - `noCurrentRouteToPhase5=true`

结论边界：

- Route B 找到了并已实现新的证据采集入口；
- 没有找到 Phase 5 candidate；
- 不能据此跑 fresh pure-protocol 网络实验；
- 现在只允许更新 manifest 并重采补 hook 后的 browser 对照样本。

### 10.3 当前下一步

Route B 重采样 manifest 已生成：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_resampling_manifest.json`
  - `routeBImplementedHookCount=3`
  - `routeBRecommendedNewHookCount=0`
  - `routeBReadyForResampling=true`
  - `manifestComplete=true`
  - `readyForRouteBControlledBrowserResampling=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

终端审计同步：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `routeBResamplingManifestExists=true`
  - `routeBControlledBrowserResamplingReady=true`
  - `readyForFreshExperiment=false`
  - `noCurrentRouteToPhase5=true`

下一步是 Route B browser evidence resampling，而不是 Phase 5 网络实验：

- next artifact: `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_resampling_matrix.json`
- next script: `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_route_b_browser_resampling.py`

重采样约束：

- 只采 browser evidence，对最终 pure-protocol success 不计数；
- 每次 attempt 必须新 session；
- Webshare 必须记录 session 和出口 IP；
- 必须打开：
  - `OUTLOOK_JS_INTERNAL_TRACE=1`
  - `OUTLOOK_HSPROTECT_JS_PATCH=1`
  - `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`
- 采样结果只用于判断 Route B hooks 是否活跃、是否 success/failure 对照差异、是否进入 request/cookie/risk；
- 不能直接作为 Phase 5 pure-protocol 实验依据。

只有 terminal audit 重新给出 `readyForFreshExperiment=true` 时，才允许网络实验。

### 10.4 Route B 重采样与对照审计已执行

Route B browser evidence resampling 已执行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_resampling_matrix.json`
  - `executedRowCount=4`
  - `routeBResamplingComplete=true`
  - `readyForLifecycleContrastAudit=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

真实计入 Route B 对照的样本：

- failure:
  - session `ibtvqcnm-JP-1781299344341`
  - JS trace `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sco6dgfxbeec_1781299354.jsonl`
  - observed Route B hooks: `OfflineAudioContext.wrap`, `serviceWorker.snapshot`, `caches.wrap`
- success:
  - session `ibtvqcnm-JP-1781299717614`
  - JS trace `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_jp2u2goou0a9_1781299723.jsonl`
  - observed Route B hooks: `OfflineAudioContext.wrap`, `serviceWorker.snapshot`, `caches.wrap`

Route B lifecycle contrast audit：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_lifecycle_contrast_audit.json`
  - `realAttemptCount=2`
  - `successSampleCount=1`
  - `failureSampleCount=1`
  - `successObservedKindCount=3`
  - `failureObservedKindCount=3`
  - `bothObservedKindCount=3`
  - `successOnlyHookKindCount=0`
  - `failureOnlyHookKindCount=0`
  - `neitherObservedHookKindCount=8`
  - `promotedSingleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

对照结论边界：

- `OfflineAudioContext.wrap`、`serviceWorker.snapshot`、`caches.wrap` 在 success/failure 两侧都出现；
- `OfflineAudioContext.new/startRendering/resolved`、`caches.open/match`、`serviceWorker.register`、`pxMobileData.wrap/postMessage` 两侧都未观察到；
- 没有 success-only Route B hook；
- 没有任何 Route B hook 晋升为 pre-accept、client-visible、pure-protocol constructible transition；
- Route B 关闭，不打开 Phase 5。

当前 terminal boundary：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `routeBLifecycleContrastAuditExists=true`
  - `routeBLifecycleContrastRealAttemptCount=2`
  - `routeBLifecycleContrastSuccessOnlyHookKindCount=0`
  - `routeBLifecycleContrastPromotedCount=0`
  - `noCurrentRouteToPhase5=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

下一步按本文档路线进入 Route C：

- 产出 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_transport_ip_decision_audit.py`
- 目标是以当前 reset + Route B 证据回答 IP/Webshare/direct 是否存在受控变量阶段差异；
- 若仍无 stage 差异，则 IP 降级为普通控制变量，继续禁止 Phase 5。

### 10.5 Route C 已执行

Route C transport/IP decision audit 已执行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_transport_ip_decision_audit.json`
  - `validPureProtocolSampleCount=5`
  - `validWebshareSampleCount=3`
  - `validDirectSampleCount=2`
  - `allValidSamplesReachedFinalSeq5Seq6=true`
  - `webshareAnyCollectorSuccess=false`
  - `directAnyCollectorSuccess=false`
  - `transportIpAloneSupported=false`
  - `allFinalResponsesSameClass=true`
  - `allFinalResponsesAreSeq5Minus1=true`
  - `anySeq5Success0=false`
  - `routeBPromotedCount=0`
  - `routeBSuccessOnlyHookKindCount=0`
  - `onlyTransportChangedStageDifferenceProved=false`
  - `ipOrTransportPromotedToControlVariableOnly=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

Route C 结论边界：

- 当前 Webshare pure-protocol 与 direct pure-protocol 都能到 final seq5/seq6；
- 两组都没有 collector success；
- final response class 相同，均为 `seq5 oIIoIooo|-1`；
- Route B 没有提供新的 success-only hook；
- 因此没有证据支持“IP/Webshare/direct 本身就是成功原因”；
- IP/Webshare/direct 后续只作为 logging/control variable，不作为独立 Phase 5 axis。

终端审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `transportDecisionOnlyTransportChangedStageDifferenceProved=false`
  - `transportDecisionPromotedToControlVariableOnly=true`
  - `resetLocalProxySearchesNegative=true`
  - `noCurrentRouteToPhase5=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

当前三条路线状态：

- Route A handler surface：关闭，0 promoted；
- Route B unobserved lifecycle：补 hook + 对照后关闭，0 promoted；
- Route C transport/IP：关闭，0 promoted；
- 当前仍无 Phase 5 入口。

下一步只能进入 Route D terminal boundary 整理：

- 固化当前 terminal audit；
- 明确最终缺口仍是 `end_to_end_pure_protocol_poc`；
- 若后续继续推进，必须提出新的证据入口，而不是重复网络重试。

### 10.6 Route D 已执行

Route D terminal boundary 已固化：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/methodological_terminal_boundary_audit.json`
  - `routeACollectorHandlerClosed=true`
  - `routeBUnobservedLifecycleClosed=true`
  - `routeCTransportIpClosed=true`
  - `allRoutesClosed=true`
  - `resetTerminalNoCurrentRouteToPhase5=true`
  - `resetTerminalReadyForFreshExperiment=false`
  - `goalAuditEndToEndPocMissing=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

剩余缺口：

- `end_to_end_pure_protocol_poc`
- 当前原因：Routes A/B/C 没有产出 single client-visible, pre-accept, pure-protocol constructible transition。

重新打开 Phase 5 的最低证据门：

1. 新 artifact 证明一个 pre-accept client-visible transition；
2. 该 transition 有值链进入 request/cookie/risk；
3. 该 transition 可在无浏览器/Camoufox/鼠标/视觉/外部打码条件下构造；
4. 现有 `seq5 oIIoIooo|-1` 负控没有直接证伪它；
5. terminal audit 重新给出 `readyForFreshExperiment=true`。

在这些证据出现前，禁止继续重复网络重试或把 IP/handler/hook 相关性当作原因。

### 10.7 下一证据入口重评估已执行

已生成：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/next_evidence_entrance_audit.json`
  - `inventoryCandidateSourceCount=3`
  - `crossSampleCandidateClientVisibleProxyCount=0`
  - `historicalNoBrowserSuccess0=false`
  - `jsReplayableClientTransitionCandidateCount=0`
  - `actionableFrontierMissingArtifactCount=0`
  - `finalGapAllLocalProxySearchesNegative=true`
  - `methodologicalAllRoutesClosed=true`
  - `resetTerminalNoCurrentRouteToPhase5=true`
  - `allKnownLocalEvidenceEntrancesClosed=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

结论边界：

- 旧 `server_internal_gap_evidence_inventory.json` 中 3 个候选入口均已有产物并已关闭：
  - cross-sample server state proxy matrix：0 client-visible proxy；
  - historical probe response class matrix：0 no-browser `oIIoIooo|0`；
  - JS internal candidate reduction：0 replayable client transition；
- reset 方法论 A/B/C/D 也已关闭；
- 当前没有可执行 nextArtifact / nextScript；
- 继续推进必须先引入真正的新证据 artifact，不能重复旧链路或网络重试。


### 10.8 Route B value taxonomy 与 instrumentation-control 纠偏

在用户指出可能被旧证据牵引后，已重新检查 Route B 新 trace 的事件和值，而不是只看 hook kind 是否出现。

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_route_b_value_taxonomy_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_value_taxonomy_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_route_b_instrumentation_control_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_instrumentation_control_audit.json`

value taxonomy 事实：

- `realAttemptCount=3`
- `successSampleCount=2`
- `failureSampleCount=1`
- `successOnlyHsprotectKindCount=50`
- `successOnlyLineageKindCount=5`
- `routeBHookKindsBothObserved=[OfflineAudioContext.wrap,caches.wrap,serviceWorker.snapshot]`
- `routeBHookValueComparedKindCount=3`
- `routeBHookSuccessOnlyValueKindCount=0`
- `routeBHookFailureOnlyValueKindCount=0`
- `hsprotectValueContrastControlled=false`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`

instrumentation-control 事实：

- 旧 failure 样本：session `ibtvqcnm-JP-1781299344341`，stage `browser_execution_failed`，`successLike=false`，`OUTLOOK_HSPROTECT_JS_PATCH_APPLY=0`
- 旧 success 样本：session `ibtvqcnm-JP-1781299717614`，stage `browser_runtime_success_redirect`，`successLike=true`，`OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`
- 新补第一条 failure-class 受控样本：session `ibtvqcnm-JP-1781301161238`，stage `browser_runtime_success_redirect`，`successLike=true`，`OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`
- 新补第二条 failure-class 受控样本：session `ibtvqcnm-JP-1781301588024`，stage `browser_runtime_success_redirect`，`successLike=true`，`OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_route_b_instrumentation_control_audit.json`
  - `patchApply0AttemptCount=1`
  - `patchApply1AttemptCount=3`
  - `patchApply1SuccessCount=3`
  - `patchApply1FailureCount=0`
  - `classOutcomeMismatchCount=2`
  - `hasControlledPatchApply1SuccessAndFailurePair=false`
  - `oldFailurePatchApply0Only=true`
  - `valueContrastControlled=false`
  - `patchApplyCanBeTreatedAsPassiveObserver=false`
  - `promotedSingleTransitionCandidateCount=0`

纠偏结论：

- 不能把 success-only `hsprotect.*` 事件直接解释为 HUMAN 成功机制；
- 因为 success/failure trace 的 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY` 不一致，且两次 fresh `failure-class + patch_apply=1` 都变成 success-like；
- 因此 applied hsprotect JS patch 是 active browser-source instrumentation，不能当作 passive observer；
- 该轴可以说明旧 Route B value 对照被 instrumentation 变量污染，但不能产出 pure-protocol transition；
- 当前仍不能进入 Phase 5。

最新 terminal audit：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `routeBValueTaxonomyPromotedCount=0`
  - `routeBValueTaxonomyHsprotectValueContrastControlled=false`
  - `routeBInstrumentationPatchApply1SuccessCount=3`
  - `routeBInstrumentationPatchApply1FailureCount=0`
  - `routeBInstrumentationValueContrastControlled=false`
  - `routeBInstrumentationPatchApplyPassiveObserver=false`
  - `noCurrentRouteToPhase5=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

后续计划规则更新：

1. 不再用 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1` 的浏览器成功样本证明纯协议可复现；
2. 不再把 success-only hook/value 当作原因，除非有同 instrumentation 条件的失败对照；
3. 若继续研究该轴，必须先证明 patch 只增加观测、不改变执行；当前证据相反，所以该轴不能进入 Phase 5；
4. 下一步只能寻找新的 artifact：一个无浏览器可构造、pre-accept、client-visible、值链进入 request/cookie/risk 的 transition。


### 10.9 C5 encoder variant family 收敛与唯一 live probe

本轮回到 hypothesis plan 的 H3/C5 分支，不重复泛化网络试错。目标是把 `payload/pc/session/server-state coupling` 中剩余的 C5 encoder family 拆到单一候选，再只执行一个受控 fresh-session 实验。

新增离线审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_encoder_variant_control_coverage.json`
  - `builtVariantCount=4`
  - `liveControlEliminatedCount=2`
  - `openVariantCount=2`
  - `openVariantsSharePayload=true`
  - `openVariantsOnlyDifferByPc=true`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_encoder_pc_coherence_audit.json`
  - `openVariantCount=2`
  - `coherentPayloadPcPairCount=1`
  - `incoherentPayloadPcPairCount=1`
  - `singleCoherentVariant=true`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coherent_encoder_variant_vs_prior_controls_audit.json`
  - `hasSingleCoherentCandidate=true`
  - `candidatePayloadUuidSourceTemplate=true`
  - `candidateMarkerSourceFresh=true`
  - `candidatePcUuidSourcePayload=true`
  - `candidateDecodedBaseEqualsS00=true`
  - `candidatePayloadNotEqualS00=true`
  - `candidatePcEqualsS00=true`
  - `candidateNotCoveredByPriorControls=true`
  - `singleTransitionCandidateCount=1`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coherent_encoder_variant_experiment_manifest.json`
  - `manifestComplete=true`
  - `readyForOneControlledFreshExperiment=true`
  - `readyForGenericPhase5=false`

唯一授权实验：

- id: `coherent_encoder_variant_template_uuid_fresh_marker_template_pc`
- 参数：
  - `payloadUuidSource=template`
  - `markerSource=fresh`
  - `pcUuidSource=payload`
  - `formOuterSource=fresh`
  - `payloadSource=built`
  - `pcSource=computed`
  - `pc=5793951654710718`
- 固定条件：fresh Webshare session、forced first-failure response order、seq4 后 POW、seq5/seq6 h2 single-session delivery、无浏览器/Camoufox/鼠标/视觉/外部打码。

执行产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/coherent_encoder_variant_live_probe_audit.json`
  - `executed=true`
  - `freshWebshareSession=true`
  - `forcedFirstFailureResponseOrder=true`
  - `seq4AfterOverlapPow=true`
  - `seq5Http200=true`
  - `seq6Http200=true`
  - `seq5HasSuccess0=false`
  - `seq6HasSuccess0=false`
  - `anyCollectorSuccess=false`
  - `seq5ReturnedDoEmpty=true`
  - `goalComplete=false`
- attempt:
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781302300000_1781302300.json`
- final combo:
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/seq5_seq6_combo_probe/seq5_seq6_combo_probe_aff3ef1c-66ab-11f1-a7a0-62666cc2b93d_1781302315.json`

C5 terminal 审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_variant_terminal_audit.json`
  - `encoderVariantFamilyClosedNoSuccess=true`
  - `promotedSingleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

结论：

- C5 remaining encoder family 在当前证据下已关闭；
- 唯一 coherent variant 返回 `{do:[]}`，没有 collector HUMAN success；
- 因没有 `_px3/_pxde` success handler，不进入 risk/verify 或 CreateAccount 重放；
- 目标仍未完成，blocking 仍是 `end_to_end_pure_protocol_poc`；
- 后续不能重复 C5 payload/pc/marker/uuid 组合，除非有新 artifact 证明新的 pre-accept client-visible transition。

### 10.10 C6/H4 浏览器 context -> server-state proxy 审计

C5 关闭后，下一步不是继续换 IP 或重跑 payload，而是检查浏览器父页面、iframe postMessage、Microsoft context 是否有尚未映射到 line922/line933 的 server-visible proxy。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_browser_context_to_server_state_proxy_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_context_to_server_state_proxy_audit.json`

输入证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_s00ld1lglrw0_1781191381.jsonl`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_variant_terminal_audit.json`

关键 checks：

- `preAcceptMessageCount=33`
- `hasPreAcceptBlockMessage=true`
- `blockUuidRepresentedInCollectorForm=true`
- `blockVidRepresentedInCollectorForm=true`
- `blockRequestUrlRiskVerify=true`
- `hasPreAcceptSetToWindowConfig=true`
- `hasPreAcceptCookieBridge=true`
- `cookieBridgePx3RepresentedInPayload=true`
- `cookieBridgeNotCookieHeader=true`
- `decodedPayloadAlreadyEqual=true`
- `line922FreshChangedFieldInstances=0`
- `line922UnresolvedChangedCandidateCount=0`
- `hasPreAcceptCrclduMessage=true`
- `crclduStringFoundInCollectorRequest=false`
- `succeededMessageAfterAcceptedLine=true`
- `microsoftMessagesOnlyPostAccept=true`
- `encoderVariantFamilyClosedNoSuccess=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`
- `blockValuesAlreadyRepresentedInRequest=true`
- `allBrowserContextServerVisibleProxiesReduced=true`

证据解释：

1. line178 的 `block` message 是 pre-accept，但其中 `uuid`/`vid` 已出现在 line933 collector form；
2. `requestUrl=/api/v1.0/risk/verify` 说明 iframe 获得了 Microsoft 风险上下文，但不是新增 collector request 字段；
3. `_px3` bridge 已证明进入 line921/922 payload，但 decoded payload equality 与 C5 encoder family 控制仍拒绝；
4. accepted s00 line933 与 fresh no-browser seq5 都没有 Cookie header，所以 parent cookie bridge 不是简单 Cookie-header 缺口；
5. `crcldu` pre-accept message 没找到进入 line933 request 的字符串代理；
6. `succeeded` 和 Microsoft login/live messages 在 collector accepted 之后，只能作为 downstream evidence。

结论：

- 当前 browser context/postMessage/Microsoft context 没有晋升新的 server-visible single transition；
- 仍不能进入网络 Phase 5；
- 下一步若继续推进，只能做静态 gap inventory：找“当前 request/payload/cookie 证据从未覆盖的 context API”，而不是重跑已关闭的 C5 或 transport 变量。

### 10.11 Browser context static gap inventory 收敛

承接 10.10，本轮继续找证据，不跑网络。目标是验证：静态 JS 中的 browser context / lifecycle / PX561 producer 是否还有“未进入当前 request/payload/cookie 证据”的可晋升单 transition。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_browser_context_static_gap_inventory.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_context_static_gap_inventory.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_post_static_context_terminal_gap_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/post_static_context_terminal_gap_audit.json`

输入证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_context_to_server_state_proxy_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_unobserved_lifecycle_surface_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_static_field_map/px561_static_field_map_success_only.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_variant_terminal_audit.json`

`browser_context_static_gap_inventory.json` 关键 checks：

- `contextProxyAllServerVisibleProxiesReduced=true`
- `lifecycleRecommendedNewHookCount=0`
- `lifecycleStaticReachableButRuntimeUnobservedCount=4`
- `hookedButUnobservedSurfaceCount=3`
- `line922FreshChangedFieldInstances=0`
- `line922UnresolvedChangedCandidateCount=0`
- `staticProducerIdentifiedCount=8`
- `staticProducerLine922FreshEqualCount=8`
- `staticProducerPromotedCount=0`
- `encoderVariantFamilyClosedNoSuccess=true`
- `terminalNoCurrentRouteToPhase5=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`
- `allStaticContextGapsReduced=true`

`post_static_context_terminal_gap_audit.json` 关键 checks：

- `contextProxyReduced=true`
- `staticContextReduced=true`
- `c5ClosedNoSuccess=true`
- `serverInternalAllLocalProxySearchesNegative=true`
- `resetTerminalNoCurrentRouteToPhase5=true`
- `endToEndPureProtocolPocMissing=true`
- `closedBranchCount=4`
- `allClosedBranchesClosed=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

证据解释：

1. 静态 JS 中确有 PX561 context/static producers，例如：
   - `HCgmIllIKxE=`: `ki() returns localStorage _pxhvd-derived value`
   - `dWFPKzMCRx4=`: `navigator.languages.length`
   - `HUlnQ1slY3A=` / `DXl3M0sUeQY=` / `FUFvS1MiYXs=` / `VQEvCxNgIjA=`: `Xt()` resource/style signals
2. 但这些 identified producers 对应的 line922 字段在 fresh seq5 已与 s00 相等，所以不是新的可变 transition。
3. Route B lifecycle 静态可达但运行时未观测的 surface 已有 hook，且 `recommendedNewHookCount=0`；它们不能作为 active pre-accept success transition。
4. C5 encoder family 已经 live probe 关闭，无 success。

结论：

- Browser context 静态入口已收敛；
- 当前仍无 `singleTransitionCandidate`；
- 当前仍不能进入 fresh 网络实验；
- 剩余缺口继续是 `collector_server_internal_or_unobserved_expected_state_after_context_inventory`，状态为 `not_reduced_to_replayable_client_transition`。

### 10.12 当前 route authority 审计

扫描所有本地 `nextArtifact` 后，未发现缺失 artifact：

- `nextArtifact refs=132`
- `nonnull=90`
- `missing=0`

同时发现两个旧 artifact 仍携带历史 ready/single-transition 信号：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coherent_encoder_variant_vs_prior_controls_audit.json`
  - 旧信号：`singleTransitionCandidateCount=1`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coherent_encoder_variant_experiment_manifest.json`
  - 旧信号：`readyForOneControlledFreshExperiment=true`

这两个信号已被后续 live probe 和 terminal audit 覆盖，因此新增 authority 审计防止后续误用旧 artifact：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_current_route_authority_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/current_route_authority_audit.json`

关键 checks：

- `oldCoherentCandidateHadSingleTransition=true`
- `oldManifestHadReadySignal=true`
- `liveProbeExecuted=true`
- `liveProbeAnyCollectorSuccess=false`
- `liveProbeClosedNoSuccess=true`
- `encoderVariantFamilyClosedNoSuccess=true`
- `postStaticContextAllClosedBranchesClosed=true`
- `resetTerminalNoCurrentRouteToPhase5=true`
- `goalStillMissingEndToEndPoc=true`
- `staleReadyArtifactCount=2`
- `currentPromotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

结论：

- 当前 authority 以 terminal audit / live probe / goal audit 为准；
- 旧 coherent encoder ready 信号是已执行前置状态，不再授权网络实验；
- 当前仍没有可执行 single transition；
- 若没有新证据入口，不能继续靠 IP、Webshare session、payload/pc 组合或随机网络重试推进。

### 10.13 未挖掘本地证据入口刷新与误报修正

本轮重新扫描 `output/protocol_reverse` 后，本地目录数量已变化：

- top-level protocol_reverse dirs: `54`
- protocol_reverse artifact files: `1546`

先直接重跑旧 unmined 审计，发现一个新缺口：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/unmined_local_evidence_source_audit.json`
  - `directoryCount=54`
  - `coveredDirectoryCount=13`
  - `uncoveredDirectoryCount=41`
  - `highValueUnminedDirectoryCount=34`
  - `unminedSuccessSignalFileCount=23`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/high_value_unmined_evidence_triage.json`
  - `classifiedSuccessSignalFileCount=23`
  - `unclassifiedSuccessSignalCount=9`

继续追证据后，9 个 unclassified success signal 全部来自 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan` 下的派生/门控文件：

- `next_evidence_entrance_audit.json`
- `reset_browser_sampling_runner_plan.json`
- `reset_collector_handler_surface_audit.json`
- `reset_cookie_mutation_audit.json`
- `reset_sampling_manifest.json`
- `reset_sampling_matrix.json`
- `reset_single_transition_candidates.json`
- `reset_state_machine.json`
- `reset_terminal_boundary_audit.json`

这些文件中的 `oIIoIooo|0` / `redirectUrl` / `state=continue` 是 success criteria、browser success sample 或 terminal authority 引用，不是独立 fresh no-browser success 证据。脚本漏把 `reset_plan` 标为 covered，导致误报。

修正：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_unmined_local_evidence_source_audit.py`
  - `COVERED_DIRS` 增加 `reset_plan`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_high_value_unmined_evidence_triage.py`
  - 增加 `reset_terminal_or_manifest_reference` 分类

修正后重跑：

- `unmined_local_evidence_source_audit.json`
  - `directoryCount=54`
  - `coveredDirectoryCount=14`
  - `uncoveredDirectoryCount=40`
  - `highValueUnminedDirectoryCount=34`
  - `unminedSuccessSignalFileCount=14`
- `high_value_unmined_evidence_triage.json`
  - `classifiedSuccessSignalFileCount=14`
  - `replayableFreshNoBrowserSuccessEvidenceCount=0`
  - `unclassifiedSuccessSignalCount=0`
  - `hasReplayableFreshNoBrowserSuccessEvidence=false`

随后刷新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_internal_unobserved_state_final_gap.json`
  - `highValueUnminedReplayableSuccessNotFound=true`
  - `allLocalProxySearchesNegative=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `legacyUnminedCoveredDirectoryCount=14`
  - `legacyUnminedSuccessSignalFileCount=14`
  - `legacyHighValueUnminedUnclassifiedSuccessSignalCount=0`
  - `legacyHighValueUnminedReplayableSuccessNotFound=true`

结论：

- 新增/变化的本地证据入口已重新扫描；
- `reset_plan` success token 是已覆盖 terminal evidence，不是新入口；
- 未挖掘高价值目录中仍没有 replayable fresh no-browser `oIIoIooo|0`；
- 当前仍不能进入 fresh network experiment。

### 10.14 递归证据盲区审计

10.13 的 unmined 审计按 top-level 目录和目录内 `*.json` 扫描。当前 `output/protocol_reverse` 存在嵌套 attempts / extracted responses / dryruns，因此继续补递归盲区审计，避免漏掉 top-level 扫描之外的 fresh/no-browser success 证据。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_recursive_evidence_blindspot_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/recursive_evidence_blindspot_audit.json`

递归扫描范围：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/**/*.json`
- 仅统计嵌套 JSON，即 relative parts >= 3 的文件。

关键 checks：

- `recursiveJsonFileCount=70`
- `categoryCount=4`
- `recursiveSuccessSignalFileCount=18`
- `recursiveNegativeSignalFileCount=51`
- `browserSamplingSuccessReferenceCount=18`
- `extractedSeq5Seq6ResponseCount=35`
- `extractedSeq5Seq6SuccessSignalCount=0`
- `unclassifiedRecursiveSuccessSignalCount=0`
- `replayableFreshNoBrowserSuccessEvidenceCount=0`
- `hasReplayableFreshNoBrowserSuccessEvidence=false`
- `readyForFreshExperiment=false`
- `goalComplete=false`

证据解释：

1. 嵌套 success token 全部来自 browser sampling attempt 引用，已由 reset sampling matrix / terminal authority 覆盖；
2. 35 个 `seq5_seq6_combo_probe/extracted/*.json` 纯协议 extracted response 中没有 success handler；
3. `remaining_encoder_variant_dryruns` 是 offline material，不是 sent/live success；
4. 没有未分类 success signal。

结论：

- top-level unmined 审计之外的嵌套 JSON 也未发现 replayable fresh no-browser success；
- 递归证据盲区关闭；
- 当前仍无 fresh network experiment 入口。

### 10.15 非 JSON / 日志证据盲区审计

10.14 只覆盖嵌套 JSON。当前本地证据还包含大量 `.log`、`.txt`、`.md`、`.html`、`.jsonl`、`.har`、`.patch` 文本文件，因此补充非 JSON 盲区审计，避免成功信号只存在于运行日志、HAR 文本、markdown audit 或 evidence package 中。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_non_json_evidence_blindspot_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/non_json_evidence_blindspot_audit.json`

扫描范围：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/evidence_packages`

关键 checks：

- `scanRootCount=4`
- `scannedTextFileCount=7813`
- `skippedFileCount=1`
- `categoryCount=5`
- `successSignalFileCount=74`
- `browserReferenceSuccessSignalCount=65`
- `documentationOrManifestSuccessSignalCount=4`
- `pureProtocolSuccessSignalFileCount=1`
- `unclassifiedSuccessSignalCount=0`
- `replayableFreshNoBrowserSuccessEvidenceCount=0`
- `hasReplayableFreshNoBrowserSuccessEvidence=false`
- `readyForFreshExperiment=false`
- `goalComplete=false`

证据解释：

1. 65 个 success signal 属于 browser/runtime/browser sampling 证据或其打包副本；
2. 4 个 success signal 属于 goal/cookie audit 这类派生说明，不是 live no-browser replay；
3. 唯一 pure-protocol 相关 success token 文件是 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_constructor/px561_experimental_live_probe_audit.md`，同文件同时包含 `oIIoIooo|-1`，结论是负向/未成功，不是 replayable success；
4. 没有未分类 success signal。

结论：

- JSON 之外的日志、markdown、HTML、HAR-like text、txt、jsonl、patch 也未发现 replayable fresh no-browser `oIIoIooo|0`；
- 当前仍不能把 IP/Webshare/session/direct 当成主变量直接重试；
- fresh network experiment 仍必须等到 single pre-accept client-visible pure-protocol transition candidate 出现。

### 10.16 关键 proof script 可复现性审计

为避免“已有证明只依赖旧输出文件”的偏差，本轮新增关键 offline proof/audit 脚本可复现性审计。该审计不跑 fresh network，只重跑当前目标审计依赖的离线证明链，并验证输出 artifact 的关键 checks 仍成立。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_proof_script_reproducibility_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/proof_script_reproducibility_audit.json`

覆盖任务：

1. trace classifier v2；
2. collector decoder coverage；
3. collector request exact body coverage；
4. POW -> PX561 OSk；
5. POW solver -> PX561 tail inputs；
6. decoded collector cookie handler -> `_px` jar -> risk/verify；
7. risk/verify + CreateAccount request rebuild；
8. WASM NQ replay；
9. WASM Ng runtime random replay artifact verification；
10. recursive JSON evidence blindspot；
11. non-JSON evidence blindspot；
12. goal gap audit。

关键 checks：

- `taskCount=12`
- `passedTaskCount=12`
- `failedTaskCount=0`
- `allProofScriptsReproducible=true`
- `offlineOnly=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

审计修正说明：

- 初跑发现 trace classifier 当前样本数已从旧的 13 增加到 14，审计改为验证最低覆盖和 stage 分布，而不是固定旧样本数；
- WASM NQ replay 的权威成功 checks 是 `pxUuidNqOnlyMatchesAnyTrace` / `pxUuidNgThenNqMatchesAnyTrace` / `pxUuidReplayMatchesAnyTrace`，不是不存在的旧 `allRuntimeNqMatched`；
- fresh AEAx / Ws.Ng 的权威证明 artifact 是 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/wasm/wasm_ng_runtime_random_replay_audit_gwyi06rpe015_1781208840.json`，旧 `wasm_ng_random_gap_audit.json` 只是历史 gap audit。

结论：

- 当前关键离线证明链在当前 worktree 可重跑或可由权威 artifact 验证；
- 这增强了已有 classifier/decoder/payload/POW/cookie/risk/WASM/盲区审计证据强度；
- 但它没有产生 end-to-end pure-protocol HUMAN success PoC，也不授权 fresh network experiment。

### 10.17 端到端剩余边界结构化审计

为避免继续被端到端缺口的长叙述牵引，本轮把最新控制证据折叠为结构化 remaining-boundary audit：哪些边界已被强负控排除，哪些仍剩余，哪些能晋升为 single transition。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_end_to_end_remaining_boundary_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/end_to_end_remaining_boundary_audit.json`

关键 checks：

- `eliminatedBoundaryCount=10`
- `remainingBoundaryCount=3`
- `promotedSingleTransitionCandidateCount=0`
- `decodedSeq5Seq6ActivityEqualityRejected=true`
- `freshServerBoundTailStrongestRejected=true`
- `exactPayloadPcAndExactBodyNoSuccess=true`
- `encodedBoundaryStillCoupled=true`
- `cookieBridgeNotCookieHeader=true`
- `sendBeaconPostSuccess=true`
- `crclduNoNetworkTransitionObserved=true`
- `proofScriptsReproducible=true`
- `endToEndPureProtocolPocMissing=true`
- `readyForFreshExperiment=false`
- `goalComplete=false`

已折叠为“不充分/已排除”的边界：

1. fresh POW/WASM tail correctness 单独不充分；
2. fresh POW/WASM tail + inner uuid 不充分；
3. inner/outer uuid binding 单独不充分；
4. stack freshness 单独不充分；
5. decoded seq5/seq6 activity equality + h2 timing 不充分；
6. first-failure history + captcha HEAD delay 不充分；
7. iframe/main/captcha/stk/ns asset lineage preload 不充分；
8. exact payload+pc 或 exact whole body replay 不充分；
9. sendBeacon 是 post-success effect，不支持 pre-success 必要条件；
10. crcldu 目前只观察到 window message，没有 runtime request/response 网络副作用。

剩余边界：

1. `encoded_payload_pc_session_server_state_binding`
   - 证据显示 decoded content、body length、payload length 已等同或受控，但 encoded payload、pc、session params/server state 仍耦合；
   - exact payload+pc 和 exact whole body 控制均无 success，因此不能晋升单点 payload/pc candidate。
2. `browser_parent_cookie_bridge_or_hidden_browser_state`
   - s00 有 parent cookie bridge；fresh no-browser 没有；
   - 但 s00 line933 与 fresh seq5 collector request 都无 Cookie header，所以这不是简单缺 Cookie header；
   - 当前只能作为 observability boundary，不能当原因。
3. `collector_server_side_expected_state`
   - decoded activities 全等仍 rejected，exact body replay 仍 rejected；
   - 这是 server-state 边界，不是 client-visible constructible transition。

结论：

- 当前没有晋升 single transition candidate；
- fresh network experiment gate 仍关闭；
- 下一步如果继续推进，必须从某个剩余边界追出具体 request/cookie/risk 字段或 state mutation，否则继续网络重试只会重复已排除变量。

### 10.18 browser parent cookie bridge 候选晋升审计

10.17 剩余边界之一是 `browser_parent_cookie_bridge_or_hidden_browser_state`。本轮追它是否能落到具体 collector request / cookie / risk 字段，若不能则降级为不可晋升 observability boundary。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_browser_cookie_bridge_candidate_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/browser_cookie_bridge_candidate_audit.json`

关键 checks：

- `timelineFileCount=11`
- `fullSuccessDecodedTimelineCount=2`
- `tfFailureTimelineCount=2`
- `allFullSuccessHaveCorrectedSuccessCorrelation=true`
- `cookieBridgeCorrelationAlsoPresentInTfFailures=true`
- `tfFailuresWithCookieBridgeNoParentSuccessCount=2`
- `parentChallengeSuccessCanExistWithoutDecodedSuccess0=true`
- `collectorCookieHeaderObservedRunCount=8`
- `primaryCollectorCookieHeaderObservedRunCount=0`
- `allKnownPrimaryCollectorFlowRequestsHaveNoCookieHeader=true`
- `collectorCookieHeadersOnlyOnBeaconOrTelemetry=true`
- `legacyTimelineSuccessCorrelationBugFound=true`
- `stateWindowLine933NoCookieHeader=true`
- `cookieSessionGapLine933AndFreshNoCookieHeader=true`
- `pxCookieJarRiskVerifyRebuildStillProved=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

证据解释：

1. parent cookie bridge 不是 success 充分条件：在 `hcxwyrtiudbg_1780949301`、`whsnxy8ag5ji_1781017142` 这类 `tf_payload_failure_stage` 样本里也存在 decoded cookie bridge correlation，但没有 parent `challenge_success`；
2. parent `challenge_success` 也不是 decoded collector success 的可靠同义词：存在 parent success 但当前没有 decoded `oIIoIooo|0` 的样本；
3. 主 collector flow 的 `/api/v2/msft` 与 `/assets/js/bundle` 请求没有 Cookie header；观察到的 Cookie header 只在 beacon/telemetry 请求中；
4. 协议侧 `_px` jar 已能由 decoded collector handlers 重放并匹配 risk/verify，所以 parent cookie bridge 目前没有提供新的 request/cookie/risk 字段。

修正说明：

- 旧 timeline correlation 对 `challenge_success` 的匹配过宽，会把 decoded `oIIoIooo|-1` 和 parent `succeeded` 误配；本审计新增 corrected success correlation，只把 decoded `oIIoIooo|0` 视为 collector success。

结论：

- browser parent cookie bridge 当前不能晋升 single transition candidate；
- 它仍可作为 browser-state observability boundary 保留，但不能作为 fresh network experiment 的单变量依据；
- 若要重新打开，必须证明它导致一个新的 pre-accept request/cookie/risk 字段或 collector state mutation。

### 10.19 encoded payload / pc / session binding 候选晋升审计

10.17 剩余边界之一是 `encoded_payload_pc_session_server_state_binding`。本轮把该耦合边界拆成可审计单轴，判断是否存在能晋升 fresh experiment 的单 transition。

新增审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_encoded_session_binding_candidate_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_session_binding_candidate_audit.json`

关键 checks：

- `singleAxisRowCount=6`
- `singleAxisEliminatedCount=6`
- `exactPayloadPcNoSuccess=true`
- `exactBodyNoSuccess=true`
- `pcAloneEliminated=true`
- `markerChoiceEliminated=true`
- `templateOuterFreshPayloadPcNoSuccess=true`
- `forcedOverlapExactPayloadPcNoSuccess=true`
- `decodedEqualButEncodedBoundaryRemains=true`
- `remainingDiffKeysArePayloadPcSession=true`
- `promotedSingleTransitionCandidateCount=0`
- `readyForFreshExperiment=false`
- `goalComplete=false`

已排除单轴：

1. exact s00 payload+pc + fresh outer；
2. exact whole s00 body replay；
3. `pc` 单独变量；
4. marker / payload uuid 选择；
5. template outer params + fresh payload/pc；
6. forced-overlap lineage 下的 exact s00 payload+pc。

剩余耦合边界：

- decoded activities / fields 已相等；
- body length / payload length 已相等；
- remaining diff keys 收敛到 `payload, uuid, cs, pc, sid, p1, vid, ci, cts`；
- 但 payload、pc、marker、outer params、exact body 任一单轴都已被负控排除；
- 因此剩余不是可直接网络验证的 single transition，而是 live session / server-state binding。

结论：

- encoded/session binding 当前不能晋升 single transition candidate；
- fresh network experiment gate 仍关闭；
- 后续必须继续把 live session / server-state binding 拆到一个具体 pre-accept、client-visible、pure-protocol constructible 字段或状态突变。
