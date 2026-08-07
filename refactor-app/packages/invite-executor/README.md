# Pinned Batch Executor

独立、无数据库的请求执行器，当前承载空间邀请、分阶段登录 OTP 提交和服务端自动补号。

## 空间邀请

邀请执行器负责：

1. 接收一个空间的管理员请求上下文和目标邮箱。
2. 一次性构造全部邮箱的上游请求参数。
3. 用固定 Webshare Backbone 凭据生成最多 1000 个代理主端点，并为每个槽位准备两个不主动使用的备用端点。
4. 每批只解析一次 `p.webshare.io`，将代理端点轮询绑定到已解析的网关 IP。
5. 每条邀请固定一个 `curl_cffi.AsyncSession(max_clients=1)`，预建 CONNECT + TLS 后保持该 Session、curl handle 和连接不关闭。
6. 全部异步任务到达同一个内存屏障后，统一释放并直接提交 POST。
7. 在内存中保留逐邮箱结果，供调用方查询。

上游请求构造和响应判断直接复用 `refactor_app.plugins.openai_chatgpt.client` 的公共方法，不维护第二套 URL、请求头、请求体或成功判断。邀请请求使用分配到的 Backbone 代理：

```text
POST /backend-api/accounts/{external_space_id}/invites
proxy username = base_username-US-endpoint
active proxy endpoints = min(email count, 1000)
gateway DNS = once per batch
transport = one pinned AsyncSession/curl handle per invitation
```

`US` 和每批代理数量可通过环境变量调整。邮箱按连续分组均匀分配给本批代理槽位。CONNECT 失败时按“主端点、备用端点、不同网关 IP”轮换，成功路线会固定到该邀请的 Session 并用于最终 POST。凭据、DNS、请求构造或全部备用路线预热失败时，整批都在 POST 前失败，不会回退直连。

## 两阶段执行

准备阶段：

```text
分配 min(邮箱数, 100) 个主代理端点，并为每个槽位准备两个备用端点
-> 统一解析 p.webshare.io
-> 构造全部邀请请求
-> 按代理槽位轮转顺序预热 CONNECT + TLS（每条间隔 20ms，单次超时 5 秒，失败时轮换备用端点和已解析网关，默认一轮，最多十次）
-> 已建连接每 5 秒 HEAD 保活，直到最后一条连接建立
-> 并发验证全部固定 Session 可直接复用连接
-> 保持 AsyncSession 和连接池打开
-> 全部任务到达同一内存屏障
```

发送阶段：

```text
释放屏障
-> 全部任务直接调用异步 POST
-> 等待每条请求结束
-> 关闭 AsyncSession
```

例如 779 个邮箱固定得到 100 个活跃代理槽位，每个槽位连续承载 7 或 8 条；每个槽位另带两个备用端点，但主端点正常时不会使用。预热顺序先遍历 100 个槽位的第 1 条，再遍历各槽位的第 2 条，以此类推；相邻 CONNECT 默认间隔 20ms，因此基础启动跨度约 15.58 秒。每条邀请从预热开始到 POST 结束始终使用自己的 AsyncSession 和 curl handle；某条 CONNECT 失败时，按该槽位的备用端点和本批统一解析出的 Webshare 网关 IP 轮换，第一条成功路线会保留到最终 POST。先建立的连接每 5 秒执行一次 HEAD 保活，直到最后一条连接建立；随后立即并发执行 HEAD 复用验证，`NUM_CONNECTS=0` 表示该固定 Session 直接复用了已有连接。验证中被迫新建的连接也会在屏障释放前保留。全部 779 条验证成功后才释放 POST；整个过程不创建 779 个操作系统线程。

## 部署

目标部署方式是虚拟机上的单 Docker 容器。先在虚拟机创建持久目录；镜像内服务用户的
UID/GID 固定为 `10001`：

```bash
sudo install -d -m 700 -o 10001 -g 10001 /opt/invite-executor/data
```

然后在 `refactor-app` 目录执行：

```bash
cp packages/invite-executor/.env.example packages/invite-executor/.env
docker compose \
  --env-file packages/invite-executor/.env \
  -f packages/invite-executor/docker-compose.yml \
  up -d --build
```

