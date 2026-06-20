# 03. 目标架构

## 1. 分层架构

```text
apps/
  web-api
  worker
  scheduler
  cli

core/
  domain
  workflow
  jobs
  plugins
  observability
  config

plugins/
  proxy-webshare
  mail-external-api
  payment-stripe-paypal
  payment-gopay
  downstream-cpa
  downstream-team

infra/
  db
  migrations
  queues
  runtime
```

## 2. 模块职责

### 2.1 domain

只放领域实体和状态转换：

- User Account。
- TeamWorkspace。
- Membership。
- UserAccountAuth。
- ProviderProfile。
- Job。
- JobRun。
- JobStep。
- JobEvent。

domain 层不允许：

- 发 HTTP。
- 读写环境变量。
- 直接操作 subprocess。
- import 具体插件。

### 2.2 plugins

插件负责外部系统对接。

每个插件应包含：

```text
plugin.py
config.py
schemas.py
errors.py
tests/
```

插件必须声明：

```python
name = "proxy.webshare"
version = "1.0.0"
capabilities = ["proxy.rotate", "proxy.healthcheck"]
```

### 2.3 workflow

Workflow 负责把能力组装成业务流程。

Workflow 只依赖：

- capability registry。
- job context。
- domain repository。

不直接依赖具体 provider。

### 2.4 jobs

Job 层负责：

- 创建任务。
- 排队。
- 执行。
- 重试。
- 取消。
- 续跑。
- step 状态持久化。
- event 持久化。

### 2.5 observability

负责：

- 结构化日志。
- error code。
- metrics。
- trace id。
- audit event。

## 3. 推荐数据模型

本节只解释表职责和字段边界；完整 DDL、外键、CHECK、索引以 `docs/schema/001_initial_schema.sql` 为准。

### 3.1 user_accounts

表结构真源：

```text
docs/schema/001_initial_schema.sql -> user_accounts
```

核心字段：

```text
id
email
phone_number
phone_dial_code
phone_country
openai_user_id
account_status
created_at
updated_at
```

`account_status` 只表示账号本身是否可作为库存使用，不表达 token 是否可用，也不表达 Team Workspace 权限。

允许值：

```text
active
invalid
```

账号可同时有邮箱和手机号。不要为 V1 单独建 `user_account_identifiers` 抽象表。

### 3.2 team_workspaces

表结构真源：

```text
docs/schema/001_initial_schema.sql -> team_workspaces
```

核心字段：

```text
id
provider
external_workspace_id
name
plan_type
seat_limit
workspace_status
last_probe_at
created_at
updated_at
```

V1 `provider` 固定为：

```text
openai_chatgpt
```

它不是用户维护字段，不需要单独页面配置。后续如果支持其它 Team Workspace 来源，再抽 provider 表或 provider profile。

`workspace_status` 只表示 Team Workspace 本身状态。可选值：`unknown`、`active`、`disabled`、`expired`、`error`。

### 3.3 user_account_team_workspace_memberships

表结构真源：

```text
docs/schema/001_initial_schema.sql -> user_account_team_workspace_memberships
```

核心字段：

```text
id
user_account_id
team_workspace_id
role
membership_status
invite_permission
user_count
invite_count
seat_status
can_invite
chatgpt_web_backend_access_token
chatgpt_web_backend_id_token
chatgpt_web_backend_access_token_expires_at
chatgpt_web_backend_access_token_status
last_chatgpt_web_backend_token_refresh_at
last_probe_status
last_probe_at
failure_code
failure_message
created_at
updated_at
```

判断规则：

```text
seat_status = full      when user_count + invite_count >= team_workspaces.seat_limit
seat_status = available when user_count + invite_count <  team_workspaces.seat_limit

can_invite = true only when:
  team_workspaces.workspace_status = active
  user_account_team_workspace_memberships.membership_status = active
  user_account_team_workspace_memberships.invite_permission = ok
  user_account_team_workspace_memberships.seat_status = available
```

`can_invite` 是派生结果。写入数据库是为了查询和排序方便，但更新它的唯一入口应是 membership probe job。

`user_account_team_workspace_memberships` 是当前状态表，不是批次流水表。  
同一个 User Account + Team Workspace 只有一行，用于保存当前 membership 状态和当前可用 ChatGPT Web backend API token。

写入场景：

