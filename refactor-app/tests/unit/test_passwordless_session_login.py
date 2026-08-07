from types import SimpleNamespace

import pytest

import refactor_app.application.workflows.account_auth as account_auth
from refactor_app.application.workflows.account_auth import BackfillSessionWorkflow
from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthFlow,
    AuthResult,
    TotpRequiredByUpstreamError,
)
from refactor_app.plugins.openai_auth_protocol.codex_rt import ExternalMailOtpAdapter


class _MailProvider:
    def wait_for_otp(self, *_args, **_kwargs) -> str:
        return "123456"


def test_external_mail_adapter_uses_original_mailbox_email() -> None:
    requested_emails: list[str] = []

    class Provider:
        def wait_for_otp_by_email(self, *, email: str, **_kwargs):
            requested_emails.append(email)
            return SimpleNamespace(code="123456")

    adapter = ExternalMailOtpAdapter(
        Provider(),
        ensure_before_wait=False,
        mailbox_email="ScottValdez527454@hotmail.com",
    )

    assert adapter.wait_for_otp("scottvaldez527454@hotmail.com") == "123456"
    assert requested_emails == ["ScottValdez527454@hotmail.com"]
    assert adapter.events[-1]["email"] == "ScottValdez527454@hotmail.com"
    assert adapter.events[-1]["openai_email"] == "scottvaldez527454@hotmail.com"


def _passwordless_flow(page_type: str) -> AuthFlow:
    flow = AuthFlow.__new__(AuthFlow)
    flow.result = AuthResult()
    flow.result.access_token = "access-token"
    flow.result.session_token = "session-token"
    flow._existing_page_type = ""
    flow._existing_email_verification_mode = ""
    flow._last_otp_sent_at = 0.0
    flow.check_proxy = lambda: True
    flow.get_csrf_token = lambda: "csrf-token"
    flow.get_auth_url_kwargs = []

    def get_auth_url(_csrf, **kwargs):
        flow.get_auth_url_kwargs.append(kwargs)
        return "https://auth.openai.test/authorize"

    flow.get_auth_url = get_auth_url
    flow.auth_oauth_init = lambda _url: "device-id"
    flow.get_sentinel_token = lambda _device_id: "sentinel-token"
    flow.authorize_continue_calls = []

    def authorize_continue(**kwargs):
        flow.authorize_continue_calls.append(kwargs)
        return {
            "continue_url": (
                "https://auth.openai.test/log-in/password"
                if page_type == "login_password"
                else "https://auth.openai.test/email-verification"
            ),
            "page": {
                "type": page_type,
                "payload": {"email_verification_mode": "passwordless_login"},
            },
        }

    flow.authorize_continue = authorize_continue
    flow._normalize_continue_url = lambda value: value
    flow.kickoff_otp_delivery = lambda _reason: True
    flow.verify_otp = lambda _code: {}
    flow.fetch_client_auth_session_dump = lambda _stage: {}
    flow._is_add_phone_state = lambda **_kwargs: False
    flow._reauthorize_for_session = lambda _url: ""
    flow._env_flag = lambda name, _default="0": name == "SKIP_OAUTH_TOKEN_EXCHANGE"
    flow.get_auth_session = lambda: ("session-token", "access-token")
    return flow


class _OAuthInitResponse:
    def __init__(self, *, challenged: bool, url: str = "https://auth.openai.com/authorize"):
        self.status_code = 403 if challenged else 200
        self.text = "<title>Just a moment...</title>" if challenged else "<html>ready</html>"
        self.headers = {"Server": "cloudflare"} if challenged else {}
        self.url = url


class _PasswordlessOtpSession:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return SimpleNamespace(status_code=200, text="{}")


class _MfaResponse:
    def __init__(self, payload: dict) -> None:
        self.status_code = 200
        self.text = "{}"
        self._payload = payload

    def json(self) -> dict:
        return self._payload


class _MfaSession:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if url.endswith("/mfa/issue_challenge"):
            self.order.append("issue")
            return _MfaResponse({"oai-client-auth-session": {"mfa_factors": []}})
        if url.endswith("/mfa/verify"):
            self.order.append("verify")
            return _MfaResponse(
                {
                    "continue_url": "https://chatgpt.com/api/auth/callback/openai?code=test",
                    "page": {"type": "external_url"},
                }
            )
        raise AssertionError(url)


class _OAuthInitSession:
    def __init__(self, responses: list[_OAuthInitResponse]):
        self._responses = iter(responses)
        self.cookies = [SimpleNamespace(name="oai-did", value="device-from-current-proxy")]
        self.get_calls: list[str] = []

    def get(self, url: str, **_kwargs):
        self.get_calls.append(url)
        return next(self._responses)


