from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
import json
from socket import gethostname
from threading import Thread
from time import sleep
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from refactor_app.api.dependencies import get_db_session
from refactor_app.application.jobs.handlers import register_core_handlers
from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.application.jobs.runner import JobRunner
from refactor_app.application.workflows.proxy import (
    ProxyWorkflowError,
    bind_team_admin_static_proxy_in_session,
    ensure_team_admin_static_proxy_url_in_session,
    reassign_team_admin_static_proxy_in_session,
)
from refactor_app.application.workflows.space_membership_invite_sync import (
    SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
    SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
    SpaceMembershipInviteSyncWorkflow,
    SpaceMembershipInviteSyncWorkflowError,
)
from refactor_app.application.workflows.space_recycle import (
    SpaceRecycleSweepInput,
    SpaceRecycleSweepWorkflow,
    manually_settle_pushed_binding_from_usage_state,
)
from refactor_app.application.workflows.space_usage import SpaceUsageError, infer_credential_type
from refactor_app.config.settings import get_settings
from refactor_app.domain.enums import AccountStatus
from refactor_app.infrastructure.db.engine import make_engine, make_session_factory
from refactor_app.infrastructure.db.models import (
    AccountSessionOtpSnapshotModel,
    AutomationScheduleModel,
    DownstreamChannelCredentialTypeBalanceModel,
    DownstreamChannelModel,
    ExternalMailLeaseModel,
    JobEventModel,
    JobModel,
    JobRunModel,
    ProxyInventoryModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceMembershipModel,
    SpaceModel,
    SpacePushBindingModel,
    SpacePushAttemptModel,
    TeamAdminProxyBindingModel,
    TeamAdminSessionModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
    WorkItemModel,
)
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTClientError,
    OpenAIChatGPTClientConfig,
    decode_access_token_claims,
)
from refactor_app.plugins.openai_chatgpt.plugin import OpenAIChatGPTPlugin

router = APIRouter(tags=["resources"])
DbSession = Annotated[Session, Depends(get_db_session)]

SPACE_CREDENTIAL_TYPES = ("personal_account", "team_5h_weekly", "team_monthly")
SPACE_AUTOMATION_TYPES = (
    "automation.space_membership_invite_sync",
    "automation.space_authorize",
    "automation.space_downstream_push",
    "automation.space_recycle_sweep",
)
DOWNSTREAM_PROVIDER_TYPES = {"sub2api", "cpa", "local_sub2api", "custom_http"}
CUSTOM_HTTP_PAYLOAD_TYPES = {"", "sub2api", "sub2api_admin_accounts", "cpa"}

_SCHEDULER_STARTED = False


class ImportUserAccountRequest(BaseModel):
    id: str = ""
    email: str
    account_status: str = AccountStatus.ACTIVE.value
    password: str = ""


class PatchUserAccountRequest(BaseModel):
    account_status: str | None = None
    password: str | None = None


class BackfillSessionRtRequest(BaseModel):
    user_account_ids: list[str]
    created_by: str = ""
    work_count: int = 10


class CreateBusinessAccessTokenCredentialsJobRequest(BaseModel):
    user_account_ids: list[str]
    external_space_id: str
    session_access_token: str = ""
    credential_name_prefix: str = "codex"
    cookie_header: str = ""
    space_name: str = ""
    owner_user_account_id: str = ""
    source_admin_session_id: str = ""
    created_by: str = ""
    work_count: int = 5


class PushSpaceCredentialsRequest(BaseModel):
    space_credential_ids: list[str]
    downstream_channel_id: str
    created_by: str = ""
    work_count: int = 5


class PushPendingSpaceCredentialsRequest(BaseModel):
    downstream_channel_id: str
    created_by: str = ""
    work_count: int = 5


class SpaceRecycleSweepJobRequest(BaseModel):
    created_by: str = ""
    limit: int = 100
    work_count: int = 5


class ManualSettleSpacePushRecordsRequest(BaseModel):
    space_credential_ids: list[str]
    created_by: str = ""


class ProtocolRegistrationJobRequest(BaseModel):
    mode: str
    count: int = 1
    work_count: int = 1
    use_proxy: bool = True
    mail_provider: str = "outlook"
    email_domain: str = ""
    project_key: str = "openai-register"
    caller_id: str = "refactor-app-protocol-registration"
    phone_provider: str = "hero_sms"
    phone_base_url: str = "https://hero-sms.com/stubs/handler_api.php"
    phone_api_key_env: str = "HERO_SMS_API_KEY"
    phone_service: str = "tg"
    phone_country: str = "2"
    phone_countries: list[str] = []
    phone_max_price: str = ""
    phone_country_max_prices: dict[str, str] = {}
    phone_max_number_attempts: int = 3
    phone_otp_timeout_s: int = 180
    phone_otp_poll_interval_s: float = 3.0
    created_by: str = ""


class SyncRemoteSpaceMembershipsRequest(BaseModel):
    page_size: int = 100


class ImportTeamAdminSessionRequest(BaseModel):
    raw_session_json: dict[str, Any]
    cookie_header: str = ""
    accounts_check_headers_text: str = ""
    timezone_offset_min: int = -480
    fetch_accounts_check: bool = False


class CreateDownstreamChannelRequest(BaseModel):
    provider_type: str
    name: str
    base_url: str
    admin_key: str = ""
    custom_payload_type: str = ""
    custom_auth_header_name: str = ""
    custom_auth_header_value: str = ""
    enabled: bool = True
    update_existing: bool = False
    timeout_s: int = 30
    sub2api_concurrency: int = 10
    sub2api_group_ids: str = ""
    max_push_count: int = 2
    max_active_slots: int = 2
    push_balance: int = 0


class PatchDownstreamChannelRequest(BaseModel):
    provider_type: str | None = None
    name: str | None = None
    base_url: str | None = None
    admin_key: str | None = None
    custom_payload_type: str | None = None
    custom_auth_header_name: str | None = None
    custom_auth_header_value: str | None = None
    enabled: bool | None = None
    update_existing: bool | None = None
    timeout_s: int | None = None
    sub2api_concurrency: int | None = None
    sub2api_group_ids: str | None = None
    max_push_count: int | None = None
    max_active_slots: int | None = None
    push_balance: int | None = None


class PatchDownstreamChannelCredentialTypeBalanceRequest(BaseModel):
    max_active_slots: int | None = None
    push_balance: int | None = None
    balance_status: str | None = None


class AddDownstreamChannelCredentialTypeBalanceRequest(BaseModel):
    amount: int


class RefreshWebsharePoolRequest(BaseModel):
    download_url: str
    proxy_type: str = "proxyserver"


class CreateAutomationScheduleRequest(BaseModel):
    schedule_type: str
    interval_seconds: int = 60
    config_json: dict[str, Any] = {}
    enabled: bool = True
    created_by: str = ""


class PatchAutomationScheduleRequest(BaseModel):
    enabled: bool | None = None
    schedule_status: str | None = None
    interval_seconds: int | None = None
    config_json: dict[str, Any] | None = None


@router.get("/user-accounts")
def list_user_accounts(session: DbSession) -> list[dict]:
    rows = session.scalars(select(UserAccountModel).order_by(UserAccountModel.created_at.desc())).all()
    return [_user_account_dict(row) for row in rows]


@router.post("/user-accounts/import")
def import_user_account(req: ImportUserAccountRequest, session: DbSession) -> dict:
    now = datetime.now(UTC)
    account_id = req.id.strip() or f"user-account-{uuid4()}"
    row = session.get(UserAccountModel, account_id)
    if row is None:
        row = UserAccountModel(
            id=account_id,
            email=req.email.strip(),
            account_status=req.account_status,
            password=req.password,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.email = req.email.strip()
        row.account_status = req.account_status
        if req.password:
            row.password = req.password
        row.updated_at = now
    session.commit()
    return _user_account_dict(row)


@router.patch("/user-accounts/{user_account_id}")
def patch_user_account(
    user_account_id: str,
    req: PatchUserAccountRequest,
    session: DbSession,
) -> dict:
    row = session.get(UserAccountModel, user_account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user account not found")
    if req.account_status is not None:
        row.account_status = req.account_status
    if req.password is not None:
        row.password = req.password
    row.updated_at = datetime.now(UTC)
    session.commit()
    return _user_account_dict(row)


@router.delete("/user-accounts/{user_account_id}")
def delete_user_account(user_account_id: str, session: DbSession) -> dict:
    row = session.get(UserAccountModel, user_account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user account not found")
    deleted_proxy_bindings = session.query(UserAccountProxyBindingModel).filter(
        UserAccountProxyBindingModel.user_account_id == user_account_id
    ).delete(synchronize_session=False)
    session.delete(row)
    session.commit()
    return {
        "user_account_id": user_account_id,
        "deleted": True,
        "deleted_proxy_bindings": int(deleted_proxy_bindings or 0),
    }


@router.post("/user-accounts/backfill-session-rt-job")
def create_backfill_session_rt_job(req: BackfillSessionRtRequest, session: DbSession) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_session_rt",
        work_type="account.backfill_session_rt",
    )


@router.post("/user-accounts/backfill-session-job")
def create_backfill_session_job(req: BackfillSessionRtRequest, session: DbSession) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_session",
        work_type="account.backfill_session",
    )


@router.post("/user-accounts/backfill-rt-job")
def create_backfill_rt_job(req: BackfillSessionRtRequest, session: DbSession) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_rt",
        work_type="account.backfill_rt",
    )


@router.get("/spaces")
def list_spaces(session: DbSession) -> dict:
    rows = session.scalars(select(SpaceModel).order_by(SpaceModel.created_at.desc())).all()
    return {"items": [_space_dict(row) for row in rows]}


@router.post("/spaces/{space_id}/memberships/sync-remote")
def sync_remote_space_memberships(
    space_id: str,
    req: SyncRemoteSpaceMembershipsRequest,
    session: DbSession,
) -> dict:
    openai_provider = OpenAIChatGPTPlugin.from_config(
        OpenAIChatGPTClientConfig(
            auth_base_url=get_settings().openai_auth_base_url,
            chatgpt_base_url=get_settings().openai_chatgpt_base_url,
        )
    )
    try:
        return SpaceMembershipInviteSyncWorkflow(
            session_factory=_session_factory_from_session(session),
            openai_provider=openai_provider,
        ).sync_remote_memberships_only(space_id=space_id, page_size=max(1, int(req.page_size or 100)))
    except SpaceMembershipInviteSyncWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OpenAIChatGPTClientError, ProxyWorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/space-credentials")
def list_space_credentials(session: DbSession) -> dict:
    rows = session.scalars(
        select(SpaceCredentialModel).order_by(SpaceCredentialModel.created_at.desc())
    ).all()
    return {"items": [_space_credential_dict(session=session, credential=row) for row in rows]}


