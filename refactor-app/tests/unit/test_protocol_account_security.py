from __future__ import annotations

from typing import Any

import refactor_app.plugins.openai_auth_protocol.account_security as account_security
from refactor_app.plugins.openai_auth_protocol.account_security import (
    ProtocolAccountSecurity,
    ProtocolAccountSecurityConfig,
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


class _Response:
    def __init__(self, status_code: int, payload: dict[str, Any], text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict[str, Any]:
        return self._payload


class _MfaSession:
    def __init__(self, *, activation_ok: bool = True) -> None:
        self.activation_ok = activation_ok
        self.mfa_info_calls = 0
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if url.endswith("/mfa_info"):
            self.mfa_info_calls += 1
            configured = self.activation_ok and self.mfa_info_calls > 1
            return _Response(
                200,
                {
                    "mfa_enabled_v2": configured,
                    "factors": {"totp": [{"id": "factor-1"}]} if configured else {},
                },
            )
        if url.endswith("/mfa/enroll"):
            return _Response(200, {"session_id": "mfa-session", "secret": "BASE32SECRET"})
        if url.endswith("/activate_enrollment"):
            if self.activation_ok:
                return _Response(200, {})
            return _Response(400, {}, "invalid code")
        raise AssertionError(f"unexpected API URL: {url}")


def _registered_result() -> AuthResult:
    result = AuthResult()
    result.email = "icloud-user@example.test"
    result.password = "registered-password"
    result.password_configured = True
    result.access_token = "web-access-token"
    result.session_token = "session-token"
    result.cookie_header = "oai-did=device-id"
    result.device_id = "device-id"
    return result


def test_protocol_totp_enrollment_uses_registration_session_without_password_requests() -> None:
    session = _MfaSession()
    vault = _TotpVault()
    events: list[tuple[str, dict[str, Any]]] = []

    result = ProtocolAccountSecurity(
        ProtocolAccountSecurityConfig(),
        event_callback=lambda stage, data, _level="INFO": events.append((stage, data)),
    ).run(
        auth_result=_registered_result(),
        twofauth_client=vault,
        http_session=session,
    )

    assert result.password_status == "configured"
    assert result.password_value_confirmed is True
    assert result.mfa_status == "configured"
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
    urls = [call["url"] for call in session.calls]
    assert urls == [
        "https://chatgpt.com/backend-api/accounts/mfa_info",
        "https://chatgpt.com/backend-api/accounts/mfa/enroll",
        "https://chatgpt.com/backend-api/accounts/mfa/user/activate_enrollment",
        "https://chatgpt.com/backend-api/accounts/mfa_info",
    ]
    assert all("password" not in url for url in urls)
    enroll_call = session.calls[1]
    assert enroll_call["headers"]["Authorization"] == "Bearer web-access-token"
    assert enroll_call["headers"]["Cookie"] == (
        "oai-did=device-id; __Secure-next-auth.session-token=session-token"
    )
    assert enroll_call["headers"]["oai-device-id"] == "device-id"
    assert session.calls[2]["json"] == {
        "code": "654321",
        "factor_type": "totp",
        "session_id": "mfa-session",
    }
    assert any(stage == "account_security.protocol.request" for stage, _data in events)


def test_protocol_totp_activation_failure_deletes_unactivated_twofauth_record() -> None:
    session = _MfaSession(activation_ok=False)
    vault = _TotpVault()

    result = ProtocolAccountSecurity(ProtocolAccountSecurityConfig()).run(
        auth_result=_registered_result(),
        twofauth_client=vault,
        http_session=session,
    )

    assert result.password_status == "configured"
    assert result.mfa_status == "failed"
    assert result.mfa_error_code == "mfa_setup_failed"
    assert result.twofauth_account_id == ""
    assert vault.deleted == ["twofauth-42"]


def test_protocol_security_requires_password_to_be_confirmed_by_registration() -> None:
    auth_result = _registered_result()
    auth_result.password_configured = False
    session = _MfaSession()

    result = ProtocolAccountSecurity(ProtocolAccountSecurityConfig()).run(
        auth_result=auth_result,
        twofauth_client=_TotpVault(),
        http_session=session,
    )

    assert result.password_status == "failed"
    assert result.password_error_code == "registration_password_not_configured"
    assert result.mfa_status == "failed"
    assert session.calls == []


def test_protocol_security_records_missing_twofauth_client_without_enrolling() -> None:
    session = _MfaSession()

    result = ProtocolAccountSecurity(ProtocolAccountSecurityConfig()).run(
        auth_result=_registered_result(),
        twofauth_client=None,
        http_session=session,
    )

    assert result.password_status == "configured"
    assert result.mfa_status == "failed"
    assert result.mfa_error_code == "twofauth_not_configured"
    assert [call["url"] for call in session.calls] == [
        "https://chatgpt.com/backend-api/accounts/mfa_info"
    ]


def test_protocol_security_reuses_captured_firefox_identity() -> None:
    session = _MfaSession()
    auth_result = _registered_result()
    auth_result.browser_user_agent = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:152.0) "
        "Gecko/20100101 Firefox/152.0"
    )
    auth_result.browser_platform = "MacIntel"
    auth_result.browser_accept_language = "en-US,en;q=0.9"
    auth_result.browser_impersonate = "firefox152"

    ProtocolAccountSecurity(ProtocolAccountSecurityConfig()).run(
        auth_result=auth_result,
        twofauth_client=None,
        http_session=session,
    )

    headers = session.calls[0]["headers"]
    assert headers["User-Agent"] == auth_result.browser_user_agent
    assert headers["Accept-Language"] == "en-US,en;q=0.9"
    assert not any(name.casefold().startswith("sec-ch-ua") for name in headers)


