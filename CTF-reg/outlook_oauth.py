"""Microsoft consumers OAuth helper for freshly registered Outlook accounts."""
from __future__ import annotations

import html
import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse, urlunparse

import requests

from config import Config
from http_client import create_http_session

logger = logging.getLogger(__name__)

TOKEN_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
AUTHORIZE_ENDPOINT = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
COMMON_AUTHORIZE_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"


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
        name = html.unescape(name_m.group(1))
        if not re.match(r"^[A-Za-z0-9_.:-]+$", name):
            continue
        value_m = re.search(r'\bvalue=["\']([^"\']*)', tag, re.I)
        out[name] = html.unescape(value_m.group(1) if value_m else "")
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


def _extract_js_string(text: str, key: str) -> str:
    match = re.search(r'"' + re.escape(key) + r'"\s*:\s*"((?:\\.|[^"])*)"', text)
    if not match:
        return ""
    try:
        return json.loads('"' + match.group(1) + '"')
    except Exception:
        return html.unescape(match.group(1).replace("\\u0026", "&"))


def _extract_js_var_string(text: str, key: str) -> str:
    match = re.search(r"(?:var\s+)?"+ re.escape(key) + r"\s*=\s*'([^']*)'", text)
    if not match:
        match = re.search(r'(?:var\s+)?' + re.escape(key) + r'\s*=\s*"((?:\\.|[^"])*)"', text)
    if not match:
        return ""
    try:
        return json.loads('"' + match.group(1) + '"')
    except Exception:
        return html.unescape(match.group(1).replace("\\u0026", "&"))


def _extract_js_int(text: str, key: str, default: int = 0) -> int:
    match = re.search(r'"' + re.escape(key) + r'"\s*:\s*(\d+)', text)
    if not match:
        return default
    try:
        return int(match.group(1))
    except Exception:
        return default


def _oauth_fingerprint_clear_url(text: str, fingerprint_url: str, *, user_agent: str) -> str:
    local_target = _extract_js_string(text, "localTarget") or _extract_js_var_string(text, "localTarget") or "https://fpt.live.com/"
    txn_id = _extract_js_string(text, "txnId") or _extract_js_var_string(text, "txnId")
    cid = _extract_js_string(text, "cid") or _extract_js_var_string(text, "cid")
    ticks = _extract_js_string(text, "ticks") or _extract_js_var_string(text, "ticks")
    rid = _extract_js_string(text, "rid") or _extract_js_var_string(text, "rid")
    txn_key = _extract_js_string(text, "txnKey") or _extract_js_var_string(text, "txnKey") or "session_id"
    rid_key = _extract_js_string(text, "ridKey") or _extract_js_var_string(text, "ridKey") or "id"
    common_query = _extract_js_string(text, "commonquery") or _extract_js_var_string(text, "commonquery") or "&PageId=SI"
    if not txn_id or not cid:
        return ""
    plugin_info = (
        "plugin_flash=false&plugin_windows_media_player=false&plugin_adobe_acrobat=false&"
        "plugin_silverlight=false&plugin_quicktime=false&plugin_shockwave=false&"
        "plugin_realplayer=false&plugin_vlc_player=false&plugin_devalvr=false&"
        "plugin_svg_viewer=false&plugin_java=false"
    )
    app_version = user_agent.removeprefix("Mozilla/")
    esi_pairs = [
        ("bua", user_agent),
        ("os", "MacIntel"),
        ("lproc", "10"),
        ("ol", "true"),
        ("rtt", "200"),
        ("chrm", "true"),
        ("prosub", "20030107"),
        ("eval", "33"),
        ("appv", app_version),
        ("ls", "true"),
        ("dm", "16"),
        ("mtp", "0"),
        ("nc", "82"),
        ("pr", "2"),
        ("sr", "3840x2160"),
        ("scd", "24"),
        ("asr", "3840x1936"),
        ("tz", "480"),
        ("dst", "0"),
        ("tzo", "480"),
        ("bl", "zh-CN"),
        ("mth", "27f51d3149e6bf209b66bd387b0af3c4"),
        ("mtn", "2"),
        ("pn", "5"),
        ("ph", "f3ac22ac59c6dcb874109d093c5255e8"),
        ("p", plugin_info),
        ("fh", "b68feeb418e8541ca1a9111328a8281a"),
        ("fn", "67"),
        ("lh", fingerprint_url[:255]),
        ("dr", "https://login.live.com/"),
        ("w", ticks),
        (rid_key, rid),
        ("a", ""),
        ("c", "cd0d0ae82ff1b6dfbc036518476d76f1"),
    ]
    esi = base64.b64encode(urlencode(esi_pairs).encode("utf-8")).decode("ascii")
    eci = base64.b64encode(json.dumps({
        "uvdr": "Google Inc. (Apple)",
        "urdr": "ANGLE (Apple, ANGLE Metal Renderer: Apple M4, Unspecified Version)",
        "vdr": "WebKit",
        "rdr": "WebKit WebGL",
        "iduh": "80d9dec8b3f5c7355141c7a0cff4f788",
    }, separators=(",", ":")).encode("utf-8")).decode("ascii")
    params = [
        ("ctx", "jscb1.0"),
        (txn_key, txn_id),
        ("CustomerId", cid),
        ("esi", esi),
        ("eci", eci),
    ]
    clear_url = urljoin(local_target, "Images/Clear.PNG") + "?" + urlencode(params)
    if common_query:
        clear_url += common_query if common_query.startswith("&") else f"&{common_query}"
    return clear_url


