from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/refactor_app"
    database_pool_size: int = 20
    database_max_overflow: int = 60
    database_pool_timeout_s: int = 60
    worker_max_concurrency: int = 500
    webshare_api_token: str = ""
    webshare_base_url: str = "https://proxy.webshare.io"
    webshare_download_url: str = ""
    openai_auth_base_url: str = "https://auth.openai.com"
    openai_chatgpt_base_url: str = "https://chatgpt.com"
    openai_probe_path_template: str = ""
    external_mail_api_base_url: str = ""
    external_mail_api_key: str = ""
    external_mail_provider_name: str = "cloudflare_temp_mail"
    protocol_register_proxy_url: str = ""
    web_login_password: str = ""

    model_config = SettingsConfigDict(env_prefix="REFACTOR_APP_", env_file=".env")


def get_settings() -> Settings:
    return Settings()
