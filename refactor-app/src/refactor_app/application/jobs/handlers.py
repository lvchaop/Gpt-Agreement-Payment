from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from refactor_app.application.jobs.attempt_disposition import (
    PERSONAL_PLUS_CHECKOUT_FAILURE_SCOPE,
    checkpoint_personal_plus_checkout_failure,
    checkpoint_personal_plus_checkout_sync_pending,
    has_personal_plus_checkout_consume_stop,
    has_personal_plus_checkout_sync_failure,
    personal_plus_checkout_consume_stop_exists_for,
    personal_plus_checkout_sync_failure_exists_for,
    resolve_personal_plus_checkout_sync_failures,
    try_acquire_personal_plus_checkout_lock,
)
from refactor_app.application.jobs.queue import WorkQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.application.workflows.account_auth import (
    BackfillRtWorkflow,
    BackfillSessionRtWorkflow,
    BackfillSessionWorkflow,
    CodexAuthorizationFallbackRequired,
    ensure_account_proxy_url,
)
from refactor_app.application.workflows.account_email_change import (
    AccountEmailChangeInput,
    AccountEmailChangeWorkflow,
)
from refactor_app.application.workflows.downstream_provider import provider_from_channel
from refactor_app.application.workflows.mail import (
    AllocateMailLeaseWorkflow,
    MarkMailLeaseFailedWorkflow,
    MarkMailLeaseUsedWorkflow,
    PollMailOtpWorkflow,
    ReleaseMailLeaseWorkflow,
)
from refactor_app.application.workflows.personal_payment_method import (
    PersonalPaymentMethodBindWorkflow,
)
from refactor_app.application.workflows.personal_paypal_agreement import (
    PayPalAgreementAddressPoolProvider,
    PayPalAgreementCardPoolProvider,
    PayPalAgreementNamePoolProvider,
    PersonalPayPalAgreementError,
    PersonalPayPalAgreementWorkflow,
    sanitize_personal_paypal_agreement_output,
)
from refactor_app.application.workflows.personal_paypal_link import (
    PersonalPayPalLinkError,
    PersonalPayPalLinkWorkflow,
    normalize_paypal_link_currency,
)
from refactor_app.application.workflows.personal_plus_checkout import (
    PersonalPlusCheckoutError,
    PersonalPlusCheckoutWorkflow,
)
from refactor_app.application.workflows.protocol_registration import (
    EMAIL_BROWSER_NO_PHONE,
    EMAIL_PROTOCOL_NO_PHONE,
    HERO_EMAIL_PROVIDERS,
    PHONE_BROWSER_BIND_EMAIL,
    PHONE_PROTOCOL_BIND_EMAIL,
    HeroSmsLongTermPhoneProviderAdapter,
    HeroSmsPhoneProviderAdapter,
    ProtocolRegistrationInput,
    ProtocolRegistrationWorkflow,
    registration_mode_requires_security,
)
from refactor_app.application.workflows.proxy import (
    BindAccountProxyWorkflow,
    BindTeamAdminProxyWorkflow,
    HealthcheckProxyWorkflow,
    RefreshWebsharePoolWorkflow,
)
from refactor_app.application.workflows.registration_proxy import (
    CliproxyProxyConfig,
    resolve_cliproxy_proxy,
)
from refactor_app.application.workflows.space_authorization import (
    BUSINESS_ACCESS_TOKEN_MIN_INTERVAL_S,
    BusinessCodexAuthorizationTarget,
    CreateBusinessAccessTokenCredentialInput,
    CreateBusinessAccessTokenCredentialWorkflow,
    resolve_business_codex_authorization_target,
    resolve_personal_codex_authorization_target,
    run_business_access_token_rate_limited,
)
from refactor_app.application.workflows.space_auto_replenish import (
    MAX_INVITE_BATCH_SIZE,
    SpaceAutoReplenishWorkflow,
)
from refactor_app.application.workflows.space_credential_heartbeat import (
    PersonalCodexCredentialHeartbeatInput,
    PersonalCodexCredentialHeartbeatWorkflow,
)
from refactor_app.application.workflows.space_direct_push import (
    SpaceDirectPushInput,
    SpaceDirectPushWorkflow,
)
from refactor_app.application.workflows.space_membership_growth import (
    DEFAULT_SESSION_WAIT_TIMEOUT_S,
    SpaceMembershipGrowthWorkflow,
)
from refactor_app.application.workflows.space_membership_invite_sync import (
    SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
    SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
    SpaceDynamicMembershipInviteInput,
    SpaceDynamicMembershipInviteWorkflow,
    SpaceMembershipInviteSyncInput,
    SpaceMembershipInviteSyncWorkflow,
)
from refactor_app.application.workflows.space_recycle import (
    SpaceRecycleSweepInput,
    SpaceRecycleSweepWorkflow,
)
from refactor_app.application.workflows.space_seat_expansion import SpaceSeatExpansionWorkflow
from refactor_app.application.workflows.space_session_otp import SpaceSessionOtpWorkflow
from refactor_app.application.workflows.space_session_otp_remote import (
    RemoteSessionOtpBridgeError,
    SessionOtpExecutorClient,
    run_remote_space_session_otp_submit,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.models import (
    DownstreamChannelModel,
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.hero_email import HeroEmailClientConfig, HeroEmailPlugin
from refactor_app.plugins.mail_external_api.client import (
    ClaimedMailAccount,
    ExternalMailApiClientConfig,
)
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.config import PhoneConfig
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTClientConfig,
    OpenAIChatGPTClientError,
)
from refactor_app.plugins.openai_chatgpt.plugin import OpenAIChatGPTPlugin
from refactor_app.plugins.proxy_webshare.client import WebshareClientConfig
from refactor_app.plugins.proxy_webshare.plugin import WebshareProxyPlugin
from refactor_app.plugins.twofauth import TwoFAuthClient, TwoFAuthClientConfig

SessionFactory = Callable[[], Session]

_PAYPAL_AGREEMENT_GRIZZLY_COUNTRIES = {
    "AU": "175",
    "BR": "73",
    "CA": "36",
    "DE": "43",
    "FR": "78",
    "GB": "16",
    "JP": "182",
    "NL": "48",
    "PL": "15",
    "SG": "10351",
    "TH": "52",
    "US": "187",
}


def _backfill_session_proxy_resolver(settings: Settings):
    config = CliproxyProxyConfig.from_settings(settings)

    def resolve(*, email: str, country_code: str, force_new_sid: bool = False):
        return resolve_cliproxy_proxy(
            email=email,
            country_code=country_code,
            config=config,
            force_new_sid=force_new_sid,
        )

    return resolve


def register_core_handlers(
    runner: JobRunner,
    *,
    session_factory: SessionFactory,
    settings: Settings,
) -> None:
    totp_code_resolver = _twofauth_otp_resolver(settings)
    backfill_session_proxy_resolver = _backfill_session_proxy_resolver(settings)
    runner.register(
        "proxy.refresh_webshare_pool",
        lambda _session, input_json: {
            "proxy_count": RefreshWebsharePoolWorkflow(
                session_factory=session_factory,
                proxy_provider=_webshare_plugin(
                    settings,
                    download_url=str(input_json.get("download_url") or ""),
                    proxy_type=str(input_json.get("proxy_type") or "proxyserver"),
                ),
                proxy_type=str(input_json.get("proxy_type") or "proxyserver"),
            ).run()
        },
    )
    runner.register(
        "proxy.bind_account",
        lambda _session, input_json: {
            "proxy_binding_id": BindAccountProxyWorkflow(session_factory=session_factory).run(
                user_account_id=str(input_json["user_account_id"]),
                bound_by_job_id=str(input_json.get("bound_by_job_id") or ""),
                bind_reason=str(input_json.get("bind_reason") or ""),
            )
        },
    )
    runner.register(
        "proxy.bind_team_admin",
        lambda _session, input_json: {
            "proxy_binding_id": BindTeamAdminProxyWorkflow(session_factory=session_factory).run(
                team_admin_session_id=str(input_json["team_admin_session_id"]),
                bind_reason=str(input_json.get("bind_reason") or ""),
            )
        },
    )
    runner.register(
        "proxy.healthcheck",
        lambda _session, input_json: HealthcheckProxyWorkflow(session_factory=session_factory).run(
            proxy_id=str(input_json["proxy_id"])
        ),
    )
    runner.register(
        "mail.allocate",
        lambda _session, input_json: {
            "mail_lease_id": AllocateMailLeaseWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
            ).run(
                user_account_id=input_json.get("user_account_id"),
                purpose=str(input_json.get("purpose") or ""),
            )
        },
    )
    runner.register(
        "mail.poll_otp",
        lambda _session, input_json: {
            "otp": PollMailOtpWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
            ).run(
                mail_lease_id=str(input_json["mail_lease_id"]),
                timeout_s=int(input_json.get("timeout_s") or 60),
            )
        },
    )
    runner.register(
        "mail.mark_used",
        lambda _session, input_json: {
            "mail_lease_id": MarkMailLeaseUsedWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
            ).run(mail_lease_id=str(input_json["mail_lease_id"]))
        },
    )
    runner.register(
        "mail.mark_failed",
        lambda _session, input_json: {
            "mail_lease_id": MarkMailLeaseFailedWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
            ).run(
                mail_lease_id=str(input_json["mail_lease_id"]),
                failure_code=str(input_json.get("failure_code") or ""),
                failure_message=str(input_json.get("failure_message") or ""),
            )
        },
    )
    runner.register(
        "mail.release",
        lambda _session, input_json: {
            "mail_lease_id": ReleaseMailLeaseWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
            ).run(
                mail_lease_id=str(input_json["mail_lease_id"]),
                reason=str(input_json.get("reason") or ""),
            )
        },
    )
    runner.register(
        "space.business_access_token.create.bulk",
        lambda _session, input_json: _run_space_authorization_bulk_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space_credential.push.bulk",
        lambda _session, input_json: {
            "work_count": len(input_json.get("space_credential_ids") or []),
        },
    )
    runner.register(
        "space.personal_codex_credential_heartbeat.tick",
        lambda _session, input_json: {
            "work_count": len(input_json.get("space_credential_ids") or []),
        },
    )
    runner.register(
        "account.backfill_session_rt",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "account.backfill_session",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "account.refresh_session_space_detection",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "account.backfill_rt",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "automation.space_authorize",
        lambda _session, input_json: _run_space_authorization_bulk_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "account.session_otp.prepare.bulk",
        lambda _session, input_json: {
            "work_count": int(input_json.get("selected_count") or 0),
        },
    )
    runner.register(
        "account.session_otp.submit.bulk",
        lambda _session, input_json: {
            "work_count": int(input_json.get("selected_count") or 0),
        },
    )
    runner.register(
        "account.session_otp.remote_submit.bulk",
        lambda _session, _input_json: {"work_count": 1},
    )
    runner.register(
        "account.protocol_register",
        lambda _session, input_json: _run_protocol_register_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "account.change_email.bulk",
        lambda _session, input_json: {
            "work_count": int(input_json.get("selected_count") or 0),
        },
    )
    runner.register(
        "space.membership_invite_sync",
        lambda _session, input_json: _run_space_membership_invite_sync_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.membership_invite_dynamic",
        lambda _session, input_json: _run_space_membership_invite_dynamic_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.membership_growth_round",
        lambda _session, input_json: _run_space_membership_growth_job(
            session_factory=session_factory,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.recycle.sweep",
        lambda _session, input_json: _run_space_recycle_sweep_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.seat_expand",
        lambda _session, input_json: _run_space_seat_expand_job(
            session_factory=session_factory,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.auto_replenish.tick",
        lambda _session, input_json: _run_space_auto_replenish_tick_job(
            session_factory=session_factory,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.auto_replenish.invite.prepare",
        lambda _session, input_json: _run_space_auto_replenish_invite_job(
            session_factory=session_factory,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.personal_payment_method_bind.tick",
        lambda _session, input_json: _run_personal_payment_method_bind_tick_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.personal_plus_checkout.tick",
        lambda _session, input_json: _run_personal_plus_checkout_tick_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.personal_paypal_link.tick",
        lambda _session, input_json: _run_personal_paypal_link_tick_job(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register(
        "space.personal_subscription_refresh.selected",
        lambda _session, input_json: _run_personal_subscription_refresh_selected_job(
            session_factory=session_factory,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "space.membership_invite.account",
        lambda _session, input_json: {
            "invite": SpaceMembershipInviteSyncWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run_invite_work(
                space_id=str(input_json["space_id"]),
                user_account_id=str(input_json["user_account_id"]),
                team_admin_session_id=str(input_json["team_admin_session_id"]),
                barrier_key=str(input_json.get("_barrier_key") or ""),
                barrier_group=str(input_json.get("_barrier_group") or ""),
                barrier_expected=int(input_json.get("_barrier_expected") or 0),
                barrier_timeout_s=float(input_json.get("_barrier_timeout_s") or 30),
                run_id=str(input_json.get("_run_id") or ""),
                work_id=str(input_json.get("_work_id") or ""),
            )
        },
    )
    runner.register_work(
        "space.membership_invite.dynamic_batch",
        lambda _session, input_json: {
            "invite": SpaceDynamicMembershipInviteWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run_batch_work(
                space_id=str(input_json["space_id"]),
                team_admin_session_id=str(input_json["team_admin_session_id"]),
                user_account_ids=[str(item) for item in input_json.get("user_account_ids") or []],
            )
        },
    )
    runner.register_work(
        "space.membership_growth.invite_batch",
        lambda _session, input_json: SpaceMembershipGrowthWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_plugin(settings),
        ).run_invite_batch_work(
            job_id=str(input_json["job_id"]),
            run_id=str(input_json.get("_run_id") or ""),
            space_id=str(input_json["space_id"]),
            session_wait_timeout_s=int(
                input_json.get("session_wait_timeout_s") or DEFAULT_SESSION_WAIT_TIMEOUT_S
            ),
        ),
    )
    runner.register_work(
        "space.membership_growth.session",
        lambda _session, input_json: _run_space_membership_growth_session_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "space.membership_growth.finalize",
        lambda _session, input_json: SpaceMembershipGrowthWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_plugin(settings),
        ).run_finalize_work(
            job_id=str(input_json["job_id"]),
            run_id=str(input_json.get("_run_id") or ""),
            space_id=str(input_json["space_id"]),
            user_account_ids=[str(item) for item in input_json.get("user_account_ids") or []],
            session_work_ids=[str(item) for item in input_json.get("session_work_ids") or []],
            session_wait_timeout_s=int(
                input_json.get("session_wait_timeout_s") or DEFAULT_SESSION_WAIT_TIMEOUT_S
            ),
        ),
    )
    runner.register_work(
        "space.business_access_token.create.account",
        lambda _session, input_json: _run_space_business_access_token_account_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "space.business_codex.authorize.account",
        lambda _session, input_json: _run_space_business_codex_authorization_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "space_credential.push.account",
        lambda _session, input_json: {
            "space_credential_id": SpaceDirectPushWorkflow(
                session_factory=session_factory,
                downstream_provider=_downstream_plugin_from_channel_id(
                    session_factory,
                    str(input_json["downstream_channel_id"]),
                ),
            ).run(
                SpaceDirectPushInput(
                    space_credential_id=str(input_json["space_credential_id"]),
                    downstream_channel_id=str(input_json["downstream_channel_id"]),
                    is_retry=bool(input_json.get("is_retry") or False),
                )
            )
        },
    )
    runner.register_work(
        "space.personal_codex_credential_heartbeat.account",
        lambda _session, input_json: _run_personal_codex_credential_heartbeat_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "space.recycle.binding",
        lambda _session, input_json: (
            SpaceRecycleSweepWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            )
            .run_binding(space_credential_id=str(input_json["space_credential_id"]))
            .__dict__
        ),
    )
    runner.register_work(
        "space.seat_expand.one",
        lambda _session, input_json: SpaceSeatExpansionWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_plugin(settings),
        ).run(
            space_id=str(input_json["space_id"]),
            run_id=str(input_json.get("_run_id") or ""),
            work_id=str(input_json.get("_work_id") or ""),
        ),
    )
    runner.register_work(
        "space.auto_replenish.space",
        lambda _session, input_json: _space_auto_replenish_workflow(
            session_factory=session_factory,
            settings=settings,
        ).run_space_cycle(
            space_id=str(input_json["space_id"]),
            run_id=str(input_json.get("_run_id") or ""),
            work_id=str(input_json.get("_work_id") or ""),
        ),
    )
    runner.register_work(
        "space.auto_replenish.invite.prepare_space",
        lambda _session, input_json: _space_auto_replenish_workflow(
            session_factory=session_factory,
            settings=settings,
        ).prepare_invites(
            space_id=str(input_json["space_id"]),
            invite_count=int(input_json.get("invite_count") or MAX_INVITE_BATCH_SIZE),
            run_id=str(input_json.get("_run_id") or ""),
        ),
    )

    def personal_payment_method_workflow(
        input_json: dict,
        *,
        require_local_promotion: bool = True,
    ) -> PersonalPaymentMethodBindWorkflow:
        return PersonalPaymentMethodBindWorkflow(
            session_factory=session_factory,
            registration_proxy_country=str(
                input_json.get("checkout_proxy_country")
                or input_json.get("proxy_country")
                or input_json.get("create_proxy_country")
                or settings.personal_plus_checkout_create_proxy_country
            ).strip().upper(),
            promo_campaign_id=settings.personal_plus_checkout_promo_campaign_id,
            checkout_ui_mode=str(
                input_json.get("checkout_ui_mode")
                or getattr(settings, "personal_payment_method_checkout_ui_mode", "custom")
                or "custom"
            ),
            require_local_promotion=require_local_promotion,
        )

    def terminal_plus_checkout_output(space_id: str) -> dict[str, Any]:
        return {
            "_work_outcome": "skipped",
            "space_id": space_id,
            "skip_reason": "personal_plus_checkout_consume_stop_exists",
            "failure_scope": PERSONAL_PLUS_CHECKOUT_FAILURE_SCOPE,
            "attempt_disposition": "consume_stop",
            "terminal": True,
        }

    def concurrent_plus_checkout_output(space_id: str) -> dict[str, Any]:
        return {
            "_work_outcome": "skipped",
            "space_id": space_id,
            "skip_reason": "personal_plus_checkout_in_progress",
            "failure_scope": PERSONAL_PLUS_CHECKOUT_FAILURE_SCOPE,
            "attempt_disposition": "release",
            "terminal": False,
        }

    def acquire_plus_checkout_guard(
        work_session: Session | None,
        *,
        space_id: str,
        start_new_checkout: bool = False,
    ) -> tuple[dict[str, Any] | None, bool]:
        if work_session is None:
            return None, False

        def prior_attempt_state() -> tuple[dict[str, Any] | None, bool]:
            terminal = has_personal_plus_checkout_consume_stop(
                work_session,
                space_id=space_id,
            )
            if terminal and start_new_checkout:
                return None, False
            recoverable_sync = bool(
                terminal
                and has_personal_plus_checkout_sync_failure(
                    work_session,
                    space_id=space_id,
                )
            )
            if terminal and not recoverable_sync:
                return terminal_plus_checkout_output(space_id), False
            return None, recoverable_sync

        guard_output, sync_only = prior_attempt_state()
        if guard_output is not None:
            return guard_output, sync_only
        if not try_acquire_personal_plus_checkout_lock(
            work_session,
            space_id=space_id,
        ):
            return concurrent_plus_checkout_output(space_id), False
        # Close the check/lock race: a prior worker may have committed its
        # terminal marker immediately before this transaction acquired the lock.
        return prior_attempt_state()

    def personal_plus_checkout_workflow(
        input_json: dict,
    ) -> PersonalPlusCheckoutWorkflow:
        checkout_proxy_country = str(
            input_json.get("checkout_proxy_country")
            or input_json.get("proxy_country")
            or input_json.get("create_proxy_country")
            or settings.personal_plus_checkout_create_proxy_country
        ).strip().upper()
        update_proxy_country = str(
            input_json.get("update_proxy_country")
            or input_json.get("promo_proxy_country")
            or checkout_proxy_country
        ).strip().upper()
        return PersonalPlusCheckoutWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_plugin(settings),
            checkout_proxy_country=checkout_proxy_country,
            update_proxy_country=update_proxy_country,
            promo_campaign_id=str(
                input_json.get("promo_campaign_id")
                or settings.personal_plus_checkout_promo_campaign_id
            ),
            checkout_ui_mode=str(
                input_json.get("checkout_ui_mode")
                or getattr(settings, "personal_plus_checkout_ui_mode", "hosted")
                or "hosted"
            ),
            browser_headless=bool(input_json.get("browser_headless", True)),
            browser_log_enabled=bool(
                input_json.get(
                    "browser_log_enabled",
                    getattr(settings, "browser_log_enabled", False),
                )
            ),
            browser_log_capture_bodies=bool(
                input_json.get(
                    "browser_log_capture_bodies",
                    getattr(settings, "browser_log_capture_bodies", False),
                )
            ),
            browser_log_max_body_chars=int(
                input_json.get(
                    "browser_log_max_body_chars",
                    getattr(settings, "browser_log_max_body_chars", 20_000),
                )
            ),
            totp_code_resolver=totp_code_resolver,
            captcha_api_url=str(
                input_json.get("captcha_api_url")
                or getattr(settings, "personal_plus_checkout_captcha_api_url", "")
                or ""
            ),
            captcha_client_key=str(
                input_json.get("captcha_client_key")
                or getattr(settings, "personal_plus_checkout_captcha_client_key", "")
                or ""
            ),
        )

    def reconcile_plus_subscription(
        work_session: Session | None,
        *,
        workflow: PersonalPlusCheckoutWorkflow,
        space_id: str,
        work_id: str,
        run_id: str,
        proxy_url_override: str = "",
    ) -> dict[str, Any]:
        reconcile_kwargs = {
            "space_id": space_id,
            "work_id": work_id,
            "run_id": run_id,
        }
        if proxy_url_override:
            reconcile_kwargs["proxy_url_override"] = proxy_url_override
        output = workflow.reconcile_subscription(**reconcile_kwargs)
        if work_session is not None:
            output["resolved_markers"] = resolve_personal_plus_checkout_sync_failures(
                work_session,
                space_id=space_id,
                work_id=work_id,
            )
        return output

    def checkpoint_plus_checkout_failure(
        work_session: Session | None,
        *,
        work_id: str,
        exc: BaseException,
    ) -> None:
        if work_session is None:
            return
        try:
            checkpoint_personal_plus_checkout_failure(
                work_session,
                work_id=work_id,
                exc=exc,
            )
        except Exception:
            # Preserve the checkout exception so the runner can make its own
            # failure-record attempt with a clean transaction.
            try:
                work_session.rollback()
            except Exception:
                pass

    def run_personal_payment_method_work(
        work_session: Session | None,
        input_json: dict,
    ) -> dict[str, Any]:
        space_id = str(input_json["space_id"])
        run_id = str(input_json.get("_run_id") or "")
        work_id = str(input_json.get("_work_id") or "")
        guard_output, sync_only = acquire_plus_checkout_guard(
            work_session,
            space_id=space_id,
        )
        if guard_output is not None:
            return guard_output
        if sync_only:
            plus_workflow = personal_plus_checkout_workflow(input_json)
            return reconcile_plus_subscription(
                work_session,
                workflow=plus_workflow,
                space_id=space_id,
                work_id=work_id,
                run_id=run_id,
            )
        output = personal_payment_method_workflow(input_json).run(
            space_id=space_id,
            run_id=run_id,
            work_id=work_id,
            payment_card_id=str(input_json.get("payment_card_id") or ""),
        )
        if not bool(input_json.get("auto_start_plus_checkout", True)):
            return output

        plus_workflow = personal_plus_checkout_workflow(input_json)
        try:
            after_bind_success = plus_workflow.run(
                space_id=space_id,
                work_id=f"{work_id}-plus",
                run_id=run_id,
            )
            output["after_bind_success"] = after_bind_success
            for marker_key in (
                "failure_scope",
                "exception_type",
                "attempt_disposition",
                "terminal",
                "error_code",
                "recovery_mode",
                "payment_checkpoint_stage",
            ):
                if marker_key in after_bind_success:
                    output[marker_key] = after_bind_success[marker_key]
        except Exception as exc:
            checkpoint_plus_checkout_failure(
                work_session,
                work_id=work_id,
                exc=exc,
            )
            raise
        return output

    runner.register_work(
        "space.personal_payment_method_bind.space",
        lambda work_session, input_json: run_personal_payment_method_work(
            work_session,
            input_json,
        ),
    )

    def run_personal_plus_checkout_work(
        work_session: Session | None,
        input_json: dict,
    ) -> dict[str, Any]:
        space_id = str(input_json["space_id"])
        work_id = str(input_json.get("_work_id") or "")
        start_new_checkout = (
            str(input_json.get("checkout_attempt_mode") or "").strip().lower() == "new"
        )
        guard_output, sync_only = acquire_plus_checkout_guard(
            work_session,
            space_id=space_id,
            start_new_checkout=start_new_checkout,
        )
        if guard_output is not None:
            return guard_output
        workflow = personal_plus_checkout_workflow(input_json)
        try:
            if sync_only:
                return reconcile_plus_subscription(
                    work_session,
                    workflow=workflow,
                    space_id=space_id,
                    work_id=work_id,
                    run_id=str(input_json.get("_run_id") or ""),
                )
            run_id = str(input_json.get("_run_id") or "")
            bind_output: dict[str, Any] | None = None
            try:
                output = workflow.run(
                    space_id=space_id,
                    work_id=work_id,
                    run_id=run_id,
                )
            except PersonalPlusCheckoutError as exc:
                payment_method_required = (
                    exc.error_code == "plus_checkout_payment_method_required"
                    or str(exc).strip() == "plus_checkout_payment_method_required"
                )
                if not payment_method_required:
                    raise
                bind_input = dict(input_json)
                bind_input["checkout_ui_mode"] = str(
                    getattr(
                        settings,
                        "personal_payment_method_checkout_ui_mode",
                        "custom",
                    )
                    or "custom"
                )
                bind_output = personal_payment_method_workflow(
                    bind_input,
                    require_local_promotion=False,
                ).run(
                    space_id=space_id,
                    work_id=f"{work_id}-bind" if work_id else "",
                    run_id=run_id,
                    payment_card_id=str(input_json.get("payment_card_id") or ""),
                )
                output = workflow.run(
                    space_id=space_id,
                    work_id=work_id,
                    run_id=run_id,
                )
            if bind_output is not None:
                output = {**output, "payment_method_bind": bind_output}
            if start_new_checkout:
                output = {**output, "checkout_attempt_mode": "new"}
                if work_session is not None:
                    output["resolved_markers"] = (
                        resolve_personal_plus_checkout_sync_failures(
                            work_session,
                            space_id=space_id,
                            work_id=work_id,
                        )
                    )
            return output
        except Exception as exc:
            checkpoint_plus_checkout_failure(
                work_session,
                work_id=work_id,
                exc=exc,
            )
            raise

    runner.register_work(
        "space.personal_plus_checkout.space",
        lambda work_session, input_json: run_personal_plus_checkout_work(
            work_session,
            input_json,
        ),
    )

    def run_personal_paypal_link_work(
        work_session: Session | None,
        input_json: dict[str, Any],
    ) -> dict[str, Any]:
        billing_country = str(
            input_json.get("billing_country")
            or settings.personal_paypal_link_billing_country
        ).strip().upper()
        payment_method_type = str(
            input_json.get("payment_method_type") or "paypal"
        ).strip().lower()
        if payment_method_type not in {"paypal", "card", "gcash", "pix"}:
            raise PersonalPayPalLinkError(
                "paypal_link_payment_method_type_invalid",
                "payment_method_type must be paypal, card, gcash, or pix",
                diagnostics={"payment_method_type": payment_method_type},
            )
        if payment_method_type == "gcash":
            billing_country = "PH"
        elif payment_method_type == "pix":
            billing_country = "BR"
        currency = normalize_paypal_link_currency(
            input_json.get("currency"),
            billing_country,
            payment_method_type=payment_method_type,
        )
        checkout_proxy_country = str(
            input_json.get("checkout_proxy_country")
            or input_json.get("proxy_country")
            or settings.personal_paypal_link_proxy_country
        ).strip().upper()
        if payment_method_type == "pix":
            checkout_proxy_country = "BR"
            update_proxy_country = checkout_proxy_country
        else:
            update_proxy_country = str(
                input_json.get("update_proxy_country") or checkout_proxy_country
            ).strip().upper()
        work_id = str(input_json.get("_work_id") or "")
        run_id = str(input_json.get("_run_id") or "")
        space_id = str(input_json["space_id"])
        start_new_checkout = (
            str(input_json.get("checkout_attempt_mode") or "").strip().lower() == "new"
        )
        guard_output, sync_only = acquire_plus_checkout_guard(
            work_session,
            space_id=space_id,
            start_new_checkout=start_new_checkout,
        )
        if guard_output is not None:
            return guard_output
        if sync_only:
            return reconcile_plus_subscription(
                work_session,
                workflow=PersonalPlusCheckoutWorkflow(
                    session_factory=session_factory,
                    checkout_proxy_country=checkout_proxy_country,
                    openai_provider=_openai_plugin(settings),
                ),
                space_id=space_id,
                work_id=work_id,
                run_id=run_id,
            )

        link_workflow = PersonalPayPalLinkWorkflow(
            session_factory=session_factory,
            proxy_country=checkout_proxy_country,
            checkout_proxy_country=checkout_proxy_country,
            update_proxy_country=update_proxy_country,
            billing_country=billing_country,
            currency=currency,
            apply_promotion=bool(input_json.get("apply_promotion", True)),
            promo_campaign_id=str(
                input_json.get("promo_campaign_id")
                or settings.personal_paypal_link_promo_campaign_id
            ),
            checkout_ui_mode=(
                "custom"
                if payment_method_type in {"gcash", "pix"}
                else str(
                    input_json.get("checkout_ui_mode")
                    or settings.personal_paypal_link_ui_mode
                )
            ),
            payment_method_type=payment_method_type,
            browser_headless=bool(input_json.get("browser_headless", True)),
            browser_log_enabled=bool(
                input_json.get(
                    "browser_log_enabled",
                    getattr(settings, "browser_log_enabled", False),
                )
            ),
            browser_log_capture_bodies=bool(
                input_json.get(
                    "browser_log_capture_bodies",
                    getattr(settings, "browser_log_capture_bodies", False),
                )
            ),
            browser_log_max_body_chars=int(
                input_json.get(
                    "browser_log_max_body_chars",
                    getattr(settings, "browser_log_max_body_chars", 20_000),
                )
            ),
            mail_provider=_mail_plugin(settings),
            totp_code_resolver=totp_code_resolver,
        )
        execute_agreement = bool(input_json.get("execute_agreement"))
        if execute_agreement and payment_method_type != "paypal":
            raise PersonalPayPalAgreementError(
                "paypal_agreement_requires_paypal_payment_method",
                "PayPal agreement execution requires payment_method_type=paypal",
            )
        phone_provider: HeroSmsPhoneProviderAdapter | None = None
        agreement_workflow: PersonalPayPalAgreementWorkflow | None = None
        if execute_agreement:
            if not settings.personal_paypal_agreement_enabled:
                raise PersonalPayPalAgreementError(
                    "paypal_agreement_disabled",
                    "PayPal agreement execution is disabled by configuration",
                )
            agreement_country = str(
                input_json.get("agreement_country") or ""
            ).strip().upper()
            agreement_proxy_country = str(
                input_json.get("agreement_proxy_country") or ""
            ).strip().upper()
            if not agreement_country:
                raise PersonalPayPalAgreementError(
                    "paypal_agreement_country_required",
                    "agreement_country is required for PayPal agreement execution",
                    attempt_disposition="release",
                )
            if not agreement_proxy_country:
                raise PersonalPayPalAgreementError(
                    "paypal_agreement_proxy_country_required",
                    "agreement_proxy_country is required for PayPal agreement execution",
                    attempt_disposition="release",
                )
            phone_provider = _personal_paypal_agreement_phone_provider(
                session_factory=session_factory,
                settings=settings,
                input_json=input_json,
                space_id=space_id,
                work_id=work_id,
                run_id=run_id,
            )
            try:
                def persist_payment_checkpoint(stage: str) -> None:
                    if not work_id:
                        raise PersonalPayPalAgreementError(
                            "paypal_agreement_checkpoint_work_id_missing",
                            "PayPal agreement payment checkpoint requires a work id",
                            diagnostics={
                                "stage": "paypal_agreement_checkpoint",
                                "recovery_mode": "subscription_sync_only",
                                "payment_checkpoint_stage": stage,
                            },
                        )
                    with session_factory() as checkpoint_session:
                        persisted = checkpoint_personal_plus_checkout_sync_pending(
                            checkpoint_session,
                            work_id=work_id,
                            stage=stage,
                        )
                    if not persisted:
                        raise PersonalPayPalAgreementError(
                            "paypal_agreement_checkpoint_persist_failed",
                            "PayPal agreement payment checkpoint could not be persisted",
                            diagnostics={
                                "stage": "paypal_agreement_checkpoint",
                                "recovery_mode": "subscription_sync_only",
                                "payment_checkpoint_stage": stage,
                            },
                        )

                agreement_workflow = PersonalPayPalAgreementWorkflow(
                    session_factory=session_factory,
                    phone_provider=phone_provider,
                    card_provider=PayPalAgreementCardPoolProvider(
                        session_factory=session_factory,
                        space_id=space_id,
                    ),
                    address_provider=PayPalAgreementAddressPoolProvider(
                        session_factory=session_factory,
                        country=agreement_country,
                        space_id=space_id,
                    ),
                    name_provider=PayPalAgreementNamePoolProvider(
                        session_factory=session_factory,
                        space_id=space_id,
                    ),
                    country=agreement_country,
                    proxy_country=agreement_proxy_country,
                    buyer_mode=str(
                        input_json.get("agreement_buyer_mode")
                        or settings.personal_paypal_agreement_buyer_mode
                    ),
                    max_card_attempts=int(
                        input_json.get("agreement_max_card_attempts")
                        or settings.personal_paypal_agreement_max_card_attempts
                    ),
                    max_phone_attempts=settings.personal_paypal_agreement_max_phone_attempts,
                    finalize_checkout=bool(
                        input_json.get(
                            "agreement_finalize_checkout",
                            settings.personal_paypal_agreement_finalize_checkout,
                        )
                    ),
                    payment_checkpoint=persist_payment_checkpoint,
                )
            except Exception:
                try:
                    phone_provider.close()
                except Exception:
                    pass
                raise
        try:
            link_result = link_workflow.run(
                space_id=space_id,
                work_id=work_id,
                run_id=run_id,
            )
            if agreement_workflow is None:
                return link_result

            agreement = agreement_workflow.run(
                space_id=space_id,
                link_result=link_result,
                checkout_proxy_country=checkout_proxy_country,
                billing_country=billing_country,
                currency=currency,
                checkout_ui_mode=str(
                    input_json.get("checkout_ui_mode")
                    or settings.personal_paypal_link_ui_mode
                ),
                checkout_proxy=link_workflow.resolved_checkout_proxy,
                work_id=work_id,
                run_id=run_id,
            )
            if agreement.get("status") == "completed":
                subscription_reconciliation = reconcile_plus_subscription(
                    work_session,
                    workflow=PersonalPlusCheckoutWorkflow(
                        session_factory=session_factory,
                        checkout_proxy_country=checkout_proxy_country,
                        openai_provider=_openai_plugin(settings),
                    ),
                    space_id=space_id,
                    work_id=work_id,
                    run_id=run_id,
                    proxy_url_override=(
                        link_workflow.resolved_checkout_proxy.proxy_url
                    ),
                )
                agreement["subscription_reconciliation"] = subscription_reconciliation
            return {
                **sanitize_personal_paypal_agreement_output(link_result),
                "status": agreement["status"],
                "agreement_status": agreement["status"],
                "agreement": agreement,
            }
        except Exception as exc:
            checkpoint_plus_checkout_failure(
                work_session,
                work_id=work_id,
                exc=exc,
            )
            raise
        finally:
            if phone_provider is not None:
                try:
                    phone_provider.close()
                except Exception:
                    pass

    runner.register_work(
        "space.personal_paypal_link.space",
        run_personal_paypal_link_work,
    )
    runner.register_work(
        "space.personal_promotion_check.space",
        lambda _session, input_json: _run_personal_promotion_check_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "space.personal_subscription_refresh.space",
        lambda _session, input_json: _run_personal_subscription_refresh_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "account.backfill_session_rt",
        lambda _session, input_json: {
            "user_account_id": BackfillSessionRtWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
                totp_code_resolver=totp_code_resolver,
                proxy_resolver=backfill_session_proxy_resolver,
                proxy_country=str(input_json.get("proxy_country") or "US").strip().upper(),
                prefer_configured_proxy_country=True,
            ).run(
                user_account_id=str(input_json["user_account_id"]),
                run_id=str(input_json.get("_run_id") or ""),
            )
        },
    )
    runner.register_work(
        "account.backfill_session",
        lambda _session, input_json: {
            "user_account_id": BackfillSessionWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
                totp_code_resolver=totp_code_resolver,
                proxy_resolver=backfill_session_proxy_resolver,
                proxy_country=str(input_json.get("proxy_country") or "US").strip().upper(),
                prefer_configured_proxy_country=True,
            ).run(
                user_account_id=str(input_json["user_account_id"]),
                run_id=str(input_json.get("_run_id") or ""),
            )
        },
    )
    runner.register_work(
        "account.refresh_session_space_detection",
        lambda _session, input_json: BackfillSessionWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
            proxy_resolver=backfill_session_proxy_resolver,
            proxy_country=str(input_json.get("proxy_country") or "US").strip().upper(),
            prefer_configured_proxy_country=True,
        ).refresh_detected_spaces_from_current_session(
            user_account_id=str(input_json["user_account_id"]),
            run_id=str(input_json.get("_run_id") or ""),
        ),
    )
    runner.register_work(
        "account.backfill_rt",
        lambda _session, input_json: {
            "user_account_id": BackfillRtWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
                totp_code_resolver=totp_code_resolver,
                proxy_resolver=backfill_session_proxy_resolver,
                proxy_country=str(input_json.get("proxy_country") or "US").strip().upper(),
                prefer_configured_proxy_country=True,
            ).run(
                user_account_id=str(input_json["user_account_id"]),
                run_id=str(input_json.get("_run_id") or ""),
            )
        },
    )
    runner.register_work(
        "space.personal_codex.authorize.account",
        lambda _session, input_json: _run_personal_codex_authorization_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "account.session_otp.prepare",
        lambda _session, input_json: SpaceSessionOtpWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
        ).run_prepare_work(
            space_id=str(input_json["space_id"]),
            space_membership_id=str(input_json["space_membership_id"]),
            user_account_id=str(input_json["user_account_id"]),
            work_id=str(input_json.get("_work_id") or ""),
            job_id=str(input_json.get("job_id") or ""),
        ),
    )
    runner.register_work(
        "account.session_otp.submit",
        lambda _session, input_json: SpaceSessionOtpWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
        ).run_submit_work(
            space_id=str(input_json["space_id"]),
            space_membership_id=str(input_json["space_membership_id"]),
            user_account_id=str(input_json["user_account_id"]),
            snapshot_id=str(input_json["snapshot_id"]),
            barrier_key=str(input_json["barrier_key"]),
            barrier_expected=int(input_json["barrier_expected"]),
            barrier_timeout_s=float(input_json.get("barrier_timeout_s") or 120),
        ),
    )
    runner.register_work(
        "account.session_otp.remote_submit",
        lambda _session, input_json: _run_remote_session_otp_submit_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "account.protocol_register.one",
        lambda _session, input_json: _run_protocol_registration_work(
            session_factory=session_factory,
            settings=settings,
            input_json=input_json,
        ),
    )
    runner.register_work(
        "account.change_email.one",
        lambda _session, input_json: AccountEmailChangeWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
            openai_provider=_openai_plugin(settings),
            totp_code_resolver=totp_code_resolver,
        ).run(
            AccountEmailChangeInput(
                user_account_id=str(input_json["user_account_id"]),
                old_mail=str(input_json["old_mail"]),
                new_mail=str(input_json.get("new_mail") or ""),
                otp_timeout_s=int(input_json.get("otp_timeout_s") or 180),
                mode=str(input_json.get("mode") or "mapped_csv"),
                mail_provider=str(input_json.get("mail_provider") or "outlook"),
                project_key="",
                caller_id=str(input_json.get("caller_id") or "refactor-app-protocol-registration"),
                email_domain=str(input_json.get("email_domain") or ""),
                source_mailbox_url=str(input_json.get("source_mailbox_url") or ""),
                source_mailbox_client_id=str(input_json.get("source_mailbox_client_id") or ""),
                source_mailbox_refresh_token=str(
                    input_json.get("source_mailbox_refresh_token") or ""
                ),
                source_mailbox_access_token=str(
                    input_json.get("source_mailbox_access_token") or ""
                ),
            ),
            work_id=str(input_json.get("_work_id") or ""),
            run_id=str(input_json.get("_run_id") or ""),
        ),
    )


