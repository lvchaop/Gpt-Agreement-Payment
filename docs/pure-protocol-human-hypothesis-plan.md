# 纯协议 HUMAN 成功复现：假设驱动重规划

## 当前权威入口（2026-06-13）

本文件保留为历史假设树和证据背景。后续实现以新的方法论驱动执行计划为准：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-methodological-execution-plan.md`

reset 阶段计划仍保留为证据记录：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`

当前最新证据门：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_terminal_boundary_audit.json`
  - `resetSamplingComplete=true`
  - `allResetCoverageComplete=true`
  - `stateMachineClientVisibleProxyCount=0`
  - `singleTransitionCandidateCount=0`
  - `runtimeJsCandidateReductionPromotedCount=0`
  - `runtimeJsCandidateReductionUnclassifiedCount=0`
  - `collectorHandlerPromotedCount=0`
  - `collectorHandlerUnclassifiedCount=0`
  - `resetLocalProxySearchesNegative=true`
  - `noCurrentRouteToPhase5=true`
  - `endToEndPureProtocolPocMissing=true`
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
  - `allOneCollectorSuccessRowsAfterAcceptedChain=true`
  - `promoteToSingleTransitionCandidate=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_hook_feature_candidate_reduction.json`
  - `successOnlyHookFeatureCandidateCount=3`
  - `promotedSingleTransitionCandidateCount=0`
  - `allHookAxesClosed=true`
  - `existingSingleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_new_hook_axis_plan.json`
  - `missingObservedHookCount=0`
  - `missingContrastHookCount=0`
  - `notInstrumentedHookCount=0`
  - `recommendedAxisCount=0`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - blocking remains `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

执行约束：

- 不再沿旧 `nextArtifact=null` 的链条继续补随机负控；
- 不在 `singleTransitionCandidateCount=0` 时跑 fresh Phase 5；
- 不把 IP / Webshare / direct 写成原因，除非有受控变量证据；
- 不把 `worker/wasm/pow_worker` success-only 相关性直接当成可重放 transition。

## 最终目标不变

实现并验证“完全纯协议解析 + 复现 HUMAN 成功包”的可行闭环：

- 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
- 纯 HTTP / JS 解析 / 加密 / 请求重放；
- 从 Outlook signup 初始状态推进到 HUMAN collector 成功事件；
- 让 Microsoft `/API/Proofs/risk/verify` 返回 `state=continue`；
- 继续让 `/API/CreateAccount` 返回 `redirectUrl`。

所有结论必须可追溯到本地证据：

- 静态 JS；
- 运行时 hook；
- network trace / HAR；
- cookie / storage 时间线；
- collector decoded response；
- 成功/失败对照样本；
- live protocol experiment 输出。

缺少证据时只记录为假设或缺口，不写成结论。

## 为什么重规划

旧路线把主要精力放在“构造一个像 s00 accepted line933 的成功包”：

- 搬运 s00 payload / pc / body；
- 逐字段替换 PX561 tail、stack、inner uuid、AEAx、TBR9、Bzt；
- 调整 HTTP/2 stream、seq5/seq6 response order、first-failure overlap；
- 追求 decoded activity equality。

现有审计已经证明这些方向都不是充分条件：

- exact whole body replay 不成功；
- exact payload+pc 放到 fresh outer session 返回 `{do:[]}`；
- decoded activity equality 仍不成功；
- h2 / stream / response order / first-failure ordering 仍不成功；
- fresh POW/WASM tail、inner uuid、stack 等单变量或组合仍不成功。

因此后续不再继续随机堆字段负控。新路线改为：

> 用假设树约束探索范围，用状态转移 diff 找第一个 decisive divergence，再只针对这个 divergence 做最小实验。

## 方法论

### 核心规则

1. 每一步只验证一个假设。
2. 每个假设必须有可证伪条件。
3. 证据优先级固定，不用弱证据覆盖强证据。
4. 不进入下一层，除非上一层已有能改变决策的证据。
5. 负控不是越多越好，只保留能改变决策的负控。
6. 不把 decoded activity equality 当作成功充分条件。
7. 不再把 s00 accepted packet 当作可跨 session 移植模板。

### 证据优先级

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage timeline；
6. 静态 JS；
7. 推断。

## 总问题

s00 浏览器 session 的 line933 为什么被 collector 接受，而 pure protocol fresh session 没有被接受？

不能预设答案是字段、IP、HTTP/2、时序、cookie、worker、captcha lifecycle 或 Microsoft context。它们都必须进入假设树，由证据决定优先级。

## 假设树

### H0: 成功包本身不可跨 session 重放

Claim:

- accepted line933 的 payload / pc / body 绑定 session-side state，不是可跨 fresh session 搬运的静态成功包。

已有支持证据：

- exact whole body replay 不成功；
- exact payload+pc + fresh outer 返回 `{do:[]}`；
- decoded activity equality 仍不成功。

可证伪条件：

- 如果某个 fresh session 在没有复现 s00 服务端状态的情况下，仅靠移植 accepted line933 body/payload/pc 就成功，则 H0 被证伪。

当前状态：

- 强支持。后续不再把“搬 accepted packet”作为主路线。

### H1: 失败原因在 request body 可见字段内

Claim:

- 服务端 HUMAN 判定主要由 collector request body 内可见字段决定。

已有反证：

- decoded activity equality 不充分；
- tail / stack / inner uuid / AEAx / TBR9 / Bzt 多个字段控制不充分；
- exact payload+pc 跨 fresh outer 不成功。

可证伪条件：

- 如果 s00 与 fresh 的 collector-visible transition 完全一致，但 body 生成输入存在 decisive 差异，并且修正该 body 差异能阶段推进，则 H1 重新升优先级。

当前状态：

- 弱。暂停 body-field 单变量试错。

### H2: 失败原因在 transport / HTTP2 / 响应顺序

Claim:

- 服务端接受依赖 Webshare IP/session、HTTP/2 stream、seq5/seq6 overlap、first-failure response order 等 transport/timing 条件。

已有反证：

- h2 single TLS session / stream 1/3 不充分；
- seq6 response before seq5 completion 不充分；
- first-failure overlap 与 forced first-failure response order 不充分；
- 同一 Webshare session 多次 fresh probe 不充分。

可证伪条件：

- 如果状态转移 diff 显示 body/state 完全一致，唯一差异是 transport/timing，并且复现该差异后阶段推进，则 H2 重新升优先级。

当前状态：

- 基本排除为主因。停止 h2 排列组合。

### H3: 失败原因在 collector server-side session state

Claim:

- s00 在 line933 前经历了 pure protocol 没有经历或顺序不同的 collector-visible state transition，导致服务端 expected state 不同。

需要证据：

- s00 与 fresh 的 collector request/response/handler/cookie/token/state 消费链 diff；
- 第一个会影响后续状态的 divergence；
- 一个 fresh-session 最小实验能证明修正该 transition 后阶段推进。

可证伪条件：

- 如果 s00 与 fresh 在 collector-visible transition 上完全一致，但结果仍不同，则 H3 降级。

当前状态：

- 高优先级，下一阶段主线。

### H4: 失败原因在 browser-only runtime state

Claim:

- accepted line933 的生成或 acceptance 依赖 network body 外的 browser-only state，例如 worker message、iframe postMessage、parent bridge、in-memory object、closure counter、performance/timing state、captcha/challenge runtime state。

需要证据：

- accepted line933 generation lineage；
- `tf.payload` 上游输入；
- PX561 activity fields 来源；
- `pc` 输入 serialized 来源；
- marker / jo / uuid 来源；
- browser-only mutation 是否进入 payload generation 或下一请求状态。

可证伪条件：

- 如果 accepted line933 所有输入都可追溯到 network trace + static JS + cookie timeline，且无 browser-only state 参与，则 H4 降级。

当前状态：

- H3 后的第二主线。

### H5: 失败原因在 Microsoft context binding

Claim:

