"""Probe registered ChatGPT accounts to tell whether they're still usable.

Status taxonomy (persisted to ``registered_accounts.last_check_status``):

  - ``valid``    Some credential successfully exchanges with OpenAI right now.
                 Either rt → fresh at, or current at → /me 200, or cookie → /me 200.
  - ``invalid``  All available credentials definitively rejected by OpenAI
                 (invalid_grant / 401 from /me with Bearer) AND there's no
                 remaining path to recover. Safe to delete.
  - ``unknown``  Network error, timeout, 5xx, or Cloudflare bot-challenge —
                 caller couldn't determine validity. NEVER auto-delete on this.

Probe order (strongest signal first):
  1. refresh_token → POST auth.openai.com/oauth/token  (most reliable: rt is
     long-lived; success means account fundamentally alive, can re-mint at)
  2. access_token  → GET chatgpt.com/backend-api/me Bearer  (at expires in
     ~1h; without an rt to re-mint, an expired at means no recovery → invalid)
  3. cookie/session_token → GET /backend-api/me with Cookie  (web session;
     CF often challenges non-browser TLS so 403 is treated as unknown, not
     invalid, to avoid false positives)

All probes go through the local gost relay (127.0.0.1:18898) when it's listening
so source IP stays close to the original registration IP.
"""
from __future__ import annotations

import base64
import json
import socket
from typing import Iterable, Optional

import httpx

from .db import get_db


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
_ME_URL = "https://chatgpt.com/backend-api/me"
_SESSION_URL = "https://chatgpt.com/api/auth/session"
_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_CHECK_V4_URL = (
    "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27"
    "?timezone_offset_min=-540"
)


