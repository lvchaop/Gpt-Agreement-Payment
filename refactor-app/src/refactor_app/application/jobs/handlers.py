from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from refactor_app.application.jobs.runner import JobRunner
from refactor_app.application.workflows.account_auth import (
    BackfillRtWorkflow,
    BackfillSessionRtWorkflow,
    BackfillSessionWorkflow,
)
from refactor_app.application.workflows.batches import (
    ActivateWorkspaceJoinBatchWorkflow,
    JoinWorkspaceBatchInput,
    JoinWorkspaceBatchWorkflow,
    ProcessWorkspaceJoinBatchItemInput,
    ProcessWorkspaceJoinBatchItemWorkflow,
)
from refactor_app.application.workflows.codex_credentials import (
    BuildCodexCredentialWorkInput,
    BuildCodexCredentialWorkItemWorkflow,
)
from refactor_app.application.workflows.heartbeat import HeartbeatCodexCredentialWorkflow
from refactor_app.application.workflows.mail import (
    AllocateMailLeaseWorkflow,
    MarkMailLeaseFailedWorkflow,
    MarkMailLeaseUsedWorkflow,
    PollMailOtpWorkflow,
    ReleaseMailLeaseWorkflow,
)
from refactor_app.application.workflows.membership import (
    AcceptWorkspaceInviteWorkflow,
    InviteWorkspaceMemberWorkflow,
    MembershipProbeWorkflow,
)
from refactor_app.application.workflows.proxy import (
    BindAccountProxyWorkflow,
    HealthcheckProxyWorkflow,
    RefreshWebsharePoolWorkflow,
)
from refactor_app.application.workflows.workspace import (
    ImportTeamWorkspaceInput,
    ImportTeamWorkspaceWorkflow,
)
from refactor_app.config.settings import Settings
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
        "team_workspace.import",
        lambda _session, input_json: {
            "team_workspace_id": ImportTeamWorkspaceWorkflow(
                session_factory=session_factory
            ).run(ImportTeamWorkspaceInput(**input_json))
        },
    )
    runner.register(
        "proxy.refresh_webshare_pool",
        lambda _session, input_json: {
            "proxy_count": RefreshWebsharePoolWorkflow(
                session_factory=session_factory,
                proxy_provider=_webshare_plugin(
                    settings,
                    download_url=str(input_json.get("download_url") or ""),
                ),
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
        "membership.probe",
        lambda _session, input_json: {
            "membership": MembershipProbeWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            )
            .run(membership_id=str(input_json["membership_id"]))
            .__dict__
        },
    )
    runner.register(
        "membership.invite_member",
        lambda _session, input_json: {
            "invite": InviteWorkspaceMemberWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run(
                inviter_membership_id=str(input_json["inviter_membership_id"]),
                email=str(input_json["email"]),
            )
        },
    )
    runner.register(
        "membership.invite_member.bulk",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "workspace_join_batch.run",
        lambda _session, input_json: {
            "batch_id": JoinWorkspaceBatchWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
                mail_provider=_mail_plugin(settings),
            ).run(JoinWorkspaceBatchInput(**input_json))
        },
    )
    runner.register(
        "workspace_join_batch.activate",
        lambda _session, input_json: {
            "batch_id": ActivateWorkspaceJoinBatchWorkflow(
                session_factory=session_factory
            ).run(batch_id=str(input_json["batch_id"]))
        },
    )
    runner.register(
        "codex_credential.heartbeat",
        lambda _session, input_json: {
            "codex_credential_id": HeartbeatCodexCredentialWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run(codex_credential_id=str(input_json["codex_credential_id"]))
        },
    )
    runner.register(
        "codex_credential.build.bulk",
        lambda _session, input_json: {
            "work_count": len(input_json.get("user_account_ids") or []),
        },
    )
    runner.register(
        "codex_credential.heartbeat.bulk",
        lambda _session, input_json: {
            "work_count": len(input_json.get("codex_credential_ids") or []),
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
    runner.register_work(
        "workspace_join_batch.item",
        lambda _session, input_json: {
            "batch_item_id": ProcessWorkspaceJoinBatchItemWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
                mail_provider=_mail_plugin(settings),
            ).run(
                ProcessWorkspaceJoinBatchItemInput(
                    batch_id=str(input_json["batch_id"]),
                    batch_item_id=str(input_json["batch_item_id"]),
                    user_account_id=str(input_json["user_account_id"]),
                    team_workspace_id=str(input_json["team_workspace_id"]),
                    codex_client_id=str(input_json["codex_client_id"]),
                )
            )
        },
    )
    runner.register_work(
        "codex_credential.build.account",
        lambda _session, input_json: {
            "codex_credential_id": BuildCodexCredentialWorkItemWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
                mail_provider=_mail_plugin(settings),
            ).run(
                BuildCodexCredentialWorkInput(
                    user_account_id=str(input_json["user_account_id"]),
                    team_workspace_id=str(input_json["team_workspace_id"]),
                    codex_client_id=str(input_json["codex_client_id"]),
                    force_reauthorize=bool(input_json.get("force_reauthorize")),
                )
            )
        },
    )
    runner.register_work(
        "codex_credential.heartbeat.account",
        lambda _session, input_json: {
            "codex_credential_id": HeartbeatCodexCredentialWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run(codex_credential_id=str(input_json["codex_credential_id"]))
        },
    )
    runner.register_work(
        "membership.invite_member.account",
        lambda _session, input_json: {
            "invite": InviteWorkspaceMemberWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run_admin_invite(
                team_workspace_id=str(input_json["team_workspace_id"]),
                user_account_id=str(input_json["user_account_id"]),
                team_admin_session_id=str(input_json.get("team_admin_session_id") or ""),
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
        "membership.accept_invite.account",
        lambda _session, input_json: {
            "accept": AcceptWorkspaceInviteWorkflow(
                session_factory=session_factory,
                openai_provider=_openai_plugin(settings),
            ).run(
                membership_id=str(input_json["membership_id"]),
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


def _webshare_plugin(settings: Settings, *, download_url: str = "") -> WebshareProxyPlugin:
    return WebshareProxyPlugin.from_config(
        WebshareClientConfig(
            api_token=settings.webshare_api_token,
            base_url=settings.webshare_base_url,
            download_url=download_url or settings.webshare_download_url,
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
