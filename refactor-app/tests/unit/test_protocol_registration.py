from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import refactor_app.application.workflows.protocol_registration as protocol_registration
from refactor_app.application.jobs import handlers
from refactor_app.application.workflows.protocol_registration import (
    HERO_YANDEX_PROVIDER,
    PHONE_BROWSER_BIND_EMAIL,
    HeroSmsLongTermPhoneProviderAdapter,
    HeroSmsPhoneProviderAdapter,
    ProtocolRegistrationInput,
    ProtocolRegistrationWorkflow,
    RegistrationMailProviderAdapter,
    _extract_otp,
    _hero_phone_parts,
    _validate_registration_email_domain,
)
from refactor_app.application.workflows.registration_proxy import CliproxyProxy
from refactor_app.config.browser_fingerprint import (
    BROWSER_SEC_CH_UA,
    BROWSER_SEC_CH_UA_PLATFORM,
    BROWSER_USER_AGENT,
    browser_fingerprint_for_email,
)
from refactor_app.config.settings import Settings
from refactor_app.plugins.contracts import OtpMessage
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.openai_auth_protocol.account_security import (
    AccountSecuritySetupResult,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow, AuthResult
from refactor_app.plugins.openai_auth_protocol.config import Config, PhoneConfig
from refactor_app.plugins.openai_auth_protocol.sentinel_quickjs import (
    create_sentinel_runtime_context,
)


def _proxy_config(country_code: str = "US") -> Config:
    config = Config()
    config.proxy_meta = {"register": {"country_code": country_code}}
    return config


def test_email_protocol_passes_proxy_country_to_sentinel_context(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Flow:
        def __init__(self, config: Config, trace_callback=None) -> None:
            captured["config"] = config
            captured["trace_callback"] = trace_callback

        def run_register(self, mail) -> AuthResult:
            captured["mail"] = mail
            return AuthResult()

    monkeypatch.setattr(protocol_registration, "AuthFlow", Flow)
    workflow = ProtocolRegistrationWorkflow.__new__(ProtocolRegistrationWorkflow)
    mail = SimpleNamespace(claim=SimpleNamespace(email="protocol@example.com"))

    workflow._execute_email_protocol(
        ProtocolRegistrationInput(mode="email_protocol_no_phone", proxy_country="JP"),
        mail=mail,
        user_account_id="account-1",
        work_id="work-1",
        proxy_url="http://proxy.example",
        proxy_mode="trojan_pool_sticky",
        emit=lambda *_args, **_kwargs: None,
    )

    config = captured["config"]
    assert isinstance(config, Config)
    assert config.proxy == "http://proxy.example"
    assert config.proxy_meta["register"]["country_code"] == "JP"
    assert config.proxy_meta["register"]["region"] == "JP"
    assert config.proxy_meta["register"]["mode"] == "trojan_pool_sticky"
    assert config.browser_fingerprint == browser_fingerprint_for_email(
        "protocol@example.com"
    )
    assert captured["mail"] is mail


def test_email_browser_runner_uses_claimed_mailbox_fingerprint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeBrowser:
        def __init__(self, config, *, event_callback):
            captured["config"] = config
            captured["event_callback"] = event_callback

        def run(self, mail, *, totp_code_provider):
            captured["mail"] = mail
            captured["totp_code_provider"] = totp_code_provider
            result = AuthResult()
            result.email = "browser@example.com"
            return result

    mail = SimpleNamespace(claim=SimpleNamespace(email="browser@example.com"))
    monkeypatch.setattr(protocol_registration, "CamoufoxEmailRegistration", FakeBrowser)
    workflow = ProtocolRegistrationWorkflow.__new__(ProtocolRegistrationWorkflow)
    workflow._cloakbrowser_license_key = "cloak-key"
    workflow._totp_code_resolver = None

    workflow._execute_email_browser(
        ProtocolRegistrationInput(mode="email_browser_no_phone", proxy_country="US"),
        mail=mail,
        user_account_id="account-1",
        work_id="work-1",
        proxy_url="http://proxy.example",
        emit=lambda *_args, **_kwargs: None,
    )

    config = captured["config"]
    assert config.browser_fingerprint == browser_fingerprint_for_email(
        "browser@example.com"
    )
    assert captured["mail"] is mail


def test_hero_gmail_rejects_fixed_email() -> None:
    workflow = ProtocolRegistrationWorkflow(
        session_factory=lambda: None,  # type: ignore[return-value]
        mail_provider=object(),  # type: ignore[arg-type]
    )
    with pytest.raises(
        protocol_registration.ProtocolRegistrationWorkflowError,
        match="fixed_email is not supported",
    ):
        workflow.run(
            ProtocolRegistrationInput(
                mode="email_protocol_no_phone",
                mail_provider="hero_gmail",
                fixed_email="existing@gmail.com",
            )
        )


def test_hero_yandex_rejects_fixed_email() -> None:
    workflow = ProtocolRegistrationWorkflow(
        session_factory=lambda: None,  # type: ignore[return-value]
        mail_provider=object(),  # type: ignore[arg-type]
    )
    with pytest.raises(
        protocol_registration.ProtocolRegistrationWorkflowError,
        match="fixed_email is not supported",
    ):
        workflow.run(
            ProtocolRegistrationInput(
                mode="email_protocol_no_phone",
                mail_provider=HERO_YANDEX_PROVIDER,
                fixed_email="existing@yandex.ru",
            )
        )


def test_yandex_dot_com_is_temporarily_disabled() -> None:
    with pytest.raises(
        protocol_registration.ProtocolRegistrationWorkflowError,
        match="temporarily disabled: yandex.com",
    ):
        _validate_registration_email_domain("new.user@yandex.com")


def test_non_yandex_email_domain_is_accepted() -> None:
    assert _validate_registration_email_domain("new.user@example.com") is None


def test_yandex_claim_uses_configured_proxy_route() -> None:
    captured: dict[str, object] = {}

    class MailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="hero-email:tr",
                email="new.user@yandex.com.tr",
                claim_token="tr",
                caller_id="caller",
                task_id="work-yandex-tr",
            )

        def claim_complete(self, _claim, *, result: str, detail: str):
            return {"success": True, "result": result, "detail": detail}

        def claim_release(self, *_args, **_kwargs):
            return {"success": True}

    class Workflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, **_kwargs):
            return lambda stage, data, level="INFO": captured.setdefault(
                stage, {"data": data, "level": level}
            )

        def _make_claim_persist_callback(self, _work_id: str):
            return None

        def _create_placeholder_account(self, *, email: str) -> str:
            return "account-yandex-tr"

        def _merge_work_output(self, _work_id: str, _patch: dict) -> None:
            return None

        def _resolve_registration_proxy(self, **kwargs) -> CliproxyProxy:
            captured["proxy_request"] = kwargs
            return CliproxyProxy(
                proxy_url="http://proxy.example",
                country_code=kwargs["country_code"],
            )

        def _detect_account_spaces_after_registration(self, **_kwargs):
            return {"accounts_check_succeeded": True}

        def _run_post_registration_security(self, *_args, **_kwargs):
            return AccountSecuritySetupResult(
                password_status="configured",
                password_value_confirmed=True,
                mfa_status="configured",
                twofauth_account_id="twofauth-tr",
            )

        def _write_success_account(self, **_kwargs) -> None:
            return None

        def _run_post_registration_promotion_check(self, input_, **kwargs):
            captured["promotion_input_country"] = input_.proxy_country
            captured["promotion_proxy_country"] = kwargs["registration_proxy"].country_code
            return None

        def _run_post_registration_codex_authorization(self, *_args, **_kwargs):
            return None

        def _delete_placeholder_account(self, _user_account_id: str) -> None:
            return None

    def runner(input_, **kwargs):
        captured["runner_input"] = input_
        result = AuthResult()
        result.email = "new.user@yandex.com.tr"
        result.password_configured = True
        result.session_token = "session-token"
        result.access_token = "access-token"
        return protocol_registration._RegistrationAttempt(
            result=result,
            flow=None,
            proxy_url=kwargs["proxy_url"],
            proxy_country=input_.proxy_country,
        )

    output = Workflow(
        session_factory=lambda: None,
        mail_provider=MailProvider(),
    )._run_registration_lifecycle(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone",
            mail_provider=HERO_YANDEX_PROVIDER,
            proxy_country="US",
            proxy_state="California",
        ),
        mode="email_protocol_no_phone",
        work_id="work-yandex-tr",
        run_id="run-yandex-tr",
        runner=runner,
    )

    assert captured["proxy_request"] == {
        "target_email": "new.user@yandex.com.tr",
        "country_code": "US",
        "state": "California",
    }
    assert captured["runner_input"].proxy_country == "US"
    assert captured["runner_input"].proxy_state == "California"
    assert captured["promotion_input_country"] == "US"
    assert captured["promotion_proxy_country"] == "US"
    assert "proxy.country_selected_from_email" not in captured
    assert output["proxy_country"] == "US"


def test_hero_gmail_resume_claim_is_scoped_to_the_same_run() -> None:
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, _model, work_id: str):
            assert work_id == "work-1"
            return SimpleNamespace(
                output_json={
                    "mail_claim_run_id": "run-1",
                    "mail_claim": {
                        "account_id": "hero-email:2770475",
                        "email": "new.user@gmail.com",
                        "email_domain": "gmail.com",
                        "claim_token": "2770475",
                        "caller_id": "caller",
                        "task_id": "work-1",
                    },
                }
            )

    claim = handlers._registration_resume_mail_claim(
        session_factory=Session,
        input_json={
            "mail_provider": "hero_gmail",
            "_work_id": "work-1",
            "_run_id": "run-1",
        },
    )
    assert claim is not None
    assert claim.email == "new.user@gmail.com"
    assert claim.claim_token == "2770475"

    assert (
        handlers._registration_resume_mail_claim(
            session_factory=Session,
            input_json={
                "mail_provider": "hero_gmail",
                "_work_id": "work-1",
                "_run_id": "retry-run",
            },
        )
        is None
    )


def test_hero_yandex_resume_claim_preserves_provider_and_suffix() -> None:
    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, _model, _work_id: str):
            return SimpleNamespace(
                output_json={
                    "mail_claim_run_id": "run-yandex",
                    "mail_claim": {
                        "account_id": "hero-email:7001",
                        "email": "new.user@yandex.com.tr",
                        "email_domain": "yandex.com.tr",
                        "claim_token": "7001",
                    },
                }
            )

    claim = handlers._registration_resume_mail_claim(
        session_factory=Session,
        input_json={
            "mail_provider": HERO_YANDEX_PROVIDER,
            "_work_id": "work-yandex",
            "_run_id": "run-yandex",
        },
    )
    assert claim is not None
    assert claim.email_domain == "yandex.com.tr"
    assert claim.raw["provider"] == HERO_YANDEX_PROVIDER


