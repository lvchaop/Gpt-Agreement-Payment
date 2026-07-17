# Business 空间倍增邀请并剔除 Job

## 目标

新增一套独立常驻 Job。每次执行只处理一个 Business Space、只完成一轮：

1. 读取远端订阅席位。
2. 一个批量邀请请求提交本轮全部邮箱。
3. 每个邀请成功账号重新获取 Session。
4. 以远端 `/users` 确认实际入组结果。
5. 无论本轮是全部还是部分账号实际入组，都从本轮确认入组账号中剔除 1 人。
6. 远端确认剔除成功并同步本地后，本轮 Job 完成；不在同一 Job 内继续下一轮。

现有固定 1000 邀请和按本地席位批量邀请保持不变。

## 类型与调度

```text
schedule_type = automation.space_membership_growth_round
job_type = space.membership_growth_round
work_type = space.membership_growth.invite_batch
work_type = space.membership_growth.session
work_type = space.membership_growth.finalize
```

调度参数：

```text
space_id = 必选，一个 active Business Space
work_count = 同时执行的 Work 数，默认 16，最大 16
session_wait_timeout_s = 等待本轮 Session Work 结束的最长时间，默认 900 秒
```

调度默认关闭。相同 Job 类型存在 `queued/running` Job 时不重复创建。

## 邀请数量

每轮现场调用远端订阅接口，读取：

```text
S = seats_entitled
U = seats_in_use
```

本轮数量：

```text
N = min(16, max(0, 2 * S - U), max(0, 999 - U), 可用账号数)
```

例如 `S=2, U=1` 时，本轮邀请 `3` 人。

候选账号沿用现有邀请候选规则并随机选择；目标 Space 现有本地成员、现有凭证、
远端 `/users` 成员和远端 pending invite 均不重复选择。

## Work 流程

### Invite Batch Work

管理员使用绑定的静态住宅代理调用：

```http
POST /backend-api/accounts/{external_space_id}/invites
```

请求只有一次：

```json
{
  "email_addresses": ["a@example.com", "b@example.com"],
  "role": "standard-user",
  "seat_type": "default",
  "resend_emails": true
}
```

邮箱出现在 `account_invites` 才进入 Session 阶段；`errored_emails` 和响应中缺失的
邮箱不进入。邀请超时后等待 30 秒，通过远端 `/users` 和 `/invites` 恢复实际成功集合。

### Session Work

每个邀请成功账号生成一个 Work，复用现有 `BackfillSessionWorkflow`：

- 使用账号自己的代理。
- 获取 Session 后调用 `accounts/check` 识别 Space。
- 单账号失败记录为 skipped，不阻断其他账号。

### Finalize Work

Finalize Work 等待本轮所有 Session Work 进入终态。等待轮询不持有数据库连接。

随后管理员通过静态住宅代理读取：

```http
GET /backend-api/accounts/{external_space_id}/users
```

只把本轮账号中实际出现在 `/users` 的账号视为入组成功：

- 确认数为 0：不剔人，Job 失败。
- 确认数大于 0：即使只是部分成功，也照常剔除 1 人。

剔除接口：

```http
DELETE /backend-api/accounts/{external_space_id}/users/{remote_user_id}
```

剔除对象从本轮远端确认入组账号中选择。DELETE 后重新读取 `/users`；目标仍存在则
Job 失败，不存在才视为成功。请求超时时同样以重新读取的远端结果为准。

最后调用现有远端成员同步，更新或物理删除目标 Space 下的本地 membership。本轮 Job
到此结束；下次调度重新读取远端席位并计算。

## 数据与状态

不新增业务表。使用现有：

- `automation_schedules`
- `jobs`
- `job_runs`
- `work_items`
- `job_events`
- `space_memberships`

邀请响应和本地 membership 状态不能代替最终判断；本轮实际入组和剔除结果均以远端
`/users` 为准。
