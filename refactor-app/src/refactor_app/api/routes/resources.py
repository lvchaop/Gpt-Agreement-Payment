from __future__ import annotations

import json
import random
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from socket import gethostname
from threading import Thread
from time import sleep
from typing import Annotated, Any
from uuid import uuid4

from curl_cffi import requests as curl_requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, exists, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from refactor_app.api.dependencies import get_db_session
from refactor_app.application.jobs.handlers import register_core_handlers
from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.application.workflows.batches import (
    BatchWorkflowError,
    CreateWorkspaceBatchFromCredentialsInput,
    CreateWorkspaceBatchFromCredentialsWorkflow,
)
from refactor_app.application.workflows.codex_credentials import (
    BuildCodexCredentialWorkInput,
    BuildCodexCredentialWorkItemWorkflow,
)
from refactor_app.application.workflows.account_auth import _active_proxy, _proxy_url
from refactor_app.application.workflows.direct_push import (
    MAX_DOWNSTREAM_PUSH_ATTEMPTS,
    _provider_from_channel,
)
from refactor_app.application.workflows.downstream import downstream_payload
from refactor_app.application.workflows.heartbeat import (
    HeartbeatCodexCredentialWorkflow,
    _is_unauthorized_heartbeat_error,
)
from refactor_app.application.workflows.proxy import HealthcheckProxyWorkflow
from refactor_app.config.settings import get_settings
from refactor_app.domain.enums import AccountStatus, CredentialStatus
from refactor_app.infrastructure.db.models import (
    AccountSessionOtpSnapshotModel,
    AutomationScheduleModel,
    CodexOAuthCredentialModel,
    DownstreamChannelModel,
    DownstreamCodexPushRecordModel,
    ExternalMailLeaseModel,
    JobEventModel,
    JobModel,
    JobRunModel,
    MembershipModel,
    ProxyInventoryModel,
    TeamAdminAccountCheckModel,
    TeamAdminSessionModel,
    TeamWorkspaceModel,
    UserAccountAuthModel,
    UserAccountCooldownModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
    WorkItemModel,
    WorkspaceAutomationStateModel,
    WorkspaceOperationLockModel,
    WorkspaceJoinBatchItemModel,
    WorkspaceJoinBatchModel,
)
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.plugins.mail_external_api.client import ExternalMailApiClientConfig
from refactor_app.plugins.mail_external_api.plugin import ExternalMailApiPlugin
from refactor_app.plugins.openai_chatgpt.client import (
    CODEX_INSTRUCTIONS_PATH,
    CODEX_RESPONSES_PATH,
    OpenAIChatGPTClientConfig,
)
from refactor_app.plugins.openai_chatgpt.client import decode_access_token_claims
from refactor_app.plugins.openai_chatgpt.plugin import OpenAIChatGPTPlugin

router = APIRouter(tags=["resources"])
DbSession = Annotated[Session, Depends(get_db_session)]
CODEX_BROWSER_AUTH_CONCURRENCY_LIMIT = 50
CODEX_USAGE_PROBE_MODEL = "gpt-5.4"
CODEX_USAGE_PROBE_VERSION = "0.125.0"
CODEX_USAGE_PROBE_USER_AGENT = "codex_cli_rs/0.125.0 (Ubuntu 22.4.0; x86_64) xterm-256color"
DOWNSTREAM_PROVIDER_TYPES = {"sub2api", "cpa", "local_sub2api"}


@dataclass(frozen=True)
class CodexUsageProbeResult:
    ok: bool
    usage_percent: int = 0
    error_code: str = ""
    error_message: str = ""
    unauthorized: bool = False
    raw_headers: dict[str, str] = field(default_factory=dict)


class ImportUserAccountRequest(BaseModel):
    id: str = ""
    email: str
    account_status: str = AccountStatus.ACTIVE.value


class PatchUserAccountRequest(BaseModel):
    account_status: str | None = None


class ImportTeamWorkspaceRequest(BaseModel):
    provider: str = "openai_chatgpt"
    external_workspace_id: str
    name: str
    plan_type: str = ""
    seat_limit: int = 0
    workspace_status: str = "unknown"


class CreateWorkspaceJoinBatchRequest(BaseModel):
    team_workspace_id: str
    user_account_ids: list[str]
    codex_client_id: str
    batch_name: str = ""
    created_by: str = ""


class CreateWorkspaceJoinBatchFromCredentialsRequest(BaseModel):
    team_workspace_id: str
    codex_credential_ids: list[str]
    batch_name: str = ""
    created_by: str = ""


class BuildCodexCredentialsRequest(BaseModel):
    user_account_ids: list[str]
    team_workspace_id: str
    codex_client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    created_by: str = ""
    concurrency: int = 1
    force_reauthorize: bool = False


class HeartbeatCodexCredentialsRequest(BaseModel):
    codex_credential_ids: list[str]
    created_by: str = ""
    concurrency: int = 1


class PushCodexCredentialsRequest(BaseModel):
    codex_credential_ids: list[str]
    downstream_channel_id: str
    created_by: str = ""
    concurrency: int = 5
    request_endpoint: str = ""


class PushPendingCodexCredentialsRequest(BaseModel):
    downstream_channel_id: str
    limit: int = 1
    created_by: str = ""
    concurrency: int = 5
    request_endpoint: str = ""


class RefreshWebsharePoolRequest(BaseModel):
    download_url: str


class BackfillSessionRtRequest(BaseModel):
    user_account_ids: list[str]
    created_by: str = ""
    concurrency: int = 1


class ImportTeamAdminSessionRequest(BaseModel):
    raw_session_json: dict[str, Any]
    cookie_header: str = ""
    accounts_check_headers_text: str = ""
    timezone_offset_min: int = -480
    fetch_accounts_check: bool = True


class RemoveWorkspaceMembersRequest(BaseModel):
    confirm_remove: bool = False
    concurrency: int = 20
    page_size: int = 100


class RevokeWorkspaceInviteRequest(BaseModel):
    concurrency: int = 20
    page_size: int = 100


class CreateDownstreamChannelRequest(BaseModel):
    provider_type: str
    name: str
    base_url: str
    admin_key: str
    enabled: bool = True
    update_existing: bool = False
    timeout_s: int = 30
    max_push_count: int = 2
    max_active_slots: int = 1
    push_balance: int = 0


class PatchDownstreamChannelRequest(BaseModel):
    provider_type: str | None = None
    name: str | None = None
    base_url: str | None = None
    admin_key: str | None = None
    enabled: bool | None = None
    update_existing: bool | None = None
    timeout_s: int | None = None
    max_push_count: int | None = None
    max_active_slots: int | None = None
    push_balance: int | None = None


class AddDownstreamChannelBalanceRequest(BaseModel):
    amount: int


class InviteSelectedUsersRequest(BaseModel):
    team_workspace_id: str
    user_account_ids: list[str]
    team_admin_session_id: str = ""
    created_by: str = ""
    concurrency: int = 1


class AcceptMembershipInvitesRequest(BaseModel):
    membership_ids: list[str]
    created_by: str = ""
    concurrency: int = 1


class SessionOtpMembershipRequest(BaseModel):
    membership_ids: list[str]
    created_by: str = ""
    concurrency: int = 1


class SyncWorkspaceMembersRequest(BaseModel):
    team_workspace_id: str
    page_size: int = 100


class WorkspaceAutomationFillRequest(BaseModel):
    team_workspace_id: str
    user_account_ids: list[str]
    team_admin_session_id: str = ""
    codex_client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    created_by: str = ""
    invite_concurrency: int = 350
    post_invite_wait_seconds: int = 120
    sync_page_size: int = 100
    lock_ttl_seconds: int = 1800


class DownstreamUsageSweepRequest(BaseModel):
    downstream_channel_id: str = ""
    threshold_percent: int = 95
    created_by: str = ""


class AutomationWorkspaceInviteSyncRequest(BaseModel):
    created_by: str = ""
    workspace_limit: int = 20
    workspace_concurrency: int = 4
    invite_count: int = 350
    invite_concurrency: int = 350
    sync_after_seconds: int = 120
    sync_page_size: int = 100


class AutomationWorkspaceAuthorizeRequest(BaseModel):
    created_by: str = ""
    workspace_limit: int = 20
    workspace_concurrency: int = 4
    codex_client_id: str = "app_EMoamEEZ73f0CkXaXp7hrann"
    sync_page_size: int = 100
    lock_ttl_seconds: int = 1800
    authorization_sync_wait_seconds: int = 5


class AutomationDownstreamPushRequest(BaseModel):
    created_by: str = ""
    channel_limit: int = 20
    channel_concurrency: int = 4
    push_concurrency: int = 5
    per_channel_limit: int = 50
    request_endpoint: str = ""


class AutomationCodexHeartbeatRequest(BaseModel):
    created_by: str = ""
    credential_limit: int = 100
    credential_concurrency: int = 10


class AutomationDownstreamUsageCleanupRequest(BaseModel):
    created_by: str = ""
    record_limit: int = 100
    record_concurrency: int = 10
    threshold_percent: int = 95


class MonitorDownstreamUsageProbeRequest(BaseModel):
    downstream_push_record_ids: list[str] = []
    downstream_channel_id: str = ""
    limit: int = 100
    concurrency: int = 5
    threshold_percent: int = 95
    persist_result: bool = True


class RepushDownstreamRecordsRequest(BaseModel):
    downstream_push_record_ids: list[str]
    created_by: str = ""


class CreateAutomationScheduleRequest(BaseModel):
    schedule_type: str
    enabled: bool = False
    interval_seconds: int = 60
    config_json: dict[str, Any] = {}
    created_by: str = ""


class PatchAutomationScheduleRequest(BaseModel):
    enabled: bool | None = None
    schedule_status: str | None = None
    interval_seconds: int | None = None
    config_json: dict[str, Any] | None = None


@router.get("/user-accounts")
def list_user_accounts(session: DbSession) -> list[dict]:
    rows = session.execute(
        select(UserAccountModel, UserAccountAuthModel)
        .outerjoin(
            UserAccountAuthModel,
            UserAccountAuthModel.user_account_id == UserAccountModel.id,
        )
        .order_by(UserAccountModel.created_at.desc())
    ).all()
    return [
        {
            "id": account.id,
            "email": account.email,
            "phone_number": account.phone_number,
            "phone_dial_code": account.phone_dial_code,
            "phone_country": account.phone_country,
            "openai_user_id": account.openai_user_id,
            "account_status": account.account_status,
            "session_status": auth.session_status if auth else "unknown",
            "refresh_token_status": auth.refresh_token_status if auth else "missing",
            "personal_chatgpt_account_id": auth.personal_chatgpt_account_id if auth else "",
            "personal_chatgpt_account_discovered_at": (
                auth.personal_chatgpt_account_discovered_at.isoformat()
                if auth and auth.personal_chatgpt_account_discovered_at
                else ""
            ),
            "created_at": account.created_at.isoformat(),
            "updated_at": account.updated_at.isoformat(),
        }
        for account, auth in rows
    ]


@router.post("/user-accounts/import")
def import_user_account(
    req: ImportUserAccountRequest,
    session: DbSession,
) -> dict:
    now = datetime.now(UTC)
    account = UserAccountModel(
        id=req.id or f"user-account-{uuid4()}",
        email=req.email,
        account_status=req.account_status,
        created_at=now,
        updated_at=now,
    )
    session.merge(account)
    session.commit()
    return {"user_account_id": account.id}


@router.patch("/user-accounts/{user_account_id}")
def patch_user_account(
    user_account_id: str,
    req: PatchUserAccountRequest,
    session: DbSession,
) -> dict:
    account = session.get(UserAccountModel, user_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="user account not found")
    if req.account_status is not None:
        account.account_status = req.account_status
    account.updated_at = datetime.now(UTC)
    session.commit()
    return {"user_account_id": account.id, "account_status": account.account_status}


@router.delete("/user-accounts/{user_account_id}")
def delete_user_account(user_account_id: str, session: DbSession) -> dict:
    account = session.get(UserAccountModel, user_account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="user account not found")
    proxy_result = session.execute(
        delete(UserAccountProxyBindingModel).where(
            UserAccountProxyBindingModel.user_account_id == user_account_id
        )
    )
    session.delete(account)
    session.commit()
    return {
        "user_account_id": user_account_id,
        "deleted": True,
        "deleted_proxy_bindings": int(proxy_result.rowcount or 0),
    }


@router.post("/user-accounts/backfill-session-rt-job")
def create_backfill_session_rt_job(
    req: BackfillSessionRtRequest,
    session: DbSession,
) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_session_rt",
        work_type="account.backfill_session_rt",
    )


@router.post("/user-accounts/backfill-session-job")
def create_backfill_session_job(
    req: BackfillSessionRtRequest,
    session: DbSession,
) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_session",
        work_type="account.backfill_session",
    )


@router.post("/user-accounts/backfill-rt-job")
def create_backfill_rt_job(
    req: BackfillSessionRtRequest,
    session: DbSession,
) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_rt",
        work_type="account.backfill_rt",
    )


@router.post("/codex-credentials/build-job")
def create_codex_credentials_build_job(
    req: BuildCodexCredentialsRequest,
    session: DbSession,
) -> dict:
    return _create_codex_build_work_job(req=req, session=session)


def _create_account_work_job(
    *,
    req: BackfillSessionRtRequest,
    session: Session,
    job_type: str,
    work_type: str,
) -> dict:
    user_account_ids = [item.strip() for item in req.user_account_ids if item.strip()]
    if not user_account_ids:
        raise HTTPException(status_code=400, detail="user_account_ids is required")
    found_ids = set(
        session.scalars(
            select(UserAccountModel.id).where(UserAccountModel.id.in_(user_account_ids))
        ).all()
    )
    missing_ids = [item for item in user_account_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "some user accounts not found", "user_account_ids": missing_ids},
        )

    settings = get_settings()
    concurrency = max(1, min(int(req.concurrency or 1), settings.worker_max_concurrency))
    job = JobQueue(session).enqueue(
        job_type=job_type,
        input_json={"user_account_ids": user_account_ids, "concurrency": concurrency},
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    for user_account_id in user_account_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type=work_type,
            input_json={"user_account_id": user_account_id, "_run_id": run.id},
        )
    session.commit()

    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(user_account_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = (
            "succeeded"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] == 0
            else "failed"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] > 0
            else "running"
        )
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = (
                f"failed={summary['failed']} queued={summary['queued']} "
                f"running={summary['running']}"
            )
        session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(user_account_ids),
        "concurrency": concurrency,
        **summary,
    }


def _create_codex_build_work_job(
    *,
    req: BuildCodexCredentialsRequest,
    session: Session,
) -> dict:
    user_account_ids = [item.strip() for item in req.user_account_ids if item.strip()]
    if not user_account_ids:
        raise HTTPException(status_code=400, detail="user_account_ids is required")
    if not req.team_workspace_id:
        raise HTTPException(status_code=400, detail="team_workspace_id is required")
    if not req.codex_client_id:
        raise HTTPException(status_code=400, detail="codex_client_id is required")
    workspace = session.get(TeamWorkspaceModel, req.team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    found_ids = set(
        session.scalars(
            select(UserAccountModel.id).where(UserAccountModel.id.in_(user_account_ids))
        ).all()
    )
    missing_ids = [item for item in user_account_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "some user accounts not found", "user_account_ids": missing_ids},
        )

    settings = get_settings()
    requested_concurrency = max(1, int(req.concurrency or 1))
    concurrency = max(
        1,
        min(
            requested_concurrency,
            settings.worker_max_concurrency,
            CODEX_BROWSER_AUTH_CONCURRENCY_LIMIT,
        ),
    )
    job = JobQueue(session).enqueue(
        job_type="codex_credential.build.bulk",
        input_json={
            "user_account_ids": user_account_ids,
            "team_workspace_id": req.team_workspace_id,
            "codex_client_id": req.codex_client_id,
            "force_reauthorize": req.force_reauthorize,
            "requested_concurrency": requested_concurrency,
            "concurrency": concurrency,
        },
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    for user_account_id in user_account_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type="codex_credential.build.account",
            input_json={
                "user_account_id": user_account_id,
                "team_workspace_id": req.team_workspace_id,
                "codex_client_id": req.codex_client_id,
                "force_reauthorize": req.force_reauthorize,
                "_run_id": run.id,
            },
        )
    session.commit()

    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(user_account_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = (
            "succeeded"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] == 0
            else "failed"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] > 0
            else "running"
        )
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = (
                f"failed={summary['failed']} queued={summary['queued']} "
                f"running={summary['running']}"
            )
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(user_account_ids),
        "concurrency": concurrency,
        **summary,
    }


def _create_codex_heartbeat_work_job(
    *,
    req: HeartbeatCodexCredentialsRequest,
    session: Session,
) -> dict:
    credential_ids = [item.strip() for item in req.codex_credential_ids if item.strip()]
    if not credential_ids:
        raise HTTPException(status_code=400, detail="codex_credential_ids is required")
    found_ids = set(
        session.scalars(
            select(CodexOAuthCredentialModel.id).where(CodexOAuthCredentialModel.id.in_(credential_ids))
        ).all()
    )
    missing_ids = [item for item in credential_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "some codex credentials not found",
                "codex_credential_ids": missing_ids,
            },
        )

    settings = get_settings()
    concurrency = max(1, min(int(req.concurrency or 1), settings.worker_max_concurrency))
    job = JobQueue(session).enqueue(
        job_type="codex_credential.heartbeat.bulk",
        input_json={"codex_credential_ids": credential_ids, "concurrency": concurrency},
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    for credential_id in credential_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type="codex_credential.heartbeat.account",
            input_json={"codex_credential_id": credential_id, "_run_id": run.id},
        )
    session.commit()

    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(credential_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = (
            "succeeded"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] == 0
            else "failed"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] > 0
            else "running"
        )
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = (
                f"failed={summary['failed']} queued={summary['queued']} "
                f"running={summary['running']}"
            )
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(credential_ids),
        "concurrency": concurrency,
        **summary,
    }


def _create_codex_push_work_job(
    *,
    req: PushCodexCredentialsRequest,
    session: Session,
) -> dict:
    credential_ids = [item.strip() for item in req.codex_credential_ids if item.strip()]
    if not credential_ids:
        raise HTTPException(status_code=400, detail="codex_credential_ids is required")
    if not req.downstream_channel_id.strip():
        raise HTTPException(status_code=400, detail="downstream_channel_id is required")
    channel = session.get(DownstreamChannelModel, req.downstream_channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    found_ids = set(
        session.scalars(
            select(CodexOAuthCredentialModel.id).where(
                CodexOAuthCredentialModel.id.in_(credential_ids)
            )
        ).all()
    )
    missing_ids = [item for item in credential_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "some codex credentials not found",
                "codex_credential_ids": missing_ids,
            },
        )

    settings = get_settings()
    concurrency = max(1, min(int(req.concurrency or 5), settings.worker_max_concurrency))
    job = JobQueue(session).enqueue(
        job_type="codex_credential.push.bulk",
        input_json={
            "codex_credential_ids": credential_ids,
            "downstream_channel_id": req.downstream_channel_id,
            "concurrency": concurrency,
        },
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    for credential_id in credential_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type="codex_credential.push.account",
            input_json={
                "codex_credential_id": credential_id,
                "downstream_channel_id": req.downstream_channel_id,
                "request_endpoint": req.request_endpoint,
                "_run_id": run.id,
            },
        )
    session.commit()

    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(credential_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = (
            "succeeded"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] == 0
            else "failed"
            if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] > 0
            else "running"
        )
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = (
                f"failed={summary['failed']} queued={summary['queued']} "
                f"running={summary['running']}"
            )
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(credential_ids),
        "concurrency": concurrency,
        **summary,
    }


