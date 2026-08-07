# Space 成员 OTP 分阶段提交

## 1. 目标

对运营选择的一个或多个 Space 下的有效账号执行两个人工 Job：

1. Prepare：完成已有账号登录前置、发送并读取邮箱 OTP、保存认证快照，不提交 OTP。
2. Remote Submit：创建一个本地 Work，将 `otp_collected` 快照交给服务器预热连接并同时
   提交 OTP。

Submit 完成后停止，不跟随 callback，不获取 ChatGPT Session。

## 2. 多 Space 账号筛选

Prepare 候选必须同时满足：

```text
spaces.id IN 运营选择的 space_ids
spaces.space_status = active
space_memberships.membership_status = active
user_accounts.account_status = active
user_accounts.email 非空
```

Space 只用于圈定候选账号，不是 OTP 快照或提交动作的归属。合并全部成员后必须先按
`user_account_id` 去重，再计算数量和创建 Work。同一账号同时存在于多个已选 Space 时，
只处理一次；按运营选择 Space 的顺序取第一条 membership 作为 Prepare 审计来源。

Submit 在同一成员范围内按 `user_account_id` 关联
`account_session_otp_snapshots`。Portal 使用的 Remote Submit 只选择 `otp_collected`；
保留的旧本地 Submit 接口兼容 `otp_collected` 和 `otp_pending`。

快照属于账号，不属于 Space 或 Prepare 批次。`source_membership_id` 只记录审计来源，
不得作为 Submit 候选过滤条件。

## 3. Prepare Job

```text
job_type = account.session_otp.prepare.bulk
work_type = account.session_otp.prepare
selected_count = account_count（已指定）或去重后有效账号数量（未指定）
work_count = 运营配置值，默认 50
```

运营可以额外传 `account_count` 限定本次处理的账号数量。指定时按既有候选顺序
精确选择前 N 个；留空时选择全部已选 Space 合并去重后的有效账号。
`account_count` 不得超过当前去重后的有效账号数量。

运营页面勾选成员时传 `user_account_ids`，优先于数量输入并精确处理勾选账号。
勾选账号必须至少属于一个已选 Space，且创建 Job 时仍在有效候选中。同一账号在页面
勾选多条 membership 时，提交参数和 Work 仍只有一个 `user_account_id`。

`work_count` 表示该 Job 最多同时运行的 Work 数。一个 Work 完成后，中央 Worker
继续领取下一个，直到所有成员处理完。

每个 Prepare Work：

1. 执行前再次确认审计来源 Space、membership、账号仍为 active。
2. 使用账号绑定代理；没有可用绑定时走既有账号代理分配逻辑。
3. 调用纯协议登录 Prepare 方法。
4. 发出 OTP 后最多查询邮箱验证码 2 次，不允许按超时时间持续无限轮询。
5. 两次内取到验证码写 `otp_collected`；仍未取到写 `otp_pending` 并立即结束 Work。
6. 保存 OTP、Cookie、认证环境和原始代理到账号快照。
7. 其他准备异常写 `failed`。
8. 不调用 OTP validate，不获取 Session。

## 4. 旧本地 Submit Job（保留）

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

1. 多选一个或多个 Space。
2. 查看合并并按账号去重后的有效账号数和可提交快照数。
3. 可选填写本次账号数；留空处理全部有效成员。
4. 配置 Prepare Work 数，默认 50。
5. 点击“预取 OTP”创建 Prepare Job。
6. 点击“服务器提交 OTP”，按当前 `otp_collected` 数量创建一个本地 Work；一次最多
   提交 1000 条，页面同时显示提交后剩余数量。
7. 创建后进入现有 Job 详情查看远端 `batch_id`、成功数、失败数和错误。

Job 输入同时保存 `space_ids` 和本次实际 `user_account_ids`。有活动 OTP Job 时按账号集合
判断冲突：存在相同账号才阻止新 Job；仅 Space 相同但账号集合不重叠时不阻止。

## 8. 验收

1. Prepare `work_count` 使用运营提交值，不固定为 50。
2. Prepare 有勾选账号时精确选择 `user_account_ids`；无勾选时才使用
   `account_count`，两者都没有时选择全部候选。
3. Prepare 只选择已选 Space 的 active membership + active account，并在创建 Work 前按
   `user_account_id` 去重。
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
14. Remote Submit 只选择 `otp_collected`，不得查询邮箱验证码接口。
15. Remote Submit 无论提交多少条，本地只创建一个 Work。
16. Portal 展示的本次提交数不得超过 1000，并展示本批完成后的剩余数量。
17. Remote Submit 只统计和提交实际保存了非空 `otp_code` 的快照；没有验证码的快照
    保持原状态，不发往服务器，也不记为提交失败。
18. 同一账号同时属于多个已选 Space 时，Prepare 和 Remote Submit 的候选数、Work 数、
    远端提交项都只能计一次。

## 9. 远端 Submit 桥接脚本

服务器执行器配置：

```text
INVITE_EXECUTOR_BASE_URL=http://43.162.85.160:31372
INVITE_EXECUTOR_API_KEY=<server API key>
```

按本地 `spaces.id` 提交：

```bash
cd /Users/chaopenglv/data/me/Gpt-Agreement-Payment/refactor-app
../.venv/bin/python scripts/submit_space_otp_remote.py <space_id>
```

桥接流程：

1. 只查询指定 Space 当前 active membership、active account 下状态为 `otp_collected`
   的快照；不选择 `otp_pending`。
2. 一次最多选择并提交 1000 条，超过部分保持 `otp_collected`，下次执行继续处理。
3. 请求项使用快照 ID 作为 `item_id`，并携带快照中的原始代理和完整认证快照。
4. 远端返回 `batch_id` 后脚本轮询到终态，再在一个事务中写回现有
   `account_session_otp_snapshots`。
5. 成功写 `otp_validated`；远端 `failed` 或 `skipped` 写 `failed`。
6. 写回前比较快照状态和 `updated_at`；轮询期间被重新 Prepare 或修改的快照不覆盖，
   计入 `stale_count`。
7. 不新增表，不修改账号 Session，也不继续获取 ChatGPT Session。

Portal 的“服务器提交 OTP”创建一个本地 Work。该 Work 携带 `space_ids` 和创建 Job 时
去重得到的 `user_account_ids` 调用上述桥接逻辑，
远端服务器负责最多 1000 条快照的连接预热、内存屏障和 OTP validate；完成后仍进入现有
Job 详情查看 `batch_id`、成功数、失败数和错误。旧的本地 Submit 接口保留，但 Portal
不再触发它。

只检查候选数量，不发请求、不写数据库：

```bash
../.venv/bin/python scripts/submit_space_otp_remote.py <space_id> --dry-run
```
