# 纯协议 HUMAN 成功复现：证据重置执行计划

## 当前权威入口（2026-06-13）

本文件保留为 reset 阶段证据和历史执行记录。后续实现不再沿本文档线性推进，改按新的方法论驱动计划执行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`

当前切换依据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `singleTransitionCandidateCount=0`
  - `runtimeJsCandidateReductionPromotedCount=0`
  - `runtimeJsCandidateReductionUnclassifiedCount=0`
  - `collectorHandlerPromotedCount=0`
  - `collectorHandlerUnclassifiedCount=0`
  - `noCurrentRouteToPhase5=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - blocking remains `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

日期：2026-06-13

## 0. 目标不变

最终目标仍然是实现并验证一条完整纯协议链路：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 仅使用 HTTP / JS 解析 / 加密 / 请求重放；
3. 从 Outlook signup 初始状态推进到 HUMAN collector 成功事件；
4. Microsoft `/API/Proofs/risk/verify` 返回 `state=continue`；
5. `/API/CreateAccount` 返回 `redirectUrl`；
6. 每一步都有本地证据路径、脚本和可复现命令。

本计划只重置执行方法，不降低完成标准。

## 1. 为什么需要新计划

当前已有计划和 artifact 已经把旧路线压到一个不可操作边界：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json`
  - `firstDivergenceAtFinalSeq5=true`
  - `decodedJsonEqual=true`
  - `requestHistoryOrderGapFalsified=true`
  - `remainingVariantFamilyNotSingle=true`
  - `serverObservableProxyNotFound=true`
  - `jsInternalReplayableTransitionNotFound=true`
  - `actionableFrontierNotFound=true`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_internal_unobserved_state_final_gap.json`
  - `singleTransitionCandidateCount=0`
  - `crossSampleCandidateClientVisibleProxyCount=0`
  - `allLocalProxySearchesNegative=true`
  - `readyForFreshExperiment=false`
  - remaining gap: `collector_server_internal_or_unobserved_expected_state`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/actionable_frontier_audit.json`
  - `actionableMissingArtifactCount=0`
  - `terminalAuthorityNextNull=true`
  - `nextArtifact=null`
  - `nextScript=null`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - 已证明：trace classifier、collector response decoder、collector payload constructor、POW recompute、`_px` cookie/token update、risk/verify rebuild、fresh TBR9/Ws.NQ、fresh AEAx/Ws.Ng
  - 仍缺：`end_to_end_pure_protocol_poc`
  - `goalComplete=false`

因此继续沿旧 artifact 的 `nextArtifact` 链执行没有证据基础。新计划不再补同一条死胡同，而是重新定义证据获取方式：用新的、成对的、可控变量样本重新建立状态机，而不是继续从已耗尽的本地样本中寻找单变量。

## 2. 方法论

### 2.1 证据原则

1. 禁止猜测；缺证据先补证据。
2. 所有结论必须引用本地文件路径和具体 checks。
3. 新实验必须先定义可证伪条件，再执行。
4. 每次 fresh attempt 必须使用新 session。
5. IP / Webshare / direct connection 只能作为受控变量进入实验矩阵，不能直接写成原因。
6. 不再以 `s00` accepted packet 为移植模板。
7. 不再把 decoded activity equality 当作成功充分条件。
8. 不再做 payload / pc / body / timing / HTTP2 的随机组合。

### 2.2 证据优先级

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage timeline；
6. 静态 JS；
7. 推断。

低优先级证据不能覆盖高优先级证据。

### 2.3 三段式推进

后续所有工作按三段推进：

1. **重新采样**：生成新的成对样本，不复用旧负控结论作为实验方案；
2. **状态机归纳**：从新样本归纳 collector server expected state 的可观测代理；
3. **最小协议实验**：只在出现单一、可操作、可观测 transition 时跑 fresh pure-protocol 实验。

## 3. 当前不能继续做的事

以下方向已经有本地反证或无可操作 frontier，除非出现新证据，否则禁止继续：