@router.get("/space-push-records")
def list_space_push_records(session: DbSession) -> dict:
    rows = session.scalars(
        select(SpacePushBindingModel).order_by(SpacePushBindingModel.updated_at.desc())
    ).all()
    return {"items": [_space_push_record_dict(session=session, binding=row) for row in rows]}


@router.post("/space-push-records/manual-settle")
def manual_settle_space_push_records(
    req: ManualSettleSpacePushRecordsRequest,
    session: DbSession,
) -> dict:
    credential_ids = [item.strip() for item in req.space_credential_ids if item.strip()]
    if not credential_ids:
        raise HTTPException(status_code=400, detail="space_credential_ids is required")
    results = [
        manually_settle_pushed_binding_from_usage_state(
            session=session,
            space_credential_id=space_credential_id,
        )
        for space_credential_id in credential_ids
    ]
    session.commit()
    summary = {
        "used": 0,
        "skipped": 0,
        "ignored": 0,
        "failed": 0,
    }
    items = []
    for result in results:
        if result.push_status in summary:
            summary[result.push_status] += 1
        else:
            summary["failed"] += 1
        items.append(
            {
                "space_credential_id": result.space_credential_id,
                "push_status": result.push_status,
                "reason": result.reason,
                "usage_percent": result.usage_percent,
            }
        )
    return {
        "selected_count": len(credential_ids),
        **summary,
        "items": items,
    }


@router.post("/space-credentials/business-access-token-job")
def create_business_access_token_credentials_job(
    req: CreateBusinessAccessTokenCredentialsJobRequest,
    session: DbSession,
) -> dict:
    return _create_business_access_token_work_job(req=req, session=session)


@router.post("/space-credentials/push-job")
def create_space_credentials_push_job(req: PushSpaceCredentialsRequest, session: DbSession) -> dict:
    return _create_space_push_work_job(req=req, session=session)


@router.post("/space-credentials/push-pending-job")
def create_pending_space_credentials_push_job(
    req: PushPendingSpaceCredentialsRequest,
    session: DbSession,
) -> dict:
    return _create_pending_space_push_work_job(req=req, session=session)


@router.post("/spaces/recycle-sweep-job")
def create_space_recycle_sweep_job(req: SpaceRecycleSweepJobRequest, session: DbSession) -> dict:
    job = JobQueue(session).enqueue(
        job_type="space.recycle.sweep",
        input_json={
            "limit": max(1, int(req.limit or 100)),
            "work_count": max(1, int(req.work_count or 5)),
        },
        created_by=req.created_by,
    )
    session.commit()
    return {"job_id": job.id, "job_status": job.job_status}


@router.post("/account-protocol-registration/jobs")
def create_protocol_registration_job(req: ProtocolRegistrationJobRequest, session: DbSession) -> dict:
    if req.mode not in ("email_protocol_no_phone", "phone_protocol_bind_email"):
        raise HTTPException(status_code=400, detail=f"unsupported protocol registration mode: {req.mode}")
    job = JobQueue(session).enqueue(
        job_type="account.protocol_register",
        input_json={
            "mode": req.mode,
            "count": max(1, int(req.count or 1)),
            "work_count": max(1, int(req.work_count or 1)),
            "use_proxy": bool(req.use_proxy),
            "mail_provider": req.mail_provider,
            "email_domain": req.email_domain,
            "project_key": req.project_key,
            "caller_id": req.caller_id,
            "phone_provider": req.phone_provider,
            "phone_base_url": req.phone_base_url,
            "phone_api_key_env": req.phone_api_key_env,
            "phone_service": req.phone_service,
            "phone_country": req.phone_country,
            "phone_countries": req.phone_countries,
            "phone_max_price": req.phone_max_price,
            "phone_country_max_prices": req.phone_country_max_prices,
            "phone_max_number_attempts": max(1, int(req.phone_max_number_attempts or 3)),
            "phone_otp_timeout_s": max(1, int(req.phone_otp_timeout_s or 180)),
            "phone_otp_poll_interval_s": max(1.0, float(req.phone_otp_poll_interval_s or 3.0)),
        },
        created_by=req.created_by,
    )
    session.commit()
    return {"job_id": job.id, "job_status": job.job_status}


