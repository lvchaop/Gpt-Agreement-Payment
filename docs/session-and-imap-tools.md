# Session 与 IMAP 工具说明

这个文档记录两个辅助脚本和 WebUI 批量邮箱筛选的用法，用来维护邮箱池和 ChatGPT session 库存。

## IMAP 邮箱探活脚本

脚本路径：

```bash
scripts/check_mail_accounts_imap.py
```

用途：

- 读取 WebUI SQLite 里的 `mail_accounts` 邮箱表。
- 通过 IMAP 登录测试邮箱是否还能正常收信。
- 把明确不可用的邮箱标坏，避免后续注册、补 session、收验证码时继续拿到坏邮箱。

默认写库策略：

- IMAP 登录成功：不改 `mail_accounts.status`。
- IMAP 登录失败：写入失败状态到 `mail_accounts.status`，把具体原因写入 `fail_reason`，并更新 `updated_at`。

失败状态含义：

- `imap_locked`：疑似邮箱被锁、安全挑战、异常活动、账号禁用，或需要网页登录确认。
- `imap_auth_failed`：密码、App Password、OAuth token 或 IMAP 认证失败。
- `imap_config_error`：本地配置缺失，比如缺密码、缺 token、缺 IMAP host、缺 client id。
- `imap_conn_error`：网络、DNS、SSL、超时、主机连接失败。
- `imap_failed`：其它未知 IMAP 失败。

常用命令：

```bash
# 先试跑，不写数据库。
.venv/bin/python scripts/check_mail_accounts_imap.py --dry-run --limit 20

# 正式探活，失败邮箱会写回 mail_accounts。
.venv/bin/python scripts/check_mail_accounts_imap.py --workers 8

# 只探活 unused 邮箱。
.venv/bin/python scripts/check_mail_accounts_imap.py --status unused --workers 8

# 重测已经被标成 IMAP 失败的邮箱。
.venv/bin/python scripts/check_mail_accounts_imap.py --include-bad --status imap_locked,imap_auth_failed

# 只探活单个邮箱。
.venv/bin/python scripts/check_mail_accounts_imap.py --email user@example.com --include-bad
```

注意：

- IMAP 探活能证明“这个邮箱凭据是否能登录 IMAP”。
- IMAP 不能 100% 区分“邮箱真的被锁”还是“密码错误、未开 IMAP、Basic Auth 被禁、需要安全验证”。
- 大批量执行前建议先加 `--dry-run` 看一下分类是否符合预期。

## Session 健康统计脚本

脚本路径：

```bash
scripts/report_session_health.py
```

用途：

- 统计 `registered_accounts` 里的账号 session 是否是正常形态。
- 输出正常账号数量和需要补 session 的账号数量。
- 可以导出需要补 session 的邮箱列表，方便粘到 WebUI 批量筛选框里再执行“选中补 session”。

正常 session 判定规则：

- `session_token` 有值。
- `access_token` 有值。
- `cookie_header` 里不重复包含 `__Secure-next-auth.session-token`。

需要补 session 的情况：

- 缺 `session_token`。
- 缺 `access_token`。
- `cookie_header` 里包含 `__Secure-next-auth.session-token`，说明 session-token 同时存在于独立字段和 cookie_header 里，属于重复旧形态。
- 其它不满足正常规则的情况。

常用命令：

```bash
# 输出总统计和样例。
.venv/bin/python scripts/report_session_health.py

# 只列出需要补 session 的账号。
.venv/bin/python scripts/report_session_health.py --only needs-session

# 只输出需要补 session 的邮箱，方便复制。
.venv/bin/python scripts/report_session_health.py --only needs-session --emails-only --limit 1000

# 只列出正常 session 账号。
.venv/bin/python scripts/report_session_health.py --only normal --emails-only --limit 1000

# 导出需要补 session 的账号到 CSV。
.venv/bin/python scripts/report_session_health.py --only needs-session --csv output/needs_session.csv

# 导出正常 session 账号到 CSV。
.venv/bin/python scripts/report_session_health.py --only normal --csv output/normal_session.csv
```

输出分类含义：

- `normal`：正常 session 形态。
- `cookie_header_duplicates_session_token`：`session_token/access_token` 都有，但 `cookie_header` 里重复塞了 session-token，需要补 session。
- `missing_session_and_access`：同时缺 `session_token` 和 `access_token`。
- `missing_session_token`：缺 `session_token`。
- `missing_access_token`：缺 `access_token`。
- `unknown`：脚本兜底分类，表示遇到未预期的字段形态。

## WebUI 批量邮箱筛选

位置：

- Run 页 -> 账号库存 -> 筛选区。

多行输入框名称：

```text
批量邮箱筛选，一行一个
```

用途：

- 把脚本导出的邮箱列表粘进去。
- WebUI 会只显示这些邮箱对应的账号。
- 然后可以直接点“全选筛选结果”，再执行“选中补 session / 选中补 RT / 删除选中”等操作。

支持输入：

```text
trecagle667398
trecagle667398@outlook.com
another@example.com
```

匹配规则：

- 推荐一行一个邮箱。
- 也支持空格、逗号、分号、中文逗号、中文分号分隔。
- 写完整邮箱时，按完整邮箱匹配。
- 只写邮箱前缀时，按 `@` 前面的 local-part 匹配。
- 批量邮箱筛选会和 plan、验证状态、支付状态、售卖状态、RT、CPA 等其它筛选条件叠加。
- 点击 `清除筛选` 会一起清空批量邮箱筛选框。
