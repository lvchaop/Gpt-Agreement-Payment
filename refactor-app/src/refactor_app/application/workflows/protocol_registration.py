from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy.orm import Session

try:  # pragma: no cover - fcntl is available on the supported host platforms.
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

from refactor_app.application.workflows.account_auth import (
    BackfillRtWorkflow,
    BackfillSessionWorkflow,
)
from refactor_app.application.workflows.proxy_locale import (
    accept_language_for_proxy_country,
    locale_for_proxy_country,
)
from refactor_app.application.workflows.registration_proxy import (
    CliproxyProxy,
    resolve_cliproxy_proxy,
)
from refactor_app.config.browser_fingerprint import browser_fingerprint_for_email
from refactor_app.infrastructure.db.models import UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.hero_email import (
    HERO_EMAIL_PROVIDERS,
    HERO_GMAIL_PROVIDER,
    HERO_YANDEX_PROVIDER,
    HeroEmailPlugin,
)
from refactor_app.plugins.mail_external_api.client import ClaimedMailAccount
from refactor_app.plugins.mail_external_api.plugin import (
    ExternalMailApiPlugin,
    prepare_domain_mailbox,
)
from refactor_app.plugins.openai_auth_browser import (
    BrowserEmailRegistrationConfig,
    CamoufoxEmailRegistration,
)
from refactor_app.plugins.openai_auth_browser.phone_email_registration import (
    BrowserPhoneEmailRegistration,
    BrowserPhoneEmailRegistrationConfig,
)
from refactor_app.plugins.openai_auth_protocol.account_security import (
    AccountSecuritySetupResult,
    ProtocolAccountSecurity,
    ProtocolAccountSecurityConfig,
)
from refactor_app.plugins.openai_auth_protocol.auth_flow import AuthFlow, AuthResult
from refactor_app.plugins.openai_auth_protocol.codex_browser_rt import BrowserPhoneOtpProvider
from refactor_app.plugins.openai_auth_protocol.config import Config, PhoneConfig
from refactor_app.plugins.twofauth import TwoFAuthClient

logger = logging.getLogger(__name__)

EMAIL_PROTOCOL_NO_PHONE = "email_protocol_no_phone"
EMAIL_BROWSER_NO_PHONE = "email_browser_no_phone"
PHONE_PROTOCOL_BIND_EMAIL = "phone_protocol_bind_email"
PHONE_BROWSER_BIND_EMAIL = "phone_browser_bind_email"
EMAIL_REGISTRATION_MODES = frozenset(
    {
        EMAIL_PROTOCOL_NO_PHONE,
        EMAIL_BROWSER_NO_PHONE,
    }
)
SECURITY_REGISTRATION_MODES = EMAIL_REGISTRATION_MODES | frozenset({PHONE_BROWSER_BIND_EMAIL})
ICLOUD_HIDE_MY_EMAIL_PROVIDER = "icloud_hide_my_email"
CLOUDFLARE_TEMP_MAIL_PROVIDER = "cloudflare_temp_mail"
SECURITY_REGISTRATION_MAIL_PROVIDERS = frozenset(
    {
        ICLOUD_HIDE_MY_EMAIL_PROVIDER,
        HERO_GMAIL_PROVIDER,
        HERO_YANDEX_PROVIDER,
    }
)
SUPPORTED_REGISTRATION_MAIL_PROVIDERS = frozenset(
    {
        "outlook",
        "imap",
        "custom",
        CLOUDFLARE_TEMP_MAIL_PROVIDER,
        ICLOUD_HIDE_MY_EMAIL_PROVIDER,
        HERO_GMAIL_PROVIDER,
        HERO_YANDEX_PROVIDER,
    }
)

_DISABLED_YANDEX_EMAIL_DOMAINS = frozenset({"yandex.com"})


def _validate_registration_email_domain(email: str) -> None:
    domain = str(email or "").strip().lower().rpartition("@")[2].rstrip(".")
    if domain in _DISABLED_YANDEX_EMAIL_DOMAINS:
        raise ProtocolRegistrationWorkflowError(
            f"Yandex email domain is temporarily disabled: {domain}"
        )


def registration_mail_provider_requires_security(provider: str) -> bool:
    return str(provider or "").strip() in SECURITY_REGISTRATION_MAIL_PROVIDERS


def registration_mode_requires_security(mode: str) -> bool:
    return str(mode or "").strip() in SECURITY_REGISTRATION_MODES


def registration_otp_code_source(*, mode: str, mail_provider: str) -> str:
    del mode, mail_provider
    return "content"


class ProtocolRegistrationWorkflowError(RuntimeError):
    pass


TraceEmitter = Callable[[str, dict[str, Any], str], None]


@dataclass(frozen=True)
class ProtocolRegistrationInput:
    mode: str
    fixed_email: str = ""
    use_proxy: bool = True
    proxy_url: str = ""
    proxy_country: str = "US"
    # Optional Cliproxy traffic selectors. The provider accepts either a
    # state or an ASN in addition to the country; the resolver validates that
    # they are not supplied together.
    proxy_state: str = ""
    proxy_asn: str = ""
    mail_provider: str = "outlook"
    email_domain: str = ""
    project_key: str = "openai-register"
    caller_id: str = "refactor-app-protocol-registration"
    browser_headless: bool = True
    browser_otp_timeout_s: int = 180
    browser_close_delay_s: float = 10.0
    browser_log_enabled: bool = False
    browser_log_capture_bodies: bool = False
    browser_log_max_body_chars: int = 20_000
    browser_backend: str = "camoufox"
    phone_provider: str = "grizzly_sms"
    phone_base_url: str = "https://api.grizzlysms.com/stubs/handler_api.php"
    phone_api_key_env: str = "GRIZZLY_SMS_API_KEY"
    phone_service: str = "dr"
    phone_country: str = ""
    phone_countries: list[str] = field(default_factory=lambda: ["187"])
    phone_max_price: str = "0.18"
    phone_country_max_prices: dict[str, str] = field(default_factory=dict)
    phone_max_number_attempts: int = 3
    phone_request_timeout_s: int = 20
    phone_otp_timeout_s: int = 180
    phone_otp_poll_interval_s: float = 3.0


@dataclass(frozen=True)
class _RegistrationAttempt:
    result: AuthResult
    flow: AuthFlow | None
    proxy_url: str
    proxy_country: str = ""


def _close_auth_flow(flow: AuthFlow | None) -> None:
    if flow is None:
        return
    try:
        flow.close()
    except Exception as exc:
        logger.warning("AuthFlow close failed: %s", exc)


class ProtocolRegistrationWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin | HeroEmailPlugin,
        hero_sms_api_key: str = "",
        twofauth_client: TwoFAuthClient | None = None,
        authorize_codex_after_security: bool = False,
        promotion_check_enabled: bool = False,
        codex_phone_provider: BrowserPhoneOtpProvider | None = None,
        totp_code_resolver: Callable[[str], str] | None = None,
        resume_mail_claim: ClaimedMailAccount | None = None,
        cloakbrowser_license_key: str = "",
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._hero_sms_api_key = str(hero_sms_api_key or "").strip()
        self._twofauth_client = twofauth_client
        self._authorize_codex_after_security = bool(authorize_codex_after_security)
        self._promotion_check_enabled = bool(promotion_check_enabled)
        self._codex_phone_provider = codex_phone_provider
        self._totp_code_resolver = totp_code_resolver
        self._resume_mail_claim = resume_mail_claim
        self._cloakbrowser_license_key = str(cloakbrowser_license_key or "").strip()

    def run(
        self, input_: ProtocolRegistrationInput, *, work_id: str = "", run_id: str = ""
    ) -> dict:
        mode = str(input_.mode or "").strip()
        provider = str(input_.mail_provider or "").strip()
        if provider not in SUPPORTED_REGISTRATION_MAIL_PROVIDERS:
            raise ProtocolRegistrationWorkflowError(
                f"unsupported registration mail provider: {provider}"
            )
        if provider in HERO_EMAIL_PROVIDERS and str(input_.fixed_email or "").strip():
            raise ProtocolRegistrationWorkflowError(
                f"{provider} requires a purchased Hero activation; fixed_email is not supported"
            )
        runners = {
            EMAIL_PROTOCOL_NO_PHONE: self._execute_email_protocol,
            EMAIL_BROWSER_NO_PHONE: self._execute_email_browser,
            PHONE_PROTOCOL_BIND_EMAIL: self._execute_phone_protocol,
            PHONE_BROWSER_BIND_EMAIL: self._execute_phone_browser,
        }
        runner = runners.get(mode)
        if runner is None:
            raise ProtocolRegistrationWorkflowError(f"unsupported registration mode: {mode}")
        return self._run_registration_lifecycle(
            input_,
            mode=mode,
            work_id=work_id,
            run_id=run_id,
            runner=runner,
        )

    def _run_registration_lifecycle(
        self,
        input_: ProtocolRegistrationInput,
        *,
        mode: str,
        work_id: str,
        run_id: str,
        runner: Callable[..., _RegistrationAttempt],
    ) -> dict:
        # Keep the callback's historical one-argument seam so integrations and
        # test doubles that override it remain compatible.
        self._active_run_id = run_id
        emit = self._make_event_emitter(run_id=run_id, work_id=work_id, mode=mode)
        emit("started", {"mail_provider": input_.mail_provider, "project_key": input_.project_key})
        mail = RegistrationMailProviderAdapter(
            mail_provider=self._mail_provider,
            caller_id=input_.caller_id,
            task_id=work_id,
            provider=input_.mail_provider,
            project_key=input_.project_key,
            email_domain=input_.email_domain,
            fixed_email=input_.fixed_email,
            otp_code_source=registration_otp_code_source(
                mode=mode,
                mail_provider=input_.mail_provider,
            ),
            event_callback=emit,
            claim_persist_callback=self._make_claim_persist_callback(work_id),
            existing_claim=self._resume_mail_claim,
        )
        user_account_id = ""
        account_persisted = False
        attempt: _RegistrationAttempt | None = None
        try:
            claimed = mail.claim_mailbox()
            target_email = claimed.email.strip()
            _validate_registration_email_domain(target_email)
            user_account_id = self._create_placeholder_account(email=target_email)
            self._merge_work_output(
                work_id,
                {"user_account_id": user_account_id, "email": target_email},
            )
            emit(
                "account.placeholder_created",
                {"user_account_id": user_account_id, "email": target_email},
            )
            proxy_request = {
                "target_email": target_email,
                "country_code": input_.proxy_country,
            }
            # Keep the legacy resolver call shape when no selector was
            # requested; integrations commonly monkeypatch this seam.
            if input_.proxy_state:
                proxy_request["state"] = input_.proxy_state
            if input_.proxy_asn:
                proxy_request["asn"] = input_.proxy_asn
            proxy = self._resolve_registration_proxy(**proxy_request)
            emit(
                "proxy.assigned",
                {
                    "user_account_id": user_account_id,
                    "has_proxy": True,
                    "proxy_type": "static_proxy",
                    "proxy_mode": proxy.proxy_mode,
                    "proxy_source": proxy.proxy_source,
                    "proxy_provider": proxy.provider,
                    "proxy_country": proxy.country_code,
                    "proxy_state": proxy.route_state,
                    "proxy_asn": proxy.route_asn,
                    "proxy_egress_ip": proxy.egress_ip,
                    "proxy_sid_source": proxy.sid_source,
                    "proxy_probe_attempts": proxy.probe_attempts,
                },
            )
            attempt = runner(
                input_,
                mail=mail,
                user_account_id=user_account_id,
                work_id=work_id,
                proxy_url=proxy.proxy_url,
                proxy_mode=proxy.proxy_mode,
                emit=emit,
            )
            result = attempt.result
            if not result.is_valid():
                raise ProtocolRegistrationWorkflowError(
                    f"{mode} finished without session/access token"
                )
            if mode in (PHONE_PROTOCOL_BIND_EMAIL, PHONE_BROWSER_BIND_EMAIL) and not result.email:
                raise ProtocolRegistrationWorkflowError(
                    "phone registration finished without bound email"
                )
            if registration_mode_requires_security(mode) and not result.password_configured:
                raise ProtocolRegistrationWorkflowError(
                    "email registration finished without configured password"
                )
            _hydrate_auth_result_cookie_headers(result, attempt.flow)
            try:
                account_detection = self._detect_account_spaces_after_registration(
                    user_account_id=user_account_id,
                    result=result,
                    flow=attempt.flow,
                    proxy_url=attempt.proxy_url,
                    proxy_country=attempt.proxy_country,
                    run_id=run_id,
                )
            except Exception as exc:
                account_detection = {
                    "accounts_check_succeeded": False,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                }
                emit(
                    "account_detection.failed",
                    {
                        "user_account_id": user_account_id,
                        "email": result.email,
                        **account_detection,
                    },
                    "WARN",
                )
            security_setup = self._run_post_registration_security(
                input_,
                result=result,
                flow=attempt.flow,
                proxy_url=attempt.proxy_url,
                proxy_country=proxy.country_code,
                emit=emit,
            )
            self._write_success_account(
                user_account_id=user_account_id,
                result=result,
                flow=attempt.flow,
                account_email=claimed.email if claimed is not None else result.email,
                security_setup=security_setup,
            )
            account_persisted = True
            mail.mark_used(result.email)
            promotion_check = self._run_post_registration_promotion_check(
                input_,
                user_account_id=user_account_id,
                registration_proxy=proxy,
                run_id=run_id,
                emit=emit,
            )
            codex_authorization = self._run_post_registration_codex_authorization(
                input_,
                user_account_id=user_account_id,
                security_setup=security_setup,
                proxy_url=attempt.proxy_url,
                run_id=run_id,
                emit=emit,
            )
            output = {
                "user_account_id": user_account_id,
                "email": result.email,
                "mode": mode,
                "has_session_token": bool(result.session_token),
                "has_access_token": bool(result.access_token),
                "account_detection": account_detection,
                "mail_claim": _safe_claim_dict(claimed),
                "proxy_provider": proxy.provider,
                "proxy_country": proxy.country_code,
                "proxy_state": proxy.route_state,
                "proxy_asn": proxy.route_asn,
                "proxy_egress_ip": proxy.egress_ip,
                "proxy_sid_source": proxy.sid_source,
                "proxy_probe_attempts": proxy.probe_attempts,
            }
            if promotion_check is not None:
                output["promotion_check"] = promotion_check
            if security_setup is not None:
                output["security_setup"] = security_setup.to_dict()
            if codex_authorization is not None:
                output["codex_authorization"] = codex_authorization
            if mode in (PHONE_PROTOCOL_BIND_EMAIL, PHONE_BROWSER_BIND_EMAIL):
                output.update(
                    {
                        "phone_number": result.phone_number,
                        "phone_dial_code": result.phone_dial_code,
                        "phone_country": result.phone_country,
                    }
                )
            emit(
                "succeeded",
                {
                    **output,
                    "phone_number": _mask_phone(result.phone_number),
                    "mail_claim": bool(claimed),
                },
            )
            return output
        except Exception as exc:
            actual_claim = mail.claim
            if actual_claim is not None and user_account_id and not account_persisted:
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
            if not account_persisted:
                try:
                    mail.mark_unused(actual_claim.email if actual_claim is not None else "")
                except Exception:
                    pass
                if user_account_id:
                    self._delete_placeholder_account(user_account_id)
            raise
        finally:
            _close_auth_flow(attempt.flow if attempt is not None else None)

    def _resolve_registration_proxy(
        self,
        *,
        target_email: str,
        country_code: str,
        state: str = "",
        asn: str = "",
    ) -> CliproxyProxy:
        proxy_request = {
            "email": target_email,
            "country_code": country_code,
        }
        if state:
            proxy_request["state"] = state
        if asn:
            proxy_request["asn"] = asn
        return resolve_cliproxy_proxy(**proxy_request)

    def _execute_email_protocol(
        self,
        input_: ProtocolRegistrationInput,
        *,
        mail: RegistrationMailProviderAdapter,
        user_account_id: str,
        work_id: str,
        proxy_url: str,
        proxy_mode: str = "cliproxy_sticky",
        emit: TraceEmitter,
    ) -> _RegistrationAttempt:
        del user_account_id, work_id
        claimed_email = str(getattr(getattr(mail, "claim", None), "email", "") or "").strip()
        cfg = Config()
        cfg.proxy = proxy_url
        cfg.proxy_meta = {
            "register": {
                "region": input_.proxy_country.upper(),
                "country_code": input_.proxy_country.upper(),
                "mode": proxy_mode,
            }
        }
        if claimed_email:
            cfg.browser_fingerprint = browser_fingerprint_for_email(claimed_email)
        flow = AuthFlow(cfg, trace_callback=self._make_http_trace_callback(emit))
        try:
            result = flow.run_register(mail)
        except Exception:
            _close_auth_flow(flow)
            raise
        return _RegistrationAttempt(
            result=result,
            flow=flow,
            proxy_url=proxy_url,
            proxy_country=input_.proxy_country.upper(),
        )

    def _execute_email_browser(
        self,
        input_: ProtocolRegistrationInput,
        *,
        mail: RegistrationMailProviderAdapter,
        user_account_id: str,
        work_id: str,
        proxy_url: str,
        proxy_mode: str = "cliproxy_sticky",
        emit: TraceEmitter,
    ) -> _RegistrationAttempt:
        del proxy_mode
        del user_account_id
        claimed_email = str(getattr(getattr(mail, "claim", None), "email", "") or "").strip()
        browser = CamoufoxEmailRegistration(
            BrowserEmailRegistrationConfig(
                proxy_url=proxy_url,
                headless=bool(input_.browser_headless),
                locale=locale_for_proxy_country(input_.proxy_country),
                browser_fingerprint=(
                    browser_fingerprint_for_email(claimed_email) if claimed_email else None
                ),
                otp_timeout_s=max(1, int(input_.browser_otp_timeout_s or 180)),
                success_close_delay_s=max(0.0, float(input_.browser_close_delay_s or 0.0)),
                work_id=work_id,
                browser_log_enabled=bool(input_.browser_log_enabled),
                browser_log_capture_bodies=bool(input_.browser_log_capture_bodies),
                browser_log_max_body_chars=max(
                    1_000,
                    int(input_.browser_log_max_body_chars or 20_000),
                ),
                browser_backend=str(input_.browser_backend or "camoufox"),
                cloakbrowser_license_key=self._cloakbrowser_license_key,
            ),
            event_callback=emit,
        )
        result = browser.run(
            mail,
            totp_code_provider=self._totp_code_resolver,
        )
        return _RegistrationAttempt(
            result=result,
            flow=None,
            proxy_url=proxy_url,
            proxy_country=input_.proxy_country.upper(),
        )

    def _execute_phone_protocol(
        self,
        input_: ProtocolRegistrationInput,
        *,
        mail: RegistrationMailProviderAdapter,
        user_account_id: str,
        work_id: str,
        proxy_url: str,
        proxy_mode: str = "cliproxy_sticky",
        emit: TraceEmitter,
    ) -> _RegistrationAttempt:
        del user_account_id, work_id
        claimed_email = str(getattr(getattr(mail, "claim", None), "email", "") or "").strip()
        cfg = Config()
        cfg.proxy = proxy_url
        cfg.proxy_meta = {
            "register": {
                "region": input_.proxy_country.upper(),
                "country_code": input_.proxy_country.upper(),
                "mode": proxy_mode,
            }
        }
        if claimed_email:
            cfg.browser_fingerprint = browser_fingerprint_for_email(claimed_email)
        cfg.phone = _phone_config(input_)
        phone = HeroSmsPhoneProviderAdapter(
            cfg.phone,
            api_key=self._hero_sms_api_key,
            event_callback=emit,
        )
        flow = AuthFlow(cfg, trace_callback=self._make_http_trace_callback(emit))
        try:
            result = flow.run_phone_register(mail, phone)
        except Exception:
            _close_auth_flow(flow)
            raise
        return _RegistrationAttempt(
            result=result,
            flow=flow,
            proxy_url=proxy_url,
            proxy_country=input_.proxy_country.upper(),
        )

    def _execute_phone_browser(
        self,
        input_: ProtocolRegistrationInput,
        *,
        mail: RegistrationMailProviderAdapter,
        user_account_id: str,
        work_id: str,
        proxy_url: str,
        proxy_mode: str = "cliproxy_sticky",
        emit: TraceEmitter,
    ) -> _RegistrationAttempt:
        """Run phone signup and mailbox binding inside one browser context.

        The phone provider is intentionally created for this attempt rather
        than shared with another work item.  The browser runner owns the
        temporary phone lease; this method owns the provider client lifetime.
        """
        del proxy_mode
        claimed_email = str(getattr(getattr(mail, "claim", None), "email", "") or "").strip()
        cfg = _phone_config(input_)
        phone = HeroSmsPhoneProviderAdapter(
            cfg,
            api_key=self._hero_sms_api_key,
            event_callback=emit,
        )
        browser = BrowserPhoneEmailRegistration(
            BrowserPhoneEmailRegistrationConfig(
                proxy_url=proxy_url,
                headless=bool(input_.browser_headless),
                locale=locale_for_proxy_country(input_.proxy_country),
                browser_fingerprint=(
                    browser_fingerprint_for_email(claimed_email) if claimed_email else None
                ),
                otp_timeout_s=max(1, int(input_.browser_otp_timeout_s or 180)),
                phone_otp_timeout_s=max(1, int(input_.phone_otp_timeout_s or 180)),
                navigation_timeout_ms=60_000,
                # Phone signup can spend the full SMS wait before password
                # and about-you stages; leave enough time for those steps too.
                completion_timeout_s=max(
                    300,
                    int(input_.browser_otp_timeout_s or 180)
                    + int(input_.phone_otp_timeout_s or 180),
                ),
                success_close_delay_s=max(0.0, float(input_.browser_close_delay_s or 0.0)),
                work_id=work_id,
                browser_log_enabled=bool(input_.browser_log_enabled),
                browser_log_capture_bodies=bool(input_.browser_log_capture_bodies),
                browser_log_max_body_chars=max(
                    1_000,
                    int(input_.browser_log_max_body_chars or 20_000),
                ),
                browser_backend=str(input_.browser_backend or "camoufox"),
                cloakbrowser_license_key=self._cloakbrowser_license_key,
            ),
            event_callback=emit,
        )
        try:
            claimed_email = str(
                getattr(getattr(mail, "claim", None), "email", "") or ""
            ).strip()
            result = browser.run(
                mail,
                phone,
                email=claimed_email,
                totp_code_provider=(
                    (lambda: self._totp_code_resolver(user_account_id))
                    if self._totp_code_resolver is not None
                    else None
                ),
            )
        except Exception:
            try:
                phone.close()
            except Exception:
                logger.debug("phone browser provider close failed", exc_info=True)
            raise
        try:
            phone.close()
        except Exception:
            logger.debug("phone browser provider close failed", exc_info=True)
        return _RegistrationAttempt(
            result=result,
            flow=None,
            proxy_url=proxy_url,
            proxy_country=input_.proxy_country.upper(),
        )

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

    def _make_claim_persist_callback(
        self,
        work_id: str,
        *,
        run_id: str = "",
    ) -> Callable[[ClaimedMailAccount], None]:
        effective_run_id = run_id or str(getattr(self, "_active_run_id", "") or "")

        def callback(claim: ClaimedMailAccount) -> None:
            if not work_id:
                return
            self._merge_work_output(
                work_id,
                {
                    "email": claim.email,
                    "mail_claim": _safe_claim_dict(claim),
                    "mail_claim_run_id": effective_run_id,
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
        security_setup: AccountSecuritySetupResult | None = None,
    ) -> None:
        now = datetime.now(UTC)
        password_status = (
            security_setup.password_status
            if security_setup is not None
            else ("configured" if result.password_configured else "unknown")
        )
        password_value_confirmed = (
            security_setup.password_value_confirmed
            if security_setup is not None
            else bool(result.password_configured)
        )
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
            account.password = (
                result.password
                if password_status == "configured" and password_value_confirmed
                else ""
            )
            account.password_status = password_status
            account.password_last_error_code = (
                security_setup.password_error_code if security_setup is not None else ""
            )
            account.password_last_error_message = (
                security_setup.password_error_message if security_setup is not None else ""
            )
            account.mfa_status = (
                security_setup.mfa_status if security_setup is not None else "not_configured"
            )
            account.twofauth_account_id = (
                security_setup.twofauth_account_id if security_setup is not None else ""
            )
            account.mfa_last_error_code = (
                security_setup.mfa_error_code if security_setup is not None else ""
            )
            account.mfa_last_error_message = (
                security_setup.mfa_error_message if security_setup is not None else ""
            )
            account.security_setup_last_attempt_at = now if security_setup is not None else None
            # Account detection stores only a validated personal-space token here.
            # Do not replace it with the registration bootstrap token.
            if not getattr(account, "access_token", ""):
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

    def _run_post_registration_security(
        self,
        input_: ProtocolRegistrationInput,
        *,
        result: AuthResult,
        flow: AuthFlow | None,
        proxy_url: str,
        proxy_country: str,
        emit: TraceEmitter,
    ) -> AccountSecuritySetupResult | None:
        if not registration_mode_requires_security(input_.mode):
            return None

        emit(
            "account_security.started",
            {
                "email": result.email,
                "password_configured_by_registration": bool(result.password_configured),
                "twofauth_configured": self._twofauth_client is not None,
                "transport": "protocol",
            },
        )
        try:
            setup = ProtocolAccountSecurity(
                ProtocolAccountSecurityConfig(
                    proxy_url=proxy_url,
                    accept_language=accept_language_for_proxy_country(proxy_country),
                    request_timeout_s=min(
                        60,
                        max(1, int(input_.browser_otp_timeout_s or 30)),
                    ),
                ),
                event_callback=emit,
            ).run(
                auth_result=result,
                twofauth_client=self._twofauth_client,
                http_session=flow.session if flow is not None else None,
            )
        except Exception as exc:
            error_message = _safe_security_error(exc)
            emit(
                "account_security.unhandled_failure",
                {"email": result.email, "error": error_message},
                "ERROR",
            )
            setup = AccountSecuritySetupResult(
                password_status="configured" if result.password_configured else "failed",
                password_value_confirmed=bool(result.password_configured),
                password_error_code=(
                    "" if result.password_configured else "account_security_unhandled_failure"
                ),
                password_error_message="" if result.password_configured else error_message,
                mfa_status="failed",
                mfa_error_code="account_security_unhandled_failure",
                mfa_error_message=error_message,
            )

        result.password_configured = setup.password_value_confirmed
        emit(
            "account_security.result",
            {
                "email": result.email,
                "password_status": setup.password_status,
                "mfa_status": setup.mfa_status,
                "password_error_code": setup.password_error_code,
                "mfa_error_code": setup.mfa_error_code,
            },
            (
                "INFO"
                if setup.password_status == "configured" and setup.mfa_status == "configured"
                else "WARN"
            ),
        )
        return setup

    def _run_post_registration_codex_authorization(
        self,
        input_: ProtocolRegistrationInput,
        *,
        user_account_id: str,
        security_setup: AccountSecuritySetupResult | None,
        proxy_url: str,
        run_id: str,
        emit: TraceEmitter,
    ) -> dict[str, Any] | None:
        if not self._authorize_codex_after_security or not registration_mode_requires_security(
            input_.mode
        ):
            return None
        if security_setup is None or security_setup.mfa_status != "configured":
            reason = "mfa_not_configured"
            emit(
                "codex_authorization.skipped",
                {"user_account_id": user_account_id, "reason": reason},
                "WARN",
            )
            return {"status": "skipped", "reason": reason}
        if self._codex_phone_provider is None:
            raise ProtocolRegistrationWorkflowError(
                "post-registration Codex authorization requires GrizzlySMS configuration"
            )

        emit(
            "codex_authorization.started",
            {
                "user_account_id": user_account_id,
                "authorization_scope": "personal",
                "proxy_source": "registration_current_proxy",
                "add_phone_provider": "grizzly_sms",
            },
        )
        try:
            BackfillRtWorkflow(
                session_factory=self._session_factory,
                mail_provider=self._mail_provider,
                phone_provider=self._codex_phone_provider,
                totp_code_resolver=self._totp_code_resolver,
            ).run(
                user_account_id=user_account_id,
                run_id=run_id,
                proxy_url_override=proxy_url,
            )
        except Exception as exc:
            emit(
                "codex_authorization.failed",
                {
                    "user_account_id": user_account_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                },
                "ERROR",
            )
            raise ProtocolRegistrationWorkflowError(
                f"post-registration Codex authorization failed: {type(exc).__name__}: {exc}"
            ) from exc

        emit(
            "codex_authorization.succeeded",
            {
                "user_account_id": user_account_id,
                "authorization_scope": "personal",
            },
        )
        return {
            "status": "succeeded",
            "authorization_scope": "personal",
            "proxy_source": "registration_current_proxy",
            "add_phone_provider": "grizzly_sms",
        }

    def _run_post_registration_promotion_check(
        self,
        input_: ProtocolRegistrationInput,
        *,
        user_account_id: str,
        registration_proxy: CliproxyProxy,
        run_id: str,
        emit: TraceEmitter,
    ) -> dict[str, Any] | None:
        if not registration_mail_provider_requires_security(input_.mail_provider):
            return None
        if not self._promotion_check_enabled:
            emit(
                "promotion_check.skipped",
                {
                    "user_account_id": user_account_id,
                    "reason": "post_registration_promotion_check_disabled",
                },
            )
            return None
        try:
            proxy = registration_proxy
            emit(
                "promotion_check.proxy_assigned",
                {
                    "user_account_id": user_account_id,
                    "proxy_provider": proxy.provider,
                    "proxy_country": proxy.country_code,
                    "proxy_egress_ip": proxy.egress_ip,
                    "proxy_source": proxy.proxy_source,
                    "proxy_sid_source": proxy.sid_source,
                    "proxy_probe_attempts": proxy.probe_attempts,
                },
            )
            result = BackfillSessionWorkflow(
                session_factory=self._session_factory,
                mail_provider=self._mail_provider,
            ).probe_personal_space_promotion(
                user_account_id=user_account_id,
                proxy_url=proxy.proxy_url,
                proxy_country=proxy.country_code,
                run_id=run_id,
            )
            emit(
                "promotion_check.succeeded",
                {
                    "user_account_id": user_account_id,
                    "has_promotion": bool(result.get("has_promotion")),
                    "promotion_id": str(result.get("promotion_id") or ""),
                    "proxy_provider": proxy.provider,
                    "proxy_country": proxy.country_code,
                    "proxy_egress_ip": proxy.egress_ip,
                    "proxy_sid_source": proxy.sid_source,
                    "proxy_probe_attempts": proxy.probe_attempts,
                },
            )
            return {
                **result,
                "proxy_provider": proxy.provider,
                "proxy_egress_ip": proxy.egress_ip,
                "proxy_sid_source": proxy.sid_source,
                "proxy_probe_attempts": proxy.probe_attempts,
            }
        except Exception as exc:
            result = {
                "status": "failed",
                "has_promotion": False,
                "promotion_id": "",
                "proxy_country": registration_proxy.country_code,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
            }
            emit(
                "promotion_check.failed",
                {"user_account_id": user_account_id, **result},
                "WARN",
            )
            return result

    def _detect_account_spaces_after_registration(
        self,
        *,
        user_account_id: str,
        result: AuthResult,
        flow: AuthFlow | None,
        proxy_url: str,
        proxy_country: str = "",
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
            proxy_country=proxy_country,
            oai_device_id=result.device_id,
            session_chatgpt_account_id=result.chatgpt_account_id,
            session_chatgpt_account_structure=result.chatgpt_account_structure,
            session_chatgpt_account_plan_type=result.chatgpt_account_plan_type,
            browser_user_agent=result.browser_user_agent,
            browser_platform=result.browser_platform,
            browser_timezone=result.browser_timezone,
            browser_timezone_offset=result.browser_timezone_offset,
            browser_accept_language=result.browser_accept_language,
            browser_impersonate=result.browser_impersonate,
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
        mail_provider: ExternalMailApiPlugin | HeroEmailPlugin,
        caller_id: str,
        task_id: str,
        provider: str,
        project_key: str,
        email_domain: str,
        fixed_email: str = "",
        otp_code_source: str = "content",
        event_callback: TraceEmitter | None = None,
        claim_persist_callback: Callable[[ClaimedMailAccount], None] | None = None,
        existing_claim: ClaimedMailAccount | None = None,
    ) -> None:
        self._mail_provider = mail_provider
        self._caller_id = caller_id
        self._task_id = task_id
        self._provider = str(provider or "").strip()
        self._project_key = project_key
        self._email_domain = (
            ""
            if self._provider == ICLOUD_HIDE_MY_EMAIL_PROVIDER
            else "gmail.com"
            if self._provider == HERO_GMAIL_PROVIDER and not str(email_domain or "").strip()
            else str(email_domain or "").strip()
        )
        self._fixed_email = str(fixed_email or "").strip()
        self._otp_code_source = str(otp_code_source or "content").strip().lower()
        self._event_callback = event_callback
        self._claim_persist_callback = claim_persist_callback
        self.claim = existing_claim
        self.last_persona = None

    def claim_mailbox(self) -> ClaimedMailAccount:
        if self.claim is None:
            if self._fixed_email:
                self.claim = ClaimedMailAccount(
                    account_id=f"local:{self._fixed_email.casefold()}",
                    email=self._fixed_email,
                    claim_token="",
                    caller_id=self._caller_id,
                    task_id=self._task_id,
                    email_domain=self._fixed_email.rpartition("@")[2],
                    raw={"source": "space_replenish_emails"},
                )
                self._emit(
                    "mail.fixed.selected",
                    {"email": self._fixed_email, "provider": self._provider},
                )
                return self.claim
            self._emit(
                (
                    "mail.create.started"
                    if self._provider == CLOUDFLARE_TEMP_MAIL_PROVIDER
                    else "mail.claim.started"
                ),
                {"provider": self._provider, "project_key": self._project_key},
            )
            if self._provider == CLOUDFLARE_TEMP_MAIL_PROVIDER:
                domain = self._email_domain.strip().lower().lstrip("@")
                if not domain:
                    raise ProtocolRegistrationWorkflowError(
                        "cloudflare_temp_mail requires email_domain"
                    )
                requested_email = f"{uuid4().hex[:12]}@{domain}"
                created = self._mail_provider.ensure_domain_email(email=requested_email)
                created_email = str(created.get("email") or requested_email).strip().lower()
                self.claim = ClaimedMailAccount(
                    account_id=f"temp-mail:{created_email}",
                    email=created_email,
                    claim_token="",
                    caller_id=self._caller_id,
                    task_id=self._task_id,
                    email_domain=created_email.rpartition("@")[2],
                    raw={"source": "external_temp_mail_ensure", "created": created},
                )
            else:
                # Long-lived registration mailboxes use the pool's global
                # availability path. Temporary mailboxes are created above.
                self.claim = self._mail_provider.claim_random(
                    caller_id=self._caller_id,
                    task_id=self._task_id,
                    provider=self._provider,
                    email_domain=self._email_domain,
                )
            self._emit(
                (
                    "mail.create.succeeded"
                    if self._provider == CLOUDFLARE_TEMP_MAIL_PROVIDER
                    else "mail.claim.succeeded"
                ),
                {
                    "email": self.claim.email,
                    "external_account_id": self.claim.account_id,
                    "email_domain": self.claim.email_domain,
                },
            )
            if self._claim_persist_callback is not None:
                self._claim_persist_callback(self.claim)
        elif (self.claim.raw or {}).get("restored"):
            self._emit(
                "mail.claim.restored",
                {
                    "email": self.claim.email,
                    "external_account_id": self.claim.account_id,
                    "email_domain": self.claim.email_domain,
                },
            )
        return self.claim

    def create_mailbox(self) -> str:
        claim = self.claim_mailbox()
        email = claim.email.strip() if self._fixed_email else claim.email.strip().lower()
        if (self._provider != CLOUDFLARE_TEMP_MAIL_PROVIDER or self._fixed_email) and callable(
            getattr(self._mail_provider, "ensure_domain_email", None)
        ):
            self._emit(
                "mail.ensure.started",
                {"email": email, "external_account_id": claim.account_id},
            )
            try:
                prepare_domain_mailbox(self._mail_provider, email=email)
            except Exception as exc:
                self._emit(
                    "mail.ensure.failed",
                    {
                        "email": email,
                        "external_account_id": claim.account_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    "ERROR",
                )
                raise
            self._emit(
                "mail.ensure.succeeded",
                {"email": email, "external_account_id": claim.account_id},
            )
        return email

    def ensure_domain_email(self, *, email: str) -> dict[str, Any]:
        """Expose the underlying mailbox initializer to browser runners."""
        ensure = getattr(self._mail_provider, "ensure_domain_email", None)
        if not callable(ensure):
            return {}
        normalized_email = str(email or "").strip()
        self._emit("mail.ensure.started", {"email": normalized_email})
        try:
            result = ensure(email=normalized_email)
        except Exception as exc:
            self._emit(
                "mail.ensure.failed",
                {"email": normalized_email, "error": f"{type(exc).__name__}: {exc}"},
                "ERROR",
            )
            raise
        self._emit("mail.ensure.succeeded", {"email": normalized_email})
        return result if isinstance(result, dict) else {}

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
                code_source=self._otp_code_source,
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
        if self.claim is not None and not self._fixed_email:
            mailbox_email = self._mailbox_email(email)
            if self._provider == CLOUDFLARE_TEMP_MAIL_PROVIDER:
                return
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
        if self.claim is not None and not self._fixed_email:
            claim = self.claim
            mailbox_email = self._mailbox_email(email)
            if self._provider == CLOUDFLARE_TEMP_MAIL_PROVIDER:
                self.claim = None
                return
            self._emit(
                "mail.claim.release.started",
                {"email": mailbox_email, "openai_email": email},
            )
            try:
                release_result = self._mail_provider.claim_release(
                    claim,
                    reason=f"registration_failed:{mailbox_email}",
                )
                released = not (
                    isinstance(release_result, dict) and release_result.get("released") is False
                )
                self._emit(
                    ("mail.claim.release.succeeded" if released else "mail.claim.release.retained"),
                    {
                        "email": mailbox_email,
                        "openai_email": email,
                        "released": released,
                    },
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

    def close(self) -> None:
        self._client.close()

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


class _HeroActivationLockUnavailable(RuntimeError):
    pass


class HeroSmsLongTermPhoneProviderAdapter(HeroSmsPhoneProviderAdapter):
    """Reuse an already-rented HeroSMS activation for PayPal OTPs.

    The normal :class:`HeroSmsPhoneProviderAdapter` owns a short-lived
    ``getNumberV2`` activation and therefore marks it complete/cancelled.  A
    long-term number is owned outside this workflow.  This adapter only reads
    the active activation and its SMS history; the lease lock remains held
    until ``close`` so concurrent PayPal jobs cannot consume one another's
    messages.
    """

    _activation_lock_registry: dict[str, threading.Lock] = {}
    _activation_lock_registry_guard = threading.Lock()
    _dial_codes = {
        "187": "1",  # United States (Hero country id)
    }
    _paypal_service_codes = frozenset({"ts", "pp", "paypal"})

    def __init__(
        self,
        cfg: PhoneConfig,
        *,
        api_key: str = "",
        activation_id: str = "",
        lock_timeout_s: float | None = None,
        country_phone_code: str = "",
        event_callback: TraceEmitter | None = None,
    ) -> None:
        super().__init__(cfg, api_key=api_key, event_callback=event_callback)
        self.activation_id = str(
            activation_id
            or getattr(cfg, "activation_id", "")
            or (getattr(cfg, "allocate_payload", None) or {}).get("activation_id", "")
            or (getattr(cfg, "allocate_payload", None) or {}).get("activationId", "")
            or ""
        ).strip()
        self.lock_timeout_s = (
            max(1.0, float(lock_timeout_s)) if lock_timeout_s is not None else None
        )
        self.country_phone_code = re.sub(r"\D+", "", str(country_phone_code or ""))
        self._lease: PhoneLease | None = None
        self._baseline_ids: set[str] = set()
        self._baseline_fingerprints: set[str] = set()
        self._otp_not_before: datetime | None = None
        self._thread_lock: threading.Lock | None = None
        self._lock_file: Any = None
        self._closed = False

    def allocate(self) -> PhoneLease:
        """Return the selected active activation and establish an SMS baseline."""
        if self._closed:
            raise ProtocolRegistrationWorkflowError("Hero SMS long-term adapter is closed")

        # A retry on the same adapter must not re-acquire a non-reentrant lock.
        # Refreshing the baseline makes a subsequent OTP wait start at the new
        # attempt while preserving the rented number.
        if self._lease is not None:
            messages = self._get_sms_messages(self._lease.lease_id)
            self._set_baseline(messages)
            self._emit(
                "phone.longterm.baseline.refreshed",
                {"lease_id": self._lease.lease_id, "message_count": len(messages)},
            )
            return self._lease

        service, country = self._required_selection()
        timeout = self.lock_timeout_s or max(1.0, float(self.cfg.otp_timeout_s or 180) + 30.0)
        deadline = time.time() + timeout
        waiting_emitted = False
        while True:
            eligible = self._eligible_active_leases(service=service, country=country)
            random.shuffle(eligible)
            for lease in eligible:
                if not self._try_acquire_activation_lock(lease.lease_id):
                    self._emit(
                        "phone.longterm.activation.skipped_locked",
                        {"lease_id": lease.lease_id},
                        "DEBUG",
                    )
                    continue
                try:
                    # Re-read the active list after locking. The activation may
                    # have expired while this worker was waiting.
                    current = {
                        item.lease_id: item
                        for item in self._eligible_active_leases(
                            service=service,
                            country=country,
                        )
                    }.get(lease.lease_id)
                    if current is None:
                        self._release_activation_lock()
                        continue
                    return self._claim_locked_lease(current)
                except Exception:
                    self._release_activation_lock()
                    raise

            if time.time() >= deadline:
                raise ProtocolRegistrationWorkflowError(
                    "Hero SMS long-term has no unlocked active PayPal activation "
                    f"after waiting {int(timeout)} seconds"
                )
            if not waiting_emitted:
                self._emit(
                    "phone.longterm.activation.waiting_for_lock",
                    {"candidate_count": len(eligible)},
                    "INFO",
                )
                waiting_emitted = True
            time.sleep(min(1.0, max(0.05, deadline - time.time())))

    def prepare_otp(self, lease_id: str) -> None:
        """Refresh the SMS baseline immediately before triggering an OTP.

        PayPal may take a little time between phone allocation and challenge
        initiation.  Callers that have such a boundary can use this hook to
        exclude anything received during that setup period while retaining the
        activation lock.
        """
        if self._closed:
            raise ProtocolRegistrationWorkflowError("Hero SMS long-term adapter is closed")
        if self._lease is None or self._lease.lease_id != str(lease_id or "").strip():
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS long-term lease mismatch for OTP preparation: {lease_id}"
            )
        messages = self._get_sms_messages(self._lease.lease_id)
        self._set_baseline(messages)
        self._otp_not_before = datetime.now(UTC) - timedelta(seconds=2)
        self._emit(
            "phone.longterm.baseline.prepared",
            {"lease_id": self._lease.lease_id, "message_count": len(messages)},
        )

    def poll_otp(self, lease_id: str) -> str:
        if self._closed:
            raise ProtocolRegistrationWorkflowError("Hero SMS long-term adapter is closed")
        lease = self._lease
        if lease is None:
            raise ProtocolRegistrationWorkflowError(
                "Hero SMS long-term poll requires allocate first"
            )
        if str(lease_id or "").strip() != lease.lease_id:
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS long-term lease mismatch: expected {lease.lease_id}, got {lease_id}"
            )

        timeout_s = max(1, int(self.cfg.otp_timeout_s or 180))
        interval_s = max(1.0, float(self.cfg.otp_poll_interval_s or 3.0))
        deadline = time.time() + timeout_s
        self._emit(
            "phone.longterm.otp.wait.started",
            {"lease_id": lease.lease_id, "timeout_s": timeout_s},
        )
        while time.time() < deadline:
            messages = self._get_sms_messages(lease.lease_id)
            for message in messages:
                message_id = _hero_sms_message_id(message)
                fingerprint = _hero_sms_message_fingerprint(message)
                if message_id and message_id in self._baseline_ids:
                    continue
                if fingerprint in self._baseline_fingerprints:
                    continue

                # Mark every new message as observed, including non-OTP text,
                # so a noisy message cannot be reconsidered on every poll.
                if message_id:
                    self._baseline_ids.add(message_id)
                self._baseline_fingerprints.add(fingerprint)
                message_time = _hero_sms_message_time(message)
                if (
                    self._otp_not_before is not None
                    and message_time is not None
                    and message_time < self._otp_not_before
                ):
                    continue
                if not self._is_paypal_sms(message):
                    continue
                code = _hero_sms_six_digit_code(message)
                if code:
                    self._emit(
                        "phone.longterm.otp.wait.succeeded",
                        {"lease_id": lease.lease_id, "message_id": message_id, "has_code": True},
                    )
                    return code
            time.sleep(interval_s)

        self._emit(
            "phone.longterm.otp.wait.failed",
            {"lease_id": lease.lease_id, "error": f"timeout ({timeout_s}s)"},
            "ERROR",
        )
        raise TimeoutError(f"Hero SMS long-term OTP timeout lease={lease.lease_id}")

    def _is_paypal_sms(self, message: dict[str, Any]) -> bool:
        service = (
            str(
                message.get("service")
                or message.get("serviceCode")
                or message.get("service_code")
                or ""
            )
            .strip()
            .lower()
        )
        source = " ".join(
            str(message.get(key) or "") for key in ("phoneFrom", "sender", "from", "text", "body")
        ).lower()
        return service in self._paypal_service_codes or "paypal" in source

    def mark_verified(self, lease_id: str) -> None:
        """Keep the day-rental active; verification is a local workflow state."""
        self._emit(
            "phone.longterm.status.verified",
            {"lease_id": str(lease_id or "")},
        )

    def mark_failed(self, lease_id: str, reason: str = "") -> None:
        """Keep the day-rental active so a retry can use the same number."""
        self._emit(
            "phone.longterm.status.failed",
            {"lease_id": str(lease_id or ""), "reason": str(reason or "")[:300]},
            "WARN",
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._release_activation_lock()
        super().close()

    def _required_selection(self) -> tuple[str, str]:
        service = str(self.cfg.service or "ts").strip().lower()
        raw_country = str(self.cfg.country or "187").strip().upper()
        country = "187" if raw_country == "US" else re.sub(r"\D+", "", raw_country)
        if service not in self._paypal_service_codes:
            raise ProtocolRegistrationWorkflowError(
                "Hero SMS long-term requires a PayPal service (ts, pp, or paypal), "
                f"got {service or '<empty>'}"
            )
        if country != "187":
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS long-term requires country=187 (US), got {country or '<empty>'}"
            )
        return service, country

    def _eligible_active_leases(self, *, service: str, country: str) -> list[PhoneLease]:
        payload = self._get_active_activations()
        activations = self._select_activations(
            payload,
            service=service,
            country=country,
        )
        leases: list[PhoneLease] = []
        last_error: ProtocolRegistrationWorkflowError | None = None
        for activation in activations:
            try:
                self._validate_activation(activation)
                leases.append(self._lease_from_activation(activation, country=country))
            except ProtocolRegistrationWorkflowError as exc:
                last_error = exc
        if leases:
            return leases
        if last_error is not None:
            raise last_error
        raise ProtocolRegistrationWorkflowError(
            f"Hero SMS long-term active activation not found (service={service}, country={country})"
        )

    def _get_active_activations(self) -> dict[str, Any]:
        limit = 100
        start = 0
        items: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for _page in range(20):
            payload = self._request_json(
                "getActiveActivations",
                start=start,
                limit=limit,
            )
            page_items = self._active_activation_items(payload)
            added = 0
            for item in page_items:
                item_id = self._activation_id_from(item)
                fingerprint = item_id or _hero_sms_message_fingerprint(item)
                if fingerprint in seen_ids:
                    continue
                seen_ids.add(fingerprint)
                items.append(item)
                added += 1
            if len(page_items) < limit or added == 0:
                break
            start += len(page_items)
        return {"data": items}

    @staticmethod
    def _active_activation_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        def extract(value: Any, depth: int = 0) -> list[dict[str, Any]]:
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if not isinstance(value, dict):
                return []
            # A bare activation object is also a valid one-row response.
            if any(key in value for key in ("activationId", "activation_id", "phoneNumber")):
                return [value]
            if depth >= 3:
                return []
            for key in ("rows", "row", "data", "activeActivations", "items", "results"):
                if key in value:
                    rows = extract(value[key], depth + 1)
                    if rows:
                        return rows
            return []

        # Hero has returned both `data` and `activeActivations` wrappers over
        # time.  Merge both sources so an empty wrapper cannot hide the other.
        items = extract(payload.get("data"))
        items.extend(extract(payload.get("activeActivations")))
        if not items:
            items = extract(payload)
        return items

    def _claim_locked_lease(self, lease: PhoneLease) -> PhoneLease:
        messages = self._get_sms_messages(lease.lease_id)
        self._set_baseline(messages)
        self._lease = lease
        self._emit(
            "phone.longterm.allocate.succeeded",
            {
                "lease_id": lease.lease_id,
                "phone": lease.masked_phone,
                "provider_country": lease.provider_country,
                "message_count": len(messages),
            },
        )
        return lease

    def _select_activations(
        self,
        payload: dict[str, Any],
        *,
        service: str,
        country: str,
    ) -> list[dict[str, Any]]:
        raw_items = self._active_activation_items(payload)

        candidates: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_service = (
                str(
                    item.get("serviceCode") or item.get("service") or item.get("service_code") or ""
                )
                .strip()
                .lower()
            )
            item_country = str(
                item.get("countryCode") or item.get("country") or item.get("country_code") or ""
            ).strip()
            if not item_country:
                phone_digits = re.sub(
                    r"\D+",
                    "",
                    str(
                        item.get("phoneNumber")
                        or item.get("phone_number")
                        or item.get("phone")
                        or ""
                    ),
                )
                if phone_digits.startswith("1") and len(phone_digits) >= 11:
                    item_country = "187"
            item_id = str(
                item.get("activationId") or item.get("activation_id") or item.get("id") or ""
            ).strip()
            if not self._service_matches(item_service, service) or not self._country_matches(
                item_country, country
            ):
                continue
            if self.activation_id and item_id != self.activation_id:
                continue
            candidates.append(item)

        if not candidates:
            requested = f" activation_id={self.activation_id}" if self.activation_id else ""
            raise ProtocolRegistrationWorkflowError(
                "Hero SMS long-term active activation not found "
                f"(service={service}, country={country}{requested})"
            )
        return candidates

    def _validate_activation(self, activation: dict[str, Any]) -> None:
        status = (
            str(
                activation.get("activationStatus")
                or activation.get("status")
                or activation.get("activation_status")
                or ""
            )
            .strip()
            .lower()
        )
        if status in {
            "6",
            "8",
            "finished",
            "finish",
            "complete",
            "completed",
            "expired",
            "status_expired",
            "status_cancel",
            "status_cancelled",
            "status_finished",
            "status_completed",
            "cancel",
            "cancelled",
        }:
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS long-term activation is completed (status={status})"
            )
        expires_at = _hero_activation_expiry(activation)
        if expires_at is not None and expires_at <= datetime.now(UTC):
            raise ProtocolRegistrationWorkflowError(
                "Hero SMS long-term activation is expired "
                f"(activation_id={self._activation_id_from(activation)}, "
                f"expires_at={expires_at.isoformat()})"
            )

    def _service_matches(self, item_service: str, requested_service: str) -> bool:
        item = str(item_service or "").strip().lower()
        requested = str(requested_service or "").strip().lower()
        if item not in self._paypal_service_codes:
            return False
        return requested in self._paypal_service_codes

    @staticmethod
    def _country_matches(item_country: str, requested_country: str) -> bool:
        normalized_item = str(item_country or "").strip().upper()
        normalized_requested = str(requested_country or "").strip().upper()
        if normalized_item in {"US", "1"}:
            normalized_item = "187"
        if normalized_requested == "US":
            normalized_requested = "187"
        return re.sub(r"\D+", "", normalized_item) == re.sub(r"\D+", "", normalized_requested)

    def _lease_from_activation(self, activation: dict[str, Any], *, country: str) -> PhoneLease:
        activation_id = self._activation_id_from(activation)
        if not activation_id:
            raise ProtocolRegistrationWorkflowError(
                "Hero SMS long-term active activation is missing activationId"
            )
        phone = (
            activation.get("phoneNumber")
            or activation.get("phone_number")
            or activation.get("phone")
        )
        if "*" in str(phone or ""):
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS long-term activation {activation_id} returned a masked phone number"
            )
        dial = (
            activation.get("countryPhoneCode")
            or activation.get("country_phone_code")
            or self.country_phone_code
        )
        if not dial:
            dial = self._dial_codes.get(country, "")
        phone_e164, phone_national, dial_code = _hero_phone_parts(phone, dial)
        return PhoneLease(
            lease_id=activation_id,
            phone_e164=phone_e164,
            masked_phone=_mask_phone(phone_e164),
            phone_national=phone_national,
            country_phone_code=dial_code,
            provider_country=country,
            expires_at=str(_hero_activation_expiry_value(activation) or ""),
            raw=dict(activation),
        )

    def _activation_id_from(self, activation: dict[str, Any]) -> str:
        return str(
            activation.get("activationId")
            or activation.get("activation_id")
            or activation.get("id")
            or ""
        ).strip()

    def _get_sms_messages(self, lease_id: str) -> list[dict[str, Any]]:
        payload = self._request_json("getAllSms", id=lease_id, size=100, page=1)
        raw_items: Any = payload.get("data", [])
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("data", [])
        if raw_items is None:
            return []
        if not isinstance(raw_items, list):
            raise ProtocolRegistrationWorkflowError(
                f"Hero SMS getAllSms returned invalid data lease={lease_id}"
            )
        return [item for item in raw_items if isinstance(item, dict)]

    def _set_baseline(self, messages: list[dict[str, Any]]) -> None:
        self._baseline_ids = {
            message_id for message in messages if (message_id := _hero_sms_message_id(message))
        }
        self._baseline_fingerprints = {
            _hero_sms_message_fingerprint(message) for message in messages
        }

    def _acquire_activation_lock(self, lease_id: str) -> bool:
        return self._acquire_activation_lock_internal(lease_id, blocking=True)

    def _try_acquire_activation_lock(self, lease_id: str) -> bool:
        return self._acquire_activation_lock_internal(lease_id, blocking=False)

    def _acquire_activation_lock_internal(self, lease_id: str, *, blocking: bool) -> bool:
        with self._activation_lock_registry_guard:
            lock = self._activation_lock_registry.setdefault(lease_id, threading.Lock())
        timeout = self.lock_timeout_s or max(1.0, float(self.cfg.otp_timeout_s or 180) + 30.0)
        if blocking:
            acquired = lock.acquire(timeout=timeout)
        else:
            acquired = lock.acquire(blocking=False)
        if not acquired:
            if blocking:
                raise ProtocolRegistrationWorkflowError(
                    f"Hero SMS long-term activation is busy (activation_id={lease_id})"
                )
            return False
        lock_file = None
        try:
            root = Path(
                os.getenv(
                    "REFACTOR_APP_HERO_LONGTERM_LOCK_DIR",
                    str(Path(tempfile.gettempdir()) / "refactor-app-hero-sms-longterm"),
                )
            )
            root.mkdir(parents=True, exist_ok=True)
            lock_file = (root / f"{hashlib.sha256(lease_id.encode()).hexdigest()}.lock").open(
                "a+", encoding="utf-8"
            )
            if fcntl is not None:
                if not blocking:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise _HeroActivationLockUnavailable from None
                else:
                    deadline = time.time() + timeout
                    while True:
                        try:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.time() >= deadline:
                                raise ProtocolRegistrationWorkflowError(
                                    "Hero SMS long-term activation is busy "
                                    f"(activation_id={lease_id})"
                                ) from None
                            time.sleep(0.1)
            self._thread_lock = lock
            self._lock_file = lock_file
            return True
        except _HeroActivationLockUnavailable:
            if lock_file is not None:
                try:
                    lock_file.close()
                except Exception:
                    pass
            lock.release()
            return False
        except Exception:
            if lock_file is not None:
                try:
                    lock_file.close()
                except Exception:
                    pass
            lock.release()
            raise

    def _release_activation_lock(self) -> None:
        lock_file, lock = self._lock_file, self._thread_lock
        self._lock_file = None
        self._thread_lock = None
        if lock_file is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_file.close()
            except Exception:
                pass
        if lock is not None:
            lock.release()