```text
1. Team Workspace 创建成功：
   创建 owner membership，role=owner，membership_status=active。

2. 导入已有 Team Workspace owner：
   token/probe 能证明 owner 属于该 workspace 后，upsert owner/admin membership。

3. owner 邀请 member 成功：
   member 已有 user_account_id 时，upsert member membership，membership_status=invited。
   如果只有邮箱、没有 User Account，不写 membership，只写 batch item 邀请结果。

4. member 接受邀请成功：
   update membership_status=accepted。

5. member 目标 ChatGPT Web backend API token 构建并校验成功：
   update membership_status=active，并写 chatgpt_web_backend_access_token/chatgpt_web_backend_id_token/token status。

6. membership probe 成功：
   update invite_permission/user_count/invite_count/seat_status/can_invite/last_probe_at。

7. probe 发现离开、禁用、封禁、失败：
   update membership_status=left/disabled/banned/failed，并写 failure_code/failure_message。

8. token refresh 失败：
   update chatgpt_web_backend_access_token_status=expired/invalid/dead/error，并写 failure_code/failure_message。
```

不写入场景：

```text
1. 创建 batch 时不预写 membership。
2. 准备推 CPA/Sub2API 时不创建 membership。
3. 只有 email、没有 User Account 时不创建 membership。
4. 没有 team_workspace_id 时不创建 membership。
```

授权落点：

```text
user_account_auth:
  存账号登录授权。
  一个 User Account 一行。
  包含 session_token / refresh_token。

user_account_team_workspace_memberships:
  存 ChatGPT Web backend API 调用凭证。
  一个 User Account 加入几个 Team Workspace，就有几行。
  每行维护该账号在该 Team Workspace 下的 chatgpt_web_backend_access_token、membership_status、invite_permission、seat_status、can_invite。
  这里不是浏览器 UI session；浏览器 UI session 是 user_account_auth.session_token。
```

示例：

```text
一个注册账号加入 3 个 Team Workspace：

user_account_auth:
  1 行

user_account_team_workspace_memberships:
  3 行，每行各自保存该 Team Workspace 上下文的 chatgpt_web_backend_access_token
```

### 3.4 workspace_join_batches

`workspace_join_batches` 表示一次批量加入 Team Workspace、生成 ChatGPT Web backend API token、推送下游的执行批次。

同一个 Team Workspace 可以有多个 batch。  
同一个 User Account + Team Workspace 也可以在不同 batch 中重复出现。  
重复出现时，`user_account_team_workspace_memberships` 仍然只有一行，batch item 记录每次执行流水。

表结构真源：

```text
docs/schema/001_initial_schema.sql -> workspace_join_batches
```

核心字段：

```text
id
team_workspace_id
batch_name
batch_status
activation_status
source_type
source_job_id
created_by
started_at
finished_at
activated_at
deactivated_at
total_count
success_count
failed_count
pushed_count
created_at
updated_at
```

`batch_status` 可选值：

```text
created
running
partial_success
success
failed
cancelled
```

`activation_status` 可选值：

```text
inactive      未生效
activating    正在生效
active        当前生效
superseded    已被后续批次替代
retired       手动下线
```

生命周期：

```text
created -> running -> success/partial_success/failed/cancelled

inactive -> activating -> active
active -> superseded
active -> retired
```

生效规则：

```text
1. batch_status 表示批次执行结果。
2. activation_status 表示批次是否作为当前有效批次参与业务。
3. batch_status=success 或 partial_success 后，才允许 activation_status 从 inactive 变为 active。
4. 对同一个 Team Workspace，默认只允许一个 active batch。
5. 新 batch 激活时，旧 active batch 必须改为 superseded。
6. failed/cancelled batch 不能 active。
7. membership 保存当前状态；active batch 表示“这批结果被采纳为当前有效批次”。
```

### 3.5 workspace_join_batch_items

`workspace_join_batch_items` 表示某个 User Account 在某个批次中的执行结果。

表结构真源：

```text
docs/schema/001_initial_schema.sql -> workspace_join_batch_items
```

核心字段：

```text
id
batch_id
user_account_id
team_workspace_id
membership_id
item_status
join_status
token_status
push_status
plan_tag
plan_type
generated_chatgpt_web_backend_access_token
generated_chatgpt_web_backend_id_token
generated_chatgpt_web_backend_token_expires_at
downstream_provider
downstream_external_id
failure_code
failure_message
created_at
updated_at
```

