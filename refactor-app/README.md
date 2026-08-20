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

Cliproxy 账号静态代理：

```dotenv
CLIPROXY_MODE=remote
CLIPROXY_GATEWAY_MODE=auto
CLIPROXY_HOST=us.arxlabs.io
CLIPROXY_US_HOST=us.arxlabs.io
CLIPROXY_SG_HOST=sg.arxlabs.io
CLIPROXY_PORT=<控制台代理端口>
CLIPROXY_SCHEME=http
CLIPROXY_USERNAME=<基础用户名>
CLIPROXY_PASSWORD=<密码>
CLIPROXY_SESSION_DURATION_MINUTES=15
CLIPROXY_MAX_SID_ATTEMPTS=4
```

`auto` 模式在进程启动后的首次使用时直连 Cloudflare Trace 探测机器出口地区：
亚洲及大洋洲使用 `sg` 接入地址，欧洲及美洲使用 `us` 接入地址；结果在当前进程内
缓存，探测失败时回退 `CLIPROXY_HOST`。`fixed` 模式始终使用 `CLIPROXY_HOST`。

注册、iCloud 优惠检测、个人空间绑支付方式及 Checkout 共用该配置。首次按规范化
邮箱的 SHA-256 生成稳定 `sid`；使用前访问 ChatGPT CSRF 接口探测，失败后改用随机
UUID `sid`，直到达到 `CLIPROXY_MAX_SID_ATTEMPTS`。该链路不读取
`proxy_inventory`，也不回退旧 Webshare Backbone。

## Hero Gmail/Yandex 注册邮箱

账号注册页可选择 `hero_gmail` 或 `hero_yandex`。每个 Work 会从 Hero 的邮箱库存购买一个
新邮箱，使用返回的 email id 轮询 OpenAI 邮箱验证码；注册完成后继续执行与 iCloud 相同的
密码设置和 2FA 配置。Yandex 支持逗号、空格或分号分隔的多个后缀；留空时会从 Hero
`/emails/domains` 当前返回且有库存的 `yandex.*`/`ya.ru` 后缀中自动选择，不把某个后缀写死。
Hero 邮箱请求不会把 API key 写入 Job 输入。

```dotenv
HERO_EMAIL_API_KEY=<Hero email API key>
HERO_EMAIL_BASE_URL=https://hero-sms.com/api/v1
HERO_EMAIL_SITE=chatgpt.com
HERO_EMAIL_DOMAIN=gmail.com
# 可选；多个后缀用逗号、空格或分号分隔。留空则动态使用 Hero 当前库存。
HERO_EMAIL_YANDEX_DOMAINS=
HERO_EMAIL_REQUEST_TIMEOUT_S=30
HERO_EMAIL_POLL_INTERVAL_S=3
```

`HERO_EMAIL_API_KEY` 未设置时会复用 `HERO_SMS_API_KEY`，便于同一个 Hero 账号同时使用
短信和邮箱余额。2FA 仍使用现有 `TWOFAUTH_API_TOKEN` 配置。

## PayPal 协议授权

只有个人 PayPal 协议 OTP 使用 HeroSMS；账号注册、Codex 加手机号和其他短信流程继续使用
GrizzlySMS 配置。

个人空间的 PayPal 提链任务可以继续执行协议授权。协议模式使用 HeroSMS 的一天租号接收
PayPal OTP；每次从 Hero 返回的活跃 US/PayPal activation 中排除正在使用的租号后随机选择，
不会重新购号、完成或取消该租号。原有 `CLIPROXY_*` 代理凭据也仍然必需。

```dotenv
REFACTOR_APP_HERO_SMS_API_KEY=<HeroSMS API key>

REFACTOR_APP_PAYPAL_AGREEMENT_ENABLED=true
REFACTOR_APP_PAYPAL_AGREEMENT_COUNTRY=US
REFACTOR_APP_PAYPAL_AGREEMENT_PROXY_COUNTRY=US
REFACTOR_APP_PAYPAL_AGREEMENT_BUYER_MODE=identity_elevation
REFACTOR_APP_PAYPAL_AGREEMENT_SMS_SERVICE=ts
REFACTOR_APP_PAYPAL_AGREEMENT_SMS_COUNTRY=187
REFACTOR_APP_PAYPAL_AGREEMENT_OTP_TIMEOUT_S=180
REFACTOR_APP_PAYPAL_AGREEMENT_MAX_PHONE_ATTEMPTS=3
REFACTOR_APP_PAYPAL_AGREEMENT_MAX_CARD_ATTEMPTS=5
REFACTOR_APP_PAYPAL_AGREEMENT_FINALIZE_CHECKOUT=true
```

配置含义：