def _run_space_membership_invite_sync_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    space_limit = max(1, int(input_json.get("space_limit") or 1))
    work_count = max(1, int(input_json.get("work_count") or SPACE_MEMBERSHIP_INVITE_WORK_COUNT))
    barrier_timeout_s = max(
        1.0,
        float(input_json.get("barrier_timeout_s") or SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S),
    )
    workflow_result = SpaceMembershipInviteSyncWorkflow(
        session_factory=session_factory,
        openai_provider=_openai_plugin(settings),
    ).run(
        SpaceMembershipInviteSyncInput(
            space_id=str(input_json.get("space_id") or ""),
            space_limit=space_limit,
            invite_limit_per_space=int(
                input_json.get("invite_limit_per_space") or SPACE_MEMBERSHIP_INVITE_WORK_COUNT
            ),
            work_count=work_count,
            barrier_timeout_s=barrier_timeout_s,
        ),
        job_id=str(input_json.get("_job_id") or ""),
        run_id=str(input_json.get("_run_id") or ""),
    )
    job_id = str(input_json.get("_job_id") or "")
    work_summary = _work_summary(session_factory=session_factory, job_id=job_id)
    output = dict(workflow_result.__dict__)
    output["invited_count"] = int(work_summary["succeeded"])
    output["failed_invite_count"] = int(work_summary["failed"])
    return {
        **output,
        "space_limit": space_limit,
        "space_id": str(input_json.get("space_id") or ""),
        "work_count": work_count,
        **work_summary,
    }


