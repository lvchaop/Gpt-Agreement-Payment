from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from socket import gethostname
from threading import Thread
from time import sleep
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from refactor_app.api.dependencies import get_db_session
from refactor_app.api.pagination import page_payload, page_values, total_for
from refactor_app.application.jobs.queue import JobQueue, WorkQueue
from refactor_app.application.workflows.account_email_change import (
    ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
    ACCOUNT_EMAIL_CHANGE_MODE_MAPPED,
    AccountEmailChangeCsvError,
    AccountEmailChangeSource,
    AccountEmailChangeSourceError,
    parse_account_email_change_csv,
    parse_account_email_change_source_jsonl,
)
from refactor_app.application.workflows.payment_method_inventory import (
    PAYMENT_METHOD_MAX_ATTEMPTS,
    PaymentMethodInventoryError,
    _normalize_address,
    _normalize_card,
    _normalize_name,
    import_payment_method_inventory,
    payment_method_inventory_summary,
)
from refactor_app.application.workflows.protocol_registration import (
    EMAIL_BROWSER_NO_PHONE,
    EMAIL_PROTOCOL_NO_PHONE,
    ICLOUD_HIDE_MY_EMAIL_PROVIDER,
    PHONE_PROTOCOL_BIND_EMAIL,
    SUPPORTED_REGISTRATION_MAIL_PROVIDERS,
)
from refactor_app.application.workflows.proxy import (
    ProxyWorkflowError,
    bind_team_admin_static_proxy_in_session,
    ensure_team_admin_static_proxy_url_in_session,
    reassign_team_admin_static_proxy_in_session,
)
from refactor_app.application.workflows.space_authorization import (
    resolve_personal_codex_authorization_target,
)
from refactor_app.application.workflows.space_auto_replenish import (
    MAX_INVITE_BATCH_SIZE,
    SpaceAutoReplenishError,
    cancel_space_auto_replenishment_hosting,
    host_space_auto_replenishment,
    import_space_replenish_emails,
)
from refactor_app.application.workflows.space_manual_export import (
    SpaceManualExportError,
    export_unpushed_sub2api_jsonl,
    redownload_sub2api_jsonl,
)
from refactor_app.application.workflows.space_membership_growth import (
    DEFAULT_SESSION_WAIT_TIMEOUT_S,
    DEFAULT_SESSION_WORK_COUNT,
    MAX_GROWTH_INVITES,
    TARGET_GROWTH_MEMBERS,
)
from refactor_app.application.workflows.space_membership_invite_sync import (
    SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
    SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
    SpaceMembershipInviteSyncWorkflow,
    SpaceMembershipInviteSyncWorkflowError,
)
from refactor_app.application.workflows.space_recycle import (
    manually_settle_pushed_binding_from_usage_state,
)
from refactor_app.application.workflows.space_seat_expansion import (
    MAX_HTTP_FAILURE_COUNT,
    MAX_NO_PROGRESS_COUNT,
    MAX_SEAT_INCREASE,
    MIN_SEAT_INCREASE,
    REQUEST_DELAY_MS,
    TARGET_SEATS,
)
from refactor_app.application.workflows.space_session_otp import (
    DEFAULT_SESSION_OTP_PREPARE_WORK_COUNT,
    SESSION_OTP_SUBMIT_BARRIER_TIMEOUT_S,
    SpaceSessionOtpWorkflowError,
    select_space_session_otp_prepare_candidates,
    select_space_session_otp_submit_candidates,
    space_session_otp_summary,
)
from refactor_app.application.workflows.space_session_otp_remote import (
    RemoteSessionOtpBridgeError,
    select_remote_session_otp_candidates,
)
from refactor_app.application.workflows.space_usage import SpaceUsageError, infer_credential_type
from refactor_app.config.settings import get_settings
from refactor_app.domain.enums import AccountStatus
from refactor_app.domain.space_status import (
    OPERATOR_SPACE_STATUSES,
    space_status_after_discovery,
)
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
    PaymentAddressPoolModel,
    PaymentCardPoolModel,
    PaymentNamePoolModel,
    ProxyInventoryModel,
    SpaceCredentialModel,
    SpaceCredentialUsageStateModel,
    SpaceMembershipModel,
    SpaceModel,
    SpacePushAttemptModel,
    SpacePushBindingModel,
    SpaceReplenishEmailModel,
    TeamAdminProxyBindingModel,
    TeamAdminSessionModel,
    UserAccountModel,
    UserAccountProxyBindingModel,
    WorkItemModel,
)
from refactor_app.plugins.openai_chatgpt.client import (
    OpenAIChatGPTClientConfig,
    OpenAIChatGPTClientError,
    decode_access_token_claims,
)
from refactor_app.plugins.openai_chatgpt.plugin import OpenAIChatGPTPlugin

router = APIRouter(tags=["resources"])
DbSession = Annotated[Session, Depends(get_db_session)]

SPACE_CREDENTIAL_TYPES = ("personal_account", "team_5h_weekly", "team_monthly")
SESSION_RECENCY_HOURS = {
    "within_6h": 6,
    "within_12h": 12,
    "within_1d": 24,
    "within_2d": 48,
    "within_3d": 72,
    "within_7d": 168,
}
SPACE_AUTOMATION_TYPES = (
    "automation.space_membership_invite_sync",
    "automation.space_membership_invite_dynamic",
    "automation.space_membership_growth_round",
    "automation.space_authorize",
    "automation.space_downstream_push",
    "automation.space_recycle_sweep",
    "automation.space_seat_expand",
    "automation.space_auto_replenish",
    "automation.personal_payment_method_bind",
)
DOWNSTREAM_PROVIDER_TYPES = {"sub2api", "cpa", "local_sub2api", "custom_http"}
CUSTOM_HTTP_PAYLOAD_TYPES = {"", "sub2api", "sub2api_admin_accounts", "cpa"}

_SCHEDULER_STARTED = False


@router.get("/ops/overview")
def get_ops_overview(session: DbSession) -> dict:
    since = datetime.now(UTC) - timedelta(hours=24)
    job_counts = dict(
        session.execute(
            select(JobModel.job_status, func.count()).group_by(JobModel.job_status)
        ).all()
    )
    queued_work = int(
        session.scalar(
            select(func.count())
            .select_from(WorkItemModel)
            .where(WorkItemModel.work_status == "queued")
        )
        or 0
    )
    failed_24h = int(
        session.scalar(
            select(func.count())
            .select_from(JobModel)
            .where(
                JobModel.job_status == "failed",
                JobModel.updated_at >= since,
            )
        )
        or 0
    )
    session_issues = int(
        session.scalar(
            select(func.count())
            .select_from(UserAccountModel)
            .where(
                UserAccountModel.account_status == "active",
                UserAccountModel.session_status != "active",
            )
        )
        or 0
    )
    unauthorized_memberships = int(
        session.scalar(
            select(func.count())
            .select_from(SpaceMembershipModel)
            .where(
                SpaceMembershipModel.membership_status == "active",
                ~select(SpaceCredentialModel.id)
                .where(
                    SpaceCredentialModel.space_id == SpaceMembershipModel.space_id,
                    SpaceCredentialModel.user_account_id == SpaceMembershipModel.user_account_id,
                    SpaceCredentialModel.credential_status == "active",
                )
                .exists(),
            )
        )
        or 0
    )
    push_attention = int(
        session.scalar(
            select(func.count())
            .select_from(SpacePushBindingModel)
            .where(SpacePushBindingModel.push_status.in_(("failed", "pushed")))
        )
        or 0
    )
    available_static_proxies = int(
        session.scalar(
            select(func.count())
            .select_from(ProxyInventoryModel)
            .where(
                ProxyInventoryModel.proxy_type == "static_proxy",
                ProxyInventoryModel.proxy_status == "available",
                ProxyInventoryModel.provider_valid.is_(True),
            )
        )
        or 0
    )
    balances = session.execute(
        select(
            func.coalesce(func.sum(DownstreamChannelCredentialTypeBalanceModel.push_balance), 0),
            func.coalesce(
                func.sum(DownstreamChannelCredentialTypeBalanceModel.max_active_slots), 0
            ),
        ).where(DownstreamChannelCredentialTypeBalanceModel.balance_status == "active")
    ).one()
    recent_failed = session.scalars(
        select(JobModel)
        .where(JobModel.job_status == "failed")
        .order_by(JobModel.updated_at.desc())
        .limit(8)
    ).all()
    return {
        "generated_at": _iso(datetime.now(UTC)),
        "metrics": {
            "running_jobs": int(job_counts.get("running", 0)),
            "queued_jobs": int(job_counts.get("queued", 0)),
            "queued_work": queued_work,
            "failed_jobs_24h": failed_24h,
            "session_issues": session_issues,
            "unauthorized_memberships": unauthorized_memberships,
            "push_attention": push_attention,
            "available_static_proxies": available_static_proxies,
            "downstream_push_balance": int(balances[0] or 0),
            "downstream_slot_limit": int(balances[1] or 0),
        },
        "recent_failed_jobs": [
            {
                "id": row.id,
                "type": row.type,
                "job_status": row.job_status,
                "created_by": row.created_by,
                "created_at": _iso(row.created_at),
                "updated_at": _iso(row.updated_at),
            }
            for row in recent_failed
        ],
    }


@router.get("/ops/options/accounts")
def account_options(session: DbSession, q: str = "", limit: int = 30) -> dict:
    stmt = select(UserAccountModel).order_by(UserAccountModel.email).limit(min(100, max(1, limit)))
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(UserAccountModel.email.ilike(needle), UserAccountModel.id.ilike(needle))
        )
    rows = session.scalars(stmt).all()
    return {
        "items": [
            {"value": row.id, "label": row.email, "status": row.account_status} for row in rows
        ]
    }


@router.get("/ops/options/spaces")
def space_options(
    session: DbSession,
    q: str = "",
    limit: int = 30,
    space_type: str = "",
    credential_type: str = "",
) -> dict:
    stmt = select(SpaceModel).order_by(SpaceModel.name).limit(min(100, max(1, limit)))
    if space_type.strip():
        stmt = stmt.where(SpaceModel.space_type == space_type.strip())
    if credential_type.strip():
        if credential_type.strip() not in SPACE_CREDENTIAL_TYPES:
            raise HTTPException(status_code=400, detail="unsupported credential_type")
        stmt = stmt.where(SpaceModel.credential_type == credential_type.strip())
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(SpaceModel.name.ilike(needle), SpaceModel.external_space_id.ilike(needle))
        )
    rows = session.scalars(stmt).all()
    return {
        "items": [
            {
                "value": row.id,
                "label": row.name or row.external_space_id or row.id,
                "description": row.external_space_id,
                "status": row.space_status,
            }
            for row in rows
        ]
    }


@router.get("/ops/options/channels")
def channel_options(session: DbSession, q: str = "", limit: int = 30) -> dict:
    stmt = (
        select(DownstreamChannelModel)
        .order_by(DownstreamChannelModel.name)
        .limit(min(100, max(1, limit)))
    )
    if q.strip():
        stmt = stmt.where(DownstreamChannelModel.name.ilike(f"%{q.strip()}%"))
    rows = session.scalars(stmt).all()
    return {
        "items": [
            {
                "value": row.id,
                "label": row.name,
                "description": row.provider_type,
                "status": "active" if row.enabled else "disabled",
            }
            for row in rows
        ]
    }


class ImportUserAccountRequest(BaseModel):
    id: str = ""
    email: str
    account_status: str = AccountStatus.ACTIVE.value
    password: str = ""


class PatchUserAccountRequest(BaseModel):
    account_status: str | None = None
    password: str | None = None


class DeleteUserAccountsRequest(BaseModel):
    user_account_ids: list[str] = Field(min_length=1)


class BackfillSessionRtRequest(BaseModel):
    user_account_ids: list[str]
    created_by: str = ""
    work_count: int = 10


class PersonalCodexAuthorizationJobRequest(BaseModel):
    space_membership_ids: list[str] = Field(min_length=1)
    created_by: str = ""
    work_count: int = Field(default=1, ge=1, le=350)
    use_hero_sms_for_add_phone: bool = False
    hero_sms_country: str = ""
    hero_sms_max_price: str | float = "0.05"
    force_clean_browser_login: bool = False


class SpaceSessionOtpPrepareJobRequest(BaseModel):
    created_by: str = ""
    work_count: int = Field(default=DEFAULT_SESSION_OTP_PREPARE_WORK_COUNT, ge=1)
    account_count: int | None = Field(default=None, ge=1)
    user_account_ids: list[str] = Field(default_factory=list)


class SpaceSessionOtpSubmitJobRequest(BaseModel):
    created_by: str = ""


class MultiSpaceSessionOtpScopeRequest(BaseModel):
    space_ids: list[str] = Field(min_length=1)


class MultiSpaceSessionOtpPrepareJobRequest(SpaceSessionOtpPrepareJobRequest):
    space_ids: list[str] = Field(min_length=1)


class MultiSpaceSessionOtpSubmitJobRequest(SpaceSessionOtpSubmitJobRequest):
    space_ids: list[str] = Field(min_length=1)


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


class SpaceSeatExpansionJobRequest(BaseModel):
    created_by: str = ""
    work_count: int = 1


class PersonalPaymentMethodBindJobRequest(BaseModel):
    auto_start_plus_checkout: bool = True
    created_by: str = ""


class PersonalPlusCheckoutJobRequest(BaseModel):
    create_proxy_country: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")
    promo_proxy_country: str = Field(default="JP", pattern=r"^[A-Za-z]{2}$")
    promo_campaign_id: str = Field(default="plus-1-month-free", min_length=1, max_length=120)
    created_by: str = ""


class PersonalPaymentMethodBindSelectedJobRequest(BaseModel):
    space_ids: list[str] = Field(min_length=1)
    auto_start_plus_checkout: bool = True
    created_by: str = ""


class PersonalPromotionCheckSelectedJobRequest(BaseModel):
    space_ids: list[str] = Field(min_length=1)
    proxy_country: str = Field(default="JP", pattern=r"^[A-Za-z]{2}$")
    work_count: int = Field(default=5, ge=1, le=50)
    created_by: str = ""


class SpaceAutoReplenishInviteJobRequest(BaseModel):
    created_by: str = ""


class ImportSpaceReplenishEmailsRequest(BaseModel):
    emails: list[str] = Field(min_length=1)


class PaymentAddressPoolImportItem(BaseModel):
    line1: str
    line2: str = ""
    city: str
    state: str = ""
    postal_code: str
    country: str
    phone: str = ""


class PaymentCardPoolImportItem(BaseModel):
    card_number: str
    cvc: str
    exp_month: int
    exp_year: int


class ImportPaymentMethodPoolsRequest(BaseModel):
    names: list[str] = Field(default_factory=list)
    addresses: list[PaymentAddressPoolImportItem | str] = Field(default_factory=list)
    cards: list[PaymentCardPoolImportItem | str] = Field(default_factory=list)


class CreatePaymentNamePoolRequest(BaseModel):
    full_name: str
    name_status: str = "active"


class PatchPaymentNamePoolRequest(BaseModel):
    full_name: str | None = None
    name_status: str | None = None


class CreatePaymentAddressPoolRequest(PaymentAddressPoolImportItem):
    address_status: str = "active"


class PatchPaymentAddressPoolRequest(BaseModel):
    line1: str | None = None
    line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    phone: str | None = None
    address_status: str | None = None


class CreatePaymentCardPoolRequest(PaymentCardPoolImportItem):
    card_status: str = "available"


class PatchPaymentCardPoolRequest(BaseModel):
    card_number: str | None = None
    cvc: str | None = None
    exp_month: int | None = None
    exp_year: int | None = None
    card_status: str | None = None


class ManualSettleSpacePushRecordsRequest(BaseModel):
    space_credential_ids: list[str]
    created_by: str = ""


class ProtocolRegistrationJobRequest(BaseModel):
    mode: str
    count: int = 1
    work_count: int = 1
    use_proxy: bool = True
    proxy_country: str = Field(default="US", pattern=r"^[A-Za-z]{2}$")
    authorize_codex_after_security: bool = False
    mail_provider: str = "outlook"
    email_domain: str = ""
    project_key: str = "openai-register"
    caller_id: str = "refactor-app-protocol-registration"
    browser_headless: bool = True
    browser_otp_timeout_s: int = 180
    browser_close_delay_s: float = Field(default=10.0, ge=0)
    phone_provider: str = "hero_sms"
    phone_base_url: str = "https://hero-sms.com/stubs/handler_api.php"
    phone_api_key_env: str = "HERO_SMS_API_KEY"
    phone_service: str = "dr"
    phone_country: str = ""
    phone_countries: list[str] = Field(default_factory=lambda: ["151", "73", "16"])
    phone_max_price: str = "0.05"
    phone_country_max_prices: dict[str, str] = {}
    phone_max_number_attempts: int = 3
    phone_otp_timeout_s: int = 180
    phone_otp_poll_interval_s: float = 3.0
    created_by: str = ""


class AccountEmailChangeJobRequest(BaseModel):
    mode: str = ACCOUNT_EMAIL_CHANGE_MODE_MAPPED
    csv_text: str = ""
    source_jsonl_text: str = ""
    work_count: int = 5
    otp_timeout_s: int = 180
    mail_provider: str = "outlook"
    project_key: str = ""
    caller_id: str = "refactor-app-protocol-registration"
    email_domain: str = ""
    created_by: str = ""


class SyncRemoteSpaceMembershipsRequest(BaseModel):
    page_size: int = 100


class PatchSpaceRequest(BaseModel):
    space_status: str | None = None
    auto_replenish_enabled: bool | None = None


class ExportUnpushedSpaceCredentialsRequest(BaseModel):
    credential_type: str = ""
    space_id: str = ""
    limit: int = 0


class RedownloadSpaceCredentialsRequest(BaseModel):
    space_credential_ids: list[str] = []
    export_batch_id: str = ""


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


class RunAutomationScheduleNowRequest(BaseModel):
    config_overrides: dict[str, Any] = {}
    created_by: str = ""


