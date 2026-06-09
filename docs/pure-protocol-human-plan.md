# 纯协议 HUMAN 成功包复现目标与执行计划

## 最终目标

实现并验证“完全纯协议解析 + 复现 HUMAN 成功包”的可行闭环：

- 不依赖浏览器、Camoufox、真实鼠标、视觉定位、外部打码；
- 纯 HTTP / JS 解析 / 加密 / 请求重放；
- 能从 Outlook signup 初始状态推进到 HUMAN collector 成功事件；
- 能让 Microsoft `/API/Proofs/risk/verify` 返回 `state=continue`；
- 能继续让 `/API/CreateAccount` 返回 `redirectUrl`。

所有结论必须来自证据：

- 静态 JS；
- 运行时 hook；
- network trace；
- HAR；
- cookie 时间线；
- 成功/失败对照样本。

没有证据时，不写成结论。

## 阶段 1：成功/失败 trace 分类器

目标：先把“什么叫成功包”变成机器可判定规则。

必须识别：

- `collector` 是否返回 decoded event；
- decoded event 是否包含 `oIIoIooo|0`；
- 是否进入 `Wc -> window["_zC5j78dihandler"]["PX764"] -> Ot(0,...)`；
- 是否触发 `zt("succeeded")`；
- 是否收到 `postMessage {"type":"succeeded"}`；
- Microsoft `/API/Proofs/risk/verify` 是否返回 `state=continue`；
- `/API/CreateAccount` 是否返回 `redirectUrl`。

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/human_trace_classifier.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/trace_classification_*.json`

## 阶段 2：collector response 离线解码器

目标：不用浏览器 hook，从 collector 原始响应里离线解码出 handler event packet。

重点函数：

- `Wl(e)`：判断响应是否 JSON 且含 `do/ob`。
- `om(e,n)`：入口；JSON 走 `jl(u,true)`，编码包走 `j(u) -> ne(...)-> split("~~~~") -> jl(u,false)`。
- `jl(e,n)`：按 `Cl/Xl` handler 表派发。
- `oIIoIooo`：成功状态 handler，最终通过 `Wc` 调用 captcha 侧 `PX764/Ot`。
- `oIIoIIoo`：`_pxde/enrich` 相关 handler。
- `IoooII/Zl`：`_px3/bake` 相关 handler。

成功标准：

- 对成功样本离线解出 `oIIoIooo|0`；
- 对失败样本明确说明缺失点；
- 输出 decoded packet 与运行时 hook 中 `hsprotect.main.om.decode` 一致。

## 阶段 3：collector payload 构造器

目标：纯协议生成 `/api/v2/msft` 请求 body。

当前已有证据：

- `tf.payload` hook 已抓到 payload 构造前字段；
- `meta.pc` 与 network POST body 的 `pc` 一致；
- `meta.appID/tag/cu` 与 network POST body 的 `appId/tag/uuid` 一致。

需要继续还原：

- `tf(t,e)`；
- `ut(t)` JSON stringify；
- `Jt(ut(t), [po(), tag, sid].join(":"))`；
- `Vs(t,d)` payload 编码；
- activity 编码与必要字段；
- beacon 与 normal collector request 差异。

## 阶段 4：POW 复算

目标：纯协议复算 captcha worker POW。

已知证据：

- 成功样本出现 worker range；
- 成功样本出现 `pow.hit i=50239`；
- `captcha.js` 中 `poi/qs/sha256` 静态函数可定位。

成功标准：

- 对成功样本复算出同一 `i/value`；
- 明确 POW result 如何进入 collector payload。

## 阶段 5：cookie/token 时间线复现

目标：纯协议维护 `_pxvid/_pxde/_px3`。

必须输出：

- 初始来源；
- 更新 handler；
- domain/path/samesite/secure；
- `risk/verify` 和 `CreateAccount` 读取的 cookie jar。

## 阶段 6：Microsoft risk/verify 重放

目标：纯协议调用 `/API/Proofs/risk/verify` 并得到 `state=continue`。

必须提取最小字段：

- URL；
- method；
- headers；
- body；
- cookies；
- challenge/session id；
- HUMAN result/token 字段。

## 阶段 7：端到端纯协议 PoC

目标：

```text
GET signup/oauth authorize
-> fingerprint/dfp prewarm
-> collector payload build
-> collector request
-> collector response decode
-> _px cookies update
-> risk/verify
-> CreateAccount
```

成功标准：

- 不启动浏览器；
- 不调用 Camoufox；
- 不调用 captcha provider；
- `risk/verify == state=continue`；
- `CreateAccount` 返回 `redirectUrl`。

## 当前证据边界

已证实：

- 客户端成功链：`collector decoded event -> oIIoIooo|0 -> Wc -> PX764 -> Ot(0) -> succeeded -> risk/verify state=continue -> CreateAccount redirectUrl`。

尚未证实：

- collector 服务端为什么返回 `oIIoIooo|0`；
- `_px3/_pxde/_pxvid` 服务端签名算法；
- Microsoft `risk/verify` 服务端评分逻辑。

这些边界必须通过后续协议重放实验来缩小，不能猜。

## 执行记录 2026-06-09

### 阶段 1 已完成：trace 成败分类器

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/human_trace_classifier.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/trace_classification_ni109xdjp5zp_1780948211.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/trace_classification_hcxwyrtiudbg_1780949301.json`

验证命令：

```bash
.venv/bin/python tools/human_trace_classifier.py \
  output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl
```

结果：

```json
[
  {
    "trace": "output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl",
    "status": "success",
    "missing": []
  },
  {
    "trace": "output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl",
    "status": "failure",
    "missing": [
      "decoded_oIIoIooo_0",
      "dispatch_oIIoIooo_0",
      "ot_succeeded",
      "captcha_succeeded_event",
      "parent_postmessage_succeeded",
      "risk_verify_state_continue",
      "create_account_redirectUrl"
    ]
  }
]
```

证据边界：

- 成功样本早期也会出现一次 `block` message；分类器不能把“出现过 block”当作最终失败，必须以后续 `oIIoIooo|0 -> Ot(0) -> succeeded -> risk/verify state=continue -> CreateAccount redirectUrl` 闭环为准。

### 阶段 2 已完成：collector response 离线解码

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_human_collector_response.mjs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.md`

静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:191-209`
  - `j(t)` 是 base64 decode。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:650-653`
  - `ne(t,e)` 是逐字符 XOR。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4215-4220`
  - `el(tag)` 计算 XOR key：`(hash(tag) % 900 + 100).toString()`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:8992-9009`
  - `om(e,n)` 对 `Wl(e)` 返回的 `ob/do` 继续执行 `j(...) -> ne(..., parseInt(el(tag),10)%128) -> split("~~~~")`。

验证结果：

- 成功样本离线解码 7 个 collector response。
- 成功样本最后一个 response 离线解出：

```text
IoIoIo|score|1|binary
IoIIIo|cu
oIIoIIoo|_pxde|330|...
oIIoIooo|0
IoooII|_px3|330|...
IoIoIo|score|0|binary
```

- 对照文件：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/compare_ni109xdjp5zp_1780948211.json`
- 对照结果：
  - 成功样本 offline decoded parts 与 runtime hook `hsprotect.main.om.decode`：`7/7` 完全一致。

失败样本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.md`
- 没有解出 `oIIoIooo|0`。

### 阶段 4 已完成：POW 纯 Node 复算

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/solve_human_pow.mjs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow/pow_replay_ni109xdjp5zp_1780948211.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow/pow_replay_hcxwyrtiudbg_1780949301.md`

静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8299-8307`

```js
function poi(r, n, u, t, v, e, f, s) {
  var m = (u + (r & n).toString(16)).slice(-t),
    z = e + (v + (r >> (t << 2))).toString(16) + m;
  if (sha256(z) === s) return z
}

function qs(r, n, u, t, v, e, f, s, m) {
  for (var z, i = r; i <= n; i++)(z = poi(i, u, t, v, e, f, 0, m)) && postMessage(z);
  postMessage(!1)
}
```

运行时证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:260-263`
  - 4 个 worker range。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:272`
  - `pow.hit i=50239`
  - `value=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f`

collector decoded event 证据：

```text
IooIIo|1|218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564|1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6|18|false
```

注意：

- `IooIIo` 第二字段是 `seed+salt` 合并值。
- worker 入参里 `seed=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac756`，`salt=4`。

复算结果：

```text
from=0
to=65536
i=50239
value=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
sha256(value)=1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
matchesObserved=true
```

这证明 POW 已经可以脱离浏览器纯协议/纯 Node 复算。

### 当前下一步

下一步进入阶段 3/5：

1. 反推 `tf(t,e) -> ut(t) -> Jt(...) -> Vs(t,d)`，实现 collector request payload 构造器。
2. 从 decoded event 自动生成 cookie 时间线：
   - `IoooII|_px3|...`
   - `oIIoIIoo|_pxde|...`
   - `IooIoo|_pxvid|...`
3. 用纯协议 cookie jar 对齐 `risk/verify` 前的浏览器状态。

### 阶段 3/5 增量：collector payload 链路对齐与 cookie 时间线

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/analyze_human_payload_chain.mjs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/human_cookie_timeline.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/payload_chain/payload_chain_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/payload_chain/payload_chain_ni109xdjp5zp_1780948211.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/cookie_timeline/cookie_timeline_ni109xdjp5zp_1780948211.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/cookie_timeline/cookie_timeline_hcxwyrtiudbg_1780949301.md`

工具校验：

```bash
node --check tools/analyze_human_payload_chain.mjs
.venv/bin/python -m py_compile tools/human_cookie_timeline.py
```

上述两个命令均无错误输出。

#### 3.1 `tf()` / `Vs()` 静态证据

静态源码位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4807-4852`
  - `tf(t,e)` 会：
    - 给 activity 增补环境字段、`_px3/_px2` 字段；
    - 计算 `h = Jt(ut(t), [po(), tag, ft].join(":"))`；
    - 构造 `d = { vid, tag, appID, cu, cs, pc }`；
    - 调用 `v = Vs(t, d)`；
    - 生成 form 参数数组：`payload/appId/tag/uuid/ft/seq/en`，并追加 `cs/pc/sid/vid/pxhd/cts/hid/pxac` 等可选字段。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:3560-3598`
  - `Vs(t,d)` 会复制 activity 数组，生成一个 metadata 字符串，并按 `cu` 派生的位置表插入到 serialized activity 字符串中。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:321-340`
  - `ut(e)` 是本地 JSON-like serializer。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:593-604`
  - `Jt(t,e)` 用 `P(t,e)` 结果派生 `pc`。

边界：

- 目前已经确认 `tf()` 输出与 POST 参数关系。
- 还没有完成纯协议重写 `Vs()` 的完全等价构造器；这仍是后续工作。

#### 3.2 失败样本 `hcx...`：`tf.payload` 与 collector POST 完全对齐

样本：

- JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl`
- runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl`
- 对照产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/payload_chain/payload_chain_hcxwyrtiudbg_1780949301.json`

对照结果：

```json
{
  "tfPayloadEvents": 6,
  "collectorRequests": 4,
  "exactPayloadMatches": 4,
  "appIdMatches": 4,
  "tagMatches": 4,
  "uuidMatches": 4,
  "pcMatches": 4
}
```

关键证据：

- runtime collector POST 第 1 个请求在 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl:27`。
- 对应 `tf.payload` 在 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:32`。
- 工具对齐后显示：
  - `payload` 完全一致；
  - `appId=PXzC5j78di` 一致；
  - `tag=YjIYfyxJHRR9` 一致；
  - `uuid=d347af50-6375-11f1-b31a-c1d900f88e04` 一致；
  - `pc` 一致。

第 1 个 POST 参数形态：

```text
payload=<tf payload>
appId=PXzC5j78di
tag=YjIYfyxJHRR9
uuid=d347af50-6375-11f1-b31a-c1d900f88e04
ft=369
seq=0
en=NTA
pc=1462244708120922
p1=19c154a1-0d0e-6906-9593-618f309a23de
rsc=1
```

注意：

- `payload` 里包含 `+` 字符。对照工具已按 form body 原始语义处理，避免把 `+` 误还原为空格。
- `hcx...` 是失败样本，适合用于反推 payload 构造，不可拿来证明成功 handler。

#### 3.3 成功样本 `ni...`：cookie/success 时间线已对齐

样本：

- JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl`
- runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl`
- collector decode：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json`
- cookie timeline：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/cookie_timeline/cookie_timeline_ni109xdjp5zp_1780948211.json`

时间线对照结果：

```json
{
  "decodedCookieOrSuccessEvents": 23,
  "parentCookieOrSuccessMessages": 17,
  "correlatedEvents": 16
}
```

关键成功包对照：

```text
collectorLine=302 part=2 handler=oIIoIIoo name=_pxde -> parentLine=331 valueMatch=True
collectorLine=302 part=3 handler=oIIoIooo name=challenge_success -> parentLine=332 valueMatch=True
collectorLine=302 part=4 handler=IoooII name=_px3 -> parentLine=330 valueMatch=True
```

对应原始证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:302`
  - 最后一个 decoded collector response 含：
    - `oIIoIIoo|_pxde|...`
    - `oIIoIooo|0`
    - `IoooII|_px3|...`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:330`
  - parent 收到 `_px3` cookie message。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:331`
  - parent 收到 `_pxde` cookie message。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:332`
  - parent 收到 `{"type":"succeeded"}`。

这条证据证明：

```text
collector response -> jl handler queue -> _pxde/_px3 cookie message -> succeeded message
```

在成功样本中成立。

#### 3.4 成功样本 `ni...` 的 payload 证据缺口

对照产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/payload_chain/payload_chain_ni109xdjp5zp_1780948211.json`

结果：

```json
{
  "tfPayloadEvents": 0,
  "collectorRequests": 5,
  "exactPayloadMatches": 0,
  "appIdMatches": 0,
  "tagMatches": 0,
  "uuidMatches": 0,
  "pcMatches": 0
}
```

原因：

- 该成功样本 runtime trace 有 5 个 collector POST。
- 但同轮 JS trace 没有 `hsprotect.main.tf.payload` hook 事件。
- 因此不能声称“成功样本的 `tf.payload` 与 collector POST 已直接对齐”。

当前只能做两个分离结论：

1. 失败样本 `hcx...` 证明 `tf.payload -> collector POST` 关系。
2. 成功样本 `ni...` 证明 `collector response -> cookie/succeeded -> risk/verify -> CreateAccount` 后半链。

下一步必须用同一轮成功样本同时抓到：

- `hsprotect.main.tf.payload`
- collector POST
- decoded `oIIoIooo|0`
- parent `succeeded`
- `risk/verify state=continue`
- `CreateAccount redirectUrl`

否则不能把整条链写成同一运行的端到端证据。

#### 3.5 多样本对照边界

对更多历史 trace 执行分类：

```bash
.venv/bin/python tools/human_trace_classifier.py \
  output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl \
  output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl \
  output/outlook_browser/js_internal_trace_nzkl1us2bp7r_1780943349.jsonl \
  output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl \
  output/outlook_browser/js_internal_trace_c0nw0cg8yyz9_1780941858.jsonl \
  output/outlook_browser/js_internal_trace_bcs0nitb7bef_1780942944.jsonl \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl
```

结果：

- `sv2n3df1y8fi_1780946111`：`partial`，缺 decoded/dispatch `oIIoIooo|0`，但后续链有部分成功迹象。
- `rdawhdfsqt6e_1780944209`：`partial`，缺 decoded/dispatch/Ot/risk/CreateAccount。
- `nzkl1us2bp7r_1780943349`：`partial`，缺 decoded/dispatch/Ot/risk/CreateAccount。
- `l74w94f94xdf_1780943704`：`partial`，缺 decoded/dispatch/Ot/risk/CreateAccount。
- `c0nw0cg8yyz9_1780941858`：`partial`，缺 decoded/dispatch/Ot/captcha/risk/CreateAccount。
- `bcs0nitb7bef_1780942944`：`partial`，缺 decoded/dispatch/Ot/risk/CreateAccount。
- `hcxwyrtiudbg_1780949301`：`failure`，缺完整成功链。

结论边界：

- 当前只有 `ni109xdjp5zp_1780948211` 是完整成功链证据。
- 早期多个 trace 虽有 `succeeded` parent message，但缺 `fp.enter/om.decode/jl.dispatch/Ot` 内部链，不能用于证明 collector 成功 handler。
- `hcx...` 有最完整的 `tf.payload` 观测，但它是失败样本。

### 下一步修正后的执行目标

当前距“完全纯协议解析 + 复现 HUMAN 成功包”仍缺：

1. 在同一成功样本里同时抓到 `tf.payload` 与成功 handler。
2. 纯 Node/纯 Python 等价实现 `ut/Jt/Vs/tf`，并用运行时样本逐字段对照。
3. 从 decoded collector response 自动更新纯协议 cookie jar：
   - `_px3`
   - `_pxde`
   - `_pxvid`
   - `cc/fed/rf/fp/nf` 等 `IIooII` cookie/flag。
4. 用纯协议重放 `risk/verify`，证明返回 `state=continue`。
5. 用同一 cookie jar 重放 `CreateAccount`，证明拿到 `redirectUrl`。

只有上述 1-5 全部完成，才可以把目标标记为完成。

## 2026-06-09 23:06 增量证据：侵入式 JS patch 污染风控，Vs payload 离线复算完成

### 4.1 运行结论：`OUTLOOK_HSPROTECT_JS_PATCH=1` 不能用于成功样本采集

本轮先补了 HSProtect JS 源码/patch 诊断落盘逻辑：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`
- 新增产物目录：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/hsprotect_js_patch/`

每次拦截 `client.hsprotect.net/PXzC5j78di/main.min.js` 或 `captcha.hsprotect.net/PXzC5j78di/captcha.js` 时会落：

- `*.source.js`
- `*.patched.js`
- `*.json` 元数据，包含 `sha256`、`patches`、needle/probe 命中情况。

本轮带 patch 重试命令：

