# 08. 架构决策记录

## ADR-001：V1 代理统一使用 Webshare

### 决策

V1 代理能力只支持 Webshare。

Webshare 能力必须按 Webshare 官方 API 文档重新实现，不参考旧项目里的 Webshare/gost/rotate 代码。

系统启动或定时任务先通过 Webshare 官方代理列表 API 拉取 IP 池，写入 `proxy_inventory`，再将 proxy 绑定到账号。

官方文档依据：

```text
Webshare API Docs:
https://apidocs.webshare.io/

List proxies:
GET https://proxy.webshare.io/api/v2/proxy/list/

Refresh proxy list:
POST https://proxy.webshare.io/api/v2/proxy/list/refresh/

Get proxy config:
GET https://proxy.webshare.io/api/v3/proxy/config?plan_id=<PLAN-ID>

Get proxy status:
GET https://proxy.webshare.io/api/v3/proxy/list/status?plan_id=<PLAN-ID>

Authentication header:
Authorization: Token <TOKEN>
```

### 规则

```text
1. 不支持 static proxy。
2. 不支持 trojan/hysteria/clash 等代理池。
3. 不支持每个 step 随机选择代理。
4. User Account 创建成功后必须绑定一个 proxy。
5. 注册、支付、token refresh、membership probe 默认使用账号绑定 proxy。
6. 只有 proxy healthcheck 失败或明确的 proxy repair job 才允许重新绑定。
7. Webshare 插件不允许调用旧项目的 WebshareClient、_rotate_webshare_ip、gost 或旧配置结构。
8. Webshare API client 只封装官方 HTTP API、官方字段和官方错误语义。
```

### 需要的能力

```text
ops.proxy.fetch_webshare_pool
ops.proxy.healthcheck
ops.proxy.bind_account
ops.proxy.refresh_webshare_pool
ops.proxy.repair_account_binding
```

### 数据模型

```text
proxy_inventory
user_account_proxy_bindings
```

### 官方字段映射

Webshare `Proxy object` 映射到 `proxy_inventory`：

```text
id                  -> external_proxy_id
username            -> proxy_username
password            -> proxy_password
proxy_address       -> proxy_host
port                -> proxy_port
valid               -> provider_valid
last_verification   -> last_provider_verification_at
country_code        -> country_code
city_name           -> city_name
```

`proxy_status` 是系统内部状态，由 `provider_valid`、绑定状态、健康检查结果派生，不直接等同于 Webshare `valid`。

Direct 连接模式：

```text
proxy_host = proxy_address
proxy_port = port
auth = username/password
```

Backbone 连接模式：

```text
proxy_host = p.webshare.io
proxy_port = one of Webshare-supported ports, or API-returned port when using IP Authorization
auth = username/password or source IP authorization
```

V1 默认使用 Direct + username/password。只有明确配置 `connection_mode=backbone` 时才使用 Backbone。

### API 约束

```text
1. 所有 Webshare API 请求必须带 Authorization: Token <TOKEN>。
2. list 接口按官方分页处理 page/page_size/next/results。
3. 遇到 HTTP 429 必须等待至少 60 秒后重试。
4. 拉取代理列表优先使用 JSON list API，不用 download token 文件接口作为主路径。
5. download token 只作为人工导出或批量校验辅助能力。
6. on-demand refresh 只能在有可用刷新次数时触发；刷新失败不能影响已有账号绑定。
7. provider 返回 valid=false 的 proxy 不分配给新账号。
```

### 原因

用户明确要求：

> 代理统一使用 webshar 就行，先拉取 ip 池，然后绑定到每个账号上。

这里按原文 `webshar` 理解为 Webshare。

用户后续明确要求：

> webshar的能力按照官方文档重新实现  不参考既有项目

## ADR-002：V1 邮箱统一使用外部邮箱接口

### 决策

V1 邮箱能力只支持 External Mail API。

本服务不维护邮箱基础设施。

### 本服务不负责

```text
邮箱账号库存
邮箱密码
IMAP
Cloudflare Email Worker
Cloudflare KV OTP
catch-all 域名
邮箱域名池
```

### 本服务只负责调用

```text
mailbox.allocate
mailbox.poll_otp
mailbox.mark_used
mailbox.mark_failed
mailbox.release
```

### 数据模型

```text
external_mail_leases
```

### 原因

用户明确要求：

> 邮箱统一使用外部邮箱接口，本服务不在维护。

这里按原意理解为“本服务不再维护邮箱账号、邮箱域名、IMAP/KV 等邮箱基础设施”。
