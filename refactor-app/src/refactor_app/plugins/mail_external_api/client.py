from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from time import monotonic, sleep, time
from typing import Any

import httpx

from refactor_app.plugins.contracts import MailLease, OtpMessage

EXTERNAL_MAIL_PROVIDER = "external_mail_api"


class ExternalMailApiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExternalMailApiPaths:
    allocate: str = "/mailbox/allocate"
    poll_otp: str = "/mailbox/{external_lease_id}/otp"
    mark_used: str = "/mailbox/{external_lease_id}/used"
    mark_failed: str = "/mailbox/{external_lease_id}/failed"
    release: str = "/mailbox/{external_lease_id}/release"
    ensure_email: str = "/api/external/temp-emails/ensure"
    verification_code: str = "/api/external/verification-code"


@dataclass(frozen=True)
class ExternalMailApiClientConfig:
    base_url: str
    api_key: str
    paths: ExternalMailApiPaths = ExternalMailApiPaths()
    api_key_header: str = "X-API-Key"
    provider_name: str = "cloudflare_temp_mail"
    timeout_s: float = 30.0
    poll_interval_s: float = 3.0

    def validate(self) -> None:
        if not self.base_url:
            raise ExternalMailApiClientError("external mail api base_url is required")
        if not self.api_key:
            raise ExternalMailApiClientError("external mail api api_key is required")
        if self.timeout_s <= 0:
            raise ExternalMailApiClientError("external mail api timeout_s must be positive")
        if self.poll_interval_s <= 0:
            raise ExternalMailApiClientError("external mail api poll_interval_s must be positive")