def _run_space_membership_invite_dynamic_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    workflow_result = SpaceDynamicMembershipInviteWorkflow(
        session_factory=session_factory,
        openai_provider=_openai_plugin(settings),
    ).prepare(
        SpaceDynamicMembershipInviteInput(
            space_id=str(input_json.get("space_id") or ""),
        ),
        job_id=str(input_json.get("_job_id") or ""),
        run_id=str(input_json.get("_run_id") or ""),
    )
    work_summary = _work_summary(
        session_factory=session_factory,
        job_id=str(input_json.get("_job_id") or ""),
    )
    return {
        **workflow_result.__dict__,
        "work_count": 1,
        **work_summary,
    }


def _run_space_membership_growth_job(
    *,
    session_factory: SessionFactory,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    with session_factory() as session:
        rows = session.scalars(
            select(WorkItemModel).where(
                WorkItemModel.job_id == job_id,
                WorkItemModel.work_type == "space.membership_growth.invite_batch",
            )
        ).all()
        for row in rows:
            payload = dict(row.input_json or {})
            if run_id and not payload.get("_run_id"):
                payload["_run_id"] = run_id
                row.input_json = payload
                row.updated_at = datetime.now(UTC)
        session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "space_id": str(input_json.get("space_id") or ""),
        "work_count": max(1, int(input_json.get("work_count") or 1)),
        "max_invite_count": int(input_json.get("max_invite_count") or 16),
        "target_member_count": int(input_json.get("target_member_count") or 999),
        **summary,
    }


