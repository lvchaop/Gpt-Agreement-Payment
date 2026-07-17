# Space 成员 OTP 分阶段提交

## 1. 目标

对运营指定 Space 下的有效成员执行两个人工 Job：

1. Prepare：完成已有账号登录前置、发送并读取邮箱 OTP、保存认证快照，不提交 OTP。
2. Submit：按当前可提交快照数量一次启动全部 Work，一个内存屏障释放后同时提交 OTP。

Submit 完成后停止，不跟随 callback，不获取 ChatGPT Session。

## 2. Space 成员筛选

Prepare 候选必须同时满足：

```text
spaces.id = 运营指定 space_id
spaces.space_status = active
space_memberships.membership_status = active
user_accounts.account_status = active
user_accounts.email 非空
```

Submit 在同一成员范围内按 `user_account_id` 关联
`account_session_otp_snapshots`，只选择状态为 `otp_collected` 或
`otp_pending` 的可提交快照。

快照属于账号，不属于 Space 或 Prepare 批次。`source_membership_id` 只记录审计来源，
不得作为 Submit 候选过滤条件。

## 3. Prepare Job

```text
job_type = account.session_otp.prepare.bulk
work_type = account.session_otp.prepare
selected_count = account_count（已指定）或有效成员数量（未指定）
work_count = 运营配置值，默认 50
```

运营可以额外传 `account_count` 限定本次处理的账号数量。指定时按既有候选顺序
精确选择前 N 个；留空时保持原逻辑，选择该 Space 的全部有效成员。
`account_count` 不得超过当前有效成员数量。

运营页面勾选成员时传 `user_account_ids`，优先于数量输入并精确处理勾选账号。
勾选账号必须全部属于当前指定 Space，且创建 Job 时仍在有效候选中。

`work_count` 表示该 Job 最多同时运行的 Work 数。一个 Work 完成后，中央 Worker
继续领取下一个，直到所有成员处理完。

每个 Prepare Work：

1. 执行前再次确认 Space、membership、账号仍为 active。
2. 使用账号绑定代理；没有可用绑定时走既有账号代理分配逻辑。
3. 调用纯协议登录 Prepare 方法。
4. 发出 OTP 后最多查询邮箱验证码 2 次，不允许按超时时间持续无限轮询。
5. 两次内取到验证码写 `otp_collected`；仍未取到写 `otp_pending` 并立即结束 Work。
6. 保存 OTP、Cookie、认证环境和原始代理到账号快照。
7. 其他准备异常写 `failed`。
8. 不调用 OTP validate，不获取 Session。

## 4. Submit Job

```text
N = 指定 Space 有效成员中的可提交快照数量
job_type = account.session_otp.submit.bulk
work_type = account.session_otp.submit
selected_count = N
work_count = N
dispatch_mode = all_at_once
required_slots = N
barrier_expected = N
barrier_key = session-otp-submit:{job_id}
barrier_timeout_s = 120
```

Submit 不使用 Prepare 的 `work_count`，不按 50 分波次，也不创建多个屏障。
有 N 条可提交快照就一次启动 N 个 Work。

中央 Worker 容量必须大于等于 N。Submit 等待当前其他 Work 排空；实际空闲槽位达到
N 后，调度器在一个事务中领取全部 N 个 Work。空闲槽位不足时一个 Submit Work 都不
启动，也不能自动降级为分波次提交。

## 5. 屏障和跳过规则

每个 Submit Work 在等待屏障前完成数据库读取并关闭 Session，不得在屏障等待或网络
请求期间占用数据库连接。

```text
N = 创建的 Submit Work 数
M = 已恢复快照、可以提交的 ready Work
K = 准备失败、不能提交的 skipped Work
N = M + K
```

规则：

1. `otp_collected` Work 恢复原始认证环境和已有 OTP。
2. `otp_pending` Work 在屏障前只查询一次 Prepare 已发送的 OTP，不重新发码；取到后成为 ready，取不到成为 skipped。
3. ready Work 在真正调用 OTP validate 前向屏障报到。
4. 准备失败的 Work 以 skipped 身份向同一个屏障报到，但不发送 OTP validate。
5. arrived 达到 N 后屏障释放，M 个 ready Work 同时发送请求。
6. skipped Work 记录原因后结束，不阻断其他 Work。
7. 只有 Work 未启动、线程卡死或进程退出导致无法报到时，才由屏障超时终止。

## 6. 状态落库

复用现有 `account_session_otp_snapshots`，不新增表。

```text
source_membership_id = 最近一次 Prepare 的来源 membership
snapshot_status = otp_collected / otp_pending / otp_validated / otp_missing / failed
snapshot_json._space_id = Prepare 来源 Space，仅审计
snapshot_json._prepare_job_id = Prepare Job，仅审计
snapshot_json._prepare_work_id = Prepare Work，仅审计
snapshot_json._proxy_id = Prepare 使用的账号代理
```

Submit 必须继续使用快照里的原始代理。原始代理信息缺失或快照无法恢复时，该 Work
按 skipped 报到，不临时更换代理。

Work 最终状态：

```text
OTP validate 成功                         -> succeeded
快照不可用、屏障前准备失败、otp_missing   -> skipped
屏障释放后 OTP validate 请求失败          -> failed
```

`skipped` 是 `work_items.work_status` 的真实状态，并单独进入 Job 汇总和运营页面统计。

## 7. 运营入口

入口位于“空间成员”页面：

1. 选择 Space。
2. 查看有效成员数和可提交快照数。
3. 可选填写本次账号数；留空处理全部有效成员。
4. 配置 Prepare Work 数，默认 50。
5. 点击“预取 OTP”创建 Prepare Job。
6. 点击“同时提交 OTP”按可提交快照数创建 Submit Job。
7. 创建后进入现有 Job 详情查看每个 Work 的状态和错误。

同一个 Space 同时只允许一个 Prepare 或 Submit Job，避免重复提交同一批账号快照。

## 8. 验收

1. Prepare `work_count` 使用运营提交值，不固定为 50。
2. Prepare 有勾选账号时精确选择 `user_account_ids`；无勾选时才使用
   `account_count`，两者都没有时选择全部候选。
3. Prepare 只选择指定 Space 的 active membership + active account。
4. Submit 数量严格等于创建瞬间的可提交快照数 N。
5. 空闲槽位不足 N 时，不得领取任何 Submit Work；槽位达到 N 后必须一次领取 N 个。
6. N 个 Submit Work 的 `barrier_key`、`barrier_expected=N` 完全一致。
7. `otp_pending` 的补码和取码发生在屏障前，屏障后只允许 OTP validate。
8. Submit 不分波次。
9. 一个 Work 准备失败时只跳过自身，其他 ready Work仍可同时提交。
10. skipped 不得计入 succeeded。
11. Submit 不调用 ChatGPT Session 接口，不修改账号 Session 字段。
12. Prepare 邮箱验证码查询次数严格不超过 2 次；不得使用 180 秒无限轮询。
13. Submit 对 `otp_pending` 只查询一次邮箱验证码，未取到立即跳过该 Work。
