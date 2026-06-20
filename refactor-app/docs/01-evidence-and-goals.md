# 01. 现状证据与重构目标

## 1. 已求证的现状

### 1.1 账号模型不支持一个账号加入多个 Team Workspace 的授权维护

证据：

- `registered_accounts` 是账号行模型，字段直接挂载 `email/password/session_token/access_token/refresh_token/last_plan_type` 等账号状态，没有 Team Workspace 关系表。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/webui/backend/db.py`
- `card_results` 只有单个 `team_account_id`、`team_gpt_account_pk`、`invite_permission` 字段，说明当前结果记录只能表达一次 Team Workspace 探测，不支持一个账号对应多个 Team Workspace 的独立状态。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/webui/backend/db.py`
- inventory 逻辑通过 email 是否出现 `team_account_id` 推导是否 team，而不是查询账号-Team Workspace 关系。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/webui/backend/account_inventory.py`
- Team 配置中 `workspace_name` 是单值字段。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/CTF-reg/config.py`

结论：

当前模型本质是：

```text
registered_account(email) -> latest token/payment/team marker
```

目标模型应是：

```text
account -> identities
account -> tokens
account -> memberships[] -> team_workspace -> authorization state
```

### 1.2 代码结构混杂，核心流程与 provider、代理、运维耦合

证据：

- `pipeline.py` 同时负责注册、支付、gpt-team probe、CPA 导入、daemon、Webshare、gost、域名池、代理池。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/pipeline.py`
- `ProxyPool` 明确还是 stub，`mark_fail()` 未实现。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/pipeline.py`
- `proxy_bridge.py` 已有 `ProxyStagePlan`，说明阶段代理已经有局部抽象，但没有上升为统一插件和调度能力。  
  证据文件：`/Users/chaopenglv/data/me/Gpt-Agreement-Payment/proxy_bridge.py`

结论：

当前不是完全没有抽象，而是抽象散落；需要将 provider、proxy、workflow、ops job 分层。

### 1.3 没有持久化 Job 系统

证据：

- 没有发现 `jobs/job_runs/job_steps/job_events` 这类持久化任务表。
- `webui/backend/runner.py` 是单 active-run 子进程控制器，日志为内存环形列表 `_log_lines`。
- `webui/backend/auto_loop.py` 通过扫描 pipeline tail log 的 regex 分类错误。

结论：

当前有“运行器”和“自动循环”，但不是可审计、可恢复、可并发、可查询的 Job 系统。

### 1.4 自动运维能力存在，但不是平台化

证据：

- `pipeline.py::daemon()` 存在，目标是维护 gpt-team 可用账号数量。
- daemon 有限流、冷却、状态持久化。
- 有 Webshare IP 轮换、gost 探活、CF 死子域清理。
- `webui/backend/auto_loop.py` 有 auto-loop。

结论：

不能说“完全没有自动运维”。准确表述是：

> 自动运维能力散落在 `pipeline.py`、`auto_loop.py` 等位置，依赖硬编码流程和 stdout 日志，缺少统一 Job/Workflow/Plugin 平台。

## 2. 重构目标

### 2.1 产品目标

新系统需要支持：

1. 一个账号加入多个 Team Workspace。
2. 每个 Team Workspace membership 独立维护 `membership_status`、`invite_permission`、`seat_status`、`can_invite`，避免用一个模糊的 `status` 表达所有含义。
3. 自动化拉取、刷新、探测、推送、恢复。
4. 插件式接入不同 provider。
5. Workflow 可组装，不再把所有流程写死到一个 pipeline。
6. 运维过程可追踪、可审计、可复盘。

### 2.2 工程目标

1. 领域模型清晰。
2. 插件边界稳定。
3. Job 持久化。
4. 日志结构化。
5. 错误码稳定。
6. 测试覆盖核心状态机。
7. 迁移可分阶段完成，不需要一次重写所有旧逻辑。

## 3. 非目标

第一阶段不做：

1. 不直接重写 `card.py` 这种大型协议文件。
2. 不追求一次性替换所有旧功能。
3. 不把 WebUI 视觉重做作为核心目标。
4. 不为了“插件化”牺牲可调试性。
