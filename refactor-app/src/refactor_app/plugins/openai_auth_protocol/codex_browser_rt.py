from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from shutil import rmtree
from typing import Callable, Protocol
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from refactor_app.config.browser_fingerprint import BROWSER_IMPERSONATE
from refactor_app.plugins.mail_external_api.plugin import prepare_domain_mailbox


DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_OAUTH_DEBUG_DIR = os.environ.get(
    "CODEX_OAUTH_DEBUG_DIR",
    "/tmp/refactor-app/codex-oauth-debug",
)
HERO_ADD_PHONE_INVALID_STATE = "hero_add_phone_invalid_state"
HERO_ADD_PHONE_OTP_TIMEOUT = "hero_add_phone_otp_timeout"
ADD_PHONE_CONTEXT_SETTLE_MS = max(
    0,
    int(os.environ.get("CODEX_ADD_PHONE_CONTEXT_SETTLE_MS", "3000")),
)
CALLBACK_CAPTURE_SETTLE_MS = max(
    0,
    int(os.environ.get("CODEX_CALLBACK_CAPTURE_SETTLE_MS", "5000")),
)


@dataclass(frozen=True)
class CodexBrowserRtResult:
    ok: bool
    refresh_token: str = ""
    access_token: str = ""
    id_token: str = ""
    token_type: str = ""
    scope: str = ""
    failure_code: str = ""
    failure_message: str = ""
    callback_url_seen: bool = False
    final_url: str = ""


class BrowserOtpProvider(Protocol):
    def wait_for_otp_by_email(
        self,
        *,
        email: str,
        timeout_s: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ): ...


class BrowserPhoneLease(Protocol):
    lease_id: str
    phone_e164: str


class BrowserPhoneOtpProvider(Protocol):
    def allocate(self) -> BrowserPhoneLease: ...

    def poll_otp(self, lease_id: str) -> str: ...

    def mark_verified(self, lease_id: str) -> None: ...

    def mark_failed(self, lease_id: str, reason: str = "") -> None: ...


class RetainedBrowserPhoneOtpProvider:
    """Keep one phone lease while a failed auth flow is restarted."""

    def __init__(self, delegate: BrowserPhoneOtpProvider) -> None:
        self._delegate = delegate
        self._lease: BrowserPhoneLease | None = None

    @property
    def has_retained_lease(self) -> bool:
        return self._lease is not None

    def allocate(self) -> BrowserPhoneLease:
        if self._lease is None:
            self._lease = self._delegate.allocate()
        return self._lease

    def poll_otp(self, lease_id: str) -> str:
        return self._delegate.poll_otp(lease_id)

    def mark_verified(self, lease_id: str) -> None:
        self._delegate.mark_verified(lease_id)
        self._lease = None

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        try:
            self._delegate.mark_failed(lease_id, reason)
        finally:
            self._lease = None

    def release_retained(self, reason: str) -> None:
        if self._lease is None:
            return
        self.mark_failed(str(self._lease.lease_id or ""), reason)


class BrowserApiRequestError(RuntimeError):
    def __init__(self, *, path: str, status: int, data: dict, body_head: str) -> None:
        self.path = path
        self.status = status
        self.data = data
        self.body_head = body_head
        error = data.get("error") if isinstance(data, dict) else None
        self.upstream_error_code = str(error.get("code") or "") if isinstance(error, dict) else ""
        super().__init__(f"{path} failed: http={status} body={body_head[:300]}")


class AddPhoneInvalidStateError(RuntimeError):
    pass


class AddPhoneNumberRejectedError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class AccountDeactivatedDuringPhoneFlowError(RuntimeError):
    pass