def test_registration_proxy_resolver_receives_state_or_asn(monkeypatch) -> None:
    calls: list[dict[str, str]] = []

    def resolve_proxy(**kwargs):
        calls.append(dict(kwargs))
        return CliproxyProxy(proxy_url="http://proxy.example", country_code="US")

    monkeypatch.setattr(protocol_registration, "resolve_cliproxy_proxy", resolve_proxy)
    workflow = ProtocolRegistrationWorkflow.__new__(ProtocolRegistrationWorkflow)

    workflow._resolve_registration_proxy(
        target_email="state@example.test",
        country_code="US",
        state="California",
    )
    workflow._resolve_registration_proxy(
        target_email="asn@example.test",
        country_code="US",
        asn="AS33363",
    )

    assert calls == [
        {
            "email": "state@example.test",
            "country_code": "US",
            "state": "California",
        },
        {
            "email": "asn@example.test",
            "country_code": "US",
            "asn": "AS33363",
        },
    ]


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


def test_email_registration_keeps_hashed_proxy_after_cloudflare_403(monkeypatch) -> None:
    proxy_url = "http://proxy-1.example"
    assigned: list[tuple[str, str]] = []
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
            raise RuntimeError(f"cloudflare_csrf_403_after_3_retries:{email}")

    def resolve_proxy(*, email: str, country_code: str):
        assigned.append((email, country_code))
        return CliproxyProxy(
            proxy_url=proxy_url,
            country_code="US",
        )

    monkeypatch.setattr(protocol_registration, "AuthFlow", Flow)
    monkeypatch.setattr(
        protocol_registration,
        "resolve_cliproxy_proxy",
        resolve_proxy,
    )

    with pytest.raises(RuntimeError, match="cloudflare_csrf_403_after_3_retries"):
        Workflow(session_factory=lambda: None, mail_provider=MailProvider()).run(
            ProtocolRegistrationInput(
                mode="email_protocol_no_phone",
                caller_id="caller",
                project_key="openai-register",
            ),
            work_id="work-1",
            run_id="run-1",
        )

    assert stored_emails == []
    assert assigned == [("RetryAccount@example.test", "US")]
    assert flow_proxies == [proxy_url]


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


def _longterm_phone_config(**overrides) -> PhoneConfig:
    values = {
        "enabled": True,
        "provider": "hero_sms",
        "base_url": "https://hero-sms.com/stubs/handler_api.php",
        "service": "ts",
        "country": "187",
        "otp_timeout_s": 2,
        "otp_poll_interval_s": 1,
    }
    values.update(overrides)
    return PhoneConfig(**values)


def test_hero_sms_longterm_reuses_active_us_activation_without_lifecycle_mutation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        params = dict(request.url.params)
        assert params["api_key"] == "hero-key"
        if params["action"] == "getActiveActivations":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {
                            "activationId": "rent-1",
                            "serviceCode": "ts",
                            "countryCode": "187",
                            "phoneNumber": "15717256466",
                            "activationStatus": "2",
                            "activationEndTime": "2099-08-16T13:35:25+00:00",
                        }
                    ],
                },
            )
        if params["action"] == "getAllSms":
            assert params["id"] == "rent-1"
            return httpx.Response(
                200,
                json={"data": [{"id": "old-1", "code": "123456", "text": "old"}]},
            )
        return httpx.Response(400, json={"error": "BAD_ACTION"})

    adapter = HeroSmsLongTermPhoneProviderAdapter(
        _longterm_phone_config(),
        api_key="hero-key",
    )
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        lease = adapter.allocate()
        adapter.mark_verified(lease.lease_id)
        adapter.mark_failed(lease.lease_id, "retry")
    finally:
        adapter.close()

    assert lease.lease_id == "rent-1"
    assert lease.phone_e164 == "+15717256466"
    assert lease.phone_national == "5717256466"
    assert lease.country_phone_code == "1"
    assert [dict(request.url.params)["action"] for request in requests] == [
        "getActiveActivations",
        "getActiveActivations",
        "getAllSms",
    ]


def test_hero_sms_longterm_repeated_allocate_refreshes_baseline_without_relocking() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        action = dict(request.url.params)["action"]
        if action == "getActiveActivations":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "activationId": "rent-1",
                            "serviceCode": "ts",
                            "countryCode": 187,
                            "phoneNumber": "+15717256466",
                            "activationStatus": "2",
                        }
                    ]
                },
            )
        assert action == "getAllSms"
        return httpx.Response(200, json={"data": [{"id": f"msg-{calls}"}]})

    adapter = HeroSmsLongTermPhoneProviderAdapter(_longterm_phone_config(), api_key="hero-key")
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        first = adapter.allocate()
        second = adapter.allocate()
    finally:
        adapter.close()

    assert first == second
    assert calls == 4


def test_hero_sms_longterm_accepts_active_activations_response_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        action = dict(request.url.params)["action"]
        if action == "getActiveActivations":
            return httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": [
                        {
                            "activationId": "rent-active-field",
                            "service": "paypal",
                            "country": "US",
                            "phoneNumber": "15717256466",
                            "activationStatus": "2",
                            "estDate": "2099-08-16 13:35:25",
                        }
                    ],
                    "activeActivations": {
                        "affected_rows": 1,
                        "num_rows": 1,
                        "rows": [],
                    },
                },
            )
        assert action == "getAllSms"
        return httpx.Response(200, json={"data": []})

    adapter = HeroSmsLongTermPhoneProviderAdapter(_longterm_phone_config(), api_key="hero-key")
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        lease = adapter.allocate()
    finally:
        adapter.close()

    assert lease.lease_id == "rent-active-field"
    assert lease.expires_at == "2099-08-16 13:35:25"


def test_hero_sms_longterm_skips_locked_activation_and_uses_another_random_candidate() -> None:
    active = [
        {
            "activationId": "rent-1",
            "serviceCode": "ts",
            "countryCode": "187",
            "phoneNumber": "15717256465",
            "activationStatus": "2",
        },
        {
            "activationId": "rent-2",
            "serviceCode": "paypal",
            "countryCode": "US",
            "phoneNumber": "15717256466",
            "activationStatus": "2",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params["action"] == "getActiveActivations":
            return httpx.Response(200, json={"data": active})
        assert params["action"] == "getAllSms"
        return httpx.Response(200, json={"data": []})

    first = HeroSmsLongTermPhoneProviderAdapter(_longterm_phone_config(), api_key="hero-key")
    second = HeroSmsLongTermPhoneProviderAdapter(_longterm_phone_config(), api_key="hero-key")
    first._client = httpx.Client(transport=httpx.MockTransport(handler))
    second._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        first_lease = first.allocate()
        second_lease = second.allocate()
        assert second_lease.lease_id != first_lease.lease_id
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize(
    ("active_data", "message"),
    [
        ([], "active activation not found"),
        (
            [
                {
                    "activationId": "rent-1",
                    "serviceCode": "ts",
                    "countryCode": "187",
                    "phoneNumber": "15717***66",
                    "activationStatus": "2",
                }
            ],
            "masked phone number",
        ),
        (
            [
                {
                    "activationId": "rent-1",
                    "serviceCode": "ts",
                    "countryCode": "187",
                    "phoneNumber": "15717256466",
                    "activationStatus": "2",
                    "activationEndTime": "2020-01-01T00:00:00Z",
                }
            ],
            "expired",
        ),
    ],
)
def test_hero_sms_longterm_selection_errors_are_explicit(active_data, message) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params)["action"] == "getActiveActivations"
        return httpx.Response(200, json={"status": "success", "data": active_data})

    adapter = HeroSmsLongTermPhoneProviderAdapter(_longterm_phone_config(), api_key="hero-key")
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(protocol_registration.ProtocolRegistrationWorkflowError, match=message):
            adapter.allocate()
    finally:
        adapter.close()


def test_hero_sms_longterm_optional_activation_id_filters_candidates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        action = dict(request.url.params)["action"]
        if action == "getActiveActivations":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "activationId": "rent-1",
                            "serviceCode": "ts",
                            "countryCode": "187",
                            "phoneNumber": "15717256465",
                            "activationStatus": "2",
                        },
                        {
                            "activationId": "rent-2",
                            "serviceCode": "ts",
                            "countryCode": "187",
                            "phoneNumber": "15717256466",
                            "activationStatus": "2",
                        },
                    ]
                },
            )
        assert action == "getAllSms"
        return httpx.Response(200, json={"data": []})

    adapter = HeroSmsLongTermPhoneProviderAdapter(
        _longterm_phone_config(), api_key="hero-key", activation_id="rent-2"
    )
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        lease = adapter.allocate()
    finally:
        adapter.close()

    assert lease.lease_id == "rent-2"


def test_hero_sms_longterm_ignores_history_and_non_code_until_new_six_digit_otp(
    monkeypatch,
) -> None:
    poll_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal poll_count
        action = dict(request.url.params)["action"]
        if action == "getActiveActivations":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "activationId": "rent-1",
                            "serviceCode": "ts",
                            "countryCode": "187",
                            "phoneNumber": "15717256466",
                            "activationStatus": "2",
                        }
                    ]
                },
            )
        assert action == "getAllSms"
        poll_count += 1
        if poll_count == 1:
            return httpx.Response(
                200,
                json={"data": [{"id": "old", "text": "PayPal code 111111"}]},
            )
        if poll_count == 2:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "old", "text": "PayPal code 111111"},
                        {"id": "noise", "text": "Welcome"},
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "old", "text": "PayPal code 111111"},
                    {"id": "noise", "text": "Welcome"},
                    {
                        "id": "delayed-old",
                        "service": "ts",
                        "date": "2020-01-01T00:00:00Z",
                        "text": "PayPal verification code: 222222",
                    },
                    {
                        "id": "new",
                        "service": "ts",
                        "date": "2099-01-01T00:00:00Z",
                        "text": "PayPal verification code: 654321",
                    },
                ]
            },
        )

    adapter = HeroSmsLongTermPhoneProviderAdapter(_longterm_phone_config(), api_key="hero-key")
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(protocol_registration.time, "sleep", lambda _seconds: None)
    try:
        adapter.allocate()
        adapter.prepare_otp("rent-1")
        assert adapter.poll_otp("rent-1") == "654321"
    finally:
        adapter.close()


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
    assert workflow_input.phone_countries == ["187"]
    assert plugin_config.country == ""
    assert plugin_config.countries == ["151", "73", "16"]
    assert job_input.phone_country == ""
    assert job_input.phone_countries == ["187"]

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