1. 直接重放 `s00` accepted body / payload / pc；
2. 随机替换 marker、uuid、PX561 tail、stack、AEAx、TBR9、Bzt；
3. 继续排列 HTTP/2 stream、seq5/seq6 response order、first-failure overlap；
4. 在 `singleTransitionCandidateCount=0` 时跑 fresh-session 网络实验；
5. 用 `decodedJsonEqual=true` 推断 collector 必须接受；
6. 用“可能是 IP”直接作为结论。

IP 相关假设只能通过本计划 Phase 2 的受控采样进入证据链。

## 4. 新假设集

### NH1: 当前样本集不足以暴露 server expected state 的可观测代理

Claim:

- 现有本地样本已经耗尽，未发现 replayable client transition；需要重新采样，尤其是采集同一运行窗口内的 success、near-failure、pure-protocol attempt 三类样本。

证据：

- `actionable_frontier_audit.json` 中 `actionableMissingArtifactCount=0`
- `server_internal_unobserved_state_final_gap.json` 中 `allLocalProxySearchesNegative=true`

可证伪条件：

- 如果新样本仍无法产生任何 client-visible proxy，则 NH1 不足以推进，需要转向服务端不可观测边界或外部约束。

### NH2: IP / proxy session 是必要但非充分的边界条件

Claim:

- IP / Webshare session 可能影响 collector expected state，但现有证据不能证明它是主因。

证据：

- 历史 direct/Webshare attempts 未得到 no-browser success；
- 用户指出需要参考浏览器 Webshare、同一会话一个 IP、多试几次、每次新尝试换 session。

可证伪条件：

- 同一采样矩阵中，只有 IP/session 变量变化且其他协议状态等价时，collector stage 稳定变化，才提升 NH2。

### NH3: 浏览器 success 中存在未被旧 hook 捕获的 state transition

Claim:

- 旧 hook 已覆盖大量 JS/runtime，但仍可能漏掉 worker、iframe、storage、crypto input、performance/time origin 或 parent bridge 的关键状态。

证据：

- 旧 JS taxonomy 未发现 replayable transition；
- 但该结论只覆盖已采集 hook，不覆盖未采集 hook。

可证伪条件：

- 新增 hook 后仍没有任何 success-only、pre-accept、可进入 request 或 cookie/risk 的状态差异。

### NH4: collector success 需要一个服务端已登记的 captcha lifecycle，而非单个 final seq5 request

Claim:

- final seq5 acceptance 可能依赖服务端看到的完整 lifecycle，而不是 final body 字段本身。

证据：

- `firstDivergenceAtFinalSeq5=true`
- `decodedJsonEqual=true` 仍失败
- `singleTransitionCandidateCount=0`

可证伪条件：

- 如果纯协议能复现完整 lifecycle 并在 final seq5 得到 `oIIoIooo|0`，则 NH4 被支持并进入 PoC。

## 5. 执行阶段

### Phase 0: 冻结新计划和旧证据边界

目的：

- 固定本文件为后续唯一入口；
- 记录旧路线已经耗尽的证据，不让旧 artifact 继续牵引执行。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`

完成条件：

- 文档列出最终目标、证据边界、新假设、采样矩阵、决策门、完成标准。

### Phase 1: 建立新采样清单

目的：

- 不立即跑网络；
- 先定义需要采的新样本、每类样本的变量、必须输出的 trace 字段。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_sampling_manifest.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_manifest.json`

必须包含：

- sample class:
  - `browser_success_webshare`
  - `browser_failure_webshare`
  - `pure_protocol_webshare`
  - `pure_protocol_direct`
- 每次 attempt 的 `session_id`；
- 每次 attempt 的 proxy/IP 证据；
- 是否同一 Webshare session；
- 是否新 Webshare session；
- 是否 direct；
- collector request/response trace path；
- decoded response path；
- cookie timeline path；
- JS/runtime hook path；
- risk/verify/CreateAccount path；
- 成功/失败判定标准。

