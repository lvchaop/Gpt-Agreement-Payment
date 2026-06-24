# 纯协议 HUMAN 成功复现：重新定界执行计划

日期：2026-06-13

## 0. 最终目标不变

最终目标仍然是证明并实现一条可复现的纯协议链路：

1. 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
2. 仅使用 HTTP / JS 解析 / 加密 / 请求重放；
3. 从 Outlook signup 初始状态推进到 HUMAN collector 成功事件；
4. Microsoft `/API/Proofs/risk/verify` 返回 `state=continue`；
5. `/API/CreateAccount` 返回 `redirectUrl`；
6. 每一步都有本地证据路径和可复现命令。

本计划只重定界执行方法，不改变最终目标。

## 1. 本轮重规划原因

旧路线已经被本地证据证明存在惯性偏差：它持续围绕 `s00` accepted line933 包做字段移植、payload/pc/body 组合、HTTP/2/时序重排，但这些方向没有产生阶段推进。

已存在的反证：

- exact whole body replay 不成功；
- exact payload + pc 放入 fresh outer session 返回 `{do:[]}`；
- decoded activity equality 仍不成功；
- h2 single TLS session / stream 1/3 不充分；
- seq6 response before seq5 completion 不充分；
- first-failure overlap 与 forced first-failure response order 不充分；
- fresh POW/WASM tail、inner uuid、stack、AEAx、TBR9、Bzt 等字段控制不充分。

因此后续禁止继续做随机字段组合，改为按“证据定界 -> 假设证伪 -> 单一决策门 -> 最小实验”的方法推进。

## 2. 方法论

### 2.1 证据优先级

所有结论按以下优先级裁决：

1. live runtime 行为；
2. network trace / HAR；
3. runtime hook；
4. decoded collector response；
5. cookie / storage timeline；
6. 静态 JS；
7. 推断。

低优先级证据不能覆盖高优先级证据。缺少证据时只能记录为缺口，不能写成结论。

### 2.2 执行规则

1. 每次只验证一个可证伪假设。
2. 不进入 fresh-session 网络实验，除非已有一个单一、可操作、可观测的 state transition。
3. 负控只保留能改变决策的结果，不再堆叠排列组合。
4. `decoded activity equality` 只能作为边界证据，不能作为成功充分条件。
5. `s00` accepted packet 不能再被当作可跨 session 移植模板。
6. 如果发现脚本或 artifact 构造逻辑误导结论，先修 artifact，再重跑下游，不继续沿旧结论推进。
7. 每个产物必须包含 `checks`、`decision.readyForFreshExperiment`、`decision.nextArtifact` 或 `decision.recommendedExperiment`。

### 2.3 决策门模型

每一阶段只能输出三类结论之一：

- `readyForFreshExperiment=true`：已经收敛到单一 state transition，可以跑一个 fresh-session 最小实验；
- `readyForFreshExperiment=false` 且 `nextArtifact` 存在：继续补静态或离线证据；
- `blockedByMissingEvidence=true`：缺少可定位证据，先补采集或补 trace，不做推断实验。

## 3. 当前已确认事实

### 3.1 固定对照组

当前固定 success sample：

- `s00ld1lglrw0_1781191381`

当前 selected fresh failed sample 来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/first_failure_overlap_attempt/first_failure_overlap_attempt_ibtvqcnm-JP-1781281000000_1781279930.json`

对照组选择产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/selected_contrast_pair.json`

### 3.2 已纠正的误导证据

旧版状态转移 diff 曾按 `seq/rsc` 对 fresh timeline 排序，导致错误结论：fresh 在 bundle POW 前缺少 Microsoft `seq1-3`。

已纠正产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/request_history_coherence_gap.json`

确认 checks：

- `s00HasMsftSeq1To3BeforeBundlePow=true`
- `freshLacksMsftSeq1To3BeforeBundlePow=false`
- `hasOrderGap=false`
- `readyForFreshExperiment=false`

结论：

- “fresh 缺少 msft seq1-3 before bundle POW”不是事实；
- 不能把请求顺序作为下一 fresh-session 实验方向。

### 3.3 当前 decisive divergence

当前第一个 decisive divergence 仍是 final seq5 acceptance response diff：

- 产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/first_decisive_divergence.json`
- id: `D1_final_seq5_acceptance_response_diff`
- hypothesis: `H3_collector_server_state`
- s00 与 fresh 都是 `seq=5`、`rsc=6`
- s00 accepted，fresh rejected
- check: `firstDivergenceAtFinalSeq5=true`