@router.get("/user-accounts")
def list_user_accounts(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    account_status: str = "",
    session_status: str = "",
    personal_plan_type: str = "",
    codex_select_channel_required: str = "",
    session_recency: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    personal_plan_type_column = (
        select(SpaceModel.plan_type)
        .where(
            SpaceModel.owner_user_account_id == UserAccountModel.id,
            SpaceModel.space_type == "personal",
        )
        .order_by(SpaceModel.updated_at.desc(), SpaceModel.id.desc())
        .limit(1)
        .correlate(UserAccountModel)
        .scalar_subquery()
    )
    stmt = select(
        UserAccountModel,
        personal_plan_type_column.label("personal_plan_type"),
    )
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                UserAccountModel.id.ilike(needle),
                UserAccountModel.email.ilike(needle),
                UserAccountModel.openai_user_id.ilike(needle),
                UserAccountModel.last_login_error_code.ilike(needle),
                UserAccountModel.last_login_error_message.ilike(needle),
            )
        )
    if account_status.strip():
        stmt = stmt.where(UserAccountModel.account_status.in_(_csv_values(account_status)))
    if session_status.strip():
        stmt = stmt.where(UserAccountModel.session_status.in_(_csv_values(session_status)))
    stmt = _apply_plan_type_filter(
        stmt,
        column=personal_plan_type_column,
        value=personal_plan_type,
    )
    select_channel_filter = codex_select_channel_required.strip().lower()
    if select_channel_filter in {"yes", "true", "1"}:
        stmt = stmt.where(UserAccountModel.codex_select_channel_required.is_(True))
    if select_channel_filter in {"no", "false", "0"}:
        stmt = stmt.where(UserAccountModel.codex_select_channel_required.is_(False))
    stmt = _apply_session_recency_filter(
        stmt,
        column=UserAccountModel.last_session_refresh_at,
        value=session_recency,
    )
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": UserAccountModel.created_at,
            "updated_at": UserAccountModel.updated_at,
            "email": UserAccountModel.email,
            "account_status": UserAccountModel.account_status,
            "session_status": UserAccountModel.session_status,
            "personal_plan_type": personal_plan_type_column,
            "last_session_refresh_at": UserAccountModel.last_session_refresh_at,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[
            _user_account_dict(row, personal_plan_type=personal_plan_type)
            for row, personal_plan_type in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.get("/user-accounts/{user_account_id}/access-token")
def get_user_account_access_token(user_account_id: str, session: DbSession) -> dict:
    row = session.get(UserAccountModel, user_account_id)
    if row is None:
        raise HTTPException(status_code=404, detail="user account not found")
    access_token = str(row.access_token or "").strip()
    if not access_token:
        raise HTTPException(status_code=409, detail="account access_token is empty")
    return {
        "user_account_id": row.id,
        "access_token": access_token,
    }


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
    deleted_personal_spaces = _delete_personal_spaces_for_account_ids(
        session=session,
        account_ids={user_account_id},
    )
    deleted_proxy_bindings = (
        session.query(UserAccountProxyBindingModel)
        .filter(UserAccountProxyBindingModel.user_account_id == user_account_id)
        .delete(synchronize_session=False)
    )
    session.delete(row)
    session.commit()
    return {
        "user_account_id": user_account_id,
        "deleted": True,
        "deleted_personal_spaces": deleted_personal_spaces,
        "deleted_proxy_bindings": int(deleted_proxy_bindings or 0),
    }


@router.post("/user-accounts/delete-selected")
def delete_selected_user_accounts(req: DeleteUserAccountsRequest, session: DbSession) -> dict:
    account_ids = list(
        dict.fromkeys(
            account_id.strip() for account_id in req.user_account_ids if account_id.strip()
        )
    )
    if not account_ids:
        raise HTTPException(status_code=400, detail="user_account_ids must not be empty")

    accounts = session.scalars(
        select(UserAccountModel).where(UserAccountModel.id.in_(account_ids))
    ).all()
    found_ids = {account.id for account in accounts}
    deleted_personal_spaces = _delete_personal_spaces_for_account_ids(
        session=session,
        account_ids=found_ids,
    )
    deleted_proxy_bindings = (
        session.query(UserAccountProxyBindingModel)
        .filter(UserAccountProxyBindingModel.user_account_id.in_(found_ids))
        .delete(synchronize_session=False)
        if found_ids
        else 0
    )
    for account in accounts:
        session.delete(account)
    session.commit()
    return {
        "requested_count": len(account_ids),
        "deleted_count": len(accounts),
        "missing_count": len(account_ids) - len(accounts),
        "deleted_personal_spaces": deleted_personal_spaces,
        "deleted_proxy_bindings": int(deleted_proxy_bindings or 0),
    }


def _delete_personal_spaces_for_account_ids(
    *,
    session: Session,
    account_ids: set[str],
) -> int:
    if not account_ids:
        return 0
    return int(
        session.query(SpaceModel)
        .filter(
            SpaceModel.space_type == "personal",
            SpaceModel.owner_user_account_id.in_(account_ids),
        )
        .delete(synchronize_session=False)
        or 0
    )


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


@router.post("/memberships/refresh-session-space-detection-job")
def create_refresh_session_space_detection_job(
    req: BackfillSessionRtRequest,
    session: DbSession,
) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.refresh_session_space_detection",
        work_type="account.refresh_session_space_detection",
    )


@router.post("/user-accounts/backfill-rt-job")
def create_backfill_rt_job(req: BackfillSessionRtRequest, session: DbSession) -> dict:
    return _create_account_work_job(
        req=req,
        session=session,
        job_type="account.backfill_rt",
        work_type="account.backfill_rt",
    )


@router.post("/memberships/personal-codex-authorize-job")
def create_personal_codex_authorization_job(
    req: PersonalCodexAuthorizationJobRequest,
    session: DbSession,
) -> dict:
    if req.use_hero_sms_for_add_phone and not get_settings().hero_sms_api_key:
        raise HTTPException(status_code=400, detail="HERO_SMS_API_KEY is not configured")
    return _create_personal_codex_authorization_work_job(req=req, session=session)


@router.get("/spaces/{space_id}/session-otp/summary")
def get_space_session_otp_summary(space_id: str, session: DbSession) -> dict:
    return _get_session_otp_summary(space_ids=[space_id], session=session)


@router.post("/memberships/session-otp/summary")
def get_multi_space_session_otp_summary(
    req: MultiSpaceSessionOtpScopeRequest,
    session: DbSession,
) -> dict:
    return _get_session_otp_summary(space_ids=req.space_ids, session=session)


def _get_session_otp_summary(*, space_ids: Sequence[str], session: Session) -> dict:
    normalized_space_ids = _normalize_session_otp_space_ids(space_ids)
    try:
        result = space_session_otp_summary(
            session=session,
            space_ids=normalized_space_ids,
        )
    except SpaceSessionOtpWorkflowError as exc:
        raise _session_otp_http_exception(
            session=session,
            space_ids=normalized_space_ids,
            exc=exc,
        ) from exc
    settings = get_settings()
    return {
        **result,
        "default_prepare_work_count": DEFAULT_SESSION_OTP_PREPARE_WORK_COUNT,
        "worker_capacity": settings.worker_capacity,
        "active_job": _space_session_otp_active_job_dict(
            session=session,
            space_ids=normalized_space_ids,
        ),
    }


@router.post("/spaces/{space_id}/session-otp/prepare-job")
def create_space_session_otp_prepare_job(
    space_id: str,
    req: SpaceSessionOtpPrepareJobRequest,
    session: DbSession,
) -> dict:
    return _create_session_otp_prepare_job(
        space_ids=[space_id],
        req=req,
        session=session,
    )


@router.post("/memberships/session-otp/prepare-job")
def create_multi_space_session_otp_prepare_job(
    req: MultiSpaceSessionOtpPrepareJobRequest,
    session: DbSession,
) -> dict:
    return _create_session_otp_prepare_job(
        space_ids=req.space_ids,
        req=req,
        session=session,
    )


def _create_session_otp_prepare_job(
    *,
    space_ids: Sequence[str],
    req: SpaceSessionOtpPrepareJobRequest,
    session: Session,
) -> dict:
    normalized_space_ids = _normalize_session_otp_space_ids(space_ids)
    settings = get_settings()
    work_count = max(1, int(req.work_count or DEFAULT_SESSION_OTP_PREPARE_WORK_COUNT))
    if work_count > settings.worker_capacity:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "prepare work_count exceeds worker capacity",
                "work_count": work_count,
                "worker_capacity": settings.worker_capacity,
            },
        )
    try:
        candidates = select_space_session_otp_prepare_candidates(
            session=session,
            space_ids=normalized_space_ids,
        )
    except SpaceSessionOtpWorkflowError as exc:
        raise _session_otp_http_exception(
            session=session,
            space_ids=normalized_space_ids,
            exc=exc,
        ) from exc
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="selected spaces have no active member accounts",
        )
    requested_user_account_ids = list(
        dict.fromkeys(item.strip() for item in req.user_account_ids if item.strip())
    )
    if requested_user_account_ids and req.account_count is not None:
        raise HTTPException(
            status_code=400,
            detail="prepare user_account_ids and account_count cannot be used together",
        )
    if requested_user_account_ids:
        candidates_by_account_id = {
            candidate.user_account_id: candidate for candidate in candidates
        }
        invalid_user_account_ids = [
            account_id
            for account_id in requested_user_account_ids
            if account_id not in candidates_by_account_id
        ]
        if invalid_user_account_ids:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "prepare contains accounts outside active selected-space candidates",
                    "invalid_user_account_ids": invalid_user_account_ids,
                },
            )
        candidates = [
            candidates_by_account_id[account_id] for account_id in requested_user_account_ids
        ]
    elif req.account_count is not None:
        if req.account_count > len(candidates):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "prepare account_count exceeds active member count",
                    "account_count": req.account_count,
                    "active_member_count": len(candidates),
                },
            )
        candidates = candidates[: req.account_count]

    selected_user_account_ids = [candidate.user_account_id for candidate in candidates]
    _reject_active_session_otp_job(
        session=session,
        space_ids=normalized_space_ids,
        user_account_ids=selected_user_account_ids,
    )
    job_input = {
        "space_id": normalized_space_ids[0],
        "space_ids": normalized_space_ids,
        "work_count": work_count,
        "selected_count": len(candidates),
        "user_account_ids": selected_user_account_ids,
    }
    if req.account_count is not None:
        job_input["account_count"] = req.account_count
    job, run = _start_work_job(
        session=session,
        job_type="account.session_otp.prepare.bulk",
        input_json=job_input,
        created_by=req.created_by,
    )
    work_queue = WorkQueue(session)
    for candidate in candidates:
        work_queue.enqueue(
            job_id=job.id,
            work_type="account.session_otp.prepare",
            input_json={
                "job_id": job.id,
                "space_id": candidate.space_id or normalized_space_ids[0],
                "space_membership_id": candidate.space_membership_id,
                "user_account_id": candidate.user_account_id,
                "_run_id": run.id,
            },
        )
    session.commit()
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=work_count,
        selected_count=len(candidates),
    )


@router.post("/spaces/{space_id}/session-otp/submit-job")
def create_space_session_otp_submit_job(
    space_id: str,
    req: SpaceSessionOtpSubmitJobRequest,
    session: DbSession,
) -> dict:
    _reject_active_space_session_otp_job(session=session, space_id=space_id)
    try:
        candidates = select_space_session_otp_submit_candidates(
            session=session,
            space_id=space_id,
        )
    except SpaceSessionOtpWorkflowError as exc:
        if session.get(SpaceModel, space_id) is None:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_count = len(candidates)
    if snapshot_count == 0:
        raise HTTPException(status_code=400, detail="space has no submit-ready OTP snapshots")

    worker_capacity = get_settings().worker_capacity
    if snapshot_count > worker_capacity:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "all submit Work must fit in the central Worker at once",
                "snapshot_count": snapshot_count,
                "worker_capacity": worker_capacity,
            },
        )

    job, run = _start_work_job(
        session=session,
        job_type="account.session_otp.submit.bulk",
        input_json={
            "space_id": space_id,
            "work_count": snapshot_count,
            "selected_count": snapshot_count,
            "dispatch_mode": "all_at_once",
            "required_slots": snapshot_count,
            "barrier_expected": snapshot_count,
            "barrier_timeout_s": SESSION_OTP_SUBMIT_BARRIER_TIMEOUT_S,
        },
        created_by=req.created_by,
    )
    barrier_key = f"session-otp-submit:{job.id}"
    work_queue = WorkQueue(session)
    for candidate in candidates:
        work_queue.enqueue(
            job_id=job.id,
            work_type="account.session_otp.submit",
            input_json={
                "space_id": space_id,
                "space_membership_id": candidate.space_membership_id,
                "user_account_id": candidate.user_account_id,
                "snapshot_id": candidate.snapshot_id,
                "barrier_key": barrier_key,
                "barrier_expected": snapshot_count,
                "barrier_timeout_s": SESSION_OTP_SUBMIT_BARRIER_TIMEOUT_S,
                "_run_id": run.id,
            },
        )
    session.commit()
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=snapshot_count,
        selected_count=snapshot_count,
    )


@router.post("/spaces/{space_id}/session-otp/remote-submit-job")
def create_space_session_otp_remote_submit_job(
    space_id: str,
    req: SpaceSessionOtpSubmitJobRequest,
    session: DbSession,
) -> dict:
    return _create_session_otp_remote_submit_job(
        space_ids=[space_id],
        req=req,
        session=session,
    )


@router.post("/memberships/session-otp/remote-submit-job")
def create_multi_space_session_otp_remote_submit_job(
    req: MultiSpaceSessionOtpSubmitJobRequest,
    session: DbSession,
) -> dict:
    return _create_session_otp_remote_submit_job(
        space_ids=req.space_ids,
        req=req,
        session=session,
    )


def _create_session_otp_remote_submit_job(
    *,
    space_ids: Sequence[str],
    req: SpaceSessionOtpSubmitJobRequest,
    session: Session,
) -> dict:
    normalized_space_ids = _normalize_session_otp_space_ids(space_ids)
    settings = get_settings()
    if not settings.session_otp_executor_base_url.strip():
        raise HTTPException(status_code=400, detail="INVITE_EXECUTOR_BASE_URL is not configured")
    if not settings.session_otp_executor_api_key.strip():
        raise HTTPException(status_code=400, detail="INVITE_EXECUTOR_API_KEY is not configured")
    try:
        selection = select_remote_session_otp_candidates(
            session=session,
            space_ids=normalized_space_ids,
        )
    except RemoteSessionOtpBridgeError as exc:
        raise _session_otp_http_exception(
            session=session,
            space_ids=normalized_space_ids,
            exc=exc,
        ) from exc
    selected_count = len(selection.candidates)
    if selected_count == 0:
        raise HTTPException(
            status_code=400,
            detail="selected spaces have no otp_collected snapshots",
        )
    selected_user_account_ids = [
        candidate.user_account_id for candidate in selection.candidates
    ]
    _reject_active_session_otp_job(
        session=session,
        space_ids=normalized_space_ids,
        user_account_ids=selected_user_account_ids,
    )

    job, run = _start_work_job(
        session=session,
        job_type="account.session_otp.remote_submit.bulk",
        input_json={
            "space_id": normalized_space_ids[0],
            "space_ids": normalized_space_ids,
            "user_account_ids": selected_user_account_ids,
            "work_count": 1,
            "selected_count": selected_count,
            "eligible_count": selection.eligible_count,
            "remaining_count": selection.remaining_count,
            "poll_interval_s": 0.5,
            "poll_timeout_s": 900.0,
            "barrier_timeout_s": 120.0,
        },
        created_by=req.created_by,
    )
    WorkQueue(session).enqueue(
        job_id=job.id,
        work_type="account.session_otp.remote_submit",
        input_json={
            "space_id": normalized_space_ids[0],
            "space_ids": normalized_space_ids,
            "user_account_ids": selected_user_account_ids,
            "expected_snapshot_count": selected_count,
            "poll_interval_s": 0.5,
            "poll_timeout_s": 900.0,
            "barrier_timeout_s": 120.0,
            "_run_id": run.id,
        },
    )
    session.commit()
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=1,
        selected_count=selected_count,
    )


