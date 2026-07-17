from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import refactor_app.application.workflows.protocol_registration as protocol_registration
from refactor_app.application.jobs import handlers
from refactor_app.application.workflows.protocol_registration import (
    HeroSmsPhoneProviderAdapter,
    ProtocolRegistrationInput,
    ProtocolRegistrationWorkflow,
    RegistrationMailProviderAdapter,
    _extract_otp,
    _hero_phone_parts,
)
from refactor_app.config.settings import Settings
from refactor_app.plugins.contracts import OtpMessage
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow, AuthResult
from refactor_app.plugins.openai_auth_protocol.config import Config, PhoneConfig


def test_auth_flow_csrf_retries_cloudflare_403_three_times(monkeypatch) -> None:
    class Response:
        status_code = 403

    class Session:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, *_args, **_kwargs):
            self.calls += 1
            return Response()

    session = Session()
    flow = AuthFlow.__new__(AuthFlow)
    flow.session = session
    flow.result = AuthResult()
    flow.warm_auth_providers = lambda: None
    flow._common_headers = lambda *_args, **_kwargs: {}
    flow._trace_http = lambda *_args, **_kwargs: None
    monkeypatch.setattr(
        "refactor_app.plugins.openai_auth_protocol.auth_flow.time.sleep",
        lambda _seconds: None,
    )

    with pytest.raises(RuntimeError, match="cloudflare_csrf_403_after_3_retries"):
        flow.get_csrf_token()

    assert session.calls == 3


def test_email_registration_reassigns_proxy_after_cloudflare_403(monkeypatch) -> None:
    proxy_urls = ["http://proxy-1.example", "http://proxy-2.example"]
    assigned: list[str] = []
    released: list[dict] = []
    flow_proxies: list[str] = []
    stored_emails: list[str] = []

    class MailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="mail-1",
                email="RetryAccount@example.test",
                claim_token="claim-token",
                caller_id="caller",
                task_id="task",
                email_domain="example.test",
            )

        def claim_complete(self, *_args, **_kwargs):
            return {"success": True}

        def claim_release(self, *_args, **_kwargs):
            return {"success": True}

    class Workflow(ProtocolRegistrationWorkflow):
        def _create_placeholder_account(self, *, email: str) -> str:
            return "account-1"

        def _set_placeholder_account_email(self, user_account_id: str, email: str) -> None:
            return None

        def _write_success_account(self, **kwargs) -> None:
            stored_emails.append(kwargs["account_email"])

        def _detect_account_spaces_after_registration(self, **_kwargs) -> dict:
            return {"accounts_check_succeeded": True}

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            return None

        def _make_event_emitter(self, **_kwargs):
            return lambda *_args, **_event_kwargs: None

        def _make_claim_persist_callback(self, work_id: str):
            return None

        def _merge_work_output(self, work_id: str, patch: dict) -> None:
            return None

    class Flow:
        def __init__(self, cfg, trace_callback=None) -> None:
            self.proxy = cfg.proxy
            self.session = SimpleNamespace(cookies={})
            flow_proxies.append(self.proxy)

        def run_register(self, mail) -> AuthResult:
            email = mail.create_mailbox()
            if len(flow_proxies) == 1:
                raise RuntimeError("cloudflare_csrf_403_after_3_retries")
            result = AuthResult()
            result.email = email
            result.session_token = "session-token"
            result.access_token = "access-token"
            return result

    def assign_proxy(*_args, **_kwargs) -> str:
        proxy = proxy_urls[len(assigned)]
        assigned.append(proxy)
        return proxy

    def release_proxy(*_args, **kwargs) -> str:
        released.append(kwargs)
        return "proxy-1"

    monkeypatch.setattr(protocol_registration, "AuthFlow", Flow)
    monkeypatch.setattr(protocol_registration, "ensure_account_proxy_url", assign_proxy)
    monkeypatch.setattr(
        protocol_registration,
        "release_account_proxy_for_reassign",
        release_proxy,
    )

    result = Workflow(session_factory=lambda: None, mail_provider=MailProvider()).run(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone",
            use_proxy=True,
            caller_id="caller",
            project_key="openai-register",
        ),
        work_id="work-1",
        run_id="run-1",
    )

    assert result["email"] == "retryaccount@example.test"
    assert stored_emails == ["RetryAccount@example.test"]
    assert assigned == proxy_urls
    assert flow_proxies == proxy_urls
    assert released == [
        {
            "error_code": "cloudflare_csrf_403_after_3_retries",
            "error_message": "cloudflare_csrf_403_after_3_retries",
        }
    ]