结论：

- divergence 位于 final seq5 响应；
- 但“final seq5 响应不同”本身不是实验方案；
- 后续必须继续向前追 request generation、server observable state、Microsoft/risk context。

### 3.4 decoded payload 边界已经收缩

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/line922_dynamic_field_source_map.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/encoded_payload_pc_form_diff_map.json`

关键 checks：

- `freshSeq5PayloadDecoded=true`
- `freshSeq5ActivityTypesEqualS00=true`
- `freshSeq5ChangedFieldInstances=0`
- `decodedJsonEqual=true`
- `decodedTextEqual=true`
- `baseAfterMarkerRemovalEqual=true`
- `payloadDiffers=true`
- `markerDiffers=true`
- `pcDiffers=true`

结论：

- decoded semantic payload 已经相等；
- payload 差异主要剩 marker/uuid insertion、pc、outer form/session；
- 继续改 decoded activity 字段没有证据价值。

### 3.5 encoder 变体不是单一实验

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/remaining_encoder_variant_build_matrix.json`

关键 checks：

- `builtAllRemainingVariants=true`
- `allDecodeMarkerMatch=true`
- `allDecodeJsonOk=true`
- `allDecodedBaseEqualS00=true`
- `variantFamilyNotSingle=true`
- `readyForFreshExperiment=false`

结论：

- 剩余 encoder 变体是一组 coupled encoder/session family；
- 任取一个去跑网络实验属于任意试错；
- 不能进入 fresh-session。

### 3.6 bridge 到 payload 的当前边界

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/server_observable_state_inventory.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json`

关键 checks：

- `hasParentPx3BeforeLine922=true`
- `hasParentPxdeBeforeLine922=true`
- `parentPx3MatchesLine922Payload=true`
- `parentPxdeMatchesLine922Payload=false`
- `decodedPayloadAlreadyEqual=true`
- `line933NoCookieHeader=true`
- `freshSeq5NoCookieHeader=true`
- `s00RiskVerifyMaterialMissing=true`
- `readyForFreshExperiment=false`

结论：

- parent bridge `_px3` 已证明进入 line921/922 payload activities；
- 但 decoded payload equality 已经复现该语义字段，仍失败；
- `_pxde` 未映射到 line922 payload fields；
- line933/fresh seq5 请求本身没有 Cookie header；
- 下一个缺口是 `s00` risk/verify material，不是继续 payload 字段试错。

## 4. 新假设树

### H0: accepted packet 不可跨 session 移植

状态：强支持。

证据：

- exact whole body replay 不成功；
- exact payload+pc fresh outer 不成功；
- decoded activity equality 不成功。

后续动作：

- 不再作为主线；
- 只作为边界约束使用。

### H1: final seq5 body 可见字段决定 acceptance

状态：弱。

证据：

- decoded JSON/text 相等仍失败；
- payload/base semantic 相等仍失败；
- 单字段和多字段负控未推进。

后续动作：

- 暂停 body-field 单变量试错；
- 只有发现新的 server-consumed body field 且能定位到单一 transition 时才恢复。

### H2: transport / IP / HTTP2 / response order 决定 acceptance

状态：低优先级。

证据：

- h2 / stream / response-order / first-failure overlap 均未充分；
- request-history order gap 已被纠正为 false。

后续动作：

- 不再做 transport 排列组合；
- 只有当 body/state/context 全部闭合且唯一差异剩 transport 时才恢复。

### H3: collector server-side session state 决定 acceptance

状态：仍是高优先级，但需要重新定界。

证据：

- first divergence 在 final seq5 response；
- decoded payload equality 不充分；
- final consumed outer/session fields 全部不同；
- encoder/session family 仍 coupled。

后续动作：

- 继续追 server observable state；
- 不直接跑 fresh 网络实验；
- 下一步先补 `s00` risk/verify material，判断 final seq5 acceptance 是否与后续 Microsoft risk state/context 形成可观测闭环。

### H4: browser-only runtime state 参与生成或 server 判定

状态：中高优先级。

证据：

- line921/922 payload generation 存在 parent bridge 输入；
- `_px3` 已进入 payload，但 semantic equality 仍失败；
- 仍存在 browser/Microsoft context 未映射到 request 的可能边界。

后续动作：

- 只追能进入 request、risk verify、Microsoft context 或 server state 的 browser-only mutation；
- 不追无法被消费的 DOM/视觉字段。

### H5: Microsoft risk/create-account context binding

状态：升为当前下一主线。

证据：

- `bridge_to_payload_context_audit.json` 明确 `s00RiskVerifyMaterialMissing=true`；
- s00 runtime trace 中已存在 `risk/initialize`、`risk/verify`、`CreateAccount` 事件，但尚未结构化进入当前 hypothesis reframe artifact；
- final 目标要求 risk/verify `state=continue` 与 CreateAccount `redirectUrl`。

后续动作：

- 先提取 s00 risk/verify 与 CreateAccount material；
- 对齐 collector accepted line933 之后的 Microsoft risk 状态；
- 判断是否存在可反推到 final seq5 前的 context/state binding。

## 5. 新执行阶段

### Phase A: 计划冻结与证据基线

目的：

- 固定本计划为后续执行入口；
- 明确旧计划中哪些结论保留、哪些方向停止。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reframed-execution-plan.md`