```bash
OUTLOOK_HSPROTECT_JS_PATCH=1 REGISTER_ONLY_MAX_ATTEMPTS=3 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python -u pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

两轮关键样本：

- `whsnxy8ag5ji`
  - runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_whsnxy8ag5ji_1781017142.jsonl`
  - JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl`
- `i294e72kliud`
  - runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_i294e72kliud_1781017380.jsonl`
  - JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl`

patch 命中证据：

- `main_main_1781017429_50a16178f090.json`
  - `patches` 包含：
    - `__outlook_hsprotect_patch_main_xn_event_bus__`
    - `__outlook_hsprotect_patch_main_sendbeacon_internal__`
    - `__outlook_hsprotect_patch_main_fp_enter__`
    - `__outlook_hsprotect_patch_main_om_enter_decode__`
    - `__outlook_hsprotect_patch_main_jl_dispatch__`
    - `__outlook_hsprotect_patch_main_tf_enter__`
    - `__outlook_hsprotect_patch_main_tf_payload__`
- `captcha_main_1781017427_42fe203091d0.json`
  - `patches` 包含：
    - `__outlook_hsprotect_patch_captcha_zt_enter__`
    - `__outlook_hsprotect_patch_captcha_ot_enter__`
    - `__outlook_hsprotect_patch_captcha_qs_pow__`
    - `__outlook_hsprotect_patch_captcha_worker_new__`

分类器结果：

```bash
.venv/bin/python tools/human_trace_classifier.py \
  output/outlook_browser/js_internal_trace_e4tprvk082rw_1781016494.jsonl \
  output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl \
  output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl
```

结果：

- `e4tprvk082rw_1781016494`：`partial`
  - 该样本未开 patch，但 runtime 已证明后半链成功：
    - `risk/verify` 返回 `state=continue`
    - `CreateAccount` 返回 `redirectUrl`
    - 最终拿到 OAuth refresh token。
- `whsnxy8ag5ji_1781017142`：`failure`
  - 缺：
    - `parent_postmessage_succeeded`
    - `risk_verify_state_continue`
    - `create_account_redirectUrl`
- `i294e72kliud_1781017380`：`failure`
  - 缺：
    - `parent_postmessage_succeeded`
    - `risk_verify_state_continue`
    - `create_account_redirectUrl`

失败链的直接证据：

- 两个带 patch 样本按压后只收到 `_px3/_pxde` cookie message，没有收到 `{"type":"succeeded"}`。
- 之后 `ch_ctx=1` iframe 变为 404：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_pending_frame_target_4_1781017325_frame4.html:3` 为 `<title>404</title>`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_pending_frame_target_4_1781017325_frame4.html:6` 为 `404`
- browser api create 返回 `error_code=1059`，没有 `redirectUrl`。

结论边界：

- `OUTLOOK_HSPROTECT_JS_PATCH=1` 会改变 HSProtect 运行环境，污染风控结果。
- 后续不能再用“改写 HSProtect JS”方式采集成功样本。
- 已落盘的 `*.source.js` 可以作为静态反混淆证据继续使用。
- 带 patch 的失败样本只能用于证明内部算法关系，不能用于证明服务端成功接受。

### 4.2 Vs payload 编码已离线复算到字节级一致

修正解析器：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/replay_human_vs_payload.mjs`

修正点：

- 之前解析器用 `vid` 推导 marker，导致：
  - `serializedMatch=6/6`
  - `payloadMatch=0/6`
- 本轮使用 `hsprotect.main.tf.payload` hook 中真实 `marker` 字段后，复算与网络 payload 字节级一致。

验证命令：

```bash
node --check tools/replay_human_vs_payload.mjs
node tools/replay_human_vs_payload.mjs \
  output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl \
  output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl
```

结果：

```json
[
  {
    "trace": "output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl",
    "eventCount": 6,
    "payloadMatches": 6,
    "serializedMatches": 6
  },
  {
    "trace": "output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl",
    "eventCount": 6,
    "payloadMatches": 6,
    "serializedMatches": 6
  }
]
```

产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/payload_replay/vs_payload_replay_whsnxy8ag5ji_1781017142.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/payload_replay/vs_payload_replay_i294e72kliud_1781017380.md`

其中 `i294e72kliud` 的复算表：

```text
line 32  serialized=true payload=true observed=584   replay=584
line 83  serialized=true payload=true observed=8612  replay=8612
line 109 serialized=true payload=true observed=6500  replay=6500
line 144 serialized=true payload=true observed=9660  replay=9660
line 197 serialized=true payload=true observed=1604  replay=1604
line 223 serialized=true payload=true observed=28344 replay=28344
```

结论边界：

- 已证实：`ut(activity) -> marker -> Vs(activity, meta) -> collector payload` 可离线复算到字节级一致。
- 尚未证实：纯协议生成的 payload 能让 collector 返回成功 handler `oIIoIooo|0`。
- 尚未证实：marker 的完整来源算法。当前 marker 来自 runtime hook 字段，不是纯静态推导。

### 4.3 当前目标调整

下一步不能再靠侵入式 hook 采成功包。路线调整为：

1. 使用无 patch 成功样本作为服务端成功链证据。
2. 使用带 patch 失败样本作为 `tf/Vs/payload` 编码器证据。
3. 使用 `hsprotect_js_patch/*.source.js` 做静态反混淆，补 marker 来源、`Jt/pc`、collector response decode。
4. 从成功样本 runtime POST 和 cookie/risk timeline 中提取最小可重放字段。
5. 纯协议重放时不得依赖浏览器，也不得注入 HSProtect JS。

## 2026-06-09 23:15 增量证据：`pc=Jt(...)` 已离线复算到字节级一致

### 5.1 静态定位

静态来源：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:321`
  - `ut(e)`：本地 JSON-like serializer。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:593`
  - `Jt(t,e)`：对 `P(t,e)` 结果做 digit/filter 变换，输出 `pc`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:650`
  - `ne(t,e)`：XOR helper。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:3541`
  - `Vs(t,e)`：payload 插入编码函数。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4807`
  - `tf(t,e)`：collector form 参数构造入口。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4827`
  - `h = Jt(ut(t), (s = e[on], l = e[cn], [po(), s, l].join(":")))`

`P(t,e)` / HMAC-MD5 证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:141`
  - `k(t,e)` 是 HMAC-MD5 inner/outer pad 实现。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:173`
  - `P(t,e,n)` 在 `e` 存在且 `n` 不存在时返回 `F(k(e,t))`，即 hex HMAC-MD5。

因此 `pc` 计算链为：

```text
serialized = ut(activities)
pcKey = [po(), tag, ft].join(":")
digest = HMAC_MD5(key=pcKey, message=serialized).hex()
pc = Jt_filter(digest)
```

其中本项目样本中：

- `tag = YjIYfyxJHRR9`
- `ft = 369`
- `po()` 与 collector request 中 `uuid` / `cu` 一致。

### 5.2 工具修正

修正文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/replay_human_vs_payload.mjs`

新增验证内容：

- `pcReplay`
- `pcObserved`
- `pcKey`
- `pcMatch`

验证命令：

```bash
node --check tools/replay_human_vs_payload.mjs
node tools/replay_human_vs_payload.mjs \
  output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl \
  output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl
```

结果：

```json
[
  {
    "trace": "output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl",
    "eventCount": 6,
    "payloadMatches": 6,
    "serializedMatches": 6,
    "pcMatches": 6
  },
  {
    "trace": "output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl",
    "eventCount": 6,
    "payloadMatches": 6,
    "serializedMatches": 6,
    "pcMatches": 6
  }
]
```

### 5.3 字段级样例

`i294e72kliud` 样本：

```text
line 32:
  pcKey      = 59453f70-6414-11f1-9b23-8786d00c81f1:YjIYfyxJHRR9:369
  pcObserved = 7583960431709729
  pcReplay   = 7583960431709729

line 83:
  pcKey      = 59453f70-6414-11f1-9b23-8786d00c81f1:YjIYfyxJHRR9:369
  pcObserved = 2647373331022820
  pcReplay   = 2647373331022820
```

`whsnxy8ag5ji` 样本：

```text
line 32:
  pcKey      = cd23d5b0-6413-11f1-a789-d34e3349a3e1:YjIYfyxJHRR9:369
  pcObserved = 8673987222119071
  pcReplay   = 8673987222119071

line 83:
  pcKey      = cd23d5b0-6413-11f1-a789-d34e3349a3e1:YjIYfyxJHRR9:369
  pcObserved = 3878893128208898
  pcReplay   = 3878893128208898
```

结论边界：

- 已证实：`ut`、`Jt/pc`、`Vs/payload` 三段均可离线复算到字段级一致。
- 尚未证实：`marker = ne(J(Qi() || Xs(118)), 10)` 中 `Qi()` 的纯协议来源。
- 尚未证实：复算出的 payload 能让 collector 返回 `oIIoIooo|0` 成功 handler。

## 6. `OUTLOOK_HSPROTECT_JS_PATCH=1` 的污染证据与新语义

结论：`OUTLOOK_HSPROTECT_JS_PATCH=1` 不能作为成功样本采集方式。它会改变 HUMAN JS 运行时代码，现有两轮样本均进入失败链路。因此该开关改为默认“只抓取源码并落盘离线分析”，不再把 patched JS 返回页面；只有显式设置 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1` 才真正注入 patched JS。

### 6.1 失败样本证据

样本 1：

- runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_whsnxy8ag5ji_1781017142.jsonl`
- JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl`
- patch meta：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/hsprotect_js_patch/main_main_1781017163_50a16178f090.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.json`

关键行：

- `runtime_trace_whsnxy8ag5ji_1781017142.jsonl:166`：`risk/verify` 返回 `HumanCaptcha`，`uuid=cd23d5b0-6413-11f1-a789-d34e3349a3e1`，`vid=ce463152-6413-11f1-85c3-2baacc4258c7`。
- `runtime_trace_whsnxy8ag5ji_1781017142.jsonl:176`：iframe 收到 `{"type":"block",...,"requestUrl":"/api/v1.0/risk/verify"}`。
- `runtime_trace_whsnxy8ag5ji_1781017142.jsonl:258`：`https://iframe.hsprotect.net/px/captcha_close?status=-1` 返回 `404`。
- `runtime_trace_whsnxy8ag5ji_1781017142.jsonl:297`：`CreateAccount` 返回 `{"error":{"code":"1059",...}}`。
- `main_main_1781017163_50a16178f090.json`：`changed=true`，patches 包含 `main_xn_event_bus`、`main_sendbeacon_internal`、`main_fp_enter`、`main_om_enter_decode`、`main_jl_dispatch`、`main_tf_enter`、`main_tf_payload`。
- `captcha_main_1781017191_42fe203091d0.json`：`changed=true`，patches 包含 `captcha_zt_enter`、`captcha_ot_enter`、`captcha_qs_pow`、`captcha_worker_new`。

样本 2：

- runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_i294e72kliud_1781017380.jsonl`
- JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl`
- patch meta：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/hsprotect_js_patch/main_main_1781017398_50a16178f090.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/hsprotect_js_patch/captcha_main_1781017427_42fe203091d0.json`

关键行：

- `runtime_trace_i294e72kliud_1781017380.jsonl:166`：`risk/verify` 返回 `HumanCaptcha`，`uuid=59453f70-6414-11f1-9b23-8786d00c81f1`，`vid=5abd227a-6414-11f1-90c0-b0cabbeb4ccb`。
- `runtime_trace_i294e72kliud_1781017380.jsonl:175`：iframe 收到 `{"type":"block",...,"requestUrl":"/api/v1.0/risk/verify"}`。
- `runtime_trace_i294e72kliud_1781017380.jsonl:257`：`https://iframe.hsprotect.net/px/captcha_close?status=-1` 返回 `404`。
- `runtime_trace_i294e72kliud_1781017380.jsonl:296`：`CreateAccount` 返回 `{"error":{"code":"1059",...}}`。
- `main_main_1781017398_50a16178f090.json` 与 `captcha_main_1781017427_42fe203091d0.json` 均为 `changed=true`。

对照成功样本：

- runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_e4tprvk082rw_1781016494.jsonl`
- JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_e4tprvk082rw_1781016494.jsonl`

关键行：

- `runtime_trace_e4tprvk082rw_1781016494.jsonl:105`：第一轮出现 `{"type":"failed"}`。
- `runtime_trace_e4tprvk082rw_1781016494.jsonl:213`：后续出现 `{"type":"succeeded"}`。
- `runtime_trace_e4tprvk082rw_1781016494.jsonl:215`：`succeeded` 后再次调用 `risk/verify`。
- `runtime_trace_e4tprvk082rw_1781016494.jsonl:221`：`risk/verify` 返回 `200`。
- `runtime_trace_e4tprvk082rw_1781016494.jsonl:222-223`：随后调用 `CreateAccount` 并返回 `200`。

证据边界：

- 已证实：在上述两轮 patched 样本中，patch 命中 main/captcha 多个函数，且链路走向 `block`、`captcha_close?status=-1`、`CreateAccount error_code=1059`。
- 已证实：无 intrusive patch 的成功样本中，存在 `succeeded -> risk/verify -> CreateAccount` 链路。
- 未证实：每一个 patch 点中具体哪一个触发检测；因此不能把原因收敛到单个函数 hook，只能认定“当前 intrusive patch 组合污染运行链路”。

### 6.2 代码语义修正

修改文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`

新语义：

- `OUTLOOK_HSPROTECT_JS_PATCH=1`：启用 HSProtect JS 采集，落盘 `source.js`、`patched.js`、meta JSON；返回给浏览器的仍是原始 JS。
- `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`：在上一个开关开启时，才把 patched JS 返回给浏览器。该模式只能用于失败样本实验，不能用于成功样本采集。

验证：

```bash
python3 -m py_compile CTF-reg/outlook_browser_register.py
```

## 7. collector handler/state 离线还原

本节新增一个离线 state replay，用 decoded collector response 直接还原 HUMAN 客户端 handler 效果。目标是把“collector 返回了什么”推进到“纯协议应维护哪些 cookie/localStorage/memory/success gate”。

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/replay_human_collector_state.py`

输入：

- `output/protocol_reverse/collector_decode/collector_decode_*.json`
- 可选 `output/outlook_browser/js_internal_trace_*.jsonl`，用于和 parent `postMessage` 里的 cookie/succeeded 消息做对齐。

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_*.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_*.md`

验证命令：

```bash
python3 -m py_compile tools/replay_human_collector_state.py

python3 tools/replay_human_collector_state.py \
  output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json \
  --trace output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl

python3 tools/replay_human_collector_state.py \
  output/protocol_reverse/collector_decode/collector_decode_whsnxy8ag5ji_1781017142.json \
  --trace output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl

python3 tools/replay_human_collector_state.py \
  output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.json \
  --trace output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl
```

### 7.1 handler 语义映射证据

静态来源：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js`

已映射 handler：

| handler | 离线 effect | 静态证据 |
|---|---|---|
| `IoooII` | set `_px3` / bake cookie | `main.beautified.js:4358` 映射到 `Zl`；`main.beautified.js:4717` 定义 `Zl`；`main.beautified.js:4721` 调 `di.trigger("bake",...)` 与 `Wn(t,e,n,a)` |
| `oIIoIIoo` | set `_pxde` / enrich cookie | `main.beautified.js:4487` 定义；`main.beautified.js:4496` 调 `Wn(t,e,n,a)` 与 `di.trigger("enrich",...)` |
| `IooIoo` | set `_pxvid` + localStorage vid | `main.beautified.js:4399` 定义；`main.beautified.js:4402` 调 `Rt(t)`, `Oi(t)`, `Wn(ui,e,t,n)`, `er(ui,{ttl,val})` |
| `oIIoIooo` | challenge success/terminal gate | `main.beautified.js:4528` 定义；`main.beautified.js:4535` 调 `Wc(... [t].concat(r))`；`main.beautified.js:2937` `Wc` 调已注册 callback |
| `oIIoIoII` | set `Jo` / `Qi()` marker seed | `main.beautified.js:4487` 映射到 `Yl`；`main.beautified.js:4701` `Yl(t){Jo=t,...}`；`main.beautified.js:2675` `Qi(){return Jo}` |
| `oIIooIIo` | set hidden-id cookie candidate | `main.beautified.js:4490` 调 `Bi(t,e)`；`main.beautified.js:1901` `Bi` 内部调用 `Wn(li,null,t,e)` |
| `IIooII` | localStorage feature flag | `main.beautified.js:4375` `IIooII` 调 `lr(true,{ff:t,ttl:e,val:n})` |
| `IoIIIo` | set `Ns` current marker | `main.beautified.js:4526` 定义；`main.beautified.js:4527` 赋值 `Ns=t` |
| `oIIooIoo` | dimension jump callback data | `main.beautified.js:4589` 定义；`main.beautified.js:4618-4624` 构造 `{startWidth,startHeight,widthJump,heightJump,hash}`；`main.beautified.js:4625-4627` 调 challenge callback |

### 7.2 成功样本 replay 结果

成功样本：

- decode：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json`
- trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl`
- state replay：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.md`

验证结果：

```json
{
  "decodedEntries": 7,
  "handlerEvents": 55,
  "cookies": 4,
  "localStorage": 6,
  "memory": 11,
  "scores": 8,
  "successEvents": 1,
  "unknownEvents": 0,
  "parentMessages": 18,
  "parentCorrelations": 16
}
```

关键证据：

- `collector_state_ni109xdjp5zp_1780948211.md`：
  - final cookies 有 `_px3`, `_pxde`, `_pxvid`, `_pxhd_candidate`。
  - success event：`value=0 collectorLine=302 part=3`。
  - parent correlation：
    - `collectorLine=302 part=2 handler=oIIoIIoo` 对齐 parent `_pxde` cookie message。
    - `collectorLine=302 part=3 handler=oIIoIooo` 对齐 parent `succeeded` message。
    - `collectorLine=302 part=4 handler=IoooII` 对齐 parent `_px3` cookie message。

这证明：成功样本中 `collector decoded response -> _pxde/_px3 cookie update -> oIIoIooo|0 -> parent succeeded` 可以完全离线还原并与 runtime message 对齐。

### 7.3 失败/污染样本 replay 结果

patched 污染样本：

- decode：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_whsnxy8ag5ji_1781017142.json`
- trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl`
- state replay：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_whsnxy8ag5ji_1781017142.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_whsnxy8ag5ji_1781017142.md`

验证结果：

```json
{
  "decodedEntries": 6,
  "handlerEvents": 49,
  "cookies": 4,
  "localStorage": 6,
  "memory": 11,
  "scores": 6,
  "successEvents": 0,
  "unknownEvents": 0,
  "parentMessages": 20,
  "parentCorrelations": 11
}
```

失败样本：

- decode：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.json`
- trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl`
- state replay：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_hcxwyrtiudbg_1780949301.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_hcxwyrtiudbg_1780949301.md`

验证结果：

```json
{
  "decodedEntries": 6,
  "handlerEvents": 49,
  "cookies": 4,
  "localStorage": 6,
  "memory": 11,
  "scores": 6,
  "successEvents": 0,
  "unknownEvents": 0,
  "parentMessages": 20,
  "parentCorrelations": 11
}
```

对照结论：

- 成功样本有 `successEvents=1`，且 `oIIoIooo|0` 与 parent `succeeded` 对齐。
- patched/失败样本无 `successEvents`，但同样能解析 cookie/localStorage/memory handler，说明失败点不是“离线 decode 不完整”，而是 collector 服务端没有返回成功 handler。
- 所有 observed handler 均已映射，`unknownEvents=0`。

### 7.4 对纯协议 PoC 的推进意义

已补齐的部分：

- collector response 可以离线解码；
- decoded handler 可以离线执行成 cookie/localStorage/memory/success state；
- 成功与失败样本可用 `successEvents` 明确区分；
- 成功样本的 `_px3/_pxde/_pxvid` 最终状态有可追溯来源。

仍未完成的部分：

- 还没有证明纯协议构造的 collector request 能让服务端返回 `oIIoIooo|0`；
- 还没有用离线 state replay 生成的 cookie jar 纯协议调用 Microsoft `risk/verify` 并得到 `state=continue`；
- 还没有端到端纯协议 `CreateAccount redirectUrl`。

## 8. Microsoft risk/verify 重放素材导出与 token 来源证明

本节新增 `risk/verify` 重放素材导出器。它不主动请求 Microsoft，只从 runtime trace 和 collector state replay 中提取可重放请求素材，并证明 `risk/verify` 请求体内的 HUMAN token 来源。

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/extract_risk_verify_material.py`

输入：

- runtime trace：`output/outlook_browser/runtime_trace_*.jsonl`
- collector state replay：`output/protocol_reverse/collector_state/collector_state_*.json`

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_*.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_*.md`

验证命令：

```bash
python3 -m py_compile tools/extract_risk_verify_material.py

python3 tools/extract_risk_verify_material.py \
  output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl \
  --collector-state output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.json

python3 tools/extract_risk_verify_material.py \
  output/outlook_browser/runtime_trace_whsnxy8ag5ji_1781017142.jsonl \
  --collector-state output/protocol_reverse/collector_state/collector_state_whsnxy8ag5ji_1781017142.json

python3 tools/extract_risk_verify_material.py \
  output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl \
  --collector-state output/protocol_reverse/collector_state/collector_state_hcxwyrtiudbg_1780949301.json
```

### 8.1 成功样本：risk/verify -> continue -> CreateAccount

成功样本输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.md`

验证结果：

```json
{
  "riskVerifyRequests": 2,
  "createAccountRequests": 1,
  "riskContinueResponses": 1,
  "tokenLinks": 2
}
```

关键链路：

| request line | response line | status | state | challengeSolution | px3 source | pxde source | pxvid source | all parent messages before request |
|---:|---:|---:|---|---|---|---|---|---|
| 157 | 158 | 200 | riskChallengeRequired | false | collectorLine=131 part=0 handler=IoooII | collectorLine=131 part=3 handler=oIIoIIoo | collectorLine=31 part=10 handler=IooIoo | true |
| 344 | 345 | 200 | continue | true | collectorLine=302 part=4 handler=IoooII | collectorLine=302 part=2 handler=oIIoIIoo | collectorLine=31 part=10 handler=IooIoo | true |

token link 证据：

- `risk.response:158 -> risk.request:344 via continuationToken match=True`
- `risk.response:345 -> create.request:346 via ContinuationToken match=True`

CreateAccount 证据：

- `requestLine=346 responseLine=347 status=200 redirectUrl=True`

时间顺序证据：

- 第二次 `risk/verify` 请求 line 344 使用的 `_px3`：
  - parent message line 330
  - `parentWallTime=1780948301.5012639`
  - `risk requestTime=1780948301.522094`
  - `parentBeforeRequest=True`
- 第二次 `risk/verify` 请求 line 344 使用的 `_pxde`：
  - parent message line 331
  - `parentWallTime=1780948301.501439`
  - `risk requestTime=1780948301.522094`
  - `parentBeforeRequest=True`
- 第二次 `risk/verify` 请求 line 344 使用的 `_pxvid`：
  - parent message line 76
  - `parentWallTime=1780948226.113396`
  - `risk requestTime=1780948301.522094`
  - `parentBeforeRequest=True`

结论：

- `risk/verify` 的成功请求体中 `challengeSolution.px3/pxde/pxvid` 与 `riskProviderMetadata[0].px3/pxde/pxvid` 可追溯到 collector decoded handler：
  - `_px3` 来源：`IoooII`
  - `_pxde` 来源：`oIIoIIoo`
  - `_pxvid` 来源：`IooIoo`
- 这些值在 runtime 中通过 parent `postMessage` 写入，且写入时间早于 `risk/verify` 成功请求。
- `risk/verify state=continue` 返回的 continuation token 被后续 `CreateAccount` 请求使用，并得到 `redirectUrl`。

### 8.2 失败/污染样本对照

patched 污染样本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_whsnxy8ag5ji_1781017142.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_whsnxy8ag5ji_1781017142.md`

结果：

```json
{
  "riskVerifyRequests": 1,
  "createAccountRequests": 1,
  "riskContinueResponses": 0,
  "tokenLinks": 0
}
```

失败样本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_hcxwyrtiudbg_1780949301.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_hcxwyrtiudbg_1780949301.md`

结果：

```json
{
  "riskVerifyRequests": 1,
  "createAccountRequests": 1,
  "riskContinueResponses": 0,
  "tokenLinks": 0
}
```

对照结论：

- 成功样本有第二次带 `challengeSolution` 的 `risk/verify`，返回 `state=continue`。
- 失败/污染样本只有第一次 `riskChallengeRequired`，没有 `challengeSolution` 成功提交，没有 `state=continue`，CreateAccount 也没有 `redirectUrl`。

### 8.3 对纯协议 PoC 的推进意义

已补齐：

- 成功 `risk/verify` 请求体完整落盘；
- 请求 headers、body、响应 headers、body 完整落盘；
- `challengeSolution` 三个 HUMAN token 有 collector handler 来源证明；
- token 写入 parent 的 runtime 时间早于 `risk/verify` 请求；
- continuation token 在 `risk.response -> risk.request -> CreateAccount` 之间的传递已证明。

仍未完成：

- 尚未主动用纯协议 session 重放 `risk/verify` 并得到实时 `state=continue`；
- 尚未主动用纯协议 session 完成 `CreateAccount redirectUrl`；
- 尚未证明新构造的 collector payload 可让服务端返回 `oIIoIooo|0`。

## 9. `risk/verify` 与 `CreateAccount` 请求体纯协议构造器验证

本节目标：证明已经可以从成功 runtime material + collector state 离线重建 Microsoft `risk/verify` 两次请求体和后续 `CreateAccount` 请求体，并做到与浏览器 runtime 抓到的 JSON 请求体字节级一致。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_risk_verify_request.py`

输入证据：

- material：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json`
- collector state：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.json`

验证命令：

```bash
python3 -m py_compile CTF-reg/outlook_browser_register.py tools/build_risk_verify_request.py
python3 tools/build_risk_verify_request.py \
  output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json \
  --collector-state output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.json
```

命令输出：

```json
{
  "jsonPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.json",
  "mdPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.md",
  "checks": {
    "initialObjectMatch": true,
    "initialJsonMatch": true,
    "solutionObjectMatch": true,
    "solutionJsonMatch": true,
    "createContinuationMatch": true,
    "createObjectMatch": true,
    "createJsonMatch": true
  }
}
```

输出文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.md`

构造器验证结果：

- `initialObjectMatch=True`：第一次 `risk/verify` 请求对象与 runtime 对象一致。
- `initialJsonMatch=True`：第一次 `risk/verify` compact JSON 字符串与 runtime `post_data` 一致。
- `solutionObjectMatch=True`：第二次带 `challengeSolution` 的 `risk/verify` 请求对象与 runtime 对象一致。
- `solutionJsonMatch=True`：第二次 `risk/verify` compact JSON 字符串与 runtime `post_data` 一致。
- `createContinuationMatch=True`：第二次 `risk/verify state=continue` 响应里的 `continuationToken` 被正确写入后续 `CreateAccount.ContinuationToken`。
- `createObjectMatch=True`：后续 `CreateAccount` 请求对象与 runtime 对象一致。
- `createJsonMatch=True`：后续 `CreateAccount` compact JSON 字符串与 runtime `post_data` 一致。

直接证据摘要：

```text
# risk/verify request build: ni109xdjp5zp_1780948211

material=output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.json
state=output/protocol_reverse/collector_state/collector_state_ni109xdjp5zp_1780948211.json

## checks
- initialObjectMatch: True
- initialJsonMatch: True
- solutionObjectMatch: True
- solutionJsonMatch: True
- createContinuationMatch: True
- createObjectMatch: True
- createJsonMatch: True

## diffs
### initial
- none
### solution
- none
### create
- none
```

结论边界：

- 已证实：给定成功样本已有的 continuation token、collector 产生的 `_px3/_pxde/_pxvid`、账号表单字段和 runtime headers/body material，可以离线重建两次 `risk/verify` 请求体与后续 `CreateAccount` 请求体，且 JSON 字符串与 runtime 完全一致。
- 未证实：纯协议端主动生成新的 collector 成功响应 `oIIoIooo|0`；因此端到端“无浏览器拿新 token”还未完成。
- 下一步应继续把 `collector payload -> collector response -> _px3/_pxde/_pxvid` 的实时生成链补齐，而不是再猜 `risk/verify` 请求体结构。

## 10. `OUTLOOK_HSPROTECT_JS_PATCH=1` 语义修正：capture 不再 route/fulfill

问题证据：

- 旧实现位于 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1510-1562`。
- 旧实现即使 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY` 未开启，也会对 HSProtect JS 走 `ctx.route("**/*") -> route.fetch() -> route.fulfill(body=原始 body)`。
- 因此旧的 `OUTLOOK_HSPROTECT_JS_PATCH=1` 虽然不返回 patched JS，但仍会改变资源加载链路；结合第 6 节污染样本，不能再把这种模式用于成功样本采集。

