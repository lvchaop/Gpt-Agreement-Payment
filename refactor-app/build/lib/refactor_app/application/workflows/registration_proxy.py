from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from urllib.parse import quote
from uuid import uuid4

try:
    from curl_cffi import requests as curl_requests
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal test envs.

    class _MissingCurlRequests:
        def Session(self, *args: object, **kwargs: object) -> object:
            raise RuntimeError("curl_cffi is required for Cliproxy health checks")

    curl_requests = _MissingCurlRequests()

from refactor_app.config.browser_fingerprint import BROWSER_IMPERSONATE

CLIPROXY_PROVIDER = "cliproxy"
DEFAULT_CLIPROXY_PROBE_URL = "https://chatgpt.com/api/auth/csrf"
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")
_SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https", "socks5", "socks5h"})
ProxyProbe = Callable[[str], bool]


class CliproxyProxyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CliproxyProxyConfig:
    """Credentials and routing parameters for Cliproxy's account/password mode."""

    host: str
    port: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    scheme: str = "http"
    state: str = ""
    session_duration_minutes: int = 15
    probe_url: str = DEFAULT_CLIPROXY_PROBE_URL
    probe_timeout_s: float = 10.0
    probe_require_csrf_token: bool = True
    max_sid_attempts: int = 4

    @classmethod
    def from_settings(cls, settings: object) -> CliproxyProxyConfig:
        return cls(
            host=str(getattr(settings, "cliproxy_host", "") or ""),
            port=int(getattr(settings, "cliproxy_port", 0) or 0),
            username=str(getattr(settings, "cliproxy_username", "") or ""),
            password=str(getattr(settings, "cliproxy_password", "") or ""),
            scheme=str(getattr(settings, "cliproxy_scheme", "http") or "http"),
            state=str(getattr(settings, "cliproxy_state", "") or ""),
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
        )

    def validate(self) -> None:
        host = self.host.strip()
        scheme = self.scheme.strip().lower()
        if not host or any(char.isspace() for char in host) or "://" in host:
            raise CliproxyProxyError("Cliproxy host is invalid")
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
        if not self.probe_url.strip():
            raise CliproxyProxyError("Cliproxy probe URL is missing")
        if float(self.probe_timeout_s) <= 0:
            raise CliproxyProxyError("Cliproxy probe timeout must be positive")
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
    stable_sid = cliproxy_stable_sid(normalized_email)
    attempt_limit = int(config.max_sid_attempts)
    candidate_sids = [stable_sid]
    while len(candidate_sids) < attempt_limit:
        candidate = uuid4().hex
        if candidate not in candidate_sids:
            candidate_sids.append(candidate)

    probe_fn = probe or (
        lambda proxy_url: probe_cliproxy_proxy(
            proxy_url,
            probe_url=config.probe_url,
            timeout_s=config.probe_timeout_s,
            require_csrf_token=config.probe_require_csrf_token,
        )
    )
    failures: list[str] = []
    for attempt_number, sid in enumerate(candidate_sids, start=1):
        sid_source = "email_sha256" if sid == stable_sid else "random_uuid"
        candidate_proxy = build_cliproxy_proxy(
            email=normalized_email,
            country_code=normalized_country,
            sid=sid,
            host=config.host,
            port=config.port,
            scheme=config.scheme,
            username=config.username,
            password=config.password,
            state=config.state,
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


def cliproxy_stable_sid(email: str) -> str:
    normalized_email = normalize_registration_proxy_email(email)
    return sha256(normalized_email.encode("utf-8")).hexdigest()


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
