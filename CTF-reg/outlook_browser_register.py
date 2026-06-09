"""Camoufox fallback for Outlook/Live account registration.

This module is intentionally scoped to the portal_protocol lane.  It keeps the
pure HTTP path as the fast path and only drives a real browser when Live returns
PerimeterX/HIP/Arkose-style challenges.
"""
from __future__ import annotations

import logging
import hashlib
import json
import os
import random
import re
import secrets
import shutil
import string
import tempfile
import time
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    portal_register_client_id: str = ""
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
            "portal_register_client_id": self.portal_register_client_id,
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


def _camoufox_geoip_enabled(proxy: dict | None) -> bool:
    if not proxy:
        return False
    server = str(proxy.get("server") or "").lower()
    return not (
        "://127.0.0.1" in server
        or "://localhost" in server
        or "://[::1]" in server
    )


def _camoufox_os_for_cfg(cfg: Config) -> str:
    override = str(os.environ.get("OUTLOOK_CAMOUFOX_OS", "") or "").strip().lower()
    if override in ("windows", "macos", "linux"):
        return override
    ua = str(_cfg_value(cfg, "user_agent", "") or "")
    if "Macintosh" in ua or "Mac OS X" in ua or "PKeyAuth/1.0" in ua:
        return "macos"
    if "Windows" in ua:
        return "windows"
    if "Linux" in ua or "X11" in ua:
        return "linux"
    return "macos"


def _camoufox_locale_for_cfg(cfg: Config) -> str:
    override = str(os.environ.get("OUTLOOK_CAMOUFOX_LOCALE", "") or "").strip()
    if override:
        return override
    return str(_cfg_value(cfg, "locale", "zh-CN") or "zh-CN")


def _browser_signup_authorize_url(cfg: Config) -> str:
    client_id = str(_cfg_value(cfg, "client_id", "00000000480728C5") or "00000000480728C5")
    locale = str(_cfg_value(cfg, "locale", "zh-CN") or "zh-CN")
    params = {
        "client_id": client_id,
        "scope": str(_cfg_value(cfg, "scope", "profile offline_access openid service::outlook.office.com::MBI_SSL")),
        "redirect_uri": str(_cfg_value(cfg, "redirect_uri", "https://login.live.com/oauth20_desktop.srf")),
        "response_type": "code",
        "x-client-SKU": str(_cfg_value(cfg, "x_client_sku", "MSAL.xplat.macOS")),
        "x-client-Ver": str(_cfg_value(cfg, "x_client_ver", "1.1.0+61e1eea1")),
        "uaid": secrets.token_hex(16),
        "msproxy": "1",
        "issuer": "mso",
        "tenant": "consumers",
        "ui_locales": locale,
        "client_info": "1",
        "fl": "easi2",
        "signup": "1",
        "lw": "1",
        "haschrome": "1",
        "noauthcancel": "1",
        "webauthn": "1",
    }
    return "https://login.live.com/oauth20_authorize.srf?" + urlencode(params)


def _safe_json_dumps(data: Any, *, limit: int = 4000) -> str:
    try:
        text = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    except Exception as e:
        text = json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
    return text[:limit]


def _collect_browser_fingerprint(page) -> dict:
    try:
        return page.evaluate(
            """
            () => {
              const nav = navigator;
              const out = {
                url: location.href,
                userAgent: nav.userAgent || '',
                platform: nav.platform || '',
                language: nav.language || '',
                languages: Array.from(nav.languages || []),
                webdriver: nav.webdriver,
                hardwareConcurrency: nav.hardwareConcurrency,
                deviceMemory: nav.deviceMemory,
                maxTouchPoints: nav.maxTouchPoints,
                cookieEnabled: nav.cookieEnabled,
                doNotTrack: nav.doNotTrack,
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || '',
                screen: {
                  width: screen.width,
                  height: screen.height,
                  availWidth: screen.availWidth,
                  availHeight: screen.availHeight,
                  colorDepth: screen.colorDepth,
                  pixelDepth: screen.pixelDepth,
                  devicePixelRatio: window.devicePixelRatio,
                  innerWidth: window.innerWidth,
                  innerHeight: window.innerHeight,
                  outerWidth: window.outerWidth,
                  outerHeight: window.outerHeight
                },
                plugins: Array.from(nav.plugins || []).map(p => p && p.name).filter(Boolean).slice(0, 20),
                mimeTypes: Array.from(nav.mimeTypes || []).map(m => m && m.type).filter(Boolean).slice(0, 20),
              };
              try {
                const canvas = document.createElement('canvas');
                canvas.width = 220;
                canvas.height = 40;
                const ctx = canvas.getContext('2d');
                ctx.textBaseline = 'top';
                ctx.font = '16px Arial';
                ctx.fillStyle = '#f60';
                ctx.fillRect(10, 10, 80, 20);
                ctx.fillStyle = '#069';
                ctx.fillText('outlook-fp-测试', 2, 2);
                out.canvasDataLen = canvas.toDataURL().length;
              } catch (e) {
                out.canvasError = String(e && e.message || e);
              }
              try {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                if (gl) {
                  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
                  out.webgl = {
                    vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
                    renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
                    version: gl.getParameter(gl.VERSION),
                    shadingLanguageVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION)
                  };
                } else {
                  out.webgl = null;
                }
              } catch (e) {
                out.webglError = String(e && e.message || e);
              }
              return out;
            }
            """
        ) or {}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _log_browser_evidence(page, *, label: str) -> None:
    fp = _collect_browser_fingerprint(page)
    logger.info("[outlook-browser] evidence fingerprint label=%s data=%s", label, _safe_json_dumps(fp))
    try:
        resp = page.context.request.get("https://api.ipify.org?format=json", timeout=15000)
        text = resp.text()[:500]
        logger.info(
            "[outlook-browser] evidence egress label=%s status=%s body=%s",
            label,
            getattr(resp, "status", ""),
            text,
        )
    except Exception as e:
        logger.info("[outlook-browser] evidence egress label=%s error=%s", label, f"{type(e).__name__}: {e}"[:300])


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


def _install_challenge_hooks(page) -> None:
    """Install lightweight in-page diagnostics for challenge state changes."""
    try:
        page.evaluate(
            """
            () => {
              if (window.__outlookChallengeHooked) return;
              window.__outlookChallengeHooked = true;
              window.__outlookChallengeLog = [];
              const push = (kind, data) => {
                try {
                  window.__outlookChallengeLog.push({
                    t: Math.round(performance.now()),
                    kind,
                    data
                  });
                  if (window.__outlookChallengeLog.length > 200) {
                    window.__outlookChallengeLog.splice(0, window.__outlookChallengeLog.length - 200);
                  }
                } catch (_) {}
              };
              for (const name of ['pointerdown','pointerup','pointermove','mousedown','mouseup','mousemove','click','touchstart','touchend']) {
                document.addEventListener(name, ev => {
                  const target = ev.target;
                  push('event', {
                    name,
                    trusted: ev.isTrusted,
                    x: ev.clientX || 0,
                    y: ev.clientY || 0,
                    tag: target && target.tagName,
                    id: target && target.id,
                    cls: target && target.className,
                    text: target && (target.innerText || target.textContent || '').slice(0, 80)
                  });
                }, true);
              }
              window.addEventListener('message', ev => {
                let data = ev.data;
                try {
                  if (typeof data === 'string') data = JSON.parse(data);
                } catch (_) {}
                push('message', {
                  origin: ev.origin || '',
                  dataType: typeof data,
                  data: typeof data === 'object' ? JSON.stringify(data) : String(data || '')
                });
              }, true);
              new MutationObserver(() => {
                const text = (document.body && document.body.innerText || '');
                push('mutation', { url: location.href, text });
              }).observe(document.documentElement, { childList: true, subtree: true, attributes: true });
              push('hooked', { url: location.href });
            }
            """
        )
    except Exception:
        pass


def _challenge_snapshot(page) -> dict:
    try:
        return page.evaluate(
            """
            () => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 5 && r.height > 5 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const candidates = [...document.querySelectorAll('button, [role=button], input[type=button], input[type=submit], #px-captcha, iframe')]
                .filter(visible)
                .map((el, idx) => {
                  const r = el.getBoundingClientRect();
                  return {
                    idx,
                    tag: el.tagName,
                    id: el.id || '',
                    cls: String(el.className || '').slice(0, 120),
                    role: el.getAttribute('role') || '',
                    aria: el.getAttribute('aria-label') || '',
                    text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 160),
                    src: el.getAttribute('src') || '',
                    rect: { x: r.x, y: r.y, width: r.width, height: r.height }
                  };
                });
              return {
                url: location.href,
                text: (document.body && document.body.innerText || '').slice(0, 500),
                candidates,
                log: window.__outlookChallengeLog || []
              };
            }
            """
        ) or {}
    except Exception:
        return {}


def _challenge_hook_status(page, *, since_t: float = 0) -> dict:
    try:
        return page.evaluate(
            """
            sinceT => {
              const log = window.__outlookChallengeLog || [];
              const out = {
                completed: false,
                failed: false,
                rendered: false,
                lastMessage: '',
                lastMessageTime: 0
              };
              for (const item of log) {
                if (!item || item.kind !== 'message') continue;
                if ((item.t || 0) <= sinceT) continue;
                const data = item.data && item.data.data || '';
                out.lastMessage = data;
                out.lastMessageTime = item.t || 0;
                if (data.includes('px-cookie-bridge-complete') || /"type"\\s*:\\s*"[^"]*(complete|success)[^"]*"/i.test(data)) {
                  out.completed = true;
                }
                if (/"type"\\s*:\\s*"failed"/i.test(data)) {
                  out.failed = true;
                }
                if (/"type"\\s*:\\s*"rendered"/i.test(data)) {
                  out.rendered = true;
                }
              }
              return out;
            }
            """,
            since_t,
        ) or {}
    except Exception:
        return {}


