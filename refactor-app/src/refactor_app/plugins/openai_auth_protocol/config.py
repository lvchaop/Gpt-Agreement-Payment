"""
自动化绑卡支付 - 配置文件
"""
import os
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MailConfig:
    """邮箱服务配置。

    mode:
      - cloudflare_kv: Cloudflare Email Routing → otp-relay Worker → KV
      - imap_list: 从 SQLite 邮箱池读取真实 Gmail/Outlook/IMAP 账号
      - external_temp_mail: 外部邮箱管理 API；本地生成完整邮箱后调用 ensure，再读验证码

    KV 凭证（api_token / account_id / kv_namespace_id）放 SQLite runtime_meta[secrets]
    的 cloudflare 段或环境变量，不在 MailConfig 里。
    """
    mode: str = "cloudflare_kv"
    catch_all_domain: str = ""
    # 域名池：pipeline 运行时从中挑一个作为 catch_all_domain（轮换 + 根据 invite 探测结果烧掉）
    catch_all_domains: list = field(default_factory=list)
    # Cloudflare 按需开通子域；调用方按需读取。
    auto_provision: dict = field(default_factory=dict)
    otp_timeout: int = 180
    mark_seen: bool = False
    external_base_url: str = ""
    external_api_key: str = ""
    # 兼容外部接口文档字段名；优先 external_provider_name，空时使用 provider_name。
    provider_name: str = ""
    external_provider_name: str = "cloudflare_temp_mail"
    external_request_timeout_s: int = 5
    external_poll_interval_s: float = 3.0


@dataclass
class CardInfo:
    """信用卡信息"""
    number: str = ""
    cvc: str = ""
    exp_month: str = ""
    exp_year: str = ""


@dataclass
class BillingInfo:
    """账单信息"""
    name: str = "John Smith"
    email: str = ""
    country: str = "US"
    currency: str = "USD"
    address_line1: str = "123 Main St"
    address_line2: str = ""
    address_city: str = "San Francisco"
    address_state: str = "CA"
    postal_code: str = "94105"


@dataclass
class TeamPlanConfig:
    """团队/Plus 计划配置"""
    plan_name: str = "chatgptteamplan"
    workspace_name: str = "MyWorkspace"
    price_interval: str = "month"
    seat_quantity: int = 5
    promo_campaign_id: str = "team-1-month-free"
    is_coupon_from_query_param: bool = False
    checkout_ui_mode: str = "custom"
    output_url_mode: str = ""
    # 以下字段由外部配置向导写入；本配置对象需要兼容加载。
    plan_type: str = "team"           # team | plus
    entry_point: str = ""             # team_workspace_purchase_modal | all_plans_pricing_modal
    billing_country: str = ""
    billing_currency: str = ""


@dataclass
class CaptchaConfig:
    """验证码打码服务配置"""
    api_url: str = ""  # 兼容 createTask/getTaskResult 协议的打码平台 API base URL
    client_key: str = ""


@dataclass
class RegistrationConfig:
    """注册路径配置。method 为空时由 pipeline / WEBUI_REG_MODE 决定。"""
    method: str = ""  # browser | protocol | phone_browser | phone_protocol


@dataclass
class PhoneConfig:
    """手机号注册接口配置。

    provider=http 时，注册流程会在手机号输入框出现后调用 allocate_path 获取号码，
    提交手机号后轮询 otp_path 获取短信验证码。
    provider=hero_sms 时，base_url 指向 handler_api.php，service/country 会拼进
    getNumberV2/getStatusV2 请求。api_key 默认建议通过 api_key_env 注入。
    """
    enabled: bool = False
    provider: str = "http"
    base_url: str = ""
    api_key: str = ""
    api_key_env: str = "PHONE_PROVIDER_API_KEY"
    country: str = ""
    countries: list = field(default_factory=lambda: ["151", "73", "16"])
    service: str = "dr"
    maxPrice: str = "0.05"
    max_price: str = ""
    country_max_prices: dict = field(default_factory=dict)
    lease_ttl_s: int = 300
    max_number_attempts: int = 3
    request_timeout_s: int = 20
    allocate_path: str = "/api/phones/allocate"
    otp_path: str = "/api/phones/{lease_id}/otp"
    otp_method: str = "GET"
    otp_timeout_s: int = 120
    otp_poll_interval_s: float = 3.0
    cancel_retry_attempts: int = 4
    cancel_retry_interval_s: float = 5.0
    stale_cancel_after_s: int = 240
    watchdog_enabled: bool = True
    release_path: str = "/api/phones/{lease_id}/release"
    fail_path: str = "/api/phones/{lease_id}/fail"
    verified_path: str = "/api/phones/{lease_id}/verified"
    headers: dict = field(default_factory=dict)
    allocate_payload: dict = field(default_factory=dict)