def acquire_codex_rt_with_existing_browser_session(
    *,
    cookie_header: str,
    auth_cookie_header: str = "",
    proxy: str = "",
    codex_client_id: str = DEFAULT_CODEX_CLIENT_ID,
    account_email: str = "",
    target_workspace_id: str = "",
    target_workspace_name: str = "",
    phone_provider: BrowserPhoneOtpProvider | None = None,
    totp_code_provider: Callable[[], str] | None = None,
    timeout_s: int = 45,
    capture_diagnostics: bool = True,
    headless: bool | None = None,
) -> CodexBrowserRtResult:
    if not cookie_header.strip():
        return CodexBrowserRtResult(
            ok=False,
            failure_code="missing_cookie_header",
            failure_message="补 RT fast path 需要已有 session/cookie，请先补 Session",
        )
    if not auth_cookie_header.strip():
        return CodexBrowserRtResult(
            ok=False,
            failure_code="missing_auth_cookie_header",
            failure_message="补 RT fast path 需要 auth.openai.com/openai.com 登录 cookie，请重新补 Session",
        )

    try:
        from browserforge.fingerprints import Screen
        from camoufox.sync_api import Camoufox
    except Exception as exc:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="browser_runtime_unavailable",
            failure_message=f"{type(exc).__name__}: {str(exc)[:300]}",
        )

    verifier = _b64url_no_pad(secrets.token_bytes(64))
    challenge = _b64url_no_pad(hashlib.sha256(verifier.encode()).digest())
    state = _b64url_no_pad(secrets.token_bytes(24))
    auth_url = "https://auth.openai.com/oauth/authorize?" + urlencode(
        {
            "client_id": codex_client_id,
            "response_type": "code",
            "redirect_uri": CODEX_REDIRECT_URI,
            "scope": "openid email profile offline_access",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        }
    )
    proxy_cfg = _camoufox_proxy(proxy)
    profile_dir = tempfile.mkdtemp(prefix="codex_rt_fast_")
    callback = {"url": ""}
    final_url = ""
    diagnostics = {"message": ""}
    totp_submitted = False

    def capture(value: str) -> bool:
        url = _extract_callback_url(value, expected_state=state)
        if not url:
            return False
        callback["url"] = url
        return True

    try:
        with Camoufox(
            headless=(
                bool(headless)
                if headless is not None
                else not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            ),
            humanize=False,
            persistent_context=True,
            user_data_dir=profile_dir,
            os="windows",
            screen=Screen(max_width=1920, max_height=1080),
            proxy=proxy_cfg,
            geoip=True,
            locale="en-US",
        ) as ctx:
            _seed_context_cookies(ctx, cookie_header, ".chatgpt.com")
            _seed_context_cookies(ctx, auth_cookie_header, ".auth.openai.com")
            _seed_context_cookies(ctx, auth_cookie_header, ".openai.com")
            _seed_account_cookie(ctx, target_workspace_id)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            _install_callback_capture(ctx, page, capture)
            try:
                page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                capture(str(exc))

            end = time.time() + max(5, timeout_s)
            while time.time() < end:
                final_url = str(getattr(page, "url", "") or "")
                if callback["url"] or capture(final_url):
                    _wait_after_callback_capture(page)
                    break
                account_failure = _account_deactivated_result(page, final_url)
                if account_failure is not None:
                    return account_failure
                if _select_existing_account_if_visible(page, account_email):
                    time.sleep(1)
                    continue
                if _is_mfa_challenge_url(final_url):
                    if totp_code_provider is None:
                        return CodexBrowserRtResult(
                            ok=False,
                            failure_code="totp_code_provider_missing",
                            failure_message="账号要求 TOTP，但没有可用的 2FAuth 记录或客户端配置",
                            final_url=final_url,
                        )
                    if not _has_otp_input(page) or totp_submitted:
                        time.sleep(1)
                        continue
                    try:
                        code = str(totp_code_provider() or "").strip()
                    except Exception as exc:
                        return CodexBrowserRtResult(
                            ok=False,
                            failure_code="totp_code_fetch_failed",
                            failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                            final_url=final_url,
                        )
                    if not _fill_otp(page, code) or not _click_first_visible(
                        page,
                        [
                            'button[type="submit"]',
                            'button:has-text("Continue")',
                            'button:has-text("Verify")',
                        ],
                    ):
                        return CodexBrowserRtResult(
                            ok=False,
                            failure_code="totp_submit_failed",
                            failure_message="检测到 TOTP 页面但填写或提交失败",
                            final_url=final_url,
                        )
                    totp_submitted = True
                    time.sleep(3)
                    continue
                if "/log-in" in final_url:
                    return CodexBrowserRtResult(
                        ok=False,
                        failure_code="session_cookie_not_accepted",
                        failure_message="已有 cookie 未通过 auth.openai.com 登录态校验，回落到登录页",
                        final_url=final_url,
                    )
                if phone_provider is not None and _is_add_phone_url(final_url):
                    phone_result = _complete_add_phone_with_provider(page, phone_provider)
                    if phone_result is not None:
                        return phone_result
                    time.sleep(0.5)
                    continue
                phone_failure = _phone_verification_failure(page, final_url)
                if phone_failure:
                    return _phone_failure_result(phone_failure, final_url=final_url)
                if _is_add_phone_url(final_url):
                    time.sleep(1)
                    continue
                if target_workspace_id or target_workspace_name:
                    if _select_workspace_if_visible(
                        page,
                        target_workspace_id=target_workspace_id,
                        target_workspace_name=target_workspace_name,
                    ):
                        time.sleep(1)
                        continue
                    _seed_account_cookie(ctx, target_workspace_id)
                    try:
                        page.evaluate(
                            """(accountId) => {
                                try { localStorage.setItem('lastActiveAccountId', accountId); } catch (_) {}
                                try { sessionStorage.setItem('lastActiveAccountId', accountId); } catch (_) {}
                            }""",
                            target_workspace_id,
                        )
                    except Exception:
                        pass
                if _is_workspace_or_consent_page(final_url):
                    if _click_first_visible(
                        page,
                        [
                            'button:has-text("Authorize")',
                            'button:has-text("Allow")',
                            'button:has-text("Continue")',
                            'button:has-text("Accept")',
                            'button:has-text("Confirm")',
                            'button[type="submit"]',
                            'button[data-testid*="consent"]',
                            'button[data-testid*="authorize"]',
                            'button[data-testid*="allow"]',
                            'button[name="action"][value="accept"]',
                            "form button",
                        ],
                        capture_exception=capture,
                    ):
                        time.sleep(1)
                        continue
                    try:
                        submitted = page.evaluate(
                            "() => { const f = document.querySelector('form'); "
                            "if (f) { f.submit(); return true; } return false; }"
                        )
                        if submitted:
                            time.sleep(1)
                            continue
                    except Exception as exc:
                        capture(str(exc))
                time.sleep(0.5)
            if not callback["url"] and capture_diagnostics:
                diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_fast")
    except Exception as exc:
        if not capture(str(exc)):
            raise
    finally:
        rmtree(profile_dir, ignore_errors=True)

    if not callback["url"]:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="callback_not_captured",
            failure_message=_callback_not_captured_message(
                "打开 Codex authorize 后未捕获 localhost callback",
                final_url,
                diagnostics["message"],
            ),
            callback_url_seen=False,
            final_url=final_url,
        )

    token_result = _exchange_callback(
        callback_url=callback["url"],
        verifier=verifier,
        client_id=codex_client_id,
        proxy=proxy,
    )
    return token_result