- collector HUMAN acceptance 绑定 Microsoft 页面上下文或 upstream risk state，例如 iframe origin、challenge URL、Microsoft session id、risk token、referer/origin、browser navigation state。

需要证据：

- s00 accepted 请求与 pure request 的 Microsoft context lineage 对照；
- collector app/session 与 Microsoft challenge/risk state 的映射；
- risk/verify 前后的 cookie/header/context 消费链。

可证伪条件：

- 如果 collector acceptance 只依赖 hsprotect collector/session，而与 Microsoft page context 无关，则 H5 降级。

当前状态：

- 中低优先级。先完成 H3/H4。

## 执行计划

### Phase 1: 固定对照组

目的：

- 避免多样本漂移；
- 后续所有 diff 都围绕一个 success sample 和一个完整 fresh failed sample。

固定 success sample：

- `s00ld1lglrw0_1781191381`

fresh failed sample 选择条件：

- bootstrap 已完成；
- second request 已完成；
- sequence 已完成；
- bundle POW 已完成；
- first-failure overlap 或等价 lineage 已完成；
- final seq5/seq6 已发送；
- collector response 可离线 decode；
- cookie/jar timeline 可重建或可由 response handler 推导。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/selected_contrast_pair.json`

必须包含：

- success trace paths；
- fresh attempt paths；
- final seq5/seq6 paths；
- decoded response paths；
- cookie timeline paths；
- 样本选择理由；
- 样本已知限制。

### Phase 2: 生成假设矩阵

目的：

- 把已有证据按 H0-H5 归档；
- 明确哪些方向已低收益；
- 明确每个假设的 next decisive test。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_hypothesis_matrix.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_matrix.json`

结构：

```json
{
  "hypotheses": {
    "H0_packet_not_portable": {
      "claim": "",
      "supportingEvidence": [],
      "contradictingEvidence": [],
      "missingEvidence": [],
      "currentStatus": "",
      "nextDecisiveTest": ""
    }
  }
}
```

决策门：

- 如果某假设只有弱推断，没有强证据，不允许作为下一实验依据；
- 下一步只能选择 `nextDecisiveTest` 最明确且能改变路线的假设。

### Phase 3: 建 collector 状态转移 diff

目的：

- 不比较孤立字段；
- 比较 s00 与 fresh 从 first failure 到 final seq5 的状态链。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_state_transition_diff.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json`

比较维度：

- collector request 顺序；
- request URL / method；
- seq / rsc；
- request 类型：PX561 / non-PX / beacon / asset / challenge；
- response status；
- decoded `do[]` / `ob`；
- response handlers；
- `_px3/_pxde/_pxvid` mutations；
- cookie domain/path/samesite/secure；
- postMessage bridge mutation；
- state 是否被下一请求消费；
- s00 与 fresh 的第一个 divergence。

输出必须包含：

- timeline；
- per-step mapping；
- divergence candidates；
- 每个 candidate 的证据路径与 line；
- 每个 candidate 是否可能影响后续请求或服务端 expected state。

### Phase 4: 提取 first decisive divergence

目的：

- 不全量修所有差异；
- 只找第一个会改变后续状态的分叉点。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/find_first_decisive_divergence.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json`

判断顺序：

1. response handler 差异；
2. cookie jar 差异；
3. seq/rsc/state counter 差异；
4. postMessage / worker 差异；
5. payload generation input 差异；
6. transport/timing 差异。

必须包含：

- divergence id；
- hypothesis id；
- s00 证据路径和 line；
- fresh 证据路径和 line；
- divergence 内容；
- 为什么它可能影响 HUMAN acceptance；
- 可证伪条件；
- 最小复现实验方案。

决策门：

- 没有 `first_decisive_divergence.json`，不允许继续 fresh-session 实验；
- divergence 不能只写“可能有关”，必须说明它如何影响下一步 request、cookie、handler 或 server expected state。

### Phase 4.5: 建 final seq5 前状态 lineage

目的：

- `first_decisive_divergence.json` 已把第一个 decisive divergence 定位到 final seq5 acceptance response；
- 在 fresh-session 实验前，必须继续缩小 final seq5 前的因果边界；
- 不能直接把 “final seq5 response 不同” 当作实验方案。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pre_seq5_state_lineage_detail.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json`

必须比较：

- s00 line635 collector seq4 response 到 line933 final seq5 request 之间的 runtime network events；
- s00 JS line623 到 line922 之间的 handler dispatch、postMessage bridge、captcha rendered、POW worker、WASM Ng/NQ、TBR9/PX561 payload 生成链；
- fresh selected sample 的 seq4 response state、fresh POW、fresh WASM Ng/NQ、final seq5 request material；
- forced-overlap decoded boundary：decoded activities 相等但 encoded payload / body / pc 不同；
- 既有 head / timing / h2 / response-order controls 是否已经反证某些边界。

输出必须包含：

- s00 pre-seq5 event timeline；
- fresh pre-seq5 lineage；
- final seq5 request material diff；
- browser-only state candidates；
- encoded/session binding candidates；
- server-side expected-state candidates；
- 每个 candidate 的证据路径和 line；
- 每个 candidate 的可证伪条件；
- 是否足以进入一个最小 fresh-session 实验。

决策门：

- 如果不能把 final seq5 divergence 收敛到一个可操作的 state transition，不允许跑 fresh-session；
- 如果只能证明“final response 不同”，则继续补 lineage，不进入实验。

### Phase 4.6: 校验 request-history coherence，避免被错误排序牵引

目的：

- 验证 selected fresh contrast 的真实请求顺序；
- 防止 artifact 构造时按 `seq/rsc` 排序造成伪 divergence；
- 只有 live attempt steps 与重建 timeline 一致时，才能把 request-history gap 当作实验方向。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_request_history_coherence_gap.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json`

必须比较：

- selected fresh attempt 的实际执行顺序；
- `collector_state_transition_diff_s00_vs_fresh.json` 中的 fresh chronology；
- s00 与 fresh 在 first bundle POW 前是否都已完成 `msft seq1/rsc2`、`msft seq2/rsc3`、`msft seq3/rsc4`；
- 如果发现 chronology 由脚本错误排序产生，必须先修脚本并重跑 Phase 3 起所有下游产物。

决策门：

- `hasOrderGap=false` 时，禁止把“msft-before-bundle POW 顺序”作为 fresh-session 实验；
- `hasOrderGap=true` 时，才允许把 request-history order 作为 Phase 5 的单变量实验；
- 无论结果如何，都必须保留实际 attempt steps 作为证据来源。

### Phase 4.7: 生成下一个 decisive static gap

目的：

- 在 request-history order 被反证后，继续用静态证据缩小 final seq5 前的未解释差异；
- 不恢复随机字段组合；
- 不在没有单一可操作 divergence 前跑 fresh-session。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/next_decisive_static_gap.json`

候选方向只允许来自已生成证据：

1. `accepted_line933_generation_lineage.json` 中仍未解释的 `tf.payload` / serialized / `pc` binding；
2. `server_expected_state_pre_seq5_gap.json` 中未被单变量 controls 覆盖的 state transition；
3. `server_state_transition_value_model.json` 中 final seq5 前最后一个未解释的 handler/value 绑定；
4. browser-only runtime state，必须能证明它进入 payload generation 或 server-visible request。

决策门：

- `next_decisive_static_gap.json` 必须给出一个 `recommendedExperiment` 或明确 `readyForFreshExperiment=false`；
- 如果仍不能给出单变量实验，继续补静态 lineage，不跑网络。

### Phase 5: 只做一个最小实验

目的：

- 验证 first decisive divergence；
- 不做随机字段组合；
- 不搬运 s00 accepted packet。

实验规则：

- 使用 fresh Webshare session；
- 每次新尝试更换 session；
- 只修改一个 state transition；
- 不启动浏览器/Camoufox；
- 不调用 captcha provider；
- 不使用真实鼠标/视觉；
- 保持纯协议；
- 成功标准是阶段推进，不要求一步 HUMAN。

阶段推进定义：

- `oIIoIooo|-1` -> `{do:[]}`；
- `{do:[]}` -> cookie/token handler；
- cookie/token handler -> `oIIoIooo|0`；
- `oIIoIooo|0` -> risk/verify `state=continue`；
- risk/verify `state=continue` -> CreateAccount `redirectUrl`。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/minimal_divergence_experiment_audit.json`

