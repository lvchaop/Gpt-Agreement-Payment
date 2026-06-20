# 12. 当前设计功能点与流程实施计划

本文档只按 `refactor-app/` 当前设计来安排实现。  
它不是历史迁移计划，也不是旧功能盘点。

## 0. 依据

当前实施计划依据：

```text
docs/00-glossary.md
docs/02-capability-model.md
docs/03-architecture.md
docs/04-tech-selection.md
docs/05-code-standards.md
docs/06-logging-observability.md
docs/09-project-structure-and-tech-stack.md
docs/11-consistency-review.md
docs/schema/001_initial_schema.sql
docs/schema/ER.md
```

硬约束：

```text
1. refactor-app 是独立新项目。
2. 禁止调用 `refactor-app/` 目录外的业务代码。
3. 运行时只依赖 PostgreSQL 作为状态型中间件。
4. 不支持 SQLite。
5. 不引入 Redis / Celery / RabbitMQ / Kafka / NATS。
6. 代理只使用 Webshare。
7. Webshare 按官方文档重新实现。
8. 邮箱只使用 external_mail_api。
9. token 直接入 PostgreSQL。
10. 不引入 auth_tokens、secret_ref、token vault。
11. 不从 RT/access token claims 自动发现 workspace。
12. Team Workspace 必须由已知输入或开通流程写入。
```

## 1. 当前设计的功能点

### 1.1 User Account

功能：

```text
创建 User Account
导入 User Account
维护 email / phone / openai_user_id
维护 account_status
维护账号级 auth
```

表：

```text
user_accounts
user_account_auth
```

边界：

```text
account_status 只表示账号本身 active / invalid。
token 状态不放 account_status。
workspace 权限不放 account_status。
```

### 1.2 Team Workspace

功能：

```text
导入已知 Team Workspace
记录 provider = openai_chatgpt
记录 external_workspace_id
维护 workspace_status
维护 seat_limit / plan_type / name
```

表：

```text
team_workspaces
```

边界：

```text
Team Workspace = ChatGPT/OpenAI Team 工作区。
不是 Codex 工作区。
不是抽象空间。
不是下游分组。
```

### 1.3 Membership

功能：

```text
维护 User Account 和 Team Workspace 的当前关系。
维护 membership_status。
维护 invite_permission。
维护 user_count / invite_count / seat_status。
维护 can_invite。
维护 ChatGPT Web backend Team Workspace API token。
```

表：

```text
user_account_team_workspace_memberships
```

唯一规则：

```text
UNIQUE(user_account_id, team_workspace_id)
```

边界：

```text
Membership 是当前状态表。
不是批次流水表。
一个账号加入多个 Team Workspace，就有多条 membership。
```

### 1.4 Workspace Join Batch

功能：

```text
表示一批账号加入某个 Team Workspace 的执行批次。
记录批次级状态。
记录每个账号在该批次中的 join/token/push 结果。
支持同一个 Team Workspace 多批次。
支持同一个 User Account 在不同批次中重复出现。
```

表：

```text
workspace_join_batches
workspace_join_batch_items
```

唯一规则：

```text
workspace_join_batch_items:
  UNIQUE(batch_id, user_account_id, team_workspace_id)

workspace_join_batches:
  UNIQUE(team_workspace_id) WHERE activation_status = 'active'
```

边界：

```text
batch item 保存历史执行结果。
membership 保存当前状态。
active batch 只表示这批结果被采纳为当前有效批次。
```

### 1.5 ChatGPT Web backend Team Workspace Credential

功能：

```text
为某个 User Account + Team Workspace 构建 ChatGPT Web backend API token。
用于 Team invite / accept / probe。
```

表：

```text
user_account_team_workspace_memberships
```

字段：

```text
chatgpt_web_backend_access_token
chatgpt_web_backend_id_token
chatgpt_web_backend_access_token_expires_at
chatgpt_web_backend_access_token_status
last_chatgpt_web_backend_token_refresh_at
```

校验：

```text
access_token JWT 里的 chatgpt_account_id 必须等于 team_workspaces.external_workspace_id。
```

### 1.6 Codex OAuth Credential

功能：

```text
为某个 User Account + Team Workspace + codex_client_id 构建当前可复用 Codex OAuth token。
用于 CPA/Sub2API 下游导入。
```

表：

```text
codex_oauth_credentials
```