def test_hero_sms_phone_provider_adapter_lifecycle(monkeypatch) -> None:
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
            countries=[],
            service="tg",
            otp_timeout_s=1,
            otp_poll_interval_s=1,
        ),
        api_key="hero-key",
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


def test_hero_sms_phone_parts_match_legacy_normalization() -> None:
    assert _hero_phone_parts("07123 456789", "44") == (
        "+447123456789",
        "7123456789",
        "44",
    )

    with pytest.raises(protocol_registration.ProtocolRegistrationWorkflowError, match="masked"):
        _hero_phone_parts("+44 7123***89", "44")


def test_hero_sms_countries_override_empty_country_and_service_defaults_to_dr() -> None:
    adapter = HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            service="",
            country="",
            countries=["2", "73"],
        ),
        api_key="hero-key",
    )

    service, countries = adapter._service_countries()

    assert service == "dr"
    assert set(countries) == {"2", "73"}
    assert adapter._max_price("2") == "0.05"


def test_hero_sms_country_defaults_and_single_country_fallback() -> None:
    workflow_input = ProtocolRegistrationInput(mode="phone_protocol_bind_email")
    plugin_config = PhoneConfig()
    job_input = handlers._protocol_registration_input({"mode": "phone_protocol_bind_email"})

    assert workflow_input.phone_country == ""
    assert workflow_input.phone_countries == ["151", "73", "16"]
    assert plugin_config.country == ""
    assert plugin_config.countries == ["151", "73", "16"]
    assert job_input.phone_country == ""
    assert job_input.phone_countries == ["151", "73", "16"]

    single_country_input = handlers._protocol_registration_input(
        {
            "mode": "phone_protocol_bind_email",
            "phone_country": "2",
            "phone_countries": [],
        }
    )
    adapter = HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            country=single_country_input.phone_country,
            countries=single_country_input.phone_countries,
        ),
        api_key="hero-key",
    )

    assert adapter._service_countries() == ("dr", ["2"])


def test_hero_sms_rejects_empty_country_configuration() -> None:
    adapter = HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            country="",
            countries=[],
        ),
        api_key="hero-key",
    )

    with pytest.raises(
        protocol_registration.ProtocolRegistrationWorkflowError,
        match="country must be numeric",
    ):
        adapter._service_countries()


def test_hero_sms_extracts_call_verification_code() -> None:
    assert _extract_otp({"call": {"text": "Your code is 654321"}}) == "654321"


def test_hero_sms_status_retries_transient_http_error(monkeypatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(409, text="TRY_AGAIN")
        return httpx.Response(200, json={"call": {"code": "123456"}})

    adapter = HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            otp_timeout_s=2,
            otp_poll_interval_s=1,
        ),
        api_key="hero-key",
    )
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(protocol_registration.time, "sleep", lambda _seconds: None)

    assert adapter.poll_otp("act-1") == "123456"
    assert calls == 2


def test_hero_sms_otp_timeout_cancel_retries_early_denial(monkeypatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(400, text="EARLY_CANCEL_DENIED")
        return httpx.Response(200, text="ACCESS_CANCEL")

    adapter = HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            cancel_retry_attempts=2,
            cancel_retry_interval_s=1,
        ),
        api_key="hero-key",
    )
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(protocol_registration.time, "sleep", lambda _seconds: None)

    adapter.mark_failed("act-1", "phone_otp_timeout")

    assert calls == 2


def test_phone_protocol_existing_account_fails_without_registration_retry() -> None:
    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.authorize_continue = lambda **_kwargs: {
        "continue_url": "https://auth.openai.com/log-in/password",
        "page": {"type": "login_password", "payload": {}},
    }
    flow._register_proxy_trace = lambda: "proxy=test"

    with pytest.raises(RuntimeError, match="识别为已有账号/登录分支"):
        flow._prepare_phone_protocol_create_password_state("+15551234567", "sentinel")

    assert flow._is_existing_account is True