决策门：

- manifest 缺少变量定义时，不执行网络；
- manifest 完整后进入 Phase 2。

### Phase 2: 受控采样，不做修复

目的：

- 只采证据，不修改协议字段；
- 用同一方法采浏览器和 pure protocol 对照；
- 把 IP/session 作为受控变量，而不是猜测原因。

执行规则：

1. 每一次新尝试都换新的 `session_id`。
2. Webshare attempt 记录代理 session 和出口 IP。
3. direct attempt 明确记录无代理证据。
4. 浏览器样本用于采证据，不计入最终 pure-protocol 成功。
5. pure protocol 样本不使用浏览器、Camoufox、真实鼠标、视觉、外部打码。
6. 每个 attempt 只跑到预定义终点，不临时改字段。

建议最小矩阵：

| class | count | variable |
| --- | ---: | --- |
| browser_success_webshare | 2 | 浏览器成功链路，Webshare |
| browser_failure_webshare | 2 | 浏览器失败或 near-failure，Webshare |
| pure_protocol_webshare | 3 | 纯协议，Webshare，每次新 session |
| pure_protocol_direct | 2 | 纯协议，direct，每次新 session |

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_sampling_matrix.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`

必须输出：

- 每个 attempt 的 raw trace；
- collector decoded response；
- final stage；
- IP/proxy/session 证据；
- `_px` cookie/token timeline；
- risk/verify/CreateAccount 结果；
- 是否发生 `oIIoIooo|-1`、`{do:[]}`、cookie handler、`oIIoIooo|0`。

决策门：

- 如果采样无法稳定产生 browser success，则先修采集，不进入 Phase 3；
- 如果 pure protocol direct 与 Webshare 没有阶段差异，NH2 降级；
- 如果 Webshare pure protocol 出现阶段推进，进入 Phase 5 最小实验复现；
- 如果没有阶段推进，进入 Phase 3 状态机归纳。

### Phase 3: 新样本状态机归纳

目的：

- 从新样本重建 collector lifecycle；
- 找 success-only 或 stage-advance-only 的 client-visible proxy。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_state_machine.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`

必须比较：

- request chronology；
- `seq/rsc`；
- decoded `do[]/ob`；
- handler dispatch；
- worker/iframe/parent bridge；
- cookie/storage mutation；
- POW/WASM inputs and outputs；
- collector response classes；
- risk/verify consumption；
- IP/session class。

必须输出：

- state nodes；
- transitions；
- success-only transitions；
- failure-only transitions；
- pure-protocol missing transitions；
- transitions 是否进入 request/cookie/risk；
- 每个 transition 的证据路径。

决策门：

- `clientVisibleProxyCount > 0` 时进入 Phase 4；
- `clientVisibleProxyCount = 0` 且采样完整时，记录为服务端不可观测边界，停止网络试错。

### Phase 4: 单变量候选归约

目的：

- 把 Phase 3 的 proxy 压缩成一个可测试 transition；
- 明确可证伪实验。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_single_transition_candidates.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_single_transition_candidates.json`

必须输出：

- candidate id；
- 来源证据；
- 出现在哪些 success；
- 缺失在哪些 failure；
- 是否进入 request/cookie/risk；
- 是否可由纯协议构造；
- 是否与 IP/session 解耦；
- 已有反证；
- 最小实验方案。

决策门：

- `singleTransitionCandidateCount=1` 且 `readyForFreshExperiment=true` 才进入 Phase 5；
- 多个候选耦合时，继续离线归约；
- 没有候选时，不跑 fresh 实验。

### Phase 5: 一个 fresh-session 最小实验

目的：

- 只验证一个 transition；
- 不做组合试错。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_minimal_transition_experiment.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_minimal_transition_experiment_audit.json`

规则：