必须包含：

- tested divergence；
- fresh session id；
- request material；
- response decode；
- cookie/token mutation；
- stage before / after；
- 是否阶段推进；
- 下一步决策。

### Phase 6: 更新总审计

目的：

- 让全局 goal audit 反映新方法论；
- 不再让旧负控牵引下一步。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.md`

必须更新：

- H0-H5 hypothesis matrix summary；
- selected contrast pair；
- collector state transition diff；
- first decisive divergence；
- minimal experiment result；
- `end_to_end_pure_protocol_poc` 的真实缺口。

## 后续实现顺序

严格按以下顺序执行：

1. `selected_contrast_pair.json`
2. `hypothesis_matrix.json`
3. `collector_state_transition_diff_s00_vs_fresh.json`
4. `first_decisive_divergence.json`
5. `pre_seq5_state_lineage_detail.json`
6. `accepted_line933_generation_lineage.json`
7. `server_expected_state_pre_seq5_gap.json`
8. `server_state_transition_value_model.json`
9. `request_history_coherence_gap.json`
10. `next_decisive_static_gap.json`
11. `minimal_divergence_experiment_audit.json`
12. 更新 `pure_protocol_goal_gap_audit.json`

如果某一步证据不足：

- 先补该步需要的最小证据；
- 不跳到 fresh-session 实验；
- 不恢复旧的字段 split-control 路线。

## 当前执行基线

本节记录截至本计划文档当前版本已经存在的本地证据。后续实现必须以这些文件为输入；如果任一文件被更新，必须重新校验对应 checks。

已生成产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/selected_contrast_pair.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_matrix.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_state_transition_diff_s00_vs_fresh.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/pre_seq5_state_lineage_detail.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/accepted_line933_generation_lineage.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_expected_state_pre_seq5_gap.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_state_transition_value_model.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/next_decisive_static_gap.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/line922_candidate_reduction.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_state_value_to_request_lineage.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/final_boundary_decision_matrix.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coupled_encoder_variant_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_internal_state_gap_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_encoder_variant_build_matrix.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_observable_state_inventory.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/s00_risk_verify_material_gap.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_to_risk_consumption_chain.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/single_transition_candidate_matrix.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/coupled_boundary_reduction_plan.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/outer_session_tuple_factorization.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoder_axis_equivalence.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_expected_state_observable_proxy.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_s00ld1lglrw0_1781191381.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/forced_overlap_template_final_encoded_decoded_boundary_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

已生成脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/select_hypothesis_contrast_pair.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_hypothesis_matrix.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_state_transition_diff.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/find_first_decisive_divergence.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_pre_seq5_state_lineage_detail.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_accepted_line933_generation_lineage.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_expected_state_pre_seq5_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_state_transition_value_model.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_request_history_coherence_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_next_decisive_static_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_line922_dynamic_field_source_map.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_line922_candidate_reduction.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_encoded_payload_pc_form_diff_map.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_state_value_to_request_lineage.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_final_boundary_decision_matrix.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_coupled_encoder_variant_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_internal_state_gap_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_remaining_encoder_variant_build_matrix.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_hypothesis_reframe_status.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_observable_state_inventory.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_bridge_to_payload_context_audit.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_s00_risk_verify_material_gap.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_to_risk_consumption_chain.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_single_transition_candidate_matrix.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_coupled_boundary_reduction_plan.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_outer_session_tuple_factorization.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_encoder_axis_equivalence.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_server_expected_state_observable_proxy.py`

当前 checks：

- `hypothesis_matrix.json`:
  - `selectedContrastPairExists=true`
  - `allHypothesesPresent=true`
  - `primaryNextIsH3=true`
  - `noFreshExperimentBeforeDivergence=true`
- `collector_state_transition_diff_s00_vs_fresh.json`:
  - `hasS00Timeline=true`
  - `hasFreshTimeline=true`
  - `hasComparisons=true`
  - `hasDivergenceCandidates=true`
  - `firstCandidateIsResponseHandlerDiff=true`
- `first_decisive_divergence.json`:
  - `inputDiffExists=true`
  - `hasCandidate=true`
  - `candidateKindAllowedByPlan=true`
  - `s00AndFreshRequestSeqRscEqual=true`
  - `firstDivergenceAtFinalSeq5=true`
- `pre_seq5_state_lineage_detail.json`:
  - `diffFirstCandidateFinalSeq5=true`
  - `s00RuntimeWindowHasCaptchaHead=true`
  - `s00JsWindowHasParentBridge=true`
  - `s00JsWindowHasPayloadGeneration=true`
  - `freshHasPowSolved=true`
  - `freshHasWasmNgNq=true`
  - `decodedEqualButEncodedDiffersAuditPresent=true`
  - `headTimingAlreadyNotSufficient=true`
  - `freshPowWasmTailAlreadyNotSufficient=true`
  - `parentBridgeNotCookieHeaderAuditPresent=true`
  - `readyForFreshExperiment=false`
- `accepted_line933_generation_lineage.json`:
  - `hasPx561YcLine917=true`
  - `hasCaptchaJcLine918=true`
  - `hasTfEnterLine920=true`
  - `hasTfPrepcLine921=true`
  - `hasTfPayloadLine922=true`
  - `prepcActivitiesEqualPayloadActivities=true`
  - `prepcInjectsPx3IntoEveryActivity=true`
  - `selectedFreshMaterialHasTemplateDecodedActivities=true`
  - `existingDecodedEqualityRejected=true`
  - `existingPx3StatefulRetryRejected=true`
  - `readyForFreshExperiment=false`
- `server_expected_state_pre_seq5_gap.json`:
  - `s00Line623Has18Parts=true`
  - `freshSeq4Has18Parts=true`
  - `handlerSequencesEqual=true`
  - `valueMismatchFieldsPresent=true`
  - `allMismatchFieldsAreSessionSpecific=true`
  - `existingFreshTailControlRejected=true`
  - `existingStatefulRetryRejected=true`
  - `readyForFreshExperiment=false`
- `server_state_transition_value_model.json`:
  - `hasS00Model=true`
  - `hasFreshModel=true`
  - `hasFinalS00Seq5=true`
  - `hasFinalFreshSeq5=true`
  - `finalS00Success=true`
  - `finalFreshRejected=true`
  - `readyForFreshExperiment=false`
- `request_history_coherence_gap.json`:
  - `hasS00Chronology=true`
  - `hasFreshChronology=true`
  - `s00HasMsftSeq1To3BeforeBundlePow=true`
  - `freshLacksMsftSeq1To3BeforeBundlePow=false`
  - `hasOrderGap=false`
  - `finalDivergenceStillSeq5=true`
  - `primaryHypothesisH3=true`
  - `readyForFreshExperiment=false`
- `line922_dynamic_field_source_map.json`:
  - `freshSeq5PayloadDecoded=true`
  - `freshSeq5ActivityTypesEqualS00=true`
  - `freshSeq5ChangedFieldInstances=0`
  - `readyForFreshExperiment=false`
- `encoded_payload_pc_form_diff_map.json`:
  - `decodedJsonEqual=true`
  - `decodedTextEqual=true`
  - `baseAfterMarkerRemovalEqual=true`
  - `payloadDiffers=true`
  - `markerDiffers=true`
  - `pcDiffers=true`
  - `readyForFreshExperiment=false`
- `remaining_encoder_variant_build_matrix.json`:
  - `builtAllRemainingVariants=true`
  - `allDecodeMarkerMatch=true`
  - `allDecodeJsonOk=true`
  - `allDecodedBaseEqualS00=true`
  - `variantFamilyNotSingle=true`
  - `readyForFreshExperiment=false`