Compose 将宿主机 `${INVITE_EXECUTOR_DATA_DIR}` 绑定到容器 `/data`。默认值是
`/opt/invite-executor/data`，注册表实际保存在宿主机：

```text
/opt/invite-executor/data/replenishment-registry.json
```

因此容器删除、重建或升级不会删除管理员和 Space 配置。不要执行针对该宿主目录的清理。

检查服务：

```bash
curl http://127.0.0.1:8080/health
```

必须保持单容器、单 Uvicorn Worker。内存屏障不能跨进程或跨副本。

必须配置：

```text
INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_HOST=p.webshare.io
INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_PORT=80
INVITE_EXECUTOR_STATIC_PROXY_USERNAME=replace-with-webshare-username
INVITE_EXECUTOR_STATIC_PROXY_PASSWORD=replace-with-webshare-password
INVITE_EXECUTOR_STATIC_PROXY_COUNTRY=US
INVITE_EXECUTOR_INVITE_PROXY_COUNT=1000
INVITE_EXECUTOR_INVITES_PER_PROXY=1
INVITE_EXECUTOR_INVITE_RELEASE_INTERVAL_MS=1
INVITE_EXECUTOR_PREWARM_ROUNDS=1
INVITE_EXECUTOR_PREWARM_ATTEMPTS=10
INVITE_EXECUTOR_PREWARM_START_INTERVAL_MS=20
INVITE_EXECUTOR_PREWARM_KEEPALIVE_INTERVAL_S=5
INVITE_EXECUTOR_PREWARM_TIMEOUT_S=5
INVITE_EXECUTOR_SESSION_OTP_BARRIER_TIMEOUT_S=120
INVITE_EXECUTOR_SESSION_OTP_RELEASE_WINDOW_S=2
```

## 创建邀请批次

```bash
curl -X POST http://127.0.0.1:8080/v1/invite-batches \
  -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{
  "external_space_id": "workspace-id",
  "access_token": "admin-access-token",
  "cookie_header": "__Secure-next-auth.session-token=...; oai-did=...",
  "emails": [
    "first@example.com",
    "second@example.com"
  ],
  "barrier_timeout_s": 30
}
JSON
```

接口立即返回 `202` 和 `batch_id`。

## 查询结果

```bash
curl \
  -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  http://127.0.0.1:8080/v1/invite-batches/BATCH_ID
```

批次状态：

- `queued`：协调线程尚未开始。
- `running`：正在准备连接、等待屏障或发送请求。
- `succeeded`：全部邮箱成功。
- `partial`：部分成功、部分失败。
- `failed`：全部失败，包括屏障超时。

每批记录连接全部就绪时间、预热连接目标数、预热轮数、HTTP 版本、最终预热轮的唯一客户端端口数、复用验证数、验证期间补建连接数和屏障释放时间。每条结果记录邮箱、代理槽位、代理端点匿名 ID、任务准备时间、请求发出时间、完成时间、HTTP 状态、上游响应或错误。管理员 `access_token`、Cookie 和代理密码不会写入批次结果；只有请求明确携带 `replenishment` 时，管理员 Cookie 和该 Space 的 workspace token 才写入补号注册表。

## 分阶段 OTP 提交

该接口只执行已有 OTP 快照的提交阶段，不负责发码、查询邮箱、跟随 callback 或获取
ChatGPT Session。每个条目由调用方直接传入 Prepare 阶段使用的原始代理：

```text
读取 snapshot 中的 OTP、Cookie、device_id 和协议指纹
-> 用 proxy_url 创建该条目独占的 AsyncSession
-> 恢复 Cookie
-> 对 auth.openai.com 预建代理 CONNECT + TLS
-> 保活并验证固定 Session 可以复用连接
-> 全部可提交条目到达同一个内存屏障
-> 屏障就绪后在 2 秒窗口内等间隔释放 POST /api/accounts/email-otp/validate
-> 返回逐条状态和 snapshot_patch
```

创建批次：