@router.post("/team-admin-sessions/import")
def import_team_admin_session(req: ImportTeamAdminSessionRequest, session: DbSession) -> dict:
    now = datetime.now(UTC)
    access_token = _session_access_token(req.raw_session_json)
    try:
        claims = decode_access_token_claims(access_token) if access_token else None
    except OpenAIChatGPTClientError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    claim_raw = claims.raw if claims is not None else {}
    profile_claim = claim_raw.get("https://api.openai.com/profile") or {}
    if not isinstance(profile_claim, dict):
        profile_claim = {}
    admin_email = str(
        req.raw_session_json.get("email")
        or req.raw_session_json.get("admin_email")
        or claim_raw.get("email")
        or profile_claim.get("email", "")
        or ""
    )
    account_payload = req.raw_session_json.get("account")
    if not isinstance(account_payload, dict):
        account_payload = {}
    external_space_id = _admin_session_account_id(account_payload)
    row = TeamAdminSessionModel(
        id=f"team-admin-session-{uuid4()}",
        admin_email=admin_email,
        raw_session_json=req.raw_session_json,
        access_token=access_token,
        session_token=str(req.raw_session_json.get("session_token") or ""),
        cookie_header=req.cookie_header,
        expires_at=None,
        imported_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.flush()
    try:
        proxy_binding = bind_team_admin_static_proxy_in_session(
            session=session,
            team_admin_session_id=row.id,
            bind_reason="team_admin_session_import",
        )
    except ProxyWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    spaces: list[dict] = []
    if external_space_id:
        openai_provider = OpenAIChatGPTPlugin.from_config(
            OpenAIChatGPTClientConfig(
                auth_base_url=get_settings().openai_auth_base_url,
                chatgpt_base_url=get_settings().openai_chatgpt_base_url,
            )
        )
        try:
            usage_payload = _fetch_business_usage_with_admin_proxy_retry(
                session=session,
                openai_provider=openai_provider,
                admin_session=row,
                access_token=access_token,
                chatgpt_account_id=external_space_id,
            )
            credential_type = infer_credential_type(
                space_type="business",
                usage_payload=usage_payload,
            )
        except (OpenAIChatGPTClientError, SpaceUsageError, ProxyWorkflowError) as exc:
            raise HTTPException(status_code=400, detail=f"business space usage probe failed: {exc}") from exc
        subscription_payload: dict[str, Any] = {}
        try:
            proxy_url = ensure_team_admin_static_proxy_url_in_session(
                session=session,
                team_admin_session_id=row.id,
                bind_reason="team_admin_session_import_subscription",
            )
            subscription_payload = openai_provider.fetch_subscription(
                access_token=access_token,
                account_id=external_space_id,
                cookie_header=row.cookie_header,
                proxy_url=proxy_url,
            )
        except Exception:
            subscription_payload = {}
        space = _upsert_business_space_from_admin_session(
            session=session,
            account_payload=account_payload,
            usage_payload=usage_payload,
            subscription_payload=subscription_payload,
            admin_session=row,
            admin_email=admin_email,
            credential_type=credential_type,
            now=now,
        )
        spaces.append(_space_dict(space))
    session.commit()
    return {
        "team_admin_session_id": row.id,
        "admin_email": row.admin_email,
        "team_admin_proxy_binding_id": proxy_binding.id,
        "proxy_id": proxy_binding.proxy_id,
        "space_count": len(spaces),
        "spaces": spaces,
    }


def _admin_session_account_id(account_payload: dict[str, Any]) -> str:
    return str(
        account_payload.get("id")
        or account_payload.get("account_id")
        or account_payload.get("accountId")
        or ""
    ).strip()


def _upsert_business_space_from_admin_session(
    *,
    session: Session,
    account_payload: dict[str, Any],
    usage_payload: dict[str, Any],
    subscription_payload: dict[str, Any],
    admin_session: TeamAdminSessionModel,
    admin_email: str,
    credential_type: str,
    now: datetime,
) -> SpaceModel:
    external_space_id = _admin_session_account_id(account_payload)
    if not external_space_id:
        raise HTTPException(status_code=400, detail="admin session account.id is required")
    space = session.scalars(
        select(SpaceModel).where(
            SpaceModel.provider == "openai_chatgpt",
            SpaceModel.external_space_id == external_space_id,
        )
    ).first()
    if space is None:
        space = SpaceModel(
            id=f"space-{uuid4()}",
            provider="openai_chatgpt",
            external_space_id=external_space_id,
            owner_user_account_id="",
            name="",
            space_type="business",
            auth_mode="backend_access_token",
            credential_type=credential_type,
            plan_type="",
            seat_limit=0,
            seats_in_use=0,
            seats_entitled=0,
            space_status="active",
            source_admin_session_id=admin_session.id,
            raw_space_json={},
            created_at=now,
            updated_at=now,
        )
        session.add(space)
    space.space_type = "business"
    space.auth_mode = "backend_access_token"
    space.credential_type = credential_type
    space.space_status = "active"
    space.source_admin_session_id = admin_session.id
    space.name = str(
        account_payload.get("name")
        or account_payload.get("display_name")
        or account_payload.get("displayName")
        or admin_email
        or external_space_id
    ).strip()
    space.plan_type = str(
        subscription_payload.get("plan_type")
        or subscription_payload.get("planType")
        or usage_payload.get("plan_type")
        or account_payload.get("planType")
        or account_payload.get("plan_type")
        or ""
    ).strip()
    seats_entitled = _safe_positive_int(
        subscription_payload.get("seats_entitled") or subscription_payload.get("seatsEntitled")
    )
    seats_in_use = _safe_positive_int(
        subscription_payload.get("seats_in_use") or subscription_payload.get("seatsInUse")
    )
    if seats_entitled:
        space.seats_entitled = seats_entitled
        space.seat_limit = seats_entitled
    if seats_in_use:
        space.seats_in_use = seats_in_use
    space.raw_space_json = {
        "admin_session_account": account_payload,
        "wham_usage": usage_payload,
        "subscription": subscription_payload,
    }
    if subscription_payload:
        space.last_subscription_sync_at = now
    space.updated_at = now
    return space


def _safe_positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _fetch_business_usage_with_admin_proxy_retry(
    *,
    session: Session,
    openai_provider: OpenAIChatGPTPlugin,
    admin_session: TeamAdminSessionModel,
    access_token: str,
    chatgpt_account_id: str,
    max_attempts: int = 3,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(max(1, int(max_attempts or 1))):
        proxy_url = ensure_team_admin_static_proxy_url_in_session(
            session=session,
            team_admin_session_id=admin_session.id,
            bind_reason="team_admin_session_import_usage_probe",
        )
        try:
            return openai_provider.fetch_wham_usage(
                access_token=access_token,
                chatgpt_account_id=chatgpt_account_id,
                cookie_header=admin_session.cookie_header,
                proxy_url=proxy_url,
            )
        except Exception as exc:
            if not _is_proxy_transport_error(exc):
                raise
            last_error = exc
            reassign_team_admin_static_proxy_in_session(
                session=session,
                team_admin_session_id=admin_session.id,
                error_code=f"usage_probe_proxy_error_attempt_{attempt + 1}",
                bind_reason="team_admin_session_import_usage_probe_retry",
            )
            session.flush()
    raise ProxyWorkflowError(
        "business space usage probe proxy failed after retry: "
        f"{type(last_error).__name__}: {last_error}"
    )


def _is_proxy_transport_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}"
    markers = (
        "ProxyError",
        "CONNECT tunnel failed",
        "Proxy CONNECT aborted",
        "curl: (56)",
        "UNEXPECTED_EOF",
        "Server disconnected",
        "Connection closed abruptly",
    )
    return any(marker in message for marker in markers)


@router.get("/team-admin-sessions")
def list_team_admin_sessions(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(TeamAdminSessionModel).order_by(TeamAdminSessionModel.imported_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "admin_email": row.admin_email,
            "session_source": row.session_source,
            "has_access_token": bool(row.access_token),
            "has_cookie_header": bool(row.cookie_header),
            "proxy_binding": _team_admin_proxy_binding_dict(session=session, team_admin_session_id=row.id),
            "expires_at": _iso(row.expires_at),
            "imported_at": _iso(row.imported_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]


@router.delete("/team-admin-sessions/{team_admin_session_id}")
def delete_team_admin_session(team_admin_session_id: str, session: DbSession) -> dict:
    row = session.get(TeamAdminSessionModel, team_admin_session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="team admin session not found")
    spaces = session.scalars(
        select(SpaceModel).where(SpaceModel.source_admin_session_id == team_admin_session_id)
    ).all()
    deleted_space_ids = [space.id for space in spaces]
    deleted_external_space_ids = [space.external_space_id for space in spaces]
    deleted_space_count = len(spaces)
    deleted_membership_count = int(
        session.scalar(
            select(func.count()).where(SpaceMembershipModel.space_id.in_(deleted_space_ids))
        )
        or 0
    ) if deleted_space_ids else 0
    deleted_credential_count = int(
        session.scalar(
            select(func.count()).where(SpaceCredentialModel.space_id.in_(deleted_space_ids))
        )
        or 0
    ) if deleted_space_ids else 0
    for space in spaces:
        session.delete(space)
    session.delete(row)
    session.commit()
    return {
        "team_admin_session_id": team_admin_session_id,
        "deleted": True,
        "deleted_space_count": deleted_space_count,
        "deleted_space_ids": deleted_space_ids,
        "deleted_external_space_ids": deleted_external_space_ids,
        "deleted_membership_count": deleted_membership_count,
        "deleted_credential_count": deleted_credential_count,
        "preserved_push_records": True,
    }


@router.get("/memberships")
def list_memberships(
    session: DbSession,
    space_id: str = "",
    space: str = "",
    external_space_id: str = "",
    user_account_id: str = "",
    membership_status: str = "",
    session_account_detected: str = "",
) -> list[dict]:
    stmt = (
        select(SpaceMembershipModel, UserAccountModel, SpaceModel)
        .join(UserAccountModel, UserAccountModel.id == SpaceMembershipModel.user_account_id)
        .join(SpaceModel, SpaceModel.id == SpaceMembershipModel.space_id)
        .order_by(SpaceMembershipModel.created_at.desc())
    )
    selected_space_id = space_id.strip() or space.strip()
    if selected_space_id:
        stmt = stmt.where(SpaceMembershipModel.space_id == selected_space_id)
    if external_space_id.strip():
        stmt = stmt.where(SpaceModel.external_space_id == external_space_id.strip())
    if user_account_id.strip():
        stmt = stmt.where(SpaceMembershipModel.user_account_id == user_account_id.strip())
    if membership_status.strip():
        stmt = stmt.where(SpaceMembershipModel.membership_status == membership_status.strip())
    detected_filter = session_account_detected.strip().lower()
    if detected_filter in {"yes", "true", "1"}:
        stmt = stmt.where(SpaceMembershipModel.session_account_detected.is_(True))
    if detected_filter in {"no", "false", "0"}:
        stmt = stmt.where(SpaceMembershipModel.session_account_detected.is_(False))
    rows = session.execute(stmt).all()
    return [
        {
            "id": membership.id,
            "space_id": membership.space_id,
            "external_space_id": space.external_space_id,
            "space_name": space.name,
            "space_type": space.space_type,
            "credential_type": space.credential_type,
            "user_account_id": membership.user_account_id,
            "user_email": account.email,
            "email": account.email,
            "role": membership.role,
            "membership_status": membership.membership_status,
            "invite_permission": membership.invite_permission,
            "seat_status": membership.seat_status,
            "can_invite": membership.can_invite,
            "session_account_detected": membership.session_account_detected,
            "remote_user_id": membership.remote_user_id,
            "remote_account_user_id": membership.remote_account_user_id,
            "remote_role": membership.remote_role,
            "remote_synced_at": _iso(membership.remote_synced_at),
            "last_probe_status": membership.last_probe_status,
            "last_probe_at": _iso(membership.last_probe_at),
            "failure_code": membership.failure_code,
            "failure_message": membership.failure_message,
            "created_at": _iso(membership.created_at),
            "updated_at": _iso(membership.updated_at),
        }
        for membership, account, space in rows
    ]


@router.get("/automation/schedules")
def list_automation_schedules(session: DbSession) -> list[dict]:
    _ensure_default_space_automation_schedules(session=session)
    session.commit()
    rows = session.scalars(
        select(AutomationScheduleModel).order_by(AutomationScheduleModel.schedule_type)
    ).all()
    return [_automation_schedule_dict(row) for row in rows]


@router.post("/automation/schedules")
def create_automation_schedule(req: CreateAutomationScheduleRequest, session: DbSession) -> dict:
    _validate_space_schedule_type(req.schedule_type)
    now = datetime.now(UTC)
    row = session.scalar(
        select(AutomationScheduleModel).where(
            AutomationScheduleModel.schedule_type == req.schedule_type
        )
    )
    if row is None:
        row = AutomationScheduleModel(
            id=_fixed_automation_schedule_id(req.schedule_type),
            schedule_type=req.schedule_type,
            interval_seconds=max(5, int(req.interval_seconds or 60)),
            config_json=dict(req.config_json or {}),
            enabled=bool(req.enabled),
            schedule_status="active",
            next_run_at=now,
            created_by=req.created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.interval_seconds = max(5, int(req.interval_seconds or 60))
        row.config_json = dict(req.config_json or {})
        row.enabled = bool(req.enabled)
        row.updated_at = now
    session.commit()
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
    _validate_space_schedule_type(row.schedule_type)
    if req.enabled is not None:
        row.enabled = bool(req.enabled)
    if req.schedule_status is not None:
        row.schedule_status = req.schedule_status
    if req.interval_seconds is not None:
        row.interval_seconds = max(5, int(req.interval_seconds or 60))
    if req.config_json is not None:
        row.config_json = dict(req.config_json)
    row.updated_at = datetime.now(UTC)
    session.commit()
    return _automation_schedule_dict(row)


@router.post("/automation/schedules/{schedule_id}/run-now")
def run_automation_schedule_now(schedule_id: str, session: DbSession) -> dict:
    row = session.get(AutomationScheduleModel, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="automation schedule not found")
    _validate_space_schedule_type(row.schedule_type)
    result = _execute_space_automation_schedule(session=session, schedule=row)
    session.commit()
    return {"schedule": _automation_schedule_dict(row), **result}


@router.get("/automation/monitor/jobs")
def get_automation_monitor_jobs(session: DbSession) -> dict:
    _ensure_default_space_automation_schedules(session=session)
    session.commit()
    rows = session.scalars(
        select(AutomationScheduleModel).order_by(AutomationScheduleModel.schedule_type)
    ).all()
    items = [_automation_monitor_job_dict(session=session, schedule=row) for row in rows]
    session.commit()
    return {"items": items}


@router.get("/automation/monitor/job-runs")
def get_automation_monitor_job_runs(
    session: DbSession,
    schedule_type: str = "",
    limit: int = 50,
) -> dict:
    stmt = (
        select(JobRunModel, JobModel)
        .join(JobModel, JobModel.id == JobRunModel.job_id)
        .order_by(JobRunModel.started_at.desc().nullslast())
        .limit(max(1, min(int(limit or 50), 200)))
    )
    if schedule_type.strip():
        _validate_space_schedule_type(schedule_type.strip())
        job_type = _job_type_for_schedule_type(schedule_type.strip())
        stmt = stmt.where(JobModel.type == job_type)
    rows = session.execute(stmt).all()
    return {"items": [_automation_monitor_run_dict(run=run, job=job) for run, job in rows], "limit": limit}


@router.get("/automation/monitor/job-console")
def get_automation_monitor_job_console(
    session: DbSession,
    schedule_type: str = "",
    run_id: str = "",
    job_id: str = "",
    level: str = "",
    limit: int = 200,
    max_bytes: int = 524288,
) -> dict:
    stmt = select(JobEventModel, JobRunModel, JobModel).join(
        JobRunModel, JobRunModel.id == JobEventModel.run_id
    ).join(JobModel, JobModel.id == JobRunModel.job_id)
    if schedule_type.strip():
        _validate_space_schedule_type(schedule_type.strip())
        stmt = stmt.where(JobModel.type == _job_type_for_schedule_type(schedule_type.strip()))
    if run_id.strip():
        stmt = stmt.where(JobEventModel.run_id == run_id.strip())
    if job_id.strip():
        stmt = stmt.where(JobRunModel.job_id == job_id.strip())
    if level.strip():
        stmt = stmt.where(JobEventModel.level == level.strip().upper())
    rows = session.execute(
        stmt.order_by(JobEventModel.ts.desc()).limit(max(1, min(int(limit or 200), 5000)))
    ).all()
    items = []
    returned_bytes = 0
    byte_limit = max(4096, min(int(max_bytes or 524288), 2_097_152))
    for event, _run, job in rows:
        item = {
            "id": event.id,
            "run_id": event.run_id,
            "job_id": job.id,
            "job_type": job.type,
            "level": event.level,
            "event_type": event.event_type,
            "message": event.message,
            "data_json": event.data_json,
            "data_summary": _compact_json(event.data_json),
            "ts": _iso(event.ts),
        }
        item_bytes = len(str(item).encode("utf-8"))
        if items and returned_bytes + item_bytes > byte_limit:
            break
        items.append(item)
        returned_bytes += item_bytes
    return {
        "items": items,
        "truncated": len(items) < len(rows),
        "returned_count": len(items),
        "returned_bytes": returned_bytes,
        "max_bytes": byte_limit,
    }


@router.get("/downstream-channels")
def list_downstream_channels(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(DownstreamChannelModel).order_by(DownstreamChannelModel.created_at.desc())
    ).all()
    return [_downstream_channel_dict(channel, session=session) for channel in rows]


@router.post("/downstream-channels")
def create_downstream_channel(req: CreateDownstreamChannelRequest, session: DbSession) -> dict:
    if req.provider_type not in DOWNSTREAM_PROVIDER_TYPES:
        raise HTTPException(status_code=400, detail="unsupported downstream provider_type")
    if req.custom_payload_type not in CUSTOM_HTTP_PAYLOAD_TYPES:
        raise HTTPException(status_code=400, detail="unsupported custom_payload_type")
    now = datetime.now(UTC)
    channel = DownstreamChannelModel(
        id=f"downstream-channel-{uuid4()}",
        provider_type=req.provider_type,
        name=req.name.strip(),
        base_url=req.base_url.strip(),
        admin_key=req.admin_key,
        custom_payload_type=req.custom_payload_type,
        custom_auth_header_name=req.custom_auth_header_name,
        custom_auth_header_value=req.custom_auth_header_value,
        enabled=bool(req.enabled),
        update_existing=bool(req.update_existing),
        timeout_s=max(1, int(req.timeout_s or 30)),
        sub2api_concurrency=max(0, int(req.sub2api_concurrency if req.sub2api_concurrency is not None else 10)),
        sub2api_group_ids=req.sub2api_group_ids,
        max_push_count=max(0, int(req.max_push_count or 0)),
        max_active_slots=max(0, int(req.max_active_slots or 0)),
        push_balance=max(0, int(req.push_balance or 0)),
        created_at=now,
        updated_at=now,
    )
    session.add(channel)
    session.flush()
    _ensure_downstream_credential_type_balances(session=session, channel=channel)
    session.commit()
    return _downstream_channel_dict(channel, session=session)


@router.get("/downstream-channels/{channel_id}/credential-type-balances")
def list_downstream_channel_credential_type_balances(
    channel_id: str,
    session: DbSession,
) -> list[dict]:
    channel = session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    _ensure_downstream_credential_type_balances(session=session, channel=channel)
    session.commit()
    return [
        _credential_type_balance_dict(row, session=session)
        for row in session.scalars(
            select(DownstreamChannelCredentialTypeBalanceModel)
            .where(DownstreamChannelCredentialTypeBalanceModel.downstream_channel_id == channel_id)
            .order_by(DownstreamChannelCredentialTypeBalanceModel.credential_type)
        ).all()
    ]


@router.patch("/downstream-channels/{channel_id}/credential-type-balances/{credential_type}")
def patch_downstream_channel_credential_type_balance(
    channel_id: str,
    credential_type: str,
    req: PatchDownstreamChannelCredentialTypeBalanceRequest,
    session: DbSession,
) -> dict:
    balance = _ensure_downstream_credential_type_balance(
        session=session,
        channel_id=channel_id,
        credential_type=credential_type,
    )
    if req.max_active_slots is not None:
        balance.max_active_slots = max(0, int(req.max_active_slots))
    if req.push_balance is not None:
        balance.push_balance = max(0, int(req.push_balance))
    if req.balance_status is not None:
        balance.balance_status = req.balance_status
    balance.updated_at = datetime.now(UTC)
    session.commit()
    return _credential_type_balance_dict(balance, session=session)


@router.post("/downstream-channels/{channel_id}/credential-type-balances/{credential_type}/add-balance")
def add_downstream_channel_credential_type_balance(
    channel_id: str,
    credential_type: str,
    req: AddDownstreamChannelCredentialTypeBalanceRequest,
    session: DbSession,
) -> dict:
    balance = _ensure_downstream_credential_type_balance(
        session=session,
        channel_id=channel_id,
        credential_type=credential_type,
    )
    balance.push_balance = max(0, int(balance.push_balance or 0) + int(req.amount or 0))
    balance.updated_at = datetime.now(UTC)
    session.commit()
    return _credential_type_balance_dict(balance, session=session)


@router.patch("/downstream-channels/{channel_id}")
def patch_downstream_channel(
    channel_id: str,
    req: PatchDownstreamChannelRequest,
    session: DbSession,
) -> dict:
    channel = session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    if req.provider_type is not None and req.provider_type not in DOWNSTREAM_PROVIDER_TYPES:
        raise HTTPException(status_code=400, detail="unsupported downstream provider_type")
    if req.custom_payload_type is not None and req.custom_payload_type not in CUSTOM_HTTP_PAYLOAD_TYPES:
        raise HTTPException(status_code=400, detail="unsupported custom_payload_type")
    for field_name in (
        "provider_type",
        "name",
        "base_url",
        "admin_key",
        "custom_payload_type",
        "custom_auth_header_name",
        "custom_auth_header_value",
        "enabled",
        "update_existing",
        "timeout_s",
        "sub2api_concurrency",
        "sub2api_group_ids",
        "max_push_count",
        "max_active_slots",
        "push_balance",
    ):
        value = getattr(req, field_name)
        if value is not None:
            setattr(channel, field_name, value)
    channel.timeout_s = max(1, int(channel.timeout_s or 30))
    channel.sub2api_concurrency = max(0, int(channel.sub2api_concurrency or 0))
    channel.max_push_count = max(0, int(channel.max_push_count or 0))
    channel.max_active_slots = max(0, int(channel.max_active_slots or 0))
    channel.push_balance = max(0, int(channel.push_balance or 0))
    channel.updated_at = datetime.now(UTC)
    _ensure_downstream_credential_type_balances(session=session, channel=channel)
    session.commit()
    return _downstream_channel_dict(channel, session=session)


@router.delete("/downstream-channels/{channel_id}")
def delete_downstream_channel(channel_id: str, session: DbSession) -> dict:
    channel = session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    session.delete(channel)
    session.commit()
    return {"downstream_channel_id": channel_id, "deleted": True}


@router.post("/proxies/refresh-webshare-job")
def create_refresh_webshare_job(req: RefreshWebsharePoolRequest, session: DbSession) -> dict:
    return _enqueue(
        session,
        "proxy.refresh_webshare_pool",
        {"download_url": req.download_url, "proxy_type": req.proxy_type},
    )


@router.post("/proxies/bind-account-job")
def create_bind_proxy_job(input_json: dict[str, Any], session: DbSession) -> dict:
    return _enqueue(session, "proxy.bind_account", input_json)


@router.post("/proxies/bind-team-admin-job")
def create_bind_team_admin_proxy_job(input_json: dict[str, Any], session: DbSession) -> dict:
    return _enqueue(session, "proxy.bind_team_admin", input_json)


@router.post("/proxies/{proxy_id}/healthcheck-job")
def create_proxy_healthcheck_job(proxy_id: str, session: DbSession) -> dict:
    return _enqueue(session, "proxy.healthcheck", {"proxy_id": proxy_id})


@router.post("/mail/allocate-job")
def create_allocate_mail_job(input_json: dict[str, Any], session: DbSession) -> dict:
    return _enqueue(session, "mail.allocate", input_json)


@router.post("/mail/poll-otp-job")
def create_poll_mail_otp_job(input_json: dict[str, Any], session: DbSession) -> dict:
    return _enqueue(session, "mail.poll_otp", input_json)


@router.post("/mail/mark-used-job")
def create_mark_mail_used_job(input_json: dict[str, Any], session: DbSession) -> dict:
    return _enqueue(session, "mail.mark_used", input_json)


@router.post("/mail/mark-failed-job")
def create_mark_mail_failed_job(input_json: dict[str, Any], session: DbSession) -> dict:
    return _enqueue(session, "mail.mark_failed", input_json)


@router.post("/mail/release-job")
def create_release_mail_job(input_json: dict[str, Any], session: DbSession) -> dict:
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
            "proxy_type": row.proxy_type,
            "external_proxy_id": row.external_proxy_id,
            "connection_mode": row.connection_mode,
            "proxy_host": row.proxy_host,
            "proxy_port": row.proxy_port,
            "proxy_scheme": row.proxy_scheme,
            "country_code": row.country_code,
            "city_name": row.city_name,
            "asn_name": row.asn_name,
            "proxy_status": row.proxy_status,
            "provider_valid": row.provider_valid,
            "last_provider_verification_at": _iso(row.last_provider_verification_at),
            "last_healthcheck_at": _iso(row.last_healthcheck_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]


@router.get("/mail-leases")
def list_mail_leases(session: DbSession) -> list[dict]:
    rows = session.scalars(
        select(ExternalMailLeaseModel).order_by(ExternalMailLeaseModel.created_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "user_account_id": row.user_account_id,
            "provider": row.provider,
            "external_lease_id": row.external_lease_id,
            "email": row.email,
            "lease_status": row.lease_status,
            "allocated_at": _iso(row.allocated_at),
            "used_at": _iso(row.used_at),
            "released_at": _iso(row.released_at),
            "failure_code": row.failure_code,
            "failure_message": row.failure_message,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]


def _user_account_dict(row: UserAccountModel) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "phone_number": row.phone_number,
        "openai_user_id": row.openai_user_id,
        "account_status": row.account_status,
        "session_status": row.session_status,
        "has_password": bool(row.password),
        "has_access_token": bool(row.access_token),
        "has_session_token": bool(row.session_token),
        "has_cookie_header": bool(row.cookie_header),
        "last_session_refresh_at": _iso(row.last_session_refresh_at),
        "last_login_error_code": row.last_login_error_code,
        "last_login_error_message": row.last_login_error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _team_admin_proxy_binding_dict(*, session: Session, team_admin_session_id: str) -> dict:
    row = session.execute(
        select(TeamAdminProxyBindingModel, ProxyInventoryModel)
        .join(ProxyInventoryModel, ProxyInventoryModel.id == TeamAdminProxyBindingModel.proxy_id)
        .where(TeamAdminProxyBindingModel.team_admin_session_id == team_admin_session_id)
    ).first()
    if row is None:
        return {}
    binding, proxy = row
    return {
        "id": binding.id,
        "proxy_id": binding.proxy_id,
        "bind_status": binding.bind_status,
        "bind_reason": binding.bind_reason,
        "proxy_type": proxy.proxy_type,
        "proxy_status": proxy.proxy_status,
        "provider_valid": proxy.provider_valid,
        "bound_at": _iso(binding.bound_at),
        "last_used_at": _iso(binding.last_used_at),
        "last_error_code": binding.last_error_code,
    }


def _space_dict(space: SpaceModel) -> dict:
    return {
        "id": space.id,
        "provider": space.provider,
        "external_space_id": space.external_space_id,
        "owner_user_account_id": space.owner_user_account_id,
        "name": space.name,
        "space_type": space.space_type,
        "auth_mode": space.auth_mode,
        "credential_type": space.credential_type,
        "plan_type": space.plan_type,
        "seat_limit": space.seat_limit,
        "seats_in_use": space.seats_in_use,
        "seats_entitled": space.seats_entitled,
        "space_status": space.space_status,
        "source_admin_session_id": space.source_admin_session_id,
        "last_subscription_sync_at": _iso(space.last_subscription_sync_at),
        "last_probe_at": _iso(space.last_probe_at),
        "created_at": _iso(space.created_at),
        "updated_at": _iso(space.updated_at),
    }


def _space_credential_dict(*, session: Session, credential: SpaceCredentialModel) -> dict:
    space = session.get(SpaceModel, credential.space_id)
    user = session.get(UserAccountModel, credential.user_account_id)
    binding = session.get(SpacePushBindingModel, credential.id)
    usage_states = session.scalars(
        select(SpaceCredentialUsageStateModel)
        .where(SpaceCredentialUsageStateModel.space_credential_id == credential.id)
        .order_by(SpaceCredentialUsageStateModel.quota_window_kind)
    ).all()
    return {
        "id": credential.id,
        "space_id": credential.space_id,
        "user_account_id": credential.user_account_id,
        "email": user.email if user is not None else "",
        "external_space_id": space.external_space_id if space is not None else "",
        "space_type": space.space_type if space is not None else "",
        "credential_type": space.credential_type if space is not None else "",
        "credential_status": credential.credential_status,
        "external_credential_id": credential.external_credential_id,
        "account_id": credential.account_id,
        "token_chatgpt_account_id": credential.token_chatgpt_account_id,
        "has_access_token": bool(credential.access_token),
        "has_refresh_token": bool(credential.refresh_token),
        "push_status": binding.push_status if binding is not None else "none",
        "downstream_channel_id": binding.downstream_channel_id if binding is not None else "",
        "pushed_count": binding.pushed_count if binding is not None else 0,
        "failed_push_count": binding.failed_push_count if binding is not None else 0,
        "used_count": binding.used_count if binding is not None else 0,
        "usage_states": [_usage_state_dict(row) for row in usage_states],
        "expires_at": _iso(credential.expires_at),
        "last_authorized_at": _iso(credential.last_authorized_at),
        "last_probe_at": _iso(credential.last_probe_at),
        "last_probe_status": credential.last_probe_status,
        "failure_code": credential.failure_code,
        "failure_message": credential.failure_message,
        "created_at": _iso(credential.created_at),
        "updated_at": _iso(credential.updated_at),
    }


def _usage_state_dict(row: SpaceCredentialUsageStateModel) -> dict:
    return {
        "quota_window_kind": row.quota_window_kind,
        "usage_percent": row.usage_percent,
        "usage_status": row.usage_status,
        "limit_window_seconds": row.limit_window_seconds,
        "reset_after_seconds": row.reset_after_seconds,
        "reset_at": _iso(row.reset_at),
        "last_checked_at": _iso(row.last_checked_at),
        "error_code": row.error_code,
        "error_message": row.error_message,
    }


def _space_push_record_dict(*, session: Session, binding: SpacePushBindingModel) -> dict:
    credential = session.get(SpaceCredentialModel, binding.space_credential_id)
    space = session.get(SpaceModel, binding.space_id)
    user = session.get(UserAccountModel, credential.user_account_id) if credential is not None else None
    channel = (
        session.get(DownstreamChannelModel, binding.downstream_channel_id)
        if binding.downstream_channel_id
        else None
    )
    usage_states = session.scalars(
        select(SpaceCredentialUsageStateModel)
        .where(SpaceCredentialUsageStateModel.space_credential_id == binding.space_credential_id)
        .order_by(SpaceCredentialUsageStateModel.quota_window_kind)
    ).all()
    usage_by_kind = {row.quota_window_kind: row for row in usage_states}
    latest_attempt = session.scalars(
        select(SpacePushAttemptModel)
        .where(SpacePushAttemptModel.space_credential_id == binding.space_credential_id)
        .order_by(SpacePushAttemptModel.created_at.desc())
        .limit(1)
    ).first()
    last_usage_checked_at = max(
        [row.last_checked_at for row in usage_states if row.last_checked_at],
        default=None,
    )
    return {
        "id": binding.space_credential_id,
        "space_credential_id": binding.space_credential_id,
        "space_id": binding.space_id,
        "external_space_id": space.external_space_id if space is not None else "",
        "space_name": space.name if space is not None else "",
        "space_type": space.space_type if space is not None else "",
        "credential_type": space.credential_type if space is not None else "",
        "user_account_id": credential.user_account_id if credential is not None else "",
        "email": user.email if user is not None else "",
        "credential_status": credential.credential_status if credential is not None else "",
        "downstream_channel_id": binding.downstream_channel_id or "",
        "downstream_channel_name": channel.name if channel is not None else "",
        "downstream_provider": channel.provider_type if channel is not None else "",
        "downstream_external_id": binding.downstream_external_id,
        "push_status": binding.push_status,
        "recycle_status": binding.recycle_status,
        "pushed_count": binding.pushed_count,
        "failed_push_count": binding.failed_push_count,
        "used_count": binding.used_count,
        "usage_summary": _usage_summary(usage_by_kind),
        "five_hour_usage_percent": _usage_percent(usage_by_kind, "five_hour"),
        "five_hour_usage_status": _usage_status(usage_by_kind, "five_hour"),
        "weekly_usage_percent": _usage_percent(usage_by_kind, "weekly"),
        "weekly_usage_status": _usage_status(usage_by_kind, "weekly"),
        "monthly_usage_percent": _usage_percent(usage_by_kind, "monthly"),
        "monthly_usage_status": _usage_status(usage_by_kind, "monthly"),
        "last_usage_checked_at": _iso(last_usage_checked_at),
        "latest_attempt_status": latest_attempt.attempt_status if latest_attempt is not None else "",
        "latest_attempt_payload_type": latest_attempt.payload_type if latest_attempt is not None else "",
        "latest_attempt_endpoint": latest_attempt.request_endpoint if latest_attempt is not None else "",
        "latest_attempt_error_code": latest_attempt.error_code if latest_attempt is not None else "",
        "latest_attempt_error_message": latest_attempt.error_message if latest_attempt is not None else "",
        "latest_attempt_started_at": _iso(latest_attempt.started_at) if latest_attempt is not None else "",
        "latest_attempt_finished_at": _iso(latest_attempt.finished_at) if latest_attempt is not None else "",
        "error_code": binding.error_code,
        "error_message": binding.error_message,
        "created_at": _iso(binding.created_at),
        "updated_at": _iso(binding.updated_at),
    }


def _usage_summary(usage_by_kind: dict[str, SpaceCredentialUsageStateModel]) -> str:
    parts: list[str] = []
    for kind, label in (("five_hour", "5h"), ("weekly", "周"), ("monthly", "月")):
        state = usage_by_kind.get(kind)
        if state is not None:
            parts.append(f"{label}:{int(state.usage_percent or 0)}%/{state.usage_status}")
    return " ".join(parts)


def _usage_percent(
    usage_by_kind: dict[str, SpaceCredentialUsageStateModel],
    kind: str,
) -> int:
    state = usage_by_kind.get(kind)
    return int(state.usage_percent or 0) if state is not None else 0


def _usage_status(
    usage_by_kind: dict[str, SpaceCredentialUsageStateModel],
    kind: str,
) -> str:
    state = usage_by_kind.get(kind)
    return state.usage_status if state is not None else ""


def _create_pending_business_access_token_work_job(
    *,
    session: Session,
    work_count: int,
    created_by: str,
    credential_name_prefix: str,
) -> dict:
    active_job = _active_work_job_for_type(
        session=session,
        job_type="space.business_access_token.create.bulk",
    )
    if active_job is not None:
        summary = _work_summary(session, active_job.id)
        return {
            "job_id": active_job.id,
            "job_status": active_job.job_status,
            "run_id": "",
            "work_count": sum(summary.values()),
            "queued": summary["queued"],
            "running": summary["running"],
            "succeeded": summary["succeeded"],
            "failed": summary["failed"],
            "cancelled": summary["cancelled"],
            "skipped_reason": "active_authorize_job_exists",
            "selected": [],
        }
    worker_count = max(1, int(work_count or 1))
    selected = _select_pending_business_access_token_items(session=session)
    if not selected:
        return {
            "job_id": "",
            "job_status": "skipped",
            "run_id": "",
            "work_count": 0,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "selected": [],
        }
    job = JobQueue(session).enqueue(
        job_type="space.business_access_token.create.bulk",
        input_json={
            "space_membership_ids": [item["space_membership_id"] for item in selected],
            "work_count": worker_count,
            "selected_count": len(selected),
            "credential_name_prefix": credential_name_prefix,
        },
        created_by=created_by,
    )
    work_queue = WorkQueue(session)
    for item in selected:
        work_queue.enqueue(
            job_id=job.id,
            work_type="space.business_access_token.create.account",
            input_json={
                "space_membership_id": item["space_membership_id"],
                "space_id": item["space_id"],
                "user_account_id": item["user_account_id"],
                "external_space_id": item["external_space_id"],
                "session_access_token": "",
                "credential_name": f"{credential_name_prefix}-{item['user_account_id']}",
                "cookie_header": item["cookie_header"],
                "space_name": item["space_name"],
                "owner_user_account_id": item["owner_user_account_id"],
                "source_admin_session_id": item["source_admin_session_id"],
                "proxy_bind_reason": "space_business_access_token_create",
            },
        )
    session.commit()
    return {
        "job_id": job.id,
        "job_status": job.job_status,
        "run_id": "",
        "work_count": len(selected),
        "queued": len(selected),
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
        "selected": [
            {
                "space_membership_id": item["space_membership_id"],
                "space_id": item["space_id"],
                "user_account_id": item["user_account_id"],
                "external_space_id": item["external_space_id"],
            }
            for item in selected
        ],
    }


def _select_pending_business_access_token_items(*, session: Session) -> list[dict]:
    credential_join_condition = and_(
        SpaceCredentialModel.space_id == SpaceMembershipModel.space_id,
        SpaceCredentialModel.user_account_id == SpaceMembershipModel.user_account_id,
        SpaceCredentialModel.credential_status == "active",
    )
    rows = session.execute(
        select(SpaceMembershipModel, SpaceModel, UserAccountModel)
        .join(SpaceModel, SpaceModel.id == SpaceMembershipModel.space_id)
        .join(UserAccountModel, UserAccountModel.id == SpaceMembershipModel.user_account_id)
        .outerjoin(SpaceCredentialModel, credential_join_condition)
        .where(
            SpaceMembershipModel.membership_status == "active",
            SpaceMembershipModel.session_account_detected.is_(True),
            SpaceModel.provider == "openai_chatgpt",
            SpaceModel.space_type == "business",
            SpaceModel.space_status == "active",
            SpaceModel.credential_type.in_(("team_5h_weekly", "team_monthly")),
            UserAccountModel.account_status == "active",
            UserAccountModel.session_status == "active",
            or_(UserAccountModel.cookie_header != "", UserAccountModel.session_token != ""),
            SpaceCredentialModel.id.is_(None),
        )
        .order_by(SpaceMembershipModel.updated_at.asc())
    ).all()
    return [
        {
            "space_membership_id": membership.id,
            "space_id": space.id,
            "user_account_id": account.id,
            "external_space_id": space.external_space_id,
            "access_token": account.access_token,
            "cookie_header": _web_session_cookie_header(account),
            "space_name": space.name,
            "owner_user_account_id": space.owner_user_account_id,
            "source_admin_session_id": space.source_admin_session_id,
        }
        for membership, space, account in rows
    ]


def _web_session_cookie_header(account: UserAccountModel) -> str:
    cookie_header = str(account.cookie_header or "").strip()
    session_token = str(account.session_token or "").strip()
    if not session_token or "__Secure-next-auth.session-token=" in cookie_header:
        return cookie_header
    if not cookie_header:
        return f"__Secure-next-auth.session-token={session_token}"
    return f"__Secure-next-auth.session-token={session_token}; {cookie_header}"


def _create_business_access_token_work_job(
    *,
    req: CreateBusinessAccessTokenCredentialsJobRequest,
    session: Session,
) -> dict:
    user_account_ids = _validated_user_account_ids(session=session, ids=req.user_account_ids)
    if not req.external_space_id.strip():
        raise HTTPException(status_code=400, detail="external_space_id is required")
    if not req.cookie_header.strip():
        raise HTTPException(status_code=400, detail="cookie_header is required")
    worker_count = max(1, int(req.work_count or 5))
    job = JobQueue(session).enqueue(
        job_type="space.business_access_token.create.bulk",
        input_json={
            "user_account_ids": user_account_ids,
            "external_space_id": req.external_space_id,
            "work_count": worker_count,
            "selected_count": len(user_account_ids),
            "credential_name_prefix": req.credential_name_prefix,
        },
        created_by=req.created_by,
    )
    work_queue = WorkQueue(session)
    for user_account_id in user_account_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type="space.business_access_token.create.account",
            input_json={
                "user_account_id": user_account_id,
                "external_space_id": req.external_space_id,
                "session_access_token": req.session_access_token,
                "credential_name": f"{req.credential_name_prefix}-{user_account_id}",
                "cookie_header": req.cookie_header,
                "space_name": req.space_name,
                "owner_user_account_id": req.owner_user_account_id,
                "source_admin_session_id": req.source_admin_session_id,
                "proxy_bind_reason": "space_business_access_token_create_manual",
            },
        )
    session.commit()
    return {
        "job_id": job.id,
        "job_status": job.job_status,
        "run_id": "",
        "work_count": len(user_account_ids),
        "queued": len(user_account_ids),
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }


def _create_space_push_work_job(
    *,
    req: PushSpaceCredentialsRequest,
    session: Session,
) -> dict:
    credential_ids = [item.strip() for item in req.space_credential_ids if item.strip()]
    if not credential_ids:
        raise HTTPException(status_code=400, detail="space_credential_ids is required")
    channel = session.get(DownstreamChannelModel, req.downstream_channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    found_ids = set(
        session.scalars(select(SpaceCredentialModel.id).where(SpaceCredentialModel.id.in_(credential_ids))).all()
    )
    missing_ids = [item for item in credential_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail={"space_credential_ids": missing_ids})
    return _create_space_push_job_for_ids(
        session=session,
        credential_ids=credential_ids,
        downstream_channel_id=req.downstream_channel_id,
        created_by=req.created_by,
        worker_count=max(1, int(req.work_count or 5)),
        retry_ids=set(),
    )


def _create_pending_space_push_work_job(
    *,
    req: PushPendingSpaceCredentialsRequest,
    session: Session,
) -> dict:
    channel = session.get(DownstreamChannelModel, req.downstream_channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    if not channel.enabled:
        raise HTTPException(status_code=400, detail="downstream channel is disabled")
    selected = _select_pending_space_push_items(
        session=session,
        channel=channel,
    )
    if not selected:
        return {
            "job_id": "",
            "job_status": "skipped",
            "run_id": "",
            "work_count": 0,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "selected": [],
        }
    return _create_space_push_job_for_ids(
        session=session,
        credential_ids=[item["space_credential_id"] for item in selected],
        downstream_channel_id=req.downstream_channel_id,
        created_by=req.created_by,
        worker_count=max(1, int(req.work_count or 5)),
        retry_ids={item["space_credential_id"] for item in selected if item.get("is_retry")},
        selected=selected,
    )


def _create_space_push_job_for_ids(
    *,
    session: Session,
    credential_ids: list[str],
    downstream_channel_id: str,
    created_by: str,
    worker_count: int,
    retry_ids: set[str],
    selected: list[dict] | None = None,
) -> dict:
    job, run = _start_work_job(
        session=session,
        job_type="space_credential.push.bulk",
        input_json={
            "space_credential_ids": credential_ids,
            "downstream_channel_id": downstream_channel_id,
            "work_count": max(1, int(worker_count or 5)),
            "selected_count": len(credential_ids),
        },
        created_by=created_by,
    )
    work_queue = WorkQueue(session)
    for credential_id in credential_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type="space_credential.push.account",
            input_json={
                "space_credential_id": credential_id,
                "downstream_channel_id": downstream_channel_id,
                "is_retry": credential_id in retry_ids,
                "_run_id": run.id,
            },
        )
    session.commit()
    result = _run_work_job_now_and_summarize(
        session=session,
        job_id=job.id,
        run_id=run.id,
        worker_count=max(1, int(worker_count or 5)),
        work_count=len(credential_ids),
    )
    if selected is not None:
        result["selected"] = selected
    return result


def _create_account_work_job(
    *,
    req: BackfillSessionRtRequest,
    session: Session,
    job_type: str,
    work_type: str,
) -> dict:
    user_account_ids = _validated_user_account_ids(session=session, ids=req.user_account_ids)
    worker_count = max(1, int(req.work_count or 10))
    job, run = _start_work_job(
        session=session,
        job_type=job_type,
        input_json={
            "user_account_ids": user_account_ids,
            "work_count": worker_count,
            "selected_count": len(user_account_ids),
        },
        created_by=req.created_by,
    )
    work_queue = WorkQueue(session)
    for user_account_id in user_account_ids:
        work_queue.enqueue(
            job_id=job.id,
            work_type=work_type,
            input_json={"user_account_id": user_account_id, "_run_id": run.id},
        )
    session.commit()
    return _run_work_job_now_and_summarize(
        session=session,
        job_id=job.id,
        run_id=run.id,
        worker_count=worker_count,
        work_count=len(user_account_ids),
    )


def _select_pending_space_push_items(
    *,
    session: Session,
    channel: DownstreamChannelModel,
) -> list[dict]:
    selected: list[dict] = []
    selected_ids: set[str] = set()
    _ensure_downstream_credential_type_balances(session=session, channel=channel)
    balances = session.scalars(
        select(DownstreamChannelCredentialTypeBalanceModel).where(
            DownstreamChannelCredentialTypeBalanceModel.downstream_channel_id == channel.id,
            DownstreamChannelCredentialTypeBalanceModel.balance_status == "active",
        )
    ).all()
    for balance in balances:
        credential_type = balance.credential_type
        active_slots = _active_space_push_slot_count(
            session=session,
            downstream_channel_id=channel.id,
            credential_type=credential_type,
        )
        allowed_slots = _allowed_space_push_slots(session=session, balance=balance)
        retry_ids = _select_retryable_failed_space_credential_ids(
            session=session,
            downstream_channel_id=channel.id,
            credential_type=credential_type,
            excluded_ids=selected_ids,
            limit=allowed_slots,
        )
        for credential_id in retry_ids:
            selected.append({"space_credential_id": credential_id, "credential_type": credential_type, "is_retry": True})
            selected_ids.add(credential_id)
        remaining_slots = max(0, allowed_slots - active_slots)
        new_limit = min(remaining_slots, int(balance.push_balance or 0))
        if new_limit <= 0:
            continue
        new_ids = _select_new_space_credential_ids(
            session=session,
            credential_type=credential_type,
            excluded_ids=selected_ids,
            limit=new_limit,
        )
        for credential_id in new_ids:
            selected.append({"space_credential_id": credential_id, "credential_type": credential_type, "is_retry": False})
            selected_ids.add(credential_id)
    return selected


def _select_retryable_failed_space_credential_ids(
    *,
    session: Session,
    downstream_channel_id: str,
    credential_type: str,
    excluded_ids: set[str],
    limit: int,
) -> list[str]:
    stmt = (
        select(SpaceCredentialModel.id)
        .join(SpacePushBindingModel, SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id)
        .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
        .where(
            SpacePushBindingModel.downstream_channel_id == downstream_channel_id,
            SpacePushBindingModel.push_status == "failed",
            SpaceCredentialModel.credential_status == "active",
            SpaceCredentialModel.access_token != "",
            SpaceModel.space_status == "active",
            SpaceModel.credential_type == credential_type,
        )
        .order_by(SpacePushBindingModel.updated_at.asc())
        .limit(limit)
    )
    if excluded_ids:
        stmt = stmt.where(~SpaceCredentialModel.id.in_(excluded_ids))
    if credential_type == "personal_account":
        stmt = stmt.where(SpaceCredentialModel.refresh_token != "")
    return [str(row) for row in session.scalars(stmt).all()]


def _select_new_space_credential_ids(
    *,
    session: Session,
    credential_type: str,
    excluded_ids: set[str],
    limit: int,
) -> list[str]:
    stmt = (
        select(SpaceCredentialModel.id)
        .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
        .outerjoin(SpacePushBindingModel, SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id)
        .where(
            SpaceCredentialModel.credential_status == "active",
            SpaceCredentialModel.access_token != "",
            SpaceModel.space_status == "active",
            SpaceModel.credential_type == credential_type,
            or_(SpacePushBindingModel.space_credential_id.is_(None), SpacePushBindingModel.push_status.in_(("none", "skipped"))),
        )
        .order_by(SpaceCredentialModel.updated_at.asc())
        .limit(limit)
    )
    if excluded_ids:
        stmt = stmt.where(~SpaceCredentialModel.id.in_(excluded_ids))
    if credential_type == "personal_account":
        stmt = stmt.where(SpaceCredentialModel.refresh_token != "")
    return [str(row) for row in session.scalars(stmt).all()]


def _active_space_push_slot_count(
    *,
    session: Session,
    downstream_channel_id: str,
    credential_type: str,
) -> int:
    value = session.scalar(
        select(func.count())
        .select_from(SpacePushBindingModel)
        .join(SpaceCredentialModel, SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id)
        .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
        .where(
            SpacePushBindingModel.downstream_channel_id == downstream_channel_id,
            SpacePushBindingModel.push_status.in_(("pushing", "pushed", "failed")),
            SpaceModel.credential_type == credential_type,
        )
    )
    return int(value or 0)


def _allowed_space_push_slots(
    *,
    session: Session,
    balance: DownstreamChannelCredentialTypeBalanceModel,
) -> int:
    max_slots = max(0, int(balance.max_active_slots or 0))
    if max_slots <= 0:
        return 0
    base_slots = max(1, max_slots // 2)
    high_usage_count = int(
        session.scalar(
            select(func.count(func.distinct(SpacePushBindingModel.space_credential_id)))
            .select_from(SpacePushBindingModel)
            .join(
                SpaceCredentialModel,
                SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id,
            )
            .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
            .join(
                SpaceCredentialUsageStateModel,
                SpaceCredentialUsageStateModel.space_credential_id
                == SpacePushBindingModel.space_credential_id,
            )
            .where(
                SpacePushBindingModel.downstream_channel_id == balance.downstream_channel_id,
                SpacePushBindingModel.push_status.in_(("pushing", "pushed", "failed")),
                SpaceModel.credential_type == balance.credential_type,
                SpaceCredentialUsageStateModel.usage_percent >= 70,
            )
        )
        or 0
    )
    return min(max_slots, base_slots + high_usage_count)


def _start_work_job(
    *,
    session: Session,
    job_type: str,
    input_json: dict[str, Any],
    created_by: str,
) -> tuple[JobModel, JobRunModel]:
    now = datetime.now(UTC)
    job = JobQueue(session).enqueue(
        job_type=job_type,
        input_json=input_json,
        created_by=created_by,
    )
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
    return job, run


def _active_work_job_for_type(*, session: Session, job_type: str) -> JobModel | None:
    jobs = session.scalars(
        select(JobModel)
        .where(
            JobModel.type == job_type,
            JobModel.job_status.in_(("queued", "running")),
        )
        .order_by(JobModel.created_at.asc())
        .limit(10)
    ).all()
    for job in jobs:
        _finalize_work_job_if_complete(session=session, job=job)
        if job.job_status == "queued":
            return job
        if job.job_status == "running":
            summary = _work_summary(session, job.id)
            if summary["queued"] > 0 or summary["running"] > 0:
                return job
    return None


def _run_work_job_now_and_summarize(
    *,
    session: Session,
    job_id: str,
    run_id: str,
    worker_count: int,
    work_count: int,
) -> dict:
    local_session_factory = _session_factory_from_session(session)
    _run_job_work_now(
        session_factory=local_session_factory,
        job_id=job_id,
        worker_count=worker_count,
    )
    session.expire_all()
    summary = _work_summary(session, job_id)
    job = session.get(JobModel, job_id)
    run = session.get(JobRunModel, run_id)
    _apply_work_job_summary(job=job, run=run, summary=summary)
    session.commit()
    return {
        "job_id": job.id if job is not None else "",
        "job_status": job.job_status if job is not None else "",
        "run_id": run.id if run is not None else "",
        "work_count": work_count,
        **summary,
    }

def _run_job_work_now(*, session_factory, job_id: str, worker_count: int) -> None:
    def run_loop() -> None:
        runner = JobRunner(session_factory)
        register_core_handlers(runner, session_factory=session_factory, settings=get_settings())
        while runner.run_one_work_for_job(job_id) is not None:
            pass

    bounded_worker_count = max(1, int(worker_count or 1))
    if bounded_worker_count <= 1:
        run_loop()
        return
    with ThreadPoolExecutor(max_workers=bounded_worker_count) as executor:
        futures = [executor.submit(run_loop) for _ in range(bounded_worker_count)]
        for future in as_completed(futures):
            future.result()


def _work_summary(session: Session, job_id: str) -> dict[str, int]:
    summary = {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }
    rows = session.execute(
        select(WorkItemModel.work_status, func.count())
        .where(WorkItemModel.job_id == job_id)
        .group_by(WorkItemModel.work_status)
    ).all()
    for status, count in rows:
        if status in summary:
            summary[status] = int(count or 0)
    return summary


def _apply_work_job_summary(
    *,
    job: JobModel | None,
    run: JobRunModel | None,
    summary: dict[str, int],
) -> None:
    now = datetime.now(UTC)
    if job is not None:
        if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] == 0:
            job.job_status = "succeeded"
        elif summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] > 0:
            job.job_status = "failed"
        else:
            job.job_status = "running"
        job.updated_at = now
    if run is not None:
        if summary["queued"] == 0 and summary["running"] == 0:
            run.run_status = "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
            run.finished_at = now
        else:
            run.run_status = "running"
            run.finished_at = None
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = (
                f"failed={summary['failed']} queued={summary['queued']} running={summary['running']}"
            )
        elif run.run_status == "succeeded":
            run.error_code = ""
            run.error_message = ""


def _finalize_work_job_if_complete(*, session: Session, job: JobModel | None) -> None:
    if job is None or job.job_status != "running":
        return
    summary = _work_summary(session, job.id)
    if summary["queued"] > 0 or summary["running"] > 0:
        return
    run = session.scalars(
        select(JobRunModel)
        .where(JobRunModel.job_id == job.id)
        .order_by(JobRunModel.started_at.desc().nullslast())
        .limit(1)
    ).first()
    _apply_work_job_summary(job=job, run=run, summary=summary)


def _validated_user_account_ids(*, session: Session, ids: list[str]) -> list[str]:
    user_account_ids = [item.strip() for item in ids if item.strip()]
    if not user_account_ids:
        raise HTTPException(status_code=400, detail="user_account_ids is required")
    found_ids = set(
        session.scalars(select(UserAccountModel.id).where(UserAccountModel.id.in_(user_account_ids))).all()
    )
    missing_ids = [item for item in user_account_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail={"user_account_ids": missing_ids})
    return user_account_ids


def _downstream_channel_dict(channel: DownstreamChannelModel, *, session: Session | None = None) -> dict:
    balances: list[dict] = []
    if session is not None:
        _ensure_downstream_credential_type_balances(session=session, channel=channel)
        balances = [
            _credential_type_balance_dict(row, session=session)
            for row in session.scalars(
                select(DownstreamChannelCredentialTypeBalanceModel)
                .where(DownstreamChannelCredentialTypeBalanceModel.downstream_channel_id == channel.id)
                .order_by(DownstreamChannelCredentialTypeBalanceModel.credential_type)
            ).all()
        ]
    return {
        "id": channel.id,
        "provider_type": channel.provider_type,
        "name": channel.name,
        "base_url": channel.base_url,
        "admin_key_summary": _summarize_secret(channel.admin_key),
        "custom_payload_type": channel.custom_payload_type,
        "custom_auth_header_name": channel.custom_auth_header_name,
        "custom_auth_header_value_summary": _summarize_secret(channel.custom_auth_header_value),
        "enabled": channel.enabled,
        "update_existing": channel.update_existing,
        "timeout_s": channel.timeout_s,
        "sub2api_concurrency": channel.sub2api_concurrency,
        "sub2api_group_ids": channel.sub2api_group_ids,
        "max_push_count": channel.max_push_count,
        "max_active_slots": channel.max_active_slots,
        "push_balance": channel.push_balance,
        "claimed_push_count": channel.claimed_push_count,
        "pushed_count": channel.pushed_count,
        "failed_push_count": channel.failed_push_count,
        "used_count": channel.used_count,
        "credential_type_balances": balances,
        "created_at": _iso(channel.created_at),
        "updated_at": _iso(channel.updated_at),
    }


def _ensure_downstream_credential_type_balances(
    *,
    session: Session,
    channel: DownstreamChannelModel,
) -> None:
    for credential_type in SPACE_CREDENTIAL_TYPES:
        _ensure_downstream_credential_type_balance(
            session=session,
            channel_id=channel.id,
            credential_type=credential_type,
            channel=channel,
        )


def _ensure_downstream_credential_type_balance(
    *,
    session: Session,
    channel_id: str,
    credential_type: str,
    channel: DownstreamChannelModel | None = None,
) -> DownstreamChannelCredentialTypeBalanceModel:
    if credential_type not in SPACE_CREDENTIAL_TYPES:
        raise HTTPException(status_code=400, detail="unsupported credential_type")
    channel = channel or session.get(DownstreamChannelModel, channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="downstream channel not found")
    row = session.get(DownstreamChannelCredentialTypeBalanceModel, (channel_id, credential_type))
    if row is None:
        now = datetime.now(UTC)
        row = DownstreamChannelCredentialTypeBalanceModel(
            downstream_channel_id=channel_id,
            credential_type=credential_type,
            max_active_slots=max(0, int(channel.max_active_slots or 0)),
            push_balance=0,
            balance_status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    return row


def _credential_type_balance_dict(
    row: DownstreamChannelCredentialTypeBalanceModel,
    *,
    session: Session | None = None,
) -> dict:
    active_slot_count = 0
    allowed_active_slots = 0
    if session is not None:
        active_slot_count = _active_space_push_slot_count(
            session=session,
            downstream_channel_id=row.downstream_channel_id,
            credential_type=row.credential_type,
        )
        allowed_active_slots = _allowed_space_push_slots(session=session, balance=row)
    return {
        "downstream_channel_id": row.downstream_channel_id,
        "credential_type": row.credential_type,
        "max_active_slots": row.max_active_slots,
        "allowed_active_slots": allowed_active_slots,
        "active_slot_count": active_slot_count,
        "remaining_active_slots": max(0, allowed_active_slots - active_slot_count),
        "push_balance": row.push_balance,
        "remaining_push_count": min(
            max(0, allowed_active_slots - active_slot_count),
            max(0, int(row.push_balance or 0)),
        ),
        "claimed_push_count": row.claimed_push_count,
        "pushed_count": row.pushed_count,
        "failed_push_count": row.failed_push_count,
        "used_count": row.used_count,
        "balance_status": row.balance_status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


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
        "last_run_at": _iso(row.last_run_at),
        "next_run_at": _iso(row.next_run_at),
        "last_job_id": row.last_job_id,
        "last_run_status": row.last_run_status,
        "locked_by": row.locked_by,
        "locked_until": _iso(row.locked_until),
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "created_by": row.created_by,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _ensure_default_space_automation_schedules(*, session: Session) -> None:
    now = datetime.now(UTC)
    defaults = {
        "automation.space_membership_invite_sync": {
            "interval_seconds": 60,
            "config_json": {
                "space_limit": 1,
                "invite_limit_per_space": 350,
                "work_count": SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
                "membership_cap_per_space": 1000,
                "page_size": 100,
                "barrier_timeout_s": SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
            },
        },
        "automation.space_authorize": {
            "interval_seconds": 60,
            "config_json": {"work_count": 1},
        },
        "automation.space_downstream_push": {
            "interval_seconds": 60,
            "config_json": {"work_count": 5},
        },
        "automation.space_recycle_sweep": {
            "interval_seconds": 300,
            "config_json": {"limit": 100, "work_count": 5},
        },
    }
    for schedule_type, values in defaults.items():
        row = session.scalar(
            select(AutomationScheduleModel).where(
                AutomationScheduleModel.schedule_type == schedule_type
            )
        )
        if row is not None:
            continue
        session.add(
            AutomationScheduleModel(
                id=_fixed_automation_schedule_id(schedule_type),
                schedule_type=schedule_type,
                schedule_status="active",
                enabled=False,
                interval_seconds=int(values["interval_seconds"]),
                config_json=dict(values["config_json"]),
                next_run_at=now,
                created_by="system:space-default",
                created_at=now,
                updated_at=now,
            )
        )


def _automation_monitor_job_dict(*, session: Session, schedule: AutomationScheduleModel) -> dict:
    job_type = _job_type_for_schedule_type(schedule.schedule_type)
    latest_job = session.scalars(
        select(JobModel).where(JobModel.type == job_type).order_by(JobModel.created_at.desc()).limit(1)
    ).first()
    latest_run = None
    if latest_job is not None:
        _finalize_work_job_if_complete(session=session, job=latest_job)
        latest_run = session.scalars(
            select(JobRunModel)
            .where(JobRunModel.job_id == latest_job.id)
            .order_by(JobRunModel.started_at.desc().nullslast())
            .limit(1)
        ).first()
    output = latest_run.output_json if latest_run is not None and isinstance(latest_run.output_json, dict) else {}
    duration_ms = 0
    if latest_run is not None and latest_run.started_at and latest_run.finished_at:
        duration_ms = int((latest_run.finished_at - latest_run.started_at).total_seconds() * 1000)
    if latest_job is not None and schedule.last_job_id == latest_job.id:
        latest_status = latest_run.run_status if latest_run is not None else latest_job.job_status
        if schedule.last_run_status != latest_status:
            schedule.last_run_status = latest_status
            schedule.updated_at = datetime.now(UTC)
        if latest_run is not None and latest_run.started_at and schedule.last_run_at != latest_run.started_at:
            schedule.last_run_at = latest_run.started_at
    return {
        **_automation_schedule_dict(schedule),
        "job_type": job_type,
        "latest_job_id": latest_job.id if latest_job is not None else "",
        "latest_job_status": latest_job.job_status if latest_job is not None else "",
        "last_job_status": latest_job.job_status if latest_job is not None else "",
        "last_run_id": latest_run.id if latest_run is not None else "",
        "duration_ms": duration_ms,
        "succeeded": int(output.get("succeeded") or output.get("invited_count") or 0),
        "failed": int(output.get("failed") or output.get("failed_invite_count") or 0),
        "skipped": int(output.get("skipped") or output.get("skipped_space_count") or 0),
    }


def _automation_monitor_run_dict(*, run: JobRunModel, job: JobModel) -> dict:
    return {
        "id": run.id,
        "run_id": run.id,
        "job_id": job.id,
        "job_type": job.type,
        "job_status": job.job_status,
        "run_status": run.run_status,
        "attempt": run.attempt,
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "error_code": run.error_code,
        "error_message": run.error_message,
        "output_json": run.output_json,
    }


def _execute_space_automation_schedule(*, session: Session, schedule: AutomationScheduleModel) -> dict:
    _validate_space_schedule_type(schedule.schedule_type)
    now = datetime.now(UTC)
    schedule.last_run_at = now
    schedule.next_run_at = now + timedelta(seconds=max(5, int(schedule.interval_seconds or 60)))
    schedule.updated_at = now
    try:
        if schedule.schedule_type == "automation.space_membership_invite_sync":
            job = JobQueue(session).enqueue(
                job_type="space.membership_invite_sync",
                input_json={
                    "space_limit": 1,
                    "invite_limit_per_space": int(
                        schedule.config_json.get("invite_limit_per_space") or 350
                    ),
                    "work_count": SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
                    "membership_cap_per_space": int(
                        schedule.config_json.get("membership_cap_per_space") or 1000
                    ),
                    "page_size": int(schedule.config_json.get("page_size") or 100),
                    "barrier_timeout_s": SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
                },
                created_by=str(schedule.config_json.get("created_by") or f"scheduler:{schedule.id}"),
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status}
        if schedule.schedule_type == "automation.space_authorize":
            result = _create_pending_business_access_token_work_job(
                session=session,
                work_count=int(
                    schedule.config_json.get("work_count")
                    or schedule.config_json.get("limit")
                    or 1
                ),
                created_by=str(schedule.config_json.get("created_by") or f"scheduler:{schedule.id}"),
                credential_name_prefix=str(
                    schedule.config_json.get("credential_name_prefix") or "codex"
                ),
            )
            schedule.last_job_id = str(result.get("job_id") or "")
            schedule.last_run_status = str(result.get("job_status") or "queued")
            return result
        if schedule.schedule_type == "automation.space_recycle_sweep":
            job = JobQueue(session).enqueue(
                job_type="space.recycle.sweep",
                input_json={
                    "limit": int(schedule.config_json.get("limit") or 100),
                    "work_count": max(1, int(schedule.config_json.get("work_count") or 5)),
                },
                created_by=str(schedule.config_json.get("created_by") or f"scheduler:{schedule.id}"),
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status}
        downstream_channel_id = str(schedule.config_json.get("downstream_channel_id") or "")
        channels_stmt = select(DownstreamChannelModel).where(DownstreamChannelModel.enabled.is_(True))
        if downstream_channel_id:
            channels_stmt = channels_stmt.where(DownstreamChannelModel.id == downstream_channel_id)
        results = []
        for channel in session.scalars(channels_stmt).all():
            result = _create_pending_space_push_work_job(
                req=PushPendingSpaceCredentialsRequest(
                    downstream_channel_id=channel.id,
                    created_by=str(schedule.config_json.get("created_by") or f"scheduler:{schedule.id}"),
                    work_count=int(schedule.config_json.get("work_count") or 5),
                ),
                session=session,
            )
            results.append(result)
        schedule.last_job_id = ",".join(str(item.get("job_id") or "") for item in results if item.get("job_id"))
        schedule.last_run_status = "succeeded"
        return {"items": results}
    except Exception as exc:
        schedule.last_run_status = "failed"
        schedule.last_error_code = "schedule_run_failed"
        schedule.last_error_message = f"{type(exc).__name__}: {exc}"
        raise


def start_automation_scheduler() -> None:
    global _SCHEDULER_STARTED
    if _SCHEDULER_STARTED:
        return
    _SCHEDULER_STARTED = True
    settings = get_settings()
    session_factory = make_session_factory(make_engine(settings))
    Thread(
        target=_automation_scheduler_loop,
        kwargs={"session_factory": session_factory},
        daemon=True,
        name="space-automation-scheduler",
    ).start()


def _automation_scheduler_loop(*, session_factory) -> None:
    scheduler_id = f"{gethostname()}-{uuid4()}"
    while True:
        try:
            with session_factory() as session:
                _run_due_space_automation_schedules(session=session, scheduler_id=scheduler_id)
                session.commit()
        except Exception:
            pass
        sleep(5)


def _run_due_space_automation_schedules(*, session: Session, scheduler_id: str) -> None:
    now = datetime.now(UTC)
    schedules = session.scalars(
        select(AutomationScheduleModel)
        .where(
            AutomationScheduleModel.enabled.is_(True),
            AutomationScheduleModel.schedule_status == "active",
            AutomationScheduleModel.schedule_type.in_(SPACE_AUTOMATION_TYPES),
            or_(AutomationScheduleModel.next_run_at.is_(None), AutomationScheduleModel.next_run_at <= now),
        )
        .order_by(AutomationScheduleModel.next_run_at.asc().nullsfirst())
        .limit(10)
    ).all()
    for schedule in schedules:
        schedule.locked_by = scheduler_id
        schedule.locked_until = now + timedelta(seconds=max(30, int(schedule.interval_seconds or 60)))
        _execute_space_automation_schedule(session=session, schedule=schedule)


def _validate_space_schedule_type(schedule_type: str) -> None:
    if schedule_type not in SPACE_AUTOMATION_TYPES:
        raise HTTPException(status_code=400, detail=f"unsupported Space automation schedule type: {schedule_type}")


def _fixed_automation_schedule_id(schedule_type: str) -> str:
    _validate_space_schedule_type(schedule_type)
    return {
        "automation.space_recycle_sweep": "automation-schedule-space-recycle-sweep",
        "automation.space_downstream_push": "automation-schedule-space-downstream-push",
        "automation.space_membership_invite_sync": "automation-schedule-space-membership-invite-sync",
        "automation.space_authorize": "automation-schedule-space-authorize",
    }[schedule_type]


def _job_type_for_schedule_type(schedule_type: str) -> str:
    _validate_space_schedule_type(schedule_type)
    return {
        "automation.space_recycle_sweep": "space.recycle.sweep",
        "automation.space_downstream_push": "space_credential.push.bulk",
        "automation.space_membership_invite_sync": "space.membership_invite_sync",
        "automation.space_authorize": "space.business_access_token.create.bulk",
    }[schedule_type]


def _enqueue(session: Session, job_type: str, input_json: dict[str, Any]) -> dict:
    job = JobQueue(session).enqueue(job_type=job_type, input_json=input_json)
    session.commit()
    return {"job_id": job.id, "job_status": job.job_status}


def _session_factory_from_session(session: Session):
    return sessionmaker(bind=session.get_bind(), autoflush=False, expire_on_commit=False)


def _session_access_token(raw: dict[str, Any]) -> str:
    for key in ("access_token", "accessToken", "token"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    current = raw
    for key in ("auth", "session", "credentials"):
        value = current.get(key)
        if isinstance(value, dict):
            token = _session_access_token(value)
            if token:
                return token
    return ""


def _summarize_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _compact_json(value: Any, *, max_chars: int = 700) -> str:
    if value in (None, "", {}):
        return ""
    try:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        text = str(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
