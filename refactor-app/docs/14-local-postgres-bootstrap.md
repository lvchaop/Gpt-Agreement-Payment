# 14. 本地 PostgreSQL Bootstrap 记录

执行时间：2026-06-19

## 1. 目标

按当前设计把初始 schema 落到本地 Docker PostgreSQL。

schema 来源：

```text
docs/schema/001_initial_schema.sql
migrations/sql/001_initial_schema.sql
```

两份文件已校验一致：

```text
cmp -s docs/schema/001_initial_schema.sql migrations/sql/001_initial_schema.sql
结果：0
```

## 2. PostgreSQL 容器

容器：

```text
shared-postgres
```

镜像：

```text
postgres:16-alpine
```

版本：

```text
psql (PostgreSQL) 16.14
```

环境：

```text
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=postgres
```

## 3. 数据库

创建数据库：

```sql
CREATE DATABASE refactor_app;
```

执行结果：

```text
CREATE DATABASE
```

## 4. Schema 导入

执行命令：

```bash
docker exec -i shared-postgres psql \
  -U postgres \
  -d refactor_app \
  -v ON_ERROR_STOP=1 \
  < refactor-app/migrations/sql/001_initial_schema.sql
```

执行结果摘要：

```text
BEGIN
CREATE TABLE x15
CREATE INDEX x40+
COMMIT
```

## 5. 表校验

表数量：

```text
15
```

表清单：

```text
codex_oauth_credentials
downstream_codex_push_records
external_mail_leases
job_events
job_runs
job_steps
jobs
proxy_inventory
team_workspaces
user_account_auth
user_account_proxy_bindings
user_account_team_workspace_memberships
user_accounts
workspace_join_batch_items
workspace_join_batches
```

## 6. 关键约束校验

已确认存在：

```text
team_workspaces(provider, external_workspace_id)
user_account_team_workspace_memberships(user_account_id, team_workspace_id)
workspace_join_batches one active per team_workspace_id
workspace_join_batch_items(batch_id, user_account_id, team_workspace_id)
codex_oauth_credentials(user_account_id, team_workspace_id, codex_client_id)
downstream_codex_push_records(batch_item_id, downstream_provider)
```

partial unique index：

```sql
CREATE UNIQUE INDEX uq_workspace_join_batches_one_active
ON public.workspace_join_batches USING btree (team_workspace_id)
WHERE (activation_status = 'active'::text)
```

## 7. 回滚方式

如果需要清空本地 bootstrap：

```bash
docker exec shared-postgres psql -U postgres -d postgres -c \
  "DROP DATABASE refactor_app;"
```

不要对 shared-postgres 容器执行 `docker rm -v`，避免误删其它本地数据库数据。