def test_phone_browser_runner_uses_claimed_mail_and_closes_phone_provider(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePhone:
        def __init__(self, cfg, *, api_key, event_callback):
            captured["phone_cfg"] = cfg
            captured["phone_api_key"] = api_key
            captured["phone_event_callback"] = event_callback

        def close(self) -> None:
            captured["phone_closed"] = True

    class FakeBrowser:
        def __init__(self, config, *, event_callback):
            captured["browser_config"] = config
            captured["browser_event_callback"] = event_callback

        def run(self, mail, phone, *, email, totp_code_provider):
            captured.update(
                {
                    "mail": mail,
                    "phone": phone,
                    "email": email,
                    "totp_code_provider": totp_code_provider,
                }
            )
            result = AuthResult()
            result.email = email
            result.session_token = "session"
            result.access_token = "access"
            result.password_configured = True
            return result

    class Mail:
        claim = SimpleNamespace(email="claimed@yandex.fi")

    monkeypatch.setattr(protocol_registration, "HeroSmsPhoneProviderAdapter", FakePhone)
    monkeypatch.setattr(protocol_registration, "BrowserPhoneEmailRegistration", FakeBrowser)

    workflow = ProtocolRegistrationWorkflow.__new__(ProtocolRegistrationWorkflow)
    workflow._hero_sms_api_key = "grizzly-key"
    workflow._cloakbrowser_license_key = "cloak-key"
    workflow._totp_code_resolver = lambda account_id: f"otp:{account_id}"

    attempt = workflow._execute_phone_browser(
        ProtocolRegistrationInput(
            mode=PHONE_BROWSER_BIND_EMAIL,
            proxy_country="FI",
            browser_backend="cloakbrowser",
            phone_country="187",
        ),
        mail=Mail(),
        user_account_id="account-1",
        work_id="work-1",
        proxy_url="http://proxy.example",
        emit=lambda *_args, **_kwargs: None,
    )

    assert attempt.flow is None
    assert attempt.proxy_url == "http://proxy.example"
    assert attempt.proxy_country == "FI"
    assert captured["email"] == "claimed@yandex.fi"
    assert captured["phone_api_key"] == "grizzly-key"
    assert captured["phone_closed"] is True
    config = captured["browser_config"]
    assert config.proxy_url == "http://proxy.example"
    assert config.locale
    assert config.browser_backend == "cloakbrowser"
    assert config.browser_fingerprint == browser_fingerprint_for_email(
        "claimed@yandex.fi"
    )
    assert captured["totp_code_provider"]() == "otp:account-1"


def test_phone_protocol_runner_uses_claimed_mailbox_fingerprint(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePhone:
        def __init__(self, config, *, api_key, event_callback):
            captured["phone_config"] = config
            captured["phone_api_key"] = api_key
            captured["phone_event_callback"] = event_callback

    class FakeFlow:
        def __init__(self, config, *, trace_callback):
            captured["config"] = config
            captured["trace_callback"] = trace_callback

        def run_phone_register(self, mail, phone):
            captured["mail"] = mail
            captured["phone"] = phone
            return AuthResult()

    monkeypatch.setattr(protocol_registration, "HeroSmsPhoneProviderAdapter", FakePhone)
    monkeypatch.setattr(protocol_registration, "AuthFlow", FakeFlow)
    workflow = ProtocolRegistrationWorkflow.__new__(ProtocolRegistrationWorkflow)
    workflow._hero_sms_api_key = "hero-key"
    workflow._make_http_trace_callback = lambda _emit: None
    mail = SimpleNamespace(claim=SimpleNamespace(email="phone-protocol@example.com"))

    workflow._execute_phone_protocol(
        ProtocolRegistrationInput(mode="phone_protocol", proxy_country="US"),
        mail=mail,
        user_account_id="account-1",
        work_id="work-1",
        proxy_url="http://proxy.example",
        emit=lambda *_args, **_kwargs: None,
    )

    config = captured["config"]
    assert config.browser_fingerprint == browser_fingerprint_for_email(
        "phone-protocol@example.com"
    )
    assert captured["mail"] is mail


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
    flow = ExistingAccountFlow(_proxy_config())

    with pytest.raises(RuntimeError, match="existing_phone_account"):
        flow.run_phone_register(SimpleNamespace(), phone)

    assert phone.allocate_count == 1
    assert phone.failed == [("act-1", "phone_protocol_failed")]


def test_settings_reads_hero_sms_api_key_without_job_payload(monkeypatch) -> None:
    monkeypatch.setenv("HERO_SMS_API_KEY", "hero-key-from-env")

    assert Settings(_env_file=None).hero_sms_api_key == "hero-key-from-env"


def test_settings_reads_grizzly_sms_api_key_without_job_payload(monkeypatch) -> None:
    monkeypatch.setenv("GRIZZLY_SMS_API_KEY", "grizzly-key-from-env")

    settings = Settings(_env_file=None)

    assert settings.grizzly_sms_api_key == "grizzly-key-from-env"
    assert settings.grizzly_sms_base_url == ("https://api.grizzlysms.com/stubs/handler_api.php")
    assert settings.grizzly_sms_service == "dr"
    assert settings.grizzly_sms_country == "187"
    assert settings.grizzly_sms_max_price == "0.18"


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


def test_browser_registration_external_mail_reads_subject_otp_from_all_fields() -> None:
    captured: dict[str, object] = {}

    class FakeMailProvider:
        @staticmethod
        def claim_random(**_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="mail-subject-code",
                email="SubjectCode@outlook.com",
                claim_token="claim-subject-code",
                caller_id="caller",
                task_id="task",
                email_domain="outlook.com",
            )

        @staticmethod
        def wait_for_otp_by_email(**kwargs) -> OtpMessage:
            captured.update(kwargs)
            if kwargs.get("code_source") != "all":
                raise TimeoutError("OTP exists only in the message subject")
            return OtpMessage(
                code="482951",
                raw={
                    "data": {
                        "subject": "Your ChatGPT verification code is 482951",
                        "content": "",
                        "html": "",
                        "matched_source": "subject",
                    }
                },
            )

    adapter = RegistrationMailProviderAdapter(
        mail_provider=FakeMailProvider(),  # type: ignore[arg-type]
        caller_id="caller",
        task_id="task",
        provider="outlook",
        project_key="openai-register",
        email_domain="outlook.com",
        otp_code_source="all",
    )

    email = adapter.create_mailbox()
    code = adapter.wait_for_otp(email, timeout=90, issued_after=123.0, max_polls=4)

    assert code == "482951"
    assert captured == {
        "email": "SubjectCode@outlook.com",
        "timeout_s": 90,
        "issued_after": 123.0,
        "max_polls": 4,
        "code_source": "all",
    }


def test_registration_otp_code_source_is_content_for_every_registration_path() -> None:
    for mode, mail_provider in (
        ("email_browser_no_phone", "outlook"),
        ("email_browser_no_phone", "cloudflare_temp_mail"),
        ("email_protocol_no_phone", "outlook"),
        ("email_browser_no_phone", "hero_gmail"),
    ):
        assert (
            protocol_registration.registration_otp_code_source(
                mode=mode,
                mail_provider=mail_provider,
            )
            == "content"
        )


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


def test_registration_mail_adapter_fixed_email_uses_verification_api_without_claiming() -> None:
    calls: list[str] = []

    class FakeMailProvider:
        def claim_random(self, **_kwargs):
            calls.append("claim_random")
            raise AssertionError("fixed email must not claim a remote mailbox")

        def wait_for_otp_by_email(self, *, email: str, **_kwargs) -> OtpMessage:
            calls.append(f"wait:{email}")
            return OtpMessage(code="654321", raw={})

        def claim_complete(self, *_args, **_kwargs):
            calls.append("claim_complete")

        def claim_release(self, *_args, **_kwargs):
            calls.append("claim_release")

    adapter = RegistrationMailProviderAdapter(
        mail_provider=FakeMailProvider(),  # type: ignore[arg-type]
        caller_id="space-auto-replenish",
        task_id="work-1",
        provider="outlook",
        project_key="space-auto-replenish",
        email_domain="",
        fixed_email="MixedCaseMailbox@outlook.com",
    )

    email = adapter.create_mailbox()
    code = adapter.wait_for_otp(email)
    adapter.mark_used(email)
    adapter.mark_unused(email)

    assert email == "MixedCaseMailbox@outlook.com"
    assert code == "654321"
    assert calls == ["wait:MixedCaseMailbox@outlook.com"]


def test_registration_mail_adapter_ensures_fixed_domain_mail_before_returning_it() -> None:
    calls: list[str] = []

    class FakeMailProvider:
        def ensure_domain_email(self, *, email: str) -> dict:
            calls.append(f"ensure:{email}")
            return {"email": email}

    adapter = RegistrationMailProviderAdapter(
        mail_provider=FakeMailProvider(),  # type: ignore[arg-type]
        caller_id="space-auto-replenish",
        task_id="work-1",
        provider="cloudflare_temp_mail",
        project_key="space-auto-replenish",
        email_domain="boluodadaxyz.xyz",
        fixed_email="Worker@boluodadaxyz.xyz",
    )

    email = adapter.create_mailbox()

    assert email == "Worker@boluodadaxyz.xyz"
    assert calls == ["ensure:Worker@boluodadaxyz.xyz"]


def test_registration_mail_adapter_creates_fresh_temp_mailbox_without_pool_claim(
    monkeypatch,
) -> None:
    calls: list[str] = []
    events: list[str] = []

    class FakeMailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            raise AssertionError("temporary mailbox must not use pool claim")

        def ensure_domain_email(self, *, email: str) -> dict:
            calls.append(f"ensure:{email}")
            return {"email": email, "ensured": True}

        def wait_for_otp_by_email(self, *, email: str, **_kwargs) -> OtpMessage:
            calls.append(f"wait:{email}")
            return OtpMessage(code="123456", raw={})

    monkeypatch.setattr(
        protocol_registration,
        "uuid4",
        lambda: SimpleNamespace(hex="freshmailbox0000000000"),
    )

    adapter = RegistrationMailProviderAdapter(
        mail_provider=FakeMailProvider(),  # type: ignore[arg-type]
        caller_id="caller",
        task_id="task",
        provider="cloudflare_temp_mail",
        project_key="openai-register",
        email_domain="wangzi.xyz",
        event_callback=lambda stage, _data, _level="INFO": events.append(stage),
    )

    email = adapter.create_mailbox()
    code = adapter.wait_for_otp(email)
    adapter.mark_used(email)

    assert email == "freshmailbox@wangzi.xyz"
    assert code == "123456"
    assert calls == [
        "ensure:freshmailbox@wangzi.xyz",
        "wait:freshmailbox@wangzi.xyz",
    ]
    assert "mail.claim.started" not in events
    assert "mail.ensure.started" not in events
    assert events == [
        "mail.create.started",
        "mail.create.succeeded",
        "mail.otp.wait.started",
        "mail.otp.wait.succeeded",
    ]


def test_registration_mail_adapter_creates_another_temp_mail_after_failure(monkeypatch) -> None:
    identifiers = iter(["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"])
    calls: list[str] = []

    class FakeMailProvider:
        def ensure_domain_email(self, *, email: str) -> dict:
            calls.append(f"ensure:{email}")
            return {"email": email, "ensured": True}

    monkeypatch.setattr(
        protocol_registration,
        "uuid4",
        lambda: SimpleNamespace(hex=next(identifiers)),
    )

    adapter = RegistrationMailProviderAdapter(
        mail_provider=FakeMailProvider(),  # type: ignore[arg-type]
        caller_id="caller",
        task_id="task",
        provider="cloudflare_temp_mail",
        project_key="openai-register",
        email_domain="wangzi.xyz",
    )

    first_email = adapter.create_mailbox()
    adapter.mark_unused(first_email)
    second_email = adapter.create_mailbox()

    assert first_email == "aaaaaaaaaaaa@wangzi.xyz"
    assert second_email == "bbbbbbbbbbbb@wangzi.xyz"
    assert calls == [
        "ensure:aaaaaaaaaaaa@wangzi.xyz",
        "ensure:bbbbbbbbbbbb@wangzi.xyz",
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
    account = SimpleNamespace(access_token="validated-personal-access-token")

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
    assert account.access_token == "validated-personal-access-token"


def test_registration_does_not_persist_password_when_security_setup_failed() -> None:
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
    result.email = "icloud-user@example.test"
    result.password = "candidate-password"
    result.session_token = "session-token"
    workflow = ProtocolRegistrationWorkflow(
        session_factory=FakeSession,
        mail_provider=object(),
    )

    workflow._write_success_account(
        user_account_id="account-1",
        result=result,
        flow=SimpleNamespace(session=SimpleNamespace(cookies={})),
        account_email=result.email,
        security_setup=AccountSecuritySetupResult(
            password_status="failed",
            password_error_code="password_setup_failed",
            password_error_message="password setup failed",
            mfa_status="failed",
            mfa_error_code="mfa_setup_failed",
            mfa_error_message="MFA setup failed",
        ),
    )

    assert account.account_status == "active"
    assert account.session_status == "active"
    assert account.password == ""
    assert account.password_status == "failed"
    assert account.password_last_error_code == "password_setup_failed"
    assert account.mfa_status == "failed"
    assert account.mfa_last_error_code == "mfa_setup_failed"
    assert account.security_setup_last_attempt_at is not None


def test_registration_persists_only_a_confirmed_configured_password() -> None:
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
    result.email = "icloud-user@example.test"
    result.password = "configured-password"
    workflow = ProtocolRegistrationWorkflow(
        session_factory=FakeSession,
        mail_provider=object(),
    )

    workflow._write_success_account(
        user_account_id="account-1",
        result=result,
        flow=SimpleNamespace(session=SimpleNamespace(cookies={})),
        account_email=result.email,
        security_setup=AccountSecuritySetupResult(
            password_status="configured",
            password_value_confirmed=True,
            mfa_status="configured",
            twofauth_account_id="twofauth-42",
        ),
    )

    assert account.password == "configured-password"
    assert account.password_status == "configured"
    assert account.mfa_status == "configured"
    assert account.twofauth_account_id == "twofauth-42"


def test_icloud_security_exception_keeps_registration_successful(monkeypatch) -> None:
    events: list[tuple[str, str]] = []
    persisted: dict = {}
    calls: dict = {}

    class FakeMailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="icloud-mail-1",
                email="icloud-user@example.test",
                claim_token="claim-token",
                caller_id="caller",
                task_id="work-icloud",
                email_domain="example.test",
            )

        def claim_complete(self, _claim, *, result: str, detail: str):
            calls["claim_complete"] = (result, detail)
            return {"success": True}

        def claim_release(self, *_args, **_kwargs):
            calls["claim_release"] = True
            return {"success": True}

    class FakeAuthFlow:
        def __init__(self, _cfg, trace_callback=None) -> None:
            self.session = SimpleNamespace(
                cookies=[
                    SimpleNamespace(
                        name="auth-session",
                        value="auth-cookie-value",
                        domain="auth.openai.com",
                    )
                ]
            )

        def run_register(self, mail) -> AuthResult:
            result = AuthResult()
            result.email = mail.create_mailbox()
            result.password = "candidate-password"
            result.password_configured = True
            result.session_token = "session-token"
            result.access_token = "access-token"
            result.cookie_header = "__Secure-next-auth.session-token=session-token"
            return result

    class FailingSecurity:
        def __init__(self, config, *, event_callback=None) -> None:
            calls["security_config"] = config

        def run(self, **kwargs):
            calls["security_run"] = kwargs
            raise RuntimeError("security setup failed")

    class Workflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, **_kwargs):
            return lambda stage, _data, level="INFO": events.append((stage, level))

        def _make_claim_persist_callback(self, _work_id: str):
            return None

        def _create_placeholder_account(self, *, email: str) -> str:
            return "account-icloud"

        def _set_placeholder_account_email(self, _user_account_id: str, _email: str) -> None:
            return None

        def _merge_work_output(self, _work_id: str, _patch: dict) -> None:
            return None

        def _write_success_account(self, **kwargs) -> None:
            persisted.update(kwargs)

        def _detect_account_spaces_after_registration(self, **_kwargs) -> dict:
            return {"accounts_check_succeeded": True}

        def _delete_placeholder_account(self, _user_account_id: str) -> None:
            calls["delete_placeholder"] = True

    twofauth_client = object()
    monkeypatch.setattr(protocol_registration, "AuthFlow", FakeAuthFlow)
    monkeypatch.setattr(protocol_registration, "ProtocolAccountSecurity", FailingSecurity)
    monkeypatch.setattr(
        protocol_registration,
        "resolve_cliproxy_proxy",
        lambda *_args, **_kwargs: CliproxyProxy(
            proxy_url="http://icloud-proxy.example",
            country_code="US",
        ),
    )

    output = Workflow(
        session_factory=lambda: None,
        mail_provider=FakeMailProvider(),
        twofauth_client=twofauth_client,
    ).run(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone",
            mail_provider="icloud_hide_my_email",
            use_proxy=False,
        ),
        work_id="work-icloud",
        run_id="run-icloud",
    )

    setup = output["security_setup"]
    assert output["user_account_id"] == "account-icloud"
    assert setup["password_status"] == "configured"
    assert setup["mfa_status"] == "failed"
    assert persisted["security_setup"].password_status == "configured"
    assert persisted["result"].password_configured is True
    assert calls["security_run"]["twofauth_client"] is twofauth_client
    assert calls["security_run"]["auth_result"].auth_cookie_header == (
        "auth-session=auth-cookie-value"
    )
    assert calls["security_run"]["http_session"] is not None
    assert calls["claim_complete"] == ("success", "icloud-user@example.test")
    assert "delete_placeholder" not in calls
    assert "claim_release" not in calls
    assert ("account_security.unhandled_failure", "ERROR") in events
    assert ("succeeded", "INFO") in events


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
        "email_domain": "",
    }
    assert provider.wait_email == "ocelots_plover_3p@icloud.com"