def test_phone_protocol_existing_account_does_not_allocate_another_number() -> None:
    class ExistingAccountFlow(AuthFlow):
        def check_proxy(self) -> bool:
            return True

        def get_csrf_token(self) -> str:
            return "csrf"

        def get_auth_url(self, *_args, **_kwargs) -> str:
            return "https://auth.openai.com/authorize"

        def auth_oauth_init(self, _auth_url: str) -> str:
            return "device-id"

        def _phone_protocol_password_verify_warmup(self, _phone_e164: str) -> None:
            return None

        def get_sentinel_token(self, _device_id: str) -> str:
            return "sentinel"

        def _prepare_phone_protocol_create_password_state(
            self,
            _phone_e164: str,
            _sentinel_token: str,
        ) -> None:
            raise RuntimeError("existing_phone_account")

    class PhoneProvider:
        cfg = PhoneConfig(max_number_attempts=3, country="2")

        def __init__(self) -> None:
            self.allocate_count = 0
            self.failed: list[tuple[str, str]] = []

        def allocate(self):
            self.allocate_count += 1
            return SimpleNamespace(
                lease_id="act-1",
                phone_e164="+15551234567",
                masked_phone="+155***67",
                phone_national="5551234567",
                country_phone_code="1",
                provider_country="2",
            )

        def mark_failed(self, lease_id: str, reason: str) -> None:
            self.failed.append((lease_id, reason))

    phone = PhoneProvider()
    flow = ExistingAccountFlow(Config())

    with pytest.raises(RuntimeError, match="existing_phone_account"):
        flow.run_phone_register(SimpleNamespace(), phone)

    assert phone.allocate_count == 1
    assert phone.failed == [("act-1", "phone_protocol_failed")]


def test_settings_reads_hero_sms_api_key_without_job_payload(monkeypatch) -> None:
    monkeypatch.setenv("HERO_SMS_API_KEY", "hero-key-from-env")

    assert Settings(_env_file=None).hero_sms_api_key == "hero-key-from-env"


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


def test_registration_mail_adapter_claims_new_mailbox_after_release() -> None:
    claims = [
        ClaimedMailAccount(
            account_id="mail-1",
            email="FirstMailbox@outlook.com",
            claim_token="claim-1",
            caller_id="caller",
            task_id="task",
        ),
        ClaimedMailAccount(
            account_id="mail-2",
            email="SecondMailbox@outlook.com",
            claim_token="claim-2",
            caller_id="caller",
            task_id="task",
        ),
    ]
    released: list[str] = []

    class FakeMailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return claims.pop(0)

        def claim_release(self, claim: ClaimedMailAccount, *, reason: str):
            released.append(f"{claim.account_id}:{reason}")
            return {"success": True}

    adapter = RegistrationMailProviderAdapter(
        mail_provider=FakeMailProvider(),
        caller_id="caller",
        task_id="task",
        provider="outlook",
        project_key="openai-register",
        email_domain="outlook.com",
    )

    first_email = adapter.create_mailbox()
    adapter.mark_unused(first_email)
    second_email = adapter.create_mailbox()

    assert first_email == "firstmailbox@outlook.com"
    assert second_email == "secondmailbox@outlook.com"
    assert released == [
        "mail-1:registration_failed:FirstMailbox@outlook.com",
    ]


def test_phone_email_binding_timeout_rotates_up_to_ten_mailboxes(monkeypatch) -> None:
    monkeypatch.delenv("PHONE_PROTOCOL_MAX_EMAIL_BIND_ATTEMPTS", raising=False)
    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    attempts: list[str] = []
    released: list[str] = []

    class MailProvider:
        def mark_unused(self, email: str) -> None:
            released.append(email)

    def bind_timeout(_mail_provider, *, phone_e164: str) -> str:
        email = f"timeout-{len(attempts) + 1}@example.test"
        attempts.append(phone_e164)
        flow.result.email = email
        raise TimeoutError("mail otp timeout")

    flow._bind_email_protocol_via_platform = bind_timeout

    with pytest.raises(RuntimeError, match="连续 10 个邮箱等待验证码超时"):
        flow._bind_email_protocol_with_retries(
            MailProvider(),
            phone_e164="+15551234567",
        )

    assert len(attempts) == 10
    assert released == [f"timeout-{index}@example.test" for index in range(1, 11)]
    assert flow.result.email == ""


