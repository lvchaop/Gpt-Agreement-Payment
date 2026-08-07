"""Run OpenAI's real Sentinel SDK in a browser-shaped Node VM."""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from refactor_app.config.browser_fingerprint import BROWSER_FINGERPRINT

logger = logging.getLogger(__name__)

SENTINEL_VERSION = "20260219f9f6"
SENTINEL_SDK_URL = f"https://sentinel.openai.com/sentinel/{SENTINEL_VERSION}/sdk.js"
SENTINEL_REQ_URL = "https://sentinel.openai.com/backend-api/sentinel/req"
MIN_SENTINEL_SDK_BYTES = 10_000
DEFAULT_UA = BROWSER_FINGERPRINT.user_agent
DEFAULT_SEC_CH_UA = BROWSER_FINGERPRINT.sec_ch_ua

_SESSION_CONTEXT_ATTR = "_openai_sentinel_runtime_context"
_FLOW_PAGE_URL = {
    "authorize_continue": "https://auth.openai.com/email-verification",
    "email_otp_validate": "https://auth.openai.com/email-verification",
    "password_verify": "https://auth.openai.com/log-in/password",
    "username_password_create": "https://auth.openai.com/create-account/password",
    "create_account": "https://auth.openai.com/about-you",
    "oauth_create_account": "https://auth.openai.com/about-you",
}

# These values are copied from the known-good registration project's captured
# browser profile. HTTP UA/client hints still come from this project's configured
# curl_cffi impersonation so the TLS and JavaScript identities use one Chrome major.
_SCREEN_PROFILE = {
    "screen_width": 1680,
    "screen_height": 1050,
    "hardware_concurrency": 6,
    "js_heap_size_limit": 4_395_630_592,
    "device_memory": 8,
    "device_pixel_ratio": 2,
}
_LOCALE_PROFILES = {
    "JP": {
        "navigator_language": "ja-JP",
        "navigator_languages": ["ja-JP"],
        "accept_language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
        "timezone_iana": "Asia/Tokyo",
        "timezone_offset_minutes": 540,
        "timezone_name": "Japan Standard Time",
    },
    "CN": {
        "navigator_language": "zh-CN",
        "navigator_languages": ["zh-CN"],
        "accept_language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "timezone_iana": "Asia/Shanghai",
        "timezone_offset_minutes": 480,
        "timezone_name": "China Standard Time",
    },
    "HK": {
        "navigator_language": "zh-HK",
        "navigator_languages": ["zh-HK"],
        "accept_language": "zh-HK,zh-TW;q=0.9,zh;q=0.8,en-US;q=0.7,en;q=0.6",
        "timezone_iana": "Asia/Hong_Kong",
        "timezone_offset_minutes": 480,
        "timezone_name": "Hong Kong Standard Time",
    },
    "TW": {
        "navigator_language": "zh-TW",
        "navigator_languages": ["zh-TW"],
        "accept_language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "timezone_iana": "Asia/Taipei",
        "timezone_offset_minutes": 480,
        "timezone_name": "Taipei Standard Time",
    },
    "US": {
        "navigator_language": "en-US",
        "navigator_languages": ["en-US"],
        "accept_language": "en-US,en;q=0.9",
        "timezone_iana": "America/Los_Angeles",
        "timezone_offset_minutes": -420,
        "timezone_name": "Pacific Daylight Time",
    },
    "SG": {
        "navigator_language": "en-SG",
        "navigator_languages": ["en-SG"],
        "accept_language": "en-SG,en-US;q=0.9,en;q=0.8",
        "timezone_iana": "Asia/Singapore",
        "timezone_offset_minutes": 480,
        "timezone_name": "Singapore Standard Time",
    },
    "GB": {
        "navigator_language": "en-GB",
        "navigator_languages": ["en-GB"],
        "accept_language": "en-GB,en-US;q=0.9,en;q=0.8",
        "timezone_iana": "Europe/London",
        "timezone_offset_minutes": 60,
        "timezone_name": "British Summer Time",
    },
    "DE": {
        "navigator_language": "de-DE",
        "navigator_languages": ["de-DE"],
        "accept_language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "timezone_iana": "Europe/Berlin",
        "timezone_offset_minutes": 120,
        "timezone_name": "Central European Summer Time",
    },
    "FR": {
        "navigator_language": "fr-FR",
        "navigator_languages": ["fr-FR"],
        "accept_language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "timezone_iana": "Europe/Paris",
        "timezone_offset_minutes": 120,
        "timezone_name": "Central European Summer Time",
    },
    "NL": {
        "navigator_language": "nl-NL",
        "navigator_languages": ["nl-NL"],
        "accept_language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
        "timezone_iana": "Europe/Amsterdam",
        "timezone_offset_minutes": 120,
        "timezone_name": "Central European Summer Time",
    },
}
_LOCALE_ALIASES = {"CA": "US", "AU": "GB"}

