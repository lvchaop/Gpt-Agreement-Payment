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
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


logger = logging.getLogger(__name__)


class ExternalMailApiProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        provider_name: str = "cloudflare_temp_mail",
        request_timeout_s: int = 20,
        poll_interval_s: float = 3.0,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = self._normalize_api_key(api_key)
        self.provider_name = (provider_name or "cloudflare_temp_mail").strip()
        self.request_timeout_s = max(1, int(request_timeout_s or 20))
        self.poll_interval_s = max(0.5, float(poll_interval_s or 3.0))
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )
        if not self.base_url:
            raise RuntimeError("ExternalMailApiProvider 缺 mail.external_base_url")
        if not self.api_key:
            raise RuntimeError("ExternalMailApiProvider 缺 mail.external_api_key")

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
            request_timeout_s=int(getattr(mail_cfg, "external_request_timeout_s", 20) or 20),
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
        if query:
            params = {
                k: str(v)
                for k, v in query.items()
                if v is not None and str(v) != ""
            }
            if params:
                url += "?" + urllib.parse.urlencode(params)

        data = None
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=self.request_timeout_s) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return int(resp.status), self._parse_json(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return int(exc.code), self._parse_json(raw)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"External mail API 网络错误 {method} {path}: {exc}") from exc

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

        while time.time() < deadline:
            polls += 1
            since_minutes = 10
            if issued_after:
                elapsed_from_issue = max(0.0, time.time() - float(issued_after))
                since_minutes = max(10, int(math.ceil(elapsed_from_issue / 60.0)) + 2)

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
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            code = str(
                data.get("verification_code")
                or data.get("code")
                or payload.get("verification_code")
                or ""
            ).strip()
            if payload.get("success") is True and code:
                logger.info(
                    "[external-mail] 收到 OTP email=%s polls=%s elapsed=%.1fs",
                    email,
                    polls,
                    time.time() - start,
                )
                return code

            err_code = str(payload.get("code") or payload.get("error", {}).get("code") or "").strip()
            last_error = self._error_message(payload, status)
            if (not ensured_after_missing) and self._is_missing_mailbox_error(payload, status):
                logger.info(
                    "[external-mail] verification-code 返回邮箱不存在，先 ensure 后继续轮询 email=%s error=%s",
                    email,
                    last_error,
                )
                self.ensure_email(email)
                ensured_after_missing = True
                continue
            if status < 500 and err_code and err_code not in not_found_codes:
                raise RuntimeError(f"verification-code 失败 email={email}: {last_error}")

            time.sleep(min(self.poll_interval_s, max(0.1, deadline - time.time())))

        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(f"ExternalMailApiProvider: 等 OTP 超时 {effective_timeout}s email={email}{suffix}")