def test_icloud_registration_runs_codex_after_mfa_with_same_proxy(monkeypatch) -> None:
    order: list[str] = []
    captured: dict = {}
    current_proxy = "http://current-registration-proxy.example:8080"
    phone_provider = object()

    def totp_resolver(_account_id: str) -> str:
        return "654321"

    class MailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="icloud-mail-codex",
                email="codex-after-mfa@icloud.com",
                claim_token="claim-token",
                caller_id="caller",
                task_id="work-icloud-codex",
            )

        def claim_complete(self, _claim, *, result: str, detail: str):
            order.append(f"claim_complete:{result}:{detail}")
            return {"success": True}

        def claim_release(self, *_args, **_kwargs):
            order.append("claim_release")
            return {"success": True}

    class Workflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, **_kwargs):
            return lambda stage, _data, level="INFO": order.append(f"event:{stage}:{level}")

        def _make_claim_persist_callback(self, _work_id: str):
            return None

        def _create_placeholder_account(self, *, email: str) -> str:
            return "account-icloud-codex"

        def _merge_work_output(self, _work_id: str, _patch: dict) -> None:
            return None

        def _resolve_registration_proxy(self, **_kwargs) -> CliproxyProxy:
            return CliproxyProxy(
                proxy_url=current_proxy,
                country_code="US",
            )

        def _run_post_registration_security(self, *_args, **_kwargs):
            order.append("security_configured")
            return AccountSecuritySetupResult(
                password_status="configured",
                password_value_confirmed=True,
                mfa_status="configured",
                twofauth_account_id="twofauth-icloud-codex",
            )

        def _write_success_account(self, **_kwargs) -> None:
            order.append("account_persisted")

        def _detect_account_spaces_after_registration(self, **_kwargs) -> dict:
            order.append("personal_space_detected")
            return {
                "accounts_check_succeeded": True,
                "personal_chatgpt_account_id": "personal-space-1",
            }

        def _delete_placeholder_account(self, _user_account_id: str) -> None:
            order.append("delete_placeholder")

    class FakeBackfillRtWorkflow:
        def __init__(self, **kwargs) -> None:
            captured["codex_init"] = kwargs

        def run(self, **kwargs) -> str:
            order.append("codex_authorized")
            captured["codex_run"] = kwargs
            return kwargs["user_account_id"]

    def runner(*_args, proxy_url: str, **_kwargs):
        assert proxy_url == current_proxy
        result = AuthResult()
        result.email = "codex-after-mfa@icloud.com"
        result.password = "configured-password"
        result.password_configured = True
        result.session_token = "session-token"
        result.access_token = "access-token"
        result.cookie_header = "__Secure-next-auth.session-token=session-token"
        return protocol_registration._RegistrationAttempt(
            result=result,
            flow=None,
            proxy_url=proxy_url,
        )

    monkeypatch.setattr(protocol_registration, "BackfillRtWorkflow", FakeBackfillRtWorkflow)
    output = Workflow(
        session_factory=lambda: None,
        mail_provider=MailProvider(),
        authorize_codex_after_security=True,
        codex_phone_provider=phone_provider,
        totp_code_resolver=totp_resolver,
    )._run_registration_lifecycle(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone",
            mail_provider="icloud_hide_my_email",
        ),
        mode="email_protocol_no_phone",
        work_id="work-icloud-codex",
        run_id="run-icloud-codex",
        runner=runner,
    )

    assert captured["codex_init"]["phone_provider"] is phone_provider
    assert captured["codex_init"]["totp_code_resolver"] is totp_resolver
    assert captured["codex_run"] == {
        "user_account_id": "account-icloud-codex",
        "run_id": "run-icloud-codex",
        "proxy_url_override": current_proxy,
    }
    assert order.index("personal_space_detected") < order.index("security_configured")
    assert order.index("security_configured") < order.index("account_persisted")
    assert order.index("account_persisted") < order.index("codex_authorized")
    assert output["codex_authorization"] == {
        "status": "succeeded",
        "authorization_scope": "personal",
        "proxy_source": "registration_current_proxy",
        "add_phone_provider": "grizzly_sms",
    }
    assert "claim_release" not in order


