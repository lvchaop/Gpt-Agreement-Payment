"""External temp-mail API provider for registration email OTP.

This client implements only the explicit-address flow:

  local persona email -> POST /api/external/temp-emails/ensure
  OTP polling         -> GET  /api/external/verification-code

It intentionally does not use the pool claim/release/complete endpoints.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter


logger = logging.getLogger(__name__)


class ExternalMailApiProvider:
    _session: requests.Session | None = None

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        provider_name: str = "cloudflare_temp_mail",
        request_timeout_s: int = 5,
        poll_interval_s: float = 3.0,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = self._normalize_api_key(api_key)
        self.provider_name = (provider_name or "cloudflare_temp_mail").strip()
        self.request_timeout_s = max(1, int(request_timeout_s or 5))
        self.poll_interval_s = max(0.5, float(poll_interval_s or 3.0))
        self._session = self._shared_session()
        if not self.base_url:
            raise RuntimeError("ExternalMailApiProvider 缺 mail.external_base_url")
        if not self.api_key:
            raise RuntimeError("ExternalMailApiProvider 缺 mail.external_api_key")

    @staticmethod
    def _coerce_epoch_seconds(value: Any) -> float:
        if value is None or value == "":
            return 0.0
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1000000000000:
                ts /= 1000.0
            return ts
        text = str(value).strip()
        if not text:
            return 0.0
        try:
            ts = float(text)
            if ts > 1000000000000:
                ts /= 1000.0
            return ts
        except Exception:
            pass
        try:
            from datetime import datetime

            normalized = text.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except Exception:
            return 0.0

    @classmethod
    def _payload_message_ts(cls, payload: dict[str, Any], data: dict[str, Any]) -> float:
        for source in (data, payload):
            for key in (
                "received_at",
                "receivedAt",
                "created_at",
                "createdAt",
                "timestamp",
                "time",
                "date",
                "sent_at",
                "sentAt",
            ):
                ts = cls._coerce_epoch_seconds(source.get(key))
                if ts:
                    return ts
        return 0.0

    @classmethod
    def _shared_session(cls) -> requests.Session:
        if cls._session is None:
            session = requests.Session()
            session.trust_env = False
            pool_size = max(1, int(os.getenv("EXTERNAL_MAIL_POOL_SIZE", "30") or "30"))
            adapter = HTTPAdapter(
                pool_connections=pool_size,
                pool_maxsize=pool_size,
                pool_block=True,
                max_retries=0,
            )
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            logger.info("[external-mail] shared HTTP pool initialized size=%s block=true", pool_size)
            cls._session = session
        return cls._session

    @staticmethod
    def _normalize_api_key(api_key: str) -> str:
        value = (api_key or "").strip()
        lowered = value.lower()
        for prefix in ("x-api-key=", "x-api-key:"):
            if lowered.startswith(prefix):
                return value[len(prefix):].strip()
        return value

    @classmethod
    def from_mail_config(cls, mail_cfg) -> "ExternalMailApiProvider":
        return cls(
            getattr(mail_cfg, "external_base_url", "") or "",
            getattr(mail_cfg, "external_api_key", "") or "",
            provider_name=(
                getattr(mail_cfg, "external_provider_name", "")
                or getattr(mail_cfg, "provider_name", "")
                or "cloudflare_temp_mail"
            ),
            request_timeout_s=int(getattr(mail_cfg, "external_request_timeout_s", 30) or 30),
            poll_interval_s=float(getattr(mail_cfg, "external_poll_interval_s", 3.0) or 3.0),
        )

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        url = self._url(path)
        params = None
        if query:
            params = {
                k: str(v)
                for k, v in query.items()
                if v is not None and str(v) != ""
            }
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        try:
            resp = self._session.request(
                method,
                url,
                params=params,
                headers=headers,
                json=body if body is not None else None,
                timeout=self.request_timeout_s,
            )
            return int(resp.status_code), self._parse_json(resp.text or "{}")
        except requests.Timeout as exc:
            raise RuntimeError(
                f"External mail API 读超时 {self.request_timeout_s}s {method} {path}: {exc}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"External mail API 网络错误 {method} {path}: {exc}") from exc

    def warmup_connection_pool(self) -> None:
        """Best-effort warmup for DNS/TCP/TLS/keep-alive before worker fan-out."""
        try:
            resp = self._session.get(
                self.base_url + "/",
                headers={"Accept": "*/*"},
                timeout=self.request_timeout_s,
                allow_redirects=False,
            )
            logger.info(
                "[external-mail] connection pool warmup ok status=%s base_url=%s",
                resp.status_code,
                self.base_url,
            )
        except requests.Timeout as exc:
            logger.warning(
                "[external-mail] connection pool warmup timeout %ss base_url=%s: %s",
                self.request_timeout_s,
                self.base_url,
                exc,
            )
        except requests.RequestException as exc:
            logger.warning(
                "[external-mail] connection pool warmup failed base_url=%s: %s",
                self.base_url,
                exc,
            )

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw or "{}")
        except Exception as exc:
            raise RuntimeError(f"External mail API 返回非 JSON: {(raw or '')[:200]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"External mail API 返回格式异常: {type(parsed).__name__}")
        return parsed

    @staticmethod
    def _error_message(payload: dict[str, Any], status: int) -> str:
        code = payload.get("code") or payload.get("error", {}).get("code") or f"HTTP_{status}"
        msg = payload.get("message") or payload.get("error", {}).get("message") or ""
        return f"{code}: {msg}".strip()

    @staticmethod
    def _is_missing_mailbox_error(payload: dict[str, Any], status: int) -> bool:
        code = str(payload.get("code") or payload.get("error", {}).get("code") or "").strip().upper()
        msg = str(payload.get("message") or payload.get("error", {}).get("message") or "").strip().lower()
        if code in {
            "TEMP_EMAIL_NOT_FOUND",
            "TEMP_MAIL_NOT_FOUND",
            "ACCOUNT_NOT_FOUND",
            "MAIL_ACCOUNT_NOT_FOUND",
            "EMAIL_ACCOUNT_NOT_FOUND",
        }:
            return True
        if status == 404 and any(
            marker in msg
            for marker in (
                "account not found",
                "mail account not found",
                "email account not found",
                "mailbox not found",
                "email not found",
                "temp email not found",
                "账号不存在",
                "邮箱不存在",
                "邮箱账号不存在",
            )
        ):
            return True
        return False

    def ensure_email(self, email_addr: str) -> dict[str, Any]:
        email = (email_addr or "").strip().lower()
        if not email or "@" not in email:
            raise RuntimeError(f"ensure_email 缺合法邮箱: {email_addr!r}")
        status, payload = self._request_json(
            "POST",
            "/api/external/temp-emails/ensure",
            body={
                "email": email,
                "provider_name": self.provider_name,
            },
        )
        if status >= 400 or payload.get("success") is not True:
            raise RuntimeError(
                f"ensure_email 失败 email={email}: {self._error_message(payload, status)}"
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        returned = str(data.get("email") or "").strip().lower()
        if returned and returned != email:
            raise RuntimeError(f"ensure_email 返回邮箱不一致 requested={email} returned={returned}")
        logger.info(
            "[external-mail] ensure ok email=%s provider=%s recovered=%s",
            email,
            data.get("provider_name") or self.provider_name,
            data.get("recovered"),
        )
        return data

    def wait_for_otp(
        self,
        email_addr: str,
        timeout: int = 180,
        issued_after: Optional[float] = None,
        max_polls: Optional[int] = None,
    ) -> str:
        email = (email_addr or "").strip().lower()
        if not email:
            raise RuntimeError("wait_for_otp 缺 email")

        effective_timeout = max(1, int(timeout or 180))
        deadline = time.time() + effective_timeout
        start = time.time()
        not_found_codes = {"MAIL_NOT_FOUND", "VERIFICATION_CODE_NOT_FOUND"}
        ensured_after_missing = False
        polls = 0
        last_error = ""
        poll_limit = max(1, int(max_polls)) if max_polls is not None else 0

        while time.time() < deadline:
            polls += 1
            min_message_ts = 0.0
            since_minutes = 10
            if issued_after:
                min_message_ts = max(0.0, float(issued_after) - 30.0)
                elapsed_from_threshold = max(0.0, time.time() - min_message_ts)
                since_minutes = max(1, int(math.ceil(elapsed_from_threshold / 60.0)) + 1)

            try:
                status, payload = self._request_json(
                    "GET",
                    "/api/external/verification-code",
                    query={
                        "email": email,
                        "since_minutes": since_minutes,
                        "code_length": "6",
                        "code_source": "all",
                    },
                )
            except RuntimeError as exc:
                last_error = str(exc)
                logger.warning("[external-mail] verification-code 轮询异常 email=%s: %s", email, last_error)
                if poll_limit and polls >= poll_limit:
                    break
                time.sleep(min(self.poll_interval_s, max(0.1, deadline - time.time())))
                continue
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            code = str(
                data.get("verification_code")
                or data.get("code")
                or payload.get("verification_code")
                or ""
            ).strip()
            if payload.get("success") is True and code:
                msg_ts = self._payload_message_ts(payload, data)
                if min_message_ts and msg_ts and msg_ts < min_message_ts:
                    last_error = (
                        f"VERIFICATION_CODE_TOO_OLD: message_ts={msg_ts:.0f} "
                        f"min_ts={min_message_ts:.0f}"
                    )
                    logger.info(
                        "[external-mail] 忽略旧 OTP email=%s polls=%s message_ts=%.0f min_ts=%.0f",
                        email,
                        polls,
                        msg_ts,
                        min_message_ts,
                    )
                    if poll_limit and polls >= poll_limit:
                        break
                    time.sleep(min(self.poll_interval_s, max(0.1, deadline - time.time())))
                    continue
                logger.info(
                    "[external-mail] 收到 OTP email=%s polls=%s elapsed=%.1fs since_minutes=%s min_ts=%.0f message_ts=%.0f",
                    email,
                    polls,
                    time.time() - start,
                    since_minutes,
                    min_message_ts,
                    msg_ts,
                )
                return code

            err_code = str(payload.get("code") or payload.get("error", {}).get("code") or "").strip()
            last_error = self._error_message(payload, status)
            if status < 500 and err_code and err_code not in not_found_codes:
                raise RuntimeError(f"verification-code 失败 email={email}: {last_error}")

            if poll_limit and polls >= poll_limit:
                break
            time.sleep(min(self.poll_interval_s, max(0.1, deadline - time.time())))

        suffix = f": {last_error}" if last_error else ""
        if poll_limit:
            raise TimeoutError(f"ExternalMailApiProvider: 单次取 OTP 未命中 email={email}{suffix}")
        raise TimeoutError(f"ExternalMailApiProvider: 等 OTP 超时 {effective_timeout}s email={email}{suffix}")
