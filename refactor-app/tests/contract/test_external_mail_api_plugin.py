from __future__ import annotations

import json

import httpx
import pytest

from refactor_app.plugins.contracts import MailProvider
from refactor_app.plugins.mail_external_api import (
    ExternalMailApiClient,
    ExternalMailApiClientConfig,
    ExternalMailApiPlugin,
)


def test_external_mail_api_client_lifecycle() -> None:
    requests: list[httpx.Request] = []
    otp_attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal otp_attempts
        requests.append(request)
        assert request.headers["X-API-Key"] == "mail-key"
        if request.method == "POST" and request.url.path == "/mailbox/allocate":
            return httpx.Response(
                200,
                json={"data": {"external_lease_id": "lease-1", "email": "user@example.test"}},
            )
        if request.method == "GET" and request.url.path == "/mailbox/lease-1/otp":
            otp_attempts += 1
            if otp_attempts == 1:
                return httpx.Response(200, json={"data": {}})
            return httpx.Response(200, json={"data": {"code": "123456"}})
        if request.method == "POST" and request.url.path in {
            "/mailbox/lease-1/used",
            "/mailbox/lease-1/failed",
            "/mailbox/lease-1/release",
        }:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"error": "not found"})

    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(
            base_url="https://mail.example.test",
            api_key="mail-key",
            poll_interval_s=0.01,
        ),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(handler),
        ),
        sleep_fn=lambda _seconds: None,
    )

    lease = client.allocate_mailbox(purpose="signup")
    otp = client.poll_otp(external_lease_id=lease.external_lease_id, timeout_s=1)
    client.mark_used(external_lease_id=lease.external_lease_id)
    client.mark_failed(
        external_lease_id=lease.external_lease_id,
        failure_code="otp_invalid",
        failure_message="OTP rejected",
    )
    client.release(external_lease_id=lease.external_lease_id, reason="done")

    assert lease.provider == "external_mail_api"
    assert lease.external_lease_id == "lease-1"
    assert lease.email == "user@example.test"
    assert otp is not None
    assert otp.code == "123456"
    assert [request.url.path for request in requests] == [
        "/mailbox/allocate",
        "/mailbox/lease-1/otp",
        "/mailbox/lease-1/otp",
        "/mailbox/lease-1/used",
        "/mailbox/lease-1/failed",
        "/mailbox/lease-1/release",
    ]


def test_external_mail_api_plugin_implements_mail_provider_contract() -> None:
    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(base_url="https://mail.example.test", api_key="mail-key"),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "data": {
                            "external_lease_id": "lease-1",
                            "email": "user@example.test",
                        }
                    },
                )
            ),
        ),
    )
    plugin: MailProvider = ExternalMailApiPlugin(client)

    assert plugin.healthcheck().status == "ok"
    assert "mailbox.allocate" in plugin.capabilities()
    assert plugin.allocate_mailbox().external_lease_id == "lease-1"


def test_external_mail_api_client_pool_claim_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/external/pool/claim-random":
            assert request.method == "POST"
            assert request.read()
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "account_id": 123,
                        "email": "abc@example.test",
                        "email_domain": "example.test",
                        "claim_token": "clm_xxx",
                    },
                },
            )
        if request.method == "GET" and request.url.path == "/api/external/pool/stats":
            return httpx.Response(200, json={"success": True, "data": {"available": 1}})
        if request.url.path in {
            "/api/external/pool/claim-complete",
            "/api/external/pool/claim-release",
        }:
            assert request.method == "POST"
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"success": False})

    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(base_url="https://mail.example.test", api_key="mail-key"),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(handler),
        ),
    )

    claim = client.claim_random(
        caller_id="worker-1",
        task_id="task-1",
        provider="cloudflare_temp_mail",
        project_key="openai-register",
        email_domain="example.test",
    )
    stats = client.pool_stats()
    client.claim_complete(claim, result="success", detail="ok")
    client.claim_release(claim, reason="abort")

    assert claim.account_id == "123"
    assert claim.email == "abc@example.test"
    assert claim.claim_token == "clm_xxx"
    assert stats["data"]["available"] == 1
    assert [request.url.path for request in requests] == [
        "/api/external/pool/claim-random",
        "/api/external/pool/stats",
        "/api/external/pool/claim-complete",
        "/api/external/pool/claim-release",
    ]