修正后的代码语义：

- `OUTLOOK_HSPROTECT_JS_PATCH=1` 且未设置 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`：
  - 使用 `ctx.on("response", response_handler)` 旁路读取 `client.hsprotect.net/.../main.min.js` 和 `captcha.hsprotect.net/.../captcha.js`；
  - 写出 `source.js`、`patched.js`、meta JSON；
  - 不注册 route；
  - 不执行 `route.fetch()`；
  - 不执行 `route.fulfill()`；
  - 浏览器仍按原始网络链路加载 HSProtect JS。
- 只有显式设置 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1` 时：
  - 才注册 route；
  - 才用 patched JS fulfill；
  - 该模式只用于失败样本实验，不能用于成功样本采集。

验证命令：

```bash
python3 -m py_compile CTF-reg/outlook_browser_register.py
```

验证结果：命令执行无错误。

对目标的影响：

- 后续成功样本采集可以开启 `OUTLOOK_HSPROTECT_JS_PATCH=1` 做静态 JS 落盘，但不会再因为 route/fulfill 改变 HSProtect 资源加载路径。
- 若后续仍出现风控失败，可以把原因从“patched JS 注入污染”与“route/fulfill 污染”中剥离出去，继续对比 collector payload、cookie/token、IP/指纹和 Microsoft risk 链。

## 11. collector POST body 构造器：从 `tf.payload` 到完整 `application/x-www-form-urlencoded`

本节目标：不再只验证 collector 请求里的 `payload` 字段，而是重建完整 collector POST body，并与 runtime `post_data` 做字符串级对比。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_human_collector_request.mjs`

验证命令：

```bash
node --check tools/build_human_collector_request.mjs
node tools/build_human_collector_request.mjs \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl \
  output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl \
  output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl
```

命令输出：

```json
[
  {
    "trace": "output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl",
    "jsonPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json",
    "mdPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.md",
    "requestCount": 4,
    "exactBodyMatches": 4,
    "payloadMatches": 4,
    "pcMatches": 4
  },
  {
    "trace": "output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl",
    "jsonPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.json",
    "mdPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.md",
    "requestCount": 4,
    "exactBodyMatches": 4,
    "payloadMatches": 4,
    "pcMatches": 4
  },
  {
    "trace": "output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl",
    "jsonPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.json",
    "mdPath": "/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.md",
    "requestCount": 4,
    "exactBodyMatches": 4,
    "payloadMatches": 4,
    "pcMatches": 4
  }
]
```

### 11.1 静态 JS 依据

`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4807-4852` 证明 `tf(t,e)` 构造 collector form 参数：

- line 4826-4828：计算 `f = Li()` 和 `h = Jt(ut(t), [po(), tag, ft].join(":"))`。
- line 4828-4835：构造 `d = {vid, tag, appID, cu, cs, pc}`。
- line 4836：`v = Vs(t, d)`，生成 `payload`。
- line 4837：form 参数顺序为 `payload, appId, tag, uuid, ft, seq, en`。
- line 4839-4852：按条件追加 `cs, pc, sid/p1, vid, cts/rsc` 等可选参数。

### 11.2 完整 body 字符串匹配证据

`hcxwyrtiudbg_1780949301`：

- 输出：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.md`
- 4 个 collector POST 均 `body=true`、`payload=true`、`pc=true`、`appId/tag/uuid=true`。

表格证据：

```text
| idx | req line | tf line | body | payload | pc | appId | tag | uuid | seq | ft |
| 0 | 27 | 32 | true | true | true | true | true | true | 0 | 369 |
| 1 | 82 | 83 | true | true | true | true | true | true | 1 | 369 |
| 2 | 109 | 114 | true | true | true | true | true | true | 2 | 369 |
| 3 | 135 | 138 | true | true | true | true | true | true | 3 | 369 |
```

`whsnxy8ag5ji_1781017142`：

- 输出：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.md`
- 4 个 collector POST 均完整 body 字符串匹配。

`i294e72kliud_1781017380`：

- 输出：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.md`
- 4 个 collector POST 均完整 body 字符串匹配。

### 11.3 marker 逆向证据

`hcxwyrtiudbg_1780949301` 的原始 hook 没有记录 `qi/marker` 字段。第一次运行构造器时，第 1 个请求匹配，但后 3 个请求 `pc=true`、`payload=false`，首个差异集中在 `Vs` 插入字符位置。重新用 runtime observed payload 反向抽取 marker 后，4 个 body 全部匹配。

marker 来源证据：

```text
- idx=0 reqLine=27 tfLine=32 source=payload.inverse marker=G^S}DNK8DNa>D`K}GK77
- idx=1 reqLine=82 tfLine=83 source=payload.inverse marker=G^i>GNa:E^GrDN_?EK77
- idx=2 reqLine=109 tfLine=114 source=payload.inverse marker=G^i>GNa:E^GrDN_?EK77
- idx=3 reqLine=135 tfLine=138 source=payload.inverse marker=G^i>GNa:E^GrDN_?EK77
```

这证明：

- `ut(activity)`、`Jt(...)->pc`、`Vs(activity, meta)->payload` 已可离线复算到完整 POST body 字符串级一致；
- marker 不是所有请求都能用固定 `Xs(118)` 得到；当 hook 没记录 marker 时，可以从 observed payload 与 base serialized 反向抽取；
- 后续纯协议实时构造还必须继续追 marker 的真实运行时来源，而不能把 `payload.inverse` 当成端到端生成能力。

### 11.4 结论边界

已证实：

- 3 个带 `tf.payload` 观测的样本共 12 个 collector POST body 可离线重建到字符串级一致。
- 其中 `whsnxy/i294` 使用 hook 中记录的 marker/qi 即可匹配。
- `hcx` 需要用 observed payload 反推 marker 才能匹配，说明 marker 来源仍是纯协议生成链的关键缺口。

仍未完成：

- `cs/sid/p1/vid/cts/rsc` 目前在完整 body 构造中仍取自 runtime request；虽然 body 可重建，但这些可选参数的生产函数还未完全独立实现。
- marker 的实时生成源还未独立证明。
- 还没有主动发送纯协议 collector request 并得到服务端成功 handler `oIIoIooo|0`。

## 12. collector optional fields 独立状态验证：`cs/sid/vid/cts/rsc/p1`

本节目标：把第 11 节里仍标为“取自 runtime request”的 optional fields，拆成可由前序 collector response 状态独立推出的字段，并逐项与后续 collector POST 对比。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/validate_collector_request_state.py`

验证命令：

```bash
python3 -m py_compile tools/validate_collector_request_state.py
python3 tools/validate_collector_request_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.json
python3 tools/validate_collector_request_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.json \
  output/protocol_reverse/collector_decode/collector_decode_whsnxy8ag5ji_1781017142.json
python3 tools/validate_collector_request_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.json \
  output/protocol_reverse/collector_decode/collector_decode_i294e72kliud_1781017380.json
```

命令输出摘要：

```json
{
  "hcxwyrtiudbg_1780949301": {
    "requestCount": 4,
    "fieldMatches": 20,
    "fieldMismatches": 0,
    "p1Matches": 4,
    "p1Gaps": 0
  },
  "whsnxy8ag5ji_1781017142": {
    "requestCount": 4,
    "fieldMatches": 20,
    "fieldMismatches": 0,
    "p1Matches": 4,
    "p1Gaps": 0
  },
  "i294e72kliud_1781017380": {
    "requestCount": 4,
    "fieldMatches": 20,
    "fieldMismatches": 0,
    "p1Matches": 4,
    "p1Gaps": 0
  }
}
```