def acquire_codex_rt_with_browser_login(
    *,
    email: str,
    password: str,
    mail_provider: BrowserOtpProvider,
    proxy: str = "",
    codex_client_id: str = DEFAULT_CODEX_CLIENT_ID,
    target_workspace_id: str = "",
    target_workspace_name: str = "",
    phone_provider: BrowserPhoneOtpProvider | None = None,
    totp_code_provider: Callable[[], str] | None = None,
    cookie_header: str = "",
    auth_cookie_header: str = "",
    timeout_s: int = 240,
    headless: bool | None = None,
) -> CodexBrowserRtResult:
    if not email.strip():
        return CodexBrowserRtResult(
            ok=False,
            failure_code="missing_email",
            failure_message="补 RT browser login 需要账号邮箱",
        )
    try:
        from browserforge.fingerprints import Screen
        from camoufox.sync_api import Camoufox
    except Exception as exc:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="browser_runtime_unavailable",
            failure_message=f"{type(exc).__name__}: {str(exc)[:300]}",
        )

    verifier = _b64url_no_pad(secrets.token_bytes(64))
    challenge = _b64url_no_pad(hashlib.sha256(verifier.encode()).digest())
    state = _b64url_no_pad(secrets.token_bytes(24))
    auth_url = "https://auth.openai.com/oauth/authorize?" + urlencode(
        {
            "client_id": codex_client_id,
            "response_type": "code",
            "redirect_uri": CODEX_REDIRECT_URI,
            "scope": "openid email profile offline_access",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
        }
    )
    proxy_cfg = _camoufox_proxy(proxy)
    profile_dir = tempfile.mkdtemp(prefix="codex_rt_login_")
    callback = {"url": ""}
    final_url = ""
    diagnostics = {"message": ""}
    otp_sent_at = time.time()
    otp_fetched = False
    otp_submit_at = 0.0
    otp_retry_count = 0
    otp_retry_max = 2
    totp_submit_at = 0.0
    totp_retry_count = 0
    totp_retry_max = 1
    passwordless_otp_started = False

    def capture(value: str) -> bool:
        url = _extract_callback_url(value, expected_state=state)
        if not url:
            return False
        callback["url"] = url
        return True

    try:
        prepare_domain_mailbox(mail_provider, email=email)
        with Camoufox(
            headless=(
                bool(headless)
                if headless is not None
                else not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            ),
            humanize=False,
            persistent_context=True,
            user_data_dir=profile_dir,
            os="windows",
            screen=Screen(max_width=1920, max_height=1080),
            proxy=proxy_cfg,
            geoip=True,
            locale="en-US",
        ) as ctx:
            _seed_context_cookies(ctx, cookie_header, ".chatgpt.com")
            _seed_context_cookies(ctx, auth_cookie_header, ".auth.openai.com")
            _seed_context_cookies(ctx, auth_cookie_header, ".openai.com")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            _seed_account_cookie(ctx, target_workspace_id)
            _install_callback_capture(ctx, page, capture)
            try:
                page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                capture(str(exc))

            _submit_email_if_visible(page, email)
            otp_sent_at = time.time()
            if password:
                _submit_password_if_visible(page, password)

            end = time.time() + max(30, timeout_s)
            while time.time() < end:
                final_url = str(getattr(page, "url", "") or "")
                if callback["url"] or capture(final_url):
                    _wait_after_callback_capture(page)
                    break

                account_failure = _account_deactivated_result(page, final_url)
                if account_failure is not None:
                    return account_failure

                if _select_existing_account_if_visible(page, email):
                    time.sleep(1)
                    continue

                if _submit_email_if_visible(page, email):
                    otp_sent_at = time.time()
                    time.sleep(2)
                    continue

                if _is_password_page(page, final_url):
                    if password:
                        if _submit_password_if_visible(page, password):
                            time.sleep(3)
                            continue
                        # The password route can become visible before its form is
                        # hydrated. Keep waiting for that form instead of treating a
                        # generic Retry control as evidence that an email OTP was sent.
                        time.sleep(1)
                        continue
                    if passwordless_otp_started:
                        return CodexBrowserRtResult(
                            ok=False,
                            failure_code="passwordless_otp_navigation_failed",
                            failure_message="邮箱验证码已发送，但页面仍停留在密码登录页",
                            final_url=final_url,
                        )
                    otp_sent_at = time.time()
                    try:
                        _start_passwordless_email_login(page)
                    except Exception as exc:
                        return CodexBrowserRtResult(
                            ok=False,
                            failure_code="passwordless_otp_send_failed",
                            failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                            final_url=final_url,
                        )
                    passwordless_otp_started = True
                    otp_fetched = False
                    otp_submit_at = 0.0
                    time.sleep(1)
                    continue

                if password and _submit_password_if_visible(page, password):
                    time.sleep(3)
                    continue

                if phone_provider is not None and _is_add_phone_url(final_url):
                    phone_result = _complete_add_phone_with_provider(page, phone_provider)
                    if phone_result is not None:
                        return phone_result
                    time.sleep(0.5)
                    continue
                phone_failure = _phone_verification_failure(page, final_url)
                if phone_failure:
                    return _phone_failure_result(phone_failure, final_url=final_url)
                if _is_add_phone_url(final_url):
                    time.sleep(1)
                    continue

                if _is_mfa_challenge_url(final_url):
                    if totp_code_provider is None:
                        return CodexBrowserRtResult(
                            ok=False,
                            failure_code="totp_code_provider_missing",
                            failure_message="账号要求 TOTP，但没有可用的 2FAuth 记录或客户端配置",
                            final_url=final_url,
                        )
                    if not _has_otp_input(page):
                        time.sleep(1)
                        continue
                    if not totp_submit_at:
                        try:
                            code = str(totp_code_provider() or "").strip()
                        except Exception as exc:
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="totp_code_fetch_failed",
                                failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                                final_url=final_url,
                            )
                        if not _fill_otp(page, code):
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="totp_input_not_found",
                                failure_message="检测到 TOTP 页面但未找到可填写的验证码输入框",
                                final_url=final_url,
                            )
                        if not _click_first_visible(
                            page,
                            [
                                'button[type="submit"]',
                                'button:has-text("Continue")',
                                'button:has-text("Verify")',
                            ],
                        ):
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="totp_submit_not_found",
                                failure_message="检测到 TOTP 页面但未找到提交按钮",
                                final_url=final_url,
                            )
                        totp_submit_at = time.time()
                        time.sleep(3)
                        continue
                    if time.time() - totp_submit_at > 30:
                        if totp_retry_count >= totp_retry_max:
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="totp_verification_stuck",
                                failure_message="TOTP 提交后仍停留在 MFA challenge 页面",
                                final_url=final_url,
                            )
                        totp_retry_count += 1
                        totp_submit_at = 0.0
                    time.sleep(1)
                    continue

                if _is_otp_page(page, final_url):
                    if not _has_otp_input(page):
                        if _click_otp_retry_control(page):
                            otp_sent_at = time.time()
                            otp_fetched = False
                            otp_submit_at = 0.0
                            otp_retry_count += 1
                            time.sleep(2)
                            continue
                        if _is_email_verification_url(final_url):
                            time.sleep(1)
                            continue
                    if not otp_fetched:
                        otp = mail_provider.wait_for_otp_by_email(
                            email=email.strip(),
                            timeout_s=180,
                            issued_after=otp_sent_at,
                        )
                        code = str(getattr(otp, "code", "") or "")
                        if not code:
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="otp_empty",
                                failure_message="外部邮箱接口返回空验证码",
                                final_url=final_url,
                            )
                        if not _fill_otp(page, code):
                            if _click_otp_retry_control(page) and otp_retry_count < otp_retry_max:
                                otp_sent_at = time.time()
                                otp_fetched = False
                                otp_submit_at = 0.0
                                otp_retry_count += 1
                                time.sleep(2)
                                continue
                            diagnostics["message"] = _capture_page_diagnostics(
                                page, "codex_rt_otp_input_not_found"
                            )
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="otp_input_not_found",
                                failure_message=_callback_not_captured_message(
                                    "检测到 OTP 页面但未找到可填写的验证码输入框",
                                    final_url,
                                    diagnostics["message"],
                                ),
                                final_url=final_url,
                            )
                        _click_first_visible(
                            page,
                            [
                                'button[type="submit"]',
                                'button:has-text("Continue")',
                                'button:has-text("Verify")',
                            ],
                        )
                        otp_fetched = True
                        otp_submit_at = time.time()
                        time.sleep(3)
                        continue
                    if otp_submit_at and time.time() - otp_submit_at > 30:
                        if otp_retry_count >= otp_retry_max:
                            diagnostics["message"] = _capture_page_diagnostics(
                                page, "codex_rt_otp_stuck"
                            )
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="otp_verification_stuck",
                                failure_message=_callback_not_captured_message(
                                    "OTP 提交后仍停留 email-verification",
                                    final_url,
                                    diagnostics["message"],
                                ),
                                final_url=final_url,
                            )
                        if not _click_otp_retry_control(page):
                            diagnostics["message"] = _capture_page_diagnostics(
                                page, "codex_rt_otp_no_retry"
                            )
                            return CodexBrowserRtResult(
                                ok=False,
                                failure_code="otp_retry_control_not_found",
                                failure_message=_callback_not_captured_message(
                                    "OTP 提交后仍停留 email-verification，但未找到 Resend/Try again",
                                    final_url,
                                    diagnostics["message"],
                                ),
                                final_url=final_url,
                            )
                        otp_sent_at = time.time()
                        otp_fetched = False
                        otp_submit_at = 0.0
                        otp_retry_count += 1
                        time.sleep(2)
                        continue

                if _is_workspace_or_consent_page(final_url):
                    if _select_workspace_if_visible(
                        page,
                        target_workspace_id=target_workspace_id,
                        target_workspace_name=target_workspace_name,
                    ):
                        time.sleep(2)
                        continue
                    if _click_first_visible(
                        page,
                        [
                            'button:has-text("Authorize")',
                            'button:has-text("Allow")',
                            'button:has-text("Continue")',
                            'button:has-text("Accept")',
                            'button:has-text("Confirm")',
                            'button[type="submit"]',
                            'button[data-testid*="consent"]',
                            'button[data-testid*="authorize"]',
                            'button[data-testid*="allow"]',
                            'button[name="action"][value="accept"]',
                            "form button",
                        ],
                        capture_exception=capture,
                    ):
                        time.sleep(2)
                        continue
                    try:
                        submitted = page.evaluate(
                            "() => { const f = document.querySelector('form'); "
                            "if (f) { f.submit(); return true; } return false; }"
                        )
                        if submitted:
                            time.sleep(2)
                            continue
                    except Exception as exc:
                        capture(str(exc))

                time.sleep(1)
            if not callback["url"]:
                diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_login")
    except Exception as exc:
        if not capture(str(exc)):
            return CodexBrowserRtResult(
                ok=False,
                failure_code="browser_login_exception",
                failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                callback_url_seen=False,
                final_url=final_url,
            )
    finally:
        rmtree(profile_dir, ignore_errors=True)

    if not callback["url"]:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="callback_not_captured",
            failure_message=_callback_not_captured_message(
                "完整浏览器登录后未捕获 localhost callback",
                final_url,
                diagnostics["message"],
            ),
            callback_url_seen=False,
            final_url=final_url,
        )

    return _exchange_callback(
        callback_url=callback["url"],
        verifier=verifier,
        client_id=codex_client_id,
        proxy=proxy,
    )


