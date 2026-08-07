from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx


class TwoFAuthClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class TwoFAuthClientConfig:
    base_url: str = "https://daboluo2fa.zeabur.app"
    api_token: str = ""
    timeout_s: float = 30.0

    def validate(self) -> None:
        if not self.base_url.strip():
            raise TwoFAuthClientError("2FAuth base_url is required")
        if not self.api_token.strip():
            raise TwoFAuthClientError("2FAuth api_token is required")
        if self.timeout_s <= 0:
            raise TwoFAuthClientError("2FAuth timeout_s must be positive")


@dataclass(frozen=True)
class TwoFAuthOtp:
    password: str
    generated_at: int
    period: int


class TwoFAuthClient:
    def __init__(
        self,
        config: TwoFAuthClientConfig,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        config.validate()
        self._config = config
        self._headers = {
            "Authorization": f"Bearer {config.api_token.strip()}",
            "Accept": "application/json",
        }
        self._client = http_client or httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=config.timeout_s,
        )

    def close(self) -> None:
        self._client.close()

    def create_totp_account(
        self,
        *,
        email: str,
        secret: str,
        service: str = "OpenAI",
        algorithm: str = "SHA1",
        digits: int = 6,
        period: int = 30,
    ) -> str:
        normalized_email = str(email or "").strip()
        normalized_secret = str(secret or "").strip()
        if not normalized_email or "@" not in normalized_email:
            raise TwoFAuthClientError("create_totp_account requires a valid email")
        if not normalized_secret:
            raise TwoFAuthClientError("create_totp_account requires secret")
        label = f"{service}:{normalized_email}"
        query = urlencode(
            {
                "secret": normalized_secret,
                "issuer": service,
                "algorithm": algorithm.upper(),
                "digits": int(digits),
                "period": int(period),
            }
        )
        uri = f"otpauth://totp/{quote(label, safe=':')}?{query}"
        response = self._client.post(
            "/api/v1/twofaccounts",
            json={"uri": uri},
            headers={**self._headers, "Content-Type": "application/json"},
        )
        payload = _response_json(response, operation="create TOTP account")
        account_id = str(payload.get("id") or "").strip()
        if not account_id:
            raise TwoFAuthClientError("2FAuth create response missing id")
        return account_id

    def get_otp(self, account_id: str) -> TwoFAuthOtp:
        normalized_id = str(account_id or "").strip()
        if not normalized_id:
            raise TwoFAuthClientError("get_otp requires account_id")
        response = self._client.get(
            f"/api/v1/twofaccounts/{quote(normalized_id)}/otp",
            headers=self._headers,
        )
        payload = _response_json(response, operation="get TOTP code")
        password = str(payload.get("password") or "").strip()
        if not password.isdigit():
            raise TwoFAuthClientError("2FAuth OTP response missing numeric password")
        return TwoFAuthOtp(
            password=password,
            generated_at=_int_value(payload.get("generated_at")),
            period=max(1, _int_value(payload.get("period"), default=30)),
        )

    def delete_account(self, account_id: str) -> None:
        normalized_id = str(account_id or "").strip()
        if not normalized_id:
            return
        response = self._client.delete(
            f"/api/v1/twofaccounts/{quote(normalized_id)}",
            headers=self._headers,
        )
        if response.status_code != 204:
            _response_json(response, operation="delete TOTP account")


def _response_json(response: httpx.Response, *, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if response.is_error:
        detail = _error_detail(payload) or str(response.text or "")[:300]
        raise TwoFAuthClientError(
            f"2FAuth {operation} failed: HTTP {response.status_code}: {detail}"
        )
    if not isinstance(payload, dict):
        raise TwoFAuthClientError(f"2FAuth {operation} returned non-object JSON")
    return payload


def _error_detail(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("message", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]
    return ""


def _int_value(value: object, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