唯一规则：

```text
UNIQUE(user_account_id, team_workspace_id, codex_client_id)
```

边界：

```text
不保存 plan_tag / plan_type。
不保存 membership_id。
不保存下游包装字段。
token 直接入库。
```

### 1.7 Downstream Push

功能：

```text
把 Codex OAuth Credential 组装成 CPA/Sub2API 需要的 payload。
调用下游管理接口。
记录同批次 item 的推送结果。
```

表：

```text
downstream_codex_push_records
```

唯一规则：

```text
UNIQUE(batch_item_id, downstream_provider)
```

含义：

```text
同一批次 item 推同一个下游，只保留一条记录。
重试时 upsert，不追加多条。
```

### 1.8 Webshare Proxy

功能：

```text
从 Webshare 拉取 IP 池。
写入 proxy_inventory。
把 proxy 绑定到 User Account。
后续账号相关请求默认使用该绑定 proxy。
```

表：

```text
proxy_inventory
user_account_proxy_bindings
```

边界：

```text
代理绑定在 User Account 上。
不绑定在 Job / Step / 单次请求上。
```

### 1.9 External Mail API

功能：

```text
申请邮箱租约。
轮询 OTP。
标记 used。
标记 failed / released。
```

表：

```text
external_mail_leases
```

边界：

```text
本服务不维护邮箱账号。
不做 IMAP。
不做 Cloudflare KV。
不做 catch-all 域名池。
```

### 1.10 Job / Run / Step / Event

功能：

```text
API 创建 job。
Worker 消费 job。
每次执行写 job_run。
每个流程步骤写 job_step。
关键事件写 job_event。
```

表：

```text
jobs
job_runs
job_steps
job_events
```

边界：

```text
API 不同步执行长任务。
业务错误必须有 error_code。
日志使用结构化 JSON line + job_events。
```

## 2. 当前设计的核心流程

### 2.1 Webshare IP 池刷新流程

输入：

```text
webshare api token
```

步骤：

```text
1. 创建 job: proxy.refresh_webshare_pool。
2. Worker 调 Webshare plugin。
3. Webshare plugin 按官方 API 拉取 proxy list。
4. 处理分页。
5. upsert proxy_inventory。
6. 记录 provider_valid / country / city / host / port / username / password。
7. 写 job_events。
```

成功结果：

```text
proxy_inventory 有可分配 proxy。
```

### 2.2 账号代理绑定流程

输入：

```text
user_account_id
```

步骤：

```text
1. 创建 job: proxy.bind_account。
2. 读取 User Account。
3. 查询 proxy_inventory 中 available proxy。
4. 写 user_account_proxy_bindings。
5. 更新 proxy_inventory.proxy_status = bound。
6. 写 job_events。
```

成功结果：

```text
一个 User Account 只有一个 active binding。
```

### 2.3 外部邮箱租约流程

输入：

```text
user_account_id 可选
purpose
```

步骤：

```text
1. 创建 job: mail.allocate。
2. 调 external_mail_api plugin 申请邮箱。
3. 写 external_mail_leases。
4. 需要 OTP 时，创建 mail.poll_otp step。
5. OTP 成功后标记 used。
6. 失败时标记 failed / released。
```

成功结果：

```text
external_mail_leases.lease_status = used
```

### 2.4 Team Workspace 导入流程

输入：

```text
provider = openai_chatgpt
external_workspace_id
name
seat_limit
plan_type
owner_user_account_id 可选
```

步骤：

```text
1. 创建或 upsert team_workspaces。
2. 如果有 owner_user_account_id，校验 owner auth。
3. 可选创建 owner membership。
4. 写 job_events。
```

成功结果：

```text
team_workspaces 存在。
如果 owner 可证明属于该 workspace，则 membership 存在。
```

### 2.5 Membership probe 流程

输入：

```text
membership_id
```

步骤：

```text
1. 读取 membership。
2. 读取 team_workspaces.external_workspace_id。
3. 确保有 ChatGPT Web backend access token。
4. 调 OpenAI ChatGPT plugin 探测 membership / seat / invite permission。
5. 更新 membership_status / invite_permission / user_count / invite_count / seat_status。
6. 重新计算 can_invite。
7. 写 last_probe_at / last_probe_status。
8. 写 job_events。
```

成功结果：

