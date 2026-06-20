from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from curl_cffi import requests as curl_requests
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
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
from refactor_app.application.workflows.proxy import HealthcheckProxyWorkflow
from refactor_app.config.settings import get_settings
from refactor_app.domain.enums import AccountStatus
from refactor_app.infrastructure.db.models import (
    CodexOAuthCredentialModel,
    DownstreamCodexPushRecordModel,
    ExternalMailLeaseModel,
    JobModel,
    JobRunModel,
    MembershipModel,
    ProxyInventoryModel,
    TeamAdminAccountCheckModel,
    TeamAdminSessionModel,
    TeamWorkspaceModel,
    UserAccountAuthModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
    WorkItemModel,
    WorkspaceJoinBatchItemModel,
    WorkspaceJoinBatchModel,
)

router = APIRouter(tags=["resources"])
DbSession = Annotated[Session, Depends(get_db_session)]
CODEX_BROWSER_AUTH_CONCURRENCY_LIMIT = 5


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


class RefreshWebsharePoolRequest(BaseModel):
    download_url: str


class BackfillSessionRtRequest(BaseModel):
    user_account_ids: list[str]
    created_by: str = ""
    concurrency: int = 1


class ImportTeamAdminSessionRequest(BaseModel):
    raw_session_json: dict[str, Any]
    cookie_header: str = ""
    timezone_offset_min: int = -480
    fetch_accounts_check: bool = True


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
            cookie_header=req.cookie_header,
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
        admin_session.cookie_header = req.cookie_header
        admin_session.expires_at = expires_at
        admin_session.imported_at = now
        admin_session.updated_at = now
    session.flush()

    check_payload: dict[str, Any] = {}
    if req.fetch_accounts_check:
        check_payload = _fetch_accounts_check(
            access_token=access_token,
            cookie_header=req.cookie_header,
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
        workspace = _upsert_workspace_from_admin_source(
            session=session,
            source_admin_session_id=admin_session.id,
            item=item,
            now=now,
        )
        if workspace is not None:
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
            workspace_status=req.workspace_status,
            created_at=now,
            updated_at=now,
        )
        session.add(workspace)
    else:
        workspace.name = req.name
        workspace.plan_type = req.plan_type
        workspace.seat_limit = req.seat_limit
        workspace.workspace_status = req.workspace_status
        workspace.updated_at = now
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


@router.get("/memberships")
def list_memberships(
    session: DbSession,
    admin_email: str = "",
    external_workspace_id: str = "",
) -> list[dict]:
    stmt = (
        select(MembershipModel, UserAccountModel, TeamWorkspaceModel, TeamAdminSessionModel)
        .join(UserAccountModel, UserAccountModel.id == MembershipModel.user_account_id)
        .join(TeamWorkspaceModel, TeamWorkspaceModel.id == MembershipModel.team_workspace_id)
        .outerjoin(
            TeamAdminSessionModel,
            TeamAdminSessionModel.id == TeamWorkspaceModel.source_admin_session_id,
        )
        .order_by(MembershipModel.created_at.desc())
    )
    if admin_email:
        stmt = stmt.where(TeamAdminSessionModel.admin_email.ilike(f"%{admin_email.strip()}%"))
    if external_workspace_id:
        stmt = stmt.where(
            TeamWorkspaceModel.external_workspace_id.ilike(f"%{external_workspace_id.strip()}%")
        )
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
            "can_invite": membership.can_invite,
            "failure_code": membership.failure_code,
            "failure_message": membership.failure_message,
        }
        for membership, account, workspace, admin_session in rows
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


@router.get("/downstream-push-records")
def list_downstream_push_records(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(DownstreamCodexPushRecordModel).order_by(
            DownstreamCodexPushRecordModel.created_at.desc()
        )
    ).all()
    return [
        {
            "id": row.id,
            "batch_item_id": row.batch_item_id,
            "downstream_provider": row.downstream_provider,
            "push_status": row.push_status,
            "downstream_chatgpt_account_id": row.downstream_chatgpt_account_id,
            "token_chatgpt_account_id": row.token_chatgpt_account_id,
        }
        for row in rows
    ]


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


def _workspace_dict(row: TeamWorkspaceModel, *, admin_email: str = "") -> dict:
    return {
        "id": row.id,
        "provider": row.provider,
        "external_workspace_id": row.external_workspace_id,
        "name": row.name,
        "plan_type": row.plan_type,
        "seat_limit": row.seat_limit,
        "workspace_status": row.workspace_status,
        "source_admin_session_id": row.source_admin_session_id,
        "admin_email": admin_email,
    }


def _fetch_accounts_check(
    *,
    access_token: str,
    cookie_header: str,
    timezone_offset_min: int,
) -> dict[str, Any]:
    if not access_token:
        raise HTTPException(status_code=400, detail="raw_session_json missing accessToken")
    headers = {
        "authorization": f"Bearer {access_token}",
        "accept": "application/json",
        "origin": "https://chatgpt.com",
        "referer": "https://chatgpt.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    if cookie_header:
        headers["cookie"] = cookie_header
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
    plan_type = str(item.get("plan_type") or item.get("planType") or item.get("plan") or "")
    seat_limit = _safe_int(item.get("seat_limit") or item.get("seatLimit") or 0)
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
            workspace_status="active",
            source_admin_session_id=source_admin_session_id,
            raw_workspace_json=item,
            created_at=now,
            updated_at=now,
        )
        session.add(workspace)
    else:
        workspace.name = name
        workspace.plan_type = plan_type
        workspace.seat_limit = seat_limit
        workspace.workspace_status = "active"
        workspace.source_admin_session_id = source_admin_session_id
        workspace.raw_workspace_json = item
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