class ExternalMailApiClient:
    def __init__(
        self,
        config: ExternalMailApiClientConfig,
        *,
        http_client: httpx.Client | None = None,
        sleep_fn: Any = sleep,
        monotonic_fn: Any = monotonic,
    ) -> None:
        config.validate()
        self._config = config
        self._client = http_client or httpx.Client(
            base_url=config.base_url,
            timeout=config.timeout_s,
            headers={config.api_key_header: config.api_key, "Accept": "application/json"},
        )
        self._sleep = sleep_fn
        self._monotonic = monotonic_fn

    def allocate_mailbox(self, *, purpose: str = "") -> MailLease:
        payload = self._request_json("POST", self._config.paths.allocate, json={"purpose": purpose})
        return parse_mail_lease(payload)

    def ensure_email(self, *, email: str) -> dict[str, Any]:
        normalized = (email or "").strip().lower()
        if not normalized or "@" not in normalized:
            raise ExternalMailApiClientError(f"ensure_email requires a valid email: {email!r}")
        payload = self._request_json(
            "POST",
            self._config.paths.ensure_email,
            json={
                "email": normalized,
                "provider_name": self._config.provider_name,
            },
        )
        if payload.get("success") is not True:
            raise ExternalMailApiClientError(
                f"ensure_email failed email={normalized}: {_error_message(payload)}"
            )
        data = _payload_data(payload)
        returned = str(data.get("email") or "").strip().lower()
        if returned and returned != normalized:
            raise ExternalMailApiClientError(
                f"ensure_email returned different email requested={normalized} returned={returned}"
            )
        return data

    def poll_otp(self, *, external_lease_id: str, timeout_s: int) -> OtpMessage | None:
        deadline = self._monotonic() + max(0, timeout_s)
        while True:
            payload = self._request_json(
                "GET",
                self._format_path(self._config.paths.poll_otp, external_lease_id),
            )
            otp = parse_otp_message(payload)
            if otp is not None:
                return otp
            if self._monotonic() >= deadline:
                return None
            self._sleep(self._config.poll_interval_s)

    def wait_for_otp_by_email(
        self,
        *,
        email: str,
        timeout_s: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ) -> OtpMessage:
        normalized = (email or "").strip().lower()
        if not normalized:
            raise ExternalMailApiClientError("wait_for_otp_by_email requires email")

        effective_timeout = max(1, int(timeout_s or 180))
        start = self._monotonic()
        deadline = start + effective_timeout
        polls = 0
        poll_limit = max(1, int(max_polls)) if max_polls is not None else 0
        last_error = ""
        not_found_codes = {"MAIL_NOT_FOUND", "VERIFICATION_CODE_NOT_FOUND"}

        while self._monotonic() < deadline:
            polls += 1
            min_message_ts = 0.0
            since_minutes = 10
            if issued_after:
                min_message_ts = max(0.0, float(issued_after) - 60.0)
                elapsed_from_threshold = max(0.0, time() - min_message_ts)
                since_minutes = max(1, int(math.ceil(elapsed_from_threshold / 60.0)) + 1)

            payload = self._request_json(
                "GET",
                self._config.paths.verification_code,
                params={
                    "email": normalized,
                    "since_minutes": str(since_minutes),
                    "code_length": "6",
                    "code_source": "all",
                },
                allow_error_status=True,
            )
            data = _payload_data(payload)
            code = _first_text(data, "verification_code", "code") or _first_text(
                payload, "verification_code"
            )
            if payload.get("success") is True and code:
                msg_ts = _payload_message_ts(payload, data)
                if min_message_ts and msg_ts and msg_ts < min_message_ts:
                    last_error = (
                        f"VERIFICATION_CODE_TOO_OLD: message_ts={msg_ts:.0f} "
                        f"min_ts={min_message_ts:.0f}"
                    )
                    if poll_limit and polls >= poll_limit:
                        break
                    self._sleep(
                        min(self._config.poll_interval_s, max(0.1, deadline - self._monotonic()))
                    )
                    continue
                return OtpMessage(code=code, raw=payload)

            err_code = str(
                payload.get("code") or payload.get("error", {}).get("code") or ""
            ).strip()
            last_error = _error_message(payload)
            if err_code and err_code not in not_found_codes:
                raise ExternalMailApiClientError(
                    f"verification-code failed email={normalized}: {last_error}"
                )
            if poll_limit and polls >= poll_limit:
                break
            self._sleep(
                min(self._config.poll_interval_s, max(0.1, deadline - self._monotonic()))
            )

        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(
            f"ExternalMailApiClient: wait_for_otp_by_email timeout "
            f"{effective_timeout}s email={normalized}{suffix}"
        )

    def mark_used(self, *, external_lease_id: str) -> None:
        self._request_json(
            "POST",
            self._format_path(self._config.paths.mark_used, external_lease_id),
        )

    def mark_failed(
        self,
        *,
        external_lease_id: str,
        failure_code: str = "",
        failure_message: str = "",
    ) -> None:
        self._request_json(
            "POST",
            self._format_path(self._config.paths.mark_failed, external_lease_id),
            json={"failure_code": failure_code, "failure_message": failure_message},
        )

    def release(self, *, external_lease_id: str, reason: str = "") -> None:
        self._request_json(
            "POST",
            self._format_path(self._config.paths.release, external_lease_id),
            json={"reason": reason},
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        allow_error_status: bool = False,
    ) -> dict[str, Any]:
        response = self._client.request(method, path, json=json, params=params)
        if response.is_error and not allow_error_status:
            raise ExternalMailApiClientError(
                f"external mail api failed: method={method} path={path} "
                f"http_status={response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ExternalMailApiClientError("external mail api response must be a JSON object")
        if allow_error_status:
            payload.setdefault("_http_status", response.status_code)
        return payload

    @staticmethod
    def _format_path(path: str, external_lease_id: str) -> str:
        if not external_lease_id:
            raise ExternalMailApiClientError("external_lease_id is required")
        return path.format(external_lease_id=external_lease_id)


def parse_mail_lease(payload: dict[str, Any]) -> MailLease:
    data = _payload_data(payload)
    external_lease_id = _first_text(data, "external_lease_id", "lease_id", "id")
    email = _first_text(data, "email", "address", "mailbox")
    if not external_lease_id:
        raise ExternalMailApiClientError("external mail api allocate response missing lease id")
    if not email:
        raise ExternalMailApiClientError("external mail api allocate response missing email")
    return MailLease(
        provider=EXTERNAL_MAIL_PROVIDER,
        external_lease_id=external_lease_id,
        email=email,
    )


def parse_otp_message(payload: dict[str, Any]) -> OtpMessage | None:
    data = _payload_data(payload)
    code = _first_text(data, "code", "otp", "verification_code", "verificationCode")
    if not code:
        return None
    return OtpMessage(code=code, raw=payload)


def _payload_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise ExternalMailApiClientError("external mail api data must be a JSON object")
    return data


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
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _payload_message_ts(payload: dict[str, Any], data: dict[str, Any]) -> float:
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
            ts = _coerce_epoch_seconds(source.get(key))
            if ts:
                return ts
    return 0.0


def _error_message(payload: dict[str, Any]) -> str:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = payload.get("code") or error.get("code") or "ERROR"
    msg = payload.get("message") or error.get("message") or ""
    return f"{code}: {msg}".strip()


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return str(value)
    return ""
