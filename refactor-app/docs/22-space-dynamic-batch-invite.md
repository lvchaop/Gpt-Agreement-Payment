# 按本地席位批量邀请 Job

## 目标

新增一套独立于固定 1000 邀请的 Business 空间邀请流程：

- 固定 1000 邀请继续使用 `automation.space_membership_invite_sync` 和内存屏障。
- 按席位批量邀请使用 `automation.space_membership_invite_dynamic`。
- 新流程不查询远端成员，不使用内存屏障。
- 一个空间只生成一个 Work，一次请求提交本轮全部邮箱。

## 调度和 Work

```text
schedule_type = automation.space_membership_invite_dynamic
job_type = space.membership_invite_dynamic
work_type = space.membership_invite.dynamic_batch
work_count = 1
```

调度参数：

```text
space_id = 指定一个本地 active Business Space；留空选择更新时间最早的一个
```

同一时间只允许存在一个 queued/running 的动态邀请 Job。

## 本轮数量

本地席位额度来自扩席 Job 已写入的 `spaces.seats_entitled`。

本地占位数只统计当前空间下：

```text
membership_status IN (active, invited, accepted)
```

计算公式：

```text
remaining_seats = max(0, spaces.seats_entitled - occupied_membership_count)
requested_count = min(remaining_seats, eligible_account_count)
```

候选账号沿用固定邀请流程的条件，并使用数据库随机排序。

## 批量请求

一个 Work 只调用一次：

```http
POST /backend-api/accounts/{external_space_id}/invites
```

```json
{
  "email_addresses": ["a@example.com", "b@example.com"],
  "role": "standard-user",
  "seat_type": "default",
  "resend_emails": true
}
```

按席位批量邀请使用空间管理员绑定的静态住宅代理。固定 1000 邀请 Job
不选择或绑定代理，所有单邮箱邀请请求直接使用本机网络。

## 响应结算

HTTP 2xx 不是最终成功条件，必须按邮箱读取响应内容：

- 邮箱出现在 `account_invites`：membership 写为 `invited`。
- 邮箱出现在 `errored_emails`：不新增、不修改、不删除 membership。
- 请求邮箱未出现在任何结果数组：不新增、不修改、不删除 membership。
- 非超时 HTTP、代理或网络失败：不修改 membership，Work 失败。
- 请求超时：本批全部 membership 写为 `failed`，等待 30 秒后执行现有远端成员
  同步；同步命中的记录会改为 `active`，远端不存在的记录会被同步逻辑删除。

只要本批存在失败邮箱，批量 Work 标记为 failed；已经成功的 membership 保持 `invited`。
超时后的批量 Work 仍标记为 failed，远端同步只负责修正 membership 真值。

数据库 session 在 HTTP 请求前关闭，请求结束后重新打开 session 批量落库。
