from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from time import monotonic, sleep
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from refactor_app.infrastructure.db.models import (
    SpaceCredentialModel,
    SpaceMembershipModel,
    SpaceModel,
    UserAccountModel,
)
from refactor_app.infrastructure.db.unit_of_work import UnitOfWork
from refactor_app.plugins.contracts import OpenAIChatGPTProvider


class SpaceAuthorizationWorkflowError(RuntimeError):
    pass


BUSINESS_ACCESS_TOKEN_MIN_INTERVAL_S = 10.0
_BUSINESS_ACCESS_TOKEN_LOCKS_GUARD = Lock()
_BUSINESS_ACCESS_TOKEN_LOCKS: dict[str, Lock] = {}
_BUSINESS_ACCESS_TOKEN_LAST_STARTED_AT: dict[str, float] = {}


def run_business_access_token_rate_limited(
    *,
    external_space_id: str,
    callback: Callable[[], str],
    initial_sleep_s: float = BUSINESS_ACCESS_TOKEN_MIN_INTERVAL_S,
) -> str:
    normalized_space_id = str(external_space_id or "").strip()
    if not normalized_space_id:
        raise SpaceAuthorizationWorkflowError("external_space_id is required")
    with _BUSINESS_ACCESS_TOKEN_LOCKS_GUARD:
        lock = _BUSINESS_ACCESS_TOKEN_LOCKS.setdefault(normalized_space_id, Lock())
    with lock:
        last_started_at = _BUSINESS_ACCESS_TOKEN_LAST_STARTED_AT.get(normalized_space_id)
        if last_started_at is None:
            wait_s = max(0.0, float(initial_sleep_s or 0.0))
        else:
            wait_s = max(
                0.0,
                BUSINESS_ACCESS_TOKEN_MIN_INTERVAL_S - (monotonic() - last_started_at),
            )
        if wait_s:
            sleep(wait_s)
        _BUSINESS_ACCESS_TOKEN_LAST_STARTED_AT[normalized_space_id] = monotonic()
        return callback()


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
    token_chatgpt_account_id: str
    expires_at: datetime | None
    raw_credential_json: dict | None = None
    space_name: str = ""


@dataclass(frozen=True)
class UpsertBusinessCodexSpaceCredentialInput:
    user_account_id: str
    space_membership_id: str
    external_space_id: str
    access_token: str
    id_token: str
    refresh_token: str
    codex_client_id: str
    account_id: str
    token_chatgpt_account_id: str
    expires_at: datetime | None
    raw_credential_json: dict | None = None


@dataclass(frozen=True)
class PersonalCodexAuthorizationTarget:
    space_membership_id: str
    space_id: str
    user_account_id: str
    external_space_id: str


@dataclass(frozen=True)
class BusinessCodexAuthorizationTarget:
    space_membership_id: str
    space_id: str
    user_account_id: str
    external_space_id: str
    space_name: str
    codex_select_channel_required: bool


