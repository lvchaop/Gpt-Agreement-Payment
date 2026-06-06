"""Camoufox fallback for Outlook/Live account registration.

This module is intentionally scoped to the portal_protocol lane.  It keeps the
pure HTTP path as the fast path and only drives a real browser when Live returns
PerimeterX/HIP/Arkose-style challenges.
"""
from __future__ import annotations

import logging
import os
import random
import shutil
import string
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from config import Config
from browser_register import _camoufox_headless, _parse_proxy
from portal_identity import generate_password, next_username

logger = logging.getLogger(__name__)


FIRST_NAMES = [
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
]
LAST_NAMES = [
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
]


@dataclass
class OutlookBrowserResult:
    email: str
    password: str
    username_seq: int = 0
    challenge_reason: str = ""
    mail_oauth_client_id: str = ""
    mail_access_token: str = ""
    mail_refresh_token: str = ""
    mail_oauth_scope: str = ""

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "password": self.password,
            "session_token": "",
            "access_token": "",
            "device_id": "",
            "csrf_token": "",
            "id_token": "",
            "refresh_token": "",
            "cookie_header": "",
            "register_method": "portal_browser",
            "portal_username_seq": self.username_seq,
            "portal_final_url": "",
            "portal_oauth_code_captured": False,
            "portal_browser_challenge_reason": self.challenge_reason,
            "mail_oauth_client_id": self.mail_oauth_client_id,
            "mail_account_id": self.mail_oauth_client_id,
            "mail_access_token": self.mail_access_token,
            "mail_refresh_token": self.mail_refresh_token,
            "mail_oauth_scope": self.mail_oauth_scope,
        }


def _cfg_value(cfg: Config, key: str, default: Any = "") -> Any:
    portal = getattr(cfg, "portal_protocol", None)
    if portal is None:
        return default
    return getattr(portal, key, default)


def _project_base_dir() -> Path:
    cwd = Path(os.getcwd()).resolve()
    if cwd.name == "CTF-reg":
        return cwd.parent
    return cwd


def _make_email(cfg: Config) -> tuple[str, int]:
    account_domain = str(_cfg_value(cfg, "account_domain", "outlook.com") or "outlook.com").strip().lstrip("@").lower()
    namespace = str(_cfg_value(cfg, "namespace", "portal-live") or "portal-live")
    state_path = str(_cfg_value(cfg, "state_path", "output/portal_identity_state.json") or "")
    username, seq = next_username(state_path, namespace=namespace, length=12, base_dir=_project_base_dir())
    return f"{username}@{account_domain}", seq


def _birth_parts() -> tuple[str, str, str]:
    year = random.randint(1985, 2000)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return str(year), str(month), str(day)


def _artifact_dir() -> Path:
    path = _project_base_dir() / "output" / "outlook_browser"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _click_first(page, selectors: list[str], *, timeout: int = 3000) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=500):
                loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def _fill_first(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=500):
                loc.evaluate(
                    """(el, value) => {
                      el.focus();
                      const proto = Object.getPrototypeOf(el);
                      const desc = Object.getOwnPropertyDescriptor(proto, 'value');
                      if (desc && desc.set) desc.set.call(el, value);
                      else el.value = value;
                      el.dispatchEvent(new Event('input', {bubbles: true}));
                      el.dispatchEvent(new Event('change', {bubbles: true}));
                      el.dispatchEvent(new Event('blur', {bubbles: true}));
                    }""",
                    value,
                )
                return True
        except Exception:
            continue
    return False


