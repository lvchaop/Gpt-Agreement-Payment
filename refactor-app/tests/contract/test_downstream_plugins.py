from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamProvider
from refactor_app.plugins.downstream_cpa import CpaClient, CpaClientConfig, CpaDownstreamPlugin
from refactor_app.plugins.downstream_cpa.client import build_cpa_auth_file
from refactor_app.plugins.downstream_sub2api import (
    Sub2ApiClient,
    Sub2ApiClientConfig,
    Sub2ApiDownstreamPlugin,
)
from refactor_app.plugins.downstream_sub2api.client import build_sub2api_import_payload


def sample_payload() -> DownstreamCodexPayload:
    return DownstreamCodexPayload(
        access_token="access-1",
        id_token="id-1",
        refresh_token="rt-1",
        email="user@example.test",
        account_id="chatgpt-user-1",
        downstream_chatgpt_account_id="workspace-1",
        token_chatgpt_account_id="workspace-1",
        client_id="client-1",
        expires_at=datetime(2026, 6, 19, 1, 2, 3, tzinfo=UTC),
        plan_tag="team",
        plan_type="team",
    )


def test_cpa_payload_builder_preserves_workspace_chatgpt_account_id() -> None:
    name, body = build_cpa_auth_file(sample_payload())

    assert name == "ChatGPT_team_user@example.test"
    assert body["type"] == "codex"
    assert body["email"] == "user@example.test"
    assert body["account_id"] == "chatgpt-user-1"
    assert body["chatgpt_account_id"] == "workspace-1"
    assert body["chatgpt_user_id"] == "chatgpt-user-1"
    assert body["client_id"] == "client-1"


def test_sub2api_payload_builder_sets_update_existing_false_by_default() -> None:
    body = build_sub2api_import_payload(sample_payload())
    credentials = json.loads(body["content"])

    assert body["update_existing"] is False
    assert body["name"] == "codex-user@example.test-team.json"
    assert credentials["chatgpt_account_id"] == "workspace-1"
    assert credentials["chatgpt_user_id"] == "chatgpt-user-1"
    assert credentials["client_id"] == "client-1"


def test_cpa_client_posts_management_auth_file() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v0/management/auth-files"
        assert request.url.params["name"] == "ChatGPT_team_user@example.test"
        assert request.headers["Authorization"] == "Bearer admin-key"
        body = request.read()
        assert b'"chatgpt_account_id":"workspace-1"' in body
        return httpx.Response(200, json={"id": "auth-file-1"})

    plugin: DownstreamProvider = CpaDownstreamPlugin(
        CpaClient(
            CpaClientConfig(base_url="https://cpa.example.test", admin_key="admin-key"),
            http_client=httpx.Client(
                base_url="https://cpa.example.test",
                headers={"Authorization": "Bearer admin-key"},
                transport=httpx.MockTransport(handler),
            ),
        )
    )

    result = plugin.push_codex_credential(sample_payload())

    assert result.pushed is True
    assert result.downstream_external_id == "auth-file-1"
    assert len(requests) == 1


def test_sub2api_client_posts_codex_session_import() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v1/admin/accounts/import/codex-session"
        assert request.headers["Authorization"] == "Bearer admin-key"
        body = request.read()
        assert b'"update_existing":false' in body
        payload = json.loads(body)
        content = json.loads(payload["content"])
        assert content["chatgpt_account_id"] == "workspace-1"
        return httpx.Response(200, json={"id": "sub2api-account-1"})

    plugin: DownstreamProvider = Sub2ApiDownstreamPlugin(
        Sub2ApiClient(
            Sub2ApiClientConfig(base_url="https://sub2api.example.test", admin_key="admin-key"),
            http_client=httpx.Client(
                base_url="https://sub2api.example.test",
                headers={"Authorization": "Bearer admin-key"},
                transport=httpx.MockTransport(handler),
            ),
        )
    )

    result = plugin.push_codex_credential(sample_payload())

    assert result.pushed is True
    assert result.downstream_external_id == "sub2api-account-1"
    assert len(requests) == 1