def test_registration_codex_grizzly_provider_matches_invite_executor_defaults() -> None:
    provider = handlers._registration_codex_grizzly_phone_provider(
        session_factory=lambda: None,
        settings=SimpleNamespace(grizzly_sms_api_key="test-grizzly-key"),
        run_id="",
    )
    try:
        assert provider.base_url == "https://api.grizzlysms.com/stubs/handler_api.php"
        assert provider.cfg.service == "dr"
        assert provider.cfg.country == "187"
        assert provider.cfg.countries == ["187"]
        assert provider.cfg.maxPrice == "0.18"
        assert provider.cfg.max_number_attempts == 3
        assert provider.cfg.request_timeout_s == 20
        assert provider.cfg.otp_timeout_s == 120
        assert provider.cfg.otp_poll_interval_s == 3.0
    finally:
        provider.close()


def test_email_protocol_hashes_claimed_email_before_openai_registration(monkeypatch) -> None:
    order: list[str] = []
    emitted: dict[str, dict] = {}

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
            def emit(stage, data, level="INFO") -> None:
                order.append(f"event:{stage}")
                emitted[stage] = data

            return emit

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
            security_setup=None,
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

    def fake_registration_proxy(*, email: str, country_code: str):
        order.append(f"hash_proxy:{email}:{country_code}")
        return CliproxyProxy(
            proxy_url="http://127.0.0.1:18088",
            country_code=country_code,
            egress_ip="198.51.100.42",
        )

    class FakeAuthFlow:
        def __init__(self, cfg, trace_callback=None) -> None:
            order.append(f"auth_flow_proxy:{cfg.proxy}")

        def run_register(self, mail: RegistrationMailProviderAdapter) -> AuthResult:
            order.append("run_register")
            email = mail.create_mailbox()
            result = AuthResult()
            result.email = email
            result.password_configured = True
            result.session_token = "session-token"
            result.access_token = "access-token"
            return result

    monkeypatch.setattr(
        protocol_registration,
        "resolve_cliproxy_proxy",
        fake_registration_proxy,
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
    assert order.index("claim_mailbox") < order.index(
        "create_account:JosephStevenson892165@outlook.com"
    )
    assert order.index("create_account:JosephStevenson892165@outlook.com") < order.index(
        "hash_proxy:JosephStevenson892165@outlook.com:US"
    )
    assert order.index("hash_proxy:JosephStevenson892165@outlook.com:US") < order.index(
        "auth_flow_proxy:http://127.0.0.1:18088"
    )
    assert "write_success:JosephStevenson892165@outlook.com" in order
    assert "claim_complete" in order
    assert "detect_account_spaces" in order
    assert order.index("detect_account_spaces") < order.index(
        "write_success:JosephStevenson892165@outlook.com"
    )
    assert result["account_detection"]["personal_chatgpt_account_id"] == "personal-1"
    assert result["proxy_egress_ip"] == "198.51.100.42"
    assert emitted["proxy.assigned"]["proxy_egress_ip"] == "198.51.100.42"
    assert emitted["succeeded"]["proxy_egress_ip"] == "198.51.100.42"
    assert "delete_account" not in order


@pytest.mark.parametrize("mail_provider", ["custom", "icloud_hide_my_email"])
def test_email_protocol_rejects_valid_tokens_without_confirmed_password(
    mail_provider: str,
) -> None:
    calls: list[str] = []

    class MailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="mail-without-password",
                email="NoPassword@example.test",
                claim_token="claim-token",
                caller_id="caller",
                task_id="work-without-password",
            )

        def claim_release(self, _claim: ClaimedMailAccount, *, reason: str):
            calls.append(f"claim_release:{reason}")
            return {"success": True}

    class Workflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, **_kwargs):
            return lambda *_args, **_event_kwargs: None

        def _make_claim_persist_callback(self, _work_id: str):
            return None

        def _create_placeholder_account(self, *, email: str) -> str:
            return "account-without-password"

        def _set_placeholder_account_email(self, _user_account_id: str, _email: str) -> None:
            return None

        def _merge_work_output(self, _work_id: str, _patch: dict) -> None:
            return None

        def _resolve_registration_proxy(self, **_kwargs) -> CliproxyProxy:
            return CliproxyProxy(
                proxy_url="http://proxy.example",
                country_code="US",
            )

        def _write_success_account(self, **_kwargs) -> None:
            calls.append("write_success")

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            calls.append(f"delete_account:{user_account_id}")

    def runner(*_args, **_kwargs):
        result = AuthResult()
        result.email = "NoPassword@example.test"
        result.session_token = "session-token"
        result.access_token = "access-token"
        return protocol_registration._RegistrationAttempt(
            result=result,
            flow=None,
            proxy_url="http://proxy.example",
        )

    workflow = Workflow(session_factory=lambda: None, mail_provider=MailProvider())
    with pytest.raises(
        protocol_registration.ProtocolRegistrationWorkflowError,
        match="without configured password",
    ):
        workflow._run_registration_lifecycle(
            ProtocolRegistrationInput(
                mode="email_protocol_no_phone",
                mail_provider=mail_provider,
            ),
            mode="email_protocol_no_phone",
            work_id="work-without-password",
            run_id="run-without-password",
            runner=runner,
        )

    assert "write_success" not in calls
    assert "delete_account:account-without-password" in calls
    assert any(call.startswith("claim_release:registration_failed:") for call in calls)


def test_default_protocol_password_meets_current_minimum_length() -> None:
    first = protocol_registration.AuthFlow._default_password_from_email("a@b")
    second = protocol_registration.AuthFlow._default_password_from_email("a@b")

    assert len(first) >= 12
    assert len(second) >= 12
    assert first != second
    assert "a@b" not in first
    assert any(character.isupper() for character in first)
    assert any(character.islower() for character in first)
    assert any(character.isdigit() for character in first)
    assert first.isalnum()


def test_email_browser_reuses_registration_proxy_for_v4(monkeypatch) -> None:
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
        resolver = None

        def __init__(self, config, *, event_callback=None) -> None:
            order.append(f"browser_proxy:{config.proxy_url}")
            assert config.headless is True
            assert config.otp_timeout_s == 180
            assert config.success_close_delay_s == 3.5
            assert config.browser_backend == "cloakbrowser"
            assert config.cloakbrowser_license_key == "cb_fixture_secret"

        def run(
            self,
            mail: RegistrationMailProviderAdapter,
            *,
            totp_code_provider=None,
        ) -> AuthResult:
            FakeBrowser.resolver = totp_code_provider
            email = mail.create_mailbox()
            order.append(f"browser_run:{email}")
            result = AuthResult()
            result.email = email
            result.password = "saved-password"
            result.password_configured = True
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

        def _run_post_registration_security(self, *_args, **_kwargs):
            order.append("security_configured")
            return AccountSecuritySetupResult(
                password_status="configured",
                password_value_confirmed=True,
                mfa_status="configured",
                twofauth_account_id="twofauth-browser-1",
            )

        def _delete_placeholder_account(self, user_account_id: str) -> None:
            order.append("delete_account")

        def _merge_work_output(self, work_id: str, patch: dict) -> None:
            order.append("persist_account")

    def fake_proxy(*, email: str, country_code: str):
        order.append(f"hash_proxy:{email}:{country_code}")
        return CliproxyProxy(
            proxy_url="http://browser-proxy.example:8080",
            country_code=country_code,
        )

    monkeypatch.setattr(protocol_registration, "CamoufoxEmailRegistration", FakeBrowser)
    monkeypatch.setattr(protocol_registration, "resolve_cliproxy_proxy", fake_proxy)

    def totp_resolver(_account_id: str) -> str:
        return "123456"

    result = TestWorkflow(
        session_factory=lambda: None,
        mail_provider=FakeMailProvider(),
        totp_code_resolver=totp_resolver,
        cloakbrowser_license_key="cb_fixture_secret",
    ).run(
        ProtocolRegistrationInput(
            mode="email_browser_no_phone",
            caller_id="caller",
            project_key="openai-register",
            use_proxy=False,
            browser_close_delay_s=3.5,
            browser_backend="cloakbrowser",
        ),
        work_id="work-1",
        run_id="run-1",
    )

    assert result["mode"] == "email_browser_no_phone"
    assert order.index("claim_mailbox") < order.index("create_account")
    assert order.index("create_account") < order.index("hash_proxy:BrowserAccount@outlook.com:US")
    assert "write_success:BrowserAccount@outlook.com" in order
    assert "detect_v4:http://browser-proxy.example:8080" in order
    assert "claim_complete" in order
    assert "claim_release" not in order
    assert "delete_account" not in order
    assert FakeBrowser.resolver is totp_resolver


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

        def run(
            self,
            mail: RegistrationMailProviderAdapter,
            *,
            totp_code_provider=None,
        ) -> AuthResult:
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
        "resolve_cliproxy_proxy",
        lambda *_args, **_kwargs: CliproxyProxy(
            proxy_url="http://browser-proxy.example:8080",
            country_code="US",
        ),
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


