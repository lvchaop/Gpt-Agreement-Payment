from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx

from refactor_app.plugins.contracts import DownstreamCodexPayload, DownstreamProvider
from refactor_app.plugins.downstream_cpa import CpaClient, CpaClientConfig, CpaDownstreamPlugin
from refactor_app.plugins.downstream_cpa.client import build_cpa_auth_file
from refactor_app.plugins.downstream_custom_http.client import (
    CustomHttpClient,
    CustomHttpClientConfig,
    build_custom_http_payload,
)
from refactor_app.plugins.downstream_custom_http.plugin import CustomHttpDownstreamPlugin
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

    assert name == "codex-08ea5c18-user@example.test-team.json"
    assert body["type"] == "codex"
    assert body["email"] == "user@example.test"
    assert body["account_id"] == "chatgpt-user-1"


def test_sub2api_payload_builder_sets_update_existing_false_by_default() -> None:
    body = build_sub2api_import_payload(sample_payload())
    credentials = json.loads(body["content"])

    assert body["update_existing"] is False
    assert body["name"] == "codex-user@example.test-team.json"
    assert credentials["chatgpt_account_id"] == "workspace-1"
    assert credentials["chatgpt_user_id"] == "chatgpt-user-1"
    assert credentials["client_id"] == "client-1"


def test_sub2api_payload_builder_adds_concurrency_and_group_ids() -> None:
    body = build_sub2api_import_payload(sample_payload(), concurrency=7, group_ids=(1, 2, 3))

    assert body["concurrency"] == 7
    assert body["group_ids"] == [1, 2, 3]


def test_custom_http_sub2api_payload_is_raw_credentials_json() -> None:
    body = build_custom_http_payload(sample_payload(), payload_type="sub2api")

    assert "content" not in body
    assert "name" not in body
    assert body["type"] == "codex"
    assert body["chatgpt_account_id"] == "workspace-1"
    assert body["refresh_token"] == "rt-1"


def test_custom_http_sub2api_admin_accounts_payload_wraps_create_account_request() -> None:
    payload = sample_payload()
    body = build_custom_http_payload(
        payload,
        payload_type="sub2api_admin_accounts",
        sub2api_concurrency=3,
        sub2api_group_ids=(10, 20),
    )

    assert body["name"] == "codex-user@example.test-team"
    assert body["platform"] == "openai"
    assert body["type"] == "oauth"
    assert body["concurrency"] == 3
    assert body["group_ids"] == [10, 20]
    assert body["expires_at"] == int(payload.expires_at.timestamp())
    assert body["credentials"]["type"] == "codex"
    assert body["credentials"]["chatgpt_account_id"] == "workspace-1"
    assert body["credentials"]["refresh_token"] == "rt-1"
    assert "content" not in body


def test_cpa_client_posts_management_auth_file() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/v0/management/auth-files"
        assert request.url.params["name"] == "codex-08ea5c18-user@example.test-team.json"
        assert request.headers["Authorization"] == "Bearer admin-key"
        body = request.read()
        assert b'"account_id":"chatgpt-user-1"' in body
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


def test_custom_http_client_posts_full_url_with_custom_header() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://custom.example.test/push"
        assert request.headers["x-api-key"] == "secret-1"
        body = json.loads(request.read())
        assert body["chatgpt_account_id"] == "workspace-1"
        assert body["refresh_token"] == "rt-1"
        assert "content" not in body
        return httpx.Response(200, json={"id": "custom-1"})

    plugin: DownstreamProvider = CustomHttpDownstreamPlugin(
        CustomHttpClient(
            CustomHttpClientConfig(
                url="https://custom.example.test/push",
                auth_header_name="x-api-key",
                auth_header_value="secret-1",
                payload_type="sub2api",
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
    )

    result = plugin.push_codex_credential(sample_payload())

    assert result.pushed is True
    assert result.downstream_external_id == "custom-1"
    assert len(requests) == 1


def test_custom_http_client_posts_sub2api_admin_accounts_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://custom.example.test/api/v1/admin/accounts"
        assert request.headers["x-api-key"] == "secret-1"
        body = json.loads(request.read())
        assert body["name"] == "codex-user@example.test-team"
        assert body["platform"] == "openai"
        assert body["type"] == "oauth"
        assert body["concurrency"] == 4
        assert body["group_ids"] == [11, 12]
        assert body["credentials"]["chatgpt_account_id"] == "workspace-1"
        assert body["expires_at"] == body["credentials"]["expires_at"]
        return httpx.Response(200, json={"data": {"id": 2337}})

    plugin: DownstreamProvider = CustomHttpDownstreamPlugin(
        CustomHttpClient(
            CustomHttpClientConfig(
                url="https://custom.example.test/api/v1/admin/accounts",
                auth_header_name="x-api-key",
                auth_header_value="secret-1",
                payload_type="sub2api_admin_accounts",
                sub2api_concurrency=4,
                sub2api_group_ids=(11, 12),
            ),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
    )

    result = plugin.push_codex_credential(sample_payload())

    assert result.pushed is True
    assert result.downstream_external_id == "2337"
    assert len(requests) == 1