def _install_callback_capture(ctx, page, capture: Callable[[str], bool]) -> None:
    def intercept(route) -> None:
        capture(route.request.url)
        try:
            route.fulfill(status=200, content_type="text/html", body="<html>OK</html>")
        except Exception:
            route.abort()

    def bind(candidate) -> None:
        candidate.on("request", lambda request: capture(request.url))
        candidate.on("framenavigated", lambda frame: capture(frame.url))

    ctx.route("http://localhost:1455/**", intercept)
    bind(page)
    ctx.on("page", bind)


def _wait_after_callback_capture(page) -> None:
    if CALLBACK_CAPTURE_SETTLE_MS <= 0:
        return
    try:
        page.wait_for_timeout(CALLBACK_CAPTURE_SETTLE_MS)
    except Exception:
        time.sleep(CALLBACK_CAPTURE_SETTLE_MS / 1000)


def _exchange_callback(
    *,
    callback_url: str,
    verifier: str,
    client_id: str,
    proxy: str,
) -> CodexBrowserRtResult:
    code = (parse_qs(urlparse(callback_url).query).get("code") or [""])[0]
    if not code:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="callback_missing_code",
            failure_message="localhost callback missing code",
            callback_url_seen=True,
        )
    try:
        from curl_cffi.requests import Session as CffiSession

        http = CffiSession(impersonate=BROWSER_IMPERSONATE)
        if proxy:
            http.proxies = {"http": proxy, "https": proxy}
        response = http.post(
            "https://auth.openai.com/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "redirect_uri": CODEX_REDIRECT_URI,
                "code_verifier": verifier,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=30,
        )
        if response.status_code != 200:
            return CodexBrowserRtResult(
                ok=False,
                failure_code=f"oauth_token_http_{response.status_code}",
                failure_message=str(response.text or "")[:500],
                callback_url_seen=True,
            )
        body = response.json()
        refresh_token = str(body.get("refresh_token") or "")
        return CodexBrowserRtResult(
            ok=bool(refresh_token),
            refresh_token=refresh_token,
            access_token=str(body.get("access_token") or ""),
            id_token=str(body.get("id_token") or ""),
            token_type=str(body.get("token_type") or ""),
            scope=str(body.get("scope") or ""),
            failure_code="" if refresh_token else "missing_refresh_token",
            failure_message="" if refresh_token else "oauth token response missing refresh_token",
            callback_url_seen=True,
        )
    except Exception as exc:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="oauth_token_exception",
            failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            callback_url_seen=True,
        )


