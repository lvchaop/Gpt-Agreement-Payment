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
from typing import Protocol
from urllib.parse import parse_qs, urlencode, urlparse


DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_OAUTH_DEBUG_DIR = "/private/tmp/refactor-app/codex-oauth-debug"


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
    ):
        ...


def acquire_codex_rt_with_existing_browser_session(
    *,
    cookie_header: str,
    auth_cookie_header: str = "",
    proxy: str = "",
    codex_client_id: str = DEFAULT_CODEX_CLIENT_ID,
    target_workspace_id: str = "",
    target_workspace_name: str = "",
    timeout_s: int = 45,
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

    def capture(value: str) -> bool:
        url = _extract_callback_url(value, expected_state=state)
        if not url:
            return False
        callback["url"] = url
        return True

    try:
        with Camoufox(
            headless=not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
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

            def intercept(route):
                capture(route.request.url)
                try:
                    route.fulfill(status=200, content_type="text/html", body="<html>OK</html>")
                except Exception:
                    route.abort()

            page.route("http://localhost:1455/**", intercept)
            page.on("request", lambda req: capture(req.url))
            page.on("framenavigated", lambda frame: capture(frame.url))
            try:
                page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            end = time.time() + max(5, timeout_s)
            while time.time() < end:
                final_url = str(getattr(page, "url", "") or "")
                if callback["url"] or capture(final_url):
                    break
                if "/log-in" in final_url:
                    return CodexBrowserRtResult(
                        ok=False,
                        failure_code="session_cookie_not_accepted",
                        failure_message="已有 cookie 未通过 auth.openai.com 登录态校验，回落到登录页",
                        final_url=final_url,
                    )
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
                            'form button',
                        ],
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
                    except Exception:
                        pass
                time.sleep(0.5)
            if not callback["url"]:
                diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_fast")
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
    timeout_s: int = 240,
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

    def capture(value: str) -> bool:
        url = _extract_callback_url(value, expected_state=state)
        if not url:
            return False
        callback["url"] = url
        return True

    try:
        with Camoufox(
            headless=not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
            humanize=False,
            persistent_context=True,
            user_data_dir=profile_dir,
            os="windows",
            screen=Screen(max_width=1920, max_height=1080),
            proxy=proxy_cfg,
            geoip=True,
            locale="en-US",
        ) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            _seed_account_cookie(ctx, target_workspace_id)

            def intercept(route):
                capture(route.request.url)
                try:
                    route.fulfill(status=200, content_type="text/html", body="<html>OK</html>")
                except Exception:
                    route.abort()

            page.route("http://localhost:1455/**", intercept)
            page.on("request", lambda req: capture(req.url))
            page.on("framenavigated", lambda frame: capture(frame.url))
            try:
                page.goto(auth_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            _submit_email_if_visible(page, email)
            otp_sent_at = time.time()
            if password:
                _submit_password_if_visible(page, password)

            end = time.time() + max(30, timeout_s)
            while time.time() < end:
                final_url = str(getattr(page, "url", "") or "")
                if callback["url"] or capture(final_url):
                    break

                if _submit_email_if_visible(page, email):
                    otp_sent_at = time.time()
                    time.sleep(2)
                    continue

                if password and _submit_password_if_visible(page, password):
                    time.sleep(3)
                    continue

                if not password and _has_password_input(page):
                    return CodexBrowserRtResult(
                        ok=False,
                        failure_code="login_password_required_by_upstream",
                        failure_message="auth.openai.com 当前登录分支要求密码，但该账号未保存密码",
                        final_url=final_url,
                    )

                phone_failure = _phone_verification_failure(page, final_url)
                if phone_failure:
                    return _phone_failure_result(phone_failure, final_url=final_url)
                if _is_add_phone_url(final_url):
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
                            diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_otp_input_not_found")
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
                            diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_otp_stuck")
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
                            diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_otp_no_retry")
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
                            'form button',
                        ],
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
                    except Exception:
                        pass

                time.sleep(1)
            if not callback["url"]:
                diagnostics["message"] = _capture_page_diagnostics(page, "codex_rt_login")
    except Exception as exc:
        return CodexBrowserRtResult(
            ok=False,
            failure_code="browser_login_exception",
            failure_message=f"{type(exc).__name__}: {str(exc)[:500]}",
            callback_url_seen=bool(callback["url"]),
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

        http = CffiSession(impersonate="chrome136")
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
        email_input.fill(email.strip().lower())
        return _click_first_visible(
            page,
            ['button[type="submit"]', 'button:has-text("Continue")', '#btnNext'],
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


def _is_otp_page(page, current_url: str) -> bool:
    if _has_otp_input(page):
        return True
    if _has_otp_retry_control(page):
        return True
    if "email-otp" in current_url or "passwordless" in current_url:
        return True
    if _is_email_verification_url(current_url):
        return True
    return False


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
    return _find_first_visible(
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
    ) is not None


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
        single = page.query_selector('input[autocomplete="one-time-code"]:visible') or page.query_selector(
            'input[inputmode="numeric"]:not([maxlength="1"]):visible'
        )
        if single:
            single.click(timeout=3000)
            single.fill(value)
            return True
        digits = page.query_selector_all('input[maxlength="1"][inputmode="numeric"]') or page.query_selector_all(
            'input[maxlength="1"]'
        )
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
        return ""
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


def _is_add_phone_url(current_url: str) -> bool:
    value = str(current_url or "")
    return "/add-phone" in value or "phone-number" in value


def _phone_failure_result(failure_code: str, *, final_url: str) -> CodexBrowserRtResult:
    messages = {
        "phone_otp_select_channel": (
            "auth.openai.com 进入 phone-otp/select-channel，Personal Codex 授权永久跳过"
        ),
        "add_phone_blocked": "auth.openai.com 要求添加手机号且没有可用跳过入口",
    }
    return CodexBrowserRtResult(
        ok=False,
        failure_code=failure_code,
        failure_message=messages.get(failure_code, failure_code),
        final_url=final_url,
    )


def _is_workspace_or_consent_page(current_url: str) -> bool:
    return "/workspace" in current_url or "/consent" in current_url or "/authorize" in current_url


def _click_first_visible(page, selectors: list[str]) -> bool:
    button = _find_first_visible(page, selectors)
    if not button:
        return False
    try:
        button.evaluate("(el) => { el.click(); return true; }")
    except Exception:
        button.click(timeout=3000, no_wait_after=True)
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