def _wait_for_any(page, selectors: list[str], *, timeout_s: float = 30.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        page.wait_for_timeout(1000)
    return False


def _fill_name_page(page, *, first_name: str, last_name: str) -> bool:
    first_ok = _fill_first(
        page,
        [
            'input[name="FirstName"]',
            "#FirstName",
            'input[id*="first" i]',
            'input[placeholder*="first" i]',
            'input[aria-label*="first" i]',
            'input[aria-label*="名" i]',
        ],
        first_name,
    )
    last_ok = _fill_first(
        page,
        [
            'input[name="LastName"]',
            "#LastName",
            'input[id*="last" i]',
            'input[placeholder*="last" i]',
            'input[aria-label*="last" i]',
            'input[aria-label*="姓" i]',
        ],
        last_name,
    )
    if first_ok or last_ok:
        logger.info("[outlook-browser] name page filled first=%s last=%s", first_ok, last_ok)
        _click_first(page, ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]', 'button:has-text("Next")'])
        page.wait_for_timeout(3000)
        return True
    return False


def _body_text(page) -> str:
    try:
        return page.inner_text("body", timeout=2500)
    except Exception:
        return ""


def _is_success_page(page) -> bool:
    url = str(getattr(page, "url", "") or "").lower()
    text = _body_text(page).lower()
    if "signup.live.com" not in url and ("live.com" in url or "outlook" in url):
        return True
    return any(
        marker in text
        for marker in (
            "account has been created",
            "welcome",
            "inbox",
            "your account is ready",
            "帐户已创建",
        )
    )


def _is_blocked(page) -> bool:
    text = _body_text(page).lower()
    return any(
        marker in text
        for marker in (
            "account creation has been blocked",
            "has been blocked",
            "account has been suspended",
            "unusual activity",
            "帐户创建已被阻止",
            "异常活动",
        )
    )


def _press_and_hold(page, *, max_press: int = 2) -> bool:
    for attempt in range(1, max_press + 1):
        target_box = None
        for sel in [
            'button:has-text("Press and hold")',
            'button:has-text("按住")',
            'button:has-text("长按")',
            'button:has-text("Appuyer et maintenir")',
            "#px-captcha",
        ]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    box = loc.bounding_box()
                    if box and box["width"] > 30 and box["height"] > 10:
                        target_box = box
                        break
            except Exception:
                continue
        if not target_box:
            try:
                frames = page.locator('iframe[src*="hsprotect.net"]')
                for idx in range(frames.count()):
                    box = frames.nth(idx).bounding_box()
                    if box and box["width"] > 50 and box["height"] > 30:
                        target_box = box
                        break
            except Exception:
                pass
        if not target_box:
            return False

        bx, by, bw, bh = target_box["x"], target_box["y"], target_box["width"], target_box["height"]
        cx = bx + bw * random.uniform(0.35, 0.65)
        cy = by + bh * random.uniform(0.4, 0.7)
        sx = random.uniform(150, 800)
        sy = random.uniform(150, 500)
        page.mouse.move(sx, sy)
        time.sleep(random.uniform(0.2, 0.6))
        steps = random.randint(16, 30)
        ctrl_x = (sx + cx) / 2 + random.uniform(-90, 90)
        ctrl_y = (sy + cy) / 2 + random.uniform(-70, 70)
        for step in range(1, steps + 1):
            t = step / steps
            mx = (1 - t) ** 2 * sx + 2 * (1 - t) * t * ctrl_x + t**2 * cx + random.uniform(-1.3, 1.3)
            my = (1 - t) ** 2 * sy + 2 * (1 - t) * t * ctrl_y + t**2 * cy + random.uniform(-1.3, 1.3)
            page.mouse.move(mx, my)
            time.sleep(random.uniform(0.005, 0.025))
        page.mouse.down()
        hold_s = random.uniform(9.0, 12.0)
        end = time.time() + hold_s
        while time.time() < end:
            page.mouse.move(cx + random.uniform(-0.8, 0.8), cy + random.uniform(-0.8, 0.8))
            time.sleep(random.uniform(0.08, 0.25))
        page.mouse.up()
        logger.info("[outlook-browser] press-and-hold attempt=%s hold_s=%.1f", attempt, hold_s)
        end_wait = time.time() + 18
        while time.time() < end_wait:
            text = _body_text(page).lower()
            if _is_success_page(page) or "press and hold" not in text:
                return True
            page.wait_for_timeout(1000)
    return False


def _captcha_api_base(cfg: Config) -> str:
    captcha = getattr(cfg, "captcha", None)
    return str(getattr(captcha, "api_url", "") or "").rstrip("/")


def _captcha_client_key(cfg: Config) -> str:
    captcha = getattr(cfg, "captcha", None)
    return str(getattr(captcha, "client_key", "") or "")


def _solve_with_project_captcha(cfg: Config, page_url: str) -> dict | str | None:
    api_url = _captcha_api_base(cfg)
    client_key = _captcha_client_key(cfg)
    if not api_url or not client_key:
        return None
    task_variants = [
        {"type": "PerimeterX", "websiteURL": page_url, "websiteKey": "PXzC5j78di"},
        {"type": "AntiPerimeterXTaskProxyless", "websiteURL": page_url},
    ]
    for task in task_variants:
        try:
            create = requests.post(
                f"{api_url}/createTask",
                json={"clientKey": client_key, "task": task},
                timeout=30,
            )
            data = create.json()
            if data.get("errorId", 0) not in (0, "0", None) or not data.get("taskId"):
                continue
            task_id = data["taskId"]
            deadline = time.time() + 90
            while time.time() < deadline:
                time.sleep(5)
                result = requests.post(
                    f"{api_url}/getTaskResult",
                    json={"clientKey": client_key, "taskId": task_id},
                    timeout=30,
                ).json()
                if result.get("status") == "ready":
                    return result.get("solution") or result
                if result.get("status") == "failed":
                    break
        except Exception as e:
            logger.debug("[outlook-browser] captcha provider task=%s failed: %s", task.get("type"), e)
    return None


def _apply_captcha_solution(ctx, page, solution: dict | str | None) -> bool:
    if not solution:
        return False
    if isinstance(solution, dict):
        cookies = []
        for key in ("_px2", "_pxhd", "_pxCaptcha", "_px3", "_pxvid", "_pxde"):
            if solution.get(key):
                cookies.append({"name": key, "value": str(solution[key]), "domain": ".live.com", "path": "/"})
        if cookies:
            try:
                ctx.add_cookies(cookies)
                page.reload(wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                return True
            except Exception:
                return False
        token = solution.get("token") or solution.get("uuid") or solution.get("captchaToken")
    else:
        token = solution
    if not token:
        return False
    try:
        injected = page.evaluate(
            """
            token => {
              const hidden = document.querySelector('input[name="fc-token"], input[name="FunCaptcha"]');
              if (hidden) { hidden.value = token; return "hidden"; }
              if (typeof window.fcCallback === 'function') { window.fcCallback(token); return "callback"; }
              if (typeof window.CE_READY === 'function') { window.CE_READY(token); return "ce_ready"; }
              return "";
            }
            """,
            str(token),
        )
        return bool(injected)
    except Exception:
        return False


def _handle_challenge(cfg: Config, ctx, page, *, early_abort: bool = True) -> bool:
    max_press_raw = os.environ.get("OUTLOOK_REG_MAX_PRESS", "").strip()
    max_press = int(max_press_raw) if max_press_raw.isdigit() else 2
    if _press_and_hold(page, max_press=max_press):
        return True
    solution = _solve_with_project_captcha(cfg, str(getattr(page, "url", "") or "https://signup.live.com/"))
    if _apply_captcha_solution(ctx, page, solution):
        return True
    return not early_abort


def _target_country_options(cfg: Config) -> list[str]:
    meta_root = getattr(cfg, "proxy_meta", {}) or {}
    meta = meta_root.get("register") if isinstance(meta_root, dict) else {}
    country = ""
    if isinstance(meta, dict):
        country = str(meta.get("region") or "").strip().upper()
    country = country or str(_cfg_value(cfg, "country", "") or "").strip().upper()
    if country == "JP":
        return ["Japan", "日本", "Japon", "JP"]
    if country in ("US", ""):
        return ["United States", "美国", "États-Unis", "US"]
    return [country]


def _fill_birthday(page, cfg: Config) -> None:
    year, month, day = _birth_parts()
    month_i = int(month)
    month_names_en = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    month_names_cn = ["", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]
    month_names_fr = [
        "",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]

    def select_combo_option(combo, candidates: list[str]) -> bool:
        try:
            combo.click(force=True)
            page.wait_for_timeout(500)
            options = page.locator('[role="option"]')
            count = options.count()
            lowered = {c.lower() for c in candidates if c}
            for idx in range(count):
                opt = options.nth(idx)
                text = (opt.text_content() or "").strip()
                if text.lower() in lowered:
                    opt.click(timeout=3000)
                    page.wait_for_timeout(500)
                    return True
            for candidate in candidates:
                if not candidate:
                    continue
                opt = page.locator(f'[role="option"]:has-text("{candidate}")').first
                if opt.count() > 0:
                    opt.click(timeout=3000)
                    page.wait_for_timeout(500)
                    return True
            try:
                page.evaluate(
                    """label => {
                      const options = [...document.querySelectorAll('[role="option"]')];
                      const target = options.find(o => (o.textContent || '').trim().toLowerCase() === String(label).toLowerCase());
                      if (target) {
                        target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        target.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        target.click();
                      }
                    }""",
                    candidates[0],
                )
            except Exception:
                page.keyboard.type(candidates[0])
                page.keyboard.press("Enter")
            page.wait_for_timeout(500)
            return True
        except Exception as e:
            logger.debug("[outlook-browser] combo option select failed candidates=%s error=%s", candidates, e)
            return False

    selects = page.locator("select")
    if selects.count() >= 2:
        if selects.count() >= 3:
            try:
                selects.nth(0).select_option("US")
            except Exception:
                try:
                    selects.nth(0).select_option(index=1)
                except Exception:
                    pass
            selects.nth(1).select_option(month)
            selects.nth(2).select_option(day)
        else:
            selects.nth(0).select_option(month)
            selects.nth(1).select_option(day)
    else:
        combos = page.locator('button[role="combobox"], [role="combobox"]')
        month_filled = False
        day_filled = False
        country_filled = False
        for idx in range(min(combos.count(), 4)):
            combo = combos.nth(idx)
            label = " ".join(
                str(combo.get_attribute(attr) or "") for attr in ("aria-label", "id")
            ).lower()
            text = (combo.text_content() or "").strip().lower()
            is_month = "month" in label or "月" in label or text in ("month", "月")
            is_day = "day" in label or "日" in label or text in ("day", "日")
            is_country = "country" in label or "region" in label
            if is_month and is_day:
                if "month" in label:
                    is_day = False
                elif "day" in label:
                    is_month = False
            if is_country and not country_filled:
                country_filled = select_combo_option(combo, _target_country_options(cfg))
                logger.info("[outlook-browser] birthday country_filled=%s", country_filled)
                continue
            if is_month and not month_filled:
                month_filled = select_combo_option(
                    combo,
                    [month_names_en[month_i], month_names_cn[month_i], month_names_fr[month_i], month],
                )
                logger.info("[outlook-browser] birthday month=%s filled=%s", month, month_filled)
                continue
            if is_day and not day_filled:
                day_filled = select_combo_option(combo, [day, f"{day}日"])
                logger.info("[outlook-browser] birthday day=%s filled=%s", day, day_filled)
                continue
    _fill_first(
        page,
        [
            "#BirthYearInput",
            '[aria-label*="year" i]',
            '[aria-label*="年" i]',
            '[id*="Year" i]',
            'input[type="text"][inputmode="numeric"]',
            'input[type="number"]',
        ],
        year,
    )
    logger.info("[outlook-browser] birthday year=%s filled", year)


def _register_in_context(cfg: Config, ctx, page, *, email: str, password: str, challenge_reason: str) -> OutlookBrowserResult:
    artifacts = _artifact_dir()
    prefix = email.split("@", 1)[0]
    first_name = str(_cfg_value(cfg, "first_name", "") or random.choice(FIRST_NAMES))
    last_name = str(_cfg_value(cfg, "last_name", "") or random.choice(LAST_NAMES))

    page.goto("https://signup.live.com/signup?lic=1", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    try:
        page.screenshot(path=str(artifacts / "outlook_browser_start.png"))
    except Exception:
        pass

    for _ in range(5):
        text = _body_text(page).lower()
        url = str(getattr(page, "url", "") or "").lower()
        if "privacynotice" in url or any(k in text for k in ("agree and continue", "同意并继续", "data export")):
            _click_first(
                page,
                [
                    'button:has-text("Agree and continue")',
                    'button:has-text("Accept")',
                    'button:has-text("Continue")',
                    'button:has-text("同意并继续")',
                    "#iNext",
                    "#iAgree",
                    "#acceptButton",
                ],
            )
            page.wait_for_timeout(2500)
        else:
            break

    logger.info("[outlook-browser] registering email=%s challenge_reason=%s", email, challenge_reason or "<none>")
    email_selectors = [
        'input[type="email"]',
        'input[name="MemberName"]',
        "#MemberName",
        "#usernameInput",
        'input[name="Username"]',
    ]
    if not _wait_for_any(page, email_selectors, timeout_s=30):
        logger.warning("[outlook-browser] email input not visible after initial wait, reloading url=%s", getattr(page, "url", ""))
        try:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
        except Exception:
            pass
    if not _wait_for_any(page, email_selectors, timeout_s=15):
        try:
            page.screenshot(path=str(artifacts / "outlook_browser_no_email_input.png"))
        except Exception:
            pass
        raise RuntimeError("Outlook browser fallback: email input not found")
    if not _fill_first(
        page,
        email_selectors,
        prefix,
    ):
        raise RuntimeError("Outlook browser fallback: email input not found")
    domain = page.locator("#LiveDomainBoxList, select[name='LiveDomainBoxList']").first
    if domain.count() > 0:
        try:
            domain.select_option("outlook.com")
        except Exception:
            pass
    elif "@" not in (page.locator('input[type="email"], input[name="MemberName"], #MemberName').first.input_value() or ""):
        _fill_first(page, ['input[type="email"]', 'input[name="MemberName"]', "#MemberName"], email)
    _click_first(page, ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]'])
    page.wait_for_timeout(3000)

    if not _fill_first(
        page,
        ['input[type="password"]', 'input[name="Password"]', "#PasswordInput", 'input[name="passwd"]'],
        password,
    ):
        raise RuntimeError("Outlook browser fallback: password input not found")
    _click_first(
        page,
        ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]', 'button:has-text("Next")', 'button:has-text("下一步")'],
    )
    page.wait_for_timeout(3000)

    _fill_birthday(page, cfg)
    _click_first(
        page,
        ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]', 'button:has-text("Next")', 'button:has-text("下一步")'],
    )
    page.wait_for_timeout(3000)

    # Optional gamertag/display name page.
    text = _body_text(page).lower()
    if any(k in text for k in ("gamertag", "display name", "用户名", "游戏")):
        handle = prefix[:10] + "".join(random.choices(string.digits, k=3))
        _fill_first(page, ['input[type="text"]', 'input[id*="displayName"]', 'input[id*="gamertag"]'], handle)
        _click_first(page, ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]', 'button:has-text("Next")'])
        page.wait_for_timeout(2500)

    # Optional first/last name page.
    _fill_name_page(page, first_name=first_name, last_name=last_name)

    deadline = time.time() + float(os.environ.get("OUTLOOK_BROWSER_TIMEOUT_S", "240") or 240)
    while time.time() < deadline:
        if _is_success_page(page):
            logger.info("[outlook-browser] success email=%s url=%s", email, getattr(page, "url", ""))
            return OutlookBrowserResult(email=email, password=password, challenge_reason=challenge_reason)
        if _is_blocked(page):
            try:
                page.screenshot(path=str(artifacts / "outlook_browser_blocked.png"))
            except Exception:
                pass
            logger.warning("[outlook-browser] blocked email=%s url=%s text=%s", email, getattr(page, "url", ""), _body_text(page)[:300])
            raise RuntimeError("Outlook browser fallback: account creation blocked")
        text = _body_text(page).lower()
        url = str(getattr(page, "url", "") or "").lower()
        if "add your name" in text or "enter your first name" in text or "enter your last name" in text:
            _fill_name_page(page, first_name=first_name, last_name=last_name)
            continue
        if any(
            k in text or k in url
            for k in (
                "captcha",
                "px-captcha",
                "hsprotect",
                "arkose",
                "funcaptcha",
                "hip",
                "prove you're human",
                "press and hold",
                "按住",
                "长按",
            )
        ):
            if not _handle_challenge(cfg, ctx, page, early_abort=True):
                raise RuntimeError("Outlook browser fallback: challenge not solved")
        _click_first(
            page,
            [
                'button:has-text("OK")',
                'button:has-text("Accept")',
                'button:has-text("Continue")',
                'button:has-text("Next")',
                'button:has-text("I agree")',
                'button:has-text("Got it")',
                'button:has-text("Skip")',
                'button:has-text("No thanks")',
                "#skipBtn",
            ],
            timeout=1500,
        )
        page.wait_for_timeout(3000)

    try:
        page.screenshot(path=str(artifacts / "outlook_browser_timeout.png"))
    except Exception:
        pass
    raise RuntimeError("Outlook browser fallback timed out")


def outlook_browser_register(
    cfg: Config,
    *,
    email: str = "",
    password: str = "",
    username_seq: int = 0,
    challenge_reason: str = "",
) -> dict:
    if not email:
        email, username_seq = _make_email(cfg)
    if not password:
        password = generate_password(12)

    proxy = _parse_proxy(str(getattr(cfg, "proxy", "") or "")) if getattr(cfg, "proxy", None) else None
    headless = _camoufox_headless()
    profile = tempfile.mkdtemp(prefix="outlook_browser_")
    logger.info("[outlook-browser] Camoufox headless=%s profile=%s proxy=%s", headless, profile, bool(proxy))

    from camoufox.sync_api import Camoufox
    try:
        from browserforge.fingerprints import Screen
    except ModuleNotFoundError:
        Screen = None
        logger.warning("[outlook-browser] browserforge 未安装，使用 Camoufox 默认 screen")

    camoufox_kwargs = {
        "headless": headless,
        "humanize": True,
        "persistent_context": True,
        "user_data_dir": profile,
        "os": "windows",
        "proxy": proxy,
        "geoip": True,
        "locale": "en-US",
    }
    if Screen is not None:
        camoufox_kwargs["screen"] = Screen(max_width=1920, max_height=1080)

    success = False
    try:
        with Camoufox(**camoufox_kwargs) as ctx:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            result = _register_in_context(
                cfg,
                ctx,
                page,
                email=email,
                password=password,
                challenge_reason=challenge_reason,
            )
            result.username_seq = username_seq
            if bool(_cfg_value(cfg, "mail_oauth_enabled", True)):
                from outlook_oauth import authorize_outlook_mailbox_browser

                mail_oauth = authorize_outlook_mailbox_browser(cfg, page, email=email, password=password)
                result.mail_oauth_client_id = mail_oauth.client_id
                result.mail_access_token = mail_oauth.access_token
                result.mail_refresh_token = mail_oauth.refresh_token
                result.mail_oauth_scope = mail_oauth.scope
            success = True
            return result.to_dict()
    finally:
        if success or str(os.environ.get("OUTLOOK_KEEP_BROWSER_PROFILE", "")).strip().lower() not in ("1", "true", "yes"):
            shutil.rmtree(profile, ignore_errors=True)
