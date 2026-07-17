from types import SimpleNamespace

import pytest

import refactor_app.application.workflows.account_auth as account_auth
from refactor_app.application.workflows.account_auth import BackfillSessionWorkflow
from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthFlow,
    AuthResult,
    PasswordRequiredByUpstreamError,
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
    flow.get_auth_url = lambda _csrf: "https://auth.openai.test/authorize"
    flow.auth_oauth_init = lambda _url: "device-id"
    flow.get_sentinel_token = lambda _device_id: "sentinel-token"
    flow.authorize_continue = lambda **_kwargs: {
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
    flow._last_auth_oauth_init_url = ""
    flow._common_headers = lambda *_args, **_kwargs: {"User-Agent": "test-agent"}
    flow._get_oai_did_cookie = lambda: ""
    flow._trace_http = lambda *_args, **_kwargs: None
    return flow


def test_auth_oauth_init_retries_cloudflare_warmup_once_with_current_proxy() -> None:
    flow = _oauth_init_flow(
        [
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=False),
        ]
    )
    warmup_calls: list[str] = []
    flow._browser_warm_auth_oauth_init = lambda url: warmup_calls.append(url) or True

    device_id = flow.auth_oauth_init("https://auth.openai.com/authorize")

    assert device_id == "device-from-current-proxy"
    assert len(flow.session.get_calls) == 3
    assert len(warmup_calls) == 2


def test_auth_oauth_init_fails_after_second_cloudflare_warmup() -> None:
    flow = _oauth_init_flow(
        [
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=True),
            _OAuthInitResponse(challenged=True),
        ]
    )
    warmup_calls: list[str] = []
    flow._browser_warm_auth_oauth_init = lambda url: warmup_calls.append(url) or True

    with pytest.raises(
        RuntimeError,
        match="auth_oauth_init 被 Cloudflare challenge 拦截",
    ):
        flow.auth_oauth_init("https://auth.openai.com/authorize")

    assert len(flow.session.get_calls) == 3
    assert len(warmup_calls) == 2


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


def test_protocol_login_without_password_does_not_guess_on_password_page() -> None:
    flow = _passwordless_flow("login_password")
    password_verify_calls: list[str] = []
    flow.login_password_verify = lambda password: password_verify_calls.append(password)

    with pytest.raises(
        PasswordRequiredByUpstreamError,
        match="login_password_required_by_upstream",
    ):
        flow.run_protocol_login(
            _MailProvider(),
            "password-required@example.test",
            "",
            existing_only=True,
        )

    assert flow.result.password == ""
    assert password_verify_calls == []


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