def test_registration_success_persists_claimed_email_case() -> None:
    account = SimpleNamespace()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, _model, _account_id):
            return account

        def commit(self) -> None:
            pass

    result = AuthResult()
    result.email = "dawnmontgomery148200@outlook.com"
    workflow = ProtocolRegistrationWorkflow(
        session_factory=FakeSession,
        mail_provider=object(),
    )

    workflow._write_success_account(
        user_account_id="account-1",
        result=result,
        flow=SimpleNamespace(session=SimpleNamespace(cookies={})),
        account_email="DawnMontgomery148200@outlook.com",
    )

    assert account.email == "DawnMontgomery148200@outlook.com"


def test_icloud_registration_adapter_ignores_email_domain() -> None:
    class FakeMailProvider:
        def __init__(self) -> None:
            self.claim_kwargs = {}
            self.wait_email = ""

        def claim_random(self, **kwargs) -> ClaimedMailAccount:
            self.claim_kwargs = kwargs
            return ClaimedMailAccount(
                account_id="456",
                email="ocelots_plover_3p@icloud.com",
                claim_token="clm_icloud",
                caller_id="caller",
                task_id="task",
                email_domain="icloud.com",
            )

        def wait_for_otp_by_email(self, *, email: str, **_kwargs) -> OtpMessage:
            self.wait_email = email
            return OtpMessage(code="123456", raw={})

    provider = FakeMailProvider()
    adapter = RegistrationMailProviderAdapter(
        mail_provider=provider,
        caller_id="caller",
        task_id="task",
        provider="icloud_hide_my_email",
        project_key="openai-register",
        email_domain="stale.example.com",
    )

    openai_email = adapter.create_mailbox()
    code = adapter.wait_for_otp(openai_email)

    assert openai_email == "ocelots_plover_3p@icloud.com"
    assert code == "123456"
    assert provider.claim_kwargs == {
        "caller_id": "caller",
        "task_id": "task",
        "provider": "icloud_hide_my_email",
        "project_key": "openai-register",
        "email_domain": "",
    }
    assert provider.wait_email == "ocelots_plover_3p@icloud.com"


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

        def _write_success_account(
            self,
            *,
            user_account_id: str,
            result: AuthResult,
            flow,
            account_email: str,
        ) -> None:
            order.append(f"write_success:{account_email}")

        def _detect_account_spaces_after_registration(self, **_kwargs):
            order.append("detect_account_spaces")
            return {
                "accounts_check_succeeded": True,
                "visible_account_ids": ["personal-1"],
                "personal_chatgpt_account_id": "personal-1",
            }

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            order.append("delete_account")

        def _merge_work_output(self, work_id: str, patch: dict) -> None:
            order.append(f"persist_account:{patch.get('user_account_id', '')}")

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

    monkeypatch.setattr(
        protocol_registration, "ensure_account_proxy_url", fake_ensure_account_proxy_url
    )
    monkeypatch.setattr(protocol_registration, "AuthFlow", FakeAuthFlow)

    workflow = TestWorkflow(session_factory=lambda: None, mail_provider=FakeMailProvider())
    result = workflow.run(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone", caller_id="caller", project_key="openai-register"
        ),
        work_id="work-1",
        run_id="run-1",
    )

    assert result["user_account_id"] == "protocol-account-1"
    assert order.index("create_account:") < order.index("assign_proxy:protocol-account-1")
    assert order.index("assign_proxy:protocol-account-1") < order.index("claim_mailbox")
    assert order.index("auth_flow_proxy:http://127.0.0.1:18088") < order.index("claim_mailbox")
    assert "write_success:JosephStevenson892165@outlook.com" in order
    assert "claim_complete" in order
    assert "detect_account_spaces" in order
    assert order.index("write_success:JosephStevenson892165@outlook.com") < order.index(
        "detect_account_spaces"
    )
    assert result["account_detection"]["personal_chatgpt_account_id"] == "personal-1"
    assert "delete_account" not in order


