# 06. 日志与可观测性规范

## 1. 当前问题证据

旧项目中存在：

- runner 内存环形日志：`webui/backend/runner.py`。
- auto-loop 扫描 tail log 进行错误分类：`webui/backend/auto_loop.py`。
- pipeline 多处直接 `print()`。
- 结果表有 `error TEXT`，但缺少稳定错误码、step、attempt、trace。

这些不是不能运行，而是难以复盘、难以稳定自动化。

## 2. 新日志目标

日志必须满足：

1. 可按 job/run/step 查询。
2. 可按 account/team_workspace/membership 查询。
3. 可按 error_code 聚合。
4. 可重放关键执行路径。
5. 不泄露敏感 token。
6. 人能读，机器也能读。

## 3. 日志格式

所有应用日志输出 JSON line。

基础字段：

```json
{
  "ts": "2026-06-19T13:30:00.000Z",
  "level": "INFO",
  "service": "worker",
  "event": "job.step.started",
  "message": "step started",
  "trace_id": "tr_xxx",
  "job_id": "job_xxx",
  "run_id": "run_xxx",
  "step_id": "step_xxx",
  "user_account_id": "acct_xxx",
  "team_workspace_id": "tw_xxx",
  "membership_id": "mem_xxx",
  "provider": "proxy.webshare",
  "data": {}
}
```

## 4. Job Event 规范

Job Event 是持久化日志，写入 `job_events`。

事件类型：

```text
job.created
job.queued
job.started
job.completed
job.failed
job.cancelled
job.retry_scheduled

job.step.started
job.step.completed
job.step.failed
job.step.skipped
job.step.retry_scheduled

provider.request.started
provider.request.completed
provider.request.failed

domain.state.changed
audit.action
```

## 5. 错误码规范

错误码必须稳定，不依赖错误文案。

格式：

```text
DOMAIN_REASON
```

示例：

```text
PROXY_DEAD
PROXY_QUOTA_EXHAUSTED
MAIL_OTP_TIMEOUT
AUTH_LOGIN_FAILED
AUTH_TOKEN_REFRESH_FAILED
PAYMENT_DECLINED
PAYMENT_PROVIDER_TIMEOUT
SPACE_NO_INVITE_PERMISSION
SPACE_SEAT_FULL
DOWNSTREAM_PUSH_FAILED
JOB_CANCELLED
UNKNOWN_ERROR
```

错误事件示例：

```json
{
  "event": "job.step.failed",
  "level": "ERROR",
  "error_code": "PROXY_QUOTA_EXHAUSTED",
  "retryable": false,
  "message": "proxy replacement quota exhausted",
  "data": {
    "provider": "proxy.webshare",
    "quota_available": 0
  }
}
```

## 6. 敏感信息规范

默认禁止输出：

- access token。
- refresh token。
- session token。
- cookie。
- password。
- API key。
- card number。
- proxy password。

可输出摘要：

```text
token_sha256_8
token_len
email
provider
last4
```

脱敏工具必须统一：

```python
redact(value, kind="token")
fingerprint(value)
```

禁止每个模块自己写一套 replace。

## 7. Metrics

建议指标：

```text
jobs_total{type,job_status}
job_duration_seconds{type}
job_step_duration_seconds{step,step_status}
provider_requests_total{provider,request_status}
provider_request_duration_seconds{provider}
user_accounts_total{account_status}
memberships_total{membership_status,invite_permission,seat_status,can_invite}
auth_token_refresh_total{token_status}
proxy_rotations_total{provider,rotation_status}
user_account_proxy_bindings_total{bind_status}
external_mail_leases_total{lease_status}
downstream_push_total{provider,push_status}
```

第一阶段可以先写入数据库和 JSON log，后续接 Prometheus。

## 8. Trace

每次 JobRun 生成 `trace_id`。

trace_id 必须传递到：

- workflow context。
- plugin context。
- provider request。
- job events。
- application logs。

## 9. 审计

人工操作必须写 audit event：

```text
account.delete
account.mark_sold
team_workspace.create
membership.force_probe
job.cancel
plugin.config.update
secret.rotate
```

审计字段：

```text
actor
action
target_type
target_id
before_json
after_json
reason
ts
```