def _chrome_client_hints(*, platform_version: bool = False) -> dict[str, str]:
    headers = {
        "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }
    if platform_version:
        headers["sec-ch-ua-platform-version"] = '"15.7.4"'
    return headers


def _browser_nav_headers(*, referer: str = "", site: str = "none", user: bool = True, platform_version: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": site,
        "Upgrade-Insecure-Requests": "1",
    }
    if user:
        headers["Sec-Fetch-User"] = "?1"
    if referer:
        headers["Referer"] = referer
    headers.update(_chrome_client_hints(platform_version=platform_version))
    return headers


def _browser_cors_headers(*, origin: str, referer: str, content_type: str, uaid: str = "", hpgid: str = "", hpgact: str = "") -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": content_type,
        "Origin": origin,
        "Referer": referer,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    if uaid:
        headers["client-request-id"] = uaid
        headers["correlationId"] = uaid
    if hpgact:
        headers["hpgact"] = hpgact
    if hpgid:
        headers["hpgid"] = hpgid
    headers.update(_chrome_client_hints(platform_version=True))
    return headers


def _har_sleep(label: str, seconds: float) -> None:
    logger.info("[outlook-oauth] HAR pacing sleep label=%s seconds=%.3f", label, seconds)
    time.sleep(seconds)


def _session_cookie_evidence(session: Any) -> list[str]:
    out: list[str] = []
    try:
        for cookie in getattr(session, "cookies", []) or []:
            name = str(getattr(cookie, "name", "") or "")
            domain = str(getattr(cookie, "domain", "") or "")
            if name:
                out.append(f"{name}@{domain or '<host>'}")
    except Exception:
        try:
            jar = getattr(session, "cookies", None)
            items = jar.items() if hasattr(jar, "items") else []
            out = [str(k) for k, _v in items]
        except Exception:
            out = []
    return sorted(out)


def _post_browser_form(
    session: Any,
    url: str,
    data: dict[str, str],
    *,
    referer: str,
    origin: str,
    site: str = "same-origin",
    timeout: int,
    user: bool = True,
) -> Any:
    headers = _browser_nav_headers(referer=referer, site=site, user=user)
    headers.update({
        "Cache-Control": "max-age=0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": origin,
    })
    return session.post(url, data=data, headers=headers, timeout=timeout, allow_redirects=False)


def _safe_url(value: str, *, max_len: int = 240) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    sensitive = {"code", "access_token", "refresh_token", "id_token", "client_secret", "passwd", "password"}
    qs = parse_qs(parsed.query, keep_blank_values=True)
    query = urlencode(
        {k: ("***" if k.lower() in sensitive else v[-1]) for k, v in qs.items() if v},
        doseq=False,
        quote_via=quote,
    )
    out = urlunparse(parsed._replace(query=query))
    return out[:max_len]


def _url_query_keys(value: str) -> list[str]:
    return sorted(parse_qs(urlparse(value).query, keep_blank_values=True).keys())


def _field_evidence(data: dict[str, Any]) -> dict[str, Any]:
    sensitive = {"passwd", "password", "ppft", "canary", "vanguardflowtoken", "flowtoken", "ctx", "ipt", "verifier", "reply_params"}
    out: dict[str, Any] = {}
    for key, value in data.items():
        text = "" if value is None else str(value)
        if key.lower() in sensitive:
            out[key] = f"<len={len(text)}>"
        else:
            out[key] = text if len(text) <= 80 else f"<len={len(text)} prefix={text[:24]}>"
    return out


def _page_markers(text: str) -> list[str]:
    lowered = (text or "").lower()
    markers = []
    for item in (
        "urlmsasignup",
        "urlgetcredentialtype",
        "getexperimentassignments",
        "checkpassword.srf",
        "ppsecure/post.srf",
        "ppft",
        "vanguardflowtoken",
        "consent/update",
        "ucaction",
        "consumers/savestate",
        "account.live.com/abuse",
        "/abuse",
    ):
        if item in lowered:
            markers.append(item)
    return markers


def _login_form_payload(
    text: str,
    *,
    email: str,
    password: str,
    flow_token: str,
    ctx: str,
    vanguardflowtoken: str = "",
) -> dict[str, str]:
    data = _hidden_inputs(text)
    data.update({
        "login": email,
        "loginfmt": email,
        "passwd": password,
        "PPFT": data.get("PPFT") or flow_token,
        "ctx": data.get("ctx") or ctx,
        "type": data.get("type") or "11",
        "LoginOptions": data.get("LoginOptions") or "3",
        "i13": data.get("i13") or "0",
        "CookieDisclosure": data.get("CookieDisclosure") or "0",
        "IsFidoSupported": data.get("IsFidoSupported") or "1",
        "isSignupPost": data.get("isSignupPost") or "0",
    })
    for key, value in {
        "PPSX": "Pas",
        "NewUser": "1",
        "FoundMSAs": "",
        "fspost": "0",
        "i21": "0",
        "isRecoveryAttemptPost": "0",
        "cpr": "0",
        "ps": "2",
        "psRNGCDefaultType": "",
        "psRNGCEntropy": "",
        "psRNGCSLK": "",
        "canary": "",
        "hpgrequestid": "",
        "lrt": "",
        "lrtPartition": "",
        "hisRegion": "",
        "hisScaleUnit": "",
    }.items():
        data.setdefault(key, value)
    if vanguardflowtoken:
        data["vanguardflowtoken"] = vanguardflowtoken
    if "vanguardflowtoken" not in data:
        token = _extract_js_string(text, "vanguardflowtoken") or _extract_js_string(text, "sVanguardFlowToken")
        if token:
            data["vanguardflowtoken"] = token
    ordered = [
        "ps",
        "psRNGCDefaultType",
        "psRNGCEntropy",
        "psRNGCSLK",
        "canary",
        "ctx",
        "hpgrequestid",
        "PPFT",
        "PPSX",
        "NewUser",
        "FoundMSAs",
        "fspost",
        "i21",
        "CookieDisclosure",
        "IsFidoSupported",
        "isSignupPost",
        "isRecoveryAttemptPost",
        "i13",
        "login",
        "loginfmt",
        "type",
        "LoginOptions",
        "lrt",
        "lrtPartition",
        "hisRegion",
        "hisScaleUnit",
        "cpr",
        "passwd",
        "vanguardflowtoken",
    ]
    out: dict[str, str] = {}
    for key in ordered:
        if key in data:
            out[key] = str(data[key])
    for key, value in data.items():
        if key not in out:
            out[str(key)] = str(value)
    return out


def _post_login_prefetches(session: Any, *, current_url: str, text: str, email: str, password: str, timeout: int) -> str:
    check_password_url = _extract_js_string(text, "urlCheckPassword")
    if not check_password_url:
        check_password_url = "https://login.live.com/checkpassword.srf"
    uaid = (parse_qs(urlparse(current_url).query).get("uaid") or [""])[0]
    headers = _browser_cors_headers(
        origin="https://login.live.com",
        referer=current_url,
        content_type="application/json; charset=utf-8",
        uaid=uaid,
        hpgact="0",
        hpgid="33",
    )
    try:
        resp = session.post(
            check_password_url,
            json={"username": email, "password": password, "checkpasswordflowtoken": ""},
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        try:
            data = resp.json()
        except Exception:
            data = {}
        token = str(data.get("vanguardflowtoken") or "")
        if token:
            logger.info("[outlook-oauth] checkpassword vanguard email=%s status=%s token_len=%s", email, getattr(resp, "status_code", ""), len(token))
            return token
        logger.info(
            "[outlook-oauth] checkpassword no vanguard email=%s status=%s result=%s detail=%s",
            email,
            getattr(resp, "status_code", ""),
            data.get("validationresult") if isinstance(data, dict) else "",
            data.get("validationdetail") if isinstance(data, dict) else "",
        )
        if isinstance(data, dict) and str(data.get("validationresult") or "").lower() == "fail":
            raise OutlookOAuthError(
                f"checkpassword failed detail={str(data.get('validationdetail') or '')[:120]}"
            )
    except OutlookOAuthError:
        raise
    except Exception as e:
        logger.debug("[outlook-oauth] checkpassword prefetch ignored email=%s err=%s", email, e)
    return ""


def _post_experiment_assignments(session: Any, *, current_url: str, timeout: int) -> None:
    if "getexperimentassignments" not in current_url.lower():
        url = "https://login.live.com/GetExperimentAssignments.srf"
    else:
        url = current_url
    payload = {
        "clientExperiments": [
            {
                "parallax": "enableidentitybannerresponsiveexperiment",
                "control": "enableidentitybannerresponsiveexperiment_control",
                "treatments": ["enableidentitybannerresponsiveexperiment_treatment"],
            },
            {
                "parallax": "enablerecoveryequalsauth",
                "control": "enablerecoveryequalsauth_control",
                "treatments": ["enablerecoveryequalsauth_treatment"],
            },
            {
                "parallax": "enablesisufeedback",
                "control": "enablesisufeedback_control",
                "treatments": ["enablesisufeedback_treatment"],
            },
            {
                "parallax": "enablecheckpasswordexperiment",
                "control": "enablecheckpasswordexperiment_control",
                "treatments": ["enablecheckpasswordexperiment_treatment"],
            },
            {
                "parallax": "enableoobefidofallbackexperiment",
                "control": "enableoobefidofallbackexperiment_control",
                "treatments": ["enableoobefidofallbackexperiment_treatment"],
            },
            {
                "parallax": "redirectfidocanceltocredpicker",
                "control": "redirectfidocanceltocredpicker_control",
                "treatments": ["redirectfidocanceltocredpicker_treatment"],
            },
            {
                "parallax": "addprivatebrowsingtexttofabricfooter",
                "control": "addprivatebrowsingtexttofabricfooter_control",
                "treatments": ["addprivatebrowsingtexttofabricfooter_treatment"],
            },
        ]
    }
    try:
        uaid = (parse_qs(urlparse(current_url).query).get("uaid") or [""])[0]
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "Origin": "https://login.live.com",
            "Referer": current_url,
            "client-request-id": uaid,
            "correlationId": uaid,
            "hpgact": "0",
            "hpgid": "33",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        headers.update(_chrome_client_hints(platform_version=True))
        resp = session.post(
            url,
            json=payload,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        logger.info("[outlook-oauth] experiment assignments email_stage status=%s url=%s", getattr(resp, "status_code", ""), _safe_url(str(getattr(resp, "url", "") or "")))
    except Exception as e:
        logger.debug("[outlook-oauth] experiment assignments ignored err=%s", e)


def _touch_live_fingerprint(session: Any, *, current_url: str, text: str, timeout: int) -> None:
    fingerprint_url = _extract_js_string(text, "urlDfp") or "https://fpt.live.com/"
    user_agent = str(getattr(session, "headers", {}).get("User-Agent") or "")
    if not user_agent:
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    try:
        dfp_resp = session.get(
            fingerprint_url,
            headers={
                **_browser_nav_headers(referer="https://login.live.com/", site="same-site", user=False),
                "Sec-Fetch-Dest": "iframe",
            },
            timeout=min(timeout, 12),
            allow_redirects=True,
        )
        clear_status = ""
        clear_url = _oauth_fingerprint_clear_url(getattr(dfp_resp, "text", "") or "", fingerprint_url, user_agent=user_agent)
        if clear_url:
            clear_resp = session.get(
                clear_url,
                headers={
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Referer": fingerprint_url,
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    **_chrome_client_hints(platform_version=True),
                },
                timeout=min(timeout, 12),
                allow_redirects=True,
            )
            clear_status = str(getattr(clear_resp, "status_code", "") or "")
        # HAR also loads df.cfp.microsoft.com/Clear.HTML as an iframe after fpt clear.
        dfp_text = getattr(dfp_resp, "text", "") or ""
        df_url = _extract_js_string(dfp_text, "dfUrl") or _extract_js_var_string(dfp_text, "dfUrl")
        if not df_url:
            target = _extract_js_var_string(dfp_text, "target")
            txn_id = _extract_js_var_string(dfp_text, "txnId")
            cid = _extract_js_var_string(dfp_text, "cid")
            ticks = _extract_js_var_string(dfp_text, "ticks")
            rid = _extract_js_var_string(dfp_text, "rid")
            common_query = _extract_js_var_string(dfp_text, "commonquery")
            if target and txn_id and cid:
                df_url = target + urlencode({
                    "session_id": txn_id,
                    "id": rid,
                    "w": ticks,
                    "tkt": "",
                    "CustomerId": cid,
                })
                if common_query:
                    df_url += common_query if common_query.startswith("&") else f"&{common_query}"
        if not df_url:
            df_url = _extract_js_string(dfp_text, "urlDf") or ""
        df_status = ""
        if df_url:
            df_resp = session.get(
                df_url,
                headers={
                    **_browser_nav_headers(referer="https://fpt.live.com/", site="cross-site", user=False),
                    "Sec-Fetch-Dest": "iframe",
                },
                timeout=min(timeout, 12),
                allow_redirects=True,
            )
            df_status = str(getattr(df_resp, "status_code", "") or "")
        cookie_names = []
        try:
            cookie_names = _session_cookie_evidence(session)
        except Exception:
            cookie_names = []
        logger.info(
            "[outlook-oauth] live fingerprint warmed dfp_status=%s clear_status=%s df_status=%s has_fptctx2=%s has_MUID=%s cookies=%s url=%s",
            getattr(dfp_resp, "status_code", "") or "",
            clear_status or "<skipped>",
            df_status or "<skipped>",
            any(str(name).split("@", 1)[0].lower() == "fptctx2" for name in cookie_names),
            any(str(name).split("@", 1)[0].upper() == "MUID" for name in cookie_names),
            cookie_names,
            _safe_url(fingerprint_url),
        )
    except Exception as e:
        logger.info("[outlook-oauth] live fingerprint skipped err=%s", e)


def _append_query(url: str, params: dict[str, str | None]) -> str:
    parsed = urlparse(url)
    existing = parse_qs(parsed.query, keep_blank_values=True)
    for key, value in params.items():
        if value is None:
            existing.pop(key, None)
        else:
            existing[key] = [value]
    query = urlencode({k: v[-1] for k, v in existing.items() if v}, doseq=False, quote_via=quote)
    return urlunparse(parsed._replace(query=query))


def _submit_common_username(session: Any, *, current_url: str, text: str, email: str, timeout: int) -> Any:
    credential_url = _extract_js_string(text, "urlGetCredentialType")
    flow_token = _extract_js_string(text, "sFT") or _extract_js_string(text, "flowToken")
    original_request = _extract_js_string(text, "sCtx") or _extract_js_string(text, "sRawQueryString")
    canary = _extract_js_string(text, "apiCanary") or _extract_js_string(text, "canary")
    correlation_id = _extract_js_string(text, "correlationId")
    hpgid = _extract_js_int(text, "hpgid", 1104)
    hpgact = _extract_js_int(text, "hpgact", 1800)
    if credential_url:
        payload = {
            "username": email,
            "isOtherIdpSupported": True,
            "checkPhones": False,
            "isRemoteNGCSupported": True,
            "isCookieBannerShown": False,
            "isFidoSupported": True,
            "originalRequest": original_request,
            "country": "CN",
            "forceotclogin": False,
            "isExternalFederationDisallowed": False,
            "isRemoteConnectSupported": False,
            "federationFlags": 0,
            "isSignup": False,
            "flowToken": flow_token,
            "isAccessPassSupported": True,
            "isQrCodePinSupported": True,
        }
        headers = _browser_cors_headers(
            origin="https://login.microsoftonline.com",
            referer=current_url,
            content_type="application/json; charset=UTF-8",
            hpgact=str(hpgact),
            hpgid=str(hpgid),
        )
        headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": "https://login.microsoftonline.com",
            "Referer": current_url,
            "canary": canary,
            "client-request-id": correlation_id,
            "hpgact": str(hpgact),
            "hpgid": str(hpgid),
        })
        logger.info(
            "[outlook-oauth] common credential request email=%s url=%s payload=%s",
            email,
            _safe_url(credential_url),
            _field_evidence(payload),
        )
        resp = session.post(credential_url, json=payload, headers=headers, timeout=timeout, allow_redirects=False)
        try:
            data = resp.json()
        except Exception:
            data = {}
        logger.info(
            "[outlook-oauth] common credential response email=%s status=%s keys=%s if_exists=%s has_password=%s flow_len=%s api_canary_len=%s",
            email,
            getattr(resp, "status_code", ""),
            sorted(data.keys()) if isinstance(data, dict) else [],
            data.get("IfExistsResult") if isinstance(data, dict) else "",
            ((data.get("Credentials") or {}).get("HasPassword") if isinstance(data, dict) and isinstance(data.get("Credentials"), dict) else ""),
            len(str(data.get("FlowToken") or "")) if isinstance(data, dict) else 0,
            len(str(data.get("apiCanary") or "")) if isinstance(data, dict) else 0,
        )
    msa_url = _extract_js_string(text, "urlMsaSignUp") or _extract_js_string(text, "urlGoToAADError")
    if not msa_url:
        raise OutlookOAuthError("common authorize page missing urlMsaSignUp")
    msa_url = _append_query(
        msa_url,
        {
            "username": email,
            "login_hint": email,
            "tenant": "common",
            "ui_locales": "zh-CN",
            "jshs": "1",
            "jsh": "",
            "jshp": "",
            "signup": None,
            "lw": None,
            "fl": None,
        },
    )
    logger.info("[outlook-oauth] common to live email=%s url=%s query_keys=%s", email, _safe_url(msa_url, max_len=500), _url_query_keys(msa_url))
    _har_sleep("common_gct_to_live_authorize_auth2", 0.7)
    return session.get(
        msa_url,
        headers=_browser_nav_headers(referer="https://login.microsoftonline.com/", site="cross-site"),
        timeout=timeout,
        allow_redirects=False,
    )


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


def _exchange_code(
    session: Any,
    *,
    client_id: str,
    client_secret: str = "",
    code: str,
    redirect_uri: str,
    scope: str,
    timeout: int,
) -> OutlookOAuthResult:
    data = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": scope,
    }
    if client_secret:
        data["client_secret"] = client_secret
    resp = session.post(
        TOKEN_ENDPOINT,
        data=data,
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


def _oauth_settings(cfg: Config) -> tuple[str, str, str, str, str, int]:
    client_id = str(_cfg_value(cfg, "mail_oauth_client_id", "") or "").strip()
    if not client_id:
        raise OutlookOAuthError("portal_protocol.mail_oauth_client_id 为空")
    client_secret = str(
        os.environ.get("MAIL_OAUTH_CLIENT_SECRET", "")
        or _cfg_value(cfg, "mail_oauth_client_secret", "")
        or ""
    ).strip()
    redirect_uri = str(_cfg_value(cfg, "mail_oauth_redirect_uri", "http://localhost") or "http://localhost").strip()
    scope = str(_cfg_value(cfg, "mail_oauth_scope", "offline_access https://outlook.office.com/IMAP.AccessAsUser.All") or "").strip()
    prompt = str(_cfg_value(cfg, "mail_oauth_prompt", "consent") or "").strip()
    timeout = int(_cfg_value(cfg, "timeout_s", 30) or 30)
    return client_id, client_secret, redirect_uri, scope, prompt, timeout


def _authorize_url(
    cfg: Config,
    *,
    email: str,
    prompt_override: str | None = None,
    endpoint: str = AUTHORIZE_ENDPOINT,
    include_login_hint: bool = True,
) -> tuple[str, str, str, str, int]:
    client_id, _client_secret, redirect_uri, scope, prompt, timeout = _oauth_settings(cfg)
    if prompt_override is not None:
        prompt = prompt_override
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "response_mode": "query",
    }
    if include_login_hint:
        params["login_hint"] = email
    if prompt:
        params["prompt"] = prompt
    return endpoint + "?" + urlencode(params, quote_via=quote), client_id, redirect_uri, scope, timeout