完成条件：

- 文档包含最终目标、方法论、当前事实、假设树、阶段顺序、禁止事项、完成标准。

### Phase B: 补齐 s00 risk/verify material

目的：

- 消除 `bridge_to_payload_context_audit.json` 中的 `s00RiskVerifyMaterialMissing=true`；
- 把 accepted collector line933 之后的 Microsoft risk/verify 与 CreateAccount 结果结构化；
- 判断 HUMAN collector acceptance 是否已经在 s00 中转化为 Microsoft 可消费 risk state。

输入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_s00ld1lglrw0_1781191381.jsonl`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/cookie_timeline/cookie_timeline_s00ld1lglrw0_1781191381.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_s00ld1lglrw0_1781191381.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/bridge_to_payload_context_audit.json`

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_s00_risk_verify_material_gap.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/s00_risk_verify_material_gap.json`

必须输出：

- s00 runtime 是否存在 `risk/initialize`；
- s00 runtime 是否存在 `risk/verify`；
- s00 runtime 是否存在 `CreateAccount`；
- risk/verify request/response line；
- CreateAccount request/response line；
- risk/verify response 是否为 `state=continue`；
- CreateAccount response 是否包含 `redirectUrl`；
- risk/verify request 中是否包含 `_px3/_pxde/_pxvid`、`challengeSolution`、`riskProviderMetadata` 或等价字段；
- 这些字段是否可追溯到 cookie timeline / parent bridge / collector response；
- 如果无法追溯，必须记录缺口字段和原因。

决策门：

- 如果 `riskVerifyStateContinue=true` 且 `createAccountRedirectUrl=true`，进入 Phase C；
- 如果 runtime 中没有可解析 risk/verify 或 CreateAccount，先补 trace，不做推断；
- 如果 risk/verify material 与 collector accepted state 无关联证据，H5 降级，回到 H3/H4 server observable state。

### Phase C: 建立 collector accepted -> risk/verify 的消费链

目的：

- 判断 accepted line933 的结果如何被 Microsoft risk/verify 消费；
- 定位 collector success 与 Microsoft continuation token / risk metadata / cookie jar 之间的映射。

输入：

- `s00_risk_verify_material_gap.json`
- `bridge_to_payload_context_audit.json`
- `server_observable_state_inventory.json`
- `accepted_line933_generation_lineage.json`
- `collector_state_transition_diff_s00_vs_fresh.json`

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_to_risk_consumption_chain.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_to_risk_consumption_chain.json`

必须输出：

- line933 response handler 是否产生后续 risk/verify 可见输入；
- `_px3/_pxde/_pxvid` 是否被 risk/verify request 消费；
- continuation token / riskProviderMetadata / challengeSolution 与 collector cookie/response 的字段映射；
- accepted collector response 到 risk/verify request 的时间线；
- fresh failed sample 在相同位置缺少什么；
- 是否存在单一可操作 state transition。

决策门：

- 如果能定位单一缺失 state transition，进入 Phase E 最小 fresh 实验；
- 如果消费链闭合但缺失点仍是 encoder/session family，进入 Phase D；
- 如果消费链与 HUMAN acceptance 无关，H5 降级，回到 H3/H4。

### Phase D: 重新压缩 server observable state

目的：

- 在风险链无法直接给出单变量时，继续把 coupled outer/session/encoder tuple 拆成服务端可观测边界；
- 不跑任意 encoder 变体网络实验。