1. 每次新实验换新 session。
2. 如果实验走 Webshare，记录 Webshare session 和出口 IP。
3. 如果实验走 direct，记录 direct 证据。
4. 只修改 Phase 4 选出的一个 transition。
5. 不修改未授权变量。
6. 不使用浏览器、Camoufox、真实鼠标、视觉、外部打码。

阶段推进标准：

- `oIIoIooo|-1` -> `{do:[]}`；
- `{do:[]}` -> cookie/token handler；
- cookie/token handler -> `oIIoIooo|0`；
- `oIIoIooo|0` -> risk/verify `state=continue`；
- risk/verify `state=continue` -> CreateAccount `redirectUrl`。

决策门：

- 有阶段推进：进入 Phase 6 扩展为完整 PoC；
- 无阶段推进：候选被证伪，回 Phase 4；
- 响应类别不稳定：回 Phase 2 增加同类采样，但必须先更新 manifest。

### Phase 6: 完整纯协议 PoC

目的：

- 把阶段推进扩展为最终目标的完整链路。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_end_to_end_pure_protocol_poc.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_end_to_end_pure_protocol_poc.json`

必须输出：

- fresh session id；
- proxy/direct 证据；
- collector success raw response；
- collector success decoded response；
- `_px` jar mutation；
- risk/verify request/response；
- CreateAccount request/response；
- `state=continue`；
- `redirectUrl`；
- 全流程命令。

完成门：

- 只有该产物证明完整链路，才能把 `goalComplete` 更新为 true。

### Phase 7: 更新全局审计

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.md`

必须更新：

- reset plan path；
- 新采样矩阵；
- 新状态机；
- 单变量候选；
- 最小实验；
- end-to-end PoC；
- 最终缺口。

## 6. 当前执行结果（2026-06-13）

本节记录本计划执行到当前的证据状态。后续以本节和第 7 节作为入口，不回到旧 artifact 链上继续试错。

### 6.1 Reset 采样覆盖已经完成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_runner_audit.json`
  - `executedAttemptCount=11`
  - `countedResetAttemptCount=8`
  - `countedBrowserSuccessResetCount=4`
  - `countedBrowserFailureResetCount=4`
  - `browserResetCoverageComplete=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`
  - `browserRunnerExecutedCount=11`
  - `resetSamplingComplete=true`
  - `pureProtocolResetSamplingComplete=true`
  - `readyForStateMachine=true`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_coverage_audit.json`
  - `browserResetCoverageComplete=true`
  - `pureProtocolResetCoverageComplete=true`
  - `allResetCoverageComplete=true`
  - `readyForFreshExperiment=false`

有效 browser reset 对照样本已经满足最小矩阵；继续盲目增加样本不符合本计划的方法论。

### 6.2 Webshare / direct 不是已证明主因

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`
  - `pureProtocolWebshareResetCount=6`
  - `pureProtocolDirectResetCount=2`
  - `pureWebshareFinalNoSuccessCount=3`
  - `pureDirectFinalNoSuccessCount=2`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_final_response_class_audit.json`
  - `webshareSampleCount=3`
  - `directSampleCount=2`
  - `allSeq5Http200=true`
  - `allSeq6Http200=true`
  - `allFinalResponsesSameClass=true`
  - `allFinalResponsesAreSeq5Minus1=true`
  - `anySeq5Success0=false`

结论边界：

- 只能说当前 reset pure-protocol 的 Webshare 与 direct 样本都没有 collector success；
- 不能把 IP 写成主因；
- 后续只有在出现“同一协议状态、仅 IP/session 变化导致阶段稳定变化”的新证据时，才能提升 NH2。

### 6.3 新 hook 轴覆盖和对照已经闭合

新增/确认的 instrumentation：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`
  - message bridge；
  - Worker / POW；
  - document.cookie；
  - fetch / XHR / sendBeacon；
  - WASM material / NQ；
  - localStorage / sessionStorage / indexedDB；
  - performance.now / Date.now；
  - crypto.getRandomValues / crypto.subtle。

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_new_hook_axis_plan.json`
  - `countedAttemptCount=8`
  - `countedRuntimeTraceCount=8`
  - `countedJsInternalTraceCount=4`
  - `countedSuccessWithJsInternalTraceCount=2`
  - `countedFailureWithJsInternalTraceCount=2`
  - `missingObservedHookCount=0`
  - `missingContrastHookCount=0`
  - `notInstrumentedHookCount=0`
  - `recommendedAxisCount=0`
  - `readyForFreshExperiment=false`

补样原因和结果：

- 旧 hook-axis audit 曾显示 `crypto` 只有 failure 侧观察；
- 已补一条新 Webshare success session：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_success_webshare_ibtvqcnm-JP-1781297091000_1781297091.json`
  - JS trace: `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_lnpmksz7yhft_1781297097.jsonl`
  - matrix 分类：`browser_runtime_success_redirect`、`successLike=true`、`countsTowardResetMinimum=true`
