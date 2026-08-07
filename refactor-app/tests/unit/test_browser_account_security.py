from __future__ import annotations

from typing import Any

from refactor_app.plugins.openai_auth_browser.account_security import (
    BrowserAccountSecurityConfig,
    CamoufoxAccountSecurity,
    _browser_api_json,
    _ensure_totp,
    _seed_context_cookies,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthResult
from refactor_app.plugins.twofauth import TwoFAuthOtp


class _TotpVault:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    def create_totp_account(self, *, email: str, secret: str, **kwargs: Any) -> str:
        self.created.append({"email": email, "secret": secret, **kwargs})
        return "twofauth-42"

    def get_otp(self, account_id: str) -> TwoFAuthOtp:
        assert account_id == "twofauth-42"
        return TwoFAuthOtp(password="654321", generated_at=0, period=30)

    def delete_account(self, account_id: str) -> None:
        self.deleted.append(account_id)


class _MfaPage:
    def __init__(self, *, activation_ok: bool = True) -> None:
        self.activation_ok = activation_ok
        self.mfa_info_calls = 0
        self.activation_body: dict[str, Any] = {}

    def evaluate(self, _script: str, argument: dict[str, Any]) -> dict[str, Any]:
        path = argument["path"]
        if path.endswith("/mfa_info"):
            self.mfa_info_calls += 1
            configured = self.activation_ok and self.mfa_info_calls > 1
            return {
                "ok": True,
                "status": 200,
                "data": {
                    "mfa_enabled_v2": configured,
                    "factors": {"totp": [{"id": "factor-1"}]} if configured else {},
                },
                "error": "",
            }
        if path.endswith("/mfa/enroll"):
            return {
                "ok": True,
                "status": 200,
                "data": {"session_id": "mfa-session", "secret": "BASE32SECRET"},
                "error": "",
            }
        if path.endswith("/activate_enrollment"):
            self.activation_body = dict(argument["body"] or {})
            if self.activation_ok:
                return {"ok": True, "status": 200, "data": {}, "error": ""}
            return {
                "ok": False,
                "status": 400,
                "data": {},
                "error": "invalid code",
            }
        raise AssertionError(f"unexpected API path: {path}")


def test_totp_enrollment_uses_twofauth_code_and_confirms_factor() -> None:
    page = _MfaPage()
    vault = _TotpVault()

    result = _ensure_totp(
        page,
        access_token="web-access-token",
        email="icloud-user@example.test",
        twofauth_client=vault,
        emit=lambda *_args, **_kwargs: None,
    )

    assert result.status == "configured"
    assert result.twofauth_account_id == "twofauth-42"
    assert vault.created == [
        {
            "email": "icloud-user@example.test",
            "secret": "BASE32SECRET",
            "service": "OpenAI",
            "algorithm": "SHA1",
            "digits": 6,
            "period": 30,
        }
    ]
    assert page.activation_body == {
        "code": "654321",
        "factor_type": "totp",
        "session_id": "mfa-session",
    }
    assert vault.deleted == []


def test_totp_activation_failure_deletes_unactivated_twofauth_record() -> None:
    page = _MfaPage(activation_ok=False)
    vault = _TotpVault()

    result = _ensure_totp(
        page,
        access_token="web-access-token",
        email="icloud-user@example.test",
        twofauth_client=vault,
        emit=lambda *_args, **_kwargs: None,
    )

    assert result.status == "failed"
    assert result.error_code == "mfa_setup_failed"
    assert result.twofauth_account_id == ""
    assert vault.deleted == ["twofauth-42"]


def test_totp_missing_client_is_a_recorded_failure() -> None:
    result = _ensure_totp(
        _MfaPage(),
        access_token="web-access-token",
        email="icloud-user@example.test",
        twofauth_client=None,
        emit=lambda *_args, **_kwargs: None,
    )

    assert result.status == "failed"
    assert result.error_code == "twofauth_not_configured"


def test_security_setup_without_session_fails_but_returns_a_result() -> None:
    auth_result = AuthResult()
    auth_result.email = "icloud-user@example.test"
    auth_result.password = "candidate-password"

    result = CamoufoxAccountSecurity(BrowserAccountSecurityConfig()).run(
        auth_result=auth_result,
        mail_provider=object(),
        twofauth_client=None,
        password_preconfigured=False,
    )

    assert result.password_status == "failed"
    assert result.password_error_code == "security_session_cookie_missing"
    assert result.mfa_status == "failed"
    assert result.mfa_error_code == "security_session_cookie_missing"


def test_browser_api_uses_web_access_token() -> None:
    class Page:
        script = ""
        argument: dict[str, Any] = {}

        def evaluate(self, script: str, argument: dict[str, Any]) -> dict[str, Any]:
            self.script = script
            self.argument = argument
            return {"ok": True, "status": 200, "data": {"eligible": True}, "error": ""}

    page = Page()

    result = _browser_api_json(
        page,
        "/backend-api/accounts/change_password/eligibility",
        access_token="web-access-token",
    )

    assert result == {"eligible": True}
    assert page.argument["accessToken"] == "web-access-token"
    assert "headers.Authorization = `Bearer ${accessToken}`" in page.script


def test_seed_context_cookies_preserves_host_only_cookie_rules() -> None:
    class Context:
        cookies: list[dict[str, Any]] = []

        def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
            self.cookies = cookies

    context = Context()
    _seed_context_cookies(
        context,
        "__Host-next-auth.csrf-token=csrf-value; "
        "__Secure-next-auth.session-token=session-value; oai-did=device-value",
        ".chatgpt.com",
    )

    by_name = {cookie["name"]: cookie for cookie in context.cookies}
    host_cookie = by_name["__Host-next-auth.csrf-token"]
    assert host_cookie["url"] == "https://chatgpt.com/"
    assert "domain" not in host_cookie
    assert "path" not in host_cookie
    assert by_name["__Secure-next-auth.session-token"]["domain"] == ".chatgpt.com"
    assert by_name["oai-did"]["domain"] == ".chatgpt.com"