def _run_space_membership_growth_session_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    user_account_id = str(input_json["user_account_id"])
    try:
        BackfillSessionWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
            totp_code_resolver=_twofauth_otp_resolver(settings),
            proxy_resolver=_backfill_session_proxy_resolver(settings),
        ).run(
            user_account_id=user_account_id,
            run_id=str(input_json.get("_run_id") or ""),
        )
    except Exception as exc:
        return {
            "_work_outcome": "skipped",
            "skip_reason": f"{type(exc).__name__}: {exc}"[:1000],
            "user_account_id": user_account_id,
            "session_succeeded": False,
            "error_type": type(exc).__name__,
            "error_message": str(exc)[:1000],
        }
    return {
        "user_account_id": user_account_id,
        "session_succeeded": True,
    }


def _run_protocol_register_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    count = max(1, int(input_json.get("count") or 1))
    work_count = max(1, int(input_json.get("work_count") or 1))
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    mode = str(input_json.get("mode") or "").strip()
    if mode not in (
        EMAIL_PROTOCOL_NO_PHONE,
        EMAIL_BROWSER_NO_PHONE,
        PHONE_PROTOCOL_BIND_EMAIL,
        PHONE_BROWSER_BIND_EMAIL,
    ):
        raise RuntimeError(f"unsupported registration mode: {mode}")
    proxy_url = str(input_json.get("proxy_url") or "")
    with session_factory() as session:
        queue = WorkQueue(session)
        for index in range(count):
            queue.enqueue(
                job_id=job_id,
                work_type="account.protocol_register.one",
                input_json={
                    **{k: v for k, v in input_json.items() if not k.startswith("_")},
                    "proxy_url": proxy_url,
                    "_run_id": run_id,
                    "registration_index": index,
                },
            )
        session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {"count": count, "work_count": work_count, **summary}


def _run_space_recycle_sweep_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    workflow = SpaceRecycleSweepWorkflow(
        session_factory=session_factory,
        openai_provider=_openai_plugin(settings),
    )
    binding_ids = workflow.select_binding_ids(
        SpaceRecycleSweepInput(limit=int(input_json.get("limit") or 100))
    )
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    with session_factory() as session:
        queue = WorkQueue(session)
        for space_credential_id in binding_ids:
            queue.enqueue(
                job_id=job_id,
                work_type="space.recycle.binding",
                input_json={
                    "space_credential_id": space_credential_id,
                    "_run_id": run_id,
                },
            )
        session.commit()
    work_count = max(1, int(input_json.get("work_count") or 5))
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "selected_count": len(binding_ids),
        "work_count": work_count,
        **summary,
    }


def _run_space_authorization_bulk_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    work_count = max(1, int(input_json.get("work_count") or 1))
    if not job_id:
        return {
            "selected_count": int(input_json.get("selected_count") or 0),
            "work_count": work_count,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        }

    with session_factory() as session:
        rows = session.scalars(
            select(WorkItemModel).where(
                WorkItemModel.job_id == job_id,
            )
        ).all()
        for row in rows:
            payload = dict(row.input_json or {})
            if run_id and not payload.get("_run_id"):
                payload["_run_id"] = run_id
                row.input_json = payload
                row.updated_at = datetime.now(UTC)
        session.commit()

    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "selected_count": int(input_json.get("selected_count") or sum(summary.values())),
        "work_count": work_count,
        **summary,
    }


def _run_space_business_codex_authorization_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    membership_id = str(input_json.get("space_membership_id") or "")
    with session_factory() as session:
        target, skip_reason = resolve_business_codex_authorization_target(
            session=session,
            space_membership_id=membership_id,
        )
    if target is None:
        return {
            "_work_outcome": "skipped",
            "space_membership_id": membership_id,
            "skip_reason": skip_reason,
        }

    if target.codex_select_channel_required:
        fallback_work_id = _enqueue_business_access_token_fallback_work(
            session_factory=session_factory,
            input_json=input_json,
            target=target,
            failure_code="phone_otp_select_channel",
        )
        return {
            "_work_outcome": "skipped",
            "space_membership_id": target.space_membership_id,
            "space_id": target.space_id,
            "user_account_id": target.user_account_id,
            "skip_reason": "phone_otp_select_channel_web_access_token_fallback",
            "fallback_work_id": fallback_work_id,
        }

    try:
        BackfillRtWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
            totp_code_resolver=_twofauth_otp_resolver(settings),
        ).run(
            user_account_id=target.user_account_id,
            run_id=str(input_json.get("_run_id") or ""),
            business_space_id=target.space_id,
            fallback_to_web_access_token_on_phone_gate=True,
        )
    except CodexAuthorizationFallbackRequired as exc:
        fallback_work_id = _enqueue_business_access_token_fallback_work(
            session_factory=session_factory,
            input_json=input_json,
            target=target,
            failure_code=exc.failure_code,
        )
        return {
            "_work_outcome": "skipped",
            "space_membership_id": target.space_membership_id,
            "space_id": target.space_id,
            "user_account_id": target.user_account_id,
            "skip_reason": f"{exc.failure_code}_web_access_token_fallback",
            "fallback_work_id": fallback_work_id,
        }

    with session_factory() as session:
        credential_id = session.scalar(
            select(SpaceCredentialModel.id).where(
                SpaceCredentialModel.space_id == target.space_id,
                SpaceCredentialModel.user_account_id == target.user_account_id,
                SpaceCredentialModel.auth_mode == "codex_oauth",
                SpaceCredentialModel.credential_status == "active",
            )
        )
    if not credential_id:
        raise RuntimeError("business_codex_authorization_did_not_create_active_credential")
    return {
        "space_credential_id": credential_id,
        "space_membership_id": target.space_membership_id,
        "space_id": target.space_id,
        "user_account_id": target.user_account_id,
        "auth_mode": "codex_oauth",
    }


def _enqueue_business_access_token_fallback_work(
    *,
    session_factory: SessionFactory,
    input_json: dict,
    target: BusinessCodexAuthorizationTarget,
    failure_code: str,
) -> str:
    work_id = str(input_json.get("_work_id") or "")
    if not work_id:
        raise RuntimeError("business_codex_fallback_missing_work_id")
    with session_factory() as session:
        source_work = session.get(WorkItemModel, work_id)
        if source_work is None:
            raise RuntimeError("business_codex_fallback_source_work_not_found")
        existing_fallback_work_id = session.scalar(
            select(WorkItemModel)
            .where(
                WorkItemModel.job_id == source_work.job_id,
                WorkItemModel.work_type == "space.business_access_token.create.account",
                WorkItemModel.input_json["space_id"].astext == target.space_id,
                WorkItemModel.input_json["user_account_id"].astext == target.user_account_id,
            )
            .with_only_columns(WorkItemModel.id)
            .limit(1)
        )
        if existing_fallback_work_id:
            return existing_fallback_work_id

        fallback_work = WorkQueue(session).enqueue(
            job_id=source_work.job_id,
            work_type="space.business_access_token.create.account",
            execution_key=f"space-business-at:{target.external_space_id}",
            input_json={
                "space_membership_id": target.space_membership_id,
                "space_id": target.space_id,
                "user_account_id": target.user_account_id,
                "external_space_id": target.external_space_id,
                "session_access_token": "",
                "credential_name": str(
                    input_json.get("credential_name") or f"codex-{target.user_account_id}"
                ),
                "cookie_header": str(input_json.get("cookie_header") or ""),
                "space_name": target.space_name,
                "owner_user_account_id": str(input_json.get("owner_user_account_id") or ""),
                "source_admin_session_id": str(input_json.get("source_admin_session_id") or ""),
                "proxy_bind_reason": "space_business_access_token_oauth_fallback",
                "startup_sleep_s": BUSINESS_ACCESS_TOKEN_MIN_INTERVAL_S,
                "oauth_fallback_reason": failure_code,
                "_run_id": str(input_json.get("_run_id") or ""),
            },
        )
        session.commit()
        return fallback_work.id


def _run_space_seat_expand_job(
    *,
    session_factory: SessionFactory,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    work_count = max(1, int(input_json.get("work_count") or 1))
    with session_factory() as session:
        rows = session.scalars(
            select(WorkItemModel).where(
                WorkItemModel.job_id == job_id,
                WorkItemModel.work_type == "space.seat_expand.one",
            )
        ).all()
        for row in rows:
            payload = dict(row.input_json or {})
            if run_id and not payload.get("_run_id"):
                payload["_run_id"] = run_id
                row.input_json = payload
                row.updated_at = datetime.now(UTC)
        session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "selected_count": int(input_json.get("selected_count") or sum(summary.values())),
        "work_count": work_count,
        "target_seats": 999,
        "max_no_progress_count": 10,
        "max_http_failure_count": 10,
        **summary,
    }


def _run_space_business_access_token_account_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    with session_factory() as session:
        space = session.get(SpaceModel, str(input_json.get("space_id") or ""))
        if space is None or space.space_status != "active":
            return {
                "space_credential_id": "",
                "skipped_reason": "space_not_active",
            }
    proxy_url = str(input_json.get("proxy_url") or "")
    if not proxy_url:
        proxy_url = ensure_account_proxy_url(
            session_factory,
            str(input_json["user_account_id"]),
            bind_reason=str(
                input_json.get("proxy_bind_reason") or "space_business_access_token_create"
            ),
        )
    external_space_id = str(input_json["external_space_id"])
    initial_sleep_s = max(0.0, float(input_json.get("startup_sleep_s") or 10.0))

    def create_credential() -> str:
        return CreateBusinessAccessTokenCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_plugin(settings),
        ).run(
            CreateBusinessAccessTokenCredentialInput(
                user_account_id=str(input_json["user_account_id"]),
                external_space_id=external_space_id,
                session_access_token=str(input_json.get("session_access_token") or ""),
                credential_name=str(input_json["credential_name"]),
                cookie_header=str(input_json.get("cookie_header") or ""),
                space_name=str(input_json.get("space_name") or ""),
                owner_user_account_id=str(input_json.get("owner_user_account_id") or ""),
                source_admin_session_id=str(input_json.get("source_admin_session_id") or ""),
                proxy_url=proxy_url,
            )
        )

    return {
        "space_credential_id": run_business_access_token_rate_limited(
            external_space_id=external_space_id,
            initial_sleep_s=initial_sleep_s,
            callback=create_credential,
        )
    }


