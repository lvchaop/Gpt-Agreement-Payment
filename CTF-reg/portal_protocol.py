"""Pure HTTP portal signup flow based on the Live signup HAR shape."""
from __future__ import annotations

import html
import base64
import json
import logging
import os
import random
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

from config import Config
from http_client import create_http_session
from portal_identity import generate_password, next_username

logger = logging.getLogger(__name__)

PORTAL_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) PKeyAuth/1.0"
)

_COUNTRY_DATE_ORDERS = {
    "US": "MDY",
    "GB": "DMY",
    "UK": "DMY",
    "JP": "DMY",
}


class PortalProtocolError(RuntimeError):
    """Raised when the portal protocol flow cannot complete."""


class PortalChallengeError(PortalProtocolError):
    """Raised when Live signup returns a browser challenge."""

    def __init__(
        self,
        reason: str,
        *,
        stage: str = "",
        email: str = "",
        password: str = "",
        username_seq: int = 0,
        marker: str = "",
    ):
        self.reason = reason
        self.stage = stage
        self.email = email
        self.password = password
        self.username_seq = username_seq
        self.marker = marker
        suffix = f" marker={marker}" if marker else ""
        super().__init__(f"portal challenge detected stage={stage or '<unknown>'} reason={reason}{suffix}")


@dataclass
class PortalSignupState:
    signup_url: str
    api_canary: str
    uaid: str
    client_id: str
    mkt: str
    hpgid: int
    scid: int
    uiflvr: int
    check_url: str
    create_url: str
    server_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PortalProtocolResult:
    email: str
    password: str
    username_seq: int
    final_url: str = ""
    oauth_code_captured: bool = False
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
            "register_method": "portal_protocol",
            "portal_username_seq": self.username_seq,
            "portal_final_url": self.final_url,
            "portal_oauth_code_captured": self.oauth_code_captured,
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


def _extract_server_data(text: str) -> dict[str, Any]:
    marker = "var ServerData"
    idx = text.find(marker)
    if idx < 0:
        raise PortalProtocolError("signup page 未找到 ServerData")
    start = text.find("{", idx)
    if start < 0:
        raise PortalProtocolError("signup page ServerData JSON 起点缺失")

    depth = 0
    in_string = False
    quote = ""
    escape = False
    end = -1
    for pos in range(start, len(text)):
        ch = text[pos]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                break
    if end < 0:
        raise PortalProtocolError("signup page ServerData JSON 终点缺失")
    try:
        data = json.loads(text[start:end])
    except Exception as e:
        raise PortalProtocolError(f"signup page ServerData JSON 解析失败: {e}") from e
    if not isinstance(data, dict):
        raise PortalProtocolError("signup page ServerData 不是对象")
    return data


def _with_query(base_url: str, source_url: str) -> str:
    source_query = parse_qsl(urlparse(source_url).query, keep_blank_values=True)
    parsed = urlparse(base_url)
    merged = parse_qsl(parsed.query, keep_blank_values=True) + source_query
    return urlunparse(parsed._replace(query=urlencode(merged)))


def _json_or_error(resp, label: str) -> dict:
    try:
        data = resp.json()
    except Exception as e:
        text = (getattr(resp, "text", "") or "")[:200]
        raise PortalProtocolError(f"{label} 返回非 JSON: {text}") from e
    if not isinstance(data, dict):
        raise PortalProtocolError(f"{label} JSON 顶层不是对象")
    return data


_CHALLENGE_MARKERS: dict[str, tuple[str, ...]] = {
    "perimeterx": (
        "perimeterx",
        "px-captcha",
        "_px.init",
        "_pxhd",
        "pxvid",
        "px3",
        "pxde",
        "px-block",
        "hsprotect",
        "press and hold",
        "bot protection",
        "按住",
        "长按",
    ),
    "arkose": (
        "arkose",
        "funcaptcha",
        "arkose_enforcement",
        "enforcement",
        "fc-token",
    ),
    "microsoft_hip": (
        "hiptemplatecontainer",
        "hippaneform",
        "gethip",
        "hipchallenge",
    ),
    "generic_challenge": (
        "humancaptcha",
        "verify you are human",
        "security check",
        "unusual activity",
        "challenge-platform",
    ),
}


