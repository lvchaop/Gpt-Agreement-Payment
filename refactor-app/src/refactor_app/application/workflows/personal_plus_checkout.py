from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from refactor_app.application.workflows.account_auth import BackfillSessionWorkflow
from refactor_app.application.workflows.personal_payment_method import (
    mail_provider_name_for_email,
)
from refactor_app.application.workflows.protocol_registration import (
    RegistrationMailProviderAdapter,
)
from refactor_app.application.workflows.registration_proxy import (
    resolve_cliproxy_proxy,
)
from refactor_app.application.workflows.space_membership_invite_sync import (
    _write_space_subscription_snapshot,
)
from refactor_app.infrastructure.db.models import SpaceModel, UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.contracts import OpenAIChatGPTProvider
from refactor_app.plugins.openai_auth_browser.email_registration import CamoufoxEmailRegistration
from refactor_app.plugins.openai_auth_browser.personal_plus_checkout import (
    READ_PLUS_CHECKOUT_SESSION_SCRIPT,
    create_plus_checkout_with_script,
    solve_plus_checkout_challenge,
    submit_plus_checkout_with_plugin,
    update_plus_checkout_promotion,
)


class PersonalPlusCheckoutError(RuntimeError):
    pass


class PersonalPlusCheckoutWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        mail_provider: ExternalMailApiPlugin,
        us_proxy_country: str = "US",
        jp_proxy_country: str = "JP",
        promo_campaign_id: str = "plus-1-month-free",
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
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._us_proxy_country = us_proxy_country
        self._jp_proxy_country = jp_proxy_country
        self._promo_campaign_id = promo_campaign_id
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

    def run(self, *, space_id: str, work_id: str = "", run_id: str = "") -> dict[str, Any]:
        context = self._load_context(space_id)
        us_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._us_proxy_country
        )
        jp_proxy = resolve_cliproxy_proxy(
            email=context["email"], country_code=self._jp_proxy_country
        )

        creator = CamoufoxEmailRegistration(
            self._browser_config(us_proxy.proxy_url, work_id=f"{work_id}-create"),
            event_callback=self._browser_event(run_id=run_id, work_id=work_id, stage="create"),
        )
        mail = RegistrationMailProviderAdapter(
            mail_provider=self._mail_provider,
            caller_id="personal-plus-checkout",
            task_id=work_id,
            provider=mail_provider_name_for_email(context["email"]),
            project_key="personal-plus-checkout",
            email_domain=context["email"].rpartition("@")[2],
            fixed_email=context["email"],
        )
        checkout = creator.run_authenticated_page_with_login(
            mail,
            login_password=context["password"],
            totp_code_provider=self._totp_code_provider(context),
            after_session=lambda _ctx, page, _result: self._checkout_on_page(
                page=page,
                context=context,
                promotion_proxy_url=jp_proxy.proxy_url,
            ),
        )
        created = checkout["created"]
        submitted = checkout["submitted"]
        checkout_url = str(created["checkout_url"])

        refreshed = BackfillSessionWorkflow(
            session_factory=self._session_factory,
            mail_provider=self._mail_provider,
            totp_code_resolver=self._totp_code_resolver,
        ).run(user_account_id=context["user_account_id"], run_id=run_id)
        subscription_sync = self._sync_subscription_snapshot(
            space_id=space_id,
            user_account_id=context["user_account_id"],
            proxy_url=us_proxy.proxy_url,
            run_id=run_id,
            work_id=work_id,
        )
        return {
            "space_id": space_id,
            "user_account_id": context["user_account_id"],
            "checkout_url": checkout_url,
            "checkout_session_id": created.get("checkout_session_id", ""),
            "create_proxy_country": us_proxy.country_code,
            "promo_proxy_country": jp_proxy.country_code,
            "promo_proxy_sid_source": jp_proxy.sid_source,
            "promo_proxy_probe_attempts": jp_proxy.probe_attempts,
            "promo_campaign_id": self._promo_campaign_id,
            "checkout_result": submitted,
            "session_refresh": refreshed,
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
        )
        created = checkout["created"]
        submitted = checkout["submitted"]
        checkout_url = str(created["checkout_url"])
        refreshed = BackfillSessionWorkflow(
            session_factory=self._session_factory,
            mail_provider=self._mail_provider,
            totp_code_resolver=self._totp_code_resolver,
        ).run(user_account_id=context["user_account_id"], run_id=run_id)
        subscription_sync = self._sync_subscription_snapshot(
            space_id=space_id,
            user_account_id=context["user_account_id"],
            proxy_url=us_proxy.proxy_url,
            run_id=run_id,
            work_id=work_id,
        )
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
                cookie_header = str(account.cookie_header or account.auth_cookie_header or "").strip()
                account_id = str(space.external_space_id or "").strip()
            if not access_token or not account_id:
                raise PersonalPlusCheckoutError("plus_checkout_subscription_credentials_missing")

            subscription = self._openai_provider.fetch_subscription(
                access_token=access_token,
                account_id=account_id,
                cookie_header=cookie_header,
                proxy_url=proxy_url,
            )
            if not isinstance(subscription, dict):
                raise PersonalPlusCheckoutError("plus_checkout_subscription_response_invalid")

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
        with self._session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type="personal_plus_checkout.subscription_sync",
                message="personal subscription snapshot sync completed",
                level=level,
                data_json={"work_id": work_id, "space_id": space_id, **result},
            )
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
                "cookie_header": account.cookie_header,
                "auth_cookie_header": account.auth_cookie_header,
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
        created = create_plus_checkout_with_script(
            page,
            expected_account_id=account_id,
        )
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
    ) -> dict[str, dict[str, Any]]:
        created = self._create_checkout(
            page,
            account_id=context["external_space_id"],
        )
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
        page.goto(checkout_url, wait_until="load", timeout=120_000)
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
            "has_access_token": True,
            "has_session_token": bool(session_token),
            "has_cookie_header": bool(cookie_header),
            "session_endpoint": "/api/auth/session",
        }

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
        if captcha_solver is None:
            return submit_plus_checkout_with_plugin(page)
        return submit_plus_checkout_with_plugin(page, captcha_solver=captcha_solver)
