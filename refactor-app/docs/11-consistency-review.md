# 11. 一致性审查记录

审查时间：2026-06-19

审查范围：

```text
refactor-app/docs
refactor-app/docs/schema/001_initial_schema.sql
refactor-app/docs/schema/ER.md
refactor-app/README.md
refactor-app/AGENTS.md
```

## 1. 结论

当前 V1 口径以以下文件为表结构真源：

```text
docs/schema/001_initial_schema.sql
```

解释性文档不得重新复制一份弱化版 DDL。解释性文档只描述：

```text
字段语义
状态含义
写入场景
流程边界
约束来源
```

## 2. 已修正的不一致

### 2.1 架构文档重复 DDL 与 schema 真源不一致

证据：

```text
docs/schema/001_initial_schema.sql
  使用 TIMESTAMPTZ、JSONB、BOOLEAN、FK、CHECK、partial unique index。

docs/03-architecture.md
  曾复制多段简化 DDL，使用 TEXT DEFAULT ''、INTEGER、缺少 FK/CHECK。
```

处理：

```text
docs/03-architecture.md 中的重复 CREATE TABLE 片段已改为：
  表结构真源指向 docs/schema/001_initial_schema.sql
  核心字段列表
```

保留原因：

```text
架构文档应该解释表的作用和边界，不应该成为第二份 DDL。
```

### 2.2 ChatGPT Web backend token 与 Codex OAuth token 混写

证据：

```text
docs/02-capability-model.md 曾出现 “workspace/Codex token”。
```

处理：

```text
改为 “ChatGPT Web backend Team Workspace Credential”。
```

最终口径：

```text
ChatGPT Web backend Team Workspace Credential:
  存 user_account_team_workspace_memberships。
  用于 Team Workspace invite/accept/probe。

Downstream Codex Credential:
  存 codex_oauth_credentials。
  用于构造 CPA/Sub2API 的 Codex OAuth 凭证包。
```

### 2.3 downstream_codex_push_records 的 codex_credential_id 必填口径

证据：

```text
docs/schema/001_initial_schema.sql:
  codex_credential_id TEXT REFERENCES codex_oauth_credentials(id) ON DELETE SET NULL

docs/schema/ER.md:
  曾写成写入时必须提供 codex_credential_id。
```

处理：

```text
ER 已改为：
  codex_credential_id 在 credential 构建成功后必须写入。
  pending 或 credential 构建失败时允许为空。
```

原因：

```text
downstream push record 可能先 upsert pending。
如果 credential 构建失败，需要记录失败结果，但此时没有 codex_credential_id。
```

## 3. 已确认一致的核心口径

### 3.1 账号状态

```text
account_status:
  active
  invalid
```

含义：

```text
只表示账号本身是否可作为库存使用。
不表示 token 是否可用。
不表示 membership 是否可用。
不表示是否能邀请成员。
```

### 3.2 Team Workspace

```text
team_workspaces.provider = openai_chatgpt
```

`external_workspace_id` 含义：

```text
OpenAI/ChatGPT 侧 Team Workspace ID。
对应 ChatGPT backend account/workspace 维度。
用于 /backend-api/accounts/{team_id}/...。
```

### 3.3 Membership

唯一约束：

```text
UNIQUE(user_account_id, team_workspace_id)
```

含义：

```text
同一个 User Account 加入同一个 Team Workspace，只维护一行当前状态。
历史执行结果由 workspace_join_batch_items 保存。
```

### 3.4 批次

批次状态拆成两类：

```text
batch_status:
  执行状态。

activation_status:
  是否被采纳为当前有效批次。
```

同一个 Team Workspace 默认只允许一个生效批次：

```sql
UNIQUE(team_workspace_id) WHERE activation_status = 'active'
```

### 3.5 Codex OAuth credential

唯一约束：

```text
UNIQUE(user_account_id, team_workspace_id, codex_client_id)
```

含义：

```text
同一个 User Account、同一个 Team Workspace、同一个 Codex client_id
只有一条当前可复用 Codex OAuth credential。
```

不保存：

```text
plan_tag
plan_type
membership_id
Sub2API 包装常量
CPA 导出名
```

### 3.6 下游推送流水

表：

```text
downstream_codex_push_records
```

唯一约束：

```text
UNIQUE(batch_item_id, downstream_provider)
```

含义：

```text
同一个批次 item 推同一个下游，只保留一条记录。
重试时 upsert，不追加多条。
```

### 3.7 Webshare

口径：

```text
V1 唯一代理来源是 Webshare。
必须按官方 API 文档重新实现。
不参考旧项目实现。
```

代理绑定位置：

```text
user_account_proxy_bindings
```

绑定对象：

```text
User Account
```

### 3.8 邮箱

口径：

```text
V1 唯一邮箱来源是 external_mail_api。
本服务不维护邮箱账号、IMAP、Cloudflare KV、catch-all 域名。
```

### 3.9 存储和中间件

口径：

```text
唯一状态型中间件：PostgreSQL
不支持 SQLite。
不引入 Redis、Celery、RabbitMQ、Kafka、NATS。
```

## 4. 后续落地要求

进入代码阶段前必须满足：

```text
1. Alembic migration 从 docs/schema/001_initial_schema.sql 转换。
2. domain enum 必须从 schema CHECK 约束生成或人工一一对齐。
3. repository 测试必须覆盖关键唯一约束：
   - team_workspaces(provider, external_workspace_id)
   - user_account_team_workspace_memberships(user_account_id, team_workspace_id)
   - workspace_join_batches one active per team_workspace_id
   - workspace_join_batch_items(batch_id, user_account_id, team_workspace_id)
   - codex_oauth_credentials(user_account_id, team_workspace_id, codex_client_id)
   - downstream_codex_push_records(batch_item_id, downstream_provider)
4. 禁止新增 auth_tokens、user_account_identifiers、provider profile、secret_ref、token vault。
```