def _submit_email_if_visible(page, email: str) -> bool:
    try:
        email_input = page.query_selector('input[type="email"]:visible') or page.query_selector(
            'input[name="email"]:visible'
        )
        if not email_input:
            return False
        email_input.click(timeout=3000)
        email_input.fill(email.strip())
        return _click_first_visible(
            page,
            ['button[type="submit"]', 'button:has-text("Continue")', "#btnNext"],
        )
    except Exception:
        return False


def _submit_password_if_visible(page, password: str) -> bool:
    if not password:
        return False
    try:
        password_input = page.query_selector('input[type="password"]:visible')
        if not password_input:
            return False
        password_input.click(timeout=3000)
        password_input.fill(password)
        return _click_first_visible(
            page,
            ['button[type="submit"]', 'button:has-text("Continue")'],
        )
    except Exception:
        return False


def _has_password_input(page) -> bool:
    try:
        return bool(page.query_selector('input[type="password"]:visible'))
    except Exception:
        return False


def _is_password_page(page, current_url: str) -> bool:
    url = str(current_url or "").lower()
    return (
        "/log-in/password" in url or "/create-account/password" in url or _has_password_input(page)
    )


def _start_passwordless_email_login(page) -> None:
    _browser_empty_post(page, "/api/accounts/passwordless/send-otp")
    page.goto(
        "https://auth.openai.com/email-verification",
        wait_until="domcontentloaded",
        timeout=30000,
    )


def _is_otp_page(page, current_url: str) -> bool:
    if (
        _is_phone_otp_url(current_url)
        or _is_mfa_challenge_url(current_url)
        or _is_password_page(page, current_url)
    ):
        return False
    if _has_otp_input(page):
        return True
    if "email-otp" in current_url or "passwordless" in current_url:
        return True
    if _is_email_verification_url(current_url):
        return True
    return False


def _is_mfa_challenge_url(current_url: str) -> bool:
    return "/mfa-challenge/" in str(current_url or "").lower()


def _is_email_verification_url(current_url: str) -> bool:
    return "email-verification" in str(current_url or "")


def _has_otp_input(page) -> bool:
    try:
        if page.query_selector('input[autocomplete="one-time-code"]:visible'):
            return True
        if page.query_selector('input[inputmode="numeric"]:visible:not([type="password"])'):
            return True
        digit_inputs = page.query_selector_all(
            'input[maxlength="1"]:visible:not([type="password"])'
        )
        return len(digit_inputs or []) >= 4
    except Exception:
        return False


def _has_otp_retry_control(page) -> bool:
    return (
        _find_first_visible(
            page,
            [
                'button:has-text("Resend email")',
                'a:has-text("Resend email")',
                'button:has-text("Resend")',
                'a:has-text("Resend")',
                'button:has-text("Try again")',
                'a:has-text("Try again")',
                'button:has-text("Retry")',
                'a:has-text("Retry")',
                '[data-testid*="resend"]',
                '[data-testid*="retry"]',
            ],
        )
        is not None
    )


def _click_otp_retry_control(page) -> bool:
    return _click_first_visible(
        page,
        [
            'button:has-text("Resend email")',
            'a:has-text("Resend email")',
            'button:has-text("Resend")',
            'a:has-text("Resend")',
            'button:has-text("Try again")',
            'a:has-text("Try again")',
            'button:has-text("Retry")',
            'a:has-text("Retry")',
            '[data-testid*="resend"]',
            '[data-testid*="retry"]',
        ],
    )


def _fill_otp(page, code: str) -> bool:
    value = "".join(ch for ch in str(code or "") if ch.isdigit())[:6]
    if not value:
        return False
    try:
        single = None
        for selector in (
            'input[autocomplete="one-time-code"]:visible',
            'input[inputmode="numeric"]:not([maxlength="1"]):visible',
            'input[aria-label*="one-time" i]:visible',
            'input[aria-label*="authentication" i]:visible',
            'input[placeholder*="one-time" i]:visible',
            'input[placeholder*="code" i]:visible',
            'input[type="text"]:visible',
        ):
            single = page.query_selector(selector)
            if single:
                break
        if single:
            single.click(timeout=3000)
            single.fill(value)
            return True
        digits = page.query_selector_all(
            'input[maxlength="1"][inputmode="numeric"]:visible'
        ) or page.query_selector_all('input[maxlength="1"]:visible')
        if len(digits) >= len(value):
            for idx, ch in enumerate(value):
                digits[idx].click(timeout=3000)
                digits[idx].fill(ch)
            return True
    except Exception:
        return False
    return False


def _phone_verification_failure(page, current_url: str) -> str:
    url = str(current_url or "")
    if "phone-otp/select-channel" in url:
        return "phone_otp_select_channel"
    if not _is_add_phone_url(url):
        return "phone_verification_required" if _is_phone_otp_url(url) else ""
    try:
        if _click_first_visible(
            page,
            [
                'a:has-text("Skip")',
                'button:has-text("Skip")',
                'a:has-text("Not now")',
                'button:has-text("Not now")',
                'a:has-text("Maybe later")',
                'button:has-text("Maybe later")',
                'a:has-text("Skip for now")',
                'button:has-text("Skip for now")',
                '[data-testid*="skip"]',
                'a[href*="skip"]',
            ],
        ):
            return ""
    except Exception:
        pass
    return "add_phone_blocked"


