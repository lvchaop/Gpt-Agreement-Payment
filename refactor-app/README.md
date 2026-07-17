# Refactor App

这是当前仓库里的独立重构项目目录。

目标：

- 按 `docs/schema/001_initial_schema.sql` 建模。
- 重新实现账号、Team Workspace、Membership、Batch、Codex Credential、Webshare、外部邮箱、Job、日志能力。
- 独立实现，不调用本目录外的业务代码。

目录结构和技术选型：

- `docs/09-project-structure-and-tech-stack.md`

运行环境：

```bash
../.venv/bin/python --version
```

本地重启：

```bash
./scripts/restart-dev.sh
```

脚本通过用户级 launchd 服务
`com.gpt-agreement-payment.refactor-dev` 重启并托管 Backend；运营页面由 Backend 的
`http://127.0.0.1:8000/ops/` 直接提供，不启动 `5173` Vite 服务。如果已安装
`com.gpt-agreement-payment.refactor-worker` launchd 服务，则由 launchd 重启并唯一
管理 Worker，避免重复 Worker 抢占 Job。

边界：

```text
runtime dependency:
  只允许本目录代码和第三方包。

design reference:
  可以阅读本项目内 docs/。

forbidden:
  不允许 import / 调用 / adapter 包装本目录外的业务代码。
```