def _create_pending_codex_push_work_job(
    *,
    req: PushPendingCodexCredentialsRequest,
    session: Session,
) -> dict:
    channel = session.get(DownstreamChannelModel, req.downstream_channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    limit = max(1, int(req.limit or 1))
    credential_ids = _select_channel_push_credential_ids(
        session=session,
        channel=channel,
        limit=limit,
    )
    if not credential_ids:
        raise HTTPException(status_code=404, detail="no retryable failed or pending_push codex credentials found")
    return _create_codex_push_work_job(
        req=PushCodexCredentialsRequest(
            codex_credential_ids=list(credential_ids),
            downstream_channel_id=req.downstream_channel_id,
            created_by=req.created_by,
            concurrency=req.concurrency,
            request_endpoint=req.request_endpoint,
        ),
        session=session,
    )


def _select_channel_push_credential_ids(
    *,
    session: Session,
    channel: DownstreamChannelModel,
    limit: int,
    selected: set[str] | None = None,
) -> list[str]:
    selected_ids = selected if selected is not None else set()
    active_slots = _active_downstream_slot_count(session, channel.id)
    allowed_slots = _allowed_downstream_active_slots(session=session, channel=channel)
    remaining_new_slots = max(0, allowed_slots - active_slots)
    retry_take = max(1, int(limit or 1))
    retry_conditions = [
        DownstreamCodexPushRecordModel.downstream_channel_id == channel.id,
        DownstreamCodexPushRecordModel.push_status == "failed",
        DownstreamCodexPushRecordModel.push_attempt_count < MAX_DOWNSTREAM_PUSH_ATTEMPTS,
        CodexOAuthCredentialModel.credential_status == "active",
        CodexOAuthCredentialModel.last_heartbeat_status == "ok",
        CodexOAuthCredentialModel.access_token != "",
        CodexOAuthCredentialModel.refresh_token != "",
    ]
    if selected_ids:
        retry_conditions.append(~CodexOAuthCredentialModel.id.in_(selected_ids))
    retry_ids = session.scalars(
        select(CodexOAuthCredentialModel.id)
        .join(
            DownstreamCodexPushRecordModel,
            DownstreamCodexPushRecordModel.codex_credential_id == CodexOAuthCredentialModel.id,
        )
        .where(*retry_conditions)
        .order_by(DownstreamCodexPushRecordModel.updated_at.asc())
        .limit(retry_take)
    ).all()

    chosen = [str(item) for item in retry_ids]
    selected_ids.update(chosen)
    pending_limit = max(0, int(limit or 1) - len(chosen))
    pending_take = min(remaining_new_slots, pending_limit, max(0, int(channel.push_balance or 0)))
    if pending_take <= 0:
        return chosen

    pending_conditions = [
        CodexOAuthCredentialModel.push_lifecycle_status == "pending_push",
        CodexOAuthCredentialModel.credential_status == "active",
        CodexOAuthCredentialModel.last_heartbeat_status == "ok",
        CodexOAuthCredentialModel.access_token != "",
        CodexOAuthCredentialModel.refresh_token != "",
    ]
    if selected_ids:
        pending_conditions.append(~CodexOAuthCredentialModel.id.in_(selected_ids))
    pending_ids = session.scalars(
        select(CodexOAuthCredentialModel.id)
        .where(*pending_conditions)
        .order_by(CodexOAuthCredentialModel.updated_at.asc())
        .limit(pending_take)
    ).all()
    chosen.extend(str(item) for item in pending_ids)
    selected_ids.update(str(item) for item in pending_ids)
    return chosen


def _allowed_downstream_active_slots(*, session: Session, channel: DownstreamChannelModel) -> int:
    max_slots = max(0, int(channel.max_active_slots or 0))
    if max_slots <= 0:
        return 0
    high_usage_count = int(
        session.scalar(
            select(func.count())
            .select_from(DownstreamCodexPushRecordModel)
            .where(
                DownstreamCodexPushRecordModel.downstream_channel_id == channel.id,
                DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
                DownstreamCodexPushRecordModel.usage_percent >= 70,
            )
        )
        or 0
    )
    return min(max_slots, 1 + high_usage_count)


@router.post("/team-admin-sessions/import")
def import_team_admin_session(
    req: ImportTeamAdminSessionRequest,
    session: DbSession,
) -> dict:
    raw = req.raw_session_json
    access_token = str(raw.get("accessToken") or raw.get("access_token") or "")
    session_token = str(raw.get("sessionToken") or raw.get("session_token") or "")
    admin_email = _session_admin_email(raw, access_token)
    expires_at = _parse_datetime_or_none(str(raw.get("expires") or ""))
    browser_headers = _parse_browser_headers_text(req.accounts_check_headers_text)
    cookie_header_text = req.cookie_header.strip()
    cookie_field_headers = _parse_browser_headers_text(cookie_header_text)
    effective_cookie_header = (
        cookie_field_headers.get("cookie")
        or cookie_header_text
        or browser_headers.get("cookie", "")
    )
    now = datetime.now(UTC)
    admin_session = None
    if admin_email:
        admin_session = session.scalars(
            select(TeamAdminSessionModel)
            .where(TeamAdminSessionModel.admin_email == admin_email)
            .order_by(TeamAdminSessionModel.imported_at.desc())
        ).first()
    if admin_session is None:
        admin_session = TeamAdminSessionModel(
            id=f"team-admin-session-{uuid4()}",
            admin_email=admin_email,
            raw_session_json=raw,
            access_token=access_token,
            session_token=session_token,
            cookie_header=effective_cookie_header,
            expires_at=expires_at,
            imported_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(admin_session)
    else:
        admin_session.raw_session_json = raw
        admin_session.access_token = access_token
        admin_session.session_token = session_token
        admin_session.cookie_header = effective_cookie_header
        admin_session.expires_at = expires_at
        admin_session.imported_at = now
        admin_session.updated_at = now
    session.flush()

    check_payload: dict[str, Any] = {}
    if req.fetch_accounts_check:
        check_payload = _fetch_accounts_check(
            access_token=access_token,
            cookie_header=effective_cookie_header,
            browser_headers=browser_headers,
            timezone_offset_min=req.timezone_offset_min,
        )
        session.add(
            TeamAdminAccountCheckModel(
                id=f"team-admin-account-check-{uuid4()}",
                team_admin_session_id=admin_session.id,
                raw_check_json=check_payload,
                checked_at=now,
                created_at=now,
            )
        )

    workspace_inputs = _extract_workspaces_from_session_and_check(raw, check_payload)
    upserted = []
    for item in workspace_inputs:
        external_workspace_id = _workspace_external_id(item)
        subscription_payload = _fetch_workspace_subscription(
            access_token=access_token,
            cookie_header=effective_cookie_header,
            account_id=external_workspace_id,
        )
        workspace = _upsert_workspace_from_admin_source(
            session=session,
            source_admin_session_id=admin_session.id,
            item={**item, "_subscription": subscription_payload},
            now=now,
        )
        if workspace is not None:
            _ensure_workspace_automation_state(session=session, workspace_id=workspace.id)
            upserted.append(_workspace_dict(workspace, admin_email=admin_email))
    session.commit()
    return {
        "team_admin_session_id": admin_session.id,
        "admin_email": admin_email,
        "workspace_count": len(upserted),
        "workspaces": upserted,
    }


@router.get("/team-admin-sessions")
def list_team_admin_sessions(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(TeamAdminSessionModel).order_by(TeamAdminSessionModel.imported_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "admin_email": row.admin_email,
            "expires_at": row.expires_at.isoformat() if row.expires_at else "",
            "imported_at": row.imported_at.isoformat(),
        }
        for row in rows
    ]


@router.delete("/team-admin-sessions/{team_admin_session_id}")
def delete_team_admin_session(team_admin_session_id: str, session: DbSession) -> dict:
    admin_session = session.get(TeamAdminSessionModel, team_admin_session_id)
    if admin_session is None:
        raise HTTPException(status_code=404, detail="team admin session not found")

    workspace_ids = session.scalars(
        select(TeamWorkspaceModel.id).where(
            TeamWorkspaceModel.source_admin_session_id == team_admin_session_id
        )
    ).all()

    deleted_downstream_push_records = 0
    deleted_batch_items = 0
    deleted_batches = 0
    deleted_credentials = 0
    deleted_memberships = 0
    deleted_workspaces = 0
    deleted_account_checks = 0

    if workspace_ids:
        downstream_result = session.execute(
            delete(DownstreamCodexPushRecordModel).where(
                DownstreamCodexPushRecordModel.team_workspace_id.in_(workspace_ids)
            )
        )
        deleted_downstream_push_records = downstream_result.rowcount or 0

        batch_item_result = session.execute(
            delete(WorkspaceJoinBatchItemModel).where(
                WorkspaceJoinBatchItemModel.team_workspace_id.in_(workspace_ids)
            )
        )
        deleted_batch_items = batch_item_result.rowcount or 0

        batch_result = session.execute(
            delete(WorkspaceJoinBatchModel).where(
                WorkspaceJoinBatchModel.team_workspace_id.in_(workspace_ids)
            )
        )
        deleted_batches = batch_result.rowcount or 0

        credential_result = session.execute(
            delete(CodexOAuthCredentialModel).where(
                CodexOAuthCredentialModel.team_workspace_id.in_(workspace_ids)
            )
        )
        deleted_credentials = credential_result.rowcount or 0

        membership_result = session.execute(
            delete(MembershipModel).where(MembershipModel.team_workspace_id.in_(workspace_ids))
        )
        deleted_memberships = membership_result.rowcount or 0

        workspace_result = session.execute(
            delete(TeamWorkspaceModel).where(TeamWorkspaceModel.id.in_(workspace_ids))
        )
        deleted_workspaces = workspace_result.rowcount or 0

    account_check_result = session.execute(
        delete(TeamAdminAccountCheckModel).where(
            TeamAdminAccountCheckModel.team_admin_session_id == team_admin_session_id
        )
    )
    deleted_account_checks = account_check_result.rowcount or 0

    session.delete(admin_session)
    session.commit()
    return {
        "team_admin_session_id": team_admin_session_id,
        "deleted": True,
        "deleted_workspaces": deleted_workspaces,
        "deleted_memberships": deleted_memberships,
        "deleted_credentials": deleted_credentials,
        "deleted_batches": deleted_batches,
        "deleted_batch_items": deleted_batch_items,
        "deleted_downstream_push_records": deleted_downstream_push_records,
        "deleted_account_checks": deleted_account_checks,
    }


@router.get("/team-workspaces")
def list_team_workspaces(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(TeamWorkspaceModel).order_by(TeamWorkspaceModel.created_at.desc())
    ).all()
    admin_session_ids = [row.source_admin_session_id for row in rows if row.source_admin_session_id]
    admin_email_by_session_id = {}
    if admin_session_ids:
        admin_rows = session.scalars(
            select(TeamAdminSessionModel).where(TeamAdminSessionModel.id.in_(admin_session_ids))
        ).all()
        admin_email_by_session_id = {row.id: row.admin_email for row in admin_rows}
    return [
        _workspace_dict(
            row,
            admin_email=admin_email_by_session_id.get(row.source_admin_session_id, ""),
        )
        for row in rows
    ]


@router.post("/team-workspaces/import")
def import_team_workspace(
    req: ImportTeamWorkspaceRequest,
    session: DbSession,
) -> dict:
    now = datetime.now(UTC)
    workspace = session.scalars(
        select(TeamWorkspaceModel).where(
            TeamWorkspaceModel.provider == req.provider,
            TeamWorkspaceModel.external_workspace_id == req.external_workspace_id,
        )
    ).first()
    if workspace is None:
        workspace = TeamWorkspaceModel(
            id=f"team-workspace-{uuid4()}",
            provider=req.provider,
            external_workspace_id=req.external_workspace_id,
            name=req.name,
            plan_type=req.plan_type,
            seat_limit=req.seat_limit,
            seats_entitled=req.seat_limit,
            seats_in_use=0,
            workspace_status=req.workspace_status,
            created_at=now,
            updated_at=now,
        )
        session.add(workspace)
    else:
        workspace.name = req.name
        workspace.plan_type = req.plan_type
        workspace.seat_limit = req.seat_limit
        workspace.seats_entitled = req.seat_limit
        workspace.workspace_status = req.workspace_status
        workspace.updated_at = now
    if workspace.workspace_status == "active":
        _ensure_workspace_automation_state(session=session, workspace_id=workspace.id)
    session.commit()
    return {"team_workspace_id": workspace.id}


@router.get("/team-workspaces/{team_workspace_id}")
def get_team_workspace(team_workspace_id: str, session: DbSession) -> dict:
    workspace = session.get(TeamWorkspaceModel, team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    admin_email = ""
    if workspace.source_admin_session_id:
        admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
        admin_email = admin_session.admin_email if admin_session is not None else ""
    return _workspace_dict(workspace, admin_email=admin_email)


@router.post("/team-workspaces/{team_workspace_id}/remove-members")
def remove_team_workspace_members(
    team_workspace_id: str,
    req: RemoveWorkspaceMembersRequest,
    session: DbSession,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    if not workspace.source_admin_session_id:
        raise HTTPException(status_code=400, detail="workspace missing source admin session")
    admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
    if admin_session is None:
        raise HTTPException(status_code=404, detail="team admin session not found")
    if not admin_session.access_token:
        raise HTTPException(status_code=400, detail="team admin session missing access_token")
    if not req.confirm_remove:
        raise HTTPException(status_code=400, detail="confirm_remove must be true")

    page_size = max(1, min(int(req.page_size or 100), 200))
    concurrency = max(1, min(int(req.concurrency or 20), 50))
    account_id = workspace.external_workspace_id
    self_ids = _workspace_self_user_ids(
        session=session,
        team_admin_session_id=admin_session.id,
        account_id=account_id,
    )
    members = _fetch_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=account_id,
        page_size=page_size,
    )
    targets, skipped = _split_removable_workspace_members(members, self_ids=self_ids)
    results = _delete_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=account_id,
        members=targets,
        concurrency=concurrency,
    )
    removed_count = sum(1 for item in results if item.get("ok") is True)
    failed_count = sum(1 for item in results if item.get("ok") is not True)
    return {
        "team_workspace_id": workspace.id,
        "external_workspace_id": account_id,
        "workspace_name": workspace.name,
        "admin_email": admin_session.admin_email,
        "total_members": len(members),
        "target_count": len(targets),
        "skipped_count": len(skipped),
        "removed_count": removed_count,
        "failed_count": failed_count,
        "skipped": skipped,
        "results": results,
    }


@router.post("/team-workspaces/{team_workspace_id}/revoke-invite")
def revoke_team_workspace_invite(
    team_workspace_id: str,
    req: RevokeWorkspaceInviteRequest,
    session: DbSession,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    if not workspace.source_admin_session_id:
        raise HTTPException(status_code=400, detail="workspace missing source admin session")
    admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
    if admin_session is None:
        raise HTTPException(status_code=404, detail="team admin session not found")
    if not admin_session.access_token:
        raise HTTPException(status_code=400, detail="team admin session missing access_token")

    page_size = max(1, min(int(req.page_size or 100), 200))
    concurrency = max(1, min(int(req.concurrency or 20), 50))
    invites = _fetch_workspace_invites(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=page_size,
    )
    results = _revoke_workspace_invites(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        invites=invites,
        concurrency=concurrency,
    )
    revoked_count = sum(1 for item in results if item.get("ok") is True)
    failed_count = sum(1 for item in results if item.get("ok") is not True)
    return {
        "team_workspace_id": workspace.id,
        "external_workspace_id": workspace.external_workspace_id,
        "workspace_name": workspace.name,
        "admin_email": admin_session.admin_email,
        "invite_count": len(invites),
        "revoked_count": revoked_count,
        "failed_count": failed_count,
        "results": results,
    }


@router.get("/memberships")
def list_memberships(
    session: DbSession,
    admin_email: str = "",
    external_workspace_id: str = "",
    user_email: str = "",
    workspace: str = "",
    membership_status: str = "",
    has_codex_credential: str = "",
    session_otp_status: str = "",
) -> list[dict]:
    credential_exists = (
        exists()
        .where(CodexOAuthCredentialModel.user_account_id == MembershipModel.user_account_id)
        .where(CodexOAuthCredentialModel.team_workspace_id == MembershipModel.team_workspace_id)
    )
    stmt = (
        select(
            MembershipModel,
            UserAccountModel,
            TeamWorkspaceModel,
            TeamAdminSessionModel,
            AccountSessionOtpSnapshotModel,
            credential_exists.label("has_codex_credential"),
        )
        .join(UserAccountModel, UserAccountModel.id == MembershipModel.user_account_id)
        .join(TeamWorkspaceModel, TeamWorkspaceModel.id == MembershipModel.team_workspace_id)
        .outerjoin(
            TeamAdminSessionModel,
            TeamAdminSessionModel.id == TeamWorkspaceModel.source_admin_session_id,
        )
        .outerjoin(
            AccountSessionOtpSnapshotModel,
            AccountSessionOtpSnapshotModel.user_account_id == MembershipModel.user_account_id,
        )
        .order_by(MembershipModel.created_at.desc())
    )
    if admin_email:
        stmt = stmt.where(TeamAdminSessionModel.admin_email.ilike(f"%{admin_email.strip()}%"))
    if external_workspace_id:
        stmt = stmt.where(
            TeamWorkspaceModel.external_workspace_id.ilike(f"%{external_workspace_id.strip()}%")
        )
    if user_email:
        stmt = stmt.where(UserAccountModel.email.ilike(f"%{user_email.strip()}%"))
    if workspace:
        value = f"%{workspace.strip()}%"
        stmt = stmt.where(
            (TeamWorkspaceModel.name.ilike(value))
            | (TeamWorkspaceModel.id.ilike(value))
            | (TeamWorkspaceModel.external_workspace_id.ilike(value))
        )
    if membership_status:
        stmt = stmt.where(MembershipModel.membership_status == membership_status.strip())
    if has_codex_credential in {"yes", "no"}:
        stmt = stmt.where(credential_exists if has_codex_credential == "yes" else ~credential_exists)
    if session_otp_status:
        stmt = stmt.where(AccountSessionOtpSnapshotModel.snapshot_status == session_otp_status.strip())
    rows = session.execute(stmt).all()
    return [
        {
            "id": membership.id,
            "user_account_id": membership.user_account_id,
            "user_email": account.email,
            "team_workspace_id": membership.team_workspace_id,
            "external_workspace_id": workspace.external_workspace_id,
            "workspace_name": workspace.name,
            "workspace_plan_type": workspace.plan_type,
            "admin_email": admin_session.admin_email if admin_session is not None else "",
            "membership_status": membership.membership_status,
            "has_codex_credential": bool(has_codex_credential),
            "session_otp_status": otp_snapshot.snapshot_status if otp_snapshot is not None else "",
            "session_otp_code_len": otp_snapshot.otp_code_len if otp_snapshot is not None else 0,
            "can_invite": membership.can_invite,
            "failure_code": membership.failure_code,
            "failure_message": membership.failure_message,
        }
        for membership, account, workspace, admin_session, otp_snapshot, has_codex_credential in rows
    ]


@router.post("/memberships/probe-job")
def create_membership_probe_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "membership.probe", input_json)


@router.post("/memberships/invite-member-job")
def create_membership_invite_member_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    if input_json.get("user_account_ids"):
        req = InviteSelectedUsersRequest(**input_json)
        return _create_invite_work_job(req=req, session=session)
    return _enqueue(session, "membership.invite_member", input_json)


@router.post("/memberships/accept-invite-job")
def create_membership_accept_invite_job(
    req: AcceptMembershipInvitesRequest,
    session: DbSession,
) -> dict:
    return _create_accept_invite_work_job(req=req, session=session)


@router.post("/memberships/session-otp-prepare-job")
def create_membership_session_otp_prepare_job(
    req: SessionOtpMembershipRequest,
    session: DbSession,
) -> dict:
    return _create_session_otp_work_job(req=req, session=session, phase="prepare")


@router.post("/memberships/session-otp-submit-job")
def create_membership_session_otp_submit_job(
    req: SessionOtpMembershipRequest,
    session: DbSession,
) -> dict:
    return _create_session_otp_work_job(req=req, session=session, phase="submit")


@router.post("/memberships/sync-remote-state")
def sync_memberships_remote_state(
    req: SyncWorkspaceMembersRequest,
    session: DbSession,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, req.team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    if not workspace.source_admin_session_id:
        raise HTTPException(status_code=400, detail="workspace missing source admin session")
    admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
    if admin_session is None:
        raise HTTPException(status_code=404, detail="team admin session not found")
    if not admin_session.access_token:
        raise HTTPException(status_code=400, detail="team admin session missing access_token")

    page_size = max(1, min(int(req.page_size or 100), 200))
    remote_members = _fetch_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=page_size,
    )
    remote_invites = _fetch_workspace_invites(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=page_size,
    )
    result = _prune_workspace_memberships_by_remote_state(
        session=session,
        workspace=workspace,
        remote_members=remote_members,
        remote_invites=remote_invites,
    )
    session.commit()
    return {
        "team_workspace_id": workspace.id,
        "external_workspace_id": workspace.external_workspace_id,
        "workspace_name": workspace.name,
        "admin_email": admin_session.admin_email,
        "remote_member_count": len(remote_members),
        "remote_invite_count": len(remote_invites),
        **result,
    }


@router.post("/automation/workspace-fill-job")
def create_workspace_fill_automation_job(
    req: WorkspaceAutomationFillRequest,
    session: DbSession,
) -> dict:
    job = JobQueue(session).enqueue(
        job_type="automation.workspace_fill",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    run.output_json = {
        "stage": "queued",
        "message": "automation workspace fill accepted; background runner starting",
        "team_workspace_id": req.team_workspace_id,
        "selected_account_count": len(req.user_account_ids),
        "post_invite_wait_seconds": req.post_invite_wait_seconds,
    }
    session.commit()
    session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    Thread(
        target=_run_workspace_fill_automation_background,
        kwargs={
            "req": req,
            "session_factory": session_factory,
            "job_id": job.id,
            "run_id": run.id,
        },
        daemon=True,
    ).start()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": "running",
        "run_id": run.id if run is not None else "",
        "stage": "queued",
        "message": "automation workspace fill is running in background",
    }


@router.post("/automation/downstream-usage-sweep-job")
def create_downstream_usage_sweep_job(
    req: DownstreamUsageSweepRequest,
    session: DbSession,
) -> dict:
    job = JobQueue(session).enqueue(
        job_type="automation.downstream_usage_sweep",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    try:
        output = _run_downstream_usage_sweep(req=req, session=session)
    except Exception as exc:
        finished_at = datetime.now(UTC)
        job.job_status = "failed"
        job.updated_at = finished_at
        run.run_status = "failed"
        run.finished_at = finished_at
        run.error_code = type(exc).__name__[:200]
        run.error_message = str(exc)[:1000]
        session.commit()
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    finished_at = datetime.now(UTC)
    job.job_status = "succeeded"
    job.updated_at = finished_at
    run.run_status = "succeeded"
    run.finished_at = finished_at
    run.output_json = output
    session.commit()
    return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


@router.post("/automation/workspace-invite-sync-job")
def create_workspace_invite_sync_job(
    req: AutomationWorkspaceInviteSyncRequest,
    session: DbSession,
) -> dict:
    job, run = _create_running_job_run(
        session=session,
        job_type="automation.workspace_invite_sync",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    session_factory = _session_factory_from(session)
    output = _finish_running_job(
        session=session,
        job=job,
        run=run,
        runner=lambda: _run_workspace_invite_sync_tick(
            req=req,
            session_factory=session_factory,
            job_id=job.id,
            run_id=run.id,
        ),
    )
    return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


@router.post("/automation/workspace-authorize-job")
def create_workspace_authorize_job(
    req: AutomationWorkspaceAuthorizeRequest,
    session: DbSession,
) -> dict:
    job, run = _create_running_job_run(
        session=session,
        job_type="automation.workspace_authorize",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    session_factory = _session_factory_from(session)
    output = _finish_running_job(
        session=session,
        job=job,
        run=run,
        runner=lambda: _run_workspace_authorize_tick(
            req=req,
            session_factory=session_factory,
            job_id=job.id,
        ),
    )
    return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


@router.post("/automation/downstream-push-job")
def create_downstream_push_job(
    req: AutomationDownstreamPushRequest,
    session: DbSession,
) -> dict:
    job, run = _create_running_job_run(
        session=session,
        job_type="automation.downstream_push",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    session_factory = _session_factory_from(session)
    output = _finish_running_job(
        session=session,
        job=job,
        run=run,
        runner=lambda: _run_downstream_push_tick(
            req=req,
            session_factory=session_factory,
            job_id=job.id,
            run_id=run.id,
        ),
    )
    return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


@router.post("/automation/codex-heartbeat-job")
def create_codex_heartbeat_automation_job(
    req: AutomationCodexHeartbeatRequest,
    session: DbSession,
) -> dict:
    job, run = _create_running_job_run(
        session=session,
        job_type="automation.codex_heartbeat",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    session_factory = _session_factory_from(session)
    output = _finish_running_job(
        session=session,
        job=job,
        run=run,
        runner=lambda: _run_codex_heartbeat_tick(
            req=req,
            session_factory=session_factory,
        ),
    )
    return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


@router.post("/automation/downstream-usage-cleanup-job")
def create_downstream_usage_cleanup_job(
    req: AutomationDownstreamUsageCleanupRequest,
    session: DbSession,
) -> dict:
    job, run = _create_running_job_run(
        session=session,
        job_type="automation.downstream_usage_cleanup",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    session_factory = _session_factory_from(session)
    output = _finish_running_job(
        session=session,
        job=job,
        run=run,
        runner=lambda: _run_downstream_usage_cleanup_tick(
            req=req,
            session_factory=session_factory,
        ),
    )
    return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


@router.get("/automation/schedules")
def list_automation_schedules(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(AutomationScheduleModel).order_by(
            AutomationScheduleModel.schedule_type.asc(),
            AutomationScheduleModel.created_at.asc(),
        )
    ).all()
    return [_automation_schedule_dict(row) for row in rows]


@router.get("/automation/monitor/jobs")
def get_automation_monitor_jobs(session: DbSession) -> dict:
    schedules = session.scalars(
        select(AutomationScheduleModel).order_by(
            AutomationScheduleModel.schedule_type.asc(),
            AutomationScheduleModel.created_at.asc(),
        )
    ).all()
    return {"items": [_automation_monitor_job_dict(session=session, schedule=row) for row in schedules]}


@router.get("/automation/monitor/job-console")
def get_automation_monitor_job_console(
    session: DbSession,
    schedule_type: str = "",
    job_id: str = "",
    run_id: str = "",
    level: str = "",
    limit: int = 1000,
    max_bytes: int = 524288,
) -> dict:
    safe_limit = max(1, min(int(limit or 1000), 5000))
    safe_max_bytes = max(4096, min(int(max_bytes or 524288), 2 * 1024 * 1024))
    stmt = select(JobEventModel, JobRunModel, JobModel).join(
        JobRunModel,
        JobRunModel.id == JobEventModel.run_id,
    ).join(
        JobModel,
        JobModel.id == JobRunModel.job_id,
    )
    if run_id.strip():
        stmt = stmt.where(JobEventModel.run_id == run_id.strip())
    if job_id.strip():
        stmt = stmt.where(JobModel.id == job_id.strip())
    if schedule_type.strip():
        stmt = stmt.where(JobModel.type == schedule_type.strip())
    if level.strip() and level.strip().upper() != "ALL":
        stmt = stmt.where(JobEventModel.level == level.strip().upper())
    rows = session.execute(stmt.order_by(JobEventModel.ts.desc()).limit(safe_limit)).all()
    items = [
        _automation_console_event_dict(event=event, run=run, job=job)
        for event, run, job in reversed(rows)
    ]
    if not items:
        items = _automation_console_fallback_items(
            session=session,
            schedule_type=schedule_type,
            job_id=job_id,
            run_id=run_id,
            level=level,
            limit=safe_limit,
        )
    limited_items, returned_bytes, truncated = _limit_console_items_by_bytes(
        items=items,
        max_bytes=safe_max_bytes,
    )
    return {
        "items": limited_items,
        "truncated": truncated,
        "returned_count": len(limited_items),
        "returned_bytes": returned_bytes,
        "max_bytes": safe_max_bytes,
        "limit": safe_limit,
    }


@router.post("/automation/monitor/downstream-usage-probe")
def probe_monitor_downstream_usage(
    req: MonitorDownstreamUsageProbeRequest,
    session: DbSession,
) -> dict:
    return _run_monitor_downstream_usage_probe(req=req, session=session)


@router.get("/automation/monitor/downstream-usage")
def list_monitor_downstream_usage(
    session: DbSession,
    downstream_channel_id: str = "",
    usage_status: str = "",
    provider_type: str = "",
    q: str = "",
    limit: int = 500,
) -> dict:
    stmt = select(DownstreamCodexPushRecordModel).where(
        DownstreamCodexPushRecordModel.push_status == "pushed",
    )
    if downstream_channel_id.strip():
        stmt = stmt.where(DownstreamCodexPushRecordModel.downstream_channel_id == downstream_channel_id.strip())
    if usage_status.strip():
        stmt = stmt.where(DownstreamCodexPushRecordModel.usage_status == usage_status.strip())
    if provider_type.strip():
        stmt = stmt.where(DownstreamCodexPushRecordModel.downstream_provider == provider_type.strip())
    rows = session.scalars(
        stmt.order_by(DownstreamCodexPushRecordModel.updated_at.desc()).limit(
            max(1, min(int(limit or 500), 2000))
        )
    ).all()
    items = [_monitor_usage_record_dict(session=session, record=row) for row in rows]
    query = q.strip().lower()
    if query:
        items = [
            item for item in items
            if query in " ".join(str(item.get(key) or "").lower() for key in (
                "id",
                "codex_credential_id",
                "user_account_id",
                "email",
                "team_workspace_id",
                "workspace_name",
                "external_workspace_id",
                "downstream_channel_name",
                "error_code",
            ))
        ]
    return {
        "summary": _monitor_usage_summary(items),
        "items": items,
    }


@router.post("/automation/schedules")
def create_automation_schedule(
    req: CreateAutomationScheduleRequest,
    session: DbSession,
) -> dict:
    now = datetime.now(UTC)
    row = session.scalars(
        select(AutomationScheduleModel)
        .where(AutomationScheduleModel.schedule_type == req.schedule_type)
        .limit(1)
    ).first()
    if row is None:
        row = AutomationScheduleModel(
            id=_fixed_automation_schedule_id(req.schedule_type),
            schedule_type=req.schedule_type,
            created_by=req.created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    row.schedule_status = "active" if req.enabled else "paused"
    row.enabled = req.enabled
    row.interval_seconds = max(5, int(req.interval_seconds or 60))
    row.config_json = req.config_json
    row.next_run_at = now
    row.last_error_code = ""
    row.last_error_message = ""
    row.updated_at = now
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _automation_schedule_dict(row)


@router.patch("/automation/schedules/{schedule_id}")
def patch_automation_schedule(
    schedule_id: str,
    req: PatchAutomationScheduleRequest,
    session: DbSession,
) -> dict:
    row = session.get(AutomationScheduleModel, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="automation schedule not found")
    if req.enabled is not None:
        row.enabled = req.enabled
        row.schedule_status = "active" if req.enabled else "paused"
    if req.schedule_status is not None:
        row.schedule_status = req.schedule_status
        row.enabled = req.schedule_status == "active"
    if req.interval_seconds is not None:
        row.interval_seconds = max(5, int(req.interval_seconds or 60))
    if req.config_json is not None:
        row.config_json = req.config_json
    row.next_run_at = datetime.now(UTC)
    row.last_error_code = ""
    row.last_error_message = ""
    row.updated_at = datetime.now(UTC)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _automation_schedule_dict(row)


@router.post("/automation/schedules/{schedule_id}/run-now")
def run_automation_schedule_now(schedule_id: str, session: DbSession) -> dict:
    row = session.get(AutomationScheduleModel, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="automation schedule not found")
    session_factory = _session_factory_from(session)
    locked_by = f"manual-{uuid4()}"
    result = _execute_automation_schedule(
        schedule_id=schedule_id,
        session_factory=session_factory,
        locked_by=locked_by,
        update_next_run=False,
        acquire_lock=True,
    )
    return {"schedule": _automation_schedule_dict(session.get(AutomationScheduleModel, schedule_id)), **result}


def _run_workspace_fill_automation(
    *,
    req: WorkspaceAutomationFillRequest,
    session: Session,
    parent_job_id: str,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, req.team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    user_account_ids = [item.strip() for item in req.user_account_ids if item.strip()]
    if not user_account_ids:
        raise HTTPException(status_code=400, detail="user_account_ids is required")
    active_user_account_ids = _exclude_workspace_cooldown_accounts(
        session=session,
        workspace_id=workspace.id,
        user_account_ids=user_account_ids,
    )
    skipped_cooldown_count = len(user_account_ids) - len(active_user_account_ids)
    if not active_user_account_ids:
        raise HTTPException(status_code=400, detail="all selected accounts are in cooldown")

    invite_summary = _create_invite_work_job(
        req=InviteSelectedUsersRequest(
            team_workspace_id=workspace.id,
            user_account_ids=active_user_account_ids,
            team_admin_session_id=req.team_admin_session_id,
            created_by=req.created_by or "automation.workspace_fill",
            concurrency=req.invite_concurrency,
        ),
        session=session,
    )
    _update_automation_run_output(
        session=session,
        job_id=parent_job_id,
        run_id=_automation_run_id(session=session, job_id=parent_job_id),
        patch={
            "stage": "post_invite_wait",
            "invite_job": invite_summary,
            "skipped_cooldown_count": skipped_cooldown_count,
            "selected_account_count": len(user_account_ids),
            "active_account_count": len(active_user_account_ids),
            "next_wait_seconds": max(0, int(req.post_invite_wait_seconds or 0)),
        },
    )
    wait_seconds = max(0, int(req.post_invite_wait_seconds or 0))
    if wait_seconds:
        sleep(wait_seconds)
    sync_after_invite = _sync_workspace_remote_state_inline(
        session=session,
        workspace_id=workspace.id,
        page_size=req.sync_page_size,
    )
    _update_automation_run_output(
        session=session,
        job_id=parent_job_id,
        run_id=_automation_run_id(session=session, job_id=parent_job_id),
        patch={
            "stage": "sync_after_invite_done",
            "invite_job": invite_summary,
            "sync_after_invite": sync_after_invite,
        },
    )

    lock_acquired = _acquire_workspace_operation_lock(
        session=session,
        workspace_id=workspace.id,
        lock_type="codex_fill",
        locked_by=parent_job_id,
        ttl_seconds=req.lock_ttl_seconds,
    )
    if not lock_acquired:
        raise HTTPException(status_code=409, detail="workspace codex_fill lock is held")
    authorized_credential_id = ""
    selected_user_account_id = ""
    fill_errors: list[dict[str, str]] = []
    try:
        workspace = session.get(TeamWorkspaceModel, workspace.id)
        if workspace is not None:
            remote_state = _sync_workspace_remote_state_inline(
                session=session,
                workspace_id=workspace.id,
                page_size=req.sync_page_size,
            )
            purchased_seats = int(workspace.seats_entitled or workspace.seat_limit or 0)
            remote_default_seat_count = int(remote_state.get("remote_default_seat_count") or 0)
            if purchased_seats <= 0 or remote_default_seat_count < purchased_seats:
                selected_user_account_id = _random_workspace_authorization_candidate(
                    session=session,
                    workspace_id=workspace.id,
                )
                if selected_user_account_id:
                    session.commit()
                    _update_automation_run_output(
                        session=session,
                        job_id=parent_job_id,
                        run_id=_automation_run_id(session=session, job_id=parent_job_id),
                        patch={
                            "stage": "codex_authorizing",
                            "current_user_account_id": selected_user_account_id,
                            "authorized_credential_count": 0,
                            "fill_error_count": 0,
                        },
                    )
                    try:
                        authorized_credential_id = BuildCodexCredentialWorkItemWorkflow(
                            session_factory=sessionmaker(
                                bind=session.get_bind(),
                                autoflush=False,
                                expire_on_commit=False,
                            ),
                            openai_provider=_openai_provider(),
                            mail_provider=_mail_provider(),
                        ).run(
                            BuildCodexCredentialWorkInput(
                                user_account_id=selected_user_account_id,
                                team_workspace_id=workspace.id,
                                codex_client_id=req.codex_client_id,
                                force_reauthorize=False,
                            )
                        )
                    except Exception as exc:
                        fill_errors.append(
                            {
                                "user_account_id": selected_user_account_id,
                                "error": f"{type(exc).__name__}: {exc}"[:1000],
                            }
                        )
                        _mark_candidate_authorization_failed(
                            session=session,
                            workspace_id=workspace.id,
                            user_account_id=selected_user_account_id,
                            error=str(exc),
                        )
                    else:
                        _mark_credential_pending_push(
                            session=session,
                            credential_id=authorized_credential_id,
                        )
                        session.commit()
                        _update_automation_run_output(
                            session=session,
                            job_id=parent_job_id,
                            run_id=_automation_run_id(session=session, job_id=parent_job_id),
                            patch={
                                "stage": "codex_authorized",
                                "selected_user_account_id": selected_user_account_id,
                                "authorized_credential_count": 1,
                                "authorized_credential_id": authorized_credential_id,
                                "authorized_credential_ids": [authorized_credential_id],
                                "fill_error_count": 0,
                                "fill_errors": [],
                            },
                        )
    finally:
        _release_workspace_operation_lock(
            session=session,
            workspace_id=req.team_workspace_id,
            lock_type="codex_fill",
            locked_by=parent_job_id,
        )
        session.commit()

    final_sync = _sync_workspace_remote_state_inline(
        session=session,
        workspace_id=req.team_workspace_id,
        page_size=req.sync_page_size,
    )
    session.commit()
    return {
        "team_workspace_id": req.team_workspace_id,
        "selected_account_count": len(user_account_ids),
        "skipped_cooldown_count": skipped_cooldown_count,
        "invite_job": invite_summary,
        "sync_after_invite": sync_after_invite,
        "selected_user_account_id": selected_user_account_id,
        "authorized_credential_count": 1 if authorized_credential_id else 0,
        "authorized_credential_id": authorized_credential_id,
        "authorized_credential_ids": [authorized_credential_id] if authorized_credential_id else [],
        "fill_error_count": len(fill_errors),
        "fill_errors": fill_errors,
        "final_sync": final_sync,
    }


def _run_workspace_fill_automation_background(
    *,
    req: WorkspaceAutomationFillRequest,
    session_factory,
    job_id: str,
    run_id: str,
) -> None:
    with session_factory() as session:
        try:
            _update_automation_run_output(
                session=session,
                job_id=job_id,
                run_id=run_id,
                patch={
                    "stage": "running",
                    "message": "automation started",
                    "team_workspace_id": req.team_workspace_id,
                    "selected_account_count": len(req.user_account_ids),
                },
            )
            output = _run_workspace_fill_automation(req=req, session=session, parent_job_id=job_id)
        except Exception as exc:
            finished_at = datetime.now(UTC)
            job = session.get(JobModel, job_id)
            run = session.get(JobRunModel, run_id)
            if job is not None:
                job.job_status = "failed"
                job.updated_at = finished_at
            if run is not None:
                run.run_status = "failed"
                run.finished_at = finished_at
                run.error_code = type(exc).__name__[:200]
                run.error_message = str(exc)[:1000]
                run.output_json = {
                    **(run.output_json or {}),
                    "stage": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            session.commit()
            return

        finished_at = datetime.now(UTC)
        job = session.get(JobModel, job_id)
        run = session.get(JobRunModel, run_id)
        if job is not None:
            job.job_status = "succeeded"
            job.updated_at = finished_at
        if run is not None:
            run.run_status = "succeeded"
            run.finished_at = finished_at
            run.output_json = {**(run.output_json or {}), **output, "stage": "succeeded"}
        session.commit()


def _update_automation_run_output(
    *,
    session: Session,
    job_id: str,
    run_id: str,
    patch: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    job = session.get(JobModel, job_id)
    run = session.get(JobRunModel, run_id)
    if job is not None:
        job.updated_at = now
    if run is not None:
        run.output_json = {**(run.output_json or {}), **patch, "updated_at": now.isoformat()}
    session.commit()


def _automation_run_id(*, session: Session, job_id: str) -> str:
    run = session.scalars(
        select(JobRunModel)
        .where(JobRunModel.job_id == job_id)
        .order_by(JobRunModel.started_at.desc())
        .limit(1)
    ).first()
    return run.id if run is not None else ""


def _run_downstream_usage_sweep(
    *,
    req: DownstreamUsageSweepRequest,
    session: Session,
) -> dict:
    now = datetime.now(UTC)
    threshold = max(1, min(int(req.threshold_percent or 95), 100))
    session_factory = _session_factory_from(session)
    stmt = select(DownstreamCodexPushRecordModel).where(
        DownstreamCodexPushRecordModel.push_status == "pushed"
    )
    if req.downstream_channel_id.strip():
        stmt = stmt.where(
            DownstreamCodexPushRecordModel.downstream_channel_id
            == req.downstream_channel_id.strip()
        )
    records = session.scalars(stmt.order_by(DownstreamCodexPushRecordModel.updated_at.asc())).all()
    checked_count = 0
    near_limit_count = 0
    failed_count = 0
    for record in records:
        probe = _probe_downstream_record_usage_with_recovery(
            session=session,
            session_factory=session_factory,
            record=record,
            threshold=threshold,
        )
        if not probe.ok:
            failed_count += 1
            checked_count += 1
            continue
        usage_percent = probe.usage_percent
        if usage_percent >= threshold:
            near_limit_count += 1
            remove_result = _mark_downstream_record_used_and_cooldown(
                session=session,
                record=record,
                now=datetime.now(UTC),
                reason=f"usage_percent>={threshold}",
            )
            if not remove_result.get("ok"):
                near_limit_count -= 1
        else:
            record.usage_status = "active"
            record.updated_at = datetime.now(UTC)
        checked_count += 1
    session.commit()
    return {
        "checked_count": checked_count,
        "near_limit_count": near_limit_count,
        "failed_count": failed_count,
        "threshold_percent": threshold,
        "usage_source": "chatgpt_codex_response_headers",
    }


def _run_monitor_downstream_usage_probe(
    *,
    req: MonitorDownstreamUsageProbeRequest,
    session: Session,
) -> dict:
    threshold = max(1, min(int(req.threshold_percent or 95), 100))
    requested_ids = [item.strip() for item in req.downstream_push_record_ids if item.strip()]
    stmt = select(DownstreamCodexPushRecordModel.id).where(
        DownstreamCodexPushRecordModel.push_status == "pushed",
    )
    if requested_ids:
        stmt = stmt.where(DownstreamCodexPushRecordModel.id.in_(requested_ids))
    if req.downstream_channel_id.strip():
        stmt = stmt.where(
            DownstreamCodexPushRecordModel.downstream_channel_id == req.downstream_channel_id.strip()
        )
    record_ids = [
        str(item)
        for item in session.scalars(
            stmt.order_by(DownstreamCodexPushRecordModel.updated_at.asc()).limit(
                max(1, min(int(req.limit or 100), 1000))
            )
        ).all()
    ]
    session_factory = _session_factory_from(session)
    concurrency = _bounded_concurrency(req.concurrency)
    items = _parallel_map(
        items=record_ids,
        max_workers=concurrency,
        fn=lambda record_id: _probe_monitor_downstream_usage_record(
            session_factory=session_factory,
            record_id=record_id,
            threshold=threshold,
            persist_result=req.persist_result,
        ),
    )
    return {
        "checked": len(items),
        "succeeded": sum(1 for item in items if item.get("probe_ok")),
        "failed": sum(1 for item in items if not item.get("probe_ok")),
        "threshold_percent": threshold,
        "concurrency": concurrency,
        "persist_result": req.persist_result,
        "items": items,
    }


def _probe_monitor_downstream_usage_record(
    *,
    session_factory,
    record_id: str,
    threshold: int,
    persist_result: bool,
) -> dict:
    with session_factory() as session:
        record = session.get(DownstreamCodexPushRecordModel, record_id)
        if record is None or record.push_status != "pushed":
            return {
                "id": record_id,
                "probe_ok": False,
                "probe_error_code": "record_not_pushed",
                "probe_error_message": "downstream push record not found or not pushed",
            }
        probe = _probe_downstream_record_usage(session=session, record=record)
        if persist_result:
            if probe.ok:
                _apply_usage_probe_success(
                    record=record,
                    result=probe,
                    threshold=threshold,
                    now=datetime.now(UTC),
                )
            else:
                _apply_usage_probe_failure(
                    record=record,
                    result=probe,
                    now=datetime.now(UTC),
                )
            session.commit()
            session.refresh(record)
        item = _monitor_usage_record_dict(session=session, record=record)
        item.update(
            {
                "probe_ok": probe.ok,
                "probe_error_code": probe.error_code,
                "probe_error_message": probe.error_message,
                "raw_headers": probe.raw_headers,
            }
        )
        return item


def _monitor_usage_record_dict(*, session: Session, record: DownstreamCodexPushRecordModel) -> dict:
    channel = session.get(DownstreamChannelModel, record.downstream_channel_id) if record.downstream_channel_id else None
    user = session.get(UserAccountModel, record.user_account_id)
    workspace = session.get(TeamWorkspaceModel, record.team_workspace_id)
    return {
        "id": record.id,
        "codex_credential_id": record.codex_credential_id,
        "user_account_id": record.user_account_id,
        "email": user.email if user is not None else "",
        "team_workspace_id": record.team_workspace_id,
        "workspace_name": workspace.name if workspace is not None else "",
        "external_workspace_id": workspace.external_workspace_id if workspace is not None else "",
        "downstream_channel_id": record.downstream_channel_id,
        "downstream_channel_name": channel.name if channel is not None else "",
        "downstream_provider": record.downstream_provider,
        "push_status": record.push_status,
        "usage_percent": record.usage_percent,
        "usage_status": record.usage_status,
        "last_usage_check_at": record.last_usage_check_at.isoformat() if record.last_usage_check_at else "",
        "downstream_chatgpt_account_id": record.downstream_chatgpt_account_id,
        "token_chatgpt_account_id": record.token_chatgpt_account_id,
        "push_attempt_count": record.push_attempt_count,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _monitor_usage_summary(items: list[dict]) -> dict:
    return {
        "total": len(items),
        "active": sum(1 for item in items if item.get("usage_status") == "active"),
        "near_limit": sum(1 for item in items if item.get("usage_status") == "near_limit"),
        "check_failed": sum(1 for item in items if item.get("usage_status") == "check_failed"),
        "unknown": sum(1 for item in items if item.get("usage_status") == "unknown"),
        "used": sum(1 for item in items if item.get("usage_status") == "used"),
        "below_80": sum(1 for item in items if int(item.get("usage_percent") or 0) < 80),
        "between_80_94": sum(1 for item in items if 80 <= int(item.get("usage_percent") or 0) < 95),
        "gte_95": sum(1 for item in items if int(item.get("usage_percent") or 0) >= 95),
    }


def _probe_downstream_record_usage_with_recovery(
    *,
    session: Session,
    session_factory,
    record: DownstreamCodexPushRecordModel,
    threshold: int,
) -> CodexUsageProbeResult:
    now = datetime.now(UTC)
    result = _probe_downstream_record_usage(session=session, record=record)
    if result.ok:
        _apply_usage_probe_success(record=record, result=result, threshold=threshold, now=now)
        return result
    if not result.unauthorized:
        _apply_usage_probe_failure(record=record, result=result, now=now)
        return result

    refresh_result = _refresh_codex_credential_access_token(session=session, record=record)
    if not refresh_result.get("ok"):
        refresh_error_code = str(refresh_result.get("error_code") or "codex_token_refresh_failed")
        refresh_error_message = str(refresh_result.get("error_message") or "")
        if not _is_usage_refresh_unauthorized_error(refresh_error_code, refresh_error_message):
            failed = CodexUsageProbeResult(
                ok=False,
                error_code=refresh_error_code,
                error_message=refresh_error_message,
            )
            _apply_usage_probe_failure(record=record, result=failed, now=datetime.now(UTC))
            return failed
        session.commit()
        reauthorize_result = _reauthorize_codex_credential_for_record(
            session_factory=session_factory,
            record=record,
        )
        return _handle_usage_reauthorize_result(
            session=session,
            record=record,
            reauthorize_result=reauthorize_result,
            threshold=threshold,
            fallback_error_code="codex_token_refresh_unauthorized",
            fallback_error_message=refresh_error_message,
        )

    result = _probe_downstream_record_usage(session=session, record=record)
    if result.ok:
        _apply_usage_probe_success(
            record=record,
            result=result,
            threshold=threshold,
            now=datetime.now(UTC),
        )
        return result
    if not result.unauthorized:
        _apply_usage_probe_failure(record=record, result=result, now=datetime.now(UTC))
        return result

    session.commit()
    reauthorize_result = _reauthorize_codex_credential_for_record(
        session_factory=session_factory,
        record=record,
    )
    return _handle_usage_reauthorize_result(
        session=session,
        record=record,
        reauthorize_result=reauthorize_result,
        threshold=threshold,
        fallback_error_code="codex_reauthorize_failed",
        fallback_error_message="",
    )


def _is_usage_refresh_unauthorized_error(error_code: str, error_message: str) -> bool:
    text_value = f"{error_code} {error_message}".lower()
    return "401" in text_value or "unauthor" in text_value


def _handle_usage_reauthorize_result(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
    reauthorize_result: dict[str, Any],
    threshold: int,
    fallback_error_code: str,
    fallback_error_message: str,
) -> CodexUsageProbeResult:
    if not reauthorize_result.get("ok"):
        error_code = str(reauthorize_result.get("error_code") or fallback_error_code)
        error_message = str(reauthorize_result.get("error_message") or fallback_error_message)
        session.expire_all()
        refreshed_record = session.get(DownstreamCodexPushRecordModel, record.id)
        if refreshed_record is not None:
            cleanup_result = None
            if _is_phone_verification_required_error(error_message):
                cleanup_result = _handle_authorization_phone_verification_failed(
                    session=session,
                    workspace_id=refreshed_record.team_workspace_id,
                    user_account_id=refreshed_record.user_account_id,
                    error=error_message,
                    sync_after_seconds=5,
                )
                error_code = "codex_reauthorize_phone_verification_required"
                error_message = (
                    f"{error_message}; phone_verification_cleanup={cleanup_result}"
                )[:1000]
            failed = CodexUsageProbeResult(
                ok=False,
                error_code=error_code,
                error_message=error_message,
            )
            _apply_usage_probe_failure(
                record=refreshed_record,
                result=failed,
                now=datetime.now(UTC),
            )
            return failed
        failed = CodexUsageProbeResult(
            ok=False,
            error_code=error_code,
            error_message=error_message,
        )
        return failed

    session.expire_all()
    refreshed_record = session.get(DownstreamCodexPushRecordModel, record.id)
    if refreshed_record is None:
        return CodexUsageProbeResult(
            ok=False,
            error_code="push_record_missing_after_reauthorize",
            error_message="push record missing after codex reauthorize",
        )
    repush_result = _repush_downstream_record(session=session, record=refreshed_record)
    if not repush_result.get("ok"):
        failed = CodexUsageProbeResult(
            ok=False,
            error_code=str(repush_result.get("error_code") or "downstream_repush_failed"),
            error_message=str(repush_result.get("error_message") or ""),
        )
        _apply_usage_probe_failure(
            record=refreshed_record,
            result=failed,
            now=datetime.now(UTC),
        )
        return failed

    result = _probe_downstream_record_usage(session=session, record=refreshed_record)
    if result.ok:
        _apply_usage_probe_success(
            record=refreshed_record,
            result=result,
            threshold=threshold,
            now=datetime.now(UTC),
        )
    else:
        _apply_usage_probe_failure(
            record=refreshed_record,
            result=result,
            now=datetime.now(UTC),
        )
    return result


def _probe_downstream_record_usage(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
) -> CodexUsageProbeResult:
    credential = session.get(CodexOAuthCredentialModel, record.codex_credential_id)
    if credential is None:
        return CodexUsageProbeResult(
            ok=False,
            error_code="missing_codex_credential",
            error_message="codex credential not found",
        )
    if not credential.access_token:
        return CodexUsageProbeResult(
            ok=False,
            error_code="missing_access_token",
            error_message="codex credential access_token is empty",
            unauthorized=True,
        )
    if credential.token_chatgpt_account_id != record.token_chatgpt_account_id:
        return CodexUsageProbeResult(
            ok=False,
            error_code="workspace_mismatch",
            error_message=(
                "credential token_chatgpt_account_id does not match push record "
                f"expected={record.token_chatgpt_account_id} actual={credential.token_chatgpt_account_id}"
            )[:1000],
        )
    settings = get_settings()
    url = f"{settings.openai_chatgpt_base_url.rstrip('/')}{CODEX_RESPONSES_PATH}"
    headers = _codex_usage_probe_headers(
        access_token=credential.access_token,
        team_id=credential.token_chatgpt_account_id,
    )
    body = _codex_usage_probe_body()
    proxy = _active_proxy(session, credential.user_account_id)
    proxy_url = _proxy_url(proxy) if proxy is not None else ""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
    try:
        with curl_requests.Session(impersonate="chrome136", proxies=proxies) as client:
            response = client.post(
                url,
                headers=headers,
                json=body,
                timeout=15,
                stream=True,
            )
            raw_headers = _codex_usage_headers(response.headers)
            status_code = int(getattr(response, "status_code", 0) or 0)
            try:
                response.close()
            except Exception:
                pass
    except Exception as exc:
        return CodexUsageProbeResult(
            ok=False,
            error_code=type(exc).__name__[:200],
            error_message=str(exc)[:1000],
        )
    usage_percent = _codex_usage_percent_from_headers(raw_headers)
    if usage_percent is not None:
        return CodexUsageProbeResult(
            ok=True,
            usage_percent=usage_percent,
            raw_headers=raw_headers,
        )
    if status_code == 401:
        return CodexUsageProbeResult(
            ok=False,
            error_code="http_401",
            error_message="chatgpt codex usage probe returned 401",
            unauthorized=True,
            raw_headers=raw_headers,
        )
    if status_code < 200 or status_code >= 300:
        return CodexUsageProbeResult(
            ok=False,
            error_code=f"http_{status_code}",
            error_message="chatgpt codex usage probe returned non-2xx without usage headers",
            raw_headers=raw_headers,
        )
    return CodexUsageProbeResult(
        ok=False,
        error_code="usage_headers_missing",
        error_message="chatgpt codex response did not include x-codex usage headers",
        raw_headers=raw_headers,
    )


def _codex_usage_probe_headers(*, access_token: str, team_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Accept": "text/event-stream",
        "OpenAI-Beta": "responses=experimental",
        "Originator": "codex_cli_rs",
        "Version": CODEX_USAGE_PROBE_VERSION,
        "User-Agent": CODEX_USAGE_PROBE_USER_AGENT,
        "chatgpt-account-id": team_id,
    }


def _codex_usage_probe_body() -> dict[str, Any]:
    try:
        instructions = CODEX_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        instructions = ""
    return {
        "model": CODEX_USAGE_PROBE_MODEL,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            }
        ],
        "stream": True,
        "store": False,
        "instructions": instructions,
    }


def _codex_usage_headers(headers: Any) -> dict[str, str]:
    keys = (
        "x-codex-primary-used-percent",
        "x-codex-primary-reset-after-seconds",
        "x-codex-primary-window-minutes",
        "x-codex-secondary-used-percent",
        "x-codex-secondary-reset-after-seconds",
        "x-codex-secondary-window-minutes",
        "x-codex-primary-over-secondary-limit-percent",
    )
    return {key: str(headers.get(key) or "") for key in keys if str(headers.get(key) or "")}


def _codex_usage_percent_from_headers(headers: dict[str, str]) -> int | None:
    values: list[float] = []
    for key in (
        "x-codex-primary-used-percent",
        "x-codex-secondary-used-percent",
        "x-codex-primary-over-secondary-limit-percent",
    ):
        raw = headers.get(key)
        if not raw:
            continue
        try:
            values.append(float(str(raw).strip().rstrip("%")))
        except ValueError:
            continue
    if not values:
        return None
    return max(0, min(int(round(max(values))), 100))


def _apply_usage_probe_success(
    *,
    record: DownstreamCodexPushRecordModel,
    result: CodexUsageProbeResult,
    threshold: int,
    now: datetime,
) -> None:
    record.usage_percent = result.usage_percent
    record.usage_status = "near_limit" if result.usage_percent >= threshold else "active"
    record.last_usage_check_at = now
    record.error_code = ""
    record.error_message = ""
    record.updated_at = now


def _apply_usage_probe_failure(
    *,
    record: DownstreamCodexPushRecordModel,
    result: CodexUsageProbeResult,
    now: datetime,
) -> None:
    record.usage_status = "check_failed"
    record.last_usage_check_at = now
    record.error_code = (result.error_code or "usage_probe_failed")[:200]
    record.error_message = (result.error_message or "")[:1000]
    record.updated_at = now


def _refresh_codex_credential_access_token(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
) -> dict[str, Any]:
    credential = session.get(CodexOAuthCredentialModel, record.codex_credential_id)
    workspace = session.get(TeamWorkspaceModel, record.team_workspace_id)
    if credential is None:
        return {"ok": False, "error_code": "missing_codex_credential"}
    if workspace is None:
        return {"ok": False, "error_code": "missing_workspace"}
    if not credential.refresh_token:
        return {"ok": False, "error_code": "missing_refresh_token"}
    settings = get_settings()
    provider = OpenAIChatGPTPlugin.from_config(
        OpenAIChatGPTClientConfig(
            auth_base_url=settings.openai_auth_base_url,
            chatgpt_base_url=settings.openai_chatgpt_base_url,
            probe_path_template=settings.openai_probe_path_template,
        )
    )
    try:
        tokens = provider.refresh_workspace_token(
            refresh_token=credential.refresh_token,
            external_workspace_id=workspace.external_workspace_id,
            client_id=credential.codex_client_id,
        )
    except Exception as exc:
        credential.credential_status = CredentialStatus.ERROR.value
        credential.failure_code = type(exc).__name__[:200]
        credential.failure_message = str(exc)[:1000]
        credential.updated_at = datetime.now(UTC)
        return {
            "ok": False,
            "error_code": type(exc).__name__,
            "error_message": str(exc),
        }
    now = datetime.now(UTC)
    credential.access_token = tokens.access_token
    credential.id_token = tokens.id_token
    credential.refresh_token = tokens.refresh_token
    credential.expires_at = tokens.expires_at
    credential.last_refresh_at = now
    credential.credential_status = CredentialStatus.ACTIVE.value
    credential.failure_code = ""
    credential.failure_message = ""
    credential.updated_at = now
    record.codex_token_expires_at = tokens.expires_at
    record.token_chatgpt_account_id = tokens.claims.token_chatgpt_account_id
    record.updated_at = now
    return {"ok": True}


def _reauthorize_codex_credential_for_record(
    *,
    session_factory,
    record: DownstreamCodexPushRecordModel,
) -> dict[str, Any]:
    return _reauthorize_codex_credential(
        session_factory=session_factory,
        user_account_id=record.user_account_id,
        team_workspace_id=record.team_workspace_id,
        codex_client_id=record.codex_client_id,
    )


def _reauthorize_codex_credential(
    *,
    session_factory,
    user_account_id: str,
    team_workspace_id: str,
    codex_client_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    workflow = BuildCodexCredentialWorkItemWorkflow(
        session_factory=session_factory,
        openai_provider=OpenAIChatGPTPlugin.from_config(
            OpenAIChatGPTClientConfig(
                auth_base_url=settings.openai_auth_base_url,
                chatgpt_base_url=settings.openai_chatgpt_base_url,
                probe_path_template=settings.openai_probe_path_template,
            )
        ),
        mail_provider=ExternalMailApiPlugin.from_config(
            ExternalMailApiClientConfig(
                base_url=settings.external_mail_api_base_url,
                api_key=settings.external_mail_api_key,
                provider_name=settings.external_mail_provider_name,
            )
        ),
    )
    try:
        credential_id = workflow.run(
            BuildCodexCredentialWorkInput(
                user_account_id=user_account_id,
                team_workspace_id=team_workspace_id,
                codex_client_id=codex_client_id,
                force_reauthorize=True,
            )
        )
    except Exception as exc:
        return {
            "ok": False,
            "error_code": type(exc).__name__,
            "error_message": str(exc),
        }
    return {"ok": True, "codex_credential_id": credential_id}


def _repush_downstream_record(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
) -> dict[str, Any]:
    if not record.downstream_channel_id:
        return {"ok": True, "reason": "record_has_no_downstream_channel"}
    channel = session.get(DownstreamChannelModel, record.downstream_channel_id)
    credential = session.get(CodexOAuthCredentialModel, record.codex_credential_id)
    user = session.get(UserAccountModel, record.user_account_id)
    workspace = session.get(TeamWorkspaceModel, record.team_workspace_id)
    if channel is None:
        return {"ok": False, "error_code": "missing_downstream_channel"}
    if credential is None:
        return {"ok": False, "error_code": "missing_codex_credential"}
    if user is None:
        return {"ok": False, "error_code": "missing_user_account"}
    if workspace is None:
        return {"ok": False, "error_code": "missing_workspace"}
    payload = downstream_payload(
        user=user,
        workspace=workspace,
        credential=credential,
        batch_item=None,
    )
    provider = _provider_from_channel(channel)
    try:
        result = provider.push_codex_credential(payload)
    except Exception as exc:
        return {
            "ok": False,
            "error_code": type(exc).__name__,
            "error_message": str(exc),
        }
    now = datetime.now(UTC)
    if not result.pushed:
        return {
            "ok": False,
            "error_code": result.error_code or "downstream_repush_failed",
            "error_message": result.error_message,
        }
    record.downstream_external_id = result.downstream_external_id or record.downstream_external_id
    record.codex_token_expires_at = credential.expires_at
    record.token_chatgpt_account_id = credential.token_chatgpt_account_id
    record.error_code = ""
    record.error_message = ""
    record.updated_at = now
    return {"ok": True, "downstream_external_id": record.downstream_external_id}


def _session_factory_from(session: Session):
    return sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)


def _create_running_job_run(
    *,
    session: Session,
    job_type: str,
    input_json: dict[str, Any],
    created_by: str,
) -> tuple[JobModel, JobRunModel]:
    job = JobQueue(session).enqueue(job_type=job_type, input_json=input_json, created_by=created_by)
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    session.commit()
    return job, run


def _finish_running_job(
    *,
    session: Session,
    job: JobModel,
    run: JobRunModel,
    runner,
) -> dict:
    try:
        output = runner()
    except Exception as exc:
        finished_at = datetime.now(UTC)
        job.job_status = "failed"
        job.updated_at = finished_at
        run.run_status = "failed"
        run.finished_at = finished_at
        run.error_code = type(exc).__name__[:200]
        run.error_message = str(exc)[:1000]
        run.output_json = {"error": f"{type(exc).__name__}: {exc}"}
        session.commit()
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc
    finished_at = datetime.now(UTC)
    output_failed = int(output.get("failed") or 0) if isinstance(output, dict) else 0
    job.job_status = "failed" if output_failed > 0 else "succeeded"
    job.updated_at = finished_at
    run.run_status = job.job_status
    run.finished_at = finished_at
    if output_failed > 0:
        run.error_code = "partial_failure"
        run.error_message = f"{output_failed} item(s) failed"
    run.output_json = output
    session.commit()
    return output


def _run_workspace_invite_sync_tick(
    *,
    req: AutomationWorkspaceInviteSyncRequest,
    session_factory,
    job_id: str,
    run_id: str,
) -> dict:
    with session_factory() as session:
        workspace_ids = _active_automation_workspace_ids(
            session=session,
            limit=req.workspace_limit,
        )
    concurrency = _bounded_concurrency(req.workspace_concurrency)
    results = _parallel_map(
        items=workspace_ids,
        max_workers=concurrency,
        fn=lambda workspace_id: _process_workspace_invite_sync(
            session_factory=session_factory,
            workspace_id=workspace_id,
            req=req,
            job_id=job_id,
            run_id=run_id,
        ),
    )
    return _automation_results_summary(
        job_type="automation.workspace_invite_sync",
        results=results,
        concurrency=concurrency,
    )


def _process_workspace_invite_sync(
    *,
    session_factory,
    workspace_id: str,
    req: AutomationWorkspaceInviteSyncRequest,
    job_id: str,
    run_id: str,
) -> dict:
    now = datetime.now(UTC)
    with session_factory() as session:
        workspace = session.get(TeamWorkspaceModel, workspace_id)
        if workspace is None or workspace.workspace_status != "active":
            return {"team_workspace_id": workspace_id, "status": "skipped", "reason": "workspace_not_active"}
        state = _ensure_workspace_automation_state(session=session, workspace_id=workspace.id)
        if state.automation_status != "active":
            return {"team_workspace_id": workspace.id, "status": "skipped", "reason": state.automation_status}
        if state.invite_status == "sent":
            if state.last_invite_finished_at is None:
                ready_to_sync = True
            else:
                ready_to_sync = now - state.last_invite_finished_at >= timedelta(
                    seconds=max(0, int(req.sync_after_seconds or 120))
                )
            if not ready_to_sync:
                return {"team_workspace_id": workspace.id, "status": "skipped", "reason": "invite_waiting"}
            result = _sync_workspace_remote_state_inline(
                session=session,
                workspace_id=workspace.id,
                page_size=req.sync_page_size,
            )
            state.last_sync_at = datetime.now(UTC)
            state.updated_at = state.last_sync_at
            session.commit()
            return {"team_workspace_id": workspace.id, "status": "synced", **result}

        account_ids = _select_invite_candidate_account_ids(
            session=session,
            workspace_id=workspace.id,
            limit=max(1, int(req.invite_count or 350)),
        )
        if not account_ids:
            state.automation_status = "paused"
            state.pause_reason = "no_available_accounts"
            state.updated_at = datetime.now(UTC)
            session.commit()
            return {"team_workspace_id": workspace.id, "status": "paused", "reason": "no_available_accounts"}

        invite_concurrency = _bounded_concurrency(req.invite_concurrency)
        barrier_key = f"invite:{job_id}:{workspace.id}"
        for index, user_account_id in enumerate(account_ids):
            group_index = index // invite_concurrency
            group_start = group_index * invite_concurrency
            group_expected = min(invite_concurrency, len(account_ids) - group_start)
            WorkQueue(session).enqueue(
                job_id=job_id,
                work_type="membership.invite_member.account",
                input_json={
                    "team_workspace_id": workspace.id,
                    "user_account_id": user_account_id,
                    "team_admin_session_id": workspace.source_admin_session_id,
                    "_run_id": run_id,
                    "_barrier_key": barrier_key,
                    "_barrier_group": str(group_index),
                    "_barrier_expected": group_expected,
                    "_barrier_timeout_s": 30,
                },
            )
        session.commit()

    _run_job_work_now(
        session_factory=session_factory,
        job_id=job_id,
        concurrency=min(invite_concurrency, len(account_ids)),
    )
    with session_factory() as session:
        state = _ensure_workspace_automation_state(session=session, workspace_id=workspace_id)
        state.invite_status = "sent"
        state.invite_job_id = job_id
        state.last_invite_finished_at = datetime.now(UTC)
        state.updated_at = state.last_invite_finished_at
        session.commit()
    return {
        "team_workspace_id": workspace_id,
        "status": "invited",
        "invited_count": len(account_ids),
        "invite_concurrency": invite_concurrency,
    }


def _run_workspace_authorize_tick(
    *,
    req: AutomationWorkspaceAuthorizeRequest,
    session_factory,
    job_id: str,
) -> dict:
    with session_factory() as session:
        workspace_ids = _active_automation_workspace_ids(
            session=session,
            limit=req.workspace_limit,
            require_invite_sent=True,
        )
    concurrency = _bounded_concurrency(req.workspace_concurrency)
    results = _parallel_map(
        items=workspace_ids,
        max_workers=concurrency,
        fn=lambda workspace_id: _process_workspace_authorize(
            session_factory=session_factory,
            workspace_id=workspace_id,
            req=req,
            job_id=job_id,
        ),
    )
    return _automation_results_summary(
        job_type="automation.workspace_authorize",
        results=results,
        concurrency=concurrency,
    )


def _process_workspace_authorize(
    *,
    session_factory,
    workspace_id: str,
    req: AutomationWorkspaceAuthorizeRequest,
    job_id: str,
) -> dict:
    with session_factory() as session:
        workspace = session.get(TeamWorkspaceModel, workspace_id)
        if workspace is None or workspace.workspace_status != "active":
            return {"team_workspace_id": workspace_id, "status": "skipped", "reason": "workspace_not_active"}
        state = _ensure_workspace_automation_state(session=session, workspace_id=workspace.id)
        if state.automation_status != "active" or state.invite_status != "sent":
            return {"team_workspace_id": workspace.id, "status": "skipped", "reason": "not_ready"}
        lock_acquired = _acquire_workspace_operation_lock(
            session=session,
            workspace_id=workspace_id,
            lock_type="codex_fill",
            locked_by=job_id,
            ttl_seconds=req.lock_ttl_seconds,
        )
        if not lock_acquired:
            return {"team_workspace_id": workspace_id, "status": "skipped", "reason": "lock_held"}
        authorized: list[dict[str, str]] = []
        fill_errors: list[dict[str, str]] = []
        last_remote_state: dict[str, Any] = {}
        authorization_attempts_left: int | None = None
        try:
            while True:
                remote_state = _sync_workspace_remote_state_inline(
                    session=session,
                    workspace_id=workspace_id,
                    page_size=req.sync_page_size,
                )
                last_remote_state = remote_state
                state = _ensure_workspace_automation_state(session=session, workspace_id=workspace_id)
                state.last_sync_at = datetime.now(UTC)
                state.updated_at = state.last_sync_at
                session.commit()

                workspace = session.get(TeamWorkspaceModel, workspace_id)
                purchased_seats = int(
                    (workspace.seats_entitled if workspace else 0)
                    or (workspace.seat_limit if workspace else 0)
                    or 0
                )
                remote_default_seat_count = int(remote_state.get("remote_default_seat_count") or 0)
                if authorization_attempts_left is None:
                    authorization_attempts_left = (
                        max(1, purchased_seats - remote_default_seat_count)
                        if purchased_seats > 0
                        else 1
                    )
                if purchased_seats > 0 and remote_default_seat_count >= purchased_seats:
                    if authorized:
                        return {
                            "team_workspace_id": workspace_id,
                            "status": "authorized",
                            "authorized_count": len(authorized),
                            "authorized": authorized,
                            "fill_error_count": len(fill_errors),
                            "fill_errors": fill_errors,
                            "remote_default_seat_count": remote_default_seat_count,
                            "purchased_seats": purchased_seats,
                        }
                    return {
                        "team_workspace_id": workspace_id,
                        "status": "skipped",
                        "reason": "seats_full",
                        "remote_member_count": int(remote_state.get("remote_member_count") or 0),
                        "remote_default_seat_count": remote_default_seat_count,
                        "purchased_seats": purchased_seats,
                    }

                if authorization_attempts_left <= 0 or (purchased_seats <= 0 and authorized):
                    return {
                        "team_workspace_id": workspace_id,
                        "status": "authorized",
                        "reason": "authorization_attempt_limit_reached",
                        "authorized_count": len(authorized),
                        "authorized": authorized,
                        "fill_error_count": len(fill_errors),
                        "fill_errors": fill_errors,
                        "remote_state": last_remote_state,
                    }

                selected_user_account_id = _random_workspace_authorization_candidate(
                    session=session,
                    workspace_id=workspace_id,
                )
                if not selected_user_account_id:
                    status = "authorized" if authorized else "skipped"
                    return {
                        "team_workspace_id": workspace_id,
                        "status": status,
                        "reason": "no_candidate",
                        "authorized_count": len(authorized),
                        "authorized": authorized,
                        "fill_error_count": len(fill_errors),
                        "fill_errors": fill_errors,
                        "remote_state": last_remote_state,
                    }
                session.commit()
                try:
                    authorization_attempts_left -= 1
                    credential_id = BuildCodexCredentialWorkItemWorkflow(
                        session_factory=session_factory,
                        openai_provider=_openai_provider(),
                        mail_provider=_mail_provider(),
                    ).run(
                        BuildCodexCredentialWorkInput(
                            user_account_id=selected_user_account_id,
                            team_workspace_id=workspace_id,
                            codex_client_id=req.codex_client_id,
                            force_reauthorize=False,
                        )
                    )
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"[:1000]
                    remote_delete_result = _handle_candidate_authorization_failed(
                        session=session,
                        workspace_id=workspace_id,
                        user_account_id=selected_user_account_id,
                        error=str(exc),
                    )
                    fill_errors.append(
                        {
                            "user_account_id": selected_user_account_id,
                            "error": error,
                            "remote_delete_result": remote_delete_result,
                        }
                    )
                    session.commit()
                    if not authorized:
                        return {
                            "team_workspace_id": workspace_id,
                            "status": "failed",
                            "user_account_id": selected_user_account_id,
                            "error": error,
                            "remote_delete_result": remote_delete_result,
                            "remote_state": last_remote_state,
                        }
                    return {
                        "team_workspace_id": workspace_id,
                        "status": "authorized",
                        "reason": "stopped_after_error",
                        "authorized_count": len(authorized),
                        "authorized": authorized,
                        "fill_error_count": len(fill_errors),
                        "fill_errors": fill_errors,
                        "remote_state": last_remote_state,
                    }
                _mark_credential_pending_push(session=session, credential_id=credential_id)
                state = _ensure_workspace_automation_state(session=session, workspace_id=workspace_id)
                state.last_authorization_at = datetime.now(UTC)
                state.updated_at = state.last_authorization_at
                session.commit()
                authorized.append(
                    {
                        "user_account_id": selected_user_account_id,
                        "codex_credential_id": credential_id,
                    }
                )
                wait_seconds = max(0, int(req.authorization_sync_wait_seconds or 0))
                if wait_seconds:
                    sleep(wait_seconds)
        finally:
            _release_workspace_operation_lock(
                session=session,
                workspace_id=workspace_id,
                lock_type="codex_fill",
                locked_by=job_id,
            )
            session.commit()


def _run_downstream_push_tick(
    *,
    req: AutomationDownstreamPushRequest,
    session_factory,
    job_id: str,
    run_id: str,
) -> dict:
    with session_factory() as session:
        retryable_failed_exists = exists().where(
            DownstreamCodexPushRecordModel.downstream_channel_id == DownstreamChannelModel.id,
            DownstreamCodexPushRecordModel.push_status == "failed",
            DownstreamCodexPushRecordModel.push_attempt_count < MAX_DOWNSTREAM_PUSH_ATTEMPTS,
        )
        channels = session.scalars(
            select(DownstreamChannelModel)
            .where(
                DownstreamChannelModel.enabled.is_(True),
                (DownstreamChannelModel.push_balance > 0) | retryable_failed_exists,
            )
            .order_by(DownstreamChannelModel.updated_at.asc())
            .limit(max(1, int(req.channel_limit or 20)))
        ).all()
        selected: set[str] = set()
        work_count = 0
        for channel in channels:
            credential_ids = _select_channel_push_credential_ids(
                session=session,
                channel=channel,
                limit=max(1, int(req.per_channel_limit or 50)),
                selected=selected,
            )
            for credential_id in credential_ids:
                selected.add(credential_id)
                WorkQueue(session).enqueue(
                    job_id=job_id,
                    work_type="codex_credential.push.account",
                    input_json={
                        "codex_credential_id": credential_id,
                        "downstream_channel_id": channel.id,
                        "request_endpoint": req.request_endpoint,
                        "_run_id": run_id,
                    },
                )
                work_count += 1
        session.commit()
    if work_count:
        push_workers = _bounded_concurrency(req.push_concurrency)
        channel_workers = _bounded_concurrency(req.channel_concurrency)
        _run_job_work_now(
            session_factory=session_factory,
            job_id=job_id,
            concurrency=min(_bounded_concurrency(push_workers * channel_workers), work_count),
        )
    with session_factory() as session:
        summary = _work_summary(session, job_id)
    return {
        "job_type": "automation.downstream_push",
        "channel_count": len(channels),
        "work_count": work_count,
        "channel_concurrency": _bounded_concurrency(req.channel_concurrency),
        "push_concurrency": _bounded_concurrency(req.push_concurrency),
        **summary,
    }


def _run_codex_heartbeat_tick(
    *,
    req: AutomationCodexHeartbeatRequest,
    session_factory,
) -> dict:
    with session_factory() as session:
        credential_ids = session.scalars(
            select(CodexOAuthCredentialModel.id)
            .where(
                CodexOAuthCredentialModel.credential_status.in_(
                    (CredentialStatus.ACTIVE.value, CredentialStatus.ERROR.value)
                ),
                CodexOAuthCredentialModel.access_token != "",
                CodexOAuthCredentialModel.refresh_token != "",
                CodexOAuthCredentialModel.last_heartbeat_status.in_(
                    ("unknown", "failed", "error")
                )
                | (CodexOAuthCredentialModel.last_heartbeat_at.is_(None)),
                CodexOAuthCredentialModel.push_lifecycle_status.in_(
                    ("none", "pending_push", "failed")
                ),
            )
            .order_by(
                CodexOAuthCredentialModel.last_heartbeat_at.asc().nullsfirst(),
                CodexOAuthCredentialModel.updated_at.asc(),
            )
            .limit(max(1, int(req.credential_limit or 100)))
        ).all()
    concurrency = _bounded_concurrency(req.credential_concurrency)
    results = _parallel_map(
        items=[str(item) for item in credential_ids],
        max_workers=concurrency,
        fn=lambda credential_id: _process_codex_heartbeat_credential(
            session_factory=session_factory,
            credential_id=credential_id,
        ),
    )
    return _automation_results_summary(
        job_type="automation.codex_heartbeat",
        results=results,
        concurrency=concurrency,
    )


def _process_codex_heartbeat_credential(
    *,
    session_factory,
    credential_id: str,
) -> dict:
    try:
        HeartbeatCodexCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_provider(),
        ).run(codex_credential_id=credential_id)
        return {"id": credential_id, "status": "active"}
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:1000]
        if not _is_unauthorized_heartbeat_error(error):
            return {"id": credential_id, "status": "failed", "error": error}

    recovery = _recover_heartbeat_credential_by_reauthorize_repush(
        session_factory=session_factory,
        credential_id=credential_id,
    )
    if not recovery.get("ok"):
        return {
            "id": credential_id,
            "status": "failed",
            "error": error,
            "recovery": recovery,
        }
    try:
        HeartbeatCodexCredentialWorkflow(
            session_factory=session_factory,
            openai_provider=_openai_provider(),
        ).run(codex_credential_id=credential_id)
        return {
            "id": credential_id,
            "status": "active",
            "recovery": recovery,
        }
    except Exception as exc:
        return {
            "id": credential_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "recovery": recovery,
        }


def _recover_heartbeat_credential_by_reauthorize_repush(
    *,
    session_factory,
    credential_id: str,
) -> dict[str, Any]:
    with session_factory() as session:
        credential = session.get(CodexOAuthCredentialModel, credential_id)
        if credential is None:
            return {
                "ok": False,
                "error_code": "credential_not_found",
                "error_message": f"codex credential not found: {credential_id}",
            }
        record = session.scalars(
            select(DownstreamCodexPushRecordModel)
            .where(
                DownstreamCodexPushRecordModel.codex_credential_id == credential_id,
                DownstreamCodexPushRecordModel.downstream_channel_id.is_not(None),
                DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
            )
            .order_by(DownstreamCodexPushRecordModel.updated_at.desc())
        ).first()
        reauthorize_result = _reauthorize_codex_credential(
            session_factory=session_factory,
            user_account_id=credential.user_account_id,
            team_workspace_id=credential.team_workspace_id,
            codex_client_id=credential.codex_client_id,
        )
        if not reauthorize_result.get("ok"):
            if _is_phone_verification_required_error(
                str(reauthorize_result.get("error_message") or "")
            ):
                cleanup_result = _handle_authorization_phone_verification_failed(
                    session=session,
                    workspace_id=credential.team_workspace_id,
                    user_account_id=credential.user_account_id,
                    error=str(reauthorize_result.get("error_message") or ""),
                    sync_after_seconds=5,
                )
                return {
                    **reauthorize_result,
                    "phone_verification_cleanup": cleanup_result,
                }
            return reauthorize_result
        if record is None:
            return {
                "ok": True,
                "reauthorize": reauthorize_result,
                "repush": {"ok": True, "skipped": True, "reason": "no_downstream_record"},
            }
        session.expire_all()
        refreshed_record = session.get(DownstreamCodexPushRecordModel, record.id)
        if refreshed_record is None:
            return {
                "ok": False,
                "error_code": "push_record_missing_after_reauthorize",
            }
        repush_result = _repush_downstream_record(session=session, record=refreshed_record)
        if not repush_result.get("ok"):
            return repush_result
        return {
            "ok": True,
            "reauthorize": reauthorize_result,
            "repush": repush_result,
        }


def _run_downstream_usage_cleanup_tick(
    *,
    req: AutomationDownstreamUsageCleanupRequest,
    session_factory,
) -> dict:
    threshold = max(1, min(int(req.threshold_percent or 95), 100))
    with session_factory() as session:
        record_ids = session.scalars(
            select(DownstreamCodexPushRecordModel.id)
            .where(DownstreamCodexPushRecordModel.push_status == "pushed")
            .order_by(DownstreamCodexPushRecordModel.updated_at.asc())
            .limit(max(1, int(req.record_limit or 100)))
        ).all()
    concurrency = _bounded_concurrency(req.record_concurrency)
    results = _parallel_map(
        items=record_ids,
        max_workers=concurrency,
        fn=lambda record_id: _process_downstream_usage_cleanup_record(
            session_factory=session_factory,
            record_id=record_id,
            threshold=threshold,
        ),
    )
    return _automation_results_summary(
        job_type="automation.downstream_usage_cleanup",
        results=results,
        concurrency=concurrency,
    )


_AUTOMATION_SCHEDULER_STARTED = False


def start_automation_scheduler() -> None:
    global _AUTOMATION_SCHEDULER_STARTED
    if _AUTOMATION_SCHEDULER_STARTED:
        return
    _AUTOMATION_SCHEDULER_STARTED = True
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    Thread(
        target=_automation_scheduler_loop,
        kwargs={"session_factory": session_factory},
        daemon=True,
        name="automation-scheduler",
    ).start()


def _automation_scheduler_loop(*, session_factory) -> None:
    scheduler_id = f"{gethostname()}-{uuid4()}"
    while True:
        try:
            _run_due_automation_schedules(
                session_factory=session_factory,
                scheduler_id=scheduler_id,
            )
        except Exception:
            pass
        sleep(5)


def _run_due_automation_schedules(*, session_factory, scheduler_id: str) -> None:
    now = datetime.now(UTC)
    with session_factory() as session:
        schedule_ids = session.scalars(
            select(AutomationScheduleModel.id)
            .where(
                AutomationScheduleModel.enabled.is_(True),
                AutomationScheduleModel.schedule_status == "active",
                AutomationScheduleModel.next_run_at <= now,
            )
            .order_by(AutomationScheduleModel.next_run_at.asc())
            .limit(4)
        ).all()

    for schedule_id in schedule_ids:
        _execute_automation_schedule(
            schedule_id=schedule_id,
            session_factory=session_factory,
            locked_by=scheduler_id,
            update_next_run=True,
            acquire_lock=True,
        )


def _execute_automation_schedule(
    *,
    schedule_id: str,
    session_factory,
    locked_by: str,
    update_next_run: bool,
    acquire_lock: bool = False,
) -> dict:
    with session_factory() as session:
        stmt = select(AutomationScheduleModel).where(AutomationScheduleModel.id == schedule_id)
        if acquire_lock:
            stmt = stmt.with_for_update(skip_locked=True)
        schedule = session.scalars(stmt).first()
        if schedule is None:
            return {"schedule_id": schedule_id, "status": "locked", "error_code": "schedule_already_running"}
        now = datetime.now(UTC)
        if acquire_lock and schedule.locked_by and (
            schedule.locked_until is None or schedule.locked_until > now
        ):
            return {"schedule_id": schedule_id, "status": "locked", "error_code": "schedule_already_running"}
        if acquire_lock and schedule.locked_by:
            schedule.locked_by = ""
            schedule.locked_until = None
        if acquire_lock:
            schedule.locked_by = locked_by
            schedule.locked_until = now + timedelta(
                seconds=max(300, min(1800, int(schedule.interval_seconds or 60) * 2))
            )
        schedule.last_run_at = now
        if update_next_run:
            schedule.next_run_at = now + timedelta(seconds=max(5, int(schedule.interval_seconds or 60)))
        schedule.last_run_status = "running"
        schedule.last_error_code = ""
        schedule.last_error_message = ""
        schedule.updated_at = now
        session.commit()

    try:
        result = _run_automation_schedule_job(
            schedule_id=schedule_id,
            session_factory=session_factory,
        )
    except Exception as exc:
        with session_factory() as session:
            schedule = session.get(AutomationScheduleModel, schedule_id)
            if schedule is not None:
                schedule.last_run_status = "failed"
                schedule.schedule_status = "error"
                schedule.enabled = False
                if schedule.locked_by == locked_by:
                    schedule.locked_by = ""
                    schedule.locked_until = None
                schedule.last_error_code = type(exc).__name__[:200]
                schedule.last_error_message = str(exc)[:1000]
                schedule.updated_at = datetime.now(UTC)
                session.commit()
        return {
            "schedule_id": schedule_id,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}"[:1000],
        }

    with session_factory() as session:
        schedule = session.get(AutomationScheduleModel, schedule_id)
        if schedule is not None:
            schedule.last_job_id = str(result.get("job_id") or "")
            schedule.last_run_status = str(result.get("job_status") or "succeeded")
            if schedule.locked_by == locked_by:
                schedule.locked_by = ""
                schedule.locked_until = None
            schedule.last_error_code = ""
            schedule.last_error_message = ""
            schedule.updated_at = datetime.now(UTC)
            session.commit()
    return {"schedule_id": schedule_id, "status": "succeeded", **result}


def _run_automation_schedule_job(*, schedule_id: str, session_factory) -> dict:
    with session_factory() as session:
        schedule = session.get(AutomationScheduleModel, schedule_id)
        if schedule is None:
            raise RuntimeError("automation schedule not found")
        schedule_type = schedule.schedule_type
        config = dict(schedule.config_json or {})
        config["created_by"] = config.get("created_by") or f"scheduler:{schedule.id}"
        if schedule_type == "automation.workspace_invite_sync":
            req = AutomationWorkspaceInviteSyncRequest(**config)
            job, run = _create_running_job_run(
                session=session,
                job_type=schedule_type,
                input_json=req.model_dump(),
                created_by=req.created_by,
            )
            output = _finish_running_job(
                session=session,
                job=job,
                run=run,
                runner=lambda: _run_workspace_invite_sync_tick(
                    req=req,
                    session_factory=session_factory,
                    job_id=job.id,
                    run_id=run.id,
                ),
            )
        elif schedule_type == "automation.workspace_authorize":
            req = AutomationWorkspaceAuthorizeRequest(**config)
            job, run = _create_running_job_run(
                session=session,
                job_type=schedule_type,
                input_json=req.model_dump(),
                created_by=req.created_by,
            )
            output = _finish_running_job(
                session=session,
                job=job,
                run=run,
                runner=lambda: _run_workspace_authorize_tick(
                    req=req,
                    session_factory=session_factory,
                    job_id=job.id,
                ),
            )
        elif schedule_type == "automation.downstream_push":
            req = AutomationDownstreamPushRequest(**config)
            job, run = _create_running_job_run(
                session=session,
                job_type=schedule_type,
                input_json=req.model_dump(),
                created_by=req.created_by,
            )
            output = _finish_running_job(
                session=session,
                job=job,
                run=run,
                runner=lambda: _run_downstream_push_tick(
                    req=req,
                    session_factory=session_factory,
                    job_id=job.id,
                    run_id=run.id,
                ),
            )
        elif schedule_type == "automation.codex_heartbeat":
            req = AutomationCodexHeartbeatRequest(**config)
            job, run = _create_running_job_run(
                session=session,
                job_type=schedule_type,
                input_json=req.model_dump(),
                created_by=req.created_by,
            )
            output = _finish_running_job(
                session=session,
                job=job,
                run=run,
                runner=lambda: _run_codex_heartbeat_tick(
                    req=req,
                    session_factory=session_factory,
                ),
            )
        elif schedule_type == "automation.downstream_usage_cleanup":
            req = AutomationDownstreamUsageCleanupRequest(**config)
            job, run = _create_running_job_run(
                session=session,
                job_type=schedule_type,
                input_json=req.model_dump(),
                created_by=req.created_by,
            )
            output = _finish_running_job(
                session=session,
                job=job,
                run=run,
                runner=lambda: _run_downstream_usage_cleanup_tick(
                    req=req,
                    session_factory=session_factory,
                ),
            )
        else:
            raise RuntimeError(f"unsupported automation schedule type: {schedule_type}")
        return {"job_id": job.id, "job_status": job.job_status, "run_id": run.id, **output}


def _process_downstream_usage_cleanup_record(
    *,
    session_factory,
    record_id: str,
    threshold: int,
) -> dict:
    with session_factory() as session:
        record = session.get(DownstreamCodexPushRecordModel, record_id)
        if record is None or record.push_status != "pushed":
            return {"record_id": record_id, "status": "skipped", "reason": "record_not_pushed"}
        if record.downstream_provider == "local_sub2api":
            return {
                "record_id": record_id,
                "status": "skipped",
                "reason": "local_sub2api_no_remote_usage",
                "usage_percent": record.usage_percent,
                "threshold_percent": threshold,
            }
        probe = _probe_downstream_record_usage_with_recovery(
            session=session,
            session_factory=session_factory,
            record=record,
            threshold=threshold,
        )
        if not probe.ok:
            session.commit()
            return {
                "record_id": record_id,
                "status": "failed",
                "reason": probe.error_code or "usage_probe_failed",
                "usage_percent": record.usage_percent,
                "threshold_percent": threshold,
            }
        usage_percent = probe.usage_percent
        if usage_percent >= threshold:
            now = datetime.now(UTC)
            remove_result = _mark_downstream_record_used_and_cooldown(
                session=session,
                record=record,
                now=now,
                reason=f"usage_percent>={threshold}",
            )
            if not remove_result.get("ok"):
                session.commit()
                return {
                    "record_id": record_id,
                    "status": "failed",
                    "reason": remove_result.get("error_code") or "remote_remove_failed",
                    "usage_percent": usage_percent,
                    "threshold_percent": threshold,
                }
            state = session.get(WorkspaceAutomationStateModel, record.team_workspace_id)
            if state is not None:
                state.last_usage_cleanup_at = now
                state.updated_at = now
            session.commit()
            return {
                "record_id": record_id,
                "status": "used",
                "usage_percent": usage_percent,
                "threshold_percent": threshold,
            }
        session.commit()
        return {
            "record_id": record_id,
            "status": "active",
            "usage_percent": usage_percent,
            "threshold_percent": threshold,
        }


def _active_automation_workspace_ids(
    *,
    session: Session,
    limit: int,
    require_invite_sent: bool = False,
) -> list[str]:
    _ensure_workspace_automation_states_for_active_workspaces(session=session)
    stmt = (
        select(TeamWorkspaceModel.id)
        .join(
            WorkspaceAutomationStateModel,
            WorkspaceAutomationStateModel.team_workspace_id == TeamWorkspaceModel.id,
        )
        .where(
            TeamWorkspaceModel.workspace_status == "active",
            WorkspaceAutomationStateModel.automation_status == "active",
        )
        .order_by(TeamWorkspaceModel.updated_at.asc())
        .limit(max(1, int(limit or 20)))
    )
    if require_invite_sent:
        stmt = stmt.where(WorkspaceAutomationStateModel.invite_status == "sent")
    return list(session.scalars(stmt).all())


def _ensure_workspace_automation_states_for_active_workspaces(*, session: Session) -> None:
    rows = session.scalars(
        select(TeamWorkspaceModel.id).where(TeamWorkspaceModel.workspace_status == "active")
    ).all()
    for workspace_id in rows:
        _ensure_workspace_automation_state(session=session, workspace_id=workspace_id)
    session.commit()


def _ensure_workspace_automation_state(
    *,
    session: Session,
    workspace_id: str,
) -> WorkspaceAutomationStateModel:
    state = session.get(WorkspaceAutomationStateModel, workspace_id)
    if state is not None:
        return state
    now = datetime.now(UTC)
    state = WorkspaceAutomationStateModel(
        team_workspace_id=workspace_id,
        automation_status="active",
        invite_status="not_sent",
        invite_job_id="",
        pause_reason="",
        last_error_code="",
        last_error_message="",
        created_at=now,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state


def _select_invite_candidate_account_ids(
    *,
    session: Session,
    workspace_id: str,
    limit: int,
) -> list[str]:
    now = datetime.now(UTC)
    existing_membership = (
        select(MembershipModel.user_account_id)
        .where(MembershipModel.team_workspace_id == workspace_id)
        .subquery()
    )
    other_workspace_membership = (
        select(MembershipModel.user_account_id)
        .where(MembershipModel.team_workspace_id != workspace_id)
        .subquery()
    )
    cooldown = (
        select(UserAccountCooldownModel.user_account_id)
        .where(
            UserAccountCooldownModel.team_workspace_id == workspace_id,
            UserAccountCooldownModel.cooldown_until > now,
        )
        .subquery()
    )
    return list(
        session.scalars(
            select(UserAccountModel.id)
            .join(UserAccountAuthModel, UserAccountAuthModel.user_account_id == UserAccountModel.id)
            .where(
                UserAccountModel.account_status == "active",
                UserAccountAuthModel.refresh_token != "",
                UserAccountAuthModel.refresh_token_status == "active",
                UserAccountAuthModel.session_status == "active",
                (
                    (UserAccountAuthModel.session_token != "")
                    | (UserAccountAuthModel.cookie_header != "")
                    | (UserAccountAuthModel.auth_cookie_header != "")
                ),
                ~UserAccountModel.id.in_(select(existing_membership.c.user_account_id)),
                ~UserAccountModel.id.in_(select(other_workspace_membership.c.user_account_id)),
                ~UserAccountModel.id.in_(select(cooldown.c.user_account_id)),
            )
            .order_by(UserAccountModel.updated_at.asc())
            .limit(max(1, int(limit or 350)))
        ).all()
    )


def _parallel_map(*, items: list[str], max_workers: int, fn) -> list[dict]:
    if not items:
        return []
    workers = max(1, min(max_workers, len(items)))
    if workers <= 1:
        return [_call_automation_item(fn=fn, item=item) for item in items]
    ordered: dict[int, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_call_automation_item, fn=fn, item=item): index for index, item in enumerate(items)}
        for future in as_completed(futures):
            ordered[futures[future]] = future.result()
    return [ordered[index] for index in range(len(items))]


def _call_automation_item(*, fn, item: str) -> dict:
    try:
        return fn(item)
    except Exception as exc:
        return {
            "id": item,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}"[:1000],
        }


def _automation_results_summary(
    *,
    job_type: str,
    results: list[dict],
    concurrency: int,
) -> dict:
    return {
        "job_type": job_type,
        "item_count": len(results),
        "concurrency": concurrency,
        "succeeded": sum(1 for item in results if item.get("status") in {"synced", "invited", "authorized", "used", "active"}),
        "skipped": sum(1 for item in results if item.get("status") == "skipped"),
        "paused": sum(1 for item in results if item.get("status") == "paused"),
        "failed": sum(1 for item in results if item.get("status") == "failed"),
        "results": results,
    }


def _bounded_concurrency(value: int) -> int:
    settings = get_settings()
    return max(1, min(int(value or 1), settings.worker_max_concurrency))


def _active_downstream_slot_count(session: Session, downstream_channel_id: str) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(DownstreamCodexPushRecordModel)
            .where(
                DownstreamCodexPushRecordModel.downstream_channel_id == downstream_channel_id,
                DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
            )
        )
        or 0
    )


def _mark_downstream_record_used_and_cooldown(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
    now: datetime,
    reason: str,
) -> dict:
    remove_result = _remove_remote_member_for_push_record(session=session, record=record)
    if not remove_result.get("ok"):
        record.usage_status = "check_failed"
        record.error_code = str(remove_result.get("error_code") or "remote_remove_failed")[:200]
        record.error_message = str(remove_result.get("error_message") or remove_result)[:1000]
        record.updated_at = now
        return remove_result

    credential = session.get(CodexOAuthCredentialModel, record.codex_credential_id)
    record.push_status = "used"
    record.usage_status = "used"
    record.used_at = now
    record.updated_at = now
    if credential is not None:
        credential.push_lifecycle_status = "used"
        credential.updated_at = now
    channel = session.get(DownstreamChannelModel, record.downstream_channel_id)
    if channel is not None:
        channel.used_count += 1
        channel.updated_at = now
    cooldown_until = datetime.fromtimestamp(now.timestamp() + 72 * 3600, tz=UTC)
    existing = session.scalars(
        select(UserAccountCooldownModel).where(
            UserAccountCooldownModel.user_account_id == record.user_account_id,
            UserAccountCooldownModel.team_workspace_id == record.team_workspace_id,
            UserAccountCooldownModel.cooldown_type == "post_usage_remove",
        )
    ).first()
    if existing is None:
        existing = UserAccountCooldownModel(
            id=f"user-account-cooldown-{uuid4()}",
            user_account_id=record.user_account_id,
            team_workspace_id=record.team_workspace_id,
            cooldown_type="post_usage_remove",
            cooldown_until=cooldown_until,
            reason=reason,
            source_push_record_id=record.id,
            created_at=now,
            updated_at=now,
        )
        session.add(existing)
    else:
        existing.cooldown_until = cooldown_until
        existing.reason = reason
        existing.source_push_record_id = record.id
        existing.updated_at = now
    session.execute(
        delete(MembershipModel).where(
            MembershipModel.user_account_id == record.user_account_id,
            MembershipModel.team_workspace_id == record.team_workspace_id,
        )
    )
    return remove_result


def _remove_remote_member_for_account(
    *,
    session: Session,
    workspace_id: str,
    user_account_id: str,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, workspace_id)
    account = session.get(UserAccountModel, user_account_id)
    auth = session.get(UserAccountAuthModel, user_account_id)
    if workspace is None or account is None:
        return {"ok": False, "error_code": "missing_workspace_or_account"}
    if not workspace.source_admin_session_id:
        return {"ok": False, "error_code": "workspace_missing_admin_session"}
    admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
    if admin_session is None or not admin_session.access_token:
        return {"ok": False, "error_code": "admin_session_missing_access_token"}

    membership = session.scalars(
        select(MembershipModel).where(
            MembershipModel.user_account_id == user_account_id,
            MembershipModel.team_workspace_id == workspace_id,
        )
    ).first()
    if membership is None:
        membership = MembershipModel(
            id="",
            user_account_id=user_account_id,
            team_workspace_id=workspace_id,
            membership_status="unknown",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    credentials = session.scalars(
        select(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.user_account_id == user_account_id,
            CodexOAuthCredentialModel.team_workspace_id == workspace_id,
        )
    ).all()
    local_ids = _local_account_remote_user_ids(
        account=account,
        auth=auth,
        membership=membership,
        credentials=list(credentials),
    )
    if not local_ids:
        return {"ok": False, "error_code": "missing_local_openai_user_id"}

    remote_members = _fetch_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=100,
    )
    target_members = [
        member
        for member in remote_members
        if _remote_user_ids(member) & local_ids
    ]
    if not target_members:
        return {
            "ok": False,
            "error_code": "remote_member_not_found",
            "local_user_ids": sorted(local_ids),
        }
    return _delete_and_confirm_workspace_member(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        member=target_members[0],
    )


def _delete_and_confirm_workspace_member(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
    member: dict[str, Any],
) -> dict:
    results = _delete_workspace_members(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
        members=[member],
        concurrency=1,
    )
    delete_result = results[0] if results else {"ok": False, "error_code": "delete_not_attempted"}
    if not delete_result.get("ok"):
        return delete_result
    deleted_user_id = str(delete_result.get("user_id") or "").strip()
    confirm_members = _fetch_workspace_members(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
        page_size=100,
    )
    still_exists = any(
        deleted_user_id and deleted_user_id in _remote_user_ids(remote_member)
        for remote_member in confirm_members
    )
    if still_exists:
        return {
            **delete_result,
            "ok": False,
            "error_code": "remote_member_still_exists",
            "error_message": "delete returned success but member is still present in remote members list",
        }
    return {**delete_result, "confirmed_removed": True}


def _remove_remote_member_for_push_record(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, record.team_workspace_id)
    account = session.get(UserAccountModel, record.user_account_id)
    auth = session.get(UserAccountAuthModel, record.user_account_id)
    if workspace is None or account is None:
        return {"ok": False, "error_code": "missing_workspace_or_account"}
    if not workspace.source_admin_session_id:
        return {"ok": False, "error_code": "workspace_missing_admin_session"}
    admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
    if admin_session is None or not admin_session.access_token:
        return {"ok": False, "error_code": "admin_session_missing_access_token"}
    remote_members = _fetch_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=100,
    )
    credentials = []
    credential = session.get(CodexOAuthCredentialModel, record.codex_credential_id)
    if credential is not None:
        credentials.append(credential)
    membership = session.scalars(
        select(MembershipModel).where(
            MembershipModel.user_account_id == record.user_account_id,
            MembershipModel.team_workspace_id == record.team_workspace_id,
        )
    ).first()
    if membership is None:
        membership = MembershipModel(
            id="",
            user_account_id=record.user_account_id,
            team_workspace_id=record.team_workspace_id,
            membership_status="unknown",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    local_ids = _local_account_remote_user_ids(
        account=account,
        auth=auth,
        membership=membership,
        credentials=credentials,
    )
    target_members = [
        member
        for member in remote_members
        if local_ids and (_remote_user_ids(member) & local_ids)
    ]
    if not target_members:
        return {"ok": False, "error_code": "remote_member_not_found"}
    results = _delete_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        members=target_members[:1],
        concurrency=1,
    )
    delete_result = results[0] if results else {"ok": False, "error_code": "delete_not_attempted"}
    if not delete_result.get("ok"):
        return delete_result
    deleted_user_id = str(delete_result.get("user_id") or "").strip()
    confirm_members = _fetch_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=100,
    )
    still_exists = any(
        deleted_user_id and deleted_user_id in _remote_user_ids(member)
        for member in confirm_members
    )
    if still_exists:
        return {
            **delete_result,
            "ok": False,
            "error_code": "remote_member_still_exists",
            "error_message": "delete returned success but member is still present in remote members list",
        }
    return {**delete_result, "confirmed_removed": True}


def _sync_workspace_remote_state_inline(
    *,
    session: Session,
    workspace_id: str,
    page_size: int,
) -> dict:
    workspace = session.get(TeamWorkspaceModel, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    if not workspace.source_admin_session_id:
        raise HTTPException(status_code=400, detail="workspace missing source admin session")
    admin_session = session.get(TeamAdminSessionModel, workspace.source_admin_session_id)
    if admin_session is None:
        raise HTTPException(status_code=404, detail="team admin session not found")
    if not admin_session.access_token:
        raise HTTPException(status_code=400, detail="team admin session missing access_token")
    safe_page_size = max(1, min(int(page_size or 100), 200))
    remote_members = _fetch_workspace_members(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=safe_page_size,
    )
    remote_invites = _fetch_workspace_invites(
        access_token=admin_session.access_token,
        cookie_header=admin_session.cookie_header,
        account_id=workspace.external_workspace_id,
        page_size=safe_page_size,
    )
    remote_default_seat_count = _workspace_default_seat_count(remote_members)
    workspace.seats_in_use = remote_default_seat_count
    workspace.updated_at = datetime.now(UTC)
    result = _prune_workspace_memberships_by_remote_state(
        session=session,
        workspace=workspace,
        remote_members=remote_members,
        remote_invites=remote_invites,
    )
    return {
        "team_workspace_id": workspace.id,
        "external_workspace_id": workspace.external_workspace_id,
        "remote_member_count": len(remote_members),
        "remote_default_seat_count": remote_default_seat_count,
        "remote_invite_count": len(remote_invites),
        **result,
    }


def _workspace_default_seat_count(remote_members: list[dict[str, Any]]) -> int:
    return sum(
        1
        for member in remote_members
        if str(member.get("seat_type") or "").strip().lower() == "default"
    )


def _exclude_workspace_cooldown_accounts(
    *,
    session: Session,
    workspace_id: str,
    user_account_ids: list[str],
) -> list[str]:
    now = datetime.now(UTC)
    cooldown_ids = set(
        session.scalars(
            select(UserAccountCooldownModel.user_account_id).where(
                UserAccountCooldownModel.team_workspace_id == workspace_id,
                UserAccountCooldownModel.user_account_id.in_(user_account_ids),
                UserAccountCooldownModel.cooldown_until > now,
            )
        ).all()
    )
    return [item for item in user_account_ids if item not in cooldown_ids]


def _random_workspace_authorization_candidate(
    *,
    session: Session,
    workspace_id: str,
) -> str:
    now = datetime.now(UTC)
    cooldown_subquery = (
        select(UserAccountCooldownModel.user_account_id)
        .where(
            UserAccountCooldownModel.team_workspace_id == workspace_id,
            UserAccountCooldownModel.cooldown_until > now,
        )
        .subquery()
    )
    other_workspace_membership = (
        select(MembershipModel.user_account_id)
        .where(MembershipModel.team_workspace_id != workspace_id)
        .subquery()
    )
    rows = session.execute(
        select(MembershipModel.user_account_id, CodexOAuthCredentialModel.id)
        .join(
            UserAccountModel,
            UserAccountModel.id == MembershipModel.user_account_id,
        )
        .join(
            UserAccountAuthModel,
            UserAccountAuthModel.user_account_id == MembershipModel.user_account_id,
        )
        .outerjoin(
            CodexOAuthCredentialModel,
            (CodexOAuthCredentialModel.user_account_id == MembershipModel.user_account_id)
            & (CodexOAuthCredentialModel.team_workspace_id == MembershipModel.team_workspace_id)
            & (CodexOAuthCredentialModel.push_lifecycle_status.in_(("pending_push", "pushing", "pushed", "used"))),
        )
        .where(
            MembershipModel.team_workspace_id == workspace_id,
            UserAccountModel.account_status == AccountStatus.ACTIVE.value,
            ~MembershipModel.user_account_id.in_(select(cooldown_subquery.c.user_account_id)),
            ~MembershipModel.user_account_id.in_(select(other_workspace_membership.c.user_account_id)),
            UserAccountAuthModel.password != "",
            CodexOAuthCredentialModel.id.is_(None),
        )
    ).all()
    candidates = [str(user_account_id) for user_account_id, credential_id in rows if not credential_id]
    return random.choice(candidates) if candidates else ""


def _mark_credential_pending_push(*, session: Session, credential_id: str) -> None:
    credential = session.get(CodexOAuthCredentialModel, credential_id)
    if credential is None:
        return
    if credential.push_lifecycle_status not in {"pushing", "pushed", "used"}:
        credential.push_lifecycle_status = "pending_push"
        credential.updated_at = datetime.now(UTC)


def _handle_candidate_authorization_failed(
    *,
    session: Session,
    workspace_id: str,
    user_account_id: str,
    error: str,
) -> dict:
    if _is_phone_verification_required_error(error):
        return _handle_authorization_phone_verification_failed(
            session=session,
            workspace_id=workspace_id,
            user_account_id=user_account_id,
            error=error,
            sync_after_seconds=5,
        )
    membership = session.scalars(
        select(MembershipModel).where(
            MembershipModel.team_workspace_id == workspace_id,
            MembershipModel.user_account_id == user_account_id,
        )
    ).first()
    if membership is not None:
        membership.failure_code = "codex_authorization_failed"
        membership.failure_message = error[:1000]
        membership.updated_at = datetime.now(UTC)
    session.commit()
    remote_delete_result = _remove_remote_member_for_account(
        session=session,
        workspace_id=workspace_id,
        user_account_id=user_account_id,
    )
    return {
        "account_invalidated": False,
        "remote_delete": remote_delete_result,
    }


def _handle_authorization_phone_verification_failed(
    *,
    session: Session,
    workspace_id: str,
    user_account_id: str,
    error: str,
    sync_after_seconds: int,
) -> dict:
    now = datetime.now(UTC)
    account = session.get(UserAccountModel, user_account_id)
    invalidated = False
    if account is not None:
        account.account_status = AccountStatus.INVALID.value
        account.updated_at = now
        invalidated = True
    membership = session.scalars(
        select(MembershipModel).where(
            MembershipModel.team_workspace_id == workspace_id,
            MembershipModel.user_account_id == user_account_id,
        )
    ).first()
    if membership is not None:
        membership.failure_code = "codex_authorization_phone_verification_required"
        membership.failure_message = error[:1000]
        membership.updated_at = now
    session.commit()

    remote_delete_result = _remove_remote_member_for_account(
        session=session,
        workspace_id=workspace_id,
        user_account_id=user_account_id,
    )
    sync_result: dict[str, Any] = {}
    local_prune_result: dict[str, Any] = {}
    if max(0, int(sync_after_seconds or 0)):
        sleep(max(0, int(sync_after_seconds or 0)))
    try:
        sync_result = _sync_workspace_remote_state_inline(
            session=session,
            workspace_id=workspace_id,
            page_size=100,
        )
        session.commit()
    except Exception as exc:
        sync_result = {
            "ok": False,
            "error_code": type(exc).__name__,
            "error_message": str(exc)[:1000],
        }

    if remote_delete_result.get("ok") or remote_delete_result.get("error_code") == "remote_member_not_found":
        local_prune_result = _delete_local_memberships_with_credentials(
            session=session,
            workspace_id=workspace_id,
            user_account_ids=[user_account_id],
            now=datetime.now(UTC),
            mark_protected_downstream_used=False,
        )
        session.commit()
    return {
        "account_invalidated": invalidated,
        "remote_delete": remote_delete_result,
        "post_delete_sync": sync_result,
        "local_prune": local_prune_result,
    }


def _is_phone_verification_required_error(error: str) -> bool:
    text_value = str(error or "")
    return (
        "phone_verification_required" in text_value
        or "phone-otp/select-channel" in text_value
        or "add-phone" in text_value
        or "phone-number" in text_value
    )


def _acquire_workspace_operation_lock(
    *,
    session: Session,
    workspace_id: str,
    lock_type: str,
    locked_by: str,
    ttl_seconds: int,
) -> bool:
    now = datetime.now(UTC)
    lock = session.scalars(
        select(WorkspaceOperationLockModel)
        .where(
            WorkspaceOperationLockModel.team_workspace_id == workspace_id,
            WorkspaceOperationLockModel.lock_type == lock_type,
        )
        .with_for_update()
    ).first()
    locked_until = datetime.fromtimestamp(now.timestamp() + max(60, int(ttl_seconds or 1800)), tz=UTC)
    if lock is not None and lock.locked_until > now and lock.locked_by != locked_by:
        session.rollback()
        return False
    if lock is None:
        lock = WorkspaceOperationLockModel(
            team_workspace_id=workspace_id,
            lock_type=lock_type,
            locked_by=locked_by,
            locked_until=locked_until,
            created_at=now,
            updated_at=now,
        )
        session.add(lock)
    else:
        lock.locked_by = locked_by
        lock.locked_until = locked_until
        lock.updated_at = now
    session.commit()
    return True


def _release_workspace_operation_lock(
    *,
    session: Session,
    workspace_id: str,
    lock_type: str,
    locked_by: str,
) -> None:
    lock = session.get(WorkspaceOperationLockModel, (workspace_id, lock_type))
    if lock is not None and lock.locked_by == locked_by:
        session.delete(lock)


def _openai_provider() -> OpenAIChatGPTPlugin:
    settings = get_settings()
    return OpenAIChatGPTPlugin.from_config(
        OpenAIChatGPTClientConfig(
            auth_base_url=settings.openai_auth_base_url,
            chatgpt_base_url=settings.openai_chatgpt_base_url,
            probe_path_template=settings.openai_probe_path_template,
        )
    )


def _mail_provider() -> ExternalMailApiPlugin:
    settings = get_settings()
    return ExternalMailApiPlugin.from_config(
        ExternalMailApiClientConfig(
            base_url=settings.external_mail_api_base_url,
            api_key=settings.external_mail_api_key,
            provider_name=settings.external_mail_provider_name,
        )
    )


def _create_invite_work_job(*, req: InviteSelectedUsersRequest, session: Session) -> dict:
    user_account_ids = [item.strip() for item in req.user_account_ids if item.strip()]
    if not user_account_ids:
        raise HTTPException(status_code=400, detail="user_account_ids is required")
    workspace = session.get(TeamWorkspaceModel, req.team_workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="team workspace not found")
    found_ids = set(
        session.scalars(
            select(UserAccountModel.id).where(UserAccountModel.id.in_(user_account_ids))
        ).all()
    )
    missing_ids = [item for item in user_account_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "some user accounts not found", "user_account_ids": missing_ids},
        )
    settings = get_settings()
    concurrency = max(1, min(int(req.concurrency or 1), settings.worker_max_concurrency))
    job = JobQueue(session).enqueue(
        job_type="membership.invite_member.bulk",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    barrier_key = f"invite:{job.id}"
    total = len(user_account_ids)
    for index, user_account_id in enumerate(user_account_ids):
        barrier_group_index = index // concurrency
        barrier_group_start = barrier_group_index * concurrency
        barrier_group_expected = min(concurrency, total - barrier_group_start)
        work_queue.enqueue(
            job_id=job.id,
            work_type="membership.invite_member.account",
            input_json={
                "team_workspace_id": req.team_workspace_id,
                "user_account_id": user_account_id,
                "team_admin_session_id": req.team_admin_session_id,
                "_run_id": run.id,
                "_barrier_key": barrier_key,
                "_barrier_group": str(barrier_group_index),
                "_barrier_expected": barrier_group_expected,
                "_barrier_timeout_s": 30,
            },
        )
    session.commit()
    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(user_account_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = "succeeded" if summary["failed"] == 0 else "failed"
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = f"failed={summary['failed']}"
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(user_account_ids),
        "concurrency": concurrency,
        **summary,
    }


def _create_accept_invite_work_job(
    *,
    req: AcceptMembershipInvitesRequest,
    session: Session,
) -> dict:
    membership_ids = [item.strip() for item in req.membership_ids if item.strip()]
    if not membership_ids:
        raise HTTPException(status_code=400, detail="membership_ids is required")
    found_ids = set(
        session.scalars(select(MembershipModel.id).where(MembershipModel.id.in_(membership_ids))).all()
    )
    missing_ids = [item for item in membership_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "some memberships not found", "membership_ids": missing_ids},
        )

    settings = get_settings()
    concurrency = max(1, min(int(req.concurrency or 1), settings.worker_max_concurrency))
    job = JobQueue(session).enqueue(
        job_type="membership.accept_invite.bulk",
        input_json=req.model_dump(),
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    barrier_key = f"accept-invite:{job.id}"
    total = len(membership_ids)
    for index, membership_id in enumerate(membership_ids):
        barrier_group_index = index // concurrency
        barrier_group_start = barrier_group_index * concurrency
        barrier_group_expected = min(concurrency, total - barrier_group_start)
        work_queue.enqueue(
            job_id=job.id,
            work_type="membership.accept_invite.account",
            input_json={
                "membership_id": membership_id,
                "_run_id": run.id,
                "_barrier_key": barrier_key,
                "_barrier_group": str(barrier_group_index),
                "_barrier_expected": barrier_group_expected,
                "_barrier_timeout_s": 30,
            },
        )
    session.commit()
    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(membership_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = "succeeded" if summary["failed"] == 0 else "failed"
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = f"failed={summary['failed']}"
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(membership_ids),
        "concurrency": concurrency,
        **summary,
    }


def _create_session_otp_work_job(
    *,
    req: SessionOtpMembershipRequest,
    session: Session,
    phase: str,
) -> dict:
    raw_membership_ids = [item.strip() for item in req.membership_ids if item.strip()]
    if not raw_membership_ids:
        raise HTTPException(status_code=400, detail="membership_ids is required")
    memberships = session.scalars(
        select(MembershipModel).where(MembershipModel.id.in_(raw_membership_ids))
    ).all()
    found_ids = {row.id for row in memberships}
    missing_ids = [item for item in raw_membership_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail={"message": "some memberships not found", "membership_ids": missing_ids},
        )

    by_account: dict[str, MembershipModel] = {}
    by_membership_id = {row.id: row for row in memberships}
    for membership_id in raw_membership_ids:
        membership = by_membership_id.get(membership_id)
        if membership is None or membership.user_account_id in by_account:
            continue
        by_account[membership.user_account_id] = membership
    membership_ids = [row.id for row in by_account.values()]
    if not membership_ids:
        raise HTTPException(status_code=400, detail="no unique memberships to process")

    settings = get_settings()
    concurrency = max(1, min(int(req.concurrency or 1), settings.worker_max_concurrency))
    job_type = f"session_otp.{phase}.bulk"
    work_type = f"session_otp.{phase}.account"
    job = JobQueue(session).enqueue(
        job_type=job_type,
        input_json={
            **req.model_dump(),
            "phase": phase,
            "deduped_membership_ids": membership_ids,
            "deduped_count": len(membership_ids),
        },
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    job.job_status = "running"
    job.updated_at = now
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(run)
    work_queue = WorkQueue(session)
    barrier_key = f"session-otp-submit:{job.id}" if phase == "submit" else ""
    total = len(membership_ids)
    for index, membership_id in enumerate(membership_ids):
        barrier_group_index = index // concurrency
        barrier_group_start = barrier_group_index * concurrency
        barrier_group_expected = min(concurrency, total - barrier_group_start)
        input_json = {
            "membership_id": membership_id,
            "_run_id": run.id,
        }
        if phase == "submit":
            input_json.update(
                {
                    "_barrier_key": barrier_key,
                    "_barrier_group": str(barrier_group_index),
                    "_barrier_expected": barrier_group_expected,
                    "_barrier_timeout_s": 120,
                }
            )
        work_queue.enqueue(job_id=job.id, work_type=work_type, input_json=input_json)
    session.commit()
    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job.id,
        concurrency=min(concurrency, len(membership_ids)),
    )
    summary = _work_summary(session, job.id)
    job = session.get(JobModel, job.id)
    if job is not None:
        job.job_status = "succeeded" if summary["failed"] == 0 else "failed"
        job.updated_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    if run is not None:
        run.run_status = (
            "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
        )
        run.finished_at = datetime.now(UTC)
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = f"failed={summary['failed']}"
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": len(membership_ids),
        "concurrency": concurrency,
        **summary,
    }


@router.post("/workspace-join-batches")
def create_workspace_join_batch_job(
    req: CreateWorkspaceJoinBatchRequest,
    session: DbSession,
) -> dict:
    return _enqueue(session, "workspace_join_batch.run", req.model_dump())


@router.get("/workspace-join-batches")
def list_workspace_join_batches(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(WorkspaceJoinBatchModel).order_by(WorkspaceJoinBatchModel.created_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "team_workspace_id": row.team_workspace_id,
            "batch_status": row.batch_status,
            "activation_status": row.activation_status,
            "total_count": row.total_count,
            "success_count": row.success_count,
            "failed_count": row.failed_count,
        }
        for row in rows
    ]


@router.post("/workspace-join-batches/from-credentials")
def create_workspace_join_batch_from_credentials(
    req: CreateWorkspaceJoinBatchFromCredentialsRequest,
    session: DbSession,
) -> dict:
    local_session_factory = sessionmaker(
        bind=session.get_bind(),
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        batch_id = CreateWorkspaceBatchFromCredentialsWorkflow(
            session_factory=local_session_factory
        ).run(CreateWorkspaceBatchFromCredentialsInput(**req.model_dump()))
    except BatchWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="some codex credentials are already bound to another active batch",
        ) from exc
    return {"batch_id": batch_id}


@router.get("/workspace-join-batches/{batch_id}")
def get_workspace_join_batch(batch_id: str, session: DbSession) -> dict:
    batch = session.get(WorkspaceJoinBatchModel, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="batch not found")
    return {
        "id": batch.id,
        "team_workspace_id": batch.team_workspace_id,
        "batch_status": batch.batch_status,
        "activation_status": batch.activation_status,
    }


@router.get("/workspace-join-batches/{batch_id}/items")
def get_workspace_join_batch_items(batch_id: str, session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(WorkspaceJoinBatchItemModel)
        .where(WorkspaceJoinBatchItemModel.batch_id == batch_id)
        .order_by(WorkspaceJoinBatchItemModel.created_at)
    ).all()
    return [
        {
            "id": row.id,
            "batch_id": row.batch_id,
            "user_account_id": row.user_account_id,
            "team_workspace_id": row.team_workspace_id,
            "membership_id": row.membership_id,
            "codex_credential_id": row.codex_credential_id,
            "item_status": row.item_status,
            "batch_binding_status": row.batch_binding_status,
            "join_status": row.join_status,
            "token_status": row.token_status,
            "push_status": row.push_status,
            "plan_tag": row.plan_tag,
            "plan_type": row.plan_type,
            "downstream_provider": row.downstream_provider,
            "downstream_external_id": row.downstream_external_id,
            "failure_code": row.failure_code,
            "failure_message": row.failure_message,
        }
        for row in rows
    ]


@router.post("/workspace-join-batches/{batch_id}/activate")
def create_batch_activate_job(batch_id: str, session: DbSession) -> dict:
    return _enqueue(session, "workspace_join_batch.activate", {"batch_id": batch_id})


@router.get("/codex-credentials")
def list_codex_credentials(session: DbSession) -> list[dict]:
    rows = session.execute(
        select(
            CodexOAuthCredentialModel,
            UserAccountModel,
            TeamWorkspaceModel,
            WorkspaceJoinBatchItemModel,
            WorkspaceJoinBatchModel,
        )
        .join(UserAccountModel, UserAccountModel.id == CodexOAuthCredentialModel.user_account_id)
        .join(
            TeamWorkspaceModel,
            TeamWorkspaceModel.id == CodexOAuthCredentialModel.team_workspace_id,
        )
        .outerjoin(
            WorkspaceJoinBatchItemModel,
            (WorkspaceJoinBatchItemModel.codex_credential_id == CodexOAuthCredentialModel.id)
            & (WorkspaceJoinBatchItemModel.batch_binding_status == "active"),
        )
        .outerjoin(
            WorkspaceJoinBatchModel,
            WorkspaceJoinBatchModel.id == WorkspaceJoinBatchItemModel.batch_id,
        )
        .order_by(CodexOAuthCredentialModel.created_at.desc())
    ).all()
    return [
        {
            "id": credential.id,
            "user_account_id": credential.user_account_id,
            "user_email": account.email,
            "team_workspace_id": credential.team_workspace_id,
            "workspace_name": workspace.name,
            "external_workspace_id": workspace.external_workspace_id,
            "codex_client_id": credential.codex_client_id,
            "credential_status": credential.credential_status,
            "push_lifecycle_status": credential.push_lifecycle_status,
            "token_chatgpt_account_id": credential.token_chatgpt_account_id,
            "expires_at": credential.expires_at.isoformat() if credential.expires_at else "",
            "last_heartbeat_status": credential.last_heartbeat_status,
            "last_heartbeat_at": credential.last_heartbeat_at.isoformat()
            if credential.last_heartbeat_at
            else "",
            "bound_batch_item_id": batch_item.id if batch_item is not None else "",
            "bound_batch_id": batch.id if batch is not None else "",
            "bound_batch_name": batch.batch_name if batch is not None else "",
            "batch_binding_status": batch_item.batch_binding_status
            if batch_item is not None
            else "",
        }
        for credential, account, workspace, batch_item, batch in rows
    ]


@router.post("/codex-credentials/{credential_id}/heartbeat-job")
def create_codex_heartbeat_job(
    credential_id: str,
    session: DbSession,
) -> dict:
    return _enqueue(session, "codex_credential.heartbeat", {"codex_credential_id": credential_id})


@router.post("/codex-credentials/heartbeat-job")
def create_codex_heartbeat_bulk_job(
    req: HeartbeatCodexCredentialsRequest,
    session: DbSession,
) -> dict:
    return _create_codex_heartbeat_work_job(req=req, session=session)


@router.post("/codex-credentials/push-job")
def create_codex_push_bulk_job(
    req: PushCodexCredentialsRequest,
    session: DbSession,
) -> dict:
    return _create_codex_push_work_job(req=req, session=session)


@router.post("/codex-credentials/push-pending-job")
def create_pending_codex_push_job(
    req: PushPendingCodexCredentialsRequest,
    session: DbSession,
) -> dict:
    return _create_pending_codex_push_work_job(req=req, session=session)


@router.get("/downstream-channels")
def list_downstream_channels(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(DownstreamChannelModel).order_by(
            DownstreamChannelModel.provider_type,
            DownstreamChannelModel.name,
        )
    ).all()
    return [_downstream_channel_dict(row, session=session) for row in rows]


@router.post("/downstream-channels")
def create_downstream_channel(req: CreateDownstreamChannelRequest, session: DbSession) -> dict:
    now = datetime.now(UTC)
    provider_type = req.provider_type.strip()
    if provider_type not in DOWNSTREAM_PROVIDER_TYPES:
        raise HTTPException(status_code=400, detail="provider_type must be sub2api, cpa or local_sub2api")
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    base_url = _downstream_channel_base_url(provider_type, req.base_url)
    admin_key = req.admin_key.strip()
    if provider_type != "local_sub2api" and not base_url:
        raise HTTPException(status_code=400, detail="base_url is required")
    if provider_type != "local_sub2api" and not admin_key:
        raise HTTPException(status_code=400, detail="admin_key is required")
    channel = DownstreamChannelModel(
        id=f"downstream-channel-{uuid4()}",
        provider_type=provider_type,
        name=req.name.strip(),
        base_url=base_url,
        admin_key=admin_key,
        enabled=req.enabled,
        update_existing=req.update_existing,
        timeout_s=max(1, int(req.timeout_s or 30)),
        max_push_count=max(0, int(req.max_push_count or 0)),
        max_active_slots=max(0, int(req.max_active_slots)),
        push_balance=max(0, int(req.push_balance or 0)),
        created_at=now,
        updated_at=now,
    )
    session.add(channel)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="downstream channel already exists") from exc
    return _downstream_channel_dict(channel, session=session)


@router.patch("/downstream-channels/{channel_id}")
def patch_downstream_channel(
    channel_id: str,
    req: PatchDownstreamChannelRequest,
    session: DbSession,
) -> dict:
    channel = session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    if req.provider_type is not None:
        provider_type = req.provider_type.strip()
        if provider_type not in DOWNSTREAM_PROVIDER_TYPES:
            raise HTTPException(status_code=400, detail="provider_type must be sub2api, cpa or local_sub2api")
        channel.provider_type = provider_type
        if provider_type == "local_sub2api" and _looks_like_url(channel.base_url):
            channel.base_url = _local_sub2api_output_dir()
    if req.name is not None:
        if not req.name.strip():
            raise HTTPException(status_code=400, detail="name is required")
        channel.name = req.name.strip()
    if req.base_url is not None:
        base_url = _downstream_channel_base_url(channel.provider_type, req.base_url)
        if channel.provider_type != "local_sub2api" and not base_url:
            raise HTTPException(status_code=400, detail="base_url is required")
        channel.base_url = base_url
    if req.admin_key is not None:
        if channel.provider_type != "local_sub2api" and not req.admin_key.strip():
            raise HTTPException(status_code=400, detail="admin_key is required")
        channel.admin_key = req.admin_key.strip()
    if req.enabled is not None:
        channel.enabled = req.enabled
    if req.update_existing is not None:
        channel.update_existing = req.update_existing
    if req.timeout_s is not None:
        channel.timeout_s = max(1, int(req.timeout_s or 30))
    if req.max_push_count is not None:
        channel.max_push_count = max(0, int(req.max_push_count or 0))
    if req.max_active_slots is not None:
        channel.max_active_slots = max(0, int(req.max_active_slots or 0))
    if req.push_balance is not None:
        channel.push_balance = max(0, int(req.push_balance or 0))
    channel.updated_at = datetime.now(UTC)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="downstream channel already exists") from exc
    return _downstream_channel_dict(channel, session=session)


@router.post("/downstream-channels/{channel_id}/add-balance")
def add_downstream_channel_balance(
    channel_id: str,
    req: AddDownstreamChannelBalanceRequest,
    session: DbSession,
) -> dict:
    amount = int(req.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be greater than 0")
    channel = session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    channel.push_balance = max(0, int(channel.push_balance or 0)) + amount
    channel.updated_at = datetime.now(UTC)
    session.commit()
    return _downstream_channel_dict(channel, session=session)


@router.delete("/downstream-channels/{channel_id}")
def delete_downstream_channel(channel_id: str, session: DbSession) -> dict:
    channel = session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")

    active_push_count = session.scalar(
        select(func.count())
        .select_from(DownstreamCodexPushRecordModel)
            .where(
                DownstreamCodexPushRecordModel.downstream_channel_id == channel_id,
                DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
            )
    ) or 0
    if active_push_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"channel has {active_push_count} active pushed/pushing/failed records; delete after usage cleanup or retry release",
        )

    legacy_allocation_count = session.scalar(
        text(
            """
            SELECT count(*)
            FROM downstream_credential_allocations
            WHERE downstream_channel_id = :channel_id
              AND allocation_status <> 'released'
            """
        ),
        {"channel_id": channel_id},
    ) or 0
    if legacy_allocation_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"channel has {legacy_allocation_count} legacy allocations; release them before delete",
        )

    detached_push_record_count = session.scalar(
        select(func.count())
        .select_from(DownstreamCodexPushRecordModel)
        .where(DownstreamCodexPushRecordModel.downstream_channel_id == channel_id)
    ) or 0

    session.delete(channel)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="downstream channel is still referenced") from exc
    return {
        "id": channel_id,
        "deleted": True,
        "detached_push_records_count": detached_push_record_count,
    }