```text
membership 当前状态可用于判断是否还能邀请。
```

### 2.6 Workspace Join Batch 流程

输入：

```text
team_workspace_id
user_account_ids[]
downstream_provider 可选
batch_name 可选
created_by
```

步骤：

```text
1. 创建 workspace_join_batches。
2. 为每个 user_account_id 创建 workspace_join_batch_items。
3. 对每个账号读取 user_account_auth。
4. 构建目标 Team Workspace 的 ChatGPT Web backend Team Workspace Credential。
5. 校验 access_token JWT chatgpt_account_id == team_workspaces.external_workspace_id。
6. upsert membership。
7. 更新 batch item join_status / token_status / generated_chatgpt_web_backend_*。
8. 如配置 downstream_provider，调用 PushCodexCredentialWorkflow。
9. 汇总 success_count / failed_count / pushed_count。
10. 更新 batch_status。
11. 写 job_events。
```

成功结果：

```text
workspace_join_batches 记录批次。
workspace_join_batch_items 记录每个账号结果。
membership 保存当前 workspace token 和当前关系状态。
```

### 2.7 Batch activation 流程

输入：

```text
batch_id
```

步骤：

```text
1. 读取 batch。
2. 校验 batch_status in success / partial_success。
3. 设置当前 batch activation_status = activating。
4. 同一个 Team Workspace 的旧 active batch 改为 superseded。
5. 当前 batch 改为 active。
6. 写 activated_at。
7. 写 job_events。
```

成功结果：

```text
同一个 Team Workspace 只有一个 active batch。
```

### 2.8 Build Codex Credential 流程

输入：

```text
user_account_id
team_workspace_id
codex_client_id
```

步骤：

```text
1. 读取 user_account_auth.refresh_token。
2. 读取 team_workspaces.external_workspace_id。
3. 查 codex_oauth_credentials 是否已有 active 且未过期且 workspace 匹配。
4. 可复用则返回 credential。
5. 不可复用则调用 OpenAI OAuth token endpoint。
6. 解析 access_token JWT。
7. 写 token_chatgpt_account_id。
8. 校验 token_chatgpt_account_id == team_workspaces.external_workspace_id。
9. upsert codex_oauth_credentials。
10. 写 job_events。
```

失败：

```text
missing_refresh_token
oauth_refresh_failed
token_decode_failed
workspace_mismatch
```

### 2.9 Push Codex Credential 流程

输入：

```text
batch_item_id
user_account_id
team_workspace_id
membership_id
downstream_provider
codex_client_id
```

步骤：

```text
1. upsert downstream_codex_push_records push_status=pending。
2. 调 BuildCodexCredentialWorkflow。
3. 读取 user_accounts.email。
4. 读取 workspace_join_batch_items.plan_tag / plan_type。
5. 构造 CPA/Sub2API payload。
6. payload 中 chatgpt_account_id = team_workspaces.external_workspace_id。
7. 校验 token_chatgpt_account_id == team_workspaces.external_workspace_id。
8. 调 downstream plugin。
9. 成功：更新 downstream_codex_push_records push_status=pushed。
10. 失败：更新 push_status=failed / error_code / error_message。
11. 同步 workspace_join_batch_items.push_status / downstream_provider / downstream_external_id。
12. 写 job_events。
```

成功结果：

```text
downstream_codex_push_records 同一 batch_item_id + downstream_provider 只有一条。
```

### 2.10 Codex Credential heartbeat 流程

输入：

```text
codex_credential_id
```

步骤：

```text
1. 读取 codex_oauth_credentials。
2. 读取 team_workspaces.external_workspace_id。
3. 校验 token_chatgpt_account_id 匹配。
4. 调 Codex responses heartbeat。
5. 更新 last_heartbeat_at / last_heartbeat_status。
6. 失败时写 last_heartbeat_error_code / last_heartbeat_error_message。
7. 写 job_events。
```

成功结果：

```text
codex_oauth_credentials.last_heartbeat_status = ok
```

## 3. 实现阶段

当前阶段状态：

```text
P0 数据库和项目骨架                 done
P1 Domain / Repository / UnitOfWork done
P2 Job / Worker / Event             done
P3 Plugin contracts                 done
P4 Webshare / External Mail 插件     done
P5 OpenAI ChatGPT 插件              done
P6 Downstream CPA / Sub2API 插件    done
P7 核心 Workflows                   done
P8 API / CLI                        done
P9 测试和验收                       done
P10 最小运维 UI                     done
```

