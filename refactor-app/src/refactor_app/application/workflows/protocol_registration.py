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

from refactor_app.application.workflows.account_auth import (
    BackfillSessionWorkflow,
    ensure_account_proxy_url,
    release_account_proxy_for_reassign,
)
from refactor_app.infrastructure.db.models import UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_browser import (
    BrowserEmailRegistrationConfig,
    CamoufoxEmailRegistration,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow, AuthResult
from refactor_app.plugins.openai_auth_protocol.config import Config, PhoneConfig

EMAIL_PROTOCOL_NO_PHONE = "email_protocol_no_phone"
EMAIL_BROWSER_NO_PHONE = "email_browser_no_phone"
PHONE_PROTOCOL_BIND_EMAIL = "phone_protocol_bind_email"
ICLOUD_HIDE_MY_EMAIL_PROVIDER = "icloud_hide_my_email"
SUPPORTED_REGISTRATION_MAIL_PROVIDERS = frozenset(
    {
        "outlook",
        "imap",
        "custom",
        "cloudflare_temp_mail",
        ICLOUD_HIDE_MY_EMAIL_PROVIDER,
    }
)


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
    browser_headless: bool = True
    browser_otp_timeout_s: int = 180
    phone_provider: str = "hero_sms"
    phone_base_url: str = "https://hero-sms.com/stubs/handler_api.php"
    phone_api_key_env: str = "HERO_SMS_API_KEY"
    phone_service: str = "dr"
    phone_country: str = ""
    phone_countries: list[str] = field(default_factory=lambda: ["151", "73", "16"])
    phone_max_price: str = "0.05"
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
        hero_sms_api_key: str = "",
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._hero_sms_api_key = str(hero_sms_api_key or "").strip()

    def run(
        self, input_: ProtocolRegistrationInput, *, work_id: str = "", run_id: str = ""
    ) -> dict:
        mode = str(input_.mode or "").strip()
        provider = str(input_.mail_provider or "").strip()
        if provider not in SUPPORTED_REGISTRATION_MAIL_PROVIDERS:
            raise ProtocolRegistrationWorkflowError(
                f"unsupported registration mail provider: {provider}"
            )
        if mode == EMAIL_PROTOCOL_NO_PHONE:
            return self._run_email_protocol(input_, work_id=work_id, run_id=run_id)
        if mode == EMAIL_BROWSER_NO_PHONE:
            return self._run_email_browser(input_, work_id=work_id, run_id=run_id)
        if mode == PHONE_PROTOCOL_BIND_EMAIL:
            return self._run_phone_protocol(input_, work_id=work_id, run_id=run_id)
        raise ProtocolRegistrationWorkflowError(f"unsupported registration mode: {mode}")

    def _run_email_protocol(
        self,
        input_: ProtocolRegistrationInput,
        *,
        work_id: str,
        run_id: str,
    ) -> dict:
        emit = self._make_event_emitter(
            run_id=run_id, work_id=work_id, mode=EMAIL_PROTOCOL_NO_PHONE
        )
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
        self._merge_work_output(work_id, {"user_account_id": user_account_id})
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
            proxy_reassign_count = 0
            while True:
                cfg = Config()
                cfg.proxy = proxy_url
                flow = AuthFlow(cfg, trace_callback=self._make_http_trace_callback(emit))
                try:
                    result = flow.run_register(mail)
                    break
                except Exception as exc:
                    if not (
                        input_.use_proxy
                        and not input_.proxy_url
                        and "cloudflare_csrf_403_after_3_retries" in str(exc).lower()
                    ):
                        raise
                    released_proxy_id = release_account_proxy_for_reassign(
                        self._session_factory,
                        user_account_id,
                        error_code="cloudflare_csrf_403_after_3_retries",
                        error_message=str(exc),
                    )
                    proxy_reassign_count += 1
                    emit(
                        "proxy.reassign_after_cloudflare_403",
                        {
                            "user_account_id": user_account_id,
                            "released_proxy_id": released_proxy_id,
                            "proxy_reassign_count": proxy_reassign_count,
                        },
                        "WARN",
                    )
                    proxy_url = ensure_account_proxy_url(
                        self._session_factory,
                        user_account_id,
                        bind_reason="protocol_registration_cloudflare_retry",
                    )
            claimed = mail.claim
            if claimed is not None:
                self._set_placeholder_account_email(user_account_id, claimed.email)
            if not result.is_valid():
                raise ProtocolRegistrationWorkflowError(
                    "registration finished without session/access token"
                )
            self._write_success_account(
                user_account_id=user_account_id,
                result=result,
                flow=flow,
                account_email=claimed.email if claimed is not None else result.email,
            )
            mail.mark_used(result.email)
            account_detection = self._detect_account_spaces_after_registration(
                user_account_id=user_account_id,
                result=result,
                flow=flow,
                proxy_url=proxy_url,
                run_id=run_id,
            )
            emit(
                "succeeded",
                {
                    "user_account_id": user_account_id,
                    "email": result.email,
                    "has_session_token": bool(result.session_token),
                    "has_access_token": bool(result.access_token),
                    "chatgpt_account_id": result.chatgpt_account_id,
                    "account_detection": account_detection,
                },
            )
            return {
                "user_account_id": user_account_id,
                "email": result.email,
                "mode": EMAIL_PROTOCOL_NO_PHONE,
                "has_session_token": bool(result.session_token),
                "has_access_token": bool(result.access_token),
                "account_detection": account_detection,
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

    def _run_email_browser(
        self,
        input_: ProtocolRegistrationInput,
        *,
        work_id: str,
        run_id: str,
    ) -> dict:
        emit = self._make_event_emitter(run_id=run_id, work_id=work_id, mode=EMAIL_BROWSER_NO_PHONE)
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
        self._merge_work_output(work_id, {"user_account_id": user_account_id})
        emit("account.placeholder_created", {"user_account_id": user_account_id, "email": ""})
        claimed: ClaimedMailAccount | None = None
        try:
            proxy_url = ""
            if input_.proxy_url:
                proxy_url = input_.proxy_url
            elif input_.use_proxy:
                proxy_url = ensure_account_proxy_url(
                    self._session_factory,
                    user_account_id,
                    bind_reason="browser_registration",
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
            browser = CamoufoxEmailRegistration(
                BrowserEmailRegistrationConfig(
                    proxy_url=proxy_url,
                    headless=bool(input_.browser_headless),
                    otp_timeout_s=max(1, int(input_.browser_otp_timeout_s or 180)),
                    work_id=work_id,
                ),
                event_callback=emit,
            )
            result = browser.run(mail)
            claimed = mail.claim
            if claimed is not None:
                self._set_placeholder_account_email(user_account_id, claimed.email)
            if not result.is_valid():
                raise ProtocolRegistrationWorkflowError(
                    "browser registration finished without session/access token"
                )
            self._write_success_account(
                user_account_id=user_account_id,
                result=result,
                flow=None,
                account_email=claimed.email if claimed is not None else result.email,
            )
            mail.mark_used(result.email)
            account_detection = self._detect_account_spaces_after_registration(
                user_account_id=user_account_id,
                result=result,
                flow=None,
                proxy_url=proxy_url,
                run_id=run_id,
            )
            emit(
                "succeeded",
                {
                    "user_account_id": user_account_id,
                    "email": result.email,
                    "has_session_token": bool(result.session_token),
                    "has_access_token": bool(result.access_token),
                    "account_detection": account_detection,
                },
            )
            return {
                "user_account_id": user_account_id,
                "email": result.email,
                "mode": EMAIL_BROWSER_NO_PHONE,
                "has_session_token": bool(result.session_token),
                "has_access_token": bool(result.access_token),
                "account_detection": account_detection,
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
        emit = self._make_event_emitter(
            run_id=run_id, work_id=work_id, mode=PHONE_PROTOCOL_BIND_EMAIL
        )
        emit("started", {"mail_provider": input_.mail_provider, "project_key": input_.project_key})
        user_account_id = self._create_placeholder_account(email="")
        self._merge_work_output(work_id, {"user_account_id": user_account_id})
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
            phone = HeroSmsPhoneProviderAdapter(
                cfg.phone,
                api_key=self._hero_sms_api_key,
                event_callback=emit,
            )
            flow = AuthFlow(cfg, trace_callback=self._make_http_trace_callback(emit))
            result = flow.run_phone_register(mail, phone)
            if not result.is_valid():
                raise ProtocolRegistrationWorkflowError(
                    "phone registration finished without session/access token"
                )
            if not result.email:
                raise ProtocolRegistrationWorkflowError(
                    "phone registration finished without bound email"
                )
            self._write_success_account(
                user_account_id=user_account_id,
                result=result,
                flow=flow,
                account_email=mail.claim.email if mail.claim is not None else result.email,
            )
            account_detection = self._detect_account_spaces_after_registration(
                user_account_id=user_account_id,
                result=result,
                flow=flow,
                proxy_url=proxy_url,
                run_id=run_id,
            )
            emit(
                "succeeded",
                {
                    "user_account_id": user_account_id,
                    "email": result.email,
                    "phone_number": _mask_phone(result.phone_number),
                    "has_session_token": bool(result.session_token),
                    "has_access_token": bool(result.access_token),
                    "account_detection": account_detection,
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
                "account_detection": account_detection,
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
        flow: AuthFlow | None,
        account_email: str,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise ProtocolRegistrationWorkflowError(
                    f"user account not found: {user_account_id}"
                )
            account.email = account_email or result.email
            account.phone_number = result.phone_number
            account.phone_dial_code = result.phone_dial_code
            account.phone_country = result.phone_country
            account.password = result.password
            # The registration response token may reflect the last selected workspace.
            account.access_token = ""
            account.session_token = result.session_token
            account.cookie_header = result.cookie_header or (
                _cookie_header_from_session(flow, "chatgpt.com") if flow is not None else ""
            )
            account.auth_cookie_header = result.auth_cookie_header or (
                _cookie_header_from_session(flow, "openai.com") if flow is not None else ""
            )
            account.device_id = result.device_id
            account.csrf_token = result.csrf_token
            account.account_status = "active"
            account.session_status = "active"
            account.last_session_refresh_at = now
            account.last_login_error_code = ""
            account.last_login_error_message = ""
            account.updated_at = now
            session.commit()

    def _detect_account_spaces_after_registration(
        self,
        *,
        user_account_id: str,
        result: AuthResult,
        flow: AuthFlow | None,
        proxy_url: str,
        run_id: str,
    ) -> dict:
        cookie_header = result.cookie_header or (
            _cookie_header_from_session(flow, "chatgpt.com") if flow is not None else ""
        )
        return BackfillSessionWorkflow(
            session_factory=self._session_factory,
            mail_provider=self._mail_provider,
        ).detect_account_spaces_from_session(
            user_account_id=user_account_id,
            access_token=result.access_token,
            cookie_header=cookie_header,
            proxy_url=proxy_url,
            oai_device_id=result.device_id,
            session_chatgpt_account_id=result.chatgpt_account_id,
            session_chatgpt_account_structure=result.chatgpt_account_structure,
            session_chatgpt_account_plan_type=result.chatgpt_account_plan_type,
            require_personal_access_token=False,
            run_id=run_id,
        )

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
        self._provider = str(provider or "").strip()
        self._project_key = project_key
        self._email_domain = "" if self._provider == ICLOUD_HIDE_MY_EMAIL_PROVIDER else email_domain
        self._event_callback = event_callback
        self._claim_persist_callback = claim_persist_callback
        self.claim: ClaimedMailAccount | None = None
        self.last_persona = None

    def claim_mailbox(self) -> ClaimedMailAccount:
        if self.claim is None:
            self._emit(
                "mail.claim.started", {"provider": self._provider, "project_key": self._project_key}
            )
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
            claim = self.claim
            mailbox_email = self._mailbox_email(email)
            self._emit(
                "mail.claim.release.started",
                {"email": mailbox_email, "openai_email": email},
            )
            try:
                self._mail_provider.claim_release(
                    claim,
                    reason=f"registration_failed:{mailbox_email}",
                )
                self._emit(
                    "mail.claim.release.succeeded",
                    {"email": mailbox_email, "openai_email": email},
                )
            finally:
                self.claim = None

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
    def __init__(
        self,
        cfg: PhoneConfig,
        *,
        api_key: str = "",
        event_callback: TraceEmitter | None = None,
    ) -> None:
        self.cfg = cfg
        self.base_url = str(cfg.base_url or "").strip()
        if not self.base_url:
            raise ProtocolRegistrationWorkflowError("Hero SMS base_url is required")
        self.api_key = str(
            api_key or cfg.api_key or os.getenv(cfg.api_key_env or "HERO_SMS_API_KEY") or ""
        ).strip()
        if not self.api_key:
            raise ProtocolRegistrationWorkflowError("Hero SMS API key is required")
        self._event_callback = event_callback
        self._client = httpx.Client(
            timeout=max(1, int(cfg.request_timeout_s or 20)),
            headers={"Accept": "*/*", "User-Agent": "curl/8.7.1"},
        )

    def allocate(self) -> PhoneLease:
        service, countries = self._service_countries()
        attempts = max(1, int(self.cfg.max_number_attempts or 3), len(countries))
        last_error = ""
        for attempt in range(1, attempts + 1):
            country = countries[(attempt - 1) % len(countries)]
            self._emit(
                "phone.allocate.started",
                {
                    "attempt": attempt,
                    "max_attempts": attempts,
                    "service": service,
                    "country": country,
                },
            )
            try:
                payload = self._request_json(
                    "getNumberV2",
                    service=service,
                    country=country,
                    maxPrice=self._max_price(country),
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts and _hero_allocate_retryable(last_error):
                    self._emit(
                        "phone.allocate.retrying",
                        {"attempt": attempt, "country": country, "error": last_error[:300]},
                        "WARN",
                    )
                    continue
                raise
            if payload.get("error") or payload.get("message") in _HERO_FATAL_MESSAGES:
                last_error = str(payload)
                if attempt < attempts and _hero_allocate_retryable(last_error):
                    self._emit(
                        "phone.allocate.retrying",
                        {"attempt": attempt, "country": country, "error": last_error[:300]},
                        "WARN",
                    )
                    continue
                raise ProtocolRegistrationWorkflowError(f"Hero SMS getNumberV2 failed: {payload}")
            lease_id = str(
                payload.get("activationId") or payload.get("activation_id") or ""
            ).strip()
            if not lease_id:
                raise ProtocolRegistrationWorkflowError(
                    f"Hero SMS getNumberV2 missing activationId: {payload}"
                )
            phone_e164, phone_national, dial = _hero_phone_parts(
                payload.get("phoneNumber") or payload.get("phone_number"),
                payload.get("countryPhoneCode"),
            )
            lease = PhoneLease(
                lease_id=lease_id,
                phone_e164=phone_e164,
                masked_phone=_mask_phone(phone_e164),
                phone_national=phone_national,
                country_phone_code=dial,
                provider_country=country,
                expires_at=str(
                    payload.get("activationEndTime") or payload.get("activation_end_time") or ""
                ),
                raw=payload,
            )
            self._emit(
                "phone.allocate.succeeded",
                {
                    "lease_id": lease_id,
                    "phone": lease.masked_phone,
                    "country": country,
                    "dial_code": dial,
                },
            )
            return lease
        raise ProtocolRegistrationWorkflowError(
            f"Hero SMS getNumberV2 exhausted: {last_error or 'unknown'}"
        )

    def poll_otp(self, lease_id: str) -> str:
        deadline = time.time() + max(1, int(self.cfg.otp_timeout_s or 180))
        interval = max(1.0, float(self.cfg.otp_poll_interval_s or 3.0))
        last_status = ""
        self._emit(
            "phone.otp.wait.started",
            {"lease_id": lease_id, "timeout_s": int(self.cfg.otp_timeout_s or 180)},
        )
        while time.time() < deadline:
            try:
                payload = self._request_json("getStatusV2", id=lease_id)
            except Exception as exc:
                if _hero_status_retryable(str(exc)):
                    last_status = str(exc)[:300]
                    self._emit(
                        "phone.otp.poll.retrying",
                        {"lease_id": lease_id, "error": last_status},
                        "WARN",
                    )
                    time.sleep(interval)
                    continue
                raise
            if payload.get("error") or payload.get("message") in {
                "NO_ACTIVATION",
                "BAD_KEY",
                "BAD_ACTION",
                "STATUS_CANCEL",
            }:
                raise ProtocolRegistrationWorkflowError(f"Hero SMS getStatusV2 failed: {payload}")
            code = _extract_otp(payload)
            if code:
                self._emit("phone.otp.wait.succeeded", {"lease_id": lease_id, "has_code": True})
                return code
            last_status = str(payload.get("verificationType") or payload.get("status") or "")
            time.sleep(interval)
        self._emit(
            "phone.otp.wait.failed",
            {"lease_id": lease_id, "error": f"timeout last_status={last_status or 'unknown'}"},
            "ERROR",
        )
        raise TimeoutError(
            f"Hero SMS OTP timeout lease={lease_id} last_status={last_status or 'unknown'}"
        )

    def mark_verified(self, lease_id: str) -> None:
        self._set_status(lease_id, "6", reason="verified")

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        self._set_status(
            lease_id,
            "8",
            reason=reason or "failed",
            retry_on_early_cancel="otp_timeout" in str(reason or "").lower(),
        )

    def _service_countries(self) -> tuple[str, list[str]]:
        service = str(self.cfg.service or "dr").strip()
        countries = [str(v).strip() for v in (self.cfg.countries or []) if str(v).strip()]
        if countries:
            random.shuffle(countries)
        else:
            countries = [str(self.cfg.country or "").strip()]
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
        return str(self.cfg.maxPrice or self.cfg.max_price or "0.05").strip()

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
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS response must be object action={action}"
            )
        return payload

    def _set_status(
        self,
        lease_id: str,
        status: str,
        *,
        reason: str,
        retry_on_early_cancel: bool = False,
    ) -> bool:
        if not lease_id:
            return False
        attempts = max(1, int(self.cfg.cancel_retry_attempts or 4)) if retry_on_early_cancel else 1
        interval = max(1.0, float(self.cfg.cancel_retry_interval_s or 5.0))
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.get(
                    self.base_url,
                    params={
                        "api_key": self.api_key,
                        "action": "setStatus",
                        "id": lease_id,
                        "status": status,
                    },
                )
                body = str(response.text or "").strip()
                if response.is_error:
                    raise ProtocolRegistrationWorkflowError(
                        "Hero SMS setStatus failed "
                        f"lease={lease_id} status={status} "
                        f"http_status={response.status_code} body={body[:200]}"
                    )
                upper = body.upper()
                if upper.startswith("BAD_") or upper == "NO_ACTIVATION":
                    raise ProtocolRegistrationWorkflowError(
                        "Hero SMS setStatus rejected "
                        f"lease={lease_id} status={status} body={body[:200]}"
                    )
                self._emit(
                    "phone.status.succeeded",
                    {"lease_id": lease_id, "status": status, "reason": reason},
                )
                return True
            except Exception as exc:
                if (
                    status == "8"
                    and retry_on_early_cancel
                    and _hero_cancel_too_early(str(exc))
                    and attempt < attempts
                ):
                    self._emit(
                        "phone.status.retrying",
                        {
                            "lease_id": lease_id,
                            "status": status,
                            "reason": reason,
                            "attempt": attempt,
                            "error": str(exc)[:300],
                        },
                        "WARN",
                    )
                    time.sleep(interval)
                    continue
                self._emit(
                    "phone.status.failed",
                    {
                        "lease_id": lease_id,
                        "status": status,
                        "reason": reason,
                        "error": str(exc)[:300],
                    },
                    "WARN",
                )
                return False
        return False

    def _emit(self, stage: str, data: dict[str, Any], level: str = "INFO") -> None:
        if self._event_callback is not None:
            self._event_callback(stage, data, level)


def _phone_config(input_: ProtocolRegistrationInput) -> PhoneConfig:
    return PhoneConfig(
        enabled=True,
        provider=input_.phone_provider or "hero_sms",
        base_url=input_.phone_base_url or "https://hero-sms.com/stubs/handler_api.php",
        api_key_env=input_.phone_api_key_env or "HERO_SMS_API_KEY",
        country=input_.phone_country,
        countries=input_.phone_countries or [],
        service=input_.phone_service or "dr",
        maxPrice=input_.phone_max_price or "0.05",
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
    raw_phone = str(phone or "").strip()
    if not raw_phone:
        raise ProtocolRegistrationWorkflowError("Hero SMS getNumberV2 missing phoneNumber")
    if "*" in raw_phone:
        raise ProtocolRegistrationWorkflowError(
            "Hero SMS returned a masked phoneNumber; a complete number is required"
        )
    raw = re.sub(r"\D+", "", raw_phone)
    if not raw:
        raise ProtocolRegistrationWorkflowError("Hero SMS getNumberV2 phoneNumber has no digits")
    dial = re.sub(r"\D+", "", str(country_phone_code or ""))
    national = raw
    if dial and national.startswith(dial):
        national = national[len(dial) :]
    if dial and national.startswith("0"):
        national = national[1:]
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
    call = payload.get("call")
    for section in (sms, call):
        if isinstance(section, dict):
            candidates.extend([section.get("code"), section.get("text"), section.get("body")])
        if not isinstance(section, list):
            continue
        for item in section:
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


def _hero_allocate_retryable(message: str) -> bool:
    upper = str(message or "").upper()
    if any(token in upper for token in ("BAD_KEY", "NO_BALANCE")):
        return False
    return any(
        token in upper
        for token in (
            "HTTP_STATUS=409",
            "HTTP_STATUS=429",
            "HTTP_STATUS=500",
            "HTTP_STATUS=502",
            "HTTP_STATUS=503",
            "HTTP_STATUS=504",
            "CONNECT",
            "TLS/SSL",
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
    )


def _hero_status_retryable(message: str) -> bool:
    upper = str(message or "").upper()
    if any(token in upper for token in ("BAD_KEY", "BAD_ACTION", "STATUS_CANCEL", "NO_ACTIVATION")):
        return False
    return any(
        token in upper
        for token in (
            "HTTP_STATUS=409",
            "HTTP_STATUS=429",
            "HTTP_STATUS=500",
            "HTTP_STATUS=502",
            "HTTP_STATUS=503",
            "HTTP_STATUS=504",
            "CONNECT",
            "TLS/SSL",
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
    )


def _hero_cancel_too_early(message: str) -> bool:
    text = str(message or "")
    return any(
        token in text
        for token in (
            "EARLY_CANCEL_DENIED",
            "Cannot terminate activation",
            "Minimum activation period",
            "minActivationTime",
        )
    )


_HERO_FATAL_MESSAGES = {
    "NO_NUMBERS",
    "NO_BALANCE",
    "BAD_KEY",
    "BAD_ACTION",
    "BAD_COUNTRY",
    "BAD_SERVICE",
}
