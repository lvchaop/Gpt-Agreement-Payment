# Business 空间扩席位 Job

状态：已实现

## 固定业务规则

```text
目标席位 = 999
最小单次增加 = 1
最大单次增加 = 15
请求间隔 = 250ms
连续无进展上限 = 10 次
单个 HTTP 操作失败上限 = 10 次
```

下一档席位计算：

```text
increase = clamp(current_seats - 1, 1, 15)
next_seats = min(999, current_seats + increase)
```

示例：

```text
2 -> 3 -> 5 -> 9 -> 17 -> 32 -> 47 -> ... -> 999
```

## Job / Work

```text
调度类型：automation.space_seat_expand
Job 类型：space.seat_expand
Work 类型：space.seat_expand.one
```

一个 Business 空间生成一条 Work。`work_count` 只控制同时运行的空间 Work 数量；
单个空间内部按“查询、更新、验证”串行执行。

调度参数：

```text
space_id = 指定一个本地 Business Space ID；留空处理全部 active Business 空间
work_count = 同时处于 running 的 Work 上限
```

## 单空间流程

1. 读取 `spaces.source_admin_session_id` 对应的管理员登录态。
2. 获取或绑定该管理员的静态住宅代理。
3. 使用管理员 `access_token`、`cookie_header` 和 `spaces.external_space_id` 查询 subscription。
4. 根据远端 `seats_entitled` 计算下一档席位。
5. 提交 `POST /backend-api/subscriptions/update`，只发送 `account_id` 和 `updated_seats`。
6. 等待 250ms，再次查询 subscription；只有远端 `seats_entitled` 增长才算有进展。
7. 更新 `spaces.seats_entitled`、`seat_limit`、`seats_in_use` 和 subscription 快照。
8. 达到 999 后 Work 成功；连续 10 次无进展或某个 HTTP 操作连续失败 10 次后 Work 失败。
