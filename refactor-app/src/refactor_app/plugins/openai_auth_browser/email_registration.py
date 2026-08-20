from __future__ import annotations

import calendar
import hashlib
import json
import os
import platform
import random
import re
import secrets
import shutil
import string
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from uuid import uuid4

from refactor_app.config.browser_fingerprint import (
    BrowserFingerprint,
)
from refactor_app.plugins.browser_runtime import managed_camoufox_context
from refactor_app.plugins.cloakbrowser_runtime import managed_cloakbrowser_context
from refactor_app.plugins.mail_external_api.plugin import prepare_domain_mailbox
from refactor_app.plugins.openai_auth_browser.browser_logging import (
    BrowserLogRecorder,
    redact_browser_value,
)
from refactor_app.plugins.openai_auth_browser.personal_payment_method import (
    BrowserBillingDetails,
    BrowserPaymentCard,
    BrowserPaymentMethodResult,
    bind_personal_payment_card,
    bind_personal_payment_cards,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthResult,
    session_account_fields,
)
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import (
    _fill_otp,
    _has_otp_input,
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
_managed_camoufox = managed_camoufox_context
APP_ROOT = Path(__file__).resolve().parents[4]
# The identity catalog now follows the normalized-email browser fingerprint.
# Bump this when the selected OS/screen constraints change so stale host-based
# identities cannot be reused for a different mailbox profile.
_BROWSER_IDENTITY_VERSION = 2
_DYNAMIC_CAMOUFOX_CONFIG_KEYS = {
    "headers.Accept-Language",
    "navigator.language",
    "navigator.languages",
    "timezone",
}
_DYNAMIC_CAMOUFOX_CONFIG_PREFIXES = ("geolocation:", "locale:", "webrtc:")
SUPPORTED_BROWSER_BACKENDS = frozenset({"camoufox", "cloakbrowser"})


class BrowserEmailRegistrationError(RuntimeError):
    pass


class BrowserAccountDeactivatedError(BrowserEmailRegistrationError):
    pass


class BrowserChatGPTAccountMissingError(BrowserEmailRegistrationError):
    pass


class _BrowserTotpVerificationUnavailable(RuntimeError):
    """The browser page cannot issue the direct MFA request.

    This is deliberately separate from a failed MFA response. A real response
    must never fall through to the UI click path, otherwise a rejected code or
    a transport failure is misreported as a no-op button click.
    """



def _random_registration_password(_email: str = "") -> str:
    """Create a strong password without deriving any bytes from the mailbox."""
    groups = (
        string.ascii_uppercase,
        string.ascii_lowercase,
        string.digits,
    )
    characters = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    characters.extend(secrets.choice(alphabet) for _ in range(17))
    secrets.SystemRandom().shuffle(characters)
    return "".join(characters)


def _host_browser_os(system: str = "") -> str:
    host = str(system or platform.system()).strip().casefold()
    if host == "darwin":
        return "macos"
    if host == "windows":
        return "windows"
    return "linux"


def _stable_camoufox_config(email: str, *, browser_os: str, screen: Any) -> dict[str, Any]:
    """Persist only the non-geographic Camoufox identity for one mailbox."""
    normalized_email = str(email or "").strip().casefold()
    identity_hash = hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()
    identity_dir = APP_ROOT / "runtime" / "browser-identities"
    identity_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    identity_dir.chmod(0o700)
    path = identity_dir / f"{identity_hash}.json"

    existing = _read_camoufox_identity(path, browser_os=browser_os)
    if existing is not None:
        return existing

    generated = _sanitize_camoufox_config(
        _generate_camoufox_fingerprint_config(browser_os=browser_os, screen=screen)
    )
    if not generated:
        raise BrowserEmailRegistrationError("Camoufox returned an empty browser identity")
    payload = json.dumps(
        {
            "version": _BROWSER_IDENTITY_VERSION,
            "browser_os": browser_os,
            "config": generated,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        existing = _read_camoufox_identity(path, browser_os=browser_os)
        if existing is not None:
            return existing
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_bytes(payload)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    else:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    path.chmod(0o600)
    return generated


def _read_camoufox_identity(path: Path, *, browser_os: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != _BROWSER_IDENTITY_VERSION:
        return None
    if str(payload.get("browser_os") or "") != browser_os:
        return None
    config = payload.get("config")
    if not isinstance(config, dict):
        return None
    sanitized = _sanitize_camoufox_config(config)
    return sanitized or None


def _camoufox_os_for_fingerprint(fingerprint: BrowserFingerprint) -> str:
    platform_name = str(fingerprint.sec_ch_ua_platform or "").strip('"').casefold()
    return {
        "windows": "windows",
        "linux": "linux",
        "macos": "macos",
    }.get(platform_name, _host_browser_os())


def _screen_for_fingerprint(fingerprint: BrowserFingerprint, screen_type: Any) -> Any:
    """Keep Camoufox near the mailbox's stable display family."""
    width = int(fingerprint.screen_width)
    height = int(fingerprint.screen_height)
    try:
        return screen_type(
            min_width=max(800, round(width * 0.8)),
            max_width=round(width * 1.2),
            min_height=max(600, round(height * 0.8)),
            max_height=round(height * 1.2),
        )
    except (TypeError, ValueError):
        return screen_type(max_width=1920, max_height=1080)


def _generate_camoufox_fingerprint_config(*, browser_os: str, screen: Any) -> dict[str, Any]:
    from camoufox import DefaultAddons
    from camoufox.utils import launch_options

    options = launch_options(
        os=browser_os,
        screen=screen,
        exclude_addons=[DefaultAddons.UBO],
        env={},
    )
    chunks: list[tuple[int, str]] = []
    for key, value in dict(options.get("env") or {}).items():
        match = re.fullmatch(r"CAMOU_CONFIG_(\d+)", str(key))
        if match:
            chunks.append((int(match.group(1)), str(value)))
    if not chunks:
        raise BrowserEmailRegistrationError("Camoufox did not generate a browser identity")
    try:
        config = json.loads("".join(value for _, value in sorted(chunks)))
    except (ValueError, TypeError) as exc:
        raise BrowserEmailRegistrationError(
            "Camoufox generated an invalid browser identity"
        ) from exc
    if not isinstance(config, dict):
        raise BrowserEmailRegistrationError("Camoufox generated an invalid browser identity")
    return config


def _sanitize_camoufox_config(config: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in config.items():
        normalized_key = str(key)
        if normalized_key in _DYNAMIC_CAMOUFOX_CONFIG_KEYS:
            continue
        if normalized_key.startswith(_DYNAMIC_CAMOUFOX_CONFIG_PREFIXES):
            continue
        sanitized[normalized_key] = value
    return sanitized


@dataclass(frozen=True)
class BrowserEmailRegistrationConfig:
    proxy_url: str = ""
    headless: bool = True
    locale: str = ""
    # Optional normalized-email fingerprint. Browser workflows pass this so
    # registration, link extraction, and Plus checkout share one identity.
    browser_fingerprint: BrowserFingerprint | None = None
    otp_timeout_s: int = 180
    navigation_timeout_ms: int = 60_000
    # Email submission is an SPA transition. Keep this shorter than the full
    # navigation timeout so a no-op click reaches the retry path promptly.
    email_submit_timeout_s: float = 16.0
    completion_timeout_s: int = 120
    success_close_delay_s: float = 0.0
    failure_close_delay_s: float = 0.0
    work_id: str = ""
    artifact_root: str = ""
    capture_artifacts: bool = False
    browser_log_enabled: bool = False
    browser_log_capture_bodies: bool = False
    browser_log_max_body_chars: int = 20_000
    browser_backend: str = "camoufox"
    cloakbrowser_license_key: str = field(default="", repr=False)


def _normalize_browser_backend(value: str) -> str:
    backend = str(value or "camoufox").strip().casefold()
    aliases = {"cloak": "cloakbrowser", "camou": "camoufox"}
    backend = aliases.get(backend, backend)
    if backend not in SUPPORTED_BROWSER_BACKENDS:
        raise BrowserEmailRegistrationError(f"unsupported browser backend: {backend}")
    return backend


def _cloakbrowser_fingerprint_seed(email: str) -> str:
    digest = hashlib.sha256(str(email or "").strip().casefold().encode("utf-8")).digest()
    return str(int.from_bytes(digest[:8], "big"))


@contextmanager
def _managed_registration_browser_context(
    config: BrowserEmailRegistrationConfig,
    *,
    flow: str,
    email: str,
    profile_dir: str,
):
    backend = _normalize_browser_backend(config.browser_backend)
    if backend == "cloakbrowser":
        with managed_cloakbrowser_context(
            flow=flow,
            user_data_dir=profile_dir,
            headless=config.headless,
            humanize=True,
            proxy_url=config.proxy_url,
            geoip=True,
            locale=config.locale,
            fingerprint_seed=_cloakbrowser_fingerprint_seed(email),
            license_key=config.cloakbrowser_license_key,
        ) as context:
            yield context
        return

    from browserforge.fingerprints import Screen
    from camoufox import DefaultAddons

    fingerprint = config.browser_fingerprint
    if fingerprint is None:
        # Preserve the direct runner's legacy behavior for callers that do not
        # provide an account identity; production workflows always provide it.
        browser_os = _host_browser_os()
        screen = Screen(max_width=1920, max_height=1080)
    else:
        browser_os = _camoufox_os_for_fingerprint(fingerprint)
        screen = _screen_for_fingerprint(fingerprint, Screen)
    fingerprint_config = _stable_camoufox_config(
        email,
        browser_os=browser_os,
        screen=screen,
    )
    with _managed_camoufox(
        flow=flow,
        headless=config.headless,
        humanize=True,
        persistent_context=True,
        user_data_dir=profile_dir,
        os=browser_os,
        screen=screen,
        config=fingerprint_config,
        exclude_addons=[DefaultAddons.UBO],
        proxy=_camoufox_proxy(config.proxy_url),
        main_world_eval=True,
        geoip=True,
        locale=config.locale,
    ) as context:
        yield context


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
        self._browser_log: BrowserLogRecorder | None = None
        self.artifact_dir: Path | None = None
        if config.capture_artifacts or config.browser_log_enabled:
            root = (
                Path(config.artifact_root)
                if config.artifact_root
                else APP_ROOT / "runtime" / "artifacts"
            )
            self.artifact_dir = root / "protocol-register" / (config.work_id or str(uuid4()))
            self.artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.artifact_dir.chmod(0o700)

    def run(
        self,
        mail_provider,
        *,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> AuthResult:
        return self._run_authenticated(
            mail_provider,
            password_for_email=_random_registration_password,
            register_method="email_browser",
            entry_mode="signup",
            passwordless_for_existing_login=True,
            prefer_password_flow=True,
            totp_code_provider=totp_code_provider,
            after_session=lambda _context, _page, result: result,
        )

    def authenticate_passwordless(self, mail_provider) -> AuthResult:
        """Complete the existing browser login/register flow and return its web session."""
        return self._run_authenticated(
            mail_provider,
            password_for_email=_random_registration_password,
            register_method="email_browser_passwordless",
            entry_mode="login",
            passwordless_for_existing_login=True,
            after_session=lambda _context, _page, result: result,
        )

    def run_authenticated_page_with_login(
        self,
        mail_provider,
        *,
        login_password: str = "",
        totp_code_provider: Callable[[], str] | None = None,
        after_session: Callable[[Any, Any, AuthResult], Any],
    ) -> Any:
        """Complete a fresh login before running an authenticated page callback."""
        password = str(login_password or "").strip()
        return self._run_authenticated(
            mail_provider,
            password_for_email=_random_registration_password,
            register_method="email_browser_payment",
            entry_mode="login",
            passwordless_for_existing_login=not bool(password),
            after_session=after_session,
            login_password=password,
            totp_code_provider=totp_code_provider,
        )

    def run_authenticated_page(
        self,
        *,
        email: str,
        cookie_header: str,
        auth_cookie_header: str = "",
        after_session: Callable[[Any, Any, AuthResult], Any],
    ) -> Any:
        """Run a browser callback using the account's existing web session only."""
        normalized_email = str(email or "").strip()
        if not normalized_email or not str(cookie_header or "").strip():
            raise BrowserEmailRegistrationError("browser_authenticated_page_session_missing")
        profile_dir = tempfile.mkdtemp(prefix="refactor_browser_checkout_")
        result = AuthResult()
        result.email = normalized_email

        self._emit("browser.started", {"email": normalized_email, "headless": self.config.headless})
        try:
            with _managed_registration_browser_context(
                self.config,
                flow="authenticated-page",
                email=normalized_email,
                profile_dir=profile_dir,
            ) as context:
                browser_log = self._install_browser_log(context)
                try:
                    _seed_context_cookies(context, cookie_header, ".chatgpt.com")
                    _seed_context_cookies(context, auth_cookie_header, ".auth.openai.com")
                    _seed_context_cookies(context, auth_cookie_header, ".openai.com")
                    page = context.pages[0] if context.pages else context.new_page()
                    page.set_default_timeout(30_000)
                    session_info = self._reuse_existing_session(page)
                    if not session_info:
                        raise BrowserEmailRegistrationError(
                            "browser_authenticated_page_session_reuse_failed"
                        )
                    authenticated = self._hydrate_authenticated_result(
                        context,
                        page,
                        result=result,
                        session_info=session_info,
                    )
                    output = after_session(context, page, authenticated)
                    delay_s = max(0.0, float(self.config.success_close_delay_s or 0.0))
                    if delay_s:
                        time.sleep(delay_s)
                    return output
                finally:
                    if browser_log is not None:
                        browser_log.close()
                        self._browser_log = None
        except Exception as exc:
            self._emit(
                "browser.failed",
                {"email": normalized_email, "error": f"{type(exc).__name__}: {exc}"},
                "ERROR",
            )
            raise
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)

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
        after_success: Callable[[Any, BrowserPaymentMethodResult], Any] | None = None,
    ) -> BrowserPaymentMethodResult:
        def bind(_context, page, _result: AuthResult) -> BrowserPaymentMethodResult:
            payment_result = bind_personal_payment_card(
                page,
                expected_personal_account_id=expected_personal_account_id,
                card=card,
                billing=billing,
                timeout_s=timeout_s,
                http_trace_emitter=self._emit,
            )
            if after_success is not None:
                after_success(page, payment_result)
            return payment_result

        return self._run_authenticated(
            mail_provider,
            password_for_email=_random_registration_password,
            register_method="email_browser_passwordless",
            entry_mode="login",
            passwordless_for_existing_login=not bool(str(login_password or "").strip()),
            after_session=bind,
            login_password=login_password,
            totp_code_provider=totp_code_provider,
            cookie_header=cookie_header,
            auth_cookie_header=auth_cookie_header,
        )

    def bind_personal_payment_cards(
        self,
        mail_provider,
        *,
        expected_personal_account_id: str,
        card_provider,
        max_attempts: int = 3,
        login_password: str = "",
        totp_code_provider: Callable[[], str] | None = None,
        cookie_header: str = "",
        auth_cookie_header: str = "",
        timeout_s: int = 120,
        on_success=None,
        on_failure=None,
    ) -> list[BrowserPaymentMethodResult]:
        def bind(_context, page, _result: AuthResult) -> list[BrowserPaymentMethodResult]:
            return bind_personal_payment_cards(
                page,
                expected_personal_account_id=expected_personal_account_id,
                card_provider=card_provider,
                max_attempts=max_attempts,
                timeout_s=timeout_s,
                http_trace_emitter=self._emit,
                on_success=on_success,
                on_failure=on_failure,
            )

        return self._run_authenticated(
            mail_provider,
            password_for_email=_random_registration_password,
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
            password_for_email=_random_registration_password,
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
        prefer_password_flow: bool = False,
    ) -> Any:
        email = mail_provider.create_mailbox()
        # Match the protocol/OAuth entrypoint: domain-backed mailboxes are
        # created before the provider starts polling for the first code.
        prepare_domain_mailbox(mail_provider, email=email)
        result = AuthResult()
        result.email = email
        result.password = str(login_password or password_for_email(email) or "")
        result.register_method = register_method
        first_name, last_name, birthday = _registration_identity(
            email,
            locale=self.config.locale,
        )
        profile_dir = tempfile.mkdtemp(prefix="refactor_browser_register_")
        page = None
        self._emit("browser.started", {"email": email, "headless": self.config.headless})
        try:
            with _managed_registration_browser_context(
                self.config,
                flow=f"browser-{entry_mode}",
                email=email,
                profile_dir=profile_dir,
            ) as context:
                browser_log = self._install_browser_log(context)
                try:
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
                                page,
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
                                birth_date=birthday,
                                entry_mode=entry_mode,
                                passwordless_for_existing_login=(passwordless_for_existing_login),
                                prefer_password_flow=prefer_password_flow,
                                totp_code_provider=totp_code_provider,
                            )
                        output = after_session(context, page, authenticated)
                        close_delay_s = max(0.0, float(self.config.success_close_delay_s or 0.0))
                        if close_delay_s:
                            self._emit(
                                "browser.success_close_delay.started",
                                {"email": email, "delay_s": close_delay_s},
                            )
                            time.sleep(close_delay_s)
                            self._emit(
                                "browser.success_close_delay.completed",
                                {"email": email, "delay_s": close_delay_s},
                            )
                        return output
                    except Exception as exc:
                        if not _is_target_closed_error(exc):
                            self._screenshot(page, "failed.png")
                        failure_delay_s = max(
                            0.0,
                            float(self.config.failure_close_delay_s or 0.0),
                        )
                        if failure_delay_s:
                            self._emit(
                                "browser.failure_close_delay.started",
                                {"email": email, "delay_s": failure_delay_s},
                                "WARN",
                            )
                            time.sleep(failure_delay_s)
                        raise
                finally:
                    if browser_log is not None:
                        browser_log.close()
                        self._browser_log = None
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
        birth_date: tuple[int, int, int] | None = None,
        entry_mode: str = "signup",
        passwordless_for_existing_login: bool = False,
        prefer_password_flow: bool = False,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> AuthResult:
        self._open_email_registration(page, entry_mode=entry_mode)
        self._complete_email_authentication(
            page,
            mail_provider,
            result=result,
            email=result.email,
            passwordless_for_existing_login=passwordless_for_existing_login,
            prefer_password_flow=prefer_password_flow,
            totp_code_provider=totp_code_provider,
        )
        self._complete_about_you(
            page,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
        )
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
            page,
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
        page,
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
        _capture_browser_identity(page, result)
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
        prefer_password_flow: bool = False,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> None:
        otp_issued_after = time.time()
        self._submit_email(page, email)
        password_submitted = self._submit_password_if_requested(
            page,
            result.password,
            email=email,
            passwordless_for_existing_login=passwordless_for_existing_login,
            reject_existing_login=prefer_password_flow,
        )
        result.password_configured = result.password_configured or password_submitted
        password_flow_submitted = self._complete_email_otp(
            page,
            mail_provider,
            email=email,
            issued_after=otp_issued_after,
            password=result.password,
            prefer_password_flow=prefer_password_flow,
            totp_code_provider=totp_code_provider,
        )
        result.password_configured = result.password_configured or password_flow_submitted

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
        entry_selectors = SIGNUP_SELECTORS if normalized_entry_mode == "signup" else LOGIN_SELECTORS
        entry_text = "sign up" if normalized_entry_mode == "signup" else "log in"
        entry_stage = "signup" if normalized_entry_mode == "signup" else "login"

        # Start on the auth entrypoint used by the reference browser flow. The
        # home page adds a replaceable header click before the email form exists.
        try:
            page.goto(
                _chatgpt_auth_login_url(),
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
        self._accept_cookie_consent(page)
        self._raise_for_external_idp(page, "open-chatgpt")
        self._raise_for_challenge(page, "open-chatgpt")
        if _visible(page, EMAIL_INPUT_SELECTORS) is not None:
            return
        if not self._wait_for_page_state(
            page,
            lambda: (
                _visible(page, EMAIL_INPUT_SELECTORS) is not None
                or _visible(page, entry_selectors) is not None
            ),
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
            self._accept_cookie_consent(page)
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
            raise BrowserEmailRegistrationError(f"{entry_stage} button not found url={page.url}")
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
            raise BrowserEmailRegistrationError(f"{entry_stage} click had no effect url={page.url}")
        if _visible(page, EMAIL_INPUT_SELECTORS) is None:
            self._accept_cookie_consent(page)
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
                current = _visible_email_input(page) or field
                _type_registration_value(
                    page,
                    current,
                    email,
                    timeout_ms=5_000,
                )
                if _input_value(current) != email:
                    # React can replace the input during typing. Re-query the new
                    # element, then use the browser event path once.
                    current = _visible_email_input(page) or current
                    _type_registration_value(
                        page,
                        current,
                        email,
                        timeout_ms=5_000,
                    )
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
            raise BrowserEmailRegistrationError("email input is empty or changed before submit")
        initial_url = str(page.url or "")
        submit_method = "button"
        clicked = _click_first_native(
            page,
            EMAIL_CONTINUE_SELECTORS,
            timeout_ms=5_000,
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
            advanced, current = self._wait_for_email_retry_target(
                page,
                initial_url=initial_url,
                stage="wait-email-retry-ready",
            )
        if not advanced:
            # Retry only after the live email form becomes editable again. A
            # disabled email field means the first submit is still navigating.
            try:
                if _input_value(current) != email:
                    _type_registration_value(
                        page,
                        current,
                        email,
                        timeout_ms=5_000,
                    )
                clicked = _click_first_native(
                    page,
                    EMAIL_CONTINUE_SELECTORS,
                    timeout_ms=5_000,
                )
            except Exception as exc:
                # The auth SPA can replace the read/write email input with the
                # read-only password-page copy during typing. Accept that real
                # transition instead of reporting a stale ElementHandle error.
                advanced = self._wait_for_email_submit_transition(
                    page,
                    initial_url=initial_url,
                    stage="wait-email-retry-race",
                    timeout_s=8.0,
                )
                if not advanced:
                    raise BrowserEmailRegistrationError(f"email form retry failed: {exc}") from exc
            if not advanced:
                advanced = self._wait_for_email_submit_transition(
                    page,
                    initial_url=initial_url,
                    stage="wait-email-retry-submit",
                )
        if not advanced:
            advanced, current = self._wait_for_email_retry_target(
                page,
                initial_url=initial_url,
                stage="wait-email-enter-ready",
            )
        if not advanced:
            submit_method = "enter"
            try:
                _click_registration_input(current, timeout_ms=5_000)
                page.keyboard.press("Enter")
            except Exception as exc:
                raise BrowserEmailRegistrationError(f"email form submit failed: {exc}") from exc
            advanced = self._wait_for_email_submit_transition(
                page,
                initial_url=initial_url,
                stage="wait-email-enter-submit",
            )
        if not advanced:
            self._screenshot(page, "email-submit-no-effect.png")
            raise BrowserEmailRegistrationError(f"email submit had no effect url={page.url}")
        self._raise_for_external_idp(page, "submit-email")
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
        timeout_s: float | None = None,
    ) -> bool:
        """Wait for the post-email page to load before touching its controls."""
        configured_timeout = float(timeout_s or self.config.email_submit_timeout_s or 16.0)
        effective_timeout_s = max(
            8.0,
            min(
                30.0,
                configured_timeout,
                float(self.config.navigation_timeout_ms or 60_000) / 1_000,
            ),
        )
        self._emit(
            "browser.email.submit.waiting",
            {
                "stage": stage,
                "timeout_s": int(effective_timeout_s),
                "initial_url": initial_url,
            },
        )
        _wait_for_document_load(
            page,
            timeout_ms=min(15_000, int(effective_timeout_s * 1_000)),
        )
        # The Google One Tap overlay can be injected again during the slow
        # post-submit navigation. Remove it only after the document had a chance
        # to load, then let the stage poll decide whether the real form exists.
        self._remove_google_one_tap(page)
        started = time.monotonic()
        advanced = self._wait_for_page_state(
            page,
            lambda: _email_submit_advanced(page, initial_url=initial_url),
            stage=stage,
            timeout_s=effective_timeout_s,
            transient_challenge_timeout_s=(
                float(self.config.navigation_timeout_ms or 60_000) / 1_000
            ),
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

    def _wait_for_email_retry_target(
        self,
        page,
        *,
        initial_url: str,
        stage: str,
    ) -> tuple[bool, Any | None]:
        """Wait until navigation wins or the original email form is actionable again."""
        navigation_timeout_s = max(
            8.0,
            min(60.0, float(self.config.navigation_timeout_ms or 60_000) / 1_000),
        )

        def resolved() -> bool:
            if _email_submit_advanced(page, initial_url=initial_url):
                return True
            return _email_input_is_editable(_visible_email_input(page))

        self._emit(
            "browser.email.submit.settling",
            {
                "stage": stage,
                "timeout_s": int(navigation_timeout_s),
                "initial_url": initial_url,
            },
        )
        settled = self._wait_for_page_state(
            page,
            resolved,
            stage=stage,
            timeout_s=navigation_timeout_s,
            transient_challenge_timeout_s=navigation_timeout_s,
        )
        if _email_submit_advanced(page, initial_url=initial_url):
            self._emit(
                "browser.email.submit.settled",
                {"stage": stage, "state": "advanced", "url": page.url},
            )
            return True, None

        current = _visible_email_input(page)
        if settled and _email_input_is_editable(current):
            self._emit(
                "browser.email.submit.settled",
                {"stage": stage, "state": "retryable", "url": page.url},
            )
            return False, current

        self._screenshot(page, f"email-submit-pending-{stage}.png")
        raise BrowserEmailRegistrationError(
            f"email submit remained pending url={page.url} stage={stage}"
        )

    def _submit_password_if_requested(
        self,
        page,
        password: str,
        *,
        email: str = "",
        passwordless_for_existing_login: bool = False,
        require_password: bool = False,
        reject_existing_login: bool = False,
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
            if require_password:
                return _visible(page, PASSWORD_INPUT_SELECTORS) is not None
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
            if (
                not require_password
                and reached_next_stage
                and (
                    _otp_inputs(page)
                    or _about_you_visible(page)
                    or _has_authenticated_session(page)
                )
            ):
                self._emit("browser.password.skipped", {"url": page.url})
                return False
            self._screenshot(page, "password-or-otp-missing.png")
            raise BrowserEmailRegistrationError(f"password/OTP stage not reached url={page.url}")
        current_url = str(page.url or "").lower()
        if passwordless_for_existing_login and "/log-in/password" in current_url:
            if reject_existing_login:
                self._screenshot(page, "registration-email-already-exists.png")
                raise BrowserEmailRegistrationError(
                    f"registration email already exists url={page.url}"
                )
            _codex_start_passwordless_email_login(page)
            self._emit("browser.passwordless_otp.started", {"url": page.url})
            return False
        if passwordless_for_existing_login and "/create-account/password" not in current_url:
            self._screenshot(page, "password-branch-unknown.png")
            raise BrowserEmailRegistrationError(
                f"password page is neither registration nor login url={page.url}"
            )
        _type_registration_value(
            page,
            field,
            password,
            timeout_ms=5_000,
        )
        time.sleep(random.uniform(0.5, 1.2))
        if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000, physical=True):
            raise BrowserEmailRegistrationError("password continue button not found")
        self._emit("browser.password.submitted", {})
        return True

    def _submit_preferred_password_flow(self, page, *, email: str, password: str) -> bool:
        if not _click_continue_with_password_if_present(page):
            return False
        self._emit("browser.password_flow.selected", {"email": email, "url": page.url})

        # The OTP page can remain mounted after the click while the auth SPA
        # switches routes. Do not let its OTP input satisfy the generic
        # password-or-OTP wait; the password branch must expose a password field.
        password_ready = self._wait_for_page_state(
            page,
            lambda: _visible(page, PASSWORD_INPUT_SELECTORS) is not None,
            stage="wait-password-flow",
            timeout_s=12,
        )
        if not password_ready:
            self._emit("browser.password_flow.retrying", {"email": email}, "WARN")
            _click_continue_with_password_if_present(page)
            password_ready = self._wait_for_page_state(
                page,
                lambda: _visible(page, PASSWORD_INPUT_SELECTORS) is not None,
                stage="wait-password-flow-retry",
                timeout_s=12,
            )
        if not password_ready:
            self._screenshot(page, "password-flow-submit-missing.png")
            raise BrowserEmailRegistrationError(
                f"continue with password did not reach password page url={page.url}"
            )
        password_submitted = self._submit_password_if_requested(
            page,
            password,
            email=email,
            passwordless_for_existing_login=False,
            require_password=True,
        )
        if not password_submitted:
            self._screenshot(page, "password-flow-submit-missing.png")
            raise BrowserEmailRegistrationError(
                f"continue with password did not submit a password url={page.url}"
            )
        return True

    def _restart_email_otp_flow(
        self,
        page,
        mail_provider,
        *,
        email: str,
        password: str,
        prefer_password_flow: bool,
    ) -> bool:
        self._open_email_registration(page, entry_mode="signup")
        self._submit_email(page, email)
        password_submitted = self._submit_password_if_requested(
            page,
            password,
            email=email,
            passwordless_for_existing_login=False,
            reject_existing_login=prefer_password_flow,
        )
        if prefer_password_flow:
            password_submitted = (
                self._submit_preferred_password_flow(
                    page,
                    email=email,
                    password=password,
                )
                or password_submitted
            )
        self._raise_for_external_idp(page, "restart-email-otp")
        return password_submitted

    def _complete_email_otp(
        self,
        page,
        mail_provider,
        *,
        email: str,
        issued_after: float,
        password: str = "",
        prefer_password_flow: bool = False,
        totp_code_provider: Callable[[], str] | None = None,
    ) -> bool:
        password_flow_submitted = False
        if prefer_password_flow and self._submit_preferred_password_flow(
            page,
            email=email,
            password=password,
        ):
            password_flow_submitted = True
            self._emit("browser.password_flow.submitted", {"email": email})
        otp_retry_count = 0
        otp_retry_max = 2
        current_issued_after = issued_after

        def restart_for_retry(reason: str) -> None:
            nonlocal current_issued_after, password_flow_submitted
            current_issued_after = time.time()
            self._emit(
                "browser.otp.restart.started",
                {
                    "email": email,
                    "attempt": otp_retry_count + 1,
                    "reason": reason,
                },
                "WARN",
            )
            try:
                password_flow_submitted = (
                    self._restart_email_otp_flow(
                        page,
                        mail_provider,
                        email=email,
                        password=password,
                        prefer_password_flow=prefer_password_flow,
                    )
                    or password_flow_submitted
                )
                self._emit(
                    "browser.otp.restart.completed",
                    {"email": email, "attempt": otp_retry_count + 1},
                )
            except Exception as exc:
                self._emit(
                    "browser.otp.restart.failed",
                    {
                        "email": email,
                        "attempt": otp_retry_count + 1,
                        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    },
                    "WARN",
                )

        while True:
            reached_next_stage = self._wait_for_page_state(
                page,
                lambda: (
                    bool(_otp_inputs(page))
                    or _is_mfa_challenge_url(str(page.url or ""))
                    or _about_you_visible(page)
                    or _has_authenticated_session(page)
                    or _visible(page, ACCOUNT_MISSING_SELECTORS) is not None
                    or _visible(page, ACCOUNT_DEACTIVATED_SELECTORS) is not None
                ),
                stage="wait-email-otp",
                timeout_s=45,
            )
            self._raise_for_terminal_account_error(page, "email-otp")
            if _is_mfa_challenge_url(str(page.url or "")):
                self._complete_totp_challenge(
                    page,
                    totp_code_provider=totp_code_provider,
                )
                return password_flow_submitted
            inputs = _otp_inputs(page)
            if not inputs:
                if reached_next_stage and (
                    _about_you_visible(page) or _has_authenticated_session(page)
                ):
                    self._emit("browser.otp.skipped", {"url": page.url})
                    return password_flow_submitted
                if otp_retry_count < otp_retry_max:
                    otp_retry_count += 1
                    self._emit(
                        "browser.otp.retrying",
                        {"email": email, "attempt": otp_retry_count + 1},
                        "WARN",
                    )
                    restart_for_retry("otp_form_missing")
                    continue
                self._screenshot(page, "otp-form-missing.png")
                raise BrowserEmailRegistrationError(f"email OTP input not found url={page.url}")
            self._emit(
                "browser.otp.wait.started",
                {
                    "email": email,
                    "timeout_s": self.config.otp_timeout_s,
                    "attempt": otp_retry_count + 1,
                },
            )
            try:
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
            except Exception:
                if otp_retry_count >= otp_retry_max:
                    raise
                otp_retry_count += 1
                self._emit(
                    "browser.otp.retrying",
                    {"email": email, "attempt": otp_retry_count + 1},
                    "WARN",
                )
                restart_for_retry("otp_wait_failed")
                continue
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
                lambda: (
                    _about_you_visible(page)
                    or _has_authenticated_session(page)
                    or _visible(page, OTP_ERROR_SELECTORS) is not None
                    or _visible(page, ACCOUNT_MISSING_SELECTORS) is not None
                    or _visible(page, ACCOUNT_DEACTIVATED_SELECTORS) is not None
                ),
                stage="wait-email-otp-submit",
                timeout_s=30,
            )
            self._raise_for_terminal_account_error(page, "email-otp")
            error = _visible(page, OTP_ERROR_SELECTORS)
            if error is not None:
                if otp_retry_count < otp_retry_max:
                    otp_retry_count += 1
                    self._emit(
                        "browser.otp.retrying",
                        {"email": email, "attempt": otp_retry_count + 1},
                        "WARN",
                    )
                    restart_for_retry("otp_rejected")
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
                        return password_flow_submitted
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
                if otp_retry_count < otp_retry_max:
                    otp_retry_count += 1
                    self._emit(
                        "browser.otp.retrying",
                        {"email": email, "attempt": otp_retry_count + 1},
                        "WARN",
                    )
                    restart_for_retry("otp_submit_no_effect")
                    continue
                self._screenshot(page, "otp-submit-no-effect.png")
                raise BrowserEmailRegistrationError(
                    f"email OTP submit had no effect url={page.url}"
                )
            self._emit("browser.otp.submitted", {"email": email})
            return password_flow_submitted

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
        if not self._wait_for_page_state(
            page,
            lambda: _has_otp_input(page),
            stage="wait-totp-input",
            timeout_s=30,
        ):
            self._screenshot(page, "totp-input-missing.png")
            raise BrowserEmailRegistrationError(f"TOTP input not found url={page.url}")
        code = str(totp_code_provider() or "").strip()
        if not code.isdigit():
            raise BrowserEmailRegistrationError("2FAuth returned an invalid TOTP code")
        if not _fill_otp(page, code):
            raise BrowserEmailRegistrationError("TOTP input not found")

        # The MFA page is an SPA and its visible button is not a reliable
        # completion signal. Match the browser HAR and submit the challenge
        # from the same page context so cookies, origin, and device headers
        # are identical to the preceding login requests.
        factor_id = _totp_factor_id_from_url(str(page.url or ""))
        if factor_id and callable(getattr(page, "evaluate", None)):
            self._emit(
                "browser.totp.verify.started",
                {"factor_id": factor_id, "url": page.url},
            )
            try:
                payload = _verify_totp_in_browser(
                    page,
                    factor_id=factor_id,
                    code=code,
                    navigation_timeout_ms=self.config.navigation_timeout_ms,
                )
            except _BrowserTotpVerificationUnavailable:
                # A lightweight test page or an older auth surface may not
                # expose page.evaluate. Keep the existing physical fallback
                # for that case only; real HTTP failures are raised above it.
                payload = None
            except BrowserEmailRegistrationError as exc:
                self._emit(
                    "browser.totp.verify.failed",
                    {
                        "factor_id": factor_id,
                        "url": page.url,
                        "error": str(exc)[:800],
                    },
                    "WARN",
                )
                raise
            else:
                page_data = payload.get("page") if isinstance(payload, dict) else {}
                page_data = page_data if isinstance(page_data, dict) else {}
                self._emit(
                    "browser.totp.verify.succeeded",
                    {
                        "factor_id": factor_id,
                        "page_type": str(page_data.get("type") or "").strip(),
                        "url": page.url,
                    },
                )
                self._emit(
                    "browser.totp.submitted",
                    {"url": page.url, "method": "direct_verify"},
                )
                return

        submitted = _click_first(
            page,
            CONTINUE_SELECTORS,
            timeout_ms=5_000,
            physical=True,
        )
        if not submitted:
            try:
                page.keyboard.press("Enter")
                submitted = True
            except Exception:
                submitted = False
        if not submitted:
            raise BrowserEmailRegistrationError("TOTP continue button not found")
        self._emit(
            "browser.totp.submitted",
            {
                "url": page.url,
                "method": "ui_click",
                "factor_id": factor_id,
            },
        )
        if not self._wait_for_page_state(
            page,
            lambda: (
                not _is_mfa_challenge_url(str(page.url or "")) or _has_authenticated_session(page)
            ),
            stage="wait-totp-submit",
            timeout_s=30,
        ):
            raise BrowserEmailRegistrationError(
                "TOTP UI submit produced no navigation: "
                f"url={page.url} factor_id={factor_id or 'unknown'}"
            )

    def _complete_about_you(
        self,
        page,
        *,
        first_name: str,
        last_name: str,
        birth_date: tuple[int, int, int] | None = None,
    ) -> None:
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
            if name is not None and (birthday is not None or len(birthday_segments) >= 3):
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
        birth_year, birth_month, birth_day = birth_date or _random_registration_birthday()
        try:
            name_field.focus()
            page.keyboard.type(f"{first_name} {last_name}", delay=random.randint(30, 80))
            age = str(max(18, time.gmtime().tm_year - birth_year))
            if birthday is None:
                _fill_segmented_birthday(
                    page,
                    birthday_segments,
                    year=birth_year,
                    month=birth_month,
                    day=birth_day,
                )
            else:
                birthday_field = elements[birthday["index"]]
                birthday_field.focus()
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                if legacy_age:
                    page.keyboard.type(age, delay=random.randint(40, 100))
                elif birthday["type"] == "date":
                    try:
                        birthday_field.fill(f"{birth_year:04d}-{birth_month:02d}-{birth_day:02d}")
                    except Exception:
                        page.keyboard.type(
                            f"{birth_year:04d}-{birth_month:02d}-{birth_day:02d}",
                            delay=random.randint(30, 70),
                        )
                else:
                    page.keyboard.type(
                        f"{birth_month:02d}/{birth_day:02d}/{birth_year:04d}",
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
                    lambda: (
                        _visible(page, USER_ALREADY_EXISTS_SELECTORS) is None
                        or _has_authenticated_session(page)
                    ),
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

    def _accept_cookie_consent(self, page) -> None:
        if _click_first(
            page,
            COOKIE_ACCEPT_SELECTORS,
            timeout_ms=2_500,
            physical=True,
        ):
            self._emit("browser.cookie_consent.accepted", {"url": page.url})

    def _raise_for_external_idp(self, page, stage: str) -> None:
        url = str(page.url or "").lower()
        bad_hosts = (
            "accounts.google.com",
            "appleid.apple.com",
            "login.microsoftonline.com",
            "github.com/login",
            "facebook.com/login",
        )
        if any(host in url for host in bad_hosts):
            self._screenshot(page, f"external-idp-{stage}.png")
            raise BrowserEmailRegistrationError(
                f"browser flow entered third-party login during {stage}: {url}"
            )

    def _wait_for_page_state(
        self,
        page,
        predicate: Callable[[], bool],
        *,
        stage: str,
        timeout_s: float,
        transient_challenge_timeout_s: float = 0.0,
    ) -> bool:
        deadline = time.monotonic() + max(0.1, timeout_s)
        screenshot_at = time.monotonic() + min(15, max(1, timeout_s / 2))
        screenshot_taken = False
        challenge_budget_s = max(0.0, transient_challenge_timeout_s)
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return True
            except Exception as exc:
                if _is_target_closed_error(exc):
                    raise BrowserEmailRegistrationError(
                        f"browser target closed during {stage}: {exc}"
                    ) from exc
                self._emit(
                    "browser.wait.predicate_error",
                    {
                        "stage": stage,
                        "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    },
                    "WARN",
                )
            challenge_reason = _challenge_reason(page)
            if challenge_reason == "Cloudflare challenge" and challenge_budget_s > 0:
                challenge_started_at = time.monotonic()
                challenge_elapsed_s = self._wait_for_transient_challenge(
                    page,
                    stage=stage,
                    reason=challenge_reason,
                    timeout_s=challenge_budget_s,
                )
                challenge_budget_s = max(0.0, challenge_budget_s - challenge_elapsed_s)
                # A security-verification page is part of the navigation, not a
                # failed form transition. Preserve the original state-wait budget.
                deadline += max(0.0, time.monotonic() - challenge_started_at)
                continue
            if challenge_reason:
                self._raise_for_challenge(page, stage)
            if not screenshot_taken and time.monotonic() >= screenshot_at:
                self._screenshot(page, f"waiting-{stage}.png")
                screenshot_taken = True
            time.sleep(0.5)
        return False

    def _wait_for_transient_challenge(
        self,
        page,
        *,
        stage: str,
        reason: str,
        timeout_s: float,
    ) -> float:
        started_at = time.monotonic()
        deadline = started_at + max(0.1, timeout_s)
        self._emit(
            "browser.challenge.waiting",
            {
                "stage": stage,
                "reason": reason,
                "timeout_s": round(max(0.1, timeout_s), 1),
                "url": page.url,
            },
            "WARN",
        )
        while time.monotonic() < deadline:
            current_reason = _challenge_reason(page)
            if not current_reason:
                elapsed_s = max(0.0, time.monotonic() - started_at)
                self._emit(
                    "browser.challenge.cleared",
                    {
                        "stage": stage,
                        "reason": reason,
                        "elapsed_ms": int(elapsed_s * 1_000),
                        "url": page.url,
                    },
                )
                return elapsed_s
            reason = current_reason
            time.sleep(0.5)

        elapsed_s = max(0.0, time.monotonic() - started_at)
        self._screenshot(page, f"challenge-{stage}.png")
        self._emit(
            "browser.challenge.timeout",
            {
                "stage": stage,
                "reason": reason,
                "elapsed_ms": int(elapsed_s * 1_000),
                "url": page.url,
            },
            "WARN",
        )
        raise BrowserEmailRegistrationError(
            f"{reason} timed out after {elapsed_s:.1f}s during {stage}"
        )

    def _raise_for_challenge(self, page, stage: str) -> None:
        reason = _challenge_reason(page)
        if not reason:
            return
        self._screenshot(page, f"challenge-{stage}.png")
        raise BrowserEmailRegistrationError(f"{reason} during {stage}")

    def _screenshot(self, page, filename: str) -> None:
        if not self.config.capture_artifacts or self.artifact_dir is None:
            return
        try:
            path = self.artifact_dir / filename
            page.screenshot(path=str(path), full_page=True)
            path.chmod(0o600)
        except Exception:
            pass

    def _emit(self, stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        callback_data = data
        if self._browser_log is not None:
            self._browser_log.record(stage, data, level, notify=False)
            callback_data = redact_browser_value(data)
        if self._event_callback is not None:
            self._event_callback(stage, callback_data, level)

    def _install_browser_log(self, context: Any) -> BrowserLogRecorder | None:
        if not self.config.browser_log_enabled:
            return None
        path = self.artifact_dir / "browser.log.jsonl" if self.artifact_dir else None
        recorder = BrowserLogRecorder(
            path=path,
            emitter=self._event_callback,
            capture_bodies=self.config.browser_log_capture_bodies,
            max_body_chars=self.config.browser_log_max_body_chars,
        )
        self._browser_log = recorder
        recorder.install(context)
        return recorder


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
_CONTINUE_WITH_PASSWORD_LABELS = (
    "Continue with password",
    "Mit Passwort fortfahren",
    "Doorgaan met wachtwoord",
    "Влизане с парола",
    "Nastavi s lozinkom",
    "Συνέχεια με κωδικό πρόσβασης",
    "Použít heslo",
    "Fortsæt med adgangskode",
    "Jätka parooliga",
    "Jatka salasanalla",
    "Continuer avec un mot de passe",
    "Folytatás jelszóval",
    "Continua con la password",
    "Turpināt ar paroli",
    "Tęsti su slaptažodžiu",
    "Kontynuuj za pomocą hasła",
    "Continuar com palavra-passe",
    "Continuă cu parola",
    "Pokračovať s heslom",
    "Nadaljujte z geslom",
    "Continuar con contraseña",
    "Fortsätt med lösenord",
    "Halda áfram með lykilorði",
    "Fortsett med passord",
    "使用密码继续",
    "使用密碼繼續",
    "パスワードで続行",
)
CONTINUE_WITH_PASSWORD_SELECTORS = (
    'a[href*="/create-account/password"]',
    'a[href*="/log-in/password"]',
    *(
        selector
        for label in _CONTINUE_WITH_PASSWORD_LABELS
        for selector in (
            f'button:has-text("{label}")',
            f'a:has-text("{label}")',
        )
    ),
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
COOKIE_ACCEPT_SELECTORS = (
    "button#onetrust-accept-btn-handler",
    'button:has-text("Accept all")',
    'button:has-text("Accept")',
    'button:has-text("I agree")',
    'button:has-text("同意")',
    'button:has-text("接受")',
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
OTP_ERROR_SELECTORS = ("text=/incorrect code|invalid code|wrong code|验证码不正确|验证码错误/i",)
ACCOUNT_MISSING_SELECTORS = ("text=/No eligible ChatGPT account found|chatgpt_account_missing/i",)
ACCOUNT_DEACTIVATED_SELECTORS = (
    "text=/account has been deleted or deactivated|account_deactivated/i",
)
USER_ALREADY_EXISTS_SELECTORS = (
    "text=/user_already_exists|An account already exists for this email address or phone number/i",
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


_REGISTRATION_NAME_POOLS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "US": (
        (
            "Aiden",
            "Amelia",
            "Avery",
            "Benjamin",
            "Camila",
            "Charlotte",
            "Daniel",
            "Elijah",
            "Emily",
            "Ethan",
            "Evelyn",
            "Harper",
            "Henry",
            "Isabella",
            "Jack",
            "James",
            "Liam",
            "Lucas",
            "Mason",
            "Mia",
            "Noah",
            "Olivia",
            "Sofia",
            "William",
        ),
        (
            "Anderson",
            "Baker",
            "Brown",
            "Campbell",
            "Clark",
            "Davis",
            "Garcia",
            "Harris",
            "Hernandez",
            "Jackson",
            "Johnson",
            "Lee",
            "Lewis",
            "Martinez",
            "Miller",
            "Moore",
            "Nelson",
            "Rodriguez",
            "Smith",
            "Taylor",
            "Thomas",
            "Thompson",
            "Walker",
            "Wilson",
        ),
    ),
    "JP": (
        (
            "Akari",
            "Aoi",
            "Daichi",
            "Haruka",
            "Haruto",
            "Hina",
            "Hinata",
            "Kaito",
            "Mei",
            "Ren",
            "Riku",
            "Rin",
            "Sakura",
            "Sota",
            "Yui",
            "Yuto",
        ),
        (
            "Abe",
            "Endo",
            "Fujita",
            "Hayashi",
            "Ito",
            "Kato",
            "Kobayashi",
            "Matsumoto",
            "Mori",
            "Nakamura",
            "Saito",
            "Sato",
            "Suzuki",
            "Takahashi",
            "Tanaka",
            "Yamada",
        ),
    ),
    "DE": (
        (
            "Anna",
            "Ben",
            "Clara",
            "Emilia",
            "Felix",
            "Finn",
            "Hannah",
            "Jonas",
            "Laura",
            "Leon",
            "Lina",
            "Lukas",
            "Marie",
            "Maximilian",
            "Mia",
            "Paul",
        ),
        (
            "Bauer",
            "Becker",
            "Fischer",
            "Hoffmann",
            "Klein",
            "Koch",
            "Krueger",
            "Lehmann",
            "Meyer",
            "Mueller",
            "Richter",
            "Schmidt",
            "Schneider",
            "Schulz",
            "Wagner",
            "Weber",
        ),
    ),
    "GB": (
        (
            "Alice",
            "Amelia",
            "Arthur",
            "Charlotte",
            "Ella",
            "Emily",
            "Florence",
            "Freddie",
            "George",
            "Harry",
            "Isla",
            "Jack",
            "Leo",
            "Noah",
            "Oliver",
            "Sophie",
        ),
        (
            "Adams",
            "Bennett",
            "Clarke",
            "Davies",
            "Edwards",
            "Evans",
            "Green",
            "Hall",
            "Harris",
            "Hughes",
            "Jones",
            "Lewis",
            "Roberts",
            "Taylor",
            "Thomas",
            "Williams",
        ),
    ),
    "FR": (
        (
            "Alice",
            "Ambre",
            "Arthur",
            "Camille",
            "Chloe",
            "Emma",
            "Gabriel",
            "Hugo",
            "Jade",
            "Jules",
            "Leo",
            "Louis",
            "Louise",
            "Lucas",
            "Nathan",
            "Rose",
        ),
        (
            "Bernard",
            "David",
            "Dubois",
            "Durand",
            "Fournier",
            "Garcia",
            "Lambert",
            "Laurent",
            "Lefebvre",
            "Leroy",
            "Martin",
            "Mercier",
            "Michel",
            "Moreau",
            "Roux",
            "Simon",
        ),
    ),
    "ES": (
        (
            "Alejandro",
            "Alvaro",
            "Carmen",
            "Daniel",
            "David",
            "Elena",
            "Hugo",
            "Lucia",
            "Manuel",
            "Maria",
            "Mateo",
            "Pablo",
            "Paula",
            "Sofia",
            "Valeria",
            "Vega",
        ),
        (
            "Alonso",
            "Blanco",
            "Castro",
            "Diaz",
            "Fernandez",
            "Garcia",
            "Gomez",
            "Gonzalez",
            "Lopez",
            "Martin",
            "Martinez",
            "Moreno",
            "Navarro",
            "Perez",
            "Ruiz",
            "Sanchez",
        ),
    ),
    "IT": (
        (
            "Alessandro",
            "Andrea",
            "Aurora",
            "Beatrice",
            "Chiara",
            "Davide",
            "Elisa",
            "Francesco",
            "Giulia",
            "Leonardo",
            "Lorenzo",
            "Luca",
            "Marco",
            "Matteo",
            "Sofia",
            "Tommaso",
        ),
        (
            "Bianchi",
            "Colombo",
            "Conti",
            "Costa",
            "De Luca",
            "Esposito",
            "Ferrari",
            "Fontana",
            "Gallo",
            "Greco",
            "Lombardi",
            "Mancini",
            "Marino",
            "Ricci",
            "Romano",
            "Rossi",
        ),
    ),
}


def _registration_identity(
    email: str,
    *,
    locale: str = "",
) -> tuple[str, str, tuple[int, int, int]]:
    country = _registration_country(locale)
    first_names, last_names = _REGISTRATION_NAME_POOLS.get(
        country,
        _REGISTRATION_NAME_POOLS["US"],
    )
    digest = hashlib.sha256(
        f"{str(email or '').strip().casefold()}|{str(locale or '').strip().casefold()}".encode()
    ).digest()
    first_name = first_names[int.from_bytes(digest[0:4], "big") % len(first_names)]
    last_name = last_names[int.from_bytes(digest[4:8], "big") % len(last_names)]
    birth_year = 1980 + int.from_bytes(digest[8:10], "big") % 23
    birth_month = 1 + digest[10] % 12
    maximum_day = calendar.monthrange(birth_year, birth_month)[1]
    birth_day = 1 + digest[11] % maximum_day
    return first_name, last_name, (birth_year, birth_month, birth_day)


def _registration_country(locale: str) -> str:
    parts = [part for part in re.split(r"[-_]", str(locale or "").strip()) if part]
    for part in reversed(parts[1:]):
        if len(part) == 2 and part.isalpha():
            return part.upper()
    language = parts[0].casefold() if parts else ""
    return {
        "de": "DE",
        "es": "ES",
        "fr": "FR",
        "it": "IT",
        "ja": "JP",
    }.get(language, "US")


def _random_registration_birthday() -> tuple[int, int, int]:
    year = 1980 + secrets.randbelow(23)
    month = 1 + secrets.randbelow(12)
    day = 1 + secrets.randbelow(calendar.monthrange(year, month)[1])
    return year, month, day


def _chatgpt_home_url() -> str:
    return "https://chatgpt.com/"


def _chatgpt_auth_login_url() -> str:
    return "https://chatgpt.com/auth/login"


def _is_target_closed_error(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return any(
        marker in text
        for marker in (
            "target page, context or browser has been closed",
            "page has been closed",
            "browser has been closed",
            "target closed",
            "execution context was destroyed",
            "connection closed while reading from the driver",
        )
    )


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


def _email_input_is_editable(element: Any) -> bool:
    if element is None:
        return False
    checker = getattr(element, "is_editable", None)
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    getter = getattr(element, "get_attribute", None)
    if callable(getter):
        try:
            if getter("disabled") is not None or getter("readonly") is not None:
                return False
            if str(getter("aria-disabled") or "").strip().lower() == "true":
                return False
        except Exception:
            return False
    return True


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


def _type_registration_value(
    page: Any,
    element: Any,
    value: str,
    *,
    timeout_ms: int,
) -> None:
    """Enter registration credentials through keyboard events."""
    _click_registration_input(element, timeout_ms=timeout_ms)
    press = getattr(element, "press", None)
    if callable(press):
        press("ControlOrMeta+A", timeout=timeout_ms)
        press("Backspace", timeout=timeout_ms)
    else:
        page.keyboard.press("ControlOrMeta+A")
        page.keyboard.press("Backspace")

    delay = random.randint(35, 85)
    type_value = getattr(element, "type", None)
    if callable(type_value):
        type_value(str(value), delay=delay, timeout=timeout_ms)
        return

    # Lightweight test adapters do not expose ElementHandle.type(). Keep their
    # value model synchronized after exercising the same keyboard path.
    page.keyboard.type(str(value), delay=delay)
    if _input_value(element) != str(value):
        fill = getattr(element, "fill", None)
        if not callable(fill):
            raise BrowserEmailRegistrationError("registration input does not support typing")
        fill(str(value), timeout=timeout_ms)


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
    native_first: bool = False,
) -> bool:
    element = _visible(page, selectors)
    if element is None:
        return False
    if physical:
        return _physical_click_element(page, element, timeout_ms=timeout_ms)
    if native_first:
        try:
            element.scroll_into_view_if_needed(timeout=2_000)
        except Exception:
            pass
        try:
            element.click(timeout=timeout_ms, no_wait_after=True)
            return True
        except Exception:
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


def _click_first_native(
    page,
    selectors: tuple[str, ...],
    *,
    timeout_ms: int,
) -> bool:
    """Click a live control natively, falling back to DOM dispatch."""
    return _click_first(page, selectors, timeout_ms=timeout_ms, native_first=True)


def _click_continue_with_password_if_present(page) -> bool:
    """Switch the registration OTP screen to the explicit password branch."""
    element = _visible(page, CONTINUE_WITH_PASSWORD_SELECTORS)
    if element is None:
        return False
    try:
        # This control is a React route transition. A native Playwright click
        # drives the same browser event path as a user click; DOM dispatch alone
        # can report success while leaving the OTP page mounted.
        element.click(timeout=5_000, no_wait_after=True)
        return True
    except Exception:
        return _physical_click_element(page, element, timeout_ms=5_000)


def _physical_click_element(page, element, *, timeout_ms: int) -> bool:
    """Use Playwright's native input path, with DOM dispatch as a fallback."""
    del page
    try:
        element.click(timeout=timeout_ms, no_wait_after=True)
        return True
    except Exception:
        try:
            element.evaluate("(el) => { el.click(); return true; }")
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


def _capture_browser_identity(page: Any, result: AuthResult) -> None:
    try:
        identity = page.evaluate(
            """() => ({
                userAgent: navigator.userAgent || '',
                platform: navigator.platform || '',
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
                timezoneOffset: new Date().getTimezoneOffset(),
                languages: Array.from(navigator.languages || [navigator.language]).filter(Boolean),
            })"""
        )
    except Exception:
        return
    if not isinstance(identity, dict):
        return
    user_agent = str(identity.get("userAgent") or "").strip()
    result.browser_user_agent = user_agent
    result.browser_platform = str(identity.get("platform") or "").strip()
    result.browser_timezone = str(identity.get("timezone") or "").strip()
    try:
        browser_offset = identity.get("timezoneOffset")
        result.browser_timezone_offset = (
            -int(browser_offset) if browser_offset is not None else None
        )
    except (TypeError, ValueError):
        result.browser_timezone_offset = None
    languages = identity.get("languages")
    result.browser_accept_language = _accept_language_from_browser(languages)
    # Preserve the browser's real version in the result. Protocol clients map
    # versions newer than curl_cffi's named profiles to its rolling alias.
    firefox_match = re.search(r"Firefox/(\d+)", user_agent, flags=re.IGNORECASE)
    chrome_match = re.search(r"(?:Chrome|Chromium)/(\d+)", user_agent, flags=re.IGNORECASE)
    if firefox_match:
        result.browser_impersonate = f"firefox{firefox_match.group(1)}"
    elif chrome_match:
        result.browser_impersonate = f"chrome{chrome_match.group(1)}"
    else:
        result.browser_impersonate = ""


def _accept_language_from_browser(value: Any) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    languages: list[str] = []
    for item in value:
        language = str(item or "").strip()
        if language and language not in languages:
            languages.append(language)
    if not languages:
        return ""
    if len(languages) == 1 and "-" in languages[0]:
        base_language = languages[0].split("-", 1)[0]
        if base_language not in languages:
            languages.append(base_language)
    parts = [languages[0]]
    for index, language in enumerate(languages[1:], start=1):
        quality = max(0.1, 1.0 - index / 10)
        parts.append(f"{language};q={quality:.1f}")
    return ",".join(parts)


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
        raise BrowserEmailRegistrationError("browser email OTP validation returned invalid data")
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


def _totp_factor_id_from_url(current_url: str) -> str:
    parsed = urlparse(str(current_url or ""))
    segments = [unquote(segment).strip() for segment in parsed.path.split("/") if segment]
    for index, segment in enumerate(segments[:-1]):
        if segment.casefold() == "mfa-challenge" and segments[index + 1]:
            return segments[index + 1]
    query = parse_qs(parsed.query)
    for key in ("factor_id", "factorId", "id"):
        values = query.get(key) or []
        if values and str(values[0]).strip():
            return unquote(str(values[0]).strip())
    return ""


def _verify_totp_in_browser(
    page,
    *,
    factor_id: str,
    code: str,
    navigation_timeout_ms: int,
) -> dict[str, Any]:
    """Verify TOTP through the authenticated auth.openai.com page context."""
    evaluate = getattr(page, "evaluate", None)
    if not callable(evaluate):
        raise _BrowserTotpVerificationUnavailable("browser page has no evaluate method")
    normalized_factor_id = str(factor_id or "").strip()
    normalized_code = str(code or "").strip()
    if not normalized_factor_id:
        raise _BrowserTotpVerificationUnavailable("TOTP challenge has no factor id")
    if not normalized_code.isdigit():
        raise BrowserEmailRegistrationError("2FAuth returned an invalid TOTP code")

    request = {
        "factorId": normalized_factor_id,
        "code": normalized_code,
        "invocationId": str(uuid4()),
    }
    try:
        result = evaluate(
            """async ({factorId, code, invocationId}) => {
                const controller = new AbortController();
                const timer = setTimeout(() => controller.abort(), 30000);
                try {
                    const response = await fetch('/api/accounts/mfa/verify', {
                        method: 'POST',
                        credentials: 'include',
                        headers: {
                            'accept': 'application/json',
                            'content-type': 'application/json',
                            'x-access-flow-invocation-id': invocationId,
                        },
                        body: JSON.stringify({id: factorId, type: 'totp', code}),
                        signal: controller.signal,
                    });
                    const text = await response.text();
                    let payload = {};
                    try { payload = JSON.parse(text); } catch (_) {}
                    return {
                        status: response.status,
                        payload,
                        body: text.slice(0, 2000),
                    };
                } catch (error) {
                    return {
                        network_error: `${error?.name || 'FetchError'}: ${error?.message || error}`,
                    };
                } finally {
                    clearTimeout(timer);
                }
            }""",
            request,
        )
    except Exception as exc:
        detail = str(exc)[:500]
        lowered = detail.casefold()
        if "timeout" in lowered or "timed out" in lowered or "abort" in lowered:
            raise BrowserEmailRegistrationError(
                f"TOTP verification request timed out: {detail}"
            ) from exc
        raise BrowserEmailRegistrationError(
            f"TOTP verification browser request failed: {detail}"
        ) from exc

    if not isinstance(result, dict):
        raise BrowserEmailRegistrationError(
            "TOTP verification browser response was not an object"
        )
    network_error = str(result.get("network_error") or "").strip()
    if network_error:
        lowered = network_error.casefold()
        if "timeout" in lowered or "timed out" in lowered or "abort" in lowered:
            raise BrowserEmailRegistrationError(
                f"TOTP verification request timed out: {network_error}"
            )
        raise BrowserEmailRegistrationError(
            f"TOTP verification transport failed: {network_error}"
        )

    try:
        status = int(result.get("status") or 0)
    except (TypeError, ValueError):
        status = 0
    payload = result.get("payload")
    payload = payload if isinstance(payload, dict) else {}
    body = str(result.get("body") or "")[:800]
    safe_body = body.replace(normalized_code, "[redacted]")
    if status // 100 != 2:
        error = payload.get("error")
        if isinstance(error, dict):
            error_code = str(error.get("code") or "unknown")
            error_message = str(error.get("message") or "")
        else:
            error_code = str(error or payload.get("code") or "unknown")
            error_message = str(payload.get("message") or "")
        message = (error_message or safe_body or "unknown")[:500]
        error_type = (
            BrowserAccountDeactivatedError
            if error_code == "account_deactivated"
            else BrowserEmailRegistrationError
        )
        raise error_type(
            "OpenAI TOTP verification failed: "
            f"http_status={status or 'unknown'} code={error_code} "
            f"message={message}"
        )

    page_data = payload.get("page")
    page_data = page_data if isinstance(page_data, dict) else {}
    page_type = str(page_data.get("type") or "").strip().lower()
    continue_url = str(payload.get("continue_url") or "").strip()
    if not continue_url and page_type == "external_url":
        page_payload = page_data.get("payload")
        page_payload = page_payload if isinstance(page_payload, dict) else {}
        continue_url = str(page_payload.get("url") or "").strip()
    if not continue_url:
        raise BrowserEmailRegistrationError(
            "OpenAI TOTP verification response has no continuation URL: "
            f"http_status={status or 'unknown'} page_type={page_type or 'unknown'} "
            f"body={safe_body}"
        )
    try:
        page.goto(
            urljoin("https://auth.openai.com", continue_url),
            wait_until="domcontentloaded",
            timeout=navigation_timeout_ms,
        )
    except Exception as exc:
        detail = str(exc)[:500]
        if "timeout" in detail.casefold() or "timed out" in detail.casefold():
            raise BrowserEmailRegistrationError(
                f"TOTP continuation navigation timed out: {detail}"
            ) from exc
        raise BrowserEmailRegistrationError(
            f"TOTP continuation navigation failed: {detail}"
        ) from exc
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
    month: int,
    day: int,
) -> None:
    elements = page.query_selector_all('[role="spinbutton"]')
    fallback_values = (str(month), str(day), str(year))
    for position, item in enumerate(metadata[:3]):
        label = str(item.get("ariaLabel") or "").casefold()
        maximum = _metadata_int(item.get("valueMax"))
        if "year" in label or maximum >= 1000:
            value = str(year)
        elif "month" in label or maximum == 12:
            value = str(month)
        elif "day" in label or 28 <= maximum <= 31:
            value = str(day)
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


def _input_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "") for key in ("type", "name", "placeholder", "ariaLabel", "label")
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
