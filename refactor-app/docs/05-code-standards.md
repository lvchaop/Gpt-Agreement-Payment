# 05. 代码规范

## 1. 总原则

1. 代码先表达领域，再表达实现。
2. 不把流程、provider、日志、存储混在一个函数里。
3. 不依赖隐式全局状态。
4. 所有外部调用必须有 timeout、错误码、日志事件。
5. 所有 Job step 必须可追踪、可重试、可审计。

## 2. 目录规范

推荐，以 `09-project-structure-and-tech-stack.md` 的目录为准：

```text
src/
  refactor_app/
    api/
    cli/
    domain/
    application/
    ports/
    infrastructure/
    plugins/
      proxy_webshare/
      mail_external_api/
      downstream_cpa/
      downstream_sub2api/
      openai_chatgpt/
tests/
  unit/
  integration/
  contract/
  workflow/
```

## 3. 命名规范

### 3.1 领域对象

使用名词：

```text
UserAccount
TeamWorkspace
Membership
UserAccountAuth
Job
JobRun
JobStep
JobEvent
```

### 3.2 Workflow

使用动词短语：

```text
RegisterAccountWorkflow
PayAccountWorkflow
ProbeMembershipWorkflow
RefreshAuthorizationWorkflow
PushDownstreamWorkflow
```

### 3.3 Plugin

使用 provider + capability：

```text
WebshareProxyPlugin
ExternalMailApiPlugin
StripePaypalPaymentPlugin
CpaDownstreamPlugin
```

## 4. 接口规范

### 4.1 Plugin 接口

```python
class Plugin:
    name: str
    version: str
    capabilities: list[str]

    def validate_config(self, config: dict) -> ValidationResult:
        ...

    def healthcheck(self, ctx: PluginContext) -> HealthcheckResult:
        ...
```

执行型能力：

```python
class CapabilityHandler:
    capability: str

    def run(self, ctx: CapabilityContext, input: BaseModel) -> BaseModel:
        ...
```

### 4.2 Workflow 接口

```python
class Workflow:
    type: str

    def plan(self, input: BaseModel) -> list[StepSpec]:
        ...

    def run(self, ctx: WorkflowContext, input: BaseModel) -> BaseModel:
        ...
```

### 4.3 Repository 接口

Repository 只负责持久化，不放业务决策。

```python
class UserAccountRepository:
    def get(self, user_account_id: str) -> UserAccount:
        ...

    def save(self, user_account: UserAccount) -> None:
        ...
```

## 5. 错误处理规范

### 5.1 禁止裸字符串判断作为主流程

旧项目中 auto-loop 通过 tail regex 判断错误，这是旧系统证据，不应延续为新设计。

新系统必须使用稳定错误码：

```text
PROXY_DEAD
PROXY_QUOTA_EXHAUSTED
MAIL_OTP_TIMEOUT
AUTH_TOKEN_EXPIRED
PAYMENT_DECLINED
SPACE_NO_INVITE_PERMISSION
SPACE_SEAT_FULL
DOWNSTREAM_PUSH_FAILED
```

### 5.2 异常结构

```python
class AppError(Exception):
    code: str
    message: str
    retryable: bool
    details: dict
```

### 5.3 错误转换

Provider 内部异常必须转换成 AppError，不允许原样向上抛外部 SDK 异常。

## 6. 配置规范

### 6.1 配置不可直接作为运行状态

旧项目中 config 和 runtime state 混用较多。新项目中：

- config 描述静态意图。
- runtime state 存数据库。
- V1 是本地项目，账号 token 和代理密码直接存数据库字段，不引入 secret store。

### 6.2 配置必须有 schema

每个插件必须定义配置 schema：

```python
class WebshareProxyConfig(BaseModel):
    api_key_ref: str
    plan_id: str | None = None
    connection_mode: Literal["direct", "backbone"] = "direct"
    auth_mode: Literal["username_password", "sourceip"] = "username_password"
    page_size: int = 100
    default_scheme: Literal["http", "socks5"] = "http"
```

禁止在 Webshare 配置里引入旧项目字段，例如 `rotate_cooldown_s`、`lock_country`、`gost`、`proxy_url`。

Webshare 插件内部必须使用官方 endpoint 常量：

```python
WEBSHARE_API_BASE = "https://proxy.webshare.io/api"
PROXY_LIST_PATH = "/v2/proxy/list/"
PROXY_REFRESH_PATH = "/v2/proxy/list/refresh/"
PROXY_CONFIG_PATH = "/v3/proxy/config"
PROXY_STATUS_PATH = "/v3/proxy/list/status"
```

邮箱配置只允许外部邮箱接口：

```python
class ExternalMailApiConfig(BaseModel):
    base_url: str
    api_key_ref: str
    request_timeout_s: int = 10
    poll_interval_s: float = 3.0
    otp_timeout_s: int = 180
```

禁止新增 IMAP、Cloudflare KV、catch-all 域名相关配置。

## 7. 测试规范

### 7.1 Unit Test

覆盖：

- domain 状态转换。
- error classification。
- plugin config validation。
- workflow plan。

### 7.2 Contract Test

每个插件必须有 contract test：

```text
given valid config
when healthcheck
then result.health_status in ok/degraded/failed
```

### 7.3 Workflow Test

Workflow 使用 fake plugin registry 测试，不依赖真实外部服务。

### 7.4 Migration Test

每个数据库 migration 必须测试：

- 空库可迁移。
- 旧库可迁移。
- 重复执行安全。

## 8. 代码质量门槛

建议 CI 至少包含：

```text
ruff check
ruff format --check
mypy or pyright
pytest
alembic upgrade head on empty db
```

如果第一阶段不引入类型检查，也要保证：

- 所有 public interface 有类型标注。
- 所有 Pydantic schema 有字段说明。
- 所有 Job input/output 有 schema。
