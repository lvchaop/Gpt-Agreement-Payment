# 09. 项目目录结构与技术选型落地

本文档定义 `refactor-app/` 的目标目录结构和 V1 技术栈。

约束来源：

- `AGENTS.md`：本目录是独立新项目，禁止调用老项目业务代码。
- `docs/schema/001_initial_schema.sql`：表结构事实来源。
- `docs/04-tech-selection.md`：技术选型原则。
- `docs/05-code-standards.md`：代码规范。
- `docs/06-logging-observability.md`：日志与事件规范。

## 1. 目录结构

目标结构：

```text
refactor-app/
  AGENTS.md
  README.md
  pyproject.toml
  alembic.ini

  docs/
    00-glossary.md
    01-evidence-and-goals.md
    02-capability-model.md
    03-architecture.md
    04-tech-selection.md
    05-code-standards.md
    06-logging-observability.md
    08-architecture-decisions.md
    09-project-structure-and-tech-stack.md
    11-consistency-review.md
    12-implementation-plan.md
    14-local-postgres-bootstrap.md
    schema/
      001_initial_schema.sql
      ER.md

  src/
    refactor_app/
      __init__.py
      main.py

      api/
        app.py
        dependencies.py
        routes/
          health.py
          user_accounts.py
          team_workspaces.py
          memberships.py
          batches.py
          codex_credentials.py
          downstream_pushes.py
          proxies.py
          mail_leases.py
          jobs.py

      cli/
        main.py

      config/
        settings.py

      domain/
        enums.py
        errors.py
        models/
          user_account.py
          team_workspace.py
          membership.py
          batch.py
          codex_credential.py
          proxy.py
          mail.py
          job.py
        services/
          membership_policy.py
          batch_activation_policy.py
          codex_credential_policy.py

      application/
        dto/
        use_cases/
        workflows/
          register_account.py
          import_team_workspace.py
          join_workspace_batch.py
          build_codex_credential.py
          push_codex_credential.py
          probe_membership.py
          refresh_webshare_pool.py
          bind_account_proxy.py
        jobs/
          queue.py
          runner.py
          scheduler.py
          unit_of_work.py

      ports/
        repositories.py
        plugins.py
        clock.py
        id_generator.py
        transaction.py

      infrastructure/
        db/
          engine.py
          models.py
          repositories.py
          unit_of_work.py
        http/
          client.py
        logging/
          json_logger.py
          event_writer.py
        migrations/
          versions/

      plugins/
        registry.py
        contracts.py
        proxy_webshare/
          plugin.py
          client.py
          schemas.py
        mail_external_api/
          plugin.py
          client.py
          schemas.py
        downstream_cpa/
          plugin.py
          client.py
          schemas.py
        downstream_sub2api/
          plugin.py
          client.py
          schemas.py
        openai_chatgpt/
          plugin.py
          oauth.py
          team_workspace.py
          schemas.py

  frontend/
    package.json
    vite.config.ts
    src/
      main.ts
      api/
      pages/
      components/
      stores/

  tests/
    unit/
    contract/
    integration/
    workflow/
    migration/
```

## 2. 分层边界

### 2.1 `domain/`

只放领域模型、状态枚举、领域规则。

允许：

```text
纯 Python dataclass / Pydantic model
状态转换规则
领域错误类型
```

禁止：

```text
SQLAlchemy model
HTTP client
FastAPI Request/Response
环境变量读取
插件实现
老项目 import
```

### 2.2 `application/`

负责用例、workflow、job 编排。

允许依赖：

```text
domain
ports
```

禁止直接依赖：

```text
具体 SQLAlchemy repository
具体 Webshare client
具体 CPA/Sub2API client
具体 FastAPI 对象
```

### 2.3 `ports/`

定义接口协议。

典型接口：

```text
UserAccountRepository
TeamWorkspaceRepository
MembershipRepository
JobRepository
ProxyProvider
MailProvider
DownstreamProvider
OpenAIChatGPTProvider
UnitOfWork
```

### 2.4 `infrastructure/`

实现数据库、HTTP、日志、事务。

允许：

```text
SQLAlchemy
Alembic
httpx
python-json-logger
```

禁止：

```text
业务流程编排
跨 provider 决策
老项目 adapter
```

### 2.5 `plugins/`

每个外部系统一个插件目录。

V1 插件固定为：

```text
proxy_webshare
mail_external_api
downstream_cpa
downstream_sub2api
openai_chatgpt
```

插件只能通过 `ports/plugins.py` 暴露能力，不允许 workflow 直接 import 插件内部 client。

### 2.6 `api/`

只负责 HTTP 入参、出参、创建 Job、查询状态。

API 进程禁止同步执行长任务：

```text
注册账号
批量加入 workspace
构建 token
推送 CPA/Sub2API
Webshare 拉池
membership probe
```

这些动作必须创建 Job，由 worker 执行。

### 2.7 `frontend/`

独立新前端，不复用老 `webui/` 代码。

页面按领域划分：

```text
User Accounts
Team Workspaces
Memberships
Batches
Codex Credentials
Proxy Inventory
Mail Leases
Jobs
Job Runs
Job Events
Settings
```