def test_post_registration_detection_failure_keeps_persisted_account() -> None:
    calls: list[str] = []

    class MailProvider:
        def claim_random(self, **_kwargs) -> ClaimedMailAccount:
            return ClaimedMailAccount(
                account_id="mail-3",
                email="SavedBrowser@icloud.com",
                claim_token="claim-token",
                caller_id="caller",
                task_id="work-3",
            )

        def claim_complete(self, _claim, *, result: str, detail: str):
            calls.append(f"claim_complete:{result}:{detail}")
            return {"success": True}

        def claim_release(self, *_args, **_kwargs):
            calls.append("claim_release")
            return {"success": True}

    class Workflow(ProtocolRegistrationWorkflow):
        def _make_event_emitter(self, **_kwargs):
            return lambda stage, _data, level="INFO": calls.append(f"event:{stage}:{level}")

        def _make_claim_persist_callback(self, _work_id: str):
            return None

        def _create_placeholder_account(self, *, email: str) -> str:
            calls.append(f"create:{email}")
            return "account-3"

        def _merge_work_output(self, _work_id: str, _patch: dict) -> None:
            return None

        def _resolve_registration_proxy(self, **_kwargs) -> CliproxyProxy:
            return CliproxyProxy(
                proxy_url="http://proxy.example",
                country_code="US",
            )

        def _write_success_account(self, **_kwargs) -> None:
            calls.append("write_success")

        def _detect_account_spaces_after_registration(self, **_kwargs) -> dict:
            raise RuntimeError("event step foreign key failed")

        def _run_post_registration_security(self, *_args, **_kwargs):
            return AccountSecuritySetupResult(
                password_status="configured",
                password_value_confirmed=True,
                mfa_status="configured",
            )

        def _delete_placeholder_account(self, _user_account_id: str) -> None:
            calls.append("delete_account")

    def runner(*_args, **_kwargs):
        result = AuthResult()
        result.email = "SavedBrowser@icloud.com"
        result.password = "saved-password"
        result.password_configured = True
        result.session_token = "session-token"
        result.access_token = "access-token"
        return protocol_registration._RegistrationAttempt(
            result=result,
            flow=None,
            proxy_url="http://proxy.example",
        )

    workflow = Workflow(session_factory=lambda: None, mail_provider=MailProvider())
    output = workflow._run_registration_lifecycle(
        ProtocolRegistrationInput(mode="email_browser_no_phone", mail_provider="custom"),
        mode="email_browser_no_phone",
        work_id="work-3",
        run_id="run-3",
        runner=runner,
    )

    assert output["user_account_id"] == "account-3"
    assert output["has_session_token"] is True
    assert output["account_detection"] == {
        "accounts_check_succeeded": False,
        "error_type": "RuntimeError",
        "error_message": "event step foreign key failed",
    }
    assert "write_success" in calls
    assert "event:account_detection.failed:WARN" in calls
    assert "event:succeeded:INFO" in calls
    assert "claim_release" not in calls
    assert "delete_account" not in calls


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


def test_protocol_registration_work_closes_security_clients_after_failure(monkeypatch) -> None:
    calls: list[str] = []

    class Client:
        def close(self) -> None:
            calls.append("twofauth_close")

    class PhoneProvider:
        def close(self) -> None:
            calls.append("grizzly_close")

    class Workflow:
        def __init__(self, **kwargs) -> None:
            assert kwargs["twofauth_client"] is client
            assert kwargs["authorize_codex_after_security"] is True
            assert kwargs["codex_phone_provider"] is phone_provider
            assert kwargs["totp_code_resolver"] is totp_resolver

        def run(self, *_args, **_kwargs):
            raise RuntimeError("registration failed")

    client = Client()
    phone_provider = PhoneProvider()

    def totp_resolver(_account_id: str) -> str:
        return "123456"

    monkeypatch.setattr(handlers, "_twofauth_client", lambda _settings: client)
    monkeypatch.setattr(
        handlers,
        "_twofauth_otp_resolver",
        lambda _settings: totp_resolver,
    )
    monkeypatch.setattr(
        handlers,
        "_registration_codex_grizzly_phone_provider",
        lambda **_kwargs: phone_provider,
    )
    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())
    monkeypatch.setattr(handlers, "ProtocolRegistrationWorkflow", Workflow)

    with pytest.raises(RuntimeError, match="registration failed"):
        handlers._run_protocol_registration_work(
            session_factory=lambda: None,
            settings=SimpleNamespace(hero_sms_api_key=""),
            input_json={
                "mode": "email_protocol_no_phone",
                "mail_provider": "icloud_hide_my_email",
                "authorize_codex_after_security": True,
            },
        )

    assert calls == ["grizzly_close", "twofauth_close"]


def test_protocol_registration_work_defaults_codex_authorization_to_disabled(monkeypatch) -> None:
    captured: dict = {}

    class Client:
        def close(self) -> None:
            captured["twofauth_closed"] = True

    class Workflow:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def run(self, input_, **_kwargs):
            captured["registration_input"] = input_
            return {"status": "ok"}

    monkeypatch.setattr(handlers, "_twofauth_client", lambda _settings: Client())
    monkeypatch.setattr(handlers, "_twofauth_otp_resolver", lambda _settings: None)
    monkeypatch.setattr(
        handlers,
        "_registration_codex_grizzly_phone_provider",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled Codex authorization must not create a phone provider")
        ),
    )
    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())
    monkeypatch.setattr(handlers, "ProtocolRegistrationWorkflow", Workflow)

    result = handlers._run_protocol_registration_work(
        session_factory=lambda: None,
        settings=SimpleNamespace(
            hero_sms_api_key="",
            cloakbrowser_license_key="cb_fixture_secret",
        ),
        input_json={
            "mode": "email_protocol_no_phone",
            "mail_provider": "icloud_hide_my_email",
            "browser_backend": "cloakbrowser",
        },
    )

    assert result == {"status": "ok"}
    assert captured["authorize_codex_after_security"] is False
    assert captured["codex_phone_provider"] is None
    assert captured["cloakbrowser_license_key"] == "cb_fixture_secret"
    assert captured["registration_input"].browser_backend == "cloakbrowser"
    assert not hasattr(captured["registration_input"], "cloakbrowser_license_key")
    assert captured["twofauth_closed"] is True


@pytest.mark.parametrize("provider", ["hero_gmail", "hero_yandex"])
def test_hero_registration_uses_hero_mail_and_security_clients(monkeypatch, provider: str) -> None:
    captured: dict[str, object] = {}
    closed: list[str] = []

    class HeroMailProvider:
        def close(self) -> None:
            closed.append("hero_mail")

    class TwoFAuthClient:
        def close(self) -> None:
            closed.append("twofauth")

    class Workflow:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        def run(self, input_, **_kwargs):
            captured["input"] = input_
            return {"status": "ok"}

    hero_mail = HeroMailProvider()
    twofauth = TwoFAuthClient()
    monkeypatch.setattr(handlers, "_hero_email_plugin", lambda _settings: hero_mail)
    monkeypatch.setattr(handlers, "_twofauth_client", lambda _settings: twofauth)
    monkeypatch.setattr(handlers, "_twofauth_otp_resolver", lambda _settings: None)
    monkeypatch.setattr(handlers, "ProtocolRegistrationWorkflow", Workflow)

    result = handlers._run_protocol_registration_work(
        session_factory=lambda: None,
        settings=SimpleNamespace(hero_sms_api_key=""),
        input_json={
            "mode": "email_browser_no_phone",
            "mail_provider": provider,
        },
    )

    assert result == {"status": "ok"}
    assert captured["mail_provider"] is hero_mail
    assert captured["twofauth_client"] is twofauth
    assert captured["input"].mail_provider == provider
    assert closed == ["twofauth", "hero_mail"]


def test_non_paypal_protocol_registration_defaults_to_grizzly_sms(monkeypatch) -> None:
    captured: dict = {}

    class Workflow:
        def __init__(self, **kwargs) -> None:
            captured["init"] = kwargs

        def run(self, input_, **_kwargs):
            captured["input"] = input_
            return {"status": "ok"}

    monkeypatch.setattr(handlers, "_mail_plugin", lambda _settings: object())
    monkeypatch.setattr(handlers, "_twofauth_otp_resolver", lambda _settings: None)
    monkeypatch.setattr(handlers, "ProtocolRegistrationWorkflow", Workflow)

    result = handlers._run_protocol_registration_work(
        session_factory=lambda: None,
        settings=SimpleNamespace(
            grizzly_sms_api_key="grizzly-key",
            grizzly_sms_base_url="https://grizzly.example.test/handler_api.php",
            grizzly_sms_service="dr",
            grizzly_sms_max_price="0.18",
        ),
        input_json={
            "mode": "phone_protocol_bind_email",
            "mail_provider": "outlook",
            "phone_base_url": "https://attacker.example.test/collect",
            "phone_api_key_env": "ATTACKER_KEY",
        },
    )

    assert result == {"status": "ok"}
    assert captured["init"]["hero_sms_api_key"] == "grizzly-key"
    assert captured["input"].phone_base_url == "https://grizzly.example.test/handler_api.php"
    assert captured["input"].phone_api_key_env == "GRIZZLY_SMS_API_KEY"
    assert captured["input"].phone_service == "dr"
    assert captured["input"].phone_max_price == "0.18"


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
    result.browser_user_agent = "Mozilla/5.0 Fixture Firefox/152.0"
    result.browser_platform = "Win32"
    result.browser_timezone = "America/New_York"
    result.browser_timezone_offset = -240
    result.browser_accept_language = "en-US,en;q=0.5"
    result.browser_impersonate = "firefox147"
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
        "proxy_country": "",
        "oai_device_id": "device-1",
        "session_chatgpt_account_id": "business-1",
        "session_chatgpt_account_structure": "workspace",
        "session_chatgpt_account_plan_type": "team",
        "browser_user_agent": "Mozilla/5.0 Fixture Firefox/152.0",
        "browser_platform": "Win32",
        "browser_timezone": "America/New_York",
        "browser_timezone_offset": -240,
        "browser_accept_language": "en-US,en;q=0.5",
        "browser_impersonate": "firefox147",
        "require_personal_access_token": False,
        "run_id": "run-1",
    }


def test_auth_result_serializes_browser_identity() -> None:
    result = AuthResult()
    result.browser_user_agent = "Mozilla/5.0 Fixture Firefox/152.0"
    result.browser_platform = "Win32"
    result.browser_timezone = "America/New_York"
    result.browser_timezone_offset = -240
    result.browser_accept_language = "en-US,en;q=0.5"
    result.browser_impersonate = "firefox147"

    payload = result.to_dict()

    assert payload["browser_user_agent"] == "Mozilla/5.0 Fixture Firefox/152.0"
    assert payload["browser_platform"] == "Win32"
    assert payload["browser_timezone"] == "America/New_York"
    assert payload["browser_timezone_offset"] == -240
    assert payload["browser_accept_language"] == "en-US,en;q=0.5"
    assert payload["browser_impersonate"] == "firefox147"


def test_icloud_promotion_check_is_disabled_by_default() -> None:
    calls: list[str] = []
    workflow = ProtocolRegistrationWorkflow(session_factory=lambda: None, mail_provider=object())

    result = workflow._run_post_registration_promotion_check(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone",
            mail_provider="icloud_hide_my_email",
        ),
        user_account_id="account-1",
        registration_proxy=CliproxyProxy(
            proxy_url="http://registration-proxy.example:8080",
            country_code="US",
        ),
        run_id="",
        emit=lambda stage, *_args, **_kwargs: calls.append(stage),
    )

    assert result is None
    assert calls == ["promotion_check.skipped"]