def _decode_jwt_payload(token: str) -> dict:
    if not token or token.count(".") < 2:
        return {}
    try:
        payload_b64 = token.split(".", 2)[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normal_plan_type(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if "team" in raw:
        return "team"
    if "pro" in raw and "plus" not in raw:
        return "pro"
    if "plus" in raw:
        return "plus"
    if "free" in raw:
        return "free"
    return raw[:40]


def _access_token_plan_type(token: str) -> str:
    payload = _decode_jwt_payload(token)
    auth_claim = payload.get("https://api.openai.com/auth") or {}
    if isinstance(auth_claim, dict):
        return _normal_plan_type(str(auth_claim.get("chatgpt_plan_type") or ""))
    return ""


def _subscription_plan_to_normal(value: str) -> str:
    return _normal_plan_type(value)


def _curl_cffi_session():
    try:
        from curl_cffi import requests as cr
    except Exception as e:
        return None, str(e)
    return cr, ""


def _curl_proxies(proxy: Optional[str]) -> dict | None:
    if not proxy:
        return None
    p = proxy.replace("socks5://", "socks5h://")
    return {"http": p, "https": p}


def _probe_check_v4_plan(access_token: str, timeout: float,
                          proxy: Optional[str]) -> tuple[str, str, str]:
    """实时读取账号 entitlement，返回 (status, plan_type, message)。"""
    cr, err = _curl_cffi_session()
    if cr is None:
        return "unknown", "", f"check/v4: curl_cffi missing: {err}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
        "Referer": "https://chatgpt.com/",
    }
    attempts: list[tuple[str, dict | None]] = []
    if proxy:
        attempts.append(("proxy", _curl_proxies(proxy)))
    attempts.append(("direct", None))

    response = None
    last_err = ""
    for label, proxies in attempts:
        try:
            with cr.Session(impersonate="chrome136", proxies=proxies) as s:
                response = s.get(_CHECK_V4_URL, headers=headers, timeout=timeout)
            break
        except Exception as e:
            last_err = f"{label}: {type(e).__name__}: {str(e)[:80]}"
            response = None
    if response is None:
        return "unknown", "", f"check/v4: {last_err}"

    code = getattr(response, "status_code", 0)
    if code == 401:
        return "invalid", "", "check/v4: 401 (token revoked)"
    if code == 403:
        return "invalid", "", "check/v4: 403 (banned/disabled)"
    if code != 200:
        return "unknown", "", f"check/v4: http {code}"

    try:
        data = response.json()
    except Exception:
        return "unknown", "", "check/v4: 200 non-json"
    account = ((data.get("accounts") or {}) if isinstance(data, dict) else {}).get("default") or {}
    if not account:
        return "unknown", "", "check/v4: no default account"
    entitlement = account.get("entitlement") or {}
    active = bool(entitlement.get("has_active_subscription"))
    raw_plan = str(entitlement.get("subscription_plan") or "")
    plan = _subscription_plan_to_normal(raw_plan)
    if not plan:
        plan = "free" if not active else "unknown"
    msg = (
        f"check/v4 ok; sub_plan={raw_plan!r} plan={plan} active={active}"
        f" expires={entitlement.get('expires_at')}"
    )
    return "valid", plan, msg


def _probe_check_v4_plan_via_cookie(account: dict, timeout: float,
                                      proxy: Optional[str]) -> tuple[str, str, str]:
    """Bearer 401 时用 session_token cookie 再读一次 check/v4。"""
    cr, err = _curl_cffi_session()
    if cr is None:
        return "unknown", "", f"check/v4-cookie: curl_cffi missing: {err}"

    session_token = (account.get("session_token") or "").strip()
    if not session_token:
        return "unknown", "", "check/v4-cookie: no session_token"
    cookies = {"__Secure-next-auth.session-token": session_token}
    csrf_token = (account.get("csrf_token") or "").strip()
    if csrf_token:
        cookies["__Host-next-auth.csrf-token"] = csrf_token
    headers = {
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
        "Referer": "https://chatgpt.com/",
    }

    attempts: list[tuple[str, dict | None]] = []
    if proxy:
        attempts.append(("proxy", _curl_proxies(proxy)))
    attempts.append(("direct", None))

    response = None
    last_err = ""
    for label, proxies in attempts:
        try:
            with cr.Session(impersonate="chrome136", proxies=proxies) as s:
                response = s.get(_CHECK_V4_URL, headers=headers, cookies=cookies, timeout=timeout)
            break
        except Exception as e:
            last_err = f"{label}: {type(e).__name__}: {str(e)[:80]}"
            response = None
    if response is None:
        return "unknown", "", f"check/v4-cookie: {last_err}"

    code = getattr(response, "status_code", 0)
    if code == 401:
        return "invalid", "", "check/v4-cookie: 401 (session revoked)"
    if code == 403:
        return "invalid", "", "check/v4-cookie: 403"
    if code != 200:
        return "unknown", "", f"check/v4-cookie: http {code}"

    try:
        data = response.json()
    except Exception:
        return "unknown", "", "check/v4-cookie: 200 non-json"
    account_data = ((data.get("accounts") or {}) if isinstance(data, dict) else {}).get("default") or {}
    if not account_data:
        return "unknown", "", "check/v4-cookie: no default account"
    entitlement = account_data.get("entitlement") or {}
    active = bool(entitlement.get("has_active_subscription"))
    raw_plan = str(entitlement.get("subscription_plan") or "")
    plan = _subscription_plan_to_normal(raw_plan)
    if not plan:
        plan = "free" if not active else "unknown"
    msg = (
        f"check/v4-cookie ok; sub_plan={raw_plan!r} plan={plan} active={active}"
        f" expires={entitlement.get('expires_at')}"
    )
    return "valid", plan, msg


def _refresh_at_via_session_cookie(account: dict, timeout: float,
                                     proxy: Optional[str]) -> tuple[str, str]:
    """用 session_token cookie 刷新 access_token，并写回 registered_accounts。"""
    cr, err = _curl_cffi_session()
    if cr is None:
        return "", f"session refresh: curl_cffi missing: {err}"

    session_token = (account.get("session_token") or "").strip()
    if not session_token:
        return "", "session refresh: no session_token"
    cookies = {"__Secure-next-auth.session-token": session_token}
    csrf_token = (account.get("csrf_token") or "").strip()
    if csrf_token:
        cookies["__Host-next-auth.csrf-token"] = csrf_token
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://chatgpt.com/",
    }

    attempts: list[tuple[str, dict | None]] = []
    if proxy:
        attempts.append(("proxy", _curl_proxies(proxy)))
    attempts.append(("direct", None))

    response = None
    last_err = ""
    for label, proxies in attempts:
        try:
            with cr.Session(impersonate="chrome136", proxies=proxies) as s:
                response = s.get(_SESSION_URL, headers=headers, cookies=cookies, timeout=timeout)
            break
        except Exception as e:
            last_err = f"{label}: {type(e).__name__}: {str(e)[:80]}"
            response = None
    if response is None:
        return "", f"session refresh: {last_err}"
    if getattr(response, "status_code", 0) != 200:
        return "", f"session refresh: http {getattr(response, 'status_code', 0)}"

    try:
        data = response.json()
    except Exception:
        return "", "session refresh: 200 non-json"
    new_at = str(data.get("accessToken") or "").strip() if isinstance(data, dict) else ""
    if not new_at or new_at.count(".") != 2:
        return "", "session refresh: no accessToken in body"

    try:
        db = get_db()
        with db._conn() as c:
            c.execute(
                "UPDATE registered_accounts SET access_token = ? WHERE id = ?",
                (new_at, int(account.get("id") or 0)),
            )
    except Exception:
        pass
    return new_at, f"session refresh ok (len={len(new_at)})"


def _gost_alive(port: int = 18898) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _client(timeout: float, proxy: Optional[str]) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=False, proxy=proxy)


