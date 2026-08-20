from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from time import monotonic, sleep, time
from typing import Any

import httpx

from refactor_app.plugins.contracts import MailLease, OtpMessage

EXTERNAL_MAIL_PROVIDER = "external_mail_api"
SIX_DIGIT_CODE_REGEX = r"(?<![0-9])([0-9]{6})(?![0-9])"
OUTLOOK_MAIL_DOMAINS = frozenset({"outlook.com", "hotmail.com", "live.com", "msn.com"})
ICLOUD_MAIL_DOMAINS = frozenset({"icloud.com", "me.com", "mac.com"})

logger = logging.getLogger(__name__)


class ExternalMailApiClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExternalMailApiPaths:
    allocate: str = "/mailbox/allocate"
    poll_otp: str = "/mailbox/{external_lease_id}/otp"
    mark_used: str = "/mailbox/{external_lease_id}/used"
    mark_failed: str = "/mailbox/{external_lease_id}/failed"
    release: str = "/mailbox/{external_lease_id}/release"
    apply_temp_email: str = "/api/external/temp-emails/apply"
    finish_temp_email: str = "/api/external/temp-emails/{task_token}/finish"
    ensure_email: str = "/api/external/temp-emails/ensure"
    verification_code: str = "/api/external/verification-code"
    claim_random: str = "/api/external/pool/claim-random"
    claim_release: str = "/api/external/pool/claim-release"
    claim_complete: str = "/api/external/pool/claim-complete"


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


