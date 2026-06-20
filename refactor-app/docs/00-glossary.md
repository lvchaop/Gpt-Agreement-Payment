# 00. 术语表

本文档集所有核心名词以本文件为准。后续设计和代码命名不得重新发明同义词。

## User Account

系统管理的 ChatGPT/OpenAI 账号主体。

User Account 只表示系统管理的登录账号本身，不表示它在哪个 Team Workspace 里有什么权限。

典型字段：

```text
user_account_id
email
phone_number
phone_dial_code
phone_country
openai_user_id
account_status
```

邮箱和手机号可以同时存在，V1 不拆 `user_account_identifiers` 表。

## Team Workspace

准确含义：

```text
Team Workspace = ChatGPT Team 工作区
               = OpenAI/ChatGPT 后端 account/workspace 维度的团队容器
               = 可邀请成员、维护席位、维护 invite permission 的对象
```

旧项目证据：

- `CTF-reg/config.py` 中有 `workspace_name`。
- `pipeline.py::_oai_team_id_from_access_token()` 注释说明 `chatgpt_account_id` 等同 `workspace id`。
- `pipeline.py::_oai_send_team_invite()` 调用 `/backend-api/accounts/{team_id}/invites`。

Team Workspace 不代表：

- 普通个人 Plus 账号。
- Codex 工作区。
- 邮箱域名池。
- 代理池。
- 下游 CPA 分组。
- 抽象意义上的“空间”。

## ChatGPT Web Backend Team Workspace Credential

某个 User Account 调用 ChatGPT Web backend 的 Team Workspace 接口时使用的 Bearer 凭证和上下文。

它不是“授权给 Codex”，不是“授权给本系统”，也不是浏览器 UI session。  
它实际表达的是：

```text
这个 access_token / id_token 属于哪个 ChatGPT User Account
这个 access_token 当前指向哪个 ChatGPT Team Workspace
调用 ChatGPT Web backend Team Workspace 接口时应该带哪个 team_workspace_id
```

旧项目里的直接证据：

```text
pipeline.py::_oai_team_id_from_access_token()
  从 access_token JWT 里读取 chatgpt_account_id。

pipeline.py::_oai_send_team_invite()
  用 Bearer access_token 调 /backend-api/accounts/{team_id}/invites。
  header 里带 chatgpt-account-id: {team_id}。
```

因此本文档里后续不再使用“空间上下文授权”这个词，统一叫：

```text
ChatGPT Web backend Team Workspace Credential
ChatGPT Web backend Team Workspace API 调用凭证
```

## Downstream Codex Credential

推送到 CPA/Sub2API 的 Codex 凭证包。

它不是 Team Workspace invite 凭证。  
它表达的是：

```text
把某个 ChatGPT/OpenAI User Account 的 Codex OAuth token 包
导入 CPA/Sub2API
让下游系统按 Codex 账号使用这个 User Account
```

旧项目里的直接证据：

```text
pipeline.py::_codex_oauth_client_id_from_card_cfg()
  从 cpa.oauth_client_id / codex_oauth_client_id 读取 Codex OAuth client_id。

pipeline.py::_cpa_import_after_team()
  使用 refresh_token + client_id 请求 https://auth.openai.com/oauth/token。
  构造 type=codex 的 JSON 凭证包。
  推送到 CPA: /v0/management/auth-files
  推送到 Sub2API: /api/v1/admin/accounts/import/codex-session
```

Codex 凭证包核心字段：

```text
id_token
access_token
refresh_token
account_id
email
last_refresh
expired
type = codex
chatgpt_account_id
```

Team 推送时 `chatgpt_account_id` 是下游平台识别 workspace 的字段，必须写目标
`team_workspaces.external_workspace_id`，不能写 user-level `account_id`。

旧 WebUI 导出时还会带 `plan_tag`。重构后 `plan_tag` 不属于 Codex credential 当前值，落到批次 item：

```text
workspace_join_batch_items.plan_tag
```

多 Team Workspace 单独授权时，目标设计必须额外记录：

```text
user_account_id
team_workspace_id
external_workspace_id
codex_client_id
token_chatgpt_account_id
```

其中：

```text
token_chatgpt_account_id 必须等于 team_workspaces.external_workspace_id
```

如果生成出来的 Codex access_token 无法证明属于目标 Team Workspace，则不能把它当成该 Team Workspace 的 Codex 凭证推送。

