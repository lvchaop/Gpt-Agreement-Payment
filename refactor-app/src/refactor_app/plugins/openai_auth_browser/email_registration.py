from __future__ import annotations

import random
import shutil
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from refactor_app.plugins.mail_external_api.plugin import prepare_domain_mailbox
from refactor_app.plugins.openai_auth_browser.personal_payment_method import (
    BrowserBillingDetails,
    BrowserPaymentCard,
    BrowserPaymentMethodResult,
    bind_personal_payment_card,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthResult,
    default_password_from_email,
    session_account_fields,
)
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    _click_otp_retry_control,
    _fill_otp,
    _is_mfa_challenge_url,
    _seed_context_cookies,
    _select_existing_account_if_visible,
)
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    _start_passwordless_email_login as _codex_start_passwordless_email_login,
)
from refactor_app.plugins.openai_chatgpt.client import (
    WHAM_CODEX_LOCAL_ACCESS_SCOPE,
    decode_access_token_claims,
)

TraceEmitter = Callable[[str, dict[str, Any], str], None]
APP_ROOT = Path(__file__).resolve().parents[4]


class BrowserEmailRegistrationError(RuntimeError):
    pass


class BrowserAccountDeactivatedError(BrowserEmailRegistrationError):
    pass


class BrowserChatGPTAccountMissingError(BrowserEmailRegistrationError):
    pass


@dataclass(frozen=True)
class BrowserEmailRegistrationConfig:
    proxy_url: str = ""
    headless: bool = True
    locale: str = "en-US"
    otp_timeout_s: int = 180
    navigation_timeout_ms: int = 60_000
    completion_timeout_s: int = 120
    work_id: str = ""
    artifact_root: str = ""
    capture_artifacts: bool = True


@dataclass(frozen=True)
class BrowserBusinessCredential:
    email: str
    chatgpt_user_id: str
    external_space_id: str
    access_token: str
    credential_id: str = ""