- 重新审计后 `crypto.successCount=1`、`crypto.failureCount=1`，hook contrast 缺口关闭。

### 6.4 状态机仍没有 client-visible proxy

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`
  - `sampleCount=23`
  - `browserSuccessBaselineCount=7`
  - `browserFailureBaselineCount=8`
  - `browserSuccessResetCount=4`
  - `browserFailureResetCount=4`
  - `clientVisibleProxyCount=0`
  - `readyForSingleTransitionReduction=false`
  - `readyForFreshExperiment=false`
- hook feature counts:
  - `worker`: success `4`, failure `0`
  - `wasm`: success `4`, failure `0`
  - `pow_worker`: success `4`, failure `0`
  - `crypto`: success `1`, failure `1`
  - `storage`: success `2`, failure `2`
  - `performance`: success `2`, failure `2`
  - `message_bridge`: success `2`, failure `2`

解释边界：

- `worker/wasm/pow_worker` 是 browser success 相关特征；
- 但状态机没有证明它们是 pre-accept、client-visible、pure-protocol 可单独构造的 transition；
- 因此不能直接把它们作为 Phase 5 输入。

### 6.5 Success-only hook feature reducer 已完成，未晋升候选

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_hook_feature_candidate_reduction.json`
  - `successOnlyHookFeatureCandidateCount=3`
  - `reductionCount=3`
  - `promotedSingleTransitionCandidateCount=0`
  - `allHookAxesClosed=true`
  - `existingSingleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`

逐项结论：

- `worker`
  - success `4` / failure `0`
  - reducer 判定：已有 pure-protocol 语义等价物是 `pow_recompute`；
  - reset pure-protocol 已经到达 POW 阶段但 final collector 仍未 success；
  - 不晋升 Phase 5。
- `pow_worker`
  - success `4` / failure `0`
  - reducer 判定：这是 POW 的浏览器执行路径，不是独立协议 transition；
  - 不晋升 Phase 5。
- `wasm`
  - success `4` / failure `0`
  - reducer 判定：`fresh_tbr9_ws_nq` 和 `fresh_aeax_ws_ng` 已在本地审计中证明；
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/wasm/wasm_ng_runtime_random_replay_audit_gwyi06rpe015_1781208840.json`
    - `offlineNgMatchesRuntimeAeax=true`
    - `offlineNqMatchesRuntimeTbr9=true`
    - `allReplayRandomSourcesProvided=true`
  - 不晋升 Phase 5。

共同负控：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_final_response_class_audit.json`
  - `allFinalResponsesSameClass=true`
  - `allFinalResponsesAreSeq5Minus1=true`
  - `anySeq5Success0=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_cookie_mutation_audit.json`
  - `allOfflineJarHasPx3Pxde=true`
  - `allHaveFailureMinus1=true`
  - `anySuccess0=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_single_transition_candidates.json`
  - `singleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`

### 6.6 当前总目标仍未完成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
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