@router.get("/downstream-push-records")
def list_downstream_push_records(session: DbSession) -> list[dict]:
    rows = session.execute(
        select(DownstreamCodexPushRecordModel, DownstreamChannelModel)
        .outerjoin(
            DownstreamChannelModel,
            DownstreamChannelModel.id == DownstreamCodexPushRecordModel.downstream_channel_id,
        )
        .order_by(
            DownstreamCodexPushRecordModel.created_at.desc()
        )
    ).all()
    return [
        {
            "id": row.id,
            "batch_item_id": row.batch_item_id,
            "codex_credential_id": row.codex_credential_id,
            "downstream_channel_id": row.downstream_channel_id,
            "downstream_channel_name": channel.name if channel is not None else "",
            "downstream_provider": row.downstream_provider,
            "push_status": row.push_status,
            "downstream_external_id": row.downstream_external_id,
            "downstream_chatgpt_account_id": row.downstream_chatgpt_account_id,
            "token_chatgpt_account_id": row.token_chatgpt_account_id,
            "push_attempt_count": row.push_attempt_count,
            "usage_percent": row.usage_percent,
            "usage_status": row.usage_status,
            "last_usage_check_at": row.last_usage_check_at.isoformat()
            if row.last_usage_check_at
            else "",
            "used_at": row.used_at.isoformat() if row.used_at else "",
            "error_code": row.error_code,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }
        for row, channel in rows
    ]


