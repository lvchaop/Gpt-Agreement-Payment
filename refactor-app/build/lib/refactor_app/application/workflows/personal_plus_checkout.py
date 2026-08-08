from __future__ import annotations

from collections.abc import Callable
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
from refactor_app.infrastructure.db.models import SpaceModel, UserAccountModel
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_browser.email_registration import CamoufoxEmailRegistration
from refactor_app.plugins.openai_auth_browser.personal_plus_checkout import (
    READ_PLUS_CHECKOUT_SESSION_SCRIPT,
    create_plus_checkout_with_script,
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
        totp_code_resolver: Callable[[str], str] | None = None,
        promotion_updater: Callable[..., Any] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._mail_provider = mail_provider
        self._us_proxy_country = us_proxy_country
        self._jp_proxy_country = jp_proxy_country
        self._promo_campaign_id = promo_campaign_id
        self._totp_code_resolver = totp_code_resolver
        self._promotion_updater = promotion_updater or update_plus_checkout_promotion

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
        }

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

    @staticmethod
    def _browser_config(proxy_url: str, *, work_id: str):
        from refactor_app.plugins.openai_auth_browser.email_registration import (
            BrowserEmailRegistrationConfig,
        )

        return BrowserEmailRegistrationConfig(proxy_url=proxy_url, headless=False, work_id=work_id)

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
        return {
            "created": created,
            "submitted": {"promo_update": promo_update, **submitted},
        }

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

    @staticmethod
    def _submit_checkout(
        page: Any,
        *,
        checkout_url: str,
        account_id: str,
    ) -> dict[str, Any]:
        if str(page.url or "").rstrip("/") != str(checkout_url or "").rstrip("/"):
            raise PersonalPlusCheckoutError("plus_checkout_page_url_mismatch")
        if not str(account_id or "").strip():
            raise PersonalPlusCheckoutError("plus_checkout_account_id_missing")
        return submit_plus_checkout_with_plugin(page)
