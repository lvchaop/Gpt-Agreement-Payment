from __future__ import annotations

import httpx

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