- `REFACTOR_APP_PAYPAL_AGREEMENT_ENABLED`：服务端协议执行总开关，默认开启。
- `REFACTOR_APP_PAYPAL_AGREEMENT_COUNTRY`：PayPal 买家资料国家，两位国家代码。
- `REFACTOR_APP_PAYPAL_AGREEMENT_PROXY_COUNTRY`：协议授权请求的出口代理国家，两位国家代码。
- `REFACTOR_APP_PAYPAL_AGREEMENT_BUYER_MODE`：买家资料模式，可选
  `identity_elevation` 或 `original`。
- `REFACTOR_APP_PAYPAL_AGREEMENT_SMS_SERVICE`：HeroSMS 服务代码，默认 `ts`。
- `REFACTOR_APP_PAYPAL_AGREEMENT_SMS_COUNTRY`：HeroSMS 数字国家编号；当前一天租号为美国
  `187`，必须与该租号匹配。
- `REFACTOR_APP_HERO_SMS_API_KEY`：HeroSMS API key。
- `REFACTOR_APP_PAYPAL_AGREEMENT_OTP_TIMEOUT_S`：等待 OTP 的秒数，范围 30-1800。
- `REFACTOR_APP_PAYPAL_AGREEMENT_MAX_PHONE_ATTEMPTS`：同一长租号码重发 OTP 的最大尝试次数，范围 1-10。
- `REFACTOR_APP_PAYPAL_AGREEMENT_MAX_CARD_ATTEMPTS`：卡片失败后的最大换卡次数，范围 1-20。
- `REFACTOR_APP_PAYPAL_AGREEMENT_FINALIZE_CHECKOUT`：授权成功后继续执行 Stripe poll、
  ChatGPT 校验和 Plus entitlement 校验，默认开启。

启用协议授权的任务必须显式提交 `agreement_country` 和
`agreement_proxy_country`，不会回退到全局代理。Portal 创建任务时会自动提交这两个字段。
Portal 的“执行 PayPal 协议授权”默认勾选，关闭后该任务只生成 PayPal 授权链接，不执行
协议授权和后续到账校验。完整流程为：

Portal 默认提交 US/US/187 的独立协议配置；账单国家、Checkout 代理和协议国家互不联动。

```text
PayPal 提链 -> PayPal 协议授权（自动取号和 OTP）
            -> Stripe Checkout poll -> ChatGPT 校验 -> Plus entitlement 校验
```

协议任务按任务参数 `agreement_proxy_country` 解析指定国家的 Cliproxy 代理，不读取
`PAYPAL_PROXY_URL`、`PAYPAL_PROXY_POOL` 或 `PAYPAL_PROXY_ENABLED` 这类全局 PayPal
代理配置。每个任务应显式选择国家代理；Checkout 使用该提链任务自己的
`checkout_proxy_country`，协议授权使用该任务自己的 `agreement_proxy_country`。
支付完成后的订阅同步若失败，后续重试只执行订阅同步，不会重新提链或支付。协议执行
完成后，Work/Event 诊断会隐藏已消费的 BA/EC token 和 Stripe client secret；关闭协议的
“仅提链”任务仍会在 Work 输出中返回完整授权链接。

可选配置本机卡号去重文件路径：

```dotenv
PAYPAL_AGREEMENT_CARD_HASH_FILE=runtime/paypal-agreement/used_local_card_hashes.txt
```

协议传输默认使用已安装的 `curl_cffi`。只有排查传输兼容性时才需要覆盖：

```dotenv
PAYPAL_HTTP_ENGINE=curl_cffi
PAYPAL_CURL_IMPERSONATE=chrome
```

本地 Trojan 池模式复用同一个解析入口，不再访问 Cliproxy 网关：

```dotenv
CLIPROXY_MODE=trojan_pool
CLIPROXY_TROJAN_POOL_FILE=runtime/proxy/trojan-pool.yaml
CLIPROXY_TROJAN_HTTP_START_PORT=18081
CLIPROXY_TROJAN_WORK_DIR=runtime/proxy/trojan-bridge
CLIPROXY_TROJAN_EXECUTABLE=sing-box
```

池文件支持老项目的 `COUNTRY trojan://...` 文本/JSON 格式，以及 Clash YAML 的
`proxies` 列表；Clash YAML 中暂时只加载 Trojan 与 Hysteria2，忽略其他协议。每个节点
由 `sing-box` 暴露为独立的本地 HTTP 端口，调用方按规范化邮箱和目标国家的 SHA-256
稳定选择节点，探测失败后按同一确定性顺序切换同国家节点。`trojan_pool` 模式不会读取
也不会回退远端 Cliproxy 的用户名、密码或网关。

边界：

```text
runtime dependency:
  只允许本目录代码和第三方包。

design reference:
  可以阅读本项目内 docs/。

forbidden:
  不允许 import / 调用 / adapter 包装本目录外的业务代码。
```