def _hero_activation_expiry_value(activation: dict[str, Any]) -> Any:
    return (
        activation.get("activationEndTime")
        or activation.get("activation_end_time")
        or activation.get("expiresAt")
        or activation.get("expires_at")
        or activation.get("endTime")
        or activation.get("end_time")
        or activation.get("estDate")
        or activation.get("estimatedEndTime")
        or activation.get("estimated_end_time")
        or ""
    )


def _hero_activation_expiry(activation: dict[str, Any]) -> datetime | None:
    value = _hero_activation_expiry_value(activation)
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(value, tz=UTC)
        except (OverflowError, OSError, ValueError):
            parsed = None
    elif isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        parsed = None
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                parsed = datetime.fromisoformat(candidate)
                break
            except ValueError:
                continue
        if parsed is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _hero_sms_message_id(message: dict[str, Any]) -> str:
    return str(
        message.get("id") or message.get("messageId") or message.get("message_id") or ""
    ).strip()


def _hero_sms_message_fingerprint(message: dict[str, Any]) -> str:
    stable = {
        str(key): message.get(key)
        for key in (
            "id",
            "messageId",
            "message_id",
            "code",
            "text",
            "body",
            "date",
            "dateTime",
            "service",
            "type",
        )
        if message.get(key) is not None
    }
    encoded = json.dumps(
        stable,
        sort_keys=True,
        ensure_ascii=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hero_sms_message_time(message: dict[str, Any]) -> datetime | None:
    value = (
        message.get("date")
        or message.get("dateTime")
        or message.get("createdAt")
        or message.get("created_at")
    )
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _hero_sms_six_digit_code(message: dict[str, Any]) -> str:
    values: list[Any] = [message.get("code"), message.get("text"), message.get("body")]
    for value in values:
        match = re.search(r"(?<!\d)(\d{6})(?!\d)", str(value or ""))
        if match:
            return match.group(1)
    return ""


def _phone_config(input_: ProtocolRegistrationInput) -> PhoneConfig:
    return PhoneConfig(
        enabled=True,
        provider=input_.phone_provider or "grizzly_sms",
        base_url=input_.phone_base_url or "https://api.grizzlysms.com/stubs/handler_api.php",
        api_key_env=input_.phone_api_key_env or "GRIZZLY_SMS_API_KEY",
        country=input_.phone_country,
        countries=input_.phone_countries or [],
        service=input_.phone_service or "dr",
        maxPrice=input_.phone_max_price or "0.18",
        country_max_prices=input_.phone_country_max_prices or {},
        max_number_attempts=max(1, int(input_.phone_max_number_attempts or 3)),
        request_timeout_s=max(1, int(input_.phone_request_timeout_s or 20)),
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


def _hydrate_auth_result_cookie_headers(result: AuthResult, flow: AuthFlow | None) -> None:
    if flow is None:
        return
    if not result.cookie_header:
        result.cookie_header = _cookie_header_from_session(flow, "chatgpt.com")
    if not result.auth_cookie_header:
        result.auth_cookie_header = _cookie_header_from_session(flow, "openai.com")


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


def _safe_security_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {str(exc)[:800]}"
    message = re.sub(
        r"(?i)(secret|token|authorization)([\s\"'=:\\]+)[^\s,}\]]+",
        r"\1\2<redacted>",
        message,
    )
    return message[:1000]


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