def test_wait_for_otp_preserves_pool_email_case() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(request.url.params)
        return httpx.Response(200, json={"success": True, "data": {"verification_code": "654321"}})

    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(
            base_url="https://mail.example.test",
            api_key="mail-key",
            poll_interval_s=0.01,
        ),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(handler),
        ),
    )

    otp = client.wait_for_otp_by_email(email="LarryHunt510867@outlook.com", timeout_s=1)

    assert otp.code == "654321"
    assert seen_params["email"] == "LarryHunt510867@outlook.com"
    assert seen_params["code_length"] == "6-6"
    assert seen_params["code_source"] == "content"


def test_wait_for_otp_supports_all_code_sources() -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.update(request.url.params)
        return httpx.Response(
            200,
            json={"success": True, "data": {"verification_code": "654321"}},
        )

    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(
            base_url="https://mail.example.test",
            api_key="mail-key",
            poll_interval_s=0.01,
        ),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(handler),
        ),
    )

    otp = client.wait_for_otp_by_email(
        email="GarrettBrown979811@hotmail.com",
        timeout_s=1,
        code_source="all",
    )

    assert otp.code == "654321"
    assert seen_params["code_source"] == "all"


def test_wait_for_otp_honors_max_polls() -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            404,
            json={
                "success": False,
                "code": "VERIFICATION_CODE_NOT_FOUND",
                "message": "not found",
            },
        )

    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(
            base_url="https://mail.example.test",
            api_key="mail-key",
            poll_interval_s=0.01,
        ),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(handler),
        ),
        sleep_fn=lambda _seconds: None,
    )

    with pytest.raises(TimeoutError):
        client.wait_for_otp_by_email(
            email="two-polls@example.test",
            timeout_s=180,
            max_polls=2,
        )

    assert request_count == 2


def test_icloud_claim_and_otp_use_hidden_email() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST" and request.url.path == "/api/external/pool/claim-random":
            assert request.read()
            assert json.loads(request.content) == {
                "caller_id": "worker-icloud",
                "task_id": "task-icloud",
                "provider": "icloud_hide_my_email",
                "project_key": "openai-register",
            }
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "account_id": 456,
                        "email": "ocelots_plover_3p@icloud.com",
                        "email_domain": "icloud.com",
                        "claim_token": "clm_icloud",
                    },
                },
            )
        if request.method == "GET" and request.url.path == "/api/external/verification-code":
            assert request.url.params["email"] == "ocelots_plover_3p@icloud.com"
            assert request.url.params["code_source"] == "content"
            return httpx.Response(
                200,
                json={"success": True, "data": {"verification_code": "123456"}},
            )
        return httpx.Response(404, json={"success": False})

    client = ExternalMailApiClient(
        ExternalMailApiClientConfig(
            base_url="https://mail.example.test",
            api_key="mail-key",
            poll_interval_s=0.01,
        ),
        http_client=httpx.Client(
            base_url="https://mail.example.test",
            headers={"X-API-Key": "mail-key", "Accept": "application/json"},
            transport=httpx.MockTransport(handler),
        ),
    )

    claim = client.claim_random(
        caller_id="worker-icloud",
        task_id="task-icloud",
        provider="icloud_hide_my_email",
        project_key="openai-register",
    )
    otp = client.wait_for_otp_by_email(email=claim.email, timeout_s=1)

    assert claim.email == "ocelots_plover_3p@icloud.com"
    assert otp.code == "123456"
    assert [request.url.path for request in requests] == [
        "/api/external/pool/claim-random",
        "/api/external/verification-code",
    ]
