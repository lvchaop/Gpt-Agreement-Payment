from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

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
from refactor_app.application.workflows.protocol_registration import (
    EMAIL_BROWSER_NO_PHONE,
    EMAIL_PROTOCOL_NO_PHONE,
    ICLOUD_HIDE_MY_EMAIL_PROVIDER,
    PHONE_PROTOCOL_BIND_EMAIL,
    HeroSmsPhoneProviderAdapter,
    ProtocolRegistrationInput,
    ProtocolRegistrationWorkflow,
)
from refactor_app.application.workflows.proxy import (
    BindAccountProxyWorkflow,
    BindTeamAdminProxyWorkflow,
    HealthcheckProxyWorkflow,
    RefreshWebsharePoolWorkflow,
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
    SpaceModel,
    UserAccountModel,
    WorkItemModel,
)
from refactor_app.infrastructure.logging.event_writer import EventWriter
from refactor_app.plugins.mail_external_api.client import ExternalMailApiClientConfig
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_auth_protocol.config import PhoneConfig
from refactor_app.plugins.openai_chatgpt.client import OpenAIChatGPTClientConfig
from refactor_app.plugins.openai_chatgpt.plugin import OpenAIChatGPTPlugin
from refactor_app.plugins.proxy_webshare.client import WebshareClientConfig
from refactor_app.plugins.proxy_webshare.plugin import WebshareProxyPlugin
from refactor_app.plugins.twofauth import TwoFAuthClient, TwoFAuthClientConfig

SessionFactory = Callable[[], Session]