def _run_space_auto_replenish_tick_job(
    *,
    session_factory: SessionFactory,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    requested_space_id = str(input_json.get("space_id") or "").strip()
    work_count = max(1, int(input_json.get("work_count") or 20))
    with session_factory() as session:
        existing_count = int(
            session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_type == "space.auto_replenish.space",
                )
            )
            or 0
        )
        if existing_count == 0:
            stmt = select(SpaceModel).where(
                SpaceModel.space_type == "business",
                SpaceModel.space_status == "active",
                SpaceModel.auto_replenish_enabled.is_(True),
            )
            if requested_space_id:
                stmt = stmt.where(SpaceModel.id == requested_space_id)
            spaces = session.scalars(stmt.order_by(SpaceModel.created_at.asc())).all()
            queue = WorkQueue(session)
            for space in spaces:
                queue.enqueue(
                    job_id=job_id,
                    work_type="space.auto_replenish.space",
                    execution_key=f"space-auto-replenish:{space.id}",
                    input_json={"space_id": space.id, "_run_id": run_id},
                )
            session.commit()
        else:
            spaces = []
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "selected_count": existing_count or len(spaces),
        "work_count": work_count,
        **summary,
    }


def _run_space_auto_replenish_invite_job(
    *,
    session_factory: SessionFactory,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    with session_factory() as session:
        existing_count = int(
            session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_type == "space.auto_replenish.invite.prepare_space",
                )
            )
            or 0
        )
        if existing_count == 0:
            WorkQueue(session).enqueue(
                job_id=job_id,
                work_type="space.auto_replenish.invite.prepare_space",
                execution_key=f"space-auto-replenish-invite:{input_json['space_id']}",
                input_json={
                    "space_id": str(input_json["space_id"]),
                    "invite_count": int(input_json.get("invite_count") or MAX_INVITE_BATCH_SIZE),
                    "_run_id": run_id,
                },
            )
            session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {"selected_count": 1, "work_count": 1, **summary}


def _run_personal_payment_method_bind_tick_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    requested_space_id = str(input_json.get("space_id") or "").strip()
    limit = max(1, int(input_json.get("limit") or 10))
    work_count = max(1, int(input_json.get("work_count") or 1))
    auto_start_plus_checkout = bool(input_json.get("auto_start_plus_checkout", True))
    proxy_country = str(
        input_json.get("proxy_country")
        or settings.personal_plus_checkout_create_proxy_country
        or "US"
    ).strip().upper()
    checkout_ui_mode = str(
        input_json.get("checkout_ui_mode")
        or getattr(settings, "personal_payment_method_checkout_ui_mode", "custom")
        or "custom"
    ).strip().lower()
    browser_headless = bool(input_json.get("browser_headless", True))
    browser_log_enabled = bool(
        input_json.get(
            "browser_log_enabled",
            getattr(settings, "browser_log_enabled", False),
        )
    )
    browser_log_capture_bodies = bool(
        input_json.get(
            "browser_log_capture_bodies",
            getattr(settings, "browser_log_capture_bodies", False),
        )
    )
    browser_log_max_body_chars = int(
        input_json.get(
            "browser_log_max_body_chars",
            getattr(settings, "browser_log_max_body_chars", 20_000),
        )
    )
    captcha_api_url = str(
        input_json.get("captcha_api_url")
        or getattr(settings, "personal_plus_checkout_captcha_api_url", "")
        or ""
    ).strip()
    captcha_client_key = str(
        input_json.get("captcha_client_key")
        or getattr(settings, "personal_plus_checkout_captcha_client_key", "")
        or ""
    ).strip()
    payment_card_id = str(input_json.get("payment_card_id") or "").strip()
    with session_factory() as session:
        now = datetime.now(UTC)
        existing_count = int(
            session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_type == "space.personal_payment_method_bind.space",
                )
            )
            or 0
        )
        selected: list[SpaceModel] = []
        if existing_count == 0:
            stmt = (
                select(SpaceModel)
                .join(
                    UserAccountModel,
                    UserAccountModel.id == SpaceModel.owner_user_account_id,
                )
                .where(
                    SpaceModel.provider == "openai_chatgpt",
                    SpaceModel.space_type == "personal",
                    SpaceModel.space_status == "active",
                    SpaceModel.has_promotion.is_(True),
                    SpaceModel.promotion_id != "",
                    SpaceModel.has_payment_method.is_(False),
                    SpaceModel.payment_method_status != "bound",
                    SpaceModel.payment_method_status != "binding",
                    or_(
                        SpaceModel.payment_method_attempt_count < 3,
                        (
                            SpaceModel.payment_method_cooldown_until.is_not(None)
                            & (SpaceModel.payment_method_cooldown_until <= now)
                        ),
                    ),
                    UserAccountModel.account_status == "active",
                )
                .order_by(
                    SpaceModel.payment_method_attempt_count.asc(),
                    SpaceModel.updated_at.asc(),
                    SpaceModel.id.asc(),
                )
            )
            if requested_space_id:
                stmt = stmt.where(SpaceModel.id == requested_space_id)
            selected = session.scalars(stmt.limit(limit)).all()
            queue = WorkQueue(session)
            for space in selected:
                work_input = {
                    "space_id": space.id,
                    "proxy_country": proxy_country,
                    "auto_start_plus_checkout": auto_start_plus_checkout,
                    "browser_headless": browser_headless,
                    "captcha_api_url": captcha_api_url,
                    "captcha_client_key": captcha_client_key,
                    "_run_id": run_id,
                }
                if checkout_ui_mode:
                    work_input["checkout_ui_mode"] = checkout_ui_mode
                if payment_card_id:
                    work_input["payment_card_id"] = payment_card_id
                queue.enqueue(
                    job_id=job_id,
                    work_type="space.personal_payment_method_bind.space",
                    execution_key=f"personal-payment-method:{space.id}",
                    input_json=work_input,
                )
            session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    result = {
        "space_id": requested_space_id,
        "selected_count": existing_count or len(selected),
        "limit": limit,
        "work_count": work_count,
        "proxy_country": proxy_country,
        "auto_start_plus_checkout": auto_start_plus_checkout,
        "browser_headless": browser_headless,
        **summary,
    }
    if checkout_ui_mode:
        result["checkout_ui_mode"] = checkout_ui_mode
    return result


def _run_personal_plus_checkout_tick_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    requested_space_id = str(input_json.get("space_id") or "").strip()
    requested_space_ids = [
        str(item).strip()
        for item in input_json.get("space_ids") or []
        if str(item).strip()
    ]
    limit = max(1, int(input_json.get("limit") or 10))
    work_count = max(1, int(input_json.get("work_count") or 1))
    checkout_proxy_country = str(
        input_json.get("checkout_proxy_country")
        or input_json.get("proxy_country")
        or input_json.get("create_proxy_country")
        or settings.personal_plus_checkout_create_proxy_country
    ).strip().upper()
    update_proxy_country = str(
        input_json.get("update_proxy_country")
        or input_json.get("promo_proxy_country")
        or checkout_proxy_country
    ).strip().upper()
    if update_proxy_country != checkout_proxy_country:
        raise PersonalPlusCheckoutError(
            "plus_checkout_proxy_country_mismatch",
            error_code="plus_checkout_proxy_country_mismatch",
            diagnostics={
                "checkout_proxy_country": checkout_proxy_country,
                "update_proxy_country": update_proxy_country,
            },
        )
    promo_campaign_id = str(
        input_json.get("promo_campaign_id")
        or settings.personal_plus_checkout_promo_campaign_id
    ).strip()
    checkout_ui_mode = str(
        input_json.get("checkout_ui_mode")
        or getattr(settings, "personal_plus_checkout_ui_mode", "hosted")
        or "hosted"
    ).strip().lower()
    browser_headless = bool(input_json.get("browser_headless", True))
    checkout_attempt_mode = str(input_json.get("checkout_attempt_mode") or "").strip().lower()
    captcha_api_url = str(
        input_json.get("captcha_api_url")
        or getattr(settings, "personal_plus_checkout_captcha_api_url", "")
        or ""
    ).strip()
    captcha_client_key = str(
        input_json.get("captcha_client_key")
        or getattr(settings, "personal_plus_checkout_captcha_client_key", "")
        or ""
    ).strip()
    with session_factory() as session:
        existing_count = int(
            session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_type == "space.personal_plus_checkout.space",
                )
            )
            or 0
        )
        selected: list[SpaceModel] = []
        if existing_count == 0:
            stmt = (
                select(SpaceModel)
                .join(UserAccountModel, UserAccountModel.id == SpaceModel.owner_user_account_id)
                .where(
                    SpaceModel.provider == "openai_chatgpt",
                    SpaceModel.space_type == "personal",
                    SpaceModel.space_status == "active",
                    UserAccountModel.account_status == "active",
                    or_(
                        UserAccountModel.access_token != "",
                        (
                            (UserAccountModel.cookie_header != "")
                            & (UserAccountModel.auth_cookie_header != "")
                        ),
                    ),
                    or_(
                        func.lower(func.coalesce(SpaceModel.plan_type, "")).notin_(
                            ("plus", "chatgptplusplan")
                        ),
                        personal_plus_checkout_sync_failure_exists_for(SpaceModel.id),
                    ),
                    or_(
                        ~personal_plus_checkout_consume_stop_exists_for(SpaceModel.id),
                        personal_plus_checkout_sync_failure_exists_for(SpaceModel.id),
                    ),
                )
                .order_by(SpaceModel.updated_at.asc(), SpaceModel.id.asc())
            )
            if requested_space_id:
                stmt = stmt.where(SpaceModel.id == requested_space_id)
            elif requested_space_ids:
                stmt = stmt.where(SpaceModel.id.in_(requested_space_ids))
            selected = session.scalars(stmt.limit(limit)).all()
            queue = WorkQueue(session)
            for space in selected:
                queue.enqueue(
                    job_id=job_id,
                    work_type="space.personal_plus_checkout.space",
                    execution_key=f"personal-plus-checkout:{space.id}",
                    input_json={
                        "space_id": space.id,
                        "checkout_attempt_mode": checkout_attempt_mode,
                        "proxy_country": checkout_proxy_country,
                        "checkout_proxy_country": checkout_proxy_country,
                        "update_proxy_country": update_proxy_country,
                        "promo_campaign_id": promo_campaign_id,
                        "browser_headless": browser_headless,
                        "browser_log_enabled": browser_log_enabled,
                        "browser_log_capture_bodies": browser_log_capture_bodies,
                        "browser_log_max_body_chars": browser_log_max_body_chars,
                        "captcha_api_url": captcha_api_url,
                        "captcha_client_key": captcha_client_key,
                        "_run_id": run_id,
                        **(
                            {"checkout_ui_mode": checkout_ui_mode}
                            if checkout_ui_mode
                            else {}
                        ),
                    },
                )
            session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    result = {
        "space_id": requested_space_id,
        "selected_count": existing_count or len(selected),
        "limit": limit,
        "work_count": work_count,
        "checkout_attempt_mode": checkout_attempt_mode,
        "proxy_country": checkout_proxy_country,
        "checkout_proxy_country": checkout_proxy_country,
        "update_proxy_country": update_proxy_country,
        "promo_campaign_id": promo_campaign_id,
        **summary,
    }
    if checkout_ui_mode:
        result["checkout_ui_mode"] = checkout_ui_mode
    return result