def test_protocol_security_uses_supported_firefox_tls_alias(monkeypatch) -> None:
    session = _MfaSession()
    captured: dict[str, str] = {}

    def create_session(*, proxy: str, impersonate: str):
        captured.update(proxy=proxy, impersonate=impersonate)
        return session

    monkeypatch.setattr(account_security, "create_http_session", create_session)
    auth_result = _registered_result()
    auth_result.browser_user_agent = "Mozilla/5.0 Gecko/20100101 Firefox/152.0"
    auth_result.browser_impersonate = "firefox152"

    ProtocolAccountSecurity(
        ProtocolAccountSecurityConfig(proxy_url="http://proxy.example:8080")
    ).run(
        auth_result=auth_result,
        twofauth_client=None,
    )

    assert captured == {
        "proxy": "http://proxy.example:8080",
        "impersonate": "firefox",
    }


def test_protocol_security_reuses_cloakbrowser_chromium_identity(monkeypatch) -> None:
    session = _MfaSession()
    captured: dict[str, str] = {}

    def create_session(*, proxy: str, impersonate: str):
        captured.update(proxy=proxy, impersonate=impersonate)
        return session

    monkeypatch.setattr(account_security, "create_http_session", create_session)
    auth_result = _registered_result()
    auth_result.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.7871.114 Safari/537.36"
    )
    auth_result.browser_platform = "Win32"
    auth_result.browser_impersonate = "chrome150"

    ProtocolAccountSecurity(
        ProtocolAccountSecurityConfig(proxy_url="http://proxy.example:8080")
    ).run(
        auth_result=auth_result,
        twofauth_client=None,
    )

    assert captured == {
        "proxy": "http://proxy.example:8080",
        "impersonate": "chrome",
    }
    headers = session.calls[0]["headers"]
    assert headers["User-Agent"] == auth_result.browser_user_agent
    assert headers["sec-ch-ua"] == (
        '"Chromium";v="150", "Google Chrome";v="150", '
        '"Not_A Brand";v="99"'
    )
    assert headers["sec-ch-ua-platform"] == '"Windows"'
