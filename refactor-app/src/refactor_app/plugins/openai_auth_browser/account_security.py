from __future__ import annotations

import re
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from refactor_app.plugins.openai_auth_browser.email_registration import (
    CONTINUE_SELECTORS,
    EMAIL_INPUT_SELECTORS,
    PASSWORD_INPUT_SELECTORS,
    _camoufox_proxy,
    _chatgpt_session_payload,
    _click_first,
    _cookie_header,
    _cookie_value,
    _managed_camoufox,
    _otp_inputs,
    _session_token,
    _type_email_otp,
    _visible,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthResult,
    session_account_fields,
)
from refactor_app.plugins.twofauth import TwoFAuthOtp

TraceEmitter = Callable[[str, dict[str, Any], str], None]


class TotpVault(Protocol):
    def create_totp_account(self, *, email: str, secret: str, **kwargs: Any) -> str: ...

    def get_otp(self, account_id: str) -> TwoFAuthOtp: ...

    def delete_account(self, account_id: str) -> None: ...


@dataclass(frozen=True)
class BrowserAccountSecurityConfig:
    proxy_url: str = ""
    headless: bool = True
    locale: str = "en-US"
    navigation_timeout_ms: int = 60_000
    password_timeout_s: int = 180
    artifact_dir: str = ""


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
class _PasswordResult:
    status: str
    value_confirmed: bool = False
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class _MfaResult:
    status: str
    twofauth_account_id: str = ""
    error_code: str = ""
    error_message: str = ""