@dataclass(frozen=True)
class ClaimedMailAccount:
    account_id: str
    email: str
    claim_token: str
    caller_id: str
    task_id: str
    email_domain: str = ""
    raw: dict[str, Any] | None = None


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

    def ensure_domain_email(self, *, email: str) -> dict[str, Any]:
        normalized = (email or "").strip()
        if not normalized or "@" not in normalized:
            raise ExternalMailApiClientError(
                f"ensure_domain_email requires a valid email: {email!r}"
            )
        if not _is_domain_mail_address(normalized):
            return {"email": normalized, "ensured": False, "skipped": True}
        return self.ensure_email(email=normalized)

    def apply_temp_email(
        self,
        *,
        caller_id: str,
        task_id: str,
        prefix: str = "",
        domain: str = "",
    ) -> ClaimedMailAccount:
        if not caller_id:
            raise ExternalMailApiClientError("apply_temp_email requires caller_id")
        if not task_id:
            raise ExternalMailApiClientError("apply_temp_email requires task_id")
        body: dict[str, Any] = {"caller_id": caller_id, "task_id": task_id}
        if prefix:
            body["prefix"] = prefix
        if domain:
            body["domain"] = domain
        payload = self._request_json(
            "POST",
            self._config.paths.apply_temp_email,
            json=body,
        )
        if payload.get("success") is not True:
            raise ExternalMailApiClientError(f"temp-email apply failed: {_error_message(payload)}")
        data = _payload_data(payload)
        email = _first_text(data, "email")
        task_token = _first_text(data, "task_token")
        if not email:
            raise ExternalMailApiClientError("temp-email apply response missing email")
        if not task_token:
            raise ExternalMailApiClientError("temp-email apply response missing task_token")
        return ClaimedMailAccount(
            account_id=f"temp-task:{task_token}",
            email=email,
            claim_token=task_token,
            caller_id=caller_id,
            task_id=task_id,
            email_domain=_first_text(data, "domain") or email.rpartition("@")[2],
            raw=payload,
        )

    def finish_temp_email(
        self,
        *,
        task_token: str,
        result: str,
        detail: str = "",
    ) -> dict[str, Any]:
        normalized_token = str(task_token or "").strip()
        if not normalized_token:
            raise ExternalMailApiClientError("finish_temp_email requires task_token")
        payload = self._request_json(
            "POST",
            self._config.paths.finish_temp_email.format(task_token=normalized_token),
            json={"result": str(result or "").strip(), "detail": str(detail or "").strip()},
        )
        if payload.get("success") is not True:
            raise ExternalMailApiClientError(f"temp-email finish failed: {_error_message(payload)}")
        return payload

    def claim_random(
        self,
        *,
        caller_id: str,
        task_id: str,
        provider: str = "",
        project_key: str = "",
        email_domain: str = "",
    ) -> ClaimedMailAccount:
        if not caller_id:
            raise ExternalMailApiClientError("claim_random requires caller_id")
        if not task_id:
            raise ExternalMailApiClientError("claim_random requires task_id")
        body: dict[str, Any] = {"caller_id": caller_id, "task_id": task_id}
        if provider:
            body["provider"] = provider
        if project_key:
            body["project_key"] = project_key
        if email_domain:
            body["email_domain"] = email_domain
        payload = self._request_json("POST", self._config.paths.claim_random, json=body)
        if payload.get("success") is not True:
            raise ExternalMailApiClientError(f"claim-random failed: {_error_message(payload)}")
        data = _payload_data(payload)
        account_id = _first_text(data, "account_id")
        email = _first_text(data, "email", "address", "mailbox")
        claim_token = _first_text(data, "claim_token")
        if not account_id:
            raise ExternalMailApiClientError("claim-random response missing account_id")
        if not email:
            raise ExternalMailApiClientError("claim-random response missing email")
        if not claim_token:
            raise ExternalMailApiClientError("claim-random response missing claim_token")
        return ClaimedMailAccount(
            account_id=account_id,
            email=email,
            claim_token=claim_token,
            caller_id=caller_id,
            task_id=task_id,
            email_domain=_first_text(data, "email_domain"),
            raw=payload,
        )

    def pool_stats(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/external/pool/stats")

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
        code_source: str = "content",
    ) -> OtpMessage:
        normalized = (email or "").strip()
        if not normalized:
            raise ExternalMailApiClientError("wait_for_otp_by_email requires email")
        normalized_code_source = str(code_source or "content").strip().lower()
        if normalized_code_source not in {"subject", "content", "html", "all"}:
            raise ExternalMailApiClientError(f"unsupported verification code_source: {code_source}")

        is_domain_mail = _is_domain_mail_address(normalized)
        lookup_email = normalized.lower() if is_domain_mail else normalized
        effective_timeout = max(1, int(timeout_s or 180))
        start = self._monotonic()
        deadline = start + effective_timeout
        polls = 0
        poll_limit = max(1, int(max_polls)) if max_polls is not None else 0
        last_error = ""
        not_found_codes = {"MAIL_NOT_FOUND", "VERIFICATION_CODE_NOT_FOUND"}
        ensured_after_missing = False

        while self._monotonic() < deadline:
            polls += 1
            min_message_ts = 0.0
            since_minutes = 10
            if issued_after:
                min_message_ts = max(0.0, float(issued_after) - 60.0)
                elapsed_from_threshold = max(0.0, time() - min_message_ts)
                since_minutes = max(1, int(math.ceil(elapsed_from_threshold / 60.0)) + 1)

            try:
                params = {
                    "email": lookup_email,
                    "since_minutes": str(since_minutes),
                    "code_length": "6" if is_domain_mail else "6-6",
                    "code_source": normalized_code_source,
                }
                if not is_domain_mail:
                    params["code_regex"] = SIX_DIGIT_CODE_REGEX
                payload = self._request_json(
                    "GET",
                    self._config.paths.verification_code,
                    params=params,
                    allow_error_status=True,
                )
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if poll_limit and polls >= poll_limit:
                    break
                self._sleep(
                    min(self._config.poll_interval_s, max(0.1, deadline - self._monotonic()))
                )
                continue
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
            if is_domain_mail and not ensured_after_missing and _is_missing_mailbox_error(payload):
                logger.info(
                    "external mailbox missing; ensure before continuing OTP polling email=%s",
                    lookup_email,
                )
                self.ensure_email(email=lookup_email)
                ensured_after_missing = True
                if poll_limit and polls >= poll_limit:
                    break
                continue
            if err_code and err_code not in not_found_codes:
                raise ExternalMailApiClientError(
                    f"verification-code failed email={lookup_email}: {last_error}"
                )
            if poll_limit and polls >= poll_limit:
                break
            self._sleep(min(self._config.poll_interval_s, max(0.1, deadline - self._monotonic())))

        suffix = f": {last_error}" if last_error else ""
        raise TimeoutError(
            f"ExternalMailApiClient: wait_for_otp_by_email timeout "
            f"{effective_timeout}s email={lookup_email}{suffix}"
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

    def claim_release(self, claim: ClaimedMailAccount, *, reason: str = "") -> dict[str, Any]:
        return self._request_json(
            "POST",
            self._config.paths.claim_release,
            json={
                "account_id": _coerce_account_id(claim.account_id),
                "claim_token": claim.claim_token,
                "caller_id": claim.caller_id,
                "task_id": claim.task_id,
                "reason": reason,
            },
        )

    def claim_complete(
        self,
        claim: ClaimedMailAccount,
        *,
        result: str,
        detail: str = "",
    ) -> dict[str, Any]:
        if not result:
            raise ExternalMailApiClientError("claim_complete requires result")
        return self._request_json(
            "POST",
            self._config.paths.claim_complete,
            json={
                "account_id": _coerce_account_id(claim.account_id),
                "claim_token": claim.claim_token,
                "caller_id": claim.caller_id,
                "task_id": claim.task_id,
                "result": result,
                "detail": detail,
            },
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
            body = response.text[:500]
            raise ExternalMailApiClientError(
                f"external mail api failed: method={method} path={path} "
                f"http_status={response.status_code} body={body}"
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


def _is_domain_mail_address(email: str) -> bool:
    domain = (email.rsplit("@", 1)[-1] if "@" in email else "").strip().lower()
    return (
        bool(domain)
        and not _is_outlook_mail_domain(domain)
        and domain not in ICLOUD_MAIL_DOMAINS
    )


def _is_outlook_mail_domain(domain: str) -> bool:
    normalized = str(domain or "").strip().lower().rstrip(".")
    return normalized in OUTLOOK_MAIL_DOMAINS or normalized.startswith("outlook.")


def _is_missing_mailbox_error(payload: dict[str, Any]) -> bool:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = str(payload.get("code") or error.get("code") or "").strip().upper()
    message = str(payload.get("message") or error.get("message") or "").strip().lower()
    if code in {
        "TEMP_EMAIL_NOT_FOUND",
        "TEMP_MAIL_NOT_FOUND",
        "ACCOUNT_NOT_FOUND",
        "MAIL_ACCOUNT_NOT_FOUND",
        "EMAIL_ACCOUNT_NOT_FOUND",
    }:
        return True
    return int(payload.get("_http_status") or 0) == 404 and any(
        marker in message
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
    )


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return str(value)
    return ""


def _coerce_account_id(value: str) -> int | str:
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return text