@router.post("/downstream-push-records/repush")
def repush_downstream_records(
    req: RepushDownstreamRecordsRequest,
    session: DbSession,
) -> dict:
    record_ids = [item.strip() for item in req.downstream_push_record_ids if item.strip()]
    if not record_ids:
        raise HTTPException(status_code=400, detail="downstream_push_record_ids is required")

    now = datetime.now(UTC)
    results: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    skipped = 0
    for record_id in record_ids:
        record = session.get(DownstreamCodexPushRecordModel, record_id)
        if record is None:
            skipped += 1
            results.append({"record_id": record_id, "status": "skipped", "reason": "record_not_found"})
            continue
        if record.push_status != "pushed":
            skipped += 1
            results.append(
                {
                    "record_id": record_id,
                    "status": "skipped",
                    "reason": f"record_status_{record.push_status}",
                }
            )
            continue

        record.push_attempt_count = int(record.push_attempt_count or 0) + 1
        record.updated_at = now
        result = _repush_downstream_record(session=session, record=record)
        if result.get("ok"):
            succeeded += 1
            record.push_status = "pushed"
            record.usage_status = "active"
            record.error_code = ""
            record.error_message = ""
            record.updated_at = datetime.now(UTC)
            results.append(
                {
                    "record_id": record_id,
                    "status": "succeeded",
                    "downstream_external_id": record.downstream_external_id,
                }
            )
        else:
            failed += 1
            record.error_code = str(result.get("error_code") or "downstream_repush_failed")[:200]
            record.error_message = str(result.get("error_message") or "")[:1000]
            record.updated_at = datetime.now(UTC)
            results.append(
                {
                    "record_id": record_id,
                    "status": "failed",
                    "error_code": record.error_code,
                    "error_message": record.error_message,
                }
            )
    session.commit()
    return {
        "requested": len(record_ids),
        "succeeded": succeeded,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }


