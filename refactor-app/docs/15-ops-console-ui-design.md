# 15. Ops Console UI Design

本文档是 `/ops` 运维台重设计稿。  
当前阶段只设计，不实现。

## 1. 设计目标

`/ops` 不是接口调试页，也不是按钮集合。

它应该服务三个主流程：

```text
1. 看状态：系统有没有失败、卡住、缺资源。
2. 跑流程：选择账号 -> 加入 Team Workspace -> 生成 token -> 推送下游。
3. 查问题：从 Batch / Job / Run / Step / Event 追到具体 error_code。
```

核心原则：

```text
少暴露 JSON。
多用表单和选择器。
所有长任务只创建 Job。
创建 Job 后自动进入 Job Trace。
错误必须能从列表直接看到 error_code。
```

## 2. 信息架构

左侧主导航：

```text
Dashboard
Jobs
Accounts
Team Workspaces
Memberships
Join Batches
Codex Credentials
Proxy
Mail
Downstream
```

顶部状态栏：

```text
Refactor Ops Console
DB: OK
API: OK
Worker: Manual
Last refresh: 13:20:01
```

## 3. 视觉方向

后台工具风格，深色、紧凑、专业。

颜色：

```text
page_bg        #0B1020
sidebar_bg     #0F172A
panel_bg       #111827
panel_bg_2     #172033
border         #263249
text_primary   #E5E7EB
text_muted     #94A3B8
accent         #3B82F6
success        #22C55E
warning        #F59E0B
danger         #EF4444
purple         #A855F7
```

组件风格：

```text
radius: 10-14px
card padding: 16-20px
table row height: 42px
font: system UI
数字指标: 24-30px / 700
导航文字: 13px / 600
表格文字: 13px
状态全部使用 badge
```

## 4. 总布局

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Topbar                                                                       │
│ Refactor Ops Console                 DB OK   API OK   Worker Manual          │
├───────────────┬──────────────────────────────────────────────────────────────┤
│ Sidebar       │ Page header                                                   │
│               │ Title + description + primary action                          │
│ Dashboard     ├──────────────────────────────────────────────────────────────┤
│ Jobs          │ KPI cards                                                     │
│ Accounts      ├──────────────────────────────────────────────────────────────┤
│ Workspaces    │ Main table / detail / form / trace                            │
│ Memberships   │                                                              │
│ Batches       │                                                              │
│ Credentials   │                                                              │
│ Proxy         │                                                              │
│ Mail          │                                                              │
│ Downstream    │                                                              │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

## 5. Dashboard 页面

### 5.1 KPI Cards

第一屏必须先回答“系统现在怎么样”。

```text
Queued Jobs
Running Jobs
Failed Jobs
Active Workspaces
Active Memberships
Token Errors
Proxy Available
Mail Leases
```

卡片结构：

```text
label
value
delta / helper
status color
```

示例：

```text
┌────────────────────┐
│ Failed Jobs         │
│ 12                  │
│ last 24h            │
└────────────────────┘
```

### 5.2 Recent Failed Jobs

字段：

```text
job_id
type
error_code
error_message
updated_at
action: View Trace
```

### 5.3 Recent Batches

字段：

```text
batch_id
workspace
batch_status
activation_status
total
success
failed
action: View Batch
```

## 6. Join Batches 页面

这是主业务页面，优先级最高。

### 6.1 Batch 列表

```text
batch_id
workspace_name
batch_status
activation_status
total_count
success_count
failed_count
pushed_count
created_by
created_at
```

状态展示：

```text
success          green
partial_success  amber
failed           red
running          blue
active           purple
inactive         gray
```

### 6.2 创建 Batch 表单

不要 JSON textarea。

```text
Team Workspace     select / searchable input
Codex Client ID    input
Batch Name         input
Created By         input
User Account IDs   multiline，一行一个
Downstream         none / cpa / sub2api
```

提交行为：

```text
点击 Create Batch Job
-> POST /workspace-join-batches
-> 返回 job_id
-> 自动切到 Jobs 页面并打开该 job trace
```

### 6.3 Batch Detail

```text
Header:
  batch_id
  workspace
  status badge
  activation badge
  [Activate Batch] [Export Failed Items] [Refresh]

Summary:
  total / success / failed / pushed

Items table:
  user_account_id
  item_status
  join_status
  token_status
  push_status
  plan_tag
  failure_code
  failure_message
```

失败项必须突出：

```text
failure_code 红色 badge
failure_message 单行截断，hover/title 显示完整
```

## 7. Jobs 页面