def detect_outlook_challenge(resp: Any = None, data: Any = None) -> tuple[str, str]:
    """Return (reason, marker) when a Live/Outlook challenge is visible.

    The protocol lane should not treat bare HTTP status as a challenge.  We only
    trigger on concrete Live/PerimeterX/Arkose/HIP markers found in URL,
    Location, HTML, or JSON payloads.
    """
    parts: list[str] = []
    if resp is not None:
        parts.append(str(getattr(resp, "url", "") or ""))
        try:
            parts.append(str((getattr(resp, "headers", {}) or {}).get("Location", "") or ""))
        except Exception:
            pass
        parts.append(str(getattr(resp, "text", "") or ""))
    if data is not None:
        try:
            parts.append(json.dumps(data, ensure_ascii=False, sort_keys=True))
        except Exception:
            parts.append(str(data))
    haystack = "\n".join(parts).lower()
    if not haystack:
        return "", ""
    for reason, markers in _CHALLENGE_MARKERS.items():
        for marker in markers:
            if marker.lower() in haystack:
                return reason, marker
    return "", ""


def _attrs(tag: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in re.finditer(r"([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(['\"])(.*?)\2", tag, re.S):
        attrs[match.group(1).lower()] = html.unescape(match.group(3))
    return attrs


def _first_form(text: str, base_url: str) -> tuple[str, str, dict[str, str]] | None:
    m = re.search(r"<form\b([^>]*)>(.*?)</form>", text, re.I | re.S)
    if not m:
        return None
    form_attrs = _attrs(m.group(1))
    body = m.group(2)
    action = urljoin(base_url, form_attrs.get("action") or base_url)
    method = (form_attrs.get("method") or "GET").upper()
    fields: dict[str, str] = {}
    for input_match in re.finditer(r"<input\b([^>]*)>", body, re.I | re.S):
        input_attrs = _attrs(input_match.group(1))
        name = input_attrs.get("name")
        if name:
            fields[name] = input_attrs.get("value", "")
    return method, action, fields


def _redirect_from_html(text: str, base_url: str) -> str:
    meta = re.search(r"http-equiv=['\"]refresh['\"][^>]+content=['\"][^;]+;\s*url=([^'\"]+)['\"]", text, re.I)
    if meta:
        return urljoin(base_url, html.unescape(meta.group(1)))
    js = re.search(r"(?:location\.href|window\.location)\s*=\s*['\"]([^'\"]+)['\"]", text, re.I)
    if js:
        return urljoin(base_url, html.unescape(js.group(1)))
    return ""


class PortalProtocol:
    def __init__(self, cfg: Config, session=None):
        self.cfg = cfg
        self.timeout = float(_cfg_value(cfg, "timeout_s", 30) or 30)
        self.user_agent = str(_cfg_value(cfg, "user_agent", PORTAL_USER_AGENT) or PORTAL_USER_AGENT)
        self.accept_language = str(_cfg_value(cfg, "accept_language", "zh-CN,zh-Hans;q=0.9") or "zh-CN,zh-Hans;q=0.9")
        self.session = session or create_http_session(proxy=cfg.proxy, impersonate="chrome131")
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
        })

    @staticmethod
    def _safe_url_label(url: str) -> str:
        parsed = urlparse(str(url or ""))
        if not parsed.scheme and not parsed.netloc:
            return parsed.path or "<empty>"
        return urlunparse(parsed._replace(query="", fragment=""))

    @staticmethod
    def _short_id(value: str, keep: int = 6) -> str:
        text = str(value or "")
        if not text:
            return "<empty>"
        return f"{text[:keep]}...len={len(text)}"

    @staticmethod
    def _uuidish(value: str) -> str:
        text = re.sub(r"[^0-9a-fA-F]", "", str(value or ""))
        if len(text) == 32:
            return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"
        return str(value or "")

    @staticmethod
    def _js_string(text: str, name: str) -> str:
        m = re.search(rf"\b{re.escape(name)}\s*=\s*'([^']*)'", text)
        return m.group(1) if m else ""

    def _cookie_names(self) -> set[str]:
        cookies = getattr(self.session, "cookies", None)
        names: set[str] = set()
        if cookies is None:
            return names
        try:
            for cookie in cookies:
                name = getattr(cookie, "name", "")
                if name:
                    names.add(str(name))
        except Exception:
            pass
        try:
            if hasattr(cookies, "keys"):
                names.update(str(name) for name in cookies.keys())
        except Exception:
            pass
        return names

    def _navigation_headers(self, uaid: str = "") -> dict[str, str]:
        request_id = self._uuidish(uaid)
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "User-Agent": self.user_agent,
            "x-client-SKU": str(_cfg_value(self.cfg, "x_client_sku", "MSAL.xplat.macOS") or "MSAL.xplat.macOS"),
            "x-client-src-SKU": str(_cfg_value(self.cfg, "x_client_src_sku", "MSAL.xplat.macOS") or "MSAL.xplat.macOS"),
            "x-client-OS": str(_cfg_value(self.cfg, "x_client_os", "15.7.4") or "15.7.4"),
            "x-client-Ver": str(_cfg_value(self.cfg, "x_client_ver", "1.1.0+61e1eea1") or "1.1.0+61e1eea1"),
            "x-ms-sso-Ignore-SSO": "1",
            "x-ms-PKeyAuth+": "1.0",
            "return-client-request-id": "false",
            "client-request-id": request_id,
            "correlation-id": request_id,
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        }

    @staticmethod
    def _normalise_country(value: str) -> str:
        country = str(value or "").strip().upper().replace("-", "_")
        if country == "UK":
            return "GB"
        return country

    @staticmethod
    def _normalise_date_order(value: str) -> str:
        order = "".join(ch for ch in str(value or "").strip().upper() if ch in {"Y", "M", "D"})
        if len(order) == 3 and set(order) == {"Y", "M", "D"}:
            return order
        return ""

    def _register_proxy_country(self) -> str:
        meta_root = getattr(self.cfg, "proxy_meta", {}) or {}
        meta = meta_root.get("register") if isinstance(meta_root, dict) else {}
        if not isinstance(meta, dict):
            return ""
        return self._normalise_country(str(meta.get("region") or ""))

    def _effective_country(self, state: PortalSignupState) -> str:
        proxy_country = self._register_proxy_country()
        if len(proxy_country) == 2:
            return proxy_country
        cfg_country = self._normalise_country(str(_cfg_value(self.cfg, "country", "") or ""))
        if len(cfg_country) == 2:
            return cfg_country
        pref_country = self._normalise_country(str(state.server_data.get("sPrefSMSCountry") or ""))
        if len(pref_country) == 2:
            return pref_country
        return "US"

    def _date_order(self, state: PortalSignupState, country: str) -> tuple[str, str]:
        country_code = self._normalise_country(country)
        return _COUNTRY_DATE_ORDERS.get(country_code, "DMY"), f"country:{country_code or 'default'}"

    def run(self) -> PortalProtocolResult:
        state = self._load_signup_state()
        account_domain = str(_cfg_value(self.cfg, "account_domain", "outlook.com") or "outlook.com").strip().lstrip("@").lower()
        namespace = str(_cfg_value(self.cfg, "namespace", "portal-live") or "portal-live")
        state_path = str(_cfg_value(self.cfg, "state_path", "output/portal_identity_state.json") or "")
        max_retries = int(_cfg_value(self.cfg, "max_name_retries", 5) or 5)

        last_error = ""
        for attempt in range(1, max_retries + 1):
            username, seq = next_username(
                state_path,
                namespace=namespace,
                length=12,
                base_dir=_project_base_dir(),
            )
            email = f"{username}@{account_domain}"
            password = generate_password(12)
            try:
                available, state = self._check_name(state, email)
                if not available:
                    last_error = f"{email} unavailable"
                    logger.info("[portal-protocol] username unavailable attempt=%s email=%s", attempt, email)
                    continue
                create_data = self._create_account(state, email, password)
            except PortalChallengeError as e:
                if not e.email:
                    e.email = email
                if not e.password:
                    e.password = password
                if not e.username_seq:
                    e.username_seq = seq
                raise
            redirect_url = str(create_data.get("redirectUrl") or "").strip()
            if not redirect_url:
                raise PortalProtocolError("CreateAccount 成功响应缺少 redirectUrl")
            final_url = self._follow_post_create_redirect(redirect_url)
            parsed_final = urlparse(final_url)
            code_captured = bool(parse_qs(parsed_final.query).get("code"))
            logger.info("[portal-protocol] created email=%s seq=%s oauth_code=%s", email, seq, code_captured)
            mail_fields: dict[str, str] = {}
            if bool(_cfg_value(self.cfg, "mail_oauth_enabled", True)):
                from outlook_oauth import authorize_outlook_mailbox

                mail_oauth = authorize_outlook_mailbox(self.cfg, self.session, email=email, password=password)
                mail_fields = mail_oauth.to_mail_fields()
            return PortalProtocolResult(
                email=email,
                password=password,
                username_seq=seq,
                final_url=urlunparse(parsed_final._replace(query="")),
                oauth_code_captured=code_captured,
                mail_oauth_client_id=mail_fields.get("mail_account_id", ""),
                mail_access_token=mail_fields.get("mail_access_token", ""),
                mail_refresh_token=mail_fields.get("mail_refresh_token", ""),
                mail_oauth_scope=mail_fields.get("mail_oauth_scope", ""),
            )

        raise PortalProtocolError(last_error or "没有可用用户名")

    def _authorize_url(self) -> str:
        client_id = str(_cfg_value(self.cfg, "client_id", "00000000480728C5") or "00000000480728C5")
        locale = str(_cfg_value(self.cfg, "locale", "zh-CN") or "zh-CN")
        params = {
            "client_id": client_id,
            "scope": str(_cfg_value(self.cfg, "scope", "profile offline_access openid service::outlook.office.com::MBI_SSL")),
            "redirect_uri": str(_cfg_value(self.cfg, "redirect_uri", "https://login.live.com/oauth20_desktop.srf")),
            "response_type": "code",
            "x-client-SKU": str(_cfg_value(self.cfg, "x_client_sku", "MSAL.xplat.macOS")),
            "x-client-Ver": str(_cfg_value(self.cfg, "x_client_ver", "1.1.0+61e1eea1")),
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

    def _load_signup_state(self) -> PortalSignupState:
        authorize_url = self._authorize_url()
        authorize_uaid = parse_qs(urlparse(authorize_url).query).get("uaid", [""])[0]
        resp = self.session.get(
            authorize_url,
            headers=self._navigation_headers(authorize_uaid),
            timeout=self.timeout,
            allow_redirects=True,
        )
        self._raise_for_status(resp, "authorize/signup")
        self._raise_if_challenge(resp, stage="authorize/signup")
        signup_url = getattr(resp, "url", "") or ""
        data = _extract_server_data(getattr(resp, "text", "") or "")
        api_canary = str(data.get("apiCanary") or "").strip()
        uaid = str(data.get("sUnauthSessionID") or parse_qs(urlparse(signup_url).query).get("uaid", [""])[0]).strip()
        client_id = str(data.get("sClientId") or parse_qs(urlparse(signup_url).query).get("client_id", [""])[0]).strip()
        mkt = str(data.get("sMkt") or parse_qs(urlparse(signup_url).query).get("mkt", ["zh-CN"])[0]).strip()
        check_url = str(data.get("urlCheckAvailableSigninNames") or "https://signup.live.com/API/CheckAvailableSigninNames")
        create_url = str(data.get("urlCreateAccount") or "https://signup.live.com/API/CreateAccount")
        if not api_canary or not uaid:
            raise PortalProtocolError("signup page 缺少 apiCanary/uaid")
        state = PortalSignupState(
            signup_url=signup_url,
            api_canary=api_canary,
            uaid=uaid,
            client_id=client_id,
            mkt=mkt,
            hpgid=int(data.get("hpgid") or 200225),
            scid=int(data.get("iScenarioId") or 100118),
            uiflvr=int(data.get("iUiFlavor") or 1),
            check_url=check_url,
            create_url=create_url,
            server_data=data,
        )
        logger.info(
            "[portal-protocol] signup state client_id=%s mkt=%s hpgid=%s scid=%s "
            "uiflvr=%s uaid=%s signup_url=%s sDateOrder=%s pref_sms_country=%s "
            "min_birth_year=%s max_birth_year=%s",
            state.client_id or "<empty>",
            state.mkt or "<empty>",
            state.hpgid,
            state.scid,
            state.uiflvr,
            self._short_id(state.uaid),
            self._safe_url_label(state.signup_url),
            state.server_data.get("sDateOrder") or "<empty>",
            state.server_data.get("sPrefSMSCountry") or "<empty>",
            state.server_data.get("iMinBirthYear") or "<empty>",
            state.server_data.get("iMaxBirthYear") or "<empty>",
        )
        self._evaluate_experiments(state)
        self._touch_fingerprint(state)
        return state

    def _api_headers(self, state: PortalSignupState) -> dict[str, str]:
        request_id = str(state.uaid or "")
        return {
            "Accept": "application/json",
            "Accept-Language": self.accept_language,
            "Content-Type": "application/json; charset=utf-8",
            "Origin": "https://signup.live.com",
            "Referer": "https://signup.live.com/",
            "User-Agent": self.user_agent,
            "canary": state.api_canary,
            "client-request-id": request_id,
            "correlationId": request_id,
            "hpgid": str(state.hpgid),
            "hpgact": "0",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
        }

    def _evaluate_experiments(self, state: PortalSignupState) -> None:
        url = str(state.server_data.get("urlClientExperiment") or "https://signup.live.com/API/EvaluateExperimentAssignments")
        body = {
            "clientExperiments": [
                {
                    "parallax": "enablesisufeedback",
                    "control": "enablesisufeedback_control",
                    "treatments": ["enablesisufeedback_treatment"],
                },
                {
                    "parallax": "addprivatebrowsingtexttofabricfooter",
                    "control": "addprivatebrowsingtexttofabricfooter_control",
                    "treatments": ["addprivatebrowsingtexttofabricfooter_treatment"],
                },
            ]
        }
        try:
            resp = self.session.post(url, json=body, headers=self._api_headers(state), timeout=self.timeout)
            self._raise_for_status(resp, "EvaluateExperimentAssignments")
        except Exception as e:
            logger.debug("[portal-protocol] experiment assignment skipped: %s", e)

    def _fingerprint_clear_url(self, html_text: str, fingerprint_url: str) -> str:
        local_target = self._js_string(html_text, "localTarget") or "https://fpt.live.com/"
        txn_id = self._js_string(html_text, "txnId")
        cid = self._js_string(html_text, "cid")
        ticks = self._js_string(html_text, "ticks")
        rid = self._js_string(html_text, "rid")
        txn_key = self._js_string(html_text, "txnKey") or "session_id"
        rid_key = self._js_string(html_text, "ridKey") or "id"
        common_query = self._js_string(html_text, "commonquery") or "&PageId=SU"
        if not txn_id or not cid:
            return ""

        app_version = self.user_agent.removeprefix("Mozilla/")
        plugin_info = (
            "plugin_flash=false&plugin_windows_media_player=false&plugin_adobe_acrobat=false&"
            "plugin_silverlight=false&plugin_quicktime=false&plugin_shockwave=false&"
            "plugin_realplayer=false&plugin_vlc_player=false&plugin_devalvr=false&"
            "plugin_svg_viewer=false&plugin_java=false"
        )
        esi_pairs = [
            ("bua", self.user_agent),
            ("os", "MacIntel"),
            ("lproc", "8"),
            ("ol", "true"),
            ("prosub", "20030107"),
            ("eval", "37"),
            ("appv", app_version),
            ("ls", "true"),
            ("mtp", "0"),
            ("nc", "39"),
            ("pr", "2"),
            ("sr", "3840x2160"),
            ("scd", "24"),
            ("asr", "3840x1968"),
            ("tz", "480"),
            ("dst", "0"),
            ("tzo", "480"),
            ("bl", "zh-CN"),
            ("mth", "27f51d3149e6bf209b66bd387b0af3c4"),
            ("mtn", "2"),
            ("pn", "5"),
            ("ph", "f3ac22ac59c6dcb874109d093c5255e8"),
            ("p", plugin_info),
            ("fh", "07d7339f27cd6608358c55b7fda0f9ec"),
            ("fn", "70"),
            ("lh", fingerprint_url[:255]),
            ("dr", "https://signup.live.com/"),
            ("w", ticks),
            (rid_key, rid),
            ("a", ""),
            ("c", "bdef6bc2985d5a701a6bf7d693ef085b"),
        ]
        esi = base64.b64encode(urlencode(esi_pairs).encode("utf-8")).decode("ascii")
        eci = base64.b64encode(json.dumps({
            "uvdr": "Apple Inc.",
            "urdr": "Apple GPU",
            "vdr": "WebKit",
            "rdr": "WebKit WebGL",
            "iduh": "457739c9dd9799ea64bab73f2a27f40d",
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

    def _touch_fingerprint(self, state: PortalSignupState) -> None:
        captcha_info = state.server_data.get("oCaptchaInfo") if isinstance(state.server_data, dict) else {}
        fingerprint_url = ""
        if isinstance(captcha_info, dict):
            fingerprint_url = str(captcha_info.get("urlDfp") or "").strip()
        if not fingerprint_url:
            fingerprint_url = "https://fpt.live.com/"

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": self.accept_language,
            "Referer": "https://signup.live.com/",
            "User-Agent": self.user_agent,
            "Sec-Fetch-Site": "same-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "iframe",
        }
        try:
            resp = self.session.get(fingerprint_url, headers=headers, timeout=min(self.timeout, 10), allow_redirects=True)
            self._raise_for_status(resp, "fingerprint dfp")
            clear_url = self._fingerprint_clear_url(getattr(resp, "text", "") or "", fingerprint_url)
            clear_status = ""
            if clear_url:
                clear_resp = self.session.get(
                    clear_url,
                    headers={
                        "Accept": "*/*",
                        "Accept-Language": self.accept_language,
                        "Referer": "https://fpt.live.com/",
                        "User-Agent": self.user_agent,
                        "Sec-Fetch-Site": "same-origin",
                        "Sec-Fetch-Mode": "cors",
                        "Sec-Fetch-Dest": "empty",
                    },
                    timeout=min(self.timeout, 10),
                    allow_redirects=True,
                )
                self._raise_for_status(clear_resp, "fingerprint clear")
                clear_status = str(getattr(clear_resp, "status_code", "") or "")
            cookie_names = self._cookie_names()
            logger.info(
                "[portal-protocol] fingerprint warmed dfp_status=%s clear_status=%s has_fptctx2=%s has_muid=%s "
                "has_pxde=%s has_px3=%s has_pxvid=%s",
                getattr(resp, "status_code", "") or "",
                clear_status or "<skipped>",
                "fptctx2" in cookie_names,
                "MUID" in cookie_names,
                "_pxde" in cookie_names,
                "_px3" in cookie_names,
                "_pxvid" in cookie_names,
            )
        except Exception as e:
            logger.info("[portal-protocol] fingerprint probe skipped: %s", e)

    def _check_name(self, state: PortalSignupState, email: str) -> tuple[bool, PortalSignupState]:
        body = {
            "includeSuggestions": True,
            "signInName": email,
            "uiflvr": state.uiflvr,
            "scid": state.scid,
            "uaid": state.uaid,
            "hpgid": state.hpgid,
        }
        logger.info(
            "[portal-protocol] check name request email=%s hpgid=%s scid=%s uiflvr=%s uaid=%s",
            email,
            state.hpgid,
            state.scid,
            state.uiflvr,
            self._short_id(state.uaid),
        )
        resp = self.session.post(
            _with_query(state.check_url, state.signup_url),
            json=body,
            headers=self._api_headers(state),
            timeout=self.timeout,
        )
        self._raise_for_status(resp, "CheckAvailableSigninNames")
        data = _json_or_error(resp, "CheckAvailableSigninNames")
        self._raise_if_challenge(resp, data, stage="CheckAvailableSigninNames", email=email)
        canary_updated = bool(data.get("apiCanary"))
        if data.get("apiCanary"):
            state.api_canary = str(data["apiCanary"])
        logger.info(
            "[portal-protocol] check name result email=%s available=%s type=%s "
            "nopa_allowed=%s canary_updated=%s response_keys=%s",
            email,
            bool(data.get("isAvailable")),
            data.get("type") or "<empty>",
            data.get("nopaAllowed"),
            canary_updated,
            ",".join(sorted(str(k) for k in data.keys())),
        )
        return bool(data.get("isAvailable")), state

    @staticmethod
    def _format_birth_date(birth: date, order: str) -> str:
        parts = {
            "Y": f"{birth.year:04d}",
            "M": f"{birth.month:02d}",
            "D": f"{birth.day:02d}",
        }
        return ":".join(parts[ch] for ch in order)

    def _birth_date_candidates(self, state: PortalSignupState, country: str) -> list[tuple[str, str, str, int]]:
        min_age = int(_cfg_value(self.cfg, "birth_age_min", 20) or 20)
        max_age = int(_cfg_value(self.cfg, "birth_age_max", 40) or 40)
        if max_age < min_age:
            min_age, max_age = max_age, min_age
        min_days = int(min_age * 365.2425)
        max_days = int(max_age * 365.2425)
        age_days = random.randint(min_days, max_days)
        birth = date.today() - timedelta(days=age_days)
        order, source = self._date_order(state, country)
        candidates: list[tuple[str, str, str, int]] = []
        seen_dates: set[str] = set()
        for idx, candidate_order in enumerate([order, "DMY", "MDY", "YMD"]):
            candidate_order = self._normalise_date_order(candidate_order)
            if not candidate_order:
                continue
            birth_date = self._format_birth_date(birth, candidate_order)
            if birth_date in seen_dates:
                continue
            seen_dates.add(birth_date)
            candidate_source = source if idx == 0 else f"fallback:{candidate_order}"
            candidates.append((birth_date, candidate_order, candidate_source, age_days))
        return candidates

    def _birth_date(self, state: PortalSignupState, country: str) -> tuple[str, str, str, int]:
        return self._birth_date_candidates(state, country)[0]

    def _create_account(self, state: PortalSignupState, email: str, password: str) -> dict:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        country = self._effective_country(state)
        first_name = str(_cfg_value(self.cfg, "first_name", "") or "")
        last_name = str(_cfg_value(self.cfg, "last_name", "") or "")
        birth_candidates = self._birth_date_candidates(state, country)
        for birth_attempt, (birth_date, birth_order, birth_order_source, birth_age_days) in enumerate(birth_candidates, start=1):
            body = {
                "BirthDate": birth_date,
                "CheckAvailStateMap": [f"{email}:false"],
                "Country": country,
                "EvictionWarningShown": [],
                "FirstName": first_name,
                "IsRDM": False,
                "IsOptOutEmailDefault": True,
                "IsOptOutEmailShown": 1,
                "IsOptOutEmail": True,
                "IsUserConsentedToChinaPIPL": True,
                "LastName": last_name,
                "LW": 1,
                "MemberName": email,
                "RequestTimeStamp": now,
                "ReturnUrl": str(state.server_data.get("sReturnUrl") or ""),
                "SignupReturnUrl": str(state.server_data.get("sSignupReturnUrl") or parse_qs(urlparse(state.signup_url).query).get("sru", [""])[0]),
                "SuggestedAccountType": "EASI",
                "SiteId": str(state.server_data.get("sSiteId") or ""),
                "VerificationCodeSlt": "",
                "PrivateAccessToken": "",
                "WReply": str(state.server_data.get("sWReply") or ""),
                "MemberNameChangeCount": 1,
                "MemberNameAvailableCount": 1,
                "MemberNameUnavailableCount": 0,
                "Password": password,
                "uiflvr": state.uiflvr,
                "scid": state.scid,
                "uaid": state.uaid,
                "hpgid": state.hpgid,
            }
            safe_keys = [k for k in sorted(body.keys()) if k != "Password"]
            cookie_names = self._cookie_names()
            logger.info(
                "[portal-protocol] create account request email=%s country=%s birth_date=%s "
                "birth_order=%s order_source=%s birth_attempt=%s/%s age_days=%s sDateOrder=%s first_empty=%s "
                "last_empty=%s signup_return_url=%s return_url=%s site_id_empty=%s "
                "has_fptctx2=%s has_muid=%s has_pxde=%s has_px3=%s has_pxvid=%s payload_keys=%s",
                email,
                country,
                birth_date,
                birth_order,
                birth_order_source,
                birth_attempt,
                len(birth_candidates),
                birth_age_days,
                state.server_data.get("sDateOrder") or "<empty>",
                first_name == "",
                last_name == "",
                bool(body.get("SignupReturnUrl")),
                bool(body.get("ReturnUrl")),
                body.get("SiteId") == "",
                "fptctx2" in cookie_names,
                "MUID" in cookie_names,
                "_pxde" in cookie_names,
                "_px3" in cookie_names,
                "_pxvid" in cookie_names,
                ",".join(safe_keys),
            )
            resp = self.session.post(
                _with_query(state.create_url, state.signup_url),
                json=body,
                headers=self._api_headers(state),
                timeout=self.timeout,
            )
            self._raise_for_status(resp, "CreateAccount")
            data = _json_or_error(resp, "CreateAccount")
            self._raise_if_challenge(resp, data, stage="CreateAccount", email=email, password=password)
            if data.get("apiCanary"):
                state.api_canary = str(data["apiCanary"])
            if data.get("error"):
                err = data.get("error") if isinstance(data.get("error"), dict) else {}
                telemetry = ""
                if isinstance(err, dict):
                    telemetry = str(err.get("telemetryContext") or "")
                error_field = err.get("field") if isinstance(err, dict) else "<non-dict-error>"
                logger.error(
                    "[portal-protocol] create account error email=%s country=%s birth_date=%s "
                    "birth_order=%s order_source=%s birth_attempt=%s/%s age_days=%s sDateOrder=%s response_status=%s "
                    "error_code=%s error_field=%s error_data=%s top_keys=%s telemetry_len=%s",
                    email,
                    country,
                    birth_date,
                    birth_order,
                    birth_order_source,
                    birth_attempt,
                    len(birth_candidates),
                    birth_age_days,
                    state.server_data.get("sDateOrder") or "<empty>",
                    getattr(resp, "status_code", ""),
                    err.get("code") if isinstance(err, dict) else "<non-dict-error>",
                    error_field,
                    err.get("data") if isinstance(err, dict) else "",
                    ",".join(sorted(str(k) for k in data.keys())),
                    len(telemetry),
                )
                if str(error_field).lower() == "birthdate" and birth_attempt < len(birth_candidates):
                    next_order = birth_candidates[birth_attempt][1]
                    logger.warning(
                        "[portal-protocol] retry create account after birthdate error email=%s next_birth_order=%s next_attempt=%s/%s",
                        email,
                        next_order,
                        birth_attempt + 1,
                        len(birth_candidates),
                    )
                    continue
                raise PortalProtocolError(f"CreateAccount error={data.get('error')} code={data.get('errorCode')}")
            logger.info(
                "[portal-protocol] create account response email=%s has_redirect=%s response_keys=%s",
                email,
                bool(data.get("redirectUrl")),
                ",".join(sorted(str(k) for k in data.keys())),
            )
            return data
        raise PortalProtocolError("CreateAccount 未返回可用响应")

    def _follow_post_create_redirect(self, redirect_url: str) -> str:
        logger.info("[portal-protocol] redirect start url=%s", self._safe_url_label(redirect_url))
        resp = self.session.post(redirect_url, data={}, timeout=self.timeout, allow_redirects=True)
        self._raise_for_status(resp, "post-create redirect")
        self._raise_if_challenge(resp, stage="post-create redirect")
        for _ in range(8):
            current_url = getattr(resp, "url", "") or redirect_url
            logger.info(
                "[portal-protocol] redirect step status=%s url=%s has_oauth_code=%s",
                getattr(resp, "status_code", ""),
                self._safe_url_label(current_url),
                bool(parse_qs(urlparse(current_url).query).get("code")),
            )
            if parse_qs(urlparse(current_url).query).get("code"):
                return current_url
            text = getattr(resp, "text", "") or ""
            form = _first_form(text, current_url)
            if form:
                method, action, fields = form
                logger.info(
                    "[portal-protocol] redirect form method=%s action=%s fields=%s",
                    method,
                    self._safe_url_label(action),
                    ",".join(sorted(fields.keys())),
                )
                if method == "POST":
                    resp = self.session.post(action, data=fields, timeout=self.timeout, allow_redirects=True)
                else:
                    resp = self.session.get(action, params=fields, timeout=self.timeout, allow_redirects=True)
                self._raise_for_status(resp, "html form redirect")
                self._raise_if_challenge(resp, stage="html form redirect")
                continue
            next_url = _redirect_from_html(text, current_url)
            if next_url:
                logger.info("[portal-protocol] redirect html url=%s", self._safe_url_label(next_url))
                resp = self.session.get(next_url, timeout=self.timeout, allow_redirects=True)
                self._raise_for_status(resp, "html redirect")
                self._raise_if_challenge(resp, stage="html redirect")
                continue
            return current_url
        return getattr(resp, "url", "") or redirect_url

    def _raise_if_challenge(
        self,
        resp: Any = None,
        data: Any = None,
        *,
        stage: str = "",
        email: str = "",
        password: str = "",
        username_seq: int = 0,
    ) -> None:
        reason, marker = detect_outlook_challenge(resp, data)
        if not reason:
            return
        weak_initial_markers = {"hsprotect", "pxvid", "px3", "pxde"}
        if stage == "authorize/signup" and reason == "perimeterx" and marker in weak_initial_markers:
            logger.info(
                "[portal-protocol] weak challenge marker ignored stage=%s reason=%s marker=%s url=%s",
                stage,
                reason,
                marker,
                self._safe_url_label(getattr(resp, "url", "") or "") if resp is not None else "",
            )
            return
        logger.warning(
            "[portal-protocol] challenge detected stage=%s reason=%s marker=%s status=%s url=%s email=%s",
            stage or "<unknown>",
            reason,
            marker or "<none>",
            getattr(resp, "status_code", "") if resp is not None else "",
            self._safe_url_label(getattr(resp, "url", "") or "") if resp is not None else "",
            email or "<none>",
        )
        raise PortalChallengeError(
            reason,
            stage=stage,
            email=email,
            password=password,
            username_seq=username_seq,
            marker=marker,
        )

    @staticmethod
    def _raise_for_status(resp, label: str) -> None:
        status = int(getattr(resp, "status_code", 0) or 0)
        if status >= 400 or status <= 0:
            text = (getattr(resp, "text", "") or "")[:200]
            raise PortalProtocolError(f"{label} HTTP {status}: {text}")


def portal_protocol_register(cfg: Config, session=None) -> dict:
    fallback_enabled = str(os.environ.get("PORTAL_BROWSER_FALLBACK", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    try:
        return PortalProtocol(cfg, session=session).run().to_dict()
    except PortalChallengeError as e:
        if not fallback_enabled:
            raise
        logger.info(
            "[portal-protocol] falling back to Camoufox Outlook browser flow reason=%s stage=%s email=%s",
            e.reason,
            e.stage or "<unknown>",
            e.email or "<auto>",
        )
        from outlook_browser_register import outlook_browser_register

        result = outlook_browser_register(
            cfg,
            email=e.email,
            password=e.password,
            username_seq=e.username_seq,
            challenge_reason=e.reason,
        )
        if (
            bool(_cfg_value(cfg, "mail_oauth_enabled", True))
            and not result.get("mail_refresh_token")
            and result.get("register_method") != "portal_browser"
        ):
            from outlook_oauth import authorize_outlook_mailbox

            oauth_session = create_http_session(getattr(cfg, "proxy", None))
            mail_oauth = authorize_outlook_mailbox(
                cfg,
                oauth_session,
                email=str(result.get("email") or ""),
                password=str(result.get("password") or ""),
            )
            result.update(mail_oauth.to_mail_fields())
            result["mail_oauth_client_id"] = mail_oauth.client_id
        return result