@router.post("/proxies/refresh-webshare-job")
def create_refresh_webshare_job(req: RefreshWebsharePoolRequest, session: DbSession) -> dict:
    download_url = req.download_url.strip()
    if not download_url:
        raise HTTPException(status_code=400, detail="download_url is required")
    if not download_url.startswith("https://proxy.webshare.io/"):
        raise HTTPException(status_code=400, detail="download_url must be a Webshare HTTPS URL")

    existing = session.scalars(
        select(JobModel)
        .where(
            JobModel.type == "proxy.refresh_webshare_pool",
            JobModel.job_status.in_(("queued", "running")),
        )
        .order_by(JobModel.created_at.desc())
        .limit(1)
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "webshare refresh job already queued or running",
                "job_id": existing.id,
            },
        )

    return _enqueue(session, "proxy.refresh_webshare_pool", {"download_url": download_url})


@router.post("/proxies/bind-account-job")
def create_bind_proxy_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "proxy.bind_account", input_json)


@router.post("/proxies/{proxy_id}/healthcheck-job")
def create_proxy_healthcheck_job(proxy_id: str, session: DbSession) -> dict:
    proxy = session.get(ProxyInventoryModel, proxy_id)
    if proxy is None:
        raise HTTPException(status_code=404, detail="proxy not found")

    now = datetime.now(UTC)
    job = JobModel(
        id=str(uuid4()),
        type="proxy.healthcheck",
        job_status="running",
        priority=0,
        input_json={"proxy_id": proxy_id},
        created_by="http",
        created_at=now,
        updated_at=now,
    )
    run = JobRunModel(
        id=str(uuid4()),
        job_id=job.id,
        run_status="running",
        attempt=1,
        started_at=now,
        output_json={},
    )
    session.add(job)
    session.add(run)
    session.commit()

    try:
        local_session_factory = sessionmaker(
            bind=session.get_bind(),
            autoflush=False,
            expire_on_commit=False,
        )
        output = HealthcheckProxyWorkflow(session_factory=local_session_factory).run(
            proxy_id=proxy_id
        )
    except Exception as exc:
        finished_at = datetime.now(UTC)
        run = session.get(JobRunModel, run.id)
        job = session.get(JobModel, job.id)
        if run is not None:
            run.run_status = "failed"
            run.finished_at = finished_at
            run.error_code = type(exc).__name__[:200]
            run.error_message = str(exc)[:1000]
        if job is not None:
            job.job_status = "failed"
            job.updated_at = finished_at
        session.commit()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    finished_at = datetime.now(UTC)
    run = session.get(JobRunModel, run.id)
    job = session.get(JobModel, job.id)
    if run is not None:
        run.run_status = "succeeded"
        run.finished_at = finished_at
        run.output_json = output
    if job is not None:
        job.job_status = "succeeded"
        job.updated_at = finished_at
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": "succeeded",
        **output,
    }


