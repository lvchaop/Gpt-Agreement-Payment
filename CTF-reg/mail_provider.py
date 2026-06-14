"""邮箱服务（CF Email Routing / IMAP account-list 路径）。

历史上这个模块走 IMAP 拉 QQ 邮箱接 OTP（5s 轮询 + 转发链路 30–90s 延迟）。
默认路径是 Cloudflare Email Worker → KV：

    寄件人 → CF MX (catch-all) → otp-relay Worker → KV
                                                       ↓
                                            cf_kv_otp_provider 读

OTP 提取由 Worker 端做（见 scripts/otp_email_worker.js），
也支持 `mail.mode=imap_list`：从 SQLite 邮箱池里取 Gmail/Outlook/自定义
IMAP 账号，用账号密码 / app password 登录邮箱读取验证码。

KV 凭证读取顺序：环境变量 `CF_API_TOKEN/CF_ACCOUNT_ID/CF_OTP_KV_NAMESPACE_ID`
→ SQLite runtime_meta[secrets] 的 cloudflare 段。详见 cf_kv_otp_provider.py。
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


# —— 真人风邮箱前缀生成 ——
# 与 browser_register._gen_name 保持同款英美常见名池；OpenAI 反欺诈系统对
# "随机字符串前缀"评分较低，用 first/last 组合更接近真实新用户分布。
_FIRST_NAMES = [
    "james", "john", "emily", "sophia", "michael", "oliver", "emma",
    "william", "amelia", "lucas", "mia", "ethan", "noah", "ava", "liam",
    "isabella", "mason", "charlotte", "logan", "harper", "elijah", "evelyn",
    "benjamin", "abigail", "jacob", "ella", "alexander", "scarlett", "henry",
    "grace", "daniel", "chloe", "matthew", "lily", "samuel", "zoe",
    "david", "hannah", "joseph", "aria", "ryan", "nora",
]
_LAST_NAMES = [
    "smith", "johnson", "williams", "brown", "jones", "garcia",
    "miller", "davis", "rodriguez", "martinez", "wilson", "anderson",
    "taylor", "thomas", "moore", "jackson", "martin", "lee", "walker",
    "hall", "allen", "young", "king", "wright", "scott", "green",
    "baker", "adams", "nelson", "carter",
]


def _humanlike_local_part(rng: random.Random | None = None) -> str:
    """生成像真人的邮箱前缀，例如 emma.davis、jsmith92、liam_wilson03。

    采样模式（权重）：
      - first.last                       (常见专业邮箱)
      - firstlast                        (无分隔)
      - first_last                       (下划线)
      - first.last + 1-2 位数字
      - firstlast + 2-4 位数字（含年份）
      - first 首字母 + last + 数字 (jsmith92)
      - first + last 首字母 + 数字 (emmas01)
      - first + 出生年（1985-2003）

    所有结果只含 [a-z0-9._]，长度 5-22，符合 RFC + 多数邮件服务的本地部要求。
    """
    r = rng or random
    first = r.choice(_FIRST_NAMES)
    last = r.choice(_LAST_NAMES)

    pattern = r.choices(
        population=[
            "first.last", "firstlast", "first_last",
            "first.last+num", "firstlast+num",
            "f.last+num", "first.l+num", "first+year",
        ],
        weights=[14, 10, 6, 18, 16, 14, 10, 12],
        k=1,
    )[0]

    if pattern == "first.last":
        local = f"{first}.{last}"
    elif pattern == "firstlast":
        local = f"{first}{last}"
    elif pattern == "first_last":
        local = f"{first}_{last}"
    elif pattern == "first.last+num":
        n = r.randint(1, 99)
        local = f"{first}.{last}{n:02d}"
    elif pattern == "firstlast+num":
        # 偏向 4 位年份样式（更像真人）
        if r.random() < 0.55:
            n = r.randint(1985, 2003)
            local = f"{first}{last}{n}"
        else:
            n = r.randint(1, 999)
            local = f"{first}{last}{n}"
    elif pattern == "f.last+num":
        n = r.randint(1, 99)
        local = f"{first[0]}{last}{n:02d}"
    elif pattern == "first.l+num":
        n = r.randint(1, 99)
        local = f"{first}{last[0]}{n:02d}"
    else:  # first+year
        n = r.randint(1985, 2003)
        local = f"{first}{n}"

    # 兜底长度（极个别长姓如 rodriguez+full year 会到 22）
    if len(local) > 22:
        local = local[:22]
    return local


class MailProvider:
    """生成 catch-all 子域随机邮箱 + 委托 CF KV provider 取 OTP。

    `last_persona` 暴露最近一次 `create_mailbox()` 产生的完整 persona
    （邮箱 / first / last / 密码），供 `browser_register` 复用，
    确保「邮箱 first-name 与注册显示姓名一致」——OpenAI 反欺诈系统
    会对二者不一致打负分。
    """

    def __init__(
        self,
        catch_all_domain: str = "",
        *,
        mode: str = "cloudflare_kv",
        otp_timeout: int = 180,
        mark_seen: bool = False,
        external_base_url: str = "",
        external_api_key: str = "",
        external_provider_name: str = "cloudflare_temp_mail",
        external_request_timeout_s: int = 20,
        external_poll_interval_s: float = 3.0,
    ):
        self.mode = (mode or "cloudflare_kv").strip().lower()
        self.catch_all_domain = catch_all_domain
        self.otp_timeout = otp_timeout
        self.mark_seen = mark_seen
        self.external_base_url = external_base_url
        self.external_api_key = external_api_key
        self.external_provider_name = external_provider_name or "cloudflare_temp_mail"
        self.external_request_timeout_s = int(external_request_timeout_s or 20)
        self.external_poll_interval_s = float(external_poll_interval_s or 3.0)
        self._external_provider = None
        self._reuse_email: Optional[str] = None  # 兼容 register-only resume
        self._reserved_account = None
        self._pool = None
        # 算法化 persona 生成器（音节合成法，详见 persona.py）
        from persona import PersonaGenerator, Persona
        self._persona_gen = PersonaGenerator(catch_all_domain)
        self.last_persona: Optional[Persona] = None

    @classmethod
    def from_config(cls, mail_cfg, config_path: str = "") -> "MailProvider":
        mode = (getattr(mail_cfg, "mode", "") or "cloudflare_kv").strip().lower()
        return cls(
            getattr(mail_cfg, "catch_all_domain", "") or "",
            mode=mode,
            otp_timeout=int(getattr(mail_cfg, "otp_timeout", 180) or 180),
            mark_seen=bool(getattr(mail_cfg, "mark_seen", False)),
            external_base_url=getattr(mail_cfg, "external_base_url", "") or "",
            external_api_key=getattr(mail_cfg, "external_api_key", "") or "",
            external_provider_name=(
                getattr(mail_cfg, "external_provider_name", "")
                or getattr(mail_cfg, "provider_name", "")
                or "cloudflare_temp_mail"
            ),
            external_request_timeout_s=int(getattr(mail_cfg, "external_request_timeout_s", 20) or 20),
            external_poll_interval_s=float(getattr(mail_cfg, "external_poll_interval_s", 3.0) or 3.0),
        )

    @staticmethod
    def _random_name() -> str:
        # 保留旧 API 兼容；新流程走 persona generator
        return _humanlike_local_part()

    def create_mailbox(self) -> str:
        """生成 random@catch_all 邮箱地址（也可复用 _reuse_email）。

        同时将算法生成的完整 persona 缓存到 `self.last_persona`，
        `browser_register` 通过该字段读取与邮箱同源的姓名 / 密码。
        """
        if self._reuse_email:
            addr = self._reuse_email
            self._reuse_email = None
            logger.info(f"复用邮箱: {addr}")
            self.last_persona = None  # resume 路径无法回推 first/last
            if self.mode == "external_temp_mail":
                self._external_mail_provider().ensure_email(addr)
            return addr
        if self.mode == "imap_list":
            account = self._email_pool().reserve_next()
            self._reserved_account = account
            self.last_persona = account.to_persona()
            logger.info(
                f"邮箱池取号: {account.email} | provider={account.provider} "
                f"(路径: IMAP account list)"
            )
            return account.email
        if not self.catch_all_domain:
            raise RuntimeError(
                "MailProvider.create_mailbox: catch_all_domain 未配置；"
                "CF Email Worker 路径需要 catch-all 子域（在 zone 内）"
            )
        persona = self._persona_gen.next()
        self.last_persona = persona
        if self.mode == "external_temp_mail":
            self._external_mail_provider().ensure_email(persona.email)
            logger.info(
                f"邮箱已创建: {persona.email} | persona={persona.first} {persona.last} "
                f"(路径: External temp mail API ensure)"
            )
            return persona.email
        logger.info(
            f"邮箱已创建: {persona.email} | persona={persona.first} {persona.last} "
            f"(路径: CF Email Worker → KV)"
        )
        return persona.email

    def wait_for_otp(
        self,
        email_addr: str,
        timeout: int = 120,
        issued_after: Optional[float] = None,
    ) -> str:
        """阻塞等 OTP。所有模式最终统一从 CF KV 读取。

        - cloudflare_kv: CF Email Worker 写 KV，本地轮询 KV。
        - external_temp_mail: 外部邮箱管理 API 读取验证码。
        - imap_list: 只对当前 reserved 活跃邮箱启动本地 relay，relay 写 KV，
          本地仍轮询 KV。
        """
        if self.mode == "external_temp_mail":
            logger.info(
                f"[mail] 走 External temp mail API 取 OTP -> {email_addr} "
                f"(timeout={timeout}s)"
            )
            return self._external_mail_provider().wait_for_otp(
                email_addr,
                timeout=timeout,
                issued_after=issued_after,
            )

        from cf_kv_otp_provider import CloudflareKVOtpProvider

        kv_provider = CloudflareKVOtpProvider.from_env_or_secrets()

        if self.mode == "imap_list":
            from mailbox_relay import MailboxRelay

            account = self._reserved_account or self._email_pool().find(email_addr)
            if account is None:
                raise RuntimeError(f"邮箱池找不到账号: {email_addr}")
            effective_timeout = int(timeout or self.otp_timeout or 180)
            logger.info(
                f"[mail] IMAP relay → CF KV → wait KV -> {email_addr} "
                f"provider={account.provider} timeout={effective_timeout}s"
            )

            relay = MailboxRelay(kv_provider, mark_seen=self.mark_seen)
            relay_state: dict = {"done": False, "error": None}

            def _run_relay() -> None:
                try:
                    relay.relay_until_otp(
                        account,
                        email_addr,
                        timeout=effective_timeout,
                        issued_after=issued_after,
                    )
                    relay_state["done"] = True
                except Exception as e:
                    relay_state["error"] = e

            thread = threading.Thread(
                target=_run_relay,
                name=f"mailbox-relay-{email_addr}",
                daemon=True,
            )
            thread.start()

            deadline = time.time() + effective_timeout
            last_timeout: Exception | None = None
            while time.time() < deadline:
                if relay_state["error"] is not None:
                    raise RuntimeError(
                        f"MailboxRelay 写 KV 失败 email={email_addr}: "
                        f"{relay_state['error']}"
                    ) from relay_state["error"]
                remaining = max(1, int(deadline - time.time()))
                chunk = min(5, remaining)
                try:
                    return kv_provider.wait_for_otp(
                        email_addr,
                        timeout=chunk,
                        issued_after=issued_after,
                    )
                except TimeoutError as e:
                    last_timeout = e
                    continue

            if relay_state["error"] is not None:
                raise RuntimeError(
                    f"MailboxRelay 写 KV 失败 email={email_addr}: "
                    f"{relay_state['error']}"
                ) from relay_state["error"]
            suffix = f": {last_timeout}" if last_timeout else ""
            raise TimeoutError(
                f"IMAP relay 已启动但统一 KV 等 OTP 超时 "
                f"{effective_timeout}s email={email_addr}{suffix}"
            )

        logger.info(
            f"[mail] 走 CF KV 取 OTP -> {email_addr} (timeout={timeout}s)"
        )
        return kv_provider.wait_for_otp(
            email_addr, timeout=timeout, issued_after=issued_after
        )

    def mark_used(self, email_addr: str) -> None:
        if self.mode == "imap_list":
            self._email_pool().mark(email_addr, "used")

    def mark_failed(self, email_addr: str, reason: str = "") -> None:
        if self.mode == "imap_list":
            self._email_pool().mark(email_addr, "failed", reason[:200])

    def mark_unused(self, email_addr: str) -> None:
        if self.mode == "imap_list":
            self._email_pool().mark(email_addr, "unused")

    def _email_pool(self):
        if self._pool is None:
            from email_account_pool import email_account_pool_from_path

            self._pool = email_account_pool_from_path()
        return self._pool

    def _external_mail_provider(self):
        if self._external_provider is None:
            from external_mail_api_provider import ExternalMailApiProvider

            self._external_provider = ExternalMailApiProvider(
                self.external_base_url,
                self.external_api_key,
                provider_name=self.external_provider_name,
                request_timeout_s=self.external_request_timeout_s,
                poll_interval_s=self.external_poll_interval_s,
            )
        return self._external_provider