def test_email_browser_reuses_account_proxy_persistence_and_v4(monkeypatch) -> None:
    order: list[str] = []

    class FakeMailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            order.append("claim_mailbox")
            return ClaimedMailAccount(
                account_id="browser-mail-1",
                email="BrowserAccount@outlook.com",
                claim_token="claim-token",
                caller_id="caller",
                task_id="work-1",
            )

        def claim_complete(self, _claim: ClaimedMailAccount, *, result: str, detail: str):
            order.append("claim_complete")
            return {"success": True}

        def claim_release(self, _claim: ClaimedMailAccount, *, reason: str):
            order.append("claim_release")
            return {"success": True}

    class FakeBrowser:
        def __init__(self, config, *, event_callback=None) -> None:
            order.append(f"browser_proxy:{config.proxy_url}")
            assert config.headless is True
            assert config.otp_timeout_s == 180

        def run(self, mail: RegistrationMailProviderAdapter) -> AuthResult:
            email = mail.create_mailbox()
            order.append(f"browser_run:{email}")
            result = AuthResult()
            result.email = email
            result.password = "saved-password"
            result.session_token = "session-token"
            result.access_token = "access-token"
            result.cookie_header = "chatgpt-cookie=value"
            result.auth_cookie_header = "auth-cookie=value"
            return result

    class TestWorkflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, *, run_id: str, work_id: str, mode: str):
            return lambda stage, data, level="INFO": order.append(f"event:{stage}")

        def _make_claim_persist_callback(self, work_id: str):
            return lambda claim: order.append(f"persist_claim:{claim.email}")

        def _create_placeholder_account(self, *, email: str) -> str:
            order.append("create_account")
            return "browser-account-1"

        def _set_placeholder_account_email(self, user_account_id: str, email: str) -> None:
            order.append(f"set_email:{email}")

        def _write_success_account(self, **kwargs) -> None:
            assert kwargs["flow"] is None
            assert kwargs["result"].auth_cookie_header == "auth-cookie=value"
            order.append(f"write_success:{kwargs['account_email']}")

        def _detect_account_spaces_after_registration(self, **kwargs):
            assert kwargs["flow"] is None
            order.append(f"detect_v4:{kwargs['proxy_url']}")
            return {"personal_chatgpt_account_id": "personal-1"}

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            order.append("delete_account")

        def _merge_work_output(self, work_id: str, patch: dict) -> None:
            order.append("persist_account")

    def fake_proxy(_session_factory, user_account_id: str, **_kwargs) -> str:
        order.append(f"assign_proxy:{user_account_id}")
        return "http://browser-proxy.example:8080"

    monkeypatch.setattr(protocol_registration, "CamoufoxEmailRegistration", FakeBrowser)
    monkeypatch.setattr(protocol_registration, "ensure_account_proxy_url", fake_proxy)

    result = TestWorkflow(
        session_factory=lambda: None,
        mail_provider=FakeMailProvider(),
    ).run(
        ProtocolRegistrationInput(
            mode="email_browser_no_phone",
            caller_id="caller",
            project_key="openai-register",
        ),
        work_id="work-1",
        run_id="run-1",
    )

    assert result["mode"] == "email_browser_no_phone"
    assert order.index("create_account") < order.index("assign_proxy:browser-account-1")
    assert order.index("assign_proxy:browser-account-1") < order.index("claim_mailbox")
    assert "write_success:BrowserAccount@outlook.com" in order
    assert "detect_v4:http://browser-proxy.example:8080" in order
    assert "claim_complete" in order
    assert "claim_release" not in order
    assert "delete_account" not in order