输出文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_state/collector_request_state_validation_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_state/collector_request_state_validation_whsnxy8ag5ji_1781017142.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_state/collector_request_state_validation_i294e72kliud_1781017380.md`

`hcxwyrtiudbg_1780949301` 明细表：

```text
| idx | req line | applied collector lines | cs | sid | vid | cts | rsc | p1 |
|---:|---:|---|---|---|---|---|---|---|
| 0 | 27 |  | true | true | true | true | true | true |
| 1 | 82 | 33 | true | true | true | true | true | true |
| 2 | 109 | 86 | true | true | true | true | true | true |
| 3 | 135 | 115 | true | true | true | true | true | true |
```

### 12.1 字段来源与静态证据

- `cs`：来自 decoded handler `IoIIII` 写入状态 `Yo`。
  - 静态证据：`main.beautified.js:2666-2667`，`Li()` 返回 `Yo`。
  - 静态证据：`main.beautified.js:4482-4484`，`IoIIII(t)` 设置 `Yo=t`。
  - 使用点：`main.beautified.js:4826` 与 `4839`。

- `sid`：来自 decoded handler `IIoIIo` 写入 sid，再拼接 `Kl(Qi())`。
  - 静态证据：`main.beautified.js:1917-1921`，`Vi()` 返回 sid。
  - 静态证据：`main.beautified.js:2675-2677`，`Qi()` 返回 `Jo`。
  - 静态证据：`main.beautified.js:4797-4802`，`Kl(t)` 把字符编码为 `%uDB40%uDDxx` 对应的 Unicode tag 字符。
  - 使用点：`main.beautified.js:4840-4842`，`sid=(g || po()) + Kl(Qi())`。
  - 实现修正：Python 代理函数应使用 `U+E0100 + ord(ch)`；验证中已用实际 observed sid 校正。

- `vid`：来自 decoded handler `IooIoo`。
  - 静态证据：`main.beautified.js:426-428`，`Rt(t)` 设置 `mt`。
  - 静态证据：`main.beautified.js:4404-4411`，`IooIoo` 设置 `_pxvid` 与相关状态。
  - 使用点：`main.beautified.js:4844`，`Ct()` 作为 `vid`。

- `cts`：来自 decoded handler `oIIooIIo` 写入 `Fo`。
  - 静态证据：`main.beautified.js:1901-1903`，`Bi(t,e,n)` 设置 `Fo=t` 并写 `pxcts`。
  - 静态证据：`main.beautified.js:4523-4525`，`oIIooIIo` 调用 `Bi(t,e)`。
  - 使用点：`main.beautified.js:4850`，`Fo && p.push(Br + Fo)`。

- `rsc`：来自发送计数器。
  - 静态证据：`main.beautified.js:8423-8425`，`Fv(t)` 追加 `&rsc=++wv`。
  - 三个样本中第 1-4 个 collector POST 分别验证为 `rsc=1/2/3/4`。

- `p1`：当前样本中来自 iframe `session_id`，等于 `window._pxParam1` 对应值。
  - 静态证据：`main.beautified.js:2640-2648`，`Gi(e)` 从 `pxParams` 或 `window[<appPrefix>_pxParam1]` 提取 `p1`。
  - 静态证据：`main.beautified.js:8602-8611`，`e[hn]()` 把 `np.params` 编码为 form 参数。
  - 运行证据：`output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:13` 的 iframe href 包含 `session_id=19c154a1-0d0e-6906-9593-618f309a23de`。
  - 运行证据：`output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:31-32` 的 `tf.payload` activity URL 仍包含同一 `session_id`。
  - 请求证据：`output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json` 的 4 个 POST 中 `p1` 均为 `19c154a1-0d0e-6906-9593-618f309a23de`。
  - 另外两个样本同样成立：`whsnxy8ag5ji` 的 `p1=c1f41028-c6ca-a551-0c73-30df3bae0224`，`i294e72kliud` 的 `p1=7c5c8650-b8cf-174e-c774-75543e1729b9`。

### 12.2 本节结论边界

已证实：

- 对 3 个样本共 12 个 collector POST，请求中的 `cs/sid/vid/cts/rsc/p1` 均可由前序 decoded collector response、matched `tf.payload` activity URL 和静态 JS 规则推出。
- 这把第 11 节的 optional fields 从“整体复用 runtime request”推进为“字段级可独立验证”。

仍未完成：

- `payload` 的 marker 在 `hcx` 样本仍依赖 `payload.inverse`，未完全由实时 `Jo/Qi` producer 独立生成。
- 还没有主动发起新的纯协议 collector POST，并获得服务端可接受的成功 handler `oIIoIooo|0`。
- 因此目标仍未完成，下一步要把 collector POST 的实时发送、response 解码、状态推进和 Microsoft `risk/verify` 串成端到端 PoC。

## 13. marker/Qi 状态验证：消除 `payload.inverse` 依赖

本节目标：验证 collector payload 的 marker 不再依赖 observed payload 反推，而是由静态 JS 与前序 decoded collector response 状态推出。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/validate_collector_marker_state.py`

同时更新：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_human_collector_request.mjs`

更新后的构造器优先使用 decoded collector response 中的 `oIIoIoII` handler 写入的 `Jo`，按静态规则生成 marker；只有没有 decode material 时才回退 hook/inverse。

验证命令：

```bash
node --check tools/build_human_collector_request.mjs
python3 -m py_compile tools/validate_collector_marker_state.py
node tools/build_human_collector_request.mjs \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl \
  output/outlook_browser/js_internal_trace_whsnxy8ag5ji_1781017142.jsonl \
  output/outlook_browser/js_internal_trace_i294e72kliud_1781017380.jsonl
python3 tools/validate_collector_marker_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.json
python3 tools/validate_collector_marker_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.json \
  output/protocol_reverse/collector_decode/collector_decode_whsnxy8ag5ji_1781017142.json
python3 tools/validate_collector_marker_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.json \
  output/protocol_reverse/collector_decode/collector_decode_i294e72kliud_1781017380.json
```

验证结果：

```json
{
  "hcxwyrtiudbg_1780949301": {"requestCount": 4, "matches": 4, "mismatches": 0, "fallbackCount": 1},
  "whsnxy8ag5ji_1781017142": {"requestCount": 4, "matches": 4, "mismatches": 0, "fallbackCount": 1},
  "i294e72kliud_1781017380": {"requestCount": 4, "matches": 4, "mismatches": 0, "fallbackCount": 1}
}
```

输出文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_marker_state/collector_marker_state_validation_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_marker_state/collector_marker_state_validation_whsnxy8ag5ji_1781017142.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_marker_state/collector_marker_state_validation_i294e72kliud_1781017380.md`

`hcxwyrtiudbg_1780949301` 关键表：

```text
| idx | req line | tf line | applied collector lines | qi | observed source | match | marker |
|---:|---:|---:|---|---|---|---|---|
| 0 | 27 | 32 |  | 1604064986000 | payload.inverse | True | `G^S}DNK8DNa>D`K}GK77` |
| 1 | 82 | 83 | 33 | 1780949314598 | payload.inverse | True | `G^i>GNa:E^GrDN_?EK77` |
| 2 | 109 | 114 | 86 | 1780949314598 | payload.inverse | True | `G^i>GNa:E^GrDN_?EK77` |
| 3 | 135 | 138 | 115 | 1780949314598 | payload.inverse | True | `G^i>GNa:E^GrDN_?EK77` |
```

注意：表中 `observed source=payload.inverse` 是旧 request_build 里记录的观测来源；更新后的 `build_human_collector_request.mjs` 已重新生成 request_build，marker sources 已变为：

```text
- idx=0 source=static.Xs118 marker=G^S}DNK8DNa>D`K}GK77
- idx=1 source=collector_state.Jo marker=G^i>GNa:E^GrDN_?EK77
- idx=2 source=collector_state.Jo marker=G^i>GNa:E^GrDN_?EK77
- idx=3 source=collector_state.Jo marker=G^i>GNa:E^GrDN_?EK77
```

### 13.1 静态证据

- `main.beautified.js:3566`：`Vs` marker 路径使用 `ne(J(Qi() || Xs(118)), 10)`。
- `main.beautified.js:2675-2677`：`Qi()` 返回 `Jo`。
- `main.beautified.js:4486-4488`：collector handler `oIIoIoII` 映射到 `Yl`。
- `main.beautified.js:4701-4702`：`Yl(t)` 设置 `Jo=t`。

### 13.2 直接计算证据

本地计算：

```text
marker = xor10(base64(qi))
```

样本值：

```text
qi=1604064986000 -> G^S}DNK8DNa>D`K}GK77
qi=1780949314598 -> G^i>GNa:E^GrDN_?EK77
qi=1781017165326 -> G^i>G^KrDpO8D^GsDm77
qi=1781017400980 -> G^i>G^KrDp[}GNa>GK77
```

这些值分别与 `hcx/whsnxy/i294` 的 collector payload marker 匹配。

### 13.3 本节结论边界

已证实：

- 对 3 个样本共 12 个 collector POST，marker 可由 `static.Xs118` 或 decoded collector response 中的 `oIIoIoII -> Jo -> Qi()` 生成。
- `build_human_collector_request.mjs` 已使用该路径重建完整 POST body，3 个样本仍全部 `exactBodyMatches=4/4`。
- 第 11 节中 `hcx` 依赖 `payload.inverse` 的缺口已被状态验证替代。

仍未完成：

- 还没有在无浏览器的新会话里主动发 collector POST 并获得服务端接受的成功 handler `oIIoIooo|0`。
- 还没有端到端纯协议把 collector response 推进到 Microsoft `risk/verify state=continue`。

## 14. 2026-06-10 00:18 勘误：`OUTLOOK_HSPROTECT_JS_PATCH=1` 仍可能叠加无条件 page hook 污染

用户反馈：`OUTLOOK_HSPROTECT_JS_PATCH=1` 下走到风控逻辑，怀疑注入脚本被识别。

### 14.1 代码证据

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1510-1557`：当前 `OUTLOOK_HSPROTECT_JS_PATCH=1` 且未设置 `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1` 时，代码只安装 `ctx.on("response", response_handler)`，用于落盘 HSProtect JS；不会注册 route，不会 `route.fetch()`，不会 `route.fulfill()`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:875-1000`：`_install_js_internal_trace()` 会通过 `page.add_init_script(...)` 注入 hook，覆盖/包装 `window.postMessage`、`EventTarget.prototype.addEventListener`、`EventTarget.prototype.dispatchEvent`、`MessageChannel` 等浏览器对象，并输出 `__OUTLOOK_JS_INTERNAL_TRACE__`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:3616-3617` 的旧逻辑：`_install_runtime_trace(...)` 后无条件调用 `_install_js_internal_trace(...)`。这意味着即使 HSProtect JS patch 已改成 capture-only，页面仍存在无条件 page init hook。

因此更精确的结论是：

- `OUTLOOK_HSPROTECT_JS_PATCH=1` 本身在当前代码里不再返回 patched HSProtect JS；
- 但浏览器注册流程旧代码仍无条件注入 JS internal trace hook；
- 如果本轮被识别，证据支持“page hook 污染运行环境”这个原因，不能只归因于 HSProtect JS patch 开关。

### 14.2 修正

修改文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`

修正内容：

- 新增 `OUTLOOK_JS_INTERNAL_TRACE=1` 显式开关；
- 默认不再调用 `_install_js_internal_trace()`；
- 默认只保留 Playwright 层 runtime trace；
- 需要 JS 内部调用栈时，必须显式设置 `OUTLOOK_JS_INTERNAL_TRACE=1`，并且该模式只能用于观测/失败样本分析，不能作为干净成功样本采集方式。

修改后的关键语义：

```text
OUTLOOK_HSPROTECT_JS_PATCH=1
  -> 只落盘 HSProtect source/patched/meta；不 route/fulfill；不等于 page hook。

OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1
  -> 显式启用 patched HSProtect JS fulfill；污染性强，只用于失败实验。

OUTLOOK_JS_INTERNAL_TRACE=1
  -> 显式启用 page.add_init_script hook；污染性强，只用于运行时函数级观测。
```

验证命令：

```bash
python3 -m py_compile CTF-reg/outlook_browser_register.py
```

验证结果：命令执行无错误。

### 14.3 对后续采样的要求

干净成功样本采集命令中不得设置：

- `OUTLOOK_HSPROTECT_JS_PATCH_APPLY=1`
- `OUTLOOK_JS_INTERNAL_TRACE=1`

若只想拉取静态 JS 继续反混淆，可以设置：

- `OUTLOOK_HSPROTECT_JS_PATCH=1`

但这只应被解释为静态资源落盘，不应再期望得到 JS 内部调用栈。

## 15. 2026-06-10 00:23 collector HTTP replay 材料审计

本节目标：把 collector POST 从“body 可重建”推进到“HTTP 请求材料可审计”。该步骤仍不主动请求远端服务，只从 runtime trace、request build、collector state validation 中提取可重放材料，并明确剩余缺口。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/extract_collector_replay_material.py`

输入材料：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.json`
- 对应的 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_state/collector_request_state_validation_*.json`
- 对应的 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_*.jsonl`

验证命令：

```bash
python3 -m py_compile tools/extract_collector_replay_material.py
python3 tools/extract_collector_replay_material.py output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json
python3 tools/extract_collector_replay_material.py output/protocol_reverse/collector_request_build/collector_request_build_whsnxy8ag5ji_1781017142.json
python3 tools/extract_collector_replay_material.py output/protocol_reverse/collector_request_build/collector_request_build_i294e72kliud_1781017380.json
```

输出文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_replay_material/collector_replay_material_hcxwyrtiudbg_1780949301.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_replay_material/collector_replay_material_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_replay_material/collector_replay_material_whsnxy8ag5ji_1781017142.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_replay_material/collector_replay_material_whsnxy8ag5ji_1781017142.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_replay_material/collector_replay_material_i294e72kliud_1781017380.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_replay_material/collector_replay_material_i294e72kliud_1781017380.md`

三组样本结果一致：

```json
{
  "requestCount": 4,
  "bodyExactMatches": 4,
  "contentLengthMatches": 4,
  "runtimeRequestsWithHeaders": 4,
  "runtimeResponsesMatched": 4,
  "stateValidationLoaded": true
}
```

以 `hcxwyrtiudbg_1780949301` 为例：

```text
| idx | req line | resp line | status | body exact | body bytes | content-length ok | fields | headers |
|---:|---:|---:|---:|---|---:|---|---:|---:|
| 0 | 27 | 30 | 200 | True | 754 | True | 10 | 14 |
| 1 | 82 | 83 | 200 | True | 9025 | True | 14 | 14 |
| 2 | 109 | 110 | 200 | True | 6913 | True | 14 | 14 |
| 3 | 135 | 136 | 200 | True | 10053 | True | 14 | 14 |
```

### 15.1 已可追溯的 HTTP body 字段

审计器把每个 form 字段标为可追溯来源：

- `payload`：由 `tools/build_human_collector_request.mjs` 使用 `tf activities + Vs + marker state` 重建。
- `appId`：`PXzC5j78di`。
- `tag`：`YjIYfyxJHRR9`。
- `uuid`：来自 `tf.payload` 的 runtime meta `cu`。
- `ft`：`369`。
- `seq`：当前仍来自 observed collector sequence。
- `en`：静态值 `NTA`，已验证。
- `pc`：由 `Jt(ut(activities), cu:tag:ft)` 重建。
- `cs`：由上一轮 collector handler `IoIIII -> Yo` 验证。
- `sid`：由上一轮 collector handler `IIoIIo + Kl(oIIoIoII -> Jo)` 验证。
- `vid`：由上一轮 collector handler `IooIoo -> _pxvid` 验证。
- `cts`：由上一轮 collector handler `oIIooIIo -> Fo` 验证。
- `p1`：由 iframe `session_id` / `_pxParam1` 验证。
- `rsc`：递增 request counter，已验证。

### 15.2 已可追溯的 HTTP headers

runtime trace 中每个 collector POST 均有完整 headers。审计器验证：

- `host` 可从 URL host 派生，匹配 runtime。
- `content-length` 可从 UTF-8 body byte length 派生，三组样本 12 个 POST 均匹配。
- `content-type=application/x-www-form-urlencoded`，匹配 runtime。
- `origin=https://iframe.hsprotect.net`，匹配 runtime。
- `referer=https://iframe.hsprotect.net/`，匹配 runtime。
- `accept=*/*`、`sec-fetch-dest=empty`、`sec-fetch-mode=cors`、`sec-fetch-site=same-site` 在样本中稳定出现。

保留为 runtime/profile/transport 材料的 headers：

- `user-agent`
- `accept-language`
- `accept-encoding`
- `proxy-authorization`
- `connection`

这些值已完整落盘，未脱敏，但还不能声称已由纯协议生成器独立产生。

### 15.3 本节结论边界

已证实：

- 对 3 个样本共 12 个 collector POST，完整 body 与 runtime 字符串一致；
- 对 3 个样本共 12 个 collector POST，`content-length` 与重建 body 的 UTF-8 字节数一致；
- runtime request headers 和 response 匹配关系已落盘；
- body 字段来源已按静态 JS、runtime tf、decoded collector state、request state validation 分类。

仍未完成：

- 该审计不证明新会话里直接发送 collector POST 会被服务端接受；
- JSONL headers 不包含 TLS/HTTP2/client transport fingerprint；
- UA/locale/proxy headers 仍是 runtime/profile 材料；
- 还没有在新纯协议会话中生成 collector success handler `oIIoIooo|0`；
- 还没有把新生成的 collector response 推进到 Microsoft `risk/verify state=continue`。

## 16. 2026-06-10 00:32 live collector probe：纯 HTTP 第 0 包可被接受，后续状态链仍缺失

本节目标：从离线材料审计推进到真实 collector HTTP POST 探测。该步骤不使用浏览器/Camoufox/鼠标/打码，只使用已有 request build material 通过 Python stdlib HTTPS 发送，并对 live response 直接执行 collector response 解码。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/probe_human_collector_live.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_body_from_live_state.py`

验证命令：

```bash
python3 -m py_compile tools/probe_human_collector_live.py tools/build_collector_body_from_live_state.py
```

### 16.1 纯 HTTP collector idx=0

输入：

- request build：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json`
- request index：`0`

命令：

```bash
python3 tools/probe_human_collector_live.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  --index 0 --send --timeout 30
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022473.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022473.md`

结果：

```json
{
  "sent": true,
  "status": 200,
  "mode": "json-ob-encoded",
  "partCount": 15,
  "handlers": [
    "IoooII",
    "IoIoIo",
    "IIoIIo",
    "IoIIIo",
    "IIoIoI",
    "oIIoIoII",
    "ooooII",
    "oIIoIoIo",
    "oIIooIIo",
    "IoIIII",
    "IooIoo",
    "IIooII",
    "IIooII",
    "oIooII",
    "oIIoIIoo"
  ],
  "hasPx3": true,
  "hasPxde": true,
  "hasSuccessHandler": false
}
```

关键 live state：

```text
Jo=1781022474607
sidBase=2ad4c116-6420-11f1-827b-4d8e1d997469
cs=43520b901923918ff999e0987e1fe9836c2b605a6eb6cafea6630c27457dfb5b
vid=2ad4bb61-6420-11f1-827b-df48e6e8f7a9
cts=2ad4c336-6420-11f1-827b-4d8e1d997469
```

结论：纯 HTTP 第 0 个 collector POST 被服务端接受，返回 `200`，且响应可用本地 decoder 解出 `_px3/_pxde/_pxvid` 相关 handler。这是第一个 live 纯协议证据。

### 16.2 使用 live idx=0 state 构造 collector idx=1

工具：