### P0. 数据库和项目骨架

任务：

```text
1. 创建 schema 执行文件 migrations/sql/001_initial_schema.sql。
2. 创建 alembic.ini / migrations/env.py，用于 PostgreSQL schema 版本管理。
3. 在本地 PostgreSQL 创建 refactor_app database。
4. 执行 schema。
5. 校验 15 张表和关键约束。
6. 创建 docs/14-local-postgres-bootstrap.md 记录执行结果。
7. 创建 src/refactor_app 目标目录骨架。
```

验收：

```text
1. PostgreSQL 中存在 refactor_app database。
2. schema 可在空库执行成功。
3. 15 张表存在。
4. 关键 UNIQUE / FK / CHECK / partial unique index 存在。
5. 新项目目录存在。
```

### P1. Domain / Repository / UnitOfWork

任务：

```text
1. 实现 domain/enums.py。
2. 实现 domain/errors.py。
3. 实现 domain models。
4. 实现 SQLAlchemy models。
5. 实现 db engine/session。
6. 实现 UnitOfWork。
7. 实现 repositories。
```

Repository：

```text
UserAccountRepository
UserAccountAuthRepository
TeamWorkspaceRepository
MembershipRepository
WorkspaceJoinBatchRepository
WorkspaceJoinBatchItemRepository
CodexOAuthCredentialRepository
DownstreamPushRecordRepository
ProxyInventoryRepository
UserAccountProxyBindingRepository
ExternalMailLeaseRepository
JobRepository
JobRunRepository
JobStepRepository
JobEventRepository
```

验收：

```text
1. enum 与 schema CHECK 对齐。
2. repository 不返回 ORM 对象。
3. UnitOfWork 支持 commit / rollback。
4. 关键唯一约束有测试。
```

### P2. Job / Worker / Event

任务：

```text
1. 实现 Job 创建。
2. 实现 Worker 领取 queued job。
3. 实现 JobRun。
4. 实现 JobStep。
5. 实现 JobEvent writer。
6. 实现 error_code 规范。
7. 实现 JSON line logging。
```

队列策略：

```text
PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED
```

验收：

```text
1. API/CLI 创建 job 后立即返回 job_id。
2. Worker 可领取并执行 job。
3. 每个 step 有状态。
4. 失败有 error_code。
5. job_events 可查询。
```

### P3. Plugin contracts

任务：

```text
1. 实现 plugins/contracts.py。
2. 实现 plugins/registry.py。
3. 定义 ProxyProvider。
4. 定义 MailProvider。
5. 定义 OpenAIChatGPTProvider。
6. 定义 DownstreamProvider。
```

统一接口：

```text
validate_config()
healthcheck()
capabilities()
```

验收：

```text
1. Workflow 只依赖 contract。
2. Workflow 不直接 new 具体 provider client。
3. 每个 plugin 有 contract test。
```

### P4. Webshare / External Mail 插件

任务：

```text
1. 实现 Webshare list client。
2. 实现 Webshare 分页。
3. 实现 proxy_inventory upsert。
4. 实现 bind account proxy。
5. 实现 external_mail_api allocate。
6. 实现 external_mail_api poll OTP。
7. 实现 external_mail_api mark used / failed / release。
```

验收：

```text
1. Webshare API mock 覆盖分页。
2. proxy_inventory 写入正确。
3. user_account_proxy_bindings 唯一绑定正确。
4. external_mail_leases 状态流转正确。
```

### P5. OpenAI ChatGPT 插件

任务：

```text
1. 实现 refresh_token 换目标 Team Workspace access_token。
2. 实现 access_token JWT decode。
3. 实现 Team invite。
4. 实现 Team invite accept。
5. 实现 membership probe。
6. 实现 seat / invite permission probe。
```

验收：

```text
1. 必须输入 team_workspace_id。
2. 必须使用已知 external_workspace_id。
3. token_chatgpt_account_id 不匹配时失败。
4. 不自动创建其它 workspace。
```

### P6. Downstream CPA / Sub2API 插件

任务：

```text
1. 实现 CPA payload builder。
2. 实现 CPA push client。
3. 实现 Sub2API payload builder。
4. 实现 Sub2API import client。
5. 实现 downstream_push_records upsert。
```

