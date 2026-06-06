"""Microsoft consumers OAuth helper for freshly registered Outlook accounts."""
from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse

import requests

from config import Config

logger = logging.getLogger(__name__)

TOKEN_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
AUTHORIZE_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"


class OutlookOAuthError(RuntimeError):
    """Raised when Outlook OAuth cannot produce a refresh token."""


@dataclass
class OutlookOAuthResult:
    client_id: str
    access_token: str
    refresh_token: str
    expires_in: int = 0
    token_type: str = ""
    scope: str = ""

    def to_mail_fields(self) -> dict[str, str]:
        return {
            "mail_account_id": self.client_id,
            "mail_access_token": self.access_token,
            "mail_refresh_token": self.refresh_token,
            "mail_oauth_scope": self.scope,
        }


def _cfg_value(cfg: Config, key: str, default: Any = "") -> Any:
    portal = getattr(cfg, "portal_protocol", None)
    if portal is None:
        return default
    return getattr(portal, key, default)


def _response_text(resp: Any) -> str:
    return getattr(resp, "text", "") or ""


def _absolute_url(base_url: str, target: str) -> str:
    target = html.unescape(str(target or "").replace("\\u0026", "&"))
    if target.startswith("http://") or target.startswith("https://"):
        return target
    return urljoin(base_url, target)


def _extract_ppft_and_post_url(text: str) -> tuple[str, str, str]:
    flow_token = ""
    sft_tag = re.search(r'sFTTag.*?value=\\?"([^"\\]+)', text, re.S)
    if sft_tag:
        flow_token = html.unescape(sft_tag.group(1))
    if not flow_token:
        ppft = re.search(r'name=["\']PPFT["\'][^>]*value=["\']([^"\']+)', text, re.I)
        if ppft:
            flow_token = html.unescape(ppft.group(1))

    post_url = ""
    urlpost_match = re.search(r'"urlPost"\s*:\s*"([^"]+)"', text)
    if urlpost_match:
        post_url = html.unescape(urlpost_match.group(1).replace("\\u0026", "&"))

    ctx = ""
    sctx_match = re.search(r'"sCtx"\s*:\s*"([^"]+)"', text)
    if sctx_match:
        ctx = html.unescape(sctx_match.group(1))
    return flow_token, post_url, ctx


