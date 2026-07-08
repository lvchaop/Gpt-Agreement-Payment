from __future__ import annotations

import httpx

import refactor_app.application.workflows.protocol_registration as protocol_registration
from refactor_app.application.workflows.protocol_registration import (
    HeroSmsPhoneProviderAdapter,
    ProtocolRegistrationInput,
    ProtocolRegistrationWorkflow,
    RegistrationMailProviderAdapter,
)
from refactor_app.plugins.contracts import OtpMessage
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthResult
from refactor_app.plugins.openai_auth_protocol.config import PhoneConfig


def test_hero_sms_phone_provider_adapter_lifecycle(monkeypatch) -> None:
    monkeypatch.setenv("HERO_SMS_API_KEY", "hero-key")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        params = dict(request.url.params)
        assert params["api_key"] == "hero-key"
        if params["action"] == "getNumberV2":
            assert params["service"] == "tg"
            assert params["country"] == "2"
            return httpx.Response(
                200,
                json={
                    "activationId": "act-1",
                    "phoneNumber": "15551234567",
                    "countryPhoneCode": "1",
                    "activationEndTime": "2026-07-07T00:00:00Z",
                },
            )
        if params["action"] == "getStatusV2":
            assert params["id"] == "act-1"
            return httpx.Response(200, json={"sms": [{"text": "Your code is 123456"}]})
        if params["action"] == "setStatus":
            assert params["id"] == "act-1"
            assert params["status"] in {"6", "8"}
            return httpx.Response(200, text="ACCESS_READY")
        return httpx.Response(400, json={"error": "BAD_ACTION"})

    adapter = HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            api_key_env="HERO_SMS_API_KEY",
            country="2",
            service="tg",
            otp_timeout_s=1,
            otp_poll_interval_s=1,
        )
    )
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))

    lease = adapter.allocate()
    code = adapter.poll_otp(lease.lease_id)
    adapter.mark_verified(lease.lease_id)
    adapter.mark_failed(lease.lease_id)

    assert lease.lease_id == "act-1"
    assert lease.phone_e164 == "+15551234567"
    assert lease.phone_national == "5551234567"
    assert lease.country_phone_code == "1"
    assert code == "123456"
    assert [dict(request.url.params)["action"] for request in requests] == [
        "getNumberV2",
        "getStatusV2",
        "setStatus",
        "setStatus",
    ]


def test_registration_mail_adapter_lowercases_openai_email_but_keeps_mailbox_email() -> None:
    class FakeMailProvider:
        def __init__(self) -> None:
            self.wait_email = ""
            self.complete_detail = ""
            self.release_reason = ""

        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="3562",
                email="DawnMontgomery148200@outlook.com",
                claim_token="claim-token",
                caller_id="caller",
                task_id="task",
                email_domain="outlook.com",
            )

        def wait_for_otp_by_email(self, *, email: str, **_kwargs) -> OtpMessage:
            self.wait_email = email
            return OtpMessage(code="123456", raw={})

        def claim_complete(self, _claim: ClaimedMailAccount, *, result: str, detail: str):
            self.complete_detail = detail
            return {"success": True, "result": result}

        def claim_release(self, _claim: ClaimedMailAccount, *, reason: str):
            self.release_reason = reason
            return {"success": True}

    provider = FakeMailProvider()
    adapter = RegistrationMailProviderAdapter(
        mail_provider=provider,
        caller_id="caller",
        task_id="task",
        provider="outlook",
        project_key="openai-register",
        email_domain="outlook.com",
    )

    openai_email = adapter.create_mailbox()
    code = adapter.wait_for_otp(openai_email)
    adapter.mark_used(openai_email)
    adapter.mark_unused(openai_email)

    assert openai_email == "dawnmontgomery148200@outlook.com"
    assert code == "123456"
    assert provider.wait_email == "DawnMontgomery148200@outlook.com"
    assert provider.complete_detail == "DawnMontgomery148200@outlook.com"
    assert provider.release_reason == "registration_failed:DawnMontgomery148200@outlook.com"


def test_email_protocol_assigns_account_proxy_before_claiming_mailbox(monkeypatch) -> None:
    order: list[str] = []

    class FakeMailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            order.append("claim_mailbox")
            return ClaimedMailAccount(
                account_id="3866",
                email="JosephStevenson892165@outlook.com",
                claim_token="claim-token",
                caller_id="caller",
                task_id="task",
                email_domain="outlook.com",
            )

        def wait_for_otp_by_email(self, **_kwargs) -> OtpMessage:
            return OtpMessage(code="936493", raw={})

        def claim_complete(self, _claim: ClaimedMailAccount, *, result: str, detail: str):
            order.append("claim_complete")
            return {"success": True, "result": result, "detail": detail}

        def claim_release(self, _claim: ClaimedMailAccount, *, reason: str):
            order.append("claim_release")
            return {"success": True, "reason": reason}

    class TestWorkflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, *, run_id: str, work_id: str, mode: str):
            return lambda stage, data, level="INFO": order.append(f"event:{stage}")

        def _make_claim_persist_callback(self, work_id: str):
            return lambda claim: order.append(f"persist_claim:{claim.email}")

        def _create_placeholder_account(self, *, email: str) -> str:
            order.append(f"create_account:{email}")
            return "protocol-account-1"

        def _set_placeholder_account_email(self, user_account_id: str, email: str) -> None:
            order.append(f"set_email:{email}")

        def _write_success_account(self, *, user_account_id: str, result: AuthResult, flow) -> None:
            order.append("write_success")

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            order.append("delete_account")

    def fake_ensure_account_proxy_url(_session_factory, user_account_id: str, **_kwargs) -> str:
        order.append(f"assign_proxy:{user_account_id}")
        return "http://127.0.0.1:18088"

    class FakeAuthFlow:
        def __init__(self, cfg, trace_callback=None) -> None:
            order.append(f"auth_flow_proxy:{cfg.proxy}")

        def run_register(self, mail: RegistrationMailProviderAdapter) -> AuthResult:
            order.append("run_register")
            email = mail.create_mailbox()
            result = AuthResult()
            result.email = email
            result.session_token = "session-token"
            result.access_token = "access-token"
            return result

    monkeypatch.setattr(protocol_registration, "ensure_account_proxy_url", fake_ensure_account_proxy_url)
    monkeypatch.setattr(protocol_registration, "AuthFlow", FakeAuthFlow)

    workflow = TestWorkflow(session_factory=lambda: None, mail_provider=FakeMailProvider())
    result = workflow.run(
        ProtocolRegistrationInput(mode="email_protocol_no_phone", caller_id="caller", project_key="openai-register"),
        work_id="work-1",
        run_id="run-1",
    )

    assert result["user_account_id"] == "protocol-account-1"
    assert order.index("create_account:") < order.index("assign_proxy:protocol-account-1")
    assert order.index("assign_proxy:protocol-account-1") < order.index("claim_mailbox")
    assert order.index("auth_flow_proxy:http://127.0.0.1:18088") < order.index("claim_mailbox")
    assert "write_success" in order
    assert "claim_complete" in order
    assert "delete_account" not in order