- `server_observable_state_inventory.json`:
  - `hasS00ObservableMutations=true`
  - `hasFreshObservableMutations=true`
  - `hasFinalConsumedFields=true`
  - `decodedJsonEqual=true`
  - `finalConsumedFieldsAllDiffer=true`
  - `parentBridgeGapKnown=true`
  - `parentBridgeNotCookieHeader=true`
  - `readyForFreshExperiment=false`
- `bridge_to_payload_context_audit.json`:
  - `hasParentPx3BeforeLine922=true`
  - `hasParentPxdeBeforeLine922=true`
  - `parentPx3MatchesLine922Payload=true`
  - `parentPxdeMatchesLine922Payload=false`
  - `decodedPayloadAlreadyEqual=true`
  - `line933NoCookieHeader=true`
  - `freshSeq5NoCookieHeader=true`
  - `s00RiskVerifyMaterialMissing=true`
  - `readyForFreshExperiment=false`
- `s00_risk_verify_material_gap.json`:
  - `hasRiskInitialize=true`
  - `hasRiskVerify=true`
  - `hasTwoRiskVerifyRequests=true`
  - `hasCreateAccount=true`
  - `riskVerifyStateContinue=true`
  - `createAccountRedirectUrl=true`
  - `riskResponseTokenFeedsCreateAccount=true`
  - `finalRiskHasChallengeSolution=true`
  - `finalChallengePxFieldsMappedToCookieTimeline=true`
  - `finalMappedParentMessagesBeforeRiskVerify=true`
  - `challengePxEqualsRiskProviderMetadata=true`
  - `riskVerifyMaterialGenerated=true`
  - `readyForFreshExperiment=false`
- `collector_to_risk_consumption_chain.json`:
  - `hasSuccessCollectorEntry=true`
  - `successCollectorLineIs948=true`
  - `successEntryHasChallengeSuccess0=true`
  - `hasFinalRiskContinueRequest=true`
  - `finalRiskRequestLineIs998=true`
  - `hasCreateAccountRedirect=true`
  - `riskContinueTokenFeedsCreateAccount=true`
  - `riskPx3PxdeLinkedToSuccessCollectorLine=true`
  - `riskPxvidLinkedToInitialCollectorLine=true`
  - `allRiskPxFieldsDecodedValueMatch=true`
  - `allRiskPxFieldsParentValueMatch=true`
  - `allParentMessagesBeforeRiskRequest=true`
  - `line933DivergenceIsAccepted=true`
  - `readyForFreshExperiment=false`
- `single_transition_candidate_matrix.json`:
  - `collectorRiskChainInputReady=true`
  - `firstDivergenceAtFinalSeq5=true`
  - `decodedPayloadSemanticEqual=true`
  - `requestHistoryOrderGapFalsified=true`
  - `riskChainDownstreamProven=true`
  - `remainingEncoderVariantFamilyNotSingle=true`
  - `candidateCount=8`
  - `eliminatedCount=4`
  - `coupledOrNonRequestBoundaryCount=3`
  - `singleTransitionCandidateCount=0`
  - `noReadySingleTransitionCandidate=true`
  - `readyForFreshExperiment=false`
- `coupled_boundary_reduction_plan.json`:
  - `singleTransitionMatrixReady=true`
  - `hasC4=true`
  - `hasC5=true`
  - `hasC6=true`
  - `hasThreeReductionTracks=true`
  - `tracksAreOfflineOnly=true`
  - `outerTupleBoundaryPresent=true`
  - `encoderVariantFamilyPresent=true`
  - `serverExpectedStateBoundaryPresent=true`
  - `recommendedNextTrack=T1_outer_session_tuple_factorization`
  - `readyForFreshExperiment=false`
- `outer_session_tuple_factorization.json`:
  - `hasAllOuterTupleFields=true`
  - `allFieldsDiffer=true`
  - `hasBootstrapSessionGroup=true`
  - `hasSeq4ResponseGroup=true`
  - `hasDerivedSessionGroup=true`
  - `sourceGroupCount=3`
  - `singletonSourceGroupCount=1`
  - `multiFieldSourceGroupCount=2`
  - `singleReadyGroupCount=0`
  - `noSingleFieldExperimentReady=true`
  - `readyForFreshExperiment=false`
- `encoder_axis_equivalence.json`:
  - `variantCountIsFour=true`
  - `allDecodedBaseEqual=true`
  - `markerSourceValueCount=2`
  - `pcUuidSourceValueCount=2`
  - `payloadSha256ValueCount=2`
  - `pcSha256ValueCount=2`
  - `bodySha256ValueCount=4`
  - `markerSourceDeterminesPayload=true`
  - `pcUuidSourceDeterminesPc=true`
  - `remainingFamilyIsIndependent2x2=true`
  - `remainingEncoderAxisCount=2`
  - `singleEncoderAxisIsolated=false`
  - `readyForFreshExperiment=false`
- `server_expected_state_observable_proxy.json`:
  - `hasPreFinalComparisons=true`
  - `allPreFinalHandlersEqual=true`
  - `allPreFinalSuccessStatusEqual=true`
  - `allPreFinalPowPresenceEqual=true`
  - `allPreFinalPxMutationPresenceEqual=true`
  - `omittedPreAcceptTransitionCount=0`
  - `hasFinalSeq5Divergence=true`
  - `firstDivergenceAtFinalSeq5=true`
  - `downstreamRiskChainStartsAfterSuccess=true`
  - `outerTupleStillCoupled=true`
  - `encoderStillCoupled=true`
  - `singleTransitionCandidateCount=0`
  - `transitionHasReplayableClientRepresentation=false`
  - `readyForFreshExperiment=false`
- `server_internal_gap_evidence_inventory.json`:
  - `serverProxyRequiresNewEvidence=true`
  - `statusSaysNotReadyForFreshExperiment=true`
  - `runtimeTraceCount=157`
  - `jsTraceCount=36`
  - `collectorDecodeCount=17`
  - `cookieTimelineCount=11`
  - `multiSurfaceBrowserRunCount=10`
  - `directWebshareAttemptCount=30`
  - `firstFailureOverlapAttemptCount=5`
  - `seq5Seq6ComboProbeCount=38`
  - `staticJsFileCount=149`
  - `hasCandidateLocalEvidenceSources=true`
  - `recommendedNextIsOffline=true`
  - `readyForFreshExperiment=false`
- `cross_sample_server_state_proxy_matrix.json`:
  - `sampleCount=14`
  - `fullSuccessCount=4`
  - `nonFullSuccessCount=10`
  - `multiSurfaceSampleCount=10`
  - `hasAtLeastThreeFullSuccessSamples=true`
  - `hasNonFullSuccessControls=true`
  - `hasMultiSurfaceSamples=true`
  - `candidateClientVisibleProxyCount=0`
  - `outcomeOnlySeparatorCount=1`
  - `readyForFreshExperiment=false`
- `historical_probe_response_class_matrix.json`:
  - `directAttemptCount=30`
  - `firstFailureOverlapAttemptCount=5`
  - `seq5Seq6ComboProbeCount=38`
  - `px561DiffFileCount=55`
  - `allDirectReachBundlePow=true`
  - `allOverlapReachBundlePow=true`
  - `directFinalComboSuccessCount=0`
  - `overlapFinalComboSuccessCount=0`
  - `seq5Seq6ComboSuccess0Count=0`
  - `seq5Seq6ComboSeq5FailureMinus1Count=32`
  - `seq5Seq6ComboSeq6AnyOIIoIoooCount=0`
  - `hasHistoricalNoBrowserSuccess0=false`
  - `hasNearSuccessFailureMinus1Class=true`
  - `readyForFreshExperiment=false`