## 3. 技术选型

### 3.1 后端

| 类别 | 选型 | 说明 |
| --- | --- | --- |
| 语言 | Python 3.12+ | `pyproject.toml` 已声明 `requires-python >=3.12`。 |
| API | FastAPI | API 只创建 Job 和查询状态。 |
| ASGI Server | Uvicorn | 本地和部署都使用同一入口。 |
| Schema | Pydantic v2 | API DTO、插件配置、Job input/output。 |
| 配置 | Pydantic Settings | env + 本地配置文件。 |
| DB | PostgreSQL 16+ | 唯一支持数据库；DDL 以 `docs/schema/001_initial_schema.sql` 为准。 |
| ORM/SQL | SQLAlchemy 2.x | repository 层使用。 |
| Migration | Alembic | schema 迁移。 |
| HTTP Client | httpx | Webshare、OpenAI ChatGPT、CPA、Sub2API、外部邮箱接口。 |
| 日志 | stdlib logging + python-json-logger | 输出 JSON line。 |
| CLI | Typer | 本地诊断、手动触发 Job、迁移工具。 |
| 测试 | pytest | unit/contract/integration/workflow/migration。 |

### 3.2 数据库访问策略

V1 使用同步 SQLAlchemy repository。

理由：

```text
1. worker/job 执行天然是后台任务，同步事务模型更简单。
2. 当前核心问题是领域模型和任务可恢复性，不是高并发 API。
3. FastAPI 支持同步 endpoint；API 只做轻量创建/查询。
```

约束：

```text
1. 所有写操作必须通过 UnitOfWork。
2. repository 不返回 SQLAlchemy ORM 对象给 domain/application。
3. migration 先从 docs/schema/001_initial_schema.sql 转为 Alembic revision。
4. 不支持 SQLite；本地、测试、生产都使用 PostgreSQL。
```

### 3.3 Job 队列

V1 使用 PostgreSQL 表实现 Job 队列。

不引入第三方队列中间件：

```text
Redis
RQ
Arq
Celery
Dramatiq
RabbitMQ
Kafka
NATS
```

落点：

```text
jobs
job_runs
job_steps
job_events
```

Worker 行为：

```text
1. 从 jobs 选择 queued 任务。
2. 创建 job_runs。
3. 每个 workflow step 写 job_steps。
4. 所有关键状态和错误写 job_events。
5. 失败按 error_code 判断是否可重试。
```

运行时依赖边界：

```text
唯一状态型中间件：PostgreSQL
不需要独立 broker
不需要独立 result backend
不需要独立 cache server
```

### 3.4 插件机制

V1 使用本地 registry。

```text
plugins/registry.py
plugins/contracts.py
```

不使用 entry points 作为 V1 必需能力。entry points 只作为后续拆包方案。

插件范围固定：

```text
proxy_webshare:
  Webshare 官方 API 重新实现；不参考旧项目实现。

mail_external_api:
  外部邮箱接口；本服务不维护邮箱账号。

downstream_cpa:
  CPA 管理接口。

downstream_sub2api:
  Sub2API 管理接口。

openai_chatgpt:
  Team Workspace、membership、OAuth/token 相关能力。
```

### 3.5 前端

| 类别 | 选型 |
| --- | --- |
| 框架 | Vue 3 |
| 构建 | Vite |
| 语言 | TypeScript |
| 路由 | Vue Router |
| 状态 | Pinia |

前端边界：

```text
1. 不复用老 webui 代码。
2. 只调用 refactor-app 后端 API。
3. UI 重点是 Job 状态、事件日志、库存管理和批次管理。
```

### 3.6 日志与事件

运行日志：

```text
stdout JSON line
```

业务事件：

```text
job_events
```

必须包含：

```text
trace_id
job_id
run_id
step_id
user_account_id
team_workspace_id
membership_id
batch_id
batch_item_id
error_code
```

## 4. 禁止项

```text
1. 禁止 import 老项目模块。
2. 禁止 subprocess 调老项目脚本完成业务逻辑。
3. 禁止 sys.path 指向老项目目录。
4. 禁止把旧 webui 当组件库复制使用。
5. 禁止在 API 请求里执行长任务。
6. 禁止 workflow 直接调用具体 provider client。
7. 禁止引入 auth_tokens 泛化表、secret_ref、token vault。
8. 禁止从 RT/access token claims 自动发现 workspace 并创建记录。
```

## 5. 当前设计功能点落地顺序

```text
1. PostgreSQL schema / Alembic revision / DB 连接。
2. Domain enum / model / repository / unit of work。
3. PostgreSQL job queue / worker / job_run / job_step / job_event。
4. Plugin contracts / plugin registry。
5. Webshare proxy pool refresh / account proxy binding。
6. External Mail API lease / OTP / used / failed / released。
7. OpenAI ChatGPT Team Workspace invite / accept / probe / token refresh。
8. Codex OAuth credential build / reuse / heartbeat。
9. CPA / Sub2API payload build / push / push record upsert。
10. Workspace join batch create / item execute / activate。
11. API / CLI 触发以上流程。
12. 最小运维 UI 查看 job、batch、membership、credential、proxy、mail lease。
```
