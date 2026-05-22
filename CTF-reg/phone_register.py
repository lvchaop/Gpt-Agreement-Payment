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
from typing import Any

from browser_register import _camoufox_headless, _gen_name, _parse_proxy, _raise_if_blocking_challenge
from phone_provider import PhoneLease, PhoneProvider

logger = logging.getLogger(__name__)


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
        'input[autocomplete="username"]',
        'input[id*="email" i]',
        'input[placeholder*="email" i]',
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
                if el.is_visible():
                    return True
            except Exception:
                continue
    return False


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
    if len(dial_code) >= 2:
        return bool(re.search(rf"(^|[^0-9]){re.escape(dial_code)}($|[^0-9])", compact))
    return False


def _select_popup_country(page, dial_code: str) -> bool:
    if not dial_code:
        return False
    wanted = f"+{dial_code}"
    search_terms = [wanted, f"+({dial_code})", f"({dial_code})"]
    if len(dial_code) >= 2:
        search_terms.append(dial_code)

    def _click_visible_country_option() -> bool:
        try:
            clicked = page.evaluate(
                """({ dialCode, terms }) => {
                    const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const cs = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden';
                    };
                    const matchesDial = (text) => {
                        const compact = String(text || '').replace(/\\s+/g, '');
                        if (!compact) return false;
                        if (terms.some(term => compact.includes(term))) return true;
                        if (dialCode.length >= 2) {
                            return new RegExp(`(^|[^0-9])${dialCode}($|[^0-9])`).test(compact);
                        }
                        return false;
                    };
                    const selector = [
                        '[data-option-id]',
                        '[role="option"]',
                        '[role="menuitem"]',
                        '[data-radix-collection-item]',
                        '[cmdk-item]',
                        'button',
                        'li',
                        'div',
                        'span'
                    ].join(',');
                    const nodes = Array.from(document.querySelectorAll(selector));
                    const matches = [];
                    for (const el of nodes) {
                        if (!visible(el)) continue;
                        const text = (el.innerText || el.textContent || '').trim();
                        const optionId = el.getAttribute('data-option-id') || '';
                        if (!matchesDial(`${optionId} ${text}`)) continue;
                        const clickable = el.closest(
                            '[data-option-id],[role="option"],[role="menuitem"],[data-radix-collection-item],[cmdk-item],button,[role="button"],li'
                        ) || el;
                        if (!visible(clickable)) continue;
                        const role = clickable.getAttribute('role') || '';
                        const specific = clickable.hasAttribute('data-option-id')
                            || role === 'option' || role === 'menuitem'
                            || clickable.hasAttribute('data-radix-collection-item')
                            || clickable.hasAttribute('cmdk-item')
                            || clickable.tagName === 'BUTTON'
                            || clickable.tagName === 'LI';
                        const r = clickable.getBoundingClientRect();
                        matches.push({
                            el: clickable,
                            text: (clickable.innerText || clickable.textContent || text).trim(),
                            score: (clickable.hasAttribute('data-option-id') ? -1000000 : 0)
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
                {"dialCode": dial_code, "terms": search_terms},
            )
            if clicked:
                logger.info("[phone-reg] 选择手机号国家: %s -> %s", wanted, str(clicked)[:100])
                time.sleep(0.5)
                return True
        except Exception:
            return False
        return False

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
                if _click_visible_country_option():
                    return True
                search = _visible_first(page, [
                    'input[placeholder*="Search" i]',
                    'input[aria-label*="Search" i]',
                    'input[type="search"]',
                    'input[role="combobox"]',
                ])
                if search:
                    for term in search_terms:
                        try:
                            search.fill(term)
                        except Exception:
                            continue
                        time.sleep(0.5)
                        if _click_visible_country_option():
                            return True
                for opt_sel in [
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
                            time.sleep(0.5)
                            return True
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
    if _select_native_country(page, dial_code) or _select_popup_country(page, dial_code):
        return
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
    for sel in [
        'input[autocomplete="one-time-code"]',
        'input[name="code"]',
        'input[inputmode="numeric"]',
    ]:
        if page.query_selector(sel):
            return True
    return False


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
    el.click(timeout=5000)
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
    try:
        otp_timeout = max(30, int(os.getenv("OTP_TIMEOUT", str(getattr(mail_provider, "otp_timeout", 180) or 180))))
    except Exception:
        otp_timeout = 180
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
    try:
        otp_timeout = max(30, int(os.getenv("OTP_TIMEOUT", str(getattr(mail_provider, "otp_timeout", 180) or 180))))
    except Exception:
        otp_timeout = 180
    code = mail_provider.wait_for_otp(email, timeout=otp_timeout, issued_after=issued_at)
    if otp_box:
        _fill_otp(page, code, label="platform_email")
    result["email"] = email
    time.sleep(4)
    logger.info("[phone-reg] platform 邮箱验证码已提交，回到 ChatGPT 收集 session")
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
    if not result.get("session_token"):
        page.screenshot(path="/tmp/phone_reg_missing_session_token.png")
        raise RuntimeError("手机号注册完成但缺 session_token")
    return session_info


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
    lease: PhoneLease | None = None
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
        ) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            logger.info("[phone-reg] 打开 ChatGPT 首页 ...")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            _raise_if_blocking_challenge(page, stage="opening ChatGPT home", screenshot_path="/tmp/phone_reg_cloudflare_challenge.png")

            phone_input = _wait_for_signup_phone_input(page)
            lease = provider.allocate()
            result["phone_number"] = _national_phone_from_lease(lease)
            result["phone_dial_code"] = lease.country_phone_code or ""
            logger.info(
                "[phone-reg] 分配手机号 lease=%s phone=%s national=%s country=+%s",
                lease.lease_id,
                lease.masked_phone,
                PhoneProvider._mask_phone(lease.phone_national or ""),
                lease.country_phone_code or "",
            )
            _fill_phone_number_and_continue(page, phone_input, lease)

            _maybe_fill_password_like_browser(page, password)
            _wait_antifraud_like_browser(page)
            try:
                has_phone_otp = _has_phone_otp_input(page)
            except Exception as e:
                if not _is_navigation_race(e):
                    raise
                time.sleep(1)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                has_phone_otp = _has_phone_otp_input(page)
            if has_phone_otp:
                logger.info("[phone-reg] 等待 Hero SMS OTP ...")
                phone_code = provider.poll_otp(lease.lease_id)
                logger.info("[phone-reg] 收到手机号 OTP lease=%s", lease.lease_id)
                _fill_phone_otp_like_browser(page, phone_code)

            bound_email = _maybe_bind_email(page, mail_provider, result=result)
            _maybe_fill_about_you(page, first_name, last_name)
            if not bound_email and not result.get("email"):
                bound_email = _bind_email_via_platform(page, mail_provider, lease, result=result)
            _wait_and_collect_session(page, ctx, result, bound_email=bound_email)
            provider.mark_verified(lease.lease_id)
            success = True
            logger.info("[phone-reg] 注册完成 email=%s", result.get("email"))
    finally:
        if lease and not success:
            try:
                provider.mark_failed(lease.lease_id, "phone_register_failed")
                if getattr(provider, "provider", "") != "hero_sms":
                    provider.release(lease.lease_id)
            except Exception:
                pass
        try:
            shutil.rmtree(tmp_profile, ignore_errors=True)
        except Exception:
            pass

    return result
