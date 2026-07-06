from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from refactor_app.application.jobs.runner import JobRunner
from refactor_app.application.workflows.account_auth import (
    BackfillRtWorkflow,
    BackfillSessionRtWorkflow,
    BackfillSessionWorkflow,
)
from refactor_app.application.workflows.downstream_provider import provider_from_channel
from refactor_app.application.workflows.mail import (
    AllocateMailLeaseWorkflow,
    MarkMailLeaseFailedWorkflow,
    MarkMailLeaseUsedWorkflow,
    PollMailOtpWorkflow,
    ReleaseMailLeaseWorkflow,
)
from refactor_app.application.workflows.proxy import (
    BindAccountProxyWorkflow,
    HealthcheckProxyWorkflow,
    RefreshWebsharePoolWorkflow,
)
from refactor_app.application.workflows.space_authorization import (
    CreateBusinessAccessTokenCredentialInput,
    CreateBusinessAccessTokenCredentialWorkflow,
)
from refactor_app.application.workflows.space_direct_push import (
    SpaceDirectPushInput,
    SpaceDirectPushWorkflow,
)
from refactor_app.application.workflows.space_recycle import (
    SpaceRecycleSweepInput,
    SpaceRecycleSweepWorkflow,
)
from refactor_app.config.settings import Settings
from refactor_app.infrastructure.db.models import DownstreamChannelModel
from refactor_app.plugins.mail_external_api.client import ExternalMailApiClientConfig
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_chatgpt.client import OpenAIChatGPTClientConfig
from refactor_app.plugins.openai_chatgpt.plugin import OpenAIChatGPTPlugin
from refactor_app.plugins.proxy_webshare.client import WebshareClientConfig
from refactor_app.plugins.proxy_webshare.plugin import WebshareProxyPlugin

SessionFactory = Callable[[], Session]


def register_core_handlers(
    runner: JobRunner,
    *,
    session_factory: SessionFactory,
    settings: Settings,
) -> None:
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
        "proxy.healthcheck",
        lambda _session, input_json: HealthcheckProxyWorkflow(
            session_factory=session_factory
        ).run(proxy_id=str(input_json["proxy_id"])),
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
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
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
        "account.backfill_rt",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "space.recycle.sweep",
        lambda _session, input_json: SpaceRecycleSweepWorkflow(
            session_factory=session_factory,
        )
        .run(
            SpaceRecycleSweepInput(
                limit=int(input_json.get("limit") or 100),
            )
        )
        .__dict__,
    )
    runner.register_work(
        "space.business_access_token.create.account",
        lambda _session, input_json: {
            "space_credential_id": CreateBusinessAccessTokenCredentialWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run(
                CreateBusinessAccessTokenCredentialInput(
                    user_account_id=str(input_json["user_account_id"]),
                    external_space_id=str(input_json["external_space_id"]),
                    session_access_token=str(input_json["session_access_token"]),
                    credential_name=str(input_json["credential_name"]),
                    cookie_header=str(input_json.get("cookie_header") or ""),
                    space_name=str(input_json.get("space_name") or ""),
                    owner_user_account_id=str(input_json.get("owner_user_account_id") or ""),
                    source_admin_session_id=str(input_json.get("source_admin_session_id") or ""),
                    proxy_url=str(input_json.get("proxy_url") or ""),
                )
            )
        },
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
        "account.backfill_session_rt",
        lambda _session, input_json: {
            "user_account_id": BackfillSessionRtWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
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
            ).run(
                user_account_id=str(input_json["user_account_id"]),
                run_id=str(input_json.get("_run_id") or ""),
            )
        },
    )
    runner.register_work(
        "account.backfill_rt",
        lambda _session, input_json: {
            "user_account_id": BackfillRtWorkflow(
                session_factory=session_factory,
                mail_provider=_mail_plugin(settings),
            ).run(
                user_account_id=str(input_json["user_account_id"]),
                run_id=str(input_json.get("_run_id") or ""),
            )
        },
    )


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


def _downstream_plugin_from_channel_id(
    session_factory: SessionFactory,
    downstream_channel_id: str,
):
    with session_factory() as session:
        channel = session.get(DownstreamChannelModel, downstream_channel_id)
        if channel is None:
            raise RuntimeError(f"downstream channel not found: {downstream_channel_id}")
        return provider_from_channel(channel)