`item_status` 可选值：

```text
pending
joined
token_generated
pushed
failed
skipped
```

维护规则：

```text
1. batch item 保存“这一次批次”的 token 生成和推送结果。
2. membership 保存“当前状态”和“当前可用 ChatGPT Web backend API token”。
3. 当 batch item 生成 token 成功后，可以把 generated_chatgpt_web_backend_access_token 同步到 membership.chatgpt_web_backend_access_token。
4. 下次同一个 workspace 新建 batch 时，必须新建 workspace_join_batches 记录，不能覆盖旧 batch。
5. 同一个 User Account + Team Workspace 再次出现在新 batch 时，新增 batch item；membership 仍复用同一行并更新当前状态。
6. plan_tag / plan_type 是本批次 item 的结果字段；不要写入 codex_oauth_credentials。
```

示例：

```text
第一次：
  batch_001 -> workspace_1
    item: user_a token_A1 pushed
    item: user_b token_B1 pushed

第二次：
  batch_002 -> workspace_1
    item: user_c token_C2 pushed
    item: user_d token_D2 pushed

如果 user_a 第二次也被处理：
  batch_002 新增 item: user_a token_A2 pushed
  membership(user_a, workspace_1) 仍是一行，当前 chatgpt_web_backend_access_token 更新为 token_A2
```

### 3.6 user_account_auth

`user_account_auth` 存账号授权字段。V1 是本地项目，token 直接放 DB，不做 secret store，不做 token vault。

表结构真源：

```text
docs/schema/001_initial_schema.sql -> user_account_auth
```

核心字段：

```text
user_account_id
session_token
refresh_token
token_type
scope
refresh_token_status
last_refresh_at
last_auth_error_code
last_auth_error_message
created_at
updated_at
```

`refresh_token_status` 可选值：

```text
missing
active
refreshing
expired
invalid
dead
error
```

规则：

```text
1. 一个 User Account 对应一行 user_account_auth。
2. refresh_token、session_token 直接存 DB 字段。
3. ChatGPT Web backend API access token 不放在 user_account_auth，放在 user_account_team_workspace_memberships。
4. 不引入 auth_tokens 泛化表。
5. 不引入 secret_ref、value_hash、token_purpose、audience。
6. 如果后续确实出现一账号多套 OAuth client，再升级模型；V1 不提前设计。
```

旧项目证据：

```text
pipeline.py::_sync_registered_account_oauth_tokens()
旧实现把 access_token、id_token、refresh_token 直接回写 registered_accounts。
WebUI 也是按 has_refresh_token / rt_state 判断 RT 状态。
V1 保持简单模型：User Account 级 refresh_token 放 user_account_auth；Team Workspace 级 ChatGPT Web backend API access_token 放 membership。
```

### 3.7 codex_oauth_credentials

`codex_oauth_credentials` 保存当前可复用的 Codex OAuth token。

它只保存“token 当前值”和“token 归属校验结果”。  
CPA/Sub2API 的包装字段在推送时由 worker 组装，不落在这张表里。

证据来自旧 Team 导出流程：

```text
pipeline.py::_cpa_import_after_team()

Team 后推送给 CPA/Sub2API 的 body 只有：
  id_token
  access_token
  refresh_token
  account_id
  email
  last_refresh
  expired
  type=codex

Sub2API 上传时额外包一层：
  content=json.dumps(body)
  name=codex-{md5(email)[:8]}-{email}-{plan_tag}.json
  update_existing

webui/backend/routes/inventory.py::_sub2api_account_from_body()

Sub2API 导出包里的 platform=openai、type=oauth、client_id、expires_at、plan_type
都是导出组装字段，不是 token 本身。

本仓库里的 Sub2API 导出样本 `scripts/input/sub2api-account-20260612120715.json`
证明 Sub2API account.credentials 里存在 `chatgpt_account_id` 字段。旧心跳实现
`webui/backend/routes/inventory.py::_post_openai_heartbeat()` 会把该值作为
`chatgpt-account-id` header 调 `https://chatgpt.com/backend-api/codex/responses`。
所以 Team 推送时必须显式把目标 workspace 写进 payload，不能只靠 access_token 自己。
```

表结构真源：

```text
docs/schema/001_initial_schema.sql -> codex_oauth_credentials
```

核心字段：

```text
id
user_account_id
team_workspace_id
codex_client_id
credential_status
account_id
token_chatgpt_account_id
access_token
id_token
refresh_token
expires_at
last_refresh_at
last_heartbeat_at
last_heartbeat_status
last_heartbeat_error_code
last_heartbeat_error_message
failure_code
failure_message
created_at
updated_at
```

字段含义：

```text
user_account_id:
  本系统 User Account 主键。