@router.get("/spaces")
def list_spaces(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    space_type: str = "",
    credential_type: str = "",
    plan_type: str = "",
    space_status: str = "",
    auth_mode: str = "",
    provider: str = "",
    session_recency: str = "",
    payment_method_status: str = "",
    has_payment_method: bool | None = None,
    has_promotion: bool | None = None,
) -> dict:
    page, page_size = page_values(page, page_size)
    space_session_at = case(
        (
            SpaceModel.space_type == "personal",
            UserAccountModel.last_session_refresh_at,
        ),
        else_=TeamAdminSessionModel.imported_at,
    ).label("last_session_refresh_at")
    stmt = (
        select(SpaceModel, space_session_at)
        .outerjoin(UserAccountModel, UserAccountModel.id == SpaceModel.owner_user_account_id)
        .outerjoin(
            TeamAdminSessionModel,
            TeamAdminSessionModel.id == SpaceModel.source_admin_session_id,
        )
    )
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                SpaceModel.id.ilike(needle),
                SpaceModel.name.ilike(needle),
                SpaceModel.external_space_id.ilike(needle),
            )
        )
    for value, column in (
        (space_type, SpaceModel.space_type),
        (credential_type, SpaceModel.credential_type),
        (space_status, SpaceModel.space_status),
        (auth_mode, SpaceModel.auth_mode),
        (provider, SpaceModel.provider),
        (payment_method_status, SpaceModel.payment_method_status),
    ):
        if value.strip():
            stmt = stmt.where(column.in_(_csv_values(value)))
    if has_payment_method is not None:
        stmt = stmt.where(SpaceModel.has_payment_method.is_(has_payment_method))
    if has_promotion is not None:
        stmt = stmt.where(SpaceModel.has_promotion.is_(has_promotion))
    stmt = _apply_plan_type_filter(stmt, column=SpaceModel.plan_type, value=plan_type)
    stmt = _apply_session_recency_filter(
        stmt,
        column=space_session_at,
        value=session_recency,
    )
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": SpaceModel.created_at,
            "updated_at": SpaceModel.updated_at,
            "name": SpaceModel.name,
            "space_status": SpaceModel.space_status,
            "credential_type": SpaceModel.credential_type,
            "plan_type": SpaceModel.plan_type,
            "payment_method_status": SpaceModel.payment_method_status,
            "last_session_refresh_at": space_session_at,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[
            _space_dict(space, last_session_refresh_at=last_session_refresh_at)
            for space, last_session_refresh_at in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.get("/payment-method-pools/summary")
def get_payment_method_pool_summary(session: DbSession) -> dict:
    return payment_method_inventory_summary(session)


@router.post("/payment-method-pools/import")
def import_payment_method_pools(
    req: ImportPaymentMethodPoolsRequest,
    session: DbSession,
) -> dict:
    try:
        result = import_payment_method_inventory(
            session=session,
            names=req.names,
            addresses=[
                item.model_dump() if isinstance(item, PaymentAddressPoolImportItem) else item
                for item in req.addresses
            ],
            cards=[
                item.model_dump() if isinstance(item, PaymentCardPoolImportItem) else item
                for item in req.cards
            ],
        )
    except PaymentMethodInventoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session.commit()
    return result


@router.get("/payment-method-pools/names")
def list_payment_name_pool(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    name_status: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(PaymentNamePoolModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                PaymentNamePoolModel.id.ilike(needle),
                PaymentNamePoolModel.full_name.ilike(needle),
            )
        )
    if name_status.strip():
        stmt = stmt.where(PaymentNamePoolModel.name_status.in_(_csv_values(name_status)))
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": PaymentNamePoolModel.created_at,
            "updated_at": PaymentNamePoolModel.updated_at,
            "full_name": PaymentNamePoolModel.full_name,
            "use_count": PaymentNamePoolModel.use_count,
            "last_used_at": PaymentNamePoolModel.last_used_at,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_payment_name_pool_dict(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.post("/payment-method-pools/names")
def create_payment_name_pool(
    req: CreatePaymentNamePoolRequest,
    session: DbSession,
) -> dict:
    _validate_payment_pool_status(req.name_status, {"active", "disabled"}, "name_status")
    try:
        _key, data = _normalize_name(req.full_name)
    except PaymentMethodInventoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = datetime.now(UTC)
    row = PaymentNamePoolModel(
        id=str(uuid4()),
        **data,
        name_status=req.name_status,
        use_count=0,
        created_at=now,
        updated_at=now,
    )
    _persist_payment_pool_row(session, row, "payment name already exists")
    return _payment_name_pool_dict(row)


@router.patch("/payment-method-pools/names/{pool_id}")
def patch_payment_name_pool(
    pool_id: str,
    req: PatchPaymentNamePoolRequest,
    session: DbSession,
) -> dict:
    row = session.get(PaymentNamePoolModel, pool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="payment name not found")
    if req.full_name is None and req.name_status is None:
        raise HTTPException(status_code=400, detail="no payment name fields to update")
    if req.name_status is not None:
        _validate_payment_pool_status(req.name_status, {"active", "disabled"}, "name_status")
        row.name_status = req.name_status
    if req.full_name is not None:
        try:
            _key, data = _normalize_name(req.full_name)
        except PaymentMethodInventoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        row.full_name = data["full_name"]
        row.normalized_name = data["normalized_name"]
    row.updated_at = datetime.now(UTC)
    _commit_payment_pool_row(session, row, "payment name already exists")
    return _payment_name_pool_dict(row)


@router.delete("/payment-method-pools/names/{pool_id}")
def delete_payment_name_pool(pool_id: str, session: DbSession) -> dict:
    row = session.get(PaymentNamePoolModel, pool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="payment name not found")
    session.delete(row)
    session.commit()
    return {"payment_name_id": pool_id, "deleted": True}


@router.get("/payment-method-pools/addresses")
def list_payment_address_pool(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    address_status: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(PaymentAddressPoolModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                PaymentAddressPoolModel.id.ilike(needle),
                PaymentAddressPoolModel.line1.ilike(needle),
                PaymentAddressPoolModel.city.ilike(needle),
                PaymentAddressPoolModel.state.ilike(needle),
                PaymentAddressPoolModel.postal_code.ilike(needle),
                PaymentAddressPoolModel.country.ilike(needle),
            )
        )
    if address_status.strip():
        stmt = stmt.where(
            PaymentAddressPoolModel.address_status.in_(_csv_values(address_status))
        )
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": PaymentAddressPoolModel.created_at,
            "updated_at": PaymentAddressPoolModel.updated_at,
            "city": PaymentAddressPoolModel.city,
            "country": PaymentAddressPoolModel.country,
            "use_count": PaymentAddressPoolModel.use_count,
            "last_used_at": PaymentAddressPoolModel.last_used_at,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_payment_address_pool_dict(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.post("/payment-method-pools/addresses")
def create_payment_address_pool(
    req: CreatePaymentAddressPoolRequest,
    session: DbSession,
) -> dict:
    _validate_payment_pool_status(req.address_status, {"active", "disabled"}, "address_status")
    try:
        _key, data = _normalize_address(req.model_dump())
    except PaymentMethodInventoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = datetime.now(UTC)
    row = PaymentAddressPoolModel(
        id=str(uuid4()),
        **data,
        address_status=req.address_status,
        use_count=0,
        created_at=now,
        updated_at=now,
    )
    _persist_payment_pool_row(session, row, "payment address already exists")
    return _payment_address_pool_dict(row)


@router.patch("/payment-method-pools/addresses/{pool_id}")
def patch_payment_address_pool(
    pool_id: str,
    req: PatchPaymentAddressPoolRequest,
    session: DbSession,
) -> dict:
    row = session.get(PaymentAddressPoolModel, pool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="payment address not found")
    if all(value is None for value in req.model_dump().values()):
        raise HTTPException(status_code=400, detail="no payment address fields to update")
    if req.address_status is not None:
        _validate_payment_pool_status(
            req.address_status, {"active", "disabled"}, "address_status"
        )
        row.address_status = req.address_status
    address_values = {
        "line1": row.line1,
        "line2": row.line2,
        "city": row.city,
        "state": row.state,
        "postal_code": row.postal_code,
        "country": row.country,
        "phone": row.phone,
    }
    for field_name in address_values:
        value = getattr(req, field_name)
        if value is not None:
            address_values[field_name] = value
    if any(getattr(req, field_name) is not None for field_name in address_values):
        try:
            _key, data = _normalize_address(address_values)
        except PaymentMethodInventoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for field_name in (
            "address_key",
            "line1",
            "line2",
            "city",
            "state",
            "postal_code",
            "country",
            "phone",
        ):
            setattr(row, field_name, data[field_name])
    row.updated_at = datetime.now(UTC)
    _commit_payment_pool_row(session, row, "payment address already exists")
    return _payment_address_pool_dict(row)


@router.delete("/payment-method-pools/addresses/{pool_id}")
def delete_payment_address_pool(pool_id: str, session: DbSession) -> dict:
    row = session.get(PaymentAddressPoolModel, pool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="payment address not found")
    session.delete(row)
    session.commit()
    return {"payment_address_id": pool_id, "deleted": True}


@router.get("/payment-method-pools/cards")
def list_payment_card_pool(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    card_status: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(PaymentCardPoolModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                PaymentCardPoolModel.id.ilike(needle),
                PaymentCardPoolModel.last4.ilike(needle),
                PaymentCardPoolModel.card_fingerprint.ilike(needle),
                PaymentCardPoolModel.last_error_code.ilike(needle),
            )
        )
    if card_status.strip():
        stmt = stmt.where(PaymentCardPoolModel.card_status.in_(_csv_values(card_status)))
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": PaymentCardPoolModel.created_at,
            "updated_at": PaymentCardPoolModel.updated_at,
            "last4": PaymentCardPoolModel.last4,
            "card_status": PaymentCardPoolModel.card_status,
            "use_count": PaymentCardPoolModel.use_count,
            "last_used_at": PaymentCardPoolModel.last_used_at,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_payment_card_pool_dict(row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.post("/payment-method-pools/cards")
def create_payment_card_pool(
    req: CreatePaymentCardPoolRequest,
    session: DbSession,
) -> dict:
    _validate_payment_pool_status(req.card_status, {"available", "disabled"}, "card_status")
    try:
        _key, data = _normalize_card(req.model_dump())
    except PaymentMethodInventoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    now = datetime.now(UTC)
    row = PaymentCardPoolModel(
        id=str(uuid4()),
        **data,
        card_status=req.card_status,
        reserved_by_space_id=None,
        reserved_at=None,
        use_count=0,
        last_used_at=None,
        last_error_code="",
        last_error_message="",
        created_at=now,
        updated_at=now,
    )
    _persist_payment_pool_row(session, row, "payment card already exists")
    return _payment_card_pool_dict(row)


@router.patch("/payment-method-pools/cards/{pool_id}")
def patch_payment_card_pool(
    pool_id: str,
    req: PatchPaymentCardPoolRequest,
    session: DbSession,
) -> dict:
    row = session.get(PaymentCardPoolModel, pool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="payment card not found")
    if all(value is None for value in req.model_dump().values()):
        raise HTTPException(status_code=400, detail="no payment card fields to update")
    if row.card_status == "in_use":
        raise HTTPException(status_code=409, detail="payment card is currently reserved")
    if req.card_status is not None:
        _validate_payment_pool_status(
            req.card_status,
            {"available", "failed", "used", "disabled"},
            "card_status",
        )
        row.card_status = req.card_status
    if any(
        value is not None
        for value in (req.card_number, req.cvc, req.exp_month, req.exp_year)
    ):
        card_values = {
            "card_number": req.card_number if req.card_number is not None else row.card_number,
            "cvc": req.cvc if req.cvc is not None else row.cvc,
            "exp_month": req.exp_month if req.exp_month is not None else row.exp_month,
            "exp_year": req.exp_year if req.exp_year is not None else row.exp_year,
        }
        try:
            _key, data = _normalize_card(card_values)
        except PaymentMethodInventoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        for field_name in (
            "card_fingerprint",
            "card_number",
            "cvc",
            "last4",
            "exp_month",
            "exp_year",
        ):
            setattr(row, field_name, data[field_name])
    row.updated_at = datetime.now(UTC)
    _commit_payment_pool_row(session, row, "payment card already exists")
    return _payment_card_pool_dict(row)


@router.delete("/payment-method-pools/cards/{pool_id}")
def delete_payment_card_pool(pool_id: str, session: DbSession) -> dict:
    row = session.get(PaymentCardPoolModel, pool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="payment card not found")
    if row.card_status == "in_use":
        raise HTTPException(status_code=409, detail="payment card is currently reserved")
    session.delete(row)
    session.commit()
    return {"payment_card_id": pool_id, "deleted": True}


@router.patch("/spaces/{space_id}")
def patch_space(space_id: str, req: PatchSpaceRequest, session: DbSession) -> dict:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if req.space_status is None and req.auto_replenish_enabled is None:
        raise HTTPException(status_code=400, detail="no space fields to update")
    if req.space_status is not None:
        requested_status = req.space_status.strip()
        if requested_status not in OPERATOR_SPACE_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="space_status must be active or disabled",
            )
        space.space_status = requested_status
    if req.auto_replenish_enabled is not None:
        if space.space_type != "business":
            raise HTTPException(
                status_code=400,
                detail="automatic replenish only supports business spaces",
            )
        space.auto_replenish_enabled = bool(req.auto_replenish_enabled)
    space.updated_at = datetime.now(UTC)
    session.commit()
    return _space_dict(space, session=session)


@router.post("/space-replenish-emails/import")
def import_replenish_emails(
    req: ImportSpaceReplenishEmailsRequest,
    session: DbSession,
) -> dict:
    result = import_space_replenish_emails(
        session_factory=_session_factory_from_session(session),
        emails=req.emails,
    )
    if result["requested"] == 0:
        raise HTTPException(status_code=400, detail="no valid email addresses")
    return {**result, **_space_replenish_email_summary(session=session)}


@router.get("/space-replenish-emails/summary")
def get_space_replenish_email_summary(session: DbSession) -> dict:
    return _space_replenish_email_summary(session=session)


@router.post("/spaces/{space_id}/auto-replenish/hosting")
def host_space_auto_replenishment_route(
    space_id: str,
    session: DbSession,
) -> dict:
    settings = get_settings()
    try:
        return host_space_auto_replenishment(
            session_factory=_session_factory_from_session(session),
            invite_executor_base_url=settings.session_otp_executor_base_url,
            invite_executor_api_key=settings.session_otp_executor_api_key,
            space_id=space_id,
        )
    except (SpaceAutoReplenishError, ProxyWorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/spaces/{space_id}/auto-replenish/hosting")
def cancel_space_auto_replenishment_hosting_route(
    space_id: str,
    session: DbSession,
) -> dict:
    settings = get_settings()
    try:
        return cancel_space_auto_replenishment_hosting(
            session_factory=_session_factory_from_session(session),
            invite_executor_base_url=settings.session_otp_executor_base_url,
            invite_executor_api_key=settings.session_otp_executor_api_key,
            space_id=space_id,
        )
    except SpaceAutoReplenishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/spaces/{space_id}/auto-replenish/invite-job")
def create_space_auto_replenish_invite_job(
    space_id: str,
    req: SpaceAutoReplenishInviteJobRequest,
    session: DbSession,
) -> dict:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if space.space_type != "business" or space.space_status != "active":
        raise HTTPException(
            status_code=400,
            detail="automatic replenish invitations require an active business space",
        )
    space.auto_replenish_enabled = True
    space.updated_at = datetime.now(UTC)
    job = JobQueue(session).enqueue(
        job_type="space.auto_replenish.invite.prepare",
        input_json={
            "space_id": space.id,
            "invite_count": MAX_INVITE_BATCH_SIZE,
            "work_count": 1,
        },
        created_by=req.created_by.strip() or "ops:space-server-invite",
    )
    session.commit()
    return {
        "job_id": job.id,
        "job_status": job.job_status,
        "work_count": 1,
        "selected_count": 1,
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "failed": 0,
        "cancelled": 0,
    }


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
        ).sync_remote_memberships_only(
            space_id=space_id, page_size=max(1, int(req.page_size or 100))
        )
    except SpaceMembershipInviteSyncWorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (OpenAIChatGPTClientError, ProxyWorkflowError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/spaces/{space_id}/seat-expansion-job")
def create_space_seat_expansion_job(
    space_id: str,
    req: SpaceSeatExpansionJobRequest,
    session: DbSession,
) -> dict:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if space.space_type != "business":
        raise HTTPException(status_code=400, detail="seat expansion only supports business spaces")
    return _create_space_seat_expand_work_job(
        session=session,
        work_count=max(1, int(req.work_count or 1)),
        created_by=req.created_by.strip() or "ops:space-seat-expand",
        space_id=space_id,
    )


@router.post("/spaces/payment-method-bind-selected-job")
def create_selected_personal_payment_method_bind_job(
    req: PersonalPaymentMethodBindSelectedJobRequest,
    session: DbSession,
) -> dict:
    requested_space_ids, selected, selection_skipped = (
        _select_personal_payment_method_bind_spaces(
            session=session,
            space_ids=req.space_ids,
        )
    )
    work_count = 1
    if not selected:
        return {
            "job_id": "",
            "job_status": "skipped",
            "run_id": "",
            "work_count": work_count,
            "requested_count": len(requested_space_ids),
            "selected_count": 0,
            "selection_skipped_count": len(selection_skipped),
            "selection_skipped": selection_skipped,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        }

    inventory = payment_method_inventory_summary(session)
    missing_pools = [
        name
        for name, count in (
            ("name", inventory["active_name_count"]),
            ("address", inventory["active_address_count"]),
            ("card", inventory["available_card_count"]),
        )
        if int(count or 0) < 1
    ]
    if missing_pools:
        raise HTTPException(
            status_code=409,
            detail={"message": "payment method inventory is empty", "pools": missing_pools},
        )

    job, run = _start_work_job(
        session=session,
        job_type="space.personal_payment_method_bind.tick",
        input_json={
            "space_ids": [space.id for space in selected],
            "limit": len(selected),
            "work_count": work_count,
            "requested_count": len(requested_space_ids),
            "selected_count": len(selected),
            "selection_skipped": selection_skipped,
            "auto_start_plus_checkout": req.auto_start_plus_checkout,
        },
        created_by=req.created_by.strip() or "ops:personal-payment-method-bind-selected",
    )
    queue = WorkQueue(session)
    for space in selected:
        queue.enqueue(
            job_id=job.id,
            work_type="space.personal_payment_method_bind.space",
            execution_key=f"personal-payment-method:{space.id}",
            input_json={
                "space_id": space.id,
                "auto_start_plus_checkout": req.auto_start_plus_checkout,
                "_run_id": run.id,
            },
        )
    session.commit()
    result = _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=work_count,
        selected_count=len(selected),
    )
    result.update(
        {
            "requested_count": len(requested_space_ids),
            "selection_skipped_count": len(selection_skipped),
            "selection_skipped": selection_skipped,
        }
    )
    return result


@router.post("/spaces/promotion-check-selected-job")
def create_selected_personal_promotion_check_job(
    req: PersonalPromotionCheckSelectedJobRequest,
    session: DbSession,
) -> dict:
    requested_space_ids, selected, selection_skipped = (
        _select_personal_promotion_check_spaces(
            session=session,
            space_ids=req.space_ids,
        )
    )
    proxy_country = req.proxy_country.strip().upper()
    work_count = int(req.work_count)
    if not selected:
        return {
            "job_id": "",
            "job_status": "skipped",
            "run_id": "",
            "work_count": work_count,
            "requested_count": len(requested_space_ids),
            "selected_count": 0,
            "selection_skipped_count": len(selection_skipped),
            "selection_skipped": selection_skipped,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        }

    job, run = _start_work_job(
        session=session,
        job_type="space.personal_promotion_check.selected",
        input_json={
            "space_ids": [space.id for space in selected],
            "proxy_country": proxy_country,
            "work_count": work_count,
            "requested_count": len(requested_space_ids),
            "selected_count": len(selected),
            "selection_skipped": selection_skipped,
        },
        created_by=req.created_by.strip() or "ops:personal-promotion-check-selected",
    )
    queue = WorkQueue(session)
    for space in selected:
        queue.enqueue(
            job_id=job.id,
            work_type="space.personal_promotion_check.space",
            execution_key=f"personal-promotion-check:{space.id}",
            input_json={
                "space_id": space.id,
                "proxy_country": proxy_country,
                "_run_id": run.id,
            },
        )
    session.commit()
    result = _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=work_count,
        selected_count=len(selected),
    )
    result.update(
        {
            "requested_count": len(requested_space_ids),
            "selection_skipped_count": len(selection_skipped),
            "selection_skipped": selection_skipped,
        }
    )
    return result


@router.post("/spaces/{space_id}/payment-method-bind-job")
def create_personal_payment_method_bind_job(
    space_id: str,
    req: PersonalPaymentMethodBindJobRequest,
    session: DbSession,
) -> dict:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if space.space_type != "personal" or space.space_status != "active":
        raise HTTPException(
            status_code=400,
            detail="payment method binding requires an active personal space",
        )
    if not space.has_promotion or not str(space.promotion_id or "").strip():
        raise HTTPException(
            status_code=409,
            detail="payment method binding requires an eligible promotion",
        )
    if space.has_payment_method and space.payment_method_status == "bound":
        raise HTTPException(status_code=409, detail="personal space already has a payment method")
    if (
        space.payment_method_attempt_count >= PAYMENT_METHOD_MAX_ATTEMPTS
        and (
            space.payment_method_cooldown_until is None
            or space.payment_method_cooldown_until > datetime.now(UTC)
        )
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "payment method binding is cooling down",
                "cooldown_until": _iso(space.payment_method_cooldown_until),
            },
        )

    active_job = _active_personal_payment_method_bind_jobs_by_space_id(
        session=session,
    ).get(space.id)
    if active_job is None:
        active_job = _active_work_job_for_type(
            session=session,
            job_type="space.personal_payment_method_bind.tick",
            space_id=space.id,
        )
    if active_job is not None:
        summary = _work_summary(session, active_job.id)
        return {
            "job_id": active_job.id,
            "job_status": active_job.job_status,
            "work_count": 1,
            "selected_count": sum(summary.values()) or 1,
            **summary,
            "skipped_reason": "active_personal_payment_method_bind_job_exists",
        }

    inventory = payment_method_inventory_summary(session)
    missing_pools = [
        name
        for name, count in (
            ("name", inventory["active_name_count"]),
            ("address", inventory["active_address_count"]),
            ("card", inventory["available_card_count"]),
        )
        if int(count or 0) < 1
    ]
    if missing_pools:
        raise HTTPException(
            status_code=409,
            detail={"message": "payment method inventory is empty", "pools": missing_pools},
        )

    job, run = _start_work_job(
        session=session,
        job_type="space.personal_payment_method_bind.tick",
        input_json={
            "space_id": space.id,
            "limit": 1,
            "work_count": 1,
            "auto_start_plus_checkout": req.auto_start_plus_checkout,
        },
        created_by=req.created_by.strip() or "ops:personal-payment-method-bind",
    )
    WorkQueue(session).enqueue(
        job_id=job.id,
        work_type="space.personal_payment_method_bind.space",
        execution_key=f"personal-payment-method:{space.id}",
        input_json={
            "space_id": space.id,
            "auto_start_plus_checkout": req.auto_start_plus_checkout,
            "_run_id": run.id,
        },
    )
    session.commit()
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=1,
        selected_count=1,
    )


