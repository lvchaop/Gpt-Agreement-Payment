from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, SecretStr, field_validator

from invite_executor.replenishment_models import ReplenishmentRegistration


class InviteBatchRequest(BaseModel):
    external_space_id: str = Field(min_length=1, max_length=200)
    access_token: SecretStr
    cookie_header: SecretStr = SecretStr("")
    emails: list[str] = Field(min_length=1, max_length=1000)
    barrier_timeout_s: float | None = Field(default=None, ge=1.0, le=300.0)
    replenishment: ReplenishmentRegistration | None = None

    @field_validator("external_space_id")
    @classmethod
    def strip_external_space_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("external_space_id is required")
        return normalized

    @field_validator("access_token", "cookie_header", mode="before")
    @classmethod
    def strip_secrets(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("access_token")
    @classmethod
    def require_access_token(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("access_token is required")
        return value

    @field_validator("emails")
    @classmethod
    def validate_emails(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in values:
            email = str(raw_value or "").strip()
            if not email or "@" not in email:
                raise ValueError(f"invalid email: {raw_value!r}")
            key = email.casefold()
            if key in seen:
                raise ValueError(f"duplicate email: {email}")
            seen.add(key)
            normalized.append(email)
        return normalized


class InviteResult(BaseModel):
    index: int
    email: str
    status: Literal["succeeded", "failed"]
    stage: Literal["proxy", "prepare", "prewarm", "barrier", "request"]
    proxy_slot: int = 0
    proxy_endpoint_id: str = ""
    http_status: int = 0
    ready_at: datetime
    request_started_at: datetime | None = None
    finished_at: datetime
    duration_ms: int = 0
    error_type: str = ""
    error_message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class InviteBatchSummary(BaseModel):
    target_count: int
    succeeded_count: int
    failed_count: int


class InviteBatchView(BaseModel):
    batch_id: str
    external_space_id: str
    status: Literal["queued", "running", "succeeded", "partial", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    connections_ready_at: datetime | None = None
    barrier_released_at: datetime | None = None
    finished_at: datetime | None = None
    prewarmed_connection_count: int = 0
    prewarm_rounds: int = 0
    prewarm_http_versions: list[int] = Field(default_factory=list)
    prewarm_unique_local_ports: int = 0
    reuse_validated_connection_count: int = 0
    opened_during_reuse_validation: int = 0
    summary: InviteBatchSummary
    results: list[InviteResult] = Field(default_factory=list)


class SessionOtpSubmitItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    proxy_url: SecretStr
    snapshot: dict[str, Any]

    @field_validator("item_id", "email")
    @classmethod
    def strip_item_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("invalid email")
        return value

    @field_validator("proxy_url", mode="before")
    @classmethod
    def strip_proxy_url(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("proxy_url")
    @classmethod
    def validate_proxy_url(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {"http", "https", "socks4", "socks5", "socks5h"}:
            raise ValueError("unsupported proxy URL scheme")
        if not parsed.hostname or parsed.port is None:
            raise ValueError("proxy URL must include host and port")
        return value

    @field_validator("snapshot")
    @classmethod
    def validate_snapshot(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("snapshot is required")
        return value


class SessionOtpBatchRequest(BaseModel):
    items: list[SessionOtpSubmitItem] = Field(min_length=1, max_length=1000)
    barrier_timeout_s: float | None = Field(default=None, ge=1.0, le=300.0)

    @field_validator("items")
    @classmethod
    def validate_unique_items(
        cls,
        values: list[SessionOtpSubmitItem],
    ) -> list[SessionOtpSubmitItem]:
        item_ids: set[str] = set()
        emails: set[str] = set()
        for item in values:
            if item.item_id in item_ids:
                raise ValueError(f"duplicate item_id: {item.item_id}")
            email_key = item.email.casefold()
            if email_key in emails:
                raise ValueError(f"duplicate email: {item.email}")
            item_ids.add(item.item_id)
            emails.add(email_key)
        return values


class SessionOtpResult(BaseModel):
    index: int
    item_id: str
    email: str
    status: Literal["succeeded", "failed", "skipped"]
    stage: Literal["prepare", "prewarm", "barrier", "request"]
    proxy_endpoint_id: str = ""
    http_status: int = 0
    ready_at: datetime
    request_started_at: datetime | None = None
    finished_at: datetime
    duration_ms: int = 0
    error_type: str = ""
    error_message: str = ""
    snapshot_patch: dict[str, Any] = Field(default_factory=dict)


class SessionOtpBatchSummary(BaseModel):
    target_count: int
    succeeded_count: int
    failed_count: int
    skipped_count: int


class SessionOtpBatchView(BaseModel):
    batch_id: str
    status: Literal["queued", "running", "succeeded", "partial", "failed"]
    created_at: datetime
    started_at: datetime | None = None
    connections_ready_at: datetime | None = None
    barrier_released_at: datetime | None = None
    finished_at: datetime | None = None
    prewarmed_connection_count: int = 0
    prewarm_rounds: int = 0
    prewarm_http_versions: list[int] = Field(default_factory=list)
    prewarm_unique_local_ports: int = 0
    reuse_validated_connection_count: int = 0
    opened_during_reuse_validation: int = 0
    summary: SessionOtpBatchSummary
    results: list[SessionOtpResult] = Field(default_factory=list)