```bash
python3 tools/build_collector_body_from_live_state.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022473.json \
  --index 1
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_state_body/collector_live_state_body_hcxwyrtiudbg_1780949301_idx1.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_state_body/collector_live_state_body_hcxwyrtiudbg_1780949301_idx1.md`

构造结果：

```text
oldMarker=G^i>GNa:E^GrDN_?EK77
newMarker=G^i>G^KsG`[9DNS}D}77
bodyLenBytes=9225
```

替换字段：

- `payload`：保留 runtime idx1 activities base，替换为 live `Jo` 生成的新 marker；
- `cs`：live `IoIIII -> Yo`；
- `sid`：live `IIoIIo + Kl(oIIoIoII -> Jo)`；
- `vid`：live `IooIoo -> _pxvid`；
- `cts`：live `oIIooIIo -> Fo`。

### 16.3 纯 HTTP collector idx=1 结果

命令：

```bash
python3 tools/probe_human_collector_live.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  --index 1 \
  --body-override-json output/protocol_reverse/collector_live_state_body/collector_live_state_body_hcxwyrtiudbg_1780949301_idx1.json \
  --send --timeout 30
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx1_1781022665.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx1_1781022665.md`

结果：

```json
{
  "sent": true,
  "status": 200,
  "bodyText": "{\"do\":[]}\n",
  "mode": "json-direct",
  "partCount": 0,
  "handlers": []
}
```

为了排除 idx0 到 idx1 间隔过长，做了一次快速链式重试：

```text
P0=/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022700.json
B1=/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_state_body/collector_live_state_body_hcxwyrtiudbg_1780949301_idx1.json
P1=/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx1_1781022700.json
```

快速链式结果仍为：

```json
{
  "status": 200,
  "mode": "json-direct",
  "decoded": [],
  "parts": [],
  "handlers": []
}
```

### 16.4 本节结论边界

已证实：

- 纯 HTTP 第 0 个 collector POST 可被服务端接受；
- 第 0 个 live response 可由本地 decoder 解出 15 个 handler；
- live response 中的 `Jo/sidBase/cs/vid/cts` 可被提取并用于构造 idx1 body；
- idx1 HTTP 层也返回 `200`，但业务 body 是 `{"do":[]}`，不是 success 或 token handler；
- 快速链式重试仍为 `{"do":[]}`，因此“idx0 到 idx1 间隔过长”不是当前主要解释。

仍未完成：

- idx1 的 payload activities 目前仍来自旧 runtime 样本；虽然 state 字段已替换为 live state，但这可能不足以让服务端继续状态机；
- 还没有纯协议生成 idx1 所需的 fresh activities/telemetry；
- 还没有 live 生成 `oIIoIooo|0`；
- 还没有用 live `_px3/_pxde/_pxvid` 推进 Microsoft `risk/verify state=continue`。

## 17. 2026-06-10 00:38 idx1 activities stale 字段审计与最小 patch 验证

第 16 节中，idx1 使用 live state 替换 `cs/sid/vid/cts/marker` 后仍返回 `{"do":[]}`。本节继续追证据：审计 idx1 `tf activities` 中仍来自旧 runtime 的动态字段，并做最小 patch 验证。

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/audit_collector_activities_dynamic_fields.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_collector_body_with_activity_patch.mjs`

验证命令：

```bash
python3 -m py_compile tools/audit_collector_activities_dynamic_fields.py
node --check tools/build_collector_body_with_activity_patch.mjs
```

### 17.1 activities 动态字段审计

命令：

```bash
python3 tools/audit_collector_activities_dynamic_fields.py \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  --live-state output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022700.json
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_dynamic/collector_activity_dynamic_audit_hcxwyrtiudbg_1780949301.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_dynamic/collector_activity_dynamic_audit_hcxwyrtiudbg_1780949301.md`

结果摘要：

```json
{
  "requestCount": 4,
  "dynamicFieldCount": 66,
  "idx1DynamicFields": 30
}
```

idx1 中被标记的关键动态字段包括：

- `d.cR1LFzd8RSQ=`：`1780949314598`，与旧 runtime 的 `Jo` 同值；
- `d.IU0bR2crHnA=`：`1780949313223`，旧 epoch ms；
- `d.QS07ZwRKPlU=`：`1780949315522`，旧 epoch ms；
- `d.MDxKNnZaRAY=`：`1780949314808`，旧 epoch ms；
- `d.SlpwEAw5eSc=`：旧 iframe URL，包含旧 `session_id=19c154a1-0d0e-6906-9593-618f309a23de`；
- `d.FUFvS1Mga38=`：旧 `cu=d347af50-6375-11f1-b31a-c1d900f88e04`；
- 多个 hex/base64ish 指纹摘要字段，例如 `fd132069`、`65d826e0`、`9f4ad436c590825b763613cc0227fb6e`、`Uh3uWG5U...`。

证据边界：这些字段只是“动态/stale 候选”，不是全部都已证明必须替换。可直接证明并可安全实验的最小集合是 epoch ms 与旧 `Jo`。

### 17.2 最小 activities patch

patch 策略：

```text
replace epoch_ms with nowMs
replace old Jo literal with live Jo
replace form cs/sid/vid/cts with live state
keep p1/session_id unchanged
```

命令：

```bash
node tools/build_collector_body_with_activity_patch.mjs \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022700.json \
  1
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx1.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx1.md`

构造结果：

```json
{
  "bodyLenBytes": 9225,
  "marker": "G^i>G^KsG`i}GN_>E[77",
  "pc": "2488674269328091"
}
```

### 17.3 live probe 对照

未 patch activities 的 idx1：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx1_1781022700.json`

结果：

```json
{
  "status": 200,
  "mode": "json-direct",
  "parts": 0,
  "handlers": []
}
```

patch activities 后的 idx1：

命令：

```bash
python3 tools/probe_human_collector_live.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  --index 1 \
  --body-override-json output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx1.json \
  --send --timeout 30
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx1_1781023070.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx1_1781023070.md`

结果：

```json
{
  "status": 200,
  "mode": "json-ob-encoded",
  "parts": 4,
  "handlers": ["IoooII", "IoIoIo", "IoIIIo", "oIIoIIoo"],
  "hasPx3": true,
  "hasPxde": true,
  "hasSuccessHandler": false
}
```

关键对照：

```text
unpatched idx1 bodySha=66fe98a124fd13ba46d9c4f3ebab28d3a3ed596e1d70de7f6b173ad3621cda41 -> {"do":[]}
patched   idx1 bodySha=b189f8371dca4b8e255533a48f71d2fd33327cd2ac1702b695d1c46318815e61 -> 4 decoded handlers
```

### 17.4 本节结论边界

已证实：

- idx1 返回 `{"do":[]}` 不是 HTTP 层不通；
- idx1 stale activities 是导致空业务响应的关键因素之一；
- 只替换 epoch ms 与旧 `Jo` 并重算 payload/pc，就能让 idx1 从 `do=[]` 变为可解码 4 handler；
- 这进一步证明下一步应追 `activities` 生成链，而不是继续盲调 headers。

仍未完成：

- 当前 patch 只恢复到 4 handler，未得到 `oIIoIooo|0`；
- idx1 中仍有多个 hash/base64ish 指纹摘要来自旧 runtime，尚未确定生成算法和依赖；
- `p1/session_id/cu` 仍保持旧值，没有证据支持直接替换；
- 后续 idx2/idx3/challenge activities 还没有纯协议生成。

## 18. 2026-06-10 00:42 idx2/idx3 最小 activities patch 验证

第 17 节证明：idx1 只替换 epoch ms 与旧 `Jo`，并重算 payload/pc，就能从 `{"do":[]}` 推进到 4 个 decoded handler。本节继续用同一策略验证 idx2/idx3。

### 18.1 构造 idx2/idx3 patched body

命令：

```bash
node tools/build_collector_body_with_activity_patch.mjs \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022700.json \
  2

node tools/build_collector_body_with_activity_patch.mjs \
  output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx0_1781022700.json \
  3
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx2.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx2.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx3.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx3.md`

构造结果：

```text
idx1 bodyLenBytes=9225  bodySha=b189f8371dca4b8e255533a48f71d2fd33327cd2ac1702b695d1c46318815e61 pc=2488674269328091
idx2 bodyLenBytes=7075  bodySha=f0bc15bd28324c10d162f1d4dfd740714c63029c576b298c63c7a754f66ce121 pc=6818454206778209
idx3 bodyLenBytes=10323 bodySha=3c1f578bb363051591addd3fd79340eb86550e012da3a3184b78a5811a9850a6 pc=9707559609338220
```

### 18.2 live probe 结果

idx2 命令：

```bash
python3 tools/probe_human_collector_live.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  --index 2 \
  --body-override-json output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx2.json \
  --send --timeout 30
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx2_1781023281.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx2_1781023281.md`

idx3 命令：

```bash
python3 tools/probe_human_collector_live.py \
  output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.json \
  --index 3 \
  --body-override-json output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_hcxwyrtiudbg_1780949301_idx3.json \
  --send --timeout 30
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx3_1781023283.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_hcxwyrtiudbg_1780949301_idx3_1781023283.md`

三包结果对照：

```json
{
  "idx1": {
    "status": 200,
    "parts": 4,
    "handlers": ["IoooII", "IoIoIo", "IoIIIo", "oIIoIIoo"],
    "hasPx3": true,
    "hasPxde": true,
    "hasSuccessHandler": false
  },
  "idx2": {
    "status": 200,
    "parts": 4,
    "handlers": ["IoooII", "IoIoIo", "IoIIIo", "oIIoIIoo"],
    "hasPx3": true,
    "hasPxde": true,
    "hasSuccessHandler": false
  },
  "idx3": {
    "status": 200,
    "parts": 4,
    "handlers": ["IoooII", "IoIoIo", "IoIIIo", "oIIoIIoo"],
    "hasPx3": true,
    "hasPxde": true,
    "hasSuccessHandler": false
  }
}
```

### 18.3 本节结论边界

已证实：

- 同一最小 patch 策略可以让 idx1/idx2/idx3 都被服务端接受，并返回 `_px3/_pxde` token handler；
- idx2/idx3 不再是 HTTP 或基础 form 问题；
- 这些普通 fingerprint/telemetry 包即使被接受，也不会直接产生 `oIIoIooo|0`。

下一步依据：

- 在成功 trace `hcxwyrtiudbg_1780949301` 中，idx0-idx3 对应 tfLine `32/83/114/138`，都是 challenge 前普通 collector 包；
- 同一 trace 中后续还有 tfLine `197` 和 `223`：
  - tfLine `197` URL 包含 `&ch_ctx=1`，并包含 `_px3` 相关字段；
  - tfLine `223` 有 3 个 activities，包含 pointerdown/pointerup、captcha stack、按压/挑战相关字段；
- 因此继续追 `oIIoIooo|0` 应转向 challenge context activities，而不是继续重复 idx1-idx3 普通 fingerprint 包。

仍未完成：

- challenge context 的 tfLine `197/223` 还没有被抽成 request_build/live probe material；
- pointer/captcha activity 中的 POW、按压时序、captcha token 字段还未纯生成；
- 尚未 live 生成 `oIIoIooo|0`；
- 尚未推进到 Microsoft `risk/verify state=continue`。

## 19. challenge context `/b/c` 已抽取并完成 live probe

本节是对第 18 节“尚未完成”项的增量修正，只记录当前已验证事实。

### 19.1 `/b/c` 请求与 tf payload 的对应关系

样本：`hcxwyrtiudbg_1780949301`。

新增构建器：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_bc_collector_request_material.py`

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bc_collector_request_build/bc_collector_request_build_hcxwyrtiudbg_1780949301.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bc_collector_request_build/bc_collector_request_build_hcxwyrtiudbg_1780949301.md`

证据文件中的匹配表：

```text
idx 0 req line 199 tf line 197 payload true pc true appId true tag true uuid true seq 0 ft 369 body bytes 1897
idx 1 req line 233 tf line 223 payload true pc true appId true tag true uuid true seq 1 ft 369 body bytes 28049
```

含义边界：

- `runtime_trace_hcxwyrtiudbg_1780949301.jsonl:199` 是第一次 challenge context `POST https://collector-pxzc5j78di.hsprotect.net/b/c`；
- `runtime_trace_hcxwyrtiudbg_1780949301.jsonl:233` 是第二次 challenge context `POST https://collector-pxzc5j78di.hsprotect.net/b/c`；
- `js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:197` 与第一个 `/b/c` request body 的 `payload/pc/appId/tag/uuid/seq/ft` 全匹配；
- `js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:223` 与第二个 `/b/c` request body 的 `payload/pc/appId/tag/uuid/seq/ft` 全匹配；
- 这里证明的是“运行时请求材料可从 tf payload 精确抽取”，不是证明成功包已纯生成。

### 19.2 `/b/c` idx0 live probe：已复现 POW 下发包

构造体：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_bc_hcxwyrtiudbg_1780949301_idx0_1781023894.json`
- bodyLenBytes: `2089`
- pc: `6885478620081781`

live probe 输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.md`

结果：

```json
{
  "status": 200,
  "mode": "json-ob-encoded",
  "partCount": 18,
  "handlers": [
    "IoooII",
    "IoIoIo",
    "IoIIIo",
    "IIoIoI",
    "oIIoIoII",
    "ooooII",
    "oIIoIoIo",
    "IoIIII",
    "oIIooIoo",
    "IooIIo",
    "IooIoI",
    "IIooII",
    "IIooII",
    "IIooII",
    "IIooII",
    "IIooII",
    "oIooII",
    "oIIoIIoo"
  ],
  "hasPowResult": true,
  "hasSuccessHandler": false,
  "hasPx3": true,
  "hasPxde": true
}
```

live 返回的 POW 相关 handler：

```text
IooIIo|1|81b174098f8c821f5e6cd919aa47747908399bdc97ccf63eaacea0341818|dd43fb8a12ddc654b5ec1e9ce8f195b409d2099a5b74985d9f24bfc52ce3f6d6|18|false
IooIoI|1|82b0bdd0-6423-11f1-9f78-750422b636f3|1539|372a2475501c42f1b3cbe9181d8553b3efb730e568947607b4df1bd527f4c42f126f78e775bf7976691d4cd730f7aef9799212961f6b5c329edaa7e6b11a1b0d_==?9|2|NA
```

结论边界：

- 已证明纯 HTTP 可以让 challenge context `/b/c` 返回与运行时同类的 POW 下发 handler：`IooIIo` 和 `IooIoI`；
- 此包仍没有 `oIIoIooo|0`；
- 因此它是“POW 下发包”，不是“成功包”。

### 19.3 `/b/c` idx1 live probe：只复现 token 刷新包，未成功

构造体：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_activity_patch_body/collector_activity_patch_body_bc_hcxwyrtiudbg_1780949301_idx1_1781023895.json`
- bodyLenBytes: `28311`
- pc: `0846814213988177`

live probe 输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx1_1781023916.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx1_1781023916.md`

结果：

```json
{
  "status": 200,
  "mode": "json-ob-encoded",
  "partCount": 4,
  "handlers": ["IoooII", "IoIoIo", "IoIIIo", "oIIoIIoo"],
  "hasPowResult": false,
  "hasSuccessHandler": false,
  "hasPx3": true,
  "hasPxde": true
}
```

结论边界：

- 第二个 `/b/c` 包当前能被服务端接受；
- 返回内容只证明 `_px3/_pxde` 类 token 刷新；
- 未产生 `oIIoIooo|0`，所以未达到 HUMAN success。

### 19.4 与真实成功样本的 POW 链对照

样本：`ni109xdjp5zp_1780948211`。

已运行：

```bash
node tools/solve_human_pow.mjs output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow/pow_replay_ni109xdjp5zp_1780948211.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow/pow_replay_ni109xdjp5zp_1780948211.md`

关键证据：

1. collector decode 中的 POW seed 与成功 handler：

```text
collector_decode_ni109xdjp5zp_1780948211.json:
line 188 IooIIo|1|218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564|1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6|18|false
line 188 IooIoI|1|5bc17530-6373-11f1-b3b6-192fa993e3c2|6796|b78eabfb4f4a231aa3d4649efff95ae0e276bcf9761414a5841027f1153df7f9906856976185e69107e7838203c38cdef6f062c2598a397345fca0ab00cd5c77_>3>2|2|NA
line 302 oIIoIooo|0
```

2. Worker POW 范围与命中值：

```text
js_internal_trace_ni109xdjp5zp_1780948211.jsonl:
line 260 range 65537..131073 target=1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
line 261 range 196611..262144 target=1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
line 262 range 131074..196610 target=1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
line 263 range 0..65536 target=1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
line 272 pow.hit i=50239 value=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
line 273 worker.message data=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
```

3. 离线 POW 复算命中：

```text
pow_replay_ni109xdjp5zp_1780948211.md:
seedLine 188 rangeLine 263 from 0 to 65536
target 1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
solved i 50239
solved value 218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
matchesObserved true
```

4. 成功 handler 到 captcha succeeded 的调用栈：

```text
js_internal_trace_ni109xdjp5zp_1780948211.jsonl:
line 323 hsprotect.captcha.Ot.enter r=0 state=succeeded
stack: Ot -> Wc -> oIIoIooo -> jl -> om -> trigger -> fp -> xv/h.onload
line 324 hsprotect.captcha.zt.enter arg=succeeded
```

5. Microsoft 风控放行：

```text
runtime_trace_ni109xdjp5zp_1780948211.jsonl:
line 344 POST https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/api/v1.0/risk/verify
line 345 response status=200 body contains "state":"continue"
```

### 19.5 当前差距重新定义

第 18 节末尾四个未完成项中，当前状态更新如下：

已完成：

- challenge context 的 tfLine `197/223` 已抽成 `/b/c` request_build；
- `/b/c` idx0/idx1 已可 live probe；
- `/b/c` idx0 已复现 POW 下发 handler；
- POW 算法已经在 `ni109xdjp5zp_1780948211` 成功样本上离线复算并与 worker hit 完全一致。

仍未完成：

- 还没有把 live `/b/c` idx0 返回的 `IooIIo/IooIoI` 立即接入纯协议 POW 求解并生成下一包；
- 还没有证明纯协议构造的下一包能让 collector 返回 `oIIoIooo|0`；
- 还没有把纯协议得到的 `_px3/_pxde` 和 success 状态接入 Microsoft `risk/verify`，并得到 `state:"continue"`；
- 因此完整目标“完全纯协议解析 + 复现 HUMAN 成功包”仍未完成。

下一步必须围绕真实成功样本 `ni109xdjp5zp_1780948211` 与 live `/b/c` 的差异继续追：