@router.post("/spaces/{space_id}/plus-checkout-job")
def create_personal_plus_checkout_job(
    space_id: str,
    req: PersonalPlusCheckoutJobRequest,
    session: DbSession,
) -> dict:
    space = session.get(SpaceModel, space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if (
        space.provider != "openai_chatgpt"
        or space.space_type != "personal"
        or space.space_status != "active"
    ):
        raise HTTPException(
            status_code=400,
            detail="plus checkout requires an active personal space",
        )
    if not space.has_promotion or not str(space.promotion_id or "").strip():
        raise HTTPException(status_code=409, detail="plus checkout requires an eligible promotion")
    if not space.has_payment_method or space.payment_method_status != "bound":
        raise HTTPException(status_code=409, detail="plus checkout requires a bound payment method")
    account = session.get(UserAccountModel, space.owner_user_account_id)
    if account is None or account.account_status != "active":
        raise HTTPException(status_code=409, detail="plus checkout owner account is not active")
    active_job = _active_work_job_for_type(
        session=session,
        job_type="space.personal_plus_checkout.tick",
        space_id=space.id,
    )
    if active_job is not None:
        summary = _work_summary(session, active_job.id)
        return {
            "job_id": active_job.id,
            "job_status": active_job.job_status,
            "work_count": 1,
            "selected_count": 1,
            **summary,
            "skipped_reason": "active_personal_plus_checkout_job_exists",
        }
    job, run = _start_work_job(
        session=session,
        job_type="space.personal_plus_checkout.tick",
        input_json={
            "space_id": space.id,
            "limit": 1,
            "work_count": 1,
            "create_proxy_country": req.create_proxy_country.strip().upper(),
            "promo_proxy_country": req.promo_proxy_country.strip().upper(),
            "promo_campaign_id": req.promo_campaign_id.strip(),
        },
        created_by=req.created_by.strip() or "ops:personal-plus-checkout",
    )
    WorkQueue(session).enqueue(
        job_id=job.id,
        work_type="space.personal_plus_checkout.space",
        execution_key=f"personal-plus-checkout:{space.id}",
        input_json={
            "space_id": space.id,
            "create_proxy_country": req.create_proxy_country.strip().upper(),
            "promo_proxy_country": req.promo_proxy_country.strip().upper(),
            "promo_campaign_id": req.promo_campaign_id.strip(),
            "_run_id": run.id,
        },
    )
    session.commit()
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=1,
        selected_count=1,
    )


@router.get("/space-credentials")
def list_space_credentials(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    credential_status: str = "",
    auth_mode: str = "",
    space_id: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(SpaceCredentialModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                SpaceCredentialModel.id.ilike(needle),
                SpaceCredentialModel.user_account_id.ilike(needle),
                SpaceCredentialModel.space_id.ilike(needle),
                SpaceCredentialModel.external_credential_id.ilike(needle),
                SpaceCredentialModel.account_id.ilike(needle),
            )
        )
    if credential_status.strip():
        stmt = stmt.where(
            SpaceCredentialModel.credential_status.in_(_csv_values(credential_status))
        )
    if auth_mode.strip():
        stmt = stmt.where(SpaceCredentialModel.auth_mode.in_(_csv_values(auth_mode)))
    if space_id.strip():
        stmt = stmt.where(SpaceCredentialModel.space_id == space_id.strip())
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": SpaceCredentialModel.created_at,
            "updated_at": SpaceCredentialModel.updated_at,
            "expires_at": SpaceCredentialModel.expires_at,
            "credential_status": SpaceCredentialModel.credential_status,
            "auth_mode": SpaceCredentialModel.auth_mode,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_space_credential_dict(session=session, credential=row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.get("/space-push-records")
def list_space_push_records(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-updated_at",
    push_status: str = "",
    recycle_status: str = "",
    downstream_channel_id: str = "",
    credential_type: str = "",
    distribution_mode: str = "",
    q: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(SpacePushBindingModel)
    if push_status.strip():
        stmt = stmt.where(SpacePushBindingModel.push_status.in_(_csv_values(push_status)))
    if recycle_status.strip():
        stmt = stmt.where(SpacePushBindingModel.recycle_status.in_(_csv_values(recycle_status)))
    if downstream_channel_id.strip():
        stmt = stmt.where(
            SpacePushBindingModel.downstream_channel_id == downstream_channel_id.strip()
        )
    if credential_type.strip():
        stmt = stmt.where(
            SpacePushBindingModel.space_credential_id.in_(
                select(SpaceCredentialModel.id)
                .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
                .where(SpaceModel.credential_type.in_(_csv_values(credential_type)))
            )
        )
    normalized_distribution_mode = distribution_mode.strip()
    manual_export_condition = and_(
        SpacePushBindingModel.downstream_channel_id.is_(None),
        SpacePushBindingModel.downstream_external_id.like("manual-export-%"),
    )
    if normalized_distribution_mode == "manual_export":
        stmt = stmt.where(manual_export_condition)
    elif normalized_distribution_mode == "channel_push":
        stmt = stmt.where(~manual_export_condition)
    elif normalized_distribution_mode:
        raise HTTPException(status_code=400, detail="unsupported distribution_mode")
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                SpacePushBindingModel.space_credential_id.ilike(needle),
                SpacePushBindingModel.error_code.ilike(needle),
                SpacePushBindingModel.error_message.ilike(needle),
                SpacePushBindingModel.downstream_external_id.ilike(needle),
                SpacePushBindingModel.space_credential_id.in_(
                    select(SpaceCredentialModel.id)
                    .join(
                        UserAccountModel,
                        UserAccountModel.id == SpaceCredentialModel.user_account_id,
                    )
                    .join(SpaceModel, SpaceModel.id == SpaceCredentialModel.space_id)
                    .where(
                        or_(
                            UserAccountModel.email.ilike(needle),
                            SpaceModel.name.ilike(needle),
                            SpaceModel.external_space_id.ilike(needle),
                        )
                    )
                ),
            )
        )
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": SpacePushBindingModel.created_at,
            "updated_at": SpacePushBindingModel.updated_at,
            "push_status": SpacePushBindingModel.push_status,
            "recycle_status": SpacePushBindingModel.recycle_status,
        },
        default="-updated_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_space_push_record_dict(session=session, binding=row) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


@router.post("/space-push-records/export-unpushed-sub2api")
def export_unpushed_space_credentials(
    req: ExportUnpushedSpaceCredentialsRequest,
    session: DbSession,
) -> Response:
    try:
        result = export_unpushed_sub2api_jsonl(
            session=session,
            credential_type=req.credential_type,
            space_id=req.space_id,
            limit=req.limit,
        )
        session.commit()
    except SpaceManualExportError as exc:
        session.rollback()
        status_code = 409 if str(exc) == "no_unpushed_credentials" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return _space_export_response(result)


@router.post("/space-push-records/redownload-sub2api")
def redownload_space_credentials(
    req: RedownloadSpaceCredentialsRequest,
    session: DbSession,
) -> Response:
    try:
        result = redownload_sub2api_jsonl(
            session=session,
            space_credential_ids=req.space_credential_ids,
            export_batch_id=req.export_batch_id,
        )
    except SpaceManualExportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _space_export_response(result)


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
def create_protocol_registration_job(
    req: ProtocolRegistrationJobRequest, session: DbSession
) -> dict:
    if req.mode not in (
        EMAIL_PROTOCOL_NO_PHONE,
        EMAIL_BROWSER_NO_PHONE,
        PHONE_PROTOCOL_BIND_EMAIL,
    ):
        raise HTTPException(status_code=400, detail=f"unsupported registration mode: {req.mode}")
    mail_provider = str(req.mail_provider or "").strip()
    if mail_provider not in SUPPORTED_REGISTRATION_MAIL_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported registration mail provider: {mail_provider}",
        )
    job = JobQueue(session).enqueue(
        job_type="account.protocol_register",
        input_json={
            "mode": req.mode,
            "count": max(1, int(req.count or 1)),
            "work_count": max(1, int(req.work_count or 1)),
            "use_proxy": bool(req.use_proxy),
            "proxy_country": str(req.proxy_country or "US").strip().upper(),
            "authorize_codex_after_security": bool(req.authorize_codex_after_security),
            "mail_provider": mail_provider,
            "email_domain": (
                "" if mail_provider == ICLOUD_HIDE_MY_EMAIL_PROVIDER else req.email_domain
            ),
            "project_key": req.project_key,
            "caller_id": req.caller_id,
            "browser_headless": bool(req.browser_headless),
            "browser_otp_timeout_s": max(1, int(req.browser_otp_timeout_s or 180)),
            "browser_close_delay_s": max(0.0, float(req.browser_close_delay_s or 0.0)),
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


@router.post("/account-email-change/jobs")
def create_account_email_change_job(
    req: AccountEmailChangeJobRequest,
    session: DbSession,
) -> dict:
    if req.mode == ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM:
        return _create_auto_claim_email_change_job(req=req, session=session)
    if req.mode != ACCOUNT_EMAIL_CHANGE_MODE_MAPPED:
        raise HTTPException(status_code=400, detail=f"unsupported email change mode: {req.mode}")

    try:
        pairs = parse_account_email_change_csv(req.csv_text)
    except AccountEmailChangeCsvError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_emails = sorted(
        {email.lower() for pair in pairs for email in (pair.old_mail, pair.new_mail)}
    )
    existing_accounts = session.scalars(
        select(UserAccountModel).where(func.lower(UserAccountModel.email).in_(normalized_emails))
    ).all()
    if existing_accounts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "CSV emails already exist in user_accounts",
                "accounts": [
                    {"user_account_id": account.id, "email": account.email}
                    for account in existing_accounts[:50]
                ],
            },
        )

    worker_count = max(1, int(req.work_count or 5))
    otp_timeout_s = max(1, int(req.otp_timeout_s or 180))
    job, run = _start_work_job(
        session=session,
        job_type="account.change_email.bulk",
        input_json={
            "mode": ACCOUNT_EMAIL_CHANGE_MODE_MAPPED,
            "work_count": worker_count,
            "selected_count": len(pairs),
            "otp_timeout_s": otp_timeout_s,
        },
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    queue = WorkQueue(session)
    for pair in pairs:
        user_account_id = f"email-change-account-{uuid4()}"
        session.add(
            UserAccountModel(
                id=user_account_id,
                email=pair.old_mail,
                account_status="registering",
                session_status="unknown",
                created_at=now,
                updated_at=now,
            )
        )
        queue.enqueue(
            job_id=job.id,
            work_type="account.change_email.one",
            input_json={
                "user_account_id": user_account_id,
                "old_mail": pair.old_mail,
                "new_mail": pair.new_mail,
                "mode": ACCOUNT_EMAIL_CHANGE_MODE_MAPPED,
                "csv_row_number": pair.row_number,
                "otp_timeout_s": otp_timeout_s,
                "_run_id": run.id,
            },
        )
    session.commit()
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=worker_count,
        selected_count=len(pairs),
    )


def _create_auto_claim_email_change_job(
    *,
    req: AccountEmailChangeJobRequest,
    session: Session,
) -> dict:
    if str(req.mail_provider or "").strip() != "outlook":
        raise HTTPException(
            status_code=400,
            detail="automatic email change currently requires mail_provider=outlook",
        )
    try:
        sources = parse_account_email_change_source_jsonl(req.source_jsonl_text)
    except AccountEmailChangeSourceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    normalized_emails = [source.email.casefold() for source in sources]
    openai_user_ids = [source.openai_user_id for source in sources]
    external_space_ids = [source.chatgpt_account_id for source in sources]
    existing_accounts = session.scalars(
        select(UserAccountModel).where(
            or_(
                func.lower(UserAccountModel.email).in_(normalized_emails),
                UserAccountModel.openai_user_id.in_(openai_user_ids),
            )
        )
    ).all()
    existing_spaces = session.scalars(
        select(SpaceModel).where(SpaceModel.external_space_id.in_(external_space_ids))
    ).all()
    accounts_by_email = {account.email.casefold(): account for account in existing_accounts}
    accounts_by_user_id = {
        account.openai_user_id: account
        for account in existing_accounts
        if account.openai_user_id
    }
    spaces_by_external_id = {
        space.external_space_id: space
        for space in existing_spaces
        if space.external_space_id
    }
    conflicts: list[dict] = []
    resolved_accounts: dict[int, UserAccountModel] = {}
    for source in sources:
        email_account = accounts_by_email.get(source.email.casefold())
        identity_account = accounts_by_user_id.get(source.openai_user_id)
        if (
            email_account is not None
            and identity_account is not None
            and email_account.id != identity_account.id
        ):
            conflicts.append(
                {
                    "source_email": source.email,
                    "reason": "email and OpenAI user ID resolve to different local accounts",
                    "email_account_id": email_account.id,
                    "identity_account_id": identity_account.id,
                }
            )
            continue
        account = email_account or identity_account
        space = spaces_by_external_id.get(source.chatgpt_account_id)
        if account is None:
            if space is not None:
                conflicts.append(
                    {
                        "source_email": source.email,
                        "reason": "personal space already belongs to another local account",
                        "space_id": space.id,
                        "owner_user_account_id": space.owner_user_account_id,
                    }
                )
            continue
        if account.email.casefold() != source.email.casefold() or (
            account.openai_user_id
            and account.openai_user_id != source.openai_user_id
        ):
            conflicts.append(
                {
                    "source_email": source.email,
                    "reason": "local account identity does not match source record",
                    "user_account_id": account.id,
                    "local_email": account.email,
                    "local_openai_user_id": account.openai_user_id,
                }
            )
            continue
        if (
            space is None
            or space.owner_user_account_id != account.id
            or space.space_type != "personal"
        ):
            conflicts.append(
                {
                    "source_email": source.email,
                    "reason": "local personal space does not match source record",
                    "user_account_id": account.id,
                    "space_id": space.id if space is not None else "",
                    "space_owner_user_account_id": (
                        space.owner_user_account_id if space is not None else ""
                    ),
                }
            )
            continue
        resolved_accounts[source.row_number] = account

    if conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "source accounts conflict with local identities",
                "conflicts": conflicts[:50],
            },
        )

    worker_count = max(1, int(req.work_count or 5))
    otp_timeout_s = max(1, int(req.otp_timeout_s or 180))
    mail_provider = str(req.mail_provider or "outlook").strip()
    project_key = ""
    caller_id = str(req.caller_id or "refactor-app-protocol-registration").strip()
    email_domain = str(req.email_domain or "").strip()
    if not caller_id:
        raise HTTPException(status_code=400, detail="caller_id is required")

    job, run = _start_work_job(
        session=session,
        job_type="account.change_email.bulk",
        input_json={
            "mode": ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
            "work_count": worker_count,
            "selected_count": len(sources),
            "otp_timeout_s": otp_timeout_s,
            "mail_provider": mail_provider,
            "project_key": project_key,
        },
        created_by=req.created_by,
    )
    now = datetime.now(UTC)
    queue = WorkQueue(session)
    reused_account_count = 0
    for source in sources:
        existing_account = resolved_accounts.get(source.row_number)
        if existing_account is not None:
            user_account_id = existing_account.id
            existing_account.email = source.email
            existing_account.openai_user_id = source.openai_user_id
            if source.password:
                existing_account.password = source.password
            if source.phone_number:
                existing_account.phone_number = source.phone_number
            existing_account.updated_at = now
            reused_account_count += 1
        else:
            user_account_id = f"email-change-account-{uuid4()}"
            _add_email_change_source_account(
                session=session,
                source=source,
                user_account_id=user_account_id,
                now=now,
            )
        queue.enqueue(
            job_id=job.id,
            work_type="account.change_email.one",
            input_json={
                "user_account_id": user_account_id,
                "old_mail": source.email,
                "new_mail": "",
                "mode": ACCOUNT_EMAIL_CHANGE_MODE_AUTO_CLAIM,
                "source_row_number": source.row_number,
                "source_db_id": source.source_db_id,
                "otp_timeout_s": otp_timeout_s,
                "mail_provider": mail_provider,
                "project_key": project_key,
                "caller_id": caller_id,
                "email_domain": email_domain,
                "source_mailbox_url": source.mailbox_url,
                "source_mailbox_client_id": source.mailbox_client_id,
                "source_mailbox_refresh_token": source.mailbox_refresh_token,
                "source_mailbox_access_token": source.mailbox_access_token,
                "_run_id": run.id,
            },
        )
    session.commit()
    response = _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=worker_count,
        selected_count=len(sources),
    )
    response["reused_account_count"] = reused_account_count
    return response