def _requests_oauth_session(cfg: Config) -> Any:
    proxy = str(getattr(cfg, "proxy", "") or "").strip()
    session = create_http_session(proxy=proxy or None, impersonate=str(_cfg_value(cfg, "mail_oauth_impersonate", "chrome131") or "chrome131"))
    session.headers.update({
        "User-Agent": str(_cfg_value(cfg, "user_agent", "") or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
        )),
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    logger.info(
        "[outlook-oauth] HTTP session type=%s impersonate=%s proxy=%s",
        type(session).__name__,
        getattr(session, "impersonate", ""),
        bool(proxy),
    )
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


def _click_browser_text_match(page: Any, patterns: list[str], *, timeout: int = 2500) -> bool:
    script = """(patterns) => {
      const needles = patterns.map((p) => String(p).toLowerCase());
      const nodes = Array.from(document.querySelectorAll('button,a,input[type="button"],input[type="submit"],[role="button"]'));
      for (const el of nodes) {
        const text = String(el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if (!text) continue;
        if (needles.some((p) => text.includes(p))) {
          el.click();
          return {ok: true, text};
        }
      }
      return {ok: false};
    }"""
    try:
        result = page.evaluate(script, patterns)
        if isinstance(result, dict) and result.get("ok"):
            page.wait_for_timeout(timeout)
            return True
    except Exception:
        pass
    return False


def _handle_browser_consent_update(page: Any) -> dict[str, Any]:
    script = """() => {
      const visible = node => {
        if (!node) return false;
        const r = node.getBoundingClientRect();
        const s = getComputedStyle(node);
        return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden' && !node.disabled;
      };
      const textOf = node => String(
        node.innerText || node.textContent || node.value || node.getAttribute('aria-label') || ''
      ).trim();
      const bodyText = String(document.body && document.body.innerText || '');
      const nodes = Array.from(document.querySelectorAll(
        '#idBtn_Accept,input[id="idBtn_Accept"],button,input[type="button"],input[type="submit"],a,[role="button"]'
      )).filter(visible);
      const acceptNeedles = ['accept', 'yes', 'continue', 'allow', '同意', '允许', '接受', '是', '继续'];
      const accept = nodes.find(el => {
        const t = textOf(el).toLowerCase();
        return el.id === 'idBtn_Accept' || acceptNeedles.some(n => t.includes(n));
      });
      if (accept) {
        accept.focus();
        accept.click();
        return {ok: true, mode: 'click', id: accept.id || '', text: textOf(accept).slice(0, 80), bodyLen: bodyText.length, buttons: nodes.length};
      }

      const forms = Array.from(document.querySelectorAll('form')).filter(visible);
      const form = forms[0] || document.querySelector('form');
      if (form) {
        const ensureHidden = (name, value) => {
          let el = form.querySelector(`input[name="${name}"]`);
          if (!el) {
            el = document.createElement('input');
            el.type = 'hidden';
            el.name = name;
            form.appendChild(el);
          }
          if (!el.value) el.value = value;
        };
        ensureHidden('ucaction', 'Yes');
        const submitter = Array.from(form.querySelectorAll('button,input[type="submit"],input[type="button"]'))
          .filter(visible)
          .find(el => {
            const t = textOf(el).toLowerCase();
            return el.id === 'idBtn_Accept' || acceptNeedles.some(n => t.includes(n));
          }) || null;
        if (form.requestSubmit) form.requestSubmit(submitter || undefined);
        else form.submit();
        return {ok: true, mode: 'form_submit', action: String(form.getAttribute('action') || '').slice(0, 160), bodyLen: bodyText.length, buttons: nodes.length};
      }
      return {ok: false, mode: 'not_found', bodyLen: bodyText.length, buttons: nodes.length, text: bodyText.slice(0, 160)};
    }"""
    try:
        result = page.evaluate(script)
        if isinstance(result, dict):
            return result
    except Exception as e:
        return {"ok": False, "mode": "exception", "error": str(e)[:200]}
    return {"ok": False, "mode": "no_result"}


def _passkey_success_url(current_url: str) -> str:
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query)
    ru = str((qs.get("ru") or [""])[0] or "").strip()
    if not ru:
        return ""
    target = urlparse(ru)
    target_qs = parse_qs(target.query)
    target_qs["res"] = ["success"]
    query = urlencode({k: v[-1] for k, v in target_qs.items() if v}, doseq=False)
    return urlunparse(target._replace(query=query))