def test_icloud_promotion_check_reuses_registration_proxy(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class Detector:
        def __init__(self, **_kwargs) -> None:
            pass

        def probe_personal_space_promotion(self, **kwargs):
            calls.append(("probe", kwargs["proxy_url"]))
            assert kwargs["user_account_id"] == "account-1"
            return {
                "status": "succeeded",
                "has_promotion": True,
                "promotion_id": "plus-1-month-free",
                "proxy_country": "US",
            }

    monkeypatch.setattr(protocol_registration, "BackfillSessionWorkflow", Detector)
    workflow = ProtocolRegistrationWorkflow(
        session_factory=lambda: None,
        mail_provider=object(),
        promotion_check_enabled=True,
    )

    result = workflow._run_post_registration_promotion_check(
        ProtocolRegistrationInput(
            mode="email_protocol_no_phone",
            mail_provider="icloud_hide_my_email",
        ),
        user_account_id="account-1",
        registration_proxy=CliproxyProxy(
            proxy_url="http://registration-proxy.example:8080",
            country_code="US",
            egress_ip="203.0.113.24",
            sid_source="registration_email_sha256",
            probe_attempts=2,
        ),
        run_id="",
        emit=lambda *_args, **_kwargs: None,
    )

    assert calls == [
        ("probe", "http://registration-proxy.example:8080"),
    ]
    assert result == {
        "status": "succeeded",
        "has_promotion": True,
        "promotion_id": "plus-1-month-free",
        "proxy_country": "US",
        "proxy_provider": "cliproxy",
        "proxy_egress_ip": "203.0.113.24",
        "proxy_sid_source": "registration_email_sha256",
        "proxy_probe_attempts": 2,
    }


def test_auth_flow_registration_does_not_run_codex_oauth() -> None:
    calls: list[str] = []
    auth_url_kwargs: list[dict] = []

    class FakeMailProvider:
        last_persona = None

        def create_mailbox(self) -> str:
            return "registration-only@example.test"

        def wait_for_otp(self, *_args, **_kwargs) -> str:
            calls.append("wait_for_otp")
            return "123456"

    class RegistrationOnlyAuthFlow(AuthFlow):
        def check_proxy(self) -> bool:
            return True

        def get_csrf_token(self) -> str:
            calls.append("providers_then_csrf")
            return "csrf"

        def get_auth_url(self, _csrf_token: str, **kwargs) -> str:
            calls.append("signin_openai")
            auth_url_kwargs.append(kwargs)
            return "https://auth.example.test/authorize"

        def auth_oauth_init(self, _auth_url: str) -> str:
            calls.extend(("authorize_302", "email_verification_200"))
            self._last_auth_oauth_init_url = "https://auth.openai.com/email-verification"
            return "device-id"

        def get_sentinel_token(self, _device_id: str) -> str:
            raise AssertionError("HAR registration must not prefetch authorize_continue sentinel")

        def signup(self, _email: str, _sentinel: str) -> bool:
            raise AssertionError("HAR registration must not call authorize/continue")

        def register_password(self, _email: str) -> bool:
            calls.append("register_password")
            self.result.password = "confirmed-registration-password"
            self.result.password_configured = True
            return True

        def send_otp(self) -> None:
            calls.extend(("send_otp_302", "email_verification_after_send_200"))
            return None

        def verify_otp(self, _code: str) -> dict:
            calls.append("validate_otp")
            return {}

        def fetch_client_auth_session_dump(self, stage: str = "") -> dict:
            calls.append(f"dump:{stage}")
            return {}

        def create_account(self) -> str:
            calls.append("create_account")
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

    flow = RegistrationOnlyAuthFlow(_proxy_config())
    result = flow.run_register(FakeMailProvider())

    assert result.is_valid()
    assert auth_url_kwargs == [
        {
            "prompt": "login",
            "screen_hint": "login_or_signup",
            "login_hint": "registration-only@example.test",
            "include_passkey_capabilities": False,
        }
    ]
    assert calls == [
        "providers_then_csrf",
        "signin_openai",
        "authorize_302",
        "email_verification_200",
        "register_password",
        "send_otp_302",
        "email_verification_after_send_200",
        "wait_for_otp",
        "validate_otp",
        "create_account",
        "chatgpt_callback",
        "chatgpt_session",
    ]


def test_signup_treats_passwordless_signup_as_new_password_registration() -> None:
    flow = AuthFlow.__new__(AuthFlow)
    flow._existing_email_verification_mode = ""
    flow._existing_page_type = ""
    flow._is_existing_account = True
    flow.authorize_continue = lambda **_kwargs: {
        "continue_url": "https://auth.openai.com/email-verification",
        "page": {
            "type": "email_otp_verification",
            "payload": {"email_verification_mode": "passwordless_signup"},
        },
    }

    assert flow.signup("new-account@example.test", "sentinel") is True
    assert flow._is_existing_account is False
    assert flow._existing_email_verification_mode == "passwordless_signup"


def test_signup_keeps_passwordless_login_on_existing_account_path() -> None:
    flow = AuthFlow.__new__(AuthFlow)
    flow._existing_email_verification_mode = ""
    flow._existing_page_type = ""
    flow._is_existing_account = False
    flow.authorize_continue = lambda **_kwargs: {
        "continue_url": "https://auth.openai.com/email-verification",
        "page": {
            "type": "email_otp_verification",
            "payload": {"email_verification_mode": "passwordless_login"},
        },
    }

    assert flow.signup("existing-account@example.test", "sentinel") is False
    assert flow._is_existing_account is True
    assert flow._existing_email_verification_mode == "passwordless_login"


def test_auth_flow_legacy_password_registration_does_not_fallback_when_password_fails() -> None:
    calls: list[str] = []

    class FakeMailProvider:
        last_persona = None

        def create_mailbox(self) -> str:
            return "password-required@example.test"

    class PasswordFailureAuthFlow(AuthFlow):
        def check_proxy(self) -> bool:
            return True

        def get_csrf_token(self) -> str:
            return "csrf"

        def get_auth_url(self, _csrf_token: str, **_kwargs) -> str:
            return "https://auth.example.test/authorize"

        def auth_oauth_init(self, _auth_url: str) -> str:
            self._last_auth_oauth_init_url = "https://auth.openai.com/email-verification"
            return "device-id"

        def get_sentinel_token(self, _device_id: str) -> str:
            return "sentinel"

        def signup(self, _email: str, _sentinel: str) -> bool:
            raise AssertionError("HAR registration must not call authorize/continue")

        def register_password(self, _email: str) -> bool:
            self._last_register_password_error = "invalid_auth_step"
            self.result.password_configured = False
            return False

        def send_otp(self) -> None:
            calls.append("send_otp")

        def kickoff_otp_delivery(self, _mode: str) -> bool:
            calls.append("kickoff_otp_delivery")
            return True

    flow = PasswordFailureAuthFlow(_proxy_config())

    with pytest.raises(RuntimeError, match="注册密码失败"):
        flow.run_register(FakeMailProvider())

    assert calls == []


def test_auth_flow_passwordless_signup_still_requires_password_before_otp() -> None:
    calls: list[str] = []

    class FakeMailProvider:
        last_persona = None

        def create_mailbox(self) -> str:
            return "passwordless-new@example.test"

        def wait_for_otp(self, *_args, **_kwargs) -> str:
            calls.append("wait_for_otp")
            return "123456"

    class PasswordlessSignupAuthFlow(AuthFlow):
        def check_proxy(self) -> bool:
            return True

        def get_csrf_token(self) -> str:
            return "csrf"

        def get_auth_url(self, _csrf_token: str, **_kwargs) -> str:
            return "https://auth.example.test/authorize"

        def auth_oauth_init(self, _auth_url: str) -> str:
            self._last_auth_oauth_init_url = "https://auth.openai.com/email-verification"
            return "device-id"

        def get_sentinel_token(self, _device_id: str) -> str:
            return "sentinel"

        def signup(self, _email: str, _sentinel: str) -> bool:
            raise AssertionError("HAR registration must not call authorize/continue")

        def register_email_password_with_retry(self, _email: str) -> bool:
            calls.append("register_password")
            self.result.password = "configured-password"
            self.result.password_configured = True
            return True

        def send_otp(self) -> None:
            calls.append("send_otp")

        def verify_otp(self, _code: str) -> dict:
            calls.append("verify_otp")
            return {}

        def create_account(self) -> str:
            calls.append("create_account")
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

    flow = PasswordlessSignupAuthFlow(_proxy_config())
    result = flow.run_register(FakeMailProvider())

    assert result.is_valid()
    assert result.password == "configured-password"
    assert result.password_configured is True
    assert calls == [
        "register_password",
        "send_otp",
        "wait_for_otp",
        "verify_otp",
        "create_account",
        "chatgpt_callback",
        "chatgpt_session",
    ]


def test_email_password_registration_retries_transient_account_creation_failure(
    monkeypatch,
) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    class RetryAuthFlow(AuthFlow):
        def register_password(self, _email: str) -> bool:
            attempts.append(len(attempts) + 1)
            if len(attempts) < 3:
                self._last_register_password_error = (
                    '{"error":{"code":"account_creation_failed",'
                    '"message":"Failed to create account. Please try again."}}'
                )
                return False
            self._last_register_password_error = ""
            self.result.password_configured = True
            return True

    monkeypatch.setenv("EMAIL_PROTOCOL_REGISTER_PASSWORD_ATTEMPTS", "3")
    monkeypatch.setattr(
        "refactor_app.plugins.openai_auth_protocol.auth_flow.time.sleep", sleeps.append
    )
    flow = RetryAuthFlow(_proxy_config())

    assert flow.register_email_password_with_retry("retry@example.test") is True
    assert attempts == [1, 2, 3]
    assert sleeps == [2.0, 4.0]


def test_email_password_registration_does_not_retry_non_transient_failure(monkeypatch) -> None:
    attempts: list[int] = []

    class NonRetryAuthFlow(AuthFlow):
        def register_password(self, _email: str) -> bool:
            attempts.append(len(attempts) + 1)
            self._last_register_password_error = "invalid_auth_step"
            return False

    monkeypatch.setenv("EMAIL_PROTOCOL_REGISTER_PASSWORD_ATTEMPTS", "3")
    flow = NonRetryAuthFlow(_proxy_config())

    assert flow.register_email_password_with_retry("no-retry@example.test") is False
    assert attempts == [1]


def test_registration_state_mutations_send_sentinel_so_and_invocation_id() -> None:
    requests: list[tuple[str, dict[str, str]]] = []
    sentinel_flows: list[str] = []
    sentinel_options: list[dict[str, object]] = []

    class Response:
        status_code = 200
        text = "{}"
        headers = {}
        url = "https://auth.openai.com/"

        def __init__(self, payload: dict | None = None) -> None:
            self._payload = payload or {}

        def json(self) -> dict:
            return self._payload

    class Session:
        def get(self, *_args, **_kwargs) -> Response:
            return Response()

        def post(self, url: str, *, headers: dict[str, str], **_kwargs) -> Response:
            requests.append((url, dict(headers)))
            if url.endswith("/api/accounts/create_account"):
                return Response({"continue_url": "https://chatgpt.com/callback"})
            return Response()

    flow = AuthFlow.__new__(AuthFlow)
    flow.session = Session()
    flow.result = AuthResult()
    flow.result.email = "new@example.test"
    flow.result.password = "candidate-password"
    flow.result.device_id = "device-id"
    flow._last_sentinel_token = ""
    flow._last_sentinel_so_token = ""
    flow._last_register_password_error = ""
    flow._common_headers = lambda *_args, **_kwargs: {}
    flow._trace_http = lambda *_args, **_kwargs: None

    def refresh(flow_name: str, **_kwargs) -> tuple[str, str]:
        sentinel_flows.append(flow_name)
        sentinel_options.append(dict(_kwargs))
        return f"sentinel-{flow_name}", f"so-{flow_name}"

    flow._refresh_sentinel_tokens = refresh

    assert flow.register_password("new@example.test") is True
    assert flow.verify_otp("123456") == {}
    assert flow.create_account() == "https://chatgpt.com/callback"

    assert sentinel_flows == [
        "username_password_create",
        "email_otp_validate",
        "oauth_create_account",
    ]
    assert sentinel_options == [{"initialize_first": True}, {}, {}]
    assert [url.rsplit("/", 1)[-1] for url, _headers in requests] == [
        "register",
        "validate",
        "create_account",
    ]
    for _url, headers in requests:
        assert headers["openai-sentinel-token"].startswith("sentinel-")
        assert headers["openai-sentinel-so-token"].startswith("so-")
        assert len(headers["x-access-flow-invocation-id"]) == 36


def test_registration_signin_query_matches_legacy_password_flow() -> None:
    requested_urls: list[str] = []
    requested_headers: list[dict] = []
    cookie_sets: list[tuple[str, str, str, str]] = []

    class Cookies:
        def set(self, name: str, value: str, *, domain: str, path: str) -> None:
            cookie_sets.append((name, value, domain, path))

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"url": "https://auth.openai.test/authorize"}

    class Session:
        cookies = Cookies()

        def post(self, url: str, **kwargs):
            requested_urls.append(url)
            requested_headers.append(dict(kwargs.get("headers") or {}))
            return Response()

    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.session = Session()
    flow._sentinel_runtime_context = create_sentinel_runtime_context("US")
    flow._trace_http = lambda *_args, **_kwargs: None
    flow._remember_oauth_params = lambda *_args, **_kwargs: None
    flow._inject_pkce_into_auth_url = lambda value: value

    flow.get_auth_url("csrf-token", screen_hint="signup", default_prompt="")

    query = parse_qs(urlparse(requested_urls[0]).query)
    assert query["screen_hint"] == ["signup"]
    assert query["ext-oai-did"] == [flow.result.device_id]
    assert requested_headers[0]["oai-device-id"] == flow.result.device_id
    assert ("oai-did", flow.result.device_id, ".chatgpt.com", "/") in cookie_sets
    assert ("oai-did", flow.result.device_id, "auth.openai.com", "/") in cookie_sets
    assert len(query["auth_session_logging_id"]) == 1
    assert "prompt" not in query
    assert "ext-passkey-client-capabilities" not in query

    flow.get_auth_url("csrf-token")

    neutral_query = parse_qs(urlparse(requested_urls[1]).query)
    assert neutral_query["ext-oai-did"] == [flow.result.device_id]
    assert len(neutral_query["auth_session_logging_id"]) == 1
    assert neutral_query["ext-passkey-client-capabilities"] == ["11111"]
    assert "prompt" not in neutral_query
    assert "screen_hint" not in neutral_query

    flow.get_auth_url(
        "csrf-token",
        prompt="login",
        screen_hint="login_or_signup",
        login_hint="registration-only@example.test",
        include_passkey_capabilities=False,
    )

    registration_query = parse_qs(urlparse(requested_urls[2]).query)
    assert registration_query["prompt"] == ["login"]
    assert registration_query["screen_hint"] == ["login_or_signup"]
    assert registration_query["login_hint"] == ["registration-only@example.test"]
    assert registration_query["ext-oai-did"] == [flow.result.device_id]
    assert "ext-passkey-client-capabilities" not in registration_query