构建 Downstream Codex Credential 时必须先选择目标 Team Workspace：

```text
build_codex_credential(user_account_id, team_workspace_id)
```

不允许只有 `user_account_id` 就构建并标记为某个 Team Workspace 已授权。  
重构后的实现必须把 `team_workspace_id` / `external_workspace_id` 直接带入 Codex OAuth 构建流程。  
`token_chatgpt_account_id` 校验只作为结果验收：不匹配就失败，不能自动归到其它 workspace。

下游推送自身也有一层管理授权：

```text
CPA/Sub2API admin_key
Authorization: Bearer {admin_key}
```

因此本系统里至少有两类不同凭证：

```text
ChatGPT Web Backend Team Workspace Credential:
  用于调用 ChatGPT Web backend 的 Team Workspace invite/accept/probe 接口。
  不是浏览器 UI session。

Downstream Codex Credential:
  用于推送 CPA/Sub2API，让下游按 Codex 账号使用。
```

## Membership

User Account 和 Team Workspace 的关系。

一个 User Account 可以加入多个 Team Workspace，所以必须有独立 Membership。

例子：

```text
user_account A -> team_workspace X -> owner
user_account A -> team_workspace Y -> member
user_account A -> team_workspace Z -> invite_failed
```

Membership 负责维护：

- 该账号在该 Team Workspace 的角色。
- 是否有 invite permission。
- 当前席位是否满。
- 最近一次探测结果。
- 是否能继续邀请成员。

Membership 是当前状态，不是批次流水。

## Workspace Join Batch

一次批量加入 Team Workspace、生成 ChatGPT Web backend API token、推送下游的执行批次。

同一个 Team Workspace 可以有多个 Workspace Join Batch。

例子：

```text
batch_001:
  workspace_1
  user_a -> token_A1 -> pushed
  user_b -> token_B1 -> pushed

batch_002:
  workspace_1
  user_c -> token_C2 -> pushed
  user_d -> token_D2 -> pushed
```

批次负责记录：

```text
本次处理了哪些 User Account
本次每个 User Account 是否加入成功
本次每个 User Account 是否生成 chatgpt_web_backend_access_token
本次每个 User Account 是否推送成功
本次失败原因
```

它不负责保存“当前最终状态”。当前最终状态仍由 Membership 保存。

批次状态拆成两类：

```text
batch_status       执行状态，表示这次批量 join/token/push 是否跑完、是否成功
activation_status  生效状态，表示这次批次结果是否被采纳为当前有效批次
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
retired       人工下线
```

判断一个批次是否生效，只看：

```text
activation_status = active
```

约束：

```text
1. failed/cancelled 批次不能 active。
2. success/partial_success 批次可以 active。
3. 同一个 Team Workspace 默认只能有一个 active 批次。
4. 新批次 active 后，旧 active 批次改成 superseded。
5. Membership 保存当前 token 和当前成员状态；active batch 只说明当前状态采纳自哪个批次。
```

## Workspace Join Batch Item

某个 User Account 在某个 Workspace Join Batch 中的一条执行记录。

同一个 User Account + Team Workspace 可以出现在多个不同 batch item 中。

例子：

```text
membership(user_a, workspace_1) 只有一条

batch_001 item: user_a -> workspace_1 -> token_A1 -> pushed
batch_002 item: user_a -> workspace_1 -> token_A2 -> pushed
```

此时：

```text
batch item 保存历史流水
membership 保存当前 chatgpt_web_backend_access_token
```

## Provider

外部系统来源或能力实现方。

Provider 必须是明确枚举，不允许写成随意字符串。

V1 固定 provider 按能力分开，不共用一个全局 provider 表：

```text
team_workspace.provider = openai_chatgpt
proxy_inventory.provider = webshare
external_mail_leases.provider = external_mail_api
downstream_provider = cpa | sub2api
```

`manual_import`、`legacy_pipeline` 只能作为 `source_type` 或 Job 来源，不作为 Team Workspace provider。

V1 不支持：

- 自维护 Cloudflare KV 邮箱。
- 自维护 IMAP 邮箱池。
- static proxy / trojan proxy / hysteria proxy。
- 多代理 provider 插拔。

原因：用户已明确要求代理统一使用 Webshare，邮箱统一使用外部邮箱接口，本服务不维护邮箱。

