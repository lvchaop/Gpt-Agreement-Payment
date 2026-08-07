from __future__ import annotations

import json
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pytest

from refactor_app.plugins.twofauth import (
    TwoFAuthClient,
    TwoFAuthClientConfig,
    TwoFAuthClientError,
)


def test_twofauth_client_creates_reads_and_deletes_totp_account() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.headers["Accept"] == "application/json"
        if request.method == "POST":
            payload = json.loads(request.content)
            uri = urlparse(payload["uri"])
            query = parse_qs(uri.query)
            assert uri.scheme == "otpauth"
            assert uri.netloc == "totp"
            assert unquote(uri.path) == "/OpenAI:icloud-user@example.test"
            assert query == {
                "secret": ["BASE32SECRET"],
                "issuer": ["OpenAI"],
                "algorithm": ["SHA1"],
                "digits": ["6"],
                "period": ["30"],
            }
            return httpx.Response(201, json={"id": 42})
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "otp_type": "totp",
                    "password": "123456",
                    "generated_at": 1_786_000_000,
                    "period": 30,
                },
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404)

    client = TwoFAuthClient(
        TwoFAuthClientConfig(
            base_url="https://twofauth.example.test",
            api_token="test-token",
        ),
        http_client=httpx.Client(
            base_url="https://twofauth.example.test",
            transport=httpx.MockTransport(handler),
        ),
    )

    account_id = client.create_totp_account(
        email="icloud-user@example.test",
        secret="BASE32SECRET",
    )
    otp = client.get_otp(account_id)
    client.delete_account(account_id)
    client.close()

    assert account_id == "42"
    assert otp.password == "123456"
    assert otp.generated_at == 1_786_000_000
    assert otp.period == 30
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/v1/twofaccounts"),
        ("GET", "/api/v1/twofaccounts/42/otp"),
        ("DELETE", "/api/v1/twofaccounts/42"),
    ]


def test_twofauth_client_error_does_not_include_api_token() -> None:
    client = TwoFAuthClient(
        TwoFAuthClientConfig(
            base_url="https://twofauth.example.test",
            api_token="sensitive-api-token",
        ),
        http_client=httpx.Client(
            base_url="https://twofauth.example.test",
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(401, json={"message": "invalid token"})
            ),
        ),
    )

    with pytest.raises(TwoFAuthClientError) as error:
        client.get_otp("42")

    assert "HTTP 401" in str(error.value)
    assert "sensitive-api-token" not in str(error.value)


def test_twofauth_client_requires_token() -> None:
    with pytest.raises(TwoFAuthClientError, match="api_token is required"):
        TwoFAuthClient(TwoFAuthClientConfig(api_token=""))
