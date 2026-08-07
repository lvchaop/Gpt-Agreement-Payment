from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

CredentialType = Literal["team_5h_weekly", "team_monthly"]


class AccountDeactivatedProvisioningError(RuntimeError):
    pass


class AuthorizationForbiddenProvisioningError(RuntimeError):
    pass


class ChatGPTAccountMissingProvisioningError(RuntimeError):
    pass


class SelectChannelProvisioningError(RuntimeError):
    def __init__(self, *, email: str, chatgpt_user_id: str) -> None:
        self.email = str(email or "").strip()
        self.chatgpt_user_id = str(chatgpt_user_id or "").strip()
        super().__init__(
            "Codex OAuth requires select-channel: "
            f"email={self.email} chatgpt_user_id={self.chatgpt_user_id}"
        )


class SpaceReplenishmentConfig(BaseModel):
    external_space_id: str = Field(min_length=1, max_length=200)
    name: str = Field(default="", max_length=320)
    enabled: bool = True
    credential_type: CredentialType
    seat_limit: int = Field(ge=1, le=1000)
    admin_key: str = Field(default="", max_length=320)
    admin_email: str = Field(default="", max_length=320)
    admin_user_id: str = Field(default="", max_length=200)
    admin_access_token: SecretStr = SecretStr("")
    admin_cookie_header: SecretStr = SecretStr("")
    admin_proxy_url: SecretStr = SecretStr("")

    @field_validator(
        "external_space_id",
        "name",
        "admin_key",
        "admin_email",
        "admin_user_id",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator(
        "admin_access_token",
        "admin_cookie_header",
        "admin_proxy_url",
        mode="before",
    )
    @classmethod
    def strip_secret(cls, value: object) -> str:
        if isinstance(value, SecretStr):
            return value.get_secret_value().strip()
        return str(value or "").strip()

    @model_validator(mode="after")
    def require_admin_authentication(self) -> SpaceReplenishmentConfig:
        if not (
            self.admin_access_token.get_secret_value()
            or self.admin_cookie_header.get_secret_value()
        ):
            raise ValueError("admin_access_token or admin_cookie_header is required")
        return self


class ReplenishmentRegistration(BaseModel):
    admin_key: str = Field(min_length=1, max_length=320)
    admin_email: str = Field(default="", max_length=320)
    admin_user_id: str = Field(default="", max_length=200)
    name: str = Field(default="", max_length=320)
    enabled: bool = True
    credential_type: CredentialType
    seat_limit: int = Field(ge=1, le=1000)
    admin_proxy_url: SecretStr = SecretStr("")

    @field_validator(
        "admin_key",
        "admin_email",
        "admin_user_id",
        "name",
        mode="before",
    )
    @classmethod
    def strip_registration_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("admin_proxy_url", mode="before")
    @classmethod
    def strip_registration_secret(cls, value: object) -> str:
        if isinstance(value, SecretStr):
            return value.get_secret_value().strip()
        return str(value or "").strip()


class ReplenishmentSpaceUpsertRequest(ReplenishmentRegistration):
    admin_access_token: SecretStr = SecretStr("")
    admin_cookie_header: SecretStr = SecretStr("")

    @field_validator("admin_access_token", "admin_cookie_header", mode="before")
    @classmethod
    def strip_upsert_secret(cls, value: object) -> str:
        if isinstance(value, SecretStr):
            return value.get_secret_value().strip()
        return str(value or "").strip()

    @model_validator(mode="after")
    def require_upsert_authentication(self) -> ReplenishmentSpaceUpsertRequest:
        if not (
            self.admin_access_token.get_secret_value()
            or self.admin_cookie_header.get_secret_value()
        ):
            raise ValueError("admin_access_token or admin_cookie_header is required")
        return self


@dataclass(frozen=True)
class RemoteMember:
    user_id: str
    email: str = ""
    role: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RemoteInvite:
    email: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpaceAdminContext:
    access_token: str
    cookie_header: str
    proxy_url: str
    admin_user_id: str = ""


@dataclass(frozen=True)
class SpaceRemoteSnapshot:
    external_space_id: str
    members: tuple[RemoteMember, ...]
    invites: tuple[RemoteInvite, ...]
    admin: SpaceAdminContext
    seat_limit: int


@dataclass(frozen=True)
class ProvisionedCodexCredential:
    email: str
    chatgpt_user_id: str
    external_space_id: str
    access_token: str
    id_token: str
    refresh_token: str
    client_id: str
    expires_at: datetime | None = None
    account_proxy_endpoint_id: str = ""


class SpaceCycleResult(BaseModel):
    external_space_id: str
    status: Literal["succeeded", "waiting", "skipped", "failed"]
    action: str = ""
    reason: str = ""
    member_count: int = 0
    non_admin_member_count: int = 0
    invite_count: int = 0
    downstream_account_count: int = 0
    seat_limit: int = 0
    new_email: str = ""
    new_chatgpt_user_id: str = ""
    replaced_chatgpt_user_id: str = ""
    downstream_account_id: int = 0
    removed_downstream_account_id: int = 0
    error_type: str = ""
    error_message: str = ""
    started_at: datetime
    finished_at: datetime


class SpaceRuntimeView(BaseModel):
    external_space_id: str
    name: str = ""
    enabled: bool
    credential_type: CredentialType
    seat_limit: int
    admin_key: str = ""
    admin_email: str = ""
    state: Literal["idle", "queued", "running"] = "idle"
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_result: SpaceCycleResult | None = None


class ReplenishmentRunView(BaseModel):
    accepted: bool
    external_space_id: str
    reason: str = ""
