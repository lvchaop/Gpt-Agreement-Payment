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
from refactor_app.application.workflows.proxy_locale import (
    locale_for_proxy_country,
    timezone_for_proxy_country,
)
from refactor_app.application.workflows.registration_proxy import (
    detect_proxy_egress_country,
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
from refactor_app.plugins.openai_auth_protocol.card_payment import (
    CardPaymentConfig,
    CardPaymentError,
    CardPaymentResult,
    run_card_payment,
)
from refactor_app.plugins.payment_card import normalize_card_cvc, normalize_card_number

MAX_PAYMENT_METHOD_CARD_ATTEMPTS = PAYMENT_METHOD_MAX_ATTEMPTS
PREFERRED_PAYMENT_CARD_BIN8_PREFIXES = (
    "42954401",
    "42954408",
    "42954405",
    "42954411",
)
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


def _payment_locale_for_proxy_country(country_code: str) -> str:
    return locale_for_proxy_country(country_code)


def _payment_timezone_for_proxy_country(country_code: str) -> str:
    return timezone_for_proxy_country(country_code)


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
    access_token: str = ""
    session_token: str = ""
    device_id: str = ""
    promotion_id: str = ""


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


def _select_available_payment_card(
    session: Session,
    *,
    payment_card_id: str = "",
) -> PaymentCardPoolModel | None:
    available_query = select(PaymentCardPoolModel).where(
        PaymentCardPoolModel.card_status == "available"
    )
    normalized_card_id = str(payment_card_id or "").strip()
    if normalized_card_id:
        return session.scalar(
            available_query.where(PaymentCardPoolModel.id == normalized_card_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )

    preferred_card = session.scalar(
        available_query.where(
            func.substr(PaymentCardPoolModel.card_number, 1, 8).in_(
                PREFERRED_PAYMENT_CARD_BIN8_PREFIXES
            )
        )
        .order_by(func.random())
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if preferred_card is not None:
        return preferred_card

    return session.scalar(
        available_query.order_by(func.random()).with_for_update(skip_locked=True).limit(1)
    )


class PersonalPaymentMethodBindWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: Any | None = None,
        registration_proxy_country: str = "US",
        browser_headless: bool = True,
        browser_log_enabled: bool = False,
        browser_log_capture_bodies: bool = False,
        browser_log_max_body_chars: int = 20_000,
        totp_code_resolver: Callable[[str], str] | None = None,
        promo_campaign_id: str = "plus-1-month-free",
        checkout_ui_mode: str = "custom",
        require_local_promotion: bool = True,
        after_bind_success: Callable[[str, Any, Any], dict[str, Any]] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registration_proxy_country = str(
            registration_proxy_country or "US"
        ).strip().upper()
        if (
            len(self._registration_proxy_country) != 2
            or not self._registration_proxy_country.isascii()
            or not self._registration_proxy_country.isalpha()
        ):
            raise PersonalPaymentMethodBindError(
                "payment_method_country_invalid",
                self._registration_proxy_country,
            )
        self._promo_campaign_id = str(promo_campaign_id or "").strip()
        self._checkout_ui_mode = str(checkout_ui_mode or "custom").strip().lower()
        self._require_local_promotion = bool(require_local_promotion)
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

        last_error: PersonalPaymentMethodBindError | None = None
        requested_card_id = str(payment_card_id or "").strip()
        preferred_card_id = requested_card_id
        billing_template: _ReservedPaymentAttempt | None = None
        protocol_mode = type(self)._bind_attempt is PersonalPaymentMethodBindWorkflow._bind_attempt
        while True:
            reserve_kwargs: dict[str, Any] = {}
            if preferred_card_id:
                reserve_kwargs["payment_card_id"] = preferred_card_id
            if protocol_mode and billing_template is not None:
                reserve_kwargs["billing_template"] = billing_template
            attempt = self._reserve_attempt(context.space_id, **reserve_kwargs)
            if billing_template is None:
                billing_template = attempt
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
                    "billing_country": attempt.country,
                    "proxy_country": self._registration_proxy_country,
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
                last_error = _account_deactivated_bind_error(exc) or _bind_error(exc)
                if last_error.error_code == "account_deactivated":
                    self._mark_account_deactivated(context=context, error=last_error)
                elif type(exc).__name__ == "BrowserChatGPTAccountMissingError":
                    last_error = PersonalPaymentMethodBindError(
                        "chatgpt_account_missing",
                        str(exc)[:900],
                    )
                elif type(exc).__name__ == "BrowserEmailRegistrationError":
                    last_error = PersonalPaymentMethodBindError(
                        "payment_method_authentication_failed",
                        f"{type(exc).__name__}: {str(exc)[:900]}",
                    )
                network_error = _is_network_payment_method_error(last_error)
                disposition = _payment_attempt_disposition(exc, network_error=network_error)
                confirm_failure = disposition != "release"
                attempt_consumed = disposition in {"consume_retry", "consume_stop"}
                if not attempt_consumed:
                    self._release_pre_payment_failure(
                        context=context,
                        attempt=attempt,
                        error=last_error,
                    )
                    authentication_failure = type(exc).__name__ == "BrowserEmailRegistrationError"
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
                    stop_replay=disposition == "consume_stop",
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
                        "network_error": network_error,
                        "attempt_consumed": True,
                        "card_invalidated": True,
                        "attempt_disposition": disposition,
                        "work_id": work_id,
                    },
                )
                if (
                    disposition == "consume_stop"
                    or bool(requested_card_id)
                    or attempt.attempt_count >= MAX_PAYMENT_METHOD_CARD_ATTEMPTS
                ):
                    raise last_error from exc
                continue

            try:
                output = self._record_success(
                    context=context,
                    attempt=attempt,
                    result=result,
                )
            except Exception as exc:
                # The remote bind is already terminal.  Retry only the local,
                # idempotent state write before falling back to manual reconcile.
                try:
                    output = self._record_success(
                        context=context,
                        attempt=attempt,
                        result=result,
                    )
                except Exception as retry_exc:
                    reconcile_error = self._record_remote_success_persistence_failure(
                        context=context,
                        attempt=attempt,
                        result=result,
                        cause=retry_exc,
                    )
                    raise reconcile_error from exc
            if self._after_bind_success is not None:
                output["after_bind_success"] = self._after_bind_success(
                    context.space_id,
                    None,
                    result,
                )
            self._event(
                run_id=run_id,
                event_type="personal_payment_method.succeeded",
                message="personal payment method bound and verified",
                data_json={**output, "work_id": work_id},
            )
            return output

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
            if self._require_local_promotion and (
                not space.has_promotion or not str(space.promotion_id or "").strip()
            ):
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
                access_token=account.access_token,
                session_token=account.session_token,
                device_id=account.device_id,
                promotion_id=space.promotion_id,
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
            if space.payment_method_status == "binding":
                raise PersonalPaymentMethodBindError(
                    "payment_method_binding_in_progress",
                    space.id,
                )
            if not str(context.external_space_id or "").strip():
                raise PersonalPaymentMethodBindError("payment_method_account_id_missing")
            if not str(context.access_token or "").strip():
                raise PersonalPaymentMethodBindError("payment_method_access_token_missing")
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
            if self._require_local_promotion and (
                not space.has_promotion or not str(space.promotion_id or "").strip()
            ):
                raise PersonalPaymentMethodBindError(
                    "payment_method_promotion_required",
                    space.id,
                )
            if space.has_payment_method and space.payment_method_status == "bound":
                raise PersonalPaymentMethodBindError("payment_method_already_bound", space.id)
            if space.payment_method_status == "binding":
                raise PersonalPaymentMethodBindError(
                    "payment_method_binding_in_progress",
                    space.id,
                )
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
                    .where(
                        PaymentAddressPoolModel.address_status == "active",
                        PaymentAddressPoolModel.country
                        == self._registration_proxy_country,
                    )
                    .order_by(func.random())
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
            card = _select_available_payment_card(
                session,
                payment_card_id=payment_card_id,
            )
            pool_rows = [("card", card)]
            if billing_template is None:
                pool_rows = [("name", name), ("address", address), *pool_rows]
            missing = [pool_name for pool_name, row in pool_rows if row is None]
            if missing:
                if billing_template is None and address is None:
                    error_code = "payment_address_pool_country_empty"
                    error_message = (
                        "no active payment address for "
                        f"{self._registration_proxy_country}"
                    )
                else:
                    error_code = f"payment_{'_'.join(missing)}_pool_empty"
                    error_message = ""
                space.payment_method_status = "failed"
                space.payment_method_last_error_code = error_code
                space.payment_method_last_error_message = error_message
                space.updated_at = now
                session.commit()
                raise PersonalPaymentMethodBindError(
                    error_code,
                    error_message,
                    diagnostics={"country": self._registration_proxy_country},
                )

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
    ) -> CardPaymentResult:
        card_number = normalize_card_number(attempt.card_number)
        cvc = normalize_card_cvc(attempt.cvc)
        if card_number[-4:] != attempt.card_last4:
            raise PersonalPaymentMethodBindError("payment_card_last4_mismatch")
        proxy = resolve_cliproxy_proxy(
            email=context.email,
            country_code=self._registration_proxy_country,
        )
        egress_country = detect_proxy_egress_country(proxy.proxy_url)
        config = CardPaymentConfig(
            access_token=context.access_token,
            account_id=context.external_space_id,
            card={
                "number": card_number,
                "cvc": cvc,
                "exp_month": str(attempt.exp_month),
                "exp_year": str(attempt.exp_year),
            },
            billing={
                "name": attempt.full_name,
                "email": context.email,
                "phone": attempt.phone,
                "line1": attempt.line1,
                "line2": attempt.line2,
                "city": attempt.city,
                "state": attempt.state,
                "postal_code": attempt.postal_code,
                "country": attempt.country,
            },
            session_token=context.session_token,
            cookie_header=context.cookie_header,
            auth_cookie_header=context.auth_cookie_header,
            device_id=context.device_id,
            promo_campaign_id=context.promotion_id or self._promo_campaign_id,
            checkout_ui_mode=self._checkout_ui_mode,
            locale=_payment_locale_for_proxy_country(egress_country),
            browser_timezone=_payment_timezone_for_proxy_country(egress_country),
        )
        return run_card_payment(
            config,
            proxy_url=proxy.proxy_url,
            event_callback=lambda event_type, data, level: self._payment_http_event(
                run_id=run_id,
                work_id=work_id,
                space_id=context.space_id,
                event_type=event_type,
                data=data,
                level=level,
            ),
        )

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

    def _mark_account_deactivated(
        self,
        *,
        context: _BindingContext,
        error: PersonalPaymentMethodBindError,
    ) -> None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, context.user_account_id, with_for_update=True)
            if account is None:
                return
            account.account_status = "invalid"
            account.session_status = "dead"
            account.last_login_error_code = "account_deactivated"
            account.last_login_error_message = error.error_message[:1000]
            account.updated_at = now
            session.commit()

    def _record_failure(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        error: PersonalPaymentMethodBindError,
        stop_replay: bool = False,
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
                if stop_replay:
                    space.payment_method_attempt_count = max(
                        int(space.payment_method_attempt_count or 0),
                        MAX_PAYMENT_METHOD_CARD_ATTEMPTS,
                    )
                    space.payment_method_status = "failed"
                    space.payment_method_cooldown_until = None
                else:
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

    def _record_remote_success_persistence_failure(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        result: Any,
        cause: Exception,
    ) -> PersonalPaymentMethodBindError:
        original_error = _bind_error(cause)
        payment_method_id = str(getattr(result, "payment_method_id", "") or "").strip()
        last4 = str(getattr(result, "last4", "") or "").strip()
        remote_detail = " ".join(
            part
            for part in (
                f"payment_method_id={payment_method_id}" if payment_method_id else "",
                f"last4={last4}" if last4 else "",
            )
            if part
        )
        persistence_detail = f"{original_error.error_code}: {original_error.error_message}".rstrip(
            ": "
        )
        detail = "; ".join(
            part
            for part in (
                f"remote bind succeeded {remote_detail}".rstrip(),
                f"local persistence failed: {persistence_detail}",
                "manual reconciliation required",
            )
            if part
        )
        diagnostics = {
            **original_error.diagnostics,
            "persistence_error_code": original_error.error_code,
        }
        if payment_method_id:
            diagnostics["payment_method_id"] = payment_method_id
        if last4:
            diagnostics["payment_method_last4"] = last4
        reconcile_error = PersonalPaymentMethodBindError(
            "payment_method_remote_success_manual_reconcile_required",
            detail,
            diagnostics=diagnostics,
        )
        try:
            self._record_failure(
                context=context,
                attempt=attempt,
                error=reconcile_error,
                stop_replay=True,
            )
        except Exception as cleanup_exc:
            cleanup_error = _bind_error(cleanup_exc)
            raise PersonalPaymentMethodBindError(
                reconcile_error.error_code,
                (
                    f"{detail}; manual reconciliation marker persistence failed: "
                    f"{cleanup_error.error_code}: {cleanup_error.error_message}"
                ).rstrip(": "),
                diagnostics={
                    **diagnostics,
                    "reconcile_persistence_error_code": cleanup_error.error_code,
                },
            ) from cleanup_exc
        return reconcile_error

    def _record_success(
        self,
        *,
        context: _BindingContext,
        attempt: _ReservedPaymentAttempt,
        result: Any,
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
                "billing_country": attempt.country,
                "proxy_country": self._registration_proxy_country,
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
    error_code = str(getattr(exc, "error_code", "") or "").strip()
    error_message = str(getattr(exc, "error_message", "") or "").strip()
    if error_code:
        return PersonalPaymentMethodBindError(
            error_code,
            error_message[:1000],
            diagnostics=getattr(exc, "diagnostics", None),
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


def _account_deactivated_bind_error(
    exc: Exception,
) -> PersonalPaymentMethodBindError | None:
    """Normalize account-deactivation errors even when browser code wraps them."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = " ".join(str(current or "").split())
        normalized = text.lower()
        if (
            type(current).__name__ == "BrowserAccountDeactivatedError"
            or "account_deactivated" in normalized
            or "account has been deleted or deactivated" in normalized
        ):
            return PersonalPaymentMethodBindError("account_deactivated", text[:1000])
        current = current.__cause__ or current.__context__
    return None


def _payment_attempt_disposition(exc: Exception, *, network_error: bool) -> str:
    disposition = str(getattr(exc, "attempt_disposition", "") or "").strip().lower()
    if disposition in {"release", "consume_retry", "consume_stop"}:
        return disposition
    if isinstance(exc, CardPaymentError):
        return "release"
    if type(exc).__name__ == "BrowserPaymentMethodConfirmError":
        return "release" if network_error else "consume_retry"
    return "release"


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