def _write_challenge_artifacts(page, *, label: str, attempt: int = 0) -> None:
    try:
        artifacts = _artifact_dir()
        prefix = f"challenge_{label}_{attempt}_{int(time.time())}"
        html_path = artifacts / f"{prefix}.html"
        json_path = artifacts / f"{prefix}.json"
        png_path = artifacts / f"{prefix}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        json_path.write_text(
            json.dumps(_challenge_snapshot(page), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        for idx, frame in enumerate(getattr(page, "frames", []) or []):
            frame_url = str(getattr(frame, "url", "") or "")
            if "iframe.hsprotect.net" not in frame_url:
                continue
            frame_html_path = artifacts / f"{prefix}_frame{idx}.html"
            frame_json_path = artifacts / f"{prefix}_frame{idx}.json"
            try:
                frame_html_path.write_text(frame.content(), encoding="utf-8")
                frame_json_path.write_text(
                    json.dumps(_frame_challenge_snapshot(frame), ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                logger.info(
                    "[outlook-browser] challenge frame artifacts url=%s html=%s json=%s",
                    frame_url,
                    frame_html_path,
                    frame_json_path,
                )
            except Exception as e:
                logger.debug("[outlook-browser] failed to write challenge frame artifacts url=%s: %s", frame_url, e)
        page.screenshot(path=str(png_path), full_page=True)
        logger.info(
            "[outlook-browser] challenge artifacts html=%s json=%s png=%s",
            html_path,
            json_path,
            png_path,
        )
    except Exception as e:
        logger.debug("[outlook-browser] failed to write challenge artifacts: %s", e)


def _form_snapshot(page) -> dict:
    try:
        return page.evaluate(
            """
            () => {
              const rectObj = el => {
                const r = el.getBoundingClientRect();
                return { x: r.x, y: r.y, width: r.width, height: r.height };
              };
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const fields = [...document.querySelectorAll('input, select, textarea, button, [role=button], [role=combobox]')]
                .filter(visible)
                .map((el, idx) => ({
                  idx,
                  tag: el.tagName,
                  type: el.getAttribute('type') || '',
                  id: el.id || '',
                  name: el.getAttribute('name') || '',
                  role: el.getAttribute('role') || '',
                  aria: el.getAttribute('aria-label') || '',
                  placeholder: el.getAttribute('placeholder') || '',
                  value: el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA' ? String(el.value || '').slice(0, 80) : '',
                  text: (el.innerText || el.textContent || '').trim().slice(0, 160),
                  options: el.tagName === 'SELECT' ? [...el.options].slice(0, 50).map(o => ({value: o.value, text: o.textContent})) : [],
                  rect: rectObj(el)
                }));
              return {
                url: location.href,
                title: document.title,
                text: (document.body && document.body.innerText || '').slice(0, 800),
                fields
              };
            }
            """
        ) or {}
    except Exception:
        return {}


def _extract_signup_server_data_from_html(html: str) -> dict[str, Any]:
    match = re.search(r"var\s+ServerData\s*=\s*(\{.*?\});\s*window\.\$Do", html, re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _cache_signup_server_data(page, *, label: str) -> dict:
    try:
        html_data: dict[str, Any] = {}
        try:
            html_data = _extract_signup_server_data_from_html(page.content())
        except Exception:
            html_data = {}
        cached = page.evaluate(
            """args => {
              const label = args.label;
              const htmlData = args.htmlData || {};
              const sd = window.ServerData || {};
              const prev = window.__outlookSignupServerData || {};
              const pick = (key, fallback = '') => {
                const value = sd[key] === undefined || sd[key] === null || sd[key] === '' ? htmlData[key] : sd[key];
                return value === undefined || value === null || value === '' ? (prev[key] || fallback) : value;
              };
              const q = location.search || prev.search || '';
              const cached = {
                label,
                url: location.href,
                search: q,
                apiCanary: pick('apiCanary', prev.apiCanary || sd.canary || ''),
                canary: pick('canary', prev.canary || sd.apiCanary || ''),
                urlCheckAvailableSigninNames: pick('urlCheckAvailableSigninNames', prev.urlCheckAvailableSigninNames || 'https://signup.live.com/API/CheckAvailableSigninNames'),
                urlCreateAccount: pick('urlCreateAccount', prev.urlCreateAccount || 'https://signup.live.com/API/CreateAccount'),
                sReturnUrl: pick('sReturnUrl', prev.sReturnUrl || ''),
                sSignupReturnUrl: pick('sSignupReturnUrl', prev.sSignupReturnUrl || ''),
                sSiteId: pick('sSiteId', prev.sSiteId || ''),
                sWReply: pick('sWReply', prev.sWReply || ''),
                uaid: pick('uaid', prev.uaid || new URLSearchParams(q).get('uaid') || ''),
                hpgid: pick('hpgid', prev.hpgid || 200225),
                iScenarioId: pick('iScenarioId', prev.iScenarioId || 100118),
                iUiFlavor: pick('iUiFlavor', prev.iUiFlavor || 1)
              };
              window.__outlookSignupServerData = cached;
              return {
                label,
                hasApiCanary: !!cached.apiCanary,
                hasCheckUrl: !!cached.urlCheckAvailableSigninNames,
                hasCreateUrl: !!cached.urlCreateAccount,
                uaid: cached.uaid,
                hpgid: cached.hpgid,
                scid: cached.iScenarioId,
                uiflvr: cached.iUiFlavor
              };
            }""",
            {"label": label, "htmlData": html_data},
        ) or {}
        logger.info(
            "[outlook-browser] cached signup server data label=%s has_canary=%s has_check=%s has_create=%s uaid=%s",
            label,
            bool(cached.get("hasApiCanary")),
            bool(cached.get("hasCheckUrl")),
            bool(cached.get("hasCreateUrl")),
            str(cached.get("uaid") or ""),
        )
        return cached
    except Exception as e:
        logger.debug("[outlook-browser] cache signup server data failed label=%s error=%s", label, e)
        return {}


def _write_form_artifacts(page, label: str) -> None:
    try:
        artifacts = _artifact_dir()
        prefix = f"form_{label}_{int(time.time())}"
        html_path = artifacts / f"{prefix}.html"
        json_path = artifacts / f"{prefix}.json"
        png_path = artifacts / f"{prefix}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        snapshot = _form_snapshot(page)
        snapshot["signupServerData"] = _cache_signup_server_data(page, label=label)
        json_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        page.screenshot(path=str(png_path), full_page=True)
        logger.info("[outlook-browser] form artifacts label=%s html=%s json=%s png=%s", label, html_path, json_path, png_path)
    except Exception as e:
        logger.debug("[outlook-browser] failed to write form artifacts label=%s: %s", label, e)


def _install_runtime_trace(page, *, label: str) -> Path:
    artifacts = _artifact_dir()
    trace_path = artifacts / f"runtime_trace_{label}_{int(time.time())}.jsonl"
    interesting = (
        "risk/initialize",
        "risk/verify",
        "collector",
        "hsprotect",
        "px-client",
        "captcha",
        "CreateAccount",
        "CheckAvailableSigninNames",
    )

    def write(item: dict[str, Any]) -> None:
        try:
            item["t"] = time.time()
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def is_interesting(url: str) -> bool:
        return any(k.lower() in url.lower() for k in interesting)

    def on_request(req) -> None:
        try:
            url = str(getattr(req, "url", "") or "")
            if not is_interesting(url):
                return
            post = ""
            try:
                post = str(req.post_data or "")
            except Exception:
                post = ""
            write({
                "kind": "request",
                "method": str(getattr(req, "method", "") or ""),
                "url": url,
                "headers": {str(k): str(v) for k, v in dict(getattr(req, "headers", {}) or {}).items()},
                "post_len": len(post),
                "post_data": post,
            })
        except Exception:
            pass

    def on_response(resp) -> None:
        try:
            url = str(getattr(resp, "url", "") or "")
            if not is_interesting(url):
                return
            body = ""
            wants_body = any(k in url for k in ("CreateAccount", "CheckAvailableSigninNames", "risk/verify"))
            if wants_body:
                try:
                    body = resp.text()
                except Exception as e:
                    body = f"<body-read-error {type(e).__name__}: {e}>"
            if "CreateAccount" in url:
                parsed: Any = None
                if body and not body.startswith("<body-read-error"):
                    try:
                        parsed = json.loads(body)
                    except Exception:
                        parsed = None
                try:
                    setattr(page, "_outlook_last_create_response", parsed if isinstance(parsed, dict) else {"text": body})
                    if isinstance(parsed, dict):
                        redirect = str(parsed.get("redirectUrl") or parsed.get("redirect_url") or parsed.get("redirect") or "")
                        error = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
                        setattr(page, "_outlook_last_create_redirect", redirect)
                        setattr(page, "_outlook_last_create_error", str(error.get("code") or parsed.get("errorCode") or ""))
                        setattr(page, "_outlook_last_create_error_field", str(error.get("field") or ""))
                except Exception:
                    pass
            write({
                "kind": "response",
                "status": int(getattr(resp, "status", 0) or 0),
                "url": url,
                "headers": {str(k): str(v) for k, v in dict(getattr(resp, "headers", {}) or {}).items()},
                "body_len": len(body),
                "body": body,
            })
        except Exception:
            pass

    def on_request_failed(req) -> None:
        try:
            url = str(getattr(req, "url", "") or "")
            if not is_interesting(url):
                return
            failure = {}
            try:
                failure = req.failure or {}
            except Exception:
                failure = {}
            write({
                "kind": "requestfailed",
                "method": str(getattr(req, "method", "") or ""),
                "url": url,
                "failure": failure,
            })
        except Exception:
            pass

    def on_console(msg) -> None:
        try:
            text = str(getattr(msg, "text", "") or "")
            if not is_interesting(text):
                return
            write({
                "kind": "console",
                "type": str(getattr(msg, "type", "") or ""),
                "text": text[:3000],
            })
        except Exception:
            pass

    def on_page_error(err) -> None:
        try:
            write({
                "kind": "pageerror",
                "error": str(err)[:4000],
            })
        except Exception:
            pass

    try:
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_request_failed)
        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        logger.info("[outlook-browser] runtime trace path=%s", trace_path)
    except Exception as e:
        logger.debug("[outlook-browser] install runtime trace failed: %s", e)
    return trace_path


def _install_js_internal_trace(page, *, label: str) -> Path:
    """Install non-invasive JS hooks for HUMAN/hsprotect runtime analysis."""
    artifacts = _artifact_dir()
    trace_path = artifacts / f"js_internal_trace_{label}_{int(time.time())}.jsonl"

    def write(item: dict[str, Any]) -> None:
        try:
            item["wall_t"] = time.time()
            with trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    try:
        page.expose_function("__outlookJsInternalTrace", write)
    except Exception:
        pass

    def on_console(msg) -> None:
        try:
            text = str(msg.text or "")
            marker = "__OUTLOOK_JS_INTERNAL_TRACE__"
            if marker not in text:
                return
            payload = text.split(marker, 1)[1]
            item = json.loads(payload)
            if isinstance(item, dict):
                item["console_type"] = str(getattr(msg, "type", "") or "")
                write(item)
        except Exception:
            pass

    try:
        page.on("console", on_console)
    except Exception:
        pass

    try:
        page.add_init_script(
            """
            (() => {
              if (window.__outlookJsInternalTraceInstalled) return;
              window.__outlookJsInternalTraceInstalled = true;
              const interesting = /hsprotect|perimeterx|px-cloud|px-client|collector|captcha|risk\\/verify|CreateAccount|CheckAvailableSigninNames/i;
              const safeString = (value) => {
                try {
                  if (value === undefined) return '<undefined>';
                  if (value === null) return '<null>';
                  if (typeof value === 'string') return value;
                  return JSON.stringify(value, (k, v) => {
                    if (typeof v === 'function') return `[function ${v.name || 'anonymous'}]`;
                    if (v instanceof Error) return { name: v.name, message: v.message, stack: String(v.stack || '') };
                    return v;
                  });
                } catch (e) {
                  try { return String(value); } catch (_) { return '<unstringifiable>'; }
                }
              };
              const stack = () => {
                try { return String((new Error()).stack || '').split('\\n').slice(2).join('\\n'); }
                catch (_) { return ''; }
              };
              const emit = (kind, data = {}) => {
                try {
                  const item = {
                    kind,
                    href: String(location.href || ''),
                    origin: String(location.origin || ''),
                    frameTop: window === window.top,
                    perf_t: Math.round(performance.now()),
                    data
                  };
                  const fn = window.__outlookJsInternalTrace;
                  if (typeof fn === 'function') fn(item);
                  try { console.debug('__OUTLOOK_JS_INTERNAL_TRACE__' + JSON.stringify(item)); } catch (_) {}
                } catch (_) {}
              };
              const maybeInteresting = url => interesting.test(String(url || location.href || ''));
              emit('hook_installed', { ua: navigator.userAgent, title: document.title });

              try {
                const originalPostMessage = window.postMessage;
                window.postMessage = function(message, targetOrigin, transfer) {
                  emit('window.postMessage.call', {
                    targetOrigin: safeString(targetOrigin, 160),
                    message: safeString(message, 1000),
                    stack: stack()
                  });
                  return originalPostMessage.apply(this, arguments);
                };
              } catch (e) {
                emit('hook_error', { hook: 'window.postMessage', error: safeString(e) });
              }

              try {
                const originalAdd = EventTarget.prototype.addEventListener;
                const originalDispatch = EventTarget.prototype.dispatchEvent;
                EventTarget.prototype.addEventListener = function(type, listener, options) {
                  if (type === 'message' || type === 'pointerdown' || type === 'pointerup' || type === 'mousedown' || type === 'mouseup' || type === 'touchstart' || type === 'touchend') {
                    let target = 'EventTarget';
                    try { target = this === window ? 'window' : (this && this.constructor && this.constructor.name) || target; } catch (_) {}
                    emit('addEventListener', { type, target, stack: stack() });
                  }
                  return originalAdd.apply(this, arguments);
                };
                EventTarget.prototype.dispatchEvent = function(event) {
                  try {
                    const type = event && event.type;
                    if (type === 'message' || type === 'pointerdown' || type === 'pointerup' || type === 'mousedown' || type === 'mouseup' || type === 'touchstart' || type === 'touchend') {
                      let target = 'EventTarget';
                      try { target = this === window ? 'window' : (this && this.constructor && this.constructor.name) || target; } catch (_) {}
                      emit('dispatchEvent', {
                        type: String(type || ''),
                        target,
                        isTrusted: !!(event && event.isTrusted),
                        pointerType: event && event.pointerType,
                        button: event && event.button,
                        buttons: event && event.buttons,
                        clientX: event && event.clientX,
                        clientY: event && event.clientY,
                        stack: stack()
                      });
                    }
                  } catch (_) {}
                  return originalDispatch.apply(this, arguments);
                };
                window.addEventListener('message', ev => {
                  emit('window.message.recv', {
                    eventOrigin: String(ev.origin || ''),
                    dataType: typeof ev.data,
                    data: safeString(ev.data, 1000)
                  });
                }, true);
              } catch (e) {
                emit('hook_error', { hook: 'addEventListener', error: safeString(e) });
              }

              try {
                if (window.MessageChannel) {
                  const OriginalMessageChannel = window.MessageChannel;
                  window.MessageChannel = function() {
                    const channel = new OriginalMessageChannel();
                    const wrapPort = (port, name) => {
                      try {
                        const originalPortPost = port.postMessage;
                        port.postMessage = function(message, transfer) {
                          emit('MessagePort.postMessage', { port: name, message: safeString(message, 1200), stack: stack() });
                          return originalPortPost.apply(this, arguments);
                        };
                        port.addEventListener('message', ev => {
                          emit('MessagePort.message', { port: name, data: safeString(ev.data, 1200) });
                        });
                      } catch (_) {}
                    };
                    wrapPort(channel.port1, 'port1');
                    wrapPort(channel.port2, 'port2');
                    emit('MessageChannel.new', { stack: stack() });
                    return channel;
                  };
                  window.MessageChannel.prototype = OriginalMessageChannel.prototype;
                }
              } catch (e) {
                emit('hook_error', { hook: 'MessageChannel', error: safeString(e) });
              }

              try {
                const proto = XMLHttpRequest.prototype;
                const originalOpen = proto.open;
                const originalSend = proto.send;
                const originalSetHeader = proto.setRequestHeader;
                proto.open = function(method, url) {
                  try {
                    this.__outlookTrace = { method: String(method || ''), url: String(url || ''), headers: {}, openStack: stack() };
                    if (maybeInteresting(url)) emit('xhr.open', this.__outlookTrace);
                  } catch (_) {}
                  return originalOpen.apply(this, arguments);
                };
                proto.setRequestHeader = function(name, value) {
                  try {
                    if (this.__outlookTrace) this.__outlookTrace.headers[String(name || '')] = String(value || '');
                  } catch (_) {}
                  return originalSetHeader.apply(this, arguments);
                };
                proto.send = function(body) {
                  try {
                    const meta = this.__outlookTrace || {};
                    if (maybeInteresting(meta.url)) {
                      emit('xhr.send', {
                        method: meta.method,
                        url: meta.url,
                        headers: meta.headers || {},
                        bodyLen: typeof body === 'string' ? body.length : (body && body.byteLength) || 0,
                        body: typeof body === 'string' ? body : Object.prototype.toString.call(body),
                        stack: stack()
                      });
                      this.addEventListener('loadend', () => {
                        let text = '';
                        try {
                          if (typeof this.responseText === 'string') text = this.responseText;
                        } catch (_) {}
                        emit('xhr.loadend', {
                          method: meta.method,
                          url: meta.url,
                          status: this.status,
                          responseURL: this.responseURL,
                          responseText: text
                        });
                      }, { once: true });
                    }
                  } catch (_) {}
                  return originalSend.apply(this, arguments);
                };
              } catch (e) {
                emit('hook_error', { hook: 'XMLHttpRequest', error: safeString(e) });
              }

              try {
                if (window.fetch) {
                  const originalFetch = window.fetch;
                  window.fetch = function(input, init = {}) {
                    const url = typeof input === 'string' ? input : (input && input.url) || '';
                    if (maybeInteresting(url)) {
                      emit('fetch.call', {
                        url: String(url),
                        method: String((init && init.method) || (input && input.method) || 'GET'),
                        bodyLen: typeof init.body === 'string' ? init.body.length : (init.body && init.body.byteLength) || 0,
                        body: typeof init.body === 'string' ? init.body : Object.prototype.toString.call(init.body),
                        stack: stack()
                      });
                    }
                    return originalFetch.apply(this, arguments).then(resp => {
                      try {
                        if (maybeInteresting(resp.url || url)) {
                          emit('fetch.response', { url: resp.url || String(url), status: resp.status, type: resp.type });
                        }
                      } catch (_) {}
                      return resp;
                    });
                  };
                }
              } catch (e) {
                emit('hook_error', { hook: 'fetch', error: safeString(e) });
              }

              try {
                if (navigator.sendBeacon) {
                  const originalBeacon = navigator.sendBeacon.bind(navigator);
                  navigator.sendBeacon = function(url, data) {
                    let dataText = '';
                    let len = 0;
                    try {
                      if (typeof data === 'string') { dataText = data; len = data.length; }
                      else if (data && typeof data.size === 'number') { len = data.size; dataText = `[${data.constructor && data.constructor.name || 'Blob'} size=${data.size} type=${data.type || ''}]`; }
                      else if (data) { len = data.byteLength || 0; dataText = Object.prototype.toString.call(data); }
                    } catch (_) {}
                    emit('sendBeacon.call', { url: String(url || ''), dataLen: len, data: dataText, stack: stack() });
                    return originalBeacon(url, data);
                  };
                }
              } catch (e) {
                emit('hook_error', { hook: 'sendBeacon', error: safeString(e) });
              }

              try {
                if (window.WebSocket) {
                  const OriginalWebSocket = window.WebSocket;
                  window.WebSocket = function(url, protocols) {
                    emit('WebSocket.new', { url: safeString(url, 500), protocols: safeString(protocols, 500), stack: stack() });
                    const ws = new OriginalWebSocket(url, protocols);
                    const originalSend = ws.send;
                    ws.send = function(data) {
                      emit('WebSocket.send', { url: safeString(url, 500), data: safeString(data, 1200), stack: stack() });
                      return originalSend.apply(this, arguments);
                    };
                    ws.addEventListener('message', ev => emit('WebSocket.message', { url: safeString(url, 500), data: safeString(ev.data, 1200) }));
                    ws.addEventListener('error', ev => emit('WebSocket.error', { url: safeString(url, 500), error: safeString(ev, 800) }));
                    return ws;
                  };
                  window.WebSocket.prototype = OriginalWebSocket.prototype;
                }
              } catch (e) {
                emit('hook_error', { hook: 'WebSocket', error: safeString(e) });
              }

              try {
                const OriginalBlob = window.Blob;
                if (OriginalBlob) {
                  window.Blob = function(parts, options) {
                    const blob = new OriginalBlob(parts, options);
                    try {
                      const textParts = Array.isArray(parts) ? parts.filter(p => typeof p === 'string').join('\\n') : '';
                      if (/sha256|postMessage|poi|captcha|worker/i.test(textParts)) {
                        emit('Blob.created', {
                          size: blob.size,
                          type: blob.type || (options && options.type) || '',
                          text: textParts,
                          stack: stack()
                        });
                      }
                    } catch (_) {}
                    return blob;
                  };
                  window.Blob.prototype = OriginalBlob.prototype;
                }
                if (URL && URL.createObjectURL) {
                  const originalCreateObjectURL = URL.createObjectURL.bind(URL);
                  URL.createObjectURL = function(obj) {
                    const out = originalCreateObjectURL(obj);
                    try {
                      emit('URL.createObjectURL', {
                        url: String(out || ''),
                        objectType: obj && obj.constructor && obj.constructor.name,
                        size: obj && obj.size,
                        type: obj && obj.type,
                        stack: stack()
                      });
                    } catch (_) {}
                    return out;
                  };
                }
                if (window.Worker) {
                  const OriginalWorker = window.Worker;
                  window.Worker = function(scriptURL, options) {
                    emit('Worker.new', { scriptURL: safeString(scriptURL, 500), options: safeString(options, 500), stack: stack() });
                    const worker = new OriginalWorker(scriptURL, options);
                    const originalWorkerPost = worker.postMessage;
                    worker.postMessage = function(message, transfer) {
                      emit('Worker.postMessage', { scriptURL: safeString(scriptURL, 300), message: safeString(message, 1000), stack: stack() });
                      return originalWorkerPost.apply(this, arguments);
                    };
                    worker.addEventListener('message', ev => {
                      emit('Worker.message', { scriptURL: safeString(scriptURL, 300), data: safeString(ev.data, 1000) });
                    });
                    worker.addEventListener('error', ev => {
                      emit('Worker.error', { scriptURL: safeString(scriptURL, 300), message: safeString(ev.message, 500), filename: ev.filename, lineno: ev.lineno, colno: ev.colno });
                    });
                    return worker;
                  };
                  window.Worker.prototype = OriginalWorker.prototype;
                }
              } catch (e) {
                emit('hook_error', { hook: 'Worker/Blob', error: safeString(e) });
              }

              try {
                let desc = Object.getOwnPropertyDescriptor(Document.prototype, 'cookie');
                let proto = Document.prototype;
                while ((!desc || !desc.set || !desc.get) && proto) {
                  proto = Object.getPrototypeOf(proto);
                  if (proto) desc = Object.getOwnPropertyDescriptor(proto, 'cookie');
                }
                if (desc && desc.configurable && desc.get && desc.set) {
                  Object.defineProperty(document, 'cookie', {
                    configurable: true,
                    enumerable: desc.enumerable,
                    get() {
                      const value = desc.get.call(document);
                      return value;
                    },
                    set(value) {
                      const text = String(value || '');
                      if (/_px3|_pxde|_pxvid|fptctx2|MUID|MSP|OParams|uaid/i.test(text)) {
                        emit('document.cookie.set', { value: text, stack: stack() });
                      }
                      return desc.set.call(document, value);
                    }
                  });
                }
              } catch (e) {
                emit('hook_error', { hook: 'document.cookie', error: safeString(e) });
              }

              try {
                if (window.HTMLFormElement) {
                  const formProto = window.HTMLFormElement.prototype;
                  if (formProto.submit) {
                    const originalSubmit = formProto.submit;
                    formProto.submit = function() {
                      emit('HTMLFormElement.submit', {
                        action: this && this.action,
                        method: this && this.method,
                        id: this && this.id,
                        stack: stack()
                      });
                      return originalSubmit.apply(this, arguments);
                    };
                  }
                  if (formProto.requestSubmit) {
                    const originalRequestSubmit = formProto.requestSubmit;
                    formProto.requestSubmit = function(submitter) {
                      emit('HTMLFormElement.requestSubmit', {
                        action: this && this.action,
                        method: this && this.method,
                        id: this && this.id,
                        submitter: submitter && (submitter.id || submitter.name || submitter.type),
                        stack: stack()
                      });
                      return originalRequestSubmit.apply(this, arguments);
                    };
                  }
                }
              } catch (e) {
                emit('hook_error', { hook: 'HTMLFormElement', error: safeString(e) });
              }

              try {
                const wrapSdk = sdk => {
                  try {
                    if (!sdk || sdk.__outlookWrapped) return sdk;
                    Object.defineProperty(sdk, '__outlookWrapped', { value: true });
                    if (sdk.Events) {
                      for (const name of ['on', 'one', 'off', 'subscribe', 'trigger']) {
                        if (typeof sdk.Events[name] !== 'function' || sdk.Events[name].__outlookWrapped) continue;
                        const original = sdk.Events[name];
                        sdk.Events[name] = function() {
                          emit('PX.Events.' + name, { args: Array.from(arguments).map(v => safeString(v, 500)), stack: stack() });
                          return original.apply(this, arguments);
                        };
                        Object.defineProperty(sdk.Events[name], '__outlookWrapped', { value: true });
                      }
                    }
                  } catch (e) {
                    emit('hook_error', { hook: 'wrapSdk', error: safeString(e) });
                  }
                  return sdk;
                };
                const installPropertyWrapper = name => {
                  try {
                    let current = window[name];
                    Object.defineProperty(window, name, {
                      configurable: true,
                      get() { return current; },
                      set(value) {
                        emit('window.property.set', { name, valueType: typeof value, valuePreview: safeString(value, 500), stack: stack() });
                        if (name.endsWith('_asyncInit') && typeof value === 'function') {
                          current = function(sdk) {
                            emit('PX.asyncInit.call', { name, sdkKeys: sdk && Object.keys(sdk).slice(0, 30) });
                            wrapSdk(sdk);
                            return value.apply(this, arguments);
                          };
                        } else {
                          current = wrapSdk(value);
                        }
                      }
                    });
                    if (current !== undefined) window[name] = current;
                  } catch (e) {
                    emit('hook_error', { hook: 'property:' + name, error: safeString(e) });
                  }
                };
                installPropertyWrapper('PXzC5j78di_asyncInit');
                installPropertyWrapper('PXzC5j78di');
                installPropertyWrapper('PX');
                const scan = () => {
                  try {
                    for (const key of Object.keys(window)) {
                      if (/^PX[A-Za-z0-9]{4,12}(_asyncInit)?$/.test(key)) {
                        const value = window[key];
                        if (value && value.Events) wrapSdk(value);
                      }
                    }
                  } catch (_) {}
                };
                setInterval(scan, 500);
                scan();
              } catch (e) {
                emit('hook_error', { hook: 'PX sdk', error: safeString(e) });
              }
            })();
            """
        )
        logger.info("[outlook-browser] js internal trace path=%s", trace_path)
    except Exception as e:
        logger.debug("[outlook-browser] install js internal trace failed: %s", e)
    return trace_path


def _js_internal_trace_enabled() -> bool:
    return str(os.environ.get("OUTLOOK_JS_INTERNAL_TRACE", "")).strip().lower() in {"1", "true", "yes", "on"}


def _hsprotect_js_patch_enabled() -> bool:
    return str(os.environ.get("OUTLOOK_HSPROTECT_JS_PATCH", "")).strip().lower() in {"1", "true", "yes", "on"}


def _hsprotect_js_patch_apply_enabled() -> bool:
    return str(os.environ.get("OUTLOOK_HSPROTECT_JS_PATCH_APPLY", "")).strip().lower() in {"1", "true", "yes", "on"}


def _patch_hsprotect_js_source(url: str, source: str) -> tuple[str, list[str]]:
    patches: list[str] = []
    patched = source

    def marker(name: str) -> str:
        return f"__outlook_hsprotect_patch_{name}__"

    emit_js = (
        "function __outlookPatchEmit(kind,data){try{"
        "var item={kind:kind,href:String(location.href||''),origin:String(location.origin||''),"
        "frameTop:window===window.top,perf_t:Math.round(performance.now()),data:data||{}};"
        "try{if(typeof window.__outlookJsInternalTrace==='function')window.__outlookJsInternalTrace(item)}catch(e){};"
        "try{console.debug('__OUTLOOK_JS_INTERNAL_TRACE__'+JSON.stringify(item))}catch(e){}"
        "}catch(e){}}"
    )

    if "client.hsprotect.net/" in url and "main.min.js" in url:
        needle = "var Xn={on:function(t,e,n){this.subscribe(t,e,n,!1)},one:function(t,e,n){this.subscribe(t,e,n,!0)},off:function(t,e){var n,r;if(void 0!==this.channels[t])for(n=0,r=this.channels[t].length;n<r;n++){if(this.channels[t][n].fn===e){this.channels[t].splice(n,1);break}}},subscribe:function(t,e,n,r){void 0===this.channels&&(this.channels={}),this.channels[t]=this.channels[t]||[],this.channels[t].push({fn:e,ctx:n,once:r||!1})},trigger:function(e){if(this.channels&&this.channels.hasOwnProperty(e)){for(var n=Array.prototype.slice.call(arguments,1),r=[];this.channels[e].length>0;){var a=this.channels[e].shift();t(a.fn)===f&&a.fn.apply(a.ctx,n),a.once||r.push(a)}this.channels[e]=r}}},"
        if needle in patched:
            replacement = (
                emit_js
                + "var Xn={on:function(t,e,n){__outlookPatchEmit('hsprotect.Xn.on',{channel:String(t),listener:String(e&&e.name||''),stack:(new Error).stack});this.subscribe(t,e,n,!1)},"
                + "one:function(t,e,n){__outlookPatchEmit('hsprotect.Xn.one',{channel:String(t),listener:String(e&&e.name||''),stack:(new Error).stack});this.subscribe(t,e,n,!0)},"
                + "off:function(t,e){var n,r;if(void 0!==this.channels[t])for(n=0,r=this.channels[t].length;n<r;n++){if(this.channels[t][n].fn===e){this.channels[t].splice(n,1);break}}},"
                + "subscribe:function(t,e,n,r){__outlookPatchEmit('hsprotect.Xn.subscribe',{channel:String(t),once:!!r,listener:String(e&&e.name||''),stack:(new Error).stack});void 0===this.channels&&(this.channels={}),this.channels[t]=this.channels[t]||[],this.channels[t].push({fn:e,ctx:n,once:r||!1})},"
                + "trigger:function(e){__outlookPatchEmit('hsprotect.Xn.trigger',{channel:String(e),args:Array.prototype.slice.call(arguments,1).map(function(x){try{return JSON.stringify(x)}catch(_){return String(x)}}),stack:(new Error).stack});if(this.channels&&this.channels.hasOwnProperty(e)){for(var n=Array.prototype.slice.call(arguments,1),r=[];this.channels[e].length>0;){var a=this.channels[e].shift();t(a.fn)===f&&a.fn.apply(a.ctx,n),a.once||r.push(a)}this.channels[e]=r}}},"
            )
            patched = patched.replace(needle, replacement)
            patches.append(marker("main_xn_event_bus"))
        send_needle = "return o.sendBeacon(n,r)"
        if send_needle in patched:
            patched = patched.replace(
                send_needle,
                "__outlookPatchEmit('hsprotect.sendBeacon.internal',{url:String(n),blobSize:r&&r.size,blobType:r&&r.type,data:String(r&&r.text?'[blob:text-async]':r),stack:(new Error).stack});try{if(r&&typeof r.text==='function')r.text().then(function(__txt){__outlookPatchEmit('hsprotect.sendBeacon.blobText',{url:String(n),blobSize:r&&r.size,blobType:r&&r.type,text:String(__txt),stack:(new Error).stack})}).catch(function(__err){__outlookPatchEmit('hsprotect.sendBeacon.blobText.error',{url:String(n),error:String(__err),stack:(new Error).stack})})}catch(__beaconTextErr){__outlookPatchEmit('hsprotect.sendBeacon.blobText.error',{url:String(n),error:String(__beaconTextErr),stack:(new Error).stack})}return o.sendBeacon(n,r)",
            )
            patches.append(marker("main_sendbeacon_internal"))
        fp_needle = "function fp(t,e){var n=235,r=251,a=279,o=235,i=Bv;np[i(279)](i(n),t,e),Ii[i(r)][i(a)](i(o),t)}"
        if fp_needle in patched:
            patched = patched.replace(
                fp_needle,
                "function fp(t,e){__outlookPatchEmit('hsprotect.main.fp.enter',{t:String(t),e:String(e),stack:(new Error).stack});var n=235,r=251,a=279,o=235,i=Bv;np[i(279)](i(n),t,e),Ii[i(r)][i(a)](i(o),t)}",
            )
            patches.append(marker("main_fp_enter"))
        om_needle = "function om(e,n){var r,a=458,o=453,c=Yp;(Mv&&_r()&&i[c(a)](),n&&Yi())||(!function(e,n){var r=278,a=227,o=235,i=Tl,c=arguments[i(278)]>2&&void 0!==arguments[2]?arguments[2]:jl;if(!e||!e[i(r)])return!1;var u=Wl(e);if(t(u)!==l)c(u,!0);else{var s=j(u),f=el(n);c(u=ne(s,parseInt(f,10)%128)[i(a)](i(o)),!1)}}(e,Tt()),n&&(tm?Pc()&&um():(vr(rr[se])&&function(t){qo=t}(e),r=(new Date)[c(o)](),$o=r,tm=!0,function(){var e={F:455},n=Yp;ur=!0,hr(cr),nm=+fr(rr[ue]),function(){var t=vr(rr[Te]),e=Np()||vr(rr[Ae]);(t||e)&&Ep(e,t)}(),vr(rr[Me])&&_p(),t(nm)===s&&nm<=Jp?setTimeout(cm[n(e.F)](this,nm),nm):cm()}())))}"
        if om_needle in patched:
            patched = patched.replace(
                om_needle,
                "function om(e,n){__outlookPatchEmit('hsprotect.main.om.enter',{e:String(e),n:!!n,stack:(new Error).stack});var r,a=458,o=453,c=Yp;(Mv&&_r()&&i[c(a)](),n&&Yi())||(!function(e,n){var r=278,a=227,o=235,i=Tl,c=arguments[i(278)]>2&&void 0!==arguments[2]?arguments[2]:jl;if(!e||!e[i(r)])return!1;var u=Wl(e);try{__outlookPatchEmit('hsprotect.main.om.Wl',{input:String(e),outputType:typeof u,output:String(u),n:String(n),stack:(new Error).stack})}catch(_){}if(t(u)!==l)c(u,!0);else{var s=j(u),f=el(n),__decoded=ne(s,parseInt(f,10)%128),__parts=__decoded[i(a)](i(o));try{__outlookPatchEmit('hsprotect.main.om.decode',{u:String(u),j:String(s),el:String(f),mod:parseInt(f,10)%128,decoded:String(__decoded),parts:__parts,stack:(new Error).stack})}catch(_){}c(u=__parts,!1)}}(e,Tt()),n&&(tm?Pc()&&um():(vr(rr[se])&&function(t){qo=t}(e),r=(new Date)[c(o)](),$o=r,tm=!0,function(){var e={F:455},n=Yp;ur=!0,hr(cr),nm=+fr(rr[ue]),function(){var t=vr(rr[Te]),e=Np()||vr(rr[Ae]);(t||e)&&Ep(e,t)}(),vr(rr[Me])&&_p(),t(nm)===s&&nm<=Jp?setTimeout(cm[n(e.F)](this,nm),nm):cm()}())))}",
            )
            patches.append(marker("main_om_enter_decode"))
        jl_needle = "function jl(e,n){var r=278,a=227,o=232,i=254,c=260,u=254,s=241,l=Tl;if(e){for(var h,d=[],v=0;v<e[l(r)];v++){var p=e[v];if(p){var m=p[l(a)](\"|\"),g=m[l(o)](),y=n?Cl[g]:Xl[g];if(m[0]===rr[pe]){h=R(R({},Fn,g),In,m);continue}f===t(y)&&(g===wl||g===Ml?d[l(i)](R(R({},Fn,g),In,m)):d[l(c)](R(R({},Fn,g),In,m)))}}h&&d[l(u)](h);for(var b=0;b<d[l(r)];b++){var I=d[b];try{(n?Cl[I[Fn]]:Xl[I[Fn]])[l(s)](R({},xn,d),I[In])}catch(t){kn(t,Cn[Fe])}}}}"
        if jl_needle in patched:
            patched = patched.replace(
                jl_needle,
                "function jl(e,n){__outlookPatchEmit('hsprotect.main.jl.enter',{n:!!n,len:e&&e.length,items:e,stack:(new Error).stack});var r=278,a=227,o=232,i=254,c=260,u=254,s=241,l=Tl;if(e){for(var h,d=[],v=0;v<e[l(r)];v++){var p=e[v];if(p){var m=p[l(a)](\"|\"),g=m[l(o)](),y=n?Cl[g]:Xl[g];try{__outlookPatchEmit('hsprotect.main.jl.item',{index:v,raw:String(p),handlerKey:String(g),args:m,table:n?'Cl':'Xl',handlerType:typeof y,stack:(new Error).stack})}catch(_){}if(m[0]===rr[pe]){h=R(R({},Fn,g),In,m);continue}f===t(y)&&(g===wl||g===Ml?d[l(i)](R(R({},Fn,g),In,m)):d[l(c)](R(R({},Fn,g),In,m)))}}h&&d[l(u)](h);try{__outlookPatchEmit('hsprotect.main.jl.queue',{n:!!n,queue:d.map(function(x){try{return{key:String(x[Fn]),args:x[In]}}catch(_){return String(x)}}),stack:(new Error).stack})}catch(_){}for(var b=0;b<d[l(r)];b++){var I=d[b];try{__outlookPatchEmit('hsprotect.main.jl.dispatch',{table:n?'Cl':'Xl',handlerKey:String(I[Fn]),args:I[In],queueLen:d.length,stack:(new Error).stack});(n?Cl[I[Fn]]:Xl[I[Fn]])[l(s)](R({},xn,d),I[In])}catch(t){kn(t,Cn[Fe])}}}}",
            )
            patches.append(marker("main_jl_dispatch"))
        tf_start_needle = "function tf(t,e){for(var n=eu(),r=0;r<t.length;r++){"
        if tf_start_needle in patched:
            patched = patched.replace(
                tf_start_needle,
                "function tf(t,e){try{__outlookPatchEmit('hsprotect.main.tf.enter',{activities:t,configKeys:e&&Object.keys?Object.keys(e):[],stack:(new Error).stack})}catch(_){}for(var n=eu(),r=0;r<t.length;r++){",
                1,
            )
            patches.append(marker("main_tf_enter"))
        tf_payload_needle = "d={vid:Ct(),tag:e[on],appID:e[an],cu:po(),cs:f,pc:h},v=Vs(t,d),p=["
        if tf_payload_needle in patched:
            patched = patched.replace(
                tf_payload_needle,
                "d={vid:Ct(),tag:e[on],appID:e[an],cu:po(),cs:f,pc:h},v=Vs(t,d);try{var __qi=Qi(),__marker=ne(J(__qi||Xs(118)),10);__outlookPatchEmit('hsprotect.main.tf.payload',{activities:t,serialized:ut(t),meta:d,payload:String(v),pc:String(h),cs:String(f),qi:String(__qi),marker:String(__marker),markerLen:String(__marker).length,stack:(new Error).stack})}catch(_){}p=[",
                1,
            )
            patches.append(marker("main_tf_payload"))

    if "captcha.hsprotect.net/" in url and "captcha.js" in url:
        zt_needle = "var zt=function(r){function n(r,n){return mt(r- -665,n)}try{R()[window[v(n(-420,-426))]][v(n(-410,-403))][v(n(-422,-429))](v(n(-417,-412)),r)}catch(r){}};"
        if zt_needle in patched:
            patched = patched.replace(
                zt_needle,
                emit_js
                + "var zt=function(r){function n(r,n){return mt(r- -665,n)}try{__outlookPatchEmit('hsprotect.captcha.zt.enter',{arg:String(r),stack:(new Error).stack})}catch(_){}try{R()[window[v(n(-420,-426))]][v(n(-410,-403))][v(n(-422,-429))](v(n(-417,-412)),r)}catch(r){}};",
            )
            patches.append(marker("captcha_zt_enter"))
        ot_needle = "function Ot(r,n,t,v){function e(r,n){return Rt(r-705,n)}var f,s=u,m=su();clearTimeout(At),r=parseInt(r),zt(s(0===r?e(1095,1044):e(1042,972))),0===r&&B()&&m[s(\"PkU0HwwBODJgEBUZGDslQi4ZChw8\")]&&setTimeout(W,Kt-T),Hn[s(e(1147,1081))]=Kn()&&-1===r;var z,i=(z=qt,Ut=!0,setTimeout[u(\"NV8XFA\")](null,z?Qt:kt,Kt)),c=function(r,n,t){var v=u;if(r&&n&&t)return\"\"[e(-466,-443)](r,\"|\")[e(-466,-475)](n,\"|\")[e(-466,-473)](t);function e(r,n){return Rt(r- -864,n)}return v(\"\")}(n,t,v),o=((f={})[s(e(1155,1184))]=r,f);c&&(o[s(e(1184,1252))]=c),i(o,!0)}"
        if ot_needle in patched:
            patched = patched.replace(
                ot_needle,
                emit_js
                + "function Ot(r,n,t,v){function e(r,n){return Rt(r-705,n)}var f,s=u,m=su();clearTimeout(At),r=parseInt(r);try{var __otState=s(0===r?e(1095,1044):e(1042,972));__outlookPatchEmit('hsprotect.captcha.Ot.enter',{r:r,n:String(n),t:String(t),v:String(v),state:String(__otState),zero:r===0,stack:(new Error).stack});zt(__otState)}catch(__otPatchErr){try{__outlookPatchEmit('hsprotect.captcha.Ot.patch_error',{error:String(__otPatchErr),stack:(new Error).stack})}catch(_){}}0===r&&B()&&m[s(\"PkU0HwwBODJgEBUZGDslQi4ZChw8\")]&&setTimeout(W,Kt-T),Hn[s(e(1147,1081))]=Kn()&&-1===r;var z,i=(z=qt,Ut=!0,setTimeout[u(\"NV8XFA\")](null,z?Qt:kt,Kt)),c=function(r,n,t){var v=u;if(r&&n&&t)return\"\"[e(-466,-443)](r,\"|\")[e(-466,-475)](n,\"|\")[e(-466,-473)](t);function e(r,n){return Rt(r- -864,n)}return v(\"\")}(n,t,v),o=((f={})[s(e(1155,1184))]=r,f);c&&(o[s(e(1184,1252))]=c),i(o,!0)}",
            )
            patches.append(marker("captcha_ot_enter"))
        needle = "function qs(r,n,u,t,v,e,f,s,m){for(var z,i=r;i<=n;i++)(z=poi(i,u,t,v,e,f,0,m))&&postMessage(z);postMessage(!1)}"
        if needle in patched:
            replacement = (
                emit_js
                + "function qs(r,n,u,t,v,e,f,s,m){var __outlookPatchEmit=(typeof self!=='undefined'&&self.__outlookPatchEmit)||(typeof window!=='undefined'&&window.__outlookPatchEmit)||function(kind,data){try{console.debug('__OUTLOOK_JS_INTERNAL_TRACE__'+JSON.stringify({kind:kind,href:String(location&&location.href||''),origin:String(location&&location.origin||''),frameTop:false,perf_t:0,data:data||{},worker:true}))}catch(_){}};__outlookPatchEmit('hsprotect.captcha.qs.start',{from:r,to:n,mask:u,len:t,prefix:v,salt:e,target:m,stack:(new Error).stack});"
                + "for(var z,i=r;i<=n;i++)(z=poi(i,u,t,v,e,f,0,m))&&(__outlookPatchEmit('hsprotect.captcha.pow.hit',{i:i,value:String(z)}),postMessage(z));"
                + "__outlookPatchEmit('hsprotect.captcha.qs.exhausted',{from:r,to:n});postMessage(!1)}"
            )
            patched = patched.replace(needle, replacement)
            patches.append(marker("captcha_qs_pow"))
        worker_needle = "var w=new Worker(c);return w"
        if worker_needle in patched:
            patched = patched.replace(worker_needle, "__outlookPatchEmit('hsprotect.captcha.worker.new',{url:String(c),sourceLen:String(v||'').length,source:String(v||''),stack:(new Error).stack});var w=new Worker(c);try{w.addEventListener('message',function(ev){__outlookPatchEmit('hsprotect.captcha.worker.message',{url:String(c),data:String(ev&&ev.data),stack:(new Error).stack})});w.addEventListener('error',function(ev){__outlookPatchEmit('hsprotect.captcha.worker.error',{url:String(c),message:String(ev&&ev.message||''),stack:(new Error).stack})})}catch(_){}return w")
            patches.append(marker("captcha_worker_new"))

    return patched, patches


def _write_hsprotect_patch_artifacts(
    *,
    label: str,
    url: str,
    source: str,
    patched: str,
    patches: list[str],
) -> None:
    try:
        out_dir = _artifact_dir() / "hsprotect_js_patch"
        out_dir.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256(source.encode("utf-8", errors="replace")).hexdigest()
        ts = int(time.time())
        kind = "captcha" if "captcha.hsprotect.net/" in url else "main"
        base = out_dir / f"{kind}_{label}_{ts}_{sha[:12]}"
        source_path = base.with_suffix(".source.js")
        patched_path = base.with_suffix(".patched.js")
        meta_path = base.with_suffix(".json")
        probes = {
            "main_min": "main.min.js" in url,
            "captcha_js": "captcha.js" in url,
            "has_Xn_event_bus": "var Xn={on:function" in source,
            "has_sendBeacon_internal": "return o.sendBeacon(n,r)" in source,
            "has_function_fp": "function fp(t,e)" in source,
            "has_function_om": "function om(e,n)" in source,
            "has_function_jl": "function jl(e,n)" in source,
            "has_function_tf": "function tf(t,e)" in source,
            "has_tf_vs_payload": "v=Vs(t,d)" in source,
            "has_captcha_Ot": "function Ot(r,n,t,v)" in source,
            "has_captcha_qs": "function qs(r,n,u,t,v,e,f,s,m)" in source,
            "has_worker_new": "var w=new Worker(c);return w" in source,
        }
        indices = {key: source.find(key) for key in [
            "var Xn={on:function",
            "return o.sendBeacon(n,r)",
            "function fp(t,e)",
            "function om(e,n)",
            "function jl(e,n)",
            "function tf(t,e)",
            "v=Vs(t,d)",
            "function Ot(r,n,t,v)",
            "function qs(r,n,u,t,v,e,f,s,m)",
            "var w=new Worker(c);return w",
        ]}
        source_path.write_text(source, encoding="utf-8", errors="replace")
        patched_path.write_text(patched, encoding="utf-8", errors="replace")
        meta_path.write_text(
            json.dumps(
                {
                    "label": label,
                    "url": url,
                    "sha256": sha,
                    "source_len": len(source),
                    "patched_len": len(patched),
                    "changed": source != patched,
                    "patches": patches,
                    "probes": probes,
                    "indices": indices,
                    "source_path": str(source_path),
                    "patched_path": str(patched_path),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        logger.info(
            "[outlook-browser] hsprotect JS patch artifact label=%s kind=%s sha256=%s patches=%s meta=%s",
            label,
            kind,
            sha,
            patches,
            meta_path,
        )
    except Exception as e:
        logger.debug("[outlook-browser] failed to write hsprotect JS patch artifact label=%s url=%s: %s", label, url, e)


def _install_hsprotect_js_patch(ctx, *, label: str) -> None:
    if not _hsprotect_js_patch_enabled():
        return
    apply_patch = _hsprotect_js_patch_apply_enabled()
    logger.info(
        "[outlook-browser] hsprotect JS patch capture enabled label=%s apply=%s",
        label,
        apply_patch,
    )

    def should_capture(url: str) -> bool:
        return (
            ("client.hsprotect.net/" in url and "main.min.js" in url)
            or ("captcha.hsprotect.net/" in url and "captcha.js" in url)
        )

    def write_artifacts_from_response(url: str, body: bytes) -> tuple[str, list[str]]:
        source = body.decode("utf-8", errors="replace")
        patched, patches = _patch_hsprotect_js_source(url, source)
        _write_hsprotect_patch_artifacts(label=label, url=url, source=source, patched=patched, patches=patches)
        if not patches:
            logger.warning("[outlook-browser] hsprotect JS patch no-op label=%s url=%s", label, url)
        else:
            logger.info(
                "[outlook-browser] hsprotect JS patch artifact captured label=%s url=%s patches=%s apply=%s",
                label,
                url,
                patches,
                apply_patch,
            )
        return patched, patches

    if not apply_patch:
        def response_handler(response) -> None:
            url = str(getattr(response, "url", "") or "")
            if not should_capture(url):
                return
            try:
                write_artifacts_from_response(url, response.body())
            except Exception as e:
                logger.warning("[outlook-browser] hsprotect JS capture failed label=%s url=%s error=%s", label, url, e)

        try:
            ctx.on("response", response_handler)
            logger.info("[outlook-browser] hsprotect JS capture installed without route interception label=%s", label)
        except Exception as e:
            logger.debug("[outlook-browser] hsprotect JS capture install failed label=%s error=%s", label, e)
        return

    def handler(route, request) -> None:
        url = str(getattr(request, "url", "") or "")
        if not should_capture(url):
            route.continue_()
            return
        try:
            resp = route.fetch()
            body = resp.body()
            patched, _patches = write_artifacts_from_response(url, body)
            headers = dict(getattr(resp, "headers", {}) or {})
            headers["content-type"] = "application/javascript; charset=utf-8"
            headers.pop("content-length", None)
            route.fulfill(status=int(getattr(resp, "status", 200) or 200), headers=headers, body=patched.encode("utf-8"))
        except Exception as e:
            logger.warning("[outlook-browser] hsprotect JS patch failed label=%s url=%s error=%s", label, url, e)
            route.continue_()

    try:
        ctx.route("**/*", handler)
    except Exception as e:
        logger.debug("[outlook-browser] hsprotect JS patch install failed label=%s error=%s", label, e)


_STATIC_CACHE_HEADER_ALLOWLIST = {
    "content-type",
    "cache-control",
    "etag",
    "last-modified",
    "expires",
    "access-control-allow-origin",
    "timing-allow-origin",
    "cross-origin-resource-policy",
}


def _static_cache_enabled() -> bool:
    return str(os.environ.get("OUTLOOK_STATIC_CACHE", "")).strip().lower() in {"1", "true", "yes", "on"}


def _static_cache_dir() -> Path:
    raw = str(os.environ.get("OUTLOOK_STATIC_CACHE_DIR", "")).strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = Path.cwd() / p
    else:
        p = _artifact_dir() / "static_cache"
    return p.resolve()


def _static_cache_ttl_s() -> int:
    raw = str(os.environ.get("OUTLOOK_STATIC_CACHE_TTL_S", "604800")).strip()
    try:
        return max(60, int(float(raw)))
    except Exception:
        return 604800


def _static_cache_log_bypass() -> bool:
    return str(os.environ.get("OUTLOOK_STATIC_CACHE_LOG_BYPASS", "")).strip().lower() in {"1", "true", "yes", "on"}


def _static_cache_key(url: str) -> tuple[str, str]:
    try:
        parts = urlsplit(url)
    except Exception:
        return "", "bad_url"
    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    path = parts.path
    lower_path = path.lower()
    if scheme != "https":
        return "", "non_https"

    state_markers = (
        "risk/initialize",
        "risk/verify",
        "createaccount",
        "checkavailablesigninnames",
        "collector",
        "beacon",
        "oauth",
        "authorize",
        "token",
        "/api/",
    )
    full_lower = url.lower()
    if any(marker in full_lower for marker in state_markers):
        return "", "state_url"
    if host in {"iframe.hsprotect.net", "login.microsoftonline.com", "signup.live.com", "login.live.com"}:
        return "", "state_host"

    if host == "client.hsprotect.net" and lower_path == "/pxzc5j78di/main.min.js":
        canonical = urlunsplit((scheme, host, path, "", ""))
        return f"js:{canonical}", "allow"

    if host == "captcha.hsprotect.net" and lower_path == "/pxzc5j78di/captcha.js":
        params = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k in {"a", "m"}:
                params.append((k, v))
        canonical_q = urlencode(sorted(params))
        canonical = urlunsplit((scheme, host, path, canonical_q, ""))
        return f"js:{canonical}", "allow"

    image_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
    if host == "logincdn.msftauth.net" and "/images/" in lower_path and lower_path.endswith(image_exts):
        return f"asset:{urlunsplit((scheme, host, path, parts.query, ''))}", "allow"

    if host in {"fonts.googleapis.com", "fonts.gstatic.com"}:
        return f"asset:{urlunsplit((scheme, host, path, parts.query, ''))}", "allow"

    return "", "not_allowlisted"


def _static_cache_index_path(cache_dir: Path) -> Path:
    return cache_dir / "index.json"


def _load_static_cache_index(cache_dir: Path) -> dict[str, Any]:
    try:
        p = _static_cache_index_path(cache_dir)
        if not p.exists():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_static_cache_index(cache_dir: Path, index: dict[str, Any]) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        tmp = cache_dir / f"index.json.tmp.{os.getpid()}.{int(time.time() * 1000)}"
        tmp.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(tmp, _static_cache_index_path(cache_dir))
    except Exception as e:
        logger.debug("[outlook-browser] static cache index save failed: %s", e)


def _static_cache_body_path(cache_dir: Path, sha256: str) -> Path:
    return cache_dir / "bodies" / sha256[:2] / f"{sha256}.bin"


def _static_cache_response_headers(headers: dict[str, Any]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in _STATIC_CACHE_HEADER_ALLOWLIST:
            clean[lk] = str(v)
    return clean


def _install_static_resource_cache(ctx, *, label: str) -> None:
    if not _static_cache_enabled():
        return
    cache_dir = _static_cache_dir()
    ttl_s = _static_cache_ttl_s()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "bodies").mkdir(parents=True, exist_ok=True)
    logger.info("[outlook-browser] static cache enabled label=%s dir=%s ttl_s=%s", label, cache_dir, ttl_s)

    def handler(route, request) -> None:
        url = str(getattr(request, "url", "") or "")
        method = str(getattr(request, "method", "") or "").upper()
        if method != "GET":
            route.continue_()
            return
        key, reason = _static_cache_key(url)
        if not key:
            if _static_cache_log_bypass():
                logger.info("[outlook-browser] static cache bypass label=%s reason=%s url=%s", label, reason, url)
            route.continue_()
            return

        now = time.time()
        index = _load_static_cache_index(cache_dir)
        entry = index.get(key) if isinstance(index.get(key), dict) else None
        if entry:
            body_sha = str(entry.get("body_sha256") or "")
            body_path = _static_cache_body_path(cache_dir, body_sha) if body_sha else cache_dir / str(entry.get("body_path") or "")
            age_s = now - float(entry.get("created_at") or 0)
            if body_path.exists() and age_s <= ttl_s:
                try:
                    body = body_path.read_bytes()
                    entry["last_hit_at"] = now
                    entry["hit_count"] = int(entry.get("hit_count") or 0) + 1
                    index[key] = entry
                    _save_static_cache_index(cache_dir, index)
                    logger.info("[outlook-browser] static cache hit label=%s url=%s bytes=%s key=%s", label, url, len(body), key)
                    route.fulfill(
                        status=int(entry.get("status") or 200),
                        headers={str(k): str(v) for k, v in dict(entry.get("headers") or {}).items()},
                        body=body,
                    )
                    return
                except Exception as e:
                    logger.debug("[outlook-browser] static cache hit failed label=%s key=%s error=%s", label, key, e)
            elif body_path.exists():
                logger.info("[outlook-browser] static cache expired label=%s url=%s age_s=%.0f key=%s", label, url, age_s, key)

        try:
            resp = route.fetch()
            body = resp.body()
            status = int(getattr(resp, "status", 0) or 0)
            headers = _static_cache_response_headers(dict(getattr(resp, "headers", {}) or {}))
            logger.info("[outlook-browser] static cache miss label=%s url=%s status=%s bytes=%s key=%s", label, url, status, len(body), key)
            if status == 200 and body:
                body_sha = hashlib.sha256(body).hexdigest()
                body_path = _static_cache_body_path(cache_dir, body_sha)
                body_path.parent.mkdir(parents=True, exist_ok=True)
                if not body_path.exists():
                    tmp = body_path.with_suffix(f".tmp.{os.getpid()}")
                    tmp.write_bytes(body)
                    os.replace(tmp, body_path)
                index = _load_static_cache_index(cache_dir)
                index[key] = {
                    "body_path": str(body_path.relative_to(cache_dir)),
                    "body_sha256": body_sha,
                    "body_len": len(body),
                    "status": status,
                    "headers": headers,
                    "created_at": now,
                    "last_hit_at": 0,
                    "hit_count": 0,
                    "source_url": url,
                }
                _save_static_cache_index(cache_dir, index)
                logger.info("[outlook-browser] static cache save label=%s url=%s sha256=%s bytes=%s key=%s", label, url, body_sha, len(body), key)
            route.fulfill(status=status, headers=headers, body=body)
        except Exception as e:
            logger.debug("[outlook-browser] static cache fetch failed label=%s url=%s error=%s", label, url, e)
            route.continue_()

    try:
        ctx.route("**/*", handler)
    except Exception as e:
        logger.debug("[outlook-browser] static cache install failed label=%s error=%s", label, e)


def _handle_data_export_consent(page, *, max_attempts: int = 4) -> bool:
    clicked = False
    artifacts = _artifact_dir()
    markers = (
        "个人数据导出许可",
        "同意并继续",
        "拒绝并退出",
        "personal data export",
        "agree and continue",
        "decline and exit",
    )
    for attempt in range(1, max_attempts + 1):
        page.wait_for_timeout(1000)
        text = _body_text(page)
        lower_text = text.lower()
        url = str(getattr(page, "url", "") or "")
        if not any(marker in text or marker in lower_text for marker in markers):
            break
        logger.info("[outlook-browser] data export consent detected attempt=%s url=%s", attempt, url)
        _write_form_artifacts(page, f"data_export_consent_{attempt}")
        try:
            page.screenshot(path=str(artifacts / f"data_export_consent_{attempt}_{int(time.time())}.png"), full_page=True)
        except Exception:
            pass
        if not _click_first(
            page,
            [
                'button:has-text("同意并继续")',
                'input[type="submit"][value*="同意"]',
                '[role="button"]:has-text("同意并继续")',
                'button:has-text("Agree and continue")',
                'button:has-text("Accept")',
                'button:has-text("Continue")',
                'input[type="submit"][value*="Agree"]',
                "#iNext",
                "#iAgree",
                "#acceptButton",
            ],
            timeout=5000,
        ):
            raise RuntimeError("Outlook browser fallback: data export consent button not found")
        clicked = True
        page.wait_for_load_state("domcontentloaded", timeout=15000)
        page.wait_for_timeout(2500)
    if clicked:
        _write_form_artifacts(page, "after_data_export_consent")
    return clicked


def prewarm_outlook_px_cookies(cfg: Config, *, timeout_s: float = 25.0) -> list[dict[str, Any]]:
    """Open the signup authorize flow just long enough for hsprotect PX cookies."""
    proxy = _parse_proxy(str(getattr(cfg, "proxy", "") or "")) if getattr(cfg, "proxy", None) else None
    geoip = _camoufox_geoip_enabled(proxy)
    headless = _camoufox_headless()
    profile = tempfile.mkdtemp(prefix="outlook_px_prewarm_")
    logger.info(
        "[outlook-browser] px prewarm Camoufox headless=%s profile=%s proxy=%s geoip=%s",
        headless,
        profile,
        bool(proxy),
        geoip,
    )

    from camoufox.sync_api import Camoufox
    try:
        from browserforge.fingerprints import Screen
    except ModuleNotFoundError:
        Screen = None

    camoufox_kwargs = {
        "headless": headless,
        "humanize": True,
        "persistent_context": True,
        "user_data_dir": profile,
        "os": _camoufox_os_for_cfg(cfg),
        "proxy": proxy,
        "geoip": geoip,
        "locale": _camoufox_locale_for_cfg(cfg),
    }
    if Screen is not None:
        camoufox_kwargs["screen"] = Screen(max_width=1920, max_height=1080)

    wanted = {"_px3", "_pxde", "_pxvid"}
    try:
        with Camoufox(**camoufox_kwargs) as ctx:
            _install_hsprotect_js_patch(ctx, label="px_prewarm")
            _install_static_resource_cache(ctx, label="px_prewarm")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(_browser_signup_authorize_url(cfg), wait_until="domcontentloaded", timeout=45000)
            _handle_data_export_consent(page, max_attempts=3)
            deadline = time.time() + max(5.0, float(timeout_s or 25.0))
            found: list[dict[str, Any]] = []
            while time.time() < deadline:
                try:
                    cookies = ctx.cookies([
                        "https://signup.live.com",
                        "https://login.live.com",
                        "https://iframe.hsprotect.net",
                        "https://collector-pxzc5j78di.hsprotect.net",
                    ])
                except Exception:
                    cookies = []
                by_name: dict[str, dict[str, Any]] = {}
                for cookie in cookies or []:
                    name = str(cookie.get("name") or "")
                    if name in wanted and str(cookie.get("value") or ""):
                        by_name[name] = cookie
                found = [by_name[name] for name in sorted(by_name)]
                if wanted.issubset(set(by_name)):
                    break
                page.wait_for_timeout(1000)
            logger.info(
                "[outlook-browser] px prewarm result names=%s url=%s",
                [str(c.get("name") or "") for c in found],
                str(getattr(page, "url", "") or ""),
            )
            return found
    finally:
        if str(os.environ.get("OUTLOOK_KEEP_BROWSER_PROFILE", "")).strip().lower() not in {"1", "true", "yes", "on"}:
            shutil.rmtree(profile, ignore_errors=True)


def _frame_challenge_snapshot(frame) -> dict:
    try:
        return frame.evaluate(
            """
            () => {
              const visible = el => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 3 && r.height > 3 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const selectors = [
                'button',
                '[role=button]',
                '#px-captcha',
                '[id*=captcha i]',
                '[class*=captcha i]',
                'canvas',
                'svg',
                'div'
              ];
              const seen = new Set();
              const candidates = [];
              for (const sel of selectors) {
                for (const el of document.querySelectorAll(sel)) {
                  if (seen.has(el) || !visible(el)) continue;
                  seen.add(el);
                  const r = el.getBoundingClientRect();
                  candidates.push({
                    tag: el.tagName,
                    id: el.id || '',
                    cls: String(el.className || '').slice(0, 160),
                    role: el.getAttribute('role') || '',
                    aria: el.getAttribute('aria-label') || '',
                    text: (el.innerText || el.value || el.textContent || '').trim().slice(0, 180),
                    rect: { x: r.x, y: r.y, width: r.width, height: r.height }
                  });
                  if (candidates.length >= 80) break;
                }
                if (candidates.length >= 80) break;
              }
              return {
                url: location.href,
                text: (document.body && document.body.innerText || '').slice(0, 500),
                candidates
              };
            }
            """
        ) or {}
    except Exception:
        return {}


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


def _challenge_still_visible(page) -> bool:
    text = _body_text(page).lower()
    url = str(getattr(page, "url", "") or "").lower()
    return any(k in text or k in url for k in ("press and hold", "prove you're human", "px-captcha", "captcha", "按住", "长按"))


def _challenge_combined_text(page) -> str:
    parts = [_body_text(page)]
    for frame in getattr(page, "frames", []) or []:
        frame_url = str(getattr(frame, "url", "") or "")
        if "iframe.hsprotect.net" not in frame_url:
            continue
        try:
            text = frame.evaluate(
                "() => (document.body && document.body.innerText || '')"
            )
            if text:
                parts.append(str(text))
        except Exception:
            continue
    return "\n".join(parts).lower()


def _challenge_frame_status(page) -> str:
    for frame in getattr(page, "frames", []) or []:
        frame_url = str(getattr(frame, "url", "") or "")
        if "iframe.hsprotect.net" not in frame_url:
            continue
        try:
            status = frame.evaluate(
                """
                () => {
                  const text = (document.body && document.body.innerText || '').toLowerCase();
                  const aria = Array.from(document.querySelectorAll('[aria-label], [aria-live]'))
                    .map(el => `${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`)
                    .join(' ')
                    .toLowerCase();
                  const combined = `${text} ${aria}`;
                  if (combined.includes('completed') || combined.includes('please wait')) return 'completed_wait';
                  if (combined.includes('press and hold') || combined.includes('human challenge')) return 'ready';
                  return combined ? 'unknown_text' : '';
                }
                """
            )
            if status:
                return str(status)
        except Exception:
            continue
    return ""


def _find_press_target_by_vision(page) -> dict | None:
    """Find the visible white press button from screenshot pixels only."""
    try:
        from PIL import Image, ImageDraw
    except Exception as e:
        logger.warning("[outlook-browser] vision press target unavailable: PIL import failed: %s", e)
        return None

    try:
        page.wait_for_timeout(1200)
        png = page.screenshot(full_page=False)
        img = Image.open(BytesIO(png)).convert("RGB")
        width, height = img.size
        viewport = page.viewport_size or {"width": width, "height": height}
        viewport_width = float(viewport.get("width") or width)
        viewport_height = float(viewport.get("height") or height)
        scale_x = viewport_width / max(1.0, float(width))
        scale_y = viewport_height / max(1.0, float(height))
        pix = img.load()
        min_y = int(height * 0.45)
        visited: set[tuple[int, int]] = set()
        candidates: list[dict] = []

        def is_button_pixel(x: int, y: int) -> bool:
            r, g, b = pix[x, y]
            if r > 238 and g > 238 and b > 238:
                return True
            # Anti-aliased white button edges / light gray fill.
            return r > 220 and g > 220 and b > 220 and max(r, g, b) - min(r, g, b) < 26

        for y in range(min_y, height - 1, 2):
            for x in range(0, width - 1, 2):
                if (x, y) in visited or not is_button_pixel(x, y):
                    continue
                stack = [(x, y)]
                visited.add((x, y))
                min_x = max_x = x
                min_cy = max_cy = y
                count = 0
                while stack:
                    px, py = stack.pop()
                    count += 1
                    if px < min_x:
                        min_x = px
                    elif px > max_x:
                        max_x = px
                    if py < min_cy:
                        min_cy = py
                    elif py > max_cy:
                        max_cy = py
                    for nx, ny in ((px + 2, py), (px - 2, py), (px, py + 2), (px, py - 2)):
                        if nx < 0 or ny < min_y or nx >= width or ny >= height or (nx, ny) in visited:
                            continue
                        if is_button_pixel(nx, ny):
                            visited.add((nx, ny))
                            stack.append((nx, ny))
                bw = max_x - min_x + 2
                bh = max_cy - min_cy + 2
                if count < 900 or bw < 180 or bh < 34 or bh > 95:
                    continue
                aspect = bw / max(1, bh)
                if aspect < 3.0 or aspect > 14.0:
                    continue
                cx = min_x + bw / 2
                cy = min_cy + bh / 2
                # The real button is in the lower middle of the challenge card, not the page background.
                if cy < height * 0.55 or cx < width * 0.20 or cx > width * 0.80:
                    continue
                candidates.append({
                    "x": float(min_x),
                    "y": float(min_cy),
                    "width": float(bw),
                    "height": float(bh),
                    "count": count,
                    "cx": float(cx),
                    "cy": float(cy),
                })

        if not candidates:
            artifacts = _artifact_dir()
            ts = int(time.time())
            raw_path = artifacts / f"challenge_vision_no_target_{ts}.png"
            img.save(raw_path)
            logger.warning("[outlook-browser] vision press target not found screenshot=%s size=%sx%s", raw_path, width, height)
            return None

        candidates.sort(key=lambda c: (c["count"], c["width"]), reverse=True)
        chosen = candidates[0]
        artifacts = _artifact_dir()
        ts = int(time.time())
        debug = img.copy()
        draw = ImageDraw.Draw(debug)
        x, y, bw, bh = chosen["x"], chosen["y"], chosen["width"], chosen["height"]
        cx, cy = chosen["cx"], chosen["cy"]
        draw.rectangle((x, y, x + bw, y + bh), outline=(255, 0, 0), width=4)
        draw.line((cx - 18, cy, cx + 18, cy), fill=(255, 0, 0), width=4)
        draw.line((cx, cy - 18, cx, cy + 18), fill=(255, 0, 0), width=4)
        debug_path = artifacts / f"challenge_vision_target_{ts}.png"
        debug.save(debug_path)
        logger.info(
            "[outlook-browser] vision press target image_rect=%.0f,%.0f %.0fx%.0f image_point=%.0f,%.0f mouse_point=%.1f,%.1f screenshot=%sx%s viewport=%.0fx%.0f scale=%.4f,%.4f candidates=%s debug=%s",
            x,
            y,
            bw,
            bh,
            cx,
            cy,
            cx * scale_x,
            cy * scale_y,
            width,
            height,
            viewport_width,
            viewport_height,
            scale_x,
            scale_y,
            len(candidates),
            debug_path,
        )
        return {
            "x": x * scale_x,
            "y": y * scale_y,
            "width": bw * scale_x,
            "height": bh * scale_y,
            "_vision_target": True,
            "_vision_point": (cx * scale_x, cy * scale_y),
            "_vision_image_point": (cx, cy),
            "_vision_debug": str(debug_path),
        }
    except Exception as e:
        logger.warning("[outlook-browser] vision press target failed: %s", e)
        return None


def _find_press_target_box(page) -> dict | None:
    frame_button_selectors = [
        '[role="button"][aria-label*="按住"][aria-label*="人工挑战"]',
        '#IjoTBAQgIekJSnS[role="button"]',
        '[role="button"][aria-label*="按住"]',
        '[role="button"][aria-label*="人工挑战"]',
        '[role="button"][aria-label*="Hold" i]',
        '[role="button"][aria-label*="Press" i]',
    ]
    saw_hsprotect = False
    for frame in getattr(page, "frames", []):
        frame_url = str(getattr(frame, "url", "") or "")
        if "iframe.hsprotect.net" not in frame_url:
            continue
        saw_hsprotect = True
        for sel in frame_button_selectors:
            try:
                loc = frame.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=700):
                    box = loc.bounding_box()
                    if box and box["width"] > 80 and box["height"] > 25:
                        box["_frame_target"] = True
                        box["_iframe_button_target"] = True
                        box["_target_selector"] = sel
                        logger.info(
                            "[outlook-browser] iframe button target selector=%s url=%s rect=%.0f,%.0f %.0fx%.0f center=%.1f,%.1f status=%s",
                            sel,
                            frame_url,
                            float(box.get("x") or 0),
                            float(box.get("y") or 0),
                            float(box.get("width") or 0),
                            float(box.get("height") or 0),
                            float(box.get("x") or 0) + float(box.get("width") or 0) / 2,
                            float(box.get("y") or 0) + float(box.get("height") or 0) / 2,
                            _challenge_frame_status(page),
                        )
                        return box
            except Exception:
                continue

    if saw_hsprotect:
        return {"_pending_frame_target": True}

    parent_iframe_selectors = [
        '#human iframe[data-testid="humanCaptchaIframe"]',
        '#human iframe[src*="iframe.hsprotect.net"][src*="ch_ctx=1"]',
        'iframe[data-testid="humanCaptchaIframe"]',
        'iframe[src*="iframe.hsprotect.net"][src*="ch_ctx=1"]',
    ]
    for sel in parent_iframe_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=700):
                box = loc.bounding_box()
                if box and box["width"] > 80 and box["height"] > 40:
                    target = {
                        "x": float(box.get("x") or 0) + float(box.get("width") or 0) * 0.18,
                        "y": float(box.get("y") or 0) + float(box.get("height") or 0) * 0.16,
                        "width": float(box.get("width") or 0) * 0.64,
                        "height": float(box.get("height") or 0) * 0.62,
                        "_visual_iframe_target": True,
                        "_target_selector": sel,
                    }
                    logger.info(
                        "[outlook-browser] parent human iframe target selector=%s iframe=%.0f,%.0f %.0fx%.0f target=%.0f,%.0f %.0fx%.0f status=%s",
                        sel,
                        float(box.get("x") or 0),
                        float(box.get("y") or 0),
                        float(box.get("width") or 0),
                        float(box.get("height") or 0),
                        target["x"],
                        target["y"],
                        target["width"],
                        target["height"],
                        _challenge_frame_status(page),
                    )
                    return target
        except Exception:
            continue

    frame_selectors = [
        (130, "#human"),
        (125, '[id="human"]'),
        (120, '[role="button"] >> xpath=ancestor-or-self::*[@id="human"]'),
        (100, '[role="button"][aria-label*="按住"]'),
        (100, '[role="button"][aria-label*="人工挑战"]'),
        (95, '[role="button"][aria-label*="Press" i]'),
        (95, '[role="button"][aria-label*="Hold" i]'),
        (90, '[role="button"]:has-text("Press and hold")'),
        (90, '[role="button"]:has-text("Press & Hold")'),
        (90, '[role="button"]:has-text("按住")'),
        (70, '[role="button"]'),
        (60, 'button:has-text("Press and hold")'),
        (60, 'button:has-text("按住")'),
        (50, 'button'),
        (10, 'canvas'),
    ]
    frame_candidates: list[tuple[int, str, str, dict]] = []
    for frame in getattr(page, "frames", []):
        frame_url = str(getattr(frame, "url", "") or "")
        if "iframe.hsprotect.net" not in frame_url:
            continue
        saw_hsprotect = True
        for score, sel in frame_selectors:
            try:
                loc = frame.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=700):
                    box = loc.bounding_box()
                    if box and box["width"] > 30 and box["height"] > 20:
                        box["_frame_target"] = True
                        box["_target_selector"] = sel
                        if sel != "#human" and sel != '[id="human"]':
                            try:
                                human_box = loc.evaluate(
                                    """el => {
                                      const human = el.id === 'human' ? el : el.closest('#human');
                                      if (!human) return null;
                                      const r = human.getBoundingClientRect();
                                      return { x: r.x, y: r.y, width: r.width, height: r.height };
                                    }"""
                                )
                                if human_box and float(human_box.get("width") or 0) > 30 and float(human_box.get("height") or 0) > 20:
                                    box.update({
                                        "x": float(human_box.get("x") or 0),
                                        "y": float(human_box.get("y") or 0),
                                        "width": float(human_box.get("width") or 0),
                                        "height": float(human_box.get("height") or 0),
                                        "_target_selector": "#human-via-" + sel,
                                    })
                                    score = max(score, 128)
                            except Exception:
                                pass
                        if float(box.get("width") or 0) > 320 and sel == "#px-captcha":
                            score -= 10
                        frame_candidates.append((score, sel, frame_url, box))
            except Exception:
                continue
    if frame_candidates:
        score, sel, frame_url, box = max(frame_candidates, key=lambda item: item[0])
        target_sel = str(box.get("_target_selector") or sel)
        logger.info(
            "[outlook-browser] frame press target selector=%s score=%s url=%s rect=%.0f,%.0f %.0fx%.0f status=%s",
            target_sel,
            score,
            frame_url,
            float(box.get("x") or 0),
            float(box.get("y") or 0),
            float(box.get("width") or 0),
            float(box.get("height") or 0),
            _challenge_frame_status(page),
        )
        return box
    if saw_hsprotect:
        return {"_pending_frame_target": True}

    iframe_selectors = [
        'iframe[data-testid="humanCaptchaIframe"]',
        'iframe[title*="Verification challenge" i]',
        'iframe[src*="iframe.hsprotect.net"][src*="ch_ctx=1"]',
        'iframe[src*="iframe.hsprotect.net"]',
    ]
    for sel in iframe_selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=700):
                box = loc.bounding_box()
                if box and box["width"] > 80 and box["height"] > 40:
                    target = {
                        "x": float(box.get("x") or 0) + float(box.get("width") or 0) * 0.25,
                        "y": float(box.get("y") or 0) + 1.0,
                        "width": float(box.get("width") or 0) * 0.63,
                        "height": min(42.0, float(box.get("height") or 0)),
                        "_visual_iframe_target": True,
                    }
                    logger.info(
                        "[outlook-browser] visual iframe press target selector=%s iframe=%.0f,%.0f %.0fx%.0f target=%.0f,%.0f %.0fx%.0f status=%s",
                        sel,
                        float(box.get("x") or 0),
                        float(box.get("y") or 0),
                        float(box.get("width") or 0),
                        float(box.get("height") or 0),
                        target["x"],
                        target["y"],
                        target["width"],
                        target["height"],
                        _challenge_frame_status(page),
                    )
                    return target
        except Exception:
            continue

    selectors = [
        'button:has-text("Press and hold")',
        'button:has-text("press and hold")',
        '[role="button"]:has-text("Press and hold")',
        'button:has-text("按住")',
        'button:has-text("长按")',
        'button:has-text("Appuyer et maintenir")',
        "#px-captcha",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=700):
                box = loc.bounding_box()
                if box and box["width"] > 30 and box["height"] > 10:
                    return box
        except Exception:
            continue
    for frame in getattr(page, "frames", []):
        try:
            for sel in selectors:
                loc = frame.locator(sel).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    box = loc.bounding_box()
                    if box and box["width"] > 30 and box["height"] > 10:
                        return box
        except Exception:
            continue
    snap = _challenge_snapshot(page)
    scored: list[tuple[int, dict]] = []
    for cand in snap.get("candidates") or []:
        text = " ".join(str(cand.get(k) or "") for k in ("text", "aria", "id", "cls", "src")).lower()
        rect = cand.get("rect") or {}
        if not rect or float(rect.get("width") or 0) < 30 or float(rect.get("height") or 0) < 10:
            continue
        score = 0
        if "press" in text and "hold" in text:
            score += 100
        if "px-captcha" in text or "hsprotect" in text:
            score += 60
        if cand.get("tag") == "BUTTON":
            score += 20
        if score:
            scored.append((score, {
                "x": float(rect.get("x") or 0),
                "y": float(rect.get("y") or 0),
                "width": float(rect.get("width") or 0),
                "height": float(rect.get("height") or 0),
            }))
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]
    return _find_press_target_by_vision(page)


def _refine_press_target_box(page, box: dict) -> dict:
    """Avoid holding the instruction text; move to the actual white button."""
    try:
        refined = page.evaluate(
            """box => {
              const cx = box.x + box.width / 2;
              const cy = box.y + box.height / 2;
              const rectObj = el => {
                const r = el.getBoundingClientRect();
                return { x: r.x, y: r.y, width: r.width, height: r.height };
              };
              const direct = document.elementFromPoint(cx, cy);
              if (direct && direct.tagName === 'IFRAME' && String(direct.src || '').includes('iframe.hsprotect.net')) {
                return rectObj(direct);
              }
              const isBetter = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                if (r.width < 80 || r.height < 24) return false;
                const text = (el.innerText || el.value || el.textContent || '').toLowerCase();
                const tag = el.tagName;
                return tag === 'BUTTON' || el.getAttribute('role') === 'button' || text.includes('press and hold');
              };
              let el = direct;
              let cur = el;
              while (cur && cur !== document.body) {
                if (isBetter(cur)) return rectObj(cur);
                cur = cur.parentElement;
              }
              for (const dy of [28, 40, 52, 64, 76, 92]) {
                for (const dx of [0, -80, 80, -140, 140]) {
                  el = document.elementFromPoint(cx + dx, cy + dy);
                  cur = el;
                  while (cur && cur !== document.body) {
                    if (isBetter(cur)) return rectObj(cur);
                    cur = cur.parentElement;
                  }
                }
              }
              return null;
            }""",
            box,
        )
        if refined and refined.get("width", 0) > 30 and refined.get("height", 0) > 10:
            return refined
    except Exception:
        pass
    if float(box.get("height") or 0) < 32:
        return {
            "x": max(0, float(box.get("x") or 0) - 40),
            "y": float(box.get("y") or 0) + 42,
            "width": max(180, float(box.get("width") or 0) + 80),
            "height": 44,
        }
    return box


def _press_and_hold(page, *, max_press: int = 4, use_registration_success_heuristic: bool = True) -> bool:
    _install_challenge_hooks(page)
    if _challenge_still_visible(page):
        _write_challenge_artifacts(page, label="initial")
    did_first_tap = False
    for attempt in range(1, max_press + 1):
        target_box = None
        target_deadline = time.time() + 8
        while time.time() < target_deadline:
            target_box = _find_press_target_box(page)
            if target_box and not target_box.get("_pending_frame_target"):
                break
            page.wait_for_timeout(500)
        if not target_box:
            snap = _challenge_snapshot(page)
            _write_challenge_artifacts(page, label="no_target", attempt=attempt)
            logger.warning(
                "[outlook-browser] press target not found url=%s candidates=%s text=%s",
                snap.get("url") or getattr(page, "url", ""),
                len(snap.get("candidates") or []),
                str(snap.get("text") or "")[:180],
            )
            continue
        if target_box.get("_pending_frame_target"):
            _write_challenge_artifacts(page, label="pending_frame_target", attempt=attempt)
            logger.warning("[outlook-browser] hsprotect frame present but inner press target not ready")
            page.wait_for_timeout(1500)
            continue
        vision_target = bool(target_box.get("_vision_target"))
        visual_target = bool(target_box.get("_visual_iframe_target"))
        iframe_button_target = bool(target_box.get("_iframe_button_target"))
        if not target_box.get("_frame_target") and not visual_target and not vision_target:
            target_box = _refine_press_target_box(page, target_box)

        bx, by, bw, bh = target_box["x"], target_box["y"], target_box["width"], target_box["height"]
        logger.info("[outlook-browser] press target attempt=%s rect=%.1f,%.1f %.1fx%.1f", attempt, bx, by, bw, bh)
        if vision_target and target_box.get("_vision_point"):
            cx, cy = target_box["_vision_point"]
        elif visual_target or iframe_button_target:
            cx = bx + bw / 2
            cy = by + bh / 2
        elif str(target_box.get("_target_selector") or "").startswith("#human"):
            cx = bx + bw * 0.50
            cy = by + bh * 0.64
        else:
            cx = bx + bw * random.uniform(0.45, 0.55)
            cy = by + bh * random.uniform(0.45, 0.58)

        def move_to_target() -> None:
            if vision_target or iframe_button_target:
                page.mouse.move(cx, cy, steps=4)
                page.wait_for_timeout(random.randint(100, 180))
                return
            sx = max(20, min(cx + random.uniform(-320, 320), 1180))
            sy = max(20, min(cy + random.uniform(-220, 220), 680))
            page.mouse.move(sx, sy, steps=random.randint(4, 8))
            time.sleep(random.uniform(0.2, 0.6))
            steps = random.randint(24, 42)
            ctrl_x = (sx + cx) / 2 + random.uniform(-90, 90)
            ctrl_y = (sy + cy) / 2 + random.uniform(-70, 70)
            for step in range(1, steps + 1):
                t = step / steps
                mx = (1 - t) ** 2 * sx + 2 * (1 - t) * t * ctrl_x + t**2 * cx + random.uniform(-1.3, 1.3)
                my = (1 - t) ** 2 * sy + 2 * (1 - t) * t * ctrl_y + t**2 * cy + random.uniform(-1.3, 1.3)
                page.mouse.move(mx, my)
                time.sleep(random.uniform(0.005, 0.025))
            page.mouse.move(cx, cy)
            page.wait_for_timeout(random.randint(120, 320))

        snap_text = _challenge_combined_text(page)
        needs_first_tap = any(
            marker in snap_text
            for marker in (
                "press the button once",
                "press again when prompted",
                "请按一次按钮",
                "再按一次",
            )
        )
        first_tap_enabled = str(os.environ.get("OUTLOOK_CHALLENGE_FIRST_TAP", "")).strip().lower() in ("1", "true", "yes")
        if first_tap_enabled and needs_first_tap and not did_first_tap:
            move_to_target()
            page.mouse.down()
            page.wait_for_timeout(random.randint(180, 420))
            page.mouse.up()
            did_first_tap = True
            logger.info("[outlook-browser] challenge first tap attempt=%s", attempt)
            confirm_deadline = time.time() + random.uniform(0.8, 1.6)
            while time.time() < confirm_deadline:
                if _is_blocked(page):
                    return False
                if use_registration_success_heuristic and (_is_success_page(page) or bool(_last_frontend_create_redirect(page))):
                    return True
                page.wait_for_timeout(400)

        move_to_target()
        hook_before_press = _challenge_hook_status(page)
        hook_since_t = float(hook_before_press.get("lastMessageTime") or 0)
        logger.info(
            "[outlook-browser] press evidence before attempt=%s hook_since_t=%s hook=%s center=%.1f,%.1f iframe_button=%s vision=%s",
            attempt,
            hook_since_t,
            _safe_json_dumps(hook_before_press, limit=1200),
            cx,
            cy,
            bool(iframe_button_target),
            bool(vision_target),
        )
        down_wall = time.time()
        page.mouse.down()
        logger.info("[outlook-browser] press evidence down attempt=%s wall=%.3f center=%.1f,%.1f", attempt, down_wall, cx, cy)
        hold_min = float(os.environ.get("OUTLOOK_HOLD_MIN_S", "6.2") or "6.2")
        hold_max_default = "42" if iframe_button_target else "7.4"
        hold_max_cfg = float(os.environ.get("OUTLOOK_HOLD_MAX_S", hold_max_default) or hold_max_default)
        if hold_max_cfg < hold_min:
            hold_max_cfg = hold_min + 0.8
        hold_max = hold_max_cfg if iframe_button_target else random.uniform(hold_min, hold_max_cfg)
        end = time.time() + hold_max
        solved_during_hold = False
        failed_during_hold = False
        hold_started = time.time()
        while time.time() < end:
            if not vision_target:
                jitter = 0.25 if iframe_button_target else 0.8
                page.mouse.move(cx + random.uniform(-jitter, jitter), cy + random.uniform(-jitter, jitter))
            if iframe_button_target and time.time() - hold_started >= hold_min:
                hook_status = _challenge_hook_status(page, since_t=hook_since_t)
                if hook_status.get("completed"):
                    solved_during_hold = True
                    logger.info(
                        "[outlook-browser] challenge hook completed during hold attempt=%s held_s=%.1f last_t=%s last=%s",
                        attempt,
                        time.time() - hold_started,
                        hook_status.get("lastMessageTime"),
                        str(hook_status.get("lastMessage") or "")[:140],
                    )
                    break
                if hook_status.get("failed"):
                    failed_during_hold = True
                    logger.info(
                        "[outlook-browser] challenge hook failed during hold attempt=%s held_s=%.1f last_t=%s",
                        attempt,
                        time.time() - hold_started,
                        hook_status.get("lastMessageTime"),
                    )
                    break
                if use_registration_success_heuristic and (_is_success_page(page) or bool(_last_frontend_create_redirect(page))):
                    solved_during_hold = True
                    break
            time.sleep(random.uniform(0.08, 0.25))
        up_wall = time.time()
        page.mouse.up()
        hook_after_up = _challenge_hook_status(page, since_t=hook_since_t)
        logger.info(
            "[outlook-browser] press evidence up attempt=%s wall=%.3f held_s=%.3f hook_after_up=%s",
            attempt,
            up_wall,
            up_wall - down_wall,
            _safe_json_dumps(hook_after_up, limit=1600),
        )
        logger.info(
            "[outlook-browser] press-and-hold attempt=%s held_s=%.1f solved_during_hold=%s failed_during_hold=%s",
            attempt,
            time.time() - hold_started,
            solved_during_hold,
            failed_during_hold,
        )
        if solved_during_hold:
            parent_wait = time.time() + 45
            while time.time() < parent_wait:
                if use_registration_success_heuristic and (_is_success_page(page) or bool(_last_frontend_create_redirect(page))):
                    return True
                if _is_blocked(page):
                    return False
                page.wait_for_timeout(500)
        if failed_during_hold:
            continue
        end_wait = time.time() + float(os.environ.get("OUTLOOK_PRESS_POST_WAIT_S", "14") or "14")
        while time.time() < end_wait:
            text = _body_text(page).lower()
            frame_status = _challenge_frame_status(page)
            if frame_status == "completed_wait":
                logger.info("[outlook-browser] challenge frame completed; waiting for parent page")
                parent_wait = time.time() + 45
                while time.time() < parent_wait:
                    if use_registration_success_heuristic and (_is_success_page(page) or bool(_last_frontend_create_redirect(page))):
                        return True
                    if _is_blocked(page):
                        return False
                    page.wait_for_timeout(1000)
                break
            if use_registration_success_heuristic and (_is_success_page(page) or bool(_last_frontend_create_redirect(page))):
                return True
            page.wait_for_timeout(1000)
            hook_after_wait = _challenge_hook_status(page, since_t=hook_since_t)
            logger.info(
                "[outlook-browser] press evidence post-wait attempt=%s remaining_s=%.1f hook=%s",
                attempt,
                max(0.0, end_wait - time.time()),
                _safe_json_dumps(hook_after_wait, limit=1600),
            )
        snap = _challenge_snapshot(page)
        logger.info(
            "[outlook-browser] press evidence snapshot-before-retry attempt=%s text=%s hook=%s",
            attempt,
            str(snap.get("text") or "").replace("\n", " | ")[:300],
            _safe_json_dumps(_challenge_hook_status(page, since_t=hook_since_t), limit=1600),
        )
        _write_challenge_artifacts(page, label="after_press", attempt=attempt)
        logger.info(
            "[outlook-browser] challenge snapshot attempt=%s candidates=%s last_events=%s text=%s",
            attempt,
            len(snap.get("candidates") or []),
            (snap.get("log") or [])[-5:],
            str(snap.get("text") or "")[:180],
        )
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


def _bridge_hsprotect_px_cookies(ctx, page, *, label: str = "challenge") -> bool:
    """Copy PX cookies produced inside hsprotect iframe onto Live signup domains."""
    wanted = {"_pxvid", "_px3", "_pxde"}
    try:
        source_cookies = ctx.cookies(["https://iframe.hsprotect.net", "https://signup.live.com"])
    except Exception as e:
        logger.debug("[outlook-browser] px cookie bridge read failed: %s", e)
        return False

    by_name: dict[str, dict] = {}
    for cookie in source_cookies or []:
        name = str(cookie.get("name") or "")
        domain = str(cookie.get("domain") or "")
        value = str(cookie.get("value") or "")
        if name not in wanted or not value:
            continue
        current = by_name.get(name)
        if current is None or domain.endswith("hsprotect.net"):
            by_name[name] = cookie

    bridge_cookies: list[dict] = []
    for name in sorted(wanted):
        src = by_name.get(name)
        if not src:
            continue
        base = {
            "name": name,
            "value": str(src.get("value") or ""),
            "path": "/",
            "secure": True,
            "httpOnly": bool(src.get("httpOnly", False)),
        }
        same_site = src.get("sameSite")
        if same_site in ("Strict", "Lax", "None"):
            base["sameSite"] = same_site
        expires = src.get("expires")
        if isinstance(expires, (int, float)) and expires > 0:
            base["expires"] = int(expires)
        for domain in ("signup.live.com", ".signup.live.com", ".live.com"):
            cloned = dict(base)
            cloned["domain"] = domain
            bridge_cookies.append(cloned)

    if not bridge_cookies:
        logger.info("[outlook-browser] px cookie bridge label=%s no source cookies found", label)
        return False

    try:
        ctx.add_cookies(bridge_cookies)
    except Exception as e:
        logger.warning("[outlook-browser] px cookie bridge add failed label=%s error=%s", label, e)
        return False

    try:
        live_cookies = ctx.cookies("https://signup.live.com")
    except Exception:
        live_cookies = []
    live_names = {str(c.get("name") or "") for c in live_cookies or []}
    ok = wanted.issubset(live_names)

    try:
        artifacts = _artifact_dir()
        report = {
            "label": label,
            "source": [
                {
                    "domain": c.get("domain"),
                    "name": c.get("name"),
                    "len": len(str(c.get("value") or "")),
                    "expires": c.get("expires"),
                }
                for c in source_cookies or []
                if str(c.get("name") or "") in wanted
            ],
            "injected": [
                {
                    "domain": c.get("domain"),
                    "name": c.get("name"),
                    "len": len(str(c.get("value") or "")),
                    "expires": c.get("expires"),
                }
                for c in bridge_cookies
            ],
            "live_names": sorted(live_names),
            "ok": ok,
        }
        (artifacts / f"px_cookie_bridge_{label}_{int(time.time())}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.debug("[outlook-browser] px cookie bridge report failed: %s", e)

    logger.info(
        "[outlook-browser] px cookie bridge label=%s has_signup_px3=%s has_signup_pxde=%s has_signup_pxvid=%s source=%s injected=%s",
        label,
        "_px3" in live_names,
        "_pxde" in live_names,
        "_pxvid" in live_names,
        sorted(by_name),
        len(bridge_cookies),
    )
    if ok:
        try:
            page.evaluate(
                """cookies => {
                  const expiresText = expires => {
                    if (typeof expires === 'number' && expires > 0) {
                      return new Date(expires * 1000).toUTCString();
                    }
                    return new Date(Date.now() + 31536e6).toUTCString();
                  };
                  for (const c of cookies) {
                    if (!c || !c.name || !c.value) continue;
                    const exp = expiresText(c.expires);
                    try {
                      document.cookie = `${c.name}=${c.value}; expires=${exp}; path=/; secure; SameSite=Lax`;
                    } catch (_) {}
                    const data = { type: 'cookie', name: c.name, value: c.value, expires: exp };
                    try {
                      window.dispatchEvent(new MessageEvent('message', {
                        data,
                        origin: 'https://iframe.hsprotect.net',
                        source: window
                      }));
                    } catch (_) {}
                  }
                  try {
                    window.dispatchEvent(new MessageEvent('message', {
                      data: { type: 'px-cookie-bridge-complete' },
                      origin: 'https://iframe.hsprotect.net',
                      source: window
                    }));
                  } catch (_) {}
                  return document.cookie;
                }""",
                [
                    {
                        "name": name,
                        "value": str(by_name[name].get("value") or ""),
                        "expires": by_name[name].get("expires"),
                    }
                    for name in sorted(wanted)
                    if name in by_name
                ],
            )
        except Exception:
            pass
    return ok


def _trigger_hsprotect_success_callbacks(page, *, label: str) -> bool:
    try:
        result = page.evaluate(
            """label => {
              const sent = [];
              const payloads = [
                { type: 'captcha', action: 'success', status: 'success', label },
                { type: 'captcha', action: 'complete', status: 'success', label },
                { type: 'success', source: 'hsprotect', label },
                { type: 'complete', source: 'hsprotect', label }
              ];
              for (const payload of payloads) {
                try {
                  window.dispatchEvent(new MessageEvent('message', {
                    data: payload,
                    origin: 'https://iframe.hsprotect.net',
                    source: window
                  }));
                  sent.push(payload.type + ':' + (payload.action || payload.status || ''));
                } catch (_) {}
              }
              return { sent };
            }""",
            label,
        ) or {}
        frame_results = []
        for frame in getattr(page, "frames", []) or []:
            frame_url = str(getattr(frame, "url", "") or "")
            if "iframe.hsprotect.net" not in frame_url:
                continue
            try:
                frame_results.append(
                    frame.evaluate(
                        """() => {
                          const out = { url: location.href, called: false, hasCallback: typeof window._pxOnCaptchaSuccess === 'function' };
                          try {
                            if (typeof window._pxOnCaptchaSuccess === 'function') {
                              window._pxOnCaptchaSuccess();
                              out.called = true;
                            }
                          } catch (e) {
                            out.error = String(e && e.message || e);
                          }
                          try {
                            window.parent.postMessage({ type: 'captcha', action: 'success', status: 'success' }, '*');
                            window.parent.postMessage({ type: 'success', source: 'hsprotect' }, '*');
                          } catch (_) {}
                          return out;
                        }"""
                    )
                )
            except Exception as e:
                frame_results.append({"url": frame_url, "error": str(e)})
        logger.info("[outlook-browser] hsprotect success callbacks label=%s parent=%s frames=%s", label, result, frame_results)
        page.wait_for_timeout(3000)
        return True
    except Exception as e:
        logger.debug("[outlook-browser] hsprotect success callbacks failed label=%s error=%s", label, e)
        return False


def _continue_after_px_bridge(page, *, label: str) -> bool:
    try:
        action = page.evaluate(
            """() => {
              const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none';
              };
              const textOf = el => `${el.id || ''} ${el.name || ''} ${el.getAttribute('aria-label') || ''} ${el.value || ''} ${el.innerText || el.textContent || ''}`.toLowerCase();
              const ignored = el => {
                const t = textOf(el);
                return t.includes('back') || t.includes('上一步') || t.includes('帮助') || t.includes('feedback') || t.includes('terms') || t.includes('privacy');
              };
              const buttons = [...document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')]
                .filter(el => visible(el) && !ignored(el));
              const preferred = buttons.find(el => {
                const t = textOf(el);
                return t.includes('next') || t.includes('continue') || t.includes('submit') || t.includes('下一步') || t.includes('继续') || t.includes('同意');
              }) || buttons.find(el => el.id === 'iSignupAction' || el.type === 'submit') || buttons[0];
              if (preferred) {
                setTimeout(() => {
                  try {
                    preferred.scrollIntoView({ block: 'center', inline: 'center' });
                    preferred.focus();
                    preferred.click();
                  } catch (_) {}
                }, 0);
                return { action: 'click', text: textOf(preferred).slice(0, 160) };
              }
              return { action: 'no_action' };
            }"""
        )
        logger.info("[outlook-browser] px bridge continue label=%s action=%s", label, action)
        if isinstance(action, dict) and action.get("action") == "no_action":
            return False
        page.wait_for_timeout(8000)
        return _is_success_page(page) or bool(_last_frontend_create_redirect(page))
    except Exception as e:
        logger.debug("[outlook-browser] px bridge continue failed label=%s error=%s", label, e)
        return False


def _last_frontend_create_redirect(page) -> str:
    return str(getattr(page, "_outlook_last_create_redirect", "") or "").strip()


def _last_frontend_create_error(page) -> tuple[str, str]:
    return (
        str(getattr(page, "_outlook_last_create_error", "") or "").strip(),
        str(getattr(page, "_outlook_last_create_error_field", "") or "").strip(),
    )


def _create_account_with_browser_api(
    page,
    *,
    email: str,
    password: str,
    cfg: Config,
    label: str,
    first_name: str = "",
    last_name: str = "",
    birth_date: str = "",
) -> bool:
    country = str(_cfg_value(cfg, "country", "") or "").strip().upper() or "JP"
    api_first_name = str(_cfg_value(cfg, "first_name", "") or "")
    api_last_name = str(_cfg_value(cfg, "last_name", "") or "")
    if not birth_date:
        birth_date = ":".join(reversed(_birth_parts()))
    try:
        result = page.evaluate(
            """async args => {
              const cachedSd = window.__outlookSignupServerData || {};
              const runtimeSd = window.ServerData || {};
              const valueOf = key => {
                const runtimeValue = runtimeSd[key];
                if (runtimeValue !== undefined && runtimeValue !== null && runtimeValue !== '') return runtimeValue;
                return cachedSd[key];
              };
              const sd = new Proxy({}, { get: (_, key) => valueOf(key) });
              const q = sd.search || location.search || '';
              const uaid = sd.uaid || new URLSearchParams(q).get('uaid') || '';
              const hpgid = sd.hpgid || 200225;
              const uiflvr = sd.iUiFlavor || 1;
              const scid = sd.iScenarioId || 100118;
              let apiCanary = sd.apiCanary || sd.canary || '';
              const checkUrl = (sd.urlCheckAvailableSigninNames || 'https://signup.live.com/API/CheckAvailableSigninNames') + q;
              const createUrl = (sd.urlCreateAccount || 'https://signup.live.com/API/CreateAccount') + q;
              const commonHeaders = () => ({
                'Accept': 'application/json',
                'Content-Type': 'application/json; charset=utf-8',
                'canary': apiCanary,
                'client-request-id': uaid,
                'correlationId': uaid,
                'hpgid': String(hpgid),
                'hpgact': '0'
              });
              const checkBody = {
                includeSuggestions: true,
                signInName: args.email,
                uiflvr,
                scid,
                uaid,
                hpgid
              };
              const checkResp = await fetch(checkUrl, {
                method: 'POST',
                credentials: 'include',
                headers: commonHeaders(),
                body: JSON.stringify(checkBody)
              });
              let checkData = null;
              let checkText = '';
              try { checkData = await checkResp.json(); } catch (_) { checkText = await checkResp.text(); }
              if (checkData && checkData.apiCanary) apiCanary = checkData.apiCanary;
              const body = {
                BirthDate: args.birthDate,
                CheckAvailStateMap: [`${args.email}:false`],
                Country: args.country,
                EvictionWarningShown: [],
                FirstName: args.firstName,
                IsRDM: false,
                IsOptOutEmailDefault: true,
                IsOptOutEmailShown: 1,
                IsOptOutEmail: true,
                IsUserConsentedToChinaPIPL: true,
                LastName: args.lastName,
                LW: 1,
                MemberName: args.email,
                RequestTimeStamp: new Date().toISOString(),
                ReturnUrl: sd.sReturnUrl || '',
                SignupReturnUrl: sd.sSignupReturnUrl || new URLSearchParams(location.search).get('sru') || '',
                SuggestedAccountType: 'EASI',
                SiteId: sd.sSiteId || '',
                VerificationCodeSlt: '',
                PrivateAccessToken: '',
                WReply: sd.sWReply || '',
                MemberNameChangeCount: 1,
                MemberNameAvailableCount: 1,
                MemberNameUnavailableCount: 0,
                Password: args.password,
                uiflvr,
                scid,
                uaid,
                hpgid
              };
              const resp = await fetch(createUrl, {
                method: 'POST',
                credentials: 'include',
                headers: commonHeaders(),
                body: JSON.stringify(body)
              });
              let data = null;
              let text = '';
              try { data = await resp.json(); } catch (_) { text = await resp.text(); }
              return {
                status: resp.status,
                url: resp.url,
                checkStatus: checkResp.status,
                checkKeys: checkData ? Object.keys(checkData).sort() : [],
                checkError: checkData && checkData.error ? checkData.error : null,
                checkAvailable: checkData && typeof checkData.isAvailable !== 'undefined' ? checkData.isAvailable : null,
                checkText: checkText.slice(0, 500),
                keys: data ? Object.keys(data).sort() : [],
                error: data && data.error ? data.error : null,
                hasRedirect: !!(data && (data.redirectUrl || data.redirect_url || data.redirect)),
                data,
                text: text.slice(0, 500),
                cookie: document.cookie,
                createBodyKeys: Object.keys(body).sort(),
                serverData: {
                  hasApiCanary: !!(sd.apiCanary || sd.canary),
                  hasCheckUrl: !!sd.urlCheckAvailableSigninNames,
                  hasCreateUrl: !!sd.urlCreateAccount,
                  fromCache: !!window.__outlookSignupServerData,
                  hpgid,
                  scid,
                  uiflvr,
                  uaid
                }
              };
            }""",
            {
                "email": email,
                "password": password,
                "country": country,
                "firstName": api_first_name,
                "lastName": api_last_name,
                "birthDate": birth_date,
            },
        )
        artifacts = _artifact_dir()
        (artifacts / f"browser_api_create_{label}_{int(time.time())}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        error_code = ""
        if isinstance(result, dict) and isinstance(result.get("error"), dict):
            error_code = str(result["error"].get("code") or "")
        try:
            setattr(page, "_outlook_last_browser_api_error", error_code)
            error_field = ""
            if isinstance(result, dict) and isinstance(result.get("error"), dict):
                error_field = str(result["error"].get("field") or "")
            setattr(page, "_outlook_last_browser_api_error_field", error_field)
        except Exception:
            pass
        logger.info(
            "[outlook-browser] browser api create label=%s check_status=%s check_available=%s status=%s keys=%s error_code=%s has_redirect=%s",
            label,
            result.get("checkStatus") if isinstance(result, dict) else "",
            result.get("checkAvailable") if isinstance(result, dict) else "",
            result.get("status") if isinstance(result, dict) else "",
            ",".join(result.get("keys") or []) if isinstance(result, dict) else "",
            error_code or "<none>",
            bool(result.get("hasRedirect")) if isinstance(result, dict) else False,
        )
        if isinstance(result, dict) and result.get("hasRedirect"):
            redirect = ""
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            for key in ("redirectUrl", "redirect_url", "redirect"):
                if data.get(key):
                    redirect = str(data[key])
                    break
            if redirect:
                page.goto(redirect, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
            return True
        return False
    except Exception as e:
        logger.debug("[outlook-browser] browser api create failed label=%s error=%s", label, e)
        return False


def _handle_challenge(
    cfg: Config,
    ctx,
    page,
    *,
    email: str = "",
    password: str = "",
    first_name: str = "",
    last_name: str = "",
    birth_date: str = "",
    early_abort: bool = True,
) -> bool:
    max_press_raw = os.environ.get("OUTLOOK_REG_MAX_PRESS", "").strip()
    max_press = int(max_press_raw) if max_press_raw.isdigit() else 4

    def replay_create(label: str) -> bool:
        if not email or not password:
            return False
        return _create_account_with_browser_api(
            page,
            email=email,
            password=password,
            cfg=cfg,
            label=label,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
        )

    def last_create_needs_human() -> bool:
        code = str(getattr(page, "_outlook_last_browser_api_error", "") or "")
        field = str(getattr(page, "_outlook_last_browser_api_error_field", "") or "").lower()
        return code == "1059" or field == "humancaptcha"

    def wait_frontend_after_press(label: str, seconds: float = 18.0) -> bool:
        try:
            deadline = time.time() + seconds
            while time.time() < deadline:
                redirect = _last_frontend_create_redirect(page)
                if redirect:
                    logger.info("[outlook-browser] frontend CreateAccount redirect observed label=%s", label)
                    try:
                        page.goto(redirect, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(5000)
                    except Exception as e:
                        logger.info("[outlook-browser] frontend redirect navigation failed label=%s error=%s", label, e)
                    return True
                error_code, error_field = _last_frontend_create_error(page)
                if error_code:
                    logger.info(
                        "[outlook-browser] frontend CreateAccount error observed label=%s code=%s field=%s",
                        label,
                        error_code,
                        error_field,
                    )
                    return False
                if _is_success_page(page):
                    logger.info("[outlook-browser] frontend completed after challenge label=%s", label)
                    return True
                if _is_blocked(page):
                    logger.info("[outlook-browser] frontend blocked after challenge label=%s", label)
                    return False
                if not _challenge_still_visible(page):
                    logger.info(
                        "[outlook-browser] challenge disappeared without CreateAccount redirect label=%s url=%s",
                        label,
                        getattr(page, "url", ""),
                    )
                    return False
                page.wait_for_timeout(1000)
        except Exception as e:
            if type(e).__name__ == "TargetClosedError":
                logger.warning("[outlook-browser] page closed while waiting after challenge label=%s", label)
                return False
            raise
        return False

    # Evidence from runtime traces shows the native Microsoft front-end drives
    # risk/verify and then posts configuration into the hsprotect iframe.  Manual
    # _px cookie bridging plus direct CreateAccount replay still returns
    # 1059/humanCaptcha, so keep the first pass inside the browser state machine.
    if _press_and_hold(page, max_press=max_press):
        if wait_frontend_after_press("native_press", seconds=45.0):
            return True
        if _is_success_page(page) or bool(_last_frontend_create_redirect(page)):
            return True
    if _bridge_hsprotect_px_cookies(ctx, page, label="after_native_press"):
        if _continue_after_px_bridge(page, label="after_native_press"):
            return True
        if _is_success_page(page) or bool(_last_frontend_create_redirect(page)):
            return True
        # Only replay after the visible human challenge has cleared. Replaying
        # while it is still visible is proven to produce 1059/humanCaptcha in
        # browser_api_create_after_frontend_press_* artifacts.
        if not _challenge_still_visible(page) and replay_create("after_native_press"):
            return True
    if _press_and_hold(page, max_press=max_press):
        if wait_frontend_after_press("native_press_retry", seconds=45.0):
            return True
        return _is_success_page(page) or bool(_last_frontend_create_redirect(page))
    if _bridge_hsprotect_px_cookies(ctx, page, label="after_press"):
        logger.info("[outlook-browser] px cookies bridged after press; refresh challenge parent")
        if replay_create("after_press"):
            return True
        if _continue_after_px_bridge(page, label="after_press"):
            return True
        page.wait_for_timeout(5000)
        if _is_success_page(page) or bool(_last_frontend_create_redirect(page)):
            return True
        try:
            page.reload(wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(8000)
        except Exception:
            pass
        if _is_success_page(page) or bool(_last_frontend_create_redirect(page)):
            return True
        return _continue_after_px_bridge(page, label="after_press_after_reload") or not early_abort
    if str(os.environ.get("OUTLOOK_ENABLE_CAPTCHA_PROVIDER", "")).strip().lower() in ("1", "true", "yes"):
        solution = _solve_with_project_captcha(cfg, str(getattr(page, "url", "") or "https://signup.live.com/"))
        if _apply_captcha_solution(ctx, page, solution):
            return True
    else:
        logger.info("[outlook-browser] external captcha provider disabled")
    if _bridge_hsprotect_px_cookies(ctx, page, label="final"):
        return _is_success_page(page) or bool(_last_frontend_create_redirect(page))
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


def _fill_birthday(page, cfg: Config) -> tuple[str, str, str]:
    year, month, day = _birth_parts()
    month_i = int(month)
    country_options = _target_country_options(cfg)
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
            handle = combo.element_handle(timeout=1500)
            if not handle:
                return False
            page.evaluate(
                """el => {
                  el.scrollIntoView({ block: 'center', inline: 'center' });
                  el.focus();
                  el.click();
                }""",
                handle,
            )
            page.wait_for_timeout(300)
            selected = page.evaluate(
                """candidates => {
                  const norm = s => String(s || '').trim().toLowerCase();
                  const wanted = candidates.map(norm).filter(Boolean);
                  const options = [...document.querySelectorAll('[role="option"]')];
                  let target = options.find(o => wanted.includes(norm(o.textContent)));
                  if (!target) {
                    target = options.find(o => wanted.some(w => norm(o.textContent).includes(w)));
                  }
                  if (!target) return false;
                  target.scrollIntoView({ block: 'center', inline: 'center' });
                  target.focus();
                  target.click();
                  return true;
                }""",
                candidates,
            )
            page.wait_for_timeout(300)
            return bool(selected)
        except Exception as e:
            logger.debug("[outlook-browser] combo option select failed candidates=%s error=%s", candidates, e)
            return False

    try:
        js_result = page.evaluate(
            """args => {
              const { year, month, day, countryOptions, monthLabels } = args;
              const fire = el => {
                for (const name of ['input', 'change', 'blur']) {
                  el.dispatchEvent(new Event(name, { bubbles: true }));
                }
              };
              const norm = s => String(s || '').trim().toLowerCase();
              const setNativeValue = (el, value) => {
                const proto = Object.getPrototypeOf(el);
                const desc = Object.getOwnPropertyDescriptor(proto, 'value');
                if (desc && desc.set) desc.set.call(el, value);
                else el.value = value;
                fire(el);
              };
              const selectBy = (sel, values) => {
                const el = document.querySelector(sel);
                if (!el) return false;
                const wanted = values.map(norm).filter(Boolean);
                for (const opt of el.options || []) {
                  const keys = [opt.value, opt.textContent, opt.label].map(norm);
                  if (keys.some(k => wanted.includes(k))) {
                    el.value = opt.value;
                    fire(el);
                    return true;
                  }
                }
                return false;
              };
              const setInput = (selectors, value) => {
                for (const sel of selectors) {
                  const el = document.querySelector(sel);
                  if (el) {
                    setNativeValue(el, value);
                    return true;
                  }
                }
                return false;
              };
              const selects = [...document.querySelectorAll('select')];
              let country = selectBy('#Country, select[name*=Country i], select[id*=Country i]', countryOptions);
              let mon = selectBy('#BirthMonth, select[name*=Month i], select[id*=Month i]', [month, ...monthLabels]);
              let dy = selectBy('#BirthDay, select[name*=Day i], select[id*=Day i]', [day, String(Number(day))]);
              if (!mon && selects.length >= 2) {
                const idx = selects.length >= 3 ? 1 : 0;
                const el = selects[idx];
                for (const opt of el.options || []) {
                  if ([opt.value, opt.textContent, opt.label].map(norm).some(k => [norm(month), ...monthLabels.map(norm)].includes(k))) {
                    el.value = opt.value; fire(el); mon = true; break;
                  }
                }
              }
              if (!dy && selects.length >= 2) {
                const idx = selects.length >= 3 ? 2 : 1;
                const el = selects[idx];
                for (const opt of el.options || []) {
                  if ([opt.value, opt.textContent, opt.label].map(norm).some(k => [norm(day), norm(String(Number(day)))].includes(k))) {
                    el.value = opt.value; fire(el); dy = true; break;
                  }
                }
              }
              const yr = setInput([
                '#BirthYearInput',
                'input[name*=Year i]',
                'input[id*=Year i]',
                'input[aria-label*=year i]',
                'input[aria-label*=年 i]',
                'input[type=number]',
                'input[inputmode=numeric]'
              ], year);
              return { country, month: mon, day: dy, year: yr, selects: selects.length };
            }""",
            {
                "year": year,
                "month": month,
                "day": day,
                "countryOptions": country_options,
                "monthLabels": [month_names_en[month_i], month_names_cn[month_i], month_names_fr[month_i]],
            },
        ) or {}
        logger.info("[outlook-browser] birthday js_fill=%s", js_result)
    except Exception as e:
        logger.debug("[outlook-browser] birthday js fill failed: %s", e)

    selects = page.locator("select")
    if selects.count() >= 2:
        if selects.count() >= 3:
            try:
                selects.nth(0).select_option(label=country_options[0])
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
                country_filled = select_combo_option(combo, country_options)
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
    return year, month, day


def _register_in_context(cfg: Config, ctx, page, *, email: str, password: str, challenge_reason: str) -> OutlookBrowserResult:
    artifacts = _artifact_dir()
    prefix = email.split("@", 1)[0]
    first_name = str(_cfg_value(cfg, "first_name", "") or random.choice(FIRST_NAMES))
    last_name = str(_cfg_value(cfg, "last_name", "") or random.choice(LAST_NAMES))
    _install_runtime_trace(page, label=prefix or "outlook")
    if _js_internal_trace_enabled():
        _install_js_internal_trace(page, label=prefix or "outlook")
    else:
        logger.info("[outlook-browser] JS internal trace disabled; set OUTLOOK_JS_INTERNAL_TRACE=1 to inject page hooks")

    signup_url = _browser_signup_authorize_url(cfg)
    logger.info("[outlook-browser] signup authorize entry client_id=%s", _cfg_value(cfg, "client_id", "00000000480728C5"))
    last_goto_error: Exception | None = None
    for goto_attempt in range(1, 5):
        try:
            page.goto(signup_url, wait_until="domcontentloaded", timeout=60000)
            last_goto_error = None
            break
        except Exception as e:
            last_goto_error = e
            marker = str(e).splitlines()[0][:180]
            logger.warning(
                "[outlook-browser] signup goto failed attempt=%s/4 error=%s",
                goto_attempt,
                marker,
            )
            page.wait_for_timeout(1500 * goto_attempt)
    if last_goto_error is not None:
        raise last_goto_error
    page.wait_for_timeout(3000)
    _log_browser_evidence(page, label="after_signup_goto")
    try:
        page.screenshot(path=str(artifacts / "outlook_browser_start.png"))
    except Exception:
        pass

    _handle_data_export_consent(page)

    logger.info("[outlook-browser] registering email=%s challenge_reason=%s", email, challenge_reason or "<none>")
    _write_form_artifacts(page, "email_before")
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
    else:
        domain_combo_present = False
        try:
            domain_combo_present = bool(page.evaluate(
                """() => {
                  const els = [...document.querySelectorAll('button, [role="combobox"]')];
                  return els.some(el => {
                    const text = `${el.id || ''} ${el.getAttribute('name') || ''} ${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`.toLowerCase();
                    return text.includes('domain') || text.includes('@outlook') || text.includes('@hotmail') || text.includes('电子邮件域');
                  });
                }"""
            ))
        except Exception:
            domain_combo_present = False
        if domain_combo_present:
            logger.info("[outlook-browser] email domain combobox detected; keep local-part input")
        elif "@" not in (page.locator('input[type="email"], input[name="MemberName"], #MemberName').first.input_value() or ""):
            _fill_first(page, ['input[type="email"]', 'input[name="MemberName"]', "#MemberName"], email)
    _write_form_artifacts(page, "email_after")
    _click_first(page, ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]'])
    page.wait_for_timeout(3000)

    _write_form_artifacts(page, "password_before")
    if not _fill_first(
        page,
        ['input[type="password"]', 'input[name="Password"]', "#PasswordInput", 'input[name="passwd"]'],
        password,
    ):
        raise RuntimeError("Outlook browser fallback: password input not found")
    _write_form_artifacts(page, "password_after")
    _click_first(
        page,
        ['#iSignupAction', 'input[type="submit"]', 'button[type="submit"]', 'button:has-text("Next")', 'button:has-text("下一步")'],
    )
    page.wait_for_timeout(3000)

    _write_form_artifacts(page, "birthday_before")
    birth_year, birth_month, birth_day = _fill_birthday(page, cfg)
    birth_date = f"{birth_day}:{birth_month}:{birth_year}"
    _write_form_artifacts(page, "birthday_after")
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
    _write_form_artifacts(page, "name_before")
    _fill_name_page(page, first_name=first_name, last_name=last_name)
    _write_form_artifacts(page, "name_after")

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
            if not _handle_challenge(
                cfg,
                ctx,
                page,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                birth_date=birth_date,
                early_abort=True,
            ):
                raise RuntimeError("Outlook browser fallback: challenge not solved")
            if _last_frontend_create_redirect(page) or _is_success_page(page):
                logger.info(
                    "[outlook-browser] challenge completed email=%s redirect_seen=%s url=%s",
                    email,
                    bool(_last_frontend_create_redirect(page)),
                    getattr(page, "url", ""),
                )
                return OutlookBrowserResult(email=email, password=password, challenge_reason=challenge_reason)
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
    geoip = _camoufox_geoip_enabled(proxy)
    headless = _camoufox_headless()
    profile = tempfile.mkdtemp(prefix="outlook_browser_")
    logger.info(
        "[outlook-browser] Camoufox headless=%s profile=%s proxy=%s geoip=%s",
        headless,
        profile,
        bool(proxy),
        geoip,
    )

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
        "os": _camoufox_os_for_cfg(cfg),
        "proxy": proxy,
        "geoip": geoip,
        "locale": _camoufox_locale_for_cfg(cfg),
    }
    if Screen is not None:
        camoufox_kwargs["screen"] = Screen(max_width=1920, max_height=1080)

    success = False
    try:
        with Camoufox(**camoufox_kwargs) as ctx:
            _install_hsprotect_js_patch(ctx, label="main")
            _install_static_resource_cache(ctx, label="main")
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            _log_browser_evidence(page, label="context_created")
            result = _register_in_context(
                cfg,
                ctx,
                page,
                email=email,
                password=password,
                challenge_reason=challenge_reason,
            )
            result.username_seq = username_seq
            result.portal_register_client_id = str(_cfg_value(cfg, "client_id", "00000000480728C5") or "")
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