### 6.7 Terminal boundary audit 已生成

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `allInputsExist=true`
  - `resetSamplingComplete=true`
  - `allResetCoverageComplete=true`
  - `stateMachineClientVisibleProxyCount=0`
  - `singleTransitionCandidateCount=0`
  - `hookAxisRecommendedAxisCount=0`
  - `hookAxisMissingObservedHookCount=0`
  - `hookAxisMissingContrastHookCount=0`
  - `hookAxisNotInstrumentedHookCount=0`
  - `promotedSingleTransitionCandidateCount=0`
  - `runtimeJsCandidateReductionPromotedCount=0`
  - `runtimeJsCandidateReductionUnclassifiedCount=0`
  - `resetLocalProxySearchesNegative=true`
  - `noCurrentRouteToPhase5=true`
  - `endToEndPureProtocolPocMissing=true`

该 artifact 是当前路线 B 的终端边界审计。它不是目标完成证明；它只证明当前 reset 证据没有可执行 Phase 5 入口。

### 6.8 路线 A：reset runtime/JS 未分类事件已审计并归约

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_runtime_js_event_taxonomy.json`
  - `countedBrowserSampleCount=8`
  - `countedSuccessCount=4`
  - `countedFailureCount=4`
  - `successWithJsTraceCount=2`
  - `failureWithJsTraceCount=2`
  - `featureCount=435`
  - `candidateClientVisibleProxyCount=194`
  - `strongJsContrastCandidateCount=62`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_runtime_js_candidate_reduction.json`
  - `candidateInputCount=194`
  - `reductionCount=194`
  - `promotedSingleTransitionCandidateCount=0`
  - `unclassifiedReductionCount=0`
  - `allCandidatesReduced=true`
  - `negativeControlsAllHold=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_onecollector_surface_audit.json`
  - `oneCollectorSuccessSampleCount=3`
  - `oneCollectorFailureSampleCount=0`
  - `oneCollectorAbsentInAllFailures=true`
  - `oneCollectorAfterAcceptedChainCount=3`
  - `allOneCollectorSuccessRowsAfterAcceptedChain=true`
  - `networkSurfaceReductionCount=2`
  - `promoteToSingleTransitionCandidate=false`

归约分类：

- `hsprotect_event_bus=9`
- `collector_response_handler=152`
- `wasm_or_crypto_runtime=19`
- `worker_pow_runtime=11`
- `sendbeacon_internal=1`
- `onecollector_telemetry=2`

结论边界：

- reset runtime/JS trace 里确实存在大量 success-correlated surfaces；
- 但它们归约后仍只是 event bus、collector response handler、WASM/crypto、worker/POW、sendBeacon 或 OneCollector telemetry；
- 唯一 network surface 是 `browser.events.data.microsoft.com/OneCollector/1.0/`；它在 3 条 success 样本中出现、failure 样本中不出现，但 3 条都发生在 CreateAccount redirect 后，是 Microsoft telemetry，不是 HUMAN collector pre-accept transition；
- 没有任何一项被证明为“pre-accept、client-visible、pure-protocol constructible、single transition”；
- 因此路线 A 当前也不能打开 Phase 5。

## 7. 下一步方法论

当前证据不支持继续“多试几次”或直接跑 Phase 5。下一步必须从“已闭合 hook/采样但仍无 candidate”的状态出发，寻找新的证据入口。允许的入口只有以下三类。

### 7.1 路线 A：寻找未进入现有 hook 的 client-visible lifecycle 证据

目标：

- 找到一个新的、可观测、pre-accept、能进入 request/cookie/risk 的 transition。

可做事项：

1. 审计浏览器成功 trace 中未分类事件和未解析 network body；
2. 审计 iframe / service worker / shared worker / message channel 是否还有未 hook 的边；
3. 审计 storage timeline 是否有值未进入当前 `storage` 粗粒度计数；
4. 审计 risk/verify 前后 Microsoft 页面状态是否有 collector response 以外的桥接字段。

禁止：