- `server_internal_unobserved_state_final_gap.json`:
  - `selectedContrastHasNoReplayableProxy=true`
  - `selectedContrastOmittedPreAcceptTransitionCount=0`
  - `singleTransitionCandidateCount=0`
  - `outerTupleNoSingleFieldExperimentReady=true`
  - `encoderSingleAxisNotIsolated=true`
  - `crossSampleCandidateClientVisibleProxyCount=0`
  - `crossSampleHasEnoughSamples=true`
  - `historicalProbeHasNoBrowserSuccess0=true`
  - `historicalProbeHasNearSuccessFailureMinus1=true`
  - `downstreamRiskChainProvenForAcceptedS00=true`
  - `unminedEvidenceAuditRan=true`
  - `unminedEvidenceHadSuccessSignals=true`
  - `highValueUnminedTriageRan=true`
  - `highValueUnminedReplayableSuccessNotFound=true`
  - `allLocalProxySearchesNegative=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `unmined_local_evidence_source_audit.json`:
  - `directoryCount=53`
  - `coveredDirectoryCount=13`
  - `uncoveredDirectoryCount=40`
  - `highValueUnminedDirectoryCount=34`
  - `unminedSuccessSignalFileCount=14`
  - `hasUnminedSuccessSignal=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `high_value_unmined_evidence_triage.json`:
  - `highValueUnminedDirectoryCount=34`
  - `classifiedSuccessSignalFileCount=14`
  - `replayableFreshNoBrowserSuccessEvidenceCount=0`
  - `unclassifiedSuccessSignalCount=0`
  - `dirsWithSuccessSignalCount=5`
  - `dirsWithLiveNegativeSignalsCount=8`
  - `hasReplayableFreshNoBrowserSuccessEvidence=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `pure_protocol_completion_requirements_audit.json`:
  - `requirementCount=7`
  - `provenCount=3`
  - `missingCount=2`
  - `notProvenCount=1`
  - `partiallyProvenCount=1`
  - `blockingRequirementCount=4`
  - `goalComplete=false`
  - `readyForFreshExperiment=false`
- `js_internal_event_taxonomy.json`:
  - `sampleCount=14`
  - `fullSuccessRunCount=4`
  - `nonFullSuccessRunCount=10`
  - `featureCount=371`
  - `candidateNonOutcomeClientEventCount=8`
  - `outcomeSeparatorCount=1`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `js_internal_candidate_reduction.json`:
  - `candidateCount=8`
  - `powChallengeHandlerCandidateCount=4`
  - `cookieFlagHandlerCandidateCount=3`
  - `outcomeHandlerCandidateCount=1`
  - `unclassifiedCandidateCount=0`
  - `replayableClientTransitionCandidateCount=0`
  - `historicalDirectReachBundlePow=true`
  - `historicalOverlapReachBundlePow=true`
  - `historicalSeq5FailureMinus1Count=32`
  - `historicalNoBrowserSuccess0=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`
- `actionable_frontier_audit.json`:
  - `jsonArtifactCount=37`
  - `nextArtifactRefCount=44`
  - `nextScriptRefCount=34`
  - `terminalAuthorityNextNull=true`
  - `completedFrontierRefCount=40`
  - `actionableMissingArtifactCount=0`
  - `nonterminalMissingArtifactCount=0`
  - `statusNextRecommendedArtifactIsNull=true`
  - `finalGapNextArtifactIsNull=true`
  - `requirementsNextArtifactIsNull=true`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

POW proxy 假阳性修正：

- 初版 cross-sample matrix 曾得到 `decode.preSuccessPowCount>0` 候选；
- 复核非 full_success 样本证明该候选是统计窗口错误：
  - `hcxwyrtiudbg_1780949301` decoded line 211 有 POW response；
  - `i294e72kliud_1781017380` decoded line 211 有 POW response；
  - `whsnxy8ag5ji_1781017142` decoded line 217 有 POW response；
  - `fk8zn2nqhex1_1781115338` decoded line 217 有 POW response；
  - `b0hnt0zycbpx_1781116322` decoded line 217 有 POW response；
- 根因：无 `oIIoIooo|0` success line 的样本被错误地按空 pre-success window 统计；
- 修正后无 success line 样本的全部 decoded responses 均计入 pre-accept evidence；
- 修正后 `candidateClientVisibleProxyCount=0`。

已纠正的误导证据：

- 旧版 `collector_state_transition_diff_s00_vs_fresh.json` 曾按 `seq/rsc` 对 fresh timeline 排序，错误地把 `bundle_seq0` 放到 `msft seq1-3` 之前；
- 实际 selected fresh attempt 顺序来自 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781281000000_1781279930.json`：
  - bootstrap；
  - second；
  - sequence；
  - bundle；
  - firstFailureOverlap；
  - seq4AfterOverlap；
  - finalSeq5Seq6Combo；
- 因此“fresh 缺少 msft seq1-3 before bundle POW”不是事实，不能作为实验方向。

当前 decisive divergence：

- id: `D1_final_seq5_acceptance_response_diff`
- hypothesis: `H3_collector_server_state`
- s00 request: `seq=5`, `rsc=6`, `uuid=7bbba710-65a9-11f1-bc5b-d972b0447135`, `pc=5793951654710718`, `payloadSha256=81b5774f2a12003af2cb3a4ad6e4db7638da325832979790a51f027839821338`, `bodySha256=8cb8ed1e9460ca34e31958dd691be9247f29abbc6789e6ae2e18ed77624d39ca`
- fresh request: `seq=5`, `rsc=6`, `uuid=9acd2880-6677-11f1-8a37-62666cc2b93d`, `pc=9971995578979710`, `payloadSha256=521b1f837172bd2ea5eb61d0f21760c5e5edf6c6eb798c40306399a63a1aa540`, `bodySha256=0a33c3c1e43a7cdb99b71070a3967ce66a2b31325c791596a057e99add6926d1`

当前下一步：

- 总审计已更新 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
- 该审计已纳入 `collector_to_risk_consumption_chain.json`、`single_transition_candidate_matrix.json` 与 `server_internal_gap_evidence_inventory.json`
- 因 `singleTransitionCandidateCount=0`，当前禁止进入 Phase 5 fresh-session 最小实验；
- `coupled_boundary_reduction_plan.json` 已定义 C4/C5/C6 的离线补证路径；
- `T1_outer_session_tuple_factorization` 已完成，C4 仍为耦合边界，无可实验单字段；
- `T2_encoder_axis_equivalence` 已完成，C5 仍为独立 2x2 encoder family，无单一 encoder axis；
- `T3_server_expected_state_observable_proxy` 已完成；
- 当前没有 client-observable omitted pre-accept transition：`omittedPreAcceptTransitionCount=0`；
- C4/C5/C6 均未收敛为 replayable single transition，当前仍禁止 fresh-session 实验；
- `server_internal_gap_evidence_inventory.json` 已完成，证明当前本地仍有可补证材料：
  - 157 个 runtime traces；
  - 36 个 JS internal traces；
  - 17 个 collector decode；
  - 11 个 cookie timeline；
  - 10 个 runtime/js/decode/cookie 多面重合 browser run；
  - 30 个 direct Webshare attempt；
  - 5 个 first-failure-overlap attempt；
  - 38 个 seq5/seq6 combo probe；
- `cross_sample_server_state_proxy_matrix.json` 已完成：
  - 4 个 full_success 样本；
  - 10 个 non-full-success control；
  - 10 个 runtime/js/decode/cookie 多面重合样本；
  - 没有发现“所有 full_success 存在且所有 non-full-success 缺失”的 pre-accept/client-visible proxy；
  - 唯一 outcome separator 是 `decode.hasDecodedSuccess0`，属于结果本身，不能作为 root-cause proxy；
- `historical_probe_response_class_matrix.json` 已完成：
  - 30 个 direct Webshare attempts；
  - 5 个 first-failure-overlap attempts；
  - 38 个 seq5/seq6 combo probes；
  - 55 个 PX561 diff files；
  - direct/overlap attempts 均能到达 bundle POW；
  - 历史 no-browser `oIIoIooo|0` 数量为 0；
  - seq5 `oIIoIooo|-1` 近成功失败类数量为 32；
  - seq6 没有 `oIIoIooo`；