_NAVIGATOR_PROTO_SAMPLES = [
    "createAuctionNonce-function createAuctionNonce() { [native code] }",
    "clearOriginJoinedAdInterestGroups-function clearOriginJoinedAdInterestGroups() { [native code] }",
    "updateAdInterestGroups-function updateAdInterestGroups() { [native code] }",
    "canLoadAdAuctionFencedFrame-function canLoadAdAuctionFencedFrame() { [native code] }",
    "gpu-[object GPU]",
    "getBattery-function getBattery() { [native code] }",
    "getGamepads-function getGamepads() { [native code] }",
    "javaEnabled-function javaEnabled() { [native code] }",
    "sendBeacon-function sendBeacon() { [native code] }",
    "vibrate-function vibrate() { [native code] }",
    "login-[object NavigatorLogin]",
]
_DOCUMENT_KEY_SAMPLES = [
    "currentScript",
    "scripts",
    "cookie",
    "URL",
    "documentURI",
    "referrer",
    "title",
    "characterSet",
    "charset",
    "compatMode",
    "contentType",
    "readyState",
    "visibilityState",
    "hidden",
    "hasFocus",
    "documentElement",
    "body",
    "addEventListener",
    "removeEventListener",
    "querySelector",
    "querySelectorAll",
    "getElementById",
    "getElementsByTagName",
    "createElement",
]
_WINDOW_KEY_SAMPLES = [
    "window",
    "self",
    "top",
    "parent",
    "frames",
    "navigator",
    "screen",
    "location",
    "localStorage",
    "sessionStorage",
    "history",
    "innerWidth",
    "innerHeight",
    "outerWidth",
    "outerHeight",
    "devicePixelRatio",
    "chrome",
    "performance",
    "crypto",
    "TextEncoder",
    "URL",
    "URLSearchParams",
    "AbortController",
    "locationbar",
    "scrollX",
    "scrollY",
    "ondevicemotion",
    "requestAnimationFrame",
    "queueMicrotask",
    "onfocus",
    "onblur",
    "onpageshow",
]


@dataclass(frozen=True)
class SentinelRuntimeContext:
    """Stable browser-visible values reused by one AuthFlow HTTP session."""

    country_code: str
    sentinel_sid: str
    react_listening_key: str
    react_container_key: str
    react_resources_key: str
    browser_profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "country_code": self.country_code,
            "sentinel_sid": self.sentinel_sid,
            "react_listening_key": self.react_listening_key,
            "react_container_key": self.react_container_key,
            "react_resources_key": self.react_resources_key,
            "browser_profile": dict(self.browser_profile),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SentinelRuntimeContext":
        profile = data.get("browser_profile")
        required = (
            "sentinel_sid",
            "react_listening_key",
            "react_container_key",
            "react_resources_key",
        )
        if not isinstance(profile, dict) or any(not str(data.get(key) or "") for key in required):
            raise ValueError("Sentinel runtime context is incomplete")
        return cls(
            country_code=str(data.get("country_code") or "US").upper(),
            sentinel_sid=str(data["sentinel_sid"]),
            react_listening_key=str(data["react_listening_key"]),
            react_container_key=str(data["react_container_key"]),
            react_resources_key=str(data["react_resources_key"]),
            browser_profile=dict(profile),
        )


