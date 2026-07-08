from __future__ import annotations

import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import ensure_account_proxy_url
from refactor_app.infrastructure.db.models import UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow, AuthResult
from refactor_app.plugins.openai_auth_protocol.config import Config, PhoneConfig


EMAIL_PROTOCOL_NO_PHONE = "email_protocol_no_phone"
PHONE_PROTOCOL_BIND_EMAIL = "phone_protocol_bind_email"


class ProtocolRegistrationWorkflowError(RuntimeError):
    pass


TraceEmitter = Callable[[str, dict[str, Any], str], None]


@dataclass(frozen=True)
class ProtocolRegistrationInput:
    mode: str
    use_proxy: bool = True
    proxy_url: str = ""
    mail_provider: str = "outlook"
    email_domain: str = ""
    project_key: str = "openai-register"
    caller_id: str = "refactor-app-protocol-registration"
    phone_provider: str = "hero_sms"
    phone_base_url: str = "https://hero-sms.com/stubs/handler_api.php"
    phone_api_key_env: str = "HERO_SMS_API_KEY"
    phone_service: str = "tg"
    phone_country: str = "2"
    phone_countries: list[str] = field(default_factory=list)
    phone_max_price: str = ""
    phone_country_max_prices: dict[str, str] = field(default_factory=dict)
    phone_max_number_attempts: int = 3
    phone_otp_timeout_s: int = 180
    phone_otp_poll_interval_s: float = 3.0


class ProtocolRegistrationWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider

    def run(self, input_: ProtocolRegistrationInput, *, work_id: str = "", run_id: str = "") -> dict:
        mode = str(input_.mode or "").strip()
        if mode == EMAIL_PROTOCOL_NO_PHONE:
            return self._run_email_protocol(input_, work_id=work_id, run_id=run_id)
        if mode == PHONE_PROTOCOL_BIND_EMAIL:
            return self._run_phone_protocol(input_, work_id=work_id, run_id=run_id)
        raise ProtocolRegistrationWorkflowError(f"unsupported protocol registration mode: {mode}")

    def _run_email_protocol(
        self,
        input_: ProtocolRegistrationInput,
        *,
        work_id: str,
        run_id: str,
    ) -> dict:
        emit = self._make_event_emitter(run_id=run_id, work_id=work_id, mode=EMAIL_PROTOCOL_NO_PHONE)
        emit("started", {"mail_provider": input_.mail_provider, "project_key": input_.project_key})
        mail = RegistrationMailProviderAdapter(
            mail_provider=self._mail_provider,
            caller_id=input_.caller_id,
            task_id=work_id,
            provider=input_.mail_provider,
            project_key=input_.project_key,
            email_domain=input_.email_domain,
            event_callback=emit,
            claim_persist_callback=self._make_claim_persist_callback(work_id),
        )
        user_account_id = self._create_placeholder_account(email="")
        emit(
            "account.placeholder_created",
            {"user_account_id": user_account_id, "email": ""},
        )
        claimed: ClaimedMailAccount | None = None
        try:
            proxy_url = ""
            if input_.proxy_url:
                proxy_url = input_.proxy_url
            elif input_.use_proxy:
                proxy_url = ensure_account_proxy_url(
                    self._session_factory,
                    user_account_id,
                    bind_reason="protocol_registration",
                )
            emit(
                "proxy.assigned",
                {
                    "user_account_id": user_account_id,
                    "has_proxy": bool(proxy_url),
                    "use_proxy": bool(input_.use_proxy),
                    "proxy_source": "override" if input_.proxy_url else "account_binding",
                },
            )
            cfg = Config()
            cfg.proxy = proxy_url
            flow = AuthFlow(cfg, trace_callback=self._make_http_trace_callback(emit))
            result = flow.run_register(mail)
            claimed = mail.claim
            if claimed is not None:
                self._set_placeholder_account_email(user_account_id, claimed.email)
            if not result.is_valid():
                raise ProtocolRegistrationWorkflowError("registration finished without session/access token")
            self._write_success_account(user_account_id=user_account_id, result=result, flow=flow)
            mail.mark_used(result.email)
            emit(
                "succeeded",
                {
                    "user_account_id": user_account_id,
                    "email": result.email,
                    "has_session_token": bool(result.session_token),
                    "has_access_token": bool(result.access_token),
                    "chatgpt_account_id": result.chatgpt_account_id,
                },
            )
            return {
                "user_account_id": user_account_id,
                "email": result.email,
                "mode": EMAIL_PROTOCOL_NO_PHONE,
                "has_session_token": bool(result.session_token),
                "has_access_token": bool(result.access_token),
                "mail_claim": _safe_claim_dict(claimed),
            }
        except Exception as exc:
            actual_claim = claimed or mail.claim
            if actual_claim is not None:
                self._set_placeholder_account_email(user_account_id, actual_claim.email)
            emit(
                "failed",
                {
                    "user_account_id": user_account_id,
                    "email": actual_claim.email if actual_claim is not None else "",
                    "error": f"{type(exc).__name__}: {exc}",
                },
                "ERROR",
            )
            try:
                mail.mark_unused(actual_claim.email if actual_claim is not None else "")
            except Exception:
                pass
            self._delete_placeholder_account(user_account_id)
            raise

    def _run_phone_protocol(
        self,
        input_: ProtocolRegistrationInput,
        *,
        work_id: str,
        run_id: str,
    ) -> dict:
        emit = self._make_event_emitter(run_id=run_id, work_id=work_id, mode=PHONE_PROTOCOL_BIND_EMAIL)
        emit("started", {"mail_provider": input_.mail_provider, "project_key": input_.project_key})
        user_account_id = self._create_placeholder_account(email="")
        emit("account.placeholder_created", {"user_account_id": user_account_id, "email": ""})
        mail = RegistrationMailProviderAdapter(
            mail_provider=self._mail_provider,
            caller_id=input_.caller_id,
            task_id=work_id,
            provider=input_.mail_provider,
            project_key=input_.project_key,
            email_domain=input_.email_domain,
            event_callback=emit,
            claim_persist_callback=self._make_claim_persist_callback(work_id),
        )
        try:
            proxy_url = ""
            if input_.proxy_url:
                proxy_url = input_.proxy_url
            elif input_.use_proxy:
                proxy_url = ensure_account_proxy_url(
                    self._session_factory,
                    user_account_id,
                    bind_reason="protocol_phone_registration",
                )
            emit(
                "proxy.assigned",
                {
                    "user_account_id": user_account_id,
                    "has_proxy": bool(proxy_url),
                    "use_proxy": bool(input_.use_proxy),
                    "proxy_source": "override" if input_.proxy_url else "account_binding",
                },
            )
            cfg = Config()
            cfg.proxy = proxy_url
            cfg.phone = _phone_config(input_)
            phone = HeroSmsPhoneProviderAdapter(cfg.phone)
            flow = AuthFlow(cfg, trace_callback=self._make_http_trace_callback(emit))
            result = flow.run_phone_register(mail, phone)
            if not result.is_valid():
                raise ProtocolRegistrationWorkflowError("phone registration finished without session/access token")
            if not result.email:
                raise ProtocolRegistrationWorkflowError("phone registration finished without bound email")
            self._write_success_account(user_account_id=user_account_id, result=result, flow=flow)
            emit(
                "succeeded",
                {
                    "user_account_id": user_account_id,
                    "email": result.email,
                    "phone_number": _mask_phone(result.phone_number),
                    "has_session_token": bool(result.session_token),
                    "has_access_token": bool(result.access_token),
                },
            )
            return {
                "user_account_id": user_account_id,
                "email": result.email,
                "mode": PHONE_PROTOCOL_BIND_EMAIL,
                "phone_number": result.phone_number,
                "phone_dial_code": result.phone_dial_code,
                "phone_country": result.phone_country,
                "has_session_token": bool(result.session_token),
                "has_access_token": bool(result.access_token),
                "mail_claim": _safe_claim_dict(mail.claim),
            }
        except Exception as exc:
            emit(
                "failed",
                {
                    "user_account_id": user_account_id,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                "ERROR",
            )
            self._delete_placeholder_account(user_account_id)
            raise

    def _make_event_emitter(self, *, run_id: str, work_id: str, mode: str) -> TraceEmitter:
        def emit(stage: str, data: dict[str, Any], level: str = "INFO") -> None:
            if not run_id:
                return
            safe_data = dict(data or {})
            safe_data.update({"work_id": work_id, "mode": mode})
            with self._session_factory() as session:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type=f"protocol.register.{stage}",
                    message=f"protocol register {stage}",
                    level=level,
                    data_json=safe_data,
                )
                session.commit()

        return emit

    @staticmethod
    def _make_http_trace_callback(emit: TraceEmitter) -> Callable[[dict[str, Any]], None]:
        def callback(record: dict[str, Any]) -> None:
            status = record.get("status_code")
            level = "WARN"
            try:
                status_int = int(status)
                level = "WARN" if status_int >= 400 else "INFO"
            except Exception:
                level = "INFO"
            emit("http", record, level)

        return callback

    def _make_claim_persist_callback(self, work_id: str) -> Callable[[ClaimedMailAccount], None]:
        def callback(claim: ClaimedMailAccount) -> None:
            if not work_id:
                return
            self._merge_work_output(
                work_id,
                {
                    "email": claim.email,
                    "mail_claim": _safe_claim_dict(claim),
                },
            )

        return callback

    def _merge_work_output(self, work_id: str, patch: dict[str, Any]) -> None:
        with self._session_factory() as session:
            from refactor_app.infrastructure.db.models import WorkItemModel

            work = session.get(WorkItemModel, work_id)
            if work is None:
                return
            current = dict(work.output_json or {})
            current.update(patch)
            work.output_json = current
            work.updated_at = datetime.now(UTC)
            session.commit()

    def _create_placeholder_account(self, *, email: str) -> str:
        now = datetime.now(UTC)
        user_account_id = f"protocol-registered-account-{uuid4()}"
        with self._session_factory() as session:
            session.add(
                UserAccountModel(
                    id=user_account_id,
                    email=email,
                    account_status="registering",
                    session_status="unknown",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        return user_account_id

    def _set_placeholder_account_email(self, user_account_id: str, email: str) -> None:
        if not email:
            return
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is not None and account.account_status == "registering":
                account.email = email
                account.updated_at = now
                session.commit()

    def _write_success_account(
        self,
        *,
        user_account_id: str,
        result: AuthResult,
        flow: AuthFlow,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise ProtocolRegistrationWorkflowError(f"user account not found: {user_account_id}")
            account.email = result.email
            account.phone_number = result.phone_number
            account.phone_dial_code = result.phone_dial_code
            account.phone_country = result.phone_country
            account.password = result.password
            account.access_token = result.access_token
            account.session_token = result.session_token
            account.cookie_header = result.cookie_header or _cookie_header_from_session(flow, "chatgpt.com")
            account.auth_cookie_header = _cookie_header_from_session(flow, "openai.com")
            account.device_id = result.device_id
            account.csrf_token = result.csrf_token
            account.account_status = "active"
            account.session_status = "active"
            account.last_session_refresh_at = now
            account.last_login_error_code = ""
            account.last_login_error_message = ""
            account.updated_at = now
            session.commit()

    def _delete_placeholder_account(self, user_account_id: str) -> None:
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is not None:
                session.delete(account)
            session.commit()


class RegistrationMailProviderAdapter:
    def __init__(
        self,
        *,
        mail_provider: ExternalMailApiPlugin,
        caller_id: str,
        task_id: str,
        provider: str,
        project_key: str,
        email_domain: str,
        event_callback: TraceEmitter | None = None,
        claim_persist_callback: Callable[[ClaimedMailAccount], None] | None = None,
    ) -> None:
        self._mail_provider = mail_provider
        self._caller_id = caller_id
        self._task_id = task_id
        self._provider = provider
        self._project_key = project_key
        self._email_domain = email_domain
        self._event_callback = event_callback
        self._claim_persist_callback = claim_persist_callback
        self.claim: ClaimedMailAccount | None = None
        self.last_persona = None

    def claim_mailbox(self) -> ClaimedMailAccount:
        if self.claim is None:
            self._emit("mail.claim.started", {"provider": self._provider, "project_key": self._project_key})
            self.claim = self._mail_provider.claim_random(
                caller_id=self._caller_id,
                task_id=self._task_id,
                provider=self._provider,
                project_key=self._project_key,
                email_domain=self._email_domain,
            )
            self._emit(
                "mail.claim.succeeded",
                {
                    "email": self.claim.email,
                    "external_account_id": self.claim.account_id,
                    "email_domain": self.claim.email_domain,
                },
            )
            if self._claim_persist_callback is not None:
                self._claim_persist_callback(self.claim)
        return self.claim

    def create_mailbox(self) -> str:
        claim = self.claim_mailbox()
        return claim.email.strip().lower()

    def wait_for_otp(
        self,
        email: str,
        timeout: int = 180,
        issued_after: float | None = None,
        max_polls: int | None = None,
    ) -> str:
        mailbox_email = self._mailbox_email(email)
        self._emit(
            "mail.otp.wait.started",
            {
                "email": mailbox_email,
                "openai_email": email,
                "timeout_s": timeout,
                "issued_after": issued_after,
                "max_polls": max_polls,
            },
        )
        try:
            otp = self._mail_provider.wait_for_otp_by_email(
                email=mailbox_email,
                timeout_s=timeout,
                issued_after=issued_after,
                max_polls=max_polls,
            )
            self._emit(
                "mail.otp.wait.succeeded",
                {"email": mailbox_email, "openai_email": email, "has_code": bool(otp.code)},
            )
            return otp.code
        except Exception as exc:
            self._emit(
                "mail.otp.wait.failed",
                {
                    "email": mailbox_email,
                    "openai_email": email,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                "ERROR",
            )
            raise

    def mark_used(self, email: str) -> None:
        if self.claim is not None:
            mailbox_email = self._mailbox_email(email)
            self._emit(
                "mail.claim.complete.started",
                {"email": mailbox_email, "openai_email": email},
            )
            self._mail_provider.claim_complete(self.claim, result="success", detail=mailbox_email)
            self._emit(
                "mail.claim.complete.succeeded",
                {"email": mailbox_email, "openai_email": email},
            )

    def mark_unused(self, email: str) -> None:
        if self.claim is not None:
            mailbox_email = self._mailbox_email(email)
            self._emit(
                "mail.claim.release.started",
                {"email": mailbox_email, "openai_email": email},
            )
            self._mail_provider.claim_release(
                self.claim,
                reason=f"registration_failed:{mailbox_email}",
            )
            self._emit(
                "mail.claim.release.succeeded",
                {"email": mailbox_email, "openai_email": email},
            )

    def _mailbox_email(self, fallback: str = "") -> str:
        if self.claim is not None and self.claim.email:
            return self.claim.email
        return (fallback or "").strip()

    def _emit(self, stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if self._event_callback is None:
            return
        self._event_callback(stage, data, level)


@dataclass(frozen=True)
class PhoneLease:
    lease_id: str
    phone_e164: str
    masked_phone: str = ""
    phone_national: str = ""
    country_phone_code: str = ""
    provider_country: str = ""
    expires_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class HeroSmsPhoneProviderAdapter:
    def __init__(self, cfg: PhoneConfig) -> None:
        self.cfg = cfg
        self.base_url = str(cfg.base_url or "").strip()
        if not self.base_url:
            raise ProtocolRegistrationWorkflowError("Hero SMS base_url is required")
        self.api_key = str(cfg.api_key or os.getenv(cfg.api_key_env or "HERO_SMS_API_KEY") or "").strip()
        if not self.api_key:
            raise ProtocolRegistrationWorkflowError("Hero SMS API key is required")
        self._client = httpx.Client(timeout=max(1, int(cfg.request_timeout_s or 20)))

    def allocate(self) -> PhoneLease:
        service, countries = self._service_countries()
        attempts = max(1, int(self.cfg.max_number_attempts or 3), len(countries))
        last_error = ""
        for attempt in range(1, attempts + 1):
            country = countries[(attempt - 1) % len(countries)]
            try:
                payload = self._request_json(
                    "getNumberV2",
                    service=service,
                    country=country,
                    maxPrice=self._max_price(country),
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts and _hero_retryable(last_error):
                    continue
                raise
            if payload.get("error") or payload.get("message") in _HERO_FATAL_MESSAGES:
                last_error = str(payload)
                if attempt < attempts and _hero_retryable(last_error):
                    continue
                raise ProtocolRegistrationWorkflowError(f"Hero SMS getNumberV2 failed: {payload}")
            lease_id = str(payload.get("activationId") or payload.get("activation_id") or "").strip()
            if not lease_id:
                raise ProtocolRegistrationWorkflowError(f"Hero SMS getNumberV2 missing activationId: {payload}")
            phone_e164, phone_national, dial = _hero_phone_parts(
                payload.get("phoneNumber") or payload.get("phone_number"),
                payload.get("countryPhoneCode"),
            )
            return PhoneLease(
                lease_id=lease_id,
                phone_e164=phone_e164,
                masked_phone=_mask_phone(phone_e164),
                phone_national=phone_national,
                country_phone_code=dial,
                provider_country=country,
                expires_at=str(payload.get("activationEndTime") or payload.get("activation_end_time") or ""),
                raw=payload,
            )
        raise ProtocolRegistrationWorkflowError(f"Hero SMS getNumberV2 exhausted: {last_error or 'unknown'}")

    def poll_otp(self, lease_id: str) -> str:
        deadline = time.time() + max(1, int(self.cfg.otp_timeout_s or 180))
        interval = max(1.0, float(self.cfg.otp_poll_interval_s or 3.0))
        last_status = ""
        while time.time() < deadline:
            payload = self._request_json("getStatusV2", id=lease_id)
            if payload.get("error") or payload.get("message") in {"NO_ACTIVATION", "BAD_KEY", "BAD_ACTION", "STATUS_CANCEL"}:
                raise ProtocolRegistrationWorkflowError(f"Hero SMS getStatusV2 failed: {payload}")
            code = _extract_otp(payload)
            if code:
                return code
            last_status = str(payload.get("verificationType") or payload.get("status") or "")
            time.sleep(interval)
        raise TimeoutError(f"Hero SMS OTP timeout lease={lease_id} last_status={last_status or 'unknown'}")

    def mark_verified(self, lease_id: str) -> None:
        self._set_status(lease_id, "6")

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        self._set_status(lease_id, "8")

    def _service_countries(self) -> tuple[str, list[str]]:
        service = str(self.cfg.service or "tg").strip()
        countries = [str(v).strip() for v in (self.cfg.countries or []) if str(v).strip()]
        if countries:
            random.shuffle(countries)
        else:
            countries = [str(self.cfg.country or "2").strip()]
        if not service:
            raise ProtocolRegistrationWorkflowError("Hero SMS service is required")
        bad = [country for country in countries if not country.isdigit()]
        if bad:
            raise ProtocolRegistrationWorkflowError(f"Hero SMS country must be numeric: {bad[0]}")
        return service, countries

    def _max_price(self, country: str) -> str:
        price_map = self.cfg.country_max_prices or {}
        if str(country) in price_map:
            return str(price_map[str(country)])
        return str(self.cfg.maxPrice or self.cfg.max_price or "").strip()

    def _request_json(self, action: str, **params: Any) -> dict[str, Any]:
        query = {"api_key": self.api_key, "action": action}
        query.update({k: v for k, v in params.items() if v is not None and v != ""})
        response = self._client.get(self.base_url, params=query)
        if response.is_error:
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS request failed action={action} http_status={response.status_code}"
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS response is not JSON action={action}: {response.text[:200]}"
            ) from exc
        if not isinstance(payload, dict):
            raise ProtocolRegistrationWorkflowError(f"Hero SMS response must be object action={action}")
        return payload

    def _set_status(self, lease_id: str, status: str) -> None:
        if not lease_id:
            return
        response = self._client.get(
            self.base_url,
            params={"api_key": self.api_key, "action": "setStatus", "id": lease_id, "status": status},
        )
        if response.is_error:
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS setStatus failed lease={lease_id} status={status} http_status={response.status_code}"
            )


def _phone_config(input_: ProtocolRegistrationInput) -> PhoneConfig:
    return PhoneConfig(
        enabled=True,
        provider=input_.phone_provider or "hero_sms",
        base_url=input_.phone_base_url or "https://hero-sms.com/stubs/handler_api.php",
        api_key_env=input_.phone_api_key_env or "HERO_SMS_API_KEY",
        country=input_.phone_country or "2",
        countries=input_.phone_countries or [],
        service=input_.phone_service or "tg",
        maxPrice=input_.phone_max_price or "",
        country_max_prices=input_.phone_country_max_prices or {},
        max_number_attempts=max(1, int(input_.phone_max_number_attempts or 3)),
        otp_timeout_s=max(1, int(input_.phone_otp_timeout_s or 180)),
        otp_poll_interval_s=max(1.0, float(input_.phone_otp_poll_interval_s or 3.0)),
    )


def _safe_claim_dict(claim: ClaimedMailAccount | None) -> dict[str, Any]:
    if claim is None:
        return {}
    return {
        "account_id": claim.account_id,
        "email": claim.email,
        "email_domain": claim.email_domain,
        "claim_token": claim.claim_token,
        "caller_id": claim.caller_id,
        "task_id": claim.task_id,
    }


def _cookie_header_from_session(flow: AuthFlow, domain_keyword: str) -> str:
    pairs: list[str] = []
    seen: set[str] = set()
    try:
        cookies = list(flow.session.cookies)
    except Exception:
        cookies = []
    for cookie in cookies:
        name = str(getattr(cookie, "name", "") or "").strip()
        value = str(getattr(cookie, "value", "") or "")
        domain = str(getattr(cookie, "domain", "") or "").lower()
        if not name or name in seen or domain_keyword not in domain:
            continue
        pairs.append(f"{name}={value}")
        seen.add(name)
    return "; ".join(pairs)


def _hero_phone_parts(phone: Any, country_phone_code: Any) -> tuple[str, str, str]:
    raw = re.sub(r"\D+", "", str(phone or ""))
    if not raw:
        raise ProtocolRegistrationWorkflowError("Hero SMS getNumberV2 missing phoneNumber")
    dial = re.sub(r"\D+", "", str(country_phone_code or ""))
    national = raw
    if dial and national.startswith(dial):
        national = national[len(dial):]
    e164_digits = f"{dial}{national}" if dial else raw
    return f"+{e164_digits}", national, dial


def _extract_otp(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("code"),
        payload.get("smsCode"),
        payload.get("verificationCode"),
        payload.get("text"),
        payload.get("message"),
    ]
    sms = payload.get("sms")
    if isinstance(sms, dict):
        candidates.extend([sms.get("code"), sms.get("text"), sms.get("body")])
    if isinstance(sms, list):
        for item in sms:
            if isinstance(item, dict):
                candidates.extend([item.get("code"), item.get("text"), item.get("body")])
            else:
                candidates.append(item)
    for value in candidates:
        match = re.search(r"\b(\d{4,8})\b", str(value or ""))
        if match:
            return match.group(1)
    return ""


def _mask_phone(phone: str) -> str:
    text = str(phone or "")
    if len(text) <= 6:
        return text
    return f"{text[:4]}***{text[-2:]}"


def _hero_retryable(message: str) -> bool:
    text = str(message or "")
    return any(token in text for token in ("NO_NUMBERS", "NO_BALANCE", "SERVER_ERROR", "TIMEOUT", "429"))


_HERO_FATAL_MESSAGES = {"NO_NUMBERS", "NO_BALANCE", "BAD_KEY", "BAD_ACTION", "BAD_COUNTRY", "BAD_SERVICE"}
