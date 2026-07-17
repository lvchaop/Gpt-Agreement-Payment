# Job / Work 统一调度设计

状态：已实现  
生效方式：直接替换旧调度，不设过渡期，不保留旧执行分支

## 1. 唯一数量语义

所有 Job 只使用以下数量：

```text
selected_count = 本次业务规则最终选出的 Work 总数
work_count = 该 Job 同时处于 running 的 Work 上限
worker_capacity = 当前 Worker 进程可同时执行的 Job/Work 总上限
```

其中：

```text
selected_count 由各业务选择规则决定。
work_count 是运营可配置的 Job 参数。
worker_capacity 是部署参数，不是运营参数。
```

禁止再使用以下参数控制 Work 运行数量：

```text
concurrency
claim_limit
claim_batch_size
固定候选锁数量
```

业务 `limit` 可以保留，但只负责选择总量。例如回收 `limit=100` 只表示最多生成 100 条回收 Work，不表示同时运行 100 条。

## 2. Job 创建规则

每个业务对象生成一条 Work：

```text
注册 100 个账号 -> 100 条 account.protocol_register.one
邀请 1000 个账号 -> 1000 条 space.membership_invite.account
推送 50 条凭证 -> 50 条 space_credential.push.account
回收 80 条绑定 -> 80 条 space.recycle.binding
```

API、手动执行和长期调度只负责：

1. 按业务规则选择对象。
2. 创建 Job、JobRun 和全部 Work。
3. 提交事务并立即返回 Job ID。

API 和 Job handler 禁止启动自己的线程池，也禁止等待全部 Work 执行完成。

## 3. Work 领取规则

中央 Worker 每次按以下公式计算：

```text
job_free_slots = work_count - 当前 Job running 数
platform_free_slots = worker_capacity - 当前执行池占用数

claim_count = min(
  job_free_slots,
  platform_free_slots,
  当前 Job queued 数
)
```

领取事务：

1. `FOR UPDATE SKIP LOCKED` 锁定一个仍有空闲位置的 running Job。
2. 只锁定 `claim_count` 条 queued Work。
3. 将这些 Work 改为 running，写入 claimed_by、claimed_at 和 lease_expires_at。
4. 提交事务，立即释放数据库行锁。
5. 提交中央执行池调用业务 Work handler。

执行上游 HTTP 时不持有数据库行锁。

不存在固定扫描一批候选后只执行 1 条的流程。

## 4. 自动补位

```text
Work 完成 -> running 数减少 -> 重新计算空闲位置 -> 领取 queued Work 补位
```

示例：

```text
selected_count = 100
work_count = 5

首次只领取 5 条。
完成 1 条后只补 1 条。
整个 Job 始终最多 5 条 running，直到 100 条全部结束。
```

## 5. 资源互斥

`execution_key` 用于同一业务资源不能同时执行的场景，不改变 work_count 语义。

Business AT 授权：

```text
execution_key = space:{external_space_id}
```

同一个 Job 内，同一个 execution_key 最多存在一条 running Work。整个 Job 同时运行总数仍不能超过 work_count。

邀请、注册、推送和回收默认 execution_key 为空，不增加额外互斥限制。

## 6. 邀请规则

邀请仍保留业务规则：

```text
invite_limit_per_space = 1000
work_count = 1000
space_id = 可选目标 Business Space；留空自动选择
static_proxy_count = 50
invites_per_proxy = 20
```

候选账号达到 1000 个时，中央 Worker 领取并提交 1000 条邀请 Work。
所有邀请 Work 直接使用本机网络，并共用一个内存屏障。

邀请 barrier 只负责“同批 Work 到齐后同时发送 POST invites”，不再负责领取 Work 或创建额外线程池。

## 7. 执行租约

每条 running Work 都有 lease_expires_at：

1. 中央 Worker 每 30 秒续租正在执行的 Work。
2. 每 60 秒扫描一次过期租约。
3. Job 仍为 running 时，过期 Work 恢复为 queued，等待重新领取。
4. 已完成、失败或取消的 Work 清空租约。

租约扫描属于 Worker 内部恢复机制，不创建新的业务 Job。

## 8. 取消规则

取消 queued 或 running Job 时：

1. Job 立即改为 cancelled。
2. 全部 queued Work 改为 cancelled。
3. 不再领取或补位该 Job 的 Work。
4. 已经发出的上游请求允许返回，但不得把 Job 状态覆盖回 running、succeeded 或 failed。
5. JobRun 最终保持 cancelled。

## 9. Job 结束规则

```text
仍有 queued/running -> Job running
没有 queued/running 且存在 failed -> Job failed
没有 queued/running 且没有 failed -> Job succeeded
Job 已取消 -> Job/JobRun 始终 cancelled
```

## 10. 中央 Worker

Worker 使用一个调度循环和一个中央执行池：

```text
默认 worker_capacity = 2000
```

执行池按实际任务数创建线程，空闲时不会启动 500 个数据库轮询线程。

所有业务共用该执行池。禁止在注册、邀请、授权、推送、补 Session 和回收流程内再创建 ThreadPoolExecutor。

## 11. 已删除的旧规则

以下旧规则不再保留：

```text
JOB_SCOPED_CLAIM_LIMIT
按 work type 区分是否允许全局领取
普通 Work 每次锁一批候选后只执行 1 条
邀请专用批量领取线程池
注册 Job 内部 work_count 线程池
API 请求线程直接执行推送或补 Session Work
外层 Worker 数量乘以内层 Job 线程数
```