def _probe_refresh(refresh_token: str, timeout: float,
                    proxy: Optional[str]) -> tuple[str, str]:
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": _CODEX_CLIENT_ID,
        "scope": "openid profile email offline_access",
    }
    headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
    try:
        with _client(timeout, proxy) as c:
            r = c.post(_OAUTH_TOKEN_URL, data=body, headers=headers)
    except httpx.TimeoutException:
        return "unknown", "rt: timeout"
    except (httpx.NetworkError, httpx.ProxyError) as e:
        return "unknown", f"rt: {type(e).__name__}"
    except Exception as e:
        return "unknown", f"rt: {type(e).__name__}: {str(e)[:80]}"
    if r.status_code == 200:
        try:
            if r.json().get("access_token"):
                return "valid", "rt → at swap ok"
        except Exception:
            pass
        return "unknown", "rt: 200 no access_token"
    if r.status_code in (400, 401):
        try:
            err = (r.json().get("error") or "")[:60]
        except Exception:
            err = ""
        if err in ("invalid_grant", "invalid_client", "unauthorized_client",
                   "invalid_request"):
            return "invalid", f"rt: {err}"
        return "invalid", f"rt: http {r.status_code} {err}".strip()
    return "unknown", f"rt: http {r.status_code}"


def _probe_me_with_bearer(access_token: str, timeout: float,
                            proxy: Optional[str]) -> tuple[str, str]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
    }
    try:
        with _client(timeout, proxy) as c:
            r = c.get(_ME_URL, headers=headers)
    except httpx.TimeoutException:
        return "unknown", "me: timeout"
    except (httpx.NetworkError, httpx.ProxyError) as e:
        return "unknown", f"me: {type(e).__name__}"
    except Exception as e:
        return "unknown", f"me: {type(e).__name__}: {str(e)[:80]}"
    if r.status_code == 200:
        try:
            data = r.json()
            uid = (data.get("id") or "")[:18]
            return "valid", f"me ok ({uid})"
        except Exception:
            return "unknown", "me: 200 non-json"
    if r.status_code == 401:
        return "invalid", "me: http 401 (token expired/revoked)"
    if r.status_code == 403:
        # /backend-api/me 走 Bearer 一般不会被 CF 误拦，403 多是 banned/disabled
        return "invalid", "me: http 403"
    return "unknown", f"me: http {r.status_code}"


def _build_cookie(account: dict) -> str:
    cookie_header = (account.get("cookie_header") or "").strip()
    if cookie_header:
        return cookie_header
    session_token = (account.get("session_token") or "").strip()
    if session_token:
        return f"__Secure-next-auth.session-token={session_token}"
    return ""


def _probe_me_with_cookie(account: dict, timeout: float,
                            proxy: Optional[str]) -> tuple[str, str]:
    cookie = _build_cookie(account)
    if not cookie:
        return "unknown", "no cookie"
    headers = {
        "Cookie": cookie,
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
        "Referer": "https://chatgpt.com/",
    }
    try:
        with _client(timeout, proxy) as c:
            r = c.get(_ME_URL, headers=headers)
    except httpx.TimeoutException:
        return "unknown", "cookie/me: timeout"
    except (httpx.NetworkError, httpx.ProxyError) as e:
        return "unknown", f"cookie/me: {type(e).__name__}"
    except Exception as e:
        return "unknown", f"cookie/me: {type(e).__name__}: {str(e)[:80]}"
    if r.status_code == 200:
        try:
            uid = (r.json().get("id") or "")[:18]
            return "valid", f"cookie/me ok ({uid})"
        except Exception:
            return "unknown", "cookie/me: 200 non-json"
    if r.status_code == 401:
        # 401 with cookie auth is OpenAI saying "session-token rejected" — usually
        # real, but with no Bearer to cross-check we treat as invalid only when
        # there's literally no other credential. Caller decides.
        return "invalid", "cookie/me: http 401"
    if r.status_code == 403:
        # 403 with no Bearer is almost always Cloudflare bot challenge / datadome,
        # not a real auth rejection. Mark unknown so we never delete on this.
        body_snip = r.text[:80].replace("\n", " ")
        return "unknown", f"cookie/me: http 403 (likely CF challenge) {body_snip}"
    return "unknown", f"cookie/me: http {r.status_code}"


