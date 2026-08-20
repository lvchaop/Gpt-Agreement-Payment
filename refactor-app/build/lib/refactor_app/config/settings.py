from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/refactor_app"
    database_pool_size: int = 20
    database_max_overflow: int = 60
    database_pool_timeout_s: int = 60
    worker_capacity: int = 2000
    worker_lease_seconds: int = Field(default=120, ge=60, le=3600)
    worker_lease_requeue_interval_s: int = Field(default=15, ge=1, le=60)
    worker_shutdown_grace_s: float = Field(default=1.0, ge=0, le=30)
    worker_shutdown_handoff_delay_s: float = Field(default=1.0, ge=0.1, le=30)
    webshare_api_token: str = ""
    webshare_base_url: str = "https://proxy.webshare.io"
    webshare_download_url: str = ""
    openai_auth_base_url: str = "https://auth.openai.com"
    openai_chatgpt_base_url: str = "https://chatgpt.com"
    openai_probe_path_template: str = ""
    browser_impersonate: str = Field(default="chrome142", pattern=r"^chrome\d+[a-z]*$")
    browser_static_asset_cache_enabled: bool = True
    browser_log_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "BROWSER_LOG_ENABLED",
            "REFACTOR_APP_BROWSER_LOG_ENABLED",
        ),
    )
    browser_log_capture_bodies: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "BROWSER_LOG_CAPTURE_BODIES",
            "REFACTOR_APP_BROWSER_LOG_CAPTURE_BODIES",
        ),
    )
    browser_log_max_body_chars: int = Field(
        default=100_000,
        ge=1_000,
        le=100_000,
        validation_alias=AliasChoices(
            "BROWSER_LOG_MAX_BODY_CHARS",
            "REFACTOR_APP_BROWSER_LOG_MAX_BODY_CHARS",
        ),
    )
    external_mail_api_base_url: str = ""
    external_mail_api_key: str = ""
    external_mail_provider_name: str = "cloudflare_temp_mail"
    hero_sms_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("HERO_SMS_API_KEY", "REFACTOR_APP_HERO_SMS_API_KEY"),
    )
    hero_sms_base_url: str = "https://hero-sms.com/stubs/handler_api.php"
    hero_sms_request_timeout_s: int = Field(default=20, ge=1, le=120)
    hero_sms_poll_interval_s: float = Field(default=3.0, ge=0.1, le=60.0)
    grizzly_sms_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GRIZZLY_SMS_API_KEY",
            "REFACTOR_APP_GRIZZLY_SMS_API_KEY",
        ),
    )
    grizzly_sms_base_url: str = "https://api.grizzlysms.com/stubs/handler_api.php"
    grizzly_sms_service: str = "dr"
    grizzly_sms_country: str = Field(default="187", pattern=r"^[0-9]+$")
    grizzly_sms_max_price: str = "0.18"
    grizzly_sms_max_number_attempts: int = Field(default=3, ge=1, le=10)
    grizzly_sms_request_timeout_s: int = Field(default=20, ge=1, le=120)
    grizzly_sms_otp_timeout_s: int = Field(default=120, ge=30, le=600)
    grizzly_sms_poll_interval_s: float = Field(default=3.0, ge=0.1, le=60.0)
    twofauth_base_url: str = "https://daboluo2fa.zeabur.app"
    twofauth_api_token: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TWOFAUTH_API_TOKEN",
            "REFACTOR_APP_TWOFAUTH_API_TOKEN",
        ),
    )
    twofauth_api_token_file: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TWOFAUTH_API_TOKEN_FILE",
            "REFACTOR_APP_TWOFAUTH_API_TOKEN_FILE",
        ),
    )
    session_otp_executor_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "INVITE_EXECUTOR_BASE_URL",
            "REFACTOR_APP_SESSION_OTP_EXECUTOR_BASE_URL",
        ),
    )
    session_otp_executor_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "INVITE_EXECUTOR_API_KEY",
            "REFACTOR_APP_SESSION_OTP_EXECUTOR_API_KEY",
        ),
    )
    protocol_register_proxy_url: str = ""
    protocol_register_proxy_country: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")
    cliproxy_mode: str = Field(
        default="remote",
        pattern=r"^(?:remote|trojan_pool)$",
        validation_alias=AliasChoices(
            "CLIPROXY_MODE",
            "REFACTOR_APP_CLIPROXY_MODE",
        ),
    )
    cliproxy_trojan_pool_file: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices(
            "CLIPROXY_TROJAN_POOL_FILE",
            "REFACTOR_APP_CLIPROXY_TROJAN_POOL_FILE",
        ),
    )
    cliproxy_trojan_http_start_port: int = Field(
        default=18081,
        ge=1,
        le=65535,
        validation_alias=AliasChoices(
            "CLIPROXY_TROJAN_HTTP_START_PORT",
            "REFACTOR_APP_CLIPROXY_TROJAN_HTTP_START_PORT",
        ),
    )
    cliproxy_trojan_work_dir: str = Field(
        default="runtime/proxy/trojan-bridge",
        validation_alias=AliasChoices(
            "CLIPROXY_TROJAN_WORK_DIR",
            "REFACTOR_APP_CLIPROXY_TROJAN_WORK_DIR",
        ),
    )
    cliproxy_trojan_executable: str = Field(
        default="sing-box",
        validation_alias=AliasChoices(
            "CLIPROXY_TROJAN_EXECUTABLE",
            "REFACTOR_APP_CLIPROXY_TROJAN_EXECUTABLE",
        ),
    )
    cliproxy_trojan_start_timeout_s: float = Field(
        default=8.0,
        ge=1.0,
        le=60.0,
        validation_alias=AliasChoices(
            "CLIPROXY_TROJAN_START_TIMEOUT_S",
            "REFACTOR_APP_CLIPROXY_TROJAN_START_TIMEOUT_S",
        ),
    )
    cliproxy_gateway_mode: str = Field(
        default="auto",
        pattern=r"^(?:auto|fixed)$",
        validation_alias=AliasChoices(
            "CLIPROXY_GATEWAY_MODE",
            "REFACTOR_APP_CLIPROXY_GATEWAY_MODE",
        ),
    )
    cliproxy_host: str = Field(
        default="us.arxlabs.io",
        validation_alias=AliasChoices(
            "CLIPROXY_HOST",
            "REFACTOR_APP_CLIPROXY_HOST",
        ),
    )
    cliproxy_us_host: str = Field(
        default="us.arxlabs.io",
        validation_alias=AliasChoices(
            "CLIPROXY_US_HOST",
            "REFACTOR_APP_CLIPROXY_US_HOST",
        ),
    )
    cliproxy_sg_host: str = Field(
        default="sg.arxlabs.io",
        validation_alias=AliasChoices(
            "CLIPROXY_SG_HOST",
            "REFACTOR_APP_CLIPROXY_SG_HOST",
        ),
    )
    cliproxy_egress_trace_url: str = Field(
        default="https://www.cloudflare.com/cdn-cgi/trace",
        validation_alias=AliasChoices(
            "CLIPROXY_EGRESS_TRACE_URL",
            "REFACTOR_APP_CLIPROXY_EGRESS_TRACE_URL",
        ),
    )
    cliproxy_egress_trace_timeout_s: float = Field(
        default=5.0,
        ge=1.0,
        le=30.0,
        validation_alias=AliasChoices(
            "CLIPROXY_EGRESS_TRACE_TIMEOUT_S",
            "REFACTOR_APP_CLIPROXY_EGRESS_TRACE_TIMEOUT_S",
        ),
    )
    cliproxy_port: int = Field(
        default=0,
        ge=0,
        le=65535,
        validation_alias=AliasChoices(
            "CLIPROXY_PORT",
            "REFACTOR_APP_CLIPROXY_PORT",
        ),
    )
    cliproxy_scheme: str = Field(
        default="http",
        validation_alias=AliasChoices(
            "CLIPROXY_SCHEME",
            "REFACTOR_APP_CLIPROXY_SCHEME",
        ),
    )
    cliproxy_username: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices(
            "CLIPROXY_USERNAME",
            "REFACTOR_APP_CLIPROXY_USERNAME",
        ),
    )
    cliproxy_password: str = Field(
        default="",
        repr=False,
        validation_alias=AliasChoices(
            "CLIPROXY_PASSWORD",
            "REFACTOR_APP_CLIPROXY_PASSWORD",
        ),
    )
    cliproxy_state: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CLIPROXY_STATE",
            "REFACTOR_APP_CLIPROXY_STATE",
        ),
    )
    cliproxy_jp_state: str = Field(
        default="Tokyo",
        validation_alias=AliasChoices(
            "CLIPROXY_JP_STATE",
            "REFACTOR_APP_CLIPROXY_JP_STATE",
        ),
    )
    cliproxy_session_duration_minutes: int = Field(
        default=15,
        ge=1,
        le=120,
        validation_alias=AliasChoices(
            "CLIPROXY_SESSION_DURATION_MINUTES",
            "REFACTOR_APP_CLIPROXY_SESSION_DURATION_MINUTES",
        ),
    )
    cliproxy_probe_url: str = Field(
        default="https://chatgpt.com/api/auth/csrf",
        validation_alias=AliasChoices(
            "CLIPROXY_PROBE_URL",
            "REFACTOR_APP_CLIPROXY_PROBE_URL",
        ),
    )
    cliproxy_probe_timeout_s: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        validation_alias=AliasChoices(
            "CLIPROXY_PROBE_TIMEOUT_S",
            "REFACTOR_APP_CLIPROXY_PROBE_TIMEOUT_S",
        ),
    )
    cliproxy_probe_require_csrf_token: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "CLIPROXY_PROBE_REQUIRE_CSRF_TOKEN",
            "REFACTOR_APP_CLIPROXY_PROBE_REQUIRE_CSRF_TOKEN",
        ),
    )
    cliproxy_max_sid_attempts: int = Field(
        default=4,
        ge=1,
        le=20,
        validation_alias=AliasChoices(
            "CLIPROXY_MAX_SID_ATTEMPTS",
            "REFACTOR_APP_CLIPROXY_MAX_SID_ATTEMPTS",
        ),
    )
    personal_plus_checkout_create_proxy_country: str = Field(
        default="US",
        validation_alias="PERSONAL_PLUS_CHECKOUT_CREATE_PROXY_COUNTRY",
        pattern=r"^[A-Za-z]{2}$",
    )
    personal_plus_checkout_promo_proxy_country: str = Field(
        default="JP",
        validation_alias="PERSONAL_PLUS_CHECKOUT_PROMO_PROXY_COUNTRY",
        pattern=r"^[A-Za-z]{2}$",
    )
    personal_plus_checkout_promo_campaign_id: str = Field(
        default="plus-1-month-free",
        validation_alias="PERSONAL_PLUS_CHECKOUT_PROMO_CAMPAIGN_ID",
    )
    personal_plus_checkout_ui_mode: str = Field(
        default="hosted",
        validation_alias="PERSONAL_PLUS_CHECKOUT_UI_MODE",
        pattern=r"^(?:hosted|custom)$",
    )
    personal_payment_method_checkout_ui_mode: str = Field(
        default="custom",
        validation_alias="PERSONAL_PAYMENT_METHOD_CHECKOUT_UI_MODE",
        pattern=r"^(?:hosted|custom)$",
    )
    personal_plus_checkout_captcha_api_url: str = Field(
        default="",
        validation_alias="PERSONAL_PLUS_CHECKOUT_CAPTCHA_API_URL",
    )
    personal_plus_checkout_captcha_client_key: str = Field(
        default="",
        validation_alias="PERSONAL_PLUS_CHECKOUT_CAPTCHA_CLIENT_KEY",
    )
    personal_paypal_link_billing_country: str = Field(
        default="DE",
        validation_alias="PERSONAL_PAYPAL_LINK_BILLING_COUNTRY",
        pattern=r"^[A-Za-z]{2}$",
    )
    personal_paypal_link_proxy_country: str = Field(
        default="BR",
        validation_alias="PERSONAL_PAYPAL_LINK_PROXY_COUNTRY",
        pattern=r"^[A-Za-z]{2}$",
    )
    personal_paypal_link_currency: str = Field(
        default="EUR",
        validation_alias="PERSONAL_PAYPAL_LINK_CURRENCY",
        pattern=r"^[A-Za-z]{3}$",
    )
    personal_paypal_link_promo_campaign_id: str = Field(
        default="plus-1-month-free",
        validation_alias="PERSONAL_PAYPAL_LINK_PROMO_CAMPAIGN_ID",
    )
    personal_paypal_link_ui_mode: str = Field(
        default="hosted",
        validation_alias="PERSONAL_PAYPAL_LINK_UI_MODE",
        pattern=r"^(?:hosted|custom)$",
    )
    personal_paypal_agreement_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_ENABLED",
            "REFACTOR_APP_PAYPAL_AGREEMENT_ENABLED",
        ),
    )
    personal_paypal_agreement_country: str = Field(
        default="US",
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_COUNTRY",
            "REFACTOR_APP_PAYPAL_AGREEMENT_COUNTRY",
        ),
        pattern=r"^[A-Za-z]{2}$",
    )
    personal_paypal_agreement_proxy_country: str = Field(
        default="US",
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_PROXY_COUNTRY",
            "REFACTOR_APP_PAYPAL_AGREEMENT_PROXY_COUNTRY",
        ),
        pattern=r"^[A-Za-z]{2}$",
    )
    personal_paypal_agreement_buyer_mode: str = Field(
        default="identity_elevation",
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_BUYER_MODE",
            "REFACTOR_APP_PAYPAL_AGREEMENT_BUYER_MODE",
        ),
        pattern=r"^(?:identity_elevation|original)$",
    )
    personal_paypal_agreement_sms_service: str = Field(
        default="ts",
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_SMS_SERVICE",
            "REFACTOR_APP_PAYPAL_AGREEMENT_SMS_SERVICE",
        ),
        min_length=1,
    )
    personal_paypal_agreement_sms_country: str = Field(
        default="187",
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_SMS_COUNTRY",
            "REFACTOR_APP_PAYPAL_AGREEMENT_SMS_COUNTRY",
        ),
        pattern=r"^[0-9]+$",
    )
    personal_paypal_agreement_hero_lock_timeout_s: int = Field(
        default=1800,
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_HERO_LOCK_TIMEOUT_S",
            "REFACTOR_APP_PAYPAL_AGREEMENT_HERO_LOCK_TIMEOUT_S",
        ),
        ge=30,
        le=7200,
    )
    personal_paypal_agreement_sms_max_price: str = Field(
        default="0.18",
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_SMS_MAX_PRICE",
            "REFACTOR_APP_PAYPAL_AGREEMENT_SMS_MAX_PRICE",
        ),
    )
    personal_paypal_agreement_otp_timeout_s: int = Field(
        default=180,
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_OTP_TIMEOUT_S",
            "REFACTOR_APP_PAYPAL_AGREEMENT_OTP_TIMEOUT_S",
        ),
        ge=30,
        le=1800,
    )
    personal_paypal_agreement_max_phone_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_MAX_PHONE_ATTEMPTS",
            "REFACTOR_APP_PAYPAL_AGREEMENT_MAX_PHONE_ATTEMPTS",
        ),
        ge=1,
        le=10,
    )
    personal_paypal_agreement_max_card_attempts: int = Field(
        default=5,
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_MAX_CARD_ATTEMPTS",
            "REFACTOR_APP_PAYPAL_AGREEMENT_MAX_CARD_ATTEMPTS",
        ),
        ge=1,
        le=20,
    )
    personal_paypal_agreement_finalize_checkout: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "PERSONAL_PAYPAL_AGREEMENT_FINALIZE_CHECKOUT",
            "REFACTOR_APP_PAYPAL_AGREEMENT_FINALIZE_CHECKOUT",
        ),
    )
    icloud_post_registration_promotion_check_enabled: bool = Field(
        default=False,
        validation_alias="ICLOUD_POST_REGISTRATION_PROMOTION_CHECK_ENABLED",
    )
    web_login_password: str = ""

    model_config = SettingsConfigDict(env_prefix="REFACTOR_APP_", env_file=".env")


def get_settings() -> Settings:
    return Settings()