def resolve_personal_codex_authorization_target(
    *,
    session: Session,
    space_membership_id: str,
) -> tuple[PersonalCodexAuthorizationTarget | None, str]:
    membership = session.get(SpaceMembershipModel, space_membership_id)
    if membership is None:
        return None, "membership_not_found"
    space = session.get(SpaceModel, membership.space_id)
    if space is None:
        return None, "space_not_found"
    account = session.get(UserAccountModel, membership.user_account_id)
    if account is None:
        return None, "account_not_found"
    if space.provider != "openai_chatgpt":
        return None, "space_provider_not_openai_chatgpt"
    if space.space_type != "personal":
        return None, "space_type_not_personal"
    if space.auth_mode != "codex_oauth":
        return None, "personal_space_auth_mode_mismatch"
    if space.credential_type != "personal_account":
        return None, "personal_space_credential_type_mismatch"
    if space.space_status != "active":
        return None, "personal_space_not_active"
    if space.owner_user_account_id != account.id:
        return None, "personal_space_owner_mismatch"
    if not str(space.external_space_id or "").strip():
        return None, "missing_personal_chatgpt_account_id"
    if membership.membership_status != "active":
        return None, "space_membership_not_active"
    if not membership.session_account_detected:
        return None, "space_membership_session_account_not_detected"
    if account.account_status != "active":
        return None, "account_not_active"
    if account.codex_select_channel_required:
        return None, "phone_otp_select_channel_permanent_skip"
    if not str(account.openai_user_id or "").strip():
        return None, "missing_user_openai_user_id"
    cookie_header = str(account.cookie_header or "").strip()
    auth_cookie_header = str(account.auth_cookie_header or "").strip()
    if not (cookie_header or auth_cookie_header):
        return None, "missing_session_cookie"
    active_credential_id = session.scalar(
        select(SpaceCredentialModel.id).where(
            SpaceCredentialModel.space_id == space.id,
            SpaceCredentialModel.user_account_id == account.id,
            SpaceCredentialModel.credential_status == "active",
        )
    )
    if active_credential_id:
        return None, "credential_already_active"
    return (
        PersonalCodexAuthorizationTarget(
            space_membership_id=membership.id,
            space_id=space.id,
            user_account_id=account.id,
            external_space_id=space.external_space_id,
        ),
        "",
    )