def _complete_add_phone_with_provider(
    page,
    phone_provider: BrowserPhoneOtpProvider,
) -> CodexBrowserRtResult | None:
    lease = None
    try:
        _wait_for_add_phone_context(page)
        max_number_attempts = _phone_number_retry_limit(phone_provider)
        send_continue = ""
        for attempt in range(1, max_number_attempts + 1):
            lease = phone_provider.allocate()
            lease_id = str(getattr(lease, "lease_id", "") or "").strip()
            phone_e164 = str(getattr(lease, "phone_e164", "") or "").strip()
            if not lease_id or not phone_e164:
                raise RuntimeError("Hero SMS returned an incomplete phone lease")
            try:
                send_continue = _submit_phone_number_in_page(page, phone_e164)
                break
            except AddPhoneNumberRejectedError as exc:
                _mark_phone_lease_failed(phone_provider, lease_id, exc.reason)
                lease = None
                if attempt >= max_number_attempts:
                    raise RuntimeError(
                        f"phone number rejected after {max_number_attempts} attempts: {exc}"
                    ) from exc
        else:
            raise RuntimeError(f"phone number submit exhausted {max_number_attempts} attempts")

        lease_id = str(getattr(lease, "lease_id", "") or "").strip()
        if "select-channel" in send_continue:
            _mark_phone_lease_failed(phone_provider, lease_id, "phone_otp_select_channel")
            return _phone_failure_result(
                "phone_otp_select_channel",
                final_url=send_continue,
            )

        code = str(phone_provider.poll_otp(lease_id) or "").strip()
        if not code:
            raise RuntimeError("Hero SMS returned an empty phone OTP")
        validate_continue = _submit_phone_otp_in_page(page, code)
        if "select-channel" in validate_continue:
            phone_provider.mark_verified(lease_id)
            return _phone_failure_result(
                "phone_otp_select_channel",
                final_url=validate_continue,
            )
        phone_provider.mark_verified(lease_id)
        return None
    except Exception as exc:
        lease_id = str(getattr(lease, "lease_id", "") or "").strip()
        if isinstance(exc, AccountDeactivatedDuringPhoneFlowError):
            _mark_phone_lease_failed(phone_provider, lease_id, "account_deactivated")
            return CodexBrowserRtResult(
                ok=False,
                failure_code="account_deactivated",
                failure_message=str(exc),
                final_url=str(getattr(page, "url", "") or ""),
            )
        if isinstance(exc, TimeoutError):
            _mark_phone_lease_failed(phone_provider, lease_id, "phone_otp_timeout")
            return CodexBrowserRtResult(
                ok=False,
                failure_code=HERO_ADD_PHONE_OTP_TIMEOUT,
                failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                final_url=str(getattr(page, "url", "") or ""),
            )
        if isinstance(exc, AddPhoneInvalidStateError) or (
            isinstance(exc, BrowserApiRequestError)
            and exc.path == "/api/accounts/add-phone/send"
            and exc.upstream_error_code == "invalid_state"
        ):
            return CodexBrowserRtResult(
                ok=False,
                failure_code=HERO_ADD_PHONE_INVALID_STATE,
                failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
                final_url=str(getattr(page, "url", "") or ""),
            )
        _mark_phone_lease_failed(
            phone_provider,
            lease_id,
            f"hero_add_phone_failed:{type(exc).__name__}",
        )
        return CodexBrowserRtResult(
            ok=False,
            failure_code="hero_add_phone_failed",
            failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            final_url=str(getattr(page, "url", "") or ""),
        )


def _phone_number_retry_limit(phone_provider: BrowserPhoneOtpProvider) -> int:
    delegate = getattr(phone_provider, "_delegate", None)
    cfg = getattr(phone_provider, "cfg", None) or getattr(delegate, "cfg", None)
    raw = (
        os.environ.get("PHONE_PROTOCOL_MAX_NUMBER_ATTEMPTS", "")
        or str(getattr(cfg, "max_number_attempts", "") or "")
        or "3"
    )
    try:
        return max(1, min(int(raw), 10))
    except (TypeError, ValueError):
        return 3