def test_email_browser_failure_releases_mail_and_deletes_placeholder(monkeypatch) -> None:
    order: list[str] = []

    class FakeMailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="browser-mail-2",
                email="FailedBrowser@outlook.com",
                claim_token="claim-token",
                caller_id="caller",
                task_id="work-2",
            )

        def claim_release(self, _claim: ClaimedMailAccount, *, reason: str):
            order.append(f"claim_release:{reason}")
            return {"success": True}

    class FakeBrowser:
        def __init__(self, config, *, event_callback=None) -> None:
            pass

        def run(self, mail: RegistrationMailProviderAdapter) -> AuthResult:
            mail.create_mailbox()
            raise RuntimeError("browser failed")

    class TestWorkflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, **_kwargs):
            return lambda stage, data, level="INFO": None

        def _make_claim_persist_callback(self, work_id: str):
            return None

        def _create_placeholder_account(self, *, email: str) -> str:
            return "browser-account-2"

        def _set_placeholder_account_email(self, user_account_id: str, email: str) -> None:
            order.append(f"set_email:{email}")

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            order.append(f"delete_account:{user_account_id}")

        def _merge_work_output(self, work_id: str, patch: dict) -> None:
            pass

    monkeypatch.setattr(protocol_registration, "CamoufoxEmailRegistration", FakeBrowser)
    monkeypatch.setattr(
        protocol_registration,
        "ensure_account_proxy_url",
        lambda *_args, **_kwargs: "http://browser-proxy.example:8080",
    )

    with pytest.raises(RuntimeError, match="browser failed"):
        TestWorkflow(session_factory=lambda: None, mail_provider=FakeMailProvider()).run(
            ProtocolRegistrationInput(mode="email_browser_no_phone"),
            work_id="work-2",
            run_id="run-2",
        )

    assert "set_email:FailedBrowser@outlook.com" in order
    assert "claim_release:registration_failed:FailedBrowser@outlook.com" in order
    assert "delete_account:browser-account-2" in order


def test_registration_job_does_not_inject_global_proxy_override(monkeypatch) -> None:
    queued_inputs: list[dict] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def commit(self) -> None:
            pass

    class FakeWorkQueue:
        def __init__(self, _session) -> None:
            pass

        def enqueue(self, *, input_json: dict, **_kwargs) -> None:
            queued_inputs.append(input_json)

    monkeypatch.setattr(handlers, "WorkQueue", FakeWorkQueue)
    monkeypatch.setattr(
        handlers,
        "_mail_plugin",
        lambda _settings: (_ for _ in ()).throw(AssertionError("pool stats must not block jobs")),
    )
    monkeypatch.setattr(
        handlers,
        "_work_summary",
        lambda **_kwargs: {
            "queued": 1,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
        },
    )

    handlers._run_protocol_register_job(
        session_factory=FakeSession,
        settings=SimpleNamespace(protocol_register_proxy_url="http://global-proxy.example"),
        input_json={
            "mode": "email_browser_no_phone",
            "count": 1,
            "work_count": 1,
            "use_proxy": True,
            "_job_id": "job-1",
            "_run_id": "run-1",
        },
    )

    assert len(queued_inputs) == 1
    assert queued_inputs[0]["mode"] == "email_browser_no_phone"
    assert queued_inputs[0]["use_proxy"] is True
    assert queued_inputs[0]["proxy_url"] == ""


def test_registration_space_detection_reuses_backfill_v4_flow(monkeypatch) -> None:
    captured = {}

    class FakeDetector:
        def __init__(self, **kwargs) -> None:
            captured["init"] = kwargs

        def detect_account_spaces_from_session(self, **kwargs):
            captured["detect"] = kwargs
            return {
                "accounts_check_succeeded": True,
                "visible_account_ids": ["personal-1", "business-1"],
                "personal_chatgpt_account_id": "personal-1",
            }

    class FakeFlow:
        session = SimpleNamespace(cookies={})

    monkeypatch.setattr(protocol_registration, "BackfillSessionWorkflow", FakeDetector)
    result = AuthResult()
    result.access_token = "access-token"
    result.cookie_header = "session-cookie=value"
    result.device_id = "device-1"
    result.chatgpt_account_id = "business-1"
    result.chatgpt_account_structure = "workspace"
    result.chatgpt_account_plan_type = "team"
    workflow = ProtocolRegistrationWorkflow(session_factory=lambda: None, mail_provider=object())

    detection = workflow._detect_account_spaces_after_registration(
        user_account_id="account-1",
        result=result,
        flow=FakeFlow(),
        proxy_url="http://account-proxy.example",
        run_id="run-1",
    )

    assert detection["personal_chatgpt_account_id"] == "personal-1"
    assert captured["detect"] == {
        "user_account_id": "account-1",
        "access_token": "access-token",
        "cookie_header": "session-cookie=value",
        "proxy_url": "http://account-proxy.example",
        "oai_device_id": "device-1",
        "session_chatgpt_account_id": "business-1",
        "session_chatgpt_account_structure": "workspace",
        "session_chatgpt_account_plan_type": "team",
        "require_personal_access_token": False,
        "run_id": "run-1",
    }


