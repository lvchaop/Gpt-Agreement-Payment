from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from refactor_app.config.browser_fingerprint import (
    BROWSER_IMPERSONATE,
    BROWSER_SEC_CH_UA,
    BROWSER_SEC_CH_UA_PLATFORM,
    BROWSER_USER_AGENT,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthResult
from refactor_app.plugins.openai_auth_protocol.http_client import create_http_session
from refactor_app.plugins.twofauth import TwoFAuthOtp

TraceEmitter = Callable[[str, dict[str, Any], str], None]


class TotpVault(Protocol):
    def create_totp_account(self, *, email: str, secret: str, **kwargs: Any) -> str: ...

    def get_otp(self, account_id: str) -> TwoFAuthOtp: ...

    def delete_account(self, account_id: str) -> None: ...


@dataclass(frozen=True)
class ProtocolAccountSecurityConfig:
    proxy_url: str = ""
    accept_language: str = ""
    request_timeout_s: int = 30


@dataclass(frozen=True)
class AccountSecuritySetupResult:
    password_status: str = "unknown"
    password_value_confirmed: bool = False
    password_error_code: str = ""
    password_error_message: str = ""
    mfa_status: str = "not_configured"
    twofauth_account_id: str = ""
    mfa_error_code: str = ""
    mfa_error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _MfaResult:
    status: str
    twofauth_account_id: str = ""
    error_code: str = ""
    error_message: str = ""


class ProtocolAccountSecurity:
    def __init__(
        self,
        config: ProtocolAccountSecurityConfig,
        *,
        event_callback: TraceEmitter | None = None,
    ) -> None:
        self.config = config
        self._event_callback = event_callback

    def run(
        self,
        *,
        auth_result: AuthResult,
        twofauth_client: TotpVault | None,
        http_session: Any | None = None,
    ) -> AccountSecuritySetupResult:
        if not auth_result.password_configured:
            return AccountSecuritySetupResult(
                password_status="failed",
                password_error_code="registration_password_not_configured",
                password_error_message="registration did not confirm the configured password",
                mfa_status="failed",
                mfa_error_code="registration_password_not_configured",
                mfa_error_message="MFA setup requires a completed password registration",
            )
        if not str(auth_result.access_token or "").strip():
            return AccountSecuritySetupResult(
                password_status="configured",
                password_value_confirmed=True,
                mfa_status="failed",
                mfa_error_code="security_access_token_missing",
                mfa_error_message="registered account has no access token",
            )

        owned_session = http_session is None
        session = http_session or create_http_session(
            proxy=self.config.proxy_url,
            impersonate=_protocol_impersonate(auth_result),
        )
        try:
            mfa = _ensure_totp(
                session,
                auth_result=auth_result,
                twofauth_client=twofauth_client,
                timeout_s=max(1, int(self.config.request_timeout_s)),
                accept_language=str(self.config.accept_language or "").strip(),
                emit=self._emit,
            )
            result = AccountSecuritySetupResult(
                password_status="configured",
                password_value_confirmed=True,
                mfa_status=mfa.status,
                twofauth_account_id=mfa.twofauth_account_id,
                mfa_error_code=mfa.error_code,
                mfa_error_message=mfa.error_message,
            )
            self._emit("account_security.completed", result.to_dict())
            return result
        finally:
            if owned_session:
                close = getattr(session, "close", None)
                if callable(close):
                    close()

    def _emit(self, stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if self._event_callback is not None:
            self._event_callback(stage, data, level)


def _ensure_totp(
    session: Any,
    *,
    auth_result: AuthResult,
    twofauth_client: TotpVault | None,
    timeout_s: int,
    accept_language: str,
    emit: TraceEmitter,
) -> _MfaResult:
    external_account_id = ""
    activation_succeeded = False
    try:
        mfa_info = _protocol_api_json(
            session,
            "/backend-api/accounts/mfa_info",
            auth_result=auth_result,
            timeout_s=timeout_s,
            accept_language=accept_language,
            emit=emit,
        )
        if _totp_factor_present(mfa_info):
            emit("account_security.mfa.already_configured", {"email": auth_result.email})
            return _MfaResult(status="configured")
        if twofauth_client is None:
            return _MfaResult(
                status="failed",
                error_code="twofauth_not_configured",
                error_message="2FAuth API token is not configured",
            )

        emit("account_security.mfa.enroll_started", {"email": auth_result.email})
        enroll = _protocol_api_json(
            session,
            "/backend-api/accounts/mfa/enroll",
            auth_result=auth_result,
            method="POST",
            body={"factor_type": "totp"},
            timeout_s=timeout_s,
            accept_language=accept_language,
            emit=emit,
        )
        session_id = str(enroll.get("session_id") or "").strip()
        secret = str(enroll.get("secret") or "").strip()
        if not session_id or not secret:
            raise RuntimeError("MFA enroll response missing session_id or secret")

        external_account_id = twofauth_client.create_totp_account(
            email=auth_result.email,
            secret=secret,
            service="OpenAI",
            algorithm="SHA1",
            digits=6,
            period=30,
        )
        otp = _fresh_totp(twofauth_client, external_account_id)
        _protocol_api_json(
            session,
            "/backend-api/accounts/mfa/user/activate_enrollment",
            auth_result=auth_result,
            method="POST",
            body={
                "code": otp.password,
                "factor_type": "totp",
                "session_id": session_id,
            },
            timeout_s=timeout_s,
            accept_language=accept_language,
            emit=emit,
        )
        activation_succeeded = True
        for _attempt in range(5):
            mfa_info = _protocol_api_json(
                session,
                "/backend-api/accounts/mfa_info",
                auth_result=auth_result,
                timeout_s=timeout_s,
                accept_language=accept_language,
                emit=emit,
            )
            if _totp_factor_present(mfa_info):
                emit(
                    "account_security.mfa.enroll_succeeded",
                    {
                        "email": auth_result.email,
                        "twofauth_account_id": external_account_id,
                    },
                )
                return _MfaResult(
                    status="configured",
                    twofauth_account_id=external_account_id,
                )
            time.sleep(0.5)
        return _MfaResult(
            status="unknown",
            twofauth_account_id=external_account_id,
            error_code="mfa_activation_not_verified",
            error_message="activate_enrollment succeeded but mfa_info has no TOTP factor",
        )
    except Exception as exc:
        if external_account_id and not activation_succeeded and twofauth_client is not None:
            try:
                twofauth_client.delete_account(external_account_id)
                external_account_id = ""
            except Exception as cleanup_exc:
                emit(
                    "account_security.mfa.cleanup_failed",
                    {"email": auth_result.email, "error": _safe_error_message(cleanup_exc)},
                    "WARN",
                )
        emit(
            "account_security.mfa.failed",
            {"email": auth_result.email, "error": _safe_error_message(exc)},
            "ERROR",
        )
        return _MfaResult(
            status="unknown" if activation_succeeded else "failed",
            twofauth_account_id=external_account_id,
            error_code="mfa_setup_failed",
            error_message=_safe_error_message(exc),
        )


def _protocol_api_json(
    session: Any,
    path: str,
    *,
    auth_result: AuthResult,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout_s: int = 30,
    accept_language: str = "",
    emit: TraceEmitter | None = None,
) -> dict[str, Any]:
    normalized_path = "/" + str(path or "").lstrip("/")
    user_agent = str(auth_result.browser_user_agent or "").strip() or BROWSER_USER_AGENT
    request_accept_language = (
        str(auth_result.browser_accept_language or "").strip()
        or str(accept_language or "").strip()
    )
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {str(auth_result.access_token or '').strip()}",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "User-Agent": user_agent,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    if request_accept_language:
        headers["Accept-Language"] = request_accept_language
    if "firefox/" not in user_agent.casefold():
        headers["sec-ch-ua"] = _chromium_sec_ch_ua(user_agent)
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = _chromium_sec_ch_ua_platform(
            str(auth_result.browser_platform or "").strip(),
            user_agent=user_agent,
        )
    cookie_header = _session_cookie_header(auth_result)
    if cookie_header:
        headers["Cookie"] = cookie_header
    if auth_result.device_id:
        headers["oai-device-id"] = auth_result.device_id
    if body is not None:
        headers["Content-Type"] = "application/json"

    response = session.request(
        method.upper(),
        f"https://chatgpt.com{normalized_path}",
        headers=headers,
        json=body,
        timeout=max(1, int(timeout_s)),
    )
    status = int(getattr(response, "status_code", 0) or 0)
    if emit is not None:
        emit(
            "account_security.protocol.request",
            {"method": method.upper(), "path": normalized_path, "status_code": status},
        )
    if status < 200 or status >= 300:
        response_text = str(getattr(response, "text", "") or "")
        raise RuntimeError(
            f"protocol API failed path={normalized_path} status={status}: {response_text[:300]}"
        )
    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"protocol API returned invalid JSON path={normalized_path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"protocol API returned non-object JSON path={normalized_path}")
    return payload


def _session_cookie_header(auth_result: AuthResult) -> str:
    cookie_header = str(auth_result.cookie_header or "").strip()
    session_token = str(auth_result.session_token or "").strip()
    if session_token and "__Secure-next-auth.session-token=" not in cookie_header:
        session_cookie = f"__Secure-next-auth.session-token={session_token}"
        cookie_header = f"{cookie_header}; {session_cookie}" if cookie_header else session_cookie
    return cookie_header


def _protocol_impersonate(auth_result: AuthResult) -> str:
    requested = str(auth_result.browser_impersonate or "").strip().casefold()
    user_agent = str(auth_result.browser_user_agent or "").strip().casefold()
    if requested.startswith("firefox") or "firefox/" in user_agent:
        # curl_cffi's generic alias selects its newest supported Firefox TLS profile.
        return "firefox"
    if re.fullmatch(r"chrome\d+[a-z]*", requested) or re.search(
        r"(?:chrome|chromium)/\d+", user_agent
    ):
        return "chrome"
    return requested or BROWSER_IMPERSONATE


def _chromium_sec_ch_ua(user_agent: str) -> str:
    match = re.search(r"(?:Chrome|Chromium)/(\d+)", str(user_agent or ""), re.IGNORECASE)
    if match is None:
        return BROWSER_SEC_CH_UA
    major = match.group(1)
    return (
        f'"Chromium";v="{major}", "Google Chrome";v="{major}", '
        '"Not_A Brand";v="99"'
    )


def _chromium_sec_ch_ua_platform(browser_platform: str, *, user_agent: str) -> str:
    platform = str(browser_platform or "").strip().casefold()
    user_agent_lower = str(user_agent or "").casefold()
    if platform.startswith(("mac", "darwin")) or "mac os x" in user_agent_lower:
        return '"macOS"'
    if platform.startswith("win") or "windows" in user_agent_lower:
        return '"Windows"'
    if "android" in platform or "android" in user_agent_lower:
        return '"Android"'
    if platform.startswith(("iphone", "ipad", "ipod")):
        return '"iOS"'
    if "linux" in platform or "linux" in user_agent_lower:
        return '"Linux"'
    return BROWSER_SEC_CH_UA_PLATFORM


def _fresh_totp(client: TotpVault, account_id: str) -> TwoFAuthOtp:
    otp = client.get_otp(account_id)
    if otp.generated_at > 0 and otp.period > 0:
        elapsed = max(0, int(time.time()) - otp.generated_at)
        remaining = otp.period - (elapsed % otp.period)
        if remaining <= 5:
            time.sleep(remaining + 0.25)
            otp = client.get_otp(account_id)
    return otp


def _totp_factor_present(payload: dict[str, Any]) -> bool:
    factors = payload.get("factors")
    if not isinstance(factors, dict):
        return False
    totp = factors.get("totp")
    return payload.get("mfa_enabled_v2") is True and isinstance(totp, list) and bool(totp)


def _safe_error_message(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:900]}"
