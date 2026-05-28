"""Phone number provider used by the phone-browser registration lane.

The provider is deliberately small and HTTP-shape based:

- allocate() reserves a number only after the page is already on the phone form.
- poll_otp() waits for the SMS OTP tied to the lease id.
- mark_verified()/mark_failed()/release() report lifecycle state back upstream.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, build_opener

logger = logging.getLogger(__name__)

_JSON_PROVIDERS = {"http", "json", "http_json"}
_HERO_SMS_PROVIDERS = {
    "hero",
    "hero_sms",
    "hero-sms",
    "sms_hub",
    "smshub",
    "sms-activate",
    "sms_activate",
    "smsactivate",
}
_MAX_OTP_WAIT_S = 120
_DEFAULT_STALE_CANCEL_AFTER_S = 240


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _hero_lease_log_path() -> Path:
    raw = str(os.getenv("HERO_PHONE_LEASE_LOG") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return _project_root() / "output" / "hero_phone_leases.jsonl"


def _append_hero_lease_event(event: dict) -> None:
    try:
        path = _hero_lease_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(event)
        payload.setdefault("ts", time.time())
        payload.setdefault("pid", os.getpid())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as e:
        logger.warning("Hero SMS lease event write failed: %s", e)


def _hero_lease_is_closed(lease_id: str) -> bool:
    path = _hero_lease_log_path()
    if not path.exists():
        return False
    latest_status = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if str(row.get("lease_id") or "") != str(lease_id):
                    continue
                latest_status = str(row.get("status") or "")
    except Exception as e:
        logger.warning("Hero SMS lease event read failed lease=%s: %s", lease_id, e)
        return False
    return latest_status in {"closed", "verified", "cancelled", "canceled"}


def _normalize_provider(provider: str) -> str:
    value = str(provider or "http").strip().lower()
    if value in _JSON_PROVIDERS:
        return "http"
    if value in _HERO_SMS_PROVIDERS:
        return "hero_sms"
    return value


@dataclass
class PhoneLease:
    lease_id: str
    phone_e164: str
    masked_phone: str = ""
    phone_national: str = ""
    country_phone_code: str = ""
    provider_country: str = ""
    expires_at: Any = None
    raw: dict | None = None


class PhoneProvider:
    def __init__(self, cfg):
        self.cfg = cfg
        self.base_url = str(getattr(cfg, "base_url", "") or "").rstrip("/")
        self.provider = _normalize_provider(getattr(cfg, "provider", "") or "http")
        self.timeout_s = int(getattr(cfg, "request_timeout_s", 20) or 20)
        self.opener = build_opener()
        self.api_key = (
            str(getattr(cfg, "api_key", "") or "").strip()
            or str(os.getenv(str(getattr(cfg, "api_key_env", "") or "PHONE_PROVIDER_API_KEY")) or "").strip()
        )
        self.extra_headers = getattr(cfg, "headers", {}) or {}

    @classmethod
    def from_config(cls, cfg) -> "PhoneProvider":
        enabled = bool(getattr(cfg, "enabled", False))
        if not enabled:
            raise RuntimeError("phone.enabled=false；手机号注册需要启用 phone 配置")
        raw_provider = str(getattr(cfg, "provider", "") or "http").strip().lower()
        provider = _normalize_provider(raw_provider)
        if provider not in ("http", "hero_sms"):
            raise RuntimeError(f"不支持的 phone.provider={raw_provider!r}（当前支持 http / hero_sms）")
        if not str(getattr(cfg, "base_url", "") or "").strip():
            raise RuntimeError("phone.base_url 未配置")
        if provider == "hero_sms":
            api_key = (
                str(getattr(cfg, "api_key", "") or "").strip()
                or str(os.getenv(str(getattr(cfg, "api_key_env", "") or "PHONE_PROVIDER_API_KEY")) or "").strip()
            )
            if not api_key:
                raise RuntimeError("Hero SMS 需要 phone.api_key 或 phone.api_key_env 指向可用环境变量")
        return cls(cfg)

    def _url(self, path: str) -> str:
        path = str(path or "").strip()
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path:
            return self.base_url
        if path.startswith("?"):
            return f"{self.base_url}{path}"
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _headers(self, *, accept: str = "application/json", json_body: bool = True, bearer_auth: bool = True) -> dict:
        headers = {
            "Accept": accept,
            # Hero SMS 文档给的是 curl；有些 API 网关会拒绝 Python-urllib 默认 UA。
            "User-Agent": "curl/8.7.1",
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        if bearer_auth and self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if isinstance(self.extra_headers, dict):
            headers.update({str(k): str(v) for k, v in self.extra_headers.items()})
        return headers

    @staticmethod
    def _truthy(value: Any) -> bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _redact_url(url: str) -> str:
        return re.sub(r"([?&]api_key=)[^&]+", r"\1<redacted>", str(url or ""))

    def _request_json(self, method: str, path: str, body: dict | None = None) -> dict:
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        url = self._url(path)
        req = Request(
            url,
            data=data,
            headers=self._headers(),
            method=method.upper(),
        )
        try:
            with self.opener.open(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"phone provider HTTP {e.code} url={self._redact_url(url)}: {raw[:300]}") from e
        if not raw.strip():
            return {}
        try:
            data_obj = json.loads(raw)
        except Exception as e:
            raise RuntimeError(f"phone provider 返回非 JSON: {raw[:300]}") from e
        if not isinstance(data_obj, dict):
            raise RuntimeError(f"phone provider JSON 顶层不是对象: {type(data_obj).__name__}")
        return data_obj

    def _request_text(self, method: str, path: str, body: dict | None = None) -> str:
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        url = self._url(path)
        req = Request(
            url,
            data=data,
            headers=self._headers(accept="*/*", json_body=body is not None, bearer_auth=False),
            method=method.upper(),
        )
        try:
            with self.opener.open(req, timeout=self.timeout_s) as resp:
                return resp.read().decode("utf-8", errors="replace").strip()
        except HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"phone provider HTTP {e.code} url={self._redact_url(url)}: {raw[:300]}") from e

    @staticmethod
    def _first_text(payload: dict, keys: tuple[str, ...]) -> str:
        for key in keys:
            val = payload.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for key in keys:
                val = data.get(key)
                if val is not None and str(val).strip():
                    return str(val).strip()
        return ""

    @staticmethod
    def _extract_otp6(value: Any) -> str:
        text = "" if value is None else str(value)
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        return (m.group(1) if m else "").strip()

    @staticmethod
    def _extract_otp_code(value: Any) -> str:
        text = "" if value is None else str(value)
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        if not m:
            m = re.search(r"(?<!\d)(\d{4,8})(?!\d)", text)
        return (m.group(1) if m else "").strip()

    @staticmethod
    def _mask_phone(phone: str) -> str:
        text = str(phone or "").strip()
        if len(text) <= 4:
            return text
        return f"{text[:2]}{'*' * max(2, len(text) - 4)}{text[-2:]}"

    @staticmethod
    def _hero_error(raw: str) -> str:
        text = str(raw or "").strip()
        hints = {
            "NO_NUMBERS": "没有可用号码",
            "NO_BALANCE": "余额不足",
            "BAD_KEY": "API key 无效",
            "BAD_ACTION": "action 参数无效",
            "BAD_SERVICE": "service 参数无效",
            "BAD_COUNTRY": "country 参数无效",
            "NO_ACTIVATION": "activation id 不存在或已过期",
            "STATUS_CANCEL": "号码租约已取消",
        }
        return f"{text}（{hints.get(text.upper(), 'Hero SMS 返回错误')}）"

    def _hero_query(self, action: str, **params: Any) -> str:
        if not self.api_key:
            raise RuntimeError("Hero SMS api_key 未配置")
        query = {"action": action, "api_key": self.api_key}
        for key, val in params.items():
            if val is None:
                continue
            text = str(val).strip()
            if text:
                query[key] = text
        return "?" + urlencode(query)

    def _hero_watchdog_enabled(self) -> bool:
        raw = getattr(self.cfg, "watchdog_enabled", True)
        if isinstance(raw, bool):
            return raw
        return self._truthy(raw)

    def _hero_stale_cancel_after_s(self) -> int:
        raw = int(getattr(self.cfg, "stale_cancel_after_s", _DEFAULT_STALE_CANCEL_AFTER_S) or _DEFAULT_STALE_CANCEL_AFTER_S)
        return max(30, raw)

    def _record_hero_lease_open(self, lease: PhoneLease) -> None:
        _append_hero_lease_event(
            {
                "event": "allocated",
                "status": "open",
                "lease_id": lease.lease_id,
                "phone": lease.masked_phone,
                "provider_country": lease.provider_country,
                "expires_at": str(lease.expires_at or ""),
            }
        )

    def _record_hero_lease_closed(self, lease_id: str, *, event: str, reason: str, ok: bool) -> None:
        _append_hero_lease_event(
            {
                "event": event,
                "status": "closed" if ok else "open",
                "lease_id": lease_id,
                "reason": reason,
                "ok": bool(ok),
            }
        )

    def _spawn_hero_cancel_watchdog(self, lease: PhoneLease) -> None:
        if self.provider != "hero_sms" or not self._hero_watchdog_enabled():
            return
        delay_s = self._hero_stale_cancel_after_s()
        env = dict(os.environ)
        env["HERO_WATCHDOG_API_KEY"] = self.api_key
        env["HERO_WATCHDOG_BASE_URL"] = self.base_url
        env["HERO_PHONE_LEASE_LOG"] = str(_hero_lease_log_path())
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--watchdog-cancel-lease",
            str(lease.lease_id),
            "--delay-s",
            str(delay_s),
        ]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
                env=env,
            )
            logger.info("Hero SMS stale cancel watchdog armed lease=%s delay=%ss", lease.lease_id, delay_s)
        except Exception as e:
            logger.warning("Hero SMS stale cancel watchdog start failed lease=%s: %s", lease.lease_id, e)

    @staticmethod
    def _split_list(value: Any) -> list[str]:
        if isinstance(value, (list, tuple, set)):
            items = value
        else:
            items = re.split(r"[\s,，;；]+", str(value or ""))
        return [str(item).strip() for item in items if str(item).strip()]

    @staticmethod
    def _normalize_price_map(value: Any) -> dict[str, str]:
        if isinstance(value, dict):
            return {
                str(k).strip(): str(v).strip()
                for k, v in value.items()
                if str(k).strip() and str(v).strip()
            }
        out: dict[str, str] = {}
        for part in re.split(r"[\n,，;；]+", str(value or "")):
            text = part.strip()
            if not text:
                continue
            if "=" in text:
                key, val = text.split("=", 1)
            elif ":" in text:
                key, val = text.split(":", 1)
            else:
                bits = text.split()
                if len(bits) < 2:
                    continue
                key, val = bits[0], bits[1]
            key = str(key).strip()
            val = str(val).strip()
            if key and val:
                out[key] = val
        return out

    def _hero_service_country(self) -> tuple[str, str]:
        service, countries = self._hero_service_countries()
        return service, countries[0]

    def _hero_service_countries(self) -> tuple[str, list[str]]:
        service = str(getattr(self.cfg, "service", "") or "tg").strip()
        countries = self._split_list(getattr(self.cfg, "countries", []) or [])
        if countries:
            random.shuffle(countries)
        else:
            countries = [str(getattr(self.cfg, "country", "") or "").strip()]
        if not service:
            raise RuntimeError("Hero SMS 需要 phone.service，例如 tg")
        bad = [country for country in countries if not country or not country.isdigit()]
        if bad:
            raise RuntimeError(f"Hero SMS 需要 phone.country/countries 填数字国家码，例如 2；当前={bad[0] or '<empty>'}")
        return service, countries

    def _hero_max_price(self, country: str = "") -> str:
        country_prices = self._normalize_price_map(getattr(self.cfg, "country_max_prices", {}) or {})
        if country and country_prices.get(str(country)):
            return country_prices[str(country)]
        return str(getattr(self.cfg, "maxPrice", "") or getattr(self.cfg, "max_price", "") or "").strip()

    def _hero_allocate_attempts(self, country_count: int) -> int:
        raw = int(getattr(self.cfg, "max_number_attempts", 3) or 3)
        return max(1, country_count, raw)

    @staticmethod
    def _hero_allocate_retryable_error(error: Exception | str) -> bool:
        text = str(error)
        retryable_tokens = (
            "HTTP 409",
            "URLERROR",
            "TLS/SSL",
            "CONNECTION HAS BEEN CLOSED",
            "CONNECTION RESET",
            "CONNECTION ABORTED",
            "EOF",
            "TIMED OUT",
            "TIMEOUT",
            "NO_NUMBERS",
            "BAD_COUNTRY",
            "BAD_SERVICE",
            "STATUS_WAIT",
            "TOO_MANY",
            "RATE_LIMIT",
            "TRY_AGAIN",
            "TEMP",
        )
        fatal_tokens = ("BAD_KEY", "NO_BALANCE")
        upper = text.upper()
        if any(token in upper for token in fatal_tokens):
            return False
        return any(token in upper for token in retryable_tokens)

    @staticmethod
    def _hero_status_retryable_error(error: Exception | str) -> bool:
        text = str(error)
        upper = text.upper()
        fatal_tokens = ("BAD_KEY", "BAD_ACTION", "STATUS_CANCEL", "NO_ACTIVATION")
        retryable_tokens = (
            "HTTP 409",
            "URLERROR",
            "TLS/SSL",
            "CONNECTION HAS BEEN CLOSED",
            "CONNECTION RESET",
            "CONNECTION ABORTED",
            "EOF",
            "TIMED OUT",
            "TIMEOUT",
            "STATUS_WAIT",
            "TRY_AGAIN",
            "RATE_LIMIT",
            "TEMP",
        )
        if any(token in upper for token in fatal_tokens):
            return False
        return any(token in upper for token in retryable_tokens)

    def _otp_timeout_s(self) -> int:
        raw = int(getattr(self.cfg, "otp_timeout_s", _MAX_OTP_WAIT_S) or _MAX_OTP_WAIT_S)
        timeout_s = max(1, min(raw, _MAX_OTP_WAIT_S))
        if raw > _MAX_OTP_WAIT_S:
            logger.info("phone OTP timeout capped at %ss (configured=%ss)", _MAX_OTP_WAIT_S, raw)
        return timeout_s

    @staticmethod
    def _hero_phone_parts(phone: str, country_phone_code: Any) -> tuple[str, str, str]:
        raw_phone = str(phone or "").strip()
        if not raw_phone:
            raise RuntimeError("Hero SMS getNumberV2 响应缺 phoneNumber")
        if "*" in raw_phone:
            raise RuntimeError("Hero SMS 返回的是脱敏手机号，无法提交到注册页；请确认接口实际返回完整 phoneNumber")
        country_code = re.sub(r"\D+", "", str(country_phone_code or ""))
        digits = re.sub(r"\D+", "", raw_phone)
        if not digits:
            raise RuntimeError(f"Hero SMS phoneNumber 无有效数字: {raw_phone}")
        national = digits
        if country_code:
            if national.startswith(country_code):
                national = national[len(country_code):]
            if national.startswith("0"):
                national = national[1:]
            e164_digits = f"{country_code}{national}"
        else:
            e164_digits = digits
        return f"+{e164_digits}", national, country_code

    def _allocate_hero_sms(self) -> PhoneLease:
        service, countries = self._hero_service_countries()
        attempts = self._hero_allocate_attempts(len(countries))
        last_error = ""
        for attempt in range(1, attempts + 1):
            country = countries[(attempt - 1) % len(countries)]
            max_price = self._hero_max_price(country)
            logger.info(
                "Hero SMS getNumberV2 attempt=%s/%s service=%s country=%s maxPrice=%s base_url=%s",
                attempt,
                attempts,
                service,
                country,
                max_price or "<empty>",
                self.base_url,
            )
            try:
                raw = self._request_text("GET", self._hero_query("getNumberV2", service=service, country=country, maxPrice=max_price))
            except Exception as e:
                last_error = str(e)
                if attempt < attempts and self._hero_allocate_retryable_error(e):
                    logger.warning(
                        "Hero SMS getNumberV2 可重试失败 attempt=%s/%s country=%s: %s",
                        attempt,
                        attempts,
                        country,
                        last_error[:220],
                    )
                    continue
                raise
            try:
                resp = json.loads(raw)
            except Exception as e:
                raise RuntimeError(f"Hero SMS getNumberV2 返回非 JSON: {self._hero_error(raw)}") from e
            if not isinstance(resp, dict):
                raise RuntimeError(f"Hero SMS getNumberV2 JSON 顶层不是对象: {type(resp).__name__}")
            if resp.get("error") or resp.get("message") in {"NO_NUMBERS", "NO_BALANCE", "BAD_KEY", "BAD_ACTION", "BAD_COUNTRY", "BAD_SERVICE"}:
                last_error = f"Hero SMS getNumberV2 失败: {resp}"
                if attempt < attempts and self._hero_allocate_retryable_error(last_error):
                    logger.warning(
                        "Hero SMS getNumberV2 可重试失败 attempt=%s/%s country=%s: %s",
                        attempt,
                        attempts,
                        country,
                        last_error[:220],
                    )
                    continue
                raise RuntimeError(last_error)
            lease_id = str(resp.get("activationId") or resp.get("activation_id") or "").strip()
            if not lease_id:
                raise RuntimeError(f"Hero SMS getNumberV2 响应缺 activationId: {resp}")
            phone_e164, phone_national, country_phone_code = self._hero_phone_parts(
                resp.get("phoneNumber") or resp.get("phone_number"),
                resp.get("countryPhoneCode"),
            )
            logger.info(
                "Hero SMS getNumberV2 success lease=%s provider_country=%s dial=+%s phone=%s expires=%s",
                lease_id,
                country,
                country_phone_code,
                self._mask_phone(phone_e164),
                resp.get("activationEndTime") or resp.get("activation_end_time") or "",
            )
            lease = PhoneLease(
                lease_id=lease_id,
                phone_e164=phone_e164,
                masked_phone=self._mask_phone(phone_e164),
                phone_national=phone_national,
                country_phone_code=country_phone_code,
                provider_country=country,
                expires_at=resp.get("activationEndTime") or resp.get("activation_end_time"),
                raw=resp,
            )
            self._record_hero_lease_open(lease)
            self._spawn_hero_cancel_watchdog(lease)
            return lease
        raise RuntimeError(f"Hero SMS getNumberV2 重试耗尽: {last_error or 'unknown'}")

    def _hero_status_v2_code(self, resp: dict) -> str:
        for section_name in ("sms", "call"):
            section = resp.get(section_name)
            if not isinstance(section, dict):
                continue
            code = self._extract_otp_code(section.get("code")) or self._extract_otp_code(section.get("text"))
            if code:
                return code
        return ""

    def _poll_hero_sms_otp(self, lease_id: str) -> str:
        timeout_s = self._otp_timeout_s()
        interval_s = float(getattr(self.cfg, "otp_poll_interval_s", 3.0) or 3.0)
        deadline = time.time() + timeout_s
        last_status = ""
        while time.time() < deadline:
            try:
                raw = self._request_text("GET", self._hero_query("getStatusV2", id=lease_id))
            except Exception as e:
                if self._hero_status_retryable_error(e):
                    last_status = str(e)[:200]
                    logger.warning("Hero SMS getStatusV2 可重试失败 lease=%s: %s", lease_id, last_status)
                    time.sleep(max(1.0, interval_s))
                    continue
                raise
            try:
                resp = json.loads(raw)
            except Exception as e:
                raise RuntimeError(f"Hero SMS getStatusV2 返回非 JSON: {self._hero_error(raw)}") from e
            if not isinstance(resp, dict):
                raise RuntimeError(f"Hero SMS getStatusV2 JSON 顶层不是对象: {type(resp).__name__}")
            if resp.get("error") or resp.get("message") in {"NO_ACTIVATION", "BAD_KEY", "BAD_ACTION", "STATUS_CANCEL"}:
                raise RuntimeError(f"Hero SMS getStatusV2 失败: {resp}")
            code = self._hero_status_v2_code(resp)
            if code:
                return code
            last_status = f"verificationType={resp.get('verificationType', '')}"
            time.sleep(max(1.0, interval_s))
        raise TimeoutError(f"等待 Hero SMS getStatusV2 OTP 超时 ({timeout_s}s, last_status={last_status or 'unknown'})")

    @staticmethod
    def _hero_cancel_too_early(msg: str) -> bool:
        text = str(msg or "")
        return (
            "EARLY_CANCEL_DENIED" in text
            or "Cannot terminate activation" in text
            or "Minimum activation period" in text
            or "minActivationTime" in text
        )

    def _hero_set_status(
        self,
        lease_id: str,
        status: str,
        *,
        reason: str = "",
        retry_on_early_cancel: bool = False,
    ) -> bool:
        if not lease_id:
            return False
        attempts = 1
        interval_s = 0.0
        if status == "8" and retry_on_early_cancel:
            attempts = max(1, int(getattr(self.cfg, "cancel_retry_attempts", 4) or 4))
            interval_s = max(1.0, float(getattr(self.cfg, "cancel_retry_interval_s", 5.0) or 5.0))
        for attempt in range(1, attempts + 1):
            try:
                raw = self._request_text("GET", self._hero_query("setStatus", id=lease_id, status=status))
                upper = raw.upper()
                if upper.startswith("BAD_") or upper in {"NO_ACTIVATION"}:
                    logger.warning(
                        "Hero SMS setStatus failed status=%s lease=%s reason=%s response=%s",
                        status,
                        lease_id,
                        reason or "-",
                        raw,
                    )
                    return False
                logger.info(
                    "Hero SMS setStatus ok status=%s lease=%s reason=%s response=%s",
                    status,
                    lease_id,
                    reason or "-",
                    raw[:120],
                )
                return True
            except Exception as e:
                msg = str(e)
                if status == "8" and "OTP_RECEIVED" in msg:
                    logger.info("Hero SMS setStatus status=%s ignored lease=%s reason=%s: %s", status, lease_id, reason or "-", msg[:200])
                    return True
                if status == "8" and retry_on_early_cancel and self._hero_cancel_too_early(msg) and attempt < attempts:
                    logger.warning(
                        "Hero SMS cancel denied, retrying lease=%s reason=%s attempt=%s/%s wait=%.1fs: %s",
                        lease_id,
                        reason or "-",
                        attempt,
                        attempts,
                        interval_s,
                        msg[:200],
                    )
                    time.sleep(interval_s)
                    continue
                logger.warning("Hero SMS setStatus failed status=%s lease=%s reason=%s: %s", status, lease_id, reason or "-", e)
                return False
        return False

    def allocate(self) -> PhoneLease:
        if self.provider == "hero_sms":
            return self._allocate_hero_sms()
        payload = {}
        extra = getattr(self.cfg, "allocate_payload", {}) or {}
        if isinstance(extra, dict):
            payload.update(extra)
        payload.setdefault("country", str(getattr(self.cfg, "country", "") or "US"))
        payload.setdefault("lease_ttl_s", int(getattr(self.cfg, "lease_ttl_s", 300) or 300))
        resp = self._request_json("POST", getattr(self.cfg, "allocate_path", ""), payload)
        lease_id = self._first_text(resp, ("lease_id", "id", "leaseId"))
        phone = self._first_text(resp, ("phone_e164", "phone_number", "phone", "number", "e164"))
        national = self._first_text(resp, ("phone_national", "national_number", "local_number"))
        country_phone_code = self._first_text(resp, ("country_phone_code", "countryPhoneCode", "dial_code"))
        provider_country = self._first_text(resp, ("provider_country", "country", "country_id", "countryId"))
        masked = self._first_text(resp, ("masked_phone", "masked", "display_phone"))
        data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
        expires_at = resp.get("expires_at") or data.get("expires_at")
        if not lease_id:
            raise RuntimeError(f"phone.allocate 响应缺 lease_id: {resp}")
        if not phone:
            raise RuntimeError(f"phone.allocate 响应缺 phone_e164/phone: lease={lease_id}")
        return PhoneLease(
            lease_id=lease_id,
            phone_e164=phone,
            masked_phone=masked or phone,
            phone_national=national,
            country_phone_code=re.sub(r"\D+", "", country_phone_code),
            provider_country=provider_country,
            expires_at=expires_at,
            raw=resp,
        )

    def poll_otp(self, lease_id: str) -> str:
        if self.provider == "hero_sms":
            return self._poll_hero_sms_otp(lease_id)
        timeout_s = self._otp_timeout_s()
        interval_s = float(getattr(self.cfg, "otp_poll_interval_s", 3.0) or 3.0)
        method = str(getattr(self.cfg, "otp_method", "GET") or "GET").strip().upper()
        path_tmpl = str(getattr(self.cfg, "otp_path", "") or "")
        deadline = time.time() + timeout_s
        last_status = ""
        while time.time() < deadline:
            path = path_tmpl.format(lease_id=lease_id)
            body = {"lease_id": lease_id} if method != "GET" else None
            resp = self._request_json(method, path, body)
            status = self._first_text(resp, ("status", "state")).lower()
            last_status = status or last_status
            code = (
                self._extract_otp6(self._first_text(resp, ("code", "otp", "sms_code", "verification_code")))
                or self._extract_otp6(self._first_text(resp, ("message", "text", "body", "sms")))
            )
            if code:
                return code
            if status in ("failed", "fail", "error", "expired", "rejected", "cancelled", "canceled"):
                reason = self._first_text(resp, ("reason", "error", "message"))
                raise RuntimeError(f"phone OTP 获取失败: status={status} reason={reason[:200]}")
            time.sleep(max(1.0, interval_s))
        raise TimeoutError(f"等待 phone OTP 超时 ({timeout_s}s, last_status={last_status or 'unknown'})")

    def _safe_post(self, path_template: str, lease_id: str, body: dict | None = None) -> None:
        path = str(path_template or "").strip()
        if not path:
            return
        try:
            self._request_json("POST", path.format(lease_id=lease_id), body or {"lease_id": lease_id})
        except Exception as e:
            logger.warning("phone provider lifecycle POST failed path=%s lease=%s: %s", path, lease_id, e)

    def mark_verified(self, lease_id: str) -> None:
        if self.provider == "hero_sms":
            ok = self._hero_set_status(lease_id, "6", reason="verified")
            self._record_hero_lease_closed(lease_id, event="verified", reason="verified", ok=ok)
            return
        self._safe_post(getattr(self.cfg, "verified_path", ""), lease_id)

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        if self.provider == "hero_sms":
            retry_cancel = "otp_timeout" in str(reason or "").lower()
            ok = self._hero_set_status(
                lease_id,
                "8",
                reason=reason,
                retry_on_early_cancel=retry_cancel,
            )
            self._record_hero_lease_closed(lease_id, event="cancel", reason=reason, ok=ok)
            return
        self._safe_post(getattr(self.cfg, "fail_path", ""), lease_id, {"lease_id": lease_id, "reason": reason[:500]})

    def release(self, lease_id: str) -> None:
        if self.provider == "hero_sms":
            ok = self._hero_set_status(lease_id, "8", reason="release")
            self._record_hero_lease_closed(lease_id, event="release", reason="release", ok=ok)
            return
        self._safe_post(getattr(self.cfg, "release_path", ""), lease_id)


def _watchdog_cancel_hero_lease(lease_id: str, delay_s: int) -> int:
    lease_id = str(lease_id or "").strip()
    if not lease_id:
        return 2
    delay_s = max(0, int(delay_s or 0))
    if delay_s:
        time.sleep(delay_s)
    if _hero_lease_is_closed(lease_id):
        _append_hero_lease_event(
            {
                "event": "watchdog_skip_closed",
                "status": "closed",
                "lease_id": lease_id,
                "reason": "already_closed",
                "ok": True,
            }
        )
        return 0

    class _Cfg:
        enabled = True
        provider = "hero_sms"
        base_url = os.getenv("HERO_WATCHDOG_BASE_URL", "https://hero-sms.com/stubs/handler_api.php")
        api_key = os.getenv("HERO_WATCHDOG_API_KEY", "")
        api_key_env = "HERO_WATCHDOG_API_KEY"
        request_timeout_s = 20
        headers = {}
        cancel_retry_attempts = 4
        cancel_retry_interval_s = 5.0

    try:
        provider = PhoneProvider(_Cfg())
        ok = provider._hero_set_status(
            lease_id,
            "8",
            reason="watchdog_stale_4m",
            retry_on_early_cancel=True,
        )
        _append_hero_lease_event(
            {
                "event": "watchdog_cancel",
                "status": "closed" if ok else "open",
                "lease_id": lease_id,
                "reason": "watchdog_stale_4m",
                "ok": bool(ok),
            }
        )
        return 0 if ok else 1
    except Exception as e:
        _append_hero_lease_event(
            {
                "event": "watchdog_cancel_exception",
                "status": "open",
                "lease_id": lease_id,
                "reason": "watchdog_stale_4m",
                "ok": False,
                "error": str(e)[:500],
            }
        )
        return 1


def _main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Hero SMS phone provider helper")
    parser.add_argument("--watchdog-cancel-lease", default="")
    parser.add_argument("--delay-s", type=int, default=_DEFAULT_STALE_CANCEL_AFTER_S)
    args = parser.parse_args()
    if args.watchdog_cancel_lease:
        return _watchdog_cancel_hero_lease(args.watchdog_cancel_lease, args.delay_s)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
