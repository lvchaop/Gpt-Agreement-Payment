from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.payment_method_inventory import (
    PAYMENT_METHOD_COOLDOWN_HOURS,
    PAYMENT_METHOD_MAX_ATTEMPTS,
)
from refactor_app.application.workflows.protocol_registration import (
    RegistrationMailProviderAdapter,
)
from refactor_app.application.workflows.registration_proxy import (
    resolve_cliproxy_proxy,
)
from refactor_app.infrastructure.db.models import (
    PaymentAddressPoolModel,
    PaymentCardPoolModel,
    PaymentNamePoolModel,
    SpaceModel,
    UserAccountModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_browser import (
    BrowserBillingDetails,
    BrowserEmailRegistrationConfig,
    BrowserEmailRegistrationError,
    BrowserPaymentCard,
    BrowserPaymentMethodConfirmError,
    BrowserPaymentMethodResult,
    CamoufoxEmailRegistration,
)
from refactor_app.plugins.payment_card import normalize_card_cvc, normalize_card_number

MAX_PAYMENT_METHOD_CARD_ATTEMPTS = PAYMENT_METHOD_MAX_ATTEMPTS
PAYMENT_METHOD_BROWSER_BATCH_SIZE = 3

_NETWORK_ERROR_MARKERS = (
    "network",
    "timeout",
    "timed out",
    "connection",
    "connecterror",
    "connectionerror",
    "socket",
    "dns",
    "proxy",
    "eof",
    "fetch failed",
    "failed to fetch",
    "load_failed",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "rate limit",
    "rate_limit",
    "too many requests",
    "too_many_requests",
    "http 408",
    "http 429",
    "http 502",
    "http 503",
    "http 504",
    "http_408",
    "http_429",
    "http_502",
    "http_503",
    "http_504",
    "status 408",
    "status 429",
    "status 502",
    "status 503",
    "status 504",
    "-> 408",
    "-> 429",
    "-> 502",
    "-> 503",
    "-> 504",
)


class PersonalPaymentMethodBindError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        error_message: str = "",
        *,
        diagnostics: dict[str, str] | None = None,
    ) -> None:
        self.error_code = str(error_code or "personal_payment_method_bind_failed")
        self.error_message = str(error_message or "")
        self.diagnostics = dict(diagnostics or {})
        super().__init__(f"{self.error_code}: {self.error_message}".rstrip(": "))


@dataclass(frozen=True)
class _BindingContext:
    space_id: str
    external_space_id: str
    user_account_id: str
    email: str
    password: str
    cookie_header: str
    auth_cookie_header: str
    mfa_status: str
    twofauth_account_id: str


@dataclass(frozen=True)
class _ReservedPaymentAttempt:
    card_id: str
    card_number: str
    cvc: str
    card_last4: str
    exp_month: int
    exp_year: int
    full_name: str
    line1: str
    line2: str
    city: str
    state: str
    postal_code: str
    country: str
    phone: str
    attempt_count: int


class PersonalPaymentMethodBindWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
        registration_proxy_country: str = "US",
        browser_headless: bool = True,
        browser_log_enabled: bool = False,
        browser_log_capture_bodies: bool = False,
        browser_log_max_body_chars: int = 20_000,
        totp_code_resolver: Callable[[str], str] | None = None,
        after_bind_success: (
            Callable[[str, Any, BrowserPaymentMethodResult], dict[str, Any]] | None
        ) = None,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._registration_proxy_country = registration_proxy_country
        self._browser_headless = browser_headless
        self._browser_log_enabled = bool(browser_log_enabled)
        self._browser_log_capture_bodies = bool(browser_log_capture_bodies)
        self._browser_log_max_body_chars = max(1_000, int(browser_log_max_body_chars or 20_000))
        self._totp_code_resolver = totp_code_resolver
        self._after_bind_success = after_bind_success

    def run(
        self,
        *,
        space_id: str,
        work_id: str = "",
        run_id: str = "",
        payment_card_id: str = "",
    ) -> dict[str, Any]:
        context, existing = self._load_context(space_id)
        if existing is not None:
            return existing

        # The production implementation keeps one Camoufox context, hosted
        # Checkout page, and SetupIntent alive for the three-card retry window.
        # Test/custom subclasses that override the single-attempt hook retain
        # the legacy hook-driven behavior.
        if type(self)._bind_attempt is PersonalPaymentMethodBindWorkflow._bind_attempt:
            return self._run_reused_browser_batch(
                context=context,
                work_id=work_id,
                run_id=run_id,
                payment_card_id=payment_card_id,
            )

        last_error: PersonalPaymentMethodBindError | None = None
        preferred_card_id = str(payment_card_id or "").strip()
        while True:
            reserve_kwargs = (
                {"payment_card_id": preferred_card_id} if preferred_card_id else {}
            )
            attempt = self._reserve_attempt(context.space_id, **reserve_kwargs)
            preferred_card_id = ""
            self._event(
                run_id=run_id,
                event_type="personal_payment_method.attempt_started",
                message="personal payment method card attempt started",
                data_json={
                    "space_id": context.space_id,
                    "user_account_id": context.user_account_id,
                    "card_id": attempt.card_id,
                    "card_last4": attempt.card_last4,
                    "attempt_count": attempt.attempt_count,
                    "work_id": work_id,
                },
            )
            try:
                result = self._bind_attempt(
                    context=context,
                    attempt=attempt,
                    work_id=work_id,
                    run_id=run_id,
                )
            except Exception as exc:
                last_error = _bind_error(exc)
                if isinstance(exc, BrowserEmailRegistrationError):
                    last_error = PersonalPaymentMethodBindError(
                        "payment_method_authentication_failed",
                        f"{type(exc).__name__}: {str(exc)[:900]}",
                    )
                network_error = _is_network_payment_method_error(last_error)
                confirm_failure = isinstance(exc, BrowserPaymentMethodConfirmError)
                attempt_consumed = confirm_failure and not network_error
                if not attempt_consumed:
                    self._release_pre_payment_failure(
                        context=context,
                        attempt=attempt,
                        error=last_error,
                    )
                    authentication_failure = isinstance(
                        exc,
                        BrowserEmailRegistrationError,
                    )
                    self._event(
                        run_id=run_id,
                        event_type=(
                            "personal_payment_method.authentication_failed"
                            if authentication_failure
                            else "personal_payment_method.attempt_released"
                        ),
                        message=(
                            "personal payment method authentication failed before confirm"
                            if authentication_failure
                            else "personal payment method attempt failed without consuming card"
                        ),
                        level="ERROR",
                        data_json={
                            "space_id": context.space_id,
                            "card_id": attempt.card_id,
                            "card_last4": attempt.card_last4,
                            "attempt_count": attempt.attempt_count,
                            "confirm_failure": confirm_failure,
                            "network_error": network_error,
                            "attempt_consumed": False,
                            "card_invalidated": False,
                            "error_code": last_error.error_code,
                            "error_message": last_error.error_message[:500],
                            "stripe_diagnostics": last_error.diagnostics,
                            "work_id": work_id,
                        },
                    )
                    raise last_error from exc
                self._record_failure(
                    context=context,
                    attempt=attempt,
                    error=last_error,
                )
                self._event(
                    run_id=run_id,
                    event_type="personal_payment_method.attempt_failed",
                    message="personal payment method card attempt failed",
                    level="ERROR",
                    data_json={
                        "space_id": context.space_id,
                        "card_id": attempt.card_id,
                        "card_last4": attempt.card_last4,
                        "attempt_count": attempt.attempt_count,
                        "error_code": last_error.error_code,
                        "error_message": last_error.error_message[:500],
                        "stripe_diagnostics": last_error.diagnostics,
                        "confirm_failure": True,
                        "network_error": False,
                        "attempt_consumed": True,
                        "card_invalidated": True,
                        "work_id": work_id,
                    },
                )
                if attempt.attempt_count >= MAX_PAYMENT_METHOD_CARD_ATTEMPTS:
                    raise last_error from exc
                continue

            output = self._record_success(
                context=context,
                attempt=attempt,
                result=result,
            )
            self._event(
                run_id=run_id,
                event_type="personal_payment_method.succeeded",
                message="personal payment method bound and verified",
                data_json={**output, "work_id": work_id},
            )
            return output

    def _run_reused_browser_batch(
        self,
        *,
        context: _BindingContext,
        work_id: str,
        run_id: str,
        payment_card_id: str = "",
    ) -> dict[str, Any]:
        proxy = resolve_cliproxy_proxy(
            email=context.email,
            country_code=self._registration_proxy_country,
        )
        mail = RegistrationMailProviderAdapter(
            mail_provider=self._mail_provider,
            caller_id="personal-payment-method-bind",
            task_id=work_id,
            provider=mail_provider_name_for_email(context.email),
            project_key="personal-payment-method-bind",
            email_domain=context.email.rpartition("@")[2],
            fixed_email=context.email,
        )
        browser = CamoufoxEmailRegistration(
            BrowserEmailRegistrationConfig(
                proxy_url=proxy.proxy_url,
                headless=self._browser_headless,
                otp_timeout_s=180,
                work_id=work_id,
                browser_log_enabled=self._browser_log_enabled,
                browser_log_capture_bodies=self._browser_log_capture_bodies,
                browser_log_max_body_chars=self._browser_log_max_body_chars,
            ),
            event_callback=lambda event_type, data, level: self._payment_http_event(
                run_id=run_id,
                work_id=work_id,
                space_id=context.space_id,
                event_type=event_type,
                data=data,
                level=level,
            ),
        )
        totp_code_provider = self._totp_code_provider(context)
        reserved: dict[int, _ReservedPaymentAttempt] = {}
        finalized: set[int] = set()
        successful: dict[str, Any] = {}

        def card_provider(index: int) -> tuple[BrowserPaymentCard, BrowserBillingDetails]:
            reserve_kwargs = {"billing_template": reserved.get(1)}
            if index == 1 and str(payment_card_id or "").strip():
                reserve_kwargs["payment_card_id"] = str(payment_card_id).strip()
            attempt = self._reserve_attempt(context.space_id, **reserve_kwargs)
            reserved[index] = attempt
            self._event(
                run_id=run_id,
                event_type="personal_payment_method.attempt_started",
                message="personal payment method card attempt started",
                data_json={
                    "space_id": context.space_id,
                    "user_account_id": context.user_account_id,
                    "card_id": attempt.card_id,
                    "card_last4": attempt.card_last4,
                    "attempt_count": attempt.attempt_count,
                    "batch_index": index,
                    "work_id": work_id,
                },
            )
            try:
                card_number = normalize_card_number(attempt.card_number)
                cvc = normalize_card_cvc(attempt.cvc)
                if card_number[-4:] != attempt.card_last4:
                    raise PersonalPaymentMethodBindError("payment_card_last4_mismatch")
            except Exception as exc:
                self._release_pre_payment_failure(
                    context=context,
                    attempt=attempt,
                    error=_bind_error(exc),
                )
                raise
            return (
                BrowserPaymentCard(
                    number=card_number,
                    cvc=cvc,
                    exp_month=attempt.exp_month,
                    exp_year=attempt.exp_year,
                ),
                BrowserBillingDetails(
                    name=attempt.full_name,
                    email=context.email,
                    phone=attempt.phone,
                    line1=attempt.line1,
                    line2=attempt.line2,
                    city=attempt.city,
                    state=attempt.state,
                    postal_code=attempt.postal_code,
                    country=attempt.country,
                ),
            )

        def on_success(page: Any, index: int, result: BrowserPaymentMethodResult) -> None:
            attempt = reserved[index]
            output = self._record_success(context=context, attempt=attempt, result=result)
            finalized.add(index)
            if self._after_bind_success is not None:
                output["after_bind_success"] = self._after_bind_success(
                    context.space_id,
                    page,
                    result,
                )
            successful.update(output)
            self._event(
                run_id=run_id,
                event_type="personal_payment_method.succeeded",
                message="personal payment method bound and verified",
                data_json={**output, "batch_index": index, "work_id": work_id},
            )

        def on_failure(page: Any, index: int, exc: Exception) -> None:
            attempt = reserved[index]
            error = _bind_error(exc)
            network_error = _is_network_payment_method_error(error)
            if network_error:
                self._release_pre_payment_failure(
                    context=context,
                    attempt=attempt,
                    error=error,
                )
            else:
                self._record_failure(context=context, attempt=attempt, error=error)
            finalized.add(index)
            self._event(
                run_id=run_id,
                event_type=(
                    "personal_payment_method.attempt_released"
                    if network_error
                    else "personal_payment_method.attempt_failed"
                ),
                message="personal payment method batch card attempt failed",
                level="ERROR",
                data_json={
                    "space_id": context.space_id,
                    "card_id": attempt.card_id,
                    "card_last4": attempt.card_last4,
                    "attempt_count": attempt.attempt_count,
                    "batch_index": index,
                    "error_code": error.error_code,
                    "error_message": error.error_message[:500],
                    "network_error": network_error,
                    "work_id": work_id,
                },
            )
            if network_error:
                raise error

        try:
            browser.bind_personal_payment_cards(
                mail,
                expected_personal_account_id=context.external_space_id,
                card_provider=card_provider,
                max_attempts=PAYMENT_METHOD_BROWSER_BATCH_SIZE,
                login_password=context.password,
                totp_code_provider=totp_code_provider,
                on_success=on_success,
                on_failure=on_failure,
            )
        except Exception as exc:
            error = _bind_error(exc)
            for index, attempt in reserved.items():
                if index not in finalized:
                    self._release_pre_payment_failure(
                        context=context,
                        attempt=attempt,
                        error=error,
                    )
            raise error from exc
        if not successful:
            raise PersonalPaymentMethodBindError("payment_method_batch_no_success")
        return successful

    def _load_context(self, space_id: str) -> tuple[_BindingContext, dict[str, Any] | None]:
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            if space is None:
                raise PersonalPaymentMethodBindError("space_not_found", space_id)
            if space.space_type != "personal":
                raise PersonalPaymentMethodBindError(
                    "payment_method_personal_space_required",
                    space.id,
                )
            if space.space_status != "active":
                raise PersonalPaymentMethodBindError(
                    "payment_method_space_not_active",
                    space.space_status,
                )
            if not space.has_promotion or not str(space.promotion_id or "").strip():
                raise PersonalPaymentMethodBindError(
                    "payment_method_promotion_required",
                    space.id,
                )
            account = session.get(UserAccountModel, space.owner_user_account_id)
            if account is None:
                raise PersonalPaymentMethodBindError(
                    "payment_method_owner_account_missing",
                    space.owner_user_account_id,
                )
            if account.account_status != "active":
                raise PersonalPaymentMethodBindError(
                    "payment_method_owner_account_not_active",
                    account.account_status,
                )
            context = _BindingContext(
                space_id=space.id,
                external_space_id=space.external_space_id,
                user_account_id=account.id,
                email=account.email,
                password=account.password,
                cookie_header=account.cookie_header,
                auth_cookie_header=account.auth_cookie_header,
                mfa_status=account.mfa_status,
                twofauth_account_id=account.twofauth_account_id,
            )
            if space.has_payment_method and space.payment_method_status == "bound":
                return context, {
                    "space_id": space.id,
                    "user_account_id": account.id,
                    "payment_method_id": space.payment_method_id,
                    "payment_method_last4": space.payment_method_last4,
                    "payment_method_status": "bound",
                    "attempt_count": space.payment_method_attempt_count,
                    "already_bound": True,
                }
            if _payment_method_cooldown_active(space, now=datetime.now(UTC)):
                raise PersonalPaymentMethodBindError(
                    "payment_method_cooldown_active",
                    _cooldown_detail(space),
                )
            return context, None

    def _reserve_attempt(
        self,
        space_id: str,
        *,
        billing_template: _ReservedPaymentAttempt | None = None,
        payment_card_id: str = "",
    ) -> _ReservedPaymentAttempt:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id, with_for_update=True)
            if space is None:
                raise PersonalPaymentMethodBindError("space_not_found", space_id)
            if not space.has_promotion or not str(space.promotion_id or "").strip():
                raise PersonalPaymentMethodBindError(
                    "payment_method_promotion_required",
                    space.id,
                )
            if space.has_payment_method and space.payment_method_status == "bound":
                raise PersonalPaymentMethodBindError("payment_method_already_bound", space.id)
            if _payment_method_cooldown_active(space, now=now):
                raise PersonalPaymentMethodBindError(
                    "payment_method_cooldown_active",
                    _cooldown_detail(space),
                )
            if space.payment_method_attempt_count >= MAX_PAYMENT_METHOD_CARD_ATTEMPTS:
                # A completed six-hour cooldown starts a fresh three-card window.
                space.payment_method_attempt_count = 0
                space.payment_method_cooldown_until = None
                space.payment_method_status = "missing"

            name = None
            address = None
            if billing_template is None:
                name = session.scalar(
                    select(PaymentNamePoolModel)
                    .where(PaymentNamePoolModel.name_status == "active")
                    .order_by(func.random())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                address = session.scalar(
                    select(PaymentAddressPoolModel)
                    .where(PaymentAddressPoolModel.address_status == "active")
                    .order_by(func.random())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            card_query = select(PaymentCardPoolModel).where(
                PaymentCardPoolModel.card_status == "available"
            )
            normalized_card_id = str(payment_card_id or "").strip()
            if normalized_card_id:
                card_query = card_query.where(PaymentCardPoolModel.id == normalized_card_id)
            else:
                card_query = card_query.order_by(func.random())
            card = session.scalar(
                card_query.with_for_update(skip_locked=True).limit(1)
            )
            pool_rows = [("card", card)]
            if billing_template is None:
                pool_rows = [("name", name), ("address", address), *pool_rows]
            missing = [pool_name for pool_name, row in pool_rows if row is None]
            if missing:
                error_code = f"payment_{'_'.join(missing)}_pool_empty"
                space.payment_method_status = "failed"
                space.payment_method_last_error_code = error_code
                space.payment_method_last_error_message = ""
                space.updated_at = now
                session.commit()
                raise PersonalPaymentMethodBindError(error_code)

            assert card is not None
            space.payment_method_attempt_count += 1
            space.payment_method_status = "binding"
            space.payment_method_last_attempt_at = now
            space.payment_method_last_error_code = ""
            space.payment_method_last_error_message = ""
            space.updated_at = now
            if name is not None:
                name.use_count += 1
                name.last_used_at = now
                name.updated_at = now
            if address is not None:
                address.use_count += 1
                address.last_used_at = now
                address.updated_at = now
            card.card_status = "in_use"
            card.reserved_by_space_id = space.id
            card.reserved_at = now
            card.use_count = 1
            card.last_used_at = now
            card.last_error_code = ""
            card.last_error_message = ""
            card.updated_at = now
            attempt = _ReservedPaymentAttempt(
                card_id=card.id,
                card_number=card.card_number,
                cvc=card.cvc,
                card_last4=card.last4,
                exp_month=card.exp_month,
                exp_year=card.exp_year,
                full_name=(
                    billing_template.full_name if billing_template is not None else name.full_name
                ),
                line1=billing_template.line1 if billing_template is not None else address.line1,
                line2=billing_template.line2 if billing_template is not None else address.line2,
                city=billing_template.city if billing_template is not None else address.city,
                state=billing_template.state if billing_template is not None else address.state,
                postal_code=(
                    billing_template.postal_code
                    if billing_template is not None
                    else address.postal_code
                ),
                country=(
                    billing_template.country if billing_template is not None else address.country
                ),
                phone=billing_template.phone if billing_template is not None else address.phone,
                attempt_count=space.payment_method_attempt_count,
            )
            session.commit()
            return attempt

    def _bind_attempt(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        work_id: str,
        run_id: str = "",
    ) -> BrowserPaymentMethodResult:
        card_number = normalize_card_number(attempt.card_number)
        cvc = normalize_card_cvc(attempt.cvc)
        if card_number[-4:] != attempt.card_last4:
            raise PersonalPaymentMethodBindError("payment_card_last4_mismatch")
        proxy = resolve_cliproxy_proxy(
            email=context.email,
            country_code=self._registration_proxy_country,
        )
        mail = RegistrationMailProviderAdapter(
            mail_provider=self._mail_provider,
            caller_id="personal-payment-method-bind",
            task_id=work_id,
            provider=mail_provider_name_for_email(context.email),
            project_key="personal-payment-method-bind",
            email_domain=context.email.rpartition("@")[2],
            fixed_email=context.email,
        )
        browser = CamoufoxEmailRegistration(
            BrowserEmailRegistrationConfig(
                proxy_url=proxy.proxy_url,
                headless=self._browser_headless,
                otp_timeout_s=180,
                work_id=work_id,
                browser_log_enabled=self._browser_log_enabled,
                browser_log_capture_bodies=self._browser_log_capture_bodies,
                browser_log_max_body_chars=self._browser_log_max_body_chars,
            ),
            event_callback=lambda event_type, data, level: self._payment_http_event(
                run_id=run_id,
                work_id=work_id,
                space_id=context.space_id,
                event_type=event_type,
                data=data,
                level=level,
            ),
        )
        totp_code_provider = self._totp_code_provider(context)
        return browser.bind_personal_payment_method(
            mail,
            expected_personal_account_id=context.external_space_id,
            card=BrowserPaymentCard(
                number=card_number,
                cvc=cvc,
                exp_month=attempt.exp_month,
                exp_year=attempt.exp_year,
            ),
            billing=BrowserBillingDetails(
                name=attempt.full_name,
                email=context.email,
                phone=attempt.phone,
                line1=attempt.line1,
                line2=attempt.line2,
                city=attempt.city,
                state=attempt.state,
                postal_code=attempt.postal_code,
                country=attempt.country,
            ),
            login_password=context.password,
            totp_code_provider=totp_code_provider,
            after_success=(
                None
                if self._after_bind_success is None
                else lambda page, result: self._after_bind_success(
                    context.space_id,
                    page,
                    result,
                )
            ),
        )

    def _totp_code_provider(self, context: _BindingContext) -> Callable[[], str] | None:
        account_id = str(context.twofauth_account_id or "").strip()
        if str(context.mfa_status or "").strip().lower() != "configured" and not account_id:
            return None

        def resolve() -> str:
            if not account_id:
                raise PersonalPaymentMethodBindError("payment_method_twofauth_account_missing")
            if self._totp_code_resolver is None:
                raise PersonalPaymentMethodBindError(
                    "payment_method_twofauth_client_not_configured"
                )
            code = str(self._totp_code_resolver(account_id) or "").strip()
            if not code.isdigit():
                raise PersonalPaymentMethodBindError("payment_method_twofauth_invalid_code")
            return code

        return resolve

    def _payment_http_event(
        self,
        *,
        run_id: str,
        work_id: str,
        space_id: str,
        event_type: str,
        data: dict[str, Any],
        level: str,
    ) -> None:
        if not event_type.startswith("payment_method.http."):
            return
        self._event(
            run_id=run_id,
            event_type=event_type,
            message=event_type,
            level=level,
            data_json={**data, "space_id": space_id, "work_id": work_id},
        )

    def _release_pre_payment_failure(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        error: PersonalPaymentMethodBindError,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = session.get(SpaceModel, context.space_id, with_for_update=True)
            card = session.get(PaymentCardPoolModel, attempt.card_id, with_for_update=True)
            if card is not None:
                card.card_status = "available"
                card.reserved_by_space_id = None
                card.reserved_at = None
                card.use_count = 0
                card.last_used_at = None
                card.last_error_code = ""
                card.last_error_message = ""
                card.updated_at = now
            if space is not None:
                space.payment_method_attempt_count = max(
                    0,
                    int(space.payment_method_attempt_count or 0) - 1,
                )
                space.payment_method_status = "missing"
                space.payment_method_cooldown_until = None
                space.payment_method_last_error_code = error.error_code[:200]
                space.payment_method_last_error_message = error.error_message[:1000]
                space.updated_at = now
            session.commit()

    def _record_failure(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        error: PersonalPaymentMethodBindError,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = session.get(SpaceModel, context.space_id, with_for_update=True)
            card = session.get(PaymentCardPoolModel, attempt.card_id, with_for_update=True)
            if card is not None:
                card.card_status = "failed"
                card.reserved_by_space_id = None
                card.reserved_at = None
                card.last_error_code = error.error_code[:200]
                card.last_error_message = error.error_message[:1000]
                card.updated_at = now
            if space is not None:
                space.has_payment_method = False
                space.payment_method_status = (
                    "failed"
                    if space.payment_method_attempt_count >= MAX_PAYMENT_METHOD_CARD_ATTEMPTS
                    else "missing"
                )
                space.payment_method_cooldown_until = (
                    now + timedelta(hours=PAYMENT_METHOD_COOLDOWN_HOURS)
                    if space.payment_method_attempt_count >= MAX_PAYMENT_METHOD_CARD_ATTEMPTS
                    else None
                )
                space.payment_method_last_error_code = error.error_code[:200]
                space.payment_method_last_error_message = error.error_message[:1000]
                space.updated_at = now
            session.commit()

    def _record_success(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        result: BrowserPaymentMethodResult,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            space = session.get(SpaceModel, context.space_id, with_for_update=True)
            card = session.get(PaymentCardPoolModel, attempt.card_id, with_for_update=True)
            if space is None or card is None:
                raise PersonalPaymentMethodBindError("payment_method_state_disappeared")
            if result.personal_account_id != space.external_space_id:
                raise PersonalPaymentMethodBindError("payment_method_personal_account_mismatch")
            if result.last4 != attempt.card_last4:
                raise PersonalPaymentMethodBindError("payment_method_last4_mismatch")
            space.has_payment_method = True
            space.payment_method_status = "bound"
            space.payment_method_id = result.payment_method_id
            space.payment_method_last4 = result.last4
            space.payment_method_cooldown_until = None
            space.payment_method_last_error_code = ""
            space.payment_method_last_error_message = ""
            space.updated_at = now
            card.card_status = "used"
            card.reserved_by_space_id = None
            card.reserved_at = None
            card.last_error_code = ""
            card.last_error_message = ""
            card.updated_at = now
            session.commit()
            return {
                "space_id": space.id,
                "user_account_id": context.user_account_id,
                "payment_method_id": result.payment_method_id,
                "payment_method_last4": result.last4,
                "payment_method_brand": result.brand,
                "payment_method_status": "bound",
                "attempt_count": space.payment_method_attempt_count,
                "already_bound": False,
            }

    def _event(
        self,
        *,
        run_id: str,
        event_type: str,
        message: str,
        data_json: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        if not run_id:
            return
        with self._session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=event_type,
                message=message,
                level=level,
                data_json=data_json,
            )
            session.commit()


def mail_provider_name_for_email(email: str) -> str:
    domain = str(email or "").rpartition("@")[2].lower()
    if domain in {"outlook.com", "hotmail.com", "live.com"}:
        return "outlook"
    if domain in {"icloud.com", "me.com", "mac.com"}:
        return "icloud_hide_my_email"
    return "cloudflare_temp_mail"


def _bind_error(exc: Exception) -> PersonalPaymentMethodBindError:
    if isinstance(exc, PersonalPaymentMethodBindError):
        return exc
    if isinstance(exc, BrowserPaymentMethodConfirmError):
        return PersonalPaymentMethodBindError(
            exc.error_code,
            exc.error_message[:1000],
            diagnostics=exc.diagnostics,
        )
    text = " ".join(str(exc or "").split())
    possible_code = text.partition(":")[0].strip()
    if possible_code and len(possible_code) <= 200 and " " not in possible_code:
        error_code = possible_code
        error_message = text.partition(":")[2].strip()
    else:
        error_code = type(exc).__name__
        error_message = text
    return PersonalPaymentMethodBindError(error_code, error_message[:1000])


def _is_network_payment_method_error(error: PersonalPaymentMethodBindError) -> bool:
    haystack = " ".join(
        part.strip().lower() for part in (error.error_code, error.error_message, str(error)) if part
    )
    return any(marker in haystack for marker in _NETWORK_ERROR_MARKERS)


def _payment_method_cooldown_active(space: SpaceModel, *, now: datetime) -> bool:
    if space.payment_method_attempt_count < MAX_PAYMENT_METHOD_CARD_ATTEMPTS:
        return False
    cooldown_until = space.payment_method_cooldown_until
    # Rows created before the cooldown migration have no timestamp; keep them
    # blocked until an operator explicitly resets them instead of bypassing the
    # three-attempt safety limit.
    return cooldown_until is None or cooldown_until > now


def _cooldown_detail(space: SpaceModel) -> str:
    cooldown_until = space.payment_method_cooldown_until
    return (
        cooldown_until.isoformat()
        if cooldown_until is not None
        else "payment_method_cooldown_until_missing"
    )