```bash
curl -X POST http://127.0.0.1:8080/v1/session-otp-submit-batches \
  -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  -H "Content-Type: application/json" \
  --data-binary @- <<'JSON'
{
  "items": [
    {
      "item_id": "work-item-id",
      "email": "user@example.com",
      "proxy_url": "http://proxy-user:proxy-password@proxy-host:proxy-port",
      "snapshot": {
        "schema": "auth_flow_protocol_snapshot.v1",
        "email": "user@example.com",
        "device_id": "device-id",
        "cookies": [
          {
            "name": "login_session",
            "value": "cookie-value",
            "domain": "auth.openai.com",
            "path": "/"
          }
        ],
        "otp_code": "123456"
      }
    }
  ],
  "barrier_timeout_s": 120
}
JSON
```

查询结果：

```bash
curl \
  -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  http://127.0.0.1:8080/v1/session-otp-submit-batches/BATCH_ID
```

单条快照缺少 OTP、邮箱不匹配或无法恢复时，该条记录为 `skipped`，其他可提交条目
继续。任一可提交条目的连接在配置次数内仍无法预热时，所有可提交条目都停在
`prewarm`，不会发出 OTP validate。屏障释放后的 HTTP 失败只影响对应条目。
默认发送窗口为 2 秒：第 `i` 条请求的绝对释放偏移为 `2 * i / N` 秒，因此首条
立即发送，末条在 2 秒边界前发送；使用绝对单调时钟，不累计逐条 sleep 漂移。该窗口可
通过 `INVITE_EXECUTOR_SESSION_OTP_RELEASE_WINDOW_S` 调整，设为 `0` 可恢复同时提交。

成功条目返回 `snapshot_patch`，包含 validate 后 Cookie、`continue_url`、`page_type`、
`otp_validated_at` 和上游响应。调用方后续接入时将补丁合并进本地原快照。服务端不
返回原代理、OTP、密码或完整输入快照。

邀请批次和 OTP 提交批次共享一个执行闸门：同一时间整个服务只运行一个批次，其他
创建请求返回 `409`，并给出当前批次 ID 和类型。

## 服务端自动补号（第二步）

本能力只实现自动补号的第二步。第一步仍由本地 Portal 手动筛选邮箱并调用现有
`POST /v1/invite-batches`；自动补号不会创建邀请、不会调用本地数据库，也不会维护
membership 表。

每 120 秒对每个已配置 Space 独立执行一次，每个 Space 同一时间最多一个周期，不同
Space 使用不同的运行状态和锁，可以并行执行。每个周期最多补一个账号：

```text
读取目标 Space 的 /users 和 /invites
-> 从 Sub2API Admin API 读取目标 group 的 OpenAI OAuth 账号
-> 只保留 credentials.chatgpt_account_id == 当前 external_space_id
-> 优先处理“Sub2API 有账号但远端 /users 已无此 user_id”
-> 其次处理额度达到 90% 的账号
-> 无替换目标时，只有远端非管理员成员数低于 seat_limit 才补号
-> 从当前 Space 的 /invites 取一个未处理邮箱
-> 固定邮箱纯协议登录；不存在时由同一协议链路注册
-> 使用该邮箱的稳定 Backbone 代理切换到目标 Space
-> 创建 90 天 Business AT（同 Space 两次创建开始时间至少间隔 10 秒）
-> 再查 /users，确认新 user_id 已在当前 Space
-> 调 Sub2API Admin API 创建账号
-> 若为替换：剔除旧远端成员，再查 /users 确认消失，最后删除旧 Sub2API 账号
```

额度字段直接读取 Sub2API 已维护的快照：

- `team_5h_weekly`：`codex_7d_used_percent`
- `team_monthly`：`codex_primary_used_percent`
- `codex_usage_updated_at` 超过 2 小时则本轮不按该快照替换

远端非管理员成员的普通补号上限为 `seat_limit`；替换期间临时重叠上限为
`floor(seat_limit * 1.5)`。新账号成功写入 Sub2API 后，`extra` 会记录旧 user ID；如果
进程在“推新”和“删旧”之间重启，下个周期会先恢复这笔未完成替换。

自动补号与邀请/OTP 批次的全局执行闸门无关。邀请或 OTP 批次运行时，自动补号仍按
各自 Space 的独立锁运行。

### 配置

默认关闭。启用前必须配置：