team_workspace_id:
  本系统 Team Workspace 主键。
  credential 必须绑定到明确目标 Team Workspace。

codex_client_id:
  OAuth client_id。
  旧流程默认 app_EMoamEEZ73f0CkXaXp7hrann。

credential_status:
  当前 token 状态。

account_id:
  Codex/OpenAI User Account 外部账号 ID。
  来自 access_token 解析或 token response 派生。
  不是本系统 user_accounts.id，也不是 Team Workspace ID。

token_chatgpt_account_id:
  从 access_token JWT 解析出来的实际 ChatGPT account/workspace 上下文。
  多 Team Workspace 推送前必须校验：
  token_chatgpt_account_id == team_workspaces.external_workspace_id。

access_token / id_token / refresh_token:
  下游 Codex 凭证包需要的 token 当前值。

expires_at:
  access_token 过期时间，对应旧 body.expired / Sub2API credentials.expires_at。

last_refresh_at:
  token 最近刷新时间，对应旧 body.last_refresh。

last_heartbeat_*:
  心跳检测最后一次结果。
```

推送时派生字段，不在本表保存：

```text
email:
  从 user_accounts.email 读取。

type=codex:
  固定常量。

platform=openai:
  Sub2API 包装常量。

sub2api type=oauth:
  Sub2API 包装常量。

name / export_name:
  推送时按旧规则生成：
  codex-{md5(email)[:8]}-{email}-{plan_tag}.json

token_source:
  CPA JSON 需要时生成：
  ChatGPT_{plan_tag}

chatgpt_account_id:
  下游平台识别 Team Workspace 的字段。
  V1 多 Team Workspace 推送时必须写 team_workspaces.external_workspace_id。
  不允许写 user-level account_id。

chatgpt_user_id:
  旧 Sub2API 导出流程默认等于 account_id。

client_id:
  写 codex_client_id。

saved_at:
  CPA JSON 推送发生时间。
```

下游 payload 如果需要 `plan_tag` / `plan_type`：

```text
credentials.plan_tag  <- workspace_join_batch_items.plan_tag
credentials.plan_type <- workspace_join_batch_items.plan_type
```

这两个字段不从 `codex_oauth_credentials` 读取。

为什么不保存 `membership_id`：

```text
credential 的唯一业务作用域是：
  user_account_id + team_workspace_id + codex_client_id

membership 是账号与 workspace 的当前关系。
同一组 user_account_id + team_workspace_id 在 user_account_team_workspace_memberships 中唯一。
批次 item 已经记录当次 membership_id。
credential 表不再重复保存 membership_id。
```

写入场景：

```text
1. 构建 Codex credential 成功：
   upsert codex_oauth_credentials。

2. access_token/id_token 刷新成功：
   update access_token/id_token/refresh_token/expires_at/last_refresh_at。

3. refresh 失败：
   update credential_status=invalid/error，写 failure_code/failure_message。

4. 推 CPA/Sub2API：
   upsert downstream_codex_push_records。
   同一 batch_item_id + downstream_provider 只保留一条推送记录。
   推送摘要同步写 workspace_join_batch_items。
   详细请求/响应摘要写 job_events。
```

约束：

```text
1. token_chatgpt_account_id 必须等于 team_workspaces.external_workspace_id。
2. Codex token 不是每次推送都必须重新拉取；未过期且 workspace 匹配时可复用。
3. access_token/id_token/refresh_token 直接存 DB。
4. UNIQUE(user_account_id, team_workspace_id, codex_client_id) 定义同一账号、同一 Team Workspace、同一 Codex client 的当前 credential。
5. plan_tag / plan_type 不属于 credential 当前值，批次结果写 workspace_join_batch_items。
6. heartbeat 结果写 last_heartbeat_at / last_heartbeat_status / last_heartbeat_error_code / last_heartbeat_error_message。
7. 推 CPA/Sub2API 的 payload 必须显式带 workspaceId 语义字段：
   credentials.chatgpt_account_id = team_workspaces.external_workspace_id。
