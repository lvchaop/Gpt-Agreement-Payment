"""Run the Auth Web Datadog and Statsig SDKs beside the pure HTTP auth flow."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import logging
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import uuid
from collections import Counter, deque
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from refactor_app.config.browser_fingerprint import BROWSER_FINGERPRINT

from .sentinel_quickjs import SentinelRuntimeContext, _resolve_node_binary

logger = logging.getLogger(__name__)

_BOOTSTRAP_SCRIPT_ID = "bootstrap-inert-script"
_DEFAULT_RUM_PROXY_PATH = "/awe/api/v2/rum"
_DEFAULT_STATSIG_API_URL = "https://ab.chatgpt.com/v1"
_DEFAULT_STATSIG_LOG_EVENT_URL = "https://chatgpt.com/ces/v1/rgstr"
_CLIENT_HINT_BRAND_PATTERN = re.compile(
    r'(?P<brand>"(?:\\.|[^"\\])*")\s*;\s*v\s*=\s*'
    r'(?P<version>"(?:\\.|[^"\\])*")'
)


class AuthWebRuntimeError(RuntimeError):
    pass


class _AuthHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bootstrap_text = ""
        self.module_texts: list[str] = []
        self.title = ""
        self._script_attrs: dict[str, str] | None = None
        self._script_chunks: list[str] = []
        self._in_title = False
        self._title_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self._script_attrs = {name: value or "" for name, value in attrs}
            self._script_chunks = []
        elif tag.lower() == "title":
            self._in_title = True
            self._title_chunks = []

    def handle_data(self, data: str) -> None:
        if self._script_attrs is not None:
            self._script_chunks.append(data)
        if self._in_title:
            self._title_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._script_attrs is not None:
            text = "".join(self._script_chunks)
            if self._script_attrs.get("id") == _BOOTSTRAP_SCRIPT_ID:
                self.bootstrap_text = text
            if self._script_attrs.get("type") == "module":
                self.module_texts.append(text)
            self._script_attrs = None
            self._script_chunks = []
        elif tag.lower() == "title" and self._in_title:
            self.title = "".join(self._title_chunks).strip()
            self._in_title = False
            self._title_chunks = []


def _parse_client_hint_brands(value: Any) -> list[dict[str, str]]:
    brands = [
        {
            "brand": str(json.loads(match.group("brand"))),
            "version": str(json.loads(match.group("version"))),
        }
        for match in _CLIENT_HINT_BRAND_PATTERN.finditer(str(value or ""))
    ]
    if not brands:
        raise AuthWebRuntimeError("browser profile Client Hint brand list is invalid")
    return brands


def _decode_client_hint_string(value: Any) -> str:
    encoded = str(value or "").strip()
    if not encoded:
        return ""
    try:
        decoded = json.loads(encoded)
    except json.JSONDecodeError:
        return encoded
    return str(decoded) if isinstance(decoded, str) else encoded


@dataclass(frozen=True)
class AuthWebRuntimeAssets:
    bootstrap_json: str
    bootstrap: dict[str, Any]
    entry_url: str
    statsig_url: str
    app_core_url: str
    datadog_url: str
    statsig_path: Path
    datadog_path: Path
    datadog_config: dict[str, Any]
    statsig_client_key: str
    statsig_api_url: str
    statsig_log_event_url: str
    page_title: str
    route_id: str
    page_url: str

    @property
    def auth_session_logging_id(self) -> str:
        metadata = self.bootstrap.get("immutableClientSessionMetadata")
        if not isinstance(metadata, dict):
            return ""
        return str(metadata.get("auth_session_logging_id") or "").strip()


def _extract_javascript_imports(source: str) -> list[str]:
    return re.findall(
        r'(?:from\s*|import\s*\(?\s*)["\']([^"\']+)["\']',
        source,
    )


def _find_import_url(entry_url: str, source: str, prefix: str) -> str:
    for specifier in _extract_javascript_imports(source):
        if Path(urlparse(specifier).path).name.startswith(prefix):
            return urljoin(entry_url, specifier)
    raise AuthWebRuntimeError(f"Auth Web entry bundle missing {prefix} import")


def _extract_literal(block: str, key: str) -> str:
    match = re.search(rf'{re.escape(key)}\s*:\s*["\']([^"\']+)["\']', block)
    if not match:
        raise AuthWebRuntimeError(f"Auth Web app-core missing Datadog field: {key}")
    return match.group(1)


def _extract_number(block: str, key: str, default: int) -> int:
    match = re.search(rf"{re.escape(key)}\s*:\s*(\d+)", block)
    return int(match.group(1)) if match else default


def _parse_app_core_config(source: str) -> tuple[dict[str, Any], str, str, str]:
    start = re.search(r"\.init\(\{\s*applicationId\s*:", source)
    if not start:
        raise AuthWebRuntimeError("Auth Web app-core Datadog initialization was not found")
    block = source[start.start() : start.start() + 6_000]
    config = {
        "applicationId": _extract_literal(block, "applicationId"),
        "clientToken": _extract_literal(block, "clientToken"),
        "site": _extract_literal(block, "site"),
        "service": _extract_literal(block, "service"),
        "env": _extract_literal(block, "env"),
        "version": _extract_literal(block, "version"),
        "sessionSampleRate": _extract_number(block, "sessionSampleRate", 100),
        "sessionReplaySampleRate": _extract_number(block, "sessionReplaySampleRate", 1),
    }
    rum_path_match = re.search(r'["\'](/awe/api/v2/rum)["\']', source)
    config["rumProxyPath"] = rum_path_match.group(1) if rum_path_match else _DEFAULT_RUM_PROXY_PATH
    client_keys = sorted(set(re.findall(r'["\'](client-[A-Za-z0-9_-]+)["\']', source)))
    if len(client_keys) != 1:
        raise AuthWebRuntimeError(
            f"Auth Web app-core Statsig client key count was {len(client_keys)}, expected 1"
        )
    statsig_api_match = re.search(r'["\'](https://ab\.chatgpt\.com/v1)["\']', source)
    statsig_log_event_match = re.search(r'["\'](/ces/v1/rgstr)["\']', source)
    return (
        config,
        client_keys[0],
        statsig_api_match.group(1) if statsig_api_match else _DEFAULT_STATSIG_API_URL,
        urljoin(
            "https://chatgpt.com",
            statsig_log_event_match.group(1)
            if statsig_log_event_match
            else _DEFAULT_STATSIG_LOG_EVENT_URL,
        ),
    )


def _cache_asset(url: str, content: bytes) -> Path:
    digest = hashlib.sha256(url.encode("utf-8") + b"\0" + content).hexdigest()
    cache_root = Path(
        os.getenv("AUTH_WEB_RUNTIME_CACHE_DIR", "").strip()
        or Path(tempfile.gettempdir()) / "refactor-app" / "auth-web-runtime"
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f"{digest}.js"
    if target.exists() and target.stat().st_size == len(content):
        return target
    temporary = cache_root / f".{digest}-{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_bytes(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _response_content(response: Any) -> bytes:
    content = getattr(response, "content", b"")
    if isinstance(content, bytes) and content:
        return content
    text = str(getattr(response, "text", "") or "")
    return text.encode("utf-8")


def _document_cookie_header(session: Any, page_url: str) -> str:
    host = (urlparse(page_url).hostname or "").lower()
    pairs: list[str] = []
    seen: set[str] = set()
    try:
        cookies = list(session.cookies)
    except Exception:
        cookies = []
    for cookie in cookies:
        name = str(getattr(cookie, "name", "") or "").strip()
        value = str(getattr(cookie, "value", "") or "")
        domain = str(getattr(cookie, "domain", "") or "").lstrip(".").lower()
        if not name or name in seen:
            continue
        if domain and host != domain and not host.endswith(f".{domain}"):
            continue
        seen.add(name)
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _download_asset(
    session: Any,
    url: str,
    *,
    referer: str,
    accept_language: str = "",
    browser_profile: dict[str, Any] | None = None,
) -> bytes:
    profile = browser_profile or {}
    request_headers = {
        "Accept": "*/*",
        "Referer": referer,
        "User-Agent": str(
            profile.get("user_agent") or BROWSER_FINGERPRINT.user_agent
        ),
        "sec-ch-ua": str(
            profile.get("sec_ch_ua") or BROWSER_FINGERPRINT.sec_ch_ua
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": str(
            profile.get("sec_ch_ua_platform")
            or BROWSER_FINGERPRINT.sec_ch_ua_platform
        ),
        "Sec-Fetch-Dest": "script",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    if str(accept_language or "").strip():
        request_headers["Accept-Language"] = str(accept_language).strip()
    response = session.get(
        url,
        headers=request_headers,
        timeout=30,
    )
    if int(getattr(response, "status_code", 0) or 0) != 200:
        raise AuthWebRuntimeError(
            f"Auth Web asset download failed: {url} HTTP {response.status_code}"
        )
    content = _response_content(response)
    if len(content) < 500:
        raise AuthWebRuntimeError(f"Auth Web asset was incomplete: {url} bytes={len(content)}")
    return content


def load_auth_web_runtime_assets(
    session: Any,
    *,
    html_text: str,
    page_url: str,
    accept_language: str = "",
    browser_profile: dict[str, Any] | None = None,
) -> AuthWebRuntimeAssets:
    parser = _AuthHtmlParser()
    parser.feed(html_text)
    if not parser.bootstrap_text:
        raise AuthWebRuntimeError("Auth Web bootstrap-inert-script was not present")
    try:
        bootstrap = json.loads(html.unescape(parser.bootstrap_text))
    except (TypeError, ValueError) as exc:
        raise AuthWebRuntimeError("Auth Web bootstrap JSON was invalid") from exc
    if not isinstance(bootstrap, dict):
        raise AuthWebRuntimeError("Auth Web bootstrap root was not an object")
    metadata = bootstrap.get("immutableClientSessionMetadata")
    statsig_data = bootstrap.get("statsigClientInitData")
    identity = statsig_data.get("identity") if isinstance(statsig_data, dict) else None
    if not isinstance(metadata, dict) or not isinstance(identity, dict):
        raise AuthWebRuntimeError("Auth Web bootstrap identity metadata was incomplete")

    module_source = "\n".join(parser.module_texts)
    entry_matches = re.findall(
        r'["\'](https://[^"\']+/entry\.client-[^"\']+\.js)["\']', module_source
    )
    if len(set(entry_matches)) != 1:
        raise AuthWebRuntimeError(
            f"Auth Web entry bundle count was {len(set(entry_matches))}, expected 1"
        )
    entry_url = entry_matches[0]
    entry_content = _download_asset(
        session,
        entry_url,
        referer=page_url,
        accept_language=accept_language,
        browser_profile=browser_profile,
    )
    entry_source = entry_content.decode("utf-8")
    statsig_url = _find_import_url(entry_url, entry_source, "statsig-")
    app_core_url = _find_import_url(entry_url, entry_source, "app-core-")
    datadog_url = _find_import_url(entry_url, entry_source, "datadog-")

    statsig_content = _download_asset(
        session,
        statsig_url,
        referer=page_url,
        accept_language=accept_language,
        browser_profile=browser_profile,
    )
    app_core_content = _download_asset(
        session,
        app_core_url,
        referer=page_url,
        accept_language=accept_language,
        browser_profile=browser_profile,
    )
    datadog_content = _download_asset(
        session,
        datadog_url,
        referer=page_url,
        accept_language=accept_language,
        browser_profile=browser_profile,
    )
    if b"StatsigClient" not in statsig_content:
        raise AuthWebRuntimeError("Auth Web Statsig bundle marker was missing")
    if b"startDurationVital" not in datadog_content or b"setGlobalContext" not in datadog_content:
        raise AuthWebRuntimeError("Auth Web Datadog bundle markers were missing")
    (
        datadog_config,
        statsig_client_key,
        statsig_api_url,
        statsig_log_event_url,
    ) = _parse_app_core_config(app_core_content.decode("utf-8"))

    route_id_matches = re.findall(
        r'window\.__reactRouterRouteModules\s*=\s*\{[^}]*["\']([A-Z][A-Z0-9_]+)["\']\s*:',
        module_source,
    )
    route_id = route_id_matches[-1] if route_id_matches else str(identity.get("route") or "")
    page_title = parser.title or str(identity.get("route") or "Auth")
    return AuthWebRuntimeAssets(
        bootstrap_json=json.dumps(bootstrap, separators=(",", ":"), ensure_ascii=False),
        bootstrap=bootstrap,
        entry_url=entry_url,
        statsig_url=statsig_url,
        app_core_url=app_core_url,
        datadog_url=datadog_url,
        statsig_path=_cache_asset(statsig_url, statsig_content),
        datadog_path=_cache_asset(datadog_url, datadog_content),
        datadog_config=datadog_config,
        statsig_client_key=statsig_client_key,
        statsig_api_url=statsig_api_url,
        statsig_log_event_url=statsig_log_event_url,
        page_title=page_title,
        route_id=route_id,
        page_url=page_url,
    )


class AuthWebRuntime:
    def __init__(
        self,
        session: Any,
        assets: AuthWebRuntimeAssets,
        sentinel_context: SentinelRuntimeContext,
    ) -> None:
        self.session = session
        self.assets = assets
        self.sentinel_context = sentinel_context
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._transport_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._stderr_lines: deque[str] = deque(maxlen=80)
        self._business_responses: dict[str, Any] = {}
        self._business_errors: dict[str, Exception] = {}
        self._telemetry_transport_counts: Counter[str] = Counter()
        self._telemetry_summary_logged = False
        self._command_sequence = 0
        self._write_lock = threading.Lock()
        self._closed = False
        self._page_url = assets.page_url
        self._page_title = assets.page_title
        self._route_id = assets.route_id
        self.runtime_info: dict[str, Any] = {}
        try:
            self._start()
        except Exception:
            process = self._process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            self._closed = True
            raise

    @property
    def is_ready(self) -> bool:
        return self._process is not None and self._process.poll() is None and not self._closed

    @property
    def auth_session_logging_id(self) -> str:
        return self.assets.auth_session_logging_id

    @property
    def page_url(self) -> str:
        return self._page_url

    @staticmethod
    def supports_url(url: str) -> bool:
        return (urlparse(url).hostname or "").lower() == "auth.openai.com"

    def _start(self) -> None:
        runner = Path(__file__).resolve().with_name("auth_web_runtime_runner.js")
        env = dict(os.environ)
        timezone_name = str(self.sentinel_context.browser_profile.get("timezone_iana") or "").strip()
        if not timezone_name:
            raise RuntimeError("verified proxy timezone is missing from Sentinel context")
        env["TZ"] = timezone_name
        self._process = subprocess.Popen(
            [_resolve_node_binary(), str(runner)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
        )
        threading.Thread(
            target=self._read_stdout, name="auth-web-runtime-stdout", daemon=True
        ).start()
        threading.Thread(
            target=self._transport_loop, name="auth-web-runtime-transport", daemon=True
        ).start()
        threading.Thread(
            target=self._read_stderr, name="auth-web-runtime-stderr", daemon=True
        ).start()
        identity = self.assets.bootstrap["statsigClientInitData"]["identity"]
        profile = self.sentinel_context.browser_profile
        sec_ch_ua = str(
            profile.get("sec_ch_ua") or BROWSER_FINGERPRINT.sec_ch_ua
        )
        sec_ch_ua_full_version_list = str(
            profile.get("sec_ch_ua_full_version_list")
            or BROWSER_FINGERPRINT.sec_ch_ua_full_version_list
        )
        result = self._command(
            {
                "type": "init",
                "bootstrapJson": self.assets.bootstrap_json,
                "datadogBundlePath": str(self.assets.datadog_path),
                "statsigBundlePath": str(self.assets.statsig_path),
                "datadogConfig": self.assets.datadog_config,
                "statsigClientKey": self.assets.statsig_client_key,
                "statsigApiUrl": self.assets.statsig_api_url,
                "statsigLogEventUrl": self.assets.statsig_log_event_url,
                "pageTitle": self.assets.page_title,
                "routeId": self.assets.route_id,
                "webProfile": {
                    "pageUrl": self.assets.page_url,
                    "pageTitle": self.assets.page_title,
                    "referrer": "https://chatgpt.com/",
                    "documentCookie": _document_cookie_header(
                        self.session,
                        self.assets.page_url,
                    ),
                    "language": str(
                        profile.get("navigator_language") or identity.get("locale") or ""
                    ),
                    "languages": list(
                        profile.get("navigator_languages")
                        or [profile.get("navigator_language") or identity.get("locale")]
                    ),
                    "userAgent": str(
                        profile.get("user_agent")
                        or identity.get("userAgent")
                        or BROWSER_FINGERPRINT.user_agent
                    ),
                    "platform": str(
                        profile.get("navigator_platform")
                        or BROWSER_FINGERPRINT.navigator_platform
                    ),
                    "hardwareConcurrency": int(profile.get("hardware_concurrency") or 8),
                    "deviceMemory": int(profile.get("device_memory") or 8),
                    "screenWidth": int(profile.get("screen_width") or 1512),
                    "screenHeight": int(profile.get("screen_height") or 982),
                    "devicePixelRatio": float(profile.get("device_pixel_ratio") or 2),
                    "chromeMajor": str(
                        profile.get("chrome_major") or BROWSER_FINGERPRINT.major_version
                    ),
                    "chromeFullVersion": str(
                        profile.get("chrome_full_version")
                        or BROWSER_FINGERPRINT.sec_ch_ua_full_version.strip('"')
                    ),
                    "userAgentData": {
                        "brands": _parse_client_hint_brands(sec_ch_ua),
                        "mobile": False,
                        "platform": _decode_client_hint_string(
                            profile.get("sec_ch_ua_platform")
                            or BROWSER_FINGERPRINT.sec_ch_ua_platform
                        ),
                        "architecture": _decode_client_hint_string(
                            profile.get("sec_ch_ua_arch")
                            or BROWSER_FINGERPRINT.sec_ch_ua_arch
                        ),
                        "bitness": _decode_client_hint_string(
                            profile.get("sec_ch_ua_bitness")
                            or BROWSER_FINGERPRINT.sec_ch_ua_bitness
                        ),
                        "model": _decode_client_hint_string(
                            profile.get("sec_ch_ua_model") or '""'
                        ),
                        "platformVersion": _decode_client_hint_string(
                            profile.get("sec_ch_ua_platform_version")
                            or BROWSER_FINGERPRINT.sec_ch_ua_platform_version
                        ),
                        "uaFullVersion": _decode_client_hint_string(
                            profile.get("sec_ch_ua_full_version")
                            or profile.get("chrome_full_version")
                            or BROWSER_FINGERPRINT.sec_ch_ua_full_version
                        ),
                        "fullVersionList": _parse_client_hint_brands(
                            sec_ch_ua_full_version_list
                        ),
                    },
                    "navigationDuration": 3459.1,
                    "domInteractive": 3425.8,
                    "redirectCount": 1,
                    "transferSize": 15989,
                    "firstContentfulPaint": 3296,
                },
            },
            timeout=60,
        )
        self.runtime_info = dict(result)
        if not result.get("datadogSessionReady") or not result.get("statsigSessionReady"):
            raise AuthWebRuntimeError("Auth Web SDK runtime did not initialize both sessions")

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                logger.error("Auth Web runtime emitted invalid JSON: %s", line[:500].rstrip())
                continue
            if isinstance(message, dict):
                if message.get("type") == "transport_request":
                    self._transport_queue.put(message)
                else:
                    self._stdout_queue.put(message)

    def _transport_loop(self) -> None:
        while True:
            message = self._transport_queue.get()
            if message is None:
                return
            try:
                self._handle_transport_request(message)
            except Exception:
                logger.exception("Auth Web runtime transport dispatcher failed")

    def _read_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr_lines.append(line.rstrip())

    def _send(self, message: dict[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            detail = " | ".join(self._stderr_lines)[-2_000:]
            raise AuthWebRuntimeError(f"Auth Web runtime process exited: {detail}")
        with self._write_lock:
            process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            process.stdin.flush()

    def _command(self, payload: dict[str, Any], *, timeout: float = 45) -> dict[str, Any]:
        self._command_sequence += 1
        command_id = f"command-{self._command_sequence}"
        self._send({**payload, "commandId": command_id})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                detail = " | ".join(self._stderr_lines)[-2_000:]
                raise AuthWebRuntimeError(
                    f"Auth Web runtime command timed out: {payload.get('type')} {detail}"
                )
            try:
                message = self._stdout_queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise AuthWebRuntimeError(
                    f"Auth Web runtime command timed out: {payload.get('type')}"
                ) from exc
            message_type = message.get("type")
            if message_type == "protocol_error":
                raise AuthWebRuntimeError(str(message.get("error") or "runtime protocol error"))
            if message_type != "command_result" or message.get("commandId") != command_id:
                continue
            if not message.get("ok"):
                raise AuthWebRuntimeError(str(message.get("error") or "runtime command failed"))
            result = message.get("result")
            return result if isinstance(result, dict) else {}

    def _handle_transport_request(self, message: dict[str, Any]) -> None:
        transport_id = str(message.get("transportId") or "")
        bridge_request_id = str(message.get("bridgeRequestId") or "")
        method = str(message.get("method") or "GET").upper()
        url = str(message.get("url") or "")
        headers = {
            str(name): str(value)
            for name, value in (message.get("headers") or {}).items()
            if value is not None
        }
        identity = self.assets.bootstrap["statsigClientInitData"]["identity"]
        profile = getattr(getattr(self, "sentinel_context", None), "browser_profile", {})
        page_url = urlparse(self._page_url)
        request_url = urlparse(url)
        if request_url.scheme == page_url.scheme and request_url.netloc == page_url.netloc:
            fetch_site = "same-origin"
        elif (
            request_url.hostname
            and page_url.hostname
            and request_url.hostname.rsplit(".", 2)[-2:]
            == page_url.hostname.rsplit(".", 2)[-2:]
        ):
            fetch_site = "same-site"
        else:
            fetch_site = "cross-site"
        referer = self._page_url
        if request_url.hostname in {"chatgpt.com", "www.chatgpt.com"} or (
            request_url.hostname or ""
        ).endswith(".chatgpt.com"):
            referer = f"{page_url.scheme}://{page_url.netloc}/"
        defaults = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": str(
                profile.get("accept_language") or identity.get("locale") or ""
            ),
            "Origin": f"{page_url.scheme}://{page_url.netloc}",
            "Referer": referer,
            "User-Agent": str(
                profile.get("user_agent")
                or identity.get("userAgent")
                or BROWSER_FINGERPRINT.user_agent
            ),
            "sec-ch-ua": str(
                profile.get("sec_ch_ua") or BROWSER_FINGERPRINT.sec_ch_ua
            ),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": str(
                profile.get("sec_ch_ua_platform")
                or BROWSER_FINGERPRINT.sec_ch_ua_platform
            ),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": fetch_site,
            "Priority": "u=1, i",
        }
        lower_names = {name.lower() for name in headers}
        for name, value in defaults.items():
            if name.lower() not in lower_names:
                headers[name] = value
        body = base64.b64decode(str(message.get("bodyBase64") or ""))
        parsed_url = urlparse(url)
        telemetry_kind = ""
        if parsed_url.hostname == "ab.chatgpt.com" and parsed_url.path.endswith(
            "/initialize"
        ):
            telemetry_kind = "statsig_initialize"
        elif parsed_url.path == "/ces/v1/rgstr":
            telemetry_kind = "statsig_events"
        elif parsed_url.path == "/awe/api/v2/rum":
            telemetry_kind = "datadog_rum"
        requested_timeout_seconds = max(
            5,
            int(float(message.get("timeoutMs") or 60_000) / 1_000),
        )
        if telemetry_kind:
            try:
                telemetry_timeout_seconds = max(
                    5,
                    int(os.getenv("AUTH_WEB_TELEMETRY_HTTP_TIMEOUT_SECONDS", "8")),
                )
            except ValueError:
                telemetry_timeout_seconds = 8
            requested_timeout_seconds = min(
                requested_timeout_seconds,
                telemetry_timeout_seconds,
            )
        try:
            requester = getattr(self.session, "request", None)
            if callable(requester):
                response = requester(
                    method,
                    url,
                    headers=headers,
                    data=body if method not in ("GET", "HEAD") else None,
                    timeout=requested_timeout_seconds,
                    allow_redirects=bool(message.get("allowRedirects", True)),
                )
            else:
                response = getattr(self.session, method.lower())(
                    url,
                    headers=headers,
                    data=body if method not in ("GET", "HEAD") else None,
                    timeout=requested_timeout_seconds,
                    allow_redirects=bool(message.get("allowRedirects", True)),
                )
            if bridge_request_id:
                self._business_responses[bridge_request_id] = response
            response_status = int(getattr(response, "status_code", 0) or 0)
            if telemetry_kind:
                self._telemetry_transport_counts[f"{telemetry_kind}:{response_status}"] += 1
                if not 200 <= response_status < 300:
                    logger.warning(
                        "Auth Web telemetry failed kind=%s status=%s",
                        telemetry_kind,
                        response_status,
                    )
            response_headers = dict(getattr(response, "headers", {}) or {})
            self._send(
                {
                    "type": "transport_response",
                    "transportId": transport_id,
                    "status": int(getattr(response, "status_code", 0) or 0),
                    "statusText": str(getattr(response, "reason", "") or ""),
                    "headers": response_headers,
                    "bodyBase64": base64.b64encode(_response_content(response)).decode("ascii"),
                }
            )
        except Exception as exc:
            if bridge_request_id:
                self._business_errors[bridge_request_id] = exc
            self._send(
                {
                    "type": "transport_response",
                    "transportId": transport_id,
                    "status": 599,
                    "statusText": type(exc).__name__,
                    "headers": {},
                    "bodyBase64": base64.b64encode(str(exc).encode("utf-8")).decode("ascii"),
                }
            )

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        if not self.is_ready:
            raise AuthWebRuntimeError("Auth Web runtime request attempted before initialization")
        unsupported = set(kwargs) - {
            "headers",
            "json",
            "data",
            "params",
            "timeout",
            "allow_redirects",
        }
        if unsupported:
            raise AuthWebRuntimeError(
                f"Auth Web runtime request has unsupported options: {sorted(unsupported)}"
            )
        method = method.upper()
        headers = {str(name): str(value) for name, value in (kwargs.get("headers") or {}).items()}
        params = kwargs.get("params")
        if params:
            parsed = urlparse(url)
            query = urlencode(params, doseq=True)
            url = urlunparse(
                parsed._replace(query="&".join(part for part in (parsed.query, query) if part))
            )
        body = b""
        if kwargs.get("json") is not None:
            body = json.dumps(kwargs["json"], separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
            if not any(name.lower() == "content-type" for name in headers):
                headers["Content-Type"] = "application/json"
        elif kwargs.get("data") is not None:
            data = kwargs["data"]
            if isinstance(data, dict):
                body = urlencode(data, doseq=True).encode("utf-8")
                if not any(name.lower() == "content-type" for name in headers):
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
            elif isinstance(data, bytes):
                body = data
            else:
                body = str(data).encode("utf-8")
        bridge_request_id = str(uuid.uuid4())
        timeout = float(kwargs.get("timeout") or 30)
        self._command(
            {
                "type": "request",
                "bridgeRequestId": bridge_request_id,
                "method": method,
                "url": url,
                "headers": headers,
                "bodyBase64": base64.b64encode(body).decode("ascii"),
                "allowRedirects": bool(kwargs.get("allow_redirects", True)),
                "timeoutMs": max(5_000, int(timeout * 1_000)),
            },
            timeout=max(45, timeout + 30),
        )
        error = self._business_errors.pop(bridge_request_id, None)
        if error is not None:
            self._business_responses.pop(bridge_request_id, None)
            raise error
        response = self._business_responses.pop(bridge_request_id, None)
        if response is None:
            raise AuthWebRuntimeError("Auth Web runtime did not return the bridged HTTP response")
        return response

    def record_stage(
        self,
        name: str,
        *,
        phase: str,
        page_url: str = "",
        status: int | None = None,
    ) -> None:
        self._command(
            {
                "type": "stage",
                "name": name,
                "phase": phase,
                "pageUrl": page_url,
                "status": status,
            }
        )

    def record_sentinel_timing(self, stage: str) -> None:
        normalized_stage = str(stage or "").strip().lower()
        if normalized_stage not in {"request_start", "ready"}:
            raise ValueError(f"unsupported Sentinel timing stage: {stage}")
        self._command(
            {
                "type": "sentinel_timing",
                "stage": normalized_stage,
            },
            timeout=15,
        )

    def navigate(
        self,
        *,
        page_url: str,
        page_title: str,
        route_id: str,
    ) -> bool:
        if not self.is_ready:
            raise AuthWebRuntimeError("Auth Web runtime navigation attempted before initialization")
        normalized_url = str(page_url or "").strip()
        normalized_title = str(page_title or "").strip()
        normalized_route = str(route_id or "").strip()
        if not normalized_url or not self.supports_url(normalized_url):
            raise AuthWebRuntimeError(f"Auth Web runtime navigation URL was invalid: {page_url}")
        result = self._command(
            {
                "type": "navigate",
                "pageUrl": normalized_url,
                "pageTitle": normalized_title,
                "routeId": normalized_route,
                "documentCookie": _document_cookie_header(self.session, normalized_url),
            }
        )
        self._page_url = normalized_url
        self._page_title = normalized_title
        self._route_id = normalized_route
        return bool(result.get("changed"))

    def flush(self) -> None:
        if not self.is_ready:
            raise AuthWebRuntimeError("Auth Web runtime flush attempted before initialization")
        self._command({"type": "flush"}, timeout=15)

    def close(self) -> None:
        if self._closed:
            return
        process = self._process
        try:
            if process is not None and process.poll() is None:
                self._command({"type": "close"}, timeout=15)
                process.wait(timeout=3)
        except Exception as exc:
            logger.warning("Auth Web runtime close failed: %s", exc)
        finally:
            self._closed = True
            self._transport_queue.put(None)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            if self._telemetry_transport_counts and not self._telemetry_summary_logged:
                self._telemetry_summary_logged = True
                logger.info(
                    "Auth Web telemetry summary %s",
                    " ".join(
                        f"{key}={count}"
                        for key, count in sorted(self._telemetry_transport_counts.items())
                    ),
                )


def start_auth_web_runtime(
    session: Any,
    *,
    html_text: str,
    page_url: str,
    sentinel_context: SentinelRuntimeContext,
) -> AuthWebRuntime:
    assets = load_auth_web_runtime_assets(
        session,
        html_text=html_text,
        page_url=page_url,
        accept_language=str(
            sentinel_context.browser_profile.get("accept_language") or ""
        ),
        browser_profile=sentinel_context.browser_profile,
    )
    return AuthWebRuntime(session, assets, sentinel_context)