def _oauth_init_flow(responses: list[_OAuthInitResponse]) -> AuthFlow:
    flow = AuthFlow.__new__(AuthFlow)
    flow.session = _OAuthInitSession(responses)
    flow.result = AuthResult()
    flow._auth_web_runtime = None
    flow._auth_web_runtime_page_url = ""
    flow._last_auth_oauth_init_url = ""
    flow._last_auth_session_logging_id = ""
    flow._common_headers = lambda *_args, **_kwargs: {"User-Agent": "test-agent"}
    flow._get_oai_did_cookie = lambda: ""
    flow._trace_http = lambda *_args, **_kwargs: None
    runtime = SimpleNamespace(
        runtime_info={"deviceId": "device-from-bootstrap"},
        auth_session_logging_id="runtime-session-id",
        is_ready=True,
        close=lambda: None,
    )

    def start_runtime(*, html_text: str, page_url: str):
        assert html_text == "<html>ready</html>"
        flow._auth_web_runtime = runtime
        flow._auth_web_runtime_page_url = page_url
        return runtime

    flow._start_auth_web_runtime = start_runtime
    return flow


def test_auth_oauth_init_retries_cloudflare_with_pure_http_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _oauth_init_flow(
        [
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=False),
        ]
    )
    warmup_calls: list[str] = []
    flow._browser_warm_auth_oauth_init = lambda url: warmup_calls.append(url) or True
    monkeypatch.setattr(
        "refactor_app.plugins.openai_auth_protocol.auth_flow.time.sleep",
        lambda _: None,
    )

    device_id = flow.auth_oauth_init("https://auth.openai.com/authorize")

    assert device_id == "device-from-current-proxy"
    assert len(flow.session.get_calls) == 3
    assert warmup_calls == []


def test_auth_oauth_init_fails_after_three_pure_http_cloudflare_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flow = _oauth_init_flow(
        [
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=True),
        ]
    )
    warmup_calls: list[str] = []
    flow._browser_warm_auth_oauth_init = lambda url: warmup_calls.append(url) or True
    monkeypatch.setattr(
        "refactor_app.plugins.openai_auth_protocol.auth_flow.time.sleep",
        lambda _: None,
    )

    with pytest.raises(
        RuntimeError,
        match="auth_oauth_init 被 Cloudflare challenge 拦截",
    ):
        flow.auth_oauth_init("https://auth.openai.com/authorize")

    assert len(flow.session.get_calls) == 3
    assert warmup_calls == []


def test_totp_challenge_request_order_matches_har() -> None:
    order: list[str] = []
    flow = AuthFlow.__new__(AuthFlow)
    flow.session = _MfaSession(order)
    flow._common_headers = lambda referer: {"Referer": referer}
    flow._trace_http = lambda *_args, **_kwargs: None
    challenge = {
        "page": {
            "type": "mfa_challenge",
            "payload": {
                "factor_id": "totp-factor",
                "factors": [
                    {
                        "id": "totp-factor",
                        "factor_type": "totp",
                        "is_recovery": False,
                    },
                    {
                        "id": "email-otp",
                        "factor_type": "email",
                        "is_recovery": True,
                    },
                ],
            },
        }
    }

    def provide_code() -> str:
        order.append("provider")
        return "123456"

    result = flow.complete_totp_challenge(challenge, provide_code)

    assert order == ["issue", "provider", "verify"]
    assert result["page"]["type"] == "external_url"
    issue, verify = flow.session.calls
    assert issue["url"].endswith("/api/accounts/mfa/issue_challenge")
    assert issue["json"] == {
        "id": "totp-factor",
        "type": "totp",
        "force_fresh_challenge": False,
    }
    assert issue["headers"]["Referer"] == "https://auth.openai.com/log-in/password"
    assert verify["url"].endswith("/api/accounts/mfa/verify")
    assert verify["json"] == {
        "id": "totp-factor",
        "type": "totp",
        "code": "123456",
    }
    assert verify["headers"]["Referer"].endswith("/mfa-challenge/totp-factor")
    assert verify["headers"]["x-access-flow-invocation-id"]


def test_totp_challenge_requires_configured_code_provider() -> None:
    flow = AuthFlow.__new__(AuthFlow)
    challenge = {
        "page": {
            "type": "mfa_challenge",
            "payload": {"factors": [{"id": "totp-factor", "factor_type": "totp"}]},
        }
    }

    with pytest.raises(
        TotpRequiredByUpstreamError,
        match="totp_code_provider_required_by_upstream",
    ):
        flow.complete_totp_challenge(challenge, None)