- `server_internal_unobserved_state_final_gap.json` 已完成：
  - selected contrast 无 replayable proxy；
  - single-transition candidate 为 0；
  - cross-sample browser matrix 无 client-visible proxy；
  - historical no-browser matrix 无 `oIIoIooo|0`；
  - accepted s00 downstream risk/verify/CreateAccount 已证明；
  - unmined local evidence audit 发现仍有 34 个高价值未纳入目录和 14 个 success-signal 文件；
  - high-value unmined triage 对 14 个 success-signal 文件分类后，`replayableFreshNoBrowserSuccessEvidenceCount=0`；
  - 当前所有本地 proxy search 均为 negative；
- 当前推荐下一产物：无；
- 当前推荐下一脚本：无；
- 当前缺口已收敛为 `collector server-internal or unobserved expected state`，状态是 `not_reduced_to_replayable_client_transition`；
- `pure_protocol_completion_requirements_audit.json` 已完成逐条完成审计：
  - R1 fresh pure-protocol collector HUMAN success: `missing`；
  - R2 fresh collector response decodes success: `missing`；
  - R3 decoded response updates `_px` jar: `proven`；
  - R4 risk/verify returns continue with jar: `proven`，但 scope 是 accepted s00/downstream material；
  - R5 CreateAccount redirectUrl: `proven`，但 scope 是 accepted s00/downstream material；
  - R6 full flow no browser/Camoufox/mouse/vision/external captcha: `not_proven`；
  - R7 every step has local evidence paths and commands: `partially_proven`；
  - blocking requirements: 4；
- `js_internal_event_taxonomy.json` 已完成：
  - 初步找到 8 个 apparent non-outcome JS separators；
  - 候选包括 `IooIIo/IooIoI/oIIooIoo` POW handler、`fp/rf/nf` cookie/config flags、`oIIoIooo` handler key；
- `js_internal_candidate_reduction.json` 已完成：
  - 4 个候选归为 POW challenge handler；
  - 3 个候选归为 collector cookie/config flag；
  - 1 个候选归为 outcome handler；
  - historical no-browser 已反复到达 bundle POW 且仍有 32 个 seq5 `oIIoIooo|-1`；
  - `replayableClientTransitionCandidateCount=0`；
- `actionable_frontier_audit.json` 已完成：
  - 扫描所有 hypothesis reframe JSON 中的 `nextArtifact/nextScript`；
  - 旧链路 nextArtifact 均已存在或已被 terminal authority 覆盖；
  - terminal authority artifacts：`hypothesis_reframe_status.json`、`server_internal_unobserved_state_final_gap.json`、`pure_protocol_completion_requirements_audit.json`；
  - terminal authority next steps 均为 null；
  - `actionableMissingArtifactCount=0`；
- 当前仍不允许 fresh-session 网络实验。

## 禁止事项

- 禁止继续随机组合 payload/pc/body/outer fields；
- 禁止把 s00 accepted packet 当作可移植模板；
- 禁止把 decoded activity equality 写成充分条件；
- 禁止在没有 divergence 的情况下跑新 session 实验；
- 禁止用“可能”“感觉”“大概率”作为结论；
- 禁止用静态 JS 注释覆盖 runtime/network 证据；
- 禁止为了得到短期阶段推进而改变最终目标。

## 完成标准

此计划本身完成不代表最终目标完成。

最终目标只有在以下证据全部成立时才算完成：

1. pure protocol fresh session 产生 collector HUMAN success；
2. collector response 离线解码包含成功状态；
3. decoded response handler 可离线更新 `_px` cookie/token jar；
4. risk/verify 使用该 jar 返回 `state=continue`；
5. CreateAccount 返回 `redirectUrl`；
6. 全流程不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码；
7. 每一步都有本地证据路径和可复现命令。

## 2026-06-13 重置执行入口

本 hypothesis plan 的本地证据链已经证明旧 `nextArtifact` 路线没有剩余可执行 frontier：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/hypothesis_reframe_status.json`
  - `readyForFreshExperiment=false`
  - `actionableFrontierNotFound=true`
  - `jsInternalReplayableTransitionNotFound=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_internal_unobserved_state_final_gap.json`
  - `singleTransitionCandidateCount=0`
  - `allLocalProxySearchesNegative=true`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/actionable_frontier_audit.json`
  - `actionableMissingArtifactCount=0`
  - `terminalAuthorityNextNull=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - `blockingOrMissing=["end_to_end_pure_protocol_poc"]`

因此后续仍服务于本计划的最终目标，但执行入口切换到新的证据重置计划：

- 计划文档：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reset-execution-plan.md`
- 当前产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_manifest.json`
- 当前脚本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_sampling_manifest.py`

`reset_sampling_manifest.json` 当前决策：

- `readyForControlledSampling=true`
- `readyForFreshExperiment=false`
- 下一产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`
- 下一脚本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_sampling_matrix.py`

后续只允许先执行受控采样矩阵，把 IP/Webshare/direct 作为受控变量采证；在新的 `singleTransitionCandidateCount=1` 且 `readyForFreshExperiment=true` 之前，仍禁止字段组合式 fresh-session 实验。

## 2026-06-13 reset 采样与 Webshare 认证缺口更新

已按 reset 入口生成并执行受控采样矩阵：

- 矩阵产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`
- 状态机产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`
- Webshare 认证缺口审计：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/webshare_proxy_auth_gap_audit.json`

当前事实：

- `pure_protocol_webshare` reset 样本数为 3；
- 3/3 Webshare reset 样本均未到达 collector bootstrap；
- 3/3 Webshare reset 样本的 bootstrap artifact 记录 `Tunnel connection failed: 407 Proxy Authentication Required`；
- 因此这些 Webshare 样本不能支持“IP 导致 HUMAN 成败”的结论；
- `pure_protocol_direct` reset 样本数为 2；
- 2/2 direct 样本均到达 final seq5/seq6；
- 2/2 direct 样本 `comboAnySuccess=false`；
- `reset_state_machine.json` 当前 `clientVisibleProxyCount=0`、`readyForFreshExperiment=false`、`goalComplete=false`。

后续修正：

- Webshare 407 的直接原因已定位为 reset runner 使用了错误 username/session 形状：`reset-webshare-*`；
- 历史可用 Webshare 样本使用 `ibtvqcnm-JP-<numeric-session>`；
- 已修复 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_sampling_matrix.py`，保持 Webshare username 形状；
- 已重新采集 3 个有效 Webshare reset 样本：
  - `ibtvqcnm-JP-1781291401000`
  - `ibtvqcnm-JP-1781291401001`
  - `ibtvqcnm-JP-1781291401002`
- 3/3 有效 Webshare reset 样本均到达 final seq5/seq6；
- 3/3 有效 Webshare reset 样本 `comboAnySuccess=false`；
- 2/2 direct reset 样本也到达 final seq5/seq6 且 `comboAnySuccess=false`；
- `reset_state_machine.json` 当前：
  - `pureWebshareFinalNoSuccessCount=3`
  - `pureWebshareProxyAuth407Count=3`，仅代表旧 malformed reset rows；
  - `pureDirectFinalNoSuccessCount=2`
  - `clientVisibleProxyCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

因此“Webshare/IP 本身足以让 pure protocol 成功”在当前 reset 样本中没有证据支持；有效 Webshare 和 direct 都能到达 final seq5/seq6，但均未产生 collector success。

已新增 transport/IP 假设审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_transport_ip_hypothesis_audit.json`
- checks:
  - `validPureProtocolSampleCount=5`
  - `validWebshareSampleCount=3`
  - `validDirectSampleCount=2`
  - `allValidSamplesReachedFinalSeq5Seq6=true`
  - `anyCollectorSuccess=false`
  - `transportIpAloneSupported=false`
  - `readyForFreshExperiment=false`