class CamoufoxAccountSecurity:
    def __init__(
        self,
        config: BrowserAccountSecurityConfig,
        *,
        event_callback: TraceEmitter | None = None,
    ) -> None:
        self.config = config
        self._event_callback = event_callback
        self._artifact_dir = Path(config.artifact_dir) if config.artifact_dir else None
        if self._artifact_dir is not None:
            self._artifact_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        auth_result: AuthResult,
        mail_provider: Any,
        twofauth_client: TotpVault | None,
        password_preconfigured: bool,
    ) -> AccountSecuritySetupResult:
        password_default = _PasswordResult(
            status="configured" if password_preconfigured else "unknown",
            value_confirmed=password_preconfigured,
        )
        if not auth_result.cookie_header and not auth_result.session_token:
            password_result = password_default
            if not password_preconfigured:
                password_result = _PasswordResult(
                    status="failed",
                    value_confirmed=False,
                    error_code="security_session_cookie_missing",
                    error_message="registered account has no browser session cookie",
                )
            return _combined_result(
                password_result,
                _MfaResult(
                    status="failed",
                    error_code="security_session_cookie_missing",
                    error_message="registered account has no browser session cookie",
                ),
            )

        try:
            from browserforge.fingerprints import Screen
            from camoufox.sync_api import Camoufox
        except Exception as exc:
            return _combined_result(
                password_default
                if password_preconfigured
                else _password_failure("browser_runtime_unavailable", exc),
                _mfa_failure("browser_runtime_unavailable", exc),
            )

        profile_dir = tempfile.mkdtemp(prefix="refactor_account_security_")
        try:
            with _managed_camoufox(
                Camoufox,
                headless=self.config.headless,
                humanize=True,
                persistent_context=True,
                user_data_dir=profile_dir,
                os="windows",
                screen=Screen(max_width=1920, max_height=1080),
                proxy=_camoufox_proxy(self.config.proxy_url),
                geoip=bool(self.config.proxy_url),
                locale=self.config.locale,
            ) as context:
                _seed_context_cookies(
                    context,
                    _session_cookie_header(auth_result),
                    ".chatgpt.com",
                )
                _seed_context_cookies(
                    context,
                    auth_result.auth_cookie_header,
                    ".auth.openai.com",
                )
                _seed_context_cookies(
                    context,
                    auth_result.auth_cookie_header,
                    ".openai.com",
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(30_000)
                page.goto(
                    "https://chatgpt.com/",
                    wait_until="domcontentloaded",
                    timeout=self.config.navigation_timeout_ms,
                )
                session_payload = _wait_for_session(page, timeout_s=45)
                access_token = str(
                    session_payload.get("accessToken") or auth_result.access_token or ""
                ).strip()
                if not access_token:
                    raise RuntimeError("registered browser session was not accepted")

                password_result = _ensure_password(
                    page,
                    access_token=access_token,
                    mail_provider=mail_provider,
                    email=auth_result.email,
                    password=auth_result.password,
                    password_preconfigured=password_preconfigured,
                    timeout_s=self.config.password_timeout_s,
                    emit=self._emit,
                )
                mfa_result = _ensure_totp(
                    page,
                    access_token=access_token,
                    email=auth_result.email,
                    twofauth_client=twofauth_client,
                    emit=self._emit,
                )
                try:
                    _refresh_auth_result(auth_result, context=context, page=page)
                except Exception as exc:
                    self._emit(
                        "account_security.session_refresh_failed",
                        {"error": _safe_error_message(exc)},
                        "WARN",
                    )
                result = _combined_result(password_result, mfa_result)
                self._emit("account_security.completed", result.to_dict())
                return result
        except Exception as exc:
            self._emit(
                "account_security.failed",
                {"error": _safe_error_message(exc)},
                "ERROR",
            )
            return _combined_result(
                password_default
                if password_preconfigured
                else _password_failure("account_security_browser_failed", exc),
                _mfa_failure("account_security_browser_failed", exc),
            )
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)

    def _emit(self, stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if self._event_callback is not None:
            self._event_callback(stage, data, level)


def _ensure_password(
    page: Any,
    *,
    access_token: str,
    mail_provider: Any,
    email: str,
    password: str,
    password_preconfigured: bool,
    timeout_s: int,
    emit: TraceEmitter,
) -> _PasswordResult:
    try:
        eligibility = _password_eligibility(page, access_token=access_token)
        if eligibility["change_eligible"]:
            emit("account_security.password.already_configured", {})
            return _PasswordResult(
                status="configured",
                value_confirmed=password_preconfigured,
            )
        if not eligibility["add_eligible"]:
            return _PasswordResult(
                status="configured" if password_preconfigured else "failed",
                value_confirmed=password_preconfigured,
                error_code="password_add_not_eligible" if not password_preconfigured else "",
                error_message=(
                    "password eligibility did not expose add or change"
                    if not password_preconfigured
                    else ""
                ),
            )
        if not str(password or "").strip():
            return _PasswordResult(
                status="failed",
                value_confirmed=False,
                error_code="password_value_missing",
                error_message="generated password is empty",
            )
        emit("account_security.password.add_started", {"email": email})
        _drive_add_password_reauthentication(
            page,
            access_token=access_token,
            mail_provider=mail_provider,
            email=email,
            password=password,
            timeout_s=timeout_s,
        )
        eligibility = _password_eligibility(page, access_token=access_token)
        if eligibility["change_eligible"] and not eligibility["add_eligible"]:
            emit("account_security.password.add_succeeded", {"email": email})
            return _PasswordResult(status="configured", value_confirmed=True)
        return _PasswordResult(
            status="failed",
            value_confirmed=False,
            error_code="password_add_not_verified",
            error_message="password eligibility still does not confirm a configured password",
        )
    except Exception as exc:
        emit(
            "account_security.password.failed",
            {"email": email, "error": _safe_error_message(exc)},
            "ERROR",
        )
        return _password_failure("password_setup_failed", exc)


def _ensure_totp(
    page: Any,
    *,
    access_token: str,
    email: str,
    twofauth_client: TotpVault | None,
    emit: TraceEmitter,
) -> _MfaResult:
    external_account_id = ""
    activation_succeeded = False
    try:
        mfa_info = _browser_api_json(
            page,
            "/backend-api/accounts/mfa_info",
            access_token=access_token,
        )
        if _totp_factor_present(mfa_info):
            emit("account_security.mfa.already_configured", {"email": email})
            return _MfaResult(status="configured")
        if twofauth_client is None:
            return _MfaResult(
                status="failed",
                error_code="twofauth_not_configured",
                error_message="2FAuth API token is not configured",
            )

        emit("account_security.mfa.enroll_started", {"email": email})
        enroll = _browser_api_json(
            page,
            "/backend-api/accounts/mfa/enroll",
            access_token=access_token,
            method="POST",
            body={"factor_type": "totp"},
        )
        session_id = str(enroll.get("session_id") or "").strip()
        secret = str(enroll.get("secret") or "").strip()
        if not session_id or not secret:
            raise RuntimeError("MFA enroll response missing session_id or secret")

        external_account_id = twofauth_client.create_totp_account(
            email=email,
            secret=secret,
            service="OpenAI",
            algorithm="SHA1",
            digits=6,
            period=30,
        )
        otp = _fresh_totp(twofauth_client, external_account_id)
        _browser_api_json(
            page,
            "/backend-api/accounts/mfa/user/activate_enrollment",
            access_token=access_token,
            method="POST",
            body={
                "code": otp.password,
                "factor_type": "totp",
                "session_id": session_id,
            },
        )
        activation_succeeded = True
        for _attempt in range(5):
            mfa_info = _browser_api_json(
                page,
                "/backend-api/accounts/mfa_info",
                access_token=access_token,
            )
            if _totp_factor_present(mfa_info):
                emit(
                    "account_security.mfa.enroll_succeeded",
                    {"email": email, "twofauth_account_id": external_account_id},
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
                    {"email": email, "error": _safe_error_message(cleanup_exc)},
                    "WARN",
                )
        emit(
            "account_security.mfa.failed",
            {"email": email, "error": _safe_error_message(exc)},
            "ERROR",
        )
        return _MfaResult(
            status="unknown" if activation_succeeded else "failed",
            twofauth_account_id=external_account_id,
            error_code="mfa_setup_failed",
            error_message=_safe_error_message(exc),
        )


def _password_eligibility(page: Any, *, access_token: str) -> dict[str, bool]:
    change = _browser_api_json(
        page,
        "/backend-api/accounts/change_password/eligibility",
        access_token=access_token,
    )
    add = _browser_api_json(
        page,
        "/backend-api/accounts/add_password/eligibility",
        access_token=access_token,
    )
    return {
        "change_eligible": change.get("eligible") is True,
        "add_eligible": add.get("eligible") is True,
    }


def _drive_add_password_reauthentication(
    page: Any,
    *,
    access_token: str,
    mail_provider: Any,
    email: str,
    password: str,
    timeout_s: int,
) -> None:
    auth_url = page.evaluate(
        """async () => {
            const csrfResponse = await fetch('/api/auth/csrf', {
                credentials: 'include', cache: 'no-store'
            });
            if (!csrfResponse.ok) {
                throw new Error(`GET /api/auth/csrf -> ${csrfResponse.status}`);
            }
            const csrf = await csrfResponse.json();
            const signin = new URL('/api/auth/signin/openai', window.location.origin);
            signin.searchParams.set('post_login_add_password', 'true');
            const form = new URLSearchParams({
                csrfToken: String(csrf.csrfToken || ''),
                callbackUrl: new URL('/', window.location.origin).toString(),
                json: 'true',
            });
            const response = await fetch(signin.toString(), {
                method: 'POST', credentials: 'include', cache: 'no-store',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: form.toString(),
            });
            const text = await response.text();
            let data = {};
            try { data = text ? JSON.parse(text) : {}; } catch (_) {}
            if (!response.ok || !data.url) {
                throw new Error(`POST add-password reauth -> ${response.status}`);
            }
            return String(data.url);
        }"""
    )
    if not str(auth_url or "").strip():
        raise RuntimeError("add-password reauthentication URL is empty")
    issued_after = time.time()
    page.goto(
        auth_url,
        wait_until="domcontentloaded",
        timeout=max(30_000, int(timeout_s) * 1000),
    )

    otp_submitted = False
    password_submitted = False
    deadline = time.monotonic() + max(30, int(timeout_s or 180))
    while time.monotonic() < deadline:
        current_url = str(page.url or "")
        current_url_lower = current_url.lower()
        if "chatgpt.com" in urlparse(current_url).netloc:
            try:
                eligibility = _password_eligibility(page, access_token=access_token)
                if eligibility["change_eligible"] and not eligibility["add_eligible"]:
                    return
            except Exception:
                pass

        email_field = _visible(page, EMAIL_INPUT_SELECTORS)
        if email_field is not None:
            email_field.click(timeout=5_000)
            email_field.fill(email)
            issued_after = time.time()
            if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000):
                page.keyboard.press("Enter")
            time.sleep(1)
            continue

        password_field = _visible(page, PASSWORD_INPUT_SELECTORS)
        if password_field is not None:
            if "/log-in/password" in current_url_lower:
                issued_after = time.time()
                _start_passwordless_login(page)
                otp_submitted = False
                time.sleep(1)
                continue
            for field in _visible_password_fields(page):
                field.click(timeout=5_000)
                field.fill(password)
            if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000):
                page.keyboard.press("Enter")
            password_submitted = True
            time.sleep(1)
            continue

        inputs = _otp_inputs(page)
        if inputs and not otp_submitted:
            code = str(
                mail_provider.wait_for_otp(
                    email,
                    timeout=max(30, int(timeout_s or 180)),
                    issued_after=issued_after,
                )
                or ""
            ).strip()
            if not code or not _type_email_otp(page, inputs, code):
                raise RuntimeError("add-password email OTP could not be filled")
            if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000):
                page.keyboard.press("Enter")
            otp_submitted = True
            time.sleep(1)
            continue

        if password_submitted and _click_first(
            page,
            (
                'button[type="submit"]',
                'button:has-text("Continue")',
                'a:has-text("Continue")',
                'button:has-text("Done")',
            ),
            timeout_ms=2_000,
        ):
            time.sleep(1)
            continue
        time.sleep(0.5)
    raise TimeoutError(f"add-password reauthentication timed out url={page.url}")