- 只因为某事件 success-only 就进入 Phase 5；
- 未证明该事件能由 pure protocol 构造就跑 fresh experiment。

产物要求：

- 新 artifact 必须输出 `clientVisibleProxyCount`；
- 若为 0，必须写明覆盖范围；
- 若大于 0，进入第 8 节 Phase 4。

### 7.2 路线 B：证明边界确实是 collector server-internal / unobserved state

目标：

- 不是猜“服务端内部”，而是列出已覆盖的客户端观测面和全部反证。

可做事项：

1. 汇总 reset 采样、hook-axis、feature reducer、final response class、cookie mutation 的证据；
2. 明确哪些客户端变量已经被覆盖；
3. 明确哪些变量仍未覆盖，且为什么当前工具无法观察；
4. 形成一个新的 terminal audit，阻止继续无目标网络试错。

产物要求：

- `allHookAxesClosed=true`
- `promotedSingleTransitionCandidateCount=0`
- `singleTransitionCandidateCount=0`
- `end_to_end_pure_protocol_poc` 仍 missing
- 决策必须是“不进入 Phase 5”，而不是“目标完成”。

### 7.3 路线 C：如果新增外部证据，重新打开采样矩阵

只有出现以下证据之一，才能重新跑网络采样：

1. 新 hook 代码能捕获之前没有的具体字段；
2. 新静态 JS 证据显示一个未采集 API 或 lifecycle 边；
3. 新协议审计显示 Webshare/direct 或 session/IP 有可证伪差异；
4. 出现一个可单独构造的 candidate transition。

重新采样规则不变：

- 每次新尝试必须新 session；
- Webshare 记录 session 和出口 IP；
- direct 记录无代理证据；
- browser 只作为对照，不计最终 pure-protocol success；
- 没有 candidate 不跑 Phase 5。

## 8. 后续实现顺序

严格按以下顺序执行：

1. 当前入口：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`
2. 当前证据门：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
3. 如果选择路线 A：
   - 先写审计脚本；
   - 输出新的 candidate/proxy artifact；
   - 再运行 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_single_transition_candidates.py`
4. 如果选择路线 B：
   - 写 terminal boundary audit；
   - 不运行网络；
   - 更新 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
5. 如果选择路线 C：
   - 先更新 manifest；
   - 再采样；
   - 然后重跑：
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/reclassify_reset_browser_sampling_attempts.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_browser_sampling_runner_audit.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_sampling_matrix.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_sampling_coverage_audit.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_state_machine.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_single_transition_candidates.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_new_hook_axis_plan.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_hook_feature_candidate_reduction.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_runtime_js_event_taxonomy.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_runtime_js_candidate_reduction.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_onecollector_surface_audit.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_terminal_boundary_audit.py`
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`
6. 仅当 `singleTransitionCandidateCount=1` 且 `readyForFreshExperiment=true` 时，才允许运行 Phase 5 最小实验。
7. 有阶段推进后，才允许运行完整纯协议 PoC。

## 9. 输出规范

所有新 JSON artifact 必须包含：

```json
{
  "generatedAt": "",
  "plan": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md",
  "inputs": [],
  "checks": {},
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

如果 artifact 进入网络实验，必须额外包含：

```json
{
  "attempt": {
    "sessionId": "",
    "transport": "webshare_or_direct",
    "proxyEvidence": {},
    "ipEvidence": {},
    "freshSession": true
  },
  "stage": {
    "before": "",
    "after": "",
    "advanced": false
  }
}
```

## 10. 完成标准

本计划文档完成不代表最终目标完成。

最终目标只有在以下证据全部成立时才算完成：

1. fresh pure-protocol session 产生 collector HUMAN success；
2. collector response 离线解码包含成功状态；
3. decoded response handler 可离线更新 `_px` cookie/token jar；
4. risk/verify 使用该 jar 返回 `state=continue`；
5. CreateAccount 返回 `redirectUrl`；
6. 全流程不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码；
7. 每一步都有本地证据路径和可复现命令。
