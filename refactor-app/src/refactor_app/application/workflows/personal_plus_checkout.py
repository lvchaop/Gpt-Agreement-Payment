from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from refactor_app.application.workflows.registration_proxy import (
    resolve_cliproxy_proxy,
)
from refactor_app.application.workflows.space_membership_invite_sync import (
    _write_space_subscription_snapshot,
)
from refactor_app.infrastructure.db.models import SpaceModel, UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_browser.personal_plus_checkout import (
    READ_PLUS_CHECKOUT_SESSION_SCRIPT,
    PlusCheckoutAlreadyPaidError,
    create_plus_checkout_with_script,
    solve_plus_checkout_challenge,
    submit_plus_checkout_with_plugin,
    update_plus_checkout_promotion,
)
from refactor_app.plugins.openai_auth_protocol.plus_checkout import (
    PlusCheckoutConfig,
    PlusCheckoutError,
    run_plus_checkout,
)


class PersonalPlusCheckoutError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        attempt_disposition: str = "release",
        error_code: str = "",
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        self.attempt_disposition = str(attempt_disposition or "release")
        self.error_code = str(error_code or "personal_plus_checkout_failed")
        self.diagnostics = dict(diagnostics or {})
        super().__init__(message)


class PersonalPlusCheckoutWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin | None = None,
        us_proxy_country: str = "US",
        jp_proxy_country: str = "JP",
        promo_campaign_id: str = "plus-1-month-free",
        checkout_ui_mode: str = "hosted",
        browser_headless: bool = True,
        browser_log_enabled: bool = False,
        browser_log_capture_bodies: bool = False,
        browser_log_max_body_chars: int = 20_000,
        totp_code_resolver: Callable[[str], str] | None = None,
        promotion_updater: Callable[..., Any] | None = None,
        openai_provider: OpenAIChatGPTProvider | None = None,
        captcha_api_url: str = "",
        captcha_client_key: str = "",
        captcha_solver: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        protocol_checkout_runner: Callable[..., Any] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._us_proxy_country = us_proxy_country
        self._jp_proxy_country = jp_proxy_country
        self._promo_campaign_id = promo_campaign_id
        self._checkout_ui_mode = str(checkout_ui_mode or "hosted").strip().lower()
        self._browser_headless = bool(browser_headless)
        self._browser_log_enabled = bool(browser_log_enabled)
        self._browser_log_capture_bodies = bool(browser_log_capture_bodies)
        self._browser_log_max_body_chars = max(1_000, int(browser_log_max_body_chars or 20_000))
        self._totp_code_resolver = totp_code_resolver
        self._promotion_updater = promotion_updater or update_plus_checkout_promotion
        self._openai_provider = openai_provider
        self._captcha_api_url = str(captcha_api_url or "").strip()
        self._captcha_client_key = str(captcha_client_key or "").strip()
        self._captcha_solver = captcha_solver
        self._protocol_checkout_runner = protocol_checkout_runner or run_plus_checkout

    def run(self, *, space_id: str, work_id: str = "", run_id: str = "") -> dict[str, Any]:
        context = self._load_context(space_id)
        if str(context.get("plan_type") or "").strip().lower() in {
            "plus",
            "chatgptplusplan",
        }:
            return {
                "space_id": space_id,
                "user_account_id": context["user_account_id"],
                "mode": "already_plus",
                "already_plus": True,
                "checkout_session_id": "",
                "subscription_sync": {
                    "status": "succeeded",
                    "plan_type": "plus",
                    "source": "local_snapshot",
                },
            }
        us_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._us_proxy_country
        )
        jp_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._jp_proxy_country
        )

        config = PlusCheckoutConfig(
            access_token=context["access_token"],
            account_id=context["external_space_id"],
            session_token=context["session_token"],
            cookie_header=context["cookie_header"],
            auth_cookie_header=context["auth_cookie_header"],
            device_id=context["device_id"],
            billing={"email": context["email"]},
            billing_country="US",
            currency="USD",
            promo_campaign_id=context["promotion_id"] or self._promo_campaign_id,
            checkout_ui_mode=self._checkout_ui_mode,
            captcha_api_url=self._captcha_api_url,
            captcha_client_key=self._captcha_client_key,
        )

        def update_promotion(**kwargs: Any) -> Any:
            created = kwargs.get("created")
            state = kwargs.get("state")
            checkout_url = str(
                kwargs.get("checkout_url") or getattr(created, "checkout_url", "") or ""
            )
            access_token = str(
                kwargs.get("access_token") or getattr(state, "access_token", "") or ""
            )
            return self._promotion_updater(
                proxy_url=jp_proxy.proxy_url,
                checkout_url=checkout_url,
                access_token=access_token or context["access_token"],
                account_id=context["external_space_id"],
                promo_campaign_id=config.promo_campaign_id,
                cookie_header=str(kwargs.get("cookie_header") or context["cookie_header"]),
                user_agent=str(kwargs.get("user_agent") or config.user_agent),
            )

        try:
            protocol_result = self._protocol_checkout_runner(
                config,
                payment_method_id=context["payment_method_id"],
                proxy_url=us_proxy.proxy_url,
                promotion_callback=update_promotion,
                session_update_callback=lambda credentials: self._persist_protocol_session(
                    user_account_id=context["user_account_id"],
                    credentials=credentials,
                ),
                event_callback=(
                    self._browser_event(run_id=run_id, work_id=work_id, stage="protocol")
                    if run_id
                    else None
                ),
            )
        except PlusCheckoutError as exc:
            raise PersonalPlusCheckoutError(
                str(exc),
                attempt_disposition=exc.attempt_disposition,
                error_code=exc.error_code,
                diagnostics=exc.diagnostics,
            ) from exc
        checkout = (
            protocol_result.to_dict()
            if callable(getattr(protocol_result, "to_dict", None))
            else protocol_result
        )
        if not isinstance(checkout, dict):
            raise PersonalPlusCheckoutError("plus_checkout_protocol_result_invalid")
        created = checkout["created"]
        submitted = checkout["submitted"]
        checkout_url = str(created.get("checkout_url") or "")

        refreshed = submitted["session_after_payment"]
        subscription_sync = self._sync_subscription_snapshot(
            space_id=space_id,
            user_account_id=context["user_account_id"],
            proxy_url=us_proxy.proxy_url,
            run_id=run_id,
            work_id=work_id,
        )
        self._require_subscription_sync(subscription_sync)
        return {
            "space_id": space_id,
            "user_account_id": context["user_account_id"],
            "checkout_url": checkout_url,
            "checkout_session_id": created.get("checkout_session_id", ""),
            "create_proxy_country": us_proxy.country_code,
            "promo_proxy_country": jp_proxy.country_code,
            "promo_proxy_sid_source": jp_proxy.sid_source,
            "promo_proxy_probe_attempts": jp_proxy.probe_attempts,
            "promo_campaign_id": config.promo_campaign_id,
            "checkout_result": submitted,
            "session_refresh": refreshed,
            "subscription_sync": subscription_sync,
        }

    def reconcile_subscription(
        self,
        *,
        space_id: str,
        work_id: str = "",
        run_id: str = "",
    ) -> dict[str, Any]:
        """Retry only the post-payment snapshot; never create or submit checkout."""
        context = self._load_context(space_id, require_payment_method=False)
        us_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._us_proxy_country
        )
        subscription_sync = self._sync_subscription_snapshot(
            space_id=space_id,
            user_account_id=context["user_account_id"],
            proxy_url=us_proxy.proxy_url,
            run_id=run_id,
            work_id=work_id,
        )
        self._require_subscription_sync(subscription_sync)
        return {
            "space_id": space_id,
            "user_account_id": context["user_account_id"],
            "mode": "subscription_sync_only",
            "create_proxy_country": us_proxy.country_code,
            "create_proxy_sid_source": us_proxy.sid_source,
            "create_proxy_probe_attempts": us_proxy.probe_attempts,
            "subscription_sync": subscription_sync,
        }

    def run_on_existing_page(
        self,
        *,
        space_id: str,
        page: Any,
        work_id: str = "",
        run_id: str = "",
    ) -> dict[str, Any]:
        """Continue directly from a successful bind page before its browser closes."""
        context = self._load_context(space_id, require_payment_method=False)
        us_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._us_proxy_country
        )
        jp_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._jp_proxy_country
        )
        checkout = self._checkout_on_page(
            page=page,
            context=context,
            promotion_proxy_url=jp_proxy.proxy_url,
            trace_emitter=(
                self._browser_event(run_id=run_id, work_id=work_id, stage="checkout")
                if run_id
                else None
            ),
        )
        created = checkout["created"]
        submitted = checkout["submitted"]
        checkout_url = str(created.get("checkout_url") or "")
        refreshed = submitted["session_after_payment"]
        subscription_sync = self._sync_subscription_snapshot(
            space_id=space_id,
            user_account_id=context["user_account_id"],
            proxy_url=us_proxy.proxy_url,
            run_id=run_id,
            work_id=work_id,
        )
        self._require_subscription_sync(subscription_sync)
        return {
            "space_id": space_id,
            "user_account_id": context["user_account_id"],
            "checkout_url": checkout_url,
            "checkout_session_id": created.get("checkout_session_id", ""),
            "create_proxy_country": self._us_proxy_country,
            "promo_proxy_country": jp_proxy.country_code,
            "promo_proxy_sid_source": jp_proxy.sid_source,
            "promo_proxy_probe_attempts": jp_proxy.probe_attempts,
            "promo_campaign_id": self._promo_campaign_id,
            "checkout_result": submitted,
            "session_refresh": refreshed,
            "subscription_sync": subscription_sync,
        }

    def _sync_subscription_snapshot(
        self,
        *,
        space_id: str,
        user_account_id: str,
        proxy_url: str,
        run_id: str,
        work_id: str,
    ) -> dict[str, Any]:
        """Refresh the paid space snapshot after payment and session refresh."""
        if self._openai_provider is None:
            result = {"status": "skipped", "reason": "openai_provider_not_configured"}
            self._write_subscription_event(
                run_id=run_id, work_id=work_id, space_id=space_id, result=result
            )
            return result

        try:
            with self._session_factory() as session:
                account = session.get(UserAccountModel, user_account_id)
                space = session.get(SpaceModel, space_id)
                if account is None or space is None:
                    raise PersonalPlusCheckoutError("plus_checkout_subscription_context_missing")
                access_token = str(account.access_token or "").strip()
                cookie_header = str(
                    account.cookie_header or account.auth_cookie_header or ""
                ).strip()
                account_id = str(space.external_space_id or "").strip()
            if not access_token or not account_id:
                raise PersonalPlusCheckoutError("plus_checkout_subscription_credentials_missing")

            subscription = self._fetch_active_plus_subscription(
                access_token=access_token,
                account_id=account_id,
                cookie_header=cookie_header,
                proxy_url=proxy_url,
            )

            now = datetime.now(UTC)
            with self._session_factory() as session:
                space = session.get(SpaceModel, space_id)
                if space is None:
                    raise PersonalPlusCheckoutError("plus_checkout_space_disappeared")
                _write_space_subscription_snapshot(
                    space=space,
                    subscription=subscription,
                    now=now,
                )
                session.commit()

            result = {
                "status": "succeeded",
                "account_id": account_id,
                "plan_type": str(
                    subscription.get("plan_type") or subscription.get("planType") or ""
                ),
                "seats_entitled": subscription.get(
                    "seats_entitled", subscription.get("seatsEntitled")
                ),
                "seats_in_use": subscription.get(
                    "seats_in_use", subscription.get("seatsInUse")
                ),
            }
            self._write_subscription_event(
                run_id=run_id, work_id=work_id, space_id=space_id, result=result
            )
            return result
        except Exception as exc:
            result = {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
            }
            self._write_subscription_event(
                run_id=run_id,
                work_id=work_id,
                space_id=space_id,
                result=result,
                level="WARN",
            )
            return result

    def _fetch_active_plus_subscription(
        self,
        *,
        access_token: str,
        account_id: str,
        cookie_header: str,
        proxy_url: str,
    ) -> dict[str, Any]:
        if self._openai_provider is None:
            raise PersonalPlusCheckoutError(
                "plus_checkout_subscription_provider_not_configured"
            )
        last_error: Exception | None = None
        last_plan_type = ""
        for delay in (0.0, 1.0, 2.0, 4.0, 8.0):
            if delay > 0:
                time.sleep(delay)
            try:
                raw = self._openai_provider.fetch_subscription(
                    access_token=access_token,
                    account_id=account_id,
                    cookie_header=cookie_header,
                    proxy_url=proxy_url,
                )
            except Exception as exc:
                last_error = exc
                continue
            if not isinstance(raw, dict):
                last_error = PersonalPlusCheckoutError(
                    "plus_checkout_subscription_response_invalid"
                )
                continue
            plan_type = self._subscription_plan_type(raw)
            last_plan_type = plan_type
            active = self._subscription_active(raw)
            status = str(raw.get("status") or "").strip().lower()
            if (
                plan_type in {"plus", "chatgptplusplan"}
                and active is not False
                and status not in {"canceled", "cancelled", "expired", "inactive"}
            ):
                return {**raw, "plan_type": "plus"}
        raise PersonalPlusCheckoutError(
            "plus_checkout_subscription_not_active_plus",
            diagnostics={
                "stage": "subscription_sync",
                "plan_type": last_plan_type,
                "error_type": type(last_error).__name__ if last_error else "",
            },
        ) from last_error

    @staticmethod
    def _subscription_plan_type(subscription: Mapping[str, Any]) -> str:
        for source in (
            subscription,
            subscription.get("account"),
            subscription.get("subscription"),
        ):
            if not isinstance(source, Mapping):
                continue
            value = str(source.get("plan_type") or source.get("planType") or "")
            if value.strip():
                return value.strip().lower()
        return ""

    @staticmethod
    def _subscription_active(subscription: Mapping[str, Any]) -> bool | None:
        sources = (subscription, subscription.get("entitlement"))
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            value = source.get("has_active_subscription")
            if value is None:
                value = source.get("hasActiveSubscription")
            if isinstance(value, bool):
                return value
            normalized = str(value or "").strip().lower()
            if normalized in {"true", "false"}:
                return normalized == "true"
        return None

    def _write_subscription_event(
        self,
        *,
        run_id: str,
        work_id: str,
        space_id: str,
        result: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        if not run_id:
            return
        try:
            with self._session_factory() as session:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type="personal_plus_checkout.subscription_sync",
                    message="personal subscription snapshot sync completed",
                    level=level,
                    data_json={"work_id": work_id, "space_id": space_id, **result},
                )
                session.commit()
        except Exception:
            pass

    @staticmethod
    def _require_subscription_sync(result: dict[str, Any]) -> None:
        if str(result.get("status") or "").strip().lower() == "succeeded":
            return
        error_type = str(result.get("error_type") or "unknown")
        error_message = str(result.get("error_message") or "")[:500]
        raise PersonalPlusCheckoutError(
            "plus_checkout_subscription_sync_failed: "
            f"{error_type}: {error_message}",
            attempt_disposition="consume_stop",
            error_code="plus_checkout_subscription_sync_failed",
            diagnostics={
                "stage": "subscription_sync",
                "error_type": error_type,
                "error_message": error_message,
            },
        )

    def _persist_protocol_session(
        self,
        *,
        user_account_id: str,
        credentials: Any,
    ) -> None:
        if not isinstance(credentials, Mapping):
            raise PersonalPlusCheckoutError("plus_checkout_session_credentials_invalid")
        access_token = str(credentials.get("access_token") or "").strip()
        session_token = str(credentials.get("session_token") or "").strip()
        cookie_header = str(credentials.get("cookie_header") or "").strip()
        device_id = str(credentials.get("device_id") or "").strip()
        csrf_token = str(credentials.get("csrf_token") or "").strip()
        if not access_token:
            raise PersonalPlusCheckoutError("plus_checkout_session_access_token_missing")

        now = datetime.now(UTC)
        with self._session_factory() as session:
            account = session.get(UserAccountModel, user_account_id)
            if account is None:
                raise PersonalPlusCheckoutError("plus_checkout_account_disappeared")
            account.access_token = access_token
            if session_token:
                account.session_token = session_token
            if cookie_header:
                account.cookie_header = cookie_header
            if device_id:
                account.device_id = device_id
            if csrf_token:
                account.csrf_token = csrf_token
            account.session_status = "active"
            account.last_session_refresh_at = now
            account.last_login_error_code = ""
            account.last_login_error_message = ""
            account.updated_at = now
            session.commit()

    def _browser_event(self, *, run_id: str, work_id: str, stage: str):
        def emit(event_type: str, data: dict[str, Any], level: str) -> None:
            if not run_id:
                return
            with self._session_factory() as session:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type=f"personal_plus_checkout.{stage}.{event_type}",
                    message=event_type,
                    level=level,
                    data_json={"work_id": work_id, "stage": stage, **data},
                )
                session.commit()

        return emit

    def _load_context(
        self,
        space_id: str,
        *,
        require_payment_method: bool = True,
    ) -> dict[str, str]:
        with self._session_factory() as session:
            space = session.get(SpaceModel, space_id)
            if space is None:
                raise PersonalPlusCheckoutError("plus_checkout_space_not_found")
            if (
                space.provider != "openai_chatgpt"
                or space.space_type != "personal"
                or space.space_status != "active"
            ):
                raise PersonalPlusCheckoutError("plus_checkout_personal_space_required")
            if not space.has_promotion or not str(space.promotion_id or "").strip():
                raise PersonalPlusCheckoutError("plus_checkout_promotion_required")
            if require_payment_method and (
                not space.has_payment_method or space.payment_method_status != "bound"
            ):
                raise PersonalPlusCheckoutError("plus_checkout_payment_method_required")
            account = session.get(UserAccountModel, space.owner_user_account_id)
            if account is None or account.account_status != "active":
                raise PersonalPlusCheckoutError("plus_checkout_owner_account_not_active")
            return {
                "user_account_id": account.id,
                "email": account.email,
                "password": account.password,
                "external_space_id": space.external_space_id,
                "access_token": account.access_token,
                "session_token": account.session_token,
                "cookie_header": account.cookie_header,
                "auth_cookie_header": account.auth_cookie_header,
                "device_id": account.device_id,
                "payment_method_id": space.payment_method_id,
                "promotion_id": space.promotion_id,
                "plan_type": str(getattr(space, "plan_type", "") or ""),
                "mfa_status": account.mfa_status,
                "twofauth_account_id": account.twofauth_account_id,
            }

    def _browser_config(self, proxy_url: str, *, work_id: str):
        from refactor_app.plugins.openai_auth_browser.email_registration import (
            BrowserEmailRegistrationConfig,
        )

        return BrowserEmailRegistrationConfig(
            proxy_url=proxy_url,
            headless=self._browser_headless,
            work_id=work_id,
            browser_log_enabled=self._browser_log_enabled,
            browser_log_capture_bodies=self._browser_log_capture_bodies,
            browser_log_max_body_chars=self._browser_log_max_body_chars,
        )

    @staticmethod
    def _create_checkout(page: Any, *, account_id: str) -> dict[str, Any]:
        try:
            created = create_plus_checkout_with_script(
                page,
                expected_account_id=account_id,
            )
        except PlusCheckoutAlreadyPaidError as exc:
            return {**exc.result, "already_paid": True}
        page.goto(str(created["checkout_url"]), wait_until="load", timeout=120_000)
        if "/auth/login" in str(page.url or ""):
            raise PersonalPlusCheckoutError("plus_checkout_login_required")
        return created

    def _totp_code_provider(self, context: dict[str, str]) -> Callable[[], str] | None:
        account_id = str(context.get("twofauth_account_id") or "").strip()
        mfa_status = str(context.get("mfa_status") or "").strip().lower()
        if mfa_status != "configured" and not account_id:
            return None

        def resolve() -> str:
            if not account_id:
                raise PersonalPlusCheckoutError("plus_checkout_twofauth_account_missing")
            if self._totp_code_resolver is None:
                raise PersonalPlusCheckoutError("plus_checkout_twofauth_client_not_configured")
            code = str(self._totp_code_resolver(account_id) or "").strip()
            if not code.isdigit():
                raise PersonalPlusCheckoutError("plus_checkout_twofauth_invalid_code")
            return code

        return resolve

    def _checkout_on_page(
        self,
        *,
        page: Any,
        context: dict[str, str],
        promotion_proxy_url: str,
        trace_emitter: Callable[[str, dict[str, Any], str], None] | None = None,
    ) -> dict[str, dict[str, Any]]:
        created = self._create_checkout(
            page,
            account_id=context["external_space_id"],
        )
        if created.get("already_paid") is True:
            session_after_payment = self._refresh_session_after_payment(
                page=page,
                checkout_url="",
                context=context,
            )
            return {
                "created": created,
                "submitted": {
                    "phase": "already_paid",
                    "provider": str(created.get("provider") or ""),
                    "promo_update": {
                        "status": "skipped",
                        "reason": "checkout_create_already_paid",
                    },
                    "payment_result": {
                        "state": "succeeded",
                        "payment_object_status": "already_paid",
                        "source": "checkout_create_already_paid",
                    },
                    "session_after_payment": session_after_payment,
                },
            }
        checkout_url = str(created.get("checkout_url") or "")
        if not checkout_url:
            raise PersonalPlusCheckoutError("plus_checkout_url_missing")

        session = self._read_checkout_session(
            page,
            account_id=context["external_space_id"],
        )
        promo_update = self._promotion_updater(
            proxy_url=promotion_proxy_url,
            checkout_url=checkout_url,
            access_token=session["access_token"],
            account_id=session["account_id"],
            promo_campaign_id=self._promo_campaign_id,
            cookie_header=self._current_cookie_header(page) or context["cookie_header"],
            user_agent=session["user_agent"],
        )
        submitted = self._submit_checkout(
            page,
            checkout_url=checkout_url,
            account_id=context["external_space_id"],
            trace_emitter=trace_emitter,
        )
        payment_state = str(
            (submitted.get("payment_result") or {}).get("state") or ""
        ).strip().lower()
        if payment_state != "succeeded":
            raise PersonalPlusCheckoutError(
                f"plus_checkout_payment_not_succeeded:{payment_state or 'missing'}"
            )
        session_after_payment = self._refresh_session_after_payment(
            page=page,
            checkout_url=checkout_url,
            context=context,
        )
        return {
            "created": created,
            "submitted": {
                "promo_update": promo_update,
                "session_after_payment": session_after_payment,
                **submitted,
            },
        }

    def _refresh_session_after_payment(
        self,
        *,
        page: Any,
        checkout_url: str,
        context: dict[str, str],
    ) -> dict[str, Any]:
        if checkout_url:
            page.goto(checkout_url, wait_until="load", timeout=120_000)
        self._wait_for_browser_navigation(page)
        if "/auth/login" in str(page.url or ""):
            raise PersonalPlusCheckoutError("plus_checkout_post_payment_login_required")

        session_info = self._read_checkout_session(
            page,
            account_id=context["external_space_id"],
        )
        cookies = page.context.cookies(["https://chatgpt.com"])
        cookie_header = self._cookie_header(cookies)
        session_token = self._session_cookie_token(cookies)
        device_id = self._cookie_value(cookies, ("oai-did", "oai-device-id"))
        csrf_cookie = self._cookie_value(cookies, ("__Host-next-auth.csrf-token",))
        csrf_token = csrf_cookie.split("|", 1)[0] if csrf_cookie else ""
        now = datetime.now(UTC)

        with self._session_factory() as session:
            account = session.get(UserAccountModel, context["user_account_id"])
            if account is None:
                raise PersonalPlusCheckoutError("plus_checkout_account_disappeared")
            account.access_token = session_info["access_token"]
            if session_token:
                account.session_token = session_token
            if cookie_header:
                account.cookie_header = cookie_header
            if device_id:
                account.device_id = device_id
            if csrf_token:
                account.csrf_token = csrf_token
            account.session_status = "active"
            account.last_session_refresh_at = now
            account.last_login_error_code = ""
            account.last_login_error_message = ""
            account.updated_at = now
            session.commit()

        return {
            "status": "succeeded",
            "account_id": session_info["account_id"],
            "plan_type": session_info["plan_type"],
            "has_access_token": True,
            "has_session_token": bool(session_token),
            "has_cookie_header": bool(cookie_header),
            "session_endpoint": "/api/auth/session",
        }

    @staticmethod
    def _wait_for_browser_navigation(page: Any) -> None:
        """Wait for the final Checkout redirect before reading the refreshed session."""
        wait_for_load_state = getattr(page, "wait_for_load_state", None)
        if callable(wait_for_load_state):
            for state, timeout_ms in (
                ("domcontentloaded", 15_000),
                ("load", 15_000),
                ("networkidle", 5_000),
            ):
                try:
                    wait_for_load_state(state, timeout=timeout_ms)
                except Exception:
                    pass
        wait_for_timeout = getattr(page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            wait_for_timeout(3_000)
        else:
            # Test doubles do not expose Playwright's wait API.
            time.sleep(0)

    @staticmethod
    def _cookie_header(cookies: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        for cookie in cookies:
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
            if not name or not value or name in seen:
                continue
            parts.append(f"{name}={value}")
            seen.add(name)
        return "; ".join(parts)

    @staticmethod
    def _cookie_value(cookies: list[dict[str, Any]], names: tuple[str, ...]) -> str:
        for name in names:
            for cookie in cookies:
                if cookie.get("name") == name and cookie.get("value"):
                    return str(cookie["value"])
        return ""

    @classmethod
    def _session_cookie_token(cls, cookies: list[dict[str, Any]]) -> str:
        direct = cls._cookie_value(cookies, ("__Secure-next-auth.session-token",))
        if direct:
            return direct
        prefix = "__Secure-next-auth.session-token."
        chunks = sorted(
            (
                str(cookie.get("name") or ""),
                str(cookie.get("value") or ""),
            )
            for cookie in cookies
            if str(cookie.get("name") or "").startswith(prefix)
            and cookie.get("value")
        )
        return "".join(value for _, value in chunks)

    @staticmethod
    def _read_checkout_session(page: Any, *, account_id: str) -> dict[str, str]:
        value = page.evaluate(
            READ_PLUS_CHECKOUT_SESSION_SCRIPT,
            {"expectedAccountId": account_id},
        )
        if not isinstance(value, dict):
            raise PersonalPlusCheckoutError("plus_checkout_session_invalid")
        access_token = str(value.get("access_token") or "").strip()
        observed_account_id = str(value.get("account_id") or "").strip()
        if not access_token or not observed_account_id:
            raise PersonalPlusCheckoutError("plus_checkout_session_missing")
        return {
            "access_token": access_token,
            "account_id": observed_account_id,
            "plan_type": str(value.get("plan_type") or "").strip(),
            "user_agent": str(value.get("user_agent") or "").strip(),
        }

    @staticmethod
    def _current_cookie_header(page: Any) -> str:
        cookies = page.context.cookies(["https://chatgpt.com"])
        return "; ".join(
            f"{cookie['name']}={cookie['value']}"
            for cookie in cookies
            if cookie.get("name") and cookie.get("value") is not None
        )

    def _submit_checkout(
        self,
        page: Any,
        *,
        checkout_url: str,
        account_id: str,
        trace_emitter: Callable[[str, dict[str, Any], str], None] | None = None,
    ) -> dict[str, Any]:
        if str(page.url or "").rstrip("/") != str(checkout_url or "").rstrip("/"):
            raise PersonalPlusCheckoutError("plus_checkout_page_url_mismatch")
        if not str(account_id or "").strip():
            raise PersonalPlusCheckoutError("plus_checkout_account_id_missing")
        captcha_solver = self._captcha_solver
        if captcha_solver is None and self._captcha_api_url and self._captcha_client_key:
            def remote_solver(challenge: dict[str, Any]) -> dict[str, Any]:
                return solve_plus_checkout_challenge(
                    challenge,
                    api_url=self._captcha_api_url,
                    client_key=self._captcha_client_key,
                )

            captcha_solver = remote_solver
        submit_kwargs: dict[str, Any] = {}
        if captcha_solver is not None:
            submit_kwargs["captcha_solver"] = captcha_solver
        if trace_emitter is not None:
            submit_kwargs["trace_emitter"] = trace_emitter
        return submit_plus_checkout_with_plugin(page, **submit_kwargs)