def create_sentinel_runtime_context(country_code: str = "") -> SentinelRuntimeContext:
    country = str(country_code or os.getenv("OPENAI_SENTINEL_PROXY_COUNTRY", "US")).upper()
    locale_key = _LOCALE_ALIASES.get(country, country)
    locale = dict(_LOCALE_PROFILES.get(locale_key, _LOCALE_PROFILES["US"]))
    suffix = uuid.uuid4().hex[:11]
    react_container_key = f"__reactContainer${suffix}"
    profile: dict[str, Any] = {
        **_SCREEN_PROFILE,
        **locale,
        "browser_family": "chrome",
        "navigator_platform": BROWSER_FINGERPRINT.navigator_platform,
        "navigator_vendor": "Google Inc.",
        "user_agent_data_platform": BROWSER_FINGERPRINT.sec_ch_ua_platform.strip('"'),
        "user_agent": BROWSER_FINGERPRINT.user_agent,
        "chrome_major": str(BROWSER_FINGERPRINT.major_version),
        "chrome_full_version": BROWSER_FINGERPRINT.sec_ch_ua_full_version.strip('"'),
        "sec_ch_ua": BROWSER_FINGERPRINT.sec_ch_ua,
        "sec_ch_ua_platform": BROWSER_FINGERPRINT.sec_ch_ua_platform,
        "sec_ch_ua_full_version_list": BROWSER_FINGERPRINT.sec_ch_ua_full_version_list,
        "sec_ch_ua_platform_version": '"15.7.0"',
        "sec_ch_ua_arch": '"arm"',
        "sec_ch_ua_bitness": '"64"',
        "sec_ch_ua_model": '""',
        "window_feature_flags": {"requestIdleCallback": 0},
    }
    return SentinelRuntimeContext(
        country_code=country,
        sentinel_sid=str(uuid.uuid4()),
        react_listening_key=f"_reactListening{uuid.uuid4().hex[:12]}",
        react_container_key=react_container_key,
        react_resources_key=f"__reactResources${suffix}",
        browser_profile=profile,
    )


def bind_sentinel_runtime_context(
    session: Any,
    *,
    country_code: str = "",
    context: SentinelRuntimeContext | dict[str, Any] | None = None,
) -> SentinelRuntimeContext:
    existing = getattr(session, _SESSION_CONTEXT_ATTR, None)
    if isinstance(existing, SentinelRuntimeContext):
        return existing
    if isinstance(context, dict):
        context = SentinelRuntimeContext.from_dict(context)
    resolved = context or create_sentinel_runtime_context(country_code)
    setattr(session, _SESSION_CONTEXT_ATTR, resolved)
    return resolved


def get_sentinel_runtime_context(session: Any) -> SentinelRuntimeContext:
    return bind_sentinel_runtime_context(
        session,
        country_code=str(getattr(session, "_openai_sentinel_country_code", "") or ""),
    )


def _resolve_node_binary() -> str:
    configured = (
        os.getenv("OPENAI_SENTINEL_NODE_PATH", "") or os.getenv("NODE_EXECUTABLE", "") or ""
    ).strip()
    if configured:
        return configured
    system_node = shutil.which("node")
    if system_node:
        return system_node
    nvm_dir = Path((os.getenv("NVM_DIR", "") or "").strip() or Path.home() / ".nvm")
    candidates = [
        candidate
        for candidate in (nvm_dir / "versions" / "node").glob("*/bin/node")
        if candidate.is_file() and os.access(candidate, os.X_OK)
    ]
    if candidates:
        return str(max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns))
    return "node"


def _runner_script_path() -> Path:
    return Path(__file__).resolve().parent / "sentinel_runner.js"


def _is_complete_sdk_bundle(content: bytes) -> bool:
    return len(content) >= MIN_SENTINEL_SDK_BYTES and all(
        marker in content
        for marker in (b"var SentinelSDK=", b"getRequirementsToken", b"getEnforcementToken")
    )