```

Sub2API 官方导入更新规则：

```text
证据：Wei-Shaw/sub2api
文件：backend/internal/handler/admin/account_codex_import.go

1. /api/v1/admin/accounts/import/codex-session 导入时先加载已有 openai/oauth 账号。
2. update_existing=true 时使用 identity keys 查已有账号。
3. identity keys 顺序：
   account:{chatgpt_account_id}
   user:{chatgpt_user_id}
   email:{email}        // 只有 account/user 都为空才使用
   access:{access_token_sha256}
4. name 不参与更新匹配。
```

因此：

```text
不能把 chatgpt_account_id 拼成 user_account_id + workspace_id 的唯一值。

原因：
  Sub2API 运行时会把 credentials.chatgpt_account_id 直接作为
  chatgpt-account-id header 发给 chatgpt.com/backend-api/codex/responses。
  拼接值不是合法 workspace id，会导致运行时请求进入错误 workspace 或失败。

同一个 Team Workspace 下有多个 User Account 时：
  如果这些账号都推到同一个 Sub2API 实例，并且 update_existing=true，
  官方 Sub2API 会优先按 account:{chatgpt_account_id} 命中，存在覆盖风险。

V1 规则：
  对 Sub2API 推送同 workspace 多账号时，默认 update_existing=false。

如果需要稳定幂等更新：
  必须扩展 Sub2API，让导入匹配使用独立字段，例如 import_identity_key。
  该字段不能复用 chatgpt_account_id。
```

### 3.8 Downstream push result

需要推送流水表，但同一批次 item 对同一个下游只保留一条记录。

唯一条件：

```text
UNIQUE(batch_item_id, downstream_provider)
```

表结构真源：

```text
docs/schema/001_initial_schema.sql -> downstream_codex_push_records
```

核心字段：

```text
id
batch_item_id
codex_credential_id
user_account_id
team_workspace_id
membership_id
downstream_provider
downstream_external_id
push_status
codex_client_id
codex_account_id
codex_email
downstream_chatgpt_account_id
token_chatgpt_account_id
codex_token_expires_at
request_endpoint
error_code
error_message
created_at
updated_at
```

`push_status` 可选值：

```text
pending
pushed
failed
skipped
```

规则：

```text
1. Codex token 包由 downstream push workflow 生成，不写入 membership。
2. membership 只保存 Team Workspace 当前状态和 Team Workspace API token。
3. CPA/Sub2API admin_key 属于 downstream provider config，不属于 User Account。
4. 下游推送最终结果写 downstream_codex_push_records，并同步摘要到 workspace_join_batch_items.push_status / downstream_provider / downstream_external_id。
5. 多 Team Workspace 场景推送时必须有 batch_item_id、membership_id、team_workspace_id。
6. token_chatgpt_account_id 必须等于 team_workspaces.external_workspace_id，否则 push_status=failed。
7. 同一个 User Account 在不同 Team Workspace 下推送 Codex 凭证时，由不同 batch item 区分。
8. 构建 Downstream Codex Credential 的输入必须包含 team_workspace_id；没有目标 Team Workspace 的构建结果不能写入 pushed。
9. 下游 payload 中的 chatgpt_account_id 必须等于 team_workspaces.external_workspace_id。
10. 同一批次 item 重试同一个 downstream_provider 时，upsert 同一条 downstream_codex_push_records，不追加多条。
```

状态写入场景：

```text
1. downstream.push_codex_credential job 开始
   upsert downstream_codex_push_records push_status=pending。
   workspace_join_batch_items.push_status=pending。

2. 构建 Codex token 失败
   downstream_codex_push_records.push_status=failed
   downstream_codex_push_records.error_code=oauth_refresh_failed / missing_refresh_token / workspace_mismatch
   workspace_join_batch_items.push_status=failed
   workspace_join_batch_items.failure_code=oauth_refresh_failed / missing_refresh_token / workspace_mismatch

3. 下游配置未启用或缺少 admin_key/base_url
   downstream_codex_push_records.push_status=skipped
   downstream_codex_push_records.error_code=downstream_disabled / downstream_config_missing
   workspace_join_batch_items.push_status=skipped
   workspace_join_batch_items.failure_code=downstream_disabled / downstream_config_missing