def _browser_api_json(
    page: Any,
    path: str,
    *,
    access_token: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = page.evaluate(
        """async ({path, method, body, accessToken}) => {
            const headers = body == null
                ? {Accept: 'application/json'}
                : {Accept: 'application/json', 'Content-Type': 'application/json'};
            if (accessToken) {
                headers.Authorization = `Bearer ${accessToken}`;
            }
            const response = await fetch(path, {
                method,
                credentials: 'include',
                cache: 'no-store',
                headers,
                body: body == null ? undefined : JSON.stringify(body),
            });
            const text = await response.text();
            let data = {};
            try { data = text ? JSON.parse(text) : {}; } catch (_) {}
            return {
                ok: response.ok,
                status: response.status,
                data,
                error: response.ok ? '' : text.slice(0, 500),
            };
        }""",
        {
            "path": path,
            "method": method,
            "body": body,
            "accessToken": str(access_token or "").strip(),
        },
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"browser API returned invalid response path={path}")
    if response.get("ok") is not True:
        raise RuntimeError(
            f"browser API failed path={path} status={response.get('status')}: "
            f"{str(response.get('error') or '')[:300]}"
        )
    data = response.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"browser API returned non-object JSON path={path}")
    return data


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


def _start_passwordless_login(page: Any) -> None:
    result = page.evaluate(
        """async () => {
            const response = await fetch('/api/accounts/passwordless/send-otp', {
                method: 'POST', credentials: 'include', cache: 'no-store'
            });
            return {ok: response.ok, status: response.status};
        }"""
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(
            "passwordless OTP send failed: "
            f"HTTP {result.get('status') if isinstance(result, dict) else 'unknown'}"
        )
    page.goto(
        "https://auth.openai.com/email-verification",
        wait_until="domcontentloaded",
        timeout=30_000,
    )


def _visible_password_fields(page: Any) -> list[Any]:
    try:
        fields = page.query_selector_all('input[type="password"]:visible')
    except Exception:
        fields = []
    return list(fields or []) or [
        field for field in (_visible(page, PASSWORD_INPUT_SELECTORS),) if field is not None
    ]


def _wait_for_session(page: Any, *, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + max(1, int(timeout_s))
    while time.monotonic() < deadline:
        payload = _chatgpt_session_payload(page)
        if payload.get("accessToken"):
            return payload
        time.sleep(0.5)
    return {}


def _refresh_auth_result(auth_result: AuthResult, *, context: Any, page: Any) -> None:
    session_payload = _chatgpt_session_payload(page)
    cookies = list(context.cookies())
    auth_result.access_token = str(session_payload.get("accessToken") or auth_result.access_token)
    auth_result.id_token = str(session_payload.get("idToken") or auth_result.id_token)
    account_id, structure, plan_type = session_account_fields(session_payload)
    auth_result.chatgpt_account_id = account_id or auth_result.chatgpt_account_id
    auth_result.chatgpt_account_structure = structure or auth_result.chatgpt_account_structure
    auth_result.chatgpt_account_plan_type = plan_type or auth_result.chatgpt_account_plan_type
    auth_result.cookie_header = _cookie_header(cookies, "chatgpt.com") or auth_result.cookie_header
    auth_result.auth_cookie_header = (
        _cookie_header(cookies, "openai.com") or auth_result.auth_cookie_header
    )
    auth_result.session_token = _session_token(cookies) or auth_result.session_token
    auth_result.device_id = (
        _cookie_value(cookies, ("oai-did", "oai-device-id")) or auth_result.device_id
    )
    csrf_cookie = _cookie_value(cookies, ("__Host-next-auth.csrf-token",))
    if csrf_cookie:
        auth_result.csrf_token = csrf_cookie.split("|", 1)[0]


def _seed_context_cookies(context: Any, cookie_header: str, domain: str) -> None:
    cookies = []
    host = str(domain or "").strip().lstrip(".")
    for raw in str(cookie_header or "").split(";"):
        if "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        cookie = {
            "name": name,
            "value": value,
            "httpOnly": name.lower().startswith("__secure-")
            or name.lower().startswith("__host-")
            or name.lower().startswith("auth"),
            "secure": True,
            "sameSite": "Lax",
        }
        if name.lower().startswith("__host-"):
            cookie["url"] = f"https://{host}/"
        else:
            cookie["domain"] = domain
            cookie["path"] = "/"
        cookies.append(cookie)
    if cookies:
        context.add_cookies(cookies)


def _session_cookie_header(auth_result: AuthResult) -> str:
    cookie_header = str(auth_result.cookie_header or "").strip()
    session_token = str(auth_result.session_token or "").strip()
    if not session_token or "__Secure-next-auth.session-token=" in cookie_header:
        return cookie_header
    session_cookie = f"__Secure-next-auth.session-token={session_token}"
    return f"{session_cookie}; {cookie_header}" if cookie_header else session_cookie


def _combined_result(
    password: _PasswordResult,
    mfa: _MfaResult,
) -> AccountSecuritySetupResult:
    return AccountSecuritySetupResult(
        password_status=password.status,
        password_value_confirmed=password.value_confirmed,
        password_error_code=password.error_code,
        password_error_message=password.error_message,
        mfa_status=mfa.status,
        twofauth_account_id=mfa.twofauth_account_id,
        mfa_error_code=mfa.error_code,
        mfa_error_message=mfa.error_message,
    )


def _password_failure(code: str, exc: Exception) -> _PasswordResult:
    return _PasswordResult(
        status="failed",
        error_code=code,
        error_message=_safe_error_message(exc),
    )


def _mfa_failure(code: str, exc: Exception) -> _MfaResult:
    return _MfaResult(
        status="failed",
        error_code=code,
        error_message=_safe_error_message(exc),
    )


def _safe_error_message(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {str(exc)[:800]}"
    message = re.sub(
        r"(?i)(secret|token|authorization)([\s\"'=:\\]+)[^\s,}\]]+",
        r"\1\2<redacted>",
        message,
    )
    return message[:1000]