def _ensure_sdk_file(session: Any, timeout_ms: int) -> Path:
    cache_dir = Path(tempfile.gettempdir()) / "openai-sentinel-demo" / SENTINEL_VERSION
    cache_dir.mkdir(parents=True, exist_ok=True)
    sdk_file = cache_dir / "sdk.js"
    if sdk_file.exists():
        try:
            cached_content = sdk_file.read_bytes()
        except OSError:
            cached_content = b""
        if _is_complete_sdk_bundle(cached_content):
            return sdk_file
        logger.warning(
            "Sentinel SDK cache is invalid; downloading again: path=%s bytes=%s",
            sdk_file,
            len(cached_content),
        )

    resp = session.get(
        SENTINEL_SDK_URL,
        headers={
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "referer": "https://auth.openai.com/",
            "user-agent": DEFAULT_UA,
            "sec-ch-ua": DEFAULT_SEC_CH_UA,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": BROWSER_FINGERPRINT.sec_ch_ua_platform,
            "sec-fetch-dest": "script",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-site": "same-site",
        },
        timeout=max(10, int(timeout_ms / 1000)),
    )
    if getattr(resp, "status_code", 0) != 200:
        raise RuntimeError(f"download sdk.js failed: HTTP {resp.status_code}")
    content = getattr(resp, "content", b"") or (resp.text or "").encode()
    if isinstance(content, str):
        content = content.encode()
    if not _is_complete_sdk_bundle(content):
        raise RuntimeError(f"downloaded sdk.js is incomplete (bytes={len(content)})")
    temp_file = cache_dir / f".sdk-{uuid.uuid4().hex}.tmp"
    try:
        temp_file.write_bytes(content)
        temp_file.replace(sdk_file)
    finally:
        temp_file.unlink(missing_ok=True)
    return sdk_file


def _ensure_oai_did_cookies(session: Any, device_id: str) -> None:
    jar = getattr(session, "cookies", None)
    if jar is None:
        return
    for domain in ("chatgpt.com", "auth.openai.com", "sentinel.openai.com"):
        try:
            jar.set("oai-did", device_id, domain=domain, path="/")
        except Exception:
            continue


def _cookie_header_for_domain(session: Any, domain: str, device_id: str) -> str:
    jar = getattr(session, "cookies", None)
    raw_jar = getattr(jar, "jar", jar)
    wanted = domain.lower().lstrip(".")
    pairs: dict[str, str] = {}
    try:
        cookies = list(raw_jar)
    except Exception:
        cookies = []
    for cookie in cookies:
        name = str(getattr(cookie, "name", "") or "").strip()
        value = str(getattr(cookie, "value", "") or "")
        cookie_domain = str(getattr(cookie, "domain", "") or "").lower().lstrip(".")
        if not name:
            continue
        if cookie_domain and not (
            wanted == cookie_domain
            or wanted.endswith(f".{cookie_domain}")
            or cookie_domain.endswith(f".{wanted}")
        ):
            continue
        pairs[name] = value
    pairs["oai-did"] = device_id
    return "; ".join(f"{name}={value}" for name, value in pairs.items())