def _hidden_inputs(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in re.finditer(r"<input\b[^>]*>", text, re.I):
        tag = match.group(0)
        name_m = re.search(r'\bname=["\']?([^"\'\s>]+)', tag, re.I)
        if not name_m:
            continue
        value_m = re.search(r'\bvalue=["\']([^"\']*)', tag, re.I)
        out[html.unescape(name_m.group(1))] = html.unescape(value_m.group(1) if value_m else "")
    return out


def _first_form(text: str) -> tuple[str, dict[str, str]]:
    form_match = re.search(r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>(.*?)</form>', text, re.S | re.I)
    if not form_match:
        return "", {}
    return html.unescape(form_match.group(1)), _hidden_inputs(form_match.group(2))


def _extract_server_data_object(text: str) -> dict[str, Any]:
    match = re.search(r"(?:var\s+)?ServerData\s*=\s*(\{.*?\});", text, re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except Exception:
        return {}


def _url_auth_code(url: str, redirect_uri: str) -> str:
    parsed = urlparse(url)
    if "code=" not in url:
        return ""
    if redirect_uri and url.startswith(redirect_uri):
        return parse_qs(parsed.query).get("code", [""])[0]
    if "localhost" in parsed.netloc or parsed.netloc in {"login.microsoftonline.com"}:
        return parse_qs(parsed.query).get("code", [""])[0]
    return parse_qs(parsed.query).get("code", [""])[0]


def _url_oauth_error(url: str) -> str:
    if "error=" not in url:
        return ""
    qs = parse_qs(urlparse(url).query)
    return qs.get("error_description", qs.get("error", [""]))[0]


def _follow_redirects(session: Any, resp: Any, redirect_uri: str, timeout: int) -> Any:
    for _ in range(12):
        status = int(getattr(resp, "status_code", 0) or 0)
        if status not in (301, 302, 303, 307, 308):
            return resp
        loc = getattr(resp, "headers", {}).get("Location", "") or getattr(resp, "headers", {}).get("location", "")
        if not loc:
            return resp
        loc = _absolute_url(getattr(resp, "url", "") or "", loc)
        if (redirect_uri and loc.startswith(redirect_uri)) or "code=" in loc or "error=" in loc:
            class RedirectCapture:
                status_code = 200
                text = ""
                headers: dict[str, str] = {}

                def __init__(self, url: str):
                    self.url = url

            return RedirectCapture(loc)
        resp = session.get(loc, timeout=timeout, allow_redirects=False)
    return resp


def _exchange_code(session: Any, *, client_id: str, code: str, redirect_uri: str, scope: str, timeout: int) -> OutlookOAuthResult:
    resp = session.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": scope,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    try:
        data = resp.json()
    except Exception as e:
        raise OutlookOAuthError(f"token 返回非 JSON: {(_response_text(resp)[:200])}") from e
    if not isinstance(data, dict) or not data.get("access_token"):
        err = data.get("error_description") if isinstance(data, dict) else ""
        raise OutlookOAuthError(f"token exchange failed: {(err or data)!s}"[:300])
    refresh_token = str(data.get("refresh_token") or "").strip()
    if not refresh_token:
        raise OutlookOAuthError("token exchange succeeded but refresh_token missing")
    return OutlookOAuthResult(
        client_id=client_id,
        access_token=str(data.get("access_token") or ""),
        refresh_token=refresh_token,
        expires_in=int(data.get("expires_in") or 0),
        token_type=str(data.get("token_type") or ""),
        scope=str(data.get("scope") or scope),
    )


def _oauth_settings(cfg: Config) -> tuple[str, str, str, str, int]:
    client_id = str(_cfg_value(cfg, "mail_oauth_client_id", "") or "").strip()
    if not client_id:
        raise OutlookOAuthError("portal_protocol.mail_oauth_client_id 为空")
    redirect_uri = str(_cfg_value(cfg, "mail_oauth_redirect_uri", "http://localhost") or "http://localhost").strip()
    scope = str(_cfg_value(cfg, "mail_oauth_scope", "offline_access https://outlook.office.com/IMAP.AccessAsUser.All") or "").strip()
    prompt = str(_cfg_value(cfg, "mail_oauth_prompt", "consent") or "").strip()
    timeout = int(_cfg_value(cfg, "timeout_s", 30) or 30)
    return client_id, redirect_uri, scope, prompt, timeout


def _authorize_url(cfg: Config, *, email: str) -> tuple[str, str, str, str, int]:
    client_id, redirect_uri, scope, prompt, timeout = _oauth_settings(cfg)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "response_mode": "query",
        "login_hint": email,
    }
    if prompt:
        params["prompt"] = prompt
    return AUTHORIZE_ENDPOINT + "?" + urlencode(params, quote_via=quote), client_id, redirect_uri, scope, timeout


def _requests_oauth_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    proxy = str(getattr(cfg, "proxy", "") or "").strip()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    session.headers.update({
        "User-Agent": str(_cfg_value(cfg, "user_agent", "") or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )),
    })
    return session


def _click_browser_first(page: Any, selectors: list[str], *, timeout: int = 2500) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=500):
                loc.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


