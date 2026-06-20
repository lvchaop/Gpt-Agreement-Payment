# 04. 技术选型

## 1. 选型原则

1. 优先选择能快速承接现有 Python 代码的方案。
2. Job、日志、状态必须持久化。
3. 插件接口要稳定，但 V1 不做多代理/多邮箱 provider；代理固定 Webshare，邮箱固定外部邮箱接口。
4. 避免在第一阶段引入过重平台。
5. 保留本地运行和部署运行两种模式。

## 2. 推荐主栈

### 2.1 后端语言：Python 3.12+

推荐：Python。

理由：

- 旧项目主体是 Python。
- 现有 Playwright/Camoufox/HTTP 协议逻辑主要在 Python。
- 迁移成本最低。
- 插件生态足够。

不建议第一阶段改 Go/Java：

- 会导致旧逻辑 adapter 成本过高。
- 协议自动化代码难以快速迁移。

### 2.2 Web 框架：FastAPI

推荐：FastAPI。

理由：

- 当前 WebUI 后端已使用 FastAPI。
- Pydantic schema 适合定义插件配置、Job input/output。
- 异步 API、SSE、OpenAPI 支持好。

### 2.3 数据库：PostgreSQL only

推荐：

- 生产：PostgreSQL。
- 本地开发：PostgreSQL。
- 测试：PostgreSQL。

理由：

- 表结构使用 `TIMESTAMPTZ`、`JSONB`、partial unique index 等 PostgreSQL 能力。
- Job、JobRun、JobStep、JobEvent 需要稳定事务和并发锁语义。
- V1 不做双数据库兼容，避免 repository、migration、测试行为分叉。

约束：

- schema 只按 PostgreSQL 设计。
- 本地运行也必须连接 PostgreSQL。
- 单元测试可以 mock repository；集成测试必须用 PostgreSQL。

### 2.4 ORM / SQL 层：SQLAlchemy 2.x + Alembic

推荐：SQLAlchemy Core/ORM + Alembic。

理由：

- Python 生态成熟。
- 支持 PostgreSQL。
- migration 管理清晰。

使用规范：

- 领域对象不要直接等于 ORM model。
- repository 层隔离数据库实现。

### 2.5 Job 队列：PostgreSQL only

V1 只使用 PostgreSQL 表实现 Job 队列。

不引入：

```text
Redis
RQ
Arq
Celery
Dramatiq
RabbitMQ
Kafka
NATS
独立结果后端
```

选择 PostgreSQL Job 队列的理由：

- 运行时中间件只有 PostgreSQL。
- 容易审计。
- 容易和 JobRun/Step/Event 一起事务化。
- 满足当前单机/少量 worker 场景。
- 避免任务状态在数据库和第三方队列之间不一致。

PostgreSQL 队列表：

```text
jobs
job_runs
job_steps
job_events
```

如果后续吞吐不足，优先优化 PostgreSQL 索引、锁策略、worker 并发和任务拆分；不在 V1 规划第三方队列中间件。

### 2.6 配置管理：Pydantic Settings

推荐：Pydantic Settings。

理由：

- 类型校验。
- 支持 env、文件、默认值。
- 适合插件配置 schema。

配置分层：

```text
system config
plugin config
workflow config
job input
downstream admin credential
```

V1 按当前表结构落地：`access_token`、`id_token`、`refresh_token`、Webshare `proxy_password` 直接存 DB 字段。  
不要在 V1 引入 `secret_ref`、token vault、密文引用表。  
如果后续要上生产级密钥管理，只能作为 V2 迁移，不改变 V1 的表含义。

### 2.7 插件加载：Python entry points + 本地 registry

第一阶段推荐本地 registry：

```python
registry.register(WebshareProxyPlugin())
registry.register(ExternalMailApiPlugin())
```

第二阶段支持 Python package entry points：

```text
[project.entry-points."app.plugins"]
proxy_webshare = "plugins.proxy_webshare:plugin"
mail_external_api = "plugins.mail_external_api:plugin"
```

理由：

- 本地 registry 调试简单。
- entry points 适合后续拆成独立包。

### 2.8 前端：Vue 3 保留

推荐：继续使用 Vue 3。

理由：

- 当前 WebUI 已是 Vue 3/Vite。
- 重构重点是后端能力平台，不是 UI 技术迁移。

前端应从“运行按钮 + 日志文本”改为：

- Job 列表。
- JobRun 详情。
- Step timeline。
- Event log viewer。
- UserAccount/TeamWorkspace/Membership 管理页。
- Plugin config/health 页面。

### 2.9 日志：structlog 或标准 logging + JSON Formatter

推荐第一阶段：标准 logging + JSON Formatter。

理由：

- 引入成本低。
- 和现有 logging 兼容。
- 后续可迁移 structlog。

日志输出必须是 JSON line。

### 2.10 测试：pytest

推荐：pytest。

理由：

- 当前已有 pytest。
- 适合 workflow、plugin、repository 测试。

测试类型：

```text
unit
contract
integration
workflow
migration
e2e smoke
```

## 3. 不推荐选项

### 3.1 第一阶段不推荐微服务化

原因：

- 领域边界还没稳定。
- 微服务会放大调试成本。
- 当前核心问题是模型和执行体系，不是部署拆分。

### 3.2 V1 不使用第三方队列中间件

原因：

- 当前要求运行时只依赖 PostgreSQL。
- 第三方 broker / result backend 会增加部署和状态一致性复杂度。
- 当前更需要透明的 JobRun/Step/Event，而不是高吞吐队列。

### 3.3 第一阶段不推荐重写成 Go

原因：

- 旧自动化逻辑迁移成本高。
- Python 生态更适合 Playwright/协议脚本复用。

## 4. 推荐版本组合

```text
Python: 3.12+
FastAPI: 0.115+
Pydantic: 2.x
SQLAlchemy: 2.x
Alembic: 1.13+
PostgreSQL: 16+
pytest: 8.x
Vue: 3.x
Vite: 5+
```

版本号是建议，不是强制；实际落地前应以当前依赖兼容性验证为准。