验收：

```text
1. chatgpt_account_id = team_workspaces.external_workspace_id。
2. 不把 chatgpt_account_id 拼接成假唯一值。
3. 同一 batch_item_id + downstream_provider 重试只更新一条。
4. 成功/失败同步 batch item。
```

### P7. 核心 Workflows

按顺序实现：

```text
1. RefreshWebsharePoolWorkflow
2. BindAccountProxyWorkflow
3. ImportTeamWorkspaceWorkflow
4. MembershipProbeWorkflow
5. BuildCodexCredentialWorkflow
6. PushCodexCredentialWorkflow
7. JoinWorkspaceBatchWorkflow
8. ActivateWorkspaceJoinBatchWorkflow
9. HeartbeatCodexCredentialWorkflow
```

验收：

```text
1. 每个 workflow 可单独 dry-run。
2. 每个 workflow 写 job_steps。
3. 每个关键状态写 job_events。
4. 失败可重试。
5. 状态落表符合 schema。
```

### P8. API / CLI

API：

```text
GET  /health

POST /jobs
GET  /jobs
GET  /jobs/{job_id}
GET  /jobs/{job_id}/runs
GET  /runs/{run_id}/events

GET  /user-accounts
POST /user-accounts/import
PATCH /user-accounts/{user_account_id}

GET  /team-workspaces
POST /team-workspaces/import
GET  /team-workspaces/{team_workspace_id}

GET  /memberships
POST /memberships/probe-job

POST /workspace-join-batches
GET  /workspace-join-batches
GET  /workspace-join-batches/{batch_id}
POST /workspace-join-batches/{batch_id}/activate

GET  /codex-credentials
POST /codex-credentials/{credential_id}/heartbeat-job

GET  /downstream-push-records

POST /proxies/refresh-webshare-job
POST /proxies/bind-account-job

GET  /mail-leases
```

CLI：

```text
refactor-app db check
refactor-app db migrate
refactor-app worker run
refactor-app job enqueue
refactor-app webshare refresh
refactor-app batch create
refactor-app batch activate
refactor-app codex heartbeat
```

验收：

```text
1. API 不同步执行长任务。
2. API 创建 job 后返回 job_id。
3. CLI 能触发核心 job。
4. OpenAPI 能生成。
```

### P9. 测试和验收

测试目录：

```text
tests/unit
tests/contract
tests/integration
tests/workflow
tests/schema
```

必测：

```text
schema 空库执行
repository CRUD/upsert
UnitOfWork rollback
Webshare pagination
External Mail 状态流转
OpenAI token workspace mismatch
Codex credential reuse
Downstream push upsert
Batch activation partial unique
Job event 写入
```

验收：

```text
pytest 全部通过。
integration test 使用 PostgreSQL。
不使用 SQLite。
不 import `refactor-app/` 目录外的业务代码。
```

### P10. 最小运维 UI

页面：

```text
Job 列表
JobRun 详情
Step timeline
Event log viewer
UserAccount 管理
TeamWorkspace 管理
Membership 管理
Batch 管理
CodexCredential 管理
Proxy inventory
Mail lease 查看
```

验收：

```text
1. 能创建 batch job。
2. 能查看 batch item。
3. 能查看 downstream push record。
4. 能按 error_code 过滤失败。
5. 能查看同一账号加入多个 Team Workspace 的状态。
```

## 4. 推荐实施顺序

```text
1. P0 数据库和项目骨架
2. P1 Domain / Repository / UnitOfWork
3. P2 Job / Worker / Event
4. P3 Plugin contracts
5. P4 Webshare / External Mail 插件
6. P5 OpenAI ChatGPT 插件
7. P6 Downstream CPA / Sub2API 插件
8. P7 核心 Workflows
9. P8 API / CLI
10. P9 测试和验收
11. P10 最小运维 UI
```

## 5. 当前验收状态

已完成：

```text
P0-P10。
```

当前验收命令：

```text
cd refactor-app && PYTHONDONTWRITEBYTECODE=1 RUFF_NO_CACHE=true ../.venv/bin/ruff check src tests
cd refactor-app && PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' ../.venv/bin/python -m pytest
```

当前验证结果：

```text
ruff: All checks passed.
 pytest: 43 passed.
 db check: ok.
 db migrate: already_applied.
```
