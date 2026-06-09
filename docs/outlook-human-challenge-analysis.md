# Outlook HUMAN / hsprotect 人机验证过程还原

> 增量文档。后续分析只追加新小节，不覆盖已有内容。

## 2026-06-08 22:54 CST 增量：最近注册日志、hook、JS 与链路还原

### 0. 证据范围

本节只基于当前工作区已落盘证据，不做猜测。主要证据文件：

- 最近注册 runtime trace：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_frju5ayty2gs_1780929636.jsonl`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_xcsk1e2yhkjq_1780929809.jsonl`
- 成功样本 runtime trace：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_b703i9khcpnt_1780847245.jsonl`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_v85399dos1y1_1780847363.jsonl`
- 批量注册详细日志：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/register_browser_headless_3x20_20260608_001309.log`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/register_browser_headless_3x10_evidence_20260607_232000.log`
- challenge artifact：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_after_press_4_1780928561.json`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_after_press_4_1780928561_frame6.html`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_after_press_4_1780928561_frame6.json`
- 本地拉取 JS：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/main.min.js`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/captcha.js`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/har_extract/js/hsprotect_main.min.js`
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/har_extract/js/hsprotect_captcha.js`
- hook 代码：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`

### 1. 总体流程还原

当前注册浏览器流中，人机验证不是一个单独的“提交验证码”接口，而是 Microsoft 注册页、`iframe.hsprotect.net`、HUMAN/PerimeterX JS、collector 上报、Microsoft risk verify 接口共同组成的链路。

#### 1.1 预热/初始化阶段

在注册页加载早期，页面先访问 HUMAN iframe：

- `GET https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=...`
- `GET https://client.hsprotect.net/PXzC5j78di/main.min.js`
- `GET https://stk.hsprotect.net/ns?c=<uuid>`
- `POST https://collector-pxzc5j78di.hsprotect.net/api/v2/msft`

证据：

- `/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl` 第 3-14 行显示：
  - iframe 首次加载；
  - `client.hsprotect.net/.../main.min.js` 加载；
  - `stk.hsprotect.net/ns?c=...` 请求；
  - 多次 `collector-pxzc5j78di.hsprotect.net/api/v2/msft` POST，payload 长度分别约 754、8986、6874。
- `/output/outlook_browser/runtime_trace_xcsk1e2yhkjq_1780929809.jsonl` 第 3-16 行有同样模式。
- `/output/outlook_browser/js_probe/main.min.js` 中可定位到：
  - `collector-PXzC5j78di.hsprotect.net`
  - `/api/v2/msft`
  - `/assets/js/bundle`
  - `/b/c`
  - `sendBeacon`
  - `onpointerdown` / `onmousedown`

结论：`main.min.js` 是注册页侧风控/采集主脚本；它会在正式 challenge 前采集设备、浏览器、事件、指纹并持续向 collector 上报。

#### 1.2 Microsoft risk verify 返回 HumanCaptcha

注册填写完成后，页面调用 Microsoft risk verify：

- `POST https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/api/v1.0/risk/verify`

如果需要人机验证，返回体包含：

- `challengeDetails.challengeType = "HumanCaptcha"`
- `challengeMetadata.appId = "PXzC5j78di"`
- `challengeMetadata.uuid = ...`
- `challengeMetadata.vid = ...`
- `challengeMetadata.challengeUrl = https://iframe.hsprotect.net/index.html?...`
- `continuationToken = ...`

证据：

- `/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl` 第 20 行：
  - `challengeType":"HumanCaptcha"`
  - `appId":"PXzC5j78di"`
  - `uuid":"ab5a0f70-6347-11f1-9d7b-2bfb57796c95"`
  - `vid":"aca3195e-6347-11f1-898f-f37dc6635e7b"`
  - `challengeUrl":"https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=618924fd-..."`
- `/output/outlook_browser/runtime_trace_xcsk1e2yhkjq_1780929809.jsonl` 第 20 行：
  - `uuid":"762cd200-6348-11f1-921c-27525194e13e"`
  - `vid":"776e7c1b-6348-11f1-8240-387fd40560a9"`
- 成功样本 `/output/outlook_browser/runtime_trace_v85399dos1y1_1780847363.jsonl` 第 20 行同样返回 HumanCaptcha。

结论：HUMAN challenge 的核心上下文由 Microsoft risk verify 返回，`uuid/vid/session_id/continuationToken` 后续必须保持同一链路。

#### 1.3 二次 iframe/ch_ctx 加载与 captcha.js

拿到 HumanCaptcha 后，页面进入正式 challenge iframe：

- `GET https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=...&ch_ctx=1`
- `GET https://captcha.hsprotect.net/PXzC5j78di/captcha.js?a=c&m=0&u=<uuid>&v=<vid>`
- `GET https://client.hsprotect.net/PXzC5j78di/main.min.js`
- `POST https://collector-pxzc5j78di.hsprotect.net/assets/js/bundle`

证据：

- `/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl` 第 21-39 行：
  - 第 21 行加载 `iframe...&ch_ctx=1`
  - 第 24 行加载 `captcha.hsprotect.net/.../captcha.js?a=c&m=0&u=ab5a0f70...&v=aca3195e...`
  - 第 27-38 行再次涉及 `main.min.js`、`stk`、`assets/js/bundle`
- `/output/outlook_browser/runtime_trace_xcsk1e2yhkjq_1780929809.jsonl` 第 21-39 行同样显示 `ch_ctx=1`、`captcha.js`、`assets/js/bundle`。
- 成功样本 `/output/outlook_browser/runtime_trace_v85399dos1y1_1780847363.jsonl` 第 21-39 行也一致。
- `/output/outlook_browser/challenge_initial_0_1780929519_frame4.html` 包含：
  - `<script src="https://captcha.hsprotect.net/PXzC5j78di/captcha.js?a=c&m=0&u=...&v=...">`
  - 内联 bridge 脚本监听 message、设置 `window[appId+"_asyncInit"]`。

结论：第一次 iframe 更像初始化/预热；第二次带 `ch_ctx=1` 的 iframe 才是正式挑战容器。`captcha.js` 依赖 `uuid/vid`，且会继续加载/协调 `main.min.js` 和 collector 上报。

### 2. iframe DOM 与按压目标

正式按钮并不在父页面 DOM 中，而在 `iframe.hsprotect.net` 的子 frame 内。父页面只看到一个 iframe 区域。

父页面 artifact：

- `/output/outlook_browser/challenge_initial_0_1780929519.json`
  - 页面 text：`证明你不是机器人 / 长按该按钮`
  - iframe rect：`x=684, y=632.5, width=360, height=90`
  - iframe src：`https://iframe.hsprotect.net/index.html?...&ch_ctx=1`

子 frame artifact：

- `/output/outlook_browser/challenge_after_press_4_1780928561_frame6.html`
  - `<title>人工验证挑战</title>`
  - `aria-label="可访问性挑战"`
  - `aria-label="按住 人工挑战"`
  - 文本：`按住`、`Human Challenge需要验证。请按住按钮直到验证完成`
- `/output/outlook_browser/challenge_after_press_4_1780928561_frame6.json`
  - 候选 1：`A#hWfKVuXZBMqPKsI role=button aria=可访问性挑战 rect=43.5,1 40x40`
  - 候选 2：`DIV#WYCUtPeurQwhQbD role=button aria=按住 人工挑战 rect=91.5,1 225x40`

父页面坐标换算：

- 父 iframe rect：`x=684, y=632.5, width=360, height=90`
- 子 frame 按压按钮 rect：`x=91.5, y=1, width=225, height=40`
- 所以父页面按压中心约为：
  - `x = 684 + 91.5 + 225/2 = 888`
  - `y = 632.5 + 1 + 40/2 = 653.5` 或不同视口下日志里的 `685.5/686`

日志证据：

- `/output/outlook_browser/register_browser_headless_3x10_evidence_20260607_232000.log` 行 1756-1758：
  - selector：`[role="button"][aria-label*="按住"][aria-label*="人工挑战"]`
  - rect：`776,666 225x40`
  - center：`888.0,685.5`
- `/output/outlook_browser/register_browser_headless_3x20_20260608_001309.log` 行 600-602：
  - `press target attempt=3 rect=871.5,608.5 225.0x40.0`
  - `center=984.0,628.5`
  - 该轮视口/iframe 位置不同，但仍是 iframe 内同一个 `225x40` 按压按钮。

结论：定位困难的根因不是“按钮坐标不可算”，而是按钮在跨域 iframe 内，且 iframe 里有多阶段 DOM：初始 `#px-captcha` 容器、loader、最终中文按钮 DOM。只有等子 frame 渲染出 `role=button aria-label*=按住 人工挑战` 后，坐标才稳定。

### 3. hook 捕获内容与状态判断

当前 hook 的安装点在 `/CTF-reg/outlook_browser_register.py`：

- `_install_challenge_hooks()` 监听：
  - `pointerdown/pointerup/pointermove`
  - `mousedown/mouseup/mousemove`
  - `click`
  - `touchstart/touchend`
  - `window.message`
  - `MutationObserver`
- `_challenge_hook_status()` 根据 `window.__outlookChallengeLog` 中的 message 判断：
  - `completed=true`：message 包含 `px-cookie-bridge-complete` 或 type 包含 `complete/success`
  - `failed=true`：message 为 `{"type":"failed"}`
  - `rendered=true`：message 为 `{"type":"rendered"}`

证据：

- `/CTF-reg/outlook_browser_register.py` 第 418-424 行：`window.addEventListener('message', ...)`，记录 origin/data。
- `/CTF-reg/outlook_browser_register.py` 第 494-505 行：根据 `"type":"failed"`、`"type":"rendered"`、success/complete 判定状态。

iframe 内联 bridge 脚本会向父页面发送消息：

- `/output/outlook_browser/challenge_initial_0_1780929519_frame4.html` 中可见：
  - `window[window._pxAppId+"_asyncInit"]=function(t){t.Events.on("captcha",(function(t){"rendered"===t&&a(),window.parent.postMessage({type:t},"*")}))}`
  - `function s(t,n,e){... window.parent.postMessage({type:"cookie",name:t,value:n,expires:e},"*")}`
  - 它会把 captcha 事件和 `_px*` cookie 通过 `postMessage` 传给父页面。

典型 message：

- cookie：
  - `{"type":"cookie","name":"_px3","value":"..."}`
  - `{"type":"cookie","name":"_pxde","value":"...","expires":"..."}`
- 渲染：
  - `{"type":"rendered"}`
- 失败：
  - `{"type":"failed"}`
- 成功：
  - `{"type":"succeeded"}`

证据：

- `/output/outlook_browser/register_browser_headless_3x10_evidence_20260607_232000.log` 行 1750：
  - last_events 包含 `_px3` cookie、`_pxde` cookie、`{"type":"rendered"}`
- 同一文件行 1790：
  - last_events 包含 `_pxde` cookie、`{"type":"failed"}`、新的 `_px3/_pxde`、`{"type":"rendered"}`
- `/output/outlook_browser/register_browser_headless_3x20_20260608_001309.log` 行 606-641：
  - post-wait 期间 repeatedly 看到 `lastMessage={"type":"succeeded"}`
  - 之后出现 `frontend CreateAccount redirect observed label=native_press`

结论：真正可用的 hook 成功信号是 `{"type":"succeeded"}`，但最终注册成功还需要父页面继续调用 Microsoft risk verify 并推进到 CreateAccount redirect。单纯看到 `rendered` 不是成功；看到 `failed` 则表示本轮验证失败或需重渲染。

### 4. 成功路径还原

成功样本中，人机验证通过后的链路如下：

1. `risk/verify` 返回 HumanCaptcha；
2. 浏览器加载 `iframe...&ch_ctx=1`；
3. iframe 加载 `captcha.js`；
4. `main.min.js/captcha.js` 向 collector 上报；
5. 自动按压 iframe 内 `按住 人工挑战` 按钮，通常按住约 42 秒；
6. hook post-wait 收到 `{"type":"succeeded"}`；
7. 随后发生 `POST /api/v1.0/risk/verify`，返回 `state:"continue"`；
8. 页面继续 `POST /signup.live.com/API/CreateAccount`；
9. CreateAccount 返回 `redirectUrl`；
10. 日志出现 `challenge completed ... redirect_seen=True`。

证据：

- `/output/outlook_browser/register_browser_headless_3x20_20260608_001309.log`：
  - 行 603-604：按压 42.194 秒；
  - 行 606-641：hook 出现 `{"type":"succeeded"}`；
  - 行 641：`frontend CreateAccount redirect observed label=native_press`；
  - 行 646：`challenge completed email=lotzgqzkew5v@outlook.com redirect_seen=True`
  - 行 651：`challenge completed email=xosk0mpq52wd@outlook.com redirect_seen=True`
  - 行 657：`challenge completed email=ej82ute9h6xv@outlook.com redirect_seen=True`
- `/output/outlook_browser/runtime_trace_v85399dos1y1_1780847363.jsonl`：
  - 第 43 行：`POST .../risk/verify`
  - 第 45 行：返回 `state":"continue"`
  - 第 46 行：`POST .../API/CreateAccount`
  - 第 47 行：CreateAccount 返回包含 `redirectUrl`、`signinName`、`slt`

结论：`{"type":"succeeded"}` 是 HUMAN iframe 层成功；`risk/verify state=continue` 是 Microsoft 风控层放行；`CreateAccount redirectUrl` 是注册主流程完成。三者要连起来才算完整通过。

### 5. 失败路径还原

#### 5.1 HUMAN 返回 failed

失败样本中，按压后 hook 出现 `{"type":"failed"}`，然后 iframe 重新渲染。

证据：

- `/output/outlook_browser/register_browser_headless_3x10_evidence_20260607_232000.log` 行 1760-1766：
  - 按压 42.141 秒；
  - post-wait 出现 `hook={"completed": false, "failed": true, "lastMessage": "{\"type\":\"failed\"}"...}`
  - 后续 `lastMessage` 变为 `{"type":"rendered"}`，说明 challenge 重新渲染。
- 同文件行 1790：
  - last_events 同时包含 `_pxde` cookie、`{"type":"failed"}`、新 `_px3/_pxde`、`{"type":"rendered"}`。

结论：`failed` 后不要继续认为当前按压有效；它触发了重渲染/新 cookie，必须等新按钮 ready 后再尝试。

#### 5.2 hook 无成功/失败消息

有些失败轮次按压 42 秒，但 hook 一直没有 `succeeded/failed/rendered`。

证据：

- `/output/outlook_browser/register_browser_headless_3x20_20260608_001309.log` 行 603-605：
  - up 后 `hook_after_up` 为空；
  - post-wait 初期仍空，随后才出现 succeeded。
- 之前 OAuth 测试日志中也出现按压后 `completed=false failed=false rendered=false`，页面仍 challenge；这类无法证明 HUMAN 接收到了有效按压结果。

结论：无 message 不能等同成功或失败；需要继续等待或重新采集 iframe artifact。若长期无消息，优先怀疑按压事件没有被 HUMAN 内部状态机采纳，或 iframe 内 JS/collector 状态未完成。

#### 5.3 Microsoft risk block

有些最近注册样本并非按压失败，而是 Microsoft risk verify 直接 block。

证据：

- `/output/outlook_browser/runtime_trace_frju5ayty2gs_1780929636.jsonl` 第 17-18 行：
  - `POST .../risk/verify`
  - 返回 `403`
  - `AADSTS7005106: Sign up attempt was blocked`
  - `innerError.code = riskBlock`

结论：这类失败发生在 Microsoft 风控层，和按钮定位/按压时长不是同一层问题；即使 HUMAN JS 正常，也可能被 Microsoft riskBlock 拦截。

### 6. JS 内容结论

#### 6.1 `main.min.js`

本地文件：

- `/output/outlook_browser/js_probe/main.min.js`
- `/output/har_extract/js/hsprotect_main.min.js`

关键证据：

- 包含 collector 域与路径：
  - `collector-PXzC5j78di.hsprotect.net`
  - `/api/v2/msft`
  - `/assets/js/bundle`
  - `/b/c`
- 包含 `_px3` 读取/上报逻辑；
- 包含 `onpointerdown`、`onmousedown`、`sendBeacon` 等事件/上报相关字符串。

结论：`main.min.js` 负责 HUMAN/PerimeterX 主采集与上报。它不是单纯渲染按钮，而是在 challenge 前后持续向 collector 发送加密 payload。

#### 6.2 `captcha.js`

本地文件：

- `/output/outlook_browser/js_probe/captcha.js`
- `/output/har_extract/js/hsprotect_captcha.js`

关键证据：

- 文件头声明 PerimeterX/HUMAN；
- 包含 `postMessage`；
- 包含 `px-captcha`；
- 包含 `press/hold` 相关字符串；
- 包含 WebWorker/POW 风格函数片段：`sha256`、`postMessage(z)`、`postMessage(!1)`。

结论：`captcha.js` 负责 captcha UI/按压状态机/计算任务等 challenge 侧逻辑。它不是一个可以靠普通 HTTP 请求直接替代的静态表单。

#### 6.3 iframe bridge 内联脚本

`challenge_initial_0_1780929519_frame4.html` 的内联脚本证明 iframe 会把事件桥接给父页面：

- 监听 `t.Events.on("captcha", ...)`
- captcha 事件发生时：`window.parent.postMessage({type:t},"*")`
- cookie 变更时：`window.parent.postMessage({type:"cookie",name:t,value:n,expires:e},"*")`

结论：hook 中看到的 `_px3/_pxde/rendered/failed/succeeded` 不是我们凭空生成，而是 iframe 内联 bridge 或我们自己的 cookie bridge 通过 `postMessage` 暴露到父页面。

### 7. 当前可执行判断标准

基于证据，完整人机验证过程应按以下状态判断：

1. `risk/verify` 返回 `challengeType=HumanCaptcha`：进入 HUMAN challenge。
2. iframe `&ch_ctx=1` 加载，且 `captcha.js?a=c&m=0&u=<uuid>&v=<vid>` 加载：正式挑战脚本已启动。
3. 子 frame 出现 `role=button aria-label="按住 人工挑战"`：按压目标 ready。
4. 按压 iframe 内按钮约 42 秒：当前成功样本多为 42 秒级别。
5. hook 看到 `{"type":"succeeded"}`：HUMAN iframe 层成功。
6. `POST /api/v1.0/risk/verify` 返回 `state:"continue"`：Microsoft 风控层放行。
7. `POST /signup.live.com/API/CreateAccount` 返回 `redirectUrl`：注册主流程继续。
8. 日志出现 `challenge completed ... redirect_seen=True`：浏览器挑战流程完成。

任何缺口都应按缺口分类：

- 没有 `ch_ctx=1/captcha.js`：iframe/challenge 脚本未完整加载。
- 没有按住按钮 DOM：不要按父页面猜测点；继续等/重采 artifact。
- hook `failed`：本轮失败，等重渲染后重新按。
- hook 无消息：按压未被确认，需看 iframe artifact 与 collector/risk 请求。
- `riskBlock`：Microsoft 风控层拒绝，和按压动作不是同类问题。

### 8. 结论

1. 最近成功样本证明：当前链路可以在 headless 注册中通过 HUMAN/hsprotect challenge，关键证据是 `{"type":"succeeded"}` -> `risk/verify state=continue` -> `CreateAccount redirectUrl` -> `challenge completed redirect_seen=True`。
2. 按钮坐标本身可以从 iframe DOM 精确计算；真正的不稳定点是 iframe 多阶段渲染、跨域 frame、以及 `failed/rendered/succeeded` message 的状态切换。
3. 单纯“按住按钮”不是完整过验证；完整放行依赖 HUMAN collector payload、cookie/message、Microsoft risk verify continuationToken 三者联动。
4. `main.min.js` 与 `captcha.js` 均参与加密上报/事件采集/状态机；纯协议复刻成本高，必须复刻 JS 执行、collector 上报、cookie/message、risk verify continuation 链。
5. 当前日志里同时存在三类失败：HUMAN `failed`、hook 无有效结果、Microsoft `riskBlock`。后续排查必须先按这三类分桶，不能混为“点错按钮”。

### 9. 是否需要继续执行注册命令补充监听

用户给出的可复现命令：