该结论已同步到总目标审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
- 当前仍只有 `end_to_end_pure_protocol_poc` 阻塞；
- `goalComplete=false`。

已新增 reset final response class 审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_final_response_class_audit.json`
- checks:
  - `sampleCount=5`
  - `webshareSampleCount=3`
  - `directSampleCount=2`
  - `allSeq5Http200=true`
  - `allSeq6Http200=true`
  - `allFinalResponsesSameClass=true`
  - `allFinalResponsesAreSeq5Minus1=true`
  - `anySeq5Success0=false`
  - `allFinalResponsesHavePx3PxdeHandlers=true`
  - `stageProgressionFound=false`

因此 5 个有效 reset pure-protocol 样本不是分散失败类；它们全部稳定落在同一 final response class：seq5 返回 `oIIoIooo|-1`，同时有 `_px3/_pxde` 更新，seq6 没有 outcome handler。该审计没有暴露新的 single transition candidate。

已新增 reset cookie mutation 审计：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_cookie_mutation_audit.json`
- 使用 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/replay_human_collector_state.py` 中已证据化的 handler 映射离线重放 5 个有效 reset final response；
- checks:
  - `sampleCount=5`
  - `webshareSampleCount=3`
  - `directSampleCount=2`
  - `allSeq5HasPx3Pxde=true`
  - `allSeq6HasPx3Pxde=true`
  - `allOfflineJarHasPx3Pxde=true`
  - `allFinalJarUsesSeq6Values=true`
  - `anyFinalJarStillUsesSeq5Values=false`
  - `anyFinalResponseHasPxvid=false`
  - `anySuccess0=false`
  - `allHaveFailureMinus1=true`
  - `riskVerifyCandidateComplete=false`
  - `readyForRiskVerifyReplay=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

结论：这些 final failure response 的 decoded handler 确实足以离线更新 `_px3/_pxde`，并且 seq6 会覆盖 seq5 的 cookie 值；但同一证据也证明没有 `oIIoIooo|0`，final response 中也没有 `_pxvid` handler，因此不能把这组 failure jar 当成完整 risk/verify success-cookie 候选。

已新增 reset single-transition candidate 审计，补齐 reset plan Phase 4 门控产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_single_transition_candidates.json`
- 输入：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_final_response_class_audit.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_cookie_mutation_audit.json`
- checks:
  - `stateMachineClientVisibleProxyCount=0`
  - `candidateClientVisibleProxyCount=0`
  - `outcomeOnlyCandidateCount=1`
  - `singleTransitionCandidateCount=0`
  - `allFinalResponsesSameClass=true`
  - `allFinalResponsesAreSeq5Minus1=true`
  - `anySeq5Success0=false`
  - `allOfflineJarHasPx3Pxde=true`
  - `riskVerifyCandidateComplete=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

因此 reset plan Phase 4 的当前结论是：没有一个可重放、client-visible、可由纯协议构造的单变量 transition；Phase 5 fresh-session 最小实验不被当前证据授权。后续不能继续随机 fresh 网络试错，除非新增采样或新增 hook 证据能把 `singleTransitionCandidateCount` 提升到 1 且 `readyForFreshExperiment=true`。

已新增 reset sampling coverage 审计，检查 Phase 2 采样是否足以支撑 Phase 4 的 no-candidate 结论：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_coverage_audit.json`
- 输入：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_manifest.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_single_transition_candidates.json`
- checks:
  - `manifestReadyForControlledSampling=true`
  - `matrixResetSamplingComplete=false`
  - `matrixPureProtocolResetSamplingComplete=true`
  - `matrixBrowserRunnerMissing=true`
  - `browserResetCoverageComplete=false`
  - `pureProtocolResetCoverageComplete=true`
  - `allResetCoverageComplete=false`
  - `stateMachineClientVisibleProxyCount=0`
  - `singleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

该审计改变后续执行入口：Phase 4 当前确实没有单变量候选，但这个 no-candidate 结论不能被视为 reset 采样完整后的最终结论，因为 reset plan 要求新采 `browser_success_webshare` 和 `browser_failure_webshare`，而当前 matrix 只使用旧 classifier baseline，且 `browserRunnerMissing=true`。下一产物应是：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_runner_plan.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_browser_sampling_runner_plan.py`

目标是先定义浏览器 Webshare reset 采样 instrumentation，补齐成功/失败各 2 个 fresh reset 样本所需的 proxy/IP/session、runtime hook、network trace、cookie timeline、risk/verify/CreateAccount 证据字段；不是继续 pure-protocol 字段突变。

已新增 reset browser sampling runner plan：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_runner_plan.json`
- 脚本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_browser_sampling_runner_plan.py`
- 输入：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_coverage_audit.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/human_trace_classifier_v2.py`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/pipeline.py`
- checks:
  - `coverageSaysBrowserResetIncomplete=true`
  - `coverageSaysPureProtocolResetComplete=true`
  - `requiredBrowserSuccessGap=2`
  - `requiredBrowserFailureGap=2`
  - `outlookBrowserRegisterExists=true`
  - `hasRuntimeTraceInstaller=true`
  - `hasJsInternalTraceInstaller=true`
  - `hasCookieBridgeArtifact=true`
  - `hasIpifyEvidence=true`
  - `classifierExists=true`
  - `readyToImplementRunner=true`
  - `readyToExecuteBrowserSampling=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

该 plan 明确：现有 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py` 已具备 runtime trace、JS internal trace、PX cookie bridge artifact、IP evidence 的 instrumentation primitives；浏览器样本只作为 reset Phase 2 成功/失败对照证据，不能计入最终 no-browser PoC。下一步不是执行浏览器，而是实现：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_browser_webshare_sampling.py`
- 输出目录：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts`

该 runner 必须每次使用新的 Webshare session，记录 `proxyEndpoint/proxySessionUser/exitIp`，并把 runtime trace、JS trace、cookie timeline、collector decode、risk/verify、CreateAccount 和最终分类写成 reset attempt summary，然后再回灌 `reset_sampling_matrix.json`。

已实现 reset browser Webshare sampling runner 骨架与自检审计：

- runner：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_browser_webshare_sampling.py`
- 自检审计脚本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_browser_sampling_runner_audit.py`
- 自检审计产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_runner_audit.json`
- dry-run 产物目录：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts`
- 已执行 dry-run：
  - `browser_success_webshare` 1 条；
  - `browser_failure_webshare` 1 条；
  - 均未执行浏览器/网络，只验证输出 schema。
- checks:
  - `runnerPlanExists=true`
  - `runnerExists=true`
  - `attemptDirExists=true`
  - `dryRunAttemptCount=2`
  - `executedAttemptCount=0`
  - `countedResetAttemptCount=0`
  - `countedBrowserSuccessResetCount=0`
  - `countedBrowserFailureResetCount=0`
  - `allAttemptsFreshSession=true`
  - `noAttemptCountsTowardFinalPureProtocolSuccess=true`
  - `readyToExecuteBrowserSampling=true`
  - `browserResetCoverageComplete=false`
  - `readyForFreshExperiment=false`
  - `goalComplete=false`

因此当前新状态是：runner 已可执行，dry-run schema 已验证；但没有任何 executed browser reset sample 被计入覆盖。后续若执行浏览器采样，必须显式使用 `--execute`，且每次 fresh Webshare session；执行后还必须重新运行 coverage/state-machine/single-candidate/goal audits，不能直接进入 Phase 5。

已增强 browser sampling runner 的 Webshare session 控制证据：

- runner 现在会为每个 attempt 复制 `CTF-reg/config.paypal-proxy.json` 到临时配置：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/configs/cardw_<session>.json`
- 临时配置写入：
  - 顶层 `proxy=http://<session>:<password>@p.webshare.io:80`
  - `proxy_meta.source=reset_browser_webshare_sampling`
  - `proxy_meta.sessionUser=<session>`
  - `proxy_meta.freshSession=true`