1. 提取 `oIIoIooo|0` 前一包的 request body、cookies、headers、`pc/cs/sid/vid/cts/rsc`；
2. 将 live `/b/c` idx0 下发的 POW seed 用现有 `poi/sha256` 逻辑求解；
3. 在后续 activity 中定位 POW 解值进入哪个字段；
4. 生成纯协议“POW 解答包”并 live probe，目标是返回 `oIIoIooo|0`。

## 20. 当前状态

### 20.1 当前工作树证据

命令：

```bash
git status --short
```

当前相关变更：

```text
 M CTF-reg/outlook_browser_register.py
?? docs/pure-protocol-human-plan.md
?? tools/analyze_human_payload_chain.mjs
?? tools/audit_collector_activities_dynamic_fields.py
?? tools/build_bc_collector_request_material.py
?? tools/build_collector_body_from_live_state.py
?? tools/build_collector_body_with_activity_patch.mjs
?? tools/build_human_collector_request.mjs
?? tools/build_risk_verify_request.py
?? tools/decode_human_collector_response.mjs
?? tools/extract_collector_replay_material.py
?? tools/extract_risk_verify_material.py
?? tools/human_cookie_timeline.py
?? tools/human_trace_classifier.py
?? tools/map_human_collector_fields.py
?? tools/probe_human_collector_live.py
?? tools/replay_human_collector_state.py
?? tools/replay_human_vs_payload.mjs
?? tools/solve_human_pow.mjs
?? tools/validate_collector_marker_state.py
?? tools/validate_collector_request_state.py
```

已存在的关键输出目录：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow/`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify_build/`

### 20.2 已完成项与证据

#### 20.2.1 成功/失败 trace 分类器

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/human_trace_classifier.py`

文档证据：

- 本文第 2 节：分类规则以 `oIIoIooo|0 -> Ot(0) -> succeeded -> risk/verify state=continue -> CreateAccount redirectUrl` 为成功闭环。
- 本文第 7 节：分类器结果中成功样本有 `successEvents=1`，且 `oIIoIooo|0` 与 parent `succeeded` 对齐。

状态：完成离线分类能力。

#### 20.2.2 collector response 离线解码器

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_human_collector_response.mjs`

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_hcxwyrtiudbg_1780949301.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_decode/collector_decode_i294e72kliud_1781017380.json`

关键已解码事实：

```text
collector_decode_ni109xdjp5zp_1780948211.json:
line 188 IooIIo|...
line 188 IooIoI|...
line 302 oIIoIooo|0
```

状态：完成离线解码能力。

#### 20.2.3 collector request body 重建

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_human_collector_request.mjs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/validate_collector_request_state.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/validate_collector_marker_state.py`

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_build/collector_request_build_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_request_state/collector_request_state_validation_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_marker_state/collector_marker_state_validation_hcxwyrtiudbg_1780949301.md`

文档证据：

- 本文第 16 节：`bodyExactMatchInRuntime=True`。
- 本文第 17 节：`cs/sid/vid/cts/rsc/p1` 与 marker 状态校验通过。

状态：完成已有 runtime 普通 collector POST 的离线重建。

#### 20.2.4 challenge context `/b/c` request_build 与 live probe

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_bc_collector_request_material.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/probe_human_collector_live.py`

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bc_collector_request_build/bc_collector_request_build_hcxwyrtiudbg_1780949301.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx1_1781023916.md`

关键证据：

```text
idx 0 req line 199 tf line 197 payload true pc true appId true tag true uuid true seq 0 ft 369 body bytes 1897
idx 1 req line 233 tf line 223 payload true pc true appId true tag true uuid true seq 1 ft 369 body bytes 28049
```

live idx0 返回：

```text
handlers: IoooII, IoIoIo, IoIIIo, IIoIoI, oIIoIoII, ooooII, oIIoIoIo, IoIIII, oIIooIoo, IooIIo, IooIoI, IIooII, IIooII, IIooII, IIooII, IIooII, oIooII, oIIoIIoo
hasPowResult: true
hasSuccessHandler: false
```

状态：完成 `/b/c` POW 下发包的 live 复现；未完成 success 包。

#### 20.2.5 POW 离线复算

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/solve_human_pow.mjs`

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow/pow_replay_ni109xdjp5zp_1780948211.md`

关键证据：

```text
seedLine 188 rangeLine 263 from 0 to 65536
target 1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6
solved i 50239
solved value 218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
matchesObserved true
```

状态：完成成功样本 POW 的离线复算。

#### 20.2.6 `risk/verify` 请求体离线构造

工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/extract_risk_verify_material.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_risk_verify_request.py`

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify/risk_verify_material_ni109xdjp5zp_1780948211.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/risk_verify_build/risk_verify_build_ni109xdjp5zp_1780948211.md`

文档证据：

- 本文第 9 节：`initialJsonMatch=True`、`solutionJsonMatch=True`、`createContinuationMatch=True`。

状态：完成对已有成功 runtime 的离线请求体重建；未执行新的 live 放行重放。

### 20.3 未完成项与证据

未完成项不是推断，直接来自本文多处状态记录：

- 本文第 19.5 节：
  - “还没有把 live `/b/c` idx0 返回的 `IooIIo/IooIoI` 立即接入纯协议 POW 求解并生成下一包”；
  - “还没有证明纯协议构造的下一包能让 collector 返回 `oIIoIooo|0`”；
  - “还没有把纯协议得到的 `_px3/_pxde` 和 success 状态接入 Microsoft `risk/verify`，并得到 `state:"continue"`”。
- 本文第 20.2.4 节 live probe 证据显示 `hasSuccessHandler: false`。

因此，原目标仍未完成。

### 20.4 下一步执行计划（修正）

上一版这里写法不正确，和本文目标冲突。基于第 19.5 与第 20.3 节的未完成项，后续继续执行以下证据闭环：

1. 将 live `/b/c` idx0 返回的 `IooIIo/IooIoI` 固化为可复跑 POW 求解 artifact。
2. 对成功样本与 live 样本同时定位 POW 解答进入下一次 collector 请求的位置。
3. 生成纯协议“POW 解答包”，以 live probe 验证 collector 是否返回 `oIIoIooo|0`。
4. 若 collector 返回 success handler，再把同一会话内得到的 `_px3/_pxde/_pxvid` 与 success 状态接入 Microsoft `risk/verify`，验证是否得到 `state:"continue"`。
5. 每一步只记录有来源的值：本地 JS、运行时 hook、runtime trace、HAR、cookie 时间线、live probe response、离线重建输出；缺少证据时先补采集或补解析。

## 21. 本轮修正与新增证据：live POW 固化、成功样本 bundle payload 反解

### 21.1 修正文档目标偏差

第 20.4 节已修正为继续执行计划。验证命令：

```bash
rg -n "执行边界|不再继续|真实第三方|live 生成 HUMAN success|risk/verify live 放行" docs/pure-protocol-human-plan.md || true
```

结果：无输出。含义：本文已删除与目标冲突的边界表述。

### 21.2 live `/b/c` POW 下发结果已固化为可复跑 artifact

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/solve_collector_pow_from_response.mjs`

执行命令：

```bash
node tools/solve_collector_pow_from_response.mjs \
  output/protocol_reverse/collector_live_probe/collector_live_probe_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.json
```

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow_response/pow_response_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow_response/pow_response_bc_collector_request_build_hcxwyrtiudbg_1780949301_idx0_1781023909.md`

关键值来自上述 `.md`：

```text
raw: IooIIo|1|81b174098f8c821f5e6cd919aa47747908399bdc97ccf63eaacea0341818|dd43fb8a12ddc654b5ec1e9ce8f195b409d2099a5b74985d9f24bfc52ce3f6d6|18|false
salt: 8
prefixBase: 9
i: 58015
value: 81b174098f8c821f5e6cd919aa47747908399bdc97ccf63eaacea0341819e29f
matchesTarget: true
```

对照样本也已固化：

- 成功样本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow_response/pow_response_ni109xdjp5zp_1780948211.md`
  - `i=50239`
  - `value=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f`
  - `matchesTarget=true`
- 失败/运行样本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/pow_response/pow_response_hcxwyrtiudbg_1780949301.md`
  - `i=928639`
  - `value=72a53368f44cfbd9eb8e0c73469107a44a2c9d796ac6435e836e70f5a8ee2b7f`
  - `matchesTarget=true`

结论边界：现在能证明 `IooIIo` POW seed 可以离线求解；还不能仅凭这一点证明下一包一定返回 `oIIoIooo|0`。

### 21.3 成功样本中 POW 解答进入下一包的位置已定位到 `/assets/js/bundle` seq=2

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_bundle_payload_with_marker.py`

执行命令：

```bash
python3 tools/decode_bundle_payload_with_marker.py \
  output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl \
  output/protocol_reverse/collector_decode/collector_decode_ni109xdjp5zp_1780948211.json \
  --term 218e34c1 --term 50239 --term 1366f575
```

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bundle_payload_decode/bundle_payload_decode_ni109xdjp5zp_1780948211.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bundle_payload_decode/bundle_payload_decode_ni109xdjp5zp_1780948211.md`

关键表格来自上述 `.md`：

```text
req line 187 seq 0 payloadLen 1576  markerQi 1780948225978 markerMatch False jsonItems 1 contains <none>
req line 278 seq 1 payloadLen 9336  markerQi 1780948253699 markerMatch True  jsonItems 1 contains <none>
req line 308 seq 2 payloadLen 45424 markerQi 1780948253699 markerMatch True  jsonItems 5 contains 218e34c1
req line 309 seq 3 payloadLen 3512  markerQi 1780948253699 markerMatch True  jsonItems 1 contains <none>
```

同一成功样本的上下文证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:272`：`hsprotect.captcha.pow.hit`，`i=50239`，`value=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:273`：`hsprotect.captcha.worker.message`，`data=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:278`：紧随 worker message 后发送 `/assets/js/bundle` seq=1。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:308`：发送 `/assets/js/bundle` seq=2；反解后 payload 包含 `218e34c1...c43f`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:307-323`：collector 随后返回并调度 `oIIoIooo|0`。

结论：成功样本中，POW worker 解答值不是直接出现在 seq=1，而是在后续 `/assets/js/bundle` seq=2 的 payload 中出现；seq=2 后 collector 返回含 `oIIoIooo|0` 的 success handler。这个结论由 runtime trace、collector decode 与 bundle payload 反解三方交叉支撑。

### 21.4 当前仍缺的证据

还未完成：

1. 将 live `/b/c` idx0 的 POW 解答 `81b174...9e29f` 注入/构造成下一次 `/assets/js/bundle` 或等价 collector 请求。
2. 证明纯协议生成的下一包在 live collector 返回 `oIIoIooo|0`。
3. 证明纯协议获得的 success 状态能接入 Microsoft `risk/verify` 并返回 `state:"continue"`。

下一步应基于第 21.3 的反解结果，抽取 seq=2 payload 中包含 POW 解答的 activity 结构，和 live 样本对应 activity 结构做字段级替换/重建，而不是继续猜请求形态。

### 21.5 POW 解答在 seq=2 activity 内的精确字段

基于第 21.3 的反解工具，对 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:308` 的 `/assets/js/bundle` seq=2 payload 进行 JSON 路径扫描，得到精确位置：

```text
items: 5
ITEM 2 t=PX561 contains 218e34c1...
FOUND [2].d.OSkIb39DDA== 218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
```

证据来源：

- payload 反解结果：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bundle_payload_decode/bundle_payload_decode_ni109xdjp5zp_1780948211.json`
- 原始请求：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:308`
- POW 解答来源：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:272-273`
- 成功 handler 来源：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:307-323`

结论：成功样本的 POW 解答值进入 collector 下一阶段请求时，落在 `/assets/js/bundle` seq=2 payload 的 activity `t=PX561` 下，字段路径为 `[2].d.OSkIb39DDA==`。下一步要做的是提取 `PX561` activity 的完整字段语义与 live 样本对应结构，复现该字段和相关时间/事件数组，而不是只替换单个 POW 字符串。

### 21.6 `PX561` 成功样本与未成功样本字段级差异

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/extract_bundle_activity_matches.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/compare_px561_activity.py`

输出证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.md`

关键匹配表：

```text
req line 308 seq 2 markerMatch True items 5 activity index 2 activity type PX561 match path d.OSkIb39DDA== term 218e34c1
```

成功样本与三个未成功/POW 下发样本的 `PX561` 对比：

```text
success line=308 seq=2 fieldCount=92 powField=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
hcx line=223 fieldCount=74 state=succeeded hasPow=False pointerEvents=10 motion150=150 motion600=600 missing=20
 i294 line=223 fieldCount=74 state=succeeded hasPow=False pointerEvents=14 motion150=150 motion600=600 missing=20
whsnxy line=223 fieldCount=74 state=succeeded hasPow=False pointerEvents=10 motion150=150 motion600=600 missing=20
```

直接结论：未成功样本并不是没有 `PX561`，也不是 `state` 没到 `succeeded`；它们已经有 `PX561` 且 `fyNOZTpPQF4=succeeded`，但缺少成功样本里的 POW 解答字段 `OSkIb39DDA==`，并且总字段数少 20 个。

20 个 success-only 字段中，静态 `Yc(e,n)` 可解释的环境注入字段有 5 个：

```text
DXl3M0sUeQY=
FUFvS1MiYXs=
PAhGQnlsSXY=
VQEvCxNgIjA=
fg4ERDtuC3Y=
```

静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:2963-3010`：`Yc(e,n)` 构造 `PX561` 的 `d`，先写入基础环境字段，再将传入对象 `e` 的字段合并进 `C`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:2988-3001`：基础字段包括 `VGBuahICYlE=`, `KDRSPm1TWQg=`, `W0shQR0nJHc=`, `KVUTX285HW4=`, `DFg2Eko5PiQ=`, `JVEfW2A0G2A=`, `S3sxMQ0YNQo=`；在 `_r() && n === F(v)` 分支还会写入若干环境字段。

仍需追来源的 success-only 字段有 15 个：

```text
Czd6cU5Yfko=
EXFgN1QeZAA=
EXFgN1QeZQU=
Em4jaFcBJlg=
Ew9iCVZkZD4=
HCQtIllLKBE=
HCgmIllIKxE=
HUlnQ1slY3A=
KVkYX28zG2o=
O2sBIX4NDBQ=
P2MOJXoMChA=
TBR9Ugl7emA=
ZR1UGyByUC8=
aRlYHyx2XCU=
dWFPKzMCRx4=
```

下一步证据目标：在 `captcha.js` 和 `main.min.js` 静态代码中定位传给 `Yc(e,n)` 的 `e` 对象构造点，确认 `OSkIb39DDA==` 和上述 15 个字段是否同源；然后用 live POW 值生成等价 `PX561` activity。

### 21.7 勘误：success stack 的 captcha.js 大 column 来自 patched.js，不能直接当原始源码 offset

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/extract_hsprotect_source_offsets.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/map_hsprotect_patch_insertions.py`