@router.post("/mail/allocate-job")
def create_allocate_mail_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "mail.allocate", input_json)


@router.post("/mail/poll-otp-job")
def create_poll_mail_otp_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "mail.poll_otp", input_json)


@router.post("/mail/mark-used-job")
def create_mark_mail_used_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "mail.mark_used", input_json)


@router.post("/mail/mark-failed-job")
def create_mark_mail_failed_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "mail.mark_failed", input_json)


@router.post("/mail/release-job")
def create_release_mail_job(
    input_json: dict[str, Any],
    session: DbSession,
) -> dict:
    return _enqueue(session, "mail.release", input_json)


@router.get("/proxies")
def list_proxies(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(ProxyInventoryModel).order_by(ProxyInventoryModel.created_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "provider": row.provider,
            "external_proxy_id": row.external_proxy_id,
            "connection_mode": row.connection_mode,
            "proxy_host": row.proxy_host,
            "proxy_port": row.proxy_port,
            "proxy_scheme": row.proxy_scheme,
            "country_code": row.country_code,
            "city_name": row.city_name,
            "proxy_status": row.proxy_status,
            "provider_valid": row.provider_valid,
            "last_provider_verification_at": (
                row.last_provider_verification_at.isoformat()
                if row.last_provider_verification_at
                else ""
            ),
            "last_healthcheck_at": (
                row.last_healthcheck_at.isoformat() if row.last_healthcheck_at else ""
            ),
        }
        for row in rows
    ]