def validate_account(account: dict, *, timeout_s: float = 10.0,
                       use_proxy: bool = True) -> tuple[str, str]:
    """Pure HTTP probe — caller persists result.

    Returns (status, message) where status ∈ {'valid','invalid','unknown'}.
    """
    refresh_token = (account.get("refresh_token") or "").strip()
    access_token = (account.get("access_token") or "").strip()
    cookie = _build_cookie(account)
    if not (refresh_token or access_token or cookie):
        return "unknown", "no credentials stored"

    proxy = "socks5://127.0.0.1:18898" if use_proxy and _gost_alive() else None

    # ── probe 1: refresh_token (most reliable, long-lived)
    if refresh_token:
        s, m = _probe_refresh(refresh_token, timeout_s, proxy)
        if s != "unknown":
            return s, m
        # rt path uncertain: fall through to at/cookie

    # ── probe 2: access_token Bearer → /me
    if access_token:
        s, m = _probe_me_with_bearer(access_token, timeout_s, proxy)
        if s == "valid":
            return s, m
        if s == "invalid":
            # at expired/revoked. Without rt there's no path to mint a new one
            # → genuinely unusable. With rt we'd already have returned above.
            if not refresh_token:
                return "invalid", m
            # If we had an rt but it returned 'unknown' earlier, falling
            # through to cookie probe is still informative.

    # ── probe 3: cookie / session_token → /me (CF-pruned, conservative)
    if cookie:
        s, m = _probe_me_with_cookie(account, timeout_s, proxy)
        if s == "valid":
            return s, m
        # cookie 401 alone isn't strong enough to delete; degrade to unknown
        if s == "invalid" and not (access_token or refresh_token):
            return "invalid", m
        if s == "invalid":
            return "unknown", f"cookie says invalid but other creds inconclusive: {m}"
        return s, m

    return "unknown", "no probe path succeeded"


def validate_account_by_id(account_id: int, *, timeout_s: float = 10.0,
                              use_proxy: bool = True) -> dict:
    """Validate one stored account, persist outcome, return summary.

    When an access_token is present, also read OpenAI's live account entitlement
    from ``/backend-api/accounts/check`` and persist ``last_plan_type``. This
    keeps portal inventory from trusting stale JWT claims after payment changes.
    """
    db = get_db()
    account = db.get_registered_account(int(account_id))
    if not account:
        return {"id": int(account_id), "status": "missing",
                "message": "account not found", "email": ""}
    status, message = validate_account(account, timeout_s=timeout_s,
                                          use_proxy=use_proxy)
    plan_type = ""
    access_token = (account.get("access_token") or "").strip()
    if access_token:
        proxy = "socks5://127.0.0.1:18898" if use_proxy and _gost_alive() else None
        live_status, live_plan, live_msg = _probe_check_v4_plan(access_token, timeout_s, proxy)
        if live_status == "invalid" and "401" in (live_msg or "") and account.get("session_token"):
            cookie_status, cookie_plan, cookie_msg = _probe_check_v4_plan_via_cookie(
                account, timeout_s, proxy,
            )
            if cookie_status == "valid":
                live_status = cookie_status
                live_plan = cookie_plan
                live_msg = f"cookie-fallback | {cookie_msg}"
            else:
                new_at, refresh_msg = _refresh_at_via_session_cookie(account, timeout_s, proxy)
                if new_at and new_at != access_token:
                    retry_status, retry_plan, retry_msg = _probe_check_v4_plan(new_at, timeout_s, proxy)
                    live_status = retry_status
                    live_plan = retry_plan
                    live_msg = f"refreshed-AT | {retry_msg}"
                    access_token = new_at
                elif refresh_msg:
                    live_msg = f"{live_msg} | {refresh_msg}"

        if live_status == "valid":
            if status != "valid":
                status = "valid"
                message = f"{message} | {live_msg}" if message else live_msg
            if live_plan and live_plan != "unknown":
                plan_type = live_plan
        elif live_status == "invalid":
            status = "invalid"
            message = f"{message} | {live_msg}" if message else live_msg
        else:
            if status == "invalid" and "403" in (message or ""):
                status = "unknown"
                message = f"httpx invalid downgraded; live check unknown: {message} | {live_msg}"
            plan_type = _access_token_plan_type(access_token)

    db.update_account_check(int(account_id), status, message, plan_type=plan_type)
    return {
        "id": int(account_id),
        "email": account.get("email", ""),
        "status": status,
        "message": message,
        "plan_type": plan_type,
    }


def validate_accounts(account_ids: Iterable[int], *, max_workers: int = 3,
                        timeout_s: float = 10.0, use_proxy: bool = True) -> list[dict]:
    """Validate many accounts with bounded concurrency."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ids = [int(i) for i in account_ids if str(i).strip().lstrip("-").isdigit()]
    if not ids:
        return []
    results: list[dict] = []
    workers = max(1, min(int(max_workers), len(ids)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(validate_account_by_id, i,
                              timeout_s=timeout_s, use_proxy=use_proxy): i
                   for i in ids}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                results.append({"id": futures[fut], "status": "unknown",
                                "message": f"worker error: {type(e).__name__}: {e}",
                                "email": ""})
    return results
