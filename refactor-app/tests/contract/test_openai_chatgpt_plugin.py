from __future__ import annotations

import base64
import json

import httpx
import pytest
from curl_cffi.const import CurlOpt

from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.openai_chatgpt import (
    OpenAIChatGPTClient,
    OpenAIChatGPTClientConfig,
    OpenAIChatGPTClientError,
    OpenAIChatGPTPlugin,
    OpenAIChatGPTTimeoutError,
    WorkspaceMismatchError,
    decode_access_token_claims,
)
from refactor_app.plugins.openai_chatgpt import client as client_module


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
            return httpx.Response(
                200,
                json={
                    "account_invites": [{"id": "invite-1", "email_address": "member@example.test"}],
                    "errored_emails": [],
                },
            )
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


def test_batch_invite_sends_all_emails_and_preserves_per_email_results() -> None:
    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["email_addresses"] == [
            "ok@example.test",
            "bad@example.test",
        ]
        return httpx.Response(
            200,
            json={
                "account_invites": [{"id": "invite-1", "email_address": "ok@example.test"}],
                "errored_emails": [
                    {
                        "email_address": "bad@example.test",
                        "error": "Unable to invite user due to an error.",
                    }
                ],
            },
        )

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

    payload = client.invite_members(
        access_token="access-1",
        team_id="workspace-1",
        emails=["ok@example.test", "bad@example.test"],
    )

    assert payload["account_invites"][0]["email_address"] == "ok@example.test"
    assert payload["errored_emails"][0]["email_address"] == "bad@example.test"


def test_change_email_uses_web_session_cookie_and_bearer_token() -> None:
    requests: list[httpx.Request] = []
    access_token = jwt_with_claims(chatgpt_account_id="personal-1", user_id="user-1")
    session_count = 0

    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        nonlocal session_count
        requests.append(request)
        assert "chatgpt-account-id" not in request.headers
        if request.url.path == "/api/auth/session":
            session_count += 1
            assert request.method == "GET"
            assert request.headers["cookie"] == (
                "__Secure-next-auth.session-token=session-1; oai-did=device-1"
            )
            return httpx.Response(
                200,
                json={
                    "accessToken": access_token,
                    "user": {
                        "email": (
                            "new@example.test" if session_count > 1 else "old@example.test"
                        )
                    },
                },
            )
        assert request.headers["authorization"] == f"Bearer {access_token}"
        assert request.headers["cookie"] == (
            "__Secure-next-auth.session-token=session-1; oai-did=device-1"
        )
        if request.url.path == "/backend-api/accounts/change_email/eligibility":
            assert request.method == "GET"
            return httpx.Response(200, json={"eligible": True})
        if request.url.path == "/backend-api/accounts/change_email/begin":
            assert request.method == "POST"
            assert json.loads(request.content) == {"email": "new@example.test"}
            return httpx.Response(200, json={"sent": True})
        if request.url.path == "/backend-api/accounts/change_email/verify":
            assert request.method == "POST"
            assert json.loads(request.content) == {
                "email": "new@example.test",
                "code": "123456",
            }
            return httpx.Response(200, json={"changed": True})
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
    cookie = "__Secure-next-auth.session-token=session-1; oai-did=device-1"

    session_before = client.fetch_web_session_payload(cookie_header=cookie)
    eligibility = client.check_change_email_eligibility(
        access_token=access_token,
        cookie_header=cookie,
    )
    begin = client.begin_change_email(
        access_token=access_token,
        cookie_header=cookie,
        email="new@example.test",
    )
    verify = client.verify_change_email(
        access_token=access_token,
        cookie_header=cookie,
        email="new@example.test",
        code="123456",
    )
    session_after = client.fetch_web_session_payload(cookie_header=cookie)

    assert session_before["user"]["email"] == "old@example.test"
    assert eligibility["eligible"] is True
    assert begin["sent"] is True
    assert verify["changed"] is True
    assert session_after["user"]["email"] == "new@example.test"
    assert [request.url.path for request in requests] == [
        "/api/auth/session",
        "/backend-api/accounts/change_email/eligibility",
        "/backend-api/accounts/change_email/begin",
        "/backend-api/accounts/change_email/verify",
        "/api/auth/session",
    ]


