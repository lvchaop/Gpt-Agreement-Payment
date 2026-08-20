"""
OpenAI Sentinel Token 生成（纯 Python 方案）。

集成自 https://github.com/zc-zhangchen/any-auto-register
（platforms/chatgpt/sentinel_token.py，MIT License）。

旧实现见 sentinel_v1_legacy.py：先在本地 SHA3-512 算 PoW 再发，被 OpenAI 服务端
silent-drop（200 OK 但不下发 OTP）。新实现的关键区别：
  1. 第一次 POST /sentinel/req 发 `requirements_token`（不带真 PoW），仅声明
     config schema。
  2. 服务端返回 `{token, proofofwork: {required, seed, difficulty}}`，
     我们用 **服务端给的 seed/difficulty** 跑 FNV-1a 32-bit PoW。
  3. 第二次 PoW 解出来的 token 拼进 `{p, t:"", c: server_token, id, flow}` 才合法。
  4. SDK 版本字符串从旧的 `prod-f501fe...` 升级到当前的
     `https://sentinel.openai.com/sentinel/20260124ceb8/sdk.js`。

公开 API `get_sentinel_token(session, device_id, flow, user_agent)` 保持不变，
auth_flow.py 的 4 处调用点不需要改。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from refactor_app.config.browser_fingerprint import (
    BROWSER_SEC_CH_UA,
    BROWSER_SEC_CH_UA_PLATFORM,
    BROWSER_USER_AGENT,
)

from .sentinel_quickjs import SentinelRuntimeContext, get_sentinel_runtime_context

logger = logging.getLogger(__name__)


SENTINEL_REQ_URL = "https://sentinel.openai.com/backend-api/sentinel/req"
SENTINEL_VERSION = "20260219f9f6"
SENTINEL_REFERER = (
    f"https://sentinel.openai.com/backend-api/sentinel/frame.html?sv={SENTINEL_VERSION}"
)
SENTINEL_SDK_URL = "https://sentinel.openai.com/backend-api/sentinel/sdk.js"

DEFAULT_UA = BROWSER_USER_AGENT
DEFAULT_SEC_CH_UA = BROWSER_SEC_CH_UA
_CHECKOUT_FLOW = "checkout_session_approval"


def _require_checkout_page_url(flow: str, page_url: str | None) -> None:
    if flow == _CHECKOUT_FLOW and not str(page_url or "").strip():
        raise ValueError("page_url is required for checkout_session_approval")


class SentinelTokenGenerator:
    """Sentinel Token 纯 Python 生成器。

    - 不依赖 Node / JS。
    - `t` 字段固定空串；上游接口（`/sentinel/req`）的返回会判定能否接受。
    """

    MAX_ATTEMPTS = 500000
    ERROR_PREFIX = "wQ8Lk5FbGpA2NcR9dShT6gYjU7VxZ4D"

    def __init__(
        self,
        device_id: str | None = None,
        user_agent: str | None = None,
        *,
        runtime_context: SentinelRuntimeContext,
    ):
        self.device_id = device_id or str(uuid.uuid4())
        self.runtime_context = runtime_context
        self.user_agent = (
            user_agent
            or str(runtime_context.browser_profile.get("user_agent") or "")
            or DEFAULT_UA
        )
        self.requirements_seed = str(random.random())
        self.sid = str(uuid.uuid4())

    @staticmethod
    def _fnv1a_32(text: str) -> str:
        h = 2166136261
        for ch in text:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        h ^= h >> 16
        h = (h * 2246822507) & 0xFFFFFFFF
        h ^= h >> 13
        h = (h * 3266489909) & 0xFFFFFFFF
        h ^= h >> 16
        return format(h & 0xFFFFFFFF, "08x")

    def _get_config(self) -> list:
        profile = self.runtime_context.browser_profile
        offset_minutes = int(profile["timezone_offset_minutes"])
        now = datetime.now(timezone(timedelta(minutes=offset_minutes)))
        sign = "+" if offset_minutes >= 0 else "-"
        absolute_offset = abs(offset_minutes)
        gmt = f"GMT{sign}{absolute_offset // 60:02d}{absolute_offset % 60:02d}"
        date_str = now.strftime(
            f"%a %b %d %Y %H:%M:%S {gmt} ({profile['timezone_name']})"
        )
        perf_now = random.uniform(1000, 50000)
        time_origin = time.time() * 1000 - perf_now
        nav_prop = random.choice(
            [
                "vendorSub",
                "productSub",
                "vendor",
                "maxTouchPoints",
                "scheduling",
                "userActivation",
                "doNotTrack",
                "geolocation",
                "connection",
                "plugins",
                "mimeTypes",
                "pdfViewerEnabled",
                "webkitTemporaryStorage",
                "webkitPersistentStorage",
                "hardwareConcurrency",
                "cookieEnabled",
                "credentials",
                "mediaDevices",
                "permissions",
                "locks",
                "ink",
            ]
        )
        return [
            "1920x1080",
            date_str,
            4294705152,
            random.random(),
            self.user_agent,
            SENTINEL_SDK_URL,
            None,
            str(profile["navigator_language"]),
            ",".join(profile["navigator_languages"]),
            random.random(),
            f"{nav_prop}−undefined",
            random.choice(["location", "implementation", "URL", "documentURI", "compatMode"]),
            random.choice(["Object", "Function", "Array", "Number", "parseFloat", "undefined"]),
            perf_now,
            self.sid,
            "",
            random.choice([4, 8, 12, 16]),
            time_origin,
        ]

    @staticmethod
    def _base64_encode(data) -> str:
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")

    def _run_check(self, start_time, seed, difficulty, config, nonce):
        config[3] = nonce
        config[9] = round((time.time() - start_time) * 1000)
        encoded = self._base64_encode(config)
        digest = self._fnv1a_32(seed + encoded)
        if digest[: len(difficulty)] <= difficulty:
            return encoded + "~S"
        return None

    def generate_token(self, seed: str | None = None, difficulty: str | None = None) -> str:
        seed = seed or self.requirements_seed
        difficulty = difficulty or "0"
        start_time = time.time()
        config = self._get_config()
        for nonce in range(self.MAX_ATTEMPTS):
            value = self._run_check(start_time, seed, difficulty, config, nonce)
            if value:
                return "gAAAAAB" + value
        return "gAAAAAB" + self.ERROR_PREFIX + self._base64_encode(str(None))

    def generate_requirements_token(self) -> str:
        config = self._get_config()
        config[3] = 1
        config[9] = round(random.uniform(5, 50))
        return "gAAAAAC" + self._base64_encode(config)


def fetch_sentinel_challenge(
    session,
    device_id: str,
    flow: str = "authorize_continue",
    user_agent: str | None = None,
    sec_ch_ua: str | None = None,
    impersonate: str | None = None,
    request_p: str | None = None,
) -> dict | None:
    """POST `/sentinel/req` 并返回响应 JSON。失败返回 None。"""
    runtime_context = get_sentinel_runtime_context(session)
    profile = runtime_context.browser_profile
    generator = SentinelTokenGenerator(
        device_id=device_id,
        user_agent=user_agent,
        runtime_context=runtime_context,
    )
    req_body = {
        "p": str(request_p or "").strip() or generator.generate_requirements_token(),
        "id": device_id,
        "flow": flow,
    }
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": str(runtime_context.browser_profile["accept_language"]),
        "Referer": SENTINEL_REFERER,
        "Origin": "https://sentinel.openai.com",
        "User-Agent": user_agent or str(profile.get("user_agent") or DEFAULT_UA),
        "sec-ch-ua": sec_ch_ua or str(profile.get("sec_ch_ua") or DEFAULT_SEC_CH_UA),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": str(
            profile.get("sec_ch_ua_platform") or BROWSER_SEC_CH_UA_PLATFORM
        ),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    kwargs = {"data": json.dumps(req_body), "headers": headers, "timeout": 20}
    if impersonate:
        kwargs["impersonate"] = impersonate
    try:
        response = session.post(SENTINEL_REQ_URL, **kwargs)
        body_preview = (
            (getattr(response, "text", "") or "").replace("\n", " ").replace("\r", " ")[:500]
        )
        logger.debug(
            "[SENTINEL DEBUG] python /req flow=%s status=%s p_len=%s body=%s",
            flow,
            getattr(response, "status_code", "N/A"),
            len(str(req_body.get("p") or "")),
            body_preview,
        )
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                pow_data = payload.get("proofofwork") or {}
                logger.debug(
                    "[SENTINEL DEBUG] python /req parsed token_len=%s pow_required=%s pow_seed_len=%s difficulty=%s",
                    len(str(payload.get("token") or "")),
                    bool(pow_data.get("required")),
                    len(str(pow_data.get("seed") or "")),
                    str(pow_data.get("difficulty") or ""),
                )
            return payload
        logger.warning(f"Sentinel /req 非 200: {response.status_code}")
    except Exception as exc:
        logger.warning(f"Sentinel /req 异常: {exc}")
        return None
    return None


def build_sentinel_token(
    session,
    device_id: str,
    flow: str = "authorize_continue",
    user_agent: str | None = None,
    sec_ch_ua: str | None = None,
    impersonate: str | None = None,
) -> str | None:
    """完整 Sentinel token：fetch challenge → 用 server-given seed/difficulty 解 PoW → 拼装。

    返回 JSON 字符串，失败返回 None。
    """
    challenge = fetch_sentinel_challenge(
        session,
        device_id,
        flow=flow,
        user_agent=user_agent,
        sec_ch_ua=sec_ch_ua,
        impersonate=impersonate,
    )
    if not challenge:
        logger.debug("[SENTINEL DEBUG] python build_sentinel_token no challenge flow=%s", flow)
        return None

    c_value = str(challenge.get("token") or "").strip()
    if not c_value:
        logger.debug(
            "[SENTINEL DEBUG] python challenge missing token flow=%s keys=%s",
            flow,
            sorted(challenge.keys()),
        )
        return None

    generator = SentinelTokenGenerator(
        device_id=device_id,
        user_agent=user_agent,
        runtime_context=get_sentinel_runtime_context(session),
    )
    pow_data = challenge.get("proofofwork") or {}
    if pow_data.get("required") and pow_data.get("seed"):
        p_value = generator.generate_token(
            seed=pow_data.get("seed"),
            difficulty=pow_data.get("difficulty", "0"),
        )
    else:
        p_value = generator.generate_requirements_token()

    payload = {
        "p": p_value,
        "t": "",
        "c": c_value,
        "id": device_id,
        "flow": flow,
    }
    return json.dumps(payload, separators=(",", ":"))


def build_sentinel_tokens(
    session,
    device_id: str,
    flow: str = "authorize_continue",
    user_agent: str | None = None,
    sec_ch_ua: str | None = None,
    impersonate: str | None = None,
) -> tuple[str, str] | None:
    """完整 Sentinel token + 可选 so-token。"""
    challenge = fetch_sentinel_challenge(
        session,
        device_id,
        flow=flow,
        user_agent=user_agent,
        sec_ch_ua=sec_ch_ua,
        impersonate=impersonate,
    )
    if not challenge:
        logger.debug("[SENTINEL DEBUG] python build_sentinel_tokens no challenge flow=%s", flow)
        return None

    c_value = str(challenge.get("token") or "").strip()
    if not c_value:
        logger.debug(
            "[SENTINEL DEBUG] python challenge missing token flow=%s keys=%s",
            flow,
            sorted(challenge.keys()),
        )
        return None

    generator = SentinelTokenGenerator(
        device_id=device_id,
        user_agent=user_agent,
        runtime_context=get_sentinel_runtime_context(session),
    )
    pow_data = challenge.get("proofofwork") or {}
    if pow_data.get("required") and pow_data.get("seed"):
        p_value = generator.generate_token(
            seed=pow_data.get("seed"),
            difficulty=pow_data.get("difficulty", "0"),
        )
    else:
        p_value = generator.generate_requirements_token()

    token = json.dumps(
        {"p": p_value, "t": "", "c": c_value, "id": device_id, "flow": flow},
        separators=(",", ":"),
    )
    so_token = ""
    return token, so_token


def get_sentinel_token(
    session,
    device_id: str,
    flow: str = "authorize_continue",
    user_agent: str | None = None,
    page_url: str | None = None,
) -> str:
    """Generate a real-SDK token; synthetic fallback is explicit and off by default."""
    _require_checkout_page_url(flow, page_url)
    disabled = _env_enabled("OPENAI_SENTINEL_DISABLE_QUICKJS")
    allow_synthetic = _env_enabled("OPENAI_SENTINEL_ALLOW_SYNTHETIC_FALLBACK")
    if not disabled:
        try:
            from .sentinel_quickjs import get_sentinel_token_via_quickjs

            qtoken = get_sentinel_token_via_quickjs(
                session,
                device_id=device_id,
                flow=flow,
                page_url=page_url,
                log=lambda m: logger.info(m),
            )
            if qtoken:
                logger.info(f"Sentinel Token 组装完成 (QuickJS 长度: {len(qtoken)})")
                return qtoken
        except Exception as e:
            if not allow_synthetic:
                raise RuntimeError(f"Sentinel real SDK failed: {e}") from e
            logger.warning("Sentinel real SDK failed; explicit synthetic fallback enabled: %s", e)
    elif not allow_synthetic:
        raise RuntimeError(
            "OPENAI_SENTINEL_DISABLE_QUICKJS requires OPENAI_SENTINEL_ALLOW_SYNTHETIC_FALLBACK=1"
        )

    token = build_sentinel_token(
        session,
        device_id=device_id,
        flow=flow,
        user_agent=user_agent,
    )
    if token:
        logger.info(f"Sentinel Token 组装完成 (纯 Python 长度: {len(token)})")
        return token

    logger.warning("Sentinel synthetic /req failed; using explicit no-challenge fallback")
    fallback_p = SentinelTokenGenerator(
        device_id=device_id,
        user_agent=user_agent,
        runtime_context=get_sentinel_runtime_context(session),
    ).generate_requirements_token()
    return json.dumps(
        {
            "p": fallback_p,
            "t": "",
            "c": "",
            "id": device_id,
            "flow": flow,
        },
        separators=(",", ":"),
    )


def get_sentinel_tokens(
    session,
    device_id: str,
    flow: str = "authorize_continue",
    user_agent: str | None = None,
    initialize_first: bool = False,
    page_url: str | None = None,
) -> tuple[str, str]:
    """Return real-SDK Sentinel headers; synthetic fallback is opt-in only."""
    _require_checkout_page_url(flow, page_url)
    disabled = _env_enabled("OPENAI_SENTINEL_DISABLE_QUICKJS")
    allow_synthetic = _env_enabled("OPENAI_SENTINEL_ALLOW_SYNTHETIC_FALLBACK")
    if not disabled:
        try:
            from .sentinel_quickjs import get_sentinel_tokens_via_quickjs

            qtokens = get_sentinel_tokens_via_quickjs(
                session,
                device_id=device_id,
                flow=flow,
                initialize_first=initialize_first,
                page_url=page_url,
                log=lambda m: logger.info(m),
            )
            if qtokens:
                token, so_token = qtokens
                logger.info(
                    "Sentinel Token 组装完成 (QuickJS token长度=%s so长度=%s)",
                    len(token or ""),
                    len(so_token or ""),
                )
                return token or "", so_token or ""
        except Exception as e:
            if not allow_synthetic:
                raise RuntimeError(f"Sentinel real SDK failed: {e}") from e
            logger.warning("Sentinel real SDK failed; explicit synthetic fallback enabled: %s", e)
    elif not allow_synthetic:
        raise RuntimeError(
            "OPENAI_SENTINEL_DISABLE_QUICKJS requires OPENAI_SENTINEL_ALLOW_SYNTHETIC_FALLBACK=1"
        )

    tokens = build_sentinel_tokens(
        session,
        device_id=device_id,
        flow=flow,
        user_agent=user_agent,
    )
    if tokens:
        token, so_token = tokens
        logger.info(
            "Sentinel Token 组装完成 (纯 Python token长度=%s so长度=%s)",
            len(token or ""),
            len(so_token or ""),
        )
        return token or "", so_token or ""

    logger.warning("Sentinel synthetic /req failed; using explicit no-challenge fallback")
    fallback_p = SentinelTokenGenerator(
        device_id=device_id,
        user_agent=user_agent,
        runtime_context=get_sentinel_runtime_context(session),
    ).generate_requirements_token()
    return json.dumps(
        {
            "p": fallback_p,
            "t": "",
            "c": "",
            "id": device_id,
            "flow": flow,
        },
        separators=(",", ":"),
    ), ""


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}