@router.get("/mail-leases")
def list_mail_leases(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(ExternalMailLeaseModel).order_by(ExternalMailLeaseModel.created_at.desc())
    ).all()
    return [{"id": row.id, "email": row.email, "lease_status": row.lease_status} for row in rows]


def _downstream_channel_dict(channel: DownstreamChannelModel, *, session: Session | None = None) -> dict:
    active_slots = _active_downstream_slot_count(session, channel.id) if session is not None else 0
    allowed_slots = (
        _allowed_downstream_active_slots(session=session, channel=channel)
        if session is not None
        else max(0, int(channel.max_active_slots or 0))
    )
    remaining_slots = max(0, allowed_slots - active_slots)
    remaining_balance = max(0, int(channel.push_balance or 0))
    return {
        "id": channel.id,
        "provider_type": channel.provider_type,
        "name": channel.name,
        "base_url": channel.base_url,
        "admin_key_summary": _summarize_secret(channel.admin_key or ""),
        "enabled": channel.enabled,
        "update_existing": channel.update_existing,
        "timeout_s": channel.timeout_s,
        "max_push_count": channel.max_push_count,
        "max_active_slots": channel.max_active_slots,
        "allowed_active_slots": allowed_slots,
        "active_slot_count": active_slots,
        "remaining_active_slots": remaining_slots,
        "push_balance": channel.push_balance,
        "claimed_push_count": channel.claimed_push_count,
        "pushed_count": channel.pushed_count,
        "failed_push_count": channel.failed_push_count,
        "used_count": channel.used_count,
        "remaining_push_count": min(remaining_slots, remaining_balance),
        "last_test_status": "unknown",
        "last_test_at": "",
        "last_error_code": "",
        "last_error_message": "",
        "created_at": channel.created_at.isoformat(),
        "updated_at": channel.updated_at.isoformat(),
    }


def _downstream_channel_base_url(provider_type: str, value: str) -> str:
    text_value = str(value or "").strip()
    if provider_type == "local_sub2api":
        return text_value or _local_sub2api_output_dir()
    return text_value.rstrip("/")


def _local_sub2api_output_dir() -> str:
    return str((Path.cwd() / "runtime" / "local-sub2api").resolve())


def _looks_like_url(value: str) -> bool:
    text_value = str(value or "").strip().lower()
    return text_value.startswith("http://") or text_value.startswith("https://")


def _summarize_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _automation_schedule_dict(row: AutomationScheduleModel | None) -> dict:
    if row is None:
        return {}
    return {
        "id": row.id,
        "schedule_type": row.schedule_type,
        "schedule_status": row.schedule_status,
        "enabled": row.enabled,
        "interval_seconds": row.interval_seconds,
        "config_json": row.config_json,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else "",
        "next_run_at": row.next_run_at.isoformat() if row.next_run_at else "",
        "last_job_id": row.last_job_id,
        "last_run_status": row.last_run_status,
        "locked_by": row.locked_by,
        "locked_until": row.locked_until.isoformat() if row.locked_until else "",
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _automation_monitor_job_dict(*, session: Session, schedule: AutomationScheduleModel) -> dict:
    job = session.get(JobModel, schedule.last_job_id) if schedule.last_job_id else None
    run = None
    if job is not None:
        run = session.scalars(
            select(JobRunModel)
            .where(JobRunModel.job_id == job.id)
            .order_by(JobRunModel.started_at.desc().nullslast())
            .limit(1)
        ).first()
    work_summary = (
        _work_summary(session, job.id)
        if job is not None
        else {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0}
    )
    output = run.output_json if run is not None and isinstance(run.output_json, dict) else {}
    started_at = run.started_at if run is not None else None
    finished_at = run.finished_at if run is not None else None
    duration_ms = (
        int((finished_at - started_at).total_seconds() * 1000)
        if started_at is not None and finished_at is not None
        else 0
    )
    return {
        **_automation_schedule_dict(schedule),
        "last_job_status": job.job_status if job is not None else "",
        "last_run_id": run.id if run is not None else "",
        "last_started_at": started_at.isoformat() if started_at else "",
        "last_finished_at": finished_at.isoformat() if finished_at else "",
        "duration_ms": duration_ms,
        "item_count": int(output.get("item_count") or output.get("work_count") or sum(work_summary.values())),
        "succeeded": int(output.get("succeeded") or work_summary["succeeded"]),
        "failed": int(output.get("failed") or work_summary["failed"]),
        "skipped": int(output.get("skipped") or 0),
        "paused": int(output.get("paused") or 0),
        "queued": work_summary["queued"],
        "running": work_summary["running"],
        "cancelled": work_summary["cancelled"],
        "output_json": output,
    }


def _automation_console_event_dict(
    *,
    event: JobEventModel,
    run: JobRunModel,
    job: JobModel,
) -> dict:
    data_json = event.data_json if isinstance(event.data_json, dict) else {}
    return {
        "id": event.id,
        "job_id": job.id,
        "job_type": job.type,
        "run_id": run.id,
        "ts": event.ts.isoformat(),
        "level": event.level,
        "event_type": event.event_type,
        "message": event.message,
        "data_json": data_json,
        "data_summary": _summarize_json(data_json, max_chars=500),
    }


def _automation_console_fallback_items(
    *,
    session: Session,
    schedule_type: str,
    job_id: str,
    run_id: str,
    level: str,
    limit: int,
) -> list[dict]:
    if level.strip() and level.strip().upper() not in {"ALL", "INFO"}:
        return []
    stmt = select(JobRunModel, JobModel).join(JobModel, JobModel.id == JobRunModel.job_id)
    if run_id.strip():
        stmt = stmt.where(JobRunModel.id == run_id.strip())
    if job_id.strip():
        stmt = stmt.where(JobModel.id == job_id.strip())
    if schedule_type.strip():
        stmt = stmt.where(JobModel.type == schedule_type.strip())
    rows = session.execute(
        stmt.order_by(JobRunModel.started_at.desc().nullslast()).limit(max(1, min(limit, 100)))
    ).all()
    items: list[dict] = []
    for run, job in reversed(rows):
        output_json = run.output_json if isinstance(run.output_json, dict) else {}
        output_failed = int(output_json.get("failed") or 0)
        level_value = "ERROR" if run.run_status == "failed" or output_failed > 0 else "INFO"
        message = (
            f"job {job.type} completed with {output_failed} failed item(s); no job_events were recorded for this run"
            if output_failed > 0
            else f"job {job.type} {run.run_status}; no job_events were recorded for this run"
        )
        data_json = {
            "run_status": run.run_status,
            "attempt": run.attempt,
            "started_at": run.started_at.isoformat() if run.started_at else "",
            "finished_at": run.finished_at.isoformat() if run.finished_at else "",
            "error_code": run.error_code,
            "error_message": run.error_message,
            "output_json": output_json,
        }
        items.append(
            {
                "id": f"fallback-{run.id}",
                "job_id": job.id,
                "job_type": job.type,
                "run_id": run.id,
                "ts": (run.finished_at or run.started_at or datetime.now(UTC)).isoformat(),
                "level": level_value,
                "event_type": "job.run_summary",
                "message": message,
                "data_json": data_json,
                "data_summary": _summarize_json(data_json, max_chars=500),
            }
        )
    return items


def _limit_console_items_by_bytes(*, items: list[dict], max_bytes: int) -> tuple[list[dict], int, bool]:
    selected: list[dict] = []
    total = 0
    truncated = False
    for item in reversed(items):
        encoded_size = len(json.dumps(item, ensure_ascii=False, default=str).encode("utf-8"))
        if selected and total + encoded_size > max_bytes:
            truncated = True
            break
        if encoded_size > max_bytes:
            compact = {**item, "data_json": {}, "data_summary": item.get("data_summary", "")}
            encoded_size = len(json.dumps(compact, ensure_ascii=False, default=str).encode("utf-8"))
            item = compact
        selected.append(item)
        total += encoded_size
    selected.reverse()
    return selected, total, truncated or len(selected) < len(items)


def _summarize_json(value: Any, *, max_chars: int) -> str:
    if value in ({}, [], "", None):
        return ""
    text_value = json.dumps(value, ensure_ascii=False, default=str)
    if len(text_value) <= max_chars:
        return text_value
    return f"{text_value[:max_chars]}..."


def _fixed_automation_schedule_id(schedule_type: str) -> str:
    mapping = {
        "automation.workspace_invite_sync": "automation-schedule-workspace-invite-sync",
        "automation.workspace_authorize": "automation-schedule-workspace-authorize",
        "automation.codex_heartbeat": "automation-schedule-codex-heartbeat",
        "automation.downstream_push": "automation-schedule-downstream-push",
        "automation.downstream_usage_cleanup": "automation-schedule-downstream-usage-cleanup",
    }
    schedule_id = mapping.get(schedule_type)
    if not schedule_id:
        raise HTTPException(status_code=400, detail=f"unsupported automation schedule type: {schedule_type}")
    return schedule_id


def _workspace_dict(row: TeamWorkspaceModel, *, admin_email: str = "") -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "external_workspace_id": row.external_workspace_id,
        "name": row.name,
        "plan_type": row.plan_type,
        "seat_limit": row.seat_limit,
        "seats_in_use": row.seats_in_use,
        "seats_entitled": row.seats_entitled,
        "last_subscription_sync_at": row.last_subscription_sync_at.isoformat()
        if row.last_subscription_sync_at
        else "",
        "workspace_status": row.workspace_status,
        "source_admin_session_id": row.source_admin_session_id,
        "admin_email": admin_email,
    }


def _workspace_self_user_ids(
    *,
    session: Session,
    team_admin_session_id: str,
    account_id: str,
) -> set[str]:
    check = session.scalars(
        select(TeamAdminAccountCheckModel)
        .where(TeamAdminAccountCheckModel.team_admin_session_id == team_admin_session_id)
        .order_by(TeamAdminAccountCheckModel.checked_at.desc())
    ).first()
    if check is None:
        return set()
    account = _workspace_account_from_check(check.raw_check_json, account_id)
    values = {
        str(account.get("account_owner_id") or "").strip(),
        str(account.get("account_user_id") or "").strip(),
        str(account.get("user_id") or "").strip(),
    }
    return {item for item in values if item}


def _fetch_workspace_members(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
    page_size: int,
) -> list[dict[str, Any]]:
    headers = _workspace_api_headers(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
    )
    members: list[dict[str, Any]] = []
    with curl_requests.Session(impersonate="chrome136") as client:
        for offset in range(0, 100000, page_size):
            response = client.get(
                f"https://chatgpt.com/backend-api/accounts/{account_id}/users",
                params={"offset": str(offset), "limit": str(page_size), "query": ""},
                headers=headers,
                timeout=45,
            )
            payload = _json_response_or_detail(response)
            if int(response.status_code or 0) >= 400:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": "workspace users list failed",
                        "http_status": response.status_code,
                        "body": payload,
                    },
                )
            items = _list_items(payload, ("items", "users", "data"))
            members.extend(items)
            total = _response_total(payload)
            if not items or len(items) < page_size or (total is not None and len(members) >= total):
                break
    return members


def _fetch_workspace_invites(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
    page_size: int,
) -> list[dict[str, Any]]:
    headers = _workspace_api_headers(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
    )
    invites: list[dict[str, Any]] = []
    with curl_requests.Session(impersonate="chrome136") as client:
        for offset in range(0, 100000, page_size):
            response = client.get(
                f"https://chatgpt.com/backend-api/accounts/{account_id}/invites",
                params={"offset": str(offset), "limit": str(page_size), "query": ""},
                headers=headers,
                timeout=45,
            )
            payload = _json_response_or_detail(response)
            if int(response.status_code or 0) >= 400:
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": "workspace invites list failed",
                        "http_status": response.status_code,
                        "body": payload,
                    },
                )
            items = _list_items(payload, ("items", "invites", "data"))
            invites.extend(items)
            total = _response_total(payload)
            if not items or len(items) < page_size or (total is not None and len(invites) >= total):
                break
    return invites


