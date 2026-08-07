from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from invite_executor.replenishment_models import (
    SpaceReplenishmentConfig,
)


class InviteExecutorSettings(BaseSettings):
    api_key: str = ""
    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)
    max_batch_size: int = Field(default=1000, ge=1, le=1000)
    barrier_timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    invite_release_interval_ms: float = Field(default=1.0, ge=1.0, le=1000.0)
    session_otp_barrier_timeout_s: float = Field(default=120.0, ge=1.0, le=300.0)
    session_otp_release_window_s: float = Field(default=2.0, ge=0.0, le=60.0)
    request_timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    prewarm_rounds: int = Field(default=1, ge=1, le=5)
    prewarm_attempts: int = Field(default=10, ge=1, le=10)
    prewarm_start_interval_ms: float = Field(default=20.0, ge=0.0, le=1000.0)
    prewarm_keepalive_interval_s: float = Field(default=5.0, ge=0.1, le=60.0)
    prewarm_timeout_s: float = Field(default=5.0, ge=1.0, le=60.0)
    result_ttl_s: int = Field(default=3600, ge=60, le=86400)
    chatgpt_base_url: str = "https://chatgpt.com"
    static_proxy_gateway_host: str = "p.webshare.io"
    static_proxy_gateway_port: int = Field(default=80, ge=1, le=65535)
    static_proxy_username: str = ""
    static_proxy_password: str = ""
    static_proxy_country: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")
    invite_proxy_count: int = Field(default=1000, ge=1, le=1000)
    invites_per_proxy: int = Field(default=1, ge=1, le=1000)
    auto_replenish_enabled: bool = False
    auto_replenish_interval_s: float = Field(default=120.0, ge=10.0, le=86400.0)
    auto_replenish_max_workers: int = Field(default=20, ge=1, le=1000)
    auto_replenish_registry_path: str = "/data/replenishment-registry.json"
    auto_replenish_account_proxy_count: int = Field(default=1000, ge=1, le=1000)
    auto_replenish_account_proxy_country: str = Field(
        default="JP",
        pattern=r"^[A-Za-z]{2}$",
    )
    auto_replenish_usage_threshold_percent: float = Field(
        default=90.0,
        ge=1.0,
        le=100.0,
    )
    auto_replenish_usage_stale_after_s: int = Field(default=7200, ge=60, le=86400)
    auto_replenish_member_confirm_attempts: int = Field(default=3, ge=1, le=20)
    auto_replenish_member_confirm_interval_s: float = Field(
        default=2.0,
        ge=0.0,
        le=60.0,
    )
    auto_replenish_candidate_failure_cooldown_s: int = Field(
        default=600,
        ge=0,
        le=86400,
    )
    auto_replenish_browser_headless: bool = True
    auto_replenish_browser_otp_timeout_s: int = Field(default=180, ge=30, le=600)
    auto_replenish_codex_timeout_s: int = Field(default=240, ge=30, le=900)
    auto_replenish_grizzly_sms_api_key: str = ""
    auto_replenish_grizzly_sms_base_url: str = "https://api.grizzlysms.com/stubs/handler_api.php"
    auto_replenish_grizzly_sms_service: str = "dr"
    auto_replenish_grizzly_sms_country: str = "187"
    auto_replenish_grizzly_sms_max_price: str = "0.18"
    auto_replenish_grizzly_sms_max_number_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
    )
    auto_replenish_grizzly_sms_request_timeout_s: int = Field(
        default=20,
        ge=1,
        le=120,
    )
    auto_replenish_grizzly_sms_otp_timeout_s: int = Field(
        default=120,
        ge=30,
        le=600,
    )
    auto_replenish_grizzly_sms_poll_interval_s: float = Field(
        default=3.0,
        ge=0.1,
        le=60.0,
    )
    auto_replenish_sub2api_base_url: str = ""
    auto_replenish_sub2api_api_key: str = ""
    auto_replenish_sub2api_api_key_header: str = "x-api-key"
    auto_replenish_sub2api_group_id: int = Field(default=0, ge=0)
    auto_replenish_sub2api_group_ids: str = ""
    auto_replenish_sub2api_timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    auto_replenish_mail_base_url: str = ""
    auto_replenish_mail_api_key: str = ""
    auto_replenish_mail_api_key_header: str = "X-API-Key"
    auto_replenish_mail_provider_name: str = "outlook"
    auto_replenish_mail_timeout_s: float = Field(default=30.0, ge=1.0, le=300.0)
    auto_replenish_mail_poll_interval_s: float = Field(default=3.0, ge=0.1, le=60.0)
    log_level: str = "info"

    model_config = SettingsConfigDict(
        env_prefix="INVITE_EXECUTOR_",
        env_file=".env",
        extra="ignore",
    )

    def validate_auto_replenishment(self) -> tuple[SpaceReplenishmentConfig, ...]:
        if not self.auto_replenish_enabled:
            return ()
        required = {
            "INVITE_EXECUTOR_AUTO_REPLENISH_REGISTRY_PATH": (self.auto_replenish_registry_path),
            "INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_BASE_URL": (
                self.auto_replenish_sub2api_base_url
            ),
            "INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_API_KEY": (self.auto_replenish_sub2api_api_key),
            "INVITE_EXECUTOR_AUTO_REPLENISH_MAIL_BASE_URL": (self.auto_replenish_mail_base_url),
            "INVITE_EXECUTOR_AUTO_REPLENISH_MAIL_API_KEY": (self.auto_replenish_mail_api_key),
        }
        missing = [name for name, value in required.items() if not str(value or "").strip()]
        if self.auto_replenish_sub2api_group_id <= 0:
            missing.append("INVITE_EXECUTOR_AUTO_REPLENISH_SUB2API_GROUP_ID")
        if not self.static_proxy_gateway_host.strip():
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_GATEWAY_HOST")
        if not self.static_proxy_username.strip():
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_USERNAME")
        if not self.static_proxy_password:
            missing.append("INVITE_EXECUTOR_STATIC_PROXY_PASSWORD")
        if missing:
            raise ValueError(
                "auto replenishment configuration is incomplete: " + ", ".join(missing)
            )
        self.sub2api_push_group_ids()
        return ()

    def sub2api_push_group_ids(self) -> tuple[int, ...]:
        values = str(self.auto_replenish_sub2api_group_ids or "").strip()
        raw_items = values.replace(";", ",").split(",") if values else []
        group_ids: list[int] = []
        if self.auto_replenish_sub2api_group_id > 0:
            group_ids.append(int(self.auto_replenish_sub2api_group_id))
        for raw_item in raw_items:
            item = raw_item.strip()
            if not item:
                continue
            try:
                group_id = int(item)
            except ValueError as exc:
                raise ValueError(f"invalid Sub2API group ID: {item}") from exc
            if group_id <= 0:
                raise ValueError(f"Sub2API group ID must be positive: {item}")
            if group_id not in group_ids:
                group_ids.append(group_id)
        return tuple(group_ids)