新增输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/source_offsets_main_success_px561_stack_ni109_linecol3.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/source_offsets_captcha_success_px561_stack_ni109_linecol.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/source_offsets_captcha_patched_success_px561_stack_ni109_linecol.md`

#### 21.7.1 已证实：`main.min.js` 侧 `PX561 -> Yc -> $c -> tf` 链可定位

成功样本 `PX561` activity 的 stack 字段：

```text
W0shQR0nJHc=
pr@https://client.hsprotect.net/PXzC5j78di/main.min.js:2:21628
Yc@https://client.hsprotect.net/PXzC5j78di/main.min.js:3:6505
$c@https://client.hsprotect.net/PXzC5j78di/main.min.js:3:7845
Iz/D/<@https://captcha.hsprotect.net/.../captcha.js:1724:473784
Ts@https://captcha.hsprotect.net/.../captcha.js:1724:222787
D@https://captcha.hsprotect.net/.../captcha.js:1724:473271
```

对应静态片段已提取：

```text
output/protocol_reverse/source_offsets/source_offsets_main_success_px561_stack_ni109_linecol3.md
```

可追溯结论：

- `main.min.js:3:6505` 附近存在 `function Yc(e,n)`。
- `Yc(e,n)` 构造 collector activity 的 `d` 字段；它先注入基础环境字段，再把传入对象 `e` 合并进去。
- `main.min.js:3:7845` 附近存在 `$c(t,e){Rc(t,Yc(e,t))}`，即 captcha 侧传入的对象会经 `$c -> Yc -> Rc` 进入 collector activity。
- `main.min.js:3:36670/36718` 附近存在 `function tf(t,e)`，它对 activity 列表补充 `_px3/_px2/pc/cs/seq` 等 collector 请求材料。

证据片段中直接可见：

```text
function Yc(e,n){... C={"VGBuahICYlE=":Gc(e),"KDRSPm1TWQg=":Pi(),"W0shQR0nJHc=":...}
...
for(var B in e){var k=e[B];if(t(k)!==h||Zt(k)||null===k)C[B]=k;else for(var N in k)C[N]=k[N]}return C}
function $c(t,e){Rc(t,Yc(e,t))}
function tf(t,e){for(var n=eu(),r=0;r<t.length;r++){var a=t[r];...}
```

这能证明 `OSkIb39DDA==` 不是 `Yc` 的固定基础字段，而是 captcha 侧传入对象 `e` 中的字段，随后被 `Yc` 合并到 `PX561.d`。

#### 21.7.2 已证实：captcha 侧大 column 不能直接映射到原始 source.js

文件长度证据：

```text
output/outlook_browser/js_probe/captcha.js
  size=724774
  line1724len=471546

output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js
  size=724774
  line1724len=471546

output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.patched.js
  size=684501
  line1724len=474343
```

success stack 中出现的列：

```text
captcha.js:1724:473271
captcha.js:1724:473784
captcha.js:1724:473828
```

这些列大于原始 source 的 `line1724len=471546`，但小于 patched 的 `line1724len=474343`。因此这些大 column 只能对应插桩后的 patched captcha.js，不能直接作为原始 HUMAN `captcha.js` 的源码位置。

patch 元数据证据：

```text
output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.json

source_len=681704
patched_len=684501
patches=[
  "__outlook_hsprotect_patch_captcha_zt_enter__",
  "__outlook_hsprotect_patch_captcha_ot_enter__",
  "__outlook_hsprotect_patch_captcha_qs_pow__",
  "__outlook_hsprotect_patch_captcha_worker_new__"
]
```

这解释了为什么运行时 stack 的 `captcha.js:1724:473784` 能在 patched.js 中切到 `D/Iz` 附近，但在原始 source.js 中越界。

#### 21.7.3 已证实：POW worker 与最终 succeeded hook 是插桩证据，不是原始算法完整证明

成功样本动态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:272`：`hsprotect.captcha.pow.hit`，`value=218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:273`：`hsprotect.captcha.worker.message`，stack 指向 `captcha.js:1724:216367`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323-325`：`Ot -> zt -> Events.trigger("captcha","succeeded")`。

但由于上述 hook 来自 patched captcha.js，当前只能证明：

- worker 算出了 POW；
- POW 值后续出现在 `/assets/js/bundle` seq=2 的 `PX561.d.OSkIb39DDA==`；
- collector response 后触发 `Ot -> zt -> captcha succeeded`；
- `_px3/_pxde` 被调度并通过 `postMessage` 回 parent。

当前还不能声称已经从原始 HUMAN `captcha.js` 静态源码中完整定位 `OSkIb39DDA==` 的生成语句。下一步必须基于 source.js 而不是 patched.js 做反混淆映射。

#### 21.7.4 下一步必须补的证据

为继续推进“完全纯协议解析 + 复现 HUMAN 成功包”，下一步不能再用 patched column 直接当源码 offset；必须做以下一项或多项：

1. 对 `captcha_main_*.source.js` 做局部反混淆，围绕原始 source 中 `function D`、`Ts`、`J(r)`、`window[L][...](z)` 这几个可见结构定位传给 `$c/PX561` 的对象。
2. 复用成功 `PX561.d.W0shQR0nJHc=` stack 中的 `main.$c/Yc` 证据，反向从 `captcha` 侧找调用 `window[Su()][...]("PX561", r)` 或等价调用点。
3. 将 `OSkIb39DDA==` 与 POW worker 输出的关联，从“动态后验匹配”升级为“静态字段赋值/对象传参证明”。

在这些证据补齐前，协议 PoC 可以尝试构造 `PX561.d.OSkIb39DDA==`，但文档结论只能写为“基于成功 payload 的字段复刻”，不能写为“已完整还原 HUMAN 原始 JS 算法”。

### 21.8 原始 `captcha.source.js` 中已定位到 `Iz -> D -> main PX API` 调用链

新增输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/source_offsets_captcha_source_iz_d_px561_candidate.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/source_offsets_captcha_source_iz_d_px561_candidate.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_source_iz_d_flow.js.txt`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_source_d_emit.js.txt`

#### 21.8.1 原始 source 里的确定调用链

在未 patched 的 `captcha_main_1781017191_42fe203091d0.source.js` 第 1724 行，局部提取区间：

```text
source line 1724 columns 467192..471150
```

可见结构：

```js
function Iz(){... function D(r,n,t){... var z=pt(...); ... var L=Su(); ... var q=J(r);
if(window[L]&&s(window[L][...])===...){
  if(window[L][...]){
    var a,d=pn({},r,((a={})[...]=ke(),a["HGASKTZabC1xSx9T"]=jz,a));
    delete d[...],
    window[L]["B25IQl5Y"](...,d)
  }
  Ts((function(n,v,e){
    ...
    var i=Ou();
    ...
    s(i)===... && (
      r[...]=v,
      r[...]=e,
      r["D2csAy8QPCd9EyVT"]=parseInt(m()-t),
      r[...]=n,
      r[...]=os,
      r["B25IQlhZYw"]=ws,
      r[...]=Ks,
      i(...,r)
    ),
    window[L][...](z),
    window[L]["B25ORlo"]=Ot
  }))
}}
```

这里的全局字符串可由 `captcha.source.js` 顶部 `function u(...)` 解码，已离线确认：

```text
B25IQl5Y => PX1200
B25ORlo  => PX764
B25IQlhZYw => PX12617
HGASKTZabC1xSx9T => KVkYX28zG2o=
D2csAy8QPCd9EyVT => XQUsAxhpKjU=
OUMUPwg/MTVhFgIFDSYk => numOfWebWorkers
```

因此当前可证实的原始源码链路是：

```text
Iz()
  -> q()
    -> Ls.init(jz, ..., D, Mz, Gz)
      -> D(r,n,t)
        -> 组装/补充 r
        -> window[Su()].PX1200(<activityType>, d)   # activityType 仍需解码确认
        -> Ts(callback)
          -> 补充 worker/时间/指针等字段到 r
          -> Ou()(<activityType>, r)
          -> window[Su()].<method>(z)
          -> window[Su()].PX764 = Ot
```

这和成功样本 `W0shQR0nJHc=` 中的 runtime stack 对齐：

```text
captcha Iz/D/< -> Ts -> D -> main $c -> Yc -> pr
```

#### 21.8.2 与 `PX561.d.OSkIb39DDA==` 的关系边界

已经证实：

- `main.Yc(e,n)` 会把 captcha 侧传入对象 `e/r/d` 合并到 `PX561.d`。
- 成功 payload 中 `OSkIb39DDA==` 位于 `/assets/js/bundle` seq=2 的 `[2].d.OSkIb39DDA==`。
- 同轮 worker 输出的 POW 值与该字段完全相等。
- 原始 `captcha.source.js` 中 `D()`/`Ts()`/`Ou()`/`window[Su()].PX1200` 是把 captcha 侧状态对象送入 main collector API 的位置。

仍未证实：

- `f(c(439,441))` / 相关局部 decoder 表达式是否解码为 `PX561`。当前手工推导 decoder 参数未通过 Node 直接执行验证，所以不能把它写成事实。
- `OSkIb39DDA==` 在原始 source 中的具体赋值表达式。当前只知道该字段进入了成功 `PX561.d`，但还没从原始 `captcha.source.js` 证明是哪一行把 worker POW 写进对象。

下一步继续目标：

1. 正确模拟 `captcha.source.js` 第 1724 行局部 decoder 的数组轮转和 wrapper 参数，把 `f(c(...))` / `f(K(...))` 表达式批量还原。
2. 确认 `f(c(439,441))` 的 activity type 是否等于 `PX561`。
3. 确认 `OSkIb39DDA==` 对应的 obfuscated key，并定位 worker message -> object field 的赋值链。

### 21.9 已补证：`PX561` activity type 与 `OSkIb39DDA==` POW 字段的原始 source 赋值链

新增工具：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_captcha_d_flow_expressions.mjs`

新增输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_d_flow_expressions.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_d_flow_expressions.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/source_offsets_captcha_source_pow_us_ts_chain.md`

验证命令：

```bash
node --check tools/decode_captcha_d_flow_expressions.mjs
node tools/decode_captcha_d_flow_expressions.mjs
```

验证结果：命令无错误，并输出 `captcha_d_flow_expressions.md/json`。

#### 21.9.1 局部 decoder 复算结果

`captcha.source.js` 第 1724 行 `Iz/D` 局部 decoder 范围：

```text
decoder range: 464990..467091
source: output/outlook_browser/hsprotect_js_patch/captcha_main_1781017191_42fe203091d0.source.js
```

关键表达式解码结果：

```text
K(-166,-160) => raw B25IQl5Y => PX1200
K(-169,-188) => raw AAYaAT86YCV6FzFT => W0cqQR4rLnA=
c(439,441)   => raw B25MRl8 => PX561
c(414,426)   => raw GGUSOQxbbRNyOE1T => OSkIb39DDA==
c(410,395)   => raw FUwNQgg9EgVVDk1T => Bzt2fUFRcw==
c(411,413)   => raw EkFAGS0+Dj1vPQdT => Ew9iCVZjYDw=
c(429,410)   => raw B25IQlhZYg => PX12616
c(415,422)   => raw D3ErBDcAPxtUPz1T => XGRtYhkLbFM=
c(413,425)   => raw B25ORl0 => PX763
```

这补齐了 21.8 的两个缺口：

- `f(c(439,441))` 解码结果确认为 `PX561`；
- `f(c(414,426))` 解码结果确认为 `OSkIb39DDA==`。

#### 21.9.2 原始 source 中 `OSkIb39DDA==` 的赋值链

原始 source 片段：

```js
function Us(r,n){Ps=r,Es=m()-n,Ms=!0}
...
function Ts(r){if(Ms)return r(Gs,Es,Ps);setTimeout((function(){Ts(r)}),500)}
...
Ts((function(n,v,e){
  ...
  s(i)===... && (
    r[f(c(410,395))]=v,
    r[f(c(414,426))]=e,
    r[f("D2csAy8QPCd9EyVT")]=parseInt(m()-t),
    r[f(c(411,413))]=n,
    r[f(c(429,410))]=os,
    r[f("B25IQlhZYw")]=ws,
    r[f(c(415,422))]=Ks,
    i(f(c(439,441)),r)
  ),
  window[L][f(c(413,425))](z),
  window[L][f("B25ORlo")]=Ot
}))
```

结合 21.9.1 的解码：

```text
Ts(callback) 第三个参数 e = Ps
Us(value, f) 设置 Ps=value
r[f(c(414,426))]=e
f(c(414,426)) => OSkIb39DDA==
f(c(439,441)) => PX561
```

因此可证实的静态链路为：

```text
poi(...) 找到 POW 解答 value
  -> Us(value, f)
    -> Ps = value
      -> Ts(callback) 调用 callback(Gs, Es, Ps)
        -> callback 第三个参数 e = Ps = POW value
          -> r["OSkIb39DDA=="] = e
          -> Ou()("PX561", r)
            -> main.$c/Yc 合并 r 到 PX561.d
```

动态成功样本对照：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:272`：worker POW hit `218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.md`：同一值出现在 `[2].d.OSkIb39DDA==`。

结论更新：`PX561.d.OSkIb39DDA==` 不再只是动态后验匹配；已经有原始 `captcha.source.js` 静态赋值链证明它是 POW 解答字段。

#### 21.9.3 对协议构造的直接影响

对 live 纯协议构造，`PX561` activity 至少必须满足：

```text
t = PX561
d.OSkIb39DDA== = 当前 collector 下发 POW 的解答 value
d.Bzt2fUFRcw== = Ts 第二参数 v / Es，即 POW 计算耗时或延迟相关值
d.Ew9iCVZjYDw= = Ts 第一参数 n / Gs，worker 可用或 fallback 状态
d.XQUsAxhpKjU= = parseInt(m()-t)，从 D 入参时间点到回调时的相对耗时
d.PX12616 = os
d.XGRtYhkLbFM= = Ks
```

其中 `OSkIb39DDA==` 的生成已完全可复算；其他时间/环境字段仍需从 live trace 或静态变量 `Gs/Es/os/ws/Ks` 来源继续补证，不能随意填常量。

### 21.10 PX561 协议构造输入清单：已分桶字段与剩余缺口

本节只追加证据，不声明纯协议已经端到端成功。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_px561_protocol_inputs.py`

运行校验：

```bash
python3 -m py_compile tools/build_px561_protocol_inputs.py
python3 tools/build_px561_protocol_inputs.py
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_protocol_inputs/px561_protocol_inputs_ni109_vs_tf.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_protocol_inputs/px561_protocol_inputs_ni109_vs_tf.md`

输入证据：

- `output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json`
- `output/protocol_reverse/source_offsets/captcha_d_flow_expressions.json`
- `output/protocol_reverse/pow_response/pow_response_ni109xdjp5zp_1780948211.json`
- `output/protocol_reverse/bundle_activity_matches/bundle_activity_matches_ni109xdjp5zp_1780948211.json`
- `output/protocol_reverse/collector_field_map/collector_field_map.json`

成功样本 `PX561` 事实：

```text
source = output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl
request line = 308
seq = 2
fieldCount = 92
state = succeeded
powField = 218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
pointer/motion counts = 11 / 150 / 600
```

字段分桶结果：

| bucket | count | 证据含义 |
|---|---:|---|
| `captcha_d_flow_static` | 5 | 已在原始 `captcha.source.js` 的 `D/Ts` 链定位到 key 解码或赋值来源 |
| `main_tf_injected` | 5 | 由 `main.min.js` 的 `tf()` 在发送 collector 前注入 |
| `main_yc_base` | 6 | 由 `main.min.js` 的 `Yc()` 活动基础字段生成 |
| `shared_runtime_field` | 57 | 成功样本与 3 个 `tf.payload` 样本共享；可先作为模板字段，但完全纯协议仍需逐项静态定位 |
| `success_only_unmapped` | 19 | 成功样本有，但 3 个 `tf.payload` 样本都缺；当前只能证明差异存在，不能凭空构造 |

已静态定位的 `captcha_d_flow_static` 字段：

| key | success value | 证据 |
|---|---|---|
| `OSkIb39DDA==` | `218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f` | `captcha_d_flow_expressions.json`: `c(414,426) -> OSkIb39DDA==`；`pow_response_ni109...json` 证明该值由 POW 解出 |
| `Bzt2fUFRcw==` | `642` | `captcha_d_flow_expressions.json`: `c(410,395) -> Bzt2fUFRcw==`，对应 `Ts` 第二参数 `v` |
| `Ew9iCVZjYDw=` | `false` | `captcha_d_flow_expressions.json`: `c(411,413) -> Ew9iCVZjYDw=`，对应 `Ts` 第一参数 `n` |
| `FU1kS1AhYX4=` | `4` | `captcha_d_flow_expressions.json`: `K(-174,-196) -> FU1kS1AhYX4=`，对应 `pn(...[key]=o...)` |
| `XGRtYhkLbFM=` | `null` | `captcha_d_flow_expressions.json`: `c(415,422) -> XGRtYhkLbFM=`，对应 `Ks` |

POW 与 bundle 落点复核：

```text
raw = IooIIo|1|218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564|1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6|18|false
i = 50239
value = 218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
matchesTarget = true
bundle request line = 308
bundle seq = 2
PX561 activity index = 2
decoded path = d.OSkIb39DDA==
markerMatch = true
```

仍未定位 producer 的 `success_only_unmapped` 字段：

```text
Czd6cU5Yfko=
DXl3M0sUeQY=
EXFgN1QeZAA=
EXFgN1QeZQU=
Em4jaFcBJlg=
Ew9iCVZkZD4=
FUFvS1MiYXs=
HCQtIllLKBE=
HCgmIllIKxE=
HUlnQ1slY3A=
KVkYX28zG2o=
P2MOJXoMChA=
PAhGQnlsSXY=
TBR9Ugl7emA=
VQEvCxNgIjA=
ZR1UGyByUC8=
aRlYHyx2XCU=
dWFPKzMCRx4=
fg4ERDtuC3Y=
```

结论边界：

- 当前已经把 `PX561.d.OSkIb39DDA==` 从 “成功包里的值” 提升为 “可由 collector POW challenge 纯计算得出的字段”。
- 当前还没有证明 92 个 `PX561.d` 字段全部可以脱离浏览器独立生成。
- 当前还没有证明构造出的新 `PX561` collector body 会返回成功 handler，也没有证明 `_px3/_pxde` 更新和 Microsoft `risk/verify state=continue` 可完全纯协议达成。

下一步协议目标：

1. 对 19 个 `success_only_unmapped` 字段继续做原始 `main.min.js` / `captcha.source.js` producer 定位。
2. 用 fresh collector POW response 复算 `OSkIb39DDA==`，生成新的 `PX561` activity，而不是复制 `ni109` 成功包。
3. 通过已映射的 `tf -> Vs -> payload/pc` 路径编码 collector body。
4. 发送 live collector 请求，验证返回 handler 是否进入成功链；只有这一步通过，才能继续推进 `_px3/_pxde` 和 Microsoft `risk/verify` 纯协议重放。

### 21.11 继续补证：19 个 `success_only_unmapped` 中 8 个已定位到 `Yc()` PX561 分支

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/map_px561_static_fields.py`

运行校验：

```bash
python3 -m py_compile tools/map_px561_static_fields.py
python3 tools/map_px561_static_fields.py
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_static_field_map/px561_static_field_map_success_only.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_static_field_map/px561_static_field_map_success_only.md`

输入证据：

- `output/outlook_browser/js_probe/main.min.js`
- `output/outlook_browser/js_static_analysis/main.beautified.js`
- `output/protocol_reverse/px561_protocol_inputs/px561_protocol_inputs_ni109_vs_tf.json`

`Dc()` 表解码结果：

```text
rotations = 18
indexBase = 219
v -> PX561
p -> PAhGQnlsSXY=
m -> dWFPKzMCRx4=
g -> languages
y -> length
b -> HCgmIllIKxE=
I -> fg4ERDtuC3Y=
E -> HUlnQ1slY3A=
S -> cssFromResourceApi
T -> DXl3M0sUeQY=
R -> imgFromResourceApi
A -> FUFvS1MiYXs=
M -> fontFromResourceApi
w -> VQEvCxNgIjA=
x -> cssFromStyleSheets
```

对应原始 `Yc()` 逻辑位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:2963-3010`

核心代码：

```js
if (... && n === F(v)) {
  C[F(p)] = Boolean(!0),
  C[F(m)] = o[F(g)] && o[F(g)][F(y)],
  C[F(b)] = ki(),
  C[F(I)] = zi();
  try {
    var X = Xt();
    C[F(E)] = X[F(S)],
    C[F(T)] = X[F(R)],
    C[F(A)] = X[F(M)],
    C[F(w)] = X[F(x)]
  } catch (t) {}
}
```

因此 19 个缺口中，以下 8 个字段已经从 “success-only 未解释字段” 提升为 “`main.min.js` 静态 producer 已定位”：

| key | success value | producer |
|---|---|---|
| `PAhGQnlsSXY=` | `true` | `Yc()` PX561 分支：`C[F(p)] = Boolean(true)` |
| `dWFPKzMCRx4=` | `2` | `Yc()` PX561 分支：`navigator.languages.length` |
| `HCgmIllIKxE=` | `3f3ed248dc9b7955d1943b7d68465f87` | `Yc()` PX561 分支：`ki()`，即 `_pxhvd` localStorage 派生值 |
| `fg4ERDtuC3Y=` | `true` | `Yc()` PX561 分支：`zi()`，即 `Element.prototype.attachShadow` 能力 |
| `HUlnQ1slY3A=` | `0` | `Yc()` PX561 分支：`Xt().cssFromResourceApi` |
| `DXl3M0sUeQY=` | `0` | `Yc()` PX561 分支：`Xt().imgFromResourceApi` |
| `FUFvS1MiYXs=` | `0` | `Yc()` PX561 分支：`Xt().fontFromResourceApi` |
| `VQEvCxNgIjA=` | `0` | `Yc()` PX561 分支：`Xt().cssFromStyleSheets` |

仍未定位 producer 的 11 个字段：

```text
Czd6cU5Yfko=
EXFgN1QeZAA=
EXFgN1QeZQU=
Em4jaFcBJlg=
Ew9iCVZkZD4=
HCQtIllLKBE=
KVkYX28zG2o=
P2MOJXoMChA=
TBR9Ugl7emA=
ZR1UGyByUC8=
aRlYHyx2XCU=
```

本节结论边界：

- `static_producer_identified=8` 只证明这 8 个字段的静态赋值路径已经定位，不代表它们的 runtime value 已经能完全脱离浏览器独立生成。
- `not_found_literal=11` 表示这 11 个 key 没有以明文出现在本轮检查的 main sources 中；它们可能来自其他解码表、captcha 侧对象、动态 hash/压缩字段或运行时合并。
- 下一步要继续追这 11 个字段的来源，优先从成功 `PX561` 的值类型和相邻字段入手，反查 `captcha.source.js` 的对象构造与 `Yc()` 合并前的传入对象。

### 21.12 继续补证：21.11 剩余 11 个字段中 8 个定位到 captcha `J(r)` / `Zm` 几何对象

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_captcha_px561_extra_fields.mjs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_captcha_px561_remaining_fields.mjs`

运行校验：

```bash
node --check tools/decode_captcha_px561_extra_fields.mjs
node --check tools/decode_captcha_px561_remaining_fields.mjs
node tools/decode_captcha_px561_extra_fields.mjs
node tools/decode_captcha_px561_remaining_fields.mjs
```

输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_px561_extra_fields.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_px561_extra_fields.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_px561_remaining_fields.md`

静态代码证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11034-11043`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11065-11071`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11073-11091`

`J(r)` 的直接赋值路径：

```js
var J = function(r) {
  var u = function() { if (bm) return Zm }();
  return !!u && (
    r[z("Em4/FyBZBTJsODFT")] = u[z(n(901, 884))],
    r[z("DWRIJSkRFi5jOkhT")] = u[z("IF8dBAY")],
    r[z(n(908, 909))] = u[z("IF8dBAYiITpG")],
    r[z(n(924, 940))] = u[z("P1MQFwYcHiJbCQ")],
    r[z("FEwdRg09YQ5QEh9T")] = u[z(n(921, 939))],
    r[z(n(915, 900))] = u[z("P1cKGA")],
    r[z(n(925, 939))] = u[z("PkIcAg8cPThYCg")],
    r[z(n(900, 904))] = u[z("I18UFToHBzhaDxU")],
    ...
  )
};
```

解码结果：

| PX561 key | success value | source object field | producer evidence |
|---|---:|---|---|
| `EXFgN1QeZAA=` | `97` | `height` | `captcha_px561_extra_fields.md`: `J left key ... -> EXFgN1QeZAA=`；right key -> `height` |
| `ZR1UGyByUC8=` | `27` | `width` | `captcha_px561_extra_fields.md`: right key -> `width` |
| `P2MOJXoMChA=` | `1` | `widthJump` | `captcha_px561_extra_fields.md`: right key -> `widthJump` |
| `aRlYHyx2XCU=` | `4` | `heightJump` | `captcha_px561_extra_fields.md`: right key -> `heightJump` |
| `Czd6cU5Yfko=` | `91476` | `totalPixelCount` | `captcha_px561_extra_fields.md`: right key -> `totalPixelCount` |
| `EXFgN1QeZQU=` | `440be25de15f8e8a59b590f3233558683cdf89b5df1579ae849d052a16ed2490` | `hash` | `captcha_px561_extra_fields.md`: right key -> `hash` |
| `HCQtIllLKBE=` | `11` | `iterations` | `captcha_px561_extra_fields.md`: right key -> `iterations` |
| `Em4jaFcBJlg=` | `40` | `timeToSolve` | `captcha_px561_extra_fields.md`: right key -> `timeToSolve` |

因此，`21.11` 中 “仍未定位 producer 的 11 个字段” 已缩小：

```text
已定位到 captcha J(r)/Zm 几何对象: 8
已定位到 captcha D submit extra: 1
表达式已定位但 runtime value 冲突未闭合: 1
仍未定位 producer: 1
```

新增定位：

| key | current status | evidence |
|---|---|---|
| `KVkYX28zG2o=` | `D()` submit 前额外字段，值来自 `jz` | `captcha_px561_remaining_fields.md`: `HGASKTZabC1xSx9T -> KVkYX28zG2o=`；`captcha.beautified.js:11070` assigns `d[key] = jz` |
| `TBR9Ugl7emA=` | 静态表达式定位为 `r[key] = _s()`，但成功包 value 是长字符串，存在未闭合冲突 | `captcha_px561_remaining_fields.md`: `v(-540,-543) -> TBR9Ugl7emA=`；`captcha.beautified.js:11083` assigns `_s()`；成功样本 `px561_compare_success_vs_tf_samples.json` 中该 key value 为长字符串 |

仍未定位 producer：

```text
Ew9iCVZkZD4=
```

冲突待查：

```text
TBR9Ugl7emA=
```

`TBR9Ugl7emA=` 的冲突不能忽略：

- 静态赋值证据显示：`captcha.beautified.js:11083` 中 `r[t(v(-540,-543))] = _s()`。
- 新解码脚本显示：`t(v(-540,-543)) -> TBR9Ugl7emA=`。
- 但成功 `PX561.d` 中 `TBR9Ugl7emA=` 的实际值是长字符串：

```text
Y@tvUUF@W!kfHgFtWXNlXwpXFSUQa#E@JWcdNy!uUxIeWg(beEAsCx!sFE(ZFl$N)QFWUdcMkZWLFhtVl%EFBRNG@)oBWxofy$@TDoBGmpvNidTdExVQAURc)cBSDcg
```

所以当前只能写成“key 表达式已定位”，不能写成“producer 已完全闭合”。下一步必须证明是否存在：

1. 后续 overwrite；
2. serializer / merge 层字段错位；
3. 解码器局部上下文仍有误；
4. 成功样本中的长字符串实际来自另一个相邻 key。

### 21.13 勘误与继续补证：`KVkYX28zG2o=` 不是单一路径，`Ew9iCVZkZD4=` 已定位到 fakeToken

本节只追加证据，不覆盖 21.12。21.12 中对 `KVkYX28zG2o=` 和 `Ew9iCVZkZD4=` 的状态需要修正：

- `KVkYX28zG2o=` 不是“只来自 `D()` submit 前额外字段 `jz`”。
- `Ew9iCVZkZD4=` 不再是“仍未定位 producer”；已定位到 challenge-state submit 对象中的 `fakeToken`。
- `TBR9Ugl7emA=` 仍未闭合，因为静态表达式和值类型冲突仍存在。

新增脚本与产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_captcha_state_submit_fields.mjs`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_state_submit_fields.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_state_submit_fields.md`

验证命令：

```bash
node --check tools/decode_captcha_state_submit_fields.mjs
node tools/decode_captcha_state_submit_fields.mjs
```

新增静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8131-8140`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8148-8155`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11070`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11083`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:9638-9644`

`Ls.PlqQBA` 初始化字段的关键解码：

| expression | decoded | value expression |
|---|---|---|
| `Hn[o("MVcSFToHPzJY")] = e[o(w(-499,-476))]` | `fakeToken` | `fakeToken = secondArg.token` |
| `e[o(w(-499,-476))]` | `token` | second argument 的 `token` property |
| `Kf(Hn[o(w(-490,-474))], Hn[o(w(-450,-472))], n)` | `fakeToken` | `fakeToken` 继续传给 `Kf(...)` |

challenge-state submit 对象 `K` 的关键解码：

| expression | raw | decoded | value expression |
|---|---|---|---|
| `K[n(L(749,725))] = Hn[n("MVcSFToHPzJY")]` | `EkFAGS0+DjxsPURT` | `Ew9iCVZkZD4=` | `Hn[fakeToken]` |
| `K[n("HGASKTZabC1xSx9T")] = Hn[n(L(740,729))]` | `HGASKTZabC1xSx9T` | `KVkYX28zG2o=` | `Hn[challengeTime]` |

因此当前字段状态应更新为：

| key | current status | evidence |
|---|---|---|
| `Ew9iCVZkZD4=` | producer 已定位到 challenge-state submit 的 `fakeToken`；成功样本 value 与 `IooIoI` collector part 的 hash prefix 相同，但还需要继续证明 `secondArg.token` 的来源就是该 hash prefix | `captcha_state_submit_fields.md`: `EkFAGS0+DjxsPURT -> Ew9iCVZkZD4=`；`captcha.beautified.js:8132` assigns `K[key] = Hn[fakeToken]`；`captcha.beautified.js:8154` assigns `fakeToken = e[token]`；`bundle_activity_matches_ni109xdjp5zp_1780948211.json` line 308 seq 2 中该 key value 为 `b78eabfb...cd5c77`；`collector_decode_ni109xdjp5zp_1780948211.md` 的 `IooIoI` part 中同 hash prefix 出现 |
| `KVkYX28zG2o=` | producer 已定位到两条路径：`D()` submit extra 的 `jz`，以及 challenge-state submit 的 `Hn[challengeTime]`；成功样本 value `4948` 还需确认实际运行分支 | `captcha_px561_remaining_fields.md`: `HGASKTZabC1xSx9T -> KVkYX28zG2o=` and `captcha.beautified.js:11070` assigns `d[key] = jz`；`captcha_state_submit_fields.md`: same raw key maps to `KVkYX28zG2o=` and `captcha.beautified.js:8132` assigns `K[key] = Hn[challengeTime]`；`bundle_activity_matches_ni109xdjp5zp_1780948211.json` line 308 seq 2 中成功值为 `4948` |
| `TBR9Ugl7emA=` | 仍未闭合。静态表达式定位为 `r[key] = _s()`，但 `_s()` 返回布尔条件；成功样本 value 是长字符串 | `captcha_px561_remaining_fields.md`: `A3QrSTsPOGBTFDFT -> TBR9Ugl7emA=`；`captcha.beautified.js:11083` assigns `_s()`；`captcha.beautified.js:9638-9644` shows `_s()` returns boolean expression；`bundle_activity_matches_ni109xdjp5zp_1780948211.json` line 308 seq 2 中该 key value 是长字符串 |

当前剩余边界：

```text
已定位 producer，但 runtime source 还需继续追参数来源:
Ew9iCVZkZD4=  -> fakeToken -> secondArg.token -> 待证明是否来自 IooIoI hash prefix
KVkYX28zG2o=  -> jz 或 challengeTime -> 待证明成功包实际采用哪条路径

仍未闭合:
TBR9Ugl7emA=  -> 静态 _s() 布尔值 vs 成功包长字符串冲突
```

### 21.14 当前基线重建与字段证据纠偏：`KVkYX28zG2o=` 可闭合，`Ew9iCVZkZD4=` producer 已定位但桥接未闭合，`TBR9Ugl7emA=` 冲突增强

本节按当前文件状态重新生成基线，不覆盖前文历史结论，只追加勘误与最新证据。

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/build_protocol_reverse_baseline.py`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_captcha_ts_callback_fields.mjs`

新增产物：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/baseline/protocol_reverse_baseline_latest.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/baseline/protocol_reverse_baseline_latest.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_ts_callback_fields.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_ts_callback_fields.md`

验证命令：

```bash
python3 -m py_compile tools/build_protocol_reverse_baseline.py
python3 tools/build_protocol_reverse_baseline.py
node --check tools/decode_captcha_state_submit_fields.mjs
node --check tools/decode_captcha_px561_remaining_fields.mjs
node --check tools/decode_captcha_ts_callback_fields.mjs
node tools/decode_captcha_ts_callback_fields.mjs
```

#### 21.14.1 基线纠偏：`trace_classification_summary.json` 不是完整成功基线

当前 `trace_classification_summary.json` 只包含 3 个较新的 trace：

```text
e4tprvk082rw_1781016494 -> partial
whsnxy8ag5ji_1781017142 -> failure
i294e72kliud_1781017380 -> failure
```

完整成功样本仍应以单独文件为准：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/trace_classification_ni109xdjp5zp_1780948211.json`

该文件证明：

```json
{
  "status": "success",
  "checks": {
    "decoded_oIIoIooo_0": true,
    "dispatch_oIIoIooo_0": true,
    "ot_succeeded": true,
    "captcha_succeeded_event": true,
    "parent_postmessage_succeeded": true,
    "risk_verify_state_continue": true,
    "create_account_redirectUrl": true
  }
}
```

因此后续所有“成功包”对照必须继续以 `ni109xdjp5zp_1780948211` 为 authoritative success sample。

#### 21.14.2 `KVkYX28zG2o=` 的成功值 `4948` 已可由 `IooIoI` 延迟字段闭合

新增证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_collector_handlers/px561_collector_handlers_ni109.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/baseline/protocol_reverse_baseline_latest.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4504`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4640`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json:981`

collector 成功样本中的 `IooIoI` part：

```text
IooIoI|1|5bc17530-6373-11f1-b3b6-192fa993e3c2|6796|b78eabfb4f4a231aa3d4649efff95ae0e276bcf9761414a5841027f1153df7f9906856976185e69107e7838203c38cdef6f062c2598a397345fca0ab00cd5c77_>3>2|2|NA
```

静态源码：

```js
// main.beautified.js:4504
Hc(e, n = +(n = ne(u[1], Vl)), r = u[0], a = +a, c)

// main.beautified.js:4640
Vl = 10
```

复算：

```text
encodedDelaySource = >3>2
XOR key = 10
">3>2" XOR 10 = "4948"
```

成功 `PX561.d` 中：

```text
KVkYX28zG2o= = 4948
```

所以 `KVkYX28zG2o=` 当前可闭合为：

```text
IooIoI.rRaw second part ">3>2"
  -> ne(">3>2", Vl=10)
  -> 4948
  -> Hc/Zc challenge time/delay 参数
  -> captcha jz / challengeTime
  -> KVkYX28zG2o=
```

边界：`captcha_state_submit_fields.md` 与 `captcha_px561_remaining_fields.md` 显示 `KVkYX28zG2o=` 有两条赋值路径：

- `captcha.beautified.js:8132`：`K[key] = Hn[challengeTime]`
- `captcha.beautified.js:11070`：`d[key] = jz`

但两条路径都指向同一类 challenge delay/time 参数；本节闭合的是成功样本值 `4948` 的来源，不等于已经完整证明所有运行分支。

#### 21.14.3 `Ew9iCVZkZD4=`：producer 已定位到 `fakeToken`，但 main/captcha 回调桥接点还不能写死

已证明部分：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/source_offsets/captcha_state_submit_fields.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8131-8155`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11031`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_compare/px561_compare_success_vs_tf_samples.json:980`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/protocol_reverse/px561_collector_handlers/px561_collector_handlers_ni109.md`

静态链：

```text
captcha.beautified.js:11031
Ls.PlqQBA(jz, { token: yz }, D, Mz, Gz)

captcha.beautified.js:8154
Hn[fakeToken] = secondArg[token]

captcha.beautified.js:8132
K[Ew9iCVZkZD4=] = Hn[fakeToken]
```

成功样本值：

```text
Ew9iCVZkZD4=
= b78eabfb4f4a231aa3d4649efff95ae0e276bcf9761414a5841027f1153df7f9906856976185e69107e7838203c38cdef6f062c2598a397345fca0ab00cd5c77
```

该值与 `IooIoI` part 中 `rRaw` 下划线前缀相同：

```text
b78eabfb4f4a231aa3d4649efff95ae0e276bcf9761414a5841027f1153df7f9906856976185e69107e7838203c38cdef6f062c2598a397345fca0ab00cd5c77_>3>2
```

但当前不能写成“main `PX762` 已精确桥接到 captcha `Fu()` 回调”，原因是：

- `main.beautified.js:3032-3041` 中 `Zc()` 确实读取 `Lc()[PX762]` 并调用 `f($c, t, e, n, r)`；
- `captcha.beautified.js:10999-11005` 中 `Fu(function(r,n,t,v,e){ gz=r; jz=n; yz=t; ... })` 确实把第三个回调参数写入 `yz`；
- 但 `captcha.beautified.js:4469` 中 `Fu()` 的可见对象 key 通过当前解码得到的是 `slice`，不是 `PX762`。

因此当前可写成：

```text
Ew9iCVZkZD4= producer 已定位到 fakeToken；
fakeToken 来自 secondArg.token；
secondArg.token 来自 yz；
成功值与 IooIoI hash prefix 相同；
但 main Zc/Lc PX762 -> captcha callback 参数的精确桥接仍需继续找证据。
```

#### 21.14.4 `TBR9Ugl7emA=` 冲突增强：不是简单相邻字段错位

新增脚本 `decode_captcha_ts_callback_fields.mjs` 解出 `captcha.beautified.js:11083-11099` 整组 `Ts` callback 字段：

| expression | decoded | value expression |
|---|---|---|
| `r[t(v(-540,-543))] = _s()` | `TBR9Ugl7emA=` | `_s() boolean` |
| `r[t("FnM4CCwDASRmEyFT")] = Ws[t("Ng")]()` | `AEAxBkUsPjQ=` | `Ws[Ng]()` |
| `r[f(c(410,395))] = v` | `Bzt2fUFRcw==` | `Ts callback param v` |
| `r[f(c(414,426))] = e` | `OSkIb39DDA==` | `Ts callback param e` |
| `i(f(c(439,441)), r)` | `PX561` | activity type passed to main collector |

成功样本中相邻字段：

```text
AEAxBkUsPjQ=  -> bc9eb64492284f6e99f35edd54c32f72...
TBR9Ugl7emA= -> Y@tvUUF@W!kfHgFtWXNlXwpXFSUQa#E@JWcd...
Bzt2fUFRcw== -> 642
OSkIb39DDA== -> 218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f
```

这说明：

- `AEAxBkUsPjQ=` 的长 hash 有明确 producer：`Ws[Ng]()`；
- `OSkIb39DDA==` 的 POW 解有明确 producer：`Ts callback param e`；
- `TBR9Ugl7emA=` 在该字段组中仍只对应 `_s()`，而 `_s()` 在 `captcha.beautified.js:9638-9644` 返回布尔表达式。

因此 `TBR9Ugl7emA=` 当前不是“相邻字段简单错位”可以解释。剩余可证方向缩小为：

1. 后续 overwrite；
2. `Ws` / serializer / merge 层存在同 key 覆盖；
3. 当前 `Vs` 局部 decoder 上下文仍有未识别分支；
4. 成功样本中的长字符串来自更早/更晚同 key producer。

当前仍不能把 `TBR9Ugl7emA=` 写成已闭合字段。
