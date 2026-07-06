from __future__ import annotations

from refactor_app.plugins.contracts import HealthcheckResult, OAuthTokenSet, TokenClaims
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTClient,
    OpenAIChatGPTClientConfig,
)


class OpenAIChatGPTPlugin:
    name = "openai_chatgpt"

    def __init__(self, client: OpenAIChatGPTClient) -> None:
        self._client = client

    @classmethod
    def from_config(cls, config: OpenAIChatGPTClientConfig) -> OpenAIChatGPTPlugin:
        return cls(OpenAIChatGPTClient(config))

    def validate_config(self) -> None:
        return None

    def healthcheck(self) -> HealthcheckResult:
        return HealthcheckResult(status="ok", details={"provider": "openai_chatgpt"})

    def capabilities(self) -> list[str]:
        return [
            "openai_chatgpt.oauth.refresh_workspace_token",
            "openai_chatgpt.jwt.decode_access_token",
            "openai_chatgpt.team_workspace.invite_member",
            "openai_chatgpt.team_workspace.subscription",
            "openai_chatgpt.team_workspace.users.list",
            "openai_chatgpt.team_workspace.invites.list",
            "openai_chatgpt.team_workspace.accept_invite",
            "openai_chatgpt.team_workspace.probe_membership",
            "openai_chatgpt.codex.heartbeat",
            "openai_chatgpt.codex.responses_usage_probe",
            "openai_chatgpt.wham.usage",
            "openai_chatgpt.wham.auth_credentials.create",
        ]

    def refresh_workspace_token(
        self,
        *,
        refresh_token: str,
        external_workspace_id: str,
        client_id: str,
    ) -> OAuthTokenSet:
        return self._client.refresh_workspace_token(
            refresh_token=refresh_token,
            external_workspace_id=external_workspace_id,
            client_id=client_id,
        )

    def decode_access_token(self, access_token: str) -> TokenClaims:
        return self._client.decode_access_token(access_token)

    def invite_member(
        self,
        *,
        access_token: str,
        team_id: str,
        email: str,
        cookie_header: str = "",
        seat_type: str = "default",
        proxy_url: str = "",
    ) -> dict:
        return self._client.invite_member(
            access_token=access_token,
            team_id=team_id,
            email=email,
            cookie_header=cookie_header,
            seat_type=seat_type,
            proxy_url=proxy_url,
        )

    def accept_invite(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        device_id: str = "",
    ) -> dict:
        return self._client.accept_invite(
            access_token=access_token,
            team_id=team_id,
            proxy_url=proxy_url,
            device_id=device_id,
        )

    def probe_membership(self, *, access_token: str, team_id: str) -> dict:
        return self._client.probe_membership(access_token=access_token, team_id=team_id)

    def fetch_subscription(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        return self._client.fetch_subscription(
            access_token=access_token,
            account_id=account_id,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )

    def list_account_users(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str = "",
        page_size: int = 100,
        proxy_url: str = "",
    ) -> list[dict]:
        return self._client.list_account_users(
            access_token=access_token,
            account_id=account_id,
            cookie_header=cookie_header,
            page_size=page_size,
            proxy_url=proxy_url,
        )

    def list_account_invites(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str = "",
        page_size: int = 100,
        proxy_url: str = "",
    ) -> list[dict]:
        return self._client.list_account_invites(
            access_token=access_token,
            account_id=account_id,
            cookie_header=cookie_header,
            page_size=page_size,
            proxy_url=proxy_url,
        )

    def heartbeat_codex_credential(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        model: str = "",
    ) -> dict:
        return self._client.heartbeat_codex_credential(
            access_token=access_token,
            team_id=team_id,
            proxy_url=proxy_url,
            model=model,
        )

    def probe_codex_responses_usage(
        self,
        *,
        access_token: str,
        team_id: str,
        proxy_url: str = "",
        model: str = "",
    ) -> dict:
        return self._client.probe_codex_responses_usage(
            access_token=access_token,
            team_id=team_id,
            proxy_url=proxy_url,
            model=model,
        )

    def fetch_wham_usage(
        self,
        *,
        access_token: str,
        chatgpt_account_id: str = "",
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        return self._client.fetch_wham_usage(
            access_token=access_token,
            chatgpt_account_id=chatgpt_account_id,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )

    def create_wham_auth_credential(
        self,
        *,
        access_token: str = "",
        chatgpt_account_id: str,
        name: str,
        ttl_seconds: int = 7_776_000,
        cookie_header: str = "",
        proxy_url: str = "",
    ) -> dict:
        return self._client.create_wham_auth_credential(
            access_token=access_token,
            chatgpt_account_id=chatgpt_account_id,
            name=name,
            ttl_seconds=ttl_seconds,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
        )