def _run_personal_paypal_link_tick_job(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    requested_space_id = str(input_json.get("space_id") or "").strip()
    payment_method_type = str(
        input_json.get("payment_method_type") or "paypal"
    ).strip().lower()
    if payment_method_type not in {"paypal", "card", "gcash", "pix"}:
        raise ValueError("payment_method_type must be paypal, card, gcash, or pix")
    checkout_proxy_country = str(
        input_json.get("checkout_proxy_country")
        or input_json.get("proxy_country")
        or settings.personal_paypal_link_proxy_country
    ).strip().upper()
    update_proxy_country = str(
        input_json.get("update_proxy_country") or checkout_proxy_country
    ).strip().upper()
    if payment_method_type == "pix":
        checkout_proxy_country = "BR"
        update_proxy_country = checkout_proxy_country
    if payment_method_type != "pix" and update_proxy_country != checkout_proxy_country:
        raise ValueError("update proxy country must match checkout/provider proxy country")
    proxy_country = checkout_proxy_country
    billing_country = str(
        input_json.get("billing_country")
        or settings.personal_paypal_link_billing_country
    ).strip().upper()
    if payment_method_type == "gcash":
        billing_country = "PH"
    elif payment_method_type == "pix":
        billing_country = "BR"
    currency = normalize_paypal_link_currency(
        input_json.get("currency"),
        billing_country,
        payment_method_type=payment_method_type,
    )
    apply_promotion = bool(input_json.get("apply_promotion", True))
    promo_campaign_id = str(
        input_json.get("promo_campaign_id")
        or settings.personal_paypal_link_promo_campaign_id
    ).strip()
    checkout_ui_mode = str(
        input_json.get("checkout_ui_mode") or settings.personal_paypal_link_ui_mode
    ).strip().lower()
    if payment_method_type in {"gcash", "pix"}:
        checkout_ui_mode = "custom"
    checkout_attempt_mode = str(input_json.get("checkout_attempt_mode") or "").strip().lower()
    browser_headless = bool(input_json.get("browser_headless", True))
    browser_log_enabled = bool(
        input_json.get(
            "browser_log_enabled",
            getattr(settings, "browser_log_enabled", False),
        )
    )
    browser_log_capture_bodies = bool(
        input_json.get(
            "browser_log_capture_bodies",
            getattr(settings, "browser_log_capture_bodies", False),
        )
    )
    browser_log_max_body_chars = int(
        input_json.get(
            "browser_log_max_body_chars",
            getattr(settings, "browser_log_max_body_chars", 20_000),
        )
    )
    agreement_input = {
        "execute_agreement": bool(input_json.get("execute_agreement")),
        "agreement_country": input_json.get("agreement_country"),
        "agreement_proxy_country": input_json.get("agreement_proxy_country"),
        "agreement_buyer_mode": str(
            input_json.get("agreement_buyer_mode")
            or settings.personal_paypal_agreement_buyer_mode
        ),
        "agreement_sms_country": str(input_json.get("agreement_sms_country") or ""),
        "agreement_max_card_attempts": int(
            input_json.get("agreement_max_card_attempts")
            or settings.personal_paypal_agreement_max_card_attempts
        ),
        "agreement_finalize_checkout": bool(
            input_json.get(
                "agreement_finalize_checkout",
                settings.personal_paypal_agreement_finalize_checkout,
            )
        ),
    }
    with session_factory() as session:
        existing_count = int(
            session.scalar(
                select(func.count())
                .select_from(WorkItemModel)
                .where(
                    WorkItemModel.job_id == job_id,
                    WorkItemModel.work_type == "space.personal_paypal_link.space",
                )
            )
            or 0
        )
        selected_count = existing_count
        if existing_count == 0 and requested_space_id:
            space = session.scalar(
                select(SpaceModel)
                .join(UserAccountModel, UserAccountModel.id == SpaceModel.owner_user_account_id)
                .where(
                    SpaceModel.id == requested_space_id,
                    SpaceModel.provider == "openai_chatgpt",
                    SpaceModel.space_type == "personal",
                    SpaceModel.space_status == "active",
                    UserAccountModel.account_status == "active",
                    UserAccountModel.access_token != "",
                )
            )
            if space is not None:
                WorkQueue(session).enqueue(
                    job_id=job_id,
                    work_type="space.personal_paypal_link.space",
                    execution_key=f"personal-paypal-link:{space.id}",
                    input_json={
                        "space_id": space.id,
                        "proxy_country": proxy_country,
                        "checkout_proxy_country": checkout_proxy_country,
                        "update_proxy_country": update_proxy_country,
                        "billing_country": billing_country,
                        "currency": currency,
                        "apply_promotion": apply_promotion,
                        "promo_campaign_id": promo_campaign_id,
                        "checkout_ui_mode": checkout_ui_mode,
                        "payment_method_type": payment_method_type,
                        "checkout_attempt_mode": checkout_attempt_mode,
                        "browser_headless": browser_headless,
                        "browser_log_enabled": browser_log_enabled,
                        "browser_log_capture_bodies": browser_log_capture_bodies,
                        "browser_log_max_body_chars": browser_log_max_body_chars,
                        **agreement_input,
                        "_run_id": run_id,
                    },
                )
                selected_count = 1
                session.commit()
    return {
        "space_id": requested_space_id,
        "selected_count": selected_count,
        "limit": 1,
        "work_count": 1,
        "proxy_country": proxy_country,
        "checkout_proxy_country": checkout_proxy_country,
        "update_proxy_country": update_proxy_country,
        "billing_country": billing_country,
        "currency": currency,
        "apply_promotion": apply_promotion,
        "promo_campaign_id": promo_campaign_id,
        "checkout_ui_mode": checkout_ui_mode,
        "payment_method_type": payment_method_type,
        "checkout_attempt_mode": checkout_attempt_mode,
        "browser_headless": browser_headless,
        "browser_log_enabled": browser_log_enabled,
        "browser_log_capture_bodies": browser_log_capture_bodies,
        "browser_log_max_body_chars": browser_log_max_body_chars,
        **agreement_input,
        **_work_summary(session_factory=session_factory, job_id=job_id),
    }


def _space_auto_replenish_workflow(
    *,
    session_factory: SessionFactory,
    settings: Settings,
) -> SpaceAutoReplenishWorkflow:
    return SpaceAutoReplenishWorkflow(
        session_factory=session_factory,
        mail_provider=_mail_plugin(settings),
        openai_provider=_openai_plugin(settings),
        invite_executor_base_url=settings.session_otp_executor_base_url,
        invite_executor_api_key=settings.session_otp_executor_api_key,
        registration_proxy_country=settings.protocol_register_proxy_country,
        browser_log_enabled=bool(getattr(settings, "browser_log_enabled", False)),
        browser_log_capture_bodies=bool(
            getattr(settings, "browser_log_capture_bodies", False)
        ),
        browser_log_max_body_chars=int(
            getattr(settings, "browser_log_max_body_chars", 20_000)
        ),
        totp_code_resolver=_twofauth_otp_resolver(settings),
    )


def _run_remote_session_otp_submit_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    if not settings.session_otp_executor_base_url.strip():
        raise RemoteSessionOtpBridgeError("INVITE_EXECUTOR_BASE_URL is not configured")
    if not settings.session_otp_executor_api_key.strip():
        raise RemoteSessionOtpBridgeError("INVITE_EXECUTOR_API_KEY is not configured")

    run_id = str(input_json.get("_run_id") or "")

    def on_submitted(batch_id: str, submitted_count: int) -> None:
        if not run_id:
            return
        with session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type="session_otp.remote_batch_submitted",
                message="remote session OTP batch submitted",
                data_json={
                    "batch_id": batch_id,
                    "submitted_count": submitted_count,
                    "space_id": str(input_json.get("space_id") or ""),
                    "space_ids": list(input_json.get("space_ids") or []),
                },
            )
            session.commit()

    with SessionOtpExecutorClient(
        base_url=settings.session_otp_executor_base_url,
        api_key=settings.session_otp_executor_api_key,
    ) as client:
        result = run_remote_space_session_otp_submit(
            session_factory=session_factory,
            space_id=str(input_json.get("space_id") or ""),
            space_ids=list(input_json.get("space_ids") or []),
            user_account_ids=list(input_json.get("user_account_ids") or []),
            client=client,
            poll_interval_s=max(0.1, float(input_json.get("poll_interval_s") or 0.5)),
            poll_timeout_s=max(1.0, float(input_json.get("poll_timeout_s") or 900.0)),
            barrier_timeout_s=max(1.0, float(input_json.get("barrier_timeout_s") or 120.0)),
            on_submitted=on_submitted,
        )
    status = str(result.get("status") or "")
    if status == "no_candidates":
        return {
            **result,
            "_work_outcome": "skipped",
            "skip_reason": "space has no otp_collected snapshots when Work started",
        }
    if status != "succeeded":
        raise RemoteSessionOtpBridgeError(
            "remote session OTP submit incomplete: "
            f"status={status or '(empty)'} batch_id={result.get('batch_id') or ''} "
            f"succeeded={result.get('succeeded_count') or 0} "
            f"failed={result.get('failed_count') or 0} stale={result.get('stale_count') or 0}"
        )
    return result


def _run_personal_codex_credential_heartbeat_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    # Cliproxy is the default for heartbeat runs; proxyserver remains available
    # only when an older or explicitly overridden job requests it.
    proxy_mode = str(input_json.get("proxy_mode") or "cliproxy").strip().lower()
    proxy_country = str(input_json.get("proxy_country") or "US").strip().upper()
    resolved_proxy_urls: dict[str, str] = {}

    def resolve_proxy(user_account_id: str) -> str:
        if user_account_id in resolved_proxy_urls:
            return resolved_proxy_urls[user_account_id]
        if proxy_mode == "cliproxy":
            with session_factory() as session:
                account = session.get(UserAccountModel, user_account_id)
                if account is None:
                    raise RuntimeError(f"user account not found: {user_account_id}")
                email = account.email
            proxy_url = resolve_cliproxy_proxy(
                email=email,
                country_code=proxy_country,
            ).proxy_url
        else:
            proxy_url = ensure_account_proxy_url(
                session_factory,
                user_account_id,
                bind_reason="space_personal_codex_credential_heartbeat",
            )
        resolved_proxy_urls[user_account_id] = proxy_url
        return proxy_url

    def reauthorize(space_membership_id: str) -> dict:
        with session_factory() as session:
            membership = session.get(SpaceMembershipModel, space_membership_id)
            if membership is None:
                raise RuntimeError(f"space membership not found: {space_membership_id}")
            proxy_url = resolve_proxy(membership.user_account_id)
        result = _run_personal_codex_authorization_work(
            session_factory=session_factory,
            settings=settings,
            input_json={
                **input_json,
                "space_membership_id": space_membership_id,
                "proxy_url_override": proxy_url,
            },
        )
        if result.get("_work_outcome") == "skipped":
            reason = str(
                result.get("skip_reason")
                or result.get("skipped_reason")
                or "personal_codex_reauthorization_skipped"
            )
            raise RuntimeError(reason)
        return result

    def repush(space_credential_id: str, downstream_channel_id: str) -> str:
        return SpaceDirectPushWorkflow(
            session_factory=session_factory,
            downstream_provider=_downstream_plugin_from_channel_id(
                session_factory,
                downstream_channel_id,
            ),
        ).run(
            SpaceDirectPushInput(
                space_credential_id=space_credential_id,
                downstream_channel_id=downstream_channel_id,
                is_retry=True,
            )
        )

    return PersonalCodexCredentialHeartbeatWorkflow(
        session_factory=session_factory,
        openai_provider=_openai_plugin(settings),
        proxy_resolver=resolve_proxy,
        reauthorize=reauthorize,
        repush=repush,
    ).run(
        PersonalCodexCredentialHeartbeatInput(
            space_credential_id=str(input_json["space_credential_id"]),
        )
    )


def _run_personal_codex_authorization_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    membership_id = str(input_json.get("space_membership_id") or "")
    with session_factory() as session:
        target, skip_reason = resolve_personal_codex_authorization_target(
            session=session,
            space_membership_id=membership_id,
        )
    if target is None:
        return {
            "_work_outcome": "skipped",
            "space_membership_id": membership_id,
            "skipped_reason": skip_reason,
        }

    run_id = str(input_json.get("_run_id") or "")
    phone_provider = _personal_codex_grizzly_phone_provider(
        session_factory=session_factory,
        settings=settings,
        input_json=input_json,
        run_id=run_id,
    )
    BackfillRtWorkflow(
        session_factory=session_factory,
        mail_provider=_mail_plugin(settings),
        phone_provider=phone_provider,
        totp_code_resolver=_twofauth_otp_resolver(settings),
    ).run(
        user_account_id=target.user_account_id,
        run_id=run_id,
        personal_space_id=target.space_id,
        force_clean_browser_login=bool(input_json.get("force_clean_browser_login")),
        proxy_url_override=str(input_json.get("proxy_url_override") or ""),
    )
    with session_factory() as session:
        credential_id = session.scalar(
            select(SpaceCredentialModel.id).where(
                SpaceCredentialModel.space_id == target.space_id,
                SpaceCredentialModel.user_account_id == target.user_account_id,
                SpaceCredentialModel.credential_status == "active",
            )
        )
    if not credential_id:
        raise RuntimeError("personal_codex_authorization_did_not_create_active_credential")
    return {
        "space_credential_id": credential_id,
        "space_membership_id": target.space_membership_id,
        "space_id": target.space_id,
        "user_account_id": target.user_account_id,
    }


def _run_personal_subscription_refresh_selected_job(
    *,
    session_factory: SessionFactory,
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "").strip()
    work_count = max(1, int(input_json.get("work_count") or 1))
    if not job_id:
        summary = {
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        }
    else:
        summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "selected_count": int(input_json.get("selected_count") or sum(summary.values())),
        "work_count": work_count,
        **summary,
    }


def _run_personal_subscription_refresh_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    space_id = str(input_json.get("space_id") or "").strip()
    with session_factory() as session:
        space = session.get(SpaceModel, space_id)
        if space is None:
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "skip_reason": "space_not_found",
            }
        if (
            space.provider != "openai_chatgpt"
            or space.space_type != "personal"
            or space.space_status != "active"
        ):
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "skip_reason": "personal_subscription_refresh_space_not_eligible",
            }
        account = session.get(UserAccountModel, space.owner_user_account_id)
        if account is None or account.account_status != "active":
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "user_account_id": space.owner_user_account_id,
                "skip_reason": "personal_subscription_refresh_owner_account_not_active",
            }
        access_token = str(account.access_token or "").strip()
        cookie_header = str(account.cookie_header or "").strip() or str(
            account.auth_cookie_header or ""
        ).strip()
        email = str(account.email or "").strip()
        external_space_id = str(space.external_space_id or "").strip()
        user_account_id = account.id
        if not access_token:
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "user_account_id": user_account_id,
                "skip_reason": "personal_subscription_refresh_access_token_missing",
            }
        if not email:
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "user_account_id": user_account_id,
                "skip_reason": "personal_subscription_refresh_owner_email_missing",
            }
        if not external_space_id:
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "user_account_id": user_account_id,
                "skip_reason": "personal_subscription_refresh_external_space_id_missing",
            }

    proxy = resolve_cliproxy_proxy(email=email, country_code="US")
    try:
        subscription = _openai_plugin(settings).fetch_subscription(
            access_token=access_token,
            account_id=external_space_id,
            cookie_header=cookie_header,
            proxy_url=proxy.proxy_url,
        )
    except Exception as exc:
        if _openai_backend_http_status(exc) != 404:
            raise
        return {
            "status": "succeeded",
            "space_id": space_id,
            "user_account_id": user_account_id,
            "external_space_id": external_space_id,
            "subscription_status": "no_subscription",
            "http_status": 404,
            **_cliproxy_output(proxy),
        }
    if not isinstance(subscription, dict):
        raise OpenAIChatGPTClientError("subscription response must be a JSON object")

    now = datetime.now(UTC)
    with session_factory() as session:
        space = session.get(SpaceModel, space_id)
        if space is None:
            raise RuntimeError(f"personal subscription refresh space disappeared: {space_id}")
        _write_personal_subscription_snapshot(
            space=space,
            subscription=subscription,
            now=now,
        )
        session.commit()
        plan_type = str(space.plan_type or "")
        seats_entitled = int(space.seats_entitled or 0)
        seats_in_use = int(space.seats_in_use or 0)

    return {
        "status": "succeeded",
        "space_id": space_id,
        "user_account_id": user_account_id,
        "external_space_id": external_space_id,
        "subscription_status": "refreshed",
        "plan_type": plan_type,
        "seats_entitled": seats_entitled,
        "seats_in_use": seats_in_use,
        **_cliproxy_output(proxy),
    }