class CamoufoxEmailRegistration:
    def __init__(
        self,
        config: BrowserEmailRegistrationConfig,
        *,
        event_callback: TraceEmitter | None = None,
    ) -> None:
        self.config = config
        self._event_callback = event_callback
        self.artifact_dir: Path | None = None
        if config.capture_artifacts:
            root = (
                Path(config.artifact_root)
                if config.artifact_root
                else APP_ROOT / "runtime" / "artifacts"
            )
            self.artifact_dir = root / "protocol-register" / (config.work_id or str(uuid4()))
            self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def run(self, mail_provider) -> AuthResult:
        return self._run_authenticated(
            mail_provider,
            password_for_email=default_password_from_email,
            register_method="email_browser",
            entry_mode="signup",
            passwordless_for_existing_login=True,
            after_session=lambda _context, _page, result: result,
        )

    def authenticate_passwordless(self, mail_provider) -> AuthResult:
        """Complete the existing browser login/register flow and return its web session."""
        return self._run_authenticated(
            mail_provider,
            password_for_email=default_password_from_email,
            register_method="email_browser_passwordless",
            entry_mode="login",
            passwordless_for_existing_login=True,
            after_session=lambda _context, _page, result: result,
        )

    def bind_personal_payment_method(
        self,
        mail_provider,
        *,
        expected_personal_account_id: str,
        card: BrowserPaymentCard,
        billing: BrowserBillingDetails,
        login_password: str = "",
        totp_code_provider: Callable[[], str] | None = None,
        cookie_header: str = "",
        auth_cookie_header: str = "",
        timeout_s: int = 120,
    ) -> BrowserPaymentMethodResult:
        def bind(_context, page, _result: AuthResult) -> BrowserPaymentMethodResult:
            return bind_personal_payment_card(
                page,
                expected_personal_account_id=expected_personal_account_id,
                card=card,
                billing=billing,
                timeout_s=timeout_s,
            )

        return self._run_authenticated(
            mail_provider,
            password_for_email=default_password_from_email,
            register_method="email_browser_passwordless",
            entry_mode="login",
            passwordless_for_existing_login=not bool(str(login_password or "").strip()),
            after_session=bind,
            login_password=login_password,
            totp_code_provider=totp_code_provider,
            cookie_header=cookie_header,
            auth_cookie_header=auth_cookie_header,
        )

    def provision_business_credential(
        self,
        mail_provider,
        *,
        external_space_id: str,
        credential_name: str,
        ttl_seconds: int = 7_776_000,
    ) -> BrowserBusinessCredential:
        workspace_id = str(external_space_id or "").strip()
        name = str(credential_name or "").strip()
        ttl = int(ttl_seconds or 0)
        if not workspace_id:
            raise BrowserEmailRegistrationError("external_space_id is required")
        if not name:
            raise BrowserEmailRegistrationError("credential_name is required")
        if ttl <= 0:
            raise BrowserEmailRegistrationError("ttl_seconds must be positive")

        def provision(context, page, result: AuthResult) -> BrowserBusinessCredential:
            payload = _create_business_credential_in_browser(
                page,
                external_space_id=workspace_id,
                credential_name=name,
                ttl_seconds=ttl,
                scope=WHAM_CODEX_LOCAL_ACCESS_SCOPE,
            )
            workspace_access_token = str(payload.pop("workspace_access_token", "") or "")
            claims = decode_access_token_claims(workspace_access_token)
            if claims.token_chatgpt_account_id != workspace_id:
                raise BrowserEmailRegistrationError(
                    "browser workspace access token does not belong to the target space: "
                    f"expected={workspace_id} actual={claims.token_chatgpt_account_id}"
                )
            access_token = str(payload.get("access_token") or "").strip()
            if not access_token:
                raise BrowserEmailRegistrationError(
                    "browser Business AT response missing access_token"
                )
            response_workspace_id = str(payload.get("workspace_id") or "").strip()
            if response_workspace_id and response_workspace_id != workspace_id:
                raise BrowserEmailRegistrationError(
                    "browser Business AT workspace mismatch: "
                    f"expected={workspace_id} actual={response_workspace_id}"
                )
            return BrowserBusinessCredential(
                email=result.email,
                chatgpt_user_id=str(claims.account_id or "").strip(),
                external_space_id=workspace_id,
                access_token=access_token,
                credential_id=str(payload.get("credential_id") or payload.get("id") or "").strip(),
            )

        return self._run_authenticated(
            mail_provider,
            password_for_email=default_password_from_email,
            register_method="email_browser_passwordless",
            entry_mode="login",
            passwordless_for_existing_login=True,
            after_session=provision,
        )

    def _run_authenticated(
        self,
        mail_provider,
        *,
        password_for_email: Callable[[str], str],
        register_method: str,
        entry_mode: str,
        passwordless_for_existing_login: bool,
        after_session: Callable[[Any, Any, AuthResult], Any],
        login_password: str = "",
        totp_code_provider: Callable[[], str] | None = None,
        cookie_header: str = "",
        auth_cookie_header: str = "",
    ) -> Any:
        from browserforge.fingerprints import Screen
        from camoufox.sync_api import Camoufox

        email = mail_provider.create_mailbox()
        # Match the protocol/OAuth entrypoint: domain-backed mailboxes are
        # created before the provider starts polling for the first code.
        prepare_domain_mailbox(mail_provider, email=email)
        result = AuthResult()
        result.email = email
        result.password = str(login_password or password_for_email(email) or "")
        result.register_method = register_method
        first_name, last_name = _registration_name()
        profile_dir = tempfile.mkdtemp(prefix="refactor_browser_register_")
        page = None
        self._emit("browser.started", {"email": email, "headless": self.config.headless})
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
                # Stripe.js is attached to the page's main world. Camoufox
                # evaluates automation scripts in an isolated world unless
                # this bridge is explicitly enabled.
                main_world_eval=True,
                # The proxy already determines the egress location. GeoIP is
                # only fingerprint data here and otherwise causes a 66 MB
                # database download before the first page can render.
                geoip=False,
                locale=self.config.locale,
            ) as context:
                _seed_context_cookies(context, cookie_header, ".chatgpt.com")
                _seed_context_cookies(context, auth_cookie_header, ".auth.openai.com")
                _seed_context_cookies(context, auth_cookie_header, ".openai.com")
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(30_000)
                try:
                    session_info = self._reuse_existing_session(page) if cookie_header else {}
                    if session_info:
                        authenticated = self._hydrate_authenticated_result(
                            context,
                            result=result,
                            session_info=session_info,
                        )
                    else:
                        authenticated = self._run_in_context(
                            context,
                            page,
                            mail_provider,
                            result=result,
                            first_name=first_name,
                            last_name=last_name,
                            entry_mode=entry_mode,
                            passwordless_for_existing_login=(
                                passwordless_for_existing_login
                            ),
                            totp_code_provider=totp_code_provider,
                        )
                    return after_session(context, page, authenticated)
                except Exception:
                    self._screenshot(page, "failed.png")
                    raise
        except Exception as exc:
            self._emit(
                "browser.failed",
                {
                    "email": email,
                    "error": f"{type(exc).__name__}: {exc}",
                    "artifact_dir": str(self.artifact_dir) if self.artifact_dir else "",
                },
                "ERROR",
            )
            raise
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)

    def _run_in_context(
        self,
        context,
        page,
        mail_provider,
        *,
        result: AuthResult,
        first_name: str,
        last_name: str,
        entry_mode: str = "signup",
        passwordless_for_existing_login: bool = False,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> AuthResult:
        self._open_email_registration(page, entry_mode=entry_mode)
        self._complete_email_authentication(
            page,
            mail_provider,
            result=result,
            email=result.email,
            passwordless_for_existing_login=passwordless_for_existing_login,
            totp_code_provider=totp_code_provider,
        )
        self._complete_about_you(page, first_name=first_name, last_name=last_name)
        session_info = self._wait_for_chatgpt_session(
            page,
            on_user_already_exists_retry=lambda: self._resume_existing_login_after_retry(
                page,
                mail_provider,
                result=result,
                totp_code_provider=totp_code_provider,
            ),
        )
        return self._hydrate_authenticated_result(
            context,
            result=result,
            session_info=session_info,
        )

    def _reuse_existing_session(self, page) -> dict[str, Any]:
        try:
            page.goto(
                _chatgpt_home_url(),
                wait_until="commit",
                timeout=self.config.navigation_timeout_ms,
            )
        except Exception as exc:
            self._emit(
                "browser.session.reuse.navigation_slow",
                {"url": page.url, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                "WARN",
            )
        if not self._wait_for_page_state(
            page,
            lambda: _has_authenticated_session(page),
            stage="wait-existing-session",
            timeout_s=15,
        ):
            self._emit("browser.session.reuse.failed", {"url": page.url}, "WARN")
            return {}
        session_info = _chatgpt_session_payload(page)
        if not session_info.get("accessToken"):
            return {}
        self._emit("browser.session.reused", {"url": page.url})
        return session_info

    def _hydrate_authenticated_result(
        self,
        context,
        *,
        result: AuthResult,
        session_info: dict[str, Any],
    ) -> AuthResult:
        cookies = list(context.cookies())
        result.access_token = str(session_info.get("accessToken") or "")
        result.id_token = str(session_info.get("idToken") or "")
        (
            result.chatgpt_account_id,
            result.chatgpt_account_structure,
            result.chatgpt_account_plan_type,
        ) = session_account_fields(session_info)
        result.cookie_header = _cookie_header(cookies, "chatgpt.com")
        result.auth_cookie_header = _cookie_header(cookies, "openai.com")
        result.session_token = _session_token(cookies)
        result.device_id = _cookie_value(cookies, ("oai-did", "oai-device-id"))
        csrf_cookie = _cookie_value(cookies, ("__Host-next-auth.csrf-token",))
        result.csrf_token = csrf_cookie.split("|", 1)[0] if csrf_cookie else ""
        if not result.is_valid():
            self._screenshot(page, "missing-session.png")
            raise BrowserEmailRegistrationError(
                "browser registration finished without session_token/access_token"
            )
        self._emit(
            "browser.succeeded",
            {
                "email": result.email,
                "has_session_token": True,
                "has_access_token": True,
            },
        )
        return result

    def _complete_email_authentication(
        self,
        page,
        mail_provider,
        *,
        result: AuthResult,
        email: str,
        passwordless_for_existing_login: bool,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> None:
        otp_issued_after = time.time()
        self._submit_email(page, email)
        password_submitted = self._submit_password_if_requested(
            page,
            result.password,
            email=email,
            passwordless_for_existing_login=passwordless_for_existing_login,
        )
        result.password_configured = result.password_configured or password_submitted
        self._complete_email_otp(
            page,
            mail_provider,
            email=email,
            issued_after=otp_issued_after,
            totp_code_provider=totp_code_provider,
        )

    def _resume_existing_login_after_retry(
        self,
        page,
        mail_provider,
        *,
        result: AuthResult,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> None:
        if not self._wait_for_page_state(
            page,
            lambda: _visible(page, EMAIL_INPUT_SELECTORS) is not None,
            stage="wait-user-already-exists-login-form",
            timeout_s=30,
        ):
            self._screenshot(page, "user-already-exists-login-form-missing.png")
            raise BrowserEmailRegistrationError(
                f"user_already_exists retry did not reach login email form url={page.url}"
            )
        self._emit(
            "browser.user_already_exists.login.started",
            {"email": result.email, "url": page.url},
            "WARN",
        )
        self._complete_email_authentication(
            page,
            mail_provider,
            result=result,
            email=result.email,
            passwordless_for_existing_login=True,
            totp_code_provider=totp_code_provider,
        )
        self._emit(
            "browser.user_already_exists.login.completed",
            {"email": result.email, "url": page.url},
        )

    def _open_email_registration(self, page, *, entry_mode: str = "login") -> None:
        normalized_entry_mode = str(entry_mode or "").strip().lower()
        if normalized_entry_mode not in {"login", "signup"}:
            raise BrowserEmailRegistrationError(
                f"unsupported browser email entry mode: {entry_mode}"
            )
        entry_selectors = (
            SIGNUP_SELECTORS if normalized_entry_mode == "signup" else LOGIN_SELECTORS
        )
        entry_text = "sign up" if normalized_entry_mode == "signup" else "log in"
        entry_stage = "signup" if normalized_entry_mode == "signup" else "login"

        # The home page can keep transferring analytics/streaming resources
        # after the login controls are already usable. Waiting for
        # ``domcontentloaded`` leaves the browser pointer at its old position
        # and prevents the click path from running. Match the existing browser
        # OAuth flow: wait for the response commit, then poll the actual controls.
        try:
            page.goto(
                _chatgpt_home_url(),
                wait_until="commit",
                timeout=self.config.navigation_timeout_ms,
            )
        except Exception as exc:
            if (
                _visible(page, EMAIL_INPUT_SELECTORS) is None
                and _visible(page, entry_selectors) is None
            ):
                raise
            self._emit(
                "browser.home.navigation.slow",
                {"url": page.url, "error": f"{type(exc).__name__}: {str(exc)[:200]}"},
                "WARN",
            )
        self._emit("browser.home.navigation.committed", {"url": page.url})
        self._raise_for_challenge(page, "open-chatgpt")
        if _visible(page, EMAIL_INPUT_SELECTORS) is not None:
            return
        if not self._wait_for_page_state(
            page,
            lambda: _visible(page, EMAIL_INPUT_SELECTORS) is not None
            or _visible(page, entry_selectors) is not None,
            stage=f"wait-email-form-or-{entry_stage}-button",
            timeout_s=30,
        ):
            self._screenshot(page, f"{entry_stage}-button-missing.png")
            raise BrowserEmailRegistrationError(
                f"email form/{entry_stage} button not found url={page.url}"
            )
        if _visible(page, EMAIL_INPUT_SELECTORS) is not None:
            self._emit("browser.compat_email_form.ready", {"url": page.url})
            return

        def click_entry() -> bool:
            self._remove_google_one_tap(page)
            return _click_registration_control(
                page,
                entry_selectors,
                required_text=entry_text,
                timeout_ms=5_000,
            )

        # The anonymous home page can replace its header while it is still
        # loading. Re-query and click immediately instead of keeping a stale
        # handle across a fixed delay.
        if not self._wait_for_page_state(
            page,
            click_entry,
            stage=f"click-{entry_stage}-button",
            timeout_s=30,
        ):
            self._screenshot(page, f"{entry_stage}-button-missing.png")
            raise BrowserEmailRegistrationError(
                f"{entry_stage} button not found url={page.url}"
            )
        self._emit(f"browser.{entry_stage}.clicked", {"attempt": 1})

        entry_opened = False
        initial_url = str(page.url or "")
        for second in range(20):
            if (
                "auth.openai.com" in str(page.url or "")
                or _visible(page, EMAIL_INPUT_SELECTORS) is not None
                or _visible(page, EMAIL_ENTRY_SELECTORS) is not None
            ):
                entry_opened = True
                break
            if second == 5 and str(page.url or "") == initial_url:
                self._remove_google_one_tap(page)
                if _click_registration_control(
                    page,
                    entry_selectors,
                    required_text=entry_text,
                    timeout_ms=3_000,
                ):
                    self._emit(f"browser.{entry_stage}.clicked", {"attempt": 2})
                else:
                    self._emit(
                        f"browser.{entry_stage}.retrying",
                        {"attempt": 2, "reason": "button_not_ready"},
                        "WARN",
                    )
            time.sleep(1)
        if not entry_opened:
            self._screenshot(page, f"{entry_stage}-click-no-effect.png")
            raise BrowserEmailRegistrationError(
                f"{entry_stage} click had no effect url={page.url}"
            )
        if _visible(page, EMAIL_INPUT_SELECTORS) is None:
            self._remove_google_one_tap(page)
            if not _click_registration_control(
                page,
                EMAIL_ENTRY_SELECTORS,
                excluded_text=("google", "apple", "phone"),
                timeout_ms=5_000,
            ):
                self._screenshot(page, "email-entry-missing.png")
                raise BrowserEmailRegistrationError(f"email entry not found url={page.url}")
            self._emit("browser.email_entry.clicked", {"attempt": 1})
        if not self._wait_for_page_state(
            page,
            lambda: _visible(page, EMAIL_INPUT_SELECTORS) is not None,
            stage="wait-email-form",
            timeout_s=60,
        ):
            self._screenshot(page, "email-form-missing.png")
            raise BrowserEmailRegistrationError(f"email input not found url={page.url}")
        self._emit("browser.email_form.ready", {"url": page.url})

    def _submit_email(self, page, email: str) -> None:
        last_error = ""
        submitted_field = None
        for attempt in range(1, 5):
            field = _visible_email_input(page)
            if field is None:
                last_error = "email input disappeared"
                time.sleep(0.5)
                continue
            try:
                _click_registration_input(field, timeout_ms=5_000)
                time.sleep(0.3)
                current = _visible_email_input(page) or field
                current.fill(email)
                if _input_value(current) != email:
                    # React can replace the input during fill. Re-query the new
                    # element, then use the browser event path once.
                    current = _visible_email_input(page) or current
                    _click_registration_input(current, timeout_ms=5_000)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    page.keyboard.type(email, delay=30)
                if _input_value(current) != email:
                    raise BrowserEmailRegistrationError(
                        "email input value did not persist before submit"
                    )
                submitted_field = current
                last_error = ""
                break
            except Exception as exc:
                last_error = str(exc)
                self._emit(
                    "browser.email.fill.retrying",
                    {"attempt": attempt, "error": last_error[:200]},
                    "WARN",
                )
                time.sleep(0.5)
        if last_error:
            raise BrowserEmailRegistrationError(f"email input fill failed: {last_error}")
        time.sleep(random.uniform(0.5, 1.2))
        current_value = _input_value(_visible_email_input(page) or submitted_field)
        if current_value != email:
            self._screenshot(page, "email-value-missing-before-submit.png")
            raise BrowserEmailRegistrationError(
                "email input is empty or changed before submit"
            )
        initial_url = str(page.url or "")
        submit_method = "button"
        clicked = _click_first(
            page,
            EMAIL_CONTINUE_SELECTORS,
            timeout_ms=5_000,
            physical=True,
        )
        # A successful form submission can navigate before Playwright finishes the
        # element click. In that case the old handle detaches and _click_first
        # reports False even though the server response already advanced the page.
        advanced = self._wait_for_email_submit_transition(
            page,
            initial_url=initial_url,
            stage="wait-email-submit",
        )
        if not advanced:
            submit_method = "enter"
            current = _visible_email_input(page) or submitted_field
            if current is None:
                raise BrowserEmailRegistrationError("email continue button not found")
            try:
                page.keyboard.press("Enter")
            except Exception as exc:
                raise BrowserEmailRegistrationError(
                    f"email form submit failed: {exc}"
                ) from exc
            advanced = self._wait_for_email_submit_transition(
                page,
                initial_url=initial_url,
                stage="wait-email-enter-submit",
            )
        if not advanced:
            self._screenshot(page, "email-submit-no-effect.png")
            raise BrowserEmailRegistrationError(
                f"email submit had no effect url={page.url}"
            )
        self._emit(
            "browser.email.submitted",
            {
                "email": email,
                "method": submit_method,
                "click_completed": clicked,
                "url": page.url,
            },
        )

    def _wait_for_email_submit_transition(
        self,
        page,
        *,
        initial_url: str,
        stage: str,
    ) -> bool:
        """Wait for the post-email page to load before touching its controls."""
        timeout_s = max(
            30.0,
            min(90.0, float(self.config.navigation_timeout_ms or 60_000) / 1_000),
        )
        self._emit(
            "browser.email.submit.waiting",
            {"stage": stage, "timeout_s": int(timeout_s), "initial_url": initial_url},
        )
        _wait_for_document_load(page, timeout_ms=min(15_000, int(timeout_s * 1_000)))
        # The Google One Tap overlay can be injected again during the slow
        # post-submit navigation. Remove it only after the document had a chance
        # to load, then let the stage poll decide whether the real form exists.
        self._remove_google_one_tap(page)
        started = time.monotonic()
        advanced = self._wait_for_page_state(
            page,
            lambda: _email_submit_advanced(page, initial_url=initial_url),
            stage=stage,
            timeout_s=timeout_s,
        )
        if advanced:
            self._emit(
                "browser.email.submit.ready",
                {
                    "stage": stage,
                    "elapsed_ms": int((time.monotonic() - started) * 1_000),
                    "url": page.url,
                },
            )
        return advanced

    def _submit_password_if_requested(
        self,
        page,
        password: str,
        *,
        email: str = "",
        passwordless_for_existing_login: bool = False,
    ) -> bool:
        if email:
            _select_existing_account_if_visible(page, email)
        if (
            email
            and _is_chatgpt_email_login_page(page)
            and _visible(page, EMAIL_INPUT_SELECTORS) is not None
        ):
            self._emit("browser.compat_email_login.ready", {"url": page.url})
            self._submit_email(page, email)

        def password_or_otp_ready() -> bool:
            # Account selection is an action, not a ready-state signal. After
            # selecting it, continue polling until the next real control is
            # present on the page.
            if email:
                _select_existing_account_if_visible(page, email)
            return bool(
                _visible(page, PASSWORD_INPUT_SELECTORS) is not None
                or _otp_inputs(page)
                or _about_you_visible(page)
                or _has_authenticated_session(page)
            )

        reached_next_stage = self._wait_for_page_state(
            page,
            password_or_otp_ready,
            stage="wait-password-or-otp",
            timeout_s=35,
        )
        self._raise_for_terminal_account_error(page, "password-or-otp")
        field = _visible(page, PASSWORD_INPUT_SELECTORS)
        if field is None:
            if reached_next_stage and (
                _otp_inputs(page) or _about_you_visible(page) or _has_authenticated_session(page)
            ):
                self._emit("browser.password.skipped", {"url": page.url})
                return False
            self._screenshot(page, "password-or-otp-missing.png")
            raise BrowserEmailRegistrationError(
                f"password/OTP stage not reached url={page.url}"
            )
        current_url = str(page.url or "").lower()
        if passwordless_for_existing_login and "/log-in/password" in current_url:
            _codex_start_passwordless_email_login(page)
            self._emit("browser.passwordless_otp.started", {"url": page.url})
            return False
        if passwordless_for_existing_login and "/create-account/password" not in current_url:
            self._screenshot(page, "password-branch-unknown.png")
            raise BrowserEmailRegistrationError(
                f"password page is neither registration nor login url={page.url}"
            )
        field.click(timeout=5_000)
        field.fill(password)
        time.sleep(random.uniform(0.5, 1.2))
        if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000, physical=True):
            raise BrowserEmailRegistrationError("password continue button not found")
        self._emit("browser.password.submitted", {})
        return True

    def _complete_email_otp(
        self,
        page,
        mail_provider,
        *,
        email: str,
        issued_after: float,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> None:
        otp_retry_count = 0
        otp_retry_max = 2
        current_issued_after = issued_after
        while True:
            reached_next_stage = self._wait_for_page_state(
                page,
                lambda: bool(_otp_inputs(page))
                or _is_mfa_challenge_url(str(page.url or ""))
                or _about_you_visible(page)
                or _has_authenticated_session(page),
                stage="wait-email-otp",
                timeout_s=45,
            )
            if _is_mfa_challenge_url(str(page.url or "")):
                self._complete_totp_challenge(
                    page,
                    totp_code_provider=totp_code_provider,
                )
                return
            inputs = _otp_inputs(page)
            if not inputs:
                if reached_next_stage and (
                    _about_you_visible(page) or _has_authenticated_session(page)
                ):
                    self._emit("browser.otp.skipped", {"url": page.url})
                    return
                if otp_retry_count < otp_retry_max and _click_otp_retry_control(page):
                    otp_retry_count += 1
                    current_issued_after = time.time()
                    self._emit(
                        "browser.otp.retrying",
                        {"email": email, "attempt": otp_retry_count + 1},
                        "WARN",
                    )
                    continue
                self._screenshot(page, "otp-form-missing.png")
                raise BrowserEmailRegistrationError(
                    f"email OTP input not found url={page.url}"
                )
            self._emit(
                "browser.otp.wait.started",
                {
                    "email": email,
                    "timeout_s": self.config.otp_timeout_s,
                    "attempt": otp_retry_count + 1,
                },
            )
            code = str(
                mail_provider.wait_for_otp(
                    email,
                    timeout=max(1, int(self.config.otp_timeout_s or 180)),
                    issued_after=current_issued_after,
                )
                or ""
            ).strip()
            if not code:
                raise BrowserEmailRegistrationError("mail provider returned empty OTP")
            if not _type_email_otp(page, inputs, code):
                raise BrowserEmailRegistrationError("email OTP inputs are incomplete")
            submit_method = "button"
            submitted = _click_first(
                page,
                CONTINUE_SELECTORS,
                timeout_ms=5_000,
                physical=True,
            )
            self._emit(
                "browser.otp.submit.clicked",
                {"email": email, "method": "button", "click_strategy": "dom"},
            )
            if not submitted:
                try:
                    page.keyboard.press("Enter")
                    submitted = True
                    submit_method = "enter"
                except Exception:
                    submitted = False
            if not submitted:
                raise BrowserEmailRegistrationError("email OTP continue button not found")
            advanced = self._wait_for_page_state(
                page,
                lambda: _about_you_visible(page)
                or _has_authenticated_session(page)
                or _visible(page, OTP_ERROR_SELECTORS) is not None
                or _visible(page, ACCOUNT_MISSING_SELECTORS) is not None
                or _visible(page, ACCOUNT_DEACTIVATED_SELECTORS) is not None,
                stage="wait-email-otp-submit",
                timeout_s=30,
            )
            self._raise_for_terminal_account_error(page, "email-otp")
            error = _visible(page, OTP_ERROR_SELECTORS)
            if error is not None:
                if otp_retry_count < otp_retry_max and _click_otp_retry_control(page):
                    otp_retry_count += 1
                    current_issued_after = time.time()
                    self._emit(
                        "browser.otp.retrying",
                        {"email": email, "attempt": otp_retry_count + 1},
                        "WARN",
                    )
                    continue
                self._screenshot(page, "otp-rejected.png")
                raise BrowserEmailRegistrationError("OpenAI rejected email OTP")
            if not advanced:
                # The verification page can keep the visible button after a
                # click that did not dispatch the SPA handler. Use the same
                # authenticated browser context to validate the code directly
                # before requesting another code; this preserves the existing
                # session and returns the server-provided continuation URL.
                try:
                    self._emit(
                        "browser.otp.submit.fallback",
                        {"email": email, "method": submit_method},
                        "WARN",
                    )
                    _validate_email_otp_in_browser(
                        page,
                        code,
                        navigation_timeout_ms=self.config.navigation_timeout_ms,
                    )
                    direct_advanced = self._wait_for_page_state(
                        page,
                        lambda: _about_you_visible(page) or _has_authenticated_session(page),
                        stage="wait-email-otp-direct-submit",
                        timeout_s=30,
                    )
                    if direct_advanced:
                        self._emit(
                            "browser.otp.submitted",
                            {"email": email, "method": "direct_validate"},
                        )
                        return
                except (BrowserAccountDeactivatedError, BrowserChatGPTAccountMissingError):
                    raise
                except Exception as exc:
                    self._emit(
                        "browser.otp.submit.fallback_failed",
                        {
                            "email": email,
                            "error": f"{type(exc).__name__}: {str(exc)[:500]}",
                        },
                        "WARN",
                    )
                if otp_retry_count < otp_retry_max and _click_otp_retry_control(page):
                    otp_retry_count += 1
                    current_issued_after = time.time()
                    self._emit(
                        "browser.otp.retrying",
                        {"email": email, "attempt": otp_retry_count + 1},
                        "WARN",
                    )
                    continue
                self._screenshot(page, "otp-submit-no-effect.png")
                raise BrowserEmailRegistrationError(
                    f"email OTP submit had no effect url={page.url}"
                )
            self._emit("browser.otp.submitted", {"email": email})
            return

    def _complete_totp_challenge(
        self,
        page,
        *,
        totp_code_provider: Callable[[], str] | None,
    ) -> None:
        if totp_code_provider is None:
            raise BrowserEmailRegistrationError(
                "TOTP challenge requires a configured 2FAuth account"
            )
        code = str(totp_code_provider() or "").strip()
        if not code.isdigit():
            raise BrowserEmailRegistrationError("2FAuth returned an invalid TOTP code")
        if not _fill_otp(page, code):
            raise BrowserEmailRegistrationError("TOTP input not found")
        if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000, physical=True):
            raise BrowserEmailRegistrationError("TOTP continue button not found")
        self._emit("browser.totp.submitted", {"url": page.url})
        if not self._wait_for_page_state(
            page,
            lambda: not _is_mfa_challenge_url(str(page.url or ""))
            or _has_authenticated_session(page),
            stage="wait-totp-submit",
            timeout_s=30,
        ):
            raise BrowserEmailRegistrationError("TOTP submit had no effect")

    def _complete_about_you(self, page, *, first_name: str, last_name: str) -> None:
        name: dict[str, Any] | None = None
        birthday: dict[str, Any] | None = None
        birthday_segments: list[dict[str, Any]] = []
        legacy_age = False
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self._raise_for_terminal_account_error(page, "about-you")
            if _has_authenticated_session(page):
                self._emit("browser.about_you.skipped", {"url": page.url})
                return
            inputs = _visible_input_metadata(page)
            birthday_segments = _visible_date_segment_metadata(page)
            birthday = next((item for item in inputs if _is_birthday_input(item)), None)
            name = next(
                (
                    item
                    for item in inputs
                    if item is not birthday
                    and _is_name_input(item)
                    and not _is_birthday_input(item)
                ),
                None,
            )
            if name is not None and (
                birthday is not None or len(birthday_segments) >= 3
            ):
                break
            if birthday is None and len(inputs) >= 2:
                name = next((item for item in inputs if _is_name_input(item)), None)
                if name is not None:
                    birthday = next((item for item in inputs if item is not name), None)
                    legacy_age = birthday is not None
                    if legacy_age:
                        break
            self._raise_for_challenge(page, "wait-about-you")
            time.sleep(1)
        if name is None or (birthday is None and len(birthday_segments) < 3):
            self._screenshot(page, "about-you-form-missing.png")
            self._emit("browser.about_you.not_found", {"url": page.url}, "WARN")
            return
        elements = page.query_selector_all("input")
        name_field = elements[name["index"]]
        try:
            name_field.focus()
            page.keyboard.type(f"{first_name} {last_name}", delay=random.randint(30, 80))
            age = str(random.randint(26, 40))
            year = time.gmtime().tm_year - int(age)
            if birthday is None:
                _fill_segmented_birthday(page, birthday_segments, year=year)
            else:
                birthday_field = elements[birthday["index"]]
                birthday_field.focus()
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                if legacy_age:
                    page.keyboard.type(age, delay=random.randint(40, 100))
                elif birthday["type"] == "date":
                    try:
                        birthday_field.fill(f"{year}-01-15")
                    except Exception:
                        page.keyboard.type(
                            f"{year}-01-15",
                            delay=random.randint(30, 70),
                        )
                else:
                    page.keyboard.type(
                        f"01/15/{year}",
                        delay=random.randint(30, 70),
                    )
            time.sleep(random.uniform(0.4, 0.9))
            if not _click_first(page, FINISH_SELECTORS, timeout_ms=5_000, physical=True):
                self._screenshot(page, "about-you-submit-missing.png")
                self._emit("browser.about_you.submit_missing", {"url": page.url}, "WARN")
                return
            self._emit(
                "browser.about_you.submitted",
                {
                    "legacy_age": legacy_age,
                    "segmented_birthday": birthday is None,
                },
            )
        except Exception as exc:
            self._screenshot(page, "about-you-fill-failed.png")
            self._emit(
                "browser.about_you.fill_failed",
                {"url": page.url, "error": f"{type(exc).__name__}: {exc}"},
                "WARN",
            )

    def _wait_for_chatgpt_session(
        self,
        page,
        *,
        on_user_already_exists_retry: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        completion_timeout_s = max(1, int(self.config.completion_timeout_s or 120))
        deadline = time.monotonic() + completion_timeout_s
        next_continue_at = time.monotonic() + 5
        user_already_exists_retried = False
        while time.monotonic() < deadline:
            self._raise_for_terminal_account_error(page, "wait-chatgpt-session")
            if _visible(page, USER_ALREADY_EXISTS_SELECTORS) is not None:
                if user_already_exists_retried:
                    self._screenshot(page, "user-already-exists-retry-no-effect.png")
                    raise BrowserEmailRegistrationError(
                        "user_already_exists retry returned to the same error page"
                    )
                if not _click_first(
                    page,
                    TRY_AGAIN_SELECTORS,
                    timeout_ms=5_000,
                    physical=True,
                ):
                    self._screenshot(page, "user-already-exists-retry-missing.png")
                    raise BrowserEmailRegistrationError(
                        "user_already_exists page has no visible Try again control"
                    )
                user_already_exists_retried = True
                self._emit(
                    "browser.user_already_exists.retry.clicked",
                    {"url": page.url, "attempt": 1},
                    "WARN",
                )
                if not self._wait_for_page_state(
                    page,
                    lambda: _visible(page, USER_ALREADY_EXISTS_SELECTORS) is None
                    or _has_authenticated_session(page),
                    stage="wait-user-already-exists-retry",
                    timeout_s=20,
                ):
                    self._screenshot(page, "user-already-exists-retry-no-effect.png")
                    raise BrowserEmailRegistrationError(
                        "user_already_exists Try again click had no effect"
                    )
                if on_user_already_exists_retry is not None:
                    on_user_already_exists_retry()
                    deadline = time.monotonic() + completion_timeout_s
                continue
            payload = _chatgpt_session_payload(page)
            if payload.get("accessToken"):
                self._emit("browser.session.succeeded", {"url": page.url})
                return payload
            if "auth.openai.com" in page.url and time.monotonic() >= next_continue_at:
                _click_first(page, CONTINUE_SELECTORS, timeout_ms=2_000, physical=True)
                next_continue_at = time.monotonic() + 10
            self._raise_for_challenge(page, "wait-chatgpt-session")
            time.sleep(1)
        self._screenshot(page, "chatgpt-session-timeout.png")
        raise BrowserEmailRegistrationError(f"ChatGPT session timeout url={page.url}")

    def _raise_for_terminal_account_error(self, page, stage: str) -> None:
        if _visible(page, ACCOUNT_DEACTIVATED_SELECTORS) is not None:
            self._screenshot(page, f"{stage}-account-deactivated.png")
            raise BrowserAccountDeactivatedError(
                "OpenAI browser flow failed: code=account_deactivated"
            )
        if _visible(page, ACCOUNT_MISSING_SELECTORS) is not None:
            self._screenshot(page, f"{stage}-account-missing.png")
            raise BrowserChatGPTAccountMissingError(
                "OpenAI browser flow failed: code=chatgpt_account_missing"
            )

    def _remove_google_one_tap(self, page) -> None:
        for selector in GOOGLE_ONE_TAP_CLOSE_SELECTORS:
            try:
                element = page.query_selector(selector)
                if element is not None and element.is_visible():
                    element.click(timeout=2_000)
            except Exception:
                pass
        try:
            page.evaluate(
                """() => {
                    document.querySelectorAll('iframe[src*="accounts.google.com/gsi"]')
                        .forEach((element) => element.remove());
                }"""
            )
        except Exception:
            pass

    def _wait_for_page_state(
        self,
        page,
        predicate: Callable[[], bool],
        *,
        stage: str,
        timeout_s: float,
    ) -> bool:
        deadline = time.monotonic() + max(0.1, timeout_s)
        screenshot_at = time.monotonic() + min(15, max(1, timeout_s / 2))
        screenshot_taken = False
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return True
            except Exception:
                pass
            self._raise_for_challenge(page, stage)
            if not screenshot_taken and time.monotonic() >= screenshot_at:
                self._screenshot(page, f"waiting-{stage}.png")
                screenshot_taken = True
            time.sleep(0.5)
        return False

    def _raise_for_challenge(self, page, stage: str) -> None:
        reason = _challenge_reason(page)
        if not reason:
            return
        self._screenshot(page, f"challenge-{stage}.png")
        raise BrowserEmailRegistrationError(f"{reason} during {stage}")

    def _screenshot(self, page, filename: str) -> None:
        if self.artifact_dir is None:
            return
        try:
            page.screenshot(path=str(self.artifact_dir / filename), full_page=True)
        except Exception:
            pass

    def _emit(self, stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if self._event_callback is not None:
            self._event_callback(stage, data, level)


EMAIL_INPUT_SELECTORS = (
    'input[type="email"]',
    'input[name="email"]',
    'input[name="login_hint"]',
    'input[placeholder="Email address"]',
    'input[autocomplete="email"]',
)
PASSWORD_INPUT_SELECTORS = (
    'input[type="password"]',
    'input[name="password"]',
)
LOGIN_SELECTORS = (
    'button[data-testid="login-button"]',
    'a[data-testid="login-button"]',
    'button:has-text("Log in")',
    'a:has-text("Log in")',
    'button:has-text("Login")',
    'a:has-text("Login")',
)
SIGNUP_SELECTORS = (
    'a[data-testid="signup-button"]',
    'button[data-testid="signup-button"]',
    'button:has-text("Sign up for free")',
    'a:has-text("Sign up for free")',
    'button:has-text("Sign up")',
    'a:has-text("Sign up")',
)
EMAIL_ENTRY_SELECTORS = (
    'button:has-text("Continue with email")',
    'button:has-text("Sign up with email")',
    'a:has-text("Continue with email")',
    'a:has-text("Sign up with email")',
    'button:has-text("Email")',
    'button[data-testid*="email"]',
)
GOOGLE_ONE_TAP_CLOSE_SELECTORS = (
    'div#credential_picker_container button[aria-label*="Close"]',
    '[aria-label="Close"][role="button"]',
)
CONTINUE_SELECTORS = (
    'button[type="submit"]',
    'button:has-text("Continue")',
    'button:has-text("Verify")',
    'button:has-text("Create")',
    'button:has-text("Next")',
)
EMAIL_CONTINUE_SELECTORS = (
    'form:has(input[type="email"]) button[type="submit"]',
    'form:has(input[name="email"]) button[type="submit"]',
    'form:has(input[name="login_hint"]) button[type="submit"]',
    'form:has(input[placeholder="Email address"]) button[type="submit"]',
    '[role="dialog"]:has(input[type="email"]) button[type="submit"]',
    '[role="dialog"]:has(input[name="email"]) button[type="submit"]',
    '[role="dialog"]:has(input[name="login_hint"]) button[type="submit"]',
    '[role="dialog"]:has(input[type="email"]) button:has-text("Continue")',
    '[role="dialog"]:has(input[name="email"]) button:has-text("Continue")',
    '[role="dialog"]:has(input[name="login_hint"]) button:has-text("Continue")',
    'form:has(input[placeholder="Email address"]) button:has-text("Continue")',
)
FINISH_SELECTORS = (
    'button:has-text("Finish")',
    'button:has-text("Create")',
    'button:has-text("Agree")',
    'button[type="submit"]',
    'button:has-text("Continue")',
)
OTP_ERROR_SELECTORS = (
    'text=/incorrect code|invalid code|wrong code|验证码不正确|验证码错误/i',
)
ACCOUNT_MISSING_SELECTORS = (
    'text=/No eligible ChatGPT account found|chatgpt_account_missing/i',
)
ACCOUNT_DEACTIVATED_SELECTORS = (
    'text=/account has been deleted or deactivated|account_deactivated/i',
)
USER_ALREADY_EXISTS_SELECTORS = (
    'text=/user_already_exists|An account already exists for this email address or phone number/i',
)
TRY_AGAIN_SELECTORS = (
    'button:has-text("Try again")',
    'button:has-text("Retry")',
    'button:has-text("重试")',
    'button:has-text("再试一次")',
    'button:has-text("重新尝试")',
    'a:has-text("Try again")',
    'a:has-text("Retry")',
    'a:has-text("重试")',
)


def _registration_name() -> tuple[str, str]:
    first_names = (
        "James",
        "John",
        "Emily",
        "Sophia",
        "Michael",
        "Oliver",
        "Emma",
        "William",
        "Amelia",
        "Lucas",
        "Mia",
        "Ethan",
    )
    last_names = (
        "Smith",
        "Johnson",
        "Williams",
        "Brown",
        "Jones",
        "Garcia",
        "Miller",
        "Davis",
        "Rodriguez",
        "Martinez",
    )
    return random.choice(first_names), random.choice(last_names)


def _chatgpt_home_url() -> str:
    return "https://chatgpt.com/"


def _camoufox_proxy(proxy_url: str) -> dict[str, str] | None:
    value = str(proxy_url or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname or not parsed.port:
        raise BrowserEmailRegistrationError("invalid browser proxy URL")
    if parsed.scheme in {"socks5", "socks5h"} and parsed.username:
        raise BrowserEmailRegistrationError(
            "authenticated SOCKS proxy is not supported by Camoufox"
        )
    proxy = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


def _visible(page, selectors: tuple[str, ...]):
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        for element in elements:
            try:
                if element.is_visible():
                    return element
            except Exception:
                continue
    return None


def _visible_email_input(page):
    return _visible(page, EMAIL_INPUT_SELECTORS)


def _click_registration_input(element, *, timeout_ms: int) -> None:
    """Focus an email field using the legacy browser registration order."""
    try:
        element.click(timeout=timeout_ms)
        return
    except Exception as native_error:
        try:
            element.evaluate("(el) => { el.focus(); el.click(); return true; }")
            return
        except Exception as dom_error:
            raise BrowserEmailRegistrationError(
                "email input click failed: "
                f"native={type(native_error).__name__}: {native_error}; "
                f"dom={type(dom_error).__name__}: {dom_error}"
            ) from dom_error


def _click_registration_control(
    page,
    selectors: tuple[str, ...],
    *,
    timeout_ms: int,
    required_text: str = "",
    excluded_text: tuple[str, ...] = (),
) -> bool:
    """Click an exact registration control, with text selectors as fallback.

    Registration controls are transient React elements. Query every matching
    control and reject unrelated social-login choices. Exact data-testid
    selectors are ordered first, so duplicate visible labels do not decide the
    target. A DOM click avoids slow or stale pointer coordinates.
    """
    normalized_required = str(required_text or "").casefold()
    normalized_excluded = tuple(str(value).casefold() for value in excluded_text)
    saw_elements = False
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        for element in elements:
            try:
                if not element.is_visible():
                    continue
                saw_elements = True
                text = str(element.inner_text() or "").casefold()
                if normalized_required and normalized_required not in text:
                    continue
                if any(value in text for value in normalized_excluded):
                    continue
                if not _physical_click_element(page, element, timeout_ms=timeout_ms):
                    return False
                return True
            except Exception:
                continue
    if saw_elements:
        return False
    return _click_first(page, selectors, timeout_ms=timeout_ms, physical=True)


def _click_first(
    page,
    selectors: tuple[str, ...],
    *,
    timeout_ms: int,
    physical: bool = False,
) -> bool:
    element = _visible(page, selectors)
    if element is None:
        return False
    if physical:
        return _physical_click_element(page, element, timeout_ms=timeout_ms)
    try:
        element.scroll_into_view_if_needed(timeout=2_000)
    except Exception:
        pass
    try:
        # Match the active Codex browser path: dispatch the element's DOM click
        # first, then use a short native click only if the handle rejects it.
        # Native Playwright clicks can wait for a slow SPA navigation after the
        # page handler has already accepted the action.
        element.evaluate("(el) => { el.click(); return true; }")
    except Exception:
        try:
            element.click(timeout=timeout_ms, no_wait_after=True)
        except Exception:
            return False
    return True


def _physical_click_element(page, element, *, timeout_ms: int) -> bool:
    """Dispatch the element click directly; use native click only as fallback."""
    del page
    try:
        element.evaluate("(el) => { el.click(); return true; }")
        return True
    except Exception:
        try:
            element.click(timeout=timeout_ms, no_wait_after=True)
            return True
        except Exception:
            return False


def _wait_for_document_load(page, *, timeout_ms: int) -> None:
    """Give a real navigation time to finish before polling React controls."""
    waiter = getattr(page, "wait_for_load_state", None)
    if not callable(waiter):
        return
    timeout = max(1_000, int(timeout_ms or 1_000))
    try:
        waiter("domcontentloaded", timeout=timeout)
    except Exception:
        # The state may already have been reached, or the page may be an SPA
        # route with no new document. The control poll below remains authoritative.
        pass
    try:
        waiter("load", timeout=min(timeout, 5_000))
    except Exception:
        pass


def _email_submit_advanced(page, *, initial_url: str) -> bool:
    # URL changes alone are not evidence that the form finished. A slow SPA
    # transition can briefly land on the home route with an empty form.
    del initial_url
    return bool(
        _visible(page, PASSWORD_INPUT_SELECTORS) is not None
        or _otp_inputs(page)
        or _about_you_visible(page)
        or _has_authenticated_session(page)
        or _visible(page, ACCOUNT_MISSING_SELECTORS) is not None
        or _visible(page, ACCOUNT_DEACTIVATED_SELECTORS) is not None
    )


def _is_chatgpt_email_login_page(page) -> bool:
    parsed = urlparse(str(getattr(page, "url", "") or ""))
    return parsed.hostname == "chatgpt.com" and parsed.path.rstrip("/") == "/auth/login"


def _input_value(element: Any) -> str:
    if element is None:
        return ""
    getter = getattr(element, "input_value", None)
    if callable(getter):
        try:
            return str(getter() or "")
        except Exception:
            pass
    getter = getattr(element, "get_attribute", None)
    if callable(getter):
        try:
            return str(getter("value") or "")
        except Exception:
            pass
    return ""


def _type_email_otp(page, inputs: list[Any], code: str) -> bool:
    value = str(code or "").strip()
    if not value or not inputs:
        return False
    if len(inputs) == 1 or str(inputs[0].get_attribute("maxlength") or "") != "1":
        field = inputs[0]
        field.click()
        field.fill("")
        page.keyboard.type(value, delay=60)
        return True
    if len(inputs) < len(value):
        return False
    for index, char in enumerate(value):
        field = inputs[index]
        field.click()
        field.fill("")
        page.keyboard.type(char, delay=60)
    return True


def _validate_email_otp_in_browser(
    page,
    code: str,
    *,
    navigation_timeout_ms: int,
) -> dict[str, Any]:
    result = page.evaluate(
        """async (code) => {
            const response = await fetch('/api/accounts/email-otp/validate', {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'accept': 'application/json',
                    'content-type': 'application/json',
                },
                body: JSON.stringify({code}),
            });
            const text = await response.text();
            let payload = {};
            try { payload = JSON.parse(text); } catch (_) {}
            return {status: response.status, payload, body: text.slice(0, 800)};
        }""",
        str(code or "").strip(),
    )
    if not isinstance(result, dict):
        raise BrowserEmailRegistrationError(
            "browser email OTP validation returned invalid data"
        )
    status = int(result.get("status") or 0)
    payload = result.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    if status // 100 != 2:
        error = payload.get("error")
        error = error if isinstance(error, dict) else {}
        error_code = str(error.get("code") or "unknown")
        message = str(error.get("message") or result.get("body") or "")[:500]
        error_type = (
            BrowserAccountDeactivatedError
            if error_code == "account_deactivated"
            else BrowserEmailRegistrationError
        )
        raise error_type(
            "OpenAI email OTP validation failed: "
            f"http_status={status or 'unknown'} code={error_code} message={message}"
        )

    page_data = payload.get("page")
    page_data = page_data if isinstance(page_data, dict) else {}
    page_type = str(page_data.get("type") or "").strip().lower()
    continue_url = str(payload.get("continue_url") or "").strip()
    if not continue_url and page_type == "external_url":
        page_payload = page_data.get("payload")
        page_payload = page_payload if isinstance(page_payload, dict) else {}
        continue_url = str(page_payload.get("url") or "").strip()
    if not continue_url and page_type == "about_you":
        continue_url = "/about-you"
    if not continue_url:
        raise BrowserEmailRegistrationError(
            "OpenAI email OTP validation response has no next browser step: "
            f"page_type={page_type or 'unknown'}"
        )
    page.goto(
        urljoin("https://auth.openai.com", continue_url),
        wait_until="domcontentloaded",
        timeout=navigation_timeout_ms,
    )
    return payload


def _otp_inputs(page) -> list[Any]:
    selectors = (
        'input[autocomplete="one-time-code"]',
        'input[name="code"]',
        'input[inputmode="numeric"]',
        'input[maxlength="1"]',
    )
    found: list[Any] = []
    seen: set[int] = set()
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        for element in elements:
            try:
                if element.is_visible() and id(element) not in seen:
                    found.append(element)
                    seen.add(id(element))
            except Exception:
                continue
    return found


def _about_you_visible(page) -> bool:
    return "about-you" in str(page.url or "")


def _chatgpt_session_payload(page) -> dict[str, Any]:
    value = str(page.url or "")
    if "chatgpt.com" not in value or "auth.openai.com" in value:
        return {}
    try:
        payload = page.evaluate(
            """async () => {
                try {
                    const response = await fetch(
                        '/api/auth/session', {credentials: 'include'}
                    );
                    return await response.json();
                } catch (error) {
                    return {};
                }
            }"""
        )
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _create_business_credential_in_browser(
    page,
    *,
    external_space_id: str,
    credential_name: str,
    ttl_seconds: int,
    scope: str,
) -> dict[str, Any]:
    page.goto(
        "https://chatgpt.com/admin/access-tokens?modal=create",
        wait_until="domcontentloaded",
        timeout=60_000,
    )
    result = page.evaluate(
        """async ({workspaceId, credentialName, ttl, scope}) => {
            const sessionUrl = new URL('/api/auth/session', window.location.origin);
            sessionUrl.searchParams.set('exchange_workspace_token', 'true');
            sessionUrl.searchParams.set('workspace_id', workspaceId);
            sessionUrl.searchParams.set('reason', 'setCurrentAccount');

            const sessionResponse = await fetch(sessionUrl.toString(), {
                credentials: 'include',
                headers: {'accept': 'application/json'},
            });
            const sessionText = await sessionResponse.text();
            let sessionPayload = {};
            try { sessionPayload = JSON.parse(sessionText); } catch (_) {}
            const workspaceAccessToken = String(sessionPayload.accessToken || '');
            if (!sessionResponse.ok || !workspaceAccessToken) {
                return {
                    stage: 'workspace_session',
                    status: sessionResponse.status,
                    body: sessionText.slice(0, 800),
                };
            }

            const headers = {
                'authorization': `Bearer ${workspaceAccessToken}`,
                'content-type': 'application/json',
                'accept': '*/*',
                'chatgpt-account-id': workspaceId,
            };
            const deviceMatch = document.cookie.match(/(?:^|;\\s*)oai-did=([^;]+)/);
            if (deviceMatch && deviceMatch[1]) {
                headers['oai-device-id'] = decodeURIComponent(deviceMatch[1]);
            }
            const credentialResponse = await fetch('/backend-api/wham/auth-credentials', {
                method: 'POST',
                credentials: 'include',
                headers,
                body: JSON.stringify({
                    name: credentialName,
                    scopes: [scope],
                    ttl,
                }),
            });
            const credentialText = await credentialResponse.text();
            let credentialPayload = {};
            try { credentialPayload = JSON.parse(credentialText); } catch (_) {}
            return {
                stage: 'credential',
                status: credentialResponse.status,
                payload: credentialPayload,
                body: credentialText.slice(0, 800),
                workspaceAccessToken,
            };
        }""",
        {
            "workspaceId": external_space_id,
            "credentialName": credential_name,
            "ttl": int(ttl_seconds),
            "scope": scope,
        },
    )
    if not isinstance(result, dict):
        raise BrowserEmailRegistrationError("browser Business AT request returned invalid data")
    if result.get("stage") != "credential" or int(result.get("status") or 0) // 100 != 2:
        stage = str(result.get("stage") or "unknown")
        status = result.get("status") or "unknown"
        body = str(result.get("body") or "")[:500]
        raise BrowserEmailRegistrationError(
            f"browser Business AT request failed: stage={stage} http_status={status} body={body}"
        )
    payload = result.get("payload")
    if not isinstance(payload, dict):
        raise BrowserEmailRegistrationError("browser Business AT response is not JSON")
    payload = dict(payload)
    payload["workspace_access_token"] = str(result.get("workspaceAccessToken") or "")
    return payload


def _has_authenticated_session(page) -> bool:
    return bool(_chatgpt_session_payload(page).get("accessToken"))


def _visible_input_metadata(page) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """() => Array.from(document.querySelectorAll('input')).map((element, index) => {
                const rect = element.getBoundingClientRect();
                const style = getComputedStyle(element);
                return {
                    index,
                    type: (element.type || '').toLowerCase(),
                    name: element.name || '',
                    placeholder: element.placeholder || '',
                    ariaLabel: element.getAttribute('aria-label') || '',
                    label: (
                        element.labels && element.labels[0] && element.labels[0].innerText
                    ) || '',
                    visible: rect.width > 0 && rect.height > 0 &&
                        style.visibility !== 'hidden' && style.display !== 'none',
                };
            })"""
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    return [
        item
        for item in result
        if isinstance(item, dict)
        and item.get("visible")
        and item.get("type") not in {"hidden", "submit", "button", "checkbox", "radio", "password"}
    ]


def _visible_date_segment_metadata(page) -> list[dict[str, Any]]:
    try:
        result = page.evaluate(
            """() => Array.from(document.querySelectorAll('[role="spinbutton"]'))
                .map((element, index) => {
                    const rect = element.getBoundingClientRect();
                    const style = getComputedStyle(element);
                    return {
                        index,
                        ariaLabel: element.getAttribute('aria-label') || '',
                        valueMin: element.getAttribute('aria-valuemin') || '',
                        valueMax: element.getAttribute('aria-valuemax') || '',
                        text: element.textContent || '',
                        visible: rect.width > 0 && rect.height > 0 &&
                            style.visibility !== 'hidden' && style.display !== 'none',
                    };
                })"""
        )
    except Exception:
        return []
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict) and item.get("visible")]


def _fill_segmented_birthday(
    page,
    metadata: list[dict[str, Any]],
    *,
    year: int,
) -> None:
    elements = page.query_selector_all('[role="spinbutton"]')
    fallback_values = ("1", "15", str(year))
    for position, item in enumerate(metadata[:3]):
        label = str(item.get("ariaLabel") or "").casefold()
        maximum = _metadata_int(item.get("valueMax"))
        if "year" in label or maximum >= 1000:
            value = str(year)
        elif "month" in label or maximum == 12:
            value = "1"
        elif "day" in label or 28 <= maximum <= 31:
            value = "15"
        else:
            value = fallback_values[position]
        field = elements[int(item["index"])]
        field.focus()
        page.keyboard.type(value, delay=random.randint(40, 100))


def _metadata_int(value: object) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


@contextmanager
def _managed_camoufox(
    manager_factory: Callable[..., Any],
    **launch_options: Any,
) -> Iterator[Any]:
    manager = manager_factory(**launch_options)
    try:
        context = manager.__enter__()
    except BaseException:
        error = sys.exc_info()
        try:
            manager.__exit__(*error)
        except Exception:
            pass
        raise
    try:
        yield context
    finally:
        manager.__exit__(None, None, None)


def _input_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("type", "name", "placeholder", "ariaLabel", "label")
    ).lower()


def _is_birthday_input(item: dict[str, Any]) -> bool:
    text = _input_text(item)
    return item.get("type") == "date" or any(
        token in text for token in ("birth", "birthday", "dob", "mm/dd/yyyy", "mm / dd / yyyy")
    )


def _is_name_input(item: dict[str, Any]) -> bool:
    text = _input_text(item)
    return any(token in text for token in ("name", "first", "last", "full", "given", "family"))


def _challenge_reason(page) -> str:
    try:
        title = str(page.title() or "")
    except Exception:
        title = ""
    try:
        body = str(page.inner_text("body", timeout=3_000) or "")
    except Exception:
        body = ""
    text = "\n".join((title, str(page.url or ""), body)).lower()
    if "just a moment" in text and ("cloudflare" in text or "verifying" in text):
        return "Cloudflare challenge"
    if "cf-turnstile" in text or "turnstile" in text:
        return "Turnstile challenge"
    if "verify you are human" in text or "verifying you are human" in text:
        return "human verification challenge"
    return ""


def _cookie_header(cookies: list[dict[str, Any]], domain_keyword: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for cookie in cookies:
        name = str(cookie.get("name") or "")
        value = str(cookie.get("value") or "")
        domain = str(cookie.get("domain") or "").lower()
        if not name or not value or domain_keyword not in domain or name in seen:
            continue
        parts.append(f"{name}={value}")
        seen.add(name)
    return "; ".join(parts)


def _cookie_value(cookies: list[dict[str, Any]], names: tuple[str, ...]) -> str:
    for name in names:
        for cookie in cookies:
            if cookie.get("name") == name and cookie.get("value"):
                return str(cookie["value"])
    return ""


def _session_token(cookies: list[dict[str, Any]]) -> str:
    name = "__Secure-next-auth.session-token"
    direct = _cookie_value(cookies, (name,))
    if direct:
        return direct
    chunks = sorted(
        (
            (str(cookie.get("name") or ""), str(cookie.get("value") or ""))
            for cookie in cookies
            if str(cookie.get("name") or "").startswith(f"{name}.") and cookie.get("value")
        ),
        key=lambda item: _cookie_chunk_index(item[0]),
    )
    return "".join(value for _, value in chunks)


def _cookie_chunk_index(name: str) -> int:
    try:
        return int(name.rsplit(".", 1)[1])
    except (IndexError, ValueError):
        return 0