### 7.1 Job 列表

```text
job_id
type
job_status
priority
created_by
created_at
updated_at
action: Trace
```

筛选：

```text
status
type
error_code
keyword
```

### 7.2 Job Trace 详情

详情页分三段：

```text
Job Summary
Run Timeline
Events
```

Run Timeline：

```text
run_id
run_status
attempt
started_at
finished_at
error_code
```

Step Timeline：

```text
step name
status
duration
error_code
```

Event Log：

```text
level
event_type
message
data_json
```

功能：

```text
按 level 过滤
按 event_type 过滤
复制 event JSON
```

## 8. Team Workspaces 页面

列表：

```text
name
external_workspace_id
provider
plan_type
seat_limit
workspace_status
last_probe_at
```

操作：

```text
Import Workspace
View Memberships
View Batches
Create Join Batch
```

导入表单：

```text
external_workspace_id
name
plan_type
seat_limit
workspace_status
```

## 9. Accounts 页面

列表：

```text
email
phone_number
openai_user_id
account_status
created_at
```

操作：

```text
Import Account
Bind Proxy
View Memberships
View Credentials
```

账号状态只显示：

```text
active
invalid
```

不要把 token 状态混在 account_status。

## 10. Memberships 页面

列表：

```text
user_account_id
team_workspace_id
membership_status
invite_permission
seat_status
can_invite
chatgpt_web_backend_access_token_status
last_probe_at
```

操作：

```text
Probe
Invite Member
View Workspace
View Account
```

Invite Member 表单：

```text
inviter_membership_id
email
```

## 11. Codex Credentials 页面

列表：

```text
user_account_id
team_workspace_id
codex_client_id
credential_status
token_chatgpt_account_id
expires_at
last_heartbeat_status
last_heartbeat_at
```

操作：

```text
Heartbeat
Copy credential id
View account
View workspace
```

token 明文不默认展示。

## 12. Proxy 页面

列表：

```text
proxy_host
proxy_port
country_code
city_name
proxy_status
provider_valid
last_provider_verification_at
last_healthcheck_at
```

操作：

```text
Refresh Webshare Pool
Bind Account Proxy
```

## 13. Mail 页面

列表：

```text
email
external_lease_id
lease_status
allocated_at
used_at
released_at
failure_code
```

操作：

```text
Allocate Lease
Poll OTP
Mark Used
Mark Failed
Release
```

表单：

```text
user_account_id optional
purpose
mail_lease_id
timeout_s
failure_code
failure_message
reason
```

## 14. Downstream 页面

列表：

```text
batch_item_id
downstream_provider
push_status
downstream_external_id
downstream_chatgpt_account_id
token_chatgpt_account_id
error_code
error_message
```

操作：

```text
View batch item
Copy failure
```

## 15. 交互规范

### 15.1 创建 Job

所有创建 Job 的操作必须统一：

```text
1. 用户填表单。
2. 点击主按钮。
3. 页面显示确认摘要。
4. POST 创建 job。
5. toast 显示 job_id。
6. 自动跳转 Jobs -> Trace。
```

### 15.2 表格

所有表格统一支持：

```text
Refresh
Search
Status filter
Row action
Empty state
Error state
```

### 15.3 错误显示

错误显示优先级：

```text
error_code badge
error_message short text
raw JSON collapsible
```

不要只 dump JSON。

## 16. 前端技术边界

必须使用当前技术选型：

```text
Vue 3
Vite
TypeScript
Vue Router
Pinia
```

边界：

```text
1. 前端目录放在 refactor-app/frontend。
2. 禁止复用老项目 webui 代码。
3. 只调用 refactor-app 后端 API。
4. 不直接访问数据库。
5. 不在浏览器里保存 token 明文。
6. API 创建 Job 后，前端跳转到 Job Trace 页面。
```

推荐目录：

```text
frontend/
  package.json
  index.html
  vite.config.ts
  tsconfig.json
  src/
    main.ts
    App.vue
    router/
      index.ts
    stores/
      ops.ts
    api/
      client.ts
      jobs.ts
      resources.ts
    layouts/
      OpsLayout.vue
    components/
      StatusBadge.vue
      DataTable.vue
      PageHeader.vue
      MetricCard.vue
      JsonBlock.vue
      ConfirmModal.vue
      ToastHost.vue
    views/
      DashboardView.vue
      JobsView.vue
      JobTraceView.vue
      AccountsView.vue
      TeamWorkspacesView.vue
      MembershipsView.vue
      JoinBatchesView.vue
      BatchDetailView.vue
      CodexCredentialsView.vue
      ProxyView.vue
      MailView.vue
      DownstreamView.vue
    styles/
      tokens.css
      app.css
```

