"""Phone-entry ChatGPT registration lane.

This lane keeps the same output shape as browser_register.py so pipeline,
payment, inventory, and DB code can stay unchanged. The phone number is a
temporary lease; the final account identity is still the resolved/bound email.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import shutil
import string
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from browser_register import _camoufox_headless, _gen_name, _parse_proxy, _raise_if_blocking_challenge
from phone_provider import PhoneLease, PhoneProvider

logger = logging.getLogger(__name__)


_TRACE_REDACT_HEADER_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "openai-sentinel-token",
    "x-openai-sentinel-token",
    "cf-clearance",
}
_TRACE_REDACT_BODY_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "code",
    "cookie",
    "csrf_token",
    "id_token",
    "openai-sentinel-token",
    "otp",
    "password",
    "refresh_token",
    "session_token",
    "token",
}
_TRACE_ALLOWED_HOSTS = {"auth.openai.com", "chatgpt.com", "platform.openai.com"}


def _env_flag(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _phone_trace_path() -> Path:
    raw = (os.getenv("PHONE_TRACE_PATH", "") or "").strip()
    if raw:
        return Path(raw).expanduser()
    root = Path(__file__).resolve().parents[1]
    return root / "output" / f"phone_trace_{time.strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.jsonl"


def _phone_trace_url_allowed(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.netloc or "").lower().split("@")[-1].split(":")[0]
    path = parsed.path or ""
    if host == "auth.openai.com":
        return path.startswith("/api/accounts/") or path.startswith("/oauth/")
    if host == "chatgpt.com":
        return path == "/api/auth/session" or path.startswith("/api/auth/")
    if host == "platform.openai.com":
        return True
    return host in _TRACE_ALLOWED_HOSTS and "/api/" in path


def _redact_trace_scalar(key: str, value: Any) -> Any:
    key_lc = (key or "").lower()
    if key_lc in _TRACE_REDACT_BODY_KEYS or any(token in key_lc for token in ("secret", "token", "cookie")):
        return "<redacted>"
    if not isinstance(value, str):
        return value
    text = value
    if re.fullmatch(r"\d{4,8}", text) and any(token in key_lc for token in ("code", "otp")):
        return "<redacted-code>"
    if "@" in text and re.search(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text):
        domain = text.split("@", 1)[1]
        return f"<email>@{domain}"
    digits = re.sub(r"\D+", "", text)
    if len(digits) >= 9 and any(token in key_lc for token in ("phone", "username", "identifier")):
        prefix = f"+{digits[:3]}" if text.strip().startswith("+") else digits[:3]
        return f"<phone:{prefix}:digits={len(digits)}>"
    return text


def _redact_trace_obj(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {str(k): _redact_trace_obj(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_trace_obj(v, key) for v in value]
    return _redact_trace_scalar(key, value)


def _redact_trace_headers(headers: dict | None) -> dict:
    out = {}
    for key, value in (headers or {}).items():
        key_s = str(key)
        if key_s.lower() in _TRACE_REDACT_HEADER_KEYS:
            out[key_s] = "<redacted>"
        else:
            out[key_s] = value
    return out


def _parse_trace_body(raw: str | None) -> Any:
    if raw is None:
        return ""
    text = str(raw)
    if len(text) > 30000:
        text = text[:30000] + "...<truncated>"
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        return _redact_trace_obj(json.loads(stripped))
    except Exception:
        return _redact_trace_scalar("", stripped)


def _write_phone_trace(path: Path, event: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        event["ts"] = time.time()
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception as e:
        logger.debug("[phone-reg] PHONE_TRACE_DUMP 写入失败: %s", e)


def _install_phone_trace(page) -> None:
    if not _env_flag("PHONE_TRACE_DUMP"):
        return
    path = _phone_trace_path()
    logger.info("[phone-reg] PHONE_TRACE_DUMP enabled: %s", path)

    def on_request(req) -> None:
        try:
            if not _phone_trace_url_allowed(req.url):
                return
            _write_phone_trace(path, {
                "type": "request",
                "method": req.method,
                "url": req.url,
                "headers": _redact_trace_headers(req.headers),
                "post_data": _parse_trace_body(req.post_data),
            })
        except Exception as e:
            logger.debug("[phone-reg] PHONE_TRACE_DUMP request 失败: %s", e)

    def on_response(resp) -> None:
        try:
            if not _phone_trace_url_allowed(resp.url):
                return
            headers = dict(resp.headers or {})
            content_type = str(headers.get("content-type") or headers.get("Content-Type") or "").lower()
            body: Any = ""
            if any(token in content_type for token in ("json", "text", "javascript")):
                try:
                    body = _parse_trace_body(resp.text())
                except Exception:
                    body = "<unavailable>"
            _write_phone_trace(path, {
                "type": "response",
                "status": resp.status,
                "url": resp.url,
                "headers": _redact_trace_headers(headers),
                "body": body,
            })
        except Exception as e:
            logger.debug("[phone-reg] PHONE_TRACE_DUMP response 失败: %s", e)

    page.on("request", on_request)
    page.on("response", on_response)


class PageState(str, Enum):
    CHATGPT_HOME = "chatgpt_home"
    AUTH_METHOD_PICKER = "auth_method_picker"
    PHONE_NUMBER_FORM = "phone_number_form"
    PASSWORD_FORM = "password_form"
    PHONE_OTP_FORM = "phone_otp_form"
    REG_EMAIL_FORM = "reg_email_form"
    CONTACT_VERIFICATION = "contact_verification"
    ABOUT_YOU_FORM = "about_you_form"
    CHATGPT_LOGGED_IN = "chatgpt_logged_in"
    PLATFORM_LOGIN = "platform_login"
    PLATFORM_METHOD_PICKER = "platform_method_picker"
    PLATFORM_PHONE_FORM = "platform_phone_form"
    PLATFORM_EMAIL_FORM = "platform_email_form"
    PLATFORM_EMAIL_OTP_FORM = "platform_email_otp_form"
    PLATFORM_BOUND = "platform_bound"
    CLOUDFLARE_BLOCKED = "cloudflare_blocked"
    UNKNOWN = "unknown"


@dataclass
class PageSnapshot:
    state: PageState
    url: str
    text: str = ""


@dataclass(frozen=True)
class FlowTiming:
    observe_poll_s: float = 2.0
    short_action_s: float = 1.5
    signup_initial_settle_s: float = 3.0
    signup_retry_after_s: float = 6.0
    signup_final_observe_s: float = 20.0
    phone_submit_observe_s: float = 20.0
    password_submit_observe_s: float = 15.0
    otp_submit_observe_s: float = 20.0
    about_submit_observe_s: float = 15.0
    platform_email_submit_observe_s: float = 15.0


@dataclass
class PhoneFlowContext:
    provider: PhoneProvider
    mail_provider: Any
    result: dict
    password: str
    first_name: str
    last_name: str
    timing: FlowTiming = FlowTiming()
    lease: PhoneLease | None = None
    bound_email: str = ""
    phone_code: str = ""
    platform_email_issued_at: float = 0.0
    platform_email_code: str = ""
    platform_email_submitted: bool = False
    platform_phone_submitted: bool = False
    phone_cancelled: bool = False
    email_reverted: bool = False
    last_action: str = ""
    observe_until: float = 0.0
    action_attempts: dict[str, int] | None = None


def _gen_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length)) + "Aa1"


def _b64url_json(segment: str) -> dict:
    try:
        padded = segment + "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()).decode("utf-8"))
    except Exception:
        return {}


def _email_from_token(token: str) -> str:
    if not token or token.count(".") < 2:
        return ""
    payload = _b64url_json(token.split(".")[1])
    profile = payload.get("https://api.openai.com/profile") if isinstance(payload, dict) else {}
    if isinstance(profile, dict) and profile.get("email"):
        return str(profile.get("email") or "").strip()
    if isinstance(payload, dict):
        return str(payload.get("email") or "").strip()
    return ""


def _resolve_email(session_info: dict, access_token: str, id_token: str, fallback: str = "") -> str:
    user = session_info.get("user") if isinstance(session_info, dict) else {}
    if isinstance(user, dict) and user.get("email"):
        return str(user.get("email") or "").strip()
    return _email_from_token(access_token) or _email_from_token(id_token) or fallback.strip()


def _visible_first(page, selectors: list[str]):
    for sel in selectors:
        try:
            els = page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
            try:
                if el.is_visible():
                    return el
            except Exception:
                continue
    return None


def _click_first(page, selectors: list[str], *, log_label: str = "") -> bool:
    for sel in selectors:
        try:
            els = page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_visible():
                    continue
                try:
                    text = (el.inner_text() or "").strip()
                except Exception:
                    text = ""
                try:
                    el.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    el.click(timeout=5000)
                except Exception:
                    el.evaluate("node => node.click()")
                if log_label:
                    logger.info("[phone-reg] 点击 %s (%s): %s", log_label, sel, text[:60])
                return True
            except Exception:
                continue
    return False


def _click_signup(page) -> None:
    clicked_signup = False
    for sel in [
        'a[data-testid="signup-button"]',
        'button[data-testid="signup-button"]',
        'button:has-text("Sign up for free")',
        'a:has-text("Sign up for free")',
        'button:has-text("Sign up")',
        'a:has-text("Sign up")',
    ]:
        try:
            btns = page.query_selector_all(sel)
        except Exception:
            continue
        for btn in btns:
            try:
                if not btn.is_visible():
                    continue
                text = btn.inner_text().lower()
                if "sign up" not in text:
                    continue
                try:
                    btn.click(timeout=5000)
                except Exception:
                    btn.evaluate("el => el.click()")
                clicked_signup = True
                logger.info("[phone-reg] 点击 Sign up (%s): %s", sel, text[:40])
                break
            except Exception as e_click:
                if "attached to the DOM" in str(e_click) or "detached" in str(e_click).lower():
                    continue
                logger.warning("[phone-reg] click 异常: %s", e_click)
        if clicked_signup:
            return
    page.screenshot(path="/tmp/phone_reg_no_signup.png")
    raise RuntimeError(f"未找到 Sign up 按钮, URL={page.url[:120]}")


def _handle_chatgpt_home_signup(page, ctx: PhoneFlowContext, snapshot: PageSnapshot) -> None:
    if _observing_action(ctx, "click_signup"):
        _wait_observing(ctx, "click_signup", snapshot.state)
        return
    attempts = _action_attempts(ctx, "click_signup")
    if attempts >= 2:
        _fail_state(page, snapshot, "Sign up 点击后页面未进入注册入口", "phone_reg_signup_stuck.png")
    if attempts == 0:
        try:
            page.wait_for_selector(
                'button[data-testid="signup-button"], a[data-testid="signup-button"]',
                state="visible",
                timeout=20000,
            )
        except Exception:
            _raise_if_blocking_challenge(
                page,
                stage="waiting for signup button",
                screenshot_path="/tmp/phone_reg_cloudflare_challenge.png",
            )
        time.sleep(ctx.timing.signup_initial_settle_s)
    else:
        logger.info("[phone-reg] Sign up 点击未生效，按邮箱注册节奏重试")
    _click_signup(page)
    observe_s = ctx.timing.signup_retry_after_s if attempts == 0 else ctx.timing.signup_final_observe_s
    _mark_action(ctx, "click_signup", observe_s)


def _dismiss_google_one_tap(page) -> None:
    try:
        page.evaluate(
            "() => document.querySelectorAll('iframe[src*=\"accounts.google.com/gsi\"]').forEach(el => el.remove())"
        )
    except Exception:
        pass
    _click_first(
        page,
        [
            'div#credential_picker_container button[aria-label*="Close"]',
            '[aria-label="Close"][role="button"]',
        ],
        log_label="关闭 Google One-Tap",
    )


def _click_email_entry(page) -> bool:
    _dismiss_google_one_tap(page)
    for sel in [
        'button:has-text("Continue with email")',
        'button:has-text("Sign up with email")',
        'a:has-text("Continue with email")',
        'a:has-text("Sign up with email")',
        'button:has-text("Email")',
        'button[data-testid*="email"]',
    ]:
        try:
            btns = page.query_selector_all(sel)
        except Exception:
            continue
        for b in btns:
            try:
                if not b.is_visible():
                    continue
                label = (b.inner_text() or "").lower().strip()
                if any(skip in label for skip in ("google", "apple", "phone")):
                    continue
                try:
                    b.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    b.click(timeout=5000)
                except Exception:
                    b.evaluate("el => el.click()")
                logger.info("[phone-reg] 点击 modal email 入口 (%s): %s", sel, label[:40])
                return True
            except Exception:
                continue
    return False


def _click_phone_entry(page) -> bool:
    _dismiss_google_one_tap(page)
    for sel in [
        'button:has-text("Continue with phone")',
        'button:has-text("Continue with phone number")',
        'button:has-text("Log in with phone")',
        'button:has-text("Login with phone")',
        'button:has-text("Sign in with phone")',
        'button:has-text("Sign up with phone")',
        'button:has-text("Use phone")',
        'button:has-text("Phone")',
        'button:has-text("手机号")',
        'a:has-text("Continue with phone")',
        'a:has-text("Log in with phone")',
        'a:has-text("Login with phone")',
        'a:has-text("Sign in with phone")',
        'a:has-text("Sign up with phone")',
        'a:has-text("Use phone")',
        'a:has-text("手机号")',
        '[data-testid*="phone" i]',
    ]:
        try:
            btns = page.query_selector_all(sel)
        except Exception:
            continue
        for b in btns:
            try:
                if not b.is_visible():
                    continue
                label = (b.inner_text() or b.get_attribute("aria-label") or "").lower().strip()
                if any(skip in label for skip in ("google", "apple", "email")):
                    continue
                try:
                    b.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    b.click(timeout=5000)
                except Exception:
                    b.evaluate("el => el.click()")
                logger.info("[phone-reg] 点击 modal phone 入口 (%s): %s", sel, label[:40])
                return True
            except Exception:
                continue
    return False


def _has_phone_entry_button(page) -> bool:
    for sel in [
        'button:has-text("Continue with phone")',
        'button:has-text("Continue with phone number")',
        'button:has-text("Log in with phone")',
        'button:has-text("Login with phone")',
        'button:has-text("Sign in with phone")',
        'button:has-text("Sign up with phone")',
        'button:has-text("Use phone")',
        'button:has-text("Phone")',
        'button:has-text("手机号")',
        'a:has-text("Continue with phone")',
        'a:has-text("Log in with phone")',
        'a:has-text("Login with phone")',
        'a:has-text("Sign in with phone")',
        'a:has-text("Sign up with phone")',
        'a:has-text("Use phone")',
        'a:has-text("手机号")',
        '[data-testid*="phone" i]',
    ]:
        try:
            els = page.query_selector_all(sel)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_visible():
                    continue
                label = (el.inner_text() or el.get_attribute("aria-label") or "").lower().strip()
                if any(skip in label for skip in ("google", "apple", "email")):
                    continue
                return True
            except Exception:
                continue
    return False


def _wait_for_any(page, selectors: list[str], *, timeout_s: int, label: str):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        el = _visible_first(page, selectors)
        if el:
            return el
        time.sleep(0.5)
    page.screenshot(path=f"/tmp/phone_reg_wait_{label}.png")
    raise RuntimeError(f"等待 {label} 超时, URL={page.url[:120]}")


def _email_identifier_selectors() -> list[str]:
    return [
        'input[type="email"]',
        'input[name="email"]',
        'input[name="username"]',
        'input[autocomplete="email"]',
        'input[autocomplete="username"]',
        'input[id*="email" i]',
        'input[placeholder*="email" i]',
        'input[aria-label*="email" i]',
    ]


def _phone_input_selectors() -> list[str]:
    return [
        'input[type="tel"]',
        'input[name*="phone" i]',
        'input[id*="phone" i]',
        'input[autocomplete="tel"]',
        'input[inputmode="tel"]',
        'input[placeholder*="phone" i]',
        'input[aria-label*="phone" i]',
    ]


def _input_summary(el) -> str:
    bits = []
    for attr in ("type", "name", "id", "autocomplete", "placeholder"):
        try:
            value = el.get_attribute(attr) or ""
        except Exception:
            value = ""
        if value:
            bits.append(f"{attr}={value[:40]}")
    return " ".join(bits) or "<input>"


def _has_phone_entry_or_input(page) -> bool:
    if _visible_first(page, _phone_input_selectors()):
        return True
    return _has_phone_entry_button(page)


def _wait_for_signup_phone_input(page):
    try:
        page.wait_for_selector(
            'button[data-testid="signup-button"], a[data-testid="signup-button"]',
            state="visible",
            timeout=20000,
        )
    except Exception:
        _raise_if_blocking_challenge(
            page,
            stage="waiting for signup button",
            screenshot_path="/tmp/phone_reg_cloudflare_challenge.png",
        )
        pass
    time.sleep(3)
    _click_signup(page)

    pre_url = page.url
    for i in range(20):
        time.sleep(1)
        if "auth.openai.com" in page.url or _has_phone_entry_or_input(page):
            break
        if i == 5 and page.url == pre_url:
            logger.info("[phone-reg] Sign up 点击未生效，重试")
            try:
                btn = page.query_selector('button[data-testid="signup-button"], a[data-testid="signup-button"]')
                if btn:
                    btn.click(timeout=3000)
            except Exception:
                try:
                    btn.evaluate("el => el.click()")
                except Exception:
                    pass
    logger.info("[phone-reg] 当前 URL: %s", page.url[:120])
    page.screenshot(path="/tmp/phone_reg_before_phone_entry.png")
    _raise_if_blocking_challenge(
        page,
        stage="before phone form",
        screenshot_path="/tmp/phone_reg_cloudflare_challenge.png",
    )

    _dismiss_google_one_tap(page)
    if not _visible_first(page, _phone_input_selectors()):
        if not _click_phone_entry(page):
            page.screenshot(path="/tmp/phone_reg_no_phone_entry.png")
            raise RuntimeError(f"未找到手机号注册入口, URL={page.url[:120]}")

    el = _wait_for_any(page, _phone_input_selectors(), timeout_s=30, label="phone_input")
    logger.info("[phone-reg] 已到达手机号输入框: %s", _input_summary(el))
    return el


def _national_phone_from_lease(lease: PhoneLease) -> str:
    if lease.phone_national:
        return lease.phone_national
    digits = "".join(ch for ch in str(lease.phone_e164 or "") if ch.isdigit())
    dial = "".join(ch for ch in str(lease.country_phone_code or "") if ch.isdigit())
    if dial and digits.startswith(dial):
        digits = digits[len(dial):]
    if digits.startswith("0"):
        digits = digits[1:]
    return digits


def _select_native_country(page, dial_code: str) -> bool:
    if not dial_code:
        return False
    wanted = f"+{dial_code}"
    wanted_paren = f"+({dial_code})"
    try:
        selects = page.query_selector_all("select")
    except Exception:
        return False
    for sel in selects:
        try:
            if not sel.is_visible():
                continue
            options = sel.query_selector_all("option")
        except Exception:
            continue
        for opt in options:
            try:
                text = " ".join([
                    opt.inner_text() or "",
                    opt.get_attribute("value") or "",
                    opt.get_attribute("label") or "",
                ])
                if not _country_text_matches_dial(text, dial_code):
                    continue
                value = opt.get_attribute("value") or opt.inner_text()
                sel.select_option(value=value)
                logger.info("[phone-reg] 选择手机号国家 select: %s/%s -> %s", wanted, wanted_paren, text[:80])
                return True
            except Exception:
                continue
    return False


def _country_text_matches_dial(text: str, dial_code: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or ""))
    if not compact or not dial_code:
        return False
    variants = [
        f"+{dial_code}",
        f"+({dial_code})",
        f"(+{dial_code})",
        f"({dial_code})",
    ]
    if any(v in compact for v in variants):
        return True
    return False


_COUNTRY_BY_DIAL = {
    "1": ("US", "CA"),
    "7": ("RU", "KZ"),
    "20": ("EG",),
    "27": ("ZA",),
    "30": ("GR",),
    "31": ("NL",),
    "32": ("BE",),
    "33": ("FR",),
    "34": ("ES",),
    "36": ("HU",),
    "39": ("IT",),
    "40": ("RO",),
    "41": ("CH",),
    "43": ("AT",),
    "44": ("GB",),
    "45": ("DK",),
    "46": ("SE",),
    "47": ("NO",),
    "48": ("PL",),
    "49": ("DE",),
    "51": ("PE",),
    "52": ("MX",),
    "54": ("AR",),
    "55": ("BR",),
    "56": ("CL",),
    "57": ("CO",),
    "58": ("VE",),
    "60": ("MY",),
    "61": ("AU",),
    "62": ("ID",),
    "63": ("PH",),
    "64": ("NZ",),
    "65": ("SG",),
    "66": ("TH",),
    "81": ("JP",),
    "82": ("KR",),
    "84": ("VN",),
    "86": ("CN",),
    "90": ("TR",),
    "91": ("IN",),
    "92": ("PK",),
    "93": ("AF",),
    "94": ("LK",),
    "95": ("MM",),
    "98": ("IR",),
    "212": ("MA",),
    "213": ("DZ",),
    "216": ("TN",),
    "218": ("LY",),
    "351": ("PT",),
    "352": ("LU",),
    "353": ("IE",),
    "354": ("IS",),
    "355": ("AL",),
    "356": ("MT",),
    "357": ("CY",),
    "358": ("FI",),
    "359": ("BG",),
    "370": ("LT",),
    "371": ("LV",),
    "372": ("EE",),
    "373": ("MD",),
    "374": ("AM",),
    "375": ("BY",),
    "376": ("AD",),
    "377": ("MC",),
    "380": ("UA",),
    "381": ("RS",),
    "385": ("HR",),
    "386": ("SI",),
    "387": ("BA",),
    "389": ("MK",),
    "420": ("CZ",),
    "421": ("SK",),
    "501": ("BZ",),
    "502": ("GT",),
    "503": ("SV",),
    "504": ("HN",),
    "505": ("NI",),
    "506": ("CR",),
    "507": ("PA",),
    "593": ("EC",),
    "595": ("PY",),
    "598": ("UY",),
    "852": ("HK",),
    "853": ("MO",),
    "855": ("KH",),
    "856": ("LA",),
    "886": ("TW",),
    "961": ("LB",),
    "962": ("JO",),
    "963": ("SY",),
    "964": ("IQ",),
    "965": ("KW",),
    "966": ("SA",),
    "967": ("YE",),
    "968": ("OM",),
    "971": ("AE",),
    "972": ("IL",),
    "974": ("QA",),
    "976": ("MN",),
    "977": ("NP",),
}


_COUNTRY_NAMES_BY_ISO = {
    "AR": ("Argentina",),
    "AU": ("Australia",),
    "BR": ("Brazil",),
    "CA": ("Canada",),
    "CL": ("Chile", "智利"),
    "CN": ("China",),
    "CO": ("Colombia",),
    "DE": ("Germany",),
    "ES": ("Spain",),
    "FR": ("France",),
    "GB": ("United Kingdom", "Great Britain"),
    "ID": ("Indonesia",),
    "IN": ("India",),
    "IT": ("Italy",),
    "JP": ("Japan",),
    "KR": ("South Korea", "Korea"),
    "MX": ("Mexico",),
    "MY": ("Malaysia",),
    "NL": ("Netherlands",),
    "PE": ("Peru",),
    "PH": ("Philippines",),
    "SG": ("Singapore",),
    "TH": ("Thailand",),
    "TR": ("Turkey",),
    "US": ("United States", "United States of America"),
    "VN": ("Vietnam", "Viet Nam"),
}


def _country_iso_candidates(lease: PhoneLease, dial_code: str) -> list[str]:
    candidates: list[str] = []
    raw = lease.raw if isinstance(lease.raw, dict) else {}
    for key in ("countryIso", "countryISO", "country_iso", "iso", "iso2", "country"):
        value = str(raw.get(key) or "").strip().upper()
        if re.fullmatch(r"[A-Z]{2}", value):
            candidates.append(value)
    candidates.extend(_COUNTRY_BY_DIAL.get(dial_code, ()))
    out: list[str] = []
    for item in candidates:
        if item and item not in out:
            out.append(item)
    return out


def _country_name_candidates(iso_codes: list[str]) -> list[str]:
    out: list[str] = []
    for iso in iso_codes:
        for name in _COUNTRY_NAMES_BY_ISO.get(iso, ()):
            if name and name not in out:
                out.append(name)
    return out


def _phone_country_selected(page, dial_code: str) -> bool:
    if not dial_code:
        return True
    try:
        return bool(page.evaluate(
            """(dialCode) => {
                const variants = [`+${dialCode}`, `+(${dialCode})`, `(+${dialCode})`, `(${dialCode})`];
                const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const cs = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
                };
                const phoneInput = document.querySelector(
                    'input[type="tel"],input[name*="phone" i],input[id*="phone" i],input[autocomplete="tel"],input[inputmode="tel"]'
                );
                const roots = [];
                if (phoneInput) {
                    let cur = phoneInput;
                    for (let i = 0; cur && i < 6; i++, cur = cur.parentElement) roots.push(cur);
                }
                roots.push(document.body);
                for (const root of roots) {
                    if (!root) continue;
                    const nodes = Array.from(root.querySelectorAll(
                        '[role="button"],button,[role="combobox"],[aria-haspopup="dialog"],[aria-haspopup="listbox"],select'
                    ));
                    for (const node of nodes) {
                        if (!visible(node)) continue;
                    const nodeText = node.tagName === 'SELECT'
                        ? Array.from(node.selectedOptions || []).map(opt => `${opt.innerText || ''} ${opt.value || ''}`).join(' ')
                        : (node.innerText || node.textContent || '');
                    const text = [
                            nodeText,
                            node.getAttribute('aria-label') || '',
                            node.getAttribute('value') || ''
                        ].join(' ').replace(/\\s+/g, '');
                        if (variants.some(v => text.includes(v))) return true;
                    }
                }
                return false;
            }""",
            dial_code,
        ))
    except Exception:
        return False


def _wait_phone_country_selected(page, dial_code: str, *, timeout_s: float = 3.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _phone_country_selected(page, dial_code):
            return True
        time.sleep(0.25)
    return _phone_country_selected(page, dial_code)


def _select_popup_country(page, dial_code: str, iso_codes: list[str] | None = None) -> bool:
    if not dial_code:
        return False
    wanted = f"+{dial_code}"
    search_terms = [wanted, f"+({dial_code})", f"({dial_code})"]
    iso_codes = [str(code or "").strip().upper() for code in (iso_codes or []) if str(code or "").strip()]
    country_names = _country_name_candidates(iso_codes)

    def _click_exact_iso_option() -> bool:
        for iso in iso_codes:
            for sel in [
                f'[role="option"][data-option-id="{iso}"]',
                f'[role="option"][data-option-id="{iso.lower()}"]',
                f'[data-option-id="{iso}"][role="option"]',
                f'[data-option-id="{iso.lower()}"][role="option"]',
                f'[data-option-id="{iso}"]',
                f'[data-option-id="{iso.lower()}"]',
            ]:
                try:
                    opt = page.query_selector(sel)
                    if not opt:
                        continue
                    text = (opt.inner_text() or "").strip()
                    try:
                        opt.scroll_into_view_if_needed(timeout=3000)
                    except Exception:
                        pass
                    opt.click(timeout=4000)
                    logger.info("[phone-reg] 选择手机号国家 exact iso=%s (%s): %s", iso, sel, text[:100])
                    if _wait_phone_country_selected(page, dial_code):
                        return True
                    logger.warning("[phone-reg] exact iso=%s 点击后未确认到 +%s: %s", iso, dial_code, text[:100])
                except Exception:
                    continue
        return False

    def _click_visible_country_option() -> bool:
        try:
            clicked = page.evaluate(
                """({ dialCode, terms, isoCodes, countryNames }) => {
                    const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const cs = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
                    };
                    const matchesIso = (value) => {
                        if (!isoCodes.length) return false;
                        const normalized = String(value || '').toUpperCase();
                        if (!normalized) return false;
                        const parts = normalized.split(/[^A-Z0-9]+/).filter(Boolean);
                        return isoCodes.some((code) => normalized === code || parts.includes(code) || normalized.endsWith(`:${code}`) || normalized.endsWith(`-${code}`) || normalized.endsWith(`_${code}`));
                    };
                    const matchesCountryName = (text) => {
                        if (!countryNames.length) return false;
                        const normalized = String(text || '').toLowerCase();
                        return countryNames.some((name) => normalized.includes(String(name || '').toLowerCase()));
                    };
                    const matchesDial = (text) => {
                        const compact = String(text || '').replace(/\\s+/g, '');
                        if (!compact) return false;
                        if (terms.some(term => compact.includes(term))) return true;
                        return false;
                    };
                    const selector = [
                        '[data-option-id]',
                        '[role="option"]',
                        '[role="menuitem"]',
                        '[data-radix-collection-item]',
                        '[cmdk-item]'
                    ].join(',');
                    const nodes = Array.from(document.querySelectorAll(selector));
                    const matches = [];
                    for (const el of nodes) {
                        if (!visible(el)) continue;
                        const text = (el.innerText || el.textContent || '').trim();
                        const optionId = el.getAttribute('data-option-id') || '';
                        const blob = `${optionId} ${el.getAttribute('aria-label') || ''} ${text}`;
                        const isoMatch = matchesIso(optionId);
                        const nameMatch = matchesCountryName(blob);
                        const dialMatch = matchesDial(blob);
                        let matchScore = 1000000;
                        if (isoCodes.length) {
                            if (isoMatch) matchScore = 0;
                            else if (nameMatch && dialMatch) matchScore = 10;
                            else if (nameMatch) matchScore = 20;
                            else continue;
                        } else if (dialMatch) {
                            matchScore = 50;
                        } else {
                            continue;
                        }
                        const clickable = el.closest(
                            '[data-option-id],[role="option"],[role="menuitem"],[data-radix-collection-item],[cmdk-item]'
                        ) || el;
                        if (!visible(clickable)) continue;
                        const role = clickable.getAttribute('role') || '';
                        const specific = clickable.hasAttribute('data-option-id')
                            || role === 'option' || role === 'menuitem'
                            || clickable.hasAttribute('data-radix-collection-item')
                            || clickable.hasAttribute('cmdk-item');
                        const r = clickable.getBoundingClientRect();
                        matches.push({
                            el: clickable,
                            text: (clickable.innerText || clickable.textContent || text).trim(),
                            score: matchScore
                                + (clickable.hasAttribute('data-option-id') ? -1000 : 0)
                                + (specific ? 0 : 1000000)
                                + (r.width * r.height)
                        });
                    }
                    matches.sort((a, b) => a.score - b.score);
                    for (const match of matches) {
                        const clickable = match.el;
                        clickable.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        clickable.click();
                        return match.text.slice(0, 140);
                    }
                    return '';
                }""",
                {
                    "dialCode": dial_code,
                    "terms": search_terms,
                    "isoCodes": iso_codes,
                    "countryNames": country_names,
                },
            )
            if clicked:
                logger.info("[phone-reg] 选择手机号国家: %s iso=%s -> %s", wanted, "/".join(iso_codes) or "-", str(clicked)[:100])
                if _wait_phone_country_selected(page, dial_code):
                    return True
                logger.warning("[phone-reg] 国家 option 点击后未生效: target=%s iso=%s clicked=%s", wanted, "/".join(iso_codes) or "-", str(clicked)[:80])
                return False
        except Exception:
            return False
        return False

    if _click_exact_iso_option():
        return True
    if _click_visible_country_option():
        return True

    candidate_selectors = [
        '[role="button"][aria-haspopup="dialog"]',
        '[role="button"][aria-haspopup="listbox"]',
        '[role="button"][aria-label*="country" i]',
        '[id^="select-trigger"]',
        '[aria-controls^="radix-"]',
        '[role="combobox"][aria-label*="country" i]',
        'button[aria-label*="country" i]',
        '[data-testid*="country" i]',
        'button[aria-haspopup="listbox"]',
        '[role="combobox"]',
        '[role="button"]:has-text("+")',
        'button:has-text("+")',
    ]
    for sel in candidate_selectors:
        try:
            controls = page.query_selector_all(sel)
        except Exception:
            continue
        for control in controls:
            try:
                if not control.is_visible():
                    continue
                label = " ".join([
                    control.inner_text() or "",
                    control.get_attribute("aria-label") or "",
                    control.get_attribute("data-testid") or "",
                ]).lower()
                if "country" not in label and "+" not in label and "phone" not in label:
                    continue
                already_open = (
                    (control.get_attribute("aria-expanded") or "").lower() == "true"
                    or (control.get_attribute("data-state") or "").lower() == "open"
                )
                try:
                    control.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                if not already_open:
                    try:
                        control.click(timeout=4000)
                    except Exception:
                        control.evaluate("el => el.click()")
                time.sleep(0.5)
                if _click_exact_iso_option():
                    return True
                if _click_visible_country_option():
                    return True
                search = _visible_first(page, [
                    'input[placeholder*="Search" i]',
                    'input[aria-label*="Search" i]',
                    'input[type="search"]',
                    'input[role="combobox"]',
                ])
                if search:
                    for term in [*country_names, *iso_codes, *search_terms]:
                        try:
                            search.fill(term)
                        except Exception:
                            continue
                        time.sleep(0.5)
                        if _click_exact_iso_option():
                            return True
                        if _click_visible_country_option():
                            return True
                for opt_sel in [
                    *[item for code in iso_codes for item in (f'[data-option-id="{code}"]', f'[data-option-id="{code.lower()}"]')],
                    f'[data-option-id]:has-text("{wanted}")',
                    f'[data-option-id]:has-text("+({dial_code})")',
                    f'[role="option"]:has-text("{wanted}")',
                    f'[role="option"]:has-text("+({dial_code})")',
                    f'[role="menuitem"]:has-text("{wanted}")',
                    f'[role="menuitem"]:has-text("+({dial_code})")',
                    f'[data-radix-collection-item]:has-text("{wanted}")',
                    f'[data-radix-collection-item]:has-text("+({dial_code})")',
                    f'[cmdk-item]:has-text("{wanted}")',
                    f'li:has-text("{wanted}")',
                    f'li:has-text("+({dial_code})")',
                    f'button:has-text("{wanted}")',
                    f'div[role="option"]:has-text("{wanted}")',
                ]:
                    try:
                        opt = page.query_selector(opt_sel)
                        if opt and opt.is_visible():
                            opt.click(timeout=4000)
                            logger.info("[phone-reg] 选择手机号国家: %s", wanted)
                            if _wait_phone_country_selected(page, dial_code):
                                return True
                            logger.warning("[phone-reg] 国家 selector 点击后未生效: %s", opt_sel)
                    except Exception:
                        continue
            except Exception:
                continue
    return False


def _select_phone_country(page, lease: PhoneLease) -> None:
    dial_code = "".join(ch for ch in str(lease.country_phone_code or "") if ch.isdigit())
    if not dial_code:
        logger.warning("[phone-reg] lease 缺 country_phone_code，跳过国家选择")
        return
    iso_codes = _country_iso_candidates(lease, dial_code)
    if _wait_phone_country_selected(page, dial_code, timeout_s=1.0):
        logger.info("[phone-reg] 手机号国家已是 +%s", dial_code)
        return
    logger.info("[phone-reg] 选择手机号国家 target=+%s iso=%s", dial_code, "/".join(iso_codes) or "-")
    if _select_native_country(page, dial_code) or _select_popup_country(page, dial_code, iso_codes):
        if _wait_phone_country_selected(page, dial_code):
            return
        logger.warning("[phone-reg] 国家选择点击后未确认到当前区号 +%s，继续按失败处理", dial_code)
    page.screenshot(path="/tmp/phone_reg_country_select_fail.png")
    raise RuntimeError(f"未能选择手机号国家 +{dial_code}")


def _fill_phone_number_and_continue(page, el, lease: PhoneLease) -> None:
    phone_number = _national_phone_from_lease(lease)
    if not phone_number:
        raise RuntimeError(f"手机号为空 lease={lease.lease_id}")
    _select_phone_country(page, lease)
    logger.info(
        "[phone-reg] 填手机号 national=%s country=+%s ...",
        PhoneProvider._mask_phone(phone_number),
        lease.country_phone_code or "",
    )
    for _try in range(4):
        try:
            phone_input = _visible_first(page, _phone_input_selectors()) or el
            if not phone_input:
                time.sleep(0.5)
                continue
            phone_input.click(timeout=5000)
            time.sleep(0.3)
            phone_input2 = _visible_first(page, _phone_input_selectors()) or phone_input
            (phone_input2 or phone_input).fill(phone_number)
            break
        except Exception as e:
            if "not attached" in str(e).lower() or "detached" in str(e).lower():
                logger.info("[phone-reg] phone input 脱链 重试 %s/4", _try + 1)
                time.sleep(0.5)
                continue
            raise
    time.sleep(random.uniform(0.5, 1.2))
    for sel in ['button[type="submit"]', 'button:has-text("Continue")', 'button:has-text("Next")']:
        b = page.query_selector(sel)
        if b and b.is_visible():
            b.click()
            logger.info("[phone-reg] 点击 phone 继续: %s", sel)
            break
    time.sleep(3)


def _otp_input_selectors() -> list[str]:
    return [
        'input[autocomplete="one-time-code"]',
        'input[name="code"]',
        'input[inputmode="numeric"]',
        'input[maxlength="1"]',
    ]


def _maybe_fill_password_like_browser(page, password: str) -> None:
    logger.info("[phone-reg] 等待密码框 ...")
    try:
        page.wait_for_selector(
            'input[type="password"], input[name="password"]',
            state="visible",
            timeout=30000,
        )
        pwd_input = page.query_selector('input[type="password"]:visible') or \
                    page.query_selector('input[name="password"]:visible')
        pwd_input.click()
        time.sleep(0.3)
        pwd_input.fill(password)
        time.sleep(random.uniform(0.5, 1.2))
        for sel in ['button[type="submit"]', 'button:has-text("Continue")',
                    'button:has-text("Create")', 'button:has-text("Next")']:
            b = page.query_selector(sel)
            if b and b.is_visible():
                b.click()
                logger.info("[phone-reg] 点击 password 继续: %s", sel)
                break
    except Exception as e:
        logger.warning("[phone-reg] 密码框异常: %s，可能走无密码 OTP 路径", e)
    time.sleep(3)
    logger.info("[phone-reg] 密码后 URL: %s", page.url[:120])


def _wait_antifraud_like_browser(page) -> None:
    logger.info("[phone-reg] 等待反欺诈检查 ...")
    for wait_i in range(30):
        time.sleep(1)
        try:
            cur = page.url
            if _has_phone_otp_input(page):
                logger.info("[phone-reg] 已到达 OTP 页面")
                break
            if "chatgpt.com" in cur and "auth.openai.com" not in cur:
                logger.info("[phone-reg] 已直接登录到 chatgpt.com")
                break
            if wait_i == 15:
                page.screenshot(path="/tmp/phone_reg_wait15.png")
                logger.info("[phone-reg] 15s 等待中: %s", cur[:80])
        except Exception as e:
            if _is_navigation_race(e):
                logger.info("[phone-reg] 页面正在跳转，继续等待反欺诈检查")
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                continue
            raise


def _is_navigation_race(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "execution context was destroyed" in msg
        or "most likely because of a navigation" in msg
        or "navigation" in msg and "destroyed" in msg
    )


def _has_phone_otp_input(page) -> bool:
    if _visible_first(
        page,
        [
            'input[autocomplete="one-time-code"]',
            'input[name="code"]',
            'input[id*="code" i]',
            'input[aria-label*="code" i]',
        ],
    ):
        return True
    text = _safe_body_text(page, limit=2500).lower()
    otp_context = any(
        token in text
        for token in (
            "verification code",
            "enter code",
            "code we sent",
            "one-time code",
            "security code",
            "check your phone",
            "verify your phone",
            "otp",
            "验证码",
        )
    )
    if not otp_context:
        return False
    try:
        visible_digit_count = 0
        for el in page.query_selector_all('input[maxlength="1"][inputmode="numeric"], input[maxlength="1"]'):
            try:
                if el.is_visible():
                    visible_digit_count += 1
            except Exception:
                continue
        if visible_digit_count >= 4:
            return True
    except Exception:
        pass
    try:
        return bool(page.evaluate('''() => {
            const visible = (el) => {
                const r = el.getBoundingClientRect();
                const cs = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
            };
            const nearbyText = (el) => {
                let cur = el;
                let out = '';
                for (let i = 0; cur && i < 4; i++, cur = cur.parentElement) {
                    out += ' ' + (cur.innerText || '');
                }
                return out;
            };
            return Array.from(document.querySelectorAll('input[inputmode="numeric"]')).some((el) => {
                if (!visible(el)) return false;
                const blob = [
                    el.name || '',
                    el.id || '',
                    el.placeholder || '',
                    el.getAttribute('aria-label') || '',
                    nearbyText(el),
                ].join(' ').toLowerCase();
                if (/age|birth|birthday|day|month|year|phone/.test(blob)) return false;
                return /code|otp|verification|security|验证码/.test(blob);
            });
        }'''))
    except Exception:
        return False


def _safe_page_url(page) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""


def _safe_body_text(page, *, limit: int = 6000) -> str:
    try:
        return str(page.evaluate(
            """(limit) => (document.body && document.body.innerText || '').slice(0, limit)""",
            limit,
        ) or "")
    except Exception:
        return ""


def _safe_visible(page, selectors: list[str]) -> bool:
    return bool(_visible_first(page, selectors))


def _session_access_token_len(page) -> int:
    try:
        value = page.evaluate('''async () => {
            try {
                const r = await fetch("/api/auth/session", {credentials: "include"});
                const d = await r.json();
                return d && d.accessToken ? d.accessToken.length : 0;
            } catch(e) {
                return 0;
            }
        }''')
        return int(value or 0)
    except Exception:
        return 0


def _looks_like_method_picker(page) -> bool:
    return _safe_visible(
        page,
        [
            'button:has-text("Continue with phone")',
            'button:has-text("Continue with email")',
            'button:has-text("Continue with Google")',
            'button:has-text("Continue with Apple")',
            'a:has-text("Continue with phone")',
            'a:has-text("Continue with email")',
        ],
    )


def _looks_like_chatgpt_home(page) -> bool:
    return _safe_visible(
        page,
        [
            'button[data-testid="signup-button"]',
            'a[data-testid="signup-button"]',
            'button:has-text("Sign up")',
            'a:has-text("Sign up")',
        ],
    )


def _looks_like_about_you(page, url: str, text: str) -> bool:
    if "/about-you" in url:
        return True
    return any(
        token in text
        for token in (
            "tell us about you",
            "tell us about yourself",
            "about you",
            "what should we call you",
            "full name",
            "date of birth",
            "birthday",
        )
    ) or bool(re.search(r"\bage\b|enter a valid age", text))


def _classify_page(page, *, phase: str, ctx: PhoneFlowContext | None = None) -> PageSnapshot:
    url = _safe_page_url(page)
    text = _safe_body_text(page).lower()
    if any(token in text for token in ("cloudflare", "checking your browser", "verify you are human")):
        return PageSnapshot(PageState.CLOUDFLARE_BLOCKED, url, text)
    if _looks_like_about_you(page, url, text):
        return PageSnapshot(PageState.ABOUT_YOU_FORM, url, text)
    try:
        has_otp = _has_phone_otp_input(page)
    except Exception as e:
        if _is_navigation_race(e):
            return PageSnapshot(PageState.UNKNOWN, url, text)
        raise
    if has_otp:
        if phase == "platform" and ctx and ctx.bound_email:
            return PageSnapshot(PageState.PLATFORM_EMAIL_OTP_FORM, url, text)
        return PageSnapshot(PageState.PHONE_OTP_FORM, url, text)
    if _safe_visible(page, ['input[type="password"], input[name="password"]']):
        return PageSnapshot(PageState.PASSWORD_FORM, url, text)
    if "contact-verification" in url:
        return PageSnapshot(PageState.CONTACT_VERIFICATION, url, text)
    if phase == "platform" and "auth.openai.com" in url and (
        "add-email" in url
        or "add email" in text
        or "email address" in text
        or "邮箱" in text
    ):
        return PageSnapshot(PageState.PLATFORM_EMAIL_FORM, url, text)
    if "platform.openai.com" in url or "build on the openai api platform" in text:
        if _safe_visible(page, _phone_input_selectors()):
            return PageSnapshot(PageState.PLATFORM_PHONE_FORM, url, text)
        if phase == "platform" and _has_phone_entry_button(page):
            return PageSnapshot(PageState.PLATFORM_METHOD_PICKER, url, text)
        if _safe_visible(page, _email_identifier_selectors()):
            if phase == "platform" and ctx and not ctx.platform_phone_submitted:
                return PageSnapshot(PageState.PLATFORM_LOGIN, url, text)
            return PageSnapshot(PageState.PLATFORM_EMAIL_FORM, url, text)
        if _looks_like_method_picker(page):
            return PageSnapshot(PageState.PLATFORM_METHOD_PICKER, url, text)
        if ctx and ctx.platform_email_submitted:
            return PageSnapshot(PageState.PLATFORM_BOUND, url, text)
        return PageSnapshot(PageState.PLATFORM_LOGIN, url, text)
    if _safe_visible(page, _phone_input_selectors()):
        return PageSnapshot(PageState.PHONE_NUMBER_FORM, url, text)
    if _looks_like_method_picker(page):
        return PageSnapshot(PageState.AUTH_METHOD_PICKER, url, text)
    if phase == "register" and _safe_visible(page, _email_identifier_selectors()):
        return PageSnapshot(PageState.REG_EMAIL_FORM, url, text)
    if "chatgpt.com" in url and "auth.openai.com" not in url:
        if _looks_like_chatgpt_home(page):
            return PageSnapshot(PageState.CHATGPT_HOME, url, text)
        if _session_access_token_len(page) > 100:
            return PageSnapshot(PageState.CHATGPT_LOGGED_IN, url, text)
        return PageSnapshot(PageState.UNKNOWN, url, text)
    if _looks_like_chatgpt_home(page):
        return PageSnapshot(PageState.CHATGPT_HOME, url, text)
    return PageSnapshot(PageState.UNKNOWN, url, text)


def _wait_after_state_action(page, seconds: float = 1.0) -> None:
    time.sleep(seconds)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass


def _fail_state(page, snapshot: PageSnapshot, reason: str, screenshot_name: str) -> None:
    try:
        page.screenshot(path=f"/tmp/{screenshot_name}")
    except Exception:
        pass
    raise RuntimeError(f"{reason}, state={snapshot.state.value} URL={snapshot.url[:120]}")


def _mark_action(ctx: PhoneFlowContext, action: str, observe_s: float) -> int:
    if ctx.action_attempts is None:
        ctx.action_attempts = {}
    attempts = int(ctx.action_attempts.get(action, 0)) + 1
    ctx.action_attempts[action] = attempts
    ctx.last_action = action
    ctx.observe_until = time.time() + observe_s
    logger.info("[phone-reg] action=%s attempt=%s observe=%.1fs", action, attempts, observe_s)
    return attempts


def _action_attempts(ctx: PhoneFlowContext, action: str) -> int:
    return int((ctx.action_attempts or {}).get(action, 0))


def _observing_action(ctx: PhoneFlowContext, action: str) -> bool:
    return ctx.last_action == action and time.time() < ctx.observe_until


def _wait_observing(ctx: PhoneFlowContext, action: str, state: PageState) -> None:
    remaining = max(0.0, ctx.observe_until - time.time())
    logger.info(
        "[phone-reg] action=%s 后观察中，当前仍是 %s，剩余 %.1fs",
        action,
        state.value,
        remaining,
    )
    time.sleep(min(ctx.timing.observe_poll_s, max(0.5, remaining)))


def _mark_email_unused(mail_provider, email: str, *, reason: str = "") -> None:
    email = str(email or "").strip()
    if not email:
        return
    marker = getattr(mail_provider, "mark_unused", None)
    if not callable(marker):
        logger.info("[phone-reg] 邮箱 provider 不支持 mark_unused，跳过回滚 email=%s", email)
        return
    try:
        marker(email)
        logger.info("[phone-reg] 邮箱状态已回滚为 unused: %s reason=%s", email, reason[:80])
    except Exception as e:
        logger.warning("[phone-reg] 邮箱状态回滚 unused 失败 email=%s: %s", email, e)


def _mark_email_used(mail_provider, email: str) -> None:
    email = str(email or "").strip()
    if not email:
        return
    marker = getattr(mail_provider, "mark_used", None)
    if not callable(marker):
        return
    try:
        marker(email)
        logger.info("[phone-reg] 邮箱状态已标记 used: %s", email)
    except Exception as e:
        logger.warning("[phone-reg] 邮箱状态标记 used 失败 email=%s: %s", email, e)


def _cancel_phone_lease(ctx: PhoneFlowContext, *, reason: str) -> None:
    if not ctx.lease or ctx.phone_cancelled:
        return
    try:
        ctx.provider.mark_failed(ctx.lease.lease_id, reason[:200])
        if getattr(ctx.provider, "provider", "") != "hero_sms":
            ctx.provider.release(ctx.lease.lease_id)
        ctx.phone_cancelled = True
        logger.info("[phone-reg] 已取消手机号 lease=%s reason=%s", ctx.lease.lease_id, reason[:80])
    except Exception as e:
        logger.warning("[phone-reg] 取消手机号失败 lease=%s: %s", ctx.lease.lease_id, e)


def _cleanup_failed_phone_flow(ctx: PhoneFlowContext, *, reason: str) -> None:
    _cancel_phone_lease(ctx, reason=reason)
    email = str(ctx.bound_email or ctx.result.get("email") or "").strip()
    if email and not ctx.email_reverted:
        _mark_email_unused(ctx.mail_provider, email, reason=reason)
        ctx.email_reverted = True


def _poll_phone_otp(ctx: PhoneFlowContext, *, stage: str) -> str:
    if not ctx.lease:
        raise RuntimeError(f"{stage} OTP 获取前缺手机号 lease")
    try:
        return ctx.provider.poll_otp(ctx.lease.lease_id)
    except TimeoutError as e:
        _cleanup_failed_phone_flow(ctx, reason=f"{stage}_phone_otp_timeout")
        raise RuntimeError(f"{stage} 验证码超过 2 分钟未获取到，已取消手机号并回滚邮箱状态") from e


def _visible_error_text(page, patterns: list[str]) -> str:
    try:
        return str(page.evaluate(
            """(patterns) => {
                const text = document.body?.innerText || '';
                for (const pattern of patterns) {
                    const re = new RegExp(pattern, 'i');
                    const m = text.match(re);
                    if (m) return m[0];
                }
                return '';
            }""",
            patterns,
        ) or "")
    except Exception:
        return ""


def _phone_form_error(page) -> str:
    return _visible_error_text(
        page,
        [
            "invalid phone[^\\n]*",
            "unsupported country[^\\n]*",
            "phone number is not supported[^\\n]*",
            "unable to send code[^\\n]*",
            "too many attempts[^\\n]*",
            "too many requests[^\\n]*",
            "invalid number[^\\n]*",
            "not a valid phone[^\\n]*",
            "an account for this phone number already exists[^\\n]*",
            "phone number already exists[^\\n]*",
            "account already exists[^\\n]*phone[^\\n]*",
        ],
    )


def _password_form_error(page) -> str:
    return _visible_error_text(
        page,
        [
            "incorrect phone number or password[^\\n]*",
            "incorrect phone[^\\n]*password[^\\n]*",
            "invalid phone number or password[^\\n]*",
            "wrong phone number or password[^\\n]*",
        ],
    )


def _fill_phone_otp_like_browser(page, code: str) -> None:
    def _fill_fields() -> None:
        otp_filled = False
        single = page.query_selector('input[autocomplete="one-time-code"]') or \
                 page.query_selector('input[name="code"]') or \
                 page.query_selector('input[inputmode="numeric"]:not([maxlength="1"])')
        if single:
            single.click()
            time.sleep(0.3)
            try:
                single.fill("")
            except Exception:
                pass
            single.fill(code)
            otp_filled = True
        else:
            digits = page.query_selector_all('input[maxlength="1"][inputmode="numeric"]') or \
                     page.query_selector_all('input[maxlength="1"]')
            visible_digits = []
            for d in digits:
                try:
                    if d.is_visible():
                        visible_digits.append(d)
                except Exception:
                    pass
            if len(visible_digits) >= len(code[:6]):
                for i, ch in enumerate(code[:6]):
                    visible_digits[i].click()
                    time.sleep(0.1)
                    try:
                        visible_digits[i].fill("")
                    except Exception:
                        pass
                    visible_digits[i].fill(ch)
                otp_filled = True
        if not otp_filled:
            page.screenshot(path="/tmp/phone_reg_otp_fail.png")
            raise RuntimeError("OTP 输入框未找到")

    def _click_continue() -> None:
        for sel in ['button[type="submit"]', 'button:has-text("Continue")',
                    'button:has-text("Verify")', 'button:has-text("Next")']:
            b = page.query_selector(sel)
            if b and b.is_visible():
                b.click()
                logger.info("[phone-reg] 点击 OTP 继续: %s", sel)
                break

    def _click_retry() -> bool:
        for sel in [
            'button:has-text("Try again")',
            'button:has-text("Retry")',
            'button:has-text("重试")',
            'button:has-text("再试一次")',
            'button:has-text("重新尝试")',
            'a:has-text("Try again")',
            'a:has-text("Retry")',
            'a:has-text("重试")',
        ]:
            try:
                b = page.query_selector(sel)
                if not b or not b.is_visible():
                    continue
                label = (b.inner_text() or "").strip()
                b.click(timeout=5000)
                logger.info("[phone-reg] OTP 提交失败，点击重试: %s", label[:40] or sel)
                time.sleep(1.5)
                return True
            except Exception:
                continue
        return False

    def _has_rejected_code_error() -> bool:
        try:
            err = page.query_selector(
                'text=/incorrect code|invalid code|wrong code|验证码不正确|验证码错误/i'
            )
            return bool(err and err.is_visible())
        except Exception:
            return False

    try:
        max_attempts = max(1, int(os.getenv("PHONE_OTP_SAME_CODE_RETRY", "2") or "2"))
    except Exception:
        max_attempts = 2
    for attempt in range(max_attempts):
        _fill_fields()
        time.sleep(0.8)
        _click_continue()
        time.sleep(4)
        if _click_retry():
            if attempt + 1 >= max_attempts:
                page.screenshot(path="/tmp/phone_reg_otp_retry_exhausted.png")
                raise RuntimeError("手机号 OTP 提交失败，重试后仍未通过")
            _wait_for_any(page, _otp_input_selectors(), timeout_s=15, label="phone_otp_retry")
            logger.info("[phone-reg] 使用同一个 OTP 重新输入 (%s/%s)", attempt + 2, max_attempts)
            continue
        if _has_rejected_code_error():
            page.screenshot(path="/tmp/phone_reg_otp_rejected.png")
            raise RuntimeError("OpenAI 拒绝手机号 OTP")
        return

    raise RuntimeError("手机号 OTP 提交失败")

def _fill_input_and_continue(page, el, value: str, *, label: str) -> None:
    try:
        el.click(timeout=5000)
    except Exception as e:
        if _is_navigation_race(e):
            raise
        try:
            el.evaluate("node => node.click()")
        except Exception:
            try:
                el.focus()
            except Exception:
                raise e
    time.sleep(0.2)
    try:
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
    except Exception:
        pass
    try:
        el.fill(value)
    except Exception:
        page.keyboard.type(value, delay=random.randint(30, 70))
    time.sleep(random.uniform(0.4, 0.9))
    _click_first(
        page,
        [
            'button[type="submit"]',
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'button:has-text("Verify")',
            'button:has-text("Send code")',
        ],
        log_label=f"{label} 继续",
    )


def _fill_otp(page, code: str, *, label: str) -> None:
    single = _visible_first(
        page,
        [
            'input[autocomplete="one-time-code"]',
            'input[name="code"]',
            'input[inputmode="numeric"]:not([maxlength="1"])',
        ],
    )
    if single:
        _fill_input_and_continue(page, single, code, label=label)
        return
    digits = page.query_selector_all('input[maxlength="1"][inputmode="numeric"]') or page.query_selector_all('input[maxlength="1"]')
    visible_digits = []
    for d in digits:
        try:
            if d.is_visible():
                visible_digits.append(d)
        except Exception:
            pass
    if len(visible_digits) >= 6:
        for i, ch in enumerate(code[:6]):
            visible_digits[i].click()
            time.sleep(0.08)
            visible_digits[i].fill(ch)
        time.sleep(0.5)
        _click_first(
            page,
            ['button[type="submit"]', 'button:has-text("Continue")', 'button:has-text("Verify")', 'button:has-text("Next")'],
            log_label=f"{label} 继续",
        )
        return
    page.screenshot(path=f"/tmp/phone_reg_{label}_otp_missing.png")
    raise RuntimeError(f"{label} OTP 输入框未找到")


def _click_retry_button(page, *, label: str) -> bool:
    for sel in [
        'button:has-text("Try again")',
        'button:has-text("Retry")',
        'button:has-text("重试")',
        'button:has-text("再试一次")',
        'button:has-text("重新尝试")',
        'a:has-text("Try again")',
        'a:has-text("Retry")',
        'a:has-text("重试")',
    ]:
        try:
            b = page.query_selector(sel)
            if not b or not b.is_visible():
                continue
            text = (b.inner_text() or "").strip()
            b.click(timeout=5000)
            logger.info("[phone-reg] %s 提交失败，点击重试: %s", label, text[:40] or sel)
            time.sleep(1.5)
            return True
        except Exception:
            continue
    return False


def _flow_otp_timeout_s(value: Any, *, default: int = 120) -> int:
    try:
        raw = int(value or default)
    except Exception:
        raw = default
    timeout_s = max(1, min(raw, 120))
    if raw > 120:
        logger.info("[phone-reg] OTP timeout capped at 120s (configured=%ss)", raw)
    return timeout_s


def _submit_email_otp_with_retry(page, mail_provider, email: str, issued_at: float, *, label: str) -> str:
    otp_timeout = _flow_otp_timeout_s(os.getenv("OTP_TIMEOUT", str(getattr(mail_provider, "otp_timeout", 120) or 120)))
    code = mail_provider.wait_for_otp(email, timeout=otp_timeout, issued_after=issued_at)
    try:
        max_attempts = max(1, int(os.getenv("EMAIL_OTP_SAME_CODE_RETRY", "2") or "2"))
    except Exception:
        max_attempts = 2
    for attempt in range(max_attempts):
        _wait_for_any(page, _otp_input_selectors(), timeout_s=30, label=f"{label}_otp")
        _fill_otp(page, code, label=label)
        time.sleep(4)
        if not _click_retry_button(page, label=label):
            return code
        if attempt + 1 >= max_attempts:
            page.screenshot(path=f"/tmp/phone_reg_{label}_otp_retry_exhausted.png")
            raise RuntimeError(f"{label} OTP 提交失败，重试后仍未通过")
        logger.info("[phone-reg] 使用同一个 %s OTP 重新输入 (%s/%s)", label, attempt + 2, max_attempts)
    return code


def _wait_platform_email_binding_complete(page, ctx: PhoneFlowContext, *, timeout_s: float = 30.0) -> None:
    logger.info("[phone-reg] platform 邮箱验证码提交后等待当前页面完成加载 ...")
    deadline = time.time() + timeout_s
    last_state = ""
    while time.time() < deadline:
        for state_name, state_timeout in (("domcontentloaded", 5000), ("networkidle", 3000)):
            try:
                page.wait_for_load_state(state_name, timeout=state_timeout)
            except Exception:
                pass
        snapshot = _classify_page(page, phase="platform", ctx=ctx)
        if snapshot.state.value != last_state:
            logger.info("[phone-reg] platform email otp wait state=%s URL=%s", snapshot.state.value, snapshot.url[:120])
            last_state = snapshot.state.value
        if _visible_first(page, [
            'button:has-text("Try again")',
            'button:has-text("Retry")',
            'button:has-text("重试")',
            'button:has-text("再试一次")',
        ]):
            page.screenshot(path="/tmp/phone_reg_platform_email_otp_retry_after_submit.png")
            raise RuntimeError("Platform 邮箱 OTP 提交后页面提示重试")
        if snapshot.state in (PageState.PLATFORM_BOUND, PageState.CHATGPT_LOGGED_IN):
            return
        if snapshot.state not in (PageState.PLATFORM_EMAIL_OTP_FORM, PageState.PLATFORM_EMAIL_FORM, PageState.UNKNOWN):
            return
        time.sleep(1)
    page.screenshot(path="/tmp/phone_reg_platform_email_otp_wait_timeout.png")
    raise RuntimeError(f"Platform 邮箱 OTP 提交后等待页面加载完成超时 ({int(timeout_s)}s)")


def _maybe_bind_email(page, mail_provider, *, result: dict) -> str:
    email_input = _visible_first(page, ['input[type="email"]', 'input[name="email"]'])
    if not email_input:
        return ""
    email = mail_provider.create_mailbox()
    persona = getattr(mail_provider, "last_persona", None)
    if not result.get("password") and persona is not None and getattr(persona, "password", ""):
        result["password"] = persona.password
    logger.info("[phone-reg] 绑定邮箱: %s", email)
    issued_at = time.time()
    _fill_input_and_continue(page, email_input, email, label="email")
    try:
        otp_box = _wait_for_any(page, _otp_input_selectors(), timeout_s=45, label="email_otp")
    except Exception:
        return email
    otp_timeout = _flow_otp_timeout_s(os.getenv("OTP_TIMEOUT", str(getattr(mail_provider, "otp_timeout", 120) or 120)))
    code = mail_provider.wait_for_otp(email, timeout=otp_timeout, issued_after=issued_at)
    if otp_box:
        _fill_otp(page, code, label="email")
    return email


def _bind_email_via_platform(page, mail_provider, lease: PhoneLease, *, result: dict) -> str:
    if result.get("email"):
        return str(result.get("email") or "")

    logger.info("[phone-reg] 注册后补绑定邮箱：打开 platform login ...")
    page.goto("https://platform.openai.com/login", wait_until="domcontentloaded", timeout=60000)
    _raise_if_blocking_challenge(
        page,
        stage="opening platform login for email binding",
        screenshot_path="/tmp/phone_reg_platform_cloudflare_challenge.png",
    )
    time.sleep(3)

    phone_input = _visible_first(page, _phone_input_selectors())
    phone_entry_clicked = False
    if not phone_input:
        phone_entry_clicked = _click_phone_entry(page)
    if phone_entry_clicked:
        phone_input = _wait_for_any(page, _phone_input_selectors(), timeout_s=30, label="platform_phone_login")
    else:
        phone_input = _visible_first(page, _phone_input_selectors())
    if phone_input:
        logger.info("[phone-reg] platform 手机号登录：填刚注册手机号")
        _fill_phone_number_and_continue(page, phone_input, lease)
    else:
        logger.info("[phone-reg] platform 未看到手机号输入框，继续等待邮箱绑定页")

    email_input = None
    for i in range(90):
        email_input = _visible_first(page, _email_identifier_selectors())
        if email_input:
            break
        if i % 10 == 5:
            _click_first(
                page,
                [
                    'button:has-text("Continue")',
                    'button:has-text("Next")',
                    'button:has-text("Submit")',
                    'button[type="submit"]',
                ],
                log_label="platform 邮箱绑定中转",
            )
        time.sleep(1)
    if not email_input:
        page.screenshot(path="/tmp/phone_reg_platform_email_missing.png")
        raise RuntimeError(f"platform 手机号登录后未出现邮箱输入框, URL={page.url[:120]}")

    email = mail_provider.create_mailbox()
    persona = getattr(mail_provider, "last_persona", None)
    if not result.get("password") and persona is not None and getattr(persona, "password", ""):
        result["password"] = persona.password
    logger.info("[phone-reg] platform 绑定邮箱: %s", email)
    issued_at = time.time()
    _fill_input_and_continue(page, email_input, email, label="platform email")

    otp_box = _wait_for_any(page, _otp_input_selectors(), timeout_s=60, label="platform_email_otp")
    otp_timeout = _flow_otp_timeout_s(os.getenv("OTP_TIMEOUT", str(getattr(mail_provider, "otp_timeout", 120) or 120)))
    code = mail_provider.wait_for_otp(email, timeout=otp_timeout, issued_after=issued_at)
    if otp_box:
        _fill_otp(page, code, label="platform_email")
    result["email"] = email
    logger.info("[phone-reg] platform 邮箱验证码已提交，等待当前页面完成加载 ...")
    legacy_deadline = time.time() + 30
    while time.time() < legacy_deadline:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass
        if not _visible_first(page, _otp_input_selectors()):
            break
        if _visible_first(page, ['button:has-text("Try again")', 'button:has-text("Retry")']):
            page.screenshot(path="/tmp/phone_reg_platform_email_otp_retry_after_submit.png")
            raise RuntimeError("Platform 邮箱 OTP 提交后页面提示重试")
        time.sleep(1)
    else:
        page.screenshot(path="/tmp/phone_reg_platform_email_otp_wait_timeout.png")
        raise RuntimeError("Platform 邮箱 OTP 提交后等待页面加载完成超时 (30s)")
    logger.info("[phone-reg] platform 邮箱验证码已提交并完成页面加载，回到 ChatGPT 收集 session")
    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
    return email


def _maybe_fill_about_you(page, first_name: str, last_name: str) -> None:
    logger.info("[phone-reg] OTP 后 URL: %s", page.url[:120])
    time.sleep(5)
    logger.info("[phone-reg] 稳定后 URL: %s", page.url[:120])

    def _advance_contact_verification() -> bool:
        if "contact-verification" not in (page.url or ""):
            return False
        clicked = _click_first(
            page,
            [
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'button:has-text("Try again")',
                'button:has-text("Retry")',
                'button:has-text("重试")',
                'button[type="submit"]',
                'a:has-text("Continue")',
                'a:has-text("Try again")',
            ],
            log_label="contact-verification 中转",
        )
        if clicked:
            time.sleep(2)
        return clicked

    for i in range(30):
        time.sleep(1)
        if "about-you" in page.url or "chatgpt.com" in page.url:
            break
        if _advance_contact_verification():
            continue
        if i == 5:
            page.screenshot(path="/tmp/phone_reg_contact_verification_wait.png")
            logger.info("[phone-reg] 等待 contact-verification 推进, URL=%s", page.url[:100])

    def _enum_inputs():
        try:
            return page.evaluate('''() => {
                const nearbyText = (el) => {
                    let cur = el.parentElement;
                    for (let i = 0; cur && i < 5; i++, cur = cur.parentElement) {
                        const text = (cur.innerText || '').trim();
                        if (text && text.length <= 220) return text;
                    }
                    return '';
                };
                return Array.from(document.querySelectorAll('input')).map((el, idx) => {
                    const r = el.getBoundingClientRect();
                    const cs = getComputedStyle(el);
                    const labelledBy = (el.getAttribute('aria-labelledby') || '')
                        .split(/\\s+/)
                        .map(id => document.getElementById(id)?.innerText || '')
                        .join(' ');
                    const describedBy = (el.getAttribute('aria-describedby') || '')
                        .split(/\\s+/)
                        .map(id => document.getElementById(id)?.innerText || '')
                        .join(' ');
                    const parentText = nearbyText(el);
                    return {
                        idx,
                        type: (el.type || '').toLowerCase(),
                        name: el.name || '',
                        placeholder: el.placeholder || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        label: (el.labels && el.labels[0] && el.labels[0].innerText) || '',
                        labelledBy,
                        describedBy,
                        parentText: parentText.slice(0, 500),
                        value: el.value || '',
                        visible: (r.width > 0 && r.height > 0 &&
                                  cs.visibility !== 'hidden' && cs.display !== 'none'),
                    };
                });
            }''') or []
        except Exception:
            return []

    def _about_you_context() -> bool:
        try:
            return bool(page.evaluate('''() => {
                const url = location.href.toLowerCase();
                const text = (document.body?.innerText || '').toLowerCase();
                if (url.includes('/about-you')) return true;
                return [
                    'tell us about you',
                    'tell us about yourself',
                    'about you',
                    'what should we call you',
                    'what is your name',
                    'full name',
                    'date of birth',
                    'birthday',
                    'birth date'
                ].some(s => text.includes(s));
            }'''))
        except Exception:
            return False

    def _is_birthday(meta: dict) -> bool:
        blob = " ".join([meta.get("type",""), meta.get("name",""),
                          meta.get("placeholder",""), meta.get("ariaLabel",""),
                          meta.get("label",""), meta.get("labelledBy",""),
                          meta.get("describedBy",""), meta.get("parentText","")]).lower()
        if meta.get("type") == "date":
            return True
        return any(kw in blob for kw in ("birth", "birthday", "dob", "date of birth", "mm/dd/yyyy", "mm / dd / yyyy"))

    def _is_name_input(meta: dict) -> bool:
        blob = " ".join([meta.get("name",""), meta.get("placeholder",""),
                          meta.get("ariaLabel",""), meta.get("label",""),
                          meta.get("labelledBy",""), meta.get("describedBy",""),
                          meta.get("parentText","")]).lower()
        return any(kw in blob for kw in ("name", "first", "last", "full", "given", "family", "age"))

    def _date_part(meta: dict) -> str:
        blob = " ".join([meta.get("name",""), meta.get("placeholder",""),
                          meta.get("ariaLabel",""), meta.get("label",""),
                          meta.get("labelledBy",""), meta.get("describedBy",""),
                          meta.get("parentText","")]).lower()
        if any(kw in blob for kw in ("month", "mm")):
            return "month"
        if any(kw in blob for kw in ("day", "dd")):
            return "day"
        if any(kw in blob for kw in ("year", "yyyy")):
            return "year"
        return ""

    def _meta_blob(meta: dict) -> str:
        return " ".join([
            str(meta.get("type", "")),
            str(meta.get("name", "")),
            str(meta.get("placeholder", "")),
            str(meta.get("ariaLabel", "")),
            str(meta.get("label", "")),
            str(meta.get("labelledBy", "")),
            str(meta.get("describedBy", "")),
        ]).strip()

    def _looks_like_chat_ui() -> bool:
        try:
            return bool(page.evaluate('''() => {
                const url = location.href;
                if (url.includes("/about-you")) return false;
                const bodyText = (document.body?.innerText || '').toLowerCase();
                if ([
                    'tell us about you',
                    'tell us about yourself',
                    'about you',
                    'what should we call you',
                    'full name',
                    'date of birth',
                    'birthday'
                ].some(s => bodyText.includes(s))) return false;
                const ta = document.querySelector('textarea[placeholder*="Ask"], div[contenteditable="true"]');
                const nc = Array.from(document.querySelectorAll("a, button"))
                    .some(el => /new chat/i.test(el.textContent || ""));
                return !!(ta || nc);
            }'''))
        except Exception:
            return False

    def _all_inputs_or_empty() -> list:
        try:
            return page.query_selector_all('input')
        except Exception as e:
            if _is_navigation_race(e):
                logger.info("[phone-reg] about-you 检测时页面正在跳转，继续等待")
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                return []
            raise

    full_name_input = None
    birthday_input = None
    birthday_meta = None
    birthday_part_inputs = {}
    for attempt in range(30):
        about_ctx = _about_you_context()
        metas = _enum_inputs()
        visible_metas = [m for m in metas if m["visible"]
                          and m["type"] not in ("hidden","submit","button","checkbox","radio","password")]
        if not visible_metas and _advance_contact_verification():
            continue
        bd = next((m for m in visible_metas if _is_birthday(m)), None)
        name_m = next((m for m in visible_metas
                        if m is not bd and _is_name_input(m) and not _is_birthday(m)), None)
        if bd and name_m:
            all_inputs_el = _all_inputs_or_empty()
            if len(all_inputs_el) <= max(name_m["idx"], bd["idx"]):
                time.sleep(1)
                continue
            full_name_input = all_inputs_el[name_m["idx"]]
            birthday_input = all_inputs_el[bd["idx"]]
            birthday_meta = bd
            logger.info("[phone-reg] 表单: name.idx=%s birthday.idx=%s type=%s placeholder=%r",
                        name_m["idx"], bd["idx"], bd["type"], bd["placeholder"][:30])
            break
        date_parts = {part: m for m in visible_metas if (part := _date_part(m))}
        if about_ctx and len(visible_metas) >= 2:
            all_inputs_el = _all_inputs_or_empty()
            if not all_inputs_el:
                time.sleep(1)
                continue
            fallback_name = name_m or next(
                (m for m in visible_metas if not _is_birthday(m) and not _date_part(m)),
                visible_metas[0],
            )
            if len(all_inputs_el) <= fallback_name["idx"]:
                time.sleep(1)
                continue
            full_name_input = all_inputs_el[fallback_name["idx"]]
            if {"month", "day", "year"}.issubset(date_parts):
                if len(all_inputs_el) <= max(meta["idx"] for meta in date_parts.values()):
                    time.sleep(1)
                    continue
                birthday_part_inputs = {
                    part: all_inputs_el[meta["idx"]]
                    for part, meta in date_parts.items()
                    if part in {"month", "day", "year"}
                }
                birthday_meta = date_parts.get("year") or date_parts.get("month")
                logger.info("[phone-reg] 表单 (about-you split birthday): name.idx=%s parts=%s",
                            fallback_name["idx"], sorted(birthday_part_inputs.keys()))
                break
            birthday_m = bd or next((m for m in visible_metas if m is not fallback_name), None)
            if birthday_m:
                if len(all_inputs_el) <= birthday_m["idx"]:
                    time.sleep(1)
                    continue
                birthday_input = all_inputs_el[birthday_m["idx"]]
                birthday_meta = birthday_m
                logger.info("[phone-reg] 表单 (about-you fallback): name.idx=%s birthday.idx=%s blob=%r",
                            fallback_name["idx"], birthday_m["idx"], _meta_blob(birthday_m)[:80])
                break
        if (
            not bd
            and len(visible_metas) >= 2
            and any(_is_name_input(m) for m in visible_metas)
            and not _looks_like_chat_ui()
        ):
            all_inputs_el = _all_inputs_or_empty()
            if len(all_inputs_el) <= max(visible_metas[0]["idx"], visible_metas[1]["idx"]):
                time.sleep(1)
                continue
            full_name_input = all_inputs_el[visible_metas[0]["idx"]]
            birthday_input = all_inputs_el[visible_metas[1]["idx"]]
            birthday_meta = visible_metas[1]
            logger.info("[phone-reg] 表单 (legacy age): %s inputs", len(visible_metas))
            break
        if (
            "chatgpt.com" in page.url
            and "auth" not in page.url
            and "/about-you" not in page.url
            and _looks_like_chat_ui()
        ):
            logger.info("[phone-reg] URL 在 chatgpt.com 主页，无 about-you 表单 → 跳过表单填写")
            break
        if attempt == 5:
            page.screenshot(path="/tmp/phone_reg_about_you_wait.png")
            logger.info("[phone-reg] 等待 about-you 输入框 5s, URL=%s inputs visible=%s",
                        page.url[:100], len(visible_metas))
            logger.info("[phone-reg] about-you candidates: %s",
                        " | ".join(_meta_blob(m)[:120] for m in visible_metas[:5]))
        time.sleep(1)

    if full_name_input and (birthday_input or birthday_part_inputs):
        page.screenshot(path="/tmp/phone_reg_about_you.png")
        full_name = f"{first_name} {last_name}"
        import datetime as _dt
        year = _dt.datetime.now().year - random.randint(26, 40)
        mm, dd = "01", "15"
        bd_type = (birthday_meta or {}).get("type", "")
        birthday_str = f"{year}-{mm}-{dd}" if bd_type == "date" else f"{mm}/{dd}/{year}"
        legacy_age = str(random.randint(26, 40))
        logger.info("[phone-reg] 填 Full name=%s Birthday=%s (legacy_age=%s)", full_name, birthday_str, legacy_age)
        try:
            full_name_input.focus(); time.sleep(0.3)
            page.keyboard.type(full_name, delay=random.randint(30, 80))
            time.sleep(random.uniform(0.4, 0.9))
            if birthday_part_inputs:
                parts = {"month": mm, "day": dd, "year": str(year)}
                for part, value in parts.items():
                    field = birthday_part_inputs.get(part)
                    if not field:
                        continue
                    field.focus(); time.sleep(0.2)
                    try:
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Delete")
                    except Exception:
                        pass
                    try:
                        field.fill(value)
                    except Exception:
                        page.keyboard.type(value, delay=random.randint(30, 70))
                    time.sleep(0.2)
            else:
                birthday_input.focus(); time.sleep(0.3)
                try:
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Delete")
                except Exception:
                    pass
                if bd_type == "date":
                    try:
                        birthday_input.fill(birthday_str)
                    except Exception:
                        page.keyboard.type(birthday_str, delay=random.randint(30, 70))
                else:
                    if _is_birthday(birthday_meta or {}):
                        page.keyboard.type(birthday_str, delay=random.randint(30, 70))
                    else:
                        page.keyboard.type(legacy_age, delay=random.randint(40, 100))
            time.sleep(random.uniform(0.4, 0.9))
            clicked = False
            for sel in ['button:has-text("Finish")', 'button:has-text("Create")',
                        'button:has-text("Agree")', 'button[type="submit"]',
                        'button:has-text("Continue")']:
                b = page.query_selector(sel)
                if b and b.is_visible():
                    b.click()
                    clicked = True
                    logger.info("[phone-reg] 点击 about-you 继续: %s", sel)
                    break
            if not clicked:
                page.screenshot(path="/tmp/phone_reg_no_finish_btn.png")
        except Exception as e:
            logger.warning("[phone-reg] about-you 填写异常: %s", e)
            page.screenshot(path="/tmp/phone_reg_name_fail.png")
    else:
        page.screenshot(path="/tmp/phone_reg_no_name_form.png")
        logger.warning("[phone-reg] 未找到 about-you 表单，URL=%s", page.url[:120])


def _wait_and_collect_session(page, ctx, result: dict, *, bound_email: str) -> dict:
    logger.info("[phone-reg] 等待跳转回 chatgpt.com ...")
    arrived = False
    last_url = ""
    for i in range(120):
        time.sleep(1)
        cur = page.url
        if cur != last_url:
            logger.info("[phone-reg] URL@%ss: %s", i, cur[:120])
            last_url = cur
        if "chatgpt.com" in cur and "auth.openai.com" not in cur:
            try:
                info = page.evaluate('''async () => {
                    try {
                        const r = await fetch("/api/auth/session", {credentials: "include"});
                        const d = await r.json();
                        return d.accessToken ? d.accessToken.length : 0;
                    } catch(e){ return -1; }
                }''')
                if info and info > 100:
                    arrived = True
                    logger.info("[phone-reg] 到达 + session accessToken 长度=%s", info)
                    break
            except Exception:
                pass
        if "auth.openai.com" in cur and i % 10 == 5:
            for sel in ['button:has-text("Continue")', 'button:has-text("Next")', 'button[type="submit"]']:
                try:
                    b = page.query_selector(sel)
                    if b and b.is_visible():
                        b.click()
                        logger.info("[phone-reg] 中转点击: %s", sel)
                        break
                except Exception:
                    pass
    if not arrived:
        page.screenshot(path="/tmp/phone_reg_no_chatgpt.png")
        raise RuntimeError(f"未跳转回 chatgpt.com，当前: {page.url[:120]}")

    time.sleep(5)
    logger.info("[phone-reg] 拉取 /api/auth/session ...")
    session_info = page.evaluate('''async () => {
        const r = await fetch("/api/auth/session", {credentials: "include"});
        return await r.json();
    }''')
    result["access_token"] = session_info.get("accessToken", "")
    result["id_token"] = session_info.get("idToken", "") if isinstance(session_info, dict) else ""
    result["email"] = _resolve_email(session_info, result["access_token"], result["id_token"], bound_email)
    logger.info("[phone-reg] access_token 长度: %s", len(result["access_token"]))

    all_cookies = ctx.cookies()
    chatgpt_cookies = [c for c in all_cookies if "chatgpt.com" in c.get("domain", "")]
    for c in chatgpt_cookies:
        name = c.get("name", "")
        if name == "__Secure-next-auth.session-token":
            result["session_token"] = c.get("value", "")
        elif name in ("oai-did", "oai-device-id"):
            result["device_id"] = c.get("value", "")
        elif name == "__Host-next-auth.csrf-token":
            value = c.get("value", "")
            result["csrf_token"] = value.split("|")[0] if "|" in value else value
    result["cookie_header"] = "; ".join(f"{c['name']}={c['value']}" for c in chatgpt_cookies)
    if not result.get("email"):
        raise RuntimeError("手机号注册完成但未解析到绑定邮箱")
    if bound_email and result["email"].strip().lower() != bound_email.strip().lower():
        raise RuntimeError(f"手机号注册完成但 session email 与绑定邮箱不一致: session={result['email']} bound={bound_email}")
    if not result.get("access_token"):
        raise RuntimeError("手机号注册完成但缺 access_token")
    if not result.get("session_token"):
        page.screenshot(path="/tmp/phone_reg_missing_session_token.png")
        raise RuntimeError("手机号注册完成但缺 session_token")
    return session_info


def _validate_phone_result_before_return(result: dict, *, bound_email: str) -> None:
    missing = []
    for key in ("email", "session_token", "access_token", "register_method", "phone_number", "phone_dial_code"):
        if not str(result.get(key) or "").strip():
            missing.append(key)
    if missing:
        raise RuntimeError(f"手机号注册结果不完整，缺: {', '.join(missing)}")
    if not bound_email:
        raise RuntimeError("手机号注册结果不完整，缺绑定邮箱")
    if result.get("register_method") != "phone_browser":
        raise RuntimeError(f"手机号注册方法异常: {result.get('register_method')}")
    if bound_email and str(result.get("email") or "").strip().lower() != bound_email.strip().lower():
        raise RuntimeError(f"绑定邮箱校验失败: result={result.get('email')} bound={bound_email}")


def _allocate_phone_if_needed(ctx: PhoneFlowContext) -> PhoneLease:
    if ctx.lease:
        return ctx.lease
    lease = ctx.provider.allocate()
    ctx.lease = lease
    ctx.result["phone_number"] = _national_phone_from_lease(lease)
    ctx.result["phone_dial_code"] = lease.country_phone_code or ""
    logger.info(
        "[phone-reg] 分配手机号 lease=%s phone=%s national=%s country=+%s",
        lease.lease_id,
        lease.masked_phone,
        PhoneProvider._mask_phone(lease.phone_national or ""),
        lease.country_phone_code or "",
    )
    return lease


def _handle_phone_number_form(page, ctx: PhoneFlowContext, *, label: str, action: str) -> None:
    lease = _allocate_phone_if_needed(ctx)
    phone_input = _visible_first(page, _phone_input_selectors()) or _wait_for_any(
        page,
        _phone_input_selectors(),
        timeout_s=30,
        label=label,
    )
    logger.info("[phone-reg] 已到达手机号输入框: %s", _input_summary(phone_input))
    _fill_phone_number_and_continue(page, phone_input, lease)
    _mark_action(ctx, action, ctx.timing.phone_submit_observe_s)


def _run_register_state_machine(page, ctx: PhoneFlowContext) -> None:
    logger.info("[phone-reg] 注册状态机启动")
    last_state = ""
    unknown_seen = 0
    for step in range(180):
        snapshot = _classify_page(page, phase="register", ctx=ctx)
        state = snapshot.state
        if state.value != last_state:
            logger.info("[phone-reg] register state=%s URL=%s", state.value, snapshot.url[:120])
            last_state = state.value
        if state != PageState.UNKNOWN:
            unknown_seen = 0
        try:
            if state == PageState.CLOUDFLARE_BLOCKED:
                _raise_if_blocking_challenge(
                    page,
                    stage="phone register state machine",
                    screenshot_path="/tmp/phone_reg_cloudflare_challenge.png",
                )
                _fail_state(page, snapshot, "遇到 Cloudflare/人机验证", "phone_reg_cloudflare_state.png")
            if state == PageState.CHATGPT_HOME:
                _handle_chatgpt_home_signup(page, ctx, snapshot)
                continue
            if state == PageState.AUTH_METHOD_PICKER:
                if not _click_phone_entry(page):
                    _fail_state(page, snapshot, "未找到手机号入口", "phone_reg_no_phone_entry.png")
                _wait_after_state_action(page, 1.5)
                continue
            if state == PageState.PHONE_NUMBER_FORM:
                err = _phone_form_error(page)
                if err:
                    _fail_state(page, snapshot, f"手机号提交失败: {err}", "phone_reg_phone_form_error.png")
                if _observing_action(ctx, "submit_phone"):
                    _wait_observing(ctx, "submit_phone", state)
                    continue
                if _action_attempts(ctx, "submit_phone") >= 2:
                    _fail_state(page, snapshot, "手机号提交后仍停留在手机号页", "phone_reg_phone_submit_stuck.png")
                _handle_phone_number_form(page, ctx, label="phone_input", action="submit_phone")
                continue
            if state == PageState.PASSWORD_FORM:
                err = _password_form_error(page)
                if err:
                    _fail_state(page, snapshot, f"密码提交失败: {err}", "phone_reg_password_error.png")
                if _observing_action(ctx, "submit_password"):
                    _wait_observing(ctx, "submit_password", state)
                    continue
                if _action_attempts(ctx, "submit_password") >= 2:
                    _fail_state(page, snapshot, "密码提交后仍停留在密码页", "phone_reg_password_submit_stuck.png")
                _maybe_fill_password_like_browser(page, ctx.password)
                _mark_action(ctx, "submit_password", ctx.timing.password_submit_observe_s)
                continue
            if state == PageState.PHONE_OTP_FORM:
                if not ctx.lease:
                    _fail_state(page, snapshot, "OTP 页缺手机号 lease", "phone_reg_otp_no_lease.png")
                if _observing_action(ctx, "submit_phone_otp"):
                    _wait_observing(ctx, "submit_phone_otp", state)
                    continue
                if _action_attempts(ctx, "submit_phone_otp") >= 2:
                    _fail_state(page, snapshot, "手机号 OTP 提交后仍停留在 OTP 页", "phone_reg_phone_otp_submit_stuck.png")
                if not ctx.phone_code:
                    logger.info("[phone-reg] 等待 Hero SMS OTP ...")
                    ctx.phone_code = _poll_phone_otp(ctx, stage="register")
                    logger.info("[phone-reg] 收到手机号 OTP lease=%s", ctx.lease.lease_id)
                _fill_phone_otp_like_browser(page, ctx.phone_code)
                _mark_action(ctx, "submit_phone_otp", ctx.timing.otp_submit_observe_s)
                continue
            if state == PageState.REG_EMAIL_FORM:
                logger.info("[phone-reg] 注册阶段看到邮箱输入页，尝试切换到手机号入口")
                if not _click_phone_entry(page):
                    _fail_state(
                        page,
                        snapshot,
                        "手机号注册阶段进入邮箱输入页，但未找到 Continue with phone",
                        "phone_reg_email_form_no_phone_entry.png",
                    )
                _wait_after_state_action(page, 1.5)
                continue
            if state == PageState.CONTACT_VERIFICATION:
                if _has_phone_otp_input(page):
                    if not ctx.lease:
                        _fail_state(page, snapshot, "contact-verification OTP 页缺手机号 lease", "phone_reg_contact_otp_no_lease.png")
                    if _observing_action(ctx, "submit_phone_otp"):
                        _wait_observing(ctx, "submit_phone_otp", state)
                        continue
                    if _action_attempts(ctx, "submit_phone_otp") >= 2:
                        _fail_state(page, snapshot, "手机号 OTP 提交后仍停留在 contact-verification", "phone_reg_contact_otp_submit_stuck.png")
                    if not ctx.phone_code:
                        logger.info("[phone-reg] 等待 Hero SMS OTP ...")
                        ctx.phone_code = _poll_phone_otp(ctx, stage="contact-verification")
                        logger.info("[phone-reg] 收到手机号 OTP lease=%s", ctx.lease.lease_id)
                    _fill_phone_otp_like_browser(page, ctx.phone_code)
                    _mark_action(ctx, "submit_phone_otp", ctx.timing.otp_submit_observe_s)
                    continue
                if _action_attempts(ctx, "submit_phone_otp") == 0:
                    if _action_attempts(ctx, "wait_contact_otp") == 0:
                        _mark_action(ctx, "wait_contact_otp", ctx.timing.otp_submit_observe_s)
                    if _observing_action(ctx, "wait_contact_otp"):
                        _wait_observing(ctx, "wait_contact_otp", state)
                        continue
                    else:
                        _fail_state(page, snapshot, "contact-verification 未出现手机号验证码输入框", "phone_reg_contact_no_otp.png")
                    continue
                if _observing_action(ctx, "submit_contact_verification"):
                    _wait_observing(ctx, "submit_contact_verification", state)
                    continue
                if _action_attempts(ctx, "submit_contact_verification") >= 2:
                    _fail_state(page, snapshot, "contact-verification 提交后仍停留在当前页", "phone_reg_contact_submit_stuck.png")
                _click_first(
                    page,
                    [
                        'button:has-text("Finish creating account")',
                        'button:has-text("Continue")',
                        'button:has-text("Next")',
                        'button:has-text("Try again")',
                        'button:has-text("Retry")',
                        'button[type="submit"]',
                        'a:has-text("Continue")',
                    ],
                    log_label="contact-verification 中转",
                )
                _mark_action(ctx, "submit_contact_verification", ctx.timing.about_submit_observe_s)
                _wait_after_state_action(page, 2)
                continue
            if state == PageState.ABOUT_YOU_FORM:
                if _observing_action(ctx, "submit_about_you"):
                    _wait_observing(ctx, "submit_about_you", state)
                    continue
                if _action_attempts(ctx, "submit_about_you") >= 2:
                    _fail_state(page, snapshot, "about-you 提交后仍停留在表单页", "phone_reg_about_submit_stuck.png")
                _maybe_fill_about_you(page, ctx.first_name, ctx.last_name)
                _mark_action(ctx, "submit_about_you", ctx.timing.about_submit_observe_s)
                _wait_after_state_action(page, 2)
                continue
            if state == PageState.CHATGPT_LOGGED_IN:
                logger.info("[phone-reg] ChatGPT 注册阶段完成，进入绑定邮箱阶段")
                return
            if state in (
                PageState.PLATFORM_LOGIN,
                PageState.PLATFORM_METHOD_PICKER,
                PageState.PLATFORM_PHONE_FORM,
                PageState.PLATFORM_EMAIL_FORM,
                PageState.PLATFORM_EMAIL_OTP_FORM,
                PageState.PLATFORM_BOUND,
            ):
                logger.info("[phone-reg] 注册阶段已进入 Platform，切换到绑定邮箱阶段")
                return
            if state == PageState.UNKNOWN:
                unknown_seen += 1
                if unknown_seen % 5 == 0:
                    _click_first(
                        page,
                        ['button:has-text("Continue")', 'button:has-text("Next")', 'button[type="submit"]'],
                        log_label="未知页中转",
                    )
                if unknown_seen >= 25:
                    _fail_state(page, snapshot, "注册状态机无法识别页面", "phone_reg_unknown_state.png")
                time.sleep(ctx.timing.observe_poll_s)
                continue
            unknown_seen = 0
            time.sleep(ctx.timing.observe_poll_s)
        except Exception as e:
            if _is_navigation_race(e):
                logger.info("[phone-reg] register state=%s 页面正在跳转，重新识别", state.value)
                _wait_after_state_action(page, 1)
                continue
            raise
    _fail_state(page, _classify_page(page, phase="register", ctx=ctx), "注册状态机超时", "phone_reg_state_timeout.png")


def _run_platform_bind_state_machine(page, ctx: PhoneFlowContext) -> str:
    if ctx.bound_email or ctx.result.get("email"):
        return str(ctx.bound_email or ctx.result.get("email") or "")
    if not ctx.lease:
        raise RuntimeError("绑定邮箱阶段缺手机号 lease")

    logger.info("[phone-reg] Platform 绑定邮箱状态机启动")
    page.goto("https://platform.openai.com/login", wait_until="domcontentloaded", timeout=60000)
    _raise_if_blocking_challenge(
        page,
        stage="opening platform login for email binding",
        screenshot_path="/tmp/phone_reg_platform_cloudflare_challenge.png",
    )
    time.sleep(2)

    last_state = ""
    unknown_seen = 0
    for step in range(160):
        snapshot = _classify_page(page, phase="platform", ctx=ctx)
        state = snapshot.state
        if state.value != last_state:
            logger.info("[phone-reg] platform state=%s URL=%s", state.value, snapshot.url[:120])
            last_state = state.value
        if state not in (PageState.UNKNOWN, PageState.PLATFORM_LOGIN, PageState.PLATFORM_METHOD_PICKER):
            unknown_seen = 0
        try:
            if state == PageState.CLOUDFLARE_BLOCKED:
                _raise_if_blocking_challenge(
                    page,
                    stage="platform bind email state machine",
                    screenshot_path="/tmp/phone_reg_platform_cloudflare_challenge.png",
                )
                _fail_state(page, snapshot, "Platform 遇到 Cloudflare/人机验证", "phone_reg_platform_cloudflare_state.png")
            if state in (PageState.PLATFORM_LOGIN, PageState.PLATFORM_METHOD_PICKER):
                if not _click_phone_entry(page):
                    unknown_seen += 1
                    if unknown_seen >= 20:
                        _fail_state(page, snapshot, "Platform 未找到 Continue with phone", "phone_reg_platform_no_phone_entry.png")
                    time.sleep(ctx.timing.observe_poll_s)
                else:
                    unknown_seen = 0
                    _wait_after_state_action(page, 1.5)
                continue
            if state == PageState.PLATFORM_PHONE_FORM:
                logger.info("[phone-reg] platform 手机号登录：填刚注册手机号")
                err = _phone_form_error(page)
                if err:
                    _fail_state(page, snapshot, f"Platform 手机号提交失败: {err}", "phone_reg_platform_phone_form_error.png")
                if _observing_action(ctx, "submit_platform_phone"):
                    _wait_observing(ctx, "submit_platform_phone", state)
                    continue
                if _action_attempts(ctx, "submit_platform_phone") >= 2:
                    _fail_state(page, snapshot, "Platform 手机号提交后仍停留在手机号页", "phone_reg_platform_phone_submit_stuck.png")
                _handle_phone_number_form(page, ctx, label="platform_phone_login", action="submit_platform_phone")
                ctx.platform_phone_submitted = True
                continue
            if state == PageState.PHONE_OTP_FORM:
                if _observing_action(ctx, "submit_phone_otp"):
                    _wait_observing(ctx, "submit_phone_otp", state)
                    continue
                if _action_attempts(ctx, "submit_phone_otp") >= 2:
                    _fail_state(page, snapshot, "手机号 OTP 提交后仍停留在 OTP 页", "phone_reg_platform_phone_otp_submit_stuck.png")
                if not ctx.phone_code:
                    ctx.phone_code = _poll_phone_otp(ctx, stage="platform")
                logger.info("[phone-reg] platform 手机号登录出现 OTP，使用手机号验证码")
                _fill_phone_otp_like_browser(page, ctx.phone_code)
                _mark_action(ctx, "submit_phone_otp", ctx.timing.otp_submit_observe_s)
                continue
            if state == PageState.PASSWORD_FORM:
                logger.info("[phone-reg] platform 手机号登录出现密码页")
                err = _password_form_error(page)
                if err:
                    _fail_state(page, snapshot, f"Platform 手机号密码登录失败: {err}", "phone_reg_platform_password_error.png")
                if _observing_action(ctx, "submit_password"):
                    _wait_observing(ctx, "submit_password", state)
                    continue
                if _action_attempts(ctx, "submit_password") >= 2:
                    _fail_state(page, snapshot, "密码提交后仍停留在密码页", "phone_reg_platform_password_submit_stuck.png")
                _maybe_fill_password_like_browser(page, ctx.password)
                _mark_action(ctx, "submit_password", ctx.timing.password_submit_observe_s)
                continue
            if state == PageState.PLATFORM_EMAIL_FORM:
                if not ctx.platform_phone_submitted:
                    logger.info("[phone-reg] platform 默认邮箱页，先切换到当前手机号登录")
                    if not _click_phone_entry(page):
                        _fail_state(page, snapshot, "Platform 尚未用手机号登录，拒绝直接输入邮箱", "phone_reg_platform_email_before_phone.png")
                    _wait_after_state_action(page, 1.5)
                    continue
                if _observing_action(ctx, "submit_platform_email"):
                    _wait_observing(ctx, "submit_platform_email", state)
                    continue
                if _action_attempts(ctx, "submit_platform_email") >= 2:
                    _fail_state(page, snapshot, "Platform 邮箱提交后仍停留在邮箱页", "phone_reg_platform_email_submit_stuck.png")
                if not ctx.bound_email:
                    ctx.bound_email = ctx.mail_provider.create_mailbox()
                    persona = getattr(ctx.mail_provider, "last_persona", None)
                    if not ctx.result.get("password") and persona is not None and getattr(persona, "password", ""):
                        ctx.result["password"] = persona.password
                    ctx.platform_email_issued_at = time.time()
                    logger.info("[phone-reg] platform 绑定邮箱: %s", ctx.bound_email)
                email_input = _visible_first(page, _email_identifier_selectors()) or _wait_for_any(
                    page,
                    _email_identifier_selectors(),
                    timeout_s=30,
                    label="platform_email",
                )
                _fill_input_and_continue(page, email_input, ctx.bound_email, label="platform email")
                _mark_action(ctx, "submit_platform_email", ctx.timing.platform_email_submit_observe_s)
                continue
            if state == PageState.PLATFORM_EMAIL_OTP_FORM:
                if ctx.platform_email_submitted:
                    _wait_platform_email_binding_complete(page, ctx)
                    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
                    return ctx.bound_email
                if not ctx.bound_email:
                    _fail_state(page, snapshot, "Platform 邮箱 OTP 页缺绑定邮箱", "phone_reg_platform_otp_no_email.png")
                if _observing_action(ctx, "submit_platform_email_otp"):
                    _wait_observing(ctx, "submit_platform_email_otp", state)
                    continue
                if _action_attempts(ctx, "submit_platform_email_otp") >= 2:
                    _fail_state(page, snapshot, "Platform 邮箱 OTP 提交后仍停留在 OTP 页", "phone_reg_platform_email_otp_submit_stuck.png")
                ctx.platform_email_code = _submit_email_otp_with_retry(
                    page,
                    ctx.mail_provider,
                    ctx.bound_email,
                    ctx.platform_email_issued_at or time.time(),
                    label="platform_email",
                )
                _mark_action(ctx, "submit_platform_email_otp", ctx.timing.otp_submit_observe_s)
                ctx.platform_email_submitted = True
                _wait_platform_email_binding_complete(page, ctx)
                logger.info("[phone-reg] platform 邮箱验证码已提交并完成页面加载，回到 ChatGPT 收集 session")
                page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
                return ctx.bound_email
            if state in (PageState.PLATFORM_BOUND, PageState.CHATGPT_LOGGED_IN):
                if not ctx.bound_email:
                    _fail_state(page, snapshot, "Platform 未完成邮箱绑定", "phone_reg_platform_no_bound_email.png")
                page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
                return ctx.bound_email
            if state == PageState.UNKNOWN:
                unknown_seen += 1
                if ctx.platform_email_submitted:
                    _wait_platform_email_binding_complete(page, ctx)
                    page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
                    return ctx.bound_email
                if unknown_seen % 5 == 0:
                    _click_first(
                        page,
                        ['button:has-text("Continue")', 'button:has-text("Next")', 'button[type="submit"]'],
                        log_label="platform 未知页中转",
                    )
                if unknown_seen >= 30:
                    _fail_state(page, snapshot, "Platform 绑定邮箱状态机无法识别页面", "phone_reg_platform_unknown_state.png")
                time.sleep(ctx.timing.observe_poll_s)
                continue
            unknown_seen = 0
            time.sleep(ctx.timing.observe_poll_s)
        except Exception as e:
            if _is_navigation_race(e):
                logger.info("[phone-reg] platform state=%s 页面正在跳转，重新识别", state.value)
                _wait_after_state_action(page, 1)
                continue
            raise
    _fail_state(page, _classify_page(page, phase="platform", ctx=ctx), "Platform 绑定邮箱状态机超时", "phone_reg_platform_timeout.png")
    return ctx.bound_email


def phone_register(cfg, mail_provider) -> dict:
    from camoufox.sync_api import Camoufox
    from browserforge.fingerprints import Screen

    try:
        cfg.phone.enabled = True
    except Exception:
        pass
    provider = PhoneProvider.from_config(cfg.phone)
    cf_proxy = _parse_proxy(cfg.proxy)
    headless = _camoufox_headless()
    tmp_profile = tempfile.mkdtemp(prefix="chatgpt_phone_reg_")
    success = False
    first_name, last_name = _gen_name()
    password = _gen_password()
    logger.info("[phone-reg] Camoufox headless=%s", headless)

    result = {
        "email": "",
        "password": password,
        "session_token": "",
        "access_token": "",
        "device_id": "",
        "csrf_token": "",
        "id_token": "",
        "refresh_token": "",
        "cookie_header": "",
        "register_method": "phone_browser",
        "phone_number": "",
        "phone_dial_code": "",
        "phone_country": str(getattr(cfg.phone, "country", "") or ""),
    }
    flow_ctx = PhoneFlowContext(
        provider=provider,
        mail_provider=mail_provider,
        result=result,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

    try:
        with Camoufox(
            headless=headless,
            humanize=True,
            persistent_context=True,
            user_data_dir=tmp_profile,
            os="windows",
            screen=Screen(max_width=1920, max_height=1080),
            proxy=cf_proxy,
            geoip=True,
            locale="en-US",
        ) as browser_ctx:
            page = browser_ctx.pages[0] if browser_ctx.pages else browser_ctx.new_page()
            _install_phone_trace(page)
            logger.info("[phone-reg] 打开 ChatGPT 首页 ...")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            _raise_if_blocking_challenge(page, stage="opening ChatGPT home", screenshot_path="/tmp/phone_reg_cloudflare_challenge.png")

            _run_register_state_machine(page, flow_ctx)
            if not flow_ctx.bound_email and not result.get("email"):
                flow_ctx.bound_email = _run_platform_bind_state_machine(page, flow_ctx)
            _wait_and_collect_session(page, browser_ctx, result, bound_email=flow_ctx.bound_email)
            _validate_phone_result_before_return(result, bound_email=flow_ctx.bound_email)
            if not flow_ctx.lease:
                raise RuntimeError("手机号注册完成但缺 lease")
            provider.mark_verified(flow_ctx.lease.lease_id)
            _mark_email_used(mail_provider, result.get("email") or flow_ctx.bound_email)
            success = True
            logger.info("[phone-reg] 注册完成 email=%s", result.get("email"))
    finally:
        if not success:
            _cleanup_failed_phone_flow(flow_ctx, reason="phone_register_failed")
        try:
            shutil.rmtree(tmp_profile, ignore_errors=True)
        except Exception:
            pass

    return result