## Webshare Proxy

V1 唯一代理来源。

实现依据只能是 Webshare 官方 API 文档：

```text
https://apidocs.webshare.io/
```

不参考旧项目里的 WebshareClient、_rotate_webshare_ip、gost 或旧 Webshare 配置。

流程固定为：

```text
GET /api/v2/proxy/list/ 拉取 Webshare IP 池
-> 建立/更新 proxy inventory
-> 给 User Account 绑定一个 proxy
-> 后续该 User Account 的注册、支付、刷新、探测默认使用绑定 proxy
```

账号绑定代理后，不应每个 step 随机换代理。除非触发明确的 proxy repair job。

默认连接模式：Direct + username/password。

## External Mail API

V1 唯一邮箱来源。

本服务不维护：

- 邮箱账号。
- 邮箱密码。
- IMAP 连接。
- Cloudflare Email Worker。
- Cloudflare KV OTP。
- catch-all 域名池。

本服务只调用外部邮箱接口：

```text
allocate mailbox
poll OTP
mark used
mark failed / release
```

## User Account Proxy Binding

账号代理绑定。

绑定位置：`user_account_proxy_bindings`。

绑定对象：`User Account`。

不绑定在：

```text
Workflow
Job
Step
单次 HTTP 请求
```

原因：同一个账号后续注册补偿、支付、token refresh、membership probe 都必须复用同一个代理，避免同一账号在不同步骤随机切换出口。

字段：

```text
user_account_id
proxy_id
bind_status
bind_reason
bound_by_job_id
bound_at
last_used_at
last_error_code
```

## account_status

只表示账号本身是否可作为库存使用，不表示账号在哪个 Team Workspace 里的权限，也不表示 token 是否可用。

允许值：

```text
active    账号本身可用
invalid   账号本身不可用
```

token 是否可用由 `user_account_auth.refresh_token_status`、`chatgpt_web_backend_access_token_status` 等 token 状态字段表达，不放在 `account_status`。

## external_workspace_id

外部系统里的 Team Workspace ID。

对 OpenAI/ChatGPT Team 来说，当前旧项目最接近的是：

```text
chatgpt_account_id
```

这个 ID 用于调用类似接口：

```text
/backend-api/accounts/{team_id}/invites
```

## workspace_status

只表示 Team Workspace 本身状态，不表示某个 User Account 在里面是否能邀请。

允许值：

```text
unknown   未探测
active    工作区本身正常
disabled  工作区被禁用
expired   工作区过期
error     探测失败
```

## membership_status

表示某个 User Account 在某个 Team Workspace 中的关系状态。

允许值：

```text
unknown
invited
accepted
active
left
disabled
banned
failed
```

## invite_permission

表示该 Membership 是否有邀请新成员的权限。

允许值：

```text
unknown
ok
no_permission
error
```

旧代码中对应判断依据是 gpt-team 返回的 `noInvitePermission`。

## seat_status

表示该 Team Workspace 对该 Membership 当前是否还有可用席位。

允许值：

```text
unknown
available
full
error
```

旧代码中对应判断依据：

```text
userCount + inviteCount < seat_limit
```

## can_invite

派生字段，不是人工直接写入。

判断规则：

```python
can_invite = (
    workspace_status == "active"
    and membership_status == "active"
    and invite_permission == "ok"
    and seat_status == "available"
)
```

旧代码证据：`pipeline.py::TeamSystemClient.count_usable_accounts()` 中“可用”判断为：

```text
account_usage 匹配
!isBanned
!isDisabled
!noInvitePermission
!expired
userCount + inviteCount < seat_limit
```

## token_status

只表示某条 token 是否可用，不表示账号或 membership 是否可用。

允许值：

```text
unknown
active
expired
refreshing
revoked
invalid
dead
error
```

## job_status / run_status / step_status

任务系统分三层状态，不能混用：

```text
job_status   表示任务整体：queued/running/succeeded/failed/cancelled
run_status   表示某次执行尝试：running/succeeded/failed/cancelled
step_status  表示某个步骤：pending/running/succeeded/failed/skipped/retrying
```

## health_status

只用于 provider healthcheck 或系统组件健康检查，不用于 User Account、Membership、Job。

允许值：

```text
ok
degraded
failed
unknown
```