```text
INVITE_EXECUTOR_AUTO_REPLENISH_ENABLED=true
INVITE_EXECUTOR_AUTO_REPLENISH_INTERVAL_S=120
INVITE_EXECUTOR_AUTO_REPLENISH_REGISTRY_PATH=/data/replenishment-registry.json
INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_BASE_URL=https://sub2api.example.com
INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_API_KEY=...
INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_ID=6
INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_IDS=6,10
INVITE_EXECUTOR_AUTO_REPLENISH_MAIL_BASE_URL=https://mail-api.example.com
INVITE_EXECUTOR_AUTO_REPLENISH_MAIL_API_KEY=...
```

Space 不再通过启动环境变量静态配置。本地 Portal 手动提交服务器邀请时，会在原请求中
携带 `replenishment`，服务端先原子更新持久化注册表，再启动邀请批次：

```json
{
  "external_space_id": "workspace-id",
  "access_token": "admin-workspace-access-token",
  "cookie_header": "session=admin-cookie",
  "emails": ["first@example.com"],
  "replenishment": {
    "admin_key": "admin@example.com",
    "admin_email": "admin@example.com",
    "name": "workspace-name",
    "credential_type": "team_monthly",
    "seat_limit": 999,
    "enabled": true
  }
}
```

注册表内部将管理员和 Space 分开保存：多个 Space 可以引用同一个 `admin_key`。管理员级
只保存一份 Cookie 和固定代理；每个 Space 单独保存自己的 workspace access token，不能
被同一管理员的其他 Space 覆盖。新增 Space、管理员 Cookie 更新或席位配置更新均不需要
重启。Compose 将虚拟机宿主目录绑定到 `/data`，容器重建后仍会读取该注册表。有 Cookie
时，每轮优先交换当前 Space 的 workspace access token；交换失败时才使用该 Space 自己保存的 token。
JWT access token 的 `chatgpt_account_id` 与目标 Space 不一致会直接失败。

### 状态与手动触发

查询所有 Space 的独立运行状态：

```bash
curl -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  http://127.0.0.1:8080/v1/replenishment/spaces
```

手动触发指定 Space 一轮：

```bash
curl -X POST \
  -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  http://127.0.0.1:8080/v1/replenishment/spaces/SPACE_ID/run
```

也可以不发邀请，单独新增或更新一个 Space 的持久化配置：

```bash
curl -X PUT \
  -H "Authorization: Bearer ${INVITE_EXECUTOR_API_KEY}" \
  -H "Content-Type: application/json" \
  http://127.0.0.1:8080/v1/replenishment/spaces/SPACE_ID \
  --data '{
    "admin_key":"admin@example.com",
    "admin_email":"admin@example.com",
    "credential_type":"team_monthly",
    "seat_limit":999,
    "admin_access_token":"workspace-access-token",
    "admin_cookie_header":"session=admin-cookie"
  }'
```

删除配置使用 `DELETE /v1/replenishment/spaces/{external_space_id}`。运行中的 Space 不允许
删除。状态和管理接口都不会返回 Cookie、Token 或代理密码。

## 运行约束

- 单批最多 1000 个邮箱，邮箱不允许重复。
- 一个邮箱对应一个上游请求。
- 邮箱按输入顺序连续、均匀地分配给最多 100 个代理槽位。
- 1000 个邮箱需要 100 个活跃 Backbone 槽位，每个槽位承载 10 条；备用端点只在 CONNECT 失败时接管对应邀请，所有邮箱仍进入同一个内存屏障和同一个 asyncio 事件循环。
- 任一请求失败只记录该邮箱失败，不打破已释放的批次。
- 任一连接在配置次数内无法预热，整批不释放屏障、不发送 POST。
- 结果默认在内存中保留 3600 秒；容器重启后清空。
- 生产环境必须使用 HTTPS，并配置足够强的 `INVITE_EXECUTOR_API_KEY`。
- 传输层不按邮箱创建操作系统线程；文件描述符上限仍需覆盖预热连接数，Compose 配置为 `8192`。
- OTP 请求中的原代理、OTP、密码和完整输入快照不写数据库、文件或日志，也不在结果中
  回显。validate 后 CookieJar 位于成功结果的 `snapshot_patch` 中，按结果 TTL 保存在内存，
  供调用方合并回本地快照；容器重启后全部清空。