def test_remove_account_user_uses_workspace_delete_endpoint_and_headers() -> None:
    requests: list[httpx.Request] = []

    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "DELETE"
        assert request.url.path == "/backend-api/accounts/workspace-1/users/user-member-1"
        assert request.headers["authorization"] == "Bearer access-1"
        assert request.headers["chatgpt-account-id"] == "workspace-1"
        return httpx.Response(200, json={"ok": True})

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

    result = client.remove_account_user(
        access_token="access-1",
        account_id="workspace-1",
        user_id="user-member-1",
    )

    assert result["ok"] is True
    assert len(requests) == 1


def test_single_invite_rejects_http_200_business_error() -> None:
    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "account_invites": [],
                        "errored_emails": [
                            {
                                "email_address": "member@example.test",
                                "error": "Unable to invite user due to an error.",
                            }
                        ],
                    },
                )
            ),
        ),
    )

    with pytest.raises(OpenAIChatGPTClientError, match="Unable to invite user"):
        client.invite_member(
            access_token="access-1",
            team_id="workspace-1",
            email="member@example.test",
        )


def test_batch_invite_exposes_typed_timeout() -> None:
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(timeout_s=30),
        auth_http_client=httpx.Client(
            base_url="https://auth.openai.com",
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        ),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(timeout_handler),
        ),
    )

    with pytest.raises(OpenAIChatGPTTimeoutError, match="timed out after 30s"):
        client.invite_members(
            access_token="access-1",
            team_id="workspace-1",
            emails=["member@example.test"],
        )


def test_proxy_session_uses_pre_resolved_proxy_dns_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[dict] = []

    class FakeCurlSession:
        def __init__(self, **kwargs: object) -> None:
            created.append(dict(kwargs))

    monkeypatch.setattr(client_module.curl_requests, "Session", FakeCurlSession)
    client = OpenAIChatGPTClient(OpenAIChatGPTClientConfig())
    resolve = ("p.webshare.io:80:198.18.0.142",)

    first = client._curl_session(  # noqa: SLF001
        "http://username:password@p.webshare.io:80",
        proxy_resolve=resolve,
    )
    second = client._curl_session(  # noqa: SLF001
        "http://username:password@p.webshare.io:80",
        proxy_resolve=resolve,
    )

    assert first is second
    assert len(created) == 1
    assert created[0]["curl_options"] == {CurlOpt.RESOLVE: list(resolve)}


def test_update_subscription_seats_uses_admin_headers_and_minimal_body() -> None:
    requests: list[httpx.Request] = []

    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/backend-api/subscriptions/update"
        assert request.headers["authorization"] == "Bearer admin-access"
        assert request.headers["chatgpt-account-id"] == "workspace-1"
        assert request.headers["cookie"] == "oai-did=device-1; session=s1"
        assert json.loads(request.content) == {
            "account_id": "workspace-1",
            "updated_seats": 32,
        }
        return httpx.Response(200, json={"ok": True})

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

    result = client.update_subscription_seats(
        access_token="admin-access",
        account_id="workspace-1",
        updated_seats=32,
        cookie_header="oai-did=device-1; session=s1",
    )

    assert result["ok"] is True
    assert len(requests) == 1