def resolve_business_codex_authorization_target(
    *,
    session: Session,
    space_membership_id: str,
) -> tuple[BusinessCodexAuthorizationTarget | None, str]:
    membership = session.get(SpaceMembershipModel, space_membership_id)
    if membership is None:
        return None, "membership_not_found"
    space = session.get(SpaceModel, membership.space_id)
    if space is None:
        return None, "space_not_found"
    account = session.get(UserAccountModel, membership.user_account_id)
    if account is None:
        return None, "account_not_found"
    if space.provider != "openai_chatgpt":
        return None, "space_provider_not_openai_chatgpt"
    if space.space_type != "business":
        return None, "space_type_not_business"
    if space.credential_type not in {"team_5h_weekly", "team_monthly"}:
        return None, "business_space_credential_type_mismatch"
    if space.space_status != "active":
        return None, "business_space_not_active"
    if not str(space.external_space_id or "").strip():
        return None, "missing_business_chatgpt_account_id"
    if membership.membership_status != "active":
        return None, "space_membership_not_active"
    if not membership.session_account_detected:
        return None, "space_membership_session_account_not_detected"
    if account.account_status != "active":
        return None, "account_not_active"
    if account.session_status != "active":
        return None, "account_session_not_active"
    if not str(account.openai_user_id or "").strip():
        return None, "missing_user_openai_user_id"
    if not (
        str(account.cookie_header or "").strip()
        or str(account.auth_cookie_header or "").strip()
        or str(account.session_token or "").strip()
    ):
        return None, "missing_session_cookie"
    active_credential_id = session.scalar(
        select(SpaceCredentialModel.id).where(
            SpaceCredentialModel.space_id == space.id,
            SpaceCredentialModel.user_account_id == account.id,
            SpaceCredentialModel.credential_status == "active",
        )
    )
    if active_credential_id:
        return None, "credential_already_active"
    return (
        BusinessCodexAuthorizationTarget(
            space_membership_id=membership.id,
            space_id=space.id,
            user_account_id=account.id,
            external_space_id=space.external_space_id,
            space_name=space.name,
            codex_select_channel_required=bool(account.codex_select_channel_required),
        ),
        "",
    )


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
            account_id = user.openai_user_id.strip()
            if not account_id:
                raise SpaceAuthorizationWorkflowError("missing_user_openai_user_id")
            existing_space = uow.spaces.get_by_provider_external_id(
                provider="openai_chatgpt",
                external_space_id=input_.external_space_id,
            )
            if existing_space is None:
                raise SpaceAuthorizationWorkflowError("missing_personal_space")
            if existing_space.owner_user_account_id != input_.user_account_id:
                raise SpaceAuthorizationWorkflowError("personal_space_owner_mismatch")
            if existing_space.space_type != "personal":
                raise SpaceAuthorizationWorkflowError("space_type_not_personal")
            if existing_space.auth_mode != "codex_oauth":
                raise SpaceAuthorizationWorkflowError("personal_space_auth_mode_mismatch")
            if existing_space.credential_type != "personal_account":
                raise SpaceAuthorizationWorkflowError("personal_space_credential_type_mismatch")
            if existing_space.space_status != "active":
                raise SpaceAuthorizationWorkflowError("personal_space_not_active")
            space = existing_space
            credential = uow.space_credentials.upsert_from_values(
                {
                    "id": f"space-credential-{uuid4()}",
                    "space_id": space.id,
                    "user_account_id": input_.user_account_id,
                    "space_membership_id": None,
                    "external_credential_id": input_.codex_client_id,
                    "auth_mode": "codex_oauth",
                    "credential_status": "active",
                    "access_token": input_.access_token,
                    "id_token": input_.id_token,
                    "refresh_token": input_.refresh_token,
                    "codex_client_id": input_.codex_client_id,
                    "account_id": account_id,
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


class UpsertBusinessCodexSpaceCredentialWorkflow:
    def __init__(self, *, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def run(self, input_: UpsertBusinessCodexSpaceCredentialInput) -> str:
        _validate_business_codex_input(input_)
        now = datetime.now(UTC)
        with UnitOfWork(self._session_factory) as uow:
            if (
                uow.user_accounts is None
                or uow.spaces is None
                or uow.space_credentials is None
                or uow.space_memberships is None
            ):
                raise SpaceAuthorizationWorkflowError("unit_of_work_not_initialized")
            user = uow.user_accounts.get(input_.user_account_id)
            if user is None:
                raise SpaceAuthorizationWorkflowError("missing_user_account")
            expected_user_id = str(user.openai_user_id or "").strip()
            if not expected_user_id:
                raise SpaceAuthorizationWorkflowError("missing_user_openai_user_id")
            if input_.account_id != expected_user_id:
                raise SpaceAuthorizationWorkflowError("business_codex_user_mismatch")
            space = uow.spaces.get_by_provider_external_id(
                provider="openai_chatgpt",
                external_space_id=input_.external_space_id,
            )
            if space is None:
                raise SpaceAuthorizationWorkflowError("missing_business_space")
            if space.space_type != "business":
                raise SpaceAuthorizationWorkflowError("space_type_not_business")
            if space.space_status != "active":
                raise SpaceAuthorizationWorkflowError("space_not_active")
            if space.credential_type not in {"team_5h_weekly", "team_monthly"}:
                raise SpaceAuthorizationWorkflowError("invalid_space_credential_type")
            if input_.token_chatgpt_account_id != space.external_space_id:
                raise SpaceAuthorizationWorkflowError("business_codex_space_mismatch")
            membership = uow.space_memberships.get_by_user_and_space(
                user_account_id=input_.user_account_id,
                space_id=space.id,
            )
            if membership is None or membership.id != input_.space_membership_id:
                raise SpaceAuthorizationWorkflowError("missing_active_space_membership")
            if membership.membership_status != "active":
                raise SpaceAuthorizationWorkflowError("space_membership_not_active")
            if not membership.session_account_detected:
                raise SpaceAuthorizationWorkflowError(
                    "space_membership_session_account_not_detected"
                )
            credential = uow.space_credentials.upsert_from_values(
                {
                    "id": f"space-credential-{uuid4()}",
                    "space_id": space.id,
                    "user_account_id": input_.user_account_id,
                    "space_membership_id": membership.id,
                    "external_credential_id": input_.codex_client_id,
                    "auth_mode": "codex_oauth",
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
        with UnitOfWork(self._session_factory) as uow:
            if (
                uow.user_accounts is None
                or uow.spaces is None
                or uow.space_credentials is None
                or uow.space_memberships is None
            ):
                raise SpaceAuthorizationWorkflowError("unit_of_work_not_initialized")
            user = uow.user_accounts.get(input_.user_account_id)
            if user is None:
                raise SpaceAuthorizationWorkflowError("missing_user_account")
            space = uow.spaces.get_by_provider_external_id(
                provider="openai_chatgpt",
                external_space_id=input_.external_space_id,
            )
            if space is None:
                raise SpaceAuthorizationWorkflowError("missing_business_space")
            if space.space_type != "business":
                raise SpaceAuthorizationWorkflowError("space_type_not_business")
            if space.space_status != "active":
                raise SpaceAuthorizationWorkflowError("space_not_active")
            if space.credential_type not in {"team_5h_weekly", "team_monthly"}:
                raise SpaceAuthorizationWorkflowError("invalid_space_credential_type")
            membership = uow.space_memberships.get_by_user_and_space(
                user_account_id=input_.user_account_id,
                space_id=space.id,
            )
            if membership is None:
                raise SpaceAuthorizationWorkflowError("missing_active_space_membership")
            if membership.membership_status != "active":
                raise SpaceAuthorizationWorkflowError("space_membership_not_active")
            if not membership.session_account_detected:
                raise SpaceAuthorizationWorkflowError(
                    "space_membership_session_account_not_detected"
                )
            existing = uow.space_credentials.get_current(
                space_id=space.id,
                user_account_id=input_.user_account_id,
            )
            if existing is not None and existing.credential_status == "active":
                return existing.id
            space_id = space.id
            credential_account_id = str(membership.remote_user_id or "").strip()
            if not credential_account_id:
                credential_account_id = str(user.openai_user_id or "").strip()
            if not credential_account_id:
                raise SpaceAuthorizationWorkflowError("missing_business_credential_account_id")

        credential_payload = self._openai_provider.create_wham_auth_credential(
            access_token="",
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
            if (
                uow.user_accounts is None
                or uow.space_credentials is None
                or uow.space_memberships is None
            ):
                raise SpaceAuthorizationWorkflowError("unit_of_work_not_initialized")
            user = uow.user_accounts.get(input_.user_account_id)
            if user is None:
                raise SpaceAuthorizationWorkflowError("missing_user_account")
            membership = uow.space_memberships.get_by_user_and_space(
                user_account_id=input_.user_account_id,
                space_id=space_id,
            )
            if membership is None:
                raise SpaceAuthorizationWorkflowError("missing_active_space_membership")
            if membership.membership_status != "active":
                raise SpaceAuthorizationWorkflowError("space_membership_not_active")
            if not membership.session_account_detected:
                raise SpaceAuthorizationWorkflowError(
                    "space_membership_session_account_not_detected"
                )

            credential = uow.space_credentials.upsert_from_values(
                {
                    "id": f"space-credential-{uuid4()}",
                    "space_id": space_id,
                    "user_account_id": input_.user_account_id,
                    "space_membership_id": membership.id,
                    "external_credential_id": str(credential_payload.get("credential_id") or ""),
                    "auth_mode": "backend_access_token",
                    "credential_status": "active",
                    "access_token": access_token,
                    "id_token": "",
                    "refresh_token": "",
                    "codex_client_id": "",
                    "account_id": credential_account_id,
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
            return credential.id


def _validate_business_input(input_: CreateBusinessAccessTokenCredentialInput) -> None:
    for field_name in (
        "user_account_id",
        "external_space_id",
        "credential_name",
    ):
        if not str(getattr(input_, field_name) or "").strip():
            raise SpaceAuthorizationWorkflowError(f"{field_name} is required")
    if not input_.cookie_header.strip():
        raise SpaceAuthorizationWorkflowError("cookie_header is required")


def _validate_personal_input(input_: UpsertPersonalCodexSpaceCredentialInput) -> None:
    for field_name in (
        "user_account_id",
        "external_space_id",
        "access_token",
        "refresh_token",
        "codex_client_id",
        "token_chatgpt_account_id",
    ):
        if not str(getattr(input_, field_name) or "").strip():
            raise SpaceAuthorizationWorkflowError(f"{field_name} is required")


def _validate_business_codex_input(input_: UpsertBusinessCodexSpaceCredentialInput) -> None:
    for field_name in (
        "user_account_id",
        "space_membership_id",
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