def _write_personal_subscription_snapshot(
    *,
    space: SpaceModel,
    subscription: dict,
    now: datetime,
) -> None:
    seats_entitled = _optional_subscription_int(
        subscription,
        "seats_entitled",
        "seatsEntitled",
    )
    seats_in_use = _optional_subscription_int(
        subscription,
        "seats_in_use",
        "seatsInUse",
    )
    if seats_entitled is not None:
        space.seats_entitled = seats_entitled
        space.seat_limit = seats_entitled
    if seats_in_use is not None:
        space.seats_in_use = seats_in_use
    plan_type = str(
        subscription.get("plan_type") or subscription.get("planType") or ""
    ).strip()
    if plan_type:
        space.plan_type = plan_type
    space.raw_space_json = dict(subscription)
    space.last_subscription_sync_at = now
    space.updated_at = now


def _optional_subscription_int(payload: dict, *keys: str) -> int | None:
    for key in keys:
        if key not in payload or payload[key] is None or isinstance(payload[key], bool):
            continue
        try:
            value = int(payload[key])
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _openai_backend_http_status(exc: Exception) -> int:
    status = getattr(exc, "http_status", None)
    try:
        if status is not None:
            return int(status)
    except (TypeError, ValueError):
        pass
    marker = "http_status="
    message = str(exc)
    marker_index = message.find(marker)
    if marker_index < 0:
        return 0
    digits = []
    for char in message[marker_index + len(marker) :]:
        if not char.isdigit():
            break
        digits.append(char)
    return int("".join(digits)) if digits else 0


def _cliproxy_output(proxy: Any) -> dict[str, Any]:
    return {
        "proxy_provider": str(getattr(proxy, "provider", "cliproxy") or "cliproxy"),
        "proxy_country": str(getattr(proxy, "country_code", "US") or "US"),
        "proxy_sid_source": str(getattr(proxy, "sid_source", "") or ""),
        "proxy_probe_attempts": int(getattr(proxy, "probe_attempts", 0) or 0),
    }


def _run_personal_promotion_check_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    space_id = str(input_json.get("space_id") or "").strip()
    proxy_country = str(input_json.get("proxy_country") or "JP").strip().upper()
    with session_factory() as session:
        space = session.get(SpaceModel, space_id)
        if space is None:
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "skipped_reason": "space_not_found",
            }
        if (
            space.provider != "openai_chatgpt"
            or space.space_type != "personal"
            or space.space_status != "active"
        ):
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "skipped_reason": "personal_promotion_check_space_not_eligible",
            }
        account = session.get(UserAccountModel, space.owner_user_account_id)
        if account is None or account.account_status != "active":
            return {
                "_work_outcome": "skipped",
                "space_id": space_id,
                "user_account_id": space.owner_user_account_id,
                "skipped_reason": "personal_promotion_check_owner_account_not_active",
            }
        user_account_id = account.id
        email = account.email

    proxy = resolve_cliproxy_proxy(
        email=email,
        country_code=proxy_country,
    )
    result = BackfillSessionWorkflow(
        session_factory=session_factory,
        mail_provider=_mail_plugin(settings),
    ).probe_personal_space_promotion(
        user_account_id=user_account_id,
        proxy_url=proxy.proxy_url,
        proxy_country=proxy.country_code,
        space_id=space_id,
        run_id=str(input_json.get("_run_id") or ""),
    )
    return {
        **result,
        "space_id": space_id,
        "user_account_id": user_account_id,
        "proxy_provider": proxy.provider,
        "proxy_country": proxy.country_code,
        "proxy_sid_source": proxy.sid_source,
        "proxy_probe_attempts": proxy.probe_attempts,
    }


def _personal_paypal_agreement_phone_provider(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict[str, Any],
    space_id: str,
    work_id: str,
    run_id: str,
) -> HeroSmsLongTermPhoneProviderAdapter:
    api_key = str(getattr(settings, "hero_sms_api_key", "") or "").strip()
    if not api_key:
        raise PersonalPayPalAgreementError(
            "paypal_agreement_sms_api_key_missing",
            "HERO_SMS_API_KEY is required for PayPal agreement execution",
        )
    agreement_country = str(
        input_json.get("agreement_country")
        or getattr(settings, "personal_paypal_agreement_country", "US")
        or "US"
    ).strip().upper()
    if agreement_country != "US":
        raise PersonalPayPalAgreementError(
            "paypal_agreement_hero_country_mismatch",
            "The configured one-day Hero phone is US; agreement_country must be US",
            diagnostics={"agreement_country": agreement_country, "hero_country": "US"},
        )
    country = str(
        getattr(settings, "personal_paypal_agreement_sms_country", "187") or "187"
    ).strip()
    configured_country = str(input_json.get("agreement_sms_country") or "").strip()
    if configured_country and configured_country != country:
        raise PersonalPayPalAgreementError(
            "paypal_agreement_sms_country_mismatch",
            "The configured Hero long-term phone is US/187; agreement_sms_country must remain 187",
            diagnostics={"configured_country": configured_country, "hero_country": country},
        )
    if not country.isdigit():
        raise PersonalPayPalAgreementError(
            "paypal_agreement_sms_country_invalid",
            "PayPal agreement Hero country must be a numeric country id",
        )

    def emit(stage: str, data: dict, level: str = "INFO") -> None:
        if not run_id:
            return
        try:
            with session_factory() as session:
                EventWriter(session).write(
                    run_id=run_id,
                    event_type=f"personal_paypal_agreement.phone.{stage}",
                    message=f"PayPal agreement phone {stage}",
                    level=level,
                    data_json={
                        "space_id": space_id,
                        "work_id": work_id,
                        "sms_country": country,
                        **data,
                    },
                )
                session.commit()
        except Exception:
            # Diagnostics must never change the SMS lease lifecycle.
            pass

    try:
        return HeroSmsLongTermPhoneProviderAdapter(
            PhoneConfig(
                enabled=True,
                provider="hero_sms_long_term",
                base_url=str(
                    getattr(
                        settings,
                        "hero_sms_base_url",
                        "https://hero-sms.com/stubs/handler_api.php",
                    )
                    or "https://hero-sms.com/stubs/handler_api.php"
                ).strip(),
                api_key_env="HERO_SMS_API_KEY",
                service=str(settings.personal_paypal_agreement_sms_service or "ts").strip(),
                country=country,
                countries=[country],
                maxPrice="",
                max_number_attempts=settings.personal_paypal_agreement_max_phone_attempts,
                request_timeout_s=int(
                    getattr(settings, "hero_sms_request_timeout_s", 20) or 20
                ),
                otp_timeout_s=settings.personal_paypal_agreement_otp_timeout_s,
                otp_poll_interval_s=float(
                    getattr(settings, "hero_sms_poll_interval_s", 3.0) or 3.0
                ),
            ),
            api_key=api_key,
            activation_id="",
            lock_timeout_s=int(
                getattr(settings, "personal_paypal_agreement_hero_lock_timeout_s", 1800)
                or 1800
            ),
            country_phone_code="1",
            event_callback=emit,
        )
    except PersonalPayPalAgreementError:
        raise
    except Exception as exc:
        raise PersonalPayPalAgreementError(
            "paypal_agreement_sms_provider_init_failed",
            str(exc),
        ) from exc


def _personal_codex_grizzly_phone_provider(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
    run_id: str,
):
    if not bool(input_json.get("use_hero_sms_for_add_phone")):
        return None
    country = str(
        input_json.get("hero_sms_country")
        or getattr(settings, "grizzly_sms_country", "187")
        or "187"
    ).strip()
    max_price = str(
        input_json.get("hero_sms_max_price")
        or getattr(settings, "grizzly_sms_max_price", "0.18")
        or "0.18"
    ).strip()
    if not country or not country.isdigit():
        raise RuntimeError("grizzly_sms_country must be a numeric GrizzlySMS country id")
    try:
        parsed_max_price = Decimal(max_price)
    except InvalidOperation as exc:
        raise RuntimeError("grizzly_sms_max_price must be a positive number") from exc
    if not parsed_max_price.is_finite() or parsed_max_price <= 0:
        raise RuntimeError("grizzly_sms_max_price must be a positive number")

    def emit(stage: str, data: dict, level: str = "INFO") -> None:
        if not run_id:
            return
        with session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=f"account_auth.grizzly_sms.{stage}",
                message=f"GrizzlySMS {stage}",
                level=level,
                data_json=data,
            )
            session.commit()

    return HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="grizzly_sms",
            base_url=str(
                getattr(
                    settings,
                    "grizzly_sms_base_url",
                    "https://api.grizzlysms.com/stubs/handler_api.php",
                )
                or "https://api.grizzlysms.com/stubs/handler_api.php"
            ).strip(),
            api_key_env="GRIZZLY_SMS_API_KEY",
            service=str(getattr(settings, "grizzly_sms_service", "dr") or "dr").strip(),
            country=country,
            countries=[country],
            maxPrice=max_price,
            max_number_attempts=max(
                1,
                int(getattr(settings, "grizzly_sms_max_number_attempts", 3) or 3),
            ),
            request_timeout_s=max(
                1,
                int(getattr(settings, "grizzly_sms_request_timeout_s", 20) or 20),
            ),
            otp_timeout_s=max(
                1,
                int(getattr(settings, "grizzly_sms_otp_timeout_s", 120) or 120),
            ),
            otp_poll_interval_s=max(
                0.1,
                float(getattr(settings, "grizzly_sms_poll_interval_s", 3.0) or 3.0),
            ),
        ),
        api_key=str(getattr(settings, "grizzly_sms_api_key", "") or "").strip(),
        event_callback=emit,
    )


def _personal_codex_hero_phone_provider(**kwargs):
    """Compatibility alias; the standalone Codex path now uses GrizzlySMS."""
    return _personal_codex_grizzly_phone_provider(**kwargs)


def _registration_codex_grizzly_phone_provider(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    run_id: str,
) -> HeroSmsPhoneProviderAdapter:
    api_key = str(getattr(settings, "grizzly_sms_api_key", "") or "").strip()
    if not api_key:
        raise RuntimeError("GRIZZLY_SMS_API_KEY is required for iCloud Codex authorization")

    def emit(stage: str, data: dict, level: str = "INFO") -> None:
        if not run_id:
            return
        with session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=f"protocol.register.codex_grizzly_sms.{stage}",
                message=f"post-registration GrizzlySMS {stage}",
                level=level,
                data_json=data,
            )
            session.commit()

    country = str(getattr(settings, "grizzly_sms_country", "187") or "187").strip()
    return HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="grizzly_sms",
            base_url=str(
                getattr(
                    settings,
                    "grizzly_sms_base_url",
                    "https://api.grizzlysms.com/stubs/handler_api.php",
                )
                or "https://api.grizzlysms.com/stubs/handler_api.php"
            ).strip(),
            api_key_env="GRIZZLY_SMS_API_KEY",
            service=str(getattr(settings, "grizzly_sms_service", "dr") or "dr").strip(),
            country=country,
            countries=[country],
            maxPrice=str(getattr(settings, "grizzly_sms_max_price", "0.18") or "0.18").strip(),
            max_number_attempts=max(
                1,
                int(getattr(settings, "grizzly_sms_max_number_attempts", 3) or 3),
            ),
            request_timeout_s=max(
                1,
                int(getattr(settings, "grizzly_sms_request_timeout_s", 20) or 20),
            ),
            otp_timeout_s=max(
                1,
                int(getattr(settings, "grizzly_sms_otp_timeout_s", 120) or 120),
            ),
            otp_poll_interval_s=max(
                0.1,
                float(getattr(settings, "grizzly_sms_poll_interval_s", 3.0) or 3.0),
            ),
        ),
        api_key=api_key,
        event_callback=emit,
    )


