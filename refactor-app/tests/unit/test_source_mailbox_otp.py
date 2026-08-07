from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from refactor_app.api.routes.jobs import _redact_value
from refactor_app.plugins.source_mailbox_otp import (
    SourceMailboxOtpConfig,
    SourceMailboxOtpError,
    SourceMailboxOtpProvider,
)


def test_mailapi_url_ignores_old_message_and_returns_current_otp() -> None:
    email = "Source.User@outlook.com"
    issued_after = datetime(2026, 7, 23, 2, 30, tzinfo=UTC).timestamp()
    responses = [
        {
            "status": "success",
            "received_at": "2026-07-23T02:20:00Z",
            "from": "noreply@tm.openai.com",
            "code": "111111",
        },
        {
            "status": "success",
            "received_at": "2026-07-23T02:30:05Z",
            "from": "noreply@tm.openai.com",
            "code": "654321",
        },
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        provider = SourceMailboxOtpProvider(
            SourceMailboxOtpConfig(
                email=email,
                mailbox_url=(
                    "http://mail.example.test/api/open/email/latest?"
                    f"api_key=secret&pt=secret&email={email}"
                ),
                poll_interval_s=0,
            ),
            client=client,
            sleep_fn=lambda _seconds: None,
        )

        otp = provider.wait_for_otp_by_email(
            email=email,
            timeout_s=10,
            issued_after=issued_after,
            max_polls=2,
        )

        assert otp.code == "654321"
        assert otp.raw["received_at"] == "2026-07-23T02:30:05Z"
        assert responses == []
    finally:
        client.close()


def test_mailapi_url_rejects_message_without_received_at() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "status": "success",
                    "from": "noreply@tm.openai.com",
                    "subject": "Your OpenAI verification code",
                    "body": "Your verification code is 654321",
                },
            )
        ),
        trust_env=False,
    )
    try:
        provider = SourceMailboxOtpProvider(
            SourceMailboxOtpConfig(
                email="source@example.test",
                mailbox_url=(
                    "http://mail.example.test/latest?"
                    "api_key=secret&pt=secret&email=source%40example.test"
                ),
            ),
            client=client,
            sleep_fn=lambda _seconds: None,
        )

        with pytest.raises(TimeoutError, match="missing received_at"):
            provider.wait_for_otp_by_email(
                email="source@example.test",
                timeout_s=10,
                issued_after=datetime.now(UTC).timestamp(),
                max_polls=1,
            )
    finally:
        client.close()


def test_mailapi_url_does_not_return_the_same_otp_message_twice() -> None:
    email = "source@example.test"
    issued_after = datetime(2026, 7, 23, 2, 30, tzinfo=UTC).timestamp()
    responses = [
        {
            "status": "success",
            "received_at": "2026-07-23T02:30:05Z",
            "from": "noreply@tm.openai.com",
            "code": "111111",
        },
        {
            "status": "success",
            "received_at": "2026-07-23T02:30:05Z",
            "from": "noreply@tm.openai.com",
            "code": "111111",
        },
        {
            "status": "success",
            "received_at": "2026-07-23T02:30:15Z",
            "from": "noreply@tm.openai.com",
            "code": "222222",
        },
    ]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        provider = SourceMailboxOtpProvider(
            SourceMailboxOtpConfig(
                email=email,
                mailbox_url=f"http://mail.example.test/latest?email={email}",
                poll_interval_s=0,
            ),
            client=client,
            sleep_fn=lambda _seconds: None,
        )

        first = provider.wait_for_otp_by_email(
            email=email,
            timeout_s=10,
            issued_after=issued_after,
            max_polls=1,
        )
        second = provider.wait_for_otp_by_email(
            email=email,
            timeout_s=10,
            issued_after=issued_after,
            max_polls=2,
        )

        assert first.code == "111111"
        assert second.code == "222222"
        assert responses == []
    finally:
        client.close()


def test_graph_mailbox_refreshes_token_and_filters_message_time() -> None:
    issued_after = datetime(2026, 7, 23, 2, 30, tzinfo=UTC).timestamp()
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.host))
        if request.url.host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "graph-access"})
        assert request.headers["authorization"] == "Bearer graph-access"
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "receivedDateTime": "2026-07-23T02:30:10Z",
                        "from": {
                            "emailAddress": {"address": "noreply@tm.openai.com"}
                        },
                        "subject": "Your ChatGPT code is 234567",
                        "body": {"contentType": "text", "content": "Code: 234567"},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    try:
        provider = SourceMailboxOtpProvider(
            SourceMailboxOtpConfig(
                email="source@outlook.com",
                graph_client_id="client-id",
                graph_refresh_token="refresh-token",
            ),
            client=client,
            sleep_fn=lambda _seconds: None,
        )

        otp = provider.wait_for_otp_by_email(
            email="source@outlook.com",
            timeout_s=10,
            issued_after=issued_after,
            max_polls=1,
        )

        assert otp.code == "234567"
        assert requests == [
            ("POST", "login.microsoftonline.com"),
            ("GET", "graph.microsoft.com"),
        ]
    finally:
        client.close()


def test_mailbox_url_email_must_match_source_account() -> None:
    with pytest.raises(SourceMailboxOtpError, match="does not match"):
        SourceMailboxOtpProvider(
            SourceMailboxOtpConfig(
                email="source@example.test",
                mailbox_url="http://mail.example.test/latest?email=other%40example.test",
            )
        )


def test_job_redaction_hides_mailbox_url_credentials() -> None:
    redacted = _redact_value(
        {
            "source_mailbox_url": (
                "http://mail.example.test/latest?"
                "api_key=secret-key&pt=secret-pt&email=source%40example.test"
            ),
            "source_mailbox_refresh_token": "secret-refresh-token",
        }
    )

    assert "secret-key" not in redacted["source_mailbox_url"]
    assert "secret-pt" not in redacted["source_mailbox_url"]
    assert "source%40example.test" in redacted["source_mailbox_url"]
    assert redacted["source_mailbox_refresh_token"] == "<redacted>"


def test_job_redaction_exposes_cookie_names_but_not_cookie_values() -> None:
    redacted = _redact_value(
        {
            "request_cookie_names": ["oai-did", "auth-session"],
            "cookie_header": "oai-did=secret-device",
        }
    )

    assert redacted["request_cookie_names"] == ["oai-did", "auth-session"]
    assert redacted["cookie_header"] == "<redacted>"