def test_create_wham_auth_credential_exchanges_workspace_before_post() -> None:
    requests: list[httpx.Request] = []
    workspace_access_token = jwt_with_claims(chatgpt_account_id="workspace-1")

    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/auth/session":
            assert request.url.params["exchange_workspace_token"] == "true"
            assert request.url.params["workspace_id"] == "workspace-1"
            assert request.url.params["reason"] == "setCurrentAccount"
            assert request.headers["cookie"] == (
                "__Secure-next-auth.session-token=session-1; oai-did=device-1"
            )
            return httpx.Response(200, json={"accessToken": workspace_access_token})
        if request.url.path == "/backend-api/wham/auth-credentials":
            assert request.headers["authorization"] == f"Bearer {workspace_access_token}"
            assert request.headers["chatgpt-account-id"] == "workspace-1"
            assert "cookie" not in request.headers
            assert request.headers["oai-device-id"] == "device-1"
            body = json.loads(request.content)
            assert body == {
                "name": "cred-1",
                "scopes": ["chatgpt.workspace.feature.allow-codex-local-access.access"],
                "ttl": 7776000,
            }
            return httpx.Response(
                200,
                json={
                    "access_token": "at-1",
                    "workspace_id": "workspace-1",
                    "credential_id": "token-1",
                },
            )
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

    payload = client.create_wham_auth_credential(
        chatgpt_account_id="workspace-1",
        name="cred-1",
        cookie_header=("oai-did=device-1; __Secure-next-auth.session-token=session-1"),
    )

    assert payload["access_token"] == "at-1"
    assert [request.url.path for request in requests] == [
        "/api/auth/session",
        "/backend-api/wham/auth-credentials",
    ]


def test_create_wham_auth_credential_requires_exchanged_access_token() -> None:
    requests: list[httpx.Request] = []

    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/api/auth/session"
        return httpx.Response(200, json={"user": {"email": "member@example.test"}})

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

    with pytest.raises(OpenAIChatGPTClientError, match="workspace_session_access_token_missing"):
        client.create_wham_auth_credential(
            chatgpt_account_id="workspace-1",
            name="cred-1",
            cookie_header="oai-did=device-1; session=s1",
        )

    assert [request.url.path for request in requests] == ["/api/auth/session"]


def test_exchange_workspace_session_rejects_token_for_different_workspace() -> None:
    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/auth/session"
        return httpx.Response(
            200,
            json={"accessToken": jwt_with_claims(chatgpt_account_id="workspace-other")},
        )

    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(chatgpt_handler),
        ),
    )

    with pytest.raises(
        WorkspaceMismatchError,
        match="expected=workspace-1 actual=workspace-other",
    ):
        client.exchange_workspace_session_access_token(
            chatgpt_account_id="workspace-1",
            cookie_header="__Secure-next-auth.session-token=session-1; oai-did=device-1",
        )


def test_exchange_workspace_session_payload_preserves_account_plan_type() -> None:
    def chatgpt_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/auth/session"
        return httpx.Response(
            200,
            json={
                "accessToken": jwt_with_claims(chatgpt_account_id="personal-1"),
                "account": {
                    "id": "personal-1",
                    "structure": "personal",
                    "planType": "pro",
                },
            },
        )

    client = OpenAIChatGPTClient(
        OpenAIChatGPTClientConfig(),
        chatgpt_http_client=httpx.Client(
            base_url="https://chatgpt.com",
            transport=httpx.MockTransport(chatgpt_handler),
        ),
    )

    payload = client.exchange_workspace_session_payload(
        chatgpt_account_id="personal-1",
        cookie_header="__Secure-next-auth.session-token=session-1; oai-did=device-1",
    )

    assert payload["account"]["planType"] == "pro"


def test_minimal_web_session_cookie_preserves_chunked_session_token() -> None:
    cookie_header = (
        "__Secure-next-auth.session-token.1=second; "
        "oai-did=device-1; "
        "__Secure-next-auth.session-token.0=first; "
        "__Host-next-auth.csrf-token=csrf-1; "
        "cf_clearance=ignored"
    )

    result = client_module._minimal_web_session_cookie_header(cookie_header)

    assert result == (
        "__Secure-next-auth.session-token.0=first; "
        "__Secure-next-auth.session-token.1=second; "
        "__Host-next-auth.csrf-token=csrf-1; "
        "oai-did=device-1"
    )


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
    assert "openai_chatgpt.team_workspace.subscription.update_seats" in plugin.capabilities()
    assert "openai_chatgpt.team_workspace.users.remove" in plugin.capabilities()
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