def register_core_handlers(
    runner: JobRunner,
    *,
    session_factory: SessionFactory,
    settings: Settings,
) -> None:
    totp_code_resolver = _twofauth_otp_resolver(settings)
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
    runner.register_work(
        "space.personal_payment_method_bind.space",
        lambda _session, input_json: PersonalPaymentMethodBindWorkflow(
            session_factory=session_factory,
            mail_provider=_mail_plugin(settings),
            registration_proxy_country=settings.protocol_register_proxy_country,
            totp_code_resolver=totp_code_resolver,
        ).run(
            space_id=str(input_json["space_id"]),
            run_id=str(input_json.get("_run_id") or ""),
            work_id=str(input_json.get("_work_id") or ""),
        ),
    )
    runner.register_work(
        "account.backfill_session_rt",
        lambda _session, input_json: {
            "user_account_id": BackfillSessionRtWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
                totp_code_resolver=totp_code_resolver,
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
    if mode not in (EMAIL_PROTOCOL_NO_PHONE, EMAIL_BROWSER_NO_PHONE, PHONE_PROTOCOL_BIND_EMAIL):
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
    input_json: dict,
) -> dict:
    job_id = str(input_json.get("_job_id") or "")
    run_id = str(input_json.get("_run_id") or "")
    requested_space_id = str(input_json.get("space_id") or "").strip()
    limit = max(1, int(input_json.get("limit") or 10))
    work_count = max(1, int(input_json.get("work_count") or 1))
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
                queue.enqueue(
                    job_id=job_id,
                    work_type="space.personal_payment_method_bind.space",
                    execution_key=f"personal-payment-method:{space.id}",
                    input_json={"space_id": space.id, "_run_id": run_id},
                )
            session.commit()
    summary = _work_summary(session_factory=session_factory, job_id=job_id)
    return {
        "space_id": requested_space_id,
        "selected_count": existing_count or len(selected),
        "limit": limit,
        "work_count": work_count,
        **summary,
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
    phone_provider = _personal_codex_hero_phone_provider(
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


def _personal_codex_hero_phone_provider(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    input_json: dict,
    run_id: str,
):
    if not bool(input_json.get("use_hero_sms_for_add_phone")):
        return None
    country = str(input_json.get("hero_sms_country") or "").strip()
    max_price = str(input_json.get("hero_sms_max_price") or "0.05").strip()
    if not country or not country.isdigit():
        raise RuntimeError("hero_sms_country must be a numeric Hero country id")
    try:
        parsed_max_price = Decimal(max_price)
    except InvalidOperation as exc:
        raise RuntimeError("hero_sms_max_price must be a positive number") from exc
    if not parsed_max_price.is_finite() or parsed_max_price <= 0:
        raise RuntimeError("hero_sms_max_price must be a positive number")

    def emit(stage: str, data: dict, level: str = "INFO") -> None:
        if not run_id:
            return
        with session_factory() as session:
            EventWriter(session).write(
                run_id=run_id,
                event_type=f"account_auth.hero_sms.{stage}",
                message=f"Hero SMS {stage}",
                level=level,
                data_json=data,
            )
            session.commit()

    return HeroSmsPhoneProviderAdapter(
        PhoneConfig(
            enabled=True,
            provider="hero_sms",
            base_url="https://hero-sms.com/stubs/handler_api.php",
            api_key_env="HERO_SMS_API_KEY",
            service="dr",
            country="",
            countries=[country],
            maxPrice=max_price,
            max_number_attempts=3,
            otp_timeout_s=180,
            otp_poll_interval_s=3.0,
        ),
        api_key=settings.hero_sms_api_key,
        event_callback=emit,
    )


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
            provider="hero_sms",
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
) -> ProtocolRegistrationInput:
    raw_phone_countries = input_json.get("phone_countries")
    if raw_phone_countries is None:
        raw_phone_countries = ["151", "73", "16"]
    return ProtocolRegistrationInput(
        mode=str(input_json.get("mode") or ""),
        fixed_email=str(input_json.get("fixed_email") or ""),
        use_proxy=bool(input_json.get("use_proxy", True)),
        proxy_url=str(input_json.get("proxy_url") or ""),
        proxy_country=str(input_json.get("proxy_country") or default_proxy_country or "US"),
        mail_provider=str(input_json.get("mail_provider") or "outlook"),
        email_domain=str(input_json.get("email_domain") or ""),
        project_key=str(input_json.get("project_key") or "openai-register"),
        caller_id=str(input_json.get("caller_id") or "refactor-app-protocol-registration"),
        browser_headless=bool(input_json.get("browser_headless", True)),
        browser_otp_timeout_s=max(1, int(input_json.get("browser_otp_timeout_s") or 180)),
        phone_provider=str(input_json.get("phone_provider") or "hero_sms"),
        phone_base_url=str(
            input_json.get("phone_base_url") or "https://hero-sms.com/stubs/handler_api.php"
        ),
        phone_api_key_env=str(input_json.get("phone_api_key_env") or "HERO_SMS_API_KEY"),
        phone_service=str(input_json.get("phone_service") or "dr"),
        phone_country=str(input_json.get("phone_country") or ""),
        phone_countries=[str(item).strip() for item in raw_phone_countries if str(item).strip()],
        phone_max_price=str(input_json.get("phone_max_price") or "0.05"),
        phone_country_max_prices=dict(input_json.get("phone_country_max_prices") or {}),
        phone_max_number_attempts=max(1, int(input_json.get("phone_max_number_attempts") or 3)),
        phone_otp_timeout_s=max(1, int(input_json.get("phone_otp_timeout_s") or 180)),
        phone_otp_poll_interval_s=max(
            1.0,
            float(input_json.get("phone_otp_poll_interval_s") or 3.0),
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
    )
    twofauth_client = (
        _twofauth_client(settings)
        if registration_input.mail_provider == ICLOUD_HIDE_MY_EMAIL_PROVIDER
        else None
    )
    codex_phone_provider = None
    try:
        authorize_codex_after_security = (
            registration_input.mail_provider == ICLOUD_HIDE_MY_EMAIL_PROVIDER
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
            mail_provider=_mail_plugin(settings),
            hero_sms_api_key=settings.hero_sms_api_key,
            twofauth_client=twofauth_client,
            authorize_codex_after_security=authorize_codex_after_security,
            codex_phone_provider=codex_phone_provider,
            totp_code_resolver=_twofauth_otp_resolver(settings),
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


def _downstream_plugin_from_channel_id(
    session_factory: SessionFactory,
    downstream_channel_id: str,
):
    with session_factory() as session:
        channel = session.get(DownstreamChannelModel, downstream_channel_id)
        if channel is None:
            raise RuntimeError(f"downstream channel not found: {downstream_channel_id}")
        return provider_from_channel(channel)