def test_auth_oauth_init_preserves_signin_device_identity() -> None:
    class Response:
        def __init__(self, *, status_code: int, url: str, location: str = "") -> None:
            self.status_code = status_code
            self.text = '<html>oai-did="server-device-id"</html>'
            self.url = url
            self.headers = {"Location": location} if location else {}

    class Cookies:
        def __init__(self) -> None:
            self.values = [SimpleNamespace(name="oai-did", value="server-device-id")]
            self.set_calls: list[tuple[str, str, str, str]] = []

        def __iter__(self):
            return iter(self.values)

        def set(self, name: str, value: str, *, domain: str, path: str) -> None:
            self.set_calls.append((name, value, domain, path))

    class Session:
        def __init__(self) -> None:
            self.cookies = Cookies()
            self.calls: list[dict] = []

        def get(self, url: str, **kwargs):
            self.calls.append({"url": url, **kwargs})
            return Response(
                status_code=302,
                url=url,
                location="https://auth.openai.com/email-verification",
            )

    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.result.device_id = "signin-device-id"
    flow.session = Session()
    flow._sentinel_runtime_context = create_sentinel_runtime_context("US")
    flow._auth_web_runtime = None
    flow._auth_web_runtime_page_url = ""
    flow._last_auth_oauth_init_url = ""
    flow._last_auth_session_logging_id = ""
    flow._trace_http = lambda *_args, **_kwargs: None
    flow._is_cloudflare_challenge_response = lambda _response: False
    runtime = SimpleNamespace(
        runtime_info={"deviceId": "bootstrap-device-id"},
        auth_session_logging_id="session-id",
        is_ready=True,
    )

    def load_document(*_args, **_kwargs):
        flow._auth_web_runtime = runtime
        return Response(
            status_code=200,
            url="https://auth.openai.com/email-verification",
        )

    flow._load_auth_web_document = load_document

    device_id = flow.auth_oauth_init("https://auth.openai.com/authorize")

    assert device_id == "signin-device-id"
    assert flow.result.device_id == "signin-device-id"
    assert flow.session.calls[0]["allow_redirects"] is False
    assert ("oai-did", "signin-device-id", ".chatgpt.com", "/") in flow.session.cookies.set_calls
    assert ("oai-did", "signin-device-id", ".openai.com", "/") in flow.session.cookies.set_calls


def test_send_otp_matches_har_document_redirect_sequence() -> None:
    requests: list[dict] = []
    traces: list[str] = []
    documents: list[dict] = []

    class Response:
        status_code = 302
        text = ""
        headers = {"Location": "https://auth.openai.com/email-verification"}

    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.result.email = "registration@example.test"
    flow._last_otp_sent_at = 0.0
    flow._common_headers = lambda *_args, **_kwargs: {
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": BROWSER_USER_AGENT,
    }

    def request(method: str, url: str, **kwargs):
        requests.append({"method": method, "url": url, **kwargs})
        return Response()

    flow._session_request = request
    flow._trace_http = lambda step, *_args, **_kwargs: traces.append(step)
    flow._load_auth_web_document = lambda page_url, **kwargs: documents.append(
        {"page_url": page_url, **kwargs}
    )

    flow.send_otp()

    assert len(requests) == 1
    request_record = requests[0]
    assert request_record["method"] == "GET"
    assert request_record["url"].endswith("/api/accounts/email-otp/send")
    assert request_record["allow_redirects"] is False
    assert request_record["headers"]["Sec-Fetch-Dest"] == "document"
    assert request_record["headers"]["Sec-Fetch-Mode"] == "navigate"
    assert request_record["headers"]["Sec-Fetch-Site"] == "same-origin"
    assert "Sec-Fetch-User" not in request_record["headers"]
    assert request_record["headers"]["sec-ch-ua"] == BROWSER_SEC_CH_UA
    assert traces == ["send_email_otp"]
    assert documents == [
        {
            "page_url": "https://auth.openai.com/email-verification",
            "referer": "https://auth.openai.com/create-account/password",
            "trace_step": "email_verification_after_otp_send",
            "include_user_activation": False,
        }
    ]
    assert flow._last_otp_sent_at > 0


def test_http_trace_reports_fingerprint_and_cookie_names_without_values() -> None:
    records: list[dict] = []
    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.result.email = "registration@example.test"
    flow.session = SimpleNamespace(cookies=[SimpleNamespace(name="oai-did", value="device")])
    flow._trace_callback = records.append
    flow._http_trace_enabled = False
    flow._trace_dump_enabled = False
    flow._trace_include_cookie = False

    request = SimpleNamespace(
        method="GET",
        url="https://auth.openai.com/email-verification",
        body=None,
        headers={
            "User-Agent": BROWSER_USER_AGENT,
            "sec-ch-ua": BROWSER_SEC_CH_UA,
            "sec-ch-ua-platform": BROWSER_SEC_CH_UA_PLATFORM,
            "Cookie": "oai-did=device-secret; auth-session=session-secret",
        },
    )
    response = SimpleNamespace(
        request=request,
        status_code=200,
        url=request.url,
        headers={},
        text="ok",
    )

    flow._trace_http("auth_email_verification_page", response)

    assert records[0]["user_agent"] == BROWSER_USER_AGENT
    assert records[0]["sec_ch_ua"] == BROWSER_SEC_CH_UA
    assert records[0]["sec_ch_ua_platform"] == BROWSER_SEC_CH_UA_PLATFORM
    assert records[0]["request_cookie_names"] == ["auth-session", "oai-did"]
    assert records[0]["session_cookie_names"] == ["oai-did"]
    assert "device-secret" not in str(records[0])
    assert "session-secret" not in str(records[0])


def test_registration_headers_match_configured_browser_fingerprint() -> None:
    flow = AuthFlow(_proxy_config())

    headers = flow._common_headers("https://auth.openai.com/create-account")

    assert headers["User-Agent"] == BROWSER_USER_AGENT
    assert headers["sec-ch-ua"] == BROWSER_SEC_CH_UA
    assert headers["sec-ch-ua-platform"] == BROWSER_SEC_CH_UA_PLATFORM
    assert "Accept-Encoding" not in headers
    assert "Cache-Control" not in headers
    assert "Pragma" not in headers