def authorize_outlook_mailbox_browser(cfg: Config, page: Any, *, email: str, password: str = "") -> OutlookOAuthResult:
    """Authorize mailbox in the already logged-in browser context, then exchange code."""
    auth_url, client_id, redirect_uri, scope, timeout = _authorize_url(cfg, email=email)
    logger.info("[outlook-oauth] browser authorize start email=%s client_id=%s", email, client_id)
    try:
        page.goto(auth_url, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
    except Exception as e:
        current = str(getattr(page, "url", "") or "")
        if "code=" not in current and "error=" not in current:
            logger.debug("[outlook-oauth] browser goto authorize raised before code: %s", e)

    deadline = __import__("time").time() + max(float(timeout), 45.0)
    while __import__("time").time() < deadline:
        current_url = str(getattr(page, "url", "") or "")
        code = _url_auth_code(current_url, redirect_uri)
        if code:
            result = _exchange_code(
                _requests_oauth_session(cfg),
                client_id=client_id,
                code=code,
                redirect_uri=redirect_uri,
                scope=scope,
                timeout=timeout,
            )
            logger.info("[outlook-oauth] browser refresh_token acquired email=%s client_id=%s rt_len=%s", email, client_id, len(result.refresh_token))
            return result
        oauth_error = _url_oauth_error(current_url)
        if oauth_error:
            raise OutlookOAuthError(f"browser authorize error: {oauth_error[:200]}")

        text = ""
        try:
            text = (page.inner_text("body", timeout=1500) or "").lower()
        except Exception:
            pass

        # Same context usually skips login, but handle password/login forms if Microsoft asks again.
        if password:
            try:
                pwd = page.locator('input[type="password"], input[name="passwd"]').first
                if pwd.count() > 0 and pwd.is_visible(timeout=500):
                    pwd.evaluate(
                        """(el, value) => {
                          el.focus(); el.value = value;
                          el.dispatchEvent(new Event('input', {bubbles: true}));
                          el.dispatchEvent(new Event('change', {bubbles: true}));
                        }""",
                        password,
                    )
                    _click_browser_first(page, ['input[type="submit"]', 'button[type="submit"]', '#idSIButton9', 'button:has-text("Sign in")'])
                    page.wait_for_timeout(2000)
                    continue
            except Exception:
                pass
        try:
            email_input = page.locator('input[type="email"], input[name="loginfmt"]').first
            if email_input.count() > 0 and email_input.is_visible(timeout=500):
                email_input.evaluate(
                    """(el, value) => {
                      el.focus(); el.value = value;
                      el.dispatchEvent(new Event('input', {bubbles: true}));
                      el.dispatchEvent(new Event('change', {bubbles: true}));
                    }""",
                    email,
                )
                _click_browser_first(page, ['input[type="submit"]', 'button[type="submit"]', '#idSIButton9', 'button:has-text("Next")'])
                page.wait_for_timeout(2000)
                continue
        except Exception:
            pass

        if any(k in text for k in ("accept", "consent", "permissions requested", "requested permissions", "同意")):
            if _click_browser_first(
                page,
                [
                    '#idBtn_Accept',
                    'input[id="idBtn_Accept"]',
                    'button:has-text("Accept")',
                    'button:has-text("Yes")',
                    'button:has-text("Continue")',
                    'button:has-text("同意")',
                    'input[type="submit"][value="Yes"]',
                    'input[type="submit"][value="Accept"]',
                    'input[type="submit"]',
                    'button[type="submit"]',
                ],
            ):
                page.wait_for_timeout(2500)
                continue

        if "proofs/add" in current_url.lower() or "add security info" in text:
            if _click_browser_first(page, ['button:has-text("Skip")', 'a:has-text("Skip")', '#iShowSkip', '#idBtn_Back']):
                page.wait_for_timeout(2000)
                continue

        if _click_browser_first(page, ['button:has-text("Continue")', 'button:has-text("Next")', 'input[type="submit"]', 'button[type="submit"]'], timeout=1200):
            page.wait_for_timeout(2000)
            continue
        page.wait_for_timeout(1000)

    marker = ""
    try:
        marker = re.sub(r"\s+", " ", (page.inner_text("body", timeout=1500) or "")[:200])
    except Exception:
        pass
    raise OutlookOAuthError(f"browser authorize did not reach code url={str(getattr(page, 'url', '') or '')[:140]} body={marker}")


def authorize_outlook_mailbox(cfg: Config, session: Any, *, email: str, password: str) -> OutlookOAuthResult:
    """Authorize the new Outlook mailbox to the configured target client_id."""
    auth_url, client_id, redirect_uri, scope, timeout = _authorize_url(cfg, email=email)
    logger.info("[outlook-oauth] authorize start email=%s client_id=%s", email, client_id)
    resp = session.get(auth_url, timeout=timeout, allow_redirects=False)
    resp = _follow_redirects(session, resp, redirect_uri, timeout)

    for step in range(20):
        current_url = str(getattr(resp, "url", "") or "")
        code = _url_auth_code(current_url, redirect_uri)
        if code:
            result = _exchange_code(session, client_id=client_id, code=code, redirect_uri=redirect_uri, scope=scope, timeout=timeout)
            logger.info("[outlook-oauth] refresh_token acquired email=%s client_id=%s rt_len=%s", email, client_id, len(result.refresh_token))
            return result
        oauth_error = _url_oauth_error(current_url)
        if oauth_error:
            raise OutlookOAuthError(f"authorize error: {oauth_error[:200]}")

        text = _response_text(resp)
        flow_token, post_url, ctx = _extract_ppft_and_post_url(text)
        if flow_token:
            if not post_url:
                post_url = "https://login.live.com/ppsecure/post.srf"
            login_data = {
                "login": email,
                "loginfmt": email,
                "passwd": password,
                "PPFT": flow_token,
                "ctx": ctx,
                "type": "11",
                "LoginOptions": "3",
                "i13": "0",
                "CookieDisclosure": "0",
                "IsFidoSupported": "0",
                "isSignupPost": "0",
                "i19": "16393",
            }
            logger.info("[outlook-oauth] submitting password email=%s step=%s", email, step)
            resp = session.post(_absolute_url(current_url, post_url), data=login_data, timeout=timeout, allow_redirects=False)
            resp = _follow_redirects(session, resp, redirect_uri, timeout)
            continue

        if "Consent/Update" in current_url or "Consent/update" in current_url:
            sd = _extract_server_data_object(text)
            if sd:
                consent_data = {
                    "ucaction": "Yes",
                    "client_id": sd.get("sClientId", client_id),
                    "scope": sd.get("sRawInputScopes", scope),
                    "cscope": sd.get("sRawInputGrantedScopes", ""),
                    "canary": sd.get("sCanary", ""),
                }
                logger.info("[outlook-oauth] accepting consent email=%s step=%s", email, step)
                resp = session.post(current_url, data=consent_data, timeout=timeout, allow_redirects=False)
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        if "proofs/Add" in current_url or "proofs/add" in current_url:
            action, form_data = _first_form(text)
            if action:
                form_data["action"] = "Skip"
                logger.info("[outlook-oauth] skipping proofs/Add email=%s step=%s", email, step)
                resp = session.post(_absolute_url(current_url, action), data=form_data, timeout=timeout, allow_redirects=False)
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        if "DoSubmit" in text or ("fmHF" in text and "onload" in text):
            action, form_data = _first_form(text)
            if action:
                logger.info("[outlook-oauth] submitting hidden redirect form email=%s step=%s", email, step)
                resp = session.post(_absolute_url(current_url, action), data=form_data, timeout=timeout, allow_redirects=False)
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        action, form_data = _first_form(text)
        if action:
            lowered = (action + " " + current_url).lower()
            if "consent" in lowered:
                form_data.setdefault("ucaccept", "Yes")
                form_data.setdefault("ucaction", "Yes")
            logger.info("[outlook-oauth] submitting form email=%s step=%s action=%s", email, step, action[:80])
            resp = session.post(_absolute_url(current_url, action), data=form_data, timeout=timeout, allow_redirects=False)
            resp = _follow_redirects(session, resp, redirect_uri, timeout)
            continue

        marker = re.sub(r"\s+", " ", text[:160])
        raise OutlookOAuthError(f"authorize stuck url={current_url[:120]} body={marker}")

    raise OutlookOAuthError("authorize did not reach auth code")