@dataclass
class Config:
    """总配置"""
    registration: RegistrationConfig = field(default_factory=RegistrationConfig)
    mail: MailConfig = field(default_factory=MailConfig)
    card: CardInfo = field(default_factory=CardInfo)
    billing: BillingInfo = field(default_factory=BillingInfo)
    team_plan: TeamPlanConfig = field(default_factory=TeamPlanConfig)
    captcha: CaptchaConfig = field(default_factory=CaptchaConfig)
    phone: PhoneConfig = field(default_factory=PhoneConfig)
    proxy: Optional[str] = None
    proxy_meta: dict = field(default_factory=dict)
    auth_trace_dump_enabled: bool = False
    auth_trace_dump_path: str = ""
    auth_env_flags: dict = field(default_factory=dict)
    # 已有凭证（可选，跳过注册直接支付时使用）
    session_token: Optional[str] = None
    access_token: Optional[str] = None
    device_id: Optional[str] = None
    # Stripe
    stripe_build_hash: str = "f197c9c0f0"

    @classmethod
    def from_file(cls, path: str) -> "Config":
        """从 JSON 文件加载配置"""
        import dataclasses

        def filtered_kwargs(dataclass_type, raw: Optional[dict]) -> dict:
            # 外部配置来源会逐步增加字段；当前流程只消费其中一部分。
            # 加载时过滤未知 key，避免因为“注册阶段不用的支付字段”中断注册流程。
            valid_keys = {f.name for f in dataclasses.fields(dataclass_type)}
            return {k: v for k, v in (raw or {}).items() if k in valid_keys}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls()
        if "registration" in data:
            cfg.registration = RegistrationConfig(**filtered_kwargs(RegistrationConfig, data["registration"]))
        if "mail" in data:
            # 过滤已废弃的 IMAP/SMTP 字段（imap_server, imap_port, smtp_*,
            # email, auth_code），让旧 config 仍然能跑而不抛 unexpected
            # keyword 错。新代码请只配 catch_all_domain(s) + auto_provision。
            cfg.mail = MailConfig(**filtered_kwargs(MailConfig, data["mail"]))
        if "card" in data:
            cfg.card = CardInfo(**filtered_kwargs(CardInfo, data["card"]))
        if "billing" in data:
            cfg.billing = BillingInfo(**filtered_kwargs(BillingInfo, data["billing"]))
        if "team_plan" in data:
            cfg.team_plan = TeamPlanConfig(**filtered_kwargs(TeamPlanConfig, data["team_plan"]))
        if "captcha" in data:
            cfg.captcha = CaptchaConfig(**filtered_kwargs(CaptchaConfig, data["captcha"]))
        if "phone" in data:
            cfg.phone = PhoneConfig(**filtered_kwargs(PhoneConfig, data["phone"]))
        cfg.proxy = data.get("proxy")
        cfg.proxy_meta = data.get("proxy_meta") if isinstance(data.get("proxy_meta"), dict) else {}
        cfg.session_token = data.get("session_token")
        cfg.access_token = data.get("access_token")
        cfg.device_id = data.get("device_id")
        cfg.stripe_build_hash = data.get("stripe_build_hash", cfg.stripe_build_hash)
        return cfg

    def to_dict(self) -> dict:
        return {
            "registration": self.registration.__dict__,
            "mail": self.mail.__dict__,
            "card": self.card.__dict__,
            "billing": self.billing.__dict__,
            "team_plan": self.team_plan.__dict__,
            "captcha": self.captcha.__dict__,
            "phone": self.phone.__dict__,
            "proxy": self.proxy,
            "proxy_meta": self.proxy_meta,
            "session_token": self.session_token,
            "access_token": self.access_token,
            "device_id": self.device_id,
            "stripe_build_hash": self.stripe_build_hash,
        }
