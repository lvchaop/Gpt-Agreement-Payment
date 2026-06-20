from __future__ import annotations

import base64
import json

import httpx
import pytest

from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.openai_chatgpt import (
    OpenAIChatGPTClient,
    OpenAIChatGPTClientConfig,
    OpenAIChatGPTPlugin,
    WorkspaceMismatchError,
    decode_access_token_claims,
)


def jwt_with_claims(*, chatgpt_account_id: str, user_id: str = "user-1") -> str:
    header = _b64({"alg": "none", "typ": "JWT"})
    payload = _b64(
        {
            "sub": "sub-1",
            "https://api.openai.com/auth": {
                "chatgpt_account_id": chatgpt_account_id,
                "chatgpt_user_id": user_id,
            },
        }
    )
    return f"{header}.{payload}."


def _b64(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def test_decode_access_token_claims_reads_workspace_and_user() -> None:
    claims = decode_access_token_claims(jwt_with_claims(chatgpt_account_id="workspace-1"))

    assert claims.token_chatgpt_account_id == "workspace-1"
    assert claims.account_id == "user-1"


def test_refresh_workspace_token_posts_oauth_grant_and_checks_workspace() -> None:
    access_token = jwt_with_claims(chatgpt_account_id="workspace-1")
    requests: list[httpx.Request] = []

    def auth_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/oauth/token"
        assert b"grant_type=refresh_token" in request.content
        assert b"refresh_token=rt-1" in request.content
        assert b"client_id=client-1" in request.content
        return httpx.Response(
            200,
            json={
                "access_token": access_token,
                "id_token": "id-1",
                "refresh_token": "rt-2",
                "expires_in": 3600,
            },
        )

    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(auth_handler),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
    )

    token_set = client.refresh_workspace_token(
        refresh_token="rt-1",
        external_workspace_id="workspace-1",
        client_id="client-1",
    )

    assert token_set.access_token == access_token
    assert token_set.id_token == "id-1"
    assert token_set.refresh_token == "rt-2"
    assert token_set.claims.token_chatgpt_account_id == "workspace-1"
    assert token_set.expires_at is not None
    assert len(requests) == 1


def test_refresh_workspace_token_rejects_workspace_mismatch() -> None:
    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "access_token": jwt_with_claims(chatgpt_account_id="workspace-other"),
                    },
                )
            ),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
    )

    with pytest.raises(WorkspaceMismatchError):
        client.refresh_workspace_token(
            refresh_token="rt-1",
            external_workspace_id="workspace-1",
            client_id="client-1",
        )


def test_invite_and_accept_use_team_backend_endpoints_and_headers() -> None:
    requests: list[httpx.Request] = []

    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer access-1"
        if request.url.path == "/backend-api/accounts/workspace-1/invites":
            assert request.headers["chatgpt-account-id"] == "workspace-1"
            body = json.loads(request.content)
            assert body["email_addresses"] == ["member@example.test"]
            return httpx.Response(200, json={"account_invites": [{"id": "invite-1"}]})
        if request.url.path == "/backend-api/accounts/workspace-1/invites/accept":
            assert "chatgpt-account-id" not in request.headers
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"error": "not found"})

    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(chatgpt_handler),
        ),
    )

    invite = client.invite_member(
        access_token="access-1",
        team_id="workspace-1",
        email="member@example.test",
    )
    accepted = client.accept_invite(access_token="access-1", team_id="workspace-1")

    assert invite["account_invites"][0]["id"] == "invite-1"
    assert accepted["ok"] is True
    assert [request.url.path for request in requests] == [
        "/backend-api/accounts/workspace-1/invites",
        "/backend-api/accounts/workspace-1/invites/accept",
    ]


def test_openai_chatgpt_plugin_contract() -> None:
    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
    )
    plugin: OpenAIChatGPTProvider = OpenAIChatGPTPlugin(client)

    assert plugin.healthcheck().status == "ok"
    assert "openai_chatgpt.team_workspace.invite_member" in plugin.capabilities()
    assert "openai_chatgpt.codex.heartbeat" in plugin.capabilities()


def test_heartbeat_codex_credential_checks_workspace_claim() -> None:
    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
    )

    result = client.heartbeat_codex_credential(
        access_token=jwt_with_claims(chatgpt_account_id="workspace-1"),
        team_id="workspace-1",
    )

    assert result["status"] == "ok"
