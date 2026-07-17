from __future__ import annotations

import random
import shutil
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from refactor_app.plugins.openai_auth_protocol.auth_flow import (
    AuthResult,
    default_password_from_email,
    session_account_fields,
)

TraceEmitter = Callable[[str, dict[str, Any], str], None]
APP_ROOT = Path(__file__).resolve().parents[4]


class BrowserEmailRegistrationError(RuntimeError):
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


class CamoufoxEmailRegistration:
    def __init__(
        self,
        config: BrowserEmailRegistrationConfig,
        *,
        event_callback: TraceEmitter | None = None,
    ) -> None:
        self.config = config
        self._event_callback = event_callback
        root = (
            Path(config.artifact_root)
            if config.artifact_root
            else APP_ROOT / "runtime" / "artifacts"
        )
        self.artifact_dir = root / "protocol-register" / (config.work_id or str(uuid4()))
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

    def run(self, mail_provider) -> AuthResult:
        from browserforge.fingerprints import Screen
        from camoufox.sync_api import Camoufox

        email = mail_provider.create_mailbox()
        result = AuthResult()
        result.email = email
        result.password = default_password_from_email(email)
        result.register_method = "email_browser"
        first_name, last_name = _registration_name()
        profile_dir = tempfile.mkdtemp(prefix="refactor_browser_register_")
        page = None
        self._emit("browser.started", {"email": email, "headless": self.config.headless})
        try:
            with Camoufox(
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
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(30_000)
                try:
                    return self._run_in_context(
                        context,
                        page,
                        mail_provider,
                        result=result,
                        first_name=first_name,
                        last_name=last_name,
                    )
                except Exception:
                    self._screenshot(page, "failed.png")
                    raise
        except Exception as exc:
            self._emit(
                "browser.failed",
                {
                    "email": email,
                    "error": f"{type(exc).__name__}: {exc}",
                    "artifact_dir": str(self.artifact_dir),
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
    ) -> AuthResult:
        self._open_email_registration(page)
        otp_issued_after = time.time()
        self._submit_email(page, result.email)
        self._submit_password_if_requested(page, result.password)
        self._complete_email_otp(
            page,
            mail_provider,
            email=result.email,
            issued_after=otp_issued_after,
        )
        self._complete_about_you(page, first_name=first_name, last_name=last_name)
        session_info = self._wait_for_chatgpt_session(page)
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

    def _open_email_registration(self, page) -> None:
        page.goto(
            "https://chatgpt.com/",
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout_ms,
        )
        self._raise_for_challenge(page, "open-chatgpt")
        if _visible(page, EMAIL_INPUT_SELECTORS) is not None:
            return
        if not self._wait_for_page_state(
            page,
            lambda: _visible(page, SIGNUP_SELECTORS) is not None,
            stage="wait-signup-button",
            timeout_s=20,
        ):
            self._screenshot(page, "signup-button-missing.png")
            raise BrowserEmailRegistrationError(f"signup button not found url={page.url}")
        time.sleep(3)
        self._remove_google_one_tap(page)
        signup_opened = False
        for attempt in range(1, 4):
            if not _click_first(page, SIGNUP_SELECTORS, timeout_ms=5_000):
                continue
            self._emit("browser.signup.clicked", {"attempt": attempt})
            signup_opened = self._wait_for_page_state(
                page,
                lambda: "auth.openai.com" in page.url
                or _visible(page, EMAIL_INPUT_SELECTORS) is not None
                or _visible(page, EMAIL_ENTRY_SELECTORS) is not None,
                stage=f"wait-signup-result-{attempt}",
                timeout_s=6,
            )
            if signup_opened:
                break
            self._remove_google_one_tap(page)
            time.sleep(1)
        if not signup_opened:
            self._screenshot(page, "signup-click-no-effect.png")
            raise BrowserEmailRegistrationError(f"signup click had no effect url={page.url}")
        if _visible(page, EMAIL_INPUT_SELECTORS) is None:
            if not _click_first(page, EMAIL_ENTRY_SELECTORS, timeout_ms=5_000):
                self._screenshot(page, "email-entry-missing.png")
                raise BrowserEmailRegistrationError(f"email entry not found url={page.url}")
        if not self._wait_for_page_state(
            page,
            lambda: _visible(page, EMAIL_INPUT_SELECTORS) is not None,
            stage="wait-email-form",
            timeout_s=30,
        ):
            self._screenshot(page, "email-form-missing.png")
            raise BrowserEmailRegistrationError(f"email input not found url={page.url}")
        self._emit("browser.email_form.ready", {"url": page.url})

    def _submit_email(self, page, email: str) -> None:
        last_error = ""
        for attempt in range(1, 5):
            field = _visible(page, EMAIL_INPUT_SELECTORS)
            if field is None:
                last_error = "email input disappeared"
                time.sleep(0.5)
                continue
            try:
                field.click(timeout=5_000)
                time.sleep(0.3)
                current = _visible(page, EMAIL_INPUT_SELECTORS) or field
                current.fill(email)
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
        if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000):
            raise BrowserEmailRegistrationError("email continue button not found")
        self._emit("browser.email.submitted", {"email": email})

    def _submit_password_if_requested(self, page, password: str) -> None:
        reached_next_stage = self._wait_for_page_state(
            page,
            lambda: _visible(page, PASSWORD_INPUT_SELECTORS) is not None
            or _otp_inputs(page)
            or _about_you_visible(page)
            or _has_authenticated_session(page),
            stage="wait-password-or-otp",
            timeout_s=35,
        )
        field = _visible(page, PASSWORD_INPUT_SELECTORS)
        if field is None:
            if reached_next_stage and (
                _otp_inputs(page) or _about_you_visible(page) or _has_authenticated_session(page)
            ):
                self._emit("browser.password.skipped", {"url": page.url})
                return
            self._screenshot(page, "password-or-otp-missing.png")
            raise BrowserEmailRegistrationError(
                f"password/OTP stage not reached url={page.url}"
            )
        field.click(timeout=5_000)
        field.fill(password)
        time.sleep(random.uniform(0.5, 1.2))
        if not _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000):
            raise BrowserEmailRegistrationError("password continue button not found")
        self._emit("browser.password.submitted", {})

    def _complete_email_otp(
        self,
        page,
        mail_provider,
        *,
        email: str,
        issued_after: float,
    ) -> None:
        reached_next_stage = self._wait_for_page_state(
            page,
            lambda: bool(_otp_inputs(page))
            or _about_you_visible(page)
            or _has_authenticated_session(page),
            stage="wait-email-otp",
            timeout_s=45,
        )
        inputs = _otp_inputs(page)
        if not inputs:
            if reached_next_stage and (
                _about_you_visible(page) or _has_authenticated_session(page)
            ):
                self._emit("browser.otp.skipped", {"url": page.url})
                return
            self._screenshot(page, "otp-form-missing.png")
            raise BrowserEmailRegistrationError(f"email OTP input not found url={page.url}")
        self._emit(
            "browser.otp.wait.started",
            {"email": email, "timeout_s": self.config.otp_timeout_s},
        )
        code = str(
            mail_provider.wait_for_otp(
                email,
                timeout=max(1, int(self.config.otp_timeout_s or 180)),
                issued_after=issued_after,
            )
            or ""
        ).strip()
        if not code:
            raise BrowserEmailRegistrationError("mail provider returned empty OTP")
        if len(inputs) == 1 or str(inputs[0].get_attribute("maxlength") or "") != "1":
            inputs[0].click()
            inputs[0].fill(code)
        else:
            if len(inputs) < len(code):
                raise BrowserEmailRegistrationError("email OTP inputs are incomplete")
            for index, char in enumerate(code):
                inputs[index].click()
                inputs[index].fill(char)
        _click_first(page, CONTINUE_SELECTORS, timeout_ms=5_000)
        time.sleep(2)
        error = _visible(page, OTP_ERROR_SELECTORS)
        if error is not None:
            self._screenshot(page, "otp-rejected.png")
            raise BrowserEmailRegistrationError("OpenAI rejected email OTP")
        self._emit("browser.otp.submitted", {"email": email})

    def _complete_about_you(self, page, *, first_name: str, last_name: str) -> None:
        name: dict[str, Any] | None = None
        birthday: dict[str, Any] | None = None
        legacy_age = False
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if _has_authenticated_session(page):
                self._emit("browser.about_you.skipped", {"url": page.url})
                return
            inputs = _visible_input_metadata(page)
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
            if name is not None and birthday is not None:
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
        if name is None or birthday is None:
            self._screenshot(page, "about-you-form-missing.png")
            self._emit("browser.about_you.not_found", {"url": page.url}, "WARN")
            return
        elements = page.query_selector_all("input")
        name_field = elements[name["index"]]
        birthday_field = elements[birthday["index"]]
        try:
            name_field.focus()
            page.keyboard.type(f"{first_name} {last_name}", delay=random.randint(30, 80))
            birthday_field.focus()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            age = str(random.randint(26, 40))
            year = time.gmtime().tm_year - int(age)
            if legacy_age:
                page.keyboard.type(age, delay=random.randint(40, 100))
            elif birthday["type"] == "date":
                try:
                    birthday_field.fill(f"{year}-01-15")
                except Exception:
                    page.keyboard.type(f"{year}-01-15", delay=random.randint(30, 70))
            else:
                page.keyboard.type(f"01/15/{year}", delay=random.randint(30, 70))
            time.sleep(random.uniform(0.4, 0.9))
            if not _click_first(page, FINISH_SELECTORS, timeout_ms=5_000):
                self._screenshot(page, "about-you-submit-missing.png")
                self._emit("browser.about_you.submit_missing", {"url": page.url}, "WARN")
                return
            self._emit("browser.about_you.submitted", {"legacy_age": legacy_age})
        except Exception as exc:
            self._screenshot(page, "about-you-fill-failed.png")
            self._emit(
                "browser.about_you.fill_failed",
                {"url": page.url, "error": f"{type(exc).__name__}: {exc}"},
                "WARN",
            )

    def _wait_for_chatgpt_session(self, page) -> dict[str, Any]:
        deadline = time.monotonic() + max(1, int(self.config.completion_timeout_s or 120))
        next_continue_at = time.monotonic() + 5
        while time.monotonic() < deadline:
            payload = _chatgpt_session_payload(page)
            if payload.get("accessToken"):
                self._emit("browser.session.succeeded", {"url": page.url})
                return payload
            if "auth.openai.com" in page.url and time.monotonic() >= next_continue_at:
                _click_first(page, CONTINUE_SELECTORS, timeout_ms=2_000)
                next_continue_at = time.monotonic() + 10
            self._raise_for_challenge(page, "wait-chatgpt-session")
            time.sleep(1)
        self._screenshot(page, "chatgpt-session-timeout.png")
        raise BrowserEmailRegistrationError(f"ChatGPT session timeout url={page.url}")

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
)
PASSWORD_INPUT_SELECTORS = (
    'input[type="password"]',
    'input[name="password"]',
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


def _click_first(page, selectors: tuple[str, ...], *, timeout_ms: int) -> bool:
    element = _visible(page, selectors)
    if element is None:
        return False
    try:
        element.scroll_into_view_if_needed(timeout=2_000)
    except Exception:
        pass
    try:
        element.click(timeout=timeout_ms)
    except Exception:
        try:
            element.evaluate("node => node.click()")
        except Exception:
            return False
    return True


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