def _add_email_change_source_account(
    *,
    session: Session,
    source: AccountEmailChangeSource,
    user_account_id: str,
    now: datetime,
) -> None:
    session.add(
        UserAccountModel(
            id=user_account_id,
            email=source.email,
            phone_number=source.phone_number,
            openai_user_id=source.openai_user_id,
            password=source.password,
            access_token=source.access_token,
            session_token=source.session_token,
            cookie_header=source.cookie_header,
            device_id=source.device_id,
            csrf_token=source.csrf_token,
            session_status=(
                "active" if source.session_token or source.cookie_header else "unknown"
            ),
            last_session_refresh_at=source.last_used_at,
            account_status="active",
            created_at=source.created_at or now,
            updated_at=now,
        )
    )
    session.add(
        SpaceModel(
            id=f"space-{uuid4()}",
            provider="openai_chatgpt",
            external_space_id=source.chatgpt_account_id,
            owner_user_account_id=user_account_id,
            name=source.email,
            space_type="personal",
            auth_mode="codex_oauth",
            credential_type="personal_account",
            plan_type="",
            seat_limit=0,
            seats_in_use=0,
            seats_entitled=0,
            space_status="active",
            source_admin_session_id="",
            raw_space_json={
                "import_source": "account_email_change_source_jsonl",
                "source_db_id": source.source_db_id,
            },
            created_at=source.created_at or now,
            updated_at=now,
        )
    )


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
            raise HTTPException(
                status_code=400, detail=f"business space usage probe failed: {exc}"
            ) from exc
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
        spaces.append(_space_dict(space, session=session))
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
    space.space_status = space_status_after_discovery(space.space_status)
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
            "proxy_binding": _team_admin_proxy_binding_dict(
                session=session, team_admin_session_id=row.id
            ),
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
    deleted_membership_count = (
        int(
            session.scalar(
                select(func.count()).where(SpaceMembershipModel.space_id.in_(deleted_space_ids))
            )
            or 0
        )
        if deleted_space_ids
        else 0
    )
    deleted_credential_count = (
        int(
            session.scalar(
                select(func.count()).where(SpaceCredentialModel.space_id.in_(deleted_space_ids))
            )
            or 0
        )
        if deleted_space_ids
        else 0
    )
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
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    space_id: str = "",
    space: str = "",
    external_space_id: str = "",
    user_account_id: str = "",
    user_email: str = "",
    admin_email: str = "",
    credential_type: str = "",
    plan_type: str = "",
    membership_status: str = "",
    session_account_detected: str = "",
    has_space_credential: str = "",
    session_otp_status: str = "",
    codex_select_channel_required: str = "",
    session_recency: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = (
        select(
            SpaceMembershipModel,
            UserAccountModel,
            SpaceModel,
            TeamAdminSessionModel,
            SpaceCredentialModel,
            AccountSessionOtpSnapshotModel,
        )
        .join(UserAccountModel, UserAccountModel.id == SpaceMembershipModel.user_account_id)
        .join(SpaceModel, SpaceModel.id == SpaceMembershipModel.space_id)
        .outerjoin(
            TeamAdminSessionModel,
            TeamAdminSessionModel.id == SpaceModel.source_admin_session_id,
        )
        .outerjoin(
            SpaceCredentialModel,
            and_(
                SpaceCredentialModel.space_id == SpaceMembershipModel.space_id,
                SpaceCredentialModel.user_account_id == SpaceMembershipModel.user_account_id,
            ),
        )
        .outerjoin(
            AccountSessionOtpSnapshotModel,
            AccountSessionOtpSnapshotModel.user_account_id == SpaceMembershipModel.user_account_id,
        )
    )
    selected_space_id = space_id.strip() or space.strip()
    if selected_space_id:
        stmt = stmt.where(SpaceMembershipModel.space_id == selected_space_id)
    if external_space_id.strip():
        stmt = stmt.where(SpaceModel.external_space_id == external_space_id.strip())
    if user_account_id.strip():
        stmt = stmt.where(SpaceMembershipModel.user_account_id == user_account_id.strip())
    if user_email.strip():
        stmt = stmt.where(UserAccountModel.email.ilike(f"%{user_email.strip()}%"))
    if admin_email.strip():
        stmt = stmt.where(TeamAdminSessionModel.admin_email.ilike(f"%{admin_email.strip()}%"))
    if credential_type.strip():
        normalized_credential_type = credential_type.strip()
        if normalized_credential_type not in SPACE_CREDENTIAL_TYPES:
            raise HTTPException(status_code=400, detail="unsupported credential_type")
        stmt = stmt.where(SpaceModel.credential_type == normalized_credential_type)
    stmt = _apply_plan_type_filter(stmt, column=SpaceModel.plan_type, value=plan_type)
    if membership_status.strip():
        stmt = stmt.where(
            SpaceMembershipModel.membership_status.in_(_csv_values(membership_status))
        )
    detected_filter = session_account_detected.strip().lower()
    if detected_filter in {"yes", "true", "1"}:
        stmt = stmt.where(SpaceMembershipModel.session_account_detected.is_(True))
    if detected_filter in {"no", "false", "0"}:
        stmt = stmt.where(SpaceMembershipModel.session_account_detected.is_(False))
    credential_filter = has_space_credential.strip().lower()
    if credential_filter in {"yes", "true", "1"}:
        stmt = stmt.where(SpaceCredentialModel.id.is_not(None))
    if credential_filter in {"no", "false", "0"}:
        stmt = stmt.where(SpaceCredentialModel.id.is_(None))
    if session_otp_status.strip():
        stmt = stmt.where(
            AccountSessionOtpSnapshotModel.snapshot_status.in_(_csv_values(session_otp_status))
        )
    select_channel_filter = codex_select_channel_required.strip().lower()
    if select_channel_filter in {"yes", "true", "1"}:
        stmt = stmt.where(UserAccountModel.codex_select_channel_required.is_(True))
    if select_channel_filter in {"no", "false", "0"}:
        stmt = stmt.where(UserAccountModel.codex_select_channel_required.is_(False))
    stmt = _apply_session_recency_filter(
        stmt,
        column=UserAccountModel.last_session_refresh_at,
        value=session_recency,
    )
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                UserAccountModel.email.ilike(needle),
                SpaceModel.name.ilike(needle),
                SpaceModel.external_space_id.ilike(needle),
                SpaceMembershipModel.id.ilike(needle),
                SpaceMembershipModel.failure_code.ilike(needle),
                SpaceMembershipModel.failure_message.ilike(needle),
                TeamAdminSessionModel.admin_email.ilike(needle),
            )
        )
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": SpaceMembershipModel.created_at,
            "updated_at": SpaceMembershipModel.updated_at,
            "remote_synced_at": SpaceMembershipModel.remote_synced_at,
            "email": UserAccountModel.email,
            "space": SpaceModel.name,
            "membership_status": SpaceMembershipModel.membership_status,
            "plan_type": SpaceModel.plan_type,
            "space_plan_type": SpaceModel.plan_type,
            "last_session_refresh_at": UserAccountModel.last_session_refresh_at,
        },
        default="-created_at",
    )
    stmt = stmt.order_by(
        SpaceMembershipModel.id.desc()
        if normalized_sort.startswith("-")
        else SpaceMembershipModel.id.asc()
    )
    total = total_for(session, stmt)
    rows = session.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        {
            "id": membership.id,
            "space_id": membership.space_id,
            "external_space_id": space.external_space_id,
            "space_name": space.name,
            "space_type": space.space_type,
            "credential_type": space.credential_type,
            "space_plan_type": space.plan_type,
            "admin_email": admin.admin_email if admin is not None else "",
            "user_account_id": membership.user_account_id,
            "user_email": account.email,
            "email": account.email,
            "role": membership.role,
            "membership_status": membership.membership_status,
            "invite_permission": membership.invite_permission,
            "seat_status": membership.seat_status,
            "can_invite": membership.can_invite,
            "session_account_detected": membership.session_account_detected,
            "has_space_credential": credential is not None,
            "space_credential_status": credential.credential_status
            if credential is not None
            else "",
            "session_status": account.session_status,
            "codex_select_channel_required": account.codex_select_channel_required,
            "codex_select_channel_detected_at": _iso(account.codex_select_channel_detected_at),
            "last_session_refresh_at": _iso(account.last_session_refresh_at),
            "session_otp_status": otp.snapshot_status if otp is not None else "",
            "session_otp_code_len": otp.otp_code_len if otp is not None else 0,
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
        for membership, account, space, admin, credential, otp in rows
    ]
    return page_payload(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


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
    interval_seconds = max(5, int(req.interval_seconds or 60))
    config_json = _effective_space_schedule_config(
        schedule_type=req.schedule_type,
        saved_config=req.config_json,
    )
    row = session.scalar(
        select(AutomationScheduleModel).where(
            AutomationScheduleModel.schedule_type == req.schedule_type
        )
    )
    if row is None:
        row = AutomationScheduleModel(
            id=_fixed_automation_schedule_id(req.schedule_type),
            schedule_type=req.schedule_type,
            interval_seconds=interval_seconds,
            config_json=config_json,
            enabled=bool(req.enabled),
            schedule_status="active",
            next_run_at=now + timedelta(seconds=interval_seconds) if req.enabled else None,
            created_by=req.created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.interval_seconds = interval_seconds
        row.config_json = config_json
        row.enabled = bool(req.enabled)
        row.schedule_status = "active"
        row.next_run_at = now + timedelta(seconds=interval_seconds) if row.enabled else None
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
    now = datetime.now(UTC)
    reset_next_run = False
    if req.enabled is not None:
        row.enabled = bool(req.enabled)
        reset_next_run = True
        if row.enabled:
            row.schedule_status = "active"
    if req.schedule_status is not None:
        if req.schedule_status not in ("active", "paused", "error"):
            raise HTTPException(status_code=400, detail="unsupported schedule_status")
        row.schedule_status = req.schedule_status
    if req.interval_seconds is not None:
        row.interval_seconds = max(5, int(req.interval_seconds or 60))
        reset_next_run = True
    if req.config_json is not None:
        row.config_json = _effective_space_schedule_config(
            schedule_type=row.schedule_type,
            saved_config=req.config_json,
        )
    if not row.enabled:
        row.next_run_at = None
    elif reset_next_run:
        row.next_run_at = now + timedelta(seconds=max(5, int(row.interval_seconds or 60)))
    row.updated_at = now
    session.commit()
    return _automation_schedule_dict(row)


@router.post("/automation/schedules/{schedule_id}/run-now")
def run_automation_schedule_now(
    schedule_id: str,
    session: DbSession,
    req: RunAutomationScheduleNowRequest | None = None,
) -> dict:
    row = session.get(AutomationScheduleModel, schedule_id)
    if row is None:
        raise HTTPException(status_code=404, detail="automation schedule not found")
    _validate_space_schedule_type(row.schedule_type)
    request = req or RunAutomationScheduleNowRequest()
    effective_config = _effective_space_schedule_config(
        schedule_type=row.schedule_type,
        saved_config=row.config_json,
        overrides=request.config_overrides,
    )
    result = _execute_space_automation_schedule(
        session=session,
        schedule=row,
        config_json=effective_config,
        advance_next_run=False,
        created_by=request.created_by.strip() or "ops:manual-run",
    )
    session.commit()
    return {
        "schedule": _automation_schedule_dict(row),
        "effective_config_json": effective_config,
        **result,
    }


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
    return {
        "items": [_automation_monitor_run_dict(run=run, job=job) for run, job in rows],
        "limit": limit,
    }


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
    stmt = (
        select(JobEventModel, JobRunModel, JobModel)
        .join(JobRunModel, JobRunModel.id == JobEventModel.run_id)
        .join(JobModel, JobModel.id == JobRunModel.job_id)
    )
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
def list_downstream_channels(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    provider_type: str = "",
    enabled: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(DownstreamChannelModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                DownstreamChannelModel.id.ilike(needle),
                DownstreamChannelModel.name.ilike(needle),
                DownstreamChannelModel.base_url.ilike(needle),
            )
        )
    if provider_type.strip():
        stmt = stmt.where(DownstreamChannelModel.provider_type.in_(_csv_values(provider_type)))
    enabled_filter = enabled.strip().lower()
    if enabled_filter in {"yes", "true", "1"}:
        stmt = stmt.where(DownstreamChannelModel.enabled.is_(True))
    if enabled_filter in {"no", "false", "0"}:
        stmt = stmt.where(DownstreamChannelModel.enabled.is_(False))
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": DownstreamChannelModel.created_at,
            "updated_at": DownstreamChannelModel.updated_at,
            "name": DownstreamChannelModel.name,
            "provider_type": DownstreamChannelModel.provider_type,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return page_payload(
        items=[_downstream_channel_dict(channel, session=session) for channel in rows],
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


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
        sub2api_concurrency=max(
            0, int(req.sub2api_concurrency if req.sub2api_concurrency is not None else 10)
        ),
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


@router.post(
    "/downstream-channels/{channel_id}/credential-type-balances/{credential_type}/add-balance"
)
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
    if (
        req.custom_payload_type is not None
        and req.custom_payload_type not in CUSTOM_HTTP_PAYLOAD_TYPES
    ):
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
def list_proxies(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    proxy_type: str = "",
    proxy_status: str = "",
    country_code: str = "",
    provider_valid: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(ProxyInventoryModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                ProxyInventoryModel.id.ilike(needle),
                ProxyInventoryModel.proxy_host.ilike(needle),
                ProxyInventoryModel.city_name.ilike(needle),
                ProxyInventoryModel.asn_name.ilike(needle),
            )
        )
    if proxy_type.strip():
        stmt = stmt.where(ProxyInventoryModel.proxy_type.in_(_proxy_type_filter_values(proxy_type)))
    if proxy_status.strip():
        stmt = stmt.where(
            ProxyInventoryModel.proxy_status.in_(_proxy_status_filter_values(proxy_status))
        )
    if country_code.strip():
        stmt = stmt.where(ProxyInventoryModel.country_code.in_(_csv_values(country_code)))
    valid_filter = provider_valid.strip().lower()
    if valid_filter in {"yes", "true", "1"}:
        stmt = stmt.where(ProxyInventoryModel.provider_valid.is_(True))
    if valid_filter in {"no", "false", "0"}:
        stmt = stmt.where(ProxyInventoryModel.provider_valid.is_(False))
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": ProxyInventoryModel.created_at,
            "updated_at": ProxyInventoryModel.updated_at,
            "last_healthcheck_at": ProxyInventoryModel.last_healthcheck_at,
            "proxy_status": ProxyInventoryModel.proxy_status,
            "country_code": ProxyInventoryModel.country_code,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    proxy_ids = [row.id for row in rows]
    account_binding_counts = _active_proxy_binding_counts(
        session=session,
        proxy_ids=proxy_ids,
        binding_model=UserAccountProxyBindingModel,
    )
    admin_binding_counts = _active_proxy_binding_counts(
        session=session,
        proxy_ids=proxy_ids,
        binding_model=TeamAdminProxyBindingModel,
    )
    items = [
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
            "active_account_binding_count": account_binding_counts.get(row.id, 0),
            "active_admin_binding_count": admin_binding_counts.get(row.id, 0),
            "active_binding_count": (
                account_binding_counts.get(row.id, 0) + admin_binding_counts.get(row.id, 0)
            ),
            "last_provider_verification_at": _iso(row.last_provider_verification_at),
            "last_healthcheck_at": _iso(row.last_healthcheck_at),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }
        for row in rows
    ]
    return page_payload(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


def _proxy_type_filter_values(value: str) -> list[str]:
    aliases = {"proxy_server": "proxyserver"}
    return [aliases.get(item, item) for item in _csv_values(value)]


def _proxy_status_filter_values(value: str) -> list[str]:
    aliases = {
        "allocated": "bound",
        "dead": "error",
    }
    return [aliases.get(item, item) for item in _csv_values(value)]


def _active_proxy_binding_counts(
    *,
    session: Session,
    proxy_ids: list[str],
    binding_model,
) -> dict[str, int]:
    if not proxy_ids:
        return {}
    rows = session.execute(
        select(binding_model.proxy_id, func.count())
        .where(
            binding_model.proxy_id.in_(proxy_ids),
            binding_model.bind_status == "active",
        )
        .group_by(binding_model.proxy_id)
    ).all()
    return {str(proxy_id): int(count) for proxy_id, count in rows}


@router.get("/mail-leases")
def list_mail_leases(
    session: DbSession,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-created_at",
    q: str = "",
    lease_status: str = "",
) -> dict:
    page, page_size = page_values(page, page_size)
    stmt = select(ExternalMailLeaseModel)
    if q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                ExternalMailLeaseModel.id.ilike(needle),
                ExternalMailLeaseModel.email.ilike(needle),
                ExternalMailLeaseModel.user_account_id.ilike(needle),
                ExternalMailLeaseModel.failure_code.ilike(needle),
                ExternalMailLeaseModel.failure_message.ilike(needle),
            )
        )
    if lease_status.strip():
        stmt = stmt.where(ExternalMailLeaseModel.lease_status.in_(_csv_values(lease_status)))
    stmt, normalized_sort = _sort_stmt(
        stmt,
        sort,
        {
            "created_at": ExternalMailLeaseModel.created_at,
            "updated_at": ExternalMailLeaseModel.updated_at,
            "allocated_at": ExternalMailLeaseModel.allocated_at,
            "lease_status": ExternalMailLeaseModel.lease_status,
        },
        default="-created_at",
    )
    total = total_for(session, stmt)
    rows = session.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = [
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
    return page_payload(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        sort=normalized_sort,
    )


def _user_account_dict(row: UserAccountModel, *, personal_plan_type: str = "") -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "phone_number": row.phone_number,
        "openai_user_id": row.openai_user_id,
        "account_status": row.account_status,
        "session_status": row.session_status,
        "personal_plan_type": str(personal_plan_type or ""),
        "codex_select_channel_required": row.codex_select_channel_required,
        "codex_select_channel_detected_at": _iso(row.codex_select_channel_detected_at),
        "has_password": bool(row.password),
        "password_status": row.password_status,
        "password_last_error_code": row.password_last_error_code,
        "password_last_error_message": row.password_last_error_message,
        "mfa_status": row.mfa_status,
        "has_twofauth_account": bool(row.twofauth_account_id),
        "mfa_last_error_code": row.mfa_last_error_code,
        "mfa_last_error_message": row.mfa_last_error_message,
        "security_setup_last_attempt_at": _iso(row.security_setup_last_attempt_at),
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


def _space_replenish_email_summary(*, session: Session) -> dict:
    source_counts = {
        str(status): int(count)
        for status, count in session.execute(
            select(SpaceReplenishEmailModel.source_type, func.count())
            .select_from(SpaceReplenishEmailModel)
            .group_by(SpaceReplenishEmailModel.source_type)
        ).all()
    }
    invite_status_counts = {
        str(status): int(count)
        for status, count in session.execute(
            select(SpaceReplenishEmailModel.invite_status, func.count())
            .select_from(SpaceReplenishEmailModel)
            .group_by(SpaceReplenishEmailModel.invite_status)
        ).all()
    }
    process_status_counts = {
        str(status): int(count)
        for status, count in session.execute(
            select(SpaceReplenishEmailModel.process_status, func.count())
            .select_from(SpaceReplenishEmailModel)
            .group_by(SpaceReplenishEmailModel.process_status)
        ).all()
    }
    available_count = int(
        session.scalar(
            select(func.count())
            .select_from(SpaceReplenishEmailModel)
            .where(
                SpaceReplenishEmailModel.source_type == "local_inventory",
                SpaceReplenishEmailModel.space_id.is_(None),
                SpaceReplenishEmailModel.invite_status == "available",
                ~exists(
                    select(SpaceMembershipModel.id)
                    .join(
                        UserAccountModel,
                        UserAccountModel.id == SpaceMembershipModel.user_account_id,
                    )
                    .where(
                        func.lower(UserAccountModel.email)
                        == SpaceReplenishEmailModel.email_key
                    )
                ),
            )
        )
        or 0
    )
    return {
        "total": sum(source_counts.values()),
        "available_count": available_count,
        "source_counts": source_counts,
        "invite_status_counts": invite_status_counts,
        "process_status_counts": process_status_counts,
    }


def _validate_payment_pool_status(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be one of {', '.join(sorted(allowed))}",
        )


def _persist_payment_pool_row(session: Session, row: Any, conflict_message: str) -> None:
    session.add(row)
    _commit_payment_pool_row(session, row, conflict_message)


def _commit_payment_pool_row(session: Session, row: Any, conflict_message: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=conflict_message) from exc


def _payment_name_pool_dict(row: PaymentNamePoolModel) -> dict:
    return {
        "id": row.id,
        "full_name": row.full_name,
        "name_status": row.name_status,
        "use_count": row.use_count,
        "last_used_at": _iso(row.last_used_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _payment_address_pool_dict(row: PaymentAddressPoolModel) -> dict:
    return {
        "id": row.id,
        "line1": row.line1,
        "line2": row.line2,
        "city": row.city,
        "state": row.state,
        "postal_code": row.postal_code,
        "country": row.country,
        "phone": row.phone,
        "address_status": row.address_status,
        "use_count": row.use_count,
        "last_used_at": _iso(row.last_used_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _payment_card_pool_dict(row: PaymentCardPoolModel) -> dict:
    return {
        "id": row.id,
        "card_fingerprint": row.card_fingerprint,
        "card_number_masked": f"**** **** **** {row.last4}",
        "last4": row.last4,
        "has_cvc": bool(row.cvc),
        "exp_month": row.exp_month,
        "exp_year": row.exp_year,
        "card_status": row.card_status,
        "reserved_by_space_id": row.reserved_by_space_id or "",
        "reserved_at": _iso(row.reserved_at),
        "use_count": row.use_count,
        "last_used_at": _iso(row.last_used_at),
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _space_dict(
    space: SpaceModel,
    *,
    session: Session | None = None,
    last_session_refresh_at: datetime | None = None,
) -> dict:
    if session is not None and last_session_refresh_at is None:
        last_session_refresh_at = _space_last_session_refresh_at(session=session, space=space)
    payment_method_attempt_count = int(space.payment_method_attempt_count or 0)
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
        "auto_replenish_enabled": space.auto_replenish_enabled,
        "has_promotion": bool(space.has_promotion),
        "promotion_id": str(space.promotion_id or ""),
        "has_payment_method": space.has_payment_method,
        "payment_method_status": space.payment_method_status,
        "payment_method_attempt_count": payment_method_attempt_count,
        "payment_method_id": space.payment_method_id,
        "payment_method_last4": space.payment_method_last4,
        "payment_method_last_attempt_at": _iso(space.payment_method_last_attempt_at),
        "payment_method_cooldown_until": _iso(space.payment_method_cooldown_until),
        "payment_method_cooldown_active": bool(
            payment_method_attempt_count >= PAYMENT_METHOD_MAX_ATTEMPTS
            and (
                space.payment_method_cooldown_until is None
                or space.payment_method_cooldown_until > datetime.now(UTC)
            )
        ),
        "payment_method_last_error_code": space.payment_method_last_error_code,
        "payment_method_last_error_message": space.payment_method_last_error_message,
        "space_status": space.space_status,
        "source_admin_session_id": space.source_admin_session_id,
        "last_session_refresh_at": _iso(last_session_refresh_at),
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
        "auth_mode": credential.auth_mode,
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
    user = (
        session.get(UserAccountModel, credential.user_account_id)
        if credential is not None
        else None
    )
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
    manual_export = not binding.downstream_channel_id and binding.downstream_external_id.startswith(
        "manual-export-"
    )
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
        "downstream_channel_name": (
            "文件导出" if manual_export else channel.name if channel is not None else ""
        ),
        "downstream_provider": (
            "manual_export"
            if manual_export
            else channel.provider_type
            if channel is not None
            else ""
        ),
        "distribution_mode": "manual_export" if manual_export else "channel_push",
        "export_batch_id": binding.downstream_external_id if manual_export else "",
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
        "latest_attempt_status": latest_attempt.attempt_status
        if latest_attempt is not None
        else "",
        "latest_attempt_payload_type": latest_attempt.payload_type
        if latest_attempt is not None
        else "",
        "latest_attempt_endpoint": latest_attempt.request_endpoint
        if latest_attempt is not None
        else "",
        "latest_attempt_error_code": latest_attempt.error_code
        if latest_attempt is not None
        else "",
        "latest_attempt_error_message": latest_attempt.error_message
        if latest_attempt is not None
        else "",
        "latest_attempt_started_at": _iso(latest_attempt.started_at)
        if latest_attempt is not None
        else "",
        "latest_attempt_finished_at": _iso(latest_attempt.finished_at)
        if latest_attempt is not None
        else "",
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


def _create_space_membership_growth_work_job(
    *,
    session: Session,
    space_id: str,
    work_count: int,
    session_wait_timeout_s: int,
    created_by: str,
) -> dict:
    normalized_space_id = space_id.strip()
    if not normalized_space_id:
        raise HTTPException(status_code=400, detail="membership growth requires one space_id")
    active_job = _active_work_job_for_type(
        session=session,
        job_type="space.membership_growth_round",
    )
    if active_job is not None:
        summary = _work_summary(session, active_job.id)
        return {
            "job_id": active_job.id,
            "job_status": active_job.job_status,
            "work_count": max(1, int((active_job.input_json or {}).get("work_count") or 1)),
            "selected_count": 1,
            **summary,
            "skipped_reason": "active_space_membership_growth_job_exists",
        }

    space = session.get(SpaceModel, normalized_space_id)
    if space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if space.space_type != "business":
        raise HTTPException(
            status_code=400,
            detail="membership growth only supports business space",
        )
    if space.space_status != "active":
        raise HTTPException(status_code=400, detail="membership growth requires active space")
    if not space.external_space_id:
        raise HTTPException(status_code=400, detail="space has no external space id")

    worker_count = max(1, min(int(work_count or 1), DEFAULT_SESSION_WORK_COUNT))
    wait_timeout = max(1, int(session_wait_timeout_s or DEFAULT_SESSION_WAIT_TIMEOUT_S))
    job = JobQueue(session).enqueue(
        job_type="space.membership_growth_round",
        input_json={
            "space_id": space.id,
            "work_count": worker_count,
            "session_wait_timeout_s": wait_timeout,
            "max_invite_count": MAX_GROWTH_INVITES,
            "target_member_count": TARGET_GROWTH_MEMBERS,
        },
        created_by=created_by,
    )
    WorkQueue(session).enqueue(
        job_id=job.id,
        work_type="space.membership_growth.invite_batch",
        execution_key=f"space-membership-growth-invite:{space.external_space_id}",
        input_json={
            "job_id": job.id,
            "space_id": space.id,
            "session_wait_timeout_s": wait_timeout,
        },
    )
    session.commit()
    return {
        "job_id": job.id,
        "job_status": job.job_status,
        "work_count": worker_count,
        "selected_count": 1,
        "queued": 1,
        "running": 0,
        "succeeded": 0,
        "skipped": 0,
        "failed": 0,
        "cancelled": 0,
        "space_id": space.id,
        "max_invite_count": MAX_GROWTH_INVITES,
        "target_member_count": TARGET_GROWTH_MEMBERS,
    }


def _create_space_seat_expand_work_job(
    *,
    session: Session,
    work_count: int,
    created_by: str,
    space_id: str = "",
) -> dict:
    active_job = _active_work_job_for_type(session=session, job_type="space.seat_expand")
    if active_job is not None:
        summary = _work_summary(session, active_job.id)
        return {
            "job_id": active_job.id,
            "job_status": active_job.job_status,
            "work_count": max(1, int((active_job.input_json or {}).get("work_count") or 1)),
            "selected_count": sum(summary.values()),
            **summary,
            "skipped_reason": "active_space_seat_expand_job_exists",
        }

    stmt = (
        select(SpaceModel)
        .where(
            SpaceModel.provider == "openai_chatgpt",
            SpaceModel.space_type == "business",
            SpaceModel.space_status == "active",
            SpaceModel.external_space_id != "",
        )
        .order_by(SpaceModel.updated_at.asc(), SpaceModel.id.asc())
    )
    if space_id.strip():
        stmt = stmt.where(SpaceModel.id == space_id.strip())
    selected = session.scalars(stmt).all()
    if not selected:
        return {
            "job_id": "",
            "job_status": "skipped",
            "work_count": 0,
            "selected_count": 0,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "failed": 0,
            "cancelled": 0,
            "skipped_reason": "no_active_business_space",
        }

    worker_count = max(1, int(work_count or 1))
    job = JobQueue(session).enqueue(
        job_type="space.seat_expand",
        input_json={
            "space_ids": [space.id for space in selected],
            "selected_count": len(selected),
            "work_count": worker_count,
            "target_seats": TARGET_SEATS,
            "min_seat_increase": MIN_SEAT_INCREASE,
            "max_seat_increase": MAX_SEAT_INCREASE,
            "request_delay_ms": REQUEST_DELAY_MS,
            "max_no_progress_count": MAX_NO_PROGRESS_COUNT,
            "max_http_failure_count": MAX_HTTP_FAILURE_COUNT,
        },
        created_by=created_by,
    )
    work_queue = WorkQueue(session)
    for space in selected:
        work_queue.enqueue(
            job_id=job.id,
            work_type="space.seat_expand.one",
            execution_key=f"space-seat-expand:{space.external_space_id}",
            input_json={
                "space_id": space.id,
                "external_space_id": space.external_space_id,
                "target_seats": TARGET_SEATS,
            },
        )
    session.commit()
    return {
        "job_id": job.id,
        "job_status": job.job_status,
        "work_count": worker_count,
        "selected_count": len(selected),
        "queued": len(selected),
        "running": 0,
        "succeeded": 0,
        "skipped": 0,
        "failed": 0,
        "cancelled": 0,
        "target_seats": TARGET_SEATS,
    }


def _create_space_authorization_work_job(
    *,
    session: Session,
    space_id: str,
    work_count: int,
    created_by: str,
    credential_name_prefix: str,
) -> dict:
    normalized_space_id = str(space_id or "").strip()
    if not normalized_space_id:
        raise HTTPException(status_code=400, detail="space_id is required")
    target_space = session.get(SpaceModel, normalized_space_id)
    if target_space is None:
        raise HTTPException(status_code=404, detail="space not found")
    if (
        target_space.provider != "openai_chatgpt"
        or target_space.space_type != "business"
        or target_space.space_status != "active"
        or target_space.credential_type not in {"team_5h_weekly", "team_monthly"}
    ):
        raise HTTPException(
            status_code=400,
            detail="space authorization requires an active OpenAI Business space",
        )
    active_job = None
    for job_type in ("automation.space_authorize", "space.business_access_token.create.bulk"):
        active_job = _active_work_job_for_type(
            session=session,
            job_type=job_type,
            space_id=target_space.id,
            external_space_id=target_space.external_space_id,
        )
        if active_job is not None:
            break
    if active_job is not None:
        summary = _work_summary(session, active_job.id)
        return {
            "job_id": active_job.id,
            "job_status": active_job.job_status,
            "run_id": "",
            "work_count": max(1, int((active_job.input_json or {}).get("work_count") or 1)),
            "selected_count": sum(summary.values()),
            "queued": summary["queued"],
            "running": summary["running"],
            "succeeded": summary["succeeded"],
            "failed": summary["failed"],
            "cancelled": summary["cancelled"],
            "skipped_reason": "active_authorize_job_exists",
            "selected": [],
        }
    worker_count = max(1, int(work_count or 1))
    selected = _select_pending_business_access_token_items(
        session=session,
        space_id=normalized_space_id,
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
    job = JobQueue(session).enqueue(
        job_type="automation.space_authorize",
        input_json={
            "space_id": normalized_space_id,
            "space_membership_ids": [item["space_membership_id"] for item in selected],
            "work_count": worker_count,
            "selected_count": len(selected),
            "credential_name_prefix": credential_name_prefix,
            "authorization_mode": "business_codex_oauth_with_web_access_token_fallback",
        },
        created_by=created_by,
    )
    work_queue = WorkQueue(session)
    for item in selected:
        work_queue.enqueue(
            job_id=job.id,
            work_type="space.business_codex.authorize.account",
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
        "work_count": worker_count,
        "selected_count": len(selected),
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


def _select_pending_business_access_token_items(
    *,
    session: Session,
    space_id: str,
) -> list[dict]:
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
            SpaceModel.id == space_id,
            SpaceModel.space_type == "business",
            SpaceModel.space_status == "active",
            SpaceModel.credential_type.in_(("team_5h_weekly", "team_monthly")),
            UserAccountModel.account_status == "active",
            UserAccountModel.session_status == "active",
            UserAccountModel.openai_user_id != "",
            or_(
                UserAccountModel.cookie_header != "",
                UserAccountModel.auth_cookie_header != "",
                UserAccountModel.session_token != "",
            ),
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
            execution_key=f"space:{req.external_space_id}",
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
        "work_count": worker_count,
        "selected_count": len(user_account_ids),
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
        session.scalars(
            select(SpaceCredentialModel.id).where(SpaceCredentialModel.id.in_(credential_ids))
        ).all()
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
    result = _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=max(1, int(worker_count or 5)),
        selected_count=len(credential_ids),
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
    return _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=worker_count,
        selected_count=len(user_account_ids),
    )


def _create_personal_codex_authorization_work_job(
    *,
    req: PersonalCodexAuthorizationJobRequest,
    session: Session,
) -> dict:
    hero_options = _validated_personal_codex_hero_options(req)
    membership_ids = list(
        dict.fromkeys(
            membership_id.strip()
            for membership_id in req.space_membership_ids
            if membership_id.strip()
        )
    )
    if not membership_ids:
        raise HTTPException(status_code=400, detail="space_membership_ids must not be empty")

    targets = []
    selection_skipped = []
    for membership_id in membership_ids:
        target, reason = resolve_personal_codex_authorization_target(
            session=session,
            space_membership_id=membership_id,
        )
        if target is None:
            selection_skipped.append({"space_membership_id": membership_id, "reason": reason})
            continue
        targets.append(target)

    worker_count = int(req.work_count)
    if not targets:
        return {
            "job_id": "",
            "job_status": "skipped",
            "run_id": "",
            "work_count": worker_count,
            "requested_count": len(membership_ids),
            "selected_count": 0,
            "selection_skipped_count": len(selection_skipped),
            "selection_skipped": selection_skipped,
            "queued": 0,
            "running": 0,
            "succeeded": 0,
            "skipped": 0,
            "failed": 0,
            "cancelled": 0,
        }

    job, run = _start_work_job(
        session=session,
        job_type="automation.space_authorize",
        input_json={
            "authorization_mode": "manual_personal_memberships",
            "space_membership_ids": [target.space_membership_id for target in targets],
            "work_count": worker_count,
            "requested_count": len(membership_ids),
            "selected_count": len(targets),
            "selection_skipped": selection_skipped,
            "force_clean_browser_login": req.force_clean_browser_login,
            **hero_options,
        },
        created_by=req.created_by.strip() or "ops:membership-personal-codex-authorize",
    )
    work_queue = WorkQueue(session)
    for target in targets:
        work_queue.enqueue(
            job_id=job.id,
            work_type="space.personal_codex.authorize.account",
            input_json={
                "space_membership_id": target.space_membership_id,
                "space_id": target.space_id,
                "user_account_id": target.user_account_id,
                "external_space_id": target.external_space_id,
                "force_clean_browser_login": req.force_clean_browser_login,
                **hero_options,
                "_run_id": run.id,
            },
        )
    session.commit()
    result = _work_job_summary_response(
        session=session,
        job_id=job.id,
        run_id=run.id,
        work_count=worker_count,
        selected_count=len(targets),
    )
    result.update(
        {
            "requested_count": len(membership_ids),
            "selection_skipped_count": len(selection_skipped),
            "selection_skipped": selection_skipped,
        }
    )
    return result


def _validated_personal_codex_hero_options(
    req: PersonalCodexAuthorizationJobRequest,
) -> dict[str, object]:
    if not req.use_hero_sms_for_add_phone:
        return {"use_hero_sms_for_add_phone": False}

    country = str(req.hero_sms_country or "").strip()
    if not country or not country.isdigit():
        raise HTTPException(
            status_code=400,
            detail="hero_sms_country must be a numeric Hero country id",
        )
    raw_max_price = str(req.hero_sms_max_price or "").strip()
    try:
        max_price = Decimal(raw_max_price)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=400,
            detail="hero_sms_max_price must be a positive number",
        ) from exc
    if not max_price.is_finite() or max_price <= 0:
        raise HTTPException(
            status_code=400,
            detail="hero_sms_max_price must be a positive number",
        )
    return {
        "use_hero_sms_for_add_phone": True,
        "hero_sms_country": country,
        "hero_sms_max_price": raw_max_price,
    }


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
            selected.append(
                {
                    "space_credential_id": credential_id,
                    "credential_type": credential_type,
                    "is_retry": True,
                }
            )
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
            selected.append(
                {
                    "space_credential_id": credential_id,
                    "credential_type": credential_type,
                    "is_retry": False,
                }
            )
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
        .join(
            SpacePushBindingModel,
            SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
        )
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
        .outerjoin(
            SpacePushBindingModel,
            SpacePushBindingModel.space_credential_id == SpaceCredentialModel.id,
        )
        .where(
            SpaceCredentialModel.credential_status == "active",
            SpaceCredentialModel.access_token != "",
            SpaceModel.space_status == "active",
            SpaceModel.credential_type == credential_type,
            or_(
                SpacePushBindingModel.space_credential_id.is_(None),
                SpacePushBindingModel.push_status.in_(("none", "skipped")),
            ),
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
        .join(
            SpaceCredentialModel,
            SpaceCredentialModel.id == SpacePushBindingModel.space_credential_id,
        )
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


def _select_personal_payment_method_bind_spaces(
    *,
    session: Session,
    space_ids: Sequence[str],
) -> tuple[list[str], list[SpaceModel], list[dict[str, str]]]:
    requested_space_ids = list(
        dict.fromkeys(
            space_id
            for space_id in (str(item or "").strip() for item in space_ids)
            if space_id
        )
    )
    if not requested_space_ids:
        raise HTTPException(status_code=400, detail="space_ids must not be empty")

    spaces_by_id = {
        space.id: space
        for space in session.scalars(
            select(SpaceModel).where(SpaceModel.id.in_(requested_space_ids))
        ).all()
    }
    owner_account_ids = {
        space.owner_user_account_id
        for space in spaces_by_id.values()
        if space.owner_user_account_id
    }
    account_status_by_id = dict(
        session.execute(
            select(UserAccountModel.id, UserAccountModel.account_status).where(
                UserAccountModel.id.in_(owner_account_ids)
            )
        ).all()
    )
    active_jobs_by_space_id = _active_personal_payment_method_bind_jobs_by_space_id(
        session=session,
    )
    now = datetime.now(UTC)
    selected: list[SpaceModel] = []
    selection_skipped: list[dict[str, str]] = []

    for space_id in requested_space_ids:
        space = spaces_by_id.get(space_id)
        reason = ""
        if space is None:
            reason = "space_not_found"
        elif space.provider != "openai_chatgpt":
            reason = "payment_method_provider_not_supported"
        elif space.space_type != "personal":
            reason = "payment_method_personal_space_required"
        elif space.space_status != "active":
            reason = "payment_method_space_not_active"
        elif not space.has_promotion or not str(space.promotion_id or "").strip():
            reason = "payment_method_promotion_required"
        elif space.has_payment_method or space.payment_method_status == "bound":
            reason = "payment_method_already_bound"
        elif (
            space.payment_method_attempt_count >= PAYMENT_METHOD_MAX_ATTEMPTS
            and (
                space.payment_method_cooldown_until is None
                or space.payment_method_cooldown_until > now
            )
        ):
            reason = "payment_method_cooldown_active"
        elif (
            not space.owner_user_account_id
            or space.owner_user_account_id not in account_status_by_id
        ):
            reason = "payment_method_owner_account_missing"
        elif account_status_by_id[space.owner_user_account_id] != "active":
            reason = "payment_method_owner_account_not_active"
        elif space.id in active_jobs_by_space_id:
            reason = "active_personal_payment_method_bind_job_exists"

        if reason:
            selection_skipped.append({"space_id": space_id, "reason": reason})
        elif space is not None:
            selected.append(space)

    return requested_space_ids, selected, selection_skipped


def _active_personal_payment_method_bind_jobs_by_space_id(
    *,
    session: Session,
) -> dict[str, JobModel]:
    active_jobs = session.scalars(
        select(JobModel).where(
            JobModel.type == "space.personal_payment_method_bind.tick",
            JobModel.job_status.in_(("queued", "running")),
        )
    ).all()
    jobs_by_id = {job.id: job for job in active_jobs}
    result: dict[str, JobModel] = {}
    if not jobs_by_id:
        return result
    works = session.scalars(
        select(WorkItemModel).where(
            WorkItemModel.job_id.in_(jobs_by_id),
            WorkItemModel.work_type == "space.personal_payment_method_bind.space",
        )
    ).all()
    job_ids_with_works = {work.job_id for work in works}
    for work in works:
        if work.work_status not in ("queued", "running"):
            continue
        space_id = str((work.input_json or {}).get("space_id") or "").strip()
        job = jobs_by_id.get(work.job_id)
        if space_id and job is not None:
            result.setdefault(space_id, job)

    # A queued job, or a running job that has not created Work rows yet, is
    # still preparing its declared scope. Once Work exists, its status is the
    # precise source of truth and completed rows no longer block a retry.
    for job in active_jobs:
        if job.job_status != "queued" and job.id in job_ids_with_works:
            continue
        input_json = job.input_json or {}
        scoped_space_ids = [str(input_json.get("space_id") or "").strip()]
        raw_space_ids = input_json.get("space_ids")
        if isinstance(raw_space_ids, list):
            scoped_space_ids.extend(str(item or "").strip() for item in raw_space_ids)
        for space_id in scoped_space_ids:
            if space_id:
                result.setdefault(space_id, job)
    return result


def _select_personal_promotion_check_spaces(
    *,
    session: Session,
    space_ids: Sequence[str],
) -> tuple[list[str], list[SpaceModel], list[dict[str, str]]]:
    requested_space_ids = list(
        dict.fromkeys(
            space_id
            for space_id in (str(item or "").strip() for item in space_ids)
            if space_id
        )
    )
    if not requested_space_ids:
        raise HTTPException(status_code=400, detail="space_ids must not be empty")

    spaces_by_id = {
        space.id: space
        for space in session.scalars(
            select(SpaceModel).where(SpaceModel.id.in_(requested_space_ids))
        ).all()
    }
    owner_account_ids = {
        space.owner_user_account_id
        for space in spaces_by_id.values()
        if space.owner_user_account_id
    }
    account_status_by_id = dict(
        session.execute(
            select(UserAccountModel.id, UserAccountModel.account_status).where(
                UserAccountModel.id.in_(owner_account_ids)
            )
        ).all()
    )
    active_jobs_by_space_id = _active_personal_promotion_check_jobs_by_space_id(
        session=session,
    )
    selected: list[SpaceModel] = []
    selection_skipped: list[dict[str, str]] = []

    for space_id in requested_space_ids:
        space = spaces_by_id.get(space_id)
        reason = ""
        if space is None:
            reason = "space_not_found"
        elif space.provider != "openai_chatgpt":
            reason = "promotion_check_provider_not_supported"
        elif space.space_type != "personal":
            reason = "promotion_check_personal_space_required"
        elif space.space_status != "active":
            reason = "promotion_check_space_not_active"
        elif (
            not space.owner_user_account_id
            or space.owner_user_account_id not in account_status_by_id
        ):
            reason = "promotion_check_owner_account_missing"
        elif account_status_by_id[space.owner_user_account_id] != "active":
            reason = "promotion_check_owner_account_not_active"
        elif space.id in active_jobs_by_space_id:
            reason = "active_personal_promotion_check_job_exists"

        if reason:
            selection_skipped.append({"space_id": space_id, "reason": reason})
        elif space is not None:
            selected.append(space)

    return requested_space_ids, selected, selection_skipped


def _active_personal_promotion_check_jobs_by_space_id(
    *,
    session: Session,
) -> dict[str, JobModel]:
    active_jobs = session.scalars(
        select(JobModel).where(
            JobModel.type == "space.personal_promotion_check.selected",
            JobModel.job_status.in_(("queued", "running")),
        )
    ).all()
    jobs_by_id = {job.id: job for job in active_jobs}
    if not jobs_by_id:
        return {}

    works = session.scalars(
        select(WorkItemModel).where(
            WorkItemModel.job_id.in_(jobs_by_id),
            WorkItemModel.work_type == "space.personal_promotion_check.space",
        )
    ).all()
    result: dict[str, JobModel] = {}
    job_ids_with_works = {work.job_id for work in works}
    for work in works:
        if work.work_status not in ("queued", "running"):
            continue
        space_id = str((work.input_json or {}).get("space_id") or "").strip()
        job = jobs_by_id.get(work.job_id)
        if space_id and job is not None:
            result.setdefault(space_id, job)

    for job in active_jobs:
        if job.job_status != "queued" and job.id in job_ids_with_works:
            continue
        raw_space_ids = (job.input_json or {}).get("space_ids")
        if not isinstance(raw_space_ids, list):
            continue
        for space_id in (str(item or "").strip() for item in raw_space_ids):
            if space_id:
                result.setdefault(space_id, job)
    return result


def _active_work_job_for_type(
    *,
    session: Session,
    job_type: str,
    space_id: str = "",
    external_space_id: str = "",
) -> JobModel | None:
    stmt = select(JobModel).where(
        JobModel.type == job_type,
        JobModel.job_status.in_(("queued", "running")),
    )
    scope_filters = []
    if space_id:
        scope_filters.append(JobModel.input_json["space_id"].astext == space_id)
    if external_space_id:
        scope_filters.append(
            JobModel.input_json["external_space_id"].astext == external_space_id
        )
    if scope_filters:
        stmt = stmt.where(or_(*scope_filters))
    jobs = session.scalars(stmt.order_by(JobModel.created_at.asc()).limit(10)).all()
    for job in jobs:
        _finalize_work_job_if_complete(session=session, job=job)
        if job.job_status == "queued":
            return job
        if job.job_status == "running":
            summary = _work_summary(session, job.id)
            if summary["queued"] > 0 or summary["running"] > 0:
                return job
    return None


_SESSION_OTP_JOB_TYPES = (
    "account.session_otp.prepare.bulk",
    "account.session_otp.submit.bulk",
    "account.session_otp.remote_submit.bulk",
)


def _normalize_session_otp_space_ids(space_ids: Sequence[str]) -> list[str]:
    normalized = list(
        dict.fromkeys(
            item
            for item in (str(candidate or "").strip() for candidate in space_ids)
            if item
        )
    )
    if not normalized:
        raise HTTPException(status_code=400, detail="space_ids is required")
    return normalized


def _session_otp_http_exception(
    *,
    session: Session,
    space_ids: Sequence[str],
    exc: Exception,
) -> HTTPException:
    found_space_ids = set(
        session.scalars(select(SpaceModel.id).where(SpaceModel.id.in_(space_ids))).all()
    )
    missing_space_ids = [item for item in space_ids if item not in found_space_ids]
    if missing_space_ids:
        return HTTPException(
            status_code=404,
            detail={"message": str(exc), "space_ids": missing_space_ids},
        )
    return HTTPException(status_code=400, detail=str(exc))


def _space_session_otp_active_job_dict(
    *,
    session: Session,
    space_id: str = "",
    space_ids: Sequence[str] = (),
    user_account_ids: Sequence[str] = (),
) -> dict:
    normalized_space_ids = set(
        _normalize_session_otp_space_ids([*space_ids, space_id])
    )
    normalized_user_account_ids = {
        item
        for item in (str(candidate or "").strip() for candidate in user_account_ids)
        if item
    }
    jobs = session.scalars(
        select(JobModel)
        .where(
            JobModel.type.in_(_SESSION_OTP_JOB_TYPES),
            JobModel.job_status.in_(("queued", "running")),
        )
        .order_by(JobModel.created_at.asc())
    ).all()
    finalized = False
    for job in jobs:
        previous_status = job.job_status
        _finalize_work_job_if_complete(session=session, job=job)
        finalized = finalized or job.job_status != previous_status
        if job.job_status not in ("queued", "running"):
            continue
        input_json = dict(job.input_json or {})
        job_space_ids = {
            item
            for item in (
                str(candidate or "").strip()
                for candidate in (
                    input_json.get("space_ids")
                    if isinstance(input_json.get("space_ids"), list)
                    else [input_json.get("space_id")]
                )
            )
            if item
        }
        job_user_account_ids = {
            item
            for item in (
                str(candidate or "").strip()
                for candidate in (
                    input_json.get("user_account_ids")
                    if isinstance(input_json.get("user_account_ids"), list)
                    else []
                )
            )
            if item
        }
        if normalized_user_account_ids and not job_user_account_ids:
            job_user_account_ids = {
                item
                for item in session.scalars(
                    select(WorkItemModel.input_json["user_account_id"].astext).where(
                        WorkItemModel.job_id == job.id
                    )
                ).all()
                if item
            }
        conflicts = (
            bool(normalized_user_account_ids & job_user_account_ids)
            if normalized_user_account_ids and job_user_account_ids
            else bool(normalized_space_ids & job_space_ids)
        )
        if not conflicts:
            continue
        if finalized:
            session.commit()
        summary = _work_summary(session, job.id)
        return {
            "job_id": job.id,
            "job_type": job.type,
            "job_status": job.job_status,
            **summary,
        }
    if finalized:
        session.commit()
    return {}


def _reject_active_space_session_otp_job(
    *,
    session: Session,
    space_id: str = "",
    space_ids: Sequence[str] = (),
    user_account_ids: Sequence[str] = (),
) -> None:
    active_job = _space_session_otp_active_job_dict(
        session=session,
        space_id=space_id,
        space_ids=space_ids,
        user_account_ids=user_account_ids,
    )
    if active_job:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "selected accounts already have an active staged OTP job"
                    if user_account_ids
                    else "space already has an active staged OTP job"
                ),
                **active_job,
            },
        )


def _reject_active_session_otp_job(
    *,
    session: Session,
    space_ids: Sequence[str],
    user_account_ids: Sequence[str],
) -> None:
    _reject_active_space_session_otp_job(
        session=session,
        space_ids=space_ids,
        user_account_ids=user_account_ids,
    )


def _work_job_summary_response(
    *,
    session: Session,
    job_id: str,
    run_id: str,
    work_count: int,
    selected_count: int,
) -> dict:
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
        "selected_count": selected_count,
        **summary,
    }


def _work_summary(session: Session, job_id: str) -> dict[str, int]:
    summary = {
        "queued": 0,
        "running": 0,
        "succeeded": 0,
        "skipped": 0,
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
    job_cancelled = job is not None and job.job_status == "cancelled"
    if job is not None and not job_cancelled:
        if summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] == 0:
            job.job_status = "succeeded"
        elif summary["queued"] == 0 and summary["running"] == 0 and summary["failed"] > 0:
            job.job_status = "failed"
        else:
            job.job_status = "running"
        job.updated_at = now
    if run is not None:
        if job_cancelled:
            run.run_status = "cancelled"
            run.finished_at = now
            run.output_json = summary
            run.error_code = "cancelled_by_operator"
            run.error_message = "job cancelled by operator"
            return
        if summary["queued"] == 0 and summary["running"] == 0:
            run.run_status = (
                "succeeded" if job is not None and job.job_status == "succeeded" else "failed"
            )
            run.finished_at = now
        else:
            run.run_status = "running"
            run.finished_at = None
        run.output_json = summary
        if run.run_status == "failed":
            run.error_code = "work_failed"
            run.error_message = (
                f"failed={summary['failed']} queued={summary['queued']} "
                f"running={summary['running']}"
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
        session.scalars(
            select(UserAccountModel.id).where(UserAccountModel.id.in_(user_account_ids))
        ).all()
    )
    missing_ids = [item for item in user_account_ids if item not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail={"user_account_ids": missing_ids})
    return user_account_ids


def _downstream_channel_dict(
    channel: DownstreamChannelModel, *, session: Session | None = None
) -> dict:
    balances: list[dict] = []
    if session is not None:
        _ensure_downstream_credential_type_balances(session=session, channel=channel)
        balances = [
            _credential_type_balance_dict(row, session=session)
            for row in session.scalars(
                select(DownstreamChannelCredentialTypeBalanceModel)
                .where(
                    DownstreamChannelCredentialTypeBalanceModel.downstream_channel_id == channel.id
                )
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
    defaults = _space_schedule_defaults()
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
                next_run_at=None,
                created_by="system:space-default",
                created_at=now,
                updated_at=now,
            )
        )


def _space_schedule_defaults() -> dict[str, dict[str, Any]]:
    return {
        "automation.space_membership_invite_sync": {
            "interval_seconds": 60,
            "config_json": {
                "space_id": "",
                "space_limit": 1,
                "invite_limit_per_space": SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
                "work_count": SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
                "barrier_timeout_s": SPACE_MEMBERSHIP_INVITE_BARRIER_TIMEOUT_S,
            },
        },
        "automation.space_membership_invite_dynamic": {
            "interval_seconds": 60,
            "config_json": {"space_id": ""},
        },
        "automation.space_membership_growth_round": {
            "interval_seconds": 60,
            "config_json": {
                "space_id": "",
                "work_count": DEFAULT_SESSION_WORK_COUNT,
                "session_wait_timeout_s": DEFAULT_SESSION_WAIT_TIMEOUT_S,
            },
        },
        "automation.space_authorize": {
            "interval_seconds": 60,
            "config_json": {
                "space_id": "",
                "work_count": 1,
                "credential_name_prefix": "codex",
            },
        },
        "automation.space_downstream_push": {
            "interval_seconds": 60,
            "config_json": {"work_count": 5, "downstream_channel_id": ""},
        },
        "automation.space_recycle_sweep": {
            "interval_seconds": 300,
            "config_json": {"limit": 100, "work_count": 5},
        },
        "automation.space_seat_expand": {
            "interval_seconds": 300,
            "config_json": {"space_id": "", "work_count": 1},
        },
        "automation.space_auto_replenish": {
            "interval_seconds": 120,
            "config_json": {"space_id": "", "work_count": 20},
        },
        "automation.personal_payment_method_bind": {
            "interval_seconds": 60,
            "config_json": {"space_id": "", "limit": 10, "work_count": 1},
        },
    }


def _effective_space_schedule_config(
    *,
    schedule_type: str,
    saved_config: dict[str, Any] | None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_space_schedule_type(schedule_type)
    defaults = dict(_space_schedule_defaults()[schedule_type]["config_json"])
    saved = _validated_space_schedule_config_values(schedule_type, saved_config or {})
    override_values = _validated_space_schedule_config_values(schedule_type, overrides or {})
    return _validated_space_schedule_config_values(
        schedule_type,
        {**defaults, **saved, **override_values},
    )


def _validated_space_schedule_config_values(
    schedule_type: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    schemas: dict[str, dict[str, tuple[str, float | None, float | None]]] = {
        "automation.space_membership_invite_sync": {
            "space_id": ("str", None, None),
            "space_limit": ("int", 1, 1),
            "invite_limit_per_space": (
                "int",
                SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
                SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
            ),
            "work_count": (
                "int",
                SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
                SPACE_MEMBERSHIP_INVITE_WORK_COUNT,
            ),
            "barrier_timeout_s": ("float", 1, None),
        },
        "automation.space_membership_invite_dynamic": {
            "space_id": ("str", None, None),
        },
        "automation.space_membership_growth_round": {
            "space_id": ("str", None, None),
            "work_count": ("int", 1, DEFAULT_SESSION_WORK_COUNT),
            "session_wait_timeout_s": ("int", 1, None),
        },
        "automation.space_authorize": {
            "space_id": ("str", None, None),
            "work_count": ("int", 1, 350),
            "credential_name_prefix": ("str", None, None),
        },
        "automation.space_downstream_push": {
            "work_count": ("int", 1, 350),
            "downstream_channel_id": ("str", None, None),
        },
        "automation.space_recycle_sweep": {
            "limit": ("int", 1, None),
            "work_count": ("int", 1, 350),
        },
        "automation.space_seat_expand": {
            "space_id": ("str", None, None),
            "work_count": ("int", 1, 350),
        },
        "automation.space_auto_replenish": {
            "space_id": ("str", None, None),
            "work_count": ("int", 1, 350),
        },
        "automation.personal_payment_method_bind": {
            "space_id": ("str", None, None),
            "limit": ("int", 1, 100),
            "work_count": ("int", 1, 10),
        },
    }
    schema = schemas[schedule_type]
    unknown = sorted(set(values) - set(schema))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={"unsupported_config_fields": unknown, "schedule_type": schedule_type},
        )
    normalized: dict[str, Any] = {}
    for key, value in values.items():
        value_type, minimum, maximum = schema[key]
        if value_type == "str":
            parsed: Any = str(value or "").strip()
            if key == "credential_name_prefix" and not parsed:
                raise HTTPException(status_code=400, detail=f"{key} is required")
        else:
            if isinstance(value, bool):
                raise HTTPException(status_code=400, detail=f"{key} must be a number")
            try:
                parsed = float(value) if value_type == "float" else int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"{key} must be a number") from exc
            if value_type == "int" and isinstance(value, float) and not value.is_integer():
                raise HTTPException(status_code=400, detail=f"{key} must be an integer")
            if minimum is not None and parsed < minimum:
                raise HTTPException(status_code=400, detail=f"{key} must be >= {minimum:g}")
            if maximum is not None and parsed > maximum:
                raise HTTPException(status_code=400, detail=f"{key} must be <= {maximum:g}")
        normalized[key] = parsed
    return normalized


def _automation_monitor_job_dict(*, session: Session, schedule: AutomationScheduleModel) -> dict:
    job_type = _job_type_for_schedule_type(schedule.schedule_type)
    latest_job = session.scalars(
        select(JobModel)
        .where(JobModel.type == job_type)
        .order_by(JobModel.created_at.desc())
        .limit(1)
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
    output = (
        latest_run.output_json
        if latest_run is not None and isinstance(latest_run.output_json, dict)
        else {}
    )
    duration_ms = 0
    if latest_run is not None and latest_run.started_at and latest_run.finished_at:
        duration_ms = int((latest_run.finished_at - latest_run.started_at).total_seconds() * 1000)
    if latest_job is not None and schedule.last_job_id == latest_job.id:
        latest_status = latest_run.run_status if latest_run is not None else latest_job.job_status
        if schedule.last_run_status != latest_status:
            schedule.last_run_status = latest_status
            schedule.updated_at = datetime.now(UTC)
        if (
            latest_run is not None
            and latest_run.started_at
            and schedule.last_run_at != latest_run.started_at
        ):
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


def _execute_space_automation_schedule(
    *,
    session: Session,
    schedule: AutomationScheduleModel,
    config_json: dict[str, Any] | None = None,
    advance_next_run: bool = True,
    created_by: str = "",
) -> dict:
    _validate_space_schedule_type(schedule.schedule_type)
    effective_config = _effective_space_schedule_config(
        schedule_type=schedule.schedule_type,
        saved_config=config_json if config_json is not None else schedule.config_json,
    )
    now = datetime.now(UTC)
    schedule.last_run_at = now
    if advance_next_run:
        schedule.next_run_at = now + timedelta(seconds=max(5, int(schedule.interval_seconds or 60)))
    schedule.last_error_code = ""
    schedule.last_error_message = ""
    schedule.updated_at = now
    actor = created_by.strip() or f"scheduler:{schedule.id}"
    try:
        if schedule.schedule_type == "automation.space_membership_invite_sync":
            job = JobQueue(session).enqueue(
                job_type="space.membership_invite_sync",
                input_json={
                    "space_id": str(effective_config["space_id"]),
                    "space_limit": int(effective_config["space_limit"]),
                    "invite_limit_per_space": int(effective_config["invite_limit_per_space"]),
                    "work_count": int(effective_config["work_count"]),
                    "barrier_timeout_s": float(effective_config["barrier_timeout_s"]),
                },
                created_by=actor,
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status}
        if schedule.schedule_type == "automation.space_membership_invite_dynamic":
            active_job = _active_work_job_for_type(
                session=session,
                job_type="space.membership_invite_dynamic",
            )
            if active_job is not None:
                summary = _work_summary(session, active_job.id)
                schedule.last_job_id = active_job.id
                schedule.last_run_status = active_job.job_status
                return {
                    "job_id": active_job.id,
                    "job_status": active_job.job_status,
                    "work_count": 1,
                    **summary,
                    "skipped_reason": "active_dynamic_invite_job_exists",
                }
            job = JobQueue(session).enqueue(
                job_type="space.membership_invite_dynamic",
                input_json={
                    "space_id": str(effective_config["space_id"]),
                    "work_count": 1,
                },
                created_by=actor,
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status, "work_count": 1}
        if schedule.schedule_type == "automation.space_membership_growth_round":
            result = _create_space_membership_growth_work_job(
                session=session,
                space_id=str(effective_config["space_id"]),
                work_count=int(effective_config["work_count"]),
                session_wait_timeout_s=int(effective_config["session_wait_timeout_s"]),
                created_by=actor,
            )
            schedule.last_job_id = str(result.get("job_id") or "")
            schedule.last_run_status = str(result.get("job_status") or "skipped")
            return result
        if schedule.schedule_type == "automation.space_authorize":
            result = _create_space_authorization_work_job(
                session=session,
                space_id=str(effective_config["space_id"]),
                work_count=int(effective_config["work_count"]),
                created_by=actor,
                credential_name_prefix=str(effective_config["credential_name_prefix"]),
            )
            schedule.last_job_id = str(result.get("job_id") or "")
            schedule.last_run_status = str(result.get("job_status") or "queued")
            return result
        if schedule.schedule_type == "automation.space_recycle_sweep":
            job = JobQueue(session).enqueue(
                job_type="space.recycle.sweep",
                input_json={
                    "limit": int(effective_config["limit"]),
                    "work_count": int(effective_config["work_count"]),
                },
                created_by=actor,
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status}
        if schedule.schedule_type == "automation.space_seat_expand":
            result = _create_space_seat_expand_work_job(
                session=session,
                work_count=int(effective_config["work_count"]),
                created_by=actor,
                space_id=str(effective_config["space_id"]),
            )
            schedule.last_job_id = str(result.get("job_id") or "")
            schedule.last_run_status = str(result.get("job_status") or "skipped")
            return result
        if schedule.schedule_type == "automation.space_auto_replenish":
            active_job = _active_work_job_for_type(
                session=session,
                job_type="space.auto_replenish.tick",
            )
            if active_job is not None:
                summary = _work_summary(session, active_job.id)
                schedule.last_job_id = active_job.id
                schedule.last_run_status = active_job.job_status
                return {
                    "job_id": active_job.id,
                    "job_status": active_job.job_status,
                    **summary,
                    "skipped_reason": "active_auto_replenish_job_exists",
                }
            job = JobQueue(session).enqueue(
                job_type="space.auto_replenish.tick",
                input_json={
                    "space_id": str(effective_config["space_id"]),
                    "work_count": int(effective_config["work_count"]),
                },
                created_by=actor,
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status}
        if schedule.schedule_type == "automation.personal_payment_method_bind":
            active_job = _active_work_job_for_type(
                session=session,
                job_type="space.personal_payment_method_bind.tick",
            )
            if active_job is not None:
                summary = _work_summary(session, active_job.id)
                schedule.last_job_id = active_job.id
                schedule.last_run_status = active_job.job_status
                return {
                    "job_id": active_job.id,
                    "job_status": active_job.job_status,
                    **summary,
                    "skipped_reason": "active_personal_payment_method_bind_job_exists",
                }
            job = JobQueue(session).enqueue(
                job_type="space.personal_payment_method_bind.tick",
                input_json={
                    "space_id": str(effective_config["space_id"]),
                    "limit": int(effective_config["limit"]),
                    "work_count": int(effective_config["work_count"]),
                },
                created_by=actor,
            )
            schedule.last_job_id = job.id
            schedule.last_run_status = "queued"
            return {"job_id": job.id, "job_status": job.job_status}
        downstream_channel_id = str(effective_config["downstream_channel_id"])
        channels_stmt = select(DownstreamChannelModel).where(
            DownstreamChannelModel.enabled.is_(True)
        )
        if downstream_channel_id:
            channels_stmt = channels_stmt.where(DownstreamChannelModel.id == downstream_channel_id)
        results = []
        for channel in session.scalars(channels_stmt).all():
            result = _create_pending_space_push_work_job(
                req=PushPendingSpaceCredentialsRequest(
                    downstream_channel_id=channel.id,
                    created_by=actor,
                    work_count=int(effective_config["work_count"]),
                ),
                session=session,
            )
            results.append(result)
        schedule.last_job_id = ",".join(
            str(item.get("job_id") or "") for item in results if item.get("job_id")
        )
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
            or_(
                AutomationScheduleModel.next_run_at.is_(None),
                AutomationScheduleModel.next_run_at <= now,
            ),
        )
        .order_by(AutomationScheduleModel.next_run_at.asc().nullsfirst())
        .limit(10)
    ).all()
    for schedule in schedules:
        schedule.locked_by = scheduler_id
        schedule.locked_until = now + timedelta(
            seconds=max(30, int(schedule.interval_seconds or 60))
        )
        _execute_space_automation_schedule(session=session, schedule=schedule)


def _validate_space_schedule_type(schedule_type: str) -> None:
    if schedule_type not in SPACE_AUTOMATION_TYPES:
        raise HTTPException(
            status_code=400, detail=f"unsupported Space automation schedule type: {schedule_type}"
        )


def _fixed_automation_schedule_id(schedule_type: str) -> str:
    _validate_space_schedule_type(schedule_type)
    return {
        "automation.space_recycle_sweep": "automation-schedule-space-recycle-sweep",
        "automation.space_downstream_push": "automation-schedule-space-downstream-push",
        "automation.space_membership_invite_sync": (
            "automation-schedule-space-membership-invite-sync"
        ),
        "automation.space_membership_invite_dynamic": (
            "automation-schedule-space-membership-invite-dynamic"
        ),
        "automation.space_membership_growth_round": (
            "automation-schedule-space-membership-growth-round"
        ),
        "automation.space_authorize": "automation-schedule-space-authorize",
        "automation.space_seat_expand": "automation-schedule-space-seat-expand",
        "automation.space_auto_replenish": "automation-schedule-space-auto-replenish",
        "automation.personal_payment_method_bind": (
            "automation-schedule-personal-payment-method-bind"
        ),
    }[schedule_type]


def _job_type_for_schedule_type(schedule_type: str) -> str:
    _validate_space_schedule_type(schedule_type)
    return {
        "automation.space_recycle_sweep": "space.recycle.sweep",
        "automation.space_downstream_push": "space_credential.push.bulk",
        "automation.space_membership_invite_sync": "space.membership_invite_sync",
        "automation.space_membership_invite_dynamic": "space.membership_invite_dynamic",
        "automation.space_membership_growth_round": "space.membership_growth_round",
        "automation.space_authorize": "automation.space_authorize",
        "automation.space_seat_expand": "space.seat_expand",
        "automation.space_auto_replenish": "space.auto_replenish.tick",
        "automation.personal_payment_method_bind": "space.personal_payment_method_bind.tick",
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


def _space_export_response(result) -> Response:
    headers = {
        "Content-Disposition": f'attachment; filename="{result.filename}"',
        "Cache-Control": "no-store",
        "X-Export-Count": str(result.exported_count),
    }
    if result.export_batch_id:
        headers["X-Export-Batch-Id"] = result.export_batch_id
    return Response(
        content=result.content,
        media_type="text/plain",
        headers=headers,
    )


def _csv_values(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _apply_plan_type_filter(stmt, *, column, value: str):
    values = _csv_values(value)
    if not values:
        return stmt
    include_unknown = "unknown" in values
    known_values = [item for item in values if item != "unknown"]
    predicates = []
    if known_values:
        predicates.append(column.in_(known_values))
    if include_unknown:
        predicates.append(or_(column.is_(None), column == ""))
    return stmt.where(or_(*predicates))


def _apply_session_recency_filter(stmt, *, column, value: str):
    normalized = value.strip()
    if not normalized:
        return stmt
    if normalized == "never":
        return stmt.where(column.is_(None))
    hours = SESSION_RECENCY_HOURS.get(normalized)
    if hours is None:
        raise HTTPException(status_code=400, detail="unsupported session_recency")
    return stmt.where(column >= datetime.now(UTC) - timedelta(hours=hours))


def _space_last_session_refresh_at(*, session: Session, space: SpaceModel) -> datetime | None:
    if space.space_type == "personal":
        account = session.get(UserAccountModel, space.owner_user_account_id)
        return account.last_session_refresh_at if account is not None else None
    admin_session = session.get(TeamAdminSessionModel, space.source_admin_session_id)
    return admin_session.imported_at if admin_session is not None else None


def _sort_stmt(stmt, sort: str, columns: dict[str, Any], *, default: str):
    requested = (sort or default).strip()
    descending = requested.startswith("-")
    key = requested[1:] if descending else requested
    if key not in columns:
        requested = default
        descending = requested.startswith("-")
        key = requested[1:] if descending else requested
    column = columns[key]
    return stmt.order_by(column.desc() if descending else column.asc()), requested


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