输入：

- `server_observable_state_inventory.json`
- `encoded_payload_pc_form_diff_map.json`
- `server_state_value_to_request_lineage.json`
- `remaining_encoder_variant_build_matrix.json`
- `collector_to_risk_consumption_chain.json`

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_single_transition_candidate_matrix.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/single_transition_candidate_matrix.json`

必须输出：

- 每个候选 transition 的来源证据；
- 进入 request 的具体字段；
- 服务端可观测性；
- 已有负控；
- 可证伪实验；
- 是否单一变量；
- 是否有阶段推进指标。

决策门：

- 只有存在 `singleTransitionCandidateCount=1` 且 `readyForFreshExperiment=true` 时进入 Phase E；
- 否则继续补离线证据或明确 blocked。

### Phase E: 一个 fresh-session 最小实验

目的：

- 只验证 Phase C 或 Phase D 输出的一个 single transition；
- 不做随机组合；
- 每次新尝试使用新 session。

规则：

- 使用 fresh Webshare session；
- 每一次新尝试必须更换 session；
- 只修改一个 state transition；
- 不启动浏览器/Camoufox；
- 不调用 captcha provider；
- 不使用真实鼠标/视觉；
- 不移植完整 s00 accepted packet；
- 不同时修改 payload、pc、outer form、timing、HTTP2、risk metadata。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/minimal_single_transition_experiment_audit.json`

必须输出：

- tested hypothesis；
- tested transition；
- fresh session id；
- 代理/IP/session 证据；
- request material；
- response raw + decoded；
- cookie/token mutation；
- risk/verify 是否推进；
- stage before / after；
- 是否阶段推进；
- 下一步决策。

阶段推进定义：

- `oIIoIooo|-1` -> `{do:[]}`；
- `{do:[]}` -> cookie/token handler；
- cookie/token handler -> `oIIoIooo|0`；
- `oIIoIooo|0` -> risk/verify `state=continue`；
- risk/verify `state=continue` -> CreateAccount `redirectUrl`。

### Phase F: 更新全局目标审计

目的：

- 让最终 goal audit 反映新计划和最新实验结论；
- 不让旧负控继续牵引路线。

脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_pure_protocol_goal_gap.py`

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.md`

必须更新：

- 新计划路径；
- H0-H5 状态；
- s00 risk/verify material；
- collector -> risk consumption chain；
- single transition candidate；
- fresh-session 最小实验结果；
- `end_to_end_pure_protocol_poc` 的真实缺口。

## 6. 后续实现顺序

从现在开始，严格按以下顺序执行：

1. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/docs/pure-protocol-human-reframed-execution-plan.md`
2. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_s00_risk_verify_material_gap.py`
3. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/s00_risk_verify_material_gap.json`
4. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_to_risk_consumption_chain.py`
5. `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/collector_to_risk_consumption_chain.json`
6. 如果仍未收敛，生成 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/single_transition_candidate_matrix.json`
7. 只有 `readyForFreshExperiment=true` 时，执行一个 fresh-session 最小实验并生成 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/hypothesis_reframe/minimal_single_transition_experiment_audit.json`
8. 更新 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/goal_audit/pure_protocol_goal_gap_audit.json`

## 7. 禁止事项

- 禁止继续随机组合 payload / pc / body / outer fields；
- 禁止把 s00 accepted packet 当作可移植模板；
- 禁止把 decoded activity equality 写成充分条件；
- 禁止在没有 single transition candidate 的情况下跑新 session 实验；
- 禁止用“可能”“感觉”“大概率”作为结论；
- 禁止用静态 JS 注释覆盖 runtime/network 证据；
- 禁止重复验证已被反证的 h2 / response-order / first-failure-order 方向；
- 禁止把已纠正的错误排序结论重新作为依据；
- 禁止为了短期阶段推进改变最终目标。

## 8. 完成标准

本计划文档完成不代表最终目标完成。

最终目标只有在以下证据全部成立时才算完成：

1. pure protocol fresh session 产生 collector HUMAN success；
2. collector response 离线解码包含成功状态；
3. decoded response handler 可离线更新 `_px` cookie/token jar；
4. risk/verify 使用该 jar 返回 `state=continue`；
5. CreateAccount 返回 `redirectUrl`；
6. 全流程不依赖浏览器/Camoufox/真实鼠标/视觉/外部打码；
7. 每一步都有本地证据路径和可复现命令。