def _passkey_enroll_url(current_url: str) -> str:
    parsed = urlparse(current_url)
    qs = parse_qs(parsed.query)
    ru = str((qs.get("ru") or [""])[0] or "").strip()
    if not ru:
        return ""
    params = {
        "uaid": str((parse_qs(urlparse(ru).query).get("uaid") or qs.get("uaid") or [""])[0] or ""),
        "ru": ru,
        "uiflavor": str((qs.get("uiflavor") or ["web"])[0] or "web"),
        "mkt": str((qs.get("mkt") or ["ZH-CN"])[0] or "ZH-CN"),
    }
    return "https://account.live.com/interrupt/passkey/enroll?" + urlencode(params, quote_via=quote)


def _log_browser_cookie_names(page: Any, *, label: str) -> None:
    try:
        urls = [
            "https://login.live.com",
            "https://account.live.com",
            "https://login.microsoftonline.com",
            "https://login.microsoft.com",
        ]
        cookies = page.context.cookies(urls)
        by_domain: dict[str, list[str]] = {}
        for cookie in cookies or []:
            domain = str(cookie.get("domain") or "")
            name = str(cookie.get("name") or "")
            if not domain or not name:
                continue
            by_domain.setdefault(domain, []).append(name)
        compact = {domain: sorted(set(names)) for domain, names in sorted(by_domain.items())}
        logger.info("[outlook-oauth] cookie names label=%s domains=%s", label, compact)
    except Exception as e:
        logger.debug("[outlook-oauth] cookie names failed label=%s error=%s", label, e)


