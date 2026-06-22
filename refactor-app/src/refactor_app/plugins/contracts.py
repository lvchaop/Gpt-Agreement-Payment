from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class HealthcheckResult:
    status: str
    message: str = ""
    details: dict = field(default_factory=dict)


class PluginContract(Protocol):
    name: str

    def validate_config(self) -> None: ...

    def healthcheck(self) -> HealthcheckResult: ...

    def capabilities(self) -> list[str]: ...


@dataclass(frozen=True)
class ProxyNode:
    provider: str
    external_proxy_id: str
    connection_mode: str
    proxy_host: str
    proxy_port: int
    proxy_scheme: str
    proxy_username: str = ""
    proxy_password: str = ""
    country_code: str = ""
    city_name: str = ""
    asn_name: str = ""
    provider_valid: bool = False
    last_provider_verification_at: datetime | None = None


class ProxyProvider(PluginContract, Protocol):
    def list_proxies(self) -> list[ProxyNode]: ...


@dataclass(frozen=True)
class MailLease:
    provider: str
    external_lease_id: str
    email: str


@dataclass(frozen=True)
class OtpMessage:
    code: str
    raw: dict = field(default_factory=dict)


class MailProvider(PluginContract, Protocol):
    def allocate_mailbox(self, *, purpose: str = "") -> MailLease: ...

    def poll_otp(self, *, external_lease_id: str, timeout_s: int) -> OtpMessage | None: ...

    def mark_used(self, *, external_lease_id: str) -> None: ...

    def mark_failed(
        self,
        *,
        external_lease_id: str,
        failure_code: str = "",
        failure_message: str = "",
    ) -> None: ...

    def release(self, *, external_lease_id: str, reason: str = "") -> None: ...


@dataclass(frozen=True)
class TokenClaims:
    token_chatgpt_account_id: str
    account_id: str = ""
    chatgpt_account_user_id: str = ""
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OAuthTokenSet:
    access_token: str
    id_token: str
    refresh_token: str
    expires_at: datetime | None
    claims: TokenClaims


class OpenAIChatGPTProvider(PluginContract, Protocol):
    def refresh_workspace_token(
        self,
        *,
        refresh_token: str,
        external_workspace_id: str,
        client_id: str,
    ) -> OAuthTokenSet: ...

    def decode_access_token(self, access_token: str) -> TokenClaims: ...

    def invite_member(
        self,
        *,
        access_token: str,
        team_id: str,
        email: str,
        cookie_header: str = "",
        seat_type: str = "default",
    ) -> dict: ...

    def accept_invite(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        device_id: str = "",
    ) -> dict: ...

    def probe_membership(self, *, access_token: str, team_id: str) -> dict: ...

    def heartbeat_codex_credential(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        model: str = "",
    ) -> dict: ...


@dataclass(frozen=True)
class DownstreamCodexPayload:
    access_token: str
    id_token: str
    refresh_token: str
    email: str
    account_id: str
    downstream_chatgpt_account_id: str
    token_chatgpt_account_id: str
    client_id: str
    expires_at: datetime | None
    plan_tag: str = ""
    plan_type: str = ""

    @property
    def chatgpt_user_id(self) -> str:
        return self.account_id


@dataclass(frozen=True)
class DownstreamPushResult:
    pushed: bool
    downstream_external_id: str = ""
    error_code: str = ""
    error_message: str = ""
    raw: dict = field(default_factory=dict)


class DownstreamProvider(PluginContract, Protocol):
    def push_codex_credential(self, payload: DownstreamCodexPayload) -> DownstreamPushResult: ...
