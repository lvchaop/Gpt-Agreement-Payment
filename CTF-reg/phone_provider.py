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
import re
import time
from dataclasses import dataclass
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

    def _hero_service_country(self) -> tuple[str, str]:
        service = str(getattr(self.cfg, "service", "") or "tg").strip()
        country = str(getattr(self.cfg, "country", "") or "").strip()
        if not service:
            raise RuntimeError("Hero SMS 需要 phone.service，例如 tg")
        if not country or not country.isdigit():
            raise RuntimeError(f"Hero SMS 需要 phone.country 填数字国家码，例如 2；当前={country or '<empty>'}")
        return service, country

    def _hero_max_price(self) -> str:
        return str(getattr(self.cfg, "maxPrice", "") or getattr(self.cfg, "max_price", "") or "").strip()

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
        service, country = self._hero_service_country()
        max_price = self._hero_max_price()
        logger.info(
            "Hero SMS getNumberV2 service=%s country=%s maxPrice=%s base_url=%s",
            service,
            country,
            max_price or "<empty>",
            self.base_url,
        )
        raw = self._request_text("GET", self._hero_query("getNumberV2", service=service, country=country, maxPrice=max_price))
        try:
            resp = json.loads(raw)
        except Exception as e:
            raise RuntimeError(f"Hero SMS getNumberV2 返回非 JSON: {self._hero_error(raw)}") from e
        if not isinstance(resp, dict):
            raise RuntimeError(f"Hero SMS getNumberV2 JSON 顶层不是对象: {type(resp).__name__}")
        if resp.get("error") or resp.get("message") in {"NO_NUMBERS", "NO_BALANCE", "BAD_KEY", "BAD_ACTION"}:
            raise RuntimeError(f"Hero SMS getNumberV2 失败: {resp}")
        lease_id = str(resp.get("activationId") or resp.get("activation_id") or "").strip()
        if not lease_id:
            raise RuntimeError(f"Hero SMS getNumberV2 响应缺 activationId: {resp}")
        phone_e164, phone_national, country_phone_code = self._hero_phone_parts(
            resp.get("phoneNumber") or resp.get("phone_number"),
            resp.get("countryPhoneCode"),
        )
        return PhoneLease(
            lease_id=lease_id,
            phone_e164=phone_e164,
            masked_phone=self._mask_phone(phone_e164),
            phone_national=phone_national,
            country_phone_code=country_phone_code,
            expires_at=resp.get("activationEndTime") or resp.get("activation_end_time"),
            raw=resp,
        )

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
            raw = self._request_text("GET", self._hero_query("getStatusV2", id=lease_id))
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

    def _hero_set_status(self, lease_id: str, status: str) -> None:
        if not lease_id:
            return
        try:
            raw = self._request_text("GET", self._hero_query("setStatus", id=lease_id, status=status))
            upper = raw.upper()
            if upper.startswith("BAD_") or upper in {"NO_ACTIVATION"}:
                logger.warning("Hero SMS setStatus failed status=%s lease=%s response=%s", status, lease_id, raw)
        except Exception as e:
            msg = str(e)
            if status == "8" and (
                "OTP_RECEIVED" in msg
                or "Cannot terminate activation" in msg
                or "Minimum activation period" in msg
                or "minActivationTime" in msg
            ):
                logger.info("Hero SMS setStatus status=%s ignored lease=%s: %s", status, lease_id, msg[:200])
                return
            logger.warning("Hero SMS setStatus failed status=%s lease=%s: %s", status, lease_id, e)

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
            self._hero_set_status(lease_id, "6")
            return
        self._safe_post(getattr(self.cfg, "verified_path", ""), lease_id)

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        if self.provider == "hero_sms":
            self._hero_set_status(lease_id, "8")
            return
        self._safe_post(getattr(self.cfg, "fail_path", ""), lease_id, {"lease_id": lease_id, "reason": reason[:500]})

    def release(self, lease_id: str) -> None:
        if self.provider == "hero_sms":
            self._hero_set_status(lease_id, "8")
            return
        self._safe_post(getattr(self.cfg, "release_path", ""), lease_id)