def authorize_outlook_mailbox_browser(cfg: Config, page: Any, *, email: str, password: str = "") -> OutlookOAuthResult:
    """Authorize mailbox in the already logged-in browser context, then exchange code."""
    auth_url, client_id, redirect_uri, scope, timeout = _authorize_url(
        cfg,
        email=email,
        prompt_override="",
        endpoint=COMMON_AUTHORIZE_ENDPOINT,
        include_login_hint=False,
    )
    login_auth_url, _login_client_id, _login_redirect_uri, _login_scope, _login_timeout = _authorize_url(cfg, email=email, prompt_override="login")
    _client_id, client_secret, _redirect_uri, _scope, _prompt, _timeout = _oauth_settings(cfg)
    logger.info("[outlook-oauth] browser authorize start email=%s client_id=%s", email, client_id)
    _log_browser_cookie_names(page, label="before_common_authorize")
    try:
        page.add_init_script(
            """(() => {
              const block = async () => { throw new DOMException('NotAllowedError', 'NotAllowedError'); };
              if (navigator.credentials) {
                try { navigator.credentials.create = block; } catch (_) {}
              }
            })();"""
        )
    except Exception:
        pass
    try:
        page.goto(auth_url, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
    except Exception as e:
        current = str(getattr(page, "url", "") or "")
        if "code=" not in current and "error=" not in current:
            logger.debug("[outlook-oauth] browser goto authorize raised before code: %s", e)

    deadline = __import__("time").time() + max(float(timeout), 45.0)
    passkey_seen = False
    denied_retries = 0
    while __import__("time").time() < deadline:
        current_url = str(getattr(page, "url", "") or "")
        code = _url_auth_code(current_url, redirect_uri)
        if code:
            result = _exchange_code(
                _requests_oauth_session(cfg),
                client_id=client_id,
                client_secret=client_secret,
                code=code,
                redirect_uri=redirect_uri,
                scope=scope,
                timeout=timeout,
            )
            logger.info("[outlook-oauth] browser refresh_token acquired email=%s client_id=%s rt_len=%s", email, client_id, len(result.refresh_token))
            return result
        oauth_error = _url_oauth_error(current_url)
        if oauth_error:
            if "denied access" in oauth_error.lower() and denied_retries < int(os.environ.get("OUTLOOK_OAUTH_DENIED_RETRIES", "5") or "5"):
                passkey_seen = False
                denied_retries += 1
                retry_url = auth_url if denied_retries != 2 else login_auth_url
                logger.info("[outlook-oauth] retry authorize after access_denied email=%s retry=%s prompt=%s", email, denied_retries, "login" if retry_url == login_auth_url else "common")
                page.goto(retry_url, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
                page.wait_for_timeout(1500)
                deadline = max(deadline, __import__("time").time() + max(float(timeout), 45.0))
                continue
            raise OutlookOAuthError(f"browser authorize error: {oauth_error[:200]}")

        text = ""
        try:
            text = (page.inner_text("body", timeout=1500) or "").lower()
        except Exception:
            pass

        locked_markers = (
            "account locked",
            "account has been locked",
            "temporarily locked",
            "temporarily suspended",
            "help us secure your account",
            "your account has been temporarily suspended",
            "帐户已锁定",
            "账户已锁定",
            "帮助我们保护你的帐户",
            "帮助我们保护你的账户",
            "暂时挂起",
            "已暂时锁定",
        )
        if any(k in current_url.lower() or k in text for k in locked_markers):
            logger.info(
                "[outlook-oauth] account lock/interruption page detected email=%s url=%s text=%s",
                email,
                current_url[:500],
                re.sub(r"\s+", " ", text)[:240],
            )
            if _click_browser_text_match(page, ["下一步", "继续", "next", "continue"]):
                logger.info("[outlook-oauth] clicked lock/interruption continue email=%s", email)
                page.wait_for_timeout(3000)
                continue

        challenge_markers = (
            "account.live.com/abuse",
            "iframe.hsprotect.net",
            "captcha.hsprotect.net",
            "px-captcha",
            "hsprotect",
            "human challenge",
            "prove you're human",
            "press and hold",
            "证明你不是机器人",
            "按住",
            "长按",
        )
        if any(k in current_url.lower() or k in text for k in challenge_markers):
            logger.info("[outlook-oauth] browser human challenge detected email=%s url=%s", email, current_url[:500])
            try:
                from outlook_browser_register import _challenge_still_visible, _press_and_hold

                max_press_raw = str(os.environ.get("OUTLOOK_OAUTH_MAX_PRESS", os.environ.get("OUTLOOK_REG_MAX_PRESS", "4")) or "4")
                max_press = int(max_press_raw) if max_press_raw.isdigit() else 4
                prev_hold_max = os.environ.get("OUTLOOK_HOLD_MAX_S")
                oauth_hold_max = str(os.environ.get("OUTLOOK_OAUTH_HOLD_MAX_S", "") or "").strip()
                try:
                    if oauth_hold_max:
                        os.environ["OUTLOOK_HOLD_MAX_S"] = oauth_hold_max
                    else:
                        os.environ.pop("OUTLOOK_HOLD_MAX_S", None)
                    solved = _press_and_hold(page, max_press=max_press, use_registration_success_heuristic=False)
                finally:
                    if prev_hold_max is None:
                        os.environ.pop("OUTLOOK_HOLD_MAX_S", None)
                    else:
                        os.environ["OUTLOOK_HOLD_MAX_S"] = prev_hold_max
                visible = _challenge_still_visible(page)
                logger.info(
                    "[outlook-oauth] browser human challenge handled email=%s solved=%s still_visible=%s url=%s",
                    email,
                    solved,
                    visible,
                    str(getattr(page, "url", "") or "")[:500],
                )
                if solved or not visible:
                    deadline = max(deadline, __import__("time").time() + max(float(timeout), 45.0))
                    page.wait_for_timeout(3000)
                    continue
            except Exception as e:
                logger.info("[outlook-oauth] browser human challenge handler failed email=%s error=%s", email, e)

        if any(k in current_url.lower() or k in text for k in ("passkey", "fido", "密钥", "安全窗口")):
            passkey_seen = True
            logger.info("[outlook-oauth] passkey/fido interrupt detected email=%s url=%s", email, current_url[:500])
            deadline = max(deadline, __import__("time").time() + max(float(timeout), 45.0))
            enroll_url = _passkey_enroll_url(current_url)
            if enroll_url:
                try:
                    # HAR evidence: the success path first posts the current
                    # /interrupt/passkey URL, which sets account.live.com IPT
                    # cookies, then posts /interrupt/passkey/enroll.
                    prep_resp = page.context.request.post(
                        current_url,
                        data="",
                        headers={
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": "https://login.live.com",
                            "Referer": "https://login.live.com/",
                        },
                        max_redirects=0,
                    )
                    logger.info("[outlook-oauth] passkey interrupt post email=%s status=%s ok=%s", email, prep_resp.status, prep_resp.ok)
                    # HAR evidence: interrupt/passkey/enroll is an empty POST that returns
                    # a 302 Location to the original authorize URL with res=success.
                    # Playwright follows redirects by default, which hides Location and
                    # leaves the page on the enroll screen; keep the 302 visible here.
                    resp = page.context.request.post(
                        enroll_url,
                        data="",
                        headers={
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "Origin": "https://login.microsoft.com",
                            "Referer": "https://login.microsoft.com/",
                        },
                        max_redirects=0,
                    )
                    location = ""
                    try:
                        location = str(resp.headers.get("location") or "")
                    except Exception:
                        location = ""
                    if location:
                        logger.info("[outlook-oauth] passkey enroll redirect email=%s status=%s location=%s", email, resp.status, location[:160])
                        if "error.aspx" not in location.lower():
                            page.goto(location, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
                            page.wait_for_timeout(1500)
                            continue
                    logger.info("[outlook-oauth] passkey enroll post email=%s status=%s ok=%s no_location", email, resp.status, resp.ok)
                    if resp.ok:
                        page.wait_for_timeout(1500)
                        continue
                except Exception as e:
                    logger.debug("[outlook-oauth] passkey enroll post failed: %s", e)
            success_url = _passkey_success_url(current_url)
            if success_url:
                try:
                    page.goto(success_url, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
                    page.wait_for_timeout(1500)
                    continue
                except Exception as e:
                    logger.debug("[outlook-oauth] passkey success redirect failed: %s", e)
            if "account.live.com/interrupt/passkey" in current_url.lower():
                if _click_browser_text_match(page, ["继续", "下一步", "continue", "next"]):
                    continue
            if "login.microsoft.com/consumers/fido/create" in current_url.lower():
                try:
                    page.goto(auth_url, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
                    page.wait_for_timeout(1500)
                    continue
                except Exception as e:
                    logger.debug("[outlook-oauth] fido/create authorize fallback failed: %s", e)
            if _click_browser_text_match(page, ["跳过", "稍后", "以后", "skip", "not now", "later"]):
                continue
            try:
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)
            except Exception:
                pass
            try:
                page.go_back(wait_until="domcontentloaded", timeout=5000)
                page.wait_for_timeout(1500)
                continue
            except Exception:
                pass
            try:
                page.goto(auth_url, wait_until="domcontentloaded", timeout=max(timeout, 45) * 1000)
                continue
            except Exception:
                pass

        if "consent/update" in current_url.lower():
            action = _handle_browser_consent_update(page)
            logger.info("[outlook-oauth] browser consent/update handled email=%s action=%s url=%s", email, action, current_url[:260])
            if action.get("ok"):
                page.wait_for_timeout(3500)
                deadline = max(deadline, __import__("time").time() + max(float(timeout), 45.0))
                continue

        # Same context usually skips login, but common authorize may ask again.
        # Handle the account identifier page before password because Microsoft
        # keeps hidden password fields in the DOM on the email step.
        try:
            email_action = page.evaluate(
                """value => {
                  const visible = node => {
                    if (!node) return false;
                    const r = node.getBoundingClientRect();
                    const s = getComputedStyle(node);
                    return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden' && !node.disabled;
                  };
                  const pageText = String(document.body && document.body.innerText || '').toLowerCase();
                  const candidates = [
                    document.querySelector('#i0116'),
                    document.querySelector('input[name="loginfmt"]'),
                    document.querySelector('input[type="email"]'),
                    ...document.querySelectorAll('input[type="text"], input[type="tel"]')
                  ].filter(visible);
                  const el = candidates.find(node => {
                    const t = `${node.id || ''} ${node.name || ''} ${node.type || ''} ${node.getAttribute('aria-label') || ''} ${node.getAttribute('placeholder') || ''} ${node.getAttribute('autocomplete') || ''}`.toLowerCase();
                    return t.includes('login') || t.includes('email') || t.includes('username') || t.includes('电子邮件') || t.includes('skype') || node.id === 'i0116';
                  }) || (pageText.includes('电子邮件、电话') || pageText.includes('skype') ? candidates[0] : null);
                  if (!el) return { found: false, inputs: candidates.length, pageText: pageText.slice(0, 120) };
                  const proto = Object.getPrototypeOf(el);
                  const desc = Object.getOwnPropertyDescriptor(proto, 'value') || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
                  if (desc && desc.set) desc.set.call(el, value);
                  else el.value = value;
                  el.focus();
                  for (const name of ['input', 'change', 'keyup', 'blur']) {
                    el.dispatchEvent(new Event(name, { bubbles: true }));
                  }
                  const buttons = [
                    document.querySelector('#idSIButton9'),
                    ...document.querySelectorAll('input[type="submit"], button[type="submit"], button, [role="button"]')
                  ].filter(visible);
                  const submit = buttons.find(b => {
                    const t = String(b.value || b.innerText || b.textContent || b.getAttribute('aria-label') || '').toLowerCase();
                    return b.id === 'idSIButton9' || t.includes('next') || t.includes('下一步');
                  }) || buttons[0];
                  if (submit) {
                    submit.focus();
                    submit.click();
                    return { found: true, clicked: true, id: submit.id || '', text: String(submit.value || submit.innerText || submit.textContent || '').slice(0, 80) };
                  }
                  return { found: true, clicked: false, buttons: buttons.length };
                }""",
                email,
            )
            if isinstance(email_action, dict) and email_action.get("found"):
                _log_browser_cookie_names(page, label="common_authorize_login_page")
                logger.info("[outlook-oauth] submitted email/login_hint on common authorize email=%s action=%s url=%s", email, email_action, current_url[:180])
                page.wait_for_timeout(3500)
                continue
        except Exception:
            pass

        if password:
            try:
                pwd = page.locator('input[type="password"], input[name="passwd"]').first
                if pwd.count() > 0 and pwd.is_visible(timeout=500):
                    _log_browser_cookie_names(page, label="common_authorize_password_page")
                    action = pwd.evaluate(
                        """(el, value) => {
                          el.focus(); el.value = value;
                          el.dispatchEvent(new Event('input', {bubbles: true}));
                          el.dispatchEvent(new Event('change', {bubbles: true}));
                          const visible = node => {
                            if (!node) return false;
                            const r = node.getBoundingClientRect();
                            const s = getComputedStyle(node);
                            return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden' && !node.disabled;
                          };
                          const buttons = [
                            document.querySelector('#idSIButton9'),
                            ...document.querySelectorAll('input[type="submit"], button[type="submit"], button, [role="button"]')
                          ].filter(visible);
                          const submit = buttons.find(b => {
                            const t = String(b.value || b.innerText || b.textContent || b.getAttribute('aria-label') || '').toLowerCase();
                            return b.id === 'idSIButton9' || t.includes('sign in') || t.includes('next') || t.includes('登录') || t.includes('下一步');
                          }) || buttons[0];
                          if (submit) {
                            submit.focus();
                            submit.click();
                            return { clicked: true, id: submit.id || '', text: String(submit.value || submit.innerText || submit.textContent || '').slice(0, 80) };
                          }
                          return { clicked: false, buttons: buttons.length };
                        }""",
                        password,
                    )
                    logger.info("[outlook-oauth] submitted password email=%s action=%s", email, action)
                    page.wait_for_timeout(3500)
                    continue
            except Exception:
                pass

        if any(k in text for k in ("accept", "consent", "permissions requested", "requested permissions", "permission", "同意", "允许", "接受", "权限")):
            if _click_browser_first(
                page,
                [
                    '#idBtn_Accept',
                    'input[id="idBtn_Accept"]',
                    'button:has-text("Accept")',
                    'button:has-text("Yes")',
                    'button:has-text("Continue")',
                    'button:has-text("同意")',
                    'button:has-text("允许")',
                    'button:has-text("接受")',
                    'button:has-text("是")',
                    'input[type="submit"][value="Yes"]',
                    'input[type="submit"][value="Accept"]',
                    'input[type="submit"][value="允许"]',
                    'input[type="submit"][value="同意"]',
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

        if _click_browser_first(page, ['button:has-text("继续")', 'button:has-text("下一步")', 'button:has-text("Continue")', 'button:has-text("Next")', 'input[type="submit"]', 'button[type="submit"]'], timeout=1200):
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
    if str(_cfg_value(cfg, "mail_oauth_har_entry", "") or "").strip().lower() in {"1", "true", "yes"}:
        auth_url, client_id, redirect_uri, scope, timeout = _authorize_url(
            cfg,
            email=email,
            prompt_override="",
            endpoint=COMMON_AUTHORIZE_ENDPOINT,
            include_login_hint=False,
        )
    _client_id, client_secret, _redirect_uri, _scope, _prompt, _timeout = _oauth_settings(cfg)
    logger.info("[outlook-oauth] authorize start email=%s client_id=%s", email, client_id)
    resp = session.get(auth_url, headers=_browser_nav_headers(site="none"), timeout=timeout, allow_redirects=False)
    logger.info(
        "[outlook-oauth] initial response email=%s status=%s url=%s location=%s",
        email,
        getattr(resp, "status_code", ""),
        _safe_url(str(getattr(resp, "url", "") or ""), max_len=500),
        _safe_url(str(getattr(resp, "headers", {}).get("Location") or ""), max_len=500),
    )
    resp = _follow_redirects(session, resp, redirect_uri, timeout)

    for step in range(20):
        current_url = str(getattr(resp, "url", "") or "")
        code = _url_auth_code(current_url, redirect_uri)
        if code:
            result = _exchange_code(
                session,
                client_id=client_id,
                client_secret=client_secret,
                code=code,
                redirect_uri=redirect_uri,
                scope=scope,
                timeout=timeout,
            )
            logger.info("[outlook-oauth] refresh_token acquired email=%s client_id=%s rt_len=%s", email, client_id, len(result.refresh_token))
            return result
        oauth_error = _url_oauth_error(current_url)
        if oauth_error:
            raise OutlookOAuthError(f"authorize error: {oauth_error[:200]}")

        text = _response_text(resp)
        action_probe, form_probe = _first_form(text)
        logger.info(
            "[outlook-oauth] step email=%s step=%s status=%s url=%s query_keys=%s text_len=%s markers=%s form_action=%s form_keys=%s js=%s",
            email,
            step,
            getattr(resp, "status_code", ""),
            _safe_url(current_url, max_len=500),
            _url_query_keys(current_url),
            len(text),
            _page_markers(text),
            action_probe[:160],
            sorted(form_probe.keys()),
            {
                "urlMsaSignUp": bool(_extract_js_string(text, "urlMsaSignUp")),
                "urlGetCredentialType": bool(_extract_js_string(text, "urlGetCredentialType")),
                "urlPost": bool(_extract_js_string(text, "urlPost")),
                "sFT_len": len(_extract_js_string(text, "sFT")),
                "sCtx_len": len(_extract_js_string(text, "sCtx")),
                "canary_len": len(_extract_js_string(text, "canary")),
            },
        )
        if "PageID\" content=\"BssoInterrupt" in text or "pageid\" content=\"bssointerrupt" in text.lower():
            reload_url = _append_query(current_url, {"sso_reload": "true"})
            logger.info("[outlook-oauth] bsso interrupt reload email=%s step=%s url=%s", email, step, _safe_url(reload_url, max_len=500))
            resp = session.get(reload_url, headers=_browser_nav_headers(referer=current_url, site="same-origin", user=False), timeout=timeout, allow_redirects=False)
            resp = _follow_redirects(session, resp, redirect_uri, timeout)
            continue
        if "login.microsoftonline.com/common/oauth2/v2.0/authorize" in current_url and _extract_js_string(text, "urlMsaSignUp"):
            logger.info("[outlook-oauth] submitting common username email=%s step=%s", email, step)
            resp = _submit_common_username(
                session,
                current_url=current_url,
                text=text,
                email=email,
                timeout=timeout,
            )
            resp = _follow_redirects(session, resp, redirect_uri, timeout)
            continue

        flow_token, post_url, ctx = _extract_ppft_and_post_url(text)
        if flow_token:
            if not post_url:
                post_url = "https://login.live.com/ppsecure/post.srf"
            if "getexperimentassignments" in text.lower():
                _har_sleep("live_authorize_to_experiments_auth2", 1.9)
                _post_experiment_assignments(session, current_url=current_url, timeout=timeout)
                _touch_live_fingerprint(session, current_url=current_url, text=text, timeout=timeout)
                _har_sleep("experiments_to_checkpassword_auth2", 8.8)
            vanguardflowtoken = _post_login_prefetches(
                session,
                current_url=current_url,
                text=text,
                email=email,
                password=password,
                timeout=timeout,
            )
            _har_sleep("checkpassword_to_ppsecure_auth2", 0.35)
            login_data = _login_form_payload(
                text,
                email=email,
                password=password,
                flow_token=flow_token,
                ctx=ctx,
                vanguardflowtoken=vanguardflowtoken,
            )
            logger.info(
                "[outlook-oauth] submitting password email=%s step=%s action=%s fields=%s evidence=%s",
                email,
                step,
                _safe_url(_absolute_url(current_url, post_url), max_len=500),
                sorted(login_data.keys()),
                _field_evidence(login_data),
            )
            logger.info("[outlook-oauth] pre-ppsecure cookies email=%s cookies=%s", email, _session_cookie_evidence(session))
            resp = session.post(
                _absolute_url(current_url, post_url),
                data=login_data,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "Cache-Control": "max-age=0",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Origin": "https://login.live.com",
                    "Referer": current_url,
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                    **_chrome_client_hints(platform_version=True),
                },
                timeout=timeout,
                allow_redirects=False,
            )
            logger.info(
                "[outlook-oauth] password response email=%s status=%s url=%s location=%s",
                email,
                getattr(resp, "status_code", ""),
                _safe_url(str(getattr(resp, "url", "") or ""), max_len=500),
                _safe_url(str(getattr(resp, "headers", {}).get("Location") or ""), max_len=500),
            )
            resp = _follow_redirects(session, resp, redirect_uri, timeout)
            continue

        if "ppsecure/post.srf" in current_url and ("type=28" in text or "PPFT" in text):
            action, form_data = _first_form(text)
            if action and form_data.get("PPFT"):
                form_data.setdefault("LoginOptions", "3")
                form_data.setdefault("type", "28")
                form_data.setdefault("canary", "")
                form_data.setdefault("hpgrequestid", "")
                form_data.setdefault("ctx", "")
                logger.info("[outlook-oauth] submitting second ppsecure form email=%s step=%s", email, step)
                resp = _post_browser_form(
                    session,
                    _absolute_url(current_url, action),
                    form_data,
                    referer=current_url,
                    origin="https://login.live.com",
                    timeout=timeout,
                )
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
                _har_sleep("consent_read_to_accept_auth2", 3.9)
                resp = _post_browser_form(
                    session,
                    current_url,
                    consent_data,
                    referer=current_url,
                    origin="https://account.live.com",
                    timeout=timeout,
                )
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue
            action, form_data = _first_form(text)
            if action and form_data:
                if "ucaction" not in form_data and "canary" in form_data:
                    form_data.setdefault("ucaction", "Yes")
                logger.info("[outlook-oauth] submitting consent form email=%s step=%s action=%s", email, step, action[:80])
                _har_sleep("consent_form_to_accept_auth2", 3.9)
                resp = _post_browser_form(
                    session,
                    _absolute_url(current_url, action),
                    form_data,
                    referer=current_url,
                    origin="https://account.live.com",
                    timeout=timeout,
                )
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        if "consumers/savestate" in current_url:
            action, form_data = _first_form(text)
            if action and form_data:
                logger.info("[outlook-oauth] submitting savestate form email=%s step=%s", email, step)
                resp = _post_browser_form(
                    session,
                    _absolute_url(current_url, action),
                    form_data,
                    referer=current_url,
                    origin="https://login.live.com",
                    site="cross-site",
                    timeout=timeout,
                    user=False,
                )
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        if "proofs/Add" in current_url or "proofs/add" in current_url:
            action, form_data = _first_form(text)
            if action:
                form_data["action"] = "Skip"
                logger.info("[outlook-oauth] skipping proofs/Add email=%s step=%s", email, step)
                _har_sleep("proofs_add_read_to_skip_auth2", 4.0)
                resp = _post_browser_form(
                    session,
                    _absolute_url(current_url, action),
                    form_data,
                    referer=current_url,
                    origin="https://account.live.com",
                    timeout=timeout,
                )
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        if "DoSubmit" in text or ("fmHF" in text and "onload" in text):
            action, form_data = _first_form(text)
            if action:
                logger.info("[outlook-oauth] submitting hidden redirect form email=%s step=%s", email, step)
                target = _absolute_url(current_url, action)
                origin = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
                resp = _post_browser_form(session, target, form_data, referer=current_url, origin=origin, timeout=timeout, user=False)
                resp = _follow_redirects(session, resp, redirect_uri, timeout)
                continue

        action, form_data = _first_form(text)
        if action:
            lowered = (action + " " + current_url).lower()
            if "consent" in lowered:
                form_data.setdefault("ucaccept", "Yes")
                form_data.setdefault("ucaction", "Yes")
            logger.info("[outlook-oauth] submitting form email=%s step=%s action=%s", email, step, action[:80])
            target = _absolute_url(current_url, action)
            origin = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
            resp = _post_browser_form(session, target, form_data, referer=current_url, origin=origin, timeout=timeout)
            resp = _follow_redirects(session, resp, redirect_uri, timeout)
            continue

        marker = re.sub(r"\s+", " ", text[:160])
        raise OutlookOAuthError(f"authorize stuck url={current_url[:120]} body={marker}")

    raise OutlookOAuthError("authorize did not reach auth code")
