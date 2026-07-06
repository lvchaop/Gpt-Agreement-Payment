from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.application.workflows.space_usage import (
    infer_credential_type,
    parse_wham_usage_windows,
    usage_status_from_percent,
)
from refactor_app.infrastructure.db.models import (
    SpaceCredentialUsageStateModel,
    SpaceMembershipModel,
    SpaceUsageCheckModel,
)
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import OpenAIChatGPTProvider


class SpaceAuthorizationWorkflowError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreateBusinessAccessTokenCredentialInput:
    user_account_id: str
    external_space_id: str
    session_access_token: str
    credential_name: str
    cookie_header: str = ""
    space_name: str = ""
    owner_user_account_id: str = ""
    source_admin_session_id: str = ""
    proxy_url: str = ""


@dataclass(frozen=True)
class UpsertPersonalCodexSpaceCredentialInput:
    user_account_id: str
    external_space_id: str
    access_token: str
    id_token: str
    refresh_token: str
    codex_client_id: str
    account_id: str
    token_chatgpt_account_id: str
    expires_at: datetime | None
    raw_credential_json: dict | None = None
    space_name: str = ""


class UpsertPersonalCodexSpaceCredentialWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, input_: UpsertPersonalCodexSpaceCredentialInput) -> str:
        _validate_personal_input(input_)
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.user_accounts is None or uow.spaces is None or uow.space_credentials is None:
                raise SpaceAuthorizationWorkflowError("unit_of_work_not_initialized")
            user = uow.user_accounts.get(input_.user_account_id)
            if user is None:
                raise SpaceAuthorizationWorkflowError("missing_user_account")
            if input_.account_id and user.openai_user_id != input_.account_id:
                user.openai_user_id = input_.account_id
                user.updated_at = now
            space = uow.spaces.upsert_from_values(
                {
                    "id": f"space-{uuid4()}",
                    "provider": "openai_chatgpt",
                    "external_space_id": input_.external_space_id,
                    "owner_user_account_id": input_.user_account_id,
                    "name": input_.space_name or user.email,
                    "space_type": "personal",
                    "auth_mode": "codex_oauth",
                    "credential_type": "personal_account",
                    "plan_type": "",
                    "seat_limit": 0,
                    "seats_in_use": 0,
                    "seats_entitled": 0,
                    "space_status": "active",
                    "source_admin_session_id": "",
                    "raw_space_json": {},
                    "last_probe_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            credential = uow.space_credentials.upsert_from_values(
                {
                    "id": f"space-credential-{uuid4()}",
                    "space_id": space.id,
                    "user_account_id": input_.user_account_id,
                    "space_membership_id": None,
                    "external_credential_id": input_.codex_client_id,
                    "credential_status": "active",
                    "access_token": input_.access_token,
                    "id_token": input_.id_token,
                    "refresh_token": input_.refresh_token,
                    "codex_client_id": input_.codex_client_id,
                    "account_id": input_.account_id,
                    "token_chatgpt_account_id": input_.token_chatgpt_account_id,
                    "expires_at": input_.expires_at,
                    "last_authorized_at": now,
                    "last_probe_at": now,
                    "last_probe_status": "ok",
                    "failure_code": "",
                    "failure_message": "",
                    "raw_credential_json": input_.raw_credential_json or {},
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return credential.id


class CreateBusinessAccessTokenCredentialWorkflow:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        openai_provider: OpenAIChatGPTProvider,
    ) -> None:
        self._session_factory = session_factory
        self._openai_provider = openai_provider

    def run(self, input_: CreateBusinessAccessTokenCredentialInput) -> str:
        _validate_business_input(input_)
        usage_payload = self._openai_provider.fetch_wham_usage(
            access_token=input_.session_access_token,
            chatgpt_account_id=input_.external_space_id,
            cookie_header=input_.cookie_header,
            proxy_url=input_.proxy_url,
        )
        credential_type = infer_credential_type(
            space_type="business",
            usage_payload=usage_payload,
        )
        windows = parse_wham_usage_windows(usage_payload)
        credential_payload = self._openai_provider.create_wham_auth_credential(
            access_token=input_.session_access_token,
            chatgpt_account_id=input_.external_space_id,
            name=input_.credential_name,
            ttl_seconds=7_776_000,
            cookie_header=input_.cookie_header,
            proxy_url=input_.proxy_url,
        )
        workspace_id = str(credential_payload.get("workspace_id") or "")
        if workspace_id != input_.external_space_id:
            raise SpaceAuthorizationWorkflowError(
                "auth_credential_workspace_mismatch:"
                f"expected={input_.external_space_id},actual={workspace_id}"
            )
        access_token = str(credential_payload.get("access_token") or "")
        if not access_token:
            raise SpaceAuthorizationWorkflowError("auth_credential_missing_access_token")

        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if uow.user_accounts is None or uow.spaces is None or uow.space_credentials is None:
                raise SpaceAuthorizationWorkflowError("unit_of_work_not_initialized")
            user = uow.user_accounts.get(input_.user_account_id)
            if user is None:
                raise SpaceAuthorizationWorkflowError("missing_user_account")

            remote_user_id = str(usage_payload.get("user_id") or "")
            if remote_user_id and user.openai_user_id != remote_user_id:
                user.openai_user_id = remote_user_id
                user.updated_at = now

            space = uow.spaces.upsert_from_values(
                {
                    "id": f"space-{uuid4()}",
                    "provider": "openai_chatgpt",
                    "external_space_id": input_.external_space_id,
                    "owner_user_account_id": input_.owner_user_account_id,
                    "name": input_.space_name or input_.external_space_id,
                    "space_type": "business",
                    "auth_mode": "backend_access_token",
                    "credential_type": credential_type,
                    "plan_type": str(usage_payload.get("plan_type") or ""),
                    "seat_limit": 0,
                    "seats_in_use": 0,
                    "seats_entitled": 0,
                    "space_status": "active",
                    "source_admin_session_id": input_.source_admin_session_id,
                    "raw_space_json": usage_payload,
                    "last_probe_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            membership = _upsert_business_membership(
                session=uow.session,
                space_id=space.id,
                user_account_id=input_.user_account_id,
                remote_user_id=remote_user_id,
                now=now,
            )
            credential = uow.space_credentials.upsert_from_values(
                {
                    "id": f"space-credential-{uuid4()}",
                    "space_id": space.id,
                    "user_account_id": input_.user_account_id,
                    "space_membership_id": membership.id,
                    "external_credential_id": str(credential_payload.get("credential_id") or ""),
                    "credential_status": "active",
                    "access_token": access_token,
                    "id_token": "",
                    "refresh_token": "",
                    "codex_client_id": "",
                    "account_id": remote_user_id,
                    "token_chatgpt_account_id": input_.external_space_id,
                    "expires_at": _epoch_seconds(credential_payload.get("expires_at")),
                    "last_authorized_at": now,
                    "last_probe_at": now,
                    "last_probe_status": "ok",
                    "failure_code": "",
                    "failure_message": "",
                    "raw_credential_json": _redact_access_token(credential_payload),
                    "created_at": now,
                    "updated_at": now,
                }
            )
            for window in windows:
                _record_usage_window(
                    session=uow.session,
                    space_credential_id=credential.id,
                    space_id=space.id,
                    usage_payload=usage_payload,
                    window_kind=window.quota_window_kind,
                    used_percent=window.used_percent,
                    limit_window_seconds=window.limit_window_seconds,
                    reset_after_seconds=window.reset_after_seconds,
                    reset_at=window.reset_at,
                    now=now,
                )
            return credential.id


def _upsert_business_membership(
    *,
    session: Session,
    space_id: str,
    user_account_id: str,
    remote_user_id: str,
    now: datetime,
) -> SpaceMembershipModel:
    membership = session.scalars(
        select(SpaceMembershipModel).where(
            SpaceMembershipModel.space_id == space_id,
            SpaceMembershipModel.user_account_id == user_account_id,
        )
    ).first()
    if membership is None:
        membership = SpaceMembershipModel(
            id=f"space-membership-{uuid4()}",
            space_id=space_id,
            user_account_id=user_account_id,
            membership_status="active",
            remote_user_id=remote_user_id,
            remote_synced_at=now if remote_user_id else None,
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
        return membership
    membership.membership_status = "active"
    if remote_user_id:
        membership.remote_user_id = remote_user_id
        membership.remote_synced_at = now
    membership.updated_at = now
    return membership


def _record_usage_window(
    *,
    session: Session,
    space_credential_id: str,
    space_id: str,
    usage_payload: dict,
    window_kind: str,
    used_percent: int,
    limit_window_seconds: int,
    reset_after_seconds: int,
    reset_at: datetime | None,
    now: datetime,
) -> None:
    state = session.get(
        SpaceCredentialUsageStateModel,
        {
            "space_credential_id": space_credential_id,
            "quota_window_kind": window_kind,
        },
    )
    status = usage_status_from_percent(used_percent)
    if state is None:
        state = SpaceCredentialUsageStateModel(
            space_credential_id=space_credential_id,
            quota_window_kind=window_kind,
            space_id=space_id,
            usage_percent=used_percent,
            usage_status=status,
            limit_window_seconds=limit_window_seconds,
            reset_after_seconds=reset_after_seconds,
            reset_at=reset_at,
            last_checked_at=now,
            raw_usage_json=usage_payload,
            created_at=now,
            updated_at=now,
        )
        session.add(state)
    else:
        state.space_id = space_id
        state.usage_percent = used_percent
        state.usage_status = status
        state.limit_window_seconds = limit_window_seconds
        state.reset_after_seconds = reset_after_seconds
        state.reset_at = reset_at
        state.last_checked_at = now
        state.raw_usage_json = usage_payload
        state.error_code = ""
        state.error_message = ""
        state.updated_at = now

    session.add(
        SpaceUsageCheckModel(
            id=f"space-usage-check-{uuid4()}",
            space_credential_id=space_credential_id,
            space_id=space_id,
            quota_window_kind=window_kind,
            usage_percent=used_percent,
            limit_window_seconds=limit_window_seconds,
            reset_after_seconds=reset_after_seconds,
            reset_at=reset_at,
            allowed=bool((usage_payload.get("rate_limit") or {}).get("allowed", True)),
            limit_reached=bool((usage_payload.get("rate_limit") or {}).get("limit_reached", False)),
            raw_usage_json=usage_payload,
            check_status="ok",
            checked_at=now,
            created_at=now,
        )
    )


def _validate_business_input(input_: CreateBusinessAccessTokenCredentialInput) -> None:
    for field_name in (
        "user_account_id",
        "external_space_id",
        "session_access_token",
        "credential_name",
    ):
        if not str(getattr(input_, field_name) or "").strip():
            raise SpaceAuthorizationWorkflowError(f"{field_name} is required")


def _validate_personal_input(input_: UpsertPersonalCodexSpaceCredentialInput) -> None:
    for field_name in (
        "user_account_id",
        "external_space_id",
        "access_token",
        "refresh_token",
        "codex_client_id",
        "account_id",
        "token_chatgpt_account_id",
    ):
        if not str(getattr(input_, field_name) or "").strip():
            raise SpaceAuthorizationWorkflowError(f"{field_name} is required")


def _epoch_seconds(value) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        timestamp = int(value)
    except (TypeError, ValueError) as exc:
        raise SpaceAuthorizationWorkflowError("expires_at must be integer epoch seconds") from exc
    if timestamp <= 0:
        return None
    return datetime.fromtimestamp(timestamp, tz=UTC)


def _redact_access_token(payload: dict) -> dict:
    data = dict(payload)
    if data.get("access_token"):
        data["access_token"] = "<redacted>"
    return data