def _wait_for_add_phone_context(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:
        pass
    try:
        page.wait_for_selector(
            'input[type="tel"], input[name="phone_number"], input[autocomplete="tel"]',
            state="visible",
            timeout=10_000,
        )
    except Exception:
        pass
    if ADD_PHONE_CONTEXT_SETTLE_MS <= 0:
        return
    try:
        page.wait_for_timeout(ADD_PHONE_CONTEXT_SETTLE_MS)
    except Exception:
        time.sleep(ADD_PHONE_CONTEXT_SETTLE_MS / 1000)


def _submit_phone_number_in_page(page, phone_e164: str) -> str:
    phone_input = _find_first_visible(
        page,
        [
            'input[type="tel"]',
            'input[name="phoneNumber"]',
            'input[name="phone_number"]',
            'input[autocomplete="tel"]',
        ],
    )
    if phone_input is None:
        raise RuntimeError("add-phone page phone input not found")
    phone_input.click(timeout=3_000)
    phone_input.fill(phone_e164)
    try:
        page.wait_for_timeout(500)
    except Exception:
        time.sleep(0.5)

    _click_first_visible(
        page,
        [
            '[role="radio"]:has-text("Text Message")',
            'button:has-text("Text Message")',
            'label:has-text("Text Message")',
        ],
    )
    if not _click_first_visible(
        page,
        [
            'form button[type="submit"]',
            'button[type="submit"]',
            'button:has-text("Continue")',
        ],
    ):
        raise RuntimeError("add-phone page Continue button not found")
    return _wait_for_phone_page_transition(page, from_phone_otp=False)


def _submit_phone_otp_in_page(page, code: str) -> str:
    if not _fill_otp(page, code):
        raise RuntimeError("phone verification page OTP input not found")
    try:
        page.wait_for_timeout(500)
    except Exception:
        time.sleep(0.5)
    if not _click_first_visible(
        page,
        [
            'form button[type="submit"]',
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Verify")',
        ],
    ):
        raise RuntimeError("phone verification page submit button not found")
    return _wait_for_phone_page_transition(page, from_phone_otp=True)


def _wait_for_phone_page_transition(page, *, from_phone_otp: bool) -> str:
    end = time.time() + 30
    while time.time() < end:
        current_url = str(getattr(page, "url", "") or "")
        account_failure = _account_deactivated_result(page, current_url)
        if account_failure is not None:
            raise AccountDeactivatedDuringPhoneFlowError(account_failure.failure_message)
        if (
            _find_first_visible(
                page,
                [
                    'text="Your sign-in session is no longer valid."',
                    'text="Please start over to continue."',
                ],
            )
            is not None
        ):
            raise AddPhoneInvalidStateError(
                "Your sign-in session is no longer valid. Please start over to continue."
            )
        rejection = _visible_phone_number_rejection(page)
        if not from_phone_otp and rejection is not None:
            raise rejection
        if "phone-otp/select-channel" in current_url:
            return current_url
        if from_phone_otp:
            if not _is_phone_otp_url(current_url):
                return current_url
        elif _is_phone_otp_url(current_url):
            return current_url
        time.sleep(0.25)
    stage = "phone OTP submit" if from_phone_otp else "phone number submit"
    raise RuntimeError(f"{stage} did not advance url={getattr(page, 'url', '')}")


def _visible_phone_number_rejection(page) -> AddPhoneNumberRejectedError | None:
    if (
        _find_first_visible(
            page,
            [
                "text=/virtual phone number/i",
                "text=/valid, non-virtual phone number/i",
                "text=/VoIP/i",
            ],
        )
        is not None
    ):
        return AddPhoneNumberRejectedError(
            "phone_number_rejected_virtual",
            "add-phone page rejected virtual/VoIP phone number",
        )
    return None


def _browser_empty_post(page, path: str) -> None:
    result = page.evaluate(
        """async (path) => {
            const headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-access-flow-invocation-id": crypto.randomUUID(),
            };
            const response = await fetch(path, {
                method: "POST",
                credentials: "include",
                headers,
            });
            const text = await response.text();
            return {
                ok: response.ok,
                status: response.status,
                body_head: text.slice(0, 500),
            };
        }""",
        path,
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"{path} returned an invalid browser response")
    if not result.get("ok"):
        raise RuntimeError(
            f"{path} failed: http={result.get('status')} body={str(result.get('body_head') or '')[:300]}"
        )


def _browser_json_post(page, path: str, payload: dict) -> dict:
    result = page.evaluate(
        """async ({ path, payload }) => {
            const headers = {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "x-access-flow-invocation-id": crypto.randomUUID(),
            };
            const response = await fetch(path, {
                method: "POST",
                credentials: "include",
                headers,
                body: JSON.stringify(payload),
            });
            const text = await response.text();
            let data = {};
            try { data = JSON.parse(text); } catch (_) {}
            return {
                ok: response.ok,
                status: response.status,
                data,
                body_head: text.slice(0, 500),
            };
        }""",
        {"path": path, "payload": payload},
    )
    if not isinstance(result, dict):
        raise RuntimeError(f"{path} returned an invalid browser response")
    if not result.get("ok"):
        raise BrowserApiRequestError(
            path=path,
            status=int(result.get("status") or 0),
            data=result.get("data") if isinstance(result.get("data"), dict) else {},
            body_head=str(result.get("body_head") or ""),
        )
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _phone_continue_url(payload: dict) -> str:
    page = payload.get("page") if isinstance(payload, dict) else None
    page_payload = page.get("payload") if isinstance(page, dict) else None
    value = str(
        payload.get("continue_url")
        or (page_payload.get("continue_url") if isinstance(page_payload, dict) else "")
        or (page_payload.get("url") if isinstance(page_payload, dict) else "")
        or ""
    ).strip()
    return urljoin("https://auth.openai.com", value) if value else ""


def _is_select_channel_response(payload: dict, continue_url: str) -> bool:
    page_type = _phone_page_type(payload)
    return "select-channel" in str(continue_url or "").lower() or "select_channel" in page_type


def _phone_page_type(payload: dict) -> str:
    page = payload.get("page") if isinstance(payload, dict) else None
    return str(page.get("type") if isinstance(page, dict) else "").strip().lower()


def _navigate_phone_continue(
    page,
    continue_url: str,
    *,
    reload_if_empty: bool = False,
) -> None:
    try:
        if continue_url:
            page.goto(continue_url, wait_until="domcontentloaded", timeout=30000)
        elif reload_if_empty:
            page.reload(wait_until="domcontentloaded", timeout=30000)
    except Exception:
        pass


def _mark_phone_lease_failed(
    phone_provider: BrowserPhoneOtpProvider,
    lease_id: str,
    reason: str,
) -> None:
    if not lease_id:
        return
    try:
        phone_provider.mark_failed(lease_id, reason)
    except Exception:
        pass


def _is_add_phone_url(current_url: str) -> bool:
    value = str(current_url or "")
    return "/add-phone" in value or "phone-number" in value


def _is_phone_otp_url(current_url: str) -> bool:
    value = str(current_url or "")
    return "/phone-verification" in value or "/phone-otp/" in value


def _phone_failure_result(failure_code: str, *, final_url: str) -> CodexBrowserRtResult:
    messages = {
        "phone_otp_select_channel": (
            "auth.openai.com 进入 phone-otp/select-channel，Personal Codex 授权永久跳过"
        ),
        "add_phone_blocked": "auth.openai.com 要求添加手机号且没有可用跳过入口",
        "phone_verification_required": "auth.openai.com 仍停留在手机验证码流程",
    }
    return CodexBrowserRtResult(
        ok=False,
        failure_code=failure_code,
        failure_message=messages.get(failure_code, failure_code),
        final_url=final_url,
    )


def _account_deactivated_result(page, final_url: str) -> CodexBrowserRtResult | None:
    if (
        _find_first_visible(
            page,
            [
                "text=/account has been deleted or deactivated/i",
                "text=/account_deactivated/i",
            ],
        )
        is None
    ):
        return None
    return CodexBrowserRtResult(
        ok=False,
        failure_code="account_deactivated",
        failure_message=("You do not have an account because it has been deleted or deactivated."),
        final_url=str(final_url or ""),
    )


def _is_workspace_or_consent_page(current_url: str) -> bool:
    return "/workspace" in current_url or "/consent" in current_url or "/authorize" in current_url


def _select_existing_account_if_visible(page, email: str) -> bool:
    expected = str(email or "").strip().casefold()
    if not expected:
        return False
    chooser_selectors = (
        'form[action*="/choose-an-account"] button[name="session_id"]',
        'button[data-dd-action-name="Select existing session"]',
    )
    try:
        for selector in chooser_selectors:
            for element in page.query_selector_all(selector):
                text = str(element.inner_text() or "").casefold()
                if expected not in text:
                    continue
                try:
                    element.click(timeout=5_000, no_wait_after=True)
                except Exception:
                    element.evaluate(
                        "(el) => { "
                        "if (el.form && typeof el.form.requestSubmit === 'function') { "
                        "el.form.requestSubmit(el); "
                        "} else { el.click(); } "
                        "}"
                    )
                return True

        current_url = str(getattr(page, "url", "") or "")
        if "/choose-an-account" not in current_url:
            return False
        return bool(
            page.evaluate(
                """(expectedEmail) => {
                    const normalized = String(expectedEmail || '').trim().toLowerCase();
                    if (!normalized) return false;
                    const candidates = Array.from(document.querySelectorAll(
                        'button, a, [role="button"], [tabindex]'
                    ));
                    const target = candidates.find((element) =>
                        String(element.innerText || element.textContent || '')
                            .toLowerCase()
                            .includes(normalized)
                    );
                    if (!target) return false;
                    target.click();
                    return true;
                }""",
                expected,
            )
        )
    except Exception:
        return False


def _click_first_visible(
    page,
    selectors: list[str],
    *,
    capture_exception: Callable[[str], bool] | None = None,
) -> bool:
    button = _find_first_visible(page, selectors)
    if not button:
        return False
    try:
        button.evaluate("(el) => { el.click(); return true; }")
    except Exception as evaluate_exc:
        if capture_exception is not None and capture_exception(str(evaluate_exc)):
            return True
        try:
            button.click(timeout=3000, no_wait_after=True)
        except Exception as click_exc:
            if capture_exception is not None and capture_exception(str(click_exc)):
                return True
            raise
    return True


def _find_first_visible(page, selectors: list[str]):
    for selector in selectors:
        try:
            button = page.query_selector(selector)
            if button and button.is_visible():
                return button
        except Exception:
            continue
    return None


def _callback_not_captured_message(prefix: str, final_url: str, diagnostics: str = "") -> str:
    value = str(final_url or "")
    if "/consent" in value:
        message = f"{prefix}; stopped_on=codex_consent"
    elif "/authorize" in value:
        message = f"{prefix}; stopped_on=oauth_authorize"
    else:
        message = prefix
    if diagnostics:
        return f"{message}; {diagnostics}"
    return message


def _capture_page_diagnostics(page, label: str) -> str:
    try:
        os.makedirs(CODEX_OAUTH_DEBUG_DIR, exist_ok=True)
        suffix = f"{int(time.time())}-{secrets.token_hex(4)}"
        screenshot_path = os.path.join(CODEX_OAUTH_DEBUG_DIR, f"{label}-{suffix}.png")
        html_path = os.path.join(CODEX_OAUTH_DEBUG_DIR, f"{label}-{suffix}.html")
        title = ""
        clickables = []
        try:
            title = str(page.title() or "")[:120]
        except Exception:
            title = ""
        try:
            clickables = page.evaluate(
                """() => Array.from(document.querySelectorAll(
                    'button,a,[role="button"],input[type="submit"],form'
                )).map((el) => ({
                    tag: el.tagName,
                    text: (el.innerText || el.textContent || el.value || '').trim().slice(0, 80),
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    value: el.getAttribute('value') || '',
                    id: el.id || '',
                    testid: el.getAttribute('data-testid') || '',
                    role: el.getAttribute('role') || '',
                    visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                    disabled: !!el.disabled,
                })).filter((item) => item.text || item.id || item.testid || item.name || item.role).slice(0, 30)"""
            )
        except Exception as exc:
            clickables = [{"error": f"{type(exc).__name__}: {str(exc)[:120]}"}]
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception:
            screenshot_path = ""
        try:
            html = str(page.content() or "")
            with open(html_path, "w", encoding="utf-8") as handle:
                handle.write(html)
        except Exception:
            html_path = ""
        return (
            f"debug_title={title!r}; debug_screenshot={screenshot_path}; "
            f"debug_html={html_path}; debug_clickables={clickables}"
        )[:1800]
    except Exception as exc:
        return f"debug_capture_failed={type(exc).__name__}: {str(exc)[:200]}"


def _select_workspace_if_visible(
    page,
    *,
    target_workspace_id: str = "",
    target_workspace_name: str = "",
) -> bool:
    targets = [
        str(target_workspace_id or "").strip().lower(),
        str(target_workspace_name or "").strip().lower(),
    ]
    targets = [item for item in targets if item]
    if not targets:
        return False
    try:
        return bool(
            page.evaluate(
                """(targets) => {
                    const inputMatches = (input) => {
                        const attrs = [
                            input.value || '',
                            input.getAttribute('data-account-id') || '',
                            input.getAttribute('data-workspace-id') || '',
                        ].join(' ').toLowerCase();
                        return targets.some((target) => attrs.includes(target));
                    };
                    const radioInputs = Array.from(document.querySelectorAll(
                        'input[type="radio"][name="workspace_id"]'
                    ));
                    for (const input of radioInputs) {
                        if (!inputMatches(input)) {
                            continue;
                        }
                        if (input.checked) {
                            return false;
                        }
                        const label = input.closest('label');
                        (label || input).click();
                        return true;
                    }

                    const candidates = Array.from(document.querySelectorAll('label,button,a,[role="button"]'));
                    for (const el of candidates) {
                        const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                        const attrs = [
                            el.getAttribute('data-testid') || '',
                            el.getAttribute('data-account-id') || '',
                            el.getAttribute('data-workspace-id') || '',
                            el.getAttribute('href') || '',
                            el.getAttribute('value') || '',
                        ].join(' ').toLowerCase();
                        if (!targets.some((target) => text.includes(target) || attrs.includes(target))) {
                            continue;
                        }
                        const checkedInput = el.querySelector && el.querySelector('input[type="radio"]:checked');
                        if (checkedInput) {
                            return false;
                        }
                        const clickable = el.closest('button,a,[role="button"],label') || el;
                        clickable.click();
                        return true;
                    }
                    return false;
                }""",
                targets,
            )
        )
    except Exception:
        return False


def _seed_account_cookie(ctx, account_id: str) -> None:
    account_id = str(account_id or "").strip()
    if not account_id:
        return
    ctx.add_cookies(
        [
            {
                "name": "_account",
                "value": account_id,
                "domain": ".chatgpt.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            }
        ]
    )


def _seed_context_cookies(ctx, cookie_header: str, domain: str) -> None:
    cookies = []
    for raw in (cookie_header or "").split(";"):
        if "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or not value:
            continue
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": "/",
                "httpOnly": name.lower().startswith("__secure-") or name.lower().startswith("auth"),
                "secure": True,
                "sameSite": "Lax",
            }
        )
    if cookies:
        ctx.add_cookies(cookies)


def _extract_callback_url(text: str, *, expected_state: str) -> str:
    value = str(text or "").replace("&amp;", "&")
    if "localhost:1455" not in value or "code=" not in value:
        return ""
    match = re.search(r"https?://localhost:1455/auth/callback\?[^\s\"'<>]+", value)
    if not match:
        return ""
    url = match.group(0).rstrip(").,;")
    params = parse_qs(urlparse(url).query)
    if not (params.get("code") or [""])[0]:
        return ""
    state = (params.get("state") or [""])[0]
    if state and state != expected_state:
        return ""
    return url


def _camoufox_proxy(proxy_url: str) -> dict | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        return None
    return {
        "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
        "username": parsed.username or "",
        "password": parsed.password or "",
    }


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")