def _protocol_registration_input(
    input_json: dict,
    *,
    default_proxy_country: str = "US",
    default_phone_provider: str = "grizzly_sms",
    default_phone_base_url: str = "https://api.grizzlysms.com/stubs/handler_api.php",
    default_phone_api_key_env: str = "GRIZZLY_SMS_API_KEY",
    default_phone_service: str = "dr",
    default_phone_country: str = "",
    default_phone_countries: tuple[str, ...] = ("187",),
    default_phone_max_price: str = "0.18",
    default_phone_max_number_attempts: int = 3,
    default_phone_request_timeout_s: int = 20,
    default_phone_otp_timeout_s: int = 120,
    default_phone_otp_poll_interval_s: float = 3.0,
    allow_phone_endpoint_override: bool = True,
    default_browser_log_enabled: bool = False,
    default_browser_log_capture_bodies: bool = False,
    default_browser_log_max_body_chars: int = 20_000,
) -> ProtocolRegistrationInput:
    raw_phone_countries = input_json.get("phone_countries")
    if raw_phone_countries is None:
        raw_phone_countries = list(default_phone_countries)
    raw_browser_close_delay = input_json.get("browser_close_delay_s", 10.0)
    if raw_browser_close_delay in (None, ""):
        raw_browser_close_delay = 10.0
    return ProtocolRegistrationInput(
        mode=str(input_json.get("mode") or ""),
        fixed_email=str(input_json.get("fixed_email") or ""),
        use_proxy=bool(input_json.get("use_proxy", True)),
        proxy_url=str(input_json.get("proxy_url") or ""),
        proxy_country=str(input_json.get("proxy_country") or default_proxy_country or "US"),
        proxy_state=str(
            input_json.get("proxy_state", input_json.get("state", "")) or ""
        ).strip(),
        proxy_asn=str(
            input_json.get("proxy_asn", input_json.get("asn", "")) or ""
        ).strip(),
        mail_provider=str(input_json.get("mail_provider") or "outlook"),
        email_domain=str(input_json.get("email_domain") or ""),
        project_key=str(input_json.get("project_key") or "openai-register"),
        caller_id=str(input_json.get("caller_id") or "refactor-app-protocol-registration"),
        browser_headless=bool(input_json.get("browser_headless", True)),
        browser_otp_timeout_s=max(1, int(input_json.get("browser_otp_timeout_s") or 180)),
        browser_close_delay_s=max(
            0.0,
            float(raw_browser_close_delay),
        ),
        browser_log_enabled=bool(
            input_json.get("browser_log_enabled", default_browser_log_enabled)
        ),
        browser_log_capture_bodies=bool(
            input_json.get(
                "browser_log_capture_bodies",
                default_browser_log_capture_bodies,
            )
        ),
        browser_log_max_body_chars=max(
            1_000,
            int(
                input_json.get(
                    "browser_log_max_body_chars",
                    default_browser_log_max_body_chars,
                )
            ),
        ),
        browser_backend=str(input_json.get("browser_backend") or "camoufox")
        .strip()
        .casefold(),
        phone_provider=str(
            input_json.get("phone_provider") or default_phone_provider
        ),
        phone_base_url=str(
            (
                input_json.get("phone_base_url")
                if allow_phone_endpoint_override
                else ""
            )
            or default_phone_base_url
        ),
        phone_api_key_env=str(
            (
                input_json.get("phone_api_key_env")
                if allow_phone_endpoint_override
                else ""
            )
            or default_phone_api_key_env
        ),
        phone_service=str(input_json.get("phone_service") or default_phone_service),
        phone_country=str(input_json.get("phone_country") or default_phone_country),
        phone_countries=[str(item).strip() for item in raw_phone_countries if str(item).strip()],
        phone_max_price=str(input_json.get("phone_max_price") or default_phone_max_price),
        phone_country_max_prices=dict(input_json.get("phone_country_max_prices") or {}),
        phone_max_number_attempts=max(
            1,
            int(
                input_json.get("phone_max_number_attempts")
                or default_phone_max_number_attempts
            ),
        ),
        phone_request_timeout_s=max(
            1,
            int(input_json.get("phone_request_timeout_s") or default_phone_request_timeout_s),
        ),
        phone_otp_timeout_s=max(
            1,
            int(input_json.get("phone_otp_timeout_s") or default_phone_otp_timeout_s),
        ),
        phone_otp_poll_interval_s=max(
            0.1,
            float(
                input_json.get("phone_otp_poll_interval_s")
                or default_phone_otp_poll_interval_s
            ),
        ),
    )


def _work_summary(*, session_factory: SessionFactory, job_id: str) -> dict[str, int]:
    with session_factory() as session:
        rows = session.scalars(select(WorkItemModel).where(WorkItemModel.job_id == job_id)).all()
        return {
            "queued": sum(1 for row in rows if row.work_status == "queued"),
            "running": sum(1 for row in rows if row.work_status == "running"),
            "succeeded": sum(1 for row in rows if row.work_status == "succeeded"),
            "skipped": sum(1 for row in rows if row.work_status == "skipped"),
            "failed": sum(1 for row in rows if row.work_status == "failed"),
            "cancelled": sum(1 for row in rows if row.work_status == "cancelled"),
        }


def _webshare_plugin(
    settings: Settings,
    *,
    download_url: str = "",
    proxy_type: str = "proxyserver",
) -> WebshareProxyPlugin:
    return WebshareProxyPlugin.from_config(
        WebshareClientConfig(
            api_token=settings.webshare_api_token,
            base_url=settings.webshare_base_url,
            download_url=download_url or settings.webshare_download_url,
            proxy_type=proxy_type,
        )
    )


def _openai_plugin(settings: Settings) -> OpenAIChatGPTPlugin:
    return OpenAIChatGPTPlugin.from_config(
        OpenAIChatGPTClientConfig(
            auth_base_url=settings.openai_auth_base_url,
            chatgpt_base_url=settings.openai_chatgpt_base_url,
            probe_path_template=settings.openai_probe_path_template,
        )
    )


def _mail_plugin(settings: Settings) -> ExternalMailApiPlugin:
    return ExternalMailApiPlugin.from_config(
        ExternalMailApiClientConfig(
            base_url=settings.external_mail_api_base_url,
            api_key=settings.external_mail_api_key,
            provider_name=settings.external_mail_provider_name,
        )
    )


def _hero_email_plugin(settings: Settings) -> HeroEmailPlugin:
    # Existing deployments already provision HERO_SMS_API_KEY for Hero. Keep
    # that key as a fallback while allowing a dedicated email key when the
    # provider account separates SMS and email balances.
    api_key = str(settings.hero_email_api_key or settings.hero_sms_api_key or "").strip()
    return HeroEmailPlugin(
        HeroEmailClientConfig(
            base_url=str(settings.hero_email_base_url or "").strip(),
            api_key=api_key,
            site=str(settings.hero_email_site or "chatgpt.com").strip(),
            domain=str(settings.hero_email_domain or "gmail.com").strip(),
            yandex_domains=str(
                getattr(settings, "hero_email_yandex_domains", "") or ""
            ).strip(),
            timeout_s=float(settings.hero_email_request_timeout_s or 30.0),
            poll_interval_s=float(settings.hero_email_poll_interval_s or 3.0),
            user_agent=str(settings.hero_email_user_agent or "").strip(),
        )
    )


def _registration_mail_plugin(
    settings: Settings,
    provider: str,
) -> ExternalMailApiPlugin | HeroEmailPlugin:
    normalized_provider = str(provider or "").strip()
    if normalized_provider in HERO_EMAIL_PROVIDERS:
        plugin = _hero_email_plugin(settings)
        # Keep the client factory's one-argument seam for existing test and
        # deployment integrations while exposing the selected Hero channel in
        # health checks and claim-completion metadata.
        if isinstance(plugin, HeroEmailPlugin):
            plugin.name = normalized_provider
        return plugin
    return _mail_plugin(settings)


def _twofauth_config(settings: Settings) -> TwoFAuthClientConfig | None:
    token = str(settings.twofauth_api_token or "").strip()
    token_file = str(settings.twofauth_api_token_file or "").strip()
    if not token and token_file:
        try:
            token = Path(token_file).expanduser().read_text().strip()
        except OSError:
            return None
    if not token:
        return None
    return TwoFAuthClientConfig(
        base_url=settings.twofauth_base_url,
        api_token=token,
    )


def _twofauth_client(settings: Settings) -> TwoFAuthClient | None:
    config = _twofauth_config(settings)
    return TwoFAuthClient(config) if config is not None else None


def _twofauth_otp_resolver(settings: Settings) -> Callable[[str], str] | None:
    config = _twofauth_config(settings)
    if config is None:
        return None

    def resolve(account_id: str) -> str:
        client = TwoFAuthClient(config)
        try:
            return client.get_otp(account_id).password
        finally:
            client.close()

    return resolve


def _run_protocol_registration_work(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
) -> dict:
    registration_input = _protocol_registration_input(
        input_json,
        default_proxy_country=str(getattr(settings, "protocol_register_proxy_country", "US")),
        default_phone_provider="grizzly_sms",
        default_phone_base_url=str(
            getattr(
                settings,
                "grizzly_sms_base_url",
                "https://api.grizzlysms.com/stubs/handler_api.php",
            )
            or "https://api.grizzlysms.com/stubs/handler_api.php"
        ),
        default_phone_api_key_env="GRIZZLY_SMS_API_KEY",
        default_phone_service=str(getattr(settings, "grizzly_sms_service", "dr") or "dr"),
        default_phone_country=str(
            getattr(settings, "grizzly_sms_country", "187") or "187"
        ),
        default_phone_countries=(
            str(getattr(settings, "grizzly_sms_country", "187") or "187"),
        ),
        default_phone_max_price=str(
            getattr(settings, "grizzly_sms_max_price", "0.18") or "0.18"
        ),
        default_phone_max_number_attempts=int(
            getattr(settings, "grizzly_sms_max_number_attempts", 3) or 3
        ),
        default_phone_request_timeout_s=int(
            getattr(settings, "grizzly_sms_request_timeout_s", 20) or 20
        ),
        default_phone_otp_timeout_s=int(
            getattr(settings, "grizzly_sms_otp_timeout_s", 120) or 120
        ),
        default_phone_otp_poll_interval_s=float(
            getattr(settings, "grizzly_sms_poll_interval_s", 3.0) or 3.0
        ),
        allow_phone_endpoint_override=False,
        default_browser_log_enabled=bool(
            getattr(settings, "browser_log_enabled", False)
        ),
        default_browser_log_capture_bodies=bool(
            getattr(settings, "browser_log_capture_bodies", False)
        ),
        default_browser_log_max_body_chars=int(
            getattr(settings, "browser_log_max_body_chars", 20_000)
        ),
    )
    twofauth_client = (
        _twofauth_client(settings)
        if registration_mode_requires_security(registration_input.mode)
        else None
    )
    mail_provider = _registration_mail_plugin(settings, registration_input.mail_provider)
    resume_mail_claim = _registration_resume_mail_claim(
        session_factory=session_factory,
        input_json=input_json,
    )
    if resume_mail_claim is not None and isinstance(mail_provider, HeroEmailPlugin):
        mail_provider.restore_claim(resume_mail_claim)
    codex_phone_provider = None
    try:
        authorize_codex_after_security = (
            registration_mode_requires_security(registration_input.mode)
            and bool(input_json.get("authorize_codex_after_security", False))
        )
        if authorize_codex_after_security:
            codex_phone_provider = _registration_codex_grizzly_phone_provider(
                session_factory=session_factory,
                settings=settings,
                run_id=str(input_json.get("_run_id") or ""),
            )
        return ProtocolRegistrationWorkflow(
            session_factory=session_factory,
            mail_provider=mail_provider,
            hero_sms_api_key=str(getattr(settings, "grizzly_sms_api_key", "") or ""),
            twofauth_client=twofauth_client,
            authorize_codex_after_security=authorize_codex_after_security,
            promotion_check_enabled=(
                bool(
                    getattr(
                        settings,
                        "icloud_post_registration_promotion_check_enabled",
                        False,
                    )
                )
            ),
            codex_phone_provider=codex_phone_provider,
            totp_code_resolver=_twofauth_otp_resolver(settings),
            resume_mail_claim=resume_mail_claim,
            cloakbrowser_license_key=str(
                getattr(settings, "cloakbrowser_license_key", "") or ""
            ).strip(),
        ).run(
            registration_input,
            work_id=str(input_json.get("_work_id") or ""),
            run_id=str(input_json.get("_run_id") or ""),
        )
    finally:
        if codex_phone_provider is not None:
            codex_phone_provider.close()
        if twofauth_client is not None:
            twofauth_client.close()
        close_mail_provider = getattr(mail_provider, "close", None)
        if callable(close_mail_provider):
            close_mail_provider()


def _registration_resume_mail_claim(
    *,
    session_factory: SessionFactory,
    input_json: dict,
) -> ClaimedMailAccount | None:
    provider = str(input_json.get("mail_provider") or "").strip()
    if provider not in HERO_EMAIL_PROVIDERS:
        return None
    work_id = str(input_json.get("_work_id") or "").strip()
    run_id = str(input_json.get("_run_id") or "").strip()
    if not work_id or not run_id:
        return None
    with session_factory() as session:
        work = session.get(WorkItemModel, work_id)
        output = dict(work.output_json or {}) if work is not None else {}
    if str(output.get("mail_claim_run_id") or "").strip() != run_id:
        return None
    raw = output.get("mail_claim")
    if not isinstance(raw, dict):
        return None
    email = str(raw.get("email") or "").strip().lower()
    email_id = str(raw.get("claim_token") or "").strip()
    account_id = str(raw.get("account_id") or "").strip()
    if not email or not email_id or not account_id.startswith("hero-email:"):
        return None
    return ClaimedMailAccount(
        account_id=account_id,
        email=email,
        claim_token=email_id,
        caller_id=str(raw.get("caller_id") or input_json.get("caller_id") or ""),
        task_id=str(raw.get("task_id") or work_id),
        email_domain=str(raw.get("email_domain") or email.rpartition("@")[2]),
        raw={"source": provider, "provider": provider, "restored": True, "email_id": email_id},
    )


def _downstream_plugin_from_channel_id(
    session_factory: SessionFactory,
    downstream_channel_id: str,
):
    with session_factory() as session:
        channel = session.get(DownstreamChannelModel, downstream_channel_id)
        if channel is None:
            raise RuntimeError(f"downstream channel not found: {downstream_channel_id}")
        return provider_from_channel(channel)
