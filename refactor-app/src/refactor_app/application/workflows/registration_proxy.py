from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

try:
    from curl_cffi import requests as curl_requests
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs.

    class _MissingCurlRequests:
        def Session(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("curl_cffi is required for Cliproxy health checks")

    curl_requests = _MissingCurlRequests()

from refactor_app.application.workflows.trojan_proxy_pool import (
    TrojanProxyPoolError,
    get_trojan_proxy_pool_manager,
)
from refactor_app.config.browser_fingerprint import BROWSER_IMPERSONATE

CLIPROXY_PROVIDER = "cliproxy"
TROJAN_POOL_PROVIDER = "local_trojan_pool"
DEFAULT_CLIPROXY_PROBE_URL = "https://chatgpt.com/api/auth/csrf"
DEFAULT_CLIPROXY_EGRESS_TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
_SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https", "socks5", "socks5h"})
_SUPPORTED_GATEWAY_MODES = frozenset({"auto", "fixed"})
_SUPPORTED_CLIPROXY_MODES = frozenset({"remote", "trojan_pool"})
_SG_GATEWAY_COUNTRIES = frozenset(
    {
        "AF",
        "AM",
        "AU",
        "AZ",
        "BD",
        "BH",
        "BN",
        "BT",
        "CN",
        "FJ",
        "FM",
        "GE",
        "HK",
        "ID",
        "IL",
        "IN",
        "IQ",
        "IR",
        "JO",
        "JP",
        "KG",
        "KH",
        "KI",
        "KP",
        "KR",
        "KW",
        "KZ",
        "LA",
        "LB",
        "LK",
        "MH",
        "MM",
        "MN",
        "MO",
        "MV",
        "MY",
        "NP",
        "NR",
        "NZ",
        "OM",
        "PG",
        "PH",
        "PK",
        "PW",
        "PS",
        "QA",
        "SA",
        "SB",
        "SG",
        "SY",
        "TH",
        "TJ",
        "TL",
        "TM",
        "TO",
        "TV",
        "TW",
        "UZ",
        "VN",
        "VU",
        "WS",
        "YE",
    }
)
ProxyProbe = Callable[[str], bool]


class CliproxyProxyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CliproxyProxyConfig:
    """Credentials and routing parameters for Cliproxy's account/password mode."""

    host: str
    port: int
    username: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    scheme: str = "http"
    state: str = ""
    jp_state: str = "Tokyo"
    session_duration_minutes: int = 15
    probe_url: str = DEFAULT_CLIPROXY_PROBE_URL
    probe_timeout_s: float = 10.0
    probe_require_csrf_token: bool = True
    max_sid_attempts: int = 4
    gateway_mode: str = "auto"
    us_host: str = "us.arxlabs.io"
    sg_host: str = "sg.arxlabs.io"
    egress_trace_url: str = DEFAULT_CLIPROXY_EGRESS_TRACE_URL
    egress_trace_timeout_s: float = 5.0
    mode: str = "remote"
    trojan_pool_file: str = field(default="", repr=False)
    trojan_http_start_port: int = 18081
    trojan_work_dir: str = "runtime/proxy/trojan-bridge"
    trojan_executable: str = "sing-box"
    trojan_start_timeout_s: float = 8.0

    @classmethod
    def from_settings(cls, settings: object) -> CliproxyProxyConfig:
        return cls(
            host=str(getattr(settings, "cliproxy_host", "") or ""),
            port=int(getattr(settings, "cliproxy_port", 0) or 0),
            username=str(getattr(settings, "cliproxy_username", "") or ""),
            password=str(getattr(settings, "cliproxy_password", "") or ""),
            scheme=str(getattr(settings, "cliproxy_scheme", "http") or "http"),
            state=str(getattr(settings, "cliproxy_state", "") or ""),
            jp_state=str(getattr(settings, "cliproxy_jp_state", "Tokyo") or ""),
            session_duration_minutes=int(
                getattr(settings, "cliproxy_session_duration_minutes", 15) or 15
            ),
            probe_url=str(
                getattr(settings, "cliproxy_probe_url", DEFAULT_CLIPROXY_PROBE_URL)
                or DEFAULT_CLIPROXY_PROBE_URL
            ),
            probe_timeout_s=float(getattr(settings, "cliproxy_probe_timeout_s", 10.0) or 10.0),
            probe_require_csrf_token=bool(
                getattr(settings, "cliproxy_probe_require_csrf_token", True)
            ),
            max_sid_attempts=int(getattr(settings, "cliproxy_max_sid_attempts", 4) or 4),
            gateway_mode=str(getattr(settings, "cliproxy_gateway_mode", "auto") or "auto"),
            us_host=str(getattr(settings, "cliproxy_us_host", "us.arxlabs.io") or ""),
            sg_host=str(getattr(settings, "cliproxy_sg_host", "sg.arxlabs.io") or ""),
            egress_trace_url=str(
                getattr(
                    settings,
                    "cliproxy_egress_trace_url",
                    DEFAULT_CLIPROXY_EGRESS_TRACE_URL,
                )
                or DEFAULT_CLIPROXY_EGRESS_TRACE_URL
            ),
            egress_trace_timeout_s=float(
                getattr(settings, "cliproxy_egress_trace_timeout_s", 5.0) or 5.0
            ),
            mode=str(getattr(settings, "cliproxy_mode", "remote") or "remote"),
            trojan_pool_file=str(
                getattr(settings, "cliproxy_trojan_pool_file", "") or ""
            ),
            trojan_http_start_port=int(
                getattr(settings, "cliproxy_trojan_http_start_port", 18081) or 18081
            ),
            trojan_work_dir=str(
                getattr(
                    settings,
                    "cliproxy_trojan_work_dir",
                    "runtime/proxy/trojan-bridge",
                )
                or "runtime/proxy/trojan-bridge"
            ),
            trojan_executable=str(
                getattr(settings, "cliproxy_trojan_executable", "sing-box") or "sing-box"
            ),
            trojan_start_timeout_s=float(
                getattr(settings, "cliproxy_trojan_start_timeout_s", 8.0) or 8.0
            ),
        )

    def validate(self) -> None:
        mode = self.mode.strip().lower()
        if mode not in _SUPPORTED_CLIPROXY_MODES:
            raise CliproxyProxyError(f"Cliproxy mode is unsupported: {mode}")
        if not self.probe_url.strip():
            raise CliproxyProxyError("Cliproxy probe URL is missing")
        if float(self.probe_timeout_s) <= 0:
            raise CliproxyProxyError("Cliproxy probe timeout must be positive")
        if mode == "trojan_pool":
            if not self.trojan_pool_file.strip():
                raise CliproxyProxyError("Cliproxy Trojan pool file is missing")
            if not 1 <= int(self.trojan_http_start_port) <= 65535:
                raise CliproxyProxyError("Cliproxy Trojan local port is invalid")
            if not self.trojan_work_dir.strip():
                raise CliproxyProxyError("Cliproxy Trojan work directory is missing")
            if not self.trojan_executable.strip():
                raise CliproxyProxyError("Cliproxy Trojan executable is missing")
            if float(self.trojan_start_timeout_s) <= 0:
                raise CliproxyProxyError("Cliproxy Trojan start timeout must be positive")
            if not 1 <= int(self.max_sid_attempts) <= 20:
                raise CliproxyProxyError("Cliproxy attempt count must be between 1 and 20")
            return

        host = self.host.strip()
        scheme = self.scheme.strip().lower()
        gateway_mode = self.gateway_mode.strip().lower()
        if not host or any(char.isspace() for char in host) or "://" in host:
            raise CliproxyProxyError("Cliproxy host is invalid")
        if gateway_mode not in _SUPPORTED_GATEWAY_MODES:
            raise CliproxyProxyError(f"Cliproxy gateway mode is unsupported: {gateway_mode}")
        if gateway_mode == "auto":
            for gateway_name, gateway_host in (("US", self.us_host), ("SG", self.sg_host)):
                normalized_gateway_host = gateway_host.strip()
                if (
                    not normalized_gateway_host
                    or any(char.isspace() for char in normalized_gateway_host)
                    or "://" in normalized_gateway_host
                ):
                    raise CliproxyProxyError(f"Cliproxy {gateway_name} host is invalid")
            if not self.egress_trace_url.strip():
                raise CliproxyProxyError("Cliproxy egress trace URL is missing")
            if float(self.egress_trace_timeout_s) <= 0:
                raise CliproxyProxyError("Cliproxy egress trace timeout must be positive")
        if not 1 <= int(self.port) <= 65535:
            raise CliproxyProxyError("Cliproxy port must be between 1 and 65535")
        if scheme not in _SUPPORTED_PROXY_SCHEMES:
            raise CliproxyProxyError(f"Cliproxy proxy scheme is unsupported: {scheme}")
        if not self.username.strip():
            raise CliproxyProxyError("Cliproxy username is missing")
        if not self.password:
            raise CliproxyProxyError("Cliproxy password is missing")
        if not 1 <= int(self.session_duration_minutes) <= 120:
            raise CliproxyProxyError(
                "Cliproxy session duration must be between 1 and 120 minutes"
            )
        if not 1 <= int(self.max_sid_attempts) <= 20:
            raise CliproxyProxyError("Cliproxy SID attempt count must be between 1 and 20")


@dataclass(frozen=True)
class CliproxyProxy:
    proxy_url: str = field(repr=False)
    country_code: str
    sid: str = field(default="", repr=False)
    sid_source: str = "email_sha256"
    probe_attempts: int = 1
    provider: str = CLIPROXY_PROVIDER
    proxy_mode: str = "cliproxy_sticky"
    proxy_source: str = "target_email_hash"


def resolve_cliproxy_proxy(
    *,
    email: str,
    country_code: str = "US",
    config: CliproxyProxyConfig | None = None,
    probe: ProxyProbe | None = None,
) -> CliproxyProxy:
    """Resolve and health-check a stable Cliproxy SID for an email."""

    if config is None:
        from refactor_app.config.settings import get_settings

        config = CliproxyProxyConfig.from_settings(get_settings())
    config.validate()
    normalized_email = normalize_registration_proxy_email(email)
    normalized_country = normalize_registration_proxy_country(country_code)
    if config.mode.strip().lower() == "trojan_pool":
        return _resolve_trojan_pool_proxy(
            email=normalized_email,
            country_code=normalized_country,
            config=config,
            probe=probe,
        )
    gateway_host = select_cliproxy_gateway_host(config)
    # Cliproxy keeps a SID pinned to its first resolved exit. Scope the stable
    # hash by country so one account's US browser and JP promo request cannot
    # reuse the same pinned route.
    stable_sid = cliproxy_stable_sid(normalized_email, normalized_country)
    attempt_limit = int(config.max_sid_attempts)
    candidate_sids = [stable_sid]
    while len(candidate_sids) < attempt_limit:
        candidate = uuid4().hex
        if candidate not in candidate_sids:
            candidate_sids.append(candidate)

    if probe is None:

        def probe_fn(proxy_url: str) -> bool:
            if not probe_cliproxy_proxy(
                proxy_url,
                probe_url=config.probe_url,
                timeout_s=config.probe_timeout_s,
                require_csrf_token=config.probe_require_csrf_token,
            ):
                return False
            return (
                detect_proxy_egress_country(
                    proxy_url,
                    trace_url=config.egress_trace_url,
                    timeout_s=config.egress_trace_timeout_s,
                )
                == normalized_country
            )

    else:
        probe_fn = probe
    failures: list[str] = []
    for attempt_number, sid in enumerate(candidate_sids, start=1):
        sid_source = "email_sha256" if sid == stable_sid else "random_uuid"
        candidate_proxy = build_cliproxy_proxy(
            email=normalized_email,
            country_code=normalized_country,
            sid=sid,
            host=gateway_host,
            port=config.port,
            scheme=config.scheme,
            username=config.username,
            password=config.password,
            state=(
                config.state
                if normalized_country == "US"
                else config.jp_state
                if normalized_country == "JP"
                else ""
            ),
            session_duration_minutes=config.session_duration_minutes,
            sid_source=sid_source,
            probe_attempts=attempt_number,
        )
        try:
            alive = bool(probe_fn(candidate_proxy.proxy_url))
        except Exception as exc:
            alive = False
            failures.append(type(exc).__name__)
        if alive:
            return candidate_proxy
        failures.append("probe_false")

    failure_types = ",".join(dict.fromkeys(failures)) or "probe_false"
    raise CliproxyProxyError(
        f"Cliproxy proxy probe failed after {attempt_limit} attempts: {failure_types}"
    )


def _resolve_trojan_pool_proxy(
    *,
    email: str,
    country_code: str,
    config: CliproxyProxyConfig,
    probe: ProxyProbe | None,
) -> CliproxyProxy:
    try:
        manager = get_trojan_proxy_pool_manager(
            config.trojan_pool_file,
            int(config.trojan_http_start_port),
            config.trojan_work_dir,
            config.trojan_executable,
            float(config.trojan_start_timeout_s),
        )
        manager.ensure_started()
        candidates = manager.candidate_nodes(email=email, country_code=country_code)
    except TrojanProxyPoolError as exc:
        raise CliproxyProxyError(str(exc)) from exc

    probe_fn = probe or (
        lambda proxy_url: probe_cliproxy_proxy(
            proxy_url,
            probe_url=config.probe_url,
            timeout_s=config.probe_timeout_s,
            require_csrf_token=config.probe_require_csrf_token,
        )
    )
    failures: list[str] = []
    attempt_limit = min(len(candidates), int(config.max_sid_attempts))
    stable_sid = cliproxy_stable_sid(email, country_code)
    for attempt_number, node in enumerate(candidates[:attempt_limit], start=1):
        try:
            alive = bool(probe_fn(node.local_http_url))
        except Exception as exc:
            alive = False
            failures.append(type(exc).__name__)
        if alive:
            return CliproxyProxy(
                proxy_url=node.local_http_url,
                country_code=node.country_code,
                sid=stable_sid,
                sid_source=(
                    "email_sha256" if attempt_number == 1 else "email_sha256_failover"
                ),
                probe_attempts=attempt_number,
                provider=TROJAN_POOL_PROVIDER,
                proxy_mode="trojan_pool_sticky",
                proxy_source="target_email_country_hash",
            )
        failures.append("probe_false")
    failure_types = ",".join(dict.fromkeys(failures)) or "probe_false"
    raise CliproxyProxyError(
        f"Trojan pool probe failed for country={country_code} "
        f"after {attempt_limit} attempts: {failure_types}"
    )


def select_cliproxy_gateway_host(config: CliproxyProxyConfig) -> str:
    """Select the nearest Cliproxy ingress from this process's direct egress."""

    if config.gateway_mode.strip().lower() == "fixed":
        return config.host.strip()
    try:
        egress_country = detect_machine_egress_country(
            config.egress_trace_url,
            float(config.egress_trace_timeout_s),
        )
    except Exception:
        return config.host.strip()
    if egress_country in _SG_GATEWAY_COUNTRIES:
        return config.sg_host.strip()
    return config.us_host.strip()


@lru_cache(maxsize=8)
def detect_machine_egress_country(
    trace_url: str = DEFAULT_CLIPROXY_EGRESS_TRACE_URL,
    timeout_s: float = 5.0,
) -> str:
    """Read Cloudflare Trace directly, bypassing system and Cliproxy settings."""

    request = Request(
        str(trace_url or "").strip(),
        headers={"Accept": "text/plain", "User-Agent": "refactor-app-egress-probe/1.0"},
    )
    opener = build_opener(ProxyHandler({}))
    with opener.open(request, timeout=float(timeout_s)) as response:
        status = int(getattr(response, "status", 200) or 200)
        payload = response.read().decode("utf-8", errors="replace")
    if status != 200:
        raise CliproxyProxyError(f"Cliproxy egress trace returned HTTP {status}")
    return _parse_egress_trace_country(payload)


def detect_proxy_egress_country(
    proxy_url: str,
    *,
    trace_url: str = DEFAULT_CLIPROXY_EGRESS_TRACE_URL,
    timeout_s: float = 5.0,
) -> str:
    """Read Cloudflare Trace through the selected Cliproxy exit."""

    normalized_proxy = str(proxy_url or "").strip()
    normalized_trace_url = str(trace_url or "").strip()
    if not normalized_proxy or not normalized_trace_url:
        raise CliproxyProxyError("Cliproxy proxy egress trace configuration is missing")
    try:
        with curl_requests.Session(
            impersonate=BROWSER_IMPERSONATE,
            proxies=_curl_proxies(normalized_proxy),
        ) as client:
            try:
                client.trust_env = False
            except Exception:
                pass
            response = client.get(
                normalized_trace_url,
                headers={
                    "Accept": "text/plain",
                    "User-Agent": "refactor-app-proxy-egress-probe/1.0",
                },
                timeout=float(timeout_s),
            )
    except Exception as exc:
        raise CliproxyProxyError(
            f"Cliproxy proxy egress trace request failed: {type(exc).__name__}"
        ) from exc
    status = int(getattr(response, "status_code", 0) or 0)
    if status != 200:
        raise CliproxyProxyError(f"Cliproxy proxy egress trace returned HTTP {status}")
    return _parse_egress_trace_country(str(getattr(response, "text", "") or ""))


def _parse_egress_trace_country(payload: str) -> str:
    trace = dict(
        line.split("=", 1)
        for line in str(payload or "").splitlines()
        if "=" in line
    )
    country_code = str(trace.get("loc") or "").strip().upper()
    if (
        not trace.get("ip")
        or not _COUNTRY_CODE_PATTERN.fullmatch(country_code)
        or country_code == "XX"
    ):
        raise CliproxyProxyError("Cliproxy egress trace did not return a usable IP location")
    return country_code


def build_cliproxy_proxy(
    *,
    email: str,
    country_code: str,
    sid: str,
    host: str,
    port: int,
    scheme: str,
    username: str,
    password: str,
    state: str = "",
    session_duration_minutes: int = 15,
    sid_source: str = "email_sha256",
    probe_attempts: int = 1,
) -> CliproxyProxy:
    normalize_registration_proxy_email(email)
    normalized_country = normalize_registration_proxy_country(country_code)
    normalized_sid = str(sid or "").strip()
    if not normalized_sid or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", normalized_sid):
        raise CliproxyProxyError("Cliproxy SID is invalid")
    normalized_host = str(host or "").strip()
    normalized_scheme = str(scheme or "http").strip().lower()
    normalized_port = int(port)
    if not normalized_host or any(char.isspace() for char in normalized_host):
        raise CliproxyProxyError("Cliproxy host is invalid")
    if not 1 <= normalized_port <= 65535:
        raise CliproxyProxyError("Cliproxy port must be between 1 and 65535")
    if normalized_scheme not in _SUPPORTED_PROXY_SCHEMES:
        raise CliproxyProxyError(f"Cliproxy proxy scheme is unsupported: {normalized_scheme}")
    if not str(username or "").strip():
        raise CliproxyProxyError("Cliproxy username is missing")
    if not password:
        raise CliproxyProxyError("Cliproxy password is missing")

    cliproxy_username = cliproxy_username_for_email(
        base_username=username,
        country_code=normalized_country,
        sid=normalized_sid,
        state=state,
        session_duration_minutes=session_duration_minutes,
    )
    proxy_url = (
        f"{normalized_scheme}://{quote(cliproxy_username, safe='')}:{quote(password, safe='')}"
        f"@{normalized_host}:{normalized_port}"
    )
    return CliproxyProxy(
        proxy_url=proxy_url,
        country_code=normalized_country,
        sid=normalized_sid,
        sid_source=str(sid_source or "email_sha256"),
        probe_attempts=max(1, int(probe_attempts)),
    )


def cliproxy_stable_sid(email: str, country_code: str = "") -> str:
    normalized_email = normalize_registration_proxy_email(email)
    normalized_country = (
        normalize_registration_proxy_country(country_code)
        if str(country_code or "").strip()
        else ""
    )
    hash_input = (
        f"{normalized_email}|{normalized_country}" if normalized_country else normalized_email
    )
    return sha256(hash_input.encode("utf-8")).hexdigest()


def cliproxy_username_for_email(
    *,
    base_username: str,
    country_code: str,
    sid: str,
    state: str = "",
    session_duration_minutes: int = 15,
) -> str:
    base = str(base_username or "").strip()
    if not base:
        raise CliproxyProxyError("Cliproxy username is missing")
    country = normalize_registration_proxy_country(country_code)
    normalized_sid = str(sid or "").strip()
    if not normalized_sid:
        raise CliproxyProxyError("Cliproxy SID is missing")
    duration = int(session_duration_minutes)
    if not 1 <= duration <= 120:
        raise CliproxyProxyError(
            "Cliproxy session duration must be between 1 and 120 minutes"
        )
    parts = [base, "region", country]
    normalized_state = re.sub(r"\s+", "_", str(state or "").strip())
    if normalized_state:
        parts.extend(("st", normalized_state))
    parts.extend(("sid", normalized_sid, "t", str(duration)))
    return "-".join(parts)


def normalize_registration_proxy_email(email: str) -> str:
    normalized = str(email or "").strip().casefold()
    if not normalized or "@" not in normalized:
        raise CliproxyProxyError("registration target email is required for proxy hashing")
    return normalized


def normalize_registration_proxy_country(country_code: str) -> str:
    normalized = str(country_code or "US").strip().upper()
    if not _COUNTRY_CODE_PATTERN.fullmatch(normalized):
        raise CliproxyProxyError("registration proxy country must be a two-letter country code")
    return normalized


def probe_cliproxy_proxy(
    proxy_url: str,
    *,
    probe_url: str = DEFAULT_CLIPROXY_PROBE_URL,
    timeout_s: float = 10.0,
    require_csrf_token: bool = True,
) -> bool:
    """Verify authentication, connectivity, and the target ChatGPT edge."""

    if not str(proxy_url or "").strip() or not str(probe_url or "").strip():
        return False
    try:
        headers = {
            "accept": "application/json",
            "accept-language": "zh-CN,zh;q=0.9",
            "referer": "https://chatgpt.com/",
        }
        with curl_requests.Session(
            impersonate=BROWSER_IMPERSONATE,
            proxies=_curl_proxies(proxy_url),
        ) as client:
            try:
                client.trust_env = False
            except Exception:
                pass
            response = client.get(
                str(probe_url).strip(),
                headers=headers,
                timeout=float(timeout_s),
            )
        if int(getattr(response, "status_code", 0) or 0) != 200:
            return False
        if not require_csrf_token:
            return True
        payload = response.json()
        return isinstance(payload, dict) and bool(str(payload.get("csrfToken") or "").strip())
    except Exception:
        return False


def _curl_proxies(proxy_url: str) -> dict[str, str]:
    value = str(proxy_url or "").strip()
    if value.startswith("socks5://"):
        value = "socks5h://" + value[len("socks5://") :]
    return {"http": value, "https": value}