- attempt summary 记录：
  - `configEvidence.sourceConfig`
  - `configEvidence.sourceConfigSha256`
  - `configEvidence.attemptConfig`
  - `configEvidence.attemptConfigSha256`
  - redacted proxy
  - command 中的 `--cardw-config <attemptConfig>`
- 最新自检 checks：
  - `attemptWithConfigCount=1`
  - `attemptMissingConfigCount=2`，代表旧 dry-run 产物来自 runner 增强前；
  - `allNewAttemptsHaveConfigWritten=true`
  - `allNewCommandsUseAttemptConfig=true`
  - `allNewConfigsProxyHasSession=true`
  - `allNewConfigProxyMetaSessionMatches=true`
  - `executedAttemptCount=0`
  - `countedResetAttemptCount=0`

因此现在有文件级证据证明：后续使用 `--execute` 时，pipeline 会读取每个 attempt 的临时 cardw config，并实际使用该 attempt 专属 Webshare session；但当前仍未执行浏览器采样，reset browser coverage 仍未完成。

已更新 reset sampling matrix，使其能回灌 browser sampling runner 的 attempt summary：

- 脚本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_sampling_matrix.py`
- 现在 `plannedRows` 中 `browser_success_webshare` / `browser_failure_webshare` 不再是 missing runner capability，而是指向：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_browser_webshare_sampling.py`
- matrix 会读取：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_*.json`
- dry-run browser attempts 会进入 `executedRows` 作为审计证据，但 `countsTowardResetMinimum=false`；
- 只有 `--execute` 产生且 `classificationMatchesSampleClass=true` 的 browser attempt 才能计入 reset minimum。

重新生成后的 matrix checks：

- `browserRunnerMissing=false`
- `browserRunnerAttemptCount=3`
- `browserRunnerExecutedCount=0`
- `resetSamplingComplete=false`
- `pureProtocolResetSamplingComplete=true`
- `readyForStateMachine=false`
- `readyForFreshExperiment=false`

重新生成后的 coverage audit 已修正 next step：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_coverage_audit.json`
- `matrixBrowserRunnerMissing=false`
- `browserResetCoverageComplete=false`
- `recommendedExperiment.kind=browser_reset_sampling_execution`
- `nextScript=/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_browser_webshare_sampling.py`
- reason：pure-protocol reset coverage 已完成，browser runner 已存在，但仍没有 executed browser Webshare success/failure samples 计入 reset minimum。

已修正 browser reset sampling 的 runtime trace 分类死角：

- 修正脚本：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_browser_webshare_sampling.py`
- 新增回灌脚本：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/reclassify_reset_browser_sampling_attempts.py`
- 回灌审计：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_reclassification_audit.json`
- 被修正的 attempt：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_success_webshare_ibtvqcnm-JP-1781293311485_1781293311.json`
- runtime trace 证据：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sroj38wglken_1781293321.jsonl`
  - line 567: `handlerKey=oIIoIooo`, `args=["0"]`
  - line 568: captcha state `succeeded`, `zero=true`
  - line 580: risk/verify request includes Human `px3/pxde/pxvid`
  - line 581: risk/verify response body has `state=continue`
  - line 582: CreateAccount request
  - line 583: CreateAccount response body has `redirectUrl`

分类器错误原因已定位：runtime trace 是 JSONL，console text 内部 JSON 被反斜杠转义；旧分类器按未转义字面量搜索 `["0"]` / `"state":"succeeded"`，导致已成功的 browser attempt 被错误归为 `browser_completed_no_redirect_classified`。新分类器会扫描反转义视图，并要求三类证据同时成立：

1. collector success：`oIIoIooo` + `0` 或 captcha `state=succeeded, zero=true`；
2. risk/verify success：response `state=continue`；
3. CreateAccount success：response `redirectUrl`。

最新回灌结果：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_reclassification_audit.json`
  - `executedAttemptCount=2`
  - `successLikeCount=1`
  - `failureLikeCount=1`
  - `countedResetAttemptCount=2`
  - `goalComplete=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_runner_audit.json`
  - `countedBrowserSuccessResetCount=1`
  - `countedBrowserFailureResetCount=1`
  - `browserResetCoverageComplete=false`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`
  - `browserRunnerExecutedCount=2`
  - `pureProtocolResetSamplingComplete=true`
  - `resetSamplingComplete=false`
  - `readyForStateMachine=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_coverage_audit.json`
  - `browserResetCoverageComplete=false`
  - `pureProtocolResetCoverageComplete=true`
  - `allResetCoverageComplete=false`
  - recommended next experiment: `browser_reset_sampling_execution`
  - required gaps: `browser_success_webshare=2`, `browser_failure_webshare=2`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_single_transition_candidates.json`
  - `singleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - blocking remains `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

结论：browser reset baseline 已有 1 success / 1 failure fresh executed Webshare session，但 reset coverage 要求仍未满足；下一步只能继续执行 browser reset sampling，各补 1 条 success/failure fresh session，然后重跑 matrix、coverage、state-machine、single-candidate、goal audit。该步骤仍只是建立对照证据，不能计入最终 pure-protocol success。

已补齐 reset browser sampling coverage，并修正两个审计一致性问题：

- runner 修正：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_browser_webshare_sampling.py`
  - `browser_success_webshare` 使用 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`
  - `browser_failure_webshare` 使用 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=0`
  - 证据原因：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py` line 1615-1623 表明 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY` 控制是否把 patched hsprotect JS 应用到浏览器响应；failure 类不能开启 apply，否则只是标签失败、runtime 实际成功。
- matrix 修正：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/run_reset_sampling_matrix.py`
  - 当前 attempt summary 优先于旧 `executedRows`，避免旧分类覆盖重分类结果。
- coverage 修正：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_reset_sampling_coverage_audit.py`
  - browser rows 按 `countsTowardResetMinimum=true` 计入 reset minimum，不再强制 browser counted=0。

新增/确认的 fresh browser samples：

- success counted:
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_success_webshare_ibtvqcnm-JP-1781293311485_1781293311.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_success_webshare_ibtvqcnm-JP-1781293916986_1781293916.json`
- failure counted:
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_failure_webshare_ibtvqcnm-JP-1781293465580_1781293465.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_failure_webshare_ibtvqcnm-JP-1781294520219_1781294520.json`
- failure-labeled but runtime-success, not counted:
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_failure_webshare_ibtvqcnm-JP-1781294082027_1781294082.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/browser_sampling_attempts/browser_sampling_browser_failure_webshare_ibtvqcnm-JP-1781294243472_1781294243.json`

最新审计状态：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_reclassification_audit.json`
  - `executedAttemptCount=6`
  - `successLikeCount=4`
  - `failureLikeCount=2`
  - `countedResetAttemptCount=4`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_browser_sampling_runner_audit.json`
  - `countedBrowserSuccessResetCount=2`
  - `countedBrowserFailureResetCount=2`
  - `browserResetCoverageComplete=true`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_matrix.json`
  - `resetSamplingComplete=true`
  - `pureProtocolResetSamplingComplete=true`
  - `readyForStateMachine=true`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_sampling_coverage_audit.json`
  - `browserResetCoverageComplete=true`
  - `pureProtocolResetCoverageComplete=true`
  - `allResetCoverageComplete=true`
  - recommended next experiment: `new_hook_or_sampling_axis`
  - reason: sampling coverage complete, but no client-visible transition candidate exists.
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_state_machine.json`
  - `clientVisibleProxyCount=0`
  - `readyForSingleTransitionReduction=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/reset_plan/reset_single_transition_candidates.json`
  - `singleTransitionCandidateCount=0`
  - `readyForFreshExperiment=false`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
  - blocking remains `end_to_end_pure_protocol_poc`
  - `goalComplete=false`

当前决策：不要进入 Phase 5 fresh pure-protocol experiment；不要继续盲目补 browser 样本。下一步按 reset plan 的方法论新增 hook 或采样轴，目标是让 Phase 4 暴露至少一个 client-visible、constructible、single transition candidate；否则最终纯协议成功 PoC 仍没有可执行入口。