def test_protocol_login_without_password_uses_passwordless_otp() -> None:
    flow = _passwordless_flow("email_otp_verification")
    password_verify_calls: list[str] = []
    flow.login_password_verify = lambda password: password_verify_calls.append(password)

    result = flow.run_protocol_login(
        _MailProvider(),
        "passwordless@example.test",
        "",
        existing_only=True,
    )

    assert result.session_token == "session-token"
    assert result.access_token == "access-token"
    assert result.password == ""
    assert password_verify_calls == []
    assert flow.get_auth_url_kwargs == [
        {
            "login_hint": "passwordless@example.test",
            "screen_hint": "login_or_signup",
            "prompt": "login",
        }
    ]


def test_protocol_login_uses_authorize_login_hint_auto_otp_without_explicit_send() -> None:
    flow = _passwordless_flow("email_otp_verification")
    flow._last_auth_oauth_init_url = ""
    flow.auth_oauth_init = lambda _url: (
        setattr(flow, "_last_auth_oauth_init_url", "https://auth.openai.com/email-verification")
        or "device-id"
    )
    flow.get_sentinel_token = lambda _device_id: pytest.fail("sentinel must not run")
    flow.authorize_continue = lambda **_kwargs: pytest.fail("authorize_continue must not run")
    flow.kickoff_otp_delivery = lambda _reason: pytest.fail("explicit OTP send must not run")
    issued_after: list[float] = []

    class MailProvider:
        def wait_for_otp(self, *_args, **kwargs) -> str:
            issued_after.append(kwargs["issued_after"])
            return "123456"

    result = flow.run_protocol_login(
        MailProvider(),
        "WendyHarrison186055@outlook.com",
        "",
        existing_only=True,
    )

    assert result.session_token == "session-token"
    assert result.access_token == "access-token"
    assert flow.get_auth_url_kwargs == [
        {
            "login_hint": "WendyHarrison186055@outlook.com",
            "screen_hint": "login_or_signup",
            "prompt": "login",
        }
    ]
    assert len(issued_after) == 1
    assert issued_after[0] > 0


def test_protocol_login_creates_account_when_otp_returns_about_you() -> None:
    flow = _passwordless_flow("email_otp_verification")
    flow._last_auth_oauth_init_url = ""
    flow.auth_oauth_init = lambda _url: (
        setattr(flow, "_last_auth_oauth_init_url", "https://auth.openai.com/email-verification")
        or "device-id"
    )
    flow.verify_otp = lambda _code: {
        "continue_url": "https://auth.openai.com/about-you",
        "page": {"type": "about_you"},
    }
    flow._extract_continue_url_from_step = lambda payload: payload["continue_url"]
    created: list[bool] = []
    flow.create_account = lambda: created.append(True) or "https://chatgpt.com/api/auth/callback/openai"
    flow.follow_redirect_chain = lambda url: (url, url)

    result = flow.run_protocol_login(
        _MailProvider(),
        "new-account@example.test",
        "",
        existing_only=False,
    )

    assert created == [True]
    assert result.is_valid()


def test_protocol_login_without_password_switches_password_page_to_passwordless_otp() -> None:
    flow = _passwordless_flow("login_password")
    password_verify_calls: list[str] = []
    passwordless_otp_calls: list[str] = []
    flow.login_password_verify = lambda password: password_verify_calls.append(password)
    flow.send_passwordless_otp = lambda referer: passwordless_otp_calls.append(referer) or True

    result = flow.run_protocol_login(
        _MailProvider(),
        "passwordless@example.test",
        "",
        existing_only=True,
    )

    assert result.session_token == "session-token"
    assert result.access_token == "access-token"
    assert flow.result.password == ""
    assert password_verify_calls == []
    assert flow.authorize_continue_calls[0]["screen_hint"] == "login_or_signup"
    assert flow.authorize_continue_calls[0]["referer"].endswith("/log-in-or-create-account")
    assert passwordless_otp_calls == ["https://auth.openai.test/log-in/password"]


def test_protocol_login_completes_totp_after_password_without_email_otp() -> None:
    flow = _passwordless_flow("login_password")
    flow.login_password_verify = lambda _password: {
        "continue_url": "https://auth.openai.com/mfa-challenge/totp-factor",
        "page": {
            "type": "mfa_challenge",
            "payload": {"factors": [{"id": "totp-factor", "factor_type": "totp"}]},
        },
    }
    provided: list[str] = []
    completed: list[dict] = []

    def provide_totp() -> str:
        provided.append("called")
        return "123456"

    def complete(step: dict, provider) -> dict:
        completed.append(step)
        assert provider() == "123456"
        return {
            "continue_url": "https://chatgpt.com/api/auth/callback/openai?code=test",
            "page": {"type": "external_url"},
        }

    flow.complete_totp_challenge = complete
    flow.follow_redirect_chain = lambda url: (url, url)

    class MailProvider:
        def wait_for_otp(self, *_args, **_kwargs) -> str:
            pytest.fail("TOTP password login must not poll mailbox OTP")

    result = flow.run_protocol_login(
        MailProvider(),
        "mfa-account@example.test",
        "configured-password",
        existing_only=True,
        totp_code_provider=provide_totp,
    )

    assert result.is_valid()
    assert provided == ["called"]
    assert completed[0]["page"]["type"] == "mfa_challenge"