def test_auth_flow_registration_does_not_run_codex_oauth() -> None:
    calls: list[str] = []
    auth_url_kwargs: list[dict] = []

    class FakeMailProvider:
        last_persona = None

        def create_mailbox(self) -> str:
            return "registration-only@example.test"

        def wait_for_otp(self, *_args, **_kwargs) -> str:
            return "123456"

    class RegistrationOnlyAuthFlow(AuthFlow):
        def check_proxy(self) -> bool:
            return True

        def get_csrf_token(self) -> str:
            return "csrf"

        def get_auth_url(self, _csrf_token: str, **kwargs) -> str:
            auth_url_kwargs.append(kwargs)
            return "https://auth.example.test/authorize"

        def auth_oauth_init(self, _auth_url: str) -> str:
            return "device-id"

        def get_sentinel_token(self, _device_id: str) -> str:
            return "sentinel"

        def signup(self, _email: str, _sentinel: str) -> bool:
            return True

        def register_password(self, _email: str) -> bool:
            return True

        def send_otp(self) -> None:
            return None

        def verify_otp(self, _code: str) -> dict:
            return {}

        def fetch_client_auth_session_dump(self, stage: str = "") -> dict:
            calls.append(f"dump:{stage}")
            return {}

        def create_account(self) -> str:
            return "https://chatgpt.com/api/auth/callback/openai?code=chatgpt-code"

        def follow_redirect_chain(self, _continue_url: str):
            calls.append("chatgpt_callback")
            return (
                "https://chatgpt.com/api/auth/callback/openai?code=chatgpt-code",
                "https://chatgpt.com/",
            )

        def get_auth_session(self):
            calls.append("chatgpt_session")
            self.result.session_token = "session-token"
            self.result.access_token = "access-token"
            return self.result.session_token, self.result.access_token

        def oauth_token_exchange(self, *_args, **_kwargs) -> bool:
            raise AssertionError("registration must not call oauth_token_exchange")

        def oauth_codex_rt_exchange(self, *_args, **_kwargs) -> bool:
            raise AssertionError("registration must not call oauth_codex_rt_exchange")

        def oauth_secondary_authorize_exchange(self) -> bool:
            raise AssertionError("registration must not call oauth_secondary_authorize_exchange")

    flow = RegistrationOnlyAuthFlow(Config())
    result = flow.run_register(FakeMailProvider())

    assert result.is_valid()
    assert auth_url_kwargs == [{"screen_hint": "signup", "default_prompt": ""}]
    assert calls == [
        "dump:post_verify_otp_new",
        "chatgpt_callback",
        "chatgpt_session",
    ]


def test_registration_signin_query_matches_legacy_password_flow() -> None:
    requested_urls: list[str] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"url": "https://auth.openai.test/authorize"}

    class Session:
        def post(self, url: str, **_kwargs):
            requested_urls.append(url)
            return Response()

    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.session = Session()
    flow._common_headers = lambda *_args, **_kwargs: {}
    flow._trace_http = lambda *_args, **_kwargs: None
    flow._remember_oauth_params = lambda *_args, **_kwargs: None
    flow._inject_pkce_into_auth_url = lambda value: value

    flow.get_auth_url("csrf-token", screen_hint="signup", default_prompt="")

    query = parse_qs(urlparse(requested_urls[0]).query)
    assert query["screen_hint"] == ["signup"]
    assert query["ext-oai-did"] == [flow.result.device_id]
    assert len(query["auth_session_logging_id"]) == 1
    assert "prompt" not in query
    assert "ext-passkey-client-capabilities" not in query


def test_registration_headers_match_legacy_chrome_148_profile() -> None:
    flow = AuthFlow(Config())

    headers = flow._common_headers("https://auth.openai.com/create-account")

    assert "Chrome/148.0.0.0" in headers["User-Agent"]
    assert headers["sec-ch-ua"] == (
        '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"'
    )
    assert "Accept-Encoding" not in headers
    assert "Cache-Control" not in headers
    assert "Pragma" not in headers