4. 调 CPA/Sub2API 成功
   downstream_codex_push_records.push_status=pushed
   downstream_codex_push_records.request_endpoint=实际调用地址
   downstream_codex_push_records.downstream_external_id=下游返回 id；如果下游不返回 id，则写导入文件名或空字符串
   workspace_join_batch_items.push_status=pushed
   workspace_join_batch_items.downstream_provider=cpa/sub2api
   workspace_join_batch_items.downstream_external_id=下游返回 id；如果下游不返回 id，则写导入文件名或空字符串

5. 调 CPA/Sub2API 失败
   downstream_codex_push_records.push_status=failed
   downstream_codex_push_records.request_endpoint=实际调用地址
   downstream_codex_push_records.error_code=downstream_push_failed
   downstream_codex_push_records.error_message=HTTP 状态或下游错误摘要
   workspace_join_batch_items.push_status=failed
   workspace_join_batch_items.failure_code=downstream_push_failed
   workspace_join_batch_items.failure_message=HTTP 状态或下游错误摘要

以上每一步都可以额外写 job_events。
```

### 3.9 user_account_proxy_bindings

代理绑定在 User Account 上，不绑定在 Workflow、Job、Step 或一次请求上。

表结构真源：

```text
docs/schema/001_initial_schema.sql -> user_account_proxy_bindings
```

核心字段：

```text
id
user_account_id
proxy_id
bind_status
bind_reason
bound_by_job_id
bound_at
last_used_at
last_error_code
created_at
updated_at
```

`bind_status` 可选值：

```text
active
repairing
disabled
released
error
```

使用规则：

```text
1. 创建账号前，RegisterAccountWorkflow 先从 proxy_inventory 分配一个 Webshare proxy。
2. 账号创建成功后，把 user_account_id + proxy_id 写入 user_account_proxy_bindings。
3. 后续该账号的注册补偿、登录、支付、token refresh、membership probe 默认都从 user_account_proxy_bindings 取 proxy。
4. Job input 里不允许直接塞临时 proxy 覆盖账号绑定；只允许传 user_account_id。
5. 只有 ops.proxy.repair_account_binding 可以换绑。
6. 换绑必须保留旧绑定历史，不直接覆盖审计记录。
```

### 3.10 proxy_inventory

V1 代理只支持 Webshare。Webshare 能力必须按官方 API 文档重新实现，不参考旧项目实现。

拉取入口：

```text
GET https://proxy.webshare.io/api/v2/proxy/list/
Authorization: Token <TOKEN>
```

官方列表接口返回分页 JSON：`count`、`next`、`previous`、`results`。系统必须按 `next` 或 `page/page_size` 拉完整 IP 池，再把 proxy 绑定到账号。

表结构真源：

```text
docs/schema/001_initial_schema.sql -> proxy_inventory
```

核心字段：

```text
id
provider
external_proxy_id
connection_mode
proxy_host
proxy_port
proxy_scheme
proxy_username
proxy_password
country_code
city_name
asn_name
proxy_status
provider_valid
last_provider_verification_at
last_healthcheck_at
created_at
updated_at
```

字段来源：

```text
external_proxy_id              <- Webshare proxy.id
proxy_username                 <- Webshare proxy.username
proxy_password                 <- Webshare proxy.password
proxy_host                     <- Webshare proxy.proxy_address，Direct 模式
proxy_port                     <- Webshare proxy.port
provider_valid                 <- Webshare proxy.valid
last_provider_verification_at  <- Webshare proxy.last_verification
country_code                   <- Webshare proxy.country_code
city_name                      <- Webshare proxy.city_name
```

`proxy_status` 枚举：

```text
unknown
available
bound
invalid
cooldown
retired
error
```

`provider_valid=false` 时，`proxy_status` 必须进入 `invalid` 或 `error`，不能分配给新账号。

### 3.11 external_mail_leases

V1 邮箱只走外部邮箱接口。本服务不维护邮箱账号，只记录外部租约和使用结果。

表结构真源：

```text
docs/schema/001_initial_schema.sql -> external_mail_leases
```

核心字段：

```text
id
user_account_id
provider
external_lease_id
email
lease_status
allocated_at
used_at
released_at
failure_code
failure_message
created_at
updated_at
```

### 3.12 jobs

表结构真源：

```text
docs/schema/001_initial_schema.sql -> jobs
```

核心字段：

```text
id
type
job_status
priority
input_json
created_by
created_at
updated_at
```

### 3.13 job_runs

表结构真源：

```text
docs/schema/001_initial_schema.sql -> job_runs
```

核心字段：

```text
id
job_id
run_status
attempt
started_at
finished_at
error_code
error_message
output_json
```

### 3.14 job_steps

表结构真源：

```text
docs/schema/001_initial_schema.sql -> job_steps
```

核心字段：

```text
id
run_id
name
step_status
attempt
started_at
finished_at
input_json
output_json
error_code
error_message
```

### 3.15 job_events

表结构真源：

```text
docs/schema/001_initial_schema.sql -> job_events
```

核心字段：

```text
id
run_id
step_id
ts
level
event_type
message
data_json
```

## 4. 运行时边界

### 4.1 Downstream Codex Credential 构建与推送流程

这个流程必须由 Worker 执行，不在 API 请求里同步执行。

```text
API:
  创建 downstream.push_codex_credential job
  input 必须包含 batch_item_id / user_account_id / team_workspace_id / membership_id / downstream_provider