def test_passwordless_otp_request_matches_browser_invocation_headers() -> None:
    flow = AuthFlow.__new__(AuthFlow)
    flow.session = _PasswordlessOtpSession()
    flow._last_sentinel_token = "sentinel-token"
    flow._common_headers = lambda referer: {"Referer": referer, "Accept": "application/json"}
    flow._trace_http = lambda *_args, **_kwargs: None
    flow._mark_otp_sent = lambda *_args, **_kwargs: None

    assert flow.send_passwordless_otp("https://auth.openai.com/log-in/password") is True

    request = flow.session.calls[0]
    assert request["url"] == "https://auth.openai.com/api/accounts/passwordless/send-otp"
    assert request["headers"]["Content-Type"] == "application/json"
    assert request["headers"]["openai-sentinel-token"] == "sentinel-token"
    assert request["headers"]["x-access-flow-invocation-id"]


def test_backfill_session_allows_blank_password(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_passwords: list[str] = []

    class Workflow(BackfillSessionWorkflow):
        def _load_input(self, user_account_id: str, run_id: str = ""):
            account = SimpleNamespace(email="passwordless@example.test")
            auth = SimpleNamespace(password="")
            return account, auth, "http://proxy.example.test"

        def _start_step(self, *_args, **_kwargs) -> str:
            return ""

        def _finish_step(self, *_args, **_kwargs) -> None:
            return None

        def _write_event(self, *_args, **_kwargs) -> None:
            return None

        def _write_trace_steps(self, *_args, **_kwargs) -> None:
            return None

        def _write_success(self, **_kwargs) -> None:
            return None

        def detect_account_spaces_from_session(self, **_kwargs) -> dict:
            return {}

    auth_result = SimpleNamespace(
        session_token="session-token",
        access_token="access-token",
        refresh_token="",
        cookie_header="",
        device_id="device-id",
    )

    def acquire(**kwargs):
        captured_passwords.append(kwargs["password"])
        return SimpleNamespace(
            ok=True,
            auth_result=auth_result,
            cookie_header="cookie=value",
            snapshot={},
        )

    monkeypatch.setattr(account_auth, "acquire_chatgpt_session", acquire)
    monkeypatch.setattr(account_auth, "_auth_trace_enabled", lambda: False)

    workflow = Workflow(session_factory=lambda: None, mail_provider=object())
    assert workflow.run(user_account_id="account-1") == "account-1"
    assert captured_passwords == [""]


def test_backfill_session_resolves_totp_from_account_twofauth_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_ids: list[str] = []
    submitted_codes: list[str] = []

    class Workflow(BackfillSessionWorkflow):
        def _load_input(self, user_account_id: str, run_id: str = ""):
            account = SimpleNamespace(email="mfa-account@example.test")
            auth = SimpleNamespace(
                password="configured-password",
                mfa_status="configured",
                twofauth_account_id="twofauth-account-42",
            )
            return account, auth, "http://proxy.example.test"

        def _start_step(self, *_args, **_kwargs) -> str:
            return ""

        def _finish_step(self, *_args, **_kwargs) -> None:
            return None

        def _write_event(self, *_args, **_kwargs) -> None:
            return None

        def _write_trace_steps(self, *_args, **_kwargs) -> None:
            return None

        def _write_success(self, **_kwargs) -> None:
            return None

        def detect_account_spaces_from_session(self, **_kwargs) -> dict:
            return {}

    auth_result = SimpleNamespace(
        session_token="session-token",
        access_token="access-token",
        refresh_token="",
        cookie_header="",
        device_id="device-id",
    )

    def acquire(**kwargs):
        submitted_codes.append(kwargs["totp_code_provider"]())
        return SimpleNamespace(
            ok=True,
            auth_result=auth_result,
            cookie_header="cookie=value",
            snapshot={},
        )

    def resolve(account_id: str) -> str:
        resolved_ids.append(account_id)
        return "654321"

    monkeypatch.setattr(account_auth, "acquire_chatgpt_session", acquire)
    monkeypatch.setattr(account_auth, "_auth_trace_enabled", lambda: False)

    workflow = Workflow(
        session_factory=lambda: None,
        mail_provider=object(),
        totp_code_resolver=resolve,
    )
    assert workflow.run(user_account_id="account-1") == "account-1"
    assert resolved_ids == ["twofauth-account-42"]
    assert submitted_codes == ["654321"]