FastAPI 集成方式：

```text
开发：Vite dev server 调 FastAPI API。
生产：Vite build 输出 dist，由 FastAPI 挂载静态文件。
```

## 17. 验收标准

视觉：

```text
不再是按钮堆。
左侧导航清晰。
Dashboard 首屏能看系统状态。
状态字段全部 badge 化。
表格密度适中，可读。
主操作按钮明确。
```

功能：

```text
能创建 Batch Job。
能查看 Batch Items。
能查看 Job Trace。
能查看 Events。
能触发 Membership Probe / Invite。
能触发 Credential Heartbeat。
能触发 Proxy Refresh / Bind。
能触发 Mail lifecycle jobs。
```

可用性：

```text
日常操作不要求手写 JSON。
失败原因能从列表定位。
创建 Job 后能追踪执行。
```

## 18. Frontend Builder Review 结论

按 `build-web-apps:frontend-app-builder` 标准审查，当前设计稿结论：

```text
结论：方向可用，但实现前还必须补足交互规格和视觉验收规则。
不能直接开工。
```

已满足：

```text
1. 明确这是 dashboard/tooling surface，不是营销页。
2. 明确 Vue 3 / Vite / TypeScript / Vue Router / Pinia。
3. 明确不复用老 webui。
4. 明确 Dashboard / Jobs / Batch / Membership 等核心页面。
5. 明确状态 badge、表格、Job Trace、Batch Detail 是核心组件。
```

原设计缺口：

```text
1. 缺少 Vue Router 路由表。
2. 缺少 API endpoint -> 页面动作映射。
3. 缺少 loading / empty / error / submitting 状态。
4. 缺少响应式断点。
5. 缺少表格列宽、溢出、复制、筛选行为。
6. 缺少 modal / toast / confirm 的交互定义。
7. 缺少视觉验收 checklist。
8. 缺少 image concept 或等价视觉规格。
```

处理方式：

```text
下面新增 19-25 节作为实现前置规格。
没有完成这些规格，不进入编码。
```

## 19. Vue Router 路由表

```text
/                         -> DashboardView
/jobs                     -> JobsView
/jobs/:jobId              -> JobTraceView
/accounts                 -> AccountsView
/team-workspaces          -> TeamWorkspacesView
/memberships              -> MembershipsView
/join-batches             -> JoinBatchesView
/join-batches/:batchId    -> BatchDetailView
/codex-credentials        -> CodexCredentialsView
/proxy                    -> ProxyView
/mail                     -> MailView
/downstream               -> DownstreamView
```

路由行为：

```text
1. 创建 Job 成功后跳转 /jobs/:jobId。
2. Batch 列表点击 batch_id 跳转 /join-batches/:batchId。
3. Job Trace 页面根据 job_id 自动加载 runs、steps、events。
4. Sidebar 当前路由高亮。
5. 所有详情页保留返回列表入口。
```

## 20. API 映射

### 20.1 Dashboard

首版不新增聚合 API，前端并发调用现有 API 后本地聚合。

```text
GET /jobs
GET /team-workspaces
GET /memberships
GET /workspace-join-batches
GET /codex-credentials
GET /proxies
GET /mail-leases
GET /downstream-push-records
```

### 20.2 Jobs

```text
GET  /jobs
POST /jobs
GET  /jobs/{job_id}
GET  /jobs/{job_id}/runs
GET  /runs/{run_id}/steps
GET  /runs/{run_id}/events
```

### 20.3 Team Workspaces

```text
GET  /team-workspaces
POST /team-workspaces/import
GET  /team-workspaces/{team_workspace_id}
```

### 20.4 Join Batches

```text
GET  /workspace-join-batches
POST /workspace-join-batches
GET  /workspace-join-batches/{batch_id}
GET  /workspace-join-batches/{batch_id}/items
POST /workspace-join-batches/{batch_id}/activate
```

### 20.5 Memberships

```text
GET  /memberships
POST /memberships/probe-job
POST /memberships/invite-member-job
```

### 20.6 Mail

```text
GET  /mail-leases
POST /mail/allocate-job
POST /mail/poll-otp-job
POST /mail/mark-used-job
POST /mail/mark-failed-job
POST /mail/release-job
```

### 20.7 Proxy

```text
GET  /proxies
POST /proxies/refresh-webshare-job
POST /proxies/bind-account-job
```

### 20.8 Codex Credentials

