from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/refactor_app"
    database_pool_size: int = 20
    database_max_overflow: int = 60
    database_pool_timeout_s: int = 60
    worker_capacity: int = 2000
    webshare_api_token: str = ""
    webshare_base_url: str = "https://proxy.webshare.io"
    webshare_download_url: str = ""
    openai_auth_base_url: str = "https://auth.openai.com"
    openai_chatgpt_base_url: str = "https://chatgpt.com"
    openai_probe_path_template: str = ""
    browser_impersonate: str = Field(default="chrome142", pattern=r"^chrome\d+[a-z]*$")
    browser_static_asset_cache_enabled: bool = False
    external_mail_api_base_url: str = ""
    external_mail_api_key: str = ""
    external_mail_provider_name: str = "cloudflare_temp_mail"
    hero_sms_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("HERO_SMS_API_KEY", "REFACTOR_APP_HERO_SMS_API_KEY"),
    )
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
    web_login_password: str = ""

    model_config = SettingsConfigDict(env_prefix="REFACTOR_APP_", env_file=".env")


def get_settings() -> Settings:
    return Settings()