def _generate_requirements_token(context: SentinelRuntimeContext) -> str:
    profile = context.browser_profile
    offset_minutes = int(profile["timezone_offset_minutes"])
    local_now = datetime.now(timezone(timedelta(minutes=offset_minutes)))
    sign = "+" if offset_minutes >= 0 else "-"
    absolute_offset = abs(offset_minutes)
    gmt = f"GMT{sign}{absolute_offset // 60:02d}{absolute_offset % 60:02d}"
    date_text = local_now.strftime(f"%a %b %d %Y %H:%M:%S {gmt} ({profile['timezone_name']})")
    perf_now = random.uniform(1_000, 8_000)
    time_origin = time.time() * 1000 - perf_now
    document_keys = [
        *_DOCUMENT_KEY_SAMPLES,
        context.react_listening_key,
        context.react_container_key,
        context.react_resources_key,
    ]
    flags = dict(profile.get("window_feature_flags") or {})
    config = [
        int(profile["screen_width"]) + int(profile["screen_height"]),
        date_text,
        int(profile["js_heap_size_limit"]),
        1,
        str(profile["user_agent"]),
        SENTINEL_SDK_URL,
        None,
        str(profile["navigator_language"]),
        ",".join(profile["navigator_languages"]),
        random.randint(1, 100),
        random.choice(_NAVIGATOR_PROTO_SAMPLES),
        random.choice(document_keys),
        random.choice(_WINDOW_KEY_SAMPLES),
        round(perf_now, 10),
        context.sentinel_sid,
        "",
        int(profile["hardware_concurrency"]),
        round(time_origin, 1),
        int(flags.get("ai", 0)),
        int(flags.get("InstallTrigger", 0)),
        int(flags.get("cache", 0)),
        int(flags.get("data", 0)),
        int(flags.get("solana", 0)),
        int(flags.get("dump", 0)),
        int(flags.get("requestIdleCallback", 0)),
    ]
    encoded = base64.b64encode(
        json.dumps(config, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return f"gAAAAAC{encoded}~S"


def _fetch_sentinel_challenge(
    session: Any,
    *,
    device_id: str,
    flow: str,
    request_p: str,
    context: SentinelRuntimeContext,
    timeout_ms: int,
) -> dict[str, Any]:
    profile = context.browser_profile
    body = {"p": request_p, "id": device_id, "flow": flow}
    resp = session.post(
        SENTINEL_REQ_URL,
        data=json.dumps(body, separators=(",", ":")),
        headers={
            "origin": "https://sentinel.openai.com",
            "referer": (
                f"https://sentinel.openai.com/backend-api/sentinel/frame.html?sv={SENTINEL_VERSION}"
            ),
            "content-type": "text/plain;charset=UTF-8",
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": str(profile["accept_language"]),
            "user-agent": str(profile["user_agent"]),
            "sec-ch-ua": str(profile["sec_ch_ua"]),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": str(profile["sec_ch_ua_platform"]),
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "oai-device-id": device_id,
            "priority": "u=1, i",
        },
        timeout=max(10, int(timeout_ms / 1000)),
    )
    if getattr(resp, "status_code", 0) != 200:
        raise RuntimeError(f"/sentinel/req HTTP {resp.status_code}")
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Sentinel challenge response is not a JSON object")
    if not str(payload.get("token") or "").strip():
        raise RuntimeError("Sentinel challenge token is empty")
    return payload


def _run_sentinel_runner(
    *,
    challenge: dict[str, Any],
    sdk_file: Path,
    device_id: str,
    flow: str,
    page_url: str,
    cookie: str,
    context: SentinelRuntimeContext,
    timeout_ms: int,
    request_p: str = "",
) -> str:
    runner = _runner_script_path()
    if not runner.is_file():
        raise RuntimeError(f"sentinel_runner.js is missing: {runner}")
    profile = context.browser_profile
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix=f"sentinel-challenge-{flow}-",
        delete=False,
        encoding="utf-8",
    ) as challenge_file:
        json.dump(challenge, challenge_file, ensure_ascii=False)
        challenge_path = Path(challenge_file.name)

    cmd = [
        _resolve_node_binary(),
        str(runner),
        "--challenge-file",
        str(challenge_path),
        "--flow",
        flow,
        "--device-id",
        device_id,
        "--sentinel-sid",
        context.sentinel_sid,
        "--react-listening-key",
        context.react_listening_key,
        "--react-container-key",
        context.react_container_key,
        "--react-resources-key",
        context.react_resources_key,
        "--page-url",
        page_url,
        "--user-agent",
        str(profile["user_agent"]),
        "--browser-family",
        str(profile["browser_family"]),
        "--navigator-platform",
        str(profile["navigator_platform"]),
        "--navigator-vendor",
        str(profile["navigator_vendor"]),
        "--user-agent-data-platform",
        str(profile["user_agent_data_platform"]),
        "--request-idle-callback",
        "1" if profile["window_feature_flags"].get("requestIdleCallback") else "0",
        "--sdk",
        str(sdk_file),
        "--script-src",
        SENTINEL_SDK_URL,
        "--width",
        str(profile["screen_width"]),
        "--height",
        str(profile["screen_height"]),
        "--cores",
        str(profile["hardware_concurrency"]),
        "--language",
        str(profile["navigator_language"]),
        "--languages",
        ",".join(profile["navigator_languages"]),
        "--time-zone",
        str(profile["timezone_iana"]),
        "--timezone-name",
        str(profile["timezone_name"]),
        "--timezone-offset-minutes",
        str(profile["timezone_offset_minutes"]),
        "--js-heap-size-limit",
        str(profile["js_heap_size_limit"]),
        "--device-memory",
        str(profile["device_memory"]),
        "--device-pixel-ratio",
        str(profile["device_pixel_ratio"]),
        "--chrome-major",
        str(profile["chrome_major"]),
        "--chrome-full-version",
        str(profile["chrome_full_version"]),
        "--sec-ch-ua",
        str(profile["sec_ch_ua"]),
        "--sec-ch-ua-platform",
        str(profile["sec_ch_ua_platform"]),
        "--sec-ch-ua-full-version-list",
        str(profile["sec_ch_ua_full_version_list"]),
        "--sec-ch-ua-platform-version",
        str(profile["sec_ch_ua_platform_version"]),
        "--sec-ch-ua-arch",
        str(profile["sec_ch_ua_arch"]),
        "--sec-ch-ua-bitness",
        str(profile["sec_ch_ua_bitness"]),
        "--sec-ch-ua-model",
        str(profile["sec_ch_ua_model"]),
        "--cookie",
        cookie,
    ]
    if request_p:
        cmd.extend(["--request-p", request_p])
    env = os.environ.copy()
    env["SENTINEL_CONFIG"] = "__none__"
    env["TZ"] = str(profile["timezone_iana"])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(runner.parent),
            timeout=max(10, int(timeout_ms / 1000) + 5),
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"sentinel_runner.js timed out for flow={flow}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(f"Node executable was not found: {_resolve_node_binary()}") from exc
    finally:
        challenge_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown error").strip()[:1000]
        raise RuntimeError(f"sentinel_runner.js exited {proc.returncode}: {detail}")
    token_text = (proc.stdout or "").strip()
    if not token_text:
        raise RuntimeError("sentinel_runner.js returned empty output")
    try:
        token = json.loads(token_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"sentinel_runner.js returned invalid JSON: {token_text[:200]}") from exc
    if not isinstance(token, dict):
        raise RuntimeError("sentinel_runner.js output is not a JSON object")
    for key in ("p", "c", "id", "flow"):
        if not str(token.get(key) or "").strip():
            raise RuntimeError(f"sentinel_runner.js output is missing {key}: {token_text[:500]}")
    if str(token["id"]) != device_id or str(token["flow"]) != flow:
        raise RuntimeError("sentinel_runner.js output does not match device_id/flow")
    if str(token["c"]) != str(challenge.get("token") or ""):
        raise RuntimeError("sentinel_runner.js output does not match challenge token")
    so_challenge = challenge.get("so")
    if (
        isinstance(so_challenge, dict)
        and bool(so_challenge.get("required"))
        and not str(token.get("so") or "").strip()
    ):
        raise RuntimeError(
            "sentinel_runner.js output is missing required Session Observer token"
        )
    return json.dumps(token, ensure_ascii=False, separators=(",", ":"))


def get_sentinel_tokens_via_quickjs(
    session: Any,
    device_id: str,
    *,
    flow: str = "authorize_continue",
    timeout_ms: int = 45_000,
    log: Optional[Callable[[str], None]] = None,
) -> tuple[str, str]:
    """Return real-SDK Sentinel and optional SO headers or raise with the exact failure."""

    emit = log or (lambda message: logger.info(message))
    did = str(device_id or "").strip()
    if not did:
        raise ValueError("device_id is required")
    context = get_sentinel_runtime_context(session)
    _ensure_oai_did_cookies(session, did)
    sdk_file = _ensure_sdk_file(session, timeout_ms)
    request_p = _generate_requirements_token(context)
    challenge = _fetch_sentinel_challenge(
        session,
        device_id=did,
        flow=flow,
        request_p=request_p,
        context=context,
        timeout_ms=timeout_ms,
    )
    page_url = _FLOW_PAGE_URL.get(flow, "https://auth.openai.com/create-account/password")
    token_text = _run_sentinel_runner(
        challenge=challenge,
        sdk_file=sdk_file,
        device_id=did,
        flow=flow,
        page_url=page_url,
        cookie=_cookie_header_for_domain(session, "auth.openai.com", did),
        context=context,
        timeout_ms=timeout_ms,
        request_p=request_p,
    )
    parsed = json.loads(token_text)
    so_token = ""
    if parsed.get("so"):
        so_token = json.dumps(
            {
                "so": parsed["so"],
                "c": parsed["c"],
                "id": did,
                "flow": flow,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    emit(
        "Sentinel real SDK succeeded "
        f"flow={flow} country={context.country_code} "
        f"p_len={len(str(parsed.get('p') or ''))} "
        f"t_len={len(str(parsed.get('t') or ''))} so_len={len(so_token)}"
    )
    return token_text, so_token


def get_sentinel_token_via_quickjs(
    session: Any,
    device_id: str,
    *,
    flow: str = "authorize_continue",
    timeout_ms: int = 45_000,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    return get_sentinel_tokens_via_quickjs(
        session,
        device_id=device_id,
        flow=flow,
        timeout_ms=timeout_ms,
        log=log,
    )[0]