```bash
REGISTER_ONLY_MAX_ATTEMPTS=3 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

当前没有继续执行该命令，原因是现有落盘证据已经覆盖本节目标所需的关键状态：

- 成功链路证据：`succeeded` -> `risk/verify state=continue` -> `CreateAccount` -> `challenge completed`，来自 `/output/outlook_browser/register_browser_headless_3x20_20260608_001309.log` 与 `/output/outlook_browser/runtime_trace_v85399dos1y1_1780847363.jsonl`。
- 失败链路证据：`failed/rendered` 重渲染，来自 `/output/outlook_browser/register_browser_headless_3x10_evidence_20260607_232000.log`。
- Microsoft 风控失败证据：`AADSTS7005106 riskBlock`，来自 `/output/outlook_browser/runtime_trace_frju5ayty2gs_1780929636.jsonl`。
- JS 与 iframe bridge 证据：来自 `/output/outlook_browser/js_probe/*.js`、`/output/har_extract/js/*.js` 与 `challenge_*_frame*.html`。

如果后续需要更细粒度监听，建议追加而不是替换现有 hook，重点补这几类事件：

1. 在父页面记录每次 `risk/verify` 请求/响应的完整 JSON 字段名、状态码、`challengeType/state/innerError`。
2. 在 iframe 上层记录每条 `postMessage` 的完整 `type/name/expires`，但 cookie value 只记录长度和前后缀，避免日志过大。
3. 记录每次按压的 target 来源：父页面 iframe rect、子 frame button rect、最终父页面坐标、`isTrusted` 事件序列数量。
4. 对 `collector-pxzc5j78di.hsprotect.net` 只记录 URL、payload 长度、时间点、状态码，不尝试解密 payload；现有证据已经证明其是加密风控上报。
5. 把 `succeeded` 到 `risk/verify state=continue` 的时间差、`state=continue` 到 `CreateAccount` 的时间差写入汇总，便于区分“iframe 成功但父页面未推进”和“Microsoft 已放行”。

### 10. JS 内部执行逻辑补充

上一节只还原了 JS 的职责和链路，没有展开 JS 内部执行顺序。基于当前落盘 JS 与 iframe HTML，能证明的内部逻辑如下。

#### 10.1 iframe 内联 bootstrap/bridge 脚本

证据文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html`

该文件第 25 行是一整段内联 bootstrap 脚本。能从源码直接还原出这些函数职责：

1. `y()`：解析 `location.search`
   - 读取 `app_id`、`session_id`、`px_param1..10`；
   - 设置 `window._pxAppId`；
   - 如果存在 `session_id`，写入 `window._pxParam1`；
   - 初始化空的 `window._pxOnCaptchaSuccess=function(){}`。

2. `i(t)`：按类型动态加载 HUMAN JS
   - 当 `t="captcha"` 时，拼出：
     - `https://captcha.hsprotect.net/<appId>/captcha.js?a=c&m=0&u=<uuid>&v=<vid>`
   - 当 `t="client"` 时，拼出：
     - `https://client.hsprotect.net/<appId>/main.min.js`
   - 先尝试 `hsprotect.net`，失败时回退 `px-cdn.net`；
   - 加载失败会上报 `clientError` 到 `collector-a.px-client.net`。

3. `r()`：安装 iframe 消息桥
   - 监听父页面 message；
   - 支持三类指令：
     - `block`：调用 `d(jsonResponse, requestUrl)`；
     - `setToWindow`：把传入 key/value 写到 window；
     - `focus`：聚焦 `#px-captcha`。
   - 设置 `window[window._pxAppId + "_asyncInit"]`：
     - 监听 HUMAN SDK 的 `Events.on("captcha", ...)`；
     - 当事件为 `rendered` 时聚焦 `#px-captcha`；
     - 无论事件是什么，都执行 `window.parent.postMessage({type:t},"*")`。

4. `d(t,n)`：处理 block 响应
   - 从 `jsonResponse` 中取 `vid/uuid`；
   - 设置：
     - `window._pxUuid`
     - `window._pxVid`
     - `window._pxBlockedUrl`
   - 调用 `i("captcha")` 加载正式 `captcha.js`。

5. `f()`：hook `document.cookie`
   - 通过 `Object.getOwnPropertyDescriptor(Document.prototype,"cookie")` 取原始 getter/setter；
   - 重定义 `document.cookie`；
   - 每次设置 cookie 时调用 `l(t)`；
   - `l(t)` 解析 cookie，只关注 `_pxvid/_px3/_pxde`；
   - 命中后调用 `s(name,value,expires)`；
   - `s()` 通过 `window.parent.postMessage({type:"cookie",name,value,expires},"*")` 把 cookie 发给父页面。

6. `m()`：hook XMLHttpRequest
   - 如果请求目标 hostname 包含 `collector-<appId>.hsprotect.net`，并且存在 `window._pxCaptchaTesting`，则注入 header：
     - `x-px-captcha-testing`

7. `v()`：初始化 `_pxvid`
   - 优先读 cookie `_pxvid`；
   - 或从 `localStorage[appId+"_pxvid"]` 解析；
   - 然后通过 `postMessage({type:"cookie", name:"_pxvid", ...})` 发给父页面。

8. `h()`：异常桥接
   - 设置 `window.onerror`；
   - 把错误对象 `{type:"error", message, source, line, column, stack, timestamp, vid}` postMessage 到父页面。

9. `g()`：总入口
   - 执行顺序是：
     - `y()` 解析参数；
     - `m()` hook XHR；
     - `f()` hook cookie；
     - `r()` 安装 message/captcha 事件桥；
     - `v()` 发布 `_pxvid`；
     - `h()` 安装错误上报；
     - 如果不是 `ch_ctx`，则调用 `i("client")` 加载 `main.min.js`。

结论：iframe 内联脚本是“桥接层”，核心职责不是解题，而是加载 HUMAN JS、接收 `block` 上下文、桥接 captcha 事件、桥接 `_px*` cookie、把 iframe 内部状态通过 `postMessage` 暴露给父页面。

#### 10.2 `main.min.js` 内部逻辑

证据文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/main.min.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/har_extract/js/hsprotect_main.min.js`

可证明的内部执行逻辑：

1. 初始化 collector 配置
   - JS 中存在：
     - `collector-PXzC5j78di.hsprotect.net`
     - `https://collector-PXzC5j78di.px-cloud.net`
     - `/api/v2/msft`
     - `/assets/js/bundle`
     - `/b/c`
   - 代码构造 collector host 列表和路径列表；运行时 trace 中确实出现这些请求。

2. 采集并编码事件队列
   - `main.min.js` 中可定位 `onpointerdown`、`onmousedown`、`sendBeacon`。
   - 日志中的 `collector.../api/v2/msft`、`collector.../assets/js/bundle` POST 都是 `payload=...` 形式的加密/编码数据。
   - 代码中 `tf(...)` 会把事件数组编码成 query-like payload，并追加 appID、tag、vid、时间戳、cookie 等字段。

3. 读取 `_px3/_px2`
   - `main.min.js` 中存在 `Pn("_px3")`；
   - 如果 `_px3` 存在，写入编码字段；
   - 否则尝试 `_px2`。
   - 这和 hook 中看到 `_px3` 被 iframe 发给父页面一致。

4. 上报通道
   - 常规 XHR/POST 到：
     - `/api/v2/msft`
     - `/assets/js/bundle`
   - beacon 通道到：
     - `/b/c/beacon`
   - runtime trace 证据：
     - `/runtime_trace_v85399dos1y1_1780847363.jsonl` 第 30、35、39、40 行：`assets/js/bundle`
     - 第 42 行：`/b/c/beacon`
     - 第 43 行：随后 Microsoft `risk/verify`

5. 与按压行为的关系
   - `main.min.js` 不是简单按钮脚本，而是记录/编码浏览器环境和交互事件；
   - 成功样本中，按压结束前后出现大 payload 上报，然后才出现 `risk/verify state=continue`；
   - 因此“按压”必须伴随 HUMAN JS 上报链，单独模拟 DOM click 不足以证明通过。

结论：`main.min.js` 是 HUMAN 主采集/上报引擎，负责把环境、cookie、事件、指纹、交互轨迹编码后发送到 collector。它为后续 Microsoft `risk/verify` 能否返回 `state=continue` 提供关键上下文。

#### 10.3 `captcha.js` 内部逻辑

证据文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/captcha.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/har_extract/js/hsprotect_captcha.js`

可证明的内部执行逻辑：

1. UI 渲染
   - 文件中存在 `px-captcha`；
   - artifact 中正式渲染后出现：
     - `role="button" aria-label="按住 人工挑战"`
     - 文本 `按住`
   - `captcha.js` 中存在生成容器/style 的代码片段，例如 `div.px-captcha-background`、`div.px-captcha-container`。

2. 按压状态机
   - `captcha.js` 中存在 `press/hold` 相关字符串；
   - 实际 UI 文案为 `按住` / `Human Challenge需要验证。请按住按钮直到验证完成`；
   - hook 日志显示按压时长通常为 42 秒级别，成功消息不是 mouseup 立即返回，而是在 post-wait 中出现。

3. POW/计算任务
   - `captcha.js` 中存在 `sha256`；
   - 存在函数形态：
     - `poi(...)`：拼接候选值并比较 `sha256(z)===s`；
     - `qs(...)`：遍历范围，命中后 `postMessage(z)`，失败则 `postMessage(!1)`。
   - 这说明 challenge 内部不只是 UI 按压，还包含计算/worker 类任务。

4. 与父页面通信
   - `captcha.js` 中存在 `postMessage`；
   - iframe bridge 的 `Events.on("captcha")` 会把 captcha 事件转发到父页面；
   - 运行日志中父页面收到的 `{"type":"rendered"}`、`{"type":"failed"}`、`{"type":"succeeded"}` 就是该事件链的外显状态。

5. 异常上报
   - 文件尾部包含 `clientError` 上报；
   - 错误会上报到 `collector-a.perimeterx.net/api/v2/collector/clientError`，携带 `appId`、`captcha_version`、line、script、stack、message 等。

结论：`captcha.js` 是 challenge UI + 按压状态机 + 计算任务 + captcha 事件输出的脚本。它输出的 `succeeded/failed/rendered` 是 iframe 层状态，但最终是否注册放行还要看 Microsoft `risk/verify` 是否返回 `state=continue`。

#### 10.4 JS 内部逻辑的完整顺序图

基于上述证据，JS 内部执行顺序可还原为：

1. iframe 加载内联 bootstrap；
2. `g()` 解析 query，得到 `app_id/session_id`；
3. 安装 XHR hook、cookie hook、message hook、captcha event hook；
4. 非 `ch_ctx` 阶段加载 `client.hsprotect.net/<appId>/main.min.js`；
5. `main.min.js` 采集环境与事件，向 `/api/v2/msft` 上报；
6. Microsoft `risk/verify` 返回 HumanCaptcha，父页面/iframe 获得 `uuid/vid/challengeUrl/continuationToken`；
7. `ch_ctx=1` iframe 加载；
8. iframe 加载 `captcha.hsprotect.net/<appId>/captcha.js?a=c&m=0&u=<uuid>&v=<vid>`；
9. `captcha.js` 渲染 `#px-captcha` 和最终按住按钮；
10. 用户/自动化按住按钮；
11. `main.min.js/captcha.js` 继续上报 `/assets/js/bundle`、`/b/c/beacon`；
12. iframe 通过 captcha event/postMessage 输出：
    - `rendered`
    - `failed`
    - `succeeded`
    - cookie `_pxvid/_px3/_pxde`
13. 父页面收到 `succeeded` 后继续调用 Microsoft `risk/verify`；
14. 若返回 `state=continue`，继续 `CreateAccount`；
15. 若返回 `riskBlock` 或 iframe 输出 `failed`，流程失败或重渲染。

#### 10.5 对上一版结论的修正

上一版说“`main.min.js` 与 `captcha.js` 参与加密上报/事件采集/状态机”是正确但不够细。本次补充后，证据更精确：

- iframe 内联脚本负责 bootstrap 与 bridge；
- `main.min.js` 负责环境/事件/cookie 编码上报；
- `captcha.js` 负责 UI、按压状态机和计算任务；
- `postMessage` 是 iframe 状态外显通道；
- Microsoft `risk/verify` 是 HUMAN 结果进入注册主流程的放行点。

### 11. 证据审计与勘误：哪些结论可追溯，哪些只是推断

本节是对前文的自审。规则：具体值必须能追溯到文件路径 + 行号或文件内 offset；无法精确追溯的内容降级为“推断/待证”，不作为确定事实。

#### 11.1 可直接追溯的具体值

| 值 / 结论 | 证据位置 | 证据类型 |
| --- | --- | --- |
| `appId=PXzC5j78di` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:20` | `risk/verify` response body 中 `challengeMetadata.appId` |
| `uuid=ab5a0f70-6347-11f1-9d7b-2bfb57796c95` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:20` | `risk/verify` response body |
| `vid=aca3195e-6347-11f1-898f-f37dc6635e7b` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:20` | `risk/verify` response body |
| `ch_ctx=1` 正式 challenge iframe | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:21` | request URL |
| `captcha.js?a=c&m=0&u=<uuid>&v=<vid>` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:24`；`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html:21` | request URL + iframe HTML script src |
| `client.hsprotect.net/PXzC5j78di/main.min.js` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:5`、`:27` | request URL |
| `collector-pxzc5j78di.hsprotect.net/api/v2/msft` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:8`、`:11`、`:13`、`:17` | request URL |
| `collector-pxzc5j78di.hsprotect.net/assets/js/bundle` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:30`、`:34`、`:39`、`:40` | request URL |
| `risk/verify state=continue` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:44` | response body |
| `CreateAccount` 与 `redirectUrl` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:45`、`:46` | request + response body |
| `AADSTS7005106 / riskBlock` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_frju5ayty2gs_1780929636.jsonl:18` | 403 response body |
| iframe 内联脚本总入口 `function g(){y(),m(),f(),r(),v(),h(),c.ch_ctx||i("client")}g();` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html:25` | iframe HTML inline JS |
| iframe cookie hook 关注 `_pxvid/_px3/_pxde` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html:25` | `var o=["_pxvid","_px3","_pxde"]` |
| iframe bridge 转发 captcha 事件 | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html:25` | `t.Events.on("captcha", ... window.parent.postMessage({type:t},"*"))` |
| iframe XHR hook header `x-px-captcha-testing` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/challenge_initial_0_1780929519_frame4.html:25` | `XMLHttpRequest.prototype.open` wrapper |
| `main.min.js` 内含 collector host/path | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/main.min.js` offsets `171490`、`171527`、`172056`、`172180`、`172250` | 静态 JS 字符串 |
| `main.min.js` 内含 `sendBeacon/onpointerdown/onmousedown/Pn("_px3")` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/main.min.js` offsets `130499`、`112330`、`113511`、`97812` | 静态 JS 字符串 |
| `captcha.js` 内含 `sha256/postMessage(z)/postMessage(!1)/px-captcha/press/hold` | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/captcha.js` offsets `417990`、`422781`、`422796`、`267647`、`185272`、`175971` | 静态 JS 字符串 |

#### 11.2 前文中需要降级为“推断”的表述

以下表述不是错，但证据链不是“源码明文直接声明”，只能作为基于运行时顺序和静态字符串的推断：

1. “第一次 iframe 更像初始化/预热；第二次 `ch_ctx=1` 才是正式挑战容器”
   - 直接证据：
     - 初次 iframe 后加载 `main.min.js`：`runtime_trace_zgkx3mozafur_1780929466.jsonl:3-6`；
     - `risk/verify` 返回 HumanCaptcha 后加载 `&ch_ctx=1` 和 `captcha.js`：同文件 `:20-24`；
     - iframe 内联入口有 `c.ch_ctx||i("client")`：`challenge_initial_0_1780929519_frame4.html:25`。
   - 结论性质：强推断。运行顺序和 JS 分支支持该结论，但 JS 没有中文明文写“第一次是预热”。

2. “`main.min.js` 负责环境/事件/cookie 编码上报”
   - 直接证据：
     - 静态字符串有 collector host/path、`sendBeacon`、`onpointerdown`、`onmousedown`、`Pn("_px3")`；
     - runtime trace 有多次 `payload=...` 到 collector。
   - 结论性质：强推断。可以证明它有这些采集/上报能力和实际请求，但具体每个字段的语义未完全反混淆。

3. “`captcha.js` 负责按压状态机和计算任务”
   - 直接证据：
     - 静态字符串有 `px-captcha`、`press`、`hold`、`sha256`、`postMessage(z)`、`postMessage(!1)`；
     - iframe DOM 有 `aria-label="按住 人工挑战"`。
   - 结论性质：强推断。可以证明 UI/按压/计算相关代码存在，但没有完整反混淆每个状态变量。

4. “父页面收到 `succeeded` 后继续调用 Microsoft `risk/verify`”
   - 直接证据：
     - 成功日志中 `succeeded` 先出现，随后 `frontend CreateAccount redirect observed`；
     - runtime trace 中 `/assets/js/bundle` 后出现 `risk/verify state=continue` 再 `CreateAccount`。
   - 结论性质：顺序事实 + 因果推断。当前证据能证明顺序，不能单靠日志证明 Microsoft 内部因果。

5. “单独模拟 DOM click 不足以证明通过”
   - 直接证据：
     - 成功链路需要 `succeeded`、`risk/verify state=continue`、`CreateAccount redirectUrl` 三段证据；
     - 失败链路存在按压后 `failed/rendered` 或 `riskBlock`。
   - 结论性质：工程结论。它来自成功/失败样本对比，不是某个 JS 文件的直接声明。

#### 11.3 前文需要修正的细节

1. `risk/verify state=continue` 的主证据应优先引用最近成功 trace：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:44`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:45-46`
   - 前文引用 `/runtime_trace_v85399dos1y1_1780847363.jsonl` 也可用，但不是唯一证据。

2. `beacon` 路径前文写成 `/b/c/beacon` 不够严谨。
   - 当前最近成功 trace 里直接看到的是：
     - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_zgkx3mozafur_1780929466.jsonl:47`
     - URL 为 `https://collector-pxzc5j78di.hsprotect.net/api/v2/msft/beacon`
   - `main.min.js` 静态字符串中存在 `/b/c` offset `172250`，但不能把运行时 `api/v2/msft/beacon` 简写成 `/b/c/beacon`。
   - 修正：运行时证据应写 `api/v2/msft/beacon`；静态备选路径可写 `/b/c`。

3. `按住约 42 秒` 只代表当前成功/失败日志样本中的自动化 hold 时长。
   - 它不是从 HUMAN JS 算出的“必须时长”。
   - 证据来自注册日志中的 `held_s=42.x`；不能推导为协议层固定参数。

4. `tf(...)`、`poi(...)`、`qs(...)` 这类函数名来自对 minified JS 片段的静态阅读。
   - 函数名不稳定，不应该作为外部协议字段或稳定 API。
   - 可追溯事实是：`captcha.js` 中存在 `sha256`、`postMessage(z)`、`postMessage(!1)`；至于具体函数名和参数语义，需要进一步格式化/动态 hook 才能完全还原。

#### 11.4 当前文档仍缺的证据

如果要把“JS 内部执行逻辑”从链路级还原到函数级，还缺以下证据：

1. `main.min.js` 的格式化版本和关键函数调用栈。
   - 目前只有字符串 offset 与运行时请求顺序；
   - 还没有记录 `sendBeacon/XHR` 调用栈、payload 生成函数入口、事件队列结构。

2. `captcha.js` 的按压状态机调用栈。
   - 目前能证明 `press/hold/sha256/postMessage` 存在；
   - 还没有证明按下、保持、松开分别触发哪些内部函数、哪些阈值、哪些 collector 上报。

3. `succeeded` 事件的直接来源栈。
   - iframe bridge 能证明它会转发 `Events.on("captcha")` 的事件；
   - 但还没有 hook 到 HUMAN SDK 内部是哪一个函数触发 `captcha` event 的 `succeeded`。

4. collector payload 的字段语义。
   - runtime trace 只保存 `payload=...` 长度和片段；
   - 没有解码或还原字段映射，因此不能声明某个 payload 字段具体代表鼠标轨迹、指纹或 POW 结果。

#### 11.5 审计后的结论边界

目前可以确定：

- Microsoft `risk/verify` 返回 HumanCaptcha 上下文；
- `iframe.hsprotect.net` 内联脚本负责加载、hook、bridge；
- `client.hsprotect.net/.../main.min.js` 和 `captcha.hsprotect.net/.../captcha.js` 都被实际加载；
- collector 上报、`succeeded`、`risk/verify state=continue`、`CreateAccount redirectUrl` 在成功样本中按顺序出现；
- `riskBlock` 是另一类失败，不应和按压失败混为一类。

目前不能确定：

- HUMAN 内部判定成功的完整算法；
- 真实所需 hold 时长是否固定；
- collector payload 每个字段的含义；
- `succeeded` 与 Microsoft `state=continue` 之间的内部因果，只能证明当前样本中的顺序关系。

---

## 12. 2026-06-09 增量：JS 内部 trace 重跑证据

本节只记录本轮新增可追溯证据，不替换前文结论。

### 12.1 本轮运行结果

命令：

```bash
REGISTER_ONLY_MAX_ATTEMPTS=3 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

结果：

- attempt 1 使用 Webshare 直连出口 `210.191.121.221`，挑战未通过，错误为 `Outlook browser fallback: challenge not solved`。
- attempt 2 使用 Webshare 直连出口 `49.106.125.213`，挑战通过，并完成 OAuth 授权。
- 成功账号：`c0nw0cg8yyz9@outlook.com`。
- 授权应用：`d8bd9ced-3bad-4ecf-86f2-090009874b3e`。
- 终端日志显示 `browser refresh_token acquired ... rt_len=417`，最终 JSON 内存在 `mail_refresh_token`。

证据文件：

- JS 内部 trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_c0nw0cg8yyz9_1780941858.jsonl`
  - `wc -l`：134 行
  - `ls -lh`：89K
- runtime network trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_c0nw0cg8yyz9_1780941858.jsonl`
  - `wc -l`：52 行
  - `ls -lh`：20K

### 12.2 JS trace 捕获到了哪些内部事件

对 `js_internal_trace_c0nw0cg8yyz9_1780941858.jsonl` 统计：

```text
addEventListener      64
hook_installed        39
window.message.recv   31
```

这说明当前 hook 成功进入页面和 iframe 上下文，并捕获到了跨 frame `postMessage` 接收事件；但本轮没有捕获到 `fetch`、`xhr`、`sendBeacon`、`PX.Events.trigger` 级别事件。该缺口仍然存在，不能声称已经还原 SDK 内部函数调用栈。

关键行：

- 第 12 行：`signup.live.com` 收到 `https://fpt.live.com` 的 `dfp:OK`。
- 第 22 行：`signup.live.com` 收到 `iframe.hsprotect.net` 发来的 `_pxvid` cookie。
- 第 54 行：挑战 iframe 加载阶段再次收到 `_pxvid`。
- 第 57 行：`iframe.hsprotect.net` 收到父页面发来的 `{"type":"block", ... "requestUrl":"/api/v1.0/risk/verify"}`。
- 第 74 行：父页面收到 `{"type":"rendered"}`。
- 第 94 行：父页面收到 `{"type":"succeeded"}`。
- 第 101 行：注册 client 链回到 `login.live.com/oauth20_authorize.srf` 后再次收到 `dfp:OK`。
- 第 116 行：授权 client 链进入 `d8bd9ced-3bad-4ecf-86f2-090009874b3e` 后，`login.live.com` 侧仍收到 `dfp:OK`。

### 12.3 runtime trace 还原出的成功顺序

`runtime_trace_c0nw0cg8yyz9_1780941858.jsonl` 中的关键顺序：

1. `risk/initialize`
   - 请求：`https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad/api/v1.0/risk/initialize`
   - 响应：`200`

2. 首次加载 HUMAN iframe
   - `GET https://iframe.hsprotect.net/index.html?app_id=PXzC5j78di&session_id=c1e2de0d-c2fd-dd14-e744-80172c84a11e`
   - 随后加载 `https://client.hsprotect.net/PXzC5j78di/main.min.js`
   - 随后多次上报 `https://collector-pxzc5j78di.hsprotect.net/api/v2/msft`

3. 用户名可用性检查
   - `POST https://signup.live.com/API/CheckAvailableSigninNames?...`
   - payload 内 `signInName=c0nw0cg8yyz9@outlook.com`
   - 响应 `isAvailable=true`

4. Microsoft 风控判定进入 HumanCaptcha
   - `POST .../api/v1.0/risk/verify`
   - 响应体包含：
     - `challengeType: HumanCaptcha`
     - `appId: PXzC5j78di`
     - `uuid: 8275e580-6364-11f1-8ed1-9f395219dcb3`
     - `vid: 84757a3f-6364-11f1-b0ac-336d47e404e3`
     - `challengeUrl: https://iframe.hsprotect.net/index.html?...`

5. challenge iframe 二次加载
   - `GET https://iframe.hsprotect.net/index.html?...&ch_ctx=1`
   - `GET https://captcha.hsprotect.net/PXzC5j78di/captcha.js?a=c&m=0&u=8275e580-6364-11f1-8ed1-9f395219dcb3&v=84757a3f-6364-11f1-b0ac-336d47e404e3`
   - 再次加载/命中 `client.hsprotect.net/PXzC5j78di/main.min.js`
   - 上报端点切换为 `collector-pxzc5j78di.hsprotect.net/assets/js/bundle`

6. 按压完成后成功链
   - `POST https://collector-pxzc5j78di.hsprotect.net/assets/js/bundle`
     - `post_len=47142`
   - 紧接着还有一个 `assets/js/bundle`
     - `post_len=3934`
   - 随后 `POST https://collector-pxzc5j78di.hsprotect.net/b/c/beacon`
   - 随后 `POST .../api/v1.0/risk/verify`
   - 响应体包含 `state:"continue"`

7. 账号创建
   - `POST https://signup.live.com/API/CreateAccount?...`
   - 响应体包含 `redirectUrl` 指向：
     - `https://login.live.com/oauth20_authorize.srf?...client_id=00000000480728C5...`

### 12.4 成功按压的时间证据

终端日志显示本轮成功 attempt：

- iframe 按钮目标：
  - `rect=632,496 225x40`
  - `center=744.0,515.5`
- `press evidence down attempt=1 wall=1780941912.211`
- `press evidence up attempt=1 wall=1780941954.248`
- `held_s=42.037`
- post-wait 收到 `{"type":"succeeded"}`：
  - `lastMessageTime=97281`
- 随后出现：
  - `frontend CreateAccount redirect observed label=native_press`
  - `challenge completed email=c0nw0cg8yyz9@outlook.com redirect_seen=True`

因此，本轮成功样本能证明：约 42 秒按压后，iframe 发出 `succeeded`，然后 Microsoft `risk/verify` 返回 `state=continue`，最后 `CreateAccount` 返回 `redirectUrl`。但仍不能证明“42 秒是固定阈值”，只能证明这是本样本的成功持有时长。

### 12.5 与失败 attempt 的直接对比

同一条命令中 attempt 1 失败，attempt 2 成功，差异有可见证据：

- attempt 1 出口：`210.191.121.221`
- attempt 2 出口：`49.106.125.213`
- attempt 1 多轮按压后持续收到：
  - `{"type":"failed"}`
  - 后续 `{"type":"rendered"}`
  - 最终 `browser api create label=after_press ... keys=error error_code=1059 has_redirect=False`
- attempt 2 第一次按压后收到：
  - `{"type":"succeeded"}`
  - `risk/verify` 响应 `state:"continue"`
  - `CreateAccount` 响应 `redirectUrl`

因此，“同样的代码路径下，出口/风险上下文不同会导致 failed 与 succeeded 分叉”有本轮证据支持。不能把失败单独归因于按压坐标，因为失败和成功样本都定位到了 iframe 内 button center。

### 12.6 当前新增 hook 的局限

本轮 hook 已经能捕获跨 frame 消息，但仍缺以下证据：

1. 没捕获到 `PX.Events.trigger` 或 `Events.on("captcha")` 的内部调用。
2. 没捕获到 `captcha.js` 内部按压状态机函数名、阈值变量或 POW 计算调用栈。
3. runtime trace 只保存 collector payload 长度和片段，没有解码字段语义。
4. `add_init_script` 注入到所有 frame，但当前有效输出主要来自 `console.debug` fallback；`expose_function` 路径没有单独证明跨 iframe 稳定可用。

所以，新增证据足以还原“跨 iframe 消息 + 网络请求顺序”，但还不足以还原 HUMAN SDK 的完整内部算法。

## 13. 2026-06-09 增量：静态反混淆 + 运行时插桩对照

本节只追加证据，不覆盖前文。目标是把第 12 节的“只看到 window.message.recv”推进到函数级调用栈：证明 `captcha.js` 内部何处触发 `succeeded`，以及它如何继续到 Microsoft `risk/verify` 和 `CreateAccount`。

### 13.1 本轮改动边界

本轮只改观测层，不改注册/挑战业务流程：

- runtime trace 增加 request/response headers、console、pageerror、requestfailed：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:698`
- JS 内部 trace hook：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:837`
- hsprotect JS patch 默认关闭，仅在 `OUTLOOK_HSPROTECT_JS_PATCH=1` 时启用：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1315`
  - patch 函数：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1318`
  - main context 安装点：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:3689`
- 语法验证：
  - 命令：`.venv/bin/python -m py_compile CTF-reg/outlook_browser_register.py`
  - 结果：exit 0

### 13.2 静态反混淆产物

静态分析脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/analyze_hsprotect_js.mjs`

输出目录：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/`

关键产物：

- `summary.json`
- `summary.md`
- `main.beautified.js`
- `captcha.beautified.js`
- `main.ast_facts.json`
- `captcha.ast_facts.json`

静态定位结果：

| 文件 | 证据 | 位置 |
| --- | --- | --- |
| `main.min.js` | 事件总线 `Xn={on,one,off,subscribe,trigger}` | `output/outlook_browser/js_static_analysis/summary.json` 中 `Xn={on:` |
| `main.min.js` | `sendBeacon` 内部调用点 | patch 命中 `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1349` |
| `captcha.js` | POW 函数 `qs(...)` 被 patch | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1357` |
| `captcha.js` | Worker 创建点 `var w=new Worker(c);return w` 被 patch | `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1365` |

直接验证 patch 函数输出：

- 命令：导入 `outlook_browser_register._patch_hsprotect_js_source(...)`
- 结果：
  - `patches ['__outlook_hsprotect_patch_captcha_qs_pow__', '__outlook_hsprotect_patch_captcha_worker_new__']`
  - `has_noop_fallback True`
  - `has_worker_message True`

### 13.3 运行时验证命令与最终结果

运行命令：

```bash
OUTLOOK_HSPROTECT_JS_PATCH=1 REGISTER_ONLY_MAX_ATTEMPTS=3 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

attempt 1：

- 邮箱：`nzkl1us2bp7r@outlook.com`
- 注册 challenge 成功：
  - `frontend CreateAccount redirect observed label=native_press`
  - `challenge completed email=nzkl1us2bp7r@outlook.com redirect_seen=True`
- OAuth 失败原因有直接证据：
  - body 包含：`帮助我们确定你不是机器人。输入你看到的字符`
  - 因此 attempt 1 失败点是 OAuth 阶段字符验证码，不是注册 HUMAN challenge。

attempt 2：

- 邮箱：`l74w94f94xdf@outlook.com`
- 出口 IP：`60.66.110.190`
- 注册 client_id：`00000000480728C5`
- 授权 client_id：`d8bd9ced-3bad-4ecf-86f2-090009874b3e`
- 终端日志显示：
  - `browser refresh_token acquired email=l74w94f94xdf@outlook.com client_id=d8bd9ced-3bad-4ecf-86f2-090009874b3e rt_len=417`
  - `LOCALAUTH_RESULT_JSON` 中存在 `mail_refresh_token`

本节不记录完整 token。

### 13.4 本轮关键 trace 文件

attempt 2 的 trace：

- runtime trace：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl`
- JS internal trace：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl`

JS trace 统计：

- 总行数：238
- `hsprotect.Xn.trigger`：54
- `window.message.recv`：38
- `hsprotect.Xn.subscribe`：14
- `hsprotect.Xn.on`：10
- `hsprotect.captcha.worker.new`：8
- `hsprotect.captcha.worker.error`：7
- `hsprotect.sendBeacon.internal`：2

### 13.5 已确认的 HUMAN 内部事件链

本轮最关键的新增证据是：不再只看到父页面 `postMessage({"type":"succeeded"})`，而是直接抓到了 hsprotect 事件总线触发 `captcha -> succeeded` 的调用栈。

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:190`

内容摘要：

```text
kind=hsprotect.Xn.trigger
channel=captcha
args=["succeeded"]
stack:
trigger@https://client.hsprotect.net/PXzC5j78di/main.min.js:2:17255
zt@https://captcha.hsprotect.net/PXzC5j78di/captcha.js?...:1724:70576
Ot@https://captcha.hsprotect.net/PXzC5j78di/captcha.js?...:1724:83058
Wc@https://client.hsprotect.net/PXzC5j78di/main.min.js:3:5296
```

紧接着父页面收到成功消息：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:196`

```text
window.message.recv origin=https://iframe.hsprotect.net data={"type":"succeeded"}
```

因此现在可以把链路从“外显 succeeded 消息”推进到：

```text
captcha.js zt/Ot
  -> main.min.js Xn.trigger("captcha", "succeeded")
  -> iframe postMessage {"type":"succeeded"}
  -> signup.live.com 父页面收到 succeeded
```

### 13.6 Worker / POW 证据与边界

静态证据显示 `captcha.js` 中存在 POW 相关函数：

- `sha256`
- `poi`
- `qs`
- `postMessage(z)`
- `postMessage(!1)`
- `new Worker`

运行时证据显示 `captcha.js` 确实创建了 Worker，并且 Worker source 中包含被 patch 后的 `qs(...)`：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:114`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:115`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:116`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:117`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:118`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:119`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:120`

摘要：

```text
kind=hsprotect.captcha.worker.new
sourceLen=5275/5279/5280/5281
sourcePreview=(function qs(r,n,u,t,v,e,f,s,m){... for(var z,i=r;i<=n;i++) ...
```

本轮也发现一个观测代码缺陷：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:142`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:143`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:146`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:148`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:149`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:152`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:154`

错误：

```text
ReferenceError: __outlookPatchEmit is not defined
```

原因：`qs` 函数被序列化进 Worker Blob 后，Worker global 内没有页面侧 `__outlookPatchEmit`。该问题已在观测代码中改为 local noop fallback：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1357`

验证：

- `py_compile` exit 0
- 直接调用 patch 函数显示：
  - `has_noop_fallback True`
  - `has_worker_message True`

边界：本轮成功样本能证明 Worker 被创建、Worker source 包含 `qs/poi/sha256` POW 逻辑，但由于旧观测代码在 Worker 内抛了 `ReferenceError`，本轮还不能声称已经抓到 Worker 内部 POW 命中值。后续若要追到 POW 输出，应基于修正后的 noop fallback 再跑一次，或把 Worker `postMessage(z)` 包装成显式 trace。

### 13.7 网络链路：succeeded 后继续到 risk/verify 与 CreateAccount

runtime trace 中，HUMAN challenge 进入两次 `risk/verify`：

1. 第一次返回 challenge metadata：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:78`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:79`
   - response 摘要包含：
     - `challengeType:"HumanCaptcha"`
     - `appId:"PXzC5j78di"`
     - `uuid:"ca7eeb20-6368-11f1-88f9-53c94d64360b"`
     - `vid:"cb907fc6-6368-11f1-aec9-49f1b0a036d6"`
     - `challengeUrl:"https://iframe.hsprotect.net/index.html?..."`

2. 成功按压后再次 `risk/verify`：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:216`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:217`

随后 `CreateAccount`：

- request：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:218`
- response：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:219`
  - response 摘要包含 `redirectUrl`

同时 JS 内部 trace 显示 succeeded 后有两次 beacon：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:197`
  - `//collector-PXzC5j78di.hsprotect.net/b/c/beacon`
  - `blobSize=2505`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_l74w94f94xdf_1780943704.jsonl:198`
  - `//collector-PXzC5j78di.hsprotect.net/api/v2/msft/beacon`
  - `blobSize=2041`

对应实际网络请求：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:221`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_l74w94f94xdf_1780943704.jsonl:222`

### 13.8 本轮结论

可证实结论：

1. `main.min.js` 内部事件总线是 `Xn`，`on/subscribe/trigger` 已被运行时捕获。
2. `captcha.js` 在成功时通过 `Xn.trigger("captcha", "succeeded")` 通知 HUMAN 主逻辑，调用栈已抓到 `zt -> Ot -> Wc -> Xn.trigger`。
3. iframe 随后向父页面发送 `{"type":"succeeded"}`。
4. 父页面继续调用 Microsoft `risk/verify`。
5. `risk/verify` 之后 `CreateAccount` 返回 `redirectUrl`。
6. attempt 2 完整跑通到 OAuth，并获得 `mail_refresh_token`。

仍然不能声称的内容：

1. 不能声称已经完整还原 HUMAN 判定算法。
2. 不能声称 42 秒是固定阈值；本轮两个成功样本都在约 42 秒释放，但这仍只是样本事实。
3. 不能声称已拿到 Worker POW 最终命中值；旧插桩在 Worker 内出现 `__outlookPatchEmit` 未定义，已修复但尚未用新修复产物重新采集 POW 输出。

下一步如果继续追函数级算法，应只做观测层改动：

1. 用修正后的 Worker noop fallback 再跑一轮，确认 `worker.error` 消失。
2. 包装 Worker 内 `postMessage(z)`，把 POW 命中值以脱敏/截断形式记录。
3. 对 `captcha.js:1724:70576` 和 `captcha.js:1724:83058` 附近做 AST 片段导出，把 `zt/Ot` 对应逻辑映射到 beautified 代码行。

## 14. 2026-06-09 增量：Worker POW 输出与同一轮 failed/succeeded 对照

第 13 节留下的主要缺口是：Worker 内 `__outlookPatchEmit` 未定义，导致只能证明 Worker source 包含 `qs/poi/sha256`，但不能证明 POW 实际命中值。本节基于修复后的观测代码重新采集。

### 14.1 观测代码修复与验证

修复点：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py:1357`

修复方式：

- Worker 内 `__outlookPatchEmit` fallback 不再是空函数；
- fallback 使用 `console.debug("__OUTLOOK_JS_INTERNAL_TRACE__" + JSON.stringify(...))` 输出 trace；
- 不改业务 `postMessage(z)` / `postMessage(!1)`，避免改变 Worker 与主线程协议。

验证命令：

```bash
.venv/bin/python -m py_compile CTF-reg/outlook_browser_register.py
```

结果：exit 0。

直接调用 patch 函数的验证输出：

```text
patches ['__outlook_hsprotect_patch_captcha_qs_pow__', '__outlook_hsprotect_patch_captcha_worker_new__']
worker_console_fallback True
pow_hit True
worker_message True
no_biz_postmessage_patch True
```

### 14.2 本轮运行结果

运行命令仍为：

```bash
OUTLOOK_HSPROTECT_JS_PATCH=1 REGISTER_ONLY_MAX_ATTEMPTS=3 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

本轮日志落盘：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_worker_trace_20260609_024322.log`

本轮 trace：

- JS trace：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl`
  - 288 行
- runtime trace：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl`
  - 271 行

最终结果：

- 邮箱：`rdawhdfsqt6e@outlook.com`
- 注册 client_id：`00000000480728C5`
- 授权 client_id：`d8bd9ced-3bad-4ecf-86f2-090009874b3e`
- 终端日志：
  - `browser refresh_token acquired email=rdawhdfsqt6e@outlook.com client_id=d8bd9ced-3bad-4ecf-86f2-090009874b3e rt_len=417`
- `LOCALAUTH_RESULT_JSON` 中存在 `mail_refresh_token`，文档不记录完整 token。

### 14.3 Worker POW 第一次计算：命中但最终 failed

首次 challenge 渲染：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:136`

```text
Xn.trigger channel=captcha args=["rendered"]
stack:
trigger@main.min.js:2:17255
zt@captcha.js:1724:70576
Kf/<@captcha.js:1724:149438
```

父页面收到 rendered：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:137`

第一次 POW 被分成 5 个 Worker 分片：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:140`
  - `from=104858 to=157286`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:141`
  - `from=52429 to=104857`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:142`
  - `from=0 to=52428`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:143`
  - `from=157287 to=209715`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:144`
  - `from=209716 to=262144`

共同参数：

```text
mask=65535
len="0000"
prefix=4
salt=8
target=a852da1cc74d88cddb19631b0607dd7aa3e72c6cd464562cf739feef4f3f94d7
```

POW 命中：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:158`

```text
i=196981
value=ab091fffd7ab5a6f15af771cad1f47cd0e0c2fe4cf8e909031263013a98b0175
```

Worker 业务消息返回同一个值：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:159`

```text
data=ab091fffd7ab5a6f15af771cad1f47cd0e0c2fe4cf8e909031263013a98b0175
stack=as/<@captcha.js:1724:215167
```

但第一次按压最终失败：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181`

```text
Xn.trigger channel=captcha args=["failed"]
stack:
trigger@main.min.js:2:17255
zt@captcha.js:1724:70576
Ot@captcha.js:1724:83058
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
```

父页面收到 failed：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:186`

然后 challenge 重新 rendered：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:213`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:214`

结论：第一次失败不是因为 POW 没算出来。证据显示 POW 已命中并由 Worker 返回，但 HUMAN 状态机仍触发 `captcha -> failed`。

### 14.4 Worker POW 第二次计算：命中并最终 succeeded

第二次 challenge 再次分 5 个 Worker 分片：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:215`
  - `from=0 to=52428`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:216`
  - `from=104858 to=157286`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:217`
  - `from=52429 to=104857`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:218`
  - `from=157287 to=209715`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:219`
  - `from=209716 to=262144`

共同参数：

```text
mask=65535
len="0000"
prefix=4
salt=12
target=ae77827254d5a9f2b5acc268544a59771573623f373c21cd5ab8ded38486ca79
```

第二次 POW 命中：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:222`

```text
i=21808
value=1277d72ddef4627873623dbc5f65d55771a1b79430bc3be3709e1c3cb19c5530
```

Worker 业务消息返回同一个值：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:223`

```text
data=1277d72ddef4627873623dbc5f65d55771a1b79430bc3be3709e1c3cb19c5530
stack=as/<@captcha.js:1724:215167
```

第二次按压最终成功：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240`

```text
Xn.trigger channel=captcha args=["succeeded"]
stack:
trigger@main.min.js:2:17255
zt@captcha.js:1724:70576
Ot@captcha.js:1724:83058
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
```

父页面收到 succeeded：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:246`

终端日志也印证：

```text
press evidence post-wait attempt=2 ... {"type":"succeeded"}
frontend CreateAccount redirect observed label=native_press
challenge completed email=rdawhdfsqt6e@outlook.com redirect_seen=True
```

### 14.5 succeeded 后的 Microsoft 侧链路

runtime trace 显示首次 `risk/verify` 返回 HUMAN challenge metadata：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:79`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:80`

摘要：

```text
challengeType=HumanCaptcha
appId=PXzC5j78di
uuid=f91d5100-6369-11f1-ba36-df4aa6b7e211
vid=fa33b77b-6369-11f1-b580-1f3e0a87dccb
```

第二次 succeeded 后，Microsoft 侧继续：

- `risk/verify` request：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:262`
- `risk/verify` response：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:264`
- `CreateAccount` request：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:265`
- `CreateAccount` response：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:266`
  - response 摘要包含 `redirectUrl`

### 14.6 本节结论

本轮把第 13 节的 Worker 缺口补齐了：

1. `qs` POW 输入参数、分片范围、target、命中 `i`、命中 value 均已由运行时 trace 捕获。
2. `worker.message` 返回值与 `pow.hit` value 一致，说明命中值确实通过 Worker 原业务 `postMessage(z)` 返回。
3. 同一轮、同一邮箱、同一 session 内出现了先 failed 后 succeeded：
   - 第一次 POW 命中但 `captcha -> failed`；
   - 第二次 POW 命中且 `captcha -> succeeded`。
4. 因此 POW 是必要子步骤之一，但不是最终 HUMAN 放行条件；最终放行还依赖 `captcha.js/main.min.js` 状态机与 Microsoft `risk/verify` 的后续判断。
5. 修复后的观测没有再出现 `hsprotect.captcha.worker.error` 计数；本轮 JS trace 统计中包含：
   - `hsprotect.captcha.qs.start`: 10
   - `hsprotect.captcha.pow.hit`: 2
   - `hsprotect.captcha.worker.message`: 2
   - `hsprotect.captcha.worker.error`: 0

仍然不能声称的内容：

1. 仍不能声称完整还原 HUMAN 全部风险评分算法。
2. 仍不能声称 42 秒是固定阈值；本轮两次按压约 42 秒，第一次失败、第二次成功，反而证明“只按够 42 秒”不是充分条件。
3. 仍需进一步对 `captcha.js:1724:70576`、`1724:83058`、`main.min.js:3:32384` 做 AST 片段映射，才能把 `zt/Ot/oIIoIooo` 的局部逻辑还原到可读伪代码。


## 15. 2026-06-09 增量：运行时栈 `zt/Ot/Wc/oIIoIooo` 的 AST 静态映射

本节补第 14 节末尾留下的缺口：把成功样本运行时栈中的 `zt/Ot/Wc/oIIoIooo` 映射回本地拉取的 `captcha.js` / `main.min.js` 静态代码片段。这里不再只依据字符串搜索，而是用 Babel AST 的节点 range 定位“包含运行时 line:column 的最小 Function 节点”。

### 15.1 新增可复查产物

新增脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/map_hsprotect_stack.mjs`

输入文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/captcha.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/main.min.js`

输出目录：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/`

关键输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/summary.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/summary.json`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/captcha_zt.function.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/captcha_Ot.function.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_Wc.function.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_oIIoIooo.function.js`

脚本执行摘要来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/summary.md`

```text
captcha_zt:       captcha.js:1724:70576 -> absoluteOffset=280733 -> zt / FunctionExpression range=280617-280763
captcha_Ot:       captcha.js:1724:83058 -> absoluteOffset=293215 -> Ot / FunctionDeclaration range=293110-293645
main_Wc:          main.min.js:3:5296 -> absoluteOffset=66289 -> Wc / FunctionDeclaration range=66233-66299
main_oIIoIooo:    main.min.js:3:32384 -> absoluteOffset=93377 -> oIIoIooo / FunctionExpression range=93297-93404
```

### 15.2 与运行时 `failed/succeeded` 栈对照

运行时证据来自成功样本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl`

第一次判失败：

- trace line 181：`hsprotect.Xn.trigger`，`channel="captcha"`，`args=["failed"]`
- stack：

```text
trigger@https://client.hsprotect.net/PXzC5j78di/main.min.js:2:17255
zt@https://captcha.hsprotect.net/PXzC5j78di/captcha.js?...:1724:70576
Ot@https://captcha.hsprotect.net/PXzC5j78di/captcha.js?...:1724:83058
Wc@https://client.hsprotect.net/PXzC5j78di/main.min.js:3:5296
oIIoIooo@https://client.hsprotect.net/PXzC5j78di/main.min.js:3:32384
...
```

第二次判成功：

- trace line 240：`hsprotect.Xn.trigger`，`channel="captcha"`，`args=["succeeded"]`
- stack 与 failed 的核心链一致：`zt -> Ot -> Wc -> oIIoIooo`

父页面收到成功消息：

- trace line 246：`window.message.recv`，`data={"type":"succeeded"}`

随后业务继续：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:262`：第二次 `risk/verify` request
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:264`：第二次 `risk/verify` response，`state="continue"`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:265`：`CreateAccount` request
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:266`：`CreateAccount` response，包含 `redirectUrl`

最终 token 证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_worker_trace_20260609_024322.log:106`：`browser refresh_token acquired email=rdawhdfsqt6e@outlook.com client_id=d8bd9ced-3bad-4ecf-86f2-090009874b3e rt_len=417`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_worker_trace_20260609_024322.log:107`：`LOCALAUTH_RESULT_JSON` 包含完整 `mail_access_token`、`mail_refresh_token`

### 15.3 `zt`：captcha 事件转发函数

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/captcha_zt.function.js:1-8`

```js
function(r) {
  function n(r, n) {
    return mt(r - -665, n);
  }
  try {
    R()[window[v(n(-420, -426))]][v(n(-410, -403))][v(n(-422, -429))](v(n(-417, -412)), r);
  } catch (r) {}
}
```

可确认事实：

1. `zt` 接收一个参数 `r`。
2. `zt` 内部通过 `R()[window[...]][...][...](..., r)` 调用外部对象方法。
3. 结合运行时插桩，`zt("rendered")`、`zt("failed")`、`zt("succeeded")` 均进入 `hsprotect.Xn.trigger channel="captcha"`：
   - rendered：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:136`、`:213`
   - failed：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181`
   - succeeded：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240`

因此 `zt` 的证据级结论是：它是 captcha 状态向 HUMAN main SDK 事件总线转发的包装函数。它本身不计算风险，只把状态值转发出去。

### 15.4 `Ot`：把数值结果转换成 captcha 状态并提交后续 payload

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/captcha_Ot.function.js:1-22`

关键行：

```js
clearTimeout(At), r = parseInt(r), zt(s(0 === r ? e(1095, 1044) : e(1042, 972))), ...
...
o = ((f = {})[s(e(1155, 1184))] = r, f);
c && (o[s(e(1184, 1252))] = c), i(o, !0);
```

可确认事实：

1. `Ot` 第一参数 `r` 被 `parseInt(r)` 转成数值。
2. `Ot` 根据 `0 === r` 分支调用 `zt(...)`。
3. `Ot` 构造对象 `o`，对象里包含数值 `r`；如果 `n/t/v` 都存在，还拼接 `n|t|v` 作为附加值 `c`，然后调用 `i(o, true)`。
4. 运行时 failed 和 succeeded 的 `Xn.trigger captcha` 栈都包含 `Ot@captcha.js:1724:83058`：
   - failed：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181`
   - succeeded：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240`

仍不能直接声称的点：由于字符串表函数 `s(...) / e(...)` 还未完全还原，不能只从静态片段直接断言 `0 === r` 对应 `succeeded` 还是 `failed`。但运行时证据证明 `Ot` 是 failed/succeeded 两种 captcha 结果进入 `zt` 前的共同状态机节点。

### 15.5 `Wc`：main SDK 当前上下文回调分发器

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_Wc.function.js:1-6`

```js
function Wc(t, e, n, r) {
  var a = yc,
    o = Lc(),
    i = o && o[a(255)];
  i && i(t, e, n, r);
}
```

可确认事实：

1. `Wc` 读取 `Lc()` 返回对象。
2. 若 `o && o[a(255)]` 存在，则调用该函数，并把 `t,e,n,r` 原样传入。
3. failed/succeeded 栈里 `Wc` 位于 `Ot` 之后、`oIIoIooo` 之前：
   - failed：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181`
   - succeeded：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240`

证据级结论：`Wc` 是 main SDK 内部的回调分发器，不是 captcha 判定核心；它把 captcha 侧传来的状态继续分发到当前 SDK 上下文的处理函数。

### 15.6 `oIIoIooo`：调用 `Wc` 的 main SDK 包装回调

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_oIIoIooo.function.js:1-10`

```js
function(t) {
  var e = {
      F: 241,
      b: 247
    },
    n = Tl;
  if (Ul) return;
  var r = _l(this[xn]);
  Wc[n(e.F)](this, r ? [t][n(e.b)](r) : [t]);
}
```

可确认事实：

1. `oIIoIooo` 接收一个参数 `t`。
2. 如果全局/闭包标志 `Ul` 为真，直接返回。
3. 否则从 `this[xn]` 取值并经 `_l(...)` 处理得到 `r`。
4. 最后调用 `Wc[...]`，参数为 `this` 和 `[t]` 或 `[t].concat(r)` 形式。
5. failed/succeeded 栈中 `oIIoIooo` 是 `Wc` 的调用方：
   - failed：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181`
   - succeeded：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240`

证据级结论：`oIIoIooo` 是 main SDK 里接收 captcha/risk 链路事件的包装回调；它把当前对象上下文里的附加参数合并进回调参数，再调用 `Wc` 分发。它不是最终放行决策点。

### 15.7 还原后的局部调用链

结合静态 AST 与运行时 trace，可以把本轮关键状态链还原为以下局部伪代码：

```text
captcha 内部状态机得到 result r
  -> Ot(r, n, t, v)
       r = parseInt(r)
       zt(resultNameFrom(r))
       payload = { result: r, optionalJoinedFields: n|t|v }
       submitNext(payload, true)
  -> zt("failed" 或 "succeeded")
       mainSdk.Events.trigger("captcha", state)
  -> main.min.js Xn.trigger(channel="captcha", args=[state])
  -> main SDK 回调 oIIoIooo(t)
       if Ul return
       extra = _l(this[xn])
       Wc(...)(this, [t] + extra)
  -> Wc(...)
       currentContextCallback(t,e,n,r)
  -> 父页面收到 postMessage {type: state}
```

运行时证据对应：

- `failed`：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181`，父页面 `failed` message 在 `:186`
- `succeeded`：`js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240`，父页面 `succeeded` message 在 `:246`

### 15.8 本轮已能确认的完整外部过程

本轮完整外部过程已经可追溯到文件和行号：

1. Microsoft `risk/verify` 返回 HUMAN challenge：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:79-80`
   - `challengeType=HumanCaptcha`
   - `appId=PXzC5j78di`
   - `uuid=f91d5100-6369-11f1-ba36-df4aa6b7e211`
   - `vid=fa33b77b-6369-11f1-b580-1f3e0a87dccb`
2. iframe 加载：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:81,84`
3. iframe 向父页面写 `_px3/_pxde` cookie message：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:134-135`
   - 第二轮成功前更新：`:244-245`
4. captcha rendered：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:136-137`
   - 第二轮 rendered：`:213-214`
5. Worker POW 分片与命中：
   - 第一次分片：`:140-144`
   - 第一次命中：`:158-159`
   - 第二次分片：`:215-219`
   - 第二次命中：`:222-223`
6. 第一次状态失败：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:181,186`
7. 第二次状态成功：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:240,246`
8. 成功后 beacon：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_rdawhdfsqt6e_1780944209.jsonl:247`
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:261,263`
9. Microsoft `risk/verify` 放行：
   - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:262,264`
   - response `state="continue"`
10. `CreateAccount` 成功并返回 `redirectUrl`：
    - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_rdawhdfsqt6e_1780944209.jsonl:265-266`
11. OAuth 邮箱授权成功并拿到 refresh_token：
    - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_worker_trace_20260609_024322.log:106-107`

### 15.9 当前边界

本节把第 14 节的 `zt/Ot/oIIoIooo` 缺口补到了函数级，但仍有两个边界必须保留：

1. `s(...) / e(...) / n(...)` 等字符串表解码未完全展开，所以 `Ot` 里 `0 === r ? ... : ...` 的两个字符串常量还不能直接从静态文本读出；其语义由运行时 `failed/succeeded` 栈证明。
2. `risk/verify` 的服务端评分规则仍不可见；本地只能证明浏览器侧产生了 `_px3/_pxde`、POW 命中、captcha state、beacon、challengeSolution，并且 Microsoft 返回 `state="continue"`。

结论：当前已经能证据化还原浏览器侧 HUMAN challenge 的外部链路与关键内部函数级状态流；不能声称完整还原 HUMAN 服务端判定算法。


## 16. 2026-06-09 增量：日志不脱敏要求后的观测代码审计

用户新增要求：日志不要脱敏。基于该要求，对新增观测层做了代码审计并修正。

### 16.1 原始 run log 已经包含完整 token

证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_worker_trace_20260609_024322.log:107`

该行 `LOCALAUTH_RESULT_JSON` 已包含完整：

- `mail_access_token`
- `mail_refresh_token`

因此原始流程输出没有对 OAuth token 做脱敏。

### 16.2 新增 trace 里的截断点已移除

修正文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/outlook_browser_register.py`

已移除新增观测层中的主动截断/preview 字段：

- request headers：从 `str(v)[:800]` 改为完整 `str(v)`
- request body：从 `post_preview` 改为完整 `post_data`
- response headers：从 `str(v)[:1200]` 改为完整 `str(v)`
- response body：从 `body_preview` 改为完整 `body`
- XHR header：从 `.slice(0, 300)` 改为完整字符串
- XHR request body：从 `bodyPreview` 改为 `body`
- XHR response：从 `responsePreview` 改为 `responseText`
- fetch body：从 `bodyPreview` 改为 `body`
- sendBeacon：从 `dataPreview` 改为 `data`
- cookie setter：从 `value.slice(0, 1200)` 改为完整 `value`
- HUMAN `Xn.trigger` args：移除 `JSON.stringify(x).slice(0,800)`
- POW hit value：移除 `String(z).slice(0,400)`
- Worker source/message：从 `sourcePreview` / `.slice(0,1200)` 改为完整 `source` / `data`
- cached signup uaid 日志：从 `_mask(uaid)` 改为原始 `uaid`

验证命令：

```text
.venv/bin/python -m py_compile CTF-reg/outlook_browser_register.py
rg -n "_mask\(|redact|<redacted>|\*\*\*|post_preview|body_preview|bodyPreview|responsePreview|dataPreview|textPreview|sourcePreview" CTF-reg/outlook_browser_register.py
```

验证结果：

```text
py_compile 通过；rg 无匹配。
```

### 16.3 仍保留的非敏感摘要截断

`outlook_browser_register.py` 中仍存在页面元素摘要类截断，例如按钮文本、DOM 元素文本、插件列表数量等。这些字段不是 token/header/body/challenge payload，也不是本轮人机验证还原的核心证据字段。它们的用途是页面调试摘要，当前未作为 HUMAN 内部链路结论依据。

如果后续需要“所有 DOM 摘要也完全不截断”，需要单独扩大这些辅助字段；本轮已确保核心观测日志不再主动脱敏或截断。


## 17. 2026-06-09 增量：函数级插桩 + `Ot` 分支静态解码 + 最新成功链路三方对照

本节补第 15 节留下的关键缺口：不再只通过 `Xn.trigger("captcha", ...)` 观察外显状态，而是把 `captcha.js` 内部 `Ot` / `zt` 入口、main SDK 事件总线、Microsoft `risk/verify` / `CreateAccount` 网络结果放在同一轮成功样本里对照。

### 17.1 本轮样本与产物

测试命令：

```text
OUTLOOK_HSPROTECT_JS_PATCH=1 REGISTER_ONLY_MAX_ATTEMPTS=1 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python -u pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

成功样本：

- email：`sv2n3df1y8fi@outlook.com`
- 注册链路 client_id：`00000000480728C5`
- OAuth 授权 client_id：`d8bd9ced-3bad-4ecf-86f2-090009874b3e`

证据文件：

- 运行日志：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log`
- JS 内部 trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl`
- runtime/network trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl`
- 摘要产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/function_trace_summary_sv2n3df1y8fi.md`
- 静态解码脚本：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_hsprotect_strings.mjs`
- 静态解码结果：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/string_decode/captcha_ot_branch_decode.md`

本轮插桩生效证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:13`：`main.min.js` 被 patch，包含 `main_xn_event_bus`、`main_sendbeacon_internal`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:41`：`captcha.js` 被 patch，包含 `captcha_zt_enter`、`captcha_ot_enter`、`captcha_qs_pow`、`captcha_worker_new`

### 17.2 运行时事实：同一轮内 4 次 failed，cookie bridge 后 1 次 succeeded

运行日志显示，本轮不是“按压时间到了就必过”，而是先连续失败，再在 `_px` cookie bridge 后成功：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:55`：attempt=1，`held_s=42.3`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:91`：attempt=2，`held_s=42.2`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:127`：attempt=3，`held_s=42.1`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:163`：attempt=4，`held_s=42.1`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:194`：`px cookie bridge label=after_native_press has_signup_px3=True has_signup_pxde=True has_signup_pxvid=True ... injected=9`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:195`：`px bridge continue label=after_native_press action={'action': 'no_action'}`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:209`：bridge 后重新进入 attempt=1，`held_s=42.4`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:220`：`challenge completed ... redirect_seen=True`

证据级结论：

1. 42 秒级长按是本轮挑战的必要输入之一，但不是充分条件；前 4 次同样约 42 秒仍失败。
2. `_px3/_pxde/_pxvid` bridge 后，下一轮同样约 42 秒长按进入 succeeded，因此 cookie/state 同步是成功链路的关键变量之一。

### 17.3 函数级运行时证据：`Ot(r)` 决定 failed/succeeded 分支，`zt` 负责转发

本轮 JS trace 统计来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/function_trace_summary_sv2n3df1y8fi.md`

关键计数：

- `hsprotect.captcha.Ot.enter`: 5
- `hsprotect.captcha.zt.enter`: 10
- `hsprotect.Xn.trigger`: 138
- `window.message.recv`: 71
- `hsprotect.captcha.qs.start`: 25
- `hsprotect.captcha.pow.hit`: 5
- `hsprotect.captcha.worker.message`: 5
- `hsprotect.sendBeacon.internal`: 2

失败样本之一：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:174`
  - `kind=hsprotect.captcha.Ot.enter`
  - `r=-1`
  - `zero=False`
  - `state=failed`
  - `n=_px3`
  - `t=330`
  - `v_len=671`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:175`
  - `kind=hsprotect.captcha.zt.enter`
  - `arg=failed`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:176`
  - `kind=hsprotect.Xn.trigger`
  - `channel=captcha`
  - `args=["failed"]`

成功样本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:473`
  - `kind=hsprotect.captcha.Ot.enter`
  - `r=0`
  - `zero=True`
  - `state=succeeded`
  - `n=_px3`
  - `t=330`
  - `v_len=671`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:474`
  - `kind=hsprotect.captcha.zt.enter`
  - `arg=succeeded`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:475`
  - `kind=hsprotect.Xn.trigger`
  - `channel=captcha`
  - `args=["succeeded"]`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_sv2n3df1y8fi_1780946111.jsonl:476`
  - `kind=hsprotect.Xn.trigger`
  - `channel=score`
  - `args=["0","binary",null,null,null]`

成功栈顶链路：

```text
Ot@captcha.js:1724:84168
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
jl@main.min.js:3:36109
om/<@main.min.js:3:125998
om@main.min.js:3:126043
trigger@main.min.js:2:17431
fp@main.min.js:3:120086
```

`zt` 转发栈：

```text
zt@captcha.js:1724:70996
Ot@captcha.js:1724:84189
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
jl@main.min.js:3:36109
om/<@main.min.js:3:125998
om@main.min.js:3:126043
trigger@main.min.js:2:17431
```

证据级结论：

1. `Ot` 是本轮 `failed/succeeded` 状态进入 `zt` 前的共同节点。
2. `r=0` 对应 `succeeded`，`r=-1` 对应 `failed`；这个结论同时由运行时插桩和静态解码支持。
3. `zt` 接收字符串状态后触发 main SDK 事件总线 `Xn.trigger(channel="captcha", state)`。

### 17.4 静态反混淆：`Ot` 分支常量已解出 `succeeded/failed`

静态目标来自第 15 节映射出的 `captcha_Ot.function.js`：

```text
zt(s(0 === r ? e(1095, 1044) : e(1042, 972)))
```

新增解码脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/decode_hsprotect_strings.mjs`

解码输入：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/captcha.js`

关键静态事实：

- `ct.functionOffset=281083`
- `ct.arrayOffset=281103`
- `ct.length=166`
- `ct.rotations=59`
- `Rt` 源码形式是 `return ot(r- -7,n)`，即 `r + 7`，不是 `r - 7`

解码结果来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/string_decode/captcha_ot_branch_decode.md`

```text
0 === r -> token JEMaEwsNMDJS -> succeeded
else    -> token MVcQHAsM     -> failed
```

同一脚本继续解出 `Ot` 后半段关键字段：

```text
e(1155, 1184) -> token JEIYBBsb -> status
e(1184, 1252) -> token I1kSFQA -> token
e(1147, 1081) -> token IVMLGQgBNzZCEB8ALjU+WhwU -> verificationFailed
u("NV8XFA") -> bind
u("PkU0HwwBODJgEBUZGDslQi4ZChw8") -> isMobileViewportWidth
```

本节修正了一个前置错误：此前脚本把 `r- -7` 误读为 `r - 7`，导致解出 `_pxJsClientSrc` / `section.container`，与运行时 `Ot.enter state=succeeded/failed` 冲突。修正为 `r + 7` 后，静态解码与运行时插桩一致。

因此，`Ot` 的关键分支可还原为：

```text
Ot(r, n, t, v):
  clearTimeout(At)
  r = parseInt(r)
  if r === 0:
      zt("succeeded")
  else:
      zt("failed")
  if r === 0 and B() and su().isMobileViewportWidth:
      setTimeout(W, Kt - T)
  Hn.verificationFailed = Kn() && r === -1
  submit = setTimeout.bind(null, qt ? Qt : kt, Kt)
  joinedToken = n && t && v ? [n, t, v].join("|") : ""
  payload = {status: r}
  if joinedToken:
      payload.token = joinedToken
  submit(payload, true)
```

这里的 `submit` 名称是文档伪代码命名；源码里对应局部变量 `i`，由 `(z=qt, Ut=true, setTimeout.bind(null, z ? Qt : kt, Kt))` 得到。仍未命名的是 `qt/Qt/kt/Kt/T/W/B/Kn/su/Hn` 的完整业务语义，但 `Ot` 对外提交的 payload 形态已经可还原为 `{status: r, token: "n|t|v"}`。

### 17.5 network 对照：`succeeded` 后 `risk/verify` 放行，随后 `CreateAccount` 返回 redirectUrl

runtime/network trace 关键行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl:509`
  - 第二次 `risk/verify` request
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl:511`
  - 第二次 `risk/verify` response
  - body 包含 `"state":"continue"`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl:512`
  - `CreateAccount` request
  - URL 包含 `client_id=00000000480728C5`
  - post body 包含 `MemberName`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl:513`
  - `CreateAccount` response
  - body 包含 `redirectUrl`
  - body 包含 `signinName=sv2n3df1y8fi@outlook.com`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl:515`
  - `collector-pxzc5j78di.hsprotect.net/api/v2/msft/beacon` request
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_sv2n3df1y8fi_1780946111.jsonl:516`
  - `collector-pxzc5j78di.hsprotect.net/api/v2/msft/beacon` response 200

OAuth 最终成功证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:235`
  - `browser refresh_token acquired email=sv2n3df1y8fi@outlook.com client_id=d8bd9ced-3bad-4ecf-86f2-090009874b3e rt_len=417`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_function_trace_20260609_031504.log:236`
  - `LOCALAUTH_RESULT_JSON` 包含完整 `mail_access_token`、`mail_refresh_token`

### 17.6 本轮可确认链路

把静态解码、运行时 JS trace、runtime/network trace 合并，本轮可以证据化还原为：

```text
captcha challenge rendered
  -> POW/Worker 多轮运行
  -> Ot(r=-1)
  -> zt("failed")
  -> Xn.trigger("captcha", "failed")
  -> challenge 重渲染
  -> 多次失败后执行 px cookie bridge
  -> Ot(r=0)
  -> zt("succeeded")
  -> Xn.trigger("captcha", "succeeded")
  -> window.message.recv {"type":"succeeded"}
  -> risk/verify response {"state":"continue"}
  -> CreateAccount response {"redirectUrl":..., "signinName":"sv2n3df1y8fi@outlook.com", ...}
  -> OAuth 授权到 d8bd9ced-3bad-4ecf-86f2-090009874b3e
  -> refresh_token acquired
```

### 17.7 仍未完全还原的部分

当前已经把 `Ot` 的核心状态分支解到函数级，但以下仍不能声称已完整还原：

1. `Ot` 后半段 `status/token/verificationFailed/isMobileViewportWidth/bind` 已解出，但 `qt/Qt/kt/Kt/T/W/B/Kn/su/Hn` 的完整业务语义还未完全命名。
2. `Wc/oIIoIooo/jl/om/fp` 在 main SDK 中如何把 captcha 结果映射到 collector payload 的完整对象链还未完全命名。
3. collector `/b/c/beacon` 与 `/api/v2/msft/beacon` payload 内字段语义未完全反混淆。
4. `_px3/_pxde/_pxvid` 的服务端判定含义不能从客户端 JS 单独推出；当前只能确认 bridge 后下一轮成功。

下一步如果继续推进，应优先解码：

- `Ot` 中 `qt/Qt/kt/Kt/T/W/B/Kn/su/Hn` 的上下文；
- `main.min.js` 中 `Wc -> oIIoIooo -> jl -> om -> fp` 每个节点的参数对象；
- `sendBeacon.internal` 两个 endpoint 的 payload 结构。


## 18. 2026-06-09 增量：main SDK `Wc -> oIIoIooo -> jl -> om -> fp` 静态补图

本节继续补第 17.7 的 main SDK 缺口。目标不是猜 HUMAN 风控算法，而是把运行时栈中已经出现的 main SDK 节点映射到静态函数，确认每个节点在链路里的职责边界。

### 18.1 新增映射产物

扩展脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/map_hsprotect_stack.mjs`

新增/刷新输出：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/summary.md`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_jl.function.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_om.function.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_om_inner.function.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_fp.function.js`

映射摘要：

```text
main_jl:       main.min.js:3:36109  -> offset=97102  -> jl / FunctionDeclaration range=96712-97145
main_om_inner:main.min.js:3:125998 -> offset=186991 -> om / FunctionDeclaration range=186614-187214
main_om:      main.min.js:3:126043 -> offset=187036 -> om / FunctionDeclaration range=186614-187214
main_fp:      main.min.js:3:120086 -> offset=181079 -> fp / FunctionDeclaration range=180899-180993
```

注意：`main_fp` 初次自动映射时命中了外层 IIFE；已修正 `map_hsprotect_stack.mjs`，当运行时列号未落入目标函数时，优先按函数名选择最近的同名函数。修正后 `main_fp` 映射到 `fp / FunctionDeclaration range=180899-180993`。

### 18.2 `fp`：接收事件并触发内部事件系统

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_fp.function.js:1-7`

```js
function fp(t, e) {
  var n = 235,
    r = 251,
    a = 279,
    o = 235,
    i = Bv;
  np[i(279)](i(n), t, e), Ii[i(r)][i(a)](i(o), t);
}
```

可确认事实：

1. `fp` 接收两个参数 `t,e`。
2. `fp` 把 `t,e` 传入 `np[...]`。
3. `fp` 随后通过 `Ii[...]` 触发另一个内部事件通道。
4. 成功/失败 `Ot` 栈中 `fp` 位于 `trigger` 之后，说明它是 main SDK 事件触发后的下游处理节点之一，而不是 `Ot` 本身的分支判定点。

### 18.3 `om`：对输入事件包解包/解码后调用 `jl`

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_om.function.js:1-34`

核心结构：

```text
om(e, n):
  if not blocked by Mv/_r/Yi:
    inner(e, Tt(), jl)
    if n:
       进入一次性初始化/定时流程
```

内部函数的关键分支：

```text
if !e or !e.length:
    return false
u = Wl(e)
if typeof u !== "string":
    jl(u, true)
else:
    s = j(u)
    f = el(n)
    u = ne(s, parseInt(f, 10) % 128).split(Tl(235))
    jl(u, false)
```

可确认事实：

1. `om` 是进入 `jl` 前的解包/解码节点。
2. 当 `Wl(e)` 的结果不是字符串时，直接 `jl(u, true)`。
3. 当结果是字符串时，会经过 `j(u)`、`el(n)`、`ne(..., mod 128)`、`.split(...)` 后再 `jl(u, false)`。
4. 因此 `om` 负责把 main SDK 内部事件包转成 `jl` 可消费的数组/列表形式。

### 18.4 `jl`：按 `|` 拆分事件项，并分发到 `Cl/Xl`

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/stack_map/main_jl.function.js:1-29`

核心结构：

```text
jl(e, n):
  d = []
  for each p in e:
      m = p.split("|")
      g = m.shift()
      y = n ? Cl[g] : Xl[g]
      if m[0] === rr[pe]:
          h = {Fn:g, In:m}
          continue
      if typeof y === "function":
          if g === wl or g === Ml:
              d.push({Fn:g, In:m})
          else:
              d.unshift({Fn:g, In:m})
  if h:
      d.push(h)
  for each I in d:
      (n ? Cl[I[Fn]] : Xl[I[Fn]]).call({xn:d}, I[In])
```

可确认事实：

1. `jl` 处理的是一个事件项列表 `e`。
2. 每个事件项用 `"|"` 拆分；第一个片段 `g` 是事件/handler key。
3. `n` 决定使用 `Cl` 还是 `Xl` handler 表。
4. `jl` 对部分 key 调整执行顺序：`wl/Ml` 走 `push`，其他函数 handler 走 `unshift`，特殊 `rr[pe]` 暂存到 `h` 并最后 `push`。
5. 最终以 `{xn: d}` 作为 `this` 上下文调用对应 handler，并把剩余参数数组 `I[In]` 传入。

结合第 17 节，`captcha` 状态从 `Ot -> zt -> Xn.trigger` 后进入 main SDK；`jl/om/fp` 属于 main SDK 事件包解析和分发层，而不是 HUMAN captcha 按压判定的第一现场。

### 18.5 当前可还原的 main SDK 局部链

结合第 17 节运行时栈与本节静态片段，main 侧可以还原为：

```text
Xn.trigger("captcha", state)
  -> fp(t, e)
      -> 写入 np[...] / 触发 Ii[...] 内部事件
  -> om(e, n)
      -> Wl/e 解包
      -> 字符串路径：j -> el -> ne(... mod 128) -> split
      -> 非字符串路径：直接传递
      -> jl(events, decodedFlag)
  -> jl(events, decodedFlag)
      -> 按 "|" 拆分事件项
      -> 选择 Cl/Xl handler 表
      -> 调整 handler 执行顺序
      -> call handler
  -> oIIoIooo(t)
      -> 合并 this[xn] 上下文参数
      -> 调用 Wc
  -> Wc(t,e,n,r)
      -> 取 Lc() 当前上下文
      -> 调用上下文回调
  -> captcha iframe 内 Ot/zt 继续状态转发
```

这个顺序是“运行时栈 + 静态函数职责”的局部还原，不等价于完整算法源码。尤其 `Cl/Xl` handler 表中每个 key 的语义、`Wl/j/el/ne` 的解码细节、`np/Ii/Lc` 的对象结构还未全部命名。

### 18.6 本节新增边界

本节新增可确认内容：

1. `fp` 是 main SDK 事件下游触发节点。
2. `om` 是事件包解包/解码节点。
3. `jl` 是事件项拆分和 `Cl/Xl` handler 分发节点。

仍未确认内容：

1. `Cl/Xl` handler 表里与 captcha 直接相关的具体 key 名称。
2. `Wl/j/el/ne` 的完整解码算法语义。
3. collector beacon payload 从 `jl` handler 到 `sendBeacon.internal` 的完整字段映射。


## 19. 2026-06-09 增量：`om -> jl -> Xl` 事件包明文、handler key 与 cookie/state 写入链

本节继续补第 18.6 的缺口：通过新增运行时插桩把 main SDK 事件包从 `om` 解包结果直接打出来，并把 `jl` 看到的 handler key、handler 参数、静态 handler 函数文件做成可复查产物。

### 19.1 本轮样本与边界

运行命令仍是 `portal_browser` + `OUTLOOK_HSPROTECT_JS_PATCH=1`。本轮注册挑战通过，但后续 OAuth 授权失败在密码页：

- 运行日志：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_full_chain_trace_20260609_035004.log`
- JS trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl`
- runtime trace：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl`
- 分析产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md`
- JSON 产物：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.json`

本轮 patch 生效证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_full_chain_trace_20260609_035004.log:13`
  - main patch 包含 `main_xn_event_bus`、`main_sendbeacon_internal`、`main_fp_enter`、`main_om_enter_decode`、`main_jl_dispatch`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_full_chain_trace_20260609_035004.log:45`
  - captcha patch 包含 `captcha_zt_enter`、`captcha_ot_enter`、`captcha_qs_pow`、`captcha_worker_new`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_full_chain_trace_20260609_035004.log:61`
  - `frontend CreateAccount redirect observed label=native_press`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_full_chain_trace_20260609_035004.log:62`
  - `challenge completed email=ni109xdjp5zp@outlook.com redirect_seen=True`

OAuth 失败边界：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/run_logs/hsprotect_full_chain_trace_20260609_035004.log:206`
  - `OutlookOAuthError`
  - 页面文本包含 `你使用不正确的帐户或密码尝试登录的次数过多`

因此本轮样本可用于 HUMAN challenge 链路分析，但不能作为 OAuth refresh_token 成功样本。

### 19.2 新增运行时观测覆盖

本轮新增 hook 覆盖：

- `hsprotect.main.fp.enter`
- `hsprotect.main.om.enter`
- `hsprotect.main.om.Wl`
- `hsprotect.main.om.decode`
- `hsprotect.main.jl.enter`
- `hsprotect.main.jl.item`
- `hsprotect.main.jl.queue`
- `hsprotect.main.jl.dispatch`
- `hsprotect.sendBeacon.blobText`

计数来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md`

```text
hsprotect.main.jl.item: 55
hsprotect.main.jl.dispatch: 55
hsprotect.main.fp.enter: 7
hsprotect.main.om.enter: 7
hsprotect.main.om.Wl: 7
hsprotect.main.om.decode: 7
hsprotect.main.jl.enter: 7
hsprotect.main.jl.queue: 7
hsprotect.captcha.Ot.enter: 1
```

本轮 `Ot` 成功证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323`
  - `r=0`
  - `state=succeeded`
  - `n=_px3`
  - `t=330`
  - `v length=671`

### 19.3 `om.decode` 明文事件包

本轮 `om.decode` 直接输出了 main SDK 解码后的事件包。代表性事件包来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:192`
- 分析产物同一内容位于：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md`

该包 `el=178`、`mod=50`、`parts=18`，明文事件项包括：

```text
IoooII|_px3|330|...|true|300
IoIoIo|score|1|binary
IoIIIo|cu
IIoIoI|10001558580705928335
oIIoIoII|1780948253699
ooooII|d8jhq78ks0es73dhlco0
oIIoIoIo|8497
IoIIII|d6a874e9abbba2e7acc267a78db6f1921a0c250429698c9125908dc5310e6690
oIIooIoo|27|57|1|4|440be25de15f8e8a59b590f3233558683cdf89b5df1579ae849d052a16ed2490
IooIIo|1|218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564|1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6|18|false
IooIoI|1|5bc17530-6373-11f1-b3b6-192fa993e3c2|6796|b78eabfb4f4a231aa3d4649efff95ae0e276bcf9761414a5841027f1153df7f9906856976185e69107e7838203c38cdef6f062c2598a397345fca0ab00cd5c77_>3>2|2|NA
IIooII|cc|60|U2FtZVNpdGU9Tm9uZTsgU2VjdXJlOyBQYXJ0aXRpb25lZDsg
IIooII|rf|60|1
IIooII|fp|60|1
IIooII|fed|60|100
IIooII|nf|0|aHR0cHM6Ly9qcy5weC1jbG91ZC5uZXQv
oIooII|ccc:0,ic:0,ic:0,ai:0,uiii:0
oIIoIIoo|_pxde|330|...|true|300
```

可确认事实：

1. `om` 的字符串路径确实把原始 `ob` 经 `Wl -> j -> el -> ne(..., mod 128) -> split` 解为 `~~~~` 分隔的明文事件项。
2. `el(n)` 在本轮多个 `om.decode` 事件里输出 `178`，`parseInt(el,10)%128` 为 `50`。
3. `_px3`、`_pxde`、`score`、cookie 属性、fingerprint/risk 相关 key 都在同一个事件包里进入 `jl`。

### 19.4 `jl` 看到的 Xl handler key 与静态 handler

分析脚本：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/tools/analyze_hsprotect_full_chain.mjs`

该脚本将本轮 trace 里的 `jl.item` / `jl.dispatch` 与静态 `Xl` handler 表关联，并输出每个观察到的 handler 文件：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IoooII_Zl.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_oIIoIIoo.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IoIoIo.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IIooII.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IooIoo.js`
- 以及同目录下其他 `handler_Xl_*.js`

本轮观察到的 key：

```text
IIoIIo
IIoIoI
IIooII
IoIIII
IoIIIo
IoIoIo
IooIIo
IooIoI
IooIoo
IoooII
oIIoIIoo
oIIoIoII
oIIoIoIo
oIIoIooo
oIIooIIo
oIIooIoo
oIooII
ooooII
```

关键 handler 的证据级语义：

#### `IoooII`：`_px3` 写入/更新路径

运行时参数例：

- `IoooII|_px3|330|...|true|300`

静态 handler：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IoooII_Zl.js`

关键静态行为：

```text
di[...](..., n, t, e, o)
Jc() && Pl(this)
Et() === r[...] 时，检查/写入 cookie 聚合字符串
```

证据级结论：

- `IoooII` 是 `_px3` 事件项对应的 handler。
- 它会调用 `di[...]`，并在特定环境下更新 cookie 聚合状态。
- 不能仅凭当前片段断言 `di[...]` 的完整内部语义，但运行时参数和 handler 代码足以确认 `_px3` 值从事件包进入该 handler。

#### `oIIoIIoo`：`_pxde` 写入/更新路径

运行时参数例：

- `oIIoIIoo|_pxde|330|...|true|300`

静态 handler：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_oIIoIIoo.js`

关键静态行为：

```text
Et() === r[...] && Wn(t, e, n, a)
特定条件下 Gn(t)
di[...](..., n, t, e, o)
```

证据级结论：

- `oIIoIIoo` 是 `_pxde` 事件项对应的 handler。
- 它同时调用 `Wn/Gn/di`，因此属于 cookie/state 写入或同步路径。
- `Wn/Gn/di` 仍需继续解码才能完全命名。

#### `IoIoIo`：score 事件触发路径

运行时参数：

- `IoIoIo|score|0|binary`
- `IoIoIo|score|1|binary`

静态 handler：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IoIoIo.js`

代码：

```js
function(t, e, n, r, a, o) {
  di[Tl(231)](t, e, n, r, a, o);
}
```

运行时对照：

- `IoIoIo|score|0|binary` 后出现 `Xn.trigger channel=score args=["0","binary",...]`
- `IoIoIo|score|1|binary` 后出现 `Xn.trigger channel=score args=["1","binary",...]`

证据级结论：

- `IoIoIo` 是 score 事件项 handler。
- `score=0` 与成功路径同现；`score=1` 与非通过/中间状态同现。

#### `IIooII` / `oIooII`：cookie 属性/状态配置路径

运行时参数：

```text
IIooII|cc|60|U2FtZVNpdGU9Tm9uZTsgU2VjdXJlOyBQYXJ0aXRpb25lZDsg
IIooII|fed|60|100
IIooII|rf|60|1
IIooII|fp|60|1
IIooII|nf|0|aHR0cHM6Ly9qcy5weC1jbG91ZC5uZXQv
oIooII|ccc:0,ic:0,ic:0,ai:0,uiii:0
```

Base64 解码证据：

```text
U2FtZVNpdGU9Tm9uZTsgU2VjdXJlOyBQYXJ0aXRpb25lZDsg
=> SameSite=None; Secure; Partitioned;
```

静态 handler：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IIooII.js`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_oIooII.js`

证据级结论：

- `IIooII` 负责将配置项 `{ff:t, ..., ...}` 传入 `lr(true, i)`。
- `oIooII` 负责解析逗号分隔的 `key:value` 列表，并逐项 `lr(false, s)`。
- 当前证据能确认它们是配置/状态写入路径；`lr` 的具体存储位置仍需继续解码。

#### `oIIoIooo`：captcha 状态回调路径

运行时参数：

- `oIIoIooo|0`

静态 handler：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_oIIoIooo.js`

这就是第 18 节中的 `oIIoIooo`，负责合并 `this[xn]` 后调用 `Wc`。

### 19.5 network 对照：事件包后 Microsoft 放行

runtime trace 关键行：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:344`
  - 第二次 `risk/verify` request
  - `post_len=3002`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:345`
  - 第二次 `risk/verify` response
  - `state_continue`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:346`
  - `CreateAccount` request
  - 包含 `MemberName`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:347`
  - `CreateAccount` response
  - 包含 `redirectUrl`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:349`
  - `collector-pxzc5j78di.hsprotect.net/api/v2/msft/beacon`

证据级结论：

- 本轮 `om.decode -> jl.dispatch -> Ot(r=0) -> risk/verify state=continue -> CreateAccount redirectUrl` 链路成立。
- 这证明 main SDK 解码出的 `_px3/_pxde/score` 事件包与后续 Microsoft 放行处于同一成功链路内。
- 仍不能从客户端证据直接推出 HUMAN/Microsoft 服务端评分公式。

### 19.6 当前新增结论与剩余缺口

新增已确认：

1. `om.decode` 的明文事件包已捕获，不再只是推断。
2. `_px3` 对应 `IoooII` handler，`_pxde` 对应 `oIIoIIoo` handler。
3. `score` 对应 `IoIoIo` handler，并转为 `Xn.trigger("score", ...)`。
4. cookie 配置项 `cc` 的 base64 值解为 `SameSite=None; Secure; Partitioned;`。
5. 本轮 success 事件包中出现 `oIIoIooo|0`，对应 captcha 状态回调 handler。

仍未完成：

1. `di/Wn/Gn/lr/er/Rt/Oi/Pl` 等底层写入函数尚未完全命名。
2. collector `/api/v2/msft` POST body 字段仍未完全解包到对象字段级。
3. `_px3/_pxde` 值本身的加密/签名结构和服务端校验逻辑仍不可见。
4. 需要同等 hook 下更多失败/bridge 样本，才能用差异证据解释“为什么某轮 score=1，某轮 score=0”。


## 20. 2026-06-09 增量：底层 cookie/state 写入函数 `Wn/Gn/Pn/lr/er` 静态确认

本节继续补第 19.6 的第一个缺口：把 `_px3/_pxde` handler 中出现的 `Wn/Gn/lr/er/Pn` 底层写入函数还原到可读语义。

静态证据来自：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js`
- 以及本轮 AST 直接定位输出。

### 20.1 `Wn`：直接写 `document.cookie`

静态位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:875`

函数片段：

```js
function Wn(t, e, n, r, o = Hn()) {
  try {
    var i;
    null !== e && (
      "number" == typeof e || "string" == typeof e && !isNaN(+e)
        ? i = new Date(It() + 1e3 * e).toUTCString().replace(/GMT$/, "UTC")
        : "string" == typeof e && (i = e)
    );
    var c = t + "=" + n + "; expires=" + i + "; path=/",
      u = (!0 === r || "true" === r) && Un();
    return u && (c = c + "; domain=." + u), a.cookie = c + "; " + o, Pn(t) === n;
  } catch (e) {
    return Pn(t) === n;
  }
}
```

证据级结论：

- `Wn(name, ttlOrExpires, value, domainFlag, attrs)` 是 cookie 写入函数。
- 它构造 `name=value; expires=...; path=/`。
- 当 `domainFlag` 为 `true` 或 `"true"` 且 `Un()` 有值时，追加 `domain=.<domain>`。
- 最后写入 `document.cookie`，并用 `Pn(name) === value` 验证写入结果。

这直接解释了第 19 节中：

- `IoooII|_px3|330|...|true|300`
- `oIIoIIoo|_pxde|330|...|true|300`

为什么会落到 cookie/state 写入链。

### 20.2 `Gn`：删除 cookie

静态位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:867`

函数：

```js
function Gn(t) {
  Wn(t, -9e4, "", !0), Wn(t, -9e4, "", !1);
}
```

证据级结论：

- `Gn(name)` 是 cookie 删除/过期函数。
- 它分别用 domain 和 non-domain 两种方式把 cookie 写成空值且过期。

第 19 节 `oIIoIIoo` handler 中的 `Gn(t)` 因此可解释为：在特定条件下清理同名 cookie。

### 20.3 `Pn`：读取指定 cookie

静态位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:875` 附近，AST 输出为 `FunctionDeclaration 17859-18027`

函数：

```js
function Pn(t) {
  var e = ("; " + (arguments.length > 1 && void 0 !== arguments[1] ? arguments[1] : H).cookie).split("; ".concat(t, "="));
  if (e.length > 1) return e.pop().split(";").shift();
}
```

证据级结论：

- `Pn(name)` 从 `document.cookie` 字符串读取指定 cookie 值。
- `Wn` 用它验证写入是否成功。

### 20.4 `er`：编码后写 storage

静态位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:979`

函数：

```js
function er(t, e) {
  var n = tr(Ln);
  try {
    n.setItem(t, J(ut(e)));
  } catch (t) {}
}
```

证据级结论：

- `er(key, value)` 将 `value` 先经过 `ut`、再经过 `J` 编码，然后 `setItem(key, encoded)`。
- `tr(Ln)` 返回具体 storage 对象；当前证据尚未命名它是 localStorage 还是 sessionStorage，但 `setItem` 行为明确。

### 20.5 `lr`：状态配置写入与 TTL 持久化

静态位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:1012`

函数：

```js
function lr(t, e) {
  var n = e.ff,
    r = e.ttl,
    a = e.args,
    o = t ? a : "1";
  or[n] = o;
  var i = r && parseInt(r) || 0;
  i > 0 && function(t, e, n) {
    var r = Jn(ar) || {};
    r[t] = {
      ttl: Ft() + e,
      val: n
    }, er(ar, r);
  }(n, i, o), t && ir[n] && hr(ir[n] || [], o);
}
```

证据级结论：

- `lr(flag, {ff, ttl, args})` 会写入内存状态 `or[ff]`。
- 当 `ttl > 0` 时，会读取 `Jn(ar)`，更新 `{ttl, val}`，再通过 `er(ar, r)` 持久化。
- 当 `flag` 为真且 `ir[ff]` 存在时，会触发 `hr(ir[ff], value)`。

这解释了第 19 节：

- `IIooII|cc|60|...`
- `IIooII|fed|60|100`
- `IIooII|rf|60|1`
- `IIooII|fp|60|1`
- `IIooII|nf|0|...`
- `oIooII|ccc:0,ic:0,ic:0,ai:0,uiii:0`

这些事件项为何属于配置/状态写入路径。

### 20.6 当前 cookie/state 链路可还原到的程度

结合第 19 节和本节，当前可证据化还原为：

```text
om.decode 解出明文事件包
  -> jl.item / jl.dispatch
  -> Xl.IoooII("_px3", 330, value, true, 300)
      -> Zl
      -> di(...)
      -> 条件满足时 Wn("_px3", 330, value, true, attrs)
      -> document.cookie = "_px3=...; expires=...; path=/; domain=...; attrs"
      -> Pn("_px3") 验证

  -> Xl.oIIoIIoo("_pxde", 330, value, true, 300)
      -> Wn("_pxde", 330, value, true, attrs)
      -> 条件满足时 Gn("_pxde") 删除旧值
      -> di(...)

  -> Xl.IIooII / Xl.oIooII
      -> lr(...)
      -> or[...] = ...
      -> ttl > 0 时 er(ar, ...)
      -> storage.setItem(ar, encodedState)
```

仍不能声称：

- `di[...]` 的具体事件总线/写入语义还未完全解码。
- `tr(Ln)` 指向的具体 storage 对象还未命名。
- `_px3/_pxde` 值内部签名结构仍未解密。
- 服务端如何校验 `_px3/_pxde` 仍不可见。


## 21. 2026-06-09 增量：`di` 事件总线确认与 collector POST 外层字段

本节继续补第 20 节剩余缺口中的 `di` 和 collector POST 外层结构。结论只基于静态绑定和本轮 runtime 对照。

### 21.1 `di` 静态绑定

静态绑定来自 `main.min.js` AST 定位：

```text
di=Bn.extend({},Xn)
Ii={Events:di,ClientUuid:po(),setChallenge:function(t){pi=1,ho(t)}}
```

原始上下文位于：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_probe/main.min.js`
- AST 输出：`di` binding 为 `VariableDeclarator range 36939-36958`

可确认事实：

1. `di` 不是独立函数，而是 `Bn.extend({}, Xn)` 生成的对象。
2. `Ii.Events = di`，说明它作为 SDK 对外/内部事件对象暴露。
3. 第 19 节中 `Xl` handler 调用的 `di[...]` 都是对这个事件对象的方法调用。

### 21.2 `di[Tl(231)]` 的运行时行为

静态片段：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/handler_Xl_IoIoIo.js`

```js
function(t, e, n, r, a, o) {
  di[Tl(231)](t, e, n, r, a, o);
}
```

运行时对照：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:56`
  - `hsprotect.main.jl.dispatch`
  - `handlerKey=IoIoIo`
  - `args=["score","0","binary"]`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:57`
  - `hsprotect.Xn.trigger`
  - `channel=score`
  - `args=["0","binary",null,null,null]`

另一个对照：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:144`
  - `handlerKey=IoIoIo`
  - `args=["score","1","binary"]`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:145`
  - `Xn.trigger channel=score args=["1","binary",...]`

证据级结论：

- 在 `IoIoIo` handler 的实际调用路径里，`di[Tl(231)]` 表现为 `Xn.trigger`。
- 因为 `di=Bn.extend({},Xn)`，这与静态绑定一致。
- 当前未单独静态解出 `Tl(231)` 字符串，但 runtime 行号级对照已经证明该调用在本路径触发 `score` 事件。

### 21.3 `di.on("risk", Ts)` 说明 risk 也是事件通道

静态调用定位：

```text
di.on("risk", Ts)
```

证据：

- AST 搜索输出：`di calls` 中包含 `76528-76544 di.on("risk",Ts)`

证据级结论：

- main SDK 内部存在 `risk` 事件通道。
- 这支持第 17-20 节的判断：captcha/score/cookie 事件通过同一事件总线进入 main SDK，再由不同 handler 处理。
- `Ts` 的具体逻辑还未命名，不能进一步声称 risk 事件如何参与最终评分。

### 21.4 collector POST 外层字段

runtime trace 已捕获 collector 请求：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:25`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:78`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:103`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:127`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:349`

可解析出的外层 form/query 字段：

```text
payload
appId=PXzC5j78di
tag=YjIYfyxJHRR9
uuid=49cc4a30-6373-11f1-89b9-3be640f75297
ft=369
seq=0/1/2/3/4
en=NTA
cs=d6a874e9abbba2e7acc267a78db6f1921a0c250429698c9125908dc5310e6690
pc=<per-request numeric value>
sid=4b399884-6373-11f1-afe0-f0a171acaab4...
p1=05386c34-e98a-664e-0540-f4b1d84f670e
vid=<present on later requests>
cts=<present on later requests>
rsc=1
```

示例：

- line 25：`seq=0`，`post_len=754`
- line 78：`seq=1`，`post_len=8986`
- line 103：`seq=2`，`post_len=6870`
- line 127：`seq=3`，`post_len=10026`
- line 349：`/api/v2/msft/beacon`，`seq=4`，`post_len=2002`

证据级结论：

1. collector 请求是 form/query 风格 POST，外层字段可稳定解析。
2. `seq` 单调递增，说明本轮 collector 上报至少 5 批。
3. `uuid` 与 captcha.js URL 参数 `u=49cc4a30-6373-11f1-89b9-3be640f75297` 一致。
4. `p1` 与 challenge/session id `05386c34-e98a-664e-0540-f4b1d84f670e` 一致。
5. `cs` 与第 19 节事件包中的 `IoIIII|d6a874e9...` 一致。

仍未完成：

- `payload` 字段仍是编码/加密后的主体，当前未解出内部字段。
- `tag/ft/en/pc/cts/rsc` 的业务语义仍未完全命名。
- collector 服务端如何使用这些字段评分仍不可见。


## 22. 2026-06-09 增量：collector `payload` 客户端生成链 `tf -> ut/ne/J/Vs`

本节继续补第 21.4 的 `payload` 内部生成链。目标是还原客户端如何从 activities 生成 collector POST body，不声称服务端如何评分。

### 22.1 `tf(t,e)`：collector form 字段组装函数

静态位置：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:4807`

关键函数：

```js
function tf(t, e) {
  for (var n = eu(), r = 0; r < t.length; r++) {
    var a = t[r];
    a.d["RTE/ewNXNUA="] = xt;
    n && (a.d["O2sBIX4NDBQ="] = n);
    a.d["P28FJXoMCRI="] = yl();
    a.d["YGwaZiUPFVQ="] = ml();
    Fl && (a.d["MkJICHQkQj8="] = Fl);
    var o = Pr();
    o && (a.d["AzN5eUVQckM="] = o, a.d["WQUjDxxjKjU="] = Di());
    var i = Ti.getItem(fi, !1);
    i && (a.d["CXVzP0wWeQQ="] = i);
    var c = Pn("_px3");
    if (c) a.d["GUVjT1wnbn4="] = c;
    else {
      var u = Pn("_px2");
      u && (a.d["NABOSnFiQ3o="] = u);
    }
  }
  ...
  h = Jt(ut(t), [po(), e[on], e[cn]].join(":"));
  d = {vid:Ct(), tag:e[on], appID:e[an], cu:po(), cs:f, pc:h};
  v = Vs(t, d);
  p = [payload=v, appId=e[an], tag=e[on], uuid=po(), ft=e[cn], seq=$l++, en=ql, ...]
  ...
  return p;
}
```

证据级结论：

1. `tf` 输入 `t` 是 activity 列表。
2. 它会给每个 activity 的 `d` 字段补充运行态字段：
   - 当前环境/模式：`xt`
   - `eu()` 返回值
   - `yl()/ml()` 返回的 `Ks` 相关状态
   - `Pr()/Di()` 状态
   - storage 中的 `fi`
   - 当前 cookie `_px3`；如果没有 `_px3`，则尝试 `_px2`
3. `tf` 用 `ut(t)` 序列化完整 activity 列表。
4. `tf` 用 `Jt(ut(t), [po(), tag, uuid].join(":"))` 生成 `pc`。
5. `tf` 用 `Vs(t,d)` 生成最终 `payload`。
6. `tf` 返回的是 form 字段数组，后续 `.join("&")` 后发送。

### 22.2 `ut`：自定义 JSON 序列化

静态位置：

- AST 输出：`ut FunctionDeclaration 7986-8654`

证据级结论：

- `ut(value)` 是自定义 JSON-like serializer。
- 对 string 调用 `ft` 转义。
- 对 Array 递归序列化为 `[...]`。
- 对 Object 遍历 own property，忽略 `undefined`，递归序列化为 `{...}`。

因此 `tf` 里的 `ut(t)` 是把 activity 数组变成稳定字符串。

### 22.3 `ne` 与 `J`：XOR + base64/custom encode

静态位置：

- `ne FunctionDeclaration 13911-14011`
- `J FunctionDeclaration 6105-6622`

`ne`：

```js
function ne(t, e) {
  for (var n = "", r = 0; r < t.length; r++)
    n += String.fromCharCode(e ^ t.charCodeAt(r));
  return n;
}
```

`J`：

```js
function J(t) {
  return ... base64/custom encode ...
}
```

证据级结论：

- `ne(text, key)` 是逐字符 XOR。
- `J(text)` 是 base64/custom encoding。
- `om.decode` 中也使用了 `j(base64 decode) + ne(..., mod)` 反向解码路径；这与第 19 节 `om.decode el=178 mod=50` 对应。

### 22.4 `Vs(t,d)`：生成 `payload` 字段

静态函数：

- AST 输出：`Vs FunctionExpression 77919-78660`

关键行为：

```text
a = t.slice()
o = ne(J(Qi() || fallback), 10)
a = J(ne(ut(a), 50))
i = d[Ns]
c = permutation(o, a.length, i)
payload = insertChars(o, a, c)
return payload
```

证据级结论：

1. `Vs` 先复制 activity 列表。
2. 它把 `ut(activityCopy)` 经 `ne(...,50)` XOR，再经 `J(...)` 编码。
3. 它从 `Qi()` 或 fallback 取一段字符串，经 `J` 和 `ne(...,10)` 生成插入串 `o`。
4. 它根据 `d[Ns]`、payload 长度和插入串计算插入位置。
5. 最终把插入串字符穿插进编码后的 activity 字符串，形成 collector `payload`。

因此 collector POST 的 `payload` 不是直接 JSON；它是：

```text
activityArray
  -> ut(activityArray)
  -> ne(serialized, 50)
  -> J(...)
  -> Vs(...) 插入混淆/校验字符
  -> payload=<result>
```

### 22.5 `Jt`：生成 `pc`

静态函数：

- AST 输出：`Jt FunctionDeclaration 13041-13254`

关键行为：

```text
Jt(text, key):
  n = P(text, key)
  r = split n into printable/high-range chars and numeric mod chars
  return every second char from r
```

在 `tf` 中：

```text
pc = Jt(ut(activityArray), [po(), tag, uuid].join(":"))
```

证据级结论：

- `pc` 是由序列化后的 activity 数组和 `[clientUuid, tag, uuid]` 共同派生出的校验/摘要字段。
- 本轮 runtime trace 中 `pc` 每个 collector 请求不同，符合它依赖 activity 内容的证据。

### 22.6 `Fv`：追加 seq

静态函数：

- `Fv FunctionDeclaration 175695-175733`

```js
function Fv(t) {
  return t += "&" + Xr + ++wv;
}
```

证据级结论：

- `Fv` 不生成 payload，只是在发送前追加递增序号字段。
- 本轮 runtime trace 中 collector 请求 `seq=0/1/2/3/4` 与该逻辑一致。

### 22.7 当前 collector payload 可还原程度

结合第 19-22 节，collector 上报链路可还原为：

```text
main SDK 收集 activity
  -> tf(activityArray, np)
      -> 给 activity.d 补运行态字段和 _px3/_px2
      -> serialized = ut(activityArray)
      -> pc = Jt(serialized, [clientUuid, tag, uuid].join(":"))
      -> payload = Vs(activityArray, {vid,tag,appID,cu,cs,pc})
           -> encoded = J(ne(ut(activityArray), 50))
           -> insertString = ne(J(Qi() || fallback), 10)
           -> 按 d[Ns] 派生位置穿插 insertString
      -> form fields: payload/appId/tag/uuid/ft/seq/en/cs/pc/sid/p1/vid/cts/rsc...
  -> Fv(postData) 追加 seq
  -> XHR or sendBeacon POST 到 collector
```

仍未完成：

1. `P`、`Qi`、`Ns`、`Xs` 字符串表的全部语义未完全命名。
2. `payload` 可逆解码工具还未实现；当前只还原了生成算法的静态结构。
3. 服务端如何校验 `payload/pc/_px3/_pxde` 仍不可见。

## 23. 新增运行时插桩：`tf(activityArray,e)` payload 构造前字段与失败样本对照

本节基于 2026-06-09 04:08:15 后新增的观测插桩，只改了观测层：

- `CTF-reg/outlook_browser_register.py:1375-1390`
  - `main_tf_enter`
  - `main_tf_payload`
- 编译验证：
  - `.venv/bin/python -m py_compile CTF-reg/outlook_browser_register.py`
- 分析工具更新：
  - `tools/analyze_hsprotect_full_chain.mjs`
  - `node --check tools/analyze_hsprotect_full_chain.mjs`

### 23.1 新失败样本文件

本轮采样命令：

```bash
OUTLOOK_HSPROTECT_JS_PATCH=1 REGISTER_ONLY_MAX_ATTEMPTS=1 OUTLOOK_HEADLESS=1 OUTLOOK_SKIP_WEBMAIL_INIT=1 OUTLOOK_BROWSER_OAUTH_TIMEOUT_S=240 OUTLOOK_OAUTH_DENIED_RETRIES=1 WEBUI_REG_METHOD=portal_browser .venv/bin/python -u pipeline.py --config CTF-pay/config.paypal.json --register-only --register-method portal_browser --cardw-config CTF-reg/config.paypal-proxy.json
```

运行产物：

- run log: `output/run_logs/hsprotect_tf_trace_20260609_040815.log`
- JS trace: `output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl`
- runtime trace: `output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl`
- 汇总报告: `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md`

运行入口证据：

- `output/run_logs/hsprotect_tf_trace_20260609_040815.log`
  - `04:08:20`：`hsprotect JS patch enabled label=main`
  - `04:08:33`：`main.min.js patches=[..., '__outlook_hsprotect_patch_main_tf_enter__', '__outlook_hsprotect_patch_main_tf_payload__']`
  - `04:09:03`：`captcha.js patches=['__outlook_hsprotect_patch_captcha_zt_enter__', '__outlook_hsprotect_patch_captcha_ot_enter__', '__outlook_hsprotect_patch_captcha_qs_pow__', '__outlook_hsprotect_patch_captcha_worker_new__']`

### 23.2 `tf.payload` 已抓到 payload 构造前字段

失败样本汇总：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:7-25`
  - `hsprotect.main.tf.enter: 6`
  - `hsprotect.main.tf.payload: 6`
- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:34-42`
  - 6 条 `tf payload events`

第一条 collector payload 构造事件：

- JS trace 原文：`output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:32`
- runtime trace 原文：`output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl:26`
- 对应 network POST：`output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl:27`

关键字段：

```json
{
  "activityCount": 1,
  "activityTypes": ["GCQiLl1BJhk="],
  "meta": {
    "tag": "YjIYfyxJHRR9",
    "appID": "PXzC5j78di",
    "cu": "d347af50-6375-11f1-b31a-c1d900f88e04",
    "pc": "1462244708120922"
  },
  "pc": "1462244708120922",
  "serializedLen": 421,
  "payloadLen": 584
}
```

同一 payload 在 network 层出现：

- `output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl:27`
  - URL: `https://collector-pxzc5j78di.hsprotect.net/api/v2/msft`
  - `post_len=754`
  - POST body 含：
    - `appId=PXzC5j78di`
    - `tag=YjIYfyxJHRR9`
    - `uuid=d347af50-6375-11f1-b31a-c1d900f88e04`
    - `pc=1462244708120922`
    - `p1=19c154a1-0d0e-6906-9593-618f309a23de`

证据级结论：

- 第 22 节静态还原的 `tf -> Vs -> Jt -> form fields` 链已经被运行时插桩验证。
- `tf.payload` 中的 `meta.pc` 与 network POST body 的 `pc` 一致。
- `tf.payload` 中的 `meta.appID/tag/cu` 与 network POST body 的 `appId/tag/uuid` 一致。
- 这不是推断；对应 JS trace、runtime trace 与 network POST 三方可对齐。

### 23.3 `tf.payload` 不等于挑战成功

失败样本中，collector 上报完整发生：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:34-42`
  - 6 次 `tf.payload`
- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:107-110`
  - 4 次 `https://collector-pxzc5j78di.hsprotect.net/api/v2/msft` POST，均 200

但同一失败样本没有成功事件：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:27-29`
  - `Ot events` 表为空
- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:111-112`
  - `risk/verify` 返回 200，但 flags 为空，没有 `state_continue`
- `output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:250`
  - parent 收到的是：

```json
{"type":"block","jsonResponse":{"vid":"d4177fcc-6375-11f1-b313-8e2a4593841f","uuid":"d347af50-6375-11f1-b31a-c1d900f88e04"},"requestUrl":"/api/v1.0/risk/verify"}
```

随后 CreateAccount 失败：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:113-114`
- `output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl:293`
  - `CreateAccount` request
- `output/outlook_browser/runtime_trace_hcxwyrtiudbg_1780949301.jsonl:295`
  - `CreateAccount` response contains `error.code="1059"`

证据级结论：

- collector payload 上报、`_px3/_pxde/_pxvid` 写入、`score=1` 都不足以证明 HUMAN challenge 成功。
- 成功判定至少还需要看到：
  1. captcha 内部 `Ot(r=0)`；
  2. parent 收到 `{"type":"succeeded"}`；
  3. Microsoft `risk/verify` 返回 `state:"continue"`；
  4. `CreateAccount` 返回 `redirectUrl`。

### 23.4 成功样本对照：真正闭环发生的位置

成功样本：

- JS trace: `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl`
- runtime trace: `output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl`
- 汇总报告: `output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md`

成功闭环证据：

1. captcha 内部成功：
   - `output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md:27-30`
   - `Ot events`
   - `line 323 | r=0 | state=succeeded | n=_px3 | t=330 | v length=671`
2. parent 收到 succeeded：
   - `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:332`
   - `{"type":"succeeded"}`
3. Microsoft risk 放行：
   - `output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md:138-139`
   - `risk/verify` 第二次 response flags: `state_continue`
   - runtime 原文：`output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:345`
4. CreateAccount 成功：
   - `output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md:140-141`
   - `CreateAccount` response flags: `redirectUrl`
   - runtime 原文：`output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:347`

对比失败样本：

| 环节 | 成功样本 `ni109xdjp5zp` | 失败样本 `hcxwyrtiudbg` |
|---|---|---|
 collector `/api/v2/msft` | 有 | 有 |
 `_px3/_pxde` cookie message | 有 | 有 |
 `score=1` | 有 | 有 |
 `captcha.Ot.enter r=0 state=succeeded` | 有，`full_chain_ni...md:27-30` | 无，`full_chain_hc...md:27-29` |
 parent `type=succeeded` | 有，`js_internal_trace_ni...jsonl:332` | 无 |
 parent `type=block` | 前置出现过一次，后续成功覆盖 | 有，`js_internal_trace_hc...jsonl:250` |
 `risk/verify state_continue` | 有，`runtime_trace_ni...jsonl:345` | 无 |
 `CreateAccount redirectUrl` | 有，`runtime_trace_ni...jsonl:347` | 无 |
 `CreateAccount error.code=1059` | 无 | 有，`runtime_trace_hc...jsonl:295` |

### 23.5 对“全量算法”的当前边界修正

已由证据闭环确认的部分：

```text
activity collection
  -> tf(activityArray,e)
  -> serialized=ut(activityArray)
  -> pc=Jt(serialized,[cu,tag,uuid])
  -> payload=Vs(activityArray,{vid,tag,appID,cu,cs,pc})
  -> POST collector /api/v2/msft
  -> collector response ob
  -> fp("xhrResponse", ob)
  -> om decode
  -> jl dispatch Xl handlers
  -> Xn.trigger risk/score/enrich
  -> cookie messages _px3/_pxde/_pxvid
```

但这条链只说明“采集与 cookie 生成链”成立。

成功闭环必须额外满足：

```text
captcha.js Ot(r=0)
  -> zt("succeeded")
  -> parent postMessage {"type":"succeeded"}
  -> Microsoft risk/verify state="continue"
  -> CreateAccount redirectUrl
```

当前仍不能声称已还原的部分：

1. 服务端如何根据 collector payload、`_px3/_pxde`、captcha token 判断 `risk/verify state=continue`；
2. `Ot(r=0)` 之前 captcha 内部如何综合按压事件、worker/pow、token 得到最终成功；
3. `payload` 可逆解码工具还没有实现；但现在已有 `tf.payload` 插桩，能直接记录 payload 构造前的 `activityArray/serialized/meta`，不再只能猜测 POST body。

## 24. captcha.js 状态机：`Ot -> kt/Qt`、延迟跳转与成功消息

本节只使用本地静态源码和运行时 trace，不推断不可见服务端逻辑。

### 24.1 静态位置

源码文件：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js`
- `output/outlook_browser/js_static_analysis/stack_map/captcha_Ot.function.js`
- `output/outlook_browser/js_static_analysis/stack_map/captcha_zt.function.js`
- `output/outlook_browser/js_static_analysis/string_decode/captcha_ot_branch_decode.md`

关键函数与变量位置：

| 符号 | 位置 | 证据 |
|---|---:|---|
| `Kt` | `captcha.beautified.js:4752` | `var wt, Kt = 2500` |
| `qt` | `captcha.beautified.js:4754` | `qt = false` |
| `At` | `captcha.beautified.js:4762` | `var At, gt, jt = ...` |
| `Ut` | `captcha.beautified.js:4771` | `Ut = false` |
| `kt` | `captcha.beautified.js:4932-4987` | post-result continuation handler |
| `Qt` | `captcha.beautified.js:4989-5023` | alternate post-result continuation handler |
| `Ot` | `captcha.beautified.js:5064-5084` | captcha result callback |
| `poi/qs` worker POW | `captcha.beautified.js:8299-8307` | `sha256(z) === s` and `postMessage(z)` |
| `Ot` installed | `captcha.beautified.js:11073-11099` | `window[L][...]=Ot` |

### 24.2 `Ot(r,n,t,v)` 的直接语义

源码证据：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js:5064-5084`
- 解码证据：
  - `output/outlook_browser/js_static_analysis/string_decode/captcha_ot_branch_decode.md`

已解码字段：

| 表达式 | 解码 |
|---|---|
| `0 === r ? ... : ...` | `r=0 -> succeeded`, 非 0 -> failed |
| `e(1155,1184)` | `status` |
| `e(1184,1252)` | `token` |
| `e(1147,1081)` | `verificationFailed` |
| `u("NV8XFA")` | `bind` |
| `u("PkU0HwwBODJgEBUZGDslQi4ZChw8")` | `isMobileViewportWidth` |

`Ot` 的行为，按源码顺序：

```text
clearTimeout(At)
r = parseInt(r)
zt(r === 0 ? "succeeded" : "failed")
if r === 0 && B() && isMobileViewportWidth:
    setTimeout(W, Kt - T)
Hn.verificationFailed = Kn() && r === -1
Ut = true
i = setTimeout.bind(null, qt ? Qt : kt, Kt)
token = n && t && v ? n + "|" + t + "|" + v : ""
payload = {status: r}
if token:
    payload.token = token
i(payload, true)
```

证据级结论：

- `Ot` 是 captcha 结果入口。
- `r=0` 是本地 JS 层成功分支；该事实由静态解码和成功运行时共同证明。
- `Ot` 不直接调用 Microsoft `risk/verify`；它先触发本地 UI/message 状态，再把 `{status, token?}` 交给 `kt` 或 `Qt`。

### 24.3 `zt`：向外发送状态文本

源码证据：

- `output/outlook_browser/js_static_analysis/stack_map/captcha_zt.function.js`

`zt` 函数体：

```js
function(r) {
  function n(r, n) {
    return mt(r - -665, n);
  }
  try {
    R()[window[v(n(-420, -426))]][v(n(-410, -403))][v(n(-422, -429))](v(n(-417, -412)), r);
  } catch (r) {}
}
```

结合运行时证据：

- 成功样本：`output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md:27-30`
  - `Ot line 323 | r=0 | state=succeeded`
- 成功样本 parent message：
  - `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:332`
  - `{"type":"succeeded"}`
- 失败样本：
  - `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:27-29`
  - `Ot events` 空
  - `output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:250`
  - `{"type":"block",...,"requestUrl":"/api/v1.0/risk/verify"}`

证据级结论：

- 成功样本能看到 `Ot(r=0)` 与 parent `type=succeeded` 同链出现。
- 失败样本即使已经写入 `_px3/_pxde`，没有 `Ot(r=0)`，最终 parent 仍是 `type=block`。

### 24.4 `Kt=2500` 与 `kt/Qt` 延迟执行

源码证据：

- `captcha.beautified.js:4752`: `Kt = 2500`
- `captcha.beautified.js:5072`: `setTimeout.bind(null, z ? Qt : kt, Kt)`
- `captcha.beautified.js:4989-5023`: `Qt(r)`
- `captcha.beautified.js:4932-4987`: `kt(r)`

静态结论：

- `Ot` 收到结果后不是立刻跳转/退出，而是通过 `setTimeout(..., Kt)` 延迟执行后续处理。
- 在当前静态源码中 `qt=false`，因此默认路径是 `kt`；如果运行时把 `qt` 改为 true，则进入 `Qt`。

`Qt(r)` 证据：

- `captcha.beautified.js:5005-5022`
  - 如果 `r.status === 0`，调用 `St(Ln(), dt, encodeURIComponent(r.token || ""))`
  - 构造 query string
  - 拼到 `jt` 或 `yt` URL 后
  - 写入 `R().location = s`
  - 如存在外部窗口回调 `t`，调用 `t(v)`

`kt(r)` 证据：

- `captcha.beautified.js:4932-4987`
  - 先记录耗时/状态：`Pt[...] = true`, `Pt[...] = Math.floor((m() - Gt) / 1000)`, `$t()`
  - 若 `r.status === 0`：
    - `St(Ln(), dt, encodeURIComponent(r.token || ""))`
    - 条件满足时 `_t(f)`、`V(t)` 或 `F()`
  - 非成功或其它环境分支会触发 `Wt()`、窗口 close、`F()` 等路径

证据级结论：

- `Kt=2500` 是 captcha 结果后处理延迟，不是按压时长。
- 成功判定的本地入口是 `Ot(r=0)`；`kt/Qt` 是收到该结果后的“落地处理/跳转/关闭/通知”路径。

### 24.5 `Ot` 是由 HUMAN 内部回调安装，不是 DOM 按钮直接调用

源码证据：

- `captcha.beautified.js:11073-11099`

关键片段：

```text
Ts(function(n,v,e) {
    At = setTimeout(function(){ Ft() }, ht)
    ...
    window[L][...](z)
    window[L][...] = Ot
})
```

证据级结论：

- 页面上的长按 DOM 只是输入源。
- `Ot` 是 HUMAN captcha SDK 在内部流程里挂到 `window[L]` 的回调。
- 因此“只找到按钮并按住”不是完整算法；必须看到内部 SDK 最终调用 `Ot(0, n, t, v)`，并产生 token。

### 24.6 POW worker 只证明存在计算任务，当前还不能证明它决定成功

源码证据：

- `captcha.beautified.js:8299-8307`

```text
poi(r,n,u,t,v,e,f,s):
    m = (u + (r & n).toString(16)).slice(-t)
    z = e + (v + (r >> (t << 2))).toString(16) + m
    if sha256(z) === s:
        return z

qs(...):
    for i in [r,n]:
        if poi(...):
            postMessage(z)
    postMessage(false)
```

成功运行时证据：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md:18-21`
  - `hsprotect.captcha.worker.new: 5`
  - `hsprotect.captcha.qs.start: 4`
  - `hsprotect.captcha.pow.hit: 1`
  - `hsprotect.captcha.worker.message: 1`

失败运行时证据：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:7-25`
  - 没有 `hsprotect.captcha.worker.new`
  - 没有 `hsprotect.captcha.qs.start`
  - 没有 `hsprotect.captcha.pow.hit`
  - 没有 `hsprotect.captcha.Ot.enter`

证据级结论：

- POW worker 是成功样本出现、失败样本缺失的关键差异之一。
- 但当前证据只能证明它参与成功路径，不能证明它单独决定成功；最终放行仍以 `Ot(r=0) -> succeeded -> risk/verify state_continue` 为准。

### 24.7 当前对 captcha 内部链路的可证实版本

结合第 23 和第 24 节，目前可证实的端到端链路是：

```text
页面长按输入
  -> HUMAN captcha SDK 内部事件/计算
  -> POW worker qs/poi 可能产出 sha256 命中值
  -> SDK 内部回调 window[L][...] = Ot
  -> Ot(0,n,t,v)
      -> zt("succeeded")
      -> token = n + "|" + t + "|" + v
      -> setTimeout(kt or Qt, 2500, {status:0, token}, true)
  -> parent 收到 {"type":"succeeded"}
  -> Microsoft risk/verify 返回 {"state":"continue"}
  -> signup CreateAccount 返回 redirectUrl
```

仍未完成的证据缺口：

1. `Ts(...)` 内部如何从 pointer/mouse/worker/network 结果算出传给 `Ot` 的四个参数；
2. 成功样本里 `Ot(0,n,t,v)` 的 `n/t/v` 原始值已在 `Ot.enter` 捕获为字符串，但还没有完整命名其字段语义；
3. `qt` 在当前源码默认 `false`，但是否存在运行时修改为 true 的样本，需要更多运行时 trace 证明；
4. `Kt=2500` 已确认是结果后处理延迟，但不是挑战需要按压的目标时长；按压结束由 SDK 内部回调决定。

## 25. 成功样本的 `POW -> main oIIoIooo/Wc -> captcha Ot` 运行时链

本节补第 24 节的运行时证据：成功样本中 `Ot(0,...)` 的直接调用栈来自 `main.min.js` 的 `oIIoIooo/Wc` handler，而不是 captcha DOM 事件直接调用。

### 25.1 成功样本的 POW 参数与命中值

成功样本文件：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl`

成功样本中出现 4 个 POW worker range：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:260`
  - `from=65537`
  - `to=131073`
  - `mask=65535`
  - `len="0000"`
  - `prefix=4`
  - `salt=4`
  - `target=1366f5750ad186bb8cc594ad8c6357ce1330456ffd437fc907981b3d25cda2b6`
- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:261`
  - `from=196611`
  - `to=262144`
- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:262`
  - `from=131074`
  - `to=196610`
- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:263`
  - `from=0`
  - `to=65536`

命中值：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:272`

```json
{
  "i": 50239,
  "value": "218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f"
}
```

worker message：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:273`

```json
{
  "url": "blob:https://iframe.hsprotect.net/16a30791-95a5-401d-98ca-1fe58f9aaf19",
  "data": "218e34c1d956511db78149accdfacd205367d5b910c4e14b347640ac7564c43f"
}
```

静态算法证据：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js:8299-8307`

```text
z = salt + (prefix + (i >> (len << 2))).toString(16) + (len + (i & mask).toString(16)).slice(-len)
if sha256(z) === target:
    postMessage(z)
```

证据级结论：

- 成功样本里确实出现了 POW 命中；
- 命中值来自 worker 扫描区间 `[0,65536]` 中的 `i=50239`；
- 该命中值随后通过 worker `message` 回到 captcha 页面。

### 25.2 失败样本没有 POW/Ot，只到 rendered

失败样本：

- `output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl`

唯一 captcha 状态：

- `output/outlook_browser/js_internal_trace_hcxwyrtiudbg_1780949301.jsonl:208`

```json
{
  "kind": "hsprotect.captcha.zt.enter",
  "arg": "rendered"
}
```

失败样本汇总：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_hcxwyrtiudbg_1780949301.md:7-25`
  - 没有 `hsprotect.captcha.worker.new`
  - 没有 `hsprotect.captcha.qs.start`
  - 没有 `hsprotect.captcha.pow.hit`
  - 没有 `hsprotect.captcha.Ot.enter`

证据级结论：

- 失败样本不是“POW 算错后失败”，而是当前 trace 中没有进入 POW/Ot 成功路径。
- 它只证明 captcha rendered、collector/cookie 链存在，不能证明人机挑战完成。

### 25.3 `Ot(0)` 直接调用栈来自 main SDK handler

成功样本 `Ot.enter`：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323`

关键字段：

```json
{
  "r": 0,
  "n": "_px3",
  "t": "330",
  "state": "succeeded",
  "zero": true
}
```

`v` 是完整 `_px3` 值：

```text
100eeaef9e4fa0be72e5b1ad720f34ea469c227fe683e73e85476f154369ff13:OeL4AXRLHbcohJH54ug50tH0J1Y/p8cjPVmqSkdkFRtKt6UvWid8BruKFAjanV6m8r2zvqyb52HfnR2RDUhjUg==:1000:SobkZaNDbqowE8Pz0wgiT2FNLTFRqQ73JGXQhOv5I8BWEI0PZDy/DJ6G3Cm/B938fsSOy15FXKX26i33U2Jjr0OAI3mhAI9X3gHae749x/FXopvx15gx8NK4gSFnl/Yz2DCWCKx/c+MVXw7pgE1mSMty+g8dQ9FQUaGukOUKLrOkPGKBRBChu2glVNKCHOL9/wc6rFLBSNpv+klPJ9mObC56IFouTmmvq2D0/NTTuW3wevcYSFBQo63tLUhuHyhR+ZSHXF09LZkLiDpK/IRz1MRUG+yFV39b/l9RWAndT5IPQEQb35MmbEuloF2ovjm7AV5eqsVp/a6C4DA+ze7gLlYII/i8G4+HyEd/w0k7i1gRKrG7eifTrXxovnpw2gI9fv3CbKHJKkKv3H+f/3PaaYt2QXCA0Vlo+tKFN0q9ylIQEo6aneIv7waIwnZzjzjc8mpTApjCTw0BqA8TiqGLcXCm30OPKduHVcwI2rO2F/ROWh7wB8oJ5rOji0O5T1lT
```

调用栈：

```text
Ot@captcha.js:1724:84168
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
jl@main.min.js:3:36718
om/<@main.min.js:3:127749
om@main.min.js:3:127765
trigger@main.min.js:2:17431
fp@main.min.js:3:121347
xv/h.onload@main.min.js:3:114990
```

静态映射：

- `output/outlook_browser/js_static_analysis/stack_map/summary.md`
  - `main_Wc`: `Wc / FunctionDeclaration`
  - `main_oIIoIooo`: `oIIoIooo / FunctionExpression`
  - `main_jl`: `jl / FunctionDeclaration`
  - `main_om`: `om / FunctionDeclaration`
  - `main_fp`: `fp / FunctionDeclaration`

证据级结论：

- `Ot(0)` 的直接上游是 main SDK 解码后的 Xl handler `oIIoIooo`，中间经 `Wc` 调用 captcha 回调。
- 所以成功路径是“collector response 解码出 `oIIoIooo|0`，main SDK 调用 captcha 回调 `Ot(0,...)`”，而不是 captcha worker 单独决定后直接成功。

### 25.4 `oIIoIooo|0` 与成功后第二个 `score=0`

成功样本中 `om.decode` 后出现：

- `output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md`
  - decoded event packet line 306:

```text
IoIoIo|score|1|binary
IoIIIo|cu
oIIoIIoo|_pxde|330|...
oIIoIooo|0
IoooII|_px3|330|100eeaef...
IoIoIo|score|0|binary
```

运行时 `Ot.enter` 紧跟该 packet：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323`
  - `Ot r=0 state=succeeded`

证据级结论：

- `oIIoIooo|0` 是当前成功样本中触发 `Ot(0)` 的关键 decoded event；
- `IoooII|_px3|...` 提供传给 `Ot` 的 `_px3` 字段；
- `score=0` 在这里并不等于失败，因为同一批事件随后触发了 `Ot(0)` 和 parent `succeeded`。因此不能把 `score` 单独当成最终结果。

### 25.5 当前可还原的 HUMAN 内部执行闭环

把第 19-25 节串起来，当前有证据支持的闭环是：

```text
1. main SDK collector 上报:
   tf(activityArray,e)
     -> serialized/meta/payload/pc
     -> POST collector /api/v2/msft

2. collector response:
   fp("xhrResponse", ob)
     -> om decode
     -> jl dispatch decoded event packets

3. 普通 cookie/state event:
   IoooII|_px3|...
   oIIoIIoo|_pxde|...
   IoIoIo|score|...
   -> Xn.trigger risk/enrich/score
   -> parent cookie messages

4. 成功关键 event:
   oIIoIooo|0
   IoooII|_px3|330|<px3>
   -> Xl handler oIIoIooo
   -> Wc
   -> captcha Ot(0, "_px3", "330", <px3>)
   -> zt("succeeded")
   -> parent {"type":"succeeded"}
   -> risk/verify state="continue"
   -> CreateAccount redirectUrl
```

仍不可见/不能断言：

- collector 服务端如何决定返回 `oIIoIooo|0`；
- `POW hit` 是否是服务端返回 `oIIoIooo|0` 的必要条件；
- `score=0/1` 的服务器语义，当前只能按事件流观察，不能用它单独判定成败。

## 26. `Ts` 与 captcha 启动入口：回调注册、就绪轮询、对外暴露函数

本节继续把 `Ot` 的上游还原到 `Ts` 和 challenge 启动入口，但只到源码可证实的边界。

### 26.1 `Ts(r)` 是就绪轮询包装

源码：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js:8585-8590`

```js
function Ts(r) {
  if (Ms) return r(Gs, Es, Ps);
  setTimeout((function() {
    Ts(r)
  }), 500)
}
```

证据级结论：

- `Ts` 自身不计算挑战结果；
- `Ts` 只做 readiness gate：
  - `Ms` ready 时调用传入回调，参数是 `Gs, Es, Ps`；
  - 未 ready 时每 500ms 重试；
- 因此 `Ts(...)` 是把后续函数挂到“captcha SDK 已就绪”之后执行的包装层。

仍未命名：

- `Ms/Gs/Es/Ps` 的字段语义还没有完全追到赋值点；当前不能给它们强行命名。

### 26.2 challenge 启动入口 `Ls.PlgQBA`

源码：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js:8148-8211`

片段：

```text
(r = {}).PlgQBA = function(r,e,f,z,c) {
    Hn[...] = r
    Hn[...] = e[...]
    Hn[...] = f
    Hn[...] = m()
    Hn[...] = i()
    Hn[...] = z
    Hn[...] = c
    Kf(...)
    we(true, document...)
    ...
    window[Su()][...]=t
}
```

从静态源码可证实：

- `Ls.PlgQBA` 接收 5 个参数；
- 它把这些参数写入 `Hn` 状态对象；
- 它调用 `Kf(...)` 渲染/初始化 captcha；
- 它调用 `we(true, document...)` 改变页面状态；
- 它还尝试从 `performance` entries / resource timing 中提取数据；
- 最后把内部函数 `t` 赋给 `window[Su()][...]`，供外部触发。

结合调用点：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js:11031`

```text
nv() || Ls.PlgQBA(jz, {...}, D, Mz, Gz)
```

证据级结论：

- `Ls.PlgQBA` 是 challenge 交互启动入口之一；
- 它不是最终成功判定函数，而是把 challenge 所需上下文写进 `Hn` 并安装后续回调。

### 26.3 `Ts` 回调里安装 `Ot`

源码：

- `output/outlook_browser/js_static_analysis/captcha.beautified.js:11073-11099`

可读链路：

```text
Ts(function(n, v, e) {
    At = setTimeout(function(){ Ft() }, ht)
    ...
    if Ou() is function:
        i("...", r)
    window[L][...](z)
    window[L]["B25ORlo"] = Ot
})
```

证据级结论：

- `Ot` 是在 `Ts` ready 后安装到 `window[L]` 上；
- 安装前还设置了超时兜底 `At = setTimeout(Ft, ht)`；
- 成功样本中 `Ot.enter` 的 stack 不是从 `Ts` 直接出现，而是后续由 main SDK 的 `Wc/oIIoIooo` 调用：
  - `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323`

### 26.4 `Wc` 和 `oIIoIooo` 的静态函数体

源码映射：

- `output/outlook_browser/js_static_analysis/stack_map/main_Wc.function.js`
- `output/outlook_browser/js_static_analysis/stack_map/main_oIIoIooo.function.js`
- `output/outlook_browser/js_static_analysis/full_chain/handler_Xl_oIIoIooo.js`

`Wc`：

```js
function Wc(t, e, n, r) {
  var a = yc,
    o = Lc(),
    i = o && o[a(255)];
  i && i(t, e, n, r);
}
```

`oIIoIooo`：

```js
function(t) {
  var e = { F: 241, b: 247 },
    n = Tl;
  if (Ul) return;
  var r = _l(this[xn]);
  Wc[n(e.F)](this, r ? [t][n(e.b)](r) : [t]);
}
```

证据级结论：

- `oIIoIooo` 把 decoded event 参数 `t` 与 `this[xn]` 中保存的附加参数合并；
- 它随后调用 `Wc`；
- `Wc` 从 `Lc()` 返回对象里取一个函数并调用；
- 运行时上这条链正好对应：

```text
oIIoIooo -> Wc -> Ot
```

运行时证据：

- `output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323`

```text
Ot@captcha.js:1724:84168
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
jl@main.min.js:3:36718
om/<@main.min.js:3:127749
om@main.min.js:3:127765
trigger@main.min.js:2:17431
fp@main.min.js:3:121347
xv/h.onload@main.min.js:3:114990
```

### 26.5 当前精确定义：什么是“全量”已还原，什么还没有

已还原到函数级且有证据：

1. collector payload 生成：
   - `tf -> ut/Jt/Vs -> POST /api/v2/msft`
   - 证据：第 22、23 节。
2. collector response 解码：
   - `fp -> om -> jl -> Xl handler`
   - 证据：第 19、21、25 节。
3. cookie/state 写入：
   - `IoooII/oIIoIIoo/IIooII/oIooII -> Wn/Gn/lr/er`
   - 证据：第 19、20 节。
4. captcha 成功回调：
   - `oIIoIooo -> Wc -> Ot(0) -> zt("succeeded")`
   - 证据：第 24、25、26 节。
5. Microsoft 放行闭环：
   - `parent succeeded -> risk/verify state_continue -> CreateAccount redirectUrl`
   - 证据：第 23、25 节。

仍未完全还原：

1. `Ms/Gs/Es/Ps` 的赋值链；
2. `Lc()` 返回对象与 `o[a(255)]` 的精确属性名；
3. collector 服务端为什么返回 `oIIoIooo|0`；
4. Microsoft `risk/verify` 服务端如何结合 `_px3/_pxde/_pxvid`、token、continuationToken 做最终放行。

这些缺口当前没有足够本地证据，不能猜。
### 27. 补齐 `Wc -> window[_zC5j78dihandler].PX764 -> Ot` 与 `Ms/Gs/Es/Ps` 就绪门证据

本节只记录本地可证实内容，修正上一节“仍需追”的两个本地缺口。

#### 27.1 `Wc()` 不是直接调用全局 `Ot`，而是通过共享 handler 容器调用 `PX764`

静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:408`
  - `bt = "PXzC5j78di"`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:2937-2941`
  - `Wc(t,e,n,r)` 执行：
    - `o = Lc()`
    - `i = o && o[a(255)]`
    - `i && i(t,e,n,r)`
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:2958-2960`
  - `Lc()` 返回 `r[zc()]`，这里 `r` 是 main SDK IIFE 入参里的 window/global 对象。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/main.beautified.js:3055-3059`
  - `zc()` 返回 `"_" + bt.replace(/^PX|px/, "") + handler`。
  - 对当前 `bt="PXzC5j78di"`，可还原为 `_zC5j78dihandler`。

字符串表解码证据：

```text
244 -> handler
255 -> PX764
```

解码依据是 `main.beautified.js:2874-2884` 对 `Dc()` 表做 rotate 后，`_c(t)` 使用 `Dc()[t-219]`；本轮本地解码命令输出：

```text
244 -> arr[25] = "handler"
255 -> arr[36] = "PX764"
```

因此 `Wc()` 的可证实调用目标是：

```text
window["_zC5j78dihandler"]["PX764"](t, e, n, r)
```

captcha 侧静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:4455-4461`
  - `Su()` 返回 `"_" + window._pxAppId.replace(/px|PX/,"") + "handler"`。
  - 当前 `window._pxAppId=PXzC5j78di` 时，同样是 `_zC5j78dihandler`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11065-11099`
  - `L = Su()`
  - `window[L][...] = Ot`
- 本地解码 `captcha.beautified.js` 的 `u()` 字符串：

```text
B25ORlo => PX764
```

所以 captcha 侧实际安装的是：

```text
window["_zC5j78dihandler"]["PX764"] = Ot
```

运行时闭环证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:322`
  - `jl.dispatch` 派发 `handlerKey="oIIoIooo"`，参数 `["0"]`。
- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323`
  - `Ot.enter` 调用栈：

```text
Ot@captcha.js:1724:84168
Wc@main.min.js:3:5296
oIIoIooo@main.min.js:3:32384
jl@main.min.js:3:36718
om/<@main.min.js:3:127749
om@main.min.js:3:127765
trigger@main.min.js:2:17431
fp@main.min.js:3:121347
xv/h.onload@main.min.js:3:114990
```

结论：

- `oIIoIooo|0` 不是直接调用 `Ot`。
- 它通过 `oIIoIooo -> Wc -> window["_zC5j78dihandler"]["PX764"] -> Ot(0, ...)` 进入 captcha 成功分支。
- 这个结论同时有 main 静态代码、captcha 静态代码、字符串解码、成功样本运行时栈四类证据。

#### 27.2 `Ts(r)` 的 `Ms/Gs/Es/Ps` 含义边界

静态证据：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8481-8488`

```js
var js, ys = Su(),
  Ms = !0,
  Gs = !1,
  Ps = null,
  Es = null,
  Zs = !1,
  bs = 1,
  hs = !1;
```

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8490-8492`

```js
function Us(r, n) {
  Ps = r, Es = m() - n, Ms = !0
}
```

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8494-8499`

```js
function Cs(r, n, t) {
  ...
  Ms = !1, Zs = !1;
  var f = m(),
```

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8525-8531`

```js
r && r[...] && -1 !== r[...][...](...) && (Gs = !0)
Zs = !0;
```

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:8585-8590`

```js
function Ts(r) {
  if (Ms) return r(Gs, Es, Ps);
  setTimeout(function() {
    Ts(r)
  }, 500)
}
```

可证实解释：

- `Ms` 是 `Ts()` 的就绪门：`Ms=true` 时立即调用回调；`Ms=false` 时每 500ms 递归等待。
- `Cs(...)` 开始时把 `Ms=false`，说明后续存在异步计算/检测阶段。
- `Us(r,n)` 把 `Ps=r`、`Es=m()-n`、`Ms=true`，说明它完成后向 `Ts` 回调提供两个值：一个结果对象/结果值 `Ps`，一个耗时 `Es`。
- `Gs` 初始为 `false`，在 `Cs` 内部某个异常/特征分支命中时置为 `true`；当前本地证据只能证明“某条件命中标志”，不能给它命名为具体浏览器风险类型。

和成功分支的关系：

- `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/captcha.beautified.js:11073-11099`
  - captcha 启动入口在 `Ts((function(n, v, e) { ... }))` 的回调里继续初始化，并最终安装 `window[L]["PX764"] = Ot`。
- 因此 `Ts/Ms/Gs/Es/Ps` 是 captcha 初始化前置就绪门；它不是 `succeeded/failed` 结果本身。
- 真正进入成功/失败分支仍以 `Ot(r, n, t, v)` 的 `r===0` 为准；这一点已由 `captcha.beautified.js:5064-5084` 和成功样本 `js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323-325` 证明。

#### 27.3 当前可还原闭环与仍不可见边界

本轮补齐后，客户端可还原闭环为：

```text
collector 返回编码包
  -> main fp/up 收到 xhrResponse/xhrSuccess
  -> om 解码
  -> jl 按 handler 表派发
  -> Xl.oIIoIooo("0")
  -> Wc("0", "_px3", "330", token)
  -> window["_zC5j78dihandler"]["PX764"](...)
  -> captcha Ot(0, "_px3", "330", token)
  -> zt("succeeded")
  -> Xn.trigger("captcha", "succeeded")
  -> iframe parent postMessage {"type":"succeeded"}
  -> Microsoft /API/Proofs/risk/verify 返回 state=continue
  -> /API/CreateAccount 返回 redirectUrl
```

对应证据：

- `collector 返回编码包 -> decoded event packet`：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_static_analysis/full_chain/full_chain_ni109xdjp5zp_1780948211.md`
- `oIIoIooo -> Wc -> Ot`：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:322-323`
- `Ot -> zt -> captcha succeeded`：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:323-325`
- `postMessage succeeded`：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/js_internal_trace_ni109xdjp5zp_1780948211.jsonl:332`
- `risk/verify state=continue`：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:345`
- `CreateAccount redirectUrl`：
  - `/Users/chaopenglv/data/me/Gpt-Agreement-Payment/output/outlook_browser/runtime_trace_ni109xdjp5zp_1780948211.jsonl:347`

仍不可见、不能猜的部分：

- collector 服务端为什么在成功样本返回 `oIIoIooo|0`，在失败样本不返回；本地只能看到请求 payload 和响应包，无法看到服务端判定模型。
- Microsoft `/API/Proofs/risk/verify` 服务端为什么给 `state=continue`；本地只能证明它发生在 `postMessage succeeded` 之后。
- `_px3/_pxde/_pxvid` token 的服务端签名算法；本地只能证明 token 被 main/captcha 接收、派发、写入或提交，不能反推出 HUMAN 私钥或服务端签名逻辑。

这些不是“未分析”，而是本地浏览器/JS/网络样本无法包含的服务端黑盒边界；继续追需要服务端源码或服务端调试权限，否则不能写成结论。