Worker:
  1. 加载 user_account_auth.refresh_token
  2. 加载 team_workspaces.external_workspace_id
  3. 加载 membership 并校验 user_account_id + team_workspace_id
  4. 查询 codex_oauth_credentials
     如果 credential_status=active、expires_at 未过期、token_chatgpt_account_id 匹配 external_workspace_id：
       复用现有 credential
     否则：
       使用 refresh_token + codex_client_id + external_workspace_id 构建目标 workspace 的 access_token/id_token
       upsert codex_oauth_credentials
  5. 解 access_token，读取 token_chatgpt_account_id
  6. 校验 token_chatgpt_account_id == external_workspace_id
  7. 校验通过后用 codex_oauth_credentials 构造 type=codex 凭证包：
     access_token/id_token/refresh_token/account_id/email/last_refresh/expired/type
     chatgpt_account_id = team_workspaces.external_workspace_id
     chatgpt_user_id = codex_oauth_credentials.account_id
  8. 使用 downstream admin_key 推送 CPA/Sub2API
  9. 写 workspace_join_batch_items.push_status
  10. 写 downstream_codex_push_records，并快照 codex_client_id/codex_account_id/codex_email/downstream_chatgpt_account_id/token_chatgpt_account_id/codex_token_expires_at
  11. 写 job_events
```

失败分支：

```text
missing_refresh_token:
  refresh_token 不存在。

missing_workspace:
  team_workspace_id 或 external_workspace_id 不存在。

membership_mismatch:
  membership 不属于输入里的 user_account_id + team_workspace_id。

oauth_refresh_failed:
  refresh_token 换目标 ChatGPT Web backend API token 失败。

workspace_mismatch:
  token_chatgpt_account_id != team_workspaces.external_workspace_id。

downstream_push_failed:
  CPA/Sub2API 管理接口返回失败。
```

约束：

```text
1. 没有 team_workspace_id 的请求不能创建 workspace 级 Codex 推送 job。
2. 构建时必须显式带入目标 external_workspace_id，不能只依赖账号默认 workspace。
3. workspace_mismatch 表示构建结果不符合输入目标，必须失败并保留事件，不能继续推送。
4. 成功推送后，只更新本 batch item 和本 downstream_codex_push_records，不覆盖其它 workspace 的记录。
```

### 4.2 API 进程

职责：

- 接收用户请求。
- 创建 Job。
- 查询状态。
- 展示日志和结果。

不直接跑长任务。

### 4.3 Worker 进程

职责：

- 拉取 Job。
- 执行 Workflow。
- 写入 step/event。
- 处理重试。

### 4.4 Scheduler 进程

职责：

- 周期创建 Job。
- 维护自动运维策略。
- 不直接执行具体业务。

### 4.5 CLI

职责：

- 本地调试。
- 手动触发 Job。
- 导入/导出数据。
- 诊断环境。

## 5. 与旧项目的关系

`refactor-app/` 是独立新项目。旧项目只能作为人工阅读的背景证据，不能作为运行时依赖。

```text
禁止 import 旧项目模块。
禁止 subprocess 调旧项目脚本完成业务逻辑。
禁止 sys.path 指向旧项目目录。
禁止把旧 WebUI 当组件库复用。
禁止把旧 pipeline 包装成 plugin / adapter。
```

所有当前设计功能必须在 `refactor-app/` 内重新实现，并通过本目录内的 contract test、workflow test、integration test 验证。