def _split_removable_workspace_members(
    members: list[dict[str, Any]],
    *,
    self_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    targets: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for member in members:
        user_id = _workspace_member_user_id(member)
        role = _workspace_member_role(member)
        email = _workspace_member_email(member)
        reason = ""
        if not user_id:
            reason = "missing_user_id"
        elif user_id in self_ids or str(member.get("account_user_id") or "").strip() in self_ids:
            reason = "self_or_current_admin"
        elif role == "account-owner":
            reason = "account_owner"
        if reason:
            skipped.append({"user_id": user_id, "email": email, "role": role, "reason": reason})
            continue
        targets.append(member)
    return targets, skipped


def _delete_workspace_members(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
    members: list[dict[str, Any]],
    concurrency: int,
) -> list[dict[str, Any]]:
    if not members:
        return []
    headers = _workspace_api_headers(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
    )
    max_workers = min(concurrency, len(members))

    def delete_one(member: dict[str, Any]) -> dict[str, Any]:
        user_id = _workspace_member_user_id(member)
        email = _workspace_member_email(member)
        role = _workspace_member_role(member)
        try:
            with curl_requests.Session(impersonate="chrome136") as client:
                response = client.delete(
                    f"https://chatgpt.com/backend-api/accounts/{account_id}/users/{user_id}",
                    headers=headers,
                    timeout=45,
                )
        except curl_requests.RequestsError as exc:
            return {
                "ok": False,
                "user_id": user_id,
                "email": email,
                "role": role,
                "error_code": "request_failed",
                "error_message": str(exc),
            }
        payload = _json_response_or_detail(response)
        ok = int(response.status_code or 0) < 400
        return {
            "ok": ok,
            "user_id": user_id,
            "email": email,
            "role": role,
            "http_status": int(response.status_code or 0),
            "body": payload if not ok else {},
        }

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_index = {
            executor.submit(delete_one, member): index for index, member in enumerate(members)
        }
        ordered: dict[int, dict[str, Any]] = {}
        for future in as_completed(future_by_index):
            ordered[future_by_index[future]] = future.result()
        for index in range(len(members)):
            results.append(ordered[index])
    return results


def _revoke_workspace_invites(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
    invites: list[dict[str, Any]],
    concurrency: int,
) -> list[dict[str, Any]]:
    if not invites:
        return []
    max_workers = min(concurrency, len(invites))

    def revoke_one(invite: dict[str, Any]) -> dict[str, Any]:
        email_address = _remote_invite_email(invite)
        if not email_address:
            return {
                "ok": False,
                "email_address": "",
                "invite_id": str(invite.get("id") or ""),
                "error_code": "missing_email_address",
                "error_message": "invite item missing email_address",
            }
        return _revoke_workspace_invite(
            access_token=access_token,
            cookie_header=cookie_header,
            account_id=account_id,
            email_address=email_address,
            invite_id=str(invite.get("id") or ""),
        )

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_by_index = {
            executor.submit(revoke_one, invite): index for index, invite in enumerate(invites)
        }
        ordered: dict[int, dict[str, Any]] = {}
        for future in as_completed(future_by_index):
            ordered[future_by_index[future]] = future.result()
        for index in range(len(invites)):
            results.append(ordered[index])
    return results


def _revoke_workspace_invite(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
    email_address: str,
    invite_id: str = "",
) -> dict[str, Any]:
    headers = _workspace_api_headers(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
    )
    headers["content-type"] = "application/json"
    try:
        with curl_requests.Session(impersonate="chrome136") as client:
            response = client.delete(
                f"https://chatgpt.com/backend-api/accounts/{account_id}/invites",
                headers=headers,
                json={"email_address": email_address},
                timeout=45,
            )
    except curl_requests.RequestsError as exc:
        return {
            "ok": False,
            "email_address": email_address,
            "invite_id": invite_id,
            "error_code": "request_failed",
            "error_message": str(exc),
        }
    body = _json_response_or_detail(response)
    ok = int(response.status_code or 0) < 400
    return {
        "ok": ok,
        "email_address": email_address,
        "invite_id": invite_id,
        "http_status": int(response.status_code or 0),
        "body": body if not ok else {},
    }


def _prune_workspace_memberships_by_remote_state(
    *,
    session: Session,
    workspace: TeamWorkspaceModel,
    remote_members: list[dict[str, Any]],
    remote_invites: list[dict[str, Any]],
) -> dict:
    now = datetime.now(UTC)
    remote_user_ids: set[str] = set()
    for member in remote_members:
        remote_user_ids.update(_remote_user_ids(member))
    invited_emails = {
        _remote_invite_email(invite).strip().lower()
        for invite in remote_invites
        if _remote_invite_email(invite).strip()
    }
    if remote_members and not remote_user_ids:
        return {
            "remote_user_id_count": 0,
            "remote_invite_email_count": len(invited_emails),
            "matched_remote_member_count": 0,
            "matched_remote_invite_count": 0,
            "removed_local_count": 0,
            "deleted_credential_count": 0,
            "released_batch_item_count": 0,
            "unbound_downstream_count": 0,
            "delete_skipped_reason": "remote members response has no user ids; local delete skipped",
        }

    rows = session.execute(
        select(MembershipModel, UserAccountModel, UserAccountAuthModel)
        .join(UserAccountModel, UserAccountModel.id == MembershipModel.user_account_id)
        .outerjoin(
            UserAccountAuthModel,
            UserAccountAuthModel.user_account_id == MembershipModel.user_account_id,
        )
        .where(MembershipModel.team_workspace_id == workspace.id)
    ).all()
    credentials = session.scalars(
        select(CodexOAuthCredentialModel).where(
            CodexOAuthCredentialModel.team_workspace_id == workspace.id
        )
    ).all()
    credentials_by_account: dict[str, list[CodexOAuthCredentialModel]] = {}
    for credential in credentials:
        credentials_by_account.setdefault(credential.user_account_id, []).append(credential)
    remote_members_by_user_id: dict[str, dict[str, Any]] = {}
    for member in remote_members:
        for remote_user_id in _remote_user_ids(member):
            remote_members_by_user_id.setdefault(remote_user_id, member)

    stale_user_account_ids: list[str] = []
    matched_remote_member_count = 0
    matched_remote_invite_count = 0
    protected_credential_member_count = 0
    for membership, account, auth in rows:
        account_credentials = credentials_by_account.get(account.id, [])
        local_user_ids = _local_account_remote_user_ids(
            account=account,
            auth=auth,
            membership=membership,
            credentials=account_credentials,
        )
        email = account.email.strip().lower()
        matched_user_ids = local_user_ids & remote_user_ids
        if matched_user_ids:
            matched_remote_member = remote_members_by_user_id.get(sorted(matched_user_ids)[0])
            if matched_remote_member is not None:
                _write_membership_remote_snapshot(
                    membership=membership,
                    account=account,
                    member=matched_remote_member,
                    now=now,
                )
            matched_remote_member_count += 1
            continue
        if email and email in invited_emails:
            matched_remote_invite_count += 1
            continue
        if account_credentials:
            protected_credential_member_count += 1
            continue
        stale_user_account_ids.append(account.id)

    removed = _delete_local_memberships_with_credentials(
        session=session,
        workspace_id=workspace.id,
        user_account_ids=stale_user_account_ids,
        now=now,
    )
    return {
        "remote_user_id_count": len(remote_user_ids),
        "remote_invite_email_count": len(invited_emails),
        "matched_remote_member_count": matched_remote_member_count,
        "matched_remote_invite_count": matched_remote_invite_count,
        "protected_credential_member_count": protected_credential_member_count,
        "removed_local_count": removed["deleted_membership_count"],
        "deleted_credential_count": removed["deleted_credential_count"],
        "released_batch_item_count": removed["released_batch_item_count"],
        "unbound_downstream_count": removed["unbound_downstream_count"],
        "delete_skipped_reason": "",
    }


def _delete_local_memberships_with_credentials(
    *,
    session: Session,
    workspace_id: str,
    user_account_ids: list[str],
    now: datetime,
    mark_protected_downstream_used: bool = True,
) -> dict:
    if not user_account_ids:
        return {
            "deleted_membership_count": 0,
            "deleted_credential_count": 0,
            "released_batch_item_count": 0,
            "unbound_downstream_count": 0,
        }
    credential_ids = session.scalars(
        select(CodexOAuthCredentialModel.id).where(
            CodexOAuthCredentialModel.team_workspace_id == workspace_id,
            CodexOAuthCredentialModel.user_account_id.in_(user_account_ids),
        )
    ).all()
    unbound_downstream_count = 0
    protected_credential_ids: set[str] = set()
    if credential_ids:
        protected_credential_ids = set(
            session.scalars(
                select(DownstreamCodexPushRecordModel.codex_credential_id).where(
                    DownstreamCodexPushRecordModel.codex_credential_id.in_(credential_ids)
                )
            ).all()
        )
        if protected_credential_ids and mark_protected_downstream_used:
            unbound_downstream_count = session.execute(
                update(DownstreamCodexPushRecordModel)
                .where(
                    DownstreamCodexPushRecordModel.codex_credential_id.in_(
                        protected_credential_ids
                    ),
                    DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed")),
                )
                .values(
                    push_status="used",
                    usage_status="used",
                    used_at=now,
                    updated_at=now,
                )
            ).rowcount
            session.execute(
                update(CodexOAuthCredentialModel)
                .where(CodexOAuthCredentialModel.id.in_(protected_credential_ids))
                .values(push_lifecycle_status="used", updated_at=now)
            )
        elif protected_credential_ids:
            records_to_release = session.scalars(
                select(DownstreamCodexPushRecordModel).where(
                    DownstreamCodexPushRecordModel.codex_credential_id.in_(
                        protected_credential_ids
                    ),
                    DownstreamCodexPushRecordModel.push_status.in_(("pushing", "pushed", "failed")),
                )
            ).all()
            unbound_downstream_count = len(records_to_release)
            used_credential_ids: set[str] = set()
            blocked_credential_ids: set[str] = set()
            for record in records_to_release:
                if int(record.usage_percent or 0) >= 60:
                    record.push_status = "used"
                    record.usage_status = "used"
                    record.used_at = now
                    used_credential_ids.add(record.codex_credential_id)
                    record.error_code = "credential_invalidated_phone_verification_required"
                    record.error_message = (
                        "marked used after phone verification failure because usage_percent>=60"
                    )
                else:
                    _refund_skipped_downstream_quota(session=session, record=record, now=now)
                    record.push_status = "skipped"
                    record.usage_status = "check_failed"
                    blocked_credential_ids.add(record.codex_credential_id)
                    record.error_code = "credential_invalidated_phone_verification_required"
                    record.error_message = (
                        "marked invalid after phone verification failure because usage_percent<60"
                    )
                record.updated_at = now
            if used_credential_ids:
                session.execute(
                    update(CodexOAuthCredentialModel)
                    .where(CodexOAuthCredentialModel.id.in_(used_credential_ids))
                    .values(push_lifecycle_status="used", updated_at=now)
                )
            if blocked_credential_ids:
                session.execute(
                    update(CodexOAuthCredentialModel)
                    .where(CodexOAuthCredentialModel.id.in_(blocked_credential_ids))
                    .values(push_lifecycle_status="blocked", updated_at=now)
                )
    released_batch_item_count = session.execute(
        update(WorkspaceJoinBatchItemModel)
        .where(
            WorkspaceJoinBatchItemModel.team_workspace_id == workspace_id,
            WorkspaceJoinBatchItemModel.user_account_id.in_(user_account_ids),
        )
        .values(
            batch_binding_status="released",
            membership_id=None,
            codex_credential_id=None,
            updated_at=now,
        )
    ).rowcount
    delete_credentials_stmt = delete(CodexOAuthCredentialModel).where(
        CodexOAuthCredentialModel.team_workspace_id == workspace_id,
        CodexOAuthCredentialModel.user_account_id.in_(user_account_ids),
    )
    if protected_credential_ids:
        delete_credentials_stmt = delete_credentials_stmt.where(
            ~CodexOAuthCredentialModel.id.in_(protected_credential_ids)
        )
    deleted_credential_count = session.execute(delete_credentials_stmt).rowcount
    deleted_membership_count = session.execute(
        delete(MembershipModel).where(
            MembershipModel.team_workspace_id == workspace_id,
            MembershipModel.user_account_id.in_(user_account_ids),
        )
    ).rowcount
    return {
        "deleted_membership_count": int(deleted_membership_count or 0),
        "deleted_credential_count": int(deleted_credential_count or 0),
        "released_batch_item_count": int(released_batch_item_count or 0),
        "unbound_downstream_count": int(unbound_downstream_count or 0),
    }


def _refund_skipped_downstream_quota(
    *,
    session: Session,
    record: DownstreamCodexPushRecordModel,
    now: datetime,
) -> None:
    if record.downstream_channel_id is None:
        return
    if record.push_status not in {"pushing", "pushed", "failed"}:
        return
    channel = session.get(DownstreamChannelModel, record.downstream_channel_id)
    if channel is None:
        return
    channel.push_balance = max(0, int(channel.push_balance or 0)) + 1
    channel.claimed_push_count = max(0, int(channel.claimed_push_count or 0) - 1)
    channel.updated_at = now


def _local_account_remote_user_ids(
    *,
    account: UserAccountModel,
    auth: UserAccountAuthModel | None,
    membership: MembershipModel,
    credentials: list[CodexOAuthCredentialModel],
) -> set[str]:
    values = {
        str(account.openai_user_id or "").strip(),
        str(membership.remote_user_id or "").strip(),
        str(membership.remote_account_user_id or "").strip(),
    }
    if auth is not None:
        values.update(_jwt_identity_user_ids(auth.access_token))
    values.update(_jwt_identity_user_ids(membership.chatgpt_web_backend_access_token))
    values.update(_jwt_identity_user_ids(membership.chatgpt_web_backend_id_token))
    for credential in credentials:
        values.add(str(credential.account_id or "").strip())
        values.update(_jwt_identity_user_ids(credential.access_token))
        values.update(_jwt_identity_user_ids(credential.id_token))
    return _stable_openai_user_ids(values)


def _jwt_identity_user_ids(token: str) -> set[str]:
    if not token or token.count(".") < 2:
        return set()
    try:
        claims = decode_access_token_claims(token)
    except Exception:
        return set()
    values = {
        str(claims.account_id or "").strip(),
        str(claims.chatgpt_account_user_id or "").strip(),
    }
    raw = claims.raw if isinstance(claims.raw, dict) else {}
    values.update(
        str(raw.get(key) or "").strip()
        for key in ("sub", "user_id", "chatgpt_user_id", "account_id")
    )
    auth = raw.get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        values.update(
            str(auth.get(key) or "").strip()
            for key in ("chatgpt_account_user_id", "chatgpt_user_id", "user_id", "account_id")
        )
    return _stable_openai_user_ids(values)


def _write_membership_remote_snapshot(
    *,
    membership: MembershipModel,
    account: UserAccountModel,
    member: dict[str, Any],
    now: datetime,
) -> None:
    remote_user_id = _workspace_member_user_id(member)
    remote_account_user_id = str(member.get("account_user_id") or member.get("accountUserId") or "").strip()
    if remote_user_id:
        membership.remote_user_id = remote_user_id
        if not account.openai_user_id:
            account.openai_user_id = remote_user_id
            account.updated_at = now
    membership.remote_account_user_id = remote_account_user_id
    membership.remote_seat_type = str(member.get("seat_type") or "").strip()
    membership.remote_role = str(member.get("role") or "").strip()
    membership.remote_synced_at = now
    membership.updated_at = now


def _remote_user_ids(item: dict[str, Any]) -> set[str]:
    values = set()
    for key in ("id", "user_id", "userId", "account_user_id", "accountUserId"):
        values.update(_openai_user_id_candidates(item.get(key)))
    user = item.get("user")
    if isinstance(user, dict):
        for key in ("id", "user_id", "userId"):
            values.update(_openai_user_id_candidates(user.get(key)))
    return _stable_openai_user_ids(values)


def _workspace_member_user_id(member: dict[str, Any]) -> str:
    user = member.get("user")
    for value in (
        member.get("user_id"),
        member.get("id"),
        user.get("id") if isinstance(user, dict) else "",
        user.get("user_id") if isinstance(user, dict) else "",
        member.get("account_user_id"),
        member.get("accountUserId"),
    ):
        user_ids = _stable_openai_user_ids(_openai_user_id_candidates(value))
        if user_ids:
            return sorted(user_ids)[0]
    return ""


def _stable_openai_user_ids(values: set[str] | list[str]) -> set[str]:
    result: set[str] = set()
    for value in values:
        result.update(_openai_user_id_candidates(value))
    return {value for value in result if value.startswith("user-") and "__" not in value}


def _openai_user_id_candidates(value: object) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    values = {text}
    if "__" in text:
        prefix = text.split("__", 1)[0].strip()
        if prefix:
            values.add(prefix)
    return values


def _workspace_member_email(member: dict[str, Any]) -> str:
    user = member.get("user")
    profile = member.get("profile")
    for value in (
        member.get("email"),
        user.get("email") if isinstance(user, dict) else "",
        profile.get("email") if isinstance(profile, dict) else "",
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _workspace_member_role(member: dict[str, Any]) -> str:
    for key in ("role", "account_user_role", "user_role"):
        text = str(member.get(key) or "").strip()
        if text:
            return text
    return ""


def _remote_invite_email(item: dict[str, Any]) -> str:
    for key in ("email", "email_address", "emailAddress", "recipient_email"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    user = item.get("user")
    if isinstance(user, dict):
        return str(user.get("email") or "").strip()
    return ""


def _list_items(payload: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _response_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    for key in ("total", "total_count", "totalCount"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _workspace_api_headers(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
) -> dict[str, str]:
    headers = {
        "authorization": f"Bearer {access_token}",
        "accept": "application/json",
        "content-type": "application/json",
        "chatgpt-account-id": account_id,
        "origin": "https://chatgpt.com",
        "referer": "https://chatgpt.com/admin",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    if cookie_header:
        headers["cookie"] = cookie_header
    return headers


def _json_response_or_detail(response) -> Any:
    text = str(getattr(response, "text", "") or "")
    try:
        return response.json() if text else {}
    except Exception:
        return {"body": text[:4000]}


def _parse_browser_headers_text(value: str) -> dict[str, str]:
    raw_value = value.strip()
    if not raw_value:
        return {}
    if raw_value.startswith('"') and raw_value.endswith('"'):
        try:
            raw_value = str(json.loads(raw_value))
        except json.JSONDecodeError:
            pass
    if "\\n" in raw_value or "\\r" in raw_value:
        raw_value = raw_value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    allowed = {
        "accept-language",
        "cookie",
        "priority",
        "sec-ch-ua",
        "sec-ch-ua-arch",
        "sec-ch-ua-bitness",
        "sec-ch-ua-full-version",
        "sec-ch-ua-full-version-list",
        "sec-ch-ua-mobile",
        "sec-ch-ua-model",
        "sec-ch-ua-platform",
        "sec-ch-ua-platform-version",
        "user-agent",
    }
    ignored = {
        "accept",
        "accept-encoding",
        "authorization",
        "connection",
        "content-length",
        "host",
        "origin",
        "referer",
        "sec-fetch-dest",
        "sec-fetch-mode",
        "sec-fetch-site",
        "sec-fetch-user",
        "upgrade-insecure-requests",
    }
    metadata = {
        "request url",
        "request method",
        "status code",
        "remote address",
        "referrer policy",
    }
    pseudo_headers = {":authority", ":method", ":path", ":scheme"}
    known_keys = allowed | ignored | metadata | pseudo_headers
    lines = [line.rstrip() for line in raw_value.splitlines()]
    parsed: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if not line:
            continue
        if ":" in line and not line.startswith(":"):
            key, inline_value = line.split(":", 1)
            header_value = inline_value.strip()
        else:
            key = line
            header_value = ""
        key = key.strip().lower()
        if key.startswith(":"):
            if index < len(lines):
                index += 1
            continue
        if key in ignored or key not in allowed:
            if not header_value and index < len(lines) and key in known_keys:
                index += 1
            continue
        if not header_value and index < len(lines):
            next_line = lines[index].strip()
            next_key = ""
            if ":" in next_line:
                next_key = next_line.split(":", 1)[0].strip().lower()
            if next_line and not next_line.startswith(":") and next_key not in known_keys:
                header_value = next_line
                index += 1
        if header_value:
            parsed[key] = header_value
    return parsed


def _fetch_accounts_check(
    *,
    access_token: str,
    cookie_header: str,
    browser_headers: dict[str, str] | None = None,
    timezone_offset_min: int,
) -> dict[str, Any]:
    if not access_token:
        raise HTTPException(status_code=400, detail="raw_session_json missing accessToken")
    browser_headers = browser_headers or {}
    headers = {
        "accept": "*/*",
        "accept-language": browser_headers.get("accept-language", "zh-CN,zh;q=0.9"),
        "authorization": f"Bearer {access_token}",
        "cookie": cookie_header,
        "oai-client-build-number": "7646290",
        "oai-client-version": "prod-497f333866796e100096ad083b51ca949d22e751",
        "oai-language": "zh-CN",
        "oai-session-id": str(uuid4()),
        "priority": browser_headers.get("priority", "u=1, i"),
        "referer": "https://chatgpt.com/admin/members?tab=invites",
        "sec-ch-ua": browser_headers.get("sec-ch-ua", '"Chromium";v="135", "Not-A.Brand";v="8"'),
        "sec-ch-ua-arch": browser_headers.get("sec-ch-ua-arch", '"arm"'),
        "sec-ch-ua-bitness": browser_headers.get("sec-ch-ua-bitness", '"64"'),
        "sec-ch-ua-full-version": browser_headers.get(
            "sec-ch-ua-full-version",
            '"135.0.7049.72"',
        ),
        "sec-ch-ua-full-version-list": browser_headers.get(
            "sec-ch-ua-full-version-list",
            '"Chromium";v="135.0.7049.72", "Not-A.Brand";v="8.0.0.0"',
        ),
        "sec-ch-ua-mobile": browser_headers.get("sec-ch-ua-mobile", "?0"),
        "sec-ch-ua-model": browser_headers.get("sec-ch-ua-model", '""'),
        "sec-ch-ua-platform": browser_headers.get("sec-ch-ua-platform", '"macOS"'),
        "sec-ch-ua-platform-version": browser_headers.get(
            "sec-ch-ua-platform-version",
            '"15.6.1"',
        ),
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": browser_headers.get(
            "user-agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/135.0.0.0 Safari/537.36",
        ),
        "x-openai-target-path": "/backend-api/accounts/check/v4-2023-04-27",
        "x-openai-target-route": "/backend-api/accounts/check/{version}",
    }
    if not cookie_header:
        raise HTTPException(status_code=400, detail="team admin cookie_header is required")
    url = (
        "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27"
        f"?timezone_offset_min={int(timezone_offset_min)}"
    )
    try:
        with curl_requests.Session(impersonate="chrome136") as client:
            response = client.get(url, headers=headers, timeout=30)
    except curl_requests.RequestsError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"accounts/check request failed: {exc}",
        ) from exc
    if int(response.status_code or 0) >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"accounts/check failed: http_status={response.status_code}",
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="accounts/check response must be object")
    return payload


def _fetch_workspace_subscription(
    *,
    access_token: str,
    cookie_header: str,
    account_id: str,
) -> dict[str, Any]:
    if not account_id:
        return {}
    headers = _workspace_api_headers(
        access_token=access_token,
        cookie_header=cookie_header,
        account_id=account_id,
    )
    try:
        with curl_requests.Session(impersonate="chrome136") as client:
            response = client.get(
                "https://chatgpt.com/backend-api/subscriptions",
                params={"account_id": account_id},
                headers=headers,
                timeout=30,
            )
    except curl_requests.RequestsError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"workspace subscription request failed: {exc}",
        ) from exc
    payload = _json_response_or_detail(response)
    if int(response.status_code or 0) >= 400:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "workspace subscription failed",
                "account_id": account_id,
                "http_status": response.status_code,
                "body": payload,
            },
        )
    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="workspace subscription response must be object")
    return payload


def _workspace_account_from_check(raw_check: dict[str, Any], account_id: str) -> dict[str, Any]:
    accounts = raw_check.get("accounts")
    if isinstance(accounts, dict):
        node = accounts.get(account_id)
        if isinstance(node, dict):
            account = node.get("account")
            if isinstance(account, dict):
                return account
            return node
    for item in _find_workspace_candidates(raw_check):
        if _workspace_external_id(item) == account_id:
            account = item.get("account")
            if isinstance(account, dict):
                return account
            return item
    return {}


def _extract_workspaces_from_session_and_check(
    raw_session: dict[str, Any],
    raw_check: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidates.extend(_find_workspace_candidates(raw_check))
    account = raw_session.get("account")
    if isinstance(account, dict) and _is_team_workspace_account(account):
        candidates.append(account)
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for item in candidates:
        external_id = _workspace_external_id(item)
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        result.append(item)
    return result


def _find_workspace_candidates(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        account = value.get("account")
        if isinstance(account, dict) and _workspace_external_id(account):
            if _is_team_workspace_account(account):
                found.append(account)
        elif _workspace_external_id(value) and _is_team_workspace_account(value):
            found.append(value)
        for child in value.values():
            found.extend(_find_workspace_candidates(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_workspace_candidates(child))
    return found


def _workspace_external_id(item: dict[str, Any]) -> str:
    for key in ("id", "account_id", "accountId", "workspace_id", "workspaceId"):
        value = str(item.get(key) or "").strip()
        if value.startswith(("acc-", "account-", "org-", "team-")) or _looks_uuid(value):
            return value
    return ""


def _is_team_workspace_account(item: dict[str, Any]) -> bool:
    structure = str(item.get("structure") or "").strip().lower()
    if structure == "workspace":
        return True
    if structure == "personal":
        return False
    if item.get("organization_id") or item.get("organizationId"):
        return True
    plan_type = str(item.get("plan_type") or item.get("planType") or "").strip().lower()
    return any(marker in plan_type for marker in ("team", "business", "enterprise"))


def _upsert_workspace_from_admin_source(
    *,
    session: Session,
    source_admin_session_id: str,
    item: dict[str, Any],
    now: datetime,
) -> TeamWorkspaceModel | None:
    external_id = _workspace_external_id(item)
    if not external_id:
        return None
    name = str(
        item.get("name")
        or item.get("workspace_name")
        or item.get("workspaceName")
        or item.get("display_name")
        or item.get("displayName")
        or external_id
    )
    subscription = item.get("_subscription")
    subscription = subscription if isinstance(subscription, dict) else {}
    plan_type = str(
        subscription.get("plan_type")
        or subscription.get("planType")
        or item.get("plan_type")
        or item.get("planType")
        or item.get("plan")
        or ""
    )
    seat_limit = _safe_int(
        subscription.get("seats_entitled")
        or subscription.get("seatsEntitled")
        or item.get("seat_limit")
        or item.get("seatLimit")
        or 0
    )
    seats_in_use = _safe_int(
        subscription.get("seats_in_use")
        or subscription.get("seatsInUse")
        or item.get("seats_in_use")
        or item.get("seatsInUse")
        or 0
    )
    workspace = session.scalars(
        select(TeamWorkspaceModel).where(
            TeamWorkspaceModel.provider == "openai_chatgpt",
            TeamWorkspaceModel.external_workspace_id == external_id,
        )
    ).first()
    if workspace is None:
        workspace = TeamWorkspaceModel(
            id=f"team-workspace-{uuid4()}",
            provider="openai_chatgpt",
            external_workspace_id=external_id,
            name=name,
            plan_type=plan_type,
            seat_limit=seat_limit,
            seats_in_use=seats_in_use,
            seats_entitled=seat_limit,
            workspace_status="active",
            source_admin_session_id=source_admin_session_id,
            raw_workspace_json=item,
            last_subscription_sync_at=now if subscription else None,
            created_at=now,
            updated_at=now,
        )
        session.add(workspace)
    else:
        workspace.name = name
        workspace.plan_type = plan_type
        workspace.seat_limit = seat_limit
        workspace.seats_in_use = seats_in_use
        workspace.seats_entitled = seat_limit
        workspace.workspace_status = "active"
        workspace.source_admin_session_id = source_admin_session_id
        workspace.raw_workspace_json = item
        workspace.last_subscription_sync_at = now if subscription else workspace.last_subscription_sync_at
        workspace.updated_at = now
    return workspace


def _session_admin_email(raw: dict[str, Any], access_token: str) -> str:
    user = raw.get("user")
    if isinstance(user, dict) and user.get("email"):
        return str(user.get("email") or "")
    claims = _decode_jwt_payload(access_token)
    profile = claims.get("https://api.openai.com/profile")
    if isinstance(profile, dict):
        return str(profile.get("email") or "")
    return ""


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    import base64
    import json

    if token.count(".") < 2:
        return {}
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


def _parse_datetime_or_none(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _looks_uuid(value: str) -> bool:
    pattern = (
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    )
    return bool(re.fullmatch(pattern, value))


def _safe_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _enqueue(session: Session, job_type: str, input_json: dict[str, Any]) -> dict:
    job = JobQueue(session).enqueue(job_type=job_type, input_json=input_json)
    session.commit()
    return {"job_id": job.id, "job_status": job.job_status}


def _run_job_work_now(*, session_factory, job_id: str, concurrency: int) -> None:
    def run_loop() -> None:
        runner = JobRunner(session_factory)
        register_core_handlers(runner, session_factory=session_factory, settings=get_settings())
        while runner.run_one_work_for_job(job_id) is not None:
            pass

    if concurrency <= 1:
        run_loop()
        return

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(run_loop) for _ in range(concurrency)]
        for future in as_completed(futures):
            future.result()


def _work_summary(session: Session, job_id: str) -> dict[str, int]:
    rows = session.scalars(
        select(WorkItemModel).where(WorkItemModel.job_id == job_id)
    ).all()
    return {
        "queued": sum(1 for row in rows if row.work_status == "queued"),
        "running": sum(1 for row in rows if row.work_status == "running"),
        "succeeded": sum(1 for row in rows if row.work_status == "succeeded"),
        "failed": sum(1 for row in rows if row.work_status == "failed"),
        "cancelled": sum(1 for row in rows if row.work_status == "cancelled"),
    }
