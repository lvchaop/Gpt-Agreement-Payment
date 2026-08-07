from __future__ import annotations

from typing import Any

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
