# 项目重构设计文档

本文档集用于描述 `refactor-app/` 新项目的目标能力、技术选型、代码规范、日志规范、功能点和执行流程。

约束：

- 不在当前项目继续打补丁。
- `refactor-app/` 是独立新项目。
- 实施主线只按当前设计功能点和流程推进。
- 新项目以“能力平台”为核心，而不是围绕某一个脚本继续堆逻辑。
- 所有关键结论必须能从 `refactor-app/docs/`、`refactor-app/docs/schema/001_initial_schema.sql` 或已实现代码中找到依据；缺少依据时先补设计或补证据。

## 文档目录

| 文档 | 重点 |
| --- | --- |
| `00-glossary.md` | 术语表：User Account、Team Workspace、Membership、Provider、状态字段 |
| `01-evidence-and-goals.md` | 现状证据、痛点确认、重构目标 |
| `02-capability-model.md` | 新系统能力模型：账号、Team Workspace、授权、插件、工作流、Job |
| `03-architecture.md` | 目标架构、模块边界、数据模型、运行时边界 |
| `04-tech-selection.md` | 技术选型、推荐栈、备选方案和取舍 |
| `05-code-standards.md` | 代码规范、目录规范、接口规范、测试规范 |
| `06-logging-observability.md` | 日志、事件、错误码、审计、可观测性规范 |
| `08-architecture-decisions.md` | 架构决策：Webshare-only 代理、External Mail API-only 邮箱 |
| `09-project-structure-and-tech-stack.md` | 新项目目录结构、分层边界、技术选型落地规则 |
| `11-consistency-review.md` | 文档、ER、schema 一致性审查记录 |
| `12-implementation-plan.md` | 按当前设计功能点和流程组织的实施计划 |
| `14-local-postgres-bootstrap.md` | 本地 Docker PostgreSQL 建库、schema 导入和校验记录 |
| `15-ops-console-ui-design.md` | 当前 Ops Console 的页面结构和 UI 设计记录 |
| `16-portal-operations-redesign.md` | Portal 运营端最终形态：导航、页面职责、操作流和后端接口改造 |
| `17-space-auth-push-redesign.md` | Space 授权、推送、余额、用量、回收重构；目标态只有一套 Space 逻辑 |
| `schema/001_initial_schema.sql` | PostgreSQL 目标表结构 |
| `schema/ER.md` | ER 图、核心关系和约束说明 |

说明：

- 本目录不维护“老项目迁移路线”。
- 本目录不维护“老项目功能盘点”作为实施依据。
- 实施只按 `12-implementation-plan.md` 中定义的当前设计功能点和流程推进。
- Space 授权、推送、余额、用量、回收以 `17-space-auth-push-redesign.md` 为最新实施依据；该域没有旧逻辑并行、没有过渡期。

## 总体方向

新项目应从“脚本编排系统”重构为“插件化自动化运维平台”：

```text
User Account / Team Workspace / Authorization
        ↓
Capability Plugin
        ↓
Workflow
        ↓
Job / JobRun / Step / Event
        ↓
Structured Logs / Metrics / Audit
```

核心变化：

1. 从“单账号记录”改为“账号可加入多个 Team Workspace，并维护每个 membership 的授权状态”。
2. 从“硬编码流程”改为“Workflow 组装能力”。
3. 从“散落 provider / proxy / daemon”改为“插件能力注册与统一调度”。
4. 从“stdout + tail regex”改为“结构化事件、错误码、可追踪日志”。
5. 从“WebUI 单 active-run”改为“持久化 Job 系统”。
6. V1 代理统一使用 Webshare：先拉取 IP 池，再绑定到账号。
7. V1 邮箱统一使用外部邮箱接口：本服务不维护邮箱账号、IMAP、Cloudflare KV 或 catch-all 域名。