```text
GET  /codex-credentials
POST /codex-credentials/{credential_id}/heartbeat-job
```

### 20.9 Downstream

```text
GET /downstream-push-records
```

## 21. 组件规格

### 21.1 StatusBadge

输入：

```text
value
domain: job | batch | activation | membership | token | proxy | mail | push | generic
```

状态颜色：

```text
succeeded / success / active / ok / pushed / available / used     green
running / refreshing / queued / pending                           blue
partial_success / warning / allocated / cooldown                  amber
failed / invalid / error / dead / revoked / banned                 red
unknown / inactive / skipped / missing                            gray
superseded / token_generated                                      purple
```

### 21.2 DataTable

必须支持：

```text
loading state
empty state
error state
row hover
sticky header
column truncate
copy cell value
row action slot
client-side search
status filter
```

禁止：

```text
不要把长 JSON 塞进表格单元格。
不要让 error_message 撑爆横向布局。
```

### 21.3 ConfirmModal

用于所有创建 Job 的动作。

显示：

```text
action title
summary fields
destructive warning if needed
confirm button
cancel button
```

### 21.4 ToastHost

类型：

```text
success
error
info
warning
```

创建 Job 成功 toast：

```text
Job created: {job_id}
View Trace
```

### 21.5 JsonBlock

用途：

```text
Job input_json
Run output_json
Event data_json
Raw API response
```

必须支持：

```text
collapse / expand
copy
monospace
max-height scroll
```

## 22. 页面状态规格

每个页面必须有：

```text
initial loading
loaded
empty
api error
submitting
submit success
submit failed
```

错误态格式：

```text
标题：请求失败
正文：method path
详情：status / message
操作：Retry
```

空态示例：

```text
No join batches yet.
Create a batch to join accounts into a Team Workspace.
```

## 23. 响应式规格

桌面优先，但不能移动端炸掉。

断点：

```text
desktop >= 1200px
tablet  768px - 1199px
mobile  < 768px
```

桌面：

```text
sidebar 固定 240px
content max-width none
table 横向填满
```

tablet：

```text
sidebar 缩到 icon + text compact
KPI cards 两列
表格允许横向滚动
```

mobile：

```text
sidebar 变 top nav / drawer
KPI cards 单列
表单单列
表格使用横向滚动，不改成卡片
```

注意：

```text
build-web-apps 技能明确要求 dashboard/tool 不要把 table-driven UI 改成 card grid。
移动端也保持表格，只允许横向滚动。
```

## 24. 视觉验收 Checklist

实现完成后必须检查：

```text
1. 首屏是否能一眼看出系统状态。
2. 左侧导航是否清晰，当前页面是否高亮。
3. 状态是否全部 badge 化。
4. Job Trace 是否能从 Job 看到 Run / Step / Event。
5. Batch Detail 是否能看到 failed item 和 failure_code。
6. 创建 Job 是否不需要手写 JSON。
7. 创建 Job 后是否自动跳转 trace。
8. 表格长字段是否截断且可复制。
9. 空态 / loading / error 是否不是浏览器默认样式。
10. 1366x768 下首屏是否可用。
11. 390px 宽移动端是否无布局溢出到页面外。
```

## 25. Image Concept 说明

`build-web-apps:frontend-app-builder` 标准流程要求先生成视觉概念图再实现。

当前执行环境没有暴露可调用的 `image_gen` 工具，因此本设计稿先提供文字版高保真规格。

如果后续环境可用 image generation，应生成以下概念图作为实现基准：

```text
Use case: ui-mockup
Asset type: operations dashboard primary screen
Primary request: dark professional operations console for managing jobs, workspaces,
accounts, memberships, batches, credentials, proxies, mail leases, and downstream pushes.
Style/medium: high-fidelity SaaS admin dashboard UI mockup.
Composition/framing: desktop 1440x1024, fixed left sidebar, top status bar,
KPI cards, recent failed jobs table, recent batches table.
Color palette: #0B1020 background, #0F172A sidebar, #111827 panels,
#3B82F6 accent, green/amber/red/purple status badges.
Text: "Refactor Ops Console", "Dashboard", "Jobs", "Join Batches",
"Failed Jobs", "Recent Failed Jobs", "Recent Batches", "View Trace".
Constraints: no marketing hero, no decorative cards, no fake illustrations,
table-driven operations UI, dense but readable, production admin console.
Avoid: browser-default controls, plain JSON dumps, oversized buttons, card-grid replacement for tables.
```

如果不使用 image concept，则必须由用户明确接受本文字设计稿作为实现基准。
